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

from meta_disco.exclusions import EXCLUDED_FILE, read_excluded
from tests.metadata_fixtures import valid_record, write_metadata

GOOD_MD5 = "a" * 32
# One representative unusable value. The md5-shape axis (null, empty, uppercase, wrong
# length, non-hex, non-string, non-dict) is covered exhaustively against the predicate
# in test_exclusions.py; what these tests pin is that each producer is wired to it.
BAD_MD5 = None


def _write_metadata(tmp_path, records):
    return write_metadata(tmp_path / "metadata.json", records)


def _names(output_path):
    return [r["file_name"] for r in json.loads(output_path.read_text())["classifications"]]


def _pair(name, fmt, *, md5):
    """One contract-shaped record for a producer to classify, keyed by the md5 under test."""
    return valid_record(
        file_name=name,
        file_format=fmt,
        file_md5sum=md5,
        file_size=10,
        dataset_id="ds1",
        dataset_title="Study A",
        entry_id="e1",
    )


class TestStandaloneProducers:
    def test_images_writes_no_row_for_a_checksum_less_file(self, tmp_path):
        metadata = _write_metadata(
            tmp_path,
            [_pair("kept.svs", ".svs", md5=GOOD_MD5), _pair("dropped.svs", ".svs", md5=BAD_MD5)],
        )
        output = tmp_path / "image_classifications.json"
        classify_images(metadata, output)
        assert _names(output) == ["kept.svs"]

    def test_auxiliary_writes_no_row_for_a_checksum_less_file(self, tmp_path):
        metadata = _write_metadata(
            tmp_path,
            [_pair("kept.pvar", ".pvar", md5=GOOD_MD5), _pair("dropped.pvar", ".pvar", md5=BAD_MD5)],
        )
        output = tmp_path / "auxiliary_classifications.json"
        classify_auxiliary_genomic(metadata, output)
        assert _names(output) == ["kept.pvar"]

    def test_catch_all_writes_no_row_for_a_checksum_less_file(self, tmp_path):
        """The catch-all is where a header-pipeline-only exclusion would have leaked."""
        metadata = _write_metadata(
            tmp_path,
            [_pair("kept.weird", ".weird", md5=GOOD_MD5), _pair("dropped.weird", ".weird", md5=BAD_MD5)],
        )
        output = tmp_path / "remaining_classifications.json"
        classify_remaining(metadata, output, [])
        assert _names(output) == ["kept.weird"]

    def test_index_propagation_writes_no_row_for_a_checksum_less_index(self, tmp_path):
        parent_md5 = "b" * 32
        metadata = _write_metadata(
            tmp_path,
            [
                _pair("s.bam", ".bam", md5=parent_md5),
                _pair("s.bam.bai", ".bai", md5=GOOD_MD5),
                _pair("t.bam", ".bam", md5="c" * 32),
                _pair("t.bam.bai", ".bai", md5=BAD_MD5),
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


class TestEveryProducerRecordsWhatItExcluded:
    """Excluding and recording are one act, so a producer cannot shed a record silently.

    This is what makes the guarantee hold for a standalone ``make classify-<type>`` run,
    which no orchestrator wraps: the shared loader writes ``excluded_files.json`` into
    the directory the producer is writing its output into.
    """

    def _run_catch_all(self, tmp_path, records):
        metadata = _write_metadata(tmp_path, records)
        run_dir = tmp_path / "run"
        classify_remaining(metadata, run_dir / "remaining_classifications.json", [])
        return run_dir

    def test_the_excluded_file_is_named_in_the_run_directory(self, tmp_path):
        run_dir = self._run_catch_all(
            tmp_path,
            [_pair("kept.weird", ".weird", md5=GOOD_MD5), _pair("dropped.weird", ".weird", md5=BAD_MD5)],
        )
        index = read_excluded(run_dir)
        assert index.present is True
        assert [f.file_name for f in index.files] == ["dropped.weird"]
        assert index.total_input == 2

    def test_the_file_is_written_even_when_nothing_was_excluded(self, tmp_path):
        run_dir = self._run_catch_all(tmp_path, [_pair("kept.weird", ".weird", md5=GOOD_MD5)])
        index = read_excluded(run_dir)
        assert index.present is True
        assert index.files == []

    def test_the_header_pipeline_records_into_its_own_run_directory(self, tmp_path):
        """`make classify-bam` writes into a fresh partials dir with no orchestrator; the
        exclusions land beside its output rather than nowhere."""
        from meta_disco.file_types import FILE_TYPE_REGISTRY
        from meta_disco.pipeline import ClassifyPipeline

        metadata = _write_metadata(
            tmp_path,
            [_pair("a.bed", ".bed", md5=GOOD_MD5), _pair("b.bed", ".bed", md5=BAD_MD5)],
        )
        run_dir = tmp_path / "partials" / "20260101_000000"
        ClassifyPipeline(
            FILE_TYPE_REGISTRY["bed"],
            metadata,
            run_dir / "bed_classifications.json",
            evidence_base=tmp_path / "evidence",
        )._load_input()

        assert [f.file_name for f in read_excluded(run_dir).files] == ["b.bed"]

    def test_concurrent_producers_leave_one_complete_file(self, tmp_path):
        """Every producer of a run writes this file, in parallel. They all read the same
        input and apply the same predicate, so the writes are identical; the atomic
        replace is what stops a reader seeing a half-written one."""
        from concurrent.futures import ThreadPoolExecutor

        from meta_disco.pipeline import load_classifiable_records

        metadata = _write_metadata(
            tmp_path,
            [_pair(f"f{i}.weird", ".weird", md5=BAD_MD5) for i in range(50)]
            + [_pair("kept.weird", ".weird", md5=GOOD_MD5)],
        )
        run_dir = tmp_path / "run"
        run_dir.mkdir()

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: load_classifiable_records(metadata, run_dir), range(24)))

        assert all(len(kept) == 1 for kept in results)
        index = read_excluded(run_dir)
        assert len(index.files) == 50
        assert index.total_input == 51
        # No temp files left behind by the write-then-rename.
        assert [p.name for p in run_dir.iterdir()] == [EXCLUDED_FILE]
