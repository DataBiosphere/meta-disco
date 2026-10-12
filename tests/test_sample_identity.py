"""A file's samples as identifiers (#357): the identifier rules, sample lists, and the header readers."""

import dataclasses
import json
from collections import Counter

import pytest

from meta_disco import code_rules
from meta_disco.file_types import BAM_CONFIG
from meta_disco.pipeline import ClassifyPipeline
from meta_disco.records import SAMPLE_LISTS_KEY, SAMPLE_OUTCOMES_KEY, UNRECOGNISED_SAMPLES_KEY
from meta_disco.sample_identity import (
    BAM_SAMPLES,
    NAMED,
    NO_SAMPLE,
    UNRECOGNISED,
    VCF_SAMPLES,
    Identifier,
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
    got = identifier_rules().recognise(raw, dataset)
    assert got is not None
    assert (got.identifier.namespace, got.identifier.id) == (namespace, ident)
    assert got.rule_id in identifier_rules().rule_ids


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
    assert identifier_rules().recognise(raw, dataset) is None


def test_a_dataset_local_identifier_carries_its_dataset():
    got = identifier_rules().recognise("simons_data_sample_1", T2T_CHRY)
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

RULE = "  - {{id: {id}, namespace: {ns}, match: '{match}'{extra}, rationale: r}}\n"


def rules_text(*rules: dict) -> str:
    return "rules:\n" + "".join(
        RULE.format(id=r["id"], ns=r.get("ns", "coriell"), match=r["match"], extra=r.get("extra", "")) for r in rules
    )


@pytest.mark.parametrize(
    ("rules", "message"),
    [
        (({"id": "a", "match": "^A$"}, {"id": "a", "match": "^B$"}), "declared twice"),
        (({"id": "a", "match": "^A$", "extra": ", dataset: D"},), "exactly on a dataset_local"),
        (({"id": "a", "ns": "dataset_local", "match": "^A$"},), "exactly on a dataset_local"),
        (({"id": "a", "match": "^(A$"},), "not a regular expression"),
        (({"id": "a", "match": "^(A)$", "extra": r", write: 'X\2'"},), "names a group"),
        (({"id": "a.b", "match": "^A$"},), "a.b"),
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
        rules.recognise("HG002", None)


def test_no_identifier_rule_id_is_a_code_rule_or_marker_id():
    declared = {
        d.id for d in (*code_rules.CODE_RULES, *code_rules.MARKERS, *code_rules.EDGE_RULES, *code_rules.SAMPLE_RULES)
    }
    assert set(identifier_rules().rule_ids) & declared == set()


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


def test_a_header_with_no_read_group_sample_names_none():
    got = BAM_SAMPLES.read("@HD\tVN:1.6\n@RG\tID:1\tPL:ILLUMINA\n", None)
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
        # No #CHROM line read at all.
        ("##fileformat=VCFv4.2\n", None),
    ],
)
def test_a_vcf_without_sample_columns_names_none(text, columns):
    header = parse_vcf_header(text)
    assert header.sample_columns == columns
    assert VCF_SAMPLES.read(header, None).outcome == NO_SAMPLE


def test_a_dataset_local_name_is_read_only_in_its_dataset():
    header = parse_vcf_header(f"{CHROM}\tFORMAT\tsimons_data_sample_7\n")
    assert VCF_SAMPLES.read(header, T2T_CHRY).outcome == NAMED
    assert VCF_SAMPLES.read(header, "ANVIL_T2T").outcome == UNRECOGNISED


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
