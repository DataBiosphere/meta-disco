# Variant-store measurement: results (#663)

Measured on Apple M1 Max, 10 cores, 64.0 GB RAM, local SSD (macOS-15.6.1-arm64-arm-64bit); bcftools 1.24, PLINK v2.0.0-a.7.11 M1 (1 Oct 2026), DuckDB 1.5.5. Input: the chr22 1000 Genomes panel (3,202 samples, SNVs, indels and SVs). Every answer below was checked against `bcftools ... -i 'GT="alt"'` on the same VCF; mismatches: Parquet 0, pgen 0, joins 0.

The pgen answers are checked on the carrier set and each carrier's zygosity; the .pgen stores phase but it was not compared. The bitmap file holds carriers only. pgen and the bitmap file are read from local disk only (`pgenlib` cannot read over HTTP). Their timings are given as **fresh / warm**: fresh opens the file (a `PgenReader`, or a mapping of the bitmap file) on every run; warm opens it once beforehand, as a running server would. Neither includes turning sample indices into names.

Latency is the median of 5 runs, except where a cell says **1 run**: a question whose first run took over 10 s was not repeated. **fresh** = a new DuckDB per run (nothing cached in DuckDB; the OS file cache is warm after the first run, which cannot be dropped without `sudo purge`); **warm** = one DuckDB reused. **Simulated S3** is a local HTTP server that delays every request by 20 or 80 ms: it models round trips, not S3's throughput or variance. `req` is the requests and bytes the first fresh run made.

## Build

|  | Value |
|---|---|
| Input VCF | 445.7 MB |
| Parquet (sorted by chrom, pos) | 164.0 MB |
| Rows (non-reference genotypes) | 207,523,964 |
| Non-reference genotypes counted by bcftools | 207,523,964 |
| Row count matches | True |
| Variants with a carrier | 1,066,555 |
| Row groups (122,880 rows each) | 1,689 |
| Build time (bcftools → DuckDB → Parquet) | 134 s |
| Parquet sorted by sample (second copy) | 1,911.3 MB |
| Sample-sorted copy build time | 40 s |
| pgen (.pgen + .pvar + .psam) | 170.1 MB (132.6 MB + 37.5 MB + 35.2 KB) |
| pgen build time (plink2 --make-pgen) | 9 s |
| Bitmap file (one 401-byte carrier mask per variant, uncompressed) | 427.7 MB |
| Bitmap file build time (from the .pgen) | 2 s |

Genotypes in the VCF, tallied by bcftools: `0|0` 3,207,591,550, `0|1` 69,137,480, `1|0` 69,177,782, `1|1` 69,208,702.

## Which samples carry variant V

| Variant | Carriers | bcftools (tabix, 1 run) | Parquet fresh | Parquet warm | Sim. S3 20 ms | Sim. S3 80 ms | pgen (fresh / warm) | Bitmap file (fresh / warm) |
|---|---|---|---|---|---|---|---|---|
| SNV, AC 4 | 4 | 12 ms | 18 ms | 20 ms | 240 ms (8 req, 1.4 MB) | 726 ms (8 req, 1.4 MB) | 2.6 ms / 0.01 ms | 0.08 ms / 0.01 ms |
| SNV, AC 64 | 64 | 14 ms | 20 ms | 19 ms | 241 ms (8 req, 1.4 MB) | 734 ms (8 req, 1.4 MB) | 2.6 ms / 0.01 ms | 0.07 ms / 0.01 ms |
| SNV, AC 108 | 107 | 13 ms | 20 ms | 18 ms | 246 ms (8 req, 1.4 MB) | 727 ms (8 req, 1.4 MB) | 2.6 ms / < 0.01 ms | 0.07 ms / 0.01 ms |
| SNV, AC 1,291 | 1,115 | 25 ms | 18 ms | 18 ms | 239 ms (8 req, 1.4 MB) | 756 ms (8 req, 1.4 MB) | 2.6 ms / 0.01 ms | 0.07 ms / 0.01 ms |
| indel, AC 8 | 8 | 19 ms | 18 ms | 18 ms | 240 ms (8 req, 1.4 MB) | 737 ms (8 req, 1.4 MB) | 2.6 ms / < 0.01 ms | 0.07 ms / 0.01 ms |
| indel, AC 21 | 20 | 11 ms | 19 ms | 18 ms | 241 ms (8 req, 1.4 MB) | 752 ms (8 req, 1.4 MB) | 2.6 ms / 0.01 ms | 0.07 ms / 0.01 ms |
| indel, AC 207 | 202 | 10 ms | 18 ms | 18 ms | 246 ms (8 req, 1.4 MB) | 733 ms (8 req, 1.4 MB) | 2.6 ms / 0.01 ms | 0.06 ms / 0.01 ms |
| indel, AC 2,531 | 1,990 | 16 ms | 18 ms | 18 ms | 240 ms (8 req, 1.4 MB) | 730 ms (8 req, 1.4 MB) | 2.6 ms / 0.01 ms | 0.07 ms / 0.01 ms |
| SV, AC 3 | 2 | 17 ms | 20 ms | 19 ms | 246 ms (8 req, 1.4 MB) | 727 ms (8 req, 1.4 MB) | 2.6 ms / < 0.01 ms | 0.06 ms / 0.01 ms |
| SV, AC 12 | 12 | 15 ms | 20 ms | 19 ms | 237 ms (8 req, 1.4 MB) | 719 ms (8 req, 1.4 MB) | 2.8 ms / < 0.01 ms | 0.07 ms / 0.01 ms |
| SV, AC 633 | 585 | 14 ms | 19 ms | 18 ms | 240 ms (8 req, 1.4 MB) | 739 ms (8 req, 1.4 MB) | 2.6 ms / 0.01 ms | 0.06 ms / 0.01 ms |
| SV, AC 1,663 | 1,583 | 17 ms | 19 ms | 18 ms | 245 ms (8 req, 1.4 MB) | 728 ms (8 req, 1.4 MB) | 2.6 ms / 0.01 ms | 0.07 ms / 0.01 ms |

## Which samples carry all of V1…V50

| Set | Carriers | bcftools (tabix, 1 run) | Parquet fresh | Parquet warm | Sim. S3 20 ms | Sim. S3 80 ms | pgen, read + filter (fresh / warm) | pgen, masks at query (fresh / warm) | Bitmap file (fresh / warm) |
|---|---|---|---|---|---|---|---|---|---|
| 50 consecutive common (AF>0.3) variants | 277 | 885 ms | 21 ms | 19 ms | 131 ms (6 req, 1.5 MB) | 387 ms (6 req, 1.5 MB) | 2.8 ms / 0.12 ms | 2.9 ms / 0.09 ms | 0.10 ms / 0.03 ms |
| 50 random variants with AF>0.5 | 6 | 880 ms | 27 ms | 27 ms | 248 ms (51 req, 5.0 MB) | 770 ms (51 req, 5.0 MB) | 2.8 ms / 0.10 ms | 2.9 ms / 0.12 ms | 0.25 ms / 0.03 ms |
| 50 random variants | 0 | 860 ms | 26 ms | 28 ms | 245 ms (52 req, 5.8 MB) | 750 ms (52 req, 5.8 MB) | 2.8 ms / 0.12 ms | 2.8 ms / 0.11 ms | 0.22 ms / 0.02 ms |

## All variants sample X carries

| Sample | Variants | bcftools (full VCF, 1 run) | Parquet by pos, fresh | Parquet by sample, fresh | By pos, sim. S3 80 ms | By sample, sim. S3 80 ms | pgen (fresh / warm) |
|---|---|---|---|---|---|---|---|
| HG01354 | 59,303 | 15 s | 337 ms | 27 ms | 46 s (1 run, 5,060 req, 151.3 MB) | 576 ms (6 req, 2.0 MB) | 141 ms / 137 ms |
| HG01377 | 61,549 | 15 s | 313 ms | 28 ms | 46 s (1 run, 5,056 req, 151.3 MB) | 570 ms (6 req, 2.1 MB) | 145 ms / 137 ms |
| NA10855 | 56,451 | 20 s | 307 ms | 28 ms | 46 s (1 run, 5,050 req, 151.2 MB) | 573 ms (9 req, 2.7 MB) | 141 ms / 138 ms |

## Carriers joined to the sample table

Stand-in sample table: 3,202 panel samples with pedigree population, and the AnVIL datasets whose file names carry the sample's id in the prod input (ANVIL_1000G_high_coverage_2019 3,202, ANVIL_T2T 3,202, ANVIL_T2T_CHRY 3,202, AnVIL_MAGE 477, ANVIL_HPRC 249, AnVIL_HPRC_R2 224, ANVIL_NIA_CARD_Coriell_Cell_Lines_Open 2); 9.8 KB. RNA-seq = named in AnVIL_MAGE; long reads = named in ANVIL_HPRC or AnVIL_HPRC_R2.

| Question | Carriers → answer | Local fresh | Local warm | Sim. S3 20 ms | Sim. S3 80 ms |
|---|---|---|---|---|---|
| carriers of chr22:42705184:A:<DEL> with RNA-seq | 1,583 → 235 | 18 ms | 17 ms | 323 ms (11 req, 1.4 MB) | 1,012 ms (11 req, 1.4 MB) |
| carriers of all of '50 consecutive common (AF>0.3) variants' with long reads | 277 → 26 | 20 ms | 18 ms | 276 ms (13 req, 1.5 MB) | 831 ms (13 req, 1.5 MB) |

## What Bloom filters cost over HTTP

The tables above are written without Bloom filters (`WRITE_BLOOM_FILTER false`). The same single-variant question, asked of a copy written with DuckDB's default Bloom filters (175.1 MB against 164.0 MB), over simulated S3 at 20 ms made **10,146 requests** (2.2 MB) and took **29.7 s**, against 8 requests and 240 ms without them. With them, each equality filter on a string column whose min/max cannot exclude a row group (`chrom` is `chr22` in all of them) reads that row group's Bloom filter, even where `pos` has already excluded it.

## Sample similarity

KING kinship over all 3,202 samples on chr22 (`plink2 --make-king triangle bin`): 8 s, 41.0 MB.

## Genome-wide extrapolation (an extrapolation, not a measurement)

Scaled by the panel VCFs' total size over chr22's, from the prod input: 23 chromosome files, 32.4 GB against 445.7 MB, a factor of **72.8**. This assumes every chromosome has chr22's genotypes per VCF byte; chrX's haploid male calls make that least true there. Storage cost is at S3 Standard's list price, $0.023/GB-month, storage only.

| Layout | Projected size | Per month |
|---|---|---|
| Parquet by pos | 11.9 GB | $0.27 |
| Parquet by sample | 139.1 GB | $3.20 |
| pgen | 12.4 GB | $0.28 |
| Bitmap file | 31.1 GB | $0.72 |

Projected rows: 15.1 billion. Projected build time on this machine, one chromosome after another: Parquet 162 min, pgen 11 min; KING 10 min if it scales with variant count.

<!-- recommendation -->
## Other findings

- **The panel has no singletons**: no site has an allele count below 2, so the questions' AC = 1 bin was empty.
- **`chrom:pos:ref:alt` does not name a variant uniquely.** Two symbolic SVs (`22857056 T <DEL>`, `49951209 G <INS>`) each share pos, ref and alt with another record, which is why 1,066,557 records give 1,066,555 variant ids. A real key needs the VCF's ID (`HGSV_…`) or END for symbolic alleles. The scripts refuse a question about either site, and compare a sample's variants as a list so both records are kept.
- **Bloom filters cost a request per row group over HTTP** (section above). DuckDB writes them by default; this prototype turns them off.
- **Sorting by sample made the copy nearly 12 times larger** (1.91 GB against 164 MB). Sorted by position, a variant's id, ref and alt repeat on consecutive rows and compress away; sorted by sample they do not. I think storing an integer variant number in place of the strings would shrink it a lot, but that was not built or measured.
- **Opening a `.pgen` costs about 2.6 ms; reading from an open one costs about 0.01 ms per variant.** The fresh pgen timings are almost all the open.

## Recommendation

**Build it genome-wide: it is small and cheap.** Extrapolated from chr22 by VCF size (an extrapolation, stated above): about 15 billion rows, about 12 GB of Parquet, about $0.27 a month in S3 storage, and about 2¾ hours to build one chromosome at a time on this laptop (the chromosomes are independent, so it parallelises). That is below the issue's "tens of GB" guess; its 15 billion rows matched.

**Layout: Parquet sorted by (chrom, pos), one file per chromosome, written without Bloom filters, queried with DuckDB.**
- It is the explorer's engine, it reads over HTTP, and it joins to the sample table in the same SQL.
- Asked by the issue's own key (chrom, pos, ref, alt), one variant's carriers took 18–20 ms locally, 237–246 ms at 20 ms per request and 719–756 ms at 80 ms, in 8 requests. Carriers of all of 50 took 131–248 ms and 387–770 ms (6–52 requests). The joins took 276–323 ms and 831 ms–1.0 s.
- Write with `WRITE_BLOOM_FILTER false`. With DuckDB's default Bloom filters the same one-variant question took 10,146 requests and 30 s at 20 ms.
- Key symbolic SVs by their VCF ID.

**pgen is the faster format, but only for a running process.** It is about the same size (170 MB) and builds 15 times faster (9 s against 134 s). With the file open, one variant's carriers take about 0.01 ms and all of 50 about 0.1 ms, against 18–28 ms for Parquet locally; opening it adds about 2.6 ms. But `pgenlib` reads local files only, so serving it means a process kept running next to the data. Revisit it if such a server is built (a Beacon endpoint, say).

**Bitmaps are not worth it.**
- ANDing carrier masks at query time was no faster than read + filter (0.09–0.12 ms against 0.10–0.12 ms with the file open): the AND is not where the time goes.
- A precomputed bitmap file answers all of 50 in 0.02–0.03 ms with the file open, but pgen is already at 0.1 ms there. The file is 2.5 times pgen's size (428 MB; 31 GB genome-wide), holds carriers only, and sits on local disk.

**Sample-keyed questions need a second copy if they must be interactive remotely.**
- On the position-sorted table, "all variants of sample X" took 0.31–0.34 s locally but about 15 s at 20 ms and 46 s at 80 ms per request (single runs, as each took over 10 s): a full scan, about 5,050 requests and 151 MB.
- The sample-sorted copy answered in 27–28 ms locally, about 0.2 s at 20 ms and about 0.57 s at 80 ms (6–9 requests). As built, though, it is nearly 12 times the size (projected 139 GB, about $3.20 a month).
- Build it only if remote sample-keyed questions are wanted, and with an integer variant number in place of the strings (unmeasured). From an open `.pgen` the same question took 137–145 ms locally.

**Precompute sample similarity (KING), not MinHash.** KING over all 3,202 samples took 8 s on chr22, a projected 10 minutes genome-wide. The output is one 41 MB matrix whatever the number of chromosomes. At 3,202 samples an exact kinship matrix is cheap, so an approximation buys nothing.

**What these numbers do not cover:**
- **Real S3.** The two delays were chosen to bracket a short and a long round trip, and the server models latency per request (over kept-alive connections), not S3's throughput or variance.
- **Cold-disk timings.** Local timings after the first run are from the OS file cache.
- **Request pricing.** Cost is storage only.
- **chrX.** Its haploid male calls make the per-byte scaling least sure there.
