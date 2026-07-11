"""Rule engine for classifying biological data files."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    ClassificationResult,
    FileInfo,
    _assert_coherent,
    build_field_entry,
    status_for_value,
)
from .rule_loader import UnifiedRule, get_unified_rules


@dataclass
class ExtendedFileInfo:
    """Extended file information including header data for tier 3 rules."""

    filename: str
    file_size: int | None = None
    file_size_gb: float | None = None
    dataset_title: str | None = None
    file_format: str | None = None

    # Header data (populated when available)
    bam_header: str | None = None
    vcf_header: str | None = None
    fastq_first_read: str | None = None
    fasta_contig_names: list[str] | None = None

    # Derived/cached fields
    platform: str | None = None

    @classmethod
    def from_file_info(cls, file_info: FileInfo) -> "ExtendedFileInfo":
        """Create ExtendedFileInfo from a FileInfo object."""
        file_size_gb = None
        if file_info.file_size is not None:
            file_size_gb = file_info.file_size / 1e9  # Use decimal GB, not GiB

        return cls(
            filename=file_info.filename,
            file_size=file_info.file_size,
            file_size_gb=file_size_gb,
            dataset_title=file_info.dataset_title,
        )


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
    field_evidence: dict[str, list[dict]] = field(
        default_factory=lambda: {fld: [] for fld in CLASSIFICATION_FIELDS})
    # Resolved status per dimension (epic #116 / #136): the dimension attributes
    # above hold a real value or None only — the sentinel (not_applicable /
    # not_classified) lives here, never in a value slot. Defaults to
    # not_classified (no statement made) until a value or status is set.
    field_status: dict[str, str] = field(
        default_factory=lambda: {fld: NOT_CLASSIFIED for fld in CLASSIFICATION_FIELDS})

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

        Not limited to YAML-defined rule IDs. Two other sources contribute:

        * The engine itself adds ``not_classified``, ``infer_assay_type`` and
          ``conflicting_{field}_rules``.
        * The content classifiers in ``header_classifier`` add their own IDs for
          signals no YAML rule expresses — ``contig_length_detection``,
          ``vcf_contig_length``, ``aligned_to_reference``, the ``fasta_*`` and
          ``bed_*`` IDs, ``rgfa_stable_rank_reference``, and ``fetch_failed``.

        So a caller must not assume an ID here names a rule in unified_rules.yaml.
        """
        seen = set()
        result = []
        for entries in self.field_evidence.values():
            for e in entries:
                rid = e["rule_id"]
                if rid not in seen:
                    seen.add(rid)
                    result.append(rid)
        return result

    @property
    def reasons(self) -> list[str]:
        """The reason from each distinct rule in field_evidence, in first-seen order.

        Deduplication is by ``rule_id``, not by reason text, so two rules that
        happen to share a reason both appear — and one rule contributing to
        several fields appears once.
        """
        seen = set()
        result = []
        for entries in self.field_evidence.values():
            for e in entries:
                rid = e["rule_id"]
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
                getattr(self, fld), status=self.field_status[fld], evidence=evidence)
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


def _resolved(declaration: str | None, reason: str,
              is_conflict: bool = False, competing: list | None = None) -> dict:
    """Package a winning declaration as ``{value, status, ...}``: a real declaration
    becomes value with status CLASSIFIED; a status declaration becomes that status
    with value None — so a sentinel never lands in ``value``."""
    status = status_for_value(declaration)
    out = {
        "value": declaration if status == CLASSIFIED else None,
        "status": status,
        "reason": reason,
        "is_conflict": is_conflict,
    }
    if competing is not None:
        out["competing_values"] = competing
    return out


def evaluate_claims(claims: list[dict]) -> dict:
    """Evaluate competing claims for a single classification field.

    Each claim *declares* either a real value or a status (not_applicable /
    not_classified — see ``_claim_declaration``). Resolution runs in declaration
    space and the winner is split back into a real value + status.

    Resolution rules:
    - No claims → not_classified
    - Single claim → use it
    - All claims agree → use that declaration
    - Claims disagree, highest tier is unique → highest tier wins (override)
    - Claims disagree, NOT_APPLICABLE at top tier → not_applicable wins (terminal)
    - Claims disagree, same max tier → conflict (not_classified)

    Args:
        claims: List of evidence dicts, each with a ``value`` or a ``status`` and
                optionally ``tier`` / ``rule_id`` / ``reason``.

    Returns:
        Dict with: value (real or None), status, reason, is_conflict,
        competing_values (if conflict).
    """
    # Drop the synthetic not_classified placeholder and empty claims, but keep
    # rule-authored not_classified declarations (e.g., fastq_modality_unknown).
    real_claims = [c for c in claims
                   if _claim_declaration(c) is not None
                   and c.get("rule_id") != "not_classified"]

    # Assertive = real-value declarations; a not_classified status means
    # "I looked but can't determine" and doesn't assert a value.
    assertive_claims = [c for c in real_claims if _claim_declaration(c) != NOT_CLASSIFIED]

    if not real_claims:
        return _resolved(NOT_CLASSIFIED, "no_claims")

    # Only not_classified declarations present → resolve as not_classified
    # (the rule's rationale is preserved in field_evidence, not in this return value)
    if not assertive_claims:
        return _resolved(NOT_CLASSIFIED,
                         "single_claim" if len(real_claims) == 1 else "unanimous")

    # Check if all assertive declarations agree
    declarations = {_claim_declaration(c) for c in assertive_claims}

    if len(declarations) == 1:
        # Unanimous — every assertive claim declares the same value
        return _resolved(next(iter(declarations)),
                         "unanimous" if len(assertive_claims) > 1 else "single_claim")

    # Assertive declarations disagree — check tiers
    max_tier = max(c.get("tier", 0) for c in assertive_claims)
    top_tier_claims = [c for c in assertive_claims if c.get("tier", 0) == max_tier]
    top_tier_decls = {_claim_declaration(c) for c in top_tier_claims}

    # NOT_APPLICABLE is a terminal declaration — it wins over real values
    # at the same tier without triggering a conflict (e.g., text_stats
    # setting not_applicable shouldn't conflict with filename_ref patterns)
    if NOT_APPLICABLE in top_tier_decls:
        return _resolved(NOT_APPLICABLE, "not_applicable_terminal")

    if len(top_tier_decls) == 1:
        # Highest tier is unanimous — override lower tiers
        return _resolved(top_tier_decls.pop(), "higher_specificity_override")

    # Same tier, different values — conflict
    return _resolved(NOT_CLASSIFIED, "conflict",
                     is_conflict=True, competing=sorted(top_tier_decls))


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
                       Legacy paths to classification_rules.yaml are automatically
                       redirected to unified_rules.yaml.
        """
        # Handle legacy path for backward compatibility
        if rules_path is not None:
            rules_path = Path(rules_path)
            if rules_path.name == "classification_rules.yaml":
                rules_path = rules_path.parent / "unified_rules.yaml"

        self.rules = get_unified_rules(rules_path)

    def classify(
        self,
        file_info: FileInfo | ExtendedFileInfo,
        include_tier3: bool = False
    ) -> ClassificationResult:
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
        self,
        file_info: FileInfo | ExtendedFileInfo,
        include_tier3: bool = False
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
        if isinstance(file_info, FileInfo):
            ext_info = ExtendedFileInfo.from_file_info(file_info)
        else:
            ext_info = file_info

        # Extract extension
        extension = self.rules.extract_extension(ext_info.filename)
        ext_info.file_format = extension

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

        Calls evaluate_claims() per field to resolve competing claims
        into a single value. Appends conflict or not_classified markers
        to evidence as appropriate.
        """
        for fld in result._CLASSIFICATION_FIELDS:
            claims = result.field_evidence.get(fld, [])
            evaluation = evaluate_claims(claims)
            result.set_field(fld, evaluation["value"], evaluation["status"])

            if evaluation["is_conflict"]:
                result.field_evidence[fld].append({
                    "rule_id": f"conflicting_{fld}_rules",
                    "reason": (f"Conflicting {fld}: {evaluation['competing_values']}"
                               " — ambiguous"),
                    "status": NOT_CLASSIFIED,
                    "competing_values": evaluation["competing_values"],
                    "is_conflict": True,
                })
            elif evaluation["reason"] == "no_claims":
                result.field_evidence[fld].append({
                    "rule_id": "not_classified",
                    "reason": f"No rule determined a value for {fld}",
                    "status": NOT_CLASSIFIED,
                })

    def _rule_matches(
        self,
        rule: UnifiedRule,
        file_info: ExtendedFileInfo,
        current: ExtendedClassificationResult
    ) -> bool:
        """Check if a unified rule's conditions match."""
        when = rule.when

        # Handle 'always: true'
        if when.get("always"):
            return True

        # Check extension filter
        if "extensions" in when:
            if file_info.file_format not in [e.lower() for e in when["extensions"]]:
                return False

        # Check filename pattern
        if pattern := when.get("filename_pattern"):
            if not re.search(pattern, file_info.filename, re.IGNORECASE):
                return False

        # Check dataset pattern
        if pattern := when.get("dataset_pattern"):
            if file_info.dataset_title is None:
                return False
            if not re.search(pattern, file_info.dataset_title, re.IGNORECASE):
                return False

        # Check file size constraints
        if min_gb := when.get("file_size_min_gb"):
            if file_info.file_size_gb is None or file_info.file_size_gb < min_gb:
                return False

        if max_gb := when.get("file_size_max_gb"):
            if file_info.file_size_gb is None or file_info.file_size_gb > max_gb:
                return False

        # Check platform constraint — check claims since fields aren't set until evaluation
        if platform := when.get("platform"):
            platform_claims = [c.get("value") for c in current.field_evidence.get("platform", [])]
            if platform not in platform_claims and file_info.platform != platform:
                return False

        # Check file format constraint
        if file_format := when.get("file_format"):
            if file_info.file_format != file_format:
                return False

        # Check modality_not_set — true unless data_modality already has a
        # definitive declaration (a real value or an explicit not_applicable; a
        # not_classified declaration does not count as "set").
        if when.get("modality_not_set"):
            declared = [c for c in current.field_evidence.get("data_modality", [])
                        if _claim_declaration(c) not in (None, NOT_CLASSIFIED)]
            if declared:
                return False

        # Check reference_not_set — same "definitive declaration" test as above.
        if when.get("reference_not_set"):
            declared = [c for c in current.field_evidence.get("reference_assembly", [])
                        if _claim_declaration(c) not in (None, NOT_CLASSIFIED)]
            if declared:
                return False

        # Check header section (tier 3) — skip if checking for absence
        if rule.scope == "header" and when.get("header_section") and not when.get("header_absent"):
            if not self._match_bam_header(when, file_info):
                return False

        # Check VCF header (tier 3)
        if rule.scope == "vcf_header" and when.get("vcf_header_type"):
            if not self._match_vcf_header(when, file_info):
                return False

        # Check FASTQ header (tier 3)
        if rule.scope == "fastq_header" and when.get("fastq_pattern"):
            if not self._match_fastq_header(when, file_info):
                return False

        # Check header absence (for unaligned detection)
        if when.get("header_absent"):
            if not self._check_header_absent(when, file_info):
                return False

        return True

    def _match_bam_header(
        self,
        when: dict[str, Any],
        file_info: ExtendedFileInfo
    ) -> bool:
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

        if not hasattr(file_info, '_parsed_bam_header'):
            file_info._parsed_bam_header = parse_sam_header(file_info.bam_header)
        return match_sam_header_pattern(file_info._parsed_bam_header, section, field_name, pattern)

    def _match_vcf_header(
        self,
        when: dict[str, Any],
        file_info: ExtendedFileInfo
    ) -> bool:
        """Match conditions against VCF header content."""
        if file_info.vcf_header is None:
            return False

        header_type = when.get("vcf_header_type", "")
        pattern = when.get("vcf_pattern", "")

        if not header_type or not pattern:
            return False

        # Parse VCF header once and cache on the file_info object
        from .validators.header_extractors import match_vcf_header_pattern, parse_vcf_header

        if not hasattr(file_info, '_parsed_vcf_header'):
            file_info._parsed_vcf_header = parse_vcf_header(file_info.vcf_header)
        return match_vcf_header_pattern(file_info._parsed_vcf_header, header_type, pattern)

    def _match_fastq_header(
        self,
        when: dict[str, Any],
        file_info: ExtendedFileInfo
    ) -> bool:
        """Match conditions against FASTQ read name."""
        if file_info.fastq_first_read is None:
            return False

        pattern = when.get("fastq_pattern", "")
        if not pattern:
            return False

        return bool(re.search(pattern, file_info.fastq_first_read, re.IGNORECASE))

    def _check_header_absent(
        self,
        when: dict[str, Any],
        file_info: ExtendedFileInfo
    ) -> bool:
        """Check if a header section is absent (for unaligned detection)."""
        section = when.get("header_section", "")

        if section == "@SQ" and file_info.bam_header is not None:
            # Check if @SQ section is missing
            from .validators.header_extractors import has_sam_section, parse_sam_header
            header = parse_sam_header(file_info.bam_header)
            return not has_sam_section(header, section)

        return False

    def _apply_rule(
        self,
        rule: UnifiedRule,
        result: ExtendedClassificationResult
    ) -> None:
        """Collect claims from a rule without setting classification fields.

        A rule authors each field either as a real value (``then``) or as a
        not_applicable / not_classified status (``then.status`` →
        ``rule.then_status``); the loader guarantees never both. Each becomes a
        claim appended to field_evidence — a value claim carries ``value``, a status
        claim carries ``status`` (never a sentinel in the value slot — epic #116 /
        #136); evaluation happens later in _finalize_result via evaluate_claims().
        """
        then = rule.then
        then_status = rule.then_status
        evidence_entry = {
            "rule_id": rule.id,
            "reason": rule.rationale or "",
            "tier": rule.tier,
        }
        for fld in result._CLASSIFICATION_FIELDS:
            value = then.get(fld)
            status = then_status.get(fld) if then_status else None
            if value is not None:
                result.field_evidence[fld].append({**evidence_entry, "value": value})
            elif status is not None:
                result.field_evidence[fld].append({**evidence_entry, "status": status})

    def infer_assay_type(
        self,
        result: ExtendedClassificationResult,
        file_info: ExtendedFileInfo
    ) -> None:
        """Infer assay type from other classification signals.

        Sets result.assay_type and appends evidence when a matching
        assay_type_rule is found. Skips if assay_type is already declared
        (a real value or an explicit not_applicable).
        """
        if result.is_declared("assay_type"):
            return
        # Don't infer over conflicts
        assay_evidence = result.field_evidence.get("assay_type", [])
        if any(e.get("is_conflict") for e in assay_evidence):
            return

        for assay_rule in self.rules.assay_type_rules:
            conditions = assay_rule.conditions

            # Check matched_rules_any condition
            if matched_any := conditions.get("matched_rules_any"):
                if not any(r in result.rules_matched for r in matched_any):
                    continue

            # Check data_modality_contains condition
            if modality_contains := conditions.get("data_modality_contains"):
                if result.data_modality is None:
                    continue
                if modality_contains not in result.data_modality:
                    continue

            # Check data_modality exact match condition
            if modality := conditions.get("data_modality"):
                if result.data_modality != modality:
                    continue

            # Check platform condition
            if platform := conditions.get("platform"):
                if result.platform != platform:
                    continue

            # Check platform_in condition
            if platform_in := conditions.get("platform_in"):
                if result.platform not in platform_in:
                    continue

            # Check file_format condition
            if file_format := conditions.get("file_format"):
                if file_info.file_format != file_format:
                    continue

            # Check file_format_not condition
            if file_format_not := conditions.get("file_format_not"):
                if file_info.file_format == file_format_not:
                    continue

            # Check file_size_gb_gt condition
            if size_gt := conditions.get("file_size_gb_gt"):
                if file_info.file_size_gb is None or file_info.file_size_gb <= size_gt:
                    continue

            # Check file_size_gb_lt condition
            if size_lt := conditions.get("file_size_gb_lt"):
                if file_info.file_size_gb is None or file_info.file_size_gb >= size_lt:
                    continue

            # All conditions passed — apply and record evidence
            result.set_field("assay_type", assay_rule.assay_type)
            # Remove stale not_classified placeholder if _finalize_result ran first
            result.field_evidence["assay_type"] = [
                e for e in result.field_evidence["assay_type"]
                if e.get("rule_id") != "not_classified"
            ]
            result.field_evidence["assay_type"].append({
                "rule_id": "infer_assay_type",
                "reason": f"Inferred {assay_rule.assay_type} from platform/modality/file size signals",
                "value": assay_rule.assay_type,
            })
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
            filename=filename,
            file_size=file_size,
            file_size_gb=file_size / 1e9 if file_size is not None else None,
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
            filename=filename,
            file_size=file_size,
            file_size_gb=file_size / 1e9 if file_size is not None else None,
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
            filename=filename,
            file_size=file_size,
            file_size_gb=file_size / 1e9 if file_size is not None else None,
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
            filename=filename,
            file_size=file_size,
            file_size_gb=file_size / 1e9 if file_size is not None else None,
            fasta_contig_names=contig_names,
        )
        return self.classify_extended(file_info, include_tier3=False)


# Alias for backward compatibility
UnifiedRuleEngine = RuleEngine
