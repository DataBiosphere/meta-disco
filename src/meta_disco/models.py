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
    "data_modality",
    "data_type",
    "platform",
    "reference_assembly",
    "assay_type",
)


def _field_entry(record: dict, field_name: str):
    """Return the per-field classification entry/value from a record, or None.

    Normalizes the layouts classification records appear in:
    - per-field:  record["classifications"][field] -> {"value", ...}
    - nested:     record[field] -> {"value", ...}
    - flat:       record[field] -> value
    Returns whatever is found at the field (a dict entry, a scalar, or None).
    """
    cls = record.get("classifications")
    if isinstance(cls, dict) and field_name in cls:
        return cls[field_name]
    return record.get(field_name)


def _entry_value(entry):
    """Resolved value from a per-field entry (a dict ``{"value": ...}`` or scalar)."""
    return entry.get("value") if isinstance(entry, dict) else entry


def status_for_value(value) -> str:
    """Derive a field's status from its (pre-split) value.

    The one place that maps a sentinel-carrying ``value`` to a status string:
    ``not_applicable`` → NOT_APPLICABLE, ``None``/``not_classified`` →
    NOT_CLASSIFIED, any real value → CLASSIFIED. Used by the read side
    (``_entry_status``) and by ``build_field_entry`` when a producer carries the
    sentinel in ``value`` and no explicit status is given, so reader and producers
    stay in lockstep as epic #116 moves sentinels out of ``value``.
    """
    if value == NOT_APPLICABLE:
        return NOT_APPLICABLE
    if value is None or value == NOT_CLASSIFIED:
        return NOT_CLASSIFIED
    return CLASSIFIED


def _assert_coherent(value, status) -> None:
    """Raise ValueError if (value, status) contradict epic #116's Stage 3 contract.

    The single definition of entry coherence: a CLASSIFIED field must carry a real
    value (not None, not a sentinel string), and a non-CLASSIFIED status must not
    carry one. Enforced on both sides — when building output (``build_field_entry``)
    and when reading an explicit status (``_entry_status``) — so a sentinel can
    never be smuggled into ``value`` under a classified status, or a real value be
    dropped under a non-classified status, from either direction.
    """
    value_is_real = status_for_value(value) == CLASSIFIED
    if status == CLASSIFIED and not value_is_real:
        raise ValueError(f"incoherent entry: CLASSIFIED status requires a real value, got {value!r}")
    if status != CLASSIFIED and value_is_real:
        raise ValueError(f"incoherent entry: {status!r} status must not carry a real value, got {value!r}")


def build_field_entry(value, status=None, evidence=None) -> dict:
    """Build a serialized per-field classification entry.

    The single place that assembles the ``{value, status, evidence}`` output shape
    and enforces epic #116's Stage 3 invariant: sentinels live only in ``status``
    and ``value`` is ``None`` unless the field is CLASSIFIED. Every producer
    (rule_engine's ``to_output_dict``, the index-propagation script, the
    header_classifier empty-input fallback) goes through here, so the invariant is
    defined once. When an explicit ``status`` is passed it must be coherent with
    ``value``: a CLASSIFIED status requires a real value, and a non-CLASSIFIED
    status must not carry one (a sentinel or ``None`` is fine) — either mismatch
    raises ValueError rather than smuggling a sentinel into ``value`` or silently
    dropping a real value. So the entry is always coherent and the read-side guard
    (``_entry_status``) is never handed a contradictory shape.

    ``status`` defaults to ``status_for_value(value)`` for producers that still
    carry the sentinel in ``value``; pass it explicitly when the status is known
    directly. The derived path is coherent by construction and never raises.
    """
    if status is None:
        status = status_for_value(value)
    _assert_coherent(value, status)
    return {
        "value": value if status == CLASSIFIED else None,
        "status": status,
        "evidence": evidence if evidence is not None else [],
    }


def _entry_status(entry) -> str:
    """Status from a per-field entry: explicit ``status`` if set, else derived.

    When the entry carries an explicit ``status``, it is validated against ``value``
    via ``_assert_coherent`` — an incoherent pairing (CLASSIFIED without a real
    value, or a non-CLASSIFIED status carrying a real value) raises ValueError.
    Epic #116's Stage 3 invariant is that sentinels live only in ``status``; this
    is the loud-failure counterpart to the declined field_label None-guard (#129):
    reject the self-contradictory shape rather than fabricating a bucket label from
    it. Both field_status and field_label route through here, so both fail loudly
    instead of silently mis-reading a smuggled sentinel as a classified value.
    """
    if isinstance(entry, dict):
        status = entry.get("status")
        if status is not None:
            _assert_coherent(entry.get("value"), status)
            return status
        value = entry.get("value")
    else:
        value = entry
    return status_for_value(value)


def field_value(record: dict, field_name: str):
    """Resolved value of a classification field, normalizing record layout.

    Use this for *value* reads. For "is this field applicable / classified?"
    questions use field_status, and for histogram / aggregation bucket keys that
    should fold unclassified into a sentinel bucket use field_label — so that when
    the sentinel→status migration moves sentinels out of `value` (epic #116),
    value-reads, status-checks, and bucket labels stay correctly separated and
    call sites do not need to change again.
    """
    return _entry_value(_field_entry(record, field_name))


def field_status(record: dict, field_name: str) -> str:
    """Status of a classification field.

    Returns an explicit non-None ``status`` from the field entry verbatim when
    present (the shape the migration is moving toward — this may be values beyond
    the three below, e.g. ``conflict`` in later stages). Otherwise derives the
    status from the current sentinel-in-``value`` convention, yielding one of
    CLASSIFIED / NOT_APPLICABLE / NOT_CLASSIFIED; a missing/None value reads as
    NOT_CLASSIFIED.
    """
    return _entry_status(_field_entry(record, field_name))


def field_label(record: dict, field_name: str) -> str | None:
    """Display label for a field: its value when classified, else its status.

    Reproduces the pre-split convention where ``value`` held either a real value or
    a sentinel — for histograms / aggregations that bucket by that combined label.
    Returns the field_value when status is CLASSIFIED (which may be None only in the
    future explicit-status shape), otherwise the status string. Survives the
    sentinel→status split (epic #116): the not_applicable / not_classified buckets
    persist via the status once sentinels move out of ``value`` (a non-sentinel
    status such as ``conflict`` would likewise surface here).
    """
    entry = _field_entry(record, field_name)
    status = _entry_status(entry)
    return _entry_value(entry) if status == CLASSIFIED else status


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
    reasons: list[str] = field(default_factory=list)
    rules_matched: list[str] = field(default_factory=list)
