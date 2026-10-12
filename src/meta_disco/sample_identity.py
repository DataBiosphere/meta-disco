"""Which samples a file's data comes from, as identifiers (#357, ADR-0002 decision 1).

A source names a sample with a string: a BAM's ``@RG SM``, a VCF's sample column, a
submitter table's cell. ``rules/sample_namespaces.yaml`` (the schema's
``IdentifierRules``) says which strings are identifiers and in which namespace; a string
no rule matches is not a sample, and is counted rather than guessed. A ``dataset_local``
rule applies only in the dataset it names, and its identifiers carry that dataset.

A file points to a **sample list** rather than listing members: a joint VCF names 3,202
samples, and 31,000 T2T windows name the same 3,202. A list is identified by a digest of
its sorted members (:func:`list_id`), so every producer and reconcile name the same list
the same way without sharing state, and a run writes each distinct list once.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

import yaml

from . import code_rules
from .schema.classification_model import IdentifierRules
from .slot_map import unique_key_loader
from .validators.header_extractors import VCFHeader, parse_sam_header, read_group_samples

DATASET_LOCAL = "dataset_local"

# Splits a file name into the tokens an accession may be: `NA24695_CTTGTA_L001_R1_001.fastq.gz`
# gives `NA24695`. A name that runs an accession into other text (`HG02080vCHM13`) gives none.
_NAME_TOKEN = re.compile(r"[^A-Za-z0-9]+")

_UniqueKeyLoader = unique_key_loader("sample namespaces file")


@dataclass(frozen=True, order=True)
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


class IdentifierRuleSet:
    """The loaded rules: :meth:`recognise` turns one string into an identifier, or None."""

    def __init__(self, rules: list[_Rule]):
        self._rules = rules

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(rule.id for rule in self._rules)

    def recognise(self, raw: str, dataset: str | None) -> Recognised | None:
        """The identifier ``raw`` is in ``dataset``, or None where no rule matches.

        Raises ``ValueError`` where two rules match one string: which namespace it is in
        would then be a choice, and the rules must not leave one.
        """
        found = []
        for rule in self._rules:
            if rule.dataset is not None and rule.dataset != dataset:
                continue
            m = rule.match.fullmatch(raw)
            if m is None:
                continue
            ident = m.expand(rule.write) if rule.write is not None else raw
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
            got = self.recognise(token, None)
            if got is not None:
                out.add(got.identifier)
        return out


def default_rules_resource():
    """The bundled rules, as package data beside the rule set."""
    return files(f"{__package__}.rules") / "sample_namespaces.yaml"


def load_identifier_rules(text: str | None = None) -> IdentifierRuleSet:
    """The rules from ``text`` or the bundled file; ``ValueError`` when invalid.

    The generated model checks the shape; here, what it cannot: rule ids unique, a
    ``dataset`` exactly on the ``dataset_local`` rules, each pattern a regular expression
    and each ``write`` template valid for it.
    """
    if text is None:
        text = default_rules_resource().read_text(encoding="utf-8")
    document = IdentifierRules.model_validate(yaml.load(text, Loader=_UniqueKeyLoader))
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
            groups = {int(g) for g in re.findall(r"\\(\d+)", rule.write)}
            if any(g > pattern.groups for g in groups):
                raise ValueError(f"identifier rule {rule.id!r}: write {rule.write!r} names a group match lacks")
        rules.append(_Rule(rule.id, namespace, pattern, rule.write, rule.dataset))
    return IdentifierRuleSet(rules)


@cache
def identifier_rules() -> IdentifierRuleSet:
    """The bundled rules, loaded once."""
    return load_identifier_rules()


# --- lists and references -----------------------------------------------------


def list_id(members: Iterable[Identifier]) -> str:
    """The digest that names a set of members: the first 16 hex of the sha256 of their sorted form."""
    canonical = json.dumps([m.to_dict() for m in sorted(set(members))], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def sample_list(members: Iterable[Identifier]) -> dict:
    """A ``SampleList``: its id and its members, sorted."""
    distinct = sorted(set(members))
    return {"list_id": list_id(distinct), "members": [m.to_dict() for m in distinct]}


def reference(members: Iterable[Identifier], named_by: list[dict]) -> dict:
    """A ``SampleReference``: the list the members make, its size, and who named it."""
    distinct = set(members)
    if not distinct:
        raise ValueError("a sample reference names at least one sample")
    return {"list_id": list_id(distinct), "count": len(distinct), "named_by": named_by}


def members_of(sample_list_entry: dict) -> frozenset[Identifier]:
    """A ``SampleList``'s members, as identifiers."""
    return frozenset(
        Identifier(m["namespace"], m["id"], m.get("dataset")) for m in sample_list_entry.get("members") or []
    )


# --- a file's own header --------------------------------------------------------

# What a header said about its samples, per file; a producer counts each per dataset.
NAMED = "named"  # every string it holds is recognised: the file's samples
UNRECOGNISED = "unrecognised"  # it holds a string no rule recognises: no samples
NO_SAMPLE = "no_sample"  # it names no sample (no @RG SM; a sites-only VCF)


@dataclass(frozen=True)
class HeaderSamples:
    """What one file's header says about its samples, and the rule that read it."""

    outcome: str
    rule: code_rules.SampleRule
    members: frozenset[Identifier] = frozenset()
    unrecognised: tuple[str, ...] = ()

    def reference(self) -> dict | None:
        """The file's ``samples`` where the header names them all; None otherwise."""
        if self.outcome != NAMED:
            return None
        return reference(self.members, [{"source_type": self.rule.source_type, "rule_id": self.rule.id}])


@dataclass(frozen=True)
class SampleReader:
    """A file type's sample reader: the strings its parsed header names samples with, and the rule that reads them."""

    rule: code_rules.SampleRule
    strings: Callable[[Any], Sequence[str]]

    def read(self, content: Any, dataset: str | None, rules: IdentifierRuleSet | None = None) -> HeaderSamples:
        """The samples ``content`` names in ``dataset``: all of them recognised, or none.

        A header with one string no rule recognises names no samples: a list missing a
        member would say the file holds fewer samples than it does.
        """
        rules = rules if rules is not None else identifier_rules()
        raws = list(dict.fromkeys(self.strings(content)))
        if not raws:
            return HeaderSamples(NO_SAMPLE, self.rule)
        members, unknown = set(), []
        for raw in raws:
            got = rules.recognise(raw, dataset)
            if got is None:
                unknown.append(raw)
            else:
                members.add(got.identifier)
        if unknown:
            return HeaderSamples(UNRECOGNISED, self.rule, unrecognised=tuple(unknown))
        return HeaderSamples(NAMED, self.rule, frozenset(members))


def _read_group_strings(header_text: str) -> list[str]:
    return read_group_samples(parse_sam_header(header_text))


def _sample_column_strings(header: VCFHeader) -> tuple[str, ...]:
    return header.sample_columns or ()


BAM_SAMPLES = SampleReader(code_rules.BAM_READ_GROUP_SAMPLES, _read_group_strings)
VCF_SAMPLES = SampleReader(code_rules.VCF_SAMPLE_COLUMNS, _sample_column_strings)
