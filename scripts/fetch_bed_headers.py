#!/usr/bin/env python3
"""Fetch BED file headers from S3 mirror for reference assembly detection.

BED files don't have formal headers, but we can infer the reference assembly
from chromosome names and max coordinates in the first N lines:
- Chromosome naming: 'chr1' vs '1' (GRCh37/b37 often omits 'chr' prefix)
- Max coordinates: each reference has unique chromosome lengths, so a
  coordinate exceeding a reference's chromosome length rules it out.

Evidence is cached in data/evidence/anvil/bed/ for resumability and audit trail.
"""

import argparse
import json
import sys
import time
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests

from src.meta_disco.header_classifier import classify_from_bed_signals

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"
EVIDENCE_DIR = Path("data/evidence/anvil/bed")


def get_evidence_path(md5sum: str) -> Path:
    """Get path for cached evidence file."""
    return EVIDENCE_DIR / md5sum[:2] / f"{md5sum}.json"


def load_cached_evidence(md5sum: str) -> dict | None:
    """Load cached evidence if it exists."""
    path = get_evidence_path(md5sum)
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def save_evidence(md5sum: str, file_name: str, evidence: dict):
    """Save fetched evidence for audit trail."""
    path = get_evidence_path(md5sum)
    path.parent.mkdir(parents=True, exist_ok=True)

    evidence.update({
        "md5sum": md5sum,
        "file_name": file_name,
        "fetch_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    with open(path, "w") as f:
        json.dump(evidence, f, indent=2)


def fetch_bed_signals(md5sum: str, is_gzipped: bool = True,
                      file_size: int | None = None) -> dict | None:
    """Fetch BED data from S3 and extract reference signals in one pass.

    Instead of storing all lines, we stream through and track only:
    - Chromosome names seen
    - Max end coordinate per chromosome

    Fetch size adapts to file size:
    - Small files (<1MB): fetch the whole file
    - Medium files (1-10MB): fetch entire file
    - Large files (>10MB): fetch 10MB (enough for ~1.3M BED lines after decompression)

    Args:
        md5sum: File MD5 hash for S3 lookup
        is_gzipped: Whether file is gzip-compressed
        file_size: Known file size in bytes (used to pick fetch size)

    Returns:
        Signals dict or None on failure
    """
    # Adaptive fetch size: small files get fetched whole, large ones get 10MB
    # HTTP Range end offset is inclusive, so bytes=0-N fetches N+1 bytes
    if file_size and file_size <= 10_000_000:
        fetch_bytes = file_size - 1
    else:
        fetch_bytes = 10_485_759  # 10MB (inclusive end)

    url = f"{S3_MIRROR_URL}/{md5sum}.md5"

    try:
        headers = {"Range": f"bytes=0-{fetch_bytes}"}
        resp = requests.get(url, headers=headers, timeout=120)

        if resp.status_code not in [200, 206]:
            return None

        content = resp.content

        # Decompress if gzipped (handle bgzip: multiple concatenated gzip blocks)
        if is_gzipped and content[:2] == b'\x1f\x8b':
            try:
                decompressed = bytearray()
                pos = 0
                while pos < len(content):
                    if content[pos:pos+2] != b'\x1f\x8b':
                        break
                    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    try:
                        chunk = decompressor.decompress(content[pos:])
                        decompressed.extend(chunk)
                        consumed = len(content[pos:]) - len(decompressor.unused_data)
                        pos += consumed
                    except zlib.error:
                        break
                content = bytes(decompressed) if decompressed else content
            except Exception:
                pass

        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')

        # Extract signals in one pass — no line storage
        return extract_bed_signals(text.split('\n'))

    except requests.Timeout:
        return None
    except Exception as e:
        print(f"Error fetching {md5sum}: {e}")
        return None


def extract_bed_signals(lines: list[str]) -> dict:
    """Extract reference assembly signals from BED lines.

    Returns dict with:
        - chromosomes: set of chromosome names seen
        - has_chr_prefix: whether chromosomes use 'chr' prefix
        - max_coordinates: dict of chrom -> max end coordinate
        - line_count: number of lines analyzed
    """
    chromosomes = set()
    max_coords: dict[str, int] = defaultdict(int)
    line_count = 0

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('track') or line.startswith('browser'):
            continue

        parts = line.split('\t')
        if len(parts) < 3:
            continue

        line_count += 1
        chrom = parts[0]
        chromosomes.add(chrom)

        try:
            end = int(parts[2])  # BED end coordinate (0-based, exclusive)
            if end > max_coords[chrom]:
                max_coords[chrom] = end
        except ValueError:
            continue

    has_chr_prefix = any(c.startswith('chr') for c in chromosomes)

    return {
        "chromosomes": sorted(chromosomes),
        "has_chr_prefix": has_chr_prefix,
        "max_coordinates": dict(max_coords),
        "line_count": line_count,
    }


def classify_bed_file(md5sum: str, file_name: str, file_size: int | None = None,
                      is_gzipped: bool = True, use_cache: bool = True) -> dict | None:
    """Fetch BED lines and infer reference assembly.

    Args:
        md5sum: File MD5 for S3 lookup
        file_name: Original filename
        file_size: File size in bytes
        is_gzipped: Whether file is gzip-compressed
        use_cache: Whether to use cached evidence

    Returns:
        Classification dict or None on failure
    """
    # Check cache
    from_cache = False
    if use_cache:
        cached = load_cached_evidence(md5sum)
        if cached and cached.get("signals"):
            signals = cached["signals"]
            from_cache = True
        else:
            signals = None
    else:
        signals = None

    # Fetch if not cached
    if signals is None:
        signals = fetch_bed_signals(md5sum, is_gzipped=is_gzipped, file_size=file_size)
        if not signals:
            return None
        save_evidence(md5sum, file_name, {"signals": signals})

    # Classify using the unified classifier
    classifications = classify_from_bed_signals(
        signals, file_name=file_name, file_size=file_size,
    )

    return {
        "file_name": file_name,
        "md5sum": md5sum,
        "file_size": file_size,
        "classifications": classifications,
        "signals": signals,
        "from_cache": from_cache,
    }


def process_bed_files(input_path: Path, output_path: Path, limit: int | None = None,
                      resume: bool = True, workers: int = 10):
    """Process BED files that need reference detection.

    Args:
        input_path: Path to metadata JSON
        output_path: Path to save results
        limit: Maximum files to process
        resume: Use cached evidence
        workers: Parallel workers
    """
    with open(input_path) as f:
        data = json.load(f)
    files = data if isinstance(data, list) else data.get("files", data)

    # Filter to BED files with MD5
    bed_files = [
        f for f in files
        if f.get("file_md5sum")
        and (f.get("file_name", "").endswith(".bed") or f.get("file_name", "").endswith(".bed.gz"))
    ]

    print(f"Found {len(bed_files)} BED files with MD5")

    if limit:
        bed_files = bed_files[:limit]
        print(f"Processing first {limit} files")

    # Check cache (after limit slice to avoid scanning full list)
    cached_count = sum(1 for f in bed_files if load_cached_evidence(f["file_md5sum"]) is not None)
    print(f"  Already cached: {cached_count}")
    print(f"  Remaining to fetch: {len(bed_files) - cached_count}")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    classifications = []
    successful = 0
    failed = 0
    from_cache = 0
    processed = 0
    lock = Lock()

    print(f"Using {workers} parallel workers")

    def process_one(record: dict) -> tuple[dict | None, bool]:
        md5 = record["file_md5sum"]
        file_name = record.get("file_name", "")
        file_size = record.get("file_size")
        is_gzipped = file_name.endswith(".gz")
        was_cached = load_cached_evidence(md5) is not None

        result = classify_bed_file(md5, file_name, file_size=file_size,
                                   is_gzipped=is_gzipped, use_cache=resume)
        if result:
            result["dataset_title"] = record.get("dataset_title")
            result["entry_id"] = record.get("entry_id")
        return result, was_cached

    if workers == 1:
        for record in bed_files:
            result, was_cached = process_one(record)
            processed += 1
            if result:
                classifications.append(result)
                successful += 1
                if was_cached:
                    from_cache += 1
            else:
                failed += 1
            print(f"\r[{processed}/{len(bed_files)}] {record.get('file_name', '')[:50]:<55}",
                  end="", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_record = {
                executor.submit(process_one, record): record
                for record in bed_files
            }
            for future in as_completed(future_to_record):
                record = future_to_record[future]
                try:
                    result, was_cached = future.result()
                    with lock:
                        processed += 1
                        if result:
                            classifications.append(result)
                            successful += 1
                            if was_cached:
                                from_cache += 1
                        else:
                            failed += 1
                        print(f"\r[{processed}/{len(bed_files)}] {record.get('file_name', '')[:50]:<55}",
                              end="", flush=True)
                except Exception as e:
                    with lock:
                        processed += 1
                        failed += 1
                    print(f"\nError: {record.get('file_name')}: {e}")

    print(f"\n\nSuccessful: {successful}")
    print(f"  From cache: {from_cache}")
    print(f"  New fetches: {successful - from_cache}")
    print(f"Failed: {failed}")

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_to_process": len(bed_files),
                "processed": processed,
                "successful": successful,
                "failed": failed,
                "from_cache": from_cache,
            },
            "classifications": classifications,
        }, f, indent=2)

    print(f"Saved to {output_path}")

    # Summary
    print_summary(classifications)


def print_summary(classifications: list[dict]):
    """Print classification summary."""
    print("\n" + "=" * 70)
    print("BED REFERENCE DETECTION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications.")
        return

    refs = defaultdict(int)
    for c in classifications:
        cls = c.get("classifications", {})
        ref_entry = cls.get("reference_assembly", {})
        ref = ref_entry.get("value") if isinstance(ref_entry, dict) else "not_classified"
        refs[ref or "not_classified"] += 1

    print(f"\nTotal: {len(classifications)}")
    print("\nReference assemblies:")
    for ref, count in sorted(refs.items(), key=lambda x: -x[1]):
        print(f"  {ref:<20} {count:>6} ({100*count/len(classifications):.1f}%)")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Fetch BED file headers for reference detection")
    parser.add_argument("--input", "-i", type=str, default="data/anvil/anvil_files_metadata.json",
                        help="Input metadata file")
    parser.add_argument("--output", "-o", type=str, default="output/anvil/bed_reference_detection.json",
                        help="Output file for results")
    parser.add_argument("--limit", "-l", type=int, default=None,
                        help="Limit number of files")
    parser.add_argument("--md5", type=str,
                        help="Classify a single file by MD5")
    parser.add_argument("--no-resume", action="store_true",
                        help="Don't use cached evidence")
    parser.add_argument("--workers", "-w", type=int, default=10,
                        help="Parallel workers (default: 10)")
    args = parser.parse_args()

    if args.md5:
        print(f"Classifying BED with MD5: {args.md5}")
        result = classify_bed_file(args.md5, "unknown.bed.gz", use_cache=not args.no_resume)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Failed to fetch or classify")
        return

    process_bed_files(
        Path(args.input),
        Path(args.output),
        limit=args.limit,
        resume=not args.no_resume,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
