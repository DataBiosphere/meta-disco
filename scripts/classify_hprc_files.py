#!/usr/bin/env python3
"""Classify HPRC catalog files for validation against catalog metadata.

Fetches headers from HPRC S3 URLs and classifies through the pipeline,
then outputs classifications for comparison against HPRC ground truth.

Catalogs handled:
  - sequencing-data (6K files): BAM/FASTQ headers fetched from S3
  - assemblies (560 files): FASTA contig names fetched from S3
  - alignments (89 files): classified from filename only (graph formats)
  - annotations (8.7K files): classified from filename only (.bed, .gff3, etc.)
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.fetchers import (
    fetch_bam_header,
    fetch_fasta_headers,
    fetch_fastq_reads,
)
from src.meta_disco.header_classifier import (
    classify_from_fasta_header,
    classify_from_fastq_header,
    classify_from_header,
)
from src.meta_disco.models import FileInfo
from src.meta_disco.rule_engine import RuleEngine


def s3_to_https(s3_path: str) -> str:
    """Convert s3://bucket/key to https://s3-us-west-2.amazonaws.com/bucket/key."""
    if s3_path.startswith("s3://"):
        parts = s3_path[5:]
        return f"https://s3-us-west-2.amazonaws.com/{parts}"
    return s3_path


def filename_key(filename: str) -> str:
    """Generate a stable cache key from filename (HPRC catalogs don't provide MD5s)."""
    return hashlib.md5(filename.encode()).hexdigest()


def classify_sequencing_data(
    catalog: list[dict],
    evidence_base: Path,
    limit: int | None = None,
) -> list[dict]:
    """Classify sequencing-data catalog files (BAM/FASTQ) by fetching headers."""
    bam_evidence = evidence_base / "bam"
    fastq_evidence = evidence_base / "fastq"
    bam_evidence.mkdir(parents=True, exist_ok=True)
    fastq_evidence.mkdir(parents=True, exist_ok=True)

    engine = RuleEngine()
    records = catalog[:limit] if limit is not None else catalog
    results = []
    success = 0
    skipped = 0

    print(f"\nClassifying {len(records)} sequencing-data files...")

    for i, rec in enumerate(records):
        fn = rec.get("filename", "")
        s3_path = rec.get("path", "")
        url = s3_to_https(s3_path) if s3_path else None
        key = filename_key(fn)
        file_size = rec.get("fileSize")  # not available in sequencing catalog

        if (i + 1) % 100 == 0 or i == 0:
            print(f"  [{i+1}/{len(records)}] {fn[:50]}", flush=True)

        classifications = None

        if fn.endswith(".bam") or fn.endswith(".cram"):
            raw_data = fetch_bam_header(
                bam_evidence, key, file_name=fn, use_cache=True, url=url,
            )
            if raw_data is not None:
                classifications = classify_from_header(
                    raw_data, file_name=fn, file_size=file_size,
                    file_format=".cram" if fn.endswith(".cram") else ".bam",
                )
        elif fn.endswith(".fastq.gz") or fn.endswith(".fastq"):
            raw_data = fetch_fastq_reads(
                fastq_evidence, key, file_name=fn,
                is_gzipped=fn.endswith(".gz"), use_cache=True, url=url,
            )
            if raw_data is not None:
                classifications = classify_from_fastq_header(
                    raw_data, file_name=fn, file_size=file_size,
                )
        else:
            # FAST5, POD5, etc. — classify from filename only
            skipped += 1
            result = engine.classify_extended(FileInfo(filename=fn, file_size=file_size))
            classifications = result.to_output_dict()

        if classifications:
            success += 1
            results.append({
                "file_name": fn,
                "key": key,
                "file_size": file_size,
                "classifications": classifications,
                "catalog": "sequencing-data",
            })

    print(f"  Classified: {success}, Skipped/failed: {len(records) - success}")
    return results


def classify_assemblies(
    catalog: list[dict],
    evidence_base: Path,
    limit: int | None = None,
) -> list[dict]:
    """Classify assembly catalog files (FASTA) by fetching contig names."""
    fasta_evidence = evidence_base / "fasta"
    fasta_evidence.mkdir(parents=True, exist_ok=True)

    records = catalog[:limit] if limit is not None else catalog
    results = []
    success = 0

    print(f"\nClassifying {len(records)} assembly files...")

    for i, rec in enumerate(records):
        fn = rec.get("filename", "")
        s3_path = rec.get("awsFasta", "")
        url = s3_to_https(s3_path) if s3_path else None
        key = filename_key(fn)
        file_size = rec.get("fileSize")

        if (i + 1) % 100 == 0 or i == 0:
            print(f"  [{i+1}/{len(records)}] {fn[:50]}", flush=True)

        raw_data = fetch_fasta_headers(
            fasta_evidence, key, file_name=fn,
            is_gzipped=fn.endswith(".gz"), use_cache=True, url=url,
        )

        if raw_data is not None:
            classifications = classify_from_fasta_header(
                raw_data, file_name=fn, file_size=file_size,
            )
            success += 1
            results.append({
                "file_name": fn,
                "key": key,
                "file_size": file_size,
                "classifications": classifications,
                "catalog": "assemblies",
            })

    print(f"  Classified: {success}, Failed: {len(records) - success}")
    return results


def classify_filename_only(
    catalog: list[dict],
    catalog_name: str,
) -> list[dict]:
    """Classify files from filename only (no header fetching)."""
    engine = RuleEngine()
    results = []

    print(f"\nClassifying {len(catalog)} {catalog_name} files (filename only)...")

    for rec in catalog:
        fn = rec.get("filename", "")
        if not fn:
            continue
        file_size = rec.get("fileSize")
        result = engine.classify_extended(FileInfo(filename=fn, file_size=file_size))
        results.append({
            "file_name": fn,
            "key": filename_key(fn),
            "file_size": file_size,
            "classifications": result.to_output_dict(),
            "catalog": catalog_name,
        })

    print(f"  Classified: {len(results)}")
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Classify HPRC catalog files for validation",
    )
    parser.add_argument(
        "--catalog-dir",
        type=Path,
        default=Path("data/hprc"),
        help="Directory containing HPRC catalog JSON files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/hprc"),
        help="Output directory for classification results",
    )
    parser.add_argument(
        "--evidence-base",
        type=Path,
        default=Path("data/evidence/hprc"),
        help="Evidence cache base directory",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit files per catalog (for testing)",
    )
    parser.add_argument(
        "--catalogs",
        type=str,
        default="all",
        help="Comma-separated catalogs to classify (sequencing,assemblies,alignments,annotations or all)",
    )
    args = parser.parse_args()

    # Create timestamped output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    catalogs_to_run = args.catalogs.split(",") if args.catalogs != "all" else [
        "sequencing", "assemblies", "alignments", "annotations"
    ]

    all_results = {}

    # Load and classify each catalog
    if "sequencing" in catalogs_to_run:
        catalog_path = args.catalog_dir / "sequencing-data.json"
        if catalog_path.exists():
            with open(catalog_path) as f:
                catalog = json.load(f)
            results = classify_sequencing_data(catalog, args.evidence_base, limit=args.limit)
            all_results["sequencing"] = results
            with open(output_dir / "sequencing_classifications.json", "w") as f:
                json.dump({"classifications": results, "metadata": {"total": len(results)}}, f, indent=2)

    if "assemblies" in catalogs_to_run:
        catalog_path = args.catalog_dir / "assemblies.json"
        if catalog_path.exists():
            with open(catalog_path) as f:
                catalog = json.load(f)
            results = classify_assemblies(catalog, args.evidence_base, limit=args.limit)
            all_results["assemblies"] = results
            with open(output_dir / "assembly_classifications.json", "w") as f:
                json.dump({"classifications": results, "metadata": {"total": len(results)}}, f, indent=2)

    if "alignments" in catalogs_to_run:
        catalog_path = args.catalog_dir / "alignments.json"
        if catalog_path.exists():
            with open(catalog_path) as f:
                catalog = json.load(f)
            results = classify_filename_only(catalog, "alignments")
            all_results["alignments"] = results
            with open(output_dir / "alignment_classifications.json", "w") as f:
                json.dump({"classifications": results, "metadata": {"total": len(results)}}, f, indent=2)

    if "annotations" in catalogs_to_run:
        catalog_path = args.catalog_dir / "annotations.json"
        if catalog_path.exists():
            with open(catalog_path) as f:
                catalog = json.load(f)
            results = classify_filename_only(catalog, "annotations")
            all_results["annotations"] = results
            with open(output_dir / "annotation_classifications.json", "w") as f:
                json.dump({"classifications": results, "metadata": {"total": len(results)}}, f, indent=2)

    # Summary
    print(f"\n{'='*70}")
    print("HPRC CLASSIFICATION SUMMARY")
    print(f"{'='*70}")
    total = 0
    for name, results in all_results.items():
        print(f"  {name}: {len(results)}")
        total += len(results)
    print(f"  Total: {total}")
    print(f"\nOutput: {output_dir}/")


if __name__ == "__main__":
    main()
