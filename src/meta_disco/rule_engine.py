"""Rule engine for classifying biological data files.

This module provides both the legacy RuleEngine (for backward compatibility)
and the new UnifiedRuleEngine that uses the consolidated rules file.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import ClassificationResult, FileInfo
from .rule_loader import UnifiedRule, UnifiedRules, get_unified_rules


@dataclass
class Rule:
    """A single classification rule (legacy format)."""

    id: str
    when: dict[str, Any]
    then: dict[str, Any]
    confidence: float
    reason: str
    terminal: bool = False


@dataclass
class FileTypeRules:
    """Rules for a specific file type (legacy format)."""

    description: str
    default_modality: str | None
    chain: list[Rule]


class RuleEngine:
    """Engine for classifying files based on YAML rules (legacy format).

    This class maintains backward compatibility with the original
    classification_rules.yaml format. For new code, use UnifiedRuleEngine.
    """

    # Compound extensions in priority order (longest first)
    COMPOUND_EXTENSIONS = [
        ".g.vcf.gz",  # Must come before .vcf.gz
        ".gvcf.gz",
        ".vcf.gz",
        ".fastq.gz",
        ".fq.gz",
        ".bed.gz",
        ".sam.gz",
        ".tar.gz",
        ".mtx.gz",
    ]

    def __init__(self, rules_path: str):
        """Initialize the rule engine with rules from a YAML file."""
        self.extension_map: dict[str, str] = {}
        self.file_types: dict[str, FileTypeRules] = {}
        self._load_rules(rules_path)

    def _load_rules(self, rules_path: str) -> None:
        """Load rules from a YAML file."""
        with open(rules_path) as f:
            # YAML file has multiple documents separated by ---
            docs = list(yaml.safe_load_all(f))

        # First document contains extension_map
        if docs and docs[0]:
            self.extension_map = docs[0].get("extension_map", {})

        # Second document contains file_types
        if len(docs) > 1 and docs[1]:
            file_types_raw = docs[1].get("file_types", {})
            for type_name, type_data in file_types_raw.items():
                chain = []
                for rule_data in type_data.get("chain", []):
                    chain.append(
                        Rule(
                            id=rule_data["id"],
                            when=rule_data.get("when", {}),
                            then=rule_data.get("then", {}),
                            confidence=rule_data.get("confidence", 0.0),
                            reason=rule_data.get("reason", ""),
                            terminal=rule_data.get("terminal", False),
                        )
                    )
                self.file_types[type_name] = FileTypeRules(
                    description=type_data.get("description", ""),
                    default_modality=type_data.get("default_modality"),
                    chain=chain,
                )

    def classify(self, file_info: FileInfo) -> ClassificationResult:
        """Classify a file based on its metadata."""
        # 1. Extract extension
        ext = self._extract_extension(file_info.filename)

        # 2. Look up file type
        file_type = self.extension_map.get(ext)
        if not file_type:
            return ClassificationResult(
                needs_manual_review=True,
                reasons=[f"Unknown extension: {ext}"],
            )

        # 3. Check if file type has rules defined
        if file_type not in self.file_types:
            return ClassificationResult(
                needs_manual_review=True,
                reasons=[f"No rules defined for file type: {file_type}"],
            )

        # 4. Execute rule chain
        return self._execute_chain(file_type, file_info)

    def _extract_extension(self, filename: str) -> str:
        """Extract the file extension, handling compound extensions."""
        filename_lower = filename.lower()

        # Check compound extensions first (in priority order)
        for ext in self.COMPOUND_EXTENSIONS:
            if filename_lower.endswith(ext):
                return ext

        # Fall back to simple extension
        if "." in filename:
            return "." + filename.rsplit(".", 1)[-1].lower()
        return ""

    def _execute_chain(self, file_type: str, file_info: FileInfo) -> ClassificationResult:
        """Execute the rule chain for a file type."""
        result = ClassificationResult()
        type_rules = self.file_types[file_type]

        for rule in type_rules.chain:
            if self._rule_matches(rule, file_info, result):
                self._apply_rule(rule, result)
                if rule.terminal:
                    break

        return result

    def _rule_matches(
        self, rule: Rule, file_info: FileInfo, current: ClassificationResult
    ) -> bool:
        """Check if a rule's conditions match."""
        when = rule.when

        # Handle 'always: true'
        if when.get("always"):
            return True

        # Handle filename patterns
        if patterns := when.get("filename_matches"):
            if not any(re.search(p, file_info.filename) for p in patterns):
                return False

        # Handle dataset patterns
        if patterns := when.get("dataset_matches"):
            if file_info.dataset_title is None:
                return False
            if not any(re.search(p, file_info.dataset_title) for p in patterns):
                return False

        # Handle file size checks
        if size_gt := when.get("file_size_gt"):
            if file_info.file_size is None or file_info.file_size <= size_gt:
                return False

        # Handle conditional checks
        if when.get("modality_not_set") and current.data_modality is not None:
            return False
        if when.get("reference_not_set") and current.reference_assembly is not None:
            return False

        return True

    def _apply_rule(self, rule: Rule, result: ClassificationResult) -> None:
        """Apply a rule's effects to the result."""
        then = rule.then

        # Set data modality (only if specified and not None in the rule)
        if "data_modality" in then:
            modality = then["data_modality"]
            if modality is not None:
                result.data_modality = modality

        # Set reference assembly
        if "reference_assembly" in then:
            ref = then["reference_assembly"]
            if ref is not None:
                result.reference_assembly = ref

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

        # Update confidence (take highest confidence from matching rules)
        if rule.confidence > result.confidence:
            result.confidence = rule.confidence

        # Track matched rules and reasons
        result.rules_matched.append(rule.id)
        if rule.reason:
            result.reasons.append(rule.reason)


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
            file_size_gb = file_info.file_size / (1024 ** 3)

        return cls(
            filename=file_info.filename,
            file_size=file_info.file_size,
            file_size_gb=file_size_gb,
            dataset_title=file_info.dataset_title,
        )


@dataclass
class ExtendedClassificationResult:
    """Extended classification result with additional fields."""

    data_modality: str | None = None
    data_type: str | None = None
    reference_assembly: str | None = None
    assay_type: str | None = None
    platform: str | None = None
    file_category: str | None = None
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    rules_matched: list[str] = field(default_factory=list)
    skip: bool = False
    needs_header_inspection: bool = False
    needs_study_context: bool = False
    needs_manual_review: bool = False

    def to_classification_result(self) -> ClassificationResult:
        """Convert to a basic ClassificationResult for backward compatibility."""
        return ClassificationResult(
            data_modality=self.data_modality,
            reference_assembly=self.reference_assembly,
            confidence=self.confidence,
            reasons=self.reasons.copy(),
            rules_matched=self.rules_matched.copy(),
            skip=self.skip,
            needs_header_inspection=self.needs_header_inspection,
            needs_study_context=self.needs_study_context,
            needs_manual_review=self.needs_manual_review,
        )


class UnifiedRuleEngine:
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
        """Initialize the unified rule engine.

        Args:
            rules_path: Path to unified rules YAML. Defaults to rules/unified_rules.yaml
        """
        self.rules = get_unified_rules(rules_path)

    def classify(
        self,
        file_info: FileInfo | ExtendedFileInfo,
        include_tier3: bool = False
    ) -> ExtendedClassificationResult:
        """Classify a file based on its metadata.

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
                        return result

        return result

    def classify_simple(self, file_info: FileInfo) -> ClassificationResult:
        """Classify using only tier 1 and 2 rules, returning basic result.

        This is a convenience method for backward compatibility.
        """
        result = self.classify(file_info, include_tier3=False)
        return result.to_classification_result()

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

        # Check modality_not_set
        if when.get("modality_not_set") and current.data_modality is not None:
            return False

        # Check reference_not_set
        if when.get("reference_not_set") and current.reference_assembly is not None:
            return False

        # Check header section (tier 3)
        if rule.scope == "header" and when.get("header_section"):
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

        # Import header extractors
        from .validators.header_extractors import parse_sam_header, match_sam_header_pattern

        header = parse_sam_header(file_info.bam_header)
        return match_sam_header_pattern(header, section, field_name, pattern)

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

        # Import header extractors
        from .validators.header_extractors import parse_vcf_header, match_vcf_header_pattern

        header = parse_vcf_header(file_info.vcf_header)
        return match_vcf_header_pattern(header, header_type, pattern)

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

        return bool(re.search(pattern, file_info.fastq_first_read))

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

        # Set data modality
        if "data_modality" in then:
            modality = then["data_modality"]
            if modality is not None:
                result.data_modality = modality

        # Set data type
        if "data_type" in then:
            data_type = then["data_type"]
            if data_type is not None:
                result.data_type = data_type

        # Set reference assembly
        if "reference_assembly" in then:
            ref = then["reference_assembly"]
            if ref is not None:
                result.reference_assembly = ref

        # Set assay type
        if "assay_type" in then:
            assay = then["assay_type"]
            if assay is not None:
                result.assay_type = assay

        # Set platform
        if "platform" in then:
            platform = then["platform"]
            if platform is not None:
                result.platform = platform

        # Set file category
        if "file_category" in then:
            category = then["file_category"]
            if category is not None:
                result.file_category = category

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

        # Update confidence (take highest confidence from matching rules)
        if rule.confidence > result.confidence:
            result.confidence = rule.confidence

        # Track matched rules and reasons
        result.rules_matched.append(rule.id)
        if rule.rationale:
            result.reasons.append(rule.rationale)

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
