"""DuckDB timing shared by ``query_parquet.py`` and ``samples.py`` (#663).

Each question is timed two ways:

- **fresh**: a new in-memory DuckDB per run, so nothing is cached in DuckDB (the OS may
  still cache the file locally). The connection, and loading ``httpfs``, happen before the
  timing starts: it is the query's cost with nothing cached, not a whole cold request's.
- **warm**: one DuckDB reused across runs, which may keep the Parquet footer and, over
  HTTP, the bytes already read.

Over HTTP the file is served by :class:`range_server.RangeServer` with a fixed delay per
request (simulated S3), and the requests and bytes of the first fresh run are recorded.

A run longer than :data:`CAP_SECONDS` is interrupted. A question with an interrupted
fresh run is recorded as capped, with the requests and bytes its first run made (by the
cap, where that run was the interrupted one); it is not run again and its answer is not
checked. An interrupted warm run ends the warm runs and is recorded as capped. A question
whose first run takes longer than :data:`REPEAT_UNDER_SECONDS` is not repeated: its one
run is its timing, and it has no warm timing.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
from common import REPEATS, WORK, summarize
from range_server import RangeServer

DELAYS_MS = (20, 80)
CAP_SECONDS = 180
REPEAT_UNDER_SECONDS = 10
PARAMS = {
    "repeats": REPEATS,
    "delays_ms": list(DELAYS_MS),  # a list, as it reads back from the saved JSON
    "cap_seconds": CAP_SECONDS,
    "repeat_under_seconds": REPEAT_UNDER_SECONDS,
}


class Source:
    """Where a mode reads its files: the local path, or a URL on a delaying server."""

    def __init__(self, server: RangeServer | None) -> None:
        self.server = server

    def __call__(self, path: Path) -> str:
        return self.server.url(path) if self.server else str(path)


def modes() -> Iterator[tuple[str, Source]]:
    """``(mode name, source)``: local first, then each simulated-S3 delay, its server running while its turn lasts."""
    yield "local", Source(None)
    for delay in DELAYS_MS:
        with RangeServer(WORK, delay) as server:
            yield f"simulated_s3_{delay}ms", Source(server)


def _connect(remote: bool) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    if remote:
        con.execute("INSTALL httpfs")  # a no-op once installed; a download the first time
        con.execute("LOAD httpfs")
    return con


def _run_capped(con: duckdb.DuckDBPyConnection, sql: str) -> tuple[list[tuple] | None, float]:
    """Run ``sql``; return its rows (None if interrupted at :data:`CAP_SECONDS`) and the wall time in ms."""
    timer = threading.Timer(CAP_SECONDS, con.interrupt)
    timer.start()
    start = time.perf_counter()
    try:
        rows = con.execute(sql).fetchall()
    except duckdb.InterruptException:
        rows = None
    finally:
        timer.cancel()
    return rows, (time.perf_counter() - start) * 1000


def run_once(sql: str, source: Source) -> dict[str, Any]:
    """One fresh run of ``sql``: its time, whether it was capped, and the requests it made over HTTP."""
    server = source.server
    con = _connect(server is not None)
    if server:
        server.stats.reset()
    rows, elapsed = _run_capped(con, sql)
    out: dict[str, Any] = {"ms": round(elapsed, 1), "capped": rows is None}
    if server:
        out.update(requests=server.stats.requests, bytes=server.stats.bytes)
    return out


def measure(sql: str, source: Source, label: str) -> dict[str, Any]:
    """Run ``sql`` fresh and warm; return the rows and both timings (plus requests made, over HTTP).

    If a fresh run is capped, return ``rows`` None and a ``capped`` entry instead of timings.
    """
    server = source.server
    fresh_times = []
    rows: list[tuple] | None = []
    requests = None
    result: dict[str, Any] | None = None
    for i in range(REPEATS):
        con = _connect(server is not None)
        if server and i == 0:
            server.stats.reset()
        rows, elapsed = _run_capped(con, sql)
        if server and i == 0:
            requests = {"requests": server.stats.requests, "bytes": server.stats.bytes}
        con.close()
        if rows is None:
            result = {"rows": None, "capped": {"cap_seconds": CAP_SECONDS, "run": i + 1}, "first_fresh_run": requests}
            break
        fresh_times.append(elapsed)
        if i == 0 and elapsed > REPEAT_UNDER_SECONDS * 1000:
            result = {"rows": rows, "fresh": summarize(fresh_times), "warm": None, "first_fresh_run": requests}
            break
    if result is None:
        con = _connect(server is not None)
        warm_times = []
        warm: dict[str, Any] | None = None
        for _ in range(REPEATS):
            warm_rows, elapsed = _run_capped(con, sql)
            if warm_rows is None:
                # Reported as capped even after runs that finished, never as a shorter median.
                warm = {"capped": CAP_SECONDS, "completed_runs": len(warm_times)}
                break
            warm_times.append(elapsed)
        warm = warm or summarize(warm_times)
        result = {"rows": rows, "fresh": summarize(fresh_times), "warm": warm, "first_fresh_run": requests}
    took = f"capped at {CAP_SECONDS} s" if "capped" in result else f"{result['fresh']['median_ms']:,.0f} ms"
    print(f"  {label}: {took} {requests or ''}", file=sys.stderr, flush=True)
    return result
