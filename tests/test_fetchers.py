"""Fetcher failure behavior: a read failure raises FetchError, never returns None (#155).

samtools being absent is the one exception — an environment failure that must
propagate as itself, not masquerade as unreadable content.
"""

import subprocess

import pytest

import meta_disco.fetchers as fetchers
from meta_disco.fetchers import (
    FetchError,
    fetch_bam_header,
    fetch_fasta_headers,
    fetch_fastq_reads,
    fetch_vcf_header,
    require_samtools,
)

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
