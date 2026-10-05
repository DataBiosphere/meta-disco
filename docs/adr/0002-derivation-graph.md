# ADR-0002: The derivation graph — samples, donors, several parents, and what a child inherits

- **Status:** Proposed (2026-09-26)
- **Decision record for:** [#355](https://github.com/DataBiosphere/meta-disco/issues/355), part of epic [#363](https://github.com/DataBiosphere/meta-disco/issues/363)
- **Extends, and supersedes in part:** `docs/derived-file-data-model.md` (#109), which settled the edge for companion files only; see [What this supersedes](#what-this-supersedes)
- **Contract:** adds 4.9 to `docs/claims-contract.md` (inheritance) and its entry under "What is not true yet"; amends 2.8, 3.1, 4.1, 4.2 and 6.6 to match
- **Related:** #356 (companion edges), #357 (sample identity), #358 (alignment ← reads), #359 (variants ← alignments), #360 (assemblies), #361 (sample ← donor), #362 (consistency and coverage), #371 (the edge carries the parent's record key), #413 (index inheritance and contract 1.1), #438 (ambiguous index parents)
- **Amended by:** [#580](https://github.com/DataBiosphere/meta-disco/issues/580) (2026-09-29): a step is an activity from AnVIL FSS's vocabulary, not a verb between two files (decision 5); [#609](https://github.com/DataBiosphere/meta-disco/issues/609) (2026-10-03): which of a header's command lines made the file (decision 6); [#620](https://github.com/DataBiosphere/meta-disco/issues/620) (2026-10-05): a header-named alignment several files carry is settled by contigs (decision 6)

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

**A file's lineage lives inside its dataset.** A parent is looked for only in the child's own dataset,
and a parent not found there is `external` (decision 2). Only sample and donor identifiers cross datasets
(decision 1).

### 1. Samples and donors are identifiers, not records

A sample or donor is `{id, namespace, source_type}`, plus its dataset where the namespace is
`dataset_local`, not an entity record of its own.

- `id` is the string as written: `HG03016`, `SRS006902`.
- `namespace` is the authority that issued it — for example `coriell` (1000G/HPRC `HG…`/`NA…`),
  `sra_sample` (`SRS…`/`ERS…`), `biosample` (`SAMN…`/`SAMEA…`), `dataset_local`. The list is #357's to
  settle against the corpus.
- `source_type` is where we read it, from `source_type_enum`, with the exact place (`@RG SM`, a VCF
  sample column, a table and column) as provenance beside it, the way a claim records it (`source`
  and `rule_id` for evidence, `rule_id` alone for inference, schema changes below);
  which constant each place is, is #357's.

**Two identifiers name the same sample or donor only when namespace and id both match** — and, for
`dataset_local`, the dataset too. That is what makes the search across datasets work: `coriell:HG03016`
is in ANVIL_1000G_high_coverage_2019, ANVIL_T2T, ANVIL_T2T_CHRY and AnVIL_HPRC_R2, and an exact match finds
all four. It is also what keeps two datasets that both call someone `S1` apart: a `dataset_local`
identifier carries its dataset, which is part of its identity, so it never matches across datasets.
Equal identifiers say nothing about whether a sample identifier and a donor identifier are one person;
that is what a `SampleCollectionActivity` edge states (#361, #580). A `SequenceActivity` uses a sample
identifier, and a `SampleCollectionActivity` makes that sample from a donor identifier, read from the
sample's own row: AnVIL's `anvil_biosample.donor_id`, filled on every sample row of ten anvil15 datasets,
and a submitter table's donor column where one has it (1000G `sample.participant`, IGVF `sample.donors`). **Identifiers are the one thing that crosses datasets;
file edges never do** (decision 2).

**Mapping between namespaces is out of scope here** and stays with #361: one person as
`coriell:HG03016` in one dataset and `sra_sample:SRS…` in another needs a registry crosswalk (IGSR,
BioSample), and without one the two stay separate.

*Why not records:* AnVIL's donor and biosample entities are populated almost nowhere (participant brief,
2026-08-22), and the attributes worth having come from registries keyed on these same ids, so a record
table would be empty scaffolding. Revisit if #337's manifest route populates them.

### 2. Parent scope: `internal` and `external`

- **`internal`** — the parent is one file we hold **in the child's own dataset**, and the edge carries its
  record key (`record_keys.SOURCE_RECORD_KEYS`). A file parent resolves only within the child's dataset,
  whatever form the source names it in, as today's filename joins do.
- **`external`** — a source names the parent (`NA21127.merged.bam` in a `@PG` line, or a `file_id` or DRS
  URI in a table) but it is missing from the child's dataset: it was never deposited, or the name is
  shared by more than one file (#438). An `external` parent passes nothing (contract 4.9).

The parent as the source wrote it is always kept, resolved or not: `parent_file` for a name (looked up
only within the child's dataset), `parent_ref` for anything else a source gives — a `file_id`, a DRS URI, an S3 or filesystem path.
`parent_key` is set only when the parent, however named, resolves to a record of the child's dataset.

`parent_scope` is **not stored** on the record: it is whether `parent_key` is set, and a stored copy
could disagree with it. `edges.jsonl` works it out, so a consumer can filter on it. An edge whose parent
is an identifier (a `SequenceActivity`'s sample, a `SampleCollectionActivity`'s donor, an `isBiologicalChildOf` parent) has no `parent_scope`: an identifier is neither a
file we hold nor one we lack.

*Rejected: a third scope, `type_only`* (the June doc's ungrounded edge: verb and parent kind known, no
parent named). A `.tbi` whose VCF cannot be picked already says it is a VCF index through its own
`data_type` and extension, so the edge would restate the file. **An edge exists only where a source names
a parent.**

*Settled with #356: an edge from a filename convention is written only where its parent resolves.* The name
such a convention gives is the child's own less a suffix (`HG01466.chr15.hc.vcf.gz.tbi` names
`HG01466.chr15.hc.vcf.gz`), so an unresolved one — no file carrying it, or two (#438) — would restate the file
for the reason above. An `external` edge comes only from a source that names the parent independently of the
child: a header line, a table row, IGVF's `derived_from`.

*Rejected: grounding by md5*, which the edge did until #356, for the reason the June doc's 5a gives (#486).

### 3. An edge can have several parents

A CRAM derives from two FASTQs; a joint-called VCF from many gVCFs. A file is made by **one** step, so its
record carries one `generated_by` (#580): the activity, and its `inputs`, one per parent, each in a role
the activity declares. The step and each input carry `named_by`, every source that named it, so agreeing
sources are all listed: a `.tbi`'s file name and `anvil_activity` both name its indexing and its VCF. An
*edge* in this record is one such input. Sources add inputs to the one step: a parent two sources name is
one input they agree on, or, for a role
that takes one, two inputs in conflict (decision 5). Sources that name different activities for one file are an **activity conflict**, listed
for review, across which nothing is inherited; a specific activity and the generic `Activity` agree, since
every term is an `Activity`. *Rejected (#580): one edge per parent, each naming
the activity*, the shape #356 first wrote: three edges naming `AlignmentActivity` read as three
alignments, and none said which input was the reads and which the reference.

The reference a file was aligned to is an input of its alignment in a role of its own (#580): an
`AlignmentActivity` has a `reads` input, which passes the sequencer and the library, and a `reference`
input, which passes `reference_assembly` and nothing else (decision 8). Where a source names the reference
(`@PG`'s reference argument, `@SQ UR`, a table row), it is an input of the alignment in that role;
where the file itself states its reference (`@SQ` lengths), that is the child's own declaration, and the
two reconcile as any two do (4.9).

### 4. A merged file is made from its shards by a `MergeActivity`; there is no callset node

ANVIL_T2T split calling into 100 kb windows (`chrY.39900001_40000000.genotyped.vcf.gz`). The chromosome
VCF's `MergeActivity` has its window VCFs as inputs, where a source names them: the merged file is the
child and the shards its parents, because that is the direction values flow (decision 8) — the lineage reaches the
windows from the CRAMs, and the chromosome VCF, the file people want, inherits it from them. The reverse
step (a shard as the child, the merged file as its parent) would send values the wrong way, from the file built last to the
files it was built from. There is **no callset node**:
no source names a callset as a thing of its own, and inventing one would be the entity scaffolding
decision 1 rejects.

*Amended by #621.* A merge may name its inputs through a **list** rather than one by one: T2T's
GenomicsDB workspace tars each merge the gVCFs of one chromosome's GATK sample-name map, and the tar's own
`vcfheader.vcf` names the map. The tar's step is a `CohortMergeActivity`, a `MergeActivity` whose one
input is the map, in the role `input_list`, and the map's own step, a `CohortDefinitionActivity`, has each listed gVCF as a `member`.
Linking each of 31,155 tars to each of its 3,202 gVCFs would be about 100M inputs; the map is the record of
who was joint-called together (a comparability factor, #619), and the tar reads its members' answers
**through** it (decision 8, contract 4.9). The map is a list of names, not data, so it passes nothing of
its own.

### 5. Activities

*Amended by #580.* A step is named by its **activity**, not by a verb between two files. The
vocabulary is `activity_type_enum`: AnVIL FSS's `ActivityTypes`, spelled as FSS's released LinkML schema
spells them (`DataBiosphere/biocore-data-model`, `AnVILDataSubmissionFindabilitySubsetSchema.linkml.yaml`),
plus nine of our own (`CoverageActivity` added by #595; `VariantProcessingActivity` and `VariantFilterActivity` by #610; `CohortDefinitionActivity` and `CohortMergeActivity` by #621). FSS's values spreadsheet spells three differently (`VariantCallingActivity`,
`ImagingActivity`, `IndexingActivity`); the schema a submission is validated against wins. A term's `meaning` is the Terra
Interoperability Model's class where it has one, else EDAM's operation where EDAM defines the same step.
TerraCore's `Activity` is a `prov:Activity`, and FSS's `used_file_id` and `generated_file_id` are PROV's
`used` and `wasGeneratedBy`. A file's record names the activity that made it
(decision 3).

| activity | child ← parent | detected from | replaces |
|---|---|---|---|
| `IndexActivity` | index ← indexed file | filename convention, `anvil_activity` `Indexing` | `index_of` |
| `ChecksumActivity` | checksum ← checked file | filename convention, `anvil_activity` `Checksum` | `checksum_of` |
| `QualityControlActivity` (ours, under `AnalysisActivity`) | QC report ← the file it reports on | submitter same-row (T2T `samtools_stats`, `mosdepth_*` → `cram`) | `summarizes` |
| `AlignmentActivity` | alignment ← reads | submitter same-row, `@PG`, `anvil_activity` (ENCORE `Alignment: STAR`) | `aligned_from` |
| `VariantCallActivity` | variants ← alignments or gVCFs | VCF caller command lines, submitter same-row (1000G `cram` → `gvcf`; T2T `interval`: region VCF ← GenomicsDB tar, #610) | `called_from` |
| `MergeActivity` (ours) | merged file ← shards | VCF headers (T2T chromosome VCF ← region VCFs, its `bcftools concat` line, #610), `anvil_activity` (ENCORE `Merger: multiple FASTQ files`, #595) | `merged_from` |
| `CohortMergeActivity` (ours, under `MergeActivity`; #621) | merged file ← the cohort's list naming its inputs (`input_list`) | a GenomicsDB workspace's `vcfheader.vcf` (T2T tar ← its chromosome's sample map, its `GenomicsDBImport` line) | — |
| `CohortDefinitionActivity` (ours; #621) | list ← each file it lists (`member`) | a GATK sample-name map's own rows (T2T `chrN_sample_map.tsv` ← its gVCFs) | — |
| `CoverageActivity` (ours, under `AnalysisActivity`; #595) | coverage track ← the alignment it covers | `anvil_activity` (ENCORE `Track: bedGraphToBigWig`) | — |
| `VariantFilterActivity` (ours, under the abstract `VariantProcessingActivity`; #610) | filtered callset ← the callset it filtered | submitter same-row (T2T `chromosome`: raw → recalibrated → PASS on CHM13; recalibrated → PASS on GRCh38, whose raw callset the table does not hold) | — |
| `LiftoverActivity` (ours, under `AnalysisActivity`) | lifted file ← the file it was lifted from | a source naming the parent (schema changes, `source_assembly`) | `lifted_over_from` |
| `AssemblyActivity` (ours) | assembly ← reads | HPRC assembly sample sheets, where the output resolves to a held assembly (Open) | `assembled_from` |
| `SequenceActivity` | reads ← sample id | `anvil_activity` `Sequencing`, submitter tables (#357) | `sample_of`, for reads |
| `SampleCollectionActivity` | sample id ← donor id | the sample's row: `anvil_biosample.donor_id`, a submitter donor column (#361) | `donor_of` |
| `Activity` | related, step unknown | IGVF `file.derived_from` between content types no term names, `anvil_activity` `Unknown` | `derived_from` |

**EDAM operations for steps not yet linked** (looked up in EBI OLS, 2026-10-04, #610). A term added
for one of these takes the id as its `meaning`, by the rule above, rather than searching again:

| step | EDAM operation | where AnVIL holds it |
|---|---|---|
| methylation calling | `operation_3919` Methylation calling | HPRC methylation BAMs (#481) |
| peak calling | `operation_3222` Peak calling | ATAC-seq and ChIP-seq peaks |
| base-calling | `operation_3185` Base-calling | ONT `fast5` → reads (NIA_CARD, HPRC; #605) |
| demultiplexing | `operation_3933` Demultiplexing | per-sample reads from a pooled run |
| read pre-processing, trimming | `operation_3219` Read pre-processing; `operation_3192` Sequence trimming | ENCORE's trimmed FASTQs |
| a population or sample subset of a callset | `operation_3695` Data filtering | T2T's per-population PASS VCFs (`…pass.AFR.vcf.gz`) |
| variant annotation or classification | `operation_3225` Variant classification | none annotated yet; `operation_0331` Variant effect prediction is about protein structure, not this |

EDAM has no operation for variant normalization, joint genotyping as a step of its own (Genotyping,
`operation_3196`, is a close mapping on `VariantCallActivity`), a GenomicsDB import, a cohort
definition, or a file's checksum (`operation_3348` checksums a sequence). A term for one of these
records no id.

FSS's other types (`SampleCollectionActivity`, `SampleTreatmentActivity`, `ExpressionActivity`,
`AnalysisActivity`, `ImageActivity`) are in the vocabulary, though when this ADR was written no
translation row mapped a source's value to one; ENCORE's `anvil_activity` rows (`Quantificatioin: salmon`,
`DifferentialExpression: deseq2`, `AlternativeSplicing: rMATS`) state expression and analysis steps that
such rows would map. (Amended by #595: `Quantificatioin: salmon` now maps to `ExpressionActivity`.) A
source's raw `activity_type` reaches a term through translation rows, as a raw value does (contract
3.9); those rows are the activity map's, `rules/activity_map.yaml` (#584).

**Not activities.** `aligned_to` is dropped: the reference is the `reference` input of an
`AlignmentActivity` (decision 3). A donor's parents are a family tie, not a step: no processing step
makes a child from its parents and nothing passes across it, so it stays the one relation of its own,
**`isBiologicalChildOf`** (the GA4GH Pedigree Standard's Kinship Ontology, KIN:032; its inverse is
`isBiologicalParentOf`, KIN:003), in `edges.jsonl` only (decision 6, #361). It points from child to
parent, as every edge here does, and carries a `role`, `mother` or `father`, from the submitter column
that states it: HPRC's and HPRC_R2's `maternal_id` / `paternal_id` (tables `sample`, `sample_metadata`,
`illumina`), 1000G's `pedigree.motherid` / `fatherid`, where `0` means not known and gives no edge. A
role takes one parent, so two tables naming different mothers for one donor are an edge conflict.
`anvil_donor` has no parent columns. *Rejected (#580): `donor_of` as a relation* beside the activities. A sample row naming its donor
states no step, but neither does a submitter row naming a CRAM beside its FASTQs, and the lineage map
names that step all the same; one formalism for lineage (HCA's `process`) keeps a place for what a paper
or methods section says about a collection. A sample that a file's own header names (`@RG SM`, a VCF's sample
columns) says which sample the data is about, not which step made the file; how it is recorded is #357's
(Open).

**Each activity declares its output and its inputs by role**, or takes them from an abstract ancestor (#610), in `rules/activities.yaml`, whose shape is
the LinkML class `ActivityDeclarations`. The output is a file or an identifier, and for a file the
`data_type` kinds it may be. Each input role says the same, and whether the step always has it
(`required`), whether an output has several in that role (`many`), and what the output takes from it
(`passes`). An `AlignmentActivity`'s `reads` are many and its `reference` one; an index's `indexed` file is
one. A required role no source names is lineage known to exist and not held. Sources that name the same
parent for a role that takes one are one parent with two sources. Sources that name different parents for
it are an **edge conflict**: a `.tbi` whose filename match says
`a.vcf.gz` and whose `anvil_activity` says `b.vcf.gz` has one of them wrong. An edge conflict is listed
for review, and nothing is inherited across that activity until it is settled. For a role that
takes many, the parents every source names are pooled into one set of inputs, each listing in `named_by`
the sources that named it (decision 6) — except where inference names that role: its step names every input
of the step it read, so a source naming another set there is an edge conflict too (#609, contract 4.9).

**A term exists where what passes differs, and is named for what the step does** (#610). Many tools
fall under one term: `AlignmentActivity` is bwa, STAR or minimap2. A family of steps that pass the same
shares one **abstract** parent that declares, once, what passes, and each step is a child named for what
it does, declaring only its reason. `VariantProcessingActivity` is such a parent (a callset in, a callset
out, every call it keeps made from the same reads against the same reference, though a subset drops
samples); `VariantFilterActivity` is its first child (GATK's
ApplyVQSR labelling every row, `bcftools view -f PASS` keeping the passing ones). Annotation,
normalization and a population subset would be further children, each one enum line. No step names an
abstract term: `activities.require_writable` refuses one in an activity-map row, and every edge rule is
held to it. Which operation a step was can also be read by comparing its input with its output (rows
removed, samples dropped, annotation fields added), so the leaves need not multiply past what a reader
asks for. *Rejected (#610): one broad term, `VariantProcessingActivity`, written on records*: it says
nothing a scientist can use.

*Rejected (#580): verbs on file-to-file edges*, which this decision first minted. The sources state
lineage as steps: `anvil_activity` has one row per step, and FSS's Activity table is its model. What
passes to a child depends on the step, so a verb was the activity seen from the child's side, and a verb
list of our own was a vocabulary no submitter writes.

### 6. Sources, and where edges live

Five sources name file parents, the Context table's: submitter tables (same row or id join), `anvil_activity`,
header command lines, HPRC's assembly sheets, and filename convention (companion files, and T2T's window
VCFs for a `MergeActivity`). Every step
and input records which sources named it, and one two sources name is one step or input listing both in
`named_by` — a consistency check (#362) reads them. Identifier parents come from the sources decision 5 lists for `SequenceActivity` and
`SampleCollectionActivity`, and, for `isBiologicalChildOf`, from submitter tables and registries (#361).

Submitter tables and `anvil_activity` are source evidence, which inference never reads (contract 1.2,
6.1). So **edges the evidence states are built at reconcile** (settled with #356, 2026-09-28; built by
#577), the stage that reads both evidence and inference: inference keeps writing the edges it reads itself
(filename convention, header lines), and reconcile adds the ones evidence states. Reconcile is also the one
stage holding both kinds, which a chain mixes (T2T: `.tbi` → VCF by name, CRAM → FASTQ by table row), and
re-running it costs no corpus run (6.4) when a lineage mapping is corrected.

A step whose output is a file is stored on that file's record as `generated_by: GeneratedBy`, its inputs
`ActivityInput`s.
A `SampleCollectionActivity` and an `isBiologicalChildOf` have an identifier as their child, which has no record, so
they live only in a flat `edges.jsonl` written once per run: child (a record key or an identifier), the
edge's activity (or `isBiologicalChildOf`, with its `role`), parent
(`parent_key` where it resolves, and `parent_file` or `parent_ref` as the source wrote it, or an
identifier), provenance (`source_type`, plus `source` and `rule_id` for evidence or `rule_id` alone for inference,
as on the edge), and `parent_scope`,
worked out. Its file-child rows are built
from the records, not a second source of truth, so the graph can be queried without loading every
record.

For companion files, `anvil_activity` states the parent by `file_id` and the filename match is the second
source: the two agreed on all 209,668 index files matched today.

**Which header command line made the file (#609).** A header carries the command lines of its inputs as
well as its own, and GATK sorts them, so neither the last line nor any one line's position names the step.
The step is **the end of the data flow**: each line is a step with inputs and an output, steps chain where
an output is an input (by base name, `.gz` aside), and an end is a step whose output no other step consumes.
An end naming another file is set aside; the step that made the file is the one end naming it, or an end
naming no output (stdout) when it is the only end at all. No such step, or a tool whose arguments are
not declared (`validators.command_lines.TOOL_ARGUMENTS`, about tools, never datasets), and no step is written. The
paths are where the workflow ran, so the parent resolves by name within the child's dataset, as a
filename edge does. Built at inference, in the VCF producer, from the cached header: it is the file's own
bytes (input kind 1), and reconcile merges it with the steps the tables state.

*Amended by #620 (2026-10-05): a name several alignments carry is settled by their contigs.* T2T
re-aligned some samples' reads to a second reference under the same file name, so a `HaplotypeCaller`'s
input names two CRAMs. GATK refuses an alignment with a contig its reference lacks or gives another
length (unless the line turns that check off, which no header we hold does), and writes that reference's
contigs into the VCF, so the parent is the one carrier whose every `@SQ` name and length is among the
VCF's `##contig` names and lengths, read from the carrier's own header (the BAM producer's cache, or
samtools into it on a miss). None or several fitting, or a VCF naming no contig lengths, gives no step
(`parent_ambiguous`); so does a carrier whose header cannot be read (`parent_unreadable`). This is the file's bytes on both sides, not a name; a
`concat`'s VCF inputs are not settled this way.

*Rejected: the last line.* T2T's `1kgp.chr1.recalibrated.snp_indel.vcf.gz` ends in the `bcftools concat`
that made its input, `chr1.genotyped.vcf`; its producer is the indel pass of `ApplyVQSR`, which GATK's
sorting puts first.

### 7. Specific process runs stay out of scope

An edge records the kind of step between two files (`AlignmentActivity`), not the run. The `@PG` line
that shows a BAM was made by `bwa mem` is evidence for the edge; recording the tool as a fact of its own
is #341's, and undecided. Where a source gives the run an id (`anvil_activity.activity_id`), the step's `named_by` entry for that
source carries it as `activity_id` (#580). The run is still not an
object that files link to, with its date and parameters. The June doc made this call; it stands.

*Rejected (#580): activities as objects of their own*: a run-level file of `{activity_id, type, used,
generated}`, each record pointing at one, as PROV and FSS's Activity table model it. A record would no
longer say where it came from without a join, reconcile would read a second file beside the records, and
most sources name no run (a submitter row, a file name), so ids would be invented for most of them.

### 8. Inheritance: what a child takes from its parent

**Example.** T2T participant `HG03016`. The CRAM's header says `ILLUMINA`, so the CRAM's record has
`platform: ILLUMINA`. The VCF called from it says nothing about the sequencer, so the VCF's record has
`platform: not_classified` today. About 200K VCFs in ANVIL_T2T and ANVIL_T2T_CHRY are in that state
(run `output/anvil/20260926_120321`), and their indexes with them.

**Decision.** A child takes its parent's resolved value for each dimension the step carries, as a
declaration credited to the parent that reconciles with the child's own; contract 4.9 is the rule. So the
VCF takes `ILLUMINA`, and a VCF whose filename says `hifi` beside that CRAM is a `conflict` for a curator:
a mislabelled file or a wrong edge, which must not be settled silently.

**Parents that differ are mixed, not a conflict.** A child has one activity (decision 3). Its parents in
one input role — the pooled set of a role that takes many (decision 5) — are settled among themselves
first, one declaration per role that passes the dimension; where two roles pass one dimension, the two
declarations reconcile with each other as any two do (no declared activity does so today):
parents that agree (4.4's sense, `is_a` nesting included) give the child one inherited declaration,
naming how many parents and which; parents that differ give it a **mixed** declaration, which carries no
value. A 1000G joint call over NovaSeq 6000 and HiSeq X CRAMs has no single `instrument_model`, and an
HPRC assembly built from HiFi, ONT and Hi-C reads no single `platform`: nobody is wrong, so where the child
says nothing the slot stays `not_classified`, marked mixed, with nothing for a curator to answer; the report
lists the parents' values. But a joint call whose filename says `NovaSeq 6000` claims one value for a
lineage that has none, so the child declaring a value against mixed is a conflict, as is the child
declaring `not_applicable` against it. A second carrying role's value or `not_applicable` against mixed is
a conflict the same way; two mixed declarations stay mixed (contract 4.9). Separately, the child
contradicting a value its parents agree on is a conflict.

**What a parent passes on.** A value, or `not_applicable`, which the child's own evidence then meets as
4.6 says: a `.fai` stays `not_applicable` for `platform` beside its reference FASTA, as it is today. A
parent that is `not_classified` has no answer, and where the parents that have one agree, the others
cannot then be known to be unanimous, so the whole activity passes nothing for that dimension: a joint VCF over
one `ILLUMINA` CRAM and one unclassified CRAM inherits no `platform`. Where the parents are already known to
differ, or one is mixed, the activity gives mixed whatever the unclassified ones are. A parent that is mixed passes mixed: a
CRAM merged from NovaSeq and HiSeq reads makes its VCF mixed too. One parent with a value and another
`not_applicable` differ, so the dimension is mixed. What a parent in `conflict` passes is open (below).

**What each step carries.** The dimensions split by whether the step keeps them. `data_type` never
carries: a VCF is not an alignment. Each activity's `passes` in `rules/activities.yaml` is the
authority, and this table is its reading when #580 wrote it, amended where a row says so.

| activity | `data_modality` | `assay_type` | `platform` | `instrument_model` | `reference_assembly` |
|---|---|---|---|---|---|
| `IndexActivity`, `QualityControlActivity`, `CoverageActivity` (amended by #595), `MergeActivity`, `VariantCallActivity`, `VariantFilterActivity` (#610, from its parent `VariantProcessingActivity`) | yes | yes | yes | yes | yes |
| `AlignmentActivity` | yes, from `reads` | yes, from `reads` | yes, from `reads` | yes, from `reads` | from its `reference` input only, not from the reads |
| `LiftoverActivity` | yes | yes | yes | yes | **no** — liftover changes it |
| `AssemblyActivity` | yes | yes | yes | yes | **no** — an assembly is its own reference |
| `ExpressionActivity` (amended by #595) | yes | yes | yes | yes | **no** — quantified against a transcriptome |
| `Activity`, `ChecksumActivity` (amended by #596), `CohortDefinitionActivity` (#621), `SequenceActivity`, `SampleCollectionActivity`, `SampleTreatmentActivity`, `ImageActivity`, `AnalysisActivity` | no | no | no | no | no |

`CohortMergeActivity`'s `input_list` role (#621) passes all five, read through its list: what the list's
`member`s settle to, not the list's own answer (contract 4.9).

- Carrying `reference_assembly` carries the build's identity — `ReferenceBuild.base` and `version` —
  so a child describes its reference as precisely as its parents agree on it. The build's observations
  (`chr1_m5`, `chry_m5`, `name`, `name_source`) are readings of the parent's own header and are not
  copied: the inherited declaration is credited to the parent (4.9), which is where they stay. The slot
  reconciles on its value (4.4). Parents that agree on the value but differ in build identity give the
  value and no build, until how builds reconcile is decided (Open). (Today's index producer copies the
  whole build; that path is #413's.)
- `Activity` is the step not known, so nothing is known to carry. `SequenceActivity`,
  `SampleCollectionActivity`, `SampleTreatmentActivity` and `ImageActivity` have a sample identifier as
  input, which has no dimensions.
- `AnalysisActivity` carries nothing until someone decides what it keeps: it covers steps too different
  to share one answer. A narrower term under it declares its own, as `QualityControlActivity` and
  `LiftoverActivity` do.
- `ExpressionActivity` never carries the reference (amended by #595): the one quantifier mapped to it,
  salmon, quantifies reads against a transcriptome, and `rules/activities.yaml` gives why. Counting genome
  alignments, which would keep their reference, needs a narrower term of its own.
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

**How it was built (#571).** Reconcile carries every row of the table across each file's step
(`reconcile_inherit`), and the index producer's own copy of its parent's answer, built outside
`make_claim`, is gone (#413): it writes the index's kind and the `IndexActivity` edge and nothing
more. That producer used to write the edge decision 2 rejects, an index edge naming no parent on an
index file it took no parent for (`declined_record`, #438, ~15K files); #356 removed it, and
`anvil_activity`, which names most of those parents, gives them theirs (#577).

**Amended (#596): a checksum passes nothing.** #571 first treated a checksum as a companion like an
index: `ChecksumActivity` passed all five dimensions, and the `checksum_file` rule dropped its
`not_applicable`. That made 14,074 `.md5` files say what their file says (`genomic`, a platform, a
reference), which is not true of a hash of bytes. AnVIL publishes none of it, and the `auxiliary_inert`
consistency rule forbids it. An index differs because it points into coordinates on its file's
reference, so the dimensions apply to it; a checksum has nothing they could describe. So
`ChecksumActivity` passes nothing, `checksum_file` makes the five `not_applicable` again, and the step
stays as the link from a checksum to its file.

## What this supersedes

In `docs/derived-file-data-model.md`, each section below carries a marker pointing here (§10's is inline,
on the bullets concerned).

| June doc | what it said | now |
|---|---|---|
| §1 point (3); §3's `not_applicable` for a `.bai`; §7's opening; §7b; §8c's "descriptive ⇒ `not_applicable`"; §9 item 3 | a companion's lineage dimensions are `not_applicable`, reached only through the link | an index's: inherited across the edge (decision 8). A checksum's: still `not_applicable`, reached through the link (#596) |
| §4a's edge with no parent; §4b; §6 Levels 1–2; §9 items 4 (its `parent_md5sum`), 5 | grounding by md5; an edge may name no parent | grounding by record key; no parent named, no edge (decision 2) |
| §1 point (1); §3's "not values copied onto this file"; §5a–5c; §6 Level 3; §9 item 7; §10 "Confirmed" on materialization and query time | store a pointer, never a copy; follow at query time | copy, as a declaration that reconciles (decision 8, contract 4.9) |
| §1 point (4); §7a; §9 item 8 | read the reference from the file first, inherit second | both are declarations; contradiction is a conflict (decision 8) |
| §8d | `merged_from` held back | a `MergeActivity` (decisions 4, 5) |
| §10 "What ships to the Explorer" | open | inherited values are on the record (decision 8) |

What stands: identity and origin are separate questions (§3's split, though not where it stores
origin) — an inherited value is credited to the parent, so the record still says which values are the
file's own — `data_type` names a companion's own
content type (§1 point 2, §8c's factoring), the step is not redundant with `data_type` (§4c), and process instances
stay out of scope (§4b's process type vs instance, decision 7).

## Schema changes this implies

Listed, not applied. Each lands with the sub-issue that first emits it.

- **Done (#580):** `derived_from` is replaced by `generated_by` (`GeneratedBy`: `activity`, `named_by`,
  and `inputs`, each an `ActivityInput` with its `role` and `named_by`). A `named_by` entry is an
  `Attribution`: `source_type`, `rule_id`, and `activity_id` and `source` where a source gives them
  (decisions 3, 6).
- `ActivityInput` gains:
  - **Done (#580):** provenance, as `named_by` entries (`Attribution`, above): for a source evidence
    states, its `source` (`ClaimSource`: name, dataset, table, column) **and** a `rule_id` naming the
    mapping that turned that column or activity type into an activity; for inference, `rule_id` alone.
    Which `source_type` `anvil_activity` is — it is neither the submitter tables nor `anvil_file` — is
    #577's (split from #356).
  - `parent_key`: the parent's record key per `SOURCE_RECORD_KEYS`, set only when the parent resolves to
    a record of the child's dataset; its presence is what `parent_scope` means, so `parent_scope` is not a
    slot (decisions 2, #371). Named for the key rather than `parent_file_id` because HPRC's key is not a
    `file_id`.
  - `parent_ref`: the parent as a source wrote it when that is not a bare name — a `file_id`, a DRS URI,
    an S3 or filesystem path — kept whether or not
    it resolves (decision 2); a name stays in `parent_file`.
  - A constraint: exactly one parent form per input — `parent_id`, or a file parent (`parent_file` or
    `parent_ref`, with `parent_key` where it resolves) — and the `form` its role declares
    (`rules/activities.yaml`: an identifier for `SequenceActivity`'s sample and the other sample steps' inputs;
    a file otherwise). Today's schema requires `parent_file`, which an
    input a source names only by `file_id` does not have (#577).
  - `parent_id`: an `EntityIdentifier`, the alternative to a file parent for an activity whose input is
    a sample (decisions 1, 5).
- `source_assembly` on the record's `reference_assembly` slot, beside `build`, not on the edge: an inlined
  `{value: reference_assembly_enum, build: ReferenceBuild}` (build optional) naming the assembly a lifted
  file's coordinates came from, read from its header (`##liftOverChain`) or name (`GRCh38` in
  `dbSNP.build_154.GRCh38.*`) whether or not a parent file is named. The slot's value stays the current
  assembly (the comment on #355; 178 Picard-lifted dbSNP files in ANVIL_T2T). A `LiftoverActivity` edge is
  written only where a parent is named.
- An inherited `reference_assembly` claim carries a `ReferenceBuild` with `base` and `version` only, where
  the parents agree on them, and none where they differ, and
  names the parent it came from (decision 8); the header observations stay on the parent's record.
- `parent_md5sum` is retired: #356 writes `parent_key` in its place.
- New class `EntityIdentifier`: `id`, `namespace` (`identifier_namespace_enum`), `dataset` (set exactly
  when the namespace is `dataset_local`, and part of its identity), and the same provenance as
  an `ActivityInput`, a `named_by` list of `Attribution` (decision 1).
- **Done (#580):** the verb (`relation`, `relation_enum`) is replaced by `GeneratedBy.activity` (range
  `activity_type_enum`, decision 5), and a source's run id is its `named_by` entry's `activity_id` (decision 7).
- Evidence cannot state an edge yet: an `EvidenceRow` carries one classification slot and a `raw_value`,
  with no room for a step or a parent. The shape of relationship evidence, and the per-dataset
  lineage map that fills it, are not designed here; #577 (split from #356) designs them with the first
  evidence-stated edge (`anvil_activity`).
- **Done (#580):** each activity's output and input roles (decision 5), and what each role passes
  (decision 8), are declared once, in `rules/activities.yaml`, whose shape is the LinkML class
  `ActivityDeclarations`; `meta_disco.activities` reads it through the generated pydantic model, so it is
  checked as it loads, and its readers trust it; `INHERITED_FIELDS` and the index producer's code rule read the
  `IndexActivity` entry.
- **Done (#571):** an inherited claim (decision 8) carries the step it crossed — `activity`, the input
  `parent_role` and the parents' record keys, `parent_keys` — so the parents a declaration is credited to
  are on the record. The values a mixed one stands for are not: they are on the parents' own records,
  which those keys join to.
- **Done (#571):** mixed is a `claim_state_enum` value, `mixed`: a claim with no value and no status, and
  the one state that takes part in resolution, as 4.9 says. Alone or beside another mixed declaration it
  leaves the slot `not_classified`; against a value or `not_applicable` from any other declaration — the
  child's own, or another role's inherited one — the slot is `conflict`.
- **Done (#571):** `credited_to_enum` and `reconcile.SLOT_CATEGORIES` gain `inherited`, so the report counts
  an inherited fill apart from every source (contract 6.10). A child against its parent takes the existing
  conflict kinds, and the conflict listing names `derivation_inheritance` with what it declared, `mixed`
  included; the report's `inheritance` block counts what each role gave. Edge conflicts are listed by #577.
- An `edges.jsonl` row is its own class, not a `GeneratedBy`: its child is a record key or an
  `EntityIdentifier`, because a `SampleCollectionActivity`'s child, a sample, and `isBiologicalChildOf`'s, a donor, have no record to sit on; its parent carries the
  same fields as an `ActivityInput`'s — `parent_key`, `parent_file`, `parent_ref`, or `parent_id` — and its
  provenance `source_type` plus `source` and `rule_id` for evidence or `rule_id` alone for inference, with `parent_scope` worked out (decision 6).
- `parent_kind_enum` gains `reference` and `assembly` if #358 and #360 need them; decided there.

## Open

- **What input evidence edges are built from.** Reconcile builds them (decision 6, settled), but no
  evidence shape carries an edge yet (schema changes, above). #577 designs it.
- **Inheritance needs the parent settled first.** Parents and children are in different producer files
  (the CRAM in one, its VCF in another) and chains are deeper than one step (FASTQ → CRAM → VCF → `.tbi`),
  so sorting ~700K records by edge would break reconcile's one-file-at-a-time streaming. I think a lookup
  table fits instead: one read of the files builds, per record key, the record's own settled answer for
  each carried dimension and its parents' keys; a file's final answer is then its own reconciled with its
  parents' final answers, looked up recursively to any depth (a `.bai`, then its BAM, then the BAM's
  FASTQs, which have none), each remembered once worked out and a cycle refused; then the files are
  written in their current order. Deciding `internal` for an evidence-stated parent needs each dataset's
  record keys and names; the pass reconcile's join already makes over the records can collect them. Built
  that way by #571 (`reconcile_inherit`): a first pass keeps each record's settled answer and each child's
  step, parents settle before children, and a second pass writes every file in its order.
- **A parent in `conflict`.** 4.4–4.5 reconcile declarations, and a conflict declares no value. Decided by
  #571, which folded in #413: it passes nothing, so the conflict is listed on the parent and not repeated
  on its companions (contract 4.9).
- **Sources that name different parent sets for a role that takes many.** A caller header naming `{A}` and a
  submitter table naming `{B}` pool to `{A, B}`, which could hide a wrong edge; but sources are often
  partial (a header lists a subset), so differing sets are not a conflict. The consistency check (#362)
  flags an activity whose sources' sets do not overlap.
- **Two builds under one `reference_assembly` value.** A `ReferenceBuild` is an object whose `version` is
  free text, so 4.4's value agreement does not say whether two GRCh38 builds with different patches
  conflict, or how their details merge. Until that is defined, an inherited build rides along as
  detail where the parents agree on it, is dropped where they do not (decision 8), and the slot
  reconciles on its value alone.
- **HPRC's sheets name working outputs, not released assemblies.** Their outputs are `/private/groups/...`
  paths; tying one to a released `*_hprc_r2_v1.0.1.fa.gz` by sample and haplotype assumes the release came
  from that run. Until that is established, an `AssemblyActivity` edge's child is only an output that resolves
  to a held file, and the released assemblies have no such edge.
- **A sample a file's own header names.** `@RG SM` on 80% of BAM headers and VCF sample columns on 99.9%
  of VCF headers (Context) say which sample the data is about. That is not a step, so it is not a
  `SequenceActivity` edge on the BAM or the VCF; whether it is an edge of its own or a field of the record
  is #357's.
- **`external` covers two cases** — never deposited, and ambiguous by name. If a consumer needs them apart,
  a reason field on the edge would do it.
