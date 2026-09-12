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

**But the two authors are a heuristic for where to look, not the rule for how to read.**
Tables exist that are both. `AnVIL_HPRC_R2/assembly` (466 rows) was designed by someone
*and* holds four files per row:

```
assembly, assembly_fai, assembly_gzi, assembly_md5        4 file pointers
haplotype, genbank_accession, assembly_method,
assembly_method_version, phasing, source, assembly_date   real metadata values
sample_id                                                 foreign key
```

**So classify the column, not the table.** Every column is one of three things, and each
is read differently:

| column kind | test | the evidence is | yields |
|---|---|---|---|
| **file link** | holds a `drs://` URI, or a list of them | its **name** — the role | an edge (#363) |
| **metadata value** | holds anything else that is not an identifier | its **value** | a dimension claim (#414) |
| **foreign key** | names another entity (`sample_id`, `analyte_id`, `maternal_id`) | its value | the subject, or an entity→entity edge |

Read that way, `assembly` needs no classification at all: `assembly_method` is a value,
`assembly_fai` is an index edge, `sample_id` is the subject.

It also says what to **ignore**, which matters as much. In a workflow-materialized table
the cell values are pointers and mean nothing, and its column names must not be mapped to
dimensions — measured, that adds nothing (§4). In a model-authored table the column name
is a field label, not a description of the file: `platform` names the field, it does not
say the file is a platform.

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

## 3. The harmonized layer: what the ingest drops, and why it is empty

`anvil_activity` in `ANVIL_T2T`: **`Indexing` 116,247, `Unknown` 3,207.** That second
number is close to the 3,202 `participant` rows and each `Unknown` activity cites one of
them, but the counts are not equal and the five-activity difference is unexplained. One
of them:

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

### Why the harmonized layer is empty

The layer the ingest produces is the **Findability Subset Schema** — the ingest repo
carries `anvil_schema/fss_index_data_dictionary/`, and the AnVIL Data-Model repo's one
artifact is `AnVILDataSubmissionFindabilitySubsetSchema.template.xlsx`. Azul indexes it.
It is mostly unpopulated, and the reason is visible in the mapping.

The schema **defines** `data_modality` / `reference_assembly` / `assay_type` on six
tables, `anvil_file` among them. Three ingest paths can fill them, and only one usually
does:

| path | record set | what it produces |
|---|---|---|
| **inventory** — most specs, including `hprc_r2_1` | `file_inventory`, `file_metadata` | `file_id`, `file_format`, `file_ref`, `file_name`, `file_size`, `file_md5sum`. **No dimension columns exist in the mapping.** |
| **passthrough** — `anvil_1`, `anvil_2`, for submitters already shaped like the AnVIL model | `file_anvil` | adds `data_modality <- file.data_modality`, `reference_assembly <- file.reference_assembly` — if the submitter filled them |
| **bespoke** | per spec | `igvf_1` is the only one in our corpus that maps dimensions explicitly |

Worked example. HPRC's `hifi` row carries `platform = PACBIO_SMRT`,
`library_strategy = WGS`, `library_source = GENOMIC`, `data_type = unaligned reads`. The
activity query reads `sample_id` and `path` from it and nothing else; the file record
comes from `file_inventory`, a different table entirely. So `anvil_file.data_modality`
comes out empty while `GENOMIC` sits two tables away, untouched. **Nobody wrote the
mapping from `hifi.library_source` to `anvil_file.data_modality`** — nor from
`library_strategy` to `assay_type`, nor `platform` to `platform` — the specification
author did the structural half and not the semantic half.

That predicts our corpus exactly:

| dataset | files | data_modality | reference_assembly |
|---|---:|---:|---:|
| AnVIL_IGVF_Mouse_R1 | 6,786 | **6,755** | 220 |
| AnVIL_ENCORE_RS293 | 3,752 | 0 | **2,932** |
| AnVIL_ENCORE_293T | 1,992 | 0 | **1,544** |
| the other nine datasets | 695,558 | **0** | **0** |
| TOTAL | 708,088 | 0.95% | 0.66% |

`data_modality` is 100% IGVF, the one bespoke spec. `reference_assembly` is IGVF plus
ENCORE, whose submitter tables are already named `file` with AnVIL columns and who filled
`reference_assembly` but not `data_modality`. The 1% figure is not attrition or sampling:
it is three datasets, for two identifiable reasons.

### A compute ledger is not a catalog

The submitter tables are not a failed catalog. They are a good **compute ledger**, which
is a different artifact. In Terra a workflow runs over rows, inputs are wired by writing
`this.read_1_fastq` — so the column name *is* the variable name — and outputs are written
back as columns on the same row. The table records what has been produced and for which
rows.

Every property that makes that work makes it unfindable:

| good for the workflow | bad for the catalog |
|---|---|
| column name = WDL variable name | the vocabulary is workspace-local |
| outputs are files | no metadata values to facet on |
| schema shaped by this pipeline | no two workspaces share a schema |
| one row per compute unit | the unit differs — sample, chromosome, cohort |

That gap is what the FSS exists to close, and filling it costs real judgment: deciding
what `WGS` and `unaligned reads` and `PACBIO_SMRT` mean in a controlled vocabulary, once
per submitter, across twelve vocabularies.

**Why it stays unfilled is reasoning, not measurement** — but the incentive falls on the
far side of the work. A submitter gets daily value from the working tables because jobs
run against them; the FSS produces value for someone else, later, looking for the
dataset. Nothing breaks when it is thin. Consistent with that, the only datasets with
anything populated are the two where the cost was already paid for another reason.

**What that means for us.** The metadata is not lost, and we are not compensating for a
failure: the submitter tables are correct and current precisely because people compute
against them, and the semantic mapping is work nobody upstream is positioned to do. It
also means we are reading the layer with the maintenance incentive behind it.

### 3.1 The structural reason, in one comparison

Thinness here is not an AnVIL defect. It follows from what the model is organized around,
and a comparison makes it concrete.

**UCSC is reference-centric.** The assembly is the spine: every track hangs off a declared
genome (`genomes.txt`), and you cannot have a track without stating its assembly.

**AnVIL (Terra/Gen3/Azul) is subject-centric.** The spine is dataset → donor/biosample →
file, with a producing `activity`. The reference assembly is an optional *field* on a
file, so it is routinely absent — 13,658 of 13,660 BEDs blank, measured. AnVIL's structure
never *forces* what UCSC's structure *requires*.

The two line up through UCSC's assembly-hub (GenArk) model:

| UCSC | AnVIL/Azul analog |
| --- | --- |
| Hub | dataset (e.g. `ANVIL_HPRC`) |
| Assembly (genome / `db`) | a standard reference **or** a per-sample de-novo assembly |
| Track (typed file on an assembly) | file |
| `type` (bed / vcfTabix / bigWig / bam) | `file_format` |
| `group` (Variation / Expression / Repeats…) | `data_modality` + `data_type` (+ producing activity) |
| subtrack per sample | donor / biosample |
| `bigDataUrl` | `drs_uri` |
| `trackDb` — *the declaration* | the Azul index, often *lacking* the declaration |

Read that way, `reference_assembly` is "which UCSC genome — a standard reference, or
`not_applicable` because the file sits on a sample-specific assembly", which is what the
34% `not_applicable` BEDs are: per-sample de-novo assembly products.

It also explains where the declarations that *are* missing have gone. The file types split
across two domains with two metadata homes:

| domain | types | where the declaration lives | does content self-describe? |
| --- | --- | --- | --- |
| aligned / reference-anchored | BAM, VCF, BED, bigWig | UCSC `trackDb` + the file's own header (VCF `##contig`, BAM `@SQ`) | often **yes** |
| raw reads | FASTQ | SRA / ENA / the study's `library_strategy` | **no** — only platform, from read names |

UCSC holds no FASTQ at all (no coordinates, so not a track), which is why a browser cannot
supply FASTQ modality: that lives in the sequencing-archive world. meta-disco spans both
domains, so it needs both kinds of source — the claims contract's 2.9 is the same point
stated as a premise.

*Retired from ADR-0001 (#422), which reasoned it out.*

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

**Subject — the largest gain.** 435,284 files get a **typed subject**, at 100% of what is
reachable. Often that is a sample or a donor, which we cannot answer for any file today —
but not always: per §2 the subject may equally be a chromosome, an interval, a pangenome
release or a population cohort, and those tables contribute to this total. The reach
number says every reachable file is attributed to *some* named entity, not that every one
gains a donor.

**Role — real, but on far fewer than 61.5%, and not "grounded" in #363's sense.** What
resolves exactly here is the **object**: the file is named by a DRS URI, `drs_uri` is a
`JOIN_KEY`, and the check below matched 656/656. The **subject** is an identifier — a
sample id — not a node resolved in our corpus, so #363's *grounded* grade, which requires
the **parent** resolved in the same dataset, does not apply and its 59–82% figures are not
comparable. What these edges avoid is the guessing on the child side: no md5 lookup, no
filename match. The value then depends on the vocabulary, and it is uneven. `ANVIL_T2T/participant`'s ten columns are genuinely varied roles.
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
understood, at least for the two slots tested: `reference_assembly` and `data_type` on a
BAM or a FASTA are determined by content we already read, so a column name restating them
adds nothing. It is not a claim about all five slots or all inputs — inference also reads
extensions and file names, and §5's cell values *are* useful dimension evidence for other
slots. What is not recoverable from a file at all is the subject and the predicate, and
that is what these tables are made of.

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

**The column names are the WDL output names, snake-cased**, and the pipeline README says
what each one is. They are not byte-identical — `cramIndex` becomes `cram_index`,
`mosdepth_globalDist` becomes `mosdepth_global_dist`, and `mosdepth_regionsBedIndex`
becomes `mosdepth_regions_bed_idx` — so match on the role, not on the string:

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

- **#414 (value translation table)** stays on **cell values**. Where it was measured —
  `assembly_sample`'s column names, two slots, 656 readable files — the names added
  nothing. That is a bounded result, not a rule about every slot or dataset; the case it
  does not cover is a file inference cannot read (§9).
- **#369 (slot map)** needs all three shapes, list-valued link columns, and a declared
  subject column per table. `assembly.assembly` is the cautionary case: it is a file
  pointer in the `assembly` table and a real reference (`unaligned`) in `hic`, so a
  column-name heuristic misroutes 466 DRS URIs into `reference_assembly`.
- **#363 (derivation graph)** is where the value is. Subject and predicate are exactly
  its nodes and edge labels, and the vocabulary is ~115 entries. Note the qualification in
  §4: the *object* resolves exactly, the subject is an identifier rather than a node in our
  corpus, so these are not "grounded" in #363's sense and its 59–82% figures do not compare.
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
- **Harmonized coverage**: count non-null `data_modality` / `reference_assembly` per
  dataset over `anvil_files_metadata.ndjson`, against the mapping specifications and
  record sets in `broadinstitute/anvil_tdr_ingest`.

## 9. What is not established

- Whether the agreement result generalises. It covers 656 files of `ANVIL_HPRC`'s 23,185,
  all BAMs and FASTAs — file types inference reads well. A corpus of headerless or
  unfetchable files is exactly where a column name would earn its keep, and is unmeasured.
- What most of the 115 predicates mean. `ANVIL_T2T`'s are documented by the workflow that
  wrote them (§6), but the other datasets' are not yet traced to a source, and mapping any
  of them onto #363's verbs is still the work.
- Why the FSS stays unfilled (§3). The incentive argument is reasoning from how the
  artifacts are used, not something anyone has stated. So is the claim that the
  submitter format suits WDL work well — that is inference from how Terra wires
  workflow inputs, not a report of what AnVIL users say, and is worth asking someone
  who lives in it.
- Whether every Terra-workspace dataset has a findable workflow. The T2T route worked
  because the producers published their WDLs; that is a courtesy, not a guarantee.
- What the upstream specifications cost to consume. They are BigQuery SQL, not a
  declarative schema, so using them means parsing queries or re-expressing them. Nothing
  in the manifests on disk carries a schema: the Azul sidecar is our own download
  bookkeeping and a verbatim line is just `{type, value}`.
