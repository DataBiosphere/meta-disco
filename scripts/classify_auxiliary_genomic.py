#!/usr/bin/env python3
"""Classify auxiliary genomic files using RuleEngine.

Uses rules from rules/unified_rules.yaml for:
- .fast5, .pod5 -> genomic.raw_signal (ONT raw signal data)
- .pvar, .psam, .pgen -> genomic.genotypes (PLINK2 genotype data)
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.rule_engine import RuleEngine
from src.meta_disco.models import FileInfo, NOT_APPLICABLE, NOT_CLASSIFIED

_SENTINEL_VALUES = {NOT_CLASSIFIED, NOT_APPLICABLE}

# Extensions handled by this script
AUXILIARY_EXTENSIONS = {".fast5", ".pod5", ".fast5.tar", ".fast5.tar.gz", ".pvar", ".psam", ".pgen"}


def classify_auxiliary_genomic(metadata_path: Path, output_path: Path):
    """Classify auxiliary genomic files using RuleEngine."""

    with open(metadata_path) as f:
        data = json.load(f)

    files = data if isinstance(data, list) else data.get("files", data.get("results", []))
    print(f"Loaded {len(files):,} files from metadata")

    engine = RuleEngine()
    results = []
    stats = {ext: {"total": 0, "with_ref": 0} for ext in AUXILIARY_EXTENSIONS}

    for f in files:
        name = f.get("file_name", "")
        fmt = f.get("file_format", "")
        dataset_title = f.get("dataset_title", "")
        name_lower = name.lower()

        # Check if this is an auxiliary file
        matched_ext = None
        for ext in AUXILIARY_EXTENSIONS:
            if fmt == ext or name_lower.endswith(ext):
                matched_ext = ext
                stats[ext]["total"] = stats[ext].get("total", 0) + 1
                break

        if not matched_ext:
            continue

        # Classify using RuleEngine
        file_info = FileInfo(
            filename=name,
            file_size=f.get("file_size"),
            dataset_title=dataset_title,
        )
        result = engine.classify_extended(file_info)

        if result.reference_assembly and result.reference_assembly not in _SENTINEL_VALUES:
            stats[matched_ext]["with_ref"] += 1

        results.append({
            "file_name": name,
            "file_format": fmt,
            "md5sum": f.get("file_md5sum"),
            "file_size": f.get("file_size"),
            "entry_id": f.get("entry_id"),
            "dataset_id": f.get("dataset_id"),
            "dataset_title": dataset_title,
            "classifications": result.to_output_dict(),
        })

    # Print summary
    print("\n" + "=" * 70)
    print("AUXILIARY GENOMIC FILE CLASSIFICATION RESULTS")
    print("=" * 70)

    total_all = 0
    ref_all = 0

    for ext in sorted(AUXILIARY_EXTENSIONS):
        s = stats[ext]
        if s["total"] > 0:
            total_all += s["total"]
            ref_all += s["with_ref"]
            ref_pct = s["with_ref"] / s["total"] * 100 if s["total"] > 0 else 0
            print(f"\n{ext}:")
            print(f"  Total:      {s['total']:>7,}")
            print(f"  With ref:   {s['with_ref']:>7,} ({ref_pct:.1f}%)")

    print(f"\n{'=' * 70}")
    print(f"Total auxiliary genomic files: {total_all:,}")
    print(f"With reference_assembly: {ref_all:,}")
    print("=" * 70)

    # Count by modality
    modalities = {}
    def _val(rec, field):
        cls = rec.get("classifications", {})
        if isinstance(cls, dict) and field in cls:
            v = cls[field]
            return v["value"] if isinstance(v, dict) and "value" in v else v
        return rec.get(field)

    for r in results:
        mod = _val(r, "data_modality") or "N/A"
        modalities[mod] = modalities.get(mod, 0) + 1

    print("\nBy modality:")
    for mod, count in sorted(modalities.items(), key=lambda x: -x[1]):
        print(f"  {mod}: {count:,}")

    # Count by reference
    refs = {}
    for r in results:
        ref = _val(r, "reference_assembly") or "N/A"
        refs[ref] = refs.get(ref, 0) + 1

    print("\nBy reference_assembly:")
    for ref, count in sorted(refs.items(), key=lambda x: -x[1]):
        print(f"  {ref}: {count:,}")

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_files": total_all,
                "by_extension": {ext: stats[ext]["total"] for ext in AUXILIARY_EXTENSIONS if stats[ext]["total"] > 0},
                "with_reference": ref_all,
                "complete": True,
            },
            "classifications": results,
        }, f, indent=2)

    print(f"\nSaved {len(results):,} classifications to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Classify auxiliary genomic files")
    parser.add_argument(
        "--metadata", "-m",
        type=Path,
        default=Path("data/anvil_files_metadata.json"),
        help="Path to source metadata JSON",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output/auxiliary_classifications.json"),
        help="Output path for classifications",
    )
    args = parser.parse_args()

    classify_auxiliary_genomic(args.metadata, args.output)


if __name__ == "__main__":
    main()
