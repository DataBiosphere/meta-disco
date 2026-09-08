#!/usr/bin/env python3
"""Survey what the AnVIL manifests on disk actually carry (#384).

Reads the compact and verbatim manifests a catalog's ``manifests.json`` names and
writes ``docs/manifest-survey.md`` beside ``docs/manifest-survey.json``: compact
column coverage, the verbatim entity census, how far each manifest reaches from a
file to a donor, and whether each dataset can support #369, #336 and #361.

Offline — it reads what ``make download`` already put on disk and fetches
nothing. A manifest the sidecar names but that is not on disk is an error, not a
gap to survey around: the run exits non-zero naming every one of them. Per-column
fill rates would survive a missing dataset, but the corpus totals the report
states against the snapshot count would not, and a survey that quietly covered
eleven of twelve datasets is the wrong thing to hand #369, #336 or #361. The
logic lives in ``meta_disco.manifest_survey``; this is the CLI.

    uv run python scripts/generate_manifest_survey.py
    uv run python scripts/generate_manifest_survey.py --catalog anvil15 --output docs/manifest-survey.md
"""

import argparse
import json
import sys
from pathlib import Path

from meta_disco.manifest_survey import (
    missing_manifests,
    render_report,
    run_survey,
    survey_data,
)

DEFAULT_CATALOG = "anvil15"
DEFAULT_DATA_DIR = Path("data/anvil")


def main() -> int:
    parser = argparse.ArgumentParser(description="Survey what the AnVIL manifests on disk carry")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, help=f"Azul catalog (default: {DEFAULT_CATALOG})")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Directory holding manifest/<catalog>/ (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument("--output", type=Path, default=Path("docs/manifest-survey.md"), help="Markdown report path")
    parser.add_argument("--json", type=Path, default=Path("docs/manifest-survey.json"), help="JSON sidecar path")
    args = parser.parse_args()

    missing = missing_manifests(args.data_dir, args.catalog)
    if missing:
        print(
            f"Cannot survey {args.catalog}: {len(missing)} manifest(s) named in the sidecar are not on disk:",
            file=sys.stderr,
        )
        for line in missing:
            print(f"  {line}", file=sys.stderr)
        print("Run `make download` to fetch them, then survey again.", file=sys.stderr)
        return 1

    survey = run_survey(args.data_dir, args.catalog)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(survey))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(survey_data(survey), indent=2, sort_keys=True) + "\n")

    print(
        f"{args.catalog}: surveyed {len(survey.datasets)} dataset(s), "
        f"{survey.measured_total:,} compact rows against a snapshot of {survey.snapshot_total:,}"
    )
    print(f"Wrote {args.output} and {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
