# AnVIL Classification Coverage Report

Classification run: **2026-09-23 20:29:01**

Source: **708,088** files across **12** open-access datasets on [explore.anvilproject.org](https://explore.anvilproject.org/).
Processed **708,088** files.

- ANVIL_T2T_CHRY (309,979 files)
- ANVIL_T2T (289,204 files)
- ANVIL_1000G_high_coverage_2019 (26,016 files)
- ANVIL_HPRC (23,185 files)
- AnVIL_HPRC_R2 (16,271 files)
- ANVIL_NIA_CARD_Coriell_Cell_Lines_Open (12,534 files)
- ANVIL_1000G_PRIMED_data_model (11,493 files)
- AnVIL_IGVF_Mouse_R1 (6,786 files)
- AnVIL_ENCORE_RS293 (3,752 files)
- ANVIL_nhp_dGTEx_V1 (3,591 files)
- AnVIL_MAGE (3,285 files)
- AnVIL_ENCORE_293T (1,992 files)

**Classified** includes all files with a determined value, including `not_applicable` (e.g., FASTQ files have no reference assembly). **Not classified** means no rule or signal could determine a value. **Conflict** means rules at the same tier disagreed and nothing has answered it (#88).

| Dimension | Classified | Not Classified | Conflict |
|---|---:|---:|---:|
| **Data Modality** | 629,493 (88.9%) | 78,595 (11.1%) | 0 (0.0%) |
| **Data Type** | 680,550 (96.1%) | 27,538 (3.9%) | 0 (0.0%) |
| **Reference Assembly** | 502,089 (70.9%) | 205,993 (29.1%) | 6 (0.0%) |
| **Platform** | 130,979 (18.5%) | 577,109 (81.5%) | 0 (0.0%) |
| **Assay Type** | 78,131 (11.0%) | 629,957 (89.0%) | 0 (0.0%) |

---

## Data Modality

| | count | % |
|---|---:|---:|
| **Classified** | 629,493 | 88.9% |
| **Not classified** | 78,595 | 11.1% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .fastq | 21,270 | FASTQ modality cannot be determined from reads alone — could be genomic, transcriptomic, or epigenomic depending on assay |
| (none) | 13,829 | No rule determined a value for data_modality |
| .tbi | 13,814 | No parent to inherit data_modality from: more than one file in this dataset carries that parent name, matched case-insensitively |
| .fast5 | 12,509 | No rule determined a value for data_modality |
| .txt | 4,929 | No rule determined a value for data_modality |
| .bed | 2,771 | No rule determined a value for data_modality |
| .bam | 2,757 | No rule determined a value for data_modality |
| .bw | 2,520 | No rule determined a value for data_modality |
| .bai | 1,089 | Parent file had no value for data_modality |
| .tsv | 923 | No rule determined a value for data_modality |
| .crai | 696 | No parent to inherit data_modality from: more than one file in this dataset carries that parent name, matched case-insensitively |
| .csi | 676 | No parent to inherit data_modality from: more than one file in this dataset carries that parent name, matched case-insensitively |
| .bigwig | 462 | No rule determined a value for data_modality |
| .sam | 192 | No rule determined a value for data_modality |
| .cram | 68 | No rule determined a value for data_modality |
| .vcf | 23 | no VCF header lines (no '#' lines) in the read head |
| .csv | 18 | No rule determined a value for data_modality |
| .fasta | 14 | No rule determined a value for data_modality |
| .fai | 13 | Parent file had no value for data_modality |
| .pod5 | 11 | No rule determined a value for data_modality |
| .pbi | 7 | Parent file had no value for data_modality |
| .fa | 4 | No rule determined a value for data_modality |

| Data Modality | count | % | extensions |
|---|---:|---:|---|
| `genomic` | 565,926 | 79.9% | .vcf (201,645)<br>.tbi (155,705)<br>(none) (124,470)<br>.csi (40,510)<br>.cram (10,555)<br>.crai (9,621)<br>.bed (8,712)<br>.psam (2,854)<br>.pgen (2,854)<br>.pvar (2,854)<br>.g.vcf (2,504)<br>.bam (1,688)<br>.fa (936)<br>.fai (464)<br>.gfa (326)<br>.bai (188)<br>.fasta (24)<br>.xg (8)<br>.gbwt (6)<br>.gbz (2) |
| `not_classified` | 78,595 | 11.1% | .fastq (21,270)<br>(none) (13,829)<br>.tbi (13,814)<br>.fast5 (12,509)<br>.txt (4,929)<br>.bed (2,771)<br>.bam (2,757)<br>.bw (2,520)<br>.bai (1,089)<br>.tsv (923)<br>.crai (696)<br>.csi (676)<br>.bigwig (462)<br>.sam (192)<br>.cram (68)<br>.vcf (23)<br>.csv (18)<br>.fasta (14)<br>.fai (13)<br>.pod5 (11)<br>.pbi (7)<br>.fa (4) |
| `not_applicable` | 58,492 | 8.3% | .txt (37,548)<br>.md5 (14,233)<br>.log (3,637)<br>.png (3,074) |
| `transcriptomic.bulk` | 4,473 | 0.6% | .bam (2,329)<br>.bai (1,465)<br>.sf (634)<br>.bw (16)<br>.bed (12)<br>.tbi (12)<br>.csv (3)<br>.txt (2) |
| `transcriptomic.single_cell` | 414 | 0.1% | .h5ad (350)<br>(none) (64) |
| `epigenomic.methylation` | 188 | 0.0% | .idat (160)<br>.bed (28) |

---

## Data Type

| | count | % |
|---|---:|---:|
| **Classified** | 680,550 | 96.1% |
| **Not classified** | 27,538 | 3.9% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| (none) | 13,827 | No rule determined a value for data_type |
| .txt | 4,929 | No rule determined a value for data_type |
| .bed | 2,771 | No rule determined a value for data_type |
| .bw | 2,520 | No rule determined a value for data_type |
| .bam | 1,805 | No rule determined a value for data_type |
| .tsv | 923 | No rule determined a value for data_type |
| .bigwig | 462 | No rule determined a value for data_type |
| .sam | 192 | No rule determined a value for data_type |
| .cram | 68 | No rule determined a value for data_type |
| .vcf | 23 | no VCF header lines (no '#' lines) in the read head |
| .csv | 18 | No rule determined a value for data_type |

| Data Type | count | % | extensions |
|---|---:|---:|---|
| `index` | 224,260 | 31.7% | .tbi (169,531)<br>.csi (41,186)<br>.crai (10,317)<br>.bai (2,742)<br>.fai (477)<br>.pbi (7) |
| `variants.germline` | 165,625 | 23.4% | .vcf (165,625) |
| `variants` | 162,667 | 23.0% | (none) (124,335)<br>.vcf (35,828)<br>.g.vcf (2,504) |
| `not_applicable` | 37,548 | 5.3% | .txt (37,548) |
| `not_classified` | 27,538 | 3.9% | (none) (13,827)<br>.txt (4,929)<br>.bed (2,771)<br>.bw (2,520)<br>.bam (1,805)<br>.tsv (923)<br>.bigwig (462)<br>.sam (192)<br>.cram (68)<br>.vcf (23)<br>.csv (18) |
| `reads` | 21,270 | 3.0% | .fastq (21,270) |
| `alignments` | 15,524 | 2.2% | .cram (10,555)<br>.bam (4,969) |
| `checksum` | 14,233 | 2.0% | .md5 (14,233) |
| `raw_signal` | 12,522 | 1.8% | .fast5 (12,509)<br>.pod5 (11)<br>(none) (2) |
| `annotations` | 8,752 | 1.2% | .bed (8,752) |
| `genotypes` | 8,562 | 1.2% | .psam (2,854)<br>.pgen (2,854)<br>.pvar (2,854) |
| `log` | 3,637 | 0.5% | .log (3,637) |
| `images` | 3,074 | 0.4% | .png (3,074) |
| `assembly` | 960 | 0.1% | .fa (936)<br>.fasta (24) |
| `quantification` | 634 | 0.1% | .sf (634) |
| `pangenome` | 449 | 0.1% | .gfa (314)<br>(none) (135) |
| `expression_matrix` | 419 | 0.1% | .h5ad (350)<br>(none) (64)<br>.csv (3)<br>.txt (2) |
| `variants.structural` | 192 | 0.0% | .vcf (192) |
| `array_signal` | 160 | 0.0% | .idat (160) |
| `pangenome.reference` | 28 | 0.0% | .gfa (12)<br>.xg (8)<br>.gbwt (6)<br>.gbz (2) |
| `sequence` | 18 | 0.0% | .fasta (14)<br>.fa (4) |
| `signal` | 16 | 0.0% | .bw (16) |

---

## Reference Assembly

| | count | % |
|---|---:|---:|
| **Classified** | 502,089 | 70.9% |
| **Not classified** | 205,993 | 29.1% |
| **Conflict** | 6 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| (none) | 138,363 | No rule determined a value for reference_assembly |
| .txt | 42,479 | No rule determined a value for reference_assembly |
| .tbi | 13,821 | No parent to inherit reference_assembly from: more than one file in this dataset carries that parent name, matched case-insensitively |
| .psam | 2,854 | No rule determined a value for reference_assembly |
| .bw | 2,536 | No rule determined a value for reference_assembly |
| .tsv | 923 | No rule determined a value for reference_assembly |
| .crai | 696 | No parent to inherit reference_assembly from: more than one file in this dataset carries that parent name, matched case-insensitively |
| .bam | 688 | No rule determined a value for reference_assembly |
| .bai | 688 | Parent file had no value for reference_assembly |
| .csi | 676 | No parent to inherit reference_assembly from: more than one file in this dataset carries that parent name, matched case-insensitively |
| .sf | 634 | No rule determined a value for reference_assembly |
| .bigwig | 462 | No rule determined a value for reference_assembly |
| .h5ad | 350 | No rule determined a value for reference_assembly |
| .gfa | 314 | No rule determined a value for reference_assembly |
| .sam | 192 | No rule determined a value for reference_assembly |
| .idat | 160 | No rule determined a value for reference_assembly |
| .cram | 68 | No rule determined a value for reference_assembly |
| .bed | 35 | No rule determined a value for reference_assembly |
| .vcf | 28 | no VCF header lines (no '#' lines) in the read head |
| .csv | 21 | No rule determined a value for reference_assembly |
| .fasta | 3 | No rule determined a value for reference_assembly |
| .fai | 2 | Parent file had no value for reference_assembly |

### What's in conflict?

Rules at the same tier disagreed and no curator rule has answered it; no value is asserted.

| extension | competing values | count |
|---|---|---:|
| .bed | CHM13 vs GRCh38 | 2 |
| .xg | CHM13 vs GRCh38 | 2 |
| .fasta | CHM13 vs GRCh38 | 1 |
| .fai | (not recorded on this record) | 1 |

| Reference Assembly | count | % | extensions |
|---|---:|---:|---|
| `CHM13` | 405,299 | 57.2% | .vcf (192,420)<br>.tbi (152,255)<br>.csi (39,500)<br>.bed (6,744)<br>.cram (6,718)<br>.crai (6,369)<br>.bam (632)<br>.bai (632)<br>.fasta (7)<br>.gfa (6)<br>.fai (6)<br>.fa (3)<br>.gbwt (3)<br>.xg (3)<br>.gbz (1) |
| `not_classified` | 205,993 | 29.1% | (none) (138,363)<br>.txt (42,479)<br>.tbi (13,821)<br>.psam (2,854)<br>.bw (2,536)<br>.tsv (923)<br>.crai (696)<br>.bam (688)<br>.bai (688)<br>.csi (676)<br>.sf (634)<br>.bigwig (462)<br>.h5ad (350)<br>.gfa (314)<br>.sam (192)<br>.idat (160)<br>.cram (68)<br>.bed (35)<br>.vcf (28)<br>.csv (21)<br>.fasta (3)<br>.fai (2) |
| `not_applicable` | 63,211 | 8.9% | .fastq (21,270)<br>.md5 (14,233)<br>.fast5 (12,509)<br>.bed (3,922)<br>.log (3,637)<br>.bam (3,113)<br>.png (3,074)<br>.fa (936)<br>.fai (464)<br>.fasta (24)<br>.pod5 (11)<br>.bai (11)<br>.pbi (7) |
| `GRCh38` | 33,565 | 4.7% | .vcf (9,209)<br>.cram (3,837)<br>.tbi (3,455)<br>.crai (3,252)<br>.pgen (2,854)<br>.pvar (2,854)<br>.g.vcf (2,504)<br>.bam (2,341)<br>.bai (1,411)<br>.csi (1,010)<br>.bed (817)<br>.gfa (6)<br>.fai (4)<br>.fasta (3)<br>.xg (3)<br>.gbwt (3)<br>.fa (1)<br>.gbz (1) |
| `GRCh37` | 14 | 0.0% | .vcf (11)<br>.bed (3) |
| `conflict` | 6 | 0.0% | .bed (2)<br>.xg (2)<br>.fasta (1)<br>.fai (1) |

---

## Platform

| | count | % |
|---|---:|---:|
| **Classified** | 130,979 | 18.5% |
| **Not classified** | 577,109 | 81.5% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf | 201,668 | No rule determined a value for platform |
| .tbi | 169,531 | Parent file had no value for platform |
| (none) | 138,363 | No rule determined a value for platform |
| .csi | 34,817 | Parent file had no value for platform |
| .txt | 4,931 | No rule determined a value for platform |
| .bed | 4,432 | No rule determined a value for platform |
| .bam | 3,664 | No rule determined a value for platform |
| .psam | 2,854 | No rule determined a value for platform |
| .pgen | 2,854 | No rule determined a value for platform |
| .pvar | 2,854 | No rule determined a value for platform |
| .bai | 2,731 | Parent file had no value for platform |
| .bw | 2,536 | No rule determined a value for platform |
| .g.vcf | 2,504 | No rule determined a value for platform |
| .tsv | 923 | No rule determined a value for platform |
| .sf | 634 | No rule determined a value for platform |
| .crai | 628 | No parent to inherit platform from: more than one file in this dataset carries that parent name, matched case-insensitively |
| .bigwig | 462 | No rule determined a value for platform |
| .h5ad | 350 | No rule determined a value for platform |
| .sam | 192 | No rule determined a value for platform |
| .idat | 160 | No rule determined a value for platform |
| .csv | 21 | No rule determined a value for platform |

| Platform | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 577,109 | 81.5% | .vcf (201,668)<br>.tbi (169,531)<br>(none) (138,363)<br>.csi (34,817)<br>.txt (4,931)<br>.bed (4,432)<br>.bam (3,664)<br>.psam (2,854)<br>.pgen (2,854)<br>.pvar (2,854)<br>.bai (2,731)<br>.bw (2,536)<br>.g.vcf (2,504)<br>.tsv (923)<br>.sf (634)<br>.crai (628)<br>.bigwig (462)<br>.h5ad (350)<br>.sam (192)<br>.idat (160)<br>.csv (21) |
| `not_applicable` | 73,749 | 10.4% | .txt (37,548)<br>.md5 (14,233)<br>.bed (7,091)<br>.csi (6,369)<br>.log (3,637)<br>.png (3,074)<br>.fa (940)<br>.fai (477)<br>.gfa (326)<br>.fasta (38)<br>.xg (8)<br>.gbwt (6)<br>.gbz (2) |
| `ILLUMINA` | 40,478 | 5.7% | .fastq (20,166)<br>.cram (10,623)<br>.crai (9,689) |
| `ONT` | 13,957 | 2.0% | .fast5 (12,509)<br>.bam (1,300)<br>.fastq (137)<br>.pod5 (11) |
| `PACBIO` | 2,795 | 0.4% | .bam (1,810)<br>.fastq (967)<br>.bai (11)<br>.pbi (7) |

**Note**: Platform is inherently unknowable for most derived formats (VCF, BED, PLINK). Only BAM/CRAM (via `@RG PL` header) and FASTQ (via read name patterns) can encode platform. The high not-classified rate is expected.

---

## Assay Type

| | count | % |
|---|---:|---:|
| **Classified** | 78,131 | 11.0% |
| **Not classified** | 629,957 | 89.0% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf | 201,668 | No rule determined a value for assay_type |
| .tbi | 169,519 | Parent file had no value for assay_type |
| (none) | 138,363 | No rule determined a value for assay_type |
| .csi | 34,817 | Parent file had no value for assay_type |
| .fastq | 21,270 | No rule determined a value for assay_type |
| .fast5 | 12,509 | No rule determined a value for assay_type |
| .cram | 10,623 | No rule determined a value for assay_type |
| .crai | 10,317 | Parent file had no value for assay_type |
| .txt | 4,931 | No rule determined a value for assay_type |
| .bam | 4,675 | No rule determined a value for assay_type |
| .bed | 4,420 | No rule determined a value for assay_type |
| .psam | 2,854 | No rule determined a value for assay_type |
| .pgen | 2,854 | No rule determined a value for assay_type |
| .pvar | 2,854 | No rule determined a value for assay_type |
| .bw | 2,536 | No rule determined a value for assay_type |
| .g.vcf | 2,504 | No rule determined a value for assay_type |
| .bai | 1,277 | Parent file had no value for assay_type |
| .tsv | 923 | No rule determined a value for assay_type |
| .bigwig | 462 | No rule determined a value for assay_type |
| .h5ad | 350 | No rule determined a value for assay_type |
| .sam | 192 | No rule determined a value for assay_type |
| .csv | 21 | No rule determined a value for assay_type |
| .pod5 | 11 | No rule determined a value for assay_type |
| .pbi | 7 | Parent file had no value for assay_type |

| Assay Type | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 629,957 | 89.0% | .vcf (201,668)<br>.tbi (169,519)<br>(none) (138,363)<br>.csi (34,817)<br>.fastq (21,270)<br>.fast5 (12,509)<br>.cram (10,623)<br>.crai (10,317)<br>.txt (4,931)<br>.bam (4,675)<br>.bed (4,420)<br>.psam (2,854)<br>.pgen (2,854)<br>.pvar (2,854)<br>.bw (2,536)<br>.g.vcf (2,504)<br>.bai (1,277)<br>.tsv (923)<br>.bigwig (462)<br>.h5ad (350)<br>.sam (192)<br>.csv (21)<br>.pod5 (11)<br>.pbi (7) |
| `not_applicable` | 73,749 | 10.4% | .txt (37,548)<br>.md5 (14,233)<br>.bed (7,091)<br>.csi (6,369)<br>.log (3,637)<br>.png (3,074)<br>.fa (940)<br>.fai (477)<br>.gfa (326)<br>.fasta (38)<br>.xg (8)<br>.gbwt (6)<br>.gbz (2) |
| `RNA-seq` | 4,222 | 0.6% | .bam (2,099)<br>.bai (1,465)<br>.sf (634)<br>.bed (12)<br>.tbi (12) |
| `Methylation array` | 160 | 0.0% | .idat (160) |

**Note**: Like platform, assay type is inherently unknowable for most derived formats. It is determined only by a rule that sees evidence of the assay: a STAR `@PG` line, filename patterns (STAR, Salmon, expression BED), and extension where the format implies it (`.idat` is a methylation array, `.svs` histology). Nothing infers it from the modality (#88), reads file size, or infers WGS from a long-read platform (#430). The high not-classified rate is expected.

