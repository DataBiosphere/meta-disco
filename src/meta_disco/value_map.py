"""The value translation table: raw source values to vocabulary terms (#414).

An importer writes ``(slot, raw_value)`` and stops (contract 1.2-1.4). This table is
the one step between that observation and a claim: a lookup from ``(slot, normalized
raw_value)`` to a **declaration**, applied per evidence line. A row is a rule only in
contract 3.8's sense — it makes a claim and is cited by it — and shares nothing with
``unified_rules.yaml``'s engine. The row's members are contract 3.9's; matching is 3.5;
seeded against authored is 3.11; scope and selection are 3.12; the queue is 5.2.

**The file** is ``rules/value_map.yaml``, a mapping whose one key is ``rows``::

    rows:
      - id: platform.revio
        match: {slot: platform, value: Revio, alternates: [REVIO]}
        scope: {source: anvil, dataset: AnVIL_HPRC_R2}   # optional
        declares: {platform: PACBIO}
        reason: PacBio's current long-read instrument; the source spells it two ways.
        seeded_from: [anvil/anvil15/AnVIL_HPRC_R2/20260920T175642Z]

A row is **authored** when it carries a ``reason`` and **seeded** otherwise. Only an
authored row may carry ``declares``, which names at most one term or status per slot
and may name slots other than the match slot; an authored row must carry it, and
``declares: {}`` is the deliberate ruling that the value means nothing here. ``value`` is a string or, for a list cell, a
list of strings; ``alternates`` are further spellings. An id is ``<slot>.<slug>``,
which is what keeps row ids apart from rule ids without either loader reading the
other: no rule id in the rule set, its assay rules, or the literals the content
classifiers write (keyword, dictionary entry or ``*_RULE_ID`` constant) contains a
dot, and ``test_value_map`` checks each.

**Matching** casefolds and strips, nothing more; ``test_value_map`` checks that this
cannot merge two terms of any slot's vocabulary. A list cell (a JSON array of strings,
``source_evidence.list_cell``) matches as the **set** of its elements, so ``["A", "B"]``
and ``["B", "A"]`` share a key and ``["A"]`` matches the row for ``A``; every key is
therefore a frozenset. **Selection** takes the narrowest of source-and-dataset, source,
unscoped, and returns the row whole. Two rows keyed alike on one slot at one scope,
alternates included, cannot load; two rows with different keys declaring one slot can,
since whether they collide depends on which cells a file has (4.8).

**Nothing in a classification run reads this module.** :func:`claims_from` exists for
the reconcile stage (#432) and the tests. The seeder and the review queue read evidence
files through ``source_evidence.iter_evidence``, one line at a time (#374), never a run's
output. **The seeder appends and never rewrites**: it adds one seeded row per ``(slot,
key)`` no row selects for, after the last row, so an authored row is untouched
byte for byte; it reloads the file afterwards and restores the original bytes if the
reload fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from functools import cached_property
from importlib.resources import files
from pathlib import Path

import yaml

from .manifest_survey import name_tokens
from .models import AUTHORABLE_STATUSES, CLASSIFICATION_FIELDS, required_str
from .rule_engine import make_claim
from .schema_vocab import value_in_vocabulary
from .slot_map import NO_NOTES, NOTES
from .source_evidence import (
    DEFAULT_SOURCE_EVIDENCE_ROOT,
    EvidenceEntry,
    discover,
    iter_evidence,
    list_cell,
    read_envelope,
)
from .summaries import md_table

Key = frozenset[str]
"""A normalized match key: one element for a scalar cell, several for a list cell."""

ROW_KEYS = frozenset({"id", "match", "scope", "declares", "reason", "seeded_from"})
MATCH_KEYS = frozenset({"slot", "value", "alternates"})
SCOPE_KEYS = frozenset({"source", "dataset"})
# Refused by name, with the reason, ahead of the anonymous unknown-key check — the
# shape `source_evidence._RETIRED_LINE_KEYS` uses. A mapping row sees only the slot,
# the raw value and `(source, dataset)` (contract 3.4).
_REFUSED_ROW_KEYS = {
    "table": "a row is slot and value only; which table a value comes from is the slot map's (contract 3.4)",
    "column": "a row is slot and value only; which column a value comes from is the slot map's (contract 3.4)",
    NOTES: NO_NOTES,
}
_FIELDS = frozenset(CLASSIFICATION_FIELDS)
_WHERE = "value map"
_STR_TAG = "tag:yaml.org,2002:str"
_NULL_TAG = "tag:yaml.org,2002:null"
_ROW_DASH = re.compile(r"^( *)- ", re.MULTILINE)
_EMPTY_ROWS = re.compile(r"^rows:[ \t]*\[[ \t]*\][ \t]*$", re.MULTILINE)


def default_value_map_resource():
    """The bundled table, as package data beside the rule set."""
    return files(f"{__package__}.rules") / "value_map.yaml"


# --- keys ------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Casefold and strip. The whole of the normalizer, on purpose (contract 3.5)."""
    return text.casefold().strip()


def match_key(raw_value: str | Iterable[str]) -> Key:
    """The key a raw value matches on: a list cell's elements normalized as a set, else a one-element set."""
    if not isinstance(raw_value, str):
        return frozenset(normalize(e) for e in raw_value)
    elements = list_cell(raw_value)
    return frozenset(normalize(e) for e in elements) if elements is not None else frozenset({normalize(raw_value)})


def row_id(slot: str, key: Key) -> str:
    """The id a seeded row is minted with: ``<slot>.<slug>``, set elements sorted and joined with ``+``."""
    return f"{slot}." + "+".join("_".join(name_tokens(e)) or "_" for e in sorted(key))


# --- rows -------------------------------------------------------------------------


@dataclass(frozen=True)
class Scope:
    """A source, or a source and dataset; never a dataset alone (contract 3.12)."""

    source: str
    dataset: str | None = None


@dataclass(frozen=True, eq=False)
class Row:
    """One row as loaded. ``value`` and ``alternates`` are verbatim; ``keys`` are normalized.

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

    @cached_property
    def keys(self) -> frozenset[Key]:
        """Every key this row matches on: its value and each alternate."""
        return frozenset(match_key(v) for v in (self.value, *self.alternates))


@dataclass(frozen=True)
class ValueMap:
    """A loaded table, its selection index, and a memo of selections already made."""

    rows: tuple[Row, ...]
    _index: dict[tuple[str, Key, Scope | None], Row] = field(default_factory=dict, init=False, repr=False)
    _selected: dict[tuple[str, str, str | None, str | None], Row | None] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Build the index, refusing two rows keyed alike on one slot at one scope (contract 3.12)."""
        for row in self.rows:
            for key in row.keys:
                at = (row.slot, key, row.scope)
                if at in self._index:
                    scope = "(unscoped)" if row.scope is None else f"{row.scope.source}/{row.scope.dataset or ''}"
                    raise ValueError(
                        f"{_WHERE}: rows {self._index[at].id!r} and {row.id!r} both match {sorted(key)} on {row.slot} "
                        f"at scope {scope} — one row per key at a scope, alternates included"
                    )
                self._index[at] = row

    def select(self, slot: str, raw_value: str, source: str | None, dataset: str | None) -> Row | None:
        """The narrowest row matching this evidence, or None. Its declaration is taken whole (3.12).

        Memoized on the arguments: a file's lines repeat a handful of distinct values a
        few million times, and each lookup otherwise re-parses and re-hashes the same key.
        """
        memo = (slot, raw_value, source, dataset)
        if memo in self._selected:
            return self._selected[memo]
        key = match_key(raw_value)
        scopes: list[Scope | None] = []
        if source is not None and dataset is not None:
            scopes.append(Scope(source, dataset))
        if source is not None:
            scopes.append(Scope(source))
        scopes.append(None)
        row = next((r for scope in scopes if (r := self._index.get((slot, key, scope))) is not None), None)
        self._selected[memo] = row
        return row

    def by_id(self, id: str) -> Row:
        return next(row for row in self.rows if row.id == id)


# --- loading ----------------------------------------------------------------------


def load_value_map(path: Path | None = None) -> ValueMap:
    """Load and check the table; the bundled one by default.

    The first violation raises ``ValueError`` naming the row, by id where it has one.
    The document is walked as YAML nodes rather than loaded to dicts so that a key
    given twice *inside* a row — two declarations for one slot — can be refused
    naming that row, which a loader-level duplicate check (``slot_map._UniqueKeyLoader``)
    cannot do: it sees the line before any row exists. Contract 3.5's bound on the
    normalizer is a property of :func:`normalize`, checked by ``test_value_map``.
    """
    resource = path if path is not None else default_value_map_resource()
    text = resource.read_text(encoding="utf-8")
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
    """Each row checked on its own; the cross-row key check is ``ValueMap``'s, id uniqueness is here."""
    seen_ids: dict[str, int] = {}
    for n, node in enumerate(nodes, start=1):
        row = _row(node, n)
        if row.id in seen_ids:
            raise ValueError(f"{_WHERE}: row {n} repeats id {row.id!r} (first at row {seen_ids[row.id]})")
        seen_ids[row.id] = n
        yield row


def _row(node: yaml.Node, n: int) -> Row:
    at = f"{_WHERE} row {n}"
    entries = _mapping(node, at)
    if "id" not in entries:
        raise ValueError(f"{at}: missing id")
    id = _scalar(entries["id"], at)
    at = f"{_WHERE} row {id!r}"
    for key, why in _REFUSED_ROW_KEYS.items():
        if key in entries:
            raise ValueError(f"{at}: carries {key!r} — {why}")
    unknown = set(entries) - ROW_KEYS
    if unknown:
        raise ValueError(f"{at}: unknown keys {sorted(unknown)}; a row has {sorted(ROW_KEYS)}")
    if "match" not in entries:
        raise ValueError(f"{at}: missing match")
    slot, value, alternates = _match(entries["match"], at)
    if not id.startswith(f"{slot}."):
        raise ValueError(
            f"{at}: id must start with {slot + '.'!r} — ids are `<slot>.<slug>`, which keeps them apart from rule ids"
        )
    scope = _scope(entries["scope"], at) if "scope" in entries else None
    reason = _reason(entries["reason"], at) if "reason" in entries else None
    declares = _declares(entries.get("declares"), at, reason is not None)
    seeded_from = _seeded_from(entries["seeded_from"], at) if "seeded_from" in entries else ()
    return Row(id, slot, value, alternates, scope, declares, reason, seeded_from)


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
    source = _identifier(entries["source"], f"{at} scope source")
    dataset = _identifier(entries["dataset"], f"{at} scope dataset") if "dataset" in entries else None
    return Scope(source, dataset)


def _identifier(node: yaml.Node, at: str) -> str:
    """A scope member, held to ``required_str`` — the check ``ClaimSource`` puts on the provenance a scoped row must equal."""
    text = _scalar(node, at)
    if not text.strip():
        raise ValueError(f"{at}: {text!r} is not an identifier — a scope names a source or dataset evidence can carry")
    try:
        return required_str(text, "identifier", at)
    except ValueError as exc:
        raise ValueError(f"{at}: {text!r} is not an identifier — {exc}") from exc


def _reason(node: yaml.Node, at: str) -> str:
    reason = _scalar(node, f"{at} reason")
    if not reason.strip():
        raise ValueError(f"{at}: reason is empty — an authored row records why; a seeded row has no `reason` key")
    return reason


def _declares(node: yaml.Node | None, at: str, authored: bool) -> Mapping[str, str]:
    if node is None:
        if authored:
            raise ValueError(
                f"{at}: has a reason but no `declares` — an authored row says what it declares; "
                "`declares: {}` is the deliberate no-op"
            )
        return {}
    if not authored:
        raise ValueError(f"{at}: declares something but has no reason — a seeded row declares nothing (contract 3.11)")
    declares: dict[str, str] = {}
    for slot, value_node in _mapping(node, f"{at} declares").items():
        if slot not in _FIELDS:
            raise ValueError(f"{at}: declares {slot!r}, which is not a slot; slots are {sorted(_FIELDS)}")
        term = _scalar(value_node, f"{at} declares {slot}")
        if term not in AUTHORABLE_STATUSES and not value_in_vocabulary(slot, term):
            raise ValueError(
                f"{at}: declares {slot}: {term!r}, which is not a term of {slot}'s vocabulary "
                f"nor one of {sorted(AUTHORABLE_STATUSES)}"
            )
        declares[slot] = term
    return declares


def _seeded_from(node: yaml.Node, at: str) -> tuple[str, ...]:
    if not isinstance(node, yaml.SequenceNode):
        raise ValueError(f"{at}: seeded_from is not a list (line {node.start_mark.line + 1})")
    return tuple(_scalar(item, f"{at} seeded_from") for item in node.value)


# --- claims -----------------------------------------------------------------------


def claims_from(entry: EvidenceEntry, source_type: str, table: ValueMap) -> list[tuple[str, dict]]:
    """The claims one evidence line makes: ``(slot, claim)`` per declared pair of its selected row, else ``[]``.

    Each goes through ``make_claim`` citing the row's id and carrying the verbatim raw
    value and the line's ``ClaimSource``, so two claims on one slot from two cells of
    one file stay distinguishable (4.8). Nothing here compares, merges or ranks: that
    is reconcile's (#432). ``source_type`` is the envelope's, which the line does not carry.
    """
    row = table.select(entry.field, entry.raw_value, entry.source.name, entry.source.dataset)
    if row is None or not row.authored:
        return []
    claims = []
    for slot, declared in row.declares.items():
        is_status = declared in AUTHORABLE_STATUSES
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


def _current_paths(evidence_root: Path, datasets: Iterable[str] | None) -> list[Path]:
    """Every current evidence file, restricted to the envelopes naming one of ``datasets`` when given."""
    paths = discover(evidence_root)
    if datasets is None:
        return paths
    wanted = set(datasets)
    return [p for p in paths if read_envelope(p).source.dataset in wanted]


@dataclass(frozen=True)
class SeedResult:
    files_scanned: int
    lines_scanned: int
    rows_added: tuple[str, ...]


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


def seed(table_path: Path, evidence_root: Path, datasets: Iterable[str] | None = None) -> SeedResult:
    """Append one seeded row per ``(slot, key)`` the evidence carries and no row selects for.

    "Selects" is :meth:`ValueMap.select` with the line's provenance (3.7), so a row scoped
    to one source or dataset does not stand in for the same key seen from another — that
    evidence has no row and gets its unscoped seed. A new row is unscoped, has no reason, spells the value as the first line that
    carried it did (a list cell as a list), lists every other spelling of the same key
    as an alternate, and records the generation directories it was seen in. A rerun
    over the same evidence adds nothing.
    """
    original = table_path.read_bytes()
    text = original.decode("utf-8")
    table = load_value_map(table_path)
    seen: dict[tuple[str, Key], _Seen] = {}
    paths = _current_paths(evidence_root, datasets)
    lines_scanned = 0
    for path in paths:
        where = _generation_name(evidence_root, path)
        for entry in iter_evidence(path):
            lines_scanned += 1
            if table.select(entry.field, entry.raw_value, entry.source.name, entry.source.dataset) is not None:
                continue
            elements = list_cell(entry.raw_value)
            spelling = entry.raw_value if elements is None else elements
            key = (entry.field, match_key(spelling))
            if key not in seen:
                seen[key] = _Seen(spelling, [], [where])
            else:
                seen[key].add(spelling, where)
    if not seen:
        return SeedResult(len(paths), lines_scanned, ())
    ids = {row.id for row in table.rows}
    if not table.rows:
        # `rows: []` loads as an empty table but a block item cannot follow a flow
        # sequence, so the empty list is spelled as the bare key before appending.
        text = _EMPTY_ROWS.sub("rows:", text)
    indent = _row_indent(text)
    added: list[str] = []
    block = []
    for (slot, key), found in sorted(seen.items(), key=lambda kv: (kv[0][0], sorted(kv[0][1]))):
        id = _fresh_id(row_id(slot, key), key, ids)
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
    return SeedResult(len(paths), lines_scanned, tuple(added))


def _generation_name(root: Path, path: Path) -> str:
    try:
        return path.parent.relative_to(root).as_posix()
    except ValueError:
        return path.parent.as_posix()


def _row_indent(text: str) -> str:
    """The indentation of the existing row items, or two spaces where there are none."""
    found = _ROW_DASH.search(text)
    return found.group(1) if found else "  "


def _fresh_id(candidate: str, key: Key, taken: set[str]) -> str:
    """``candidate``, or ``candidate_<digest>`` where another key already slugged to it (``a-b`` and ``a_b``).

    The digest is of the key, so the id a key gets does not depend on how many others
    collided before it — the same scan on a fresh table mints the same ids. Six hex
    characters, extended one at a time while the result is taken, so a table that
    already holds the short form still gets an unused id.
    """
    if candidate not in taken:
        return candidate
    digest = hashlib.sha1("\0".join(sorted(key)).encode()).hexdigest()
    for n in range(6, len(digest) + 1):
        if (id := f"{candidate}_{digest[:n]}") not in taken:
            return id
    raise ValueError(
        f"{_WHERE}: no unused id for {candidate!r} — the table already holds every digest of {sorted(key)}"
    )


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


_Group = tuple[str, str | None, str | None, str | None, str, str]


def review_queue(evidence_root: Path, table: ValueMap, datasets: Iterable[str] | None = None) -> list[QueueEntry]:
    """Every evidence value whose selected row is not authored, grouped by provenance and slot, most files first.

    Driven by the evidence, not the rows (5.2): a value with no row and a value with a
    seeded row are listed the same way; a value whose selected row is an authored no-op
    is not listed. ``files`` counts distinct target key values within each file and sums
    across files — a group's table names one current file per dataset in the generation
    layout, so the sum is exact there, and the per-file fold keeps memory at the largest
    file rather than the corpus.
    """
    files: dict[_Group, int] = {}
    row_ids: dict[_Group, str | None] = {}
    for path in _current_paths(evidence_root, datasets):
        targets: dict[_Group, set[str]] = {}
        for entry in iter_evidence(path):
            row = table.select(entry.field, entry.raw_value, entry.source.name, entry.source.dataset)
            if row is not None and row.authored:
                continue
            src = entry.source
            group = (src.name, src.dataset, src.table, src.column, entry.field, entry.raw_value)
            targets.setdefault(group, set()).add(entry.target_key_value)
            row_ids.setdefault(group, None if row is None else row.id)
        for group, seen in targets.items():
            files[group] = files.get(group, 0) + len(seen)
    entries = [
        QueueEntry(
            source=source,
            dataset=dataset,
            table=table_name,
            column=column,
            slot=slot,
            raw_value=raw_value,
            files=count,
            row_id=row_ids[(source, dataset, table_name, column, slot, raw_value)],
        )
        for (source, dataset, table_name, column, slot, raw_value), count in files.items()
    ]
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
        *md_table(
            ["files", "slot", "raw value", "source", "dataset", "table", "column", "row"],
            [
                [
                    f"{e.files:,}",
                    e.slot,
                    f"`{e.raw_value}`",
                    e.source,
                    e.dataset or "",
                    e.table or "",
                    e.column or "",
                    e.row_id or "—",
                ]
                for e in entries
            ],
        ),
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``scripts/value_map.py``: ``seed`` appends seeded rows, ``queue`` prints the queue."""
    parser = argparse.ArgumentParser(
        description="The value translation table: seed it from evidence, or list its queue"
    )
    parser.add_argument("--table", type=Path, default=None, help="Table file (default: the bundled value_map.yaml)")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_SOURCE_EVIDENCE_ROOT)
    parser.add_argument("--dataset", action="append", help="Only this dataset's evidence (repeatable)")
    parser.add_argument("--output", type=Path, default=None, help="queue: write the markdown here instead of stdout")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="Append a seeded row for every value no row matches")
    sub.add_parser("queue", help="List every value whose selected row is not authored")
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
