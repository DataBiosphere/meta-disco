"""The slot map and its loader (#369): one entry shape, spans that belong to the names
they claim, the two structural exclusions enforced rather than hoped for, and the
bundled AnVIL map holding to all of it — including citing no classification run."""

from pathlib import Path

import pytest

from meta_disco.azul_manifest import VERBATIM_FILE
from meta_disco.manifest_survey import NAME_TOKENS, name_tokens
from meta_disco.models import (
    CLASSIFICATION_FIELDS,
    SOURCE_CONTENT_READ,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_METADATA,
    SOURCE_WRANGLER_ANNOTATION,
)
from meta_disco.records import PUBLISHED_FIELDS
from meta_disco.slot_map import (
    ENTITY_TOKENS,
    SOURCE_CELL,
    SOURCE_COLUMN_NAME,
    SOURCE_TABLE_NAME,
    default_slot_map_resource,
    is_derivative_column,
    load_slot_map,
    published_slot_map_resource,
)

MINIMAL = """
catalog: anvil15
datasets:
  D:
    hifi:
      path:
        platform:
          - {cell: platform}
          - {table_name: hifi}
"""


def load(tmp_path: Path, text: str):
    path = tmp_path / "map.yaml"
    path.write_text(text)
    return load_slot_map(path)


def refuses(tmp_path: Path, text: str, *fragments: str) -> None:
    with pytest.raises(ValueError) as exc:
        load(tmp_path, text)
    for fragment in fragments:
        assert fragment in str(exc.value), str(exc.value)


# --- shape --------------------------------------------------------------------


def test_one_entry_shape(tmp_path):
    slot_map = load(tmp_path, MINIMAL)
    assert slot_map.catalog == "anvil15"
    (entry,) = slot_map.entries
    assert (entry.dataset, entry.table, entry.column) == ("D", "hifi", "path")
    sources = entry.slots["platform"]
    assert [(s.form, s.value) for s in sources] == [(SOURCE_CELL, "platform"), (SOURCE_TABLE_NAME, "hifi")]
    assert slot_map.cells("D", "hifi") == {"platform"}


def test_a_dataset_with_nothing_to_map_is_simply_absent(tmp_path):
    """The loader requires no dataset, table or column to be present; absence is the statement."""
    assert load(tmp_path, MINIMAL).datasets() == ["D"]


def test_an_empty_level_is_refused_because_absence_spells_it(tmp_path):
    refuses(tmp_path, "catalog: c\ndatasets:\n  D: {}\n", "D", "left out")
    refuses(tmp_path, "catalog: c\ndatasets:\n  D:\n    t: {}\n", "D/t", "left out")
    refuses(tmp_path, "catalog: c\ndatasets:\n  D:\n    t:\n      c: {}\n", "D/t/c", "left out")


def test_a_bare_term_is_a_shape_error(tmp_path):
    """A slot names where its value comes from; the map holds no vocabulary (contract 1.5)."""
    text = "catalog: c\ndatasets:\n  D:\n    hifi:\n      path:\n        platform: PACBIO\n"
    refuses(tmp_path, text, "platform", "bare term", "PACBIO")


def test_a_source_is_exactly_one_form(tmp_path):
    two = "catalog: c\ndatasets:\n  D:\n    hifi:\n      path:\n        platform:\n          - {cell: platform, table_name: hifi}\n"
    refuses(tmp_path, two, "one mapping with one key")
    unknown = "catalog: c\ndatasets:\n  D:\n    hifi:\n      path:\n        platform:\n          - {value: hifi}\n"
    refuses(tmp_path, unknown, "'value' is not a source form")


def test_an_unknown_slot_is_refused(tmp_path):
    text = "catalog: c\ndatasets:\n  D:\n    hifi:\n      path:\n        instrument:\n          - {cell: platform}\n"
    refuses(tmp_path, text, "'instrument' is not a slot")


def test_a_cell_cannot_be_the_link_column_itself(tmp_path):
    text = "catalog: c\ndatasets:\n  D:\n    hifi:\n      path:\n        platform:\n          - {cell: path}\n"
    refuses(tmp_path, text, "file-link column itself")


def test_a_duplicate_key_fails_naming_it(tmp_path):
    """PyYAML keeps the last of two equal keys silently; a column listed twice would lose one."""
    text = "catalog: c\ndatasets:\n  D:\n    hifi:\n      path:\n        platform:\n          - {cell: platform}\n      path:\n        assay_type:\n          - {cell: library_strategy}\n"
    refuses(tmp_path, text, "duplicate key 'path'", "line 8", "first at line 5")


def test_the_top_level_is_catalog_and_datasets_and_optionally_the_source_type(tmp_path):
    refuses(tmp_path, "datasets:\n  D:\n    t:\n      c:\n        platform: [{cell: p}]\n", "top-level keys")
    refuses(tmp_path, "catalog: c\nversion: 2\n" + MINIMAL.split("\n", 2)[2], "top-level keys")
    refuses(
        tmp_path, "catalog: ''\ndatasets:\n  D:\n    t:\n      c:\n        platform: [{cell: p}]\n", "catalog is ''"
    )


def test_a_map_declares_the_kind_of_source_it_describes(tmp_path):
    """The top-level `source_type` is what every envelope written from the map carries
    (#497). Absent, a map describes a submitter's own tables; the published map says
    `published_value`. Only a kind an importer may write is accepted — a curator enters
    as rules, and inference's own kinds name our engine as the publisher."""
    assert load(tmp_path, MINIMAL).source_type == SOURCE_REPOSITORY_METADATA
    published = MINIMAL.replace("catalog: anvil15", f"catalog: anvil15\nsource_type: {SOURCE_PUBLISHED_VALUE}")
    assert load(tmp_path, published).source_type == SOURCE_PUBLISHED_VALUE
    for bad in (SOURCE_WRANGLER_ANNOTATION, SOURCE_CONTENT_READ, "", None):
        refuses(tmp_path, MINIMAL.replace("catalog: anvil15", f"catalog: anvil15\nsource_type: {bad}"), "source_type")


# --- notes --------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "catalog: c\nnotes: x\ndatasets:\n  D:\n    t:\n      c:\n        platform: [{cell: p}]\n",
        "catalog: c\ndatasets:\n  notes: x\n  D:\n    t:\n      c:\n        platform: [{cell: p}]\n",
        "catalog: c\ndatasets:\n  D:\n    notes: x\n    t:\n      c:\n        platform: [{cell: p}]\n",
        "catalog: c\ndatasets:\n  D:\n    t:\n      notes: x\n      c:\n        platform: [{cell: p}]\n",
        "catalog: c\ndatasets:\n  D:\n    t:\n      c:\n        notes: x\n        platform: [{cell: p}]\n",
        "catalog: c\ndatasets:\n  D:\n    t:\n      c:\n        platform: [{notes: x}]\n",
    ],
    ids=["top", "datasets", "dataset", "table", "column", "source"],
)
def test_there_is_no_notes_member_at_any_level(tmp_path, text):
    """Findings go in the pull request and on the issue; a data file is silent (R4)."""
    refuses(tmp_path, text, "no notes member")


# --- spans --------------------------------------------------------------------


def test_a_span_must_be_part_of_the_name_it_claims_in_the_names_casing(tmp_path):
    table = "catalog: c\ndatasets:\n  D:\n    SGDP_CHM13v2_sample:\n      cram:\n        reference_assembly:\n          - {table_name: chm13}\n"
    refuses(
        tmp_path,
        table,
        "span 'chm13' is not a run of whole tokens of the table name 'SGDP_CHM13v2_sample'",
        "own casing",
    )
    column = "catalog: c\ndatasets:\n  D:\n    assembly_sample:\n      mat_chm13_aln_bam:\n        reference_assembly:\n          - {column_name: grch38}\n"
    refuses(tmp_path, column, "span 'grch38' is not a run of whole tokens of the column name 'mat_chm13_aln_bam'")


def test_a_span_is_whole_tokens_of_the_name_not_a_substring(tmp_path):
    """`ont` sits inside `montage` and says nothing about it."""
    text = "catalog: c\ndatasets:\n  D:\n    montage:\n      path:\n        platform:\n          - {table_name: ont}\n"
    refuses(tmp_path, text, "span 'ont' is not a run of whole tokens of the table name 'montage'")
    text = "catalog: c\ndatasets:\n  D:\n    ont_methylation:\n      location:\n        data_modality:\n          - {table_name: methylation}\n"
    assert load(tmp_path, text).entries


def test_a_span_is_transcribed_in_the_names_casing(tmp_path):
    text = "catalog: c\ndatasets:\n  D:\n    SGDP_CHM13v2_sample:\n      cram:\n        reference_assembly:\n          - {table_name: CHM13v2}\n"
    (entry,) = load(tmp_path, text).entries
    assert entry.slots["reference_assembly"][0].value == "CHM13v2"


def test_the_same_word_in_table_and_column_name_is_one_source(tmp_path):
    """`1KGP_CHM13v2_chromosome.chm13v2_pass_vcf_gz` spells the assembly twice; it is one fact (R3)."""
    text = (
        "catalog: c\ndatasets:\n  D:\n    1KGP_CHM13v2_chromosome:\n      chm13v2_pass_vcf_gz:\n"
        "        reference_assembly:\n          - {table_name: CHM13v2}\n          - {column_name: chm13v2}\n"
    )
    refuses(tmp_path, text, "column_name 'chm13v2' repeats table_name 'CHM13v2'", "one source, not two")


def test_the_same_cell_twice_is_refused_too(tmp_path):
    text = "catalog: c\ndatasets:\n  D:\n    hifi:\n      path:\n        platform:\n          - {cell: platform}\n          - {cell: platform}\n"
    refuses(tmp_path, text, "repeats")


def test_a_slot_may_name_several_distinct_sources(tmp_path):
    """`platform` and `instrument_model` are two facts about one file (contract 6.8)."""
    text = (
        "catalog: c\ndatasets:\n  D:\n    hifi:\n      path:\n        platform:\n"
        "          - {cell: platform}\n          - {cell: instrument_model}\n          - {table_name: hifi}\n"
    )
    (entry,) = load(tmp_path, text).entries
    assert len(entry.slots["platform"]) == 3


# --- the two structural exclusions --------------------------------------------


def test_an_entity_shaped_token_is_refused_as_a_source(tmp_path):
    """`interval` says what a row is — a scatter window — not what its files are (R2)."""
    text = "catalog: c\ndatasets:\n  D:\n    PAR_interval_CHM13v2:\n      sgdp_genomics_db_tar:\n        data_type:\n          - {table_name: interval}\n"
    refuses(tmp_path, text, "span 'interval' names what a row is")
    assert "interval" in ENTITY_TOKENS


def test_a_derivative_column_takes_no_data_type_but_keeps_its_reference(tmp_path):
    index = "catalog: c\ndatasets:\n  D:\n    1KGP_CHM13v2_sample:\n      chr1_hcvcf_index:\n        data_type:\n          - {table_name: sample}\n"
    refuses(tmp_path, index, "'chr1_hcvcf_index' is an index or checksum column")
    reference = "catalog: c\ndatasets:\n  D:\n    1KGP_CHM13v2_sample:\n      chr1_hcvcf_index:\n        reference_assembly:\n          - {table_name: CHM13v2}\n"
    (entry,) = load(tmp_path, reference).entries
    assert entry.is_derivative


@pytest.mark.parametrize(
    "column, derivative",
    [
        ("cram_index", True),
        ("mosdepth_regions_bed_idx", True),
        ("mat_chm13_aln_bai", True),
        ("assembly_md5", True),
        ("assembly_fai", True),
        ("gvcf_tbi", True),
        ("assembly.fa.gzi", True),
        ("cram", False),
        ("read_1_fastq", False),
        ("mosdepth_regions_bed", False),
        ("index", True),
    ],
)
def test_which_columns_are_derivative(column, derivative):
    assert is_derivative_column(column) is derivative


# --- anchors -------------------------------------------------------------------


def test_yaml_anchors_give_each_column_its_own_entry(tmp_path):
    """The T2T_CHRY tables list sixty near-identical columns; an alias per column keeps
    the file readable and each column is still its own entry."""
    text = (
        "catalog: c\ndatasets:\n  D:\n    SGDP_CHM13v2_sample:\n"
        "      cram: &t\n        reference_assembly:\n          - {table_name: CHM13v2}\n"
        "      cram_index: *t\n      read_1_fastq: *t\n"
    )
    slot_map = load(tmp_path, text)
    assert [e.column for e in slot_map.entries] == ["cram", "cram_index", "read_1_fastq"]
    assert all(e.slots["reference_assembly"][0].value == "CHM13v2" for e in slot_map.entries)


# --- the bundled AnVIL map -----------------------------------------------------


class TestTheBundledMap:
    def test_it_loads_and_names_the_catalog_it_was_authored_against(self):
        slot_map = load_slot_map()
        assert slot_map.catalog == "anvil15"
        assert slot_map.entries

    def test_every_name_span_carries_the_slot_it_is_declared_under(self):
        """`PAR_interval_CHM13v2`'s reference reads `CHM13v2`, never `interval`: each token of
        a span is one the survey knows, and its slot is the one declared (acceptance criterion)."""
        for entry in load_slot_map().entries:
            for slot, sources in entry.slots.items():
                for source in sources:
                    if not source.is_name:
                        continue
                    tokens = name_tokens(source.value)
                    assert tokens, (entry, source)
                    for token in tokens:
                        assert token in NAME_TOKENS, f"{entry.dataset}/{entry.table}/{entry.column}: {source.value!r}"
                        assert NAME_TOKENS[token][0] == slot, (
                            f"{entry.dataset}/{entry.table}/{entry.column}: span {source.value!r} is a "
                            f"{NAME_TOKENS[token][0]} token, declared under {slot}"
                        )

    def test_the_map_cites_no_classification_run(self):
        """Sources stay pure (R1, contract 3.4): nothing in the file names a run or a result."""
        text = default_slot_map_resource().read_text(encoding="utf-8")
        for forbidden in ("output/", "classifications", "notes:", "agree", "inference"):
            assert forbidden not in text, forbidden

    def test_a_table_name_and_a_column_name_on_one_slot_are_different_words(self):
        """`assembly_annotation.mat_repeat_masker` says `annotation` and `repeat_masker` for data_type:
        two facts. The same word from both names is one source, and the loader refuses it twice."""
        for entry in load_slot_map().entries:
            for slot, sources in entry.slots.items():
                spans = [s.value.casefold() for s in sources if s.is_name]
                assert len(spans) == len(set(spans)), (entry.dataset, entry.table, entry.column, slot)

    def test_every_slot_in_the_map_is_a_classification_field(self):
        for entry in load_slot_map().entries:
            assert set(entry.slots) <= set(CLASSIFICATION_FIELDS)


class TestTheBundledPublishedMap:
    """The published map (#497): the harmonized `anvil_file` columns, which are what
    AnVIL itself publishes for a file, read through the same importer under its own
    label so reconcile can tell the repository's value from a submitter's."""

    def test_it_loads_against_the_same_catalog_and_declares_the_published_kind(self):
        slot_map = load_slot_map(published_slot_map_resource())
        assert slot_map.catalog == load_slot_map().catalog
        assert slot_map.source_type == SOURCE_PUBLISHED_VALUE
        assert slot_map.entries

    def test_it_maps_only_the_anvil_file_table_and_only_its_published_columns(self):
        """One table, its TDR link column, and each published slot read from the cell
        of the same name — nothing a submitter wrote and no name span."""
        for entry in load_slot_map(published_slot_map_resource()).entries:
            assert (entry.table, entry.column) == (VERBATIM_FILE, "file_ref"), entry
            assert set(entry.slots) == set(PUBLISHED_FIELDS), entry
            for slot, sources in entry.slots.items():
                assert [(source.form, source.value) for source in sources] == [(SOURCE_CELL, slot)], entry

    def test_the_submitter_map_never_reads_the_published_columns_from_anvil_file(self):
        """The two maps are two sources: a submitter's table is one, what the repository
        publishes is the other, and the submitter map does not reach into `anvil_file`."""
        assert not [e for e in load_slot_map().entries if e.table == VERBATIM_FILE]

    def test_the_map_cites_no_classification_run(self):
        text = published_slot_map_resource().read_text(encoding="utf-8")
        for forbidden in ("output/", "classifications", "notes:", "agree", "inference"):
            assert forbidden not in text, forbidden
