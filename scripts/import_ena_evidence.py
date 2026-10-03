#!/usr/bin/env python3
"""Read ENA's run records into evidence files, for the files ENA generated (#606).

For every dataset of the catalog (or each ``--dataset``), reads the files its verbatim
manifest names as ENA names a generated FASTQ (``<run>_1.fastq.gz``), asks ENA's portal
API for those runs, and writes one generation under
``data/source_evidence/ena/<catalog>/<dataset>/<generation>/``: the lines of the files
whose md5 ENA's ``fastq_md5`` equals, and ENA's response as fetched. The logic lives in
``meta_disco.ena_evidence``.

``--response`` imports from a stored response instead of the network, once per file,
each for the dataset it names (repeatable):

    uv run python scripts/import_ena_evidence.py
    uv run python scripts/import_ena_evidence.py --dataset ANVIL_T2T
    uv run python scripts/import_ena_evidence.py --response data/source_evidence/ena/anvil15/ANVIL_T2T/<generation>/read_run.response.json

A classification run lists these files and consumes none; reconcile (``make reconcile``,
#432) reads them into its own artifact.
"""

import argparse
import sys
from pathlib import Path

from meta_disco.deployments import PROD
from meta_disco.ena_evidence import Fetch, Response, describe, fetch_runs, import_all, load_response
from meta_disco.source_evidence import DEFAULT_SOURCE_EVIDENCE_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Import ENA's run records as evidence files")
    parser.add_argument("--catalog", default=PROD.catalog, help=f"Azul catalog (default: prod's, {PROD.catalog})")
    parser.add_argument("--data-dir", type=Path, default=PROD.input_root, help="Directory holding manifest/<catalog>/")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_SOURCE_EVIDENCE_ROOT)
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--dataset", action="append", help="Import only this dataset (repeatable)")
    which.add_argument(
        "--response", type=Path, action="append", help="Import from this stored ENA response, not the network"
    )
    args = parser.parse_args()

    fetch: Fetch = fetch_runs
    datasets = args.dataset
    if args.response:
        stored: dict[str, Response] = {}
        for path in args.response:
            response = load_response(path)
            if response.dataset in stored:
                print(f"Two responses for {response.dataset}: give one per dataset.", file=sys.stderr)
                return 1
            stored[response.dataset] = response
        datasets = list(stored)
        fetch = lambda _catalog, dataset, _accessions: stored[dataset]  # noqa: E731

    imports = import_all(args.data_dir, args.catalog, args.evidence_root, fetch, datasets)
    for line in describe(imports):
        print(line)
    print(
        f"Wrote {sum(i.written for i in imports):,} evidence lines for {sum(i.outcomes['matched'] for i in imports):,} files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
