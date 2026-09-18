"""Every producer carries the identity that outlives a catalog (#433).

A sweep for the same reason `TestEveryProducerCarriesPublishedValues` is: a run has
three record shapes (#429), so a field wired into `ClassifyPipeline` alone reaches some
outputs and not others, and the gap is a silently absent key rather than an error.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from meta_disco.records import ClassifierRecord, InvalidRecord, OutputRecord
from tests.metadata_fixtures import valid_record

FILE_ID = "c01810fe-a41b-c20e-69f0-8ac565a309f6"
# Deliberately not `drs://drs.anv0:v2_<FILE_ID>`, so this fails if anyone derives it.
DRS_URI = "drs://drs.anv0:v2_0f41f5b3-7608-362c-9015-0e29ad6f6440"


def _record(name: str, fmt: str) -> dict:
    return valid_record(
        file_name=name,
        file_format=fmt,
        file_md5sum="a" * 32,
        file_size=10,
        entry_id="e1",
        file_id=FILE_ID,
        drs_uri=DRS_URI,
        dataset_id="ds1",
        dataset_title="AnVIL_IGVF_Mouse_R1",
    )


def _metadata(tmp_path: pathlib.Path, records: list[dict]) -> pathlib.Path:
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": records}))
    return path


def _identities(output_path: pathlib.Path) -> list[tuple]:
    rows = json.loads(output_path.read_text())["classifications"]
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
    """The four that assemble records by hand. `ClassifyPipeline` is covered above."""

    @pytest.mark.parametrize(
        "producer,name,fmt",
        [
            ("classify_images", "slide.svs", ".svs"),
            ("classify_auxiliary_genomic", "cohort.pvar", ".pvar"),
            ("classify_remaining", "mystery.xyz", ".xyz"),
        ],
    )
    def test_a_standalone_producer_carries_both(self, tmp_path, producer, name, fmt):
        from classify_auxiliary_genomic import classify_auxiliary_genomic
        from classify_images import classify_images
        from classify_remaining_files import classify_remaining

        funcs = {
            "classify_images": classify_images,
            "classify_auxiliary_genomic": classify_auxiliary_genomic,
            "classify_remaining": lambda m, o: classify_remaining(m, o, []),
        }
        output = tmp_path / "out_classifications.json"
        funcs[producer](_metadata(tmp_path, [_record(name, fmt)]), output)
        assert _identities(output) == [(FILE_ID, DRS_URI)], f"{producer} dropped the durable identity"

    def test_the_index_producer_carries_the_index_files_own_identity(self, tmp_path):
        """Not the parent's — the index file is the row, and it resolves to its own bytes."""
        from classify_index_files import propagate_to_index_files

        parent = valid_record(
            file_name="sample.bam",
            file_format=".bam",
            file_md5sum="b" * 32,
            entry_id="p1",
            file_id="parent-file-id",
            drs_uri="drs://drs.anv0:v2_parent",
            dataset_id="ds1",
        )
        metadata = _metadata(tmp_path, [parent, _record("sample.bam.bai", ".bai")])
        parents = tmp_path / "bam_classifications.json"
        parents.write_text(json.dumps({"classifications": []}))
        output = tmp_path / "index_classifications.json"
        propagate_to_index_files(metadata, [parents], output)

        assert _identities(output) == [(FILE_ID, DRS_URI)]

    def test_the_index_producer_carries_it_on_a_declined_record(self, tmp_path):
        """A file with no parent to inherit from still resolves to its own bytes (#438)."""
        from classify_index_files import propagate_to_index_files

        metadata = _metadata(tmp_path, [_record("orphan.bam.bai", ".bai")])
        parents = tmp_path / "bam_classifications.json"
        parents.write_text(json.dumps({"classifications": []}))
        output = tmp_path / "index_classifications.json"
        propagate_to_index_files(metadata, [parents], output)

        assert _identities(output) == [(FILE_ID, DRS_URI)]
