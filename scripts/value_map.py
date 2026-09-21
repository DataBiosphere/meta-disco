#!/usr/bin/env python3
"""The value translation table (#414): seed it from evidence files, or list its review queue.

A thin entry point for ``meta_disco.value_map.main``, which says what each command does.

    uv run python scripts/value_map.py --dataset AnVIL_HPRC_R2 --dataset ANVIL_HPRC seed
    uv run python scripts/value_map.py queue
    uv run python scripts/value_map.py queue --output output/review_queue.md
"""

import sys

from meta_disco.value_map import main

if __name__ == "__main__":
    sys.exit(main())
