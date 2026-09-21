"""A completed run holds one row per file, and says so before its reports are read.

Two producers claiming the same file is silent in the output — the run just carries an
extra row — so every count taken over it double-counts and no identifier is a primary
key (#445). The check turns that into a failed run.
"""

import json

from meta_disco.classify_run import _check_one_row_per_file
from meta_disco.output_utils import CLASSIFICATION_FILES, row_identities
from meta_disco.pipeline import SOURCE_RECORD_KEYS

ANVIL_KEY = SOURCE_RECORD_KEYS["anvil"]
HPRC_KEY = SOURCE_RECORD_KEYS["hprc"]
FILE_ID = ANVIL_KEY.output_field


def _write(run_dir, fname, rows):
    """One classification file in the envelope every producer writes."""
    (run_dir / fname).write_text(json.dumps({"metadata": {}, "classifications": rows}))


def _row(file_id):
    return {"file_name": "sample.bam", "file_id": file_id, "entry_id": f"e-{file_id}"}


class TestRowIdentities:
    def test_a_file_id_in_two_producers_outputs_is_a_duplicate(self, tmp_path):
        _write(tmp_path, "tar_classifications.json", [_row("f1"), _row("f2")])
        _write(tmp_path, "auxiliary_classifications.json", [_row("f1")])

        identities = row_identities(tmp_path, FILE_ID)
        assert identities.total_rows == 3
        # Named in CLASSIFICATION_FILES order. Derived rather than spelled, so this pins
        # that property rather than where these two producers happen to sit.
        both = {"tar_classifications.json", "auxiliary_classifications.json"}
        assert identities.duplicates == {"f1": [f for f in CLASSIFICATION_FILES if f in both]}

    def test_a_file_id_written_twice_by_one_producer_is_a_duplicate_too(self, tmp_path):
        _write(tmp_path, "bam_classifications.json", [_row("f1"), _row("f1")])

        assert row_identities(tmp_path, FILE_ID).duplicates == {
            "f1": ["bam_classifications.json", "bam_classifications.json"]
        }

    def test_distinct_file_ids_are_no_duplicates(self, tmp_path):
        _write(tmp_path, "bam_classifications.json", [_row("f1"), _row("f2")])
        _write(tmp_path, "vcf_classifications.json", [_row("f3")])

        identities = row_identities(tmp_path, FILE_ID)
        assert identities.total_rows == 3
        assert identities.duplicates == {}
        assert identities.without_key == 0

    def test_rows_with_no_file_id_are_counted_not_paired(self, tmp_path):
        """Rows that carry no identity cannot be compared for uniqueness at all."""
        _write(tmp_path, "bam_classifications.json", [_row(None), _row(""), _row("f1")])

        identities = row_identities(tmp_path, FILE_ID)
        assert identities.without_key == 2
        assert identities.duplicates == {}

    def test_the_scan_keys_on_the_field_it_is_told(self, tmp_path):
        """An HPRC row carries no `file_id`; its identity is the URL hash written as
        `md5sum` (#446), and a repeat of that is a duplicate under that key."""
        hprc_row = {"file_name": "HG002.bam", "file_id": None, "entry_id": None, "md5sum": "a" * 32}
        _write(tmp_path, "bam_classifications.json", [hprc_row, dict(hprc_row, file_name="HG003.bam")])

        by_md5 = row_identities(tmp_path, HPRC_KEY.output_field)
        assert by_md5.without_key == 0
        assert by_md5.duplicates == {"a" * 32: ["bam_classifications.json", "bam_classifications.json"]}


class TestTheRunFailsOnDuplicates:
    def test_a_duplicate_fails_the_run_and_names_it(self, tmp_path, capsys):
        _write(tmp_path, "tar_classifications.json", [_row("f1")])
        _write(tmp_path, "auxiliary_classifications.json", [_row("f1")])

        assert _check_one_row_per_file(tmp_path, ANVIL_KEY) is False
        out = capsys.readouterr().out
        assert "f1" in out
        assert "tar_classifications.json" in out
        assert "auxiliary_classifications.json" in out

    def test_one_row_per_file_passes(self, tmp_path, capsys):
        _write(tmp_path, "bam_classifications.json", [_row("f1"), _row("f2")])

        assert _check_one_row_per_file(tmp_path, ANVIL_KEY) is True
        assert "2 rows" in capsys.readouterr().out

    def test_rows_without_a_file_id_do_not_fail_the_run(self, tmp_path, capsys):
        """And are not reported as one row per file: nothing was checkable."""
        _write(tmp_path, "bam_classifications.json", [_row(None), _row(None)])

        assert _check_one_row_per_file(tmp_path, ANVIL_KEY) is True
        out = capsys.readouterr().out
        assert "no file_id" in out
        assert "One row per file" not in out

    def test_an_hprc_run_is_checked_on_its_own_key(self, tmp_path, capsys):
        """Before #446 an HPRC run reported "not checked": every row lacks a `file_id`.
        Keyed on the field its source guarantees unique, the same rows are checked."""
        rows = [{"file_name": n, "file_id": None, "md5sum": m} for n, m in (("a.bam", "a" * 32), ("b.bam", "b" * 32))]
        _write(tmp_path, "bam_classifications.json", rows)

        assert _check_one_row_per_file(tmp_path, HPRC_KEY) is True
        out = capsys.readouterr().out
        assert "One row per file: 2 rows, no repeated md5sum" in out
        assert "not checked" not in out

        _write(tmp_path, "tar_classifications.json", [rows[0]])
        assert _check_one_row_per_file(tmp_path, HPRC_KEY) is False
        assert "a" * 32 in capsys.readouterr().out
