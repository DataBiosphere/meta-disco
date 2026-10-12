"""Which samples each file's data comes from, settled at reconcile (#357).

Two kinds of source name a file's samples. Inference reads the file's own header (a BAM's
``@RG SM``, a VCF's sample columns, ``sample_identity.SampleReader``) and writes the
record's ``samples``, a pointer into its producer file's sample lists. A submitter table
names them in a column the slot map routes to ``samples``, and the importer writes each
cell as an evidence line; reconcile reads it here, through the same identifier rules
(``rules/sample_namespaces.yaml``).

They settle as a file's step does (``edges.merge_steps``, ADR-0002 decision 6). Sources
that name the same members give one ``samples``, every source listed in ``named_by``; one
source alone gives its own. Sources that name different members give **none**, and the
file is counted: a ``conflict`` where two of them name members in one namespace
(``coriell:NA19770`` against ``coriell:NA19771``), ``incomparable`` where they share none
(``coriell:NA19770`` against ``sra_sample:SRS006871``, which may be one person, but only a
crosswalk could say, #361). A wrong sample is worse than none.

A file's name is never a source. Where it carries exactly one recognised identifier and
the settled members include one in that namespace, a name naming another is counted as a
disagreement (:func:`name_disagrees`): the check that finds a column mapped to the wrong
row's sample.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from .models import ClaimSource
from .sample_identity import Identifier, IdentifierRuleSet, members_of, reference, sample_list
from .source_evidence import list_cell

# How a file's samples settled; the report counts each per dataset.
AGREED = "agreed"  # header and table named the same samples
HEADER_ONLY = "header_only"
TABLE_ONLY = "table_only"
CONFLICT = "conflict"  # two sources named different members in one namespace
INCOMPARABLE = "incomparable"  # sources named different members, sharing no namespace
OUTCOMES = (AGREED, HEADER_ONLY, TABLE_ONLY, CONFLICT, INCOMPARABLE)


@dataclass(frozen=True)
class Named:
    """One source's samples for one file, and its attributions (``Attribution`` dicts)."""

    members: frozenset[Identifier]
    named_by: tuple[dict, ...]
    from_header: bool = False


def from_line(
    raw_value: str, dataset: str | None, source_type: str, source: ClaimSource, rules: IdentifierRuleSet
) -> Named | None:
    """The samples one evidence line names, or None where any string it holds no rule recognises.

    A list cell names each of its elements. Each distinct identifier rule that recognised
    one is an attribution of its own, with the line's source: ``Attribution`` names one rule.
    """
    elements = list_cell(raw_value)
    members, rule_ids = set(), []
    for element in elements if elements is not None else [raw_value]:
        got = rules.recognise(element, dataset)
        if got is None:
            return None
        members.add(got.identifier)
        if got.rule_id not in rule_ids:
            rule_ids.append(got.rule_id)
    if not members:
        return None
    named_by = tuple({"source_type": source_type, "rule_id": r, "source": source.to_dict()} for r in rule_ids)
    return Named(frozenset(members), named_by)


def from_record(record: dict, lists: dict[str, dict]) -> Named | None:
    """The samples inference wrote on ``record``, its members read from the run's ``lists``.

    Raises ``ValueError`` where the record points to a list its run does not hold: the
    producer file is damaged, or was written before its lists were.
    """
    samples = record.get("samples")
    if not samples:
        return None
    entry = lists.get(samples["list_id"])
    if entry is None:
        raise ValueError(
            f"record {record.get('file_name')!r} points to sample list {samples['list_id']!r}, which no "
            "producer file of the run holds"
        )
    return Named(members_of(entry), tuple(samples["named_by"]), from_header=True)


def settle(named: Iterable[Named]) -> tuple[str | None, dict | None, frozenset[Identifier]]:
    """``(outcome, samples, members)`` for one file from every source that named its samples.

    ``outcome`` is None where no source did. ``samples`` is the record's ``samples`` where
    the sources agree, else None; ``members`` are then the settled members, else empty.
    """
    named = list(named)
    if not named:
        return None, None, frozenset()
    sets = {n.members for n in named}
    if len(sets) > 1:
        namespaces = [{m.namespace for m in s} for s in sets]
        overlapping = any(a & b for i, a in enumerate(namespaces) for b in namespaces[i + 1 :])
        return (CONFLICT if overlapping else INCOMPARABLE), None, frozenset()
    members = next(iter(sets))
    named_by: list[dict] = []
    seen: set[str] = set()
    for n in sorted(named, key=lambda n: not n.from_header):
        for attribution in n.named_by:
            key = json.dumps(attribution, sort_keys=True)
            if key not in seen:
                seen.add(key)
                named_by.append(attribution)
    header = any(n.from_header for n in named)
    table = any(not n.from_header for n in named)
    outcome = AGREED if header and table else (HEADER_ONLY if header else TABLE_ONLY)
    return outcome, reference(members, named_by), members


def name_disagrees(file_name: str, members: frozenset[Identifier], rules: IdentifierRuleSet) -> Identifier | None:
    """The identifier ``file_name`` names, where it names one the settled ``members`` contradict; else None.

    Checked only where the name carries exactly one identifier and a member shares its
    namespace: a name naming two (a trio's file) says nothing about which, and one in
    another namespace cannot be compared.
    """
    in_name = rules.in_name(file_name)
    if len(in_name) != 1:
        return None
    named = next(iter(in_name))
    if named in members or not any(m.namespace == named.namespace for m in members):
        return None
    return named


# --- the report -----------------------------------------------------------------

# A file no source named a sample for; counted beside OUTCOMES.
NONE = "none"
MAX_EXAMPLES = 5


@dataclass
class SampleReport:
    """Per dataset, how each file's samples settled, and the lists the run's records point to."""

    rules: IdentifierRuleSet
    outcomes: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    # Per dataset and outcome (conflict, incomparable), the first few files.
    examples: dict[tuple[str, str], list[str]] = field(default_factory=lambda: defaultdict(list))
    # Per dataset, the files whose name names another sample than the settled members.
    name_disagreements: Counter = field(default_factory=Counter)
    name_examples: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    # Each distinct list a reconciled record points to, by id.
    lists: dict[str, dict] = field(default_factory=dict)

    def settle(self, record: dict, inference_lists: dict[str, dict], table: list[Named]) -> dict | None:
        """The reconciled ``samples`` for ``record``, counted; None where no source names them, or sources differ."""
        header = from_record(record, inference_lists)
        outcome, samples, members = settle(([header] if header is not None else []) + table)
        dataset = str(record.get("dataset_title") or "")
        file_name = str(record.get("file_name") or "")
        self.outcomes[dataset][outcome or NONE] += 1
        if outcome in (CONFLICT, INCOMPARABLE) and len(self.examples[(dataset, outcome)]) < MAX_EXAMPLES:
            self.examples[(dataset, outcome)].append(file_name)
        if samples is not None:
            self.lists.setdefault(samples["list_id"], sample_list(members))
            named = name_disagrees(file_name, members, self.rules)
            if named is not None:
                self.name_disagreements[dataset] += 1
                if len(self.name_examples[dataset]) < MAX_EXAMPLES:
                    self.name_examples[dataset].append(
                        {
                            "file_name": file_name,
                            "name_names": named.to_dict(),
                            "samples": [m.to_dict() for m in sorted(members)[:MAX_EXAMPLES]],
                        }
                    )
        return samples

    def to_dict(self, headers: dict[str, dict], unrecognised: dict[str, Counter]) -> dict:
        """The report's ``samples`` block: per dataset, what the headers said, how files settled, and what was not read.

        ``headers`` is per dataset what inference's headers said (``reconcile.header_samples``):
        each outcome's files (``sample_identity``'s ``NAMED``, ``UNRECOGNISED``, ``NO_SAMPLE``)
        and its most frequent unrecognised strings. ``unrecognised`` is the table values no
        rule recognised, with the lines that held each.
        """
        datasets = sorted(set(self.outcomes) | set(headers) | set(unrecognised))
        return {
            "lists": len(self.lists),
            "by_dataset": {
                dataset: {
                    "settled": {o: self.outcomes[dataset][o] for o in (*OUTCOMES, NONE) if self.outcomes[dataset][o]},
                    "conflict_examples": self.examples.get((dataset, CONFLICT), []),
                    "incomparable_examples": self.examples.get((dataset, INCOMPARABLE), []),
                    "headers": headers.get(dataset, {}),
                    "table_unrecognised": dict(Counter(unrecognised.get(dataset, {})).most_common(MAX_EXAMPLES * 4)),
                    "table_unrecognised_lines": sum(unrecognised.get(dataset, Counter()).values()),
                    "name_disagreements": self.name_disagreements[dataset],
                    "name_disagreement_examples": self.name_examples.get(dataset, []),
                }
                for dataset in datasets
            },
        }

    def sorted_lists(self) -> list[dict]:
        """The run's lists in id order, as the artifact writes them."""
        return [self.lists[key] for key in sorted(self.lists)]
