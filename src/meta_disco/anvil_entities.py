"""Read AnVIL's donor facts into entity evidence files, through the entity map (#693).

The entity map (``entity_map``) says which submitter table's columns say what about a
donor, and which column names the donor. This module checks the map against the verbatim
manifests on disk, then writes, per dataset, one generation of entity evidence files: one
file per mapped table under ``<root>/anvil/``, and one for AnVIL's published donor table
under ``<root>/anvil_published/``, each line an ``EntityEvidenceRow``.

**A line is a cell, as written** (contract 1.1, 1.4): the identifier string the row names
the donor by, and the cell's value — a string verbatim, anything else as ``json.dumps``
spells it (1000 Genomes' ``pedigree.sex`` is the number ``1``). Neither is interpreted
here: the identifier rules recognise the identifier and the value map translates the
value, both at reconcile. A null or empty-list cell, or a row whose identifier cell is not
a non-empty string, writes nothing and is counted.

**AnVIL's published donor** names no identifier of its own that crosses datasets: it is
attached to one through the submitter row it was made from (``source_rows``), read in that
row's table's identifier column. A donor whose source rows are in no mapped table, are not
found, or name two identifiers writes nothing and is counted.

Offline: it reads what ``make download`` left on disk.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .anvil_evidence import EVIDENCE_DIRS, chosen_datasets, verbatim_manifest
from .azul_manifest import (
    FORMAT_VERBATIM,
    REPOSITORY,
    iter_verbatim_entities,
    manifest_path,
    sidecar_datasets,
    sidecar_requested_at,
)
from .entity_evidence import write_entity_file
from .entity_map import EntityMap, EntityTable
from .models import JOIN_KEY_ENTITY_IDENTIFIER, SOURCE_PUBLISHED_VALUE, SOURCE_REPOSITORY_METADATA
from .sample_identity import DONOR, identifier_rules
from .schema.classification_model import EntityEvidenceRow, ImporterSourceTypeEnum, JoinKeyEnum
from .source_evidence import (
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    evidence_file_path,
    generation_dir,
    new_generation,
    staged_generation,
)

# How many unrecognised identifiers a check problem names as examples.
_EXAMPLES = 3


@dataclass
class TableImport:
    """What one table produced: rows read, lines written, donors named, and what wrote nothing.

    ``no_identifier`` counts rows whose identifier cell is not a non-empty string;
    ``null_cells`` is per column, null or empty-list cells on the other rows. For the
    published table, ``unmapped`` counts donors none of whose source rows (often none at
    all) is a mapped table's, ``unresolved``
    those whose source row is not in the manifest, and ``ambiguous`` those whose source rows
    name two identifiers.
    """

    table: str
    path: Path
    rows: int = 0
    written: int = 0
    donors: set[str] = field(default_factory=set)
    no_identifier: int = 0
    null_cells: Counter = field(default_factory=Counter)
    unmapped: int = 0
    unresolved: int = 0
    ambiguous: int = 0


@dataclass
class DatasetImport:
    """One dataset's import: the generation, and each file it wrote, submitter tables then published."""

    dataset: str
    generation: str
    tables: list[TableImport]


# --- checking the map against the manifests -----------------------------------


def check(entity_map: EntityMap, manifest_root: Path, catalog: str, datasets: list[str] | None = None) -> list[str]:
    """How the map disagrees with the manifests on disk, one line per problem; empty when none.

    Per mapped dataset (or those in ``datasets``, which must be in the map): its verbatim
    manifest is on disk. Per mapped table: it has rows; the identifier column and every slot
    column appear on some row; and at least half the identifier column's non-empty strings
    are recognised as donors by the identifier rules, or the column names something else.
    Per dataset with published donors: every table they were made from is mapped. Not
    that a published column holds a value: 1000 Genomes' donors carry no published sex.
    """
    named = sidecar_datasets(manifest_root, catalog)
    known = entity_map.datasets()
    problems = []
    for dataset in chosen_datasets(known, datasets):
        if dataset not in known:
            problems.append(f"{dataset}: not in the entity map")
            continue
        path = verbatim_manifest(manifest_root, catalog, dataset, named)
        if isinstance(path, str):
            problems.append(path)
            continue
        problems += _check_dataset(entity_map, dataset, path)
    return problems


def _check_dataset(entity_map: EntityMap, dataset: str, path: Path) -> list[str]:
    tables = {t.table: t for t in entity_map.tables_of(dataset)}
    published = entity_map.published
    rules = identifier_rules()
    rows: Counter = Counter()
    seen: dict[str, set[str]] = {name: set() for name in tables}
    recognised: Counter = Counter()
    unrecognised: dict[str, list[str]] = {name: [] for name in tables}
    sources: set[str] = set()
    for kind, row in iter_verbatim_entities(path, {*tables, published.table}):
        if kind == published.table:
            sources.update(_source_table(s) for s in row.get(published.source_rows) or [])
            continue
        rows[kind] += 1
        seen[kind].update(k for k, v in row.items() if v is not None and v != [])
        raw = row.get(tables[kind].identifier)
        if not isinstance(raw, str) or not raw:
            continue
        if rules.recognise(raw, dataset, DONOR) is not None:
            recognised[kind] += 1
        else:
            unrecognised[kind].append(raw)
    problems = []
    for name, table in tables.items():
        at = f"{dataset}/{name}"
        if not rows[name]:
            problems.append(f"{at}: no row of this type in the manifest")
            continue
        for column in (table.identifier, *(c for cs in table.slots.values() for c in cs)):
            if column not in seen[name]:
                problems.append(f"{at}: column {column!r} holds a value on no row")
        missed = unrecognised[name]
        if len(missed) > recognised[name]:
            problems.append(
                f"{at}: {len(missed):,} of {len(missed) + recognised[name]:,} values of {table.identifier!r} are not "
                f"a donor any identifier rule recognises (e.g. {missed[:_EXAMPLES]})"
            )
    for table in sorted(sources - set(tables)):
        problems.append(f"{dataset}/{published.table}: donors made from {table!r}, which the map does not name")
    return problems


def _source_table(source_row: object) -> str:
    """The table a ``<table>:<datarepo_row_id>`` source row names, or the whole value where it names none."""
    return str(source_row).partition(":")[0]


# --- importing ----------------------------------------------------------------


def import_all(
    entity_map: EntityMap,
    manifest_root: Path,
    catalog: str,
    service: str,
    entity_root: Path,
    datasets: list[str] | None = None,
    generation: str | None = None,
) -> list[DatasetImport]:
    """Import every dataset the map names (or ``datasets``), each as one new generation.

    The stamp is shared across the datasets of one run. Raises before writing anything if
    a named dataset is not in the map.
    """
    known = entity_map.datasets()
    chosen = chosen_datasets(known, datasets)
    unknown = [d for d in chosen if d not in known]
    if unknown:
        raise ValueError(f"not in the entity map: {unknown}")
    stamp = generation if generation is not None else new_generation()
    return [import_dataset(entity_map, manifest_root, catalog, service, d, entity_root, stamp) for d in chosen]


def import_dataset(
    entity_map: EntityMap,
    manifest_root: Path,
    catalog: str,
    service: str,
    dataset: str,
    entity_root: Path,
    generation: str | None = None,
) -> DatasetImport:
    """Write one generation of entity files for one dataset: the submitter tables', then the published table's.

    Each kind is its own generation directory (``anvil/`` and ``anvil_published/``), staged
    and renamed into place whole, as ``anvil_evidence.import_dataset`` stages its own. A
    mapped table that writes no line is the map disagreeing with the catalog and raises.
    The published table's file is written wherever the dataset has published donors, even
    with no line: 1000 Genomes' donors carry no published sex, and the empty file says so.
    ``fetched_at`` is the verbatim manifest's request time from the sidecar; ``service`` is
    the Azul service the manifests were pulled from, written as each file's source url.
    """
    stamp = generation if generation is not None else new_generation()
    path = manifest_path(manifest_root, catalog, dataset, FORMAT_VERBATIM)
    fetched_at = sidecar_requested_at(manifest_root, catalog, dataset, FORMAT_VERBATIM)
    if fetched_at is None:
        raise ValueError(
            f"{dataset}: the {catalog} sidecar records no {FORMAT_VERBATIM} requested_at to write as fetched_at"
        )
    target = EvidenceTarget(system=REPOSITORY, dataset=dataset, version=catalog)

    def envelope(source_type: str, table: str, source_key: str) -> EvidenceFileEnvelope:
        return EvidenceFileEnvelope(
            source=EvidenceFileSource(repository=REPOSITORY, dataset=dataset, table=table, url=service),
            source_type=ImporterSourceTypeEnum(source_type),
            source_version=catalog,
            source_key=source_key,
            target=target,
            target_key=JoinKeyEnum(JOIN_KEY_ENTITY_IDENTIFIER),
            fetched_at=fetched_at.isoformat(),
        )

    tables = entity_map.tables_of(dataset)
    results = []
    directory = generation_dir(entity_root, EVIDENCE_DIRS[SOURCE_REPOSITORY_METADATA], catalog, dataset, stamp)
    with staged_generation(directory) as staging:
        for table in tables:
            result = TableImport(table=table.table, path=evidence_file_path(directory, table.table))
            result.written = write_entity_file(
                evidence_file_path(staging, table.table),
                envelope(SOURCE_REPOSITORY_METADATA, table.table, table.identifier),
                _table_rows(path, table, result),
            )
            if not result.written:
                raise ValueError(f"{dataset}/{table.table}: no line written; the map disagrees with {catalog} here")
            results.append(result)

    published = entity_map.published
    identifiers = _source_identifiers(path, tables)
    result = TableImport(table=published.table, path=Path())
    lines = list(_published_rows(path, entity_map, tables, identifiers, result))
    if result.rows:
        directory = generation_dir(entity_root, EVIDENCE_DIRS[SOURCE_PUBLISHED_VALUE], catalog, dataset, stamp)
        result.path = evidence_file_path(directory, published.table)
        with staged_generation(directory) as staging:
            result.written = write_entity_file(
                evidence_file_path(staging, published.table),
                envelope(SOURCE_PUBLISHED_VALUE, published.table, published.source_rows),
                lines,
            )
        results.append(result)
    return DatasetImport(dataset=dataset, generation=stamp, tables=results)


def _cell(value: object) -> str | None:
    """A cell as written: a string verbatim, a null or empty list as None, anything else as ``json.dumps`` spells it."""
    if value is None or value == []:
        return None
    return value if isinstance(value, str) else json.dumps(value)


def _lines(
    row: dict, slots, identifier: str, identifier_column: str, result: TableImport, identifier_table: str | None = None
) -> Iterator[EntityEvidenceRow]:
    for slot, columns in slots.items():
        for column in columns:
            raw = _cell(row.get(column))
            if raw is None:
                result.null_cells[column] += 1
                continue
            result.donors.add(identifier)
            yield EntityEvidenceRow(
                field=slot,
                target_key_value=identifier,
                raw_value=raw,
                column=column,
                identifier_column=identifier_column,
                identifier_table=identifier_table,
            )


def _table_rows(path: Path, table: EntityTable, result: TableImport) -> Iterator[EntityEvidenceRow]:
    """Every line one mapped table yields, streamed row by row, counting into ``result``."""
    for _type, row in iter_verbatim_entities(path, {table.table}):
        result.rows += 1
        identifier = row.get(table.identifier)
        if not isinstance(identifier, str) or not identifier:
            result.no_identifier += 1
            continue
        yield from _lines(row, table.slots, identifier, table.identifier, result)


def _source_identifiers(path: Path, tables: list[EntityTable]) -> dict[tuple[str, str], str]:
    """Each mapped table's rows by ``(table, datarepo_row_id)``, to the identifier its row names."""
    by_name = {t.table: t for t in tables}
    out = {}
    for kind, row in iter_verbatim_entities(path, set(by_name)):
        identifier = row.get(by_name[kind].identifier)
        if isinstance(identifier, str) and identifier:
            out[(kind, str(row.get("datarepo_row_id")))] = identifier
    return out


def _published_rows(
    path: Path,
    entity_map: EntityMap,
    tables: list[EntityTable],
    identifiers: dict[tuple[str, str], str],
    result: TableImport,
) -> Iterator[EntityEvidenceRow]:
    """Every line the published donor table yields, each donor attached through its source rows in ``tables`` (``identifiers``)."""
    published = entity_map.published
    columns = {t.table: t.identifier for t in tables}
    for _type, row in iter_verbatim_entities(path, {published.table}):
        result.rows += 1
        found: set[tuple[str, str]] = set()
        reached = False
        for source_row in row.get(published.source_rows) or []:
            table, _, row_id = str(source_row).partition(":")
            if table not in columns:
                continue
            reached = True
            if (identifier := identifiers.get((table, row_id))) is not None:
                found.add((table, identifier))
        if not reached:
            result.unmapped += 1
            continue
        if not found:
            result.unresolved += 1
            continue
        if len({identifier for _, identifier in found}) > 1:
            result.ambiguous += 1
            continue
        table, identifier = min(found)
        yield from _lines(row, published.slots, identifier, columns[table], result, identifier_table=table)


# --- reporting -----------------------------------------------------------------


def describe(imports: list[DatasetImport]) -> list[str]:
    """One block per dataset: each file's counts."""
    lines = []
    for run in imports:
        lines.append(f"{run.dataset} ({run.generation})")
        for table in run.tables:
            lines.append(
                f"  {table.table}: {table.rows:,} rows, {table.written:,} lines, {len(table.donors):,} donors named"
            )
            if table.no_identifier:
                lines.append(f"    no identifier on {table.no_identifier:,} rows")
            for column, n in sorted(table.null_cells.items()):
                lines.append(f"    {column}: null on {n:,} rows")
            for label, n in (
                ("with no source row in a mapped table", table.unmapped),
                ("source row not in the manifest", table.unresolved),
                ("source rows naming two identifiers", table.ambiguous),
            ):
                if n:
                    lines.append(f"    {n:,} donors {label}")
    return lines
