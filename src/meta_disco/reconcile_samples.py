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

A file's name is never a source. Where it carries exactly one recognised identifier that
contradicts the settled members (``sample_identity.name_contradicts``), it is counted as a
disagreement (:func:`name_disagrees`): the check that finds a column mapped to the wrong
row's sample.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache

from .edges import distinct
from .models import ClaimSource
from .sample_identity import (
    Identifier,
    IdentifierRuleSet,
    members_of,
    name_contradicts,
    reference,
    sample_list,
    sorted_lists,
)
from .source_evidence import list_cell

# How a file's samples settled; the report counts each per dataset.
AGREED = "agreed"  # header and table named the same samples
HEADER_ONLY = "header_only"
TABLE_ONLY = "table_only"
CONFLICT = "conflict"  # two sources named different members in one namespace
INCOMPARABLE = "incomparable"  # sources named different members, sharing no namespace
NONE = "none"  # no source named a sample
OUTCOMES = (AGREED, HEADER_ONLY, TABLE_ONLY, CONFLICT, INCOMPARABLE)


@dataclass(frozen=True)
class Named:
    """One source's samples for one file, and its attributions (``Attribution`` dicts)."""

    members: frozenset[Identifier]
    named_by: tuple[dict, ...]
    from_header: bool = False
    # The list the members make, where the source already named it (inference's record), so
    # it is not digested again for every file pointing to it.
    list_id: str | None = None


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
    return Named(frozenset(members), _attributions(source_type, tuple(rule_ids), source))


# A source's column is one `ClaimSource` for every line of its file, and the join keeps every
# line's attributions for the whole run: built once per (rule, column), not once per line.
@lru_cache(maxsize=4096)
def _attributions(source_type: str, rule_ids: tuple[str, ...], source: ClaimSource) -> tuple[dict, ...]:
    return tuple({"source_type": source_type, "rule_id": r, "source": source.to_dict()} for r in rule_ids)


def from_record(record: dict, lists: dict[str, dict], members: dict[str, frozenset[Identifier]]) -> Named | None:
    """The samples inference wrote on ``record``, its members read from the run's ``lists``.

    ``members`` keeps each list's members once read, by list id: 31,000 T2T windows point
    to one 3,202-sample list. Raises ``ValueError`` where the record points to a list its
    run does not hold: the producer file is damaged, or was written before its lists were.
    """
    samples = record.get("samples")
    if not samples:
        return None
    key = samples["list_id"]
    if key not in members:
        entry = lists.get(key)
        if entry is None:
            raise ValueError(
                f"record {record.get('file_name')!r} points to sample list {key!r}, which no "
                "producer file of the run holds"
            )
        members[key] = members_of(entry)
    return Named(members[key], tuple(samples["named_by"]), from_header=True, list_id=key)


def settle(named: Iterable[Named]) -> tuple[str, dict | None, frozenset[Identifier]]:
    """``(outcome, samples, members)`` for one file from every source that named its samples.

    ``samples`` is the record's ``samples`` where the sources agree, else None; ``members``
    are then the settled members, else empty. Agreeing sources are listed header first, each
    attribution once.
    """
    named = list(named)
    if not named:
        return NONE, None, frozenset()
    sets = {n.members for n in named}
    if len(sets) > 1:
        namespaces = [{m.namespace for m in s} for s in sets]
        overlapping = any(a & b for i, a in enumerate(namespaces) for b in namespaces[i + 1 :])
        return (CONFLICT if overlapping else INCOMPARABLE), None, frozenset()
    members = next(iter(sets))
    named_by = list(distinct(a for n in sorted(named, key=lambda n: not n.from_header) for a in n.named_by))
    header = any(n.from_header for n in named)
    table = any(not n.from_header for n in named)
    outcome = AGREED if header and table else (HEADER_ONLY if header else TABLE_ONLY)
    known = next((n.list_id for n in named if n.list_id is not None), None)
    return outcome, reference(members, named_by, known=known), members


def name_disagrees(file_name: str, members: frozenset[Identifier], rules: IdentifierRuleSet) -> Identifier | None:
    """The one identifier ``file_name`` names, where it contradicts the settled ``members``; else None."""
    named = rules.in_name_one(file_name)
    return named if named is not None and name_contradicts(named, members) else None


# --- the report -----------------------------------------------------------------

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
    # Each inference list's members once read, by id (:func:`from_record`).
    members: dict[str, frozenset[Identifier]] = field(default_factory=dict)

    def settle(self, record: dict, inference_lists: dict[str, dict], table: list[Named]) -> dict | None:
        """The reconciled ``samples`` for ``record``, counted; None where no source names them, or sources differ."""
        header = from_record(record, inference_lists, self.members)
        outcome, samples, members = settle(([header] if header is not None else []) + table)
        dataset = str(record.get("dataset_title") or "")
        file_name = str(record.get("file_name") or "")
        self.outcomes[dataset][outcome] += 1
        if outcome in (CONFLICT, INCOMPARABLE) and len(self.examples[(dataset, outcome)]) < MAX_EXAMPLES:
            self.examples[(dataset, outcome)].append(file_name)
        if samples is not None:
            key = samples["list_id"]
            if key not in self.lists:
                # A header's list is the inference list itself; only a table's is built here.
                self.lists[key] = inference_lists.get(key) or sample_list(members)
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

    def to_dict(self, headers: dict[str, dict], unrecognised: dict[str, dict[tuple[str, str, str], set[str]]]) -> dict:
        """The report's ``samples`` block: per dataset, what the headers said, how files settled, and what was not read.

        ``headers`` is per dataset what inference's headers said (``reconcile.header_samples``):
        each outcome's files (``sample_identity``'s ``NAMED``, ``UNRECOGNISED``, ``NO_SAMPLE``, ``UNREAD``)
        and its most frequent unrecognised strings. ``unrecognised`` is every table value no rule
        recognised, by table and column, with the files whose line held it; each is listed
        (contract 5.2), the most files first.
        """
        datasets = sorted(set(self.outcomes) | set(headers) | set(unrecognised))
        by_dataset = {}
        for dataset in datasets:
            ranked = sorted(unrecognised.get(dataset, {}).items(), key=lambda kv: (-len(kv[1]), kv[0]))
            table_unrecognised = [
                {"table": table, "column": column, "raw_value": raw, "files": len(files)}
                for (table, column, raw), files in ranked
            ]
            by_dataset[dataset] = {
                "settled": {o: self.outcomes[dataset][o] for o in (*OUTCOMES, NONE) if self.outcomes[dataset][o]},
                "conflict_examples": self.examples.get((dataset, CONFLICT), []),
                "incomparable_examples": self.examples.get((dataset, INCOMPARABLE), []),
                "headers": headers.get(dataset, {}),
                "table_unrecognised": table_unrecognised,
                "name_disagreements": self.name_disagreements[dataset],
                "name_disagreement_examples": self.name_examples.get(dataset, []),
            }
        return {"lists": len(self.lists), "by_dataset": by_dataset}

    def sorted_lists(self) -> list[dict]:
        """The run's lists in id order, as the artifact writes them."""
        return sorted_lists(self.lists)
