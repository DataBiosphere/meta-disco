"""The steps of T2T's joint-calling cohort (#621): a sample map's members, and a GenomicsDB
workspace tar's one input, the map, read from the tar's own ``vcfheader.vcf``."""

import dataclasses
import json

import pytest

from meta_disco import code_rules
from meta_disco import cohort_steps as cs
from meta_disco.evidence import TarHead
from meta_disco.file_types import SAMPLE_MAP_CONFIG, TAR_CONFIG
from meta_disco.header_classifier import workspace_header_member
from meta_disco.models import SOURCE_CONTENT_READ
from meta_disco.pipeline import ClassifyPipeline
from meta_disco.record_keys import RecordKey
from meta_disco.validators.command_lines import GATK, Step
from tests.metadata_fixtures import write_metadata
from tests.test_producer_steps import EVIDENCE, IMPORT, SELECT, header, header_text

KEY = RecordKey("file_id", "file_id")
TAR = "chr1.100000001_100100000.tar"
MAP = "chr1_sample_map.tsv"
MAP_TEXT = (
    "HG00096\tgs://b/hc_vcfs/compressed/chr1/HG00096.chr1.hc.vcf.gz\n"
    "HG00097\tgs://b/hc_vcfs/compressed/chr1/HG00097.chr1.hc.vcf.gz\n"
)


def records(*entries) -> list[dict]:
    """(file name, dataset) records, keyed by ``file_id`` f0, f1, …"""
    return [{"file_id": f"f{n}", "file_name": name, "dataset_id": ds} for n, (name, ds) in enumerate(entries)]


def tar_head(*lines: str) -> cs.ParsedTarHead:
    return cs.parse_tar_head(TarHead(["./chr1.100000001_100100000/vcfheader.vcf"], header_text(*lines)))


# --- reading the sample-name map argument --------------------------------------------------


def test_the_sample_name_map_is_an_input_list_not_an_input():
    (step,) = [c.step for c in header(IMPORT).commands]
    assert step == Step(
        GATK,
        "GenomicsDBImport",
        (),
        "./chr1.100000001_100100000",
        input_lists=("gs://b/sample_maps/chr1_sample_map.tsv",),
    )


# --- the tar's step --------------------------------------------------------------------------


def test_a_workspace_tar_merges_the_gvcfs_its_sample_map_lists():
    reader = cs.TarSteps.for_run(records((MAP, "D"), (MAP, "OTHER"), ("HG00096.chr1.hc.vcf.gz", "D")), KEY, EVIDENCE)
    step, outcome = reader(tar_head(IMPORT), TAR, "D")
    assert outcome == cs.STEPPED
    assert step is not None and step["activity"] == "CohortMergeActivity"
    (used,) = step["inputs"]
    assert (used["role"], used["parent_file"], used["parent_key"]) == ("input_list", MAP, "f0")
    assert used["named_by"] == [
        {"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.MERGE_BY_WORKSPACE_HEADER.id}
    ]


@pytest.mark.parametrize(
    ("entries", "outcome"),
    [
        (((MAP, "OTHER"),), cs.PARENT_NOT_FOUND),
        (((MAP, "D"), (MAP.upper(), "D")), cs.PARENT_AMBIGUOUS),
        # Only a file the sample-map producer claims can be the list.
        ((("chr1_sample_map.txt", "D"),), cs.PARENT_NOT_FOUND),
    ],
)
def test_a_list_no_sample_map_or_two_of_the_dataset_carry_gives_no_step(entries, outcome):
    assert cs.TarSteps.for_run(records(*entries), KEY, EVIDENCE)(tar_head(IMPORT), TAR, "D") == (None, outcome)


def test_a_workspace_naming_another_directory_is_not_this_tars():
    reader = cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)
    assert reader(tar_head(IMPORT), "chr1.1_100000.tar", "D") == (None, cs.OUTPUT_NOT_THIS_FILE)


@pytest.mark.parametrize(
    ("lines", "outcome"),
    [
        # gVCFs named one by one beside the list.
        ((IMPORT.replace("--batch-size 50", "-V a.g.vcf.gz"),), cs.NO_ACTIVITY),
        # Two different imports.
        ((IMPORT, IMPORT.replace("chr1_sample_map", "chr2_sample_map")), cs.NO_ACTIVITY),
        ((SELECT,), cs.NO_ACTIVITY),
        ((), cs.NO_COMMAND_LINE),
    ],
)
def test_any_other_header_gives_no_step(lines, outcome):
    assert cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(tar_head(*lines), TAR, "D") == (None, outcome)


def test_an_identical_import_line_twice_is_one_step():
    step, outcome = cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(tar_head(IMPORT, IMPORT), TAR, "D")
    assert outcome == cs.STEPPED and step is not None


def test_a_tar_whose_header_was_not_read_gives_no_step():
    head = cs.ParsedTarHead(["x/callset.json"], None)
    assert cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(head, TAR, "D") == (None, cs.NO_VCF_HEADER)
    # A tar that is no GenomicsDB workspace has no step to read, and is not counted.
    other = cs.ParsedTarHead(["reads/a.fastq"], None)
    assert cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(other, TAR, "D") == (None, None)
    failed = cs.ParsedTarHead(["x/callset.json"], None, "ConnectionError: reset")
    assert cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(failed, TAR, "D") == (None, cs.VCF_HEADER_UNREADABLE)
    assert cs.parse_tar_head(TarHead(["a"], None, "reset")).vcf_header_unread == "reset"


def test_only_a_genomicsdb_store_has_its_header_member_kept():
    assert workspace_header_member(["ws/callset.json"]) == "vcfheader.vcf"
    assert workspace_header_member(["ws/vcfheader.vcf"]) == "vcfheader.vcf"
    assert workspace_header_member(["reads/a.fastq", "ws/__array_schema.tdb"]) is None


def test_the_tar_head_is_parsed_once_with_its_header():
    parsed = cs.parse_tar_head(TarHead(["a"], header_text(IMPORT)))
    assert parsed.member_names == ["a"]
    assert parsed.commands is not None and [c.step.tool for c in parsed.commands] == ["GenomicsDBImport"]
    assert cs.parse_tar_head(TarHead(["a"], None)).commands is None


# --- the sample map's step -------------------------------------------------------------------


def test_a_sample_map_is_two_tab_separated_columns_naming_vcfs():
    assert cs.parse_sample_map(MAP_TEXT + "\n") == (
        ("HG00096", "gs://b/hc_vcfs/compressed/chr1/HG00096.chr1.hc.vcf.gz"),
        ("HG00097", "gs://b/hc_vcfs/compressed/chr1/HG00097.chr1.hc.vcf.gz"),
    )
    assert cs.parse_sample_map("HG00096\tgs://b/HG00096.chr1.hc.vcf.gz\r\n") == (
        ("HG00096", "gs://b/HG00096.chr1.hc.vcf.gz"),
    )
    # GATK's optional third column, the member's index, is allowed and is no member.
    assert cs.parse_sample_map("HG00096\tgs://b/HG00096.chr1.hc.vcf.gz\tgs://b/HG00096.chr1.hc.vcf.gz.tbi\n") == (
        ("HG00096", "gs://b/HG00096.chr1.hc.vcf.gz"),
    )
    assert cs.parse_sample_map("HG00096\tgs://b/HG00096.chr1.hc.vcf.gz\tgs://b/HG00096.chr1.hc.vcf.gz.csi\n") == (
        ("HG00096", "gs://b/HG00096.chr1.hc.vcf.gz"),
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "\n\n",
        "HG00096\tgs://b/HG00096.cram\n",
        "HG00096 gs://b/HG00096.chr1.hc.vcf.gz\n",
        "HG00096\tgs://b/HG00096.chr1.hc.vcf.gz\textra\n",
        "HG00096\tgs://b/HG00096.chr1.hc.vcf.gz\tgs://b/HG00096.chr1.hc.vcf.gz.tbi\tmore\n",
        "\tgs://b/HG00096.chr1.hc.vcf.gz\n",
        MAP_TEXT + "a header line\n",
    ],
)
def test_anything_else_is_not_a_sample_map(text):
    assert cs.parse_sample_map(text) is None


def map_reader(*entries) -> cs.SampleMapSteps:
    return cs.SampleMapSteps.for_run(records(*entries), KEY, EVIDENCE)


def test_a_sample_map_lists_each_gvcf_of_that_name_in_the_dataset_as_a_member():
    reader = map_reader(("HG00096.chr1.hc.vcf.gz", "D"), ("HG00097.chr1.hc.vcf.gz", "D"), ("HG00096.cram", "D"))
    step, outcome = reader(cs.parse_sample_map(MAP_TEXT), MAP, "D")
    assert outcome == cs.STEPPED
    assert step is not None and step["activity"] == "CohortDefinitionActivity"
    assert [(i["role"], i["parent_key"], i["parent_kind"]) for i in step["inputs"]] == [
        ("member", "f0", "variants"),
        ("member", "f1", "variants"),
    ]
    assert step["named_by"] == [{"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.COHORT_BY_SAMPLE_MAP.id}]


@pytest.mark.parametrize(
    ("entries", "outcome"),
    [
        ((("HG00096.chr1.hc.vcf.gz", "D"),), cs.PARENT_NOT_FOUND),
        (
            (("HG00096.chr1.hc.vcf.gz", "D"), ("HG00097.chr1.hc.vcf.gz", "D"), ("HG00097.CHR1.hc.vcf.gz", "D")),
            cs.PARENT_AMBIGUOUS,
        ),
    ],
)
def test_a_member_missing_or_ambiguous_declines_the_whole_cohort(entries, outcome):
    assert map_reader(*entries)(cs.parse_sample_map(MAP_TEXT), MAP, "D") == (None, outcome)


def test_two_rows_naming_one_file_decline_the_cohort():
    rows = cs.parse_sample_map(MAP_TEXT.replace("HG00097.chr1", "HG00096.chr1"))
    assert map_reader(("HG00096.chr1.hc.vcf.gz", "D"))(rows, MAP, "D") == (None, cs.PARENT_AMBIGUOUS)


def test_a_file_that_is_no_sample_map_gives_no_step():
    assert map_reader(("HG00096.chr1.hc.vcf.gz", "D"))(None, MAP, "D") == (None, cs.NOT_A_LIST)


# --- the two producers -----------------------------------------------------------------------


def _run(tmp_path, config, payloads: dict, entries: list[tuple[str, str]]) -> tuple[dict, dict]:
    """Run ``config`` over ``entries`` (file name, file id), its fetcher stubbed by md5; the rows by file id and the details."""
    inputs = []
    for n, (name, file_id) in enumerate(entries):
        inputs.append(
            {
                "file_id": file_id,
                "file_name": name,
                "dataset_id": "D",
                "dataset_title": "T",
                "file_md5sum": f"{n:032x}",
                "file_size": 1,
                "file_format": "." + name.rsplit(".", 1)[1],
            }
        )
    by_md5 = {f"{n:032x}": payloads[name] for n, (name, _) in enumerate(entries) if name in payloads}

    def fetch(evidence_dir, md5, **kwargs):
        return by_md5[md5]

    out = tmp_path / f"{config.name}.json"
    pipeline = ClassifyPipeline(
        dataclasses.replace(config, fetcher=fetch),
        write_metadata(tmp_path / f"{config.name}_in.json", inputs),
        out,
        evidence_base=tmp_path / "ev",
        workers=1,
    )
    rows = {r["file_id"]: r for r in pipeline.run()}
    return rows, json.loads(out.read_text())["metadata"]["details"]


def test_the_sample_map_producer_writes_the_cohort_and_classifies_from_the_name(tmp_path):
    rows, details = _run(
        tmp_path,
        SAMPLE_MAP_CONFIG,
        {MAP: MAP_TEXT, "chr2_sample_map.tsv": "not\ta list\n"},
        [
            (MAP, "m1"),
            ("chr2_sample_map.tsv", "m2"),
            ("HG00096.chr1.hc.vcf.gz", "g1"),
            ("HG00097.chr1.hc.vcf.gz", "g2"),
        ],
    )
    assert set(rows) == {"m1", "m2"}
    assert [i["parent_key"] for i in rows["m1"]["generated_by"]["inputs"]] == ["g1", "g2"]
    assert rows["m2"]["generated_by"] is None
    # A map is a list of files: data_type sample_map, the data's five dimensions not applicable.
    m1 = rows["m1"]["classifications"]
    assert m1["data_type"]["value"] == "sample_map"
    assert {slot: c["status"] for slot, c in m1.items() if slot != "data_type"} == dict.fromkeys(
        [s for s in m1 if s != "data_type"], "not_applicable"
    )
    # A file named like a map that is not one keeps what its name says: nothing.
    assert {c["status"] for c in rows["m2"]["classifications"].values()} == {"not_classified"}
    assert details == {"producer_steps": {"T": {cs.STEPPED: 1, cs.NOT_A_LIST: 1}}}


def test_the_tar_producer_writes_the_workspace_step(tmp_path):
    members = ["./chr1.100000001_100100000/vcfheader.vcf", "./chr1.100000001_100100000/callset.json"]
    rows, details = _run(
        tmp_path,
        TAR_CONFIG,
        {TAR: TarHead(members, header_text(IMPORT)), "chr1.1_100000.tar": TarHead(members, None)},
        [(TAR, "t1"), ("chr1.1_100000.tar", "t2"), (MAP, "m1")],
    )
    assert rows["t1"]["generated_by"]["inputs"][0]["parent_key"] == "m1"
    assert rows["t2"]["generated_by"] is None
    assert rows["t1"]["classifications"]["data_type"]["value"] == "variants"
    assert details == {"producer_steps": {"T": {cs.STEPPED: 1, cs.NO_VCF_HEADER: 1}}}


def test_the_edge_rules_are_declared_with_the_others():
    assert code_rules.MERGE_BY_WORKSPACE_HEADER in code_rules.EDGE_RULES
    assert code_rules.COHORT_BY_SAMPLE_MAP in code_rules.EDGE_RULES
