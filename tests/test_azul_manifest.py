"""Azul manifest ingest (issue #368): the job-following, discovery, parity, and
record mapping, against a fake HTTP session; and the script's idempotence."""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from meta_disco import azul_manifest as am

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import download_anvil_manifest as dl

COMPACT_HEADER = "\t".join(
    [
        "files.document_id",
        "files.file_id",
        "files.file_name",
        "files.file_format",
        "files.file_size",
        "files.file_md5sum",
        "files.data_modality",
        "files.reference_assembly",
        "files.is_supplementary",
        "files.drs_uri",
        "datasets.dataset_id",
        "datasets.title",
        "donors.organism_type",
        "donors.phenotypic_sex",
    ]
)


def compact_payload(dataset: str, n: int) -> bytes:
    rows = [COMPACT_HEADER]
    for i in range(n):
        rows.append(
            "\t".join(
                [
                    f"doc-{i}",
                    f"file-{i}",
                    f"sample{i}.bam",
                    ".bam",
                    str(1000 + i),
                    f"{i:032x}",
                    "",
                    "GRCh38",
                    "False",
                    f"drs://drs.anv0:v2_{i}",
                    "ds-1",
                    dataset,
                    "Human",
                    "Female",
                ]
            )
        )
    return ("\n".join(rows) + "\n").encode()


def verbatim_payload(n: int) -> bytes:
    lines = [json.dumps({"type": "anvil_file", "value": {"file_id": f"file-{i}"}}) for i in range(n)]
    lines.append(json.dumps({"type": "anvil_dataset", "value": {"title": "x"}}))
    return ("\n".join(lines) + "\n").encode()


class FakeResponse:
    def __init__(self, *, json_body=None, content=b""):
        self._json = json_body
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class FakeSession:
    """Answers the files facet, then a manifest job that polls twice before finishing."""

    def __init__(self, datasets: dict[str, int], payloads: dict[tuple[str, str], bytes], polls: int = 2):
        self.datasets = datasets
        self.payloads = payloads
        self.polls = polls
        self.calls: list[tuple[str, str, dict | None]] = []
        self._jobs: dict[str, dict] = {}

    def get(self, url, **kwargs):
        params = kwargs.get("params")
        self.calls.append(("GET", url, params))
        if url == am.FILES_URL:
            terms = [{"term": t, "count": c} for t, c in self.datasets.items()]
            return FakeResponse(json_body={"termFacets": {"datasets.title": {"terms": terms}}})
        if url.startswith("job://"):
            job = self._jobs[url]
            job["left"] -= 1
            if job["left"] > 0:
                return FakeResponse(json_body={"Status": 301, "Location": url, "Retry-After": 3})
            return FakeResponse(json_body={"Status": 302, "Location": "signed://" + url})
        if url.startswith("signed://job://"):
            return FakeResponse(content=self._jobs[url.removeprefix("signed://")]["payload"])
        raise AssertionError(f"unexpected GET {url}")

    def put(self, url, **kwargs):
        params = kwargs.get("params")
        self.calls.append(("PUT", url, params))
        assert url == am.MANIFEST_URL and params is not None
        title = json.loads(params["filters"])["datasets.title"]["is"][0]
        key = (title, params["format"])
        job_url = f"job://{title}/{params['format']}"
        self._jobs[job_url] = {"left": self.polls, "payload": self.payloads[key]}
        return FakeResponse(json_body={"Status": 301, "Location": job_url, "Retry-After": 1})


class TestDiscovery:
    def test_lists_the_accessible_datasets_with_counts_largest_first(self):
        """Scenario 1."""
        session = FakeSession({"small": 2, "big": 5}, {})
        assert am.discover_datasets("anvil15", session) == [am.Dataset("big", 5), am.Dataset("small", 2)]
        [(_, _, params)] = session.calls
        assert params == {"catalog": "anvil15", "size": 1}


class TestFetchManifest:
    def test_follows_the_job_and_downloads_the_signed_url(self):
        """Scenario 2: 301, 301, 302, then the payload, waiting Retry-After between polls."""
        session = FakeSession({}, {("ds", "compact"): b"h\nr\n"}, polls=3)
        sleeps = []
        payload = am.fetch_manifest("anvil15", "compact", "ds", session, sleep=sleeps.append)
        assert payload == b"h\nr\n"
        assert [c[0] for c in session.calls] == ["PUT", "GET", "GET", "GET", "GET"]
        assert sleeps == [1.0, 3.0, 3.0]
        put_params = session.calls[0][2]
        assert put_params is not None
        assert put_params["catalog"] == "anvil15" and put_params["format"] == "compact"
        assert json.loads(put_params["filters"]) == {"datasets.title": {"is": ["ds"]}}

    def test_a_job_that_never_finishes_times_out(self):
        session = FakeSession({}, {("ds", "compact"): b""}, polls=10**6)
        with pytest.raises(TimeoutError):
            am.fetch_manifest("anvil15", "compact", "ds", session, sleep=lambda _s: None, timeout=5)

    def test_an_unknown_format_is_refused_before_any_request(self):
        session = FakeSession({}, {})
        with pytest.raises(ValueError):
            am.fetch_manifest("anvil15", "terra.bdbag", "ds", session)
        assert session.calls == []


class TestParity:
    def test_counts_are_measured_per_format(self):
        assert am.count_rows("compact", compact_payload("ds", 3)) == 3
        assert am.count_rows("verbatim.jsonl", verbatim_payload(3)) == 3

    def test_a_mismatch_or_a_missing_manifest_is_a_problem(self):
        """Scenario 3."""
        datasets = [am.Dataset("a", 3), am.Dataset("b", 1)]
        counts = {("a", "compact"): 3, ("a", "verbatim.jsonl"): 2, ("b", "compact"): 1}
        problems = am.parity_problems(datasets, counts)
        assert problems == [
            "a: verbatim.jsonl has 2 files, the catalog facet says 3",
            "b: no verbatim.jsonl manifest on disk",
        ]
        assert am.parity_problems([am.Dataset("a", 3)], {("a", "compact"): 3, ("a", "verbatim.jsonl"): 3}) == []


class TestRecordMapping:
    def test_a_row_becomes_a_contract_record(self):
        cells = compact_payload("ds", 1).decode().splitlines()[1].split("\t")
        row: dict[str, str] = dict(zip(COMPACT_HEADER.split("\t"), cells, strict=True))
        record = am.record_from_compact_row(row)
        assert record == {
            "entry_id": "doc-0",
            "file_id": "file-0",
            "file_name": "sample0.bam",
            "file_format": ".bam",
            "file_size": 1000,
            "file_md5sum": "0" * 32,
            "data_modality": None,
            "reference_assembly": "GRCh38",
            "is_supplementary": False,
            "drs_uri": "drs://drs.anv0:v2_0",
            "dataset_id": "ds-1",
            "dataset_title": "ds",
            "organism_type": "Human",
            "phenotypic_sex": "Female",
        }

    def test_a_multi_valued_cell_takes_its_first_value(self):
        assert am._first("genomic || transcriptomic") == "genomic"
        assert am._first("") is None

    def test_the_metadata_block_names_the_catalog_and_the_source(self):
        block = am.metadata_block("anvil15", {"b": 1, "a": 2}, datetime(2026, 9, 4))
        assert block == {
            "downloaded_at": "2026-09-04T00:00:00",
            "total_files": 3,
            "api_url": am.MANIFEST_URL,
            "catalog": "anvil15",
            "source": "manifest",
            "datasets": {"a": 2, "b": 1},
        }


class TestScript:
    @pytest.fixture
    def session(self, monkeypatch):
        payloads = {
            ("ds", "compact"): compact_payload("ds", 2),
            ("ds", "verbatim.jsonl"): verbatim_payload(2),
        }
        session = FakeSession({"ds": 2}, payloads)
        monkeypatch.setattr(am, "requests", type("R", (), {"Session": staticmethod(lambda: session)}))
        monkeypatch.setattr(am, "time", type("T", (), {"sleep": staticmethod(lambda _s: None)}))
        return session

    def test_a_full_run_writes_manifests_sidecar_and_input(self, tmp_path, session):
        assert dl.download("anvil15", tmp_path, None, force=False) == 0
        manifest_dir = tmp_path / "manifest" / "anvil15"
        assert (manifest_dir / "ds.compact.tsv").is_file() and (manifest_dir / "ds.verbatim.jsonl").is_file()
        sidecar = json.loads((manifest_dir / "manifests.json").read_text())
        assert sidecar["catalog"] == "anvil15"
        assert sidecar["datasets"]["ds"]["compact"]["rows"] == 2
        assert sidecar["datasets"]["ds"]["verbatim.jsonl"]["rows"] == 2
        out = json.loads((tmp_path / "anvil_files_metadata.json").read_text())
        assert out["metadata"]["catalog"] == "anvil15" and out["metadata"]["datasets"] == {"ds": 2}
        assert [r["file_name"] for r in out["files"]] == ["sample0.bam", "sample1.bam"]
        assert (tmp_path / "anvil_files_metadata.ndjson").read_text().count("\n") == 2

    def test_a_rerun_skips_manifests_on_disk_but_rebuilds_the_input(self, tmp_path, session):
        """Scenario 6."""
        assert dl.download("anvil15", tmp_path, None, force=False) == 0
        (tmp_path / "anvil_files_metadata.json").unlink()
        puts_before = sum(1 for c in session.calls if c[0] == "PUT")
        assert dl.download("anvil15", tmp_path, None, force=False) == 0
        assert sum(1 for c in session.calls if c[0] == "PUT") == puts_before
        assert (tmp_path / "anvil_files_metadata.json").is_file()

    def test_a_parity_mismatch_exits_nonzero_and_writes_no_input(self, tmp_path, monkeypatch):
        """Scenario 3, end to end: the facet says 3 files, the compact manifest has 2."""
        payloads = {("ds", "compact"): compact_payload("ds", 2), ("ds", "verbatim.jsonl"): verbatim_payload(3)}
        session = FakeSession({"ds": 3}, payloads)
        monkeypatch.setattr(am, "requests", type("R", (), {"Session": staticmethod(lambda: session)}))
        monkeypatch.setattr(am, "time", type("T", (), {"sleep": staticmethod(lambda _s: None)}))
        assert dl.download("anvil15", tmp_path, None, force=False) == 1
        assert not (tmp_path / "anvil_files_metadata.json").exists()
