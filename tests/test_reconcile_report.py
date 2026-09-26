"""The reconcile report (#395): markdown and dashboard rendered from ``reconcile_report.json`` alone."""

import json
import shutil
from pathlib import Path

import generate_reconcile_report as rr
import pytest

from meta_disco.models import SOURCE_REPOSITORY_METADATA
from meta_disco.output_utils import RECONCILED_DIR
from meta_disco.reconcile import REPORT_FILE
from meta_disco.summaries import md_code
from tests.run_fixtures import write_run
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
    md, html = tmp_path / "report.md", tmp_path / "dashboard.html"
    code = rr.main([*argv, "--markdown", str(md), "--html", str(html)])
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
    # The conflicts by their competing values, and the corpus rate: 2 conflicts of 18 slots.
    assert f"inference: GRCh38; {SOURCE_REPOSITORY_METADATA}: CHM13" in md
    assert 'published_value (unreviewed): ["GRCm39"]' in md
    assert "**2 of 18 slots (11.111%)**" in md
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
    for block in ("files", "slots", "inputs", "conflicts"):
        report[block][rr.ALL] = report[block][DATASET]
    data = rr.dashboard_data(report, None, Path("report.json"))
    assert data["run"]["files"] == 6
    assert [(scope["name"], scope["files"]) for scope in data["datasets"]] == [(rr.ALL, 3), (DATASET, 3)]


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
    assert matrix["columns"] == ["PACBIO", "not_classified"]
    (row,) = matrix["rows"]
    assert (row["counts"], row["files"]) == ({"PACBIO": 1, "not_classified": 2}, 3)
    assert (round(row["has_value"], 3), round(row["determined"], 3)) == (0.333, 0.333)
    assert "## Values by dataset" in md and "### platform" in md
    assert "| dataset | PACBIO | not_classified | files | has a value | determined |" in md
    assert "Values by dataset" in html and '"values_change": null' in html


def test_determined_counts_not_applicable_and_has_a_value_does_not():
    report = {
        "files": {"D": 4},
        "values": {"D": {"reference_assembly": {"GRCh38": 1, "not_applicable": 2, "conflict": 1}}},
    }
    (row,) = rr.values_matrix(report, "reference_assembly")["rows"]
    assert (row["has_value"], row["determined"]) == (0.25, 0.75)
    assert rr.values_matrix(report, "reference_assembly")["columns"] == ["GRCh38", "conflict", "not_applicable"]


def test_a_wide_slot_is_grouped_by_top_level_term_in_the_markdown_only(monkeypatch):
    counts = {"variants": 1, "variants.germline": 2, "reads": 4, "not_classified": 1}
    report = {"files": {"D": 8}, "values": {"D": {"data_type": counts}}}
    matrix = rr.values_matrix(report, "data_type")
    grouped, groups = rr._grouped(matrix)
    assert grouped["columns"] == ["reads", "variants", "not_classified"]
    assert grouped["rows"][0]["counts"] == {"reads": 4, "variants": 3, "not_classified": 1}
    assert groups == {"variants": ["variants.germline", "variants"]}
    # Grouping happens only past the column limit, and the matrix itself keeps every term.
    monkeypatch.setattr(rr, "MARKDOWN_VALUE_COLUMNS", 2)
    md = "\n".join(rr._values_section({slot: rr.values_matrix(report, slot) for slot in rr.CLASSIFICATION_FIELDS}))
    assert "`variants` = `variants.germline`, `variants`" in md
    assert matrix["columns"] == ["reads", "variants.germline", "variants", "not_classified"]


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
