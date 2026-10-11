"""A local HTTP server that answers Range requests after a fixed delay (#663).

It stands in for S3: every request (HEAD or GET) waits ``delay_ms`` before it is
answered, which simulates one round trip to object storage. Timings taken through it
are **simulated**, not S3's: they model latency per request, not S3's throughput or
its variance. It counts requests and bytes served so a measurement can say how many
round trips a query made.
"""

from __future__ import annotations

import re
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_RANGE = re.compile(r"bytes=(\d+)-(\d*)")


class Stats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.requests = 0
        self.bytes = 0

    def reset(self) -> None:
        with self.lock:
            self.requests = 0
            self.bytes = 0

    def add(self, n: int) -> None:
        with self.lock:
            self.requests += 1
            self.bytes += n


class _Server(ThreadingHTTPServer):
    # DuckDB opens several connections at once; the default backlog of 5 refused some of
    # them when every request opened a new one (HTTP/1.0). Kept as a margin.
    request_queue_size = 128


class RangeServer:
    """Serve ``root`` on 127.0.0.1 from a background thread; ``url(path)`` names a file."""

    def __init__(self, root: Path, delay_ms: float) -> None:
        self.stats = Stats()
        self.delay = delay_ms / 1000
        server = self

        class Handler(SimpleHTTPRequestHandler):
            # Keep connections open between requests, as S3 clients do; the handler's
            # default, HTTP/1.0, closes the connection after every response.
            protocol_version = "HTTP/1.1"

            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(root), **kwargs)

            def log_message(self, format, *args):
                pass

            def do_HEAD(self):
                time.sleep(server.delay)
                path = Path(self.translate_path(self.path))
                self.send_response(200)
                self.send_header("Content-Length", str(path.stat().st_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                server.stats.add(0)

            def do_GET(self):
                time.sleep(server.delay)
                path = Path(self.translate_path(self.path))
                total = path.stat().st_size
                match = _RANGE.fullmatch(self.headers.get("Range", ""))
                start, end = 0, total - 1
                if match:
                    start = int(match.group(1))
                    end = min(int(match.group(2)), total - 1) if match.group(2) else total - 1
                length = end - start + 1
                if length <= 0 and match:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{total}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    server.stats.add(0)
                    return
                self.send_response(206 if match else 200)
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                if match:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                self.end_headers()
                with path.open("rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining:
                        chunk = f.read(min(remaining, 1 << 20))
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                server.stats.add(length)

        self.httpd = _Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> RangeServer:
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def url(self, path: Path) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/{path.name}"
