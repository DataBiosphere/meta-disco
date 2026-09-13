#!/usr/bin/env python3
"""Compare this run's inferred values against the ones the repository publishes (#424).

Writes a markdown report (``docs/published-comparison.md``) and the flat per-file
table beside it (``docs/published-comparison.tsv``) — the published value beside the
inferred one, per file, which is the shape the retired pipeline's
``classification_results_*.tsv`` had and the move to per-field JSON lost.

Offline: everything it needs is in the run's own output, because the pipeline carries
the published values into each record's ``published`` block. Nothing here changes a
classification. The logic lives in ``meta_disco.published_comparison``; this is the
CLI wrapper.

    uv run python scripts/generate_published_comparison.py                    # latest run
    uv run python scripts/generate_published_comparison.py --run-dir output/anvil/20260912_152414
"""

import argparse
from pathlib import Path

from meta_disco.output_utils import find_latest_run
from meta_disco.published_comparison import KEEP, REVIEW, gather, render_report, render_tsv

DEFAULT_OUTPUT_DIR = Path("output/anvil")


def main():
    parser = argparse.ArgumentParser(
        description="Compare a run's inferred values against the ones the repository publishes"
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help=f"Run directory (default: latest under {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/published-comparison.md"),
        help="Markdown report path (the flat table is written beside it as .tsv)",
    )
    args = parser.parse_args()

    run_dir = args.run_dir or find_latest_run(DEFAULT_OUTPUT_DIR)
    report = gather(run_dir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(report))
    tsv_path = args.output.with_suffix(".tsv")
    tsv_path.write_text(render_tsv(report))

    keep = sum(c for (_, _, rec), c in report.counts.items() if rec == KEEP)
    review = sum(c for (_, _, rec), c in report.counts.items() if rec == REVIEW)
    print(
        f"{report.files:,} files · {report.published_files:,} with a published value · "
        f"{keep:,} keep · {review:,} review"
    )
    print(f"Written to {args.output} and {tsv_path}")


if __name__ == "__main__":
    main()
