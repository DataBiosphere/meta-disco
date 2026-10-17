#!/usr/bin/env python3
"""Read AnVIL's donor facts and its donor and biosample identifiers into entity evidence files, through the entity map (#693, #669).

Checks the map against the manifests on disk first and refuses to write if anything
disagrees, listing every problem. Then writes one generation per dataset under
``data/entity_evidence/anvil/<catalog>/<dataset>/<generation>/`` (the submitter tables)
and ``data/entity_evidence/anvil_published/…`` (AnVIL's ``anvil_donor`` and
``anvil_biosample``), and prints what each table produced and, when every dataset is
imported, the datasets the map leaves out. Offline: it reads what ``make download`` left on disk. The logic
lives in ``meta_disco.anvil_entities``; reconcile reads the files (``reconcile_entities``).

    uv run python scripts/import_anvil_entities.py --check
    uv run python scripts/import_anvil_entities.py
    uv run python scripts/import_anvil_entities.py --dataset ANVIL_T2T
"""

import argparse
import sys
from pathlib import Path

from meta_disco.anvil_entities import check, describe, import_all, left_out
from meta_disco.anvil_evidence import chosen_datasets
from meta_disco.deployments import PROD
from meta_disco.entity_evidence import DEFAULT_ENTITY_EVIDENCE_ROOT
from meta_disco.entity_map import load_entity_map
from meta_disco.source_evidence import unfinished_imports


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import AnVIL's donor facts and donor and biosample identifiers as entity evidence, through the entity map"
    )
    parser.add_argument("--catalog", default=None, help="Azul catalog (default: the one the map was authored against)")
    parser.add_argument("--data-dir", type=Path, default=PROD.input_root, help="Directory holding manifest/<catalog>/")
    parser.add_argument(
        "--service",
        default=PROD.service,
        help=f"The Azul service the manifests were pulled from, written into each file's source url (default: {PROD.service})",
    )
    parser.add_argument("--entity-root", type=Path, default=DEFAULT_ENTITY_EVIDENCE_ROOT)
    parser.add_argument("--dataset", action="append", help="Import only this dataset (repeatable)")
    parser.add_argument("--check", action="store_true", help="Check the map against the manifests and write nothing")
    parser.add_argument(
        "--entity-map", type=Path, default=None, help="An entity map file to read instead of the bundled one"
    )
    args = parser.parse_args()

    entity_map = load_entity_map(args.entity_map)
    catalog = args.catalog or entity_map.catalog
    if catalog != entity_map.catalog:
        print(f"The map was authored against {entity_map.catalog}; importing {catalog} through it.", file=sys.stderr)

    problems = check(entity_map, args.data_dir, catalog, args.dataset)
    if problems:
        print(f"The entity map disagrees with the {catalog} manifests in {len(problems)} place(s):", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1
    checked = chosen_datasets(entity_map.datasets(), args.dataset)
    tables = sum(1 for table in entity_map.tables if table.dataset in checked)
    print(f"Entity map checked against {catalog}: {tables} tables across {len(checked)} dataset(s).")
    if args.check:
        return 0

    for partial in unfinished_imports(args.entity_root):
        print(f"Unfinished import, not read (remove it by hand): {partial}", file=sys.stderr)
    imports = import_all(entity_map, args.data_dir, catalog, args.service, args.entity_root, args.dataset)
    left = left_out(entity_map, args.data_dir, catalog) if args.dataset is None else []
    for line in describe(imports, left):
        print(line)
    print(f"Wrote {sum(t.written for i in imports for t in i.tables):,} entity lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
