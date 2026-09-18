"""Every producer carries the identity that outlives a catalog (#433).

A sweep for the same reason `TestEveryProducerCarriesPublishedValues` is: a run has
three record shapes (#429), so a field wired into `ClassifyPipeline` alone reaches some
outputs and not others, and the gap is a silently absent key rather than an error.
`tests/producer_sweep` holds the half the two sweeps share.
"""

import pytest

from meta_disco.records import ClassifierRecord, InvalidRecord, OutputRecord
from tests.metadata_fixtures import valid_record
from tests.producer_sweep import STANDALONE_PRODUCERS, run_index_producer, run_producer

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


class TestEveryStandaloneProducerCarriesIt:
    """The four that assemble records by hand.

    `ClassifyPipeline` is not swept here: `TestBothStreamsCarryIt` pins its record
    construction in isolation, and the golden fixture (`test_output_shape.RECORD_KEYS`
    and `expected_output.json`) covers it end to end from a real run.
    """

    @pytest.mark.parametrize("producer,name,fmt", STANDALONE_PRODUCERS)
    def test_a_standalone_producer_carries_both(self, tmp_path, producer, name, fmt):
        rows = run_producer(producer, tmp_path, [_record(name, fmt)])
        assert _identities(rows) == [(FILE_ID, DRS_URI)]

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
