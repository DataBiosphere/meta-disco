"""Every classification producer excludes checksum-less records (#376, AC1).

AC1 is a claim about *every* ``*_classifications.json``, not just the header pipeline's.
There are five producers, each loading the input metadata in its own process, and the
Phase 3 catch-all is the one that makes the claim non-trivial: it classifies every input
record no earlier producer named, so excluding only in the header pipeline would have
relocated a checksum-less file into ``remaining_classifications.json`` rather than kept
it out of the output.

The header pipeline's own exclusion is covered in ``test_pipeline.py``; this file pins
the four standalone scripts.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from classify_auxiliary_genomic import classify_auxiliary_genomic
from classify_images import classify_images
from classify_index_files import propagate_to_index_files
from classify_remaining_files import classify_remaining

GOOD_MD5 = "a" * 32


def _write_metadata(tmp_path, records):
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"files": records}))
    return path


def _names(output_path):
    return [r["file_name"] for r in json.loads(output_path.read_text())["classifications"]]


def _pair(name, fmt, *, md5):
    """One record for a producer to classify, keyed by the md5 under test."""
    return {
        "file_name": name,
        "file_format": fmt,
        "file_md5sum": md5,
        "file_size": 10,
        "dataset_id": "ds1",
        "dataset_title": "Study A",
        "entry_id": "e1",
    }


@pytest.mark.parametrize("bad_md5", [None, "", "abc123"], ids=["null", "empty", "malformed"])
class TestStandaloneProducers:
    def test_images_writes_no_row_for_a_checksum_less_file(self, tmp_path, bad_md5):
        metadata = _write_metadata(
            tmp_path,
            [_pair("kept.svs", ".svs", md5=GOOD_MD5), _pair("dropped.svs", ".svs", md5=bad_md5)],
        )
        output = tmp_path / "image_classifications.json"
        classify_images(metadata, output)
        assert _names(output) == ["kept.svs"]

    def test_auxiliary_writes_no_row_for_a_checksum_less_file(self, tmp_path, bad_md5):
        metadata = _write_metadata(
            tmp_path,
            [_pair("kept.pvar", ".pvar", md5=GOOD_MD5), _pair("dropped.pvar", ".pvar", md5=bad_md5)],
        )
        output = tmp_path / "auxiliary_classifications.json"
        classify_auxiliary_genomic(metadata, output)
        assert _names(output) == ["kept.pvar"]

    def test_catch_all_writes_no_row_for_a_checksum_less_file(self, tmp_path, bad_md5):
        """The catch-all is where a header-pipeline-only exclusion would have leaked."""
        metadata = _write_metadata(
            tmp_path,
            [_pair("kept.weird", ".weird", md5=GOOD_MD5), _pair("dropped.weird", ".weird", md5=bad_md5)],
        )
        output = tmp_path / "remaining_classifications.json"
        classify_remaining(metadata, output, [])
        assert _names(output) == ["kept.weird"]

    def test_index_propagation_writes_no_row_for_a_checksum_less_index(self, tmp_path, bad_md5):
        parent_md5 = "b" * 32
        metadata = _write_metadata(
            tmp_path,
            [
                _pair("s.bam", ".bam", md5=parent_md5),
                _pair("s.bam.bai", ".bai", md5=GOOD_MD5),
                _pair("t.bam", ".bam", md5="c" * 32),
                _pair("t.bam.bai", ".bai", md5=bad_md5),
            ],
        )
        parents = tmp_path / "bam_classifications.json"
        parents.write_text(
            json.dumps(
                {
                    "metadata": {},
                    "classifications": [
                        {
                            "file_name": "s.bam",
                            "md5sum": parent_md5,
                            "classifications": {
                                "data_modality": {"value": "genomic", "evidence": []},
                                "data_type": {"value": "alignments", "evidence": []},
                                "platform": {"value": "not_classified", "evidence": []},
                                "reference_assembly": {"value": "GRCh38", "evidence": []},
                                "assay_type": {"value": "not_classified", "evidence": []},
                            },
                        }
                    ],
                }
            )
        )
        output = tmp_path / "index_classifications.json"
        propagate_to_index_files(metadata, [parents], output)
        assert _names(output) == ["s.bam.bai"]


def test_a_non_dict_record_reaches_no_producer(tmp_path):
    """A non-dict cannot carry a checksum, so it is excluded at load — the catch-all
    reads records with ``.get`` and would raise on one."""
    metadata = _write_metadata(tmp_path, ["a bare string", None, _pair("kept.weird", ".weird", md5=GOOD_MD5)])
    output = tmp_path / "remaining_classifications.json"
    classify_remaining(metadata, output, [])
    assert _names(output) == ["kept.weird"]
