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
from collections import Counter
from pathlib import Path

from meta_disco.models import FileInfo
from meta_disco.pipeline import load_classifiable_snapshot
from meta_disco.records import published_from
from meta_disco.rule_engine import RuleEngine


def load_already_classified(classification_paths: list[Path]) -> set[str]:
    """Entry ids already carrying a classification record from another producer.

    Keyed on ``entry_id``, not on ``file_name``: a name identifies a file only about
    60% of the time here — the corpus holds 708,088 records under 442,865 distinct
    names — so a name-keyed set skips a file because a *different* file elsewhere
    shares its name, and that file then appears in no ``classifications`` array at
    all. ``entry_id`` is unique across the corpus with no collisions.

    The hazard was dormant until #438: every index file used to get a record from
    ``classify_index_files``, so nothing with a colliding name reached this producer.
    Declining an ambiguous parent sends 15,006 index files here, 140 of whose names
    are also carried by matched index records in other datasets.

    ``entry_id`` is Azul's ``files.document_id`` and does not survive a catalog
    re-index — measured, zero of 705,949 records kept theirs from anvil14 to anvil15.
    That does not matter here: this set and the records it is tested against come from
    one run against one snapshot. It does matter for anything published for another
    system to join against, where ``file_id`` is the stable id (#433).
    """
    seen = set()
    for path in classification_paths:
        if not path.is_file():
            continue
        with path.open() as f:
            data = json.load(f)
        for r in data.get("classifications", data.get("results", [])):
            entry_id = r.get("entry_id")
            if entry_id:
                seen.add(entry_id)
    return seen


def classify_remaining(metadata_path: Path, output_path: Path, classification_paths: list[Path]):
    """Classify files not handled by other classifiers."""

    # Records with no usable file_md5sum are excluded here, at the shared load path,
    # so no classification output can name a file the run could never fetch (#376).
    # The load also records what it excluded into the run directory this output lands in.
    source, files = load_classifiable_snapshot(metadata_path, output_path.parent)
    print(f"Loaded {len(files):,} files from metadata")

    already = load_already_classified(classification_paths)
    print(f"Already classified by other scripts: {len(already):,}")

    engine = RuleEngine()
    results = []
    ext_counts = Counter()

    for rec in files:
        name = rec.get("file_name", "")
        if not name or rec.get("entry_id") in already:
            continue

        file_info = FileInfo.from_filename(
            name,
            file_size=rec.get("file_size"),
            dataset_title=rec.get("dataset_title", ""),
        )
        result = engine.classify_extended(file_info)

        ext = name.rsplit(".", 1)[-1].lower() if "." in name else "(none)"
        ext_counts[ext] += 1

        results.append(
            {
                "file_name": name,
                "file_format": rec.get("file_format", ""),
                "md5sum": rec.get("file_md5sum"),
                "file_size": rec.get("file_size"),
                "entry_id": rec.get("entry_id"),
                "dataset_id": rec.get("dataset_id"),
                "dataset_title": rec.get("dataset_title", ""),
                "classifications": result.to_output_dict(),
                # What AnVIL declares about this file today, carried beside what this
                # run concluded (#424). Every producer of a run must write it or the
                # comparison silently under-reports: this catch-all alone holds 5,817
                # of the corpus's 11,231 files with a published value.
                "published": published_from(rec, source),
            }
        )

    print(f"\nClassified {len(results):,} remaining files")
    print("\nBy extension:")
    for ext, count in ext_counts.most_common(20):
        print(f"  .{ext}: {count:,}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as out:
        json.dump(
            {
                "metadata": {
                    "total_files": len(results),
                    "by_extension": dict(ext_counts.most_common()),
                    "complete": True,
                },
                "classifications": results,
            },
            out,
            indent=2,
        )

    print(f"\nSaved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Classify files not handled by other classifiers")
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
        default=Path("output/anvil/remaining_classifications.json"),
        help="Output path for classifications",
    )
    parser.add_argument(
        "--classifications",
        "-c",
        type=Path,
        nargs="+",
        default=None,
        help="Classification files from other scripts (to exclude already-classified files)",
    )
    args = parser.parse_args()

    classify_remaining(args.metadata, args.output, args.classifications or [])


if __name__ == "__main__":
    main()
