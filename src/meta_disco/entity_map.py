"""The entity map: which of a source's tables say what about a donor (#693).

The slot map (``slot_map``) says where a raw value for one of a *file's* dimensions comes
from, keyed by a file-link column. This map says where a raw value for one of a *donor's*
slots (``models.DONOR_FIELDS``) comes from, keyed by the column naming the donor — rows
such as 1000 Genomes' ``pedigree`` have no file-link column to key them by. It is read by
``anvil_entities``, which writes each cell as an ``EntityEvidenceRow``. Like the slot map
it holds no vocabulary and maps structure, never meaning::

    datasets:
      ANVIL_1000G_high_coverage_2019:
        pedigree:
          identifier: pedigree_id
          phenotypic_sex: [sex]
          genetic_ancestry: [population, superpopulation]
    published:
      table: anvil_donor
      source_rows: source_datarepo_row_ids
      phenotypic_sex: [phenotypic_sex]

**Per table**: ``identifier``, the column naming the donor, and per slot the columns whose
cells it reads, at least one slot. A table of AnVIL's harmonized ``anvil_*`` data is not a
submitter table, and is refused under ``datasets``.

**``published``**: what the repository publishes for a donor, read in every dataset the map
names. Its ``table`` is AnVIL's donor table; ``source_rows`` its column naming the submitter
rows each donor was made from (``<table>:<datarepo_row_id>``), whose table's ``identifier``
column above names the donor.

No ``notes`` member, for the slot map's reason.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files

from .azul_manifest import HARMONIZED_PREFIX
from .lineage_map import expect_keys, expect_mapping, expect_name, map_document
from .models import DONOR_FIELDS
from .slot_map import Readable, unique_key_loader

_WHERE = "entity map"
IDENTIFIER = "identifier"
_PUBLISHED_KEYS = frozenset({"table", "source_rows"})

_UniqueKeyLoader = unique_key_loader(_WHERE)


@dataclass(frozen=True)
class EntityTable:
    """One mapped table of one dataset: the column naming the donor, and each slot's columns."""

    dataset: str
    table: str
    identifier: str
    slots: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class PublishedDonors:
    """The repository's donor table: its name, its column of source rows, and each slot's columns."""

    table: str
    source_rows: str
    slots: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class EntityMap:
    """A loaded entity map: the catalog it was authored against, its tables, and the published donor table."""

    catalog: str
    tables: tuple[EntityTable, ...]
    published: PublishedDonors

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

    Checked here: the shape, each slot one of ``DONOR_FIELDS`` with a non-empty list of
    distinct columns, no column read both as the identifier and as a slot's, and no
    harmonized table under ``datasets``. Whether the columns exist and hold what the map
    says is ``anvil_entities.check``'s, against the manifests.
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
            expect_keys(entry, {IDENTIFIER}, {IDENTIFIER, *DONOR_FIELDS}, at)
            identifier = expect_name(entry[IDENTIFIER], f"{at} identifier")
            slots = _slots(entry, at, {identifier})
            tables.append(EntityTable(dataset=dataset, table=str(table), identifier=identifier, slots=slots))
    published = document["published"]
    at = f"{_WHERE} published"
    expect_keys(published, set(_PUBLISHED_KEYS), {*_PUBLISHED_KEYS, *DONOR_FIELDS}, at)
    source_rows = expect_name(published["source_rows"], f"{at} source_rows")
    return EntityMap(
        catalog=document["catalog"],
        tables=tuple(tables),
        published=PublishedDonors(
            table=expect_name(published["table"], f"{at} table"),
            source_rows=source_rows,
            slots=_slots(published, at, {source_rows}),
        ),
    )


def _slots(entry: dict, at: str, taken: set[str]) -> dict[str, tuple[str, ...]]:
    """Each slot ``entry`` names and its columns; at least one slot, each a non-empty list of distinct names not in ``taken``."""
    slots = {}
    for slot in DONOR_FIELDS:
        if slot not in entry:
            continue
        columns = entry[slot]
        if not isinstance(columns, list) or not columns:
            raise ValueError(f"{at} {slot}: must be a non-empty list of columns, not {columns!r}")
        names = tuple(expect_name(c, f"{at} {slot}") for c in columns)
        if len(set(names)) != len(names):
            raise ValueError(f"{at} {slot}: lists a column twice")
        if clash := sorted(set(names) & taken):
            raise ValueError(f"{at} {slot}: column {clash[0]!r} is read as the identifier too")
        slots[slot] = names
    if not slots:
        raise ValueError(f"{at}: reads no slot; a mapped table reads at least one of {list(DONOR_FIELDS)}")
    return slots
