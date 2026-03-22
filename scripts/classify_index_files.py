#!/usr/bin/env python3
"""Propagate metadata from parent files to index files.

Index files (.bai, .tbi, .csi, .crai, .pbi) inherit data_modality and
reference_assembly from their parent files (.bam, .vcf.gz, .cram).
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def _get_field(record: dict, field: str):
    """Extract a classification field from either per-field or flat format."""
    # Per-field format: {"classifications": {"field": {"value": ...}}}
    cls = record.get("classifications", {})
    if isinstance(cls, dict) and field in cls:
        entry = cls[field]
        if isinstance(entry, dict) and "value" in entry:
            return entry["value"]
    # Flat format: {"field": value}
    v = record.get(field)
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


def _get_max_confidence(record: dict) -> float:
    """Extract max confidence from either format."""
    cls = record.get("classifications", {})
    if isinstance(cls, dict):
        confs = []
        for v in cls.values():
            if isinstance(v, dict) and "confidence" in v:
                confs.append(v["confidence"])
        if confs:
            return max(confs)
    return record.get("confidence", 0.0) or 0.0

# Index extension -> parent extension mapping
# List specific compound extensions to avoid false candidates from bare .gz
INDEX_TO_PARENT = {
    ".bai": [".bam"],
    ".tbi": [".vcf.gz", ".bed.gz", ".txt.gz", ".tsv.gz", ".gff.gz", ".gtf.gz"],
    ".csi": [".vcf.gz", ".bcf", ".bed.gz"],  # CSI can index BED files too
    ".crai": [".cram"],
    ".pbi": [".bam"],
}


def get_parent_candidates(index_name: str, index_ext: str) -> list[str]:
    """Get possible parent filenames for an index file.

    Handles both patterns:
    - sample.bam.bai -> sample.bam (Pattern 1: index appended to parent)
    - sample.bai -> sample.bam (Pattern 2: index replaces parent ext)
    """
    candidates = []
    parent_exts = INDEX_TO_PARENT.get(index_ext, [])

    if index_name.endswith(index_ext):
        base = index_name[:-len(index_ext)]

        # Pattern 1: index ext appended to parent (sample.bam.bai -> sample.bam)
        # This is the most common pattern
        pattern1_matched = False
        for parent_ext in parent_exts:
            if base.endswith(parent_ext):
                candidates.append(base)
                pattern1_matched = True
                break  # Only add once

        # Pattern 2: index ext replaces parent ext (sample.bai -> sample.bam)
        # Only try this if Pattern 1 didn't match (avoids junk like sample.vcf.gz.vcf.gz)
        if not pattern1_matched:
            for parent_ext in parent_exts:
                candidate = base + parent_ext
                if candidate not in candidates:
                    candidates.append(candidate)

    return candidates


def load_classifications(*paths: Path) -> dict[str, dict]:
    """Load classifications from one or more classification JSON files, keyed by md5sum."""
    classifications = {}

    for path in paths:
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        for c in data.get("classifications", []):
            md5 = c.get("md5sum")
            if md5:
                classifications[md5] = {
                    "data_modality": _get_field(c, "data_modality"),
                    "data_type": _get_field(c, "data_type"),
                    "assay_type": _get_field(c, "assay_type"),
                    "platform": _get_field(c, "platform"),
                    "reference_assembly": _get_field(c, "reference_assembly"),
                    "confidence": _get_max_confidence(c),
                    "source_file": c.get("file_name"),
                }

    return classifications


def propagate_to_index_files(
    metadata_path: Path,
    classification_paths: list[Path],
    output_path: Path,
):
    """Propagate metadata from parent files to index files."""

    # Load source metadata
    with open(metadata_path) as f:
        data = json.load(f)

    files = data if isinstance(data, list) else data.get("files", data.get("results", []))
    print(f"Loaded {len(files):,} files from metadata")

    # Load classifications
    classifications = load_classifications(*classification_paths)
    print(f"Loaded {len(classifications):,} parent classifications")

    # Group files by dataset for matching
    by_dataset = defaultdict(list)
    for f in files:
        ds = f.get("dataset_id", "unknown")
        by_dataset[ds].append(f)

    # Build filename -> file lookup per dataset
    # Also build filename -> md5 lookup
    filename_to_file = {}
    filename_to_md5 = {}
    for ds, ds_files in by_dataset.items():
        for f in ds_files:
            name = f.get("file_name")
            md5 = f.get("file_md5sum")
            if name:
                key = (ds, name)
                filename_to_file[key] = f
                if md5:
                    filename_to_md5[key] = md5

    # Find index files and match to parents
    results = []
    unmatched = []  # Track failed lookups
    stats = defaultdict(lambda: {"total": 0, "matched": 0, "unmatched": 0, "with_modality": 0, "with_ref": 0})

    for ds, ds_files in by_dataset.items():
        for f in ds_files:
            name = f.get("file_name", "")
            fmt = f.get("file_format", "")

            # Check if this is an index file
            index_ext = None
            for ext in INDEX_TO_PARENT.keys():
                if fmt == ext or name.endswith(ext):
                    index_ext = ext
                    break

            if not index_ext:
                continue

            stats[index_ext]["total"] += 1

            # Find parent file
            parent_candidates = get_parent_candidates(name, index_ext)
            parent_md5 = None
            parent_name = None

            for candidate in parent_candidates:
                key = (ds, candidate)
                if key in filename_to_md5:
                    parent_md5 = filename_to_md5[key]
                    parent_name = candidate
                    break

            if not parent_md5:
                # Track the failure with diagnostic info
                stats[index_ext]["unmatched"] += 1
                unmatched.append({
                    "file_name": name,
                    "file_format": fmt,
                    "file_md5sum": f.get("file_md5sum"),
                    "entry_id": f.get("entry_id"),
                    "dataset_id": ds,
                    "dataset_title": f.get("dataset_title"),
                    "index_extension": index_ext,
                    "candidates_tried": parent_candidates,
                    "reason": "no_matching_parent_in_dataset",
                })
                continue

            stats[index_ext]["matched"] += 1

            # Get parent classification
            parent_class = classifications.get(parent_md5, {})

            result = {
                "entry_id": f.get("entry_id"),
                "file_name": name,
                "file_format": fmt,
                "file_md5sum": f.get("file_md5sum"),
                "dataset_id": ds,
                "dataset_title": f.get("dataset_title"),
                "parent_file": parent_name,
                "parent_md5sum": parent_md5,
                "data_modality": parent_class.get("data_modality"),
                "data_type": parent_class.get("data_type"),
                "assay_type": parent_class.get("assay_type"),
                "platform": parent_class.get("platform"),
                "reference_assembly": parent_class.get("reference_assembly"),
                "confidence": parent_class.get("confidence"),
                "inheritance_source": "parent_file",
            }

            if result["data_modality"]:
                stats[index_ext]["with_modality"] += 1
            if result["reference_assembly"]:
                stats[index_ext]["with_ref"] += 1

            results.append(result)

    # Print stats
    print("\n" + "=" * 70)
    print("INDEX FILE INHERITANCE RESULTS")
    print("=" * 70)

    total_all = 0
    matched_all = 0
    unmatched_all = 0
    modality_all = 0
    ref_all = 0

    for ext in INDEX_TO_PARENT.keys():
        s = stats[ext]
        if s["total"] > 0:
            match_pct = s["matched"] / s["total"] * 100
            unmatch_pct = s["unmatched"] / s["total"] * 100
            mod_pct = s["with_modality"] / s["total"] * 100 if s["total"] > 0 else 0
            ref_pct = s["with_ref"] / s["total"] * 100 if s["total"] > 0 else 0
            print(f"\n{ext}:")
            print(f"  Total:              {s['total']:>7,}")
            print(f"  Matched to parent:  {s['matched']:>7,} ({match_pct:.1f}%)")
            print(f"  Unmatched:          {s['unmatched']:>7,} ({unmatch_pct:.1f}%)")
            print(f"  With data_modality: {s['with_modality']:>7,} ({mod_pct:.1f}%)")
            print(f"  With reference:     {s['with_ref']:>7,} ({ref_pct:.1f}%)")

            total_all += s["total"]
            matched_all += s["matched"]
            unmatched_all += s["unmatched"]
            modality_all += s["with_modality"]
            ref_all += s["with_ref"]

    print(f"\n{'=' * 70}")
    print("TOTAL:")
    print(f"  Index files:        {total_all:>7,}")
    if total_all > 0:
        print(f"  Matched to parent:  {matched_all:>7,} ({matched_all/total_all*100:.1f}%)")
        print(f"  Unmatched:          {unmatched_all:>7,} ({unmatched_all/total_all*100:.1f}%)")
        print(f"  With data_modality: {modality_all:>7,} ({modality_all/total_all*100:.1f}%)")
        print(f"  With reference:     {ref_all:>7,} ({ref_all/total_all*100:.1f}%)")
    else:
        print("  No index files found")
    print("=" * 70)

    # Print sample of unmatched files for diagnostics
    if unmatched:
        print("\nSample unmatched index files (showing up to 10):")
        for u in unmatched[:10]:
            print(f"  {u['file_name']}")
            print(f"    Dataset: {u['dataset_id']}")
            print(f"    Tried: {u['candidates_tried']}")

    # Save results in same format as other classification outputs
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to standard classification format (matching bam_classifications.json / vcf_classifications.json)
    _sentinels = {"not_classified", "not_applicable", None}

    def inherited_evidence(field_val, parent):
        """Build evidence entry for an inherited classification field."""
        if field_val and field_val not in _sentinels:
            return [{"rule_id": "inherited_from_parent",
                     "reason": f"Inherited from parent file: {parent}",
                     "confidence": 0.95}]
        return [{"rule_id": "inherited_from_parent",
                 "reason": f"Parent file {parent} had no value for this field",
                 "confidence": 0.0}]

    standard_results = []
    for r in results:
        parent = r["parent_file"]
        standard_results.append({
            "file_name": r["file_name"],
            "file_format": r["file_format"],
            "md5sum": r.get("file_md5sum"),
            "file_size": r.get("file_size"),
            "entry_id": r["entry_id"],
            "dataset_id": r["dataset_id"],
            "dataset_title": r["dataset_title"],
            "parent_file": parent,
            "parent_md5sum": r["parent_md5sum"],
            "classifications": {
                fld: (lambda evi: {"value": r.get(fld), "confidence": evi[0]["confidence"], "evidence": evi})(
                    inherited_evidence(r.get(fld), parent)
                )
                for fld in ["data_modality", "data_type", "platform", "reference_assembly", "assay_type"]
            },
        })

    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_index_files": total_all,
                "matched_to_parent": matched_all,
                "unmatched": unmatched_all,
                "with_data_modality": modality_all,
                "with_reference_assembly": ref_all,
                "complete": True,
            },
            "classifications": standard_results,
            "unmatched_files": unmatched,
        }, f, indent=2)

    print(f"\nSaved {len(standard_results):,} matched + {len(unmatched):,} unmatched index files to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Propagate metadata to index files")
    parser.add_argument(
        "--metadata", "-m",
        type=Path,
        default=Path("data/anvil_files_metadata.json"),
        help="Path to source metadata JSON",
    )
    parser.add_argument(
        "--classifications", "-c",
        type=Path,
        nargs="+",
        help="Paths to classification JSON files (BAM, VCF, BED, FASTQ, FASTA, etc.)",
    )
    # Backwards-compatible args (default to standard output paths)
    parser.add_argument("--bam", "-b", type=Path,
                        default=Path("output/bam_classifications.json"),
                        help="Path to BAM classifications (used when --classifications not provided)")
    parser.add_argument("--vcf", "-v", type=Path,
                        default=Path("output/vcf_classifications.json"),
                        help="Path to VCF classifications (used when --classifications not provided)")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output/index_classifications.json"),
        help="Output path for index classifications",
    )
    args = parser.parse_args()

    # Build list of classification paths (deduplicated)
    if args.classifications:
        cls_paths = list(dict.fromkeys(args.classifications))
    else:
        cls_paths = [args.bam, args.vcf]

    propagate_to_index_files(
        args.metadata,
        cls_paths,
        args.output,
    )


if __name__ == "__main__":
    main()
