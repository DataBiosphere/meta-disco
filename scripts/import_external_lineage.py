#!/usr/bin/env python3
"""Link each GenomicsDB workspace tar to the declared sample map it was imported from (#710).

For each dataset of ``sources/external_files.yaml``: reads each tar's ``vcfheader.vcf`` from the
tar producer's cache, and, for a tar naming a declared map, its ``callset.json`` from AnVIL's S3
mirror, and writes one generation under
``data/lineage_evidence/external/<catalog>/<dataset>/<generation>/``: a lineage line per tar
whose samples are exactly its map's, and the inputs it read. A workaround until AnVIL holds the
maps (#624). The logic lives in ``meta_disco.external_lineage``.

``--check`` checks the declaration against the deployment, the manifests and the cache, and
writes nothing. ``--inputs`` re-imports from kept inputs instead of the network (repeatable)::

    uv run python scripts/import_external_lineage.py --check
    uv run python scripts/import_external_lineage.py
    uv run python scripts/import_external_lineage.py --inputs data/lineage_evidence/external/anvil15/ANVIL_T2T_CHRY/<generation>/sample_maps.inputs.json

A classification run reads none of it; reconcile (``make reconcile``) does.
"""

import argparse
import sys
from pathlib import Path

from meta_disco.deployments import PROD
from meta_disco.external_files import DEFAULT_EXTERNAL_ROOT, load_external_files
from meta_disco.external_lineage import check, describe, import_all, load_inputs
from meta_disco.lineage_evidence import DEFAULT_LINEAGE_EVIDENCE_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the declared sample maps' lineage for workspace tars")
    parser.add_argument("--data-dir", type=Path, default=PROD.input_root, help="Directory holding manifest/<catalog>/")
    parser.add_argument("--lineage-root", type=Path, default=DEFAULT_LINEAGE_EVIDENCE_ROOT)
    parser.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    parser.add_argument(
        "--evidence-dir", type=Path, default=Path("data/evidence/anvil/tar"), help="The tar producer's cache"
    )
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--check", action="store_true", help="Check the declaration against the deployment and cache")
    which.add_argument("--inputs", type=Path, action="append", help="Import from these kept inputs, not the network")
    args = parser.parse_args()

    declared = load_external_files()
    problems = check(declared, PROD, args.data_dir, args.external_root)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    if args.check:
        files = sum(len(e.sample_maps) for e in declared.entries)
        print(
            f"External files: {files} files of {len(declared.entries)} datasets agree with {PROD.name} and the cache."
        )
        return 0
    stored = load_inputs(args.inputs) if args.inputs else None
    imports = import_all(
        declared,
        args.data_dir,
        args.lineage_root,
        args.evidence_dir,
        args.external_root,
        stored=stored,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
    )
    for line in describe(imports):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
