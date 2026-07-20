#!/usr/bin/env python3
"""Classify image files using RuleEngine.

Uses rules from the bundled unified_rules.yaml (package data of meta_disco.rules) for:
- .svs -> imaging.histology (Aperio whole-slide images)
- .png -> derived visualizations (QC plots)
"""

import argparse
import json
from pathlib import Path

# Add project root to path for imports
from meta_disco.header_classifier import filename_for_rules
from meta_disco.models import FileInfo, field_label
from meta_disco.rule_engine import RuleEngine

# Extensions this script classifies; also the set filename_for_rules trusts as
# "usable" so a name lacking one falls back to file_format (issue #157).
IMAGE_EXTENSIONS = (".svs", ".tiff", ".tif", ".png", ".jpg")


def classify_images(metadata_path: Path, output_path: Path):
    """Classify image files using RuleEngine."""

    with metadata_path.open() as f:
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
        for ext in stats:
            if fmt == ext or name_lower.endswith(ext):
                is_image = True
                stats[ext]["total"] = stats[ext].get("total", 0) + 1
                break

        if not is_image:
            continue

        # Classify using RuleEngine. Fall back to file_format when the name
        # carries no usable image extension (issue #157).
        filename = filename_for_rules(name, fmt, default=name, allowed_extensions=IMAGE_EXTENSIONS)
        file_info = FileInfo(
            filename=filename,
            file_size=f.get("file_size"),
            dataset_title=f.get("dataset_title"),
        )
        result = engine.classify_extended(file_info)

        results.append(
            {
                "file_name": name,
                "file_format": fmt,
                "md5sum": f.get("file_md5sum"),
                "file_size": f.get("file_size"),
                "entry_id": f.get("entry_id"),
                "dataset_id": f.get("dataset_id"),
                "dataset_title": f.get("dataset_title"),
                "classifications": result.to_output_dict(),
            }
        )

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
        mod = field_label(r, "data_modality")
        modalities[mod] = modalities.get(mod, 0) + 1

    print("\nBy modality:")
    for mod, count in sorted(modalities.items(), key=lambda x: -x[1]):
        print(f"  {mod}: {count:,}")

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(
            {
                "metadata": {
                    "total_images": total_all,
                    "by_extension": {ext: stats[ext]["total"] for ext in stats if stats[ext]["total"] > 0},
                    "complete": True,
                },
                "classifications": results,
            },
            f,
            indent=2,
        )

    print(f"\nSaved {len(results):,} image classifications to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Classify image files")
    parser.add_argument(
        "--metadata",
        "-m",
        type=Path,
        default=Path("data/anvil/anvil_files_metadata.json"),
        help="Path to source metadata JSON",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output/anvil/image_classifications.json"),
        help="Output path for image classifications",
    )
    args = parser.parse_args()

    classify_images(args.metadata, args.output)


if __name__ == "__main__":
    main()
