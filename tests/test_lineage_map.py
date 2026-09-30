"""The lineage map (#583): its one entry shape, the keys each side may hold, one child
key per table, and the refusals that keep it structural."""

import pytest

from meta_disco.lineage_map import Lookup, load_lineage_map, source_type_of
from meta_disco.models import SOURCE_REPOSITORY_ACTIVITY, SOURCE_REPOSITORY_METADATA


def load(tmp_path, text):
    path = tmp_path / "map.yaml"
    path.write_text(text)
    return load_lineage_map(path)


def test_the_bundled_map_loads():
    assert load_lineage_map().links


def test_the_three_forms_load_as_written(tmp_path):
    lineage_map = load(
        tmp_path,
        """
catalog: anvil15
datasets:
  D:
    anvil_activity:
      - child: {column: generated_file_id, key: file_id}
        parent: {column: used_file_id, key: file_id}
        raw_activity: {cell: activity_type}
        activity_id: {cell: activity_id}
    sample:
      - child: {column: stats}
        parent: {column: cram}
    file:
      - child: {column: file_path}
        parent: {column: derived_from, table: file, identifier_column: file_id, locator_column: file_path}
""",
    )
    activity, row, lookup = lineage_map.links
    assert (activity.child_key, activity.parent_key, activity.raw_activity_cell, activity.activity_id_cell) == (
        "file_id",
        "file_id",
        "activity_type",
        "activity_id",
    )
    assert (row.child_key, row.parent_key, row.lookup, row.raw_activity_cell) == ("drs_uri", "drs_uri", None, None)
    assert lookup.parent_key is None
    assert lookup.lookup == Lookup(table="file", identifier_column="file_id", locator_column="file_path")
    assert lineage_map.tables("D") == ["anvil_activity", "sample", "file"]


def test_the_kind_of_source_follows_from_the_table():
    assert source_type_of("anvil_activity") == SOURCE_REPOSITORY_ACTIVITY
    assert source_type_of("participant") == SOURCE_REPOSITORY_METADATA


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ("- {child: {column: a}, parent: {column: b, key: md5}}", "key 'md5'"),
        ("- {child: {column: a, key: biosample_id}, parent: {column: b}}", "key 'biosample_id'"),
        ("- {child: {column: a}, parent: {column: b}, notes: why}", "no notes member"),
        ("- {child: {column: a}, parent: {column: b}, value: x}", "keys are"),
        ("- {child: {column: a}, parent: {column: a}}", "both column 'a'"),
        ("- {child: {column: a}, parent: {column: b, table: t, identifier_column: i}}", "keys are"),
        ("- {child: {column: a}, parent: {column: b}, raw_activity: {cell: ''}}", "not a column or table name"),
        (
            "- {child: {column: a}, parent: {column: b}}\n      - {child: {column: a}, parent: {column: b}}",
            "listed twice",
        ),
        (
            "- {child: {column: a}, parent: {column: b}}\n      - {child: {column: c, key: file_id}, parent: {column: b}}",
            "one table is one file",
        ),
    ],
)
def test_a_malformed_link_is_refused_naming_it(tmp_path, entry, message):
    with pytest.raises(ValueError, match=message):
        load(tmp_path, f"catalog: anvil15\ndatasets:\n  D:\n    t:\n      {entry}\n")


def test_a_harmonized_table_other_than_anvil_activity_is_refused(tmp_path):
    with pytest.raises(ValueError, match="states no lineage"):
        load(
            tmp_path,
            "catalog: anvil15\ndatasets:\n  D:\n    anvil_file:\n      - {child: {column: a}, parent: {column: b}}\n",
        )


def test_a_repeated_key_is_refused(tmp_path):
    with pytest.raises(ValueError, match="given twice"):
        load(tmp_path, "catalog: anvil15\ndatasets:\n  D:\n    t: []\n    t: []\n")


def test_a_top_level_notes_member_is_refused(tmp_path):
    with pytest.raises(ValueError, match="no notes member"):
        load(tmp_path, "catalog: anvil15\ndatasets: {}\nnotes: x\n")
