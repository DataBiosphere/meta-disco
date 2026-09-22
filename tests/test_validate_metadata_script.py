"""Tests for the standalone metadata-validation gate (scripts/validate_metadata.py)."""

import json

import pytest
import validate_metadata

from meta_disco.pipeline import load_records
from tests.metadata_fixtures import valid_record as _valid


def _write(path, records, key="files", metadata=None):
    envelope = {"repository": "anvil"} if metadata is None else metadata
    path.write_text(json.dumps({"metadata": envelope, key: records}))
    return path


class TestLoadRecords:
    """The loader the gate reads through (`pipeline.load_snapshot` is its envelope half)."""

    def test_reads_files_envelope(self, tmp_path):
        path = _write(tmp_path / "m.json", [_valid()], key="files")
        assert len(load_records(path)) == 1

    def test_reads_legacy_results_envelope(self, tmp_path):
        path = _write(tmp_path / "m.json", [_valid()], key="results")
        assert len(load_records(path)) == 1

    def test_reads_ndjson(self, tmp_path):
        path = tmp_path / "m.ndjson"
        path.write_text("\n".join(json.dumps(_valid()) for _ in range(3)))
        assert len(load_records(path)) == 3

    def test_empty_results_list_is_returned_not_treated_as_missing(self, tmp_path):
        # A present-but-empty results list is a valid empty corpus, not a missing key.
        path = _write(tmp_path / "m.json", [], key="results")
        assert load_records(path) == []

    def test_missing_both_keys_raises_value_error(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"metadata": {}}))
        with pytest.raises(ValueError):
            load_records(path)

    def test_non_dict_top_level_raises_type_error(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(json.dumps([1, 2, 3]))
        with pytest.raises(TypeError):
            load_records(path)

    @pytest.mark.parametrize("payload", [{"results": None}, {"files": "oops"}, {"files": {}}])
    def test_non_list_records_value_raises_type_error(self, tmp_path, payload):
        path = tmp_path / "m.json"
        path.write_text(json.dumps(payload))
        with pytest.raises(TypeError):
            load_records(path)


class TestGateExit:
    def test_clean_corpus_exits_zero(self, tmp_path, capsys):
        path = _write(tmp_path / "m.json", [_valid(), _valid(entry_id="e2", file_id="f2")])
        rc = validate_metadata.main(["-i", str(path)])
        assert rc == 0
        assert "OK — no problems." in capsys.readouterr().out

    def test_bad_corpus_exits_one_and_prints_grouped_summary(self, tmp_path, capsys):
        records = [_valid(), _valid(entry_id="e2", file_id="f2", file_size="oops")]
        path = _write(tmp_path / "m.json", records)
        rc = validate_metadata.main(["-i", str(path)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "file_size: expected an integer" in out

    def test_ndjson_corpus_fails_the_gate_for_want_of_an_envelope(self, tmp_path, capsys):
        """The records validate, but an `.ndjson` file names no repository, so a run
        could not resolve its record key from it (#446) — the gate says so."""
        path = tmp_path / "m.ndjson"
        path.write_text("\n".join(json.dumps(_valid(entry_id=f"e{i}", file_id=f"f{i}")) for i in range(2)))
        rc = validate_metadata.main(["-i", str(path)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "OK — no problems." in out, "the record contract itself passed"
        assert "repository None, which declares no record key" in out

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


class TestChecksumGate:
    """AC4: `make classify` now depends on this gate, and the gate must fail on an
    unusable checksum, naming the offending records — otherwise the long run starts on a
    corpus that will shed files (#376)."""

    @pytest.mark.parametrize(
        "md5",
        [None, "", "abc123", "A" * 32],
        ids=["null", "empty", "malformed", "uppercase"],
    )
    def test_unusable_checksum_fails_the_gate(self, tmp_path, capsys, md5):
        path = _write(tmp_path / "m.json", [_valid(), _valid(entry_id="e2", file_id="f2", file_md5sum=md5)])
        assert validate_metadata.main(["-i", str(path)]) == 1
        out = capsys.readouterr().out
        assert "file_md5sum" in out
        assert "f2" in out  # the offending record is named, by file_id

    def test_a_corpus_of_well_formed_checksums_passes(self, tmp_path, capsys):
        path = _write(tmp_path / "m.json", [_valid(), _valid(entry_id="e2", file_id="f2", file_md5sum="b" * 32)])
        assert validate_metadata.main(["-i", str(path)]) == 0
        assert "OK — no problems." in capsys.readouterr().out


class TestEnvelopeGate:
    """What a run needs of its input beyond the records (#446): an envelope naming a
    repository with a declared record key, and that key unique across the records."""

    def test_an_envelope_naming_no_repository_fails(self, tmp_path, capsys):
        path = _write(tmp_path / "m.json", [_valid()], metadata={"catalog": "anvil15"})
        assert validate_metadata.main(["-i", str(path)]) == 1
        assert "declares no record key" in capsys.readouterr().out

    def test_an_unknown_repository_fails(self, tmp_path, capsys):
        path = _write(tmp_path / "m.json", [_valid()], metadata={"repository": "gtex"})
        assert validate_metadata.main(["-i", str(path)]) == 1
        assert "'gtex', which declares no record key" in capsys.readouterr().out

    def test_a_repeated_key_fails_naming_the_value(self, tmp_path, capsys):
        """Two records with one `file_id` would be one file with two rows in the run —
        the failure the post-run check (#445) reports hours in, caught here first."""
        records = [_valid(), _valid(entry_id="e2", file_md5sum="b" * 32), _valid(entry_id="e3", file_id="f3")]
        path = _write(tmp_path / "m.json", records)
        assert validate_metadata.main(["-i", str(path)]) == 1
        out = capsys.readouterr().out
        assert "1 value(s) of file_id are carried by more than one record" in out
        assert "f1 (x2)" in out

    def test_a_null_key_is_the_record_contracts_to_report_not_a_repeat(self, tmp_path, capsys):
        """Two records with no `file_id` are two contract violations, not one repeated
        value; the uniqueness check counts only usable strings."""
        records = [_valid(file_id=None), _valid(entry_id="e2", file_id=None)]
        path = _write(tmp_path / "m.json", records)
        assert validate_metadata.main(["-i", str(path)]) == 1
        out = capsys.readouterr().out
        assert "file_id" in out
        assert "more than one record" not in out
