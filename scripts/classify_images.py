#!/usr/bin/env python3
"""Classify image files using RuleEngine.

Uses rules from rules/unified_rules.yaml for:
- .svs -> imaging.histology (Aperio whole-slide images)
- .png -> derived visualizations (QC plots)
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.rule_engine import RuleEngine
from src.meta_disco.models import FileInfo


def classify_images(metadata_path: Path, output_path: Path):
    """Classify image files using RuleEngine."""

    with open(metadata_path) as f:
        data = json.load(f)

    files = data if isinstance(data, list) else data.get("files", data.get("results", []))
    print(f"Loaded {len(files):,} files from metadata")

    engine = RuleEngine()
    results = []
    stats = {".svs": {"total": 0}, ".png": {"total": 0}, ".jpg": {"total": 0}, ".tiff": {"total": 0}}

    for f in files:
        name = f.get("file_name", "")
        fmt = f.get("file_format", "")
        name_lower = name.lower()

        # Check if this is an image file
        is_image = False
        matched_ext = None
        for ext in stats.keys():
            if fmt == ext or name_lower.endswith(ext):
                is_image = True
                matched_ext = ext
                stats[ext]["total"] = stats[ext].get("total", 0) + 1
                break

        if not is_image:
            continue

        # Classify using RuleEngine
        file_info = FileInfo(
            filename=name,
            file_size=f.get("file_size"),
            dataset_title=f.get("dataset_title"),
        )
        result = engine.classify_extended(file_info)

        results.append({
            "file_name": name,
            "file_format": fmt,
            "md5sum": f.get("file_md5sum"),
            "file_size": f.get("file_size"),
            "entry_id": f.get("entry_id"),
            "dataset_id": f.get("dataset_id"),
            "dataset_title": f.get("dataset_title"),
            "data_modality": result.data_modality,
            "data_type": result.data_type,
            "assay_type": result.assay_type,
            "platform": result.platform,
            "reference_assembly": result.reference_assembly,
            "confidence": result.confidence,
            "matched_rules": result.rules_matched,
            "reasons": result.reasons,
        })

    # Print summary
    print("\n" + "=" * 70)
    print("IMAGE FILE CLASSIFICATION RESULTS")
    print("=" * 70)

    total_all = sum(s["total"] for s in stats.values())

    for ext, s in stats.items():
        if s["total"] > 0:
            print(f"\n{ext}: {s['total']:,}")

    print(f"\n{'=' * 70}")
    print(f"Total images: {total_all:,}")
    print("=" * 70)

    # Count by modality
    modalities = {}
    for r in results:
        mod = r.get("data_modality") or "N/A"
        modalities[mod] = modalities.get(mod, 0) + 1

    print("\nBy modality:")
    for mod, count in sorted(modalities.items(), key=lambda x: -x[1]):
        print(f"  {mod}: {count:,}")

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_images": total_all,
                "by_extension": {ext: stats[ext]["total"] for ext in stats if stats[ext]["total"] > 0},
                "complete": True,
            },
            "classifications": results,
        }, f, indent=2)

    print(f"\nSaved {len(results):,} image classifications to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Classify image files")
    parser.add_argument(
        "--metadata", "-m",
        type=Path,
        default=Path("data/anvil_files_metadata.json"),
        help="Path to source metadata JSON",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output/image_classifications.json"),
        help="Output path for image classifications",
    )
    args = parser.parse_args()

    classify_images(args.metadata, args.output)


if __name__ == "__main__":
    main()
