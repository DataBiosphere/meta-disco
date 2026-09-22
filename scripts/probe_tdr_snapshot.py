#!/usr/bin/env python3
"""Probe a TDR snapshot through the BigQuery layer (issue #498): can this
identity read it, and how long does a table take to stream?

Lists the snapshot's tables, counts each with ``COUNT(*)`` (timed), then streams
one table (``anvil_file`` unless ``--table`` says otherwise), reporting its row
count, the elapsed time, and the column names of the first row. No cell value
is printed. The stream is checked against the table's ``COUNT(*)`` by the layer
itself, and a mismatch exits non-zero.

Identity: see :mod:`meta_disco.tdr`. Needs the ``tdr`` extra
(``uv sync --extra tdr``). The result of the live run on
``ANVIL_1000G_2019_Dev`` goes on #478.

Usage:
    python scripts/probe_tdr_snapshot.py --project datarepo-xxxxxxxx --snapshot ANVIL_1000G_2019_Dev
    python scripts/probe_tdr_snapshot.py --project ... --snapshot ... --table anvil_dataset
"""

from __future__ import annotations

import argparse
import sys
import time

from meta_disco.azul_manifest import Log
from meta_disco.tdr import (
    BigQueryClient,
    RowCountMismatch,
    Snapshot,
    count_rows,
    default_client,
    iter_rows,
    list_tables,
)

DEFAULT_TABLE = "anvil_file"


def probe(client: BigQueryClient, snapshot: Snapshot, table: str, log: Log) -> int:
    """Run the probe against ``client``; returns the process exit code."""
    log(f"snapshot {snapshot.dataset}")
    started = time.monotonic()
    tables = list_tables(client, snapshot)
    log(f"{len(tables)} table(s) listed in {time.monotonic() - started:.1f}s")
    if table not in tables:
        log(f"table {table!r} is not in the snapshot; nothing counted or streamed")
        return 1

    counts: dict[str, int] = {}
    for name in tables:
        started = time.monotonic()
        counts[name] = count_rows(client, snapshot, name)
        log(f"  {name}: {counts[name]} row(s), counted in {time.monotonic() - started:.1f}s")

    log(f"streaming {table}")
    started = time.monotonic()
    streamed = 0
    columns: list[str] = []
    try:
        for row in iter_rows(client, snapshot, table, expect=counts[table]):
            if streamed == 0:
                columns = list(row)
            streamed += 1
    except RowCountMismatch as exc:
        log(f"  {exc}")
        return 1
    log(f"  {streamed} row(s) streamed in {time.monotonic() - started:.1f}s")
    log(f"  columns: {', '.join(columns) if columns else '(no row)'}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True, help="the TDR data project holding the snapshot")
    parser.add_argument("--snapshot", required=True, help="the snapshot name (its BigQuery dataset id)")
    parser.add_argument("--table", default=DEFAULT_TABLE, help=f"the table to stream (default: {DEFAULT_TABLE})")
    parser.add_argument(
        "--billing-project",
        default=None,
        help="where query jobs run and are billed; default: the environment's own (inside Terra, the workspace project)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    snapshot = Snapshot(project=args.project, name=args.snapshot)
    client = default_client(billing_project=args.billing_project)
    return probe(client, snapshot, args.table, log=lambda line: print(line, file=sys.stderr))


if __name__ == "__main__":
    sys.exit(main())
