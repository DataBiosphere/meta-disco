# AnVIL Classification Coverage Report

Classification run: **2026-10-10 16:12:15**

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
| **Data Modality** | 379,527 (53.6%) | 328,561 (46.4%) | 0 (0.0%) |
| **Data Type** | 685,435 (96.8%) | 22,653 (3.2%) | 0 (0.0%) |
| **Platform** | 69,973 (9.9%) | 638,115 (90.1%) | 0 (0.0%) |
| **Reference Assembly** | 292,948 (41.4%) | 415,132 (58.6%) | 8 (0.0%) |
| **Assay Type** | 28,145 (4.0%) | 679,943 (96.0%) | 0 (0.0%) |
| **Instrument Model** | 23,202 (3.3%) | 684,886 (96.7%) | 0 (0.0%) |
| **Variant Kind** | 325,529 (46.0%) | 382,559 (54.0%) | 0 (0.0%) |
| **Variant Origin** | 325,541 (46.0%) | 382,547 (54.0%) | 0 (0.0%) |

---

## Data Modality

| | count | % |
|---|---:|---:|
| **Classified** | 379,527 | 53.6% |
| **Not classified** | 328,561 | 46.4% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .tbi | 169,531 | `No reason recorded` |
| .txt | 42,477 | `No rule determined a value for data_modality` |
| .csi | 41,186 | `No reason recorded` |
| .fastq | 21,270 | `FASTQ modality cannot be determined from reads alone — could be genomic, transcriptomic, or epigenomic depending on assay` |
| .fast5 | 12,509 | `No rule determined a value for data_modality` |
| .crai | 10,317 | `No reason recorded` |
| (none) | 10,071 | `No rule determined a value for data_modality` |
| .bed | 9,768 | `No rule determined a value for data_modality` |
| .bam | 2,757 | `No rule determined a value for data_modality` |
| .bai | 2,742 | `No reason recorded` |
| .gff3 | 1,565 | `No rule determined a value for data_modality` |
| .chain | 926 | `No rule determined a value for data_modality` |
| .tsv | 899 | `No rule determined a value for data_modality` |
| .fai | 477 | `No reason recorded` |
| .gzi | 466 | `No reason recorded` |
| .bigwig | 462 | `No rule determined a value for data_modality` |
| .sizes | 458 | `No rule determined a value for data_modality` |
| .paf | 297 | `No rule determined a value for data_modality` |
| .sam | 192 | `No rule determined a value for data_modality` |
| .cram | 68 | `No rule determined a value for data_modality` |
| .vcf | 23 | `no VCF header lines (no run of '#' lines starting the read head)` |
| .csv | 18 | `No rule determined a value for data_modality` |
| .fasta | 14 | `No rule determined a value for data_modality` |
| .pod5 | 11 | `No rule determined a value for data_modality` |
| .dict | 9 | `No rule determined a value for data_modality` |
| .pbi | 7 | `No reason recorded` |
| .snarls | 6 | `No rule determined a value for data_modality` |
| .gg | 6 | `No rule determined a value for data_modality` |
| .min | 6 | `No rule determined a value for data_modality` |
| .dist | 6 | `No rule determined a value for data_modality` |
| .trans | 6 | `No rule determined a value for data_modality` |
| .fa | 4 | `No rule determined a value for data_modality` |
| .fna | 2 | `No rule determined a value for data_modality` |
| .hal | 2 | `No rule determined a value for data_modality` |
| .hapl | 2 | `No rule determined a value for data_modality` |
| .delta | 1 | `No rule determined a value for data_modality` |

| Data Modality | count | % | extensions |
|---|---:|---:|---|
| `genomic` | 352,441 | 49.8% | .vcf (201,645)<br>(none) (124,470)<br>.cram (10,555)<br>.pvar (2,854)<br>.psam (2,854)<br>.pgen (2,854)<br>.g.vcf (2,504)<br>.bed (1,715)<br>.bam (1,688)<br>.fa (936)<br>.gfa (326)<br>.fasta (24)<br>.xg (8)<br>.gbwt (6)<br>.gbz (2) |
| `not_classified` | 328,561 | 46.4% | .tbi (169,531)<br>.txt (42,477)<br>.csi (41,186)<br>.fastq (21,270)<br>.fast5 (12,509)<br>.crai (10,317)<br>(none) (10,071)<br>.bed (9,768)<br>.bam (2,757)<br>.bai (2,742)<br>.gff3 (1,565)<br>.chain (926)<br>.tsv (899)<br>.fai (477)<br>.gzi (466)<br>.bigwig (462)<br>.sizes (458)<br>.paf (297)<br>.sam (192)<br>.cram (68)<br>.vcf (23)<br>.csv (18)<br>.fasta (14)<br>.pod5 (11)<br>.dict (9)<br>.pbi (7)<br>.snarls (6)<br>.gg (6)<br>.min (6)<br>.dist (6)<br>.trans (6)<br>.fa (4)<br>.fna (2)<br>.hal (2)<br>.hapl (2)<br>.delta (1) |
| `not_applicable` | 20,968 | 3.0% | .md5 (14,233)<br>.log (3,637)<br>.png (3,074)<br>.tsv (24) |
| `transcriptomic` | 5,930 | 0.8% | .bw (2,536)<br>.bam (2,329)<br>.sf (634)<br>.h5ad (350)<br>(none) (64)<br>.bed (12)<br>.csv (3)<br>.txt (2) |
| `genomic.genotyping` | 160 | 0.0% | .idat (160) |
| `epigenomic.methylation` | 28 | 0.0% | .bed (28) |

---

## Data Type

| | count | % |
|---|---:|---:|
| **Classified** | 685,435 | 96.8% |
| **Not classified** | 22,653 | 3.2% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| (none) | 10,069 | `No rule determined a value for data_type` |
| .txt | 4,929 | `No rule determined a value for data_type` |
| .bed | 2,771 | `No rule determined a value for data_type` |
| .gff3 | 1,565 | `No rule determined a value for data_type` |
| .chain | 926 | `No rule determined a value for data_type` |
| .tsv | 899 | `No rule determined a value for data_type` |
| .bigwig | 462 | `No rule determined a value for data_type` |
| .sizes | 458 | `No rule determined a value for data_type` |
| .paf | 297 | `No rule determined a value for data_type` |
| .sam | 192 | `No rule determined a value for data_type` |
| .vcf | 23 | `no VCF header lines (no run of '#' lines starting the read head)` |
| .csv | 18 | `No rule determined a value for data_type` |
| .dict | 9 | `No rule determined a value for data_type` |
| .snarls | 6 | `No rule determined a value for data_type` |
| .gg | 6 | `No rule determined a value for data_type` |
| .min | 6 | `No rule determined a value for data_type` |
| .dist | 6 | `No rule determined a value for data_type` |
| .trans | 6 | `No rule determined a value for data_type` |
| .hal | 2 | `No rule determined a value for data_type` |
| .hapl | 2 | `No rule determined a value for data_type` |
| .delta | 1 | `No rule determined a value for data_type` |

| Data Type | count | % | extensions |
|---|---:|---:|---|
| `index` | 224,726 | 31.7% | .tbi (169,531)<br>.csi (41,186)<br>.crai (10,317)<br>.bai (2,742)<br>.fai (477)<br>.gzi (466)<br>.pbi (7) |
| `variants.germline.gvcf` | 168,825 | 23.8% | .vcf (166,321)<br>.g.vcf (2,504) |
| `variants` | 159,504 | 22.5% | (none) (124,335)<br>.vcf (35,169) |
| `qc_report` | 37,548 | 5.3% | .txt (37,548) |
| `reads` | 24,383 | 3.4% | .fastq (21,270)<br>.bam (3,113) |
| `not_classified` | 22,653 | 3.2% | (none) (10,069)<br>.txt (4,929)<br>.bed (2,771)<br>.gff3 (1,565)<br>.chain (926)<br>.tsv (899)<br>.bigwig (462)<br>.sizes (458)<br>.paf (297)<br>.sam (192)<br>.vcf (23)<br>.csv (18)<br>.dict (9)<br>.snarls (6)<br>.gg (6)<br>.min (6)<br>.dist (6)<br>.trans (6)<br>.hal (2)<br>.hapl (2)<br>.delta (1) |
| `alignments` | 14,284 | 2.0% | .cram (10,623)<br>.bam (3,661) |
| `checksum` | 14,233 | 2.0% | .md5 (14,233) |
| `raw_signal` | 12,522 | 1.8% | .fast5 (12,509)<br>.pod5 (11)<br>(none) (2) |
| `annotations.coverage` | 9,533 | 1.3% | .bed (6,997)<br>.bw (2,536) |
| `genotypes` | 8,562 | 1.2% | .pvar (2,854)<br>.psam (2,854)<br>.pgen (2,854) |
| `log` | 3,637 | 0.5% | .log (3,637) |
| `images` | 3,074 | 0.4% | .png (3,074) |
| `annotations` | 1,755 | 0.2% | .bed (1,755) |
| `assembly` | 960 | 0.1% | .fa (936)<br>.fasta (24) |
| `quantification` | 634 | 0.1% | .sf (634) |
| `pangenome` | 449 | 0.1% | .gfa (314)<br>(none) (135) |
| `expression_matrix` | 419 | 0.1% | .h5ad (350)<br>(none) (64)<br>.csv (3)<br>.txt (2) |
| `array_signal` | 160 | 0.0% | .idat (160) |
| `variants.structural` | 153 | 0.0% | .vcf (153) |
| `pangenome.reference` | 28 | 0.0% | .gfa (12)<br>.xg (8)<br>.gbwt (6)<br>.gbz (2) |
| `sample_map` | 24 | 0.0% | .tsv (24) |
| `sequence` | 20 | 0.0% | .fasta (14)<br>.fa (4)<br>.fna (2) |
| `variants.germline` | 2 | 0.0% | .vcf (2) |

---

## Platform

| | count | % |
|---|---:|---:|
| **Classified** | 69,973 | 9.9% |
| **Not classified** | 638,115 | 90.1% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf | 201,668 | `No rule determined a value for platform` |
| .tbi | 169,531 | `No reason recorded` |
| (none) | 134,605 | `No rule determined a value for platform` |
| .txt | 42,479 | `No rule determined a value for platform` |
| .csi | 41,186 | `No reason recorded` |
| .bed | 11,523 | `No rule determined a value for platform` |
| .crai | 10,317 | `No reason recorded` |
| .bam | 3,664 | `No rule determined a value for platform` |
| .pvar | 2,854 | `No rule determined a value for platform` |
| .psam | 2,854 | `No rule determined a value for platform` |
| .pgen | 2,854 | `No rule determined a value for platform` |
| .bai | 2,742 | `No reason recorded` |
| .bw | 2,536 | `No rule determined a value for platform` |
| .g.vcf | 2,504 | `No rule determined a value for platform` |
| .gff3 | 1,565 | `No rule determined a value for platform` |
| .chain | 926 | `No rule determined a value for platform` |
| .tsv | 899 | `No rule determined a value for platform` |
| .sf | 634 | `No rule determined a value for platform` |
| .fai | 477 | `No reason recorded` |
| .gzi | 466 | `No reason recorded` |
| .bigwig | 462 | `No rule determined a value for platform` |
| .sizes | 458 | `No rule determined a value for platform` |
| .h5ad | 350 | `No rule determined a value for platform` |
| .paf | 297 | `No rule determined a value for platform` |
| .sam | 192 | `No rule determined a value for platform` |
| .csv | 21 | `No rule determined a value for platform` |
| .dict | 9 | `No rule determined a value for platform` |
| .pbi | 7 | `No reason recorded` |
| .snarls | 6 | `No rule determined a value for platform` |
| .gg | 6 | `No rule determined a value for platform` |
| .min | 6 | `No rule determined a value for platform` |
| .dist | 6 | `No rule determined a value for platform` |
| .trans | 6 | `No rule determined a value for platform` |
| .hal | 2 | `No rule determined a value for platform` |
| .hapl | 2 | `No rule determined a value for platform` |
| .delta | 1 | `No rule determined a value for platform` |

| Platform | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 638,115 | 90.1% | .vcf (201,668)<br>.tbi (169,531)<br>(none) (134,605)<br>.txt (42,479)<br>.csi (41,186)<br>.bed (11,523)<br>.crai (10,317)<br>.bam (3,664)<br>.pvar (2,854)<br>.psam (2,854)<br>.pgen (2,854)<br>.bai (2,742)<br>.bw (2,536)<br>.g.vcf (2,504)<br>.gff3 (1,565)<br>.chain (926)<br>.tsv (899)<br>.sf (634)<br>.fai (477)<br>.gzi (466)<br>.bigwig (462)<br>.sizes (458)<br>.h5ad (350)<br>.paf (297)<br>.sam (192)<br>.csv (21)<br>.dict (9)<br>.pbi (7)<br>.snarls (6)<br>.gg (6)<br>.min (6)<br>.dist (6)<br>.trans (6)<br>.hal (2)<br>.hapl (2)<br>.delta (1) |
| `ILLUMINA` | 30,949 | 4.4% | .fastq (20,166)<br>.cram (10,623)<br>.idat (160) |
| `not_applicable` | 22,290 | 3.1% | .md5 (14,233)<br>.log (3,637)<br>.png (3,074)<br>.fa (940)<br>.gfa (326)<br>.fasta (38)<br>.tsv (24)<br>.xg (8)<br>.gbwt (6)<br>.fna (2)<br>.gbz (2) |
| `ONT` | 13,957 | 2.0% | .fast5 (12,509)<br>.bam (1,300)<br>.fastq (137)<br>.pod5 (11) |
| `PACBIO` | 2,777 | 0.4% | .bam (1,810)<br>.fastq (967) |

**Note**: Platform is inherently unknowable for most derived formats (VCF, BED, PLINK). It is read from a BAM/CRAM `@RG PL` header, FASTQ read name patterns, a nanopore signal file's extension, and an Illumina IDAT's run log, from whose scan software the array scanner is inferred (#603). The high not-classified rate is expected.

---

## Reference Assembly

| | count | % |
|---|---:|---:|
| **Classified** | 292,948 | 41.4% |
| **Not classified** | 415,132 | 58.6% |
| **Conflict** | 8 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .tbi | 169,531 | `No reason recorded` |
| (none) | 134,605 | `No rule determined a value for reference_assembly` |
| .txt | 42,479 | `No rule determined a value for reference_assembly` |
| .csi | 41,186 | `No reason recorded` |
| .crai | 10,317 | `No reason recorded` |
| .psam | 2,854 | `No rule determined a value for reference_assembly` |
| .pgen | 2,853 | `No rule determined a value for reference_assembly` |
| .bai | 2,742 | `No reason recorded` |
| .bw | 2,536 | `No rule determined a value for reference_assembly` |
| .gff3 | 1,386 | `No rule determined a value for reference_assembly` |
| .tsv | 899 | `No rule determined a value for reference_assembly` |
| .sf | 634 | `No rule determined a value for reference_assembly` |
| .fai | 477 | `No reason recorded` |
| .gzi | 466 | `No reason recorded` |
| .bigwig | 462 | `No rule determined a value for reference_assembly` |
| .sizes | 456 | `No rule determined a value for reference_assembly` |
| .h5ad | 350 | `No rule determined a value for reference_assembly` |
| .gfa | 314 | `No rule determined a value for reference_assembly` |
| .paf | 296 | `No rule determined a value for reference_assembly` |
| .sam | 192 | `No rule determined a value for reference_assembly` |
| .bed | 36 | `No rule determined a value for reference_assembly` |
| .vcf | 26 | `no VCF header lines (no run of '#' lines starting the read head)` |
| .csv | 21 | `No rule determined a value for reference_assembly` |
| .pbi | 7 | `No reason recorded` |
| .fasta | 3 | `No rule determined a value for reference_assembly` |
| .bam | 2 | `No rule determined a value for reference_assembly` |
| .chain | 1 | `No rule determined a value for reference_assembly` |
| .dict | 1 | `No rule determined a value for reference_assembly` |

### What's in conflict?

Rules at the same tier disagreed and no curator rule has answered it; no value is asserted.

| extension | competing values | count |
|---|---|---:|
| .bed | CHM13 vs GRCh38 | 2 |
| .xg | CHM13 vs GRCh38 | 2 |
| .fasta | CHM13 vs GRCh38 | 1 |
| .chain | CHM13 vs GRCh38 | 1 |
| .dict | CHM13 vs GRCh38 | 1 |
| .gff3 | CHM13 vs GRCh38 | 1 |

| Reference Assembly | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 415,132 | 58.6% | .tbi (169,531)<br>(none) (134,605)<br>.txt (42,479)<br>.csi (41,186)<br>.crai (10,317)<br>.psam (2,854)<br>.pgen (2,853)<br>.bai (2,742)<br>.bw (2,536)<br>.gff3 (1,386)<br>.tsv (899)<br>.sf (634)<br>.fai (477)<br>.gzi (466)<br>.bigwig (462)<br>.sizes (456)<br>.h5ad (350)<br>.gfa (314)<br>.paf (296)<br>.sam (192)<br>.bed (36)<br>.vcf (26)<br>.csv (21)<br>.pbi (7)<br>.fasta (3)<br>.bam (2)<br>.chain (1)<br>.dict (1) |
| `t2t-chm13.20200921.withGRCh38chrY.chrEBV.chrYKI270740v1r` | 111,756 | 15.8% | .vcf (108,478)<br>.cram (3,202)<br>.bam (76) |
| `T2T-CHM13v2.0` | 87,747 | 12.4% | .vcf (83,804)<br>.cram (3,481)<br>.bam (462) |
| `not_applicable` | 62,913 | 8.9% | .fastq (21,270)<br>.md5 (14,233)<br>.fast5 (12,509)<br>.bed (3,922)<br>.log (3,637)<br>.bam (3,113)<br>.png (3,074)<br>.fa (936)<br>.idat (160)<br>.fasta (24)<br>.tsv (24)<br>.pod5 (11) |
| `GRCh38` | 20,705 | 2.9% | .vcf (9,186)<br>.cram (3,837)<br>.g.vcf (2,504)<br>.bam (2,341)<br>.pvar (1,427)<br>.bed (817)<br>.chain (462)<br>.gff3 (88)<br>.gfa (6)<br>.fasta (3)<br>.dict (3)<br>.snarls (3)<br>.min (3)<br>.gg (3)<br>.dist (3)<br>.trans (3)<br>.xg (3)<br>.gbwt (3)<br>.fna (2)<br>.fa (1)<br>.pgen (1)<br>.sizes (1)<br>.hal (1)<br>.paf (1)<br>.delta (1)<br>.hapl (1)<br>.gbz (1) |
| `CHM13` | 7,395 | 1.0% | .bed (6,744)<br>.chain (462)<br>.gff3 (90)<br>.vcf (54)<br>.fasta (7)<br>.gfa (6)<br>.dict (4)<br>.fa (3)<br>.gg (3)<br>.snarls (3)<br>.trans (3)<br>.min (3)<br>.dist (3)<br>.gbwt (3)<br>.xg (3)<br>.sizes (1)<br>.hal (1)<br>.gbz (1)<br>.hapl (1) |
| `GRCh37` | 1,463 | 0.2% | .pvar (1,427)<br>.vcf (34)<br>.bed (2) |
| `Mmul_10` | 422 | 0.1% | .bam (372)<br>.cram (49)<br>.vcf (1) |
| `mCalJa1.2.pat.X` | 334 | 0.0% | .bam (314)<br>.cram (19)<br>.vcf (1) |
| `CHM13Y_EBV_v1.1` | 95 | 0.0% | .bam (94)<br>.vcf (1) |
| `T2T-CHM13v1.0` | 59 | 0.0% | .vcf (59) |
| `t2t-chm13.20200921.HG002chrY.chrEBV` | 35 | 0.0% | .cram (35) |
| `T2T-CHM13v1.1` | 24 | 0.0% | .vcf (24) |
| `conflict` | 8 | 0.0% | .bed (2)<br>.xg (2)<br>.fasta (1)<br>.chain (1)<br>.dict (1)<br>.gff3 (1) |

---

## Assay Type

| | count | % |
|---|---:|---:|
| **Classified** | 28,145 | 4.0% |
| **Not classified** | 679,943 | 96.0% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf | 201,668 | `No rule determined a value for assay_type` |
| .tbi | 169,531 | `No reason recorded` |
| (none) | 134,541 | `No rule determined a value for assay_type` |
| .txt | 42,479 | `No rule determined a value for assay_type` |
| .csi | 41,186 | `No reason recorded` |
| .fastq | 21,270 | `No rule determined a value for assay_type` |
| .fast5 | 12,509 | `No rule determined a value for assay_type` |
| .bed | 11,511 | `No rule determined a value for assay_type` |
| .cram | 10,623 | `No rule determined a value for assay_type` |
| .crai | 10,317 | `No reason recorded` |
| .bam | 4,675 | `No rule determined a value for assay_type` |
| .pvar | 2,854 | `No rule determined a value for assay_type` |
| .psam | 2,854 | `No rule determined a value for assay_type` |
| .pgen | 2,854 | `No rule determined a value for assay_type` |
| .bai | 2,742 | `No reason recorded` |
| .g.vcf | 2,504 | `No rule determined a value for assay_type` |
| .gff3 | 1,565 | `No rule determined a value for assay_type` |
| .chain | 926 | `No rule determined a value for assay_type` |
| .tsv | 899 | `No rule determined a value for assay_type` |
| .fai | 477 | `No reason recorded` |
| .gzi | 466 | `No reason recorded` |
| .bigwig | 462 | `No rule determined a value for assay_type` |
| .sizes | 458 | `No rule determined a value for assay_type` |
| .paf | 297 | `No rule determined a value for assay_type` |
| .sam | 192 | `No rule determined a value for assay_type` |
| .csv | 21 | `No rule determined a value for assay_type` |
| .pod5 | 11 | `No rule determined a value for assay_type` |
| .dict | 9 | `No rule determined a value for assay_type` |
| .pbi | 7 | `No reason recorded` |
| .snarls | 6 | `No rule determined a value for assay_type` |
| .gg | 6 | `No rule determined a value for assay_type` |
| .min | 6 | `No rule determined a value for assay_type` |
| .dist | 6 | `No rule determined a value for assay_type` |
| .trans | 6 | `No rule determined a value for assay_type` |
| .hal | 2 | `No rule determined a value for assay_type` |
| .hapl | 2 | `No rule determined a value for assay_type` |
| .delta | 1 | `No rule determined a value for assay_type` |

| Assay Type | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 679,943 | 96.0% | .vcf (201,668)<br>.tbi (169,531)<br>(none) (134,541)<br>.txt (42,479)<br>.csi (41,186)<br>.fastq (21,270)<br>.fast5 (12,509)<br>.bed (11,511)<br>.cram (10,623)<br>.crai (10,317)<br>.bam (4,675)<br>.pvar (2,854)<br>.psam (2,854)<br>.pgen (2,854)<br>.bai (2,742)<br>.g.vcf (2,504)<br>.gff3 (1,565)<br>.chain (926)<br>.tsv (899)<br>.fai (477)<br>.gzi (466)<br>.bigwig (462)<br>.sizes (458)<br>.paf (297)<br>.sam (192)<br>.csv (21)<br>.pod5 (11)<br>.dict (9)<br>.pbi (7)<br>.snarls (6)<br>.gg (6)<br>.min (6)<br>.dist (6)<br>.trans (6)<br>.hal (2)<br>.hapl (2)<br>.delta (1) |
| `not_applicable` | 22,290 | 3.1% | .md5 (14,233)<br>.log (3,637)<br>.png (3,074)<br>.fa (940)<br>.gfa (326)<br>.fasta (38)<br>.tsv (24)<br>.xg (8)<br>.gbwt (6)<br>.fna (2)<br>.gbz (2) |
| `RNA-seq` | 5,281 | 0.7% | .bw (2,536)<br>.bam (2,099)<br>.sf (634)<br>.bed (12) |
| `sc/snRNA-seq` | 414 | 0.1% | .h5ad (350)<br>(none) (64) |
| `Genotyping array` | 160 | 0.0% | .idat (160) |

**Note**: Like platform, assay type is inherently unknowable for most derived formats. It is determined only by a rule that sees evidence of the assay: a STAR `@PG` line, filename patterns (STAR, Salmon, expression BED), an IDAT's header, whose chip type and probe count name the BeadChip (#603), and extension where the format implies it (`.svs` histology, a `.h5ad` / `.loom` / `.mtx` single-cell matrix `sc/snRNA-seq`, and a tar whose members are one of these, #533). Nothing infers it from the modality (#88), reads file size, or infers WGS from a long-read platform (#430). The high not-classified rate is expected.

---

## Instrument Model

| | count | % |
|---|---:|---:|
| **Classified** | 23,202 | 3.3% |
| **Not classified** | 684,886 | 96.7% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf | 201,668 | `No rule determined a value for instrument_model` |
| .tbi | 169,531 | `No reason recorded` |
| (none) | 134,605 | `No rule determined a value for instrument_model` |
| .txt | 42,479 | `No rule determined a value for instrument_model` |
| .csi | 41,186 | `No reason recorded` |
| .fastq | 21,270 | `No rule determined a value for instrument_model` |
| .fast5 | 12,509 | `No rule determined a value for instrument_model` |
| .bed | 11,523 | `No rule determined a value for instrument_model` |
| .cram | 10,555 | `No rule determined a value for instrument_model` |
| .crai | 10,317 | `No reason recorded` |
| .bam | 6,090 | `No rule determined a value for instrument_model` |
| .pvar | 2,854 | `No rule determined a value for instrument_model` |
| .psam | 2,854 | `No rule determined a value for instrument_model` |
| .pgen | 2,854 | `No rule determined a value for instrument_model` |
| .bai | 2,742 | `No reason recorded` |
| .bw | 2,536 | `No rule determined a value for instrument_model` |
| .g.vcf | 2,504 | `No rule determined a value for instrument_model` |
| .gff3 | 1,565 | `No rule determined a value for instrument_model` |
| .chain | 926 | `No rule determined a value for instrument_model` |
| .tsv | 899 | `No rule determined a value for instrument_model` |
| .sf | 634 | `No rule determined a value for instrument_model` |
| .fai | 477 | `No reason recorded` |
| .gzi | 466 | `No reason recorded` |
| .bigwig | 462 | `No rule determined a value for instrument_model` |
| .sizes | 458 | `No rule determined a value for instrument_model` |
| .h5ad | 350 | `No rule determined a value for instrument_model` |
| .paf | 297 | `No rule determined a value for instrument_model` |
| .sam | 192 | `No rule determined a value for instrument_model` |
| .csv | 21 | `No rule determined a value for instrument_model` |
| .pod5 | 11 | `No rule determined a value for instrument_model` |
| .dict | 9 | `No rule determined a value for instrument_model` |
| .pbi | 7 | `No reason recorded` |
| .snarls | 6 | `No rule determined a value for instrument_model` |
| .gg | 6 | `No rule determined a value for instrument_model` |
| .min | 6 | `No rule determined a value for instrument_model` |
| .dist | 6 | `No rule determined a value for instrument_model` |
| .trans | 6 | `No rule determined a value for instrument_model` |
| .hal | 2 | `No rule determined a value for instrument_model` |
| .hapl | 2 | `No rule determined a value for instrument_model` |
| .delta | 1 | `No rule determined a value for instrument_model` |

| Instrument Model | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 684,886 | 96.7% | .vcf (201,668)<br>.tbi (169,531)<br>(none) (134,605)<br>.txt (42,479)<br>.csi (41,186)<br>.fastq (21,270)<br>.fast5 (12,509)<br>.bed (11,523)<br>.cram (10,555)<br>.crai (10,317)<br>.bam (6,090)<br>.pvar (2,854)<br>.psam (2,854)<br>.pgen (2,854)<br>.bai (2,742)<br>.bw (2,536)<br>.g.vcf (2,504)<br>.gff3 (1,565)<br>.chain (926)<br>.tsv (899)<br>.sf (634)<br>.fai (477)<br>.gzi (466)<br>.bigwig (462)<br>.sizes (458)<br>.h5ad (350)<br>.paf (297)<br>.sam (192)<br>.csv (21)<br>.pod5 (11)<br>.dict (9)<br>.pbi (7)<br>.snarls (6)<br>.gg (6)<br>.min (6)<br>.dist (6)<br>.trans (6)<br>.hal (2)<br>.hapl (2)<br>.delta (1) |
| `not_applicable` | 22,290 | 3.1% | .md5 (14,233)<br>.log (3,637)<br>.png (3,074)<br>.fa (940)<br>.gfa (326)<br>.fasta (38)<br>.tsv (24)<br>.xg (8)<br>.gbwt (6)<br>.fna (2)<br>.gbz (2) |
| `Revio` | 684 | 0.1% | .bam (684) |
| `Illumina iScan` | 160 | 0.0% | .idat (160) |
| `Illumina NovaSeq X` | 68 | 0.0% | .cram (68) |

**Note**: Inference reads the instrument model from a BAM/CRAM `@RG PM` value that names exactly one model (#532) and from an IDAT's run log naming the iScan's software (#603); a read-name serial prefix is a vendor numbering convention and is not read. Most files carry no such value, so the high not-classified rate is expected. This report reads inference only; the submitter tables, which reconcile reads, name models far more often.

---

## Variant Kind

| | count | % |
|---|---:|---:|
| **Classified** | 325,529 | 46.0% |
| **Not classified** | 382,559 | 54.0% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .tbi | 169,531 | `No reason recorded` |
| (none) | 134,605 | `No rule determined a value for variant_kind` |
| .csi | 41,186 | `No reason recorded` |
| .crai | 10,317 | `No reason recorded` |
| .txt | 4,929 | `No rule determined a value for variant_kind` |
| .pvar | 2,854 | `not a VCF: a PLINK 2 .pvar records no step of its own` |
| .psam | 2,854 | `No rule determined a value for variant_kind` |
| .pgen | 2,854 | `No rule determined a value for variant_kind` |
| .bed | 2,771 | `No rule determined a value for variant_kind` |
| .bai | 2,742 | `No reason recorded` |
| .vcf | 1,763 | `no caller on the step chain: no one step made this file (no_single_end); the header records 0 other tools` |
| .gff3 | 1,565 | `No rule determined a value for variant_kind` |
| .chain | 926 | `No rule determined a value for variant_kind` |
| .tsv | 899 | `No rule determined a value for variant_kind` |
| .fai | 477 | `No reason recorded` |
| .gzi | 466 | `No reason recorded` |
| .bigwig | 462 | `No rule determined a value for variant_kind` |
| .sizes | 458 | `No rule determined a value for variant_kind` |
| .gfa | 326 | `No rule determined a value for variant_kind` |
| .paf | 297 | `No rule determined a value for variant_kind` |
| .sam | 192 | `No rule determined a value for variant_kind` |
| .csv | 18 | `No rule determined a value for variant_kind` |
| .dict | 9 | `No rule determined a value for variant_kind` |
| .xg | 8 | `No rule determined a value for variant_kind` |
| .pbi | 7 | `No reason recorded` |
| .snarls | 6 | `No rule determined a value for variant_kind` |
| .gg | 6 | `No rule determined a value for variant_kind` |
| .min | 6 | `No rule determined a value for variant_kind` |
| .dist | 6 | `No rule determined a value for variant_kind` |
| .trans | 6 | `No rule determined a value for variant_kind` |
| .gbwt | 6 | `No rule determined a value for variant_kind` |
| .hal | 2 | `No rule determined a value for variant_kind` |
| .gbz | 2 | `No rule determined a value for variant_kind` |
| .hapl | 2 | `No rule determined a value for variant_kind` |
| .delta | 1 | `No rule determined a value for variant_kind` |

| Variant Kind | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 382,559 | 54.0% | .tbi (169,531)<br>(none) (134,605)<br>.csi (41,186)<br>.crai (10,317)<br>.txt (4,929)<br>.pvar (2,854)<br>.psam (2,854)<br>.pgen (2,854)<br>.bed (2,771)<br>.bai (2,742)<br>.vcf (1,763)<br>.gff3 (1,565)<br>.chain (926)<br>.tsv (899)<br>.fai (477)<br>.gzi (466)<br>.bigwig (462)<br>.sizes (458)<br>.gfa (326)<br>.paf (297)<br>.sam (192)<br>.csv (18)<br>.dict (9)<br>.xg (8)<br>.pbi (7)<br>.snarls (6)<br>.gg (6)<br>.min (6)<br>.dist (6)<br>.trans (6)<br>.gbwt (6)<br>.hal (2)<br>.gbz (2)<br>.hapl (2)<br>.delta (1) |
| `small` | 202,256 | 28.6% | .vcf (199,752)<br>.g.vcf (2,504) |
| `not_applicable` | 123,120 | 17.4% | .txt (37,550)<br>.fastq (21,270)<br>.md5 (14,233)<br>.fast5 (12,509)<br>.cram (10,623)<br>.bed (8,752)<br>.bam (6,774)<br>.log (3,637)<br>.png (3,074)<br>.bw (2,536)<br>.fa (940)<br>.sf (634)<br>.h5ad (350)<br>.idat (160)<br>.fasta (38)<br>.tsv (24)<br>.pod5 (11)<br>.csv (3)<br>.fna (2) |
| `structural` | 153 | 0.0% | .vcf (153) |

**Note**: Read from the caller that made a VCF: its header's producing step, walked back through steps that keep the kind, or a `##source` naming one tool, looked up in `rules/callers.yaml` (#654). Not applicable to a file whose rule says it holds no variants. An index or a GenomicsDB workspace takes its parent's kind only at reconcile, which this report does not read.

---

## Variant Origin

| | count | % |
|---|---:|---:|
| **Classified** | 325,541 | 46.0% |
| **Not classified** | 382,547 | 54.0% |
| **Conflict** | 0 | 0.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .tbi | 169,531 | `No reason recorded` |
| (none) | 134,605 | `No rule determined a value for variant_origin` |
| .csi | 41,186 | `No reason recorded` |
| .crai | 10,317 | `No reason recorded` |
| .txt | 4,929 | `No rule determined a value for variant_origin` |
| .pvar | 2,854 | `not a VCF: a PLINK 2 .pvar records no step of its own` |
| .psam | 2,854 | `No rule determined a value for variant_origin` |
| .pgen | 2,854 | `No rule determined a value for variant_origin` |
| .bed | 2,771 | `No rule determined a value for variant_origin` |
| .bai | 2,742 | `No reason recorded` |
| .vcf | 1,751 | `no caller on the step chain: no one step made this file (no_single_end); the header records 0 other tools` |
| .gff3 | 1,565 | `No rule determined a value for variant_origin` |
| .chain | 926 | `No rule determined a value for variant_origin` |
| .tsv | 899 | `No rule determined a value for variant_origin` |
| .fai | 477 | `No reason recorded` |
| .gzi | 466 | `No reason recorded` |
| .bigwig | 462 | `No rule determined a value for variant_origin` |
| .sizes | 458 | `No rule determined a value for variant_origin` |
| .gfa | 326 | `No rule determined a value for variant_origin` |
| .paf | 297 | `No rule determined a value for variant_origin` |
| .sam | 192 | `No rule determined a value for variant_origin` |
| .csv | 18 | `No rule determined a value for variant_origin` |
| .dict | 9 | `No rule determined a value for variant_origin` |
| .xg | 8 | `No rule determined a value for variant_origin` |
| .pbi | 7 | `No reason recorded` |
| .snarls | 6 | `No rule determined a value for variant_origin` |
| .gg | 6 | `No rule determined a value for variant_origin` |
| .min | 6 | `No rule determined a value for variant_origin` |
| .dist | 6 | `No rule determined a value for variant_origin` |
| .trans | 6 | `No rule determined a value for variant_origin` |
| .gbwt | 6 | `No rule determined a value for variant_origin` |
| .hal | 2 | `No rule determined a value for variant_origin` |
| .gbz | 2 | `No rule determined a value for variant_origin` |
| .hapl | 2 | `No rule determined a value for variant_origin` |
| .delta | 1 | `No rule determined a value for variant_origin` |

| Variant Origin | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 382,547 | 54.0% | .tbi (169,531)<br>(none) (134,605)<br>.csi (41,186)<br>.crai (10,317)<br>.txt (4,929)<br>.pvar (2,854)<br>.psam (2,854)<br>.pgen (2,854)<br>.bed (2,771)<br>.bai (2,742)<br>.vcf (1,751)<br>.gff3 (1,565)<br>.chain (926)<br>.tsv (899)<br>.fai (477)<br>.gzi (466)<br>.bigwig (462)<br>.sizes (458)<br>.gfa (326)<br>.paf (297)<br>.sam (192)<br>.csv (18)<br>.dict (9)<br>.xg (8)<br>.pbi (7)<br>.snarls (6)<br>.gg (6)<br>.min (6)<br>.dist (6)<br>.trans (6)<br>.gbwt (6)<br>.hal (2)<br>.gbz (2)<br>.hapl (2)<br>.delta (1) |
| `germline` | 202,421 | 28.6% | .vcf (199,917)<br>.g.vcf (2,504) |
| `not_applicable` | 123,120 | 17.4% | .txt (37,550)<br>.fastq (21,270)<br>.md5 (14,233)<br>.fast5 (12,509)<br>.cram (10,623)<br>.bed (8,752)<br>.bam (6,774)<br>.log (3,637)<br>.png (3,074)<br>.bw (2,536)<br>.fa (940)<br>.sf (634)<br>.h5ad (350)<br>.idat (160)<br>.fasta (38)<br>.tsv (24)<br>.pod5 (11)<br>.csv (3)<br>.fna (2) |

**Note**: Germline or somatic, read from the caller that made a VCF, found as for the kind and looked up in `rules/callers.yaml` (#658). A caller with a somatic mode (Sniffles2) gives its origin only where its command line shows the mode was off. Not applicable to a file whose rule says it holds no variants. An index or a GenomicsDB workspace takes its parent's origin only at reconcile, which this report does not read.

