"""A VCF's variant kind, read from the caller that made it (#654): the reader's new tools,
the kind rules over real-shaped headers, the caller table, and the claim the classifier makes."""

import pytest

from meta_disco import header_classifier
from meta_disco import producer_steps as ps
from meta_disco import variant_kinds as vk
from meta_disco.file_name import FileName
from meta_disco.models import NOT_CLASSIFIED, SOURCE_CONTENT_READ
from meta_disco.validators.command_lines import BCFTOOLS, DRAGEN, GATK3, PROGRAM
from tests.test_producer_steps import (
    CONCAT,
    HC,
    IMPORT,
    PASS,
    SELECT,
    VQSR_INDEL,
    VQSR_SNP,
    gatk4,
    header,
    header_text,
    steps,
)

GENOTYPE = gatk4("GenotypeGVCFs", "-V gendb://chr1_db -O chr1.100000001_100100000.margined.genotyped.vcf.gz -R ref.fa")
SNIFFLES_COMMAND = '##command="/usr/local/bin/sniffles -i /x/minimap2.bam -v sniffles.vcf -t 64 --minsvlen 30"'
SVTYPE = '##INFO=<ID=SVTYPE,Number=1,Type=String,Description="Type of structural variant">'
ALT_DEL = '##ALT=<ID=DEL,Description="Deletion">'


def kind(*lines: str, name: str = "x.vcf.gz") -> vk.KindReading:
    return vk.read_kind(header(*lines), name)


# --- the reader's new tools ---------------------------------------------------------------


def test_sniffles_plain_command_line_is_a_step_of_the_program_its_first_word_names():
    (step,) = steps(header(SNIFFLES_COMMAND))
    assert (step.family, step.tool, step.inputs, step.output) == (
        PROGRAM,
        "sniffles",
        ("/x/minimap2.bam",),
        "sniffles.vcf",
    )


def test_a_plain_command_line_of_an_undeclared_program_is_unread():
    assert ps.steps_of(header('##command="/bin/freebayes -f ref.fa a.bam"')) is None


def test_gatk3_apply_recalibration_reads_its_rod_binding_input_and_its_output():
    line = (
        '##GATKCommandLine.ApplyRecalibration=<ID=ApplyRecalibration,CommandLineOptions="analysis_type=ApplyRecalibration '
        "input=[(RodBinding name=input source=/t/chr17.recalibrated_snps_raw_indels.vcf)] "
        'recal_file=(RodBinding name=recal_file source=/t/x.recal) out=/t/chr17.recal.vcf mode=INDEL">'
    )
    (step,) = steps(header(line))
    assert (step.family, step.tool, step.inputs, step.output) == (
        GATK3,
        "ApplyRecalibration",
        ("/t/chr17.recalibrated_snps_raw_indels.vcf",),
        "/t/chr17.recal.vcf",
    )


@pytest.mark.parametrize(
    "line, inputs, output",
    [
        ("##bcftools_normCommand=norm -m -any -Oz -o out.vcf.gz in.vcf.gz; Date=x", ("in.vcf.gz",), "out.vcf.gz"),
        ("##bcftools_annotateCommand=annotate -x INFO/AT -a ann.bed -o out.vcf in.vcf; Date=x", ("in.vcf",), "out.vcf"),
        (
            "##bcftools_mergeCommand=merge --force-samples -o m.vcf a.vcf.gz b.vcf.gz; Date=x",
            ("a.vcf.gz", "b.vcf.gz"),
            "m.vcf",
        ),
    ],
)
def test_bcftools_norm_annotate_and_merge_are_read(line, inputs, output):
    (step,) = steps(header(line))
    assert (step.family, step.inputs, step.output) == (BCFTOOLS, inputs, output)


@pytest.mark.parametrize(
    "line",
    [
        "##bcftools_mergeCommand=merge -l gvcfs.txt -o m.vcf a.vcf.gz; Date=x",
        "##bcftools_concatCommand=concat -f gvcfs.txt -o m.vcf a.vcf.gz; Date=x",
    ],
)
def test_a_bcftools_file_list_is_a_list_of_inputs_not_an_input(line):
    (step,) = steps(header(line))
    assert (step.inputs, step.input_lists) == (("a.vcf.gz",), ("gvcfs.txt",))


def test_a_dragen_line_is_read_and_names_no_single_output():
    line = (
        '##DRAGENCommandLine=<ID=dragen,Version="4.3.6",CommandLineOptions="--ht-reference /r '
        '--output-directory multi-sample --output-file-prefix multi-sample --variant-list gvcf_list.txt">'
    )
    (step,) = steps(header(line))
    assert (step.family, step.tool, step.output, step.input_lists) == (DRAGEN, "dragen", None, ("gvcf_list.txt",))


def test_every_source_line_is_kept_in_order():
    parsed = header("##source=GenomicsDBImport", "##source=SelectVariants")
    assert parsed.sources == ("GenomicsDBImport", "SelectVariants")
    assert parsed.source == "SelectVariants"


# --- rules 1, 2 and 4: the producing step's caller ---------------------------------------


def test_a_producing_caller_gives_its_kind():
    reading = kind(HC, name="HG00096.chr10.hc.vcf.gz")
    assert (reading.by, reading.kind) == (vk.BY_STEP, "small")


def test_the_walk_back_passes_steps_that_keep_the_kind_to_the_caller_that_wrote_their_input():
    reading = kind(GENOTYPE, SELECT, name="chr1.100000001_100100000.genotyped.vcf.gz")
    assert reading.kind == "small"
    assert "SelectVariants <- GenotypeGVCFs" in reading.reason


def test_a_kept_step_whose_input_no_step_wrote_takes_the_headers_one_other_step():
    # T2T's region files: GenomicsDBImport and SelectVariants, and no GenotypeGVCFs line between them.
    reading = kind(IMPORT, SELECT, name="chr1.100000001_100100000.genotyped.vcf.gz")
    assert reading.kind == "small"
    assert "the header's one other step" in reading.reason


@pytest.mark.parametrize(
    "extra, doubt",
    [(SVTYPE, "declares structural-variant fields"), ("##source=Sniffles2_2.0.7", "also names Sniffles2_2.0.7")],
)
def test_the_headers_one_other_step_is_not_taken_where_the_rest_of_the_header_doubts_it(extra, doubt):
    reading = kind(IMPORT, SELECT, extra, name="chr1.100000001_100100000.genotyped.vcf.gz")
    assert reading.kind is None and reading.reason.startswith(vk.FALLBACK_DISAGREES) and doubt in reading.reason


def test_a_kept_step_with_no_caller_in_the_header_gives_no_kind():
    reading = kind(PASS, name="1kgp.chr1.recalibrated.snp_indel.pass.vcf.gz")
    assert reading.kind is None and reading.reason.startswith(vk.NO_CALLER_ON_CHAIN)


def test_a_caller_the_table_does_not_list_gives_no_kind():
    line = '##DRAGENCommandLine=<ID=dragen,CommandLineOptions="--output-directory d --output-file-prefix p">'
    reading = kind(line)
    assert reading.kind is None and reading.reason.startswith(vk.NOT_IN_TABLE)


def test_an_unread_command_line_gives_no_kind():
    reading = kind("##bcftools_pluginCommand=plugin fill-tags -- -t AF; Date=x")
    assert reading.kind is None and reading.reason.startswith(vk.UNREAD_STEP)


def test_a_pvar_gives_no_kind():
    assert kind(HC, name="EUR.10.pvar").reason.startswith(vk.PVAR)


def test_a_renamed_callers_output_takes_the_headers_one_step():
    # Sniffles wrote `sniffles.vcf`; the file was published as `sniffles_sv.vcf`.
    reading = kind(SNIFFLES_COMMAND, name="sniffles_sv.vcf")
    assert reading.kind == "structural"


def test_with_no_one_producing_step_two_other_tools_give_no_kind():
    # Neither step wrote this file, and the header's other steps are two callers of two kinds.
    reading = kind(HC, SNIFFLES_COMMAND, name="x.vcf.gz")
    assert reading.kind is None and reading.reason.startswith(vk.NO_CALLER_ON_CHAIN)
    assert "2 other tools" in reading.reason


def test_a_kept_steps_input_written_by_two_steps_is_not_walked_to_either():
    combine = gatk4("CombineGVCFs", "-V a.g.vcf -O chr1.100000001_100100000.margined.genotyped.vcf.gz")
    reading = kind(GENOTYPE, combine, SELECT, name="chr1.100000001_100100000.genotyped.vcf.gz")
    assert reading.kind is None and "several steps" in reading.reason


def test_an_empty_fastq_holds_no_variants():
    assert header_classifier.classify_from_fastq_header([])["variant_kind"]["status"] == "not_applicable"


# --- rule 3: the one tool a header with no command line names -----------------------------


@pytest.mark.parametrize(
    "lines, expected",
    [
        (["##source=Sniffles2_2.0.7"], "structural"),
        (["##source=SVIM-asm-v1.0.2"], "structural"),
        (["##DeepVariant_version=1.4.0"], "small"),
        (["##source=HaplotypeCaller", "##source=HaplotypeCaller"], "small"),
        (["##source=Sniffles2_2.0.6", "##source=Sniffles2_2.0.7"], "structural"),
    ],
)
def test_the_one_tool_a_header_names_gives_its_kind(lines, expected):
    reading = kind(*lines)
    assert (reading.by, reading.kind) == (vk.BY_SOURCE, expected)


def test_where_the_command_lines_name_no_caller_the_tool_the_header_names_gives_the_kind():
    # PEPPER-Margin-DeepVariant's rejected calls: a DeepVariant version line and bcftools filters.
    reading = kind("##DeepVariant_version=1.1.0", PASS, name="1kgp.chr1.recalibrated.snp_indel.pass.vcf.gz")
    assert (reading.by, reading.kind) == (vk.BY_SOURCE, "small")


def test_two_tools_naming_themselves_give_no_kind():
    # NIA CARD's concatenation of PEPPER-Margin-DeepVariant calls and SVIM-asm calls.
    reading = kind("##source=SVIM-asm-v1.0.2", "##DeepVariant_version=1.4.0")
    assert reading.kind is None and reading.reason.startswith(vk.SEVERAL_TOOLS)


def test_a_caller_beside_a_tool_the_table_does_not_list_is_two_tools():
    reading = kind("##source=Sniffles2_2.0.7", "##source=dbSNP")
    assert reading.kind is None and reading.reason.startswith(vk.SEVERAL_TOOLS)


def test_a_header_naming_no_tool_gives_no_kind():
    assert kind().reason.startswith(vk.NO_CALLER_LINE)


def test_a_reference_resource_names_a_tool_the_table_does_not_list():
    reading = kind("##source=dbSNP")
    assert reading.kind is None and reading.reason == f"{vk.NOT_IN_TABLE}: dbSNP"


# --- rule 5: a merge ----------------------------------------------------------------------


def test_a_merge_of_small_variant_callers_declaring_no_sv_field_is_small():
    reading = kind(IMPORT, SELECT, CONCAT, name="chr1.genotyped.vcf.gz")
    assert (reading.by, reading.kind) == (vk.BY_MERGE, "small")


@pytest.mark.parametrize("declaration", [SVTYPE, ALT_DEL])
def test_a_merge_whose_header_declares_an_sv_field_gives_no_kind(declaration):
    reading = kind(IMPORT, SELECT, CONCAT, declaration, name="chr1.genotyped.vcf.gz")
    assert reading.kind is None and reading.reason.startswith(vk.SV_DECLARED)


def test_a_merge_of_callers_of_two_kinds_gives_no_kind():
    concat = "##bcftools_concatCommand=concat -a -o merged.vcf pmdv.vcf hapdiff.vcf; Date=x"
    reading = kind(concat, "##source=SVIM-asm-v1.0.2", "##DeepVariant_version=1.4.0", name="merged.vcf")
    assert reading.kind is None and reading.reason.startswith(vk.MIXED_MERGE)


def test_a_merge_naming_no_caller_gives_no_kind():
    reading = kind("##bcftools_concatCommand=concat -o m.vcf a.vcf b.vcf; Date=x", name="m.vcf")
    assert reading.kind is None and reading.reason.startswith(vk.NO_CALLER_LINE)


def test_with_no_one_producing_step_a_merge_in_the_header_settles_the_kind():
    # T2T's population subsets: several `view` steps write to stdout, so no one step made the file.
    other_view = (
        "##bcftools_viewCommand=view -s HG00096 /cromwell_root/z/1kgp.chr1.recalibrated.snp_indel.pass.vcf.gz; Date=x"
    )
    reading = kind(IMPORT, SELECT, CONCAT, VQSR_SNP, VQSR_INDEL, PASS, other_view, name="1kgp.chr1.pass.EUR.vcf.gz")
    assert (reading.by, reading.kind) == (vk.BY_MERGE, "small")


# --- the caller table ---------------------------------------------------------------------


def test_every_callers_kind_is_a_variant_kind_term():
    from meta_disco.schema_vocab import dimension_values

    table = vk.load_caller_kinds()
    assert {c.kind for c in table.callers} <= dimension_values("variant_kind")


def test_a_caller_name_matches_whole_and_case_insensitively():
    table = vk.load_caller_kinds()
    assert [getattr(table.caller(n), "name", None) for n in ("sniffles", "Sniffles2_2.0.7")] == ["Sniffles"] * 2
    assert table.caller("SnifflesX") is None


# --- the claim ----------------------------------------------------------------------------


def test_the_classifier_claims_the_kind_at_the_content_tier_as_a_one_item_list():
    out = header_classifier.classify_from_vcf_header(header_text(HC), name=FileName.parse("HG00096.chr10.hc.vcf.gz"))
    entry = out["variant_kind"]
    assert entry["value"] == ["small"]
    (claim,) = [e for e in entry["evidence"] if e.get("rule_id") == "vcf_step_caller_kind"]
    assert (claim["value"], claim["tier"], claim["source_type"]) == ("small", 4, SOURCE_CONTENT_READ)


def test_the_classifier_claims_not_classified_with_the_reason_where_no_kind_is_read():
    out = header_classifier.classify_from_vcf_header(header_text("##source=dbSNP"), name=FileName.parse("dbsnp.vcf.gz"))
    entry = out["variant_kind"]
    assert (entry["value"], entry["status"]) == (None, NOT_CLASSIFIED)
    (claim,) = [e for e in entry["evidence"] if e.get("rule_id") == "vcf_source_caller_kind"]
    assert claim["status"] == NOT_CLASSIFIED and claim["reason"] == f"{vk.NOT_IN_TABLE}: dbSNP"
