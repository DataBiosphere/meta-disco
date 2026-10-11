"""Shared paths and helpers for the variant-store measurement prototype (#663).

Nothing here is part of meta_disco; the scripts beside it import it by name, which
works because ``uv run <script>`` puts the script's directory on ``sys.path``. It needs
only the standard library, so every script's environment can import it.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

WORK = Path(os.environ.get("VARIANT_STORE_DIR", "data/prototypes/variant_store"))
VCF = WORK / "chr22.panel.vcf.gz"
PEDIGREE = WORK / "pedigree.txt"
GENOTYPES = WORK / "genotypes.parquet"
GENOTYPES_BY_SAMPLE = WORK / "genotypes_by_sample.parquet"
GENOTYPES_WITH_BLOOM = WORK / "genotypes_with_bloom.parquet"
SAMPLES = WORK / "samples.parquet"
PGEN_PREFIX = WORK / "pgen" / "chr22"
RESULTS = WORK / "results"
PROD_INPUT = Path("data/anvil/prod/anvil_files_metadata.ndjson")
CHROM = "chr22"

# Random choices (which variants and samples are asked about) are drawn from this seed,
# so a rerun asks the same questions.
SEED = 663
REPEATS = 5
ROW_GROUP_SIZE = 122_880  # DuckDB's default, stated so every Parquet copy names the same one
# Every table is written without Bloom filters. With them, an equality filter on a string
# column whose min/max cannot exclude a row group (``chrom`` is ``chr22`` in all of them)
# read that row group's Bloom filter over HTTP, a request per row group per column, even
# where ``pos`` had already excluded it (measured: 10,146 requests against 8 for one variant).
PARQUET_OPTIONS = f"FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE {ROW_GROUP_SIZE}, WRITE_BLOOM_FILTER false"


def save(name: str, data: dict[str, Any]) -> Path:
    """Write one measurement's results to ``results/<name>.json``."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path


def load(name: str) -> dict[str, Any] | None:
    """``results/<name>.json``, or None where it does not exist."""
    path = RESULTS / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def fingerprint(data: Any) -> str:
    """A short hash of ``data``'s JSON, to tell whether saved results were made from the same inputs."""
    return hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


def cached_lines(cache: Path, shell: str) -> list[list[str]]:
    """The tab-separated lines ``shell`` prints, run once and kept in ``cache``.

    ``shell`` runs under ``bash -o pipefail``, so a failed stage of a pipeline fails the
    run and nothing is cached.
    """
    if not cache.exists():
        subprocess.run(["bash", "-o", "pipefail", "-c", f"{shell} > {cache}.part"], check=True)
        Path(f"{cache}.part").rename(cache)
    return [line.split("\t") for line in cache.read_text().splitlines()]


def _first_line(cmd: list[str]) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.splitlines()[0].strip()
    except (OSError, subprocess.CalledProcessError, IndexError):
        return None


def machine() -> dict[str, Any]:
    """The machine a measurement ran on.

    ``memory_gb`` is None where ``sysctl`` cannot be read, and ``cpu`` falls back to
    ``platform.processor()``.
    """
    mem = _first_line(["sysctl", "-n", "hw.memsize"])
    return {
        "platform": platform.platform(),
        "cpu": _first_line(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor(),
        "cpu_count": os.cpu_count(),
        "memory_gb": round(int(mem) / 2**30, 1) if mem else None,
        "disk_free_gb": round(shutil.disk_usage(WORK).free / 2**30, 1),
        "bcftools": _first_line(["bcftools", "--version"]),
        "plink2": _first_line(["plink2", "--version"]),
    }


def time_ms(fn: Callable[[], Any], repeats: int) -> tuple[Any, list[float]]:
    """Run ``fn`` ``repeats`` times; return its last result and each run's wall time in ms."""
    times = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = fn()
        times.append((time.perf_counter() - start) * 1000)
    return result, times


def summarize(times: list[float]) -> dict[str, float]:
    """First run, median and max of a list of ms timings (the first run is the least cached)."""
    return {
        "first_ms": round(times[0], 2),
        "median_ms": round(statistics.median(times), 2),
        "max_ms": round(max(times), 2),
        "runs": len(times),
    }


def size(path: Path) -> int:
    return path.stat().st_size


def stale(output: Path, source: Path) -> bool:
    """True where ``output`` is missing or older than the ``source`` it is made from."""
    return not output.exists() or output.stat().st_mtime < source.stat().st_mtime


class Checker:
    """Compares each layout's answer with bcftools's, keeping the labels of those that differ."""

    def __init__(self, mismatches: list[str] | None = None) -> None:
        self.mismatches = list(mismatches or [])

    def __call__(self, label: str, got: Any, want: Any) -> None:
        if got != want:
            self.mismatches.append(label)
            print(f"MISMATCH {label}", file=sys.stderr, flush=True)

    def exit_on_mismatch(self) -> None:
        if self.mismatches:
            sys.exit(f"{len(self.mismatches)} answers differ from bcftools: {self.mismatches}")
