"""Derivation edges from a child's own name: the catch-all's ``ChecksumActivity`` edge (#356).

The index producer's ``IndexingActivity`` edge is tested with that producer, in
``test_index_propagation``. Here: a checksum file names the file it checks where exactly
one file of its dataset carries its name less ``.md5``, and nothing otherwise.
"""

from tests.metadata_fixtures import valid_record
from tests.producer_sweep import CATCH_ALL, run_producer


def _file(name: str, file_id: str, dataset_id: str = "d1") -> dict:
    return valid_record(
        file_name=name, file_format="." + name.rsplit(".", 1)[-1], file_id=file_id, dataset_id=dataset_id
    )


def _rows(tmp_path, records) -> dict[str, dict]:
    return {r["file_name"]: r for r in run_producer(CATCH_ALL, tmp_path, records)}


def test_a_checksum_file_names_the_one_file_it_checks(tmp_path):
    rows = _rows(tmp_path, [_file("sample.bam", "f-bam"), _file("sample.bam.md5", "f-md5")])
    provenance = {"source_type": "filename_rule", "rule_id": "checksum_by_name"}
    assert rows["sample.bam.md5"]["generated_by"] == {
        "activity": "ChecksumActivity",
        **provenance,
        "inputs": [
            {
                "role": "checked",
                "parent_file": "sample.bam",
                "parent_key": "f-bam",
                "parent_kind": "alignment",
                **provenance,
            }
        ],
    }
    # The parent itself states nothing.
    assert rows["sample.bam"]["generated_by"] is None


def test_the_parent_name_is_matched_across_case_and_named_as_the_catalog_spells_it(tmp_path):
    rows = _rows(tmp_path, [_file("Sample.BAM", "f-bam"), _file("sample.bam.MD5", "f-md5")])
    [edge] = rows["sample.bam.MD5"]["generated_by"]["inputs"]
    assert (edge["parent_file"], edge["parent_key"]) == ("Sample.BAM", "f-bam")


def test_no_file_carrying_the_name_gives_no_edge(tmp_path):
    rows = _rows(tmp_path, [_file("sample.bam.md5", "f-md5")])
    assert rows["sample.bam.md5"]["generated_by"] is None


def test_a_name_two_files_carry_gives_no_edge(tmp_path):
    """#438's rule for an index, applied to a checksum: a shared name names neither file."""
    rows = run_producer(
        CATCH_ALL,
        tmp_path,
        [_file("sample.bam", "f-1"), _file("sample.bam", "f-2"), _file("sample.bam.md5", "f-md5")],
    )
    [md5] = [r for r in rows if r["file_name"] == "sample.bam.md5"]
    assert md5["generated_by"] is None


def test_a_parent_in_another_dataset_is_not_the_parent(tmp_path):
    """A file's lineage lives in its dataset (ADR-0002): the same name elsewhere is not it."""
    rows = _rows(tmp_path, [_file("sample.bam", "f-bam", dataset_id="d2"), _file("sample.bam.md5", "f-md5")])
    assert rows["sample.bam.md5"]["generated_by"] is None


def test_a_wrapped_checksum_names_its_parent_by_stem(tmp_path):
    """The rule matches `.md5` under a wrapper, and the parent is the name's stem."""
    rows = _rows(tmp_path, [_file("sample.bam", "f-bam"), _file("sample.bam.md5.gz", "f-md5")])
    [edge] = rows["sample.bam.md5.gz"]["generated_by"]["inputs"]
    assert edge["parent_key"] == "f-bam"


def test_a_file_that_is_not_a_checksum_gets_no_edge(tmp_path):
    """`sample.bam.txt` strips to a held name too, but only a checksum states the edge."""
    rows = _rows(tmp_path, [_file("sample.bam", "f-bam"), _file("sample.bam.txt", "f-txt")])
    assert rows["sample.bam.txt"]["generated_by"] is None
