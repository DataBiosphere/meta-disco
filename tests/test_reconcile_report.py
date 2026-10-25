"""The reconcile report (#395): markdown and dashboard rendered from ``reconcile_report.json`` alone."""

import json
import shutil
from pathlib import Path

import generate_reconcile_report as rr
import pytest

from meta_disco.models import CLASSIFICATION_FIELDS, SOURCE_PUBLISHED_VALUE, SOURCE_REPOSITORY_METADATA
from meta_disco.output_utils import RECONCILED_DIR
from meta_disco.reconcile import FILLED_GROUPS, REPORT_FILE, UNFILLED_CATEGORIES
from meta_disco.record_keys import HPRC_REPOSITORY
from meta_disco.summaries import md_code
from tests.run_fixtures import provenance, write_run
from tests.test_reconcile import DATASET, TABLE, drs, go, published, record, write_evidence
from tests.test_value_map import load


@pytest.fixture
def table(tmp_path: Path):
    return load(tmp_path, TABLE)


@pytest.fixture
def evidence(tmp_path: Path) -> Path:
    root = tmp_path / "evidence"
    root.mkdir()
    return root


def reconcile(tmp_path: Path, name: str, evidence: Path, table, records: list[dict]) -> Path:
    run_dir = tmp_path / "output" / name
    write_run(run_dir, records)
    go(run_dir, tmp_path, evidence, table)
    return run_dir


def render(tmp_path: Path, *argv: str) -> tuple[int, str, str]:
    md, html, tsv = tmp_path / "report.md", tmp_path / "dashboard.html", tmp_path / "sample-conflicts.tsv"
    code = rr.main([*argv, "--markdown", str(md), "--html", str(html), "--conflicts-tsv", str(tsv)])
    return code, md.read_text() if md.exists() else "", html.read_text() if html.exists() else ""


@pytest.fixture
def conflicted(tmp_path, evidence, table) -> Path:
    """A run with one source conflict, one submitter fill and one unreviewed published value beside inference."""
    write_evidence(evidence, [("reference_assembly", drs(1), "CHM13"), ("platform", drs(2), "PACBIO_SMRT")])
    published(evidence, [("reference_assembly", drs(3), '["GRCm39"]')])
    return reconcile(
        tmp_path,
        "20260923_000000",
        evidence,
        table,
        [record(1, reference_assembly="GRCh38"), record(2), record(3, reference_assembly="GRCh38")],
    )


def test_the_report_is_rendered_from_the_reconcile_report_alone(tmp_path, conflicted):
    # Nothing of the run but the report: no inference file, no reconciled record.
    report = conflicted / RECONCILED_DIR / REPORT_FILE
    kept = tmp_path / "kept.json"
    shutil.copy(report, kept)
    shutil.rmtree(conflicted)
    (conflicted / RECONCILED_DIR).mkdir(parents=True)
    shutil.copy(kept, report)

    code, md, html = render(tmp_path, "--run-dir", str(conflicted), "--no-previous")
    assert code == 0
    sha = json.loads(report.read_text())["value_map_sha256"]
    assert "`20260923_000000`" in md and sha in md
    # The headline names every category, published included though it filled nothing.
    assert "| dimension | published | published harmonized | submitter | submitter harmonized | inference |" in md
    assert "| platform | 0 | 0 | 0 | 1 | 0 |" in md
    # The conflicts by their competing values, and the corpus rate: 2 conflicts of 21 slots.
    assert f"inference: GRCh38; {SOURCE_REPOSITORY_METADATA}: CHM13" in md
    assert 'published_value (unreviewed): ["GRCm39"]' in md
    assert "**2 of 24 slots (8.333%)**" in md
    assert f"### `{DATASET}`" in md
    assert rr.PLACEHOLDER not in html and '"(every dataset)"' in html and f'"{DATASET}"' in html


def test_a_run_not_reconciled_is_refused_not_replaced_by_an_older_one(tmp_path, conflicted, capsys):
    later = tmp_path / "output" / "20260924_000000"
    later.mkdir()
    code, md, _ = render(tmp_path, "--run-dir", str(later))
    assert code == 1 and md == ""
    assert "make reconcile" in capsys.readouterr().err


def test_the_change_is_against_the_newest_earlier_reconciled_run(tmp_path, conflicted, evidence, table):
    # A later run where file 2's platform is inference's own and file 1 agrees with the source.
    later = reconcile(
        tmp_path,
        "20260924_000000",
        evidence,
        table,
        [record(1, reference_assembly="CHM13"), record(2, platform="ILLUMINA"), record(3, reference_assembly="GRCh38")],
    )
    assert rr.find_previous(later) == conflicted
    code, md, _ = render(tmp_path, "--run-dir", str(later))
    assert code == 0
    assert "Against `20260923_000000` (3 files; the same translation table)" in md
    change = {r["dimension"]: r for r in rr.change(rr.load_report(later), rr.load_report(conflicted))}
    ref = change["reference_assembly"]["counts"]
    assert (ref["conflict_sources"], ref["filled_by_submitter"]) == (-1, 1)
    # PACBIO_SMRT beside ILLUMINA is now a conflict, no longer a submitter fill.
    platform = change["platform"]["counts"]
    assert (platform["filled_by_submitter_harmonized"], platform["conflict_sources"]) == (-1, 1)


def test_a_slot_category_the_report_does_not_know_is_refused(tmp_path, conflicted):
    path = conflicted / RECONCILED_DIR / REPORT_FILE
    report = json.loads(path.read_text())
    report["slots"][DATASET]["platform"]["filled_by_curator"] = 1
    path.write_text(json.dumps(report))
    with pytest.raises(rr.ReportError, match="filled_by_curator"):
        rr.load_report(conflicted)


def test_a_conflict_kind_the_report_does_not_know_is_refused(conflicted):
    path = conflicted / RECONCILED_DIR / REPORT_FILE
    report = json.loads(path.read_text())
    report["conflicts"][DATASET]["reference_assembly"]["conflict_curator"] = []
    path.write_text(json.dumps(report))
    with pytest.raises(rr.ReportError, match="conflict_curator"):
        rr.load_report(conflicted)


def test_a_source_no_evidence_came_from_has_no_columns(conflicted):
    shown = set(rr.columns(rr.load_report(conflicted)))
    assert "filled_by_published" in shown and "filled_by_submitter_harmonized" in shown
    assert not any(key.startswith("filled_by_external") for key in shown)


def test_an_inherited_conflict_says_it_carries_no_values():
    assert rr.competing({"inference": []}) == "inference: (no values carried)"


def test_a_report_written_before_the_conflict_tally_is_refused_but_still_compared_against(conflicted):
    path = conflicted / RECONCILED_DIR / REPORT_FILE
    report = json.loads(path.read_text())
    del report["conflicts"]
    path.write_text(json.dumps(report))
    with pytest.raises(rr.ReportError, match="predates the conflict tally"):
        rr.load_report(conflicted)
    # As the previous run it is only compared against, and the change reads no conflicts.
    assert "conflicts" not in rr.load_report(conflicted, previous=True)


def reconcile_later(tmp_path: Path, earlier: Path) -> Path:
    """A second reconciled run beside ``earlier``: its report copied under a later name."""
    later = earlier.parent / "20260925_000000"
    (later / RECONCILED_DIR).mkdir(parents=True)
    shutil.copy(earlier / RECONCILED_DIR / REPORT_FILE, later / RECONCILED_DIR / REPORT_FILE)
    return later


def test_a_symlinked_run_is_not_its_own_previous_run(tmp_path, conflicted):
    latest = conflicted.parent / "latest"
    latest.symlink_to(conflicted.name)
    assert rr.find_previous(latest) is None

    # A symlink elsewhere still finds the run's own earlier siblings.
    elsewhere = tmp_path / "latest"
    elsewhere.symlink_to(later := reconcile_later(tmp_path, conflicted))
    assert rr.find_previous(elsewhere) == conflicted and later.name > conflicted.name


def test_a_dataset_titled_like_the_whole_run_does_not_replace_it(conflicted):
    """A second dataset whose title is the whole run's label stays one dataset beside the run."""
    report = rr.load_report(conflicted)
    for block in ("files", "slots", "inputs", "conflicts", "values"):
        report[block][rr.ALL] = report[block][DATASET]
    data = rr.dashboard_data(report, None, Path("report.json"))
    assert data["run"]["files"] == 6
    assert [(scope["name"], scope["files"]) for scope in data["datasets"]] == [(rr.ALL, 3), (DATASET, 3)]


def test_the_headline_closes_with_each_columns_total_and_its_share_of_the_slots(conflicted):
    data = rr.dashboard_data(rr.load_report(conflicted), None, Path("report.json"))
    whole = data["run"]
    counts = whole["totals"]["counts"]
    for category, total in counts.items():
        assert total == sum(r["counts"][category] for r in whole["headline"])
    assert sum(counts.values()) == whole["slots"]
    md = rr.render_markdown(data)
    shares = next(line for line in md.splitlines() if line.startswith("| **% of slots** |"))
    keys = [*(c["key"] for c in data["columns"])]
    expected = [counts[k] for k in keys] + [whole["totals"][rr.ADDED], whole["totals"][rr.FILLED_OVER]]
    assert shares.strip("| ").split(" | ")[1:] == [f"**{rr._of_slots(v, whole['slots'])}**" for v in expected]


def test_completeness_counts_each_filled_slot_once_and_nothing_else(conflicted):
    data = rr.dashboard_data(rr.load_report(conflicted), None, Path("report.json"))
    for scope in (data["run"], *data["datasets"]):
        c, counts = scope["completeness"], scope["totals"]["counts"]
        assert c["filled"] + sum(counts[k] for k in UNFILLED_CATEGORIES) == scope["slots"]
    md = rr.render_markdown(data)
    filled = data["run"]["completeness"]["filled"]
    assert f"| **filled** | **{filled:,}** | **{rr._of_slots(filled, data['run']['slots'])}** |" in md


def test_the_completeness_filled_count_is_the_values_tables_filled_summed_over_the_dimensions(conflicted):
    """Two counts of one thing, from the slot categories and from the per-value counts: they must agree."""
    data = rr.dashboard_data(rr.load_report(conflicted), None, Path("report.json"))
    filled = sum(m["total"]["filled"] * m["total"]["files"] for m in data["values"].values())
    assert round(filled) == data["run"]["completeness"]["filled"] > 0


def test_the_catalog_today_counts_its_own_dimensions_and_the_values_it_publishes(conflicted):
    """Its slots are the files times its published columns; a value no translation row reads still fills one."""
    data = rr.dashboard_data(rr.load_report(conflicted), None, Path("report.json"))
    whole = data["run"]
    assert whole["catalog_today"] == {
        "dimensions": ["data_modality", "reference_assembly"],
        "slots": whole["files"] * 2,
        "filled": 1,  # the one unreviewed published reference_assembly
    }
    md = rr.render_markdown(data)
    assert "|  | meta-disco (8 dimensions) | % | catalog today (2 dimensions) | % |" in md
    # What the catalog publishes is the original metadata: its count is in that row, and no other.
    c, slots, share = whole["completeness"], whole["slots"], rr._of_slots(1, whole["files"] * 2)
    original = f"| original (catalog's published values) | {c['published']:,} | {rr._of_slots(c['published'], slots)} |"
    assert f"{original} 1 | {share} |" in md
    assert f"| submitter tables | {c['submitter']:,} | {rr._of_slots(c['submitter'], slots)} | — | — |" in md
    assert "only the dimensions it has a column for (`data_modality`, `reference_assembly`)" in md


@pytest.mark.parametrize(
    "unread",
    [
        pytest.param({"repository": HPRC_REPOSITORY}, id="no published source"),
        pytest.param({"evidence": [], "evidence_excluded": True}, id="evidence excluded"),
        pytest.param("no published evidence read", id="published values never imported"),
    ],
)
def test_the_catalog_today_is_not_shown_where_it_is_unknown(conflicted, unread):
    """Where this run read none of the catalog's values, its count is unknown, not 0.0%."""
    report = rr.load_report(conflicted)
    if unread == "no published evidence read":
        unread = {"evidence": [e for e in report["evidence"] if e["source_type"] != SOURCE_PUBLISHED_VALUE]}
        assert unread["evidence"] != report["evidence"]
    data = rr.dashboard_data({**report, **unread}, None, Path("report.json"))
    assert data["run"]["catalog_today"] is None
    assert all(scope["catalog_today"] is None for scope in data["datasets"])
    assert "catalog today" not in rr.render_markdown(data).lower()


def test_a_source_no_evidence_came_from_has_no_completeness_row(conflicted):
    """As the headline leaves out such a source's columns, the completeness table leaves out its row."""
    report = rr.load_report(conflicted)
    unread = rr.unread_sources(report)
    assert unread  # the fixture reads no external evidence
    data = rr.dashboard_data(report, None, Path("report.json"))
    assert [g["key"] for g in data["filled_groups"]] == [g for g in FILLED_GROUPS if g not in unread]
    md = rr.render_markdown(data)
    assert all(f"| {rr.group_label(g)} |" not in md for g in unread)
    assert f"| {rr.group_label(rr.CATALOG_GROUP)} |" in md


def test_a_source_only_the_previous_run_read_has_no_completeness_row(conflicted):
    """The headline keeps its columns, for the change table; the completeness rows count this run alone."""
    report = rr.load_report(conflicted)
    (gone,) = [e for e in report["evidence"] if e["source_type"] == SOURCE_REPOSITORY_METADATA][:1]
    current = {**report, "evidence": [e for e in report["evidence"] if e["source_type"] != SOURCE_REPOSITORY_METADATA]}
    data = rr.dashboard_data(current, report, Path("report.json"))
    submitter = rr.SOURCE_GROUP[gone["source_type"]]
    assert submitter not in [g["key"] for g in data["filled_groups"]]
    assert rr.fill_category(submitter, False) in [c["key"] for c in data["columns"]]


def test_each_sources_row_adds_its_own_and_its_harmonized_column(conflicted):
    data = rr.dashboard_data(rr.load_report(conflicted), None, Path("report.json"))
    c, counts = data["run"]["completeness"], data["run"]["totals"]["counts"]
    assert c["submitter"] == counts["filled_by_submitter"] + counts["filled_by_submitter_harmonized"] > 0
    assert c["published"] == counts["filled_by_published"] + counts["filled_by_published_harmonized"]


def test_a_share_too_small_to_show_is_not_shown_as_zero():
    assert rr._of_slots(0, 100) == "0.0%" and rr._of_slots(5, 0) == "0.0%"
    assert rr._of_slots(1, 10_000) == "<0.1%" and rr._of_slots(1, 1_000) == "0.1%"
    assert rr._of_slots(1, 8) == "12.5%" and rr._of_slots(8, 8) == "100%"


def test_each_datasets_completeness_and_catalog_today_count_that_dataset_alone(conflicted):
    """A second dataset the catalog publishes nothing for: its own counts, and the run's are the two summed."""
    report = rr.load_report(conflicted)
    other = "OTHER"
    report["files"][other] = 4
    report["slots"][other] = {slot: {"not_classified": 4} for slot in CLASSIFICATION_FIELDS}
    report["values"][other] = {slot: {"not_classified": 4} for slot in CLASSIFICATION_FIELDS}
    data = rr.dashboard_data(report, None, Path("report.json"))
    scopes = {scope["name"]: scope for scope in data["datasets"]}
    dims = ["data_modality", "reference_assembly"]
    assert scopes[other]["catalog_today"] == {"dimensions": dims, "slots": 8, "filled": 0}
    assert scopes[DATASET]["catalog_today"] == {"dimensions": dims, "slots": 6, "filled": 1}
    assert data["run"]["catalog_today"] == {"dimensions": dims, "slots": 14, "filled": 1}
    assert scopes[other]["completeness"]["filled"] == 0
    assert data["run"]["completeness"] == scopes[DATASET]["completeness"]
    assert data["run"]["slots"] == scopes[DATASET]["slots"] + scopes[other]["slots"]


def test_catalog_text_is_a_code_span_in_the_markdown():
    """Pages renders the markdown through Jekyll: a value holding a link, an image or HTML must show literally."""
    row = {"dataset": "<b>D</b>", "dimension": "platform", "kind": "conflict_sources", "files": 1}
    value = "![x](https://example.invalid/t)"
    (line,) = rr._conflict_table([{**row, "inputs": {"published_value (unreviewed)": [value]}}], True)[2:]
    assert "| `<b>D</b>` |" in line and f"`published_value (unreviewed): {value}`" in line


def test_a_code_span_outlasts_the_backticks_in_its_value():
    assert md_code("a`b") == "``a`b``"
    assert md_code("`x`") == "`` `x` ``"
    assert md_code("one\ntwo") == "`one two`"


def test_no_catalog_text_can_close_the_dashboards_script_tag():
    html = rr.render_html(
        {"name": "</SCRIPT><img src=x>", "other": "<!--<script"},
        "<script>const D = PLACEHOLDER;</script>".replace("PLACEHOLDER", rr.PLACEHOLDER),
    )
    assert html.count("<") == 2  # the template's own two tags
    assert (
        json.loads(html.removeprefix("<script>const D = ").removesuffix(";</script>"))["name"] == "</SCRIPT><img src=x>"
    )


def test_the_join_lists_only_evidence_files_with_values_that_did_not_join(conflicted):
    report = rr.load_report(conflicted)
    md = rr.render_markdown(rr.dashboard_data(report, None, Path("report.json")))
    assert "**All 3 values in the 2 evidence files joined their file;** none unmatched or ambiguous." in md
    report["evidence"][0] = {**report["evidence"][0], "matched": 1, "unmatched": 1}
    md = rr.render_markdown(rr.dashboard_data(report, None, Path("report.json")))
    assert "**1 of 2 evidence files have values that did not join their file** (3 values in all):" in md
    assert "<summary>Evidence files read (2)</summary>" in md


# --- values by dataset (#545) ---------------------------------------------------------


def test_each_dimensions_values_are_shown_per_dataset(tmp_path, conflicted):
    code, md, html = render(tmp_path, "--run-dir", str(conflicted), "--no-previous")
    assert code == 0
    matrix = rr.values_matrix(rr.load_report(conflicted), "platform")
    # File 2's platform came from the submitter table; the other two have none.
    assert (matrix["values"], matrix["statuses"]) == (["PACBIO"], ["not_classified"])
    (row,) = matrix["rows"]
    assert (row["counts"], row["files"]) == ({"PACBIO": 1, "not_classified": 2}, 3)
    assert (round(row["has_value"], 3), round(row["filled"], 3)) == (0.333, 0.333)
    assert "## Values by dataset" in md and "### platform" in md
    assert "| dataset | `PACBIO` | `not_classified` | files | has a value | filled |" in md
    assert "Values by dataset" in html and '"values_change": null' in html


def test_filled_counts_not_applicable_and_has_a_value_does_not():
    report = {
        "files": {"D": 4},
        "values": {"D": {"reference_assembly": {"GRCh38": 1, "not_applicable": 2, "conflict": 1}}},
    }
    (row,) = rr.values_matrix(report, "reference_assembly")["rows"]
    assert (row["has_value"], row["filled"]) == (0.25, 0.75)
    matrix = rr.values_matrix(report, "reference_assembly")
    assert (matrix["values"], matrix["statuses"]) == (["GRCh38"], ["conflict", "not_applicable"])


def test_a_wide_slot_is_grouped_by_top_term_in_the_markdown_only(monkeypatch):
    counts = {"variants": 1, "variants.gvcf": 5, "reads": 4, "not_classified": 1}
    report = {"files": {"D": 11}, "values": {"D": {"data_type": counts}}}
    matrix = rr.values_matrix(report, "data_type")
    grouped, groups = rr._grouped("data_type", matrix)
    assert (grouped["values"], grouped["statuses"]) == (["variants", "reads"], ["not_classified"])
    assert grouped["rows"][0]["counts"] == {"variants": 6, "reads": 4, "not_classified": 1}
    assert groups == {"variants": ["variants.gvcf", "variants"]}
    # Grouping happens only past the column limit, and the matrix itself keeps every term.
    monkeypatch.setattr(rr, "MARKDOWN_VALUE_COLUMNS", 2)
    md = "\n".join(rr._values_section({slot: rr.values_matrix(report, slot) for slot in rr.CLASSIFICATION_FIELDS}))
    assert "`variants` = `variants.gvcf`, `variants`" in md
    assert matrix["values"] == ["variants.gvcf", "reads", "variants"]


def test_the_top_term_is_read_from_is_a_and_a_value_outside_the_vocabulary_is_its_own_group():
    """A term groups under the top of its `is_a` chain (#607); a value a stored run holds that
    today's vocabulary does not, dotted or not, stands alone rather than being guessed a parent."""
    counts = {"variants.gvcf": 1, "variants.retired": 2}
    matrix = rr.values_matrix({"files": {"D": 3}, "values": {"D": {"data_type": counts}}}, "data_type")
    grouped, groups = rr._grouped("data_type", matrix)
    assert grouped["values"] == ["variants.retired", "variants"]
    assert groups == {"variants": ["variants.gvcf"]}


def test_a_wide_slot_groups_an_is_a_family_whose_names_have_no_dot(monkeypatch):
    """Grouping follows `is_a` in every dimension (#607): `snRNA-seq` is a `RNA-seq` though no dot says so."""
    counts = {"RNA-seq": 1, "snRNA-seq": 2, "WGS": 4}
    report = {"files": {"D": 7}, "values": {"D": {"assay_type": counts}}}
    monkeypatch.setattr(rr, "MARKDOWN_VALUE_COLUMNS", 2)
    md = "\n".join(rr._values_section({slot: rr.values_matrix(report, slot) for slot in rr.CLASSIFICATION_FIELDS}))
    assert "`RNA-seq` = `snRNA-seq`, `RNA-seq`" in md
    assert "| dataset | `WGS` | `RNA-seq` | files | has a value | filled |" in md


def test_a_wide_slot_with_no_dotted_terms_is_not_grouped(monkeypatch):
    counts = {"Revio": 3, "PromethION": 2, "Illumina NovaSeq 6000": 1}
    report = {"files": {"D": 6}, "values": {"D": {"instrument_model": counts}}}
    monkeypatch.setattr(rr, "MARKDOWN_VALUE_COLUMNS", 2)
    md = "\n".join(rr._values_section({slot: rr.values_matrix(report, slot) for slot in rr.CLASSIFICATION_FIELDS}))
    assert "under its top term" not in md
    assert "| dataset | `Revio` | `PromethION` | `Illumina NovaSeq 6000` | files | has a value | filled |" in md


def test_a_report_without_per_value_counts_is_refused_unless_only_compared_against(conflicted):
    path = conflicted / RECONCILED_DIR / REPORT_FILE
    report = json.loads(path.read_text())
    del report["values"]
    path.write_text(json.dumps(report))
    with pytest.raises(rr.ReportError, match="predates the per-value counts"):
        rr.load_report(conflicted)
    assert "values" not in rr.load_report(conflicted, previous=True)


def test_the_cells_that_moved_since_the_previous_run_are_listed(tmp_path, conflicted, evidence, table):
    later = reconcile(
        tmp_path,
        "20260924_000000",
        evidence,
        table,
        [record(1, reference_assembly="CHM13"), record(2, platform="ILLUMINA"), record(3, reference_assembly="GRCh38")],
    )
    moved = rr.values_change(rr.load_report(later), rr.load_report(conflicted))
    assert moved is not None
    by_cell = {(m["dimension"], m["value"]): (m["before"], m["after"]) for m in moved}
    # File 1 now agrees with the source's CHM13; file 2's platform is now a conflict.
    assert by_cell[("reference_assembly", "CHM13")] == (0, 1)
    assert by_cell[("reference_assembly", "conflict")] == (2, 1)
    assert by_cell[("platform", "PACBIO")] == (1, 0)
    code, md, _ = render(tmp_path, "--run-dir", str(later))
    assert code == 0 and "### Values that moved, by dataset" in md


def test_a_previous_report_without_per_value_counts_is_compared_without_them(tmp_path, conflicted):
    later = reconcile_later(tmp_path, conflicted)
    path = conflicted / RECONCILED_DIR / REPORT_FILE
    report = json.loads(path.read_text())
    del report["values"]
    path.write_text(json.dumps(report))
    assert rr.values_change(rr.load_report(later), rr.load_report(conflicted, previous=True)) is None
    code, md, _ = render(tmp_path, "--run-dir", str(later), "--previous", str(conflicted))
    assert code == 0
    assert "predates the per-value counts (#545)" in md


def lineage_report(**lineage) -> dict:
    base = {"sources": {}, "steps": {}, "conflicts": {}, "misfits": []}
    return {"lineage": {**base, **lineage}}


def test_the_lineage_section_lists_each_sources_lines_who_named_each_step_conflicts_and_misfits():
    by = {"source_type": "repository_activity", "rule_id": "activity.indexing"}
    report = lineage_report(
        sources={"repository_activity": {DATASET: {"offered": 3, "resolved": 2, "untranslated": 1}}},
        steps={DATASET: {"filename_rule+repository_activity": 2}},
        conflicts={
            DATASET: {
                "edge": {
                    "files": 1,
                    "examples": [{"file_name": "a.tbi", "role": "indexed", "said": [{"said": "b.vcf.gz", "by": by}]}],
                }
            }
        },
        misfits=[
            {
                "dataset": DATASET,
                "activity": "AlignmentActivity",
                "problem": "required role missing",
                "detail": "reference",
                "files": 4,
            }
        ],
    )
    rows = rr.lineage_rows(report)
    assert rows is not None
    (source,) = rows["sources"]
    assert (source["offered"], source["resolved"], source["untranslated"], source["several_match"]) == (3, 2, 1, 0)
    md = "\n".join(rr._lineage_section(rows))
    assert f"| `repository_activity` | `{DATASET}` | 3 | 2 | 0 | 0 | 1 | 0 | 0 |" in md
    assert f"| `{DATASET}` | `filename_rule+repository_activity` | 2 |" in md
    assert "`a.tbi`: repository_activity (activity.indexing): `b.vcf.gz`" in md
    assert f"| `{DATASET}` | `AlignmentActivity` | required role missing | `reference` | 4 |" in md


def test_a_report_written_before_lineage_says_so_and_one_with_no_conflicts_says_none():
    assert rr.lineage_rows({}) is None
    assert "predates lineage at reconcile (#577)" in "\n".join(rr._lineage_section(None))
    rows = rr.lineage_rows(lineage_report(sources={"repository_activity": {DATASET: {"offered": 1, "resolved": 1}}}))
    md = "\n".join(rr._lineage_section(rows))
    assert "None: wherever two sources named a file's step, they agreed." in md


def test_the_content_steps_are_listed_per_producer_and_dataset_in_outcome_order_and_absent_ones_say_so():
    content = {
        "vcf": {DATASET: {"stepped": 3, "parent_ambiguous": 1}},
        "tar": {DATASET: {"stepped": 2, "no_vcf_header": 5}},
    }
    rows = rr.lineage_rows(lineage_report(content_steps=content))
    assert rows is not None
    md = "\n".join(rr._lineage_section(rows))
    assert "### Steps read from file content" in md
    # Columns: the VCF reader's ten outcomes, then the cohort readers' three of their own.
    assert f"| `tar` | `{DATASET}` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 0 | 0 |" in md
    assert f"| `vcf` | `{DATASET}` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |" in md
    # A report written before the reader (#609) has no step block at all.
    rows = rr.lineage_rows(lineage_report())
    assert rows is not None and rows["content_steps"] == []
    assert "None: no producer read a step in this run" in "\n".join(rr._lineage_section(rows))


def test_a_report_written_before_621_reads_its_header_steps_as_the_vcf_producers():
    rows = rr.lineage_rows(lineage_report(header_steps={DATASET: {"stepped": 3}}))
    assert rows is not None and [(r["producer"], r["stepped"]) for r in rows["content_steps"]] == [("vcf", 3)]


def test_the_inheritance_section_lists_what_each_role_passed_per_dataset_role_and_dimension():
    report = {
        "inheritance": {DATASET: {"platform": {"declared": 5, "mixed": 1, "list_unresolved": 3}}},
        "inheritance_by_role": {
            DATASET: {
                "shard": {"platform": {"declared": 5, "mixed": 1}},
                "input_list": {
                    "platform": {"list_unresolved": 3},
                    "data_modality": {"declared": 7, "parent_not_classified": 2},
                },
            }
        },
    }
    rows = rr.inheritance_rows(report)
    assert rows is not None
    # Roles in name order, dimensions in dimension order, every outcome a column, zero where none.
    assert [(r["role"], r["slot"]) for r in rows] == [
        ("input_list", "data_modality"),
        ("input_list", "platform"),
        ("shard", "platform"),
    ]
    md = "\n".join(rr._inheritance_section(rows))
    assert f"| `{DATASET}` | `input_list` | `data_modality` | 7 | 0 | 0 | 2 | 0 | 0 |" in md
    assert f"| `{DATASET}` | `input_list` | `platform` | 0 | 0 | 0 | 0 | 0 | 3 |" in md
    assert f"| `{DATASET}` | `shard` | `platform` | 5 | 1 | 0 | 0 | 0 | 0 |" in md


def test_a_report_written_before_the_per_role_counts_lists_every_role_together():
    report = {"inheritance": {DATASET: {"platform": {"declared": 5, "mixed": 1}}}}
    rows = rr.inheritance_rows(report)
    assert rows is not None and [(r["role"], r["slot"]) for r in rows] == [(None, "platform")]
    assert f"| `{DATASET}` | every role | `platform` | 5 | 1 | 0 | 0 | 0 | 0 |" in "\n".join(
        rr._inheritance_section(rows)
    )


def test_a_report_written_before_inheritance_says_so():
    assert rr.inheritance_rows({}) is None
    assert "predates inheritance at reconcile (#571)" in "\n".join(rr._inheritance_section(None))


def test_the_dashboard_carries_the_lineage_section(tmp_path, conflicted):
    code, md, html = render(tmp_path, "--run-dir", str(conflicted), "--no-previous")
    assert code == 0
    assert "## Lineage: how each file was made" in md and "No lineage was read." in md
    assert '"lineage": {"sources": []' in html or '"lineage":{"sources":[]' in html


def test_the_code_that_classified_and_reconciled_a_run_is_named_in_words():
    """`classified_by` and `reconciled_by` (#404), as the report and dashboard name them."""
    code = {"recorded": True, "version": "0.1.0", "commit": "a" * 40, "dirty": False}
    assert rr.describe_code(code) == "commit aaaaaaaaaaaa, version 0.1.0"
    assert rr.describe_code({**code, "dirty": True}) == "commit aaaaaaaaaaaa (dirty tree), version 0.1.0"
    assert rr.describe_code({**code, "dirty": None}) == "commit aaaaaaaaaaaa (tree state unknown), version 0.1.0"
    assert rr.describe_code({**code, "commit": None, "version": None}) == "commit unknown, version unknown"
    assert rr.describe_code({**code, "recorded": False}) == "not recorded"
    assert rr.describe_classified_by(None) == "not recorded"
    assert rr.describe_classified_by([{**code, "files": ["bam.json"]}]) == "commit aaaaaaaaaaaa, version 0.1.0"
    mixed = [{**code, "files": ["bam.json", "vcf.json"]}, {**code, "recorded": False, "files": ["old.json"]}]
    assert (
        rr.describe_classified_by(mixed)
        == "commit aaaaaaaaaaaa, version 0.1.0: bam.json, vcf.json; not recorded: old.json"
    )


def test_the_report_and_the_dashboard_name_the_code_that_classified_and_reconciled(tmp_path, table):
    run_dir = tmp_path / "output" / "20260923_000000"
    write_run(run_dir, [record(1)], metadata={"provenance": provenance()})
    go(run_dir, tmp_path, None, table)
    code, md, html = render(tmp_path, "--run-dir", str(run_dir), "--no-previous")
    assert code == 0
    reconciled_by = rr.describe_code(json.loads((run_dir / RECONCILED_DIR / REPORT_FILE).read_text())["reconciled_by"])
    assert "- **Classified by:** commit cccccccccccc, version 0.1.0" in md
    assert f"- **Reconciled by:** {reconciled_by}" in md
    assert '"classified_by": "commit cccccccccccc, version 0.1.0"' in html
    assert f'"reconciled_by": "{reconciled_by}"' in html


# --- samples (#357) ------------------------------------------------------------------


def test_the_samples_section_counts_how_each_dataset_settled(tmp_path, evidence, table):
    write_evidence(
        evidence,
        [("samples", drs(1), "HG00096"), ("samples", drs(2), "Sample")],
        table="participant",
        column="participant_id",
    )
    run_dir = reconcile(tmp_path, "20261012_000000", evidence, table, [record(1), record(2)])
    code, md, _ = render(tmp_path, "--run-dir", str(run_dir), "--no-previous")
    assert code == 0
    assert "## Samples: whose data each file holds" in md
    header = (
        "| dataset | header named | header unrecognised | header no_sample | header unread | agreed | header_only "
        "| table_only | activity_only | fileset_only | inherited |"
    )
    assert header in md
    assert f"| `{DATASET}` | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |" in md
    assert "None in this run." in md
    assert "`Sample` (1)" in md
    # Every table value no rule recognises, with its table, column and files (contract 5.2).
    assert f"| `{DATASET}` | `participant` | `participant_id` | `Sample` | 1 |" in md


def test_the_samples_section_lists_what_passed_and_each_parent_disagreement():
    """#668: per activity, what each role passing samples gave, and pairs disagreeing across another step."""
    block = {
        "settled": {"inherited": 2},
        "headers": {},
        "conflict_examples": [],
        "incomparable_examples": [],
        "table_unrecognised": [],
        "name_disagreements": 0,
        "name_disagreement_examples": [],
        "inheritance": {"IndexActivity": {"passed": 2, "parent_none": 1}},
        "parent_disagreements": {"AlignmentActivity": 1, "VariantCallActivity": 1},
        "parent_disagreement_examples": [
            {"file_name": "a.cram", "activity": "AlignmentActivity", "parent_file": "a.fastq.gz"},
            {"file_name": "a.vcf.gz", "activity": "VariantCallActivity", "parent_file": "a.cram"},
        ],
    }
    md = "\n".join(rr._samples_section(rr.samples_rows({"samples": {"by_dataset": {DATASET: block}}})))
    assert f"| `{DATASET}` | `IndexActivity` | 2 | 0 | 0 | 0 | 1 |" in md
    assert "| dataset | activity | pairs | examples |" in md
    assert f"| `{DATASET}` | `AlignmentActivity` | 1 | `a.cram` ← `a.fastq.gz` |" in md
    assert f"| `{DATASET}` | `VariantCallActivity` | 1 | `a.vcf.gz` ← `a.cram` |" in md


def test_a_report_written_before_the_parent_check_says_so_rather_than_none():
    block = {
        "settled": {},
        "headers": {},
        "conflict_examples": [],
        "incomparable_examples": [],
        "table_unrecognised": [],
        "name_disagreements": 0,
        "name_disagreement_examples": [],
    }
    md = "\n".join(rr._samples_section(rr.samples_rows({"samples": {"by_dataset": {DATASET: block}}})))
    assert "predates this check" in md and "None in this run." not in md


def test_a_report_written_before_samples_says_so():
    assert rr.samples_rows({}) is None
    assert "predates samples at reconcile" in "\n".join(rr._samples_section(None))


def test_the_most_frequent_unrecognised_strings_are_shown_whatever_the_report_order():
    """The report JSON is written with sorted keys; the section ranks by count."""
    assert rr._strings({"a": 1, "b": 1, "c": 9, "d": 1, "e": 1, "f": 1}, limit=2) == "`c` (9), `a` (1)"


def test_the_sample_maps_held_outside_anvil_are_listed_per_dataset(conflicted):
    report = rr.load_report(conflicted)
    md = rr.render_markdown(rr.dashboard_data(report, None, Path("report.json")))
    assert "None: no lineage line named one in this run." in md
    report["external_lists"] = {"ANVIL_T2T_CHRY": {"lists": 25, "rows": 78447, "samples_named": 25, "stepped": 25}}
    md = rr.render_markdown(rr.dashboard_data(report, None, Path("report.json")))
    row = next(line for line in md.splitlines() if line.startswith("| `ANVIL_T2T_CHRY` |"))
    assert row.strip("| ").split(" | ")[1:] == ["25", "25", "78,447", "0", "0", "25"]


def test_the_sample_maps_inference_rebuilt_are_listed_per_dataset(conflicted):
    report = rr.load_report(conflicted)
    md = rr.render_markdown(rr.dashboard_data(report, None, Path("report.json")))
    assert (
        "### Sample maps inference rebuilt" in md
        and "None: the run's tar producer rebuilt none, or the run predates #726." in md
    )
    report["rebuilt_lists"] = {"ANVIL_T2T_CHRY": {"lists": 52, "members": 14300}}
    data = rr.dashboard_data(report, None, Path("report.json"))
    assert data["rebuilt_list_columns"] == ["lists", "members"]
    row = next(line for line in rr.render_markdown(data).splitlines() if line.startswith("| `ANVIL_T2T_CHRY` | 52"))
    assert row.strip("| ").split(" | ")[1:] == ["52", "14,300"]
    html = rr.render_html(data, rr.TEMPLATE.read_text())
    assert "<h3>Sample maps inference rebuilt</h3>" in html and "DATA.rebuilt_lists" in html
    assert '"ANVIL_T2T_CHRY": {"lists": 52, "members": 14300}' in html


def test_the_dashboard_draws_the_sample_maps_held_outside_anvil(tmp_path, conflicted):
    report = rr.load_report(conflicted)
    report["external_lists"] = {"ANVIL_T2T_CHRY": {"lists": 25, "stepped": 25}}
    data = rr.dashboard_data(report, None, Path("report.json"))
    assert data["external_list_columns"] == list(rr.EXTERNAL_LIST_COLUMNS)
    html = rr.render_html(data, rr.TEMPLATE.read_text())
    assert "<h3>Sample maps held outside AnVIL</h3>" in html and "DATA.external_lists" in html
    assert '"ANVIL_T2T_CHRY": {"lists": 25, "stepped": 25}' in html
