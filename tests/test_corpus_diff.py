"""Tests for the two-generation corpus comparison (#335)."""

import json
from collections import Counter
from pathlib import Path

import pytest

from meta_disco.corpus_diff import (
    _sort_key,
    classified_by_dataset,
    diff_runs,
    read_snapshot,
    render_dataset_section,
    render_report,
    run_labels,
    snapshot_parity,
)
from meta_disco.models import CLASSIFICATION_FIELDS, NOT_APPLICABLE, build_field_entry
from tests.metadata_fixtures import valid_record

_DIMS = CLASSIFICATION_FIELDS


def _snapshot_record(name, md5, dataset="DS1"):
    """An input-snapshot record, from the shared contract-valid builder."""
    return valid_record(file_name=name, file_md5sum=md5, dataset_title=dataset)


def _parity_by_dataset(rows):
    return {row.dataset: row for row in rows}


def test_parity_matches_identical_snapshots():
    records = [_snapshot_record("a.bam", "m1"), _snapshot_record("b.vcf.gz", "m2")]
    (row,) = snapshot_parity(records, list(records))
    assert (row.unchanged, row.md5_changed, row.removed, row.added) == (2, 0, 0, 0)
    assert row.old_total == row.new_total == 2


def test_parity_separates_md5_change_from_removal_and_addition():
    old = [
        _snapshot_record("kept.bam", "m1"),
        _snapshot_record("rewritten.bam", "m2"),
        _snapshot_record("gone.bam", "m3"),
    ]
    new = [
        _snapshot_record("kept.bam", "m1"),
        _snapshot_record("rewritten.bam", "m2-new"),
        _snapshot_record("fresh.bam", "m4"),
    ]
    (row,) = snapshot_parity(old, new)
    assert (row.unchanged, row.md5_changed, row.removed, row.added) == (1, 1, 1, 1)


def test_parity_reports_a_dataset_that_left_the_catalog():
    old = [_snapshot_record("a.bam", "m1", dataset="KEPT"), _snapshot_record("g.svs", "m2", dataset="GONE")]
    new = [_snapshot_record("a.bam", "m1", dataset="KEPT")]
    rows = _parity_by_dataset(snapshot_parity(old, new))
    assert rows["GONE"].removed == 1
    assert rows["GONE"].new_total == 0
    assert rows["KEPT"].unchanged == 1
    # The changed dataset sorts ahead of the identical one.
    assert [row.dataset for row in snapshot_parity(old, new)] == ["GONE", "KEPT"]


def test_parity_counts_repeated_identities_as_a_multiset():
    old = [_snapshot_record("dup.bam", "m1")] * 3
    new = [_snapshot_record("dup.bam", "m1")] * 2
    (row,) = snapshot_parity(old, new)
    assert (row.unchanged, row.removed) == (2, 1)


def test_parity_skips_malformed_records():
    """A non-dict entry or a nameless record is skipped, not counted or raised on.

    The input contract is the ``validate_metadata`` gate's job; a parity report
    should still produce a table for the records it can identify.
    """
    old = ["not-a-record", {"file_md5sum": "m0"}, _snapshot_record("a.bam", "m1")]
    (row,) = snapshot_parity(old, [_snapshot_record("a.bam", "m1")])
    assert (row.unchanged, row.removed, row.added) == (1, 0, 0)


def test_read_snapshot_tolerates_a_non_numeric_total(tmp_path):
    """A stringified total must not blow up at render time, after both parses."""
    path = tmp_path / "snap.json"
    path.write_text(json.dumps({"metadata": {"catalog": "anvil15", "total_files": "708088"}, "files": []}))
    assert read_snapshot(path)[0].total_files == 708088
    path.write_text(json.dumps({"metadata": {"catalog": "anvil15", "total_files": "many"}, "files": []}))
    assert read_snapshot(path)[0].total_files is None


def _write_run(run_dir: Path, records: list[dict], fname="bam_classifications.json"):
    """Write a run directory holding one classification output file."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / fname).write_text(json.dumps({"metadata": {}, "classifications": records}))
    return run_dir


def _run_record(name, md5, dataset="DS1", **labels):
    """A classification output record; each dim kwarg is a value, else not_classified.

    Entries come from ``models.build_field_entry`` — the single place that assembles
    the ``{value, status, evidence}`` shape — so the fixture follows the output
    shape rather than restating it.
    """
    classifications = {dim: build_field_entry(labels.get(dim)) for dim in _DIMS}
    return {"file_name": name, "md5sum": md5, "dataset_title": dataset, "classifications": classifications}


def test_run_labels_reads_identity_and_labels(tmp_path):
    run = _write_run(tmp_path / "run", [_run_record("a.bam", "m1", data_modality="genomic")])
    labels = run_labels(run)
    assert list(labels) == [("DS1", "a.bam", "m1")]
    (label_tuple,) = labels[("DS1", "a.bam", "m1")]
    assert label_tuple[_DIMS.index("data_modality")] == "genomic"
    assert label_tuple[_DIMS.index("data_type")] == "not_classified"


def test_run_labels_skips_a_missing_output_file(tmp_path):
    """A run that did not write every CLASSIFICATION_FILES entry still reads."""
    run = _write_run(tmp_path / "run", [_run_record("a.bam", "m1")])
    assert len(run_labels(run)) == 1


def test_run_labels_raises_on_a_missing_run_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_labels(tmp_path / "absent")


def test_run_labels_keeps_records_whose_dataset_title_is_absent(tmp_path):
    """dataset_title is a qualifier, not the identity — the HPRC source has none.

    Requiring it would drop that whole corpus, so a record with an md5 and no
    dataset title still joins to its counterpart.
    """
    record = _run_record("a.bam", "m1", data_modality="genomic")
    record["dataset_title"] = None
    old = _write_run(tmp_path / "old", [dict(record)])
    new = _write_run(tmp_path / "new", [dict(record)])
    assert set(run_labels(old)) == set(run_labels(new)) == {("", "a.bam", "m1")}
    diff = diff_runs(run_labels(old), run_labels(new))["data_modality"]
    assert (diff.classified_lost, diff.classified_gained) == (0, 0)
    assert diff.classified_old == diff.classified_new == 1


def test_diff_attributes_a_label_change_to_the_classifier(tmp_path):
    old = _write_run(tmp_path / "old", [_run_record("a.bam", "m1")])
    new = _write_run(tmp_path / "new", [_run_record("a.bam", "m1", data_modality="genomic")])
    diff = diff_runs(run_labels(old), run_labels(new))["data_modality"]
    assert diff.changed == Counter({("not_classified", "genomic"): 1})
    assert (diff.classified_lost, diff.classified_gained) == (0, 0)
    assert diff.classified_net_changed == 1
    assert diff.classified_new - diff.classified_old == 1


def test_diff_attributes_a_dropped_file_to_corpus_loss(tmp_path):
    old = _write_run(
        tmp_path / "old",
        [_run_record("a.bam", "m1", data_modality="genomic"), _run_record("gone.bam", "m2", data_modality="genomic")],
    )
    new = _write_run(tmp_path / "new", [_run_record("a.bam", "m1", data_modality="genomic")])
    diff = diff_runs(run_labels(old), run_labels(new))["data_modality"]
    assert diff.classified_lost == 1
    assert (diff.classified_gained, diff.classified_net_changed) == (0, 0)
    assert not diff.changed
    assert diff.classified_new - diff.classified_old == -1


def test_diff_attributes_a_new_file_to_corpus_gain(tmp_path):
    old = _write_run(tmp_path / "old", [_run_record("a.bam", "m1", data_modality="genomic")])
    new = _write_run(
        tmp_path / "new",
        [_run_record("a.bam", "m1", data_modality="genomic"), _run_record("fresh.bam", "m9", data_modality="genomic")],
    )
    diff = diff_runs(run_labels(old), run_labels(new))["data_modality"]
    assert diff.classified_gained == 1
    assert (diff.classified_lost, diff.classified_net_changed) == (0, 0)


def test_diff_reports_an_md5_change_as_loss_plus_gain(tmp_path):
    """md5 is part of the identity, so changed content is a different file.

    Which run's corpus a file belongs to is then decided by content, and the
    snapshot parity table is what says how many such files there were.
    """
    old = _write_run(tmp_path / "old", [_run_record("a.bam", "m1", data_modality="genomic")])
    new = _write_run(tmp_path / "new", [_run_record("a.bam", "m2", data_modality="genomic")])
    diff = diff_runs(run_labels(old), run_labels(new))["data_modality"]
    assert (diff.classified_lost, diff.classified_gained) == (1, 1)
    assert not diff.changed


def test_classified_by_dataset_counts_values_per_dataset(tmp_path):
    run = _write_run(
        tmp_path / "run",
        [
            _run_record("a.bam", "m1", dataset="A", data_modality="genomic"),
            _run_record("b.bam", "m2", dataset="A"),
            _run_record("c.bam", "m3", dataset="B", data_modality="genomic", data_type="alignment"),
        ],
    )
    counts = classified_by_dataset(run_labels(run))
    assert set(counts) == {"A", "B"}
    assert counts["A"]["data_modality"] == 1
    assert counts["A"]["data_type"] == 0
    assert counts["B"]["data_modality"] == counts["B"]["data_type"] == 1


def test_classified_by_dataset_excludes_not_applicable(tmp_path):
    """not_applicable is a status, not a value, so it must not count as coverage."""
    record = _run_record("a.gfa", "m1")
    record["classifications"]["platform"] = build_field_entry(None, status=NOT_APPLICABLE)
    run = _write_run(tmp_path / "run", [record])
    counts = classified_by_dataset(run_labels(run))
    assert counts["DS1"]["platform"] == 0


def test_classified_by_dataset_keeps_a_dataset_with_nothing_classified(tmp_path):
    """A dataset the classifier recognises nothing in must still be a key.

    Otherwise it disappears from the per-dataset table — the one case that table
    most needs to show. Asserted on the keys, since the returned mapping is a plain
    dict and would otherwise raise rather than auto-create.
    """
    run = _write_run(
        tmp_path / "run",
        [
            _run_record("a.bam", "m1", dataset="EMPTY"),
            _run_record("b.bam", "m2", dataset="FULL", data_type="alignment"),
        ],
    )
    counts = classified_by_dataset(run_labels(run))
    assert set(counts) == {"EMPTY", "FULL"}
    assert sum(counts["EMPTY"].values()) == 0


def test_dataset_section_lists_a_dataset_with_nothing_classified(tmp_path):
    """The rendered table keeps that dataset's row rather than dropping it."""
    old = _write_run(tmp_path / "old", [_run_record("a.bam", "m1", dataset="QUIET")])
    new = _write_run(tmp_path / "new", [_run_record("a.bam", "m1", dataset="QUIET")])
    rendered = "\n".join(render_dataset_section(run_labels(old), run_labels(new)))
    assert "QUIET" in rendered


def test_sort_key_tolerates_a_none_label():
    """Pairing leftovers must not raise on a label tuple holding a None.

    ``field_label``'s return type admits None; ``models._assert_coherent`` makes it
    unreachable through a well-formed run (it raises on that shape instead), so
    this guards the sort against a shape the diff cannot itself verify.
    """
    tuples = [("genomic", None), (None, "alignment")]
    ordered = sorted(tuples, key=_sort_key)
    # Which order results is arbitrary and not part of the contract — that sorting
    # is total over these shapes, rather than raising on None, is.
    assert set(ordered) == set(tuples)
    assert sorted(tuples, key=_sort_key) == ordered


def test_diff_pairs_repeated_identities_as_multisets(tmp_path):
    """Two copies of one identity, one of which changed label, yields one change."""
    old = _write_run(
        tmp_path / "old",
        [_run_record("dup.bam", "m1"), _run_record("dup.bam", "m1")],
    )
    new = _write_run(
        tmp_path / "new",
        [_run_record("dup.bam", "m1"), _run_record("dup.bam", "m1", data_modality="genomic")],
    )
    diff = diff_runs(run_labels(old), run_labels(new))["data_modality"]
    assert diff.changed == Counter({("not_classified", "genomic"): 1})
    assert diff.old["not_classified"] == 2
    assert diff.new["genomic"] == 1


def test_diff_counts_an_extra_copy_of_an_identity_as_a_gain(tmp_path):
    """Unequal copy counts leave a leftover with nothing to pair against.

    The extra copy arrived in the corpus, so it belongs in gained rather than
    being dropped from the attribution.
    """
    old = _write_run(tmp_path / "old", [_run_record("dup.bam", "m1", data_modality="genomic")])
    new = _write_run(
        tmp_path / "new",
        [_run_record("dup.bam", "m1", data_modality="genomic"), _run_record("dup.bam", "m1", data_type="alignment")],
    )
    diff = diff_runs(run_labels(old), run_labels(new))["data_modality"]
    assert diff.classified_gained == 0  # the extra copy is not classified on this dimension
    assert diff.gained["not_classified"] == 1
    assert diff.classified_new - diff.classified_old == 0


def test_attribution_accounts_for_the_whole_delta(tmp_path):
    """new - old == gained - lost + net(changed), over a mixed scenario."""
    old = _write_run(
        tmp_path / "old",
        [
            _run_record("stable.bam", "m1", data_modality="genomic"),
            _run_record("relabelled.bam", "m2"),
            _run_record("gone.bam", "m3", data_modality="genomic"),
            _run_record("declassified.bam", "m4", data_modality="genomic"),
        ],
    )
    new = _write_run(
        tmp_path / "new",
        [
            _run_record("stable.bam", "m1", data_modality="genomic"),
            _run_record("relabelled.bam", "m2", data_modality="genomic"),
            _run_record("declassified.bam", "m4"),
            _run_record("fresh.bam", "m5", data_modality="genomic"),
        ],
    )
    diff = diff_runs(run_labels(old), run_labels(new))["data_modality"]
    delta = diff.classified_new - diff.classified_old
    assert delta == diff.classified_gained - diff.classified_lost + diff.classified_net_changed
    assert (diff.classified_lost, diff.classified_gained, diff.classified_net_changed) == (1, 1, 0)


def test_not_applicable_is_not_counted_as_classified(tmp_path):
    """not_applicable is a status label, so it must not inflate the classified count."""
    record = _run_record("a.gfa", "m1")
    record["classifications"]["platform"] = build_field_entry(None, status=NOT_APPLICABLE)
    run = _write_run(tmp_path / "run", [record])
    labels = run_labels(run)
    diff = diff_runs(labels, labels)["platform"]
    assert diff.classified_old == diff.classified_new == 0
    assert diff.old["not_applicable"] == 1


def test_read_snapshot_reads_the_envelope(tmp_path):
    path = tmp_path / "snap.json"
    path.write_text(
        json.dumps({"metadata": {"catalog": "anvil15", "downloaded_at": "2026-09-04", "total_files": 7}, "files": []})
    )
    meta, records = read_snapshot(path)
    assert (meta.catalog, meta.downloaded_at, meta.total_files) == ("anvil15", "2026-09-04", 7)
    assert records == []


def test_read_snapshot_tolerates_an_unlabelled_snapshot(tmp_path):
    """The archived anvil14 pull predates the recorded catalog — report it as unknown."""
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"metadata": {"downloaded_at": "2026-07-29", "total_files": 3}, "files": []}))
    assert read_snapshot(path)[0].catalog is None


def test_render_report_covers_every_section(tmp_path):
    old = _write_run(tmp_path / "old", [_run_record("a.bam", "m1"), _run_record("g.svs", "m2", dataset="GONE")])
    new = _write_run(tmp_path / "new", [_run_record("a.bam", "m1", data_modality="genomic")])
    old_snap = tmp_path / "old.json"
    new_snap = tmp_path / "new.json"
    old_snap.write_text(json.dumps({"metadata": {"total_files": 2}, "files": []}))
    new_snap.write_text(json.dumps({"metadata": {"catalog": "anvil15", "total_files": 1}, "files": []}))

    report = render_report(
        old_meta=read_snapshot(old_snap)[0],
        new_meta=read_snapshot(new_snap)[0],
        parity=snapshot_parity(
            [_snapshot_record("a.bam", "m1"), _snapshot_record("g.svs", "m2", dataset="GONE")],
            [_snapshot_record("a.bam", "m1")],
        ),
        old_run=old,
        new_run=new,
        old_labels=run_labels(old),
        new_labels=run_labels(new),
        generated_at="2026-09-04 01:00",
    )
    assert "## Input snapshots" in report
    assert "## Coverage by dimension" in report
    assert "## Label changes on files present in both runs" in report
    assert "## Per-dataset classified counts" in report
    assert "(unrecorded)" in report  # the old snapshot's missing catalog
    assert "GONE" in report


def test_render_report_says_so_when_no_label_changed(tmp_path):
    run = _write_run(tmp_path / "run", [_run_record("a.bam", "m1", data_modality="genomic")])
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"metadata": {"catalog": "anvil15", "total_files": 1}, "files": []}))
    report = render_report(
        old_meta=read_snapshot(snap)[0],
        new_meta=read_snapshot(snap)[0],
        parity=snapshot_parity([_snapshot_record("a.bam", "m1")], [_snapshot_record("a.bam", "m1")]),
        old_run=run,
        new_run=run,
        old_labels=run_labels(run),
        new_labels=run_labels(run),
        generated_at="2026-09-04 01:00",
    )
    assert "No file present in both runs changed a label." in report
