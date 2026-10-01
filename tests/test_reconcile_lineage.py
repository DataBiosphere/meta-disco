"""Reconcile's lineage pass (#577): each file's ``generated_by`` from the imported lineage.

One test per acceptance criterion a fixture can check, numbered ``ac<N>`` in its name;
the real-run examples (a T2T_CHRY ``.tbi``, ``HG01536.samtools.stats.txt``,
``IGVFFI3781KRJF.bai``) are on the pull request. Fixtures are a few output rows written
through ``run_fixtures.write_run``, lineage files written through ``write_lineage_file``
into the generation layout beside the slot evidence root, and an activity map written in
each test, so reconcile reads them the way it reads a real run and a real import.
"""

from pathlib import Path

import pytest

from meta_disco.activity_map import load_activity_map
from meta_disco.models import SOURCE_REPOSITORY_ACTIVITY, SOURCE_REPOSITORY_METADATA
from meta_disco.output_utils import iter_reconciled_records
from meta_disco.reconcile import reconcile_run
from meta_disco.schema.classification_model import ClassificationRecord
from tests.lineage_fixtures import activity_line, line, write_lineage
from tests.metadata_fixtures import write_metadata
from tests.run_fixtures import output_record, write_run

DATASET = "D"

ACTIVITY_MAP = """
rows:
  - id: activity.indexing
    match: {source_type: repository_activity, table: anvil_activity, raw_activity: Indexing, parent_column: used_file_id}
    declares: {activity: IndexActivity, role: indexed}
    reason: An index of the file it used.
  - id: activity.qc
    match: {source_type: repository_metadata, table: sample, child_column: stats, parent_column: cram}
    declares: {activity: QualityControlActivity, role: reported_on}
    reason: A report on the row's CRAM.
  - id: activity.align
    match: {source_type: repository_metadata, table: sample, child_column: cram, parent_column: [r1, r2]}
    declares: {activity: AlignmentActivity, role: reads}
    reason: The row's FASTQs aligned.
"""

NAME = {"source_type": "filename_rule", "rule_id": "index_by_name"}


def rec(n: int, name: str, data_type: str | None = None, generated_by: dict | None = None) -> dict:
    row = output_record(name, f"md5-{n}", dataset=DATASET, file_id=f"file-{n}", data_type=data_type)
    row["drs_uri"] = drs(n)
    row["generated_by"] = generated_by
    return row


def name_edge(parent: int, parent_file: str) -> dict:
    """The step inference writes from an index's name (``edges.generated_by``)."""
    return {
        "activity": "IndexActivity",
        "named_by": [NAME],
        "inputs": [
            {
                "role": "indexed",
                "parent_file": parent_file,
                "parent_key": f"file-{parent}",
                "parent_kind": "variants",
                "named_by": [NAME],
            }
        ],
    }


@pytest.fixture
def roots(tmp_path: Path):
    """The slot evidence root and the lineage root beside it, as reconcile finds them by default."""
    evidence = tmp_path / "data" / "source_evidence"
    evidence.mkdir(parents=True)
    return evidence, tmp_path / "data" / "lineage_evidence"


def go(tmp_path: Path, rows: list[dict] | None, evidence: Path | None) -> tuple[dict[str, dict], dict]:
    """Reconcile a run of ``rows`` (or the run already written, for None) with the test's activity map."""
    run_dir = tmp_path / "output" / "20261001_000000"
    if rows is not None:
        write_run(run_dir, rows)
    table = tmp_path / "activity_map.yaml"
    table.write_text(ACTIVITY_MAP)
    metadata = write_metadata(tmp_path / "input.json", [], repository="anvil", catalog="anvil15")
    report = reconcile_run(run_dir, metadata, evidence, activity_table=load_activity_map(table))
    return {r["file_name"]: r for r in iter_reconciled_records(run_dir)}, report


def activity_lines(lineage: Path, *lines) -> None:
    write_lineage(lineage, "anvil_activity", list(lines), dataset=DATASET)


def sample_lines(lineage: Path, *lines) -> None:
    write_lineage(
        lineage, "sample", list(lines), dataset=DATASET, source_type=SOURCE_REPOSITORY_METADATA, key="drs_uri"
    )


def drs(n: int) -> str:
    return f"drs://drs.anv0:v2_{n}"


def sample_line(child: int, parent: int, child_column: str, parent_column: str):
    return line(drs(child), drs(parent), child_column, parent_column, "drs_uri")


# --- acceptance ---------------------------------------------------------------------


def test_ac1_an_index_inference_declined_gets_its_step_from_anvil_activity(tmp_path, roots):
    evidence, lineage = roots
    activity_lines(lineage, activity_line("file-2", "file-1", "Indexing"))
    rows, report = go(tmp_path, [rec(1, "a.vcf.gz", "variants"), rec(2, "a.vcf.gz.tbi", "index")], evidence)
    step = rows["a.vcf.gz.tbi"]["generated_by"]
    assert step["activity"] == "IndexActivity"
    (used,) = step["inputs"]
    assert (used["role"], used["parent_key"], used["parent_file"], used["parent_kind"]) == (
        "indexed",
        "file-1",
        "a.vcf.gz",
        "variants",
    )
    (by,) = used["named_by"]
    assert by["source_type"] == SOURCE_REPOSITORY_ACTIVITY and by["rule_id"] == "activity.indexing"
    assert {k: by["source"][k] for k in ("name", "dataset", "table", "column")} == {
        "name": "anvil",
        "dataset": DATASET,
        "table": "anvil_activity",
        "column": "used_file_id",
    }
    counts = report["lineage"]["sources"][SOURCE_REPOSITORY_ACTIVITY][DATASET]
    assert (counts["offered"], counts["resolved"]) == (1, 1)


def test_ac2_each_qc_file_gets_the_cram_on_its_own_row(tmp_path, roots):
    evidence, lineage = roots
    sample_lines(lineage, sample_line(3, 1, "stats", "cram"), sample_line(4, 2, "stats", "cram"))
    rows, _ = go(
        tmp_path,
        [
            rec(1, "s.GRCh38.cram", "alignments"),
            rec(2, "s.CHM13.cram", "alignments"),
            rec(3, "s.GRCh38.stats.txt", "qc_report"),
            rec(4, "s.CHM13.stats.txt", "qc_report"),
        ],
        evidence,
    )
    for child, parent in (("s.GRCh38.stats.txt", "file-1"), ("s.CHM13.stats.txt", "file-2")):
        step = rows[child]["generated_by"]
        assert step["activity"] == "QualityControlActivity"
        assert [(i["role"], i["parent_key"]) for i in step["inputs"]] == [("reported_on", parent)]


def test_ac3_an_alignment_takes_every_fastq_on_its_row_as_reads(tmp_path, roots):
    evidence, lineage = roots
    sample_lines(lineage, sample_line(3, 1, "cram", "r1"), sample_line(3, 2, "cram", "r2"))
    rows, report = go(
        tmp_path,
        [rec(1, "s_1.fastq.gz", "reads"), rec(2, "s_2.fastq.gz", "reads"), rec(3, "s.cram", "alignments")],
        evidence,
    )
    step = rows["s.cram"]["generated_by"]
    assert step["activity"] == "AlignmentActivity"
    assert [(i["role"], i["parent_key"]) for i in step["inputs"]] == [("reads", "file-1"), ("reads", "file-2")]
    # No source names the reference an alignment used: flagged, and the step is still written.
    assert {(m["activity"], m["problem"], m["detail"], m["files"]) for m in report["lineage"]["misfits"]} == {
        ("AlignmentActivity", "required role missing", "reference", 1)
    }


def test_ac4_a_name_and_a_table_naming_one_parent_give_one_input_with_both(tmp_path, roots):
    evidence, lineage = roots
    activity_lines(lineage, activity_line("file-2", "file-1", "Indexing"))
    rows, report = go(
        tmp_path,
        [rec(1, "a.vcf.gz", "variants"), rec(2, "a.vcf.gz.tbi", "index", name_edge(1, "a.vcf.gz"))],
        evidence,
    )
    (used,) = rows["a.vcf.gz.tbi"]["generated_by"]["inputs"]
    assert [n["source_type"] for n in used["named_by"]] == ["filename_rule", SOURCE_REPOSITORY_ACTIVITY]
    assert report["lineage"]["steps"][DATASET] == {f"filename_rule+{SOURCE_REPOSITORY_ACTIVITY}": 1}


def test_ac4_a_name_and_a_table_naming_different_parents_are_an_edge_conflict(tmp_path, roots):
    evidence, lineage = roots
    activity_lines(lineage, activity_line("file-3", "file-2", "Indexing"))
    rows, report = go(
        tmp_path,
        [
            rec(1, "a.vcf.gz", "variants"),
            rec(2, "b.vcf.gz", "variants"),
            rec(3, "a.vcf.gz.tbi", "index", name_edge(1, "a.vcf.gz")),
        ],
        evidence,
    )
    assert rows["a.vcf.gz.tbi"]["generated_by"] is None
    conflict = report["lineage"]["conflicts"][DATASET]["edge"]
    assert conflict["files"] == 1
    (example,) = conflict["examples"]
    assert example["file_name"] == "a.vcf.gz.tbi" and example["role"] == "indexed"
    assert [(s["said"], s["by"]["source_type"]) for s in example["said"]] == [
        ("a.vcf.gz", "filename_rule"),
        ("b.vcf.gz", SOURCE_REPOSITORY_ACTIVITY),
    ]


def test_ac5_inference_output_is_untouched(tmp_path, roots):
    evidence, lineage = roots
    activity_lines(lineage, activity_line("file-2", "file-1", "Indexing"))
    run_dir = write_run(tmp_path / "output" / "20261001_000000", [rec(1, "a.vcf.gz"), rec(2, "a.vcf.gz.tbi")])
    before = {p.name: p.read_bytes() for p in run_dir.glob("*.json")}
    rows, _ = go(tmp_path, None, evidence)
    assert rows["a.vcf.gz.tbi"]["generated_by"] is not None
    assert {p.name: p.read_bytes() for p in run_dir.glob("*.json")} == before


# --- what gives no step --------------------------------------------------------------


def test_lines_that_give_no_step_are_counted_by_why(tmp_path, roots):
    evidence, lineage = roots
    activity_lines(
        lineage,
        activity_line("file-2", "file-9", "Indexing"),  # the parent is no file of the run
        line(
            "file-2",
            "S1",
            parent_column="used_biosample_id",
            key="biosample_id",
            raw_activity="Sequencing",
            raw_activity_column="activity_type",
        ),  # a sample parent, out of scope (#582)
        activity_line("file-2", "file-1", "Unknown"),  # no authored row
        activity_line("file-8", "file-1", "Indexing"),  # the child is no file of the run
    )
    rows, report = go(tmp_path, [rec(1, "a.vcf.gz"), rec(2, "a.vcf.gz.tbi")], evidence)
    assert rows["a.vcf.gz.tbi"]["generated_by"] is None
    assert report["lineage"]["sources"][SOURCE_REPOSITORY_ACTIVITY][DATASET] == {
        "offered": 4,
        "not_in_dataset": 1,
        "sample_parent": 1,
        "untranslated": 1,
        "child_not_in_run": 1,
    }


def test_a_parent_two_files_of_the_dataset_carry_is_several_match(tmp_path, roots):
    evidence, lineage = roots
    sample_lines(lineage, sample_line(3, 1, "stats", "cram"))
    twin = rec(2, "other.cram")
    twin["drs_uri"] = drs(1)
    rows, report = go(tmp_path, [rec(1, "s.cram"), twin, rec(3, "s.stats.txt")], evidence)
    assert rows["s.stats.txt"]["generated_by"] is None
    assert report["lineage"]["sources"][SOURCE_REPOSITORY_METADATA][DATASET]["several_match"] == 1


def test_without_evidence_no_lineage_is_read_and_inferences_step_stands(tmp_path, roots):
    _, lineage = roots
    activity_lines(lineage, activity_line("file-3", "file-2", "Indexing"))
    edge = name_edge(1, "a.vcf.gz")
    rows, report = go(tmp_path, [rec(1, "a.vcf.gz"), rec(2, "b.vcf.gz"), rec(3, "a.vcf.gz.tbi", "index", edge)], None)
    assert rows["a.vcf.gz.tbi"]["generated_by"] == edge
    assert report["lineage"]["sources"] == {}


def test_a_record_no_lineage_names_keeps_inferences_step_byte_for_byte(tmp_path, roots):
    evidence, lineage = roots
    activity_lines(lineage, activity_line("file-2", "file-1", "Indexing"))
    edge = name_edge(3, "c.vcf.gz")
    rows, _ = go(
        tmp_path,
        [rec(1, "a.vcf.gz"), rec(2, "a.vcf.gz.tbi"), rec(3, "c.vcf.gz"), rec(4, "c.vcf.gz.tbi", "index", edge)],
        evidence,
    )
    assert rows["c.vcf.gz.tbi"]["generated_by"] == edge


def test_a_reconciled_record_with_a_lineage_step_validates_against_the_schema(tmp_path, roots):
    evidence, lineage = roots
    activity_lines(lineage, activity_line("file-2", "file-1", "Indexing"))
    rows, _ = go(tmp_path, [rec(1, "a.vcf.gz", "variants"), rec(2, "a.vcf.gz.tbi", "index")], evidence)
    ClassificationRecord.model_validate(rows["a.vcf.gz.tbi"])


def test_the_artifact_names_the_activity_map_and_the_lineage_files_it_read(tmp_path, roots):
    evidence, lineage = roots
    activity_lines(lineage, activity_line("file-2", "file-1", "Indexing"))
    _, report = go(tmp_path, [rec(1, "a.vcf.gz"), rec(2, "a.vcf.gz.tbi")], evidence)
    assert report["activity_map_sha256"]
    assert report["lineage_files"] == ["anvil/anvil15/D/20260930T062532Z/anvil_activity.ndjson"]


def test_a_parent_that_is_the_child_and_a_child_two_records_carry_give_no_step(tmp_path, roots):
    evidence, lineage = roots
    sample_lines(lineage, sample_line(1, 1, "stats", "cram"), sample_line(2, 3, "stats", "cram"))
    twin = rec(4, "twin.stats.txt")
    twin["drs_uri"] = drs(2)
    rows, report = go(tmp_path, [rec(1, "s.cram"), rec(2, "s.stats.txt"), rec(3, "t.cram"), twin], evidence)
    assert all(r["generated_by"] is None for r in rows.values())
    counts = report["lineage"]["sources"][SOURCE_REPOSITORY_METADATA][DATASET]
    assert (counts["parent_is_child"], counts["child_several_match"]) == (1, 1)
