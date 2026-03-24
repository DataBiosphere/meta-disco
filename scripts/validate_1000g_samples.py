#!/usr/bin/env python3 -u
"""Validate classifications against 1000 Genomes IGSR metadata.

Cross-references our platform and modality classifications with the
authoritative IGSR (International Genome Sample Resource) metadata.

Usage:
    python scripts/validate_1000g_samples.py
    python scripts/validate_1000g_samples.py --input output/anvil/bam_classifications.json
    python scripts/validate_1000g_samples.py --limit 100 --workers 5

Output saved to: output/1000g_validation_results.json
"""

import argparse
import json
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

IGSR_API = "https://www.internationalgenome.org/api/beta/sample"

# Map IGSR sequence types to our modality classifications
# Note: assay_type (WGS/WES) is now separate from data_modality
SEQUENCE_TO_MODALITY = {
    # Exome - assay_type: WES
    "Exome": "genomic",
    # WGS - various coverage levels - assay_type: WGS
    "Low coverage WGS": "genomic",
    "PCR-free high coverage": "genomic",
    "High coverage WGS": "genomic",
    "Complete Genomics": "genomic",
    # Long read WGS - assay_type: WGS
    "PacBio SMRT genomic": "genomic",
    "PacBio HiFi": "genomic",
    "Oxford Nanopore Technologies": "genomic",
    "Illumina NovaSeq 6000": "genomic",
    # Transcriptomic - assay_type: RNA-seq
    "mRNA": "transcriptomic.bulk",
}

# Collections that imply WGS even without explicit sequence type
WGS_COLLECTION_PATTERNS = [
    "1000 Genomes 30x",
    "high coverage",
]

# Map IGSR data collection titles to platforms
COLLECTION_TO_PLATFORM = {
    "1KG_ONT_VIENNA": "ONT",
    "Oxford Nanopore": "ONT",
}


def fetch_igsr_metadata(sample_id: str) -> dict | None:
    """Fetch metadata for a sample from IGSR API."""
    try:
        resp = requests.get(f"{IGSR_API}/{sample_id}", timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        # Data is nested in _source
        return data.get("_source", data)
    except Exception:
        return None


def extract_sample_id(filename: str) -> str | None:
    """Extract 1000 Genomes sample ID from filename."""
    match = re.search(r"\b((?:NA|HG)\d{5})\b", filename)
    return match.group(1) if match else None


def get_expected_modalities(igsr_data: dict) -> set[str]:
    """Extract expected modalities from IGSR data collections."""
    modalities = set()
    for collection in igsr_data.get("dataCollections", []):
        title = collection.get("title", "")
        sequences = collection.get("sequence", [])
        if isinstance(sequences, str):
            sequences = [sequences]

        # Check sequence types
        for seq in sequences:
            if seq in SEQUENCE_TO_MODALITY:
                modalities.add(SEQUENCE_TO_MODALITY[seq])

        # Check collection title for WGS patterns
        title_lower = title.lower()
        for pattern in WGS_COLLECTION_PATTERNS:
            if pattern.lower() in title_lower:
                modalities.add("genomic")  # WGS is now assay_type, not modality
                break
    return modalities


def get_expected_platforms(igsr_data: dict) -> set[str]:
    """Extract expected platforms from IGSR data collections."""
    platforms = set()
    for collection in igsr_data.get("dataCollections", []):
        title = collection.get("title", "")
        sequences = collection.get("sequence") or []
        if isinstance(sequences, str):
            sequences = [sequences]

        # Check sequence field for platform info
        for seq in sequences:
            seq_lower = seq.lower()
            if "pacbio" in seq_lower or "hifi" in seq_lower or "smrt" in seq_lower:
                platforms.add("PACBIO")
            if "nanopore" in seq_lower or "ont" in seq_lower:
                platforms.add("ONT")
            if "illumina" in seq_lower or "novaseq" in seq_lower or "hiseq" in seq_lower:
                platforms.add("ILLUMINA")

        # Check title for platform info
        title_lower = title.lower()
        for pattern, platform in COLLECTION_TO_PLATFORM.items():
            if pattern.lower() in title_lower:
                platforms.add(platform)
        if "pacbio" in title_lower or "hifi" in title_lower:
            platforms.add("PACBIO")
        if "nanopore" in title_lower or "ont" in title_lower:
            platforms.add("ONT")
        # Most 1000G data includes Illumina
        if "illumina" in title_lower or "1000 genomes" in title_lower:
            platforms.add("ILLUMINA")
    # Default to Illumina if no specific platform found (most 1000G samples)
    if not platforms:
        platforms.add("ILLUMINA")
    return platforms


def validate_against_igsr(
    input_paths: list[Path],
    output_path: Path,
    limit: int | None = None,
    workers: int = 10,
):
    """Validate classifications against IGSR metadata."""

    all_classifications = []

    # Load classifications from all input files
    for input_path in input_paths:
        print(f"Loading classifications from {input_path}...", flush=True)
        with open(input_path) as f:
            data = json.load(f)
        classifications = data.get("classifications", data)
        all_classifications.extend(classifications)

    # Extract sample IDs and group by sample
    sample_files = defaultdict(list)
    for c in all_classifications:
        sample_id = extract_sample_id(c.get("file_name", ""))
        if sample_id:
            c["sample_id"] = sample_id
            sample_files[sample_id].append(c)

    print(f"Found {len(sample_files):,} unique sample IDs across {sum(len(v) for v in sample_files.values()):,} files", flush=True)

    if limit:
        # Limit by number of samples, not files
        sample_ids = list(sample_files.keys())[:limit]
        sample_files = {k: sample_files[k] for k in sample_ids}
        print(f"Limiting to first {limit} samples", flush=True)

    print(f"Using {workers} parallel workers", flush=True)

    # Results tracking
    results = {
        "platform_match": 0,
        "platform_mismatch": 0,
        "modality_match": 0,
        "modality_mismatch": 0,
        "modality_partial": 0,  # Our classification is in IGSR's set but not exact
        "api_errors": 0,
        "total_files_validated": 0,
        "total_samples_validated": 0,
    }
    mismatches = []
    api_errors = []

    # Cache IGSR responses per sample
    igsr_cache = {}

    print()
    print("Validating against IGSR API...")
    print("-" * 60)

    start_time = time.time()
    completed_samples = 0
    total_samples = len(sample_files)

    def fetch_sample(sample_id: str) -> tuple[str, dict | None]:
        """Fetch and return sample metadata."""
        return sample_id, fetch_igsr_metadata(sample_id)

    # Fetch all sample metadata in parallel
    print("Fetching IGSR metadata...", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_sample, sid): sid for sid in sample_files.keys()}

        for future in as_completed(futures):
            completed_samples += 1
            sample_id, igsr_data = future.result()
            igsr_cache[sample_id] = igsr_data

            if completed_samples % 50 == 0 or completed_samples == total_samples:
                elapsed = time.time() - start_time
                rate = completed_samples / elapsed if elapsed > 0 else 0
                print(f"\r  Fetched {completed_samples:,}/{total_samples:,} samples ({rate:.1f}/sec)   ", end="", flush=True)

    print()
    print("Validating classifications...", flush=True)

    # Now validate each file
    for sample_id, files in sample_files.items():
        igsr_data = igsr_cache.get(sample_id)

        if not igsr_data:
            results["api_errors"] += len(files)
            for f in files:
                api_errors.append({
                    "sample_id": sample_id,
                    "file": f.get("file_name"),
                    "reason": "api_failed",
                })
            continue

        results["total_samples_validated"] += 1
        expected_modalities = get_expected_modalities(igsr_data)
        expected_platforms = get_expected_platforms(igsr_data)

        for f in files:
            results["total_files_validated"] += 1
            our_platform = (f.get("platform") or "").upper()
            our_modality = f.get("data_modality") or ""

            # Platform validation (only if we have a classification)
            if our_platform:
                if our_platform in expected_platforms:
                    results["platform_match"] += 1
                else:
                    results["platform_mismatch"] += 1
                    mismatches.append({
                        "sample_id": sample_id,
                        "file": f.get("file_name"),
                        "type": "platform",
                        "ours": our_platform,
                        "expected": list(expected_platforms),
                    })

            # Modality validation
            # Check if our modality matches or is a prefix of any expected modality
            modality_match = False
            modality_partial = False

            if our_modality:
                for exp_mod in expected_modalities:
                    if our_modality == exp_mod:
                        modality_match = True
                        break
                    elif our_modality.startswith(exp_mod.split(".")[0]) or exp_mod.startswith(our_modality):
                        modality_partial = True

            if modality_match:
                results["modality_match"] += 1
            elif modality_partial:
                results["modality_partial"] += 1
                results["modality_match"] += 1  # Count partial as match
            elif not our_modality:
                # No classification = can't validate
                pass
            else:
                results["modality_mismatch"] += 1
                mismatches.append({
                    "sample_id": sample_id,
                    "file": f.get("file_name"),
                    "type": "modality",
                    "ours": our_modality,
                    "expected": list(expected_modalities),
                })

    elapsed = time.time() - start_time
    n_files = results["total_files_validated"]
    n_samples = results["total_samples_validated"]

    print()
    print("=" * 60)
    print("1000 GENOMES VALIDATION RESULTS")
    print("=" * 60)
    print(f"Total samples:              {total_samples:,}")
    print(f"Successfully validated:     {n_samples:,} samples, {n_files:,} files")
    print(f"API errors:                 {results['api_errors']:,} files")
    print(f"Time elapsed:               {elapsed:.1f}s")
    print()

    if n_files > 0:
        # Calculate based on files we actually tried to validate
        plat_total = results["platform_match"] + results["platform_mismatch"]
        mod_total = results["modality_match"] + results["modality_mismatch"]

        if plat_total > 0:
            plat_pct = 100 * results["platform_match"] / plat_total
            print(f"PLATFORM ACCURACY:  {results['platform_match']:,}/{plat_total:,} ({plat_pct:.2f}%)")

        if mod_total > 0:
            mod_pct = 100 * results["modality_match"] / mod_total
            print(f"MODALITY ACCURACY:  {results['modality_match']:,}/{mod_total:,} ({mod_pct:.2f}%)")
            if results["modality_partial"] > 0:
                print(f"  (includes {results['modality_partial']:,} partial matches)")

    if results["platform_mismatch"] > 0:
        print(f"\nPlatform mismatches: {results['platform_mismatch']:,}")
    if results["modality_mismatch"] > 0:
        print(f"Modality mismatches: {results['modality_mismatch']:,}")

    # Show sample mismatches
    platform_mismatches = [m for m in mismatches if m["type"] == "platform"]
    modality_mismatches = [m for m in mismatches if m["type"] == "modality"]

    if platform_mismatches:
        print("\nSample platform mismatches (first 10):")
        for m in platform_mismatches[:10]:
            print(f"  {m['sample_id']}: ours={m['ours']} vs expected={m['expected']}")

    if modality_mismatches:
        print("\nSample modality mismatches (first 10):")
        for m in modality_mismatches[:10]:
            print(f"  {m['sample_id']}: ours={m['ours']} vs expected={m['expected']}")

    print("=" * 60)

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_samples": total_samples,
                "validated_samples": n_samples,
                "validated_files": n_files,
                "api_errors": results["api_errors"],
                "elapsed_seconds": elapsed,
            },
            "results": results,
            "mismatches": mismatches[:100],  # Limit to first 100
            "api_errors": api_errors[:100],
        }, f, indent=2)

    print(f"\nResults saved to: {output_path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate classifications against 1000 Genomes IGSR metadata"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        nargs="+",
        default=[
            Path("output/anvil/bam_classifications.json"),
            Path("output/anvil/fastq_classifications.json"),
        ],
        help="Input classification files",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output/1000g_validation_results.json"),
        help="Output validation results file",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit number of samples to validate (for testing)",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=10,
        help="Number of parallel workers (default: 10)",
    )
    args = parser.parse_args()

    validate_against_igsr(
        args.input,
        args.output,
        limit=args.limit,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
