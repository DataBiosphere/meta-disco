"""The slot map and its loader (#369): one entry shape, spans that belong to the names
they claim, the three structural exclusions enforced rather than hoped for, and the
bundled AnVIL map holding to all of it — including citing no classification run."""

from pathlib import Path

import pytest

from meta_disco.azul_manifest import PUBLISHED_TABLE
from meta_disco.manifest_survey import NAME_TOKENS, name_tokens
from meta_disco.models import (
    CLASSIFICATION_FIELDS,
    EVIDENCE_FIELDS,
    SOURCE_CONTENT_READ,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_METADATA,
    SOURCE_WRANGLER_ANNOTATION,
)
from meta_disco.slot_map import (
    ENTITY_TOKENS,
    SOURCE_CELL,
    SOURCE_COLUMN_NAME,
    SOURCE_TABLE_NAME,
    default_slot_map_resource,
    is_derivative_column,
    load_slot_map,
    published_slot_map_resource,
    row_key,
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

# The two harmonized columns AnVIL publishes on `anvil_file`, each a slot of the
# published slot map. Spelled here as the expectation the map is held to.
PUBLISHED_COLUMNS = ("data_modality", "reference_assembly")


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
    for bad in (SOURCE_WRANGLER_ANNOTATION, SOURCE_CONTENT_READ, "''", "null"):
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


# --- the three structural exclusions ------------------------------------------


def test_an_entity_shaped_token_is_refused_as_a_source(tmp_path):
    """`interval` says what a row is — a scatter window — not what its files are (R2)."""
    text = "catalog: c\ndatasets:\n  D:\n    PAR_interval_CHM13v2:\n      sgdp_genomics_db_tar:\n        data_type:\n          - {table_name: interval}\n"
    refuses(tmp_path, text, "span 'interval' names what a row is")
    assert "interval" in ENTITY_TOKENS


def test_a_derivative_column_takes_no_data_type_but_keeps_its_reference(tmp_path):
    index = "catalog: c\ndatasets:\n  D:\n    1KGP_CHM13v2_sample:\n      chr1_hcvcf_index:\n        data_type:\n          - {table_name: sample}\n"
    refuses(tmp_path, index, "'chr1_hcvcf_index' is an index column")
    reference = "catalog: c\ndatasets:\n  D:\n    1KGP_CHM13v2_sample:\n      chr1_hcvcf_index:\n        reference_assembly:\n          - {table_name: CHM13v2}\n"
    (entry,) = load(tmp_path, reference).entries
    assert entry.is_derivative


@pytest.mark.parametrize("slot", CLASSIFICATION_FIELDS)
def test_a_checksum_column_takes_no_slot(tmp_path, slot):
    """A checksum holds no data (#596): its data_type is checksum and its carried dimensions are
    not_applicable, so no source speaks for any slot of one."""
    text = f"catalog: c\ndatasets:\n  D:\n    GRCh38_alignments:\n      cram_md5:\n        {slot}:\n          - {{table_name: GRCh38}}\n"
    refuses(tmp_path, text, "'cram_md5' is a checksum column")


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

    @pytest.mark.parametrize("resource", [default_slot_map_resource, published_slot_map_resource])
    def test_the_map_cites_no_classification_run(self, resource):
        """Sources stay pure (R1, contract 3.4): nothing in either file names a run or a result."""
        text = resource().read_text(encoding="utf-8")
        for forbidden in ("output/", "classifications", "notes:", "agree", "inference"):
            assert forbidden not in text, forbidden

    def test_a_table_name_and_a_column_name_on_one_slot_are_different_words(self):
        """`assembly_annotation.mat_repeat_masker` says `annotation` and `repeat_masker` for data_type:
        two facts. The same word from both names is one source, and the loader refuses it twice."""
        for entry in load_slot_map().entries:
            for slot, sources in entry.slots.items():
                spans = [s.value.casefold() for s in sources if s.is_name]
                assert len(spans) == len(set(spans)), (entry.dataset, entry.table, entry.column, slot)

    def test_every_slot_in_the_map_is_a_classification_field_or_samples(self):
        for entry in load_slot_map().entries:
            assert set(entry.slots) <= set(EVIDENCE_FIELDS)


class TestTheBundledPublishedMap:
    """The published map (#497): the harmonized `anvil_file` columns, which are what
    AnVIL itself publishes for a file, read through the same importer under its own
    label so reconcile can tell the repository's value from a submitter's."""

    def test_it_loads_against_the_same_catalog_and_declares_the_published_kind(self):
        slot_map = load_slot_map(published_slot_map_resource())
        assert slot_map.catalog == load_slot_map().catalog
        assert slot_map.source_type == SOURCE_PUBLISHED_VALUE
        assert slot_map.entries

    def test_it_maps_only_the_declared_published_table_and_only_its_published_columns(self):
        """One table — AnVIL's published table — its TDR link
        column, and each published slot read from the cell of the same name: nothing a
        submitter wrote and no name span."""
        for entry in load_slot_map(published_slot_map_resource()).entries:
            assert (entry.table, entry.column) == (PUBLISHED_TABLE, "file_ref"), entry
            assert set(entry.slots) == set(PUBLISHED_COLUMNS), entry
            for slot, sources in entry.slots.items():
                assert [(source.form, source.value) for source in sources] == [(SOURCE_CELL, slot)], entry

    def test_the_submitter_map_never_reads_the_published_table(self):
        """The two maps are two sources: a submitter's table is one, what the repository
        publishes is the other, and the submitter map does not reach into it. Pinned by
        `anvil_evidence.check` too; this is the bundled map holding to it."""
        assert not [e for e in load_slot_map().entries if e.table == PUBLISHED_TABLE]


def test_a_slot_map_may_not_declare_a_lineage_only_kind(tmp_path):
    path = tmp_path / "map.yaml"
    path.write_text(
        "catalog: anvil15\nsource_type: repository_activity\ndatasets:\n  D:\n    t:\n      c:\n        platform:\n          - {cell: p}\n"
    )
    with pytest.raises(ValueError, match="written only as lineage evidence"):
        load_slot_map(path)


@pytest.mark.parametrize(
    "sources",
    [
        "[{table_name: hifi}]",
        "[{column_name: path}]",
        "[{cell: sample_id}, {cell: coriell_id}]",
    ],
)
def test_a_sample_is_read_from_exactly_one_cell(tmp_path, sources):
    path = tmp_path / "map.yaml"
    path.write_text(f"catalog: anvil15\ndatasets:\n  D:\n    hifi:\n      path:\n        samples: {sources}\n")
    with pytest.raises(ValueError, match="exactly one cell"):
        load_slot_map(path)


# --- folder entries (#604) ----------------------------------------------------

FOLDER = """
catalog: anvil15
datasets:
  D:
    sequencing:
      seq_filename:
        files_under: reads/fast5
        assay_type:
          - {cell: sequencing_assay}
          - {table_name: sequencing}
"""


def test_a_folder_entry_names_the_path_below_the_folder_its_column_names(tmp_path):
    slot_map = load(tmp_path, FOLDER)
    (entry,) = slot_map.entries
    assert entry.is_folder
    assert slot_map.has_folders("D")
    assert entry.files_under == "reads/fast5"
    assert entry.folder_prefix("HG002") == "HG002/reads/fast5/"
    assert set(entry.slots) == {"assay_type"}


def test_a_link_entry_is_not_a_folder_entry(tmp_path):
    slot_map = load(tmp_path, MINIMAL)
    (entry,) = slot_map.entries
    assert not entry.is_folder
    assert not slot_map.has_folders("D")
    with pytest.raises(ValueError, match="link column"):
        entry.folder_prefix("HG002")


@pytest.mark.parametrize(
    "value", ['""', '"/reads"', '"reads/"', '"reads//fast5"', '"."', '".."', '"reads/../x"', "3", "null", "[reads]"]
)
def test_files_under_is_a_relative_path_of_folder_names(tmp_path, value):
    refuses(tmp_path, FOLDER.replace("files_under: reads/fast5", f"files_under: {value}"), "files_under is")


def test_a_folder_entry_maps_at_least_one_slot(tmp_path):
    text = "catalog: anvil15\ndatasets:\n  D:\n    sequencing:\n      seq_filename:\n        files_under: reads\n"
    refuses(tmp_path, text, "names files_under and no slot")


@pytest.mark.parametrize("span", ["seq", "sample", "interval"])
def test_a_folder_columns_name_is_no_span_for_a_slot_whatever_the_span(tmp_path, span):
    text = FOLDER.replace("{table_name: sequencing}", f"{{column_name: {span}}}")
    refuses(tmp_path, text, "names a folder", "describes no file")


@pytest.mark.parametrize("sources", ["[{cell: sample_id}]", "[{cell: a}, {cell: b}]", "[{table_name: sequencing}]"])
def test_a_folder_entry_reads_no_samples_however_they_are_spelled(tmp_path, sources):
    text = FOLDER + f"        samples: {sources}\n"
    refuses(tmp_path, text, "a folder entry reads no samples", "#740")


def test_a_cell_may_not_read_a_folder_column_of_its_table_as_a_value(tmp_path):
    text = FOLDER.replace(
        "    sequencing:\n",
        "    sequencing:\n      seq_fileref:\n        platform:\n          - {cell: seq_filename}\n",
    )
    refuses(tmp_path, text, "cell 'seq_filename' is a folder column of this table")


# --- a cell of a linked row (#562) ---------------------------------------------

LINKED = """
catalog: anvil15
datasets:
  D:
    plink_file_wide:
      pgen:
        platform:
          - {cell: seq_platform, row_of: sequencing_dataset}
        data_type:
          - {table_name: plink}
"""


def test_a_cell_may_be_read_from_the_row_its_row_links_to(tmp_path):
    slot_map = load(tmp_path, LINKED)
    (entry,) = slot_map.entries
    (source,) = entry.slots["platform"]
    assert (source.form, source.value, source.row_of) == (SOURCE_CELL, "seq_platform", "sequencing_dataset")
    assert slot_map.cells("D", "plink_file_wide") == set()
    assert slot_map.cells("D", "sequencing_dataset") == {"seq_platform"}
    assert slot_map.linked_tables("D") == ["sequencing_dataset"]
    assert slot_map.source_tables("D") == ["sequencing_dataset", "plink_file_wide"]
    assert slot_map.readers("D", "sequencing_dataset") == ["plink_file_wide"]
    assert slot_map.readers("D", "plink_file_wide") == ["plink_file_wide"]
    assert row_key("sequencing_dataset") == "sequencing_dataset_id"


def test_row_of_is_for_a_cell_never_a_span_of_the_entrys_own_names(tmp_path):
    text = LINKED.replace("{table_name: plink}", "{table_name: plink, row_of: sequencing_dataset}")
    refuses(tmp_path, text, "row_of reads a cell of a linked row")


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        ("plink_file_wide", "is the entry's own table"),
        ('""', "not the name of"),
        ("3", "not the name of"),
        ("[x]", "not the name of"),
    ],
)
def test_row_of_names_another_table(tmp_path, value, fragment):
    text = LINKED.replace("row_of: sequencing_dataset", f"row_of: {value}")
    refuses(tmp_path, text, fragment)


def test_a_cell_and_row_of_are_the_only_pair_a_source_may_hold(tmp_path):
    text = LINKED.replace("row_of: sequencing_dataset}", "row_of: sequencing_dataset, table_name: plink}")
    refuses(tmp_path, text, "one mapping with one key", "may add row_of")


def test_a_sample_is_never_read_through_a_link(tmp_path):
    text = LINKED + "        samples:\n          - {cell: sample_id, row_of: sample}\n"
    refuses(tmp_path, text, "through row_of")


def test_a_linked_table_is_not_also_mapped_by_its_own_file_links(tmp_path):
    text = LINKED + "    sequencing_dataset:\n      readme:\n        platform:\n          - {cell: seq_platform}\n"
    refuses(tmp_path, text, "row_of 'sequencing_dataset' is a table this map also maps")


def test_a_cell_of_the_row_and_the_same_cell_of_a_linked_row_are_two_sources(tmp_path):
    text = LINKED.replace("        platform:\n", "        platform:\n          - {cell: seq_platform}\n")
    entry = load(tmp_path, text).entries[0]
    assert [s.row_of for s in entry.slots["platform"]] == [None, "sequencing_dataset"]
    twice = LINKED.replace(
        "          - {cell: seq_platform, row_of: sequencing_dataset}\n",
        "          - {cell: seq_platform, row_of: sequencing_dataset}\n" * 2,
    )
    refuses(tmp_path, twice, "the same fact spelled twice")


@pytest.mark.parametrize(
    ("column", "slot", "fragment"),
    [
        ("pgen_md5", "platform", "checksum column"),
        ("pgen_index", "data_type", "index column"),
        ("psam", "platform", "sample-table column"),
        ("psam", "assay_type", "sample-table column"),
    ],
)
def test_a_linked_cell_obeys_the_link_columns_structural_exclusions(tmp_path, column, slot, fragment):
    text = f"catalog: anvil15\ndatasets:\n  D:\n    plink_file_wide:\n      {column}:\n        {slot}:\n          - {{cell: x, row_of: sequencing_dataset}}\n"
    refuses(tmp_path, text, fragment)


def test_a_linked_tables_key_is_a_pointer_not_a_value(tmp_path):
    text = LINKED.replace("{cell: seq_platform, row_of", "{cell: sequencing_dataset_id, row_of")
    refuses(tmp_path, text, "is sequencing_dataset's key")


def test_a_rows_own_link_to_another_table_is_a_pointer_not_a_value(tmp_path):
    text = LINKED.replace(
        "{table_name: plink}", "{table_name: plink}\n        assay_type:\n          - {cell: sequencing_dataset_id}"
    )
    refuses(tmp_path, text, "cell 'sequencing_dataset_id' is a link to another table's row")


def test_a_linked_cell_may_share_a_name_with_a_column_of_the_linking_table(tmp_path):
    """The own-row refusals are about the row's own columns; a linked row's `pgen` or `seq_filename` is another table's."""
    text = LINKED.replace("{cell: seq_platform, row_of", "{cell: pgen, row_of")
    assert load(tmp_path, text).entries[0].slots["platform"][0].value == "pgen"
    folder = FOLDER + "        platform:\n          - {cell: seq_filename, row_of: sequencing_dataset}\n"
    assert load(tmp_path, folder).linked_tables("D") == ["sequencing_dataset"]


def test_no_link_to_a_linked_table_is_read_as_a_value_on_either_side_anywhere_in_the_dataset(tmp_path):
    """The link column is a pointer whichever row holds it, and whichever of the dataset's tables reads it."""
    two = LINKED + "        assay_type:\n          - {cell: x, row_of: sample_set}\n"
    assert load(tmp_path, two).linked_tables("D") == ["sequencing_dataset", "sample_set"]
    linked_side = two + "        data_modality:\n          - {cell: sample_set_id, row_of: sequencing_dataset}\n"
    refuses(tmp_path, linked_side, "cell 'sample_set_id' is a link to another table's row")
    elsewhere = LINKED + "    vcf:\n      path:\n        assay_type:\n          - {cell: sequencing_dataset_id}\n"
    refuses(tmp_path, elsewhere, "D/vcf/path assay_type: cell 'sequencing_dataset_id' is a link")


def test_two_sources_differing_where_a_dot_falls_are_two_sources(tmp_path):
    text = LINKED.replace(
        "          - {cell: seq_platform, row_of: sequencing_dataset}\n",
        "          - {cell: c, row_of: a.b}\n          - {cell: b.c, row_of: a}\n",
    )
    assert len(load(tmp_path, text).entries[0].slots["platform"]) == 2


def test_a_sample_table_column_may_name_its_samples(tmp_path):
    """A `.psam` takes no dimension (#751), but a cell naming its samples is the one slot it may take."""
    text = "catalog: anvil15\ndatasets:\n  D:\n    plink_file_wide:\n      psam:\n        samples:\n          - {cell: sample_id}\n"
    assert load(tmp_path, text).entries[0].slots["samples"][0].value == "sample_id"
