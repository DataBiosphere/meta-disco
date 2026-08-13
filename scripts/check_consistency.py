#!/usr/bin/env python3
"""Report cross-field self-consistency violations over a classification run (#314).

Report-only spike: writes a markdown report (``docs/consistency-report.md`` by
default) and prints a one-line summary. Exits 0 — gating is a follow-up once the
violation landscape is known. Committing the report gives a diffable baseline.

    uv run python scripts/check_consistency.py                     # latest run -> docs/
    uv run python scripts/check_consistency.py --run-dir output/anvil/20260802_170826
"""

import argparse
from pathlib import Path

from meta_disco.consistency import check_run, load_rules, render_report


def main():
    parser = argparse.ArgumentParser(description="Cross-field self-consistency report over a classification run")
    parser.add_argument("--run-dir", type=Path, default=None, help="Run directory (default: latest under output/anvil)")
    parser.add_argument("--output", type=Path, default=Path("docs/consistency-report.md"), help="Markdown report path")
    parser.add_argument("--examples", type=int, default=3, help="Example violations to show per rule")
    args = parser.parse_args()

    rules = load_rules()
    run_dir, total, violations, activations = check_run(args.run_dir, rules)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(run_dir, total, violations, activations, rules, args.examples))

    print(f"Consistency check over {run_dir} — {total:,} records, {len(violations):,} violations")
    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()
