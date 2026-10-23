"""The slot map: which of a source's tables and columns speak to which slot (#369).

A slot map is the importer's half of reading a source (claims contract 1.3, 2.2): it
says *where* a raw value for a slot comes from and nothing about what the value means.
It holds no vocabulary (1.5). `anvil_evidence` reads the AnVIL map to turn the verbatim
manifests into evidence files; the translation table (`value_map`, #414) is where raw
values become terms.

**Two entry shapes.** A **link entry** is keyed by the **file-link column** — the column
whose DRS URI says which file a row is about — and names, per slot, where the raw value
comes from::

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

**A folder entry** (#604) reaches its files by where they are stored rather than by DRS
URI: its column holds the name of a top folder of the dataset's storage, and its one
member that is not a slot, ``files_under``, names the path below it. The entry reaches
every file with a ``file_ref`` whose ``anvil_file.file_path``, its empty segments dropped,
begins ``<cell>/<files_under>/`` (``anvil_evidence.folder_files``)::

    ANVIL_NIA_CARD_Coriell_Cell_Lines_Open:
      sequencing:
        seq_filename:              # holds a top folder's name, `HG002_R10`
          files_under: reads       # reaches `HG002_R10/reads/…`
          assay_type:
            - {cell: sequencing_assay}

Its column's name says nothing about the files it reaches, so the derivative and checksum
exclusions below cannot be read off it: ``anvil_evidence.check`` refuses a folder entry that
reaches a file whose own name ends in one of those suffixes, and the entry's ``files_under``
is narrowed instead. It is declared per table, so it reaches files only where a map names it. What it reaches
is written as any other entry's evidence, keyed by the file's DRS URI. It may not carry
two things a link entry may: a ``column_name`` span, because the folder column's name is a
field label that describes no file, and the ``samples`` slot, until a folder row's sample
can be compared with each file's own (#740). A cell of the same table may not name a folder
column either: the column is a pointer, and a column is one kind, never two (2.7).

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

**A map says what kind of source it describes.** The top-level ``source_type`` is one
of ``IMPORTER_SOURCE_TYPES`` other than a lineage-only kind (``LINEAGE_ONLY_SOURCE_TYPES``,
#583) and becomes the envelope's ``source_type`` on every evidence file the importer
writes from the map; it defaults to ``repository_metadata``,
a submitter's own table, and the published map (#497) declares ``published_value``. One
map is one kind of source — a map that mixed the two would have no place to say which
table is which.

**Sources stay pure** (3.4). Nothing in a map may cite what a classification run
concluded; ``test_slot_map`` checks the file for the strings that would. The only
exclusions are structural. Three are enforced by the loader:

- A **derivative column** — an index or a checksum sidecar, named by
  :data:`DERIVATIVE_SUFFIXES` — carries no ``data_type`` of its own payload. An index is
  an ``index`` (#437) and the column says so in its own name. Its ``reference_assembly``
  is the payload's and stays.
- A **checksum column** (:data:`CHECKSUM_SUFFIXES`) takes no slot at all: a checksum
  holds no data, so its ``data_type`` is ``checksum`` and every carried dimension is
  ``not_applicable`` (the ``checksum_file`` rule,
  #596), and a source value for one would only conflict with it.
- An **entity-shaped name token** (:data:`ENTITY_TOKENS`) describes a row, not a file. A
  table keyed by ``interval_id`` with chromosome and start columns is one row per
  scatter window; its ``interval`` token says what the row is, and its files are that
  window's VCFs. No slot reads such a span.

The rest is the authoring rule, a judgment about the source's own schema that the
loader does not enforce, recorded here and on the issue (#369) — never about a run.
Contract 2.7 sorts columns into file links, metadata values and foreign keys. A
**cell** maps where the column's name, in the source's schema, names one of our
dimensions. A table with **one** file-link column is a file table: its name describes the
file, so its name tokens map. A table with **several** is an entity table (one row per
sample, one column per file): its column names describe the files and map, and its
name maps for a slot only on the columns whose files all share the fact, and not for one
the row's files differ on (an entity table holding an assembly and its alignments takes
no `data_type` from `assembly` in its name). A reference build named in the table name
is shared by the row's outputs — its alignments, calls and stats — and not by its
unaligned input reads, which carry no reference: ANVIL_T2T_CHRY lists the same FASTQs in its
``SGDP_CHM13v2_sample`` and ``SGDP_GRCh38_sample`` tables, so their read columns take
no reference from either name (#555).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from importlib.resources import files
from typing import Protocol

import yaml

from .manifest_survey import name_tokens
from .models import (
    EVIDENCE_FIELDS,
    LINEAGE_ONLY_SOURCE_TYPES,
    SAMPLES_FIELD,
    SOURCE_REPOSITORY_METADATA,
    require_importer_source_type,
)

# The member of a folder entry that is not a slot (#604): the path below the folder its
# column names, under which the entry's files are stored.
FILES_UNDER = "files_under"

# The three forms a source can take, by the key its mapping carries.
SOURCE_CELL = "cell"
SOURCE_TABLE_NAME = "table_name"
SOURCE_COLUMN_NAME = "column_name"
SOURCE_FORMS = (SOURCE_CELL, SOURCE_TABLE_NAME, SOURCE_COLUMN_NAME)
_NAME_FORMS = frozenset({SOURCE_TABLE_NAME, SOURCE_COLUMN_NAME})

# A column whose last name token (`name_tokens`) is one of these is a sidecar of
# another column's file: an index or a checksum. It takes no `data_type` from any
# source, name or cell (its own name already says what it is). An index keeps the
# payload's `reference_assembly`; a checksum (`CHECKSUM_SUFFIXES`, below) takes no slot.
DERIVATIVE_SUFFIXES = frozenset({"index", "idx", "bai", "crai", "tbi", "csi", "fai", "gzi", "md5"})
# The derivative suffixes that name a checksum, which takes no slot from any source (#596):
# its own `data_type` is `checksum` and its carried dimensions are `not_applicable`.
CHECKSUM_SUFFIXES = frozenset({"md5"})

# Name tokens that describe what a *row* is rather than what its files are. Only the
# ones a slot could otherwise read are listed: `sample`, `participant` and `donor` are
# entity-shaped too but no slot token maps them, so there is nothing to refuse.
ENTITY_TOKENS = frozenset({"interval"})

# The one member a data file must not carry, and what the refusal says. Shared with
# `value_map`, whose rows carry a `reason` and no prose either.
NOTES = "notes"
NO_NOTES = (
    "there is no notes member — findings and reasoning go in the pull request and on the issue, "
    "where they are read; a data file maps what maps and is otherwise silent"
)
_WHERE = "slot map"

_FIELDS = frozenset(EVIDENCE_FIELDS)
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
    """One file-link or folder column and what its files' slots are read from.

    ``slots`` maps a slot to its sources in file order. Every non-empty value a link
    column holds in the source is a DRS URI or a list of them; every one a folder
    column (``files_under`` set, #604) holds is a top folder's name. `anvil_evidence.check`
    verifies either against the manifests, since the map cannot.
    """

    dataset: str
    table: str
    column: str
    slots: dict[str, tuple[SlotSource, ...]]
    files_under: str | None = None

    @property
    def is_folder(self) -> bool:
        return self.files_under is not None

    def folder_prefix(self, folder: str) -> str:
        """The storage-path prefix of the files this folder entry reaches from the folder a cell names."""
        if self.files_under is None:
            raise ValueError(f"{self.dataset}/{self.table}/{self.column} is a link column, not a folder column")
        return f"{folder}/{self.files_under}/"

    @property
    def is_derivative(self) -> bool:
        return is_derivative_column(self.column)


@dataclass(frozen=True)
class SlotMap:
    """A loaded map: the catalog it was authored against, the kind of source it
    describes (one of ``IMPORTER_SOURCE_TYPES`` less ``LINEAGE_ONLY_SOURCE_TYPES``), and every column entry in it."""

    catalog: str
    source_type: str
    entries: tuple[ColumnEntry, ...]

    def datasets(self) -> list[str]:
        """Dataset titles in file order, each once."""
        return list(dict.fromkeys(e.dataset for e in self.entries))

    def tables(self, dataset: str) -> list[str]:
        return list(dict.fromkeys(e.table for e in self.entries if e.dataset == dataset))

    def columns(self, dataset: str, table: str) -> list[ColumnEntry]:
        return [e for e in self.entries if e.dataset == dataset and e.table == table]

    def has_folders(self, dataset: str) -> bool:
        """Whether any of the dataset's entries is a folder entry, whose files are reached by storage path."""
        return any(e.is_folder for e in self.entries if e.dataset == dataset)

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
    return is_derivative_name(column)


def is_derivative_name(name: str) -> bool:
    """Whether a name — a column's, or a file's own (``x.bam.bai``) — ends in an index or checksum
    suffix (:data:`DERIVATIVE_SUFFIXES`)."""
    tokens = name_tokens(name)
    return bool(tokens) and tokens[-1] in DERIVATIVE_SUFFIXES


def is_checksum_column(column: str) -> bool:
    """Whether a column name says its file is a checksum of another file."""
    tokens = name_tokens(column)
    return bool(tokens) and tokens[-1] in CHECKSUM_SUFFIXES


ENTITY = "entity"
DERIVATIVE = "derivative"
CHECKSUM = "checksum"


def structural_exclusion(slot: str, column: str, span: str) -> str | None:
    """Which of the three structural rules refuses ``span`` as a source for ``slot`` on ``column``, if any.

    The one statement of the rules: the loader raises on what this returns. ``ENTITY`` — a
    token of the span names what a row is; ``CHECKSUM`` — the column is a checksum sidecar,
    which takes no slot; ``DERIVATIVE`` — the slot is ``data_type`` and the column is an
    index sidecar.
    """
    if any(token in ENTITY_TOKENS for token in name_tokens(span)):
        return ENTITY
    if is_checksum_column(column):
        return CHECKSUM
    if slot == DATA_TYPE and is_derivative_column(column):
        return DERIVATIVE
    return None


class Readable(Protocol):
    """What a map is loaded from: a `Path` or a package-data resource, read as text."""

    def read_text(self, encoding: str) -> str: ...


def default_slot_map_resource():
    """The bundled AnVIL map of the submitter tables, as a package-data resource (a `Readable`)."""
    return files(f"{__package__}.sources") / "anvil_slot_map.yaml"


def published_slot_map_resource():
    """The bundled AnVIL map of the published ``anvil_file`` columns (#497), as a package-data resource."""
    return files(f"{__package__}.sources") / "anvil_published_slot_map.yaml"


def unique_key_loader(label: str, hint: str = "") -> type[yaml.SafeLoader]:
    """A YAML loader that refuses a duplicate mapping key instead of keeping the last.

    PyYAML's default silently takes the later value, so an entry listed twice would drop
    one of them without a word. Refused naming ``label``, the key and both lines, with
    ``hint`` after. Shared by the slot map and the lineage map (#583).
    """

    class UniqueKeyLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            seen: dict = {}
            for key_node, _value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if key in seen:
                    raise ValueError(
                        f"{label} line {key_node.start_mark.line + 1}: duplicate key {key!r} "
                        f"(first at line {seen[key] + 1}){hint}"
                    )
                seen[key] = key_node.start_mark.line
            return super().construct_mapping(node, deep=deep)

    return UniqueKeyLoader


_UniqueKeyLoader = unique_key_loader(_WHERE, " — one entry per column, table and dataset")


def load_slot_map(source: Readable | None = None) -> SlotMap:
    """Load and check a slot map; the bundled AnVIL one by default.

    The shape rules — the two entry shapes, three source forms, a span inside its name, no
    source twice, no ``notes``, the three structural exclusions — are checked here, and
    the first violation raises ``ValueError`` naming where it sits, as far down as the
    level allows (dataset, table, column, slot; a duplicate key by its line). Source
    purity (contract 3.4) is not a shape and is ``test_slot_map``'s to check. Checked
    when the map loads, not when an import reaches a bad entry: a map that cannot load
    must not produce an evidence file, and an importer should fail before it reads the
    first of millions of rows.
    """
    resource = source if source is not None else default_slot_map_resource()
    document = yaml.load(resource.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    if not isinstance(document, dict):
        raise ValueError(f"{_WHERE}: the document is {type(document).__name__}, not a mapping")
    _refuse_notes(document, _WHERE)
    if not {"catalog", "datasets"} <= set(document) <= {"catalog", "datasets", "source_type"}:
        raise ValueError(
            f"{_WHERE}: top-level keys are {sorted(document)}, expected 'catalog' and 'datasets' "
            "and optionally 'source_type'"
        )
    catalog = document["catalog"]
    if not isinstance(catalog, str) or not catalog:
        raise ValueError(f"{_WHERE}: catalog is {catalog!r}, not the name of the catalog the map was authored against")
    source_type = require_importer_source_type(
        document.get("source_type", SOURCE_REPOSITORY_METADATA), "source_type", _WHERE
    )
    if source_type in LINEAGE_ONLY_SOURCE_TYPES:
        raise ValueError(
            f"{_WHERE}: source_type {source_type!r} is written only as lineage evidence, not by a slot map"
        )
    datasets = document["datasets"]
    _expect_nonempty_mapping(datasets, _WHERE, "dataset")
    return SlotMap(catalog=catalog, source_type=source_type, entries=tuple(_entries(datasets)))


def _entries(datasets: dict) -> Iterator[ColumnEntry]:
    for dataset, tables in datasets.items():
        _expect_nonempty_mapping(tables, f"{_WHERE} {dataset}", "table")
        for table, columns in tables.items():
            _expect_nonempty_mapping(columns, f"{_WHERE} {dataset}/{table}", "file-link column")
            entries = [_entry(dataset, table, column, members) for column, members in columns.items()]
            _refuse_cells_naming_folders(entries, f"{_WHERE} {dataset}/{table}")
            yield from entries


def _entry(dataset: str, table: str, column: str, members: dict) -> ColumnEntry:
    at = f"{_WHERE} {dataset}/{table}/{column}"
    _expect_nonempty_mapping(members, at, "slot")
    files_under = _files_under(members[FILES_UNDER], at) if FILES_UNDER in members else None
    slots = {slot: sources for slot, sources in members.items() if slot != FILES_UNDER}
    if not slots:
        raise ValueError(f"{at}: names {FILES_UNDER} and no slot — a folder entry maps at least one slot")
    if files_under is not None:
        _refuse_in_folder_entry(slots, column, at)
    parsed = {slot: _sources(slot, sources, table, column, at) for slot, sources in slots.items()}
    return ColumnEntry(dataset=dataset, table=table, column=column, slots=parsed, files_under=files_under)


def _files_under(value: object, at: str) -> str:
    """Check a folder entry's ``files_under``: a relative path of plain segments, no ``.`` or ``..``."""
    if isinstance(value, str) and all(segment not in ("", ".", "..") for segment in value.split("/")):
        return value
    raise ValueError(
        f"{at}: {FILES_UNDER} is {value!r}, not a relative path of folder names below the folder the "
        "column names (no leading or trailing '/', no '.' or '..')"
    )


def _refuse_in_folder_entry(slots: dict, column: str, at: str) -> None:
    """Refuse what a link entry may carry and a folder entry may not: the ``samples`` slot, and a
    span of the column's name. Read off the unparsed sources, so either is refused for what it is
    before any other rule a source breaks is reported."""
    if SAMPLES_FIELD in slots:
        raise ValueError(
            f"{at} {SAMPLES_FIELD}: a folder entry reads no samples — a folder row's sample is not yet "
            "compared with each file's own (#740)"
        )
    for slot, sources in slots.items():
        if isinstance(sources, list) and any(isinstance(s, dict) and SOURCE_COLUMN_NAME in s for s in sources):
            raise ValueError(
                f"{at} {slot}: column {column!r} names a folder, and its name is a field label that describes "
                "no file, so no slot reads a span of it"
            )


def _refuse_cells_naming_folders(entries: list[ColumnEntry], at: str) -> None:
    """A cell naming one of the table's folder columns reads a pointer as a value: refused (2.7)."""
    folders = {entry.column for entry in entries if entry.is_folder}
    for entry in entries:
        for slot, sources in entry.slots.items():
            for source in sources:
                if source.form == SOURCE_CELL and source.value in folders:
                    raise ValueError(
                        f"{at}/{entry.column} {slot}: cell {source.value!r} is a folder column of this table, "
                        "which holds a pointer and no value"
                    )


def _is_cell(item: object) -> bool:
    return isinstance(item, dict) and list(item) == [SOURCE_CELL]


def _sources(slot: str, sources: object, table: str, column: str, at: str) -> tuple[SlotSource, ...]:
    """Check one slot's source list, returning it typed."""
    if slot not in _FIELDS:
        raise ValueError(f"{at}: {slot!r} is not a slot (expected one of {sorted(_FIELDS)})")
    at = f"{at} {slot}"
    # A sample is read from one cell of the row (#357): a table's or a column's name says what
    # the files are, never which sample they are of, and a second cell would be a second
    # source for the same fact from the same row.
    if slot == SAMPLES_FIELD and isinstance(sources, list) and (len(sources) != 1 or not _is_cell(sources[0])):
        raise ValueError(f"{at}: a sample is read from exactly one {SOURCE_CELL}, never from a name")
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
    if form == NOTES:
        raise ValueError(f"{at}: {NO_NOTES}")
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
    if excluded == CHECKSUM:
        raise ValueError(
            f"{at}: {column!r} is a checksum column (suffixes {sorted(CHECKSUM_SUFFIXES)}), which holds no data, so "
            f"it takes no slot: a checksum's data_type is checksum and its carried dimensions are not_applicable (#596)"
        )
    if excluded == DERIVATIVE:
        raise ValueError(
            f"{at}: {column!r} is an index column and carries no data_type of its own "
            f"payload (suffixes {sorted(DERIVATIVE_SUFFIXES - CHECKSUM_SUFFIXES)}); its reference_assembly may be mapped"
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
    if NOTES in mapping:
        raise ValueError(f"{at}: {NO_NOTES}")


def _expect_nonempty_mapping(value: object, at: str, noun: str) -> None:
    """An empty level maps nothing, and nothing-to-map is spelled by absence, not by an empty block."""
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{at}: must be a mapping of at least one {noun} — a level with nothing to map is left out")
    _refuse_notes(value, at)
