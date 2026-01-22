# AnVIL File Metadata Classification Report

## Executive Summary

This report documents the rule-based metadata classification system for biological data files from the AnVIL (Analysis, Visualization, and Informatics Lab-space) platform. The system infers `data_modality` and `reference_assembly` from file metadata without requiring full file downloads.

### Key Metrics

| Metric                                 | Count   | Percentage |
| -------------------------------------- | ------- | ---------- |
| Total files classified                 | 246,768 | 100%       |
| Files with `data_modality`             | 243,098 | 98.5%      |
| Files with `reference_assembly`        | 42,700  | 19.1%*     |
| High-confidence classifications (≥80%) | 240,153 | 97.3%      |
| Files needing manual review (<50%)     | ~2,000  | <1%        |

*Reference assembly detection limited to BAM/CRAM and VCF files with explicit header annotations.

---

## 1. Ontology Overview

### 1.1 Data Modality Hierarchy

The classification system maps files to a hierarchical data modality ontology:

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
│  BAM @RG/@PG, VCF ##source/##reference, FASTQ read names            │
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

1. **Definitive signals** (95%): Explicit tags like `PL:PACBIO`, `##source=HaplotypeCaller`
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

| Level      | Range  | Description                                   |
| ---------- | ------ | --------------------------------------------- |
| Definitive | 95-99% | Explicit metadata tag (e.g., `PL:PACBIO`)     |
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
| genomic                     | 559     | 0.3%       |
| Unknown                     | 366     | 0.2%       |

**Variant Types:**

| Variant Type | Count   | Percentage |
| ------------ | ------- | ---------- |
| Germline     | 158,858 | 77.5%      |
| Structural   | 669     | 0.3%       |
| Unknown      | 45,483  | 22.2%      |

**Reference Assemblies:**

| Assembly | Count   | Percentage |
| -------- | ------- | ---------- |
| GRCh38   | 31,673  | 15.4%      |
| CHM13    | 198     | 0.1%       |
| Unknown  | 173,139 | 84.5%      |

High confidence (≥80%): 204,085 (99.5%)

### 5.4 Overall Classification Coverage

| File Type | Total   | With Modality | With Reference | High Confidence |
| --------- | ------- | ------------- | -------------- | --------------- |
| BAM/CRAM  | 18,662  | 96.3%         | 58.0%          | 83.6%           |
| FASTQ     | 23,096  | 100%*         | N/A            | 88.6%           |
| VCF       | 205,010 | 99.8%         | 15.5%          | 99.5%           |
| **Total** | 246,768 | 98.5%         | 19.1%          | 97.3%           |

*FASTQ modality defaults to "genomic" when platform is detected but no RNA-seq indicators found.

---

## 6. Limitations and Future Work

### 6.1 Current Limitations

1. **Header-only inspection**: Cannot detect modality for files without informative headers
2. **Archive reformatting**: Some SRA/ENA files lose original metadata
3. **Mixed-content files**: Cannot detect if BAM contains both DNA and RNA
4. **Reference version ambiguity**: Some files use non-standard contig names

### 6.2 Planned Improvements

1. Add contig length-based reference detection
2. Implement study-level context propagation
3. Add support for additional file types (10X, spatial transcriptomics)
4. Machine learning model for ambiguous cases

---

## Appendix A: Rule Statistics

| Category                 | Rule Count |
| ------------------------ | ---------- |
| BAM/CRAM platform rules  | 8          |
| BAM/CRAM program rules   | 15         |
| BAM/CRAM reference rules | 6          |
| VCF reference rules      | 6          |
| VCF caller rules         | 27         |
| FASTQ platform rules     | 16         |
| FASTQ archive rules      | 3          |
| Consistency rules        | 12         |
| File size rules          | 8          |
| **Total**                | **101**    |

---

_Generated by meta-disco classification system_
_Report date: 2026-01-22_
