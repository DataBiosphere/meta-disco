"""Read AnVIL's donor facts and its own donor and biosample identifiers into entity evidence files, through the entity map (#693, #669).

The entity map (``entity_map``) says which submitter table's columns say what about a
donor, and which column names the donor or sample. This module checks the map against the
verbatim manifests on disk, then writes, per dataset, one generation of entity evidence
files: one file per mapped table reading a slot under ``<root>/anvil/``, and one per
published table (``anvil_donor``, ``anvil_biosample``) under ``<root>/anvil_published/``,
each line an ``EntityEvidenceRow``.

**A line is a cell, as written** (contract 1.1, 1.4): the identifier string the row names
the donor by, and the cell's value — a string verbatim, anything else as ``json.dumps``
spells it (1000 Genomes' ``pedigree.sex`` is the number ``1``). Neither is interpreted
here: the identifier rules recognise the identifier and, at reconcile, the value map
translates a sex or ancestry value, while a family value (``models.FAMILY_FIELDS``, #582) is
read there as written or as a parent's identifier. A null or empty-list cell, or a row whose identifier cell is not
a non-empty string, writes nothing and is counted.

**AnVIL's published donor and biosample** name no identifier of ours: each is attached to
one through the submitter row it was made from (``source_rows``), read in that row's table's
identifier column, and writes a line carrying AnVIL's own identifier for it
(``repository_id``, written as ``donor_repository_id`` or ``sample_repository_id``) beside
its slots' lines. A record whose source rows are in no mapped table, are not found, or name
two identifiers writes nothing and is counted.

Offline: it reads what ``make download`` left on disk.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .anvil_evidence import EVIDENCE_DIRS, chosen_datasets, verbatim_manifest
from .azul_manifest import (
    FORMAT_VERBATIM,
    REPOSITORY,
    cell_as_written,
    iter_verbatim_entities,
    manifest_path,
    sidecar_datasets,
    sidecar_requested_at,
)
from .entity_evidence import write_entity_file
from .entity_map import EntityMap, EntityTable, PublishedEntities
from .models import JOIN_KEY_ENTITY_IDENTIFIER, SOURCE_PUBLISHED_VALUE, SOURCE_REPOSITORY_METADATA
from .sample_identity import DONOR, REPOSITORY_ID_FIELD, EntityKind, identifier_rules
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
    """What one table produced: rows read, lines written, identifiers named, and what wrote nothing.

    ``path`` is None for a table reading no slot, which writes no file and is read only for its
    identifiers. ``named`` is the identifier strings the lines were written for. ``no_identifier`` counts
    rows whose identifier cell is not a non-empty string; ``null_cells`` is per column, null
    or empty-list cells on the other rows. For a published table, ``unmapped`` counts records
    none of whose source rows (often none at all) is a mapped table's, ``unresolved`` those
    whose mapped source rows name no identifier (not in the manifest, or an identifier cell
    that is not a non-empty string), and ``ambiguous`` those whose source rows name two
    identifiers.
    """

    table: str
    path: Path | None
    rows: int = 0
    written: int = 0
    named: set[str] = field(default_factory=set)
    no_identifier: int = 0
    null_cells: Counter = field(default_factory=Counter)
    unmapped: int = 0
    unresolved: int = 0
    ambiguous: int = 0


@dataclass
class DatasetImport:
    """One dataset's import: the generation, and each table it read in the map's order (a file written for
    each but those read for identifiers only), then each published file (donors, then samples)."""

    dataset: str
    generation: str
    tables: list[TableImport]


@dataclass
class LeftOut:
    """A dataset the catalog's sidecar names and the map does not: how many records of each published table it holds."""

    dataset: str
    records: dict[str, int]


# --- checking the map against the manifests -----------------------------------


def check(entity_map: EntityMap, manifest_root: Path, catalog: str, datasets: list[str] | None = None) -> list[str]:
    """How the map disagrees with the manifests on disk, one line per problem; empty when none.

    Per mapped dataset (or those in ``datasets``, which must be in the map): its verbatim
    manifest is on disk. Per mapped table: it has rows; the identifier column and every slot
    column appear on some row; it serves a kind, a donor where it reads a slot or a published
    donor is made from its rows, a sample where a published sample is; and for each kind it
    serves, at least half the identifier column's non-empty strings are recognised as that
    kind by the identifier rules, or the column names something else. Per published table
    with rows: its source rows and repository identifier columns appear on some row, and
    every table its records were made from is mapped. Not that a published slot column holds
    a value: 1000 Genomes' donors carry no published sex.
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
    published = {p.table: p for p in entity_map.published}
    rules = identifier_rules()
    rows: Counter = Counter()
    seen: dict[str, set[str]] = {name: set() for name in tables}
    identifiers: dict[str, list[str]] = {name: [] for name in tables}
    sources: dict[str, set[str]] = {name: set() for name in published}
    published_seen: dict[str, set[str]] = {name: set() for name in published}
    for entity_type, row in iter_verbatim_entities(path, {*tables, *published}):
        if entity_type in published:
            rows[entity_type] += 1
            published_seen[entity_type].update(k for k, v in row.items() if v is not None and v != [])
            source_rows = row.get(published[entity_type].source_rows) or []
            sources[entity_type].update(table for table, _ in map(_source_row, source_rows))
            continue
        rows[entity_type] += 1
        seen[entity_type].update(k for k, v in row.items() if v is not None and v != [])
        raw = row.get(tables[entity_type].identifier)
        if isinstance(raw, str) and raw:
            identifiers[entity_type].append(raw)
    problems = []
    for name, table in tables.items():
        at = f"{dataset}/{name}"
        if not rows[name]:
            problems.append(f"{at}: no row of this type in the manifest")
            continue
        for column in (table.identifier, *(c for cs in table.slots.values() for c in cs)):
            if column not in seen[name]:
                problems.append(f"{at}: column {column!r} holds a value on no row")
        kinds = _kinds_served(table, entity_map.published, sources)
        if not kinds:
            problems.append(f"{at}: reads no slot, and no published table's records are made from its rows")
        for kind in kinds:
            missed = [raw for raw in identifiers[name] if rules.recognise(raw, dataset, kind) is None]
            if 2 * len(missed) > len(identifiers[name]):
                problems.append(
                    f"{at}: {len(missed):,} of {len(identifiers[name]):,} values of {table.identifier!r} are not "
                    f"a {kind} any identifier rule recognises (e.g. {missed[:_EXAMPLES]})"
                )
    for entity in entity_map.published:
        if rows[entity.table]:
            for column in (entity.source_rows, entity.repository_id):
                if column not in published_seen[entity.table]:
                    problems.append(f"{dataset}/{entity.table}: column {column!r} holds a value on no row")
        for table in sorted(sources[entity.table] - set(tables)):
            problems.append(
                f"{dataset}/{entity.table}: {entity.kind}s made from {table!r}, which the map does not name"
            )
    return problems


def _kinds_served(
    table: EntityTable, published: tuple[PublishedEntities, ...], sources: dict[str, set[str]]
) -> list[EntityKind]:
    """What ``table``'s identifier names: a donor where it reads a slot, and each kind a published table makes records of from its rows."""
    kinds: list[EntityKind] = [DONOR] if table.slots else []
    for entity in published:
        if table.table in sources[entity.table] and entity.kind not in kinds:
            kinds.append(entity.kind)
    return kinds


def _source_row(value: object) -> tuple[str, str]:
    """A ``<table>:<datarepo_row_id>`` source row as its table and row id; the row id is empty where it names none."""
    table, _, row_id = str(value).partition(":")
    return table, row_id


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
    """Write one generation of entity files for one dataset: the submitter tables', then each published table's.

    Each kind is its own generation directory (``anvil/`` and ``anvil_published/``), staged
    together and renamed into place only once both are written: a failure while writing
    either removes both. The two renames are separate, so a crash between them can still
    leave the new published generation beside the older submitter one. A mapped table
    reading a slot that writes no line is the map disagreeing with the catalog and raises; a
    table reading none writes no file, and is read only for its identifiers. Each published
    table's file is written for every dataset, with no line where the dataset has no
    published record of that kind tied to an identifier, so a re-import supersedes both kinds
    and never leaves an older published generation current.
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
    # Each mapped row's identifier by (table, datarepo_row_id), gathered as the tables stream, for
    # the published records' source rows.
    identifiers: dict[tuple[str, str], str] = {}
    results = []
    directory = generation_dir(entity_root, EVIDENCE_DIRS[SOURCE_REPOSITORY_METADATA], catalog, dataset, stamp)
    published_dir = generation_dir(entity_root, EVIDENCE_DIRS[SOURCE_PUBLISHED_VALUE], catalog, dataset, stamp)
    # Both kinds staged together: a failure in either removes both, so a submitter generation
    # never becomes current beside an older published one.
    with staged_generation(directory) as staging, staged_generation(published_dir) as published_staging:
        for table in tables:
            if not table.slots:
                result = TableImport(table=table.table, path=None)
                _index_identifiers(path, table, result, identifiers)
                results.append(result)
                continue
            result = TableImport(table=table.table, path=evidence_file_path(directory, table.table))
            result.written = write_entity_file(
                evidence_file_path(staging, table.table),
                envelope(SOURCE_REPOSITORY_METADATA, table.table, table.identifier),
                _table_rows(path, table, result, identifiers),
            )
            if not result.written:
                raise ValueError(f"{dataset}/{table.table}: no line written; the map disagrees with {catalog} here")
            results.append(result)
        for published in entity_map.published:
            result = TableImport(table=published.table, path=evidence_file_path(published_dir, published.table))
            result.written = write_entity_file(
                evidence_file_path(published_staging, published.table),
                envelope(SOURCE_PUBLISHED_VALUE, published.table, published.source_rows),
                _published_rows(path, published, tables, identifiers, result),
            )
            results.append(result)
    return DatasetImport(dataset=dataset, generation=stamp, tables=results)


def _lines(
    row: dict, slots, identifier: str, identifier_column: str, result: TableImport, identifier_table: str | None = None
) -> Iterator[EntityEvidenceRow]:
    for slot, columns in slots.items():
        for column in columns:
            raw = cell_as_written(row.get(column))
            if raw is None:
                result.null_cells[column] += 1
                continue
            result.named.add(identifier)
            yield EntityEvidenceRow(
                field=slot,
                target_key_value=identifier,
                raw_value=raw,
                column=column,
                identifier_column=identifier_column,
                identifier_table=identifier_table,
            )


def _identify(
    row: dict, table: EntityTable, result: TableImport, identifiers: dict[tuple[str, str], str]
) -> str | None:
    """Count ``row`` into ``result``, and keep its identifier in ``identifiers`` and return it; None where its cell names none."""
    result.rows += 1
    identifier = row.get(table.identifier)
    if not isinstance(identifier, str) or not identifier:
        result.no_identifier += 1
        return None
    identifiers[(table.table, str(row.get("datarepo_row_id")))] = identifier
    return identifier


def _table_rows(
    path: Path, table: EntityTable, result: TableImport, identifiers: dict[tuple[str, str], str]
) -> Iterator[EntityEvidenceRow]:
    """Every line one mapped table yields, streamed row by row, counting into ``result`` and keeping each row's identifier in ``identifiers``."""
    for _type, row in iter_verbatim_entities(path, {table.table}):
        if (identifier := _identify(row, table, result, identifiers)) is not None:
            yield from _lines(row, table.slots, identifier, table.identifier, result)


def _index_identifiers(
    path: Path, table: EntityTable, result: TableImport, identifiers: dict[tuple[str, str], str]
) -> None:
    """Read a table reading no slot for its rows' identifiers alone, into ``identifiers``, counting into ``result``."""
    for _type, row in iter_verbatim_entities(path, {table.table}):
        _identify(row, table, result, identifiers)


def _published_rows(
    path: Path,
    published: PublishedEntities,
    tables: list[EntityTable],
    identifiers: dict[tuple[str, str], str],
    result: TableImport,
) -> Iterator[EntityEvidenceRow]:
    """Every line one published table yields, each record attached through its source rows in ``tables`` (``identifiers``):
    its repository identifier's line, then its slots'."""
    columns = {t.table: t.identifier for t in tables}
    fields = {REPOSITORY_ID_FIELD[published.kind]: (published.repository_id,), **published.slots}
    for _type, row in iter_verbatim_entities(path, {published.table}):
        result.rows += 1
        found: set[tuple[str, str]] = set()
        reached = False
        for table, row_id in map(_source_row, row.get(published.source_rows) or []):
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
        yield from _lines(row, fields, identifier, columns[table], result, identifier_table=table)


def left_out(entity_map: EntityMap, manifest_root: Path, catalog: str) -> list[LeftOut]:
    """Each dataset the catalog's sidecar names and the map does not, with how many records of each published table it holds.

    Their records tie to nothing, since no table of theirs is mapped; this says how many. A
    dataset whose verbatim manifest is not on disk is listed with no counts.
    """
    named = sidecar_datasets(manifest_root, catalog)
    mapped = set(entity_map.datasets())
    tables = [p.table for p in entity_map.published]
    out = []
    for dataset in sorted(set(named) - mapped):
        path = verbatim_manifest(manifest_root, catalog, dataset, named)
        if isinstance(path, str):
            out.append(LeftOut(dataset=dataset, records={}))
            continue
        records = Counter(entity_type for entity_type, _ in iter_verbatim_entities(path, set(tables)))
        out.append(LeftOut(dataset=dataset, records={t: records[t] for t in tables}))
    return out


# --- reporting -----------------------------------------------------------------


def describe(imports: list[DatasetImport]) -> list[str]:
    """One block per dataset: each file's counts, and each table read for identifiers only."""
    lines = []
    for run in imports:
        lines.append(f"{run.dataset} ({run.generation})")
        for table in run.tables:
            if table.path is None:
                lines.append(f"  {table.table}: {table.rows:,} rows, read for identifiers only")
            else:
                lines.append(
                    f"  {table.table}: {table.rows:,} rows, {table.written:,} lines, "
                    f"{len(table.named):,} identifiers named"
                )
            if table.no_identifier:
                lines.append(f"    no identifier on {table.no_identifier:,} rows")
            for column, n in sorted(table.null_cells.items()):
                lines.append(f"    {column}: null on {n:,} rows")
            for label, n in (
                ("with no source row in a mapped table", table.unmapped),
                ("whose source rows name no identifier", table.unresolved),
                ("whose source rows name two identifiers", table.ambiguous),
            ):
                if n:
                    lines.append(f"    {n:,} records {label}")
    return lines


def describe_left_out(left: list[LeftOut]) -> list[str]:
    """One line per dataset :func:`left_out` found holding a published record, or not on disk, with its records' counts."""
    lines = []
    for dataset in left:
        if dataset.records and not any(dataset.records.values()):
            continue  # no published record to tie
        counts = ", ".join(f"{n:,} {table}" for table, n in dataset.records.items())
        lines.append(
            f"{dataset.dataset}: not in the entity map, so none of its records tie ({counts or 'not on disk'})"
        )
    return lines
