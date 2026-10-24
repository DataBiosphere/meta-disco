"""Which samples each file's data comes from, settled at reconcile (#357).

Four kinds of source name a file's samples: its own content, a submitter table, the
repository's record of the step that generated it (below), and its parent across a step that
passes samples (below). Inference reads the file's own content, called its
header here (a BAM's ``@RG SM``, a VCF's sample columns, a GATK sample map's rows, a nanopore
FAST5's ``sample_id``, a GenomicsDB workspace's ``callset.json``, ``sample_identity.SampleReader``), and writes the record's ``samples``, a pointer into its
producer file's sample lists. A submitter table
names them in a column the slot map routes to ``samples``, and the importer writes each
cell as an evidence line; reconcile reads it here, through the same identifier rules
(``rules/sample_namespaces.yaml``).

**The repository's record of the step that generated a file** (#698): AnVIL's activity rows
(``azul_manifest.ACTIVITY_TABLES``: ``anvil_activity``, and NIA_CARD's ``anvil_sequencingactivity``) naming the file as a ``generated_file_id``, and their ``used_biosample_id``, which the lineage
importer writes as lineage lines whose parent is a sample (``reconcile_lineage.BiosampleLink``). Each
biosample ties to one of our sample records through the AnVIL ids listed on it (``repository_ids``,
#669); the biosamples of every row naming the file are one source (:func:`activity_sources`), and a
file one of whose biosamples ties to no sample record gets none from it, and is counted.

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

Across any other step the child keeps its own samples, and a child and parent whose lists
disagree are counted (:func:`lists_disagree`): a CRAM whose ``@RG SM`` is not its reads' sample.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache

from . import activities, code_rules
from .edges import distinct, parent_node
from .models import SOURCE_DERIVATION_INHERITANCE, ClaimSource
from .reconcile_inherit import PARENT_CONFLICT, Step, parent_first
from .reconcile_lineage import CHILD_NOT_IN_RUN, CHILD_SEVERAL_MATCH, LineageJoin
from .records import identity_from
from .sample_identity import (
    SAMPLE,
    Identifier,
    IdentifierRuleSet,
    identifier_order,
    list_id,
    members_of,
    name_contradicts,
    reference,
    sample_list,
    sorted_lists,
)
from .source_evidence import list_cell

# How a file's samples settled; the report counts each per dataset.
AGREED = "agreed"  # two or more kinds of the file's own source named the same samples
HEADER_ONLY = "header_only"
TABLE_ONLY = "table_only"
ACTIVITY_ONLY = "activity_only"  # only the repository's record of the step that generated it (#698)
INHERITED = "inherited"  # only the file's parent named them (#668)
CONFLICT = "conflict"  # two sources named different members in one namespace
INCOMPARABLE = "incomparable"  # sources named different members, sharing no namespace
NONE = "none"  # no source named a sample
OUTCOMES = (AGREED, HEADER_ONLY, TABLE_ONLY, ACTIVITY_ONLY, INHERITED, CONFLICT, INCOMPARABLE)

# Which kind of source named a file's samples, in the order ``named_by`` lists them.
# ``header`` is whatever inference read from the file's own content, a sample map's rows included.
HEADER, TABLE, ACTIVITY, PARENT = "header", "table", "activity", "parent"
KINDS = (HEADER, TABLE, ACTIVITY, PARENT)
_ONLY = {HEADER: HEADER_ONLY, TABLE: TABLE_ONLY, ACTIVITY: ACTIVITY_ONLY}

# What became of the repository's links from a file to its biosamples (#698), per dataset: per file
# whose record the links name, whether every biosample tied to a sample record; per line, a child no
# record or several records carry (``reconcile_lineage``'s labels).
TIED = "tied"
UNTIED = "untied"
LINK_OUTCOMES = (TIED, UNTIED, CHILD_NOT_IN_RUN, CHILD_SEVERAL_MATCH)

# What a role that passes samples gave a child (#668); the report counts each per dataset and
# activity. First match wins: different lists, a parent in conflict, lists naming none by design
# (#726), a parent with none; but for the third, ``reconcile_inherit.settle_parents``' order (mixed,
# conflict, not_classified). A parent outside the run holds no list, so it counts as one with none.
PASSED = "passed"
PARENTS_DIFFER = "parents_differ"  # parents in the role name different lists
# PARENT_CONFLICT: a parent's own sources named different samples, so it has none to pass
LIST_NAMES_NONE = "list_names_none"  # every parent in the role is a list naming none by design (#726)
PARENT_NONE = "parent_none"  # a parent in the role has no settled samples: no source named any
PASSING_OUTCOMES = (PASSED, PARENTS_DIFFER, PARENT_CONFLICT, LIST_NAMES_NONE, PARENT_NONE)


@dataclass(frozen=True)
class Named:
    """One source's samples for one file, and its attributions (``Attribution`` dicts)."""

    members: frozenset[Identifier]
    named_by: tuple[dict, ...]
    kind: str = TABLE
    # The list the members make, where the source already named it (inference's record, a
    # parent's settled list), so it is not digested again for every file pointing to it.
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
        got = rules.recognise(element, dataset, SAMPLE)
        if got is None:
            return None
        members.add(got.identifier)
        if got.rule_id not in rule_ids:
            rule_ids.append(got.rule_id)
    return Named(frozenset(members), attributions(source_type, tuple(rule_ids), source))


# A source's column is one `ClaimSource` for every line of its file, and the join keeps every
# line's attributions for the whole run: built once per (rule, column), not once per line.
@lru_cache(maxsize=4096)
def attributions(source_type: str, rule_ids: tuple[str, ...], source: ClaimSource) -> tuple[dict, ...]:
    return tuple({"source_type": source_type, "rule_id": r, "source": source.to_dict()} for r in rule_ids)


def from_record(record: dict, lists: dict[str, dict], members: dict[str, frozenset[Identifier]]) -> Named | None:
    """The samples inference wrote on ``record``, its members read from the run's ``lists``.

    ``members`` keeps each list's members once read, by list id: 31,000 T2T windows point
    to one 3,202-sample list. It may hold lists no producer file holds (a table's), so the
    run's ``lists`` are checked whatever it holds. Raises ``ValueError`` where the record
    points to a list its run does not hold: the producer file is damaged, or was written
    before its lists were.
    """
    samples = record.get("samples")
    if not samples:
        return None
    key = samples["list_id"]
    entry = lists.get(key)
    if entry is None:
        raise ValueError(
            f"record {record.get('file_name')!r} points to sample list {key!r}, which no producer file of the run holds"
        )
    if key not in members:
        members[key] = members_of(entry)
    return Named(members[key], tuple(samples["named_by"]), kind=HEADER, list_id=key)


def settle(named: Iterable[Named]) -> tuple[str, dict | None, frozenset[Identifier]]:
    """``(outcome, samples, members)`` for one file from every source that named its samples.

    ``samples`` is the record's ``samples`` where the sources agree, else None; ``members``
    are then the settled members, else empty. Agreeing sources are listed header first, then
    tables, then the activity, then the parent (``KINDS``), each attribution once. The outcome is ``agreed`` where two or more kinds of the
    file's own source (header, table, activity) named them, the one kind's where one did, and
    ``inherited`` where only its parent did.
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
    named_by = list(distinct(a for n in sorted(named, key=lambda n: KINDS.index(n.kind)) for a in n.named_by))
    own = {n.kind for n in named} - {PARENT}
    if not own:
        outcome = INHERITED
    elif len(own) > 1:
        outcome = AGREED
    else:
        outcome = _ONLY[next(iter(own))]
    known = next((n.list_id for n in named if n.list_id is not None), None)
    return outcome, reference(members, named_by, known=known), members


@dataclass
class ActivityLinks:
    """:func:`activity_sources`' result: per record key, the samples its biosample links name; per dataset, what
    became of the links (``LINK_OUTCOMES``), and the first few biosample ids that tie to no sample record."""

    named: dict[str, Named] = field(default_factory=dict)
    counts: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    untied_examples: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


def activity_sources(lineage: LineageJoin, samples_by_id: Mapping[tuple[str, str], Identifier]) -> ActivityLinks:
    """Each file's samples as the repository's record of its steps names them (#698), one source per file.

    ``lineage`` holds, per child record key, the lineage lines naming a biosample it was made from
    (``resolve_lineage``), and ``samples_by_id`` the sample record each repository id ties to, keyed by
    ``(repository, id)`` (``EntityEvidence.samples_by_repository_id``). A file's lines name the biosamples of
    every row naming it; where each ties to a sample record, they name those samples, cited once per row
    (its ``activity_id``) and column, else nothing, and the file is counted ``untied``. The lines whose
    child no record, or several, carry are counted as the lineage pass counted them.
    """
    result = ActivityLinks()
    for dataset, misses in lineage.biosample_misses.items():
        result.counts[dataset].update(misses)
    # A list's id is digested once per distinct set: IGVF's 6,757 files name 326.
    ids: dict[frozenset[Identifier], str] = {}
    for key, links in lineage.biosamples.items():
        dataset = str(links[0].child[1])
        untied = [k.biosample for k in links if (k.repository, k.biosample) not in samples_by_id]
        if untied:
            result.counts[dataset][UNTIED] += 1
            examples = result.untied_examples[dataset]
            for biosample in untied:
                if len(examples) < MAX_EXAMPLES and biosample not in examples:
                    examples.append(biosample)
            continue
        result.counts[dataset][TIED] += 1
        members = frozenset(samples_by_id[(k.repository, k.biosample)] for k in links)
        if (known := ids.get(members)) is None:
            known = ids[members] = list_id(members)
        named_by = distinct(k.attribution for k in links)
        result.named[key] = Named(members, named_by, kind=ACTIVITY, list_id=known)
    return result


def lists_disagree(child: frozenset[Identifier], parent: frozenset[Identifier]) -> bool:
    """Whether a child's and its parent's sample lists disagree.

    Lists naming samples in different namespaces (a dataset's own names in each dataset as one)
    disagree, until a crosswalk can say whether an identifier names the same sample (#361).
    Within the same namespaces, a child holding its parent's samples and more (a cohort's list
    beside one member) or fewer (a callset with samples dropped) agrees; otherwise they disagree.
    """
    if _namespaces(child) != _namespaces(parent):
        return True
    return not (child <= parent or parent <= child)


def _namespaces(members: frozenset[Identifier]) -> set[tuple[str, str | None]]:
    return {(m.namespace, m.dataset) for m in members}


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
    """Per dataset, how each file's samples settled, and the lists the run's records point to; each file whose
    sources differ, and each file no source names samples for (#698).

    Reconcile reads the run twice. In the first pass :meth:`hold` keeps each file's own
    settled samples, and a child's own sources where its step passes samples; :meth:`inherit`
    then settles those children, parents first; in the second pass :meth:`settle` settles and
    counts each file as it is written.
    """

    rules: IdentifierRuleSet
    outcomes: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    # Per dataset, the files whose name names another sample than the settled members.
    name_disagreements: Counter = field(default_factory=Counter)
    name_examples: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    # Each distinct list a reconciled record points to, by id.
    lists: dict[str, dict] = field(default_factory=dict)
    files_by_list: Counter = field(default_factory=Counter)
    # Each list's members once read, by id: an inference list's (:func:`from_record`), and each
    # list a file holds (:attr:`held`).
    members: dict[str, frozenset[Identifier]] = field(default_factory=dict)
    # Per record key, the id of the file's settled list, its parent's weighed in once :meth:`inherit` ran.
    held: dict[str, str] = field(default_factory=dict)
    # Per dataset and activity, what each role passing samples gave a child (``PASSING_OUTCOMES``).
    passing: dict[str, dict[str, Counter]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(Counter)))
    # Per dataset and activity, the child and parent pairs whose lists disagree, across a step
    # passing no samples (:func:`lists_disagree`), and the first few per activity.
    parent_disagreements: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    parent_examples: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    # The keys of the lists that name no samples by design (rebuilt lists, #726), counted apart when passing.
    names_none: set[str] = field(default_factory=set)
    # What became of the repository's links from each file to its biosamples (#698).
    activity: ActivityLinks = field(default_factory=ActivityLinks)
    # Each file whose sources named different samples, with every source (#698), and each file no
    # source named a sample for, in the order settled.
    conflicts: list[dict] = field(default_factory=list)
    without_samples: list[dict] = field(default_factory=list)
    # Per child whose step passes samples, its own sources and dataset, until :meth:`inherit` reads them.
    _own: dict[str, tuple[list[Named], str]] = field(default_factory=dict, init=False, repr=False)
    # Per child, what its parents passed it, for the second pass.
    _inherited: dict[str, tuple[Named, ...]] = field(default_factory=dict, init=False, repr=False)
    # The record keys whose sources named different samples (a conflict, or incomparable).
    _conflicted: set[str] = field(default_factory=set, init=False, repr=False)
    # Per child, the parents in conflict that passed it nothing (``PARENT_CONFLICT``), named on its row if it has none.
    _conflicted_parents: dict[str, list[str]] = field(default_factory=dict, init=False, repr=False)

    def _own_sources(
        self, identity: str, record: dict, inference_lists: dict[str, dict], table: list[Named]
    ) -> list[Named]:
        header = from_record(record, inference_lists, self.members)
        activity = self.activity.named.get(identity)
        return ([header] if header is not None else []) + table + ([activity] if activity is not None else [])

    def _hold(self, identity: str, outcome: str, samples: dict | None, members: frozenset[Identifier]) -> None:
        # Adding a parent's source cannot settle a file's own conflict, so a key once in conflict stays.
        if outcome in (CONFLICT, INCOMPARABLE):
            self._conflicted.add(identity)
        if samples is None:
            self.held.pop(identity, None)
            return
        # Interned, so the 31,000 tars holding one list share one id string.
        key = sys.intern(samples["list_id"])
        self.members.setdefault(key, members)
        self.held[identity] = key

    def hold(
        self, identity: str, record: dict, inference_lists: dict[str, dict], table: list[Named], step: Step | None
    ) -> None:
        """The first pass: hold ``record``'s own settled samples, and its own sources where ``step`` passes samples."""
        named = self._own_sources(identity, record, inference_lists, table)
        if step is not None and activities.samples_roles(step.activity):
            self._own[identity] = (named, str(record.get("dataset_title") or ""))
        self._hold(identity, *settle(named))

    def inherit(self, steps: Mapping[str, Step]) -> None:
        """Settle each child whose step passes samples with its parents' settled samples, parents first.

        A role's parents pass their list where every one holds the same; two holding different
        lists, a parent in conflict, or a parent holding none, pass nothing. Raises
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
                parent_keys = step.parents(role)
                if not parent_keys:
                    continue
                lists = {self.held[p] for p in parent_keys if p in self.held}
                if len(lists) > 1:
                    outcome = PARENTS_DIFFER
                elif any(p in self._conflicted for p in parent_keys):
                    outcome = PARENT_CONFLICT
                    held = self._conflicted_parents.setdefault(key, [])
                    held.extend(p for p in parent_keys if p in self._conflicted and p not in held)
                elif all(p in self.names_none for p in parent_keys):
                    outcome = LIST_NAMES_NONE
                elif any(p not in self.held for p in parent_keys):
                    outcome = PARENT_NONE
                else:
                    outcome = PASSED
                    (list_key,) = lists
                    attribution = _inherited_attribution(step.activity, role, parent_keys)
                    passed.append(Named(self.members[list_key], (attribution,), kind=PARENT, list_id=list_key))
                self.passing[dataset][step.activity][outcome] += 1
            if passed:
                self._inherited[key] = tuple(passed)
                self._hold(key, *settle([*named, *passed]))

    def settle(
        self,
        record: dict,
        inference_lists: dict[str, dict],
        table: list[Named],
        identity: str,
        generated_by: dict | None,
        data_type: str | None,
    ) -> dict | None:
        """The reconciled ``samples`` for ``record``, counted; None where no source names them, or sources differ.

        ``identity`` is its record key, under which :meth:`inherit` kept what its parents
        passed; ``generated_by`` its reconciled step (None where it has none), whose parents in
        roles passing no samples are checked against the settled samples (:func:`lists_disagree`).
        A file whose sources differ is kept in :attr:`conflicts` with every source, and one no
        source names samples for in :attr:`without_samples`, with ``data_type``, its reconciled one, and
        ``parent_conflict``, the record keys of the parents whose conflict passed it nothing, where any did;
        each row names the file by ``record_key`` (``identity``) beside the catalog identity, which an
        HPRC record does not carry.
        """
        named = self._own_sources(identity, record, inference_lists, table) + list(self._inherited.get(identity, ()))
        outcome, samples, members = settle(named)
        dataset = str(record.get("dataset_title") or "")
        file_name = str(record.get("file_name") or "")
        self.outcomes[dataset][outcome] += 1
        if outcome in (CONFLICT, INCOMPARABLE):
            self.conflicts.append(
                {
                    "dataset_title": dataset,
                    "file_name": file_name,
                    "record_key": identity,
                    **identity_from(record),
                    "outcome": outcome,
                    "sources": [_source_row(n) for n in named],
                }
            )
        elif outcome == NONE:
            row = {
                "dataset_title": dataset,
                "file_name": file_name,
                "record_key": identity,
                **identity_from(record),
                "data_type": data_type,
            }
            if parents := self._conflicted_parents.get(identity):
                row["parent_conflict"] = parents  # the conflict rows, by record key, that left it none
            self.without_samples.append(row)
        if samples is not None:
            key = samples["list_id"]
            self.files_by_list[(dataset, key)] += 1
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

    def links_to_dict(self, dataset: str) -> dict:
        """The report's ``activity_links`` for ``dataset``: each ``LINK_OUTCOMES`` count, and the first untied biosamples."""
        counts = self.activity.counts.get(dataset, Counter())
        block: dict = {o: counts[o] for o in LINK_OUTCOMES if counts[o]}
        if examples := self.activity.untied_examples.get(dataset):
            block["untied_examples"] = examples
        return block

    def _check_parents(self, dataset: str, file_name: str, members: frozenset[Identifier], generated_by: dict) -> None:
        """Count each parent, in a role passing no samples, whose settled samples disagree with ``members``."""
        activity = generated_by["activity"]
        passing = activities.samples_roles(activity)
        seen: set[str] = set()
        for i in generated_by["inputs"]:
            key = parent_node(i)
            if i["role"] in passing or key in seen:
                continue
            seen.add(key)
            parent = self.held.get(key)
            if parent is None or not lists_disagree(members, self.members[parent]):
                continue
            self.parent_disagreements[dataset][activity] += 1
            if sum(e["activity"] == activity for e in self.parent_examples[dataset]) < MAX_EXAMPLES:
                self.parent_examples[dataset].append(
                    {
                        "file_name": file_name,
                        "activity": activity,
                        "parent_file": i.get("parent_file"),
                        "samples": [m.to_dict() for m in sorted(members)[:MAX_EXAMPLES]],
                        "parent_samples": [m.to_dict() for m in sorted(self.members[parent])[:MAX_EXAMPLES]],
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
        lists disagree across a step passing none (#668). ``activity_links`` counts what became of the
        repository's links from the dataset's files to their biosamples (#698).
        """
        datasets = sorted(
            set(self.outcomes) | set(headers) | set(unrecognised) | set(self.passing) | set(self.activity.counts)
        )
        # Per dataset and outcome (conflict, incomparable), the first few files.
        examples: dict[tuple[str, str], list[str]] = defaultdict(list)
        for row in self.conflicts:
            if len(names := examples[(row["dataset_title"], row["outcome"])]) < MAX_EXAMPLES:
                names.append(row["file_name"])
        by_dataset = {}
        for dataset in datasets:
            ranked = sorted(unrecognised.get(dataset, {}).items(), key=lambda kv: (-len(kv[1]), kv[0]))
            table_unrecognised = [
                {"table": table, "column": column, "raw_value": raw, "files": len(files)}
                for (table, column, raw), files in ranked
            ]
            by_dataset[dataset] = {
                "settled": {o: self.outcomes[dataset][o] for o in (*OUTCOMES, NONE) if self.outcomes[dataset][o]},
                "conflict_examples": examples.get((dataset, CONFLICT), []),
                "incomparable_examples": examples.get((dataset, INCOMPARABLE), []),
                "headers": headers.get(dataset, {}),
                "table_unrecognised": table_unrecognised,
                "name_disagreements": self.name_disagreements[dataset],
                "name_disagreement_examples": self.name_examples.get(dataset, []),
                "inheritance": {
                    activity: {o: counts[o] for o in PASSING_OUTCOMES if o in counts}
                    for activity, counts in sorted(self.passing.get(dataset, {}).items())
                },
                "parent_disagreements": dict(sorted(self.parent_disagreements.get(dataset, Counter()).items())),
                "parent_disagreement_examples": self.parent_examples.get(dataset, []),
                "activity_links": self.links_to_dict(dataset),
            }
        return {"lists": len(self.lists), "by_dataset": by_dataset}

    def sorted_lists(self) -> list[dict]:
        """The run's lists in id order, as the artifact writes them."""
        return sorted_lists(self.lists)


def _source_row(named: Named) -> dict:
    """One source of a conflicting file's samples, as the conflicts artifact lists it: its kind, who named it, and the samples."""
    return {
        "kind": named.kind,
        "named_by": list(named.named_by),
        "samples": [m.to_dict() for m in sorted(named.members, key=identifier_order)],
    }
