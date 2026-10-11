"""Write the measurement tables of RESULTS.md from ``results/*.json`` (#663).

Everything above the ``<!-- recommendation -->`` marker is regenerated; the
recommendation below it is written by hand and kept across runs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from common import PROD_INPUT, load

RESULTS_MD = Path(__file__).with_name("RESULTS.md")
MARKER = "<!-- recommendation -->"
# chrX's panel file is named ...phased_panel.v2.vcf.gz, the autosomes' ...phased_panel.vcf.gz.
PANEL = re.compile(r"SNV_INDEL_SV_phased_panel(\.v2)?\.vcf\.gz$")
# S3 Standard, US East, first 50 TB: the list price third-party pricing pages give (2026);
# AWS's own page was not read.
S3_DOLLARS_PER_GB_MONTH = 0.023


def mb(n: float) -> str:
    return f"{n / 1e6:,.1f} MB" if n >= 1e5 else f"{n / 1e3:,.1f} KB"


def gb(n: float) -> str:
    return f"{n / 1e9:,.1f} GB"


def ms(d: dict[str, Any] | float | None) -> str:
    """A median timing; "not repeated" where the question ran once, "> N min" where it was capped."""
    if d is None:
        return "not repeated"
    if isinstance(d, dict) and "capped" in d:
        return f"> {d['capped'] // 60} min"
    value = d["median_ms"] if isinstance(d, dict) else d
    if value >= 10_000:
        return f"{value / 1000:,.0f} s"
    if value >= 10:
        return f"{value:,.0f} ms"
    if value >= 1:
        return f"{value:,.1f} ms"
    return f"{value:,.2f} ms" if value >= 0.005 else "< 0.01 ms"


def fresh(m: dict[str, Any]) -> str:
    if "capped" in m:
        return f"> {m['capped']['cap_seconds'] // 60} min, not interactive"
    return ms(m["fresh"])


def fw(d: dict[str, Any]) -> str:
    """A pgen or bitmap-file timing as "fresh / warm"."""
    return f"{ms(d['fresh'])} / {ms(d['warm'])}"


def with_requests(m: dict[str, Any]) -> str:
    req = m["first_fresh_run"]
    return f"{fresh(m)} ({req['requests']:,} req, {mb(req['bytes'])})" if req else fresh(m)


def panel_sizes() -> dict[str, int]:
    """Each chromosome's panel VCF size, from the prod input."""
    sizes = {}
    with PROD_INPUT.open() as f:
        for line in f:
            r = json.loads(line)
            name = r.get("file_name") or ""
            if PANEL.search(name):
                sizes[name.split(".")[1]] = r["file_size"]
    return sizes


def need(name: str) -> dict[str, Any]:
    data = load(name)
    if data is None:
        raise SystemExit(f"results/{name}.json is missing: run {name.split('_')[0]}'s script first")
    return data


def table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def main() -> None:
    b, q, p, s = need("build_parquet"), need("query_parquet"), need("pgen"), need("samples")
    m = b["machine"]
    g = q["genotypes"]
    bs = q["genotypes_by_sample"]
    bc = q["bcftools_ms"]
    near_ms, far_ms = q["params"]["delays_ms"]
    near, far = f"simulated_s3_{near_ms}ms", f"simulated_s3_{far_ms}ms"
    pgen_bytes = sum(p["bytes"].values())
    sizes = panel_sizes()
    factor = sum(sizes.values()) / sizes["chr22"]
    out = []
    out.append("# Variant-store measurement: results (#663)\n")
    out.append(
        f"Measured on {m['cpu']}, {m['cpu_count']} cores, {m['memory_gb']} GB RAM, local SSD ({m['platform']}); "
        f"{m['bcftools']}, {m['plink2']}, DuckDB {q['duckdb']}. Input: the chr22 1000 Genomes panel "
        "(3,202 samples, SNVs, indels and SVs). Every answer below was checked against "
        "`bcftools ... -i 'GT=\"alt\"'` on the same VCF; "
        f"mismatches: Parquet {len(q['mismatches'])}, pgen {len(p['mismatches'])}, joins {len(s['mismatches'])}.\n"
    )
    out.append(
        "The pgen answers are checked on the carrier set and each carrier's zygosity; the .pgen stores phase "
        "but it was not compared. The bitmap file holds carriers only. pgen and the bitmap file are read from "
        "local disk only (`pgenlib` cannot read over HTTP). Their timings are given as **fresh / warm**: "
        "fresh opens the file (a `PgenReader`, or a mapping of the bitmap file) on every run; warm opens it "
        "once beforehand, as a running server would. Neither includes turning sample indices into names.\n"
    )
    out.append(
        "Latency is the median of "
        f"{q['params']['repeats']} runs. **fresh** = a new DuckDB per run (nothing cached in DuckDB; the OS file cache is "
        "warm after the first run, which cannot be dropped without `sudo purge`); **warm** = one DuckDB reused. "
        "**Simulated S3** is a local HTTP server that delays every request by "
        f"{near_ms} or {far_ms} ms: it models round "
        "trips, not S3's throughput or variance. `req` is the requests and bytes the first fresh run made.\n"
    )

    out.append("## Build\n")
    out.append(
        table(
            ["", "Value"],
            [
                ["Input VCF", mb(b["input_bytes"])],
                ["Parquet (sorted by chrom, pos)", mb(b["output_bytes"])],
                ["Rows (non-reference genotypes)", f"{b['rows']:,}"],
                ["Non-reference genotypes counted by bcftools", f"{b['vcf_non_reference_genotypes']:,}"],
                ["Row count matches", str(b["rows"] == b["vcf_non_reference_genotypes"])],
                ["Variants with a carrier", f"{b['variants_with_a_carrier']:,}"],
                [f"Row groups ({b['row_group_size']:,} rows each)", f"{b['row_groups']:,}"],
                ["Build time (bcftools → DuckDB → Parquet)", f"{b['build_seconds']:,.0f} s"],
                ["Parquet sorted by sample (second copy)", mb(q["by_sample_bytes"])],
                ["Sample-sorted copy build time", f"{q.get('by_sample_build_seconds', 0):,.0f} s"],
                [
                    "pgen (.pgen + .pvar + .psam)",
                    f"{mb(pgen_bytes)} ({mb(p['bytes']['pgen'])} + {mb(p['bytes']['pvar'])} + {mb(p['bytes']['psam'])})",
                ],
                ["pgen build time (plink2 --make-pgen)", f"{p['build_seconds']:,.0f} s"],
                [
                    f"Bitmap file (one {(p['samples'] + 7) // 8}-byte carrier mask per variant, uncompressed)",
                    mb(p["bitmap_bytes"]),
                ],
                ["Bitmap file build time (from the .pgen)", f"{p['bitmap_build_seconds']:,.0f} s"],
            ],
        )
    )
    out.append("")
    out.append(
        "Genotypes in the VCF, tallied by bcftools: "
        + ", ".join(f"`{k}` {v:,}" for k, v in sorted(b["vcf_genotype_histogram"].items()))
        + ".\n"
    )

    out.append("## Which samples carry variant V\n")
    pg = {r["variant"]: r for r in p["carriers"]}
    rows = []
    for r, s20, s80 in zip(g["local"]["carriers"], g[near]["carriers"], g[far]["carriers"], strict=True):
        rows.append(
            [
                f"{r['kind']}, AC {r['ac']:,}",
                f"{r['carriers']:,}",
                ms(bc["carriers"][r["variant"]]),
                fresh(r),
                ms(r.get("warm")),
                with_requests(s20),
                with_requests(s80),
                fw(pg[r["variant"]]["pgen"]),
                fw(pg[r["variant"]]["bitmap_file"]),
            ]
        )
    header = [
        "Variant",
        "Carriers",
        "bcftools (tabix)",
        "Parquet fresh",
        "Parquet warm",
        f"Sim. S3 {near_ms} ms",
        f"Sim. S3 {far_ms} ms",
        "pgen (fresh / warm)",
        "Bitmap file (fresh / warm)",
    ]
    out.append(table(header, rows) + "\n")

    out.append("## Which samples carry all of V1…V50\n")
    pg = {r["set"]: r for r in p["carriers_of_all"]}
    rows = []
    for r, s20, s80 in zip(
        g["local"]["carriers_of_all"], g[near]["carriers_of_all"], g[far]["carriers_of_all"], strict=True
    ):
        rows.append(
            [
                r["set"],
                f"{r['carriers']:,}",
                ms(bc["carriers_of_all"][r["set"]]),
                fresh(r),
                ms(r.get("warm")),
                with_requests(s20),
                with_requests(s80),
                fw(pg[r["set"]]["read_filter"]),
                fw(pg[r["set"]]["masks_at_query"]),
                fw(pg[r["set"]]["bitmap_file"]),
            ]
        )
    header = [
        "Set",
        "Carriers",
        "bcftools (tabix)",
        "Parquet fresh",
        "Parquet warm",
        f"Sim. S3 {near_ms} ms",
        f"Sim. S3 {far_ms} ms",
        "pgen, read + filter (fresh / warm)",
        "pgen, masks at query (fresh / warm)",
        "Bitmap file (fresh / warm)",
    ]
    out.append(table(header, rows) + "\n")

    out.append("## All variants sample X carries\n")
    pg = {r["sample"]: r for r in p["sample"]}
    rows = []
    for r, by_sample, far_pos, far_sample in zip(
        g["local"]["sample"], bs["local"]["sample"], g[far]["sample"], bs[far]["sample"], strict=True
    ):
        rows.append(
            [
                r["sample"],
                f"{r['variants']:,}",
                ms(bc["variants_of"][r["sample"]]),
                fresh(r),
                fresh(by_sample),
                with_requests(far_pos),
                with_requests(far_sample),
                fw(pg[r["sample"]]),
            ]
        )
    header = [
        "Sample",
        "Variants",
        "bcftools (full VCF)",
        "Parquet by pos, fresh",
        "Parquet by sample, fresh",
        f"By pos, sim. S3 {far_ms} ms",
        f"By sample, sim. S3 {far_ms} ms",
        "pgen (fresh / warm)",
    ]
    out.append(table(header, rows) + "\n")

    out.append("## Carriers joined to the sample table\n")
    out.append(
        f"Stand-in sample table: {s['samples']:,} panel samples with pedigree population, and the AnVIL datasets "
        "whose file names carry the sample's id in the prod input ("
        + ", ".join(f"{d} {n:,}" for d, n in sorted(s["samples_by_dataset"].items(), key=lambda x: -x[1]))
        + f"); {mb(s['samples_bytes'])}. RNA-seq = named in AnVIL_MAGE; long reads = named in ANVIL_HPRC or "
        "AnVIL_HPRC_R2.\n"
    )
    rows = [
        [
            j["question"],
            f"{j['carriers']:,} → {j['answer']:,}",
            fresh(j["local"]),
            ms(j["local"].get("warm")),
            with_requests(j[near]),
            with_requests(j[far]),
        ]
        for j in s["joins"]
    ]
    header = [
        "Question",
        "Carriers → answer",
        "Local fresh",
        "Local warm",
        f"Sim. S3 {near_ms} ms",
        f"Sim. S3 {far_ms} ms",
    ]
    out.append(table(header, rows) + "\n")

    bloom = q["with_bloom_filters"]
    without = next(r for r in g[f"simulated_s3_{bloom['delay_ms']}ms"]["carriers"] if r["variant"] == bloom["variant"])
    out.append("## What Bloom filters cost over HTTP\n")
    out.append(
        "The tables above are written without Bloom filters (`WRITE_BLOOM_FILTER false`). The same "
        f"single-variant question, asked of a copy written with DuckDB's default Bloom filters "
        f"({mb(bloom['bytes_on_disk'])} against {mb(b['output_bytes'])}), over simulated S3 at "
        f"{bloom['delay_ms']} ms made **{bloom['requests']:,} requests** ({mb(bloom['bytes'])}) and took "
        f"**{bloom['ms'] / 1000:,.1f} s**, against {without['first_fresh_run']['requests']:,} requests and "
        f"{ms(without['fresh'])} without them. With them, each equality filter on a string column whose "
        "min/max cannot exclude a row group (`chrom` is `chr22` in all of them) reads that row group's Bloom "
        "filter, even where `pos` has already excluded it.\n"
    )

    out.append("## Sample similarity\n")
    out.append(
        f"KING kinship over all {p['samples']:,} samples on chr22 (`plink2 --make-king triangle bin`): "
        f"{p['king_seconds']:,.0f} s, {mb(p['king_bytes'])}.\n"
    )

    out.append("## Genome-wide extrapolation (an extrapolation, not a measurement)\n")
    out.append(
        f"Scaled by the panel VCFs' total size over chr22's, from the prod input: {len(sizes)} chromosome files, "
        f"{gb(sum(sizes.values()))} against {mb(sizes['chr22'])}, a factor of **{factor:.1f}**. This assumes "
        "every chromosome has chr22's genotypes per VCF byte; chrX's haploid male calls make that least true there. "
        f"Storage cost is at S3 Standard's list price, ${S3_DOLLARS_PER_GB_MONTH}/GB-month, storage only.\n"
    )
    rows = []
    for label, n in (
        ("Parquet by pos", b["output_bytes"]),
        ("Parquet by sample", q["by_sample_bytes"]),
        ("pgen", pgen_bytes),
        ("Bitmap file", p["bitmap_bytes"]),
    ):
        rows.append([label, gb(n * factor), f"${n * factor / 1e9 * S3_DOLLARS_PER_GB_MONTH:,.2f}"])
    out.append(table(["Layout", "Projected size", "Per month"], rows))
    out.append("")
    out.append(
        f"Projected rows: {b['rows'] * factor / 1e9:,.1f} billion. Projected build time on this machine, one "
        f"chromosome after another: Parquet {b['build_seconds'] * factor / 60:,.0f} min, pgen "
        f"{p['build_seconds'] * factor / 60:,.0f} min; KING {p['king_seconds'] * factor / 60:,.0f} min if it "
        "scales with variant count.\n"
    )

    previous = RESULTS_MD.read_text() if RESULTS_MD.exists() else ""
    recommendation = previous.split(MARKER, 1)[1] if MARKER in previous else "\n## Recommendation\n\nTo be written.\n"
    RESULTS_MD.write_text("\n".join(out) + "\n" + MARKER + recommendation)
    print(RESULTS_MD)


if __name__ == "__main__":
    main()
