"""Tests for the standalone metadata-validation gate (scripts/validate_metadata.py)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import validate_metadata  # noqa: E402

from tests.metadata_fixtures import valid_record as _valid  # noqa: E402


def _write(path, records, key="files"):
    path.write_text(json.dumps({"metadata": {}, key: records}))
    return path


class TestLoadRecords:
    def test_reads_files_envelope(self, tmp_path):
        path = _write(tmp_path / "m.json", [_valid()], key="files")
        assert len(validate_metadata.load_records(path)) == 1

    def test_reads_legacy_results_envelope(self, tmp_path):
        path = _write(tmp_path / "m.json", [_valid()], key="results")
        assert len(validate_metadata.load_records(path)) == 1

    def test_reads_ndjson(self, tmp_path):
        path = tmp_path / "m.ndjson"
        path.write_text("\n".join(json.dumps(_valid()) for _ in range(3)))
        assert len(validate_metadata.load_records(path)) == 3

    def test_empty_results_list_is_returned_not_treated_as_missing(self, tmp_path):
        # A present-but-empty results list is a valid empty corpus, not a missing key.
        path = _write(tmp_path / "m.json", [], key="results")
        assert validate_metadata.load_records(path) == []

    def test_missing_both_keys_raises_value_error(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"metadata": {}}))
        with pytest.raises(ValueError):
            validate_metadata.load_records(path)

    def test_non_dict_top_level_raises_type_error(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(json.dumps([1, 2, 3]))
        with pytest.raises(TypeError):
            validate_metadata.load_records(path)

    @pytest.mark.parametrize("payload", [{"results": None}, {"files": "oops"}, {"files": {}}])
    def test_non_list_records_value_raises_type_error(self, tmp_path, payload):
        path = tmp_path / "m.json"
        path.write_text(json.dumps(payload))
        with pytest.raises(TypeError):
            validate_metadata.load_records(path)


class TestGateExit:
    def test_clean_corpus_exits_zero(self, tmp_path, capsys):
        path = _write(tmp_path / "m.json", [_valid(), _valid(entry_id="e2")])
        rc = validate_metadata.main(["-i", str(path)])
        assert rc == 0
        assert "OK — no problems." in capsys.readouterr().out

    def test_bad_corpus_exits_one_and_prints_grouped_summary(self, tmp_path, capsys):
        records = [_valid(), _valid(entry_id="e2", file_size="oops")]
        path = _write(tmp_path / "m.json", records)
        rc = validate_metadata.main(["-i", str(path)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "file_size: expected an integer" in out

    def test_ndjson_corpus_is_validated_through_main(self, tmp_path, capsys):
        path = tmp_path / "m.ndjson"
        path.write_text("\n".join(json.dumps(_valid(entry_id=f"e{i}")) for i in range(2)))
        rc = validate_metadata.main(["-i", str(path)])
        assert rc == 0
        assert "OK — no problems." in capsys.readouterr().out

    def test_malformed_json_exits_one_without_traceback(self, tmp_path, capsys):
        path = tmp_path / "m.json"
        path.write_text("{ not valid json")
        rc = validate_metadata.main(["-i", str(path)])
        assert rc == 1
        assert "Could not read" in capsys.readouterr().out

    def test_io_error_exits_one_without_traceback(self, tmp_path, capsys):
        # A path that exists but can't be read as a file (here, a directory) raises
        # OSError from open(); the gate must report it, not crash.
        path = tmp_path / "a_directory"
        path.mkdir()
        rc = validate_metadata.main(["-i", str(path)])
        assert rc == 1
        assert "Could not read" in capsys.readouterr().out

    def test_empty_corpus_exits_one(self, tmp_path, capsys):
        # An empty-but-valid download is almost always a failed download; the gate
        # must not green-light a multi-hour classify over zero records.
        path = _write(tmp_path / "m.json", [])
        rc = validate_metadata.main(["-i", str(path)])
        assert rc == 1
        assert "No records found" in capsys.readouterr().out

    def test_missing_input_exits_two(self, tmp_path, capsys):
        rc = validate_metadata.main(["-i", str(tmp_path / "nope.json")])
        assert rc == 2
        assert "not found" in capsys.readouterr().out
