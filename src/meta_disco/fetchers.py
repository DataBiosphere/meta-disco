"""Header fetchers for biological data files.

Each fetcher retrieves header/metadata from files on S3 (via range requests
or samtools) and caches the results locally for resumability and audit.

Every range-based fetcher reads the same way (#263): pull a file's head from S3 in
escalating byte ranges, decompress it on the fly when gzipped, and feed the decompressed
stream to a small matcher that stops as soon as it has what it needs. That single path is:

* :class:`_RawRangeReader` — a forward-only ``io.RawIOBase`` that lazily fetches escalating
  byte ranges (via :func:`_fetch_range`'s ``start_byte`` / ``RangeNotSatisfiable`` /
  ``Content-Range`` alignment, #260), capped at a compressed-byte ceiling.
* :func:`_open_stream` — wraps it in ``gzip.GzipFile`` when gzipped (which decodes
  concatenated members transparently, so a BGZF head reads past its first block, unlike a
  fixed first-member decode).
* line drivers (:func:`_iter_lines`, :func:`_read_head_text`) + matchers
  (:class:`_VcfMatcher`, :class:`_FastqMatcher`, :class:`_FastaMatcher`) for the text types,
  and :func:`_walk_tar_members` for tar.

Decompression-bomb defense falls out of the design: the line readers stop at
``MAX_DECOMPRESSED`` decompressed bytes (:func:`_iter_lines` discards each line as it scans;
:func:`_read_head_text` holds at most that capped head), while the tar walk streams member
bodies past without materializing them, bounded on the network side by ``TAR_COMPRESSED_CAP``
compressed bytes — so a pathological ``.gz`` yields a truncated head, never an unbounded buffer.

BAM/CRAM stays on ``samtools`` (:func:`fetch_bam_header`): its compression is fused with the
container structure, and htslib already range-fetches well.

The cache records themselves — path layout, save/load, and the per-type
:class:`~meta_disco.evidence.CachedEvidence` shapes — live in ``evidence.py``;
each fetcher constructs its typed evidence subclass and calls ``.save``/``.load``.
"""

import functools
import gzip
import io
import shutil
import subprocess
import tarfile
import zlib
from pathlib import Path

import requests

from .evidence import BamEvidence, FastaEvidence, FastqEvidence, GfaEvidence, SegmentTag, TarEvidence, VcfEvidence

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"

# The first range every streaming fetcher reads (``FIRST_CHUNK``), the GFA head window, and
# the base for the FASTQ/FASTA/GFA compressed caps. rGFA tags sit on the leading segments,
# well inside this.
HEAD_BYTES = 262144  # 256KiB


class FetchError(Exception):
    """A file's content could not be read or parsed.

    Raised instead of returning None so the caller can keep the file in the
    output — classified as far as its filename allows — with `reason` recorded
    as evidence. `reason` is a short human-readable cause, safe to store as
    classification evidence, and should name the actual failure (an HTTP status,
    an exception type), not merely that something went wrong.

    Raised by `_fetch_range` on any non-2xx response, and by every header fetcher
    (bam/vcf/fastq/fasta/gfa) when the content cannot be read or parsed — each
    propagates it (rather than returning None), so its record is written as a
    `not_classified` row naming the cause instead of vanishing (#155). One
    exception: `fetch_bam_header` lets a `FileNotFoundError` (samtools not
    installed) propagate as itself, since a missing tool is an environment failure
    for every BAM record, not unreadable content for one. The mirror missing an
    unknown number of objects is tracked separately (#156).
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class RangeNotSatisfiable(FetchError):
    """A range request started at or past the end of the object (HTTP 416).

    A subclass of :class:`FetchError` so every ``except FetchError`` still treats it
    as unreadable content by default. The escalating reader (:meth:`_RawRangeReader._fill`)
    catches it specifically: once it already holds bytes, a 416 on the next range means
    the file ended exactly on a range boundary, so it stops with the head in hand rather
    than failing a file it fully read.
    """


def wrap_as_fetch_error(label: str, passthrough: tuple[type[BaseException], ...] = ()):
    """Decorate a fetcher so any read/parse failure surfaces as ``FetchError``.

    Centralizes the wrapping policy every fetcher shares (#155), so the ordering
    rule lives in one place instead of a hand-copied ``except`` tail per fetcher:

    * a ``FetchError`` raised in the body passes through unchanged — its ``reason``
      is already specific (e.g. the HTTP status from ``_fetch_range`` or an
      empty-content message);
    * exception types in ``passthrough`` propagate as themselves — for an
      *environment* failure (``fetch_bam_header`` passes ``FileNotFoundError`` when
      samtools is absent) that must not become one file's unreadable content;
    * everything else becomes ``FetchError(f"{label}: {type(e).__name__}: {e}")``,
      so the record is kept as a ``not_classified`` row naming the cause.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except FetchError:
                raise
            except passthrough:
                raise
            except Exception as e:
                raise FetchError(f"{label}: {type(e).__name__}: {e}") from e

        return wrapper

    return decorator


# =============================================================================
# SHARED FETCH HELPERS
# =============================================================================
#
# The evidence cache itself — its path layout, save/load, and the per-type record
# shapes — now lives in ``evidence.py`` as :class:`~meta_disco.evidence.CachedEvidence`
# and its subclasses (#206). ``get_evidence_path`` moved there too; import it from
# ``meta_disco.evidence``.


def _content_range_start(content_range: str) -> int | None:
    """The first-byte position of a ``Content-Range: bytes <start>-<end>/<total>`` header.

    ``"bytes 0-262143/524288"`` -> ``0``. Returns ``None`` when the header is absent or
    unparseable, which the caller treats the same as a misaligned window.
    """
    try:
        return int(content_range.split()[1].split("/")[0].split("-")[0])
    except (IndexError, ValueError):
        return None


def _fetch_range(md5sum: str, end_byte: int, timeout: int = 60, url: str | None = None, start_byte: int = 0) -> bytes:
    """Fetch bytes ``start_byte`` through ``end_byte`` (inclusive) from S3. Returns raw bytes.

    ``start_byte`` defaults to 0 (a whole-head fetch); the escalating reader
    (:meth:`_RawRangeReader._fill`) passes a non-zero start to fetch only the *new* bytes
    of the next range. If url is provided, fetches from that URL directly. Otherwise uses
    the AnVIL S3 mirror.

    Raises FetchError naming the HTTP status on a non-2xx response. 404 means the
    mirror does not hold this md5 — which is not the same as the file not existing,
    since the catalog entry may still carry a size and a DRS URI. `@wrap_as_fetch_error`
    lets this FetchError pass through unchanged, so the record becomes a
    `not_classified` row with the HTTP status as its reason (#155). A 416 raises
    ``RangeNotSatisfiable``; a 200 to a ``start_byte > 0`` request (the server ignored
    Range) also raises, so a caller accumulating bytes never appends a duplicated body.

    A 206 is verified against its ``Content-Range``: the returned window must start where
    we asked (``start_byte``). A mismatched or missing ``Content-Range`` means the server
    handed back the wrong bytes — classifying from a misaligned window could produce a
    *wrong* answer, so it raises rather than guess. (Fewer bytes than requested is fine —
    the object is shorter than the range; the caller reads that as EOF.)
    """
    fetch_url = url or f"{S3_MIRROR_URL}/{md5sum}.md5"
    headers = {"Range": f"bytes={start_byte}-{end_byte}"}
    resp = requests.get(fetch_url, headers=headers, timeout=timeout)
    source = "source URL" if url else "AnVIL S3 mirror"
    if resp.status_code == 416:  # start_byte at/past EOF — the escalating reader treats this as end-of-file
        raise RangeNotSatisfiable(f"HTTP 416 from {source} range request")
    if start_byte > 0 and resp.status_code == 200:
        # A 200 to a ranged request means the server ignored Range and returned the whole
        # body from byte 0; appending that to the bytes already held would duplicate and
        # corrupt the buffer. S3 and GCS (where this data lives) honor Range with 206, so
        # this should never fire — fail loudly rather than classify from a corrupt buffer.
        raise FetchError(f"HTTP 200 (Range ignored) from {source} range request")
    if resp.status_code not in [200, 206]:
        raise FetchError(f"HTTP {resp.status_code} from {source} range request")
    if resp.status_code == 206:
        got = resp.headers.get("Content-Range", "")
        if _content_range_start(got) != start_byte:
            raise FetchError(
                f"misaligned range from {source}: requested start={start_byte}, got {got or '(no Content-Range)'!r}"
            )
    return resp.content


def _decode_bytes(content: bytes | bytearray) -> str:
    """Decode bytes to string, trying UTF-8 first then Latin-1.

    Accepts a ``bytearray`` too, so a caller holding one can decode it directly rather than
    copying it to ``bytes`` first (``bytearray`` exposes the same ``.decode``).
    """
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")


# =============================================================================
# STREAMING READ PATH (#263)
# =============================================================================

# Range-fetch sizing. The first range is 256KiB — the common head size (FASTQ/FASTA/GFA and
# tar's first stage); subsequent ranges grow geometrically, so the fetchers that read further
# (VCF up to its 1MiB cap, a deep tar) reach their data in a few round-trips, not many.
FIRST_CHUNK = HEAD_BYTES
CHUNK_GROWTH = 4
MAX_CHUNK = 10 * 1024 * 1024

# Internal decompressed-read granularity for the line drivers.
_READ_CHUNK = 65536

# Compressed-byte ceilings (network bound): the most compressed input each fetcher pulls before
# giving up, usually stopping earlier once its matcher is satisfied. ``_fill`` requests an
# *inclusive* ``end_byte``, so a cap of N+1 pulls bytes 0..N — hence the +1 for VCF/FASTQ/FASTA
# over their round windows; GFA caps at exactly 256KiB (bytes 0..262143).
VCF_COMPRESSED_CAP = 1024 * 1024 + 1  # VCF header read window: bytes 0..1048576
HEAD_COMPRESSED_CAP = HEAD_BYTES + 1  # FASTQ / FASTA read window: bytes 0..262144
GFA_COMPRESSED_CAP = HEAD_BYTES  # GFA read window: bytes 0..262143 (256KiB)
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
        """Total bytes handed downstream via ``readinto`` — how far the immediate consumer has
        pulled, lagging ``bytes_fetched`` by the outstanding fill. The tar walk gates escalation
        on this rather than ``bytes_fetched`` (which jumps a whole range ahead on the first fill
        and would cross a stage boundary before any member is parsed)."""
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
    past its first block.

    Decompression is enabled only when ``is_gzipped`` *and* the head actually starts with the
    gzip magic (peeked, not consumed), so a plain file misnamed ``.gz`` is read as raw text
    rather than raising ``BadGzipFile``.
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
    split a record in half. (Same truncation rule as :func:`parse_gfa_segment_tags`.)
    """
    reader = _CappedRead(stream, raw, cap)
    remainder = bytearray()  # unterminated tail; extended in place so a newline-sparse read stays O(n)
    for chunk in reader:
        remainder += chunk
        start = 0
        while (nl := remainder.find(b"\n", start)) >= 0:
            # memoryview slice is a view (no copy); bytes() makes the single copy the decode needs
            yield _decode_bytes(bytes(memoryview(remainder)[start:nl]))
            start = nl + 1
        del remainder[:start]  # drop the lines already yielded, keep the tail
    if reader.complete and remainder:
        yield _decode_bytes(remainder)  # bytearray decodes in place — no copy


def _read_head_text(stream, raw: "_RawRangeReader", *, cap: int) -> tuple[str, bool]:
    """Decode up to ``cap`` decompressed bytes; report whether the read was truncated.

    ``truncated`` is True when the read stopped at either cap or on a cut-short gzip stream,
    and False only when the whole object was read — the signal :func:`parse_gfa_segment_tags`
    needs to decide whether a final unterminated line is a real record or a byte-window artifact.
    """
    reader = _CappedRead(stream, raw, cap)
    data = bytearray()
    for chunk in reader:
        data += chunk
    return _decode_bytes(data), not reader.complete  # bytearray decodes in place — no whole-head copy


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
    consumer has read past the next byte offset in ``stages``, measured by ``raw.bytes_served``
    (compressed bytes handed downstream) on all members read so far. That count *leads* tarfile's
    true member-parse position by a bounded amount — the ``BufferedReader`` and ``tarfile`` both
    read ahead — so a crossing fires near, not exactly at, the stage offset. A mixed archive is
    therefore voted on a head *sample* rather than cut at the first recognized member.

    This *approximates* a staged escalation; it does not read exactly one compressed byte-stage
    at a time. Because the detector is checked only at stage *crossings* and the layers above
    buffer ahead, the member set near a boundary can differ from a stop-at-exactly-that-stage
    read by a few members either way. Since the walk stops only when the detector reports the
    sample *conclusive*, this near-boundary variation did not change any classification in the
    #263 stage-2 shadow-diff over the sampled corpus (an observed result, not a guarantee for
    every possible archive/detector).

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


# =============================================================================
# BAM FETCHER
# =============================================================================


def require_samtools() -> None:
    """Abort the run if samtools is not on PATH (FileTypeConfig.preflight for BAM).

    Run once before the worker pool: a missing tool then fails fast with one clear
    message, instead of every BAM record's ``samtools`` call raising
    ``FileNotFoundError`` and the records vanishing — the disappearance #155 exists
    to prevent. The per-record ``FileNotFoundError`` passthrough in
    ``fetch_bam_header`` remains as a backstop for a tool removed mid-run.
    """
    if shutil.which("samtools") is None:
        raise RuntimeError(
            "samtools not found on PATH — required to read BAM/CRAM headers. Install samtools and retry."
        )


@wrap_as_fetch_error("BAM header", passthrough=(FileNotFoundError,))
def fetch_bam_header(
    evidence_dir: Path,
    md5sum: str,
    file_name: str = "",
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> str:
    """Read BAM/CRAM header from S3 using samtools.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns raw (non-empty) SAM header text.

    Raises ``FetchError`` naming the cause when the header cannot be read (samtools
    exits non-zero, times out, returns an empty header, or the parse fails), so the
    record is kept as a ``not_classified`` row instead of vanishing (#155). An empty
    header is a failure, not a readable result — a valid BAM/CRAM always carries at
    least an ``@HD``/``@SQ`` line — so it raises like the vcf/fastq empty-content
    cases rather than caching an empty string. ``samtools`` being absent is *not* a
    ``FetchError`` (see ``passthrough`` on the decorator): it is an environment
    failure affecting every BAM record, so the ``FileNotFoundError`` propagates
    rather than masquerading as unreadable content.
    """
    payload = _load_cached(BamEvidence, evidence_dir, md5sum, use_cache)
    if payload is not None:
        return payload

    fetch_url = url or f"{S3_MIRROR_URL}/{md5sum}.md5"
    result = subprocess.run(
        ["samtools", "view", "-H", fetch_url],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise FetchError(f"samtools view -H exited {result.returncode}: {result.stderr.strip() or 'no stderr'}")

    header_text = result.stdout
    if not header_text:
        raise FetchError("samtools returned an empty SAM header")

    # raw_bytes_fetched stays None: samtools reads a stream, so there is no
    # byte-range count to report for a BAM/CRAM (evidence.py models this).
    BamEvidence(md5sum=md5sum, file_name=file_name, header_text=header_text, source_url=url).save(evidence_dir)

    return header_text


# =============================================================================
# VCF FETCHER
# =============================================================================


def extract_max_positions(variant_lines: list[str], max_variants: int = 100) -> dict[str, int]:
    """Extract max position per chromosome from variant lines.

    Used for reference assembly detection when header-based detection fails.
    """
    max_positions: dict[str, int] = {}
    count = 0

    for line in variant_lines:
        if count >= max_variants:
            break
        if not line or line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        chrom = parts[0].replace("chr", "")
        try:
            pos = int(parts[1])
            max_positions[chrom] = max(max_positions.get(chrom, 0), pos)
            count += 1
        except ValueError:
            continue

    return max_positions


@wrap_as_fetch_error("VCF header")
def fetch_vcf_header(
    evidence_dir: Path,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> str:
    """Read VCF header from S3 via a streamed range read.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns header text (lines starting with #). Raises ``FetchError`` naming the cause when
    the range read fails or no header is found, so the record is kept as a ``not_classified``
    row instead of vanishing (#155).

    The head is decompressed on the fly (BGZF-aware: ``gzip.GzipFile`` reads past the first
    member), so a ``##source`` caller tag beyond the first BGZF block is seen — the accuracy
    gain over a first-member-only decode (#263).
    """
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


# =============================================================================
# FASTQ FETCHER
# =============================================================================


@wrap_as_fetch_error("FASTQ")
def fetch_fastq_reads(
    evidence_dir: Path,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    num_reads: int = 10,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> list[str]:
    """Read first N read names from a FASTQ file on S3 via a streamed range read.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns list of read name lines (starting with @). Raises ``FetchError`` naming
    the cause when the range read fails or no read names are found, so the record
    is kept as a ``not_classified`` row instead of vanishing (#155).
    """
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


# =============================================================================
# FASTA FETCHER
# =============================================================================


@wrap_as_fetch_error("FASTA")
def fetch_fasta_headers(
    evidence_dir: Path,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> list[str]:
    """Read contig names from a FASTA file on S3 via a streamed range read.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns list of contig names (from > header lines, without >); an empty list when
    the fetched head holds no contig line is a readable result, not a failure. Raises
    ``FetchError`` naming the cause when the range read itself fails, so the record
    is kept as a ``not_classified`` row instead of vanishing (#155).
    """
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


# =============================================================================
# GFA FETCHER
# =============================================================================


def parse_gfa_segment_tags(text: str, truncated: bool = True) -> list[SegmentTag]:
    """Parse rGFA stable-sequence tags from the S (segment) lines of GFA text.

    Returns one :class:`~meta_disco.evidence.SegmentTag` per segment that carries at
    least one of `SN:Z:` (stable sequence name) and `SR:i:` (stable rank). Segments
    with neither — every segment of a plain GFA, such as a minigraph-cactus graph —
    are omitted, so a plain GFA yields an empty list.

    The sequence column is not sliced out into its own string: in a real graph it
    holds the full segment sequence and dominates the line, while the tags follow
    it. Splitting `text` into lines does copy each sequence once; the tag scan
    below avoids copying it a second time.

    ``truncated`` says whether `text` was cut short — the usual case, since the
    fetcher reads only a head. An unterminated final line is then a partial record
    and is dropped. The caller must tell us: a byte-range cut can land exactly on a
    tag boundary, so a truncated line may be *syntactically complete* and no
    inspection of the text can distinguish the two. When `text` is the whole file
    (``truncated=False``), an unterminated final line is a real record and is
    parsed — otherwise a small newline-less rGFA would lose its last segment's
    tags, and with them the reference signal.
    """
    lines = text.split("\n")
    if truncated and not text.endswith("\n"):
        lines.pop()  # partial trailing record from the byte-range cut

    segments = []
    for line in lines:
        if not line.startswith("S\t"):
            continue
        # Advance past the record type (0), name (1), and sequence (2) columns
        # by locating their trailing tabs, so the sequence is never materialized.
        pos = -1
        for _ in range(3):
            pos = line.find("\t", pos + 1)
            if pos == -1:
                break
        if pos == -1:
            continue  # fewer than 4 columns — no tag columns follow the sequence

        sn = sr = None
        for fld in line[pos + 1 :].rstrip("\r").split("\t"):
            if fld.startswith("SN:Z:"):
                sn = fld[5:]
            elif fld.startswith("SR:i:"):
                sr = fld[5:]
        if sn is not None or sr is not None:
            segments.append(SegmentTag(sn=sn, sr=sr))
    return segments


@wrap_as_fetch_error("GFA head")
def fetch_gfa_segment_tags(
    evidence_dir: Path,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> list[SegmentTag]:
    """Read rGFA stable-sequence tags from the S lines at the head of a GFA file.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns a list of :class:`SegmentTag`s, one per rGFA-tagged segment — empty for a plain
    GFA, which is a successful read of a graph that carries no rGFA tags.

    Never returns None. A file that cannot be read or parsed raises FetchError,
    so the caller can tell "read it, found no tags" from "could not read it" and
    keep the file in the output with the cause recorded.

    Only the head (up to ``GFA_COMPRESSED_CAP`` = 256KiB compressed) is read, decompressed
    on the fly when gzipped. rGFA tags sit on the leading segments, after each segment's
    sequence, so the rank-0 signal is normally within the first KB — on the two HPRC
    minigraph graphs I fetched, every segment in the decoded head was rank-0 tagged. It is
    not guaranteed: a graph whose leading segment sequences exceed the decoded head would
    push the tags out of reach, yielding no tags. That degrades safely — the caller makes
    no content claim and falls back to the filename rules, so a reference graph without an
    identifying filename token is left unrefined rather than misclassified.

    On graphs of that scale the head does not reach GFA `P`/`W` path lines,
    which follow every segment line.

    When the read reaches the whole file, the text is not truncated and its final line is
    parsed even without a trailing newline — so a small complete rGFA keeps its last
    segment's tags.
    """
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


# =============================================================================
# TAR FETCHER (#255)
# =============================================================================

# Cap on member names read from a tar head. The 256KiB first range truncates most
# archives long before this; the cap bounds a pathological head of many tiny members.
MAX_TAR_MEMBERS = 200

# Escalating head-read stages (#260): cumulative byte targets (``bytes_served``). The walk
# consults the detector once the consumer has read past 256KiB (conclusive for ~98% of the
# T2T variant-store tars measured) and only escalates while the head is not yet conclusive —
# a GenomicsDB store whose variant signal is deeper than 256KiB, say. The deepest stage is
# ``TAR_COMPRESSED_CAP`` (the network ceiling), so the two stay in lockstep by construction.
# Only the deep-signal tail ever reads past the first stage.
TAR_HEAD_STAGES = (HEAD_BYTES, 1024 * 1024, 10 * 1024 * 1024, TAR_COMPRESSED_CAP)


@wrap_as_fetch_error("TAR head")
def fetch_tar_headers(
    evidence_dir: Path,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = False,
    use_cache: bool = True,
    url: str | None = None,
    head_detector=None,
    **kwargs,
) -> list[str]:
    """Read member names from the head of a tar / tar.gz archive on S3 (#255, #260).

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns the member names visible in the read head; an empty list (a truncated or
    non-tar head) is a readable result, not a failure. Raises ``FetchError`` naming the
    cause when the range read itself fails, so the record is kept as a ``not_classified``
    row instead of vanishing (#155).

    The head is streamed and members are walked (:func:`_walk_tar_members`); ``head_detector``
    gates escalation at :data:`TAR_HEAD_STAGES` byte crossings — the walk reads deeper only
    while the members seen so far are not yet conclusive, so a GenomicsDB store whose variant
    signal is deeper than 256KiB is still found, up to the 100MiB cap. ``head_detector`` is
    injected by the caller (``FileTypeConfig.head_detector`` → ``pipeline``), so the fetcher
    stays ignorant of what makes a head conclusive; ``None`` degrades to an always-conclusive
    detector that stops at the first stage boundary. A ``.tar.gz`` is decompressed on the fly
    (BGZF-aware); a container carries no format of its own (#245) — the archive is classified
    from its inner members.
    """
    payload = _load_cached(TarEvidence, evidence_dir, md5sum, use_cache)
    if payload is not None:
        return payload

    detector = head_detector or (lambda _members: True)
    stream, raw = _open_stream(md5sum, url=url, is_gzipped=is_gzipped, compressed_cap=TAR_COMPRESSED_CAP)
    member_names = _walk_tar_members(
        stream, raw, detector=detector, max_members=MAX_TAR_MEMBERS, stages=TAR_HEAD_STAGES
    )
    if len(member_names) >= MAX_TAR_MEMBERS:
        # `>=` reaches the cap; the walk does not report whether more members followed, so this
        # may also fire for an archive of exactly that many — hence "may have more" rather than
        # asserting the cap truncated the list. Warn so an under-sampled head is not silent.
        print(f"tar member scan reached the {MAX_TAR_MEMBERS}-member cap for {file_name or md5sum}; may have more")

    _save_head_evidence(
        TarEvidence, evidence_dir, md5sum=md5sum, file_name=file_name, raw=raw, url=url, member_names=member_names
    )
    return member_names
