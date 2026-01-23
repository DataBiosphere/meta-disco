#!/usr/bin/env python3
"""Fetch VCF headers from S3 mirror for files needing header inspection.

Headers are cached in data/evidence/vcf/ for:
- Resumability after interruption
- Audit trail of classification evidence
"""

import argparse
import json
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from src.meta_disco.header_classifier import classify_from_vcf_header, get_rules_documentation

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"
EVIDENCE_DIR = Path("data/evidence/vcf")


def get_evidence_path(md5sum: str) -> Path:
    """Get path for cached header evidence file."""
    # Use first 2 chars of MD5 as subdirectory to avoid too many files in one dir
    return EVIDENCE_DIR / md5sum[:2] / f"{md5sum}.json"


def load_cached_header(md5sum: str) -> dict | None:
    """Load cached header if it exists."""
    path = get_evidence_path(md5sum)
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def extract_max_positions(variant_lines: list[str], max_variants: int = 100) -> dict[str, int]:
    """Extract max position per chromosome from variant lines.

    This is used for reference assembly detection when header-based
    detection fails. Only stores the max position per chromosome,
    not the raw variant data.
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


def save_header_evidence(md5sum: str, file_name: str, header_text: str,
                         raw_bytes: int, max_positions: dict[str, int] | None = None):
    """Save fetched header as evidence for audit trail."""
    path = get_evidence_path(md5sum)
    path.parent.mkdir(parents=True, exist_ok=True)

    evidence = {
        "md5sum": md5sum,
        "file_name": file_name,
        "header_text": header_text,
        "header_line_count": len(header_text.split('\n')),
        "raw_bytes_fetched": raw_bytes,
        "fetch_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if max_positions:
        evidence["max_positions"] = max_positions

    with open(path, "w") as f:
        json.dump(evidence, f, indent=2)


def get_vcf_header(md5sum: str, file_name: str = "", is_gzipped: bool = True,
                   use_cache: bool = True) -> str | None:
    """
    Read VCF header from S3 mirror.

    VCF headers are all lines starting with # at the beginning of the file.
    For gzipped VCFs, we fetch the first chunk and decompress.

    Headers are cached in data/evidence/vcf/ for resumability.
    """
    # Check cache first
    if use_cache:
        cached = load_cached_header(md5sum)
        if cached and cached.get("header_text"):
            return cached["header_text"]

    url = f"{S3_MIRROR_URL}/{md5sum}.md5"

    try:
        # Fetch first 1MB - should be enough for headers
        headers = {"Range": "bytes=0-1048576"}
        resp = requests.get(url, headers=headers, timeout=60)

        if resp.status_code not in [200, 206]:
            return None

        content = resp.content
        raw_bytes = len(content)

        # Decompress if gzipped
        if is_gzipped and content[:2] == b'\x1f\x8b':
            try:
                # Use zlib with gzip header handling for partial data
                decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                content = decompressor.decompress(content)
            except zlib.error:
                # Maybe it's not actually gzipped or corrupted
                pass

        # Decode and extract header lines
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')

        # Extract header lines and variant lines
        header_lines = []
        variant_lines = []
        in_header = True

        for line in text.split('\n'):
            if line.startswith('#'):
                header_lines.append(line)
            elif line.strip():
                in_header = False
                # Collect variant lines for position-based reference detection
                if len(variant_lines) < 100:
                    variant_lines.append(line)

        if header_lines:
            header_text = '\n'.join(header_lines)
            # Extract max positions from variant lines (for fallback ref detection)
            max_positions = extract_max_positions(variant_lines) if variant_lines else None
            # Save to cache for resumability
            save_header_evidence(md5sum, file_name, header_text, raw_bytes, max_positions)
            return header_text

        return None

    except requests.Timeout:
        print(f"Timeout reading header for {md5sum}")
        return None
    except Exception as e:
        print(f"Error reading header for {md5sum}: {e}")
        return None


def classify_single_vcf(
    md5sum: str,
    file_name: str = "",
    file_size: int | None = None,
    is_gzipped: bool = True,
    use_cache: bool = True,
) -> dict | None:
    """Fetch header and classify a single VCF file by MD5."""
    header_text = get_vcf_header(md5sum, file_name, is_gzipped, use_cache=use_cache)
    if not header_text:
        return None

    # Load max_positions from cache for fallback reference detection
    cached = load_cached_header(md5sum)
    max_positions = cached.get("max_positions") if cached else None

    classification = classify_from_vcf_header(
        header_text, file_size=file_size, max_positions=max_positions
    )
    classification["file_name"] = file_name
    classification["md5sum"] = md5sum
    classification["file_size"] = file_size
    classification["header_line_count"] = len(header_text.split('\n'))
    classification["header_preview"] = header_text[:1000] + "..." if len(header_text) > 1000 else header_text

    return classification


def process_single_record(record: dict, resume: bool) -> tuple[dict | None, bool]:
    """Process a single VCF record. Returns (classification, was_cached)."""
    md5 = record.get("file_md5sum")
    file_name = record.get("file_name", "")
    file_size = record.get("file_size")
    file_format = record.get("file_format", "")
    entry_id = record.get("entry_id")

    # Check if gzipped
    is_gzipped = file_name.endswith(".gz") or file_format.endswith(".gz")

    # Check cache first
    was_cached = load_cached_header(md5) is not None

    result = classify_single_vcf(md5, file_name, file_size=file_size,
                                 is_gzipped=is_gzipped, use_cache=resume)

    if result:
        result["entry_id"] = entry_id
        result["original_record"] = {
            "file_format": file_format,
            "file_size": file_size,
            "dataset_title": record.get("dataset_title"),
        }
        result["from_cache"] = was_cached
        return result, was_cached

    return None, was_cached


def process_vcf_files(input_path: Path, output_path: Path, limit: int | None = None,
                      resume: bool = True, workers: int = 1, skip_complete: bool = False,
                      skip_cached: bool = False):
    """Process VCF files that need header inspection.

    Args:
        input_path: Path to classification results JSON
        output_path: Path to save header classifications
        limit: Maximum number of files to process
        resume: If True, use cached headers instead of re-fetching
        workers: Number of parallel workers (default: 1)
        skip_complete: If True, skip if output already has all files classified
        skip_cached: If True, skip files entirely if header is already cached (no re-analysis)
    """

    # Load classification results or raw metadata
    with open(input_path) as f:
        if input_path.suffix == ".ndjson":
            results = [json.loads(line) for line in f if line.strip()]
        else:
            data = json.load(f)
            results = data.get("results", data.get("files", data))

    # Filter to VCF files with MD5
    vcf_extensions = [".vcf", ".vcf.gz", ".g.vcf.gz", ".gvcf.gz"]
    needs_inspection = [
        r for r in results
        if r.get("file_md5sum")  # Must have MD5
        and any(r.get("file_format", "").endswith(ext) or r.get("file_name", "").endswith(ext)
                for ext in vcf_extensions)
        and not r.get("skip")
    ]

    # Check if output is already complete
    if skip_complete and output_path.exists():
        try:
            with open(output_path) as f:
                existing = json.load(f)
            existing_count = len(existing.get("classifications", []))
            if existing.get("metadata", {}).get("complete") and existing_count >= len(needs_inspection):
                print(f"Output already complete with {existing_count} classifications. Skipping.")
                return
        except (json.JSONDecodeError, IOError):
            pass

    print(f"Found {len(needs_inspection)} VCF files with MD5 for header inspection")

    # Check how many are already cached
    cached_count = sum(1 for r in needs_inspection
                       if load_cached_header(r.get("file_md5sum")) is not None)
    print(f"  Already cached: {cached_count}")
    print(f"  Remaining to fetch: {len(needs_inspection) - cached_count}")

    # Skip cached files entirely if requested (no re-analysis)
    if skip_cached and cached_count > 0:
        needs_inspection = [r for r in needs_inspection
                          if load_cached_header(r.get("file_md5sum")) is None]
        print(f"  Skipping cached files, processing only {len(needs_inspection)} new files")

    if limit:
        needs_inspection = needs_inspection[:limit]
        print(f"Processing first {limit} files")

    # Ensure evidence directory exists
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    classifications = []
    successful = 0
    failed = 0
    from_cache = 0
    processed = 0

    # Thread-safe lock for updating shared state
    lock = Lock()

    print(f"Using {workers} parallel workers")

    def update_progress(result, was_cached, file_name):
        nonlocal successful, failed, from_cache, processed
        with lock:
            processed += 1
            if result:
                classifications.append(result)
                successful += 1
                if was_cached:
                    from_cache += 1
            else:
                failed += 1

            cache_indicator = "[cached] " if was_cached else ""
            print(f"\r[{processed}/{len(needs_inspection)}] {cache_indicator}{file_name[:45]:<52}", end="", flush=True)

            # Save incremental progress every 500 files
            if processed % 500 == 0:
                save_progress(output_path, classifications, len(needs_inspection), successful, failed, from_cache)

    if workers == 1:
        # Sequential processing
        for record in needs_inspection:
            result, was_cached = process_single_record(record, resume)
            update_progress(result, was_cached, record.get("file_name", ""))
    else:
        # Parallel processing
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks
            future_to_record = {
                executor.submit(process_single_record, record, resume): record
                for record in needs_inspection
            }

            # Process as they complete
            for future in as_completed(future_to_record):
                record = future_to_record[future]
                try:
                    result, was_cached = future.result()
                    update_progress(result, was_cached, record.get("file_name", ""))
                except Exception as e:
                    print(f"\nError processing {record.get('file_name')}: {e}")
                    with lock:
                        processed += 1
                        failed += 1

    print(f"\n\nSuccessfully classified: {successful}")
    print(f"  From cache: {from_cache}")
    print(f"  New fetches: {successful - from_cache}")
    print(f"Failed to fetch header: {failed}")

    # Save final results
    save_progress(output_path, classifications, len(needs_inspection), successful, failed, from_cache, final=True)

    print(f"\nSaved to {output_path}")
    print(f"Evidence cached in: {EVIDENCE_DIR}/")

    # Print summary
    print_vcf_classification_summary(classifications)


def save_progress(output_path: Path, classifications: list, total: int,
                  successful: int, failed: int, from_cache: int, final: bool = False):
    """Save current progress to output file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_to_process": total,
                "processed": successful + failed,
                "successful": successful,
                "failed": failed,
                "from_cache": from_cache,
                "complete": final,
            },
            "classifications": classifications,
        }, f, indent=2)


def print_vcf_classification_summary(classifications: list[dict]):
    """Print summary statistics of VCF classifications."""
    print("\n" + "=" * 70)
    print("VCF HEADER CLASSIFICATION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications to summarize.")
        return

    # Aggregate stats
    modalities = {}
    variant_types = {}
    references = {}
    callers = {}

    for c in classifications:
        mod = c.get("data_modality") or "unknown"
        modalities[mod] = modalities.get(mod, 0) + 1

        vtype = c.get("variant_type") or "unknown"
        variant_types[vtype] = variant_types.get(vtype, 0) + 1

        ref = c.get("reference_assembly") or "unknown"
        references[ref] = references.get(ref, 0) + 1

        caller = c.get("caller") or "unknown"
        # Truncate long caller names
        caller = caller[:40] + "..." if len(caller) > 40 else caller
        callers[caller] = callers.get(caller, 0) + 1

    print(f"\nTotal files classified: {len(classifications)}")

    print("\nData Modalities:")
    for mod, count in sorted(modalities.items(), key=lambda x: -x[1]):
        print(f"  {mod:<40} {count:>5}")

    print("\nVariant Types:")
    for vtype, count in sorted(variant_types.items(), key=lambda x: -x[1]):
        print(f"  {vtype:<40} {count:>5}")

    print("\nReference Assemblies:")
    for ref, count in sorted(references.items(), key=lambda x: -x[1]):
        print(f"  {ref:<40} {count:>5}")

    print("\nVariant Callers:")
    for caller, count in sorted(callers.items(), key=lambda x: -x[1])[:15]:
        print(f"  {caller:<40} {count:>5}")

    # Show sample evidence
    print("\n" + "-" * 70)
    print("SAMPLE EVIDENCE (first 3 files):")
    print("-" * 70)

    for c in classifications[:3]:
        print(f"\nFile: {c.get('file_name', 'unknown')}")
        print(f"  Modality: {c.get('data_modality')} (confidence: {c.get('confidence', 0):.0%})")
        print(f"  Variant Type: {c.get('variant_type')}")
        print(f"  Reference: {c.get('reference_assembly')}")
        print(f"  Caller: {c.get('caller')}")
        print(f"  Rules matched: {', '.join(c.get('matched_rules', [])[:5])}")
        if c.get("warnings"):
            print(f"  Warnings: {c['warnings']}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Fetch VCF headers and classify")
    parser.add_argument("--input", "-i", type=str,
                        help="Input file (classification JSON or metadata NDJSON)")
    parser.add_argument("--output", "-o", type=str, default="output/vcf_headers.json",
                        help="Output file for classifications")
    parser.add_argument("--limit", "-l", type=int, default=None,
                        help="Limit number of files to process")
    parser.add_argument("--md5", type=str,
                        help="Classify a single file by MD5 hash")
    parser.add_argument("--gzipped", action="store_true", default=True,
                        help="File is gzipped (default: True)")
    parser.add_argument("--no-gzip", action="store_true",
                        help="File is not gzipped")
    parser.add_argument("--no-resume", action="store_true",
                        help="Don't use cached headers, re-fetch all")
    parser.add_argument("--workers", "-w", type=int, default=10,
                        help="Number of parallel workers (default: 10)")
    parser.add_argument("--skip-complete", action="store_true",
                        help="Skip if output file already has all files classified")
    parser.add_argument("--skip-cached", action="store_true",
                        help="Skip files entirely if header is already cached (no re-analysis)")
    parser.add_argument("--docs", action="store_true",
                        help="Print rules documentation and exit")
    args = parser.parse_args()

    if args.docs:
        print(get_rules_documentation())
        return

    if args.md5:
        is_gzipped = not args.no_gzip
        print(f"Classifying VCF with MD5: {args.md5} (gzipped={is_gzipped})")
        result = classify_single_vcf(args.md5, is_gzipped=is_gzipped)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Failed to fetch or classify header")
        return

    if not args.input:
        parser.error("--input required unless using --md5 or --docs")

    process_vcf_files(
        Path(args.input),
        Path(args.output),
        args.limit,
        resume=not args.no_resume,
        workers=args.workers,
        skip_complete=args.skip_complete,
        skip_cached=args.skip_cached
    )


if __name__ == "__main__":
    main()
