"""A VCF's variant kind, read from the caller that made it (#654, ADR-0003).

The records a header holds cannot settle a kind: a mixed callset shows a structural
variant in its first hundred records only by chance (#630). The caller can, because a
caller calls one kind. So the kind is the caller's, looked up in ``rules/caller_kinds.yaml``,
and the caller is found in the header, in this order:

1. **The producing step**, the end of the header's data flow (``producer_steps.producing_step``).
2. **Walked back** from it through steps that keep the kind (``keeps_kind``), each to the
   step that wrote its input, to the first step that does not. That step is the caller.
   Where the chain names none — no one producing step (several bcftools ``view`` steps
   writing to stdout, or a step whose output the file was renamed from), or a kept step
   whose input no step the header records wrote (T2T's
   ``SelectVariants`` reads a callset whose ``GenotypeGVCFs`` line is not in the header) —
   the header's other steps, those that do not keep the kind, name it: a merge among them
   (rule 5), else the one tool they are, if they are exactly one and the rest of the header
   bears it out, as rule 5's guard does a merge's callers (:func:`_fallback_doubt`).
3. **Where no command line names a caller** (the header records none, or rules 1 and 2 find
   none), the one tool its ``##source`` lines, and a ``##DeepVariant_version`` line, name
   (:data:`SELF_NAMING_KEYS`): exactly one, or none.
4. **A caller's kind** is its ``callers`` row's.
5. **A merge** (``merges``) is ``small`` when every caller the header names, on a command
   line or a self-naming line (rule 3's), is a small-variant caller and the header declares no
   structural-variant field (:func:`declares_sv`). The guard is there because a merged
   header can keep one input's ``##source`` and lose another's; the VCF spec requires a
   structural variant to be declared, so an input's structural variants leave their
   declarations behind.
6. **Otherwise no kind**, with the reason (``NO_CALLER_LINE`` and the constants beside it).

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
from .validators.header_extractors import SV_INFO_IDS, VCFHeader, declared_alt_ids, declared_info_ids

# Header keys whose line names the tool that wrote the file, as ``##source`` does, and the
# tool each names: DeepVariant writes no command line and no ``##source`` (measured
# 2026-10-09 over the cached heads).
SELF_NAMING_KEYS = {"DeepVariant_version": "DeepVariant"}

# The ALT ids a header declares for a structural variant (VCF 4.3, section 1.4.5).
SV_ALT_IDS = frozenset({"DEL", "DUP", "INS", "INV", "CNV", "BND"})

# Why a file has no kind. One per path that can decline; the claim's reason starts with it.
NO_CALLER_LINE = "no caller line"
SEVERAL_TOOLS = "more than one tool names itself"
UNREAD_STEP = "a command line names a tool the reader does not know"
NO_CALLER_ON_CHAIN = "no caller on the step chain"
NOT_IN_TABLE = "caller not in the kind table"
MIXED_MERGE = "a merge whose callers are not all small-variant callers"
SV_DECLARED = "a merge whose header declares structural-variant fields"
FALLBACK_DISAGREES = "the header's one other step is not borne out by the rest of the header"
PVAR = "not a VCF"


@dataclass(frozen=True)
class Caller:
    """One ``callers`` row: a tool, the pattern its names match, and the kind it calls (the row's ``reason`` documents it)."""

    name: str
    pattern: re.Pattern[str]
    kind: str


@dataclass(frozen=True)
class CallerKinds:
    """``rules/caller_kinds.yaml``, loaded: the callers, and the steps that keep or merge a callset."""

    callers: tuple[Caller, ...]
    keeps_kind: frozenset[str]
    merges: frozenset[str]

    def caller(self, name: str) -> Caller | None:
        """The row whose pattern matches ``name`` whole, case-insensitively, or None."""
        return next((c for c in self.callers if c.pattern.fullmatch(name)), None)

    def keeps(self, tool: str) -> bool:
        return tool.lower() in self.keeps_kind

    def merges_callsets(self, tool: str) -> bool:
        return tool.lower() in self.merges


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
    """``rules/caller_kinds.yaml``, checked: each row gives a reason, each kind a term of ``variant_kind_enum``, no name twice.

    Raises ValueError on a row that breaks one.
    """
    raw = yaml.load(
        files(f"{__package__}.rules").joinpath(CALLER_KINDS).read_text(), Loader=unique_key_loader(CALLER_KINDS)
    )
    vocabulary = dimension_values("variant_kind")
    callers = []
    for row in raw["callers"]:
        if not str(row.get("reason") or "").strip():
            raise ValueError(f"{CALLER_KINDS}: {row['name']} gives no reason for its kind")
        if row["kind"] not in vocabulary:
            raise ValueError(f"{CALLER_KINDS}: {row['name']}'s kind {row['kind']!r} is not a term of variant_kind_enum")
        callers.append(Caller(row["name"], re.compile(row["pattern"], re.IGNORECASE), row["kind"]))
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
    return bool(declared_info_ids(header, SV_INFO_IDS) or declared_alt_ids(header, SV_ALT_IDS))


def self_named_tools(header: VCFHeader) -> list[str]:
    """The distinct tools the header's ``##source`` and :data:`SELF_NAMING_KEYS` lines name, in header order."""
    names = list(header.sources)
    names += [SELF_NAMING_KEYS[key] for key in header.meta_keys if key in SELF_NAMING_KEYS]
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
        caller, how, fallback = _header_caller(steps, table, f"no one step made this file ({outcome})")
    else:
        caller, how, fallback = _walk_back(step, steps, table)
    if caller is None:
        # Rule 3 where no command line names a caller: the tools the header names itself.
        return _from_sources(header, table) if self_named_tools(header) else _none(BY_STEP, NO_CALLER_ON_CHAIN, how)
    if table.merges_callsets(caller.tool):
        return _merge(header, steps, caller, table)
    row = table.caller(caller.tool)
    if row is None:
        return _none(BY_STEP, NOT_IN_TABLE, f"{caller.tool} ({how})")
    if fallback and (doubt := _fallback_doubt(header, row, table)):
        return _none(BY_STEP, FALLBACK_DISAGREES, f"{caller.tool} ({how}); {doubt}")
    return KindReading(BY_STEP, row.kind, f"called by {row.name} ({how})")


def _fallback_doubt(header: VCFHeader, row: Caller, table: CallerKinds) -> str | None:
    """Why the fallback's one other step cannot be taken as the caller, as rule 5 doubts a merge; None where nothing does.

    A small-variant caller's header that declares a structural-variant field, or a header naming
    itself a tool that is not a caller of the same kind, leaves the kind open.
    """
    if row.kind == "small" and declares_sv(header):
        return "the header declares structural-variant fields"
    named = [n for n in self_named_tools(header) if not table.keeps(n) and not table.merges_callsets(n)]
    other = [n for n in named if getattr(table.caller(n), "kind", None) != row.kind]
    return f"the header also names {', '.join(other)}" if other else None


def _walk_back(step: Step, steps: list[Step], table: CallerKinds) -> tuple[Step | None, str, bool]:
    """The caller behind the producing ``step``, how it was reached, and whether by rule 2's fallback; None and why where none is."""
    path = [step.tool]
    seen = {step}
    while table.keeps(step.tool):
        wrote = {data_name(i) for i in step.inputs}
        before = [s for s in steps if s.output is not None and data_name(s.output) in wrote and s not in seen]
        if len(before) != 1:
            why = "several steps" if before else "no step in the header"
            return _header_caller(steps, table, f"producing step {' <- '.join(path)}, whose input {why} wrote")
        step = before[0]
        seen.add(step)
        path.append(step.tool)
    if len(path) == 1:
        return step, "the producing step", False
    return step, f"producing step {' <- '.join(path)}", False


def _header_caller(steps: list[Step], table: CallerKinds, why: str) -> tuple[Step | None, str, bool]:
    """Where the chain names no caller: rule 2's fallback (module docstring). ``why`` says how the chain fell short.

    The flag is True where the one other step is taken, which :func:`_fallback_doubt` then checks.
    """
    others = [s for s in steps if not table.keeps(s.tool)]
    merge = next((s for s in others if table.merges_callsets(s.tool)), None)
    if merge is not None:
        return merge, f"{why}; a {merge.tool} in the header", False
    tools = list(dict.fromkeys(s.tool for s in others))
    if len(tools) != 1:
        return None, f"{why}; the header records {len(tools)} other tools", False
    return others[0], f"{why}; {tools[0]}, the header's one other step", True


def _from_sources(header: VCFHeader, table: CallerKinds) -> KindReading:
    """Rule 3: the one tool the header's self-naming lines name, where no command line names a caller.

    Spellings of one caller (``Sniffles2_2.0.6`` and ``Sniffles2_2.0.7``) are one tool, the
    table's row; a spelling the table does not list is a tool of its own.
    """
    spellings = self_named_tools(header)
    if not spellings:
        return _none(BY_SOURCE, NO_CALLER_LINE, "no command line, ##source or tool version line")
    tools = {(row.name if (row := table.caller(name)) else name): row for name in spellings}
    if len(tools) > 1:
        return _none(BY_SOURCE, SEVERAL_TOOLS, ", ".join(spellings))
    ((tool, row),) = tools.items()
    if row is None:
        return _none(BY_SOURCE, NOT_IN_TABLE, tool)
    return KindReading(BY_SOURCE, row.kind, f"called by {row.name} (named by the header: {', '.join(spellings)})")


def _merge(header: VCFHeader, steps: Iterable[Step], merge: Step, table: CallerKinds) -> KindReading:
    """Rule 5 (module docstring): every tool the header names, less the steps that keep or merge, read as callers."""
    tools = dict.fromkeys([s.tool for s in steps] + self_named_tools(header))
    named = [t for t in tools if not table.keeps(t) and not table.merges_callsets(t)]
    if not named:
        return _none(BY_MERGE, NO_CALLER_LINE, f"{merge.tool} of inputs whose callers the header does not name")
    rows = [table.caller(n) for n in named]
    if any(r is None or r.kind != "small" for r in rows):
        return _none(BY_MERGE, MIXED_MERGE, f"{merge.tool} of {', '.join(named)}")
    if declares_sv(header):
        return _none(BY_MERGE, SV_DECLARED, f"{merge.tool} of {', '.join(named)}")
    callers = ", ".join(dict.fromkeys(r.name for r in rows if r is not None))
    return KindReading(BY_MERGE, "small", f"{merge.tool} of calls by {callers}; no structural-variant field declared")


def _unread_tools(header: VCFHeader) -> str:
    tools = dict.fromkeys(c.step.tool or c.key for c in header.commands if not c.step.read)
    return ", ".join(tools)


def _none(by: str, reason: str, detail: str) -> KindReading:
    return KindReading(by, None, f"{reason}: {detail}")
