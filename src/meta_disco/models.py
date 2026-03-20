"""Data models for file classification."""

from dataclasses import dataclass, field


# Classification value constants
NOT_APPLICABLE = "not_applicable"
NOT_CLASSIFIED = "not_classified"


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
    skip: bool = False
    needs_header_inspection: bool = False
    needs_study_context: bool = False
    needs_manual_review: bool = False
