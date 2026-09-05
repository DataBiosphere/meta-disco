#!/usr/bin/env python3
"""Report what a classification run could not classify, and why (#376).

Writes a markdown report (``docs/unprocessable-report.md`` by default) grouping every
unprocessable file by reason — checksum-less files excluded from classification,
input-contract violations, and content that could not be read — and prints a one-line
summary. The logic lives in ``meta_disco.unprocessable``; this is the CLI wrapper.

    uv run python scripts/generate_unprocessable_report.py                      # latest anvil run
    uv run python scripts/generate_unprocessable_report.py --run-dir output/hprc/20260728_231939
"""

import argparse
from pathlib import Path

from meta_disco.output_utils import find_latest_run
from meta_disco.unprocessable import (
    CONTENT_UNREADABLE,
    CONTRACT_VIOLATION,
    DEFAULT_EXAMPLES,
    gather,
    reason_total,
    render_report,
)

DEFAULT_OUTPUT_DIR = Path("output/anvil")


def main():
    parser = argparse.ArgumentParser(description="Report what a classification run could not classify, and why")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help=f"Run directory (default: latest under {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/unprocessable-report.md"),
        help="Markdown report path",
    )
    parser.add_argument(
        "--examples",
        type=int,
        default=DEFAULT_EXAMPLES,
        help="Example filenames to show per dataset for the row-backed reasons "
        "(excluded files are always listed in full)",
    )
    args = parser.parse_args()

    run_dir = args.run_dir or find_latest_run(DEFAULT_OUTPUT_DIR)
    data = gather(run_dir, max_examples=args.examples)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(data, max_examples=args.examples))

    unreadable = reason_total(data, CONTENT_UNREADABLE)
    violations = reason_total(data, CONTRACT_VIOLATION)
    print(
        f"Unprocessable files in {run_dir} — "
        f"{len(data.excluded):,} excluded, {violations:,} contract violations, {unreadable:,} unreadable"
    )
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
