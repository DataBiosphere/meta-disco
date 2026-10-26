"""A file's samples as identifiers (#357): the identifier rules, sample lists, and the header readers."""

import dataclasses
import json
from collections import Counter

import pytest

from meta_disco import code_rules
from meta_disco.cohort_steps import parse_sample_map
from meta_disco.file_types import BAM_CONFIG
from meta_disco.pipeline import ClassifyPipeline
from meta_disco.records import SAMPLE_LISTS_KEY, SAMPLE_OUTCOMES_KEY, UNRECOGNISED_SAMPLES_KEY
from meta_disco.sample_identity import (
    BAM_SAMPLES,
    DONOR,
    NAMED,
    NO_SAMPLE,
    SAMPLE,
    SAMPLE_MAP_SAMPLES,
    UNREAD,
    UNRECOGNISED,
    VCF_SAMPLES,
    EntityKind,
    Identifier,
    identifier_rule_declarations,
    identifier_rules,
    list_id,
    load_identifier_rules,
    most_frequent,
    reference,
    sample_list,
)
from meta_disco.validators.header_extractors import parse_vcf_header
from tests.metadata_fixtures import write_metadata

T2T_CHRY = "ANVIL_T2T_CHRY"
CHROM = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"


def coriell(n: str) -> Identifier:
    return Identifier("coriell", n)


# --- the bundled rules ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "dataset", "namespace", "ident"),
    [
        ("NA19908", None, "coriell", "NA19908"),
        # A cell line and the DNA extracted from it are one sample, written NA.
        ("GM19908", None, "coriell", "NA19908"),
        ("HG00096", None, "coriell", "HG00096"),
        ("HG002", None, "giab", "HG002"),
        ("HG007", None, "giab", "HG007"),
        ("SRS006902", None, "sra_sample", "SRS006902"),
        ("ERS000001", None, "sra_sample", "ERS000001"),
        ("SAMN29220955", None, "biosample", "SAMN29220955"),
        ("SAMEA1234", None, "biosample", "SAMEA1234"),
        ("simons_data_sample_219", T2T_CHRY, "dataset_local", "simons_data_sample_219"),
    ],
)
def test_a_recognised_string_is_an_identifier_in_its_namespace(raw, dataset, namespace, ident):
    got = identifier_rules().recognise(raw, dataset, SAMPLE)
    assert got is not None
    assert (got.identifier.namespace, got.identifier.id) == (namespace, ident)
    assert got.rule_id in {r.id for r in identifier_rule_declarations()}


@pytest.mark.parametrize(
    ("raw", "dataset"),
    [
        ("Sample", None),
        ("BioSample_3", "AnVIL_HPRC_R2"),
        ("GRCh38", None),
        ("HG008", None),
        ("GM18861-6-1", "AnVIL_MAGE"),
        ("HG03831_Fraction2_480dcq", "AnVIL_HPRC_R2"),
        ("GIABvCHM13_20200921_wm/alignments/HG002vCHM13_20200921_wm_PBCCS.sort.bam", "ANVIL_T2T"),
        # A dataset's own names are identifiers only in that dataset.
        ("simons_data_sample_219", "ANVIL_T2T"),
        ("simons_data_sample_219", None),
    ],
)
def test_a_string_no_rule_matches_is_not_a_sample(raw, dataset):
    assert identifier_rules().recognise(raw, dataset, SAMPLE) is None


def test_a_dataset_local_identifier_carries_its_dataset():
    got = identifier_rules().recognise("simons_data_sample_1", T2T_CHRY, SAMPLE)
    assert got is not None and got.identifier.dataset == T2T_CHRY
    assert got.identifier.to_dict() == {"id": "simons_data_sample_1", "namespace": "dataset_local", "dataset": T2T_CHRY}


def test_a_name_gives_the_identifiers_its_tokens_are():
    rules = identifier_rules()
    assert rules.in_name("NA24695_CTTGTA_L001_R1_001.fastq.gz") == {coriell("NA24695")}
    assert rules.in_name("05_25_21_R941_GM24631_9X_3.UL_Guppy.bam") == {coriell("NA24631")}
    assert rules.in_name("HG00096.HG00097.trio.vcf.gz") == {coriell("HG00096"), coriell("HG00097")}
    # An accession run into other text is not a token.
    assert rules.in_name("HG02080vCHM13_20200921_wm_ONT.sort.bam") == set()
    # A dataset's own names are not read from names.
    assert rules.in_name("simons_data_sample_3.cram") == set()


# --- the loader ----------------------------------------------------------------------

RULE = "  - {{id: {id}, namespace: {ns}, match: '{match}', names: [{names}]{extra}, rationale: r}}\n"


def rules_text(*rules: dict) -> str:
    return "rules:\n" + "".join(
        RULE.format(
            id=r["id"],
            ns=r.get("ns", "coriell"),
            match=r["match"],
            names=r.get("names", "sample"),
            extra=r.get("extra", ""),
        )
        for r in rules
    )


@pytest.mark.parametrize(
    ("rules", "message"),
    [
        (({"id": "a", "match": "^A$"}, {"id": "a", "match": "^B$"}), "declared twice"),
        (({"id": "a", "match": "^A$", "extra": ", dataset: D"},), "exactly on a dataset_local"),
        (({"id": "a", "ns": "dataset_local", "match": "^A$"},), "exactly on a dataset_local"),
        (({"id": "a", "match": "^(A$"},), "not a regular expression"),
        (({"id": "a", "match": "^(A)$", "extra": r", write: 'X\2'"},), "names a group"),
        (({"id": "a", "match": "^(A)$", "extra": r", write: 'X\g<missing>'"},), "not literal text"),
        (({"id": "a", "match": "^(A)$", "extra": r", write: 'X\n'"},), "not literal text"),
        (({"id": "a", "match": "^(A)$", "extra": ", write: ''"},), "not literal text"),
        # Read by `re` as group 10, not group 1 then "0".
        (({"id": "a", "match": "^(A)$", "extra": r", write: 'X\10'"},), "not literal text"),
        (({"id": "a", "match": "^(A)$", "extra": ', write: "X\\nY"'},), "not literal text"),
        (({"id": "a.b", "match": "^A$"},), "a.b"),
        (({"id": "a", "match": "^A$", "names": ""},), "must name a sample, a donor or both"),
        (({"id": "a", "match": "^A$", "names": "sample, sample"},), "must name a sample, a donor or both"),
        (({"id": "a", "match": "^A$", "names": "person"},), "names"),
    ],
)
def test_the_loader_refuses_what_the_model_cannot(rules, message):
    with pytest.raises(ValueError, match=message):
        load_identifier_rules(rules_text(*rules))


def test_two_rules_matching_one_string_is_refused_not_chosen():
    rules = load_identifier_rules(
        rules_text({"id": "a", "match": "^HG.*$"}, {"id": "b", "ns": "giab", "match": "^HG0.*$"})
    )
    with pytest.raises(ValueError, match="matches 2 identifier rules"):
        rules.recognise("HG002", None, SAMPLE)


def recognised(rules, raw: str, dataset: str | None, entity: EntityKind = SAMPLE) -> Identifier:
    got = rules.recognise(raw, dataset, entity)
    assert got is not None, raw
    return got.identifier


def test_a_string_is_read_only_as_what_its_rule_names():
    """A donor accession is no file's sample, and a sample accession keys no donor (#693)."""
    rules = identifier_rules()
    assert rules.recognise("IGVFDO2696EIGV", None, SAMPLE) is None
    assert recognised(rules, "IGVFDO2696EIGV", None, DONOR) == Identifier("igvf", "IGVFDO2696EIGV")
    assert rules.recognise("SRS006902", None, DONOR) is None
    assert recognised(rules, "HG00096", None, DONOR) == coriell("HG00096")
    assert rules.in_name("IGVFDO2696EIGV.fastq.gz") == set()
    assert rules.recognise("IGVFSM9197PTER", None, DONOR) is None
    assert recognised(rules, "IGVFSM9197PTER", None, SAMPLE) == Identifier("igvf", "IGVFSM9197PTER")
    with pytest.raises(ValueError, match="is not one of"):
        rules.recognise("HG00096", None, "person")  # type: ignore[arg-type]


def test_two_rules_naming_different_entities_do_not_compete():
    rules = load_identifier_rules(
        rules_text({"id": "s", "match": "^X\\d$"}, {"id": "d", "ns": "giab", "match": "^X\\d$", "names": "donor"})
    )
    assert recognised(rules, "X1", None) == coriell("X1")
    assert recognised(rules, "X1", None, DONOR) == Identifier("giab", "X1")


def test_a_sample_is_collected_from_the_donor_its_rule_names_with_the_same_identifier():
    """Decision 3 of epic #692: a Coriell number is the cell line and the person it came from."""
    rules = identifier_rules()
    found = rules.collected_from(recognised(rules, "GM19908", None))
    assert found is not None
    assert (found.identifier, found.rule_id) == (coriell("NA19908"), "coriell_cell_line_or_dna")
    giab = rules.collected_from(Identifier("giab", "HG002"))
    assert giab is not None and giab.identifier == Identifier("giab", "HG002")
    assert rules.collected_from(Identifier("sra_sample", "SRS006902")) is None
    assert rules.collected_from(recognised(rules, "simons_data_sample_1", T2T_CHRY)) is None


@pytest.mark.parametrize(
    ("sample", "expected"),
    [
        # Only a rule of the sample's own namespace links it, not one matching the same string in another.
        (Identifier("coriell", "X1"), ("coriell", "a")),
        # A dataset_local rule links only its own dataset's samples.
        (Identifier("dataset_local", "S1", "D"), ("dataset_local", "l")),
        (Identifier("dataset_local", "S1", "E"), None),
        # A rule naming donors alone links nothing.
        (Identifier("giab", "X1"), None),
    ],
)
def test_a_sample_is_linked_only_by_a_rule_of_its_namespace_and_dataset_naming_both(sample, expected):
    rules = load_identifier_rules(
        rules_text(
            {"id": "a", "match": "^X\\d$", "names": "sample, donor"},
            {"id": "g", "ns": "giab", "match": "^X\\d$", "names": "donor"},
            {"id": "l", "ns": "dataset_local", "match": "^S\\d$", "names": "sample, donor", "extra": ", dataset: D"},
        )
    )
    found = rules.collected_from(sample)
    assert (None if found is None else (found.identifier.namespace, found.rule_id)) == expected
    if found is not None:
        assert found.identifier == sample


def test_a_rule_naming_both_that_writes_what_it_does_not_accept_is_refused_not_unlinked():
    """`GM19908` written `NA19908` by a rule matching only `GM` could not be linked to its donor."""
    rules = load_identifier_rules(
        rules_text({"id": "a", "match": "^GM(\\d{5})$", "names": "sample, donor", "extra": ", write: 'NA\\1'"})
    )
    with pytest.raises(ValueError, match="its own pattern does not match"):
        rules.recognise("GM19908", None, SAMPLE)
    only_samples = load_identifier_rules(rules_text({"id": "a", "match": "^GM(\\d{5})$", "extra": ", write: 'NA\\1'"}))
    assert recognised(only_samples, "GM19908", None) == coriell("NA19908")


def test_two_rules_linking_one_sample_are_refused():
    rules = load_identifier_rules(
        rules_text(
            {"id": "a", "match": "^X\\d$", "names": "sample, donor"},
            {"id": "b", "match": "^X1$", "names": "sample, donor"},
        )
    )
    with pytest.raises(ValueError, match="matches 2 identifier rules"):
        rules.collected_from(coriell("X1"))


def test_a_rule_naming_only_samples_links_no_donor():
    rules = load_identifier_rules(rules_text({"id": "s", "match": "^X\\d$"}))
    assert rules.collected_from(coriell("X1")) is None


def test_no_identifier_rule_id_is_a_code_rule_or_marker_id():
    declared = {
        d.id for d in (*code_rules.CODE_RULES, *code_rules.MARKERS, *code_rules.EDGE_RULES, *code_rules.SAMPLE_RULES)
    }
    assert {r.id for r in identifier_rule_declarations()} & declared == set()


# --- lists ---------------------------------------------------------------------------


def test_a_list_is_named_by_its_members_whatever_their_order_or_repeats():
    a, b = coriell("HG00096"), coriell("HG00097")
    assert list_id([a, b]) == list_id([b, a, b])
    assert list_id([a]) != list_id([a, b])
    assert len(list_id([a])) == 16


def test_a_dataset_local_identifier_differs_from_the_same_name_elsewhere():
    assert list_id([Identifier("dataset_local", "S1", "D1")]) != list_id([Identifier("dataset_local", "S1", "D2")])


def test_a_sample_list_and_a_reference_name_the_same_list():
    members = [coriell("HG00097"), coriell("HG00096")]
    entry = sample_list(members)
    ref = reference(members, [{"source_type": "content_read", "rule_id": "x"}])
    assert entry["list_id"] == ref["list_id"]
    assert [m["id"] for m in entry["members"]] == ["HG00096", "HG00097"]
    assert ref["count"] == 2


def test_a_reference_names_at_least_one_sample():
    with pytest.raises(ValueError, match="at least one"):
        reference([], [])


# --- the header readers ---------------------------------------------------------------


def test_a_bam_header_names_each_distinct_read_group_sample():
    got = BAM_SAMPLES.read("@HD\tVN:1.6\n@RG\tID:1\tSM:GM19908\n@RG\tID:2\tSM:NA19908\n@RG\tID:3\tSM:HG00096\n", None)
    assert got.outcome == NAMED and got.members == {coriell("NA19908"), coriell("HG00096")}
    ref = got.reference()
    assert ref is not None and ref["count"] == 2
    assert ref["named_by"] == [{"source_type": "content_read", "rule_id": code_rules.BAM_READ_GROUP_SAMPLES.id}]


def test_one_unrecognised_string_names_no_samples():
    """A list missing a member would say the file holds fewer samples than it does."""
    got = BAM_SAMPLES.read("@RG\tID:1\tSM:HG00096\n@RG\tID:2\tSM:Sample\n", None)
    assert got.outcome == UNRECOGNISED and got.unrecognised == ("Sample",)
    assert got.members == frozenset() and got.reference() is None


def test_a_read_group_without_sm_makes_the_header_name_no_samples():
    """lane2's reads are someone's: a list of NA12878 alone could be missing a member."""
    got = BAM_SAMPLES.read("@RG\tID:lane1\tSM:NA12878\n@RG\tID:lane2\tPL:ILLUMINA\n", None)
    assert got.outcome == UNRECOGNISED and got.reference() is None
    assert BAM_SAMPLES.read("@RG\tID:1\tPL:ILLUMINA\n", None).outcome == UNRECOGNISED


def test_a_header_with_no_read_group_names_none():
    got = BAM_SAMPLES.read("@HD\tVN:1.6\n", None)
    assert got.outcome == NO_SAMPLE and got.reference() is None


def test_a_vcf_names_its_sample_columns():
    header = parse_vcf_header(f"##fileformat=VCFv4.2\n{CHROM}\tFORMAT\tHG00096\tHG00097\n")
    assert header.sample_columns == ("HG00096", "HG00097")
    got = VCF_SAMPLES.read(header, None)
    assert got.outcome == NAMED and got.members == {coriell("HG00096"), coriell("HG00097")}
    ref = got.reference()
    assert ref is not None and ref["named_by"][0]["rule_id"] == code_rules.VCF_SAMPLE_COLUMNS.id


@pytest.mark.parametrize(
    ("text", "columns"),
    [
        # Sites-only: no FORMAT column, and so no sample columns.
        (f"##fileformat=VCFv4.2\n{CHROM}\n", ()),
        # A PLINK .pvar's #CHROM line has no FORMAT column either.
        ("##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tCM\n", ()),
    ],
)
def test_a_vcf_without_sample_columns_names_none(text, columns):
    header = parse_vcf_header(text)
    assert header.sample_columns == columns
    assert VCF_SAMPLES.read(header, None).outcome == NO_SAMPLE


@pytest.mark.parametrize(
    "columns",
    ["\tformat\tHG00096", "\tHG00096\tHG00097", "\tCM\tHG00096", "\tHG00096\tCM", "\tFORMAT\tHG00096\t", "\tCM\tCM"],
    ids=["lower-case format", "no FORMAT", "CM then a column", "CM after a column", "a trailing tab", "CM twice"],
)
def test_columns_after_info_with_no_format_are_unread_not_sampleless(columns):
    """A malformed #CHROM line is not a sites-only file's (#655)."""
    header = parse_vcf_header(f"##fileformat=VCFv4.2\n{CHROM}{columns}\n")
    assert header.sample_columns is None
    assert VCF_SAMPLES.read(header, None).outcome == UNREAD


def test_a_chrom_line_not_split_by_tabs_is_unread():
    header = parse_vcf_header("##fileformat=VCFv4.2\n#CHROM POS ID REF ALT QUAL FILTER INFO FORMAT HG002 HG003\n")
    assert header.sample_columns is None


@pytest.mark.parametrize(
    ("line", "vcf"),
    [
        ("#CHROM\tPOS\tID\tREF\tALT", False),
        ("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tCM", False),
        (CHROM, True),
        (f"{CHROM}\tFORMAT", True),
    ],
    ids=["a pvar's five", "a pvar's nine, CM after INFO", "the fixed eight", "FORMAT and no sample"],
)
def test_a_line_with_no_sample_column_names_none(line, vcf):
    header = parse_vcf_header(f"##fileformat=VCFv4.2\n{line}\n")
    assert (header.sample_columns, header.vcf_columns) == ((), vcf)
    assert VCF_SAMPLES.read(header, None).outcome == NO_SAMPLE


def test_a_vcf_head_that_ends_before_its_chrom_line_is_unread_not_sampleless():
    header = parse_vcf_header("##fileformat=VCFv4.2\n##contig=<ID=chr1,length=1>\n")
    assert header.sample_columns is None
    got = VCF_SAMPLES.read(header, None)
    assert got.outcome == UNREAD and got.reference() is None


def test_a_dataset_local_name_is_read_only_in_its_dataset():
    header = parse_vcf_header(f"{CHROM}\tFORMAT\tsimons_data_sample_7\n")
    assert VCF_SAMPLES.read(header, T2T_CHRY).outcome == NAMED
    assert VCF_SAMPLES.read(header, "ANVIL_T2T").outcome == UNRECOGNISED


def test_a_sample_map_names_the_sample_in_each_rows_first_column():
    rows = parse_sample_map("HG00096\tgs://b/HG00096.chr22.hc.vcf.gz\nGM19908\tgs://b/NA19908.chr22.hc.vcf.gz\n")
    got = SAMPLE_MAP_SAMPLES.read(rows, None)
    assert got.outcome == NAMED and got.members == {coriell("HG00096"), coriell("NA19908")}
    ref = got.reference()
    assert ref is not None and ref["named_by"][0]["rule_id"] == code_rules.SAMPLE_MAP_ROWS.id


def test_a_sample_map_with_a_name_no_rule_recognises_names_none_and_a_file_no_map_names_none():
    rows = parse_sample_map("HG00096\tgs://b/a.g.vcf.gz\nSample\tgs://b/b.g.vcf.gz\n")
    assert SAMPLE_MAP_SAMPLES.read(rows, None).outcome == UNRECOGNISED
    assert parse_sample_map("not a map\n") is None
    assert SAMPLE_MAP_SAMPLES.read(None, None).outcome == NO_SAMPLE


# --- the producer ----------------------------------------------------------------------


def test_the_bam_producer_writes_each_files_samples_its_lists_and_counts_every_outcome(tmp_path):
    records: list[dict] = [
        {"file_name": "a.bam", "dataset_title": "T"},
        {"file_name": "b.bam", "dataset_title": "T"},
        {"file_name": "c.bam", "dataset_title": "T"},
        {"file_name": "d.bam", "dataset_title": "T"},
    ]
    for n, record in enumerate(records):
        record.update(file_id=f"f{n}", file_md5sum=f"{n:032x}", file_size=1, file_format=".bam")
    headers = {
        f"{0:032x}": "@RG\tID:1\tSM:GM12878\n",
        f"{1:032x}": "@RG\tID:1\tSM:NA12878\n",
        f"{2:032x}": "@RG\tID:1\tSM:Sample\n",
        f"{3:032x}": "@HD\tVN:1.6\n",
    }

    def fetch(evidence_dir, md5, **kwargs):
        return headers[md5]

    config = dataclasses.replace(BAM_CONFIG, fetcher=fetch, preflight=None)
    pipeline = ClassifyPipeline(
        config,
        write_metadata(tmp_path / "in.json", records),
        tmp_path / "bam.json",
        evidence_base=tmp_path / "ev",
        workers=1,
    )
    rows = {r["file_id"]: r for r in pipeline.run()}
    written = json.loads((tmp_path / "bam.json").read_text())

    # GM12878 and NA12878 are one sample, so the two files point to one list, written once.
    assert rows["f0"]["samples"]["list_id"] == rows["f1"]["samples"]["list_id"]
    assert written[SAMPLE_LISTS_KEY] == [sample_list([coriell("NA12878")])]
    assert rows["f2"]["samples"] is None and rows["f3"]["samples"] is None
    details = written["metadata"]["details"]
    assert details[SAMPLE_OUTCOMES_KEY] == {"T": {NAMED: 2, UNRECOGNISED: 1, NO_SAMPLE: 1}}
    assert details[UNRECOGNISED_SAMPLES_KEY] == {"T": {"Sample": 1}}


def test_the_most_frequent_strings_tie_by_the_string_whatever_order_they_were_counted_in():
    """A producer counts from many threads; its metadata must not depend on which finished first."""
    a = Counter({"b": 1, "a": 1, "c": 2})
    b = Counter({"c": 2, "a": 1, "b": 1})
    assert list(most_frequent(a)) == list(most_frequent(b)) == ["c", "a", "b"]
    assert most_frequent(a, 2) == {"c": 2, "a": 1}


def test_a_name_is_never_read_by_a_dataset_local_rule():
    rules = load_identifier_rules(
        rules_text({"id": "s", "ns": "dataset_local", "match": "^S\\d$", "extra": ", dataset: D"})
    )
    assert rules.recognise("S1", "D", SAMPLE) is not None
    assert rules.in_name("S1.bam") == set()


def test_the_producer_reads_a_header_in_its_files_dataset(tmp_path):
    """A dataset's own names (T2T_CHRY's SGDP names) are samples only in that dataset."""
    records: list[dict] = [
        {"file_name": "a.bam", "dataset_title": T2T_CHRY},
        {"file_name": "b.bam", "dataset_title": "X"},
    ]
    for n, record in enumerate(records):
        record.update(file_id=f"f{n}", file_md5sum=f"{n:032x}", file_size=1, file_format=".bam")

    def fetch(evidence_dir, md5, **kwargs):
        return "@RG\tID:1\tSM:simons_data_sample_7\n"

    config = dataclasses.replace(BAM_CONFIG, fetcher=fetch, preflight=None)
    pipeline = ClassifyPipeline(
        config,
        write_metadata(tmp_path / "in.json", records),
        tmp_path / "bam.json",
        evidence_base=tmp_path / "ev",
        workers=1,
    )
    rows = {r["file_id"]: r for r in pipeline.run()}
    assert rows["f0"]["samples"] is not None and rows["f1"]["samples"] is None
