"""Read AnVIL's tables into lineage evidence files, through a lineage map (#583).

The lineage map (`lineage_map`) says which columns name a file and the parent it was
made from; this module checks the map against the verbatim manifests, then writes,
per dataset, one generation of lineage files (`lineage_evidence`) with one file per
mapped table. It is an importer in the contract's sense (1.2, 1.3): it transcribes
which file a source says was made from which, and what the source calls the step,
and translates nothing.

**Every parent is written; a child must be ours.** A line is about its child, so a
child that is not among the dataset's own files (its ``anvil_file`` DRS URIs, or its
``file_id``s) is dropped and counted, as ``anvil_evidence`` drops a link outside the
dataset. A parent is written whether or not it is one of the dataset's files — finding
it is reconcile's (#577), which will report one it cannot find, and dropping it here would
hide it. The count of such parents is reported, not acted on.

**One lookup, the map's.** Where a parent column holds the source's own identifiers,
the map names the table they are defined in (``lineage_map.Lookup``), and the importer
reads that table once to find each identifier's locator. It writes the locator as the
parent and keeps the identifier as ``parent_source_identifier``; an identifier with no
row, or with rows naming two or more locators, is written with the identifier alone and
counted. Nothing is looked up in our catalog or our classifications.

**One line per (child, parent) pair**: a cell holding a list is spread, so an
``anvil_activity`` row that generated four files from one is four lines.

**An import is a generation**, written to a staging directory and renamed into place
once every table is written, under ``lineage_evidence.DEFAULT_LINEAGE_EVIDENCE_ROOT``
in the slot root's layout: ``anvil/<catalog>/<dataset>/<generation>/<table>.ndjson``.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .anvil_evidence import chosen_datasets, verbatim_manifest
from .azul_manifest import (
    ANVIL_FILE_HANDLE_COLUMNS,
    FORMAT_VERBATIM,
    REPOSITORY,
    VERBATIM_FILE,
    iter_verbatim_entities,
    link_handles,
    manifest_path,
    sidecar_datasets,
    sidecar_requested_at,
)
from .lineage_evidence import write_lineage_file
from .lineage_map import LineageMap, Link, Lookup, source_type_of
from .models import JOIN_KEY_DRS_URI, JOIN_KEY_FILE_ID
from .schema.classification_model import (
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    ImporterSourceTypeEnum,
    JoinKeyEnum,
    LineageParentKeyEnum,
    LineageRow,
)
from .source_evidence import evidence_file_path, generation_dir, new_generation, staged_generation


@dataclass(frozen=True)
class DatasetFiles:
    """The dataset's own files, as its ``anvil_file`` entities name them."""

    drs_uris: frozenset[str]
    file_ids: frozenset[str]

    def has(self, key: str, value: str) -> bool:
        """Whether ``value``, a ``key`` (``drs_uri`` or ``file_id``), is one of these files; any other key raises."""
        if key == JOIN_KEY_DRS_URI:
            return value in self.drs_uris
        if key == JOIN_KEY_FILE_ID:
            return value in self.file_ids
        raise ValueError(f"{key!r} names no file of the dataset")


@dataclass
class TableLineage:
    """What one mapped table produced, and what it could not; each counter is keyed by column.

    ``no_value`` counts rows whose cell held nothing; ``not_value`` rows whose cell held
    something that is not the key the map says (a non-DRS value in a locator column, a
    non-string in an identifier column). The rest count values, each once per row:
    ``child_outside`` children not among the dataset's files, dropped; ``parent_outside``
    parents not among them, written; ``identifier_missing`` / ``identifier_several``
    source identifiers the lookup table has no row for, or rows with two locators for,
    written with the identifier alone.
    ``children`` is the distinct children that received a line.
    """

    table: str
    path: Path
    rows: int = 0
    written: int = 0
    children: set[str] = field(default_factory=set)
    no_value: Counter = field(default_factory=Counter)
    not_value: Counter = field(default_factory=Counter)
    child_outside: Counter = field(default_factory=Counter)
    parent_outside: Counter = field(default_factory=Counter)
    identifier_missing: Counter = field(default_factory=Counter)
    identifier_several: Counter = field(default_factory=Counter)


@dataclass
class DatasetLineage:
    """One generation of one dataset: where it went and what each table produced."""

    dataset: str
    generation: str
    directory: Path
    tables: list[TableLineage]


# --- reading a cell ------------------------------------------------------------


def cell_values(value: Any, locator: bool) -> list[str] | None:
    """The values one cell holds: None when it holds nothing, ``[]`` when it holds something else.

    A ``locator`` cell holds a ``drs://`` URI or a list of them, per
    ``azul_manifest.link_handles``; any other holds identifiers, a non-empty string or a
    list of them. Null, the empty string and the empty list hold nothing.
    """
    if locator:
        return link_handles(value)
    if value is None or value == "" or value == []:
        return None
    items = value if isinstance(value, list) else [value]
    return list(items) if all(isinstance(i, str) and i for i in items) else []


def _raw(value: Any) -> str | None:
    """A step cell as a line records it: a string verbatim, the empty string included; null
    and the empty list omitted, as the slot importer omits them (``anvil_evidence._transcribe``),
    since neither observes anything; anything else as its JSON."""
    if value is None or value == []:
        return None
    return value if isinstance(value, str) else json.dumps(value)


def _identifier(value: Any) -> str | None:
    """A step's id as a line records it: ``_raw``'s, but the empty string is no id and is omitted."""
    raw = _raw(value)
    return raw or None


# --- checking the map against the manifests -------------------------------------


def check(lineage_map: LineageMap, manifest_root: Path, catalog: str, datasets: list[str] | None = None) -> list[str]:
    """How the map disagrees with the manifests on disk, one line per problem; empty when none.

    Per chosen dataset (which must be in the map): the sidecar names it and its
    verbatim manifest is on disk. Per mapped table and lookup table: it has rows, and
    every column the map names appears on some row. Per column, by what the map says
    it holds: a locator column's every non-empty value is a DRS URI or a list of them;
    an identifier column's every non-empty value is a string or a list of them; a
    child ``file_id`` column holds at least one of the dataset's own ``file_id``s, so a
    column of some other identifier is caught (a parent column is not held to that,
    since a parent outside the dataset is written). Every chosen dataset is checked and
    every problem returned, so a map edited in one sitting is answered in one run.
    """
    named = sidecar_datasets(manifest_root, catalog)
    known = lineage_map.datasets()
    problems: list[str] = []
    for dataset in chosen_datasets(known, datasets):
        if dataset not in known:
            problems.append(f"{dataset}: not in the lineage map")
            continue
        path = verbatim_manifest(manifest_root, catalog, dataset, named)
        if isinstance(path, str):
            problems.append(path)
            continue
        problems += _check_dataset(lineage_map.dataset_links(dataset), dataset, path)
    return problems


# What the map says a column holds, for the check: a locator, an identifier, or a
# step's cell (whose value is transcribed whatever it is, so it is checked for presence only).
_LOCATOR, _IDENTIFIER, _CELL = "locator", "identifier", "cell"


def _check_dataset(links: list[Link], dataset: str, path: Path) -> list[str]:
    """``check``'s per-dataset half, in one pass over the manifest (``anvil_file`` rows included)."""
    wanted: dict[str, dict[str, str]] = defaultdict(dict)
    for link in links:
        wanted[link.table][link.child_column] = _LOCATOR if link.child_key == JOIN_KEY_DRS_URI else _IDENTIFIER
        wanted[link.table][link.parent_column] = _LOCATOR if link.parent_key_type == JOIN_KEY_DRS_URI else _IDENTIFIER
        for cell in (link.raw_activity_cell, link.activity_id_cell):
            if cell is not None:
                wanted[link.table][cell] = _CELL
        if link.lookup is not None:
            wanted[link.lookup.table][link.lookup.identifier_column] = _IDENTIFIER
            wanted[link.lookup.table][link.lookup.locator_column] = _LOCATOR
    child_file_ids = {(link.table, link.child_column) for link in links if link.child_key == JOIN_KEY_FILE_ID}
    file_ids: set[str] = set()
    child_values: dict[tuple[str, str], set[str]] = defaultdict(set)
    rows: Counter = Counter()
    seen: dict[str, set[str]] = defaultdict(set)
    wrong: dict[tuple[str, str], Any] = {}
    for table, row in iter_verbatim_entities(path, {*wanted, VERBATIM_FILE}):
        if table == VERBATIM_FILE:
            if isinstance(row.get("file_id"), str):
                file_ids.add(row["file_id"])
            if table not in wanted:
                continue
        rows[table] += 1
        seen[table].update(row)
        for column, holds in wanted[table].items():
            if holds == _CELL or (table, column) in wrong:
                continue
            values = cell_values(row.get(column), holds == _LOCATOR)
            if values == []:
                wrong[(table, column)] = row[column]
            elif values and (table, column) in child_file_ids:
                child_values[(table, column)].update(values)
    problems = []
    for table in sorted(wanted):
        if not rows[table]:
            problems.append(f"{dataset}/{table}: no row of this type in the manifest")
            continue
        for column, holds in sorted(wanted[table].items()):
            if column not in seen[table]:
                problems.append(f"{dataset}/{table}/{column}: no row carries this column")
            elif (table, column) in wrong:
                kind = "a DRS URI or a list of them" if holds == _LOCATOR else "a string or a list of them"
                problems.append(f"{dataset}/{table}/{column}: holds {wrong[(table, column)]!r}, not {kind}")
            elif (table, column) in child_file_ids and not child_values[(table, column)] & file_ids:
                problems.append(f"{dataset}/{table}/{column}: holds no file_id of this dataset's anvil_file rows")
    return problems


def dataset_files(path: Path) -> DatasetFiles:
    """The dataset's own files, as its ``anvil_file`` entities name them: DRS URIs and ``file_id``s."""
    drs_uris: set[str] = set()
    file_ids: set[str] = set()
    for _table, value in iter_verbatim_entities(path, {VERBATIM_FILE}):
        for column in ANVIL_FILE_HANDLE_COLUMNS:
            drs_uris.update(link_handles(value.get(column)) or [])
        if isinstance(value.get("file_id"), str):
            file_ids.add(value["file_id"])
    return DatasetFiles(frozenset(drs_uris), frozenset(file_ids))


def lookup_locators(path: Path, lookup: Lookup) -> dict[str, set[str]]:
    """Each source identifier in ``lookup.table``'s ``identifier_column``, to the locators its rows give it."""
    found: dict[str, set[str]] = {}
    for _table, row in iter_verbatim_entities(path, {lookup.table}):
        locators = link_handles(row.get(lookup.locator_column))
        if not locators:
            continue
        for identifier in cell_values(row.get(lookup.identifier_column), locator=False) or []:
            found.setdefault(identifier, set()).update(locators)
    return found


# --- importing -----------------------------------------------------------------


def import_all(
    lineage_map: LineageMap,
    manifest_root: Path,
    catalog: str,
    service: str,
    lineage_root: Path,
    datasets: list[str] | None = None,
    generation: str | None = None,
) -> list[DatasetLineage]:
    """Import every dataset the map names (or ``datasets``), each as one new generation under one shared stamp.

    Raises before writing anything if a named dataset is not in the map.
    """
    known = lineage_map.datasets()
    chosen = chosen_datasets(known, datasets)
    unknown = [d for d in chosen if d not in known]
    if unknown:
        raise ValueError(f"not in the lineage map: {unknown}")
    stamp = generation if generation is not None else new_generation()
    return [
        import_dataset(lineage_map, manifest_root, catalog, service, dataset, lineage_root, stamp) for dataset in chosen
    ]


def import_dataset(
    lineage_map: LineageMap,
    manifest_root: Path,
    catalog: str,
    service: str,
    dataset: str,
    lineage_root: Path,
    generation: str | None = None,
) -> DatasetLineage:
    """Write one generation of lineage files for one dataset, one file per mapped table.

    The generation directory must not exist, and is written to a staging directory
    renamed into place at the end, so a generation exists whole or not at all (as
    ``anvil_evidence.import_dataset``). A mapped table that writes no line is a
    failure: the map disagrees with the catalog there. The envelope's source ``url`` is
    ``service``, the Azul service the manifests were pulled from, and its
    ``fetched_at`` the verbatim manifest's request time from the sidecar.
    """
    if not lineage_map.tables(dataset):
        raise ValueError(f"{dataset}: not in the lineage map")
    stamp = generation if generation is not None else new_generation()
    directory = generation_dir(lineage_root, REPOSITORY, catalog, dataset, stamp)
    path = manifest_path(manifest_root, catalog, dataset, FORMAT_VERBATIM)
    fetched_at = sidecar_requested_at(manifest_root, catalog, dataset, FORMAT_VERBATIM)
    if fetched_at is None:
        raise ValueError(f"{dataset}: the {catalog} sidecar records no {FORMAT_VERBATIM} requested_at")
    files = dataset_files(path)
    lookups = {
        lookup: lookup_locators(path, lookup)
        for lookup in {link.lookup for link in lineage_map.dataset_links(dataset) if link.lookup is not None}
    }
    target = EvidenceTarget(system=REPOSITORY, dataset=dataset, version=catalog)
    tables = []
    with staged_generation(directory) as staging:
        for table in lineage_map.tables(dataset):
            links = lineage_map.table_links(dataset, table)
            child_key = links[0].child_key
            envelope = EvidenceFileEnvelope(
                source=EvidenceFileSource(repository=REPOSITORY, dataset=dataset, table=table, url=service),
                source_type=ImporterSourceTypeEnum(source_type_of(table)),
                source_version=catalog,
                source_key=child_key,
                target=target,
                target_key=JoinKeyEnum(child_key),
                fetched_at=fetched_at.isoformat(),
            )
            result = TableLineage(table=table, path=evidence_file_path(directory, table))
            rows = _table_rows(path, table, links, files, lookups, result)
            result.written = write_lineage_file(evidence_file_path(staging, table), envelope, rows)
            if not result.written:
                raise ValueError(
                    f"{dataset}/{table}: no lineage line written — every child was empty or outside the dataset's "
                    f"files, or no row named a parent; the map disagrees with {catalog} here"
                )
            tables.append(result)
    return DatasetLineage(dataset=dataset, generation=stamp, directory=directory, tables=tables)


def _table_rows(
    path: Path,
    table: str,
    links: list[Link],
    files: DatasetFiles,
    lookups: dict[Lookup, dict[str, set[str]]],
    result: TableLineage,
) -> Iterator[LineageRow]:
    """Every lineage line one table yields, streamed row by row, counting into ``result``."""
    for _type, row in iter_verbatim_entities(path, {table}):
        result.rows += 1
        # Each column read once per row, and counted once per row however many links name it.
        read: dict[str, list[str]] = {}
        # (counter, column, value) already counted on this row: a value is counted once per
        # row however many lines it reaches.
        counted: set[tuple[str, str, str]] = set()
        for link in links:
            children = _values(row, link.child_column, link.child_key == JOIN_KEY_DRS_URI, read, result)
            parents = _values(row, link.parent_column, link.parent_key_type == JOIN_KEY_DRS_URI, read, result)
            if not children or not parents:
                continue
            raw_activity = None if link.raw_activity_cell is None else _raw(row.get(link.raw_activity_cell))
            activity_id = None if link.activity_id_cell is None else _identifier(row.get(link.activity_id_cell))
            for child in children:
                if not files.has(link.child_key, child):
                    _count(result, "child_outside", link.child_column, child, counted)
                    continue
                for parent in parents:
                    result.children.add(child)
                    yield _row(link, child, parent, raw_activity, activity_id, files, lookups, result, counted)


def _count(result: TableLineage, counter: str, column: str, value: str, counted: set[tuple[str, str, str]]) -> None:
    """Count ``value`` under ``column`` in ``result``'s ``counter``, once per row (``counted`` is the row's own)."""
    key = (counter, column, value)
    if key not in counted:
        counted.add(key)
        getattr(result, counter)[column] += 1


def _values(row: dict, column: str, locator: bool, read: dict[str, list[str]], result: TableLineage) -> list[str]:
    """``column``'s values (``cell_values``), counting an empty or wrong cell once per row."""
    if column not in read:
        values = cell_values(row.get(column), locator)
        if values is None:
            result.no_value[column] += 1
        elif not values:
            result.not_value[column] += 1
        read[column] = values or []
    return read[column]


def _row(
    link: Link,
    child: str,
    parent: str,
    raw_activity: str | None,
    activity_id: str | None,
    files: DatasetFiles,
    lookups: dict[Lookup, dict[str, set[str]]],
    result: TableLineage,
    counted: set[tuple[str, str, str]],
) -> LineageRow:
    """One line: the parent as the map says the column holds it, found through the lookup where it names one."""
    source_identifier = None
    parent_key: str | None = link.parent_key_type
    if link.lookup is not None:
        source_identifier = parent
        locators = lookups[link.lookup].get(parent, set())
        if len(locators) == 1:
            (parent,) = locators
            parent_key = JOIN_KEY_DRS_URI
        else:
            counter = "identifier_missing" if not locators else "identifier_several"
            _count(result, counter, link.parent_column, parent, counted)
            parent_key = None
    if parent_key in (JOIN_KEY_DRS_URI, JOIN_KEY_FILE_ID) and not files.has(parent_key, parent):
        _count(result, "parent_outside", link.parent_column, parent, counted)
    return LineageRow(
        target_key_value=child,
        parent=parent if parent_key is not None else None,
        parent_key_type=LineageParentKeyEnum(parent_key) if parent_key is not None else None,
        parent_source_identifier=source_identifier,
        raw_activity=raw_activity,
        activity_id=activity_id,
        child_column=link.child_column,
        parent_column=link.parent_column,
        raw_activity_column=link.raw_activity_cell if raw_activity is not None else None,
    )


# --- reporting -----------------------------------------------------------------


def describe(imports: list[DatasetLineage]) -> list[str]:
    """One block per dataset: the generation, then each table's counts."""
    lines = []
    for run in imports:
        lines.append(f"{run.dataset} -> {run.directory}")
        for table in run.tables:
            lines.append(
                f"  {table.table}: {table.rows:,} rows, {table.written:,} lines, {len(table.children):,} children"
            )
            for label, counter in (
                ("empty", table.no_value),
                ("not the key the map says", table.not_value),
                ("children outside the dataset, dropped", table.child_outside),
                ("parents outside the dataset, written", table.parent_outside),
                ("source identifiers with no row", table.identifier_missing),
                ("source identifiers with several locators", table.identifier_several),
            ):
                for column, n in sorted(counter.items()):
                    lines.append(f"    {column}: {label} on {n:,}")
    return lines
