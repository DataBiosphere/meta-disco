"""The catch-all producer decides what to skip by identity, not by filename (#438).

A name identifies a file only about 60% of the time in the AnVIL corpus — 708,088
records under 442,865 distinct names — so a name-keyed skip set drops a file because a
*different* file elsewhere happens to share its name. That file then appears in no
``classifications`` array at all, which is the counted-and-dropped shape #376 exists to
prevent.

Which field is the identity is the source's to say (``pipeline.SOURCE_RECORD_KEYS``, #446):
``file_id`` for AnVIL, the URL hash written as the checksum for HPRC. The producer reads
it off the input envelope and refuses an envelope that names no repository.
"""

import json
from pathlib import Path

import pytest
from classify_hprc_files import build_metadata_records
from classify_remaining_files import classify_remaining, load_already_classified

from meta_disco.models import NOT_CLASSIFIED
from meta_disco.pipeline import SOURCE_RECORD_KEYS
from tests.metadata_fixtures import valid_record, write_metadata

ANVIL_KEY = SOURCE_RECORD_KEYS["anvil"]
HPRC_KEY = SOURCE_RECORD_KEYS["hprc"]


def _record(name: str, file_id: str, md5: str, dataset_id: str) -> dict:
    return {
        "file_name": name,
        "file_format": ".weird",
        "file_md5sum": md5,
        "dataset_id": dataset_id,
        "dataset_title": dataset_id,
        "entry_id": f"entry-{file_id}",
        "file_id": file_id,
    }


def _hprc_records(*names: str) -> list[dict]:
    """Records as the HPRC builder emits them: no catalog identity, a URL-hash checksum."""
    rows = [{"filename": n, "loc": f"s3://bucket/{n}", "fileSize": 1} for n in names]
    return build_metadata_records(rows, "loc", workers=1)


def _rows(path: Path):
    with path.open() as f:
        return json.load(f)["classifications"]


class TestSkipKey:
    def test_the_set_holds_file_ids(self, tmp_path):
        """What a producer contributes to the skip set is its records' identities."""
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"classifications": [{"file_id": "f1", "file_name": "shared.weird"}]}))
        assert load_already_classified([other], ANVIL_KEY) == {"f1"}

    def test_a_name_shared_with_another_dataset_does_not_strand_a_file(self, tmp_path):
        """The bug this replaces: two files, one name, only one already classified.

        `f1` in ds1 has a record from another producer. `f2` in ds2 is a different file
        that happens to carry the same name and has no record anywhere. Keyed on the
        name, `f2` was skipped here too and ended up in no output at all; keyed on
        identity, it is classified like any other unhandled file.
        """
        metadata_file = tmp_path / "metadata.json"
        write_metadata(
            metadata_file,
            [
                _record("shared.weird", "f1", "11111111111111111111111111111111", "ds1"),
                _record("shared.weird", "f2", "22222222222222222222222222222222", "ds2"),
            ],
        )
        other = tmp_path / "other.json"
        other.write_text(
            json.dumps({"classifications": [{"file_id": "f1", "file_name": "shared.weird", "md5sum": "1" * 32}]})
        )
        output_file = tmp_path / "remaining.json"
        classify_remaining(metadata_file, output_file, [other])

        entries = {r["file_id"] for r in _rows(output_file)}
        assert entries == {"f2"}, "the unclassified file must get a record; its twin must not get a second"

    def test_a_file_already_classified_is_still_skipped(self, tmp_path):
        """The guard still does its job — no file gets two records."""
        metadata_file = tmp_path / "metadata.json"
        write_metadata(metadata_file, [_record("only.weird", "f1", "11111111111111111111111111111111", "ds1")])
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"classifications": [{"file_id": "f1", "file_name": "only.weird"}]}))
        output_file = tmp_path / "remaining.json"
        classify_remaining(metadata_file, output_file, [other])

        assert _rows(output_file) == []

    def test_a_row_with_no_file_id_is_refused(self, tmp_path):
        """A null `file_id` in a producer's output raises rather than being skipped.

        `file_id` is not classifier-relevant, so a drifted one reaches the valid stream
        and is echoed into a producer's row untouched — unlike `file_name`, the key this
        replaced. Skipping such a row would drop it from the set and give the file a
        second classification record. `make validate-metadata` rejects it upstream, so
        reaching here means that gate was bypassed, and the loud failure says so.
        """
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"classifications": [{"file_id": None, "file_name": "drifted.weird"}]}))
        with pytest.raises(ValueError, match="file_id"):
            load_already_classified([other], ANVIL_KEY)

    def test_an_empty_file_id_is_refused_too(self, tmp_path):
        """Empty string, not just null — both mean the identity is absent."""
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"classifications": [{"file_id": "", "file_name": "x.weird"}]}))
        with pytest.raises(ValueError, match="file_id"):
            load_already_classified([other], ANVIL_KEY)

    def test_an_input_record_with_no_file_id_is_refused(self, tmp_path):
        """The guard is symmetric: a drifted identity on the *input* side raises too.

        `load_already_classified` guards the records it reads; this guards the records
        it compares them against. A drifted `file_id` here matches nothing in the skip
        set, so an already-classified file would be classified a second time — the same
        failure, entering by the other side.
        """
        metadata_file = tmp_path / "metadata.json"
        write_metadata(metadata_file, [_record("x.weird", "f1", "1" * 32, "ds1")])
        # Drift it after the contract-shaped fixture is written, as a producer would see it.
        doc = json.loads(metadata_file.read_text())
        doc["files"][0]["file_id"] = None
        metadata_file.write_text(json.dumps(doc))

        with pytest.raises(ValueError, match="file_id"):
            classify_remaining(metadata_file, tmp_path / "out.json", [])


class TestARepeatedInputKeyIsRefused:
    """Two input records with one key would let one hide behind the other (#446).

    The earlier producer writes one; this producer skips both as already classified; the
    post-run scan sees one row and passes. `make validate-metadata` reports it first for
    `make classify`; a run started any other way is refused here, before a row is written.
    """

    def test_the_hidden_file_is_not_silently_skipped(self, tmp_path):
        metadata_file = tmp_path / "metadata.json"
        write_metadata(
            metadata_file,
            [
                _record("written.bam", "f1", "1" * 32, "ds1"),
                _record("hidden.weird", "f1", "2" * 32, "ds1"),
            ],
        )
        other = tmp_path / "bam_classifications.json"
        other.write_text(json.dumps({"classifications": [{"file_id": "f1", "file_name": "written.bam"}]}))

        with pytest.raises(
            ValueError, match=r"1 value\(s\) of file_id are carried by more than one input record.*f1 \(x2\)"
        ):
            classify_remaining(metadata_file, tmp_path / "out.json", [other])
        assert not (tmp_path / "out.json").exists(), "refused before a row was written"


class TestTheKeyIsTheSources:
    """An HPRC record has no `file_id`, `entry_id` or `drs_uri` — the catalogs issue none
    and none is minted (#446). Its identity is the URL hash the source writes as the
    checksum, which the output row spells `md5sum`."""

    def test_an_hprc_run_keys_on_the_url_hash(self, tmp_path):
        a, b = _hprc_records("a.weird", "b.weird")
        metadata_file = write_metadata(tmp_path / "metadata.json", [a, b], "hprc")
        other = tmp_path / "other.json"
        row = {"file_name": "a.weird", "file_id": None, "md5sum": a["file_md5sum"]}
        other.write_text(json.dumps({"classifications": [row]}))
        output_file = tmp_path / "remaining.json"

        classify_remaining(metadata_file, output_file, [other])

        [written] = _rows(output_file)
        assert written["md5sum"] == b["file_md5sum"], "the row another producer wrote is skipped on its hash"
        assert written["file_id"] is None and written["entry_id"] is None and written["drs_uri"] is None

    def test_a_legacy_results_envelope_is_read(self, tmp_path):
        """The record list may sit under the legacy `results` key, as the report readers
        allow (`output_utils._records_in`); both producers read it the same way."""
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"results": [{"file_name": "a.weird", "md5sum": "a" * 32}]}))
        assert load_already_classified([other], HPRC_KEY) == {"a" * 32}

    def test_the_set_is_read_under_the_output_spelling(self, tmp_path):
        """Input says `file_md5sum`, an output row says `md5sum`; the key carries both."""
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"classifications": [{"file_name": "a.weird", "md5sum": "a" * 32}]}))
        assert load_already_classified([other], HPRC_KEY) == {"a" * 32}

    def test_an_hprc_row_with_no_hash_is_refused(self, tmp_path):
        """The raise is the source's key's, not `file_id`'s: it names the field expected."""
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"classifications": [{"file_name": "a.weird", "md5sum": None}]}))
        with pytest.raises(ValueError, match="md5sum"):
            load_already_classified([other], HPRC_KEY)

    def test_an_envelope_naming_no_repository_is_refused_naming_the_file(self, tmp_path):
        """Without a repository there is no key to read, and guessing one is how a file
        gets a second row. The refusal names the input and the repositories known."""
        metadata_file = tmp_path / "metadata.json"
        metadata_file.write_text(json.dumps({"files": [_record("x.weird", "f1", "1" * 32, "ds1")]}))
        with pytest.raises(
            ValueError, match=r"metadata\.json.*repository None, which declares no record key.*'anvil', 'hprc'"
        ):
            classify_remaining(metadata_file, tmp_path / "out.json", [])

    def test_an_unknown_repository_is_refused(self, tmp_path):
        metadata_file = tmp_path / "metadata.json"
        write_metadata(metadata_file, [_record("x.weird", "f1", "1" * 32, "ds1")], repository="gtex")
        with pytest.raises(ValueError, match="'gtex', which declares no record key"):
            classify_remaining(metadata_file, tmp_path / "out.json", [])


class TestARecordWithNoNameIsWrittenNotDropped:
    """A nameless record violates the input contract and still gets a row (#155/#161).

    The catch-all used to skip it silently: no row anywhere in the run, and
    `unprocessable-report` — which finds such a file by scanning the output — could not
    see it. The pipeline has always written one; this producer now does too.
    """

    def _run(self, tmp_path, records):
        output = tmp_path / "remaining_classifications.json"
        metadata = tmp_path / "metadata.json"
        metadata.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": records}))
        classify_remaining(metadata, output, [])
        return json.loads(output.read_text())

    def test_it_is_written_as_validation_failed(self, tmp_path):
        envelope = self._run(tmp_path, [valid_record(file_name="", file_format=".xyz", file_id="f1")])
        [row] = envelope["classifications"]
        assert row["file_id"] == "f1"
        assert all(entry["status"] == NOT_CLASSIFIED for entry in row["classifications"].values())
        assert envelope["metadata"]["validation_failed"] == 1
        assert envelope["metadata"]["successful"] == 0

    def test_a_drifted_file_name_is_coerced_not_echoed(self, tmp_path):
        """`OutputRecord.file_name` is typed `str`, so a drifted one is coerced on the
        way in — the pipeline's `InvalidRecord` path does it, and this uses that path
        rather than echoing a raw value into a row that claims to be a string."""
        envelope = self._run(tmp_path, [valid_record(file_name=0, file_format=None, entry_id="e1")])
        [row] = envelope["classifications"]
        assert row["file_name"] == "0"
        assert row["file_format"] == ""

    def test_the_tallies_still_describe_the_rows(self, tmp_path):
        """`total` is the rows written and `processed` accounts for all of them, which is
        what lets the run's eleven metadata blocks sum to the corpus."""
        envelope = self._run(
            tmp_path,
            [
                valid_record(file_name="", file_format=".xyz", entry_id="e1", file_id="f1"),
                valid_record(file_name="mystery.xyz", file_format=".xyz", entry_id="e2", file_id="f2"),
            ],
        )
        meta = envelope["metadata"]
        assert len(envelope["classifications"]) == meta["total_to_process"] == meta["processed"] == 2
        assert meta["successful"] == 1 and meta["validation_failed"] == 1

    def test_a_nameless_record_another_producer_wrote_is_not_written_again(self, tmp_path):
        """The contract check runs after the already-written one, or a nameless record
        claimed on its `file_format` would get a second row."""
        output = tmp_path / "remaining_classifications.json"
        metadata = tmp_path / "metadata.json"
        record = valid_record(file_name="", file_format=".xyz", file_id="f1")
        metadata.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": [record]}))
        other = tmp_path / "bam_classifications.json"
        other.write_text(json.dumps({"classifications": [{"file_id": "f1", "file_name": ""}]}))

        classify_remaining(metadata, output, [other])
        assert json.loads(output.read_text())["classifications"] == []
