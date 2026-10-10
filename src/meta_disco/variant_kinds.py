"""A VCF's variant kind, read from the caller that made it (#654, ADR-0003).

The records a header holds cannot settle a kind: a mixed callset shows a structural
variant in its first hundred records only by chance (#630). The caller can, because a
caller calls one kind. So the kind is the caller's, looked up in ``rules/caller_kinds.yaml``,
and the caller is found in the header, in this order:

1. **The producing step**, the end of the header's data flow (``producer_steps.producing_step``).
2. **Walked back** from it through steps that keep the kind (``keeps_kind``), each to the
   step that wrote its input, to the first step that does not. That step is the caller.
   Where the chain names none — no one producing step (several bcftools ``view`` steps
   writing to stdout), or a kept step whose input no step the header records wrote (T2T's
   ``SelectVariants`` reads a callset whose ``GenotypeGVCFs`` line is not in the header) —
   the header's other steps, those that do not keep the kind, name it: a merge among them
   (rule 5), else the one tool they are, if they are exactly one.
3. **Where the header records no command line**, the one tool its ``##source`` lines, and
   a ``##DeepVariant_version`` line, name (:data:`SELF_NAMING_KEYS`): exactly one, or none.
4. **A caller's kind** is its ``callers`` row's.
5. **A merge** (``merges``) is ``small`` when every caller the header names, on a command
   line or a ``##source`` line, is a small-variant caller and the header declares no
   structural-variant field (:func:`declares_sv`). The guard is there because a merged
   header can keep one input's ``##source`` and lose another's; the VCF spec requires a
   structural variant to be declared, so an input's structural variants leave their
   declarations behind.
6. **Otherwise no kind**, with the reason (:data:`REASONS`).

A file whose header cannot give a kind is ``not_classified``: never guessed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

import yaml

from .producer_steps import NO_COMMAND_LINE, NOT_A_VCF, UNKNOWN_TOOL, data_name, producing_step, steps_of
from .schema_vocab import dimension_values
from .slot_map import unique_key_loader
from .validators.command_lines import Step
from .validators.header_extractors import SV_INFO_IDS, VCFHeader, declared_info_ids

VARIANT_KIND = "variant_kind"

# Header keys whose line names the tool that wrote the file, as ``##source`` does, and the
# tool each names: DeepVariant writes no command line and no ``##source`` (measured
# 2026-10-09 over the cached heads).
SELF_NAMING_KEYS = {"DeepVariant_version": "DeepVariant"}

# The ALT ids a header declares for a structural variant (VCF 4.3, section 1.4.5).
SV_ALT_IDS = frozenset({"DEL", "DUP", "INS", "INV", "CNV", "BND"})
_ALT_ID = re.compile(r"^##ALT=<ID=([^,>:]+)")

# Why a file has no kind. One per path that can decline; the claim's reason starts with it.
NO_CALLER_LINE = "no caller line"
SEVERAL_TOOLS = "more than one tool names itself"
UNREAD_STEP = "a command line names a tool the reader does not know"
NO_PRODUCING_STEP = "no one step made this file"
NO_CALLER_ON_CHAIN = "no caller on the step chain"
NOT_IN_TABLE = "caller not in the kind table"
MIXED_MERGE = "a merge whose callers are not all small-variant callers"
SV_DECLARED = "a merge whose header declares structural-variant fields"
PVAR = "not a VCF"
REASONS = (
    NO_CALLER_LINE,
    SEVERAL_TOOLS,
    UNREAD_STEP,
    NO_PRODUCING_STEP,
    NO_CALLER_ON_CHAIN,
    NOT_IN_TABLE,
    MIXED_MERGE,
    SV_DECLARED,
    PVAR,
)


@dataclass(frozen=True)
class Caller:
    """One ``callers`` row: a tool, the pattern its names match, the kind it calls, and why."""

    name: str
    pattern: re.Pattern[str]
    kind: str
    reason: str


@dataclass(frozen=True)
class CallerKinds:
    """``rules/caller_kinds.yaml``, loaded: the callers, and the steps that keep or merge a callset."""

    callers: tuple[Caller, ...]
    keeps_kind: frozenset[str]
    merges: frozenset[str]

    def caller(self, name: str) -> Caller | None:
        """The row whose pattern matches ``name`` whole, case-insensitively, or None."""
        return next((c for c in self.callers if c.pattern.fullmatch(name)), None)

    def keeps(self, step: Step) -> bool:
        return step.tool.lower() in self.keeps_kind

    def merges_callsets(self, step: Step) -> bool:
        return step.tool.lower() in self.merges


# Which of the rules read a header's kind, or declined it: the producing step's caller
# (rules 1, 2 and 4), the one tool the header names where it records no command line (3
# and 4), or a merge's callers (5). Each is a content rule of its own in ``code_rules``.
BY_STEP = "step"
BY_SOURCE = "source"
BY_MERGE = "merge"


@dataclass(frozen=True)
class KindReading:
    """What a header gives: a kind, or None with the reason; which rule read it (:data:`BY_STEP`…); and why."""

    by: str
    kind: str | None
    reason: str


CALLER_KINDS = "caller_kinds.yaml"


@cache
def load_caller_kinds() -> CallerKinds:
    """``rules/caller_kinds.yaml``, checked: each kind a term of ``variant_kind_enum``, no name twice.

    Raises ValueError on a row that breaks either.
    """
    raw = yaml.load(
        files("meta_disco.rules").joinpath(CALLER_KINDS).read_text(), Loader=unique_key_loader(CALLER_KINDS)
    )
    vocabulary = dimension_values(VARIANT_KIND)
    callers = []
    for row in raw["callers"]:
        if row["kind"] not in vocabulary:
            raise ValueError(f"{CALLER_KINDS}: {row['name']}'s kind {row['kind']!r} is not a term of variant_kind_enum")
        callers.append(Caller(row["name"], re.compile(row["pattern"], re.IGNORECASE), row["kind"], row["reason"]))
    names = [c.name for c in callers]
    if len(set(names)) != len(names):
        raise ValueError(f"{CALLER_KINDS}: a caller is listed twice")
    return CallerKinds(
        tuple(callers),
        frozenset(t.lower() for t in raw["keeps_kind"]),
        frozenset(t.lower() for t in raw["merges"]),
    )


def declares_sv(header: VCFHeader) -> bool:
    """Whether the header declares a structural-variant ``##INFO`` field or ``##ALT`` id."""
    if declared_info_ids(header, SV_INFO_IDS):
        return True
    return any((m := _ALT_ID.match(line)) and m.group(1) in SV_ALT_IDS for line in header.other_meta or [])


def self_named_tools(header: VCFHeader) -> list[str]:
    """The distinct tools the header's ``##source`` and :data:`SELF_NAMING_KEYS` lines name, in header order."""
    names = list(header.sources)
    for line in header.other_meta or []:
        key = line[2:].split("=", 1)[0]
        if key in SELF_NAMING_KEYS:
            names.append(SELF_NAMING_KEYS[key])
    return list(dict.fromkeys(names))


def read_kind(header: VCFHeader, file_name: str) -> KindReading:
    """The variant kind ``header`` gives the file ``file_name``, by the module docstring's rules."""
    table = load_caller_kinds()
    step, outcome = producing_step(header, file_name)
    if outcome == NOT_A_VCF:
        return _none(BY_STEP, PVAR, "a PLINK 2 .pvar records no step of its own")
    if outcome == NO_COMMAND_LINE:
        return _from_sources(header, table)
    if outcome == UNKNOWN_TOOL:
        return _none(BY_STEP, UNREAD_STEP, _unread_tools(header))
    steps = steps_of(header) or []
    if step is None:
        caller, how = _header_caller(steps, table, f"no one step made this file ({outcome})")
    else:
        caller, how = _walk_back(step, steps, table)
    if caller is None:
        return _none(BY_STEP, NO_CALLER_ON_CHAIN, how)
    if table.merges_callsets(caller):
        return _merge(header, steps, caller, table)
    row = table.caller(caller.tool)
    if row is None:
        return _none(BY_STEP, NOT_IN_TABLE, f"{caller.tool} ({how})")
    return KindReading(BY_STEP, row.kind, f"called by {row.name} ({how})")


def _walk_back(step: Step, steps: list[Step], table: CallerKinds) -> tuple[Step | None, str]:
    """The caller behind the producing ``step``, and how it was reached; None and why where none is."""
    path = [step.tool]
    seen = {step}
    while table.keeps(step):
        wrote = {data_name(i) for i in step.inputs}
        before = [s for s in steps if s.output is not None and data_name(s.output) in wrote and s not in seen]
        if len(before) != 1:
            why = "several steps" if before else "no step in the header"
            return _header_caller(steps, table, f"producing step {' <- '.join(path)}, whose input {why} wrote")
        step = before[0]
        seen.add(step)
        path.append(step.tool)
    if len(path) == 1:
        return step, "the producing step"
    return step, f"producing step {' <- '.join(path)}"


def _header_caller(steps: list[Step], table: CallerKinds, why: str) -> tuple[Step | None, str]:
    """Where the chain names no caller: a merge among the header's other steps, else its one other step.

    "Other" is every step that does not keep the kind. A merge is taken first, so rule 5
    weighs every caller the header names. ``why`` says how the chain fell short.
    """
    others = [s for s in steps if not table.keeps(s)]
    merge = next((s for s in others if table.merges_callsets(s)), None)
    if merge is not None:
        return merge, f"{why}; a {merge.tool} in the header"
    tools = list(dict.fromkeys(s.tool for s in others))
    if len(tools) != 1:
        return None, f"{why}; the header records {len(tools)} other tools"
    return others[0], f"{why}; {tools[0]}, the header's one other step"


def _from_sources(header: VCFHeader, table: CallerKinds) -> KindReading:
    """Rule 3: the one tool the header's self-naming lines name, where it records no command line."""
    rule = BY_SOURCE
    tools = self_named_tools(header)
    if not tools:
        return _none(rule, NO_CALLER_LINE, "no command line, ##source or tool version line")
    if len(tools) > 1:
        return _none(rule, SEVERAL_TOOLS, ", ".join(tools))
    row = table.caller(tools[0])
    if row is None:
        return _none(rule, NOT_IN_TABLE, tools[0])
    return KindReading(rule, row.kind, f"called by {row.name} (named by the header: {tools[0]})")


def _merge(header: VCFHeader, steps: Iterable[Step], merge: Step, table: CallerKinds) -> KindReading:
    """Rule 5: a merge is small where every caller the header names is a small-variant caller and no SV field is declared."""
    rule = BY_MERGE
    named = [s.tool for s in steps if not table.keeps(s) and not table.merges_callsets(s)] + self_named_tools(header)
    named = [n for n in dict.fromkeys(named) if not _is_kept_or_merge_name(n, table)]
    rows = [table.caller(n) for n in named]
    if not named:
        return _none(rule, NO_CALLER_LINE, f"{merge.tool} of inputs whose callers the header does not name")
    if any(r is None or r.kind != "small" for r in rows):
        return _none(rule, MIXED_MERGE, f"{merge.tool} of {', '.join(named)}")
    if declares_sv(header):
        return _none(rule, SV_DECLARED, f"{merge.tool} of {', '.join(named)}")
    callers = ", ".join(dict.fromkeys(r.name for r in rows if r is not None))
    return KindReading(rule, "small", f"{merge.tool} of calls by {callers}; no structural-variant field declared")


def _is_kept_or_merge_name(name: str, table: CallerKinds) -> bool:
    """Whether a self-named tool (a ``##source`` value) is a step that keeps or merges, not a caller."""
    return name.lower() in table.keeps_kind or name.lower() in table.merges


def _unread_tools(header: VCFHeader) -> str:
    tools = dict.fromkeys(c.step.tool or c.key for c in header.commands if not c.step.read)
    return ", ".join(tools)


def _none(by: str, reason: str, detail: str) -> KindReading:
    return KindReading(by, None, f"{reason}: {detail}")
