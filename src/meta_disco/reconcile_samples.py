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

**A file takes its parent's samples across a step that passes them** (#668): an input role
``rules/activities.yaml`` declares ``passes_samples`` (an index's, a checksum's, a QC
report's, a coverage track's, a cohort merge's list). The parent's settled samples are one
more source of the child's, settled with its own by the same rule: alone, the file's samples
are ``inherited``; agreeing, they are listed beside its own; differing, the file has none.
Parents settle before children (``reconcile_inherit.parent_first``), so a ``.crai.md5``
takes what its ``.crai`` took from its CRAM. Parents in one role that name different lists,
or a parent with none, pass nothing.

Across any other step the child keeps its own samples, and a child and parent that share a
namespace but neither of whose lists holds the other's are counted (:func:`lists_disagree`):
a CRAM whose ``@RG SM`` is not its reads' sample.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache

from . import activities, code_rules
from .edges import distinct
from .models import SOURCE_DERIVATION_INHERITANCE, ClaimSource
from .reconcile_inherit import Step, parent_first
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
INHERITED = "inherited"  # only the file's parent named them (#668)
CONFLICT = "conflict"  # two sources named different members in one namespace
INCOMPARABLE = "incomparable"  # sources named different members, sharing no namespace
NONE = "none"  # no source named a sample
OUTCOMES = (AGREED, HEADER_ONLY, TABLE_ONLY, INHERITED, CONFLICT, INCOMPARABLE)

# Which kind of source named a file's samples, in the order ``named_by`` lists them.
HEADER, TABLE, PARENT = "header", "table", "parent"
_KIND_ORDER = {HEADER: 0, TABLE: 1, PARENT: 2}

# What a role that passes samples gave a child (#668); the report counts each per dataset and activity.
PASSED = "passed"
PARENT_NONE = "parent_none"  # a parent in the role has no settled samples
PARENTS_DIFFER = "parents_differ"  # parents in the role name different lists
PASSING_OUTCOMES = (PASSED, PARENT_NONE, PARENTS_DIFFER)


@dataclass(frozen=True)
class Named:
    """One source's samples for one file, and its attributions (``Attribution`` dicts)."""

    members: frozenset[Identifier]
    named_by: tuple[dict, ...]
    kind: str = TABLE
    # The list the members make, where the source already named it (inference's record, a
    # parent's settled list), so it is not digested again for every file pointing to it.
    list_id: str | None = None


@dataclass(frozen=True, slots=True)
class Held:
    """A file's settled samples as its children and the disagreement check read them."""

    list_id: str
    members: frozenset[Identifier]


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
    return Named(members[key], tuple(samples["named_by"]), kind=HEADER, list_id=key)


def settle(named: Iterable[Named]) -> tuple[str, dict | None, frozenset[Identifier]]:
    """``(outcome, samples, members)`` for one file from every source that named its samples.

    ``samples`` is the record's ``samples`` where the sources agree, else None; ``members``
    are then the settled members, else empty. Agreeing sources are listed header first, then
    tables, then the parent, each attribution once. The outcome is the file's own sources'
    where any named the samples, and ``inherited`` where only its parent did.
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
    named_by = list(distinct(a for n in sorted(named, key=lambda n: _KIND_ORDER[n.kind]) for a in n.named_by))
    kinds = {n.kind for n in named}
    if HEADER in kinds:
        outcome = AGREED if TABLE in kinds else HEADER_ONLY
    else:
        outcome = TABLE_ONLY if TABLE in kinds else INHERITED
    known = next((n.list_id for n in named if n.list_id is not None), None)
    return outcome, reference(members, named_by, known=known), members


def lists_disagree(child: frozenset[Identifier], parent: frozenset[Identifier]) -> bool:
    """Whether a child's and its parent's samples share a namespace and neither holds all the other's.

    A child holding its parent's samples and more (a cohort's list beside one member) or fewer
    (a callset with samples dropped) agrees; lists in no shared namespace cannot be compared (#361).
    """
    if child <= parent or parent <= child:
        return False
    return bool({m.namespace for m in child} & {m.namespace for m in parent})


def _inherited_attribution(activity: str, role: str, parent_keys: tuple[str, ...]) -> dict:
    return {
        "source_type": SOURCE_DERIVATION_INHERITANCE,
        "rule_id": code_rules.SAMPLES_INHERITED_FROM_PARENT.id,
        "activity": activity,
        "parent_role": role,
        "parent_keys": list(parent_keys),
    }


def name_disagrees(file_name: str, members: frozenset[Identifier], rules: IdentifierRuleSet) -> Identifier | None:
    """The one identifier ``file_name`` names, where it contradicts the settled ``members``; else None."""
    named = rules.in_name_one(file_name)
    return named if named is not None and name_contradicts(named, members) else None


# --- the report -----------------------------------------------------------------

MAX_EXAMPLES = 5


@dataclass
class SampleReport:
    """Per dataset, how each file's samples settled, and the lists the run's records point to.

    Reconcile reads the run twice. In the first pass :meth:`hold` keeps each file's own
    settled samples, and a child's own sources where its step passes samples; :meth:`inherit`
    then settles those children, parents first; in the second pass :meth:`settle` settles and
    counts each file as it is written.
    """

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
    # Per record key, the file's settled samples, its parent's weighed in once :meth:`inherit` ran.
    held: dict[str, Held] = field(default_factory=dict)
    # Per dataset and activity, what each role passing samples gave a child (``PASSING_OUTCOMES``).
    passing: dict[str, dict[str, Counter]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(Counter)))
    # Per dataset and activity, the child and parent pairs whose lists disagree, across a step
    # passing no samples (:func:`lists_disagree`), and the first few.
    parent_disagreements: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    parent_examples: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    # Per child whose step passes samples, its own sources and dataset, until :meth:`inherit` reads them.
    _own: dict[str, tuple[list[Named], str]] = field(default_factory=dict, init=False, repr=False)
    # Per child, what its parents passed it, for the second pass.
    _inherited: dict[str, tuple[Named, ...]] = field(default_factory=dict, init=False, repr=False)
    # Each distinct held list once, by id: 31,000 tars hold one 3,202-sample list.
    _held_lists: dict[str, Held] = field(default_factory=dict, init=False, repr=False)

    def _own_sources(self, record: dict, inference_lists: dict[str, dict], table: list[Named]) -> list[Named]:
        header = from_record(record, inference_lists, self.members)
        return ([header] if header is not None else []) + table

    def _hold(self, identity: str, samples: dict | None, members: frozenset[Identifier]) -> None:
        if samples is None:
            self.held.pop(identity, None)
            return
        key = samples["list_id"]
        if key not in self._held_lists:
            self._held_lists[key] = Held(key, members)
        self.held[identity] = self._held_lists[key]

    def hold(
        self, identity: str, record: dict, inference_lists: dict[str, dict], table: list[Named], step: Step | None
    ) -> None:
        """The first pass: hold ``record``'s own settled samples, and its own sources where ``step`` passes samples."""
        named = self._own_sources(record, inference_lists, table)
        if step is not None and activities.samples_roles(step.activity):
            self._own[identity] = (named, str(record.get("dataset_title") or ""))
        _, samples, members = settle(named)
        self._hold(identity, samples, members)

    def inherit(self, steps: Mapping[str, Step]) -> None:
        """Settle each child whose step passes samples with its parents' settled samples, parents first.

        A role's parents pass their list where every one holds the same; a parent holding
        none, or two holding different lists, pass nothing. Raises
        ``reconcile_inherit.InheritanceCycle`` where the steps form a cycle.
        """
        for key in parent_first(steps):
            own = self._own.pop(key, None)
            if own is None:
                continue
            named, dataset = own
            step = steps[key]
            passed: list[Named] = []
            for role in activities.samples_roles(step.activity):
                parent_keys = tuple(dict.fromkeys(p for r, p in step.inputs if r == role))
                if not parent_keys:
                    continue
                held = [self.held.get(p) for p in parent_keys]
                if any(h is None for h in held):
                    outcome = PARENT_NONE
                elif len({h.list_id for h in held if h is not None}) > 1:
                    outcome = PARENTS_DIFFER
                else:
                    outcome = PASSED
                    first = held[0]
                    assert first is not None
                    attribution = _inherited_attribution(step.activity, role, parent_keys)
                    passed.append(Named(first.members, (attribution,), kind=PARENT, list_id=first.list_id))
                self.passing[dataset][step.activity][outcome] += 1
            if passed:
                self._inherited[key] = tuple(passed)
                _, samples, members = settle([*named, *passed])
                self._hold(key, samples, members)
        self._own.clear()

    def settle(
        self,
        record: dict,
        inference_lists: dict[str, dict],
        table: list[Named],
        identity: str | None = None,
        generated_by: dict | None = None,
    ) -> dict | None:
        """The reconciled ``samples`` for ``record``, counted; None where no source names them, or sources differ.

        ``identity`` is its record key, under which :meth:`inherit` kept what its parents
        passed; ``generated_by`` its reconciled step, whose parents in roles passing no
        samples are checked against the settled samples (:func:`lists_disagree`).
        """
        inherited = list(self._inherited.get(identity, ())) if identity is not None else []
        outcome, samples, members = settle(self._own_sources(record, inference_lists, table) + inherited)
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
            if generated_by is not None:
                self._check_parents(dataset, file_name, members, generated_by)
        return samples

    def _check_parents(self, dataset: str, file_name: str, members: frozenset[Identifier], generated_by: dict) -> None:
        """Count each parent, in a role passing no samples, whose settled samples disagree with ``members``."""
        activity = generated_by["activity"]
        passing = activities.samples_roles(activity)
        seen: set[str] = set()
        for i in generated_by["inputs"]:
            key = i["parent_key"]
            if i["role"] in passing or key in seen:
                continue
            seen.add(key)
            parent = self.held.get(key)
            if parent is None or not lists_disagree(members, parent.members):
                continue
            self.parent_disagreements[dataset][activity] += 1
            if len(self.parent_examples[dataset]) < MAX_EXAMPLES:
                self.parent_examples[dataset].append(
                    {
                        "file_name": file_name,
                        "activity": activity,
                        "parent_file": i.get("parent_file"),
                        "samples": [m.to_dict() for m in sorted(members)[:MAX_EXAMPLES]],
                        "parent_samples": [m.to_dict() for m in sorted(parent.members)[:MAX_EXAMPLES]],
                    }
                )

    def to_dict(self, headers: dict[str, dict], unrecognised: dict[str, dict[tuple[str, str, str], set[str]]]) -> dict:
        """The report's ``samples`` block: per dataset, what the headers said, how files settled, and what was not read.

        ``headers`` is per dataset what inference's headers said (``reconcile.header_samples``):
        each outcome's files (``sample_identity``'s ``NAMED``, ``UNRECOGNISED``, ``NO_SAMPLE``, ``UNREAD``)
        and its most frequent unrecognised strings. ``unrecognised`` is every table value no rule
        recognised, by table and column, with the number of files whose line held it; each is listed
        (contract 5.2), the most files first. Per activity, ``inheritance`` counts what each role
        passing samples gave a child, and ``parent_disagreements`` the child and parent pairs whose
        lists disagree across a step passing none (#668).
        """
        datasets = sorted(set(self.outcomes) | set(headers) | set(unrecognised) | set(self.passing))
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
                "inheritance": {
                    activity: {o: counts[o] for o in PASSING_OUTCOMES if counts[o]}
                    for activity, counts in sorted(self.passing.get(dataset, {}).items())
                },
                "parent_disagreements": dict(sorted(self.parent_disagreements.get(dataset, Counter()).items())),
                "parent_disagreement_examples": self.parent_examples.get(dataset, []),
            }
        return {"lists": len(self.lists), "by_dataset": by_dataset}

    def sorted_lists(self) -> list[dict]:
        """The run's lists in id order, as the artifact writes them."""
        return sorted_lists(self.lists)
