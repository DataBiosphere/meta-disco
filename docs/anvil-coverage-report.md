# AnVIL Classification Coverage Report

Classification run: **2026-03-22 19:57:03**

Source: **758,658** files across **11** open-access datasets on [explore.anvilproject.org](https://explore.anvilproject.org/).
Processed **758,657** files (1 not yet handled by any classifier).

- ANVIL_T2T_CHRY (309,979 files)
- ANVIL_T2T (289,204 files)
- ANVIL_HPRC (67,830 files)
- ANVIL_1000G_high_coverage_2019 (26,016 files)
- ANVIL_GTEx_public_data (25,789 files)
- ANVIL_NIA_CARD_Coriell_Cell_Lines_Open (12,534 files)
- ANVIL_1000G_PRIMED_data_model (11,493 files)
- AnVIL_IGVF_Mouse_R1 (6,784 files)
- AnVIL_ENCORE_RS293 (3,752 files)
- AnVIL_MAGE (3,285 files)
- AnVIL_ENCORE_293T (1,992 files)

**Classified** includes all files with a determined value, including `not_applicable` (e.g., FASTQ files have no reference assembly). **Not classified** means no rule or signal could determine a value.

| Dimension | Classified | Not Classified |
|---|---:|---:|
| **Data Modality** | 689,445 (90.9%) | 69,212 (9.1%) |
| **Data Type** | 722,825 (95.3%) | 35,832 (4.7%) |
| **Reference Assembly** | 596,211 (78.6%) | 162,446 (21.4%) |
| **Platform** | 157,981 (20.8%) | 600,676 (79.2%) |
| **Assay Type** | 141,230 (18.6%) | 617,427 (81.4%) |

---

## Data Modality

| | count | % |
|---|---:|---:|
| **Classified** | 689,445 | 90.9% |
| **Not classified** | 69,212 | 9.1% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .fastq.gz | 23,033 | FASTQ modality cannot be determined from reads alone — could be genomic, transcriptomic, or epigenomic depending on assay |
| .fast5 | 12,394 | No rule determined a value for data_modality |
| .gz | 7,451 | No rule determined a value for data_modality |
| .txt | 4,584 | No rule determined a value for data_modality |
| .hist | 3,870 | No rule determined a value for data_modality |
| .pdf | 3,028 | No rule determined a value for data_modality |
| .bw | 2,520 | No rule determined a value for data_modality |
| .tsv | 1,278 | No rule determined a value for data_modality |
| .tar.gz | 1,155 | No rule determined a value for data_modality |
| .sizes | 1,086 | No rule determined a value for data_modality |
| .tex | 940 | No rule determined a value for data_modality |
| .tdf | 860 | No rule determined a value for data_modality |
| .vst | 672 | No rule determined a value for data_modality |
| .stats | 659 | No rule determined a value for data_modality |
| .qv | 645 | No rule determined a value for data_modality |
| .sf | 634 | No rule determined a value for data_modality |
| .gfa | 598 | No rule determined a value for data_modality |
| .html | 510 | No rule determined a value for data_modality |
| .sam.gz | 474 | No rule determined a value for data_modality |
| .counts | 430 | No rule determined a value for data_modality |
| .bam | 357 | No rule determined a value for data_modality |
| .fast5.tar | 273 | No rule determined a value for data_modality |
| .bb | 272 | No rule determined a value for data_modality |
| .count | 215 | No rule determined a value for data_modality |
| .cmap | 210 | No rule determined a value for data_modality |
| .bedpe | 188 | No rule determined a value for data_modality |
| .dat | 94 | No rule determined a value for data_modality |
| .superdups | 86 | No rule determined a value for data_modality |
| .ped | 67 | No rule determined a value for data_modality |
| .xmap | 64 | No rule determined a value for data_modality |
| .tbi | 60 | Parent file had no value for data_modality |
| .fastq | 56 | FASTQ modality cannot be determined from reads alone — could be genomic, transcriptomic, or epigenomic depending on assay |
| .table | 47 | No rule determined a value for data_modality |
| (none) | 40 | No rule determined a value for data_modality |
| .tar | 37 | No rule determined a value for data_modality |
| .fast5.tar.gz | 26 | No rule determined a value for data_modality |
| .csv | 25 | No rule determined a value for data_modality |
| .bgz | 23 | No rule determined a value for data_modality |
| .bai | 19 | Parent file had no value for data_modality |
| .xg | 16 | No rule determined a value for data_modality |
| .gbwt | 12 | No rule determined a value for data_modality |
| .snarls | 12 | No rule determined a value for data_modality |
| .min | 12 | No rule determined a value for data_modality |
| .gg | 12 | No rule determined a value for data_modality |
| .dist | 12 | No rule determined a value for data_modality |
| .pod5 | 11 | No rule determined a value for data_modality |
| .err | 10 | No rule determined a value for data_modality |
| .dict | 9 | No rule determined a value for data_modality |
| .stdout | 8 | No rule determined a value for data_modality |
| .m5 | 8 | No rule determined a value for data_modality |
| .smap | 8 | No rule determined a value for data_modality |
| .xlsx | 7 | No rule determined a value for data_modality |
| .errbin | 6 | No rule determined a value for data_modality |
| .bnx | 6 | No rule determined a value for data_modality |
| .maprate | 6 | No rule determined a value for data_modality |
| .md | 6 | No rule determined a value for data_modality |
| .bin | 6 | No rule determined a value for data_modality |
| .r | 5 | No rule determined a value for data_modality |
| .indel | 4 | No rule determined a value for data_modality |
| .hal | 4 | No rule determined a value for data_modality |
| .xml | 4 | No rule determined a value for data_modality |
| .chimeric | 4 | No rule determined a value for data_modality |
| .sam | 4 | No rule determined a value for data_modality |
| .gct | 2 | No rule determined a value for data_modality |
| .yak | 2 | No rule determined a value for data_modality |
| .scan | 2 | No rule determined a value for data_modality |
| .errbias3 | 2 | No rule determined a value for data_modality |
| .id | 2 | No rule determined a value for data_modality |
| .md5_fq | 2 | No rule determined a value for data_modality |
| .errbias1 | 2 | No rule determined a value for data_modality |
| .errbias2 | 2 | No rule determined a value for data_modality |
| .zip | 2 | No rule determined a value for data_modality |
| .out | 2 | No rule determined a value for data_modality |
| .errbias0 | 2 | No rule determined a value for data_modality |
| .reads_bam | 2 | No rule determined a value for data_modality |
| .chain | 2 | No rule determined a value for data_modality |
| .txt~ | 1 | No rule determined a value for data_modality |
| .fofn | 1 | No rule determined a value for data_modality |
| .snakefile | 1 | No rule determined a value for data_modality |
| .scfmap | 1 | No rule determined a value for data_modality |
| .docx | 1 | No rule determined a value for data_modality |
| .fna | 1 | No rule determined a value for data_modality |
| .py | 1 | No rule determined a value for data_modality |
| .0 | 1 | No rule determined a value for data_modality |
| .h5 | 1 | No rule determined a value for data_modality |
| .gtf | 1 | No rule determined a value for data_modality |
| .swp | 1 | No rule determined a value for data_modality |
| .cpp | 1 | No rule determined a value for data_modality |
| .json | 1 | No rule determined a value for data_modality |
| .parquet | 1 | No rule determined a value for data_modality |

| Data Modality | count | % | extensions |
|---|---:|---:|---|
| `genomic` | 587,921 | 77.5% | .vcf.gz (201,883)<br>.tbi (169,463)<br>.tar (124,335)<br>.csi (41,138)<br>.cram (10,829)<br>.crai (10,319)<br>.bed.gz (7,191)<br>.bam (6,063)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.g.vcf.gz (2,504)<br>.fa.gz (1,633)<br>.pbi (1,102)<br>.bai (1,061)<br>.bed (1,059)<br>.vcf (646)<br>.fasta.gz (93)<br>.fasta (37)<br>.fa (2)<br>.sam (1) |
| `not_applicable` | 72,595 | 9.6% | .txt (37,593)<br>.md5 (15,565)<br>.png (8,049)<br>.bed (5,370)<br>.log (5,066)<br>.csi (48)<br>.pbi (32)<br>.fai (12)<br>.000014 (6)<br>.000021 (5)<br>.000022 (5)<br>.000034 (5)<br>.000033 (5)<br>.000032 (5)<br>.000024 (5)<br>.000036 (5)<br>.000044 (5)<br>.000013 (5)<br>.000035 (5)<br>.000028 (5)<br>.000045 (5)<br>.000016 (5)<br>.000010 (5)<br>.000030 (5)<br>.000039 (5)<br>.000023 (5)<br>.000006 (5)<br>.000037 (5)<br>.000043 (5)<br>.000038 (5)<br>.000004 (5)<br>.000020 (5)<br>.000008 (5)<br>.000017 (5)<br>.000011 (5)<br>.000029 (5)<br>.000041 (5)<br>.000002 (5)<br>.000007 (5)<br>.000031 (5)<br>.000015 (5)<br>.000012 (5)<br>.000003 (5)<br>.000005 (5)<br>.000019 (5)<br>.000025 (5)<br>.000026 (5)<br>.000018 (5)<br>.000009 (5)<br>.000042 (5)<br>.000000 (5)<br>.000001 (5)<br>.000040 (5)<br>.000056 (4)<br>.000073 (4)<br>.000079 (4)<br>.000048 (4)<br>.000077 (4)<br>.000081 (4)<br>.000068 (4)<br>.000054 (4)<br>.000046 (4)<br>.000069 (4)<br>.000065 (4)<br>.000050 (4)<br>.000055 (4)<br>.000078 (4)<br>.000083 (4)<br>.000027 (4)<br>.000060 (4)<br>.000071 (4)<br>.000053 (4)<br>.000057 (4)<br>.000061 (4)<br>.000067 (4)<br>.000063 (4)<br>.000064 (4)<br>.000075 (4)<br>.000070 (4)<br>.000051 (4)<br>.000072 (4)<br>.000058 (4)<br>.000062 (4)<br>.000059 (4)<br>.000074 (4)<br>.000047 (4)<br>.000085 (4)<br>.000082 (4)<br>.000076 (4)<br>.000052 (4)<br>.000066 (4)<br>.000049 (4)<br>.000080 (4)<br>.000092 (3)<br>.000113 (3)<br>.000108 (3)<br>.000115 (3)<br>.000124 (3)<br>.000126 (3)<br>.000118 (3)<br>.000099 (3)<br>.000104 (3)<br>.000086 (3)<br>.000090 (3)<br>.000111 (3)<br>.000093 (3)<br>.000127 (3)<br>.000116 (3)<br>.000088 (3)<br>.000120 (3)<br>.000096 (3)<br>.000101 (3)<br>.000125 (3)<br>.000123 (3)<br>.000102 (3)<br>.000119 (3)<br>.000109 (3)<br>.000084 (3)<br>.000122 (3)<br>.000091 (3)<br>.000114 (3)<br>.000089 (3)<br>.000117 (3)<br>.000097 (3)<br>.000087 (3)<br>.000105 (3)<br>.000106 (3)<br>.000112 (3)<br>.000098 (3)<br>.000095 (3)<br>.000107 (3)<br>.000103 (3)<br>.000094 (3)<br>.000121 (3)<br>.000100 (3)<br>.000158 (2)<br>.000159 (2)<br>.000140 (2)<br>.000168 (2)<br>.000170 (2)<br>.000179 (2)<br>.bai (2)<br>.000166 (2)<br>.000129 (2)<br>.000164 (2)<br>.000110 (2)<br>.000135 (2)<br>.000150 (2)<br>.000138 (2)<br>.000180 (2)<br>.000143 (2)<br>.000173 (2)<br>.000171 (2)<br>.000141 (2)<br>.000152 (2)<br>.000139 (2)<br>.000177 (2)<br>.000157 (2)<br>.000156 (2)<br>.000147 (2)<br>.000148 (2)<br>.000132 (2)<br>.000174 (2)<br>.000142 (2)<br>.000130 (2)<br>.000133 (2)<br>.000136 (2)<br>.000137 (2)<br>.000165 (2)<br>.000134 (2)<br>.000169 (2)<br>.000154 (2)<br>.000178 (2)<br>.000145 (2)<br>.tbi (2)<br>.000163 (2)<br>.000128 (2)<br>.000144 (2)<br>.000172 (2)<br>.000176 (2)<br>.000131 (2)<br>.000155 (2)<br>.000161 (2)<br>.000149 (2)<br>.000153 (2)<br>.000162 (2)<br>.000146 (2)<br>.000167 (2)<br>.000151 (2)<br>.000175 (2)<br>.000265 (1)<br>.245537z (1)<br>.940364z (1)<br>.000328 (1)<br>.690977z (1)<br>.000292 (1)<br>.000270 (1)<br>.000195 (1)<br>.000218 (1)<br>.897209z (1)<br>.403914z (1)<br>.800260z (1)<br>.000232 (1)<br>.000274 (1)<br>.000313 (1)<br>.319905z (1)<br>.000299 (1)<br>.082165z (1)<br>.000203 (1)<br>.000324 (1)<br>.000326 (1)<br>.984990z (1)<br>.000160 (1)<br>.000193 (1)<br>.000184 (1)<br>.064718z (1)<br>.000238 (1)<br>.000307 (1)<br>.000295 (1)<br>.000316 (1)<br>.000318 (1)<br>.000185 (1)<br>.000235 (1)<br>.000209 (1)<br>.000822 (1)<br>.000305 (1)<br>.000327 (1)<br>.152454z (1)<br>.000271 (1)<br>.000246 (1)<br>.693904z (1)<br>.000304 (1)<br>.328584z (1)<br>.000293 (1)<br>.419574z (1)<br>.000260 (1)<br>.000214 (1)<br>.000331 (1)<br>.392375z (1)<br>.758552z (1)<br>.000206 (1)<br>.001142 (1)<br>.196093z (1)<br>.000288 (1)<br>.895704z (1)<br>.000256 (1)<br>.006944z (1)<br>.000320 (1)<br>.000230 (1)<br>.000647 (1)<br>.000332 (1)<br>.000207 (1)<br>.000220 (1)<br>.705621z (1)<br>.000202 (1)<br>.000939 (1)<br>.000198 (1)<br>.089663z (1)<br>.000311 (1)<br>.000212 (1)<br>.906471z (1)<br>.000257 (1)<br>.115119z (1)<br>.000216 (1)<br>.408558z (1)<br>.328107z (1)<br>.000233 (1)<br>.000241 (1)<br>.000280 (1)<br>.000301 (1)<br>.297614z (1)<br>.000315 (1)<br>.372846z (1)<br>.000253 (1)<br>.401447z (1)<br>.000285 (1)<br>.008290z (1)<br>.000204 (1)<br>.914044z (1)<br>.000273 (1)<br>.000263 (1)<br>.000196 (1)<br>.225115z (1)<br>.000289 (1)<br>.000262 (1)<br>.000242 (1)<br>.000222 (1)<br>.643111z (1)<br>.000239 (1)<br>.000200 (1)<br>.356527z (1)<br>.000199 (1)<br>.000334 (1)<br>.000225 (1)<br>.000254 (1)<br>.000197 (1)<br>.737407z (1)<br>.936487z (1)<br>.000259 (1)<br>.000247 (1)<br>.979322z (1)<br>.000234 (1)<br>.998860z (1)<br>.000217 (1)<br>.000264 (1)<br>.000237 (1)<br>.978368z (1)<br>.000279 (1)<br>.000211 (1)<br>.848693z (1)<br>.023047z (1)<br>.213071z (1)<br>.000226 (1)<br>.000297 (1)<br>.000255 (1)<br>.035388z (1)<br>.000224 (1)<br>.988120z (1)<br>.055644z (1)<br>.000258 (1)<br>.222181z (1)<br>.333014z (1)<br>.000267 (1)<br>.051074z (1)<br>.884243z (1)<br>.000251 (1)<br>.000243 (1)<br>.000223 (1)<br>.000215 (1)<br>.000308 (1)<br>.000227 (1)<br>.000286 (1)<br>.000277 (1)<br>.000278 (1)<br>.500269z (1)<br>.430624z (1)<br>.000268 (1)<br>.000189 (1)<br>.448782z (1)<br>.570463z (1)<br>.000329 (1)<br>.410201z (1)<br>.000221 (1)<br>.000972 (1)<br>.800472z (1)<br>.000231 (1)<br>.000321 (1)<br>.000323 (1)<br>.771515z (1)<br>.006029z (1)<br>.000269 (1)<br>.901353z (1)<br>.000294 (1)<br>.000281 (1)<br>.464162z (1)<br>.000298 (1)<br>.000314 (1)<br>.104091z (1)<br>.000322 (1)<br>.000236 (1)<br>.855151z (1)<br>.000186 (1)<br>.000201 (1)<br>.258028z (1)<br>.000219 (1)<br>.000302 (1)<br>.000261 (1)<br>.684033z (1)<br>.672091z (1)<br>.000187 (1)<br>.000250 (1)<br>.000191 (1)<br>.000336 (1)<br>.000283 (1)<br>.000284 (1)<br>.000248 (1)<br>.000249 (1)<br>.000245 (1)<br>.000266 (1)<br>.000240 (1)<br>.000303 (1)<br>.169365z (1)<br>.546615z (1)<br>.921606z (1)<br>.000229 (1)<br>.220190z (1)<br>.000252 (1)<br>.169559z (1)<br>.000190 (1)<br>.000296 (1)<br>.000188 (1)<br>.000182 (1)<br>.000291 (1)<br>.000330 (1)<br>.000213 (1)<br>.960061z (1)<br>.000317 (1)<br>.000244 (1)<br>.968554z (1)<br>.613426z (1)<br>.000205 (1)<br>.871149z (1)<br>.000210 (1)<br>.000272 (1)<br>.000183 (1)<br>.000192 (1)<br>.000310 (1)<br>.102850z (1)<br>.000208 (1)<br>.000290 (1)<br>.000276 (1)<br>.000287 (1)<br>.759786z (1)<br>.278222z (1)<br>.288628z (1)<br>.000319 (1)<br>.000312 (1)<br>.337209z (1)<br>.000282 (1)<br>.000275 (1)<br>.000228 (1)<br>.067517z (1)<br>.000194 (1)<br>.000309 (1)<br>.000300 (1)<br>.796966z (1)<br>.000306 (1)<br>.000181 (1) |
| `not_classified` | 69,212 | 9.1% | .fastq.gz (23,033)<br>.fast5 (12,394)<br>.gz (7,451)<br>.txt (4,584)<br>.hist (3,870)<br>.pdf (3,028)<br>.bw (2,520)<br>.tsv (1,278)<br>.tar.gz (1,155)<br>.sizes (1,086)<br>.tex (940)<br>.tdf (860)<br>.vst (672)<br>.stats (659)<br>.qv (645)<br>.sf (634)<br>.gfa (598)<br>.html (510)<br>.sam.gz (474)<br>.counts (430)<br>.bam (357)<br>.fast5.tar (273)<br>.bb (272)<br>.count (215)<br>.cmap (210)<br>.bedpe (188)<br>.dat (94)<br>.superdups (86)<br>.ped (67)<br>.xmap (64)<br>.tbi (60)<br>.fastq (56)<br>.table (47)<br>(none) (40)<br>.tar (37)<br>.fast5.tar.gz (26)<br>.csv (25)<br>.bgz (23)<br>.bai (19)<br>.xg (16)<br>.gbwt (12)<br>.snarls (12)<br>.min (12)<br>.gg (12)<br>.dist (12)<br>.pod5 (11)<br>.err (10)<br>.dict (9)<br>.stdout (8)<br>.m5 (8)<br>.smap (8)<br>.xlsx (7)<br>.errbin (6)<br>.bnx (6)<br>.maprate (6)<br>.md (6)<br>.bin (6)<br>.r (5)<br>.indel (4)<br>.hal (4)<br>.xml (4)<br>.chimeric (4)<br>.sam (4)<br>.gct (2)<br>.yak (2)<br>.scan (2)<br>.errbias3 (2)<br>.id (2)<br>.md5_fq (2)<br>.errbias1 (2)<br>.errbias2 (2)<br>.zip (2)<br>.out (2)<br>.errbias0 (2)<br>.reads_bam (2)<br>.chain (2)<br>.txt~ (1)<br>.fofn (1)<br>.snakefile (1)<br>.scfmap (1)<br>.docx (1)<br>.fna (1)<br>.py (1)<br>.0 (1)<br>.h5 (1)<br>.gtf (1)<br>.swp (1)<br>.cpp (1)<br>.json (1)<br>.parquet (1) |
| `imaging.histology` | 25,708 | 3.4% | .svs (25,708) |
| `transcriptomic.bulk` | 2,514 | 0.3% | .bam (1,413)<br>.bai (779)<br>.txt (279)<br>.bw (16)<br>.bed.gz (12)<br>.tbi (12)<br>.csv (3) |
| `transcriptomic.single_cell` | 353 | 0.0% | .h5ad (352)<br>.fastq.gz (1) |
| `epigenomic.methylation` | 348 | 0.0% | .idat (320)<br>.bed.gz (28) |
| `epigenomic.chromatin_accessibility` | 6 | 0.0% | .fastq.gz (6) |

---

## Data Type

| | count | % |
|---|---:|---:|
| **Classified** | 722,825 | 95.3% |
| **Not classified** | 35,832 | 4.7% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .gz | 7,451 | No rule determined a value for data_type |
| .txt | 4,584 | No rule determined a value for data_type |
| .hist | 3,870 | No rule determined a value for data_type |
| .pdf | 3,028 | No rule determined a value for data_type |
| .bw | 2,520 | No rule determined a value for data_type |
| .bam | 2,065 | No rule determined a value for data_type |
| .tsv | 1,278 | No rule determined a value for data_type |
| .tar.gz | 1,155 | No rule determined a value for data_type |
| .sizes | 1,086 | No rule determined a value for data_type |
| .tex | 940 | No rule determined a value for data_type |
| .tdf | 860 | No rule determined a value for data_type |
| .pbi | 677 | Parent file had no value for data_type |
| .vst | 672 | No rule determined a value for data_type |
| .stats | 659 | No rule determined a value for data_type |
| .qv | 645 | No rule determined a value for data_type |
| .sf | 634 | No rule determined a value for data_type |
| .gfa | 598 | No rule determined a value for data_type |
| .html | 510 | No rule determined a value for data_type |
| .sam.gz | 474 | No rule determined a value for data_type |
| .counts | 430 | No rule determined a value for data_type |
| .bb | 272 | No rule determined a value for data_type |
| .count | 215 | No rule determined a value for data_type |
| .cmap | 210 | No rule determined a value for data_type |
| .bedpe | 188 | No rule determined a value for data_type |
| .dat | 94 | No rule determined a value for data_type |
| .superdups | 86 | No rule determined a value for data_type |
| .ped | 67 | No rule determined a value for data_type |
| .xmap | 64 | No rule determined a value for data_type |
| .tbi | 60 | Parent file had no value for data_type |
| .bai | 47 | Parent file had no value for data_type |
| .table | 47 | No rule determined a value for data_type |
| (none) | 40 | No rule determined a value for data_type |
| .tar | 37 | No rule determined a value for data_type |
| .csv | 25 | No rule determined a value for data_type |
| .bgz | 23 | No rule determined a value for data_type |
| .xg | 16 | No rule determined a value for data_type |
| .gbwt | 12 | No rule determined a value for data_type |
| .snarls | 12 | No rule determined a value for data_type |
| .min | 12 | No rule determined a value for data_type |
| .gg | 12 | No rule determined a value for data_type |
| .dist | 12 | No rule determined a value for data_type |
| .err | 10 | No rule determined a value for data_type |
| .dict | 9 | No rule determined a value for data_type |
| .stdout | 8 | No rule determined a value for data_type |
| .m5 | 8 | No rule determined a value for data_type |
| .smap | 8 | No rule determined a value for data_type |
| .xlsx | 7 | No rule determined a value for data_type |
| .errbin | 6 | No rule determined a value for data_type |
| .bnx | 6 | No rule determined a value for data_type |
| .maprate | 6 | No rule determined a value for data_type |
| .md | 6 | No rule determined a value for data_type |
| .bin | 6 | No rule determined a value for data_type |
| .r | 5 | No rule determined a value for data_type |
| .indel | 4 | No rule determined a value for data_type |
| .hal | 4 | No rule determined a value for data_type |
| .xml | 4 | No rule determined a value for data_type |
| .chimeric | 4 | No rule determined a value for data_type |
| .sam | 4 | No rule determined a value for data_type |
| .gct | 2 | No rule determined a value for data_type |
| .yak | 2 | No rule determined a value for data_type |
| .scan | 2 | No rule determined a value for data_type |
| .errbias3 | 2 | No rule determined a value for data_type |
| .id | 2 | No rule determined a value for data_type |
| .md5_fq | 2 | No rule determined a value for data_type |
| .errbias1 | 2 | No rule determined a value for data_type |
| .errbias2 | 2 | No rule determined a value for data_type |
| .zip | 2 | No rule determined a value for data_type |
| .out | 2 | No rule determined a value for data_type |
| .errbias0 | 2 | No rule determined a value for data_type |
| .reads_bam | 2 | No rule determined a value for data_type |
| .chain | 2 | No rule determined a value for data_type |
| .txt~ | 1 | No rule determined a value for data_type |
| .fofn | 1 | No rule determined a value for data_type |
| .snakefile | 1 | No rule determined a value for data_type |
| .scfmap | 1 | No rule determined a value for data_type |
| .docx | 1 | No rule determined a value for data_type |
| .fna | 1 | No rule determined a value for data_type |
| .py | 1 | No rule determined a value for data_type |
| .0 | 1 | No rule determined a value for data_type |
| .h5 | 1 | No rule determined a value for data_type |
| .gtf | 1 | No rule determined a value for data_type |
| .swp | 1 | No rule determined a value for data_type |
| .cpp | 1 | No rule determined a value for data_type |
| .json | 1 | No rule determined a value for data_type |
| .parquet | 1 | No rule determined a value for data_type |

| Data Type | count | % | extensions |
|---|---:|---:|---|
| `variants.germline` | 317,745 | 41.9% | .tbi (158,887)<br>.vcf.gz (158,858) |
| `archive` | 124,335 | 16.4% | .tar (124,335) |
| `variants` | 90,166 | 11.9% | .vcf.gz (42,970)<br>.csi (34,141)<br>.tbi (10,546)<br>.g.vcf.gz (2,504)<br>.vcf (5) |
| `not_applicable` | 59,176 | 7.8% | .txt (37,593)<br>.md5 (15,565)<br>.log (5,066)<br>.csi (48)<br>.pbi (32)<br>.fai (12)<br>.000014 (6)<br>.000021 (5)<br>.000022 (5)<br>.000034 (5)<br>.000033 (5)<br>.000032 (5)<br>.000024 (5)<br>.000036 (5)<br>.000044 (5)<br>.000013 (5)<br>.000035 (5)<br>.000028 (5)<br>.000045 (5)<br>.000016 (5)<br>.000010 (5)<br>.000030 (5)<br>.000039 (5)<br>.000023 (5)<br>.000006 (5)<br>.000037 (5)<br>.000043 (5)<br>.000038 (5)<br>.000004 (5)<br>.000020 (5)<br>.000008 (5)<br>.000017 (5)<br>.000011 (5)<br>.000029 (5)<br>.000041 (5)<br>.000002 (5)<br>.000007 (5)<br>.000031 (5)<br>.000015 (5)<br>.000012 (5)<br>.000003 (5)<br>.000005 (5)<br>.000019 (5)<br>.000025 (5)<br>.000026 (5)<br>.000018 (5)<br>.000009 (5)<br>.000042 (5)<br>.000000 (5)<br>.000001 (5)<br>.000040 (5)<br>.000056 (4)<br>.000073 (4)<br>.000079 (4)<br>.000048 (4)<br>.000077 (4)<br>.000081 (4)<br>.000068 (4)<br>.000054 (4)<br>.000046 (4)<br>.000069 (4)<br>.000065 (4)<br>.000050 (4)<br>.000055 (4)<br>.000078 (4)<br>.000083 (4)<br>.000027 (4)<br>.000060 (4)<br>.000071 (4)<br>.000053 (4)<br>.000057 (4)<br>.000061 (4)<br>.000067 (4)<br>.000063 (4)<br>.000064 (4)<br>.000075 (4)<br>.000070 (4)<br>.000051 (4)<br>.000072 (4)<br>.000058 (4)<br>.000062 (4)<br>.000059 (4)<br>.000074 (4)<br>.000047 (4)<br>.000085 (4)<br>.000082 (4)<br>.000076 (4)<br>.000052 (4)<br>.000066 (4)<br>.000049 (4)<br>.000080 (4)<br>.000092 (3)<br>.000113 (3)<br>.000108 (3)<br>.000115 (3)<br>.000124 (3)<br>.000126 (3)<br>.000118 (3)<br>.000099 (3)<br>.000104 (3)<br>.000086 (3)<br>.000090 (3)<br>.000111 (3)<br>.000093 (3)<br>.000127 (3)<br>.000116 (3)<br>.000088 (3)<br>.000120 (3)<br>.000096 (3)<br>.000101 (3)<br>.000125 (3)<br>.000123 (3)<br>.000102 (3)<br>.000119 (3)<br>.000109 (3)<br>.000084 (3)<br>.000122 (3)<br>.000091 (3)<br>.000114 (3)<br>.000089 (3)<br>.000117 (3)<br>.000097 (3)<br>.000087 (3)<br>.000105 (3)<br>.000106 (3)<br>.000112 (3)<br>.000098 (3)<br>.000095 (3)<br>.000107 (3)<br>.000103 (3)<br>.000094 (3)<br>.000121 (3)<br>.000100 (3)<br>.000158 (2)<br>.000159 (2)<br>.000140 (2)<br>.000168 (2)<br>.000170 (2)<br>.000179 (2)<br>.bai (2)<br>.000166 (2)<br>.000129 (2)<br>.000164 (2)<br>.000110 (2)<br>.000135 (2)<br>.000150 (2)<br>.000138 (2)<br>.000180 (2)<br>.000143 (2)<br>.000173 (2)<br>.000171 (2)<br>.000141 (2)<br>.000152 (2)<br>.000139 (2)<br>.000177 (2)<br>.000157 (2)<br>.000156 (2)<br>.000147 (2)<br>.000148 (2)<br>.000132 (2)<br>.000174 (2)<br>.000142 (2)<br>.000130 (2)<br>.000133 (2)<br>.000136 (2)<br>.000137 (2)<br>.000165 (2)<br>.000134 (2)<br>.000169 (2)<br>.000154 (2)<br>.000178 (2)<br>.000145 (2)<br>.tbi (2)<br>.000163 (2)<br>.000128 (2)<br>.000144 (2)<br>.000172 (2)<br>.000176 (2)<br>.000131 (2)<br>.000155 (2)<br>.000161 (2)<br>.000149 (2)<br>.000153 (2)<br>.000162 (2)<br>.000146 (2)<br>.000167 (2)<br>.000151 (2)<br>.000175 (2)<br>.000265 (1)<br>.245537z (1)<br>.940364z (1)<br>.000328 (1)<br>.690977z (1)<br>.000292 (1)<br>.000270 (1)<br>.000195 (1)<br>.000218 (1)<br>.897209z (1)<br>.403914z (1)<br>.800260z (1)<br>.000232 (1)<br>.000274 (1)<br>.000313 (1)<br>.319905z (1)<br>.000299 (1)<br>.082165z (1)<br>.000203 (1)<br>.000324 (1)<br>.000326 (1)<br>.984990z (1)<br>.000160 (1)<br>.000193 (1)<br>.000184 (1)<br>.064718z (1)<br>.000238 (1)<br>.000307 (1)<br>.000295 (1)<br>.000316 (1)<br>.000318 (1)<br>.000185 (1)<br>.000235 (1)<br>.000209 (1)<br>.000822 (1)<br>.000305 (1)<br>.000327 (1)<br>.152454z (1)<br>.000271 (1)<br>.000246 (1)<br>.693904z (1)<br>.000304 (1)<br>.328584z (1)<br>.000293 (1)<br>.419574z (1)<br>.000260 (1)<br>.000214 (1)<br>.000331 (1)<br>.392375z (1)<br>.758552z (1)<br>.000206 (1)<br>.001142 (1)<br>.196093z (1)<br>.000288 (1)<br>.895704z (1)<br>.000256 (1)<br>.006944z (1)<br>.000320 (1)<br>.000230 (1)<br>.000647 (1)<br>.000332 (1)<br>.000207 (1)<br>.000220 (1)<br>.705621z (1)<br>.000202 (1)<br>.000939 (1)<br>.000198 (1)<br>.089663z (1)<br>.000311 (1)<br>.000212 (1)<br>.906471z (1)<br>.000257 (1)<br>.115119z (1)<br>.000216 (1)<br>.408558z (1)<br>.328107z (1)<br>.000233 (1)<br>.000241 (1)<br>.000280 (1)<br>.000301 (1)<br>.297614z (1)<br>.000315 (1)<br>.372846z (1)<br>.000253 (1)<br>.401447z (1)<br>.000285 (1)<br>.008290z (1)<br>.000204 (1)<br>.914044z (1)<br>.000273 (1)<br>.000263 (1)<br>.000196 (1)<br>.225115z (1)<br>.000289 (1)<br>.000262 (1)<br>.000242 (1)<br>.000222 (1)<br>.643111z (1)<br>.000239 (1)<br>.000200 (1)<br>.356527z (1)<br>.000199 (1)<br>.000334 (1)<br>.000225 (1)<br>.000254 (1)<br>.000197 (1)<br>.737407z (1)<br>.936487z (1)<br>.000259 (1)<br>.000247 (1)<br>.979322z (1)<br>.000234 (1)<br>.998860z (1)<br>.000217 (1)<br>.000264 (1)<br>.000237 (1)<br>.978368z (1)<br>.000279 (1)<br>.000211 (1)<br>.848693z (1)<br>.023047z (1)<br>.213071z (1)<br>.000226 (1)<br>.000297 (1)<br>.000255 (1)<br>.035388z (1)<br>.000224 (1)<br>.988120z (1)<br>.055644z (1)<br>.000258 (1)<br>.222181z (1)<br>.333014z (1)<br>.000267 (1)<br>.051074z (1)<br>.884243z (1)<br>.000251 (1)<br>.000243 (1)<br>.000223 (1)<br>.000215 (1)<br>.000308 (1)<br>.000227 (1)<br>.000286 (1)<br>.000277 (1)<br>.000278 (1)<br>.500269z (1)<br>.430624z (1)<br>.000268 (1)<br>.000189 (1)<br>.448782z (1)<br>.570463z (1)<br>.000329 (1)<br>.410201z (1)<br>.000221 (1)<br>.000972 (1)<br>.800472z (1)<br>.000231 (1)<br>.000321 (1)<br>.000323 (1)<br>.771515z (1)<br>.006029z (1)<br>.000269 (1)<br>.901353z (1)<br>.000294 (1)<br>.000281 (1)<br>.464162z (1)<br>.000298 (1)<br>.000314 (1)<br>.104091z (1)<br>.000322 (1)<br>.000236 (1)<br>.855151z (1)<br>.000186 (1)<br>.000201 (1)<br>.258028z (1)<br>.000219 (1)<br>.000302 (1)<br>.000261 (1)<br>.684033z (1)<br>.672091z (1)<br>.000187 (1)<br>.000250 (1)<br>.000191 (1)<br>.000336 (1)<br>.000283 (1)<br>.000284 (1)<br>.000248 (1)<br>.000249 (1)<br>.000245 (1)<br>.000266 (1)<br>.000240 (1)<br>.000303 (1)<br>.169365z (1)<br>.546615z (1)<br>.921606z (1)<br>.000229 (1)<br>.220190z (1)<br>.000252 (1)<br>.169559z (1)<br>.000190 (1)<br>.000296 (1)<br>.000188 (1)<br>.000182 (1)<br>.000291 (1)<br>.000330 (1)<br>.000213 (1)<br>.960061z (1)<br>.000317 (1)<br>.000244 (1)<br>.968554z (1)<br>.613426z (1)<br>.000205 (1)<br>.871149z (1)<br>.000210 (1)<br>.000272 (1)<br>.000183 (1)<br>.000192 (1)<br>.000310 (1)<br>.102850z (1)<br>.000208 (1)<br>.000290 (1)<br>.000276 (1)<br>.000287 (1)<br>.759786z (1)<br>.278222z (1)<br>.288628z (1)<br>.000319 (1)<br>.000312 (1)<br>.337209z (1)<br>.000282 (1)<br>.000275 (1)<br>.000228 (1)<br>.067517z (1)<br>.000194 (1)<br>.000309 (1)<br>.000300 (1)<br>.796966z (1)<br>.000306 (1)<br>.000181 (1) |
| `not_classified` | 35,832 | 4.7% | .gz (7,451)<br>.txt (4,584)<br>.hist (3,870)<br>.pdf (3,028)<br>.bw (2,520)<br>.bam (2,065)<br>.tsv (1,278)<br>.tar.gz (1,155)<br>.sizes (1,086)<br>.tex (940)<br>.tdf (860)<br>.pbi (677)<br>.vst (672)<br>.stats (659)<br>.qv (645)<br>.sf (634)<br>.gfa (598)<br>.html (510)<br>.sam.gz (474)<br>.counts (430)<br>.bb (272)<br>.count (215)<br>.cmap (210)<br>.bedpe (188)<br>.dat (94)<br>.superdups (86)<br>.ped (67)<br>.xmap (64)<br>.tbi (60)<br>.bai (47)<br>.table (47)<br>(none) (40)<br>.tar (37)<br>.csv (25)<br>.bgz (23)<br>.xg (16)<br>.gbwt (12)<br>.snarls (12)<br>.min (12)<br>.gg (12)<br>.dist (12)<br>.err (10)<br>.dict (9)<br>.stdout (8)<br>.m5 (8)<br>.smap (8)<br>.xlsx (7)<br>.errbin (6)<br>.bnx (6)<br>.maprate (6)<br>.md (6)<br>.bin (6)<br>.r (5)<br>.indel (4)<br>.hal (4)<br>.xml (4)<br>.chimeric (4)<br>.sam (4)<br>.gct (2)<br>.yak (2)<br>.scan (2)<br>.errbias3 (2)<br>.id (2)<br>.md5_fq (2)<br>.errbias1 (2)<br>.errbias2 (2)<br>.zip (2)<br>.out (2)<br>.errbias0 (2)<br>.reads_bam (2)<br>.chain (2)<br>.txt~ (1)<br>.fofn (1)<br>.snakefile (1)<br>.scfmap (1)<br>.docx (1)<br>.fna (1)<br>.py (1)<br>.0 (1)<br>.h5 (1)<br>.gtf (1)<br>.swp (1)<br>.cpp (1)<br>.json (1)<br>.parquet (1) |
| `images` | 33,757 | 4.4% | .svs (25,708)<br>.png (8,049) |
| `alignments` | 29,154 | 3.8% | .cram (10,829)<br>.crai (10,319)<br>.bam (5,768)<br>.bai (1,812)<br>.pbi (425)<br>.sam (1) |
| `reads` | 23,096 | 3.0% | .fastq.gz (23,040)<br>.fastq (56) |
| `annotations` | 20,673 | 2.7% | .bed.gz (7,231)<br>.csi (6,997)<br>.bed (6,429)<br>.tbi (16) |
| `raw_signal` | 12,704 | 1.7% | .fast5 (12,394)<br>.fast5.tar (273)<br>.fast5.tar.gz (26)<br>.pod5 (11) |
| `genotypes` | 8,562 | 1.1% | .pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854) |
| `assembly` | 1,747 | 0.2% | .fa.gz (1,631)<br>.fasta.gz (90)<br>.fasta (25)<br>.fa (1) |
| `variants.structural` | 722 | 0.1% | .vcf (641)<br>.vcf.gz (55)<br>.tbi (26) |
| `expression_matrix` | 634 | 0.1% | .h5ad (352)<br>.txt (279)<br>.csv (3) |
| `array_signal` | 320 | 0.0% | .idat (320) |
| `sequence` | 16 | 0.0% | .fasta (10)<br>.fasta.gz (3)<br>.fa.gz (2)<br>.fa (1) |
| `signal` | 16 | 0.0% | .bw (16) |
| `reference_genome` | 2 | 0.0% | .fasta (2) |

---

## Reference Assembly

| | count | % |
|---|---:|---:|
| **Classified** | 596,211 | 78.6% |
| **Not classified** | 162,446 | 21.4% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .tar | 124,372 | No rule determined a value for reference_assembly |
| .gz | 7,060 | No rule determined a value for reference_assembly |
| .txt | 4,467 | No rule determined a value for reference_assembly |
| .hist | 3,870 | No rule determined a value for reference_assembly |
| .pdf | 3,027 | No rule determined a value for reference_assembly |
| .bw | 2,536 | No rule determined a value for reference_assembly |
| .vcf.gz | 2,197 | No rule determined a value for reference_assembly |
| .csi | 1,968 | Parent file had no value for reference_assembly |
| .tsv | 1,260 | No rule determined a value for reference_assembly |
| .tar.gz | 1,145 | No rule determined a value for reference_assembly |
| .sizes | 1,084 | No rule determined a value for reference_assembly |
| .tex | 940 | No rule determined a value for reference_assembly |
| .tdf | 860 | No rule determined a value for reference_assembly |
| .vst | 672 | No rule determined a value for reference_assembly |
| .stats | 659 | No rule determined a value for reference_assembly |
| .qv | 645 | No rule determined a value for reference_assembly |
| .sf | 634 | No rule determined a value for reference_assembly |
| .gfa | 598 | No rule determined a value for reference_assembly |
| .html | 510 | No rule determined a value for reference_assembly |
| .sam.gz | 474 | No rule determined a value for reference_assembly |
| .counts | 430 | No rule determined a value for reference_assembly |
| .h5ad | 352 | No rule determined a value for reference_assembly |
| .idat | 320 | No rule determined a value for reference_assembly |
| .bam | 277 | No rule determined a value for reference_assembly |
| .bai | 274 | Parent file had no value for reference_assembly |
| .tbi | 266 | Parent file had no value for reference_assembly |
| .vcf | 252 | No rule determined a value for reference_assembly |
| .count | 215 | No rule determined a value for reference_assembly |
| .cmap | 210 | No rule determined a value for reference_assembly |
| .bedpe | 188 | No rule determined a value for reference_assembly |
| .bb | 94 | No rule determined a value for reference_assembly |
| .dat | 94 | No rule determined a value for reference_assembly |
| .superdups | 86 | No rule determined a value for reference_assembly |
| .ped | 67 | No rule determined a value for reference_assembly |
| .xmap | 64 | No rule determined a value for reference_assembly |
| .table | 47 | No rule determined a value for reference_assembly |
| (none) | 40 | No rule determined a value for reference_assembly |
| .bed.gz | 31 | No rule determined a value for reference_assembly |
| .csv | 28 | No rule determined a value for reference_assembly |
| .err | 10 | No rule determined a value for reference_assembly |
| .stdout | 8 | No rule determined a value for reference_assembly |
| .m5 | 8 | No rule determined a value for reference_assembly |
| .smap | 8 | No rule determined a value for reference_assembly |
| .xlsx | 7 | No rule determined a value for reference_assembly |
| .errbin | 6 | No rule determined a value for reference_assembly |
| .bnx | 6 | No rule determined a value for reference_assembly |
| .maprate | 6 | No rule determined a value for reference_assembly |
| .md | 6 | No rule determined a value for reference_assembly |
| .bin | 6 | No rule determined a value for reference_assembly |
| .sam | 5 | No rule determined a value for reference_assembly |
| .r | 5 | No rule determined a value for reference_assembly |
| .indel | 4 | No rule determined a value for reference_assembly |
| .xml | 4 | No rule determined a value for reference_assembly |
| .chimeric | 4 | No rule determined a value for reference_assembly |
| .fasta | 3 | No rule determined a value for reference_assembly |
| .gct | 2 | No rule determined a value for reference_assembly |
| .yak | 2 | No rule determined a value for reference_assembly |
| .scan | 2 | No rule determined a value for reference_assembly |
| .errbias3 | 2 | No rule determined a value for reference_assembly |
| .md5_fq | 2 | No rule determined a value for reference_assembly |
| .errbias1 | 2 | No rule determined a value for reference_assembly |
| .errbias2 | 2 | No rule determined a value for reference_assembly |
| .zip | 2 | No rule determined a value for reference_assembly |
| .out | 2 | No rule determined a value for reference_assembly |
| .errbias0 | 2 | No rule determined a value for reference_assembly |
| .reads_bam | 2 | No rule determined a value for reference_assembly |
| .bed | 1 | No rule determined a value for reference_assembly |
| .txt~ | 1 | No rule determined a value for reference_assembly |
| .fofn | 1 | No rule determined a value for reference_assembly |
| .snakefile | 1 | No rule determined a value for reference_assembly |
| .dict | 1 | No rule determined a value for reference_assembly |
| .scfmap | 1 | No rule determined a value for reference_assembly |
| .docx | 1 | No rule determined a value for reference_assembly |
| .py | 1 | No rule determined a value for reference_assembly |
| .0 | 1 | No rule determined a value for reference_assembly |
| .h5 | 1 | No rule determined a value for reference_assembly |
| .swp | 1 | No rule determined a value for reference_assembly |
| .chain | 1 | No rule determined a value for reference_assembly |
| .cpp | 1 | No rule determined a value for reference_assembly |
| .json | 1 | No rule determined a value for reference_assembly |
| .parquet | 1 | No rule determined a value for reference_assembly |

| Reference Assembly | count | % | extensions |
|---|---:|---:|---|
| `CHM13` | 414,459 | 54.6% | .vcf.gz (190,224)<br>.tbi (159,059)<br>.csi (37,922)<br>.bed.gz (6,723)<br>.cram (6,718)<br>.crai (6,715)<br>.txt (5,298)<br>.bam (427)<br>.bed (413)<br>.bai (393)<br>.vcf (208)<br>.gz (195)<br>.bb (89)<br>.xg (10)<br>.tsv (8)<br>.fasta (6)<br>.tar.gz (6)<br>.gbwt (6)<br>.snarls (6)<br>.gg (6)<br>.min (6)<br>.dist (6)<br>.dict (5)<br>.fasta.gz (3)<br>.fa.gz (2)<br>.hal (2)<br>.fa (1)<br>.sizes (1)<br>.chain (1) |
| `not_classified` | 162,446 | 21.4% | .tar (124,372)<br>.gz (7,060)<br>.txt (4,467)<br>.hist (3,870)<br>.pdf (3,027)<br>.bw (2,536)<br>.vcf.gz (2,197)<br>.csi (1,968)<br>.tsv (1,260)<br>.tar.gz (1,145)<br>.sizes (1,084)<br>.tex (940)<br>.tdf (860)<br>.vst (672)<br>.stats (659)<br>.qv (645)<br>.sf (634)<br>.gfa (598)<br>.html (510)<br>.sam.gz (474)<br>.counts (430)<br>.h5ad (352)<br>.idat (320)<br>.bam (277)<br>.bai (274)<br>.tbi (266)<br>.vcf (252)<br>.count (215)<br>.cmap (210)<br>.bedpe (188)<br>.bb (94)<br>.dat (94)<br>.superdups (86)<br>.ped (67)<br>.xmap (64)<br>.table (47)<br>(none) (40)<br>.bed.gz (31)<br>.csv (28)<br>.err (10)<br>.stdout (8)<br>.m5 (8)<br>.smap (8)<br>.xlsx (7)<br>.errbin (6)<br>.bnx (6)<br>.maprate (6)<br>.md (6)<br>.bin (6)<br>.sam (5)<br>.r (5)<br>.indel (4)<br>.xml (4)<br>.chimeric (4)<br>.fasta (3)<br>.gct (2)<br>.yak (2)<br>.scan (2)<br>.errbias3 (2)<br>.md5_fq (2)<br>.errbias1 (2)<br>.errbias2 (2)<br>.zip (2)<br>.out (2)<br>.errbias0 (2)<br>.reads_bam (2)<br>.bed (1)<br>.txt~ (1)<br>.fofn (1)<br>.snakefile (1)<br>.dict (1)<br>.scfmap (1)<br>.docx (1)<br>.py (1)<br>.0 (1)<br>.h5 (1)<br>.swp (1)<br>.chain (1)<br>.cpp (1)<br>.json (1)<br>.parquet (1) |
| `not_applicable` | 136,176 | 17.9% | .txt (32,494)<br>.svs (25,708)<br>.fastq.gz (23,040)<br>.md5 (15,565)<br>.fast5 (12,394)<br>.png (8,049)<br>.log (5,066)<br>.bed (4,830)<br>.bam (4,653)<br>.fa.gz (1,631)<br>.pbi (1,134)<br>.fast5.tar (273)<br>.bed.gz (188)<br>.fasta.gz (90)<br>.fastq (56)<br>.csi (48)<br>.fast5.tar.gz (26)<br>.fasta (25)<br>.bai (24)<br>.fai (12)<br>.pod5 (11)<br>.000014 (6)<br>.000021 (5)<br>.000022 (5)<br>.000034 (5)<br>.000033 (5)<br>.000032 (5)<br>.000024 (5)<br>.000036 (5)<br>.000044 (5)<br>.000013 (5)<br>.000035 (5)<br>.000028 (5)<br>.000045 (5)<br>.000016 (5)<br>.000010 (5)<br>.000030 (5)<br>.000039 (5)<br>.000023 (5)<br>.000006 (5)<br>.000037 (5)<br>.000043 (5)<br>.000038 (5)<br>.000004 (5)<br>.000020 (5)<br>.000008 (5)<br>.000017 (5)<br>.000011 (5)<br>.000029 (5)<br>.000041 (5)<br>.000002 (5)<br>.000007 (5)<br>.000031 (5)<br>.000015 (5)<br>.000012 (5)<br>.000003 (5)<br>.000005 (5)<br>.000019 (5)<br>.000025 (5)<br>.000026 (5)<br>.000018 (5)<br>.000009 (5)<br>.000042 (5)<br>.000000 (5)<br>.000001 (5)<br>.000040 (5)<br>.000056 (4)<br>.000073 (4)<br>.000079 (4)<br>.000048 (4)<br>.000077 (4)<br>.000081 (4)<br>.000068 (4)<br>.000054 (4)<br>.000046 (4)<br>.000069 (4)<br>.000065 (4)<br>.000050 (4)<br>.000055 (4)<br>.000078 (4)<br>.000083 (4)<br>.000027 (4)<br>.000060 (4)<br>.000071 (4)<br>.000053 (4)<br>.000057 (4)<br>.000061 (4)<br>.000067 (4)<br>.000063 (4)<br>.000064 (4)<br>.000075 (4)<br>.000070 (4)<br>.000051 (4)<br>.000072 (4)<br>.000058 (4)<br>.000062 (4)<br>.000059 (4)<br>.000074 (4)<br>.000047 (4)<br>.000085 (4)<br>.000082 (4)<br>.000076 (4)<br>.000052 (4)<br>.000066 (4)<br>.000049 (4)<br>.000080 (4)<br>.000092 (3)<br>.000113 (3)<br>.000108 (3)<br>.000115 (3)<br>.000124 (3)<br>.000126 (3)<br>.000118 (3)<br>.000099 (3)<br>.000104 (3)<br>.000086 (3)<br>.000090 (3)<br>.000111 (3)<br>.000093 (3)<br>.000127 (3)<br>.000116 (3)<br>.000088 (3)<br>.000120 (3)<br>.000096 (3)<br>.000101 (3)<br>.000125 (3)<br>.000123 (3)<br>.000102 (3)<br>.000119 (3)<br>.000109 (3)<br>.000084 (3)<br>.000122 (3)<br>.000091 (3)<br>.000114 (3)<br>.000089 (3)<br>.000117 (3)<br>.000097 (3)<br>.000087 (3)<br>.000105 (3)<br>.000106 (3)<br>.000112 (3)<br>.000098 (3)<br>.000095 (3)<br>.000107 (3)<br>.000103 (3)<br>.000094 (3)<br>.000121 (3)<br>.000100 (3)<br>.000158 (2)<br>.000159 (2)<br>.000140 (2)<br>.000168 (2)<br>.000170 (2)<br>.000179 (2)<br>.000166 (2)<br>.000129 (2)<br>.000164 (2)<br>.000110 (2)<br>.000135 (2)<br>.000150 (2)<br>.000138 (2)<br>.000180 (2)<br>.000143 (2)<br>.000173 (2)<br>.000171 (2)<br>.000141 (2)<br>.000152 (2)<br>.000139 (2)<br>.000177 (2)<br>.000157 (2)<br>.000156 (2)<br>.000147 (2)<br>.000148 (2)<br>.000132 (2)<br>.000174 (2)<br>.000142 (2)<br>.000130 (2)<br>.000133 (2)<br>.000136 (2)<br>.000137 (2)<br>.000165 (2)<br>.000134 (2)<br>.000169 (2)<br>.000154 (2)<br>.000178 (2)<br>.000145 (2)<br>.tbi (2)<br>.000163 (2)<br>.000128 (2)<br>.000144 (2)<br>.000172 (2)<br>.000176 (2)<br>.000131 (2)<br>.000155 (2)<br>.000161 (2)<br>.000149 (2)<br>.000153 (2)<br>.000162 (2)<br>.000146 (2)<br>.000167 (2)<br>.000151 (2)<br>.000175 (2)<br>.fa (1)<br>.000265 (1)<br>.245537z (1)<br>.940364z (1)<br>.000328 (1)<br>.690977z (1)<br>.000292 (1)<br>.000270 (1)<br>.000195 (1)<br>.000218 (1)<br>.897209z (1)<br>.403914z (1)<br>.800260z (1)<br>.000232 (1)<br>.000274 (1)<br>.000313 (1)<br>.319905z (1)<br>.000299 (1)<br>.082165z (1)<br>.000203 (1)<br>.000324 (1)<br>.000326 (1)<br>.984990z (1)<br>.000160 (1)<br>.000193 (1)<br>.000184 (1)<br>.064718z (1)<br>.000238 (1)<br>.000307 (1)<br>.000295 (1)<br>.000316 (1)<br>.000318 (1)<br>.000185 (1)<br>.000235 (1)<br>.000209 (1)<br>.000822 (1)<br>.000305 (1)<br>.000327 (1)<br>.152454z (1)<br>.000271 (1)<br>.000246 (1)<br>.693904z (1)<br>.000304 (1)<br>.328584z (1)<br>.000293 (1)<br>.419574z (1)<br>.000260 (1)<br>.000214 (1)<br>.000331 (1)<br>.392375z (1)<br>.758552z (1)<br>.000206 (1)<br>.001142 (1)<br>.196093z (1)<br>.000288 (1)<br>.895704z (1)<br>.000256 (1)<br>.006944z (1)<br>.000320 (1)<br>.000230 (1)<br>.000647 (1)<br>.000332 (1)<br>.000207 (1)<br>.000220 (1)<br>.705621z (1)<br>.000202 (1)<br>.000939 (1)<br>.000198 (1)<br>.089663z (1)<br>.000311 (1)<br>.000212 (1)<br>.906471z (1)<br>.000257 (1)<br>.115119z (1)<br>.000216 (1)<br>.408558z (1)<br>.328107z (1)<br>.000233 (1)<br>.000241 (1)<br>.000280 (1)<br>.000301 (1)<br>.297614z (1)<br>.000315 (1)<br>.372846z (1)<br>.000253 (1)<br>.401447z (1)<br>.000285 (1)<br>.008290z (1)<br>.000204 (1)<br>.914044z (1)<br>.000273 (1)<br>.000263 (1)<br>.000196 (1)<br>.225115z (1)<br>.000289 (1)<br>.000262 (1)<br>.000242 (1)<br>.000222 (1)<br>.643111z (1)<br>.000239 (1)<br>.000200 (1)<br>.356527z (1)<br>.000199 (1)<br>.000334 (1)<br>.000225 (1)<br>.000254 (1)<br>.000197 (1)<br>.737407z (1)<br>.936487z (1)<br>.000259 (1)<br>.000247 (1)<br>.979322z (1)<br>.000234 (1)<br>.998860z (1)<br>.000217 (1)<br>.000264 (1)<br>.000237 (1)<br>.978368z (1)<br>.000279 (1)<br>.000211 (1)<br>.848693z (1)<br>.023047z (1)<br>.213071z (1)<br>.000226 (1)<br>.000297 (1)<br>.000255 (1)<br>.035388z (1)<br>.000224 (1)<br>.988120z (1)<br>.055644z (1)<br>.000258 (1)<br>.222181z (1)<br>.333014z (1)<br>.000267 (1)<br>.051074z (1)<br>.884243z (1)<br>.000251 (1)<br>.000243 (1)<br>.000223 (1)<br>.000215 (1)<br>.000308 (1)<br>.000227 (1)<br>.000286 (1)<br>.000277 (1)<br>.000278 (1)<br>.500269z (1)<br>.430624z (1)<br>.000268 (1)<br>.000189 (1)<br>.448782z (1)<br>.570463z (1)<br>.000329 (1)<br>.410201z (1)<br>.000221 (1)<br>.000972 (1)<br>.800472z (1)<br>.000231 (1)<br>.000321 (1)<br>.000323 (1)<br>.771515z (1)<br>.006029z (1)<br>.000269 (1)<br>.901353z (1)<br>.000294 (1)<br>.000281 (1)<br>.464162z (1)<br>.000298 (1)<br>.000314 (1)<br>.104091z (1)<br>.000322 (1)<br>.000236 (1)<br>.855151z (1)<br>.000186 (1)<br>.000201 (1)<br>.258028z (1)<br>.000219 (1)<br>.000302 (1)<br>.000261 (1)<br>.684033z (1)<br>.672091z (1)<br>.000187 (1)<br>.000250 (1)<br>.000191 (1)<br>.000336 (1)<br>.000283 (1)<br>.000284 (1)<br>.000248 (1)<br>.000249 (1)<br>.000245 (1)<br>.000266 (1)<br>.000240 (1)<br>.000303 (1)<br>.169365z (1)<br>.546615z (1)<br>.921606z (1)<br>.000229 (1)<br>.220190z (1)<br>.000252 (1)<br>.169559z (1)<br>.000190 (1)<br>.000296 (1)<br>.000188 (1)<br>.000182 (1)<br>.000291 (1)<br>.000330 (1)<br>.000213 (1)<br>.960061z (1)<br>.000317 (1)<br>.000244 (1)<br>.968554z (1)<br>.613426z (1)<br>.000205 (1)<br>.871149z (1)<br>.000210 (1)<br>.000272 (1)<br>.000183 (1)<br>.000192 (1)<br>.000310 (1)<br>.102850z (1)<br>.000208 (1)<br>.000290 (1)<br>.000276 (1)<br>.000287 (1)<br>.759786z (1)<br>.278222z (1)<br>.288628z (1)<br>.000319 (1)<br>.000312 (1)<br>.337209z (1)<br>.000282 (1)<br>.000275 (1)<br>.000228 (1)<br>.067517z (1)<br>.000194 (1)<br>.000309 (1)<br>.000300 (1)<br>.796966z (1)<br>.000306 (1)<br>.000181 (1) |
| `GRCh38` | 45,560 | 6.0% | .tbi (10,210)<br>.vcf.gz (9,454)<br>.cram (4,111)<br>.crai (3,604)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.g.vcf.gz (2,504)<br>.bam (2,476)<br>.csi (1,248)<br>.bed (1,180)<br>.bai (1,170)<br>.bed.gz (289)<br>.txt (197)<br>.gz (196)<br>.vcf (183)<br>.bb (89)<br>.bgz (23)<br>.tsv (10)<br>.min (6)<br>.xg (6)<br>.gbwt (6)<br>.gg (6)<br>.dist (6)<br>.snarls (6)<br>.tar.gz (4)<br>.fasta (3)<br>.dict (3)<br>.hal (2)<br>.id (2)<br>.fna (1)<br>.gtf (1)<br>.sizes (1)<br>.pdf (1) |
| `GRCh37` | 16 | 0.0% | .vcf.gz (8)<br>.bed (5)<br>.vcf (3) |

---

## Platform

| | count | % |
|---|---:|---:|
| **Classified** | 157,981 | 20.8% |
| **Not classified** | 600,676 | 79.2% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf.gz | 201,883 | No rule determined a value for platform |
| .tbi | 169,535 | Parent file had no value for platform |
| .tar | 124,372 | No rule determined a value for platform |
| .csi | 41,138 | Parent file had no value for platform |
| .gz | 7,451 | No rule determined a value for platform |
| .bed.gz | 7,231 | No rule determined a value for platform |
| .bed | 6,429 | No rule determined a value for platform |
| .txt | 4,863 | No rule determined a value for platform |
| .hist | 3,870 | No rule determined a value for platform |
| .pdf | 3,028 | No rule determined a value for platform |
| .bam | 2,960 | No rule determined a value for platform |
| .pgen | 2,854 | No rule determined a value for platform |
| .pvar | 2,854 | No rule determined a value for platform |
| .psam | 2,854 | No rule determined a value for platform |
| .bw | 2,536 | No rule determined a value for platform |
| .g.vcf.gz | 2,504 | No rule determined a value for platform |
| .bai | 1,499 | Parent file had no value for platform |
| .tsv | 1,278 | No rule determined a value for platform |
| .tar.gz | 1,155 | No rule determined a value for platform |
| .sizes | 1,086 | No rule determined a value for platform |
| .tex | 940 | No rule determined a value for platform |
| .tdf | 860 | No rule determined a value for platform |
| .vst | 672 | No rule determined a value for platform |
| .stats | 659 | No rule determined a value for platform |
| .vcf | 646 | No rule determined a value for platform |
| .qv | 645 | No rule determined a value for platform |
| .sf | 634 | No rule determined a value for platform |
| .gfa | 598 | No rule determined a value for platform |
| .html | 510 | No rule determined a value for platform |
| .sam.gz | 474 | No rule determined a value for platform |
| .counts | 430 | No rule determined a value for platform |
| .h5ad | 352 | No rule determined a value for platform |
| .idat | 320 | No rule determined a value for platform |
| .bb | 272 | No rule determined a value for platform |
| .count | 215 | No rule determined a value for platform |
| .cmap | 210 | No rule determined a value for platform |
| .bedpe | 188 | No rule determined a value for platform |
| .dat | 94 | No rule determined a value for platform |
| .superdups | 86 | No rule determined a value for platform |
| .ped | 67 | No rule determined a value for platform |
| .xmap | 64 | No rule determined a value for platform |
| .table | 47 | No rule determined a value for platform |
| (none) | 40 | No rule determined a value for platform |
| .csv | 28 | No rule determined a value for platform |
| .bgz | 23 | No rule determined a value for platform |
| .xg | 16 | No rule determined a value for platform |
| .gbwt | 12 | No rule determined a value for platform |
| .snarls | 12 | No rule determined a value for platform |
| .min | 12 | No rule determined a value for platform |
| .gg | 12 | No rule determined a value for platform |
| .dist | 12 | No rule determined a value for platform |
| .err | 10 | No rule determined a value for platform |
| .dict | 9 | No rule determined a value for platform |
| .stdout | 8 | No rule determined a value for platform |
| .m5 | 8 | No rule determined a value for platform |
| .smap | 8 | No rule determined a value for platform |
| .xlsx | 7 | No rule determined a value for platform |
| .errbin | 6 | No rule determined a value for platform |
| .bnx | 6 | No rule determined a value for platform |
| .maprate | 6 | No rule determined a value for platform |
| .md | 6 | No rule determined a value for platform |
| .bin | 6 | No rule determined a value for platform |
| .sam | 5 | No rule determined a value for platform |
| .r | 5 | No rule determined a value for platform |
| .indel | 4 | No rule determined a value for platform |
| .hal | 4 | No rule determined a value for platform |
| .xml | 4 | No rule determined a value for platform |
| .chimeric | 4 | No rule determined a value for platform |
| .gct | 2 | No rule determined a value for platform |
| .yak | 2 | No rule determined a value for platform |
| .scan | 2 | No rule determined a value for platform |
| .errbias3 | 2 | No rule determined a value for platform |
| .id | 2 | No rule determined a value for platform |
| .md5_fq | 2 | No rule determined a value for platform |
| .errbias1 | 2 | No rule determined a value for platform |
| .errbias2 | 2 | No rule determined a value for platform |
| .zip | 2 | No rule determined a value for platform |
| .out | 2 | No rule determined a value for platform |
| .errbias0 | 2 | No rule determined a value for platform |
| .reads_bam | 2 | No rule determined a value for platform |
| .chain | 2 | No rule determined a value for platform |
| .txt~ | 1 | No rule determined a value for platform |
| .fofn | 1 | No rule determined a value for platform |
| .snakefile | 1 | No rule determined a value for platform |
| .scfmap | 1 | No rule determined a value for platform |
| .docx | 1 | No rule determined a value for platform |
| .fna | 1 | No rule determined a value for platform |
| .py | 1 | No rule determined a value for platform |
| .0 | 1 | No rule determined a value for platform |
| .h5 | 1 | No rule determined a value for platform |
| .gtf | 1 | No rule determined a value for platform |
| .swp | 1 | No rule determined a value for platform |
| .cpp | 1 | No rule determined a value for platform |
| .json | 1 | No rule determined a value for platform |
| .parquet | 1 | No rule determined a value for platform |

| Platform | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 600,676 | 79.2% | .vcf.gz (201,883)<br>.tbi (169,535)<br>.tar (124,372)<br>.csi (41,138)<br>.gz (7,451)<br>.bed.gz (7,231)<br>.bed (6,429)<br>.txt (4,863)<br>.hist (3,870)<br>.pdf (3,028)<br>.bam (2,960)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.bw (2,536)<br>.g.vcf.gz (2,504)<br>.bai (1,499)<br>.tsv (1,278)<br>.tar.gz (1,155)<br>.sizes (1,086)<br>.tex (940)<br>.tdf (860)<br>.vst (672)<br>.stats (659)<br>.vcf (646)<br>.qv (645)<br>.sf (634)<br>.gfa (598)<br>.html (510)<br>.sam.gz (474)<br>.counts (430)<br>.h5ad (352)<br>.idat (320)<br>.bb (272)<br>.count (215)<br>.cmap (210)<br>.bedpe (188)<br>.dat (94)<br>.superdups (86)<br>.ped (67)<br>.xmap (64)<br>.table (47)<br>(none) (40)<br>.csv (28)<br>.bgz (23)<br>.xg (16)<br>.gbwt (12)<br>.snarls (12)<br>.min (12)<br>.gg (12)<br>.dist (12)<br>.err (10)<br>.dict (9)<br>.stdout (8)<br>.m5 (8)<br>.smap (8)<br>.xlsx (7)<br>.errbin (6)<br>.bnx (6)<br>.maprate (6)<br>.md (6)<br>.bin (6)<br>.sam (5)<br>.r (5)<br>.indel (4)<br>.hal (4)<br>.xml (4)<br>.chimeric (4)<br>.gct (2)<br>.yak (2)<br>.scan (2)<br>.errbias3 (2)<br>.id (2)<br>.md5_fq (2)<br>.errbias1 (2)<br>.errbias2 (2)<br>.zip (2)<br>.out (2)<br>.errbias0 (2)<br>.reads_bam (2)<br>.chain (2)<br>.txt~ (1)<br>.fofn (1)<br>.snakefile (1)<br>.scfmap (1)<br>.docx (1)<br>.fna (1)<br>.py (1)<br>.0 (1)<br>.h5 (1)<br>.gtf (1)<br>.swp (1)<br>.cpp (1)<br>.json (1)<br>.parquet (1) |
| `not_applicable` | 94,698 | 12.5% | .txt (37,593)<br>.svs (25,708)<br>.md5 (15,565)<br>.png (8,049)<br>.log (5,066)<br>.fa.gz (1,633)<br>.fasta.gz (93)<br>.csi (48)<br>.fasta (37)<br>.pbi (32)<br>.fai (12)<br>.000014 (6)<br>.000021 (5)<br>.000022 (5)<br>.000034 (5)<br>.000033 (5)<br>.000032 (5)<br>.000024 (5)<br>.000036 (5)<br>.000044 (5)<br>.000013 (5)<br>.000035 (5)<br>.000028 (5)<br>.000045 (5)<br>.000016 (5)<br>.000010 (5)<br>.000030 (5)<br>.000039 (5)<br>.000023 (5)<br>.000006 (5)<br>.000037 (5)<br>.000043 (5)<br>.000038 (5)<br>.000004 (5)<br>.000020 (5)<br>.000008 (5)<br>.000017 (5)<br>.000011 (5)<br>.000029 (5)<br>.000041 (5)<br>.000002 (5)<br>.000007 (5)<br>.000031 (5)<br>.000015 (5)<br>.000012 (5)<br>.000003 (5)<br>.000005 (5)<br>.000019 (5)<br>.000025 (5)<br>.000026 (5)<br>.000018 (5)<br>.000009 (5)<br>.000042 (5)<br>.000000 (5)<br>.000001 (5)<br>.000040 (5)<br>.000056 (4)<br>.000073 (4)<br>.000079 (4)<br>.000048 (4)<br>.000077 (4)<br>.000081 (4)<br>.000068 (4)<br>.000054 (4)<br>.000046 (4)<br>.000069 (4)<br>.000065 (4)<br>.000050 (4)<br>.000055 (4)<br>.000078 (4)<br>.000083 (4)<br>.000027 (4)<br>.000060 (4)<br>.000071 (4)<br>.000053 (4)<br>.000057 (4)<br>.000061 (4)<br>.000067 (4)<br>.000063 (4)<br>.000064 (4)<br>.000075 (4)<br>.000070 (4)<br>.000051 (4)<br>.000072 (4)<br>.000058 (4)<br>.000062 (4)<br>.000059 (4)<br>.000074 (4)<br>.000047 (4)<br>.000085 (4)<br>.000082 (4)<br>.000076 (4)<br>.000052 (4)<br>.000066 (4)<br>.000049 (4)<br>.000080 (4)<br>.000092 (3)<br>.000113 (3)<br>.000108 (3)<br>.000115 (3)<br>.000124 (3)<br>.000126 (3)<br>.000118 (3)<br>.000099 (3)<br>.000104 (3)<br>.000086 (3)<br>.000090 (3)<br>.000111 (3)<br>.000093 (3)<br>.000127 (3)<br>.000116 (3)<br>.000088 (3)<br>.000120 (3)<br>.000096 (3)<br>.000101 (3)<br>.000125 (3)<br>.000123 (3)<br>.000102 (3)<br>.000119 (3)<br>.000109 (3)<br>.000084 (3)<br>.000122 (3)<br>.000091 (3)<br>.000114 (3)<br>.000089 (3)<br>.000117 (3)<br>.000097 (3)<br>.000087 (3)<br>.000105 (3)<br>.000106 (3)<br>.000112 (3)<br>.000098 (3)<br>.000095 (3)<br>.000107 (3)<br>.000103 (3)<br>.000094 (3)<br>.000121 (3)<br>.000100 (3)<br>.fa (2)<br>.000158 (2)<br>.000159 (2)<br>.000140 (2)<br>.000168 (2)<br>.000170 (2)<br>.000179 (2)<br>.bai (2)<br>.000166 (2)<br>.000129 (2)<br>.000164 (2)<br>.000110 (2)<br>.000135 (2)<br>.000150 (2)<br>.000138 (2)<br>.000180 (2)<br>.000143 (2)<br>.000173 (2)<br>.000171 (2)<br>.000141 (2)<br>.000152 (2)<br>.000139 (2)<br>.000177 (2)<br>.000157 (2)<br>.000156 (2)<br>.000147 (2)<br>.000148 (2)<br>.000132 (2)<br>.000174 (2)<br>.000142 (2)<br>.000130 (2)<br>.000133 (2)<br>.000136 (2)<br>.000137 (2)<br>.000165 (2)<br>.000134 (2)<br>.000169 (2)<br>.000154 (2)<br>.000178 (2)<br>.000145 (2)<br>.tbi (2)<br>.000163 (2)<br>.000128 (2)<br>.000144 (2)<br>.000172 (2)<br>.000176 (2)<br>.000131 (2)<br>.000155 (2)<br>.000161 (2)<br>.000149 (2)<br>.000153 (2)<br>.000162 (2)<br>.000146 (2)<br>.000167 (2)<br>.000151 (2)<br>.000175 (2)<br>.000265 (1)<br>.245537z (1)<br>.940364z (1)<br>.000328 (1)<br>.690977z (1)<br>.000292 (1)<br>.000270 (1)<br>.000195 (1)<br>.000218 (1)<br>.897209z (1)<br>.403914z (1)<br>.800260z (1)<br>.000232 (1)<br>.000274 (1)<br>.000313 (1)<br>.319905z (1)<br>.000299 (1)<br>.082165z (1)<br>.000203 (1)<br>.000324 (1)<br>.000326 (1)<br>.984990z (1)<br>.000160 (1)<br>.000193 (1)<br>.000184 (1)<br>.064718z (1)<br>.000238 (1)<br>.000307 (1)<br>.000295 (1)<br>.000316 (1)<br>.000318 (1)<br>.000185 (1)<br>.000235 (1)<br>.000209 (1)<br>.000822 (1)<br>.000305 (1)<br>.000327 (1)<br>.152454z (1)<br>.000271 (1)<br>.000246 (1)<br>.693904z (1)<br>.000304 (1)<br>.328584z (1)<br>.000293 (1)<br>.419574z (1)<br>.000260 (1)<br>.000214 (1)<br>.000331 (1)<br>.392375z (1)<br>.758552z (1)<br>.000206 (1)<br>.001142 (1)<br>.196093z (1)<br>.000288 (1)<br>.895704z (1)<br>.000256 (1)<br>.006944z (1)<br>.000320 (1)<br>.000230 (1)<br>.000647 (1)<br>.000332 (1)<br>.000207 (1)<br>.000220 (1)<br>.705621z (1)<br>.000202 (1)<br>.000939 (1)<br>.000198 (1)<br>.089663z (1)<br>.000311 (1)<br>.000212 (1)<br>.906471z (1)<br>.000257 (1)<br>.115119z (1)<br>.000216 (1)<br>.408558z (1)<br>.328107z (1)<br>.000233 (1)<br>.000241 (1)<br>.000280 (1)<br>.000301 (1)<br>.297614z (1)<br>.000315 (1)<br>.372846z (1)<br>.000253 (1)<br>.401447z (1)<br>.000285 (1)<br>.008290z (1)<br>.000204 (1)<br>.914044z (1)<br>.000273 (1)<br>.000263 (1)<br>.000196 (1)<br>.225115z (1)<br>.000289 (1)<br>.000262 (1)<br>.000242 (1)<br>.000222 (1)<br>.643111z (1)<br>.000239 (1)<br>.000200 (1)<br>.356527z (1)<br>.000199 (1)<br>.000334 (1)<br>.000225 (1)<br>.000254 (1)<br>.000197 (1)<br>.737407z (1)<br>.936487z (1)<br>.000259 (1)<br>.000247 (1)<br>.979322z (1)<br>.000234 (1)<br>.998860z (1)<br>.000217 (1)<br>.000264 (1)<br>.000237 (1)<br>.978368z (1)<br>.000279 (1)<br>.000211 (1)<br>.848693z (1)<br>.023047z (1)<br>.213071z (1)<br>.000226 (1)<br>.000297 (1)<br>.000255 (1)<br>.035388z (1)<br>.000224 (1)<br>.988120z (1)<br>.055644z (1)<br>.000258 (1)<br>.222181z (1)<br>.333014z (1)<br>.000267 (1)<br>.051074z (1)<br>.884243z (1)<br>.000251 (1)<br>.000243 (1)<br>.000223 (1)<br>.000215 (1)<br>.000308 (1)<br>.000227 (1)<br>.000286 (1)<br>.000277 (1)<br>.000278 (1)<br>.500269z (1)<br>.430624z (1)<br>.000268 (1)<br>.000189 (1)<br>.448782z (1)<br>.570463z (1)<br>.000329 (1)<br>.410201z (1)<br>.000221 (1)<br>.000972 (1)<br>.800472z (1)<br>.000231 (1)<br>.000321 (1)<br>.000323 (1)<br>.771515z (1)<br>.006029z (1)<br>.000269 (1)<br>.901353z (1)<br>.000294 (1)<br>.000281 (1)<br>.464162z (1)<br>.000298 (1)<br>.000314 (1)<br>.104091z (1)<br>.000322 (1)<br>.000236 (1)<br>.855151z (1)<br>.000186 (1)<br>.000201 (1)<br>.258028z (1)<br>.000219 (1)<br>.000302 (1)<br>.000261 (1)<br>.684033z (1)<br>.672091z (1)<br>.000187 (1)<br>.000250 (1)<br>.000191 (1)<br>.000336 (1)<br>.000283 (1)<br>.000284 (1)<br>.000248 (1)<br>.000249 (1)<br>.000245 (1)<br>.000266 (1)<br>.000240 (1)<br>.000303 (1)<br>.169365z (1)<br>.546615z (1)<br>.921606z (1)<br>.000229 (1)<br>.220190z (1)<br>.000252 (1)<br>.169559z (1)<br>.000190 (1)<br>.000296 (1)<br>.000188 (1)<br>.000182 (1)<br>.000291 (1)<br>.000330 (1)<br>.000213 (1)<br>.960061z (1)<br>.000317 (1)<br>.000244 (1)<br>.968554z (1)<br>.613426z (1)<br>.000205 (1)<br>.871149z (1)<br>.000210 (1)<br>.000272 (1)<br>.000183 (1)<br>.000192 (1)<br>.000310 (1)<br>.102850z (1)<br>.000208 (1)<br>.000290 (1)<br>.000276 (1)<br>.000287 (1)<br>.759786z (1)<br>.278222z (1)<br>.288628z (1)<br>.000319 (1)<br>.000312 (1)<br>.337209z (1)<br>.000282 (1)<br>.000275 (1)<br>.000228 (1)<br>.067517z (1)<br>.000194 (1)<br>.000309 (1)<br>.000300 (1)<br>.796966z (1)<br>.000306 (1)<br>.000181 (1) |
| `ILLUMINA` | 41,776 | 5.5% | .fastq.gz (20,628)<br>.cram (10,829)<br>.crai (10,319) |
| `ONT` | 15,556 | 2.1% | .fast5 (12,394)<br>.bam (1,509)<br>.fastq.gz (1,278)<br>.fast5.tar (273)<br>.bai (65)<br>.fast5.tar.gz (26)<br>.pod5 (11) |
| `PACBIO` | 5,951 | 0.8% | .bam (3,364)<br>.fastq.gz (1,134)<br>.pbi (1,102)<br>.bai (295)<br>.fastq (56) |

**Note**: Platform is inherently unknowable for most derived formats (VCF, BED, PLINK). Only BAM/CRAM (via `@RG PL` header) and FASTQ (via read name patterns) can encode platform. The high not-classified rate is expected.

---

## Assay Type

| | count | % |
|---|---:|---:|
| **Classified** | 141,230 | 18.6% |
| **Not classified** | 617,427 | 81.4% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf.gz | 201,883 | No rule determined a value for assay_type |
| .tbi | 169,523 | Parent file had no value for assay_type |
| .tar | 124,372 | No rule determined a value for assay_type |
| .csi | 41,138 | Parent file had no value for assay_type |
| .fastq.gz | 20,621 | No rule determined a value for assay_type |
| .gz | 7,451 | No rule determined a value for assay_type |
| .bed.gz | 7,191 | No rule determined a value for assay_type |
| .bed | 6,429 | No rule determined a value for assay_type |
| .txt | 4,584 | No rule determined a value for assay_type |
| .hist | 3,870 | No rule determined a value for assay_type |
| .pdf | 3,028 | No rule determined a value for assay_type |
| .pgen | 2,854 | No rule determined a value for assay_type |
| .pvar | 2,854 | No rule determined a value for assay_type |
| .psam | 2,854 | No rule determined a value for assay_type |
| .bw | 2,520 | No rule determined a value for assay_type |
| .g.vcf.gz | 2,504 | No rule determined a value for assay_type |
| .tsv | 1,278 | No rule determined a value for assay_type |
| .bam | 1,215 | No rule determined a value for assay_type |
| .tar.gz | 1,155 | No rule determined a value for assay_type |
| .sizes | 1,086 | No rule determined a value for assay_type |
| .tex | 940 | No rule determined a value for assay_type |
| .tdf | 860 | No rule determined a value for assay_type |
| .vst | 672 | No rule determined a value for assay_type |
| .stats | 659 | No rule determined a value for assay_type |
| .vcf | 646 | No rule determined a value for assay_type |
| .qv | 645 | No rule determined a value for assay_type |
| .sf | 634 | No rule determined a value for assay_type |
| .gfa | 598 | No rule determined a value for assay_type |
| .html | 510 | No rule determined a value for assay_type |
| .sam.gz | 474 | No rule determined a value for assay_type |
| .counts | 430 | No rule determined a value for assay_type |
| .bai | 397 | Parent file had no value for assay_type |
| .bb | 272 | No rule determined a value for assay_type |
| .count | 215 | No rule determined a value for assay_type |
| .cmap | 210 | No rule determined a value for assay_type |
| .bedpe | 188 | No rule determined a value for assay_type |
| .dat | 94 | No rule determined a value for assay_type |
| .superdups | 86 | No rule determined a value for assay_type |
| .ped | 67 | No rule determined a value for assay_type |
| .xmap | 64 | No rule determined a value for assay_type |
| .table | 47 | No rule determined a value for assay_type |
| (none) | 40 | No rule determined a value for assay_type |
| .csv | 25 | No rule determined a value for assay_type |
| .bgz | 23 | No rule determined a value for assay_type |
| .xg | 16 | No rule determined a value for assay_type |
| .gbwt | 12 | No rule determined a value for assay_type |
| .snarls | 12 | No rule determined a value for assay_type |
| .min | 12 | No rule determined a value for assay_type |
| .gg | 12 | No rule determined a value for assay_type |
| .dist | 12 | No rule determined a value for assay_type |
| .err | 10 | No rule determined a value for assay_type |
| .dict | 9 | No rule determined a value for assay_type |
| .stdout | 8 | No rule determined a value for assay_type |
| .m5 | 8 | No rule determined a value for assay_type |
| .smap | 8 | No rule determined a value for assay_type |
| .xlsx | 7 | No rule determined a value for assay_type |
| .errbin | 6 | No rule determined a value for assay_type |
| .bnx | 6 | No rule determined a value for assay_type |
| .maprate | 6 | No rule determined a value for assay_type |
| .md | 6 | No rule determined a value for assay_type |
| .bin | 6 | No rule determined a value for assay_type |
| .r | 5 | No rule determined a value for assay_type |
| .indel | 4 | No rule determined a value for assay_type |
| .hal | 4 | No rule determined a value for assay_type |
| .xml | 4 | No rule determined a value for assay_type |
| .chimeric | 4 | No rule determined a value for assay_type |
| .sam | 4 | No rule determined a value for assay_type |
| .gct | 2 | No rule determined a value for assay_type |
| .yak | 2 | No rule determined a value for assay_type |
| .scan | 2 | No rule determined a value for assay_type |
| .errbias3 | 2 | No rule determined a value for assay_type |
| .id | 2 | No rule determined a value for assay_type |
| .md5_fq | 2 | No rule determined a value for assay_type |
| .errbias1 | 2 | No rule determined a value for assay_type |
| .errbias2 | 2 | No rule determined a value for assay_type |
| .zip | 2 | No rule determined a value for assay_type |
| .out | 2 | No rule determined a value for assay_type |
| .errbias0 | 2 | No rule determined a value for assay_type |
| .reads_bam | 2 | No rule determined a value for assay_type |
| .chain | 2 | No rule determined a value for assay_type |
| .txt~ | 1 | No rule determined a value for assay_type |
| .fofn | 1 | No rule determined a value for assay_type |
| .snakefile | 1 | No rule determined a value for assay_type |
| .scfmap | 1 | No rule determined a value for assay_type |
| .docx | 1 | No rule determined a value for assay_type |
| .fna | 1 | No rule determined a value for assay_type |
| .py | 1 | No rule determined a value for assay_type |
| .0 | 1 | No rule determined a value for assay_type |
| .h5 | 1 | No rule determined a value for assay_type |
| .gtf | 1 | No rule determined a value for assay_type |
| .swp | 1 | No rule determined a value for assay_type |
| .cpp | 1 | No rule determined a value for assay_type |
| .json | 1 | No rule determined a value for assay_type |
| .parquet | 1 | No rule determined a value for assay_type |

| Assay Type | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 617,427 | 81.4% | .vcf.gz (201,883)<br>.tbi (169,523)<br>.tar (124,372)<br>.csi (41,138)<br>.fastq.gz (20,621)<br>.gz (7,451)<br>.bed.gz (7,191)<br>.bed (6,429)<br>.txt (4,584)<br>.hist (3,870)<br>.pdf (3,028)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.bw (2,520)<br>.g.vcf.gz (2,504)<br>.tsv (1,278)<br>.bam (1,215)<br>.tar.gz (1,155)<br>.sizes (1,086)<br>.tex (940)<br>.tdf (860)<br>.vst (672)<br>.stats (659)<br>.vcf (646)<br>.qv (645)<br>.sf (634)<br>.gfa (598)<br>.html (510)<br>.sam.gz (474)<br>.counts (430)<br>.bai (397)<br>.bb (272)<br>.count (215)<br>.cmap (210)<br>.bedpe (188)<br>.dat (94)<br>.superdups (86)<br>.ped (67)<br>.xmap (64)<br>.table (47)<br>(none) (40)<br>.csv (25)<br>.bgz (23)<br>.xg (16)<br>.gbwt (12)<br>.snarls (12)<br>.min (12)<br>.gg (12)<br>.dist (12)<br>.err (10)<br>.dict (9)<br>.stdout (8)<br>.m5 (8)<br>.smap (8)<br>.xlsx (7)<br>.errbin (6)<br>.bnx (6)<br>.maprate (6)<br>.md (6)<br>.bin (6)<br>.r (5)<br>.indel (4)<br>.hal (4)<br>.xml (4)<br>.chimeric (4)<br>.sam (4)<br>.gct (2)<br>.yak (2)<br>.scan (2)<br>.errbias3 (2)<br>.id (2)<br>.md5_fq (2)<br>.errbias1 (2)<br>.errbias2 (2)<br>.zip (2)<br>.out (2)<br>.errbias0 (2)<br>.reads_bam (2)<br>.chain (2)<br>.txt~ (1)<br>.fofn (1)<br>.snakefile (1)<br>.scfmap (1)<br>.docx (1)<br>.fna (1)<br>.py (1)<br>.0 (1)<br>.h5 (1)<br>.gtf (1)<br>.swp (1)<br>.cpp (1)<br>.json (1)<br>.parquet (1) |
| `not_applicable` | 68,990 | 9.1% | .txt (37,593)<br>.md5 (15,565)<br>.png (8,049)<br>.log (5,066)<br>.fa.gz (1,633)<br>.fasta.gz (93)<br>.csi (48)<br>.fasta (37)<br>.pbi (32)<br>.fai (12)<br>.000014 (6)<br>.000021 (5)<br>.000022 (5)<br>.000034 (5)<br>.000033 (5)<br>.000032 (5)<br>.000024 (5)<br>.000036 (5)<br>.000044 (5)<br>.000013 (5)<br>.000035 (5)<br>.000028 (5)<br>.000045 (5)<br>.000016 (5)<br>.000010 (5)<br>.000030 (5)<br>.000039 (5)<br>.000023 (5)<br>.000006 (5)<br>.000037 (5)<br>.000043 (5)<br>.000038 (5)<br>.000004 (5)<br>.000020 (5)<br>.000008 (5)<br>.000017 (5)<br>.000011 (5)<br>.000029 (5)<br>.000041 (5)<br>.000002 (5)<br>.000007 (5)<br>.000031 (5)<br>.000015 (5)<br>.000012 (5)<br>.000003 (5)<br>.000005 (5)<br>.000019 (5)<br>.000025 (5)<br>.000026 (5)<br>.000018 (5)<br>.000009 (5)<br>.000042 (5)<br>.000000 (5)<br>.000001 (5)<br>.000040 (5)<br>.000056 (4)<br>.000073 (4)<br>.000079 (4)<br>.000048 (4)<br>.000077 (4)<br>.000081 (4)<br>.000068 (4)<br>.000054 (4)<br>.000046 (4)<br>.000069 (4)<br>.000065 (4)<br>.000050 (4)<br>.000055 (4)<br>.000078 (4)<br>.000083 (4)<br>.000027 (4)<br>.000060 (4)<br>.000071 (4)<br>.000053 (4)<br>.000057 (4)<br>.000061 (4)<br>.000067 (4)<br>.000063 (4)<br>.000064 (4)<br>.000075 (4)<br>.000070 (4)<br>.000051 (4)<br>.000072 (4)<br>.000058 (4)<br>.000062 (4)<br>.000059 (4)<br>.000074 (4)<br>.000047 (4)<br>.000085 (4)<br>.000082 (4)<br>.000076 (4)<br>.000052 (4)<br>.000066 (4)<br>.000049 (4)<br>.000080 (4)<br>.000092 (3)<br>.000113 (3)<br>.000108 (3)<br>.000115 (3)<br>.000124 (3)<br>.000126 (3)<br>.000118 (3)<br>.000099 (3)<br>.000104 (3)<br>.000086 (3)<br>.000090 (3)<br>.000111 (3)<br>.000093 (3)<br>.000127 (3)<br>.000116 (3)<br>.000088 (3)<br>.000120 (3)<br>.000096 (3)<br>.000101 (3)<br>.000125 (3)<br>.000123 (3)<br>.000102 (3)<br>.000119 (3)<br>.000109 (3)<br>.000084 (3)<br>.000122 (3)<br>.000091 (3)<br>.000114 (3)<br>.000089 (3)<br>.000117 (3)<br>.000097 (3)<br>.000087 (3)<br>.000105 (3)<br>.000106 (3)<br>.000112 (3)<br>.000098 (3)<br>.000095 (3)<br>.000107 (3)<br>.000103 (3)<br>.000094 (3)<br>.000121 (3)<br>.000100 (3)<br>.fa (2)<br>.000158 (2)<br>.000159 (2)<br>.000140 (2)<br>.000168 (2)<br>.000170 (2)<br>.000179 (2)<br>.bai (2)<br>.000166 (2)<br>.000129 (2)<br>.000164 (2)<br>.000110 (2)<br>.000135 (2)<br>.000150 (2)<br>.000138 (2)<br>.000180 (2)<br>.000143 (2)<br>.000173 (2)<br>.000171 (2)<br>.000141 (2)<br>.000152 (2)<br>.000139 (2)<br>.000177 (2)<br>.000157 (2)<br>.000156 (2)<br>.000147 (2)<br>.000148 (2)<br>.000132 (2)<br>.000174 (2)<br>.000142 (2)<br>.000130 (2)<br>.000133 (2)<br>.000136 (2)<br>.000137 (2)<br>.000165 (2)<br>.000134 (2)<br>.000169 (2)<br>.000154 (2)<br>.000178 (2)<br>.000145 (2)<br>.tbi (2)<br>.000163 (2)<br>.000128 (2)<br>.000144 (2)<br>.000172 (2)<br>.000176 (2)<br>.000131 (2)<br>.000155 (2)<br>.000161 (2)<br>.000149 (2)<br>.000153 (2)<br>.000162 (2)<br>.000146 (2)<br>.000167 (2)<br>.000151 (2)<br>.000175 (2)<br>.000265 (1)<br>.245537z (1)<br>.940364z (1)<br>.000328 (1)<br>.690977z (1)<br>.000292 (1)<br>.000270 (1)<br>.000195 (1)<br>.000218 (1)<br>.897209z (1)<br>.403914z (1)<br>.800260z (1)<br>.000232 (1)<br>.000274 (1)<br>.000313 (1)<br>.319905z (1)<br>.000299 (1)<br>.082165z (1)<br>.000203 (1)<br>.000324 (1)<br>.000326 (1)<br>.984990z (1)<br>.000160 (1)<br>.000193 (1)<br>.000184 (1)<br>.064718z (1)<br>.000238 (1)<br>.000307 (1)<br>.000295 (1)<br>.000316 (1)<br>.000318 (1)<br>.000185 (1)<br>.000235 (1)<br>.000209 (1)<br>.000822 (1)<br>.000305 (1)<br>.000327 (1)<br>.152454z (1)<br>.000271 (1)<br>.000246 (1)<br>.693904z (1)<br>.000304 (1)<br>.328584z (1)<br>.000293 (1)<br>.419574z (1)<br>.000260 (1)<br>.000214 (1)<br>.000331 (1)<br>.392375z (1)<br>.758552z (1)<br>.000206 (1)<br>.001142 (1)<br>.196093z (1)<br>.000288 (1)<br>.895704z (1)<br>.000256 (1)<br>.006944z (1)<br>.000320 (1)<br>.000230 (1)<br>.000647 (1)<br>.000332 (1)<br>.000207 (1)<br>.000220 (1)<br>.705621z (1)<br>.000202 (1)<br>.000939 (1)<br>.000198 (1)<br>.089663z (1)<br>.000311 (1)<br>.000212 (1)<br>.906471z (1)<br>.000257 (1)<br>.115119z (1)<br>.000216 (1)<br>.408558z (1)<br>.328107z (1)<br>.000233 (1)<br>.000241 (1)<br>.000280 (1)<br>.000301 (1)<br>.297614z (1)<br>.000315 (1)<br>.372846z (1)<br>.000253 (1)<br>.401447z (1)<br>.000285 (1)<br>.008290z (1)<br>.000204 (1)<br>.914044z (1)<br>.000273 (1)<br>.000263 (1)<br>.000196 (1)<br>.225115z (1)<br>.000289 (1)<br>.000262 (1)<br>.000242 (1)<br>.000222 (1)<br>.643111z (1)<br>.000239 (1)<br>.000200 (1)<br>.356527z (1)<br>.000199 (1)<br>.000334 (1)<br>.000225 (1)<br>.000254 (1)<br>.000197 (1)<br>.737407z (1)<br>.936487z (1)<br>.000259 (1)<br>.000247 (1)<br>.979322z (1)<br>.000234 (1)<br>.998860z (1)<br>.000217 (1)<br>.000264 (1)<br>.000237 (1)<br>.978368z (1)<br>.000279 (1)<br>.000211 (1)<br>.848693z (1)<br>.023047z (1)<br>.213071z (1)<br>.000226 (1)<br>.000297 (1)<br>.000255 (1)<br>.035388z (1)<br>.000224 (1)<br>.988120z (1)<br>.055644z (1)<br>.000258 (1)<br>.222181z (1)<br>.333014z (1)<br>.000267 (1)<br>.051074z (1)<br>.884243z (1)<br>.000251 (1)<br>.000243 (1)<br>.000223 (1)<br>.000215 (1)<br>.000308 (1)<br>.000227 (1)<br>.000286 (1)<br>.000277 (1)<br>.000278 (1)<br>.500269z (1)<br>.430624z (1)<br>.000268 (1)<br>.000189 (1)<br>.448782z (1)<br>.570463z (1)<br>.000329 (1)<br>.410201z (1)<br>.000221 (1)<br>.000972 (1)<br>.800472z (1)<br>.000231 (1)<br>.000321 (1)<br>.000323 (1)<br>.771515z (1)<br>.006029z (1)<br>.000269 (1)<br>.901353z (1)<br>.000294 (1)<br>.000281 (1)<br>.464162z (1)<br>.000298 (1)<br>.000314 (1)<br>.104091z (1)<br>.000322 (1)<br>.000236 (1)<br>.855151z (1)<br>.000186 (1)<br>.000201 (1)<br>.258028z (1)<br>.000219 (1)<br>.000302 (1)<br>.000261 (1)<br>.684033z (1)<br>.672091z (1)<br>.000187 (1)<br>.000250 (1)<br>.000191 (1)<br>.000336 (1)<br>.000283 (1)<br>.000284 (1)<br>.000248 (1)<br>.000249 (1)<br>.000245 (1)<br>.000266 (1)<br>.000240 (1)<br>.000303 (1)<br>.169365z (1)<br>.546615z (1)<br>.921606z (1)<br>.000229 (1)<br>.220190z (1)<br>.000252 (1)<br>.169559z (1)<br>.000190 (1)<br>.000296 (1)<br>.000188 (1)<br>.000182 (1)<br>.000291 (1)<br>.000330 (1)<br>.000213 (1)<br>.960061z (1)<br>.000317 (1)<br>.000244 (1)<br>.968554z (1)<br>.613426z (1)<br>.000205 (1)<br>.871149z (1)<br>.000210 (1)<br>.000272 (1)<br>.000183 (1)<br>.000192 (1)<br>.000310 (1)<br>.102850z (1)<br>.000208 (1)<br>.000290 (1)<br>.000276 (1)<br>.000287 (1)<br>.759786z (1)<br>.278222z (1)<br>.288628z (1)<br>.000319 (1)<br>.000312 (1)<br>.337209z (1)<br>.000282 (1)<br>.000275 (1)<br>.000228 (1)<br>.067517z (1)<br>.000194 (1)<br>.000309 (1)<br>.000300 (1)<br>.796966z (1)<br>.000306 (1)<br>.000181 (1) |
| `WGS` | 43,306 | 5.7% | .fast5 (12,394)<br>.cram (10,824)<br>.crai (10,319)<br>.bam (5,205)<br>.fastq.gz (2,412)<br>.pbi (1,102)<br>.bai (683)<br>.fast5.tar (273)<br>.fastq (56)<br>.fast5.tar.gz (26)<br>.pod5 (11)<br>.sam (1) |
| `Histology` | 25,708 | 3.4% | .svs (25,708) |
| `RNA-seq` | 2,867 | 0.4% | .bam (1,413)<br>.bai (779)<br>.h5ad (352)<br>.txt (279)<br>.bw (16)<br>.bed.gz (12)<br>.tbi (12)<br>.csv (3)<br>.fastq.gz (1) |
| `Methylation array` | 320 | 0.0% | .idat (320) |
| `Bisulfite-seq` | 28 | 0.0% | .bed.gz (28) |
| `ATAC-seq` | 6 | 0.0% | .fastq.gz (6) |
| `WES` | 5 | 0.0% | .cram (5) |

**Note**: Like platform, assay type is inherently unknowable for most derived formats. Only BAM/CRAM (via `@PG` programs and file size heuristics) and filename patterns can determine assay. The high not-classified rate is expected.

