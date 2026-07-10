#!/usr/bin/env python3
"""Validate downloaded AnVIL metadata against the record schema.

Run this after `make download` and before a multi-hour classification run: a
renamed key or a newly-nullable column otherwise surfaces as a crash somewhere
deep in the corpus, or as a silently wrong classification.

    python scripts/validate_metadata.py
    python scripts/validate_metadata.py --input data/anvil/anvil_files_metadata.json

Exit code 1 when the records do not match the schema.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.metadata_schema import (  # noqa: E402
    ANVIL_RECORD_SCHEMA,
    validate_anvil_records,
)

DEFAULT_INPUT = Path("data/anvil/anvil_files_metadata.json")


def load_records(path: Path) -> list[dict]:
    """Read the records array from a metadata file (JSON or NDJSON)."""
    if path.suffix == ".ndjson":
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]

    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"Expected a JSON object, got {type(data).__name__}")
    records = data.get("files") or data.get("results")
    if records is None:
        raise ValueError("JSON object must contain a 'files' or 'results' key")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT,
                        help=f"Metadata file to check (default: {DEFAULT_INPUT})")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"No such file: {args.input}", file=sys.stderr)
        return 1

    records = load_records(args.input)
    report = validate_anvil_records(records)

    print(f"Schema: {len(ANVIL_RECORD_SCHEMA)} fields")
    print(f"Input : {args.input}")
    print(report.summary())

    if report.is_valid:
        return 0

    print(
        "\nThe AnVIL record shape has changed, or the download is incomplete.\n"
        "Fix the schema in src/meta_disco/metadata_schema.py if the change is\n"
        "intended — do NOT coerce the values, or the drift is hidden rather than\n"
        "caught.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
