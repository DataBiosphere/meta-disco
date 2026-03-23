#!/usr/bin/env python3
"""Unified header classification for BAM, VCF, FASTQ, and FASTA files.

Replaces the 4 separate classify_*_files.py scripts with a single entry point.
File types are selected with --type (comma-separated or "all").

Examples:
    python scripts/classify_headers.py --type bam -i data/anvil_files_metadata.json
    python scripts/classify_headers.py --type bam,vcf,fastq,fasta -i data/metadata.json
    python scripts/classify_headers.py --type all -i data/metadata.json
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.file_types import FILE_TYPE_REGISTRY
from src.meta_disco.pipeline import ClassifyPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Classify files by header inspection",
    )
    parser.add_argument(
        "--type", "-t",
        required=True,
        help="File type(s) to classify: bam, vcf, fastq, fasta, or all (comma-separated)",
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=Path("data/anvil_files_metadata.json"),
        help="Input metadata file (JSON or NDJSON)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output classification file (default: {type}_classifications.json)",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Maximum number of files to process",
    )
    parser.add_argument(
        "--md5",
        type=str,
        default=None,
        help="Classify a single file by MD5 hash",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-fetch headers even if cached",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--skip-complete",
        action="store_true",
        help="Skip if output already has all files classified",
    )
    parser.add_argument(
        "--skip-cached",
        action="store_true",
        help="Skip files that already have cached headers",
    )

    args = parser.parse_args()

    # Parse file types
    if args.type.lower() == "all":
        type_names = list(FILE_TYPE_REGISTRY.keys())
    else:
        type_names = [t.strip().lower() for t in args.type.split(",")]

    for name in type_names:
        if name not in FILE_TYPE_REGISTRY:
            parser.error(f"Unknown file type: {name}. Choose from: {', '.join(FILE_TYPE_REGISTRY)}")

    # Single-file mode
    if args.md5:
        if len(type_names) != 1:
            parser.error("--md5 requires exactly one --type")
        config = FILE_TYPE_REGISTRY[type_names[0]]
        pipeline = ClassifyPipeline(
            config, args.input, args.output or Path(config.default_output),
        )
        result = pipeline.classify_single(args.md5, use_cache=not args.no_resume)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print(f"Failed to classify {args.md5}")
            sys.exit(1)
        return

    # Batch mode
    for name in type_names:
        config = FILE_TYPE_REGISTRY[name]
        output = args.output or Path(config.default_output)

        pipeline = ClassifyPipeline(
            config,
            args.input,
            output,
            limit=args.limit,
            resume=not args.no_resume,
            workers=args.workers,
            skip_complete=args.skip_complete,
            skip_cached=args.skip_cached,
        )
        pipeline.run()


if __name__ == "__main__":
    main()
