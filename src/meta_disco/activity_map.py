"""The activity translation table: lineage's raw words to an activity and a role (#584).

A lineage line (``lineage_evidence``, #583) says a file was made from a parent in the
source's own words, and declares nothing. This table is the one step between that
observation and the step reconcile will build (#577): a lookup from what the line says
to an activity of ``activity_type_enum`` and the role the parent takes in it, whose
``passes`` (``rules/activities.yaml``) say what the parent hands on. It is
``value_map``'s counterpart for lineage (contract 3.9-3.12). It shares value_map's YAML
walk and append-only seeding (``yaml_rows``), its report columns (``summaries``) and
its id slugging (``manifest_survey.name_tokens``); it does not import ``value_map``.

**The file** is ``rules/activity_map.yaml``, a mapping whose one key is ``rows``::

    rows:
      - id: activity.indexing
        match: {source_type: repository_activity, raw_activity: Indexing}
        declares: {activity: IndexActivity, role: indexed}
        reason: An AnVIL Indexing step makes an index of the one file it used.
        seeded_from: [anvil/anvil15/ANVIL_T2T_CHRY/20260930T062532Z]

**A line's key** is the seven :data:`PARTS`, each the line's value or ``None`` where it
has none: the envelope's ``source_type`` and ``table``; the line's ``raw_activity``,
``child_column`` and ``parent_column``; and ``child_data_type`` / ``parent_data_type``,
the raw ``data_type`` value the slot evidence of the *same* catalog, repository,
dataset, table and kind of source wrote for the child and for the parent (IGVF's
``content_type``, #570). A source that writes no ``data_type`` for its lineage table
(``anvil_activity``, T2T's sample tables) leaves both ``None``, as does a file the table
gives two values. Only the latest catalog is read (:func:`lineage_paths`). Nothing is joined into one string, and every
part is compared exactly as the source wrote it: no casefolding, no stripping.

**A row's match** names ``source_type`` and any others of the parts, each a string,
``null`` (the line has none), or a non-empty list of those. A row matches a line when
every part it names holds the line's value; a part it does not name is not looked at.
A seeded row names all seven, so it matches exactly the key it was seeded from.
**No two rows may match one line**: two rows whose values intersect on every part both
name cannot load, seeded or authored alike, so authoring a row that covers seeded keys
means deleting those seeded rows, and the seeder never mints them again.

A row is **authored** when it carries a ``reason``, and then must carry ``declares:
{activity, role}``: an activity ``activities.yaml`` declares, and a role that activity
declares. A **seeded** row has no ``reason`` and declares nothing. An id is
``activity.<slug>``: the prefix keeps it apart from rule ids (which contain no dot) and
from ``value_map``'s ids, whose prefix is a slot.

**Nothing in a classification run or in reconcile reads this module yet**; reconcile
applying it is #577. The seeder and review queue read the lineage files through
``lineage_evidence.iter_lineage`` and the slot files through
``source_evidence.iter_evidence``, one line at a time.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import yaml

from .activities import Declared, declarations, require_writable
from .lineage_evidence import DEFAULT_LINEAGE_EVIDENCE_ROOT, LINEAGE_SOURCE_TYPES, iter_lineage, read_lineage_envelope
from .manifest_survey import name_tokens
from .models import SOURCE_REPOSITORY_ACTIVITY, SOURCE_REPOSITORY_METADATA
from .schema.classification_model import EvidenceFileEnvelope, LineageRow
from .source_evidence import DEFAULT_SOURCE_EVIDENCE_ROOT, discover, is_generation, iter_evidence, read_envelope
from .summaries import ReportColumn, md_rows
from .yaml_rows import (
    NULL_TAG,
    STR_TAG,
    fresh_id,
    generation_name,
    kind,
    mapping,
    open_rows,
    parse_rows,
    read_reason,
    read_seeded_from,
    replace_checked,
    row_indent,
    row_text,
    scalar,
)

PARTS = (
    "source_type",
    "table",
    "raw_activity",
    "child_column",
    "parent_column",
    "child_data_type",
    "parent_data_type",
)
Value = str | None
LineKey = tuple[Value, ...]
"""A line's value for each of :data:`PARTS`, in order."""

ROW_KEYS = frozenset({"id", "match", "declares", "reason", "seeded_from"})
DECLARES_KEYS = frozenset({"activity", "role"})
ID_PREFIX = "activity."
_WHERE = "activity map"


def default_activity_map_resource():
    """The bundled table, as package data beside the rule set."""
    return files(f"{__package__}.rules") / "activity_map.yaml"


# --- rows -------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Row:
    """One row as loaded: each named part's values as a set, and the declaration when authored."""

    id: str
    match: Mapping[str, frozenset[Value]]
    activity: str | None
    role: str | None
    reason: str | None

    @property
    def authored(self) -> bool:
        return self.reason is not None


@dataclass(frozen=True)
class ActivityMap:
    """A loaded table and its selection index: per set of named parts, the rows by each value tuple they match."""

    rows: tuple[Row, ...]
    # The sha256 of the text the table was loaded from, so an artifact built from it can
    # say which table that was; None for a table built in memory.
    digest: str | None = None
    _index: dict[tuple[str, ...], dict[tuple[Value, ...], Row]] = field(default_factory=dict, init=False, repr=False)
    _selected: dict[LineKey, Row | None] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        """Refuse two rows that could match one line, then index every value combination each row names."""
        for a, b in itertools.combinations(self.rows, 2):
            shared = a.match.keys() & b.match.keys()
            if all(a.match[p] & b.match[p] for p in shared):
                raise ValueError(
                    f"{_WHERE}: rows {a.id!r} and {b.id!r} can both match one line — "
                    f"they agree on every part both name ({sorted(shared)}); a line has one row"
                )
        for row in self.rows:
            shape = tuple(p for p in PARTS if p in row.match)
            by_values = self._index.setdefault(shape, {})
            for values in itertools.product(*(sorted(row.match[p], key=_sort_key) for p in shape)):
                by_values[values] = row

    def select(self, key: LineKey) -> Row | None:
        """The one row matching this line's key, or None. Memoized: a file's keys repeat."""
        if key in self._selected:
            return self._selected[key]
        found = None
        for shape, by_values in self._index.items():
            row = by_values.get(tuple(key[PARTS.index(p)] for p in shape))
            if row is not None:
                found = row
                break
        self._selected[key] = found
        return found


def _sort_key(value: Value) -> tuple[bool, str]:
    return (value is not None, value or "")


# --- loading ----------------------------------------------------------------------


def load_activity_map(path: Path | None = None, activities: Mapping[str, Declared] | None = None) -> ActivityMap:
    """Load and check the table (the bundled one by default) against ``activities`` (the bundled declarations).

    The first violation raises ``ValueError`` naming the row, by id where it has one.
    """
    resource = path if path is not None else default_activity_map_resource()
    text = resource.read_text(encoding="utf-8")
    declared = activities if activities is not None else declarations()
    seen_ids: dict[str, int] = {}
    rows = []
    for n, node in enumerate(parse_rows(text, _WHERE), start=1):
        row = _row(node, n, declared)
        if row.id in seen_ids:
            raise ValueError(f"{_WHERE}: row {n} repeats id {row.id!r} (first at row {seen_ids[row.id]})")
        seen_ids[row.id] = n
        rows.append(row)
    return ActivityMap(rows=tuple(rows), digest=hashlib.sha256(text.encode("utf-8")).hexdigest())


def _row(node: yaml.Node, n: int, declared: Mapping[str, Declared]) -> Row:
    at = f"{_WHERE} row {n}"
    entries = mapping(node, at)
    if "id" not in entries:
        raise ValueError(f"{at}: missing id")
    id = scalar(entries["id"], at)
    at = f"{_WHERE} row {id!r}"
    if not id.startswith(ID_PREFIX) or not id[len(ID_PREFIX) :].strip() or "\n" in id or "\r" in id:
        raise ValueError(f"{at}: id must be {ID_PREFIX + '<slug>'!r} on one line, with a non-blank slug")
    unknown = set(entries) - ROW_KEYS
    if unknown:
        raise ValueError(f"{at}: unknown keys {sorted(unknown)}; a row has {sorted(ROW_KEYS)}")
    if "match" not in entries:
        raise ValueError(f"{at}: missing match")
    match = _match(entries["match"], at)
    reason = read_reason(entries["reason"], at) if "reason" in entries else None
    activity, role = _declares(entries.get("declares"), at, reason is not None, declared)
    if "seeded_from" in entries:
        read_seeded_from(entries["seeded_from"], at)
    return Row(id, match, activity, role, reason)


def _match(node: yaml.Node, at: str) -> dict[str, frozenset[Value]]:
    entries = mapping(node, f"{at} match")
    unknown = set(entries) - set(PARTS)
    if unknown:
        raise ValueError(f"{at}: match has unknown parts {sorted(unknown)}; the parts are {list(PARTS)}")
    if "source_type" not in entries:
        raise ValueError(f"{at}: match names no source_type — every row says which kind of source it reads")
    match = {part: _values(value_node, f"{at} match {part}") for part, value_node in entries.items()}
    stray = match["source_type"] - LINEAGE_SOURCE_TYPES
    if stray:
        raise ValueError(
            f"{at}: match source_type {sorted(stray, key=_sort_key)} is not a lineage source "
            f"({sorted(LINEAGE_SOURCE_TYPES)})"
        )
    return match


def _values(node: yaml.Node, at: str) -> frozenset[Value]:
    """A part's values: one string or null, or a non-empty list of those, given once each."""
    items = node.value if isinstance(node, yaml.SequenceNode) else [node]
    if not items:
        raise ValueError(f"{at}: an empty list matches nothing (line {node.start_mark.line + 1})")
    values: list[Value] = []
    for item in items:
        if not isinstance(item, yaml.ScalarNode) or item.tag not in (STR_TAG, NULL_TAG):
            raise ValueError(f"{at}: expected a string or null, got {kind(item)} (line {item.start_mark.line + 1})")
        values.append(None if item.tag == NULL_TAG else item.value)
    if len(set(values)) != len(values):
        raise ValueError(f"{at}: a value is listed twice (line {node.start_mark.line + 1})")
    return frozenset(values)


def _declares(
    node: yaml.Node | None, at: str, authored: bool, declared: Mapping[str, Declared]
) -> tuple[str | None, str | None]:
    if node is None:
        if authored:
            raise ValueError(f"{at}: has a reason but no `declares` — an authored row names its activity and role")
        return None, None
    if not authored:
        raise ValueError(f"{at}: declares something but has no reason — a seeded row declares nothing (contract 3.11)")
    entries = mapping(node, f"{at} declares")
    if set(entries) != DECLARES_KEYS:
        raise ValueError(f"{at}: declares {sorted(entries)}; it declares exactly {sorted(DECLARES_KEYS)}")
    activity = scalar(entries["activity"], f"{at} declares activity")
    role = scalar(entries["role"], f"{at} declares role")
    if activity not in declared:
        raise ValueError(f"{at}: declares activity {activity!r}, which activities.yaml does not declare")
    require_writable(activity, at, declared)
    roles = [i.role for i in declared[activity].inputs]
    if role not in roles:
        raise ValueError(f"{at}: declares role {role!r}, which {activity} does not declare; its roles are {roles}")
    return activity, role


# --- lines ------------------------------------------------------------------------


@dataclass(frozen=True)
class KeyedLine:
    """One lineage line and its key, with its file's envelope and the generation directory it was read from."""

    key: LineKey
    line: LineageRow
    envelope: EvidenceFileEnvelope
    generation: str

    @property
    def dataset(self) -> str:
        return str(self.envelope.source.dataset)


def _slot_identity(envelope: EvidenceFileEnvelope) -> tuple:
    """What a lineage file and a slot file must share for the slot file's data_type to speak for its files."""
    s = envelope.source
    return (s.repository, s.dataset, s.table, str(envelope.source_type), str(envelope.target_key))


def _data_types(slot_paths: list[Path]) -> dict[str, str]:
    """The raw ``data_type`` value per target key value in these slot files, for the files given exactly one.

    A file the table gives two distinct values (a table-name rule and a column both
    routed to ``data_type``) is left out, so its lines key with no data type and reach
    the queue; a key takes one value, and choosing between two would be a guess.
    """
    found: dict[str, str] = {}
    ambiguous: set[str] = set()
    for path in slot_paths:
        for entry in iter_evidence(path):
            if entry.field != "data_type":
                continue
            if found.setdefault(entry.target_key_value, entry.raw_value) != entry.raw_value:
                ambiguous.add(entry.target_key_value)
    return {target: raw for target, raw in found.items() if target not in ambiguous}


def lineage_paths(lineage_root: Path, datasets: Iterable[str] | None = None) -> list[Path]:
    """The current lineage files of the latest catalog, restricted to the envelopes naming one of ``datasets``.

    Only the latest catalog is current: once a newer catalog is imported beside an older
    one, the older is history, kept on disk and never read, as ``discover`` treats an
    older generation of one dataset. The latest is the catalog (the envelope's target
    ``version``) holding the newest generation stamp, which sorts as time; a catalog's
    name does not (``anvil9`` against ``anvil16``, dev's ``anvil``).
    """
    by_catalog: dict[str, list[tuple[Path, str | None]]] = {}
    for path in discover(lineage_root):
        envelope = read_lineage_envelope(path)
        by_catalog.setdefault(str(envelope.target.version), []).append((path, envelope.source.dataset))
    if not by_catalog:
        return []
    # The latest catalog is chosen over every dataset first, so a dataset the latest
    # catalog lacks is not read from an older one.
    latest = max(by_catalog, key=lambda catalog: max(generation_stamp(p) for p, _ in by_catalog[catalog]))
    wanted = set(datasets) if datasets is not None else None
    return [p for p, dataset in by_catalog[latest] if wanted is None or dataset in wanted]


def generation_stamp(path: Path) -> str:
    """The generation stamp a file sits under, or "" for a file outside the generation layout."""
    return path.parent.name if is_generation(path.parent.name) else ""


def keyed_lines(lineage_root: Path, evidence_root: Path, paths: Iterable[Path]) -> Iterator[KeyedLine]:
    """Every line of the lineage files ``paths`` (under ``lineage_root``) with its key, in file order.

    ``paths`` are one catalog, as :func:`lineage_paths` returns them: paths whose
    envelopes name more than one target ``version`` raise before any line is read. Only
    slot files of that same catalog are joined for the data types.
    """
    envelopes = [(path, read_lineage_envelope(path)) for path in paths]
    catalogs = sorted({str(envelope.target.version) for _, envelope in envelopes})
    if len(catalogs) > 1:
        raise ValueError(f"{_WHERE}: the lineage names {len(catalogs)} catalogs, {catalogs}; it is read one at a time")
    slot_files: dict[tuple, list[Path]] = {}
    for path in discover(evidence_root):
        slot = read_envelope(path)
        if catalogs and str(slot.target.version) == catalogs[0]:
            slot_files.setdefault(_slot_identity(slot), []).append(path)
    for path, envelope in envelopes:
        types = _data_types(slot_files.get(_slot_identity(envelope), []))
        generation = generation_name(lineage_root, path)
        for line in iter_lineage(path):
            parent_type = (
                types.get(line.parent)
                if line.parent is not None and str(line.parent_key_type) == str(envelope.target_key)
                else None
            )
            key = (
                str(envelope.source_type),
                envelope.source.table,
                line.raw_activity,
                line.child_column,
                line.parent_column,
                types.get(line.target_key_value),
                parent_type,
            )
            yield KeyedLine(key, line, envelope, generation)


# --- seeding ----------------------------------------------------------------------


@dataclass(frozen=True)
class SeedResult:
    files_scanned: int
    lines_scanned: int
    rows_added: tuple[str, ...]


def row_id(key: LineKey) -> str:
    """The id a seeded row is minted with: ``activity.`` and the tokens of every part but the source type."""
    tokens = [token for value in key[1:] if value for token in name_tokens(value)]
    return ID_PREFIX + ("_".join(tokens) or "_")


def seed(
    table_path: Path,
    lineage_root: Path = DEFAULT_LINEAGE_EVIDENCE_ROOT,
    evidence_root: Path = DEFAULT_SOURCE_EVIDENCE_ROOT,
    datasets: Iterable[str] | None = None,
    activities: Mapping[str, Declared] | None = None,
) -> SeedResult:
    """Append one seeded row per key the lineage carries and no row matches.

    A new row names all seven parts, has no reason, and records the generation
    directories its key was seen in. A rerun over the same evidence adds nothing. The
    table is written beside itself and renamed over only once the result loads;
    otherwise it is left as it was and this raises.
    """
    text = table_path.read_text(encoding="utf-8")
    table = load_activity_map(table_path, activities)
    seen: dict[LineKey, list[str]] = {}
    paths = lineage_paths(lineage_root, datasets)
    lines = 0
    for keyed in keyed_lines(lineage_root, evidence_root, paths):
        lines += 1
        if table.select(keyed.key) is not None:
            continue
        where = seen.setdefault(keyed.key, [])
        if keyed.generation not in where:
            where.append(keyed.generation)
    if not seen:
        return SeedResult(len(paths), lines, ())
    ids = {row.id for row in table.rows}
    indent = row_indent(text)
    new_text = open_rows(text, _WHERE, not table.rows)
    added: list[str] = []
    for key, where in sorted(seen.items(), key=lambda kv: tuple(_sort_key(v) for v in kv[0])):
        id = fresh_id(row_id(key), repr(key), ids, _WHERE)
        ids.add(id)
        added.append(id)
        new_text += row_text({"id": id, "match": dict(zip(PARTS, key, strict=True)), "seeded_from": where}, indent)
    replace_checked(
        table_path,
        new_text,
        lambda p: len(load_activity_map(p, activities).rows),
        len(table.rows) + len(added),
        _WHERE,
    )
    return SeedResult(len(paths), lines, tuple(added))


# --- the review queue ---------------------------------------------------------------


@dataclass(frozen=True)
class QueueEntry:
    """One key no authored row reads: its parts, the lines carrying it, the datasets they came from."""

    key: LineKey
    lines: int
    datasets: tuple[str, ...]
    row_id: str | None
    """The seeded row it selects, or None where no row matches."""

    @property
    def source_type(self) -> str:
        return str(self.key[0])


@dataclass(frozen=True)
class MappingLine:
    """One authored row and the lineage lines it matched."""

    row: Row
    lines: int


@dataclass(frozen=True)
class Review:
    queue: list[QueueEntry]
    mappings: list[MappingLine]


def review(
    table: ActivityMap,
    lineage_root: Path = DEFAULT_LINEAGE_EVIDENCE_ROOT,
    evidence_root: Path = DEFAULT_SOURCE_EVIDENCE_ROOT,
    datasets: Iterable[str] | None = None,
) -> Review:
    """Every key whose selected row is not authored, most lines first; and every authored row with its lines."""
    counts: dict[LineKey, int] = {}
    in_datasets: dict[LineKey, set[str]] = {}
    matched: dict[Row, int] = {row: 0 for row in table.rows if row.authored}
    for keyed in keyed_lines(lineage_root, evidence_root, lineage_paths(lineage_root, datasets)):
        row = table.select(keyed.key)
        if row is not None and row.authored:
            matched[row] += 1
            continue
        counts[keyed.key] = counts.get(keyed.key, 0) + 1
        in_datasets.setdefault(keyed.key, set()).add(keyed.dataset)
    entries = []
    for key, count in counts.items():
        row = table.select(key)
        entries.append(QueueEntry(key, count, tuple(sorted(in_datasets[key])), None if row is None else row.id))
    entries.sort(key=lambda e: (-e.lines, tuple(_sort_key(v) for v in e.key)))
    mappings = [MappingLine(row, n) for row, n in matched.items()]
    mappings.sort(key=lambda m: (-m.lines, m.row.id))
    return Review(entries, mappings)


# The queue's groups, one per lineage source type, with its heading.
QUEUE_GROUP_TEXT = {
    SOURCE_REPOSITORY_ACTIVITY: ("Repository activity", "the repository's own record of each step"),
    SOURCE_REPOSITORY_METADATA: ("Submitter", "the submitter tables"),
}


def queue_groups(entries: list[QueueEntry]) -> list[tuple[str, str, list[QueueEntry]]]:
    """``(label, description, entries)`` per lineage source type, in :data:`QUEUE_GROUP_TEXT` order."""
    return [
        (label, text, [e for e in entries if e.source_type == st]) for st, (label, text) in QUEUE_GROUP_TEXT.items()
    ]


def _part(e_key: LineKey, part: str) -> str:
    value = e_key[PARTS.index(part)]
    return "" if value is None else repr(value)


QUEUE_COLUMNS = (
    ReportColumn("lines", "num", lambda e: f"{e.lines:,}"),
    *(ReportColumn(part, "catalog", lambda e, part=part: _part(e.key, part)) for part in PARTS[1:]),
    ReportColumn("datasets", "catalog", lambda e: ", ".join(e.datasets)),
    ReportColumn("rule it would use", "plain", lambda e: e.row_id or "—"),
)


def describe_match(row: Row) -> str:
    """A row's match parts in order, each part's values as written (``none`` for null), for a report."""
    return "; ".join(
        f"{part}: " + " · ".join(repr(v) if v is not None else "none" for v in sorted(row.match[part], key=_sort_key))
        for part in PARTS
        if part in row.match
    )


MAPPING_COLUMNS = (
    ReportColumn("lines", "num", lambda m: f"{m.lines:,}"),
    ReportColumn("rule", "plain", lambda m: m.row.id),
    ReportColumn("matches", "catalog", lambda m: describe_match(m.row)),
    ReportColumn("declares", "plain", lambda m: f"{m.row.activity} / {m.row.role}"),
    ReportColumn("reason", "plain", lambda m: " ".join((m.row.reason or "").split())),
)
HEADING = "Lineage: what each step is (the activity map)"
MAPPINGS_HEADING = "Authored activity mappings"


def queue_intro(entries: list[QueueEntry], datasets: Iterable[str] | None = None) -> str:
    """The sentence above the lineage queue, in plain text; each renderer marks it up."""
    scope = f" for {', '.join(sorted(datasets))} only" if datasets else ""
    return (
        "Lineage lines (a file made from a parent) whose step no authored activity-map row names yet, so reconcile "
        "cannot say what the parent passes on. One entry per key: the source's table, its words for the step, the "
        "columns the child and parent came from, and the data type the same table gives each. "
        f"{len(entries):,} keys listed, from the lineage evidence{scope}."
    )


def render_section(entries: list[QueueEntry], mappings: list[MappingLine], datasets=None) -> list[str]:
    """The lineage queue and its authored mappings as markdown lines, for the review queue report."""
    lines = ["", f"## {HEADING}", "", queue_intro(entries, datasets)]
    for label, description, group in queue_groups(entries):
        lines += ["", f"### {label}: {description}", ""]
        lines += md_rows(QUEUE_COLUMNS, group) if group else ["No unreviewed steps."]
    lines += ["", f"### {MAPPINGS_HEADING}", ""]
    lines += md_rows(MAPPING_COLUMNS, mappings) if mappings else ["No authored rows."]
    return lines


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``scripts/activity_map.py``: ``seed`` appends seeded rows, ``queue`` prints the queue."""
    parser = argparse.ArgumentParser(description="The activity translation table: seed it, or list its queue")
    parser.add_argument("--table", type=Path, default=None, help="Table file (default: the bundled activity_map.yaml)")
    parser.add_argument("--lineage-root", type=Path, default=DEFAULT_LINEAGE_EVIDENCE_ROOT)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_SOURCE_EVIDENCE_ROOT)
    parser.add_argument("--dataset", action="append", help="Only this dataset's lineage (repeatable)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="Append a seeded row for every lineage key no row matches")
    sub.add_parser("queue", help="Print every lineage key whose selected row is not authored")
    args = parser.parse_args(argv)
    table_path = args.table if args.table is not None else Path(str(default_activity_map_resource()))
    if args.command == "seed":
        result = seed(table_path, args.lineage_root, args.evidence_root, args.dataset)
        print(
            f"Scanned {result.files_scanned} lineage files, {result.lines_scanned:,} lines; "
            f"added {len(result.rows_added)} seeded rows to {table_path}",
            file=sys.stderr,
        )
        for id in result.rows_added:
            print(f"  {id}", file=sys.stderr)
        return 0
    found = review(load_activity_map(table_path), args.lineage_root, args.evidence_root, args.dataset)
    print("\n".join(render_section(found.queue, found.mappings, args.dataset)).lstrip("\n"))
    return 0
