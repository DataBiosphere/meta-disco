"""The slot map: which of a source's tables and columns speak to which slot (#369).

A slot map is the importer's half of reading a source (claims contract 1.3, 2.2): it
says *where* a raw value for a slot comes from and nothing about what the value means.
It holds no vocabulary (1.5). `anvil_evidence` reads the AnVIL map to turn the verbatim
manifests into evidence files; the translation table (#414) is what turns the raw
values those carry into terms.

**One entry shape.** An entry is keyed by the **file-link column** — the column whose
DRS URI says which file a row is about — and names, per slot, where the raw value comes
from::

    datasets:
      AnVIL_HPRC_R2:
        hic:                       # table
          path:                    # file-link column
            platform:
              - {cell: platform}
              - {cell: instrument_model}
            assay_type:
              - {cell: library_strategy}
              - {table_name: hic}

A source is exactly one of three forms. ``{cell: <column>}`` is a metadata value in the
same row. ``{table_name: <span>}`` and ``{column_name: <span>}`` are a span of the
table's or the link column's own name, transcribed in the name's casing (``CHM13v2``,
not ``chm13``): a name is evidence the same as a cell is (contract 2.6), and the span
is what the evidence row carries as its raw value. A slot may name several sources —
``platform`` and ``instrument_model`` are two facts about one file and both are
evidence (6.8) — but the same word spelled in both the table name and the column name
is one source, not two, and the loader refuses it listed twice.

**Absence is the statement.** A column, table or dataset with nothing to map is not in
the file, and the loader does not require it to be. The ``catalog`` stamp records that
the whole of that catalog was considered, so absence means *considered and not mapped*
rather than overlooked (2.4). There is no ``notes`` member and the loader refuses one
by name: findings and reasoning belong in the pull request and on the issue, where they
are read, not in a data file.

**Sources stay pure** (3.4). Nothing in a map may cite what a classification run
concluded; ``test_slot_map`` checks the file for that. The only exclusions are
structural, and the loader enforces the two named ones so that authoring discipline is
not what they rest on:

- A **derivative column** — an index or a checksum sidecar, named by
  :data:`DERIVATIVE_SUFFIXES` — carries no ``data_type`` of its own payload. An index is
  an ``index`` (#437) and the column says so in its own name. Its ``reference_assembly``
  is the payload's and stays.
- An **entity-shaped name token** (:data:`ENTITY_TOKENS`) describes a row, not a file. A
  table keyed by ``interval_id`` with chromosome and start columns is one row per
  scatter window; its ``interval`` token says what the row is, and its files are that
  window's VCFs. No slot reads such a span.

The rest of what is and is not mapped is a judgment about the source's own schema,
recorded on the issue (#369) — never about a run.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from importlib.resources import files
from typing import Protocol

import yaml

from .manifest_survey import name_tokens
from .models import CLASSIFICATION_FIELDS

# The three forms a source can take, by the key its mapping carries.
SOURCE_CELL = "cell"
SOURCE_TABLE_NAME = "table_name"
SOURCE_COLUMN_NAME = "column_name"
SOURCE_FORMS = (SOURCE_CELL, SOURCE_TABLE_NAME, SOURCE_COLUMN_NAME)
_NAME_FORMS = frozenset({SOURCE_TABLE_NAME, SOURCE_COLUMN_NAME})

# A column whose name ends in one of these, after the last underscore or dot, is a
# sidecar of another column's file: an index or a checksum. It takes no `data_type` from
# a name (its own name already says what it is) and keeps the payload's
# `reference_assembly`. `idx` and `index` are how the T2T workflows spell it, `fai` /
# `gzi` are samtools', `crai` / `bai` / `tbi` / `csi` are htslib's.
DERIVATIVE_SUFFIXES = frozenset({"index", "idx", "bai", "crai", "tbi", "csi", "fai", "gzi", "md5"})

# Name tokens that describe what a *row* is rather than what its files are. Only the
# ones a slot could otherwise read are listed: `sample`, `participant` and `donor` are
# entity-shaped too but no slot token maps them, so there is nothing to refuse.
ENTITY_TOKENS = frozenset({"interval"})

# The one member a map must not carry, and what the refusal says.
_NOTES = "notes"
_NO_NOTES = (
    "there is no notes member — findings and reasoning go in the pull request and on the issue, "
    "where they are read; a data file maps what maps and is otherwise silent"
)
_WHERE = "slot map"

_FIELDS = frozenset(CLASSIFICATION_FIELDS)
DATA_TYPE = "data_type"


@dataclass(frozen=True)
class SlotSource:
    """Where one slot's raw value comes from: a cell of the row, or a span of a name."""

    form: str
    value: str

    @property
    def is_name(self) -> bool:
        return self.form in _NAME_FORMS


@dataclass(frozen=True)
class ColumnEntry:
    """One file-link column and what its files' slots are read from.

    ``slots`` maps a slot to its sources in file order. Every non-empty value a column
    named here holds in the source is a DRS URI or a list of them — `anvil_evidence.check`
    verifies that against the manifests, since the map cannot.
    """

    dataset: str
    table: str
    column: str
    slots: dict[str, tuple[SlotSource, ...]]

    @property
    def is_derivative(self) -> bool:
        return is_derivative_column(self.column)


@dataclass(frozen=True)
class SlotMap:
    """A loaded map: the catalog it was authored against and every column entry in it."""

    catalog: str
    entries: tuple[ColumnEntry, ...]

    def datasets(self) -> list[str]:
        """Dataset titles in file order, each once."""
        return list(dict.fromkeys(e.dataset for e in self.entries))

    def tables(self, dataset: str) -> list[str]:
        return list(dict.fromkeys(e.table for e in self.entries if e.dataset == dataset))

    def columns(self, dataset: str, table: str) -> list[ColumnEntry]:
        return [e for e in self.entries if e.dataset == dataset and e.table == table]

    def cells(self, dataset: str, table: str) -> set[str]:
        """Every column a ``cell`` source of this table names."""
        return {
            source.value
            for entry in self.columns(dataset, table)
            for sources in entry.slots.values()
            for source in sources
            if source.form == SOURCE_CELL
        }


def is_derivative_column(column: str) -> bool:
    """Whether a column name says its file is an index or checksum of another file."""
    tokens = name_tokens(column)
    return bool(tokens) and tokens[-1] in DERIVATIVE_SUFFIXES


ENTITY = "entity"
DERIVATIVE = "derivative"


def structural_exclusion(slot: str, column: str, span: str) -> str | None:
    """Which of the two structural rules refuses ``span`` as a source for ``slot`` on ``column``, if either.

    The one statement of both rules: the loader raises on what this returns, and the
    forecast (`anvil_forecast.name_claims`) counts it, so a rule added here reaches
    both. ``ENTITY`` — a token of the span names what a row is; ``DERIVATIVE`` — the
    slot is ``data_type`` and the column is an index or checksum sidecar.
    """
    if any(token in ENTITY_TOKENS for token in name_tokens(span)):
        return ENTITY
    if slot == DATA_TYPE and is_derivative_column(column):
        return DERIVATIVE
    return None


class Readable(Protocol):
    """What a map is loaded from: a `Path` or a package-data resource, read as text."""

    def read_text(self, encoding: str) -> str: ...


def default_slot_map_resource():
    """The bundled AnVIL map, as a package-data resource (a `Readable`)."""
    return files(f"{__package__}.sources") / "anvil_slot_map.yaml"


class _UniqueKeyLoader(yaml.SafeLoader):
    """A YAML loader that refuses a duplicate mapping key instead of keeping the last.

    PyYAML's default silently takes the later value, so a column listed twice under one
    table would drop one of them without a word. Refused naming the key and the line.
    """

    def construct_mapping(self, node, deep=False):
        seen: dict = {}
        for key_node, _value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ValueError(
                    f"slot map line {key_node.start_mark.line + 1}: duplicate key {key!r} "
                    f"(first at line {seen[key] + 1}) — one entry per column, table and dataset"
                )
            seen[key] = key_node.start_mark.line
        return super().construct_mapping(node, deep=deep)


def load_slot_map(source: Readable | None = None) -> SlotMap:
    """Load and check a slot map; the bundled AnVIL one by default.

    The shape rules — one entry shape, three source forms, a span inside its name, no
    source twice, no ``notes``, the two structural exclusions — are checked here, and
    the first violation raises ``ValueError`` naming the dataset, table, column and
    slot it sits on. Source purity (R1) is not a shape and is ``test_slot_map``'s to
    check. Load time rather than import time: a map that cannot load must not be able
    to produce an evidence file, and an importer running against millions of rows
    should learn about a malformed entry before it reads the first one.
    """
    resource = source if source is not None else default_slot_map_resource()
    document = yaml.load(resource.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    if not isinstance(document, dict):
        raise ValueError(f"{_WHERE}: the document is {type(document).__name__}, not a mapping")
    _refuse_notes(document, _WHERE)
    if set(document) != {"catalog", "datasets"}:
        raise ValueError(f"{_WHERE}: top-level keys are {sorted(document)}, expected exactly ['catalog', 'datasets']")
    catalog = document["catalog"]
    if not isinstance(catalog, str) or not catalog:
        raise ValueError(f"{_WHERE}: catalog is {catalog!r}, not the name of the catalog the map was authored against")
    datasets = document["datasets"]
    _expect_nonempty_mapping(datasets, _WHERE, "dataset")
    return SlotMap(catalog=catalog, entries=tuple(_entries(datasets)))


def _entries(datasets: dict) -> Iterator[ColumnEntry]:
    for dataset, tables in datasets.items():
        _expect_nonempty_mapping(tables, f"{_WHERE} {dataset}", "table")
        for table, columns in tables.items():
            _expect_nonempty_mapping(columns, f"{_WHERE} {dataset}/{table}", "file-link column")
            for column, slots in columns.items():
                at = f"{_WHERE} {dataset}/{table}/{column}"
                _expect_nonempty_mapping(slots, at, "slot")
                yield ColumnEntry(
                    dataset=dataset,
                    table=table,
                    column=column,
                    slots={slot: _sources(slot, sources, table, column, at) for slot, sources in slots.items()},
                )


def _sources(slot: str, sources: object, table: str, column: str, at: str) -> tuple[SlotSource, ...]:
    """Check one slot's source list, returning it typed."""
    if slot not in _FIELDS:
        raise ValueError(f"{at}: {slot!r} is not a slot (expected one of {sorted(_FIELDS)})")
    at = f"{at} {slot}"
    if isinstance(sources, str):
        raise ValueError(
            f"{at}: is the bare term {sources!r} — a slot names where its raw value comes from "
            f"({', '.join(SOURCE_FORMS)}), never a value; the map holds no vocabulary"
        )
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"{at}: must be a non-empty list of sources, not {type(sources).__name__}")
    parsed = [_source(slot, item, table, column, at) for item in sources]
    seen: dict[tuple[str, str], SlotSource] = {}
    for source in parsed:
        key = ("name", source.value.casefold()) if source.is_name else (source.form, source.value)
        if key in seen:
            raise ValueError(
                f"{at}: {source.form} {source.value!r} repeats {seen[key].form} {seen[key].value!r} — "
                "the same fact spelled twice is one source, not two"
            )
        seen[key] = source
    return tuple(parsed)


def _source(slot: str, item: object, table: str, column: str, at: str) -> SlotSource:
    if not isinstance(item, dict) or len(item) != 1:
        raise ValueError(f"{at}: a source is one mapping with one key ({', '.join(SOURCE_FORMS)}), not {item!r}")
    ((form, value),) = item.items()
    if form == _NOTES:
        raise ValueError(f"{at}: {_NO_NOTES}")
    if form not in SOURCE_FORMS:
        raise ValueError(f"{at}: {form!r} is not a source form (expected one of {SOURCE_FORMS})")
    if not isinstance(value, str) or not value:
        raise ValueError(f"{at}: {form} is {value!r}, not a non-empty string")
    if form == SOURCE_CELL and value == column:
        raise ValueError(f"{at}: cell {value!r} is the file-link column itself, which holds a pointer and no value")
    if form == SOURCE_TABLE_NAME and not _span_of(value, table):
        raise ValueError(
            f"{at}: span {value!r} is not a run of whole tokens of the table name {table!r}, in the name's own casing"
        )
    if form == SOURCE_COLUMN_NAME and not _span_of(value, column):
        raise ValueError(
            f"{at}: span {value!r} is not a run of whole tokens of the column name {column!r}, in the name's own casing"
        )
    excluded = structural_exclusion(slot, column, value if form in _NAME_FORMS else "")
    if excluded == ENTITY:
        raise ValueError(
            f"{at}: span {value!r} names what a row is, not what its files are (entity tokens: "
            f"{sorted(ENTITY_TOKENS)}), so no slot reads it"
        )
    if excluded == DERIVATIVE:
        raise ValueError(
            f"{at}: {column!r} is an index or checksum column and carries no data_type of its own "
            f"payload (suffixes {sorted(DERIVATIVE_SUFFIXES)}); its reference_assembly may be mapped"
        )
    return SlotSource(form=form, value=value)


def _span_of(span: str, name: str) -> bool:
    """Whether ``span`` is a run of whole tokens of ``name``, spelled as the name spells it.

    Whole tokens, not a substring: ``ont`` is inside ``montage`` and says nothing about
    it. The tokens are :func:`name_tokens`'s, so the test agrees with the survey's; the
    casing check is on the raw text, because a span is transcribed as the name's raw
    value and must be the name's own spelling.
    """
    if span not in name:
        return False
    tokens, wanted = name_tokens(name), name_tokens(span)
    if not wanted:
        return False
    return any(tokens[i : i + len(wanted)] == wanted for i in range(len(tokens) - len(wanted) + 1))


def _refuse_notes(mapping: dict, at: str) -> None:
    if _NOTES in mapping:
        raise ValueError(f"{at}: {_NO_NOTES}")


def _expect_nonempty_mapping(value: object, at: str, noun: str) -> None:
    """An empty level maps nothing, and nothing-to-map is spelled by absence, not by an empty block."""
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{at}: must be a mapping of at least one {noun} — a level with nothing to map is left out")
    _refuse_notes(value, at)
