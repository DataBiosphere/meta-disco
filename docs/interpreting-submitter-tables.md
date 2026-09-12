# Interpreting submitter tables

**Status:** Findings, measured 2026-09-11 against `data/anvil/manifest/anvil15/`
**Scope:** the AnVIL *verbatim* manifests — the submitters' own tables, delivered unaltered

The verbatim manifests look like metadata tables and mostly are not. They are a **graph
serialized to tables**, and reading them as tables of file attributes is why three
separate attempts to mine them for our five dimensions came back nearly empty.

This document records what shape they are actually in, what that is worth, and what it
costs to use — all measured, with the method at the end so it can be re-run.

---

## 1. Three shapes, and two authors

There are 107 submitter tables across 12 datasets. Every one of them is in one of three
shapes, distinguished by how many of its columns hold a file pointer (a `drs://` URI, or
a list of them):

| shape | tables | a row is | the file's description lives in |
|---|---:|---|---|
| **one link column** | 37 | a **file** | the row's other columns |
| **two or more** | 23 | an **entity** — sample, participant, chromosome, release | the **column name** |
| **none** | 47 | something that reaches no file (`pedigree`, `subject`, `workspace_attributes`) | — |

The variety is in the column *names*, not the structure. Every submitter invented their
own vocabulary — `hifi`, `cram`, `chr10_hcvcf_gz`, `mat_grch38_aln_bam` — but only three
ways of connecting a row to a file.

**A link column may hold a list.** `ANVIL_HPRC/sample` is the one table that does:
`hifi`, `hic` and `nanopore` each hold several DRS URIs. A reader that only checks for a
scalar string finds nothing there and silently classifies the table as reaching no files.

**Why a table is in one shape or another: it depends on who wrote the columns.**

- **Workflow-materialized.** A WDL ran over an entity table and Terra wrote each output
  back as a column on that row. That produces one row per entity (the workflow's input
  unit), one column per output, the column named for the output, and **no dimension cells
  at all** — a workflow writes files, not metadata. `ANVIL_T2T/participant` and
  `ANVIL_HPRC/assembly_sample` are this; the 62-column `1KGP_CHM13v2_sample` is a
  chromosome-sharded variant caller rather than a data-modelling decision. §6 verifies it
  against the workflow that produced `ANVIL_T2T`.
- **Model-authored.** Someone designed a schema first and filled it. Entities are
  normalized, relationships are foreign keys, files live in their own tables, and the
  columns carry **metadata values**. `AnVIL_HPRC_R2`'s `hifi` / `ont` / `hic` are this.
  So is a GREGoR-style table like `experiment_nanopore`, whose columns are
  `analyte_id`, `sequencing_platform`, `chemistry_type`, `seq_library_prep_kit_method`,
  `targeted_regions_method` — one file pointer in the whole row, and that one a targeting
  BED rather than an output.

**This is the distinction that predicts where dimension values are.** They are in
model-authored tables and essentially nowhere else, which is why import's measured gain
on `AnVIL_HPRC_R2` (+4,305 `data_modality`, +2,786 `data_type`) comes from `hifi`/`ont`/
`hic`, and why the workflow-materialized `assembly_sample` added nothing at all (§4). A
dataset made entirely of workflow outputs has no dimension metadata to import, however
many columns it has.

## 2. The entity shape is a triple

```
ANVIL_T2T / participant          87 columns, 10 hold a DRS URI
  participant_id = HG03605
  read_1_fastq, read_2_fastq              the raw input
  cram, cram_index                        the alignment OF those reads
  mosdepth_*, samtools_stats              QC OVER that alignment
```

Of the other 77 columns only five are populated, and not one is a dimension value. The
row's entire content is *these files came from this person, in these roles*:

| | | |
|---|---|---|
| **subject** | the row's entity id | `participant_id = HG03605` |
| **predicate** | the column **name** | `cram`, `read_1_fastq` |
| **object** | what the column's value points at | `drs://drs.anv0:v2_a95d2ac5…` |

**Finding the subject.** It is the `<type>_id` column on 16 of the 23 entity tables. The
7 exceptions are all `ANVIL_T2T_CHRY` and are a SQL-identifier artifact: type
`1KGP_CHM13v2_sample` → column `t_1kgp_chm13v2_sample_id`, lowercased with `t_` prefixed
because the name starts with a digit. Derivable, but not blindly — declare it per table
rather than guess.

**Subjects are typed, and often are not samples:**

| table | subject | what it is |
|---|---|---|
| `ANVIL_T2T/participant` | `HG03605`, `SRS006902` | a person (1000G uses SRA accessions) |
| `ANVIL_HPRC/assembly_sample` | `HG00438` | a sample — the column is named for the table, the value is a sample |
| `ANVIL_T2T/chromosome` | `chr16` | a genomic region |
| `ANVIL_T2T/interval` | `chr9.72400001_72500000` | an interval |
| `ANVIL_HPRC/minigraph_cactus` | `hprc-v1.0-mc-chm13-minaf.0` | a pangenome release |
| `ANVIL_1000G_PRIMED/plink_file_wide` | `PJL_hg19_mega_hm3_20` | a population cohort |

**There are entity→entity edges too**, not only entity→file: `sample_id` inside
`assembly` and `hifi`; `maternal_id` / `paternal_id` in `ANVIL_HPRC/sample`, which puts a
pedigree in the same row as the file pointers; `coriell_id` / `kgp_sample_id` in MAGE.

**The predicate is compound.** `mat_grch38_aln_bam` packs role, haplotype, reference and
format into one token. One column name therefore speaks to several slots at once.

## 3. The harmonization is Broad's, at TDR ingest, and it drops the column

`anvil_activity` in `ANVIL_T2T`: **`Indexing` 116,247, `Unknown` 3,207.** That second
number is the participant count (3,202). One of them:

```
activity_type           = Unknown
source_datarepo_row_ids = ['participant:ff52de4e-…']
used_biosample_id       = ['ef5c98bf-…']            1 biosample
generated_file_id       = [10 file ids]
used_file_id            = []
```

The pointer table *was* read. The subject survived as a biosample, the objects survived
as ten file ids, and the ten labelled edges collapsed into one untyped bundle.
`read_1_fastq`, `cram` and `samtools_stats` are indistinguishable here, and the activity
is `Unknown` because the column names were the only statement of what happened.

**So the predicate survives only in the verbatim manifest.** AnVIL's own typed edges are
almost entirely `Indexing` — the one edge we already recover from filename convention at
97%.

**Where it happens, and exactly what is lost.** The transformation is Broad's, at ingest
into TDR, not Azul's at index time. It lives in
[`broadinstitute/anvil_tdr_ingest`](https://github.com/broadinstitute/anvil_tdr_ingest)
as BigQuery SQL run against the submitter's tables. From `anvil_schema/mapping/specifications/hprc_r2_1.json`:

```sql
SELECT 'hifi:'||hifi_id, sample_id, [path], ['hifi:'||datarepo_row_id]
  FROM `$BQ_DATASET.hifi`
UNION ALL
SELECT 'assembly:'||assembly_id, sample_id,
       [assembly, assembly_fai, assembly_gzi, assembly_md5],
       ['assembly:'||datarepo_row_id]
  FROM `$BQ_DATASET.assembly`
```

One `UNION ALL` arm per submitter table, each producing
`(activity_id, used_biosample_id, generated_file_id[], source_datarepo_row_ids)`.

So it is the **column**, not the table, that is discarded. The source table survives
unhashed in `source_datarepo_row_ids` (`'assembly:'||datarepo_row_id`), while four named
columns — `assembly`, `assembly_fai`, `assembly_gzi`, `assembly_md5` — collapse into one
unordered array. Given a harmonized activity you can say which table a file came from;
you cannot say which column, and the column is where the role lives.

**`source_datarepo_row_ids` does not shortcut the join.** It is 100% populated on
`anvil_file` (289,204/289,204 in `ANVIL_T2T`) but only ever names `file_inventory` — a
1:1 restatement, not the entity→file edge. Joining an entity table to our records still
goes through the DRS URI, which works: `drs_uri` is in `JOIN_KEYS`, and in the check
below it matched 656/656 with no misses.

## 4. What it is worth

**Reach: 435,284 of 708,088 files — 61.5% of the corpus — are reachable from an entity
table, and every one carries a subject id.**

| dataset | entity tables | files reached |
|---|---:|---:|
| ANVIL_T2T_CHRY | 7 | 279,087 |
| ANVIL_T2T | 3 | 125,605 |
| ANVIL_1000G_high_coverage_2019 | 2 | 9,603 |
| ANVIL_1000G_PRIMED_data_model | 1 | 8,562 |
| ANVIL_HPRC | 6 | 5,851 |
| AnVIL_HPRC_R2 | 2 | 3,460 |
| AnVIL_MAGE | 2 | 3,116 |

Three different things come out of that, and they are worth very different amounts.

**Subject — the largest gain.** 435,284 files get "which sample or donor is this from",
at 100% of what is reachable. We cannot answer that for any file today.

**Role — real, but on far fewer than 61.5%.** These edges arrive *grounded*: the parent
is a DRS URI that resolves to one of our records, against 59–82% grounding for the
content-derived edges #363 measured. But the value depends on the vocabulary, and it is
uneven. `ANVIL_T2T/participant`'s ten columns are genuinely varied roles.
`ANVIL_T2T_CHRY`'s 62 are mostly `chr1…chr22,X,Y` × `hcvcf_gz`/`hcvcf_index` — **279,087
files, 64% of the reachable set, where the role is uniformly "variants" and the only new
fact is the chromosome**, which has no slot.

**The five dimensions — about zero.** Measured on `ANVIL_HPRC/assembly_sample`, whose
column names claim a reference assembly and a data type:

| slot | files claimed | agree | disagree | inference silent |
|---|---:|---:|---:|---:|
| reference_assembly | 375 | **375** | 0 | 0 |
| data_type | 281 | **281** | 0 | 0 |

100% agreement, **zero coverage added**. Which is the expected result once the shape is
understood: our five dimensions are *file-intrinsic* and we read them from the bytes, so
a table restating them tells us nothing. What is not recoverable from the bytes is the
subject and the predicate — and that is what these tables are made of.

Separately, `AnVIL_HPRC_R2`'s value-bearing tables (`hifi`, `ont`, `hic`, …) do carry
real dimension cells: **26 distinct values** across 8 columns. Those are worth mapping,
and are #414's scope. The distinction that matters is cell values versus column names,
not dataset versus dataset.

## 5. What it costs: 115 predicates

Distinct link-column names across the 23 entity tables: **161 raw, 115 after collapsing
the chromosome axis** (`chr7_hcvcf_gz` and `chr8_hcvcf_gz` are one predicate).

Per dataset, collapsed: `ANVIL_HPRC` 57 · `ANVIL_T2T_CHRY` 37 · `ANVIL_T2T` 17 ·
`AnVIL_HPRC_R2` 6 · `ANVIL_1000G_PRIMED_data_model` 3 ·
`ANVIL_1000G_high_coverage_2019` 3 · `AnVIL_MAGE` 3.

Note the shape of that: **the datasets with the most files have the least vocabulary.**
And the distribution is steeply top-heavy — `chrN_hcvcf_gz` and `chrN_hcvcf_index` alone
reach 165,440 files, 38% of everything reachable:

```
  82,720  chrN_hcvcf_gz            10,164  cram
  82,720  chrN_hcvcf_index          6,962  cram_index
  31,158  t_1kgp_genomics_db_tar    6,962  mosdepth_regions_bed
  31,158  sgdp_genomics_db_tar      6,401  gvcf
  31,155  genomics_db_tar           3,202  samtools_stats
  31,155  genotyped_bgzip           2,854  pgen / psam / pvar
  10,540  read_chrN_fastq             466  assembly / assembly_fai
```

So the mapping work is roughly a hundred rows, and a couple of dozen of them cover most
of the corpus.

## 6. Where a predicate vocabulary comes from: the workflow that wrote it

`ANVIL_T2T` and `ANVIL_T2T_CHRY` are 85% of the corpus and appear in *none* of
`anvil_tdr_ingest`'s mapping specifications. They did not take that route. The schatzlab
group ran WDL workflows on AnVIL and published the results as a Terra workspace
([`anvil-datastorage/AnVIL_T2T_CHRY`](https://anvil.terra.bio/#workspaces/anvil-datastorage/AnVIL_T2T_CHRY),
May 2023), which was snapshotted into TDR afterwards. The workflows are published, in
[`schatzlab/t2t-chm13-chry`](https://github.com/schatzlab/t2t-chm13-chry).

**The column names are the WDL output names, verbatim**, and the pipeline README says
what each one is:

| WDL output (from `t2t_realignment`, `haplotype_calling`) | column | what the README says it is |
|---|---|---|
| `cram` | `cram` | alignment, compressed with the karyotype-specific reference |
| `cramIndex` | `cram_index` | CRAM index for that alignment |
| `mosdepth_globalDist`, `mosdepth_regionsBed`, `mosdepth_regionsBedIndex`, `mosdepth_regionsDist`, `mosdepth_summary` | `mosdepth_*` | output of running `mosdepth` on the alignment CRAM |
| `samtools_stats` | `samtools_stats` | output of running `samtools stats` on the alignment CRAM |
| `chr{1-22}_hcVCF_gz` | `chrN_hcvcf_gz` | the gzipped output VCF for each autosome |

So for this dataset the predicate dictionary is not a set of judgments to be made — it is
a document written by the people who produced the files, covering ~17 predicates over
125,605 files. It also hands #363 the producing tool with the edge, which is #341's
subject: `mosdepth`, `samtools stats`, GATK `HaplotypeCaller`, BWA.

**Generalised: to read a submitter table, find the workflow that wrote it.** The column
vocabulary of a Terra-workspace dataset is whatever WDL produced it, and the karyotype
split visible in `xx_chrN_hcvcf_gz` / `xy_chrN_par_hcvcf_gz` is a documented pipeline
decision (separate XX and XY references, to improve sex-chromosome calling) rather than a
naming quirk.

## 7. What this means for the open work

- **#414 (value translation table)** stays on **cell values**. Column names contribute
  nothing to the five dimensions, measured twice.
- **#369 (slot map)** needs all three shapes, list-valued link columns, and a declared
  subject column per table. `assembly.assembly` is the cautionary case: it is a file
  pointer in the `assembly` table and a real reference (`unaligned`) in `hic`, so a
  column-name heuristic misroutes 466 DRS URIs into `reference_assembly`.
- **#363 (derivation graph)** is where the value is. Subject and predicate are exactly
  its nodes and edge labels, they arrive grounded, and the vocabulary is ~115 entries.
- **The upstream specifications are prior art for both.** `anvil_tdr_ingest` carries a
  mapping specification per dataset — `hprc_r2_1`, `mage_1`, `igvf_1`, `primed_1`,
  `card_1`, `gtex_ext_*` among them. Each names, per submitter table, the subject column
  and exactly which columns hold file pointers, which is the structural half of #369's
  slot map already authored by the people who ingest the data. Each also runs a
  `mapping_eval_query` counting records per `(source_value, mapped_value)` *including
  unmapped ones* — #414's review queue, already operational — against a
  `transform_resources.vocab_map` table keyed `(attribute, source_value, mapped_value)`,
  which is #414's translation table in all but name. That table is in BigQuery and not
  published, so its contents are not readable from here; the shape is what matters.
- **Facts with no slot** keep appearing, and they share a shape — they are properties of
  a relationship or an entity, never of a file's content: haplotype (`mat_`/`pat_`), read
  number (`read_1`/`read_2`), producing tool (`mosdepth`, `samtools`), chromosome
  (`chr10_`), instrument model, subject id. That is a #364 question, not a mapping one.

## 8. Method

All measurements are offline, over `data/anvil/manifest/anvil15/*.verbatim.jsonl` via
`azul_manifest.iter_verbatim_entities`, with the corpus from
`data/anvil/anvil_files_metadata.ndjson` and inference results from the stored run
`output/anvil/20260905_234159`.

- **Shape census**: per submitter table, count columns that ever hold a `drs://` string
  or a list of them. Bucket by 0 / 1 / 2+.
- **Reach**: union of DRS URIs held by any column of a 2+-link table, per dataset and
  overall.
- **Agreement**: `assembly_sample` column names → claimed value; join by `drs_uri` to the
  corpus; compare against the stored run's `reference_assembly` and `data_type`.
- **Predicates**: distinct link-column names on 2+-link tables, collapsed by replacing a
  chromosome token with `chrN`.

## 9. What is not established

- Whether the agreement result generalises. It covers 656 files of `ANVIL_HPRC`'s 23,185,
  all BAMs and FASTAs — file types inference reads well. A corpus of headerless or
  unfetchable files is exactly where a column name would earn its keep, and is unmeasured.
- What most of the 115 predicates mean. `ANVIL_T2T`'s are documented by the workflow that
  wrote them (§6), but the other datasets' are not yet traced to a source, and mapping any
  of them onto #363's verbs is still the work.
- Whether every Terra-workspace dataset has a findable workflow. The T2T route worked
  because the producers published their WDLs; that is a courtesy, not a guarantee.
- What the upstream specifications cost to consume. They are BigQuery SQL, not a
  declarative schema, so using them means parsing queries or re-expressing them. Nothing
  in the manifests on disk carries a schema: the Azul sidecar is our own download
  bookkeeping and a verbatim line is just `{type, value}`.
