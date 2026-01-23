#!/usr/bin/env python3
"""Classify image files by extension.

.svs -> imaging.histology (Aperio whole-slide images)
.png -> N/A (derived visualizations, QC plots)
"""

import argparse
import json
from pathlib import Path

# Extension-based classification rules for images
IMAGE_RULES = {
    ".svs": {
        "data_modality": "imaging.histology",
        "reference_assembly": None,
        "confidence": 0.95,
        "rationale": "SVS files are Aperio whole-slide histology images used for pathology analysis.",
    },
    ".png": {
        "data_modality": None,  # QC plots, derived visualizations - not primary data
        "reference_assembly": None,
        "confidence": 0.90,
        "rationale": "PNG files are derived visualizations (QC plots, assembly graphs) - not primary experimental data.",
    },
}


def classify_images(metadata_path: Path, output_path: Path):
    """Classify image files based on extension."""

    with open(metadata_path) as f:
        data = json.load(f)

    files = data if isinstance(data, list) else data.get("files", data.get("results", []))
    print(f"Loaded {len(files):,} files from metadata")

    results = []
    stats = {}

    for ext in IMAGE_RULES:
        stats[ext] = {"total": 0, "classified": 0}

    for f in files:
        name = f.get("file_name", "")
        fmt = f.get("file_format", "")

        # Check each image extension
        for ext, rule in IMAGE_RULES.items():
            if fmt == ext or name.lower().endswith(ext):
                stats[ext]["total"] += 1
                stats[ext]["classified"] += 1

                results.append({
                    "file_name": name,
                    "file_format": fmt,
                    "md5sum": f.get("file_md5sum"),
                    "file_size": f.get("file_size"),
                    "entry_id": f.get("entry_id"),
                    "dataset_id": f.get("dataset_id"),
                    "dataset_title": f.get("dataset_title"),
                    "data_modality": rule["data_modality"],
                    "reference_assembly": rule["reference_assembly"],
                    "confidence": rule["confidence"],
                    "matched_rules": [f"image_ext_{ext}"],
                    "evidence": [{
                        "rule_id": f"image_ext_{ext}",
                        "matched": f"Extension: {ext}",
                        "classification": rule["data_modality"] or "N/A",
                        "confidence": rule["confidence"],
                        "rationale": rule["rationale"],
                    }],
                })
                break  # Only match one rule per file

    # Print summary
    print("\n" + "=" * 70)
    print("IMAGE FILE CLASSIFICATION RESULTS")
    print("=" * 70)

    total_all = 0
    classified_all = 0

    for ext, rule in IMAGE_RULES.items():
        s = stats[ext]
        total_all += s["total"]
        classified_all += s["classified"]
        mod = rule["data_modality"] or "N/A"
        print(f"\n{ext}:")
        print(f"  Total:      {s['total']:>7,}")
        print(f"  Modality:   {mod}")

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
                "by_extension": {ext: stats[ext]["total"] for ext in IMAGE_RULES},
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
