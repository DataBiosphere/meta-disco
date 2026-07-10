"""Header fetchers and evidence cache for biological data files.

Each fetcher retrieves header/metadata from files on S3 (via range requests
or samtools) and caches the results locally for resumability and audit.

Shared evidence cache helpers are parameterized by evidence_dir so the
same logic works for all file types.
"""

import json
import subprocess
import time
import zlib
from pathlib import Path

import requests

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"


class FetchError(Exception):
    """A file's content could not be read or parsed.

    Raised instead of returning None so the caller can keep the file in the
    output — classified as far as its filename allows — with `reason` recorded
    as evidence. `reason` is a short human-readable cause, safe to store as
    classification evidence, and should name the actual failure (an HTTP status,
    an exception type), not merely that something went wrong.

    Raised by `_fetch_range` on any non-2xx response, and by
    `fetch_gfa_segment_tags` around its parse. The other three range-based
    fetchers (vcf, fastq, fasta) catch it in their `except Exception` and still
    return None, so their records are still dropped (see #155).
    `fetch_bam_header` never raises FetchError: it shells out to samtools rather
    than calling `_fetch_range`.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


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
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def save_evidence(evidence_dir: Path, md5sum: str, evidence: dict) -> None:
    """Save evidence dict to cache."""
    path = get_evidence_path(evidence_dir, md5sum)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(evidence, f, indent=2)


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _fetch_range(md5sum: str, end_byte: int, timeout: int = 60, url: str | None = None) -> bytes:
    """Fetch bytes 0 through end_byte (inclusive) from S3. Returns raw bytes.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.

    Raises FetchError naming the HTTP status on a non-2xx response. 404 means the
    mirror does not hold this md5 — which is not the same as the file not existing,
    since the catalog entry may still carry a size and a DRS URI. The vcf/fastq/fasta
    callers swallow it in their `except Exception` and return None (see #155).
    """
    fetch_url = url or f"{S3_MIRROR_URL}/{md5sum}.md5"
    headers = {"Range": f"bytes=0-{end_byte}"}
    resp = requests.get(fetch_url, headers=headers, timeout=timeout)
    if resp.status_code not in [200, 206]:
        raise FetchError(
            f"HTTP {resp.status_code} from {'source URL' if url else 'AnVIL S3 mirror'} "
            f"range request"
        )
    return resp.content


def _decompress_if_gzipped(content: bytes, is_gzipped: bool) -> bytes:
    """Decompress gzipped content, returning original if not gzipped or on error."""
    if is_gzipped and content[:2] == b'\x1f\x8b':
        try:
            decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
            return decompressor.decompress(content)
        except zlib.error:
            pass
    return content


def _decode_bytes(content: bytes) -> str:
    """Decode bytes to string, trying UTF-8 first then Latin-1."""
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        return content.decode('latin-1')


# =============================================================================
# BAM FETCHER
# =============================================================================

def fetch_bam_header(
    evidence_dir: Path,
    md5sum: str,
    file_name: str = "",
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> str | None:
    """Read BAM/CRAM header from S3 using samtools.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns raw SAM header text or None.
    """
    if use_cache:
        cached = load_cached_evidence(evidence_dir, md5sum)
        if cached and cached.get("header_text"):
            return cached["header_text"]

    fetch_url = url or f"{S3_MIRROR_URL}/{md5sum}.md5"
    try:
        result = subprocess.run(
            ["samtools", "view", "-H", fetch_url],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return None

        header_text = result.stdout
        if header_text:
            evidence = {
                "md5sum": md5sum,
                "file_name": file_name,
                "header_text": header_text,
                "header_line_count": len(header_text.split('\n')),
                "fetch_timestamp": _timestamp(),
            }
            if url:
                evidence["source_url"] = url
            save_evidence(evidence_dir, md5sum, evidence)

        return header_text
    except subprocess.TimeoutExpired:
        print(f"Timeout reading header for {md5sum}")
        return None
    except FileNotFoundError:
        print("Error: samtools not found. Please install samtools.")
        return None
    except Exception as e:
        print(f"Error reading header for {md5sum}: {e}")
        return None


# =============================================================================
# VCF FETCHER
# =============================================================================

def extract_max_positions(
    variant_lines: list[str], max_variants: int = 100
) -> dict[str, int]:
    """Extract max position per chromosome from variant lines.

    Used for reference assembly detection when header-based detection fails.
    """
    max_positions: dict[str, int] = {}
    count = 0

    for line in variant_lines:
        if count >= max_variants:
            break
        if not line or line.startswith('#'):
            continue

        parts = line.split('\t')
        if len(parts) < 2:
            continue

        chrom = parts[0].replace('chr', '')
        try:
            pos = int(parts[1])
            max_positions[chrom] = max(max_positions.get(chrom, 0), pos)
            count += 1
        except ValueError:
            continue

    return max_positions


def fetch_vcf_header(
    evidence_dir: Path,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> str | None:
    """Read VCF header from S3 via range request.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns header text (lines starting with #) or None.
    """
    if use_cache:
        cached = load_cached_evidence(evidence_dir, md5sum)
        if cached and cached.get("header_text"):
            return cached["header_text"]

    try:
        content = _fetch_range(md5sum, 1048576, timeout=60, url=url)  # 1MB
        raw_bytes = len(content)

        content = _decompress_if_gzipped(content, is_gzipped)
        text = _decode_bytes(content)

        header_lines = []
        variant_lines = []

        for line in text.split('\n'):
            if line.startswith('#'):
                header_lines.append(line)
            elif line.strip():
                if len(variant_lines) < 100:
                    variant_lines.append(line)

        if header_lines:
            header_text = '\n'.join(header_lines)
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

        return None

    except requests.Timeout:
        print(f"Timeout reading header for {md5sum}")
        return None
    except Exception as e:
        print(f"Error reading header for {md5sum}: {e}")
        return None


# =============================================================================
# FASTQ FETCHER
# =============================================================================

def fetch_fastq_reads(
    evidence_dir: Path,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    num_reads: int = 10,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> list[str] | None:
    """Read first N read names from a FASTQ file on S3.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns list of read name lines (starting with @) or None.
    """
    if use_cache:
        cached = load_cached_evidence(evidence_dir, md5sum)
        if cached and cached.get("read_names"):
            return cached["read_names"]

    try:
        content = _fetch_range(md5sum, 262144, timeout=60, url=url)  # 256KB
        raw_bytes = len(content)

        content = _decompress_if_gzipped(content, is_gzipped)
        text = _decode_bytes(content)

        lines = text.split('\n')
        read_names = []
        i = 0
        while i < len(lines) and len(read_names) < num_reads:
            line = lines[i].strip()
            if line.startswith('@'):
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

        return read_names if read_names else None

    except requests.Timeout:
        print(f"Timeout reading FASTQ for {md5sum}")
        return None
    except Exception as e:
        print(f"Error reading FASTQ for {md5sum}: {e}")
        return None


# =============================================================================
# FASTA FETCHER
# =============================================================================

def fetch_fasta_headers(
    evidence_dir: Path,
    md5sum: str,
    file_name: str = "",
    is_gzipped: bool = True,
    use_cache: bool = True,
    url: str | None = None,
    **kwargs,
) -> list[str] | None:
    """Read contig names from a FASTA file on S3.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    Returns list of contig names (from > header lines, without >) or None.
    """
    if use_cache:
        cached = load_cached_evidence(evidence_dir, md5sum)
        if cached and "contig_names" in cached:
            return cached["contig_names"]

    try:
        content = _fetch_range(md5sum, 262144, timeout=60, url=url)  # 256KB
        raw_bytes = len(content)

        content = _decompress_if_gzipped(content, is_gzipped)
        text = _decode_bytes(content)

        contig_names = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('>'):
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

    except requests.Timeout:
        print(f"Timeout reading FASTA for {md5sum}")
        return None
    except Exception as e:
        print(f"Error reading FASTA for {md5sum}: {e}")
        return None


# =============================================================================
# GFA FETCHER
# =============================================================================

def parse_gfa_segment_tags(text: str) -> list[dict]:
    """Parse rGFA stable-sequence tags from the S (segment) lines of GFA text.

    Returns one dict per segment that carries at least one of `SN:Z:` (stable
    sequence name) and `SR:i:` (stable rank). Segments with neither — every
    segment of a plain GFA, such as a minigraph-cactus graph — are omitted, so
    a plain GFA yields an empty list.

    The sequence column is not sliced out into its own string: in a real graph it
    holds the full segment sequence and dominates the line, while the tags follow
    it. Splitting `text` into lines does copy each sequence once; the tag scan
    below avoids copying it a second time.

    `text` is expected to be the head of a file, so the final line is usually
    truncated mid-record; it is dropped unless `text` ends with a newline. A
    complete final line that happens to lack a trailing newline is dropped too.
    """
    lines = text.split("\n")
    if not text.endswith("\n"):
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
        for fld in line[pos + 1:].rstrip("\r").split("\t"):
            if fld.startswith("SN:Z:"):
                tags["SN"] = fld[5:]
            elif fld.startswith("SR:i:"):
                tags["SR"] = fld[5:]
        if tags:
            segments.append(tags)
    return segments


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
    """
    if use_cache:
        cached = load_cached_evidence(evidence_dir, md5sum)
        if cached and "gfa_segment_tags" in cached:
            return cached["gfa_segment_tags"]

    try:
        # end_byte is inclusive, so 262143 fetches exactly 256KiB.
        content = _fetch_range(md5sum, 262143, timeout=60, url=url)
        raw_bytes = len(content)

        content = _decompress_if_gzipped(content, is_gzipped)
        text = _decode_bytes(content)

        segment_tags = parse_gfa_segment_tags(text)

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

    except FetchError:
        raise  # already carries its reason — don't re-wrap as "FetchError: ..."
    except requests.Timeout as e:
        raise FetchError(f"Timeout reading GFA head: {e}") from e
    except Exception as e:
        # Wrapped, not swallowed: the caller turns this into a not_classified
        # record whose evidence names the cause. A programming error in the
        # parser therefore surfaces as `TypeError: ...` in the output rather
        # than silently deleting the file's row.
        raise FetchError(f"{type(e).__name__}: {e}") from e
