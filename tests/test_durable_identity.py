"""Every producer carries the identity that outlives a catalog (#433).

That the fields are *present* is structural since #450 — every producer builds
`OutputRecord`, and `test_output_shape` pins its key set. What is left here is whose
identity a record carries where a producer has two in hand.
"""

import pytest

from meta_disco.records import ClassifierRecord, InvalidRecord, OutputRecord
from tests.metadata_fixtures import valid_record
from tests.producer_sweep import run_index_producer

FILE_ID = "file-id-1"
# Deliberately not `drs://drs.anv0:v2_<FILE_ID>`, so this fails if anyone derives it.
DRS_URI = "drs://drs.anv0:v2_a-different-object"


def _record(name: str, fmt: str) -> dict:
    return valid_record(
        file_name=name,
        file_format=fmt,
        file_md5sum="a" * 32,
        file_size=10,
        file_id=FILE_ID,
        drs_uri=DRS_URI,
        dataset_id="ds1",
        dataset_title="AnVIL_IGVF_Mouse_R1",
    )


def _identities(rows: list[dict]) -> list[tuple]:
    return [(r.get("file_id"), r.get("drs_uri")) for r in rows]


class TestBothStreamsCarryIt:
    def test_the_valid_stream_carries_both(self):
        item = ClassifierRecord.from_record(_record("s.bam", ".bam"))
        assert (item.file_id, item.drs_uri) == (FILE_ID, DRS_URI)

    def test_the_invalid_stream_carries_both(self):
        """A record failing the contract on another field still has an identity to echo."""
        bad = _record("s.bam", ".bam") | {"file_size": "not a number"}
        item = InvalidRecord.from_record(bad, ["file_size is not an integer"])
        assert (item.file_id, item.drs_uri) == (FILE_ID, DRS_URI)

    def test_the_envelope_carries_both(self):
        item = ClassifierRecord.from_record(_record("s.bam", ".bam"))
        row = OutputRecord.from_work_item(item, {}).to_dict()
        assert (row["file_id"], row["drs_uri"]) == (FILE_ID, DRS_URI)

    def test_the_single_file_path_has_neither_and_says_so(self):
        """`classify_single` has no input record, so both are None rather than absent."""
        row = OutputRecord.from_single(
            md5sum="c" * 32, file_name="x", file_size=1, file_format=".test", classifications={}
        ).to_dict()
        assert row["file_id"] is None and row["drs_uri"] is None


class TestTheIndexProducerCarriesTheRightIdentity:
    """That the fields are present is structural now (#450) — every producer builds
    `OutputRecord` and `test_output_shape` pins its key set. What is left here is whose
    identity a record carries where a producer has two in hand, and the one array that
    is not an `OutputRecord`.
    """

    @pytest.mark.parametrize("with_parent", [True, False], ids=["matched", "declined"])
    def test_the_index_producer_carries_the_index_files_own_identity(self, tmp_path, with_parent):
        """Not the parent's — the index file is the row, and it resolves to its own bytes.

        Both of this producer's record-building sites: `inherited_evidence` when a parent
        is found, and `declined_record` when none is (#438).
        """
        parent = valid_record(
            file_name="sample.bam",
            file_format=".bam",
            file_md5sum="b" * 32,
            file_id="parent-file-id",
            drs_uri="drs://drs.anv0:v2_parent",
            dataset_id="ds1",
        )
        records = ([parent] if with_parent else []) + [_record("sample.bam.bai", ".bai")]
        envelope = run_index_producer(tmp_path, records)
        assert _identities(envelope["classifications"]) == [(FILE_ID, DRS_URI)]

    def test_an_unmatched_files_entry_carries_both(self, tmp_path):
        """The diagnostic array is how a declined file is chased down, so it needs them too."""
        envelope = run_index_producer(tmp_path, [_record("orphan.bam.bai", ".bai")])
        assert _identities(envelope["unmatched_files"]) == [(FILE_ID, DRS_URI)]
