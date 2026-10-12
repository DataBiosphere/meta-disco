"""A file's samples settled at reconcile (#357): header and table, by the step rule."""

import gzip
import json
from pathlib import Path

import pytest

from meta_disco import code_rules
from meta_disco.models import SAMPLES_FIELD, SOURCE_REPOSITORY_METADATA, ClaimSource
from meta_disco.output_utils import (
    RECONCILED_DIR,
    SAMPLE_LISTS_FILE,
    iter_reconciled_records,
    iter_reconciled_sample_lists,
)
from meta_disco.reconcile_samples import (
    AGREED,
    CONFLICT,
    HEADER_ONLY,
    INCOMPARABLE,
    NONE,
    TABLE_ONLY,
    Named,
    from_line,
    from_record,
    name_disagrees,
    settle,
)
from meta_disco.records import SAMPLE_LISTS_KEY, SAMPLE_OUTCOMES_KEY, UNRECOGNISED_SAMPLES_KEY
from meta_disco.sample_identity import Identifier, identifier_rules, reference, sample_list
from meta_disco.schema.classification_model import ClassificationRecord, SampleList
from tests.test_reconcile import DATASET, drs, go, record, write_evidence
from tests.test_value_map import load

HEADER = {"source_type": "content_read", "rule_id": code_rules.BAM_READ_GROUP_SAMPLES.id}
SOURCE = ClaimSource(name="anvil", dataset=DATASET, table="participant", column="participant_id")


def coriell(n: str) -> Identifier:
    return Identifier("coriell", n)


def header(*ids: str) -> Named:
    return Named(frozenset(coriell(i) for i in ids), (HEADER,), from_header=True)


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
