#!/usr/bin/env python3
"""What a submitter name would claim, measured against a stored run (#369).

By default measures every dataset the catalog's sidecar names, with no slot map: for
each file a submitter table links, what its table name and column name would claim by
``manifest_survey.NAME_TOKENS``, and whether a run (the latest under output/anvil by
default) agrees. With ``--evidence``
it measures the written evidence instead — the newest generation of each dataset under
the evidence root — and prints the numbers an import is judged on. Both are forecasts
for the translation table (#414) and the resolver; neither is an input to the map.

    uv run python scripts/name_signals.py
    uv run python scripts/name_signals.py --dataset ANVIL_T2T_CHRY --run output/anvil/20260919_195611
    uv run python scripts/name_signals.py --evidence
"""

import argparse
import sys
from pathlib import Path

from meta_disco.anvil_forecast import (
    evidence_forecast,
    index_run,
    name_signals,
    render_evidence_forecast,
    render_name_signals,
)
from meta_disco.azul_manifest import DEFAULT_CATALOG
from meta_disco.output_utils import find_latest_run
from meta_disco.source_evidence import DEFAULT_SOURCE_EVIDENCE_ROOT

DEFAULT_DATA_DIR = Path("data/anvil")
DEFAULT_OUTPUT_DIR = Path("output/anvil")


def main() -> int:
    parser = argparse.ArgumentParser(description="Forecast what submitter names, or written evidence, would claim")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Directory holding manifest/<catalog>/")
    parser.add_argument(
        "--run", type=Path, default=None, help="A run directory (default: the latest under output/anvil)"
    )
    parser.add_argument("--dataset", action="append", help="Measure only this dataset (repeatable)")
    parser.add_argument("--evidence", action="store_true", help="Measure the written evidence instead of the names")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_SOURCE_EVIDENCE_ROOT)
    parser.add_argument("--output", type=Path, default=None, help="Write the markdown here instead of stdout")
    args = parser.parse_args()

    run_dir = args.run if args.run is not None else find_latest_run(DEFAULT_OUTPUT_DIR)
    print(f"Indexing {run_dir} ...", file=sys.stderr)
    run = index_run(run_dir)
    print(f"{len(run):,} records with a drs_uri", file=sys.stderr)

    if args.evidence:
        report = render_evidence_forecast(evidence_forecast(args.evidence_root, run), args.evidence_root, run_dir)
    else:
        report = render_name_signals(name_signals(args.data_dir, args.catalog, run, args.dataset), run_dir)
    if args.output is not None:
        args.output.write_text(report)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
