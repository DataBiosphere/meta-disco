"""A VCF's variant origin, read from the caller that made it (#658): the origin rules over
real-shaped headers, the somatic-mode and somatic-declaration guards, the caller table, and
the claim the classifier makes."""

import pytest

from meta_disco import activities, callers, header_classifier
from meta_disco import variant_origins as vo
from meta_disco.file_name import FileName
from meta_disco.models import NOT_CLASSIFIED, SOURCE_CONTENT_READ
from meta_disco.schema_vocab import dimension_values
from tests.test_producer_steps import CONCAT, HC, IMPORT, SELECT, gatk4, header, header_text
from tests.test_variant_kinds import SNIFFLES_COMMAND

MUTECT = gatk4("Mutect2", "-I tumor.bam -I normal.bam -normal N -O unfiltered.vcf.gz -R ref.fa")
FILTER = gatk4("FilterMutectCalls", "-V unfiltered.vcf.gz -O somatic.vcf.gz -R ref.fa")
SOMATIC_INFO = '##INFO=<ID=SOMATIC,Number=0,Type=Flag,Description="Somatic mutation">'


@pytest.fixture
def somatic_caller(monkeypatch):
    """The table with a somatic caller row, which the bundled table does not yet have (#658): Mutect2, as a test-only row."""
    import dataclasses
    import re

    table = callers.load_callers()
    row = callers.Caller("Mutect2", re.compile("Mutect2", re.IGNORECASE), "small", "somatic")
    monkeypatch.setattr(callers, "load_callers", lambda: dataclasses.replace(table, callers=(*table.callers, row)))


def origin(*lines: str, name: str = "x.vcf.gz") -> callers.Reading:
    parsed = header(*lines)
    return vo.read_origin(parsed, callers.find_caller(parsed, name))


def sniffles(flags: str) -> str:
    return f'##command="/usr/local/bin/sniffles -i /x/minimap2.bam -v sniffles.vcf {flags}"'


# --- the caller's origin --------------------------------------------------------------------


def test_a_germline_callers_producing_step_gives_germline():
    reading = origin(HC, name="HG00096.chr10.hc.vcf.gz")
    assert (reading.by, reading.value) == (callers.BY_STEP, "germline")


def test_the_bundled_table_lists_no_somatic_caller_so_a_mutect2_file_has_no_origin():
    """Mutect2 is not always somatic (mitochondria mode, tumour-only runs), so it is not listed yet (#658)."""
    reading = origin(MUTECT, FILTER, name="somatic.vcf.gz")
    assert reading.value is None and reading.reason.startswith(callers.NOT_IN_TABLE)


@pytest.mark.usefixtures("somatic_caller")
def test_a_somatic_callers_output_walked_back_through_its_filter_gives_somatic():
    reading = origin(MUTECT, FILTER, name="somatic.vcf.gz")
    assert (reading.by, reading.value) == (callers.BY_STEP, "somatic")
    assert "FilterMutectCalls <- Mutect2" in reading.reason


@pytest.mark.usefixtures("somatic_caller")
def test_the_headers_one_other_step_is_refused_where_the_header_names_a_caller_of_another_origin():
    reading = origin(IMPORT, SELECT, "##source=Mutect2", name="chr1.100000001_100100000.genotyped.vcf.gz")
    assert reading.value is None and reading.reason.startswith(callers.FALLBACK_DISAGREES)


def test_the_headers_one_other_step_is_refused_where_the_header_names_a_caller_whose_mode_is_open():
    reading = origin(IMPORT, SELECT, "##source=Sniffles2_2.0.7", name="chr1.100000001_100100000.genotyped.vcf.gz")
    assert reading.value is None and reading.reason.startswith(callers.FALLBACK_DISAGREES)
    assert "Sniffles2_2.0.7" in reading.reason


def test_a_fallback_to_a_caller_with_a_mode_is_cleared_by_its_own_command_line():
    # Sniffles wrote `sniffles.vcf`; the file was published under another name.
    reading = origin(SNIFFLES_COMMAND, "##source=Sniffles2_2.0.7", name="sniffles_sv.vcf")
    assert reading.value == "germline"


def test_no_caller_gives_no_origin_with_the_callers_reason():
    reading = origin("##source=dbSNP")
    assert reading.value is None and reading.reason == f"{callers.NOT_IN_TABLE}: dbSNP"


# --- a caller with a somatic mode -----------------------------------------------------------


def test_sniffles2_whose_command_line_uses_no_mode_flag_is_germline():
    reading = origin("##source=Sniffles2_2.0.3", SNIFFLES_COMMAND, name="sniffles.vcf")
    assert reading.value == "germline"


@pytest.mark.parametrize("flags", ["--non-germline", "--mosaic", "-t 8 --mosaic --minsvlen 30"])
def test_sniffles2_run_in_its_somatic_mode_gives_no_origin(flags):
    reading = origin("##source=Sniffles2_2.0.3", sniffles(flags), name="sniffles.vcf")
    assert reading.value is None and reading.reason.startswith(vo.SOMATIC_MODE)


def test_sniffles_1_named_only_by_its_source_line_predates_the_mode():
    reading = origin("##source=Sniffles")
    assert (reading.by, reading.value) == (callers.BY_SOURCE, "germline")


def test_sniffles2_named_only_by_its_source_line_leaves_the_mode_unstated():
    reading = origin("##source=Sniffles2_2.0.6")
    assert reading.value is None and reading.reason.startswith(vo.MODE_NOT_STATED)


@pytest.mark.parametrize("flags", ["--non", "--mos", "--non-germ"])
def test_a_shortened_mode_flag_counts_as_argparse_takes_it(flags):
    reading = origin(sniffles(flags), name="sniffles.vcf")
    assert reading.value is None and reading.reason.startswith(vo.SOMATIC_MODE)


def test_a_flag_that_only_shares_a_prefix_with_no_mode_flag_does_not_count():
    reading = origin(sniffles("--minsvlen 30 --phase"), name="sniffles.vcf")
    assert reading.value == "germline"


def test_a_mode_flags_value_form_counts():
    reading = origin(sniffles("--mosaic=True"), name="sniffles.vcf")
    assert reading.value is None and reading.reason.startswith(vo.SOMATIC_MODE)


# --- the somatic declaration guard ----------------------------------------------------------


@pytest.mark.parametrize("declaration", [SOMATIC_INFO, "##tumor_sample=T", "##normal_sample=N"])
def test_a_germline_reading_is_refused_where_the_header_declares_somatic_fields(declaration):
    reading = origin(HC, declaration, name="HG00096.chr10.hc.vcf.gz")
    assert reading.value is None and reading.reason.startswith(vo.SOMATIC_DECLARED)


@pytest.mark.usefixtures("somatic_caller")
def test_a_somatic_callers_own_declarations_do_not_refuse_its_origin():
    reading = origin(MUTECT, FILTER, SOMATIC_INFO, "##tumor_sample=T", name="somatic.vcf.gz")
    assert reading.value == "somatic"


# --- a merge ----------------------------------------------------------------------------------


def test_a_merge_of_germline_callers_is_germline():
    reading = origin(IMPORT, SELECT, CONCAT, name="chr1.genotyped.vcf.gz")
    assert (reading.by, reading.value) == (callers.BY_MERGE, "germline")


def test_a_merge_of_germline_callers_of_two_kinds_is_germline():
    # NIA CARD's concatenation of PEPPER-Margin-DeepVariant calls and SVIM-asm calls: two kinds, one origin.
    concat = "##bcftools_concatCommand=concat -a -o merged.vcf pmdv.vcf hapdiff.vcf; Date=x"
    reading = origin(concat, "##source=SVIM-asm-v1.0.2", "##DeepVariant_version=1.4.0", name="merged.vcf")
    assert (reading.by, reading.value) == (callers.BY_MERGE, "germline")


@pytest.mark.usefixtures("somatic_caller")
@pytest.mark.parametrize("other", ["##source=Mutect2", "##source=dbSNP"])
def test_a_merge_naming_a_caller_that_is_not_germline_gives_no_origin(other):
    reading = origin(IMPORT, SELECT, CONCAT, other, name="chr1.genotyped.vcf.gz")
    assert reading.value is None and reading.reason.startswith(vo.MIXED_MERGE)


def test_a_merge_whose_header_declares_somatic_fields_gives_no_origin():
    reading = origin(IMPORT, SELECT, CONCAT, SOMATIC_INFO, name="chr1.genotyped.vcf.gz")
    assert reading.value is None and reading.reason.startswith(vo.SOMATIC_DECLARED)


def test_in_a_merge_one_command_line_without_the_mode_does_not_clear_every_input():
    concat = "##bcftools_concatCommand=concat -o m.vcf a.vcf b.vcf; Date=x"
    reading = origin(concat, sniffles("-t 8"), "##source=Sniffles2_2.0.7", name="m.vcf")
    assert reading.value is None and reading.reason.startswith(vo.MODE_NOT_STATED)


def test_in_a_merge_a_spelling_that_predates_the_mode_clears_it():
    concat = "##bcftools_concatCommand=concat -o m.vcf a.vcf b.vcf; Date=x"
    reading = origin(concat, "##source=Sniffles", "##source=SVIM-asm-v1.0.2", name="m.vcf")
    assert (reading.by, reading.value) == (callers.BY_MERGE, "germline")


def test_in_a_merge_a_command_line_using_the_mode_still_refuses():
    concat = "##bcftools_concatCommand=concat -o m.vcf a.vcf b.vcf; Date=x"
    reading = origin(concat, sniffles("--mosaic"), "##source=Sniffles", name="m.vcf")
    assert reading.value is None and reading.reason.startswith(vo.SOMATIC_MODE)


def test_a_merge_with_a_caller_whose_mode_is_unstated_gives_no_origin():
    concat = "##bcftools_concatCommand=concat -a -o merged.vcf a.vcf b.vcf; Date=x"
    reading = origin(concat, "##source=Sniffles2_2.0.6", "##source=SVIM-asm-v1.0.2", name="merged.vcf")
    assert reading.value is None and reading.reason.startswith(vo.MODE_NOT_STATED)


# --- the caller table ---------------------------------------------------------------------


def test_every_callers_origin_is_a_variant_origin_term():
    table = callers.load_callers()
    assert {c.origin for c in table.callers} <= dimension_values("variant_origin")


def test_a_somatic_mode_names_its_flags_and_the_spellings_that_predate_it():
    sniffles_row = callers.load_callers().caller("Sniffles")
    assert sniffles_row is not None and sniffles_row.somatic_mode is not None
    assert sniffles_row.somatic_mode.flags == {"--non-germline", "--mosaic"}
    assert sniffles_row.somatic_mode.predates == {"sniffles"}


@pytest.mark.parametrize(
    "mode, refused",
    [
        ({"flags": [], "reason": "r"}, "names no flags"),
        ({"flags": ["mosaic"], "reason": "r"}, "names no flags"),
        ({"flags": ["--mosaic"]}, "gives no reason"),
        ({"flags": ["--mosaic"], "predates": ["Snifles"], "reason": "r"}, "its pattern does not match"),
    ],
)
def test_a_somatic_mode_that_could_never_hold_is_refused_when_the_table_loads(mode, refused):
    import re

    with pytest.raises(ValueError, match=refused):
        callers._somatic_mode({"name": "Sniffles", "somatic_mode": mode}, re.compile("sniffles2?", re.IGNORECASE))


# --- the claim and its inheritance --------------------------------------------------------


def test_the_classifier_claims_the_origin_at_the_content_tier():
    out = header_classifier.classify_from_vcf_header(header_text(HC), name=FileName.parse("HG00096.chr10.hc.vcf.gz"))
    entry = out["variant_origin"]
    assert entry["value"] == "germline"
    (claim,) = [e for e in entry["evidence"] if e.get("rule_id") == "vcf_step_caller_origin"]
    assert (claim["value"], claim["tier"], claim["source_type"]) == ("germline", 4, SOURCE_CONTENT_READ)


@pytest.mark.parametrize(
    "lines, name, rule_id",
    [
        (["##source=Sniffles2_2.0.6"], "x.vcf", "vcf_source_caller_origin"),
        ([IMPORT, SELECT, CONCAT, "##source=Mutect2"], "chr1.genotyped.vcf.gz", "vcf_merge_germline_callers"),
    ],
)
def test_the_classifier_claims_not_classified_with_the_reason_under_the_rule_that_read_it(lines, name, rule_id):
    out = header_classifier.classify_from_vcf_header(header_text(*lines), name=FileName.parse(name))
    entry = out["variant_origin"]
    assert (entry["value"], entry["status"]) == (None, NOT_CLASSIFIED)
    (claim,) = [e for e in entry["evidence"] if e.get("rule_id") == rule_id]
    assert claim["status"] == NOT_CLASSIFIED and claim["reason"]


def test_the_variant_origin_passes_across_an_index_a_merge_a_cohort_merge_and_variant_processing():
    """A filter can drop calls but not change where they arose, so variant processing passes the origin (#658)."""
    passing = {term for term in activities.declarations() if "variant_origin" in activities.passes(term)}
    assert passing == {
        activities.INDEXING,
        activities.MERGE,
        activities.COHORT_MERGE,
        "VariantProcessingActivity",
        "VariantFilterActivity",
    }


def test_every_rule_that_says_a_file_holds_no_calls_says_so_for_both_call_dimensions():
    """A rule knows a file holds no variants, so neither dimension of its calls applies (#658)."""
    from importlib.resources import files

    import yaml

    def mappings(node):
        if isinstance(node, dict):
            yield node
            for v in node.values():
                yield from mappings(v)
        elif isinstance(node, list):
            for v in node:
                yield from mappings(v)

    rules = list(yaml.safe_load_all(files("meta_disco.rules").joinpath("unified_rules.yaml").read_text()))
    declared = [m for m in mappings(rules) if {"variant_kind", "variant_origin"} & m.keys()]
    assert declared
    for m in declared:
        assert m.get("variant_kind") == m.get("variant_origin") == "not_applicable", m


@pytest.mark.parametrize(
    "lines, name, expected",
    [
        ([HC], "HG00096.chr10.hc.vcf.gz", ["HaplotypeCaller"]),
        (["##source=Sniffles"], "x.vcf", ["Sniffles"]),
        (
            [
                "##bcftools_concatCommand=concat -a -o m.vcf a.vcf b.vcf; Date=x",
                "##source=SVIM-asm-v1.0.2",
                "##DeepVariant_version=1.4.0",
            ],
            "m.vcf",
            ["SVIM", "DeepVariant"],
        ),
        (["##source=dbSNP"], "x.vcf", []),
    ],
)
def test_a_readings_reason_names_the_callers_it_was_read_from(lines, name, expected):
    """The rules report counts each caller from a reading's reason (``callers.callers_in_reason``)."""
    assert callers.callers_in_reason(origin(*lines, name=name).reason) == expected
