"""Tests for AnVIL metadata record validation.

The constraints here were measured against the 758,658-record corpus, not
assumed. Two of them are counterintuitive and are pinned explicitly: `file_size`
may be 0, and `data_modality`/`reference_assembly` are nullable by design.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.metadata_schema import (
    ANVIL_RECORD_SCHEMA,
    validate_anvil_records,
    validate_pipeline_records,
)


def _record(**overrides):
    """A record that satisfies the full AnVIL schema."""
    rec = {
        "entry_id": "e1",
        "file_id": "f1",
        "file_name": "sample.bam",
        "file_format": ".bam",
        "file_size": 1234,
        "file_md5sum": "0" * 32,
        "drs_uri": "drs://drs.anv0:v2_abc",
        "dataset_id": "d1",
        "dataset_title": "ANVIL_HPRC",
        "is_supplementary": False,
        "data_modality": None,
        "reference_assembly": None,
    }
    rec.update(overrides)
    return rec


class TestAnvilSchema:
    def test_a_good_record_has_no_problems(self):
        assert validate_anvil_records([_record()]).is_valid

    def test_zero_file_size_is_valid(self):
        """Three corpus records have size 0. `min_value=0`, not 1."""
        assert validate_anvil_records([_record(file_size=0)]).is_valid

    def test_negative_file_size_is_a_range_problem(self):
        report = validate_anvil_records([_record(file_size=-1)])
        assert "range:file_size" in report.counts

    def test_declared_modality_and_assembly_are_nullable(self):
        """AnVIL's own declarations, null for ~99% of the corpus."""
        report = validate_anvil_records(
            [_record(data_modality=None, reference_assembly=None)]
        )
        assert report.is_valid

    def test_a_null_required_field_is_a_null_problem(self):
        report = validate_anvil_records([_record(file_name=None)])
        assert report.counts["null:file_name"] == 1

    def test_a_renamed_key_shows_up_as_missing(self):
        rec = _record()
        rec["fileName"] = rec.pop("file_name")
        report = validate_anvil_records([rec])
        assert report.counts["missing:file_name"] == 1

    def test_an_added_key_is_not_a_problem(self):
        """The API may add a column; that must not fail a download."""
        assert validate_anvil_records([_record(new_column="x")]).is_valid

    def test_a_stringified_size_is_a_type_problem(self):
        report = validate_anvil_records([_record(file_size="1234")])
        assert report.counts["type:file_size"] == 1

    def test_a_bool_is_not_an_int(self):
        """bool subclasses int, so isinstance(True, int) is True."""
        report = validate_anvil_records([_record(file_size=True)])
        assert report.counts["type:file_size"] == 1

    def test_an_empty_string_is_an_empty_problem(self):
        report = validate_anvil_records([_record(dataset_title="")])
        assert report.counts["empty:dataset_title"] == 1

    def test_a_malformed_md5_is_a_pattern_problem(self):
        report = validate_anvil_records([_record(file_md5sum="NOTHEX")])
        assert report.counts["pattern:file_md5sum"] == 1

    def test_uppercase_md5_is_rejected(self):
        report = validate_anvil_records([_record(file_md5sum="A" * 32)])
        assert report.counts["pattern:file_md5sum"] == 1

    def test_a_non_object_record_is_reported_not_crashed_on(self):
        report = validate_anvil_records([_record(), "not a dict", 42])
        assert report.counts["not_an_object"] == 2

    def test_samples_are_bounded(self):
        report = validate_anvil_records([_record(file_name=None) for _ in range(50)])
        assert report.counts["null:file_name"] == 50
        assert len(report.samples["null:file_name"]) == 3

    def test_summary_names_every_problem_kind(self):
        report = validate_anvil_records([_record(file_name=None, file_size=-1)])
        summary = report.summary()
        assert "null:file_name" in summary
        assert "range:file_size" in summary

    def test_schema_covers_the_twelve_fields_the_download_produces(self):
        assert len(ANVIL_RECORD_SCHEMA) == 12


class TestPipelineContract:
    """The pipeline reads four string fields and a size; a derived input may omit
    any of them, but must never carry a present-and-null value."""

    def test_a_minimal_record_is_valid(self):
        assert validate_pipeline_records([{"file_md5sum": "x"}]).is_valid

    def test_absent_fields_are_fine(self):
        assert validate_pipeline_records([{}]).is_valid

    def test_a_null_file_name_is_rejected(self):
        """`rec.get("file_name", "")` returns None for a null, and the first
        `.lower()` or slice downstream then raises."""
        report = validate_pipeline_records([{"file_md5sum": "x", "file_name": None}])
        assert report.counts["null:file_name"] == 1

    @pytest.mark.parametrize(
        "fld", ["file_md5sum", "file_name", "file_format", "dataset_title"]
    )
    def test_every_pipeline_string_field_rejects_null(self, fld):
        report = validate_pipeline_records([{fld: None}])
        assert report.counts[f"null:{fld}"] == 1

    def test_a_null_file_size_is_allowed(self):
        """Some derived inputs omit the size rather than the key."""
        assert validate_pipeline_records([{"file_size": None}]).is_valid

    def test_a_stringified_size_is_rejected(self):
        report = validate_pipeline_records([{"file_size": "100"}])
        assert report.counts["type:file_size"] == 1

    def test_a_bool_size_is_rejected(self):
        report = validate_pipeline_records([{"file_size": True}])
        assert report.counts["type:file_size"] == 1

    def test_zero_size_is_allowed_negative_is_not(self):
        assert validate_pipeline_records([{"file_size": 0}]).is_valid
        assert not validate_pipeline_records([{"file_size": -1}]).is_valid

    def test_the_pipeline_contract_does_not_require_the_anvil_fields(self):
        """drs_uri, entry_id, etc. are absent from a derived input and that is fine."""
        assert validate_pipeline_records([{"file_md5sum": "x", "file_name": "a.bam"}]).is_valid
