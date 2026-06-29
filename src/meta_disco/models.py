"""Data models for file classification."""

from dataclasses import dataclass, field

# Classification status constants. NOT_APPLICABLE / NOT_CLASSIFIED are today
# smuggled into a field's `value`; the sentinel→status migration (epic #116) is
# splitting them into a dedicated `status` field. CLASSIFIED is the status when a
# real value was determined.
CLASSIFIED = "classified"
NOT_APPLICABLE = "not_applicable"
NOT_CLASSIFIED = "not_classified"

# The five classification dimension fields, in canonical output order. Single
# source of truth for the field set — the rule engine, rule_loader's 'then' key
# validation, and schema_vocab's dimensions all derive from this.
CLASSIFICATION_FIELDS = (
    "data_modality", "data_type", "platform", "reference_assembly", "assay_type",
)


def _field_entry(record: dict, field_name: str):
    """Return the per-field classification entry/value from a record, or None.

    Normalizes the layouts classification records appear in:
    - per-field:  record["classifications"][field] -> {"value", ...}
    - nested:     record[field] -> {"value", ...}
    - flat:       record[field] -> value
    Returns whatever is found at the field (a dict entry, a scalar, or None).
    """
    cls = record.get("classifications", {})
    if isinstance(cls, dict) and field_name in cls:
        return cls[field_name]
    return record.get(field_name)


def field_value(record: dict, field_name: str):
    """Resolved value of a classification field, normalizing record layout.

    Use this for *value* reads. For "is this field applicable / classified?"
    questions use field_status — so that when the sentinel→status migration moves
    sentinels out of `value` (epic #116), value-reads and status-checks stay
    correctly separated and call sites do not need to change again.
    """
    entry = _field_entry(record, field_name)
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def field_status(record: dict, field_name: str) -> str:
    """Status of a classification field.

    Returns an explicit non-None ``status`` from the field entry verbatim when
    present (the shape the migration is moving toward — this may be values beyond
    the three below, e.g. ``conflict`` in later stages). Otherwise derives the
    status from the current sentinel-in-``value`` convention, yielding one of
    CLASSIFIED / NOT_APPLICABLE / NOT_CLASSIFIED; a missing/None value reads as
    NOT_CLASSIFIED.
    """
    entry = _field_entry(record, field_name)
    if isinstance(entry, dict):
        if entry.get("status") is not None:
            return entry["status"]
        value = entry.get("value")
    else:
        value = entry
    if value == NOT_APPLICABLE:
        return NOT_APPLICABLE
    if value is None or value == NOT_CLASSIFIED:
        return NOT_CLASSIFIED
    return CLASSIFIED


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
