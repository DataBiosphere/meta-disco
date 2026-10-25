"""A file's samples settled at reconcile (#357): header and table, by the step rule, a parent's across a step (#668),
and a PLINK fileset's sample table's (#751)."""

import gzip
import json
from pathlib import Path

import pytest
from generate_reconcile_report import CONFLICT_COLUMNS, conflict_tsv

from meta_disco import code_rules, edges
from meta_disco.models import SAMPLES_FIELD, SOURCE_REPOSITORY_METADATA, ClaimSource
from meta_disco.output_utils import (
    FILES_WITHOUT_SAMPLES_FILE,
    RECONCILED_DIR,
    SAMPLE_CONFLICTS_FILE,
    SAMPLE_LISTS_FILE,
    iter_reconciled_artifact,
    iter_reconciled_records,
    iter_reconciled_sample_lists,
    run_filesets,
)
from meta_disco.reconcile_inherit import Step
from meta_disco.reconcile_samples import (
    AGREED,
    CONFLICT,
    FILESET_ONLY,
    HEADER_ONLY,
    INCOMPARABLE,
    INHERITED,
    MAX_EXAMPLES,
    NONE,
    PARENT,
    PARENT_CONFLICT,
    PARENT_NONE,
    PARENTS_DIFFER,
    PASSED,
    TABLE_ONLY,
    Named,
    SampleReport,
    from_line,
    from_record,
    lists_disagree,
    name_disagrees,
    settle,
    tables_of,
)
from meta_disco.record_keys import SOURCE_RECORD_KEYS
from meta_disco.records import FILESETS_KEY, SAMPLE_LISTS_KEY, SAMPLE_OUTCOMES_KEY, UNRECOGNISED_SAMPLES_KEY
from meta_disco.sample_identity import Identifier, identifier_rules, reference, sample_list
from meta_disco.schema.classification_model import ClassificationRecord, SampleList
from tests.test_reconcile import DATASET, drs, go, record, write_evidence
from tests.test_value_map import load

HEADER = {"source_type": "content_read", "rule_id": code_rules.BAM_READ_GROUP_SAMPLES.id}
SOURCE = ClaimSource(name="anvil", dataset=DATASET, table="participant", column="participant_id")


def coriell(n: str) -> Identifier:
    return Identifier("coriell", n)


def header(*ids: str) -> Named:
    return Named(frozenset(coriell(i) for i in ids), (HEADER,), kind="header")


def table_says(*members: Identifier, column: str = "participant_id") -> Named:
    source = ClaimSource(name="anvil", dataset=DATASET, table="participant", column=column)
    attribution = {"source_type": SOURCE_REPOSITORY_METADATA, "rule_id": "coriell_hg", "source": source.to_dict()}
    return Named(frozenset(members), (attribution,))


# --- settling ------------------------------------------------------------------------


def test_header_and_table_agreeing_give_one_list_named_by_both_header_first():
    outcome, samples, members = settle([table_says(coriell("HG00096")), header("HG00096")])
    assert outcome == AGREED and members == {coriell("HG00096")}
    assert samples is not None and samples["count"] == 1
    assert [a["rule_id"] for a in samples["named_by"]] == [HEADER["rule_id"], "coriell_hg"]


def test_one_source_alone_gives_its_own():
    assert settle([header("HG00096")])[0] == HEADER_ONLY
    assert settle([table_says(coriell("HG00096"))])[0] == TABLE_ONLY


def test_two_table_lines_naming_the_same_sample_are_one_attribution_each_listed_once():
    outcome, samples, _ = settle([table_says(coriell("HG00096")), table_says(coriell("HG00096"))])
    assert outcome == TABLE_ONLY and samples is not None and len(samples["named_by"]) == 1


def test_different_members_in_one_namespace_are_a_conflict_and_give_no_samples():
    assert settle([header("HG00096"), table_says(coriell("HG00097"))]) == (CONFLICT, None, frozenset())


def test_different_members_sharing_no_namespace_are_incomparable_and_give_no_samples():
    """`NA19770` and `SRS006871` may be one person, but only a crosswalk could say (#361)."""
    sra = Identifier("sra_sample", "SRS006871")
    assert settle([header("NA19770"), table_says(sra)]) == (INCOMPARABLE, None, frozenset())


def test_no_source_gives_nothing():
    assert settle([]) == (NONE, None, frozenset())


def parent_says(*ids: str) -> Named:
    attribution = {"source_type": "derivation_inheritance", "rule_id": code_rules.SAMPLES_INHERITED_FROM_PARENT.id}
    return Named(frozenset(coriell(i) for i in ids), (attribution,), kind=PARENT)


def test_a_parent_alone_gives_inherited_samples():
    outcome, samples, _ = settle([parent_says("HG00096")])
    assert outcome == INHERITED and samples is not None and samples["count"] == 1


def test_a_parent_agreeing_with_the_files_own_keeps_its_outcome_and_is_listed_last():
    outcome, samples, _ = settle([parent_says("HG00096"), table_says(coriell("HG00096"))])
    assert outcome == TABLE_ONLY and samples is not None
    assert [a["rule_id"] for a in samples["named_by"]] == ["coriell_hg", code_rules.SAMPLES_INHERITED_FROM_PARENT.id]


def test_a_parent_differing_from_the_files_own_is_a_conflict():
    assert settle([parent_says("HG00096"), table_says(coriell("HG00097"))]) == (CONFLICT, None, frozenset())


@pytest.mark.parametrize(
    ("child", "parent", "expected"),
    [
        ({"HG00096"}, {"HG00096"}, False),
        ({"HG00096", "HG00097"}, {"HG00096"}, False),  # a cohort's list beside one member
        ({"HG00096"}, {"HG00096", "HG00097"}, False),  # a callset with samples dropped
        ({"HG00097"}, {"HG00096"}, True),
        ({"HG00096", "HG00098"}, {"HG00096", "HG00097"}, True),
    ],
)
def test_lists_disagree_where_neither_holds_the_other(child, parent, expected):
    assert lists_disagree(frozenset(map(coriell, child)), frozenset(map(coriell, parent))) is expected


def test_lists_naming_samples_in_namespaces_the_other_lacks_disagree_until_a_crosswalk():
    """``NA19770`` and ``SRS006871`` may be one person, but no crosswalk says so yet (#361)."""
    sra = Identifier("sra_sample", "SRS006871")
    assert lists_disagree(frozenset({coriell("NA19770")}), frozenset({sra}))
    assert lists_disagree(
        frozenset({coriell("HG00096"), sra}), frozenset({coriell("HG00096")}) | {Identifier("biosample", "SAMN1")}
    )
    # An extra namespace disagrees even where the rest of one list holds the other.
    assert lists_disagree(frozenset({coriell("HG00096"), sra}), frozenset({coriell("HG00096")}))
    assert lists_disagree(frozenset({coriell("HG00096")}), frozenset({coriell("HG00096"), sra}))
    # A dataset's own names in two datasets are two namespaces, even where one list holds the other.
    in_a, in_b = Identifier("dataset_local", "s7", "A"), Identifier("dataset_local", "s8", "B")
    assert lists_disagree(frozenset({in_a, in_b}), frozenset({in_a}))


# --- an evidence line ----------------------------------------------------------------


def test_a_line_names_its_sample_citing_the_rule_and_the_column():
    got = from_line("GM19908", DATASET, SOURCE_REPOSITORY_METADATA, SOURCE, identifier_rules())
    assert got is not None and got.members == {coriell("NA19908")}
    assert got.named_by == (
        {"source_type": SOURCE_REPOSITORY_METADATA, "rule_id": "coriell_cell_line_or_dna", "source": SOURCE.to_dict()},
    )


def test_a_list_cell_names_each_element_and_each_rule_once():
    got = from_line('["HG00096", "HG002", "HG00097"]', DATASET, SOURCE_REPOSITORY_METADATA, SOURCE, identifier_rules())
    assert got is not None and got.members == {coriell("HG00096"), coriell("HG00097"), Identifier("giab", "HG002")}
    assert [a["rule_id"] for a in got.named_by] == ["coriell_hg", "giab_name"]


@pytest.mark.parametrize("raw", ["BioSample_3", '["HG00096", "Sample"]'])
def test_a_line_holding_an_unrecognised_string_names_nothing(raw):
    assert from_line(raw, DATASET, SOURCE_REPOSITORY_METADATA, SOURCE, identifier_rules()) is None


def test_a_record_pointing_to_a_list_its_run_lacks_is_refused():
    row = {"file_name": "x.bam", "samples": {"list_id": "0" * 16, "count": 1, "named_by": [HEADER]}}
    with pytest.raises(ValueError, match="no producer file of the run holds"):
        from_record(row, {}, {})


def test_a_list_held_from_a_table_does_not_excuse_a_record_whose_run_lacks_it():
    """The members cache also holds tables' lists (#668); the run's own lists are still checked."""
    key = "0" * 16
    row = {"file_name": "x.bam", "samples": {"list_id": key, "count": 1, "named_by": [HEADER]}}
    with pytest.raises(ValueError, match="no producer file of the run holds"):
        from_record(row, {}, {key: frozenset({coriell("HG00096")})})


# --- the name check ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "members", "expected"),
    [
        # A parent's CRAM labelled with the child's sample: the trap #357 found in HPRC's `mat_ilmn`.
        ("HG01105.final.cram", {coriell("HG01106")}, coriell("HG01105")),
        ("HG01105.final.cram", {coriell("HG01105")}, None),
        # GM and NA are one sample.
        ("GM19908.bam", {coriell("NA19908")}, None),
        # A name naming two says nothing about which.
        ("HG00096.HG00097.vcf.gz", {coriell("HG00098")}, None),
        # A name in another namespace cannot be compared.
        ("NA24695_L001_R1.fastq.gz", {Identifier("giab", "HG007")}, None),
        ("readme.txt", {coriell("HG00096")}, None),
    ],
)
def test_a_name_disagrees_only_where_it_names_one_sample_in_a_members_namespace(name, members, expected):
    assert name_disagrees(name, frozenset(members), identifier_rules()) == expected


# --- through a run -------------------------------------------------------------------


@pytest.fixture
def table(tmp_path: Path):
    return load(tmp_path, "rows: []\n")


@pytest.fixture
def run(tmp_path: Path) -> Path:
    return tmp_path / "output" / "20261012_000000"


@pytest.fixture
def evidence(tmp_path: Path) -> Path:
    root = tmp_path / "evidence"
    root.mkdir()
    return root


def write_bam_run(run_dir: Path, rows: list[dict], lists: list[dict], details: dict | None = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    body = {"metadata": {"details": details} if details else {}, "classifications": rows, SAMPLE_LISTS_KEY: lists}
    (run_dir / "bam_classifications.json").write_text(json.dumps(body))


def with_header_samples(row: dict, *ids: str) -> tuple[dict, dict]:
    members = [coriell(i) for i in ids]
    row["samples"] = reference(members, [HEADER])
    return row, sample_list(members)


def reconciled(run_dir: Path) -> dict[str, dict]:
    return {r["file_id"]: r for r in iter_reconciled_records(run_dir)}


def test_a_run_settles_header_and_table_and_writes_each_list_once(tmp_path, run, evidence, table):
    agreed, agreed_list = with_header_samples(record(1), "HG00096")
    differs, differs_list = with_header_samples(record(2), "HG00097")
    header_only, _ = with_header_samples(record(3), "HG00096")
    write_bam_run(run, [agreed, differs, header_only, record(4), record(5)], [agreed_list, differs_list])
    write_evidence(
        evidence,
        [
            (SAMPLES_FIELD, drs(1), "HG00096"),
            (SAMPLES_FIELD, drs(2), "HG00099"),
            (SAMPLES_FIELD, drs(4), "GM19908"),
            (SAMPLES_FIELD, drs(5), "Sample"),
        ],
        table="participant",
        column="participant_id",
    )
    report = go(run, tmp_path, evidence, table)
    rows = reconciled(run)

    assert [a["rule_id"] for a in rows["file-1"]["samples"]["named_by"]] == [HEADER["rule_id"], "coriell_hg"]
    assert rows["file-1"]["samples"]["list_id"] == agreed_list["list_id"]
    assert rows["file-2"]["samples"] is None
    assert rows["file-3"]["samples"]["list_id"] == agreed_list["list_id"]
    assert rows["file-4"]["samples"]["named_by"][0]["source"]["column"] == "participant_id"
    assert rows["file-5"]["samples"] is None
    # Every list a record points to, once, and none another does not.
    lists = {entry["list_id"]: entry for entry in iter_reconciled_sample_lists(run)}
    assert set(lists) == {r["samples"]["list_id"] for r in rows.values() if r["samples"]}
    assert lists[rows["file-4"]["samples"]["list_id"]]["members"] == [{"id": "NA19908", "namespace": "coriell"}]
    for entry in lists.values():
        SampleList(**entry)
    for row in rows.values():
        ClassificationRecord(**row)

    block = report[SAMPLES_FIELD]["by_dataset"][DATASET]
    assert block["settled"] == {AGREED: 1, HEADER_ONLY: 1, TABLE_ONLY: 1, CONFLICT: 1, "none": 1}
    # Coverage lists the dimensions each source speaks to; samples is not one.
    assert all(SAMPLES_FIELD not in slots for per in report["coverage"].values() for slots in per.values())
    assert block["conflict_examples"] == ["f2.bam"]
    assert block["table_unrecognised"] == [
        {"table": "participant", "column": "participant_id", "raw_value": "Sample", "files": 1}
    ]


def test_without_evidence_the_header_samples_stand(tmp_path, run, table):
    row, entry = with_header_samples(record(1), "HG00096")
    write_bam_run(run, [row], [entry])
    go(run, tmp_path, None, table)
    assert reconciled(run)["file-1"]["samples"] == row["samples"]


def test_the_report_names_what_the_headers_said(tmp_path, run, table):
    details = {
        SAMPLE_OUTCOMES_KEY: {DATASET: {"named": 3, "unrecognised": 1}},
        UNRECOGNISED_SAMPLES_KEY: {DATASET: {"Sample": 1}},
    }
    write_bam_run(run, [record(1)], [], details)
    report = go(run, tmp_path, None, table)
    assert report[SAMPLES_FIELD]["by_dataset"][DATASET]["headers"] == {
        "outcomes": {"named": 3, "unrecognised": 1},
        "unrecognised": {"Sample": 1},
    }


def test_a_name_naming_another_sample_than_the_settled_one_is_counted(tmp_path, run, evidence, table):
    row = record(1)
    row["file_name"] = "HG01105.final.cram"
    write_bam_run(run, [row], [])
    write_evidence(evidence, [(SAMPLES_FIELD, drs(1), "HG01106")], table="sample", column="sample_id")
    report = go(run, tmp_path, evidence, table)
    block = report[SAMPLES_FIELD]["by_dataset"][DATASET]
    assert block["name_disagreements"] == 1
    assert block["name_disagreement_examples"][0]["name_names"] == {"id": "HG01105", "namespace": "coriell"}
    # A check, never a source: the table's sample still stands.
    assert reconciled(run)["file-1"]["samples"]["count"] == 1


def test_the_lists_file_starts_with_the_envelope(tmp_path, run, table):
    row, entry = with_header_samples(record(1), "HG00096")
    write_bam_run(run, [row], [entry])
    go(run, tmp_path, None, table)
    lines = gzip.decompress((run / RECONCILED_DIR / SAMPLE_LISTS_FILE).read_bytes()).splitlines()
    assert "reconcile" in json.loads(lines[0]) and json.loads(lines[1]) == entry


def test_a_run_reconciled_before_samples_has_no_lists_to_read(tmp_path, run):
    (run / RECONCILED_DIR).mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match=SAMPLE_LISTS_FILE):
        list(iter_reconciled_sample_lists(run))


# --- across a step (#668) -------------------------------------------------------------


def child(n: int, name: str, rule, parent: int, parent_name: str) -> dict:
    row = record(n)
    row["file_name"] = name
    row["generated_by"] = edges.generated_by(
        rule, [{"file_name": parent_name, "file_id": f"file-{parent}"}], SOURCE_RECORD_KEYS["anvil"]
    )
    return row


def test_an_index_and_its_checksum_take_the_parents_samples_parents_first(tmp_path, run, table):
    """``.tbi.md5`` <- ``.tbi`` <- ``.vcf.gz``: the checksum takes what its index took, whatever the row order."""
    vcf, entry = with_header_samples(record(1), "HG02078")
    vcf["file_name"] = "HG02078.chr6.hc.vcf.gz"
    tbi = child(2, "HG02078.chr6.hc.vcf.gz.tbi", code_rules.INDEX_BY_NAME, 1, vcf["file_name"])
    md5 = child(3, "HG02078.chr6.hc.vcf.gz.tbi.md5", code_rules.CHECKSUM_BY_NAME, 2, tbi["file_name"])
    write_bam_run(run, [md5, tbi, vcf], [entry])
    report = go(run, tmp_path, None, table)
    rows = reconciled(run)
    for key, parent in (("file-2", "file-1"), ("file-3", "file-2")):
        samples = rows[key]["samples"]
        assert samples["list_id"] == entry["list_id"] and samples["count"] == 1
        (attribution,) = samples["named_by"]
        assert attribution["rule_id"] == code_rules.SAMPLES_INHERITED_FROM_PARENT.id
        assert (attribution["activity"], attribution["parent_role"]) == (
            ("IndexActivity", "indexed") if key == "file-2" else ("ChecksumActivity", "checked")
        )
        assert attribution["source_type"] == "derivation_inheritance"
        assert attribution["parent_keys"] == [parent]
        ClassificationRecord(**rows[key])
    block = report[SAMPLES_FIELD]["by_dataset"][DATASET]
    assert block["settled"] == {HEADER_ONLY: 1, INHERITED: 2}
    assert block["inheritance"] == {"ChecksumActivity": {PASSED: 1}, "IndexActivity": {PASSED: 1}}


def test_a_parent_with_no_samples_passes_nothing_and_is_counted(tmp_path, run, table):
    write_bam_run(run, [record(1), child(2, "f1.bam.bai", code_rules.INDEX_BY_NAME, 1, "f1.bam")], [])
    report = go(run, tmp_path, None, table)
    assert reconciled(run)["file-2"]["samples"] is None
    assert report[SAMPLES_FIELD]["by_dataset"][DATASET]["inheritance"] == {"IndexActivity": {PARENT_NONE: 1}}


def test_a_parent_in_conflict_passes_nothing_and_is_counted_apart_from_one_naming_none(tmp_path, run, evidence, table):
    """The conflict is the parent's, listed on it once, not on its index (as contract 4.9's for dimensions)."""
    bam, entry = with_header_samples(record(1), "HG00096")
    bai = child(2, "f1.bam.bai", code_rules.INDEX_BY_NAME, 1, "f1.bam")
    write_bam_run(run, [bam, bai], [entry])
    write_evidence(evidence, [(SAMPLES_FIELD, drs(1), "HG00097")], table="participant", column="participant_id")
    report = go(run, tmp_path, evidence, table)
    rows = reconciled(run)
    assert rows["file-1"]["samples"] is None and rows["file-2"]["samples"] is None
    block = report[SAMPLES_FIELD]["by_dataset"][DATASET]
    assert block["settled"] == {CONFLICT: 1, NONE: 1}
    assert block["inheritance"] == {"IndexActivity": {PARENT_CONFLICT: 1}}


def test_an_index_whose_own_table_row_names_another_sample_is_a_conflict(tmp_path, run, evidence, table):
    bam, entry = with_header_samples(record(1), "HG00096")
    bai = child(2, "f1.bam.bai", code_rules.INDEX_BY_NAME, 1, "f1.bam")
    write_bam_run(run, [bam, bai], [entry])
    write_evidence(evidence, [(SAMPLES_FIELD, drs(2), "HG00097")], table="participant", column="participant_id")
    report = go(run, tmp_path, evidence, table)
    assert reconciled(run)["file-2"]["samples"] is None
    assert report[SAMPLES_FIELD]["by_dataset"][DATASET]["settled"][CONFLICT] == 1


def test_a_cohort_merge_takes_its_lists_samples_not_its_members(tmp_path, run, table):
    """A GenomicsDB tar takes the samples its sample map names, though each gVCF names one."""
    members = [with_header_samples(record(n), s) for n, s in ((1, "HG00096"), (2, "HG00097"))]
    smap, cohort = with_header_samples(record(3), "HG00096", "HG00097")
    smap["file_name"] = "chr1_sample_map.tsv"
    smap["generated_by"] = edges.generated_by(
        code_rules.COHORT_BY_SAMPLE_MAP,
        [{"file_name": f"f{n}.bam", "file_id": f"file-{n}"} for n in (1, 2)],
        SOURCE_RECORD_KEYS["anvil"],
    )
    tar = child(4, "chr1.1_100000.tar", code_rules.MERGE_BY_WORKSPACE_HEADER, 3, smap["file_name"])
    write_bam_run(run, [*(r for r, _ in members), smap, tar], [*(e for _, e in members), cohort])
    report = go(run, tmp_path, None, table)
    samples = reconciled(run)["file-4"]["samples"]
    assert samples["list_id"] == cohort["list_id"] and samples["count"] == 2
    # Each member's one sample is within the map's list: no disagreement across the definition step.
    assert report[SAMPLES_FIELD]["by_dataset"][DATASET]["parent_disagreements"] == {}


def test_samples_never_pass_across_a_variant_call_and_a_disagreement_is_counted(tmp_path, run, table):
    cram, cram_list = with_header_samples(record(1), "HG00096")
    vcf, vcf_list = with_header_samples(
        child(2, "HG00097.g.vcf.gz", code_rules.VARIANT_CALL_BY_HEADER, 1, "f1.bam"), "HG00097"
    )
    silent = child(3, "x.g.vcf.gz", code_rules.VARIANT_CALL_BY_HEADER, 1, "f1.bam")
    write_bam_run(run, [cram, vcf, silent], [cram_list, vcf_list])
    report = go(run, tmp_path, None, table)
    rows = reconciled(run)
    assert rows["file-2"]["samples"]["list_id"] == vcf_list["list_id"]
    assert rows["file-3"]["samples"] is None
    block = report[SAMPLES_FIELD]["by_dataset"][DATASET]
    assert block["parent_disagreements"] == {"VariantCallActivity": 1}
    (example,) = block["parent_disagreement_examples"]
    assert example["file_name"] == "HG00097.g.vcf.gz" and example["parent_file"] == "f1.bam"
    assert example["parent_samples"] == [{"id": "HG00096", "namespace": "coriell"}]


def test_each_activity_keeps_its_own_disagreement_examples():
    """Five examples from one activity do not crowd out another's (#668)."""
    report = SampleReport(identifier_rules())
    report.members["p"] = frozenset({coriell("HG00096")})
    report.held["parent"] = "p"
    child_says = frozenset({coriell("HG00097")})

    def step(activity: str) -> dict:
        return {"activity": activity, "inputs": [{"role": "x", "parent_key": "parent", "parent_file": "p.bam"}]}

    for n in range(MAX_EXAMPLES + 1):
        report._check_parents(DATASET, f"a{n}.vcf.gz", child_says, step("VariantCallActivity"))
    report._check_parents(DATASET, "b.cram", child_says, step("AlignmentActivity"))
    assert report.parent_disagreements[DATASET] == {"VariantCallActivity": MAX_EXAMPLES + 1, "AlignmentActivity": 1}
    assert [e["file_name"] for e in report.parent_examples[DATASET] if e["activity"] == "AlignmentActivity"] == [
        "b.cram"
    ]


def test_parents_in_one_role_naming_different_lists_pass_nothing():
    report = SampleReport(identifier_rules())
    report.members.update({"l1": frozenset({coriell("HG00096")}), "l2": frozenset({coriell("HG00097")})})
    report.held.update({"p1": "l1", "p2": "l2"})
    report._own["c"] = ([], DATASET)
    report.inherit({"c": Step("IndexActivity", (("indexed", "p1"), ("indexed", "p2")))})
    assert report.passing[DATASET]["IndexActivity"] == {PARENTS_DIFFER: 1}
    assert "c" not in report.held and "c" not in report._inherited


def test_a_parent_named_twice_in_a_step_is_one_disagreement():
    report = SampleReport(identifier_rules())
    report.members["p"] = frozenset({coriell("HG00096")})
    report.held["parent"] = "p"
    twice = [{"role": "calls_from", "parent_key": "parent", "parent_file": "p.cram"}] * 2
    report._check_parents(
        DATASET, "c.vcf.gz", frozenset({coriell("HG00097")}), {"activity": "VariantCallActivity", "inputs": twice}
    )
    assert report.parent_disagreements[DATASET] == {"VariantCallActivity": 1}


# --- a PLINK fileset's sample table (#751) --------------------------------------------

PSAM = {"source_type": "content_read", "rule_id": code_rules.PSAM_SAMPLE_IDS.id}


def write_psam_run(run_dir: Path, psam: dict, entry: dict | None, members: list[int]) -> None:
    """``psam`` in the psam producer's file, paired with the rows ``members`` names (in the bam file here)."""
    run_dir.mkdir(parents=True, exist_ok=True)
    filesets = [{"sample_table": psam["file_id"], "members": [f"file-{n}" for n in members]}]
    body = {
        "metadata": {},
        "classifications": [psam],
        SAMPLE_LISTS_KEY: [entry] if entry else [],
        FILESETS_KEY: filesets,
    }
    (run_dir / "psam_classifications.json").write_text(json.dumps(body))


def psam_row(n: int, *ids: str) -> tuple[dict, dict]:
    """A `.psam`'s row naming ``ids``, and its list."""
    row = member(n, f"ACB.{n}.psam")
    members = [coriell(i) for i in ids]
    row["samples"] = reference(members, [PSAM])
    return row, sample_list(members)


def member(n: int, name: str) -> dict:
    row = record(n)
    row["file_name"] = name
    return row


def test_a_filesets_members_take_its_sample_tables_samples(tmp_path, run, table):
    psam, entry = psam_row(1, "HG01879", "NA19700")
    write_psam_run(run, psam, entry, [2, 3, 4])
    write_bam_run(run, [member(2, "ACB.1.pgen"), member(3, "ACB.1.pvar"), member(4, "ACB.1.log")], [])
    report = go(run, tmp_path, None, table)
    rows = reconciled(run)
    for key in ("file-2", "file-3", "file-4"):
        samples = rows[key]["samples"]
        assert samples["list_id"] == entry["list_id"] and samples["count"] == 2
        assert samples["named_by"] == [
            {
                "source_type": "content_read",
                "rule_id": code_rules.SAMPLES_FROM_FILESET_SAMPLE_TABLE.id,
                "sample_table_key": "file-1",
            }
        ]
        ClassificationRecord(**rows[key])
    block = report[SAMPLES_FIELD]["by_dataset"][DATASET]
    assert block["settled"] == {HEADER_ONLY: 1, FILESET_ONLY: 3}
    assert block["filesets"] == {PASSED: 3}


def test_a_sample_table_naming_none_passes_nothing_and_is_counted(tmp_path, run, table):
    write_psam_run(run, member(1, "ACB.1.psam"), None, [2])
    write_bam_run(run, [member(2, "ACB.1.pgen")], [])
    report = go(run, tmp_path, None, table)
    assert reconciled(run)["file-2"]["samples"] is None
    assert report[SAMPLES_FIELD]["by_dataset"][DATASET]["filesets"] == {PARENT_NONE: 1}


def test_a_sample_table_in_conflict_passes_nothing(tmp_path, run, evidence, table):
    psam, entry = psam_row(1, "HG01879")
    write_psam_run(run, psam, entry, [2])
    write_bam_run(run, [member(2, "ACB.1.pgen")], [])
    write_evidence(evidence, [(SAMPLES_FIELD, drs(1), "HG01880")], table="participant", column="participant_id")
    report = go(run, tmp_path, evidence, table)
    assert reconciled(run)["file-2"]["samples"] is None
    block = report[SAMPLES_FIELD]["by_dataset"][DATASET]
    assert block["settled"] == {CONFLICT: 1, NONE: 1}
    assert block["filesets"] == {PARENT_CONFLICT: 1}
    # The member's row names the table apart from a parent: the table is no parent (#751).
    (row,) = iter_reconciled_artifact(run, FILES_WITHOUT_SAMPLES_FILE)
    assert row["sample_table_conflict"] == ["file-1"] and "parent_conflict" not in row


@pytest.mark.parametrize(
    ("said", "outcome"),
    [pytest.param("HG01879", AGREED, id="agreeing"), pytest.param("HG01880", CONFLICT, id="differing")],
)
def test_a_members_own_source_settles_with_its_sample_tables(tmp_path, run, evidence, table, said, outcome):
    psam, entry = psam_row(1, "HG01879")
    write_psam_run(run, psam, entry, [2])
    write_bam_run(run, [member(2, "ACB.1.pgen")], [])
    write_evidence(evidence, [(SAMPLES_FIELD, drs(2), said)], table="participant", column="participant_id")
    report = go(run, tmp_path, evidence, table)
    samples = reconciled(run)["file-2"]["samples"]
    if outcome == AGREED:
        assert [a["rule_id"] for a in samples["named_by"]] == [
            "coriell_hg",
            code_rules.SAMPLES_FROM_FILESET_SAMPLE_TABLE.id,
        ]
    else:
        assert samples is None
        # The conflicts TSV names the sample table the fileset source came from.
        _, *lines = conflict_tsv(iter_reconciled_artifact(run, SAMPLE_CONFLICTS_FILE)).splitlines()
        rows = [dict(zip(CONFLICT_COLUMNS, line.split("\t"), strict=True)) for line in lines]
        assert {row["source_kind"]: row["from_records"] for row in rows} == {"table": "", "fileset": "file-1"}
    assert report[SAMPLES_FIELD]["by_dataset"][DATASET]["settled"][outcome] == 1


def test_a_members_checksum_takes_what_the_member_took_from_its_table(tmp_path, run, table):
    """The pairing settles before inheritance, so a step from a member passes the table's samples on."""
    psam, entry = psam_row(1, "HG01879")
    write_psam_run(run, psam, entry, [2])
    md5 = child(3, "ACB.1.pgen.md5", code_rules.CHECKSUM_BY_NAME, 2, "ACB.1.pgen")
    write_bam_run(run, [md5, member(2, "ACB.1.pgen")], [])
    report = go(run, tmp_path, None, table)
    samples = reconciled(run)["file-3"]["samples"]
    assert samples["list_id"] == entry["list_id"]
    assert samples["named_by"][0]["rule_id"] == code_rules.SAMPLES_INHERITED_FROM_PARENT.id
    assert report[SAMPLES_FIELD]["by_dataset"][DATASET]["settled"] == {HEADER_ONLY: 1, FILESET_ONLY: 1, INHERITED: 1}


def test_a_member_two_tables_paired_takes_from_neither_where_they_differ():
    tables = tables_of([{"sample_table": "a", "members": ["m", "x"]}, {"sample_table": "b", "members": ["m"]}])
    assert tables == {"m": ("a", "b"), "x": ("a",)}
    report = SampleReport(identifier_rules(), tables=tables)
    report.members.update({"l1": frozenset({coriell("HG00096")}), "l2": frozenset({coriell("HG00097")})})
    report.held.update({"a": "l1", "b": "l2"})
    report._member_own["m"] = ([], DATASET)
    report.pair()
    assert report.fileset_outcomes[DATASET] == {PARENTS_DIFFER: 1}
    assert "m" not in report.held


def test_a_damaged_filesets_block_is_refused(run):
    run.mkdir(parents=True)
    (run / "psam_classifications.json").write_text(
        json.dumps({"classifications": [], FILESETS_KEY: [{"sample_table": "a", "members": []}]})
    )
    with pytest.raises(ValueError, match="does not name its members"):
        run_filesets(run)


@pytest.mark.parametrize(
    ("held", "conflicted", "outcome"),
    [
        pytest.param({"a": "l1", "b": "l2"}, {"b"}, PARENTS_DIFFER, id="different lists before a conflict"),
        pytest.param({"a": "l1"}, set(), PARENT_NONE, id="one holding a list, one holding none"),
        pytest.param({"a": "l1", "b": "l1"}, set(), PASSED, id="two holding one list"),
    ],
)
def test_what_two_sources_pass_first_match_wins(held, conflicted, outcome):
    report = SampleReport(identifier_rules())
    report.members.update({"l1": frozenset({coriell("HG00096")}), "l2": frozenset({coriell("HG00097")})})
    report.held.update(held)
    report._conflicted.update(conflicted)
    assert report._passing("c", ("a", "b"), report._conflicted_parents)[0] == outcome


def test_two_tables_naming_one_list_both_pass_and_are_both_cited():
    report = SampleReport(identifier_rules(), tables={"m": ("a", "b")})
    report.members["l"] = frozenset({coriell("HG00096")})
    report.held.update({"a": "l", "b": "l"})
    report._member_own["m"] = ([], DATASET)
    report.pair()
    assert [a["sample_table_key"] for a in report._from_table["m"].named_by] == ["a", "b"]
    assert report.held["m"] == "l"


def test_a_member_whose_step_passes_other_samples_keeps_its_tables_source_through_inheritance():
    """The table's source joins the member's own, so a parent naming another sample makes the member a conflict."""
    report = SampleReport(identifier_rules(), tables={"m": ("t",)})
    report.members.update({"l1": frozenset({coriell("HG00096")}), "l2": frozenset({coriell("HG00097")})})
    report.held.update({"t": "l1", "p": "l2"})
    own: list[Named] = []
    report._own["m"] = report._member_own["m"] = (own, DATASET)
    report.pair()
    report.inherit({"m": Step("IndexActivity", (("indexed", "p"),))})
    assert "m" not in report.held and "m" in report._conflicted


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param({"sample_table": "a", "members": "x"}, id="members not a list"),
        pytest.param({"sample_table": "a\nb", "members": ["x"]}, id="a key holding a newline"),
    ],
)
def test_a_filesets_entry_off_the_schema_is_refused(run, entry):
    run.mkdir(parents=True)
    (run / "psam_classifications.json").write_text(json.dumps({"classifications": [], FILESETS_KEY: [entry]}))
    with pytest.raises(ValueError, match="does not name its members"):
        run_filesets(run)
