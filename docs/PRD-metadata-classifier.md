# PRD: AnVIL File Metadata Classifier

**Version:** 1.0
**Date:** 2026-01-28
**Status:** Implemented

## 1. Problem Statement

The AnVIL Explorer (explore.anvilproject.org) hosts 2.6M+ biological data files. Many files have incomplete, missing, or potentially incorrect metadata for:
- **Data modality** (genomic, transcriptomic, epigenomic, etc.)
- **Data type** (reads, alignments, variant_calls, peaks, etc.)
- **Platform** (ILLUMINA, PACBIO, ONT)
- **Reference assembly** (GRCh38, GRCh37, CHM13, etc.)

This limits researchers' ability to discover and filter datasets effectively.

## 1.1 Current State Analysis (API Exploration Findings)

We explored the AnVIL API (`service.explore.anvilproject.org/index/files`) to understand the current data landscape.

### Scale

| Metric | Count | Notes |
|--------|-------|-------|
| **Total files** | 2.6M+ | Full inventory (requires authentication) |
| **Open access files** | 758,658 | Accessible without login |
| **Inaccessible files** | 1.9M+ | Managed access, requires auth |

### Metadata Completeness (Critical Gap)

| Field | Populated | NULL | Coverage |
|-------|-----------|------|----------|
| `data_modality` | ~6,767 | 751,903 | **0.9%** |
| `reference_assembly` | ~4,696 | 753,962 | **0.6%** |

**This confirms the core problem**: 99%+ of files lack modality and reference metadata.

### File Composition

| Category | Count | % | Description |
|----------|-------|---|-------------|
| **Data files** | ~305K | 40% | VCF, BAM, CRAM, FASTQ, etc. - ✅ classified via header inspection |
| **Index files** | ~224K | 29% | TBI, CSI, BAI, CRAI - ✅ inherit from parent (99.96% matched) |
| **Image files** | ~34K | 4% | SVS, PNG - ✅ classified by extension |
| **Auxiliary genomic** | ~21K | 3% | FAST5, PLINK - ✅ classified by extension + dataset |
| **BED files** | ~14K | 2% | Genomic intervals - ✅ classified by pattern + dataset |
| **Other/ambiguous** | ~145K | 19% | TXT, TAR, LOG - mixed utility |
| **Checksum files** | ~16K | 2% | MD5 - skip |

### Top File Formats (Open Access)

| Format | Count | Classification Notes |
|--------|-------|---------------------|
| `.vcf.gz` | 204,384 | ✅ Genomic (variant calls) - header classified |
| `.tbi` | 169,537 | ✅ Index - inherits from parent VCF |
| `Other` | 100,906 | Needs extension re-parsing |
| `.txt` | 42,120 | Ambiguous (stats, metadata, data) |
| `.csi` | 41,186 | ✅ Index - inherits from parent VCF |
| `.tar` | 31,984 | Archive - needs content inspection |
| `.svs` | 25,708 | Imaging (histology slides) |
| `.fastq.gz` | 16,255 | ✅ Sequencing reads - header classified |
| `.cram` | 10,829 | ✅ Alignments - header classified |
| `.bam` | 7,834 | ✅ Alignments - header classified |

### Data Quality Issues Discovered

1. **`is_supplementary` flag is unreliable**
   - Marks primary data files (VCF, BAM, CRAM) as supplementary
   - Marks actual supplementary files (CRAI, MD5) as non-supplementary
   - Cannot be trusted for filtering

2. **`file_format` detection broken for coordinate-named files**
   - Files like `chr5.136400001_136500001.tar` classified as "Other"
   - Format parser mistakes genomic coordinates for extension
   - ~100K files affected

3. **Dataset naming inconsistency**
   - Some datasets use `ANVIL_` prefix (uppercase)
   - Others use `AnVIL_` prefix (mixed case)

4. **Sparse activity metadata**
   - 93% of files have no `activities` data
   - When present, usually "Unknown", "Checksum", or "Indexing"
   - Not useful for modality classification

5. **Sparse organism/donor metadata**
   - 90% of files have no organism type
   - Only ~74K files have Human/Mouse annotation

### Classification Challenges Identified

| Challenge | Count (sample) | Issue |
|-----------|----------------|-------|
| BAM files with no modality hint in name | 12+ | e.g., `m64043_210211_005516.hifi_reads.bam` - need header inspection |
| VCF files named by chromosome only | 245+ | e.g., `NA19189.chr2.hc.vcf.gz` - no modality context |
| Ambiguous TXT files | 67+ | Could be stats, metadata, or data |
| Image files (SVS, PNG) | 37+ | GTEx histology vs HPRC assembly plots - different modalities |
| TAR archives | varies | Need to know contents to classify |

### False Positive Risks for Pattern Matching

| Pattern | False Match Example | Why It's Wrong |
|---------|---------------------|----------------|
| `RNA` | `paternal_not_maternal.hist` | Assembly haplotype, not transcriptomics |
| `maternal` | `HG02148.maternal.f1_assembly_v2.pdf` | Haplotype assembly, not gender study |

### Reference Assembly in Filenames

Many files contain reference hints in filename but have NULL metadata:
- `HG01879.CHM13v2.chrX.samtools.stats.txt` → CHM13 in name, NULL in API
- `clinvar_20210308.noY.GRCh38.rejected_position-failed.vcf.gz.tbi` → GRCh38 in name, NULL in API

**Implication**: Tier 2 filename pattern matching should recover significant reference assembly coverage.

## 2. Goals

Build a hierarchical, primarily deterministic classifier that:

1. **Classifies files** by data modality, data type, platform, and reference assembly
2. **Fills gaps** in missing metadata (99%+ of files lack these fields)
3. **Validates/corrects** potentially incorrect existing values
4. **Uses file inspection** (headers, extensions, filenames) to infer metadata
5. **Provides explainable, traceable rationale** for every classification
6. **Produces defensible confidence scores** for each call

## 3. Non-Goals (v1)

- Real-time classification (batch processing is acceptable)
- Classification of non-biological data files (documentation, indices, etc.)
- Modification of source files or AnVIL database (output is separate report)

## 4. Success Metrics

### Spike Success Criteria

| Metric | Target | Notes |
|--------|--------|-------|
| **Accuracy** | Measure against validation set | No target yet - spike will establish baseline |
| **Coverage** | Measure % classified with confidence ≥ 0.9 | Goal: understand what's achievable deterministically |
| **Speed** | Benchmark per-file throughput | Identify bottlenecks (API, downloads, parsing) |
| **Explainability** | 100% | Every classification has evidence chain |

### Validation Set Requirements

- **Size**: 200-500 files minimum
- **Diversity**: Cover all major modalities and file types
- **Source**: Manually labeled by domain expert
- **Format**: Ground truth annotations for modality + reference assembly

## 5. Metadata Schema

### 5.1 Overview

We define **6 orthogonal dimensions** for file classification. Each dimension answers a different question:

| Dimension | Question | Multiplicity | Inferability |
|-----------|----------|--------------|--------------|
| `data_modality` | What biology is measured? | 1 | Medium |
| `data_type` | What artifact do I have? | 1 | High |
| `platform` | What sequencing instrument? | 0..1 | High |
| `reference_assembly` | What reference genome? | 0..1 | High |
| `file_format` | How is it stored? | 1 | Trivial |
| `assay_type` | What method class? (v2) | 0..1 | Low |

**V1 Scope**: We predict `data_modality`, `data_type`, `platform`, `reference_assembly`, and `file_format` from file inspection.

**V2 Scope**: `assay_type` and `assay` (specific protocol) require external metadata and are deferred.

### 5.2 Data Modality

**Definition**: The biological signal domain the information is about (independent of protocol and file format).

The hierarchy reflects **what was measured** (the biological information captured), not **how it was measured** (the technology/protocol).

```
data_modality
├── genomic                      # DNA sequence/variation
├── transcriptomic               # RNA expression
├── epigenomic                   # DNA/chromatin modifications
│   ├── methylation              # DNA methylation state
│   ├── chromatin_accessibility  # ATAC-seq, DNase-seq
│   └── histone_modification     # ChIP-seq for histones
├── proteomic                    # protein abundance
├── metabolomic                  # small molecule abundance
├── imaging                      # visual/spatial data
│   └── histology                # tissue slides
├── phenotypic                   # clinical/phenotype data
└── unknown                      # needs manual classification
```

### 5.3 Data Type

**Definition**: The artifact/content class of the stored object—what you can download/open/analyze (independent of assay).

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
├── assemblies                   # Genome assemblies (FASTA)
├── annotations                  # Genomic annotations (GTF, GFF)
├── raw_signal                   # Instrument signal (FAST5, POD5)
├── images                       # Image files (SVS, PNG)
└── other                        # Auxiliary files
```

### 5.4 Platform

**Definition**: The sequencing instrument/technology used to generate the data.

```
platform
├── ILLUMINA                     # Illumina short-read
├── PACBIO                       # PacBio long-read (HiFi, CLR)
├── ONT                          # Oxford Nanopore
├── BGI                          # MGI/BGISEQ
├── ION_TORRENT                  # Ion Torrent
├── ELEMENT                      # Element Biosciences
└── not_applicable               # Non-sequencing data
```

### 5.5 Reference Assembly

**Definition**: The reference genome the data is aligned to or called against.

```
reference_assembly
├── human
│   ├── GRCh38 (hg38)
│   ├── GRCh37 (hg19)
│   ├── CHM13 (T2T)
│   └── hg18 (legacy)
├── mouse
│   ├── GRCm39 (mm39)
│   └── GRCm38 (mm10)
├── other_organism
│   └── [extensible]
└── not_applicable               # Unaligned reads, raw signal
```

### 5.6 Assay Type (V2)

**Definition**: The top-level assay kind / method class used to generate the measurement. Requires external metadata.

```
assay_type
├── WGS                          # Whole genome sequencing
├── WES                          # Whole exome sequencing
├── RNAseq                       # Bulk RNA sequencing
├── scRNAseq                     # Single-cell RNA sequencing
├── ATACseq                      # Bulk ATAC-seq
├── scATACseq                    # Single-cell ATAC-seq
├── ChIPseq                      # ChIP sequencing
├── WGBS                         # Whole genome bisulfite sequencing
├── HiC                          # Chromatin conformation
└── [extensible]
```

### 5.7 Ontology Alignment

We align with established ontologies where possible:

| Ontology | Use Case | Notes |
|----------|----------|-------|
| **[EFO](https://www.ebi.ac.uk/efo/)** | Assay types | Map assay_type to EFO terms |
| **[EDAM](https://edamontology.org/)** | Data/Format | Map data_type and file_format |
| **[OBI](https://obi-ontology.org/)** | Definitions | Reference for rigorous semantics |

### 5.8 Example Classifications

**10x scATAC peak file**:
- `data_modality`: epigenomic.chromatin_accessibility
- `data_type`: peaks
- `platform`: ILLUMINA
- `reference_assembly`: GRCh38
- `file_format`: .narrowPeak
- `assay_type`: scATACseq *(v2)*

**PacBio HiFi FASTQ**:
- `data_modality`: genomic
- `data_type`: reads
- `platform`: PACBIO
- `reference_assembly`: not_applicable
- `file_format`: .fastq.gz
- `assay_type`: WGS *(v2)*

**Aligned BAM from RNA-seq**:
- `data_modality`: transcriptomic
- `data_type`: alignments
- `platform`: ILLUMINA
- `reference_assembly`: GRCh38
- `file_format`: .bam
- `assay_type`: RNAseq *(v2)*

## 6. Classification Strategy

### 6.1 Hierarchical Rule Engine

All 147 classification rules are defined in `rules/unified_rules.yaml` and executed by `src/meta_disco/rule_engine.py`.

Process files through tiers of increasing complexity/cost:

```
┌─────────────────────────────────────────────────────────────────┐
│ TIER 1: File Extension Rules (instant, deterministic)          │
│ .bam, .cram → likely genomic/transcriptomic                    │
│ .fastq, .fq → sequencing reads                                 │
│ .vcf → variant calls                                           │
│ .bed, .bigwig → genomic regions/signal                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (if confidence < threshold)
┌─────────────────────────────────────────────────────────────────┐
│ TIER 2: Filename Pattern Rules (instant, deterministic)        │
│ *_RNA_*, *_rna_*, *transcriptome* → transcriptomic             │
│ *_WGS_*, *_wgs_*, *genome* → genomic                           │
│ *_ATAC_*, *_ChIP_* → epigenomic                                │
│ *hg38*, *GRCh38*, *grch38* → GRCh38 reference                  │
│ *hg19*, *GRCh37*, *grch37* → GRCh37 reference                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (if confidence < threshold)
┌─────────────────────────────────────────────────────────────────┐
│ TIER 3: File Size Heuristics (instant, probabilistic)          │
│ BAM > 50GB + WGS pattern → high confidence WGS                 │
│ BAM 1-10GB + RNA pattern → likely bulk RNA-seq                 │
│ [calibrated from known samples]                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (if confidence < threshold)
┌─────────────────────────────────────────────────────────────────┐
│ TIER 4: Study Context (API lookup, cached)                     │
│ Study title, description, consent group                        │
│ Associated activities/assay types in AnVIL API                 │
│ PubMed abstract if available                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (if confidence < threshold)
┌─────────────────────────────────────────────────────────────────┐
│ TIER 5: File Header Inspection (download required)             │
│ BAM/CRAM: @RG tags, @PG programs, SQ references                │
│ VCF: ##reference, ##contig headers                             │
│ FASTQ: read patterns, quality encoding                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (if confidence < threshold)
┌─────────────────────────────────────────────────────────────────┐
│ TIER 6: LLM Inference (future, if needed)                      │
│ Placeholder - evaluate need based on spike results             │
│ If used: must support private LLM for managed access data      │
└─────────────────────────────────────────────────────────────────┘
```

**Note**: This spike will focus on Tiers 1-5 (deterministic rules + header inspection). LLM integration will be evaluated based on what gaps remain after deterministic classification.

### 6.2 Index File Inheritance

Index files (`.tbi`, `.csi`, `.bai`, `.crai`, `.pbi`) inherit metadata from their parent data files by filename matching within the same dataset.

| Index | Parent | Match Rate | Notes |
|-------|--------|------------|-------|
| `.tbi` | `.vcf.gz` | 100.0% | VCF tabix index |
| `.csi` | `.vcf.gz` | 99.9% | VCF coordinate-sorted index |
| `.crai` | `.cram` | 100.0% | CRAM index |
| `.bai` | `.bam` | 99.9% | BAM index |
| `.pbi` | `.bam` | 97.2% | PacBio BAM index |

**Implementation**: `scripts/classify_index_files.py` (rules in `rules/unified_rules.yaml`)

**Results** (224,037 index files):
- 223,953 matched to parent (99.96%)
- 216,533 with `data_modality` (96.7%)
- 211,750 with `reference_assembly` (94.5%)

Index files without `reference_assembly` inherit from unaligned parent BAMs (raw HiFi/ONT reads) where reference is correctly N/A.

### 6.3 Image File Classification

Image files are classified by extension using domain-specific rules.

| Extension | Data Modality     | Reference | Confidence | Rationale |
|-----------|-------------------|-----------|------------|-----------|
| `.svs`    | imaging.histology | N/A       | 95%        | Aperio whole-slide histology images |
| `.png`    | N/A               | N/A       | 90%        | Derived visualizations (QC plots) |

**Implementation**: `scripts/classify_images.py` (rules in `rules/unified_rules.yaml`)

**Results** (33,757 image files):
- SVS: 25,708 files (GTEx tissue slides) → `imaging.histology`
- PNG: 8,049 files (HPRC QC plots) → N/A (not primary data)

PNG files are excluded from data_modality assignment as they are derived artifacts (assembly graphs, QC plots), not primary experimental data.

### 6.4 Auxiliary Genomic File Classification

FAST5 and PLINK files are classified by extension with dataset-based reference inference.

| Extension | Data Modality             | Reference | Rule Type |
|-----------|---------------------------|-----------|-----------|
| `.fast5`  | genomic                   | N/A       | Extension |
| `.pvar`   | genomic.germline_variants | GRCh38*   | Extension + Dataset |
| `.psam`   | genomic.germline_variants | GRCh38*   | Extension + Dataset |
| `.pgen`   | genomic.germline_variants | GRCh38*   | Extension + Dataset |

*Reference inferred from dataset context (ANVIL_1000G_PRIMED uses GRCh38).

**Implementation**: `scripts/classify_auxiliary_genomic.py` (rules in `rules/unified_rules.yaml`)

**Results** (20,956 files):
- FAST5: 12,394 files (ONT raw signal) → `genomic`, no reference (pre-basecalling)
- PLINK: 8,562 files → `genomic.germline_variants`, GRCh38

### 6.5 BED File Classification

BED files are classified using filename pattern matching and dataset context.

| Pattern | Data Modality | Example |
|---------|---------------|---------|
| `modbam2bed\|cpg\|methylat` | epigenomic.methylation | CpG calls |
| `TMM\|TPM\|counts\|leafcutter` | transcriptomic | Expression quantification |
| `peak\|summit\|chip\|atac` | epigenomic.chromatin_accessibility | Peak calls |
| `.regions.bed` | genomic | Callable regions |
| Assembly QC patterns | N/A | Derived artifacts |

Reference inferred from filename patterns (hg38, chm13) or dataset context (T2T → CHM13).

**Implementation**: `scripts/classify_bed_files.py` (rules in `rules/unified_rules.yaml`)

**Results** (13,660 files):
- 8,560 with data_modality (62.7%)
- 7,068 with reference_assembly (51.7%)
- 5,100 assembly QC files marked as N/A (derived artifacts)

### 6.6 Confidence Scoring

Each tier contributes evidence with weights:

```python
confidence = {
    "modality": {
        "value": "transcriptomic.bulk_rna_seq",
        "score": 0.92,
        "evidence": [
            {"tier": 1, "rule": "extension:.bam", "weight": 0.3, "signal": "sequencing_alignment"},
            {"tier": 2, "rule": "filename:*_RNA_*", "weight": 0.4, "signal": "transcriptomic"},
            {"tier": 3, "rule": "size:2.3GB", "weight": 0.2, "signal": "bulk_not_sc"},
            {"tier": 4, "rule": "study:RNA-seq cohort", "weight": 0.1, "signal": "transcriptomic"}
        ]
    },
    "reference_assembly": {
        "value": "GRCh38",
        "score": 0.98,
        "evidence": [
            {"tier": 2, "rule": "filename:*hg38*", "weight": 0.5, "signal": "GRCh38"},
            {"tier": 5, "rule": "bam_header:SQ_GRCh38", "weight": 0.5, "signal": "GRCh38"}
        ]
    }
}
```

### 6.7 Decision Thresholds

| Confidence Score | Action |
|------------------|--------|
| ≥ 0.90 | Auto-accept classification |
| 0.70 - 0.89 | Accept with "needs_review" flag |
| 0.50 - 0.69 | Escalate to LLM tier |
| < 0.50 | Flag for manual review |

## 7. Technical Architecture

### 7.1 Components

```
┌─────────────────────────────────────────────────────────────────┐
│                      Meta-Disco Classifier                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  AnVIL API  │  │  Rule       │  │  File Header            │ │
│  │  Client     │  │  Engine     │  │  Inspector              │ │
│  │             │  │             │  │  (samtools, pysam, etc) │ │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘ │
│         │                │                     │               │
│         └────────────────┼─────────────────────┘               │
│                          ▼                                     │
│                 ┌─────────────────┐                            │
│                 │  Classification │                            │
│                 │  Orchestrator   │                            │
│                 └────────┬────────┘                            │
│                          │                                     │
│         ┌────────────────┼────────────────┐                    │
│         ▼                ▼                ▼                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  LLM        │  │  Confidence │  │  Output     │            │
│  │  Service    │  │  Calculator │  │  Writer     │            │
│  │  (optional) │  │             │  │             │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Data Flow

1. **Input**: File listing from AnVIL API (`/index/files` endpoint)
2. **Enrichment**: Fetch related metadata (study, biosample, activities)
3. **Classification**: Run through tier hierarchy
4. **Output**: Classification results with evidence chains

### 7.3 LLM Requirements (Future)

Deferred until spike results show where LLM might help. If needed:
- Must support fully private deployment for managed-access data
- Cost tracking required
- Existing Ollama infrastructure available

## 8. Output Schema

```yaml
# Classification result for a single file
file_classification:
  file_id: "dg.ANV0/abc123"
  file_name: "sample_RNA_hg38.bam"
  file_format: ".bam"

  # V1 fields (inferrable from file inspection)
  data_modality:
    value: "transcriptomic"
    confidence: 0.92
    previous_value: null  # from AnVIL API
    change_type: "new"  # new | refined | corrected | validated

  data_type:
    value: "alignments"
    confidence: 0.99
    change_type: "new"

  platform:
    value: "ILLUMINA"
    confidence: 0.95
    change_type: "new"

  reference_assembly:
    value: "GRCh38"
    confidence: 0.98
    previous_value: null
    change_type: "new"

  # V2 fields (require external metadata)
  assay_type:
    value: null  # Would be "RNAseq" if metadata available
    confidence: 0.0

  evidence_chain:
    - tier: 1
      rule_id: "ext_bam"
      input: {extension: ".bam"}
      output: {data_type: "alignments"}
      confidence_contribution: 0.3
    - tier: 2
      rule_id: "fname_rna"
      input: {filename: "sample_RNA_hg38.bam"}
      output: {modality: "transcriptomic", reference: "GRCh38"}
      confidence_contribution: 0.4
    - tier: 5
      rule_id: "bam_header_star"
      input: {pg_program: "STAR"}
      output: {modality: "transcriptomic"}
      confidence_contribution: 0.2
    # ... additional evidence

  processing:
    highest_tier_used: 5
    llm_used: false
    processing_time_ms: 150

  flags:
    needs_review: false
    low_confidence_fields: []
```

## 9. Spike Approach

This is an **exploration/spike** to determine if deterministic classification is viable. The goal is to answer: *What coverage and accuracy can we achieve without LLMs?*

### Spike 1: Low-Hanging Fruit
**Goal**: Classify files using only metadata from the API (no downloads)

- [ ] Set up AnVIL API client with pagination
- [ ] Implement Tier 1-2 rule engine (extension + filename patterns)
- [ ] Run against sample of files, measure coverage
- [ ] **Create validation set**: Manually label ~200-500 files across modality types
- [ ] Evaluate accuracy against validation set

**Key question answered**: What % of files can we classify confidently from filename/extension alone?

### Spike 2: Study Context
**Goal**: Use study metadata to improve coverage

- [ ] Implement Tier 3-4 (file size heuristics, study context)
- [ ] Evaluate incremental coverage gain
- [ ] Identify file types that remain ambiguous

**Key question answered**: Does study context significantly help, or is it redundant with filename?

### Spike 3: Header Inspection
**Goal**: Parse file headers for ground truth signals

- [ ] Implement Tier 5 for BAM/CRAM headers (reference assembly from @SQ)
- [ ] Add VCF header parsing
- [ ] Measure accuracy improvement and processing cost

**Key question answered**: Is header inspection worth the download/processing cost?

### Evaluation Checkpoint
After spikes, assess:
- Coverage: What % of 2.6M files can we classify with confidence ≥ 0.9?
- Accuracy: How do we perform against validation set?
- Gaps: What file types/modalities need additional signals (possibly LLM)?

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Existing AnVIL metadata unreliable as ground truth | **Confirmed** | Medium | Create independent validation set; don't assume API is correct |
| `is_supplementary` flag unreliable | **Confirmed** | Low | Use file extension to determine if file is index/checksum/data |
| Filename patterns too inconsistent for rules | Medium | High | Initial sampling shows promise (ref assembly in names); spike will quantify |
| False positives from pattern matching (e.g., "RNA" in assembly names) | Medium | Medium | Use negative patterns; require multiple signals for high confidence |
| File header inspection too slow/expensive | Medium | Medium | Spike 3 will quantify; can be selective if needed |
| 100K "Other" format files need special handling | **Confirmed** | Medium | Re-parse extensions; many are `.tar` with coordinates in name |
| Deterministic rules insufficient for good coverage | Medium | High | Spike will measure gap; LLM is fallback option |

## 11. Open Questions

### Answered by API Exploration
- ~~**Existing API accuracy**~~: `data_modality` is 99% NULL - cannot use as ground truth
- ~~**is_supplementary reliability**~~: Unreliable - must use our own file type classification

### Still Open
1. **Validation set creation**: Who will manually label the validation set? Domain expertise required.
2. **AnVIL API rate limits**: What are the throttling constraints for bulk queries? (Initial testing showed no issues at 1000 files/request)
3. **File download access**: Do we have programmatic access (DRS URIs) to download files for header inspection?
4. **Managed access data**: How do we handle the 1.9M files that require authentication?
5. **"Other" format files**: Should we re-parse the 100K "Other" files to extract true extensions, or handle them separately?
6. **TAR archive contents**: Do we need to inspect TAR contents, or can we infer from dataset context?

## 12. References

- [EFO - Experimental Factor Ontology](https://www.ebi.ac.uk/efo/)
- [EDAM - Ontology of bioinformatics operations](https://edamontology.org/)
- [OBI - Ontology for Biomedical Investigations](https://obi-ontology.org/)
- [MODAL - Broad Institute Data Modality Ontology](https://github.com/broadinstitute/modal)
- [Omics data types overview (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6018996/)
- [AnVIL Explorer](https://explore.anvilproject.org/files)

---

## Appendix A: Common File Extensions

| Extension | Typical Modality | Notes |
|-----------|------------------|-------|
| `.bam`, `.cram` | genomic, transcriptomic | Requires header inspection to differentiate |
| `.fastq`, `.fq`, `.fastq.gz` | genomic, transcriptomic | Raw reads, needs context |
| `.vcf`, `.vcf.gz`, `.bcf` | genomic | Variant calls |
| `.bed`, `.bedGraph` | varies | Genomic intervals |
| `.bigwig`, `.bw` | varies | Signal tracks |
| `.gtf`, `.gff` | transcriptomic | Annotations |
| `.h5ad`, `.loom` | transcriptomic | Single-cell matrices |
| `.idat` | epigenomic | Methylation arrays |
| `.cel` | varies | Microarrays |

## Appendix B: Datasets in Open Access Sample

| Dataset | Files (sample) | Primary Formats | Notes |
|---------|----------------|-----------------|-------|
| `ANVIL_T2T_CHRY` | 309,979 | VCF, TBI, TXT, CRAM | T2T consortium, chrY focus |
| `ANVIL_T2T` | 289,204 | VCF, TBI, CSI, TAR | T2T consortium |
| `ANVIL_HPRC` | 67,830 | BAM, PNG, FASTQ, BED | Human Pangenome Reference |
| `ANVIL_1000G_high_coverage_2019` | 26,016 | MD5, CRAI, TBI, CRAM | 1000 Genomes high coverage |
| `ANVIL_GTEx_public_data` | 25,789 | SVS | GTEx histology slides |
| `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open` | 12,534 | FAST5 | Nanopore data |
| `ANVIL_1000G_PRIMED_data_model` | 11,493 | LOG, PVAR, PSAM, PGEN | PLINK format genotypes |
| `AnVIL_IGVF_Mouse_R1` | 6,784 | FASTQ | Mouse IGVF, single-nucleus RNA/ATAC |
| `AnVIL_ENCORE_RS293` | 3,752 | BW (bigwig) | Signal tracks |
| `AnVIL_MAGE` | 3,285 | BAI, BAM | Alignments |

## Appendix C: Filename Pattern Examples

These patterns were refined based on API exploration to avoid false positives.

```python
MODALITY_PATTERNS = {
    "genomic.wgs": [r"_WGS_", r"_wgs_", r"whole.?genome", r"WGS\d+"],
    "genomic.wes": [r"_WES_", r"_wes_", r"exome", r"WES\d+"],
    "transcriptomic.rna_seq": [r"_RNA_", r"_rna_", r"rnaseq", r"transcriptome"],
    "transcriptomic.scrna": [r"_scRNA", r"single.?cell", r"10x", r"chromium"],
    "epigenomic.atac": [r"_ATAC_", r"atac.?seq"],
    "epigenomic.chip": [r"_ChIP_", r"chip.?seq"],
    "epigenomic.methylation": [r"bisulfite", r"WGBS", r"methylation"],
}

REFERENCE_PATTERNS = {
    "GRCh38": [r"hg38", r"GRCh38", r"grch38", r"hs38"],
    "GRCh37": [r"hg19", r"GRCh37", r"grch37", r"hs37"],
    "CHM13": [r"chm13", r"CHM13v2", r"t2t", r"T2T"],
}

# Patterns to EXCLUDE (false positive prevention)
FALSE_POSITIVE_EXCLUSIONS = {
    # "RNA" appears in haplotype assembly files, not transcriptomics
    "transcriptomic": [r"maternal", r"paternal", r"haplotype", r"\.hist$"],
}
```
