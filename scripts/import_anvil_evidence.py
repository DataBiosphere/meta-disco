#!/usr/bin/env python3
"""Read AnVIL's tables into evidence files, through a slot map (#369, #497).

Checks the map against the manifests on disk first and refuses to write if anything
disagrees — every problem ``check`` finds is listed, not only the first (a missing
manifest or an empty table masks what is beneath it). Then writes one generation per
dataset under ``data/source_evidence/<source-dir>/<catalog>/<dataset>/<generation>/``,
one file per mapped table, and prints what each table produced. Offline: it reads what
``make download`` left on disk. The logic lives in ``meta_disco.anvil_evidence``.

The map is the bundled submitter map by default, written under ``anvil/``. The
published map (``--slot-map`` naming ``anvil_published_slot_map.yaml``, ``--source-dir
anvil_published``; ``make import-anvil-published``) reads the harmonized ``anvil_file``
columns through the same importer, and its files carry the map's own ``source_type``.

    uv run python scripts/import_anvil_evidence.py --check
    uv run python scripts/import_anvil_evidence.py
    uv run python scripts/import_anvil_evidence.py --dataset AnVIL_HPRC_R2
    uv run python scripts/import_anvil_evidence.py --slot-map src/meta_disco/sources/anvil_published_slot_map.yaml --source-dir anvil_published

A classification run lists these files (``report_evidence_files``) and consumes none,
so its output is unchanged by them; ``make name-signals ARGS=--evidence`` is what reads
them today.
"""

import argparse
import sys
from pathlib import Path

from meta_disco.anvil_evidence import check, describe, import_all
from meta_disco.azul_manifest import REPOSITORY
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
    parser.add_argument("--slot-map", type=Path, default=None, help="A slot map to read instead of the bundled one")
    parser.add_argument(
        "--source-dir", default=REPOSITORY, help="Directory under the evidence root the generations go to"
    )
    args = parser.parse_args()

    slot_map = load_slot_map(args.slot_map)
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

    imports = import_all(slot_map, args.data_dir, catalog, args.evidence_root, args.dataset, source=args.source_dir)
    for line in describe(imports):
        print(line)
    print(
        f"Wrote {sum(t.written for i in imports for t in i.tables):,} evidence rows for {sum(i.files for i in imports):,} files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
