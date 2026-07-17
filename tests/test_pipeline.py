"""Tests for the shared ClassifyPipeline infrastructure."""

import json
from pathlib import Path

import pytest

from meta_disco.pipeline import ClassifyPipeline, FileTypeConfig, NdjsonWriter
from meta_disco.records import ClassifierRecord, InvalidRecord
from tests.metadata_fixtures import valid_record as _valid_record

# --- Test fixtures ---


def _make_config(**overrides):
    """Create a FileTypeConfig with test defaults."""
    defaults = {
        "name": "test",
        "extensions": (".test",),
        "fetcher": lambda evidence_dir, md5, **kw: f"header_for_{md5}",
        "classifier": lambda raw_data, **kw: {"data_modality": {"value": "genomic"}},
    }
    defaults.update(overrides)
    return FileTypeConfig(**defaults)


@pytest.fixture
def input_file(tmp_path):
    """Create a test input JSON file with records."""
    records = [
        _valid_record(file_md5sum="a" * 32, file_name="sample.test", file_format=".test", entry_id="e1"),
        _valid_record(file_md5sum="b" * 32, file_name="sample2.test", file_format=".test", entry_id="e2"),
        _valid_record(file_md5sum="c" * 32, file_name="other.bam", file_format=".bam", entry_id="e3"),
    ]
    path = tmp_path / "input.json"
    path.write_text(json.dumps({"results": records}))
    return path


@pytest.fixture
def ndjson_input(tmp_path):
    """Create a test NDJSON input file."""
    records = [
        {"file_md5sum": "abc123", "file_name": "s.test", "file_format": ".test"},
    ]
    path = tmp_path / "input.ndjson"
    path.write_text("\n".join(json.dumps(r) for r in records))
    return path


# --- NdjsonWriter tests ---


class TestNdjsonWriter:
    def test_write_and_close(self, tmp_path):
        output = tmp_path / "out.json"
        writer = NdjsonWriter(output)
        writer.write({"a": 1})
        writer.write({"b": 2})
        writer.close()

        ndjson = output.with_suffix(".ndjson")
        lines = ndjson.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1}
        assert json.loads(lines[1]) == {"b": 2}


# --- Pipeline filter tests ---


class TestFilterRecords:
    def test_filters_by_extension(self, input_file, tmp_path):
        config = _make_config()
        pipeline = ClassifyPipeline(config, input_file, tmp_path / "out.json")
        records = pipeline._load_input()
        filtered = pipeline._filter_records(records)
        assert len(filtered) == 2
        assert all(r["file_format"] == ".test" for r in filtered)

    def test_filters_by_filename(self, tmp_path):
        records = [{"file_md5sum": "x", "file_name": "foo.test"}]
        path = tmp_path / "in.json"
        path.write_text(json.dumps({"results": records}))
        config = _make_config()
        pipeline = ClassifyPipeline(config, path, tmp_path / "out.json")
        filtered = pipeline._filter_records(pipeline._load_input())
        assert len(filtered) == 1

    def test_missing_md5_is_routed_not_dropped(self, tmp_path):
        # md5 is classifier-relevant: an extension-matching record with no md5 must
        # reach processing (to be written as validation_failed), not be filtered out.
        records = [{"file_name": "foo.test", "file_format": ".test"}]
        path = tmp_path / "in.json"
        path.write_text(json.dumps({"results": records}))
        config = _make_config()
        pipeline = ClassifyPipeline(config, path, tmp_path / "out.json")
        filtered = pipeline._filter_records(pipeline._load_input())
        assert len(filtered) == 1

    def test_non_dict_record_is_filtered_out_without_crashing(self, tmp_path):
        records = ["a bare string", None, {"file_name": "ok.test", "file_format": ".test"}]
        path = tmp_path / "in.json"
        path.write_text(json.dumps({"results": records}))
        config = _make_config()
        pipeline = ClassifyPipeline(config, path, tmp_path / "out.json")
        filtered = pipeline._filter_records(pipeline._load_input())
        assert filtered == [{"file_name": "ok.test", "file_format": ".test"}]

    def test_skips_flagged(self, tmp_path):
        records = [{"file_md5sum": "x", "file_name": "foo.test", "skip": True}]
        path = tmp_path / "in.json"
        path.write_text(json.dumps({"results": records}))
        config = _make_config()
        pipeline = ClassifyPipeline(config, path, tmp_path / "out.json")
        filtered = pipeline._filter_records(pipeline._load_input())
        assert len(filtered) == 0

    def test_loads_ndjson(self, ndjson_input, tmp_path):
        config = _make_config()
        pipeline = ClassifyPipeline(config, ndjson_input, tmp_path / "out.json")
        records = pipeline._load_input()
        assert len(records) == 1


# --- Pipeline run tests ---


class TestPipelineRun:
    def test_full_run(self, input_file, tmp_path):
        config = _make_config()
        output = tmp_path / "out.json"
        pipeline = ClassifyPipeline(
            config,
            input_file,
            output,
            evidence_base=tmp_path / "evidence",
        )
        results = pipeline.run()

        assert len(results) == 2  # Only .test files, not .bam
        assert output.exists()

        with output.open() as f:
            data = json.load(f)
        assert data["metadata"]["successful"] == 2
        assert data["metadata"]["complete"] is True
        assert len(data["classifications"]) == 2

    def test_limit(self, input_file, tmp_path):
        config = _make_config()
        output = tmp_path / "out.json"
        pipeline = ClassifyPipeline(
            config,
            input_file,
            output,
            limit=1,
            evidence_base=tmp_path / "evidence",
        )
        results = pipeline.run()
        assert len(results) == 1

    def test_fetch_failure_writes_not_classified_row_never_dropped(self, input_file, tmp_path):
        """A fetcher that raises FetchError keeps the record as a content_unreadable
        row (classified from the filename), never dropped (#155)."""
        from meta_disco.fetchers import FetchError

        def _boom(evidence_dir, md5, **kw):
            raise FetchError("HTTP 404 from AnVIL S3 mirror range request")

        config = _make_config(fetcher=_boom)
        output = tmp_path / "out.json"
        pipeline = ClassifyPipeline(config, input_file, output, evidence_base=tmp_path / "evidence")
        results = pipeline.run()
        assert len(results) == 2  # both .test files written, none dropped

        data = json.loads(output.read_text())
        assert data["metadata"]["dropped"] == 0
        assert data["metadata"]["failed"] == 0
        assert data["metadata"]["content_unreadable"] == 2

    @pytest.mark.parametrize("workers", [1, 2])
    def test_null_file_name_is_written_as_validation_failed_not_lost(self, tmp_path, workers):
        """A present-but-null file_name is a contract violation (issue #161): the
        record is diverted to validation_failed and written, never dropped and never
        crashing the run.

        This is the same protection #151 gave — the record survives in both the
        sequential and parallel paths (a raise in the parallel path had landed in the
        executor's `except Exception` and discarded the record) — now via validation.
        """
        config = _make_config()
        input_path = tmp_path / "in.json"
        input_path.write_text(
            json.dumps(
                {
                    "results": [
                        _valid_record(file_name=None, file_format=".test"),
                    ]
                }
            )
        )
        output = tmp_path / "out.json"
        results = ClassifyPipeline(
            config,
            input_path,
            output,
            evidence_base=tmp_path / "evidence",
            workers=workers,
        ).run()

        assert len(results) == 1, "the record must be written, not dropped"
        meta = json.loads(output.read_text())["metadata"]
        assert meta["validation_failed"] == 1
        assert meta["processed"] == 1
        assert meta["successful"] == 0
        assert meta["errored"] == 0
        assert meta["failed"] == 0
        # Written with every dimension not_classified, carrying the reason.
        cls = results[0]["classifications"]
        assert all(cls[f]["status"] == "not_classified" for f in cls)
        reasons = [e["reason"] for e in cls["data_modality"]["evidence"]]
        assert any("file_name" in r for r in reasons)

    @pytest.mark.parametrize("workers", [1, 2])
    def test_bad_classifier_irrelevant_field_still_classifies(self, tmp_path, workers):
        """A contract violation on a field the classifier never reads (here a
        non-boolean is_supplementary) must NOT divert the record — it classifies
        normally. Only classifier-relevant violations block (issue #161 split)."""
        config = _make_config()
        input_path = tmp_path / "in.json"
        input_path.write_text(
            json.dumps(
                {
                    "results": [
                        _valid_record(file_name="ok.test", file_format=".test", is_supplementary="not-a-bool"),
                    ]
                }
            )
        )
        output = tmp_path / "out.json"
        results = ClassifyPipeline(
            config,
            input_path,
            output,
            evidence_base=tmp_path / "evidence",
            workers=workers,
        ).run()

        assert len(results) == 1
        meta = json.loads(output.read_text())["metadata"]
        assert meta["validation_failed"] == 0
        assert meta["successful"] == 1
        assert results[0]["classifications"]["data_modality"]["value"] == "genomic"

    def test_missing_md5_record_is_written_as_validation_failed(self, tmp_path):
        """A record routed by extension but missing md5 (classifier-relevant) is
        written as validation_failed through a full run, not dropped (#155/#161)."""
        config = _make_config()
        input_path = tmp_path / "in.json"
        input_path.write_text(
            json.dumps(
                {
                    "results": [
                        _valid_record(file_name="x.test", file_format=".test", file_md5sum=None),
                    ]
                }
            )
        )
        output = tmp_path / "out.json"
        results = ClassifyPipeline(
            config,
            input_path,
            output,
            evidence_base=tmp_path / "evidence",
        ).run()

        assert len(results) == 1
        meta = json.loads(output.read_text())["metadata"]
        assert meta["validation_failed"] == 1
        assert meta["successful"] == 0
        reasons = [e["reason"] for e in results[0]["classifications"]["data_modality"]["evidence"]]
        assert any("file_md5sum" in r for r in reasons)

    def test_skip_cached_keeps_invalid_records_and_tolerates_unhashable_md5(self, tmp_path):
        """skip_cached must not drop validation_failed records (they are never cached)
        and must not crash on an InvalidRecord whose md5 drifted to an unhashable
        type — only classifiable records are skip-filtered against the cached set."""
        from meta_disco.fetchers import get_evidence_path

        cached_md5 = "a" * 32
        valid = _valid_record(file_md5sum=cached_md5, file_name="v.test", file_format=".test")
        # Blocking drift (non-int file_size) + an unhashable md5 (a list).
        invalid = _valid_record(file_name="i.test", file_format=".test", file_size="big", file_md5sum=["x"])
        input_path = tmp_path / "in.json"
        input_path.write_text(json.dumps({"results": [valid, invalid]}))

        pipeline = ClassifyPipeline(
            _make_config(),
            input_path,
            tmp_path / "out.json",
            evidence_base=tmp_path / "evidence",
            resume=True,
            skip_cached=True,
            workers=1,
        )
        ev = get_evidence_path(pipeline.evidence_dir, cached_md5)
        ev.parent.mkdir(parents=True, exist_ok=True)
        ev.write_text("{}")

        results = pipeline.run()  # must not raise on the unhashable md5

        names = [r["file_name"] for r in results]
        assert "v.test" not in names  # cached classifiable record is skipped
        assert "i.test" in names  # validation_failed record is still written
        meta = json.loads((tmp_path / "out.json").read_text())["metadata"]
        assert meta["validation_failed"] == 1

    def test_preflight_aborts_before_processing(self, input_file, tmp_path):
        """A failing preflight (e.g. a missing external tool) aborts run() before the
        worker pool, so no output is written — a missing dependency fails fast instead
        of every record failing and vanishing (#155)."""

        def _boom():
            raise RuntimeError("samtools not found")

        config = _make_config(preflight=_boom)
        output = tmp_path / "out.json"
        pipeline = ClassifyPipeline(config, input_file, output, evidence_base=tmp_path / "evidence")
        with pytest.raises(RuntimeError, match="samtools not found"):
            pipeline.run()
        assert not output.exists()

    def test_preflight_skipped_when_work_is_all_invalid(self, tmp_path):
        """The preflight guards a fetch-time dependency, so it must not fire when no
        record will reach the fetcher — e.g. work is entirely validation_failed."""

        def _boom():
            raise RuntimeError("samtools not found")

        config = _make_config(preflight=_boom)
        input_path = tmp_path / "in.json"
        # Drifted file_size -> InvalidRecord, diverted before any fetch.
        input_path.write_text(
            json.dumps({"results": [_valid_record(file_name="a.test", file_format=".test", file_size="big")]})
        )
        output = tmp_path / "out.json"
        results = ClassifyPipeline(config, input_path, output, evidence_base=tmp_path / "evidence").run()
        assert len(results) == 1  # written as validation_failed, not aborted
        assert json.loads(output.read_text())["metadata"]["validation_failed"] == 1

    def test_preflight_skipped_when_all_cached(self, tmp_path):
        """An all-cached resume run invokes no fetcher, so the preflight must not fire
        — the case CI hit (cached/stubbed run with no samtools installed)."""
        from meta_disco.fetchers import get_evidence_path

        def _boom():
            raise RuntimeError("samtools not found")

        md5 = "a" * 32
        pipeline = ClassifyPipeline(
            _make_config(preflight=_boom),
            tmp_path / "in.json",
            tmp_path / "out.json",
            evidence_base=tmp_path / "evidence",
            resume=True,
        )
        (tmp_path / "in.json").write_text(
            json.dumps({"results": [_valid_record(file_md5sum=md5, file_name="a.test", file_format=".test")]})
        )
        ev = get_evidence_path(pipeline.evidence_dir, md5)
        ev.parent.mkdir(parents=True, exist_ok=True)
        ev.write_text("{}")
        assert len(pipeline.run()) == 1  # must not raise despite the raising preflight

    def test_partition_routes_by_classifier_relevant_fields(self, tmp_path):
        """The load-boundary split (#172) preserves #161's divert rule: a contract
        violation only on a field the classifier never reads (drs_uri) still yields a
        ClassifierRecord and classifies; a violation on a classifier-relevant field
        (file_size) yields an InvalidRecord diverted to validation_failed."""
        pipeline = ClassifyPipeline(
            _make_config(),
            tmp_path / "in.json",
            tmp_path / "out.json",
            evidence_base=tmp_path / "evidence",
        )
        good = _valid_record(file_name="a.test", file_format=".test")
        non_classifier_drift = _valid_record(file_name="b.test", file_format=".test", drs_uri=123)
        classifier_drift = _valid_record(file_name="c.test", file_format=".test", file_size="big")

        work = pipeline._partition_records([good, non_classifier_drift, classifier_drift])

        assert isinstance(work[0], ClassifierRecord)
        assert isinstance(work[1], ClassifierRecord)  # drs_uri drift is not blocking
        assert isinstance(work[2], InvalidRecord)  # file_size drift is blocking
        assert any("file_size" in reason for reason in work[2].reasons)

    def test_build_record_echoes_typed_item_identity(self):
        # _build_record reads identity off the typed work item into an OutputRecord. On
        # the validation_failed path that is an InvalidRecord, which has already coerced
        # file_name/file_format to str, so the output types stay stable.
        item = InvalidRecord.from_record({"file_name": 123, "file_format": None, "file_md5sum": "x"}, [])
        out = ClassifyPipeline._build_record(item, {})
        assert out.file_name == "123"
        assert out.file_format == ""
        assert isinstance(out.file_name, str) and isinstance(out.file_format, str)

    @pytest.mark.parametrize("workers", [1, 2])
    def test_non_string_file_name_does_not_crash_progress(self, tmp_path, workers):
        """A non-string file_name (drift, e.g. an int) routes by its matching format,
        becomes validation_failed, and must not crash the progress label's slice."""
        config = _make_config()
        input_path = tmp_path / "in.json"
        input_path.write_text(
            json.dumps(
                {
                    "results": [
                        _valid_record(file_name=123, file_format=".test"),
                    ]
                }
            )
        )
        output = tmp_path / "out.json"
        results = ClassifyPipeline(
            config,
            input_path,
            output,
            evidence_base=tmp_path / "evidence",
            workers=workers,
        ).run()

        assert len(results) == 1
        meta = json.loads(output.read_text())["metadata"]
        assert meta["validation_failed"] == 1
        assert meta["errored"] == 0

    @pytest.mark.parametrize(
        "md5",
        [
            None,
            "",
            123,  # non-string / empty: no evidence path, must not raise
            "ABC",
            "0" * 31,  # too short / wrong shape
            "g" * 32,
            "A" * 32,  # non-hex / uppercase — not a contractual md5
        ],
    )
    def test_is_cached_returns_false_for_non_md5(self, tmp_path, md5):
        """Only a well-formed lowercase-hex md5 can be cached. A null/non-string value
        must not raise on ``md5[:2]``; a non-md5 string must not be treated as cached."""
        pipeline = ClassifyPipeline(
            _make_config(),
            tmp_path / "in.json",
            tmp_path / "out.json",
            evidence_base=tmp_path / "evidence",
        )
        assert pipeline._is_cached(md5) is False

    def test_parallel_workers(self, input_file, tmp_path):
        config = _make_config()
        output = tmp_path / "out.json"
        pipeline = ClassifyPipeline(
            config,
            input_file,
            output,
            workers=2,
            evidence_base=tmp_path / "evidence",
        )
        results = pipeline.run()
        assert len(results) == 2

    def test_classify_single(self, tmp_path):
        config = _make_config()
        result = ClassifyPipeline.classify_single(
            config,
            "test_md5",
            file_name="sample.test",
            evidence_base=tmp_path / "evidence",
        )
        assert result is not None
        assert result["md5sum"] == "test_md5"
        assert "classifications" in result
        # classify_single now emits the same canonical 7-key envelope as the batch path
        # (#204): dataset_title/entry_id are present (None) on the single-file path.
        assert set(result) == {
            "file_name",
            "md5sum",
            "file_size",
            "file_format",
            "dataset_title",
            "classifications",
            "entry_id",
        }
        assert result["dataset_title"] is None and result["entry_id"] is None

    def test_gzip_detection(self, tmp_path):
        """When extensions include .gz variants, is_gzipped is inferred from filename."""
        calls = []

        def tracking_fetcher(evidence_dir, md5, is_gzipped=True, **kw):
            calls.append(is_gzipped)
            return "header"

        config = _make_config(
            fetcher=tracking_fetcher,
            extensions=(".test", ".test.gz"),
        )
        records = [
            _valid_record(file_md5sum="a" * 32, file_name="x.test.gz", file_format=".test"),
            _valid_record(file_md5sum="b" * 32, file_name="y.test", file_format=".test"),
        ]
        path = tmp_path / "in.json"
        path.write_text(json.dumps({"results": records}))
        pipeline = ClassifyPipeline(
            config,
            path,
            tmp_path / "out.json",
            evidence_base=tmp_path / "evidence",
        )
        pipeline.run()
        assert True in calls  # .gz file
        assert False in calls  # non-.gz file


# --- File type config tests ---


class TestFileTypeConfigs:
    def test_all_configs_exist(self):
        from meta_disco.file_types import FILE_TYPE_REGISTRY

        assert set(FILE_TYPE_REGISTRY.keys()) == {"bam", "vcf", "fastq", "fasta", "gfa"}

    def _run_with_failing_fetcher(self, tmp_path, file_name, file_format):
        import dataclasses

        from meta_disco.fetchers import FetchError
        from meta_disco.file_types import FILE_TYPE_REGISTRY
        from meta_disco.pipeline import ClassifyPipeline

        def _boom(evidence_dir, md5, **kwargs):
            raise FetchError("HTTPError: 404 Not Found")

        config = dataclasses.replace(FILE_TYPE_REGISTRY["gfa"], fetcher=_boom)
        input_path = tmp_path / "in.json"
        input_path.write_text(
            json.dumps(
                {
                    "results": [
                        _valid_record(
                            file_md5sum="d" * 32,
                            file_name=file_name,
                            file_format=file_format,
                            file_size=10,
                            entry_id="e1",
                        )
                    ]
                }
            )
        )
        return ClassifyPipeline(
            config,
            input_path,
            tmp_path / "out.json",
            evidence_base=tmp_path / "evidence",
            workers=1,
        ).run()

    def test_fetch_error_keeps_the_row_and_what_the_filename_already_gave(self, tmp_path):
        """A dropped row is indistinguishable from a file that was never seen. But
        blanking every dimension is also wrong: `pangenome` is knowable from the
        extension without reading a byte. Only content-dependent fields go
        not_classified, annotated with the cause."""
        from meta_disco.models import CLASSIFIED, NOT_APPLICABLE, NOT_CLASSIFIED

        results = self._run_with_failing_fetcher(tmp_path, "graph.gfa", ".gfa")
        assert len(results) == 1, "the unreadable file must still appear in the output"
        cls = results[0]["classifications"]

        # Knowable from the extension alone — must survive a failed fetch.
        assert cls["data_type"]["value"] == "pangenome"
        assert cls["data_type"]["status"] == CLASSIFIED
        assert cls["data_modality"]["value"] == "genomic"
        assert cls["platform"]["status"] == NOT_APPLICABLE
        assert cls["assay_type"]["status"] == NOT_APPLICABLE

        # The note lands on the dimension GFA *content* determines (data_type,
        # which the unread rGFA tags might have refined to pangenome.reference).
        failed = [e for e in cls["data_type"]["evidence"] if e["rule_id"] == "fetch_failed"]
        assert [e["reason"] for e in failed] == ["HTTPError: 404 Not Found"]

        # NOT on reference_assembly: GFA content never determines it (no lengths
        # are parsed), so a note there would say a re-fetch could resolve an
        # assembly only the filename can supply.
        assert cls["reference_assembly"]["status"] == NOT_CLASSIFIED
        assert not [e for e in cls["reference_assembly"]["evidence"] if e["rule_id"] == "fetch_failed"]

    def test_fetch_error_on_mc_graph_keeps_the_filename_refinement(self, tmp_path):
        """The `-mc-` token still refines data_type even though content is unreadable."""
        results = self._run_with_failing_fetcher(tmp_path, "hprc-v1.0-mc-grch38.gfa.gz", ".gfa.gz")
        cls = results[0]["classifications"]
        assert cls["data_type"]["value"] == "pangenome.reference"
        assert cls["reference_assembly"]["value"] == "GRCh38"

    def test_fetch_error_reports_unreadable_and_never_counts_as_cached(self, tmp_path):
        """A fetcher raises only after its own cache check missed, so it went to the
        network. If a stale evidence file makes _is_cached True, the record must
        still be reported unreadable rather than tallied under 'From cache'."""
        import dataclasses

        from meta_disco.fetchers import FetchError, get_evidence_path
        from meta_disco.file_types import FILE_TYPE_REGISTRY
        from meta_disco.pipeline import ClassifyPipeline

        def _boom(evidence_dir, md5, **kwargs):
            raise FetchError("HTTP 404 from AnVIL S3 mirror range request")

        config = dataclasses.replace(FILE_TYPE_REGISTRY["gfa"], fetcher=_boom)
        record = _valid_record(
            file_md5sum="d" * 32, file_name="hprc-v1.0-mc-grch38.gfa.gz", file_format=".gfa.gz", file_size=10
        )
        input_path = tmp_path / "in.json"
        input_path.write_text(json.dumps({"results": [record]}))

        pipeline = ClassifyPipeline(
            config,
            input_path,
            tmp_path / "out.json",
            evidence_base=tmp_path / "evidence",
            workers=1,
            resume=True,
        )
        # A corrupt evidence file: _is_cached() sees it, load_cached_evidence() cannot
        # read it, so the fetcher re-fetches and fails.
        stale = get_evidence_path(pipeline.evidence_dir, "d" * 32)
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("{ not json")

        out, was_cached, content_unreadable, _validation_failed = pipeline._process_single_record(
            ClassifierRecord.from_record(record)
        )

        assert content_unreadable is True
        assert was_cached is False, "a fetch that reached the network is not a cache hit"
        assert out is not None
        # The note is on data_type (what content refines), not on the four others.
        cls = out.classifications
        noted = [f for f in cls if any(e["rule_id"] == "fetch_failed" for e in cls[f]["evidence"])]
        assert noted == ["data_type"]

    def test_unreadable_count_is_persisted_in_run_metadata(self, tmp_path):
        """from_cache is persisted; unreadable must be too, or a consumer cannot tell
        a filename-only fallback from a real content read."""
        import dataclasses

        from meta_disco.fetchers import FetchError
        from meta_disco.file_types import FILE_TYPE_REGISTRY
        from meta_disco.pipeline import ClassifyPipeline

        def _boom(evidence_dir, md5, **kwargs):
            raise FetchError("HTTP 404 from AnVIL S3 mirror range request")

        config = dataclasses.replace(FILE_TYPE_REGISTRY["gfa"], fetcher=_boom)
        input_path = tmp_path / "in.json"
        input_path.write_text(
            json.dumps(
                {
                    "results": [
                        _valid_record(
                            file_md5sum="a" * 32, file_name="hprc-v1.0-mc-grch38.gfa.gz", file_format=".gfa.gz"
                        ),
                        _valid_record(file_md5sum="b" * 32, file_name="HG002.hap1.p_ctg.gfa", file_format=".gfa"),
                    ]
                }
            )
        )
        out_path = tmp_path / "out.json"
        ClassifyPipeline(
            config, input_path, out_path, evidence_base=tmp_path / "evidence", workers=1, resume=False
        ).run()

        meta = json.loads(out_path.read_text())["metadata"]
        assert meta["content_unreadable"] == 2
        assert meta["from_cache"] == 0
        assert meta["successful"] == 2

    def test_fetcherror_is_unreadable_row_but_a_bug_is_errored(self, tmp_path):
        """A FetchError keeps the record as a content_unreadable row; a non-FetchError
        bug in a fetcher surfaces as errored (no row), not a silent drop. `dropped` is
        0 now that fetch failures are never dropped (#155); `failed` = dropped + errored."""
        import dataclasses

        from meta_disco.fetchers import FetchError
        from meta_disco.file_types import FILE_TYPE_REGISTRY
        from meta_disco.pipeline import ClassifyPipeline

        bug_md5 = "a" * 32

        def _fetch(evidence_dir, md5, **kwargs):
            if md5 == bug_md5:
                raise TypeError("a bug in the parser, not a fetch failure")
            raise FetchError("HTTP 404 from AnVIL S3 mirror range request")

        config = dataclasses.replace(FILE_TYPE_REGISTRY["gfa"], fetcher=_fetch)
        input_path = tmp_path / "in.json"
        input_path.write_text(
            json.dumps(
                {
                    "results": [
                        _valid_record(file_md5sum=bug_md5, file_name="a.gfa", file_format=".gfa"),
                        _valid_record(file_md5sum="b" * 32, file_name="b.gfa", file_format=".gfa"),
                    ]
                }
            )
        )
        out_path = tmp_path / "out.json"
        # workers>1 so the executor's `except Exception` handles the TypeError.
        ClassifyPipeline(
            config, input_path, out_path, evidence_base=tmp_path / "evidence", workers=2, resume=False
        ).run()

        meta = json.loads(out_path.read_text())["metadata"]
        assert meta["dropped"] == 0, "fetch failures are no longer dropped (#155)"
        assert meta["errored"] == 1, "the TypeError bug — no row"
        assert meta["content_unreadable"] == 1, "the FetchError — written as not_classified"
        assert meta["successful"] == 1, "the content_unreadable row counts as written"
        assert meta["failed"] == 1, "dropped(0) + errored(1)"

    def test_configs_have_required_fields(self):
        from meta_disco.file_types import FILE_TYPE_REGISTRY

        for name, config in FILE_TYPE_REGISTRY.items():
            assert config.name == name
            assert len(config.extensions) > 0
            assert callable(config.fetcher)
            assert callable(config.classifier)
