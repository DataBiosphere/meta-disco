#!/usr/bin/env python3 -u
"""Validate classifications against HPRC metadata.

Cross-references our platform classifications with the official HPRC
sample metadata from GitHub.

Usage:
    python scripts/validate_hprc_samples.py
    python scripts/validate_hprc_samples.py --limit 100

Output saved to: output/hprc_validation_results.json
"""

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import requests

HPRC_BASE_URL = "https://raw.githubusercontent.com/human-pangenomics/hprc_intermediate_assembly/main/data_tables/sequencing_data"

# Platform-specific index files
HPRC_PLATFORM_INDEXES = {
    "PACBIO": f"{HPRC_BASE_URL}/data_hifi_pre_release.index.csv",
    "ONT": f"{HPRC_BASE_URL}/data_ont_pre_release.index.csv",
    "ILLUMINA": f"{HPRC_BASE_URL}/data_illumina_pre_release.index.csv",
}


def fetch_hprc_metadata() -> dict[str, set[str]]:
    """Fetch HPRC sample metadata from GitHub.

    Returns dict mapping sample_id -> set of available platforms.
    """
    print("Fetching HPRC metadata from GitHub...", flush=True)
    sample_platforms = defaultdict(set)

    for platform, url in HPRC_PLATFORM_INDEXES.items():
        try:
            print(f"  Fetching {platform} index...", end=" ", flush=True)
            resp = requests.get(url, timeout=30)
            if resp.status_code != 200:
                print(f"failed (HTTP {resp.status_code})")
                continue

            # Remove BOM if present
            text = resp.text.lstrip('\ufeff')
            reader = csv.DictReader(io.StringIO(text))

            count = 0
            for row in reader:
                # Try different column names for sample ID
                sample_id = (
                    row.get("sample_ID") or
                    row.get("sample_id") or
                    row.get("sample") or
                    ""
                ).strip()
                if sample_id:
                    sample_platforms[sample_id].add(platform)
                    count += 1

            print(f"{count} entries")

        except Exception as e:
            print(f"error: {e}")

    print(f"  Total: {len(sample_platforms)} unique samples")
    return dict(sample_platforms)


def extract_sample_id(filename: str) -> str | None:
    """Extract HPRC sample ID from filename."""
    # Match HG/NA followed by 5 digits, or specific HPRC samples
    match = re.search(r"\b((?:NA|HG)\d{5})\b", filename)
    if match:
        return match.group(1)

    # Also match CHM13, HG002, HG003, etc (shorter IDs)
    match = re.search(r"\b((?:HG|NA)\d{3})\b", filename)
    if match:
        return match.group(1)

    return None


def validate_against_hprc(
    input_paths: list[Path],
    output_path: Path,
    limit: int | None = None,
):
    """Validate classifications against HPRC metadata."""

    # Fetch HPRC metadata
    hprc_metadata = fetch_hprc_metadata()
    if not hprc_metadata:
        print("Failed to fetch HPRC metadata, aborting")
        return

    # Load our classifications
    all_classifications = []
    for input_path in input_paths:
        if not input_path.exists():
            continue
        print(f"Loading {input_path}...", flush=True)
        with open(input_path) as f:
            data = json.load(f)
        classifications = data.get("classifications", data)
        all_classifications.extend(classifications)

    # Filter to HPRC files (by dataset or sample ID)
    hprc_files = []
    for c in all_classifications:
        orig = c.get("original_record", {})
        dataset = orig.get("dataset_title", "")
        filename = c.get("file_name", "")

        # Check if HPRC dataset
        is_hprc = "HPRC" in dataset.upper() or "T2T" in dataset.upper()

        # Or if sample ID matches HPRC samples
        sample_id = extract_sample_id(filename)
        if sample_id and sample_id in hprc_metadata:
            is_hprc = True
            c["sample_id"] = sample_id

        if is_hprc and sample_id:
            hprc_files.append(c)

    print(f"\nFound {len(hprc_files):,} HPRC files with sample IDs")

    if limit:
        hprc_files = hprc_files[:limit]
        print(f"Limiting to {limit} files")

    # Separate raw data files from aligned files
    raw_data_files = []
    aligned_files = []
    for c in hprc_files:
        filename = c.get("file_name", "").lower()
        # Raw data: HiFi BAM, FASTQ, FAST5
        if filename.endswith((".fastq.gz", ".fq.gz", ".fast5", ".pod5")):
            raw_data_files.append(c)
        elif ".hifi_reads.bam" in filename or ".ccs.bam" in filename:
            raw_data_files.append(c)
        elif filename.endswith(".cram"):
            aligned_files.append(c)
        else:
            raw_data_files.append(c)  # Default to raw

    print(f"  Raw data files: {len(raw_data_files):,}")
    print(f"  Aligned files (CRAM): {len(aligned_files):,}")

    # Validate only raw data files (HPRC index tracks raw data platforms)
    hprc_files = raw_data_files

    # Validate
    results = {
        "platform_match": 0,
        "platform_mismatch": 0,
        "platform_unknown": 0,  # We don't have a classification
        "sample_not_in_hprc": 0,
        "total_validated": 0,
        "aligned_files_skipped": len(aligned_files),
    }
    mismatches = []
    sample_stats = defaultdict(lambda: {"files": 0, "matched": 0})

    print("\nValidating raw data files only (HPRC index tracks raw data)...", flush=True)

    for c in hprc_files:
        sample_id = c.get("sample_id")
        our_platform = (c.get("platform") or "").upper()
        filename = c.get("file_name", "")

        if sample_id not in hprc_metadata:
            results["sample_not_in_hprc"] += 1
            continue

        results["total_validated"] += 1
        expected_platforms = hprc_metadata[sample_id]
        sample_stats[sample_id]["files"] += 1

        if not our_platform:
            results["platform_unknown"] += 1
            continue

        if our_platform in expected_platforms:
            results["platform_match"] += 1
            sample_stats[sample_id]["matched"] += 1
        else:
            results["platform_mismatch"] += 1
            mismatches.append({
                "sample_id": sample_id,
                "file": filename,
                "ours": our_platform,
                "expected": list(expected_platforms),
            })

    # Summary
    validated = results["platform_match"] + results["platform_mismatch"]

    print()
    print("=" * 60)
    print("HPRC VALIDATION RESULTS")
    print("=" * 60)
    print(f"Total HPRC files:         {len(hprc_files):,}")
    print(f"With sample in HPRC:      {results['total_validated']:,}")
    print(f"Sample not in HPRC index: {results['sample_not_in_hprc']:,}")
    print()

    if validated > 0:
        accuracy = 100 * results["platform_match"] / validated
        print(f"PLATFORM ACCURACY:  {results['platform_match']:,}/{validated:,} ({accuracy:.2f}%)")

    if results["platform_unknown"] > 0:
        print(f"No platform classification: {results['platform_unknown']:,}")

    if results["platform_mismatch"] > 0:
        print(f"\nMismatches: {results['platform_mismatch']:,}")
        print("Sample mismatches (first 10):")
        for m in mismatches[:10]:
            print(f"  {m['sample_id']}: ours={m['ours']} vs expected={m['expected']}")
            print(f"    File: {m['file'][:60]}...")

    # Platform distribution in our data
    print("\nOur platform distribution for HPRC files:")
    platform_counts = Counter(c.get("platform") or "null" for c in hprc_files)
    for plat, count in platform_counts.most_common():
        print(f"  {plat}: {count:,}")

    print("=" * 60)

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_hprc_files": len(hprc_files),
                "samples_in_index": len(hprc_metadata),
                "validated": results["total_validated"],
            },
            "results": results,
            "mismatches": mismatches[:100],
        }, f, indent=2)

    print(f"\nResults saved to: {output_path}")
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate classifications against HPRC metadata"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        nargs="+",
        default=[
            Path("output/bam_headers.json"),
            Path("output/fastq_headers.json"),
        ],
        help="Input classification files",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output/hprc_validation_results.json"),
        help="Output file",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit files to validate",
    )
    args = parser.parse_args()

    validate_against_hprc(args.input, args.output, args.limit)


if __name__ == "__main__":
    main()
