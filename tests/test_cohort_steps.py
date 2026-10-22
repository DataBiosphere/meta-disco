"""The steps of T2T's joint-calling cohort (#621): a sample map's members, and a GenomicsDB
workspace tar's one input, the map, read from the tar's own ``vcfheader.vcf``."""

import dataclasses
import json

import pytest

from meta_disco import code_rules
from meta_disco import cohort_steps as cs
from meta_disco.evidence import TarHead
from meta_disco.file_types import SAMPLE_MAP_CONFIG, TAR_CONFIG
from meta_disco.header_classifier import CALLSET_FOLDERS, callset_member, workspace_header_member
from meta_disco.models import SOURCE_CONTENT_READ
from meta_disco.pipeline import ClassifyPipeline
from meta_disco.record_keys import RecordKey
from meta_disco.records import REBUILT_LISTS_KEY
from meta_disco.schema.classification_model import GeneratedBy, RebuiltList
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
    step, outcome = reader(tar_head(IMPORT), TAR, "D", None)
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
    assert cs.TarSteps.for_run(records(*entries), KEY, EVIDENCE)(tar_head(IMPORT), TAR, "D", None) == (None, outcome)


def test_a_workspace_naming_another_directory_is_not_this_tars():
    reader = cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)
    assert reader(tar_head(IMPORT), "chr1.1_100000.tar", "D", None) == (None, cs.OUTPUT_NOT_THIS_FILE)


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
    assert cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(tar_head(*lines), TAR, "D", None) == (None, outcome)


def test_an_identical_import_line_twice_is_one_step():
    step, outcome = cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(tar_head(IMPORT, IMPORT), TAR, "D", None)
    assert outcome == cs.STEPPED and step is not None


@pytest.mark.parametrize("name", [TAR, "CHR1.100000001_100100000.TAR.GZ"])
def test_a_tar_is_matched_to_its_workspace_case_folded_less_tar_and_gz(name):
    """The workspace path names the directory: the tar's name less .tar and any .gz, either case (#678)."""
    step, outcome = cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(tar_head(IMPORT), name, "D", None)
    assert outcome == cs.STEPPED and step is not None


def test_unread_names_why_only_for_a_workspace_whose_header_was_not_parsed():
    assert cs.ParsedTarHead(["x/callset.json"], None).unread == cs.NO_VCF_HEADER
    assert cs.ParsedTarHead(["x/callset.json"], None, "reset").unread == cs.VCF_HEADER_UNREADABLE
    # Not a workspace, or a header parsed: nothing to explain.
    assert cs.ParsedTarHead(["reads/a.fastq"], None, "reset").unread is None
    assert tar_head(IMPORT).unread is None


def test_a_tar_whose_header_was_not_read_gives_no_step():
    head = cs.ParsedTarHead(["x/callset.json"], None)
    assert cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(head, TAR, "D", None) == (None, cs.NO_VCF_HEADER)
    # A tar that is no GenomicsDB workspace has no step to read, and is not counted.
    other = cs.ParsedTarHead(["reads/a.fastq"], None)
    assert cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(other, TAR, "D", None) == (None, None)
    failed = cs.ParsedTarHead(["x/callset.json"], None, "ConnectionError: reset")
    assert cs.TarSteps.for_run(records((MAP, "D")), KEY, EVIDENCE)(failed, TAR, "D", None) == (
        None,
        cs.VCF_HEADER_UNREADABLE,
    )
    assert cs.parse_tar_head(TarHead(["a"], None, "reset")).vcf_header_unread == "reset"


def test_only_a_genomicsdb_store_has_its_header_member_kept():
    assert workspace_header_member(["ws/callset.json"]) == "vcfheader.vcf"
    assert workspace_header_member(["ws/vcfheader.vcf"]) == "vcfheader.vcf"
    assert workspace_header_member(["reads/a.fastq", "ws/__array_schema.tdb"]) is None


def test_the_tar_head_is_parsed_once_with_its_header():
    parsed = cs.parse_tar_head(TarHead(["a"], header_text(IMPORT)))
    assert parsed.member_names == ["a"]
    assert parsed.header is not None and [c.step.tool for c in parsed.header.commands] == ["GenomicsDBImport"]
    assert cs.parse_tar_head(TarHead(["a"], None)).header is None


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
    step, outcome = reader(cs.parse_sample_map(MAP_TEXT), MAP, "D", None)
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
    assert map_reader(*entries)(cs.parse_sample_map(MAP_TEXT), MAP, "D", None) == (None, outcome)


def test_two_rows_naming_one_file_decline_the_cohort():
    rows = cs.parse_sample_map(MAP_TEXT.replace("HG00097.chr1", "HG00096.chr1"))
    assert map_reader(("HG00096.chr1.hc.vcf.gz", "D"))(rows, MAP, "D", None) == (None, cs.PARENT_AMBIGUOUS)


def test_a_file_that_is_no_sample_map_gives_no_step():
    assert map_reader(("HG00096.chr1.hc.vcf.gz", "D"))(None, MAP, "D", None) == (None, cs.NOT_A_LIST)


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
    assert details["producer_steps"] == {"T": {cs.STEPPED: 1, cs.NOT_A_LIST: 1}}
    # Its rows' first column names its samples (#668); a file that is no map names none.
    assert rows["m1"]["samples"]["count"] == 2
    assert rows["m1"]["samples"]["named_by"][0]["rule_id"] == code_rules.SAMPLE_MAP_ROWS.id
    assert rows["m2"]["samples"] is None
    assert details["sample_outcomes"] == {"T": {"named": 1, "no_sample": 1}}


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
    # No tar here is one whose callset.json is read (#724): the sample reader counts none.
    assert details == {
        "producer_steps": {"T": {cs.STEPPED: 1, cs.NO_VCF_HEADER: 1}},
        "sample_outcomes": {},
        "unrecognised_samples": {},
        "unread_samples": {},
    }


# --- a workspace's callset.json, read for its samples (#724) ---------------------------------


def callset(*samples: str) -> str:
    return json.dumps({"callsets": [{"sample_name": s, "row_idx": i} for i, s in enumerate(samples)]})


@pytest.mark.parametrize(
    ("text", "samples"),
    [
        (callset("A", "B"), ["A", "B"]),
        (json.dumps({"callsets": {"A": {"row_idx": 0}, "B": {"row_idx": 1}}}), ["A", "B"]),
    ],
)
def test_a_callset_names_its_samples_in_either_shape(text, samples):
    assert cs.callset_samples(text) == samples


@pytest.mark.parametrize(
    "text",
    [
        "[]",
        json.dumps({"callsets": [{"row_idx": 0}]}),
        json.dumps({"callsets": []}),
        json.dumps({"callsets": [{"sample_name": "A"}, {"row_idx": 1}]}),
    ],
)
def test_a_callset_naming_no_sample_is_refused(text):
    with pytest.raises(ValueError):
        cs.callset_samples(text)


WORKSPACE = ["ws/vcfheader.vcf", "ws/callset.json"]
SGDP = "SGDP_CHM13v2/genomics_db"


@pytest.mark.parametrize(
    ("head", "samples", "why"),
    [
        (TarHead(WORKSPACE, callset=callset("A"), callset_read=True), ["A"], None),
        (TarHead(WORKSPACE, callset_read=True), None, cs.NO_CALLSET),
        (TarHead(WORKSPACE, callset_unread="ConnectionError: reset"), None, cs.CALLSET_UNREADABLE),
        (TarHead(WORKSPACE, callset="not json", callset_read=True), None, cs.NOT_A_CALLSET),
        (TarHead(WORKSPACE, callset=json.dumps({"callsets": []}), callset_read=True), None, cs.NOT_A_CALLSET),
        # Not wanted: neither names nor a cause.
        (TarHead(WORKSPACE), None, None),
    ],
)
def test_the_parse_gives_a_callsets_samples_or_why_not(head, samples, why):
    parsed = cs.parse_tar_head(head)
    assert (parsed.samples, parsed.samples_unread) == (samples, why)


@pytest.mark.parametrize(
    ("names", "dataset", "folder", "member"),
    [
        (WORKSPACE, "ANVIL_T2T_CHRY", SGDP, "callset.json"),
        (WORKSPACE, "ANVIL_T2T_CHRY", "SGDP_GRCh38/genomics_db", "callset.json"),
        # The same name in 1000 Genomes' folder, another dataset, no folder, a deeper folder.
        (WORKSPACE, "ANVIL_T2T_CHRY", "1KGP/genomics_db", None),
        (WORKSPACE, "ANVIL_T2T", SGDP, None),
        (WORKSPACE, "ANVIL_T2T_CHRY", None, None),
        (WORKSPACE, "ANVIL_T2T_CHRY", SGDP + "/x", None),
        # No GenomicsDB store.
        (["reads/a.fastq"], "ANVIL_T2T_CHRY", SGDP, None),
    ],
)
def test_only_a_declared_folders_workspaces_have_their_callset_read(names, dataset, folder, member):
    assert SGDP in CALLSET_FOLDERS["ANVIL_T2T_CHRY"]
    assert callset_member(names, dataset, folder) == member


def test_the_tar_producer_reads_each_wanted_callsets_samples_and_counts_each_tar_not_read_by_cause(tmp_path):
    named = callset("simons_data_sample_1", "simons_data_sample_2")
    heads = {
        "s1": TarHead(WORKSPACE, callset=named, callset_read=True),
        "s2": TarHead(WORKSPACE, callset_unread="ConnectionError: reset"),
        "s3": TarHead(WORKSPACE, callset_read=True),
        "s4": TarHead(WORKSPACE, callset="{}", callset_read=True),
        "s5": TarHead(WORKSPACE, callset=callset("simons_data_sample_1", "nobody"), callset_read=True),
        "k1": TarHead(WORKSPACE),
    }
    inputs = [
        {
            "file_id": file_id,
            "file_name": f"chr1.{n}.tar",
            "dataset_id": "D",
            "dataset_title": "ANVIL_T2T_CHRY",
            "file_md5sum": f"{n:032x}",
            "file_size": 1,
            "file_format": ".tar",
            "file_path": f"{'1KGP/genomics_db' if file_id == 'k1' else SGDP}/chr1.{n}.tar",
        }
        for n, file_id in enumerate(heads)
    ]
    by_md5 = {f"{n:032x}": head for n, head in enumerate(heads.values())}
    asked: dict[str, str | None] = {}

    def fetch(evidence_dir, md5, **kwargs):
        asked[md5] = kwargs["samples_member"](WORKSPACE)
        return by_md5[md5]

    out = tmp_path / "tar.json"
    rows = {
        r["file_id"]: r
        for r in ClassifyPipeline(
            dataclasses.replace(TAR_CONFIG, fetcher=fetch),
            write_metadata(tmp_path / "tar_in.json", inputs),
            out,
            evidence_base=tmp_path / "ev",
            workers=1,
        ).run()
    }
    # The fetcher is asked for each tar's samples member with its dataset and folder bound in.
    assert asked[f"{0:032x}"] == "callset.json"
    assert asked[f"{5:032x}"] is None
    assert rows["s1"]["samples"]["count"] == 2
    assert rows["s1"]["samples"]["named_by"] == [
        {"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.TAR_CALLSET_SAMPLES.id}
    ]
    assert all(rows[f]["samples"] is None for f in ("s2", "s3", "s4", "s5", "k1"))
    details = json.loads(out.read_text())["metadata"]["details"]
    # The 1000 Genomes tar's callset was not wanted: it is not counted.
    assert details["sample_outcomes"] == {"ANVIL_T2T_CHRY": {"named": 1, "unread": 3, "unrecognised": 1}}
    assert details["unread_samples"] == {
        "ANVIL_T2T_CHRY": {cs.CALLSET_UNREADABLE: 1, cs.NO_CALLSET: 1, cs.NOT_A_CALLSET: 1}
    }
    assert details["unrecognised_samples"] == {"ANVIL_T2T_CHRY": {"nobody": 1}}


def test_the_callset_rule_is_declared_with_the_sample_rules():
    assert code_rules.TAR_CALLSET_SAMPLES in code_rules.SAMPLE_RULES
    assert TAR_CONFIG.samples is not None and TAR_CONFIG.samples.rule is code_rules.TAR_CALLSET_SAMPLES


def test_the_edge_rules_are_declared_with_the_others():
    assert code_rules.MERGE_BY_WORKSPACE_HEADER in code_rules.EDGE_RULES
    assert code_rules.COHORT_BY_SAMPLE_MAP in code_rules.EDGE_RULES
    assert code_rules.COHORT_BY_REBUILT_SAMPLE_MAP in code_rules.EDGE_RULES


# --- the folder settling a shared name (#717) --------------------------------------------------


def _in_folders(*entries) -> list[dict]:
    """(file name, folder) records of dataset D, keyed f0, f1, …, each stored in its folder."""
    return [
        {"file_id": f"f{n}", "file_name": name, "dataset_id": "D", "file_path": f"{folder}/{name}"}
        for n, (name, folder) in enumerate(entries)
    ]


def test_a_tar_takes_the_sample_map_of_that_name_in_its_own_folder():
    reader = cs.TarSteps.for_run(_in_folders((MAP, "SGDP_CHM13v2"), (MAP, "SGDP_GRCh38")), KEY, EVIDENCE)
    step, outcome = reader(tar_head(IMPORT), TAR, "D", "SGDP_GRCh38")
    assert outcome == cs.STEPPED and step is not None
    assert [i["parent_key"] for i in step["inputs"]] == ["f1"]
    assert reader(tar_head(IMPORT), TAR, "D", "1KGP") == (None, cs.PARENT_AMBIGUOUS)


def test_a_sample_map_takes_each_member_of_that_name_in_its_own_folder():
    gvcfs = ("HG00096.chr1.hc.vcf.gz", "HG00097.chr1.hc.vcf.gz")
    reader = cs.SampleMapSteps.for_run(_in_folders(*((g, f) for f in ("a", "b") for g in gvcfs)), KEY, EVIDENCE)
    step, outcome = reader(cs.parse_sample_map(MAP_TEXT), MAP, "D", "b")
    assert outcome == cs.STEPPED and step is not None
    assert [i["parent_key"] for i in step["inputs"]] == ["f2", "f3"]


# --- a sample map rebuilt from the tars that read it (#726) ------------------------------------

T2T = "ANVIL_T2T_CHRY"
CHM13 = "SGDP_CHM13v2"
GRCH38 = "SGDP_GRCh38"
XX, XY = "simons_data_sample_1", "simons_data_sample_2"


def import_of(map_name: str) -> str:
    return IMPORT.replace("chr1_sample_map.tsv", map_name)


def sgdp_head(map_name: str, *samples: str) -> cs.ParsedTarHead:
    """An SGDP workspace's head: its header naming ``map_name``, its callset.json listing ``samples``."""
    head = TarHead(
        ["./chr1.100000001_100100000/vcfheader.vcf", "./chr1.100000001_100100000/callset.json"],
        header_text(import_of(map_name)),
        callset=callset(*samples) if samples else None,
        callset_read=True,
    )
    return cs.parse_tar_head(head)


def stored(*paths: str, dataset: str = T2T) -> list[dict]:
    """A record per path, of one dataset, keyed f0, f1, …"""
    return [
        {
            "file_id": f"f{n}",
            "file_name": path.rsplit("/", 1)[1],
            "dataset_id": "D",
            "dataset_title": dataset,
            "file_path": path,
        }
        for n, path in enumerate(paths)
    ]


def gvcf(reference: str, folder: str, name: str) -> str:
    return f"{reference}/{cs.GVCF_FOLDER}/{folder}/{name}"


# Both references' gVCFs, one name each: only the tar's own reference folder's are its members.
CHR1 = [gvcf(r, "chr1", f"{s}.chr1.hc.vcf.gz") for r in (CHM13, GRCH38) for s in (XX, XY)]
CHRX = [
    gvcf(CHM13, "XX_samples_chrX", f"{XX}.chrX.hc.vcf.gz"),
    gvcf(CHM13, "XY_samples_chrX-PAR", f"{XY}.chrX_PAR.hc.vcf.gz"),
    gvcf(CHM13, "XY_samples_chrX-nonPAR", f"{XY}.chrX_non_PAR.hc.vcf.gz"),
]


@pytest.mark.parametrize(
    ("map_name", "layout"),
    [
        ("chr1_sample_map.tsv", (("chr1", ".chr1.hc.vcf.gz"),)),
        ("chr22_sample_map.tsv", (("chr22", ".chr22.hc.vcf.gz"),)),
        (
            "chrX_PAR1_sample_map.tsv",
            (("XX_samples_chrX", ".chrX.hc.vcf.gz"), ("XY_samples_chrX-PAR", ".chrX_PAR.hc.vcf.gz")),
        ),
        (
            "chrX_PAR2_sample_map.tsv",
            (("XX_samples_chrX", ".chrX.hc.vcf.gz"), ("XY_samples_chrX-PAR", ".chrX_PAR.hc.vcf.gz")),
        ),
        (
            "chrX_non_PAR_sample_map.tsv",
            (("XX_samples_chrX", ".chrX.hc.vcf.gz"), ("XY_samples_chrX-nonPAR", ".chrX_non_PAR.hc.vcf.gz")),
        ),
        ("chrY_sample_map.tsv", (("XY_samples_chrY-nonPAR", ".chrY.hc.vcf.gz"),)),
        ("chr23_sample_map.tsv", None),
        ("chrX_sample_map.tsv", None),
        ("chrM_sample_map.tsv", None),
        ("CHR1_sample_map.tsv", None),
    ],
)
def test_the_layout_places_each_maps_gvcfs(map_name, layout):
    assert cs.gvcf_layout(map_name) == layout


def test_a_declared_folders_tar_reads_through_the_list_rebuilt_from_its_own_samples():
    reader = cs.TarSteps.for_run(stored(*CHR1), KEY, EVIDENCE)
    step, outcome = reader(sgdp_head(MAP, XX, XY), TAR, "D", f"{GRCH38}/genomics_db")
    assert outcome == cs.STEPPED and step is not None
    (used,) = step["inputs"]
    assert step["activity"] == "CohortMergeActivity" and used["role"] == "input_list"
    assert used["parent_file"] == MAP and "parent_key" not in used
    assert used["named_by"] == [
        {"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.MERGE_BY_WORKSPACE_HEADER.id}
    ]
    (rebuilt,) = reader.rebuilt_lists()
    assert used["parent_ref"] == rebuilt["ref"]
    assert rebuilt["ref"].startswith(f"rebuilt:{T2T}/{GRCH38}/{MAP}#")
    assert (rebuilt["dataset"], rebuilt["file_name"]) == (T2T, MAP)
    members = rebuilt["generated_by"]
    assert members["activity"] == "CohortDefinitionActivity"
    # The GRCh38 folder's two gVCFs, not CHM13v2's of the same names.
    assert [(i["role"], i["parent_key"]) for i in members["inputs"]] == [("member", "f2"), ("member", "f3")]
    # The address's digest is over the members' record keys, not their names.
    assert rebuilt["ref"].endswith("#" + cs.set_id(["f2", "f3"]))
    assert cs.set_id(["f2", "f3"]) != cs.set_id(i["parent_file"] for i in members["inputs"])
    assert members["named_by"] == [
        {"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.COHORT_BY_REBUILT_SAMPLE_MAP.id}
    ]
    GeneratedBy.model_validate(step)
    RebuiltList.model_validate(rebuilt)


@pytest.mark.parametrize(
    ("map_name", "members"),
    [
        # An XX sample's whole-chrX gVCF either way; an XY sample's PAR or non-PAR one by the map.
        ("chrX_PAR1_sample_map.tsv", ["f0", "f1"]),
        ("chrX_non_PAR_sample_map.tsv", ["f0", "f2"]),
    ],
)
def test_on_chrx_the_map_decides_an_xy_samples_gvcf(map_name, members):
    reader = cs.TarSteps.for_run(stored(*CHRX), KEY, EVIDENCE)
    _, outcome = reader(sgdp_head(map_name, XX, XY), TAR, "D", f"{CHM13}/genomics_db")
    assert outcome == cs.STEPPED
    (rebuilt,) = reader.rebuilt_lists()
    assert [i["parent_key"] for i in rebuilt["generated_by"]["inputs"]] == members


def test_tars_reading_one_list_name_it_once_and_another_set_of_samples_is_another_list():
    reader = cs.TarSteps.for_run(stored(*CHR1), KEY, EVIDENCE)
    first, _ = reader(sgdp_head(MAP, XX, XY), TAR, "D", f"{CHM13}/genomics_db")
    again, _ = reader(sgdp_head(MAP, XY, XX), TAR, "D", f"{CHM13}/genomics_db")
    fewer, _ = reader(sgdp_head(MAP, XX), TAR, "D", f"{CHM13}/genomics_db")
    assert first is not None and again is not None and fewer is not None
    assert first["inputs"][0]["parent_ref"] == again["inputs"][0]["parent_ref"]
    assert fewer["inputs"][0]["parent_ref"] != first["inputs"][0]["parent_ref"]
    lists = reader.rebuilt_lists()
    assert sorted(len(r["generated_by"]["inputs"]) for r in lists) == [1, 2]
    # By address, so a run writes them in one order whatever order its threads read the tars in.
    assert [r["ref"] for r in lists] == sorted(r["ref"] for r in lists)


@pytest.mark.parametrize(
    ("paths", "map_name", "samples", "outcome"),
    [
        (CHR1, "chrM_sample_map.tsv", (XX,), cs.MAP_NOT_IN_LAYOUT),
        (CHR1, MAP, (), cs.NO_SAMPLES),
        (CHR1, MAP, (XX, "simons_data_sample_3"), cs.MEMBER_NOT_FOUND),
        # A gVCF of that name, but in the other reference's folder.
        (CHR1[2:], MAP, (XX,), cs.MEMBER_NOT_FOUND),
        (CHR1, MAP, (XX, XX), cs.MEMBER_AMBIGUOUS),
        # Two names one gVCF carries up to case are one sample listed twice.
        (CHR1, MAP, (XX, XX.upper()), cs.MEMBER_AMBIGUOUS),
        # Two files of one name, up to case, in the folder.
        ([*CHR1, gvcf(CHM13, "chr1", f"{XX.upper()}.chr1.hc.vcf.gz")], MAP, (XX,), cs.MEMBER_AMBIGUOUS),
        # An XY sample with both chrX gVCFs placed for one map would be two members for one sample.
        (
            [*CHRX, gvcf(CHM13, "XX_samples_chrX", f"{XY}.chrX.hc.vcf.gz")],
            "chrX_PAR1_sample_map.tsv",
            (XY,),
            cs.MEMBER_AMBIGUOUS,
        ),
    ],
)
def test_a_list_missing_a_member_or_with_two_for_a_sample_is_not_rebuilt(paths, map_name, samples, outcome):
    reader = cs.TarSteps.for_run(stored(*paths), KEY, EVIDENCE)
    assert reader(sgdp_head(map_name, *samples), TAR, "D", f"{CHM13}/genomics_db") == (None, outcome)
    assert reader.rebuilt_lists() == []


def test_a_tar_outside_the_declared_folders_looks_for_the_catalog_map():
    reader = cs.TarSteps.for_run(stored(*CHR1, f"1KGP/sample_maps/{MAP}"), KEY, EVIDENCE)
    step, outcome = reader(sgdp_head(MAP, XX, XY), TAR, "D", "1KGP/genomics_db")
    assert outcome == cs.STEPPED and step is not None
    assert step["inputs"][0]["parent_key"] == "f4"
    # Another dataset's folder of that name is not declared either.
    other = cs.TarSteps.for_run(stored(*CHR1, dataset="OTHER"), KEY, EVIDENCE)
    assert other(sgdp_head(MAP, XX, XY), TAR, "D", f"{CHM13}/genomics_db") == (None, cs.PARENT_NOT_FOUND)
    assert reader.rebuilt_lists() == other.rebuilt_lists() == []


def test_a_declared_folder_never_takes_a_catalog_map():
    reader = cs.TarSteps.for_run(stored(*CHR1, f"{CHM13}/genomics_db/{MAP}"), KEY, EVIDENCE)
    step, _ = reader(sgdp_head(MAP, XX, XY), TAR, "D", f"{CHM13}/genomics_db")
    assert step is not None and "parent_key" not in step["inputs"][0]


def test_every_folder_whose_lists_are_rebuilt_has_its_callset_read():
    for dataset, folders in cs.REBUILT_MAP_FOLDERS.items():
        assert set(folders) <= CALLSET_FOLDERS[dataset]


def test_the_tar_producer_writes_each_rebuilt_list_once_beside_its_records(tmp_path):
    heads = {
        f"t{n}": TarHead(
            ["./chr1.100000001_100100000/vcfheader.vcf"],
            header_text(IMPORT),
            callset=callset(XX, XY),
            callset_read=True,
        )
        for n in range(2)
    }
    inputs = [
        {
            "file_id": file_id,
            "file_name": TAR,
            "dataset_id": "D",
            "dataset_title": T2T,
            "file_md5sum": f"{n:032x}",
            "file_size": 1,
            "file_format": ".tar",
            "file_path": f"{CHM13}/genomics_db/{TAR}",
        }
        for n, file_id in enumerate(heads)
    ] + [
        {**record, "file_md5sum": f"{9:031x}{n}", "file_size": 1, "file_format": ".vcf.gz", "file_id": f"g{n}"}
        for n, record in enumerate(stored(*CHR1))
    ]
    by_md5 = {f"{n:032x}": head for n, head in enumerate(heads.values())}
    out = tmp_path / "tar.json"
    rows = {
        r["file_id"]: r
        for r in ClassifyPipeline(
            dataclasses.replace(TAR_CONFIG, fetcher=lambda evidence_dir, md5, **kwargs: by_md5[md5]),
            write_metadata(tmp_path / "tar_in.json", inputs),
            out,
            evidence_base=tmp_path / "ev",
            workers=2,
        ).run()
    }
    written = json.loads(out.read_text())
    (rebuilt,) = written[REBUILT_LISTS_KEY]
    assert [i["parent_key"] for i in rebuilt["generated_by"]["inputs"]] == ["g0", "g1"]
    assert {rows[t]["generated_by"]["inputs"][0]["parent_ref"] for t in heads} == {rebuilt["ref"]}
    assert written["metadata"]["details"]["producer_steps"] == {T2T: {cs.STEPPED: 2}}


def test_a_record_of_another_type_with_a_drifted_dataset_id_does_not_stop_the_tar_reader():
    drifted = {"file_id": "b1", "file_name": "a.bam", "dataset_id": ["D"], "dataset_title": T2T}
    reader = cs.TarSteps.for_run([*stored(*CHR1), drifted], KEY, EVIDENCE)
    _, outcome = reader(sgdp_head(MAP, XX, XY), TAR, "D", f"{CHM13}/genomics_db")
    assert outcome == cs.STEPPED
