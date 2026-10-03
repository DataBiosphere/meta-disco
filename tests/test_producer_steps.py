"""The producer step read from a VCF header (#609): command lines as steps, the end of their
data flow as the step that made the file, and the VCF producer turning a HaplotypeCaller into
a VariantCallActivity whose parent resolves by name within the dataset."""

import dataclasses
import json

import pytest

from meta_disco import code_rules
from meta_disco import producer_steps as ps
from meta_disco.file_types import VCF_CONFIG
from meta_disco.models import SOURCE_CONTENT_READ
from meta_disco.output_utils import run_file_metadata
from meta_disco.pipeline import ClassifyPipeline, RecordKey
from meta_disco.reconcile import header_step_counts
from tests.metadata_fixtures import write_metadata

KEY = RecordKey("file_id", "file_id")


def gatk4(tool: str, command: str) -> str:
    return f'##GATKCommandLine=<ID={tool},CommandLine="{tool} {command}",Version="4.1.9.0",Date="April 12, 2021">'


def header(*lines: str) -> str:
    return "\n".join(["##fileformat=VCFv4.2", *lines, "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"])


def steps(text: str) -> list[ps.Step]:
    found = ps.steps_of(text)
    assert found is not None
    return found


def made(text: str, file_name: str) -> ps.Step:
    step, outcome = ps.producing_step(text, file_name)
    assert outcome == ps.STEPPED and step is not None
    return step


HC = gatk4(
    "HaplotypeCaller",
    "--sample-ploidy 2 --emit-ref-confidence GVCF --output HG00096.chr10.hc.vcf --intervals chr10 "
    "--input ./HG00096.cram --reference t2t.fa",
)
GATK3_HC = (
    '##GATKCommandLine.HaplotypeCaller=<ID=HaplotypeCaller,CommandLineOptions="analysis_type=HaplotypeCaller '
    "input_file=[/data/analysis/Sample_HG04164/analysis/HG04164.final.bam] showFullBamList=false "
    'intervals=[chr1] reference_sequence=/ref/GRCh38.fa",Date="Sat Dec 08 16:51:04 EST 2018",Version=3.5-0-g36282e4>'
)
# T2T's joint calling, as its region and chromosome VCFs carry it: the first region's
# GenomicsDBImport and SelectVariants ride along in every later file, in GATK's sorted order.
IMPORT = gatk4(
    "GenomicsDBImport",
    "--genomicsdb-workspace-path ./chr1.100000001_100100000 --batch-size 50 "
    "--sample-name-map gs://b/sample_maps/chr1_sample_map.tsv --reader-threads 6",
)
SELECT = gatk4(
    "SelectVariants",
    "--output chr1.100000001_100100000.genotyped.vcf --variant chr1.100000001_100100000.margined.genotyped.vcf.gz",
)
CONCAT = (
    "##bcftools_concatCommand=concat -a -D --threads 4 -o chr1.genotyped.vcf "
    "/cromwell_root/x/chr1.1_100000.genotyped.vcf.gz /cromwell_root/y/chr1.100000001_100100000.genotyped.vcf.gz"
    "; Date=Wed Apr 14 19:11:18 2021"
)
VQSR_SNP = gatk4("ApplyVQSR", "--output 1kgp.chr1.recalibrated.snp.vcf --variant chr1.genotyped.vcf --mode SNP")
VQSR_INDEL = gatk4(
    "ApplyVQSR", "--output 1kgp.chr1.recalibrated.snp_indel.vcf --variant 1kgp.chr1.recalibrated.snp.vcf --mode INDEL"
)
PASS = (
    "##bcftools_viewCommand=view -f PASS /cromwell_root/z/1kgp.chr1.recalibrated.snp_indel.vcf.gz; Date=Sun Apr 18 2021"
)


# --- reading command lines ---------------------------------------------------------------


def test_a_gatk4_line_is_its_tools_inputs_and_output():
    (step,) = steps(header(HC))
    assert step == ps.Step(ps.GATK, "HaplotypeCaller", ("./HG00096.cram",), "HG00096.chr10.hc.vcf")


def test_a_gatk3_line_reads_its_key_value_options_and_names_no_output():
    (step,) = steps(header(GATK3_HC))
    assert step == ps.Step(
        ps.GATK3, "HaplotypeCaller", ("/data/analysis/Sample_HG04164/analysis/HG04164.final.bam",), None
    )


def test_a_bcftools_line_takes_positional_inputs_past_options_with_and_without_values():
    (step,) = steps(header(CONCAT))
    assert step.tool == "concat"
    assert step.output == "chr1.genotyped.vcf"
    assert [i.rsplit("/", 1)[-1] for i in step.inputs] == [
        "chr1.1_100000.genotyped.vcf.gz",
        "chr1.100000001_100100000.genotyped.vcf.gz",
    ]


def test_bcftools_without_an_output_option_writes_to_stdout():
    (step,) = steps(header(PASS))
    assert step.output is None
    assert step.inputs == ("/cromwell_root/z/1kgp.chr1.recalibrated.snp_indel.vcf.gz",)


def test_identical_lines_are_one_step_and_other_lines_are_not_steps():
    assert len(steps(header(HC, HC, "##source=HaplotypeCaller", "##contig=<ID=chr1,length=10>"))) == 1


def test_an_undeclared_tool_is_no_reading_at_all():
    assert ps.steps_of(header(HC, gatk4("Mutect2", "-I a.bam -O b.vcf"))) is None
    assert ps.steps_of(header("##bcftools_normCommand=norm -m -any in.vcf.gz; Date=x")) is None


# --- the end of the data flow ------------------------------------------------------------


def test_a_lone_haplotypecaller_made_its_file():
    assert made(header(HC), "HG00096.chr10.hc.vcf.gz").tool == "HaplotypeCaller"


@pytest.mark.parametrize(
    ("lines", "file_name", "tool"),
    [
        # concat consumes SelectVariants' output; the import's workspace names another file
        ((IMPORT, SELECT, CONCAT), "chr1.genotyped.vcf.gz", "concat"),
        # the indel pass consumes the SNP pass, which consumes concat: the file is the indel pass's
        ((VQSR_INDEL, VQSR_SNP, IMPORT, SELECT, CONCAT), "1kgp.chr1.recalibrated.snp_indel.vcf.gz", "ApplyVQSR"),
    ],
)
def test_the_producer_is_the_end_of_the_flow_not_the_last_line(lines, file_name, tool):
    assert made(header(*lines), file_name).tool == tool


def test_a_stdout_end_beside_an_end_set_aside_declines():
    # The PASS filter writes to stdout. The import's workspace is an end too, set aside for
    # naming another file, so nothing says the unnamed end made this one (#610 revisits it).
    lines = (VQSR_INDEL, VQSR_SNP, IMPORT, SELECT, CONCAT, PASS)
    assert ps.producing_step(header(*lines), "1kgp.chr1.recalibrated.snp_indel.pass.vcf.gz") == (
        None,
        ps.NO_SINGLE_END,
    )


def test_the_indel_pass_is_found_wherever_gatk_sorted_it():
    lines = (VQSR_SNP, IMPORT, CONCAT, VQSR_INDEL, SELECT)
    assert (
        made(header(*lines), "1kgp.chr1.recalibrated.snp_indel.vcf.gz").output == "1kgp.chr1.recalibrated.snp_indel.vcf"
    )


def test_two_unnamed_ends_decline():
    a = "##bcftools_viewCommand=view -f PASS /p/x.vcf.gz; Date=x"
    b = "##bcftools_viewCommand=view -s AFR /p/x.pass.vcf; Date=y"
    assert ps.producing_step(header(a, b), "x.pass.AFR.vcf.gz")[1] == ps.NO_SINGLE_END


def test_an_end_that_names_another_file_is_not_this_files_producer():
    assert ps.producing_step(header(HC), "HG00096.chr11.hc.vcf.gz")[1] == ps.OUTPUT_NOT_THIS_FILE


def test_a_header_with_no_command_line_or_an_undeclared_tool_declines():
    assert ps.producing_step(header("##source=Sniffles2"), "x.vcf.gz")[1] == ps.NO_COMMAND_LINE
    assert ps.producing_step(header(gatk4("Mutect2", "-O x.vcf")), "x.vcf.gz")[1] == ps.UNKNOWN_TOOL


# --- the step a producing HaplotypeCaller gives ------------------------------------------


def reader(*entries) -> ps.HeaderSteps:
    """A run's step reader over these (file name, dataset) records, keyed by ``file_id`` f0, f1, …"""
    records = [{"file_id": f"f{n}", "file_name": name, "dataset_id": ds} for n, (name, ds) in enumerate(entries)]
    return ps.HeaderSteps.for_run(records, KEY)


def test_a_haplotypecaller_calls_from_the_one_alignment_of_that_name_in_the_dataset():
    step, outcome = reader(("HG00096.cram", "D"), ("HG00096.cram", "OTHER"))(header(HC), "HG00096.chr10.hc.vcf.gz", "D")
    assert outcome == ps.STEPPED
    assert step is not None and step["activity"] == "VariantCallActivity"
    (used,) = step["inputs"]
    assert (used["role"], used["parent_file"], used["parent_key"], used["parent_kind"]) == (
        "calls_from",
        "HG00096.cram",
        "f0",
        "alignment",
    )
    assert used["named_by"] == [{"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.VARIANT_CALL_BY_HEADER.id}]


@pytest.mark.parametrize(
    ("entries", "outcome"),
    [
        ((("HG00096.cram", "OTHER"),), ps.PARENT_NOT_FOUND),
        ((("HG00096.cram", "D"), ("hg00096.CRAM", "D")), ps.PARENT_AMBIGUOUS),
    ],
)
def test_a_parent_no_file_or_two_files_of_the_dataset_carry_gives_no_step(entries, outcome):
    assert reader(*entries)(header(HC), "HG00096.chr10.hc.vcf.gz", "D") == (None, outcome)


def test_a_gatk3_haplotypecaller_resolves_by_the_inputs_base_name():
    step, outcome = reader(("HG04164.final.bam", "D"))(header(GATK3_HC), "HG04164.haplotypeCalls.er.raw.g.vcf.gz", "D")
    assert outcome == ps.STEPPED and step is not None
    assert step["inputs"][0]["parent_file"] == "HG04164.final.bam"


def test_any_other_producing_step_gives_no_step_yet():
    step = reader(("chr1.genotyped.vcf.gz", "D"))(header(IMPORT, SELECT, CONCAT), "chr1.genotyped.vcf.gz", "D")
    assert step == (None, ps.NO_ACTIVITY)


def test_the_reader_keeps_only_the_records_a_rule_could_take_as_a_parent():
    held = reader(("HG00096.cram", "D"), ("HG00096.chr1.hc.vcf.gz", "D"), ("notes.txt", "D")).index
    assert [name for _, name in held] == ["hg00096.cram"]
    ((record,),) = held.values()
    assert record == {"file_name": "HG00096.cram", "file_id": "f0", "dataset_id": "D"}


def test_the_edge_rule_is_declared_with_the_others():
    assert code_rules.VARIANT_CALL_BY_HEADER in code_rules.EDGE_RULES
    assert code_rules.VARIANT_CALL_BY_HEADER.source_type == SOURCE_CONTENT_READ


# --- the VCF producer --------------------------------------------------------------------


def test_the_vcf_producer_writes_the_step_and_counts_every_outcome(tmp_path):
    records: list[dict] = [
        {"file_id": "c1", "file_name": "HG00096.cram", "dataset_id": "D", "dataset_title": "T"},
        {"file_id": "c2", "file_name": "HG00097.cram", "dataset_id": "D", "dataset_title": "T"},
        {"file_id": "c3", "file_name": "HG00097.cram", "dataset_id": "D", "dataset_title": "T"},
        {"file_id": "v1", "file_name": "HG00096.chr10.hc.vcf.gz", "dataset_id": "D", "dataset_title": "T"},
        {"file_id": "v2", "file_name": "HG00097.chr10.hc.vcf.gz", "dataset_id": "D", "dataset_title": "T"},
    ]
    for n, record in enumerate(records):
        record.update(file_md5sum=f"{n:032x}", file_size=1, file_format=record["file_name"].split(".", 1)[1])
    headers = {
        f"{3:032x}": header(HC),
        f"{4:032x}": header(HC.replace("HG00096", "HG00097")),
    }

    def fetch(evidence_dir, md5, **kwargs):
        return headers[md5]

    config = dataclasses.replace(VCF_CONFIG, fetcher=fetch)
    pipeline = ClassifyPipeline(
        config,
        write_metadata(tmp_path / "in.json", records),
        tmp_path / "vcf.json",
        evidence_base=tmp_path / "ev",
        workers=1,
    )
    rows = {r["file_id"]: r for r in pipeline.run()}
    assert rows["v1"]["generated_by"]["inputs"][0]["parent_key"] == "c1"
    assert rows["v2"]["generated_by"] is None
    written = json.loads((tmp_path / "vcf.json").read_text())
    assert written["metadata"]["details"] == {"producer_steps": {"T": {ps.STEPPED: 1, ps.PARENT_AMBIGUOUS: 1}}}


def test_a_files_metadata_block_is_read_from_its_head_and_otherwise_from_the_whole_file(tmp_path):
    block = {"complete": True, "details": {"producer_steps": {"T": {"stepped": 2}}}}
    leading = tmp_path / "vcf_classifications.json"
    leading.write_text(json.dumps({"metadata": block, "classifications": [{"file_name": "x"}]}, indent=2))
    assert run_file_metadata(leading) == block
    trailing = tmp_path / "bam_classifications.json"
    trailing.write_text(json.dumps({"classifications": [], "metadata": block}))
    assert run_file_metadata(trailing) == block
    bare = tmp_path / "bed_classifications.json"
    bare.write_text(json.dumps({"classifications": []}))
    assert run_file_metadata(bare) is None


def test_a_runs_header_steps_are_summed_per_dataset_over_its_files(tmp_path):
    def write(name, steps):
        details = {"producer_steps": steps} if steps is not None else None
        (tmp_path / name).write_text(json.dumps({"metadata": {"details": details}, "classifications": []}))

    write("vcf_classifications.json", {"T": {"stepped": 2, "no_activity": 1}, "U": {"stepped": 1}})
    write("bam_classifications.json", None)
    assert header_step_counts(tmp_path) == {"T": {"stepped": 2, "no_activity": 1}, "U": {"stepped": 1}}


def test_a_quoted_input_is_read_without_its_quotes():
    # Inside GATK's quoted `CommandLine="…"` attribute a quote is written `\"`.
    (step,) = steps(header(gatk4("HaplotypeCaller", '--input \\"/x/HG00096.cram\\" --output HG00096.chr1.hc.vcf')))
    assert step.inputs == ("/x/HG00096.cram",)


def test_any_other_tools_command_line_is_an_undeclared_tool():
    dragen = '##DRAGENCommandLine=<ID=dragen,Version="SW: 4.2",CommandLine="dragen -f -r /ref --vc-target-bed x">'
    assert ps.producing_step(header(dragen), "x.vcf.gz") == (None, ps.UNKNOWN_TOOL)


def test_a_bcftools_short_option_with_its_value_attached_takes_no_next_word():
    (step,) = steps(header("##bcftools_concatCommand=concat -a -Oz -o chr1.vcf.gz a.vcf.gz b.vcf.gz; Date=x"))
    assert (step.output, step.inputs) == ("chr1.vcf.gz", ("a.vcf.gz", "b.vcf.gz"))


def test_an_unnamed_end_beside_one_set_aside_for_another_file_is_not_taken():
    joint = gatk4("GenotypeGVCFs", "--variant a.g.vcf.gz -O joint.vcf.gz")
    assert ps.producing_step(header(GATK3_HC, joint), "cohort.vcf.gz") == (None, ps.NO_SINGLE_END)
    assert made(header(GATK3_HC), "HG04164.haplotypeCalls.er.raw.g.vcf.gz").tool == "HaplotypeCaller"


def test_a_candidate_parent_with_no_record_key_stops_the_run_when_the_reader_is_built():
    with pytest.raises(ValueError, match="file_id"):
        ps.HeaderSteps.for_run([{"file_name": "HG00096.cram", "dataset_id": "D"}], KEY)


def test_the_vcf_producer_refuses_an_input_naming_no_repository_before_any_work(tmp_path):
    path = tmp_path / "in.ndjson"
    path.write_text(json.dumps({"file_id": "v1", "file_name": "x.vcf.gz", "file_md5sum": "0" * 32}) + "\n")
    with pytest.raises(ValueError):
        ClassifyPipeline(VCF_CONFIG, path, tmp_path / "vcf.json", evidence_base=tmp_path / "ev").run()
