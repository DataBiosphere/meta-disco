#!/usr/bin/env python3
"""Fetch BAM/CRAM headers from S3 mirror for files needing header inspection.

Headers are cached in data/evidence/bam/ for:
- Resumability after interruption
- Audit trail of classification evidence

Requires samtools to be installed and in PATH.
"""

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from src.meta_disco.header_classifier import classify_from_header, get_rules_documentation

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"
EVIDENCE_DIR = Path("data/evidence/bam")


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


def save_header_evidence(md5sum: str, file_name: str, header_text: str):
    """Save fetched header as evidence for audit trail."""
    path = get_evidence_path(md5sum)
    path.parent.mkdir(parents=True, exist_ok=True)

    evidence = {
        "md5sum": md5sum,
        "file_name": file_name,
        "header_text": header_text,
        "header_line_count": len(header_text.split('\n')),
        "fetch_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(path, "w") as f:
        json.dump(evidence, f, indent=2)


def get_bam_header(md5sum: str, file_name: str = "", use_cache: bool = True) -> str | None:
    """
    Read BAM/CRAM header from S3 mirror using samtools.

    Headers are cached in data/evidence/bam/ for resumability.
    """
    # Check cache first
    if use_cache:
        cached = load_cached_header(md5sum)
        if cached and cached.get("header_text"):
            return cached["header_text"]

    url = f"{S3_MIRROR_URL}/{md5sum}.md5"
    try:
        result = subprocess.run(
            ["samtools", "view", "-H", url],
            capture_output=True,
            text=True,
            timeout=120
        )
        if result.returncode != 0:
            return None

        header_text = result.stdout
        if header_text:
            # Save to cache for resumability
            save_header_evidence(md5sum, file_name, header_text)

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


def classify_single_file(
    md5sum: str,
    file_name: str = "",
    file_size: int | None = None,
    file_format: str | None = None,
    use_cache: bool = True,
) -> dict | None:
    """Fetch header and classify a single file by MD5."""
    header_text = get_bam_header(md5sum, file_name, use_cache=use_cache)
    if not header_text:
        return None

    full = classify_from_header(header_text, file_size=file_size, file_format=file_format)

    # Evidence files (data/evidence/) are immutable raw data — don't write
    # classification results back into them. Classifications go in output/.
    return {
        "file_name": file_name,
        "md5sum": md5sum,
        "file_size": file_size,
        "file_format": file_format,
        "data_modality": full.get("data_modality"),
        "data_type": full.get("data_type"),
        "assay_type": full.get("assay_type"),
        "reference_assembly": full.get("reference_assembly"),
        "platform": full.get("platform"),
        "confidence": full.get("confidence"),
        "is_aligned": full.get("is_aligned"),
        "rule_evidence": [
            {"rule_id": r, "reason": rsn}
            for r, rsn in zip(full.get("matched_rules", []), full.get("reasons", []))
        ],
    }


def process_single_record(record: dict, resume: bool) -> tuple[dict | None, bool]:
    """Process a single BAM/CRAM record. Returns (classification, was_cached)."""
    md5 = record.get("file_md5sum")
    file_name = record.get("file_name", "")
    file_size = record.get("file_size")
    file_format = record.get("file_format")
    entry_id = record.get("entry_id")

    # Check cache first
    was_cached = load_cached_header(md5) is not None

    result = classify_single_file(md5, file_name, file_size=file_size,
                                  file_format=file_format, use_cache=resume)

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


def process_files_needing_inspection(input_path: Path, output_path: Path, limit: int | None = None,
                                     resume: bool = True, workers: int = 1, skip_complete: bool = False,
                                     skip_cached: bool = False):
    """Process BAM/CRAM files that need header inspection.

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

    # Filter to BAM/CRAM files with MD5
    needs_inspection = [
        r for r in results
        if r.get("file_md5sum")  # Must have MD5
        and (r.get("file_format") in [".bam", ".cram"]
             or r.get("file_name", "").endswith((".bam", ".cram")))
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

    print(f"Found {len(needs_inspection)} BAM/CRAM files with MD5 for header inspection")

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

    writer = NdjsonWriter(output_path)

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
                writer.write(result)
                successful += 1
                if was_cached:
                    from_cache += 1
            else:
                failed += 1

            cache_indicator = "[cached] " if was_cached else ""
            print(f"\r[{processed}/{len(needs_inspection)}] {cache_indicator}{file_name[:45]:<52}", end="", flush=True)

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

    # Close writer and write final JSON
    writer.close()
    save_final(output_path, len(needs_inspection), successful, failed, from_cache)

    print(f"\nSaved to {output_path}")
    print(f"Evidence cached in: {EVIDENCE_DIR}/")

    # Read back for summary
    with open(output_path) as f:
        final_data = json.load(f)
    print_classification_summary(final_data.get("classifications", []))


def _ndjson_path(output_path: Path) -> Path:
    """Get the NDJSON progress file path for an output path."""
    return output_path.with_suffix(".ndjson")


class NdjsonWriter:
    """Append-only NDJSON writer with periodic flush."""

    def __init__(self, output_path: Path):
        self.path = _ndjson_path(output_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w")
        self._count = 0

    def write(self, record: dict):
        self._fh.write(json.dumps(record) + "\n")
        self._count += 1
        if self._count % 500 == 0:
            self._fh.flush()

    def close(self):
        self._fh.flush()
        self._fh.close()


def save_final(output_path: Path, total: int, successful: int, failed: int, from_cache: int):
    """Write final JSON output from NDJSON progress file."""
    ndjson = _ndjson_path(output_path)
    classifications = []
    if ndjson.exists():
        with open(ndjson) as f:
            for line in f:
                if line.strip():
                    classifications.append(json.loads(line))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_to_process": total,
                "processed": successful + failed,
                "successful": successful,
                "failed": failed,
                "from_cache": from_cache,
                "complete": True,
            },
            "classifications": classifications,
        }, f, indent=2)

    if ndjson.exists():
        ndjson.unlink()


def print_classification_summary(classifications: list[dict]):
    """Print summary statistics of classifications."""
    print("\n" + "=" * 70)
    print("BAM/CRAM HEADER CLASSIFICATION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications to summarize.")
        return

    # Aggregate stats
    modalities = {}
    references = {}
    platforms = {}
    aligned_count = 0
    unaligned_count = 0

    for c in classifications:
        mod = c.get("data_modality") or "unknown"
        modalities[mod] = modalities.get(mod, 0) + 1

        ref = c.get("reference_assembly") or "unknown"
        references[ref] = references.get(ref, 0) + 1

        plat = c.get("platform") or "unknown"
        platforms[plat] = platforms.get(plat, 0) + 1

        if c.get("is_aligned"):
            aligned_count += 1
        else:
            unaligned_count += 1

    print(f"\nTotal files classified: {len(classifications)}")
    print(f"  Aligned: {aligned_count}")
    print(f"  Unaligned: {unaligned_count}")

    print("\nData Modalities:")
    for mod, count in sorted(modalities.items(), key=lambda x: -x[1]):
        print(f"  {mod:<35} {count:>5}")

    print("\nReference Assemblies:")
    for ref, count in sorted(references.items(), key=lambda x: -x[1]):
        print(f"  {ref:<35} {count:>5}")

    print("\nPlatforms:")
    for plat, count in sorted(platforms.items(), key=lambda x: -x[1]):
        print(f"  {plat:<35} {count:>5}")

    # Show sample evidence
    print("\n" + "-" * 70)
    print("SAMPLE EVIDENCE (first 3 files):")
    print("-" * 70)

    for c in classifications[:3]:
        print(f"\nFile: {c.get('file_name', 'unknown')}")
        print(f"  Modality: {c.get('data_modality')} (confidence: {c.get('confidence', 0):.0%})")
        print(f"  Reference: {c.get('reference_assembly')}")
        print(f"  Platform: {c.get('platform')}")
        print(f"  Aligned: {c.get('is_aligned')}")
        print(f"  Rules matched: {', '.join(c.get('matched_rules', []))}")
        if c.get("evidence"):
            print("  Evidence:")
            for e in c["evidence"][:3]:
                print(f"    - {e['rule_id']}: {e['matched']}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Fetch BAM/CRAM headers and classify")
    parser.add_argument("--input", "-i", type=str,
                        help="Input file (classification JSON or metadata NDJSON)")
    parser.add_argument("--output", "-o", type=str, default="output/bam_classifications.json",
                        help="Output file for classifications")
    parser.add_argument("--limit", "-l", type=int, default=None,
                        help="Limit number of files to process")
    parser.add_argument("--md5", type=str,
                        help="Classify a single file by MD5 hash")
    parser.add_argument("--no-resume", action="store_true",
                        help="Don't use cached headers, re-fetch all")
    parser.add_argument("--workers", "-w", type=int, default=4,
                        help="Number of parallel workers (default: 4)")
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
        print(f"Classifying file with MD5: {args.md5}")
        result = classify_single_file(args.md5)
        if result:
            print(json.dumps(result, indent=2))
            print("\nEvidence:")
            for e in result.get("evidence", []):
                print(f"\n  Rule: {e['rule_id']}")
                print(f"  Matched: {e['matched']}")
                print(f"  Classification: {e['classification']}")
                print(f"  Confidence: {e['confidence']:.0%}")
                print(f"  Rationale: {e['rationale']}")
        else:
            print("Failed to fetch or classify header")
        return

    if not args.input:
        parser.error("--input required unless using --md5 or --docs")

    process_files_needing_inspection(
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
