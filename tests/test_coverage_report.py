"""The coverage report's three buckets (#88).

``classified`` is every label that is neither ``not_classified`` nor ``conflict``, so
``not_applicable`` — a determined answer — counts there; ``conflict`` is counted on its
own and listed by extension and competing values. Before #88 a conflict resolved to
``not_classified`` and the report had no way to tell the two apart.
"""

import json

import generate_coverage_report as report

from meta_disco.models import CONFLICT, NOT_APPLICABLE, NOT_CLASSIFIED, build_field_entry
from meta_disco.rule_engine import CONFLICT_MARKER
from tests.run_fixtures import output_record, write_run

REF = "reference_assembly"


def _conflict_record(file_name: str, md5: str, competing: list[str]) -> dict:
    """An output row whose reference_assembly is in conflict, marker included, in the
    shape ``rule_engine._conflict_marker`` writes."""
    record = output_record(file_name, md5)
    marker = {
        "marker": CONFLICT_MARKER,
        "reason": f"Conflicting {REF}: {competing} — ambiguous",
        "status": CONFLICT,
        "competing_values": competing,
    }
    record["classifications"][REF] = build_field_entry(None, CONFLICT, evidence=[marker])
    return record


def _run(tmp_path):
    return write_run(
        tmp_path / "run",
        [
            output_record("a.bam", "1" * 32, reference_assembly="GRCh38"),
            output_record("b.bam", "2" * 32, reference_assembly="GRCh38"),
            output_record("c.fastq", "3" * 32, reference_assembly=NOT_APPLICABLE),
            output_record("d.txt", "4" * 32, reference_assembly=NOT_CLASSIFIED),
            _conflict_record("e.bed", "5" * 32, ["CHM13", "GRCh38"]),
            _conflict_record("f.bed", "6" * 32, ["CHM13", "GRCh38"]),
            _conflict_record("g.vcf.gz", "7" * 32, ["GRCh37", "GRCh38"]),
            # An index file re-emitting its parent's conflict: the status, no marker.
            output_record("e.bed.idx", "8" * 32, reference_assembly=CONFLICT),
        ],
    )


def test_load_records_reads_the_competing_values_off_the_marker(tmp_path):
    records = report.load_records(_run(tmp_path))
    by_name = {r["file_name"]: r for r in records}
    assert by_name["e.bed"][REF] == CONFLICT
    assert by_name["e.bed"][f"{REF}_competing"] == "CHM13 vs GRCh38"
    assert f"{REF}_competing" not in by_name["a.bam"]


def test_tally_counts_conflict_apart_from_both_neighbours(tmp_path):
    tally = report.Tally(report.load_records(_run(tmp_path)), REF)
    # not_applicable is a determined answer and stays in classified; conflict is not.
    assert (tally.classified, tally.nc, tally.conflict) == (3, 1, 4)


def test_conflict_breakdown_groups_by_extension_and_competing_values(tmp_path):
    rows = report.get_conflict_breakdown(report.load_records(_run(tmp_path)), REF)
    assert rows == [
        {"ext": ".bed", "competing": "CHM13 vs GRCh38", "count": 2},
        {"ext": ".vcf", "competing": "GRCh37 vs GRCh38", "count": 1},
        {"ext": ".idx", "competing": report.COMPETING_NOT_RECORDED, "count": 1},
    ]


def test_section_lists_the_conflict_row_and_table_only_where_there_is_one(tmp_path):
    records = report.load_records(_run(tmp_path))
    section, _ = report.build_section(records, REF, "Reference Assembly")
    assert "| **Conflict** | 4 |" in section
    assert "### What's in conflict?" in section
    assert "| .bed | CHM13 vs GRCh38 | 2 |" in section
    # Every dimension gets the row; only one with a conflict gets the table.
    modality, _ = report.build_section(records, "data_modality", "Data Modality")
    assert "| **Conflict** | 0 |" in modality
    assert "What's in conflict?" not in modality


def test_dashboard_payload_carries_the_conflict_count_and_breakdown(tmp_path):
    records = report.load_records(_run(tmp_path))
    out = tmp_path / "dash.html"
    report.generate_html_dashboard(records, "run", {}, out)
    # The template's `const DATA = COVERAGE_DATA_PLACEHOLDER;` line becomes the payload.
    line = next(ln for ln in out.read_text().splitlines() if "const DATA = " in ln)
    payload = json.loads(line.split("const DATA = ", 1)[1].rstrip(";").replace(r"<\/", "</"))
    ref = next(d for d in payload["dimensions"] if d["field"] == REF)
    assert (ref["classified"], ref["not_classified"], ref["conflict"]) == (3, 1, 4)
    assert ref["conflict_breakdown"][0] == {"ext": ".bed", "competing": "CHM13 vs GRCh38", "count": 2}
