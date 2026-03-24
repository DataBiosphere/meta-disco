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


def _fetch_range(md5sum: str, end_byte: int, timeout: int = 60, url: str | None = None) -> bytes | None:
    """Fetch bytes 0 through end_byte (inclusive) from S3. Returns raw bytes or None.

    If url is provided, fetches from that URL directly. Otherwise uses the AnVIL S3 mirror.
    """
    fetch_url = url or f"{S3_MIRROR_URL}/{md5sum}.md5"
    headers = {"Range": f"bytes=0-{end_byte}"}
    resp = requests.get(fetch_url, headers=headers, timeout=timeout)
    if resp.status_code not in [200, 206]:
        return None
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
        if content is None:
            return None
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
        if content is None:
            return None
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
        if content is None:
            return None
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
