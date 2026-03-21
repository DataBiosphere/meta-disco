"""Rule engine for classifying biological data files."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import ClassificationResult, FileInfo, NOT_APPLICABLE, NOT_CLASSIFIED
from .rule_loader import UnifiedRule, UnifiedRules, get_unified_rules


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
    file_category: str | None = None
    confidence: float = 0.0
    field_evidence: dict[str, list[dict]] = field(default_factory=lambda: {
        "data_modality": [],
        "data_type": [],
        "reference_assembly": [],
        "assay_type": [],
        "platform": [],
        "_general": [],  # Rules that don't set a specific classification field
    })
    skip: bool = False
    needs_header_inspection: bool = False
    needs_study_context: bool = False
    needs_manual_review: bool = False

    @property
    def rules_matched(self) -> list[str]:
        """Flatten field_evidence into a deduplicated list of rule IDs."""
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
            skip=self.skip,
            needs_header_inspection=self.needs_header_inspection,
            needs_study_context=self.needs_study_context,
            needs_manual_review=self.needs_manual_review,
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
        # Include general evidence (skip rules, etc.) if any
        general = self.field_evidence.get("_general", [])
        if general:
            classifications["_general"] = {
                "evidence": general,
            }
        return classifications

    # Classification field names (shared with _finalize_result)
    _CLASSIFICATION_FIELDS = (
        "data_modality", "data_type", "platform", "reference_assembly", "assay_type"
    )


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
                        if result.assay_type is None:
                            inferred = self.infer_assay_type(result, ext_info)
                            if inferred:
                                result.assay_type = inferred
                        self._finalize_result(result)
                        return result

        # After all rules, attempt assay_type inference if still unset
        if result.assay_type is None:
            inferred = self.infer_assay_type(result, ext_info)
            if inferred:
                result.assay_type = inferred

        self._finalize_result(result)
        return result

    def _finalize_result(self, result: ExtendedClassificationResult) -> None:
        """Set any remaining None values to appropriate sentinels with evidence.

        This distinguishes between:
        - not_applicable: Field doesn't apply (skipped files, or explicitly set by rules)
        - not_classified: No rule determined a value (default for non-skipped files)
        """
        if result.skip:
            for fld in result._CLASSIFICATION_FIELDS:
                if getattr(result, fld) is None:
                    setattr(result, fld, NOT_APPLICABLE)
                    result.field_evidence[fld].append({
                        "rule_id": "skip",
                        "reason": "File type is skipped (index, checksum, etc.)",
                        "confidence": 1.0,
                    })
            return

        for fld in result._CLASSIFICATION_FIELDS:
            if getattr(result, fld) is None:
                setattr(result, fld, NOT_CLASSIFIED)
                result.field_evidence[fld].append({
                    "rule_id": "not_classified",
                    "reason": "No rule determined a value for this field",
                    "confidence": 0.0,
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

        # Check modality_not_set (treat sentinels as "not set")
        if when.get("modality_not_set") and current.data_modality not in (None, NOT_CLASSIFIED):
            return False

        # Check reference_not_set (treat sentinels as "not set")
        if when.get("reference_not_set") and current.reference_assembly not in (None, NOT_CLASSIFIED):
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
        from .validators.header_extractors import parse_sam_header, match_sam_header_pattern

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
        from .validators.header_extractors import parse_vcf_header, match_vcf_header_pattern

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
            from .validators.header_extractors import parse_sam_header, has_sam_section
            header = parse_sam_header(file_info.bam_header)
            return not has_sam_section(header, section)

        return False

    def _apply_rule(
        self,
        rule: UnifiedRule,
        result: ExtendedClassificationResult
    ) -> None:
        """Apply a rule's effects to the result."""
        then = rule.then
        evidence_entry = {
            "rule_id": rule.id,
            "reason": rule.rationale or "",
            "confidence": rule.confidence,
        }

        # Set classification fields and record per-field evidence
        set_any_field = False
        for fld in result._CLASSIFICATION_FIELDS:
            if fld in then and then[fld] is not None:
                setattr(result, fld, then[fld])
                result.field_evidence[fld].append(evidence_entry.copy())
                set_any_field = True

        # Rules that don't set classification fields (skip, needs_*, etc.)
        if not set_any_field:
            result.field_evidence["_general"].append(evidence_entry)

        # Set file category (not a classification field)
        if "file_category" in then and then["file_category"] is not None:
            result.file_category = then["file_category"]

        # Set skip flag
        if then.get("skip"):
            result.skip = True

        # Set inspection/review flags
        if then.get("needs_header_inspection"):
            result.needs_header_inspection = True
        if then.get("needs_study_context"):
            result.needs_study_context = True
        if then.get("needs_manual_review"):
            result.needs_manual_review = True

        # Update overall confidence (take highest confidence from matching rules)
        if rule.confidence > result.confidence:
            result.confidence = rule.confidence

    def infer_assay_type(
        self,
        result: ExtendedClassificationResult,
        file_info: ExtendedFileInfo
    ) -> str | None:
        """Infer assay type from other classification signals.

        Uses the assay_type_rules from unified rules to infer WGS/WES/RNA-seq/etc.
        based on matched rules, modality, platform, and file size.
        """
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

            # All conditions passed - return this assay type
            return assay_rule.assay_type

        return None

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
            file_size_gb=file_size / 1e9 if file_size else None,
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
            file_size_gb=file_size / 1e9 if file_size else None,
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
            file_size_gb=file_size / 1e9 if file_size else None,
            fastq_first_read=first_read,
        )
        return self.classify_extended(file_info, include_tier3=True)


# Alias for backward compatibility
UnifiedRuleEngine = RuleEngine
