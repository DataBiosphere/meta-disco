#!/usr/bin/env python3 -u
"""Validate a downloaded AnVIL metadata file against the input-record contract.

A pre-run gate: run it once after `make download`, before committing to a
multi-hour `make classify`, so an API shape change (a renamed key, a newly-null
column, a stringified `file_size`) is caught in seconds with a grouped summary
instead of surfacing as a per-record failure deep in the run. See issue #161.

Exits non-zero if any record violates the contract.

Usage:
    python scripts/validate_metadata.py
    python scripts/validate_metadata.py --input data/anvil/anvil_files_metadata.json
"""

import argparse
import json
import sys
from pathlib import Path

from meta_disco.metadata_schema import validate_records
from meta_disco.pipeline import load_records

DEFAULT_INPUT = Path("data/anvil/anvil_files_metadata.json")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Metadata file to validate (default: {DEFAULT_INPUT})",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Input not found: {args.input} (run `make download` first)")
        return 2

    print(f"Validating {args.input} …")
    try:
        records = load_records(args.input)
    except (json.JSONDecodeError, TypeError, ValueError, OSError) as exc:
        # A truncated or wrong-shaped download — or an unreadable file (OSError) — is
        # exactly what this gate exists to catch: report it as a failure, not an
        # uncaught traceback.
        print(f"Could not read {args.input}: {exc}")
        return 1

    if not records:
        # An empty file is almost always a broken download (an auth failure or a
        # run that yielded zero files), not a corpus worth a multi-hour classify.
        print(f"No records found in {args.input} — likely an empty or failed download.")
        return 1

    report = validate_records(records)
    print(report.summary())
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
