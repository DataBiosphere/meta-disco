#!/usr/bin/env python3
"""CLI wrapper: run all classifications over the AnVIL metadata, with timestamped output.

The orchestration itself lives in ``meta_disco.classify_run`` (the single classification
path shared with the HPRC source); this script is just the AnVIL-facing entry point.
"""

import argparse
from pathlib import Path

from meta_disco.classify_run import run_all_classifications


def main():
    parser = argparse.ArgumentParser(description="Re-run all classification scripts")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("output/anvil"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--metadata",
        "-m",
        type=Path,
        default=Path("data/anvil/anvil_files_metadata.json"),
        help="Source metadata file (JSON format)",
    )
    parser.add_argument(
        "--evidence-base",
        type=Path,
        default=Path("data/evidence/anvil"),
        help="Evidence cache base directory (per source, e.g. data/evidence/hprc)",
    )
    args = parser.parse_args()
    run_all_classifications(args.metadata, args.output_dir, args.evidence_base)


if __name__ == "__main__":
    main()
