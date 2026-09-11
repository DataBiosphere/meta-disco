"""Rule engine for classifying biological data files."""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .file_name import FileName, Format
from .models import (
    CLAIM_STATES,
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    EXTERNAL_SOURCE_TYPES,
    NO_VOCABULARY_TERM,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_FILENAME_RULE,
    SOURCE_HEADER_RULE,
    SOURCE_SIGNAL_INFERENCE,
    SOURCE_TYPES,
    UNMAPPED,
    ClaimSource,
    ClassificationResult,
    FileInfo,
    _assert_coherent,
    build_field_entry,
    require_join_key,
    status_for_value,
)
from .rule_loader import UnifiedRule, get_unified_rules

if TYPE_CHECKING:
    from .validators.header_extractors import SAMHeader, VCFHeader


# Tiers 1-3 are the rule tiers declared in ``unified_rules.yaml`` (extension /
# filename / header). Tier 4 is reserved for claims *derived from reading file
# bytes* (contig lengths, VCF ``##contig`` lengths, FASTA content, GFA segment
# tags) — a definitive signal that must out-rank even a disagreeing tier-3
# filename/header rule. ``evaluate_claims`` needs no special case for it: its
# "highest unique tier wins" rule already lets a tier-4 content claim override
# lower tiers (issue #226; the migration of the content sites onto ``add_claim``
# at this tier is #227).
CONTENT_TIER = 4

# The kind of source a rule claim comes from, by the rule's ``scope`` (#392).
# Scope, not tier: a rule's scope is its declaration of *what it reads*, whereas
# tier is only its precedence, and the two do not line up — tier 1 holds two
# filename-scope rules and tier 2 holds seven extension-scope rules. An extension
# is part of the filename, so both of those scopes are ``filename_rule``.
#
# Keys are a subset of ``RuleLoader.VALID_SCOPES``: ``file_size`` is absent
# because a rule matching on size alone reads neither a name nor a header, and no
# source_type honestly describes it. No such rule exists today, and
# test_rule_vocabulary pins every authored scope to this map, so authoring one
# fails in the suite rather than mislabelling its provenance in the output.
_RULE_SOURCE_TYPES = {
    "extension": SOURCE_FILENAME_RULE,
    "filename": SOURCE_FILENAME_RULE,
    "header": SOURCE_HEADER_RULE,
    "vcf_header": SOURCE_HEADER_RULE,
    "fastq_header": SOURCE_HEADER_RULE,
}


@dataclass
class ExtendedFileInfo:
    """Extended file information including header data for tier 3 rules.

    Carries the filename as a parsed :class:`FileName` fact (epic #242): the name is
    parsed once at the load boundary and threaded here, so ``classify_extended``
    reads the pre-parsed extension and the filename-pattern matcher reads ``name.raw``
    rather than re-parsing. Defaults to :data:`FileName.EMPTY` for a header-only call
    with no filename — which reads as an unresolved extension, so the engine falls
    back to the ``file_format`` the caller set.
    """

    name: FileName = FileName.EMPTY
    file_size: int | None = None
    dataset_title: str | None = None
    file_format: str | None = None
    # Canonical file Format derived from the extension (#243). Set by
    # classify_extended from the extension it settles on, so it always agrees
    # with file_format; None when that extension maps to no seeded format. Rules
    # key on it via `when.format`.
    format: Format | None = None

    # Header data (populated when available)
    bam_header: str | None = None
    vcf_header: str | None = None
    fastq_first_read: str | None = None
    fasta_contig_names: list[str] | None = None

    # Derived/cached fields
    platform: str | None = None

    # Lazily-parsed header caches, memoized on first use by the tier-3 matchers
    # (_match_bam_header/_match_vcf_header). init=False with no default preserves
    # the hasattr()-guarded lazy init — the attribute stays absent until the
    # first parse — while declaring the type for the checker. repr/compare are
    # excluded so an unset cache never trips repr()/==.
    _parsed_bam_header: "SAMHeader" = field(init=False, repr=False, compare=False)
    _parsed_vcf_header: "VCFHeader" = field(init=False, repr=False, compare=False)

    @property
    def file_size_gb(self) -> float | None:
        """Size in decimal GB (not GiB), derived from ``file_size`` bytes.

        Kept as a read-only accessor rather than stored state so bytes are the
        single source of truth; the assay-size rules author their thresholds in
        GB and read this (#241)."""
        return self.file_size / 1e9 if self.file_size is not None else None

    @classmethod
    def from_file_info(cls, file_info: FileInfo) -> "ExtendedFileInfo":
        """Create ExtendedFileInfo from a FileInfo object.

        Copies the parsed :class:`FileName` across as-is — no re-parse — so a name
        parsed once when the ``FileInfo`` was built is threaded through unchanged
        (epic #242).
        """
        return cls(
            name=file_info.name,
            file_size=file_info.file_size,
            dataset_title=file_info.dataset_title,
        )


def make_claim(
    *,
    source_type: str,
    reason: str | None = None,
    rule_id: str | None = None,
    tier: int | None = None,
    value: str | None = None,
    status: str | None = None,
    state: str | None = None,
    source: ClaimSource | None = None,
    raw_value: str | None = None,
    join_key: str | None = None,
    match_exact: bool | None = None,
) -> dict:
    """Construct one claim dict for ``field_evidence``, enforcing its invariants.

    The single construction site for a claim from *any* source (issue #392) —
    one of our rules, a content read, an external catalog, a submitter manifest,
    a curator table. Extends the rule-only record it grew from rather than
    running a second format alongside it, so every claim reaching
    ``evaluate_claims`` and the output ``evidence`` array has one shape.

    **What a claim declares.** Exactly one of a real ``value``, a ``status``, or
    a ``state`` — declaring two or none raises rather than silently picking one.
    ``value``/``status`` is the original invariant (the same one ``rule_loader``
    enforces for a rule's ``then`` vs ``then.status`` — epic #116 / #136), widened
    by one arm. A ``status`` claim declares a non-classified sentinel only
    (``not_applicable`` / ``not_classified`` — the authorable statuses, never
    ``classified``, which is expressed as a ``value`` claim). A ``state`` claim
    declares one of the claim states (``unmapped`` / ``no_vocabulary_term`` /
    ``declined``): the source was consulted and produced no vocabulary value.
    An unknown status or state raises here rather than being passed through as a
    free string; otherwise ``evaluate_claims`` would read the stray string as a
    real value and resolve the field CLASSIFIED to it — a silent wrong answer.

    A ``state`` claim declares nothing to resolution: ``_claim_declaration``
    reads ``value`` then ``status``, so it returns None for one, and
    ``evaluate_claims`` drops it before the tier math. It therefore cannot win a
    field, cannot create a conflict, and leaves a field carrying only such claims
    ``not_classified`` — while remaining visible in the evidence, and
    distinguishable both from a ``not_applicable`` claim and from no claim at all.

    **Who made it.** At least one producer handle is required: ``rule_id`` for one
    of our rules or content classifiers, ``source`` for an external source. An
    external claim carries *both*, and they answer different questions: ``source`` is
    where the raw value was read from, ``rule_id`` is the mapping rule that turned it
    into a vocabulary term. It is required on one — including for an identity
    mapping, since there is no implicit copy — except in state ``unmapped``, which
    means exactly that no mapping entry fired (#401). No rule id is *fabricated* for
    an external claim; the one it carries names a real, reviewable mapping. ``source_type`` is required
    on every claim and checked against the schema's ``source_type_enum``; it is
    deliberately not derived from ``tier``, which cannot tell ``contig_detection``
    from ``content_read`` (both at ``CONTENT_TIER``) nor either from
    ``signal_inference`` (at a rule tier without being a rule).

    **Tier.** Required on a claim that declares a ``value`` or ``status`` *and
    competes* — that is, one of ours. A claim that competes must never fall back to a
    tier-0 default (#150 — the silent default that let the #151 rGFA near-miss
    resolve to the wrong value). Rejected on a ``state`` claim, which does not
    compete and would only be carrying a number nothing reads, and rejected on a
    claim from an external ``source``, which does not compete either: epic #391
    settled on measured evidence that imports are not tier participants, so a tier on
    one is a number the importer must invent and the policy discards.
    ``evaluate_claims`` drops a claim carrying a ``source`` before the tier math, so
    an imported claim is inert there — visible in the evidence, never winning and
    never conflicting. Comparing the two resolutions is #396.

    **What the source said, and how it was matched.** ``raw_value`` records the
    source's own value before mapping, so ``Revio`` → ``PACBIO`` stays auditable;
    ``join_key`` and ``match_exact`` record which key attached the claim to our
    file and whether the match was exact (#390 — identity is the risky step, and
    it is per claim, not per source, so the two are not factorable into a claim
    file's envelope the way ``source`` is). These three are not yet tied to
    ``source``, so nothing stops a rule or content claim from carrying a
    ``join_key`` for a join that never happened. Deliberately left open until the
    first importer (#369/#394) shows what the constraint should be — the guard is
    cheap to add then and cheap to get wrong now.

    Keys whose argument is None are omitted from the returned dict, so a rule
    claim serializes exactly as it did before this record was extended, apart
    from its ``source_type``.
    """
    producer = rule_id or (source.name if source is not None else None)
    if not producer:
        raise ValueError(
            f"claim must identify its producer with rule_id or source (reason={reason!r}, source_type={source_type!r})"
        )
    declared = [d for d in (value, status, state) if d is not None]
    if len(declared) != 1:
        raise ValueError(
            f"claim from {producer!r} must declare exactly one of value/status/state "
            f"(got value={value!r}, status={status!r}, state={state!r})"
        )
    if status is not None and status not in (NOT_APPLICABLE, NOT_CLASSIFIED):
        raise ValueError(
            f"claim from {producer!r} has unknown status {status!r} (expected {NOT_APPLICABLE!r} or {NOT_CLASSIFIED!r})"
        )
    if state is not None and state not in CLAIM_STATES:
        raise ValueError(
            f"claim from {producer!r} has unknown state {state!r} (expected one of {sorted(CLAIM_STATES)})"
        )
    if source_type not in SOURCE_TYPES:
        raise ValueError(
            f"claim from {producer!r} has unknown source_type {source_type!r} (expected one of {sorted(SOURCE_TYPES)})"
        )
    # A source object and an external source type are one fact stated twice, so they
    # are required to agree. Neither alone is enough: a claim naming `repository_
    # metadata` with no `ClaimSource` would skip every import rule below — including
    # the tier refusal — and `tier=999` would then outrank every rule in
    # `evaluate_claims`, which is the silent override #391 rejected; and a source
    # object under a rule's source type would be an import that resolution reads as
    # one of ours (#401 review).
    if (source is None) is (source_type in EXTERNAL_SOURCE_TYPES):
        raise ValueError(
            f"claim from {producer!r} has source_type {source_type!r} and "
            f"{'no' if source is None else 'a'} ClaimSource — a claim from an external source carries both, "
            f"and one of ours carries neither (external: {sorted(EXTERNAL_SOURCE_TYPES)})"
        )
    if source is not None:
        # An imported claim does not compete on the tier ladder at all. Epic #391
        # settled that on measured evidence: the 12 known disagreements on
        # AnVIL_HPRC_R2 have inference claims at rule tiers 1-2, so admitting imports
        # at CONTENT_TIER would have produced one conflict and eleven silent wrong
        # overrides. Inference and imports resolve separately and are compared. A
        # tier on such a claim is therefore a number an importer must invent and the
        # policy discards — and a number a claim file could forge to outrank every
        # rule. Rejected for the reason a state claim's is: it never competes (#401).
        if tier is not None:
            raise ValueError(
                f"claim from {producer!r} carries a tier, but a claim from an external source does not "
                "compete on the rule tiers — inference and imports are resolved separately and compared"
            )
        # It cites the mapping rule that produced it. There is no implicit copy:
        # `PACBIO` -> `PACBIO` is an identity mapping and gets an entry like any
        # other, because a source value that happens to spell a vocabulary term is a
        # coincidence of spelling rather than an agreement about meaning. The one
        # state with no rule is `unmapped`, which means exactly "no entry exists for
        # this raw value" — which is what makes the review queue derivable rather
        # than asserted (#401). The mapping table itself is #395/#399.
        if state == UNMAPPED:
            if rule_id is not None:
                raise ValueError(
                    f"claim from {producer!r} is {UNMAPPED!r} but cites rule {rule_id!r} — "
                    f"{UNMAPPED!r} means no mapping entry fired"
                )
        elif not rule_id:
            # `not rule_id` and not `is None`: an empty string is non-None, so it
            # would otherwise satisfy the check while naming no rule at all.
            raise ValueError(
                f"claim from {producer!r} declares something but cites no mapping rule — "
                f"an imported claim carries the rule_id that produced it, or state {UNMAPPED!r}"
            )
    # Tier is the resolution input for a claim that does compete, so it is required
    # exactly where one does and rejected where it cannot.
    if source is None and state is None and tier is None:
        raise ValueError(f"claim from {producer!r} declaring value/status must carry a tier")
    # And it must be a number `evaluate_claims` can order. A claim arriving from a
    # file can carry `"tier": "1"`, which passes the None check and then fails inside
    # the tier comparison, against a claim that has nothing to do with it. `bool` is
    # an `int` in Python and is not a tier (#401 review).
    if tier is not None and (not isinstance(tier, int) or isinstance(tier, bool)):
        raise ValueError(f"claim from {producer!r} has tier {tier!r}, which is not an integer")
    if state is not None and tier is not None:
        raise ValueError(f"claim from {producer!r} declaring state {state!r} must not carry a tier — it never competes")
    if join_key is not None:
        require_join_key(join_key, "join_key", f"claim from {producer!r}")
    if match_exact is not None and join_key is None:
        raise ValueError(f"claim from {producer!r} has match_exact without a join_key to qualify")
    # The members whose *type* nothing else pins. The vocabularies above check
    # membership, which implies a string; these are free text and a boolean, so a
    # claim built by hand could otherwise carry `value=7` or `match_exact="yes"` into
    # resolution and out into the schema's Evidence, which says strings and a boolean
    # (#401 review). `add_claim` is the reachable way in: a claim file cannot carry
    # `match_exact` at all, since `_check_entry` refuses a post-join member outright.
    # Cheap next to the membership tests this already runs.
    # A rule's reason is the text that makes output readable and is not recoverable
    # from anything else. An imported claim's is: it cites a mapping rule, and the
    # text is resolved from that rule when the claim enters the stream — so the file
    # carries the id rather than the prose repeated on a few million lines. Writing
    # it is still allowed, for the curator table, whose reason ("checked against the
    # marker paper") is not derivable either (#401). Resolving it is #395.
    if reason is None and source is None:
        raise ValueError(f"claim from {producer!r} has no reason — a rule claim carries the text it explains itself by")
    if reason is not None and not isinstance(reason, str):
        raise ValueError(f"claim from {producer!r} has reason {reason!r}, which is not a string")
    # Unrolled rather than looped over a tuple of pairs: this runs a few million times
    # per corpus run, and building that tuple was five allocations of it per call.
    if value is not None and not isinstance(value, str):
        raise ValueError(f"claim from {producer!r} has value {value!r}, which is not a string")
    if raw_value is not None and not isinstance(raw_value, str):
        raise ValueError(f"claim from {producer!r} has raw_value {raw_value!r}, which is not a string")
    # `unmapped` and `no_vocabulary_term` are *about* a raw value: one says no mapping
    # entry exists for it, the other that our vocabulary has no word for it. Without
    # it the claim says only that something was not mapped, which makes the review
    # queue and the vocabulary decision (#399) unactionable — and the schema already
    # says raw_value is "the whole content of the claim" for these two. `declined` is
    # the exception and stays optional: it declines a whole column as an authority,
    # and there is no one value it is about (#401 review).
    if state in (UNMAPPED, NO_VOCABULARY_TERM) and raw_value is None:
        raise ValueError(
            f"claim from {producer!r} is {state!r} but carries no raw_value — "
            "the raw value is what the claim is about, and what a reviewer acts on"
        )
    if rule_id is not None and not isinstance(rule_id, str):
        raise ValueError(f"claim from {producer!r} has rule_id {rule_id!r}, which is not a string")
    if match_exact is not None and not isinstance(match_exact, bool):
        raise ValueError(f"claim from {producer!r} has match_exact {match_exact!r}, which is not a boolean")

    claim: dict = {}
    if rule_id is not None:
        claim["rule_id"] = rule_id
    if reason is not None:
        claim["reason"] = reason
    if tier is not None:
        claim["tier"] = tier
    if value is not None:
        claim["value"] = value
    elif status is not None:
        claim["status"] = status
    else:
        claim["claim_state"] = state
    claim["source_type"] = source_type
    if source is not None:
        claim["source"] = source.to_dict()
    if raw_value is not None:
        claim["raw_value"] = raw_value
    if join_key is not None:
        claim["join_key"] = join_key
    if match_exact is not None:
        claim["match_exact"] = match_exact
    return claim


# Kinds of synthetic resolution marker ``_sync_markers`` appends to explain an
# absent or ambiguous answer. These are NOT rules: a marker carries a ``marker``
# kind and no ``rule_id`` (issue #228 — stop overloading ``rule_id`` to hold a
# sentinel). These must stay in lockstep with the schema's ``evidence_marker_enum``
# (pinned by tests/test_rule_vocabulary.py); adding a kind means editing both.
NOT_CLASSIFIED_MARKER = "not_classified"
CONFLICT_MARKER = "conflict"


def _is_synthetic_marker(entry: dict) -> bool:
    """True if this evidence entry is a synthetic resolution marker (carries a
    ``marker`` kind), not a claim. A rule-authored ``not_classified`` declaration
    has a real ``rule_id`` and no ``marker``, so it is a claim, not a marker."""
    return "marker" in entry


def _not_classified_marker(fld: str) -> dict:
    """The synthetic placeholder that keeps a claimless field's evidence non-empty."""
    return {
        "marker": NOT_CLASSIFIED_MARKER,
        "reason": f"No rule determined a value for {fld}",
        "status": NOT_CLASSIFIED,
    }


def _conflict_marker(fld: str, competing: list[str]) -> dict:
    """The synthetic marker recording that top-tier claims disagreed."""
    return {
        "marker": CONFLICT_MARKER,
        "reason": f"Conflicting {fld}: {competing} — ambiguous",
        "status": NOT_CLASSIFIED,
        "competing_values": competing,
    }


@dataclass
class ExtendedClassificationResult:
    """Extended classification result with additional fields.

    Each classification field (data_modality, data_type, etc.) has its own
    evidence list in field_evidence, linking each value to the rules that
    determined it.
    """

    data_modality: str | None = None
    data_type: str | None = None
    reference_assembly: str | None = None
    assay_type: str | None = None
    platform: str | None = None
    field_evidence: dict[str, list[dict]] = field(default_factory=lambda: {fld: [] for fld in CLASSIFICATION_FIELDS})
    # Resolved status per dimension (epic #116 / #136): the dimension attributes
    # above hold a real value or None only — the sentinel (not_applicable /
    # not_classified) lives here, never in a value slot. Defaults to
    # not_classified (no statement made) until a value or status is set.
    field_status: dict[str, str] = field(default_factory=lambda: dict.fromkeys(CLASSIFICATION_FIELDS, NOT_CLASSIFIED))
    # Extra facts *about* a dimension's value, keyed by dimension exactly as
    # field_evidence and field_status are — the first being reference_assembly's
    # resolved build (#340). Detail is not a claim: it carries no tier and never
    # competes in ``evaluate_claims``, so it cannot change which value wins. A
    # dimension with no detail serializes exactly as it did before.
    field_detail: dict[str, dict] = field(default_factory=dict)

    def set_field(self, fld: str, value: str | None = None, status: str | None = None) -> None:
        """Set a dimension's value and status coherently.

        ``value`` is a real value or None; ``status`` defaults to
        ``status_for_value(value)``. A CLASSIFIED status stores the value; any
        non-classified status stores None (the sentinel lives only in
        ``field_status``). ``fld`` must be a known classification field and
        ``status`` one of classified / not_applicable / not_classified — a typo
        raises rather than silently creating a stray attribute or emitting an
        invalid status. The (value, status) pairing is checked against the single
        coherence definition (``models._assert_coherent``): a CLASSIFIED status
        without a real value, or a non-classified status carrying one, raises
        rather than silently mis-storing.
        """
        self._require_field(fld)
        if status is None:
            status = status_for_value(value)
        if status not in (CLASSIFIED, NOT_APPLICABLE, NOT_CLASSIFIED):
            raise ValueError(f"unknown status {status!r} for field {fld}")
        _assert_coherent(value, status)  # single coherence definition (models)
        setattr(self, fld, value if status == CLASSIFIED else None)
        self.field_status[fld] = status

    def add_claim(
        self,
        fld: str,
        *,
        source_type: str,
        reason: str | None = None,
        rule_id: str | None = None,
        tier: int | None = None,
        value: str | None = None,
        status: str | None = None,
        state: str | None = None,
        source: ClaimSource | None = None,
        raw_value: str | None = None,
        join_key: str | None = None,
        match_exact: bool | None = None,
    ) -> None:
        """Append a claim to a field and re-resolve the field's value from all its claims.

        The claim is built through ``make_claim``, which enforces every invariant
        of the record (exactly one of value/status/state, a known source_type, a
        tier iff the claim competes, a producer handle — see that function);
        it is appended to ``field_evidence[fld]``, and the field is then set from
        ``evaluate_claims`` over the list — so the field's value is *derived* from
        its claims, never written alongside them (#150). "Derived from its claims"
        means the ones that compete: ``evaluate_claims`` drops a claim carrying a
        ``source`` (#401), so adding an imported claim records what the source said
        without moving the field, exactly as adding a ``state`` claim does. A field
        whose only claim is an imported one therefore stays ``not_classified``, with
        the import visible beside the placeholder saying no rule determined a value —
        which is true of it, and is what #396 will compare against. A same-tier
        disagreement therefore resolves to ``not_classified`` here, rather than the
        last writer silently winning. A ``state`` claim declares nothing, so
        appending one records the source's answer without changing the field —
        and a field carrying only such claims keeps its synthetic
        ``not_classified`` placeholder, which remains true of it.

        Callers use this *after* ``classify_extended`` has run, so
        ``_finalize_result`` may already have appended a synthetic
        ``not_classified`` / conflict marker to the list. ``evaluate_claims``
        ignores those markers when resolving, and ``_sync_markers`` then rewrites
        them to match the new resolution — so a stale placeholder or conflict
        marker is dropped when this claim resolves the field, and a fresh conflict
        marker is emitted if this claim creates one. The field always keeps the
        claim just appended, so its evidence is never emptied.
        """
        self._require_field(fld)
        claim = make_claim(
            rule_id=rule_id,
            reason=reason,
            source_type=source_type,
            tier=tier,
            value=value,
            status=status,
            state=state,
            source=source,
            raw_value=raw_value,
            join_key=join_key,
            match_exact=match_exact,
        )
        self.field_evidence[fld].append(claim)
        evaluation = evaluate_claims(self.field_evidence[fld])
        self.set_field(fld, evaluation.value, evaluation.status)
        self._sync_markers(fld, evaluation)

    def _sync_markers(self, fld: str, evaluation: "ClaimResolution") -> None:
        """Rewrite a field's synthetic markers to match its current resolution.

        Strips any existing synthetic markers (a placeholder or conflict marker
        left by a prior resolution) and appends the one that describes the current
        outcome: a conflict marker when top-tier claims disagree, the
        ``not_classified`` placeholder when no claim was made at all, or nothing
        when the field resolved to a real value or ``not_applicable``. Real claims
        (including rule-authored ``not_classified`` declarations) are untouched.
        Shared by ``_finalize_result`` (fresh classify — nothing to strip) and
        ``add_claim`` (incremental re-resolve), so both keep the evidence honest.
        """
        self.field_evidence[fld] = [e for e in self.field_evidence[fld] if not _is_synthetic_marker(e)]
        # competing_values is non-None iff the resolution is a conflict (ClaimResolution
        # invariant); testing it directly narrows the type without a separate assert.
        if evaluation.competing_values is not None:
            self.field_evidence[fld].append(_conflict_marker(fld, evaluation.competing_values))
        elif evaluation.reason == ResolutionReason.NO_CLAIMS:
            self.field_evidence[fld].append(_not_classified_marker(fld))

    def _require_field(self, fld: str) -> None:
        """Raise ValueError for an unknown classification field, so every accessor
        that takes a ``fld`` fails with one clear message rather than a bare
        KeyError leaking from the ``field_status`` lookup."""
        if fld not in self.field_status:
            raise ValueError(f"unknown classification field {fld!r}")

    def status_of(self, fld: str) -> str:
        """Resolved status of a dimension (classified / not_applicable / not_classified)."""
        self._require_field(fld)
        return self.field_status[fld]

    def is_declared(self, fld: str) -> bool:
        """True if a definitive statement was made for the field — a real value
        (CLASSIFIED) or an explicit not_applicable — vs not_classified/unset."""
        self._require_field(fld)
        return self.field_status[fld] in (CLASSIFIED, NOT_APPLICABLE)

    def label(self, fld: str) -> str | None:
        """Combined value-or-status label for the field (mirrors models.field_label):
        the real value when CLASSIFIED, else the status string. For flat/legacy
        views (basic ClassificationResult, CSV reports) that want one column."""
        self._require_field(fld)
        return getattr(self, fld) if self.field_status[fld] == CLASSIFIED else self.field_status[fld]

    @property
    def rules_matched(self) -> list[str]:
        """Deduplicated list of all rule identifiers from field evidence.

        Not limited to YAML-defined rule IDs, and not exhaustive of evidence:
        synthetic resolution markers (the ``not_classified`` placeholder and
        conflict markers) carry no ``rule_id`` and are skipped — they are not
        rules. The content classifiers in ``header_classifier`` do contribute
        their own IDs for signals no YAML rule expresses — ``contig_length_detection``,
        ``vcf_contig_length``, ``aligned_to_reference``, the ``fasta_*`` and
        ``bed_*`` IDs, ``rgfa_stable_rank_reference``, ``fetch_failed``, and the
        engine's ``infer_assay_type``.

        So a caller must not assume an ID here names a rule in unified_rules.yaml.

        **An imported claim now contributes one too.** It used to carry a ``source``
        and no ``rule_id`` (#392), so it was skipped like a marker; under #401 it
        cites the ``rule_id`` of the mapping that produced it, and only an
        ``unmapped`` one still names nothing. ``infer_assay_type``'s
        ``matched_rules_any`` conditions read this list and are written against our
        own rule IDs, so a ``map_*`` id could satisfy — or fail to satisfy — one of
        them. Nothing feeds an imported claim into ``field_evidence`` until the join
        lands, so whether these belong here is #402's to settle.
        """
        seen = set()
        result = []
        for entries in self.field_evidence.values():
            for e in entries:
                if _is_synthetic_marker(e):
                    continue
                rid = e.get("rule_id")
                if rid is None:
                    continue
                if rid not in seen:
                    seen.add(rid)
                    result.append(rid)
        return result

    @property
    def reasons(self) -> list[str]:
        """The reason from each distinct rule in field_evidence, in first-seen order.

        Deduplication is by ``rule_id``, not by reason text, so two rules that
        happen to share a reason both appear — and one rule contributing to
        several fields appears once. Entries carrying no ``rule_id`` are skipped:
        synthetic markers, which are not rules, and an ``unmapped`` imported claim,
        which by definition cites none.

        **An imported claim is not filtered out here.** It carries the ``rule_id`` of
        the mapping that produced it (#401), so it is not skipped like a marker, and
        what it contributes is whatever ``reason`` it stores: prose for a curator
        claim, which is allowed to carry one and does in the tests, and an empty
        string for a mapped claim off a claim file, which stores the id alone and
        leaves the text to be resolved from the mapping rule — which this accessor
        does not do. ``add_claim`` is the public path that can put one
        there today, and does so in the tests; nothing in the classification run takes
        it, so no corpus output is affected until the join lands (#402). Whichever of
        #395 or #402 first makes it routine owns deciding whether these belong here at
        all. An external claim's reason is read from the evidence itself, which keeps
        every claim, not from here.
        """
        seen = set()
        result = []
        for entries in self.field_evidence.values():
            for e in entries:
                if _is_synthetic_marker(e):
                    continue
                rid = e.get("rule_id")
                if rid is None:
                    continue
                if rid not in seen:
                    seen.add(rid)
                    result.append(e.get("reason", ""))
        return result

    def to_classification_result(self) -> ClassificationResult:
        """Convert to a basic ClassificationResult for backward compatibility."""
        return ClassificationResult(
            data_modality=self.data_modality,
            reference_assembly=self.reference_assembly,
            reasons=self.reasons,
            rules_matched=self.rules_matched,
        )

    def to_output_dict(self) -> dict:
        """Convert to the per-field output format.

        Each dimension emits ``{value, status, evidence}`` via
        ``models.build_field_entry``. The dimension attribute holds a real value or
        None and ``field_status`` holds the resolved status (epic #116 / #136), so
        both are passed straight through — the sentinel is never in ``value``,
        internally or in the output.
        """
        classifications = {}
        for fld in self._CLASSIFICATION_FIELDS:
            evidence = self.field_evidence.get(fld, [])
            classifications[fld] = build_field_entry(
                getattr(self, fld),
                status=self.field_status[fld],
                evidence=evidence,
                detail=self.field_detail.get(fld),
            )
        return classifications

    # Classification field names (single source of truth: models.CLASSIFICATION_FIELDS)
    _CLASSIFICATION_FIELDS = CLASSIFICATION_FIELDS


def _claim_declaration(claim: dict) -> str | None:
    """A claim's *declaration*: its real ``value``, else its ``status`` (a rule
    authors not_applicable / not_classified as a ``status``, never in the value
    slot — epic #116 / #136). Resolution runs over declarations; the winner is
    split back into (value, status) by ``_resolved``."""
    value = claim.get("value")
    return value if value is not None else claim.get("status")


class ResolutionReason(str, Enum):
    """Why ``evaluate_claims`` reached its result. ``str``-backed so the value is
    wire-compatible with the pre-#212 magic strings (e.g. ``"no_claims"``)."""

    NO_CLAIMS = "no_claims"
    SINGLE_CLAIM = "single_claim"
    UNANIMOUS = "unanimous"
    HIGHER_SPECIFICITY_OVERRIDE = "higher_specificity_override"
    NOT_APPLICABLE_TERMINAL = "not_applicable_terminal"
    CONFLICT = "conflict"

    def __str__(self) -> str:
        # Render as the underlying value ("no_claims"), not "ResolutionReason.NO_CLAIMS",
        # so str()/f-string formatting stays wire-compatible across Python versions.
        return self.value


@dataclass(frozen=True)
class ClaimResolution:
    """The resolved outcome of ``evaluate_claims`` for one classification field.

    ``competing_values`` is non-None only for a conflict (``None`` otherwise);
    ``is_conflict`` derives from it, so the two can never disagree.
    """

    value: str | None
    status: str
    reason: ResolutionReason
    competing_values: list[str] | None = None

    @property
    def is_conflict(self) -> bool:
        return self.competing_values is not None


def _resolved(
    declaration: str | None,
    reason: ResolutionReason,
    competing: list[str] | None = None,
) -> ClaimResolution:
    """Package a winning declaration as a ``ClaimResolution``: a real declaration
    becomes value with status CLASSIFIED; a status declaration becomes that status
    with value None — so a sentinel never lands in ``value``."""
    status = status_for_value(declaration)
    return ClaimResolution(
        value=declaration if status == CLASSIFIED else None,
        status=status,
        reason=reason,
        competing_values=competing,
    )


def evaluate_claims(claims: list[dict]) -> ClaimResolution:
    """Evaluate competing claims for a single classification field.

    A claim *declares* either a real value or a status (not_applicable /
    not_classified — see ``_claim_declaration``), or it declares nothing: a claim
    carrying a ``claim_state`` (#392) records that a source was consulted and
    produced no vocabulary value, and is dropped below with the markers rather
    than resolved. Resolution runs in declaration space over what is left, and
    the winner is split back into a real value + status.

    Resolution rules:
    - No claims → not_classified
    - Single claim → use it
    - All claims agree → use that declaration
    - Claims disagree, highest tier is unique → highest tier wins (override)
    - Claims disagree, NOT_APPLICABLE at top tier → not_applicable wins (terminal)
    - Claims disagree, same max tier → conflict (not_classified)

    Tier ladder: tiers 1-3 are the rule tiers (extension / filename / header,
    declared in ``unified_rules.yaml``); ``CONTENT_TIER`` (4) is reserved for
    claims derived from reading file bytes. Because it is a unique tier above
    every rule, the "highest unique tier wins" rule above makes a content claim
    override a disagreeing tier-3 rule, and a content ``not_applicable`` win via
    the terminal rule — no special case needed here (issue #226).

    Args:
        claims: List of evidence dicts. Those declaring a ``value`` or a
                ``status`` *and carrying a tier* are resolved; ``rule_id`` /
                ``reason`` are optional here. Three kinds are dropped before the
                tier math: synthetic markers (which carry a ``marker`` kind),
                ``claim_state`` claims (which declare nothing), and claims carrying
                a ``source`` — claims from an external source, which are inert here
                rather than competing (#401). A *rule* claim with no tier still
                raises ``KeyError`` on the disagreement path, which is #228's guard
                against resolving at a phantom tier 0.

    Returns:
        ClaimResolution with: value (real or None), status, reason, is_conflict,
        competing_values (non-None iff conflict).
    """
    # Drop synthetic markers (placeholder / conflict) and everything that declares
    # nothing — an empty claim, or a claim_state claim (#392) — but keep
    # rule-authored not_classified declarations (e.g., fastq_modality_unknown) —
    # those are real claims, not markers.
    #
    # A claim from an external source is dropped too, and that is what makes an
    # imported claim inert here (#401): `make_claim` rejects a tier on one, so it has
    # nothing to compete with. This is the operational form of epic #391's decision
    # that imports are not tier participants — without it an imported claim either
    # reached `max(c["tier"] …)` and raised, or resolved a field by itself, which is
    # the silent override the epic measured and rejected. It stays visible in
    # field_evidence either way; comparing the two resolutions is #396.
    #
    # Keyed on `source` rather than on a missing tier, so that a *rule* claim with no
    # tier still raises in the tier math below. That is #228's guard against a
    # phantom tier 0 (#150/#151), and dropping such a claim silently instead would
    # give the malformed case the treatment the deliberate one gets.
    real_claims = [
        c for c in claims if _claim_declaration(c) is not None and "source" not in c and not _is_synthetic_marker(c)
    ]

    # Assertive = real-value declarations; a not_classified status means
    # "I looked but can't determine" and doesn't assert a value.
    assertive_claims = [c for c in real_claims if _claim_declaration(c) != NOT_CLASSIFIED]

    if not real_claims:
        return _resolved(NOT_CLASSIFIED, ResolutionReason.NO_CLAIMS)

    # Only not_classified declarations present → resolve as not_classified
    # (the rule's rationale is preserved in field_evidence, not in this return value)
    if not assertive_claims:
        return _resolved(
            NOT_CLASSIFIED,
            ResolutionReason.SINGLE_CLAIM if len(real_claims) == 1 else ResolutionReason.UNANIMOUS,
        )

    # Check if all assertive declarations agree
    declarations = {_claim_declaration(c) for c in assertive_claims}

    if len(declarations) == 1:
        # Unanimous — every assertive claim declares the same value
        return _resolved(
            next(iter(declarations)),
            ResolutionReason.UNANIMOUS if len(assertive_claims) > 1 else ResolutionReason.SINGLE_CLAIM,
        )

    # Assertive declarations disagree — check tiers. Every assertive claim is built
    # through make_claim, which requires a tier on any claim that declares a value or
    # status, so read it directly: a missing tier is a bug that should raise here, not
    # silently resolve at a phantom tier 0 (#228). The tier-free claims make_claim also
    # builds declare a claim_state, which is not a declaration, so they never reach here.
    max_tier = max(c["tier"] for c in assertive_claims)
    top_tier_claims = [c for c in assertive_claims if c["tier"] == max_tier]
    # Declarations are non-None here (real_claims already dropped None ones); the
    # explicit filter restates that so the set is set[str] and sorted() type-checks.
    top_tier_decls = {d for c in top_tier_claims if (d := _claim_declaration(c)) is not None}

    # NOT_APPLICABLE is a terminal declaration — it wins over real values
    # at the same tier without triggering a conflict (e.g., text_stats
    # setting not_applicable shouldn't conflict with filename_ref patterns)
    if NOT_APPLICABLE in top_tier_decls:
        return _resolved(NOT_APPLICABLE, ResolutionReason.NOT_APPLICABLE_TERMINAL)

    if len(top_tier_decls) == 1:
        # Highest tier is unanimous — override lower tiers
        return _resolved(top_tier_decls.pop(), ResolutionReason.HIGHER_SPECIFICITY_OVERRIDE)

    # Same tier, different values — conflict
    return _resolved(NOT_CLASSIFIED, ResolutionReason.CONFLICT, competing=sorted(top_tier_decls))


class RuleEngine:
    """Engine for classifying files using the unified rules format.

    This engine supports all scope types:
    - extension: Rules based on file extension only
    - filename: Rules based on filename patterns
    - file_size: Rules based on file size
    - header: Rules based on BAM/CRAM header content
    - vcf_header: Rules based on VCF header content
    - fastq_header: Rules based on FASTQ read names

    Rules are executed in tier order (1 -> 2 -> 3), with higher tiers
    requiring more information (headers) to evaluate.
    """

    def __init__(self, rules_path: str | Path | None = None):
        """Initialize the rule engine.

        Args:
            rules_path: Path to unified rules YAML. Defaults to the bundled
                       unified_rules.yaml (package data of meta_disco.rules).
        """
        self.rules = get_unified_rules(rules_path)

    def classify(self, file_info: FileInfo | ExtendedFileInfo, include_tier3: bool = False) -> ClassificationResult:
        """Classify a file based on its metadata.

        Args:
            file_info: File information (filename, size, etc.)
            include_tier3: Whether to evaluate tier 3 (header-based) rules.
                          Requires ExtendedFileInfo with header data.

        Returns:
            ClassificationResult with classification and metadata
        """
        result = self.classify_extended(file_info, include_tier3)
        return result.to_classification_result()

    def classify_extended(
        self, file_info: FileInfo | ExtendedFileInfo, include_tier3: bool = False
    ) -> ExtendedClassificationResult:
        """Classify a file and return extended result with all fields.

        Args:
            file_info: File information (filename, size, etc.)
            include_tier3: Whether to evaluate tier 3 (header-based) rules.
                          Requires ExtendedFileInfo with header data.

        Returns:
            ExtendedClassificationResult with classification and metadata
        """
        # Convert to ExtendedFileInfo if needed
        ext_info = ExtendedFileInfo.from_file_info(file_info) if isinstance(file_info, FileInfo) else file_info

        # Read the extension from the pre-parsed FileName (parsed once at the load
        # boundary, #242) — no re-parse here. FileName.parse yields None (not a junk
        # last-dot suffix) for a name with no known extension, so an unknown name
        # leaves the caller's file_format fallback intact — a header-only call
        # (name is FileName.EMPTY) yields None here too, so file_format sets the
        # extension and the rules still run without inventing a filename (#152/#241).
        parsed_ext = ext_info.name.extension
        if parsed_ext:
            # From the real name: already the clean core, lower-cased by the parse.
            ext_info.file_format = parsed_ext
        elif ext_info.file_format:
            # No usable name — normalize the caller's file_format fallback to its
            # clean core suffix, so it matches the core-keyed rules (#244) and is
            # case-insensitive. Route it through parse_file_name (treating the token
            # as a degenerate name): a compound fallback (".fastq.gz", passed by a
            # header-only call) becomes its core (".fastq"), and since #249 the parser
            # recognizes multi-dot cores directly, so ".g.vcf" stays ".g.vcf"
            # (Format.GVCF) rather than collapsing to ".vcf" — which is why the #244
            # known-core short-circuit is no longer needed. A non-extension label
            # ("Other") parses to None and keeps its lower-cased self, matching
            # nothing (#152/#243).
            core = self.rules.parse_file_name(ext_info.file_format).extension
            ext_info.file_format = core if core is not None else ext_info.file_format.lower()
        extension = ext_info.file_format or ""

        # Derive the canonical format from the extension the engine settled on
        # (parsed name or the caller's file_format fallback), so format and
        # extension always agree — one funnel through extension_to_format (#243).
        ext_info.format = self.rules.extension_to_format(extension)

        # Initialize result
        result = ExtendedClassificationResult()

        # Get all rules that apply to this extension
        applicable_rules = self.rules.get_rules_for_extension(extension)

        # Filter by tier
        max_tier = 3 if include_tier3 else 2

        # Execute rules by tier
        for tier in range(1, max_tier + 1):
            tier_rules = [r for r in applicable_rules if r.tier == tier]
            for rule in tier_rules:
                if self._rule_matches(rule, ext_info, result):
                    self._apply_rule(rule, result)
        # Evaluate all collected claims, then attempt assay_type inference
        self._finalize_result(result)
        self.infer_assay_type(result, ext_info)
        return result

    def _finalize_result(self, result: ExtendedClassificationResult) -> None:
        """Evaluate collected claims for each field and set final values.

        Calls evaluate_claims() per field to resolve competing claims into a single
        value, then ``_sync_markers`` records the conflict / not_classified marker
        when the resolution warrants one. On this fresh pass no prior markers exist,
        so ``_sync_markers`` only appends.
        """
        for fld in result._CLASSIFICATION_FIELDS:
            claims = result.field_evidence.get(fld, [])
            evaluation = evaluate_claims(claims)
            result.set_field(fld, evaluation.value, evaluation.status)
            result._sync_markers(fld, evaluation)

    def _rule_matches(
        self, rule: UnifiedRule, file_info: ExtendedFileInfo, current: ExtendedClassificationResult
    ) -> bool:
        """Check if a unified rule's conditions match."""
        when = rule.when

        # Handle 'always: true'
        if when.get("always"):
            return True

        # Check extension filter. file_format is already lower-cased by
        # classify_extended, so this compares consistently with matches_extension's
        # own lowering (a mixed-case caller file_format was normalized upstream).
        if "extensions" in when and file_info.file_format not in [e.lower() for e in when["extensions"]]:
            return False

        # Check format filter (#243), a peer of the extensions filter above and
        # keyed by presence like it: when `format` is present the rule matches
        # only a file whose derived format equals it. `when.format` is a Format
        # value string ("FASTA"); file_info.format is a Format (a str enum), so
        # equality compares by value. A present-but-non-matching format — an
        # unresolved (None) format, a different one, or a stray falsy value the
        # loader does not value-check — fails the match rather than being skipped.
        if "format" in when and file_info.format != when["format"]:
            return False

        # Check filename pattern against the parsed name's raw string (#242). A
        # header-only call carries FileName.EMPTY (raw ""), so a filename_pattern rule
        # simply does not match rather than raising.
        if (pattern := when.get("filename_pattern")) and not re.search(pattern, file_info.name.raw, re.IGNORECASE):
            return False

        # Check dataset pattern
        if pattern := when.get("dataset_pattern"):
            if file_info.dataset_title is None:
                return False
            if not re.search(pattern, file_info.dataset_title, re.IGNORECASE):
                return False

        # Check file size constraints
        if (min_gb := when.get("file_size_min_gb")) and (
            file_info.file_size_gb is None or file_info.file_size_gb < min_gb
        ):
            return False

        if (max_gb := when.get("file_size_max_gb")) and (
            file_info.file_size_gb is None or file_info.file_size_gb > max_gb
        ):
            return False

        # Check platform constraint — check claims since fields aren't set until evaluation
        if platform := when.get("platform"):
            platform_claims = [c.get("value") for c in current.field_evidence.get("platform", [])]
            if platform not in platform_claims and file_info.platform != platform:
                return False

        # Check file format constraint
        if (file_format := when.get("file_format")) and file_info.file_format != file_format:
            return False

        # Check modality_not_set — true unless data_modality already has a
        # definitive declaration (a real value or an explicit not_applicable; a
        # not_classified declaration does not count as "set").
        if when.get("modality_not_set"):
            declared = [
                c
                for c in current.field_evidence.get("data_modality", [])
                if _claim_declaration(c) not in (None, NOT_CLASSIFIED)
            ]
            if declared:
                return False

        # Check reference_not_set — same "definitive declaration" test as above.
        if when.get("reference_not_set"):
            declared = [
                c
                for c in current.field_evidence.get("reference_assembly", [])
                if _claim_declaration(c) not in (None, NOT_CLASSIFIED)
            ]
            if declared:
                return False

        # Check header section (tier 3) — skip if checking for absence
        if (
            rule.scope == "header"
            and when.get("header_section")
            and not when.get("header_absent")
            and not self._match_bam_header(when, file_info)
        ):
            return False

        # Check VCF header (tier 3)
        if rule.scope == "vcf_header" and when.get("vcf_header_type") and not self._match_vcf_header(when, file_info):
            return False

        # Check FASTQ header (tier 3)
        if rule.scope == "fastq_header" and when.get("fastq_pattern") and not self._match_fastq_header(when, file_info):
            return False

        # Check header absence (for unaligned detection). Kept as a guard clause
        # (if ... : return False) to match the preceding checks rather than folding
        # into `return not (...)`, which reads worse in this run of guards.
        if when.get("header_absent") and not self._check_header_absent(when, file_info):  # noqa: SIM103
            return False

        return True

    def _match_bam_header(self, when: dict[str, Any], file_info: ExtendedFileInfo) -> bool:
        """Match conditions against BAM header content."""
        if file_info.bam_header is None:
            return False

        section = when.get("header_section", "")
        field_name = when.get("header_field", "")
        pattern = when.get("header_pattern", "")

        if not section:
            return False

        # Parse BAM header once and cache on the file_info object
        from .validators.header_extractors import match_sam_header_pattern, parse_sam_header

        if not hasattr(file_info, "_parsed_bam_header"):
            file_info._parsed_bam_header = parse_sam_header(file_info.bam_header)
        return match_sam_header_pattern(file_info._parsed_bam_header, section, field_name, pattern)

    def _match_vcf_header(self, when: dict[str, Any], file_info: ExtendedFileInfo) -> bool:
        """Match conditions against VCF header content."""
        if file_info.vcf_header is None:
            return False

        header_type = when.get("vcf_header_type", "")
        pattern = when.get("vcf_pattern", "")

        if not header_type or not pattern:
            return False

        # Parse VCF header once and cache on the file_info object
        from .validators.header_extractors import match_vcf_header_pattern, parse_vcf_header

        if not hasattr(file_info, "_parsed_vcf_header"):
            file_info._parsed_vcf_header = parse_vcf_header(file_info.vcf_header)
        return match_vcf_header_pattern(file_info._parsed_vcf_header, header_type, pattern)

    def _match_fastq_header(self, when: dict[str, Any], file_info: ExtendedFileInfo) -> bool:
        """Match conditions against FASTQ read name."""
        if file_info.fastq_first_read is None:
            return False

        pattern = when.get("fastq_pattern", "")
        if not pattern:
            return False

        return bool(re.search(pattern, file_info.fastq_first_read, re.IGNORECASE))

    def _check_header_absent(self, when: dict[str, Any], file_info: ExtendedFileInfo) -> bool:
        """Check if a header section is absent (for unaligned detection)."""
        section = when.get("header_section", "")

        if section == "@SQ" and file_info.bam_header is not None:
            # Check if @SQ section is missing
            from .validators.header_extractors import has_sam_section, parse_sam_header

            header = parse_sam_header(file_info.bam_header)
            return not has_sam_section(header, section)

        return False

    def _apply_rule(self, rule: UnifiedRule, result: ExtendedClassificationResult) -> None:
        """Collect claims from a rule without setting classification fields.

        A rule authors each field either as a real value (``then``) or as a
        not_applicable / not_classified status (``then.status`` →
        ``rule.then_status``); the loader guarantees never both. Each becomes a
        claim appended to field_evidence — a value claim carries ``value``, a status
        claim carries ``status`` (never a sentinel in the value slot — epic #116 /
        #136); evaluation happens later in _finalize_result via evaluate_claims().

        The claim's ``source_type`` comes from the rule's ``scope`` via
        ``_RULE_SOURCE_TYPES`` — scope being the rule's own declaration of what it
        reads (#392). Every other producer states its kind explicitly.
        """
        then = rule.then
        then_status = rule.then_status
        reason = rule.rationale or ""
        source_type = _RULE_SOURCE_TYPES.get(rule.scope)
        if source_type is None:
            raise ValueError(
                f"rule {rule.id!r} has scope {rule.scope!r}, which no source_type describes "
                f"(known: {sorted(_RULE_SOURCE_TYPES)}). Decide what kind of source such a rule is "
                f"and add it to _RULE_SOURCE_TYPES."
            )
        for fld in result._CLASSIFICATION_FIELDS:
            value = then.get(fld)
            status = then_status.get(fld) if then_status else None
            if value is not None:
                result.field_evidence[fld].append(
                    make_claim(rule_id=rule.id, reason=reason, tier=rule.tier, source_type=source_type, value=value)
                )
            elif status is not None:
                result.field_evidence[fld].append(
                    make_claim(rule_id=rule.id, reason=reason, tier=rule.tier, source_type=source_type, status=status)
                )

    def infer_assay_type(self, result: ExtendedClassificationResult, file_info: ExtendedFileInfo) -> None:
        """Infer assay type from other classification signals.

        Sets result.assay_type and appends evidence when a matching
        assay_type_rule is found. Skips if assay_type is already declared
        (a real value or an explicit not_applicable).
        """
        if result.is_declared("assay_type"):
            return
        # Don't infer over conflicts
        assay_evidence = result.field_evidence.get("assay_type", [])
        if any(e.get("marker") == CONFLICT_MARKER for e in assay_evidence):
            return

        for assay_rule in self.rules.assay_type_rules:
            conditions = assay_rule.conditions

            # Check matched_rules_any condition
            if (matched_any := conditions.get("matched_rules_any")) and not any(
                r in result.rules_matched for r in matched_any
            ):
                continue

            # Check data_modality_contains condition
            if modality_contains := conditions.get("data_modality_contains"):
                if result.data_modality is None:
                    continue
                if modality_contains not in result.data_modality:
                    continue

            # Check data_modality exact match condition
            if (modality := conditions.get("data_modality")) and result.data_modality != modality:
                continue

            # Check platform condition
            if (platform := conditions.get("platform")) and result.platform != platform:
                continue

            # Check platform_in condition
            if (platform_in := conditions.get("platform_in")) and result.platform not in platform_in:
                continue

            # Check file_format condition
            if (file_format := conditions.get("file_format")) and file_info.file_format != file_format:
                continue

            # Check file_format_not condition
            if (file_format_not := conditions.get("file_format_not")) and file_info.file_format == file_format_not:
                continue

            # Check file_size_gb_gt condition
            if (size_gt := conditions.get("file_size_gb_gt")) and (
                file_info.file_size_gb is None or file_info.file_size_gb <= size_gt
            ):
                continue

            # Check file_size_gb_lt condition
            if (size_lt := conditions.get("file_size_gb_lt")) and (
                file_info.file_size_gb is None or file_info.file_size_gb >= size_lt
            ):
                continue

            # All conditions passed — record the inference as a claim. add_claim
            # sets the field, drops the synthetic not_classified placeholder, and
            # enforces make_claim's invariants. tier 3: the inference derives from
            # already-resolved signals (the header-derived platform is typically
            # tier 3), so it carries a tier rather than the tier-0 default #228
            # will forbid; it never competes (the is_declared guard above means it
            # only fires when no other claim determined assay_type), so the tier is
            # for consistency, not resolution. Its source kind is stated rather
            # than read off that tier: this reads other dimensions' resolved
            # values, plus the file's format and size — not a header (#392).
            result.add_claim(
                "assay_type",
                rule_id="infer_assay_type",
                tier=3,
                source_type=SOURCE_SIGNAL_INFERENCE,
                reason=f"Inferred {assay_rule.assay_type} from platform/modality/file size signals",
                value=assay_rule.assay_type,
            )
            return

    def classify_with_bam_header(
        self,
        filename: str,
        bam_header: str,
        file_size: int | None = None,
    ) -> ExtendedClassificationResult:
        """Classify a BAM/CRAM file using its header.

        This is a convenience method that creates ExtendedFileInfo from the
        provided header text and runs tier 1-3 classification.

        Args:
            filename: The filename (used for extension and filename pattern rules)
            bam_header: Raw SAM/BAM header text (lines starting with @)
            file_size: Optional file size in bytes

        Returns:
            ExtendedClassificationResult with classification and metadata
        """
        file_info = ExtendedFileInfo(
            name=FileName.parse(filename),
            file_size=file_size,
            bam_header=bam_header,
        )
        return self.classify_extended(file_info, include_tier3=True)

    def classify_with_vcf_header(
        self,
        filename: str,
        vcf_header: str,
        file_size: int | None = None,
    ) -> ExtendedClassificationResult:
        """Classify a VCF file using its header.

        This is a convenience method that creates ExtendedFileInfo from the
        provided header text and runs tier 1-3 classification.

        Args:
            filename: The filename (used for extension and filename pattern rules)
            vcf_header: Raw VCF header text (lines starting with ##)
            file_size: Optional file size in bytes

        Returns:
            ExtendedClassificationResult with classification and metadata
        """
        file_info = ExtendedFileInfo(
            name=FileName.parse(filename),
            file_size=file_size,
            vcf_header=vcf_header,
        )
        return self.classify_extended(file_info, include_tier3=True)

    def classify_with_fastq_header(
        self,
        filename: str,
        first_read: str,
        file_size: int | None = None,
    ) -> ExtendedClassificationResult:
        """Classify a FASTQ file using its first read name.

        This is a convenience method that creates ExtendedFileInfo from the
        provided read name and runs tier 1-3 classification.

        Args:
            filename: The filename (used for extension and filename pattern rules)
            first_read: First read name line from FASTQ (starting with @)
            file_size: Optional file size in bytes

        Returns:
            ExtendedClassificationResult with classification and metadata
        """
        file_info = ExtendedFileInfo(
            name=FileName.parse(filename),
            file_size=file_size,
            fastq_first_read=first_read,
        )
        return self.classify_extended(file_info, include_tier3=True)

    def classify_with_fasta_header(
        self,
        filename: str,
        contig_names: list[str],
        file_size: int | None = None,
    ) -> ExtendedClassificationResult:
        """Classify a FASTA file using its contig names.

        This is a convenience method that creates ExtendedFileInfo from the
        provided contig names and runs tier 1-2 classification. FASTA does
        not yet have tier 3 rules; contig analysis is handled in
        header_classifier.classify_from_fasta_header.

        Args:
            filename: The filename (used for extension and filename pattern rules)
            contig_names: List of contig/sequence names from > header lines
            file_size: Optional file size in bytes

        Returns:
            ExtendedClassificationResult with classification and metadata
        """
        file_info = ExtendedFileInfo(
            name=FileName.parse(filename),
            file_size=file_size,
            fasta_contig_names=contig_names,
        )
        return self.classify_extended(file_info, include_tier3=False)


# Alias for backward compatibility
UnifiedRuleEngine = RuleEngine
