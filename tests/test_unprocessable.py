"""Tests for the unprocessable-files report (#376, AC3).

The report is the answer to "what did this run not classify, and why?", so what is
tested is that each reason is recognized from the right signal, rendered with its
explanation, and — when a category is empty — says so in words rather than showing an
empty table.
"""

import json

import pytest

from meta_disco.exclusions import EXCLUDED_FILE, ExcludedFile, write_excluded
from meta_disco.header_classifier import FETCH_FAILED_RULE_ID
from meta_disco.metadata_schema import VALIDATION_RULE_ID
from meta_disco.models import all_not_classified, build_field_entry
from meta_disco.unprocessable import (
    CONTENT_UNREADABLE,
    CONTRACT_VIOLATION,
    NO_CHECKSUM,
    UNKNOWN_DATASET,
    gather,
    render_report,
)


def _classified_record(file_name="ok.bam", dataset="Study A"):
    """A normal record: classified, no reason to appear in the report."""
    return {
        "file_name": file_name,
        "dataset_title": dataset,
        "md5sum": "a" * 32,
        "classifications": {
            "data_modality": build_field_entry("genomic"),
            "data_type": build_field_entry("alignments"),
            "platform": build_field_entry(None),
            "reference_assembly": build_field_entry(None),
            "assay_type": build_field_entry(None),
        },
    }


def _reason_record(rule_id, file_name, dataset, reason="because"):
    return {
        "file_name": file_name,
        "dataset_title": dataset,
        "md5sum": "b" * 32,
        "classifications": all_not_classified([{"rule_id": rule_id, "reason": reason}]),
    }


def _write_run(tmp_path, records, fname="bam_classifications.json"):
    run_dir = tmp_path / "20260101_000000"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / fname).write_text(json.dumps({"metadata": {}, "classifications": records}))
    return run_dir


def _excluded(file_name, dataset="Study A", **overrides):
    record = {"file_name": file_name, "dataset_title": dataset, "entry_id": "e1", "file_id": "f1"}
    record.update(overrides)
    return ExcludedFile.from_record(record)


class TestGather:
    def test_recognizes_a_contract_violation_by_its_rule_id(self, tmp_path):
        run_dir = _write_run(tmp_path, [_reason_record(VALIDATION_RULE_ID, "bad.bam", "Study A")])
        data = gather(run_dir)
        groups = data.rows[CONTRACT_VIOLATION.key]
        assert groups["Study A"].count == 1
        assert groups["Study A"].examples == ["bad.bam"]

    def test_recognizes_content_unreadable_by_its_rule_id(self, tmp_path):
        run_dir = _write_run(tmp_path, [_reason_record(FETCH_FAILED_RULE_ID, "gone.bam", "Study B")])
        data = gather(run_dir)
        assert data.rows[CONTENT_UNREADABLE.key]["Study B"].count == 1
        assert data.rows[CONTRACT_VIOLATION.key] == {}

    def test_the_two_row_reasons_are_not_confused(self, tmp_path):
        """Both produce the same all-not_classified shape, so only the rule_id can tell
        them apart — a shape-based check would collapse them into one category."""
        run_dir = _write_run(
            tmp_path,
            [
                _reason_record(VALIDATION_RULE_ID, "bad.bam", "Study A"),
                _reason_record(FETCH_FAILED_RULE_ID, "gone.bam", "Study A"),
            ],
        )
        data = gather(run_dir)
        assert data.rows[CONTRACT_VIOLATION.key]["Study A"].examples == ["bad.bam"]
        assert data.rows[CONTENT_UNREADABLE.key]["Study A"].examples == ["gone.bam"]

    def test_a_classified_record_is_not_reported(self, tmp_path):
        run_dir = _write_run(tmp_path, [_classified_record()])
        data = gather(run_dir)
        assert data.total_records == 1
        assert all(groups == {} for groups in data.rows.values())

    def test_groups_by_dataset_and_bounds_the_examples(self, tmp_path):
        records = [_reason_record(FETCH_FAILED_RULE_ID, f"f{i}.bam", "Study A") for i in range(9)]
        records.append(_reason_record(FETCH_FAILED_RULE_ID, "other.bam", "Study B"))
        run_dir = _write_run(tmp_path, records)

        data = gather(run_dir, max_examples=3)
        groups = data.rows[CONTENT_UNREADABLE.key]
        assert groups["Study A"].count == 9
        assert len(groups["Study A"].examples) == 3
        assert groups["Study B"].count == 1

    def test_a_drifted_file_name_is_not_collapsed_to_empty(self, tmp_path):
        """A file_name of 0 is drift the report exists to surface; `str(x or "")` would
        have shown it as a blank example, hiding it."""
        run_dir = _write_run(tmp_path, [_reason_record(FETCH_FAILED_RULE_ID, 0, "Study A")])
        assert gather(run_dir).rows[CONTENT_UNREADABLE.key]["Study A"].examples == ["0"]

    def test_a_missing_dataset_title_gets_a_named_bucket(self, tmp_path):
        """The HPRC source carries no dataset_title; those rows must stay visible."""
        run_dir = _write_run(tmp_path, [_reason_record(FETCH_FAILED_RULE_ID, "h.bam", None)])
        assert gather(run_dir).rows[CONTENT_UNREADABLE.key][UNKNOWN_DATASET].count == 1

    def test_reads_the_exclusions_file(self, tmp_path):
        run_dir = _write_run(tmp_path, [])
        write_excluded(run_dir, [_excluded("no-md5.bam")], total_input=5)

        data = gather(run_dir)
        assert [f.file_name for f in data.excluded] == ["no-md5.bam"]
        assert data.exclusions_present is True
        assert data.total_input == 5

    def test_a_run_without_an_exclusions_file_is_marked_absent(self, tmp_path):
        data = gather(_write_run(tmp_path, []))
        assert data.exclusions_present is False
        assert data.excluded == []

    def test_missing_run_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            gather(tmp_path / "nope")


class TestExcludedCount:
    """The count is `None` when unknown, so a renderer cannot default it to zero.

    Every renderer written so far that reached for `len(data.excluded)` instead got this
    wrong, which is why the accessor exists.
    """

    def test_none_when_the_run_recorded_nothing(self, tmp_path):
        assert gather(_write_run(tmp_path, [])).excluded_count is None

    def test_none_when_the_exclusions_file_is_unreadable(self, tmp_path):
        run_dir = _write_run(tmp_path, [])
        (run_dir / EXCLUDED_FILE).write_text("not json")
        assert gather(run_dir).excluded_count is None

    def test_zero_when_the_run_recorded_a_zero(self, tmp_path):
        run_dir = _write_run(tmp_path, [])
        write_excluded(run_dir, [], total_input=4)
        assert gather(run_dir).excluded_count == 0

    def test_the_count_when_the_run_recorded_files(self, tmp_path):
        run_dir = _write_run(tmp_path, [])
        write_excluded(run_dir, [_excluded("a.bam"), _excluded("b.bam")], total_input=9)
        assert gather(run_dir).excluded_count == 2

    def test_recoverable_rows_do_not_make_a_damaged_file_countable(self, tmp_path):
        """The rows are still listed, but their number is not the run's excluded count."""
        run_dir = _write_run(tmp_path, [])
        (run_dir / EXCLUDED_FILE).write_text(json.dumps({"excluded": ["nope", {"file_name": "half.bam"}]}))
        data = gather(run_dir)
        assert len(data.excluded) == 1
        assert data.excluded_count is None


class TestDatasetLabel:
    def test_a_drifted_but_present_title_keeps_its_own_bucket(self, tmp_path):
        """`0` is a title the catalog actually carried — drift this report exists to
        surface, not the same thing as having no title at all."""
        run_dir = _write_run(tmp_path, [_reason_record(FETCH_FAILED_RULE_ID, "x.bam", 0)])
        groups = gather(run_dir).rows[CONTENT_UNREADABLE.key]
        assert "0" in groups
        assert UNKNOWN_DATASET not in groups

    @pytest.mark.parametrize("title", [None, ""], ids=["null", "empty"])
    def test_an_absent_or_empty_title_falls_into_the_untitled_bucket(self, tmp_path, title):
        run_dir = _write_run(tmp_path, [_reason_record(FETCH_FAILED_RULE_ID, "x.bam", title)])
        assert UNKNOWN_DATASET in gather(run_dir).rows[CONTENT_UNREADABLE.key]


class TestRenderReport:
    def test_every_reason_gets_a_section_with_its_explanation(self, tmp_path):
        run_dir = _write_run(tmp_path, [])
        write_excluded(run_dir, [], total_input=0)
        report = render_report(gather(run_dir))

        for reason in (NO_CHECKSUM, CONTRACT_VIOLATION, CONTENT_UNREADABLE):
            assert f"### {reason.title}" in report
            assert reason.explanation in report
            assert reason.row_exists in report

    def test_an_empty_category_says_so_instead_of_an_empty_table(self, tmp_path):
        run_dir = _write_run(tmp_path, [_classified_record()])
        write_excluded(run_dir, [], total_input=1)
        report = render_report(gather(run_dir))

        assert report.count("None in this run") == 3
        assert "| dataset | files | examples |" not in report

    def test_excluded_files_are_listed_individually(self, tmp_path):
        run_dir = _write_run(tmp_path, [])
        write_excluded(
            run_dir,
            [_excluded("a.bam"), _excluded("b.bam"), _excluded("c.bam", dataset="Study B")],
            total_input=3,
        )
        report = render_report(gather(run_dir))

        # Every excluded file is named — this report is the only place they appear.
        for name in ("a.bam", "b.bam", "c.bam"):
            assert name in report
        assert "#### Study A — 2 file(s)" in report
        assert "#### Study B — 1 file(s)" in report

    def test_row_backed_reasons_are_counted_not_listed(self, tmp_path):
        records = [_reason_record(FETCH_FAILED_RULE_ID, f"f{i}.bam", "Study A") for i in range(30)]
        run_dir = _write_run(tmp_path, records)
        report = render_report(gather(run_dir, max_examples=2), max_examples=2)

        assert "| Study A | 30 |" in report
        assert "(+28 more)" in report
        assert "f29.bam" not in report

    def test_summary_totals_cover_every_reason(self, tmp_path):
        run_dir = _write_run(
            tmp_path,
            [
                _reason_record(VALIDATION_RULE_ID, "bad.bam", "Study A"),
                _reason_record(FETCH_FAILED_RULE_ID, "gone.bam", "Study A"),
                _reason_record(FETCH_FAILED_RULE_ID, "gone2.bam", "Study A"),
            ],
        )
        write_excluded(run_dir, [_excluded("no-md5.bam")], total_input=4)
        report = render_report(gather(run_dir))

        assert f"| {NO_CHECKSUM.title} | 1 | no — excluded |" in report
        assert f"| {CONTRACT_VIOLATION.title} | 1 | yes |" in report
        assert f"| {CONTENT_UNREADABLE.title} | 2 | yes |" in report
        assert "| **Total** | **4** | |" in report

    def test_a_pre_exclusion_run_says_the_answer_is_unknown(self, tmp_path):
        """No exclusions file is a different statement from "excluded nothing", and the
        report must not silently render the second when it means the first."""
        report = render_report(gather(_write_run(tmp_path, [])))
        assert "**Unknown**" in report
        # States the possibilities rather than asserting one cause (CLAUDE.md: no
        # speculation as fact) — a missing file is not proof the run predates #376.
        assert "cannot be told from the directory" in report

    def test_an_unknown_excluded_count_is_not_rendered_as_zero(self, tmp_path):
        """The summary must not contradict its own body: a run with no exclusions file
        shows "?" and is left out of the total, rather than claiming zero were shed."""
        run_dir = _write_run(tmp_path, [_reason_record(FETCH_FAILED_RULE_ID, "gone.bam", "Study A")])
        report = render_report(gather(run_dir))

        assert f"| {NO_CHECKSUM.title} | ? | no — excluded |" in report
        # The known reasons still total, marked as a lower bound.
        assert "| **Total** | **1+** | |" in report

    def test_a_recorded_zero_input_still_states_the_count(self, tmp_path):
        """A run over an empty input recorded 0 checked — a real answer. Testing
        total_input for truthiness would have hidden it as though it were unknown."""
        run_dir = _write_run(tmp_path, [])
        write_excluded(run_dir, [], total_input=0)
        report = render_report(gather(run_dir))

        assert "None in this run (0 input records checked)." in report
        assert "against 0 input record(s)." in report

    def test_an_unreadable_exclusions_file_is_not_read_as_a_known_zero(self, tmp_path):
        """A damaged file is a different fact from "excluded nothing". Reporting the
        second when we mean the first is the unevidenced claim this whole change exists
        to stop — and the rows that survived are still named, since nothing else holds
        them."""
        run_dir = _write_run(tmp_path, [])
        # Valid JSON, but a row that is not a record: the count is untrustworthy while
        # the intact row is still recoverable.
        (run_dir / EXCLUDED_FILE).write_text(json.dumps({"excluded": ["nope", {"file_name": "half.bam"}]}))
        report = render_report(gather(run_dir))

        assert "**Unknown**" in report
        assert "could not be read" in report
        assert "half.bam" in report
        assert f"| {NO_CHECKSUM.title} | ? | no — excluded |" in report
        assert "input records checked" not in report

    def test_an_unparseable_exclusions_file_reports_unknown_with_nothing_to_list(self, tmp_path):
        """Truncated JSON yields no recoverable rows at all — still unknown, not zero."""
        run_dir = _write_run(tmp_path, [])
        (run_dir / EXCLUDED_FILE).write_text('{"excluded": [{"file_name": "x.bam"}], "meta')
        report = render_report(gather(run_dir))

        assert "**Unknown**" in report
        assert "could not be read" in report
        assert "listed in full" not in report

    def test_an_unrecorded_run_states_no_input_count(self, tmp_path):
        """With no exclusions file there is no input count to state, so the summary line
        must not imply one."""
        report = render_report(gather(_write_run(tmp_path, [])))
        assert "input record(s)." not in report

    def test_a_known_zero_is_rendered_as_zero(self, tmp_path):
        """A run that recorded its exclusions and shed nothing says 0, not "?"."""
        run_dir = _write_run(tmp_path, [])
        write_excluded(run_dir, [], total_input=5)
        report = render_report(gather(run_dir))

        assert f"| {NO_CHECKSUM.title} | 0 | no — excluded |" in report
        assert "| **Total** | **0** | |" in report

    def test_pipes_in_a_dataset_title_do_not_break_the_table(self, tmp_path):
        run_dir = _write_run(tmp_path, [_reason_record(FETCH_FAILED_RULE_ID, "x.bam", "A | B")])
        report = render_report(gather(run_dir))
        assert "A \\| B" in report
