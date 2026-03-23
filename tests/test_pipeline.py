"""Tests for the shared ClassifyPipeline infrastructure."""

import json
import pytest
from pathlib import Path

from src.meta_disco.pipeline import ClassifyPipeline, FileTypeConfig, NdjsonWriter


# --- Test fixtures ---

def _make_config(**overrides):
    """Create a FileTypeConfig with test defaults."""
    defaults = {
        "name": "test",
        "extensions": (".test",),
        "evidence_subdir": "test",
        "default_output": "test_classifications.json",
        "default_workers": 1,
        "fetcher": lambda evidence_dir, md5, **kw: f"header_for_{md5}",
        "classifier": lambda raw_data, **kw: {"data_modality": {"value": "genomic"}},
        "summary_printer": None,
        "detect_gzip": False,
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
        """When detect_gzip=True, is_gzipped is inferred from filename."""
        calls = []
        def tracking_fetcher(evidence_dir, md5, is_gzipped=True, **kw):
            calls.append(is_gzipped)
            return "header"

        config = _make_config(fetcher=tracking_fetcher, detect_gzip=True)
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
        from src.meta_disco.file_types import FILE_TYPE_REGISTRY
        assert set(FILE_TYPE_REGISTRY.keys()) == {"bam", "vcf", "fastq", "fasta"}

    def test_configs_have_required_fields(self):
        from src.meta_disco.file_types import FILE_TYPE_REGISTRY
        for name, config in FILE_TYPE_REGISTRY.items():
            assert config.name == name
            assert len(config.extensions) > 0
            assert config.evidence_subdir
            assert config.default_output.endswith(".json")
            assert callable(config.fetcher)
            assert callable(config.classifier)
