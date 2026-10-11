# Variant-store measurement prototype (#663)

A measurement, not a feature. It answers one question: how big and how fast would a
"which samples carry this variant" store be, built from the 1000 Genomes chr22 panel
VCF? Nothing here is served, wired into the explorer, or imported by `meta_disco`. The
numbers and the recommendation are in [RESULTS.md](RESULTS.md).

## What it measures

| Script | Measures |
|---|---|
| `fetch.sh` | Downloads the chr22 panel VCF from the AnVIL S3 mirror (md5-checked), indexes it, downloads the 1000 Genomes pedigree |
| `build_parquet.py` | Builds the long table of non-reference genotypes (`genotypes.parquet`, sorted by chrom and pos); checks its row count against every genotype in the VCF tallied by `bcftools` |
| `query_parquet.py` | Times "carriers of V", "carriers of all of V1…V50" and "all variants of sample X" on the Parquet table, locally and through simulated S3; builds and times a sample-sorted copy |
| `pgen.py` | Builds the PLINK 2 `.pgen` (2 bits per genotype) and a carrier bitmap file (one mask per variant), and times the same questions on both, "carriers of all of 50" three ways; times KING kinship |
| `samples.py` | Builds a stand-in sample table (pedigree + AnVIL datasets named in file names) and times carrier queries joined to it |
| `report.py` | Writes the measurement tables of `RESULTS.md` from `results/*.json` |

Every answer is checked against `bcftools ... -i 'GT="alt"'` on the same VCF
(`truth.py`, which computes the answers once and caches them in `results/truth.json`); a
script exits non-zero on any mismatch. `duck.py` holds the DuckDB timing that
`query_parquet.py` and `samples.py` share. "Simulated S3" is a local HTTP
server (`range_server.py`) that delays every request by a fixed time: it models round
trips, not S3's throughput.

## Run it

From the repository root, with `bcftools` and `plink2` on `PATH`
(`brew install bcftools plink-ng`) and `uv`. Each script declares its own Python
dependencies, so `uv run` installs them in an isolated environment and the project's
environment is untouched. Inputs and outputs go to `data/prototypes/variant_store/`
(ignored by git), or to `$VARIANT_STORE_DIR`.

`samples.py` and `report.py` also read the prod input,
`data/anvil/prod/anvil_files_metadata.ndjson`, which a clean checkout does not have:
`samples.py` matches sample ids in its file names, and `report.py` takes every panel
VCF's size from it for the genome-wide extrapolation. Create it with `make download`
(the repository's own input step) before running them.

```bash
scripts/prototypes/variant_store/fetch.sh
uv run scripts/prototypes/variant_store/build_parquet.py
uv run scripts/prototypes/variant_store/query_parquet.py
uv run scripts/prototypes/variant_store/pgen.py
uv run scripts/prototypes/variant_store/samples.py
uv run scripts/prototypes/variant_store/report.py
```

A DuckDB query is interrupted at 3 minutes and recorded as capped. `query_parquet.py` saves after each table and mode, and a rerun resumes unless the parameters or questions changed; `pgen.py` reuses the builds it finds. `report.py` regenerates everything in `RESULTS.md` above its `<!-- recommendation -->` marker and keeps the hand-written text below it.

`query_parquet.py` and `samples.py` bind a local port and install DuckDB's `httpfs`
extension on first use (a download from extensions.duckdb.org).
