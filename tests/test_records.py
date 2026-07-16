"""Tests for the typed record views the pipeline parses at its load boundary (#172)."""

import pytest

from meta_disco.records import ClassifierRecord, InvalidRecord
from tests.metadata_fixtures import valid_record


class TestClassifierRecord:
    def test_from_record_exposes_typed_classifier_fields(self):
        rec = valid_record(file_name="a.bam", file_format=".bam", file_size=42, file_md5sum="a" * 32)
        cr = ClassifierRecord.from_record(rec)
        assert cr.file_name == "a.bam"
        assert cr.file_format == ".bam"
        assert cr.file_size == 42
        assert cr.file_md5sum == "a" * 32

    def test_passes_through_non_classifier_identity(self):
        cr = ClassifierRecord.from_record(valid_record(entry_id="e9", dataset_title="T"))
        assert cr.entry_id == "e9"
        assert cr.dataset_title == "T"

    def test_missing_optional_identity_is_none(self):
        rec = valid_record()
        del rec["dataset_title"]
        del rec["entry_id"]
        cr = ClassifierRecord.from_record(rec)
        assert cr.dataset_title is None
        assert cr.entry_id is None


class TestInvalidRecord:
    @pytest.mark.parametrize("raw,expected", [(None, ""), (123, "123"), ("x.bam", "x.bam"), ("", "")])
    def test_coerces_file_name_to_str(self, raw, expected):
        inv = InvalidRecord.from_record({"file_name": raw}, [])
        assert inv.file_name == expected
        assert isinstance(inv.file_name, str)

    @pytest.mark.parametrize("raw,expected", [(None, ""), (0, "0"), (".bam", ".bam")])
    def test_coerces_file_format_to_str(self, raw, expected):
        inv = InvalidRecord.from_record({"file_format": raw}, [])
        assert inv.file_format == expected
        assert isinstance(inv.file_format, str)

    @pytest.mark.parametrize("raw,expected", [(None, ""), (0, "0"), (False, "False"), ("", "")])
    def test_only_null_becomes_empty_falsy_values_are_preserved(self, raw, expected):
        # Only None (absent/null) maps to ""; a falsy-but-present drift like 0/False
        # is stringified, not erased (a str(x or "") would collapse both to "").
        inv = InvalidRecord.from_record({"file_name": raw}, [])
        assert inv.file_name == expected

    def test_passes_other_identity_fields_through_raw(self):
        # md5/size/title/entry_id are echoed as-is on the validation_failed path —
        # a drifted row may carry their raw (non-string) types.
        inv = InvalidRecord.from_record(
            {"file_md5sum": 5, "file_size": "big", "dataset_title": None, "entry_id": "e9"}, []
        )
        assert inv.file_md5sum == 5
        assert inv.file_size == "big"
        assert inv.dataset_title is None
        assert inv.entry_id == "e9"

    def test_carries_blocking_reasons(self):
        inv = InvalidRecord.from_record({"file_name": 7, "file_md5sum": "z"}, ["file_size: expected an integer"])
        assert inv.file_name == "7"
        assert inv.file_md5sum == "z"
        assert inv.reasons == ["file_size: expected an integer"]
