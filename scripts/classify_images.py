#!/usr/bin/env python3
"""Classify image files using RuleEngine.

Takes what `PRODUCERS["images"]` claims, and uses rules from the bundled
unified_rules.yaml (package data of meta_disco.rules):
- .svs -> imaging.histology (Aperio whole-slide images)
- the rest -> derived visualizations (QC plots), data_type images only
"""

import argparse
import json
from pathlib import Path

# Add project root to path for imports
from meta_disco.models import FileInfo, field_label
from meta_disco.pipeline import load_classifiable_snapshot
from meta_disco.producers import PRODUCERS
from meta_disco.records import OutputRecord, RunMetadata
from meta_disco.rule_engine import RuleEngine

# Routes through the shared predicate — see meta_disco.producers.
IMAGES = PRODUCERS["images"]


def classify_images(metadata_path: Path, output_path: Path):
    """Classify image files using RuleEngine."""

    # Records with no usable file_md5sum are excluded here, at the shared load path,
    # so no classification output can name a file the run could never fetch (#376).
    # The load also records what it excluded into the run directory this output lands in.
    source, files = load_classifiable_snapshot(metadata_path, output_path.parent)
    print(f"Loaded {len(files):,} files from metadata")

    engine = RuleEngine()
    results = []
    # The registry's tuple has a fixed order, so the summary and the output's
    # by_extension map are ordered identically by every run over one input.
    stats = {ext: {"total": 0} for ext in IMAGES.extensions}

    for f in files:
        matched_ext = IMAGES.claim(f)
        if matched_ext is None:
            continue
        name = f.get("file_name", "")

        stats[matched_ext]["total"] += 1

        # Classify using RuleEngine
        file_info = FileInfo.from_filename(
            name,
            file_size=f.get("file_size"),
            dataset_title=f.get("dataset_title"),
        )
        result = engine.classify_extended(file_info)

        # One record shape for every producer (#450).
        results.append(OutputRecord.from_record(f, result.to_output_dict(), source).to_dict())

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
                "metadata": RunMetadata.from_counts(
                    total=total_all,
                    successful=len(results),
                    from_cache=0,
                    content_unreadable=0,
                    details={"by_extension": {ext: stats[ext]["total"] for ext in stats if stats[ext]["total"] > 0}},
                ).to_dict(),
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
        default=Path("output/anvil") / IMAGES.output,
        help="Output path for image classifications",
    )
    args = parser.parse_args()

    classify_images(args.metadata, args.output)


if __name__ == "__main__":
    main()
