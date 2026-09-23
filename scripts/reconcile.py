#!/usr/bin/env python3
"""Reconcile a stored inference run with the source evidence (#432).

A thin entry point for ``meta_disco.reconcile.main``, whose module docstring says what
the stage does.

    uv run python scripts/reconcile.py
    uv run python scripts/reconcile.py --run output/anvil/20260922_221819 --no-evidence
"""

import sys

from meta_disco.reconcile import main

if __name__ == "__main__":
    sys.exit(main())
