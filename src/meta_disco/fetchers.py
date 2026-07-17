"""Header fetchers and evidence cache for biological data files.

Each fetcher retrieves header/metadata from files on S3 (via range requests
or samtools) and caches the results locally for resumability and audit.

Shared evidence cache helpers are parameterized by evidence_dir so the
same logic works for all file types.
"""

import functools
import json
import shutil
import subprocess
import time
import zlib
from pathlib import Path

import requests

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"

# Bytes read from the head of a GFA file. rGFA tags sit on the leading
# segments, well inside this.
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
# SHARED EVIDENCE CACHE
# =============================================================================


def get_evidence_path(evidence_dir: Path, md5sum: str) -> Path:
    """Get path for cached evidence file.

    Uses first 2 chars of MD5 as subdirectory to avoid too many files in one dir.
    """
    return evidence_dir / md5sum[:2] / f"{md5sum}.json"


def load_cached_evidence(evidence_dir: Path, md5sum: str) -> dict | None:
    """Load cached evidence JSON if it exists."""
    path = get_evidence_path(evidence_dir, md5sum)
    if path.exists():
        try:
            with path.open() as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
    return None


def save_evidence(evidence_dir: Path, md5sum: str, evidence: dict) -> None:
    """Save evidence dict to cache."""
    path = get_evidence_path(evidence_dir, md5sum)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(evidence, f, indent=2)


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fetch_range(md5sum: str, end_byte: int, timeout: int = 60, url: str | None = None) -> bytes:
    """Fetch bytes 0 through end_byte (inclusive) from S3. Returns raw bytes.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.

    Raises FetchError naming the HTTP status on a non-2xx response. 404 means the
    mirror does not hold this md5 — which is not the same as the file not existing,
    since the catalog entry may still carry a size and a DRS URI. `@wrap_as_fetch_error`
    lets this FetchError pass through unchanged, so the record becomes a
    `not_classified` row with the HTTP status as its reason (#155).
    """
    fetch_url = url or f"{S3_MIRROR_URL}/{md5sum}.md5"
    headers = {"Range": f"bytes=0-{end_byte}"}
    resp = requests.get(fetch_url, headers=headers, timeout=timeout)
    if resp.status_code not in [200, 206]:
        raise FetchError(f"HTTP {resp.status_code} from {'source URL' if url else 'AnVIL S3 mirror'} range request")
    return resp.content


def _decompress_if_gzipped(content: bytes, is_gzipped: bool) -> bytes:
    """Decompress gzipped content, returning original if not gzipped or on error."""
    return _decompress_head(content, is_gzipped)[0]


def _decompress_head(content: bytes, is_gzipped: bool) -> tuple[bytes, bool]:
    """Decompress, and report whether the decompressed text ends the stream.

    Returns ``(bytes, stream_complete)``. ``stream_complete`` is False when more
    compressed data follows what was decoded — either the gzip stream was cut off,
    or it is BGZF and only the first member was read (see #149). Non-gzipped input
    is trivially complete: the bytes are exactly what was fetched.
    """
    if is_gzipped and content[:2] == b"\x1f\x8b":
        try:
            decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
            out = decompressor.decompress(content)
            return out, decompressor.eof and not decompressor.unused_data
        except zlib.error:
            return content, False
    return content, True


def _decode_bytes(content: bytes) -> str:
    """Decode bytes to string, trying UTF-8 first then Latin-1."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")


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
    if use_cache:
        cached = load_cached_evidence(evidence_dir, md5sum)
        if cached and cached.get("header_text"):
            return cached["header_text"]

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

    evidence = {
        "md5sum": md5sum,
        "file_name": file_name,
        "header_text": header_text,
        "header_line_count": len(header_text.splitlines()),
        "fetch_timestamp": _timestamp(),
    }
    if url:
        evidence["source_url"] = url
    save_evidence(evidence_dir, md5sum, evidence)

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
    """Read VCF header from S3 via range request.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns header text (lines starting with #). Raises ``FetchError`` naming the
    cause when the range request fails or no header is found, so the record is kept
    as a ``not_classified`` row instead of vanishing (#155).
    """
    if use_cache:
        cached = load_cached_evidence(evidence_dir, md5sum)
        if cached and cached.get("header_text"):
            return cached["header_text"]

    content = _fetch_range(md5sum, 1048576, timeout=60, url=url)  # 1MB
    raw_bytes = len(content)

    content = _decompress_if_gzipped(content, is_gzipped)
    text = _decode_bytes(content)

    header_lines = []
    variant_lines = []

    for line in text.split("\n"):
        if line.startswith("#"):
            header_lines.append(line)
        elif line.strip() and len(variant_lines) < 100:
            variant_lines.append(line)

    if header_lines:
        header_text = "\n".join(header_lines)
        max_positions = extract_max_positions(variant_lines) if variant_lines else None
        evidence = {
            "md5sum": md5sum,
            "file_name": file_name,
            "header_text": header_text,
            "header_line_count": len(header_lines),
            "raw_bytes_fetched": raw_bytes,
            "fetch_timestamp": _timestamp(),
        }
        if max_positions:
            evidence["max_positions"] = max_positions
        if url:
            evidence["source_url"] = url
        save_evidence(evidence_dir, md5sum, evidence)
        return header_text

    raise FetchError("no VCF header lines (no '#' lines) in first 1MB")


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
    """Read first N read names from a FASTQ file on S3.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns list of read name lines (starting with @). Raises ``FetchError`` naming
    the cause when the range request fails or no read names are found, so the record
    is kept as a ``not_classified`` row instead of vanishing (#155).
    """
    if use_cache:
        cached = load_cached_evidence(evidence_dir, md5sum)
        if cached and cached.get("read_names"):
            return cached["read_names"]

    content = _fetch_range(md5sum, 262144, timeout=60, url=url)  # 256KB
    raw_bytes = len(content)

    content = _decompress_if_gzipped(content, is_gzipped)
    text = _decode_bytes(content)

    lines = text.split("\n")
    read_names = []
    i = 0
    while i < len(lines) and len(read_names) < num_reads:
        line = lines[i].strip()
        if line.startswith("@"):
            read_names.append(line)
            i += 4  # Skip sequence, +, quality
        else:
            i += 1

    if read_names:
        evidence = {
            "md5sum": md5sum,
            "file_name": file_name,
            "read_names": read_names,
            "raw_bytes_fetched": raw_bytes,
            "fetch_timestamp": _timestamp(),
        }
        if url:
            evidence["source_url"] = url
        save_evidence(evidence_dir, md5sum, evidence)
        return read_names

    raise FetchError("no FASTQ read names (no '@' lines) in first 256KB")


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
    """Read contig names from a FASTA file on S3.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns list of contig names (from > header lines, without >); an empty list when
    the fetched head holds no contig line is a readable result, not a failure. Raises
    ``FetchError`` naming the cause when the range request itself fails, so the record
    is kept as a ``not_classified`` row instead of vanishing (#155).
    """
    if use_cache:
        cached = load_cached_evidence(evidence_dir, md5sum)
        if cached and "contig_names" in cached:
            return cached["contig_names"]

    content = _fetch_range(md5sum, 262144, timeout=60, url=url)  # 256KB
    raw_bytes = len(content)

    content = _decompress_if_gzipped(content, is_gzipped)
    text = _decode_bytes(content)

    contig_names = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith(">"):
            name = line[1:].split()[0] if line[1:].strip() else line[1:].strip()
            if name:
                contig_names.append(name)

    evidence = {
        "md5sum": md5sum,
        "file_name": file_name,
        "contig_names": contig_names,
        "contig_count": len(contig_names),
        "raw_bytes_fetched": raw_bytes,
        "fetch_timestamp": _timestamp(),
    }
    if url:
        evidence["source_url"] = url
    save_evidence(evidence_dir, md5sum, evidence)

    return contig_names


# =============================================================================
# GFA FETCHER
# =============================================================================


def parse_gfa_segment_tags(text: str, truncated: bool = True) -> list[dict]:
    """Parse rGFA stable-sequence tags from the S (segment) lines of GFA text.

    Returns one dict per segment that carries at least one of `SN:Z:` (stable
    sequence name) and `SR:i:` (stable rank). Segments with neither — every
    segment of a plain GFA, such as a minigraph-cactus graph — are omitted, so
    a plain GFA yields an empty list.

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

        tags = {}
        for fld in line[pos + 1 :].rstrip("\r").split("\t"):
            if fld.startswith("SN:Z:"):
                tags["SN"] = fld[5:]
            elif fld.startswith("SR:i:"):
                tags["SR"] = fld[5:]
        if tags:
            segments.append(tags)
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
) -> list[dict]:
    """Read rGFA stable-sequence tags from the S lines at the head of a GFA file.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns a list of tag dicts, one per rGFA-tagged segment — empty for a plain
    GFA, which is a successful read of a graph that carries no rGFA tags.

    Never returns None. A file that cannot be read or parsed raises FetchError,
    so the caller can tell "read it, found no tags" from "could not read it" and
    keep the file in the output with the cause recorded.

    Only the first 256KiB is fetched, and for BGZF input only that range's first
    gzip member decompresses — about 64KiB (see #149).

    rGFA tags sit on the leading segments, after each segment's sequence, so the
    rank-0 signal is normally within the first KB — on the two HPRC minigraph
    graphs I fetched, every segment in the decoded head was rank-0 tagged. It is
    not guaranteed: a graph whose leading segment sequences exceed the decoded
    head would push the tags out of reach, yielding no tags. That degrades
    safely — the caller makes no content claim and falls back to the filename
    rules, so a reference graph without an identifying filename token is left
    unrefined rather than misclassified.

    On graphs of that scale the head does not reach GFA `P`/`W` path lines,
    which follow every segment line.

    When the fetch returns the whole file and the gzip stream ends, the text is not
    truncated and its final line is parsed even without a trailing newline — so a
    small complete rGFA keeps its last segment's tags.
    """
    if use_cache:
        cached = load_cached_evidence(evidence_dir, md5sum)
        if cached and "gfa_segment_tags" in cached:
            return cached["gfa_segment_tags"]

    # end_byte is inclusive, so 262143 fetches exactly HEAD_BYTES. A read/parse
    # failure — including a programming error in parse_gfa_segment_tags — is wrapped
    # as FetchError by @wrap_as_fetch_error, so it surfaces as a not_classified row
    # naming the cause rather than silently deleting the file's row.
    content = _fetch_range(md5sum, HEAD_BYTES - 1, timeout=60, url=url)
    raw_bytes = len(content)

    # Fewer bytes than we asked for means we hold the whole file; a gzip stream
    # that ends with nothing after it means we decoded all of it. Only when both
    # hold is the text complete, so an unterminated final line is a real record.
    # (BGZF fails the second test: its first member ends but more members follow.)
    got_whole_file = raw_bytes < HEAD_BYTES
    content, stream_complete = _decompress_head(content, is_gzipped)
    text = _decode_bytes(content)

    segment_tags = parse_gfa_segment_tags(text, truncated=not (got_whole_file and stream_complete))

    evidence = {
        "md5sum": md5sum,
        "file_name": file_name,
        "gfa_segment_tags": segment_tags,
        "tagged_segment_count": len(segment_tags),
        "raw_bytes_fetched": raw_bytes,
        "fetch_timestamp": _timestamp(),
    }
    if url:
        evidence["source_url"] = url
    save_evidence(evidence_dir, md5sum, evidence)

    return segment_tags
