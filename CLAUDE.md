# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Meta-disco extracts and validates metadata from biological data files (BAM, CRAM, FASTQ, etc.) for the AnVIL Explorer and Terra Data Repository. It infers eight dimensions — `data_modality`, `data_type`, `reference_assembly`, `assay_type`, `platform`, `instrument_model`, `variant_kind`, `variant_origin` — from filenames, extensions, and file headers (BAM/SAM `@SQ`/`@RG`, VCF `##contig`, FASTQ read names, FASTA/GFA content, IDAT chip type and scanner), using a deterministic tiered rule engine.

## Architecture

The project has two main components:

1. **Classification** (`src/meta_disco/`, `src/meta_disco/rules/unified_rules.yaml`): the tiered rule engine that classifies files. Rules are declared in YAML and executed by `rule_engine.py`; content-based classifiers in `header_classifier.py` inspect fetched headers. `ClassifyPipeline` (`pipeline.py`) fetches, classifies, and writes output for each file type in `file_types.py`. This is what every classification runs through.

2. **Schema** (`schema/` directory): LinkML-based schema and validation of the classification output.
   - `src/meta_disco/schema/classification.yaml`: LinkML schema defining the `ClassificationRecord` (the eight metadata dimensions nested under `classifications`, each a `{value, status, evidence}` entry) and the controlled vocabulary
   - `scripts/validate_outputs.py`: Validates YAML instances against the schema
   - Uses uv for dependency management (Python 3.10+); its own env, separate from the runtime

> The classification `data_modality`/`reference_assembly` inference was originally
> LLM-based (Ollama); that path has been removed in favor of the rule engine.

## Commands

### Schema Validation (run from `schema/` directory)

```bash
# Setup (its own uv env — keeps linkml out of the runtime)
uv sync

# Validate a metadata file
make validate INSTANCE=path/to/metadata.yaml
# or
uv run python scripts/validate_outputs.py path/to/metadata.yaml

# Run tests
make test
# or
uv run pytest tests/
```

### Classification (run from root directory)

```bash
# Derive a deployment's input (#500). DEPLOYMENT names the deployment, `prod` (the
# default) or `dev`, each declared in src/meta_disco/deployments.py with its Azul
# service, catalog, TDR snapshots and its own root, data/anvil/<deployment>/.
# INPUT_SOURCE names how the records are derived: `azul-compact` (the default,
# today's behaviour), `azul-verbatim` (the verbatim manifest only), or `tdr-direct`
# (the snapshots read in place from BigQuery, nothing downloaded; it syncs the `tdr`
# extra in and takes its identity from the environment, see Environment below). An
# unknown value of either fails before any request, query or write.
make download
make download DEPLOYMENT=dev INPUT_SOURCE=azul-verbatim

# Validate a derived input against the input contract (issue #161), the deployment's
# own by DEPLOYMENT. Non-zero exit + grouped summary on any shape violation. `make
# classify` runs it on prod's input first (#376), so a long run cannot start on a
# corpus that violates the contract; run it directly to check a download before
# committing.
make validate-metadata

# Full pipeline over all file types, in parallel, then reconciled with the source
# evidence into <run>/reconciled/ (#432). Reads prod's input: a run is not given a
# deployment, or its own output and cache roots, until #480.
make classify

# One file type (network required for header fetches)
make classify-bam        # or classify-vcf / classify-fastq / classify-fasta / classify-gfa

# Reconcile a stored run again (RUN_DIR=, default the latest), then render its
# reconcile_report.json as docs/reconcile-report.md + docs/reconcile-dashboard.html (#395)
make reconcile
make reconcile-report

# Every rule that classifies a file (the YAML rules, the rules written in Python and
# the translation rows), each with its basis and how often it fired in a reconciled
# run (RUN_DIR=, default the latest), and the caller table's rows (#658), to
# docs/rules-report.md + docs/rules-dashboard.html (#572)
make rules-report

# What a run could not classify, and why: excluded (no checksum), contract
# violations, unreadable content (issue #376); RUN_DIR=, default the latest
make unprocessable-report

# Tests and lint
make test
make lint

# Donors' facts from the submitter tables and AnVIL's anvil_donor (#693, #582, #699), samples'
# from AnVIL's anvil_biosample (#699), and AnVIL's donor and biosample ids (#669): check the entity map against the manifests, or
# import it as entity evidence under data/entity_evidence/; `make reconcile` settles each
# donor from it and lists each AnVIL id on the record it ties to
make check-entity-map
make import-anvil-entities

# SGDP's donors for ANVIL_T2T_CHRY's SGDP genomes (#559), from SGDP's metadata file (network)
make import-sgdp-entities

# Probe a TDR snapshot in place in BigQuery (#498): list its tables, COUNT(*)
# each, stream one and time it. Syncs the `tdr` extra in for the run; identity
# is the environment's, see Environment below.
make probe-tdr PROJECT=<tdr data project> SNAPSHOT=<snapshot name>
```

## Schema Details

The LinkML schema (`classification.yaml`) defines the `ClassificationRecord` — the
eight metadata dimensions nested under `classifications`, each a `{value, status,
evidence}` entry — plus the controlled vocabulary:
- **reference_assembly_enum**: NCBI's assembly names as an `is_a` hierarchy (#473):
  GRCh37, GRCh38, and CHM13 (any release, or release unknown) above
  T2T-CHM13v1.0/v1.1/v2.0 and the three grafted-chrY hybrids under their release;
  and rhesus macaque's `Mmul_10` and marmoset's `mCalJa1.2.pat.X` (#636)
- **data_modality_enum**: AnVIL FSS's recommended values, the Broad's MODAL tree, as dotted
  paths with `is_a` and MODAL ids (#563): genomic, transcriptomic, epigenomic, imaging,
  proteomic, metabolomic, microbiome and their children
- **classification_status_enum**: classified, not_applicable, not_classified, conflict
- **instrument_model_enum**: ENA/SRA's instrument-model strings for the platforms in
  `platform_enum`, with EFO ids as `meaning` where EFO has the same model (#532), and our own
  term for an array scanner, which SRA does not list (`Illumina iScan`, #603)
- **assay_type_enum**: EFO's assay terms as an `is_a` tree, each term's ontology id as `meaning`
  (#533): EFO's, except `Histology`'s, which is OBI's `histological assay` as EFO imports it; a
  term of our own (`snATAC-seq`) has no id and sits under the EFO term it narrows; the two
  array assays (`Methylation array`, `Genotyping array`) are EFO terms with no parent among the values
- **data_type_enum**: dotted terms with `is_a` to the term before the last dot (#607),
  e.g. `annotations.coverage` under `annotations`; a callset's kind and origin are
  `variant_kind` and `variant_origin`, not `variants` subterms (ADR-0003, #657), and
  `variants.gvcf` is the one format term left in the tree until a format slot exists
- **variant_kind_enum**: `small` and `structural`, the one dimension whose value is a list
  (`models.MULTIVALUED_FIELDS`, ADR-0003, #654): a claim declares one kind, a string, and
  the record stores the settled value as `["small"]` (`models.stored_value` /
  `settled_value`); read from the caller a VCF's header names, or a GenomicsDB workspace's
  `vcfheader.vcf` (#678) (`variant_kinds`, `rules/callers.yaml`)
- **variant_origin_enum**: `germline` and `somatic`, Sequence Ontology's two children of
  `variant_origin` (#658); read from the same caller (`variant_origins`, found by `callers`),
  a caller with a somatic mode (Sniffles2) only where its command line shows the mode off
- **identifier_namespace_enum**: who issued a sample or donor identifier (#357, #693): `coriell`,
  `giab`, `sra_sample`, `biosample`, `igvf`, `dataset_local`, and SGDP's `sgdp` and CEPH-HGDP's `hgdp` (#559); which strings each recognises, and
  whether they name a sample, a donor or both (`names`), is `rules/sample_namespaces.yaml`'s
- **phenotypic_sex_enum** and **genetic_ancestry_enum**: a donor's slots (#693), AnVIL's
  `Female`/`Male` (PATO `meaning`s) and 1000 Genomes' population codes as a HANCESTRO `is_a`
  tree (`GBR` under `EUR`), on a `DonorRecord`, never on a file
- **organism_type_enum**, **reported_ethnicity_enum** and **biosample_type_enum** (#699): AnVIL's
  values for its donors' and biosamples' fields (`Human`/`Mouse` with NCBITaxon `meaning`s; the census
  categories, with none; `Tissue`), on a `DonorRecord` or `SampleRecord`
- also **platform_enum**

`status` is required on every dimension; `value` is null unless status is `classified`.

## Design Principles

- **Accuracy over efficiency**: Always prefer reading actual file content (headers, indices, range requests) over guessing from filenames. If there is an exact method to determine a classification — even if it requires downloading headers or running compute — use it.
- **Accuracy over coverage**: It is better to leave a file as `not_classified` than to guess wrong. Only classify when evidence supports it.
- **No identity, no classification**: a record with no well-formed `file_md5sum`
  cannot be fetched (the content URL is built from it) or cached (the evidence
  cache is keyed by it), so it is *excluded* from classification rather than
  written as a row echoing a null md5 — such a row has no usable identity and
  would collide with any other in `corpus_diff` (#376). Exclusion happens once,
  at the shared load path (`pipeline.load_classifiable_records`), so every
  producer inherits it — and that same load writes the run's
  `excluded_files.json`, so excluding a record and naming it are one act, down
  to a standalone `make classify-bam`. `make unprocessable-report` lists them
  individually. This is not the retired `dropped` concept (#155) — nothing goes
  unrecorded.
- **No speculation as fact**: Never confidently assert something unless you actually know it. If inferring or guessing, say "I think" or "it could be". This applies to root cause analysis, data interpretation, and codebase history.
- **Claims, evidence and reconciliation live in `docs/claims-contract.md`**, not here.
  It is the authority on who makes a claim, what an importer may do, how sources
  reconcile, and what the pipeline's stages are. Cite it by assertion number (`3.4`,
  `6.9`) rather than restating it — restating is the drift it exists to stop.
  **Read its "What is not true yet" section before building against it.** Much of it
  describes a target state. The evidence file (#401, amended by #421), the slot map
  (#369), the translation table (#414) and the reconcile stage (#432, which absorbed
  read-sources) exist; inference reads neither the evidence nor the table, reconcile
  reads both. Curator rules (#397) do not exist yet. Its Open section lists what is
  still undecided. Epic #391 tracks the work.

- **What the code does today, which the contract does not replace:**
  - `rule_engine.make_claim` (or `add_claim`, which wraps it) is the single
    construction site for a claim, and enforces its invariants: exactly one of
    `value` / `status` / `state`, a `tier` only where one belongs, and a producer
    handle. An **inherited claim** (`derivation_inheritance`) is built through it too, at
    reconcile (`reconcile_inherit`, #571): it names the `activity`, `parent_role` and
    `parent_keys` it crossed, carries no tier, and is the only claim that may declare the
    state `mixed`. The index producer's two hand-built paths (#413) are gone: it no longer
    copies a parent's answer, and a declined index's markers are notes (`rule_id` and
    `reason`, declaring nothing), as a fetch failure's are.
  - Every claim carries a `source_type`, stated explicitly from the `SOURCE_*`
    constants. Never derive it from `tier`, which cannot tell `contig_detection`
    from `content_read`. Rule claims are the one derived case and key off `scope`.
  - `CONTENT_TIER` (4, in `rule_engine.py`) is for claims derived from reading file
    bytes. Give any content-read claim `tier=CONTENT_TIER`, never a hard-coded
    number (#226). Tiers 1–3 are the rule tiers declared in `unified_rules.yaml`.
  - **A rule written in Python is declared once, in `code_rules.CODE_RULES`** (#572),
    with what it reads, what it sets and its rationale; a marker that carries a
    `rule_id` is in `code_rules.MARKERS`. A call site names it through its constant
    (`rule_id=code_rules.VCF_CONTIG_LENGTH.id`), never a string: `test_code_rules`
    fails on a rule id written as a string literal (a `rule_id=` keyword, an evidence
    dict's `rule_id`, or a `*_RULE_ID` constant) anywhere else in `src/` or `scripts/`.
  - Evidence files under `data/source_evidence/<source>/` are NDJSON, written and
    read through `source_evidence.write_evidence_file` / `iter_evidence` and never
    with a whole-file `json.load` — the corpus is millions of records (#374). An
    import is a **generation** (#369): `<source>/<version>/<dataset>/<generation>/`,
    written once and never over an earlier one; `discover` returns the newest per
    dataset. The AnVIL importer is `anvil_evidence`, driven by a slot map: the
    submitter tables' `sources/anvil_slot_map.yaml` (`make check-slot-map` /
    `make import-anvil-evidence`, under `anvil/`) and the published columns'
    `sources/anvil_published_slot_map.yaml` (`make check-published-map` /
    `make import-anvil-published`, under `anvil_published/`, #497). A map's top-level
    `source_type` is the label its evidence carries and decides its directory
    (`anvil_evidence.EVIDENCE_DIRS`). Line 1 is the envelope, naming both sides of the
    join and the source's kind (`source_type`, one of `IMPORTER_SOURCE_TYPES` less the lineage-only kinds, constant
    for the file. `wrangler_annotation` is deliberately not among them: a curator
    enters as rules, not as evidence, per contract 1.6/1.7). The envelope's shape lives
    in the LinkML schema (`EvidenceFileEnvelope` and its two parts in
    `classification.yaml`) and reaches the runtime as the generated pydantic model
    `schema/classification_model.py` (#494) — regenerated by `make -C schema gen`,
    committed, and held to the schema by the drift test. `source_evidence` imports
    those classes as they are; the one rule the generator drops (a `file_name` key
    needs a target dataset) is a function there, not a subclass.
  - **Lineage evidence** (#583) is a second kind of evidence file: the same envelope, but each
    line a `LineageRow` (a child, its parent — a DRS URI, `file_id` or sample id, with the source's
    own identifier kept where the importer looked the locator up — and the source's `raw_activity`),
    written by `lineage_evidence` under its **own root**, `data/lineage_evidence/`, because every
    reader of `data/source_evidence/` takes each file there as slot lines. The importer is
    `anvil_lineage`, driven by `sources/anvil_lineage_map.yaml` (`make check-lineage-map` /
    `make import-anvil-lineage`). A line declares no activity or role (#584 translates) and the
    parent is not resolved (#577 does). `repository_activity` (`anvil_activity`) is an importer kind
    written only as lineage (`models.LINEAGE_ONLY_SOURCE_TYPES`); a slot evidence file refuses it.
  - **ENA's run records** (#606) are the one external (`external_ground_truth`) slot evidence:
    `ena_evidence` (`make import-ena-evidence`, network) looks up the files named as ENA names
    its generated FASTQs (`ERR…_1.fastq.gz`) and writes a file's `library_strategy`,
    `library_source`, `instrument_platform` and `instrument_model`, keyed by `file_id`, under
    `data/source_evidence/ena/`, only where the md5 confirms the file is ENA's (contract 2.10).
    ENA's response is kept beside each generation (`read_run.response.json`, not evidence), and
    `--response` re-imports from it offline.
  - **ENA run lineage** (#594) is the one place a lineage parent may be in another dataset
    (ADR-0002 decision 2): `sources/ena_run_lineage_map.yaml`, declared and checked in
    `run_lineage_map`, imported by `ena_lineage` (`make import-ena-lineage`, network), which
    links T2T_CHRY's 1KGP CRAMs to their ENA run's FASTQs in ANVIL_T2T by read and base
    counts (contract 2.10). Reconcile resolves a line's `parent_dataset` only where
    `RunLineageMap.declares` says so, writes it on the input, and counts any other `undeclared_dataset`.
  - **A file the catalog lacks may be held outside AnVIL for one dataset, as a workaround** (#710, contract
    2.11, until AnVIL holds it, #624): `sources/external_files.yaml` declares ANVIL_T2T_CHRY's published
    1000 Genomes sample maps, pinned by commit and sha256, read through `external_files`;
    `make fetch-external-files` keeps them under `data/external/<dataset>/` (dataset first), refusing a
    download whose sha256 differs (a changed cached copy is downloaded again, and read refused until it is). `external_lineage` (`make import-external-lineage`, network) links a workspace tar to the
    map its header names only where the tar's own `callset.json` lists exactly the map's samples, writing
    lineage under `data/lineage_evidence/external/` (`parent_key_type: external_file`). Reconcile
    (`reconcile_external`) holds each named map under its address, builds its members and samples from
    the cached copy (no lineage line names a map's members), and the
    tar's input names it by `parent_ref` (no `parent_key`); the maps are written to
    `reconciled/external_lists.ndjson.gz`. Read an input's parent through `edges.parent_node`, never
    `["parent_key"]` alone.
  - **Every repository has exactly one published source** (contract 7.12), declared in
    `record_keys.PUBLISHED_TABLES` beside the record keys, each repository's own entry in
    its module (`azul_manifest.PUBLISHED_TABLE`); `anvil_evidence.check` holds both maps to it
    and the run's preflight refuses evidence that contradicts it
    (`source_evidence.require_one_published_source`).
  - **A line is an observation, not a claim** (#421, contract 1.1): `EvidenceEntry`
    is `(field, target_key_value, raw_value, source)`. An importer writes no `value`,
    `status`, `claim_state`, `rule_id` or `tier` — each is refused by name — and
    `raw_value` is transcribed verbatim and checked only for being a string. The
    vocabulary check on a *mapped* value belongs to the translation table (`value_map`,
    #414), which checks an authored row's terms when it loads. Do not reintroduce one here.
  - **The value translation table** is `rules/value_map.yaml`, loaded and applied by
    `value_map.py` (#414; the row is contract 3.9, matching 3.5, seeded/authored 3.11,
    scope 3.12, the queue 5.2). A row without a `reason` is seeded and declares nothing.
    Row ids are `<slot>.<slug>`, and no rule id contains a dot, which is what keeps the
    two apart. `make seed-value-map` appends seeded rows and never rewrites one;
    `make review-queue` writes the unauthored values, grouped by source type, to
    `docs/review-queue-report.md` and `docs/review-queue.html` (#524). `claims_from` builds a line's
    claims through `make_claim`; reconcile is its one caller in a run.
  - **The activity translation table** is `rules/activity_map.yaml`, loaded by `activity_map.py`
    (#584): a lineage line's step, as an activity of `activities.yaml` and the role its parent takes.
    A row's `match` names `source_type` and any of the line's other parts (`table`, `raw_activity`,
    the child and parent columns, and the raw `data_type` the same table's slot evidence gives the
    child and the parent), each exact, `null`, or a list; **no two rows may match one line**, so
    authoring a row that covers seeded keys means deleting those seeded rows, or the table will not load. It shares its YAML walk and
    append-only seeding with `value_map` (`yaml_rows`). `make seed-activity-map` seeds it and
    `make review-queue` lists its unauthored rows; reconcile applies it (#577), and no classification run reads it.
  - `run_all_classifications` calls `report_evidence_files` and never `iter_evidence`,
    so no evidence reaches inference and a run with evidence files present writes the
    same inference output as one without.
  - **Every classification file records its own provenance** (#404), in
    `metadata.provenance` (`provenance.run_provenance`, required by
    `RunMetadata.from_counts`): its input (path, `repository`, `catalog`,
    `downloaded_at`), when it started, and the code's `version`, `commit` and `dirty`
    flag (tracked files only), `null` where unknown. Per file, not per run, because
    `make classify-bam RUN_DIR=…` rewrites one file of a stored run. Reconcile refuses an
    input whose `repository` or `catalog` differs from what a run file records, and
    writes `classified_by` (each distinct code identity with its files) and
    `reconciled_by` into its envelope and report.
  - **The reconcile stage** is `reconcile.py` (`make reconcile`, #432): it reads a stored
    run plus the evidence and writes `<run>/reconciled/` — one gzip-compressed NDJSON
    file (`.ndjson.gz`, #554) per inference file, envelope on line 1, plus
    `reconcile_report.json` — and never touches the inference output (contract 6.3),
    which stays JSON at the run root. Which evidence applies comes from the input
    envelope's `repository`, and its `catalog` where it names one (HPRC never will).
    `resolve_slot` is the whole resolution rule and
    `use_for` the per-slot `use` indicator (`meta_disco` | `published`) the indexer
    reads; per-input outcomes (match, harmonized, disagreed, unreviewed, no_claim, silent) are
    computed in the report and never stored on a record. The per-slot attribution is
    stored on the record, as `credited_to` (`reconcile.credited_to`, contract 6.10, #552). `corpus_diff` must be told
    which artifact it compares (`--artifact inference|reconciled`).
  - **Reconcile builds each file's step from the lineage too** (#577, `reconcile_lineage`): the
    lineage files of the run's catalog, translated through the activity map, each child and file
    parent resolved within the child's dataset by `file_id` / `drs_uri` (or in the dataset a
    declared ENA run lineage line names, #594), and merged with
    inference's own step by `edges.merge_steps` into the reconciled `generated_by`. A lineage
    source is cited by its activity-map row id and a `ClaimSource`. An unresolved parent gives no
    input and a conflict (two activities; two parents in a role that takes one; in any role, other
    parents than inference names there, #609; a generic `Activity` beside a specific one naming another
    parent) gives no
    `generated_by`; both are counted in the report's `lineage` block, never written on a record. A
    sample parent gives no input (no issue yet). A file whose only steps are generic gets none, counted as
    `generic_only`. The inference artifact's `generated_by` is never changed.
  - **Reconcile carries each parent's answer across that step** (#571, contract 4.9,
    `reconcile_inherit`): for each input role and each dimension its activity passes, the
    parents settle, first match wins (a parent not in the run → nothing; any mixed parent, or
    two that do not nest → `mixed`, whatever the rest are; then any `conflict` or
    `not_classified` → nothing; else their value) and give the child one inherited claim, resolved with its
    own by `reconcile.settle`, the one resolution rule. Parents settle before children (a
    cycle is refused), so the run is read twice after the join's own scan. A slot filled only by inheritance is
    credited `inherited`; the report's `inheritance` block counts what each role gave. With
    `--no-evidence` it still crosses the steps inference wrote (6.6). Inference itself
    inherits nothing: an index's carried dimensions are `not_classified` there. A checksum's are
    `not_applicable`, and `ChecksumActivity` passes nothing (#596).
  - **No output record carries what a repository publishes** (#513). The `published`
    block (#424) and `make published-comparison` are deleted: the published values are
    input kind 2, written by the published importer as evidence (contract 7.1, 7.12,
    #497), which the reconcile stage reads and reconciles with inference (#432). The
    input path no longer
    copies AnVIL's two published columns onto a record; an input file written before
    that still carries them, and the input model ignores them (`extra="ignore"`). Do not
    add a per-record copy back: a published value no authored row maps is listed by
    `make review-queue`, not carried on a record.
  - The **catalog identity** — `entry_id`, `file_id`, `drs_uri` — is one set with one
    name, `records.CATALOG_IDENTITY_FIELDS`, reached through `records.identity_from`
    (`coerce=True` for the `unmatched_files` diagnostic, which echoes a drifted value the
    way `excluded_files.json` does). Drive a producer's identity keys from it rather than
    spelling the three; #433 had to add two fields to seven hand-written copies, which is
    what the tuple exists to prevent a third time. `entry_id` is regenerated when the
    catalog is re-indexed and the other two are not, which is why a consumer joins on
    `file_id` — the schema's slot descriptions carry that, not the tuple. Since #499
    `entry_id` is optional on the input: absent from a record derived from a snapshot,
    and null on that record's output row. The input gate's samples name a record by
    the source's record key (`record_keys.key_field`), not by `entry_id`; the reports that
    echo the catalog identity (`excluded_files.json`, the unprocessable report) still
    carry `entry_id` as one of its three columns.
  - **The input is a TDR snapshot's tables, however they arrived** (#499). The one
    canonical shape is `snapshot_input.SnapshotTables` — table names, one table's rows
    streamed, TDR's column names — with two readers behind it: `TdrDirect` (BigQuery in
    place through `meta_disco.tdr`; identity and the `tdr` extra per that module's
    docstring) and `AzulVerbatim` (the verbatim manifest on disk, Azul's additions
    stripped; needs nothing, and is the stand-in and parity oracle, not the target).
    `derive_records` is AnVIL's: it reads `anvil_file` and `anvil_dataset` and refuses a
    snapshot lacking either before yielding a record. The compact path
    (`record_from_compact_manifest_row`) stands beside it unchanged, and every envelope
    `metadata_block` writes names how its records were derived in `input_source`
    (`azul_manifest.INPUT_SOURCES`), stated by the writer and never inferred — the HPRC
    builder writes its own envelope and prod's file on disk predates the field. The
    downloader chooses the reader from `INPUT_SOURCE` and writes the kind it ran with
    (#500); no classification run reads the field.
  - **A deployment is declared once**, in `deployments.DEPLOYMENTS` (#500): its Azul
    service, catalog, input root (`data/anvil/<deployment>/`) and each dataset's TDR
    snapshot. Its datasets are exactly the declared ones — the downloader skips a
    catalog dataset it does not declare — and the declaration is checked, not
    consulted: a compact manifest naming another snapshot than the declared one refuses
    the download. The envelope names the `deployment`, its `catalog` for every kind of
    input, and per dataset `tdr_project` and `snapshot`. Only the input is the
    deployment's: output and the header cache stay prod's paths until #480/#479. Each
    dataset's `dataset_id` is declared too, and a manifest is requested by it, not by
    title (#717); every record an Azul manifest gives must carry the declared title and id
    (`tdr-direct` reads the declared snapshot itself, and checks the title in `derive_records`). The row-count check
    is what refuses a short manifest: on 2026-10-21 two title filters returned manifests
    Azul had stored days earlier, missing files.
  - **The input carries each file's storage path**, `file_path` (#717): an optional slot
    of the input contract, read from `anvil_file.file_path` by every input source (Azul
    added it to both manifests by 2026-10-17; HPRC records have none). Its one use is a
    parent several files of the dataset carry by name: `edges.matches` keeps the one in
    the child's own folder, for every name lookup inference makes (index, checksum, header
    and cohort steps; reconcile's external sample maps have no path). It makes no claim, and no output record carries it.
  - **Every producer builds `records.OutputRecord`** (#450) — the pipeline through
    `from_work_item`, the four standalone producers through `from_record`. A per-record
    field added there reaches all fourteen outputs; one wired into a producer does not.
    That is why the per-producer sweeps for the catalog identity (#433), and formerly
    for the `published` block (#424, deleted by #513), are gone: `test_output_shape`
    pins the record's key set across all fourteen instead.
    Add a new standalone producer to `STANDALONE_PRODUCERS` in `tests/producer_sweep`
    and that test picks it up.
  - **Output records carry no `dataset_id`** (#450). It is an input-contract slot and
    stays on the index producer's `unmatched_files` diagnostic, but it is not a slot of
    `ClassificationRecord` and no reader of a run wants it: consumers group on
    `dataset_title` and join on `file_id`. Do not add it back to a record.
  - **`generated_by` is the one step that made a file, written only where a parent
    resolves** (#450, #356, #580, ADR-0002): an `activity` (a term of `activity_type_enum`,
    AnVIL FSS's activity types, never a verb) and its `inputs`, each in a `role` the
    activity declares. What each role passes is `rules/activities.yaml`'s to say, read
    through `meta_disco.activities` and trusted by its readers; a term may take its
    declaration from an abstract parent, and no step names an abstract term (#610). Inference
    states six of `code_rules.EDGE_RULES`'s seven (the seventh is reconcile's, an external sample map's
    members, #710): two from the child's own name through
    `meta_disco.edges`, the index producer's `IndexActivity` and the catch-all's
    `ChecksumActivity` for a `.md5`, two from a VCF's header through
    `meta_disco.producer_steps` (#609, #610): the end of the header's data flow (ADR-0002
    decision 6), a `HaplotypeCaller` giving `VariantCallActivity` (an input name several
    alignments carry settled, on a GATK 4 line, by which one's `@SQ` contigs all fit the VCF's `##contig`s, read
    from the BAM producer's cache or with samtools into it on a miss, #620) and a bcftools `concat`
    giving `MergeActivity` with every input VCF a `shard`, and two of T2T's joint-calling
    cohort through `meta_disco.cohort_steps` (#621): a GATK sample-name map's rows giving
    `CohortDefinitionActivity` with every listed gVCF a `member` (the `sample_map` producer),
    and a GenomicsDB workspace tar's own `vcfheader.vcf` giving `CohortMergeActivity` with the
    map its one `input_list`, whose values reconcile reads **through** the map's members
    (`read_through` in `activities.yaml`, contract 4.9); the tar fetcher keeps that member's
    text in the tar's cache entry (`TarEvidence.vcf_header`), and for the workspaces
    `header_classifier.CALLSET_FOLDERS` declares (ANVIL_T2T_CHRY's SGDP cohort, #724) its `callset.json`
    too (`TarEvidence.callset`).
    Their outcomes per dataset are in each producer's `metadata.details.producer_steps`.
    **A VCF's command lines are read once, on first use, by `VCFHeader.commands`** (#615),
    which gives each line's words and its step, through `validators.command_lines` and its
    `TOOL_ARGUMENTS` (an undeclared tool is an unread step, never a guess). Its readers
    (`producer_steps`, `reference_builds`) inspect that and never split command-line text, and
    the pipeline parses each VCF header once for both the classifier and the step reader
    (`FileTypeConfig.parser`). An
    input carries `parent_file`, `parent_key` (the parent's record key, never its md5),
    `parent_kind`, and `named_by`, every source that named it (the step has its own). A parent no file or
    two files of the dataset carry gives none. Steps the source tables state are built at
    reconcile (#577), and reconcile inherits across every step (#571).
  - **`samples` names whose data a file holds, as a pointer to one of the run's sample
    lists** (#357, ADR-0002 decision 1): `{list_id, count, named_by}`, the list a digest of
    its sorted members, each an `EntityIdentifier`. A string is a sample only through
    `rules/sample_namespaces.yaml` (`sample_identity`), which also declares the one rewrite
    (`GM` → `NA`, same number); a string no rule recognises is counted, never guessed.
    Inference reads it from the file's own content, a header, a sample map's rows, a nanopore
    FAST5's `sample_id` (`fast5`, #605: found by name in the first 64 KiB, its attribute
    message parsed whole) or an SGDP workspace tar's `callset.json` (#724; each tar not read is
    counted by cause, `unread_samples`) (`FileTypeConfig.samples`, its readers among `code_rules.SAMPLE_RULES`), all of its strings or none, and each producer file holds its lists under
    `sample_lists`. A submitter table states it through the slot map, one cell per column
    (`samples` is the one non-dimension in `models.EVIDENCE_FIELDS`, never translated by the
    value map), and `make check-slot-map` refuses a column whose files' names mostly name
    another sample. Reconcile (`reconcile_samples`) settles the two by the step rule:
    agreeing sources are each listed, different samples give none, counted as a conflict or
    as incomparable; a file name is a check, never a source. It writes
    `reconciled/sample_lists.ndjson.gz`. A derived file takes its parent's samples across a step whose
    role declares `passes_samples` in `rules/activities.yaml` (index, checksum, QC report, coverage track,
    cohort merge from its sample map, whose own rows name its samples), as one more source credited
    `samples_inherited_from_parent` (#668, contract 4.9); across any other step the child keeps its own and a
    disagreeing pair is counted in the report's samples block.
  - **Donors and samples are records keyed by their identifier** (#693, ADR-0002 decision 1 as
    amended): reconcile (`reconcile_entities`) writes `reconciled/donors.ndjson.gz`, a
    `DonorRecord` per donor with `phenotypic_sex`, `genetic_ancestry` and more (`models.DONOR_FIELDS`)
    settled by `reconcile.settle` (now in `resolution`, re-exported), and
    `reconciled/samples.ndjson.gz`, a `SampleRecord` per sample a reconciled file names or an
    AnVIL biosample ties to, with its `collected_from` donor where an identifier rule naming both
    a sample and a donor says so (`IdentifierRuleSet.collected_from`). A donor's slots come from **entity evidence**,
    `data/entity_evidence/` (`entity_evidence`), its own root because every reader of
    `data/source_evidence/` reads each file there as a file's slot lines: lines
    (`EntityEvidenceRow`) keyed by the identifier as the source wrote it (`target_key:
    entity_identifier`, which a slot or lineage file refuses), recognised as a donor or, for a
    sample's slot or id, a sample at reconcile, never at import. The importer is `anvil_entities`, driven by
    `sources/anvil_entity_map.yaml` (`make check-entity-map` / `make import-anvil-entities`):
    per table the identifier column and each slot's columns (none, for a table AnVIL's
    biosamples are made from), and per kind AnVIL's published `anvil_donor` and
    `anvil_biosample`, each record attached to an identifier through its
    `source_datarepo_row_ids`. **AnVIL's own `donor_id` and `biosample_id`** (#669), the same in
    prod anvil15 and dev's 1000G snapshot (#692) and often several per person, are lines of their own
    (`models.REPOSITORY_ID_FIELDS`), never translated: reconcile lists each on the one record
    it ties to, as `repository_ids` (many to one), and refuses one tying to two records. The value
    map translates a file's, a donor's and a sample's slots (`models.TRANSLATED_FIELDS`), a row
    declaring only slots of the kind it matches (`models.KIND_OF_SLOT`), and its seeding and review queue read the entity root beside the slot
    root. **A donor's family** (#582, `models.FAMILY_FIELDS`) is `mother`, `father` and `family_id`,
    settled the same way but never translated: a parent string is recognised as a donor through
    `rules/sample_namespaces.yaml` and its claim declares the parent's `EntityIdentifier` (the one
    claim value that is not a string), citing that identifier rule; PED's `0` makes no claim and is
    counted; a family id is taken as written (`code_rules.FAMILY_ID_AS_WRITTEN`, an `ENTITY_RULES`
    entry). Every parent named gets a donor record. **AnVIL's own donor and biosample records** (#699) are
    a source for each field they fill: a donor's `organism_type` and `reported_ethnicity`, translated, and
    a sample's `biosample_type`, translated, and `anatomical_site`, as written (`models.SAMPLE_SLOTS`),
    settled on the `SampleRecord`. Every donor and sample slot carries `use` (`resolution.use_for`, which
    `reconcile` re-exports); `published` means show what the repository publishes, which is in the
    slot's evidence where AnVIL has a value (no AnVIL field holds a family).
    **ANVIL_T2T_CHRY's SGDP genomes** (#559) get their donors from SGDP's own metadata file,
    `sgdp_entities` (`make import-sgdp-entities`, network, sha256-pinned, a generation under
    `data/entity_evidence/sgdp/`), written only for a sample whose SGDP sex and T2T_CHRY karyotype agree
    (275 of 279; the rest are #718), each line cited to its source: T2T_CHRY's tables' pairing as
    `repository_metadata`, SGDP's facts as `external_ground_truth`. Its links are the two **identity
    links** (`models.IDENTITY_LINK_FIELDS`): `collected_from` names a sample's donor, beside the
    identifier rule's link, and `same_donor_as` names another identifier for a donor, followed to the end
    of its chain, so the record is keyed by `coriell:HG01504` or `hgdp:HGDP01163` and lists SGDP's own
    `sgdp:S_Spanish-2` under `synonyms`.
    No donor value is copied onto a file record.
  - **A producer is declared once**, in `producers.PRODUCERS` — the fourteen writers of a
    run's `*_classifications.json` files. Add one there, never to a second list:
    `build_parallel_jobs` and `output_utils.CLASSIFICATION_FILES` are derived from it,
    and the three hand-maintained lists they replaced are what let a registered type
    never run (#151).
  - **A source's record key is declared once**, in `record_keys.SOURCE_RECORD_KEYS`, keyed by the
    input envelope's `repository` and read through `record_keys.record_key` (#446). It is
    the field the source guarantees unique per file, in both spellings a run uses: AnVIL's
    is `file_id` (durable across a re-index, #433; not `entry_id`, not `file_name`), HPRC's
    is `file_md5sum` / `md5sum`, a hash of the file's URL that the HPRC builder writes
    because its catalogs issue no identifier — no catalog identity is minted for an HPRC
    record. None of its readers may hard-code a field; they include the input gate
    (`scripts/validate_metadata.py`, which also names its sample records by it through
    `record_keys.key_field`), the catch-all producer's skip set
    (`scripts/classify_remaining_files.py`), an edge's `parent_key` (`edges.generated_by`,
    written by the index producer and the catch-all; the index producer joined parent rows
    on it until #571 took the copy away, #486), the post-run one-row-per-file check (#445)
    and reconcile. The catch-all reads another producer's rows through `record_keys.keyed_rows`
    and compares every input record against them through `record_keys.input_key_value`, and an
    edge grounds its parent through the same function; both raise on a missing key rather
    than skip. An envelope naming no repository is refused before a run starts.
  - **Ask `Producer.claims`; never write a second routing predicate.** A file has one
    owner because one function says so — the name decides and `file_format` is only a
    fallback, for reasons `route`'s docstring gives. Four hand-written predicates are
    what let two producers claim one file and a run write it twice (#445).

## Surprises

You may encounter an environment, tool, dependency, or constraint that the
user never mentioned and that changes your approach. Examples: an unexpected
conda environment, a missing credential, a second uv project. When that
happens, STOP and ask before proceeding. Do not work around the surprise
silently.

## Git Discipline

- **Never amend commits.** Use a separate commit for each fix round.
  Amending rewrites commits a reviewer already read, which loses the
  review context. This is the behavior to avoid; adding commits is how
  review history stays intact.
- **Never force push `main`.**
- **On a feature branch, prefer adding commits over force pushing**, so
  review history is preserved. Force pushing is allowed only for the
  structural rebase a stacked pull request needs: when the branch it was
  based on merges, rebase onto the new `main` and push with
  `--force-with-lease`. A rebase does rewrite commit SHAs, so re-request
  review afterward if the branch was already reviewed. The reason it is
  allowed and amending is not: it replays the same reviewed changes onto a
  new base, rather than altering the content of a commit that is under
  review.

## Code Change Discipline

- **After any rename/move**: grep the entire codebase for all references to the old name — imports, comments, docs, Makefile targets, YAML, tests. Do not assume you found them all by hand.
- **After changing a function signature or rule ID**: grep for all callers/references before committing.
- **After changing function behavior**: verify the docstring still matches — especially guard conditions, side effects, return values, and mutation behavior.
- **After changing output format**: check all consumers — summary printers, tests, downstream scripts.

## Docstring & Comment Accuracy

Docstrings and comments are claims about behavior and MUST be literally true and
precisely scoped — verify each against the code before committing. This is a
review gate: `/simplify` and `/code-review` must check docstrings/comments for
these, and flag any that overclaim.

- **No overclaiming scope/coverage**: do not say "every"/"all"/"any" when the code covers a subset (e.g. a check that only iterates `CLASSIFICATION_FIELDS` is not "every emitted field"). State the actual scope.
- **No false absolutes**: do not say "byte-identical" for a semantic dict compare, or "deterministic / no network" unless the code guarantees it. Describe the real mechanism.
- **No speculation as fact** (see Design Principles): if a comment asserts what a code path does, confirm it actually does that on the inputs in question.
- **Prefer precise over tidy**: a longer accurate sentence beats a clean wrong one. Re-read every docstring/comment you touched against the final code.

## Environment

- Classification (root): Python 3.10+, `pyproject.toml`; runtime deps `pyyaml`, `requests`, `pydantic`; dev `pytest`, `ruff`, `pyright`
- The `tdr` extra (`uv sync --extra tdr`) adds `google-cloud-bigquery` for reading a TDR
  snapshot in place (`meta_disco.tdr`, #498); the package imports and `make test` runs
  without it. **Identity is the environment's, never meta-disco's**: the module docstring
  of `meta_disco.tdr` is the authority on how, and is cited rather than restated.
- Schema (`schema/`): a separate uv project (Python 3.10+) with linkml/linkml-validator; kept out of the runtime env
