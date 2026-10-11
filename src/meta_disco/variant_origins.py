"""A VCF's variant origin, the row's in ``rules/callers.yaml`` for the caller :func:`.callers.find_caller` finds (#658).

- **A somatic mode** (a row's ``somatic_mode``) leaves the origin open unless the caller's command
  line shows none of its flags, or a ``##source`` spelling predates the mode (:func:`_mode_doubt`).
- **A germline reading** is refused where the header declares the ``SOMATIC`` INFO flag or
  Mutect2's tumour / normal sample lines (:func:`declares_somatic`).
- **Rule 2's fallback** is refused where the header names a tool of another origin.
- **A merge** is ``germline`` where every named caller is and nothing somatic is declared; there a
  command line clears a mode for its own input only, so only a ``predates`` spelling clears it.

Otherwise ``not_classified``: never guessed.
"""

from __future__ import annotations

from .callers import (
    BY_MERGE,
    FALLBACK_DISAGREES,
    Caller,
    Found,
    FoundMerge,
    NotFound,
    Reading,
    others_disagreeing,
    self_named_tools,
)
from .validators.header_extractors import VCFHeader, declared_info_ids

GERMLINE = "germline"

# What a somatic callset declares: the VCF spec's reserved INFO flag (VCF 4.3, section 1.6.1),
# and the keys Mutect2 writes naming its tumour and normal samples.
SOMATIC_INFO_IDS = frozenset({"SOMATIC"})
SOMATIC_META_KEYS = frozenset({"tumor_sample", "normal_sample"})

# Why a file has no origin, beyond why it has no caller (``callers.NO_CALLER_LINE`` and the
# constants beside it); the claim's reason starts with it.
SOMATIC_MODE = "the caller was run in its somatic mode"
MODE_NOT_STATED = "the caller has a somatic mode and the header does not say which it ran in"
SOMATIC_DECLARED = "the header declares somatic fields"
MIXED_MERGE = "a merge whose callers are not all germline callers"


def declares_somatic(header: VCFHeader) -> bool:
    """Whether the header declares the ``SOMATIC`` INFO flag or a ``##tumor_sample`` / ``##normal_sample`` line."""
    return bool(declared_info_ids(header, SOMATIC_INFO_IDS) or SOMATIC_META_KEYS.intersection(header.meta_keys))


def read_origin(header: VCFHeader, found: Found | FoundMerge | NotFound) -> Reading:
    """The variant origin ``header`` gives, from the caller ``found`` in it, by the module docstring's rules."""
    if isinstance(found, NotFound):
        return Reading(found.by, None, found.reason)
    if isinstance(found, FoundMerge):
        return _merge(header, found)
    row = found.row
    if doubt := _mode_doubt(header, row):
        return Reading(found.by, None, f"{doubt} ({found.how})")
    if row.origin == GERMLINE and declares_somatic(header):
        return Reading(found.by, None, f"{SOMATIC_DECLARED}: called by {row.name} ({found.how})")
    if found.fallback and (other := others_disagreeing(header, row, "origin")):
        detail = f"{found.tool} ({found.how}); the header also names {', '.join(other)}"
        return Reading(found.by, None, f"{FALLBACK_DISAGREES}: {detail}")
    return Reading(found.by, row.origin, f"called by {row.name} ({found.how})")


def _mode_doubt(header: VCFHeader, row: Caller, merged: bool = False) -> str | None:
    """Why a caller with a somatic mode leaves the origin open, starting with the reason's constant; None where its mode is known to be off.

    ``merged``: the header is a merge's, where a command line without the flags clears the mode
    for one input only and another input's line may be lost, so only ``predates`` clears it.
    """
    mode = row.somatic_mode
    if mode is None:
        return None
    lines = [c for c in header.commands if row.pattern.fullmatch(c.step.tool)]
    used = sorted({w.split("=", 1)[0] for c in lines for w in c.words if _turns_on(w.split("=", 1)[0], mode.flags)})
    if used:
        return f"{SOMATIC_MODE}: {row.name} with {', '.join(used)}"
    if lines and not merged:
        return None
    spellings = [s for s in self_named_tools(header) if row.pattern.fullmatch(s)]
    if spellings and all(s.lower() in mode.predates for s in spellings):
        return None
    if merged:
        return f"{MODE_NOT_STATED}: {row.name}, in a merge whose inputs' command lines may be lost"
    return f"{MODE_NOT_STATED}: {row.name}, no command line of it"


def _turns_on(option: str, flags: frozenset[str]) -> bool:
    """Whether ``option`` is one of ``flags``, or a ``--`` prefix of one, which argparse takes for it by default."""
    return option in flags or (option.startswith("--") and len(option) > 2 and any(f.startswith(option) for f in flags))


def _merge(header: VCFHeader, found: FoundMerge) -> Reading:
    """Rule 5 for the origin: germline where every named caller is a germline caller in its germline mode and nothing somatic is declared."""
    named = ", ".join(found.named)
    rows = [r for r in found.rows if r is not None]
    if None in found.rows or any(r.origin != GERMLINE for r in rows):
        return Reading(BY_MERGE, None, f"{MIXED_MERGE}: {found.merge} of {named}")
    for row in rows:
        if doubt := _mode_doubt(header, row, merged=True):
            return Reading(BY_MERGE, None, f"{doubt} ({found.merge} of {named})")
    if declares_somatic(header):
        return Reading(BY_MERGE, None, f"{SOMATIC_DECLARED}: {found.merge} of {named}")
    callers = ", ".join(dict.fromkeys(r.name for r in rows))
    return Reading(BY_MERGE, GERMLINE, f"{found.merge} of calls by {callers}; no somatic field declared")
