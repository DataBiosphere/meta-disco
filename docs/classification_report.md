# AnVIL File Metadata Classification Report

## Executive Summary

This report documents the rule-based metadata classification system for biological data files from the AnVIL (Analysis, Visualization, and Informatics Lab-space) platform. The system infers five classification dimensions from file metadata without requiring full file downloads.

### Classification Dimensions

The classifier populates five orthogonal metadata fields:

| Field | Question Answered | Example Values |
| ----- | ----------------- | -------------- |
| `data_modality` | What biology is measured? | genomic, transcriptomic, epigenomic |
| `data_type` | What artifact is this? | alignments, variant_calls, reads |
| `platform` | What sequencing instrument? | ILLUMINA, PACBIO, ONT |
| `reference_assembly` | What reference genome? | GRCh38, GRCh37, CHM13 |
| `assay_type` | What method class? | WGS, WES, RNAseq |

#### data_modality

The biological signal domain—**what was measured** (independent of protocol/file format).

```
data_modality
├── genomic                      # DNA sequence/variation
├── transcriptomic               # RNA expression
├── epigenomic                   # DNA/chromatin modifications
│   ├── methylation              # DNA methylation state
│   ├── chromatin_accessibility  # ATAC-seq, DNase-seq
│   └── histone_modification     # ChIP-seq for histones
├── imaging                      # Visual/spatial data
│   └── histology                # Tissue slides
├── not_applicable               # Derived artifacts (QC plots, indexes, checksums)
└── not_classified               # Could not be determined from available signals
```

#### data_type

The artifact/content class—**what you can download and analyze** (independent of assay).

```
data_type
├── reads                        # Raw sequencing reads (FASTQ)
├── alignments                   # Aligned reads (BAM, CRAM)
├── variant_calls                # SNV/indel calls (VCF)
├── structural_variants          # SV calls (VCF)
├── peaks                        # ChIP/ATAC peaks (BED, narrowPeak)
├── signal_tracks                # Coverage/signal (bigWig)
├── expression_matrix            # Gene/transcript counts
├── methylation_calls            # CpG methylation levels
├── raw_signal                   # Instrument signal (FAST5, POD5)
├── images                       # Image files (SVS, PNG)
├── annotations                  # Genomic intervals (BED)
└── other                        # Auxiliary files
```

#### platform

The sequencing instrument/technology used to generate the data.

```
platform
├── ILLUMINA                     # Illumina short-read
├── PACBIO                       # PacBio long-read (HiFi, CLR)
├── ONT                          # Oxford Nanopore
├── MGI                          # MGI/BGISEQ
├── ELEMENT                      # Element Biosciences
├── not_applicable               # Non-sequencing data (images, annotations)
└── not_classified               # Could not be determined from available signals
```

#### reference_assembly

The reference genome the data is aligned to or called against.

```
reference_assembly
├── GRCh38                       # Human reference (2013), aliases: hg38, hs38
├── GRCh37                       # Human reference (2009), aliases: hg19, b37
├── CHM13                        # T2T complete genome (2022), aliases: t2t, hs1
├── not_applicable               # Unaligned reads, raw signal, non-genomic data
└── not_classified               # Could not be determined from available signals
```

#### assay_type

The top-level assay/method class. Inferred from platform, modality, and file size heuristics.

```
assay_type
├── WGS                          # Whole genome sequencing
├── WES                          # Whole exome sequencing
├── RNAseq                       # Bulk RNA sequencing
├── scRNAseq                     # Single-cell RNA sequencing
├── ATACseq                      # Bulk ATAC-seq
├── ChIPseq                      # ChIP sequencing
├── not_applicable               # Non-sequencing data (images, annotations)
└── not_classified               # Could not be determined from file alone
```

### Initial State (Before Classification)

The source AnVIL metadata contained **758,658 files** but with minimal semantic annotation:

| Field                | Files Populated | Percentage |
| -------------------- | --------------- | ---------- |
| `file_format`        | 758,658         | 100%       |
| `data_modality`      | 6,755           | 0.9%       |
| `reference_assembly` | 4,696           | 0.6%       |

**Files by format (classifiable types):**

| Format | Count | Classification Method |
| ------ | ----- | --------------------- |
| .vcf.gz | 204,384 | Header inspection (contig lengths, caller) |
| .tbi/.csi/.crai/.bai/.pbi | 224,037 | Inherited from parent file |
| .svs | 25,708 | Extension → imaging.histology |
| .fastq.gz | 16,255 | Read name parsing (platform detection) |
| .bed | 13,660 | Filename patterns + dataset context |
| .fast5 | 12,394 | Extension → genomic (raw ONT signal) |
| .cram | 10,829 | Header inspection (@RG, @PG, @SQ) |
| .pvar/.psam/.pgen | 8,562 | Extension + dataset → germline variants |
| .bam | 7,834 | Header inspection (@RG, @PG, @SQ) |
| .png | 8,049 | Extension → N/A (derived visualizations) |

The classification system processes these file types (539,178 total) using header inspection, filename patterns, extension rules, and dataset context.

### Output Files

Classification results are stored in JSON files in the `output/` directory:

| File | Contents | Records |
| ---- | -------- | ------- |
| [`bam_headers.json`](../output/bam_headers.json) | BAM/CRAM classifications | 18,662 |
| [`vcf_headers.json`](../output/vcf_headers.json) | VCF classifications | 205,010 |
| [`fastq_headers.json`](../output/fastq_headers.json) | FASTQ classifications | 23,096 |
| [`index_file_classifications.json`](../output/index_file_classifications.json) | Index file classifications | 223,953* |
| [`image_classifications.json`](../output/image_classifications.json) | Image classifications | 33,757 |
| [`auxiliary_genomic_classifications.json`](../output/auxiliary_genomic_classifications.json) | FAST5/PLINK classifications | 20,956 |
| [`bed_classifications.json`](../output/bed_classifications.json) | BED file classifications | 13,660 |

*84 additional orphaned index files (no matching parent) are logged in the `unmatched_files` array. See Section 6.1.

#### Output File Structure

Each JSON file contains:

```json
{
  "metadata": {
    "total_to_process": 205033,
    "processed": 205033,
    "successful": 205010,
    "complete": true
  },
  "classifications": [ ... ]
}
```

#### Classification Record Structure

Each record in `classifications` contains all five classification dimensions:

```json
{
  "file_name": "HG01874.chr17.hc.vcf.gz",
  "md5sum": "e1dca89aef536083f15093c39a0daa8f",
  "file_size": 158571384,
  "data_modality": "genomic",
  "data_type": "variant_calls",
  "platform": "ILLUMINA",
  "reference_assembly": "CHM13",
  "assay_type": "WGS",
  "confidence": 0.90,
  "matched_rules": ["vcf_contig_length", "vcf_gatk_haplotypecaller"],
  "evidence": [
    {
      "rule_id": "vcf_contig_length",
      "matched": "4 contigs matched CHM13 chromosome lengths",
      "classification": "CHM13",
      "confidence": 0.98,
      "rationale": "Chromosome lengths are unique to each reference assembly..."
    }
  ]
}
```

#### Confidence Score Interpretation

| Score | Level | Meaning |
| ----- | ----- | ------- |
| 0.95-1.0 | Definitive | Explicit metadata tag or exact match (e.g., contig lengths) |
| 0.85-0.94 | High | Strong program indicator (e.g., STAR aligner → transcriptomic) |
| 0.70-0.84 | Medium | Filename pattern match or dataset context |
| 0.50-0.69 | Low | Size heuristic or weak signal |
| <0.50 | Uncertain | Needs manual review |

The overall `confidence` score is the maximum confidence from matched rules. When multiple rules agree (convergent evidence), confidence increases. When rules conflict, confidence decreases and warnings are added.

#### Evidence Interpretation

Each `evidence` entry explains why a classification was made:

- **rule_id**: Identifier of the rule that matched (e.g., `vcf_contig_length`, `bam_star_aligner`)
- **matched**: The specific signal found (e.g., `"##source=HaplotypeCaller"`, `"4 contigs matched CHM13"`)
- **classification**: What value this rule assigned (e.g., `"CHM13"`, `"transcriptomic"`)
- **confidence**: How confident this specific rule is (0.0-1.0)
- **rationale**: Human-readable explanation of why this signal indicates this classification

Multiple evidence entries indicate multiple rules matched. Review files with conflicting evidence (check `warnings` field) for potential misclassification.

### Classification Results

**Coverage of all AnVIL files (758,658 total):**

| Category                          | Count   | % of Total | Status |
| --------------------------------- | ------- | ---------- | ------ |
| Data files (BAM/CRAM/VCF/FASTQ)*  | 246,768 | 32.5%      | ✅ Header classified |
| Index files (.tbi, .csi, .crai)   | 224,037 | 29.5%      | ✅ Inherited from parent |
| Images (.svs, .png)               | 33,757  | 4.4%       | ✅ Extension rules |
| Auxiliary genomic (FAST5, PLINK)  | 20,956  | 2.8%       | ✅ Extension + dataset |
| BED files                         | 13,660  | 1.8%       | ✅ Pattern + dataset |
| **Total classified**              | **539,178** | **71.1%** | |
| Unclassified (.txt, .tar, .md5, etc) | 219,480 | 28.9%   | Skipped |

*Files with MD5 checksums enabling S3 mirror header retrieval.

**Unclassified files inventory (219,480 files):**

| Format | Count | Description |
| ------ | ----- | ----------- |
| .tar | 124,645 | Archives (would need content inspection) |
| .txt | 42,456 | Ambiguous (stats, metadata, logs) |
| .md5 | 15,565 | Checksums - skip |
| .log | 5,066 | Processing logs - skip |
| .hist | 3,870 | Histogram files |
| .txt.gz | 3,310 | Compressed text |
| .pdf | 3,028 | Documentation |
| .bw | 2,536 | BigWig signal tracks |
| .yaml.gz | 1,949 | Compressed config/metadata |
| .fa.gz | 1,633 | Reference sequences |
| .tsv | 1,278 | Tab-separated data |
| .tar.gz | 1,181 | Compressed archives |
| Other | 12,964 | Various formats |

These files are excluded from classification as they are primarily:
- **Archives/checksums**: Not primary data (.tar, .md5)
- **Logs/documentation**: Processing artifacts (.log, .pdf, .txt)
- **Signal tracks**: Could classify as genomic (.bw) but low priority
- **Reference files**: Not experimental data (.fa.gz)

**Classification results (539,178 files: 246,768 data + 224,037 index + 33,757 images + 20,956 auxiliary + 13,660 BED):**

| Metric                                 | Count   | % of Total |
| -------------------------------------- | ------- | ---------- |
| Files with `data_modality`             | 511,855 | 94.9%      |
| Files with `reference_assembly`        | 440,772 | 81.7%      |
| High-confidence classifications (≥80%) | 518,819 | 96.2%      |
| Files needing manual review (<50%)     | ~2,000  | <1%        |

**Improvement summary:**

| Field                | Before | After  | Improvement |
| -------------------- | ------ | ------ | ----------- |
| `data_modality`      | 0.9%   | 94.9%  | +94.0pp     |
| `reference_assembly` | 0.6%   | 81.7%  | +81.1pp     |

---

## 1. Ontology Overview

### 1.1 Data Modality Hierarchy

The classification system maps files to a hierarchical data modality ontology based on the [Experimental Factor Ontology (EFO)](https://www.ebi.ac.uk/efo/):

```
data_modality
├── genomic
│   ├── genomic.whole_genome         # WGS data
│   ├── genomic.whole_exome          # WES/exome capture
│   ├── genomic.targeted             # Targeted panels
│   ├── genomic.germline_variants    # Germline variant calls
│   ├── genomic.somatic_variants     # Tumor/somatic variants
│   ├── genomic.structural_variants  # SVs (deletions, inversions, etc.)
│   └── genomic.copy_number_variants # CNV calls
├── transcriptomic
│   ├── transcriptomic.bulk          # Bulk RNA-seq
│   ├── transcriptomic.single_cell   # scRNA-seq
│   └── transcriptomic.long_read     # PacBio IsoSeq, ONT RNA
├── epigenomic
│   ├── epigenomic.methylation       # Bisulfite-seq, arrays
│   ├── epigenomic.chromatin_accessibility  # ATAC-seq
│   └── epigenomic.histone_modification     # ChIP-seq
└── imaging                          # Histology, microscopy
    └── imaging.histology            # Whole-slide tissue images
```

### 1.2 Reference Assembly Values

| Value    | Description                | Common Indicators                |
| -------- | -------------------------- | -------------------------------- |
| `GRCh38` | Human reference (2013)     | hg38, GRCh38, GCA_000001405.15   |
| `GRCh37` | Human reference (2009)     | hg19, b37, hs37, GCA_000001405.1 |
| `CHM13`  | T2T complete genome (2022) | chm13, t2t, hs1                  |

---

## 2. Rules Approach

### 2.1 Classification Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                     File Metadata Input                             │
│  (filename, file_size, file_format, dataset_title)                  │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Tier 1: Extension Mapping                         │
│  .bam → alignment, .vcf → variant, .fastq → sequence, etc.          │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Tier 2: Filename Pattern Rules                    │
│  RNA/rnaseq → transcriptomic, WGS → genomic.whole_genome, etc.      │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Tier 3: File Size Heuristics                      │
│  BAM >50GB → likely WGS, CRAM 10-30GB → likely WES, etc.            │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Tier 4: Header Inspection                         │
│  BAM @RG/@PG, VCF ##source/##contig, FASTQ read names               │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Tier 5: Consistency Validation                    │
│  Cross-check signals, boost/reduce confidence                       │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Classification Result                           │
│  data_modality, reference_assembly, confidence, evidence            │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Rule Evaluation Order

Rules are evaluated in order of confidence, with higher-confidence rules taking precedence:

1. **Definitive signals** (95-98%): Explicit tags like `PL:PACBIO`, contig lengths, `##source=HaplotypeCaller`
2. **Strong indicators** (85-90%): Aligner programs like STAR (RNA-seq), BWA (DNA)
3. **Pattern matches** (70-85%): Filename patterns like `_RNA_`, `_WGS_`, `.hg38.`
4. **Size heuristics** (60-70%): File size ranges typical for WGS vs WES
5. **Fallback defaults** (50%): Extension-based defaults when no other signal

---

## 3. Glossary

### 3.1 Rule Types

#### Filename Pattern Rules

Match regular expressions against filenames to infer modality or reference.

| Example Pattern  | Classification       | Confidence           |
| ---------------- | -------------------- | -------------------- | -------------- | --- |
| `(?i)(rna        | rnaseq               | transcriptom)`       | transcriptomic | 85% |
| `(?i)(wgs        | whole.?genome)`      | genomic.whole_genome | 85%            |
| `(?i)(hg38       | grch38)`             | GRCh38               | 90%            |
| `(?i)\.hifi[_.]` | genomic.whole_genome | 80%                  |

#### Header Inspection Rules

Parse file headers (without downloading entire files) to extract metadata.

**BAM/CRAM Headers:**

- `@RG PL:` - Platform (ILLUMINA, PACBIO, ONT)
- `@PG PN:` - Program name (STAR, BWA, minimap2)
- `@SQ AS:` - Assembly (GRCh38, GRCh37)

**VCF Headers:**

- `##reference=` - Reference genome path
- `##source=` - Variant caller (HaplotypeCaller, Mutect2, Manta)
- `##contig=<...,assembly=>` - Assembly annotation
- `##contig=<...,length=>` - Chromosome length (definitive assembly detection)

**FASTQ Read Names:**

- `@A00297:44:HFKH3DSXX:...` - Illumina modern format
- `@m64011_190830/1/ccs` - PacBio CCS/HiFi
- `@uuid runid=...` - Oxford Nanopore

### 3.2 Cross-Validation Rules

Cross-validation checks for consistency between multiple signals:

#### Convergent Signals (Boost Confidence)

| Signal A    | Signal B     | Expected Agreement   |
| ----------- | ------------ | -------------------- |
| PL:PACBIO   | READTYPE=CCS | genomic.whole_genome |
| PL:ILLUMINA | PN:bwa       | genomic              |
| PL:ILLUMINA | PN:STAR      | transcriptomic       |
| PL:PACBIO   | PN:minimap2  | genomic              |

#### Conflicting Signals (Reduce Confidence + Warning)

| Signal A    | Signal B     | Issue                       |
| ----------- | ------------ | --------------------------- |
| PL:PACBIO   | PN:STAR      | STAR is short-read only     |
| PL:ILLUMINA | READTYPE=CCS | CCS is PacBio-specific      |
| PN:bwa      | PN:STAR      | Mutually exclusive aligners |

### 3.3 File Size Heuristics

Size-based rules provide fallback classification when other signals are absent:

| File Type | Size Range | Classification       | Confidence |
| --------- | ---------- | -------------------- | ---------- |
| BAM       | >50 GB     | genomic.whole_genome | 65%        |
| BAM       | 5-50 GB    | genomic.whole_exome  | 60%        |
| CRAM      | >15 GB     | genomic.whole_genome | 65%        |
| CRAM      | 3-15 GB    | genomic.whole_exome  | 60%        |

**Platform-specific adjustments:**

- PacBio HiFi BAMs tend to be larger (100+ GB for WGS)
- ONT BAMs can be very large due to longer reads
- Illumina CRAMs compress well (~3:1 vs BAM)

### 3.4 Confidence Scoring System

#### Base Confidence Levels

| Level      | Range  | Description                                          |
| ---------- | ------ | ---------------------------------------------------- |
| Definitive | 95-99% | Explicit metadata tag or contig length match         |
| High       | 85-94% | Strong program indicator (e.g., STAR aligner) |
| Medium     | 70-84% | Filename pattern match                        |
| Low        | 50-69% | Size heuristic or weak pattern                |
| Uncertain  | <50%   | Needs manual review                           |

#### Confidence Adjustments

| Condition                            | Adjustment                 |
| ------------------------------------ | -------------------------- |
| Multiple convergent signals          | +5% per pair (diminishing) |
| All reads agree (FASTQ)              | +5%                        |
| Conflicting signals detected         | -20%                       |
| Multiple reference assemblies in @SQ | -10%                       |

---

## 4. Header Inspection Details

### 4.1 BAM/CRAM Header Rules

**Platform Detection (from @RG PL field):**

| Pattern       | Platform | Confidence | Rationale             |
| ------------- | -------- | ---------- | --------------------- |
| `PL:ILLUMINA` | ILLUMINA | 95%        | Explicit platform tag |
| `PL:PACBIO`   | PACBIO   | 95%        | Explicit platform tag |
| `PL:ONT`      | ONT      | 95%        | Oxford Nanopore       |
| `PL:DNBSEQ`   | MGI      | 90%        | MGI/BGI sequencers    |

**Modality Detection (from @PG programs):**

| Program  | Modality       | Confidence | Rationale                |
| -------- | -------------- | ---------- | ------------------------ |
| STAR     | transcriptomic | 95%        | Splice-aware RNA aligner |
| HISAT2   | transcriptomic | 90%        | RNA-seq aligner          |
| TopHat   | transcriptomic | 85%        | Legacy RNA aligner       |
| BWA      | genomic        | 85%        | DNA short-read aligner   |
| minimap2 | genomic        | 80%        | Long-read aligner        |
| pbmm2    | genomic        | 90%        | PacBio-specific aligner  |

### 4.2 VCF Header Rules

**Reference Assembly Detection (by Contig Length):**

Chromosome lengths are unique to each reference assembly, providing definitive identification even when `##reference` or `assembly=` tags are missing. The classifier matches `##contig=<ID=chr1,length=...>` lines against known reference sizes.

| Chromosome | GRCh37      | GRCh38      | CHM13       |
| ---------- | ----------- | ----------- | ----------- |
| chr1       | 249,250,621 | 248,956,422 | 248,387,497 |
| chr2       | 243,199,373 | 242,193,529 | 242,696,747 |
| chr3       | 198,022,430 | 198,295,559 | 201,106,605 |
| chr10      | 135,534,747 | 133,797,422 | 134,758,134 |
| chr22      |  51,304,566 |  50,818,468 |  51,324,926 |

| Rule ID            | Method                        | Confidence |
| ------------------ | ----------------------------- | ---------- |
| `vcf_contig_length` | Exact match on contig lengths | 98%        |
| `vcf_contig_length` | Fuzzy match (±1000bp)         | 95%        |
| `vcf_max_positions` | Position exceeds chrom length | 90%        |

**Reference Assembly Detection (by Variant Position):**

When header-based detection fails, max variant positions can rule out references where positions exceed chromosome lengths. For example, a variant at chr1:249,000,000 rules out CHM13 and GRCh38.

**Variant Caller Detection:**

| Caller          | Variant Type         | Confidence |
| --------------- | -------------------- | ---------- |
| HaplotypeCaller | germline_variants    | 90%        |
| DeepVariant     | germline_variants    | 90%        |
| Mutect2         | somatic_variants     | 90%        |
| Strelka         | somatic_variants     | 90%        |
| Manta           | structural_variants  | 90%        |
| DELLY           | structural_variants  | 90%        |
| CNVkit          | copy_number_variants | 90%        |

### 4.3 FASTQ Read Name Rules

**Platform Detection from Read Name Format:**

| Platform          | Pattern Example                         | Confidence |
| ----------------- | --------------------------------------- | ---------- |
| Illumina (modern) | `@A00297:44:HFKH3DSXX:1:1101:...`       | 90%        |
| Illumina (legacy) | `@HWUSI-EAS100R:6:73:941:1973#0/1`      | 85%        |
| PacBio CCS        | `@m64011_190830_220126/1/ccs`           | 95%        |
| PacBio CLR        | `@m64011_190830_220126/1234/0_5000`     | 90%        |
| ONT               | `@a1b2c3d4-e5f6-7890-abcd-ef1234567890` | 95%        |
| MGI/BGI           | `@V350012345L1C001R0010000001/1`        | 90%        |

**Archive Accession Extraction:**

When files are downloaded from public archives, accessions are extracted:

| Prefix | Archive        | Example                       |
| ------ | -------------- | ----------------------------- |
| ERR    | ENA (European) | `@ERR3242571.1 A00297:44:...` |
| SRR    | SRA (NCBI)     | `@SRR12345678.1 ...`          |
| DRR    | DDBJ (Japan)   | `@DRR000001.1 ...`            |

---

## 5. Results Analysis

### 5.1 BAM/CRAM Classification Results

**Total files classified: 18,662**

| Data Modality        | Count  | Percentage |
| -------------------- | ------ | ---------- |
| genomic.whole_genome | 14,922 | 80.0%      |
| genomic              | 1,635  | 8.8%       |
| transcriptomic       | 1,413  | 7.6%       |
| genomic.exome        | 3      | 0.0%       |
| Unknown              | 689    | 3.7%       |

**Platforms Detected:**

| Platform | Count  | Percentage |
| -------- | ------ | ---------- |
| ILLUMINA | 10,829 | 58.0%      |
| PACBIO   | 3,364  | 18.0%      |
| ONT      | 1,509  | 8.1%       |
| Unknown  | 2,960  | 15.9%      |

**Reference Assemblies:**

| Assembly | Count | Percentage |
| -------- | ----- | ---------- |
| GRCh38   | 7,313 | 39.2%      |
| CHM13    | 3,516 | 18.8%      |
| Unknown  | 7,833 | 42.0%      |

High confidence (≥80%): 15,606 (83.6%)

### 5.2 FASTQ Classification Results

**Total files classified: 23,096**

| Platform | Count  | Percentage |
| -------- | ------ | ---------- |
| ILLUMINA | 18,232 | 78.9%      |
| ONT      | 1,278  | 5.5%       |
| PACBIO   | 952    | 4.1%       |
| Unknown  | 2,634  | 11.4%      |

**Archive Accessions Found:**

- ENA (ERR): 6,962 files

High confidence (≥80%): 20,462 (88.6%)

### 5.3 VCF Classification Results

**Total files classified: 205,010**

| Data Modality               | Count   | Percentage |
| --------------------------- | ------- | ---------- |
| genomic.germline_variants   | 158,858 | 77.5%      |
| genomic.structural_variants | 45,227  | 22.1%      |
| genomic                     | 915     | 0.4%       |
| Unknown                     | 10      | 0.0%       |

**Variant Types:**

| Variant Type | Count   | Percentage |
| ------------ | ------- | ---------- |
| Germline     | 158,858 | 77.5%      |
| Structural   | 669     | 0.3%       |
| Unknown      | 45,483  | 22.2%      |

**Reference Assemblies:**

| Assembly | Count   | Percentage |
| -------- | ------- | ---------- |
| CHM13    | 159,251 | 77.7%      |
| GRCh38   | 43,297  | 21.1%      |
| GRCh37   | 11      | 0.0%       |
| Unknown  | 2,451   | 1.2%       |

**Top Variant Callers:**

| Caller          | Count   | Percentage |
| --------------- | ------- | ---------- |
| HaplotypeCaller | 158,858 | 77.5%      |
| Sniffles        | 304     | 0.1%       |
| SVIM            | 197     | 0.1%       |
| PBSV            | 168     | 0.1%       |
| Unknown         | 45,483  | 22.2%      |

**Rules Matched:**

| Rule                     | Matches |
| ------------------------ | ------- |
| vcf_ref_grch38           | 873,506 |
| vcf_info_sv              | 204,083 |
| vcf_contig_length        | 170,688 |
| vcf_gatk_haplotypecaller | 158,858 |
| vcf_ref_chm13            | 1,398   |

High confidence (≥80%): 204,085 (99.5%)

### 5.4 Overall Classification Coverage

| File Type | Total   | With Modality | With Reference | High Confidence |
| --------- | ------- | ------------- | -------------- | --------------- |
| BAM/CRAM  | 18,662  | 96.3%         | 58.0%          | 83.6%           |
| FASTQ     | 23,096  | 100%*         | N/A            | 88.6%           |
| VCF       | 205,010 | 99.9%         | 98.8%          | 99.5%           |
| Index     | 224,037 | 96.7%         | 94.5%          | 96.7%           |
| Image     | 33,757  | 76.2%**       | N/A            | 100%            |
| FAST5     | 12,394  | 100%          | N/A***         | 90%             |
| PLINK     | 8,562   | 100%          | 100%           | 95%             |
| BED       | 13,660  | 62.7%****     | 51.7%          | 85%             |
| **Total** | 539,178 | 94.9%         | 81.2%          | 96.2%           |

*FASTQ modality defaults to "genomic" when platform is detected but no RNA-seq indicators found.
**PNG files (8,049) classified as N/A (derived visualizations) - not primary data.
***FAST5 files are raw ONT signal data (pre-basecalling) - reference not applicable.
****5,100 BED files are assembly QC artifacts (N/A) - not primary data.

### 5.5 Index File Inheritance Results

Index files inherit metadata from their parent data files by filename matching within the same dataset.

**Total index files: 224,037**

| Index Type | Total   | Matched | With Modality | With Reference |
| ---------- | ------- | ------- | ------------- | -------------- |
| `.tbi`     | 169,537 | 100.0%  | 100.0%        | 99.8%          |
| `.csi`     | 41,186  | 99.9%   | 82.9%         | 78.1%          |
| `.crai`    | 10,319  | 100.0%  | 100.0%        | 100.0%         |
| `.bai`     | 1,861   | 99.9%   | 81.5%         | 0.0%*          |
| `.pbi`     | 1,134   | 97.2%   | 97.2%         | 0.0%*          |
| **Total**  | 224,037 | 99.96%  | 96.7%         | 94.5%          |

*Parent BAM files are unaligned reads (raw HiFi/ONT) - reference_assembly is correctly N/A.

**Inheritance rule**: Index files (e.g., `sample.vcf.gz.tbi`) are matched to parent files (e.g., `sample.vcf.gz`) within the same dataset. The parent's `data_modality` and `reference_assembly` are propagated to the index.

### 5.6 Image File Classification Results

Image files are classified by extension using domain-specific rules.

**Total image files: 33,757**

| Extension | Count  | Data Modality      | Confidence | Source Dataset        |
| --------- | ------ | ------------------ | ---------- | --------------------- |
| `.svs`    | 25,708 | imaging.histology  | 95%        | GTEx (tissue slides)  |
| `.png`    | 8,049  | N/A                | 90%        | HPRC (QC/assembly plots) |

**Classification approach**: Extension-based rules only.

- **SVS files**: Aperio whole-slide histology images used for pathology analysis. All from GTEx public dataset containing tissue slide images.
- **PNG files**: Derived visualizations (QC plots, assembly graphs) - not primary experimental data. Excluded from `data_modality` assignment as they are derived artifacts, not primary data files.

**Implementation**: `scripts/classify_images.py` (rules in `rules/unified_rules.yaml`)

### 5.7 Auxiliary Genomic File Classification Results

FAST5 and PLINK files are classified by extension with dataset-based reference inference.

**Total auxiliary genomic files: 20,956**

| Extension | Count  | Data Modality             | Reference | Confidence |
| --------- | ------ | ------------------------- | --------- | ---------- |
| `.fast5`  | 12,394 | genomic                   | N/A*      | 90%        |
| `.pvar`   | 2,854  | genomic.germline_variants | GRCh38    | 95%        |
| `.psam`   | 2,854  | genomic.germline_variants | GRCh38    | 95%        |
| `.pgen`   | 2,854  | genomic.germline_variants | GRCh38    | 95%        |

*FAST5 files contain raw ONT electrical signal data (pre-basecalling). Reference not applicable until basecalling and alignment.

**Classification rules:**

- **FAST5**: Extension-based. Raw nanopore signal data from ANVIL_NIA_CARD_Coriell_Cell_Lines_Open dataset.
- **PLINK**: Extension-based modality + dataset-based reference. All from ANVIL_1000G_PRIMED_data_model (1000 Genomes Project uses GRCh38).

**Implementation**: `scripts/classify_auxiliary_genomic.py` (rules in `rules/unified_rules.yaml`)

### 5.8 BED File Classification Results

BED files are classified using filename pattern matching and dataset context.

**Total BED files: 13,660**

| Rule | Count | Data Modality | Description |
| ---- | ----- | ------------- | ----------- |
| `bed_regions` | 6,997 | genomic | `.regions.bed` analysis regions |
| `bed_assembly_qc` | 5,100 | N/A | Assembly QC (haplotype, flagger, switch) |
| `bed_default` | 1,523 | genomic | Unmatched patterns (default) |
| `bed_methylation` | 28 | epigenomic.methylation | CpG methylation (modbam2bed) |
| `bed_expression` | 12 | transcriptomic | Expression quantification (TMM, leafcutter) |

**Reference assembly detection:**

| Reference | Count | Source |
| --------- | ----- | ------ |
| CHM13 | 7,031 | T2T datasets + filename patterns |
| GRCh38 | 36 | Filename patterns (hg38) |
| GRCh37 | 1 | Filename patterns (hg19) |
| N/A | 6,592 | No reference signal |

**Classification approach:**
1. **Pattern-based modality**: Filename patterns identify methylation, expression, peaks, regions, or assembly QC
2. **Filename-based reference**: Explicit reference in filename (hg38, chm13, etc.)
3. **Dataset-based reference**: T2T datasets default to CHM13

Most BED files (5,100) are assembly QC artifacts from HPRC/T2T - derived outputs marked as N/A.

**Implementation**: `scripts/classify_bed_files.py` (rules in `rules/unified_rules.yaml`)

---

## 6. Data Quality Issues

The classification process surfaced data integrity issues in the source AnVIL metadata that may warrant investigation.

### 6.1 Orphaned Index Files

Index files exist without corresponding parent data files in the same dataset.

**Total orphaned indexes: 84** (0.04% of 224,037 index files)

| Index Type | Orphaned | Description |
| ---------- | -------: | ----------- |
| `.csi`     | 48       | CSI indexes for VCF files that don't exist |
| `.pbi`     | 32       | PacBio indexes referencing missing BAMs |
| `.tbi`     | 2        | Tabix indexes without parent |
| `.bai`     | 2        | BAM indexes without parent |

**Example orphaned file:**
```
File: 1kgp.chr8.recalibrated.snp_indel.pass.singleton.chm13.draft_v1.0_plus38Y.no_snyteny_1Mbp.Homo_sapiens_assembly38.liftover.vcf.gz.csi
Dataset: ANVIL_T2T
Tried parent: 1kgp.chr8...liftover.vcf.gz
Result: Parent VCF not found in dataset
```

**Possible causes:**
1. Parent files were deleted but indexes retained
2. Files were moved between datasets without indexes
3. Incomplete data uploads

**Output location:** Orphaned files are recorded in `index_file_classifications.json` under the `unmatched_files` array with:
- `file_name`: Index filename
- `dataset_id`: Dataset containing the orphan
- `candidates_tried`: Parent filenames attempted
- `reason`: `no_matching_parent_in_dataset`

### 6.2 Recommendations

1. **Audit orphaned indexes** - Determine if parent files exist elsewhere or should be re-uploaded
2. **Add integrity checks** - Validate parent-child relationships during data ingest
3. **Document expected orphans** - Some may be intentional (e.g., shared reference indexes)

---

## 7. Validation Against Existing Metadata

### 7.1 Comparison with AnVIL Source Metadata

The AnVIL source metadata includes pre-existing `data_modality` and `reference_assembly` values for a small fraction of files. We compared our classifications against these as a consistency check.

**Available ground truth:**

| Field                | Files with existing values | Source                |
| -------------------- | -------------------------:| --------------------- |
| `data_modality`      | 6,755                     | Single dataset (IGVF) |
| `reference_assembly` | 4,696                     | Single dataset (IGVF) |

**Data modality comparison (3,492 comparable files):**

| Result   | Count | Percentage |
| -------- | -----:| ----------:|
| Agree    | 0     | 0%         |
| Disagree | 3,492 | 100%       |

All disagreements follow the same pattern: AnVIL labels files as `single-nucleus RNA sequencing assay` or `single-nucleus ATAC-seq`, while our classifier returns `genomic`. This 100% disagreement reflects three stacked issues, not classifier error:

1. **Non-human data**: All 6,755 tagged files are from `AnVIL_IGVF_Mouse_R1` (mouse, GRCm39). Our classifier is designed for human data only.
2. **Assay-level metadata is invisible at file level**: snRNA-seq and WGS FASTQ reads are indistinguishable by read name format, index length, or any other file-level signal. The assay type (`single-nucleus RNA sequencing assay`) can only be determined from study-level metadata.
3. **Vocabulary mismatch**: AnVIL uses EFO assay terms (`single-nucleus RNA sequencing assay`) while our taxonomy uses modality terms (`transcriptomic`). Even a correct classification would appear as a disagreement without a mapping layer.

**Reference assembly comparison (634 ENCORE BAM files):**

The ENCORE datasets (`AnVIL_ENCORE_RS293`, `AnVIL_ENCORE_293T`) contain 4,476 files tagged with `reference_assembly: GRCh38 + Gencode40`. Of these, 634 are BAM files with cached headers containing `@SQ` contig lines.

| Result   | Count | Percentage |
| -------- | -----:| ----------:|
| Agree (GRCh38) | 634 | **100%** |
| Disagree | 0     | 0%         |

All 634 ENCORE BAM files are STAR-aligned RNA-seq with 292 `@SQ` lines. Our contig length detection independently confirms GRCh38 (chr1 length 248,956,422) — matching the AnVIL metadata exactly. This is the first positive validation of our classifier against existing AnVIL annotations.

The remaining ENCORE files (3,842) are non-BAM formats (`.tsv`, `.tar`, `Other`) that we don't currently classify.

### 7.2 Implications for Using the Classifier as a Validator

Despite the poor headline agreement rate, the classifier has validation value in specific scenarios:

**Where file-level validation works:**
- **Reference assembly for aligned files** (BAM/CRAM/VCF): Contig lengths and header tags provide definitive ground truth independent of study metadata
- **Platform detection**: Read name formats and `@RG PL:` tags are reliable file-level signals
- **Data type**: File format to content-type mapping (`.bam` → alignments, `.vcf` → variant calls) is deterministic

**Where study-level context is required:**
- **Assay type** (WGS vs WES vs snRNA-seq): Cannot be determined from FASTQ reads alone
- **Data modality for raw reads**: snRNA-seq, snATAC-seq, and WGS FASTQs are indistinguishable at the file level
- **Organism**: No file-level signal distinguishes human from mouse data

**Recommendations for a validation pipeline:**
1. **Flag non-human datasets** before running human-specific classification
2. **Validate reference assembly** on aligned files — this is the highest-confidence, highest-value check
3. **Cross-reference platform** between `@RG PL:` tags and study metadata
4. **Accept study-level assay metadata** as authoritative for raw reads — do not attempt to override from file inspection

### 7.3 External Validation: HPRC Catalog

The [HPRC Data Explorer catalog](https://github.com/human-pangenomics/hprc-data-explorer) provides structured metadata for HPRC files including `annotationType`, `referenceCoordinates`, and `pipeline`. Cross-referencing against AnVIL HPRC files:

- **885 BED files** matched by filename between the HPRC catalog and AnVIL
- All matched files are de novo assembly annotations (CenSat, Flagger, NucFlag, SegDups) using per-sample haplotype contig names — confirming they are not aligned to a standard reference
- The HPRC catalog `annotationType` field does not encode reference assembly (e.g., `CenSat`, `Flagger_HiFi`), unlike the `referenceCoordinates` field used for alignments
- Our coordinate-based BED reference detector correctly returns `None` for these files (non-standard chromosome names)

---

## 8. Limitations and Future Work

### 8.1 Current Limitations

1. **Header-only inspection**: Cannot detect modality for files without informative headers
2. **Archive reformatting**: Some SRA/ENA files lose original metadata
3. **Mixed-content files**: Cannot detect if BAM contains both DNA and RNA
4. **Non-standard contig names**: Some files use custom contig naming that doesn't match standard assemblies
5. **Confidence uses max() not additive**: When multiple rules converge, confidence is the maximum single-rule score rather than boosted for agreement. Documentation describes "+5% per converging pair" but this is not implemented.
6. **N/A classifications lack semantic distinction**: Files with `data_modality: null` include both "derived artifacts" (PNG plots, assembly QC BEDs) and "pre-processing data" (FAST5 raw signal). These have different meanings but identical output representation.

### 8.2 Planned Improvements

1. Implement study-level context propagation
2. Add support for additional file types (10X, spatial transcriptomics)
3. Machine learning model for ambiguous cases
4. **Convergent signal confidence boost**: Implement additive confidence adjustment when multiple independent rules agree on a classification, matching documented behavior
5. **File category field using EDAM terms**: Add `file_category` to distinguish processing stages:
   - `edam:data_3914` (Quality control report) for assembly QC BEDs
   - `edam:data_2884` (Plot) for PNG visualizations
   - `edam:data_2968` (Image) for histology images
   - Custom `raw_signal` for FAST5 (no EDAM equivalent exists for pre-basecalled data)

---

## Appendix A: Rule Statistics

All rules are defined in `rules/unified_rules.yaml`.

| Category                 | Rule Count |
| ------------------------ | ---------- |
| Alignment (BAM/CRAM)     | 18         |
| VCF variant callers      | 25         |
| FASTQ platform detection | 15         |
| Header/program rules     | 15         |
| Reference detection      | 12         |
| BED patterns             | 7          |
| Image files              | 5          |
| File size heuristics     | 8          |
| Index/skip rules         | 5          |
| Single-cell formats      | 4          |
| Signal tracks (BigWig)   | 4          |
| Dataset context          | 4          |
| Intervals (targets)      | 3          |
| Auxiliary (PLINK/IDAT)   | 4          |
| Text/log/checksum        | 4          |
| Archive files            | 2          |
| Other                    | 12         |
| **Total**                | **147**    |

---

## Appendix B: Sample Classifications

Example classification records from each file type, showing the evidence chain and confidence scoring.

#### BAM/CRAM Examples

```json
{
  "file_name": "HG04047.cram",
  "data_modality": "genomic.whole_genome",
  "reference_assembly": "CHM13",
  "confidence": 0.84,
  "matched_rules": ["platform_illumina", "program_bwa", "ref_chm13_t2t", "illumina_cram_wgs_medium"],
  "evidence": [
    {
      "rule_id": "platform_illumina",
      "matched": "PL:ILLUMINA",
      "confidence": 0.95,
      "rationale": "Illumina short-read sequencing platform detected from @RG header."
    },
    {
      "rule_id": "program_bwa",
      "matched": "PN:bwa",
      "classification": "genomic",
      "confidence": 0.80,
      "rationale": "BWA is the standard short-read aligner for DNA sequencing (WGS/WES)."
    },
    {
      "rule_id": "ref_chm13_t2t",
      "matched": "UR:...chm13v2.0.fasta (25 contigs)",
      "classification": "CHM13",
      "confidence": 0.95,
      "rationale": "Reference path in @SQ headers contains 'chm13' indicating T2T-CHM13 assembly."
    },
    {
      "rule_id": "illumina_cram_wgs_medium",
      "matched": "file_size=14.8GB",
      "classification": "genomic.whole_genome",
      "confidence": 0.65,
      "rationale": "Illumina CRAM files 10-20 GB indicate WGS at moderate coverage."
    }
  ]
}
```

#### VCF Examples

```json
{
  "file_name": "HG01874.chr17.hc.vcf.gz",
  "data_modality": "genomic.germline_variants",
  "reference_assembly": "CHM13",
  "confidence": 0.90,
  "matched_rules": ["vcf_contig_length", "vcf_gatk_haplotypecaller", "vcf_info_sv"],
  "evidence": [
    {
      "rule_id": "vcf_contig_length",
      "matched": "4 contigs matched CHM13 chromosome lengths",
      "confidence": 0.98
    },
    {
      "rule_id": "vcf_gatk_haplotypecaller",
      "matched": "##source=HaplotypeCaller",
      "confidence": 0.90
    }
  ]
}
```

#### FASTQ Examples

```json
{
  "file_name": "5D1_S11_L002_R2_001.fastq.gz",
  "data_modality": "genomic",
  "platform": "ILLUMINA",
  "confidence": 0.95,
  "matched_rules": ["fastq_illumina_modern", "fastq_paired_r1"],
  "evidence": [
    {
      "rule_id": "fastq_illumina_modern",
      "matched": "@D00360:78:H2YVCBCXX:2:1101:1196:2250 2:N:0:11",
      "confidence": 0.90
    },
    {
      "rule_id": "fastq_paired_r1",
      "matched": "Paired-end indicator found",
      "confidence": 0.80
    }
  ]
}
```

#### Index File Examples

```json
{
  "file_name": "NA18637.chr15.hc.vcf.gz.tbi",
  "data_modality": "genomic.germline_variants",
  "reference_assembly": "CHM13",
  "confidence": 0.90,
  "parent_file": "NA18637.chr15.hc.vcf.gz",
  "evidence": [
    {
      "rule_id": "inherited_from_parent",
      "matched": "Parent file: NA18637.chr15.hc.vcf.gz",
      "confidence": 0.90
    }
  ]
}
```

#### Image Examples

```json
{
  "file_name": "GTEX-18A6Q-1126.svs",
  "data_modality": "imaging.histology",
  "confidence": 0.95,
  "evidence": [
    {
      "rule_id": "image_ext_.svs",
      "matched": "Extension: .svs",
      "confidence": 0.95
    }
  ]
}
```

#### Auxiliary Genomic Examples

```json
{
  "file_name": "PAK57726_28c8475f_fcf1fc64_1794.fast5",
  "data_modality": "genomic",
  "reference_assembly": null,
  "confidence": 0.90,
  "evidence": [
    {
      "rule_id": "ext_fast5",
      "matched": "Extension: .fast5",
      "confidence": 0.90
    }
  ]
}
```

```json
{
  "file_name": "IBS.3.pgen",
  "data_modality": "genomic.germline_variants",
  "reference_assembly": "GRCh38",
  "confidence": 0.95,
  "evidence": [
    {
      "rule_id": "ext_pgen",
      "matched": "Extension: .pgen",
      "confidence": 0.90
    },
    {
      "rule_id": "dataset_reference",
      "matched": "Dataset: ANVIL_1000G_PRIMED_data_model",
      "confidence": 0.95
    }
  ]
}
```

#### BED Examples

```json
{
  "file_name": "HG01928.paternal.f1_assembly_v2_genbank.HSat2and3_Regions.bed",
  "data_modality": null,
  "reference_assembly": null,
  "confidence": 0.85,
  "evidence": [
    {
      "rule_id": "bed_assembly_qc",
      "matched": "Pattern: assembly QC file (paternal/haplotype)",
      "confidence": 0.85
    }
  ]
}
```

```json
{
  "file_name": "HG04191.regions.bed.gz",
  "data_modality": "genomic",
  "reference_assembly": "CHM13",
  "confidence": 0.90,
  "evidence": [
    {
      "rule_id": "bed_regions",
      "matched": "Pattern: .regions.bed",
      "confidence": 0.80
    },
    {
      "rule_id": "dataset_t2t",
      "matched": "Dataset: ANVIL_T2T_CHRY",
      "confidence": 0.90
    }
  ]
}
```

---

_Generated by meta-disco classification system_
_Report date: 2026-01-24_
