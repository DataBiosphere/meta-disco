"""A PLINK 2 fileset's sample table (#751): a `.psam`'s IIDs as its samples, and each `.psam` paired with its fileset."""

import pytest

from meta_disco import code_rules, edges
from meta_disco.plink import (
    MEMBERS,
    NO_HEADER,
    NO_PATH,
    SAMPLE_TABLES,
    SEVERAL_CARRY,
    SHORT_ROW,
    UNPAIRED,
    PsamRows,
    filesets,
    parse_psam,
)
from meta_disco.record_keys import RecordKey
from meta_disco.sample_identity import NAMED, NO_SAMPLE, PSAM_SAMPLES, UNREAD, UNRECOGNISED, Identifier

KEY = RecordKey("file_id", "file_id")
PRIMED = "#IID\tPAT\tMAT\tSEX\tSuperPop\tPopulation\nHG01879\t0\t0\t1\tAFR\tACB\nNA19700\t0\t0\t1\tAFR\tASW\n"


# --- reading a .psam ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "iids"),
    [
        pytest.param(PRIMED, ("HG01879", "NA19700"), id="PRIMED's header, IID first"),
        pytest.param("#FID\tIID\tSEX\nfam1\tHG01879\t1\n", ("HG01879",), id="FID first, IID second"),
        pytest.param("##comment\n#IID SEX\nHG01879 1\n\n", ("HG01879",), id="## lines and blank lines skipped"),
        pytest.param("#IID\tSEX\n", (), id="a header and no row"),
    ],
)
def test_a_psam_gives_each_rows_iid(text, iids):
    assert parse_psam(text) == PsamRows(iids)


@pytest.mark.parametrize(
    ("text", "why"),
    [
        pytest.param("HG01879\tHG01879\t0\t0\t1\t-9\n", NO_HEADER, id="headerless, as .fam columns"),
        pytest.param("#FID\tSEX\nfam1\t1\n", NO_HEADER, id="a header naming no IID"),
        pytest.param("", NO_HEADER, id="empty"),
        pytest.param("#FID\tIID\nfam1\n", SHORT_ROW, id="a row too short to hold its IID"),
    ],
)
def test_a_psam_not_read_gives_no_iids_and_says_why(text, why):
    assert parse_psam(text) == PsamRows(None, why)


def test_a_psam_whose_every_iid_is_recognised_names_them():
    read = PSAM_SAMPLES.read(parse_psam(PRIMED), "AnVIL_TEST")
    assert read.outcome == NAMED
    assert read.members == {Identifier("coriell", "HG01879"), Identifier("coriell", "NA19700")}
    samples = read.reference()
    assert samples is not None
    assert samples["named_by"] == [{"source_type": "content_read", "rule_id": code_rules.PSAM_SAMPLE_IDS.id}]


def test_a_psam_with_an_iid_no_rule_recognises_names_no_samples():
    """One unrecognised IID and the table names none: a list missing a sample would understate the fileset."""
    read = PSAM_SAMPLES.read(parse_psam(PRIMED + "Sample_7\t0\t0\t2\tAFR\tACB\n"), "AnVIL_TEST")
    assert read.outcome == UNRECOGNISED
    assert read.unrecognised == ("Sample_7",)
    assert read.reference() is None


def test_a_psam_not_read_is_unread_with_its_cause_and_one_with_no_row_names_none():
    unread = PSAM_SAMPLES.read(parse_psam("HG01879\t0\n"), "AnVIL_TEST")
    assert (unread.outcome, unread.unread) == (UNREAD, NO_HEADER)
    assert PSAM_SAMPLES.read(parse_psam("#IID\n"), "AnVIL_TEST").outcome == NO_SAMPLE


# --- pairing a fileset --------------------------------------------------------------


def file(file_id: str, path: str | None, dataset: str = "d1", title: str = "AnVIL_TEST", name: str = "") -> dict:
    record = {
        "file_id": file_id,
        "file_name": name or (path or "").rsplit("/", 1)[-1],
        "dataset_id": dataset,
        "dataset_title": title,
    }
    if path is not None:
        record["file_path"] = path
    return record


def test_a_psam_pairs_the_pgen_pvar_and_log_beside_it_under_its_stem():
    records = [
        file("psam", "hg38/hm3/AFR.19.psam"),
        file("pgen", "hg38/hm3/AFR.19.pgen"),
        file("pvar", "hg38/hm3/AFR.19.pvar"),
        file("log", "hg38/hm3/AFR.19.log"),
        # Another fileset's files, and the same stem in another folder: neither is this fileset's.
        file("other", "hg38/hm3/AFR.20.pgen"),
        file("elsewhere", "hg19/hm3/AFR.19.pgen"),
    ]
    result = filesets(records, KEY)
    assert result.entries == [{"sample_table": "psam", "members": ["pgen", "pvar", "log"]}]
    assert result.counts == {"AnVIL_TEST": {SAMPLE_TABLES: 1, MEMBERS: 3}}


def test_the_folder_is_required_where_edges_would_take_a_lone_name_anywhere():
    """`AFR.19.pgen` is the only file of that name in the dataset, but not in the `.psam`'s folder."""
    result = filesets([file("psam", "hg38/hm3/AFR.19.psam"), file("pgen", "hg19/hm3/AFR.19.pgen")], KEY)
    assert result.entries == [] and result.counts == {"AnVIL_TEST": {UNPAIRED: 1}}


def test_a_name_matches_up_to_case_and_only_within_the_dataset():
    records = [
        file("psam", "x/AFR.19.psam"),
        file("pgen", "x/afr.19.PGEN"),
        file("pvar", "x/AFR.19.pvar", dataset="d2"),
    ]
    assert filesets(records, KEY).entries == [{"sample_table": "psam", "members": ["pgen"]}]


def test_a_psam_with_no_path_pairs_nothing_and_is_counted():
    result = filesets([file("psam", None, name="AFR.19.psam"), file("pgen", "AFR.19.pgen")], KEY)
    assert result.entries == [] and result.counts == {"AnVIL_TEST": {NO_PATH: 1}}


def test_a_member_name_two_files_of_the_folder_carry_pairs_neither():
    records = [file("psam", "x/A.psam"), file("pgen1", "x/A.pgen"), file("pgen2", "x/a.pgen"), file("log", "x/A.log")]
    result = filesets(records, KEY)
    assert result.entries == [{"sample_table": "psam", "members": ["log"]}]
    assert result.counts == {"AnVIL_TEST": {SAMPLE_TABLES: 1, MEMBERS: 1, SEVERAL_CARRY: 1}}


def test_a_file_at_the_top_of_its_dataset_pairs_with_one_beside_it():
    assert filesets([file("psam", "A.psam"), file("pgen", "A.pgen")], KEY).entries == [
        {"sample_table": "psam", "members": ["pgen"]}
    ]


def test_entries_are_in_key_order():
    records = [file("b", "y/B.psam"), file("b-pgen", "y/B.pgen"), file("a", "x/A.psam"), file("a-pgen", "x/A.pgen")]
    assert [e["sample_table"] for e in filesets(records, KEY).entries] == ["a", "b"]


def test_a_member_whose_key_is_not_usable_is_refused():
    with pytest.raises(ValueError, match="pair a PLINK fileset"):
        filesets([file("psam", "x/A.psam"), {**file("pgen", "x/A.pgen"), "file_id": ""}], KEY)


def test_a_sample_table_named_as_a_parent_has_no_parent_kind():
    """A `.psam` holds no genotypes, so a step naming it would not call it `genotypes`, as it does a `.pgen`."""
    assert (edges.parent_kind_of("ACB.1.psam"), edges.parent_kind_of("ACB.1.pgen")) == (None, "genotypes")
