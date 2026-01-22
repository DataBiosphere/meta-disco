# File Formats Reference

A reference guide for bioinformatics file formats commonly found in AnVIL, including their purpose, typical contents, producing tools, and classification implications.

---

## Alignment Files

### BAM (.bam)
**Binary Alignment Map**

| Property | Value |
|----------|-------|
| **Contains** | Aligned sequencing reads mapped to a reference genome |
| **Binary/Text** | Binary (compressed) |
| **Modality** | Ambiguous - could be genomic (WGS/WES), transcriptomic (RNA-seq), or epigenomic (ChIP/ATAC) |
| **Reference** | Encoded in header (@SQ lines) |

**Producing Tools:**
- [BWA](https://github.com/lh3/bwa) - Burrows-Wheeler Aligner for DNA sequences
- [Bowtie2](https://bowtie-bio.sourceforge.net/bowtie2/) - Fast aligner for DNA
- [STAR](https://github.com/alexdobin/STAR) - Spliced aligner for RNA-seq
- [HISAT2](http://daehwankimlab.github.io/hisat2/) - Graph-based aligner for RNA-seq
- [minimap2](https://github.com/lh3/minimap2) - Long-read and assembly aligner

**Classification Notes:**
- Header inspection can reveal reference assembly and read groups
- STAR output (RNA-seq) often has `Aligned.sortedByCoord.out.bam` naming
- File size correlates with coverage: WGS (~50-150GB), RNA-seq (~2-20GB)

---

### CRAM (.cram)
**Compressed Reference-oriented Alignment Map**

| Property | Value |
|----------|-------|
| **Contains** | Same as BAM but more compressed using reference-based compression |
| **Binary/Text** | Binary (highly compressed) |
| **Modality** | Same ambiguity as BAM |
| **Reference** | Required for decompression; encoded in header |

**Producing Tools:**
- [samtools](http://www.htslib.org/) - `samtools view -C` converts BAM to CRAM
- [Cramtools](https://github.com/enasequence/cramtools) - CRAM utilities

**Classification Notes:**
- More common for archival storage (1000 Genomes, UK Biobank)
- Reference assembly is critical metadata (needed to read the file)

---

### SAM (.sam, .sam.gz)
**Sequence Alignment Map**

| Property | Value |
|----------|-------|
| **Contains** | Text version of BAM |
| **Binary/Text** | Text (optionally gzipped) |
| **Modality** | Same as BAM |

**Producing Tools:**
- Same as BAM (all aligners output SAM, then convert)

**Classification Notes:**
- Rarely stored long-term due to size
- Sometimes used for debugging or small datasets

---

## Variant Files

### VCF (.vcf, .vcf.gz)
**Variant Call Format**

| Property | Value |
|----------|-------|
| **Contains** | Genetic variants (SNPs, indels, structural variants) relative to a reference |
| **Binary/Text** | Text (often bgzipped) |
| **Modality** | **Genomic** - always |
| **Reference** | In header (##reference, ##contig lines) |

**Producing Tools:**
- [GATK HaplotypeCaller](https://gatk.broadinstitute.org/) - Gold standard for germline variants
- [DeepVariant](https://github.com/google/deepvariant) - Deep learning variant caller
- [bcftools](http://www.htslib.org/) - Variant calling and manipulation
- [FreeBayes](https://github.com/freebayes/freebayes) - Bayesian variant caller
- [Strelka2](https://github.com/Illumina/strelka) - Germline and somatic caller

**Classification Notes:**
- Always genomic data (DNA variants)
- gVCF (.g.vcf.gz) includes non-variant sites for joint calling
- Header contains reference assembly info

---

### BCF (.bcf)
**Binary Call Format**

| Property | Value |
|----------|-------|
| **Contains** | Binary version of VCF |
| **Binary/Text** | Binary |
| **Modality** | **Genomic** |

**Producing Tools:**
- [bcftools](http://www.htslib.org/) - `bcftools view -Ob`

---

## Sequencing Reads

### FASTQ (.fastq, .fq, .fastq.gz)
**FASTQ Format**

| Property | Value |
|----------|-------|
| **Contains** | Raw sequencing reads with quality scores |
| **Binary/Text** | Text (usually gzipped) |
| **Modality** | Ambiguous - depends on assay (WGS, RNA-seq, ATAC, ChIP, etc.) |
| **Reference** | None - unaligned |

**Producing Tools:**
- [bcl2fastq](https://support.illumina.com/sequencing/sequencing_software/bcl2fastq-conversion-software.html) - Illumina demultiplexing
- [Cell Ranger](https://support.10xgenomics.com/single-cell-gene-expression/software/pipelines/latest/what-is-cell-ranger) - 10x Genomics demultiplexing
- Sequencer output (Illumina, PacBio, Nanopore)

**Classification Notes:**
- Most ambiguous format - requires study context
- Paired-end files often named `_R1`/`_R2` or `_1`/`_2`
- File size varies widely by coverage and read length

---

### FAST5 (.fast5)
**Oxford Nanopore Format**

| Property | Value |
|----------|-------|
| **Contains** | Raw electrical signal from Nanopore sequencing |
| **Binary/Text** | Binary (HDF5-based) |
| **Modality** | Usually **genomic**, can be transcriptomic (direct RNA) |

**Producing Tools:**
- Oxford Nanopore sequencers (MinION, PromethION, etc.)

**Classification Notes:**
- Contains raw signal, not basecalled reads
- Direct RNA sequencing is minority use case
- Being replaced by POD5 format

---

### POD5 (.pod5)
**Oxford Nanopore POD5 Format**

| Property | Value |
|----------|-------|
| **Contains** | Next-generation Nanopore signal format (replacing FAST5) |
| **Binary/Text** | Binary |
| **Modality** | Same as FAST5 |

**Producing Tools:**
- Modern Oxford Nanopore sequencers and software

---

## Genotyping Files

### PLINK Binary (.pgen, .pvar, .psam)
**PLINK 2.0 Binary Format**

| Property | Value |
|----------|-------|
| **Contains** | Genotype calls, variant info, and sample info (trio of files) |
| **Binary/Text** | .pgen (binary), .pvar/.psam (text) |
| **Modality** | **Genomic** - genotyping data |

**Producing Tools:**
- [PLINK 2.0](https://www.cog-genomics.org/plink/2.0/) - Genome-wide association analysis
- Converted from VCF or array data

**Classification Notes:**
- Always genomic (SNP genotypes)
- Three files work together (.pgen + .pvar + .psam)
- Common in GWAS studies

---

## Single-Cell Files

### H5AD (.h5ad)
**AnnData HDF5**

| Property | Value |
|----------|-------|
| **Contains** | Single-cell expression matrix with annotations |
| **Binary/Text** | Binary (HDF5) |
| **Modality** | Usually **transcriptomic.single_cell**, can be ATAC |

**Producing Tools:**
- [Scanpy](https://scanpy.readthedocs.io/) - Single-cell analysis in Python
- [Cell Ranger](https://support.10xgenomics.com/) - 10x Genomics pipeline

**Classification Notes:**
- Standard format for scRNA-seq analysis
- Can also store scATAC-seq peak matrices

---

### Loom (.loom)
**Loom Format**

| Property | Value |
|----------|-------|
| **Contains** | Single-cell expression matrix |
| **Binary/Text** | Binary (HDF5-based) |
| **Modality** | **Transcriptomic.single_cell** |

**Producing Tools:**
- [Velocyto](http://velocyto.org/) - RNA velocity
- [SCENIC](https://scenic.aertslab.org/) - Gene regulatory networks

---

### MTX (.mtx, .mtx.gz)
**Matrix Market Format**

| Property | Value |
|----------|-------|
| **Contains** | Sparse expression matrix (usually with barcodes.tsv and features.tsv) |
| **Binary/Text** | Text (sparse matrix format) |
| **Modality** | **Transcriptomic.single_cell** |

**Producing Tools:**
- [Cell Ranger](https://support.10xgenomics.com/) - 10x Genomics output
- [STARsolo](https://github.com/alexdobin/STAR) - STAR single-cell mode

---

## Epigenomic Files

### IDAT (.idat)
**Illumina Intensity Data**

| Property | Value |
|----------|-------|
| **Contains** | Raw intensity values from Illumina BeadArrays |
| **Binary/Text** | Binary |
| **Modality** | **Epigenomic.methylation** (for methylation arrays like EPIC/450K) |

**Producing Tools:**
- Illumina array scanners
- Processed by [minfi](https://bioconductor.org/packages/minfi/), [sesame](https://bioconductor.org/packages/sesame/)

**Classification Notes:**
- Paired files: one for red channel, one for green
- EPIC array (850K probes) or 450K array

---

### BigWig (.bigwig, .bw)
**Binary Wiggle**

| Property | Value |
|----------|-------|
| **Contains** | Continuous signal values across genomic coordinates |
| **Binary/Text** | Binary |
| **Modality** | Ambiguous - depends on assay (ChIP, ATAC, RNA-seq coverage) |

**Producing Tools:**
- [deepTools](https://deeptools.readthedocs.io/) - `bamCoverage` for coverage tracks
- [bedGraphToBigWig](http://hgdownload.soe.ucsc.edu/admin/exe/) - UCSC converter
- [wigToBigWig](http://hgdownload.soe.ucsc.edu/admin/exe/) - UCSC converter

**Classification Notes:**
- Used for visualization in genome browsers
- ChIP-seq: histone modification signal
- ATAC-seq: chromatin accessibility signal
- RNA-seq: expression coverage

---

### BedGraph (.bedGraph)
**BedGraph Format**

| Property | Value |
|----------|-------|
| **Contains** | Signal values in BED-like format |
| **Binary/Text** | Text |
| **Modality** | Same as BigWig (depends on assay) |

**Producing Tools:**
- [bedtools](https://bedtools.readthedocs.io/) - `genomecov`
- Often converted to BigWig for efficiency

---

### NarrowPeak / BroadPeak (.narrowPeak, .broadPeak)
**ENCODE Peak Formats**

| Property | Value |
|----------|-------|
| **Contains** | Called peaks from ChIP-seq or ATAC-seq |
| **Binary/Text** | Text (BED-like) |
| **Modality** | **Epigenomic** (chromatin_accessibility or histone_modification) |

**Producing Tools:**
- [MACS2](https://github.com/macs3-project/MACS) - Peak caller for ChIP/ATAC
- [MACS3](https://github.com/macs3-project/MACS) - Updated version

**Classification Notes:**
- narrowPeak: sharp peaks (transcription factors, ATAC)
- broadPeak: broad peaks (histone modifications like H3K27me3)

---

## Genomic Intervals

### BED (.bed, .bed.gz)
**Browser Extensible Data**

| Property | Value |
|----------|-------|
| **Contains** | Genomic intervals (chr, start, end + optional fields) |
| **Binary/Text** | Text |
| **Modality** | Ambiguous - could be peaks, targets, annotations, etc. |

**Producing Tools:**
- Many tools output BED format
- [bedtools](https://bedtools.readthedocs.io/) - BED manipulation

**Classification Notes:**
- Very generic format
- Needs filename context (peaks, targets, regions)
- Often supplementary/reference data

---

## Annotation Files

### GTF/GFF (.gtf, .gff, .gff3)
**Gene Transfer Format / General Feature Format**

| Property | Value |
|----------|-------|
| **Contains** | Gene annotations (genes, transcripts, exons) |
| **Binary/Text** | Text |
| **Modality** | Reference annotation (not assay data) |

**Producing Tools:**
- [GENCODE](https://www.gencodegenes.org/) - Human/mouse annotations
- [Ensembl](https://www.ensembl.org/) - Multi-species annotations
- [StringTie](https://ccb.jhu.edu/software/stringtie/) - Transcript assembly

**Classification Notes:**
- Usually reference data, not sample data
- Skip for modality classification unless sample-specific assembly

---

## Image Files

### SVS (.svs)
**Aperio ScanScope Virtual Slide**

| Property | Value |
|----------|-------|
| **Contains** | Whole-slide histology/pathology images |
| **Binary/Text** | Binary (TIFF-based) |
| **Modality** | **Imaging** |

**Producing Tools:**
- Aperio slide scanners (Leica Biosystems)

**Classification Notes:**
- Large files (hundreds of MB to GB)
- Common in GTEx, TCGA for histology

---

## Index Files

### BAI (.bai)
**BAM Index**

| Property | Value |
|----------|-------|
| **Contains** | Index for random access to BAM file |
| **Companion to** | .bam |
| **Classification** | Skip - inherits from parent |

**Producing Tools:**
- [samtools](http://www.htslib.org/) - `samtools index`

---

### CRAI (.crai)
**CRAM Index**

| Property | Value |
|----------|-------|
| **Contains** | Index for CRAM file |
| **Companion to** | .cram |
| **Classification** | Skip - inherits from parent |

---

### TBI (.tbi)
**Tabix Index**

| Property | Value |
|----------|-------|
| **Contains** | Index for bgzipped tab-delimited files (VCF, BED, etc.) |
| **Companion to** | .vcf.gz, .bed.gz, etc. |
| **Classification** | Skip - inherits from parent |

**Producing Tools:**
- [tabix](http://www.htslib.org/) - `tabix -p vcf file.vcf.gz`

---

### CSI (.csi)
**Coordinate-Sorted Index**

| Property | Value |
|----------|-------|
| **Contains** | Alternative index format for very large chromosomes |
| **Companion to** | .vcf.gz, .bam (when chromosomes > 2^29 bp) |
| **Classification** | Skip - inherits from parent |

**Producing Tools:**
- [tabix](http://www.htslib.org/) - `tabix -C`
- [samtools](http://www.htslib.org/) - `samtools index -c`

---

### FAI (.fai)
**FASTA Index**

| Property | Value |
|----------|-------|
| **Contains** | Index for FASTA reference files |
| **Companion to** | .fa, .fasta |
| **Classification** | Skip - reference data |

**Producing Tools:**
- [samtools](http://www.htslib.org/) - `samtools faidx`

---

### PBI (.pbi)
**PacBio BAM Index**

| Property | Value |
|----------|-------|
| **Contains** | PacBio-specific BAM index with ZMW information |
| **Companion to** | .bam (PacBio) |
| **Classification** | Skip - inherits from parent |

**Producing Tools:**
- [pbindex](https://github.com/PacificBiosciences/pbbam) - PacBio BAM tools

---

## Archive Files

### TAR (.tar, .tar.gz)
**Tape Archive**

| Property | Value |
|----------|-------|
| **Contains** | Collection of files |
| **Modality** | Unknown - depends on contents |

**Classification Notes:**
- Requires inspection or context
- In T2T dataset, contains genomic region data

---

## Checksum Files

### MD5 (.md5)
**MD5 Checksum**

| Property | Value |
|----------|-------|
| **Contains** | MD5 hash for data integrity verification |
| **Classification** | Skip - not data |

---

## Reference Assemblies Quick Reference

| Assembly | Aliases | Organism | Notes |
|----------|---------|----------|-------|
| GRCh38 | hg38, hs38 | Human | Current standard |
| GRCh37 | hg19, hs37 | Human | Legacy, still common |
| CHM13 | T2T, T2T-CHM13 | Human | Telomere-to-telomere, complete |
| hg18 | NCBI36 | Human | Very old, rare |
| GRCm39 | mm39 | Mouse | Current standard |
| GRCm38 | mm10 | Mouse | Previous standard |
