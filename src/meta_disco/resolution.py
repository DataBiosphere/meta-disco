"""The resolution rule: one slot's answer from every input's declaration (#432, #473, #571, #693).

Shared by reconcile's file records (``reconcile``) and its donor records
(``reconcile_entities``), so a donor's slot is settled by the same rule as a file's
dimension. ``reconcile`` re-exports both functions, where its callers and the docs cite them.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet

from .models import CLASSIFIED, CONFLICT, NOT_APPLICABLE, NOT_CLASSIFIED, settled_value
from .schema_vocab import most_specific


def declaration(entry: dict, slot: str | None = None) -> str | None:
    """What a claim, or inference's conclusion, declares for resolution: a value, ``not_applicable``, or None.

    Reads ``value`` then ``status``. ``not_classified`` declares no answer (4.6) and
    ``conflict`` is not a declaration, so both are None, like a claim declaring nothing.
    A conclusion carries a value only when it is ``classified`` (the schema's rule), so
    one function serves both. Given the ``slot``, a record's stored value is read as
    resolution reads it (``models.settled_value``): pass it for an entry read off a record,
    as a reconciled slot's ``inferred`` is.
    """
    if entry.get("value") is not None:
        return entry["value"] if slot is None else settled_value(slot, entry["value"])
    if entry.get("status") == NOT_APPLICABLE:
        return NOT_APPLICABLE
    return None


def settle(
    slot: str, inference_conflict: bool, declared: AbstractSet[str], mixed: bool, published_unreviewed: bool
) -> tuple[str, str | None]:
    """One slot's ``(status, value)`` from every input's declaration: the whole resolution rule.

    ``declared`` holds each input's declaration (a value or ``not_applicable``: inference's,
    every source's, every inherited one's); ``mixed`` whether an inherited declaration is
    the state ``mixed``. In order:

    1. Inference itself concluded ``conflict``: the conflict stands, whatever a source
       says — agreeing with one of two disagreeing rules is not resolving them, which 4.7
       reserves for a curator rule (open question 1, decided 2026-09-22).
    2. The declarations differ — two values, or a value beside ``not_applicable`` (4.6):
       ``conflict``, unless the values nest in the slot's ``is_a`` hierarchy
       (:func:`~.schema_vocab.most_specific`, #473): ``CHM13`` beside
       ``T2T-CHM13v2.0`` is one answer at two levels of detail, and the deepest is
       the value (4.4).
    3. An inherited ``mixed`` beside any declaration: ``conflict``, since one value
       contradicts a lineage that has none, and ``not_applicable`` stands for the values
       it would contradict (4.9). Alone it declares nothing, and the slot goes on.
    4. The published source spoke with a value no authored row reads (unreviewed): a
       ``conflict`` if any other input declared something, else ``not_classified`` —
       missing work, not a challenge.
    5. One value: ``classified``. Otherwise ``not_applicable`` if anyone declared it, and
       ``not_classified`` if nobody declared anything. ``not_classified`` never conflicts
       and yields to ``not_applicable`` (4.6).

    ``value`` is null unless the status is ``classified``.
    """
    if inference_conflict:
        return CONFLICT, None
    if len(declared) > 1:
        deepest = most_specific(slot, declared)
        if deepest is None:
            return CONFLICT, None
        declared = {deepest}
    if mixed and declared:
        return CONFLICT, None
    if published_unreviewed:
        return (CONFLICT, None) if declared else (NOT_CLASSIFIED, None)
    if not declared:
        return NOT_CLASSIFIED, None
    (only,) = declared
    if only == NOT_APPLICABLE:
        return NOT_APPLICABLE, None
    return CLASSIFIED, only
