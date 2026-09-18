"""No file routes to two producers.

Every producer routes by filename suffix, so one filename reaches two of them exactly
when one producer's extension ends with another's. Both then write a full record, the
run holds two rows for one file, and no identifier in the output is unique (#445).
"""

from meta_disco.file_types import TAR_CONFIG
from meta_disco.pipeline import ClassifyPipeline
from tests.producer_sweep import (
    PRODUCER_EXTENSIONS,
    classify_auxiliary_genomic,
    run_producer,
    write_snapshot,
)


def _fast5_tar_record():
    return {
        "file_name": "HG02148_1.fast5.tar",
        "file_format": ".fast5.tar",
        "file_md5sum": "a" * 32,
        "file_size": 1024,
        "entry_id": "e1",
        "file_id": "f1",
        "drs_uri": "drs://example/f1",
        "dataset_title": "ANVIL_HPRC",
    }


def test_no_producer_claims_an_extension_another_producer_claims():
    """The suffix relation, not equality: `.fast5.tar` ends with `.tar`, so a file named
    for the first routes to the producer claiming the second as well."""
    collisions = []
    names = sorted(PRODUCER_EXTENSIONS)
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            for one in sorted(PRODUCER_EXTENSIONS[first]):
                for other in sorted(PRODUCER_EXTENSIONS[second]):
                    if one.endswith(other) or other.endswith(one):
                        collisions.append(f"{first} {one} / {second} {other}")
    assert not collisions, (
        "Producers claim overlapping extensions, so a file routes to both and the run "
        f"writes it twice: {collisions}. One of them must give the extension up."
    )


class TestATarOfFast5sIsATar:
    """An archive is classified as the container it is, by the producer that reads its
    members — not by the producer that knows the inner format's name (#242)."""

    def test_the_auxiliary_producer_writes_no_row_for_it(self, tmp_path):
        assert run_producer(classify_auxiliary_genomic, tmp_path, [_fast5_tar_record()]) == []

    def test_the_tar_type_routes_it(self, tmp_path):
        pipeline = ClassifyPipeline(
            TAR_CONFIG,
            write_snapshot(tmp_path, [_fast5_tar_record()]),
            tmp_path / "tar_classifications.json",
        )
        routed = pipeline._filter_records(pipeline._load_input())
        assert [r["file_name"] for r in routed] == ["HG02148_1.fast5.tar"]
