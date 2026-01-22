#!/usr/bin/env python3
"""Fetch FASTQ headers from S3 mirror for files needing header inspection."""

import argparse
import json
import sys
import time
import zlib
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from src.meta_disco.header_classifier import classify_from_fastq_header, get_rules_documentation

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"


def get_fastq_reads(md5sum: str, is_gzipped: bool = True, num_reads: int = 10) -> list[str] | None:
    """
    Read first N read names from a FASTQ file on S3.

    For gzipped files, fetches first chunk and decompresses.
    Returns list of read name lines (starting with @).
    """
    url = f"{S3_MIRROR_URL}/{md5sum}.md5"

    try:
        # Fetch first 256KB - should be enough for several reads
        headers = {"Range": "bytes=0-262144"}
        resp = requests.get(url, headers=headers, timeout=60)

        if resp.status_code not in [200, 206]:
            return None

        content = resp.content

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
) -> dict | None:
    """Fetch reads and classify a single FASTQ file by MD5."""
    read_names = get_fastq_reads(md5sum, is_gzipped)
    if not read_names:
        return None

    classification = classify_from_fastq_header(read_names, file_name)
    classification["file_name"] = file_name
    classification["md5sum"] = md5sum
    classification["file_size"] = file_size
    classification["reads_sampled"] = len(read_names)
    classification["sample_reads"] = read_names[:3]  # First 3 for preview

    return classification


def process_fastq_files(input_path: Path, output_path: Path, limit: int | None = None):
    """Process FASTQ files that need header inspection."""

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

    print(f"Found {len(needs_inspection)} FASTQ files with MD5 for header inspection")

    if limit:
        needs_inspection = needs_inspection[:limit]
        print(f"Processing first {limit} files")

    classifications = []
    successful = 0
    failed = 0

    for i, record in enumerate(needs_inspection):
        md5 = record.get("file_md5sum")
        file_name = record.get("file_name", "")
        file_size = record.get("file_size")
        file_format = record.get("file_format", "")
        entry_id = record.get("entry_id")

        # Check if gzipped
        is_gzipped = file_name.endswith(".gz") or file_format.endswith(".gz")

        print(f"\r[{i+1}/{len(needs_inspection)}] {file_name[:50]:<52}", end="", flush=True)

        result = classify_single_fastq(md5, file_name, file_size=file_size, is_gzipped=is_gzipped)

        if result:
            result["entry_id"] = entry_id
            result["original_record"] = {
                "file_format": file_format,
                "file_size": file_size,
                "dataset_title": record.get("dataset_title"),
            }
            classifications.append(result)
            successful += 1
        else:
            failed += 1

        # Brief delay to be nice to servers
        time.sleep(0.1)

    print(f"\n\nSuccessfully classified: {successful}")
    print(f"Failed to fetch header: {failed}")

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_processed": len(needs_inspection),
                "successful": successful,
                "failed": failed,
            },
            "classifications": classifications,
        }, f, indent=2)

    print(f"\nSaved to {output_path}")

    # Print summary
    print_fastq_classification_summary(classifications)


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

    for c in classifications:
        plat = c.get("platform") or "unknown"
        platforms[plat] = platforms.get(plat, 0) + 1

        mod = c.get("data_modality") or "unknown"
        modalities[mod] = modalities.get(mod, 0) + 1

        if c.get("is_paired_end"):
            paired_count += 1

        model = c.get("instrument_model")
        if model:
            instrument_models[model] = instrument_models.get(model, 0) + 1

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
        print(f"  Sample read: {c.get('sample_reads', [''])[0][:70]}...")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Fetch FASTQ headers and classify")
    parser.add_argument("--input", "-i", type=str,
                        help="Input file (classification JSON or metadata NDJSON)")
    parser.add_argument("--output", "-o", type=str, default="output/fastq_headers.json",
                        help="Output file for classifications")
    parser.add_argument("--limit", "-l", type=int, default=None,
                        help="Limit number of files to process")
    parser.add_argument("--md5", type=str,
                        help="Classify a single file by MD5 hash")
    parser.add_argument("--gzipped", action="store_true", default=True,
                        help="File is gzipped (default: True)")
    parser.add_argument("--no-gzip", action="store_true",
                        help="File is not gzipped")
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
        args.limit
    )


if __name__ == "__main__":
    main()
