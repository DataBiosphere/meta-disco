"""The resolution rule and the translation of a line into claims, shared by reconcile's file and donor records (#693)."""

from __future__ import annotations

import json
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field

from .models import (
    CLASSIFIED,
    CONFLICT,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_PUBLISHED_VALUE,
    UNMAPPED,
    settled_value,
)
from .rule_engine import make_claim
from .schema_vocab import most_specific
from .source_evidence import EvidenceEntry
from .value_map import ValueMap, claims_from


def identifier_key(identifier: dict) -> str:
    """An ``EntityIdentifier`` dict's canonical JSON spelling: equal exactly when the identifiers are."""
    return json.dumps(identifier, sort_keys=True)


def declaration(entry: dict, slot: str | None = None) -> str | None:
    """What a claim, or inference's conclusion, declares for resolution: a value, ``not_applicable``, or None.

    Reads ``value`` then ``status``. ``not_classified`` declares no answer (4.6) and
    ``conflict`` is not a declaration, so both are None, like a claim declaring nothing.
    A conclusion carries a value only when it is ``classified`` (the schema's rule), so
    one function serves both. Given the ``slot``, a record's stored value is read as
    resolution reads it (``models.settled_value``): pass it for an entry read off a record,
    as a reconciled slot's ``inferred`` is.

    A donor's parent claim declares an identifier, a dict (#582): it is read as its canonical
    JSON spelling (:func:`identifier_key`), so every declaration is a string resolution can compare.
    """
    if isinstance(entry.get("value"), dict):
        return identifier_key(entry["value"])
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
       the value (4.4). A slot with no vocabulary (a donor's family, #582) has no
       hierarchy, so two of its values always conflict.
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


@dataclass(slots=True)
class SlotEvidence:
    """What the sources said about one slot of one record: a file's, or a donor's (#693)."""

    claims: list[dict] = field(default_factory=list)
    # Source types that spoke to the slot with a value no authored row reads.
    unreviewed: set[str] = field(default_factory=set)
    # Source types that spoke to the slot with a value whose authored row declares
    # nothing for it (`declares: {}`, or declares only other slots): reviewed, no claim.
    no_claim: set[str] = field(default_factory=set)


# The slot evidence of a slot no source spoke to. Shared and never written: every reader
# only reads it.
NO_EVIDENCE = SlotEvidence()


def translate(
    record_slots: dict[str, SlotEvidence],
    entry: EvidenceEntry,
    source_type: str,
    join_key: str,
    table: ValueMap,
    match_exact: bool = True,
) -> set[str]:
    """Add a matched line's claims to its record's slots, or mark the slot unreviewed by its source type.

    ``source_type`` and ``join_key`` are the line's evidence file's; a record is a file's or,
    from entity evidence (``reconcile_entities``, #693), a donor's. ``match_exact`` is whether
    the line's key equalled the record's as written; false where an identifier rule rewrote it.

    The row is selected here and handed to ``claims_from``, because an authored row
    declaring nothing (``declares: {}``) yields no claim and is still reviewed.

    A line no authored row reads makes no claim (contract 3.7). From the published source
    it still moves the slot (to ``conflict`` or ``not_classified``), so what it said is
    kept in the slot's evidence as an ``unmapped`` entry — its source, raw value and join,
    and no value, status or rule — and the record shows why on its own (6.10). It declares
    nothing, so resolution does not read it. Another source's unreviewed value moves
    nothing, is counted in the report, and is not written to the record.

    Returns the slots the line's claims were made on.
    """
    row = table.select(entry.field, entry.raw_value, entry.source.name, entry.source.dataset)
    if row is None or not row.authored:
        said = record_slots[entry.field]
        said.unreviewed.add(source_type)
        if source_type != SOURCE_PUBLISHED_VALUE:
            return set()
        seen = make_claim(
            source_type=source_type,
            state=UNMAPPED,
            source=entry.source,
            raw_value=entry.raw_value,
            join_key=join_key,
            match_exact=match_exact,
        )
        if seen not in said.claims:
            said.claims.append(seen)
        return set()
    if entry.field not in row.declares:
        record_slots[entry.field].no_claim.add(source_type)
    claimed = set()
    for slot, claim in claims_from(entry, source_type, table, join_key=join_key, row=row, match_exact=match_exact):
        claimed.add(slot)
        existing = record_slots[slot].claims
        if claim not in existing:
            existing.append(claim)
    return claimed
