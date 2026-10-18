"""Which samples a file's data comes from, and which donor a sample was collected from, as identifiers (#357, #693).

A source names a sample with a string: a BAM's ``@RG SM``, a VCF's sample column, a
submitter table's cell. ``rules/sample_namespaces.yaml`` (the schema's
``IdentifierRules``) says which strings are identifiers, in which namespace, and whether
each names a sample, a donor or both; a string no rule matches is not a sample, and is
counted rather than guessed. A ``dataset_local`` rule applies only in the dataset it names,
and its identifiers carry that dataset. A rule naming both says the sample was collected
from the donor with the same identifier (:meth:`IdentifierRuleSet.collected_from`).

A file points to a **sample list** rather than listing members: a joint VCF names 3,202
samples, and 31,000 T2T windows name the same 3,202. A list is identified by a digest of
its sorted members (:func:`list_id`), so every producer and reconcile name the same list
the same way without sharing state. Each producer file holds each list its records point
to once, and so does the reconciled artifact.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from functools import cache, cached_property, lru_cache
from importlib.resources import files
from typing import Any, Literal

import yaml

from . import code_rules
from .models import DONOR_REPOSITORY_ID, SAMPLE_REPOSITORY_ID
from .schema.classification_model import IdentifierRule, IdentifierRules
from .slot_map import unique_key_loader
from .validators.header_extractors import VCFHeader, parse_sam_header

DATASET_LOCAL = "dataset_local"

# What an identifier names (the schema's `entity_kind_enum`, #693).
EntityKind = Literal["sample", "donor"]
SAMPLE: EntityKind = "sample"
DONOR: EntityKind = "donor"
ENTITY_KINDS = frozenset({SAMPLE, DONOR})
# Each kind, and the entity evidence field a repository's own identifier for one is written as
# (#669); and back, the kind a repository identifier line's identifier names.
REPOSITORY_ID_FIELD: dict[EntityKind, str] = {DONOR: DONOR_REPOSITORY_ID, SAMPLE: SAMPLE_REPOSITORY_ID}
KIND_OF_REPOSITORY_ID: dict[str, EntityKind] = {field: kind for kind, field in REPOSITORY_ID_FIELD.items()}

# Splits a file name into the tokens an accession may be: `NA24695_CTTGTA_L001_R1_001.fastq.gz`
# gives `NA24695`. A name that runs an accession into other text (`HG02080vCHM13`) gives none.
_NAME_TOKEN = re.compile(r"[^A-Za-z0-9]+")

_UniqueKeyLoader = unique_key_loader("sample namespaces file")

# A rule's ``write`` template: literal text on one line and numbered groups ``\1`` to ``\9`` (none
# followed by another digit), never empty and nothing else, so
# every template is checked whole at load (a named ``\g<...>`` or another escape would otherwise
# fail only at the first string it rewrites).
_TEMPLATE = re.compile(r"(?:[^\\\r\n]|\\[1-9])*")
# A group reference followed by a digit (``\10``) is read by ``re`` as group 10, not group 1 then "0".
_AMBIGUOUS_GROUP = re.compile(r"\\[1-9][0-9]")


@dataclass(frozen=True, order=True, slots=True)
class Identifier:
    """A sample as an identifier: equal exactly when namespace, id and dataset are."""

    namespace: str
    id: str
    dataset: str | None = None

    def to_dict(self) -> dict:
        """As an ``EntityIdentifier``: ``dataset`` only where the namespace is ``dataset_local``."""
        out = {"id": self.id, "namespace": self.namespace}
        if self.dataset is not None:
            out["dataset"] = self.dataset
        return out


@dataclass(frozen=True)
class Recognised:
    """A string recognised as an identifier, and the rule that recognised it."""

    identifier: Identifier
    rule_id: str


@dataclass(frozen=True)
class _Rule:
    id: str
    namespace: str
    match: re.Pattern
    write: str | None
    dataset: str | None
    names: frozenset[str]


class IdentifierRuleSet:
    """The loaded rules: :meth:`recognise` turns one string into an identifier, or None."""

    def __init__(self, rules: list[_Rule]):
        self._rules = rules

    def recognise(self, raw: str, dataset: str | None, entity: EntityKind) -> Recognised | None:
        """The identifier ``raw`` is in ``dataset``, as the ``entity`` given, or None where no rule naming it matches.

        Raises ``ValueError`` where two rules naming ``entity`` match one string: which
        namespace it is in would then be a choice, and the rules must not leave one. Raises too
        where a rule naming a sample and a donor writes an identifier its own pattern does not
        match, since :meth:`collected_from` could not find that rule again.
        """
        if entity not in ENTITY_KINDS:
            raise ValueError(f"{entity!r} is not one of {sorted(ENTITY_KINDS)}")
        found = []
        for rule in self._rules:
            if entity not in rule.names:
                continue
            if rule.dataset is not None and rule.dataset != dataset:
                continue
            m = rule.match.fullmatch(raw)
            if m is None:
                continue
            ident = m.expand(rule.write) if rule.write is not None else raw
            if rule.names == ENTITY_KINDS and rule.match.fullmatch(ident) is None:
                # `collected_from` finds the rule again by matching the identifier as written.
                raise ValueError(
                    f"identifier rule {rule.id!r} writes {raw!r} as {ident!r}, which its own pattern does not match; "
                    "a rule naming a sample and a donor must accept what it writes, or the sample's donor is lost"
                )
            found.append(Recognised(Identifier(rule.namespace, ident, rule.dataset), rule.id))
        if len(found) > 1:
            raise ValueError(f"{raw!r} matches {len(found)} identifier rules: {[r.rule_id for r in found]}")
        return found[0] if found else None

    def in_name(self, file_name: str) -> set[Identifier]:
        """The identifiers a file name's tokens are, by every rule but the ``dataset_local`` ones.

        A dataset's own names are recognised only where it writes them as a sample, not
        wherever they appear in a name.
        """
        out = set()
        for token in _NAME_TOKEN.split(file_name):
            if not token:
                continue
            got = self.recognise(token, None, SAMPLE)
            if got is not None:
                out.add(got.identifier)
        return out

    def collected_from(self, sample: Identifier) -> Recognised | None:
        """The donor ``sample`` was collected from, by a rule naming both in its namespace, or None.

        A rule naming a sample and a donor with one string says the sample was collected
        from the donor of the same identifier (#693): ``coriell:HG00096``, the cell line, is
        from ``coriell:HG00096``, the person. The rule is the one whose pattern the
        identifier as written matches, so ``NA19908`` (written from ``GM19908``) is found
        by the rule that wrote it. Raises ``ValueError`` where two such rules match.
        """
        found = [
            Recognised(sample, rule.id)
            for rule in self._rules
            if rule.names == ENTITY_KINDS
            and rule.namespace == sample.namespace
            and rule.dataset == sample.dataset
            and rule.match.fullmatch(sample.id) is not None
        ]
        if len(found) > 1:
            raise ValueError(f"{sample!r} matches {len(found)} identifier rules: {[r.rule_id for r in found]}")
        return found[0] if found else None

    def in_name_one(self, file_name: str) -> Identifier | None:
        """The one identifier ``file_name`` names, or None where it names none or several (a trio's file)."""
        found = self.in_name(file_name)
        return next(iter(found)) if len(found) == 1 else None


def name_contradicts(named: Identifier, members: Collection[Identifier]) -> bool:
    """Whether a file name's one identifier contradicts the file's samples: another sample in a namespace they share.

    One in another namespace cannot be compared (`giab:HG007` against `coriell:NA24695` may be one
    person, #361), so it contradicts nothing. Shared by ``make check-slot-map`` and reconcile, so
    both count a disagreement the same way.
    """
    return named not in members and any(m.namespace == named.namespace for m in members)


def default_rules_resource():
    """The bundled rules, as package data beside the rule set."""
    return files(f"{__package__}.rules") / "sample_namespaces.yaml"


def load_identifier_rules(text: str | None = None) -> IdentifierRuleSet:
    """The rules from ``text`` or the bundled file; ``ValueError`` when invalid.

    The generated model checks the shape; here, what it cannot: rule ids unique, a
    ``dataset`` exactly on the ``dataset_local`` rules, ``names`` non-empty and without
    repeats, each pattern a regular expression and each ``write`` template valid for it.
    """
    return _rule_set(_document(text))


def _rule_set(document: IdentifierRules) -> IdentifierRuleSet:
    rules: list[_Rule] = []
    seen: set[str] = set()
    for rule in document.rules:
        if rule.id in seen:
            raise ValueError(f"identifier rule {rule.id!r}: declared twice")
        seen.add(rule.id)
        namespace = str(rule.namespace)
        if (namespace == DATASET_LOCAL) != (rule.dataset is not None):
            raise ValueError(f"identifier rule {rule.id!r}: a dataset is set exactly on a {DATASET_LOCAL} rule")
        try:
            pattern = re.compile(rule.match)
        except re.error as exc:
            raise ValueError(
                f"identifier rule {rule.id!r}: match {rule.match!r} is not a regular expression: {exc}"
            ) from None
        if rule.write is not None:
            if not rule.write or _TEMPLATE.fullmatch(rule.write) is None or _AMBIGUOUS_GROUP.search(rule.write):
                raise ValueError(
                    f"identifier rule {rule.id!r}: write {rule.write!r} is not literal text and \\1 to \\9"
                )
            groups = {int(g) for g in re.findall(r"\\(\d)", rule.write)}
            if any(g > pattern.groups for g in groups):
                raise ValueError(f"identifier rule {rule.id!r}: write {rule.write!r} names a group match lacks")
        names = [str(n) for n in rule.names]
        if not names or len(set(names)) != len(names):
            raise ValueError(
                f"identifier rule {rule.id!r}: names {names} must name a sample, a donor or both, once each"
            )
        rules.append(_Rule(rule.id, namespace, pattern, rule.write, rule.dataset, frozenset(names)))
    return IdentifierRuleSet(rules)


def _document(text: str | None) -> IdentifierRules:
    if text is None:
        text = default_rules_resource().read_text(encoding="utf-8")
    return IdentifierRules.model_validate(yaml.load(text, Loader=_UniqueKeyLoader))


def identifier_rule_declarations(text: str | None = None) -> list[IdentifierRule]:
    """The rules as declared, with their rationale, for a reader that lists them; checked as :func:`load_identifier_rules` checks them."""
    document = _document(text)
    _rule_set(document)
    return list(document.rules)


@cache
def identifier_rules() -> IdentifierRuleSet:
    """The bundled rules, loaded once."""
    return load_identifier_rules()


# --- lists and references -----------------------------------------------------


def identifier_order(identifier: Identifier) -> tuple[str, str, str]:
    """The key identifiers sort by: namespace, id, then dataset (absent sorting first)."""
    return (identifier.namespace, identifier.id, identifier.dataset or "")


def _sorted(members: Iterable[Identifier]) -> list[dict]:
    """The distinct members as ``EntityIdentifier`` dicts, in one canonical order.

    Sorted by a plain tuple key rather than the dataclass's own ordering, whose comparisons
    run in Python: building a 3,202-member list that way, sorted twice, measured about 10 ms.
    The order is the same: a namespace's identifiers all carry a dataset
    (``dataset_local``) or none.
    """
    return [m.to_dict() for m in sorted(set(members), key=identifier_order)]


def _digest(entries: list[dict]) -> str:
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def list_id(members: Iterable[Identifier]) -> str:
    """The digest that names a set of members: the first 16 hex of the sha256 of their sorted form."""
    return _digest(_sorted(members))


def sample_list(members: Iterable[Identifier]) -> dict:
    """A ``SampleList``: its id and its members, sorted."""
    entries = _sorted(members)
    return {"list_id": _digest(entries), "members": entries}


def reference(members: Iterable[Identifier], named_by: list[dict], known: str | None = None) -> dict:
    """A ``SampleReference``: the list the members make, its size, and who named it.

    ``known`` is the list's id where the caller already holds it (a header's reading, an
    inference record), so a 3,202-member list is not digested again for every file.
    """
    distinct = set(members)
    if not distinct:
        raise ValueError("a sample reference names at least one sample")
    return {"list_id": known if known is not None else list_id(distinct), "count": len(distinct), "named_by": named_by}


def sorted_lists(lists: dict[str, dict]) -> list[dict]:
    """A run's sample lists by id, in id order, as a producer file and the reconciled artifact write them."""
    return [lists[key] for key in sorted(lists)]


def most_frequent(counts: Counter, limit: int | None = None) -> dict[str, int]:
    """``counts`` most frequent first, ties by the string, so the same counts give the same order however they were made."""
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return dict(ranked if limit is None else ranked[:limit])


def members_of(sample_list_entry: dict) -> frozenset[Identifier]:
    """A ``SampleList``'s members, as identifiers."""
    return frozenset(
        Identifier(m["namespace"], m["id"], m.get("dataset")) for m in sample_list_entry.get("members") or []
    )


# --- a file's own content: a header, a sample map's rows (#668) ------------------

# What a file's header (or other content a reader reads) said about its samples, per file; a
# producer counts each per dataset.
NAMED = "named"  # every string it holds is recognised: the file's samples
UNRECOGNISED = "unrecognised"  # it holds a string no rule recognises: no samples
NO_SAMPLE = "no_sample"  # it names no sample (no @RG line; a sites-only VCF; a file that is no sample map)
UNREAD = "unread"  # the head read did not reach where the samples are (a VCF's #CHROM line)


@dataclass(frozen=True)
class HeaderSamples:
    """What one file's header says about its samples, and the rule that read it."""

    outcome: str
    rule: code_rules.SampleRule
    members: frozenset[Identifier] = frozenset()
    unrecognised: tuple[str, ...] = ()

    @cached_property
    def sample_list(self) -> dict | None:
        """The ``SampleList`` the members make, built once per reading; None where the header names none."""
        return sample_list(self.members) if self.outcome == NAMED else None

    def reference(self) -> dict | None:
        """The file's ``samples`` where the header names them all; None otherwise."""
        if self.sample_list is None:
            return None
        named_by = [{"source_type": self.rule.source_type, "rule_id": self.rule.id}]
        return reference(self.members, named_by, known=self.sample_list["list_id"])


@dataclass(frozen=True)
class SampleReader:
    """A file type's sample reader: the strings its parsed content (a header, a sample map's rows) names samples with, and the rule that reads them."""

    rule: code_rules.SampleRule
    # The strings the parse names samples with, or None where the head read did not reach them.
    strings: Callable[[Any], Sequence[str] | None]

    def read(self, content: Any, dataset: str | None) -> HeaderSamples:
        """The samples ``content`` names in ``dataset``: all of them recognised, or none.

        A header with one string no rule recognises names no samples: a list missing a
        member would say the file holds fewer samples than it does.
        """
        strings = self.strings(content)
        if strings is None:
            return HeaderSamples(UNREAD, self.rule)
        return _read(self.rule, tuple(dict.fromkeys(strings)), dataset, identifier_rules())


# A joint VCF's 3,202 sample columns repeat across 31,000 T2T windows: each distinct reading is
# made once, and its list (sorted, digested) with it, rather than once per file (#357). A
# 3,202-member reading holds about 1 MB (measured), so the cache is bounded at 128 readings.
# A reading is evicted only once 128 others have been used since its own last use.
@lru_cache(maxsize=128)
def _read(
    rule: code_rules.SampleRule, raws: tuple[str, ...], dataset: str | None, rules: IdentifierRuleSet
) -> HeaderSamples:
    if not raws:
        return HeaderSamples(NO_SAMPLE, rule)
    members, unknown = set(), []
    for raw in raws:
        got = rules.recognise(raw, dataset, SAMPLE)
        if got is None:
            unknown.append(raw)
        else:
            members.add(got.identifier)
    if unknown:
        return HeaderSamples(UNRECOGNISED, rule, unrecognised=tuple(unknown))
    return HeaderSamples(NAMED, rule, frozenset(members))


# What a read group with no SM contributes: a string no rule recognises, so the header names no
# samples rather than a list missing whoever that read group's reads came from.
NO_SM = "(a read group without SM)"


def _read_group_strings(header_text: str) -> list[str]:
    return [rg.get("SM") or NO_SM for rg in parse_sam_header(header_text).rg or []]


def _sample_column_strings(header: VCFHeader) -> tuple[str, ...] | None:
    return header.sample_columns


def _sample_map_strings(rows: Sequence[tuple[str, str]] | None) -> list[str]:
    """Each row's sample name; none for a file that is not a map (``cohort_steps.parse_sample_map``'s None)."""
    return [sample for sample, _ in rows or ()]


BAM_SAMPLES = SampleReader(code_rules.BAM_READ_GROUP_SAMPLES, _read_group_strings)
VCF_SAMPLES = SampleReader(code_rules.VCF_SAMPLE_COLUMNS, _sample_column_strings)
SAMPLE_MAP_SAMPLES = SampleReader(code_rules.SAMPLE_MAP_ROWS, _sample_map_strings)
# A sample map held outside AnVIL for a dataset (#710), read at reconcile.
EXTERNAL_SAMPLE_MAP_SAMPLES = SampleReader(code_rules.EXTERNAL_SAMPLE_MAP_ROWS, _sample_map_strings)
