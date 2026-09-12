#!/usr/bin/env python3
"""Report this run's answer beside the incumbent AnVIL publishes today (#424).

Writes a markdown report (``docs/incumbent-comparison.md``) and the flat per-file
table beside it (``docs/incumbent-comparison.tsv``) — the ``file_name · dataset ·
slot · azul_value · our_value · recommendation`` shape the retired pipeline's
``classification_results_*.tsv`` had and the move to per-field JSON lost.

Offline: everything it needs is in the run's own output, because the pipeline carries
the incumbent declaration into each record's ``declared`` block. Nothing here changes
a classification. The logic lives in ``meta_disco.incumbent``; this is the CLI wrapper.

    uv run python scripts/generate_incumbent_report.py                     # latest anvil run
    uv run python scripts/generate_incumbent_report.py --run-dir output/anvil/20260909_014657
"""

import argparse
from pathlib import Path

from meta_disco.incumbent import COMPARE, TAKE_AZUL, gather, render_report, render_tsv
from meta_disco.output_utils import find_latest_run

DEFAULT_OUTPUT_DIR = Path("output/anvil")


def main():
    parser = argparse.ArgumentParser(description="Compare a run's classifications against the incumbent AnVIL values")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help=f"Run directory (default: latest under {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/incumbent-comparison.md"),
        help="Markdown report path (the flat table is written beside it as .tsv)",
    )
    args = parser.parse_args()

    run_dir = args.run_dir or find_latest_run(DEFAULT_OUTPUT_DIR)
    report = gather(run_dir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(report))
    tsv_path = args.output.with_suffix(".tsv")
    tsv_path.write_text(render_tsv(report))

    take_azul = sum(c for (_, _, rec), c in report.counts.items() if rec == TAKE_AZUL)
    compare = sum(c for (_, _, rec), c in report.counts.items() if rec == COMPARE)
    print(
        f"{report.files:,} files · {report.declared_files:,} declared · {take_azul:,} take_azul · {compare:,} compare"
    )
    print(f"Written to {args.output} and {tsv_path}")


if __name__ == "__main__":
    main()
