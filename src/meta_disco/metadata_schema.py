"""Validate raw AnVIL input metadata records against the modeled contract.

The contract is authored in ``src/meta_disco/schema/metadata.yaml`` and generates
the Pydantic model ``AnvilFileMetadataRecord`` (``schema/metadata_model.py``, via
``make gen-metadata``). This module validates records against that model — the
single source of truth for the field spec — so an API shape change is caught at
load instead of surfacing as a crash deep in a run (issue #161).

Two deliberate departures from the generated model's defaults:

* ``strict=True`` — a type drift (``file_size`` returned as the string ``"123"``,
  say) must *fail*, not silently coerce. Catching drift is the whole point.
* ``extra="ignore"`` — a record may carry columns beyond those modeled (the
  download script also emits ``organism_type`` / ``phenotypic_sex``); an unmodeled
  key must never fail a record.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import ConfigDict, ValidationError

from .models import CLASSIFICATION_FIELDS, NOT_CLASSIFIED, build_field_entry
from .schema.metadata_model import AnvilFileMetadataRecord

# rule_id stamped on the evidence of a record that failed input validation.
VALIDATION_RULE_ID = "input_validation"

# Offending entry_ids kept per problem kind, so a report over 758k records stays
# bounded while still pointing at concrete records to inspect.
_MAX_SAMPLE = 5

# `loc` a pydantic error carries when the whole record (not a field) is invalid —
# e.g. a non-dict where an object was expected. Kept as a named constant because
# both the reason formatter and the classification-blocking check test for it.
_RECORD_LOC = "<record>"

# The fields the classification/fetch path actually consumes. A contract violation
# on one of these makes the record unclassifiable; a violation on any *other*
# contract field is real drift the standalone gate reports, but does not by itself
# stop this record from classifying (issue #161 review: the run marks only what it
# genuinely cannot classify, the whole-corpus gate flags the rest).
#
# Keep in sync with the fields ClassifyPipeline._process_single_record reads and
# passes to _fetch_and_classify. A field the run consumes but omitted here would
# let a record bad on that field fetch instead of divert to validation_failed.
CLASSIFIER_RELEVANT_FIELDS = frozenset(
    {
        "file_md5sum",
        "file_name",
        "file_size",
        "file_format",
    }
)

# A violation blocks classification when it is on a classifier-relevant field or is
# a whole-record type error (a non-dict where an object was expected).
_BLOCKING_FIELDS = CLASSIFIER_RELEVANT_FIELDS | {_RECORD_LOC}


class _ValidatedRecord(AnvilFileMetadataRecord):
    """The generated contract, re-validated strictly and tolerant of extra keys.

    The child ``model_config`` overrides only ``strict`` and ``extra``; the rest of
    the generated base config is inherited. See the module docstring for why.
    """

    model_config = ConfigDict(extra="ignore", strict=True)


def validate_record(record) -> list[str]:
    """Return the reasons ``record`` violates the input contract; empty if valid.

    Each reason is a human-readable ``"<field>: <message>"`` string. Never mutates
    the record. A non-dict ``record`` (garbage where an object was expected) yields
    a single reason rather than raising.
    """
    try:
        _ValidatedRecord.model_validate(record)
        return []
    except ValidationError as exc:
        return [_format_error(err) for err in exc.errors()]


def _reason_field(reason: str) -> str:
    """The field a ``"<field>: <why>"`` reason refers to (text before the first ``:``)."""
    return reason.split(":", 1)[0]


def classification_blocking_reasons(record) -> list[str]:
    """Contract violations that make ``record`` unclassifiable; empty if classifiable.

    A record can violate the full contract on a field the classifier never reads
    (a provenance field like ``drs_uri`` or ``is_supplementary``) yet still be
    perfectly classifiable from its name/format/header. This returns only the
    violations on ``CLASSIFIER_RELEVANT_FIELDS`` (plus a whole-record type error),
    so the run diverts a record to ``validation_failed`` only when it truly cannot
    classify it. The other violations are real drift — surfaced loudly by the
    standalone ``validate_metadata`` gate over the whole corpus, not here.
    """
    return [r for r in validate_record(record) if _reason_field(r) in _BLOCKING_FIELDS]


# Value-independent description per pydantic error ``type``. Authored here rather
# than taken from ``err["msg"]`` because LinkML's generated pattern validators
# raise ``ValueError`` messages that embed the offending value ("Invalid
# file_md5sum format: <value>"). Grouping on those would split one drift into a
# distinct kind per bad value — 758k kinds in the worst case. These descriptions
# are constant per violation, so ``validate_records`` groups by kind as intended.
_TYPE_DESCRIPTIONS = {
    "missing": "required field is missing",
    "string_type": "expected a string",
    "int_type": "expected an integer",
    "bool_type": "expected a boolean",
    "float_type": "expected a number",
    "model_type": "expected an object",
    # LinkML pattern validators surface as a custom value_error.
    "value_error": "does not match the required format",
}


def _format_error(err: dict) -> str:
    """Render one pydantic error dict as a value-independent ``"<field>: <why>"``.

    For every error type this schema can raise, the description comes from
    ``_TYPE_DESCRIPTIONS`` (or the inlined ``greater_than_equal`` bound), not from
    ``err["msg"]``, so the same violation on different records yields the same
    string regardless of the offending value — which is what lets
    ``validate_records`` group by kind. Only an unmapped type (none in the current
    schema) falls back to pydantic's own message, which may embed the value.
    """
    loc = ".".join(str(part) for part in err["loc"]) or _RECORD_LOC
    etype = err.get("type", "")
    if etype == "greater_than_equal":
        bound = (err.get("ctx") or {}).get("ge")
        why = f"must be >= {bound}"
    else:
        why = _TYPE_DESCRIPTIONS.get(etype) or err.get("msg", etype)
    return f"{loc}: {why}"


def validation_failed_classifications(reasons: list[str]) -> dict:
    """Build a classifications dict marking every dimension ``not_classified``.

    A record that fails the input contract is written but classified as nothing:
    each of the five dimensions carries ``not_classified`` status and the
    validation reasons as evidence. It is never dropped — a missing row is
    indistinguishable from a file that was never seen (issue #155).

    Every dimension is blanked deliberately, even ones the filename alone could
    support (unlike the fetch-failure path, which keeps filename-derived values):
    a contract violation means the record's provenance is untrusted wholesale, so
    it is marked uniformly unclassifiable rather than partly classified.
    """

    # A fresh evidence list (and fresh dicts) per field: sharing one list across
    # all five dimensions would alias them, so a later in-place edit of one field's
    # evidence would silently mutate all five.
    def _evidence():
        return [{"rule_id": VALIDATION_RULE_ID, "reason": reason} for reason in reasons]

    return {fld: build_field_entry(None, status=NOT_CLASSIFIED, evidence=_evidence()) for fld in CLASSIFICATION_FIELDS}


@dataclass
class _ProblemKind:
    """One class of violation, its count, and a bounded sample of offenders."""

    reason: str
    count: int = 0
    sample_entry_ids: list = field(default_factory=list)


@dataclass
class ValidationReport:
    """Aggregate outcome of validating a batch of records.

    Counts failures by kind rather than listing every bad record, so a report over
    the full corpus stays readable. Never holds the records themselves.
    """

    total: int = 0
    invalid: int = 0
    kinds: dict = field(default_factory=dict)  # reason -> _ProblemKind

    @property
    def ok(self) -> bool:
        return self.invalid == 0

    def _record_problem(self, reason: str, entry_id) -> None:
        kind = self.kinds.get(reason)
        if kind is None:
            kind = _ProblemKind(reason=reason)
            self.kinds[reason] = kind
        kind.count += 1
        if len(kind.sample_entry_ids) < _MAX_SAMPLE:
            kind.sample_entry_ids.append(entry_id)

    def summary(self) -> str:
        """A human-readable summary: one block per problem kind, biggest first."""
        lines = [f"{self.total:,} records checked"]
        if self.ok:
            lines.append("OK — no problems.")
            return "\n".join(lines)
        lines.append(f"FAIL — {len(self.kinds)} problem kind(s), {self.invalid:,} record(s) affected:")
        for kind in sorted(self.kinds.values(), key=lambda k: (-k.count, k.reason)):
            lines.append(f"  {kind.reason}    {kind.count:,} record(s)")
            sample = ", ".join(str(e) for e in kind.sample_entry_ids)
            more = kind.count - len(kind.sample_entry_ids)
            suffix = f" … (+{more:,} more)" if more > 0 else ""
            lines.append(f"    sample entry_ids: {sample}{suffix}")
        return "\n".join(lines)


def validate_records(records) -> ValidationReport:
    """Validate every record, grouping violations by kind into a ValidationReport."""
    report = ValidationReport()
    for record in records:
        report.total += 1
        reasons = validate_record(record)
        if reasons:
            report.invalid += 1
            sample = _sample_label(record)
            for reason in reasons:
                report._record_problem(reason, sample)
    return report


def _sample_label(record) -> str:
    """A record's entry_id for the report sample, distinguishing the states that a
    truthy-or default would conflate: a missing key vs a present-but-empty/null
    entry_id (itself a contract violation worth seeing in drift diagnosis)."""
    if not isinstance(record, dict) or "entry_id" not in record:
        return "<unknown>"
    entry_id = record["entry_id"]
    return entry_id if entry_id not in (None, "") else "<empty>"
