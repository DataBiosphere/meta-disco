"""Inheritance across each file's ``generated_by`` at reconcile (contract 4.9, #571).

The parents' rule is tested on :func:`reconcile_inherit.settle_parents` directly; the rest
through ``reconcile_run`` over a few output rows (``run_fixtures.write_run``), with lineage
written into the generation layout beside the slot evidence root and an activity map
written here, so reconcile reads them as it reads a real run. Tests named ``ac_*`` are the
issue's acceptance cases in miniature; the real-run counts are on the pull request.
"""

from pathlib import Path
from typing import Any

import pytest

from meta_disco import activities, code_rules, edges
from meta_disco.models import (
    CLASSIFIED,
    CONFLICT,
    MIXED,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_DERIVATION_INHERITANCE,
    build_field_entry,
)
from meta_disco.pipeline import SOURCE_RECORD_KEYS
from meta_disco.reconcile import INHERITED, ReconcileError, reconcile_run
from meta_disco.reconcile_inherit import (
    DECLARED,
    PARENT_CONFLICT,
    PARENT_NOT_CLASSIFIED,
    PARENT_NOT_IN_RUN,
    Answer,
    settle_parents,
)
from meta_disco.rule_engine import make_claim
from meta_disco.schema.classification_model import ClassificationRecord
from tests.lineage_fixtures import drs, reconcile_fixture, sample_line, sample_lines
from tests.run_fixtures import output_record

DATASET = "D"

ACTIVITY_MAP = """
rows:
  - id: activity.qc
    match: {source_type: repository_metadata, table: sample, child_column: stats, parent_column: cram}
    declares: {activity: QualityControlActivity, role: reported_on}
    reason: A report on the row's CRAM.
  - id: activity.align
    match: {source_type: repository_metadata, table: sample, child_column: cram, parent_column: [r1, r2]}
    declares: {activity: AlignmentActivity, role: reads}
    reason: The row's FASTQs aligned.
  - id: activity.call
    match: {source_type: repository_metadata, table: sample, child_column: vcf, parent_column: cram}
    declares: {activity: VariantCallActivity, role: calls_from}
    reason: The row's VCF called from its CRAM.
"""

CARRIED = activities.carried()


def rec(n: int, name: str, generated_by: dict | None = None, build: dict | None = None, **dims: str) -> dict:
    row = output_record(name, f"md5-{n}", dataset=DATASET, file_id=f"file-{n}", **dims)
    row["drs_uri"] = drs(n)
    row["generated_by"] = generated_by
    if build is not None:
        row["classifications"]["reference_assembly"] = build_field_entry(
            dims["reference_assembly"], detail={"build": build}
        )
    return row


def index_of(parent: int, parent_file: str) -> dict:
    """The step inference writes from an index's name, as ``edges.generated_by`` writes it."""
    return edges.generated_by(
        code_rules.INDEX_BY_NAME, {"file_name": parent_file, "file_id": f"file-{parent}"}, SOURCE_RECORD_KEYS["anvil"]
    )


def go(tmp_path: Path, rows: list[dict], evidence: Path | None) -> tuple[dict[str, dict], dict]:
    return reconcile_fixture(tmp_path, rows, evidence, ACTIVITY_MAP)


def slot(row: dict, name: str) -> dict:
    return row["classifications"][name]


def inherited_claims(entry: dict) -> list[dict]:
    return [e for e in entry["evidence"] if e.get("source_type") == SOURCE_DERIVATION_INHERITANCE]


# --- how the parents in one role settle ----------------------------------------------


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        pytest.param([(CLASSIFIED, "genomic")], (DECLARED, "genomic"), id="one parent declares its value"),
        pytest.param([(CLASSIFIED, "genomic"), (CLASSIFIED, "genomic")], (DECLARED, "genomic"), id="agreeing parents"),
        pytest.param([(NOT_APPLICABLE, None)], (DECLARED, NOT_APPLICABLE), id="not_applicable passes as itself"),
        pytest.param(
            [(CLASSIFIED, "genomic"), (CLASSIFIED, "transcriptomic")], (MIXED, MIXED), id="differing parents are mixed"
        ),
        pytest.param(
            [(CLASSIFIED, "genomic"), (NOT_APPLICABLE, None)], (MIXED, MIXED), id="a value beside not_applicable"
        ),
        pytest.param([(MIXED, None), (CLASSIFIED, "genomic")], (MIXED, MIXED), id="a mixed parent is mixed"),
        pytest.param(
            [(CLASSIFIED, "genomic"), (CLASSIFIED, "transcriptomic"), (CONFLICT, None)],
            (MIXED, MIXED),
            id="known to differ beats a conflicted one",
        ),
        pytest.param([(CONFLICT, None)], (PARENT_CONFLICT, None), id="a conflicted parent passes nothing"),
        pytest.param(
            [(CLASSIFIED, "genomic"), (NOT_CLASSIFIED, None)],
            (PARENT_NOT_CLASSIFIED, None),
            id="an unknown parent cannot be known to agree",
        ),
        pytest.param([(CLASSIFIED, "genomic"), None], (PARENT_NOT_IN_RUN, None), id="a parent the run lacks"),
    ],
)
def test_how_the_parents_in_one_role_settle(answers, expected):
    assert settle_parents("data_modality", answers) == expected


def test_parents_that_nest_declare_the_deepest():
    """CHM13 and T2T-CHM13v2.0 are one answer at two depths (4.4, #473)."""
    answers: list[Answer | None] = [(CLASSIFIED, "CHM13"), (CLASSIFIED, "T2T-CHM13v2.0")]
    assert settle_parents("reference_assembly", answers) == (DECLARED, "T2T-CHM13v2.0")


# --- acceptance ------------------------------------------------------------------------


def test_ac_a_qc_report_takes_its_crams_modality_credited_as_inherited(tmp_path, roots):
    evidence, lineage = roots
    sample_lines(lineage, sample_line(2, 1, "stats", "cram"))
    rows, report = go(
        tmp_path,
        [
            rec(1, "HG01536.cram", data_modality="genomic", data_type="alignments"),
            rec(2, "HG01536.samtools.stats.txt", data_type="qc_report"),
        ],
        evidence,
    )
    entry = slot(rows["HG01536.samtools.stats.txt"], "data_modality")
    assert (entry["status"], entry["value"], entry["credited_to"], entry["use"]) == (
        CLASSIFIED,
        "genomic",
        INHERITED,
        "meta_disco",
    )
    (claim,) = inherited_claims(entry)
    assert (claim["value"], claim["activity"], claim["parent_role"], claim["parent_keys"]) == (
        "genomic",
        "QualityControlActivity",
        "reported_on",
        ["file-1"],
    )
    assert claim["rule_id"] == "inherited_from_parent"
    assert report["slots"][DATASET]["data_modality"][INHERITED] == 1
    assert report["inheritance"][DATASET]["data_modality"][DECLARED] == 1


def test_ac_each_qc_report_inherits_from_the_cram_on_its_own_row(tmp_path, roots):
    evidence, lineage = roots
    sample_lines(lineage, sample_line(3, 1, "stats", "cram"), sample_line(4, 2, "stats", "cram"))
    rows, _ = go(
        tmp_path,
        [
            rec(1, "s.GRCh38.cram", reference_assembly="GRCh38"),
            rec(2, "s.CHM13.cram", reference_assembly="T2T-CHM13v2.0"),
            rec(3, "s.GRCh38.stats.txt"),
            rec(4, "s.CHM13.stats.txt"),
        ],
        evidence,
    )
    assert slot(rows["s.GRCh38.stats.txt"], "reference_assembly")["value"] == "GRCh38"
    assert slot(rows["s.CHM13.stats.txt"], "reference_assembly")["value"] == "T2T-CHM13v2.0"


def test_ac_a_tbi_takes_platform_from_its_vcf_which_takes_it_from_its_cram(tmp_path, roots):
    """Two hops, parents first, whatever order the run's files come in."""
    evidence, lineage = roots
    sample_lines(lineage, sample_line(2, 1, "vcf", "cram"))
    rows, report = go(
        tmp_path,
        [
            # The `.tbi` first: inheritance must settle its VCF, and the VCF's CRAM, before it.
            rec(3, "s.chr17.hc.vcf.gz.tbi", generated_by=index_of(2, "s.chr17.hc.vcf.gz"), data_type="index"),
            rec(2, "s.chr17.hc.vcf.gz", data_modality="genomic", data_type="variants"),
            rec(1, "s.cram", data_modality="genomic", platform="ILLUMINA", data_type="alignments"),
        ],
        evidence,
    )
    for name in ("s.chr17.hc.vcf.gz", "s.chr17.hc.vcf.gz.tbi"):
        entry = slot(rows[name], "platform")
        assert (entry["value"], entry["credited_to"]) == ("ILLUMINA", INHERITED), name
    # The VCF's own modality agrees with its CRAM's, so it stays inference's.
    assert slot(rows["s.chr17.hc.vcf.gz"], "data_modality")["credited_to"] == "filled_by_inference"
    assert report["inheritance"][DATASET]["platform"][DECLARED] == 2


def test_ac_an_alignment_takes_its_reads_and_its_index_takes_them_on_the_second_hop(tmp_path, roots):
    """The IGVF `.bai` -> BAM -> FASTQs case (#573): the reads pass all but the reference."""
    evidence, lineage = roots
    sample_lines(lineage, sample_line(3, 1, "cram", "r1"), sample_line(3, 2, "cram", "r2"))
    reads = {"data_modality": "epigenomic.chromatin_accessibility", "assay_type": "snATAC-seq"}
    fastq = {"data_type": "reads", "reference_assembly": NOT_APPLICABLE, **reads}
    rows, report = go(
        tmp_path,
        [
            rec(1, "r1.fastq.gz", None, None, **fastq),
            rec(2, "r2.fastq.gz", None, None, **fastq),
            rec(3, "s.bam", data_type="alignments"),
            rec(4, "s.bam.bai", generated_by=index_of(3, "s.bam"), data_type="index"),
        ],
        evidence,
    )
    for name in ("s.bam", "s.bam.bai"):
        for dimension, value in reads.items():
            assert slot(rows[name], dimension)["value"] == value, (name, dimension)
        # The reads' reference does not pass: `reference` is the role that would, and no
        # source names one, so the alignment's reference stays its own.
        assert slot(rows[name], "reference_assembly")["status"] == NOT_CLASSIFIED, name
    assert report["inheritance"][DATASET]["reference_assembly"] == {PARENT_NOT_CLASSIFIED: 1}


def test_ac_a_parent_not_classified_leaves_the_child_not_classified(tmp_path):
    rows, report = go(
        tmp_path,
        [rec(1, "s.bam"), rec(2, "s.bam.bai", generated_by=index_of(1, "s.bam"), data_type="index")],
        None,
    )
    for dimension in CARRIED:
        entry = slot(rows["s.bam.bai"], dimension)
        assert entry["status"] == NOT_CLASSIFIED and not inherited_claims(entry), dimension
    assert report["inheritance"][DATASET]["platform"] == {PARENT_NOT_CLASSIFIED: 1}


def test_a_parent_in_conflict_passes_nothing(tmp_path):
    """Decided for #571: the conflict stays on the parent and is not repeated on its index."""
    rows, report = go(
        tmp_path,
        [
            rec(1, "s.bam", reference_assembly=CONFLICT, data_modality="genomic"),
            rec(2, "s.bam.bai", generated_by=index_of(1, "s.bam"), data_type="index"),
        ],
        None,
    )
    assert slot(rows["s.bam.bai"], "reference_assembly")["status"] == NOT_CLASSIFIED
    assert slot(rows["s.bam.bai"], "data_modality")["value"] == "genomic"
    assert report["inheritance"][DATASET]["reference_assembly"] == {PARENT_CONFLICT: 1}


def test_reads_that_disagree_give_mixed_and_mixed_passes_on(tmp_path, roots):
    evidence, lineage = roots
    sample_lines(lineage, sample_line(3, 1, "cram", "r1"), sample_line(3, 2, "cram", "r2"))
    rows, report = go(
        tmp_path,
        [
            rec(1, "r1.fastq.gz", platform="ILLUMINA"),
            rec(2, "r2.fastq.gz", platform="PACBIO"),
            rec(3, "s.bam"),
            rec(4, "s.bam.bai", generated_by=index_of(3, "s.bam")),
        ],
        evidence,
    )
    for name in ("s.bam", "s.bam.bai"):
        entry = slot(rows[name], "platform")
        assert (entry["status"], entry["credited_to"]) == (NOT_CLASSIFIED, NOT_CLASSIFIED), name
        (claim,) = inherited_claims(entry)
        assert claim["claim_state"] == MIXED, name
    assert report["inheritance"][DATASET]["platform"] == {MIXED: 2}


def test_mixed_against_the_childs_own_value_is_a_conflict(tmp_path, roots):
    evidence, lineage = roots
    sample_lines(lineage, sample_line(3, 1, "cram", "r1"), sample_line(3, 2, "cram", "r2"))
    rows, report = go(
        tmp_path,
        [
            rec(1, "r1.fastq.gz", platform="ILLUMINA"),
            rec(2, "r2.fastq.gz", platform="PACBIO"),
            rec(3, "s.bam", platform="ILLUMINA"),
        ],
        evidence,
    )
    assert slot(rows["s.bam"], "platform")["status"] == CONFLICT
    (listed,) = report["conflicts"][DATASET]["platform"]["conflict_sources"]
    assert listed["inputs"] == {"derivation_inheritance": ["mixed"], "inference": ["ILLUMINA"]}


def test_an_inherited_value_against_the_childs_own_is_a_conflict_listed_with_both(tmp_path):
    rows, report = go(
        tmp_path,
        [
            rec(1, "s.bam", data_modality="genomic"),
            rec(2, "s.bam.bai", generated_by=index_of(1, "s.bam"), data_modality="transcriptomic"),
        ],
        None,
    )
    entry = slot(rows["s.bam.bai"], "data_modality")
    assert (entry["status"], entry["credited_to"]) == (CONFLICT, "conflict_sources")
    (listed,) = report["conflicts"][DATASET]["data_modality"]["conflict_sources"]
    assert listed["inputs"] == {"derivation_inheritance": ["genomic"], "inference": ["transcriptomic"]}
    # The report scores inference against the inherited value too, so it agrees with the slot.
    assert report["inputs"][DATASET]["data_modality"]["inference"] == {"added": 1, "disagreed": 1}


def test_an_inherited_reference_carries_the_parents_build_base_and_version_only(tmp_path):
    build = {"base": "GRCh38", "version": "p14", "chr1_m5": "6aef897c3d6ff0c78aff06ac189178dd", "name": "hg38.fa"}
    rows, _ = go(
        tmp_path,
        [
            rec(1, "s.bam", reference_assembly="GRCh38", build=build),
            rec(2, "s.bam.bai", generated_by=index_of(1, "s.bam")),
        ],
        None,
    )
    entry = slot(rows["s.bam.bai"], "reference_assembly")
    assert (entry["value"], entry["build"]) == ("GRCh38", {"base": "GRCh38", "version": "p14"})


def test_without_evidence_inheritance_still_crosses_the_steps_inference_wrote(tmp_path):
    """Contract 6.6: a run with no inputs but inference concludes what inheritance carries too."""
    rows, report = go(
        tmp_path,
        [rec(1, "s.bam", platform="ILLUMINA"), rec(2, "s.bam.bai", generated_by=index_of(1, "s.bam"))],
        None,
    )
    assert report["evidence_excluded"]
    assert slot(rows["s.bam.bai"], "platform")["value"] == "ILLUMINA"


def test_a_cycle_through_the_steps_is_refused(tmp_path):
    with pytest.raises(ReconcileError, match=r"file-1 -> file-2 -> file-1|file-2 -> file-1 -> file-2"):
        go(
            tmp_path,
            [
                rec(1, "a.bai", generated_by=index_of(2, "b.bai")),
                rec(2, "b.bai", generated_by=index_of(1, "a.bai")),
            ],
            None,
        )


def test_a_reconciled_record_with_inherited_and_mixed_claims_validates_against_the_schema(tmp_path, roots):
    evidence, lineage = roots
    sample_lines(lineage, sample_line(3, 1, "cram", "r1"), sample_line(3, 2, "cram", "r2"))
    rows, _ = go(
        tmp_path,
        [
            rec(1, "r1.fastq.gz", platform="ILLUMINA", data_modality="genomic"),
            rec(2, "r2.fastq.gz", platform="PACBIO", data_modality="genomic"),
            rec(3, "s.bam"),
        ],
        evidence,
    )
    ClassificationRecord.model_validate(rows["s.bam"])


# --- the claim's invariants --------------------------------------------------------------


def _inherited(**overrides: Any) -> dict:
    kwargs: dict[str, Any] = {
        "source_type": SOURCE_DERIVATION_INHERITANCE,
        "rule_id": "inherited_from_parent",
        "reason": "test",
        "value": "genomic",
        "activity": "IndexActivity",
        "parent_role": "indexed",
        "parent_keys": ["file-1"],
    }
    return make_claim(**{**kwargs, **overrides})


def test_an_inherited_claim_names_its_step_and_carries_no_tier():
    claim = _inherited()
    assert "tier" not in claim
    assert (claim["activity"], claim["parent_role"], claim["parent_keys"]) == ("IndexActivity", "indexed", ["file-1"])


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"parent_keys": []}, id="no parents"),
        pytest.param({"parent_keys": None}, id="parents missing"),
        pytest.param({"activity": None}, id="no activity"),
        pytest.param({"parent_role": ""}, id="no role"),
        pytest.param({"tier": 1}, id="a tier"),
        pytest.param({"value": None, "status": "not_classified"}, id="not_classified is no inheritance"),
        pytest.param({"value": None, "state": "unmapped"}, id="a state other than mixed"),
    ],
)
def test_an_inherited_claim_that_does_not_name_its_step_is_refused(overrides):
    with pytest.raises(ValueError):
        _inherited(**overrides)


def test_only_an_inherited_claim_may_name_a_step_or_be_mixed():
    with pytest.raises(ValueError, match="only an inherited"):
        make_claim(source_type="filename_rule", rule_id="r", reason="x", tier=1, value="genomic", activity="Activity")
    with pytest.raises(ValueError, match="only an inherited claim may"):
        make_claim(source_type="filename_rule", rule_id="r", reason="x", state=MIXED)


def test_two_roles_that_agree_are_not_mixed_in_either_pass():
    """Both passes weigh one inherited value from each of two roles as that value (no activity does this yet)."""
    from meta_disco.reconcile import _Graph, reconcile_record
    from meta_disco.reconcile_inherit import Inherited

    graph = _Graph()
    row = rec(1, "s.bam")
    graph.add("file-1", row, {}, index_of(2, "p.bam"))
    passed = [Inherited("IndexActivity", role, ("file-2",), "genomic") for role in ("indexed", "other")]
    assert graph.resolve("file-1", "data_modality", passed) == (CLASSIFIED, "genomic")
    written = reconcile_record(row, {}, {"data_modality": passed})
    assert slot(written, "data_modality")["value"] == "genomic"


def test_a_file_passes_on_only_the_build_its_record_shows(tmp_path, roots):
    """A VCF whose own GRCh38 has no build passes none to its `.tbi`, though its CRAM has one."""
    evidence, lineage = roots
    sample_lines(lineage, sample_line(2, 1, "vcf", "cram"))
    build = {"base": "GRCh38", "version": "p14"}
    rows, _ = go(
        tmp_path,
        [
            rec(1, "s.cram", reference_assembly="GRCh38", build=build),
            rec(2, "s.vcf.gz", reference_assembly="GRCh38"),
            rec(3, "s.vcf.gz.tbi", generated_by=index_of(2, "s.vcf.gz")),
        ],
        evidence,
    )
    assert "build" not in slot(rows["s.vcf.gz"], "reference_assembly")
    entry = slot(rows["s.vcf.gz.tbi"], "reference_assembly")
    assert (entry["value"], entry["credited_to"]) == ("GRCh38", INHERITED)
    assert "build" not in entry


def test_a_parent_build_with_no_base_or_version_passes_no_build(tmp_path):
    """Header observations alone are the parent's own: a child gets no `build` block for them."""
    observed = {"base": None, "version": None, "name": "chm13.draft_v1.0.fasta"}
    rows, _ = go(
        tmp_path,
        [
            rec(1, "s.bam", reference_assembly="GRCh38", build=observed),
            rec(2, "s.bam.bai", generated_by=index_of(1, "s.bam")),
        ],
        None,
    )
    entry = slot(rows["s.bam.bai"], "reference_assembly")
    assert entry["value"] == "GRCh38" and "build" not in entry
