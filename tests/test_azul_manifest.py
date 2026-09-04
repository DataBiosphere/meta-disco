"""Azul manifest ingest (issue #368): the job-following, discovery, parity, and
record mapping, against a fake HTTP session; and the script's idempotence and
rebuild-from-disk behaviour with the same fake injected."""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest
import requests

from meta_disco import azul_manifest as am
from meta_disco.metadata_schema import validate_record
from meta_disco.pipeline import load_records
from tests.metadata_fixtures import valid_record

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import download_anvil_manifest as dl


def no_sleep(_seconds: float) -> None:
    pass


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
    # Submitter-table lines, the bulk of a real verbatim manifest, are not anvil_file
    lines.append(json.dumps({"type": "sample", "value": {"note": "mentions anvil_file in a value only"}}))
    lines.append(json.dumps({"type": "anvil_dataset", "value": {"title": "x"}}))
    return ("\n".join(lines) + "\n").encode()


class FakeResponse:
    def __init__(self, *, json_body=None, content=b"", status_code=200, headers=None):
        self._json = json_body
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def iter_content(self, chunk_size):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeSession:
    """Answers the files facet, then manifest jobs that poll ``polls`` times before finishing."""

    def __init__(
        self,
        datasets: dict[str, int] | None,
        payloads: dict[tuple[str, str], bytes],
        polls: int = 2,
        rate_limits: int = 0,
    ):
        self.datasets = datasets  # None: the catalog is gone, discovery 404s
        self.payloads = payloads
        self.polls = polls
        self.rate_limits = rate_limits  # how many PUTs answer 429 before one is accepted
        self.calls: list[tuple[str, str, dict | None]] = []
        self._jobs: dict[str, dict] = {}

    def get(self, url, **kwargs):
        params = kwargs.get("params")
        self.calls.append(("GET", url, params))
        if url == am.FILES_URL:
            if self.datasets is None:
                return FakeResponse(json_body={"message": "no such catalog"}, status_code=404)
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
        if self.rate_limits > 0:
            self.rate_limits -= 1
            return FakeResponse(json_body={"message": "slow down"}, status_code=429, headers={"Retry-After": "7"})
        title = json.loads(params["filters"])["datasets.title"]["is"][0]
        key = (title, params["format"])
        job_url = f"job://{title}/{params['format']}"
        self._jobs[job_url] = {"left": self.polls, "payload": self.payloads[key]}
        return FakeResponse(json_body={"Status": 301, "Location": job_url, "Retry-After": 1})

    def puts(self) -> int:
        return sum(1 for c in self.calls if c[0] == "PUT")


def one_dataset_session(n: int = 2, facet: int | None = None) -> FakeSession:
    payloads = {("ds", "compact"): compact_payload("ds", n), ("ds", "verbatim.jsonl"): verbatim_payload(n)}
    return FakeSession({"ds": n if facet is None else facet}, payloads)


def two_dataset_session() -> FakeSession:
    payloads = {}
    for title, n in (("a", 3), ("b", 2)):
        payloads[(title, "compact")] = compact_payload(title, n)
        payloads[(title, "verbatim.jsonl")] = verbatim_payload(n)
    return FakeSession({"a": 3, "b": 2}, payloads)


def run(catalog: str, root: Path, session: FakeSession) -> int:
    return dl.download(catalog, root, None, force=False, session=session, sleep=no_sleep)


class TestDiscovery:
    def test_lists_the_accessible_datasets_with_counts_largest_first(self):
        """Scenario 1."""
        session = FakeSession({"small": 2, "big": 5}, {})
        assert am.discover_datasets("anvil15", session) == [am.Dataset("big", 5), am.Dataset("small", 2)]
        [(_, _, params)] = session.calls
        assert params == {"catalog": "anvil15", "size": 1}


class TestFetchManifest:
    def test_follows_the_job_and_downloads_the_signed_url(self, tmp_path):
        """Scenario 2: 301, 301, 302, then the payload, waiting Retry-After between polls."""
        session = FakeSession({}, {("ds", "compact"): b"h\nr\n"}, polls=3)
        sleeps = []
        out = tmp_path / "m.tsv"
        assert am.fetch_manifest("anvil15", "compact", "ds", out, session, sleep=sleeps.append) == 4
        assert out.read_bytes() == b"h\nr\n" and not out.with_name("m.tsv.tmp").exists()
        assert [c[0] for c in session.calls] == ["PUT", "GET", "GET", "GET", "GET"]
        assert sleeps == [1.0, 3.0, 3.0]
        put_params = session.calls[0][2]
        assert put_params is not None
        assert put_params["catalog"] == "anvil15" and put_params["format"] == "compact"
        assert json.loads(put_params["filters"]) == {"datasets.title": {"is": ["ds"]}}

    def test_a_rate_limited_request_is_retried_after_the_named_wait(self, tmp_path):
        """The seventeenth consecutive job of the first real run drew 429 with Retry-After: 30."""
        session = FakeSession({}, {("ds", "compact"): b"h\nr\n"}, polls=1, rate_limits=2)
        sleeps = []
        throttled = []
        original_put = session.put

        def put(url, **kwargs):
            resp = original_put(url, **kwargs)
            if resp.status_code == 429:
                throttled.append(resp)
            return resp

        session.put = put
        assert am.fetch_manifest("anvil15", "compact", "ds", tmp_path / "m", session, sleep=sleeps.append) == 4
        assert [c[0] for c in session.calls][:3] == ["PUT", "PUT", "PUT"]
        assert sleeps[:2] == [7.0, 7.0]
        assert [getattr(r, "closed", False) for r in throttled] == [True, True]

    def test_a_request_that_stays_rate_limited_gives_up_at_max_wait(self, tmp_path):
        """Retry-After is 7s, so a 30s budget allows four waits and refuses the fifth."""
        session = FakeSession({}, {("ds", "compact"): b""}, rate_limits=10**6)
        sleeps = []
        with pytest.raises(RuntimeError, match=r"still returning HTTP 429 after 28s of waiting"):
            am.fetch_manifest("anvil15", "compact", "ds", tmp_path / "m", session, sleep=sleeps.append, max_wait=30)
        assert sleeps == [7.0] * 4
        assert session.puts() == 5

    def test_a_zero_or_dated_retry_after_does_not_defeat_the_budget(self, tmp_path):
        """Retry-After: 0 must not spin without consuming the budget, and an HTTP-date
        value (valid per RFC 7231) must fall back to the backoff, not abort the run."""

        class Throttled(FakeSession):
            def __init__(self, header: str):
                super().__init__({}, {})
                self.header = header

            def put(self, url, **kwargs):
                self.calls.append(("PUT", url, kwargs.get("params")))
                return FakeResponse(status_code=429, headers={"Retry-After": self.header})

        session = Throttled("0")
        sleeps = []
        with pytest.raises(RuntimeError):
            am.fetch_manifest("anvil15", "compact", "ds", tmp_path / "m", session, sleep=sleeps.append, max_wait=3)
        assert sleeps == [1.0, 1.0, 1.0]
        session = Throttled("Wed, 21 Oct 2026 07:28:00 GMT")
        sleeps = []
        with pytest.raises(RuntimeError):
            am.fetch_manifest("anvil15", "compact", "ds", tmp_path / "m", session, sleep=sleeps.append, max_wait=12)
        assert sleeps == [5.0]

    def test_each_wait_is_reported(self, tmp_path):
        session = FakeSession({}, {("ds", "compact"): b"h\nr\n"}, polls=1, rate_limits=1)
        messages = []
        am.fetch_manifest("anvil15", "compact", "ds", tmp_path / "m", session, sleep=no_sleep, log=messages.append)
        assert messages == ["HTTP 429; waiting 7s (7s of 1800s)"]

    def test_backoff_without_retry_after_doubles_to_a_cap(self, tmp_path):
        class Flaky(FakeSession):
            def put(self, url, **kwargs):
                if len(self.calls) < 5:
                    self.calls.append(("PUT", url, kwargs.get("params")))
                    return FakeResponse(status_code=503)
                return super().put(url, **kwargs)

        session = Flaky({}, {("ds", "compact"): b"h\nr\n"}, polls=1)
        sleeps = []
        assert am.fetch_manifest("anvil15", "compact", "ds", tmp_path / "m", session, sleep=sleeps.append) == 4
        assert sleeps[:5] == [5.0, 10.0, 20.0, 40.0, 60.0]

    def test_a_download_that_dies_midway_leaves_no_manifest(self, tmp_path):
        """A rerun must not take a truncated file for a finished manifest."""

        class Dying(FakeResponse):
            def iter_content(self, chunk_size):
                yield b"h\n"
                raise requests.ConnectionError("dropped")

        class Session(FakeSession):
            def get(self, url, **kwargs):
                if url.startswith("signed://"):
                    self.calls.append(("GET", url, None))
                    return Dying(content=b"h\nr\n")
                return super().get(url, **kwargs)

        session = Session({}, {("ds", "compact"): b"h\nr\n"}, polls=1)
        out = tmp_path / "m.tsv"
        with pytest.raises(requests.ConnectionError):
            am.fetch_manifest("anvil15", "compact", "ds", out, session, sleep=no_sleep)
        assert not out.exists() and not out.with_name("m.tsv.tmp").exists()

    def test_a_job_that_never_finishes_times_out(self, tmp_path):
        session = FakeSession({}, {("ds", "compact"): b""}, polls=10**6)
        with pytest.raises(TimeoutError):
            am.fetch_manifest("anvil15", "compact", "ds", tmp_path / "m", session, sleep=no_sleep, timeout=5)

    def test_an_unknown_format_is_refused_before_any_request(self, tmp_path):
        session = FakeSession({}, {})
        with pytest.raises(ValueError):
            am.fetch_manifest("anvil15", "terra.bdbag", "ds", tmp_path / "m", session)
        assert session.calls == []


class TestParity:
    def test_counts_are_streamed_per_format(self, tmp_path):
        (tmp_path / "c.tsv").write_bytes(compact_payload("ds", 3))
        (tmp_path / "v.jsonl").write_bytes(verbatim_payload(3))
        assert am.count_rows("compact", tmp_path / "c.tsv") == 3
        assert am.count_rows("verbatim.jsonl", tmp_path / "v.jsonl") == 3

    def test_a_mismatch_or_a_missing_manifest_is_a_problem(self):
        """Scenario 3."""
        datasets = [am.Dataset("a", 3), am.Dataset("b", 1)]
        counts = {("a", "compact"): 3, ("a", "verbatim.jsonl"): 2, ("b", "compact"): 1}
        assert am.parity_problems(datasets, counts) == [
            "a: verbatim.jsonl has 2 files, the catalog said 3 when requested",
            "b: no verbatim.jsonl manifest on disk",
        ]
        assert am.parity_problems([am.Dataset("a", 3)], {("a", "compact"): 3, ("a", "verbatim.jsonl"): 3}) == []


class TestLayout:
    def test_a_title_that_could_escape_the_catalog_directory_is_refused(self, tmp_path):
        assert am.manifest_path(tmp_path, "anvil15", "AnVIL_HPRC R2", "compact").name == "AnVIL_HPRC R2.compact.tsv"
        for title in ("../../x", "/etc/passwd", "a/b", "", ".", ".."):
            with pytest.raises(ValueError):
                am.manifest_path(tmp_path, "anvil15", title, "compact")
        with pytest.raises(ValueError, match="unknown manifest format"):
            am.manifest_path(tmp_path, "anvil15", "ds", "terra.pfb")

    def test_a_hostile_title_from_the_catalog_exits_with_a_message(self, tmp_path, capsys):
        session = FakeSession({"../escape": 1}, {})
        assert run("anvil15", tmp_path, session) == 1
        assert "Refusing dataset title from the catalog" in capsys.readouterr().err
        assert not (tmp_path / "manifest").exists() or not list((tmp_path / "manifest").rglob("*.tsv"))


class TestRecordMapping:
    def test_a_compact_row_becomes_a_record_the_contract_accepts(self, tmp_path):
        (tmp_path / "c.tsv").write_bytes(compact_payload("ds", 1))
        [record] = am.iter_compact_records(tmp_path / "c.tsv")
        assert record == valid_record(
            entry_id="doc-0",
            file_id="file-0",
            file_name="sample0.bam",
            file_format=".bam",
            file_size=1000,
            file_md5sum="0" * 32,
            reference_assembly="GRCh38",
            drs_uri="drs://drs.anv0:v2_0",
            dataset_id="ds-1",
            dataset_title="ds",
            organism_type="Human",
            phenotypic_sex="Female",
        )
        assert validate_record(record) == []

    def test_a_multi_valued_cell_takes_its_first_value(self):
        assert am._first("genomic || transcriptomic") == "genomic"
        assert am._first("") is None

    def test_a_boolean_cell_that_is_neither_spelling_is_refused(self, tmp_path):
        payload = compact_payload("ds", 1).replace(b"\tFalse\t", b"\ttrue\t")
        (tmp_path / "c.tsv").write_bytes(payload)
        with pytest.raises(ValueError, match=r"c\.tsv line 2"):
            list(am.iter_compact_records(tmp_path / "c.tsv"))

    def test_donor_fields_take_the_first_of_a_multi_value(self, tmp_path):
        payload = compact_payload("ds", 1).replace(b"\tFemale\n", b"\tFemale || Male\n")
        (tmp_path / "c.tsv").write_bytes(payload)
        [record] = am.iter_compact_records(tmp_path / "c.tsv")
        assert record["phenotypic_sex"] == "Female"

    def test_a_failed_write_leaves_the_previous_input_files(self, tmp_path):
        block = am.metadata_block("anvil15", {"ds": 1}, datetime(2026, 9, 4))
        assert am.write_input_files(tmp_path, block, [valid_record()]) == 1
        before = (tmp_path / "anvil_files_metadata.json").read_bytes()

        def bad():
            yield valid_record()
            raise ValueError("a cell the mapping rejects")

        with pytest.raises(ValueError):
            am.write_input_files(tmp_path, block, bad())
        assert (tmp_path / "anvil_files_metadata.json").read_bytes() == before
        assert load_records(tmp_path / "anvil_files_metadata.ndjson") == [valid_record()]
        assert not list(tmp_path.glob("*.tmp"))

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
    def test_a_full_run_writes_manifests_sidecar_and_input(self, tmp_path):
        """The output directory need not exist beforehand."""
        session = one_dataset_session()
        tmp_path = tmp_path / "data" / "anvil"
        assert run("anvil15", tmp_path, session) == 0
        assert am.manifest_path(tmp_path, "anvil15", "ds", "compact").is_file()
        assert am.manifest_path(tmp_path, "anvil15", "ds", "verbatim.jsonl").is_file()
        sidecar = am.load_sidecar(tmp_path, "anvil15")
        assert sidecar["catalog"] == "anvil15"
        assert sidecar["datasets"]["ds"]["file_count"] == 2
        assert sidecar["datasets"]["ds"]["compact"]["rows"] == 2
        assert sidecar["datasets"]["ds"]["verbatim.jsonl"]["rows"] == 2
        out = json.loads((tmp_path / "anvil_files_metadata.json").read_text())
        assert out["metadata"]["catalog"] == "anvil15" and out["metadata"]["datasets"] == {"ds": 2}
        for path in ("anvil_files_metadata.json", "anvil_files_metadata.ndjson"):
            records = load_records(tmp_path / path)
            assert [r["file_name"] for r in records] == ["sample0.bam", "sample1.bam"]
            assert all(validate_record(r) == [] for r in records)

    def test_a_rerun_skips_manifests_on_disk_but_rebuilds_the_input(self, tmp_path):
        """Scenario 6."""
        session = one_dataset_session()
        assert run("anvil15", tmp_path, session) == 0
        (tmp_path / "anvil_files_metadata.json").unlink()
        puts_before = session.puts()
        assert run("anvil15", tmp_path, session) == 0
        assert session.puts() == puts_before
        assert (tmp_path / "anvil_files_metadata.json").is_file()

    def test_a_rerun_judges_parity_by_the_stored_count_when_the_catalog_has_moved(self, tmp_path, capsys):
        """The manifests were requested when the facet said 2; today it says 3. They are
        still internally consistent, so the rebuild proceeds and the drift is reported."""
        session = one_dataset_session()
        assert run("anvil15", tmp_path, session) == 0
        session.datasets = {"ds": 3}
        assert run("anvil15", tmp_path, session) == 0
        assert "catalog now says 3 files, stored 2" in capsys.readouterr().out

    def test_a_deleted_catalog_still_rebuilds_from_disk(self, tmp_path, capsys):
        """anvil14 was deleted server-side; manifests pulled from it must still yield an input file."""
        session = one_dataset_session()
        assert run("anvil14", tmp_path, session) == 0
        (tmp_path / "anvil_files_metadata.json").unlink()
        session.datasets = None
        assert run("anvil14", tmp_path, session) == 0
        assert (tmp_path / "anvil_files_metadata.json").is_file()
        assert "rebuilding from the 1 dataset(s) on disk" in capsys.readouterr().err

    def test_a_dataset_subset_fetches_only_that_dataset_but_rebuilds_the_whole_input(self, tmp_path):
        """A targeted repair must not shrink the corpus: --datasets narrows the fetch, not the file."""
        session = two_dataset_session()
        assert run("anvil15", tmp_path, session) == 0
        am.manifest_path(tmp_path, "anvil15", "b", "compact").unlink()
        puts_before = session.puts()
        assert dl.download("anvil15", tmp_path, {"b"}, force=True, session=session, sleep=no_sleep) == 0
        assert session.puts() == puts_before + 2  # b's two manifests, nothing of a's
        out = json.loads((tmp_path / "anvil_files_metadata.json").read_text())
        assert out["metadata"]["datasets"] == {"a": 3, "b": 2} and len(out["files"]) == 5

    def test_an_unreachable_catalog_still_rebuilds_from_disk(self, tmp_path, capsys):
        """Discovery failing with a connection error, not just a 404, must not abort a rebuild."""
        session = one_dataset_session()
        assert run("anvil15", tmp_path, session) == 0

        class Unreachable(FakeSession):
            def get(self, url, **kwargs):
                if url == am.FILES_URL:
                    raise requests.ConnectionError("no route")
                return super().get(url, **kwargs)

        assert run("anvil15", tmp_path, Unreachable({"ds": 2}, session.payloads)) == 0
        assert "rebuilding from the 1 dataset(s) on disk" in capsys.readouterr().err

    def test_a_parity_mismatch_exits_nonzero_and_writes_no_input(self, tmp_path):
        """Scenario 3, end to end: the facet says 3 files, the compact manifest has 2."""
        session = one_dataset_session(n=2, facet=3)
        session.payloads[("ds", "verbatim.jsonl")] = verbatim_payload(3)
        assert run("anvil15", tmp_path, session) == 1
        assert not (tmp_path / "anvil_files_metadata.json").exists()
