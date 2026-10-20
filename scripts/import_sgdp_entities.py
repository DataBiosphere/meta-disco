#!/usr/bin/env python3
"""Read SGDP's metadata file into entity evidence for ANVIL_T2T_CHRY's SGDP genomes (#559).

Downloads SGDP's metadata file (refused unless its sha256 is the one pinned), joins it to
T2T_CHRY's SGDP sample tables on SGDP's name, and writes one generation under
``data/entity_evidence/sgdp/<catalog>/ANVIL_T2T_CHRY/<generation>/``: the lines of the samples
whose sex both sides agree on, and the file as read. The logic lives in ``meta_disco.sgdp_entities``.

``--file`` imports from a kept copy instead of the network:

    uv run python scripts/import_sgdp_entities.py
    uv run python scripts/import_sgdp_entities.py --file data/entity_evidence/sgdp/anvil15/ANVIL_T2T_CHRY/<generation>/SGDP_metadata.txt

Reconcile (``make reconcile``) reads the lines into each sample's donor and each donor's record.
"""

import argparse
import sys
from pathlib import Path

from meta_disco.deployments import PROD
from meta_disco.entity_evidence import DEFAULT_ENTITY_EVIDENCE_ROOT
from meta_disco.sgdp_entities import Fetch, describe, fetch, import_sgdp, load_kept


def main() -> int:
    parser = argparse.ArgumentParser(description="Import SGDP's metadata file as entity evidence")
    parser.add_argument("--catalog", default=PROD.catalog, help=f"Azul catalog (default: prod's, {PROD.catalog})")
    parser.add_argument("--data-dir", type=Path, default=PROD.input_root, help="Directory holding manifest/<catalog>/")
    parser.add_argument("--entity-root", type=Path, default=DEFAULT_ENTITY_EVIDENCE_ROOT)
    parser.add_argument("--file", type=Path, help="Import from this kept copy of the file, not the network")
    args = parser.parse_args()

    read: Fetch = fetch if args.file is None else (lambda: load_kept(args.file))
    try:
        result = import_sgdp(args.data_dir, args.catalog, args.entity_root, read)
    except ValueError as exc:
        print(f"import refused: {exc}", file=sys.stderr)
        return 1
    for line in describe(result):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
