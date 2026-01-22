#!/usr/bin/env python3
"""Fetch BAM/CRAM headers from S3 mirror for files needing header inspection."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from src.meta_disco.header_classifier import classify_from_header, get_rules_documentation

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"
API_URL = "https://service.explore.anvilproject.org/index/files"


def get_md5_from_api(entry_id: str) -> str | None:
    """Fetch MD5 hash from API for a single file."""
    try:
        resp = requests.get(f"{API_URL}/{entry_id}", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        files = data.get("files", [{}])
        if files:
            return files[0].get("file_md5sum")
    except Exception as e:
        print(f"Error fetching MD5 for {entry_id}: {e}")
    return None


def get_bam_header(md5sum: str) -> str | None:
    """Read BAM header from S3 mirror using samtools."""
    url = f"{S3_MIRROR_URL}/{md5sum}.md5"
    try:
        result = subprocess.run(
            ["samtools", "view", "-H", url],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        print(f"Timeout reading header for {md5sum}")
        return None
    except Exception as e:
        print(f"Error reading header for {md5sum}: {e}")
        return None


def classify_single_file(
    md5sum: str,
    file_name: str = "",
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict | None:
    """Fetch header and classify a single file by MD5."""
    header_text = get_bam_header(md5sum)
    if not header_text:
        return None

    classification = classify_from_header(header_text, file_size=file_size, file_format=file_format)
    classification["file_name"] = file_name
    classification["md5sum"] = md5sum
    classification["file_size"] = file_size
    classification["file_format"] = file_format
    classification["header_preview"] = header_text[:500] + "..." if len(header_text) > 500 else header_text

    return classification


def process_files_needing_inspection(input_path: Path, output_path: Path, limit: int | None = None):
    """Process files that need header inspection."""

    # Load classification results or raw metadata
    with open(input_path) as f:
        if input_path.suffix == ".ndjson":
            results = [json.loads(line) for line in f if line.strip()]
        else:
            data = json.load(f)
            results = data.get("results", data.get("files", data))

    # Filter to files needing header inspection (BAM/CRAM only) with MD5
    needs_inspection = [
        r for r in results
        if r.get("file_md5sum")  # Must have MD5
        and r.get("file_format") in [".bam", ".cram"]
        and not r.get("skip")
        and (r.get("needs_header_inspection") or r.get("needs_header_inspection") is None)
    ]

    print(f"Found {len(needs_inspection)} BAM/CRAM files with MD5 needing header inspection")

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
        file_format = record.get("file_format")
        entry_id = record.get("entry_id")

        print(f"\r[{i+1}/{len(needs_inspection)}] {file_name[:40]:<42}", end="", flush=True)

        result = classify_single_file(md5, file_name, file_size=file_size, file_format=file_format)

        if result:
            result["entry_id"] = entry_id
            result["original_record"] = {
                "file_format": record.get("file_format"),
                "file_size": record.get("file_size"),
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
    print_classification_summary(classifications)


def print_classification_summary(classifications: list[dict]):
    """Print summary statistics of classifications."""
    print("\n" + "=" * 70)
    print("HEADER CLASSIFICATION SUMMARY")
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
                print(f"      Rationale: {e['rationale'][:80]}...")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Fetch BAM headers and classify")
    parser.add_argument("--input", "-i", type=str,
                        help="Input file (classification JSON or metadata NDJSON)")
    parser.add_argument("--output", "-o", type=str, default="output/bam_headers.json",
                        help="Output file for classifications")
    parser.add_argument("--limit", "-l", type=int, default=None,
                        help="Limit number of files to process")
    parser.add_argument("--md5", type=str,
                        help="Classify a single file by MD5 hash")
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
        args.limit
    )


if __name__ == "__main__":
    main()
