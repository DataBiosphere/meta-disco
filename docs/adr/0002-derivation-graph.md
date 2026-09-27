# ADR-0002: The derivation graph — samples, donors, several parents, and what a child inherits

- **Status:** Proposed (2026-09-26)
- **Decision record for:** [#355](https://github.com/DataBiosphere/meta-disco/issues/355), part of epic [#363](https://github.com/DataBiosphere/meta-disco/issues/363)
- **Extends, and supersedes in part:** `docs/derived-file-data-model.md` (#109), which settled the edge for companion files only; see [What this supersedes](#what-this-supersedes)
- **Contract:** adds 4.9 to `docs/claims-contract.md` (inheritance), with its entry under "What is not true yet"
- **Related:** #356 (companion edges), #357 (sample identity), #358 (alignment ← reads), #359 (variants ← alignments), #360 (assemblies), #361 (sample ← donor), #362 (consistency and coverage), #371 (the edge carries the parent's record key), #413 (index inheritance and contract 1.1), #438 (ambiguous index parents)

## Context

The June design gave a derived file a typed `derived_from` edge: a verb, the kind of parent, and a
best-effort grounding by md5. Only the index producer emits one. This note extends that edge to the
whole chain — donor → sample → reads → alignments → variants, and reads → assembly → the files derived
from an assembly — so a question like "which reads made this CRAM" or "which of these VCFs come from one
person" has an answer across the corpus.

The measurements below are the re-measure of 2026-09-25, posted on
[#363](https://github.com/DataBiosphere/meta-disco/issues/363#issuecomment-5828815057), over anvil15
(708,088 files) and run `output/anvil/20260924_232619`. They replace the 2026-09-03 figures #355 quotes,
which counted header command lines only and overstated BAM grounding (59% then, 12% re-measured). The
re-measure found three sources beyond headers, and they are where most lineage is:

| source | what it states | measured |
|---|---|---|
| submitter tables, same row | one row lists several files, the column names give the direction — T2T `participant`: `read_1_fastq`, `read_2_fastq` → `cram` → `samtools_stats`, `mosdepth_*` | T2T 6,404 of 6,404 FASTQs linked to a CRAM; MAGE, ENCORE, HPRC_R2 `hifi` likewise |
| submitter tables, id join | a row's `*_id` equals an `assembly_id` in another table | HPRC_R2: 15 tables, 462 of 462 rows, 6,930 derivative files |
| `anvil_activity` | used files → generated files, by `file_id` | 244,116 files with a stated parent; covers 15,006 of #438's 15,058 declined index files |
| header command lines | BAM `@PG`, VCF caller lines | VCF ← alignment 151,268 resolved to one file (74%); BAM ← input 1,973 (12%) |
| HPRC assembly sample sheets (`hprc_intermediate_assembly`) | reads → assembly, per input file | 194 of 234 R2 assembly samples; 5,029 of 5,711 inputs match one file by name |
| filename convention | index ← parent, checksum ← parent | 93.3% and 99.6% |

Sample identity is the densest signal of all, measured over the cached headers: `@RG SM` on 80% of BAM
headers (13,125 of 16,427), VCF sample columns on 99.9% of VCF headers (203,823 of 204,102).

## Decisions

### 1. Samples and donors are identifiers, not records

A sample or donor is `{id, namespace, source_type}`, plus its dataset where the namespace is
`dataset_local`, not an entity record of its own.

- `id` is the string as written: `HG03016`, `SRS006902`.
- `namespace` is the authority that issued it — for example `coriell` (1000G/HPRC `HG…`/`NA…`),
  `sra_sample` (`SRS…`/`ERS…`), `biosample` (`SAMN…`/`SAMEA…`), `dataset_local`. The list is #357's to
  settle against the corpus.
- `source_type` is where we read it, from `source_type_enum`, with the exact place (`@RG SM`, a VCF
  sample column, a table and column) as provenance beside it, the way evidence records its column;
  which constant each place is, is #357's.

**Two identifiers name the same individual only when namespace and id both match** — and, for
`dataset_local`, the dataset too. That is what makes the search across datasets work:
`coriell:HG03016` is in ANVIL_1000G_high_coverage_2019, ANVIL_T2T, ANVIL_T2T_CHRY and AnVIL_HPRC_R2, and
an exact match finds all four. It is also what keeps two datasets that both call someone `S1` apart: a
`dataset_local` identifier carries its dataset, which is part of its identity, so it never matches across
datasets.

**Mapping between namespaces is out of scope here** and stays with #361: one person as
`coriell:HG03016` in one dataset and `sra_sample:SRS…` in another needs a registry crosswalk (IGSR,
BioSample), and without one the two stay separate.

*Why not records:* AnVIL's donor and biosample entities are populated almost nowhere (participant brief,
2026-08-22), and the attributes worth having come from registries keyed on these same ids, so a record
table would be empty scaffolding. Revisit if #337's manifest route populates them.

### 2. Parent scope: `internal` and `external`

- **`internal`** — the parent is one file we hold, in any dataset, and the edge carries its record key
  (`pipeline.SOURCE_RECORD_KEYS`). HPRC's parental Illumina CRAMs in ANVIL_1000G_high_coverage_2019 are
  internal though they are in another dataset.
- **`external`** — a source names the parent (`NA21127.merged.bam` in a `@PG` line) but it does not
  resolve to one file we hold: it was never deposited, or the name is shared by more than one (#438).

`parent_scope` is **not stored** on the record: it is whether `parent_key` is set, and a stored copy
could disagree with it. `edges.jsonl` works it out, so a consumer can filter on it. An edge whose parent
is an identifier (`sample_of`, `donor_of`, `child_of`) has no `parent_scope`: an identifier is neither a
file we hold nor one we lack.

*Rejected: a third scope, `type_only`* (the June doc's ungrounded edge: verb and parent kind known, no
parent named). A `.tbi` whose VCF cannot be picked already says it is a VCF index through its own
`data_type` and extension, so the edge would restate the file. **An edge exists only where a source names
a parent.**

*Rejected: grounding by md5*, which today's edge does, for the reason the June doc's 5a gives (#486).

### 3. An edge can have several parents

A CRAM derives from two FASTQs; a joint-called VCF from many gVCFs. `derived_from` becomes a list with one
edge per parent per source that states it, so a parent two sources name is two edges (decision 6).

The reference a file was aligned to is recorded **both** ways: the `reference_assembly` dimension is the
answer, and an `aligned_to` edge — to the reference FASTA where we hold it, otherwise external — is
where the answer came from. The edge never decides the dimension; it is evidence a consistency check
(#362) can compare with it.

### 4. A merged file is `merged_from` its shards; there is no callset node

ANVIL_T2T split calling into 100 kb windows (`chrY.39900001_40000000.genotyped.vcf.gz`). The chromosome
VCF is `merged_from` its window VCFs, where a source names them: the merged file is the child and the
shards its parents, because that is the direction values flow (decision 8) — the lineage reaches the
windows from the CRAMs, and the chromosome VCF, the file people want, inherits it from them. The reverse
verb (`shard_of`, merged file as parent) would send values the wrong way, from the file built last to the
files it was built from. There is **no callset node**:
no source names a callset as a thing of its own, and inventing one would be the entity scaffolding
decision 1 rejects.

### 5. Verbs

Only a verb a source can detect is minted (June doc 8d). The existing five stay:
`index_of`, `checksum_of`, `summarizes`, `lifted_over_from`, `derived_from` (generic: related, verb unknown).

| new verb | child ← parent | detected from |
|---|---|---|
| `aligned_from` | alignment ← reads | submitter same-row, `@PG`, `anvil_activity` (ENCORE `Alignment: STAR`) |
| `aligned_to` | alignment ← the reference it was aligned to | `@PG` reference argument, `@SQ UR` |
| `called_from` | variants ← alignments or gVCFs | VCF caller command lines, submitter same-row (1000G `cram` → `gvcf`) |
| `merged_from` | merged file ← shards | headers and filenames (T2T chromosome VCF ← window VCFs); the held-back verb of the June doc's 8d, now detectable |
| `assembled_from` | assembly ← reads | HPRC assembly sample sheets |
| `sample_of` | file ← sample id | `@RG SM`, VCF sample columns, filename accession, submitter tables (#357) |
| `donor_of` | sample id ← donor id | submitter tables, registries (#361) |
| `child_of` | donor id ← donor id | HPRC `sample.maternal_id`/`paternal_id`, 1000G pedigree (#361) |

`sample_of`, `donor_of` and `child_of` have an identifier as their parent, not a file (decision 1).

### 6. Sources, and where edges live

Five sources name file parents, the Context table's: submitter tables (same row or id join), `anvil_activity`,
header command lines, HPRC's assembly sheets, and filename convention for companion files. Every edge
records which one stated it, and an edge two sources state is two edges that agree — a consistency
check (#362) reads them. Identifier parents come from the sources decision 5 lists for `sample_of`,
`donor_of` and `child_of`, registries among them.

Submitter tables and `anvil_activity` are source evidence, which inference never reads (contract 1.2,
6.1). So **I recommend edges be built at reconcile**, the stage that reads both evidence and inference:
inference keeps writing the edges it reads itself (filename convention, header lines), and reconcile adds
the ones evidence states.

An edge whose child is a file is stored on that file's record as `derived_from: [DerivationEdge]`.
`donor_of` and `child_of` have an identifier as their child, which has no record, so they live only in a
flat `edges.jsonl` written once per run: child (a record key or an identifier), relation, parent
(`parent_key`, `parent_file` or an identifier), source, `parent_scope`. Its file-child rows are built
from the records, not a second source of truth, so the graph can be queried without loading every
record.

For companion files, `anvil_activity` states the parent by `file_id` and the filename match is the second
source: the two agreed on all 209,668 index files matched today.

### 7. Specific process runs stay out of scope

An edge records the **kind** of step — "aligned by `bwa mem`" from a `@PG` line (#341) — and links file to
file. It never records a particular run (a job id, a date, the exact parameters) as an object files link
to. The June doc made this call; it stands.

### 8. Inheritance: what a child takes from its parent

**Example.** T2T participant `HG03016`. The CRAM's header says `ILLUMINA`, so the CRAM's record has
`platform: ILLUMINA`. The VCF called from it says nothing about the sequencer, so the VCF's record has
`platform: not_classified` today. About 200K VCFs in ANVIL_T2T and ANVIL_T2T_CHRY are in that state
(run `output/anvil/20260926_120321`), and their indexes with them.

**Decision.** A child takes its parent's resolved value for each dimension the step carries, as a
declaration credited to the parent that reconciles with the child's own; contract 4.9 is the rule. So the
VCF takes `ILLUMINA`, and a VCF whose filename says `hifi` beside that CRAM is a `conflict` for a curator:
a mislabelled file or a wrong edge, which must not be settled silently.

**Parents that differ are mixed, not a conflict.** A child's parents are settled among themselves first:
parents that agree (4.4's sense, `is_a` nesting included) give the child one inherited declaration,
naming how many parents and which; parents that differ give it none, and the dimension is **mixed**. A
1000G joint call over NovaSeq 6000 and HiSeq X CRAMs has no single `instrument_model`, and an HPRC assembly
built from HiFi, ONT and Hi-C reads no single `platform`: nobody is wrong, so there is nothing for a
curator to answer. A mixed dimension leaves the child's own declarations to settle the slot alone, and
where the child has none it stays `not_classified`; the report lists the parents' values. Only the child
contradicting its inherited value is a conflict.

**What a parent passes on.** A value, or `not_applicable`, which the child's own evidence then meets as
4.6 says: a `.fai` stays `not_applicable` for `platform` beside its reference FASTA, as it is today. A
parent that is `not_classified` or mixed has no answer and passes nothing, so a mixed CRAM leaves its VCF
to the VCF's own evidence. One parent with a value and another `not_applicable` differ, so the
dimension is mixed. What a parent in `conflict` passes is open (below).

**What each step carries.** The dimensions split by whether the step keeps them. `data_type` never
carries: a VCF is not an alignment.

| step | `data_modality` | `assay_type` | `platform` | `instrument_model` | `reference_assembly` |
|---|---|---|---|---|---|
| `index_of`, `checksum_of`, `summarizes`, `merged_from`, `called_from` | yes | yes | yes | yes | yes |
| `aligned_from` | yes | yes | yes | yes | **no** — alignment introduces the reference |
| `lifted_over_from` | yes | yes | yes | yes | **no** — liftover changes it |
| `assembled_from` | yes | yes | yes | yes | **no** — an assembly is its own reference |
| `aligned_to`, `derived_from`, `sample_of`, `donor_of`, `child_of` | no | no | no | no | no |

- `aligned_to` points at a reference, not at the data the child came from. `derived_from` is the verb
  for "related, step unknown", so nothing is known to carry. `sample_of`, `donor_of` and `child_of`
  have an identifier as parent, which has no dimensions.
- Where the child reads a carried dimension itself — a VCF's `##contig` lines state its reference —
  inheriting it is a cross-check: agreement confirms the value, and a contradiction exposes a wrong edge.
  This supersedes the June doc's 7a (see [What this supersedes](#what-this-supersedes)).

**How this fits the rule-independence principle** (#88, PR #510: a rule never reads another rule's
answer, and no slot is filled only because it is empty). Where the child says nothing, inheriting *is* a
fallback; 4.9 names it, limits it to the table above and to crossing an edge, and has a contradiction
conflict rather than override.

*Rejected: never copy, follow the edge at query time* (the June doc's 5c). It keeps each record to what
its file shows, but nothing in this repo follows an edge, and whether the Explorer can is not known (June
doc 5c), so the ~200K VCFs would likely stay unclassified in practice. The table keeps the June doc's
concern where it matters: the dimensions that describe the file itself (`data_type`, and
`reference_assembly` across a step that changes it) are not copied.

*Rejected: the child's own evidence wins a contradiction.* It would settle a disagreement nobody reviewed.

**Today's case.** The index producer's inheritance (`classify_index_files.INHERITED_FIELDS`) is the
`index_of` row of the table, built the way the contract's "What is not true yet" entry on 1.1 describes.
How that path moves under 4.9 is #413's. That producer also writes the edge decision 2 rejects: an index
file with no parent picked (`declined_record`, #438, ~15K files) gets an `index_of` edge naming no parent.
#356 is where it is revisited, since `anvil_activity` names most of those parents.

The `checksum_file` rule contradicts the `checksum_of` row: it stamps all five lineage dimensions
`not_applicable`, which 4.6 would make a conflict against every inherited value (~14K `.md5` files). A
checksum is a companion like an index, not a special case, so when 4.9 is built that rule keeps only
`data_type: checksum` and drops the five statuses — the correction #437 made to the index rule. It also
shrinks what the engine's same-tier `not_applicable` exception protects (#511).

## What this supersedes

In `docs/derived-file-data-model.md`, each section below carries a marker pointing here.

| June doc | what it said | now |
|---|---|---|
| §1 point (3); §7b; §9 item 3 | a companion's lineage dimensions are `not_applicable`, reached only through the link | inherited across the edge (decision 8) |
| §4b; §6 Levels 1–2; §9 items 4 (its `parent_md5sum`), 5 | grounding by md5; an edge may name no parent | grounding by record key; no parent named, no edge (decision 2) |
| §1 point (1); §5a–5c; §9 item 7 | store a pointer, never a copy; follow at query time | copy, as a declaration that reconciles (decision 8, contract 4.9) |
| §1 point (4); §7a; §9 item 8 | read the reference from the file first, inherit second | both are declarations; contradiction is a conflict (decision 8) |
| §8d | `merged_from` held back | minted (decisions 4, 5) |
| §10 "What ships to the Explorer" | open | inherited values are on the record (decision 8) |

What stands: identity and origin are separate questions (§3) — an inherited value is credited to the
parent, so the record still says which values are the file's own — `data_type` names a companion's own
content type (§1 point 2, §8c), the verb is not redundant with `data_type` (§4c), and process instances
stay out of scope (§4b's process type vs instance, decision 7).

## Schema changes this implies

Listed, not applied. Each lands with the sub-issue that first emits it.

- `derived_from`: multivalued, `inlined_as_list` (decision 3).
- `DerivationEdge` gains:
  - `source_type`: the existing slot (range `source_type_enum`), not a new `source` — that slot name is
    taken, with range `ClaimSource` — with the table, column or header line as provenance beside it,
    as evidence records its column (decision 6). Which kind `anvil_activity` is — it is neither the
    submitter tables nor `anvil_file` — is #356's.
  - `parent_key`: the parent's record key per `SOURCE_RECORD_KEYS`; its presence is what `parent_scope`
    means, so `parent_scope` is not a slot (decisions 2, #371). Named for the key rather than
    `parent_file_id` because HPRC's key is not a `file_id`.
  - `parent_id`: an `EntityIdentifier`, the alternative to a file parent for `sample_of`, `donor_of`,
    `child_of` (decisions 1, 5).
  - `source_assembly`: range `reference_assembly_enum`, optionally with a `build` of range
    `ReferenceBuild`, on `lifted_over_from` only — the assembly the coordinates came from; the
    record's `reference_assembly` stays the current one (the comment on #355, measured 178
    Picard-lifted dbSNP files in ANVIL_T2T).
- `parent_md5sum` stays while the index producer emits it, and is retired by #371 once `parent_key` is
  written.
- New class `EntityIdentifier`: `id`, `namespace` (`identifier_namespace_enum`), `dataset` (set exactly
  when the namespace is `dataset_local`, and part of its identity), and `source_type` with the place it
  was read as provenance beside it, as on `DerivationEdge` (decision 1).
- `relation_enum` gains `aligned_from`, `aligned_to`, `called_from`, `merged_from`, `assembled_from`,
  `sample_of`, `donor_of`, `child_of` (decision 5); its description drops `merged_from` from the
  held-back list.
- What each step carries (decision 8) is declared once in data — on the `relation_enum` values or in a
  rules file — and read by code and a drift test; `INHERITED_FIELDS` becomes a reader of the `index_of`
  entry rather than a second copy.
- `credited_to_enum` and `reconcile.SLOT_CATEGORIES` gain a category for a slot filled by inheritance,
  and the conflict kinds one for a child against its parent, so the reconcile report counts neither as a
  source (contract 6.10). The report also needs a way to list a mixed dimension with its parents' values.
- An `edges.jsonl` row is its own class, not a `DerivationEdge`: its child is a record key or an
  `EntityIdentifier`, because `donor_of` and `child_of` have no record to sit on (decision 6).
- `parent_kind_enum` gains `reference` and `assembly` if #358 and #360 need them; decided there.

## Open

- **Which stage builds edges from evidence.** Decision 6 recommends reconcile; #356 confirms or overturns it.
- **Inheritance needs the parent settled first.** Parents and children are in different producer files
  (the CRAM in one, its VCF in another) and chains are deeper than one step (FASTQ → CRAM → VCF → `.tbi`),
  so sorting ~700K records by edge would break reconcile's one-file-at-a-time streaming. I think two
  passes fit instead: settle every record's own slots and keep only the carried dimensions per record key,
  resolve inheritance over that small map by a memoized walk that refuses a cycle, then write the files in
  their current order. Deciding `internal` for an evidence-stated parent needs the run's record keys; the
  pass reconcile's join already makes over the records can collect them. Not designed here.
- **A parent in `conflict`.** 4.4–4.5 reconcile declarations, and a conflict declares no value. Whether a
  parent's conflict reaches the child as a conflict (what the index producer does today) or as nothing is
  #413's to decide.
- **`external` covers two cases** — never deposited, and ambiguous by name. If a consumer needs them apart,
  a reason field on the edge would do it.
