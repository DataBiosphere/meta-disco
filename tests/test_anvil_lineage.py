"""The AnVIL lineage importer (#583), on synthetic manifests: each of the map's forms, one
line per pair, an unknown child dropped and every parent written, the lookup's hits and
misses, the check against the manifests, and an import that is a generation."""

import pytest

from meta_disco import anvil_lineage as al
from meta_disco.lineage_evidence import iter_lineage, read_lineage_envelope
from meta_disco.lineage_map import load_lineage_map
from meta_disco.models import SOURCE_REPOSITORY_ACTIVITY, SOURCE_REPOSITORY_METADATA
from meta_disco.source_evidence import discover
from tests.manifest_fixtures import CATALOG, REAL_MANIFESTS, SERVICE, anvil_file, drs, write_dataset

STAMP = "20260930T000000Z"

MAP = """
catalog: anvil15
datasets:
  D:
    anvil_activity:
      - child: {column: generated_file_id, key: file_id}
        parent: {column: used_file_id, key: file_id}
        raw_activity: {cell: activity_type}
        activity_id: {cell: activity_id}
      - child: {column: generated_file_id, key: file_id}
        parent: {column: used_biosample_id, key: biosample_id}
        raw_activity: {cell: activity_type}
        activity_id: {cell: activity_id}
    sample:
      - child: {column: stats}
        parent: {column: cram}
      - child: {column: cram}
        parent: {column: read_1}
    file:
      - child: {column: file_path}
        parent: {column: derived_from, table: file, identifier_column: file_id, locator_column: file_path}
"""


def activity(generated, used_files=(), used_samples=(), activity_type: str | None = "Indexing", activity_id="a"):
    return "anvil_activity", {
        "activity_id": activity_id,
        "activity_type": activity_type,
        "generated_file_id": list(generated),
        "used_file_id": list(used_files),
        "used_biosample_id": list(used_samples),
    }


def entities():
    return [
        *(anvil_file(n) for n in range(1, 10)),
        activity(["f2"], ["f1"], activity_id="a1"),
        activity(["f3", "f4"], ["f1"], activity_type="Track: bedGraphToBigWig", activity_id="a2"),
        activity(["f5"], ["outside"], activity_type=None, activity_id="a3"),
        activity(["nobody"], ["f1"], activity_id="a4"),
        activity(["f6"], used_samples=["S1"], activity_type="Sequencing", activity_id="a5"),
        ("sample", {"stats": drs(7), "cram": drs(6), "read_1": drs(9)}),
        ("sample", {"stats": None, "cram": drs(6), "read_1": None}),
        ("file", {"file_id": "IGVF_BAI", "file_path": drs(8), "derived_from": ["IGVF_BAM", "IGVF_GONE"]}),
        ("file", {"file_id": "IGVF_BAM", "file_path": drs(6), "derived_from": []}),
    ]


@pytest.fixture
def imported(tmp_path):
    map_path = tmp_path / "map.yaml"
    map_path.write_text(MAP)
    lineage_map = load_lineage_map(map_path)
    write_dataset(tmp_path / "m", "D", entities())
    assert al.check(lineage_map, tmp_path / "m", CATALOG) == []
    (run,) = al.import_all(lineage_map, tmp_path / "m", CATALOG, SERVICE, tmp_path / "lin", generation=STAMP)
    return run


def lines(run, table):
    return [row.model_dump(exclude_none=True) for row in iter_lineage(run.directory / f"{table}.ndjson")]


def test_an_activity_row_is_one_line_per_pair_with_its_raw_words(imported):
    got = [
        (r["target_key_value"], r.get("parent"), r.get("raw_activity"), r.get("activity_id"))
        for r in lines(imported, "anvil_activity")
    ]
    assert got == [
        ("f2", "f1", "Indexing", "a1"),
        ("f3", "f1", "Track: bedGraphToBigWig", "a2"),
        ("f4", "f1", "Track: bedGraphToBigWig", "a2"),
        ("f5", "outside", None, "a3"),
        ("f6", "S1", "Sequencing", "a5"),
    ]


def test_a_null_activity_type_is_omitted_and_a_sample_parent_is_kept(imported):
    by_child = {r["target_key_value"]: r for r in lines(imported, "anvil_activity")}
    assert "raw_activity" not in by_child["f5"] and "raw_activity_column" not in by_child["f5"]
    assert by_child["f6"]["parent_key_type"] == "biosample_id"
    assert by_child["f2"] == {
        "target_key_value": "f2",
        "parent": "f1",
        "parent_key_type": "file_id",
        "raw_activity": "Indexing",
        "activity_id": "a1",
        "child_column": "generated_file_id",
        "parent_column": "used_file_id",
        "raw_activity_column": "activity_type",
    }


def test_an_unknown_child_is_dropped_and_a_parent_outside_the_dataset_is_written(imported):
    (table,) = [t for t in imported.tables if t.table == "anvil_activity"]
    assert table.child_outside == {"generated_file_id": 1}
    assert table.parent_outside == {"used_file_id": 1}
    assert "nobody" not in {r["target_key_value"] for r in lines(imported, "anvil_activity")}


def test_a_submitter_row_is_one_line_per_mapped_pair(imported):
    got = [
        (r["target_key_value"], r["parent"], r["child_column"], r["parent_column"]) for r in lines(imported, "sample")
    ]
    assert got == [(drs(7), drs(6), "stats", "cram"), (drs(6), drs(9), "cram", "read_1")]
    (table,) = [t for t in imported.tables if t.table == "sample"]
    # The second row's empty stats and read_1 cells are counted once each, not once per link.
    assert table.no_value == {"stats": 1, "read_1": 1}


def test_a_source_identifier_becomes_its_rows_locator_and_is_kept(imported):
    found, missing = lines(imported, "file")
    assert found == {
        "target_key_value": drs(8),
        "parent": drs(6),
        "parent_key_type": "drs_uri",
        "parent_source_identifier": "IGVF_BAM",
        "child_column": "file_path",
        "parent_column": "derived_from",
    }
    assert missing == {
        "target_key_value": drs(8),
        "parent_source_identifier": "IGVF_GONE",
        "child_column": "file_path",
        "parent_column": "derived_from",
    }
    (table,) = [t for t in imported.tables if t.table == "file"]
    assert table.identifier_missing == {"derived_from": 1}


def test_each_file_names_its_kind_and_how_its_child_is_keyed(imported):
    activity_envelope = read_lineage_envelope(imported.directory / "anvil_activity.ndjson")
    sample_envelope = read_lineage_envelope(imported.directory / "sample.ndjson")
    assert (activity_envelope.source_type, activity_envelope.target_key) == (SOURCE_REPOSITORY_ACTIVITY, "file_id")
    assert (sample_envelope.source_type, sample_envelope.target_key) == (SOURCE_REPOSITORY_METADATA, "drs_uri")
    assert activity_envelope.source.url == SERVICE and activity_envelope.target.dataset == "D"


def test_an_import_is_a_generation_and_never_overwrites_one(imported, tmp_path):
    assert imported.directory == tmp_path / "lin" / "anvil" / CATALOG / "D" / STAMP
    assert len(discover(tmp_path / "lin")) == 3
    map_path = tmp_path / "map.yaml"
    with pytest.raises(FileExistsError, match="never overwrites"):
        al.import_all(load_lineage_map(map_path), tmp_path / "m", CATALOG, SERVICE, tmp_path / "lin", generation=STAMP)


def test_a_table_that_writes_nothing_fails_the_import_and_leaves_nothing(tmp_path):
    map_path = tmp_path / "map.yaml"
    map_path.write_text(
        "catalog: anvil15\ndatasets:\n  D:\n    sample:\n      - {child: {column: stats}, parent: {column: cram}}\n"
    )
    write_dataset(tmp_path / "m", "D", [anvil_file(1), ("sample", {"stats": drs(1), "cram": None})])
    with pytest.raises(ValueError, match="no lineage line written"):
        al.import_all(load_lineage_map(map_path), tmp_path / "m", CATALOG, SERVICE, tmp_path / "lin", generation=STAMP)
    assert not list((tmp_path / "lin").rglob("*.ndjson"))


def test_the_check_names_every_problem(tmp_path):
    map_path = tmp_path / "map.yaml"
    map_path.write_text(
        """
catalog: anvil15
datasets:
  D:
    anvil_activity:
      - {child: {column: generated_file_id, key: file_id}, parent: {column: used_file_id, key: file_id}}
    sample:
      - {child: {column: stats}, parent: {column: missing}}
    file:
      - child: {column: file_path}
        parent: {column: derived_from, table: nowhere, identifier_column: file_id, locator_column: file_path}
  E:
    sample:
      - {child: {column: stats}, parent: {column: cram}}
"""
    )
    write_dataset(
        tmp_path / "m",
        "D",
        [
            anvil_file(1),
            activity(["someone-else"], ["f1"]),
            ("sample", {"stats": "not a drs uri"}),
            ("file", {"file_path": drs(1), "derived_from": ["X"]}),
        ],
    )
    problems = al.check(load_lineage_map(map_path), tmp_path / "m", CATALOG)
    assert problems == [
        "D/anvil_activity/generated_file_id: holds no file_id of this dataset's anvil_file rows",
        "D/nowhere: no row of this type in the manifest",
        "D/sample/missing: no row carries this column",
        "D/sample/stats: holds 'not a drs uri', not a DRS URI or a list of them",
        "E: not a dataset the anvil15 sidecar names",
    ]


@pytest.mark.skipif(not REAL_MANIFESTS.is_dir(), reason="the anvil15 manifests are not on disk")
def test_the_bundled_map_agrees_with_the_anvil15_manifests():
    assert al.check(load_lineage_map(), REAL_MANIFESTS.parent.parent, CATALOG) == []
