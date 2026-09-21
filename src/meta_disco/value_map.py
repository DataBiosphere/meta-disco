"""The value translation table: raw source values to vocabulary terms (#414).

An importer writes ``(slot, raw_value)`` and stops (contract 1.2-1.4). This table is
the one step between that observation and a claim: a lookup from ``(slot, normalized
raw_value)`` to a **declaration**, applied per evidence line. It shares nothing with
``unified_rules.yaml``'s engine — no tiers, no ``when``/``then`` over file attributes —
and a row qualifies as a rule only in contract 3.8's sense: it makes a claim and is
cited by it.

**The file** is ``rules/value_map.yaml``, a mapping whose one key is ``rows``, a list::

    rows:
      - id: platform.revio
        match: {slot: platform, value: Revio, alternates: [REVIO]}
        scope: {source: anvil, dataset: AnVIL_HPRC_R2}   # optional; a source, or a source and dataset
        declares: {platform: PACBIO}
        reason: PacBio's current long-read instrument; the source spells it two ways.
        seeded_from: [anvil/anvil15/AnVIL_HPRC_R2/20260920T175642Z]

A row is **authored** when it carries a ``reason`` and **seeded** otherwise (3.11).
Only an authored row may carry ``declares``; a seeded one declares nothing whatever it
spells, and an authored row may declare ``{}`` to rule that a value means nothing here
(the ``bam``-in-a-data_type-column case). ``declares`` names at most one pair per
slot, each a term of *that slot's* vocabulary or one of the two rule-authorable
statuses (3.9), and may name slots other than the match slot (3.10). ``value`` is a
string or, for a list-valued cell, a list of strings; ``alternates`` are further
spellings of the same key. No row carries a table or column name (3.4): the loader
refuses the keys outright.

**Matching** (3.5) casefolds and strips, and nothing more; ``test_value_map`` checks
that this cannot merge two terms of any slot's vocabulary. A cell whose raw value is a
JSON array of strings is one fact and matches as the **set** of its elements, so
``["A", "B"]`` and ``["B", "A"]`` share a key and ``["A"]`` matches the row for ``A``.
Every key is therefore a frozenset. Nothing matches by similarity.

**Selection** (3.12) takes the narrowest of the row scoped to the evidence's source
and dataset, the row scoped to its source, and the unscoped row, and returns it whole.
Two rows keyed the same on one slot at one scope, alternates included, cannot load.
Two rows with different keys declaring the same slot can: whether they collide depends
on which cells a file has, which is not knowable at load (4.8).

**Nothing in a classification run reads this module.** :func:`claims_from` exists for
the reconcile stage (#432) and for the tests; the seeder and the review queue read
evidence files, never a run's output. Both go through
``source_evidence.iter_evidence`` one line at a time (#374).

**The seeder appends and never rewrites.** It loads the table, walks the evidence,
and appends one seeded row per ``(slot, key)`` no row of any scope matches, each
recording the generation directories it was seen in. An authored row is untouched
byte for byte; ``rows`` is the document's only key, so an item appended at the end
extends it. After appending it reloads the file and restores the original bytes if
the reload fails.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import yaml

from .models import CLASSIFICATION_FIELDS, NOT_APPLICABLE, NOT_CLASSIFIED
from .rule_engine import make_claim
from .rule_loader import get_unified_rules
from .schema_vocab import dimension_values
from .source_evidence import EvidenceEntry, discover, iter_evidence, read_envelope

Key = frozenset[str]
"""A normalized match key: one element for a scalar cell, several for a list cell."""

STATUSES = frozenset({NOT_APPLICABLE, NOT_CLASSIFIED})
"""The two statuses a row may declare in place of a term (contract 3.6)."""

ROW_KEYS = frozenset({"id", "match", "scope", "declares", "reason", "seeded_from"})
MATCH_KEYS = frozenset({"slot", "value", "alternates"})
SCOPE_KEYS = frozenset({"source", "dataset"})
_FORBIDDEN_ROW_KEYS = frozenset({"table", "column", "notes"})
_FIELDS = frozenset(CLASSIFICATION_FIELDS)
_WHERE = "value map"
_STR_TAG = "tag:yaml.org,2002:str"
_NULL_TAG = "tag:yaml.org,2002:null"
_SLUG = re.compile(r"[^a-z0-9]+")
_SET_JOIN = "+"
_SCOPE_MARK = "@"


def default_value_map_resource():
    """The bundled table, as package data beside the rule set."""
    return files(f"{__package__}.rules") / "value_map.yaml"


# --- keys ------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Casefold and strip. The whole of the normalizer, on purpose (contract 3.5)."""
    return text.casefold().strip()


def match_key(raw_value: str | list[str]) -> Key:
    """The key a raw value matches on: the normalized set of a list cell's elements, else a one-element set.

    A string is parsed as a list only when it is a JSON array of strings, which is how
    the AnVIL importer transcribes a list-valued cell (its JSON, verbatim). Anything
    else is one scalar, brackets included.
    """
    if isinstance(raw_value, list):
        return frozenset(normalize(e) for e in raw_value)
    parsed = _json_string_list(raw_value)
    return frozenset(normalize(e) for e in parsed) if parsed is not None else frozenset({normalize(raw_value)})


def _json_string_list(text: str) -> list[str] | None:
    if not text.lstrip().startswith("["):
        return None
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if isinstance(parsed, list) and all(isinstance(e, str) for e in parsed):
        return parsed
    return None


def row_id(slot: str, key: Key, scope: Scope | None = None) -> str:
    """The id a seeded row is minted with: ``<slot>.<slug>``, set elements sorted and joined, scope appended."""
    slug = _SET_JOIN.join(_SLUG.sub("_", e).strip("_") or "_" for e in sorted(key))
    if scope is not None:
        slug += _SCOPE_MARK + scope.source + ("" if scope.dataset is None else f".{scope.dataset}")
    return f"{slot}.{slug}"


# --- rows -------------------------------------------------------------------------


@dataclass(frozen=True)
class Scope:
    """A source, or a source and dataset; never a dataset alone (contract 3.12)."""

    source: str
    dataset: str | None = None


@dataclass(frozen=True, eq=False)
class Row:
    """One row of the table, as loaded. ``value`` and ``alternates`` are verbatim; ``keys`` are normalized.

    Identity equality: a loaded row is one object the index and the selection share, and
    ``declares`` is a mapping, which a field-wise hash could not take.
    """

    id: str
    slot: str
    value: str | tuple[str, ...]
    alternates: tuple[str | tuple[str, ...], ...]
    scope: Scope | None
    declares: Mapping[str, str]
    reason: str | None
    seeded_from: tuple[str, ...]

    @property
    def authored(self) -> bool:
        return self.reason is not None

    @property
    def keys(self) -> frozenset[Key]:
        """Every key this row matches on: its value and each alternate."""
        return frozenset(match_key(_as_key_input(v)) for v in (self.value, *self.alternates))


def _as_key_input(value: str | tuple[str, ...]) -> str | list[str]:
    return list(value) if isinstance(value, tuple) else value


@dataclass(frozen=True)
class ValueMap:
    """A loaded table and its selection index."""

    rows: tuple[Row, ...]
    _index: dict[tuple[str, Key, Scope | None], Row] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        for row in self.rows:
            for key in row.keys:
                self._index[(row.slot, key, row.scope)] = row

    def select(self, slot: str, raw_value: str, source: str | None, dataset: str | None) -> Row | None:
        """The narrowest row matching this evidence, or None. Its declaration is taken whole (3.12)."""
        key = match_key(raw_value)
        candidates: list[Scope | None] = [None]
        if source is not None:
            candidates.insert(0, Scope(source))
            if dataset is not None:
                candidates.insert(0, Scope(source, dataset))
        for scope in candidates:
            row = self._index.get((slot, key, scope))
            if row is not None:
                return row
        return None

    def keyed(self) -> frozenset[tuple[str, Key]]:
        """Every ``(slot, key)`` some row of any scope matches — what the seeder does not mint again."""
        return frozenset((row.slot, key) for row in self.rows for key in row.keys)

    def by_id(self, id: str) -> Row:
        return next(row for row in self.rows if row.id == id)


# --- loading ----------------------------------------------------------------------


def load_value_map(path: Path | None = None) -> ValueMap:
    """Load and check the table; the bundled one by default.

    The checks the contract puts on a row are here, bar 3.5's bound on the normalizer,
    which is a property of :func:`normalize` that ``test_value_map`` checks. The first
    violation raises ``ValueError`` naming the row (by id where it has one, else by position): unknown
    or forbidden keys, a duplicate key inside a row, a duplicate id or one the rule set
    already uses, a malformed match or scope, ``declares`` on a seeded row, a declared
    term outside its slot's vocabulary on an authored row, and two rows keyed the same
    on one slot at one scope. A seeded row's *match* value is never checked against
    anything — it is the source's spelling (3.11).
    """
    text = path.read_text(encoding="utf-8") if path is not None else default_value_map_resource().read_text()
    return ValueMap(rows=tuple(_rows(_parse(text))))


def _parse(text: str) -> list[yaml.Node]:
    """The row nodes of the document, checked down to the top-level shape."""
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    if root is None:
        raise ValueError(f"{_WHERE}: the document is empty; it needs a `rows` key")
    document = _mapping(root, _WHERE)
    if set(document) != {"rows"}:
        raise ValueError(f"{_WHERE}: top-level keys are {sorted(document)}, expected exactly ['rows']")
    rows_node = document["rows"]
    if rows_node.tag == _NULL_TAG:
        return []
    if not isinstance(rows_node, yaml.SequenceNode):
        raise ValueError(f"{_WHERE}: `rows` is not a list (line {rows_node.start_mark.line + 1})")
    return list(rows_node.value)


def _mapping(node: yaml.Node, at: str) -> dict[str, yaml.Node]:
    """A mapping node's entries by string key, refusing anything else and any key given twice."""
    if not isinstance(node, yaml.MappingNode):
        raise ValueError(f"{at}: expected a mapping, got {_kind(node)} (line {node.start_mark.line + 1})")
    entries: dict[str, yaml.Node] = {}
    for key_node, value_node in node.value:
        key = _scalar(key_node, at)
        if key in entries:
            raise ValueError(f"{at}: key {key!r} given twice (line {key_node.start_mark.line + 1})")
        entries[key] = value_node
    return entries


def _scalar(node: yaml.Node, at: str) -> str:
    if not isinstance(node, yaml.ScalarNode) or node.tag != _STR_TAG:
        raise ValueError(f"{at}: expected a string, got {_kind(node)} (line {node.start_mark.line + 1})")
    return node.value


def _string_or_list(node: yaml.Node, at: str) -> str | tuple[str, ...]:
    if isinstance(node, yaml.SequenceNode):
        return tuple(_scalar(item, at) for item in node.value)
    return _scalar(node, at)


def _kind(node: yaml.Node) -> str:
    if isinstance(node, yaml.ScalarNode):
        return f"{node.tag.rsplit(':', 1)[-1]} {node.value!r}"
    return type(node).__name__.replace("Node", "").lower()


def _rows(nodes: list[yaml.Node]) -> Iterator[Row]:
    rule_ids = {rule.id for rule in get_unified_rules().rules}
    seen_ids: dict[str, int] = {}
    seen_keys: dict[tuple[str, Key, Scope | None], str] = {}
    for n, node in enumerate(nodes, start=1):
        row = _row(node, n)
        if row.id in seen_ids:
            raise ValueError(f"{_WHERE}: row {n} repeats id {row.id!r} (first at row {seen_ids[row.id]})")
        if row.id in rule_ids:
            raise ValueError(
                f"{_WHERE}: row {row.id!r} has the id of a rule in unified_rules.yaml — "
                "a claim cites either by rule_id, so the two sets share one namespace"
            )
        seen_ids[row.id] = n
        for key in row.keys:
            at = (row.slot, key, row.scope)
            if at in seen_keys:
                raise ValueError(
                    f"{_WHERE}: rows {seen_keys[at]!r} and {row.id!r} both match {sorted(key)} on {row.slot} "
                    f"at scope {_scope_text(row.scope)} — one row per key at a scope, alternates included"
                )
            seen_keys[at] = row.id
        yield row


def _row(node: yaml.Node, n: int) -> Row:
    at = f"{_WHERE} row {n}"
    entries = _mapping(node, at)
    if "id" in entries:
        at = f"{_WHERE} row {_scalar(entries['id'], at)!r}"
    forbidden = _FORBIDDEN_ROW_KEYS & set(entries)
    if forbidden:
        raise ValueError(
            f"{at}: carries {sorted(forbidden)} — a row is slot and value only; table and column belong to the "
            "slot map (contract 3.4), and the reason for a ruling is `reason`"
        )
    unknown = set(entries) - ROW_KEYS
    if unknown:
        raise ValueError(f"{at}: unknown keys {sorted(unknown)}; a row has {sorted(ROW_KEYS)}")
    missing = {"id", "match"} - set(entries)
    if missing:
        raise ValueError(f"{at}: missing {sorted(missing)}")
    id = _scalar(entries["id"], at)
    if not id.strip():
        raise ValueError(f"{at}: id is empty")
    slot, value, alternates = _match(entries["match"], at)
    scope = _scope(entries["scope"], at) if "scope" in entries else None
    reason = _reason(entries["reason"], at) if "reason" in entries else None
    declares = _declares(entries.get("declares"), at, reason is not None)
    seeded_from = _seeded_from(entries["seeded_from"], at) if "seeded_from" in entries else ()
    return Row(
        id=id,
        slot=slot,
        value=value,
        alternates=alternates,
        scope=scope,
        declares=declares,
        reason=reason,
        seeded_from=seeded_from,
    )


def _match(node: yaml.Node, at: str) -> tuple[str, str | tuple[str, ...], tuple[str | tuple[str, ...], ...]]:
    entries = _mapping(node, f"{at} match")
    unknown = set(entries) - MATCH_KEYS
    if unknown:
        raise ValueError(f"{at}: match has unknown keys {sorted(unknown)}; it has {sorted(MATCH_KEYS)}")
    if {"slot", "value"} - set(entries):
        raise ValueError(f"{at}: match needs `slot` and `value`")
    slot = _scalar(entries["slot"], at)
    if slot not in _FIELDS:
        raise ValueError(f"{at}: match slot {slot!r} is not one of {sorted(_FIELDS)}")
    value = _string_or_list(entries["value"], f"{at} match value")
    alternates: tuple[str | tuple[str, ...], ...] = ()
    if "alternates" in entries:
        alt_node = entries["alternates"]
        if not isinstance(alt_node, yaml.SequenceNode):
            raise ValueError(f"{at}: match alternates is not a list (line {alt_node.start_mark.line + 1})")
        alternates = tuple(_string_or_list(item, f"{at} match alternates") for item in alt_node.value)
    return slot, value, alternates


def _scope(node: yaml.Node, at: str) -> Scope:
    entries = _mapping(node, f"{at} scope")
    unknown = set(entries) - SCOPE_KEYS
    if unknown:
        raise ValueError(f"{at}: scope has unknown keys {sorted(unknown)}; it is a source, or a source and dataset")
    if "source" not in entries:
        raise ValueError(f"{at}: scope names a dataset with no source — a dataset belongs to a source (contract 3.12)")
    source = _scalar(entries["source"], at)
    dataset = _scalar(entries["dataset"], at) if "dataset" in entries else None
    return Scope(source, dataset)


def _reason(node: yaml.Node, at: str) -> str:
    reason = _scalar(node, f"{at} reason")
    if not reason.strip():
        raise ValueError(f"{at}: reason is empty — an authored row records why; a seeded row has no `reason` key")
    return reason


def _declares(node: yaml.Node | None, at: str, authored: bool) -> Mapping[str, str]:
    if node is None:
        return {}
    if not authored:
        raise ValueError(f"{at}: declares something but has no reason — a seeded row declares nothing (contract 3.11)")
    entries = _mapping(node, f"{at} declares")
    declares: dict[str, str] = {}
    for slot, value_node in entries.items():
        if slot not in _FIELDS:
            raise ValueError(f"{at}: declares {slot!r}, which is not a slot; slots are {sorted(_FIELDS)}")
        term = _scalar(value_node, f"{at} declares {slot}")
        if term not in STATUSES and term not in dimension_values(slot):
            raise ValueError(
                f"{at}: declares {slot}: {term!r}, which is not a term of {slot}'s vocabulary "
                f"nor one of {sorted(STATUSES)}"
            )
        declares[slot] = term
    return declares


def _seeded_from(node: yaml.Node, at: str) -> tuple[str, ...]:
    if not isinstance(node, yaml.SequenceNode):
        raise ValueError(f"{at}: seeded_from is not a list (line {node.start_mark.line + 1})")
    return tuple(_scalar(item, f"{at} seeded_from") for item in node.value)


def _scope_text(scope: Scope | None) -> str:
    if scope is None:
        return "(unscoped)"
    return scope.source if scope.dataset is None else f"{scope.source}/{scope.dataset}"


# --- claims -----------------------------------------------------------------------


def claims_from(entry: EvidenceEntry, source_type: str, table: ValueMap) -> list[tuple[str, dict]]:
    """The claims one evidence line makes: ``(slot, claim)`` per declared pair of its selected row, else nothing.

    Selection reads the line's slot, raw value and provenance (3.7). A seeded row, an
    authored row declaring nothing, or no row at all yields ``[]``. Each claim goes
    through ``make_claim`` citing the row's id, carrying the verbatim raw value and the
    line's :class:`ClaimSource` — source, dataset, table and column — so two claims on
    one slot from two cells of one file can be told apart afterwards (4.8). Nothing
    here compares, merges or ranks: that is reconcile's (#432). ``source_type`` is the
    envelope's, which the line does not carry.
    """
    row = table.select(entry.field, entry.raw_value, entry.source.name, entry.source.dataset)
    if row is None or not row.authored:
        return []
    claims = []
    for slot, declared in row.declares.items():
        is_status = declared in STATUSES
        claim = make_claim(
            source_type=source_type,
            rule_id=row.id,
            value=None if is_status else declared,
            status=declared if is_status else None,
            source=entry.source,
            raw_value=entry.raw_value,
        )
        claims.append((slot, claim))
    return claims


# --- evidence walks -----------------------------------------------------------------


def _current_files(evidence_root: Path, datasets: Iterable[str] | None) -> list[tuple[Path, str]]:
    """Each current evidence file with its envelope's source type, restricted to ``datasets`` when given."""
    wanted = None if datasets is None else set(datasets)
    found = []
    for path in discover(evidence_root):
        envelope = read_envelope(path)
        if wanted is None or envelope.source.dataset in wanted:
            found.append((path, envelope.source_type))
    return found


@dataclass(frozen=True)
class SeedResult:
    files_scanned: int
    lines_scanned: int
    rows_added: tuple[str, ...]


def seed(table_path: Path, evidence_root: Path, datasets: Iterable[str] | None = None) -> SeedResult:
    """Append one seeded row per ``(slot, key)`` the evidence carries and no row matches.

    A key any row of any scope already matches is left alone, so a rerun over the same
    evidence adds nothing and an authored row is never touched. Each new row is
    unscoped, has no reason, spells the value as the first line that carried it did
    (a list cell as a list), lists every other spelling that normalized to the same
    key as an alternate, and records the generation directories it was seen in.
    Rows are appended in ``(slot, key)`` order after the last existing row, at the
    existing rows' indentation, then the file is reloaded; a reload failure restores the
    original bytes and raises.
    """
    original = table_path.read_bytes()
    text = original.decode("utf-8")
    table = load_value_map(table_path)
    keyed = table.keyed()
    seen: dict[tuple[str, Key], _Seen] = {}
    files_scanned = lines_scanned = 0
    for path, _ in _current_files(evidence_root, datasets):
        files_scanned += 1
        where = _generation_name(evidence_root, path)
        for entry in iter_evidence(path):
            lines_scanned += 1
            key = (entry.field, match_key(entry.raw_value))
            if key in keyed:
                continue
            parsed = _json_string_list(entry.raw_value)
            spelling = parsed if parsed is not None else entry.raw_value
            if key not in seen:
                seen[key] = _Seen(spelling, [], [where])
            else:
                seen[key].add(spelling, where)
    if not seen:
        return SeedResult(files_scanned, lines_scanned, ())
    ids = {row.id for row in table.rows}
    indent = _row_indent(text)
    added: list[str] = []
    block = []
    for (slot, key), found in sorted(seen.items(), key=lambda kv: (kv[0][0], sorted(kv[0][1]))):
        id = _fresh_id(row_id(slot, key), ids)
        ids.add(id)
        added.append(id)
        block.append(_row_text(id, slot, found, indent))
    new_text = text if text.endswith("\n") or not text else text + "\n"
    table_path.write_text(new_text + "".join(block), encoding="utf-8")
    try:
        reloaded = load_value_map(table_path)
        if len(reloaded.rows) != len(table.rows) + len(added):
            raise ValueError(f"reloaded {len(reloaded.rows)} rows, expected {len(table.rows) + len(added)}")
    except Exception as exc:
        table_path.write_bytes(original)
        raise ValueError(
            f"{_WHERE}: seeding {table_path} produced a table that does not load; restored: {exc}"
        ) from exc
    return SeedResult(files_scanned, lines_scanned, tuple(added))


def _generation_name(root: Path, path: Path) -> str:
    try:
        return path.parent.relative_to(root).as_posix()
    except ValueError:
        return path.parent.as_posix()


def _row_indent(text: str) -> str:
    """The indentation of the existing row items, or two spaces where there are none."""
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    rows_node = _mapping(root, _WHERE)["rows"]
    if isinstance(rows_node, yaml.SequenceNode) and rows_node.value:
        if rows_node.flow_style:
            raise ValueError(f"{_WHERE}: `rows` is a flow-style list ([...]); the seeder appends block items")
        # A block sequence's own mark is at its first dash; an item's is at its first key.
        return " " * rows_node.start_mark.column
    return "  "


def _fresh_id(candidate: str, taken: set[str]) -> str:
    """``candidate``, or the first ``candidate_N`` not taken: two values can slug alike (``a-b`` and ``a_b``)."""
    if candidate not in taken:
        return candidate
    n = 2
    while f"{candidate}_{n}" in taken:
        n += 1
    return f"{candidate}_{n}"


@dataclass
class _Seen:
    """One key the seeder will mint: the first spelling seen, every other spelling, every generation it was in."""

    value: str | list[str]
    alternates: list[str | list[str]]
    seeded_from: list[str]

    def add(self, spelling: str | list[str], where: str) -> None:
        if spelling != self.value and spelling not in self.alternates:
            self.alternates.append(spelling)
        if where not in self.seeded_from:
            self.seeded_from.append(where)


def _row_text(id: str, slot: str, found: _Seen, indent: str) -> str:
    inner = indent + "  "
    match = f"slot: {slot}, value: {_yaml_value(found.value)}"
    if found.alternates:
        match += f", alternates: [{', '.join(_yaml_value(a) for a in found.alternates)}]"
    lines = [
        f"{indent}- id: {_yaml_scalar(id)}",
        f"{inner}match: {{{match}}}",
        f"{inner}seeded_from: [{', '.join(_yaml_scalar(s) for s in found.seeded_from)}]",
    ]
    return "\n".join(lines) + "\n"


def _yaml_scalar(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def _yaml_value(value: str | list[str]) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_yaml_scalar(e) for e in value) + "]"
    return _yaml_scalar(value)


@dataclass(frozen=True)
class QueueEntry:
    """One unmatched value, as contract 5.2 lists it: where it came from, what it is, how many files carry it."""

    source: str
    dataset: str | None
    table: str | None
    column: str | None
    slot: str
    raw_value: str
    files: int
    row_id: str | None
    """The seeded row it selects, or None where no row matches."""


def review_queue(evidence_root: Path, table: ValueMap, datasets: Iterable[str] | None = None) -> list[QueueEntry]:
    """Every evidence value whose selected row is not authored, grouped by provenance and slot, most files first.

    Driven by the evidence, not the rows (5.2): a value with no row and a value with a
    seeded row are listed the same way, and a value whose selected row is an authored
    no-op is not listed at all. ``files`` counts distinct target key values in the
    group. Selection is per line, so the same value can be listed under one dataset
    and absent under another that has an authored scoped row.
    """
    groups: dict[tuple[str, str | None, str | None, str | None, str, str], tuple[set[str], str | None]] = {}
    for path, _ in _current_files(evidence_root, datasets):
        for entry in iter_evidence(path):
            row = table.select(entry.field, entry.raw_value, entry.source.name, entry.source.dataset)
            if row is not None and row.authored:
                continue
            src = entry.source
            group = (src.name, src.dataset, src.table, src.column, entry.field, entry.raw_value)
            if group not in groups:
                groups[group] = (set(), None if row is None else row.id)
            groups[group][0].add(entry.target_key_value)
    entries = [QueueEntry(*group, files=len(targets), row_id=row_id) for group, (targets, row_id) in groups.items()]
    entries.sort(
        key=lambda e: (-e.files, e.slot, e.raw_value, e.source, e.dataset or "", e.table or "", e.column or "")
    )
    return entries


def render_queue(entries: list[QueueEntry], evidence_root: Path) -> str:
    """The queue as a markdown table."""
    lines = [
        "# Review queue: values whose selected row is not authored",
        "",
        f"Evidence root: `{evidence_root}`. {len(entries)} listed; a value is one line per source, dataset, "
        "table and column it arrives through (contract 5.2). `row` is the seeded row it selects, or `—` where "
        "no row matches.",
        "",
        "| files | slot | raw value | source | dataset | table | column | row |",
        "|---:|---|---|---|---|---|---|---|",
    ]
    for e in entries:
        lines.append(
            f"| {e.files:,} | {e.slot} | `{e.raw_value}` | {e.source} | {e.dataset or ''} | {e.table or ''} | "
            f"{e.column or ''} | {e.row_id or '—'} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``scripts/value_map.py``: ``seed`` appends seeded rows, ``queue`` prints the queue."""
    import argparse

    from .source_evidence import DEFAULT_SOURCE_EVIDENCE_ROOT

    parser = argparse.ArgumentParser(
        description="The value translation table: seed it from evidence, or list its queue"
    )
    parser.add_argument("--table", type=Path, default=None, help="Table file (default: the bundled value_map.yaml)")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_SOURCE_EVIDENCE_ROOT)
    parser.add_argument("--dataset", action="append", help="Only this dataset's evidence (repeatable)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="Append a seeded row for every value no row matches")
    queue = sub.add_parser("queue", help="List every value whose selected row is not authored")
    queue.add_argument("--output", type=Path, default=None, help="Write the markdown here instead of stdout")
    args = parser.parse_args(argv)

    table_path = args.table if args.table is not None else Path(str(default_value_map_resource()))
    if args.command == "seed":
        result = seed(table_path, args.evidence_root, args.dataset)
        print(
            f"Scanned {result.files_scanned} evidence files, {result.lines_scanned:,} lines; "
            f"added {len(result.rows_added)} seeded rows to {table_path}",
            file=sys.stderr,
        )
        for id in result.rows_added:
            print(f"  {id}", file=sys.stderr)
        return 0
    report = render_queue(
        review_queue(args.evidence_root, load_value_map(table_path), args.dataset), args.evidence_root
    )
    if args.output is not None:
        args.output.write_text(report)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(report, end="")
    return 0
