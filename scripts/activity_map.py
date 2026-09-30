#!/usr/bin/env python3
"""The activity translation table (#584): seed it from lineage evidence, or print its review queue.

A thin entry point for ``meta_disco.activity_map.main``, which says what each command does.

    uv run python scripts/activity_map.py seed
    uv run python scripts/activity_map.py --dataset ANVIL_T2T queue
"""

import sys

from meta_disco.activity_map import main

if __name__ == "__main__":
    sys.exit(main())
