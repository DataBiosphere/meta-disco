#!/usr/bin/env python3
"""Run rule engine classification on downloaded AnVIL metadata."""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco import FileInfo, RuleEngine
from src.meta_disco.models import NOT_APPLICABLE, NOT_CLASSIFIED

_SENTINEL_VALUES = {NOT_CLASSIFIED, NOT_APPLICABLE}


def load_metadata(input_path: Path) -> list[dict]:
    """Load metadata from JSON or NDJSON file."""
    if input_path.suffix == ".ndjson":
        files = []
        with open(input_path) as f:
            for line in f:
                if line.strip():
                    files.append(json.loads(line))
        return files
    else:
        with open(input_path) as f:
            data = json.load(f)
        return data.get("files", data)


def run_classification(files: list[dict], engine: RuleEngine) -> list[dict]:
    """Run classification on all files."""
    results = []
    total = len(files)

    for i, file_data in enumerate(files):
        if (i + 1) % 10000 == 0:
            print(f"\rClassifying... {i+1:,}/{total:,} ({100*(i+1)/total:.1f}%)", end="", flush=True)

        file_info = FileInfo(
            filename=file_data.get("file_name", ""),
            file_size=file_data.get("file_size"),
            dataset_title=file_data.get("dataset_title"),
        )

        result = engine.classify(file_info)

        results.append({
            # Original metadata
            "entry_id": file_data.get("entry_id"),  # Needed for API lookups
            "file_id": file_data.get("file_id"),
            "file_name": file_data.get("file_name"),
            "file_format": file_data.get("file_format"),
            "file_size": file_data.get("file_size"),
            "file_md5sum": file_data.get("file_md5sum"),  # Needed for S3 access
            "dataset_id": file_data.get("dataset_id"),
            "dataset_title": file_data.get("dataset_title"),
            # Original API values
            "api_data_modality": file_data.get("data_modality"),
            "api_reference_assembly": file_data.get("reference_assembly"),
            # Classification results
            "predicted_modality": result.data_modality,
            "predicted_reference": result.reference_assembly,
            "confidence": result.confidence,
            "skip": result.skip,
            "needs_header_inspection": result.needs_header_inspection,
            "needs_study_context": result.needs_study_context,
            "needs_manual_review": result.needs_manual_review,
            "rules_matched": "|".join(result.rules_matched),
            "reasons": "|".join(result.reasons),
        })

    print()
    return results


def compute_stats(results: list[dict]) -> dict:
    """Compute classification statistics."""
    total = len(results)
    stats = {
        "total_files": total,
        "classified_with_modality": 0,
        "classified_with_reference": 0,
        "skipped": 0,
        "needs_header_inspection": 0,
        "needs_study_context": 0,
        "needs_manual_review": 0,
        "high_confidence": 0,  # >= 0.9
        "medium_confidence": 0,  # 0.7-0.89
        "low_confidence": 0,  # < 0.7
        "modality_breakdown": {},
        "reference_breakdown": {},
        "file_format_breakdown": {},
        "api_had_modality": 0,
        "api_had_reference": 0,
        "filled_missing_modality": 0,
        "filled_missing_reference": 0,
    }

    for r in results:
        if r["skip"]:
            stats["skipped"] += 1
        if r["needs_header_inspection"]:
            stats["needs_header_inspection"] += 1
        if r["needs_study_context"]:
            stats["needs_study_context"] += 1
        if r["needs_manual_review"]:
            stats["needs_manual_review"] += 1


        mod = r["predicted_modality"]
        if mod and mod not in _SENTINEL_VALUES:
            stats["classified_with_modality"] += 1
        if mod:
            stats["modality_breakdown"][mod] = stats["modality_breakdown"].get(mod, 0) + 1

        ref = r["predicted_reference"]
        if ref and ref not in _SENTINEL_VALUES:
            stats["classified_with_reference"] += 1
        if ref:
            stats["reference_breakdown"][ref] = stats["reference_breakdown"].get(ref, 0) + 1

        conf = r["confidence"]
        if conf >= 0.9:
            stats["high_confidence"] += 1
        elif conf >= 0.7:
            stats["medium_confidence"] += 1
        elif conf > 0:
            stats["low_confidence"] += 1

        # Track file formats
        fmt = r.get("file_format", "unknown")
        stats["file_format_breakdown"][fmt] = stats["file_format_breakdown"].get(fmt, 0) + 1

        # Compare with API values
        if r["api_data_modality"]:
            stats["api_had_modality"] += 1
        if r["api_reference_assembly"]:
            stats["api_had_reference"] += 1

        # Count where we filled missing values (exclude sentinels)
        if mod and mod not in _SENTINEL_VALUES and not r["api_data_modality"]:
            stats["filled_missing_modality"] += 1
        if ref and ref not in _SENTINEL_VALUES and not r["api_reference_assembly"]:
            stats["filled_missing_reference"] += 1

    return stats


def save_results(results: list[dict], stats: dict, output_dir: Path):
    """Save classification results and stats."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save full results as JSON
    json_path = output_dir / f"classification_results_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump({
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "total_files": len(results),
            },
            "stats": stats,
            "results": results,
        }, f, indent=2)
    print(f"Saved JSON results to {json_path}")

    # Save as TSV for easy viewing
    tsv_path = output_dir / f"classification_results_{timestamp}.tsv"
    if results:
        with open(tsv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys(), delimiter="\t")
            writer.writeheader()
            writer.writerows(results)
    print(f"Saved TSV results to {tsv_path}")

    # Save stats summary
    stats_path = output_dir / f"classification_stats_{timestamp}.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Saved stats to {stats_path}")

    # Print summary
    print("\n" + "=" * 70)
    print("CLASSIFICATION SUMMARY")
    print("=" * 70)
    print(f"Total files:                  {stats['total_files']:,}")
    print(f"Skipped (index/checksum):     {stats['skipped']:,} ({100*stats['skipped']/stats['total_files']:.1f}%)")
    print()
    print("MODALITY CLASSIFICATION:")
    print(f"  Classified with modality:   {stats['classified_with_modality']:,} ({100*stats['classified_with_modality']/stats['total_files']:.1f}%)")
    print(f"  API had modality:           {stats['api_had_modality']:,} ({100*stats['api_had_modality']/stats['total_files']:.1f}%)")
    print(f"  Filled missing modality:    {stats['filled_missing_modality']:,}")
    print()
    print("REFERENCE CLASSIFICATION:")
    print(f"  Classified with reference:  {stats['classified_with_reference']:,} ({100*stats['classified_with_reference']/stats['total_files']:.1f}%)")
    print(f"  API had reference:          {stats['api_had_reference']:,} ({100*stats['api_had_reference']/stats['total_files']:.1f}%)")
    print(f"  Filled missing reference:   {stats['filled_missing_reference']:,}")
    print()
    print("CONFIDENCE LEVELS:")
    print(f"  High (>=90%):               {stats['high_confidence']:,}")
    print(f"  Medium (70-89%):            {stats['medium_confidence']:,}")
    print(f"  Low (<70%):                 {stats['low_confidence']:,}")
    print()
    print("NEEDS FURTHER WORK:")
    print(f"  Needs header inspection:    {stats['needs_header_inspection']:,}")
    print(f"  Needs study context:        {stats['needs_study_context']:,}")
    print(f"  Needs manual review:        {stats['needs_manual_review']:,}")
    print()
    print("TOP MODALITIES:")
    for mod, count in sorted(stats["modality_breakdown"].items(), key=lambda x: -x[1])[:10]:
        print(f"  {mod:<35} {count:>8,}")
    print()
    print("REFERENCE ASSEMBLIES:")
    for ref, count in sorted(stats["reference_breakdown"].items(), key=lambda x: -x[1]):
        print(f"  {ref:<35} {count:>8,}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Run batch classification on AnVIL metadata")
    parser.add_argument("--input", "-i", type=str, default="data/anvil_files_metadata.json",
                        help="Input metadata file (JSON or NDJSON)")
    parser.add_argument("--output", "-o", type=str, default="output",
                        help="Output directory")
    parser.add_argument("--rules", "-r", type=str, default="rules/unified_rules.yaml",
                        help="Path to rules file")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        print("Run scripts/download_anvil_metadata.py first to download the data.")
        return 1

    print(f"Loading metadata from {input_path}...")
    files = load_metadata(input_path)
    print(f"Loaded {len(files):,} files")

    print(f"\nLoading rules from {args.rules}...")
    engine = RuleEngine(args.rules)

    print("\nRunning classification...")
    results = run_classification(files, engine)

    print("\nComputing statistics...")
    stats = compute_stats(results)

    save_results(results, stats, output_dir)

    return 0


if __name__ == "__main__":
    exit(main())
