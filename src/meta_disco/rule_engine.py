"""Rule engine for classifying biological data files."""

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from .models import ClassificationResult, FileInfo


@dataclass
class Rule:
    """A single classification rule."""

    id: str
    when: dict[str, Any]
    then: dict[str, Any]
    confidence: float
    reason: str
    terminal: bool = False


@dataclass
class FileTypeRules:
    """Rules for a specific file type."""

    description: str
    default_modality: str | None
    chain: list[Rule]


class RuleEngine:
    """Engine for classifying files based on YAML rules."""

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
