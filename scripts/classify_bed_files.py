#!/usr/bin/env python3
"""Classify BED files using RuleEngine + coordinate-based reference detection.

Uses rules from rules/unified_rules.yaml for:
- modbam2bed/cpg/methylation -> epigenomic.methylation
- TMM/TPM/counts/leafcutter/TSS -> transcriptomic
- peak/summit/chip/atac -> epigenomic.chromatin_accessibility
- .regions.bed -> genomic
- Assembly QC (hap1/2, flagger, switch, dip) -> N/A (derived)
- Reference detection from filename patterns and dataset context
- Reference detection from BED coordinate signals (coordinate elimination)
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.header_classifier import classify_from_bed_signals
from src.meta_disco.models import NOT_APPLICABLE, NOT_CLASSIFIED

_SENTINEL_VALUES = {NOT_CLASSIFIED, NOT_APPLICABLE}

EVIDENCE_DIR = Path("data/evidence/bed")


def load_bed_reference_evidence() -> dict[str, dict]:
    """Load cached coordinate-based reference evidence for BED files.

    Returns dict mapping md5sum -> evidence dict (with 'signals' key).
    Evidence is produced by scripts/fetch_bed_headers.py which reads actual
    BED file content from S3 and infers reference from chromosome coordinates.
    """
    evidence = {}
    if not EVIDENCE_DIR.exists():
        return evidence

    for subdir in EVIDENCE_DIR.iterdir():
        if not subdir.is_dir():
            continue
        for evi_file in subdir.iterdir():
            try:
                with open(evi_file) as fh:
                    evi = json.load(fh)
                md5 = evi.get("md5sum")
                if md5:
                    evidence[md5] = evi
            except (json.JSONDecodeError, IOError):
                continue

    return evidence


def classify_bed_files(metadata_path: Path, output_path: Path):
    """Classify BED files using RuleEngine + coordinate-based reference evidence."""

    with open(metadata_path) as f:
        data = json.load(f)

    files = data if isinstance(data, list) else data.get("files", data.get("results", []))
    print(f"Loaded {len(files):,} files from metadata")

    # Find BED files
    bed_files = []
    for f in files:
        name = f.get("file_name", "")
        fmt = f.get("file_format", "")
        if name.endswith(".bed") or name.endswith(".bed.gz") or fmt in [".bed", ".bed.gz"]:
            bed_files.append(f)

    print(f"Found {len(bed_files):,} BED files")

    # Load coordinate-based reference evidence
    ref_evidence = load_bed_reference_evidence()
    print(f"Loaded {len(ref_evidence):,} BED coordinate evidence files")

    results = []
    stats = {
        "total": 0,
        "with_modality": 0,
        "with_reference": 0,
        "by_modality": {},
        "by_reference": {},
    }

    for f in bed_files:
        name = f.get("file_name", "")
        dataset_title = f.get("dataset_title", "")
        md5 = f.get("file_md5sum")
        stats["total"] += 1

        # Get coordinate signals from cached evidence
        signals = ref_evidence.get(md5, {}).get("signals", {}) if md5 else {}

        # Classify using unified classifier (rule engine + coordinate detection)
        classifications = classify_from_bed_signals(
            signals,
            file_name=name,
            file_size=f.get("file_size"),
            dataset_title=dataset_title,
        )

        # Update stats
        data_modality = classifications.get("data_modality", {}).get("value")
        reference_assembly = classifications.get("reference_assembly", {}).get("value")

        if data_modality and data_modality not in _SENTINEL_VALUES:
            stats["with_modality"] += 1
        stats["by_modality"][data_modality or "N/A"] = stats["by_modality"].get(data_modality or "N/A", 0) + 1

        if reference_assembly and reference_assembly not in _SENTINEL_VALUES:
            stats["with_reference"] += 1
        stats["by_reference"][reference_assembly or "N/A"] = stats["by_reference"].get(reference_assembly or "N/A", 0) + 1

        results.append({
            "file_name": name,
            "file_format": f.get("file_format"),
            "md5sum": md5,
            "file_size": f.get("file_size"),
            "entry_id": f.get("entry_id"),
            "dataset_id": f.get("dataset_id"),
            "dataset_title": dataset_title,
            "classifications": classifications,
        })

    # Print summary
    print("\n" + "=" * 70)
    print("BED FILE CLASSIFICATION RESULTS")
    print("=" * 70)

    print(f"\nTotal BED files: {stats['total']:,}")
    if stats["total"] > 0:
        print(f"With data_modality: {stats['with_modality']:,} ({stats['with_modality']/stats['total']*100:.1f}%)")
        print(f"With reference: {stats['with_reference']:,} ({stats['with_reference']/stats['total']*100:.1f}%)")

    print("\nBy modality:")
    for mod, count in sorted(stats["by_modality"].items(), key=lambda x: -x[1]):
        print(f"  {mod or 'N/A'}: {count:,}")

    print("\nBy reference:")
    for ref, count in sorted(stats["by_reference"].items(), key=lambda x: -x[1]):
        print(f"  {ref}: {count:,}")

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_files": stats["total"],
                "with_data_modality": stats["with_modality"],
                "with_reference_assembly": stats["with_reference"],
                "by_modality": stats["by_modality"],
                "by_reference": stats["by_reference"],
                "complete": True,
            },
            "classifications": results,
        }, f, indent=2)

    print(f"\nSaved {len(results):,} classifications to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Classify BED files")
    parser.add_argument(
        "--metadata", "-m",
        type=Path,
        default=Path("data/anvil_files_metadata.json"),
        help="Path to source metadata JSON",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output/bed_classifications.json"),
        help="Output path for classifications",
    )
    args = parser.parse_args()

    classify_bed_files(args.metadata, args.output)


if __name__ == "__main__":
    main()
