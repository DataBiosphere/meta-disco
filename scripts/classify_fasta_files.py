#!/usr/bin/env python3
"""Classify FASTA files by contig name inspection.

DEPRECATED: Use scripts/classify_headers.py --type fasta instead.
This wrapper is kept for backward compatibility.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.file_types import FASTA_CONFIG
from src.meta_disco.pipeline import ClassifyPipeline


def classify_single_fasta(
    md5sum: str,
    file_name: str = "",
    file_size: int | None = None,
    is_gzipped: bool = True,
    use_cache: bool = True,
) -> dict | None:
    """Backward-compat: classify a single FASTA file by MD5."""
    return ClassifyPipeline.classify_single(
        FASTA_CONFIG, md5sum, file_name=file_name, file_size=file_size,
        is_gzipped=is_gzipped, use_cache=use_cache,
    )


def main():
    parser = argparse.ArgumentParser(description="Fetch FASTA contig names and classify")
    parser.add_argument("--input", "-i", type=str,
                        help="Input file (classification JSON or metadata NDJSON)")
    parser.add_argument("--output", "-o", type=str, default="output/anvil/fasta_classifications.json",
                        help="Output file for classifications")
    parser.add_argument("--limit", "-l", type=int, default=None,
                        help="Limit number of files to process")
    parser.add_argument("--md5", type=str,
                        help="Classify a single file by MD5 hash")
    parser.add_argument("--filename", type=str,
                        help="Classify a single file by filename (with --md5)")
    parser.add_argument("--no-resume", action="store_true",
                        help="Don't use cached headers, re-fetch all")
    parser.add_argument("--workers", "-w", type=int, default=10,
                        help="Number of parallel workers (default: 10)")
    parser.add_argument("--skip-complete", action="store_true",
                        help="Skip if output file already has all files classified")
    parser.add_argument("--skip-cached", action="store_true",
                        help="Skip files entirely if header is already cached")
    args = parser.parse_args()

    if args.md5:
        result = ClassifyPipeline.classify_single(
            FASTA_CONFIG, args.md5, file_name=args.filename or "",
            use_cache=not args.no_resume,
        )
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Failed to fetch or classify")
        return

    if not args.input:
        parser.error("--input required unless using --md5")

    pipeline = ClassifyPipeline(
        FASTA_CONFIG,
        Path(args.input),
        Path(args.output),
        limit=args.limit,
        resume=not args.no_resume,
        workers=args.workers,
        skip_complete=args.skip_complete,
        skip_cached=args.skip_cached,
    )
    pipeline.run()


if __name__ == "__main__":
    main()
