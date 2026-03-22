"""Shared utilities for working with classification output directories."""

import sys
from pathlib import Path


def find_latest_run(output_dir: Path) -> Path:
    """Find the most recent timestamped run directory.

    Looks for subdirectories whose names start with a digit (e.g., 20260322_112336)
    and returns the one that sorts last (most recent).
    """
    if not output_dir.is_dir():
        print(f"Output directory not found: {output_dir}", file=sys.stderr)
        print("Run 'make classify' first.", file=sys.stderr)
        sys.exit(1)
    runs = sorted(
        [d for d in output_dir.iterdir() if d.is_dir() and d.name[0].isdigit()],
        key=lambda d: d.name,
        reverse=True,
    )
    if not runs:
        print(f"No run directories found in {output_dir}", file=sys.stderr)
        sys.exit(1)
    return runs[0]
