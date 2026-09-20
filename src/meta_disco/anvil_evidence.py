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
recoverable as the set it was. A cell that is null, or an empty list — which observes
nothing, where an empty string is something the source published — is skipped and
counted against the column, once per row and column on the rows whose link resolved —
not once per slot the column feeds, so a diagnostic can never exceed the table it
describes. A name span is written as the span itself, in the name's casing.

**Provenance** names the value's column. An evidence row's ``column`` is the cell the
raw value came from, not the file-link column that reached the file; a ``table_name``
source has no column, and a ``column_name`` source names the column whose name it is.
The file itself is named by its DRS URI, which the submitter wrote in the link column
and AnVIL publishes unchanged as ``drs_uri`` — so ``source_key`` and ``target_key``
are the same string, resolved here against the dataset's own ``anvil_file`` entities:
a link an importer cannot resolve is counted per column and not written.

**An import is a generation** (`source_evidence.generation_dir`): written once, never
over an earlier one, and read by ``discover`` as the newest per dataset. Within-source
contradictions pass through — a FASTQ reached by both an SGDP CHM13v2 table and an
SGDP GRCh38 table receives both spans, and which is right is the resolver's (4.5).
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .azul_manifest import (
    ANVIL_FILE_HANDLE_COLUMNS,
    API_URL,
    FORMAT_VERBATIM,
    REPOSITORY,
    VERBATIM_FILE,
    iter_verbatim_entities,
    link_handles,
    manifest_path,
    sidecar_datasets,
    sidecar_requested_at,
)
from .models import JOIN_KEY_DRS_URI, SOURCE_REPOSITORY_METADATA, ClaimSource
from .slot_map import SOURCE_CELL, SOURCE_COLUMN_NAME, ColumnEntry, SlotMap, SlotSource
from .source_evidence import (
    EvidenceEntry,
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    evidence_file_path,
    generation_dir,
    new_generation,
    write_evidence_file,
)


@dataclass
class TableImport:
    """What one mapped table produced, and what it could not.

    ``no_link``, ``not_link`` and ``unresolved`` are per file-link column: rows whose link
    cell held nothing, rows whose cell held something that is not a DRS URI (which
    ``check`` reports and an import still counts, so a drifted manifest cannot pass
    silently), and handles not among the dataset's own files. ``null_cells`` is per cell
    column, once per row and column, counting null and empty-list cells on the rows
    whose link resolved. ``files`` is the distinct files that received at
    least one evidence row; ``written`` counts the rows, which exceeds it wherever a
    file has several slots or sources.
    """

    table: str
    path: Path
    rows: int = 0
    written: int = 0
    files: set[str] = field(default_factory=set)
    no_link: Counter = field(default_factory=Counter)
    not_link: Counter = field(default_factory=Counter)
    unresolved: Counter = field(default_factory=Counter)
    null_cells: Counter = field(default_factory=Counter)


@dataclass
class DatasetImport:
    """One generation of one dataset: where it went and what each table produced."""

    dataset: str
    generation: str
    directory: Path
    tables: list[TableImport]

    @property
    def files(self) -> int:
        """Distinct files that received at least one evidence row, across the tables."""
        return len(set().union(*(table.files for table in self.tables)))


# --- checking the map against the manifests -----------------------------------


def check(slot_map: SlotMap, manifest_root: Path, catalog: str, datasets: list[str] | None = None) -> list[str]:
    """How the map disagrees with the manifests on disk, one line per problem; empty when none.

    Per mapped dataset (or those in ``datasets``): the sidecar names it and its verbatim
    manifest is on disk. Per mapped table: at least one row of that type exists. Per
    file-link column: it appears on some row, and every non-empty value it holds is a
    DRS URI or a list of them. Per cell: the column appears on some row of its table
    and is not itself a file-link column — a column is one kind, never two (contract
    2.7). Every chosen dataset is checked, and within one every table and column, so a
    map edited in one sitting is answered in one pass; a dataset whose manifest is
    missing, or a table with no rows, masks the problems beneath it until that one is
    fixed.
    """
    problems: list[str] = []
    named = sidecar_datasets(manifest_root, catalog)
    known = slot_map.datasets()
    for dataset in known if datasets is None else dict.fromkeys(datasets):
        if dataset not in known:
            problems.append(f"{dataset}: not in the slot map")
            continue
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
    wanted = {table: [entry.column for entry in slot_map.columns(dataset, table)] for table in tables}
    cells = {table: sorted(slot_map.cells(dataset, table)) for table in tables}
    rows: Counter = Counter()
    columns_seen: dict[str, set[str]] = {table: set() for table in tables}
    not_links: dict[tuple[str, str], object] = {}
    # A cell is a link column when every non-empty value it holds is a link: `None`
    # until a non-empty value is seen, then whether all of them so far were links.
    cell_is_link: dict[tuple[str, str], bool | None] = {(t, c): None for t in tables for c in cells[t]}
    for table, row in iter_verbatim_entities(path, tables):
        rows[table] += 1
        columns_seen[table].update(row)
        for column in wanted[table]:
            if (table, column) not in not_links and link_handles(row.get(column)) == []:
                not_links[(table, column)] = row[column]
        for cell in cells[table]:
            handles = link_handles(row.get(cell))
            if handles is not None and cell_is_link[(table, cell)] is not False:
                cell_is_link[(table, cell)] = handles != []
    problems = []
    for table in tables:
        if not rows[table]:
            problems.append(f"{dataset}/{table}: no row of this type in the manifest")
            continue
        for column in wanted[table]:
            if column not in columns_seen[table]:
                problems.append(f"{dataset}/{table}/{column}: no row carries this column")
            elif (table, column) in not_links:
                problems.append(
                    f"{dataset}/{table}/{column}: holds {not_links[(table, column)]!r}, "
                    "not a DRS URI or a list of them — not a file-link column"
                )
        for cell in cells[table]:
            if cell not in columns_seen[table]:
                problems.append(f"{dataset}/{table}: cell {cell!r} is not a column of this table")
            elif cell_is_link[(table, cell)]:
                problems.append(
                    f"{dataset}/{table}: cell {cell!r} holds DRS URIs — a file-link column, not a metadata value"
                )
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
    disk; each dataset is still imported whole and independently, and once however many
    times it is named. Raises before writing anything if a named dataset is not in the map.
    """
    known = slot_map.datasets()
    chosen = known if datasets is None else list(dict.fromkeys(datasets))
    unknown = [d for d in chosen if d not in known]
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
    file keeps ``write_evidence_file``'s write-then-rename guarantee on its own; each
    pass parses only the lines that name its table (``iter_verbatim_entities``'s gate).

    The generation directory must not exist: an import never writes over another. It
    is a generation only once every table is written: a failure part-way — a bad row,
    a full disk, an interrupt — removes the directory before the error propagates, so
    ``discover`` cannot take a half-written generation for the dataset's newest. A hard
    kill leaves that residue to remove by hand. A mapped table that writes no row at all
    is such a failure: a table the map names should reach files, and one that reaches
    none is the map disagreeing with the catalog (contract 5.3), not an empty result.
    The evidence root directory and the target system are both the repository the
    manifests came from.
    """
    stamp = generation if generation is not None else new_generation()
    directory = generation_dir(evidence_root, REPOSITORY, catalog, dataset, stamp)
    if directory.exists():
        raise FileExistsError(f"{directory}: generation already written — an import never overwrites one")
    path = manifest_path(manifest_root, catalog, dataset, FORMAT_VERBATIM)
    # When the *source* was fetched — the manifest's request time, not the import's. A
    # sidecar that cannot say is refused: an evidence file must record it, and inventing
    # the import time would be a fetch the file never made.
    fetched_at = sidecar_requested_at(manifest_root, catalog, dataset, FORMAT_VERBATIM)
    if fetched_at is None:
        raise ValueError(
            f"{dataset}: the {catalog} sidecar records no {FORMAT_VERBATIM} requested_at to write as fetched_at"
        )
    handles = _file_handles(path)
    tables = []
    try:
        for table in slot_map.tables(dataset):
            source = EvidenceFileSource(repository=REPOSITORY, dataset=dataset, table=table, url=API_URL)
            envelope = EvidenceFileEnvelope(
                source=source,
                source_type=SOURCE_REPOSITORY_METADATA,
                source_version=catalog,
                source_key=JOIN_KEY_DRS_URI,
                target=EvidenceTarget(system=REPOSITORY, dataset=dataset, version=catalog),
                target_key=JOIN_KEY_DRS_URI,
                fetched_at=fetched_at,
            )
            result = TableImport(table=table, path=evidence_file_path(directory, table))
            entries = _table_entries(path, table, slot_map.columns(dataset, table), handles, source, result)
            result.written = write_evidence_file(result.path, envelope, entries)
            if not result.written:
                raise ValueError(
                    f"{dataset}/{table}: no evidence row written — every link was empty or outside the "
                    f"dataset's files, or every mapped cell was null; the map disagrees with {catalog} here"
                )
            tables.append(result)
    except BaseException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return DatasetImport(dataset=dataset, generation=stamp, directory=directory, tables=tables)


def _file_handles(path: Path) -> set[str]:
    """The dataset's own files, as the DRS URIs its ``anvil_file`` entities carry."""
    handles = set()
    for _table, value in iter_verbatim_entities(path, {VERBATIM_FILE}):
        for column in ANVIL_FILE_HANDLE_COLUMNS:
            handles.update(link_handles(value.get(column)) or [])
    return handles


def _table_entries(
    path: Path,
    table: str,
    columns: list[ColumnEntry],
    handles: set[str],
    source: EvidenceFileSource,
    result: TableImport,
) -> Iterator[EvidenceEntry]:
    """Every evidence row one table yields, streamed row by row, counting into ``result``."""
    by_column: dict[str | None, ClaimSource] = {}
    for _type, row in iter_verbatim_entities(path, {table}):
        result.rows += 1
        nulls: set[str] = set()
        for entry in columns:
            links = link_handles(row.get(entry.column))
            if links is None:
                result.no_link[entry.column] += 1
                continue
            if not links:
                result.not_link[entry.column] += 1
                continue
            for handle in links:
                if handle not in handles:
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
                        result.files.add(handle)
                        yield EvidenceEntry(field=slot, target_key_value=handle, raw_value=raw, source=claim_source)


def _transcribe(
    spec: SlotSource, row: dict, link_column: str, nulls: set[str], result: TableImport
) -> tuple[str | None, str | None]:
    """The raw value one source yields for this row, and the column to record for it.

    ``None`` for a null or empty-list cell, counted once per row against its column:
    ``nulls`` is the row's own set, shared across every slot and file the row feeds. An
    empty list is treated as null and not as the JSON ``[]`` because it observes
    nothing; the empty string is kept because the source wrote it. A non-string scalar
    (a number, a boolean the manifest carries as JSON) is written as its JSON literal —
    still what the source wrote, in the one spelling JSON has for it.
    """
    if spec.form == SOURCE_CELL:
        value = row.get(spec.value)
        if value is None or value == []:
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
            for column, n in sorted(table.not_link.items()):
                lines.append(f"    {column}: not a DRS URI on {n:,} rows")
            for column, n in sorted(table.unresolved.items()):
                lines.append(f"    {column}: {n:,} links not among the dataset's files")
            for column, n in sorted(table.null_cells.items()):
                lines.append(f"    {column}: null on {n:,} rows")
    return lines
