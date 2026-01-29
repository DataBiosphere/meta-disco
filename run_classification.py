#!/usr/bin/env python3
"""Run rule engine classification on files from various sources."""

import argparse
import json
import sys
from pathlib import Path

import requests

from src.meta_disco import RuleEngine, FileInfo


def load_from_tsv(path: str) -> list[FileInfo]:
    """Load file info from a TSV file."""
    import csv
    files = []
    with open(path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            files.append(FileInfo(
                filename=row.get('filename', row.get('file_name', '')),
                file_size=int(row['file_size']) if row.get('file_size') else None,
                dataset_title=row.get('title', row.get('dataset_title')),
            ))
    return files


def fetch_from_anvil_api(limit: int = 100) -> list[FileInfo]:
    """Fetch files from the AnVIL API."""
    url = "https://service.explore.anvilproject.org/index/files"
    params = {
        "size": limit,
        "filters": json.dumps({"access": {"is": ["open"]}})
    }

    print(f"Fetching {limit} files from AnVIL API...")
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    files = []
    for hit in data.get("hits", []):
        files.append(FileInfo(
            filename=hit.get("file_name", ""),
            file_size=hit.get("file_size"),
            dataset_title=hit.get("datasets", [{}])[0].get("title", [""])[0] if hit.get("datasets") else None,
        ))
    return files


def get_sample_files() -> list[FileInfo]:
    """Return sample files from the PRD/API exploration."""
    return [
        # Alignment files
        FileInfo("m64043_210211_005516.hifi_reads.bam", 50_000_000_000),
        FileInfo("HG002.trio.bam", 120_000_000_000),
        FileInfo("sample_RNA_aligned.hg38.bam", 5_000_000_000),
        FileInfo("sample.Aligned.sortedByCoord.out.bam", 3_000_000_000),
        FileInfo("HG01879.CHM13v2.cram", 30_000_000_000),
        FileInfo("NA12878.grch38.wgs.cram", 80_000_000_000),

        # Variant files
        FileInfo("NA19189.chr2.hc.vcf.gz"),
        FileInfo("clinvar_20210308.noY.GRCh38.rejected_position-failed.vcf.gz"),
        FileInfo("sample.hg19.filtered.vcf"),
        FileInfo("joint_calls.g.vcf.gz"),

        # Index/checksum files (should skip)
        FileInfo("HG02558.final.cram.md5"),
        FileInfo("sample.bam.bai"),
        FileInfo("variants.vcf.gz.tbi"),
        FileInfo("alignment.cram.crai"),

        # Single-cell
        FileInfo("pbmc_10x_v3.h5ad"),
        FileInfo("brain_atac_peaks.h5ad"),

        # Epigenomics
        FileInfo("sample_H3K27ac_ChIP.bigwig"),
        FileInfo("GM12878_ATAC.bw"),
        FileInfo("sample.idat"),

        # Imaging
        FileInfo("GTEX-18A6Q-1126.svs"),
        FileInfo("assembly_merqury_plot.png"),

        # Nanopore
        FileInfo("flowcell_001.fast5"),
        FileInfo("sample_direct_rna.pod5"),

        # FASTQ
        FileInfo("sample_rnaseq_R1.fastq.gz"),
        FileInfo("SRR123456_1.fastq.gz"),
        FileInfo("HG002_WGS_R1.fq.gz"),

        # Text/ambiguous
        FileInfo("sample.samtools.stats.txt"),
        FileInfo("gene_counts.txt"),
        FileInfo("mosdepth.summary.txt"),
        FileInfo("random_data.txt"),

        # PLINK genotypes
        FileInfo("ukb_chr22.pgen"),
        FileInfo("cohort.pvar"),

        # Archives
        FileInfo("chr5.136400001_136500001.tar", dataset_title="ANVIL_T2T"),

        # Signal tracks
        FileInfo("coverage.bedGraph"),
        FileInfo("sample_rna_coverage.bw"),
    ]


def print_results(files: list[FileInfo], engine: RuleEngine, output_format: str = "table"):
    """Classify files and print results."""
    results = []

    for file_info in files:
        result = engine.classify(file_info)
        results.append((file_info, result))

    if output_format == "json":
        output = []
        for file_info, result in results:
            output.append({
                "filename": file_info.filename,
                "file_size": file_info.file_size,
                "dataset_title": file_info.dataset_title,
                "data_modality": result.data_modality,
                "reference_assembly": result.reference_assembly,
                "confidence": result.confidence,
                "skip": result.skip,
                "needs_header_inspection": result.needs_header_inspection,
                "needs_study_context": result.needs_study_context,
                "needs_manual_review": result.needs_manual_review,
                "rules_matched": result.rules_matched,
                "reasons": result.reasons,
            })
        print(json.dumps(output, indent=2))
    else:
        # Table format
        print(f"\n{'='*100}")
        print(f"{'Filename':<50} {'Modality':<30} {'Ref':<10} {'Conf':>5} {'Status'}")
        print(f"{'='*100}")

        # Stats
        stats = {
            "total": 0,
            "classified": 0,
            "skipped": 0,
            "needs_header": 0,
            "needs_context": 0,
            "needs_review": 0,
        }

        for file_info, result in results:
            stats["total"] += 1

            filename = file_info.filename[:48] + ".." if len(file_info.filename) > 50 else file_info.filename
            modality = result.data_modality or "-"
            ref = result.reference_assembly or "-"
            conf = f"{result.confidence:.0%}" if result.confidence > 0 else "-"

            if result.skip:
                status = "SKIP"
                stats["skipped"] += 1
            elif result.needs_manual_review:
                status = "REVIEW"
                stats["needs_review"] += 1
            elif result.needs_header_inspection:
                status = "HEADER"
                stats["needs_header"] += 1
            elif result.needs_study_context:
                status = "CONTEXT"
                stats["needs_context"] += 1
            elif result.data_modality:
                status = "OK"
                stats["classified"] += 1
            else:
                status = "?"

            print(f"{filename:<50} {modality:<30} {ref:<10} {conf:>5} {status}")

        print(f"{'='*100}")
        print(f"\nSummary:")
        print(f"  Total files:        {stats['total']}")
        print(f"  Classified:         {stats['classified']} ({100*stats['classified']/stats['total']:.1f}%)")
        print(f"  Skipped (index/md5):{stats['skipped']} ({100*stats['skipped']/stats['total']:.1f}%)")
        print(f"  Needs header:       {stats['needs_header']} ({100*stats['needs_header']/stats['total']:.1f}%)")
        print(f"  Needs context:      {stats['needs_context']} ({100*stats['needs_context']/stats['total']:.1f}%)")
        print(f"  Needs review:       {stats['needs_review']} ({100*stats['needs_review']/stats['total']:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="Run rule engine classification")
    parser.add_argument("--source", choices=["sample", "api", "tsv"], default="sample",
                        help="Data source: sample (built-in examples), api (fetch from AnVIL), tsv (local file)")
    parser.add_argument("--tsv", type=str, help="Path to TSV file (required if source=tsv)")
    parser.add_argument("--limit", type=int, default=100, help="Number of files to fetch from API")
    parser.add_argument("--format", choices=["table", "json"], default="table", help="Output format")
    parser.add_argument("--rules", type=str, default="rules/unified_rules.yaml", help="Path to rules file")
    args = parser.parse_args()

    # Load rules
    engine = RuleEngine(args.rules)

    # Load files from source
    if args.source == "sample":
        files = get_sample_files()
        print(f"Using {len(files)} sample files from PRD examples")
    elif args.source == "api":
        files = fetch_from_anvil_api(args.limit)
        print(f"Fetched {len(files)} files from AnVIL API")
    elif args.source == "tsv":
        if not args.tsv:
            print("Error: --tsv path required when source=tsv", file=sys.stderr)
            sys.exit(1)
        files = load_from_tsv(args.tsv)
        print(f"Loaded {len(files)} files from {args.tsv}")

    # Run classification
    print_results(files, engine, args.format)


if __name__ == "__main__":
    main()
