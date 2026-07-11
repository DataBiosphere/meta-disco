"""Tests for the shared ClassifyPipeline infrastructure."""

import json
from pathlib import Path

import pytest

from meta_disco.pipeline import ClassifyPipeline, FileTypeConfig, NdjsonWriter

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
        {"file_md5sum": "abc123", "file_name": "sample.test", "file_size": 1000,
         "file_format": ".test", "entry_id": "e1"},
        {"file_md5sum": "def456", "file_name": "sample2.test", "file_size": 2000,
         "file_format": ".test", "entry_id": "e2"},
        {"file_md5sum": "ghi789", "file_name": "other.bam", "file_size": 3000,
         "file_format": ".bam", "entry_id": "e3"},
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

    def test_skips_without_md5(self, tmp_path):
        records = [{"file_name": "foo.test", "file_format": ".test"}]
        path = tmp_path / "in.json"
        path.write_text(json.dumps({"results": records}))
        config = _make_config()
        pipeline = ClassifyPipeline(config, path, tmp_path / "out.json")
        filtered = pipeline._filter_records(pipeline._load_input())
        assert len(filtered) == 0

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
            config, input_file, output,
            evidence_base=tmp_path / "evidence",
        )
        results = pipeline.run()

        assert len(results) == 2  # Only .test files, not .bam
        assert output.exists()

        with open(output) as f:
            data = json.load(f)
        assert data["metadata"]["successful"] == 2
        assert data["metadata"]["complete"] is True
        assert len(data["classifications"]) == 2

    def test_limit(self, input_file, tmp_path):
        config = _make_config()
        output = tmp_path / "out.json"
        pipeline = ClassifyPipeline(
            config, input_file, output, limit=1,
            evidence_base=tmp_path / "evidence",
        )
        results = pipeline.run()
        assert len(results) == 1

    def test_fetcher_returns_none(self, input_file, tmp_path):
        """Files where fetcher returns None are counted as failures."""
        config = _make_config(fetcher=lambda evidence_dir, md5, **kw: None)
        output = tmp_path / "out.json"
        pipeline = ClassifyPipeline(
            config, input_file, output,
            evidence_base=tmp_path / "evidence",
        )
        results = pipeline.run()
        assert len(results) == 0

        with open(output) as f:
            data = json.load(f)
        assert data["metadata"]["failed"] == 2

    @pytest.mark.parametrize("workers", [1, 2])
    def test_null_file_name_does_not_crash_or_lose_the_record(self, tmp_path, workers):
        """`record.get("file_name", "")` returns None for a present-but-null key, and
        _filter_records admits such a record when its file_format matches.

        Sequentially that aborted the run. In the parallel path it was worse: the
        raise landed in the executor's `except Exception`, so a record that had
        classified successfully was counted as errored and never written.
        """
        config = _make_config()
        input_path = tmp_path / "in.json"
        input_path.write_text(json.dumps({"results": [
            {"file_md5sum": "n1", "file_name": None, "file_format": ".test"},
        ]}))
        output = tmp_path / "out.json"
        results = ClassifyPipeline(
            config, input_path, output,
            evidence_base=tmp_path / "evidence", workers=workers,
        ).run()

        assert len(results) == 1, "the record must be classified, not dropped"
        meta = json.loads(output.read_text())["metadata"]
        assert meta["successful"] == 1
        assert meta["errored"] == 0
        assert meta["failed"] == 0

    def test_parallel_workers(self, input_file, tmp_path):
        config = _make_config()
        output = tmp_path / "out.json"
        pipeline = ClassifyPipeline(
            config, input_file, output, workers=2,
            evidence_base=tmp_path / "evidence",
        )
        results = pipeline.run()
        assert len(results) == 2

    def test_classify_single(self, tmp_path):
        config = _make_config()
        result = ClassifyPipeline.classify_single(
            config, "test_md5", file_name="sample.test",
            evidence_base=tmp_path / "evidence",
        )
        assert result is not None
        assert result["md5sum"] == "test_md5"
        assert "classifications" in result

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
            {"file_md5sum": "a", "file_name": "x.test.gz", "file_format": ".test"},
            {"file_md5sum": "b", "file_name": "y.test", "file_format": ".test"},
        ]
        path = tmp_path / "in.json"
        path.write_text(json.dumps({"results": records}))
        pipeline = ClassifyPipeline(
            config, path, tmp_path / "out.json",
            evidence_base=tmp_path / "evidence",
        )
        pipeline.run()
        assert True in calls   # .gz file
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
        input_path.write_text(json.dumps({"results": [{
            "file_md5sum": "deadbeef", "file_name": file_name,
            "file_format": file_format, "file_size": 10, "entry_id": "e1",
        }]}))
        return ClassifyPipeline(
            config, input_path, tmp_path / "out.json",
            evidence_base=tmp_path / "evidence", workers=1,
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
        assert not [e for e in cls["reference_assembly"]["evidence"]
                    if e["rule_id"] == "fetch_failed"]

    def test_fetch_error_on_mc_graph_keeps_the_filename_refinement(self, tmp_path):
        """The `-mc-` token still refines data_type even though content is unreadable."""
        results = self._run_with_failing_fetcher(
            tmp_path, "hprc-v1.0-mc-grch38.gfa.gz", ".gfa.gz"
        )
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
        record = {"file_md5sum": "deadbeef", "file_name": "hprc-v1.0-mc-grch38.gfa.gz",
                  "file_format": ".gfa.gz", "file_size": 10}
        input_path = tmp_path / "in.json"
        input_path.write_text(json.dumps({"results": [record]}))

        pipeline = ClassifyPipeline(
            config, input_path, tmp_path / "out.json",
            evidence_base=tmp_path / "evidence", workers=1, resume=True,
        )
        # A corrupt evidence file: _is_cached() sees it, load_cached_evidence() cannot
        # read it, so the fetcher re-fetches and fails.
        stale = get_evidence_path(pipeline.evidence_dir, "deadbeef")
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("{ not json")

        out, was_cached, content_unreadable = pipeline._process_single_record(record)

        assert content_unreadable is True
        assert was_cached is False, "a fetch that reached the network is not a cache hit"
        # The note is on data_type (what content refines), not on the four others.
        cls = out["classifications"]
        noted = [f for f in cls
                 if any(e["rule_id"] == "fetch_failed" for e in cls[f]["evidence"])]
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
        input_path.write_text(json.dumps({"results": [
            {"file_md5sum": "a1", "file_name": "hprc-v1.0-mc-grch38.gfa.gz",
             "file_format": ".gfa.gz"},
            {"file_md5sum": "b2", "file_name": "HG002.hap1.p_ctg.gfa", "file_format": ".gfa"},
        ]}))
        out_path = tmp_path / "out.json"
        ClassifyPipeline(config, input_path, out_path,
                         evidence_base=tmp_path / "evidence", workers=1,
                         resume=False).run()

        meta = json.loads(out_path.read_text())["metadata"]
        assert meta["content_unreadable"] == 2
        assert meta["from_cache"] == 0
        assert meta["successful"] == 2

    def test_dropped_and_errored_are_counted_separately(self, tmp_path):
        """`Dropped (fetcher gave no cause)` must not absorb records whose worker
        raised and printed a cause. `failed` stays the sum, for existing consumers."""
        import dataclasses

        from meta_disco.file_types import FILE_TYPE_REGISTRY
        from meta_disco.pipeline import ClassifyPipeline

        def _explode(evidence_dir, md5, **kwargs):
            if md5 == "boom":
                raise TypeError("a bug in the parser, not a fetch failure")
            return None  # silent drop, no cause

        config = dataclasses.replace(FILE_TYPE_REGISTRY["gfa"], fetcher=_explode)
        input_path = tmp_path / "in.json"
        input_path.write_text(json.dumps({"results": [
            {"file_md5sum": "boom", "file_name": "a.gfa", "file_format": ".gfa"},
            {"file_md5sum": "quiet", "file_name": "b.gfa", "file_format": ".gfa"},
        ]}))
        out_path = tmp_path / "out.json"
        # workers>1 so the executor's `except Exception` handles the TypeError.
        ClassifyPipeline(config, input_path, out_path,
                         evidence_base=tmp_path / "evidence", workers=2,
                         resume=False).run()

        meta = json.loads(out_path.read_text())["metadata"]
        assert meta["dropped"] == 1, "the None-returning fetcher"
        assert meta["errored"] == 1, "the raising fetcher"
        assert meta["failed"] == 2, "kept as the sum for existing consumers"
        assert meta["successful"] == 0

    def test_fetcher_returning_none_still_drops_the_row(self, tmp_path):
        """Unchanged for the fetchers that give no cause (see #155)."""
        import dataclasses

        from meta_disco.file_types import FILE_TYPE_REGISTRY
        from meta_disco.pipeline import ClassifyPipeline

        config = dataclasses.replace(
            FILE_TYPE_REGISTRY["gfa"], fetcher=lambda evidence_dir, md5, **kw: None
        )
        input_path = tmp_path / "in.json"
        input_path.write_text(json.dumps({"results": [
            {"file_md5sum": "d", "file_name": "graph.gfa", "file_format": ".gfa"}
        ]}))
        pipeline = ClassifyPipeline(
            config, input_path, tmp_path / "out.json",
            evidence_base=tmp_path / "evidence", workers=1,
        )
        assert pipeline.run() == []

    def test_configs_have_required_fields(self):
        from meta_disco.file_types import FILE_TYPE_REGISTRY
        for name, config in FILE_TYPE_REGISTRY.items():
            assert config.name == name
            assert len(config.extensions) > 0
            assert callable(config.fetcher)
            assert callable(config.classifier)
