#!/usr/bin/env python3 -u
"""Validate classifications against HPRC metadata.

Cross-references our platform classifications with the official HPRC
sequencing data catalog from the hprc-data-explorer repository.

This uses file-level validation (matching by filename) rather than
sample-level validation, providing accurate ground truth.

Usage:
    python scripts/validate_hprc_samples.py
    python scripts/validate_hprc_samples.py --limit 100

Output saved to: output/hprc_validation_results.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import requests

# HPRC Data Explorer catalog - comprehensive file-level metadata
HPRC_SEQUENCING_DATA_URL = (
    "https://raw.githubusercontent.com/human-pangenomics/hprc-data-explorer/"
    "main/catalog/output/sequencing-data.json"
)

# Platform name normalization: HPRC uses different naming conventions
PLATFORM_MAP = {
    "PACBIO_SMRT": "PACBIO",
    "OXFORD_NANOPORE": "ONT",
    "ILLUMINA": "ILLUMINA",
}


def fetch_hprc_catalog() -> dict[str, dict]:
    """Fetch HPRC sequencing data catalog from GitHub.

    Returns dict mapping filename -> {platform, instrumentModel, sampleId, ...}
    """
    print("Fetching HPRC sequencing data catalog...", flush=True)

    try:
        resp = requests.get(HPRC_SEQUENCING_DATA_URL, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Error fetching catalog: {e}")
        return {}

    # Build filename -> metadata lookup
    catalog = {}
    for record in data:
        filename = record.get("filename", "")
        if not filename:
            continue

        hprc_platform = record.get("platform", "")
        normalized_platform = PLATFORM_MAP.get(hprc_platform, hprc_platform)

        catalog[filename] = {
            "platform": normalized_platform,
            "hprc_platform": hprc_platform,
            "instrumentModel": record.get("instrumentModel"),
            "sampleId": record.get("sampleId"),
            "accession": record.get("accession"),
            "libraryStrategy": record.get("libraryStrategy"),
        }

    # Summary
    platforms = Counter(v["platform"] for v in catalog.values())
    print(f"  Loaded {len(catalog):,} files from HPRC catalog")
    print(f"  Platforms: {dict(platforms)}")

    return catalog


def validate_against_hprc(
    input_paths: list[Path],
    output_path: Path,
    limit: int | None = None,
):
    """Validate classifications against HPRC catalog using file-level matching."""

    # Fetch HPRC catalog
    hprc_catalog = fetch_hprc_catalog()
    if not hprc_catalog:
        print("Failed to fetch HPRC catalog, aborting")
        return

    # Load our classifications
    all_classifications = []
    for input_path in input_paths:
        if not input_path.exists():
            print(f"  Skipping {input_path} (not found)")
            continue
        print(f"Loading {input_path}...", flush=True)
        with open(input_path) as f:
            data = json.load(f)
        classifications = data.get("classifications", data)
        all_classifications.extend(classifications)

    print(f"Loaded {len(all_classifications):,} total classifications")

    # Match our files against HPRC catalog by filename
    matched_files = []
    for c in all_classifications:
        filename = c.get("file_name", "")
        if filename in hprc_catalog:
            c["hprc_metadata"] = hprc_catalog[filename]
            matched_files.append(c)

    print(f"Matched {len(matched_files):,} files against HPRC catalog")

    if limit:
        matched_files = matched_files[:limit]
        print(f"Limiting to {limit} files")

    # Validate platforms
    results = {
        "platform_match": 0,
        "platform_mismatch": 0,
        "platform_unknown": 0,  # We don't have a classification
        "total_validated": len(matched_files),
    }
    mismatches = []
    matches_by_platform = Counter()

    print("\nValidating platform classifications...", flush=True)

    for c in matched_files:
        filename = c.get("file_name", "")
        our_platform = (c.get("platform") or "").upper()
        hprc_meta = c["hprc_metadata"]
        expected_platform = hprc_meta["platform"]

        if not our_platform:
            results["platform_unknown"] += 1
            continue

        if our_platform == expected_platform:
            results["platform_match"] += 1
            matches_by_platform[expected_platform] += 1
        else:
            results["platform_mismatch"] += 1
            mismatches.append({
                "file": filename,
                "sampleId": hprc_meta.get("sampleId"),
                "ours": our_platform,
                "expected": expected_platform,
                "hprc_instrument": hprc_meta.get("instrumentModel"),
                "our_instrument": c.get("instrument_model"),
            })

    # Summary
    validated = results["platform_match"] + results["platform_mismatch"]

    print()
    print("=" * 60)
    print("HPRC VALIDATION RESULTS (File-Level)")
    print("=" * 60)
    print(f"HPRC catalog files:       {len(hprc_catalog):,}")
    print(f"Our files matched:        {len(matched_files):,}")
    print()

    if validated > 0:
        accuracy = 100 * results["platform_match"] / validated
        print(f"PLATFORM ACCURACY:  {results['platform_match']:,}/{validated:,} ({accuracy:.2f}%)")

    if results["platform_unknown"] > 0:
        print(f"No platform classification: {results['platform_unknown']:,}")

    # Breakdown by platform
    print("\nMatches by platform:")
    for plat, count in matches_by_platform.most_common():
        print(f"  {plat}: {count:,}")

    if results["platform_mismatch"] > 0:
        print(f"\nMismatches: {results['platform_mismatch']:,}")
        print("Sample mismatches (first 10):")
        for m in mismatches[:10]:
            print(f"  {m['file'][:50]}...")
            print(f"    ours={m['ours']} vs expected={m['expected']}")
            print(f"    HPRC instrument: {m['hprc_instrument']}")
            if m.get("our_instrument"):
                print(f"    Our instrument:  {m['our_instrument']}")

    # Platform distribution in our matched data
    print("\nOur platform distribution for matched files:")
    platform_counts = Counter(c.get("platform") or "(none)" for c in matched_files)
    for plat, count in platform_counts.most_common():
        print(f"  {plat}: {count:,}")

    print("=" * 60)

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "hprc_catalog_files": len(hprc_catalog),
                "matched_files": len(matched_files),
                "validated": validated,
                "source": HPRC_SEQUENCING_DATA_URL,
            },
            "results": results,
            "matches_by_platform": dict(matches_by_platform),
            "mismatches": mismatches,
        }, f, indent=2)

    print(f"\nResults saved to: {output_path}")
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate classifications against HPRC sequencing data catalog"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        nargs="+",
        default=[
            Path("output/bam_classifications.json"),
            Path("output/fastq_classifications.json"),
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
