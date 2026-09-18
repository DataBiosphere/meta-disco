"""The published comparison: what AnVIL declares, beside what a run concluded (#424).

Covers the three joints the feature has: the declaration surviving from an input
record into the output envelope (``records.build_published``), the recommendation for
one file and one dimension (``published.recommendation``), and the report gathered
over a run directory (``published.gather``).
"""

import json
import pathlib

import pytest

from meta_disco.models import NOT_APPLICABLE, NOT_CLASSIFIED
from meta_disco.pipeline import ClassifyPipeline, load_classifiable_snapshot, published_source
from meta_disco.published_comparison import (
    ADD,
    KEEP,
    MULTI_VALUE_SEP,
    NONE,
    REVIEW,
    TSV_HEADER,
    gather,
    recommendation,
    render_report,
    render_tsv,
    spoke,
)
from meta_disco.records import ClassifierRecord, InvalidRecord, OutputRecord, build_published
from tests.metadata_fixtures import valid_record
from tests.producer_sweep import STANDALONE_PRODUCERS, run_index_producer, run_producer


def _entry(value=None, status=None):
    """One dimension entry in the output's per-field layout."""
    return {"value": value, "status": status or ("classified" if value else NOT_CLASSIFIED)}


def _record(name, *, modality=None, assembly=None, published=None, dataset="AnVIL_IGVF_Mouse_R1"):
    """One output record as a run writes it."""
    return {
        "file_name": name,
        "md5sum": name,
        "entry_id": name,
        "dataset_title": dataset,
        "classifications": {"data_modality": _entry(modality), "reference_assembly": _entry(assembly)},
        "published": published,
    }


def _write_run(run_dir, records):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "bam_classifications.json").write_text(json.dumps({"metadata": {}, "classifications": records}))
    return run_dir


class TestBuildPublished:
    def test_a_declaration_is_transcribed_verbatim_as_a_list(self):
        block = build_published(
            {
                "data_modality": ["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"],
                "reference_assembly": None,
            },
            "anvil/anvil15",
        )
        assert block is not None
        assert block["data_modality"] == ["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"]
        assert block["reference_assembly"] is None
        assert block["source"] == "anvil/anvil15"

    def test_a_file_the_repository_publishes_nothing_for_gets_no_block(self):
        assert build_published({"data_modality": None, "reference_assembly": None}, "anvil/anvil15") is None

    def test_in_vocabulary_names_only_the_values_that_are_terms(self):
        block = build_published(
            {"data_modality": ["genomic", "single-nucleus ATAC-seq"], "reference_assembly": ["GRCm39"]}, None
        )
        assert block is not None
        # `genomic` is a data_modality_enum term; the other two are not.
        assert block["in_vocabulary"] == {"data_modality": ["genomic"], "reference_assembly": []}

    def test_every_value_the_corpus_declares_today_is_outside_our_vocabulary(self):
        # The measured state at #424, and the reason the translation table (#414) is
        # owed: not one published value is a term this schema knows.
        block = build_published(
            {
                "data_modality": ["single-nucleus RNA sequencing assay", "single-nucleus ATAC-seq"],
                "reference_assembly": ["GRCh38 + Gencode40", "GRCm39"],
            },
            "anvil/anvil15",
        )
        assert block is not None
        assert block["in_vocabulary"] == {"data_modality": [], "reference_assembly": []}

    def test_a_dimension_with_no_published_value_is_absent_from_in_vocabulary(self):
        block = build_published({"data_modality": ["genomic"], "reference_assembly": None}, None)
        assert block is not None
        assert set(block["in_vocabulary"]) == {"data_modality"}


class TestPublishedValuesReachTheOutput:
    def test_a_classifier_record_carries_it_into_the_envelope(self):
        item = ClassifierRecord.from_record(valid_record(reference_assembly=["GRCh38 + Gencode40"]))
        out = OutputRecord.from_work_item(item, {}, source="anvil/anvil15").to_dict()
        assert out["published"]["reference_assembly"] == ["GRCh38 + Gencode40"]
        assert out["published"]["in_vocabulary"] == {"reference_assembly": []}

    def test_a_validation_failed_record_still_reports_what_is_published(self):
        # Failing our contract on file_size does not stop AnVIL from declaring a
        # modality, and the row must still say so.
        item = InvalidRecord.from_record(valid_record(file_size="big", data_modality=["genomic"]), ["file_size: bad"])
        out = OutputRecord.from_work_item(item, {}, source="anvil/anvil15").to_dict()
        assert out["published"]["data_modality"] == ["genomic"]

    def test_the_envelope_carries_the_key_even_with_no_published_value(self):
        item = ClassifierRecord.from_record(valid_record())
        out = OutputRecord.from_work_item(item, {}, source="anvil/anvil15").to_dict()
        assert "published" in out and out["published"] is None


class TestPublishedSource:
    def test_it_names_the_catalog_the_snapshot_recorded(self):
        assert published_source({"repository": "anvil", "catalog": "anvil15"}) == "anvil/anvil15"

    def test_a_second_repository_is_named_from_its_own_envelope(self):
        # The name is not inferred: a shared load path must not label another
        # repository's snapshot `anvil/...` (contract 7.11).
        assert published_source({"repository": "hprc", "catalog": "v2"}) == "hprc/v2"

    @pytest.mark.parametrize(
        "metadata",
        [{}, {"catalog": None}, {"catalog": ""}, {"catalog": "anvil15"}, {"repository": "anvil"}],
        ids=["empty", "null-catalog", "empty-catalog", "no-repository", "no-catalog"],
    )
    def test_an_envelope_missing_either_half_leaves_the_repository_unnamed(self, metadata):
        # An unnamed repository is a fact; a guessed one is the drift #335 exists to catch.
        assert published_source(metadata) is None


class TestRecommendation:
    @pytest.mark.parametrize(
        "published,label,expected",
        [
            (None, "genomic", ADD),
            (["GRCm39"], NOT_CLASSIFIED, KEEP),
            (["GRCh38 + Gencode40"], "GRCh38", REVIEW),
            (None, NOT_CLASSIFIED, NONE),
            (None, None, NONE),
        ],
    )
    def test_the_four_states(self, published, label, expected):
        assert recommendation(published, label) == expected

    def test_not_applicable_counts_as_us_having_spoken(self):
        # The four .bai/.tbi rows: AnVIL carries the set's modality, we say the
        # dimension does not apply. That is a comparison to make, not a gap to fill —
        # filing it under keep would claim we had no opinion.
        assert spoke(NOT_APPLICABLE)
        assert recommendation(["single-nucleus ATAC-seq"], NOT_APPLICABLE) == REVIEW

    def test_not_classified_is_the_only_silence(self):
        assert not spoke(NOT_CLASSIFIED)
        assert not spoke(None)


class TestGather:
    def test_it_counts_every_file_and_rows_only_the_published_ones(self, tmp_path):
        run = _write_run(
            tmp_path / "run",
            [
                _record("a.bam", modality="genomic"),
                _record(
                    "b.bam",
                    published=build_published(
                        {"data_modality": ["single-nucleus ATAC-seq"], "reference_assembly": None}, "anvil/anvil15"
                    ),
                ),
            ],
        )
        report = gather(run)
        assert report.files == 2
        assert report.published_files == 1
        assert report.sources == {"anvil/anvil15"}
        assert report.counts[("AnVIL_IGVF_Mouse_R1", "data_modality", ADD)] == 1
        assert report.counts[("AnVIL_IGVF_Mouse_R1", "data_modality", KEEP)] == 1
        # b.bam has no published assembly and inference found none: neither side has a value.
        assert report.counts[("AnVIL_IGVF_Mouse_R1", "reference_assembly", NONE)] == 2

    def test_a_file_written_twice_is_counted_once(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        record = _record("t.tar", modality="genomic")
        for name in ("tar_classifications.json", "auxiliary_classifications.json"):
            (run / name).write_text(json.dumps({"metadata": {}, "classifications": [record]}))
        report = gather(run)
        assert report.files == 1
        assert report.duplicate_records == 1

    def test_compare_rows_group_by_the_value_pair_they_share(self, tmp_path):
        published = build_published(
            {"data_modality": None, "reference_assembly": ["GRCh38 + Gencode40"]}, "anvil/anvil15"
        )
        run = _write_run(
            tmp_path / "run",
            [
                _record(f"e{i}.bam", assembly="GRCh38", published=published, dataset="AnVIL_ENCORE_RS293")
                for i in range(3)
            ],
        )
        pairs = gather(run).compare_pairs()
        assert list(pairs) == [("reference_assembly", "GRCh38 + Gencode40", "GRCh38")]
        assert len(pairs[("reference_assembly", "GRCh38 + Gencode40", "GRCh38")]) == 3

    def test_a_multi_valued_published_cell_is_rejoined_as_the_repository_published_it(self, tmp_path):
        published = build_published(
            {
                "data_modality": ["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"],
                "reference_assembly": None,
            },
            "anvil/anvil15",
        )
        run = _write_run(
            tmp_path / "run", [_record("x.h5ad", modality="transcriptomic.single_cell", published=published)]
        )
        report = gather(run)
        # One dimension carrying two values is still one row.
        assert len(report.rows) == 1
        [row] = [r for r in report.rows if r.dimension == "data_modality"]
        assert row.published_cell == "single-nucleus ATAC-seq || single-nucleus RNA sequencing assay"
        assert row.recommendation == REVIEW
        assert row.vocabulary_standing == "no"


class TestRender:
    def test_the_tsv_has_one_row_per_published_file_and_dimension(self, tmp_path):
        published = build_published({"data_modality": ["GRCm39"], "reference_assembly": ["GRCm39"]}, "anvil/anvil15")
        run = _write_run(
            tmp_path / "run", [_record("m.bam", published=published), _record("n.bam", modality="genomic")]
        )
        lines = render_tsv(gather(run)).strip().split("\n")
        assert lines[0].split("\t") == [
            "entry_id",
            "md5sum",
            "file_name",
            "dataset",
            "dimension",
            "published_value",
            "inferred_value",
            "recommendation",
            "published_in_vocabulary",
        ]
        # Only the file with published values appears, once per dimension, leading with
        # the identity gather deduplicated on — name and dataset do not identify a file.
        assert len(lines) == 3
        # Two rows, one file: `published_files` counts files, not rows, which is why it
        # derives from `file_key` rather than `len(rows)`. Without this, replacing the
        # property with `len(self.rows)` passes the whole suite.
        report = gather(run)
        assert len(report.rows) == 2
        assert report.published_files == 1
        # Every cell, not just the leading identity: swapping two columns in the emitted
        # row is otherwise invisible to this suite.
        assert lines[1].split("\t") == [
            "m.bam",
            "m.bam",
            "m.bam",
            "AnVIL_IGVF_Mouse_R1",
            "data_modality",
            "GRCm39",
            "not_classified",
            "keep",
            "no",
        ]

    def test_the_report_names_the_vocabulary_gap(self, tmp_path):
        published = build_published({"data_modality": None, "reference_assembly": ["GRCm39"]}, "anvil/anvil15")
        run = _write_run(tmp_path / "run", [_record("m.bam", published=published)])
        text = render_report(gather(run))
        assert "`GRCm39`" in text
        assert "1 of 1 distinct published values have no term in the schema vocabulary" in text
        assert "anvil/anvil15" in text


class TestEveryProducerCarriesPublishedValues:
    """The block holds the file's own published values, not a parent's.

    That every producer emits the key at all is structural now (#450): all eleven build
    `OutputRecord`, and `test_output_shape` pins its key set for each. What structure
    cannot enforce is *which record* a producer built the block from — the index
    producer has a parent in hand and must not publish its values as the index file's.
    """

    @staticmethod
    def _published_blocks(rows):
        return [r.get("published") for r in rows]

    @staticmethod
    def _input(name, fmt):
        return valid_record(
            file_name=name,
            file_format=fmt,
            file_md5sum="a" * 32,
            file_size=10,
            entry_id="e1",
            dataset_id="ds1",
            dataset_title="AnVIL_IGVF_Mouse_R1",
            data_modality=["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"],
            reference_assembly=["GRCm39"],
        )

    def test_the_index_producer_writes_the_index_files_own_declaration(self, tmp_path):
        # Not the parent's: AnVIL carries the set's modality on a .bai, and that row is
        # where the two sides most often both speak.
        parent = valid_record(
            file_name="sample.bam", file_format=".bam", file_md5sum="b" * 32, entry_id="p1", dataset_id="ds1"
        )
        envelope = run_index_producer(tmp_path, [parent, self._input("sample.bam.bai", ".bai")])

        [block] = self._published_blocks(envelope["classifications"])
        assert block is not None
        assert block["reference_assembly"] == ["GRCm39"]


def test_the_display_join_matches_the_manifest_reader():
    """The report rejoins a published list with the separator the reader split on.

    This module holds its own copy rather than importing `azul_manifest`, which imports
    `requests` at module scope. That duplication is only safe while the two agree: if
    Azul's separator moved and only the reader were updated, every `published_cell` in the
    report would silently stop matching what Azul published. Imported inside the test so
    the report keeps its offline import graph.
    """
    from meta_disco import azul_manifest

    assert MULTI_VALUE_SEP == azul_manifest._MULTI_VALUE_SEP


def test_two_files_sharing_a_name_in_one_dataset_are_counted_twice(tmp_path):
    """The headline counts files on the identity `gather` deduplicated on.

    The corpus admits a repeated name within a dataset — `corpus_diff` keys on
    (dataset, name, md5) and keeps such a pair as a multiset — so counting by name
    would report one file while the recommendation tables counted two.
    """
    published = build_published({"data_modality": None, "reference_assembly": ["GRCm39"]}, "anvil/anvil15")
    twins = []
    for entry in ("e1", "e2"):
        rec = _record("same.bam", published=published)
        rec["entry_id"], rec["md5sum"] = entry, entry
        twins.append(rec)
    report = gather(_write_run(tmp_path / "run", twins))

    assert report.files == 2
    assert report.duplicate_records == 0
    assert report.published_files == 2
    assert report.counts[("AnVIL_IGVF_Mouse_R1", "reference_assembly", KEEP)] == 2


class TestPublishedShapeIsRefused:
    """`build_published` refuses a shape it cannot use — the constructor-level gate.

    These fields left the input contract, so `validate_metadata` passes them through
    unexamined. Two other gates cover them: `pipeline.refuse_bad_published_shape` at the
    load boundary, which is what refuses a whole snapshot, and the output schema's
    `Published` class at the far end. This one is the single construction site, and
    covers a caller that reached it without passing through the loader.

    Both bad shapes are quiet without it: a bare string is iterable, so it is walked
    character by character; a non-iterable raises a bare `TypeError` from inside a
    classification worker, mid-run.
    """

    def test_a_scalar_string_is_refused_rather_than_walked_character_by_character(self):
        # 'GRCh38' would otherwise report a real vocabulary term as one we lack, and
        # render as 'G || R || C || h || 3 || 8'.
        with pytest.raises(ValueError, match=r"published reference_assembly is str, not a list"):
            build_published({"data_modality": None, "reference_assembly": "GRCh38"}, "anvil/anvil15")

    def test_the_scalar_message_names_the_cause(self):
        with pytest.raises(ValueError, match=r"built before #424"):
            build_published({"data_modality": None, "reference_assembly": "GRCh38"}, None)

    def test_a_non_iterable_is_refused_instead_of_raising_a_bare_type_error(self):
        with pytest.raises(ValueError, match=r"published data_modality is int, not a list"):
            build_published({"data_modality": 12345, "reference_assembly": None}, None)

    def test_a_non_iterable_gets_no_invented_cause(self):
        # The pre-#424 spelling was a string; an int is drift with no story to tell.
        with pytest.raises(ValueError) as exc:
            build_published({"data_modality": 12345, "reference_assembly": None}, None)
        assert "#424" not in str(exc.value)

    def test_a_list_holding_a_non_string_is_refused(self):
        # It would survive the vocabulary check (a frozenset test just says False) and
        # then fail in the report, where the values are joined into a cell.
        with pytest.raises(ValueError, match=r"holds a non-string value"):
            build_published({"data_modality": ["genomic", 7], "reference_assembly": None}, None)

    def test_the_shapes_a_rebuilt_snapshot_actually_produces_are_accepted(self):
        assert build_published({"data_modality": None, "reference_assembly": None}, None) is None
        block = build_published({"data_modality": ["genomic"], "reference_assembly": ["GRCh38"]}, "anvil/anvil15")
        assert block is not None
        assert block["in_vocabulary"] == {"data_modality": ["genomic"], "reference_assembly": ["GRCh38"]}


def test_the_dataset_table_omits_datasets_with_nothing_published(tmp_path):
    """The per-dataset table is about published values, so a dataset with none is out.

    Regression: the filter once read `add` out of RECOMMENDATIONS by position, so
    reordering that tuple to lead with `add` silently let every dataset through — a
    presentation change altering which rows a report contains.
    """
    published = build_published({"data_modality": None, "reference_assembly": ["GRCm39"]}, "anvil/anvil15")
    run = _write_run(
        tmp_path / "run",
        [
            _record("published.bam", dataset="HAS_PUBLISHED", published=published),
            _record("silent.bam", dataset="NO_PUBLISHED", modality="genomic", assembly="GRCh38"),
        ],
    )
    text = render_report(gather(run))
    dataset_table = text[text.index("## By dataset") : text.index("## Vocabulary coverage")]
    assert "HAS_PUBLISHED" in dataset_table
    assert "NO_PUBLISHED" not in dataset_table


def test_the_pipeline_carries_the_catalog_into_a_written_record(tmp_path):
    """`ClassifyPipeline`, end to end: input envelope -> written record's `published`.

    The one producer the sweep above cannot cover, and the one whose propagation runs
    through mutable state: `_load_input` sets `self.published_source` as a side effect,
    and `_build_record` reads it later. Nothing else pins that. `test_pipeline.py`'s
    nearest test asserts only the negative (`published is None` on a pipeline that never
    loaded an input), and the golden fixture is built from an envelope with no catalog
    and no published values, so every golden record is `published: null`.

    Written against the real `run()` rather than the private steps, so a regression in
    where the source is read, when it is set, or whether it reaches the envelope fails
    here rather than only in a corpus run.
    """
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from test_pipeline import _make_config, _valid_record

    record = _valid_record(
        file_md5sum="a" * 32,
        file_name="sample.test",
        file_format=".test",
        entry_id="e1",
        data_modality=["single-nucleus ATAC-seq"],
        reference_assembly=["GRCm39"],
    )
    input_path = tmp_path / "in.json"
    input_path.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": [record]}))
    output_path = tmp_path / "out.json"

    pipeline = ClassifyPipeline(
        _make_config(), input_path, output_path, evidence_base=tmp_path / "evidence", resume=False
    )
    [written] = pipeline.run()

    assert written["published"] == {
        "source": "anvil/anvil15",
        "data_modality": ["single-nucleus ATAC-seq"],
        "reference_assembly": ["GRCm39"],
        "in_vocabulary": {"data_modality": [], "reference_assembly": []},
    }


def test_the_pipeline_leaves_the_repository_unnamed_when_the_envelope_has_no_catalog(tmp_path):
    """An `.ndjson` input carries no envelope, so there is no catalog to name.

    Pairs with the test above: it is the same propagation path proving it reports
    `None` rather than inventing a catalog, which is the whole point of
    `published_source` returning None (contract 7.1's `source`, and #335's drift rule).
    """
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from test_pipeline import _make_config, _valid_record

    record = _valid_record(
        file_md5sum="a" * 32,
        file_name="sample.test",
        file_format=".test",
        entry_id="e1",
        data_modality=["single-nucleus ATAC-seq"],
    )
    input_path = tmp_path / "in.ndjson"
    input_path.write_text(json.dumps(record) + "\n")

    pipeline = ClassifyPipeline(
        _make_config(), input_path, tmp_path / "out.json", evidence_base=tmp_path / "evidence", resume=False
    )
    [written] = pipeline.run()

    assert written["published"]["source"] is None
    assert written["published"]["data_modality"] == ["single-nucleus ATAC-seq"]


def test_the_review_preamble_follows_the_vocabulary_table(tmp_path):
    """The sentence about unmapped strings is derived, not asserted.

    Every other figure in the report is computed from the run. This one used to state
    outright that no published value is a term the schema knows — true of today's
    corpus, and a claim that would contradict the vocabulary table printed two sections
    above it the day #414 lands a term.
    """
    unknown = build_published({"data_modality": None, "reference_assembly": ["GRCm39"]}, "anvil/anvil15")
    run = _write_run(tmp_path / "unknown", [_record("m.bam", assembly="GRCh38", published=unknown)])
    assert "None of the published values above is a term the schema knows" in render_report(gather(run))

    # `GRCh38` *is* a reference_assembly_enum term, so the report must not say otherwise.
    known = build_published({"data_modality": None, "reference_assembly": ["GRCh38"]}, "anvil/anvil15")
    run = _write_run(tmp_path / "known", [_record("k.bam", assembly="GRCh38", published=known)])
    text = render_report(gather(run))
    assert "None of the published values above is a term the schema knows" not in text
    assert "1 of 1 published values *are* terms the schema knows" in text


def test_a_tab_in_a_published_value_does_not_break_the_tsv(tmp_path):
    """Published values are verbatim (contract 7.3), so they are not tab-free by contract.

    No value in the corpus contains a tab today. The point is that the file's validity
    should not depend on that staying true: joining on tabs would turn one such value
    into an extra column, silently, for every consumer of the export.
    """
    import csv
    import io

    published = build_published({"data_modality": ["has\ttab"], "reference_assembly": None}, "anvil/anvil15")
    run = _write_run(tmp_path / "run", [_record("t.bam", published=published)])
    text = render_tsv(gather(run))

    rows = list(csv.reader(io.StringIO(text), delimiter="\t"))
    assert len(rows) == 2, "the tab must not have split the row"
    assert len(rows[1]) == len(TSV_HEADER)
    assert rows[1][5] == "has\ttab", "and the value must survive verbatim"


def test_the_load_boundary_refuses_a_snapshot_before_any_record_is_processed(tmp_path):
    """A bad published shape stops the run, rather than deleting rows one at a time.

    `build_published` also refuses it, but on the pipeline path that raise happens inside
    a worker, and `_run_parallel` catches every worker exception and writes no row — so
    the file would vanish while the run reported success. Refusing at load is what makes
    "the snapshot is refused" true.
    """
    good = valid_record(file_name="a.test", file_format=".test", entry_id="ok", reference_assembly=["GRCh38"])
    bad = valid_record(file_name="b.test", file_format=".test", entry_id="drifted", data_modality="genomic")
    path = tmp_path / "in.json"
    path.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": [good, bad]}))

    with pytest.raises(ValueError) as exc:
        load_classifiable_snapshot(path)
    message = str(exc.value)
    assert "1 record(s)" in message
    assert "drifted" in message, "the offending record is named"
    assert "rebuild it with" in message


def test_the_load_boundary_refuses_a_non_string_inside_a_list(tmp_path):
    """The loader must refuse everything `build_published` refuses, not just the outer shape.

    A list holding a non-string passed the outer-shape check, then raised in a worker —
    where `_run_parallel` swallows it and writes no row. So the record disappeared while
    the run reported success: the exact failure the load-boundary check exists to close,
    reintroduced through the half of the shape it did not check.
    """
    bad = valid_record(file_name="b.test", file_format=".test", entry_id="drifted", data_modality=["genomic", 123])
    path = tmp_path / "in.json"
    path.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": [bad]}))

    with pytest.raises(ValueError, match=r"holds a non-string value"):
        load_classifiable_snapshot(path)


def test_the_refusal_counts_records_and_fields_separately(tmp_path):
    """One record wrong on both dimensions is one record, not two.

    The count is the operator's measure of how much of the snapshot is bad, so counting
    fields as records would overstate it — by exactly a factor of two on the shape this
    is most likely to meet, a pre-#424 snapshot where both dimensions are scalars.
    """
    bad = valid_record(
        file_name="b.test",
        file_format=".test",
        entry_id="drifted",
        data_modality="genomic",
        reference_assembly="GRCh38",
    )
    path = tmp_path / "in.json"
    path.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": [bad]}))

    with pytest.raises(ValueError) as exc:
        load_classifiable_snapshot(path)
    assert "1 record(s), 2 field(s)" in str(exc.value)


def test_a_backtick_in_a_published_value_does_not_break_the_table():
    """Published values are verbatim (7.3), so a backtick is possible and would spill.

    A single-backtick span is terminated by the first backtick in its content, so the
    rest of the value would land in the table as markup. CommonMark fences with any run
    not present in the content; `_code` picks one longer than the longest run inside.
    """
    from meta_disco.published_comparison import _code

    assert _code("plain") == "`plain`"
    # A backtick inside needs a longer fence.
    assert _code("has`tick") == "``has`tick``"
    # A run of two needs three.
    assert _code("has``run") == "```has``run```"
    # Leading or trailing backticks additionally need padding, which the reader strips.
    assert _code("`edge`") == "`` `edge` ``"


def test_a_pipe_in_a_published_value_is_escaped_once_not_twice():
    """`md_table` escapes the pipe and GFM processes that escape inside a code span.

    Escaping it again in `_code` would put a visible backslash in the rendered cell. The
    corpus's twelve multi-valued cells all take this path, so getting it wrong would be
    visible on every one of them.
    """
    from meta_disco.published_comparison import _code
    from meta_disco.summaries import md_table

    assert _code("a || b") == "`a || b`", "the code span itself must not escape"
    [_header, _rule, row] = md_table(["v"], [[_code("a || b")]])
    # Exactly once. GitHub's renderer turns this row into
    # `<td><code>a || b</code></td>` — checked against its /markdown API, not inferred,
    # because "the report shows backslashes" has been reported three times and is wrong.
    assert r"\|\|" in row, "md_table escapes it exactly once, which GFM then unescapes"
    assert r"\\|" not in row, "escaping twice is what would show a backslash in the cell"


def test_a_checksum_less_record_is_excluded_rather_than_refusing_the_run(tmp_path):
    """The shape check sees classifiable records only, and that ordering is deliberate.

    A record with no usable checksum produces no output row whatever its shape (#376)
    and is named in `excluded_files.json`, so a bad published value on one can lose
    nothing. Refusing the run over it would block a snapshot that classifies correctly.
    """
    good = valid_record(file_name="a.test", file_format=".test", entry_id="ok", reference_assembly=["GRCh38"])
    excluded = valid_record(file_name="b.test", file_format=".test", entry_id="no-md5", data_modality="genomic")
    excluded["file_md5sum"] = None
    path = tmp_path / "in.json"
    path.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": [good, excluded]}))

    source, records = load_classifiable_snapshot(path)
    assert source == "anvil/anvil15"
    assert [r["entry_id"] for r in records] == ["ok"], "the drifted record was excluded, not refused"


def test_an_empty_element_is_refused_by_both_gates(tmp_path):
    """The reader and the constructor must agree on what an empty element means.

    `azul_manifest._published` drops empty elements, so a manifest cell of nothing but
    separators arrives as no published value at all. A list holding one therefore did not
    come from that reader, and counting it would put a blank in the comparison as though
    the repository had published something. Refused rather than dropped: silently
    transforming a value in the constructor is what `_first()` did wrong.
    """
    from meta_disco import azul_manifest

    assert azul_manifest._published(" || ") is None, "the reader treats it as nothing"

    with pytest.raises(ValueError, match=r"holds an empty value"):
        build_published({"data_modality": [""], "reference_assembly": None}, "anvil/anvil15")

    # `all([])` is True, so an empty list slips past the check above and needs its own.
    # Left accepted, it emits `[]` beside a real list — where both the reader and this
    # block spell an absent dimension `null` — and when both dimensions are empty the
    # block collapses to None, swallowing the malformed shape entirely.
    assert all([]) is True, "the reason this needs a separate check"
    with pytest.raises(ValueError, match=r"is an empty list"):
        build_published({"data_modality": [], "reference_assembly": ["GRCh38"]}, "anvil/anvil15")
    with pytest.raises(ValueError, match=r"is an empty list"):
        build_published({"data_modality": [], "reference_assembly": []}, "anvil/anvil15")

    envelope = {"repository": "anvil", "catalog": "anvil15"}
    for value, expected in (([""], r"holds an empty value"), ([], r"is an empty list")):
        bad = valid_record(file_name="b.test", file_format=".test", entry_id="blank", data_modality=value)
        path = tmp_path / f"in{len(value)}.json"
        path.write_text(json.dumps({"metadata": envelope, "files": [bad]}))
        with pytest.raises(ValueError, match=expected):
            load_classifiable_snapshot(path)


def test_two_entry_ids_whose_string_forms_coincide_are_distinct_files(tmp_path):
    """`entry_id` is not classifier-relevant, so type drift on it reaches `gather`.

    `str()` alone maps the int 1 and the string "1" to one key, so two distinct files
    would dedupe into one and the comparison would undercount. The key is type-tagged
    for that, and stringified within the tag because the value is not guaranteed
    hashable either — an `InvalidRecord` echoes a drifted list or dict un-coerced.
    """
    published = build_published({"data_modality": None, "reference_assembly": ["GRCm39"]}, "anvil/anvil15")
    twins = []
    for entry in (1, "1"):
        rec = _record("same.bam", published=published)
        rec["entry_id"], rec["md5sum"] = entry, "shared-md5"
        twins.append(rec)
    report = gather(_write_run(tmp_path / "run", twins))

    assert report.files == 2, "an int and a string entry_id are different files"
    assert report.duplicate_records == 0
    assert report.published_files == 2


def test_an_unhashable_entry_id_does_not_raise(tmp_path):
    """The reason the key is stringified inside the tag rather than kept raw."""
    published = build_published({"data_modality": None, "reference_assembly": ["GRCm39"]}, "anvil/anvil15")
    rec = _record("drifted.bam", published=published)
    rec["entry_id"] = ["a", "list"]
    report = gather(_write_run(tmp_path / "run", [rec]))
    assert report.files == 1
    assert report.rows[0].entry_id == "['a', 'list']"
