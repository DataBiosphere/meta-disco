"""Fetcher failure behavior: a read failure raises FetchError, never returns None (#155).

samtools being absent is the one exception — an environment failure that must
propagate as itself, not masquerade as unreadable content.
"""

import gzip
import io
import subprocess
import tarfile

import pytest
import requests

import meta_disco.fetchers as fetchers
from meta_disco.fetchers import (
    FetchError,
    fetch_bam_header,
    fetch_fasta_headers,
    fetch_fastq_reads,
    fetch_tar_headers,
    fetch_vcf_header,
    parse_tar_member_names,
    require_samtools,
)


def _make_tar(members: list[tuple[str, bytes]]) -> bytes:
    """Build an in-memory tar from ``(name, data)`` pairs."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for member_name, data in members:
            info = tarfile.TarInfo(member_name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


MD5 = "a" * 32


class _Resp:
    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content


@pytest.fixture
def evidence_dir(tmp_path):
    return tmp_path / "ev"


def _patch_get(monkeypatch, resp):
    monkeypatch.setattr(fetchers.requests, "get", lambda *a, **k: resp)


class TestRangeFetchers:
    def test_vcf_non_2xx_raises_fetcherror(self, monkeypatch, evidence_dir):
        _patch_get(monkeypatch, _Resp(404))
        with pytest.raises(FetchError) as exc:
            fetch_vcf_header(evidence_dir, MD5, use_cache=False)
        assert "404" in exc.value.reason

    def test_vcf_empty_header_raises_fetcherror(self, monkeypatch, evidence_dir):
        _patch_get(monkeypatch, _Resp(200, b"not a header line\nanother\n"))
        with pytest.raises(FetchError) as exc:
            fetch_vcf_header(evidence_dir, MD5, is_gzipped=False, use_cache=False)
        assert "no VCF header" in exc.value.reason

    def test_fastq_non_2xx_raises_fetcherror(self, monkeypatch, evidence_dir):
        _patch_get(monkeypatch, _Resp(403))
        with pytest.raises(FetchError):
            fetch_fastq_reads(evidence_dir, MD5, use_cache=False)

    def test_fastq_empty_raises_fetcherror(self, monkeypatch, evidence_dir):
        _patch_get(monkeypatch, _Resp(200, b"no read names here\n"))
        with pytest.raises(FetchError) as exc:
            fetch_fastq_reads(evidence_dir, MD5, is_gzipped=False, use_cache=False)
        assert "no FASTQ read names" in exc.value.reason

    def test_fasta_non_2xx_raises_fetcherror(self, monkeypatch, evidence_dir):
        _patch_get(monkeypatch, _Resp(500))
        with pytest.raises(FetchError):
            fetch_fasta_headers(evidence_dir, MD5, use_cache=False)

    def test_fasta_empty_contigs_is_readable_not_error(self, monkeypatch, evidence_dir):
        # No '>' lines in the fetched head is a readable empty result, not a failure.
        _patch_get(monkeypatch, _Resp(200, b"ACGTACGT\nACGTACGT\n"))
        assert fetch_fasta_headers(evidence_dir, MD5, is_gzipped=False, use_cache=False) == []

    @pytest.mark.parametrize("fetcher", [fetch_vcf_header, fetch_fastq_reads, fetch_fasta_headers])
    def test_request_timeout_is_wrapped_as_fetcherror(self, monkeypatch, evidence_dir, fetcher):
        # requests.Timeout must be wrapped (by the decorator), not propagate raw.
        def _timeout(*a, **k):
            raise requests.Timeout("read timed out")

        monkeypatch.setattr(fetchers.requests, "get", _timeout)
        with pytest.raises(FetchError):
            fetcher(evidence_dir, MD5, use_cache=False)


class TestBamFetcher:
    def _patch_run(self, monkeypatch, fn):
        monkeypatch.setattr(fetchers.subprocess, "run", fn)

    def test_returncode_nonzero_raises_fetcherror(self, monkeypatch, evidence_dir):
        self._patch_run(
            monkeypatch,
            lambda *a, **k: subprocess.CompletedProcess(a, returncode=1, stdout="", stderr="curl: (22) 404"),
        )
        with pytest.raises(FetchError) as exc:
            fetch_bam_header(evidence_dir, MD5, use_cache=False)
        assert "404" in exc.value.reason

    def test_missing_samtools_propagates_not_fetcherror(self, monkeypatch, evidence_dir):
        # An absent tool affects every BAM record — it must NOT become not_classified
        # data, so it propagates as FileNotFoundError rather than FetchError.
        def _run(*a, **k):
            raise FileNotFoundError(2, "No such file or directory", "samtools")

        self._patch_run(monkeypatch, _run)
        with pytest.raises(FileNotFoundError):
            fetch_bam_header(evidence_dir, MD5, use_cache=False)

    def test_timeout_raises_fetcherror(self, monkeypatch, evidence_dir):
        def _run(*a, **k):
            raise subprocess.TimeoutExpired(cmd="samtools", timeout=120)

        self._patch_run(monkeypatch, _run)
        with pytest.raises(FetchError):
            fetch_bam_header(evidence_dir, MD5, use_cache=False)

    def test_empty_header_raises_fetcherror(self, monkeypatch, evidence_dir):
        # returncode 0 but no header — a valid BAM always has @HD/@SQ, so an empty
        # header is a failure, not a readable result.
        self._patch_run(
            monkeypatch,
            lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout="", stderr=""),
        )
        with pytest.raises(FetchError, match="empty SAM header"):
            fetch_bam_header(evidence_dir, MD5, use_cache=False)

    def test_success_returns_header(self, monkeypatch, evidence_dir):
        self._patch_run(
            monkeypatch,
            lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout="@HD\tVN:1.6\n", stderr=""),
        )
        assert fetch_bam_header(evidence_dir, MD5, use_cache=False) == "@HD\tVN:1.6\n"


class TestRequireSamtools:
    def test_raises_when_missing(self, monkeypatch):
        monkeypatch.setattr(fetchers.shutil, "which", lambda _: None)
        with pytest.raises(RuntimeError, match="samtools not found"):
            require_samtools()

    def test_ok_when_present(self, monkeypatch):
        monkeypatch.setattr(fetchers.shutil, "which", lambda _: "/usr/bin/samtools")
        require_samtools()  # must not raise


class TestParseTarMemberNames:
    """Member-name extraction from a (possibly truncated) tar head (#255)."""

    def test_reads_all_members_of_a_whole_tar(self):
        data = _make_tar([("dir/a.vcf", b"x" * 10), ("dir/b.fasta", b"y" * 20), ("dir/c.bam", b"z" * 5)])
        assert parse_tar_member_names(data) == ["dir/a.vcf", "dir/b.fasta", "dir/c.bam"]

    def test_truncated_head_keeps_members_read_before_the_cut(self):
        # A large second member is cut off by the head slice; the first survives.
        data = _make_tar([("dir/a.vcf", b"h" * 10), ("dir/big.tdb", b"D" * 8000)])
        assert parse_tar_member_names(data[:1500]) == ["dir/a.vcf"]

    def test_non_tar_and_empty_yield_no_members(self):
        assert parse_tar_member_names(b"not a tar at all, just bytes") == []
        assert parse_tar_member_names(b"") == []

    def test_member_cap_is_honored(self):
        data = _make_tar([(f"m{i}.txt", b"") for i in range(10)])
        assert parse_tar_member_names(data, max_members=3) == ["m0.txt", "m1.txt", "m2.txt"]


class TestTarFetcher:
    """fetch_tar_headers: range-read a head, parse members, wrap failures as FetchError."""

    def test_returns_member_names_from_the_head(self, monkeypatch, evidence_dir):
        data = _make_tar([("g/callset.json", b"{}"), ("g/vcfheader.vcf", b"##")])
        _patch_get(monkeypatch, _Resp(206, data))
        names = fetch_tar_headers(evidence_dir, MD5, file_name="x.tar", is_gzipped=False, use_cache=False)
        assert names == ["g/callset.json", "g/vcfheader.vcf"]

    def test_gzipped_tar_head_is_decompressed_then_parsed(self, monkeypatch, evidence_dir):
        # A .tar.gz: is_gzipped=True must decompress the head before the tar parse.
        gz = gzip.compress(_make_tar([("g/callset.json", b"{}"), ("g/vidmap.json", b"{}")]))
        _patch_get(monkeypatch, _Resp(206, gz))
        names = fetch_tar_headers(evidence_dir, MD5, file_name="x.tar.gz", is_gzipped=True, use_cache=False)
        assert names == ["g/callset.json", "g/vidmap.json"]

    def test_non_2xx_raises_fetcherror(self, monkeypatch, evidence_dir):
        _patch_get(monkeypatch, _Resp(404))
        with pytest.raises(FetchError):
            fetch_tar_headers(evidence_dir, MD5, file_name="x.tar", is_gzipped=False, use_cache=False)

    def test_non_tar_head_is_readable_empty_not_error(self, monkeypatch, evidence_dir):
        # A readable-but-unparseable head is an empty member list (not_classified),
        # not a FetchError — the range request itself succeeded.
        _patch_get(monkeypatch, _Resp(200, b"garbage, not a tar"))
        assert fetch_tar_headers(evidence_dir, MD5, file_name="x.tar", is_gzipped=False, use_cache=False) == []
