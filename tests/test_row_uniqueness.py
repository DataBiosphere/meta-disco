"""A completed run holds one row per file, and says so before its reports are read.

Two producers claiming the same file is silent in the output — the run just carries an
extra row — so every count taken over it double-counts and no identifier is a primary
key (#445). The check turns that into a failed run.
"""

import json

from meta_disco.classify_run import _check_one_row_per_file
from meta_disco.output_utils import CLASSIFICATION_FILES, row_identities


def _write(run_dir, fname, rows):
    """One classification file in the envelope every producer writes."""
    (run_dir / fname).write_text(json.dumps({"metadata": {}, "classifications": rows}))


def _row(file_id):
    return {"file_name": "sample.bam", "file_id": file_id, "entry_id": f"e-{file_id}"}


class TestRowIdentities:
    def test_a_file_id_in_two_producers_outputs_is_a_duplicate(self, tmp_path):
        _write(tmp_path, "tar_classifications.json", [_row("f1"), _row("f2")])
        _write(tmp_path, "auxiliary_classifications.json", [_row("f1")])

        identities = row_identities(tmp_path)
        assert identities.total_rows == 3
        # The two are named in CLASSIFICATION_FILES order, which is the producer
        # registry's order (#449). Derived rather than spelled, so this pins that
        # property rather than the positions these two producers happen to sit at.
        both = {"tar_classifications.json", "auxiliary_classifications.json"}
        assert identities.duplicates == {"f1": [f for f in CLASSIFICATION_FILES if f in both]}

    def test_a_file_id_written_twice_by_one_producer_is_a_duplicate_too(self, tmp_path):
        _write(tmp_path, "bam_classifications.json", [_row("f1"), _row("f1")])

        assert row_identities(tmp_path).duplicates == {"f1": ["bam_classifications.json", "bam_classifications.json"]}

    def test_distinct_file_ids_are_no_duplicates(self, tmp_path):
        _write(tmp_path, "bam_classifications.json", [_row("f1"), _row("f2")])
        _write(tmp_path, "vcf_classifications.json", [_row("f3")])

        identities = row_identities(tmp_path)
        assert identities.total_rows == 3
        assert identities.duplicates == {}
        assert identities.without_file_id == 0

    def test_rows_with_no_file_id_are_counted_not_paired(self, tmp_path):
        """A source whose catalog gives files no identity writes them that way, and
        rows that carry no identity cannot be compared for uniqueness at all."""
        _write(tmp_path, "bam_classifications.json", [_row(None), _row(""), _row("f1")])

        identities = row_identities(tmp_path)
        assert identities.without_file_id == 2
        assert identities.duplicates == {}


class TestTheRunFailsOnDuplicates:
    def test_a_duplicate_fails_the_run_and_names_it(self, tmp_path, capsys):
        _write(tmp_path, "tar_classifications.json", [_row("f1")])
        _write(tmp_path, "auxiliary_classifications.json", [_row("f1")])

        assert _check_one_row_per_file(tmp_path) is False
        out = capsys.readouterr().out
        assert "f1" in out
        assert "tar_classifications.json" in out
        assert "auxiliary_classifications.json" in out

    def test_one_row_per_file_passes(self, tmp_path, capsys):
        _write(tmp_path, "bam_classifications.json", [_row("f1"), _row("f2")])

        assert _check_one_row_per_file(tmp_path) is True
        assert "2 rows" in capsys.readouterr().out

    def test_rows_without_a_file_id_do_not_fail_the_run(self, tmp_path, capsys):
        """And are not reported as one row per file: nothing was checkable."""
        _write(tmp_path, "bam_classifications.json", [_row(None), _row(None)])

        assert _check_one_row_per_file(tmp_path) is True
        out = capsys.readouterr().out
        assert "no file_id" in out
        assert "One row per file" not in out
