#!/usr/bin/env python3
"""Fetch FASTQ headers from S3 mirror for files needing header inspection.

Headers are cached in data/evidence/fastq/ for:
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
from src.meta_disco.header_classifier import classify_from_fastq_header, get_rules_documentation

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"
EVIDENCE_DIR = Path("data/evidence/fastq")


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


def save_header_evidence(md5sum: str, file_name: str, read_names: list[str], raw_bytes: int):
    """Save fetched header as evidence for audit trail."""
    path = get_evidence_path(md5sum)
    path.parent.mkdir(parents=True, exist_ok=True)

    evidence = {
        "md5sum": md5sum,
        "file_name": file_name,
        "read_names": read_names,
        "raw_bytes_fetched": raw_bytes,
        "fetch_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(path, "w") as f:
        json.dump(evidence, f, indent=2)


def get_fastq_reads(md5sum: str, file_name: str = "", is_gzipped: bool = True,
                    num_reads: int = 10, use_cache: bool = True) -> list[str] | None:
    """
    Read first N read names from a FASTQ file on S3.

    For gzipped files, fetches first chunk and decompresses.
    Returns list of read name lines (starting with @).

    Headers are cached in data/evidence/fastq/ for resumability.
    """
    # Check cache first
    if use_cache:
        cached = load_cached_header(md5sum)
        if cached and cached.get("read_names"):
            return cached["read_names"]

    url = f"{S3_MIRROR_URL}/{md5sum}.md5"

    try:
        # Fetch first 256KB - should be enough for several reads
        headers = {"Range": "bytes=0-262144"}
        resp = requests.get(url, headers=headers, timeout=60)

        if resp.status_code not in [200, 206]:
            return None

        content = resp.content
        raw_bytes = len(content)

        # Decompress if gzipped
        if is_gzipped and content[:2] == b'\x1f\x8b':
            try:
                decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                content = decompressor.decompress(content)
            except zlib.error:
                pass

        # Decode
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')

        # Extract read names (lines starting with @, every 4th line in FASTQ)
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

        # Save to cache for resumability
        if read_names:
            save_header_evidence(md5sum, file_name, read_names, raw_bytes)

        return read_names if read_names else None

    except requests.Timeout:
        print(f"Timeout reading FASTQ for {md5sum}")
        return None
    except Exception as e:
        print(f"Error reading FASTQ for {md5sum}: {e}")
        return None


def classify_single_fastq(
    md5sum: str,
    file_name: str = "",
    file_size: int | None = None,
    is_gzipped: bool = True,
    use_cache: bool = True,
) -> dict | None:
    """Fetch reads and classify a single FASTQ file by MD5."""
    read_names = get_fastq_reads(md5sum, file_name, is_gzipped, use_cache=use_cache)
    if not read_names:
        return None

    classification = classify_from_fastq_header(read_names, file_name)
    classification["file_name"] = file_name
    classification["md5sum"] = md5sum
    classification["file_size"] = file_size
    classification["reads_sampled"] = len(read_names)
    classification["sample_reads"] = read_names[:3]  # First 3 for preview

    return classification


def process_single_record(record: dict, resume: bool) -> tuple[dict | None, bool]:
    """Process a single FASTQ record. Returns (classification, was_cached)."""
    md5 = record.get("file_md5sum")
    file_name = record.get("file_name", "")
    file_size = record.get("file_size")
    file_format = record.get("file_format", "")
    entry_id = record.get("entry_id")

    # Check if gzipped
    is_gzipped = file_name.endswith(".gz") or file_format.endswith(".gz")

    # Check cache first
    was_cached = load_cached_header(md5) is not None

    result = classify_single_fastq(md5, file_name, file_size=file_size,
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


def process_fastq_files(input_path: Path, output_path: Path, limit: int | None = None,
                        resume: bool = True, workers: int = 1, skip_complete: bool = False,
                        skip_cached: bool = False):
    """Process FASTQ files that need header inspection.

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

    # Filter to FASTQ files with MD5
    fastq_extensions = [".fastq", ".fastq.gz", ".fq", ".fq.gz"]
    needs_inspection = [
        r for r in results
        if r.get("file_md5sum")  # Must have MD5
        and any(r.get("file_format", "").endswith(ext) or r.get("file_name", "").endswith(ext)
                for ext in fastq_extensions)
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

    print(f"Found {len(needs_inspection)} FASTQ files with MD5 for header inspection")

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
    print_fastq_classification_summary(classifications)


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


def print_fastq_classification_summary(classifications: list[dict]):
    """Print summary statistics of FASTQ classifications."""
    print("\n" + "=" * 70)
    print("FASTQ HEADER CLASSIFICATION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications to summarize.")
        return

    # Aggregate stats
    platforms = {}
    modalities = {}
    paired_count = 0
    instrument_models = {}
    archive_sources = {}

    def _val(rec, field):
        """Extract value from per-field or flat format."""
        # Check nested under "classifications" key
        cls = rec.get("classifications", {})
        if isinstance(cls, dict) and field in cls:
            v = cls[field]
            return v["value"] if isinstance(v, dict) and "value" in v else v
        # Check top-level (direct from to_output_dict)
        v = rec.get(field)
        if isinstance(v, dict) and "value" in v:
            return v["value"]
        return v

    for c in classifications:
        plat = _val(c, "platform") or "unknown"
        platforms[plat] = platforms.get(plat, 0) + 1

        mod = _val(c, "data_modality") or "unknown"
        modalities[mod] = modalities.get(mod, 0) + 1

        if c.get("is_paired_end"):
            paired_count += 1

        model = c.get("instrument_model")
        if model:
            instrument_models[model] = instrument_models.get(model, 0) + 1

        source = c.get("archive_source")
        if source:
            archive_sources[source] = archive_sources.get(source, 0) + 1

    print(f"\nTotal files classified: {len(classifications)}")
    print(f"  Paired-end detected: {paired_count}")

    print("\nPlatforms:")
    for plat, count in sorted(platforms.items(), key=lambda x: -x[1]):
        print(f"  {plat:<30} {count:>5}")

    print("\nData Modalities:")
    for mod, count in sorted(modalities.items(), key=lambda x: -x[1]):
        print(f"  {mod:<30} {count:>5}")

    if instrument_models:
        print("\nInstrument Models (Illumina):")
        for model, count in sorted(instrument_models.items(), key=lambda x: -x[1]):
            print(f"  {model:<30} {count:>5}")

    if archive_sources:
        print("\nArchive Accessions:")
        for source, count in sorted(archive_sources.items(), key=lambda x: -x[1]):
            print(f"  {source:<30} {count:>5}")

    # Show sample evidence
    print("\n" + "-" * 70)
    print("SAMPLE EVIDENCE (first 3 files):")
    print("-" * 70)

    for c in classifications[:3]:
        print(f"\nFile: {c.get('file_name', 'unknown')}")
        print(f"  Platform: {c.get('platform')}")
        print(f"  Modality: {c.get('data_modality')} (confidence: {c.get('confidence', 0):.0%})")
        print(f"  Paired-end: {c.get('is_paired_end')}")
        if c.get("instrument_model"):
            print(f"  Instrument: {c.get('instrument_model')}")
        if c.get("archive_accession"):
            print(f"  Archive: {c.get('archive_source')} - {c.get('archive_accession')}")
        print(f"  Sample read: {c.get('sample_reads', [''])[0][:70]}...")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Fetch FASTQ headers and classify")
    parser.add_argument("--input", "-i", type=str,
                        help="Input file (classification JSON or metadata NDJSON)")
    parser.add_argument("--output", "-o", type=str, default="output/fastq_classifications.json",
                        help="Output file for classifications")
    parser.add_argument("--limit", "-l", type=int, default=None,
                        help="Limit number of files to process")
    parser.add_argument("--md5", type=str,
                        help="Classify a single file by MD5 hash")
    parser.add_argument("--no-gzip", action="store_true",
                        help="File is not gzipped (default: assume gzipped)")
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
        print(f"Classifying FASTQ with MD5: {args.md5} (gzipped={is_gzipped})")
        result = classify_single_fastq(args.md5, is_gzipped=is_gzipped)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Failed to fetch or classify FASTQ")
        return

    if not args.input:
        parser.error("--input required unless using --md5 or --docs")

    process_fastq_files(
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
