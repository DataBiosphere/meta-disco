#!/usr/bin/env python3
"""Download AnVIL file metadata as Azul manifests, one dataset at a time (issue #368).

For every dataset with accessible files in the named catalog this requests a
``compact`` manifest and a ``verbatim.jsonl`` manifest, in that order, one job
in flight at a time, and stores them under::

    <output>/manifest/<catalog>/<dataset>.compact.tsv
    <output>/manifest/<catalog>/<dataset>.verbatim.jsonl
    <output>/manifest/<catalog>/manifests.json      # sidecar: what was fetched, when, how many rows

Then, if every manifest's row count matches the catalog's file count for its
dataset, it derives the classifier's input from the compact rows::

    <output>/anvil_files_metadata.json     # {"metadata": {...}, "files": [...]}
    <output>/anvil_files_metadata.ndjson   # one record per line

A manifest already on disk is not re-requested unless ``--force`` is given; the
input file is rebuilt from whatever is on disk either way. A parity mismatch
exits non-zero and leaves the input file untouched.

Usage:
    python scripts/download_anvil_manifest.py --catalog anvil15
    python scripts/download_anvil_manifest.py --catalog anvil15 --datasets AnVIL_ENCORE_293T
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from meta_disco.azul_manifest import (
    FORMAT_SUFFIX,
    FORMATS,
    Dataset,
    count_rows,
    discover_datasets,
    fetch_manifest,
    metadata_block,
    parity_problems,
    records_from_compact,
)

SIDECAR = "manifests.json"


def manifest_path(manifest_dir: Path, dataset: Dataset, fmt: str) -> Path:
    return manifest_dir / f"{dataset.title}.{FORMAT_SUFFIX[fmt]}"


def load_sidecar(manifest_dir: Path) -> dict:
    path = manifest_dir / SIDECAR
    if path.is_file():
        with path.open() as f:
            return json.load(f)
    return {"datasets": {}}


def save_sidecar(manifest_dir: Path, sidecar: dict) -> None:
    with (manifest_dir / SIDECAR).open("w") as f:
        json.dump(sidecar, f, indent=2, sort_keys=True)


def download(catalog: str, output_dir: Path, only: set[str] | None, force: bool) -> int:
    manifest_dir = output_dir / "manifest" / catalog
    manifest_dir.mkdir(parents=True, exist_ok=True)
    sidecar = load_sidecar(manifest_dir)
    sidecar["catalog"] = catalog

    datasets = discover_datasets(catalog)
    if only:
        unknown = only - {d.title for d in datasets}
        if unknown:
            print(f"Not in the {catalog} accessible-dataset facet: {sorted(unknown)}", file=sys.stderr)
            return 1
        datasets = [d for d in datasets if d.title in only]
    print(f"{catalog}: {len(datasets)} dataset(s), {sum(d.file_count for d in datasets):,} accessible files")

    counts: dict[tuple[str, str], int] = {}
    for dataset in datasets:
        entry = sidecar["datasets"].setdefault(dataset.title, {})
        entry["file_count"] = dataset.file_count
        for fmt in FORMATS:
            path = manifest_path(manifest_dir, dataset, fmt)
            if path.is_file() and not force:
                payload = path.read_bytes()
                print(f"  {dataset.title} {fmt}: on disk, {len(payload):,} bytes")
            else:
                started = datetime.now()
                print(f"  {dataset.title} {fmt}: requesting ...", end="", flush=True)
                payload = fetch_manifest(catalog, fmt, dataset.title)
                path.write_bytes(payload)
                elapsed = (datetime.now() - started).total_seconds()
                print(f" {len(payload):,} bytes in {elapsed:.0f}s")
                entry[fmt] = {"requested_at": started.isoformat(), "bytes": len(payload), "seconds": round(elapsed)}
            rows = count_rows(fmt, payload)
            counts[(dataset.title, fmt)] = rows
            entry.setdefault(fmt, {})["rows"] = rows
            save_sidecar(manifest_dir, sidecar)

    problems = parity_problems(datasets, counts)
    if problems:
        print("Row counts disagree with the catalog; input file not written:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1

    records = []
    for dataset in datasets:
        records.extend(records_from_compact(manifest_path(manifest_dir, dataset, "compact").read_bytes()))
    block = metadata_block(catalog, {d.title: d.file_count for d in datasets}, datetime.now())
    json_path = output_dir / "anvil_files_metadata.json"
    with json_path.open("w") as f:
        json.dump({"metadata": block, "files": records}, f)
    with (output_dir / "anvil_files_metadata.ndjson").open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    print(f"Wrote {len(records):,} records to {json_path} (catalog {catalog})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--catalog",
        required=True,
        help="Azul catalog generation to pull (e.g. anvil15). Required so a snapshot is never unlabelled.",
    )
    parser.add_argument("--output", "-o", type=Path, default=Path("data/anvil"), help="Output directory")
    parser.add_argument("--datasets", nargs="+", help="Only these dataset titles (default: every accessible dataset)")
    parser.add_argument("--force", action="store_true", help="Re-request manifests already on disk")
    args = parser.parse_args(argv)
    return download(args.catalog, args.output, set(args.datasets) if args.datasets else None, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
