"""No file routes to two producers on a shared extension.

A producer claims a record whose ``file_format`` or ``file_name`` carries one of its
extensions, so two of them claim one file when one's extension ends with another's —
what put 115 files in two output files each (#445). Both write a full record, the run
holds two rows for one file, and no identifier in the output is unique.

The suffix relation is not the only way two producers can claim one record: the two
fields are matched independently, so a ``file_name`` answering one producer and a
``file_format`` answering another collides with no shared extension at all. That shape
is caught after the fact by ``classify_run._check_one_row_per_file``, not here.
"""

import itertools

import pytest

from meta_disco.file_types import TAR_CONFIG
from meta_disco.pipeline import ClassifyPipeline
from tests.metadata_fixtures import valid_record
from tests.producer_sweep import (
    PRODUCER_EXTENSIONS,
    classify_auxiliary_genomic,
    run_producer,
    write_snapshot,
)


def _fast5_tar_record(file_name="HG02148_1.fast5.tar", file_format=".fast5.tar"):
    return valid_record(file_name=file_name, file_format=file_format, dataset_title="ANVIL_HPRC")


def test_no_producer_claims_an_extension_another_producer_claims():
    """The suffix relation, not equality: `.fast5.tar` ends with `.tar`, so a file named
    for the first routes to the producer claiming the second as well."""
    claims = [(producer, ext) for producer, exts in sorted(PRODUCER_EXTENSIONS.items()) for ext in sorted(exts)]
    collisions = [
        f"{one_producer} {one} / {other_producer} {other}"
        for (one_producer, one), (other_producer, other) in itertools.combinations(claims, 2)
        if one_producer != other_producer and (one.endswith(other) or other.endswith(one))
    ]
    assert not collisions, (
        "Producers claim overlapping extensions, so a file routes to both and the run "
        f"writes it twice: {collisions}. One of them must give the extension up."
    )


class TestATarOfFast5sIsATar:
    """An archive is classified as the container it is, by the producer that reads its
    members — not by the producer that knows the inner format's name (#242)."""

    def test_the_auxiliary_producer_writes_no_row_for_it(self, tmp_path):
        assert run_producer(classify_auxiliary_genomic, tmp_path, [_fast5_tar_record()]) == []

    @pytest.mark.parametrize(
        "file_name, file_format",
        [
            ("HG02148_1.fast5.tar", ".fast5"),
            ("HG02148_1.fast5.tar.gz", ".fast5"),
        ],
        ids=["tar", "tar.gz"],
    )
    def test_nor_when_the_source_declares_the_core_extension(self, tmp_path, file_name, file_format):
        """A source may set `file_format` from the parsed core, so the archive arrives
        declaring `.fast5`. Matching that on the format while the tar type matches the
        name is how one file gets two rows with no shared extension to detect."""
        records = [_fast5_tar_record(file_name=file_name, file_format=file_format)]
        assert run_producer(classify_auxiliary_genomic, tmp_path, records) == []

    def test_an_unwrapped_fast5_stays_with_the_auxiliary_producer(self, tmp_path):
        rows = run_producer(classify_auxiliary_genomic, tmp_path, [_fast5_tar_record("HG02148_1.fast5", ".fast5")])
        assert [r["file_name"] for r in rows] == ["HG02148_1.fast5"]

    def test_the_tar_type_routes_it(self, tmp_path):
        pipeline = ClassifyPipeline(
            TAR_CONFIG,
            write_snapshot(tmp_path, [_fast5_tar_record()]),
            tmp_path / "tar_classifications.json",
        )
        routed = pipeline._filter_records(pipeline._load_input())
        assert [r["file_name"] for r in routed] == ["HG02148_1.fast5.tar"]
