"""Loader for unified classification rules from YAML."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class UnifiedRule:
    """A unified classification rule."""

    id: str
    tier: int
    scope: str
    when: dict[str, Any]
    then: dict[str, Any]
    confidence: float
    rationale: str
    terminal: bool = False

    def matches_extension(self, extension: str) -> bool:
        """Check if this rule applies to a given file extension."""
        if "extensions" not in self.when:
            return True  # No extension filter means applies to all
        return extension.lower() in [ext.lower() for ext in self.when["extensions"]]


@dataclass
class ValidatorConfig:
    """Configuration for a Python validator function."""

    name: str
    description: str
    module: str
    function: str
    applies_to: list[str]
    confidence: float = 0.0


@dataclass
class AssayTypeRule:
    """Rule for inferring assay type from other signals."""

    id: str
    priority: int
    conditions: dict[str, Any]
    assay_type: str


@dataclass
class IlluminaInstrument:
    """Mapping from instrument ID prefix to model name."""

    prefix: str
    model: str


@dataclass
class UnifiedRules:
    """Container for all unified rules and configurations."""

    extension_map: dict[str, str]
    rules: list[UnifiedRule]
    validators: dict[str, ValidatorConfig]
    assay_type_rules: list[AssayTypeRule]
    illumina_instruments: list[IlluminaInstrument]
    reference_contig_lengths: dict[str, dict[str, int]]

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
        ".fast5.tar.gz",
        ".fast5.tar",
    ]

    def get_rules_by_scope(self, scope: str) -> list[UnifiedRule]:
        """Get all rules for a given scope."""
        return [r for r in self.rules if r.scope == scope]

    def get_rules_by_tier(self, tier: int) -> list[UnifiedRule]:
        """Get all rules for a given tier."""
        return [r for r in self.rules if r.tier == tier]

    def get_rules_for_extension(self, extension: str) -> list[UnifiedRule]:
        """Get all rules that apply to a given file extension."""
        return [r for r in self.rules if r.matches_extension(extension)]

    def get_file_type(self, extension: str) -> str | None:
        """Get the file type for an extension."""
        return self.extension_map.get(extension.lower())

    def extract_extension(self, filename: str) -> str:
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


class RuleLoader:
    """Loader for unified classification rules."""

    VALID_SCOPES = {"extension", "filename", "header", "vcf_header", "fastq_header", "file_size"}
    VALID_TIERS = {1, 2, 3}

    def __init__(self, rules_path: str | Path | None = None):
        """Initialize the rule loader.

        Args:
            rules_path: Path to the unified rules YAML file.
                       Defaults to rules/unified_rules.yaml relative to project root.
        """
        if rules_path is None:
            # Default to rules/unified_rules.yaml relative to this file
            rules_path = Path(__file__).parent.parent.parent / "rules" / "unified_rules.yaml"
        self.rules_path = Path(rules_path)
        self._rules: UnifiedRules | None = None

    def load(self) -> UnifiedRules:
        """Load and parse the unified rules.

        Returns:
            UnifiedRules container with all rules and configurations.

        Raises:
            FileNotFoundError: If rules file doesn't exist.
            ValueError: If rules file has invalid structure.
        """
        if self._rules is not None:
            return self._rules

        if not self.rules_path.exists():
            raise FileNotFoundError(f"Rules file not found: {self.rules_path}")

        with open(self.rules_path) as f:
            docs = list(yaml.safe_load_all(f))

        if len(docs) < 2:
            raise ValueError("Rules file must have at least 2 YAML documents")

        # First document: extension_map
        extension_map = docs[0].get("extension_map", {})

        # Second document: rules
        rules_data = docs[1].get("rules", [])
        rules = self._parse_rules(rules_data)

        # Third document: validators (optional)
        validators = {}
        if len(docs) > 2 and docs[2]:
            validators = self._parse_validators(docs[2].get("validators", {}))

        # Fourth document: assay type rules (optional)
        assay_type_rules = []
        if len(docs) > 3 and docs[3]:
            assay_type_rules = self._parse_assay_type_rules(docs[3].get("assay_type_rules", []))

        # Fifth document: illumina instruments (optional)
        illumina_instruments = []
        if len(docs) > 4 and docs[4]:
            illumina_instruments = self._parse_illumina_instruments(
                docs[4].get("illumina_instruments", [])
            )

        # Sixth document: reference contig lengths (optional)
        reference_contig_lengths = {}
        if len(docs) > 5 and docs[5]:
            reference_contig_lengths = docs[5].get("reference_contig_lengths", {})

        self._rules = UnifiedRules(
            extension_map=extension_map,
            rules=rules,
            validators=validators,
            assay_type_rules=assay_type_rules,
            illumina_instruments=illumina_instruments,
            reference_contig_lengths=reference_contig_lengths,
        )

        return self._rules

    def _parse_rules(self, rules_data: list[dict]) -> list[UnifiedRule]:
        """Parse rule definitions from YAML."""
        rules = []
        seen_ids = set()

        for i, rule_data in enumerate(rules_data):
            rule_id = rule_data.get("id")
            if not rule_id:
                raise ValueError(f"Rule at index {i} missing required 'id' field")

            if rule_id in seen_ids:
                raise ValueError(f"Duplicate rule ID: {rule_id}")
            seen_ids.add(rule_id)

            tier = rule_data.get("tier")
            if tier not in self.VALID_TIERS:
                raise ValueError(f"Rule {rule_id}: invalid tier {tier}, must be one of {self.VALID_TIERS}")

            scope = rule_data.get("scope")
            if scope not in self.VALID_SCOPES:
                raise ValueError(f"Rule {rule_id}: invalid scope '{scope}', must be one of {self.VALID_SCOPES}")

            rules.append(UnifiedRule(
                id=rule_id,
                tier=tier,
                scope=scope,
                when=rule_data.get("when", {}),
                then=rule_data.get("then", {}),
                confidence=rule_data.get("confidence", 0.0),
                rationale=rule_data.get("rationale", ""),
                terminal=rule_data.get("terminal", False),
            ))

        return rules

    def _parse_validators(self, validators_data: dict) -> dict[str, ValidatorConfig]:
        """Parse validator configurations from YAML."""
        validators = {}

        for name, config in validators_data.items():
            validators[name] = ValidatorConfig(
                name=name,
                description=config.get("description", ""),
                module=config.get("module", ""),
                function=config.get("function", ""),
                applies_to=config.get("applies_to", []),
                confidence=config.get("confidence", 0.0),
            )

        return validators

    def _parse_assay_type_rules(self, rules_data: list[dict]) -> list[AssayTypeRule]:
        """Parse assay type inference rules from YAML."""
        rules = []

        for rule_data in rules_data:
            rules.append(AssayTypeRule(
                id=rule_data.get("id", ""),
                priority=rule_data.get("priority", 0),
                conditions=rule_data.get("conditions", {}),
                assay_type=rule_data.get("assay_type", ""),
            ))

        # Sort by priority (highest first)
        rules.sort(key=lambda r: r.priority, reverse=True)
        return rules

    def _parse_illumina_instruments(self, instruments_data: list[dict]) -> list[IlluminaInstrument]:
        """Parse Illumina instrument mappings from YAML."""
        return [
            IlluminaInstrument(
                prefix=inst.get("prefix", ""),
                model=inst.get("model", ""),
            )
            for inst in instruments_data
        ]

    def get_rules(self) -> UnifiedRules:
        """Get the loaded rules, loading if necessary."""
        if self._rules is None:
            return self.load()
        return self._rules


# Global singleton for convenient access
_default_loader: RuleLoader | None = None


def get_unified_rules(rules_path: str | Path | None = None) -> UnifiedRules:
    """Get the unified rules, loading from file if necessary.

    Args:
        rules_path: Optional path to rules file. If None, uses default.

    Returns:
        UnifiedRules container with all rules and configurations.
    """
    global _default_loader

    if rules_path is not None:
        # Use a new loader for custom path
        loader = RuleLoader(rules_path)
        return loader.load()

    if _default_loader is None:
        _default_loader = RuleLoader()

    return _default_loader.get_rules()


def reload_rules(rules_path: str | Path | None = None) -> UnifiedRules:
    """Force reload the unified rules from file.

    Args:
        rules_path: Optional path to rules file. If None, uses default.

    Returns:
        UnifiedRules container with all rules and configurations.
    """
    global _default_loader

    if rules_path is None:
        _default_loader = RuleLoader()
        return _default_loader.load()
    else:
        loader = RuleLoader(rules_path)
        return loader.load()
