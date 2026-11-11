"""Curator rules (#777): the loader's checks, and a samples conflict a rule answers or leaves standing."""

from pathlib import Path

import pytest

from meta_disco import code_rules
from meta_disco.curator_rules import CuratorRules, load_curator_rules
from meta_disco.models import SOURCE_REPOSITORY_ACTIVITY, ClaimSource
from meta_disco.reconcile_samples import ACTIVITY, ANSWERED, HEADER, Named, answer, answering_rule
from meta_disco.sample_identity import Identifier, identifier_rules
from meta_disco.slot_map import load_slot_map
from tests.test_reconcile import DATASET
from tests.test_reconcile_samples import HEADER as HEADER_ATTRIBUTION
from tests.test_reconcile_samples import coriell, parent_says, table_says

SLOT_MAP = f"""
catalog: anvil15
source_type: repository_metadata
datasets:
  {DATASET}:
    sample:
      mat_reads:
        samples:
          - {{cell: maternal_id}}
        platform:
          - {{cell: seq_platform}}
      child_reads:
        samples:
          - {{cell: sample_id}}
"""

RULE = f"""
samples:
  - id: parent_reads
    author: someone
    date: "2026-11-10"
    dataset: {DATASET}
    table: sample
    columns: [maternal_id]
    same_sample:
      - {{name: "coriell:NA24695", sample: "giab:HG007", cited: "a registry's record"}}
    rationale: A parent's reads, listed in the child's row.
"""


def load(tmp_path: Path, text: str = RULE) -> CuratorRules:
    slot_map = tmp_path / "slot_map.yaml"
    slot_map.write_text(SLOT_MAP)
    rules = tmp_path / "curator_rules.yaml"
    rules.write_text(text)
    return load_curator_rules(rules, load_slot_map(slot_map), identifier_rules())


@pytest.fixture
def curator(tmp_path: Path) -> CuratorRules:
    return load(tmp_path)


def cell(member: Identifier, column: str = "maternal_id", table: str = "sample") -> Named:
    """The child's row naming ``member`` in ``column``."""
    return table_says(member, column=column, table=table)


def header_says(member: Identifier) -> Named:
    return Named(frozenset({member}), (HEADER_ATTRIBUTION,), kind=HEADER, list_id="list-1")


def activity_says(member: Identifier) -> Named:
    source = ClaimSource(name="anvil", dataset=DATASET, table="anvil_activity", column="used_biosample_id")
    attribution = {
        "source_type": SOURCE_REPOSITORY_ACTIVITY,
        "rule_id": code_rules.SAMPLES_FROM_ACTIVITY_BIOSAMPLE.id,
        "source": source.to_dict(),
        "activity_id": "a1",
    }
    return Named(frozenset({member}), (attribution,), kind=ACTIVITY)


MOTHER, CHILD = Identifier("giab", "HG007"), Identifier("giab", "HG005")


def answered(curator: CuratorRules, named: list[Named], file_name: str, dataset: str = DATASET):
    """The file's samples as the rule judged on its own sources ``named`` answers them, or None."""
    rule = answering_rule(curator, named, dataset, file_name, identifier_rules())
    return None if rule is None else answer(rule, named)


# --- answering -------------------------------------------------------------------------


def test_a_header_agreeing_with_the_table_answers_with_their_samples(curator):
    mother = Identifier("coriell", "HG01105")
    named = [activity_says(Identifier("coriell", "HG01106")), cell(mother), header_says(mother)]
    found = answered(curator, named, "reads.cram")
    assert found is not None
    outcome, samples, members, answered_by = found
    assert (outcome, answered_by, members) == (ANSWERED, "parent_reads", {mother})
    # The header first, then the table, then the rule; the activity is no source of the answer.
    assert samples is not None
    assert [a["rule_id"] for a in samples["named_by"]] == [
        code_rules.BAM_READ_GROUP_SAMPLES.id,
        "coriell_hg",
        "parent_reads",
    ]
    assert samples["named_by"][-1] == {"source_type": "wrangler_annotation", "rule_id": "parent_reads"}
    assert samples["list_id"] == "list-1"


def test_a_name_naming_the_tables_sample_answers(curator):
    found = answered(
        curator,
        [cell(Identifier("giab", "HG004")), activity_says(Identifier("giab", "HG002"))],
        "HG004_HiSeq30x_subsampled_R1.fastq.gz",
    )
    assert found is not None and found.members == {Identifier("giab", "HG004")}


def test_a_name_a_pair_declares_the_tables_sample_answers(curator):
    found = answered(curator, [cell(MOTHER), activity_says(CHILD)], "NA24695_CTTGTA_L002_R1_034.fastq.gz")
    assert found is not None and found.members == {MOTHER}


@pytest.mark.parametrize(
    "file_name",
    [
        "AGAACGAG-CGGCTAAT_S10_L002_R1_001.fastq.gz",  # names no sample
        "NA24694_GCCAAT_L002_R2_021.fastq.gz",  # names a sample no pair makes the table's
        "HG005_HG007.fastq.gz",  # names two
    ],
)
def test_without_a_header_a_name_not_agreeing_answers_nothing(curator, file_name):
    assert answered(curator, [cell(MOTHER), activity_says(CHILD)], file_name) is None


def test_a_name_confirms_no_cell_naming_several_samples_but_a_header_does(curator):
    father = Identifier("giab", "HG006")
    both = table_says(MOTHER, father, column="maternal_id", table="sample")
    name = "NA24695_CTTGTA_L002_R1_034.fastq.gz"
    assert answered(curator, [both, activity_says(CHILD)], name) is None
    header = Named(frozenset({MOTHER, father}), (HEADER_ATTRIBUTION,), kind=HEADER)
    found = answered(curator, [both, header, activity_says(CHILD)], name)
    assert found is not None and found.members == {MOTHER, father}


def test_a_cell_of_another_column_or_table_or_dataset_answers_nothing(curator):
    name = "NA24695_CTTGTA_L002_R1_034.fastq.gz"
    assert answered(curator, [cell(MOTHER, column="sample_id"), activity_says(CHILD)], name) is None
    assert answered(curator, [cell(MOTHER, table="participant"), activity_says(CHILD)], name) is None
    assert answered(curator, [cell(MOTHER), activity_says(CHILD)], name, dataset="AnVIL_OTHER") is None


def test_a_cell_another_datasets_evidence_gives_the_file_answers_nothing(curator):
    """Evidence naming no target dataset joins every dataset's files, so a file's cell may be another dataset's."""
    own = cell(MOTHER)
    attribution = {**own.named_by[0], "source": {**own.named_by[0]["source"], "dataset": "AnVIL_OTHER"}}
    foreign = Named(own.members, (attribution,), kind=own.kind)
    assert answered(curator, [foreign, activity_says(CHILD)], "NA24695_CTTGTA_L002_R1_034.fastq.gz") is None


def test_a_header_alone_beside_the_activity_answers_nothing(curator):
    """The rule answers with its table's cells; a header and an activity disagreeing stand."""
    assert answered(curator, [header_says(MOTHER), activity_says(CHILD)], "NA24695.cram") is None


def test_sources_disagreeing_beside_the_activity_answer_nothing(curator):
    named = [cell(MOTHER), header_says(Identifier("giab", "HG006")), activity_says(CHILD)]
    assert answered(curator, named, "NA24695_CTTGTA_L002_R1_034.fastq.gz") is None


def test_sources_with_no_activity_among_them_are_not_answered(curator):
    """The rule answers against the activity alone: agreeing sources with none beside them are no conflict of its."""
    assert answered(curator, [cell(MOTHER), header_says(MOTHER)], "NA24695.cram") is None


def test_a_pairs_name_answers_only_for_the_sample_it_is_paired_with(curator):
    father = Identifier("giab", "HG006")
    assert answered(curator, [cell(father), activity_says(CHILD)], "NA24695_CTTGTA_L002_R1_034.fastq.gz") is None


def test_a_parents_samples_beside_them_answer_nothing(curator):
    named = [cell(coriell("HG01105")), parent_says("HG01105"), activity_says(coriell("HG01106"))]
    assert answered(curator, named, "HG01105.final.cram") is None


# --- loading ---------------------------------------------------------------------------


def test_the_bundled_rules_load():
    assert load_curator_rules().samples


def test_a_rule_is_loaded_with_its_pairs_and_digest(curator):
    (rule,) = curator.samples
    assert rule.columns == {"maternal_id"} and rule.author == "someone"
    assert [(p.name, p.sample) for p in rule.same_sample] == [(Identifier("coriell", "NA24695"), MOTHER)]
    assert len(curator.digest) == 64


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("columns: [maternal_id]", "columns: [paternal_id]", "reads no samples cell"),
        ("columns: [maternal_id]", "columns: [seq_platform]", "reads no samples cell"),  # read for another slot
        ("table: sample", "table: participant", "reads no samples cell"),
        ("columns: [maternal_id]", "columns: []", "columns"),
        ("    author: someone\n", "", "author"),
        ("author: someone", "author: someone\n    extra: 1", "extra"),
        ("author: someone", "author: ''", "author"),
        ('"giab:HG007"', '"coriell:HG007"', "recognise"),
        ('"coriell:NA24695"', '"NA24695"', "recognise"),
        ('cited: "a registry\'s record"', "cited: ''", "cited"),
        ("columns: [maternal_id]", "columns: maternal_id", "columns"),
    ],
)
def test_a_wrong_rule_is_refused_by_name(tmp_path, old, new, message):
    assert old in RULE
    with pytest.raises(ValueError, match=message):
        load(tmp_path, RULE.replace(old, new))


def test_an_answer_takes_the_agreeing_samples_a_parent_passes_beside_the_files_own(curator):
    (rule,) = curator.samples
    own = [cell(coriell("HG01105")), activity_says(coriell("HG01106"))]
    assert answering_rule(curator, own, DATASET, "HG01105.final.cram", identifier_rules()) is rule
    found = answer(rule, [*own, parent_says("HG01105")])
    assert found is not None and found.samples is not None and found.members == {coriell("HG01105")}
    assert [a["rule_id"] for a in found.samples["named_by"]][-1] == "parent_reads"
    assert answer(rule, [*own, parent_says("HG01104")]) is None


def test_two_rules_one_file_could_match_are_refused(tmp_path):
    body = RULE.split("samples:\n", 1)[1].replace("id: parent_reads", "id: other_reads")
    with pytest.raises(ValueError, match="could both answer"):
        load(tmp_path, RULE + body)


PATERNAL_SLOT_MAP = SLOT_MAP.replace(
    "child_reads:", "pat_reads:\n        samples:\n          - {cell: paternal_id}\n      child_reads:"
)


def test_two_rules_sharing_one_column_of_one_table_are_refused(tmp_path):
    (tmp_path / "slot_map.yaml").write_text(PATERNAL_SLOT_MAP)
    body = RULE.split("samples:\n", 1)[1].replace("id: parent_reads", "id: both_reads")
    (tmp_path / "curator_rules.yaml").write_text(RULE + body.replace("[maternal_id]", "[maternal_id, paternal_id]"))
    with pytest.raises(ValueError, match="could both answer"):
        load_curator_rules(tmp_path / "curator_rules.yaml", load_slot_map(tmp_path / "slot_map.yaml"))


def test_a_name_two_pairs_share_is_refused(tmp_path):
    twice = '{name: "coriell:NA24695", sample: "giab:HG007", cited: "a registry\'s record"}'
    with pytest.raises(ValueError, match="one name twice"):
        load(tmp_path, RULE.replace(twice, twice + "\n      - " + twice.replace("HG007", "HG006")))


def test_two_rules_of_one_table_sharing_no_column_both_load(tmp_path):
    (tmp_path / "slot_map.yaml").write_text(PATERNAL_SLOT_MAP)
    body = RULE.split("samples:\n", 1)[1].replace("id: parent_reads", "id: father_reads")
    (tmp_path / "curator_rules.yaml").write_text(RULE + body.replace("[maternal_id]", "[paternal_id]"))
    loaded = load_curator_rules(tmp_path / "curator_rules.yaml", load_slot_map(tmp_path / "slot_map.yaml"))
    assert [r.id for r in loaded.samples] == ["parent_reads", "father_reads"]


def test_a_repeated_rule_id_is_refused(tmp_path):
    body = RULE.split("samples:\n", 1)[1]
    with pytest.raises(ValueError, match="repeated"):
        load(tmp_path, RULE + body)


def test_a_document_of_another_kind_is_refused(tmp_path):
    with pytest.raises(ValueError, match="mapping of"):
        load(tmp_path, RULE.replace("samples:", "dimensions:", 1))


def test_samples_that_are_no_list_are_refused(tmp_path):
    with pytest.raises(ValueError, match="samples is a list"):
        load(tmp_path, "samples: {}\n")


def test_pairs_that_are_no_list_are_refused(tmp_path):
    head = RULE.split("    same_sample:\n", 1)[0]
    with pytest.raises(ValueError, match="same_sample is a list"):
        load(tmp_path, head + "    same_sample: {}\n    rationale: A parent's reads.\n")
