"""The producer step read from a VCF header (#609): command lines as steps, the end of their
data flow as the step that made the file, and the VCF producer turning a HaplotypeCaller into
a VariantCallActivity whose parent resolves by name within the dataset."""

import dataclasses
import json
from pathlib import Path

import pytest

from meta_disco import code_rules, header_classifier
from meta_disco import producer_steps as ps
from meta_disco.evidence import BamEvidence, get_evidence_path
from meta_disco.fetchers import FetchError
from meta_disco.file_types import BAM_CONFIG, VCF_CONFIG
from meta_disco.models import SOURCE_CONTENT_READ
from meta_disco.output_utils import run_file_metadata
from meta_disco.pipeline import ClassifyPipeline
from meta_disco.reconcile import content_step_counts, run_metadata
from meta_disco.record_keys import RecordKey
from meta_disco.validators import header_extractors, reference_builds
from meta_disco.validators.command_lines import BCFTOOLS, GATK, GATK3, TOOL_ARGUMENTS, Step
from meta_disco.validators.header_extractors import VCFHeader, parse_vcf_header
from tests.metadata_fixtures import write_metadata

KEY = RecordKey("file_id", "file_id")
# A step reader's evidence base, never read where a VCF names no contigs (#620's tests make their own).
EVIDENCE = Path("no-evidence")


def gatk4(tool: str, command: str) -> str:
    return f'##GATKCommandLine=<ID={tool},CommandLine="{tool} {command}",Version="4.1.9.0",Date="April 12, 2021">'


def header_text(*lines: str) -> str:
    return "\n".join(["##fileformat=VCFv4.2", *lines, "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"])


def header(*lines: str) -> VCFHeader:
    return parse_vcf_header(header_text(*lines))


def steps(parsed: VCFHeader) -> list[Step]:
    found = ps.steps_of(parsed)
    assert found is not None
    return found


def made(parsed: VCFHeader, file_name: str) -> Step:
    step, outcome = ps.producing_step(parsed, file_name)
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
    assert step == Step(GATK, "HaplotypeCaller", ("./HG00096.cram",), "HG00096.chr10.hc.vcf", mode="GVCF")


def test_a_gatk3_line_reads_its_key_value_options_and_names_no_output():
    (step,) = steps(header(GATK3_HC))
    assert step == Step(GATK3, "HaplotypeCaller", ("/data/analysis/Sample_HG04164/analysis/HG04164.final.bam",), None)


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
    assert ps.steps_of(header(HC, gatk4("LeftAlignAndTrimVariants", "-V a.vcf -O b.vcf"))) is None
    assert ps.steps_of(header("##bcftools_pluginCommand=plugin fill-tags -- -t AF; Date=x")) is None


@pytest.mark.parametrize(
    "line, mode",
    [
        (HC, "GVCF"),
        (gatk4("HaplotypeCaller", "-ERC BP_RESOLUTION -O a.vcf -I a.cram"), "BP_RESOLUTION"),
        (gatk4("HaplotypeCaller", "--emit-ref-confidence=NONE -O a.vcf -I a.cram"), "NONE"),
        (GATK3_HC.replace("showFullBamList=false", "emitRefConfidence=GVCF showFullBamList=false"), "GVCF"),
        (GATK3_HC, None),
        (gatk4("HaplotypeCaller", "-O a.vcf -I a.cram"), None),
        (gatk4("GenotypeGVCFs", "-V a.g.vcf.gz -O a.vcf --emit-ref-confidence GVCF"), None),
    ],
)
def test_a_haplotypecaller_lines_reference_confidence_mode_is_read_in_each_spelling(line, mode):
    """GATK 4's two option spellings, with or without `=`, and GATK 3's `key=value`; a tool
    whose arguments declare no mode option has none, whatever its words (#607)."""
    (step,) = steps(header(line))
    assert step.mode == mode


def test_a_mode_option_given_twice_is_read_as_its_first_value():
    (step,) = steps(header(gatk4("HaplotypeCaller", "-ERC GVCF -O a.vcf -I a.cram --emit-ref-confidence NONE")))
    assert step.mode == "GVCF"


def test_two_lines_alike_but_for_their_mode_are_two_steps_and_name_no_single_producer():
    other = HC.replace("--emit-ref-confidence GVCF", "--emit-ref-confidence NONE")
    assert len(steps(header(HC, other))) == 2
    assert ps.producing_step(header(HC, other), "HG00096.chr10.hc.vcf.gz") == (None, ps.NO_SINGLE_END)


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


def test_a_stdout_end_beside_an_end_set_aside_is_no_end_of_the_flow_but_the_last_line_names_it():
    # The PASS filter writes to stdout. The import's workspace is an end too, set aside for
    # naming another file, so nothing in the flow says the unnamed end made this one; the PASS
    # filter is the header's last line, which does (#771).
    lines = (VQSR_INDEL, VQSR_SNP, IMPORT, SELECT, CONCAT, PASS)
    file_name = "1kgp.chr1.recalibrated.snp_indel.pass.vcf.gz"
    assert ps.end_of_flow(header(*lines), file_name) == (None, ps.NO_SINGLE_END)
    assert made(header(*lines), file_name).options == ("-f",)


def test_the_indel_pass_is_found_wherever_gatk_sorted_it():
    lines = (VQSR_SNP, IMPORT, CONCAT, VQSR_INDEL, SELECT)
    assert (
        made(header(*lines), "1kgp.chr1.recalibrated.snp_indel.vcf.gz").output == "1kgp.chr1.recalibrated.snp_indel.vcf"
    )


def test_two_unnamed_ends_are_no_end_of_the_flow_and_the_last_line_names_the_step():
    a = "##bcftools_viewCommand=view -f PASS /p/x.vcf.gz; Date=x"
    b = "##bcftools_viewCommand=view -s AFR /p/x.pass.vcf; Date=y"
    assert ps.end_of_flow(header(a, b), "x.pass.AFR.vcf.gz")[1] == ps.NO_SINGLE_END
    assert made(header(a, b), "x.pass.AFR.vcf.gz").inputs == ("/p/x.pass.vcf",)


def test_an_end_that_names_another_file_is_not_this_files_producer():
    assert ps.producing_step(header(HC), "HG00096.chr11.hc.vcf.gz")[1] == ps.OUTPUT_NOT_THIS_FILE


def test_a_pvar_never_takes_a_step_from_the_vcf_it_was_converted_from():
    """A `.pvar` keeps its source VCF's command lines, and plink2 adds none of its own, so a
    HaplotypeCaller line naming no output must not become the `.pvar`'s step (#561)."""
    assert ps.producing_step(header(HC), "HG00096.chr11.hc.vcf.gz")[1] == ps.OUTPUT_NOT_THIS_FILE
    assert ps.producing_step(header(HC), "HG00096.chr11.pvar") == (None, ps.NOT_A_VCF)
    assert ps.producing_step(header(HC), "HG00096.chr11.pvar.gz") == (None, ps.NOT_A_VCF)


def test_a_bgz_compares_as_its_vcf():
    assert ps.data_name("dir/ALL.chr1.genotypes.vcf.bgz") == ps.data_name("ALL.chr1.genotypes.vcf")


def test_a_header_with_no_command_line_or_an_undeclared_tool_declines():
    assert ps.producing_step(header("##source=Sniffles2"), "x.vcf.gz")[1] == ps.NO_COMMAND_LINE
    assert ps.producing_step(header(gatk4("LeftAlignAndTrimVariants", "-O x.vcf")), "x.vcf.gz")[1] == ps.UNKNOWN_TOOL


# --- the step a producing HaplotypeCaller gives ------------------------------------------


def reader(*entries, parent: tuple[str, ...] | None = None) -> ps.HeaderSteps:
    """A run's step reader over these (file name, dataset) records, keyed by ``file_id`` f0, f1, …,
    reading every VCF parent's header as ``parent``'s lines (None: unreadable)."""
    records = [{"file_id": f"f{n}", "file_name": name, "dataset_id": ds} for n, (name, ds) in enumerate(entries)]
    steps = ps.HeaderSteps.for_run(records, KEY, EVIDENCE, alignments=BAM_CONFIG.name, variants=VCF_CONFIG.name)
    steps.header_of = lambda record: None if parent is None else header(*parent)
    return steps


def test_a_haplotypecaller_calls_from_the_one_alignment_of_that_name_in_the_dataset():
    step, outcome = reader(("HG00096.cram", "D"), ("HG00096.cram", "OTHER"))(
        header(HC), "HG00096.chr10.hc.vcf.gz", "D", None
    )
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
    assert reader(*entries)(header(HC), "HG00096.chr10.hc.vcf.gz", "D", None) == (None, outcome)


def test_a_gatk3_haplotypecaller_resolves_by_the_inputs_base_name():
    step, outcome = reader(("HG04164.final.bam", "D"))(
        header(GATK3_HC), "HG04164.haplotypeCalls.er.raw.g.vcf.gz", "D", None
    )
    assert outcome == ps.STEPPED and step is not None
    assert step["inputs"][0]["parent_file"] == "HG04164.final.bam"


def test_a_haplotypecaller_with_two_inputs_gives_no_step():
    two = HC.replace("--input ./HG00096.cram", "--input ./HG00096.cram --input ./HG00097.cram")
    entries = (("HG00096.cram", "D"), ("HG00097.cram", "D"))
    assert reader(*entries)(header(two), "HG00096.chr10.hc.vcf.gz", "D", None) == (None, ps.NO_ACTIVITY)


def test_a_path_listed_twice_is_one_input():
    twice = HC.replace("--input ./HG00096.cram", "--input ./HG00096.cram --input ./HG00096.cram")
    step, outcome = reader(("HG00096.cram", "D"))(header(twice), "HG00096.chr10.hc.vcf.gz", "D", None)
    assert outcome == ps.STEPPED and step is not None and len(step["inputs"]) == 1


def test_a_tool_of_a_family_its_rule_does_not_name_gives_no_step(monkeypatch):
    bcftools_only = dataclasses.replace(ps.STEP_RULES["HaplotypeCaller"], families=frozenset({"bcftools"}))
    monkeypatch.setitem(ps.STEP_RULES, "HaplotypeCaller", bcftools_only)
    assert reader(("HG00096.cram", "D"))(header(HC), "HG00096.chr10.hc.vcf.gz", "D", None) == (None, ps.NO_ACTIVITY)


REGIONS = (("chr1.1_100000.genotyped.vcf.gz", "D"), ("chr1.100000001_100100000.genotyped.vcf.gz", "D"))


def test_a_concat_merges_every_region_vcf_it_names_as_a_shard():
    step, outcome = reader(*REGIONS)(header(IMPORT, SELECT, CONCAT), "chr1.genotyped.vcf.gz", "D", None)
    assert outcome == ps.STEPPED and step is not None
    assert step["activity"] == "MergeActivity"
    assert [(i["role"], i["parent_file"], i["parent_key"]) for i in step["inputs"]] == [
        ("shard", "chr1.1_100000.genotyped.vcf.gz", "f0"),
        ("shard", "chr1.100000001_100100000.genotyped.vcf.gz", "f1"),
    ]
    assert step["named_by"] == [{"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.MERGE_BY_HEADER.id}]


@pytest.mark.parametrize(
    ("entries", "outcome"),
    [
        (REGIONS[:1], ps.PARENT_NOT_FOUND),
        ((*REGIONS, ("CHR1.1_100000.genotyped.vcf.gz", "D")), ps.PARENT_AMBIGUOUS),
    ],
)
def test_a_concat_with_an_input_no_file_or_two_files_carry_gives_no_step(entries, outcome):
    assert reader(*entries)(header(IMPORT, SELECT, CONCAT), "chr1.genotyped.vcf.gz", "D", None) == (None, outcome)


def test_a_concat_of_two_paths_with_one_name_gives_no_step():
    """Scatter shards share a name (`shard-0/out.vcf.gz`, `shard-1/out.vcf.gz`): one file carrying it is not both."""
    shards = CONCAT.replace("/cromwell_root/y/chr1.100000001_100100000", "/cromwell_root/y/chr1.1_100000")
    assert reader(*REGIONS)(header(shards), "chr1.genotyped.vcf.gz", "D", None) == (None, ps.PARENT_AMBIGUOUS)


def test_a_concat_reading_an_input_from_stdin_gives_no_step():
    piped = CONCAT.replace(" /cromwell_root/x/chr1.1_100000.genotyped.vcf.gz", " -")
    assert steps(header(piped))[0].stdin
    assert reader(*REGIONS)(header(piped), "chr1.genotyped.vcf.gz", "D", None) == (None, ps.NO_ACTIVITY)


def test_a_concat_of_one_vcf_is_not_a_merge():
    """`concat -o out.vcf.gz in.vcf.gz` recompresses one file; a merge joins two or more."""
    one = CONCAT.replace(" /cromwell_root/y/chr1.100000001_100100000.genotyped.vcf.gz", "")
    assert reader(*REGIONS)(header(one), "chr1.genotyped.vcf.gz", "D", None) == (None, ps.NO_ACTIVITY)


def test_a_concat_naming_an_input_that_is_not_a_vcf_gives_no_step():
    listed = CONCAT.replace("/cromwell_root/x/chr1.1_100000.genotyped.vcf.gz", "/cromwell_root/x/shards.txt")
    entries = (("shards.txt", "D"), *REGIONS)
    assert reader(*entries)(header(listed), "chr1.genotyped.vcf.gz", "D", None) == (None, ps.NO_ACTIVITY)


def test_any_other_producing_step_gives_no_step():
    file_name = "1kgp.chr1.recalibrated.snp_indel.vcf.gz"
    step = reader(("chr1.genotyped.vcf.gz", "D"))(header(VQSR_SNP, VQSR_INDEL), file_name, "D", None)
    assert step == (None, ps.NO_ACTIVITY)


def test_the_reader_keeps_only_the_records_a_rule_could_take_as_a_parent():
    held = reader(("HG00096.cram", "D"), ("HG00096.chr1.hc.vcf.gz", "D"), ("notes.txt", "D")).index
    assert sorted(name for _, name in held) == ["hg00096.chr1.hc.vcf.gz", "hg00096.cram"]
    assert held[("D", "hg00096.cram")] == [{"file_name": "HG00096.cram", "file_id": "f0", "dataset_id": "D"}]


def test_the_edge_rules_are_declared_with_the_others():
    for rule in (
        code_rules.VARIANT_CALL_BY_HEADER,
        code_rules.MERGE_BY_HEADER,
        code_rules.VARIANT_SUBSET_BY_HEADER,
        code_rules.VARIANT_FILTER_BY_HEADER,
        code_rules.VARIANT_SUBSET_BY_LAST_LINE,
        code_rules.VARIANT_FILTER_BY_LAST_LINE,
    ):
        assert rule in code_rules.EDGE_RULES
        assert rule.source_type == SOURCE_CONTENT_READ


# --- a bcftools view: by its options, and on the header's last line (#771) ------------------

# T2T's CHM13 chain as a population subset carries it: the joint calling, the PASS filter to
# stdout, then the subset of that, also to stdout. Two unnamed ends, so the flow has no one end.
CHAIN = (VQSR_INDEL, VQSR_SNP, IMPORT, SELECT, CONCAT, PASS)
PASSED = "1kgp.chr1.recalibrated.snp_indel.pass.vcf.gz"
CEU = "1kgp.chr1.recalibrated.snp_indel.pass.CEU.vcf.gz"


def view(options: str, path: str = f"/cromwell_root/w/{PASSED}") -> str:
    return f"##bcftools_viewCommand=view {options} {path}; Date=Thu Apr 22 03:34:28 2021"


def test_a_view_line_records_each_option_as_written():
    (step,) = steps(header(view("-S /r/CEU.txt --force-samples --min-ac=1 -Oz")))
    assert step.options == ("-S", "--force-samples", "--min-ac", "-O")


def test_every_option_the_view_parser_declares_has_a_declared_effect():
    """The options' effects are declared beside the rules, apart from the parser's ``TOOL_ARGUMENTS``;
    an option the parser learns must be given an effect too, or every view giving it silently gives no step."""
    arguments = TOOL_ARGUMENTS[(BCFTOOLS, "view")]
    declared = ps.VIEW_SUBSET_OPTIONS | ps.VIEW_FILTER_OPTIONS | ps.VIEW_OUTPUT_OPTIONS | ps.VIEW_NO_STEP_OPTIONS
    assert set(arguments.outputs) | set(arguments.no_value) <= declared
    groups = (ps.VIEW_SUBSET_OPTIONS, ps.VIEW_FILTER_OPTIONS, ps.VIEW_OUTPUT_OPTIONS, ps.VIEW_NO_STEP_OPTIONS)
    assert sum(len(g) for g in groups) == len(declared), "an option is in two groups"


def test_two_views_alike_but_for_their_options_are_two_steps_and_name_no_single_producer():
    """Kept as one, the first line's options would decide the activity of a file the second made (#771)."""
    a, b = view("-S a.txt", "/p/tmp.vcf.gz"), view("-f PASS", "/p/tmp.vcf.gz")
    assert len(steps(header(a, b))) == 2
    assert len(steps(header(a, view("-S b.txt", "/p/tmp.vcf.gz")))) == 1
    assert ps.end_of_flow(header(a, b), CEU)[1] == ps.NO_SINGLE_END
    assert made(header(a, b), CEU).options == ("-f",)


@pytest.mark.parametrize(
    ("options", "rule"),
    [
        ("-S /r/CEU.txt --force-samples", code_rules.VARIANT_SUBSET_BY_LAST_LINE),
        ("-R /r/chm13v1_unique_100mer_coverage.bed", code_rules.VARIANT_SUBSET_BY_LAST_LINE),
        ("--min-ac 1", code_rules.VARIANT_FILTER_BY_LAST_LINE),
        (f"-q 1 -Oz -o {CEU}", code_rules.VARIANT_FILTER_BY_LAST_LINE),
    ],
)
def test_a_last_line_view_of_one_vcf_is_a_subset_or_a_filter_of_it_by_its_options(options, rule):
    assert ps.end_of_flow(header(*CHAIN, view(options)), CEU)[1] == ps.NO_SINGLE_END
    step, outcome = reader((PASSED, "D"), parent=CHAIN)(header(*CHAIN, view(options)), CEU, "D", None)
    assert outcome == ps.STEPPED and step is not None
    assert step["activity"] == rule.activity
    (used,) = step["inputs"]
    assert (used["role"], used["parent_file"], used["parent_key"], used["parent_kind"]) == (
        "processed",
        PASSED,
        "f0",
        "variants",
    )
    assert step["named_by"] == [{"source_type": SOURCE_CONTENT_READ, "rule_id": rule.id}]


def test_the_pass_filter_on_the_last_line_names_the_callset_it_filtered():
    """The step the chromosome table states for the PASS callset, so the two agree at reconcile."""
    entries = (("1kgp.chr1.recalibrated.snp_indel.vcf.gz", "D"),)
    step, outcome = reader(*entries, parent=CHAIN[:-1])(header(*CHAIN), PASSED, "D", None)
    assert outcome == ps.STEPPED and step is not None
    assert step["activity"] == "VariantFilterActivity"
    assert step["inputs"][0]["parent_file"] == "1kgp.chr1.recalibrated.snp_indel.vcf.gz"
    assert step["named_by"][0]["rule_id"] == code_rules.VARIANT_FILTER_BY_LAST_LINE.id


def test_a_lone_view_is_the_one_end_of_the_flow_and_takes_its_rule_by_options():
    step, outcome = reader((PASSED, "D"))(header(view("-S /r/CEU.txt --force-samples")), CEU, "D", None)
    assert outcome == ps.STEPPED and step is not None and step["activity"] == "VariantSubsetActivity"
    assert step["named_by"][0]["rule_id"] == code_rules.VARIANT_SUBSET_BY_HEADER.id


def test_a_last_line_view_is_read_where_another_lines_tool_is_undeclared():
    """An undeclared tool's line leaves the chain unread; a later tool's own line would be last, so the view is."""
    unread = gatk4("LeftAlignAndTrimVariants", "-V a.vcf -O b.vcf")
    assert ps.end_of_flow(header(unread, view("-S /r/CEU.txt")), CEU)[1] == ps.UNKNOWN_TOOL
    step, outcome = reader((PASSED, "D"), parent=(unread,))(header(unread, view("-S /r/CEU.txt")), CEU, "D", None)
    assert outcome == ps.STEPPED and step is not None and step["activity"] == "VariantSubsetActivity"
    assert step["named_by"][0]["rule_id"] == code_rules.VARIANT_SUBSET_BY_LAST_LINE.id


CEU_SAMPLES = "\tFORMAT\tHG00096\tHG00097"


def with_samples(parsed: VCFHeader, *samples: str) -> VCFHeader:
    return dataclasses.replace(parsed, sample_columns=samples)


def test_a_last_line_view_is_written_only_where_its_parents_header_fits():
    step = reader((PASSED, "D"), parent=CHAIN)
    assert step(header(*CHAIN, view("-S /r/CEU.txt")), CEU, "D", None)[1] == ps.STEPPED
    # The name resolved, but the file it names is not the one the view read.
    other = reader((PASSED, "D"), parent=(IMPORT, SELECT, CONCAT, "##contig=<ID=chr1,length=248387328>"))
    assert other(header(*CHAIN, view("-S /r/CEU.txt")), CEU, "D", None) == (None, ps.PARENT_HEADER_DIFFERS)
    assert reader((PASSED, "D"))(header(*CHAIN, view("-S /r/CEU.txt")), CEU, "D", None) == (None, ps.PARENT_UNREADABLE)


@pytest.mark.parametrize(
    ("child", "parent", "fits"),
    [
        ((*CHAIN, view("-S /r/CEU.txt")), CHAIN, True),
        # bcftools' version line on its first pass, and htslib's own words for PASS.
        (
            (
                *CHAIN,
                "##bcftools_viewVersion=1.9+htslib-1.9",
                '##FILTER=<ID=PASS,Description="All filters passed">',
                PASS,
            ),
            (*CHAIN[:-1], '##FILTER=<ID=PASS,Description="Site contains at least one allele that passes filters">'),
            True,
        ),
        ((*CHAIN, "##contig=<ID=chr1,length=10>", view("-S /r/CEU.txt")), CHAIN, False),
        ((*CHAIN, "##reference=file:/r/other.fa", view("-S /r/CEU.txt")), CHAIN, False),
        ((*CHAIN, '##INFO=<ID=AF,Number=A,Type=Float,Description="x">', view("-S /r/CEU.txt")), CHAIN, False),
        ((*CHAIN[1:], view("-S /r/CEU.txt")), CHAIN, False),
        ((*CHAIN, "##fileDate=20210422", view("-S /r/CEU.txt")), CHAIN, False),
    ],
    ids=[
        "view-of-it",
        "first-pass",
        "contig-added",
        "reference-changed",
        "info-added",
        "line-dropped",
        "other-line-added",
    ],
)
def test_a_childs_header_fits_its_parent_where_only_bcftools_own_lines_are_added(child, parent, fits):
    assert ps.fits_parent(header(*child), header(*parent)) is fits


def test_a_child_whose_samples_its_parent_lacks_does_not_fit():
    parent = with_samples(header(*CHAIN), "HG00096", "HG00097")
    child = header(*CHAIN, view("-S /r/CEU.txt"))
    assert ps.fits_parent(with_samples(child, "HG00096"), parent)
    assert not ps.fits_parent(with_samples(child, "HG00096", "NA12878"), parent)
    assert not ps.fits_parent(with_samples(child, "HG00096"), dataclasses.replace(parent, sample_columns=None))


def test_a_lifted_callset_whose_header_was_re_sorted_after_the_view_gives_no_step():
    """Picard's LiftoverVcf writes no command line, but its re-sort leaves lines after the view's (#771)."""
    lifted = header(*CHAIN, "##reference=file:/r/chm13.v1.1.fasta", "##source=SelectVariants")
    file_name = "1kgp.chr1.recalibrated.snp_indel.pass.chm13.v1.1.liftover.vcf.gz"
    entries = (("1kgp.chr1.recalibrated.snp_indel.vcf.gz", "D"),)
    assert reader(*entries)(lifted, file_name, "D", None) == (None, ps.NO_SINGLE_END)


def test_the_end_of_the_flow_wins_over_a_last_line_view_naming_another_output():
    other = view("-S /r/CEU.txt -o other.vcf.gz", "/p/unrelated.vcf.gz")
    step, outcome = reader(("HG00096.cram", "D"))(header(HC, other), "HG00096.chr10.hc.vcf.gz", "D", None)
    assert outcome == ps.STEPPED and step is not None and step["activity"] == "VariantCallActivity"


@pytest.mark.parametrize(
    ("last", "outcome"),
    [
        (view("-S /r/CEU.txt -o other.vcf.gz"), ps.OUTPUT_NOT_THIS_FILE),
        (view("-S /r/CEU.txt -f PASS"), ps.NO_ACTIVITY),
        (view("-Oz"), ps.NO_ACTIVITY),
        (view("-S /r/CEU.txt -G"), ps.NO_ACTIVITY),
        (view("-S /r/CEU.txt", "-"), ps.NO_ACTIVITY),
        (view("-S /r/CEU.txt", f"/p/{PASSED} /p/{CEU}"), ps.NO_ACTIVITY),
        (view("-S /r/CEU.txt", "/p/tmp.3.vcf"), ps.PARENT_NOT_FOUND),
        (view("-S /r/CEU.txt", "/p/ceu_samples.txt"), ps.NO_ACTIVITY),
    ],
    ids=[
        "another-output",
        "subset-and-filter",
        "neither",
        "undeclared-option",
        "stdin",
        "two-inputs",
        "no-parent",
        "not-a-vcf",
    ],
)
def test_a_last_line_view_gives_no_step_where_its_output_options_or_input_say_nothing(last, outcome):
    entries = ((PASSED, "D"), (CEU, "D"), ("ceu_samples.txt", "D"))
    assert reader(*entries)(header(IMPORT, last), CEU, "D", None) == (None, outcome)


def test_a_last_line_views_parent_two_files_carry_gives_no_step():
    entries = ((PASSED, "D"), (PASSED.upper(), "D"))
    assert reader(*entries)(header(*CHAIN, view("-S /r/CEU.txt")), CEU, "D", None) == (None, ps.PARENT_AMBIGUOUS)


def test_a_header_cut_short_of_its_chrom_line_has_no_last_line_to_read():
    text = "\n".join(["##fileformat=VCFv4.2", *CHAIN, view("-S /r/CEU.txt")])
    assert reader((PASSED, "D"))(parse_vcf_header(text), CEU, "D", None) == (None, ps.NO_SINGLE_END)


def test_a_pvar_takes_no_step_from_a_view_its_vcf_ended_with():
    pvar = "1kgp.chr1.recalibrated.snp_indel.pass.CEU.pvar"
    assert reader((PASSED, "D"))(header(*CHAIN, view("-S /r/CEU.txt")), pvar, "D", None) == (None, ps.NOT_A_VCF)


def test_the_last_line_is_the_headers_last_double_hash_line_whatever_its_key():
    assert header(*CHAIN, "##contig=<ID=chr1,length=10>").last_meta_line == "##contig=<ID=chr1,length=10>"
    assert parse_vcf_header("#CHROM\tPOS").last_meta_line is None


# --- a name several alignments carry, settled by contigs (#620) ----------------------------

# T2T's re-alignment of one sample's reads to two references, both named HG00096.cram: the
# first reference's chrY is GRCh38's, the second's HG002's, and the gVCF names the first's.
CONTIGS = ("##contig=<ID=chr1,length=248387328>", "##contig=<ID=chrY,length=57227415>")
GRCH38_Y = "@HD\tVN:1.6\n@SQ\tSN:chrY\tLN:57227415\n@SQ\tSN:chr1\tLN:248387328\n"
HG002_Y = "@HD\tVN:1.6\n@SQ\tSN:chr1\tLN:248387328\n@SQ\tSN:chrY_hg002\tLN:62460029\n"
GVCF = "HG00096.chr10.hc.vcf.gz"


@pytest.fixture
def fetches(monkeypatch) -> list[str]:
    """Every alignment header the step reader reads, served from the BAM producer's cache only:
    one not in it cannot be read, as when the fetch fails."""
    read: list[str] = []
    cached = ps.fetch_bam_header

    def fetch(evidence_dir, md5, **kwargs):
        read.append(md5)
        if not get_evidence_path(evidence_dir, md5).exists():
            raise FetchError("not cached")
        return cached(evidence_dir, md5, **kwargs)

    monkeypatch.setattr(ps, "fetch_bam_header", fetch)
    return read


def carriers(tmp_path, *headers: str | None, folders: tuple[str, ...] = ()) -> ps.HeaderSteps:
    """A step reader over one HG00096.cram of dataset D per header, keyed f0, f1, …, each header
    in the BAM producer's cache under ``tmp_path`` (None: not cached, so unreadable), the n-th
    stored in ``folders[n]`` where given."""
    records = []
    for n, text in enumerate(headers):
        md5 = f"{n:032x}"
        records.append({"file_id": f"f{n}", "file_name": "HG00096.cram", "dataset_id": "D", "file_md5sum": md5})
        if folders:
            records[-1]["file_path"] = f"{folders[n]}/HG00096.cram"
        if text is not None:
            BamEvidence(md5sum=md5, file_name="HG00096.cram", header_text=text).save(tmp_path / BAM_CONFIG.name)
    return ps.HeaderSteps.for_run(records, KEY, tmp_path, alignments=BAM_CONFIG.name, variants=VCF_CONFIG.name)


def test_of_alignments_sharing_a_name_the_parent_is_the_one_with_the_vcfs_contigs(tmp_path, fetches):
    step, outcome = carriers(tmp_path, HG002_Y, GRCH38_Y)(header(HC, *CONTIGS), GVCF, "D", None)
    assert outcome == ps.STEPPED and step is not None
    (used,) = step["inputs"]
    assert (used["parent_file"], used["parent_key"]) == ("HG00096.cram", "f1")
    assert used["named_by"] == [{"source_type": SOURCE_CONTENT_READ, "rule_id": code_rules.VARIANT_CALL_BY_HEADER.id}]


@pytest.mark.parametrize(
    ("headers", "contigs"),
    [
        pytest.param((HG002_Y, HG002_Y), CONTIGS, id="none-has-the-vcfs-contigs"),
        pytest.param((GRCH38_Y, GRCH38_Y), CONTIGS, id="two-have-them"),
        pytest.param((GRCH38_Y, HG002_Y), CONTIGS[:1], id="the-vcf-names-a-subset"),
        pytest.param((GRCH38_Y, HG002_Y), ("##contig=<ID=chr1>", CONTIGS[1]), id="the-vcf-names-no-length"),
    ],
)
def test_alignments_sharing_a_name_that_contigs_do_not_tell_apart_give_no_step(tmp_path, fetches, headers, contigs):
    assert carriers(tmp_path, *headers)(header(HC, *contigs), GVCF, "D", None) == (None, ps.PARENT_AMBIGUOUS)


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param((GRCH38_Y, None), id="one-is-not-cached-and-cannot-be-fetched"),
        pytest.param((GRCH38_Y, GRCH38_Y.replace("SQ\tSN:chrY\tLN:57227415", "SQ\tSN:chrY")), id="one-names-no-length"),
    ],
)
def test_a_carrier_whose_contigs_cannot_be_read_gives_no_step_and_says_so(tmp_path, fetches, headers):
    """It may be the parent, so the other is not taken, and the outcome is not a tie (#620)."""
    assert carriers(tmp_path, *headers)(header(HC, *CONTIGS), GVCF, "D", None) == (None, ps.PARENT_UNREADABLE)


def test_an_alignment_to_part_of_the_vcfs_reference_fits_it(tmp_path, fetches):
    """GATK takes an alignment whose every contig is the reference's, at its length: the VCF
    may name more (a decoy the alignment's reference left out)."""
    decoy = "##contig=<ID=chrEBV,length=171823>"
    step, outcome = carriers(tmp_path, HG002_Y, GRCH38_Y)(header(HC, *CONTIGS, decoy), GVCF, "D", None)
    assert outcome == ps.STEPPED and step is not None and step["inputs"][0]["parent_key"] == "f1"


def test_a_gatk3_line_naming_an_alignment_two_files_carry_is_not_settled_by_contigs(tmp_path, fetches):
    """GATK 3's own contig check may accept a partial overlap, so its lines keep the name rule."""
    hc3 = GATK3_HC.replace("/data/analysis/Sample_HG04164/analysis/HG04164.final.bam", "/x/HG00096.cram")
    reader3 = carriers(tmp_path, HG002_Y, GRCH38_Y)
    assert reader3(header(hc3, *CONTIGS), "HG00096.g.vcf.gz", "D", None) == (None, ps.PARENT_AMBIGUOUS)
    assert fetches == []


def test_a_vcf_naming_no_contigs_reads_no_alignment(tmp_path, fetches):
    assert carriers(tmp_path, GRCH38_Y, HG002_Y)(header(HC), GVCF, "D", None) == (None, ps.PARENT_AMBIGUOUS)
    assert fetches == []


def test_an_alignment_name_one_file_carries_is_taken_without_reading_it(tmp_path, fetches):
    step, outcome = carriers(tmp_path, HG002_Y)(header(HC, *CONTIGS), GVCF, "D", None)
    assert outcome == ps.STEPPED and step is not None and step["inputs"][0]["parent_key"] == "f0"
    assert fetches == []


def test_each_alignment_is_read_once_for_all_of_its_samples_vcfs(tmp_path, fetches):
    reader = carriers(tmp_path, HG002_Y, GRCH38_Y)
    for chrom in ("chr10", "chr11"):
        hc = HC.replace("chr10", chrom)
        assert reader(header(hc, *CONTIGS), f"HG00096.{chrom}.hc.vcf.gz", "D", None)[1] == ps.STEPPED
    assert sorted(fetches) == [f"{0:032x}", f"{1:032x}"]


def test_contigs_are_compared_as_names_and_lengths_in_any_order():
    assert ps.vcf_contigs(header(*CONTIGS)) == ps.sam_contigs(GRCH38_Y) == {("chr1", 248387328), ("chrY", 57227415)}
    assert ps.sam_contigs("@HD\tVN:1.6\n") is None
    assert ps.vcf_contigs(header("##contig=<ID=chr1,length=12x>")) is None


def test_a_rule_taking_several_inputs_cannot_settle_a_shared_name_by_contigs():
    with pytest.raises(ValueError, match="several inputs"):
        dataclasses.replace(ps.STEP_RULES["concat"], same_contigs=True)


# --- the VCF producer --------------------------------------------------------------------


def test_the_vcf_producer_writes_the_step_and_counts_every_outcome(tmp_path, monkeypatch):
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
        f"{3:032x}": header_text(HC),
        f"{4:032x}": header_text(HC.replace("HG00096", "HG00097")),
    }

    def fetch(evidence_dir, md5, **kwargs):
        return headers[md5]

    # Every parse of a VCF header through a binding of `parse_vcf_header` the run can reach:
    # the config's parser, the classifier's own (it parses a header handed over as text),
    # the name `rule_engine` imports when it parses, and the one `reference_builds`
    # holds. The classifier and the step reader share the pipeline's one parse per file
    # (#615), so neither makes a second.
    parses: list[str] = []

    def counting_parse(text):
        parses.append(text)
        return parse_vcf_header(text)

    monkeypatch.setattr(header_extractors, "parse_vcf_header", counting_parse)
    monkeypatch.setattr(reference_builds, "parse_vcf_header", counting_parse)
    monkeypatch.setattr(header_classifier, "parse_vcf_header", counting_parse)
    # The stub fetcher reads no alignment, so the preflight guarding samtools is dropped with it.
    config = dataclasses.replace(VCF_CONFIG, fetcher=fetch, parser=counting_parse, preflight=None)
    pipeline = ClassifyPipeline(
        config,
        write_metadata(tmp_path / "in.json", records),
        tmp_path / "vcf.json",
        evidence_base=tmp_path / "ev",
        workers=1,
    )
    rows = {r["file_id"]: r for r in pipeline.run()}
    assert sorted(parses) == sorted(headers.values())
    assert rows["v1"]["generated_by"]["inputs"][0]["parent_key"] == "c1"
    assert rows["v2"]["generated_by"] is None
    written = json.loads((tmp_path / "vcf.json").read_text())
    assert written["metadata"]["details"]["producer_steps"] == {"T": {ps.STEPPED: 1, ps.PARENT_AMBIGUOUS: 1}}


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


def test_a_runs_step_outcomes_are_kept_per_producer_and_dataset(tmp_path):
    def write(name, steps):
        details = {"producer_steps": steps} if steps is not None else None
        (tmp_path / name).write_text(json.dumps({"metadata": {"details": details}, "classifications": []}))

    write("vcf_classifications.json", {"T": {"stepped": 2, "no_activity": 1}, "U": {"stepped": 1}})
    write("tar_classifications.json", {"T": {"stepped": 4, "no_vcf_header": 1}})
    write("bam_classifications.json", None)
    assert content_step_counts(run_metadata(tmp_path)) == {
        "tar": {"T": {"stepped": 4, "no_vcf_header": 1}},
        "vcf": {"T": {"stepped": 2, "no_activity": 1}, "U": {"stepped": 1}},
    }


def test_a_quoted_input_is_read_without_its_quotes():
    # Inside GATK's quoted `CommandLine="…"` attribute a quote is written `\"`.
    (step,) = steps(header(gatk4("HaplotypeCaller", '--input \\"/x/HG00096.cram\\" --output HG00096.chr1.hc.vcf')))
    assert step.inputs == ("/x/HG00096.cram",)


def test_any_other_tools_command_line_is_an_undeclared_tool():
    freebayes = '##commandline="freebayes -f ref.fa a.bam"'
    assert ps.producing_step(header(freebayes), "x.vcf.gz") == (None, ps.UNKNOWN_TOOL)


def test_a_bcftools_short_option_with_its_value_attached_takes_no_next_word():
    (step,) = steps(header("##bcftools_concatCommand=concat -a -Oz -o chr1.vcf.gz a.vcf.gz b.vcf.gz; Date=x"))
    assert (step.output, step.inputs) == ("chr1.vcf.gz", ("a.vcf.gz", "b.vcf.gz"))


def test_an_unnamed_end_beside_one_set_aside_for_another_file_is_not_taken():
    joint = gatk4("GenotypeGVCFs", "--variant a.g.vcf.gz -O joint.vcf.gz")
    assert ps.producing_step(header(GATK3_HC, joint), "cohort.vcf.gz") == (None, ps.NO_SINGLE_END)
    assert made(header(GATK3_HC), "HG04164.haplotypeCalls.er.raw.g.vcf.gz").tool == "HaplotypeCaller"


def test_a_candidate_parent_with_no_record_key_stops_the_run_when_the_reader_is_built():
    with pytest.raises(ValueError, match="file_id"):
        ps.HeaderSteps.for_run(
            [{"file_name": "HG00096.cram", "dataset_id": "D"}],
            KEY,
            EVIDENCE,
            alignments=BAM_CONFIG.name,
            variants=VCF_CONFIG.name,
        )


def test_the_vcf_producer_checks_its_preflight_even_when_every_vcf_is_cached(tmp_path):
    """Its step reader may fetch an alignment's header the VCF cache does not show (#620),
    so a missing samtools refuses the run before any work, cached VCFs or not."""
    record: dict = {"file_id": "v1", "file_name": "HG00096.chr10.hc.vcf.gz", "dataset_id": "D", "dataset_title": "T"}
    record.update(file_md5sum="a" * 32, file_size=1, file_format="vcf.gz")

    def no_samtools():
        raise RuntimeError("samtools not found")

    config = dataclasses.replace(VCF_CONFIG, fetcher=lambda *a, **k: header_text(HC), preflight=no_samtools)
    pipeline = ClassifyPipeline(
        config, write_metadata(tmp_path / "in.json", [record]), tmp_path / "vcf.json", evidence_base=tmp_path / "ev"
    )
    cached = get_evidence_path(pipeline.evidence_dir, "a" * 32)
    cached.parent.mkdir(parents=True)
    cached.write_text("{}")
    with pytest.raises(RuntimeError, match="samtools not found"):
        pipeline.run()
    assert not (tmp_path / "vcf.json").exists()


def test_the_vcf_producer_refuses_an_input_naming_no_repository_before_any_work(tmp_path):
    path = tmp_path / "in.ndjson"
    path.write_text(json.dumps({"file_id": "v1", "file_name": "x.vcf.gz", "file_md5sum": "0" * 32}) + "\n")
    with pytest.raises(ValueError):
        ClassifyPipeline(VCF_CONFIG, path, tmp_path / "vcf.json", evidence_base=tmp_path / "ev").run()


def test_a_step_whose_input_is_its_own_output_less_gz_is_still_an_end():
    hc = gatk4("HaplotypeCaller", "--input ./HG00096.cram --output HG00096.chr1.hc.vcf")
    recompress = "##bcftools_viewCommand=view -Oz -o HG00096.chr1.hc.vcf.gz HG00096.chr1.hc.vcf; Date=x"
    assert made(header(hc, recompress), "HG00096.chr1.hc.vcf.gz").tool == "view"


def test_a_file_type_that_reads_a_step_must_declare_the_parser_it_reads_it_from():
    with pytest.raises(ValueError, match="parser"):
        dataclasses.replace(VCF_CONFIG, parser=None)


# --- the folder, which settles a shared name only where content does not (#717) ------------


def test_the_contigs_outrank_the_folder(tmp_path, fetches):
    """The CRAM beside the gVCF has another reference's chrY: the one that fits is the parent."""
    reader_ = carriers(tmp_path, HG002_Y, GRCH38_Y, folders=("b", "a"))
    step, outcome = reader_(header(HC, *CONTIGS), GVCF, "D", "b")
    assert outcome == ps.STEPPED and step is not None and step["inputs"][0]["parent_key"] == "f1"


def test_the_folder_breaks_a_tie_the_contigs_leave(tmp_path, fetches):
    reader_ = carriers(tmp_path, GRCH38_Y, GRCH38_Y, folders=("a", "b"))
    step, outcome = reader_(header(HC, *CONTIGS), GVCF, "D", "b")
    assert outcome == ps.STEPPED and step is not None and step["inputs"][0]["parent_key"] == "f1"
    assert reader_(header(HC, *CONTIGS), GVCF, "D", "c") == (None, ps.PARENT_AMBIGUOUS)


def test_the_folder_does_not_stand_in_for_an_unreadable_carrier(tmp_path, fetches):
    reader_ = carriers(tmp_path, GRCH38_Y, None, folders=("a", "b"))
    assert reader_(header(HC, *CONTIGS), GVCF, "D", "a") == (None, ps.PARENT_UNREADABLE)


def test_a_line_whose_contigs_are_not_relied_on_is_settled_by_the_folder(tmp_path, fetches):
    """GATK 3 keeps the name rule (#620), and the folder settles a name two files carry."""
    hc3 = GATK3_HC.replace("/data/analysis/Sample_HG04164/analysis/HG04164.final.bam", "/x/HG00096.cram")
    reader3 = carriers(tmp_path, HG002_Y, GRCH38_Y, folders=("a", "b"))
    step, outcome = reader3(header(hc3, *CONTIGS), "HG00096.g.vcf.gz", "D", "b")
    assert outcome == ps.STEPPED and step is not None and step["inputs"][0]["parent_key"] == "f1"
    assert fetches == []


def test_the_vcf_producer_hands_each_file_s_folder_to_the_step_reader(tmp_path, monkeypatch):
    """Through the pipeline (#717): the work item's folder, from the input's `file_path`, settles a
    name two alignments carry, on a line whose contigs are not relied on."""
    gvcf = "HG04164.haplotypeCalls.er.raw.g.vcf.gz"
    records: list[dict] = [
        {"file_id": "a", "file_name": "HG04164.final.bam", "file_path": "a/HG04164.final.bam"},
        {"file_id": "b", "file_name": "HG04164.final.bam", "file_path": "b/HG04164.final.bam"},
        {"file_id": "v", "file_name": gvcf, "file_path": f"b/{gvcf}"},
    ]
    for n, record in enumerate(records):
        record.update(dataset_id="D", dataset_title="T", file_md5sum=f"{n:032x}", file_size=1)
        record["file_format"] = record["file_name"].split(".", 1)[1]
    config = dataclasses.replace(
        VCF_CONFIG, fetcher=lambda *_a, **_k: header_text(GATK3_HC), parser=parse_vcf_header, preflight=None
    )
    pipeline = ClassifyPipeline(
        config, write_metadata(tmp_path / "in.json", records), tmp_path / "vcf.json", evidence_base=tmp_path / "ev"
    )
    [row] = [r for r in pipeline.run() if r["file_id"] == "v"]
    assert row["generated_by"]["inputs"][0]["parent_key"] == "b"
