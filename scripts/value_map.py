#!/usr/bin/env python3
"""The value translation table (#414): seed it from evidence files, or list its review queue.

``seed`` appends one seeded row to ``src/meta_disco/rules/value_map.yaml`` for every
``(slot, raw_value)`` the current evidence carries and no row matches; it never rewrites
an existing row. ``queue`` lists every evidence value whose selected row is not authored,
with its source, dataset, table, column and file count (contract 5.2). Both read the
newest generation of each dataset under the evidence root, one line at a time. Offline.

    uv run python scripts/value_map.py --dataset AnVIL_HPRC_R2 --dataset ANVIL_HPRC seed
    uv run python scripts/value_map.py queue
    uv run python scripts/value_map.py queue --output output/review_queue.md
"""

import sys

from meta_disco.value_map import main

if __name__ == "__main__":
    sys.exit(main())
