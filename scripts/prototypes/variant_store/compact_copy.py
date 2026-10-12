# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb==1.5.5"]
# ///
"""Build and time a compact sample-sorted copy: integer variant numbers, strings in a lookup (#663).

The sample-sorted copy ``query_parquet.py`` builds keeps each row's variant strings
(``variant_id``, ``chrom``, ``ref``, ``alt``), which compress well sorted by position and
poorly sorted by sample. This copy holds only ``sample``, an integer ``variant`` and
``genotype``, beside a lookup table from that number to the variant's strings. It is timed
locally on the sample-keyed question, answered through the lookup, and checked against
bcftools.
"""

from __future__ import annotations

import time
from typing import Any

import duckdb
import truth
from common import GENOTYPES, PARQUET_OPTIONS, WORK, Checker, machine, save, size
from duck import Source, measure

COMPACT = WORK / "genotypes_by_sample_compact.parquet"
VARIANTS = WORK / "variants.parquet"


def build() -> float:
    """Write :data:`VARIANTS` and :data:`COMPACT` from :data:`GENOTYPES`; return the seconds it took."""
    start = time.perf_counter()
    con = duckdb.connect()
    # One number per distinct variant id; the two symbolic SVs that share an id share a number,
    # as they share a variant_id in the table.
    con.execute(f"""
        CREATE TABLE variants AS
        SELECT row_number() OVER (ORDER BY chrom, pos, ref, alt)::INTEGER AS variant, chrom, pos, ref, alt, variant_id
        FROM (SELECT DISTINCT chrom, pos, ref, alt, variant_id FROM read_parquet('{GENOTYPES}'))
    """)
    con.execute(f"COPY variants TO '{VARIANTS}' ({PARQUET_OPTIONS})")
    con.execute(f"""
        COPY (
            SELECT g.sample, v.variant, g.genotype
            FROM read_parquet('{GENOTYPES}') g JOIN variants v USING (chrom, pos, ref, alt)
            ORDER BY g.sample, v.variant
        ) TO '{COMPACT}' ({PARQUET_OPTIONS})
    """)
    return time.perf_counter() - start


def main() -> None:
    seconds = build()
    answers = truth.answers()
    _, _, samples = truth.questions()
    check = Checker()
    rows = duckdb.connect().execute(f"SELECT count(*) FROM read_parquet('{COMPACT}')").fetchone()
    result: dict[str, Any] = {
        "machine": machine(),
        "duckdb": duckdb.__version__,
        "build_seconds": round(seconds, 1),
        "compact_bytes": size(COMPACT),
        "variants_bytes": size(VARIANTS),
        "rows": rows[0] if rows else None,
        "sample": [],
    }
    for sample in samples:
        sql = (
            f"SELECT v.variant_id, g.genotype FROM read_parquet('{COMPACT}') g "
            f"JOIN read_parquet('{VARIANTS}') v USING (variant) WHERE g.sample = '{sample}'"
        )
        m = measure(sql, Source(None), f"variants of {sample} (compact)")
        if (got := m.pop("rows")) is not None:
            check(f"variants of {sample} (compact)", sorted(got), answers.variants_of[sample])
        result["sample"].append({"sample": sample, **m})
    result["mismatches"] = check.mismatches
    print(save("compact_copy", result))
    check.exit_on_mismatch()


if __name__ == "__main__":
    main()
