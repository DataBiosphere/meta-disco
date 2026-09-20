#!/usr/bin/env python3
"""Read AnVIL's submitter tables into evidence files, through the slot map (#369).

Checks the bundled map against the manifests on disk first and refuses to write if
anything disagrees — every problem is listed, not the first. Then writes one generation
per dataset under ``data/source_evidence/anvil/<catalog>/<dataset>/<generation>/``, one
file per mapped table, and prints what each table produced. Offline: it reads what
``make download`` left on disk. The logic lives in ``meta_disco.anvil_evidence``.

    uv run python scripts/import_anvil_evidence.py --check
    uv run python scripts/import_anvil_evidence.py
    uv run python scripts/import_anvil_evidence.py --dataset AnVIL_HPRC_R2

Nothing reads what this writes until the join (#402) and reconcile (#432) land, so a
classification run's output is unchanged by it.
"""

import argparse
import sys
from pathlib import Path

from meta_disco.anvil_evidence import check, describe, import_all
from meta_disco.slot_map import load_slot_map
from meta_disco.source_evidence import DEFAULT_SOURCE_EVIDENCE_ROOT

DEFAULT_DATA_DIR = Path("data/anvil")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import AnVIL submitter tables as evidence files")
    parser.add_argument("--catalog", default=None, help="Azul catalog (default: the one the map was authored against)")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="Directory holding manifest/<catalog>/")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_SOURCE_EVIDENCE_ROOT)
    parser.add_argument("--dataset", action="append", help="Import only this dataset (repeatable)")
    parser.add_argument("--check", action="store_true", help="Check the map against the manifests and write nothing")
    args = parser.parse_args()

    slot_map = load_slot_map()
    catalog = args.catalog or slot_map.catalog
    if catalog != slot_map.catalog:
        print(f"The map was authored against {slot_map.catalog}; importing {catalog} through it.", file=sys.stderr)

    problems = check(slot_map, args.data_dir, catalog, args.dataset)
    if problems:
        print(f"The slot map disagrees with the {catalog} manifests in {len(problems)} place(s):", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    checked = slot_map.datasets() if args.dataset is None else list(dict.fromkeys(args.dataset))
    entries = sum(1 for e in slot_map.entries if e.dataset in checked)
    print(f"Slot map checked against {catalog}: {entries} column entries across {len(checked)} dataset(s).")
    if args.check:
        return 0

    imports = import_all(slot_map, args.data_dir, catalog, args.evidence_root, args.dataset)
    for line in describe(imports):
        print(line)
    print(
        f"Wrote {sum(t.written for i in imports for t in i.tables):,} evidence rows for {sum(i.files for i in imports):,} files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
