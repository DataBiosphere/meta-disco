# AnVIL Classification Coverage Report

Classification run: **2026-07-28 18:37:13**

Source: **758,658** files across **11** open-access datasets on [explore.anvilproject.org](https://explore.anvilproject.org/).
Processed **758,957** files.

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
| **Data Modality** | 688,080 (90.7%) | 70,877 (9.3%) |
| **Data Type** | 723,774 (95.4%) | 35,183 (4.6%) |
| **Reference Assembly** | 544,619 (71.8%) | 214,338 (28.2%) |
| **Platform** | 169,070 (22.3%) | 589,887 (77.7%) |
| **Assay Type** | 138,189 (18.2%) | 620,768 (81.8%) |

---

## Data Modality

| | count | % |
|---|---:|---:|
| **Classified** | 688,080 | 90.7% |
| **Not classified** | 70,877 | 9.3% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .fastq | 23,089 | FASTQ modality cannot be determined from reads alone — could be genomic, transcriptomic, or epigenomic depending on assay |
| (none) | 19,061 | No rule determined a value for data_modality |
| .fast5 | 12,992 | No rule determined a value for data_modality |
| .txt | 7,888 | No rule determined a value for data_modality |
| .bw | 2,520 | No rule determined a value for data_modality |
| .bam | 2,430 | No rule determined a value for data_modality |
| .tsv | 1,311 | No rule determined a value for data_modality |
| .pbi | 570 | Parent file had no value for data_modality |
| .sam | 479 | No rule determined a value for data_modality |
| .bai | 360 | Parent file had no value for data_modality |
| .fa | 91 | No rule determined a value for data_modality |
| .tbi | 37 | Parent file had no value for data_modality |
| .csv | 27 | No rule determined a value for data_modality |
| .pod5 | 11 | No rule determined a value for data_modality |
| .cram | 6 | No rule determined a value for data_modality |
| .fasta | 5 | No rule determined a value for data_modality |

| Data Modality | count | % | extensions |
|---|---:|---:|---|
| `genomic` | 591,222 | 77.9% | .vcf (202,552)<br>.tbi (169,486)<br>(none) (124,609)<br>.csi (41,138)<br>.bed (13,620)<br>.cram (10,823)<br>.crai (10,319)<br>.bam (3,991)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.g.vcf (2,504)<br>.fa (1,544)<br>.bai (720)<br>.gfa (669)<br>.pbi (532)<br>.fasta (125)<br>.xg (16)<br>.gbwt (12) |
| `not_classified` | 70,877 | 9.3% | .fastq (23,089)<br>(none) (19,061)<br>.fast5 (12,992)<br>.txt (7,888)<br>.bw (2,520)<br>.bam (2,430)<br>.tsv (1,311)<br>.pbi (570)<br>.sam (479)<br>.bai (360)<br>.fa (91)<br>.tbi (37)<br>.csv (27)<br>.pod5 (11)<br>.cram (6)<br>.fasta (5) |
| `not_applicable` | 67,225 | 8.9% | .txt (37,593)<br>.md5 (15,565)<br>.png (8,049)<br>.log (5,066)<br>(none) (856)<br>.csi (48)<br>.pbi (32)<br>.fai (12)<br>.bai (2)<br>.tbi (2) |
| `imaging.histology` | 25,708 | 3.4% | .svs (25,708) |
| `transcriptomic.bulk` | 3,154 | 0.4% | .bam (1,413)<br>.bai (779)<br>.sf (634)<br>.txt (285)<br>.bw (16)<br>.bed (12)<br>.tbi (12)<br>.csv (3) |
| `transcriptomic.single_cell` | 417 | 0.1% | .h5ad (352)<br>(none) (64)<br>.fastq (1) |
| `epigenomic.methylation` | 348 | 0.0% | .idat (320)<br>.bed (28) |
| `epigenomic.chromatin_accessibility` | 6 | 0.0% | .fastq (6) |

---

## Data Type

| | count | % |
|---|---:|---:|
| **Classified** | 723,774 | 95.4% |
| **Not classified** | 35,183 | 4.6% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| (none) | 19,059 | No rule determined a value for data_type |
| .txt | 7,888 | No rule determined a value for data_type |
| .bam | 2,774 | No rule determined a value for data_type |
| .bw | 2,520 | No rule determined a value for data_type |
| .tsv | 1,311 | No rule determined a value for data_type |
| .pbi | 570 | Parent file had no value for data_type |
| .bai | 512 | Parent file had no value for data_type |
| .sam | 479 | No rule determined a value for data_type |
| .tbi | 37 | Parent file had no value for data_type |
| .csv | 27 | No rule determined a value for data_type |
| .cram | 6 | No rule determined a value for data_type |

| Data Type | count | % | extensions |
|---|---:|---:|---|
| `variants.germline` | 331,250 | 43.6% | .vcf (165,625)<br>.tbi (165,625) |
| `variants` | 201,543 | 26.6% | (none) (124,332)<br>.vcf (36,735)<br>.csi (34,141)<br>.tbi (3,831)<br>.g.vcf (2,504) |
| `not_applicable` | 59,176 | 7.8% | .txt (37,593)<br>.md5 (15,565)<br>.log (5,066)<br>(none) (856)<br>.csi (48)<br>.pbi (32)<br>.fai (12)<br>.bai (2)<br>.tbi (2) |
| `not_classified` | 35,183 | 4.6% | (none) (19,059)<br>.txt (7,888)<br>.bam (2,774)<br>.bw (2,520)<br>.tsv (1,311)<br>.pbi (570)<br>.bai (512)<br>.sam (479)<br>.tbi (37)<br>.csv (27)<br>.cram (6) |
| `images` | 33,757 | 4.4% | .svs (25,708)<br>.png (8,049) |
| `alignments` | 28,081 | 3.7% | .cram (10,823)<br>.crai (10,319)<br>.bam (5,060)<br>.bai (1,347)<br>.pbi (532) |
| `reads` | 23,096 | 3.0% | .fastq (23,096) |
| `annotations` | 20,680 | 2.7% | .bed (13,660)<br>.csi (6,997)<br>.tbi (16)<br>(none) (7) |
| `raw_signal` | 13,005 | 1.7% | .fast5 (12,992)<br>.pod5 (11)<br>(none) (2) |
| `genotypes` | 8,562 | 1.1% | .pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854) |
| `assembly` | 1,652 | 0.2% | .fa (1,541)<br>.fasta (111) |
| `pangenome` | 923 | 0.1% | .gfa (653)<br>(none) (270) |
| `expression_matrix` | 704 | 0.1% | .h5ad (352)<br>.txt (285)<br>(none) (64)<br>.csv (3) |
| `quantification` | 634 | 0.1% | .sf (634) |
| `array_signal` | 320 | 0.0% | .idat (320) |
| `variants.structural` | 218 | 0.0% | .vcf (192)<br>.tbi (26) |
| `sequence` | 113 | 0.0% | .fa (94)<br>.fasta (19) |
| `pangenome.reference` | 44 | 0.0% | .gfa (16)<br>.xg (16)<br>.gbwt (12) |
| `signal` | 16 | 0.0% | .bw (16) |

---

## Reference Assembly

| | count | % |
|---|---:|---:|
| **Classified** | 544,619 | 71.8% |
| **Not classified** | 214,338 | 28.2% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| (none) | 143,108 | No rule determined a value for reference_assembly |
| .txt | 40,399 | No rule determined a value for reference_assembly |
| .bed | 13,596 | No rule determined a value for reference_assembly |
| .csi | 6,997 | Parent file had no value for reference_assembly |
| .bw | 2,536 | No rule determined a value for reference_assembly |
| .bam | 2,456 | No rule determined a value for reference_assembly |
| .tsv | 1,293 | No rule determined a value for reference_assembly |
| .pbi | 697 | Parent file had no value for reference_assembly |
| .gfa | 653 | No rule determined a value for reference_assembly |
| .sf | 634 | No rule determined a value for reference_assembly |
| .sam | 479 | No rule determined a value for reference_assembly |
| .h5ad | 352 | No rule determined a value for reference_assembly |
| .vcf | 345 | No rule determined a value for reference_assembly |
| .idat | 320 | No rule determined a value for reference_assembly |
| .bai | 276 | Parent file had no value for reference_assembly |
| .fa | 91 | No rule determined a value for reference_assembly |
| .tbi | 54 | Parent file had no value for reference_assembly |
| .csv | 30 | No rule determined a value for reference_assembly |
| .fasta | 8 | No rule determined a value for reference_assembly |
| .cram | 6 | No rule determined a value for reference_assembly |
| .xg | 4 | Filename contains GRCh38/hg38 reference indicator |
| .fai | 4 | No rule determined a value for reference_assembly |

| Reference Assembly | count | % | extensions |
|---|---:|---:|---|
| `CHM13` | 404,724 | 53.3% | .vcf (192,548)<br>.tbi (159,189)<br>.csi (33,179)<br>.cram (6,718)<br>.crai (6,715)<br>.txt (5,170)<br>.bam (427)<br>.bai (393)<br>(none) (310)<br>.bed (31)<br>.fasta (8)<br>.gfa (8)<br>.tsv (8)<br>.gbwt (6)<br>.xg (6)<br>.fai (5)<br>.fa (3) |
| `not_classified` | 214,338 | 28.2% | (none) (143,108)<br>.txt (40,399)<br>.bed (13,596)<br>.csi (6,997)<br>.bw (2,536)<br>.bam (2,456)<br>.tsv (1,293)<br>.pbi (697)<br>.gfa (653)<br>.sf (634)<br>.sam (479)<br>.h5ad (352)<br>.vcf (345)<br>.idat (320)<br>.bai (276)<br>.fa (91)<br>.tbi (54)<br>.csv (30)<br>.fasta (8)<br>.cram (6)<br>.xg (4)<br>.fai (4) |
| `not_applicable` | 96,019 | 12.7% | .svs (25,708)<br>.fastq (23,096)<br>.md5 (15,565)<br>.fast5 (12,992)<br>.png (8,049)<br>.log (5,066)<br>.bam (2,565)<br>.fa (1,541)<br>(none) (856)<br>.pbi (437)<br>.fasta (111)<br>.bai (22)<br>.pod5 (11) |
| `GRCh38` | 43,864 | 5.8% | .tbi (10,294)<br>.vcf (9,648)<br>.cram (4,105)<br>.crai (3,604)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.g.vcf (2,504)<br>.bam (2,386)<br>.bai (1,170)<br>.csi (1,010)<br>(none) (316)<br>.txt (197)<br>.bed (32)<br>.tsv (10)<br>.gfa (8)<br>.xg (6)<br>.gbwt (6)<br>.fasta (3)<br>.fai (3) |
| `GRCh37` | 12 | 0.0% | .vcf (11)<br>.bed (1) |

---

## Platform

| | count | % |
|---|---:|---:|
| **Classified** | 169,070 | 22.3% |
| **Not classified** | 589,887 | 77.7% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf | 202,552 | No rule determined a value for platform |
| .tbi | 169,535 | Parent file had no value for platform |
| (none) | 143,734 | No rule determined a value for platform |
| .csi | 34,141 | Parent file had no value for platform |
| .txt | 8,173 | No rule determined a value for platform |
| .bed | 6,475 | No rule determined a value for platform |
| .bam | 4,530 | No rule determined a value for platform |
| .pgen | 2,854 | No rule determined a value for platform |
| .pvar | 2,854 | No rule determined a value for platform |
| .psam | 2,854 | No rule determined a value for platform |
| .bw | 2,536 | No rule determined a value for platform |
| .g.vcf | 2,504 | No rule determined a value for platform |
| .fastq | 1,821 | No rule determined a value for platform |
| .bai | 1,643 | Parent file had no value for platform |
| .tsv | 1,311 | No rule determined a value for platform |
| .sf | 634 | No rule determined a value for platform |
| .pbi | 549 | Parent file had no value for platform |
| .sam | 479 | No rule determined a value for platform |
| .h5ad | 352 | No rule determined a value for platform |
| .idat | 320 | No rule determined a value for platform |
| .csv | 30 | No rule determined a value for platform |
| .cram | 6 | No rule determined a value for platform |

| Platform | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 589,887 | 77.7% | .vcf (202,552)<br>.tbi (169,535)<br>(none) (143,734)<br>.csi (34,141)<br>.txt (8,173)<br>.bed (6,475)<br>.bam (4,530)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.bw (2,536)<br>.g.vcf (2,504)<br>.fastq (1,821)<br>.bai (1,643)<br>.tsv (1,311)<br>.sf (634)<br>.pbi (549)<br>.sam (479)<br>.h5ad (352)<br>.idat (320)<br>.csv (30)<br>.cram (6) |
| `not_applicable` | 109,577 | 14.4% | .txt (37,593)<br>.svs (25,708)<br>.md5 (15,565)<br>.png (8,049)<br>.bed (7,185)<br>.csi (7,045)<br>.log (5,066)<br>.fa (1,635)<br>(none) (856)<br>.gfa (669)<br>.fasta (130)<br>.pbi (32)<br>.xg (16)<br>.gbwt (12)<br>.fai (12)<br>.bai (2)<br>.tbi (2) |
| `ILLUMINA` | 41,477 | 5.5% | .fastq (20,335)<br>.cram (10,823)<br>.crai (10,319) |
| `ONT` | 14,192 | 1.9% | .fast5 (12,992)<br>.bam (1,043)<br>.fastq (146)<br>.pod5 (11) |
| `PACBIO` | 3,824 | 0.5% | .bam (2,261)<br>.fastq (794)<br>.pbi (553)<br>.bai (216) |

**Note**: Platform is inherently unknowable for most derived formats (VCF, BED, PLINK). Only BAM/CRAM (via `@RG PL` header) and FASTQ (via read name patterns) can encode platform. The high not-classified rate is expected.

---

## Assay Type

| | count | % |
|---|---:|---:|
| **Classified** | 138,189 | 18.2% |
| **Not classified** | 620,768 | 81.8% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf | 202,552 | No rule determined a value for assay_type |
| .tbi | 169,523 | Parent file had no value for assay_type |
| (none) | 143,734 | No rule determined a value for assay_type |
| .csi | 34,141 | Parent file had no value for assay_type |
| .fastq | 23,089 | No rule determined a value for assay_type |
| .fast5 | 12,992 | No rule determined a value for assay_type |
| .txt | 7,888 | No rule determined a value for assay_type |
| .bed | 6,435 | No rule determined a value for assay_type |
| .bam | 3,538 | No rule determined a value for assay_type |
| .pgen | 2,854 | No rule determined a value for assay_type |
| .pvar | 2,854 | No rule determined a value for assay_type |
| .psam | 2,854 | No rule determined a value for assay_type |
| .bw | 2,520 | No rule determined a value for assay_type |
| .g.vcf | 2,504 | No rule determined a value for assay_type |
| .tsv | 1,311 | No rule determined a value for assay_type |
| .bai | 886 | Parent file had no value for assay_type |
| .pbi | 570 | Parent file had no value for assay_type |
| .sam | 479 | No rule determined a value for assay_type |
| .csv | 27 | No rule determined a value for assay_type |
| .pod5 | 11 | No rule determined a value for assay_type |
| .cram | 6 | No rule determined a value for assay_type |

| Assay Type | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 620,768 | 81.8% | .vcf (202,552)<br>.tbi (169,523)<br>(none) (143,734)<br>.csi (34,141)<br>.fastq (23,089)<br>.fast5 (12,992)<br>.txt (7,888)<br>.bed (6,435)<br>.bam (3,538)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.bw (2,520)<br>.g.vcf (2,504)<br>.tsv (1,311)<br>.bai (886)<br>.pbi (570)<br>.sam (479)<br>.csv (27)<br>.pod5 (11)<br>.cram (6) |
| `not_applicable` | 83,869 | 11.1% | .txt (37,593)<br>.md5 (15,565)<br>.png (8,049)<br>.bed (7,185)<br>.csi (7,045)<br>.log (5,066)<br>.fa (1,635)<br>(none) (856)<br>.gfa (669)<br>.fasta (130)<br>.pbi (32)<br>.xg (16)<br>.gbwt (12)<br>.fai (12)<br>.bai (2)<br>.tbi (2) |
| `Histology` | 25,708 | 3.4% | .svs (25,708) |
| `WGS` | 24,751 | 3.3% | .cram (10,823)<br>.crai (10,319)<br>.bam (2,883)<br>.pbi (532)<br>.bai (194) |
| `RNA-seq` | 3,507 | 0.5% | .bam (1,413)<br>.bai (779)<br>.sf (634)<br>.h5ad (352)<br>.txt (285)<br>.bw (16)<br>.bed (12)<br>.tbi (12)<br>.csv (3)<br>.fastq (1) |
| `Methylation array` | 320 | 0.0% | .idat (320) |
| `Bisulfite-seq` | 28 | 0.0% | .bed (28) |
| `ATAC-seq` | 6 | 0.0% | .fastq (6) |

**Note**: Like platform, assay type is inherently unknowable for most derived formats. Only BAM/CRAM (via `@PG` programs and file size heuristics) and filename patterns can determine assay. The high not-classified rate is expected.

