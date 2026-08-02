# AnVIL Classification Coverage Report

Classification run: **2026-08-02 17:08:26**

Source: **733,877** files across **13** open-access datasets on [explore.anvilproject.org](https://explore.anvilproject.org/).
Processed **733,992** files.

- ANVIL_T2T_CHRY (309,979 files)
- ANVIL_T2T (289,204 files)
- ANVIL_1000G_high_coverage_2019 (26,016 files)
- ANVIL_GTEx_public_data (25,789 files)
- ANVIL_HPRC (23,185 files)
- AnVIL_HPRC_R2 (16,271 files)
- ANVIL_NIA_CARD_Coriell_Cell_Lines_Open (12,534 files)
- ANVIL_1000G_PRIMED_data_model (11,493 files)
- AnVIL_IGVF_Mouse_R1 (6,786 files)
- AnVIL_ENCORE_RS293 (3,752 files)
- ANVIL_nhp_dGTEx_V1 (3,591 files)
- AnVIL_MAGE (3,285 files)
- AnVIL_ENCORE_293T (1,992 files)

**Classified** includes all files with a determined value, including `not_applicable` (e.g., FASTQ files have no reference assembly). **Not classified** means no rule or signal could determine a value.

| Dimension | Classified | Not Classified |
|---|---:|---:|
| **Data Modality** | 676,842 (92.2%) | 57,150 (7.8%) |
| **Data Type** | 708,212 (96.5%) | 25,780 (3.5%) |
| **Reference Assembly** | 552,365 (75.3%) | 181,627 (24.7%) |
| **Platform** | 158,110 (21.5%) | 575,882 (78.5%) |
| **Assay Type** | 128,778 (17.5%) | 605,214 (82.5%) |

---

## Data Modality

| | count | % |
|---|---:|---:|
| **Classified** | 676,842 | 92.2% |
| **Not classified** | 57,150 | 7.8% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .fastq | 21,269 | FASTQ modality cannot be determined from reads alone — could be genomic, transcriptomic, or epigenomic depending on assay |
| (none) | 13,872 | No rule determined a value for data_modality |
| .fast5 | 12,624 | No rule determined a value for data_modality |
| .txt | 4,674 | No rule determined a value for data_modality |
| .bw | 2,520 | No rule determined a value for data_modality |
| .tsv | 924 | No rule determined a value for data_modality |
| .bigwig | 462 | No rule determined a value for data_modality |
| .bam | 345 | No rule determined a value for data_modality |
| .sam | 192 | No rule determined a value for data_modality |
| .cram | 68 | No rule determined a value for data_modality |
| .crai | 68 | Parent file had no value for data_modality |
| .tbi | 60 | Parent file had no value for data_modality |
| .vcf | 23 | no VCF header lines (no '#' lines) in the read head |
| .csv | 20 | No rule determined a value for data_modality |
| .pod5 | 11 | No rule determined a value for data_modality |
| .bai | 11 | Parent file had no value for data_modality |
| .pbi | 7 | Parent file had no value for data_modality |

| Data Modality | count | % | extensions |
|---|---:|---:|---|
| `genomic` | 586,752 | 79.9% | .vcf (201,645)<br>.tbi (169,457)<br>(none) (124,475)<br>.csi (41,138)<br>.bed (11,483)<br>.cram (10,555)<br>.crai (10,249)<br>.bam (4,100)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.g.vcf (2,504)<br>.bai (1,264)<br>.fa (940)<br>.gfa (326)<br>.fasta (38)<br>.xg (8)<br>.gbwt (6)<br>.gbz (2) |
| `not_applicable` | 59,021 | 8.0% | .txt (37,548)<br>.md5 (14,233)<br>.log (3,637)<br>.png (3,074)<br>.fai (477)<br>.csi (48)<br>.bai (2)<br>.tbi (2) |
| `not_classified` | 57,150 | 7.8% | .fastq (21,269)<br>(none) (13,872)<br>.fast5 (12,624)<br>.txt (4,674)<br>.bw (2,520)<br>.tsv (924)<br>.bigwig (462)<br>.bam (345)<br>.sam (192)<br>.cram (68)<br>.crai (68)<br>.tbi (60)<br>.vcf (23)<br>.csv (20)<br>.pod5 (11)<br>.bai (11)<br>.pbi (7) |
| `imaging.histology` | 25,708 | 3.5% | .svs (25,708) |
| `transcriptomic.bulk` | 4,756 | 0.6% | .bam (2,329)<br>.bai (1,465)<br>.sf (634)<br>.txt (285)<br>.bw (16)<br>.bed (12)<br>.tbi (12)<br>.csv (3) |
| `transcriptomic.single_cell` | 417 | 0.1% | .h5ad (352)<br>(none) (64)<br>.fastq (1) |
| `epigenomic.methylation` | 188 | 0.0% | .idat (160)<br>.bed (28) |

---

## Data Type

| | count | % |
|---|---:|---:|
| **Classified** | 708,212 | 96.5% |
| **Not classified** | 25,780 | 3.5% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| (none) | 13,870 | No rule determined a value for data_type |
| .txt | 4,674 | No rule determined a value for data_type |
| .bw | 2,520 | No rule determined a value for data_type |
| .bam | 1,805 | No rule determined a value for data_type |
| .bai | 1,087 | Parent file had no value for data_type |
| .tsv | 924 | No rule determined a value for data_type |
| .bigwig | 462 | No rule determined a value for data_type |
| .sam | 192 | No rule determined a value for data_type |
| .cram | 68 | No rule determined a value for data_type |
| .crai | 68 | Parent file had no value for data_type |
| .tbi | 60 | Parent file had no value for data_type |
| .vcf | 23 | no VCF header lines (no '#' lines) in the read head |
| .csv | 20 | No rule determined a value for data_type |
| .pbi | 7 | Parent file had no value for data_type |

| Data Type | count | % | extensions |
|---|---:|---:|---|
| `variants.germline` | 331,250 | 45.1% | .vcf (165,625)<br>.tbi (165,625) |
| `variants` | 200,612 | 27.3% | (none) (124,335)<br>.vcf (35,828)<br>.csi (34,141)<br>.tbi (3,804)<br>.g.vcf (2,504) |
| `not_applicable` | 55,947 | 7.6% | .txt (37,548)<br>.md5 (14,233)<br>.log (3,637)<br>.fai (477)<br>.csi (48)<br>.bai (2)<br>.tbi (2) |
| `images` | 28,782 | 3.9% | .svs (25,708)<br>.png (3,074) |
| `alignments` | 27,426 | 3.7% | .cram (10,555)<br>.crai (10,249)<br>.bam (4,969)<br>.bai (1,653) |
| `not_classified` | 25,780 | 3.5% | (none) (13,870)<br>.txt (4,674)<br>.bw (2,520)<br>.bam (1,805)<br>.bai (1,087)<br>.tsv (924)<br>.bigwig (462)<br>.sam (192)<br>.cram (68)<br>.crai (68)<br>.tbi (60)<br>.vcf (23)<br>.csv (20)<br>.pbi (7) |
| `reads` | 21,270 | 2.9% | .fastq (21,270) |
| `annotations` | 18,539 | 2.5% | .bed (11,523)<br>.csi (6,997)<br>.tbi (14)<br>(none) (5) |
| `raw_signal` | 12,637 | 1.7% | .fast5 (12,624)<br>.pod5 (11)<br>(none) (2) |
| `genotypes` | 8,562 | 1.2% | .pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854) |
| `assembly` | 961 | 0.1% | .fa (936)<br>.fasta (25) |
| `expression_matrix` | 704 | 0.1% | .h5ad (352)<br>.txt (285)<br>(none) (64)<br>.csv (3) |
| `quantification` | 634 | 0.1% | .sf (634) |
| `pangenome` | 449 | 0.1% | .gfa (314)<br>(none) (135) |
| `variants.structural` | 218 | 0.0% | .vcf (192)<br>.tbi (26) |
| `array_signal` | 160 | 0.0% | .idat (160) |
| `pangenome.reference` | 28 | 0.0% | .gfa (12)<br>.xg (8)<br>.gbwt (6)<br>.gbz (2) |
| `sequence` | 17 | 0.0% | .fasta (13)<br>.fa (4) |
| `signal` | 16 | 0.0% | .bw (16) |

---

## Reference Assembly

| | count | % |
|---|---:|---:|
| **Classified** | 552,365 | 75.3% |
| **Not classified** | 181,627 | 24.7% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| (none) | 137,249 | No rule determined a value for reference_assembly |
| .txt | 37,141 | No rule determined a value for reference_assembly |
| .bw | 2,536 | No rule determined a value for reference_assembly |
| .bam | 688 | No rule determined a value for reference_assembly |
| .bai | 688 | Parent file had no value for reference_assembly |
| .sf | 634 | No rule determined a value for reference_assembly |
| .fai | 467 | No rule determined a value for reference_assembly |
| .bigwig | 462 | No rule determined a value for reference_assembly |
| .tsv | 444 | No rule determined a value for reference_assembly |
| .h5ad | 352 | No rule determined a value for reference_assembly |
| .gfa | 314 | No rule determined a value for reference_assembly |
| .sam | 192 | No rule determined a value for reference_assembly |
| .idat | 160 | No rule determined a value for reference_assembly |
| .tbi | 71 | Parent file had no value for reference_assembly |
| .cram | 68 | No rule determined a value for reference_assembly |
| .crai | 68 | Parent file had no value for reference_assembly |
| .bed | 37 | No rule determined a value for reference_assembly |
| .vcf | 28 | no VCF header lines (no '#' lines) in the read head |
| .csv | 23 | No rule determined a value for reference_assembly |
| .fasta | 3 | No rule determined a value for reference_assembly |
| .xg | 2 | Filename contains GRCh38/hg38 reference indicator |

| Reference Assembly | count | % | extensions |
|---|---:|---:|---|
| `CHM13` | 419,209 | 57.1% | .vcf (192,420)<br>.tbi (159,186)<br>.csi (39,914)<br>.bed (6,744)<br>.cram (6,718)<br>.crai (6,715)<br>.txt (5,170)<br>.bam (632)<br>.bai (632)<br>(none) (579)<br>.tsv (470)<br>.fasta (7)<br>.gfa (6)<br>.fai (6)<br>.fa (3)<br>.gbwt (3)<br>.xg (3)<br>.gbz (1) |
| `not_classified` | 181,627 | 24.7% | (none) (137,249)<br>.txt (37,141)<br>.bw (2,536)<br>.bam (688)<br>.bai (688)<br>.sf (634)<br>.fai (467)<br>.bigwig (462)<br>.tsv (444)<br>.h5ad (352)<br>.gfa (314)<br>.sam (192)<br>.idat (160)<br>.tbi (71)<br>.cram (68)<br>.crai (68)<br>.bed (37)<br>.vcf (28)<br>.csv (23)<br>.fasta (3)<br>.xg (2) |
| `not_applicable` | 88,571 | 12.1% | .svs (25,708)<br>.fastq (21,270)<br>.md5 (14,233)<br>.fast5 (12,624)<br>.bed (3,922)<br>.log (3,637)<br>.bam (3,113)<br>.png (3,074)<br>.fa (936)<br>.fasta (25)<br>.pod5 (11)<br>.bai (11)<br>.pbi (7) |
| `GRCh38` | 44,571 | 6.1% | .tbi (10,274)<br>.vcf (9,209)<br>.cram (3,837)<br>.crai (3,534)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.g.vcf (2,504)<br>.bam (2,341)<br>.bai (1,411)<br>.csi (1,272)<br>.bed (817)<br>(none) (583)<br>.txt (196)<br>.tsv (10)<br>.gfa (6)<br>.fai (4)<br>.fasta (3)<br>.gbwt (3)<br>.xg (3)<br>.fa (1)<br>.gbz (1) |
| `GRCh37` | 14 | 0.0% | .vcf (11)<br>.bed (3) |

---

## Platform

| | count | % |
|---|---:|---:|
| **Classified** | 158,110 | 21.5% |
| **Not classified** | 575,882 | 78.5% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf | 201,668 | No rule determined a value for platform |
| .tbi | 169,529 | Parent file had no value for platform |
| (none) | 138,411 | No rule determined a value for platform |
| .csi | 34,141 | Parent file had no value for platform |
| .txt | 4,959 | No rule determined a value for platform |
| .bed | 4,432 | No rule determined a value for platform |
| .bam | 3,664 | No rule determined a value for platform |
| .pgen | 2,854 | No rule determined a value for platform |
| .pvar | 2,854 | No rule determined a value for platform |
| .psam | 2,854 | No rule determined a value for platform |
| .bai | 2,729 | Parent file had no value for platform |
| .bw | 2,536 | No rule determined a value for platform |
| .g.vcf | 2,504 | No rule determined a value for platform |
| .tsv | 924 | No rule determined a value for platform |
| .sf | 634 | No rule determined a value for platform |
| .bigwig | 462 | No rule determined a value for platform |
| .h5ad | 352 | No rule determined a value for platform |
| .sam | 192 | No rule determined a value for platform |
| .idat | 160 | No rule determined a value for platform |
| .csv | 23 | No rule determined a value for platform |

| Platform | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 575,882 | 78.5% | .vcf (201,668)<br>.tbi (169,529)<br>(none) (138,411)<br>.csi (34,141)<br>.txt (4,959)<br>.bed (4,432)<br>.bam (3,664)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.bai (2,729)<br>.bw (2,536)<br>.g.vcf (2,504)<br>.tsv (924)<br>.sf (634)<br>.bigwig (462)<br>.h5ad (352)<br>.sam (192)<br>.idat (160)<br>.csv (23) |
| `not_applicable` | 100,137 | 13.6% | .txt (37,548)<br>.svs (25,708)<br>.md5 (14,233)<br>.bed (7,091)<br>.csi (7,045)<br>.log (3,637)<br>.png (3,074)<br>.fa (940)<br>.fai (477)<br>.gfa (326)<br>.fasta (38)<br>.xg (8)<br>.gbwt (6)<br>.bai (2)<br>.tbi (2)<br>.gbz (2) |
| `ILLUMINA` | 41,106 | 5.6% | .fastq (20,166)<br>.cram (10,623)<br>.crai (10,317) |
| `ONT` | 14,072 | 1.9% | .fast5 (12,624)<br>.bam (1,300)<br>.fastq (137)<br>.pod5 (11) |
| `PACBIO` | 2,795 | 0.4% | .bam (1,810)<br>.fastq (967)<br>.bai (11)<br>.pbi (7) |

**Note**: Platform is inherently unknowable for most derived formats (VCF, BED, PLINK). Only BAM/CRAM (via `@RG PL` header) and FASTQ (via read name patterns) can encode platform. The high not-classified rate is expected.

---

## Assay Type

| | count | % |
|---|---:|---:|
| **Classified** | 128,778 | 17.5% |
| **Not classified** | 605,214 | 82.5% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf | 201,668 | No rule determined a value for assay_type |
| .tbi | 169,517 | Parent file had no value for assay_type |
| (none) | 138,411 | No rule determined a value for assay_type |
| .csi | 34,141 | Parent file had no value for assay_type |
| .fastq | 21,269 | No rule determined a value for assay_type |
| .fast5 | 12,624 | No rule determined a value for assay_type |
| .txt | 4,674 | No rule determined a value for assay_type |
| .bed | 4,392 | No rule determined a value for assay_type |
| .pgen | 2,854 | No rule determined a value for assay_type |
| .pvar | 2,854 | No rule determined a value for assay_type |
| .psam | 2,854 | No rule determined a value for assay_type |
| .bw | 2,520 | No rule determined a value for assay_type |
| .g.vcf | 2,504 | No rule determined a value for assay_type |
| .bam | 1,905 | No rule determined a value for assay_type |
| .bai | 1,275 | Parent file had no value for assay_type |
| .tsv | 924 | No rule determined a value for assay_type |
| .bigwig | 462 | No rule determined a value for assay_type |
| .sam | 192 | No rule determined a value for assay_type |
| .cram | 68 | No rule determined a value for assay_type |
| .crai | 68 | Parent file had no value for assay_type |
| .csv | 20 | No rule determined a value for assay_type |
| .pod5 | 11 | No rule determined a value for assay_type |
| .pbi | 7 | Parent file had no value for assay_type |

| Assay Type | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 605,214 | 82.5% | .vcf (201,668)<br>.tbi (169,517)<br>(none) (138,411)<br>.csi (34,141)<br>.fastq (21,269)<br>.fast5 (12,624)<br>.txt (4,674)<br>.bed (4,392)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.bw (2,520)<br>.g.vcf (2,504)<br>.bam (1,905)<br>.bai (1,275)<br>.tsv (924)<br>.bigwig (462)<br>.sam (192)<br>.cram (68)<br>.crai (68)<br>.csv (20)<br>.pod5 (11)<br>.pbi (7) |
| `not_applicable` | 74,429 | 10.1% | .txt (37,548)<br>.md5 (14,233)<br>.bed (7,091)<br>.csi (7,045)<br>.log (3,637)<br>.png (3,074)<br>.fa (940)<br>.fai (477)<br>.gfa (326)<br>.fasta (38)<br>.xg (8)<br>.gbwt (6)<br>.bai (2)<br>.tbi (2)<br>.gbz (2) |
| `Histology` | 25,708 | 3.5% | .svs (25,708) |
| `WGS` | 23,344 | 3.2% | .cram (10,555)<br>.crai (10,249)<br>.bam (2,540) |
| `RNA-seq` | 5,109 | 0.7% | .bam (2,329)<br>.bai (1,465)<br>.sf (634)<br>.h5ad (352)<br>.txt (285)<br>.bw (16)<br>.bed (12)<br>.tbi (12)<br>.csv (3)<br>.fastq (1) |
| `Methylation array` | 160 | 0.0% | .idat (160) |
| `Bisulfite-seq` | 28 | 0.0% | .bed (28) |

**Note**: Like platform, assay type is inherently unknowable for most derived formats. Only BAM/CRAM (via `@PG` programs and file size heuristics) and filename patterns can determine assay. The high not-classified rate is expected.

