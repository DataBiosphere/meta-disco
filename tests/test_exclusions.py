"""Tests for the checksum-less exclusion (#376).

The guarantee under test is narrow and absolute: a record with no well-formed
``file_md5sum`` reaches no classification output, and every one that is excluded is
named in the run's ``excluded_files.json``.
"""

import json

import pytest

from meta_disco.exclusions import (
    EXCLUDED_FILE,
    NO_CHECKSUM_REASON,
    ExcludedFile,
    has_usable_checksum,
    partition_records,
    read_excluded,
    write_excluded,
)
from meta_disco.output_utils import CLASSIFICATION_FILES
from tests.metadata_fixtures import valid_record

GOOD_MD5 = "0123456789abcdef0123456789abcdef"


def _record(**overrides):
    """A contract-shaped record, defaulted to a usable md5 and a full identity set.

    Built from the shared ``valid_record`` so the identity fields ``ExcludedFile``
    echoes stay tied to the input contract rather than to a hand-written literal.
    """
    defaults = {
        "file_name": "sample.bam",
        "file_format": ".bam",
        "file_size": 100,
        "file_md5sum": GOOD_MD5,
        "entry_id": "e1",
        "file_id": "f1",
        "drs_uri": "drs://example/f1",
        "dataset_title": "Study A",
    }
    return valid_record(**{**defaults, **overrides})


class TestHasUsableChecksum:
    def test_well_formed_md5_is_usable(self):
        assert has_usable_checksum(_record()) is True

    @pytest.mark.parametrize(
        "md5",
        [
            None,
            "",
            "abc123",
            "a" * 31,
            "a" * 33,
            GOOD_MD5.upper(),
            "0123456789abcdef0123456789abcdeg",  # 'g' is not hex
            " " + GOOD_MD5,
            GOOD_MD5 + "\n",
            12345,
            ["x"],
            {"md5": GOOD_MD5},
        ],
        ids=[
            "null",
            "empty",
            "too-short",
            "31-chars",
            "33-chars",
            "uppercase",
            "non-hex",
            "leading-space",
            "trailing-newline",
            "int",
            "list",
            "dict",
        ],
    )
    def test_unusable_md5_values(self, md5):
        assert has_usable_checksum(_record(file_md5sum=md5)) is False

    def test_absent_key_is_unusable(self):
        record = _record()
        del record["file_md5sum"]
        assert has_usable_checksum(record) is False

    @pytest.mark.parametrize("record", ["a bare string", None, 42, ["a", "list"]])
    def test_non_dict_record_is_unusable(self, record):
        """A non-dict cannot carry a checksum — and the catch-all classifier reads
        records with .get, so letting one through would crash rather than classify."""
        assert has_usable_checksum(record) is False


class TestPartitionRecords:
    def test_splits_and_preserves_order(self):
        good_a = _record(file_name="a.bam", file_md5sum="a" * 32)
        bad = _record(file_name="b.bam", file_md5sum=None)
        good_b = _record(file_name="c.bam", file_md5sum="c" * 32)

        classifiable, excluded = partition_records([good_a, bad, good_b])

        assert classifiable == [good_a, good_b]
        assert [e.file_name for e in excluded] == ["b.bam"]

    def test_classifiable_records_are_the_original_objects(self):
        """The kept side is handed straight to the producers, so it must not be copies."""
        record = _record()
        classifiable, _ = partition_records([record])
        assert classifiable[0] is record

    def test_empty_input_yields_two_empty_lists(self):
        assert partition_records([]) == ([], [])

    def test_nothing_excluded_when_every_record_is_well_formed(self):
        records = [_record(file_md5sum=c * 32) for c in "abcdef"]
        classifiable, excluded = partition_records(records)
        assert classifiable == records
        assert excluded == []


class TestExcludedFile:
    def test_carries_every_identity_field_the_record_has(self):
        excluded = ExcludedFile.from_record(_record(file_md5sum=None))
        assert excluded.file_name == "sample.bam"
        assert excluded.dataset_title == "Study A"
        assert excluded.entry_id == "e1"
        assert excluded.file_id == "f1"
        assert excluded.drs_uri == "drs://example/f1"
        assert excluded.file_size == 100
        assert excluded.reason == NO_CHECKSUM_REASON

    def test_absent_identity_fields_stay_none(self):
        """None means "the record had no such field", which an empty string would hide."""
        excluded = ExcludedFile.from_record({"file_name": "x.bam"})
        assert excluded.entry_id is None
        assert excluded.file_id is None
        assert excluded.drs_uri is None
        assert excluded.dataset_title is None
        assert excluded.file_size is None

    def test_non_dict_record_yields_an_empty_identity(self):
        excluded = ExcludedFile.from_record("a bare string")
        assert excluded.file_name == ""
        assert excluded.entry_id is None
        assert excluded.reason == NO_CHECKSUM_REASON

    def test_drifted_file_name_is_stringified(self):
        assert ExcludedFile.from_record({"file_name": 7}).file_name == "7"

    def test_to_dict_emits_every_field_in_declaration_order(self):
        keys = list(ExcludedFile.from_record(_record()).to_dict())
        assert keys == ["file_name", "dataset_title", "entry_id", "file_id", "drs_uri", "file_size", "reason"]

    def test_round_trips_through_to_dict_and_from_dict(self):
        original = ExcludedFile.from_record(_record(file_md5sum=None))
        assert ExcludedFile.from_dict(original.to_dict()) == original

    def test_from_dict_defaults_missing_keys(self):
        rebuilt = ExcludedFile.from_dict({"file_name": "x.bam"})
        assert rebuilt.file_name == "x.bam"
        assert rebuilt.entry_id is None
        assert rebuilt.reason == NO_CHECKSUM_REASON


class TestWriteAndReadExcluded:
    def test_writes_the_count_in_the_metadata_block(self, tmp_path):
        _, excluded = partition_records([_record(file_md5sum=None), _record()])
        write_excluded(tmp_path, excluded, total_input=2)

        payload = json.loads((tmp_path / EXCLUDED_FILE).read_text())
        assert payload["metadata"] == {"total_input": 2, "excluded": 1, "complete": True}
        assert len(payload["excluded"]) == 1

    def test_written_even_when_nothing_was_excluded(self, tmp_path):
        """The file's presence is what distinguishes "excluded nothing" from a run that
        predates the exclusion — so an empty run still writes it."""
        write_excluded(tmp_path, [], total_input=17)

        index = read_excluded(tmp_path)
        assert index.present is True
        assert index.files == []
        assert index.total_input == 17

    def test_absent_file_reads_as_not_present(self, tmp_path):
        index = read_excluded(tmp_path)
        assert index.present is False
        assert index.files == []

    def test_round_trips_the_excluded_files(self, tmp_path):
        _, excluded = partition_records([_record(file_name="x.bam", file_md5sum=""), "garbage"])
        write_excluded(tmp_path, excluded, total_input=2)

        index = read_excluded(tmp_path)
        assert index.present is True
        assert [f.file_name for f in index.files] == ["x.bam", ""]

    @pytest.mark.parametrize("payload", [{"excluded": None}, {"excluded": "oops"}, {}, [1, 2, 3]])
    def test_malformed_file_yields_no_files_rather_than_raising(self, tmp_path, payload):
        """This is a report input, not a contract gate: a malformed file must not stop
        the report that would have shown it."""
        (tmp_path / EXCLUDED_FILE).write_text(json.dumps(payload))
        index = read_excluded(tmp_path)
        assert index.files == []
        assert index.present is True

    @pytest.mark.parametrize(
        "text",
        ['{"excluded": [{"file_name": "x.bam"}', "", "not json at all"],
        ids=["truncated", "empty", "garbage"],
    )
    def test_unparseable_file_yields_no_files_rather_than_raising(self, tmp_path, text):
        """write_excluded replaces the file atomically, so a torn write is not the source
        here — a hand-edited or externally truncated file is. Either way `make
        all-reports` must still run rather than die on it."""
        (tmp_path / EXCLUDED_FILE).write_text(text)
        index = read_excluded(tmp_path)
        assert index.files == []
        assert index.present is True

    def test_non_dict_rows_are_skipped(self, tmp_path):
        (tmp_path / EXCLUDED_FILE).write_text(json.dumps({"excluded": ["nope", 1, {"file_name": "ok.bam"}]}))
        assert [f.file_name for f in read_excluded(tmp_path).files] == ["ok.bam"]


def test_exclusions_file_is_not_a_classification_file():
    """A reader of CLASSIFICATION_FILES must never treat an excluded file as a
    classification — it is the opposite of one (#376, AC2)."""
    assert EXCLUDED_FILE not in CLASSIFICATION_FILES
