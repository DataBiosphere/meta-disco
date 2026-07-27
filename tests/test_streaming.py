"""Unit tests for the streaming read path (#264).

Everything here mocks ``streaming._fetch_range`` to serve a fixed in-memory object in
response to byte ranges, so nothing touches the network. Coverage: the escalating
range reader, gzip / concatenated-gzip decode, the decompressed-byte cap (bomb defense),
the truncation rule, each line matcher, the tar walk, and the five fetchers end to end
(including equivalence with their fixed-window counterparts on identical bytes).
"""

import gzip
import io
import tarfile

import pytest
import requests

import meta_disco.fetchers as fetchers
import meta_disco.streaming as streaming
from meta_disco.evidence import VcfEvidence
from meta_disco.fetchers import FetchError, RangeNotSatisfiable
from meta_disco.streaming import (
    _FastaMatcher,
    _FastqMatcher,
    _iter_lines,
    _open_stream,
    _RawRangeReader,
    _read_head_text,
    _scan_lines,
    _VcfMatcher,
    _walk_tar_members,
    fetch_fasta_headers_streaming,
    fetch_fastq_reads_streaming,
    fetch_gfa_segment_tags_streaming,
    fetch_tar_headers_streaming,
    fetch_vcf_header_streaming,
)

MD5 = "a" * 32


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
    monkeypatch.setattr(streaming, "_fetch_range", _range_server(obj, calls))


def _install_both(monkeypatch, obj: bytes) -> None:
    """Serve the same bytes to both the streaming and fixed-window read paths."""
    monkeypatch.setattr(streaming, "_fetch_range", _range_server(obj))
    monkeypatch.setattr(fetchers, "_fetch_range", _range_server(obj))


def _tags_json(tags):
    return [t.to_json() for t in tags]


def _make_tar(names: list[str], *, gzipped: bool = False, body_len: int = 0) -> bytes:
    """Build an in-memory tar (or tar.gz); each member gets a ``body_len``-byte body."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz" if gzipped else "w") as tar:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = body_len
            tar.addfile(info, io.BytesIO(b"z" * body_len))
    return buf.getvalue()


@pytest.fixture
def evidence_dir(tmp_path):
    return tmp_path / "ev"


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
    # so it propagates (mirrors _read_head_until's `if not buf: raise`) rather than yielding
    # an empty-but-successful head.
    _install(monkeypatch, b"")

    reader = _RawRangeReader(MD5, url=None, cap=1000)
    with pytest.raises(RangeNotSatisfiable):
        io.BufferedReader(reader).read()


def test_raw_reader_416_after_bytes_is_eof(monkeypatch):
    # A 416 on a later range (the object ended exactly on the prior boundary) is clean EOF.
    obj = b"x" * 100
    monkeypatch.setattr(streaming, "FIRST_CHUNK", 100)  # first range returns exactly 100 (not short)
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
    # first, unlike the fixed-window fetchers.
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
    # stages=(1,): the first fetch pulls the whole small tar, so bytes_fetched crosses 1 after
    # member 0, and the detector is consulted there.
    _install(monkeypatch, _make_tar(["a.vcf", "b.txt", "c.bam"]))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    names = _walk_tar_members(stream, raw, detector=lambda ns: "a.vcf" in ns, max_members=200, stages=(1,))
    assert names == ["a.vcf"]


def test_walk_tar_does_not_cut_at_first_recognized_member(monkeypatch):
    # The bug this guards: applying the detector per-member cut a mixed archive at its first
    # recognized member. With real stages a small tar never crosses a boundary, so the whole
    # head is voted on — all members are returned, not just the leading outlier.
    _install(monkeypatch, _make_tar(["outlier.fasta", "v1.vcf", "v2.vcf", "v3.vcf"]))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    names = _walk_tar_members(stream, raw, detector=lambda ns: True, max_members=200, stages=streaming.TAR_HEAD_STAGES)
    assert names == ["outlier.fasta", "v1.vcf", "v2.vcf", "v3.vcf"]


def test_walk_tar_stage_boundary_tracks_consumed_not_fetched_bytes(monkeypatch):
    # _walk_tar_members gates escalation on bytes_served (consumed). The reader prefetches the
    # whole (61 KiB) archive on the first fill, so bytes_fetched jumps to the end immediately —
    # gating on it would cross the 30 KiB stage after member 0 (a per-member early-stop → 1 name).
    # Gating on bytes_served, the boundary is crossed only once tarfile has actually consumed that
    # far, so the head is voted on many members and the walk still stops before reading all 100.
    _install(monkeypatch, _make_tar([f"m{i}.dat" for i in range(100)]))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    names = _walk_tar_members(stream, raw, detector=lambda ns: True, max_members=200, stages=(30_000,))
    assert 1 < len(names) < 100


def test_walk_tar_stops_at_max_members(monkeypatch):
    _install(monkeypatch, _make_tar(["m0", "m1", "m2", "m3"]))
    stream, raw = _open_stream(MD5, url=None, is_gzipped=False, compressed_cap=1 << 20)
    names = _walk_tar_members(stream, raw, detector=lambda ns: False, max_members=2, stages=(1,))
    assert names == ["m0", "m1"]


def test_walk_tar_reads_gzipped_archive(monkeypatch):
    _install(monkeypatch, _make_tar(["only.vcf"], gzipped=True))
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
    monkeypatch.setattr(streaming, "_fetch_range", _raise_transport)
    with pytest.raises(FetchError):
        fetch_fasta_headers_streaming(evidence_dir, MD5, is_gzipped=False, use_cache=False)


def test_transport_error_in_tar_walk_propagates(monkeypatch, evidence_dir):
    monkeypatch.setattr(streaming, "_fetch_range", _raise_transport)
    with pytest.raises(FetchError):
        fetch_tar_headers_streaming(evidence_dir, MD5, is_gzipped=False, use_cache=False)


def test_first_range_416_raises_not_empty_success(monkeypatch, evidence_dir):
    # An empty/absent object must raise (kept as not_classified), not cache an empty-list success.
    _install(monkeypatch, b"")
    with pytest.raises(FetchError):
        fetch_fasta_headers_streaming(evidence_dir, MD5, is_gzipped=False, use_cache=False)


# --- fetchers end to end -----------------------------------------------------------


def test_fetch_vcf_streaming_returns_header_and_caches(monkeypatch, evidence_dir):
    obj = gzip.compress(b"##fileformat=VCFv4.2\n#CHROM\tPOS\tID\n1\t100\t.\n")
    _install(monkeypatch, obj)

    header = fetch_vcf_header_streaming(evidence_dir, MD5, is_gzipped=True, use_cache=False)
    assert header == "##fileformat=VCFv4.2\n#CHROM\tPOS\tID"

    cached = VcfEvidence.load(evidence_dir, MD5)
    assert cached is not None and cached.payload == header

    # a second call hits the cache and never re-fetches
    monkeypatch.setattr(streaming, "_fetch_range", lambda *a, **k: pytest.fail("re-fetched a cached VCF"))
    assert fetch_vcf_header_streaming(evidence_dir, MD5, is_gzipped=True, use_cache=True) == header


def test_fetch_vcf_streaming_matches_fixed_window(monkeypatch, evidence_dir):
    obj = gzip.compress(b"##fileformat=VCFv4.2\n#CHROM\tPOS\tID\n1\t100\t.\n1\t200\t.\n")
    monkeypatch.setattr(streaming, "_fetch_range", _range_server(obj))
    monkeypatch.setattr(fetchers, "_fetch_range", _range_server(obj))

    new = fetch_vcf_header_streaming(evidence_dir / "new", MD5, is_gzipped=True, use_cache=False)
    old = fetchers.fetch_vcf_header(evidence_dir / "old", MD5, is_gzipped=True, use_cache=False)
    assert new == old


def test_fetch_vcf_streaming_no_header_raises(monkeypatch, evidence_dir):
    _install(monkeypatch, gzip.compress(b"1\t100\t.\n2\t200\t.\n"))
    with pytest.raises(FetchError):
        fetch_vcf_header_streaming(evidence_dir, MD5, is_gzipped=True, use_cache=False)


def test_fetch_fastq_streaming(monkeypatch, evidence_dir):
    _install_both(monkeypatch, gzip.compress(b"@r1\nACGT\n+\nIIII\n@r2\nTTTT\n+\nIIII\n"))
    new = fetch_fastq_reads_streaming(evidence_dir / "new", MD5, is_gzipped=True, use_cache=False)
    old = fetchers.fetch_fastq_reads(evidence_dir / "old", MD5, is_gzipped=True, use_cache=False)
    assert new == ["@r1", "@r2"]
    assert new == old  # drop-in equivalent on identical bytes


def test_fetch_fasta_streaming(monkeypatch, evidence_dir):
    _install_both(monkeypatch, gzip.compress(b">chr1 desc\nACGT\n>chr2\nTTTT\n"))
    new = fetch_fasta_headers_streaming(evidence_dir / "new", MD5, is_gzipped=True, use_cache=False)
    old = fetchers.fetch_fasta_headers(evidence_dir / "old", MD5, is_gzipped=True, use_cache=False)
    assert new == ["chr1", "chr2"]
    assert new == old


def test_fetch_gfa_streaming(monkeypatch, evidence_dir):
    _install_both(monkeypatch, b"S\t1\tACGT\tSN:Z:chr1\tSR:i:0\n")
    new = fetch_gfa_segment_tags_streaming(evidence_dir / "new", MD5, is_gzipped=False, use_cache=False)
    old = fetchers.fetch_gfa_segment_tags(evidence_dir / "old", MD5, is_gzipped=False, use_cache=False)
    assert len(new) == 1
    assert new[0].is_reference_backbone
    # equivalence covers the truncated derivation (raw.whole_file vs got_whole_file+stream_complete)
    assert _tags_json(new) == _tags_json(old)


def test_fetch_tar_streaming_reads_whole_small_head(monkeypatch, evidence_dir):
    # A tar smaller than the first stage never crosses a detector boundary, so its whole head
    # is read and voted on — both members returned, regardless of the injected detector. (The
    # detector's escalation role at a boundary is covered by the _walk_tar_members tests.)
    obj = _make_tar(["x.vcf", "y.vcf"])

    _install_both(monkeypatch, obj)
    new = fetch_tar_headers_streaming(evidence_dir / "new", MD5, is_gzipped=False, use_cache=False)
    old = fetchers.fetch_tar_headers(evidence_dir / "old", MD5, is_gzipped=False, use_cache=False)
    assert new == ["x.vcf", "y.vcf"]
    assert new == old  # both read the whole small head and return every member

    _install(monkeypatch, obj)
    both = fetch_tar_headers_streaming(
        evidence_dir / "b", MD5, is_gzipped=False, use_cache=False, head_detector=lambda ns: len(ns) >= 2
    )
    assert both == ["x.vcf", "y.vcf"]


def test_fetch_tar_streaming_escalation_is_bounded_superset_of_old(monkeypatch, evidence_dir):
    # Staged escalation (detector false at stage 1, true at a later stage) is NOT byte-equal to
    # the old fixed-head fetcher: the detector is checked only at stage crossings and tarfile
    # buffers ahead, so streaming overshoots a few members past the conclusive point. The
    # contract we hold is a bounded superset — streaming never returns fewer members than old,
    # both conclude on the same signal, and the extra are only near the boundary.
    names = [f"m{i}.dat" for i in range(8)]
    names[5] = "signal.vcf"  # signal member sits past stage 1
    obj = _make_tar(names, body_len=1024)  # bodies spread member headers across the byte stages
    detector = lambda ns: "signal.vcf" in ns  # noqa: E731

    monkeypatch.setattr(fetchers, "TAR_HEAD_STAGES", (4000, 9000, 20000))
    monkeypatch.setattr(streaming, "TAR_HEAD_STAGES", (4000, 9000, 20000))
    monkeypatch.setattr(streaming, "FIRST_CHUNK", 2048)  # force multi-fetch so bytes_served lags
    _install_both(monkeypatch, obj)

    old = fetchers.fetch_tar_headers(
        evidence_dir / "old", MD5, is_gzipped=False, use_cache=False, head_detector=detector
    )
    new = fetch_tar_headers_streaming(
        evidence_dir / "new", MD5, is_gzipped=False, use_cache=False, head_detector=detector
    )

    assert "signal.vcf" in old and "signal.vcf" in new  # both escalate to and conclude on the signal
    assert set(old) <= set(new)  # bounded superset: streaming never drops a member old had
    assert len(new) >= len(old)
