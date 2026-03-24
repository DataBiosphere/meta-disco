#!/usr/bin/env python3
"""Classify files not handled by any other classifier.

Catches all files that other classifiers skip (unrecognized extensions,
etc.) and runs them through the rule engine. Most will get not_classified
for all dimensions, making them visible in coverage reports.

Usage:
    python scripts/classify_remaining_files.py
    python scripts/classify_remaining_files.py --metadata data/anvil/anvil_files_metadata.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.models import FileInfo
from src.meta_disco.rule_engine import RuleEngine


def load_already_classified(classification_paths: list[Path]) -> set[str]:
    """Load filenames already classified by other scripts."""
    seen = set()
    for path in classification_paths:
        if not path.is_file():
            continue
        with open(path) as f:
            data = json.load(f)
        for r in data.get("classifications", data.get("results", [])):
            name = r.get("file_name", "")
            if name:
                seen.add(name)
    return seen


def classify_remaining(metadata_path: Path, output_path: Path,
                       classification_paths: list[Path]):
    """Classify files not handled by other classifiers."""

    with open(metadata_path) as f:
        data = json.load(f)

    files = data if isinstance(data, list) else data.get("files", data.get("results", []))
    print(f"Loaded {len(files):,} files from metadata")

    already = load_already_classified(classification_paths)
    print(f"Already classified by other scripts: {len(already):,}")

    engine = RuleEngine()
    results = []
    ext_counts = Counter()

    for rec in files:
        name = rec.get("file_name", "")
        if not name or name in already:
            continue

        file_info = FileInfo(
            filename=name,
            file_size=rec.get("file_size"),
            dataset_title=rec.get("dataset_title", ""),
        )
        result = engine.classify_extended(file_info)

        ext = name.rsplit(".", 1)[-1].lower() if "." in name else "(none)"
        ext_counts[ext] += 1

        results.append({
            "file_name": name,
            "file_format": rec.get("file_format", ""),
            "md5sum": rec.get("file_md5sum"),
            "file_size": rec.get("file_size"),
            "entry_id": rec.get("entry_id"),
            "dataset_id": rec.get("dataset_id"),
            "dataset_title": rec.get("dataset_title", ""),
            "classifications": result.to_output_dict(),
        })

    print(f"\nClassified {len(results):,} remaining files")
    print("\nBy extension:")
    for ext, count in ext_counts.most_common(20):
        print(f"  .{ext}: {count:,}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as out:
        json.dump({
            "metadata": {
                "total_files": len(results),
                "by_extension": dict(ext_counts.most_common()),
                "complete": True,
            },
            "classifications": results,
        }, out, indent=2)

    print(f"\nSaved to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Classify files not handled by other classifiers"
    )
    parser.add_argument(
        "--metadata", "-m",
        type=Path,
        default=Path("data/anvil/anvil_files_metadata.json"),
        help="Path to source metadata JSON",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output/anvil/remaining_classifications.json"),
        help="Output path for classifications",
    )
    parser.add_argument(
        "--classifications", "-c",
        type=Path,
        nargs="+",
        default=None,
        help="Classification files from other scripts (to exclude already-classified files)",
    )
    args = parser.parse_args()

    classify_remaining(args.metadata, args.output,
                       args.classifications or [])


if __name__ == "__main__":
    main()
