"""The caller that made a VCF, found in its header (#654, #658), for the dimensions read from it.

A VCF's records cannot settle what its caller calls: a mixed callset shows a structural
variant in its first hundred records only by chance (#630). The caller can, because each caller
the table lists calls one kind of variant, of one origin (one whose origin turns on a mode is
listed with its ``somatic_mode``; one that mixes origins is not listed). So ``variant_kind`` (:mod:`.variant_kinds`) and
``variant_origin`` (:mod:`.variant_origins`) are the caller's, looked up in
``rules/callers.yaml``, and the caller is found in the header, in this order:

1. **The producing step**, the end of the header's data flow (``producer_steps.producing_step``).
2. **Walked back** from it through steps that keep their input's calls (``keeps_calls``), each to the
   step that wrote its input, to the first step that does not. That step is the caller.
   Where the chain names none — no one producing step (several bcftools ``view`` steps
   writing to stdout, or a step whose output the file was renamed from), or a kept step
   whose input no step the header records wrote (T2T's
   ``SelectVariants`` reads a callset whose ``GenotypeGVCFs`` line is not in the header) —
   the header's other steps, those that do not keep calls, name it: a merge among them
   (rule 5), else the one tool they are (:attr:`Found.fallback`), which each dimension checks
   against the rest of the header.
3. **Where no command line names a caller** (the header records none, or rules 1 and 2 find
   none), the one tool its ``##source`` lines, and a ``##DeepVariant_version`` line, name
   (:data:`SELF_NAMING_KEYS`), less the steps that keep or merge calls: exactly one, or none.
4. **The caller's row** in the table gives each dimension its value.
5. **A merge** (``merges``) is settled by every caller the header names, on a command line or a
   self-naming line (rule 3's) (:class:`FoundMerge`); each dimension says how.
6. **Otherwise no caller**, with the reason (:class:`NotFound`, ``NO_CALLER_LINE`` and the
   constants beside it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

import yaml

from .producer_steps import NO_COMMAND_LINE, NOT_A_VCF, UNKNOWN_TOOL, data_name, producing_step, steps_of
from .schema_vocab import dimension_values
from .slot_map import unique_key_loader
from .validators.command_lines import Step
from .validators.header_extractors import VCFHeader

# Header keys whose line names the tool that wrote the file, as ``##source`` does, and the
# tool each names: DeepVariant writes no command line and no ``##source`` (measured
# 2026-10-09 over the cached heads).
SELF_NAMING_KEYS = {"DeepVariant_version": "DeepVariant"}

# Why a file has no caller. One per path that can decline; a claim's reason starts with it.
NO_CALLER_LINE = "no caller line"
SEVERAL_TOOLS = "more than one tool names itself"
UNREAD_STEP = "a command line names a tool the reader does not know"
NO_CALLER_ON_CHAIN = "no caller on the step chain"
NOT_IN_TABLE = "caller not in the caller table"
PVAR = "not a VCF"
# Why a dimension refuses rule 2's fallback (:attr:`Found.fallback`), where the rest of the header doubts it.
FALLBACK_DISAGREES = "the header's one other step is not borne out by the rest of the header"

# Which rule found the caller: the producing step's (rules 1, 2 and 4), the one tool the
# header names where no command line names one (3 and 4), or a merge's callers (5). Each
# dimension has a content rule of its own in ``code_rules`` for each.
BY_STEP = "step"
BY_SOURCE = "source"
BY_MERGE = "merge"


@dataclass(frozen=True)
class SomaticMode:
    """A caller's somatic mode: the flags that turn it on, and the ``##source`` spellings of versions without it."""

    flags: frozenset[str]
    predates: frozenset[str]
    reason: str = ""


@dataclass(frozen=True)
class Caller:
    """One ``callers`` row: a tool, the pattern its names match, the kind and origin it calls, its somatic mode, and why."""

    name: str
    pattern: re.Pattern[str]
    kind: str
    origin: str
    somatic_mode: SomaticMode | None = None
    reason: str = ""


@dataclass(frozen=True)
class Callers:
    """``rules/callers.yaml``, loaded: the callers, and the steps that keep or merge a callset."""

    callers: tuple[Caller, ...]
    keeps_calls: frozenset[str]
    merges: frozenset[str]

    def caller(self, name: str) -> Caller | None:
        """The row whose pattern matches ``name`` whole, case-insensitively, or None."""
        return next((c for c in self.callers if c.pattern.fullmatch(name)), None)

    def keeps(self, tool: str) -> bool:
        return tool.lower() in self.keeps_calls

    def merges_callsets(self, tool: str) -> bool:
        return tool.lower() in self.merges

    def may_call(self, tool: str) -> bool:
        """Whether ``tool`` can be a caller: it is not a step that keeps or merges calls."""
        return not self.keeps(tool) and not self.merges_callsets(tool)


@dataclass(frozen=True)
class Found:
    """One caller found: by which rule, its row, the tool as the header names it, and how it was reached.

    ``fallback`` is True where rule 2 took the header's one other step, which each dimension
    then checks against the rest of the header.
    """

    by: str
    row: Caller
    tool: str
    how: str
    fallback: bool = False


@dataclass(frozen=True)
class FoundMerge:
    """Rule 5: a merge step, and every caller the header names (less the steps that keep or merge), each with its row or None."""

    merge: str
    named: tuple[str, ...]
    rows: tuple[Caller | None, ...]


@dataclass(frozen=True)
class NotFound:
    """No caller: by which rule, and why (the reason starts with one of the module's constants)."""

    by: str
    reason: str


@dataclass(frozen=True)
class Reading:
    """What a header gives one dimension read from its caller: a value, or None with the reason; which rule read it (:data:`BY_STEP`…); and why."""

    by: str
    value: str | None
    reason: str


CALLERS = "callers.yaml"

# How a dimension's reading names the callers it was read from, where it gives a value:
# ``called by <name> (<how>)`` for one caller, ``<merge> of calls by <name>, <name>; ...``
# for a merge's (``variant_kinds``, ``variant_origins``). :func:`callers_in_reason` reads them.
_CALLED_BY = re.compile(r"called by (.+?) \(")
_MERGE_OF = re.compile(r"\S+ of calls by (.+?); ")


def callers_in_reason(reason: str) -> list[str]:
    """The caller names a classified kind or origin reading's ``reason`` gives, empty for any other reason."""
    if called := _CALLED_BY.match(reason):
        return [called.group(1)]
    if merged := _MERGE_OF.match(reason):
        return merged.group(1).split(", ")
    return []


@cache
def load_callers() -> Callers:
    """``rules/callers.yaml``, checked: each row and somatic mode gives a reason, each kind and origin a term of its enum, no name twice.

    Raises ValueError on a row that breaks one.
    """
    raw = yaml.load(files(f"{__package__}.rules").joinpath(CALLERS).read_text(), Loader=unique_key_loader(CALLERS))
    vocabulary = {"kind": dimension_values("variant_kind"), "origin": dimension_values("variant_origin")}
    callers = []
    for row in raw["callers"]:
        if not str(row.get("reason") or "").strip():
            raise ValueError(f"{CALLERS}: {row['name']} gives no reason for its kind and origin")
        for key, terms in vocabulary.items():
            if row[key] not in terms:
                raise ValueError(f"{CALLERS}: {row['name']}'s {key} {row[key]!r} is not a term of variant_{key}_enum")
        pattern = re.compile(row["pattern"], re.IGNORECASE)
        somatic_mode = _somatic_mode(row, pattern)
        reason = " ".join(str(row["reason"]).split())
        callers.append(Caller(row["name"], pattern, row["kind"], row["origin"], somatic_mode, reason))
    names = [c.name for c in callers]
    if len(set(names)) != len(names):
        raise ValueError(f"{CALLERS}: a caller is listed twice")
    return Callers(
        tuple(callers),
        frozenset(t.lower() for t in raw["keeps_calls"]),
        frozenset(t.lower() for t in raw["merges"]),
    )


def _somatic_mode(row: dict, pattern: re.Pattern[str]) -> SomaticMode | None:
    """A row's ``somatic_mode``, checked: a reason, at least one ``-`` flag, and each ``predates`` spelling one the row's pattern matches.

    Raises ValueError on a mode that breaks one.
    """
    mode = row.get("somatic_mode")
    if mode is None:
        return None
    if not str(mode.get("reason") or "").strip():
        raise ValueError(f"{CALLERS}: {row['name']}'s somatic_mode gives no reason")
    flags = frozenset(mode.get("flags") or ())
    if not flags or not all(f.startswith("-") for f in flags):
        raise ValueError(f"{CALLERS}: {row['name']}'s somatic_mode names no flags, or one not starting with -")
    predates = list(mode.get("predates") or ())
    if unmatched := [s for s in predates if not pattern.fullmatch(s)]:
        raise ValueError(
            f"{CALLERS}: {row['name']}'s somatic_mode predates {unmatched}, which its pattern does not match"
        )
    return SomaticMode(flags, frozenset(s.lower() for s in predates), " ".join(str(mode["reason"]).split()))


def self_named_tools(header: VCFHeader) -> list[str]:
    """The distinct tools the header's ``##source`` and :data:`SELF_NAMING_KEYS` lines name, in header order."""
    names = list(header.sources)
    names += [SELF_NAMING_KEYS[key] for key in header.meta_keys if key in SELF_NAMING_KEYS]
    return list(dict.fromkeys(names))


def named_callers(header: VCFHeader, table: Callers) -> list[str]:
    """The tools the header names itself that can be callers (:meth:`Callers.may_call`): what rules 2, 3 and 5 read."""
    return [n for n in self_named_tools(header) if table.may_call(n)]


def find_caller(header: VCFHeader, file_name: str) -> Found | FoundMerge | NotFound:
    """The caller ``header`` names for the file ``file_name``, by the module docstring's rules."""
    table = load_callers()
    step, outcome = producing_step(header, file_name)
    if outcome == NOT_A_VCF:
        return NotFound(BY_STEP, f"{PVAR}: a PLINK 2 .pvar records no step of its own")
    if outcome == NO_COMMAND_LINE:
        return _from_sources(header, table)
    if outcome == UNKNOWN_TOOL:
        return NotFound(BY_STEP, f"{UNREAD_STEP}: {_unread_tools(header)}")
    steps = steps_of(header) or []
    if step is None:
        caller, how, fallback = _header_caller(steps, table, f"no one step made this file ({outcome})")
    else:
        caller, how, fallback = _walk_back(step, steps, table)
    if caller is None:
        # Rule 3 where no command line names a caller: the tools the header names itself.
        if named_callers(header, table):
            return _from_sources(header, table)
        return NotFound(BY_STEP, f"{NO_CALLER_ON_CHAIN}: {how}")
    if table.merges_callsets(caller.tool):
        return _merge(header, steps, caller, table)
    row = table.caller(caller.tool)
    if row is None:
        return NotFound(BY_STEP, f"{NOT_IN_TABLE}: {caller.tool} ({how})")
    return Found(BY_STEP, row, caller.tool, how, fallback)


def others_disagreeing(header: VCFHeader, row: Caller, field: str) -> list[str]:
    """The :func:`named_callers` whose ``field`` (``kind`` or ``origin``) is not ``row``'s.

    What rule 2's fallback is checked against: a tool the table does not list disagrees.
    """
    table = load_callers()
    return [n for n in named_callers(header, table) if getattr(table.caller(n), field, None) != getattr(row, field)]


def _walk_back(step: Step, steps: list[Step], table: Callers) -> tuple[Step | None, str, bool]:
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


def _header_caller(steps: list[Step], table: Callers, why: str) -> tuple[Step | None, str, bool]:
    """Where the chain names no caller: rule 2's fallback (module docstring). ``why`` says how the chain fell short.

    The flag is True where the one other step is taken, which each dimension then checks.
    """
    others = [s for s in steps if not table.keeps(s.tool)]
    merge = next((s for s in others if table.merges_callsets(s.tool)), None)
    if merge is not None:
        return merge, f"{why}; a {merge.tool} in the header", False
    tools = list(dict.fromkeys(s.tool for s in others))
    if len(tools) != 1:
        return None, f"{why}; the header records {len(tools)} other tools", False
    return others[0], f"{why}; {tools[0]}, the header's one other step", True


def _from_sources(header: VCFHeader, table: Callers) -> Found | NotFound:
    """Rule 3: the one tool the header's self-naming lines name, less steps that keep or merge, where no command line names a caller.

    Spellings of one caller (``Sniffles2_2.0.6`` and ``Sniffles2_2.0.7``) are one tool, the
    table's row; a spelling the table does not list is a tool of its own.
    """
    spellings = named_callers(header, table)
    if not spellings:
        if steps_only := self_named_tools(header):
            detail = f"the header names only steps that keep or merge calls: {', '.join(steps_only)}"
            return NotFound(BY_SOURCE, f"{NO_CALLER_LINE}: {detail}")
        return NotFound(BY_SOURCE, f"{NO_CALLER_LINE}: no command line, ##source or tool version line")
    tools = {(row.name if (row := table.caller(name)) else name): row for name in spellings}
    if len(tools) > 1:
        return NotFound(BY_SOURCE, f"{SEVERAL_TOOLS}: {', '.join(spellings)}")
    ((tool, row),) = tools.items()
    if row is None:
        return NotFound(BY_SOURCE, f"{NOT_IN_TABLE}: {tool}")
    return Found(BY_SOURCE, row, tool, f"named by the header: {', '.join(spellings)}")


def _merge(header: VCFHeader, steps: list[Step], merge: Step, table: Callers) -> FoundMerge | NotFound:
    """Rule 5 (module docstring): every tool the header names, less the steps that keep or merge, read as callers."""
    tools = dict.fromkeys([s.tool for s in steps] + self_named_tools(header))
    named = [t for t in tools if table.may_call(t)]
    if not named:
        return NotFound(BY_MERGE, f"{NO_CALLER_LINE}: {merge.tool} of inputs whose callers the header does not name")
    return FoundMerge(merge.tool, tuple(named), tuple(table.caller(n) for n in named))


def _unread_tools(header: VCFHeader) -> str:
    tools = dict.fromkeys(c.step.tool or c.key for c in header.commands if not c.step.read)
    return ", ".join(tools)
