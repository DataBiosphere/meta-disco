#!/usr/bin/env python3
"""Unified header classification for BAM, VCF, FASTQ, and FASTA files.

Replaces the 4 separate classify_*_files.py scripts with a single entry point.

Examples:
    python scripts/classify_headers.py --type bam -i data/anvil/anvil_files_metadata.json -o output/anvil/bam.json
    python scripts/classify_headers.py --type bam --md5 abc123
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
from meta_disco.file_types import FILE_TYPE_REGISTRY
from meta_disco.pipeline import ClassifyPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Classify files by header inspection",
    )
    parser.add_argument(
        "--type",
        "-t",
        required=True,
        choices=list(FILE_TYPE_REGISTRY.keys()),
        help="File type to classify",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=Path("data/anvil/anvil_files_metadata.json"),
        help="Input metadata file (JSON or NDJSON)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output classification file (explicit path; overrides --run-dir)",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help=(
            "Run folder to write <type>_classifications.json into. Omit for a "
            "standalone run, which lands in a fresh output/anvil/partials/<timestamp>/ "
            "folder; the reports' find_latest_run selects only digit-prefixed run "
            "dirs, so the letter-prefixed partials/ folder is skipped."
        ),
    )
    parser.add_argument(
        "--limit",
        "-l",
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
        "--workers",
        "-w",
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
    parser.add_argument(
        "--evidence-base",
        type=Path,
        default=Path("data/evidence/anvil"),
        help="Evidence cache base directory (per source, e.g. data/evidence/hprc)",
    )

    args = parser.parse_args()
    config = FILE_TYPE_REGISTRY[args.type]

    # Single-file mode
    if args.md5:
        result = ClassifyPipeline.classify_single(
            config,
            args.md5,
            use_cache=not args.no_resume,
            evidence_base=args.evidence_base,
        )
        if result:
            print(json.dumps(result, indent=2))
        else:
            print(f"Failed to classify {args.md5}")
            sys.exit(1)
        return

    # Batch mode — resolve where the output lands:
    #   -o wins (explicit one-off path); else <type>_classifications.json inside the
    #   run dir (--run-dir, shared by `make classify-headers`); else a fresh dated
    #   partials folder. Standalone/per-type runs are test artifacts under
    #   output/anvil/partials/; the reports' find_latest_run selects only
    #   digit-prefixed run dirs, so the letter-prefixed partials/ folder is skipped
    #   (see output_utils.find_latest_run).
    if args.output:
        output_path = args.output
    else:
        run_dir = args.run_dir or (Path("output/anvil/partials") / datetime.now().strftime("%Y%m%d_%H%M%S"))
        output_path = run_dir / f"{args.type}_classifications.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pipeline = ClassifyPipeline(
        config,
        args.input,
        output_path,
        evidence_base=args.evidence_base,
        limit=args.limit,
        resume=not args.no_resume,
        workers=args.workers,
        skip_complete=args.skip_complete,
        skip_cached=args.skip_cached,
    )
    pipeline.run()


if __name__ == "__main__":
    main()
