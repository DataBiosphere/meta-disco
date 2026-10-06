#!/usr/bin/env python3
"""Link each alignment the ENA run lineage map declares to the ENA run whose reads it holds (#594).

For each child dataset of ``sources/ena_run_lineage_map.yaml``: reads each alignment's
``samtools stats`` counts (AnVIL's S3 mirror), the declared studies' runs (ENA's portal
API) and the alignment's ``@PG`` lines (the BAM producer's header cache, or samtools into
it), and writes one generation under
``data/lineage_evidence/ena/<catalog>/<dataset>/<generation>/``: a lineage line per FASTQ
of each linked run, naming the dataset holding it, and the inputs it read. The logic lives
in ``meta_disco.ena_lineage``.

``--check`` checks the map against the deployment and the manifests and writes nothing.
``--inputs`` re-imports from kept inputs instead of the network (repeatable)::

    uv run python scripts/import_ena_lineage.py --check
    uv run python scripts/import_ena_lineage.py
    uv run python scripts/import_ena_lineage.py --inputs data/lineage_evidence/ena/anvil15/ANVIL_T2T_CHRY/<generation>/1KGP_CHM13v2_sample.inputs.json

A classification run reads none of it; reconcile (``make reconcile``) does.
"""

import argparse
import sys
from pathlib import Path

from meta_disco.deployments import PROD
from meta_disco.ena_lineage import check, describe, import_all, load_inputs
from meta_disco.lineage_evidence import DEFAULT_LINEAGE_EVIDENCE_ROOT
from meta_disco.run_lineage_map import load_run_lineage_map


def main() -> int:
    parser = argparse.ArgumentParser(description="Import ENA run lineage for declared alignments")
    parser.add_argument("--data-dir", type=Path, default=PROD.input_root, help="Directory holding manifest/<catalog>/")
    parser.add_argument("--lineage-root", type=Path, default=DEFAULT_LINEAGE_EVIDENCE_ROOT)
    parser.add_argument(
        "--evidence-dir", type=Path, default=Path("data/evidence/anvil/bam"), help="The BAM producer's header cache"
    )
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--check", action="store_true", help="Check the map against the deployment and manifests")
    which.add_argument("--inputs", type=Path, action="append", help="Import from these kept inputs, not the network")
    args = parser.parse_args()

    run_map = load_run_lineage_map()
    problems = check(run_map, PROD, args.data_dir)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    if args.check:
        print(f"Run lineage map: {len(run_map.entries)} entries agree with {PROD.name} and the manifests.")
        return 0
    stored = load_inputs(args.inputs) if args.inputs else None
    imports = import_all(
        run_map,
        args.data_dir,
        args.lineage_root,
        args.evidence_dir,
        stored=stored,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
    )
    for line in describe(imports):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
