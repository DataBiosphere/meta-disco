"""AnVIL's links from a file to its biosamples as a source of the file's samples (#698), and the lists no route ties.

The links are lineage lines whose parent is a biosample (``anvil_activity.used_biosample_id``), written
here as the lineage importer writes them; each biosample ties to a sample record through an entity
evidence line carrying AnVIL's id for it (#669), written as the entity importer writes it.
"""

from pathlib import Path

import pytest
from generate_reconcile_report import CONFLICT_COLUMNS, conflict_tsv, dashboard_data, main, render_markdown

from meta_disco import code_rules
from meta_disco.edges import lineage_attribution
from meta_disco.models import (
    COLLECTED_FROM,
    SAMPLE_REPOSITORY_ID,
    SAMPLES_FIELD,
    SOURCE_REPOSITORY_ACTIVITY,
    SOURCE_REPOSITORY_METADATA,
    ClaimSource,
)
from meta_disco.output_utils import (
    FILES_WITHOUT_SAMPLES_FILE,
    RECONCILED_DIR,
    SAMPLE_CONFLICTS_FILE,
    UNREACHED_ENTITIES_FILE,
    iter_reconciled_artifact,
)
from meta_disco.reconcile_lineage import (
    CHILD_NOT_IN_RUN,
    CHILD_SEVERAL_MATCH,
    SAMPLE_PARENT,
    BiosampleLink,
    Carrier,
    PendingLineage,
    resolve_lineage,
)
from meta_disco.reconcile_samples import (
    ACTIVITY,
    ACTIVITY_ONLY,
    AGREED,
    CONFLICT,
    NONE,
    PARENT_CONFLICT,
    TIED,
    UNTIED,
    Named,
    activity_sources,
    settle,
)
from meta_disco.sample_identity import Identifier, reference, sample_list
from meta_disco.schema.classification_model import ClassificationRecord
from tests.lineage_fixtures import line, write_lineage
from tests.test_entities import write_entity_lines
from tests.test_reconcile import DATASET, go, record
from tests.test_reconcile_samples import (
    HEADER,
    child,
    coriell,
    header,
    reconciled,
    table_says,
    with_header_samples,
    write_bam_run,
)
from tests.test_value_map import load

SOURCE = ClaimSource(name="anvil", dataset=DATASET, table="anvil_activity", column="used_biosample_id")


def activity_says(*ids: str, activity_id: str = "a1") -> Named:
    attribution = {
        "source_type": SOURCE_REPOSITORY_ACTIVITY,
        "rule_id": code_rules.SAMPLES_FROM_ACTIVITY_BIOSAMPLE.id,
        "source": SOURCE.to_dict(),
        "activity_id": activity_id,
    }
    return Named(frozenset(coriell(i) for i in ids), (attribution,), kind=ACTIVITY)


# --- settling ------------------------------------------------------------------------


def test_an_activity_link_alone_gives_its_samples():
    outcome, samples, _ = settle([activity_says("HG00096")])
    assert outcome == ACTIVITY_ONLY and samples is not None
    assert samples["named_by"][0]["source_type"] == SOURCE_REPOSITORY_ACTIVITY


def test_an_activity_link_agreeing_with_the_header_is_listed_after_it_and_tables():
    outcome, samples, _ = settle([activity_says("HG00096"), header("HG00096"), table_says(coriell("HG00096"))])
    assert outcome == AGREED and samples is not None
    assert [a["rule_id"] for a in samples["named_by"]] == [
        HEADER["rule_id"],
        "coriell_hg",
        code_rules.SAMPLES_FROM_ACTIVITY_BIOSAMPLE.id,
    ]


def test_an_activity_link_naming_another_sample_than_the_files_own_is_a_conflict():
    """ANVIL_HPRC's case: a parent's reads, which AnVIL generates from the child's biosample."""
    named = [header("HG01105"), table_says(coriell("HG01105")), activity_says("HG01106")]
    assert settle(named) == (CONFLICT, None, frozenset())


# --- the links -----------------------------------------------------------------------


def link(child_id: str, biosample: str, activity_id: str | None = "a1") -> BiosampleLink:
    rule = code_rules.SAMPLES_FROM_ACTIVITY_BIOSAMPLE.id
    cited = lineage_attribution(SOURCE_REPOSITORY_ACTIVITY, rule, SOURCE, activity_id)
    return BiosampleLink(("file_id", DATASET, child_id), "anvil", biosample, cited)


def carriers(*keys: str) -> dict:
    found: dict = {}
    for key in keys:
        found.setdefault(("file_id", DATASET, key), []).append(Carrier(key, f"{key}.bam", None))
    return found


def linked(links: list[BiosampleLink], found: dict, by_id: dict):
    """``activity_sources`` over ``links`` handed to their children by the lineage pass, as reconcile does."""
    return activity_sources(resolve_lineage(PendingLineage(biosample_links=links), found), by_id)


def test_a_files_links_name_each_biosamples_sample_once_per_activity():
    by_id = {("anvil", "b1"): coriell("HG00096"), ("anvil", "b2"): coriell("HG00097")}
    links = [link("f1", "b1", "a1"), link("f1", "b2", "a1"), link("f1", "b1", "a2")]
    result = linked(links, carriers("f1"), by_id)
    named = result.named["f1"]
    assert named.kind == ACTIVITY and named.members == {coriell("HG00096"), coriell("HG00097")}
    assert [a["activity_id"] for a in named.named_by] == ["a1", "a2"]
    assert result.counts[DATASET] == {TIED: 1}


def test_a_file_one_of_whose_biosamples_ties_to_no_sample_gets_none_and_is_counted():
    links = [link("f1", "b1"), link("f1", "b-unknown")]
    result = linked(links, carriers("f1"), {("anvil", "b1"): coriell("HG00096")})
    assert "f1" not in result.named
    assert result.counts[DATASET] == {UNTIED: 1}
    assert result.untied_examples[DATASET] == ["b-unknown"]


def test_a_link_whose_file_no_record_or_several_carry_gives_nothing():
    found = carriers("dup", "dup")
    result = linked([link("gone", "b1"), link("dup", "b1")], found, {("anvil", "b1"): coriell("HG00096")})
    assert result.named == {}
    assert result.counts[DATASET] == {CHILD_NOT_IN_RUN: 1, CHILD_SEVERAL_MATCH: 1}


def test_a_biosample_id_of_another_repository_does_not_tie():
    result = linked([link("f1", "b1")], carriers("f1"), {("hprc", "b1"): coriell("HG00096")})
    assert result.counts[DATASET] == {UNTIED: 1}


# --- through a run -------------------------------------------------------------------


@pytest.fixture
def table(tmp_path: Path):
    return load(tmp_path, "rows: []\n")


@pytest.fixture
def run(tmp_path: Path) -> Path:
    return tmp_path / "output" / "20261024_000000"


@pytest.fixture
def evidence(roots) -> Path:
    """The slot evidence root (``roots``); the lineage and entity roots are beside it, where reconcile finds them."""
    return roots[0]


def biosample_lines(evidence: Path, *links: tuple[int, str, str]) -> None:
    """One ``anvil_activity`` lineage file: per ``(record, biosample id, activity id)``, the step that generated the record used the biosample."""
    rows = [
        line(
            f"file-{n}",
            biosample,
            parent_column="used_biosample_id",
            key="biosample_id",
            raw_activity="Unknown",
            raw_activity_column="activity_type",
            activity_id=activity_id,
        )
        for n, biosample, activity_id in links
    ]
    write_lineage(evidence.parent / "lineage_evidence", "anvil_activity", rows, dataset=DATASET)


def biosamples(evidence: Path, *ties: tuple[str, str]) -> None:
    """AnVIL's ids for its biosamples, per ``(biosample id, the identifier of the row it was made from)``."""
    write_entity_lines(evidence.parent / "entity_evidence", DATASET, SAMPLE_REPOSITORY_ID, list(ties))


def test_a_run_reads_anvils_links_beside_its_other_sources(tmp_path, run, evidence, table):
    """file-1 has only the link; file-2's header names another sample (a conflict, so its index file-3 inherits
    nothing); file-4's biosample ties to no sample; file-5 has nothing."""
    linked = record(1)
    parental, entry = with_header_samples(record(2), "HG01105")
    bai = child(3, "f2.bam.bai", code_rules.INDEX_BY_NAME, 2, "f2.bam")
    write_bam_run(run, [linked, parental, bai, record(4), record(5)], [entry])
    biosample_lines(evidence, (1, "b-child", "a1"), (2, "b-child", "a1"), (4, "b-unknown", "a2"))
    biosamples(evidence, ("b-child", "HG01106"))
    report = go(run, tmp_path, evidence, table)
    rows = reconciled(run)

    samples = rows["file-1"]["samples"]
    assert samples is not None and samples["count"] == 1
    (attribution,) = samples["named_by"]
    assert attribution == {
        "source_type": SOURCE_REPOSITORY_ACTIVITY,
        "rule_id": code_rules.SAMPLES_FROM_ACTIVITY_BIOSAMPLE.id,
        "source": {**SOURCE.to_dict(), "url": "https://azul.test"},
        "activity_id": "a1",
    }
    for row in rows.values():
        ClassificationRecord(**row)
    assert rows["file-2"]["samples"] is None and rows["file-3"]["samples"] is None
    assert rows["file-4"]["samples"] is None

    block = report[SAMPLES_FIELD]["by_dataset"][DATASET]
    assert block["settled"] == {ACTIVITY_ONLY: 1, CONFLICT: 1, NONE: 3}
    assert block["inheritance"] == {"IndexActivity": {PARENT_CONFLICT: 1}}
    assert block["activity_links"] == {TIED: 2, UNTIED: 1, "untied_examples": ["b-unknown"]}
    # The lines still give no step: the sample input is #701's.
    assert report["lineage"]["sources"][SOURCE_REPOSITORY_ACTIVITY][DATASET][SAMPLE_PARENT] == 3

    (conflict,) = iter_reconciled_artifact(run, SAMPLE_CONFLICTS_FILE)
    assert (conflict["record_key"], conflict["file_name"], conflict["outcome"]) == ("file-2", "f2.bam", CONFLICT)
    assert [(s["kind"], s["samples"]) for s in conflict["sources"]] == [
        ("header", [{"id": "HG01105", "namespace": "coriell"}]),
        (ACTIVITY, [{"id": "HG01106", "namespace": "coriell"}]),
    ]
    without = list(iter_reconciled_artifact(run, FILES_WITHOUT_SAMPLES_FILE))
    assert [r["file_id"] for r in without] == ["file-3", "file-4", "file-5"]
    identity = {"dataset_title", "file_name", "record_key", "entry_id", "file_id", "drs_uri", "data_type"}
    # The index has none because its parent conflicts, and its row names that parent's conflict row.
    assert set(without[0]) == identity | {"parent_conflict"} and without[0]["parent_conflict"] == ["file-2"]
    assert without[0]["record_key"] == "file-3"
    assert set(without[1]) == identity
    # HG01106, which only the activity link names, is reached by file-1.
    assert list(iter_reconciled_artifact(run, UNREACHED_ENTITIES_FILE)) == []


def test_the_conflicts_tsv_has_a_line_per_file_source_and_attribution(tmp_path, run, evidence, table):
    parental, entry = with_header_samples(record(2), "HG01105")
    write_bam_run(run, [parental], [entry])
    biosample_lines(evidence, (2, "b-child", "a1"))
    biosamples(evidence, ("b-child", "HG01106"))
    go(run, tmp_path, evidence, table)
    header_line, *lines = conflict_tsv(iter_reconciled_artifact(run, SAMPLE_CONFLICTS_FILE)).splitlines()
    assert header_line.split("\t") == list(CONFLICT_COLUMNS)
    rows = [dict(zip(CONFLICT_COLUMNS, row.split("\t"), strict=True)) for row in lines]
    by_kind = {row["source_kind"]: row for row in rows}
    assert set(by_kind) == {"header", ACTIVITY}
    assert by_kind["header"]["samples"] == "coriell:HG01105"
    assert by_kind[ACTIVITY] == {
        "dataset": DATASET,
        "record_key": "file-2",
        "file_id": "file-2",
        "file_name": "f2.bam",
        "outcome": CONFLICT,
        "source_kind": ACTIVITY,
        "source_type": SOURCE_REPOSITORY_ACTIVITY,
        "table": "anvil_activity",
        "column": "used_biosample_id",
        "rule_id": code_rules.SAMPLES_FROM_ACTIVITY_BIOSAMPLE.id,
        "activity_id": "a1",
        "samples": "coriell:HG01106",
    }


def test_samples_and_donors_no_file_of_their_dataset_reaches_are_listed(tmp_path, run, evidence, table):
    """HG00096 is reached by a file and through it its donor; HG00097's biosample and HG00098's donor are reached by none."""
    bam, entry = with_header_samples(record(1), "HG00096")
    write_bam_run(run, [bam], [entry])
    biosamples(evidence, ("b1", "HG00096"), ("b2", "HG00097"))
    write_entity_lines(
        evidence.parent / "entity_evidence",
        DATASET,
        "phenotypic_sex",
        [("female", "HG00096"), ("male", "HG00098")],
        source_type=SOURCE_REPOSITORY_METADATA,
    )
    report = go(run, tmp_path, evidence, table)
    rows = list(iter_reconciled_artifact(run, UNREACHED_ENTITIES_FILE))
    assert rows == [
        {"dataset": DATASET, "kind": "sample", "identifier": {"id": "HG00097", "namespace": "coriell"}},
        {"dataset": DATASET, "kind": "donor", "identifier": {"id": "HG00098", "namespace": "coriell"}},
    ]
    assert report["entities"]["unreached"] == {
        DATASET: {
            "sample": {"records": 1, "examples": [{"id": "HG00097", "namespace": "coriell"}]},
            "donor": {"records": 1, "examples": [{"id": "HG00098", "namespace": "coriell"}]},
        }
    }
    markdown = render_markdown(dashboard_data(report, None, run / "report.json"))
    assert "## What no route ties" in markdown
    assert "`coriell:HG00097`" in markdown and "`coriell:HG00098`" in markdown


def test_a_sample_named_only_by_an_identity_link_and_reached_by_no_file_is_listed(tmp_path, run, evidence, table):
    """A ``collected_from`` line is about its sample, as a slot's line is, and names its donor: HG00097 is both, and no
    file reaches either."""
    bam, entry = with_header_samples(record(1), "HG00096")
    write_bam_run(run, [bam], [entry])
    write_entity_lines(
        evidence.parent / "entity_evidence",
        DATASET,
        COLLECTED_FROM,
        [("HG00097", "HG00097")],
        source_type=SOURCE_REPOSITORY_METADATA,
    )
    go(run, tmp_path, evidence, table)
    assert list(iter_reconciled_artifact(run, UNREACHED_ENTITIES_FILE)) == [
        {"dataset": DATASET, "kind": "sample", "identifier": {"id": "HG00097", "namespace": "coriell"}},
        {"dataset": DATASET, "kind": "donor", "identifier": {"id": "HG00097", "namespace": "coriell"}},
    ]


def _conflicted_run(tmp_path, run, evidence, table) -> None:
    parental, entry = with_header_samples(record(2), "HG01105")
    write_bam_run(run, [parental], [entry])
    biosample_lines(evidence, (2, "b-child", "a1"))
    biosamples(evidence, ("b-child", "HG01106"))
    go(run, tmp_path, evidence, table)


def _render(tmp_path: Path, run: Path, tsv: Path) -> int:
    reports = ["--markdown", str(tmp_path / "r.md"), "--html", str(tmp_path / "r.html")]
    return main(["--run-dir", str(run), "--no-previous", *reports, "--conflicts-tsv", str(tsv)])


def test_a_tsv_that_cannot_be_written_fails_the_report(tmp_path, run, evidence, table):
    _conflicted_run(tmp_path, run, evidence, table)
    with pytest.raises(FileNotFoundError):
        _render(tmp_path, run, tmp_path / "missing" / "sample-conflicts.tsv")


def test_a_run_without_the_conflicts_artifact_removes_a_tsv_left_from_another(tmp_path, run, evidence, table):
    _conflicted_run(tmp_path, run, evidence, table)
    tsv = tmp_path / "sample-conflicts.tsv"
    assert _render(tmp_path, run, tsv) == 0 and tsv.read_text().count("\n") == 3
    (run / RECONCILED_DIR / SAMPLE_CONFLICTS_FILE).unlink()  # as a run reconciled before #698
    assert _render(tmp_path, run, tsv) == 0
    assert not tsv.exists()


# --- what the tests above would let through (the no-context review's mutations) -------


def test_a_table_and_an_activity_agreeing_are_agreed():
    outcome, _, _ = settle([table_says(coriell("HG00096")), activity_says("HG00096")])
    assert outcome == AGREED


def test_an_untied_biosample_two_files_name_is_one_example():
    links = [link("f1", "b-unknown"), link("f2", "b-unknown")]
    result = linked(links, carriers("f1", "f2"), {})
    assert result.counts[DATASET] == {UNTIED: 2}
    assert result.untied_examples[DATASET] == ["b-unknown"]


def test_a_submitter_tables_biosample_line_is_no_activity_link(tmp_path, run, evidence, table):
    """Only the repository's record of a step names samples through this rule; a submitter table's sample parent does not."""
    write_bam_run(run, [record(1)], [])
    row = line("file-1", "b-child", parent_column="biosample", key="biosample_id")
    write_lineage(
        evidence.parent / "lineage_evidence",
        "sample",
        [row],
        dataset=DATASET,
        source_type=SOURCE_REPOSITORY_METADATA,
    )
    biosamples(evidence, ("b-child", "HG01106"))
    report = go(run, tmp_path, evidence, table)
    assert reconciled(run)["file-1"]["samples"] is None
    assert report[SAMPLES_FIELD]["by_dataset"][DATASET]["activity_links"] == {}


def test_each_activity_naming_a_file_is_one_attribution_and_one_tsv_line(tmp_path, run, evidence, table):
    """Two steps generating one file from one biosample: one source, cited once per step, a TSV line each."""
    parental, entry = with_header_samples(record(2), "HG01105")
    write_bam_run(run, [parental], [entry])
    biosample_lines(evidence, (2, "b-child", "a1"), (2, "b-child", "a2"))
    biosamples(evidence, ("b-child", "HG01106"))
    go(run, tmp_path, evidence, table)
    (conflict,) = iter_reconciled_artifact(run, SAMPLE_CONFLICTS_FILE)
    (activity,) = [s for s in conflict["sources"] if s["kind"] == ACTIVITY]
    assert [a["activity_id"] for a in activity["named_by"]] == ["a1", "a2"]
    _, *lines = conflict_tsv([conflict]).splitlines()
    rows = [dict(zip(CONFLICT_COLUMNS, row.split("\t"), strict=True)) for row in lines]
    assert [row["activity_id"] for row in rows if row["source_kind"] == ACTIVITY] == ["a1", "a2"]


def test_a_conflict_with_its_parents_samples_lists_the_parent_as_a_source(tmp_path, run, evidence, table):
    """An index takes its BAM's samples; its own activity link names another sample: both are listed."""
    bam, entry = with_header_samples(record(1), "HG00096")
    bai = child(2, "f1.bam.bai", code_rules.INDEX_BY_NAME, 1, "f1.bam")
    write_bam_run(run, [bam, bai], [entry])
    biosample_lines(evidence, (2, "b-other", "a1"))
    biosamples(evidence, ("b-other", "HG00097"))
    go(run, tmp_path, evidence, table)
    (conflict,) = iter_reconciled_artifact(run, SAMPLE_CONFLICTS_FILE)
    assert conflict["record_key"] == "file-2"
    assert [(s["kind"], s["samples"][0]["id"]) for s in conflict["sources"]] == [
        (ACTIVITY, "HG00097"),
        ("parent", "HG00096"),
    ]


def test_a_file_with_no_samples_carries_its_reconciled_data_type(tmp_path, run, evidence, table):
    write_bam_run(run, [record(1, data_type="alignments")], [])
    go(run, tmp_path, evidence, table)
    (row,) = iter_reconciled_artifact(run, FILES_WITHOUT_SAMPLES_FILE)
    assert row["data_type"] == "alignments"


def test_a_donor_reached_through_collected_from_is_not_unreached(tmp_path, run, evidence, table):
    """SRS000707 names no donor by its own id; its collected_from line says HG00099, which its file then reaches."""
    bam, entry = record(1), sample_list([Identifier("sra_sample", "SRS000707")])
    bam["samples"] = reference([Identifier("sra_sample", "SRS000707")], [HEADER])
    write_bam_run(run, [bam], [entry])
    write_entity_lines(
        evidence.parent / "entity_evidence",
        DATASET,
        COLLECTED_FROM,
        [("HG00099", "SRS000707")],
        source_type=SOURCE_REPOSITORY_METADATA,
    )
    go(run, tmp_path, evidence, table)
    assert list(iter_reconciled_artifact(run, UNREACHED_ENTITIES_FILE)) == []


def test_a_sample_only_another_datasets_file_reaches_is_unreached_in_its_own(tmp_path, run, evidence, table):
    """HG00098 and HG00099 are named in DATASET; only a file of another dataset names HG00098."""
    other, entry = with_header_samples(record(1, dataset="AnVIL_OTHER"), "HG00098")
    write_bam_run(run, [other], [entry])
    biosamples(evidence, ("b1", "HG00099"), ("b2", "HG00098"))
    go(run, tmp_path, evidence, table)
    rows = list(iter_reconciled_artifact(run, UNREACHED_ENTITIES_FILE))
    assert [(r["dataset"], r["kind"], r["identifier"]["id"]) for r in rows] == [
        (DATASET, "sample", "HG00098"),
        (DATASET, "sample", "HG00099"),
    ]


def test_a_parent_a_table_names_whom_no_file_reaches_is_an_unreached_donor(tmp_path, run, evidence, table):
    """ANVIL_HPRC's case: a child's row names its mother, whose reads are in conflict, so no file reaches her."""
    bam, entry = with_header_samples(record(1), "HG00096")
    write_bam_run(run, [bam], [entry])
    write_entity_lines(
        evidence.parent / "entity_evidence",
        DATASET,
        "mother",
        [("HG00095", "HG00096")],
        source_type=SOURCE_REPOSITORY_METADATA,
    )
    go(run, tmp_path, evidence, table)
    assert list(iter_reconciled_artifact(run, UNREACHED_ENTITIES_FILE)) == [
        {"dataset": DATASET, "kind": "donor", "identifier": {"id": "HG00095", "namespace": "coriell"}},
    ]


def test_two_files_of_one_name_and_no_file_id_are_told_apart_in_the_tsv_by_record_key():
    """HPRC's records carry no file_id; their record key, the md5, is what tells two same-named files apart."""
    source = {
        "kind": "header",
        "named_by": [{"source_type": "content_read", "rule_id": code_rules.BAM_READ_GROUP_SAMPLES.id}],
        "samples": [{"id": "HG00096", "namespace": "coriell"}],
    }
    conflicts = [
        {
            "dataset_title": None,
            "file_name": "reads.bam",
            "record_key": md5,
            "file_id": None,
            "outcome": CONFLICT,
            "sources": [source],
        }
        for md5 in ("md5-a", "md5-b")
    ]
    _, *lines = conflict_tsv(conflicts).splitlines()
    rows = [dict(zip(CONFLICT_COLUMNS, line.split("\t"), strict=True)) for line in lines]
    assert [(row["record_key"], row["file_id"], row["file_name"]) for row in rows] == [
        ("md5-a", "", "reads.bam"),
        ("md5-b", "", "reads.bam"),
    ]
