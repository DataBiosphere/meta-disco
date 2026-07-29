"""Tests for the header fetchers and the streaming read path (#155, #263).

Two layers:

* Failure behavior at the ``requests`` boundary — a read failure raises ``FetchError``,
  never returns None (#155); samtools being absent is the one exception, an environment
  failure that propagates as itself rather than masquerading as unreadable content.
* The streaming read path (#263): the escalating range reader, gzip / concatenated-gzip
  decode, the decompressed-byte cap (bomb defense), the truncation rule, each line matcher,
  the tar walk, and the five fetchers end to end. These mock ``fetchers._fetch_range`` to
  serve a fixed in-memory object by byte range, so nothing touches the network.
"""

import gzip
import io
import subprocess
import tarfile

import pytest
import requests

import meta_disco.fetchers as fetchers
from meta_disco.evidence import VcfEvidence
from meta_disco.fetchers import (
    FetchError,
    RangeNotSatisfiable,
    _BedMatcher,
    _FastaMatcher,
    _FastqMatcher,
    _iter_lines,
    _open_stream,
    _RawRangeReader,
    _read_head_text,
    _scan_lines,
    _VcfMatcher,
    _walk_tar_members,
    fetch_bam_header,
    fetch_bed_signals,
    fetch_fasta_headers,
    fetch_fastq_reads,
    fetch_gfa_segment_tags,
    fetch_tar_headers,
    fetch_vcf_header,
    require_samtools,
)

MD5 = "a" * 32


@pytest.fixture
def evidence_dir(tmp_path):
    return tmp_path / "ev"


# =============================================================================
# requests-boundary failure behavior (#155)
# =============================================================================


class _Resp:
    def __init__(self, status_code, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


def _partial(full: bytes, start: int, end: int) -> "_Resp":
    """A conformant 206: the requested slice plus a matching Content-Range header."""
    body = full[start : end + 1]
    return _Resp(206, body, headers={"Content-Range": f"bytes {start}-{start + len(body) - 1}/{len(full)}"})


def _patch_get(monkeypatch, resp):
    monkeypatch.setattr(fetchers.requests, "get", lambda *a, **k: resp)


class TestFetchRangeGuards:
    """`_fetch_range` maps an HTTP response to bytes or a specific FetchError. These guards
    fire on the 2nd+ escalating range (start_byte > 0) that `_RawRangeReader` issues in
    production, so they need direct coverage beyond the reader's mocked-`_fetch_range` tests."""

    def test_aligned_206_returns_the_slice(self, monkeypatch):
        _patch_get(monkeypatch, _partial(b"0123456789", 0, 4))
        assert fetchers._fetch_range(MD5, 4) == b"01234"

    def test_416_raises_range_not_satisfiable(self, monkeypatch):
        _patch_get(monkeypatch, _Resp(416))
        with pytest.raises(RangeNotSatisfiable):
            fetchers._fetch_range(MD5, 100, start_byte=50)

    def test_non_2xx_raises_fetcherror_naming_the_status(self, monkeypatch):
        _patch_get(monkeypatch, _Resp(503))
        with pytest.raises(FetchError, match="503"):
            fetchers._fetch_range(MD5, 100)

    def test_200_to_a_ranged_request_raises(self, monkeypatch):
        # A server that ignores Range and returns the whole body (200) on a start_byte>0 request
        # would duplicate/corrupt the accumulated buffer — fail loud instead of appending it.
        _patch_get(monkeypatch, _Resp(200, b"whole body"))
        with pytest.raises(FetchError, match="Range ignored"):
            fetchers._fetch_range(MD5, 100, start_byte=50)

    def test_206_with_misaligned_content_range_raises(self, monkeypatch):
        # Asked start=0, server's window starts at 5 — the wrong bytes; classifying from a
        # misaligned window could be wrong, so raise rather than guess.
        _patch_get(monkeypatch, _Resp(206, b"xxxxx", headers={"Content-Range": "bytes 5-9/100"}))
        with pytest.raises(FetchError, match="misaligned range"):
            fetchers._fetch_range(MD5, 9)

    def test_206_without_content_range_raises(self, monkeypatch):
        # A conformant 206 always carries Content-Range; its absence can't be confirmed aligned.
        _patch_get(monkeypatch, _Resp(206, b"xxxxx"))
        with pytest.raises(FetchError, match="misaligned range"):
            fetchers._fetch_range(MD5, 9)


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


class TestTarFetcher:
    """fetch_tar_headers: stream a head, walk members, wrap failures as FetchError."""

    def test_returns_member_names_from_the_head(self, monkeypatch, evidence_dir):
        data = _make_tar_named(["g/callset.json", "g/vcfheader.vcf"])
        _patch_get(monkeypatch, _partial(data, 0, len(data) - 1))
        names = fetch_tar_headers(evidence_dir, MD5, file_name="x.tar", is_gzipped=False, use_cache=False)
        assert names == ["g/callset.json", "g/vcfheader.vcf"]

    def test_gzipped_tar_head_is_decompressed_then_parsed(self, monkeypatch, evidence_dir):
        # A .tar.gz: is_gzipped=True must decompress the head before the tar walk.
        gz = _make_tar_named(["g/callset.json", "g/vidmap.json"], gzipped=True)
        _patch_get(monkeypatch, _partial(gz, 0, len(gz) - 1))
        names = fetch_tar_headers(evidence_dir, MD5, file_name="x.tar.gz", is_gzipped=True, use_cache=False)
        assert names == ["g/callset.json", "g/vidmap.json"]

    def test_non_2xx_raises_fetcherror(self, monkeypatch, evidence_dir):
        _patch_get(monkeypatch, _Resp(404))
        with pytest.raises(FetchError):
            fetch_tar_headers(evidence_dir, MD5, file_name="x.tar", is_gzipped=False, use_cache=False)

    def test_non_tar_head_is_readable_empty_not_error(self, monkeypatch, evidence_dir):
        # A readable-but-unparseable head is an empty member list (not_classified),
        # not a FetchError — the range read itself succeeded.
        _patch_get(monkeypatch, _Resp(200, b"garbage, not a tar"))
        assert fetch_tar_headers(evidence_dir, MD5, file_name="x.tar", is_gzipped=False, use_cache=False) == []


# =============================================================================
# streaming read path (#263)
# =============================================================================


def _range_server(obj: bytes, calls: list | None = None):
    """A fake ``_fetch_range`` serving ``obj`` by range; a start at/past EOF raises 416."""

    def fake(md5sum, end_byte, timeout=60, url=None, start_byte=0):
        if calls is not None:
            calls.append((start_byte, end_byte))
        if start_byte >= len(obj):
            raise RangeNotSatisfiable("HTTP 416")
        return obj[start_byte : end_byte + 1]

    return fake


def _install(monkeypatch, obj: bytes, calls: list | None = None) -> None:
    monkeypatch.setattr(fetchers, "_fetch_range", _range_server(obj, calls))


def _tags_json(tags):
    return [t.to_json() for t in tags]


def _make_tar_named(names: list[str], *, gzipped: bool = False, body_len: int = 0) -> bytes:
    """Build an in-memory tar (or tar.gz); each member gets a ``body_len``-byte body."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz" if gzipped else "w") as tar:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = body_len
            tar.addfile(info, io.BytesIO(b"z" * body_len))
    return buf.getvalue()


# --- _RawRangeReader ---------------------------------------------------------------


def test_raw_reader_reassembles_object_in_few_ranges(monkeypatch):
    obj = bytes(range(256)) * 8000  # ~2 MB, spans several geometric ranges
    calls: list = []
    _install(monkeypatch, obj, calls)

    reader = _RawRangeReader(MD5, url=None, cap=len(obj))
    got = io.BufferedReader(reader).read()

    assert got == obj
    assert reader.bytes_fetched == len(obj)
    assert len(calls) <= 4  # geometric growth keeps round-trips low, not one-per-8KB


def test_raw_reader_stops_at_compressed_cap(monkeypatch):
    obj = b"x" * 1000
    _install(monkeypatch, obj)

    reader = _RawRangeReader(MD5, url=None, cap=500)
    got = io.BufferedReader(reader).read()

    assert got == obj[:500]
    assert reader.bytes_fetched == 500


def test_raw_reader_416_on_first_range_raises(monkeypatch):
    # An empty/absent object 416s on the very first range: that is a read failure, not EOF,
    # so it propagates (kept as not_classified) rather than yielding an empty-but-successful head.
    _install(monkeypatch, b"")

    reader = _RawRangeReader(MD5, url=None, cap=1000)
    with pytest.raises(RangeNotSatisfiable):
        io.BufferedReader(reader).read()


def test_raw_reader_416_after_bytes_is_eof(monkeypatch):
    # A 416 on a later range (the object ended exactly on the prior boundary) is clean EOF.
    obj = b"x" * 100
    monkeypatch.setattr(fetchers, "FIRST_CHUNK", 100)  # first range returns exactly 100 (not short)
    _install(monkeypatch, obj)

    reader = _RawRangeReader(MD5, url=None, cap=1000)
    assert io.BufferedReader(reader).read() == obj
    assert reader.whole_file is True


# --- decompression / line drivers --------------------------------------------------


def test_iter_lines_plain_stream(monkeypatch):
    _install(monkeypatch, b"aaa\nbbb\nccc")  # no trailing newline
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    assert list(_iter_lines(stream, raw, cap=1 << 20)) == ["aaa", "bbb", "ccc"]


def test_iter_lines_decodes_gzip(monkeypatch):
    _install(monkeypatch, gzip.compress(b"##head\n#CHROM\n"))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=True, compressed_cap=1 << 20)
    assert list(_iter_lines(stream, raw, cap=1 << 20)) == ["##head", "#CHROM"]


def test_iter_lines_decodes_concatenated_gzip_members(monkeypatch):
    # BGZF and `cat a.gz b.gz` are concatenated gzip members; GzipFile must read past the
    # first, unlike a fixed first-member decode.
    _install(monkeypatch, gzip.compress(b"a\n") + gzip.compress(b"b\nc"))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=True, compressed_cap=1 << 20)
    assert list(_iter_lines(stream, raw, cap=1 << 20)) == ["a", "b", "c"]


def test_iter_lines_drops_partial_trailing_line_when_decompressed_cap_hit(monkeypatch):
    _install(monkeypatch, b"aaa\nbbbbb")
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    # the decompressed cap cuts inside "bbbbb": that partial record is dropped, "aaa" kept.
    assert list(_iter_lines(stream, raw, cap=5)) == ["aaa"]


def test_compressed_cap_truncation_is_visible(monkeypatch):
    # A non-gzip object larger than its compressed cap: stopping at the cap returns 0 bytes
    # just like EOF, so completeness must come from raw.whole_file — else the partial final
    # line is wrongly kept as a whole record.
    _install(monkeypatch, b"aaa\nbbb\ncccccc")
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=10)  # cuts inside "cccccc"
    text, truncated = _read_head_text(stream, raw, cap=1 << 20)
    assert truncated is True
    assert text == "aaa\nbbb\ncc"

    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=10)
    assert list(_iter_lines(stream, raw, cap=1 << 20)) == ["aaa", "bbb"]  # partial "cc" dropped


def test_open_stream_only_gzips_when_magic_present(monkeypatch, evidence_dir):
    # A file routed as gzipped (name ends .gz) whose bytes are NOT gzip must be read as raw
    # text (the magic is peeked, not assumed) — not raised as BadGzipFile and dropped. An
    # uncompressed VCF/FASTA misnamed .gz still yields its content.
    _install(monkeypatch, b">chr1 desc\nACGT\n>chr2\nTTTT\n")  # plain FASTA, but is_gzipped=True
    assert fetch_fasta_headers(evidence_dir, MD5, is_gzipped=True, use_cache=False) == ["chr1", "chr2"]


def test_read_head_text_reports_completion(monkeypatch):
    _install(monkeypatch, gzip.compress(b"hello\nworld\n"))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=True, compressed_cap=1 << 20)
    text, truncated = _read_head_text(stream, raw, cap=1 << 20)
    assert text == "hello\nworld\n"
    assert truncated is False


def test_read_head_text_caps_a_decompression_bomb(monkeypatch):
    # ~1 MB of one repeated byte compresses tiny; the cap bounds the decompressed output.
    _install(monkeypatch, gzip.compress(b"X" * 1_000_000))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=True, compressed_cap=1 << 20)
    text, truncated = _read_head_text(stream, raw, cap=1000)
    assert len(text) == 1000
    assert truncated is True


# --- matchers ----------------------------------------------------------------------


def test_vcf_matcher_splits_header_and_variants():
    m = _VcfMatcher(max_variants=2)
    assert m.feed("##fileformat=VCFv4.2") is False
    assert m.feed("#CHROM\tPOS") is False
    assert m.feed("1\t100") is False
    assert m.feed("1\t200") is True  # second variant → satisfied
    assert m.header_lines == ["##fileformat=VCFv4.2", "#CHROM\tPOS"]
    assert m.variant_lines == ["1\t100", "1\t200"]


def test_fastq_matcher_skips_three_lines_per_read():
    m = _FastqMatcher(num_reads=2)
    feeds = [m.feed(line) for line in ["@r1", "ACGT", "+", "IIII", "@r2", "ACGT"]]
    assert m.read_names == ["@r1", "@r2"]
    assert feeds[4] is True  # satisfied on the second read name


def test_fasta_matcher_collects_contig_names():
    m = _FastaMatcher()
    for line in [">chr1 description", "ACGT", ">chr2", ">"]:
        assert m.feed(line) is False  # never an early stop
    assert m.contig_names == ["chr1", "chr2"]  # bare ">" yields no name


# --- tar walk ----------------------------------------------------------------------


def test_walk_tar_stops_at_stage_boundary_when_conclusive(monkeypatch):
    # stages=(1,): the first fetch pulls the whole small tar, so bytes_served crosses 1 after
    # member 0, and the detector is consulted there.
    _install(monkeypatch, _make_tar_named(["a.vcf", "b.txt", "c.bam"]))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    names = _walk_tar_members(stream, raw, detector=lambda ns: "a.vcf" in ns, max_members=200, stages=(1,))
    assert names == ["a.vcf"]


def test_walk_tar_does_not_cut_at_first_recognized_member(monkeypatch):
    # The bug this guards: applying the detector per-member cut a mixed archive at its first
    # recognized member. With real stages a small tar never crosses a boundary, so the whole
    # head is voted on — all members are returned, not just the leading outlier.
    _install(monkeypatch, _make_tar_named(["outlier.fasta", "v1.vcf", "v2.vcf", "v3.vcf"]))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    names = _walk_tar_members(stream, raw, detector=lambda ns: True, max_members=200, stages=fetchers.TAR_HEAD_STAGES)
    assert names == ["outlier.fasta", "v1.vcf", "v2.vcf", "v3.vcf"]


def test_walk_tar_stage_boundary_tracks_consumed_not_fetched_bytes(monkeypatch):
    # _walk_tar_members gates escalation on bytes_served (consumed). The reader prefetches the
    # whole (61 KiB) archive on the first fill, so bytes_fetched jumps to the end immediately —
    # gating on it would cross the 30 KiB stage after member 0 (a per-member early-stop → 1 name).
    # Gating on bytes_served, the boundary is crossed only once tarfile has actually consumed that
    # far, so the head is voted on many members and the walk still stops before reading all 100.
    _install(monkeypatch, _make_tar_named([f"m{i}.dat" for i in range(100)]))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    names = _walk_tar_members(stream, raw, detector=lambda ns: True, max_members=200, stages=(30_000,))
    assert 1 < len(names) < 100


def test_walk_tar_stops_at_max_members(monkeypatch):
    _install(monkeypatch, _make_tar_named(["m0", "m1", "m2", "m3"]))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    names = _walk_tar_members(stream, raw, detector=lambda ns: False, max_members=2, stages=(1,))
    assert names == ["m0", "m1"]


def test_walk_tar_reads_gzipped_archive(monkeypatch):
    _install(monkeypatch, _make_tar_named(["only.vcf"], gzipped=True))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=True, compressed_cap=1 << 20)
    names = _walk_tar_members(stream, raw, detector=lambda ns: False, max_members=200, stages=(1,))
    assert names == ["only.vcf"]


def test_walk_tar_non_tar_head_is_empty(monkeypatch):
    _install(monkeypatch, b"not a tar at all, just bytes")
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    assert _walk_tar_members(stream, raw, detector=lambda ns: False, max_members=200, stages=(1,)) == []


# --- scan driver -------------------------------------------------------------------


def test_scan_lines_stops_early_on_matcher(monkeypatch):
    _install(monkeypatch, b"\n".join(b"line%d" % i for i in range(1000)))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    m = _scan_lines(stream, raw, cap=1 << 20, matcher=_FastqMatcher(num_reads=1))
    # no "@" lines → matcher never satisfied → it read the whole (capped) head cleanly
    assert m.read_names == []


# --- error propagation -------------------------------------------------------------


def _raise_transport(*_args, **_kwargs):
    raise requests.exceptions.ConnectionError("connection reset")


def test_transport_error_propagates_as_fetch_error(monkeypatch, evidence_dir):
    # requests exceptions subclass OSError; they must NOT be swallowed by the gzip-truncation
    # except clauses — a mid-read network failure surfaces as FetchError, not a silent empty read.
    monkeypatch.setattr(fetchers, "_fetch_range", _raise_transport)
    with pytest.raises(FetchError):
        fetch_fasta_headers(evidence_dir, MD5, is_gzipped=False, use_cache=False)


def test_transport_error_in_tar_walk_propagates(monkeypatch, evidence_dir):
    monkeypatch.setattr(fetchers, "_fetch_range", _raise_transport)
    with pytest.raises(FetchError):
        fetch_tar_headers(evidence_dir, MD5, is_gzipped=False, use_cache=False)


def test_first_range_416_raises_not_empty_success(monkeypatch, evidence_dir):
    # An empty/absent object must raise (kept as not_classified), not cache an empty-list success.
    _install(monkeypatch, b"")
    with pytest.raises(FetchError):
        fetch_fasta_headers(evidence_dir, MD5, is_gzipped=False, use_cache=False)


# --- fetchers end to end -----------------------------------------------------------


def test_fetch_vcf_returns_header_and_caches(monkeypatch, evidence_dir):
    obj = gzip.compress(b"##fileformat=VCFv4.2\n#CHROM\tPOS\tID\n1\t100\t.\n")
    _install(monkeypatch, obj)

    header = fetch_vcf_header(evidence_dir, MD5, is_gzipped=True, use_cache=False)
    assert header == "##fileformat=VCFv4.2\n#CHROM\tPOS\tID"

    cached = VcfEvidence.load(evidence_dir, MD5)
    assert cached is not None and cached.payload == header

    # a second call hits the cache and never re-fetches
    monkeypatch.setattr(fetchers, "_fetch_range", lambda *a, **k: pytest.fail("re-fetched a cached VCF"))
    assert fetch_vcf_header(evidence_dir, MD5, is_gzipped=True, use_cache=True) == header


def test_fetch_vcf_no_header_raises(monkeypatch, evidence_dir):
    _install(monkeypatch, gzip.compress(b"1\t100\t.\n2\t200\t.\n"))
    with pytest.raises(FetchError):
        fetch_vcf_header(evidence_dir, MD5, is_gzipped=True, use_cache=False)


def test_fetch_fastq_reads_names(monkeypatch, evidence_dir):
    _install(monkeypatch, gzip.compress(b"@r1\nACGT\n+\nIIII\n@r2\nTTTT\n+\nIIII\n"))
    assert fetch_fastq_reads(evidence_dir, MD5, is_gzipped=True, use_cache=False) == ["@r1", "@r2"]


def test_fetch_fasta_contig_names(monkeypatch, evidence_dir):
    _install(monkeypatch, gzip.compress(b">chr1 desc\nACGT\n>chr2\nTTTT\n"))
    assert fetch_fasta_headers(evidence_dir, MD5, is_gzipped=True, use_cache=False) == ["chr1", "chr2"]


def test_fetch_bed_signals(monkeypatch, evidence_dir):
    # BED reference signals read through the shared streaming reader (#282): chromosomes,
    # chr-prefix, and the per-contig MAX end coordinate.
    _install(monkeypatch, gzip.compress(b"chr1\t0\t1000\nchr1\t2000\t5000\nchr2\t0\t300\n"))
    signals = fetch_bed_signals(evidence_dir, MD5, is_gzipped=True, use_cache=False)
    assert signals.chromosomes == ["chr1", "chr2"]
    assert signals.has_chr_prefix is True
    assert signals.max_coordinates == {"chr1": 5000, "chr2": 300}


def test_fetch_bed_signals_uncompressed(monkeypatch, evidence_dir):
    # BED_CONFIG covers plain .bed as well as .bed.gz; the shared reader must read an
    # uncompressed body (is_gzipped=False) through the same matcher.
    _install(monkeypatch, b"chr1\t0\t1000\nchr2\t0\t300\n")
    signals = fetch_bed_signals(evidence_dir, MD5, is_gzipped=False, use_cache=False)
    assert signals.chromosomes == ["chr1", "chr2"]
    assert signals.max_coordinates == {"chr1": 1000, "chr2": 300}


def test_bed_reads_deeper_than_the_generic_decompressed_cap():
    # #282 correctness fix: BED reference detection needs per-contig MAX coordinates, which
    # for a whole-genome sorted .bed.gz sit deep in the decompressed stream. BED's decompressed
    # ceiling must exceed the generic MAX_DECOMPRESSED (which would truncate the head and
    # undercount coordinates, regressing GRCh38 -> not_classified) and the compressed cap, so
    # the compressed cap is what bounds a legitimate read (matching the pre-#282 fetcher).
    assert fetchers.BED_MAX_DECOMPRESSED > fetchers.MAX_DECOMPRESSED
    assert fetchers.BED_MAX_DECOMPRESSED > fetchers.BED_COMPRESSED_CAP


def test_bed_matcher_skips_headers_and_short_rows():
    matcher = _BedMatcher()
    for line in ["track name=x", "1\t0\t100", "1\t50", "# comment", "2\t0\t9999"]:
        matcher.feed(line)
    signals = matcher.result()
    assert signals.chromosomes == ["1", "2"]
    assert signals.has_chr_prefix is False  # no 'chr' prefix -> the GRCh37/b37 signal
    assert signals.max_coordinates == {"1": 100, "2": 9999}
    assert signals.line_count == 2  # the two 3-column rows; header/short/comment skipped


def test_bed_matcher_parses_space_delimited_rows():
    # BED is usually tab-delimited but the spec permits any whitespace; a space-delimited
    # file must still yield coordinate signals rather than parsing to nothing.
    matcher = _BedMatcher()
    for line in ["chr1 0 100", "chr2 0 9999"]:
        matcher.feed(line)
    signals = matcher.result()
    assert signals.chromosomes == ["chr1", "chr2"]
    assert signals.max_coordinates == {"chr1": 100, "chr2": 9999}
    assert signals.line_count == 2


def test_bed_matcher_ignores_rows_with_a_non_numeric_end():
    # A 3+ column row whose end coordinate does not parse (e.g. a stray column-name header)
    # must contribute nothing: no chromosome, no has_chr_prefix, no line_count.
    matcher = _BedMatcher()
    for line in ["chrom\tstart\tend", "chr1\t0\t100"]:
        matcher.feed(line)
    signals = matcher.result()
    assert signals.chromosomes == ["chr1"]  # "chrom" from the bad row is not recorded
    assert signals.max_coordinates == {"chr1": 100}
    assert signals.line_count == 1


def test_bed_matcher_detects_chr_prefix_case_insensitively():
    # `Chr1`/`CHR1` carry a chr prefix; a case-sensitive check would miss them and let
    # _infer_bed_reference mislabel a chr-prefixed file as GRCh37 via its "no prefix" shortcut.
    matcher = _BedMatcher()
    for line in ["Chr1\t0\t100", "CHR2\t0\t9999"]:
        matcher.feed(line)
    assert matcher.result().has_chr_prefix is True


def test_fetch_gfa_reference_backbone_tags(monkeypatch, evidence_dir):
    _install(monkeypatch, b"S\t1\tACGT\tSN:Z:chr1\tSR:i:0\n")
    tags = fetch_gfa_segment_tags(evidence_dir, MD5, is_gzipped=False, use_cache=False)
    assert len(tags) == 1
    assert tags[0].is_reference_backbone
    assert _tags_json(tags) == [{"SN": "chr1", "SR": "0"}]


def test_fetch_tar_reads_whole_small_head(monkeypatch, evidence_dir):
    # A tar smaller than the first stage never crosses a detector boundary, so its whole head
    # is read and voted on — both members returned, regardless of the injected detector. (The
    # detector's escalation role at a boundary is covered by the _walk_tar_members tests.)
    obj = _make_tar_named(["x.vcf", "y.vcf"])

    _install(monkeypatch, obj)
    assert fetch_tar_headers(evidence_dir / "a", MD5, is_gzipped=False, use_cache=False) == ["x.vcf", "y.vcf"]

    both = fetch_tar_headers(
        evidence_dir / "b", MD5, is_gzipped=False, use_cache=False, head_detector=lambda ns: len(ns) >= 2
    )
    assert both == ["x.vcf", "y.vcf"]


def test_fetch_tar_escalates_to_a_deep_signal(monkeypatch, evidence_dir):
    # The detector is false at stage 1 and true only once "signal.vcf" (member 5) is seen, past
    # the first stage. The walk must escalate to reach it — a small multi-fetch stands in for the
    # deep-signal GenomicsDB store — and conclude on that signal rather than stopping shallow.
    names = [f"m{i}.dat" for i in range(8)]
    names[5] = "signal.vcf"
    obj = _make_tar_named(names, body_len=1024)  # bodies spread member headers across the byte stages
    detector = lambda ns: "signal.vcf" in ns  # noqa: E731

    monkeypatch.setattr(fetchers, "TAR_HEAD_STAGES", (4000, 9000, 20000))
    monkeypatch.setattr(fetchers, "FIRST_CHUNK", 2048)  # force multi-fetch so bytes_served lags
    _install(monkeypatch, obj)

    names_out = fetch_tar_headers(evidence_dir, MD5, is_gzipped=False, use_cache=False, head_detector=detector)
    assert "signal.vcf" in names_out  # escalated to and concluded on the deep signal


def test_fetch_tar_warns_when_member_cap_reached(monkeypatch, evidence_dir, capsys):
    # A tar with more members than the cap truncates to MAX_TAR_MEMBERS; the walk must warn so an
    # under-sampled head is not silent (bodies are empty, so all headers sit inside one range).
    _install(monkeypatch, _make_tar_named([f"m{i}.dat" for i in range(fetchers.MAX_TAR_MEMBERS + 5)]))
    names = fetch_tar_headers(evidence_dir, MD5, file_name="big.tar", is_gzipped=False, use_cache=False)
    assert len(names) == fetchers.MAX_TAR_MEMBERS
    out = capsys.readouterr().out
    assert "reached the" in out and "big.tar" in out


# =============================================================================
# fetch_content_length — S3 object size for the HPRC adapter (#276)
# =============================================================================


class TestFetchContentLength:
    def test_head_returns_content_length(self, monkeypatch):
        monkeypatch.setattr(
            fetchers.requests, "head", lambda *a, **k: _Resp(200, headers={"Content-Length": "23303924936"})
        )
        assert fetchers.fetch_content_length("https://example.org/o.bam") == 23303924936

    def test_missing_content_length_raises(self, monkeypatch):
        monkeypatch.setattr(fetchers.requests, "head", lambda *a, **k: _Resp(200))  # no Content-Length
        with pytest.raises(FetchError):
            fetchers.fetch_content_length("https://example.org/o.bam")

    def test_non_2xx_raises_fetcherror(self, monkeypatch):
        monkeypatch.setattr(fetchers.requests, "head", lambda *a, **k: _Resp(403))
        with pytest.raises(FetchError):
            fetchers.fetch_content_length("https://example.org/o.bam")
