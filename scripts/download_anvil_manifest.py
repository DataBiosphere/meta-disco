#!/usr/bin/env python3
"""Download AnVIL file metadata as Azul manifests, one dataset at a time (issue #368).

For every dataset with accessible files in the named catalog this requests a
``compact`` manifest and a ``verbatim.jsonl`` manifest, in that order, one job
in flight at a time, and stores them under::

    <output>/manifest/<catalog>/<dataset>.compact.tsv
    <output>/manifest/<catalog>/<dataset>.verbatim.jsonl
    <output>/manifest/<catalog>/manifests.json      # sidecar: what was fetched, when, how many rows

Then, if every manifest's row count matches the catalog's file count for its
dataset as it stood when the manifest was requested, it derives the
classifier's input from the compact rows::

    <output>/anvil_files_metadata.json     # {"metadata": {...}, "files": [...]}
    <output>/anvil_files_metadata.ndjson   # one record per line

A manifest already on disk is not re-requested unless ``--force`` is given, and
the input file is rebuilt from every dataset on disk either way — ``--datasets``
narrows what is fetched, never what the input file covers, so a targeted
repair cannot shrink the corpus. Discovery decides what to fetch; parity is
judged against the sidecar's stored counts, so a catalog that has moved on
since the pull — or been deleted, as anvil14 was — still rebuilds, and the live
count is reported beside the stored one when the two differ. A parity mismatch
exits non-zero and leaves the input files untouched. A rate-limit or gateway error is waited out, honoring the server's
``Retry-After``, for up to ``--max-wait`` seconds per request (see
``azul_manifest._request``); ``--pause`` seconds separate consecutive jobs.

Usage:
    python scripts/download_anvil_manifest.py --catalog anvil15
    python scripts/download_anvil_manifest.py --catalog anvil15 --datasets AnVIL_ENCORE_293T
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

from meta_disco.azul_manifest import (
    DEFAULT_MAX_WAIT,
    FORMAT_COMPACT,
    FORMATS,
    Dataset,
    HttpSession,
    Sleep,
    count_rows,
    discover_datasets,
    fetch_manifest,
    iter_compact_records,
    load_sidecar,
    manifest_path,
    metadata_block,
    parity_problems,
    save_sidecar,
    write_input_files,
)


def _all_records(root: Path, catalog: str, datasets: list[Dataset]):
    for dataset in datasets:
        yield from iter_compact_records(manifest_path(root, catalog, dataset.title, FORMAT_COMPACT))


def download(
    catalog: str,
    output_dir: Path,
    only: set[str] | None,
    force: bool,
    pause: float = 5.0,
    max_wait: float = DEFAULT_MAX_WAIT,
    session: HttpSession | None = None,
    sleep: Sleep = time.sleep,
) -> int:
    http: HttpSession = session if session is not None else requests.Session()
    output_dir.mkdir(parents=True, exist_ok=True)
    sidecar = load_sidecar(output_dir, catalog)
    stored = sidecar["datasets"]

    log = lambda m: print(f"\n    {m}", end="", flush=True)  # noqa: E731
    try:
        live = {d.title: d for d in discover_datasets(catalog, http, sleep, max_wait, log)}
    except (requests.RequestException, RuntimeError) as exc:
        if not stored or force:
            raise
        # The catalog is gone or unreachable, but its manifests are here.
        print(f"Discovery failed ({exc}); rebuilding from the {len(stored)} dataset(s) on disk", file=sys.stderr)
        live = {}
    # Every dataset the input file covers: the catalog's, plus any on disk from an
    # earlier pull. --datasets narrows only what is fetched.
    titles = list(live) + [t for t in stored if t not in live]
    fetch = set(live)
    if only:
        unknown = only - set(titles)
        if unknown:
            print(f"Not in the {catalog} accessible-dataset facet or on disk: {sorted(unknown)}", file=sys.stderr)
            return 1
        fetch &= only
    accessible = f", {sum(d.file_count for d in live.values()):,} accessible files" if live else ""
    print(f"{catalog}: {len(titles)} dataset(s){accessible}")

    datasets: list[Dataset] = []
    counts: dict[tuple[str, str], int] = {}
    for title in titles:
        try:
            manifest_path(output_dir, catalog, title, FORMAT_COMPACT)
        except ValueError as exc:
            print(f"Refusing dataset title from the catalog: {exc}", file=sys.stderr)
            return 1
        entry = stored.setdefault(title, {})
        on_disk = all(manifest_path(output_dir, catalog, title, fmt).is_file() for fmt in FORMATS)
        if on_disk and not (force and title in fetch) and "file_count" in entry:
            # Parity is judged against the count the manifests were requested under.
            if title in live and live[title].file_count != entry["file_count"]:
                print(f"  {title}: catalog now says {live[title].file_count:,} files, stored {entry['file_count']:,}")
        elif title in live:
            entry["file_count"] = live[title].file_count
        if "file_count" not in entry:
            # Neither a stored count nor a live one: the sidecar entry is from an
            # interrupted first fetch of a dataset the catalog no longer lists.
            print(f"  {title}: no manifests on disk and the catalog no longer lists it", file=sys.stderr)
            return 1
        dataset = Dataset(title, entry["file_count"])
        datasets.append(dataset)
        for fmt in FORMATS:
            path = manifest_path(output_dir, catalog, title, fmt)
            if path.is_file() and not (force and title in fetch):
                print(f"  {title} {fmt}: on disk, {path.stat().st_size:,} bytes")
            elif title not in fetch:
                continue  # missing and not being fetched: parity reports it
            else:
                started = datetime.now()
                print(f"  {title} {fmt}: requesting ...", end="", flush=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                size = fetch_manifest(catalog, fmt, title, path, http, sleep, max_wait=max_wait, log=log)
                elapsed = (datetime.now() - started).total_seconds()
                print(f" {size:,} bytes in {elapsed:.0f}s")
                entry[fmt] = {"requested_at": started.isoformat(), "bytes": size, "seconds": round(elapsed)}
                # A courtesy gap between consecutive jobs; the endpoint has a quota.
                sleep(pause)
            rows = count_rows(fmt, path)
            counts[(title, fmt)] = rows
            entry.setdefault(fmt, {})["rows"] = rows
            save_sidecar(output_dir, catalog, sidecar)

    problems = parity_problems(datasets, counts)
    if problems:
        print("Row counts disagree with the catalog; input file not written:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1

    block = metadata_block(catalog, {d.title: d.file_count for d in datasets}, datetime.now())
    n = write_input_files(output_dir, block, _all_records(output_dir, catalog, datasets))
    print(f"Wrote {n:,} records to {output_dir / 'anvil_files_metadata.json'} (catalog {catalog})")
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
    parser.add_argument("--pause", type=float, default=5.0, help="Seconds to wait between manifest jobs (default 5)")
    parser.add_argument(
        "--max-wait",
        type=float,
        default=DEFAULT_MAX_WAIT,
        help=f"Seconds one request may spend waiting out a rate limit before failing (default {DEFAULT_MAX_WAIT:.0f})",
    )
    args = parser.parse_args(argv)
    only = set(args.datasets) if args.datasets else None
    return download(args.catalog, args.output, only, args.force, args.pause, args.max_wait)


if __name__ == "__main__":
    raise SystemExit(main())
