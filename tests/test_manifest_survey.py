"""The manifest survey (issue #384): absence, the entity census, the two reach
traversals that disagree, the readiness bands, and the contradictions it records —
against synthetic manifests small enough to reason about, plus the script's
refusal to survey an incomplete set."""

import json
import re
import sys
from pathlib import Path

import pytest

from meta_disco import manifest_survey as ms
from meta_disco.azul_manifest import (
    FORMAT_COMPACT,
    FORMAT_VERBATIM,
    iter_verbatim_entities,
    manifest_dir,
    manifest_path,
    save_sidecar,
)

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import generate_manifest_survey as cli

CATALOG = "anvil15"

COMPACT_COLUMNS = [
    "datasets.consent_group",
    "datasets.data_use_permission",
    "datasets.registered_identifier",
    "donors.donor_id",
    "donors.phenotypic_sex",
    "biosamples.biosample_id",
    "biosamples.anatomical_site",
    "biosamples.biosample_type",
    "activities.activity_id",
    "activities.assay_type",
    "files.file_id",
    "files.data_modality",
]


def compact_path(root: Path, title: str = "D") -> Path:
    """One dataset's compact manifest, located the way the survey locates it.

    Through ``azul_manifest`` rather than by re-spelling ``manifest/<catalog>/``:
    the layout reorg in #268/#269 moves these directories, and a test that spells
    them itself is the thing that breaks when it lands.
    """
    return manifest_path(root, CATALOG, title, FORMAT_COMPACT)


def verbatim_path(root: Path, title: str = "D") -> Path:
    return manifest_path(root, CATALOG, title, FORMAT_VERBATIM)


def write_manifests(root: Path, title: str, compact: list[dict], verbatim: list[tuple[str, dict]]) -> None:
    """Put one dataset's two manifests on disk in the layout the survey reads."""
    manifest_dir(root, CATALOG).mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(COMPACT_COLUMNS)]
    lines += ["\t".join(str(row.get(column, "")) for column in COMPACT_COLUMNS) for row in compact]
    compact_path(root, title).write_text("\n".join(lines) + "\n")
    verbatim_path(root, title).write_text(
        "".join(json.dumps({"type": entity_type, "value": value}) + "\n" for entity_type, value in verbatim)
    )


def write_sidecar(root: Path, counts: dict[str, int]) -> None:
    save_sidecar(root, CATALOG, {"catalog": CATALOG, "datasets": {t: {"file_count": n} for t, n in counts.items()}})


def anvil_file(file_id: str, name: str = "", drs: str | None = None) -> tuple[str, dict]:
    value = {"file_id": file_id, "file_name": name or f"{file_id}.bam"}
    if drs is not None:
        value["drs_uri"] = f"drs://drs.anv0:v2_{drs}"
    return "anvil_file", value


def activity(used: list[str], generated: list[str], biosamples: list[str] | None = None) -> tuple[str, dict]:
    return "anvil_activity", {
        "activity_id": f"act-{'-'.join(generated) or 'none'}",
        "used_file_id": used,
        "generated_file_id": generated,
        "used_biosample_id": biosamples or [],
    }


UUID_A = "aaaaaaaa-1111-2222-3333-444444444444"
UUID_B = "bbbbbbbb-1111-2222-3333-444444444444"


# --- absence ------------------------------------------------------------------


@pytest.mark.parametrize("cell", ["", "  ", "null", "NULL", "NA", "n/a", "None", "[]", "{}"])
def test_absent_spellings_are_absent(cell):
    assert ms.cell_absent(cell)


@pytest.mark.parametrize("cell", ["0", "false", "NRES", "GRCh38", "nan"])
def test_values_are_not_absent(cell):
    assert not ms.cell_absent(cell)


def test_zero_and_false_are_values_not_gaps():
    # A coverage of 0.0 or a has_replicates of false is data the submitter
    # recorded; only nothing is nothing.
    assert ms._is_filled(0)
    assert ms._is_filled(False)
    assert not ms._is_filled(None)
    assert not ms._is_filled([])
    assert not ms._is_filled("  ")


def test_compact_fill_counts_and_spelling_census(tmp_path):
    write_manifests(
        tmp_path,
        "D",
        [
            {"donors.donor_id": "d1", "files.file_id": "f1", "datasets.consent_group": "NRES"},
            {"donors.donor_id": "NA", "files.file_id": "f2", "datasets.consent_group": "NRES"},
            {"donors.donor_id": "", "files.file_id": "f3", "datasets.consent_group": "NRES"},
        ],
        [],
    )
    rows, columns, spellings = ms.survey_compact(compact_path(tmp_path))
    assert rows == 3
    by_name = {c.column: c for c in columns}
    assert by_name["donors.donor_id"].filled == 1
    assert by_name["files.file_id"].rate == 1.0
    # Both the empty cell and the literal NA are counted, under their own spellings.
    assert spellings["na"] == 1
    assert spellings["(empty)"] >= 1


def test_join_counts_come_from_the_column_coverage(tmp_path):
    # The three JOIN_* columns are counted once, with every other column; nothing
    # keeps a second tally of them.
    write_manifests(
        tmp_path,
        "D",
        [
            {"donors.donor_id": "dn1", "biosamples.biosample_id": "bs1", "activities.activity_id": "ac1"},
            {"donors.donor_id": "", "biosamples.biosample_id": "", "activities.activity_id": ""},
        ],
        [anvil_file("f1")],
    )
    write_sidecar(tmp_path, {"D": 1})
    dataset = ms.run_survey(tmp_path, CATALOG).datasets[0]
    assert dataset.filled(ms.JOIN_DONOR) == 1
    assert dataset.filled("donors.donor_id") == 1
    assert dataset.filled("no.such.column") == 0
    assert dataset.join_uniform


def test_join_uniform_is_false_when_a_column_lags(tmp_path):
    write_manifests(
        tmp_path,
        "D",
        [
            {"donors.donor_id": "dn1", "biosamples.biosample_id": "bs1", "activities.activity_id": "ac1"},
            {"donors.donor_id": "dn2", "biosamples.biosample_id": "bs2"},
        ],
        [anvil_file("f1")],
    )
    write_sidecar(tmp_path, {"D": 1})
    dataset = ms.run_survey(tmp_path, CATALOG).datasets[0]
    assert not dataset.join_uniform
    assert ms.join_uniform([dataset]) == []


# --- the entity census --------------------------------------------------------


def test_census_separates_submitter_tables_from_harmonized(tmp_path):
    write_manifests(
        tmp_path,
        "D",
        [{"files.file_id": "f1"}],
        [
            anvil_file("f1"),
            ("hifi", {"hifi_id": "x", "instrument_model": "Revio", "coverage": None}),
            ("hifi", {"hifi_id": "y", "instrument_model": "", "coverage": 30.0}),
        ],
    )
    tables, _reach, _files = ms.survey_verbatim(verbatim_path(tmp_path))
    by_name = {t.name: t for t in tables}
    assert by_name["anvil_file"].is_submitter is False
    hifi = by_name["hifi"]
    assert hifi.is_submitter and hifi.rows == 2
    assert hifi.fields["hifi_id"] == 2
    assert hifi.fields["instrument_model"] == 1  # the empty string is not a value
    assert hifi.fields["coverage"] == 1  # 30.0 counts, None does not


def test_table_name_encodes_dimensions():
    assert ms._table_encodes("chains_to_chm13_mc") == [
        ("data_type", "chain"),
        ("reference_assembly", "CHM13"),
    ]
    assert ("platform", "Oxford Nanopore") in ms._table_encodes("ont_methylation")
    assert ms._table_encodes("participant") == []
    # An ambiguous name keeps both references rather than picking one.
    encoded = ms._table_encodes("chm13_vs_grch38")
    assert ("reference_assembly", "CHM13") in encoded
    assert ("reference_assembly", "GRCh38") in encoded


def test_dimension_fields_need_to_be_populated(tmp_path):
    write_manifests(
        tmp_path,
        "D",
        [{"files.file_id": "f1"}],
        [
            anvil_file("f1"),
            ("submitted", {"reference_assembly": "GRCh38", "platform": None, "assembly_date": "2024-09"}),
        ],
    )
    tables, _reach, _files = ms.survey_verbatim(verbatim_path(tmp_path))
    table = next(t for t in tables if t.name == "submitted")
    # reference_assembly is filled and counts; platform is present but empty and
    # does not; assembly_date is not a dimension field despite the prefix.
    assert table.dimension_fields == [("reference_assembly", "reference_assembly")]
    assert table.carries_dimension


# --- file identity ------------------------------------------------------------


def test_file_keys_index_drs_uuid_distinct_from_file_id():
    keys = ms.FileKeys()
    keys.add({"file_id": "azul-1", "file_name": "a.bam", "drs_uri": f"drs://drs.anv0:v2_{UUID_A}"})
    resolved = keys.resolved()
    # ENCORE's shape: the submitter names the DRS object, not Azul's file id.
    assert resolved[UUID_A] == "azul-1"
    assert resolved["azul-1"] == "azul-1"
    assert resolved["a.bam"] == "azul-1"


def test_file_keys_drop_a_name_two_files_share():
    keys = ms.FileKeys()
    keys.add({"file_id": "one", "file_name": "same.bam"})
    keys.add({"file_id": "two", "file_name": "same.bam"})
    keys.add({"file_id": "three", "file_name": "unique.bam"})
    resolved = keys.resolved()
    assert "same.bam" not in resolved
    assert resolved["unique.bam"] == "three"


def test_submitter_table_names_files_through_a_drs_uri(tmp_path):
    write_manifests(
        tmp_path,
        "D",
        [{"files.file_id": "azul-1"}],
        [
            anvil_file("azul-1", "a.bam", drs=UUID_A),
            anvil_file("azul-2", "b.bam", drs=UUID_B),
            ("hifi", {"hifi_id": "s1", "path": f"drs://drs.anv0:v2_{UUID_A}"}),
            # A uuid that is not one of this dataset's files must not count.
            ("hifi", {"hifi_id": "s2", "path": "drs://drs.anv0:v2_cccccccc-1111-2222-3333-444444444444"}),
        ],
    )
    tables, _reach, dimension_files = ms.survey_verbatim(verbatim_path(tmp_path))
    assert next(t for t in tables if t.name == "hifi").files_named == 1
    assert dimension_files == 1


def test_dimension_files_are_a_union_not_a_sum(tmp_path):
    write_manifests(
        tmp_path,
        "D",
        [{"files.file_id": "f1"}],
        [
            anvil_file("f1", "a.bam"),
            ("hifi", {"hifi_id": "s", "path": "f1"}),
            ("assembly", {"assembly_id": "s", "assembly": "f1"}),
        ],
    )
    _tables, _reach, dimension_files = ms.survey_verbatim(verbatim_path(tmp_path))
    # Both tables name the same one file; summing them would say two.
    assert dimension_files == 1


# --- reach --------------------------------------------------------------------


def test_single_hop_and_transitive_reach_disagree_on_a_chain(tmp_path):
    # biosample -> fastq (generated by an activity that names it)
    #           -> bam   (generated by an activity that used the fastq only)
    # Single hop reaches the fastq; transitive closure reaches both. This is the
    # 1000G shape in miniature.
    write_manifests(
        tmp_path,
        "D",
        [{"files.file_id": "fastq"}, {"files.file_id": "bam"}],
        [
            anvil_file("fastq"),
            anvil_file("bam"),
            ("anvil_biosample", {"biosample_id": "bs1", "donor_id": ["dn1"]}),
            activity(used=[], generated=["fastq"], biosamples=["bs1"]),
            activity(used=["fastq"], generated=["bam"]),
        ],
    )
    _tables, reach, _files = ms.survey_verbatim(verbatim_path(tmp_path))
    assert reach.files == 2
    assert reach.single_hop_donor == 1
    assert reach.transitive_donor == 2


def test_a_biosample_without_a_donor_reaches_a_biosample_only(tmp_path):
    write_manifests(
        tmp_path,
        "D",
        [{"files.file_id": "f1"}],
        [
            anvil_file("f1"),
            ("anvil_biosample", {"biosample_id": "bs1", "donor_id": []}),
            activity(used=[], generated=["f1"], biosamples=["bs1"]),
        ],
    )
    _tables, reach, _files = ms.survey_verbatim(verbatim_path(tmp_path))
    assert reach.single_hop_biosample == 1
    assert reach.single_hop_donor == 0
    assert reach.transitive_biosample == 1
    assert reach.transitive_donor == 0


def test_a_file_no_activity_mentions_reaches_nothing(tmp_path):
    write_manifests(
        tmp_path,
        "D",
        [{"files.file_id": "f1"}],
        [anvil_file("f1"), ("anvil_biosample", {"biosample_id": "bs1", "donor_id": ["dn1"]})],
    )
    _tables, reach, _files = ms.survey_verbatim(verbatim_path(tmp_path))
    assert reach.transitive_donor == 0
    assert reach.single_hop_donor == 0


def test_components_merge_when_a_later_activity_joins_them(tmp_path):
    # The activity naming the biosample is seen first, and only the last activity
    # connects "late" to it. A mark applied before that union must still count.
    write_manifests(
        tmp_path,
        "D",
        [{"files.file_id": "early"}, {"files.file_id": "late"}],
        [
            anvil_file("early"),
            anvil_file("late"),
            ("anvil_biosample", {"biosample_id": "bs1", "donor_id": ["dn1"]}),
            activity(used=[], generated=["early"], biosamples=["bs1"]),
            activity(used=["early"], generated=["late"]),
        ],
    )
    _tables, reach, _files = ms.survey_verbatim(verbatim_path(tmp_path))
    assert reach.transitive_donor == 2


# --- readiness ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("rate", "verdict"),
    [(1.0, "yes"), (ms.READY_HIGH, "yes"), (ms.READY_HIGH - 0.01, "partial"), (ms.READY_LOW, "partial"), (0.0, "no")],
)
def test_verdict_bands(rate, verdict):
    assert ms._verdict(rate) == verdict


def test_readiness_reports_the_number_behind_each_verdict(tmp_path):
    survey = surveyed(tmp_path)
    verdicts = ms.readiness(survey.datasets[0])
    assert verdicts["governance"][0] == "yes"
    assert "consent/DUO 100%" in verdicts["governance"][1]
    assert verdicts["edges"][0] == "yes"
    # The denominator is named, because the dimensions verdict uses a different one.
    assert "2 of 2 compact rows" in verdicts["edges"][1]
    assert "verbatim files" in verdicts["dimensions"][1]


# --- end to end ---------------------------------------------------------------


def surveyed(root: Path) -> ms.Survey:
    """A one-dataset survey whose every dimension is exercised by the assertions above."""
    write_sidecar(root, {"D": 2})
    write_manifests(
        root,
        "D",
        [
            {
                "datasets.consent_group": "NRES",
                "datasets.data_use_permission": "NRES",
                "donors.donor_id": "dn1",
                "donors.phenotypic_sex": "XX",
                "biosamples.biosample_id": "bs1",
                "files.file_id": "fastq",
            },
            {
                "datasets.consent_group": "NRES",
                "datasets.data_use_permission": "NRES",
                "donors.donor_id": "dn1",
                "donors.phenotypic_sex": "XX",
                "biosamples.biosample_id": "bs1",
                "files.file_id": "bam",
            },
        ],
        [
            anvil_file("fastq"),
            anvil_file("bam"),
            ("anvil_biosample", {"biosample_id": "bs1", "donor_id": ["dn1"]}),
            activity(used=[], generated=["fastq"], biosamples=["bs1"]),
            activity(used=["fastq"], generated=["bam"]),
            ("hifi", {"hifi_id": "s", "path": "fastq"}),
        ],
    )
    return ms.run_survey(root, CATALOG)


def test_run_survey_totals_against_the_sidecar(tmp_path):
    survey = surveyed(tmp_path)
    assert survey.measured_total == 2
    assert survey.snapshot_total == 2
    assert survey.datasets[0].compact_rows == 2


def test_contradiction_records_the_traversal_not_the_manifest(tmp_path):
    found = ms.contradictions(surveyed(tmp_path))
    traversal = [c for c in found if "#337" in c[0]]
    assert len(traversal) == 1
    assert "Single hop reaches 1 files" in traversal[0][2]
    assert "transitive closure over the same activities reaches 2" in traversal[0][2]


def test_contradiction_records_the_brief_where_a_field_is_populated(tmp_path):
    found = ms.contradictions(surveyed(tmp_path))
    brief = [c for c in found if "comparability-gap" in c[0]]
    assert len(brief) == 1
    assert "donor sex 100% in D" in brief[0][2]


def test_contradiction_records_the_join_arriving_whole(tmp_path):
    # #384's body reports HPRC_R2 at 91% donor/biosample but 23% activity. If the
    # three columns are filled together, that figure came from somewhere else.
    write_sidecar(tmp_path, {"AnVIL_HPRC_R2": 2})
    write_manifests(
        tmp_path,
        "AnVIL_HPRC_R2",
        [
            {"donors.donor_id": "dn1", "biosamples.biosample_id": "bs1", "activities.activity_id": "ac1"},
            {"files.file_id": "f2"},
        ],
        [anvil_file("f1"), anvil_file("f2")],
    )
    found = ms.contradictions(ms.run_survey(tmp_path, CATALOG))
    join = [c for c in found if "compact join" in c[1]]
    assert len(join) == 1
    assert "the same share as donor and biosample" in join[0][2]


def test_no_join_contradiction_when_the_columns_do_come_apart(tmp_path):
    write_sidecar(tmp_path, {"AnVIL_HPRC_R2": 2})
    write_manifests(
        tmp_path,
        "AnVIL_HPRC_R2",
        [
            {"donors.donor_id": "dn1", "biosamples.biosample_id": "bs1", "activities.activity_id": "ac1"},
            {"donors.donor_id": "dn2", "biosamples.biosample_id": "bs2"},
        ],
        [anvil_file("f1"), anvil_file("f2")],
    )
    found = ms.contradictions(ms.run_survey(tmp_path, CATALOG))
    assert [c for c in found if "compact join" in c[1]] == []


def test_no_contradiction_when_nothing_disagrees(tmp_path):
    write_sidecar(tmp_path, {"D": 1})
    write_manifests(tmp_path, "D", [{"files.file_id": "f1"}], [anvil_file("f1")])
    assert ms.contradictions(ms.run_survey(tmp_path, CATALOG)) == []


def test_report_renders_and_escapes_a_pipe_in_a_title(tmp_path):
    write_sidecar(tmp_path, {"a|b": 1})
    write_manifests(tmp_path, "a|b", [{"files.file_id": "f1"}], [anvil_file("f1")])
    report = ms.render_report(ms.run_survey(tmp_path, CATALOG))
    assert "a\\|b" in report
    # An unescaped pipe would close its cell, leaving the row a column short.
    lines = report.splitlines()
    header = next(i for i, line in enumerate(lines) if line.startswith("| key |"))
    title_row = next(line for line in lines[header:] if "a\\|b" in line)
    cells = lambda row: len(re.split(r"(?<!\\)\|", row))  # noqa: E731 — an escaped pipe is not a cell break
    assert cells(title_row) == cells(lines[header])


def test_survey_data_carries_the_unrounded_numbers(tmp_path):
    data = ms.survey_data(surveyed(tmp_path))
    dataset = data["datasets"]["D"]
    assert dataset["reach"]["single_hop_donor"] == 1
    assert dataset["reach"]["transitive_donor"] == 2
    assert dataset["compact_columns"]["donors.donor_id"]["rate"] == 1.0
    assert dataset["readiness"]["edges"]["verdict"] == "yes"


# --- the script ---------------------------------------------------------------


def test_script_writes_both_outputs(tmp_path, monkeypatch, capsys):
    surveyed(tmp_path)
    report, sidecar = tmp_path / "out.md", tmp_path / "out.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_manifest_survey.py", "--data-dir", str(tmp_path), "--output", str(report), "--json", str(sidecar)],
    )
    assert cli.main() == 0
    assert "# What the AnVIL manifests carry" in report.read_text()
    assert json.loads(sidecar.read_text())["catalog"] == CATALOG


def test_script_refuses_an_incomplete_set_and_names_what_is_missing(tmp_path, monkeypatch, capsys):
    surveyed(tmp_path)
    (verbatim_path(tmp_path)).unlink()
    monkeypatch.setattr(sys, "argv", ["generate_manifest_survey.py", "--data-dir", str(tmp_path)])
    assert cli.main() == 1
    assert "D.verbatim.jsonl" in capsys.readouterr().err


def test_script_refuses_an_empty_sidecar(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["generate_manifest_survey.py", "--data-dir", str(tmp_path)])
    assert cli.main() == 1
    assert "no manifests recorded" in capsys.readouterr().err


# --- the reader this leans on -------------------------------------------------


def test_verbatim_reader_raises_on_a_line_it_cannot_use(tmp_path):
    path = tmp_path / "broken.jsonl"
    path.write_text('{"type": "anvil_file", "value": {"file_id": "f1"}}\nnot json\n')
    with pytest.raises(ValueError, match="line 2"):
        list(iter_verbatim_entities(path))


def test_verbatim_reader_skips_blank_lines(tmp_path):
    path = tmp_path / "padded.jsonl"
    path.write_text('\n{"type": "anvil_file", "value": {"file_id": "f1"}}\n\n')
    assert [t for t, _ in iter_verbatim_entities(path)] == ["anvil_file"]
