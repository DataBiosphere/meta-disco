"""Curator rules (claims contract 1.6, 1.7, 4.7): a person's answer to a conflict, as a rule (#397).

Today one kind, a file's samples (#777), read from ``rules/curator_rules.yaml``'s ``samples`` rows;
``reconcile_samples.answer`` applies them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.resources import files

import yaml

from .lineage_map import expect_keys
from .models import required_str
from .sample_identity import SAMPLE, Identifier, IdentifierRuleSet, identifier_rules
from .slot_map import Readable, SlotMap, load_slot_map, unique_key_loader

_WHERE = "curator rules"
_Loader = unique_key_loader(_WHERE)
_KINDS = {"samples"}
_SAMPLE_KEYS = {"id", "author", "date", "dataset", "table", "columns", "same_sample", "rationale"}
_PAIR_KEYS = {"name", "sample", "cited"}


@dataclass(frozen=True)
class SameSample:
    """A file name's identifier that is the table's ``sample``, as ``cited`` says, for a rule's name check alone."""

    name: Identifier
    sample: Identifier
    cited: str


@dataclass(frozen=True)
class SampleAnswer:
    """A curator rule answering a samples conflict in ``dataset`` with the sources naming the same samples as a cell
    of ``table`` in one of ``columns``, where the activity alone names others."""

    id: str
    author: str
    date: str
    dataset: str
    table: str
    columns: frozenset[str]
    same_sample: tuple[SameSample, ...]
    rationale: str

    def name_agrees(self, named: Identifier | None, members: frozenset[Identifier]) -> bool:
        """Whether a file name's one identifier, ``named``, is the one sample ``members`` holds, or a pair's name for it.

        A name names one sample, so it never confirms several.
        """
        if named is None or len(members) != 1:
            return False
        return named in members or any(p.name == named and p.sample in members for p in self.same_sample)


@dataclass(frozen=True)
class CuratorRules:
    """The loaded rules, and the sha256 of the text they were read from."""

    samples: tuple[SampleAnswer, ...]
    digest: str


def default_curator_rules_resource():
    """The bundled rules, as a package-data resource."""
    return files(f"{__package__}.rules") / "curator_rules.yaml"


def load_curator_rules(
    source: Readable | None = None, slot_map: SlotMap | None = None, rules: IdentifierRuleSet | None = None
) -> CuratorRules:
    """Load the rules, the bundled ones by default, checked against ``slot_map`` and the identifier ``rules``.

    Raises ``ValueError`` naming where a row is wrong: a key missing or unknown, an id repeated, a column the
    slot map does not read in the row's dataset and table, a pair whose identifier the identifier rules
    do not recognise as written, or two rows one file could match (one dataset and table, a column shared).
    """
    text = (source if source is not None else default_curator_rules_resource()).read_text(encoding="utf-8")
    document = yaml.load(text, Loader=_Loader)
    if not isinstance(document, dict) or set(document) != _KINDS:
        raise ValueError(f"{_WHERE}: the document is a mapping of {sorted(_KINDS)}")
    rows = document["samples"]
    if not isinstance(rows, list):
        raise ValueError(f"{_WHERE}: samples is a list of rules")
    slot_map = slot_map if slot_map is not None else load_slot_map()
    rules = rules if rules is not None else identifier_rules()
    answers = tuple(_sample_answer(row, n, slot_map, rules) for n, row in enumerate(rows))
    ids = [a.id for a in answers]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{_WHERE}: a rule id is repeated: {sorted({i for i in ids if ids.count(i) > 1})}")
    for n, a in enumerate(answers):
        for b in answers[n + 1 :]:
            if (a.dataset, a.table) == (b.dataset, b.table) and a.columns & b.columns:
                raise ValueError(f"{_WHERE}: {a.id} and {b.id} could both answer a file of {a.dataset}'s {a.table}")
    return CuratorRules(answers, hashlib.sha256(text.encode("utf-8")).hexdigest())


def _sample_answer(row: object, n: int, slot_map: SlotMap, rules: IdentifierRuleSet) -> SampleAnswer:
    at = f"{_WHERE} samples[{n}]"
    expect_keys(row, _SAMPLE_KEYS, _SAMPLE_KEYS, at)
    assert isinstance(row, dict)
    for key in _SAMPLE_KEYS - {"columns", "same_sample"}:
        required_str(row[key], key, at)
    dataset, table, columns = row["dataset"], row["table"], row["columns"]
    if not isinstance(columns, list) or not columns or not all(isinstance(c, str) for c in columns):
        raise ValueError(f"{at}: columns is {columns!r}, not a list of column names")
    unread = sorted(set(columns) - slot_map.cells(dataset, table))
    if unread:
        raise ValueError(f"{at}: the slot map reads no cell {unread} of {dataset}'s {table}")
    pairs = row["same_sample"]
    if not isinstance(pairs, list):
        raise ValueError(f"{at}: same_sample is a list of pairs")
    return SampleAnswer(
        id=row["id"],
        author=row["author"],
        date=row["date"],
        dataset=dataset,
        table=table,
        columns=frozenset(columns),
        same_sample=tuple(_pair(p, f"{at} same_sample[{i}]", rules) for i, p in enumerate(pairs)),
        rationale=row["rationale"],
    )


def _pair(pair: object, at: str, rules: IdentifierRuleSet) -> SameSample:
    expect_keys(pair, _PAIR_KEYS, _PAIR_KEYS, at)
    assert isinstance(pair, dict)
    required_str(pair["cited"], "cited", at)
    return SameSample(_identifier(pair["name"], at, rules), _identifier(pair["sample"], at, rules), pair["cited"])


def _identifier(written: object, at: str, rules: IdentifierRuleSet) -> Identifier:
    """``namespace:id``, refused unless the identifier rules recognise the id as that sample, as written."""
    namespace, _, ident = str(written).partition(":")
    got = rules.recognise(ident, None, SAMPLE)
    if got is None or got.identifier != Identifier(namespace, ident):
        raise ValueError(f"{at}: {written!r} is not a sample the identifier rules recognise as written")
    return got.identifier
