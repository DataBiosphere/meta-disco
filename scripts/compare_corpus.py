#!/usr/bin/env python3
"""Compare two corpus generations and write the comparison report (issue #335).

Answers the two questions a single-run coverage report cannot: did the *corpus*
change (input snapshots compared file by file, by md5), and — where coverage
moved — was it the catalog or the classifier (each per-dimension delta split into
files that left, files that arrived, and files present in both runs whose label
changed). The comparison itself lives in ``meta_disco.corpus_diff``; this is the
CLI over it.

The defaults compare the archived anvil14 generation with the current one: the
read-only snapshot and run under ``data/anvil/archive/`` and
``output/anvil/20260802_170826``, against the live input and the latest run dir.

Usage:
    python scripts/compare_corpus.py
    python scripts/compare_corpus.py --new-run output/anvil/20260904_010000
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from meta_disco.corpus_diff import render_report, run_labels, snapshot_meta, snapshot_parity
from meta_disco.output_utils import find_latest_run
from meta_disco.pipeline import load_records

DEFAULT_OLD_SNAPSHOT = Path("data/anvil/archive/anvil14_20260729/anvil_files_metadata.json")
DEFAULT_NEW_SNAPSHOT = Path("data/anvil/anvil_files_metadata.json")
DEFAULT_OLD_RUN = Path("output/anvil/20260802_170826")
DEFAULT_OUTPUT = Path("docs/corpus-comparison.md")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--old-snapshot", type=Path, default=DEFAULT_OLD_SNAPSHOT, help="Baseline input snapshot")
    parser.add_argument("--new-snapshot", type=Path, default=DEFAULT_NEW_SNAPSHOT, help="Current input snapshot")
    parser.add_argument("--old-run", type=Path, default=DEFAULT_OLD_RUN, help="Baseline run directory")
    parser.add_argument(
        "--new-run",
        type=Path,
        default=None,
        help="Current run directory (default: the latest run under output/anvil)",
    )
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT, help="Report to write")
    args = parser.parse_args(argv)

    new_run = args.new_run or find_latest_run(Path("output/anvil"))
    for path in (args.old_snapshot, args.new_snapshot):
        if not path.is_file():
            print(f"Snapshot not found: {path}")
            return 2

    print(f"Snapshots: {args.old_snapshot} → {args.new_snapshot}")
    old_meta = snapshot_meta(args.old_snapshot)
    new_meta = snapshot_meta(args.new_snapshot)
    parity = snapshot_parity(load_records(args.old_snapshot), load_records(args.new_snapshot))

    print(f"Runs: {args.old_run} → {new_run}")
    old_labels = run_labels(args.old_run)
    new_labels = run_labels(new_run)

    report = render_report(
        old_meta=old_meta,
        new_meta=new_meta,
        parity=parity,
        old_run=args.old_run,
        new_run=new_run,
        old_labels=old_labels,
        new_labels=new_labels,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report + "\n")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
