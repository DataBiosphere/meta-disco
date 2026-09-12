# Interpreting submitter tables

**Status:** Findings, measured 2026-09-11 against `data/anvil/manifest/anvil15/`
**Scope:** the AnVIL *verbatim* manifests — the submitters' own tables, delivered unaltered

The verbatim manifests look like metadata tables and mostly are not. They are a **graph
serialized to tables**, and reading them as tables of file attributes is why three
separate attempts to mine them for our five dimensions came back nearly empty.

This document records what shape they are actually in, what that is worth, and what it
costs to use — all measured, with the method at the end so it can be re-run.

---

## 1. Three shapes, not one per submitter

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

## 3. The harmonized layer keeps the subject and the object, and drops the predicate

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

**Where this happens is not established.** The `anvil_*` entities carry
`datarepo_row_id`, and `anvil_activity.source_datarepo_row_ids` points at a TDR row in
the submitter's table, which suggests the mapping runs at ingest into TDR rather than in
Azul. That is inference from field names, not from documentation, and should be confirmed
before anyone repeats it.

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

## 6. What this means for the open work

- **#414 (value translation table)** stays on **cell values**. Column names contribute
  nothing to the five dimensions, measured twice.
- **#369 (slot map)** needs all three shapes, list-valued link columns, and a declared
  subject column per table. `assembly.assembly` is the cautionary case: it is a file
  pointer in the `assembly` table and a real reference (`unaligned`) in `hic`, so a
  column-name heuristic misroutes 466 DRS URIs into `reference_assembly`.
- **#363 (derivation graph)** is where the value is. Subject and predicate are exactly
  its nodes and edge labels, they arrive grounded, and the vocabulary is ~115 entries.
- **Facts with no slot** keep appearing, and they share a shape — they are properties of
  a relationship or an entity, never of a file's content: haplotype (`mat_`/`pat_`), read
  number (`read_1`/`read_2`), producing tool (`mosdepth`, `samtools`), chromosome
  (`chr10_`), instrument model, subject id. That is a #364 question, not a mapping one.

## 7. Method

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

## 8. What is not established

- Whether the harmonization loss happens in TDR or in Azul (§3).
- Whether the agreement result generalises. It covers 656 files of `ANVIL_HPRC`'s 23,185,
  all BAMs and FASTAs — file types inference reads well. A corpus of headerless or
  unfetchable files is exactly where a column name would earn its keep, and is unmeasured.
- What the 115 predicates mean. Reading `mosdepth_regions_bed` as a coverage track is a
  human judgment, and mapping them onto #363's verbs is the actual work.
- Whether a machine-readable schema exists upstream. Nothing on disk carries one: the
  Azul sidecar is our own download bookkeeping and a verbatim line is just
  `{type, value}`. TDR snapshots do define relational schemas, but reaching one needs the
  TDR API and a snapshot id nothing on disk records.
