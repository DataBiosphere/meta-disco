# Classification Hierarchy

How meta-disco classifies files, organized by file format. Each section shows
what values we can currently detect for each classification dimension, and
what signal (rule) provides the evidence.

## Hierarchy

```
file_format (extension)
  └→ data_type (what kind of content)
       └→ data_modality (what biological signal)
            └→ assay_type (specific method)
                 └→ platform (instrument)
                      └→ reference_assembly (aligned to what)
```

---

## Alignments (.bam, .cram)

**data_type**: `alignments`

**data_modality**:
- `genomic` ← filename (WGS, WES, HiFi), header @RG PL (PacBio, ONT), header @PG PN (bwa, minimap2, bowtie2, ccs), file size heuristics
- `transcriptomic.bulk` ← filename (RNA, transcriptome, STAR), header @PG PN (STAR, HISAT2, TopHat, Salmon, Kallisto, IsoSeq)
- `transcriptomic.single_cell` ← filename (scRNA, 10x, chromium)
- `epigenomic.chromatin_accessibility` ← filename (ATAC)
- `epigenomic.histone_modification` ← filename (ChIP)

**assay_type**:
- `WGS` ← filename, file size (>50GB BAM, >20GB CRAM), PacBio HiFi header, CCS program
- `WES` ← filename (exome), file size (5-20GB BAM, 2-8GB CRAM)
- `RNA-seq` ← STAR/HISAT2/TopHat/Salmon/Kallisto in @PG, IsoSeq
- `ATAC-seq` ← filename
- `ChIP-seq` ← filename

**platform**:
- `ILLUMINA` ← header @RG PL:ILLUMINA
- `PACBIO` ← header @RG PL:PACBIO, filename (HiFi, PacBio), @PG PN:ccs/lima/isoseq
- `ONT` ← header @RG PL:ONT/NANOPORE

**reference_assembly**:
- `GRCh38` ← filename (hg38, grch38), header @SQ SN/AS pattern, contig lengths (definitive)
- `GRCh37` ← filename (hg19, grch37, b37), header @SQ SN/AS pattern, contig lengths (definitive)
- `CHM13` ← filename (chm13, t2t, hs1), header @SQ SN/AS pattern, contig lengths (definitive)
- `not_applicable` ← no @SQ lines (unaligned)

**Coverage**: Best covered format. All 5 dimensions determinable from headers.

---

## Variants (.vcf, .vcf.gz, .g.vcf.gz, .gvcf.gz, .bcf)

**data_type**: `variants`, `variants.germline`, `variants.somatic`, `variants.structural`, `variants.cnv`

**data_modality**:
- `genomic` ← extension default + caller-specific rules

**assay_type**: _(not determined — VCF doesn't encode assay)_

**platform**: _(not determined — VCF doesn't encode platform)_

**reference_assembly**:
- `GRCh38/GRCh37/CHM13` ← ##reference line, ##contig assembly= tag, contig lengths (definitive), filename

**Coverage**: Good for reference and variant subtype. No modality diversity (always genomic). No platform/assay info.

---

## Reads (.fastq, .fastq.gz, .fq, .fq.gz)

**data_type**: `reads`

**data_modality**:
- `genomic` ← filename (WGS), PacBio/ONT read names (but see issue #37)
- `transcriptomic.bulk` ← filename (RNA, transcriptome)
- `transcriptomic.single_cell` ← filename (scRNA, 10x)
- `epigenomic.chromatin_accessibility` ← filename (ATAC)
- `not_classified` ← **default when no signal** (issue #35, merged)

**assay_type**:
- `WGS` ← filename, PacBio CCS read names
- `ATAC-seq` ← filename

**platform**:
- `ILLUMINA` ← read name pattern (@instrument:run:flowcell:lane:tile:x:y)
- `PACBIO` ← read name pattern (@movie/zmw/ccs or /start_end)
- `ONT` ← read name UUID pattern
- `MGI` ← read name pattern
- `ELEMENT`, `ULTIMA` ← read name patterns

**reference_assembly**: `not_applicable` (raw reads, not aligned)

**Coverage**: Platform detection is strong. Modality is a known gap — FASTQ format has no assay metadata. Illumina FASTQs without filename keywords get `not_classified` for modality. PacBio/ONT FASTQs get `genomic` from platform rules (but see issue #37).

---

## Sequences (.fasta, .fasta.gz, .fa, .fa.gz)

**data_type**: `sequence`, `assembly`, `reference_genome`

**data_modality**:
- `genomic` ← filename (assembly keywords, haplotype keywords), contig names (assembler patterns)
- `transcriptomic.bulk` ← contig names (ENST*, NM_*, NR_*)

**assay_type**: `not_applicable`

**platform**: `not_applicable`

**reference_assembly**:
- `GRCh38/GRCh37/CHM13` ← contig names matching reference chromosomes (20+), filename
- `not_applicable` ← assembler contigs (de novo assembly)

**Coverage**: Good for assembly vs reference detection. Limited by 256KB range request — large uncompressed FASTAs only yield 1 contig.

---

## Intervals/Peaks (.bed, .bed.gz, .narrowPeak, .broadPeak)

**data_type**: `annotations`, `peaks`

**data_modality**:
- `genomic` ← regions.bed pattern, fallback default
- `transcriptomic.bulk` ← filename (expression, TPM, leafcutter, TSS)
- `epigenomic.methylation` ← filename (CpG, methylation, bisulfite, modbam2bed)
- `epigenomic.chromatin_accessibility` ← filename (ATAC), peak patterns
- `epigenomic.histone_modification` ← filename (ChIP, histone, H3K)
- `not_applicable` ← assembly QC patterns (haplotype, flagger, switch errors)

**assay_type**:
- `ATAC-seq` ← filename
- `ChIP-seq` ← filename (ChIP, histone)
- `Bisulfite-seq` ← filename (methylation, bisulfite)
- `RNA-seq` ← filename (expression)

**reference_assembly**: `GRCh38/GRCh37/CHM13` ← filename, BED coordinate detection

**Coverage**: Good modality coverage from filename patterns. Reference from coordinates is strong.

---

## Signal Tracks (.bigwig, .bw, .bedGraph)

**data_type**: `signal`

**data_modality**:
- `epigenomic.histone_modification` ← filename (ChIP, histone, H3K)
- `epigenomic.chromatin_accessibility` ← filename (ATAC)
- `transcriptomic.bulk` ← filename (RNA, coverage)

**Coverage**: Filename-dependent only. No header inspection available.

---

## Single-cell Matrices (.h5ad, .loom, .mtx)

**data_type**: `expression_matrix`

**data_modality**:
- `transcriptomic.single_cell` ← extension default
- `epigenomic.chromatin_accessibility` ← filename (ATAC, peaks)

**Coverage**: Good defaults from extension. ATAC variant detected from filename.

---

## Nanopore Raw Signal (.fast5, .pod5)

**data_type**: `raw_signal`

**data_modality**:
- `genomic` ← extension default (but see issue #37)
- `transcriptomic.bulk` ← filename (RNA, direct RNA)

**platform**: `ONT` (always)

**reference_assembly**: `not_applicable` (raw signal, pre-basecalling)

---

## Other Formats

| Format | data_type | data_modality | Notes |
|--------|-----------|---------------|-------|
| .pgen/.pvar/.psam | genotypes | genomic | PLINK files |
| .idat | array_signal | epigenomic.methylation | Illumina methylation arrays |
| .svs | images | imaging.histology | Whole-slide histology |
| .png/.jpg/.tiff | images | not_applicable | Derived plots/QC |
| .bai/.crai/.tbi/.csi/.pbi | _(skip)_ | _(inherited from parent)_ | Index files |
| .md5 | _(skip)_ | — | Checksums |
| .log | _(skip)_ | — | Log files |

---

## Known Gaps

| Gap | Impact | Issue |
|-----|--------|-------|
| FASTQ modality defaults to not_classified | ~21K Illumina FASTQ files with unknown modality | #35 (merged) |
| PacBio/ONT assume genomic modality | Incorrect for IsoSeq/direct RNA | #37 |
| Mouse genome (GRCm39) not supported | 220 IGVF files unclassified | #15 |
| No dataset-level context for FASTQ | snRNA-seq indistinguishable from WGS | #34 |
| FASTA range request gets 1 contig for large files | Some references classified as sequence | — |
| Matched header content not in evidence | Can't see what triggered a rule | #30 |
