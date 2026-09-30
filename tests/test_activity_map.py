"""The activity translation table (#584): loading, selection, seeding and the review queue.

One test per acceptance criterion, numbered ``ac<N>`` in its name, plus the rules the
table adds (lists, null, one row per line, the data_type join). Tables are written in
each test and evidence through ``write_lineage_file`` / ``write_evidence_file`` into the
generation layout, so the seeder reads them as it reads a real generation; the one test
on the bundled table checks only that it loads.
"""

import re
from pathlib import Path

import generate_review_queue as grq
import pytest

from meta_disco.activity_map import (
    PARTS,
    QUEUE_GROUP_TEXT,
    ActivityMap,
    keyed_lines,
    lineage_paths,
    load_activity_map,
    render_section,
    review,
    seed,
)
from meta_disco.lineage_evidence import LINEAGE_SOURCE_TYPES, write_lineage_file
from meta_disco.models import SOURCE_REPOSITORY_ACTIVITY, SOURCE_REPOSITORY_METADATA
from meta_disco.schema.classification_model import (
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    ImporterSourceTypeEnum,
    JoinKeyEnum,
    LineageRow,
)
from meta_disco.source_evidence import (
    EvidenceEntry,
    claim_source_for,
    discover,
    evidence_file_path,
    generation_dir,
)
from tests.test_value_map import imported_segments, write_generation

STAMP = "20260930T062532Z"


def envelope(table, source_type=SOURCE_REPOSITORY_ACTIVITY, dataset="D", key="file_id", version="anvil15"):
    return EvidenceFileEnvelope(
        source=EvidenceFileSource(repository="anvil", dataset=dataset, table=table, url="https://azul.test"),
        source_type=ImporterSourceTypeEnum(source_type),
        source_version=version,
        source_key=key,
        target=EvidenceTarget(system="anvil", dataset=dataset, version=version),
        target_key=JoinKeyEnum(key),
        fetched_at="2026-09-03T21:45:47",
    )


def line(child, parent, child_column="generated_file_id", parent_column="used_file_id", key="file_id", **more):
    members = {
        "target_key_value": child,
        "parent": parent,
        "parent_key_type": key,
        "child_column": child_column,
        "parent_column": parent_column,
        **more,
    }
    return LineageRow.model_validate(members)


def activity_line(child, parent, raw_activity, parent_column="used_file_id"):
    return line(
        child, parent, parent_column=parent_column, raw_activity=raw_activity, raw_activity_column="activity_type"
    )


def write_lineage(root, table, rows, dataset="D", **envelope_kw):
    directory = generation_dir(root, "anvil", "anvil15", dataset, STAMP)
    directory.mkdir(parents=True, exist_ok=True)
    write_lineage_file(evidence_file_path(directory, table), envelope(table, dataset=dataset, **envelope_kw), rows)


def write_slots(root, table, data_types, dataset="D", source_type=SOURCE_REPOSITORY_METADATA, key="drs_uri"):
    """One slot evidence file giving each ``(target, raw data_type)`` in ``data_types``."""
    env = envelope(table, source_type=source_type, dataset=dataset, key=key)
    source = claim_source_for(env.source, "content_type")
    entries = [EvidenceEntry("data_type", target, raw, source) for target, raw in data_types]
    write_generation(root, dataset, table, entries, envelope=env)


def table_file(tmp_path, text, name="activity_map.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def key(**parts):
    return tuple(parts.get(p) for p in PARTS)


@pytest.fixture
def roots(tmp_path):
    return tmp_path / "lineage", tmp_path / "evidence"


# --- acceptance ------------------------------------------------------------------


def test_ac1_seeding_lists_every_raw_activity_and_column_pair_and_a_second_seed_adds_nothing(tmp_path, roots):
    lineage, evidence = roots
    write_lineage(
        lineage,
        "anvil_activity",
        [
            activity_line("c1", "p1", "Indexing"),
            activity_line("c2", "p2", "Indexing"),
            activity_line("c3", "s1", "Sequencing", parent_column="used_biosample_id"),
            line("c4", "p4"),  # no activity_type cell
        ],
    )
    write_lineage(
        lineage,
        "sample",
        [line("d1", "d2", "cram_index", "cram", "drs_uri"), line("d3", "d2", "samtools_stats", "cram", "drs_uri")],
        source_type=SOURCE_REPOSITORY_METADATA,
        key="drs_uri",
    )
    path = table_file(tmp_path, "rows:\n")
    first = seed(path, lineage, evidence)
    assert first.lines_scanned == 6
    assert len(first.rows_added) == 5
    table = load_activity_map(path)
    selected = {
        (row.match["raw_activity"], row.match["child_column"], row.match["parent_column"]) for row in table.rows
    }
    assert selected == {
        (frozenset({"Indexing"}), frozenset({"generated_file_id"}), frozenset({"used_file_id"})),
        (frozenset({"Sequencing"}), frozenset({"generated_file_id"}), frozenset({"used_biosample_id"})),
        (frozenset({None}), frozenset({"generated_file_id"}), frozenset({"used_file_id"})),
        (frozenset({None}), frozenset({"cram_index"}), frozenset({"cram"})),
        (frozenset({None}), frozenset({"samtools_stats"}), frozenset({"cram"})),
    }
    assert all(not row.authored and set(row.match) == set(PARTS) for row in table.rows)
    before = path.read_text()
    assert seed(path, lineage, evidence).rows_added == ()
    assert path.read_text() == before


def test_ac1_seeding_keeps_an_authored_row_byte_for_byte_and_skips_what_it_matches(tmp_path, roots):
    lineage, evidence = roots
    write_lineage(lineage, "anvil_activity", [activity_line("c1", "p1", "Indexing"), activity_line("c2", "p2", "X")])
    authored = (
        "rows:\n"
        "  - id: activity.indexing\n"
        "    match: {source_type: repository_activity, raw_activity: Indexing}\n"
        "    declares: {activity: IndexActivity, role: indexed}\n"
        "    reason: An index of the file it used.\n"
    )
    path = table_file(tmp_path, authored)
    assert len(seed(path, lineage, evidence).rows_added) == 1
    assert path.read_text().startswith(authored)
    assert [row.id for row in load_activity_map(path).rows][1:] == [
        "activity.anvil_activity_x_generated_file_id_used_file_id"
    ]


AUTHORED = (
    "rows:\n"
    "  - id: activity.a\n"
    "    match: {{source_type: repository_activity, raw_activity: Indexing}}\n"
    "    declares: {{activity: {activity}, role: {role}}}\n"
    "    reason: why.\n"
)


@pytest.mark.parametrize(
    "activity, role, message",
    [
        ("IndexingActivity", "indexed", "declares activity 'IndexingActivity', which activities.yaml does not declare"),
        ("IndexActivity", "reads", "declares role 'reads', which IndexActivity does not declare"),
    ],
)
def test_ac2_an_undeclared_activity_or_role_fails_naming_the_row(tmp_path, activity, role, message):
    path = table_file(tmp_path, AUTHORED.format(activity=activity, role=role))
    with pytest.raises(ValueError, match=re.escape("row 'activity.a'")) as raised:
        load_activity_map(path)
    assert message in str(raised.value)


def test_ac3_the_bundled_table_loads():
    table = load_activity_map()
    assert any(row.authored for row in table.rows)


def test_ac3_the_review_queue_lists_what_no_authored_row_reads(tmp_path, roots):
    lineage, evidence = roots
    write_lineage(
        lineage,
        "anvil_activity",
        [
            activity_line("c1", "p1", "Indexing"),
            activity_line("c2", "p2", "Unknown"),
            activity_line("c3", "p3", "Unknown"),
        ],
    )
    path = table_file(tmp_path, AUTHORED.format(activity="IndexActivity", role="indexed"))
    seed(path, lineage, evidence)
    found = review(load_activity_map(path), lineage, evidence)
    assert [(e.key[PARTS.index("raw_activity")], e.lines, e.datasets) for e in found.queue] == [("Unknown", 2, ("D",))]
    assert found.queue[0].row_id is not None
    assert [(m.row.id, m.lines) for m in found.mappings] == [("activity.a", 1)]
    markdown = "\n".join(render_section(found.queue, found.mappings))
    assert "'Unknown'" in markdown and "IndexActivity / indexed" in markdown
    page = grq.render_html([], evidence, "QUEUE_PLACEHOLDER", lineage=found)
    assert "Unknown" in page and "Authored activity mappings" in page


def test_ac4_nothing_but_the_review_queue_imports_the_table():
    """Inference output is unchanged because no classification code reaches the module: of every module and
    script but its own entry point, only the review-queue report imports it, and it writes only its two files."""
    sources = [*Path("src/meta_disco").rglob("*.py"), *Path("scripts").rglob("*.py")]
    importers = sorted(
        str(p) for p in sources if p.name != "activity_map.py" and "activity_map" in imported_segments(p)
    )
    assert importers == ["scripts/generate_review_queue.py"], importers


# --- matching ----------------------------------------------------------------------


def rows(*match_texts) -> str:
    return "rows:\n" + "".join(f"  - id: activity.r{n}\n    match: {m}\n" for n, m in enumerate(match_texts))


def test_a_listed_part_matches_each_member_and_only_those(tmp_path):
    table = load_activity_map(
        table_file(
            tmp_path,
            rows("{source_type: repository_metadata, child_column: [chr1_vcf, chr2_vcf], parent_column: cram}"),
        )
    )
    st = SOURCE_REPOSITORY_METADATA
    assert table.select(key(source_type=st, child_column="chr2_vcf", parent_column="cram")) is table.rows[0]
    assert table.select(key(source_type=st, child_column="chr3_vcf", parent_column="cram")) is None
    assert table.select(key(source_type=st, child_column="chr1_vcf", parent_column="crai")) is None


def test_null_matches_only_a_line_without_the_part_and_matching_is_exact(tmp_path):
    table = load_activity_map(
        table_file(
            tmp_path,
            rows(
                "{source_type: repository_activity, raw_activity: null}",
                "{source_type: repository_activity, raw_activity: Indexing}",
            ),
        )
    )
    st = SOURCE_REPOSITORY_ACTIVITY
    assert table.select(key(source_type=st)) is table.rows[0]
    assert table.select(key(source_type=st, raw_activity="Indexing")) is table.rows[1]
    assert table.select(key(source_type=st, raw_activity="indexing")) is None
    assert table.select(key(source_type=st, raw_activity="")) is None


@pytest.mark.parametrize(
    "first, second",
    [
        # One names a part the other does not: a line with both values matches both.
        (
            "{source_type: repository_activity, raw_activity: Indexing}",
            "{source_type: repository_activity, parent_column: used_file_id}",
        ),
        # An authored list and a seeded row it covers.
        (
            "{source_type: repository_metadata, child_column: [a, b]}",
            "{source_type: repository_metadata, child_column: b, parent_column: c}",
        ),
    ],
)
def test_two_rows_that_can_match_one_line_cannot_load(tmp_path, first, second):
    with pytest.raises(ValueError, match=re.escape("rows 'activity.r0' and 'activity.r1' can both match one line")):
        load_activity_map(table_file(tmp_path, rows(first, second)))


def test_rows_apart_on_a_shared_part_load(tmp_path):
    table = load_activity_map(
        table_file(
            tmp_path,
            rows("{source_type: repository_activity, raw_activity: A}", "{source_type: repository_metadata, table: t}"),
        )
    )
    assert isinstance(table, ActivityMap)


@pytest.mark.parametrize(
    "row_text, message",
    [
        ("    match: {raw_activity: Indexing}\n", "match names no source_type"),
        ("    match: {source_type: published_value}\n", "is not a lineage source"),
        (
            "    match: {source_type: repository_activity, activity_type: X}\n",
            "match has unknown parts ['activity_type']",
        ),
        ("    match: {source_type: repository_activity, raw_activity: []}\n", "an empty list matches nothing"),
        ("    match: {source_type: repository_activity, raw_activity: [A, A]}\n", "a value is listed twice"),
        (
            "    match: {source_type: repository_activity}\n    declares: {activity: IndexActivity, role: indexed}\n",
            "a seeded row declares nothing",
        ),
        ("    match: {source_type: repository_activity}\n    reason: why.\n", "has a reason but no `declares`"),
        (
            "    match: {source_type: repository_activity}\n    declares: {activity: IndexActivity}\n    reason: why.\n",
            "it declares exactly ['activity', 'role']",
        ),
    ],
)
def test_a_malformed_row_is_refused_naming_it(tmp_path, row_text, message):
    with pytest.raises(ValueError, match=re.escape("row 'activity.x'")) as raised:
        load_activity_map(table_file(tmp_path, "rows:\n  - id: activity.x\n" + row_text))
    assert message in str(raised.value)


def test_an_id_outside_the_prefix_is_refused(tmp_path):
    with pytest.raises(ValueError, match=re.escape("id must be 'activity.<slug>'")):
        load_activity_map(
            table_file(tmp_path, "rows:\n  - id: platform.x\n    match: {source_type: repository_activity}\n")
        )


# --- the data_type join -------------------------------------------------------------


def test_child_and_parent_data_types_come_from_the_same_tables_slot_evidence(roots):
    lineage, evidence = roots
    write_lineage(
        lineage,
        "file",
        [
            line("drs://i", "drs://a", "file_path", "derived_from", "drs_uri"),
            line("drs://a", "drs://elsewhere", "file_path", "derived_from", "drs_uri"),
        ],
        source_type=SOURCE_REPOSITORY_METADATA,
        key="drs_uri",
    )
    write_slots(evidence, "file", [("drs://i", "index"), ("drs://a", "alignments")])
    # Another table's data_type for the same file does not speak for this one's lines.
    write_slots(evidence, "other", [("drs://elsewhere", "reads")])
    keys = [k.key for k in keyed_lines(lineage, evidence, lineage_paths(lineage))]
    types = [(k[PARTS.index("child_data_type")], k[PARTS.index("parent_data_type")]) for k in keys]
    assert types == [("index", "alignments"), ("alignments", None)]


def test_a_file_given_two_data_types_by_its_table_keys_with_none(roots):
    lineage, evidence = roots
    write_lineage(
        lineage,
        "file",
        [line("drs://i", "drs://a", "file_path", "derived_from", "drs_uri")],
        source_type=SOURCE_REPOSITORY_METADATA,
        key="drs_uri",
    )
    write_slots(evidence, "file", [("drs://i", "index"), ("drs://i", "alignments"), ("drs://a", "alignments")])
    (keyed,) = keyed_lines(lineage, evidence, lineage_paths(lineage))
    assert (keyed.key[PARTS.index("child_data_type")], keyed.key[PARTS.index("parent_data_type")]) == (
        None,
        "alignments",
    )


def test_only_the_latest_catalog_is_read_and_slot_files_of_another_catalog_are_not_joined(tmp_path, roots):
    lineage, evidence = roots
    rows = [line("drs://i", "drs://a", "file_path", "derived_from", "drs_uri")]
    old = generation_dir(lineage, "anvil", "anvil9", "D", "20260101T000000Z")
    new = generation_dir(lineage, "anvil", "anvil16", "D", "20260901T000000Z")
    for directory, version in ((old, "anvil9"), (new, "anvil16")):
        directory.mkdir(parents=True)
        env = envelope("file", source_type=SOURCE_REPOSITORY_METADATA, key="drs_uri", version=version)
        write_lineage_file(evidence_file_path(directory, "file"), env, rows)
    # anvil16 is latest by its stamp, although "anvil9" sorts after it as text.
    assert lineage_paths(lineage) == [evidence_file_path(new, "file")]
    # A slot file of the older catalog gives the child a data type; it is not joined.
    older = envelope("file", source_type=SOURCE_REPOSITORY_METADATA, key="drs_uri", version="anvil9")
    source = claim_source_for(older.source, "content_type")
    write_generation(evidence, "D", "file", [EvidenceEntry("data_type", "drs://i", "index", source)], envelope=older)
    (keyed,) = keyed_lines(lineage, evidence, lineage_paths(lineage))
    assert keyed.key[PARTS.index("child_data_type")] is None
    with pytest.raises(ValueError, match=re.escape("names 2 catalogs, ['anvil16', 'anvil9']")):
        list(keyed_lines(lineage, evidence, discover(lineage)))


def test_the_queue_has_a_group_for_every_lineage_source_type():
    """So an entry of a new lineage kind cannot fall out of both reports unlisted."""
    assert set(QUEUE_GROUP_TEXT) == LINEAGE_SOURCE_TYPES
