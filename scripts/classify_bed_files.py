#!/usr/bin/env python3
"""Classify BED files by filename patterns and dataset context.

Pattern-based rules:
- modbam2bed/cpg/methylation -> epigenomic.methylation
- TMM/TPM/counts/leafcutter/TSS -> transcriptomic
- peak/summit/chip/atac -> epigenomic.chromatin_accessibility
- .regions.bed -> genomic
- Assembly QC (hap1/2, flagger, switch, dip) -> N/A (derived)

Reference rules:
- T2T datasets -> CHM13
- hg38/GRCh38 in filename -> GRCh38
- chm13 in filename -> CHM13
"""

import argparse
import json
import re
from pathlib import Path

# Pattern-based modality rules (order matters - first match wins)
MODALITY_RULES = [
    {
        "id": "bed_methylation",
        "pattern": r"(modbam2bed|cpg|methylat|bisulfite|wgbs)",
        "data_modality": "epigenomic.methylation",
        "confidence": 0.90,
        "rationale": "BED file contains CpG methylation calls or bisulfite sequencing regions.",
    },
    {
        "id": "bed_expression",
        "pattern": r"(TMM|TPM|RPKM|FPKM|counts|expression|leafcutter|\.TSS\.)",
        "data_modality": "transcriptomic",
        "confidence": 0.90,
        "rationale": "BED file contains gene expression quantification or splicing data.",
    },
    {
        "id": "bed_peaks",
        "pattern": r"(peak|summit|narrowPeak|broadPeak|\.chip\.|\.atac\.)",
        "data_modality": "epigenomic.chromatin_accessibility",
        "confidence": 0.85,
        "rationale": "BED file contains ChIP-seq or ATAC-seq peak calls.",
    },
    {
        "id": "bed_assembly_qc",
        # Must be before bed_regions to catch hap1.regions.bed, etc.
        "pattern": r"(\.hap[12]\.|\.paternal\.|\.maternal\.|\.dip\.bed|\.switch\.|flagger|\.lowQ\.|unreliable|issues\.bed|_genbank\.)",
        "data_modality": None,  # Derived QC, not primary data
        "confidence": 0.85,
        "rationale": "BED file is assembly QC output (haplotype regions, error flags) - derived artifact, not primary data.",
    },
    {
        "id": "bed_regions",
        "pattern": r"\.regions\.bed",
        "data_modality": "genomic",
        "confidence": 0.80,
        "rationale": "BED file contains genomic analysis regions (callable, target, etc.).",
    },
]

# Dataset-based reference rules
DATASET_REFERENCE_RULES = [
    {
        "id": "dataset_t2t",
        "pattern": r"ANVIL_T2T",
        "reference_assembly": "CHM13",
        "confidence": 0.90,
        "rationale": "T2T consortium data uses CHM13 reference.",
    },
]

# Filename-based reference rules
FILENAME_REFERENCE_RULES = [
    {
        "id": "filename_grch38",
        "pattern": r"(hg38|GRCh38|grch38)",
        "reference_assembly": "GRCh38",
        "confidence": 0.95,
        "rationale": "Filename explicitly references GRCh38/hg38.",
    },
    {
        "id": "filename_chm13",
        "pattern": r"(chm13|CHM13|t2t)",
        "reference_assembly": "CHM13",
        "confidence": 0.95,
        "rationale": "Filename explicitly references CHM13/T2T.",
    },
    {
        "id": "filename_grch37",
        "pattern": r"(hg19|GRCh37|grch37|b37)",
        "reference_assembly": "GRCh37",
        "confidence": 0.95,
        "rationale": "Filename explicitly references GRCh37/hg19.",
    },
]


def classify_bed_files(metadata_path: Path, output_path: Path):
    """Classify BED files based on filename patterns and dataset context."""

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

        # Determine modality from filename patterns
        data_modality = None
        modality_confidence = 0.70  # Default low confidence
        evidence = []

        for rule in MODALITY_RULES:
            if re.search(rule["pattern"], name, re.IGNORECASE):
                data_modality = rule["data_modality"]
                modality_confidence = rule["confidence"]
                evidence.append({
                    "rule_id": rule["id"],
                    "matched": f"Pattern: {rule['pattern']}",
                    "classification": data_modality or "N/A",
                    "confidence": rule["confidence"],
                    "rationale": rule["rationale"],
                })
                stats["by_rule"][rule["id"]] = stats["by_rule"].get(rule["id"], 0) + 1
                break

        # If no pattern matched, mark as unclassified genomic intervals
        if not evidence:
            data_modality = "genomic"
            modality_confidence = 0.60
            evidence.append({
                "rule_id": "bed_default",
                "matched": "No specific pattern matched",
                "classification": "genomic",
                "confidence": 0.60,
                "rationale": "BED file with no specific pattern - defaulting to genomic intervals.",
            })
            stats["by_rule"]["bed_default"] = stats["by_rule"].get("bed_default", 0) + 1

        # Determine reference from filename first, then dataset
        reference_assembly = None
        ref_confidence = 0.0

        # Check filename patterns
        for rule in FILENAME_REFERENCE_RULES:
            if re.search(rule["pattern"], name, re.IGNORECASE):
                reference_assembly = rule["reference_assembly"]
                ref_confidence = rule["confidence"]
                evidence.append({
                    "rule_id": rule["id"],
                    "matched": f"Filename pattern: {rule['pattern']}",
                    "classification": reference_assembly,
                    "confidence": rule["confidence"],
                    "rationale": rule["rationale"],
                })
                break

        # If no filename match, check dataset
        if not reference_assembly:
            for rule in DATASET_REFERENCE_RULES:
                if re.search(rule["pattern"], dataset_title, re.IGNORECASE):
                    reference_assembly = rule["reference_assembly"]
                    ref_confidence = rule["confidence"]
                    evidence.append({
                        "rule_id": rule["id"],
                        "matched": f"Dataset: {dataset_title}",
                        "classification": reference_assembly,
                        "confidence": rule["confidence"],
                        "rationale": rule["rationale"],
                    })
                    break

        # Update stats
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

        # Calculate overall confidence
        confidence = modality_confidence
        if reference_assembly:
            confidence = max(modality_confidence, ref_confidence)

        results.append({
            "file_name": name,
            "file_format": f.get("file_format"),
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

    # Print summary
    print("\n" + "=" * 70)
    print("BED FILE CLASSIFICATION RESULTS")
    print("=" * 70)

    print(f"\nTotal BED files: {stats['total']:,}")
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
