"""A VCF's variant kind, the row's in ``rules/callers.yaml`` for the caller :func:`.callers.find_caller` finds (#654).

Rule 2's fallback is refused where the rest of the header doubts it; a merge is ``small`` only
where every named caller is and no structural-variant field is declared: a merged header can
lose an input's ``##source``, but the VCF spec requires an SV to be declared. Else ``not_classified``.
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
)
from .validators.header_extractors import SV_INFO_IDS, VCFHeader, declared_alt_ids, declared_info_ids

# The ALT ids a header declares for a structural variant (VCF 4.3, section 1.4.5).
SV_ALT_IDS = frozenset({"DEL", "DUP", "INS", "INV", "CNV", "BND"})

# Why a file has no kind, beyond why it has no caller; the claim's reason starts with it.
MIXED_MERGE = "a merge whose callers are not all small-variant callers"
SV_DECLARED = "a merge whose header declares structural-variant fields"


def declares_sv(header: VCFHeader) -> bool:
    """Whether the header declares a structural-variant ``##INFO`` field or ``##ALT`` id."""
    return bool(declared_info_ids(header, SV_INFO_IDS) or declared_alt_ids(header, SV_ALT_IDS))


def read_kind(header: VCFHeader, found: Found | FoundMerge | NotFound) -> Reading:
    """The variant kind ``header`` gives, from the caller ``found`` in it, by the module docstring's rules."""
    if isinstance(found, NotFound):
        return Reading(found.by, None, found.reason)
    if isinstance(found, FoundMerge):
        return _merge(header, found)
    row = found.row
    if found.fallback and (doubt := _fallback_doubt(header, row)):
        return Reading(found.by, None, f"{FALLBACK_DISAGREES}: {found.tool} ({found.how}); {doubt}")
    return Reading(found.by, row.kind, f"called by {row.name} ({found.how})")


def _fallback_doubt(header: VCFHeader, row: Caller) -> str | None:
    """Why the fallback's step is not the caller: SV fields beside a small caller, or a tool of another kind named; else None."""
    if row.kind == "small" and declares_sv(header):
        return "the header declares structural-variant fields"
    other = others_disagreeing(header, row, "kind")
    return f"the header also names {', '.join(other)}" if other else None


def _merge(header: VCFHeader, found: FoundMerge) -> Reading:
    """Rule 5 for the kind: small where every named caller is a small-variant caller and no SV field is declared."""
    named = ", ".join(found.named)
    rows = [r for r in found.rows if r is not None]
    if None in found.rows or any(r.kind != "small" for r in rows):
        return Reading(BY_MERGE, None, f"{MIXED_MERGE}: {found.merge} of {named}")
    if declares_sv(header):
        return Reading(BY_MERGE, None, f"{SV_DECLARED}: {found.merge} of {named}")
    callers = ", ".join(dict.fromkeys(r.name for r in rows))
    return Reading(BY_MERGE, "small", f"{found.merge} of calls by {callers}; no structural-variant field declared")
