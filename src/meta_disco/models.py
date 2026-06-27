"""Data models for file classification."""

from dataclasses import dataclass, field

# Classification value constants
NOT_APPLICABLE = "not_applicable"
NOT_CLASSIFIED = "not_classified"

# The five classification dimension fields, in canonical output order. Single
# source of truth for the field set — the rule engine, rule_loader's 'then' key
# validation, and schema_vocab's dimensions all derive from this.
CLASSIFICATION_FIELDS = (
    "data_modality", "data_type", "platform", "reference_assembly", "assay_type",
)


@dataclass
class FileInfo:
    """Input file information for classification."""

    filename: str
    file_size: int | None = None
    dataset_title: str | None = None
    # Future: bam_header, vcf_header for Tier 5


@dataclass
class ClassificationResult:
    """Result of classifying a file."""

    data_modality: str | None = None
    reference_assembly: str | None = None
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    rules_matched: list[str] = field(default_factory=list)
