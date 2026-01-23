# BAM/CRAM, VCF, and FASTQ Header Classification Rules

## Overview

This document describes the rules used to classify BAM/CRAM, VCF, and FASTQ files based on their
header content. Headers contain metadata about sequencing platform, alignment
software, and reference genome that can definitively identify data modality and reference assembly.

## Header Sections Reference

> **Specification**: [SAM/BAM Format Specification v1](https://samtools.github.io/hts-specs/SAMv1.pdf) |
> [SAM Tags](https://samtools.github.io/hts-specs/SAMtags.pdf) |
> [hts-specs GitHub](https://github.com/samtools/hts-specs)

### @HD (Header)
File-level metadata including SAM format version and sort order.

### @SQ (Sequence Dictionary)
Reference sequences the reads are aligned to. Key fields:
- **SN**: Sequence name (e.g., chr1, NC_000001.11)
- **LN**: Sequence length
- **AS**: Genome assembly identifier (e.g., GRCh38)
- **M5**: MD5 checksum of sequence

### @RG (Read Group)
Metadata about a set of reads. Key fields:
- **ID**: Read group identifier
- **PL**: Platform/technology (ILLUMINA, PACBIO, ONT)
- **PM**: Platform model (e.g., SEQUELII, NovaSeq)
- **SM**: Sample name
- **DS**: Description (PacBio uses for READTYPE)

### @PG (Program)
Software used to create/modify the file. Key fields:
- **ID**: Program record identifier
- **PN**: Program name (e.g., bwa, STAR, minimap2)
- **VN**: Program version
- **CL**: Command line used

---

## Classification Rules

### Platform Detection

*Source: @RG PL field*

#### `platform_pacbio`

- **Pattern**: `PACBIO`
- **Classification**: genomic
- **Confidence**: 70%

**Rationale**: PL:PACBIO indicates PacBio long-read sequencing. PacBio is primarily used for whole genome sequencing, structural variant detection, and de novo assembly due to its long read lengths (10-25kb average for HiFi). Can also be used for IsoSeq (transcriptomics) but this is less common.

#### `platform_illumina`

- **Pattern**: `ILLUMINA`
- **Classification**: N/A (ambiguous)
- **Confidence**: 0%

**Rationale**: PL:ILLUMINA indicates Illumina short-read sequencing. Illumina platforms are used for diverse applications including WGS, WES, RNA-seq, ChIP-seq, ATAC-seq, bisulfite sequencing, and more. Platform alone is insufficient to determine modality - requires program info or study context.

#### `platform_ont`

- **Pattern**: `ONT`
- **Classification**: genomic
- **Confidence**: 70%

**Rationale**: PL:ONT indicates Oxford Nanopore long-read sequencing. ONT is primarily used for whole genome sequencing, structural variants, and direct RNA sequencing. The ultra-long reads (>100kb possible) make it valuable for resolving complex genomic regions and phasing.

#### `platform_ont_alt`

- **Pattern**: `NANOPORE`
- **Classification**: genomic
- **Confidence**: 70%

**Rationale**: Alternative platform identifier for Oxford Nanopore Technology.

---

### PacBio Read Type

*Source: @RG DS field*

> **Reference**: [PacBio BAM Format Specification](https://pacbiofileformats.readthedocs.io/en/latest/BAM.html) |
> [CCS Documentation](https://ccs.how/)

#### `pacbio_hifi`

- **Pattern**: `READTYPE=CCS`
- **Classification**: genomic.whole_genome
- **Confidence**: 85%

**Rationale**: READTYPE=CCS indicates PacBio HiFi (High-Fidelity) reads. CCS (Circular Consensus Sequencing) generates highly accurate long reads (>Q20, ~99% accuracy) by sequencing the same molecule multiple times. HiFi is the current standard for PacBio WGS, used extensively in projects like HPRC for diploid assembly.

#### `pacbio_clr`

- **Pattern**: `READTYPE=SUBREAD`
- **Classification**: genomic.whole_genome
- **Confidence**: 80%

**Rationale**: READTYPE=SUBREAD indicates PacBio CLR (Continuous Long Read) data. These are raw subreads from a single pass around the circular molecule, longer but less accurate than HiFi. Still used for some assembly applications.

---

### RNA-seq Programs

*Source: @PG PN field*

#### `program_star`

- **Pattern**: `STAR`
- **Classification**: transcriptomic
- **Confidence**: 95%
- **Reference**: [GitHub](https://github.com/alexdobin/STAR) | [PMID:23104886](https://pubmed.ncbi.nlm.nih.gov/23104886/)

**Rationale**: STAR (Spliced Transcripts Alignment to a Reference) is the most widely used RNA-seq aligner. It performs splice-aware alignment essential for mapping reads across exon-exon junctions. Presence of STAR in @PG strongly indicates RNA-seq data.

#### `program_hisat2`

- **Pattern**: `hisat2`
- **Classification**: transcriptomic
- **Confidence**: 95%
- **Reference**: [Documentation](http://daehwankimlab.github.io/hisat2/) | [GitHub](https://github.com/DaehwanKimLab/hisat2)

**Rationale**: HISAT2 is a splice-aware aligner optimized for RNA-seq. It uses a graph-based index that incorporates known splice sites and SNPs. Like STAR, its presence strongly indicates transcriptomic data.

#### `program_tophat`

- **Pattern**: `tophat`
- **Classification**: transcriptomic
- **Confidence**: 95%
- **Reference**: [Manual](https://ccb.jhu.edu/software/tophat/manual.shtml) | [GitHub](https://github.com/DaehwanKimLab/tophat)

**Rationale**: TopHat was an early splice-aware aligner for RNA-seq (now superseded by HISAT2). It identifies splice junctions and aligns reads across them. Legacy RNA-seq data may still have TopHat in the header.

#### `program_salmon`

- **Pattern**: `salmon`
- **Classification**: transcriptomic
- **Confidence**: 95%
- **Reference**: [Documentation](https://salmon.readthedocs.io/) | [GitHub](https://github.com/COMBINE-lab/salmon)

**Rationale**: Salmon is a transcript-level quantification tool for RNA-seq. It uses quasi-mapping for fast, accurate abundance estimation. Presence indicates processed RNA-seq data.

#### `program_kallisto`

- **Pattern**: `kallisto`
- **Classification**: transcriptomic
- **Confidence**: 95%
- **Reference**: [Manual](https://pachterlab.github.io/kallisto/manual) | [DOI:10.1038/nbt.3519](https://doi.org/10.1038/nbt.3519)

**Rationale**: Kallisto performs rapid transcript quantification using pseudoalignment. Like Salmon, it's specifically designed for RNA-seq analysis.

---

### DNA Alignment Programs

*Source: @PG PN field*

#### `program_bwa`

- **Pattern**: `bwa`
- **Classification**: genomic
- **Confidence**: 80%
- **Reference**: [GitHub](https://github.com/lh3/bwa) | [BWA-MEM2](https://github.com/bwa-mem2/bwa-mem2)

**Rationale**: BWA (Burrows-Wheeler Aligner) is the standard short-read aligner for DNA sequencing. It's optimized for aligning reads to a reference genome without splice awareness. Commonly used for WGS, WES, and ChIP-seq. Confidence is not 100% because BWA can technically be used for non-spliced RNA alignment.

#### `program_minimap2`

- **Pattern**: `minimap2`
- **Classification**: genomic
- **Confidence**: 75%
- **Reference**: [GitHub](https://github.com/lh3/minimap2) | [Man Page](https://lh3.github.io/minimap2/minimap2.html)

**Rationale**: Minimap2 is a versatile aligner for long reads (PacBio, ONT) and assemblies. While primarily used for genomic alignment, it can also be used for direct RNA sequencing with appropriate presets (-ax splice). Confidence moderate due to this dual use.

#### `program_bowtie2`

- **Pattern**: `bowtie2`
- **Classification**: genomic
- **Confidence**: 75%
- **Reference**: [Manual](https://bowtie-bio.sourceforge.net/bowtie2/manual.shtml) | [GitHub](https://github.com/BenLangmead/bowtie2)

**Rationale**: Bowtie2 is a fast short-read aligner commonly used for ChIP-seq, ATAC-seq, and WGS. It doesn't handle spliced alignment, so presence suggests genomic or epigenomic data rather than RNA-seq. However, it's sometimes used for small RNA sequencing.

---

### PacBio Programs

*Source: @PG PN field*

#### `program_ccs`

- **Pattern**: `ccs`
- **Classification**: genomic.whole_genome
- **Confidence**: 85%
- **Reference**: [GitHub](https://github.com/PacificBiosciences/ccs) | [Documentation](https://ccs.how/)

**Rationale**: The 'ccs' program generates HiFi reads from PacBio subreads. Its presence confirms this is PacBio HiFi data, typically used for high-quality genome assembly and variant calling.

#### `program_isoseq`

- **Pattern**: `isoseq`
- **Classification**: transcriptomic
- **Confidence**: 95%
- **Reference**: [GitHub](https://github.com/PacificBiosciences/IsoSeq) | [Documentation](https://isoseq.how/)

**Rationale**: IsoSeq is PacBio's full-length transcript sequencing method. The 'isoseq' program in @PG indicates this is long-read RNA-seq data for transcript discovery and isoform characterization.

#### `program_lima`

- **Pattern**: `lima`
- **Classification**: N/A (ambiguous)
- **Confidence**: 0%

**Rationale**: Lima is PacBio's barcode demultiplexer. It separates multiplexed samples but doesn't indicate data modality. Other header info needed.

---

### Reference Assembly

*Source: @SQ SN/AS fields*

> **References**:
> - GRCh38: [NCBI](https://www.ncbi.nlm.nih.gov/datasets/genome/GCF_000001405.40/) | [GRC Data](https://www.ncbi.nlm.nih.gov/grc/human/data?asm=GRCh38.p14)
> - GRCh37: [NCBI Assembly](https://www.ncbi.nlm.nih.gov/assembly/2758) | [Ensembl Archive](https://grch37.ensembl.org)
> - CHM13: [GitHub](https://github.com/marbl/CHM13) | [Science 2022](https://www.science.org/doi/10.1126/science.abj6987)
> - [GATK Reference Guide](https://gatk.broadinstitute.org/hc/en-us/articles/360035890951-Human-genome-reference-builds-GRCh38-or-hg38-b37-hg19)

#### `ref_grch38_hg38`

- **Pattern**: `(?i)(grch38|hg38|hs38)`
- **Classification**: GRCh38
- **Confidence**: 95%

**Rationale**: Contig names containing 'GRCh38', 'hg38', or 'hs38' indicate alignment to the GRCh38 human reference genome (released 2013, current standard). The @SQ lines list all reference sequences the reads are aligned against.

#### `ref_grch37_hg19`

- **Pattern**: `(?i)(grch37|hg19|hs37)`
- **Classification**: GRCh37
- **Confidence**: 95%

**Rationale**: Contig names containing 'GRCh37', 'hg19', or 'hs37' indicate alignment to the GRCh37 human reference (released 2009). Still used for legacy data and some clinical pipelines for compatibility.

#### `ref_chm13_t2t`

- **Pattern**: `(?i)(chm13|t2t|hs1)`
- **Classification**: CHM13
- **Confidence**: 95%

**Rationale**: Contig names containing 'CHM13', 'T2T', or 'hs1' indicate alignment to the T2T-CHM13 reference (released 2022). This is the first complete human genome assembly, filling gaps in GRCh38 including centromeres and telomeres.

#### `ref_assembly_tag`

- **Pattern**: `.*`
- **Classification**: N/A (ambiguous)
- **Confidence**: 90%

**Rationale**: The AS (Assembly) tag in @SQ lines explicitly names the reference assembly. When present, it provides definitive reference identification.

---

### Unaligned Detection

*Source: @SQ absence*

#### `unaligned_no_sq`

- **Pattern**: `(absent)`
- **Classification**: unaligned
- **Confidence**: 90%

**Rationale**: Absence of @SQ lines in the header indicates unaligned reads. The BAM contains raw sequencing data not yet mapped to a reference genome. Common for PacBio HiFi deliverables before alignment.

---

## Consistency Validation Rules

The classifier validates that multiple signals in the same header are consistent.
Convergent signals (that agree) increase confidence, while conflicting signals
indicate potential errors and reduce confidence.

### Convergent Signals (Should Agree)

These signal pairs reinforce each other when both are present:

#### `pacbio_platform_readtype`

- **Signal A**: `platform_pacbio`
- **Signal B**: `pacbio_hifi`
- **Expected Agreement**: genomic.whole_genome

**Rationale**: PL:PACBIO and READTYPE=CCS both indicate PacBio HiFi sequencing, which is used for whole genome sequencing. These signals reinforce each other.

#### `pacbio_platform_ccs_program`

- **Signal A**: `platform_pacbio`
- **Signal B**: `program_ccs`
- **Expected Agreement**: genomic.whole_genome

**Rationale**: PL:PACBIO platform with ccs program confirms PacBio HiFi data generation.

#### `pacbio_hifi_ccs_program`

- **Signal A**: `pacbio_hifi`
- **Signal B**: `program_ccs`
- **Expected Agreement**: genomic.whole_genome

**Rationale**: READTYPE=CCS and PN:ccs both indicate HiFi consensus calling was performed.

#### `illumina_bwa`

- **Signal A**: `platform_illumina`
- **Signal B**: `program_bwa`
- **Expected Agreement**: genomic

**Rationale**: Illumina platform with BWA aligner is the standard WGS/WES pipeline. Both indicate short-read DNA sequencing.

#### `illumina_star`

- **Signal A**: `platform_illumina`
- **Signal B**: `program_star`
- **Expected Agreement**: transcriptomic

**Rationale**: Illumina platform with STAR aligner indicates standard RNA-seq workflow.

#### `pacbio_minimap2`

- **Signal A**: `platform_pacbio`
- **Signal B**: `program_minimap2`
- **Expected Agreement**: genomic

**Rationale**: PacBio platform with minimap2 is the standard long-read alignment pipeline.

#### `ont_minimap2`

- **Signal A**: `platform_ont`
- **Signal B**: `program_minimap2`
- **Expected Agreement**: genomic

**Rationale**: ONT platform with minimap2 is the standard nanopore alignment pipeline.

#### `pacbio_isoseq`

- **Signal A**: `platform_pacbio`
- **Signal B**: `program_isoseq`
- **Expected Agreement**: transcriptomic

**Rationale**: PacBio platform with IsoSeq program indicates long-read RNA sequencing.

---

### Conflicting Signals (Indicate Errors)

These signal pairs should NOT appear together. If found, confidence is reduced:

#### `pacbio_star_conflict`

- **Signal A**: `platform_pacbio`
- **Signal B**: `program_star`

**Rationale**: STAR is a short-read splice-aware aligner not designed for PacBio long reads. This combination is unexpected and may indicate a pipeline error or misannotation.

#### `illumina_ccs_conflict`

- **Signal A**: `platform_illumina`
- **Signal B**: `pacbio_hifi`

**Rationale**: READTYPE=CCS is PacBio-specific. Finding it with PL:ILLUMINA indicates a header error or file corruption.

#### `illumina_ccs_program_conflict`

- **Signal A**: `platform_illumina`
- **Signal B**: `program_ccs`

**Rationale**: The ccs program is PacBio-specific. Finding it with Illumina platform indicates a header error.

#### `ont_ccs_conflict`

- **Signal A**: `platform_ont`
- **Signal B**: `pacbio_hifi`

**Rationale**: READTYPE=CCS is PacBio-specific and incompatible with ONT platform.

#### `bwa_star_conflict`

- **Signal A**: `program_bwa`
- **Signal B**: `program_star`

**Rationale**: BWA (DNA aligner) and STAR (RNA aligner) in the same file suggests mixed or incorrectly processed data. Files should use one or the other.

#### `dna_rna_aligner_conflict`

- **Signal A**: `program_bowtie2`
- **Signal B**: `program_star`

**Rationale**: Bowtie2 (DNA/ChIP aligner) and STAR (RNA aligner) indicate conflicting data modalities in the same file.

---

## File Size Rules (WGS vs WES)

File size helps distinguish Whole Genome Sequencing (WGS) from Whole Exome Sequencing (WES):

| Type | Typical BAM Size | Typical CRAM Size |
|------|------------------|-------------------|
| WGS 30x | 50-150 GB | 15-50 GB |
| WES 100x | 5-15 GB | 2-8 GB |

The ~10:1 ratio exists because WGS covers the whole genome (~3 billion bases) while
WES only covers exons (~1-2% of genome, ~30-60 million bases).

**Caveats:**
- Coverage depth varies (higher coverage = larger files)
- CRAM is ~60-70% smaller than BAM
- Some files may be subsets or downsampled
- Long-read BAMs (PacBio/ONT) are typically larger due to read length

#### `illumina_bam_wgs_large`

- **Size Range**: 50 GB - any
- **Platform**: ILLUMINA
- **File Format**: .bam
- **Classification**: genomic.whole_genome
- **Confidence**: 80%

**Rationale**: Illumina BAM files >50 GB strongly suggest WGS. At 30x coverage, a human WGS BAM is typically 80-120 GB. WES files rarely exceed 20 GB even at high coverage.

#### `illumina_bam_wgs_medium`

- **Size Range**: 30 GB - 50 GB
- **Platform**: ILLUMINA
- **File Format**: .bam
- **Classification**: genomic.whole_genome
- **Confidence**: 65%

**Rationale**: Illumina BAM files 30-50 GB likely indicate WGS at lower coverage (15-20x) or WES at very high coverage (200x+). WGS is more common in this range.

#### `illumina_bam_wes_likely`

- **Size Range**: 5 GB - 20 GB
- **Platform**: ILLUMINA
- **File Format**: .bam
- **Classification**: genomic.exome
- **Confidence**: 60%

**Rationale**: Illumina BAM files 5-20 GB are typical for WES at 80-150x coverage. Could also be low-coverage WGS, but WES is more common in this size range.

#### `illumina_cram_wgs_large`

- **Size Range**: 20 GB - any
- **Platform**: ILLUMINA
- **File Format**: .cram
- **Classification**: genomic.whole_genome
- **Confidence**: 80%

**Rationale**: Illumina CRAM files >20 GB strongly suggest WGS. CRAM compression reduces file size by 60-70% vs BAM, so a 20 GB CRAM corresponds to ~50-70 GB BAM.

#### `illumina_cram_wgs_medium`

- **Size Range**: 10 GB - 20 GB
- **Platform**: ILLUMINA
- **File Format**: .cram
- **Classification**: genomic.whole_genome
- **Confidence**: 65%

**Rationale**: Illumina CRAM files 10-20 GB likely indicate WGS at moderate coverage.

#### `illumina_cram_wes_likely`

- **Size Range**: 2 GB - 8 GB
- **Platform**: ILLUMINA
- **File Format**: .cram
- **Classification**: genomic.exome
- **Confidence**: 60%

**Rationale**: Illumina CRAM files 2-8 GB are typical for WES. This corresponds to ~5-20 GB BAM, the standard WES size range.

#### `pacbio_large_wgs`

- **Size Range**: 20 GB - any
- **Platform**: PACBIO
- **File Format**: any
- **Classification**: genomic.whole_genome
- **Confidence**: 75%

**Rationale**: Large PacBio files (>20 GB) typically indicate WGS. PacBio is rarely used for WES due to cost; it's primarily used for WGS and structural variant detection.

#### `ont_large_wgs`

- **Size Range**: 20 GB - any
- **Platform**: ONT
- **File Format**: any
- **Classification**: genomic.whole_genome
- **Confidence**: 75%

**Rationale**: Large ONT files (>20 GB) typically indicate WGS. ONT is rarely used for targeted sequencing; its strength is in long-range structural analysis.

---

## VCF Header Classification Rules

> **Specification**: [VCF v4.5](https://samtools.github.io/hts-specs/VCFv4.5.pdf) |
> [VCF v4.3](https://samtools.github.io/hts-specs/VCFv4.3.pdf) |
> [hts-specs GitHub](https://github.com/samtools/hts-specs)

VCF files contain rich metadata in `##` header lines that can identify:
- Reference genome (from `##reference=` and `##contig=` lines)
- Variant caller (from `##source=` line)
- Variant type (germline, somatic, structural, CNV)

### VCF Header Line Reference

| Line Type | Description | Example |
|-----------|-------------|---------|
| `##fileformat` | VCF version | `##fileformat=VCFv4.2` |
| `##reference` | Reference genome path | `##reference=file:///path/to/GRCh38.fa` |
| `##contig` | Contig definitions | `##contig=<ID=chr1,length=248956422,assembly=GRCh38>` |
| `##source` | Variant caller | `##source=GATK HaplotypeCaller` |
| `##INFO` | INFO field definitions | `##INFO=<ID=DP,Number=1,Type=Integer,...>` |
| `##FORMAT` | FORMAT field definitions | `##FORMAT=<ID=GT,Number=1,Type=String,...>` |

### Reference Assembly Detection

#### `vcf_ref_grch38`

- **Header Type**: `##reference`
- **Pattern**: `(?i)(grch38|hg38|hs38|GCA_000001405\.15)`
- **Classification**: GRCh38
- **Confidence**: 95%

**Rationale**: ##reference line containing GRCh38, hg38, or the GRCh38 GenBank accession (GCA_000001405.15) indicates variants were called against the GRCh38 reference.

#### `vcf_ref_grch37`

- **Header Type**: `##reference`
- **Pattern**: `(?i)(grch37|hg19|hs37|GCA_000001405\.1[^5]|b37)`
- **Classification**: GRCh37
- **Confidence**: 95%

**Rationale**: ##reference line containing GRCh37, hg19, b37, or earlier GRCh37 accessions indicates variants were called against the GRCh37 reference.

#### `vcf_ref_chm13`

- **Header Type**: `##reference`
- **Pattern**: `(?i)(chm13|t2t|hs1)`
- **Classification**: CHM13
- **Confidence**: 95%

**Rationale**: ##reference line containing CHM13 or T2T indicates variants called against the T2T-CHM13 complete human genome assembly.

#### `vcf_contig_grch38`

- **Header Type**: `##contig`
- **Pattern**: `(?i)assembly=(grch38|hg38|GCA_000001405\.15)`
- **Classification**: GRCh38
- **Confidence**: 95%

**Rationale**: ##contig lines with assembly=GRCh38 explicitly declare the reference genome.

#### `vcf_contig_grch37`

- **Header Type**: `##contig`
- **Pattern**: `(?i)assembly=(grch37|hg19|b37)`
- **Classification**: GRCh37
- **Confidence**: 95%

**Rationale**: ##contig lines with assembly=GRCh37 explicitly declare the reference genome.

#### `vcf_contig_chm13`

- **Header Type**: `##contig`
- **Pattern**: `(?i)assembly=(chm13|t2t|hs1)`
- **Classification**: CHM13
- **Confidence**: 95%

**Rationale**: ##contig lines with assembly=CHM13 explicitly declare the reference genome.

---

### Reference Assembly Detection by Contig Length

Chromosome lengths are unique to each reference assembly, providing definitive identification even when `##reference` or `assembly=` tags are missing. The classifier matches `##contig=<ID=chr1,length=...>` lines against known reference sizes.

| Chromosome | GRCh37      | GRCh38      | CHM13       |
|------------|-------------|-------------|-------------|
| chr1       | 249,250,621 | 248,956,422 | 248,387,497 |
| chr2       | 243,199,373 | 242,193,529 | 242,696,747 |
| chr3       | 198,022,430 | 198,295,559 | 201,106,605 |
| chr10      | 135,534,747 | 133,797,422 | 134,758,134 |
| chr22      |  51,304,566 |  50,818,468 |  51,324,926 |

#### `vcf_contig_length`

- **Header Type**: `##contig`
- **Pattern**: `##contig=<ID=([^,>]+),length=(\d+)`
- **Classification**: GRCh38, GRCh37, or CHM13
- **Confidence**: 98% (exact match), 95% (fuzzy match ±1000bp)

**Rationale**: Chromosome lengths are unique fingerprints for each reference assembly. Matching multiple contig lengths against known reference sizes provides definitive assembly identification. Fuzzy matching handles minor version differences (e.g., CHM13 v1.0 vs v2.0).

#### `vcf_max_positions`

- **Header Type**: Variant data (first 100 records)
- **Pattern**: Position exceeds chromosome length
- **Classification**: GRCh38, GRCh37, or CHM13 (by elimination)
- **Confidence**: 90%

**Rationale**: When header-based detection fails, max variant positions can rule out references where positions exceed chromosome lengths. For example, a variant at chr1:249,000,000 rules out CHM13 (248,387,497) and GRCh38 (248,956,422), leaving GRCh37.

---

### Germline Variant Callers

#### `vcf_gatk_haplotypecaller`

- **Pattern**: `(?i)haplotypecaller`
- **Classification**: genomic.germline_variants
- **Confidence**: 90%
- **Reference**: [GATK Docs](https://gatk.broadinstitute.org/hc/en-us/articles/360037225632-HaplotypeCaller) | [GitHub](https://github.com/broadinstitute/gatk)

**Rationale**: GATK HaplotypeCaller is the standard germline SNV/indel caller. It performs local de novo assembly to call variants, optimized for diploid germline samples.

#### `vcf_deepvariant`

- **Pattern**: `(?i)deepvariant`
- **Classification**: genomic.germline_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/google/deepvariant) | [Documentation](https://google.github.io/deepvariant/)

**Rationale**: DeepVariant is Google's deep learning-based germline variant caller. It's trained on truth sets and excels at both SNVs and indels.

#### `vcf_gatk_genotypegvcfs`

- **Pattern**: `(?i)genotypegvcfs`
- **Classification**: genomic.germline_variants
- **Confidence**: 90%
- **Reference**: [GATK Docs](https://gatk.broadinstitute.org/hc/en-us/articles/360037057852-GenotypeGVCFs)

**Rationale**: GATK GenotypeGVCFs performs joint genotyping on gVCF files, used in cohort germline variant calling workflows.

#### `vcf_glnexus`

- **Pattern**: `(?i)glnexus`
- **Classification**: genomic.germline_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/dnanexus-rnd/GLnexus)

**Rationale**: GLnexus is a scalable gVCF merging and joint genotyping tool, commonly used with DeepVariant for population-scale germline calling.

#### `vcf_bcftools_call`

- **Pattern**: `(?i)bcftools.*call`
- **Classification**: genomic.germline_variants
- **Confidence**: 85%
- **Reference**: [samtools.github.io](https://samtools.github.io/bcftools/bcftools.html#call)

**Rationale**: bcftools call is a lightweight germline variant caller using the multiallelic or consensus caller models.

#### `vcf_freebayes`

- **Pattern**: `(?i)freebayes`
- **Classification**: genomic.germline_variants
- **Confidence**: 85%
- **Reference**: [GitHub](https://github.com/freebayes/freebayes)

**Rationale**: FreeBayes is a Bayesian haplotype-based germline variant caller that can handle pooled or mixed samples.

#### `vcf_strelka2_germline`

- **Pattern**: `(?i)strelka2.*germline|strelka2(?!.*somatic)`
- **Classification**: genomic.germline_variants
- **Confidence**: 85%
- **Reference**: [GitHub](https://github.com/Illumina/strelka)

**Rationale**: Strelka2 in germline mode calls SNVs and indels from germline samples.

---

### Somatic Variant Callers

#### `vcf_mutect2`

- **Pattern**: `(?i)mutect2?`
- **Classification**: genomic.somatic_variants
- **Confidence**: 95%
- **Reference**: [GATK Docs](https://gatk.broadinstitute.org/hc/en-us/articles/360037593851-Mutect2) | [GitHub](https://github.com/broadinstitute/gatk)

**Rationale**: GATK Mutect2 is the standard somatic SNV/indel caller for tumor-normal or tumor-only analysis. Its presence strongly indicates cancer genomics data.

#### `vcf_strelka_somatic`

- **Pattern**: `(?i)strelka.*somatic|strelka(?!.*germline)`
- **Classification**: genomic.somatic_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/Illumina/strelka)

**Rationale**: Strelka/Strelka2 in somatic mode calls somatic variants from tumor-normal pairs.

#### `vcf_varscan_somatic`

- **Pattern**: `(?i)varscan.*somatic`
- **Classification**: genomic.somatic_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/dkoboldt/varscan)

**Rationale**: VarScan somatic mode calls somatic variants from tumor-normal pairs using a heuristic/statistical approach.

#### `vcf_somaticsniper`

- **Pattern**: `(?i)somaticsniper`
- **Classification**: genomic.somatic_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/genome/somatic-sniper)

**Rationale**: SomaticSniper identifies somatic point mutations in tumor-normal pairs.

#### `vcf_muse`

- **Pattern**: `(?i)muse`
- **Classification**: genomic.somatic_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/danielfan/MuSE)

**Rationale**: MuSE calls somatic point mutations using a Markov substitution model, designed for tumor-normal pairs.

---

### Structural Variant Callers

#### `vcf_manta`

- **Pattern**: `(?i)manta`
- **Classification**: genomic.structural_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/Illumina/manta) | [DOI:10.1093/bioinformatics/btv710](https://doi.org/10.1093/bioinformatics/btv710)

**Rationale**: Manta calls structural variants (deletions, insertions, inversions, translocations) and large indels from short-read data.

#### `vcf_delly`

- **Pattern**: `(?i)delly`
- **Classification**: genomic.structural_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/dellytools/delly) | [PMID:22962449](https://pubmed.ncbi.nlm.nih.gov/22962449/)

**Rationale**: DELLY discovers structural variants using paired-end and split-read analysis.

#### `vcf_lumpy`

- **Pattern**: `(?i)lumpy`
- **Classification**: genomic.structural_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/arq5x/lumpy-sv)

**Rationale**: LUMPY is a probabilistic SV caller using multiple alignment signals.

#### `vcf_smoove`

- **Pattern**: `(?i)smoove`
- **Classification**: genomic.structural_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/brentp/smoove)

**Rationale**: Smoove simplifies SV calling by wrapping LUMPY with additional filtering.

#### `vcf_svim`

- **Pattern**: `(?i)svim`
- **Classification**: genomic.structural_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/eldariont/svim)

**Rationale**: SVIM detects structural variants from long-read sequencing data (PacBio/ONT).

#### `vcf_sniffles`

- **Pattern**: `(?i)sniffles`
- **Classification**: genomic.structural_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/fritzsedlazeck/Sniffles)

**Rationale**: Sniffles is a long-read SV caller optimized for PacBio and ONT data, detecting complex SVs that short reads miss.

#### `vcf_pbsv`

- **Pattern**: `(?i)pbsv`
- **Classification**: genomic.structural_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/PacificBiosciences/pbsv)

**Rationale**: PBSV is PacBio's structural variant caller for HiFi and CLR data.

#### `vcf_cutesv`

- **Pattern**: `(?i)cutesv`
- **Classification**: genomic.structural_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/tjiangHIT/cuteSV)

**Rationale**: CuteSV is a fast long-read SV caller using clustering of signatures.

---

### Copy Number Variant Callers

#### `vcf_cnvkit`

- **Pattern**: `(?i)cnvkit`
- **Classification**: genomic.copy_number_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/etal/cnvkit) | [Documentation](https://cnvkit.readthedocs.io/)

**Rationale**: CNVkit detects copy number variants from targeted/exome or WGS data.

#### `vcf_gatk_cnv`

- **Pattern**: `(?i)gatk.*(cnv|copynumber)|modelsegments`
- **Classification**: genomic.copy_number_variants
- **Confidence**: 90%
- **Reference**: [GATK CNV Docs](https://gatk.broadinstitute.org/hc/en-us/articles/360035531092-Copy-Number-Variation-Pipelines)

**Rationale**: GATK CNV tools (ModelSegments, etc.) call copy number variants from read depth data.

#### `vcf_canvas`

- **Pattern**: `(?i)canvas`
- **Classification**: genomic.copy_number_variants
- **Confidence**: 90%
- **Reference**: [GitHub](https://github.com/Illumina/canvas)

**Rationale**: Canvas is Illumina's CNV caller for WGS and tumor-normal analysis.

---

### INFO Field Indicators

#### `vcf_info_somatic`

- **Pattern**: `ID=(SOMATIC|TUMOR_|NORMAL_|TumorVAF|NormalVAF)`
- **Classification**: genomic.somatic_variants
- **Confidence**: 85%

**Rationale**: INFO fields with SOMATIC, TUMOR_, or NORMAL_ prefixes indicate this VCF contains somatic variant calls from tumor-normal analysis.

#### `vcf_info_sv`

- **Pattern**: `ID=(SVTYPE|SVLEN|END|CIPOS|CIEND|MATEID|IMPRECISE)`
- **Classification**: genomic.structural_variants
- **Confidence**: 80%

**Rationale**: Standard SV INFO fields (SVTYPE, SVLEN, CIPOS, etc.) indicate this VCF contains structural variant calls.

#### `vcf_info_cnv`

- **Pattern**: `ID=(CN|FOLD_CHANGE|PROBES|LOG2_COPY_RATIO)`
- **Classification**: genomic.copy_number_variants
- **Confidence**: 80%

**Rationale**: CNV-specific INFO fields indicate copy number variant calls.

---

## FASTQ Read Name Classification Rules

> **References**:
> - Illumina: [FASTQ Files Documentation](https://help.basespace.illumina.com/files-used-by-basespace/fastq-files) | [Knowledge Base](https://knowledge.illumina.com/software/general/software-general-reference_material-list/000002211)
> - PacBio: [BAM Format Specification](https://pacbiofileformats.readthedocs.io/en/latest/BAM.html)
> - ONT: [Output Specifications](https://software-docs.nanoporetech.com/output-specifications/25.05/read_formats/fastq/)
> - Archives: [ENA Accessions](https://ena-docs.readthedocs.io/en/latest/submit/general-guide/accessions.html) | [INSDC](https://www.insdc.org/)

FASTQ read names have platform-specific formats that can identify the sequencing platform,
instrument model, and read type without inspecting the sequence data.

### Read Name Format Examples

| Platform | Example Read Name | Format |
|----------|------------------|--------|
| **Illumina (modern)** | `@A00488:61:HFWFVDSXX:1:1101:1000:1000` | `@instrument:run:flowcell:lane:tile:x:y` |
| **Illumina (legacy)** | `@HWUSI-EAS100R:6:73:941:1973#0/1` | `@instrument:lane:tile:x:y#index/read` |
| **ENA/SRA reformatted** | `@ERR123456.1 A00297:44:HFKH3DSXX:...` | `@accession.seq [original read name]` |
| **PacBio CCS/HiFi** | `@m64011_190830_220126/1/ccs` | `@movie/zmw/ccs` |
| **PacBio CLR** | `@m64011_190830_220126/1234/0_5000` | `@movie/zmw/start_end` |
| **ONT** | `@a1b2c3d4-e5f6-7890-abcd-ef1234567890` | `@uuid [key=value...]` |
| **MGI/BGI** | `@V350012345L1C001R0010000001/1` | `@flowcellLaneCcolumnRrow/pair` |

### Illumina Read Names

#### `fastq_illumina_modern`

- **Pattern**: `^@[A-Z0-9-]+:\d+:[A-Z0-9]+:\d+:\d+:\d+:\d+`
- **Platform**: ILLUMINA
- **Classification**: genomic
- **Confidence**: 90%

**Rationale**: Modern Illumina read names (Casava 1.8+) follow the format @instrument:run:flowcell:lane:tile:x:y. This format is used by HiSeq 2500+, NovaSeq, NextSeq, and MiSeq instruments.

#### `fastq_illumina_legacy`

- **Pattern**: `^@[A-Z0-9-]+:\d+:\d+:\d+:\d+#`
- **Platform**: ILLUMINA
- **Classification**: genomic
- **Confidence**: 85%

**Rationale**: Legacy Illumina read names follow @instrument:lane:tile:x:y#index format. Used by older instruments like GA, GAIIx, HiSeq 2000.

#### `fastq_illumina_srr`

- **Pattern**: `^@SRR\d+\.\d+`
- **Platform**: ILLUMINA
- **Classification**: genomic
- **Confidence**: 70%

**Rationale**: SRA-reformatted read names starting with @SRR typically indicate Illumina data downloaded from NCBI SRA. Lower confidence as original platform info is lost.

---

### PacBio Read Names

#### `fastq_pacbio_ccs`

- **Pattern**: `^@m\d+[_e]?\d*_\d+_\d+/\d+/ccs`
- **Platform**: PACBIO
- **Classification**: genomic.whole_genome
- **Confidence**: 95%

**Rationale**: PacBio CCS (HiFi) read names follow @movie/zmw/ccs format. The 'ccs' suffix indicates Circular Consensus Sequencing was performed, producing high-accuracy long reads (>Q20). Movie names start with 'm' followed by instrument ID and timestamp.

#### `fastq_pacbio_clr`

- **Pattern**: `^@m\d+[_e]?\d*_\d+_\d+/\d+/\d+_\d+`
- **Platform**: PACBIO
- **Classification**: genomic.whole_genome
- **Confidence**: 90%

**Rationale**: PacBio CLR (Continuous Long Read) subread names follow @movie/zmw/start_end format. The start_end coordinates indicate the position within the ZMW polymerase read.

#### `fastq_pacbio_generic`

- **Pattern**: `^@m\d+[_e]?\d*_\d+_\d+/\d+`
- **Platform**: PACBIO
- **Classification**: genomic.whole_genome
- **Confidence**: 85%

**Rationale**: Generic PacBio read names follow @movie/zmw format. The movie name encodes the instrument (m=RSII/Sequel, followed by instrument ID) and run timestamp.

---

### Oxford Nanopore (ONT) Read Names

#### `fastq_ont_uuid`

- **Pattern**: `^@[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}`
- **Platform**: ONT
- **Classification**: genomic
- **Confidence**: 95%

**Rationale**: ONT read names are UUIDs (format: 8-4-4-4-12 hex characters). This uniquely identifies Oxford Nanopore data. Additional metadata like runid, read number, and channel may follow as key=value pairs.

#### `fastq_ont_metadata`

- **Pattern**: `runid=[a-f0-9]+`
- **Platform**: ONT
- **Classification**: genomic
- **Confidence**: 95%

**Rationale**: ONT reads often include 'runid=' metadata in the header line, providing the unique run identifier from MinKNOW.

---

### MGI/BGI Read Names

#### `fastq_mgi`

- **Pattern**: `^@[A-Z]\d{9}L\dC\d{3}R\d{3}\d+`
- **Platform**: MGI
- **Classification**: genomic
- **Confidence**: 90%

**Rationale**: MGI/BGI-SEQ read names follow @flowcellLaneCcolumnRrow format. MGI (formerly BGI) instruments use this distinctive naming convention with embedded lane (L), column (C), and row (R) identifiers.

#### `fastq_mgi_alt`

- **Pattern**: `^@[A-Z]\d+L\d+C\d+R\d+`
- **Platform**: MGI
- **Classification**: genomic
- **Confidence**: 85%

**Rationale**: Alternative MGI/BGI read name format with varying digit lengths.

---

### Other Platforms

#### `fastq_element`

- **Pattern**: `^@[A-Z0-9]+:[A-Z0-9]+:\d+:\d+:\d+:\d+:\d+`
- **Platform**: ELEMENT
- **Classification**: genomic
- **Confidence**: 80%

**Rationale**: Element Biosciences AVITI read names follow a similar format to Illumina but with different instrument ID patterns.

#### `fastq_ultima`

- **Pattern**: `^@[A-Z0-9]+_\d+_\d+_\d+_[ACGT]+`
- **Platform**: ULTIMA
- **Classification**: genomic
- **Confidence**: 80%

**Rationale**: Ultima Genomics read names include flow-space encoded sequences in the read identifier.

---

### Archive Accessions (ENA/SRA/DDBJ)

When FASTQ files are submitted to public archives (ENA, SRA, DDBJ), read names are
prefixed with accession IDs. The original instrument information is often preserved after the accession.

**Example**: `@ERR3242571.1 A00297:44:HFKH3DSXX:2:1354:30508:28839/1`
- Archive accession: `ERR3242571` (ENA)
- Original read name: `A00297:44:HFKH3DSXX:2:1354:30508:28839/1` (NovaSeq)

The accession can be used to query archive APIs for study metadata:
- **ENA**: `https://www.ebi.ac.uk/ena/browser/api/xml/ERRxxxxxxx`
- **SRA**: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra&id=SRRxxxxxxx`
- **DDBJ**: `https://ddbj.nig.ac.jp/resource/sra-run/DRRxxxxxxx`

#### `fastq_ena_err`

- **Pattern**: `^@ERR\d+\.\d+`
- **Archive**: ENA
- **Confidence**: 60%

**Rationale**: ERR accessions indicate data from the European Nucleotide Archive (ENA). The accession can be used to look up study metadata via ENA API. Original platform info may be preserved after the accession.

#### `fastq_sra_srr`

- **Pattern**: `^@SRR\d+\.\d+`
- **Archive**: SRA
- **Confidence**: 60%

**Rationale**: SRR accessions indicate data from NCBI Sequence Read Archive (SRA). The accession can be used to query SRA metadata. Original instrument info may follow after a space.

#### `fastq_ddbj_drr`

- **Pattern**: `^@DRR\d+\.\d+`
- **Archive**: DDBJ
- **Confidence**: 60%

**Rationale**: DRR accessions indicate data from DDBJ Sequence Read Archive (Japan). The accession links to DDBJ metadata resources.

---

### Paired-End Detection

#### `fastq_paired_r1`

- **Pattern**: `[/\s][12]$|[/\s][12]:|_R[12]_|\.R[12]\.|_r[12]_|\.r[12]\.`
- **Confidence**: 80%

**Rationale**: Read 1 or Read 2 indicators (/1, /2, _R1_, _R2_) suggest paired-end sequencing. This is common for Illumina WGS, WES, and RNA-seq workflows.

---


