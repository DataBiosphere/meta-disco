#!/usr/bin/env python3
"""Classify BED files using RuleEngine.

Uses rules from rules/unified_rules.yaml for:
- modbam2bed/cpg/methylation -> epigenomic.methylation
- TMM/TPM/counts/leafcutter/TSS -> transcriptomic
- peak/summit/chip/atac -> epigenomic.chromatin_accessibility
- .regions.bed -> genomic
- Assembly QC (hap1/2, flagger, switch, dip) -> N/A (derived)
- Reference detection from filename patterns and dataset context
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.rule_engine import RuleEngine
from src.meta_disco.models import FileInfo


def classify_bed_files(metadata_path: Path, output_path: Path):
    """Classify BED files using RuleEngine."""

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

    engine = RuleEngine()
    results = []
    stats = {
        "total": 0,
        "with_modality": 0,
        "with_reference": 0,
        "by_modality": {},
        "by_reference": {},
        "by_rule": {},
    }

    for f in bed_files:
        name = f.get("file_name", "")
        dataset_title = f.get("dataset_title", "")
        stats["total"] += 1

        # Classify using RuleEngine
        file_info = FileInfo(
            filename=name,
            file_size=f.get("file_size"),
            dataset_title=dataset_title,
        )
        result = engine.classify_extended(file_info)

        # Update stats
        data_modality = result.data_modality
        reference_assembly = result.reference_assembly

        if data_modality:
            stats["with_modality"] += 1
            stats["by_modality"][data_modality] = stats["by_modality"].get(data_modality, 0) + 1
        else:
            stats["by_modality"]["N/A"] = stats["by_modality"].get("N/A", 0) + 1

        if reference_assembly:
            stats["with_reference"] += 1
            stats["by_reference"][reference_assembly] = stats["by_reference"].get(reference_assembly, 0) + 1
        else:
            stats["by_reference"]["N/A"] = stats["by_reference"].get("N/A", 0) + 1

        for rule_id in result.rules_matched:
            stats["by_rule"][rule_id] = stats["by_rule"].get(rule_id, 0) + 1

        results.append({
            "file_name": name,
            "file_format": f.get("file_format"),
            "md5sum": f.get("file_md5sum"),
            "file_size": f.get("file_size"),
            "entry_id": f.get("entry_id"),
            "dataset_id": f.get("dataset_id"),
            "dataset_title": dataset_title,
            "data_modality": data_modality,
            "data_type": result.data_type,
            "assay_type": result.assay_type,
            "platform": result.platform,
            "reference_assembly": reference_assembly,
            "confidence": result.confidence,
            "matched_rules": result.rules_matched,
            "reasons": result.reasons,
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

    print("\nBy rule matched:")
    for rule, count in sorted(stats["by_rule"].items(), key=lambda x: -x[1]):
        print(f"  {rule}: {count:,}")

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
