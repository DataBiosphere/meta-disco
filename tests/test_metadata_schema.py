"""Tests for the input-metadata contract validator (issue #161)."""

import pytest

from meta_disco.metadata_schema import (
    VALIDATION_RULE_ID,
    ValidationReport,
    classification_blocking_reasons,
    validate_record,
    validate_records,
    validation_failed_classifications,
)
from meta_disco.models import CLASSIFICATION_FIELDS, NOT_CLASSIFIED
from tests.metadata_fixtures import valid_record as _valid


class TestValidRecords:
    def test_a_complete_record_passes(self):
        assert validate_record(_valid()) == []

    def test_file_size_zero_is_valid(self):
        # Three zero-size files exist in the corpus; the bound is >= 0, not > 0.
        assert validate_record(_valid(file_size=0)) == []

    def test_nullable_declarations_may_be_null(self):
        # data_modality / reference_assembly are AnVIL's own declarations, null for
        # ~99% of the corpus. Rejecting null there would reject nearly everything.
        assert validate_record(_valid(data_modality=None, reference_assembly=None)) == []

    def test_nullable_declarations_may_carry_a_value(self):
        assert validate_record(_valid(data_modality="genomic",
                                      reference_assembly="GRCh38")) == []

    def test_extra_keys_are_tolerated(self):
        # The download script also emits organism_type / phenotypic_sex, absent from
        # the current on-disk data; an unmodeled column must not fail a record.
        assert validate_record(_valid(organism_type="human", phenotypic_sex="male")) == []


class TestFieldConstraints:
    @pytest.mark.parametrize("field", [
        "entry_id", "file_id", "file_name", "file_format",
        "file_md5sum", "drs_uri", "dataset_id", "dataset_title",
    ])
    def test_required_string_field_rejects_null(self, field):
        reasons = validate_record(_valid(**{field: None}))
        assert any(field in r for r in reasons)

    @pytest.mark.parametrize("field", [
        "entry_id", "file_id", "file_name", "file_format",
        "dataset_id", "dataset_title",
    ])
    def test_string_field_rejects_empty(self, field):
        reasons = validate_record(_valid(**{field: ""}))
        assert any(field in r for r in reasons)

    def test_missing_key_is_reported_as_required(self):
        record = _valid()
        del record["file_name"]
        reasons = validate_record(record)
        assert reasons == ["file_name: required field is missing"]

    def test_stringified_file_size_fails_not_coerced(self):
        # A drift where file_size arrives as a JSON string must fail, not silently
        # coerce to int — strict validation is the whole point.
        assert validate_record(_valid(file_size="1000")) == [
            "file_size: expected an integer"]

    def test_negative_file_size_fails(self):
        assert validate_record(_valid(file_size=-1)) == ["file_size: must be >= 0"]

    def test_bad_md5_fails(self):
        assert validate_record(_valid(file_md5sum="NOTHEX")) == [
            "file_md5sum: does not match the required format"]

    def test_uppercase_md5_fails(self):
        assert validate_record(_valid(file_md5sum="0" * 31 + "A")) == [
            "file_md5sum: does not match the required format"]

    def test_non_drs_uri_fails(self):
        assert validate_record(_valid(drs_uri="s3://bucket/key")) == [
            "drs_uri: does not match the required format"]

    def test_non_boolean_is_supplementary_fails(self):
        assert validate_record(_valid(is_supplementary="true")) == [
            "is_supplementary: expected a boolean"]

    def test_non_dict_record_fails_gracefully(self):
        assert validate_record("garbage") == ["<record>: expected an object"]

    def test_a_record_can_have_several_problems(self):
        reasons = validate_record(_valid(file_size="x", file_md5sum="bad"))
        assert len(reasons) == 2


class TestValidationReport:
    def test_clean_corpus_reports_ok(self):
        report = validate_records([_valid(), _valid(entry_id="e2")])
        assert report.ok
        assert report.total == 2
        assert report.invalid == 0
        assert "OK — no problems." in report.summary()

    def test_groups_by_kind_across_distinct_values(self):
        # 100 records, each a *different* bad md5, must collapse to ONE kind — else a
        # single drift would explode the report into thousands of one-off entries.
        records = [_valid(entry_id=f"e{i}", file_md5sum=f"bad{i}") for i in range(100)]
        report = validate_records(records)
        assert not report.ok
        assert report.invalid == 100
        assert len(report.kinds) == 1
        (kind,) = report.kinds.values()
        assert kind.count == 100

    def test_sample_is_bounded_and_names_entry_ids(self):
        records = [_valid(entry_id=f"e{i}", file_size="x") for i in range(50)]
        report = validate_records(records)
        (kind,) = report.kinds.values()
        assert kind.count == 50
        assert len(kind.sample_entry_ids) == 5  # bounded
        assert kind.sample_entry_ids[0] == "e0"
        summary = report.summary()
        assert "50 record(s)" in summary
        assert "+45 more" in summary

    def test_separate_kinds_are_counted_separately(self):
        report = validate_records([
            _valid(file_size="x"),
            _valid(file_md5sum="bad"),
            _valid(drs_uri="nope"),
        ])
        assert report.invalid == 3
        assert len(report.kinds) == 3

    def test_missing_entry_id_falls_back_to_placeholder(self):
        rec = _valid(file_size="x")
        del rec["entry_id"]
        report = validate_records([rec])
        samples = {s for k in report.kinds.values() for s in k.sample_entry_ids}
        assert "<unknown>" in samples


    def test_a_fresh_empty_report_is_ok(self):
        report = ValidationReport()
        assert report.ok
        assert report.total == 0


class TestClassificationBlockingReasons:
    def test_valid_record_blocks_nothing(self):
        assert classification_blocking_reasons(_valid()) == []

    @pytest.mark.parametrize("field", ["file_md5sum", "file_name", "file_size", "file_format"])
    def test_classifier_relevant_violation_blocks(self, field):
        bad = "" if field != "file_size" else "x"
        reasons = classification_blocking_reasons(_valid(**{field: bad}))
        assert reasons and all(field in r for r in reasons)

    # Values that violate the full contract on a classifier-irrelevant field.
    @pytest.mark.parametrize("field,bad", [
        ("drs_uri", "s3://not-drs"),      # fails the drs:// pattern
        ("is_supplementary", "not-a-bool"),  # fails the bool type
        ("file_id", None),                # fails required non-null string
        ("dataset_id", None),
    ])
    def test_classifier_irrelevant_violation_does_not_block(self, field, bad):
        # These fields violate the full contract (validate_record flags them) but
        # the classifier never reads them, so they must not divert the record.
        assert validate_record(_valid(**{field: bad}))          # full contract fails
        assert classification_blocking_reasons(_valid(**{field: bad})) == []

    def test_only_relevant_reasons_returned_when_both_present(self):
        rec = _valid(file_size="x", drs_uri="nope")
        reasons = classification_blocking_reasons(rec)
        assert reasons == ["file_size: expected an integer"]

    def test_non_dict_record_blocks(self):
        assert classification_blocking_reasons("garbage") == ["<record>: expected an object"]


class TestValidationFailedClassifications:
    def test_marks_every_dimension_not_classified_with_reasons(self):
        reasons = ["file_size: expected an integer"]
        cls = validation_failed_classifications(reasons)
        assert set(cls) == set(CLASSIFICATION_FIELDS)
        for entry in cls.values():
            assert entry["value"] is None
            assert entry["status"] == NOT_CLASSIFIED
            assert entry["evidence"] == [
                {"rule_id": VALIDATION_RULE_ID, "reason": reasons[0]}]

    def test_all_reasons_are_carried_as_evidence(self):
        reasons = ["file_size: expected an integer", "file_name: expected a string"]
        cls = validation_failed_classifications(reasons)
        for entry in cls.values():
            assert [e["reason"] for e in entry["evidence"]] == reasons

    def test_evidence_is_not_shared_across_dimensions(self):
        # Each dimension must own its evidence list — a shared list would alias all
        # five, so mutating one would mutate them all.
        cls = validation_failed_classifications(["file_size: expected an integer"])
        entries = list(cls.values())
        entries[0]["evidence"].append({"rule_id": "x", "reason": "y"})
        assert all(len(e["evidence"]) == 1 for e in entries[1:])
