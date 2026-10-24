# AnVIL data issues to report

Last updated 2026-10-24.

These are defects in AnVIL's open-access catalog that meta-disco found and cannot fix on its side. They go to the AnVIL data team at anvil-data@broadinstitute.org. Nothing here has been sent yet.

This file is the list. Add an issue here by pull request, once it is checked against the rows it is about (the manifest, the submitter table, the file's own header) and against AnVIL's design, which can explain what looks like a defect; a finding that turns out not to be one goes under [Checked, not reported](#checked-not-reported).

Each issue names the dataset, what AnVIL holds, what the files themselves or the submitter tables say, how many files it touches, and the change that would fix it. Counts come from meta-disco's reconcile on catalog `anvil15`, run `20261024_005617` (708,088 files), unless an issue says otherwise.

| # | Dataset | Issue | Files |
| --- | --- | --- | --: |
| 1 | `ANVIL_HPRC` | Parents' reads generated from the child's biosample | 1,314 |
| 2 | `ANVIL_HPRC`, `AnVIL_HPRC_R2` | Two HG03704 HiFi BAMs whose read groups name HG02451 | 2 in each |
| 3 | `ANVIL_T2T` | Workspace cells point to files not in the bucket | 150,490 unlinked |
| 4 | `ANVIL_T2T_CHRY` | GATK sample maps missing for the workspace tars | 93,180 |
| 5 | `ANVIL_1000G_high_coverage_2019` | 698 instrument models that do not exist | 1,396 |
| 6 | `AnVIL_IGVF_Mouse_R1` | Published data modality holds assay names | 6,755 |
| 7 | `ANVIL_T2T` | Liftover VCF indexes whose VCFs are missing | 48 |
| 8 | `ANVIL_T2T_CHRY` | Two SGDP samples whose rows disagree with their genomes | 2 samples |
| 9 | `AnVIL_HPRC_R2`, ENCORE | Swapped columns; a misspelled activity type | 230 + 634 rows |
| 10 | `ANVIL_HPRC` | One HG005 assembly BAM listed under HG00621 too | 1 |

## 1. ANVIL\_HPRC: parents' reads generated from the child's biosample

AnVIL's `anvil_activity` says 1,314 files of a child's parents were made from the child's biosample. The files, and HPRC's own submitter table, say they are the parents'.

**What the submitter table says.** HPRC's `sample` table has one row per assembled child. The row lists the reads used to build the assembly, the parents' included: `child_ilmn`, `mat_ilmn` (the mother's Illumina reads) and `pat_ilmn` (the father's), with `maternal_id` and `paternal_id`. The parents have no `sample` or `participant` row of their own.

**What AnVIL made of it.** One `anvil_activity` per child row, whose `used_biosample_id` is the child's biosample and whose `generated_file_id` lists every file in the row, the parents' reads included.

**Example.** The row for `HG01106` lists `HG01105.final.cram` as `mat_ilmn`, with `maternal_id` `HG01105`.

| Source | Names the file's sample as |
| --- | --- |
| The CRAM's read group (`@RG SM`) | `HG01105` |
| `sample.mat_ilmn` → `maternal_id` | `HG01105` |
| `anvil_activity` `2a80a7ab-5f73-f475-e77b-5ffc98508fab` → `used_biosample_id` | `HG01106` (the child) |

**Scale.** 1,314 files, from 50 child rows and 100 parent pairings. HG005's row alone carries 1,212: 612 `NA24695_*` FASTQs of HG007 (the mother) and 600 `NA24694_*` of HG006 (the father). Four `.md5` checksums of those files are affected too. Each file is listed with every source in `docs/sample-conflicts.tsv`, one line per file, source and attribution; the TSV also holds issue 2's two AnVIL_HPRC_R2 files and issue 10's file.

**Effect.** Anyone joining files to biosamples through AnVIL's activities finds the parents' reads under the child. In meta-disco these files are now conflicts and name no sample, so 1,318 ANVIL\_HPRC files lose their donor.

**Suggested fix.** In AnVIL's HPRC transform, make a biosample for each parent named by `maternal_id` / `paternal_id`. Link the `mat_ilmn` and `pat_ilmn` files to the parent's biosample, not the child's.

## 2. ANVIL\_HPRC and AnVIL\_HPRC\_R2: two HG03704 HiFi BAMs whose read groups name HG02451

Two PacBio HiFi BAMs in HG03704's folder say `SM:HG02451` in their read groups. Everything else says HG03704. This may be a header label error or a sample swap; only a genotype check can tell. It is the submitter's data, so it is one to pass on to HPRC.

| File (in both datasets, same md5) | Read group `SM` | Folder | AnVIL_HPRC_R2's `hifi.sample_id` and activity |
| --- | --- | --- | --- |
| `m54329U_211105_213234-bc1001.5mc.hifi_reads.bam` (`ce90c1ae…`) | `HG02451` | `working/HPRC/HG03704/raw_data/PacBio_HiFi/` | `HG03704` |
| `m54329U_211111_222027-bc1001.5mc.hifi_reads.bam` (`930b6f2a…`) | `HG02451` | the same | `HG03704` |

HG03704's 2022 run in the same folder, `m54329U_220207_224702-bc1001.5mc.hifi_reads.bam`, says `SM:HG03704`. The FASTQs made from the two 2021 runs are named for HG03704 (`HG03704.m54329U_211105_213234.dc.q20.fastq.gz`). HG02451's own HiFi runs are on another instrument, `m64076`. In ANVIL\_HPRC no table or activity names these two files' sample, so meta-disco takes the read group's HG02451 there; in AnVIL\_HPRC\_R2 the read group and the rows disagree, and the files have no sample.

**Ask.** Confirm whose reads these are. If they are HG03704's, correct the read groups. If they are HG02451's, move them and fix R2's `hifi` rows.

## 3. ANVIL\_T2T: workspace table cells point to files not in the bucket

In snapshot `ANVIL_T2T_20230714_ANV6_202607080209`, no `participant` row links to its 150,490 HaplotypeCaller gVCFs and indexes. The files are in the snapshot, but the workspace paths that should link them are stale, so TDR left those cells null. Checked with `gsutil ls` and in BigQuery on 2026-10-03, in meta-disco's epic [#608](https://github.com/DataBiosphere/meta-disco/issues/608).

| Workspace column | Points to | Where the files are | Cells |
| --- | --- | --- | --: |
| `participant.chrN_hc_bgzip`, `chrN_hc_tabix` (24 chromosomes) | `1KGP/haplotype_caller/compressed/…` | `1KGP/haplotype_caller/` (one level up) | 75,245 each |
| `participant.chrN_hc_vcf` | `1KGP/haplotype_caller/uncompressed/…hc.vcf` | nowhere | 75,245 |
| `interval.genotyped_vcf`, five uncompressed `chromosome.*_VCF` | uncompressed `.vcf` files | nowhere; the `_gz` / `genotyped_bgzip` columns are fine | 31,155 + |

The workspace bucket is `gs://fc-47de7dae-e8e6-429c-b760-b4ba49136eee`. For example, `HG00096.chr10.hc.vcf.gz` sits at the flat path, created 2024-02-17.

**Suggested fix.** Repoint `chrN_hc_bgzip` / `chrN_hc_tabix` to the flat `1KGP/haplotype_caller/` paths. Clear the columns that name uncompressed `.vcf` files. Take a new snapshot.

**Also in ANVIL\_T2T, for the workspace description (`anvil-datastorage/AnVIL_T2T`):**

- The tools' own records name stale paths. The GenomicsDB tars record `--sample-name-map gs://…/sample_maps/chrN_sample_map.tsv`, but the 24 maps are at `1KGP/sample_maps/`. The chr1 map lists its 3,202 gVCFs at `hc_vcfs/compressed/chr1/`, but they are at `1KGP/haplotype_caller/`. File names still match, so nothing is lost.
- An undescribed `1KGP/v2/` set holds a second CRAM, of the same name, for 35 samples: a re-alignment to CHM13 with HG002's chrY (`t2t-chm13.20200921.HG002chrY.chrEBV.fasta`). With its statistics that is 280 files, all in the snapshot, none linked from a table row. A line saying what `v2/` is would let users tell the two apart, and a `cram_v2` column would link them.

## 4. ANVIL\_T2T\_CHRY: GATK sample maps missing for 93,180 GenomicsDB workspace tars

Each of ANVIL\_T2T\_CHRY's 93,180 GenomicsDB workspace tars was built from a GATK sample-name map that is not in the dataset. Each tar's `vcfheader.vcf` names its map, in one of two workspace buckets that no longer exist (`NoSuchBucket`). Checked 2026-10-04; tracked in [meta-disco #624](https://github.com/DataBiosphere/meta-disco/issues/624).

| Map directory named by the tars | Tars | Cohort | Public copy |
| --- | --: | --- | --- |
| `gs://fc-c58482ad-a2f7-4d08-b7fa-553b70fd6c6a/sample_maps/full_sample/` | 31,158 | 1000 Genomes | 25 maps on the Schatz lab's [GitHub](https://github.com/schatzlab/t2t-chm13-chry/tree/efad0878/alignment_variant_calling_pipeline/example_sample_maps), matching the dataset's 76,844 gVCFs |
| `gs://fc-1b543b1d-8887-4a24-a4fd-37f06e9d9d70/uploads/sample_maps/` | 62,022 | SGDP (31,158 CHM13v2 + 30,864 GRCh38 runs) | none found |

Nothing in the snapshot mentions `sample_map`. The two directories reuse 26 file names (`chr19_sample_map.tsv`), and the two SGDP runs name the same map paths.

**Ask.** Add the maps to the snapshot, either under distinct names or with a table linking each tar (or each chromosome and run) to its map. For 1000 Genomes the GitHub copies would do, if they are the maps used, with one gap: the tars name separate `chrX_PAR1` and `chrX_PAR2` maps, and the lab published one `chrX_PAR` map. For SGDP we need the maps each run used.

**Effect until then.** meta-disco reads the GitHub maps as a workaround for the 1000 Genomes tars ([meta-disco #710](https://github.com/DataBiosphere/meta-disco/issues/710)). It rebuilds each SGDP tar's map from the tar's own `callset.json` ([meta-disco #726](https://github.com/DataBiosphere/meta-disco/issues/726)).

## 5. ANVIL\_1000G\_high\_coverage\_2019: 698 instrument models that do not exist

The submitter's `participant.instrument_model` holds every value from `Illumina NovaSeq 6001` to `Illumina NovaSeq 6698`, one row each, beside 2,504 rows of `Illumina NovaSeq 6000`. It looks like a spreadsheet fill series dragged down the column. No such Illumina models exist.

- **Example:** `NA12802`'s row says `Illumina NovaSeq 6573`.
- **Scale:** 698 rows, 1,396 files (each row's `gvcf` and `gvcf_tbi`).
- **Effect:** meta-disco takes the platform (Illumina) from these rows but not the instrument model.
- **Suggested fix:** set the 698 cells to `Illumina NovaSeq 6000`, if that is what the runs used.

## 6. AnVIL\_IGVF\_Mouse\_R1: the published data modality holds assay names

AnVIL's own `anvil_file.data_modality` carries IGVF's assay titles, not data modalities, on 6,755 of the dataset's 6,786 files.

| `anvil_file.data_modality` | Files |
| --- | --: |
| `single-nucleus RNA sequencing assay` | 6,733 |
| `single-nucleus ATAC-seq`, `single-nucleus RNA sequencing assay` | 12 |
| `single-nucleus ATAC-seq` | 10 |
| empty | 31 |

**Effect.** A reader of the column gets an assay where it expects a modality. meta-disco translates each title to an assay and, for the two single assays, a modality (transcriptomic; epigenomic chromatin accessibility). It declares no modality for the SHARE-seq pair, whose files hold one half each.

**Suggested fix.** In AnVIL's IGVF transform, map the assay titles to FSS modalities, and keep the titles in `assay_type`.

## 7. ANVIL\_T2T: 48 liftover VCF indexes whose VCFs are not in the dataset

48 `.csi` indexes under `joint_vcfs/recalibrated/singleton/novel_regions/liftover/non_syntenic/` have no `.vcf.gz` beside them, or anywhere in the dataset.

- **Example:** `1kgp.chr19.recalibrated.snp_indel.pass.singleton.chm13.draft_v1.0_plus38Y.no_snyteny_1Mbp.Homo_sapiens_assembly38.rejected.vcf.gz.csi` is present; its VCF is not.
- **Scale:** 48 indexes, `*.liftover.vcf.gz.csi` and `*.rejected.vcf.gz.csi` across chromosomes.
- **Ask:** add the 48 VCFs, or drop the indexes if the VCFs were left out on purpose.

## 8. ANVIL\_T2T\_CHRY: two SGDP samples whose table rows disagree with their genomes

Two of the 279 SGDP samples in the `SGDP_*_sample` tables don't match what their genomes show. Measured by genotype checks against SGDP's and HGDP's public releases ([meta-disco #718](https://github.com/DataBiosphere/meta-disco/issues/718), `docs/studies/sgdp-genome-identity.md`).

| Sample | Table says | What we found |
| --- | --- | --- |
| `simons_data_sample_187` | `sgdp_id` `S_Palestinian-2`, karyotype `XX` | The `sgdp_id` is right: its genotypes match HGDP00725, which is S_Palestinian-2's genome, recorded as male by SGDP and HGDP. Its own chrX gVCF shows one X: 155 heterozygous against 921 homozygous-alternate calls on chrX 40–42 Mb, where a female control has 1,394 against 420. So `XX` looks wrong. It may be a male cell line that lost its Y; that is not checked. |
| `simons_data_sample_273` | `sgdp_id` `S_Naxi-2` | SGDP's metadata has `S_Naxi-1` and `S_Naxi-3` but no `S_Naxi-2`, and neither release holds it. The sample matches no public genome; its nearest, `S_Naxi-3`, differs at 2.6% of sites. |

**Effect.** `simons_data_sample_273` reaches no donor, so its 118 single-sample files, and every joint-called file naming it, have a sample with no donor.

**Ask.** Confirm sample 187's karyotype (its `sgdp_id` stands), and which SGDP genome sample 273 is.

## 9. Smaller fixes in submitter tables

Neither changes what meta-disco settles today; both are worth a line in the same message. meta-disco's activity map matches `Quantificatioin: salmon` as written (`rules/activity_map.yaml`), so a corrected spelling needs a matching row there, or those ENCORE steps go untranslated.

| Dataset | Table and column | What it holds | Rows |
| --- | --- | --- | --: |
| `AnVIL_HPRC_R2` | `kinnex.data_type`, `kinnex.filetype` | `data_type: bam` and `filetype: unaligned reads`: the two columns look swapped | 230 |
| `AnVIL_ENCORE_293T`, `AnVIL_ENCORE_RS293` | `activity.activity_type` | `Quantificatioin: salmon`, misspelled; AnVIL's `anvil_activity` copies it | 224 + 410 |

## 10. ANVIL\_HPRC: one HG005 assembly BAM listed under HG00621 too

HPRC's `assembly_sample` table lists `HG005.paternal.GRCh38_no_alt.bam` as `pat_grch38_aln_bam` in two rows: HG005's and HG00621's. The file sits in HG005's folder (`working/HPRC_PLUS/HG005/assemblies/year1_f1_assembly_v2_genbank/alignment/assembly-to-reference/`), so HG00621's row looks wrong.

- **Effect:** the two rows name different people, so meta-disco gives the file no sample (listed as `incomparable` in `docs/sample-conflicts.tsv`).
- **Ask:** confirm which assembly the BAM aligns, and point HG00621's `pat_grch38_aln_bam` at HG00621's own file.

## Checked, not reported

These looked like defects and turned out not to be, or were already handled.

- **AnVIL\_HPRC\_R2's reference FASTAs linked to biosamples (8 files).** The `sample_metadata` rows are `GRCh38` (`SAMN12121739`) and `CHM13` (`SAMN03255769`), the two references HPRC includes in its pangenome. The link is right; our identifier rules just don't name them.
- **AnVIL\_HPRC\_R2's `alignments_v2` table holds graphs and VCFs (12 rows).** They are the Minigraph-Cactus pangenome, and Cactus is a whole-genome aligner, so the name fits.
- **ANVIL\_NIA\_CARD\_Coriell\_Cell\_Lines\_Open's steps are in `anvil_sequencingactivity`, not `anvil_activity` (6 rows).** That is AnVIL's typed activity table, by design; meta-disco now reads it ([meta-disco #698](https://github.com/DataBiosphere/meta-disco/issues/698)). Each row links only `hapdup_contigs_1.fasta`, because the submitter's `sequencing.sequencing_id_fileref` names that one file per row.
- **ANVIL\_NIA\_CARD\_Coriell\_Cell\_Lines\_Open's biosamples are typed `Blood` (3 samples), though each is a cell line.** The submitter's `sample.sample_source` is `UBERON:0000178` (blood), the lines' source tissue, and AnVIL maps it as given.
- **`Unknown` biosample types and sites** (IGVF's 135, HPRC\_R2's 230, NIA\_CARD's sites) mean "not known", not a wrong value.
- **ANVIL\_T2T's CHM13 CRAMs say `DS:GRCh38` in their read groups.** bwa's `-R` copied NYGC's read groups in whole; the alignment's reference is in `@SQ`, which meta-disco reads instead.
- **Malformed consent labels and placeholder descriptions on Azul's dataset records** (`phs001642`'s `DS_GI`-style and `DS-GI,18+` variants, a `TBD` label, `[Description currently not available]`; measured 2026-08-17 and 2026-08-18, `docs/studies/findings.md`). Fixed by AnVIL: on 2026-10-24 none of Azul's 464 `anvil15` datasets carries one, and the only label with an underscore is the registered `DS-MULTIPLE_DISEASES-IRB-COL-NPU-RD`.
- **Azul served stale, short compact manifests** for title filters (HPRC\_R2 11,905 of 16,271 rows, IGVF 3,334 of 6,786), 2026-10-21. Handled with the Azul team on Slack.
- **ENCORE's biosamples and IGVF's pooled mouse samples** tie to none of our sample records, or to many donors. Both are gaps on meta-disco's side ([meta-disco #711](https://github.com/DataBiosphere/meta-disco/issues/711)), not AnVIL's.

## Before sending

- [ ] Issue 1: attach `docs/sample-conflicts.tsv`, which `make reconcile-report` regenerates from a reconciled run; it lists each file with every source.
- [ ] Issue 2: decide whether it goes to AnVIL or straight to HPRC.
- [ ] Issue 3: re-check the paths with `gsutil ls` against the current snapshot; they were last checked on 2026-10-03.
- [ ] Issue 4: send [meta-disco #624](https://github.com/DataBiosphere/meta-disco/issues/624)'s drafted email as it stands, or fold it in here.
- [ ] Issues 2 and 8 go to the submitters (HPRC, T2T) as much as to AnVIL; decide the route.

Issues 5, 6, 7, 9 and 10 were checked against the `anvil15` manifests on 2026-10-24; issue 8 rests on the genotype checks of 2026-10-22 ([meta-disco #718](https://github.com/DataBiosphere/meta-disco/issues/718)).
