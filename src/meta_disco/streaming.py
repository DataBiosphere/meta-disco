"""One streaming read path for the range-based head-fetchers (#263, #264).

Every range-based fetcher reads the same way: pull a file's head from S3 in bytes,
decompress it on the fly when gzipped, and feed the decompressed stream to a small
matcher that stops as soon as it has what it needs. This module builds that single
path **alongside** the fixed-window fetchers in ``fetchers.py`` — nothing here is wired
into the pipeline yet; ``scripts/compare_streaming.py`` diffs the two before any cutover
(#264 is stage 1 of #263).

The shape:

* :class:`_RawRangeReader` — a forward-only ``io.RawIOBase`` that lazily fetches
  escalating byte ranges (reusing ``fetchers._fetch_range``'s ``start_byte`` /
  ``RangeNotSatisfiable`` / ``Content-Range`` alignment from #260), capped at a
  compressed-byte ceiling.
* :func:`_open_stream` — wraps it in ``gzip.GzipFile`` when gzipped (which decodes
  concatenated members transparently, so BGZF reads past its first block).
* line drivers (:func:`_iter_lines`, :func:`_read_head_text`) + matchers
  (:class:`_VcfMatcher`, :class:`_FastqMatcher`, :class:`_FastaMatcher`) for the text
  types, and :func:`_walk_tar_members` for tar.

Decompression-bomb defense falls out of the design: the line readers stop at
``MAX_DECOMPRESSED`` decompressed bytes (``_iter_lines`` discards each line as it scans;
``_read_head_text`` holds at most that capped head), while the tar walk streams member bodies
past without materializing them, bounded on the network side by ``TAR_COMPRESSED_CAP``
compressed bytes — so a pathological ``.gz`` yields a truncated head, never an unbounded buffer.
"""

import gzip
import io
import tarfile
import zlib

from .evidence import FastaEvidence, FastqEvidence, GfaEvidence, SegmentTag, TarEvidence, VcfEvidence
from .fetchers import (
    HEAD_BYTES,
    MAX_TAR_MEMBERS,
    TAR_HEAD_STAGES,
    FetchError,
    RangeNotSatisfiable,
    _decode_bytes,
    _fetch_range,
    extract_max_positions,
    parse_gfa_segment_tags,
    wrap_as_fetch_error,
)

# Range-fetch sizing. The first range matches the fixed-window fetchers' 256KiB head;
# each subsequent range grows so a deep read (tar) costs few round-trips, not many.
FIRST_CHUNK = HEAD_BYTES
CHUNK_GROWTH = 4
MAX_CHUNK = 10 * 1024 * 1024

# Internal decompressed-read granularity for the line drivers.
_READ_CHUNK = 65536

# Compressed-byte ceilings (network bound). Each is the *maximum* window its old fetcher
# would read, so if streaming reads to the cap it sees the same bytes (it usually stops
# earlier). The old fetchers pass an *inclusive* end_byte, hence the +1 over the round
# window for VCF/FASTQ/FASTA; old GFA already uses HEAD_BYTES-1 (256KiB exactly).
VCF_COMPRESSED_CAP = 1024 * 1024 + 1  # fetch_vcf_header reads bytes 0..1048576
HEAD_COMPRESSED_CAP = HEAD_BYTES + 1  # fetch_fastq_reads / fetch_fasta_headers read bytes 0..262144
GFA_COMPRESSED_CAP = HEAD_BYTES  # fetch_gfa_segment_tags reads bytes 0..262143 (256KiB)
TAR_COMPRESSED_CAP = 100 * 1024 * 1024  # #260 escalation ceiling

# Decompressed-byte ceiling (memory bound) for the line readers — comfortably above any
# real header, and the cap a decompression bomb hits instead of exhausting memory.
MAX_DECOMPRESSED = 16 * 1024 * 1024


class _RawRangeReader(io.RawIOBase):
    """Forward-only raw bytes of a file's head, fetched in escalating ranges up to a cap.

    Fetches large ranges internally and serves ``readinto`` from that buffer, so the
    small reads a ``BufferedReader`` / ``GzipFile`` / ``tarfile`` make on top do not each
    become a range request. Ranges start where the last ended (``start_byte``) and grow
    geometrically; a short read or a 416 marks end-of-object. ``bytes_fetched`` is the
    total compressed bytes pulled from the origin — the ``raw_bytes_fetched`` an evidence
    record reports.
    """

    def __init__(self, md5sum: str, *, url: str | None, cap: int):
        self._md5sum = md5sum
        self._url = url
        self._cap = cap
        self._pending = b""  # the current fetched range
        self._pos = 0  # read offset into _pending (advanced, not sliced, so reads stay O(n))
        self._fetched = 0  # total compressed bytes pulled from the origin
        self._served = 0  # total bytes handed to the consumer via readinto
        self._chunk = FIRST_CHUNK
        self._eof = False

    def readable(self) -> bool:
        return True

    @property
    def bytes_fetched(self) -> int:
        """Total bytes pulled from the origin — the ``raw_bytes_fetched`` for evidence.

        Runs *ahead* of what the consumer has read: a fill fetches a whole range (up to
        ``FIRST_CHUNK``/``MAX_CHUNK``) at once, so this is not a position in the stream."""
        return self._fetched

    @property
    def bytes_served(self) -> int:
        """Total bytes handed downstream via ``readinto`` — how far the consumer has actually
        read, lagging ``bytes_fetched`` by the outstanding fill. The tar walk gates escalation
        on this (not ``bytes_fetched``, which jumps a whole range ahead on the first fill and
        would cross a stage boundary before any member is parsed)."""
        return self._served

    @property
    def whole_file(self) -> bool:
        """True once the object has been read to its end (a short read or a 416 after
        some bytes) — as opposed to stopping at the compressed-byte cap. Lets a consumer
        tell "the file ended" from "we stopped early", which readinto returning 0 cannot."""
        return self._eof

    def _fill(self) -> bool:
        """Ensure unread bytes are available in ``_pending``; return False at end/cap."""
        if self._pos < len(self._pending):
            return True
        if self._eof or self._fetched >= self._cap:
            return False
        want = min(self._chunk, self._cap - self._fetched)
        try:
            data = _fetch_range(self._md5sum, self._fetched + want - 1, url=self._url, start_byte=self._fetched)
        except RangeNotSatisfiable:
            if self._fetched == 0:
                raise  # 416 on the first range — an empty/absent object, a read failure not EOF
            self._eof = True  # 416 after some bytes — the object ended on the prior boundary
            return False
        if not data:
            self._eof = True
            return False
        self._pending = data
        self._pos = 0
        self._fetched += len(data)
        if len(data) < want:
            self._eof = True  # short read — the object ended inside this range
        self._chunk = min(self._chunk * CHUNK_GROWTH, MAX_CHUNK)
        return True

    def readinto(self, b) -> int:
        if len(b) == 0:  # a zero-length probe must not trigger a range fetch
            return 0
        if not self._fill():
            return 0
        n = min(len(b), len(self._pending) - self._pos)
        b[:n] = memoryview(self._pending)[self._pos : self._pos + n]
        self._pos += n
        self._served += n
        return n


def _open_stream(md5sum: str, *, url: str | None, is_gzipped: bool, compressed_cap: int):
    """Open a forward-only stream of a file's head, decompressed when gzipped.

    Returns ``(stream, raw)``: ``stream`` yields decompressed bytes (or raw bytes when not
    gzipped) for a matcher to read; ``raw`` is the underlying :class:`_RawRangeReader`,
    kept so the caller can read ``raw.bytes_fetched`` for the evidence record afterwards.
    ``gzip.GzipFile`` decodes concatenated members transparently, so a BGZF head reads
    past its first block (unlike the fixed-window fetchers, which decode only the first).

    Decompression is enabled only when ``is_gzipped`` *and* the head actually starts with the
    gzip magic (peeked, not consumed) — matching the legacy ``_decompress_head`` magic check, so
    a plain file misnamed ``.gz`` is read as raw text rather than raising ``BadGzipFile``.
    """
    raw = _RawRangeReader(md5sum, url=url, cap=compressed_cap)
    buffered = io.BufferedReader(raw)
    if is_gzipped and buffered.peek(2)[:2] == b"\x1f\x8b":
        return gzip.GzipFile(fileobj=buffered), raw
    return buffered, raw


class _CappedRead:
    """Iterate a decompressed stream in chunks totalling at most ``cap`` bytes.

    ``complete`` is True after iteration only when the whole object was read: the decoded
    stream ended AND the raw reader reached genuine object EOF (``raw.whole_file``). It stays
    False when the read stopped at the decompressed ``cap``, at the compressed cap (which
    makes the raw reader return 0 bytes indistinguishably from EOF, so ``raw.whole_file`` is
    the tie-breaker), or on a cut-short/corrupt gzip stream. Note this is conservative at the
    cap: if the decoded stream happens to end exactly as ``cap`` is reached, the loop exits on
    the cap without observing EOF, so ``complete`` is False — a technically-whole head is
    reported truncated rather than claiming a completion the code cannot prove without reading
    past the cap. This is the one place the caps and the truncated-gzip handling live; the
    line drivers below share it.

    Only gzip *decode* failures are caught here — ``EOFError`` / ``zlib.error`` /
    ``gzip.BadGzipFile`` from a truncated or corrupt stream. A failed range fetch mid-read is
    deliberately NOT caught: an HTTP-status ``FetchError`` and a transport error alike
    propagate out to be surfaced as ``FetchError`` by ``@wrap_as_fetch_error``, rather than
    masquerading as a clean truncation. This is exactly why the catch excludes ``OSError`` —
    ``requests`` transport exceptions (``ConnectionError`` / ``Timeout``) are ``OSError``
    subclasses (``RequestException`` derives from ``OSError``), so catching it would swallow them.
    """

    def __init__(self, stream, raw: "_RawRangeReader", cap: int):
        self._stream = stream
        self._raw = raw
        self._cap = cap
        self.complete = False

    def __iter__(self):
        read = 0
        while read < self._cap:
            try:
                chunk = self._stream.read(min(_READ_CHUNK, self._cap - read))
            except (EOFError, zlib.error, gzip.BadGzipFile):
                return  # gzip stream cut short / corrupt — truncated, so complete stays False
            if not chunk:
                # An empty read is EOF only if the object truly ended; at the compressed cap
                # the raw reader also returns 0, and that is a truncation, not completion.
                self.complete = self._raw.whole_file
                return
            read += len(chunk)
            yield chunk


def _iter_lines(stream, raw: "_RawRangeReader", *, cap: int):
    """Yield decoded lines from a decompressed stream, reading at most ``cap`` bytes.

    Bytes are split on ``b"\\n"`` and each line is decoded whole, so a multi-byte character
    is never cut across a read boundary. A trailing line with no terminating newline is
    yielded only when the whole object was read; if the read stopped at either cap or on a
    cut-short gzip stream, that final partial line is dropped — the byte window may have
    split a record in half. (Same truncation rule as
    :func:`~meta_disco.fetchers.parse_gfa_segment_tags`.)
    """
    reader = _CappedRead(stream, raw, cap)
    remainder = bytearray()  # unterminated tail; extended in place so a newline-sparse read stays O(n)
    for chunk in reader:
        remainder += chunk
        start = 0
        while (nl := remainder.find(b"\n", start)) >= 0:
            yield _decode_bytes(bytes(remainder[start:nl]))
            start = nl + 1
        del remainder[:start]  # drop the lines already yielded, keep the tail
    if reader.complete and remainder:
        yield _decode_bytes(bytes(remainder))


def _read_head_text(stream, raw: "_RawRangeReader", *, cap: int) -> tuple[str, bool]:
    """Decode up to ``cap`` decompressed bytes; report whether the read was truncated.

    ``truncated`` is True when the read stopped at either cap or on a cut-short gzip stream,
    and False only when the whole object was read — the signal
    :func:`~meta_disco.fetchers.parse_gfa_segment_tags` needs to decide whether a final
    unterminated line is a real record or a byte-window artifact.
    """
    reader = _CappedRead(stream, raw, cap)
    data = bytearray()
    for chunk in reader:
        data += chunk
    return _decode_bytes(bytes(data)), not reader.complete


class _VcfMatcher:
    """Collect ``#`` header lines and up to ``max_variants`` variant lines from a VCF head."""

    def __init__(self, max_variants: int = 100):
        self.header_lines: list[str] = []
        self.variant_lines: list[str] = []
        self._max_variants = max_variants

    def feed(self, line: str) -> bool:
        if line.startswith("#"):
            self.header_lines.append(line)
        elif line.strip() and len(self.variant_lines) < self._max_variants:
            self.variant_lines.append(line)
        return len(self.variant_lines) >= self._max_variants


class _FastqMatcher:
    """Collect the first ``num_reads`` read-name (``@``) lines, skipping the 3 lines each."""

    def __init__(self, num_reads: int = 10):
        self.read_names: list[str] = []
        self._num_reads = num_reads
        self._skip = 0  # sequence, +, quality lines to skip after a read name

    def feed(self, line: str) -> bool:
        if self._skip:
            self._skip -= 1
            return False
        line = line.strip()
        if line.startswith("@"):
            self.read_names.append(line)
            self._skip = 3
        return len(self.read_names) >= self._num_reads


class _FastaMatcher:
    """Collect contig names from ``>`` header lines across the read head."""

    def __init__(self):
        self.contig_names: list[str] = []

    def feed(self, line: str) -> bool:
        line = line.strip()
        if line.startswith(">"):
            parts = line[1:].split()  # split() drops surrounding whitespace, so a bare ">" yields []
            if parts:
                self.contig_names.append(parts[0])
        return False  # no early signal — read the whole capped head


def _scan_lines(stream, raw: "_RawRangeReader", *, cap: int, matcher):
    """Feed decoded lines to ``matcher`` until it reports it is satisfied (or ``cap`` is hit)."""
    for line in _iter_lines(stream, raw, cap=cap):
        if matcher.feed(line):
            break
    return matcher


def _walk_tar_members(stream, raw: "_RawRangeReader", *, detector, max_members: int, stages) -> list[str]:
    """Member names from the head of a streamed, already-decompressed tar archive.

    ``detector`` gates *escalation*, not per-member stopping: it is consulted only once the
    consumer has read past the next byte offset in ``stages`` (``raw.bytes_served``, i.e. bytes
    actually parsed, not the whole range prefetched into the reader), on all members read so
    far. That is why a mixed archive is voted on a head sample rather than cut at the first
    recognized member.

    This *approximates* the old fixed-head fetcher's staged escalation; it does not byte-mirror
    it. The old path parses a whole compressed byte-stage and stops at exactly that stage's
    members, whereas here the detector is checked only at stage *crossings* and ``tarfile``
    buffers ahead, so the walk overshoots a few members past the conclusive point before the
    next check fires. The result is a bounded *superset* of the old member set — never fewer, a
    few more near the boundary (for real stages, a handful out of up to ``max_members``). The
    stage-2 shadow-diff quantifies any classification impact.

    Walking stops when the detector is conclusive at a stage boundary, at ``max_members``, or
    when the stream ends / is cut short (a truncated or non-tar head raises ``TarError`` /
    ``EOFError`` / a gzip error, caught here — the names read before the cut are the result). A
    non-tar head yields ``[]``.
    """
    names: list[str] = []
    pending = list(stages)
    try:
        with tarfile.open(fileobj=stream, mode="r|") as tar:
            for member in tar:
                names.append(member.name)
                if len(names) >= max_members:
                    break
                crossed = False
                while pending and raw.bytes_served >= pending[0]:
                    pending.pop(0)
                    crossed = True
                if crossed and detector(names):
                    break
    except (tarfile.TarError, EOFError, zlib.error, gzip.BadGzipFile):
        pass
    return names


def _load_cached(evidence_cls, evidence_dir, md5sum: str, use_cache: bool):
    """Return a cached payload for ``md5sum`` when caching is on and a record is present, else None.

    An empty-list payload (a valid FASTA / GFA / TAR hit) is returned as-is, not confused
    with a miss — the ``_EMPTY_IS_MISS`` types already fail their own ``.load`` when empty.
    """
    if not use_cache:
        return None
    cached = evidence_cls.load(evidence_dir, md5sum)
    return cached.payload if cached is not None else None


def _save_head_evidence(evidence_cls, evidence_dir, *, md5sum, file_name, raw, url, **payload) -> None:
    """Persist a fetched head as its typed evidence, filling the fields every fetcher shares.

    ``payload`` carries the type-specific field(s) — e.g. ``read_names=...``, plus VCF's extra
    ``max_positions``; ``md5sum`` / ``file_name`` / ``raw_bytes_fetched`` (from ``raw``) /
    ``source_url`` are the common provenance all five fetchers record identically.
    """
    evidence_cls(
        md5sum=md5sum,
        file_name=file_name,
        raw_bytes_fetched=raw.bytes_fetched,
        source_url=url,
        **payload,
    ).save(evidence_dir)


@wrap_as_fetch_error("VCF header")
def fetch_vcf_header_streaming(
    evidence_dir,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> str:
    """Streaming counterpart of :func:`~meta_disco.fetchers.fetch_vcf_header`."""
    payload = _load_cached(VcfEvidence, evidence_dir, md5sum, use_cache)
    if payload is not None:
        return payload

    stream, raw = _open_stream(md5sum, url=url, is_gzipped=is_gzipped, compressed_cap=VCF_COMPRESSED_CAP)
    matcher = _scan_lines(stream, raw, cap=MAX_DECOMPRESSED, matcher=_VcfMatcher())

    if matcher.header_lines:
        header_text = "\n".join(matcher.header_lines)
        max_positions = extract_max_positions(matcher.variant_lines) if matcher.variant_lines else None
        _save_head_evidence(
            VcfEvidence,
            evidence_dir,
            md5sum=md5sum,
            file_name=file_name,
            raw=raw,
            url=url,
            header_text=header_text,
            max_positions=max_positions,
        )
        return header_text

    raise FetchError("no VCF header lines (no '#' lines) in the read head")


@wrap_as_fetch_error("FASTQ")
def fetch_fastq_reads_streaming(
    evidence_dir,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    num_reads: int = 10,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> list[str]:
    """Streaming counterpart of :func:`~meta_disco.fetchers.fetch_fastq_reads`."""
    payload = _load_cached(FastqEvidence, evidence_dir, md5sum, use_cache)
    if payload is not None:
        return payload

    stream, raw = _open_stream(md5sum, url=url, is_gzipped=is_gzipped, compressed_cap=HEAD_COMPRESSED_CAP)
    matcher = _scan_lines(stream, raw, cap=MAX_DECOMPRESSED, matcher=_FastqMatcher(num_reads=num_reads))

    if matcher.read_names:
        _save_head_evidence(
            FastqEvidence,
            evidence_dir,
            md5sum=md5sum,
            file_name=file_name,
            raw=raw,
            url=url,
            read_names=matcher.read_names,
        )
        return matcher.read_names

    raise FetchError("no FASTQ read names (no '@' lines) in the read head")


@wrap_as_fetch_error("FASTA")
def fetch_fasta_headers_streaming(
    evidence_dir,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> list[str]:
    """Streaming counterpart of :func:`~meta_disco.fetchers.fetch_fasta_headers`."""
    payload = _load_cached(FastaEvidence, evidence_dir, md5sum, use_cache)
    if payload is not None:
        return payload

    stream, raw = _open_stream(md5sum, url=url, is_gzipped=is_gzipped, compressed_cap=HEAD_COMPRESSED_CAP)
    matcher = _scan_lines(stream, raw, cap=MAX_DECOMPRESSED, matcher=_FastaMatcher())

    _save_head_evidence(
        FastaEvidence,
        evidence_dir,
        md5sum=md5sum,
        file_name=file_name,
        raw=raw,
        url=url,
        contig_names=matcher.contig_names,
    )
    return matcher.contig_names


@wrap_as_fetch_error("GFA head")
def fetch_gfa_segment_tags_streaming(
    evidence_dir,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> list[SegmentTag]:
    """Streaming counterpart of :func:`~meta_disco.fetchers.fetch_gfa_segment_tags`."""
    payload = _load_cached(GfaEvidence, evidence_dir, md5sum, use_cache)
    if payload is not None:
        return payload

    stream, raw = _open_stream(md5sum, url=url, is_gzipped=is_gzipped, compressed_cap=GFA_COMPRESSED_CAP)
    text, truncated = _read_head_text(stream, raw, cap=MAX_DECOMPRESSED)
    segment_tags = parse_gfa_segment_tags(text, truncated=truncated)

    _save_head_evidence(
        GfaEvidence, evidence_dir, md5sum=md5sum, file_name=file_name, raw=raw, url=url, gfa_segment_tags=segment_tags
    )
    return segment_tags


@wrap_as_fetch_error("TAR head")
def fetch_tar_headers_streaming(
    evidence_dir,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = False,
    use_cache: bool = True,
    url: str | None = None,
    head_detector=None,
    **kwargs,
) -> list[str]:
    """Streaming counterpart of :func:`~meta_disco.fetchers.fetch_tar_headers`.

    ``head_detector`` is injected by the caller; ``None`` degrades to an always-conclusive
    detector, which stops the walk at the first stage boundary (a single head — the compressed
    cap never binds, since the detector concludes before it). It decides when the members seen
    so far are conclusive; see :func:`_walk_tar_members` for how the stage-boundary gating
    *approximates* (a bounded superset of) the escalating fetcher rather than mirroring it
    byte-for-byte.
    """
    payload = _load_cached(TarEvidence, evidence_dir, md5sum, use_cache)
    if payload is not None:
        return payload

    detector = head_detector or (lambda _members: True)
    stream, raw = _open_stream(md5sum, url=url, is_gzipped=is_gzipped, compressed_cap=TAR_COMPRESSED_CAP)
    member_names = _walk_tar_members(
        stream, raw, detector=detector, max_members=MAX_TAR_MEMBERS, stages=TAR_HEAD_STAGES
    )

    _save_head_evidence(
        TarEvidence, evidence_dir, md5sum=md5sum, file_name=file_name, raw=raw, url=url, member_names=member_names
    )
    return member_names
