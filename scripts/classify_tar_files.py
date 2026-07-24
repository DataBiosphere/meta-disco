#!/usr/bin/env python3
"""Classify tar / tar.gz archives by reading their member headers (#255).

A container carries no format of its own (#245), so the archive is classified from
its dominant recognized *inner* member format — read from the archive's head via a
range request. Alternatively use scripts/classify_headers.py --type tar.
"""

import argparse
import json
from pathlib import Path

from meta_disco.file_types import TAR_CONFIG
from meta_disco.pipeline import ClassifyPipeline


def classify_single_tar(
    md5sum: str,
    file_name: str = "",
    file_size: int | None = None,
    is_gzipped: bool = False,
    use_cache: bool = True,
) -> dict | None:
    """Classify a single tar/tar.gz archive by MD5. ``is_gzipped`` for a .tar.gz."""
    return ClassifyPipeline.classify_single(
        TAR_CONFIG,
        md5sum,
        file_name=file_name,
        file_size=file_size,
        is_gzipped=is_gzipped,
        use_cache=use_cache,
    )


def main():
    parser = argparse.ArgumentParser(description="Read tar member headers and classify by inner format")
    parser.add_argument("--input", "-i", type=str, help="Input file (classification JSON or metadata NDJSON)")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="output/anvil/tar_classifications.json",
        help="Output file for classifications",
    )
    parser.add_argument("--limit", "-l", type=int, default=None, help="Limit number of files to process")
    parser.add_argument("--md5", type=str, help="Classify a single file by MD5 hash")
    parser.add_argument("--filename", type=str, help="Classify a single file by filename (with --md5)")
    parser.add_argument("--no-resume", action="store_true", help="Don't use cached headers, re-fetch all")
    parser.add_argument("--workers", "-w", type=int, default=10, help="Number of parallel workers (default: 10)")
    parser.add_argument(
        "--skip-complete", action="store_true", help="Skip if output file already has all files classified"
    )
    parser.add_argument("--skip-cached", action="store_true", help="Skip files entirely if header is already cached")
    args = parser.parse_args()

    if args.md5:
        file_name = args.filename or ""
        result = ClassifyPipeline.classify_single(
            TAR_CONFIG,
            args.md5,
            file_name=file_name,
            is_gzipped=file_name.endswith(".gz"),
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
        TAR_CONFIG,
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
