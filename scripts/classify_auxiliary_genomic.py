#!/usr/bin/env python3
"""Classify auxiliary genomic files by extension.

FAST5 -> genomic (ONT raw signal, pre-basecalling, no reference)
PLINK (.pvar/.psam/.pgen) -> genomic.germline_variants (genotype data)
"""

import argparse
import json
from pathlib import Path

# Extension-based classification rules
AUXILIARY_RULES = {
    ".fast5": {
        "data_modality": "genomic",
        "reference_assembly": None,  # Raw signal data, pre-basecalling
        "confidence": 0.90,
        "rationale": "FAST5 files contain raw ONT electrical signal data. Reference not applicable until basecalling/alignment.",
    },
    ".pvar": {
        "data_modality": "genomic.germline_variants",
        "reference_assembly": None,  # Set by dataset rule below
        "confidence": 0.90,
        "rationale": "PLINK2 variant information file containing genotype calls.",
    },
    ".psam": {
        "data_modality": "genomic.germline_variants",
        "reference_assembly": None,  # Set by dataset rule below
        "confidence": 0.90,
        "rationale": "PLINK2 sample information file for genotype data.",
    },
    ".pgen": {
        "data_modality": "genomic.germline_variants",
        "reference_assembly": None,  # Set by dataset rule below
        "confidence": 0.90,
        "rationale": "PLINK2 binary genotype file containing variant calls.",
    },
}

# Dataset-based reference assembly rules
DATASET_REFERENCE_RULES = {
    "ANVIL_1000G_PRIMED_data_model": {
        "reference_assembly": "GRCh38",
        "confidence": 0.95,
        "rationale": "1000 Genomes Project high-coverage data uses GRCh38 reference.",
    },
}


def classify_auxiliary_genomic(metadata_path: Path, output_path: Path):
    """Classify auxiliary genomic files based on extension and dataset context."""

    with open(metadata_path) as f:
        data = json.load(f)

    files = data if isinstance(data, list) else data.get("files", data.get("results", []))
    print(f"Loaded {len(files):,} files from metadata")

    results = []
    stats = {}

    for ext in AUXILIARY_RULES:
        stats[ext] = {"total": 0, "with_ref": 0}

    for f in files:
        name = f.get("file_name", "")
        fmt = f.get("file_format", "")
        dataset_title = f.get("dataset_title", "")

        # Check each extension
        for ext, rule in AUXILIARY_RULES.items():
            if fmt == ext or name.lower().endswith(ext):
                stats[ext]["total"] += 1

                # Start with base rule
                data_modality = rule["data_modality"]
                reference_assembly = rule["reference_assembly"]
                confidence = rule["confidence"]
                evidence = [{
                    "rule_id": f"ext_{ext.lstrip('.')}",
                    "matched": f"Extension: {ext}",
                    "classification": data_modality,
                    "confidence": confidence,
                    "rationale": rule["rationale"],
                }]

                # Apply dataset-based reference rules for PLINK files
                if ext in [".pvar", ".psam", ".pgen"]:
                    for ds_pattern, ds_rule in DATASET_REFERENCE_RULES.items():
                        if ds_pattern in dataset_title:
                            reference_assembly = ds_rule["reference_assembly"]
                            confidence = max(confidence, ds_rule["confidence"])
                            evidence.append({
                                "rule_id": "dataset_reference",
                                "matched": f"Dataset: {dataset_title}",
                                "classification": reference_assembly,
                                "confidence": ds_rule["confidence"],
                                "rationale": ds_rule["rationale"],
                            })
                            stats[ext]["with_ref"] += 1
                            break

                results.append({
                    "file_name": name,
                    "file_format": fmt,
                    "md5sum": f.get("file_md5sum"),
                    "file_size": f.get("file_size"),
                    "entry_id": f.get("entry_id"),
                    "dataset_id": f.get("dataset_id"),
                    "dataset_title": dataset_title,
                    "data_modality": data_modality,
                    "reference_assembly": reference_assembly,
                    "confidence": confidence,
                    "matched_rules": [e["rule_id"] for e in evidence],
                    "evidence": evidence,
                })
                break  # Only match one rule per file

    # Print summary
    print("\n" + "=" * 70)
    print("AUXILIARY GENOMIC FILE CLASSIFICATION RESULTS")
    print("=" * 70)

    total_all = 0
    ref_all = 0

    for ext, rule in AUXILIARY_RULES.items():
        s = stats[ext]
        if s["total"] > 0:
            total_all += s["total"]
            ref_all += s["with_ref"]
            ref_pct = s["with_ref"] / s["total"] * 100 if s["total"] > 0 else 0
            print(f"\n{ext}:")
            print(f"  Total:      {s['total']:>7,}")
            print(f"  Modality:   {rule['data_modality']}")
            print(f"  With ref:   {s['with_ref']:>7,} ({ref_pct:.1f}%)")

    print(f"\n{'=' * 70}")
    print(f"Total auxiliary genomic files: {total_all:,}")
    print(f"With reference_assembly: {ref_all:,}")
    print("=" * 70)

    # Count by modality
    modalities = {}
    for r in results:
        mod = r.get("data_modality") or "N/A"
        modalities[mod] = modalities.get(mod, 0) + 1

    print("\nBy modality:")
    for mod, count in sorted(modalities.items(), key=lambda x: -x[1]):
        print(f"  {mod}: {count:,}")

    # Count by reference
    refs = {}
    for r in results:
        ref = r.get("reference_assembly") or "N/A"
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
                "by_extension": {ext: stats[ext]["total"] for ext in AUXILIARY_RULES},
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
        default=Path("output/auxiliary_genomic_classifications.json"),
        help="Output path for classifications",
    )
    args = parser.parse_args()

    classify_auxiliary_genomic(args.metadata, args.output)


if __name__ == "__main__":
    main()
