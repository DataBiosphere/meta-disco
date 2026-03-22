# AnVIL Classification Coverage Report

Coverage of 541,169 classified file records across 5 dimensions.
Classification run: **2026-03-22 10:16:42**

**Classified** includes all files with a determined value, including `not_applicable` (e.g., FASTQ files have no reference assembly). **Not classified** means no rule or signal could determine a value.

| Dimension | Classified | Not Classified |
|---|---:|---:|
| **Data Modality** | 520,112 (96.1%) | 21,057 (3.9%) |
| **Data Type** | 538,320 (99.5%) | 2,849 (0.5%) |
| **Reference Assembly** | 535,900 (99.0%) | 5,269 (1.0%) |
| **Platform** | 98,805 (18.3%) | 442,364 (81.7%) |
| **Assay Type** | 81,083 (15.0%) | 460,086 (85.0%) |

---

## Data Modality

| | count | % |
|---|---:|---:|
| **Classified** | 520,112 | 96.1% |
| **Not classified** | 21,057 | 3.9% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .fastq.gz | 20,621 | FASTQ modality cannot be determined from reads alone — could be genomic, transcriptomic, or epigenomic depending on assay |
| .bam | 357 | No rule determined a value for data_modality |
| .tbi | 60 | Parent file had no value for this field |
| .bai | 19 | Parent file had no value for this field |

| Data Modality | count | % | extensions |
|---|---:|---:|---|
| `genomic` | 478,734 | 88.5% | .vcf.gz (201,860)<br>.tbi (169,463)<br>.csi (41,138)<br>.fast5 (12,394)<br>.cram (10,829)<br>.crai (10,319)<br>.bed.gz (7,191)<br>.bam (6,063)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.g.vcf.gz (2,504)<br>.fastq.gz (2,412)<br>.fa.gz (1,633)<br>.pbi (1,102)<br>.bai (1,061)<br>.bed (1,059)<br>.vcf (646)<br>.fast5.tar (273)<br>.fasta.gz (93)<br>.fastq (56)<br>.fasta (37)<br>.fast5.tar.gz (26)<br>.pod5 (11)<br>.fa (2) |
| `imaging.histology` | 25,708 | 4.8% | .svs (25,708) |
| `not_classified` | 20,997 | 3.9% | .fastq.gz (20,621)<br>.bam (357)<br>.bai (19) |
| `not_applicable` | 13,419 | 2.5% | .png (8,049)<br>.bed (5,370) |
| `transcriptomic.bulk` | 2,216 | 0.4% | .bam (1,413)<br>.bai (779)<br>.bed.gz (12)<br>.tbi (12) |
| `None` | 60 | 0.0% | .tbi (60) |
| `epigenomic.methylation` | 28 | 0.0% | .bed.gz (28) |
| `epigenomic.chromatin_accessibility` | 6 | 0.0% | .fastq.gz (6) |
| `transcriptomic.single_cell` | 1 | 0.0% | .fastq.gz (1) |

---

## Data Type

| | count | % |
|---|---:|---:|
| **Classified** | 538,320 | 99.5% |
| **Not classified** | 2,849 | 0.5% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .bam | 2,065 | No rule determined a value for data_type |
| .pbi | 677 | Parent file had no value for this field |
| .tbi | 60 | Parent file had no value for this field |
| .bai | 47 | Parent file had no value for this field |

| Data Type | count | % | extensions |
|---|---:|---:|---|
| `variants.germline` | 317,745 | 58.7% | .tbi (158,887)<br>.vcf.gz (158,858) |
| `variants` | 90,143 | 16.7% | .vcf.gz (42,947)<br>.csi (34,141)<br>.tbi (10,546)<br>.g.vcf.gz (2,504)<br>.vcf (5) |
| `images` | 33,757 | 6.2% | .svs (25,708)<br>.png (8,049) |
| `alignments` | 29,153 | 5.4% | .cram (10,829)<br>.crai (10,319)<br>.bam (5,768)<br>.bai (1,812)<br>.pbi (425) |
| `reads` | 23,096 | 4.3% | .fastq.gz (23,040)<br>.fastq (56) |
| `annotations` | 20,673 | 3.8% | .bed.gz (7,231)<br>.csi (6,997)<br>.bed (6,429)<br>.tbi (16) |
| `raw_signal` | 12,704 | 2.3% | .fast5 (12,394)<br>.fast5.tar (273)<br>.fast5.tar.gz (26)<br>.pod5 (11) |
| `genotypes` | 8,562 | 1.6% | .pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854) |
| `not_classified` | 2,789 | 0.5% | .bam (2,065)<br>.pbi (677)<br>.bai (47) |
| `assembly` | 1,747 | 0.3% | .fa.gz (1,631)<br>.fasta.gz (90)<br>.fasta (25)<br>.fa (1) |
| `variants.structural` | 722 | 0.1% | .vcf (641)<br>.vcf.gz (55)<br>.tbi (26) |
| `None` | 60 | 0.0% | .tbi (60) |
| `sequence` | 16 | 0.0% | .fasta (10)<br>.fasta.gz (3)<br>.fa.gz (2)<br>.fa (1) |
| `reference_genome` | 2 | 0.0% | .fasta (2) |

---

## Reference Assembly

| | count | % |
|---|---:|---:|
| **Classified** | 535,900 | 99.0% |
| **Not classified** | 5,269 | 1.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf.gz | 2,197 | No rule determined a value for reference_assembly |
| .csi | 1,968 | Parent file had no value for this field |
| .bam | 277 | No rule determined a value for reference_assembly |
| .bai | 274 | Parent file had no value for this field |
| .tbi | 266 | Parent file had no value for this field |
| .vcf | 252 | No rule determined a value for reference_assembly |
| .bed.gz | 31 | No rule determined a value for reference_assembly |
| .fasta | 3 | No rule determined a value for reference_assembly |
| .bed | 1 | No rule determined a value for reference_assembly |

| Reference Assembly | count | % | extensions |
|---|---:|---:|---|
| `CHM13` | 408,814 | 75.5% | .vcf.gz (190,224)<br>.tbi (159,059)<br>.csi (37,922)<br>.bed.gz (6,723)<br>.cram (6,718)<br>.crai (6,715)<br>.bam (427)<br>.bed (413)<br>.bai (393)<br>.vcf (208)<br>.fasta (6)<br>.fasta.gz (3)<br>.fa.gz (2)<br>.fa (1) |
| `not_applicable` | 82,099 | 15.2% | .svs (25,708)<br>.fastq.gz (23,040)<br>.fast5 (12,394)<br>.png (8,049)<br>.bed (4,830)<br>.bam (4,653)<br>.fa.gz (1,631)<br>.pbi (1,102)<br>.fast5.tar (273)<br>.bed.gz (188)<br>.fasta.gz (90)<br>.fastq (56)<br>.fast5.tar.gz (26)<br>.fasta (25)<br>.bai (22)<br>.pod5 (11)<br>.fa (1) |
| `GRCh38` | 44,971 | 8.3% | .tbi (10,210)<br>.vcf.gz (9,431)<br>.cram (4,111)<br>.crai (3,604)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.g.vcf.gz (2,504)<br>.bam (2,476)<br>.csi (1,248)<br>.bed (1,180)<br>.bai (1,170)<br>.bed.gz (289)<br>.vcf (183)<br>.fasta (3) |
| `not_classified` | 5,209 | 1.0% | .vcf.gz (2,197)<br>.csi (1,968)<br>.bam (277)<br>.bai (274)<br>.vcf (252)<br>.tbi (206)<br>.bed.gz (31)<br>.fasta (3)<br>.bed (1) |
| `None` | 60 | 0.0% | .tbi (60) |
| `GRCh37` | 16 | 0.0% | .vcf.gz (8)<br>.bed (5)<br>.vcf (3) |

---

## Platform

| | count | % |
|---|---:|---:|
| **Classified** | 98,805 | 18.3% |
| **Not classified** | 442,364 | 81.7% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf.gz | 201,860 | No rule determined a value for platform |
| .tbi | 169,535 | Parent file had no value for this field |
| .csi | 41,138 | Parent file had no value for this field |
| .bed.gz | 7,231 | No rule determined a value for platform |
| .bed | 6,429 | No rule determined a value for platform |
| .bam | 2,960 | No rule determined a value for platform |
| .pgen | 2,854 | No rule determined a value for platform |
| .pvar | 2,854 | No rule determined a value for platform |
| .psam | 2,854 | No rule determined a value for platform |
| .g.vcf.gz | 2,504 | No rule determined a value for platform |
| .bai | 1,499 | Parent file had no value for this field |
| .vcf | 646 | No rule determined a value for platform |

| Platform | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 442,304 | 81.7% | .vcf.gz (201,860)<br>.tbi (169,475)<br>.csi (41,138)<br>.bed.gz (7,231)<br>.bed (6,429)<br>.bam (2,960)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.g.vcf.gz (2,504)<br>.bai (1,499)<br>.vcf (646) |
| `ILLUMINA` | 41,776 | 7.7% | .fastq.gz (20,628)<br>.cram (10,829)<br>.crai (10,319) |
| `not_applicable` | 35,522 | 6.6% | .svs (25,708)<br>.png (8,049)<br>.fa.gz (1,633)<br>.fasta.gz (93)<br>.fasta (37)<br>.fa (2) |
| `ONT` | 15,556 | 2.9% | .fast5 (12,394)<br>.bam (1,509)<br>.fastq.gz (1,278)<br>.fast5.tar (273)<br>.bai (65)<br>.fast5.tar.gz (26)<br>.pod5 (11) |
| `PACBIO` | 5,951 | 1.1% | .bam (3,364)<br>.fastq.gz (1,134)<br>.pbi (1,102)<br>.bai (295)<br>.fastq (56) |
| `None` | 60 | 0.0% | .tbi (60) |

**Note**: Platform is inherently unknowable for most derived formats (VCF, BED, PLINK). Only BAM/CRAM (via `@RG PL` header) and FASTQ (via read name patterns) can encode platform. The high not-classified rate is expected.

---

## Assay Type

| | count | % |
|---|---:|---:|
| **Classified** | 81,083 | 15.0% |
| **Not classified** | 460,086 | 85.0% |

### What's not classified?

| extension | count | reason (from evidence) |
|---|---:|---|
| .vcf.gz | 201,860 | No rule determined a value for assay_type |
| .tbi | 169,523 | Parent file had no value for this field |
| .csi | 41,138 | Parent file had no value for this field |
| .fastq.gz | 20,621 | No rule determined a value for assay_type |
| .bed.gz | 7,191 | No rule determined a value for assay_type |
| .bed | 6,429 | No rule determined a value for assay_type |
| .pgen | 2,854 | No rule determined a value for assay_type |
| .pvar | 2,854 | No rule determined a value for assay_type |
| .psam | 2,854 | No rule determined a value for assay_type |
| .g.vcf.gz | 2,504 | No rule determined a value for assay_type |
| .bam | 1,215 | No rule determined a value for assay_type |
| .vcf | 646 | No rule determined a value for assay_type |
| .bai | 397 | Parent file had no value for this field |

| Assay Type | count | % | extensions |
|---|---:|---:|---|
| `not_classified` | 460,026 | 85.0% | .vcf.gz (201,860)<br>.tbi (169,463)<br>.csi (41,138)<br>.fastq.gz (20,621)<br>.bed.gz (7,191)<br>.bed (6,429)<br>.pgen (2,854)<br>.pvar (2,854)<br>.psam (2,854)<br>.g.vcf.gz (2,504)<br>.bam (1,215)<br>.vcf (646)<br>.bai (397) |
| `WGS` | 43,305 | 8.0% | .fast5 (12,394)<br>.cram (10,824)<br>.crai (10,319)<br>.bam (5,205)<br>.fastq.gz (2,412)<br>.pbi (1,102)<br>.bai (683)<br>.fast5.tar (273)<br>.fastq (56)<br>.fast5.tar.gz (26)<br>.pod5 (11) |
| `Histology` | 25,708 | 4.8% | .svs (25,708) |
| `not_applicable` | 9,814 | 1.8% | .png (8,049)<br>.fa.gz (1,633)<br>.fasta.gz (93)<br>.fasta (37)<br>.fa (2) |
| `RNA-seq` | 2,217 | 0.4% | .bam (1,413)<br>.bai (779)<br>.bed.gz (12)<br>.tbi (12)<br>.fastq.gz (1) |
| `None` | 60 | 0.0% | .tbi (60) |
| `Bisulfite-seq` | 28 | 0.0% | .bed.gz (28) |
| `ATAC-seq` | 6 | 0.0% | .fastq.gz (6) |
| `WES` | 5 | 0.0% | .cram (5) |

**Note**: Like platform, assay type is inherently unknowable for most derived formats. Only BAM/CRAM (via `@PG` programs and file size heuristics) and filename patterns can determine assay. The high not-classified rate is expected.

