"""The coverage report's three buckets (#88): the rule is stated on
``generate_coverage_report.Tally``, which these tests hold to it. Before #88 a
conflict resolved to ``not_classified`` and the report had no way to tell the two apart.
"""

import json

import generate_coverage_report as report
import pytest

from meta_disco.models import CONFLICT, NOT_APPLICABLE, NOT_CLASSIFIED, build_field_entry
from meta_disco.rule_engine import conflict_marker
from tests.run_fixtures import output_record, write_run

REF = "reference_assembly"


def _conflict_record(file_name: str, md5: str, competing: list[str]) -> dict:
    """An output row whose reference_assembly is in conflict, with the marker the rule
    engine writes for one."""
    record = output_record(file_name, md5)
    record["classifications"][REF] = build_field_entry(None, CONFLICT, evidence=[conflict_marker(REF, competing)])
    return record


@pytest.fixture
def records(tmp_path) -> list[dict]:
    run = write_run(
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
    return report.load_records(run)


def test_load_records_reads_the_competing_values_off_the_marker(records):
    by_name = {r["file_name"]: r for r in records}
    assert by_name["e.bed"][REF] == CONFLICT
    assert by_name["e.bed"][f"{REF}_competing"] == "CHM13 vs GRCh38"
    assert f"{REF}_competing" not in by_name["a.bam"]
    assert f"{REF}_competing" not in by_name["e.bed.idx"]


def test_tally_counts_conflict_apart_from_both_neighbours(records):
    tally = report.Tally(records, REF)
    # not_applicable is a determined answer and stays in classified; conflict is not.
    assert (tally.classified, tally.nc, tally.conflict) == (3, 1, 4)


def test_conflict_rows_group_by_extension_and_competing_values(records):
    assert report.Tally(records, REF).conflict_rows() == [
        {"ext": ".bed", "competing": "CHM13 vs GRCh38", "count": 2},
        {"ext": ".vcf", "competing": "GRCh37 vs GRCh38", "count": 1},
        {"ext": ".idx", "competing": report.COMPETING_NOT_RECORDED, "count": 1},
    ]


def test_section_lists_the_conflict_row_and_table_only_where_there_is_one(records):
    total = len(records)
    section = report.build_section(report.Tally(records, REF), total, "Reference Assembly")
    assert "| **Conflict** | 4 |" in section
    assert "### What's in conflict?" in section
    assert "| .bed | CHM13 vs GRCh38 | 2 |" in section
    # Every dimension gets the row; only one with a conflict gets the table.
    modality = report.build_section(report.Tally(records, "data_modality"), total, "Data Modality")
    assert "| **Conflict** | 0 |" in modality
    assert "What's in conflict?" not in modality


def test_dashboard_payload_carries_the_conflict_count_and_breakdown(records, tmp_path):
    tallies = [(field, label, notes, report.Tally(records, field)) for field, label, notes in report.DIMENSIONS]
    out = tmp_path / "dash.html"
    report.generate_html_dashboard(tallies, len(records), "run", {}, out)
    # The template's `const DATA = COVERAGE_DATA_PLACEHOLDER;` line becomes the payload.
    line = next(ln for ln in out.read_text().splitlines() if "const DATA = " in ln)
    payload = json.loads(line.split("const DATA = ", 1)[1].rstrip(";").replace(r"<\/", "</"))
    ref = next(d for d in payload["dimensions"] if d["field"] == REF)
    assert (ref["classified"], ref["not_classified"], ref["conflict"]) == (3, 1, 4)
    assert ref["conflict_breakdown"][0] == {"ext": ".bed", "competing": "CHM13 vs GRCh38", "count": 2}
