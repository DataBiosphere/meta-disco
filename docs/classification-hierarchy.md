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

**data_type**:
- `alignments` ← header has `@SQ` lines (`aligned_has_sq`)
- `reads` ← header has no `@SQ` line (`unaligned_no_sq`). Neither the name nor an `@PG` aligner decides it (#537)

**data_modality**:
- `genomic` ← header @RG DS basecall model (`dna_`), header @PG PN (bwa, minimap2)
- `transcriptomic.bulk` ← filename (`.flnc.` IsoSeq reads, STAR output), header @PG PN (STAR)

**assay_type**:
- `RNA-seq` ← STAR in @PG (`program_star` declares it). No rule infers it from the modality: that read another rule's answer, and was removed (#88)
- `WGS` is no longer inferred: `hifi` names a chemistry, which says neither assay nor modality, and a long-read platform is not an assay (#430)

**platform**:
- `ILLUMINA` ← header @RG PL:ILLUMINA
- `PACBIO` ← header @RG PL:PACBIO, filename (HiFi), @PG PN:ccs
- `ONT` ← header @RG PL:ONT

**reference_assembly**:
- `GRCh38` ← filename (hg38, grch38), contig lengths (definitive)
- `GRCh37` ← filename (hg19, grch37, b37), contig lengths (definitive)
- `CHM13` ← filename (chm13, t2t, hs1), contig lengths (definitive)
- `not_applicable` ← no @SQ lines (unaligned)

**Coverage**: Best covered format. Four dimensions are determinable from headers; `assay_type` only where the aligner is STAR or the modality is transcriptomic. The `@SQ` name-pattern reference rules, the file-size assay rules and the long-read WGS inference were removed in #430 — the first fired on nothing, the others on nothing that meant anything.

---

## Variants (.vcf, .vcf.gz, .g.vcf.gz, .gvcf.gz, .bcf)

**data_type**: `variants`, `variants.germline`, `variants.structural`

`variants.somatic` and `variants.cnv` are in the vocabulary but no rule emits them: every somatic and CNV caller rule fired on nothing across 204,149 VCFs and was removed (#430). Caller detection survives for GATK HaplotypeCaller, sniffles and svim, which is what the catalogs actually hold.

**data_modality**:
- `genomic` ← extension default; the three surviving caller rules assert it too

**assay_type**: _(not determined — VCF doesn't encode assay)_

**platform**: _(not determined — VCF doesn't encode platform)_

**reference_assembly**:
- `GRCh38/CHM13` ← ##reference line, ##contig assembly= tag, contig lengths (definitive), filename
- `GRCh37` ← contig lengths (definitive), filename — its header-pattern rules fired on nothing and were removed (#430)

**Coverage**: Good for reference; variant subtype only where the caller is one of the three seen. No modality diversity (always genomic). No platform/assay info.

---

## Reads (.fastq, .fastq.gz, .fq, .fq.gz)

**data_type**: `reads`

**data_modality**:
- `not_classified` ← always: a read name says the platform, not what was sequenced (issue #35; the PacBio/ONT rules set `platform` only)

**assay_type**: _(not determined — a read name does not say what was sequenced)_

**platform**:
- `ILLUMINA` ← read name pattern (@instrument:run:flowcell:lane:tile:x:y)
- `PACBIO` ← read name pattern (@movie/zmw/ccs or /start_end)
- `ONT` ← read name UUID pattern

**reference_assembly**: `not_applicable` (raw reads, not aligned)

**Coverage**: Platform detection is strong. Modality is a known gap — FASTQ format has no assay metadata, so every FASTQ is `not_classified` for modality (the PacBio/ONT rules set `platform` only; #430).

---

## Sequences (.fasta, .fasta.gz, .fa, .fa.gz, .fna, .fna.gz)

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

**Coverage**: Extension-driven, so all listed formats classify. Content inspection covers the text GFA formats (`.gfa`, `.gfa.gz`, `.rgfa`, `.rgfa.gz`); the binary vg/GBWT formats (`.gbz`, `.vg`, `.gbwt`, `.xg`) classify from extension and filename alone. Auxiliary vg indices (`.snarls`, `.dist`, `.min`, `.gg`, `.hapl`, `.trans`) are recognized and claim only a `reference_assembly` from the filename (#526); the pangenome rules give them no `data_type` (issue #144 left them out). Single- vs multi-sample graph distinction is deferred (issue #147).

---

## Intervals/Peaks (.bed, .bed.gz, .narrowPeak, .broadPeak)

**data_type**: `annotations`

`.narrowPeak` and `.broadPeak` resolve to the `intervals` category by extension but
no rule claims them: neither catalog holds one, and the rule set is the minimum the
data can verify (#430). They report nothing. If one arrives, a rule keyed on the
extension can claim `data_type: peaks` — the format is used for ATAC and ChIP alike,
so the extension cannot say which, and `data_modality` would stay unset.

A `.bed` with no signal of its own reports nothing. The rule that called such a file
`genomic` annotations by default, `intervals_fallback`, was deleted with every other
fallback (#88): a rule has an opinion or none, never fills a field only because other
rules left it empty, and a disagreement is settled by tier or by a curator.

Four rules used to claim `peaks` from a filename instead — `bed_peaks_generic`,
`bed_atac_peaks`, `bed_chip_peaks` and `intervals_chip_peaks` — and all four fired on no
file in either corpus, so #430 deleted them. Two matched a bare `peak`/`atac` token; the
other two were delimiter-carrying (`\.chip\.|chip[-_]?seq|…`) and went for being dead,
not for being unanchored.

**data_modality**:
- `genomic` ← assembly QC patterns (haplotype, flagger, switch errors)
- `transcriptomic.bulk` ← filename (`TMM` or `counts` as a delimited token, leafcutter, `.TSS.`)
- `epigenomic.methylation` ← filename (modbam2bed, or CpG as a delimited token)
- open ← mosdepth `.regions.bed.gz` (`annotations.coverage`): the alignment's modality, which the name does not show (#541)

**assay_type**:
- _(none)_ — `bed_methylation` used to assert `Bisulfite-seq` for every file it matched, including modbam2bed output, which is nanopore modified-base calling and not bisulfite. No file in either catalog supports a CpG name meaning bisulfite either, so the assay is left open (#430). `Bisulfite-seq` stays in the vocabulary for a rule that can claim it on evidence.
- `RNA-seq` ← filename (expression)

**reference_assembly**: `GRCh38/GRCh37/CHM13` ← filename, BED coordinate detection

**Coverage**: Good modality coverage from filename patterns. Reference from coordinates is strong.

---

## Signal Tracks (.bigwig, .bw, .bedGraph)

**data_type**: `annotations.coverage` ← `Signal.Unique[Multiple].strand±.bw`, STAR's signal output converted to bigWig (#543)

**data_modality**: `transcriptomic.bulk`, and **assay_type** `RNA-seq`, from the same
name: STAR is an RNA-seq aligner, as `star_filename` has it for STAR's BAMs.

**Coverage**: Filename-dependent only. No header inspection available. Any other bigWig
or bedGraph (the HPRC `*.5mC.bigwig` methylation tracks among them) has no `data_type`,
`data_modality` or `assay_type`; only a reference named in the filename is still claimed.
A bare `rna` in a name no longer says transcriptomic.

---

## Single-cell Matrices (.h5ad, .loom, .mtx)

**data_type**: `expression_matrix`

**data_modality**:
- `transcriptomic.single_cell` ← extension default

**Coverage**: Good defaults from extension.

---

## Nanopore Raw Signal (.fast5, .pod5)

**data_type**: `raw_signal`

**data_modality**: _(not classified — the container says the platform, not what was sequenced; issue #37)_

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
| .bai/.crai/.tbi/.csi/.pbi/.fai/.gzi/.idx | index | _(inherited from parent)_ | Index files — `data_type` is the file's own kind, the rest describe the data it points into (#437) |
| .md5 | checksum | not_applicable | Checksums |
| .log | log | not_applicable | Log files |

---

## Known Gaps

| Gap | Impact | Issue |
|-----|--------|-------|
| FASTQ modality defaults to not_classified | ~21K Illumina FASTQ files with unknown modality | #35 (merged) |
| PacBio/ONT no longer assume a genomic modality (#430); nothing supplies one for raw reads or signal | Iso-Seq/direct RNA are not miscalled, but genomes are not called either | #37 |
| Mouse genome (GRCm39) not supported | 220 IGVF files unclassified | #15 |
| No dataset-level context for FASTQ | snRNA-seq indistinguishable from WGS | #34 |
| FASTA range request gets 1 contig for large files | Some references classified as sequence | — |
| Matched header content not in evidence | Can't see what triggered a rule | #30 |
