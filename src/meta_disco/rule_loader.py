"""Loader for unified classification rules from YAML."""

from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, ClassVar

import yaml

from .file_name import FileName
from .models import CLASSIFICATION_FIELDS, NOT_APPLICABLE, NOT_CLASSIFIED


def default_rules_resource():
    """The bundled ``unified_rules.yaml``, as a package-data resource.

    Anchored on this module's own package (``{__package__}.rules``), so it resolves
    whether ``meta_disco`` is installed as a wheel or run from a checkout (#166),
    mirroring ``schema_vocab.default_schema_path``. Returns an ``importlib.resources``
    traversable; both it and ``pathlib.Path`` support ``.read_text()`` and ``str()``,
    so it and an explicitly-passed filesystem path are handled uniformly.
    """
    return files(f"{__package__}.rules") / "unified_rules.yaml"


@dataclass
class UnifiedRule:
    """A unified classification rule.

    ``then`` holds only real dimension values ({field: value}). A field a rule
    declares non-classified is authored in the ``then.status`` sub-map instead and
    parsed into ``then_status`` ({field: status}); the two never share a field. So
    a sentinel (``not_applicable`` / ``not_classified``) is never written into a
    value slot — see epic #116 / issue #133.
    """

    id: str
    tier: int
    scope: str
    when: dict[str, Any]
    then: dict[str, Any]
    rationale: str
    then_status: dict[str, str] = field(default_factory=dict)

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
    COMPOUND_EXTENSIONS: ClassVar[list[str]] = [
        ".g.vcf.gz",  # Must come before .vcf.gz
        ".gvcf.gz",
        ".vcf.gz",
        ".fastq.gz",
        ".fq.gz",
        ".fasta.gz",
        ".fa.gz",
        ".bed.gz",
        ".sam.gz",
        ".rgfa.gz",
        ".gfa.gz",
        ".fast5.tar.gz",  # Must come before .tar.gz
        ".fast5.tar",  # Must come before .tar
        ".tar.gz",
        ".mtx.gz",
    ]

    # Compression and archive suffixes — "wrappers" around the format, not the
    # format itself (see FileName). Kept as advice; in this foundation they are
    # informational and may overlap the still-compound extension (the clean
    # split is #244).
    WRAPPER_SUFFIXES: ClassVar[tuple[str, ...]] = (".gz", ".bgz", ".bz2", ".xz", ".zip", ".tar")

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

    def parse_file_name(self, filename: str) -> "FileName":
        """Parse ``filename`` into a :class:`FileName` against this vocabulary.

        The parse is vocabulary-gated (it consults ``COMPOUND_EXTENSIONS`` /
        ``extension_map``), so it lives here with the rules rather than on the
        pure ``FileName`` data type. ``extension`` equals ``extract_extension``
        for every name with a known extension, so rule routing is unchanged for
        those; a name with no known extension yields ``None`` rather than the
        junk suffix ``extract_extension`` returns (which matched no rules anyway).
        """
        lower = filename.lower()

        extension = None
        for ext in self.COMPOUND_EXTENSIONS:
            if lower.endswith(ext):
                extension = ext
                break
        if extension is None and "." in filename:
            simple = "." + filename.rsplit(".", 1)[-1].lower()
            if simple in self.extension_map:
                extension = simple

        wrappers: list[str] = []
        rest = lower
        while True:
            for suffix in self.WRAPPER_SUFFIXES:
                if rest.endswith(suffix):
                    wrappers.append(suffix)
                    rest = rest[: -len(suffix)]
                    break
            else:
                break
        wrappers.reverse()  # name order: "x.tar.gz" -> (".tar", ".gz")

        stem = filename[: -len(extension)] if extension else filename
        return FileName(raw=filename, stem=stem, extension=extension, wrappers=tuple(wrappers))


class RuleLoader:
    """Loader for unified classification rules."""

    VALID_SCOPES: ClassVar[set[str]] = {"extension", "filename", "header", "vcf_header", "fastq_header", "file_size"}
    VALID_TIERS: ClassVar[set[int]] = {1, 2, 3}

    # Condition keys the engine interprets. Keep in sync with
    # rule_engine.RuleEngine._rule_matches() and its _match_* helpers — a key not
    # listed here is silently ignored at match time, so an unrecognized key is
    # almost always a typo (e.g. "filename_patern").
    VALID_WHEN_KEYS: ClassVar[set[str]] = {
        "always",
        "extensions",
        "filename_pattern",
        "dataset_pattern",
        "file_format",
        "file_size_min_gb",
        "file_size_max_gb",
        "platform",
        "modality_not_set",
        "reference_not_set",
        "header_section",
        "header_field",
        "header_pattern",
        "header_absent",
        "vcf_header_type",
        "vcf_pattern",
        "fastq_pattern",
    }
    # Effect keys _apply_rule() reads from a `then` block: the classification
    # fields (real-value effects) plus the reserved `status` key, whose value is a
    # sub-map of {field: status} for fields a rule declares non-classified (#133).
    # A key not listed here would never be applied, so it is treated as an error.
    THEN_STATUS_KEY: ClassVar[str] = "status"
    VALID_THEN_KEYS: ClassVar[set[str]] = set(CLASSIFICATION_FIELDS) | {THEN_STATUS_KEY}

    # Statuses a rule may author in a `then.status` sub-map. `classified` is
    # implied by a real value and `conflict` is engine-derived, so neither may be
    # written by a rule (mirrors schema_vocab's antecedent/emitted split).
    AUTHORABLE_STATUSES: ClassVar[set[str]] = {NOT_APPLICABLE, NOT_CLASSIFIED}

    # assay_type_rules condition keys that infer_assay_type() treats as iterables
    # (`x not in platform_in`, `any(r in ... for r in matched_rules_any)`). A
    # scalar string here silently becomes a per-character membership test, so it
    # must be a list. Keep in sync with rule_engine.RuleEngine.infer_assay_type().
    LIST_VALUED_ASSAY_CONDITIONS: ClassVar[set[str]] = {"platform_in", "matched_rules_any"}

    def __init__(self, rules_path: str | Path | None = None):
        """Initialize the rule loader.

        Args:
            rules_path: Path to the unified rules YAML file. Defaults to the bundled
                ``unified_rules.yaml`` shipped as package data of ``meta_disco.rules``.
        """
        # The default (bundled) resource resolves lazily in load(), so a missing
        # meta_disco.rules package (ModuleNotFoundError from files()) and a missing
        # YAML both surface through load()'s one friendly error. An explicit path is
        # a plain filesystem Path. _is_default tailors that message: a missing bundled
        # resource means a broken install, a missing explicit path is the caller's.
        self._is_default = rules_path is None
        # Narrow on rules_path directly (not self._is_default, which pyright can't
        # correlate with rules_path's None-ness) so the Path() call type-checks.
        self.rules_path = None if rules_path is None else Path(rules_path)
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

        try:
            # rules_path is None only for the default (unresolved) case; resolve it
            # to the bundled resource here. Binding to a local lets pyright narrow
            # away None for the read_text() call below.
            resource = self.rules_path
            if resource is None:
                resource = default_rules_resource()
                self.rules_path = resource
            text = resource.read_text(encoding="utf-8")
        except (FileNotFoundError, KeyError, ModuleNotFoundError) as e:
            # KeyError: a zip-backed resource (zipapp / un-unpacked wheel) reports a
            # missing entry that way rather than as FileNotFoundError. ModuleNotFoundError:
            # files() raises it if the meta_disco.rules package was dropped entirely, in
            # which case rules_path is still None — name the package instead of a path.
            if not self._is_default:
                raise FileNotFoundError(f"Rules file not found at {self.rules_path}") from e
            lead = (
                f"Rules file not found at {self.rules_path}"
                if self.rules_path is not None
                else f"Rules not found in the {__package__}.rules package"
            )
            raise FileNotFoundError(
                f"{lead}. It ships as package data of {__package__}.rules — "
                "reinstall/rebuild the package (uv sync), or run from a checkout "
                "where src/meta_disco/rules/ is present."
            ) from e
        docs = list(yaml.safe_load_all(text))

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
            illumina_instruments = self._parse_illumina_instruments(docs[4].get("illumina_instruments", []))

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
        """Parse rule definitions from YAML.

        Validates each rule's id (present, unique), tier, scope, and the keys
        used in its ``when``/``then`` blocks (against VALID_WHEN_KEYS /
        VALID_THEN_KEYS), including the ``then.status`` sub-map (fields, authorable
        statuses, and value/status non-overlap — see ``_parse_then_status``).
        Raises ValueError on any violation. Does not validate ``then`` *values*
        against the controlled vocabulary — that check lives in
        tests/test_rule_vocabulary.py, which reads the LinkML schema.
        """
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

            # Coerce only a null block to {}; any other non-mapping (e.g. "" or [])
            # is a malformed rule and must raise rather than silently become an
            # unconditional match.
            when = rule_data.get("when", {})
            if when is None:
                when = {}
            if not isinstance(when, dict):
                raise ValueError(f"Rule {rule_id}: 'when' must be a mapping, got {type(when).__name__}")
            unknown_when = set(when) - self.VALID_WHEN_KEYS
            if unknown_when:
                raise ValueError(
                    f"Rule {rule_id}: unknown 'when' condition key(s) {sorted(unknown_when)}; "
                    f"valid keys are {sorted(self.VALID_WHEN_KEYS)}"
                )

            then = rule_data.get("then", {})
            if then is None:
                then = {}
            if not isinstance(then, dict):
                raise ValueError(f"Rule {rule_id}: 'then' must be a mapping, got {type(then).__name__}")
            unknown_then = set(then) - self.VALID_THEN_KEYS
            if unknown_then:
                raise ValueError(
                    f"Rule {rule_id}: unknown 'then' effect key(s) {sorted(unknown_then)}; "
                    f"valid keys are {sorted(self.VALID_THEN_KEYS)}"
                )
            then_values = {k: v for k, v in then.items() if k != self.THEN_STATUS_KEY}
            then_status = self._parse_then_status(rule_id, then.get(self.THEN_STATUS_KEY), then_values)

            rules.append(
                UnifiedRule(
                    id=rule_id,
                    tier=tier,
                    scope=scope,
                    when=when,
                    then=then_values,
                    rationale=rule_data.get("rationale", ""),
                    then_status=then_status,
                )
            )

        return rules

    def _parse_then_status(self, rule_id: str, raw: Any, then_values: dict[str, Any]) -> dict[str, str]:
        """Validate and return a rule's ``then.status`` sub-map ({field: status}).

        ``raw`` is the value of the ``then.status`` key (``None`` if the block has
        no ``status``). Each key must be a classification field, each value an
        authorable status (``not_applicable`` / ``not_classified`` — not the
        implied ``classified`` or engine-derived ``conflict``), and no field may
        also carry a real value in ``then_values`` (a value-vs-status
        contradiction). Raises ValueError on any violation.
        """
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError(f"Rule {rule_id}: 'then.status' must be a mapping, got {type(raw).__name__}")
        unknown_fields = set(raw) - set(CLASSIFICATION_FIELDS)
        if unknown_fields:
            raise ValueError(
                f"Rule {rule_id}: unknown 'then.status' field(s) {sorted(unknown_fields)}; "
                f"valid fields are {sorted(CLASSIFICATION_FIELDS)}"
            )
        bad = sorted(f"{k}={v!r}" for k, v in raw.items() if v not in self.AUTHORABLE_STATUSES)
        if bad:
            raise ValueError(
                f"Rule {rule_id}: 'then.status' values must be one of {sorted(self.AUTHORABLE_STATUSES)}; got {bad}"
            )
        conflicting = set(raw) & set(then_values)
        if conflicting:
            raise ValueError(
                f"Rule {rule_id}: field(s) {sorted(conflicting)} appear in both 'then' "
                f"(as a value) and 'then.status' (as a status) — a field is one or the other"
            )
        return dict(raw)

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
            )

        return validators

    def _parse_assay_type_rules(self, rules_data: list[dict]) -> list[AssayTypeRule]:
        """Parse assay type inference rules from YAML."""
        rules = []

        for rule_data in rules_data:
            assay_id = rule_data.get("id", "")

            # Coerce only a null block to {} (a catch-all rule); any other
            # non-mapping is malformed and must raise rather than crash
            # infer_assay_type, which assumes conditions is a mapping. Mirrors
            # the when/then handling in _parse_rules.
            conditions = rule_data.get("conditions", {})
            if conditions is None:
                conditions = {}
            if not isinstance(conditions, dict):
                raise ValueError(
                    f"Assay type rule {assay_id}: 'conditions' must be a mapping, got {type(conditions).__name__}"
                )

            # List-typed condition keys must be lists; a scalar string would be
            # iterated character-by-character by infer_assay_type and silently
            # mis-match (e.g. platform_in: ILLUMINA).
            for key in self.LIST_VALUED_ASSAY_CONDITIONS:
                if key in conditions and not isinstance(conditions[key], list):
                    raise ValueError(
                        f"Assay type rule {assay_id}: condition '{key}' must be a "
                        f"list, got {type(conditions[key]).__name__}"
                    )

            rules.append(
                AssayTypeRule(
                    id=assay_id,
                    priority=rule_data.get("priority", 0),
                    conditions=conditions,
                    assay_type=rule_data.get("assay_type", ""),
                )
            )

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
    loader = RuleLoader(rules_path)
    return loader.load()
