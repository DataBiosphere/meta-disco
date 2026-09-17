"""The catch-all producer decides what to skip by identity, not by filename (#438).

A name identifies a file only about 60% of the time in this corpus — 708,088 records
under 442,865 distinct names — so a name-keyed skip set drops a file because a
*different* file elsewhere happens to share its name. That file then appears in no
``classifications`` array at all, which is the counted-and-dropped shape #376 exists
to prevent.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from classify_remaining_files import classify_remaining, load_already_classified

from tests.metadata_fixtures import write_metadata


def _record(name: str, entry_id: str, md5: str, dataset_id: str) -> dict:
    return {
        "file_name": name,
        "file_format": ".weird",
        "file_md5sum": md5,
        "dataset_id": dataset_id,
        "dataset_title": dataset_id,
        "entry_id": entry_id,
    }


class TestSkipKey:
    def test_the_set_holds_entry_ids(self, tmp_path):
        """What a producer contributes to the skip set is its records' identities."""
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"classifications": [{"entry_id": "e1", "file_name": "shared.weird"}]}))
        assert load_already_classified([other]) == {"e1"}

    def test_a_name_shared_with_another_dataset_does_not_strand_a_file(self, tmp_path):
        """The bug this replaces: two files, one name, only one already classified.

        `e1` in ds1 has a record from another producer. `e2` in ds2 is a different file
        that happens to carry the same name and has no record anywhere. Keyed on the
        name, `e2` was skipped here too and ended up in no output at all; keyed on
        identity, it is classified like any other unhandled file.
        """
        metadata_file = tmp_path / "metadata.json"
        write_metadata(
            metadata_file,
            [
                _record("shared.weird", "e1", "11111111111111111111111111111111", "ds1"),
                _record("shared.weird", "e2", "22222222222222222222222222222222", "ds2"),
            ],
        )
        other = tmp_path / "other.json"
        other.write_text(
            json.dumps({"classifications": [{"entry_id": "e1", "file_name": "shared.weird", "md5sum": "1" * 32}]})
        )
        output_file = tmp_path / "remaining.json"
        classify_remaining(metadata_file, output_file, [other])

        with output_file.open() as f:
            output = json.load(f)
        entries = {r["entry_id"] for r in output["classifications"]}
        assert entries == {"e2"}, "the unclassified file must get a record; its twin must not get a second"

    def test_a_file_already_classified_is_still_skipped(self, tmp_path):
        """The guard still does its job — no file gets two records."""
        metadata_file = tmp_path / "metadata.json"
        write_metadata(metadata_file, [_record("only.weird", "e1", "11111111111111111111111111111111", "ds1")])
        other = tmp_path / "other.json"
        other.write_text(json.dumps({"classifications": [{"entry_id": "e1", "file_name": "only.weird"}]}))
        output_file = tmp_path / "remaining.json"
        classify_remaining(metadata_file, output_file, [other])

        with output_file.open() as f:
            output = json.load(f)
        assert output["classifications"] == []
