# AnVIL File Metadata Classification Report

## Executive Summary

This report documents the rule-based metadata classification system for biological data files from the AnVIL (Analysis, Visualization, and Informatics Lab-space) platform. The system infers `data_modality` and `reference_assembly` from file metadata without requiring full file downloads.

### Key Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Files with `data_modality` | TBD% | TBD% | +TBD% |
| Files with `reference_assembly` | TBD% | TBD% | +TBD% |
| High-confidence classifications (≥80%) | TBD% | TBD% | +TBD% |
| Files needing manual review | TBD% | TBD% | -TBD% |

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

| Value | Description | Common Indicators |
|-------|-------------|-------------------|
| `GRCh38` | Human reference (2013) | hg38, GRCh38, GCA_000001405.15 |
| `GRCh37` | Human reference (2009) | hg19, b37, hs37, GCA_000001405.1 |
| `CHM13` | T2T complete genome (2022) | chm13, t2t, hs1 |

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

| Example Pattern | Classification | Confidence |
|----------------|----------------|------------|
| `(?i)(rna|rnaseq|transcriptom)` | transcriptomic | 85% |
| `(?i)(wgs|whole.?genome)` | genomic.whole_genome | 85% |
| `(?i)(hg38|grch38)` | GRCh38 | 90% |
| `(?i)\.hifi[_.]` | genomic.whole_genome | 80% |

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

| Signal A | Signal B | Expected Agreement |
|----------|----------|-------------------|
| PL:PACBIO | READTYPE=CCS | genomic.whole_genome |
| PL:ILLUMINA | PN:bwa | genomic |
| PL:ILLUMINA | PN:STAR | transcriptomic |
| PL:PACBIO | PN:minimap2 | genomic |

#### Conflicting Signals (Reduce Confidence + Warning)

| Signal A | Signal B | Issue |
|----------|----------|-------|
| PL:PACBIO | PN:STAR | STAR is short-read only |
| PL:ILLUMINA | READTYPE=CCS | CCS is PacBio-specific |
| PN:bwa | PN:STAR | Mutually exclusive aligners |

### 3.3 File Size Heuristics

Size-based rules provide fallback classification when other signals are absent:

| File Type | Size Range | Classification | Confidence |
|-----------|-----------|----------------|------------|
| BAM | >50 GB | genomic.whole_genome | 65% |
| BAM | 5-50 GB | genomic.whole_exome | 60% |
| CRAM | >15 GB | genomic.whole_genome | 65% |
| CRAM | 3-15 GB | genomic.whole_exome | 60% |

**Platform-specific adjustments:**
- PacBio HiFi BAMs tend to be larger (100+ GB for WGS)
- ONT BAMs can be very large due to longer reads
- Illumina CRAMs compress well (~3:1 vs BAM)

### 3.4 Confidence Scoring System

#### Base Confidence Levels

| Level | Range | Description |
|-------|-------|-------------|
| Definitive | 95-99% | Explicit metadata tag (e.g., `PL:PACBIO`) |
| High | 85-94% | Strong program indicator (e.g., STAR aligner) |
| Medium | 70-84% | Filename pattern match |
| Low | 50-69% | Size heuristic or weak pattern |
| Uncertain | <50% | Needs manual review |

#### Confidence Adjustments

| Condition | Adjustment |
|-----------|------------|
| Multiple convergent signals | +5% per pair (diminishing) |
| All reads agree (FASTQ) | +5% |
| Conflicting signals detected | -20% |
| Multiple reference assemblies in @SQ | -10% |

---

## 4. Header Inspection Details

### 4.1 BAM/CRAM Header Rules

**Platform Detection (from @RG PL field):**

| Pattern | Platform | Confidence | Rationale |
|---------|----------|------------|-----------|
| `PL:ILLUMINA` | ILLUMINA | 95% | Explicit platform tag |
| `PL:PACBIO` | PACBIO | 95% | Explicit platform tag |
| `PL:ONT` | ONT | 95% | Oxford Nanopore |
| `PL:DNBSEQ` | MGI | 90% | MGI/BGI sequencers |

**Modality Detection (from @PG programs):**

| Program | Modality | Confidence | Rationale |
|---------|----------|------------|-----------|
| STAR | transcriptomic | 95% | Splice-aware RNA aligner |
| HISAT2 | transcriptomic | 90% | RNA-seq aligner |
| TopHat | transcriptomic | 85% | Legacy RNA aligner |
| BWA | genomic | 85% | DNA short-read aligner |
| minimap2 | genomic | 80% | Long-read aligner |
| pbmm2 | genomic | 90% | PacBio-specific aligner |

### 4.2 VCF Header Rules

**Variant Caller Detection:**

| Caller | Variant Type | Confidence |
|--------|--------------|------------|
| HaplotypeCaller | germline_variants | 90% |
| DeepVariant | germline_variants | 90% |
| Mutect2 | somatic_variants | 90% |
| Strelka | somatic_variants | 90% |
| Manta | structural_variants | 90% |
| DELLY | structural_variants | 90% |
| CNVkit | copy_number_variants | 90% |

### 4.3 FASTQ Read Name Rules

**Platform Detection from Read Name Format:**

| Platform | Pattern Example | Confidence |
|----------|-----------------|------------|
| Illumina (modern) | `@A00297:44:HFKH3DSXX:1:1101:...` | 90% |
| Illumina (legacy) | `@HWUSI-EAS100R:6:73:941:1973#0/1` | 85% |
| PacBio CCS | `@m64011_190830_220126/1/ccs` | 95% |
| PacBio CLR | `@m64011_190830_220126/1234/0_5000` | 90% |
| ONT | `@a1b2c3d4-e5f6-7890-abcd-ef1234567890` | 95% |
| MGI/BGI | `@V350012345L1C001R0010000001/1` | 90% |

**Archive Accession Extraction:**

When files are downloaded from public archives, accessions are extracted:

| Prefix | Archive | Example |
|--------|---------|---------|
| ERR | ENA (European) | `@ERR3242571.1 A00297:44:...` |
| SRR | SRA (NCBI) | `@SRR12345678.1 ...` |
| DRR | DDBJ (Japan) | `@DRR000001.1 ...` |

---

## 5. Results Analysis

### 5.1 FASTQ Classification Results

*(To be populated after scan completes)*

| Platform | Count | Percentage |
|----------|-------|------------|
| ILLUMINA | TBD | TBD% |
| PACBIO | TBD | TBD% |
| ONT | TBD | TBD% |
| MGI | TBD | TBD% |
| Unknown | TBD | TBD% |

**Archive Accessions Found:**
- ENA (ERR): TBD files
- SRA (SRR): TBD files
- DDBJ (DRR): TBD files

### 5.2 VCF Classification Results

*(To be populated after scan completes)*

| Variant Type | Count | Percentage |
|--------------|-------|------------|
| Germline | TBD | TBD% |
| Somatic | TBD | TBD% |
| Structural | TBD | TBD% |
| CNV | TBD | TBD% |

**Reference Assemblies:**
- GRCh38: TBD files
- GRCh37: TBD files
- Unknown: TBD files

### 5.3 Overall Classification Coverage

*(To be populated with final metrics)*

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

| Category | Rule Count |
|----------|------------|
| BAM/CRAM platform rules | 8 |
| BAM/CRAM program rules | 15 |
| BAM/CRAM reference rules | 6 |
| VCF reference rules | 6 |
| VCF caller rules | 27 |
| FASTQ platform rules | 16 |
| FASTQ archive rules | 3 |
| Consistency rules | 12 |
| File size rules | 8 |
| **Total** | **101** |

---

*Generated by meta-disco classification system*
*Report date: 2026-01-22*
