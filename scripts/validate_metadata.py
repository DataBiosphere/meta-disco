#!/usr/bin/env python3 -u
"""Validate a downloaded AnVIL metadata file against the input-record contract.

A pre-run gate: run it once after `make download`, before committing to a
multi-hour `make classify`, so an API shape change (a renamed key, a newly-null
column, a stringified `file_size`) is caught in seconds with a grouped summary
instead of surfacing as a per-record failure deep in the run. See issue #161.

Exits non-zero if any record violates the contract, if the envelope names no repository
with a declared record key (`pipeline.SOURCE_RECORD_KEYS`, #446), or if that key is
carried by more than one record — the two things a run needs of its input beyond the
records themselves, checked here so they stop a run before it starts.

Usage:
    python scripts/validate_metadata.py
    python scripts/validate_metadata.py --input data/anvil/anvil_files_metadata.json
"""

import argparse
import json
import sys
from pathlib import Path

from meta_disco.metadata_schema import validate_records
from meta_disco.pipeline import key_field, load_snapshot, record_key, repeated_key_values

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
        metadata, records = load_snapshot(args.input)
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

    # The samples name a record by the source's record key, resolved off the envelope
    # the way the run resolves it; an envelope naming none leaves them unnamed, and is
    # refused below, after the record contract has had its say.
    report = validate_records(records, key_field(metadata))
    print(report.summary())
    ok = report.ok

    # The envelope, which the record contract never sees: a run resolves its record key
    # from it, and refuses to start without one.
    try:
        key = record_key(metadata, args.input)
    except ValueError as exc:
        print(f"FAIL — {exc}")
        return 1

    repeated = repeated_key_values(records, key)
    if repeated:
        examples = ", ".join(f"{value} (x{n})" for value, n in sorted(repeated.items())[:_REPEATS_SHOWN])
        more = f", +{len(repeated) - _REPEATS_SHOWN:,} more" if len(repeated) > _REPEATS_SHOWN else ""
        print(
            f"FAIL — {len(repeated):,} value(s) of {key.input_field} are carried by more than one "
            f"record, but a run keys on it as unique per file: {examples}{more}"
        )
        ok = False
    return 0 if ok else 1


# Repeated key values to name before printing a count instead.
_REPEATS_SHOWN = 10


if __name__ == "__main__":
    sys.exit(main())
