# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb==1.5.5"]
# ///
"""Build the long table of non-reference genotypes from the chr22 panel VCF (#663).

``bcftools query -i 'GT="alt"'`` prints one line per (variant, sample) whose genotype
carries an alternate allele; DuckDB reads that stream from a named pipe and writes it
as Parquet sorted by (chrom, pos). The row count is then checked against an
independent count: every genotype in the VCF tallied by value with no filter
(``bcftools query -f '[%GT\\n]'``), less those that are ``0|0``. That equals the
non-reference count only where no genotype is unphased or missing (``0/0``, ``.``); the
chr22 panel's tally holds ``0|0``, ``0|1``, ``1|0`` and ``1|1`` alone.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import duckdb
from common import GENOTYPES, PARQUET_OPTIONS, ROW_GROUP_SIZE, VCF, WORK, cached_lines, machine, save, size

QUERY_FORMAT = r"[%CHROM\t%POS\t%REF\t%ALT\t%SAMPLE\t%GT\n]"


def build() -> float:
    """Write :data:`GENOTYPES` from the VCF; return the wall time in seconds.

    The table is written beside it and renamed into place only once bcftools has exited
    cleanly, so a failed run leaves the previous table as it was.
    """
    start = time.perf_counter()
    part = GENOTYPES.with_suffix(".parquet.part")
    with tempfile.TemporaryDirectory() as tmp:
        fifo = Path(tmp) / "genotypes.tsv"
        os.mkfifo(fifo)
        proc = subprocess.Popen(
            f"bcftools query -i 'GT=\"alt\"' -f '{QUERY_FORMAT}' {VCF} > {fifo}",
            shell=True,
        )
        con = duckdb.connect()
        con.execute(f"""
            COPY (
                SELECT chrom || ':' || pos || ':' || ref || ':' || alt AS variant_id,
                       chrom, pos, ref, alt, sample, genotype
                FROM read_csv('{fifo}', delim='\t', header=false, quote='', escape='',
                              auto_detect=false,
                              columns={{'chrom': 'VARCHAR', 'pos': 'INTEGER', 'ref': 'VARCHAR',
                                        'alt': 'VARCHAR', 'sample': 'VARCHAR', 'genotype': 'VARCHAR'}})
                ORDER BY chrom, pos, ref, alt, sample
            ) TO '{part}' ({PARQUET_OPTIONS})
        """)
        if proc.wait() != 0:
            part.unlink(missing_ok=True)
            sys.exit(f"bcftools query exited {proc.returncode}")
    part.rename(GENOTYPES)
    return time.perf_counter() - start


def genotype_histogram() -> dict[str, int]:
    """Every genotype in the VCF tallied by value, cached in ``gt_histogram.tsv``."""
    rows = cached_lines(
        WORK / "gt_histogram.tsv",
        f"bcftools query -f '[%GT\\n]' {VCF} 2>/dev/null"
        f" | LC_ALL=C awk '{{c[$1]++}} END{{for(k in c) print k\"\\t\"c[k]}}'",
    )
    return {gt: int(n) for gt, n in rows}


def main() -> None:
    seconds = build()
    con = duckdb.connect()
    rows, variants, samples = con.execute(
        f"SELECT count(*), count(DISTINCT variant_id), count(DISTINCT sample) FROM '{GENOTYPES}'"
    ).fetchone()
    row_groups = con.execute(f"SELECT count(DISTINCT row_group_id) FROM parquet_metadata('{GENOTYPES}')").fetchone()[0]
    by_genotype = dict(con.execute(f"SELECT genotype, count(*) FROM '{GENOTYPES}' GROUP BY 1").fetchall())

    histogram = genotype_histogram()
    non_reference = sum(n for gt, n in histogram.items() if gt != "0|0")
    result = {
        "machine": machine(),
        "duckdb": duckdb.__version__,
        "input_bytes": size(VCF),
        "output_bytes": size(GENOTYPES),
        "build_seconds": round(seconds, 1),
        "row_group_size": ROW_GROUP_SIZE,
        "row_groups": row_groups,
        "rows": rows,
        "variants_with_a_carrier": variants,
        "samples_with_a_genotype": samples,
        "rows_by_genotype": by_genotype,
        "vcf_genotype_histogram": histogram,
        "vcf_non_reference_genotypes": non_reference,
    }
    print(save("build_parquet", result))
    if rows != non_reference:
        sys.exit(f"row count {rows} != non-reference genotypes {non_reference}")


if __name__ == "__main__":
    main()
