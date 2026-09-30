"""The lineage map: which of a source's columns name a file and the parent it was made from (#583).

The slot map (`slot_map`) says where a raw value for one of a file's dimensions comes
from. This map says where a *link* comes from: which column names the child, which
names its parent, and, where the source names the step, which cell says what it is.
It is read by ``anvil_lineage``, which writes each link as a ``LineageRow``. Like the
slot map it holds no vocabulary and maps structure, never meaning.

**One generic entry shape**, a list of links per table, so a new dataset is new
entries and never new code::

    datasets:
      ANVIL_T2T:
        participant:
          - child: {column: samtools_stats}        # key defaults to drs_uri
            parent: {column: cram}
        anvil_activity:
          - child: {column: generated_file_id, key: file_id}
            parent: {column: used_file_id, key: file_id}
            raw_activity: {cell: activity_type}
            activity_id: {cell: activity_id}
      AnVIL_IGVF_Mouse_R1:
        file:
          - child: {column: file_path}
            parent: {column: derived_from, table: file, identifier_column: file_id, locator_column: file_path}

**What a column holds** is its ``key``: a locator (``drs_uri``, the default), AnVIL's
own identifier (``file_id``), or a sample's (``biosample_id``, a parent only). A parent
column holding the *source's* identifiers names instead the table where each is
defined: ``identifier_column`` is that table's column of them and ``locator_column``
its column of locators, so the importer writes the parent's locator and keeps the
identifier beside it.

**One table, one child key.** A table's lines go to one file, whose envelope names one
``target_key``, so every link of a table names its child the same way.

**The kind of source follows from the table.** ``anvil_activity`` is the repository's
own record of a step (``repository_activity``); any other ``anvil_*`` table is AnVIL's
harmonized data and has no lineage to map, and is refused; a submitter's table is
``repository_metadata``.

No ``notes`` member, for the slot map's reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

import yaml

from .azul_manifest import HARMONIZED_PREFIX, VERBATIM_ACTIVITY
from .models import (
    JOIN_KEY_DRS_URI,
    JOIN_KEY_FILE_ID,
    SOURCE_REPOSITORY_ACTIVITY,
    SOURCE_REPOSITORY_METADATA,
)
from .slot_map import NO_NOTES, NOTES, Readable, unique_key_loader

KEY_BIOSAMPLE_ID = "biosample_id"
# What a child column may hold: a file, by locator or by AnVIL's identifier. A parent
# may also be a sample.
CHILD_KEYS = (JOIN_KEY_DRS_URI, JOIN_KEY_FILE_ID)
PARENT_KEYS = (JOIN_KEY_DRS_URI, JOIN_KEY_FILE_ID, KEY_BIOSAMPLE_ID)

_WHERE = "lineage map"
_LINK_KEYS = frozenset({"child", "parent", "raw_activity", "activity_id"})
_LOOKUP_KEYS = frozenset({"table", "identifier_column", "locator_column"})


@dataclass(frozen=True)
class Lookup:
    """Where a source's own identifier is defined: ``table``'s ``identifier_column``, beside its ``locator_column``."""

    table: str
    identifier_column: str
    locator_column: str


@dataclass(frozen=True)
class Link:
    """One mapped link: the child's column and key, the parent's, and the step's cells.

    Exactly one of ``parent_key`` and ``lookup`` is set: a parent column holds either
    values of a key we know, or the source's identifiers to find in ``lookup``, whose
    result is a locator.
    """

    dataset: str
    table: str
    child_column: str
    child_key: str
    parent_column: str
    parent_key: str | None
    lookup: Lookup | None
    raw_activity_cell: str | None
    activity_id_cell: str | None


@dataclass(frozen=True)
class LineageMap:
    """A loaded map: the catalog it was authored against, and every link in it."""

    catalog: str
    links: tuple[Link, ...]

    def datasets(self) -> list[str]:
        """Dataset titles in file order, each once."""
        return list(dict.fromkeys(link.dataset for link in self.links))

    def tables(self, dataset: str) -> list[str]:
        return list(dict.fromkeys(link.table for link in self.links if link.dataset == dataset))

    def table_links(self, dataset: str, table: str) -> list[Link]:
        return [link for link in self.links if link.dataset == dataset and link.table == table]

    def dataset_links(self, dataset: str) -> list[Link]:
        return [link for link in self.links if link.dataset == dataset]


def source_type_of(table: str) -> str:
    """The kind of source a table's lines are: ``repository_activity`` for ``anvil_activity``, else ``repository_metadata``."""
    return SOURCE_REPOSITORY_ACTIVITY if table == VERBATIM_ACTIVITY else SOURCE_REPOSITORY_METADATA


def default_lineage_map_resource():
    """The bundled AnVIL lineage map, as a package-data resource."""
    return files(f"{__package__}.sources") / "anvil_lineage_map.yaml"


_UniqueKeyLoader = unique_key_loader(_WHERE)


def load_lineage_map(source: Readable | None = None) -> LineageMap:
    """Load and check a lineage map, the bundled one by default; ``ValueError`` naming where it is wrong.

    Checked here: the entry shape, the keys each side may hold, one child key per
    table, no ``notes``, no harmonized table but ``anvil_activity``. Whether the
    columns exist and hold what the map says is ``anvil_lineage.check``'s, against the
    manifests.
    """
    resource = source if source is not None else default_lineage_map_resource()
    document = yaml.load(resource.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    if not isinstance(document, dict):
        raise ValueError(f"{_WHERE}: the document is {type(document).__name__}, not a mapping")
    if NOTES in document:
        raise ValueError(f"{_WHERE}: {NO_NOTES}")
    if set(document) != {"catalog", "datasets"}:
        raise ValueError(f"{_WHERE}: top-level keys are {sorted(document)}, expected 'catalog' and 'datasets'")
    catalog = document["catalog"]
    if not isinstance(catalog, str) or not catalog:
        raise ValueError(f"{_WHERE}: catalog is {catalog!r}, not the name of the catalog the map was authored against")
    datasets = document["datasets"]
    _expect_mapping(datasets, _WHERE, "dataset")
    links = []
    for dataset, tables in datasets.items():
        _expect_mapping(tables, f"{_WHERE} {dataset}", "table")
        for table, entries in tables.items():
            at = f"{_WHERE} {dataset}/{table}"
            if table.startswith(HARMONIZED_PREFIX) and table != VERBATIM_ACTIVITY:
                raise ValueError(f"{at}: a harmonized table other than {VERBATIM_ACTIVITY!r} states no lineage")
            if not isinstance(entries, list) or not entries:
                raise ValueError(f"{at}: must be a non-empty list of links, not {type(entries).__name__}")
            table_links = [_link(dataset, table, entry, f"{at} link {i}") for i, entry in enumerate(entries, 1)]
            keys = {link.child_key for link in table_links}
            if len(keys) > 1:
                raise ValueError(f"{at}: children named by {sorted(keys)} — one table is one file, keyed one way")
            pairs = [(link.child_column, link.parent_column) for link in table_links]
            if len(set(pairs)) != len(pairs):
                raise ValueError(f"{at}: a (child, parent) column pair is listed twice")
            _refuse_two_readings(table_links, at)
            links += table_links
    return LineageMap(catalog=catalog, links=tuple(links))


def _refuse_two_readings(links: list[Link], at: str) -> None:
    """Refuse a column read two ways within one table: as a locator in one link and an identifier in another.

    The importer reads each column once per row, so a second reading would be silently
    ignored; and a column holds one kind of value, whichever link names it.
    """
    readings: dict[str, str] = {}
    for link in links:
        parent = "a source identifier" if link.lookup is not None else str(link.parent_key)
        for column, reading in ((link.child_column, link.child_key), (link.parent_column, parent)):
            if readings.setdefault(column, reading) != reading:
                raise ValueError(f"{at}: column {column!r} is read as {readings[column]} and as {reading}")


def _link(dataset: str, table: str, entry: object, at: str) -> Link:
    if not isinstance(entry, dict):
        raise ValueError(f"{at}: is {type(entry).__name__}, not a mapping")
    if NOTES in entry:
        raise ValueError(f"{at}: {NO_NOTES}")
    if not {"child", "parent"} <= set(entry) <= _LINK_KEYS:
        raise ValueError(
            f"{at}: keys are {sorted(entry)}, expected 'child' and 'parent', and optionally 'raw_activity', 'activity_id'"
        )
    child = entry["child"]
    _expect_keys(child, {"column"}, {"column", "key"}, f"{at} child")
    child_key = child.get("key", JOIN_KEY_DRS_URI)
    if child_key not in CHILD_KEYS:
        raise ValueError(f"{at} child: key {child_key!r} is not one of {CHILD_KEYS}")
    parent = entry["parent"]
    lookup = None
    parent_key = None
    if isinstance(parent, dict) and _LOOKUP_KEYS & set(parent):
        _expect_keys(parent, {"column"} | _LOOKUP_KEYS, {"column"} | _LOOKUP_KEYS, f"{at} parent")
        lookup = Lookup(
            table=_name(parent["table"], f"{at} parent table"),
            identifier_column=_name(parent["identifier_column"], f"{at} parent identifier_column"),
            locator_column=_name(parent["locator_column"], f"{at} parent locator_column"),
        )
    else:
        _expect_keys(parent, {"column"}, {"column", "key"}, f"{at} parent")
        parent_key = parent.get("key", JOIN_KEY_DRS_URI)
        if parent_key not in PARENT_KEYS:
            raise ValueError(f"{at} parent: key {parent_key!r} is not one of {PARENT_KEYS}")
    child_column = _name(child["column"], f"{at} child column")
    parent_column = _name(parent["column"], f"{at} parent column")
    if child_column == parent_column:
        raise ValueError(f"{at}: child and parent are both column {child_column!r}")
    return Link(
        dataset=dataset,
        table=table,
        child_column=child_column,
        child_key=child_key,
        parent_column=parent_column,
        parent_key=parent_key,
        lookup=lookup,
        raw_activity_cell=_cell(entry.get("raw_activity"), f"{at} raw_activity"),
        activity_id_cell=_cell(entry.get("activity_id"), f"{at} activity_id"),
    )


def _cell(value: object, at: str) -> str | None:
    if value is None:
        return None
    _expect_keys(value, {"cell"}, {"cell"}, at)
    assert isinstance(value, dict)
    return _name(value["cell"], f"{at} cell")


def _name(value: object, at: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{at}: is {value!r}, not a column or table name")
    return value


def _expect_keys(value: object, required: set, allowed: set, at: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{at}: is {value!r}, not a mapping")
    if NOTES in value:
        raise ValueError(f"{at}: {NO_NOTES}")
    if not required <= set(value) <= allowed:
        raise ValueError(f"{at}: keys are {sorted(value)}, expected {sorted(required)} (allowed {sorted(allowed)})")


def _expect_mapping(value: object, at: str, what: str) -> None:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{at}: must be a non-empty mapping of {what} names, not {type(value).__name__}")
