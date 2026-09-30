#!/usr/bin/env python3
"""Read AnVIL's tables into lineage evidence files, through the lineage map (#583).

Checks the map against the manifests on disk first and refuses to write if anything
disagrees, listing every problem. Then writes one generation per dataset under
``data/lineage_evidence/anvil/<catalog>/<dataset>/<generation>/``, one file per mapped
table, and prints what each table produced. Offline: it reads what ``make download``
left on disk. The logic lives in ``meta_disco.anvil_lineage``.

    uv run python scripts/import_anvil_lineage.py --check
    uv run python scripts/import_anvil_lineage.py
    uv run python scripts/import_anvil_lineage.py --dataset ANVIL_T2T

No classification run and no reconcile reads these files yet; building each file's
``generated_by`` from them is #577.
"""

import argparse
import sys
from pathlib import Path

from meta_disco.anvil_lineage import check, chosen_datasets, describe, import_all
from meta_disco.deployments import PROD
from meta_disco.lineage_evidence import DEFAULT_LINEAGE_EVIDENCE_ROOT
from meta_disco.lineage_map import load_lineage_map


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import AnVIL's lineage as lineage evidence files, through the lineage map"
    )
    parser.add_argument("--catalog", default=None, help="Azul catalog (default: the one the map was authored against)")
    parser.add_argument("--data-dir", type=Path, default=PROD.input_root, help="Directory holding manifest/<catalog>/")
    parser.add_argument(
        "--service",
        default=PROD.service,
        help=f"The Azul service the manifests were pulled from, written into each file's source url (default: {PROD.service})",
    )
    parser.add_argument("--lineage-root", type=Path, default=DEFAULT_LINEAGE_EVIDENCE_ROOT)
    parser.add_argument("--dataset", action="append", help="Import only this dataset (repeatable)")
    parser.add_argument("--check", action="store_true", help="Check the map against the manifests and write nothing")
    parser.add_argument(
        "--lineage-map", type=Path, default=None, help="A lineage map file to read instead of the bundled one"
    )
    args = parser.parse_args()

    lineage_map = load_lineage_map(args.lineage_map)
    catalog = args.catalog or lineage_map.catalog
    if catalog != lineage_map.catalog:
        print(f"The map was authored against {lineage_map.catalog}; importing {catalog} through it.", file=sys.stderr)

    problems = check(lineage_map, args.data_dir, catalog, args.dataset)
    if problems:
        print(f"The lineage map disagrees with the {catalog} manifests in {len(problems)} place(s):", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    checked = chosen_datasets(lineage_map, args.dataset)
    links = sum(1 for link in lineage_map.links if link.dataset in checked)
    print(f"Lineage map checked against {catalog}: {links} links across {len(checked)} dataset(s).")
    if args.check:
        return 0

    imports = import_all(lineage_map, args.data_dir, catalog, args.service, args.lineage_root, args.dataset)
    for line in describe(imports):
        print(line)
    print(f"Wrote {sum(t.written for i in imports for t in i.tables):,} lineage lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
