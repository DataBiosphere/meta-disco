#!/usr/bin/env python3
"""Derive one AnVIL deployment's classifier input from a named input source (issues #368, #500).

The deployment (``--deployment``, ``prod`` by default) names the Azul service, the
catalog, the datasets with their TDR snapshots, and the root everything below is
written under — ``data/anvil/prod/`` or ``data/anvil/dev/`` (``meta_disco.deployments``).
The input source (``--input-source``) names how the records are derived:

- ``azul-compact`` (the default; today's behaviour): for every dataset the deployment
  declares, request a ``compact`` manifest and a ``verbatim.jsonl`` manifest, in that
  order, one job in flight at a time, and derive the records from the compact join.
- ``azul-verbatim``: request the verbatim manifest only, and derive the records from
  its ``anvil_file`` and ``anvil_dataset`` entities through
  ``snapshot_input.AzulVerbatim``.
- ``tdr-direct``: request nothing. Read each declared snapshot's tables in place from
  BigQuery through ``snapshot_input.TdrDirect``, with whatever identity the
  environment supplies (see ``meta_disco.tdr``) and the ``tdr`` extra installed.

An unknown deployment or input source is refused by the argument parser, before any
request, query or write. Every kind writes the same two files under the root::

    <root>/anvil_files_metadata.json     # {"metadata": {...}, "files": [...]}
    <root>/anvil_files_metadata.ndjson   # one record per line

and the two Azul kinds store what they fetched beside them::

    <root>/manifest/<catalog>/<dataset>.compact.tsv       # azul-compact only
    <root>/manifest/<catalog>/<dataset>.verbatim.jsonl
    <root>/manifest/<catalog>/manifests.json              # sidecar: what was fetched, when, how many rows

The envelope names the deployment, the input source and, per dataset, the TDR data
project and snapshot (``azul_manifest.metadata_block``).

**The deployment's datasets are exactly the declared ones.** A dataset the catalog
lists but the deployment does not declare is reported and skipped — dev's
``ANVIL_CMG_Sample_1`` — and a declared one the catalog no longer lists is rebuilt
from the manifests on disk, or refused if there are none. On ``azul-compact`` the
snapshot the manifest names on every row is checked against the declaration, and a
disagreement refuses the run naming both (decision of 2026-09-22 on #500): the
declaration says what the deployment reads, and the fix is to update it.

A manifest already on disk is not re-requested unless ``--force`` is given, or
any manifest the input source needs for that dataset is missing or recorded in the
sidecar with another row count than the dataset's stored file count — a dataset is
fetched whole, so its manifests share one count. That includes a manifest of the
dataset's own last pull that failed parity: the sidecar records its rows before
parity is judged, so the next run requests the dataset again rather than failing
on the same file. The input file is rebuilt from every declared dataset either way — ``--datasets`` narrows
what is fetched, never what the input file covers, so a targeted repair cannot shrink
the corpus. Discovery decides what to fetch; parity is judged against the sidecar's
stored counts, so a catalog that has moved on since the pull — or been deleted, as
anvil14 was — still rebuilds, and the live count is reported beside the stored one
when the two differ. A parity mismatch exits non-zero and leaves the input files
untouched. A rate-limit or gateway error is waited out, honoring the server's
``Retry-After``, for up to ``--max-wait`` seconds per request (see
``azul_manifest._request``); ``--pause`` seconds separate consecutive jobs.

Usage:
    python scripts/download_anvil_manifest.py
    python scripts/download_anvil_manifest.py --deployment dev --input-source azul-verbatim
    python scripts/download_anvil_manifest.py --deployment dev --input-source tdr-direct
    python scripts/download_anvil_manifest.py --datasets AnVIL_ENCORE_293T --force
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import requests

from meta_disco import tdr
from meta_disco.azul_manifest import (
    DEFAULT_MAX_WAIT,
    FORMAT_COMPACT,
    FORMAT_VERBATIM,
    FORMATS,
    INPUT_SOURCE_AZUL_COMPACT,
    INPUT_SOURCE_AZUL_VERBATIM,
    INPUT_SOURCE_TDR_DIRECT,
    INPUT_SOURCES,
    VERBATIM_FILE,
    Dataset,
    HttpSession,
    Sleep,
    count_rows,
    dataset_entry,
    dataset_source,
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
from meta_disco.deployments import DEFAULT_DEPLOYMENT, DEPLOYMENTS, Deployment
from meta_disco.snapshot_input import AzulVerbatim, TdrDirect, derive_records

#: Which manifests each Azul kind fetches. ``tdr-direct`` fetches none and is not here.
MANIFEST_FORMATS = {INPUT_SOURCE_AZUL_COMPACT: FORMATS, INPUT_SOURCE_AZUL_VERBATIM: (FORMAT_VERBATIM,)}


def _compact_records(dep: Deployment, datasets: list[Dataset]) -> Iterator[dict[str, Any]]:
    for dataset in datasets:
        yield from iter_compact_records(manifest_path(dep.input_root, dep.catalog, dataset.title, FORMAT_COMPACT))


def _verbatim_records(dep: Deployment, datasets: list[Dataset]) -> Iterator[dict[str, Any]]:
    for dataset in datasets:
        path = manifest_path(dep.input_root, dep.catalog, dataset.title, FORMAT_VERBATIM)
        yield from derive_records(AzulVerbatim(path), dataset.title)


#: How each Azul kind derives its records from the manifests on disk.
RECORDS = {INPUT_SOURCE_AZUL_COMPACT: _compact_records, INPUT_SOURCE_AZUL_VERBATIM: _verbatim_records}


def download(
    dep: Deployment,
    input_source: str,
    only: set[str] | None,
    force: bool,
    pause: float = 5.0,
    max_wait: float = DEFAULT_MAX_WAIT,
    session: HttpSession | None = None,
    sleep: Sleep = time.sleep,
) -> int:
    """Fetch the deployment's manifests for an Azul ``input_source`` and derive its input.
    Returns the process exit code. ``tdr-direct`` fetches nothing and is
    :func:`derive_direct`'s; asking for it here is refused before any request."""
    if input_source not in MANIFEST_FORMATS:
        print(f"{input_source!r} is not an input source that downloads manifests", file=sys.stderr)
        return 2
    formats = MANIFEST_FORMATS[input_source]
    http: HttpSession = session if session is not None else requests.Session()
    root, catalog = dep.input_root, dep.catalog
    root.mkdir(parents=True, exist_ok=True)
    sidecar = load_sidecar(root, catalog)
    stored = sidecar["datasets"]

    log = lambda m: print(f"\n    {m}", end="", flush=True)  # noqa: E731
    try:
        live = {d.title: d for d in discover_datasets(dep.service, catalog, http, sleep, max_wait, log)}
    except (requests.RequestException, RuntimeError) as exc:
        if not stored:
            print(f"Discovery failed ({exc}) and nothing is on disk for {catalog}; nothing to do", file=sys.stderr)
            return 1
        # The catalog is gone or unreachable, but its manifests are here. Nothing
        # can be re-fetched, so --force has nothing to force.
        forced = "; --force has no effect without the catalog" if force else ""
        print(
            f"Discovery failed ({exc}); rebuilding from the {len(stored)} dataset(s) on disk{forced}", file=sys.stderr
        )
        live = {}
    # The input file covers the deployment's declared datasets, in the catalog's order
    # (largest first, as `discover_datasets` sorts) with any the catalog no longer lists
    # after them — the order the records are written in. A catalog dataset the
    # deployment does not declare is not part of it: reported, never fetched.
    declared = set(dep.snapshots)
    undeclared = sorted(t for t in live if t not in declared)
    if undeclared:
        skipped = ", ".join(f"{t} ({live[t].file_count:,} files)" for t in undeclared)
        print(f"Not declared by the {dep.name} deployment, skipped: {skipped}")
    titles = [t for t in live if t in declared] + [t for t in dep.snapshots if t not in live]
    fetch = set(live) & declared
    if only:
        unknown = only - declared
        if unknown:
            print(f"Not declared by the {dep.name} deployment: {sorted(unknown)}", file=sys.stderr)
            return 1
        fetch &= only
    accessible = f", {sum(live[t].file_count for t in titles if t in live):,} accessible files" if live else ""
    print(f"{dep.name} ({catalog}, {input_source}): {len(titles)} dataset(s){accessible}")

    datasets: list[Dataset] = []
    counts: dict[tuple[str, str], int] = {}
    for title in titles:
        try:
            manifest_path(root, catalog, title, FORMAT_COMPACT)
        except ValueError as exc:
            print(f"Refusing dataset title: {exc}", file=sys.stderr)
            return 1
        entry = stored.setdefault(title, {})
        on_disk = all(manifest_path(root, catalog, title, fmt).is_file() for fmt in formats)
        # A dataset is fetched whole: when any manifest this source needs is missing, or
        # the sidecar records one as holding another row count than the dataset's stored
        # file count, every one is requested again, so they are all counted under the one
        # file count stored below. The sidecar is shared by the two Azul kinds, so a pull
        # of one kind can leave the other's manifest counted under an earlier count (a
        # verbatim manifest pulled before a compact run, or a compact one left behind by
        # an `azul-verbatim --force` pull); without this it would fail parity on every
        # run until --force.
        stale = any((entry.get(fmt) or {}).get("rows") not in (None, entry.get("file_count")) for fmt in formats)
        refetch = title in fetch and (force or not on_disk or stale)
        if on_disk and not refetch and "file_count" in entry:
            # Parity is judged against the count the manifests were requested under.
            if title in live and live[title].file_count != entry["file_count"]:
                print(f"  {title}: catalog now says {live[title].file_count:,} files, stored {entry['file_count']:,}")
        elif title in live:
            entry["file_count"] = live[title].file_count
        if "file_count" not in entry:
            # Neither a stored count nor a live one: a declared dataset never pulled (or
            # pulled only partway) that the catalog does not list, or could not be asked
            # about because discovery failed.
            print(
                f"  {title}: no manifests on disk, and the catalog does not list it or could not be reached",
                file=sys.stderr,
            )
            return 1
        dataset = Dataset(title, entry["file_count"])
        datasets.append(dataset)
        for fmt in formats:
            path = manifest_path(root, catalog, title, fmt)
            if path.is_file() and not refetch:
                print(f"  {title} {fmt}: on disk, {path.stat().st_size:,} bytes")
            elif not refetch:
                continue  # missing and not being fetched: parity reports it
            else:
                started = datetime.now()
                print(f"  {title} {fmt}: requesting ...", end="", flush=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                size = fetch_manifest(dep.service, catalog, fmt, title, path, http, sleep, max_wait=max_wait, log=log)
                elapsed = (datetime.now() - started).total_seconds()
                print(f" {size:,} bytes in {elapsed:.0f}s")
                entry[fmt] = {"requested_at": started.isoformat(), "bytes": size, "seconds": round(elapsed)}
                # A courtesy gap between consecutive jobs; the endpoint has a quota.
                sleep(pause)
            rows = count_rows(fmt, path)
            counts[(title, fmt)] = rows
            entry.setdefault(fmt, {})["rows"] = rows
            save_sidecar(root, catalog, sidecar)

    problems = parity_problems(datasets, counts, formats)
    if problems:
        print("Row counts disagree with the catalog; input file not written:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        return 1

    # The TDR snapshot each dataset was materialised from (#434): the deployment's
    # declaration, which a compact manifest must agree with. Read here rather than
    # during the record stream because the envelope is written before the records, so
    # it has to be known first — and read in full rather than off the first row,
    # because `dataset_source` refuses a manifest naming two snapshots instead of
    # picking one. That is a second full parse of every compact manifest, measured at
    # ~2.7s for the largest (309,979 rows) and a few seconds more across the corpus. No
    # network — the manifests are on disk — but not free either, and the refusal is
    # what it buys. A verbatim manifest carries no snapshot column, so the verbatim
    # kind takes the declaration on its own.
    entries: dict[str, dict[str, Any]] = {}
    for dataset in datasets:
        snapshot = dep.snapshots[dataset.title]
        source_id = None
        if input_source == INPUT_SOURCE_AZUL_COMPACT:
            try:
                source_id, spec = dataset_source(manifest_path(root, catalog, dataset.title, FORMAT_COMPACT)) or (
                    None,
                    None,
                )
                named = tdr.Snapshot.from_source_spec(spec) if spec else None
            except ValueError as exc:
                # Reported the way every other failure here is — to stderr with a non-zero
                # exit — rather than as a traceback. The input file is not written either
                # way, since `write_input_files` is below this.
                #
                # The heading says "reading", not "naming the snapshot", because this also
                # catches `iter_compact_manifest_rows` refusing a short or surplus row: a
                # manifest truncated mid-download fails here now rather than later in the
                # record stream, and blaming that on the snapshot columns would misdirect.
                print(f"Cannot read {dataset.title}'s compact manifest:\n  {exc}", file=sys.stderr)
                return 1
            if named is None:
                # Azul writes the snapshot on every compact row, so a manifest naming none is
                # not a dataset without one; the declaration cannot be checked, and writing it
                # would record it as confirmed (decision of 2026-09-22 on #500: refuse).
                print(
                    f"{dataset.title}: the compact manifest names no snapshot, so the {dep.name} "
                    f"deployment's declared {snapshot.source_spec} cannot be checked. Input file not written.",
                    file=sys.stderr,
                )
                return 1
            if named != snapshot:
                print(
                    f"{dataset.title}: the compact manifest names snapshot {named.source_spec}, but the "
                    f"{dep.name} deployment declares {snapshot.source_spec}. The catalog has moved to "
                    f"another snapshot; update the declaration in meta_disco.deployments if that is "
                    f"what this deployment should now read. Input file not written.",
                    file=sys.stderr,
                )
                return 1
        entries[dataset.title] = dataset_entry(dataset.file_count, snapshot, source_id)

    block = metadata_block(dep, entries, datetime.now(), input_source)
    try:
        n = write_input_files(root, block, RECORDS[input_source](dep, datasets))
    except ValueError as exc:
        print(
            f"Cannot derive the input from the {input_source} manifests; input file not written:\n  {exc}",
            file=sys.stderr,
        )
        return 1
    print(f"Wrote {n:,} records to {dep.input_file} ({dep.name}, {catalog}, {input_source})")
    return 0


def derive_direct(dep: Deployment, client: tdr.BigQueryClient) -> int:
    """Derive the deployment's input from its declared snapshots, read in place through
    ``client``. Every snapshot is opened — its tables listed and checked, its dataset
    row read and checked against the declared title, its ``anvil_file`` table counted —
    before any is streamed or anything written, so a snapshot without the tables the
    derivation needs, or one holding another dataset, refuses the run with a one-line
    message and nothing written. A snapshot this identity cannot read fails at the same
    point, before anything is written, but with the client library's own exception and
    traceback: this script does not import that library to catch its errors. Returns
    the process exit code."""
    streams: list[Iterator[dict[str, Any]]] = []
    entries: dict[str, dict[str, Any]] = {}
    try:
        for title, snapshot in dep.snapshots.items():
            reader = TdrDirect(client, snapshot)
            streams.append(derive_records(reader, title))
            # `derive_records` opened the file stream at the call, which counted the
            # table; the envelope is written before the records, so it takes that count,
            # which the stream is then checked against.
            entries[title] = dataset_entry(reader.counts[VERBATIM_FILE], snapshot)
        dep.input_root.mkdir(parents=True, exist_ok=True)
        block = metadata_block(dep, entries, datetime.now(), INPUT_SOURCE_TDR_DIRECT)
        n = write_input_files(dep.input_root, block, (record for stream in streams for record in stream))
    except (ValueError, tdr.RowCountMismatch) as exc:
        print(
            f"Cannot derive the {dep.name} input from its snapshots; input file not written:\n  {exc}", file=sys.stderr
        )
        return 1
    print(
        f"Wrote {n:,} records to {dep.input_file} ({dep.name}, {INPUT_SOURCE_TDR_DIRECT}, {len(streams)} snapshot(s))"
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--deployment",
        default=DEFAULT_DEPLOYMENT,
        choices=sorted(DEPLOYMENTS),
        help=f"The AnVIL deployment to derive the input of (default: {DEFAULT_DEPLOYMENT})",
    )
    parser.add_argument(
        "--input-source",
        default=INPUT_SOURCE_AZUL_COMPACT,
        choices=sorted(INPUT_SOURCES),
        help=f"How the records are derived (default: {INPUT_SOURCE_AZUL_COMPACT})",
    )
    parser.add_argument(
        "--datasets", nargs="+", help="Only fetch these dataset titles (default: every dataset the deployment declares)"
    )
    parser.add_argument("--force", action="store_true", help="Re-request manifests already on disk")
    parser.add_argument("--pause", type=float, default=5.0, help="Seconds to wait between manifest jobs (default 5)")
    parser.add_argument(
        "--max-wait",
        type=float,
        default=DEFAULT_MAX_WAIT,
        help=f"Seconds one request may spend waiting out a rate limit before failing (default {DEFAULT_MAX_WAIT:.0f})",
    )
    # Parse, refuse an unknown name, and exit: the Makefile runs this without the `tdr`
    # extra before `uv run --extra tdr`, so a bad name fails before that extra is synced.
    parser.add_argument("--check-args", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--billing-project",
        default=None,
        help="tdr-direct only: where query jobs run and are billed (default: the environment's own)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.check_args:
        return 0
    dep = DEPLOYMENTS[args.deployment]
    if args.input_source == INPUT_SOURCE_TDR_DIRECT:
        if args.datasets or args.force:
            # There is nothing on disk to narrow to or to re-request: every declared
            # snapshot is read on every run.
            print("--datasets and --force have no meaning for tdr-direct, which fetches nothing", file=sys.stderr)
            return 2
        return derive_direct(dep, tdr.default_client(billing_project=args.billing_project))
    only = set(args.datasets) if args.datasets else None
    return download(dep, args.input_source, only, args.force, args.pause, args.max_wait)


if __name__ == "__main__":
    raise SystemExit(main())
