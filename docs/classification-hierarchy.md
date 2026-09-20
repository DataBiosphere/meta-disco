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
- `genomic` ← filename (HiFi), header @RG PL (PacBio, ONT), header @PG PN (bwa, minimap2, bowtie2, ccs), file size heuristics
- `transcriptomic.bulk` ← filename (IsoSeq, STAR), header @PG PN (STAR, HISAT2, TopHat, Salmon, Kallisto, IsoSeq)

**assay_type**:
- `WGS` ← filename (HiFi), file size (Illumina BAM >20GB, CRAM >8GB), PacBio HiFi header, CCS program
- `WES` ← file size (Illumina BAM <20GB, CRAM <8GB)
- `RNA-seq` ← STAR/HISAT2/TopHat/Salmon/Kallisto in @PG, IsoSeq

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
- `genomic` ← PacBio/ONT read names (but see issue #37)
- `transcriptomic.single_cell` ← filename (scRNA, single-cell, 10x — as a delimited token, #430)
- `not_classified` ← **default when no signal** (issue #35, merged)

**assay_type**:
- `WGS` ← PacBio CCS read names

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

**data_type**: `sequence`, `assembly`, `assembly.reference`

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

## Pangenome Graphs (.gfa, .gfa.gz, .rgfa, .rgfa.gz, .gbz, .vg, .gbwt, .xg)

**data_type**: `pangenome`, `pangenome.reference`

`data_type` describes structure: linear sequence (FASTA — `sequence`, refining to `assembly`/`assembly.reference`) versus a sequence graph (nodes/edges/haplotype paths), which is `pangenome`. The reference-graph case — a graph used as the alignment coordinate system — refines to `pangenome.reference`, detected two ways:

- **From file content (preferred)** — an rGFA whose segments carry stable rank 0 (`SR:i:0`) plus a stable name (`SN:Z:`) defines a reference backbone. `fetch_gfa_segment_tags` reads the S-line tags from the head of the file and `classify_from_gfa_segment_tags` emits `rgfa_stable_rank_reference`. When those tags are in the head the signal is exact; if they are not, no content claim is made and detection falls back to the filename. This catches the HPRC `minigraph` graphs (#148).
- **From filename** — HPRC minigraph-cactus graphs match the `-mc-` token (tier-2 `pangenome_reference_mc`). Their GFA segments carry no tags, and the PanSN `P`/`W` path lines that identify them sit after every segment line — ~11 GB into the file — so content inspection is not economical.

PGGB and single-sample assembly graphs stay `pangenome`.

**data_modality**: `genomic` ← extension (all graph formats)

**assay_type**: `not_applicable`

**platform**: `not_applicable` (a graph is an assembled product, not raw reads)

**reference_assembly**: `GRCh38/GRCh37/CHM13` ← filename (shared `filename_ref_*` rules; e.g. an `mc-grch38` graph's coordinate system). Not derived from graph content: no sequence lengths are parsed, so contig-length detection cannot run, and the stable names in the fetched head (`chr1`) are shared between GRCh38 and CHM13.

**Coverage**: Extension-driven, so all listed formats classify. Content inspection covers the text GFA formats (`.gfa`, `.gfa.gz`, `.rgfa`, `.rgfa.gz`); the binary vg/GBWT formats (`.gbz`, `.vg`, `.gbwt`, `.xg`) classify from extension and filename alone. Auxiliary vg indices (`.min`, `.dist`, `.snarls`, `.gg`) are out of scope (issue #144). Single- vs multi-sample graph distinction is deferred (issue #147).

---

## Intervals/Peaks (.bed, .bed.gz, .narrowPeak, .broadPeak)

**data_type**: `annotations` (`.bed`), `peaks` (`.narrowPeak`, `.broadPeak`)

`peaks` comes from the extension, via `intervals_called_peaks`: a `.narrowPeak` or
`.broadPeak` file says what it holds. `intervals_called_peaks_compound` covers the
spelling where that name sits mid-filename and the parsed extension is `.bed`
(`sample.narrowPeak.bed`), which the extension-keyed rule cannot see — the one place a
filename token is still read for peaks, and it is a ten-character one on a delimiter.
Either way `data_modality` is deliberately left unset: the format serves ATAC
(accessibility) and ChIP (histone/TF) alike, so the extension cannot tell them apart.

Four rules used to claim `peaks` from a filename instead — `bed_peaks_generic`,
`bed_atac_peaks`, `bed_chip_peaks` and `intervals_chip_peaks` — and all four fired on no
file in either corpus, so #430 deleted them. Two matched a bare `peak`/`atac` token; the
other two were delimiter-carrying (`\.chip\.|chip[-_]?seq|…`) and went for being dead,
not for being unanchored.

**data_modality**:
- `genomic` ← regions.bed pattern, fallback default
- `transcriptomic.bulk` ← filename (expression, TPM, leafcutter, TSS)
- `epigenomic.methylation` ← filename (CpG as a delimited token, methylation, bisulfite, modbam2bed)
- `not_applicable` ← assembly QC patterns (haplotype, flagger, switch errors)

**assay_type**:
- `Bisulfite-seq` ← filename (methylation, bisulfite)
- `RNA-seq` ← filename (expression)

**reference_assembly**: `GRCh38/GRCh37/CHM13` ← filename, BED coordinate detection

**Coverage**: Good modality coverage from filename patterns. Reference from coordinates is strong.

---

## Signal Tracks (.bigwig, .bw, .bedGraph)

**data_type**: `signal`

**data_modality**:
- `transcriptomic.bulk` ← filename (RNA, transcriptome, coverage)

**Coverage**: Filename-dependent only. No header inspection available. The surviving
RNA pattern is unanchored and matches inside a gene symbol; #471 owns that.

---

## Single-cell Matrices (.h5ad, .loom, .mtx)

**data_type**: `expression_matrix`

**data_modality**:
- `transcriptomic.single_cell` ← extension default

**Coverage**: Good defaults from extension.

---

## Nanopore Raw Signal (.fast5, .pod5)

**data_type**: `raw_signal`

**data_modality**:
- `genomic` ← extension default (but see issue #37)

**platform**: `ONT` (always)

**reference_assembly**: `not_applicable` (raw signal, pre-basecalling)

---

## Other Formats

| Format | data_type | data_modality | Notes |
|--------|-----------|---------------|-------|
| .pgen/.pvar/.psam | genotypes | genomic | PLINK files |
| .idat | array_signal | epigenomic.methylation | Illumina methylation arrays |
| .svs | images | imaging.histology | Whole-slide histology |
| .png/.jpg/.jpeg/.tiff/.tif | images | not_applicable | Derived plots/QC |
| .bai/.crai/.tbi/.csi/.pbi/.fai/.idx | index | _(inherited from parent)_ | Index files — `data_type` is the file's own kind, the rest describe the data it points into (#437) |
| .md5 | checksum | not_applicable | Checksums |
| .log | log | not_applicable | Log files |

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
