"""The entity map: which of a source's tables say what about a donor, and name which donor or sample (#693, #669).

The slot map keys a raw value for a *file's* dimension by a file-link column; this map keys a
raw value for a *donor's* slot (``models.DONOR_FIELDS``, and on a submitter table the family's,
``models.FAMILY_FIELDS``, #582) by the column naming the donor, since
rows such as 1000 Genomes' ``pedigree`` have no file-link column. ``anvil_entities`` reads it.
It maps structure, never meaning; the shape is ``sources/anvil_entity_map.yaml``'s.

Per table: ``identifier`` and per slot its columns. A table reading no slot names only its
identifier column, for the repository's records made from its rows to tie to; whether it
serves one is ``anvil_entities.check``'s to say, against the manifests. A harmonized
``anvil_*`` table is refused there. ``published``: per kind (``donor``, ``sample``), the
repository's own table of that kind, read in every dataset the map names: its column of
source rows (``<table>:<datarepo_row_id>``), through which each record is attached to an
identifier in that table's ``identifier`` column; its column holding the repository's own
identifier for the record (``repository_id``, #669); and, for donors, each slot's columns.
No ``notes`` member, for the slot map's reason.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files

from .azul_manifest import HARMONIZED_PREFIX
from .lineage_map import expect_keys, expect_mapping, expect_name, map_document
from .models import DONOR_FIELDS, FAMILY_FIELDS
from .sample_identity import DONOR, REPOSITORY_ID_FIELD, SAMPLE, EntityKind
from .slot_map import Readable, unique_key_loader

_WHERE = "entity map"
IDENTIFIER = "identifier"
_PUBLISHED_KEYS = frozenset({"table", "source_rows", "repository_id"})
# The slots a submitter table may read: a donor's, and its family's.
_TABLE_SLOTS = (*DONOR_FIELDS, *FAMILY_FIELDS)
# The slots a published record of each kind may read: a donor's, but not its family, which AnVIL's
# model has no field for; a sample has none yet.
_PUBLISHED_SLOTS: dict[EntityKind, tuple[str, ...]] = {DONOR: DONOR_FIELDS, SAMPLE: ()}

_UniqueKeyLoader = unique_key_loader(_WHERE)


@dataclass(frozen=True)
class EntityTable:
    """One mapped table of one dataset: the column naming its donor or sample, and each slot's columns, none or more."""

    dataset: str
    table: str
    identifier: str
    slots: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class PublishedEntities:
    """The repository's table of one kind of record: its name, its column of source rows, its own identifier's column, and each slot's columns."""

    kind: EntityKind
    table: str
    source_rows: str
    repository_id: str
    slots: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class EntityMap:
    """A loaded entity map: the catalog it was authored against, its tables, and the published tables, donors first."""

    catalog: str
    tables: tuple[EntityTable, ...]
    published: tuple[PublishedEntities, ...]

    def datasets(self) -> list[str]:
        """The datasets the map names, in the map's order."""
        return list(dict.fromkeys(t.dataset for t in self.tables))

    def tables_of(self, dataset: str) -> list[EntityTable]:
        """The dataset's mapped tables, in the map's order."""
        return [t for t in self.tables if t.dataset == dataset]


def default_entity_map_resource():
    """The bundled AnVIL entity map, as a package-data resource."""
    return files(f"{__package__}.sources") / "anvil_entity_map.yaml"


def load_entity_map(source: Readable | None = None) -> EntityMap:
    """Load and check an entity map, the bundled one by default; ``ValueError`` naming where it is wrong.

    Checked here: the shape, each slot one of ``DONOR_FIELDS`` (or, on a table, ``FAMILY_FIELDS``) with a non-empty list of
    distinct columns, no column read both as the identifier (or a published table's source
    rows or repository identifier) and as a slot's, a slot only on a table or on the published
    donors, at least one table per dataset reading a slot, and no harmonized table under
    ``datasets``. Whether the columns exist and hold
    what the map says, and whether a table reading no slot serves a published table, is
    ``anvil_entities.check``'s, against the manifests.
    """
    resource = source if source is not None else default_entity_map_resource()
    document = map_document(resource, _UniqueKeyLoader, _WHERE, {"published"})
    tables = []
    for dataset, by_table in document["datasets"].items():
        expect_mapping(by_table, f"{_WHERE} {dataset}", "table")
        for table, entry in by_table.items():
            at = f"{_WHERE} {dataset}/{table}"
            if str(table).startswith(HARMONIZED_PREFIX):
                raise ValueError(f"{at}: a harmonized table is the repository's, not a submitter's; see `published`")
            expect_keys(entry, {IDENTIFIER}, {IDENTIFIER, *_TABLE_SLOTS}, at)
            identifier = expect_name(entry[IDENTIFIER], f"{at} identifier")
            slots = _slots(entry, at, {identifier}, _TABLE_SLOTS)
            tables.append(EntityTable(dataset=dataset, table=str(table), identifier=identifier, slots=slots))
    published = _published(document["published"])
    for dataset in document["datasets"]:
        if not any(t.slots for t in tables if t.dataset == dataset):
            raise ValueError(
                f"{_WHERE} {dataset}: no table reads a slot, so the import would write no submitter "
                "generation, and the import writes both generations of a dataset or neither"
            )
    return EntityMap(catalog=document["catalog"], tables=tuple(tables), published=published)


def _published(document: dict) -> tuple[PublishedEntities, ...]:
    """The ``published`` member: per kind, its table; at least one kind, donors first."""
    at = f"{_WHERE} published"
    expect_keys(document, set(), set(REPOSITORY_ID_FIELD), at)
    if not document:
        raise ValueError(f"{at}: names no kind; expected one or more of {sorted(REPOSITORY_ID_FIELD)}")
    published = []
    for kind in REPOSITORY_ID_FIELD:
        if kind not in document:
            continue
        entry, where = document[kind], f"{at} {kind}"
        expect_keys(entry, set(_PUBLISHED_KEYS), {*_PUBLISHED_KEYS, *_PUBLISHED_SLOTS[kind]}, where)
        source_rows = expect_name(entry["source_rows"], f"{where} source_rows")
        repository_id = expect_name(entry["repository_id"], f"{where} repository_id")
        if source_rows == repository_id:
            raise ValueError(
                f"{where}: column {source_rows!r} is read as the source rows and the repository identifier"
            )
        published.append(
            PublishedEntities(
                kind=kind,
                table=expect_name(entry["table"], f"{where} table"),
                source_rows=source_rows,
                repository_id=repository_id,
                slots=_slots(entry, where, {source_rows, repository_id}, _PUBLISHED_SLOTS[kind]),
            )
        )
    tables = [p.table for p in published]
    if len(set(tables)) != len(tables):
        raise ValueError(f"{at}: two kinds name one table, {tables}")
    return tuple(published)


def _slots(entry: dict, at: str, taken: set[str], fields: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """Each of ``fields`` that ``entry`` names and its columns, none or more, each a non-empty list of distinct names not in ``taken``."""
    slots = {}
    for slot in fields:
        if slot not in entry:
            continue
        columns = entry[slot]
        if not isinstance(columns, list) or not columns:
            raise ValueError(f"{at} {slot}: must be a non-empty list of columns, not {columns!r}")
        names = tuple(expect_name(c, f"{at} {slot}") for c in columns)
        if len(set(names)) != len(names):
            raise ValueError(f"{at} {slot}: lists a column twice")
        if clash := sorted(set(names) & taken):
            raise ValueError(
                f"{at} {slot}: column {clash[0]!r} is read as the identifier (or source rows, or repository id) too"
            )
        slots[slot] = names
    return slots
