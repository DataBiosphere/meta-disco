"""The coverage report's three buckets (#88): the rule is stated on
``generate_coverage_report.Tally``, which these tests hold to it. Before #88 a
conflict resolved to ``not_classified`` and the report had no way to tell the two apart.
"""

import json
from collections import Counter

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
    """Ties by extension, whatever order the records were read in (#732)."""
    expected = [
        {"ext": ".bed", "competing": "CHM13 vs GRCh38", "count": 2},
        {"ext": ".idx", "competing": report.COMPETING_NOT_RECORDED, "count": 1},
        {"ext": ".vcf", "competing": "GRCh37 vs GRCh38", "count": 1},
    ]
    assert report.Tally(records, REF).conflict_rows() == expected
    assert report.Tally(records[::-1], REF).conflict_rows() == expected


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
    report.generate_html_dashboard(tallies, len(records), "run", Counter(), out)
    # The template's `const DATA = COVERAGE_DATA_PLACEHOLDER;` line becomes the payload.
    line = next(ln for ln in out.read_text().splitlines() if "const DATA = " in ln)
    payload = json.loads(line.split("const DATA = ", 1)[1].rstrip(";").replace(r"<\/", "</"))
    ref = next(d for d in payload["dimensions"] if d["field"] == REF)
    assert (ref["classified"], ref["not_classified"], ref["conflict"]) == (3, 1, 4)
    assert ref["conflict_breakdown"][0] == {"ext": ".bed", "competing": "CHM13 vs GRCh38", "count": 2}


def test_a_reason_carrying_file_content_is_shown_literally_not_as_markup():
    # An unrecognised IDAT's chip type reaches its reason (#603); Pages renders raw HTML.
    reason = "chip type '<img src=x onerror=alert(1)>', 7 probes: not a chip this rule recognises"
    records = [{"ext": ".idat", REF: NOT_CLASSIFIED, f"{REF}_reason": reason}]
    section = report.build_section(report.Tally(records, REF), 1, "Reference Assembly")
    assert f"`{reason}`" in section


def test_every_section_and_the_dashboard_rank_ties_by_name_whatever_order_the_records_came_in(tmp_path):
    """#732's case: tied extensions (`.snarls`, `.gg`, `.min`) and tied values reordered on a re-download."""
    rows = [
        {"ext": ext, REF: value, f"{REF}_reason": reason, "dataset_title": dataset}
        for ext, value, reason, dataset in [
            (".snarls", NOT_CLASSIFIED, "No rule for .snarls", "B"),
            (".gg", NOT_CLASSIFIED, "No rule for .gg", "A"),
            (".min", NOT_CLASSIFIED, "No rule for .min", "B"),
            (".bam", "GRCh38", None, "A"),
            (".cram", "GRCh37", None, "C"),
            (".gg", NOT_CLASSIFIED, "Another reason", "C"),
        ]
    ]
    outputs = []
    for name, order in (("forward", rows), ("backward", rows[::-1])):
        tally = report.Tally(order, REF)
        html = tmp_path / f"{name}.html"
        report.generate_html_dashboard(
            [(REF, "Reference", "", tally)], len(order), "run", Counter(r["dataset_title"] for r in order), html
        )
        outputs.append((report.build_section(tally, len(order), "Reference"), html.read_text()))
    assert outputs[0] == outputs[1]
    section = outputs[0][0]
    assert section.index("| .gg |") < section.index("| .min |") < section.index("| .snarls |")
    assert "`GRCh37`" in section and section.index("`GRCh37`") < section.index("`GRCh38`")
