# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb==1.5.5"]
# ///
"""Time the carrier and sample questions on the Parquet table, locally and through simulated S3 (#663).

Every answer is checked against bcftools (:mod:`truth`); how each question is timed,
capped and repeated is :mod:`duck`'s. The sample-keyed question is then asked of a
second copy sorted by sample.

A variant is asked for by ``chrom``, ``pos``, ``ref`` and ``alt``, the issue's key; ``pos``
prunes row groups by their min/max. The tables are written without Bloom filters
(:data:`common.PARQUET_OPTIONS` says why); one run of the same question against a copy
written with them is recorded (``with_bloom_filters``) to show what they cost over HTTP.

Results are saved after each table and mode; a rerun skips the modes already saved, unless
the saved file was made with other parameters or questions, when it starts afresh.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

import duckdb
import truth
from common import (
    CHROM,
    GENOTYPES,
    GENOTYPES_BY_SAMPLE,
    GENOTYPES_WITH_BLOOM,
    PARQUET_OPTIONS,
    RESULTS,
    ROW_GROUP_SIZE,
    WORK,
    Checker,
    fingerprint,
    load,
    machine,
    save,
    size,
    stale,
)
from duck import DELAYS_MS, PARAMS, Source, measure, modes, run_once
from range_server import RangeServer

# Bumped when the queries change, so a rerun does not resume from answers to other queries.
QUERIES = 2


def carriers_sql(src: str, v: truth.Variant) -> str:
    return (
        f"SELECT sample, genotype FROM read_parquet('{src}') "
        f"WHERE chrom = '{CHROM}' AND pos = {v.pos} AND ref = '{v.ref}' AND alt = '{v.alt}'"
    )


def carriers_of_all_sql(src: str, vs: list[truth.Variant]) -> str:
    positions = ", ".join(str(v.pos) for v in vs)
    ids = ", ".join(f"'{v.id}'" for v in vs)
    return (
        f"SELECT sample FROM read_parquet('{src}') "
        f"WHERE chrom = '{CHROM}' AND pos IN ({positions}) AND variant_id IN ({ids}) "
        f"GROUP BY sample HAVING count(*) = {len(vs)}"
    )


def sample_sql(src: str, sample: str) -> str:
    return f"SELECT variant_id, genotype FROM read_parquet('{src}') WHERE sample = '{sample}'"


def run_questions(table: Path, source: Source, answers: truth.Answers, check: Checker, variant_keyed: bool) -> dict:
    """Ask the sample-keyed questions of ``table``, and the variant-keyed ones too where ``variant_keyed``."""
    singles, sets, samples = truth.questions()
    src = source(table)
    out: dict[str, Any] = {"carriers": [], "carriers_of_all": [], "sample": []}
    for v in singles if variant_keyed else []:
        want = answers.carriers[v.id]
        m = measure(carriers_sql(src, v), source, f"carriers {v.id}")
        if (rows := m.pop("rows")) is not None:
            check(f"carriers {v.id}", dict(rows), want)
        out["carriers"].append({"variant": v.id, "kind": v.kind, "ac": v.ac, "carriers": len(want), **m})
    for name, vs in sets.items() if variant_keyed else []:
        want_set = answers.carriers_of_all[name]
        m = measure(carriers_of_all_sql(src, vs), source, f"carriers of all: {name}")
        if (rows := m.pop("rows")) is not None:
            check(f"carriers of all: {name}", {r[0] for r in rows}, want_set)
        out["carriers_of_all"].append({"set": name, "carriers": len(want_set), **m})
    for sample in samples:
        want = answers.variants_of[sample]
        m = measure(sample_sql(src, sample), source, f"variants of {sample}")
        if (rows := m.pop("rows")) is not None:
            check(f"variants of {sample}", sorted(rows), want)
        out["sample"].append({"sample": sample, "variants": len(want), **m})
    return out


def build_by_sample() -> float:
    start = time.perf_counter()
    duckdb.connect().execute(f"""
        COPY (SELECT * FROM read_parquet('{GENOTYPES}') ORDER BY sample, chrom, pos, ref, alt)
        TO '{GENOTYPES_BY_SAMPLE}' ({PARQUET_OPTIONS})
    """)
    return time.perf_counter() - start


def build_with_bloom() -> None:
    """A copy of :data:`GENOTYPES` written with DuckDB's default Bloom filters, to measure what they cost."""
    duckdb.connect().execute(f"""
        COPY (SELECT * FROM read_parquet('{GENOTYPES}'))
        TO '{GENOTYPES_WITH_BLOOM}' (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE {ROW_GROUP_SIZE})
    """)


def main() -> None:
    answers = truth.answers()
    params = {**PARAMS, "questions": fingerprint(load("questions")), "queries": QUERIES}
    saved: dict[str, Any] = load("query_parquet") or {}
    result: dict[str, Any] = saved
    if saved.get("params") != params:
        # Start afresh, keeping only the sample-sorted copy's build time (the copy is kept too,
        # unless it is older than the table it is sorted from).
        build = (
            {"by_sample_build_seconds": saved["by_sample_build_seconds"]} if "by_sample_build_seconds" in saved else {}
        )
        result = {"machine": machine(), "duckdb": duckdb.__version__, "params": params, **build}
    check = Checker(result.get("mismatches"))
    result["bcftools_ms"] = answers.bcftools_ms
    if stale(GENOTYPES_BY_SAMPLE, GENOTYPES):
        result["by_sample_build_seconds"] = round(build_by_sample(), 1)
    result["by_sample_bytes"] = size(GENOTYPES_BY_SAMPLE)
    save("query_parquet", result)

    # The sample-sorted copy is built for the sample-keyed question only, so only it is asked there.
    for table, variant_keyed in ((GENOTYPES, True), (GENOTYPES_BY_SAMPLE, False)):
        done = result.setdefault(table.stem, {})
        for mode, source in modes():
            if mode in done:
                continue
            print(f"{table.stem} {mode}", file=sys.stderr, flush=True)
            done[mode] = run_questions(table, source, answers, check, variant_keyed)
            result["mismatches"] = check.mismatches
            save("query_parquet", result)

    if "with_bloom_filters" not in result:
        if stale(GENOTYPES_WITH_BLOOM, GENOTYPES):
            build_with_bloom()
        v = truth.questions()[0][0]
        with RangeServer(WORK, DELAYS_MS[0]) as server:
            source = Source(server)
            run = run_once(carriers_sql(source(GENOTYPES_WITH_BLOOM), v), source)
        result["with_bloom_filters"] = {
            "variant": v.id,
            "delay_ms": DELAYS_MS[0],
            "bytes_on_disk": size(GENOTYPES_WITH_BLOOM),
            **run,
        }
        save("query_parquet", result)
    print(RESULTS / "query_parquet.json")
    check.exit_on_mismatch()


if __name__ == "__main__":
    main()
