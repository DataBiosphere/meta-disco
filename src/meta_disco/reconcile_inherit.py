"""Inheritance across each file's ``generated_by``, at reconcile (contract 4.9, #571).

A file's one step (its reconciled ``generated_by``, #577) names its activity and, per input
role, its parents by record key. What each role passes is the activity's declaration in
``rules/activities.yaml`` (:func:`activities.role_passes`). For each role and each dimension
it passes, the parents in that role settle their answers among themselves and give the
child one declaration (:class:`Inherited`), which reconcile weighs with the child's own
declarations (4.2-4.6). The parents settle first: :func:`inherit` walks the graph
parent-first, so a VCF's answer is final before its ``.tbi`` takes it, and refuses a cycle.

How the parents in one role settle (:func:`settle_parents`), first match wins:

- any parent ``mixed``, or two parents whose answers do not nest (4.4), declares the state
  ``mixed``, whatever the rest are;
- any parent in ``conflict`` passes nothing (decided for #571, which folds in #413): the
  conflict is the parent's to settle, and is listed on the parent, not on its companions;
- any parent ``not_classified`` passes nothing, since it cannot be known to agree;
- otherwise the one answer — the deepest where they nest — is declared: a value or
  ``not_applicable``. For ``reference_assembly`` it carries the build's ``base`` and
  ``version`` where every parent has the same ones, and never the parents' header
  observations.

Before any of these, a role with a parent no record of the run carries passes nothing.
That cannot happen to a step reconcile built, whose parents all resolved in the run
(#577), and is counted rather than assumed.

This module holds the graph and the parents' rule; how a child's own declarations and an
inherited one resolve is reconcile's (``reconcile.resolve_slot``), handed in as a callback,
so there is one resolution rule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from . import activities, code_rules
from .models import CLASSIFIED, CONFLICT, MIXED, NOT_APPLICABLE, NOT_CLASSIFIED, SOURCE_DERIVATION_INHERITANCE
from .rule_engine import make_claim
from .schema_vocab import most_specific

REFERENCE_ASSEMBLY = "reference_assembly"

# Why a role's parents passed nothing for a slot; with DECLARED and MIXED, the outcomes the
# report counts per dataset and slot.
DECLARED = "declared"
PARENT_CONFLICT = "parent_conflict"
PARENT_NOT_CLASSIFIED = "parent_not_classified"
PARENT_NOT_IN_RUN = "parent_not_in_run"
OUTCOMES = (DECLARED, MIXED, PARENT_CONFLICT, PARENT_NOT_CLASSIFIED, PARENT_NOT_IN_RUN)

# One slot's settled answer: ``(status, value)``, where status may be ``mixed`` — the
# slot is ``not_classified`` on the record, marked by its mixed claim, and passes on as
# mixed. A build is ``(base, version)``, carried with a ``reference_assembly`` value.
Answer = tuple[str, "str | None"]
Build = tuple["str | None", "str | None"]


@dataclass(frozen=True, slots=True)
class Settled:
    """One record's settled answer per carried slot (``activities.carried()``), and its reference build.

    ``build`` is the record's own inferred build where its ``reference_assembly`` answer is
    the one inference gave, else that of the inherited declaration it took (:func:`build_for`).
    """

    answers: dict[str, Answer]
    build: Build | None = None


class Interner:
    """Holds each distinct value once: most records share one of a few answers, outcomes and steps."""

    def __init__(self) -> None:
        self._values: dict = {}
        self._settled: dict[tuple, Settled] = {}

    def __call__(self, value):
        return self._values.setdefault(value, value)

    def settled(self, answers: dict[str, Answer], build: Build | None) -> Settled:
        pattern = (tuple(answers.items()), build)
        if pattern not in self._settled:
            self._settled[pattern] = Settled(answers, build)
        return self._settled[pattern]


@dataclass(frozen=True, slots=True)
class Step:
    """A child's step as inheritance reads it: the activity, and each input as ``(role, parent_key)``."""

    activity: str
    inputs: tuple[tuple[str, str], ...]

    @classmethod
    def of(cls, generated_by: dict, share: Callable = lambda v: v) -> Step:
        inputs = tuple((share(i["role"]), i["parent_key"]) for i in generated_by["inputs"])
        return cls(share(generated_by["activity"]), inputs)


@dataclass(frozen=True, slots=True)
class Inherited:
    """One role's parents' declaration for a slot of a child: a value, ``not_applicable`` or ``mixed``."""

    activity: str
    role: str
    parent_keys: tuple[str, ...]
    declared: str
    build: Build | None = None

    def claim(self) -> dict:
        """The declaration as a claim, through ``make_claim``, naming the step it crossed and the parents."""
        declared = self.declared
        said = "disagree" if declared == MIXED else f"say {declared}"
        return make_claim(
            source_type=SOURCE_DERIVATION_INHERITANCE,
            rule_id=code_rules.INHERITED_FROM_PARENT.id,
            reason=f"Inherited across {self.activity}: its {self.role} input(s) {said}",
            value=None if declared in (MIXED, NOT_APPLICABLE) else declared,
            status=NOT_APPLICABLE if declared == NOT_APPLICABLE else None,
            state=MIXED if declared == MIXED else None,
            activity=self.activity,
            parent_role=self.role,
            parent_keys=list(self.parent_keys),
        )


def build_for(value: str | None, own: Build | None, inherited: list[Inherited]) -> Build | None:
    """The build a settled ``reference_assembly`` value carries: the record's own, else an inherited one's.

    ``own`` is the record's inferred build, given only where the value is inference's own;
    otherwise the build of the inherited declaration that declared the value, if any. One
    rule for the graph (what a child passes on) and the record (what it writes).
    """
    if own is not None:
        return own
    return next((i.build for i in inherited if i.declared == value), None)


def build_detail(build: Build | None) -> dict:
    """The ``build`` detail of a reference value from its parents: ``base`` and ``version`` only."""
    if build is None:
        return {}
    base, version = build
    return {"build": {"base": base, "version": version}}


def settle_parents(slot: str, answers: list[Answer | None]) -> tuple[str, str | None]:
    """How the parents in one role settle for ``slot``: ``(outcome, declared)``, ``declared`` None unless one is made.

    ``answers`` is each parent's settled answer, None for a parent no record of the run
    carries. The order is the module docstring's.
    """
    known = [a for a in answers if a is not None]
    if len(known) < len(answers):
        return PARENT_NOT_IN_RUN, None
    if any(status == MIXED for status, _ in known):
        return MIXED, MIXED
    said: set[str] = set()
    for status, value in known:
        if status == NOT_APPLICABLE:
            said.add(NOT_APPLICABLE)
        elif status == CLASSIFIED and value is not None:
            said.add(value)
    deepest = most_specific(slot, said) if said else None
    if len(said) > 1 and deepest is None:
        return MIXED, MIXED
    if any(status == CONFLICT for status, _ in known):
        return PARENT_CONFLICT, None
    if any(status == NOT_CLASSIFIED for status, _ in known):
        return PARENT_NOT_CLASSIFIED, None
    return DECLARED, deepest


def _parents_build(slot: str, declared: str, builds: list[Build | None]) -> Build | None:
    """The build an inherited reference value carries: the parents' one build, where they all have the same."""
    if slot != REFERENCE_ASSEMBLY or declared in (MIXED, NOT_APPLICABLE):
        return None
    return builds[0] if len(set(builds)) == 1 else None


class InheritanceCycle(ValueError):
    """A file is its own ancestor through the steps: it derives, directly or through others, from itself."""


@dataclass
class Inheritance:
    """What :func:`inherit` found: per child, its inherited declarations by slot, and per child its outcomes."""

    declarations: dict[str, dict[str, list[Inherited]]] = field(default_factory=dict)
    # Per child, one (slot, outcome) per role and slot it passes: the report counts them.
    outcomes: dict[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)


def inherit(
    steps: dict[str, Step],
    base: Callable[[str], Settled | None],
    resolve: Callable[[str, str, list[Inherited]], Answer],
    intern: Interner | None = None,
) -> Inheritance:
    """Every child's inherited declarations, its parents settled first.

    ``steps`` are the children, by record key. ``base(key)`` is a record's settled answer
    before inheritance, None for a key no record of the run carries; for a record that is
    not a child it is final, and every child has one. ``resolve(key, slot, inherited)`` is a
    child's answer for ``slot`` with its own declarations and ``inherited`` weighed together
    (reconcile's rule). Raises :class:`InheritanceCycle`, naming the files, when a child is
    its own ancestor.
    """
    final: dict[str, Settled | None] = {}
    intern = intern or Interner()
    result = Inheritance()

    def settled(key: str) -> Settled | None:
        return final[key] if key in final else base(key)

    def compute(key: str) -> Settled:
        step = steps[key]
        own = base(key)
        if own is None:
            raise ValueError(f"child {key!r} has a step but no settled answer of its own")
        answers = dict(own.answers)
        by_slot: dict[str, list[Inherited]] = {}
        outcomes: list[tuple[str, str]] = []
        for role, slots in activities.role_passes(step.activity).items():
            parent_keys = tuple(dict.fromkeys(p for r, p in step.inputs if r == role))
            if not parent_keys:
                continue
            parents = [settled(p) for p in parent_keys]
            builds = [p.build if p is not None else None for p in parents]
            for slot in slots:
                outcome, declared = settle_parents(
                    slot, [p.answers.get(slot) if p is not None else None for p in parents]
                )
                outcomes.append((slot, outcome))
                if declared is not None:
                    passed = Inherited(
                        step.activity, role, parent_keys, declared, _parents_build(slot, declared, builds)
                    )
                    by_slot.setdefault(slot, []).append(passed)
        build = own.build
        for slot, inherited in by_slot.items():
            answer = resolve(key, slot, inherited)
            if slot == REFERENCE_ASSEMBLY:
                mine = own.build if answer == own.answers.get(slot) else None
                build = build_for(answer[1], mine, inherited) if answer[0] == CLASSIFIED else None
            answers[slot] = answer
        if by_slot:
            result.declarations[key] = by_slot
        if outcomes:
            result.outcomes[key] = intern(tuple(outcomes))
        return intern.settled(answers, build)

    for start in steps:
        if start in final:
            continue
        # Depth-first, parents before children; `path` holds the files being settled, so
        # a parent already on it is a cycle.
        path: dict[str, None] = {}
        stack: list[tuple[str, bool]] = [(start, False)]
        while stack:
            key, ready = stack.pop()
            if ready:
                final[key] = compute(key)
                del path[key]
                continue
            if key in final:
                continue
            path[key] = None
            stack.append((key, True))
            for _, parent in steps[key].inputs:
                if parent in path:
                    on_path = list(path)
                    cycle = [*on_path[on_path.index(parent) :], parent]
                    raise InheritanceCycle(f"files derive from themselves through their steps: {' -> '.join(cycle)}")
                if parent in steps:
                    stack.append((parent, False))
    return result
