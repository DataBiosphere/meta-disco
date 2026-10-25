"""A bcftools stats report's step to the VCF it reports on, and its samples, read from its own text (#683)."""

import dataclasses

import pytest

from meta_disco import bcftools_stats as bs
from meta_disco import code_rules
from meta_disco.fetchers import FetchError
from meta_disco.file_name import FileName
from meta_disco.file_types import BCFTOOLS_STATS_CONFIG, PSAM_CONFIG
from meta_disco.models import SOURCE_CONTENT_READ
from meta_disco.pipeline import _fetch_and_classify
from meta_disco.producers import producer_of
from tests.test_cohort_steps import in_folders, run_producer
from tests.test_producer_steps import EVIDENCE, KEY

VCF = "1kgp.chr15.recalibrated.snp_indel.pass.singleton.KHV_singleton.variants.vcf.gz"
CROMWELL = "/cromwell_root/fc-5/f7/filter_ac_variants/9d/call-bgzip_bcftools_index/"


# The definition lines bcftools stats 1.9 writes above its `ID`, `IDD` and `PSC` lines, copied from a T2T report.
ID_DEFINITION = "# ID\t[2]id\t[3]tab-separated file names\n"
IDD_DEFINITION = "# IDD\t[2]id\t[3]length (deletions negative)\t[4]count\n"
PSC_DEFINITION = (
    "# PSC\t[2]id\t[3]sample\t[4]nRefHom\t[5]nNonRefHom\t[6]nHets\t[7]nTransitions\t[8]nTransversions"
    "\t[9]nIndels\t[10]average depth\t[11]nSingletons\t[12]nHapRef\t[13]nHapAlt\t[14]nMissing\n"
)


def report_text(*inputs: str, options: str = "", psc: tuple[str, ...] = ()) -> str:
    """A report shaped as bcftools stats 1.9 writes one, cut to the lines read: its two header lines, the
    ``ID`` definition and an ``ID`` line per input, a histogram line, the ``PSC`` definition and ``PSC`` lines."""
    return "".join(
        [
            "# This file was produced by bcftools stats (1.9+htslib-1.9) and can be plotted using plot-vcfstats.\n",
            f"# The command line was:\tbcftools stats  {options}{' '.join(inputs)}\n",
            "#\n",
            ID_DEFINITION,
            *(f"ID\t{n}\t{path}\n" for n, path in enumerate(inputs)),
            IDD_DEFINITION,
            "IDD\t0\t-60\t1023\n",
            PSC_DEFINITION,
            *(
                f"PSC\t0\t{sample}\t5176388\t74864\t159228\t155086\t74882\t52028\t29.9\t3681\t0\t0\t32550\n"
                for sample in psc
            ),
        ]
    )


# --- the parse -------------------------------------------------------------------------------


def test_a_report_names_its_input_on_its_id_line_not_its_idd_lines():
    report = bs.parse_stats_report(report_text(CROMWELL + VCF))
    assert report == bs.StatsReport(inputs=(CROMWELL + VCF,))


def test_a_file_whose_first_line_is_not_bcftools_stats_is_no_report():
    text = "# This file was produced by samtools stats (1.10)\nID\t0\tx.vcf.gz\n"
    assert bs.parse_stats_report(text) is None
    assert bs.parse_stats_report("") is None


@pytest.mark.parametrize("option", ["-v --samples-file /w/MSL.txt ", "-S/w/MSL.txt ", ""])
def test_a_reports_samples_are_its_psc_names_however_its_command_line_reads(option):
    """The `PSC` lines name the samples, not the option that asked for them (`-S/w/MSL.txt` has its value attached)."""
    report = bs.parse_stats_report(report_text(CROMWELL + VCF, options=option, psc=("HG03052", "HG03054")))
    assert report == bs.StatsReport(inputs=(CROMWELL + VCF,), samples=("HG03052", "HG03054"))


def test_a_report_with_no_psc_line_names_no_samples_of_its_own():
    report = bs.parse_stats_report(report_text(CROMWELL + VCF, options="--samples-file /w/MSL.txt "))
    assert report is not None and report.samples is None
    assert not bs.STATS_REPORT_SAMPLES.reads(report) and not bs.STATS_REPORT_SAMPLES.reads(None)


# --- the step --------------------------------------------------------------------------------


def reader(*entries) -> bs.StatsReportSteps:
    return bs.StatsReportSteps.for_run(in_folders(*entries), KEY, EVIDENCE)


def test_a_report_on_one_vcf_of_that_name_is_a_quality_control_step_on_it():
    step, outcome = reader((VCF, "KHV"), ("other.vcf.gz", "KHV"))(
        bs.parse_stats_report(report_text(CROMWELL + VCF)), "x.bcftools.stats.txt", "D", "KHV"
    )
    assert outcome == bs.STEPPED
    assert step == {
        "activity": "QualityControlActivity",
        "named_by": [{"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.QC_REPORT_BY_CONTENT.id}],
        "inputs": [
            {
                "role": "reported_on",
                "parent_file": VCF,
                "parent_key": "f0",
                "parent_kind": "variants",
                "named_by": [{"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.QC_REPORT_BY_CONTENT.id}],
            }
        ],
    }


def test_a_name_three_vcfs_carry_is_settled_by_the_reports_folder():
    """ANVIL_T2T_CHRY's three cohorts each store `chrN.recalibrated.snp_indel.pass.vcf.gz` (#717)."""
    name = "chr6.recalibrated.snp_indel.pass.vcf.gz"
    steps = reader((name, "1KGP/PASS"), (name, "SGDP_CHM13v2/PASS"), (name, "SGDP_GRCh38/PASS"))
    report = bs.parse_stats_report(report_text(CROMWELL + name))
    step, outcome = steps(report, "chr6.bcftools.stats.txt", "D", "SGDP_CHM13v2/PASS")
    assert outcome == bs.STEPPED and step is not None and step["inputs"][0]["parent_key"] == "f1"
    assert steps(report, "chr6.bcftools.stats.txt", "D", "1KGP/unrelated") == (None, bs.PARENT_AMBIGUOUS)


@pytest.mark.parametrize(
    ("report", "outcome"),
    [
        (None, bs.NOT_A_REPORT),
        (bs.parse_stats_report(report_text()), bs.NO_INPUT),
        (bs.parse_stats_report(report_text(CROMWELL + VCF, "/w/other.vcf.gz")), bs.SEVERAL_INPUTS),
        (bs.parse_stats_report(report_text("/w/sample.cram")), bs.INPUT_NOT_A_VCF),
        (bs.parse_stats_report(report_text("/w/x.Homo_sapiens_assembly38.liftover.vcf.gz")), bs.PARENT_NOT_FOUND),
    ],
)
def test_a_report_gives_no_step_unless_its_one_input_is_one_vcf_of_the_dataset(report, outcome):
    assert reader((VCF, "KHV"), ("sample.cram", "KHV"))(report, "x.bcftools.stats.txt", "D", "KHV") == (None, outcome)


# --- the producer ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "producer"),
    [
        ("chr13.recalibrated.snp_indel.pass.bcftools.stats.txt", "bcftools_stats"),
        ("x_chr22.recalibrated_variants.pass.singleton.AFR_singleton.per_sample.stats.txt", "bcftools_stats"),
        ("1kgp.chr14.recalibrated.snp_indel.pass.singleton.ACB_singleton.chm13_AFR.stats.txt", "bcftools_stats"),
        # samtools stats and HPRC's assembly QC stay the catch-all's.
        ("HG04122.CHM13v2.chrY.samtools.stats.txt", None),
        ("NA18906.qc.stats.txt", None),
    ],
)
def test_the_producer_claims_the_reports_by_name(name, producer):
    routed = producer_of({"file_name": name, "file_format": ".txt"})
    assert (routed.name if routed else None) == producer


def test_the_producer_writes_the_step_and_samples_and_classifies_from_the_name(tmp_path):
    per_sample = "KHV.per_sample.stats.txt"
    plain = "KHV.variants.bcftools.stats.txt"
    not_one = "fake.bcftools.stats.txt"
    entries = [(per_sample, "r1"), (plain, "r2"), (not_one, "r3"), (VCF, "v1")]
    payloads = {
        per_sample: report_text(CROMWELL + VCF, options="-v --samples-file /w/KHV.txt ", psc=("HG03052", "HG03054")),
        plain: report_text(CROMWELL + VCF),
        not_one: "chr\tstart\tend\n",
    }
    rows, details = run_producer(tmp_path, BCFTOOLS_STATS_CONFIG, payloads, entries, folder="KHV")
    assert set(rows) == {"r1", "r2", "r3"}
    assert [i["parent_key"] for i in rows["r1"]["generated_by"]["inputs"]] == ["v1"]
    assert [i["parent_key"] for i in rows["r2"]["generated_by"]["inputs"]] == ["v1"]
    assert rows["r3"]["generated_by"] is None
    # The dimensions are the name's (`text_stats`), whatever the content: the content adds a step and samples.
    for row in rows.values():
        assert {slot: (c["status"], c["value"]) for slot, c in row["classifications"].items()} == {
            "data_type": ("classified", "qc_report"),
            "variant_kind": ("not_applicable", None),
            "variant_origin": ("not_applicable", None),
            **dict.fromkeys(
                ["data_modality", "reference_assembly", "assay_type", "platform", "instrument_model"],
                ("not_classified", None),
            ),
        }
    assert rows["r1"]["samples"]["count"] == 2
    assert rows["r1"]["samples"]["named_by"] == [
        {"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.BCFTOOLS_STATS_SAMPLES.id}
    ]
    # A report with no `PSC` line reads none, and is not counted.
    assert rows["r2"]["samples"] is None and rows["r3"]["samples"] is None
    assert details["producer_steps"] == {"T": {bs.STEPPED: 2, bs.NOT_A_REPORT: 1}}
    assert details["sample_outcomes"] == {"T": {"named": 1}}


def test_a_bcftools_stats_line_not_first_is_no_report():
    assert bs.parse_stats_report("chr\tstart\n" + report_text(CROMWELL + VCF)) is None


def test_a_report_that_cannot_be_read_keeps_what_its_name_says(tmp_path):
    """A failed read keeps the name rule's answers (`answers_from_name`), as the catch-all gave them."""

    def unreadable(*args, **kwargs):
        raise FetchError("connection reset")

    name = "KHV.variants.bcftools.stats.txt"
    classifications, unread, payload = _fetch_and_classify(
        dataclasses.replace(BCFTOOLS_STATS_CONFIG, fetcher=unreadable),
        tmp_path,
        "0" * 32,
        file_name=name,
        name=FileName.parse(name),
        file_size=1,
        file_format=".txt",
        is_gzipped=False,
        use_cache=False,
    )
    assert unread and payload is None
    assert classifications["data_type"]["value"] == "qc_report"
    assert classifications["variant_kind"]["status"] == "not_applicable"


def test_each_name_only_type_binds_its_own_stand_in():
    """With no name, the engine reads the bound stand-in: a `.psam`'s extension rule still fires; a report's
    `text_stats` rule needs the name, so `.txt` alone gives it no data_type."""
    assert PSAM_CONFIG.classifier(None)["data_type"]["value"] == "sample_table"
    assert BCFTOOLS_STATS_CONFIG.classifier(None)["data_type"]["status"] == "not_classified"
