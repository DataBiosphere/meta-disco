"""Read AnVIL's submitter tables into evidence files, through the slot map (#369).

The verbatim manifests (#368) carry every submitter table unaltered, and the slot map
(`slot_map`) says which of their columns and names speak to which slot. This module is
the importer between the two: it checks the map against the manifests, then writes,
per dataset, one generation of evidence files with one file per mapped table. It is an
importer in the contract's sense (1.2, 1.3): it transcribes what a source wrote and
maps structure, never meaning. No vocabulary, no value mapping, no claim — ``PACBIO_SMRT``
is written as ``PACBIO_SMRT`` and what it means is the translation table's (#414).

**Transcription** (contract 1.4). A string cell is written verbatim, the empty string
included. A list cell is written as its JSON array, so a set of assay titles is
recoverable as the set it was. A cell that is null is skipped and counted against the
column that was null, once per row and column — not once per slot the column feeds, so
a diagnostic can never exceed the table it describes. A name span is written as the
span itself, in the name's casing.

**Provenance** names the value's column. An evidence row's ``column`` is the cell the
raw value came from, not the file-link column that reached the file; a ``table_name``
source has no column, and a ``column_name`` source names the column whose name it is.
The file itself is named by its DRS URI, which the submitter wrote in the link column
and AnVIL publishes unchanged as ``drs_uri`` — so ``source_key`` and ``target_key``
are the same string, resolved here against the dataset's own ``anvil_file`` entities:
a link an importer cannot resolve is counted, not written (5.3).

**An import is a generation** (`source_evidence.generation_dir`): written once, never
over an earlier one, and read by ``discover`` as the newest per dataset. Within-source
contradictions pass through — a FASTQ reached by both an SGDP CHM13v2 table and an
SGDP GRCh38 table receives both spans, and which is right is the resolver's (4.5).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .azul_manifest import API_URL, FORMAT_VERBATIM, REPOSITORY, VERBATIM_FILE, load_sidecar, manifest_path
from .models import JOIN_KEY_DRS_URI, SOURCE_REPOSITORY_METADATA, ClaimSource
from .slot_map import SOURCE_CELL, SOURCE_COLUMN_NAME, ColumnEntry, SlotMap, SlotSource
from .source_evidence import (
    EVIDENCE_FILE_GLOB,
    EvidenceEntry,
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    generation_dir,
    new_generation,
    write_evidence_file,
)

# The source's directory under the evidence root, and the target system: both are the
# repository the manifests came from.
SOURCE = REPOSITORY
_DRS_PREFIX = "drs://"


@dataclass
class TableImport:
    """What one mapped table produced, and what it could not.

    ``no_link`` and ``unresolved`` are per file-link column: rows whose link cell held
    nothing, and handles not among the dataset's own files. ``null_cells`` is per cell
    column, once per row and column. ``written`` is evidence lines, which exceeds the
    number of files reached wherever a file has several slots or sources.
    """

    table: str
    path: Path
    rows: int = 0
    written: int = 0
    no_link: Counter = field(default_factory=Counter)
    unresolved: Counter = field(default_factory=Counter)
    null_cells: Counter = field(default_factory=Counter)


@dataclass
class DatasetImport:
    """One generation of one dataset: where it went and what each table produced."""

    dataset: str
    generation: str
    directory: Path
    tables: list[TableImport]
    files: int  # distinct files that received at least one evidence row


# --- checking the map against the manifests -----------------------------------


def check(slot_map: SlotMap, manifest_root: Path, catalog: str) -> list[str]:
    """Every way the map disagrees with the manifests on disk, all at once; empty when none.

    Per mapped dataset: the sidecar names it and its verbatim manifest is on disk. Per
    mapped table: at least one row of that type exists. Per file-link column: it appears
    on some row, and every value it holds is a DRS URI or a list of them. Per cell: the
    column appears on some row of its table. Reported together rather than at the first,
    because a map is edited in one sitting and each problem costs a pass over a
    half-gigabyte manifest to find.
    """
    problems: list[str] = []
    named = load_sidecar(manifest_root, catalog).get("datasets") or {}
    for dataset in slot_map.datasets():
        if dataset not in named:
            problems.append(f"{dataset}: not a dataset the {catalog} sidecar names")
            continue
        path = manifest_path(manifest_root, catalog, dataset, FORMAT_VERBATIM)
        if not path.is_file():
            problems.append(f"{dataset}: no verbatim manifest at {path}")
            continue
        problems += _check_dataset(slot_map, dataset, path)
    return problems


def _check_dataset(slot_map: SlotMap, dataset: str, path: Path) -> list[str]:
    tables = slot_map.tables(dataset)
    rows: Counter = Counter()
    columns_seen: set[tuple[str, str]] = set()
    not_links: dict[tuple[str, str], object] = {}
    wanted = {(table, entry.column) for table in tables for entry in slot_map.columns(dataset, table)}
    for table, row in _rows(path, set(tables)):
        rows[table] += 1
        for column in row:
            columns_seen.add((table, column))
        for table_name, column in wanted:
            if table_name != table or (table, column) in not_links:
                continue
            value = row.get(column)
            if value is None or value == "" or value == []:
                continue
            handles = value if isinstance(value, list) else [value]
            if not all(isinstance(h, str) and h.startswith(_DRS_PREFIX) for h in handles):
                not_links[(table, column)] = value
    problems = []
    for table in tables:
        if not rows[table]:
            problems.append(f"{dataset}/{table}: no row of this type in the manifest")
            continue
        for entry in slot_map.columns(dataset, table):
            if (table, entry.column) not in columns_seen:
                problems.append(f"{dataset}/{table}/{entry.column}: no row carries this column")
            elif (table, entry.column) in not_links:
                problems.append(
                    f"{dataset}/{table}/{entry.column}: holds {not_links[(table, entry.column)]!r}, "
                    "not a DRS URI or a list of them — not a file-link column"
                )
        for cell in sorted(slot_map.cells(dataset, table)):
            if (table, cell) not in columns_seen:
                problems.append(f"{dataset}/{table}: cell {cell!r} is not a column of this table")
    return problems


# --- importing -----------------------------------------------------------------


def import_all(
    slot_map: SlotMap,
    manifest_root: Path,
    catalog: str,
    evidence_root: Path,
    datasets: list[str] | None = None,
    generation: str | None = None,
) -> list[DatasetImport]:
    """Import every dataset the map names (or ``datasets``), each as one new generation.

    The stamp is shared across the datasets of one run so the run is one generation on
    disk; each dataset is still imported whole and independently. Raises before writing
    anything if a named dataset is not in the map.
    """
    chosen = slot_map.datasets() if datasets is None else list(datasets)
    unknown = [d for d in chosen if d not in slot_map.datasets()]
    if unknown:
        raise ValueError(f"not in the slot map: {unknown}")
    stamp = generation if generation is not None else new_generation()
    return [import_dataset(slot_map, manifest_root, catalog, dataset, evidence_root, stamp) for dataset in chosen]


def import_dataset(
    slot_map: SlotMap,
    manifest_root: Path,
    catalog: str,
    dataset: str,
    evidence_root: Path,
    generation: str | None = None,
) -> DatasetImport:
    """Write one generation of evidence files for one dataset.

    Two kinds of pass over the manifest: one to collect the dataset's own file handles
    (its ``anvil_file`` DRS URIs), then one per mapped table to write that table's file.
    Per-table passes rather than one pass fanning out to every table's writer, so each
    file keeps ``write_evidence_file``'s write-then-rename guarantee on its own. A pass
    parses only the lines that name its table, which the cheap substring test in
    :func:`_rows` gates.

    The generation directory must not exist: an import never writes over another.
    """
    stamp = generation if generation is not None else new_generation()
    directory = generation_dir(evidence_root, SOURCE, catalog, dataset, stamp)
    if directory.exists():
        raise FileExistsError(f"{directory}: generation already written — an import never overwrites one")
    path = manifest_path(manifest_root, catalog, dataset, FORMAT_VERBATIM)
    fetched_at = _fetched_at(manifest_root, catalog, dataset)
    handles = _file_handles(path)
    files: set[str] = set()
    tables = []
    for table in slot_map.tables(dataset):
        source = EvidenceFileSource(repository=REPOSITORY, dataset=dataset, table=table, url=API_URL)
        envelope = EvidenceFileEnvelope(
            source=source,
            source_type=SOURCE_REPOSITORY_METADATA,
            source_version=catalog,
            source_key=JOIN_KEY_DRS_URI,
            target=EvidenceTarget(system=SOURCE, dataset=dataset, version=catalog),
            target_key=JOIN_KEY_DRS_URI,
            fetched_at=fetched_at,
        )
        result = TableImport(table=table, path=directory / f"{table}{EVIDENCE_FILE_GLOB.lstrip('*')}")
        entries = _table_entries(path, table, slot_map.columns(dataset, table), handles, source, result, files)
        result.written = write_evidence_file(result.path, envelope, entries)
        tables.append(result)
    return DatasetImport(dataset=dataset, generation=stamp, directory=directory, tables=tables, files=len(files))


def _fetched_at(manifest_root: Path, catalog: str, dataset: str) -> datetime:
    """When the dataset's verbatim manifest was fetched, from the download sidecar.

    The envelope's ``fetched_at`` is when the *source* was fetched, which is the
    manifest's request time and not the import's. A sidecar that cannot say is refused:
    an evidence file must record it, and inventing the import time would be a fetch
    the file never made.
    """
    entry = (load_sidecar(manifest_root, catalog).get("datasets") or {}).get(dataset) or {}
    requested = (entry.get(FORMAT_VERBATIM) or {}).get("requested_at")
    if not isinstance(requested, str):
        raise ValueError(
            f"{dataset}: the {catalog} sidecar records no {FORMAT_VERBATIM} requested_at to write as fetched_at"
        )
    return datetime.fromisoformat(requested)


def _file_handles(path: Path) -> set[str]:
    """The dataset's own files, as the DRS URIs its ``anvil_file`` entities carry."""
    handles = set()
    for _table, value in _rows(path, {VERBATIM_FILE}):
        for key in ("drs_uri", "file_ref"):
            handle = value.get(key)
            if isinstance(handle, str) and handle.startswith(_DRS_PREFIX):
                handles.add(handle)
    return handles


def _rows(path: Path, tables: set[str]) -> Iterator[tuple[str, dict]]:
    """Every ``(type, value)`` of the named types, streamed, parsing only candidate lines.

    A verbatim line is ``{"value": {...}, "type": "..."}``; the type sits at the end, so
    a substring test on ``"<table>"`` is what keeps a per-table pass from parsing every
    line of a half-gigabyte file. The test is a gate, not the decision: the parsed type
    is what selects the row. Malformed lines raise naming the file and line, as
    ``azul_manifest.iter_verbatim_entities`` does.
    """
    needles = [f'"{table}"' for table in tables]
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            if not any(needle in line for needle in needles):
                continue
            try:
                entity = json.loads(line)
                entity_type, value = entity["type"], entity["value"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"{path.name} line {n}: not a verbatim entity: {exc!r}") from None
            if entity_type in tables and isinstance(value, dict):
                yield entity_type, value


def _table_entries(
    path: Path,
    table: str,
    columns: list[ColumnEntry],
    handles: set[str],
    source: EvidenceFileSource,
    result: TableImport,
    files: set[str],
) -> Iterator[EvidenceEntry]:
    """Every evidence row one table yields, streamed row by row."""
    by_column: dict[str | None, ClaimSource] = {}
    for _type, row in _rows(path, {table}):
        result.rows += 1
        nulls: set[str] = set()
        for entry in columns:
            link = row.get(entry.column)
            if link is None or link == "" or link == []:
                result.no_link[entry.column] += 1
                continue
            for handle in link if isinstance(link, list) else [link]:
                if not isinstance(handle, str) or handle not in handles:
                    result.unresolved[entry.column] += 1
                    continue
                for slot, sources in entry.slots.items():
                    for spec in sources:
                        raw, column = _transcribe(spec, row, entry.column, nulls, result)
                        if raw is None:
                            continue
                        claim_source = by_column.get(column)
                        if claim_source is None:
                            claim_source = by_column[column] = source.as_claim_source(column)
                        # Counted here and not when the link resolved: a file whose every
                        # mapped cell is null receives nothing, and is not "a file with evidence".
                        files.add(handle)
                        yield EvidenceEntry(field=slot, target_key_value=handle, raw_value=raw, source=claim_source)


def _transcribe(
    spec: SlotSource, row: dict, link_column: str, nulls: set[str], result: TableImport
) -> tuple[str | None, str | None]:
    """The raw value one source yields for this row, and the column to record for it.

    ``None`` for a null cell, counted once per row against its column: ``nulls`` is the
    row's own set, shared across every slot and file the row feeds. A non-string scalar
    (a number, a boolean the manifest carries as JSON) is written as its JSON literal —
    still what the source wrote, in the one spelling JSON has for it.
    """
    if spec.form == SOURCE_CELL:
        value = row.get(spec.value)
        if value is None:
            if spec.value not in nulls:
                nulls.add(spec.value)
                result.null_cells[spec.value] += 1
            return None, None
        return (value if isinstance(value, str) else json.dumps(value)), spec.value
    if spec.form == SOURCE_COLUMN_NAME:
        return spec.value, link_column
    return spec.value, None


# --- reporting -----------------------------------------------------------------


def describe(imports: list[DatasetImport]) -> list[str]:
    """One block per dataset: the generation, then each table's counts."""
    lines = []
    for run in imports:
        lines.append(f"{run.dataset} -> {run.directory} ({run.files:,} files)")
        for table in run.tables:
            lines.append(f"  {table.table}: {table.rows:,} rows, {table.written:,} evidence rows")
            for column, n in sorted(table.no_link.items()):
                lines.append(f"    {column}: no link on {n:,} rows")
            for column, n in sorted(table.unresolved.items()):
                lines.append(f"    {column}: {n:,} links not among the dataset's files")
            for column, n in sorted(table.null_cells.items()):
                lines.append(f"    {column}: null on {n:,} rows")
    return lines
