"""Unit tests for the classification field accessors (models.field_*).

These accessors are the seam the sentinel→status migration (epic #116) relies on:
value reads go through field_value, status checks through field_status, and
histogram/aggregation bucket keys through field_label. The suite pins their
semantics across every record layout, every sentinel state, and — critically —
the *future* explicit-``status`` shape that Stage 2/#120 will introduce (no
producer writes ``status`` yet, so only these tests exercise that path).
"""

import pytest

from src.meta_disco.models import (
    CLASSIFIED,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    build_field_entry,
    field_label,
    field_status,
    field_value,
)


def _wrapped(field, entry):
    """A per-field record: {"classifications": {field: entry}}."""
    return {"classifications": {field: entry}}


# --- field_value -----------------------------------------------------------

class TestFieldValue:
    def test_classified_wrapped(self):
        assert field_value(_wrapped("data_modality", {"value": "genomic"}), "data_modality") == "genomic"

    def test_sentinel_value_returned_verbatim_today(self):
        # Pre-split, the sentinel lives in `value`; field_value returns it raw.
        rec = _wrapped("reference_assembly", {"value": NOT_APPLICABLE})
        assert field_value(rec, "reference_assembly") == NOT_APPLICABLE

    def test_none_value(self):
        assert field_value(_wrapped("platform", {"value": None}), "platform") is None

    def test_nested_layout(self):
        assert field_value({"platform": {"value": "ONT"}}, "platform") == "ONT"

    def test_flat_layout(self):
        assert field_value({"platform": "ILLUMINA"}, "platform") == "ILLUMINA"

    def test_missing_field(self):
        assert field_value(_wrapped("platform", {"value": "ONT"}), "data_modality") is None

    def test_empty_record(self):
        assert field_value({}, "platform") is None

    def test_scalar_field(self):
        # Non-dimension scalar metadata: returned as-is (no sentinel semantics).
        assert field_value({"classifications": {"is_paired_end": False}}, "is_paired_end") is False

    def test_future_status_shape_returns_value(self):
        # Once sentinels move to `status`, an unclassified field has value=None.
        rec = _wrapped("platform", {"value": None, "status": NOT_CLASSIFIED})
        assert field_value(rec, "platform") is None


# --- field_status ----------------------------------------------------------

class TestFieldStatus:
    def test_classified(self):
        assert field_status(_wrapped("data_modality", {"value": "genomic"}), "data_modality") == CLASSIFIED

    def test_not_applicable_from_value(self):
        assert field_status(_wrapped("platform", {"value": NOT_APPLICABLE}), "platform") == NOT_APPLICABLE

    def test_not_classified_from_value(self):
        assert field_status(_wrapped("platform", {"value": NOT_CLASSIFIED}), "platform") == NOT_CLASSIFIED

    def test_none_value_is_not_classified(self):
        assert field_status(_wrapped("platform", {"value": None}), "platform") == NOT_CLASSIFIED

    def test_missing_field_is_not_classified(self):
        assert field_status({}, "platform") == NOT_CLASSIFIED

    def test_flat_scalar_classified(self):
        assert field_status({"platform": "ILLUMINA"}, "platform") == CLASSIFIED

    def test_explicit_status_preferred(self):
        # An explicit non-None status is returned verbatim — even values beyond
        # the three derived ones (e.g. conflict in a later stage).
        rec = _wrapped("data_modality", {"value": None, "status": "conflict"})
        assert field_status(rec, "data_modality") == "conflict"

    def test_explicit_none_status_falls_through_to_value(self):
        rec = _wrapped("platform", {"value": "ONT", "status": None})
        assert field_status(rec, "platform") == CLASSIFIED

    def test_future_split_shape(self):
        # Stage 3: value=None, status carries the sentinel.
        rec = _wrapped("reference_assembly", {"value": None, "status": NOT_APPLICABLE})
        assert field_status(rec, "reference_assembly") == NOT_APPLICABLE


# --- field_label -----------------------------------------------------------

class TestFieldLabel:
    def test_classified_returns_value(self):
        assert field_label(_wrapped("data_modality", {"value": "genomic"}), "data_modality") == "genomic"

    def test_not_applicable_returns_sentinel(self):
        assert field_label(_wrapped("platform", {"value": NOT_APPLICABLE}), "platform") == NOT_APPLICABLE

    def test_not_classified_returns_sentinel(self):
        assert field_label(_wrapped("platform", {"value": NOT_CLASSIFIED}), "platform") == NOT_CLASSIFIED

    def test_none_value_returns_not_classified(self):
        assert field_label(_wrapped("platform", {"value": None}), "platform") == NOT_CLASSIFIED

    def test_missing_field_returns_not_classified(self):
        assert field_label({}, "platform") == NOT_CLASSIFIED

    def test_never_none_for_sentinels(self):
        # The property histograms rely on: field_label is a usable bucket key,
        # never None, for the unclassified cases.
        assert field_label(_wrapped("platform", {"value": None}), "platform") is not None

    def test_future_split_preserves_sentinel_bucket(self):
        # Stage 3: sentinel moved to status; the bucket label still resolves to it.
        rec = _wrapped("reference_assembly", {"value": None, "status": NOT_APPLICABLE})
        assert field_label(rec, "reference_assembly") == NOT_APPLICABLE

    def test_future_split_classified_returns_value(self):
        rec = _wrapped("data_modality", {"value": "genomic", "status": CLASSIFIED})
        assert field_label(rec, "data_modality") == "genomic"

    def test_non_sentinel_status_surfaces(self):
        # A non-sentinel status (conflict) surfaces as the bucket label.
        rec = _wrapped("data_modality", {"value": None, "status": "conflict"})
        assert field_label(rec, "data_modality") == "conflict"


# --- consistency across the three accessors --------------------------------

@pytest.mark.parametrize("value,exp_status,exp_label", [
    ("genomic", CLASSIFIED, "genomic"),
    (NOT_APPLICABLE, NOT_APPLICABLE, NOT_APPLICABLE),
    (NOT_CLASSIFIED, NOT_CLASSIFIED, NOT_CLASSIFIED),
    (None, NOT_CLASSIFIED, NOT_CLASSIFIED),
])
def test_accessor_consistency_today(value, exp_status, exp_label):
    rec = _wrapped("data_modality", {"value": value})
    assert field_value(rec, "data_modality") == value
    assert field_status(rec, "data_modality") == exp_status
    assert field_label(rec, "data_modality") == exp_label


# --- coherence guard (#129): reject status=classified with a null value --------

class TestCoherenceGuard:
    def test_field_status_raises_on_classified_none(self):
        rec = _wrapped("data_modality", {"value": None, "status": CLASSIFIED})
        with pytest.raises(ValueError, match="incoherent"):
            field_status(rec, "data_modality")

    def test_field_label_raises_on_classified_none(self):
        # The declined None-guard, inverted: fail loudly instead of returning a
        # None bucket label from a self-contradictory entry.
        rec = _wrapped("data_modality", {"value": None, "status": CLASSIFIED})
        with pytest.raises(ValueError, match="incoherent"):
            field_label(rec, "data_modality")

    def test_coherent_classified_does_not_raise(self):
        rec = _wrapped("data_modality", {"value": "genomic", "status": CLASSIFIED})
        assert field_status(rec, "data_modality") == CLASSIFIED
        assert field_label(rec, "data_modality") == "genomic"

    def test_non_classified_status_with_none_value_is_fine(self):
        # not_applicable / not_classified / conflict with value=None are the
        # normal Stage 3 shape — only status==classified requires a value.
        for status in (NOT_APPLICABLE, NOT_CLASSIFIED, "conflict"):
            rec = _wrapped("reference_assembly", {"value": None, "status": status})
            assert field_status(rec, "reference_assembly") == status

    def test_legacy_sentinel_in_value_still_reads(self):
        # No explicit status (old on-disk shape) → derive; never triggers the guard.
        rec = _wrapped("reference_assembly", {"value": NOT_APPLICABLE})
        assert field_status(rec, "reference_assembly") == NOT_APPLICABLE


# --- build_field_entry: the single producer shape/invariant --------------------

class TestBuildFieldEntry:
    def test_classified_keeps_value(self):
        e = build_field_entry("genomic", confidence=0.9, evidence=[{"x": 1}])
        assert e == {"value": "genomic", "status": CLASSIFIED,
                     "confidence": 0.9, "evidence": [{"x": 1}]}

    def test_derived_sentinel_nulls_value(self):
        # Sentinel-carrying value with no explicit status → status derived, value nulled.
        assert build_field_entry(NOT_APPLICABLE)["value"] is None
        assert build_field_entry(NOT_APPLICABLE)["status"] == NOT_APPLICABLE
        assert build_field_entry(None)["status"] == NOT_CLASSIFIED

    def test_explicit_status_nulls_value_when_unclassified(self):
        e = build_field_entry(None, status=NOT_APPLICABLE)
        assert (e["value"], e["status"]) == (None, NOT_APPLICABLE)

    def test_explicit_classified_with_value(self):
        e = build_field_entry("reads", status=CLASSIFIED)
        assert (e["value"], e["status"]) == ("reads", CLASSIFIED)

    def test_evidence_defaults_to_fresh_list(self):
        a = build_field_entry(None)
        b = build_field_entry(None)
        assert a["evidence"] == [] and a["evidence"] is not b["evidence"]

    def test_classified_without_value_raises(self):
        # Self-guard: build_field_entry never emits the incoherent shape the
        # read-side guard would reject (#129).
        with pytest.raises(ValueError, match="CLASSIFIED"):
            build_field_entry(None, status=CLASSIFIED)
