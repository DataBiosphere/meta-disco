"""Rule engine for classifying biological data files."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import NOT_APPLICABLE, NOT_CLASSIFIED, ClassificationResult, FileInfo
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
    confidence: float = 0.0
    field_evidence: dict[str, list[dict]] = field(default_factory=lambda: {
        "data_modality": [],
        "data_type": [],
        "reference_assembly": [],
        "assay_type": [],
        "platform": [],
    })

    @property
    def rules_matched(self) -> list[str]:
        """Deduplicated list of all rule identifiers from field evidence.

        Includes YAML-defined rule IDs and synthetic IDs (not_classified,
        infer_assay_type, conflicting_*) added by the rule engine.
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
        """Flatten field_evidence into a deduplicated list of reasons."""
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
            confidence=self.confidence,
            reasons=self.reasons,
            rules_matched=self.rules_matched,
        )

    def to_output_dict(self) -> dict:
        """Convert to the per-field output format."""
        classifications = {}
        for fld in self._CLASSIFICATION_FIELDS:
            value = getattr(self, fld)
            evidence = self.field_evidence.get(fld, [])
            fld_conf = max((e.get("confidence", 0) for e in evidence), default=0.0)
            classifications[fld] = {
                "value": value,
                "confidence": fld_conf,
                "evidence": evidence,
            }
        return classifications

    # Classification field names (shared with _finalize_result)
    _CLASSIFICATION_FIELDS = (
        "data_modality", "data_type", "platform", "reference_assembly", "assay_type"
    )


def evaluate_claims(claims: list[dict]) -> dict:
    """Evaluate competing claims for a single classification field.

    Takes a list of evidence entries (each with rule_id, value, confidence,
    and optionally tier) and resolves them to a single value.

    Resolution rules:
    - No claims → not_classified
    - Single claim → use it
    - All claims agree → use value, max confidence
    - Claims disagree, highest tier is unique → highest tier wins (override)
    - Claims disagree, same max tier → conflict (not_classified)

    Args:
        claims: List of evidence dicts with at least {value, confidence}.
                Optional: tier (int), rule_id (str), reason (str).

    Returns:
        Dict with: value, confidence, reason, is_conflict, competing_values (if conflict)
    """
    # Filter out synthetic entries (not_classified placeholders)
    real_claims = [c for c in claims if c.get("value") not in (None, NOT_CLASSIFIED)]

    if not real_claims:
        return {
            "value": NOT_CLASSIFIED,
            "confidence": 0.0,
            "reason": "no_claims",
            "is_conflict": False,
        }

    # Check if all claims agree
    values = {c["value"] for c in real_claims}

    if len(values) == 1:
        # Unanimous — use the value with highest confidence
        best = max(real_claims, key=lambda c: c.get("confidence", 0))
        return {
            "value": best["value"],
            "confidence": max(c.get("confidence", 0) for c in real_claims),
            "reason": "unanimous" if len(real_claims) > 1 else "single_claim",
            "is_conflict": False,
        }

    # Claims disagree — check tiers
    max_tier = max(c.get("tier", 0) for c in real_claims)
    top_tier_claims = [c for c in real_claims if c.get("tier", 0) == max_tier]
    top_tier_values = {c["value"] for c in top_tier_claims}

    if len(top_tier_values) == 1:
        # Highest tier is unanimous — override lower tiers
        winner_value = top_tier_values.pop()
        best = max(
            (c for c in top_tier_claims if c["value"] == winner_value),
            key=lambda c: c.get("confidence", 0),
        )
        return {
            "value": best["value"],
            "confidence": best.get("confidence", 0),
            "reason": "higher_specificity_override",
            "is_conflict": False,
        }

    # Same tier, different values — conflict
    return {
        "value": NOT_CLASSIFIED,
        "confidence": 0.0,
        "reason": "conflict",
        "is_conflict": True,
        "competing_values": sorted(top_tier_values),
    }


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
            rules_path: Path to unified rules YAML. Defaults to rules/unified_rules.yaml.
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
                    if rule.terminal:
                        self._finalize_result(result)
                        self.infer_assay_type(result, ext_info)
                        return result

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
            setattr(result, fld, evaluation["value"])

            if evaluation["is_conflict"]:
                result.field_evidence[fld].append({
                    "rule_id": f"conflicting_{fld}_rules",
                    "reason": (f"Conflicting {fld}: {evaluation['competing_values']}"
                               " — ambiguous"),
                    "confidence": 0.0,
                    "value": NOT_CLASSIFIED,
                    "competing_values": evaluation["competing_values"],
                })
            elif evaluation["reason"] == "no_claims":
                result.field_evidence[fld].append({
                    "rule_id": "not_classified",
                    "reason": f"No rule determined a value for {fld}",
                    "confidence": 0.0,
                    "value": NOT_CLASSIFIED,
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

        # Check platform constraint
        if platform := when.get("platform"):
            if current.platform != platform and file_info.platform != platform:
                return False

        # Check file format constraint
        if file_format := when.get("file_format"):
            if file_info.file_format != file_format:
                return False

        # Check modality_not_set — true if no real claims for data_modality yet
        if when.get("modality_not_set"):
            real_claims = [c for c in current.field_evidence.get("data_modality", [])
                          if c.get("value") not in (None, NOT_CLASSIFIED)]
            if real_claims:
                return False

        # Check reference_not_set — true if no real claims for reference_assembly yet
        if when.get("reference_not_set"):
            real_claims = [c for c in current.field_evidence.get("reference_assembly", [])
                          if c.get("value") not in (None, NOT_CLASSIFIED)]
            if real_claims:
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
        """Collect claims from a rule without setting field values.

        Claims are appended to field_evidence. Evaluation happens
        later in _finalize_result via evaluate_claims().
        """
        then = rule.then
        evidence_entry = {
            "rule_id": rule.id,
            "reason": rule.rationale or "",
            "confidence": rule.confidence,
            "tier": rule.tier,
        }
        for fld in result._CLASSIFICATION_FIELDS:
            if fld in then and then[fld] is not None:
                entry = evidence_entry.copy()
                entry["value"] = then[fld]
                result.field_evidence[fld].append(entry)

        # Update overall confidence (take highest confidence from matching rules)
        if rule.confidence > result.confidence:
            result.confidence = rule.confidence

    def infer_assay_type(
        self,
        result: ExtendedClassificationResult,
        file_info: ExtendedFileInfo
    ) -> None:
        """Infer assay type from other classification signals.

        Sets result.assay_type and appends evidence when a matching
        assay_type_rule is found. Skips if assay_type is already set
        or conflicted.
        """
        if result.assay_type not in (None, NOT_CLASSIFIED):
            return
        # Don't infer over conflicts
        assay_evidence = result.field_evidence.get("assay_type", [])
        if any("conflicting_" in e.get("rule_id", "") for e in assay_evidence):
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
            result.assay_type = assay_rule.assay_type
            # Remove stale not_classified placeholder if _finalize_result ran first
            result.field_evidence["assay_type"] = [
                e for e in result.field_evidence["assay_type"]
                if e.get("rule_id") != "not_classified"
            ]
            result.field_evidence["assay_type"].append({
                "rule_id": "infer_assay_type",
                "reason": f"Inferred {assay_rule.assay_type} from platform/modality/file size signals",
                "confidence": 0.70,
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
