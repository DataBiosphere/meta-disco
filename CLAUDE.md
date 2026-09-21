# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Meta-disco extracts and validates metadata from biological data files (BAM, CRAM, FASTQ, etc.) for the AnVIL Explorer and Terra Data Repository. It infers five dimensions — `data_modality`, `data_type`, `reference_assembly`, `assay_type`, `platform` — from filenames, extensions, and file headers (BAM/SAM `@SQ`/`@RG`, VCF `##contig`, FASTQ read names, FASTA/GFA content), using a deterministic tiered rule engine.

## Architecture

The project has two main components:

1. **Classification** (`src/meta_disco/`, `src/meta_disco/rules/unified_rules.yaml`): the tiered rule engine that classifies files. Rules are declared in YAML and executed by `rule_engine.py`; content-based classifiers in `header_classifier.py` inspect fetched headers. `ClassifyPipeline` (`pipeline.py`) fetches, classifies, and writes output for each file type in `file_types.py`. This is what every classification runs through.

2. **Schema** (`schema/` directory): LinkML-based schema and validation of the classification output.
   - `src/meta_disco/schema/classification.yaml`: LinkML schema defining the `ClassificationRecord` (the five metadata dimensions nested under `classifications`, each a `{value, status, evidence}` entry) and the controlled vocabulary
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
# Validate a freshly downloaded metadata file against the input contract (issue
# #161). Non-zero exit + grouped summary on any shape violation. `make classify`
# runs it as a prerequisite (#376), so a long run cannot start on a corpus that
# violates the contract; run it directly to check a download before committing.
make validate-metadata

# Full pipeline over all file types, in parallel
make classify

# One file type (network required for header fetches)
make classify-bam        # or classify-vcf / classify-fastq / classify-fasta / classify-gfa

# What a run could not classify, and why: excluded (no checksum), contract
# violations, unreadable content (issue #376)
make unprocessable-report

# Tests and lint
make test
make lint
```

## Schema Details

The LinkML schema (`classification.yaml`) defines the `ClassificationRecord` — the
five metadata dimensions nested under `classifications`, each a `{value, status,
evidence}` entry — plus the controlled vocabulary:
- **reference_assembly_enum**: GRCh37, GRCh38, CHM13
- **data_modality_enum**: genomic, transcriptomic.*, epigenomic.*, imaging.histology
- **classification_status_enum**: classified, not_applicable, not_classified, conflict
- also **data_type_enum**, **assay_type_enum**, **platform_enum**

`status` is required on every dimension; `value` is null unless status is `classified`.

## Design Principles

- **Accuracy over efficiency**: Always prefer reading actual file content (headers, indices, range requests) over guessing from filenames. If there is an exact method to determine a classification — even if it requires downloading headers or running compute — use it.
- **Accuracy over coverage**: It is better to leave a file as `not_classified` than to guess wrong. Only classify when evidence supports it.
- **No identity, no classification**: a record with no well-formed `file_md5sum`
  cannot be fetched (the content URL is built from it) or cached (the evidence
  cache is keyed by it), so it is *excluded* from classification rather than
  written as a row echoing a null md5 — such a row has no usable identity and
  would collide with any other in `corpus_diff` (#376). Exclusion happens once,
  at the shared load path (`pipeline.load_classifiable_snapshot`), so every
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
  describes a target state: the read-sources and reconcile stages do not exist yet.
  The evidence file (#401, amended by #421), the slot map (#369) and the translation
  table (#414) do, and no classification run reads the evidence or the table. Its Open
  section lists what is still undecided. Epic #391 tracks the work.

- **What the code does today, which the contract does not replace:**
  - `rule_engine.make_claim` (or `add_claim`, which wraps it) is the single
    construction site for a claim, and enforces its invariants: exactly one of
    `value` / `status` / `state`, a `tier` only where one belongs, and a producer
    handle. `classify_index_files` holds the two paths outside it, both hand-building
    evidence for the same reason — an index file has exactly one claim per dimension and
    never reaches `evaluate_claims`, so there is no tier to carry, and `inherited_evidence`
    additionally copies a parent's resolved `conflict`, which `make_claim` refuses.
    `inherited_evidence` serves a matched index; `declined_record` serves one this
    producer took no parent for (#438). Both are known violations of the contract's 1.1,
    tracked as #413, which should fold them in together.
  - Every claim carries a `source_type`, stated explicitly from the `SOURCE_*`
    constants. Never derive it from `tier`, which cannot tell `contig_detection`
    from `content_read`. Rule claims are the one derived case and key off `scope`.
  - `CONTENT_TIER` (4, in `rule_engine.py`) is for claims derived from reading file
    bytes. Give any content-read claim `tier=CONTENT_TIER`, never a hard-coded
    number (#226). Tiers 1–3 are the rule tiers declared in `unified_rules.yaml`.
  - Evidence files under `data/source_evidence/<source>/` are NDJSON, written and
    read through `source_evidence.write_evidence_file` / `iter_evidence` and never
    with a whole-file `json.load` — the corpus is millions of records (#374). An
    import is a **generation** (#369): `<source>/<version>/<dataset>/<generation>/`,
    written once and never over an earlier one; `discover` returns the newest per
    dataset. The AnVIL importer is `anvil_evidence`, driven by the slot map in
    `sources/anvil_slot_map.yaml` (`slot_map` loads it; `make check-slot-map`
    checks it against the manifests; `make import-anvil-evidence` writes). Line 1
    is the envelope, naming both sides of the join and the source's kind
    (`source_type`, one of `IMPORTER_SOURCE_TYPES`, constant for the file — the two
    kinds an importer may write. `wrangler_annotation` is deliberately not among
    them: a curator enters as rules, not as evidence, per contract 1.6/1.7).
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
    `make review-queue` lists the unauthored values. `claims_from` builds a line's
    claims through `make_claim` for reconcile (#432) — nothing in a run calls it.
  - `run_all_classifications` calls `report_evidence_files` and never `iter_evidence`,
    so no evidence reaches classification and a run with evidence files present
    produces the same output as one without. Currency is not decidable offline;
    recording which catalog a run enhances is #404, and is not built.
  - Published values (contract section 7, built by #424) live in each output record's
    `published` block — what the repository publishes for that file today, beside what
    the run inferred. `records.build_published` is its single construction site, reached
    through `OutputRecord` either way: `from_work_item` off the pipeline's typed work
    item, `from_record` off a standalone producer's raw dict. Both drive the field list
    from `PUBLISHED_FIELDS`, so no call site can read a stale subset. The two fields are
    deliberately absent from the input contract (`schema/metadata.yaml`) — they are not
    input. Contract 7.7 — every producer writes the block — is structural since #450,
    pinned for all eleven by `RECORD_KEYS`. What structure cannot pin is that a producer
    passed `source`, and 7.11 makes that the field that matters: no recommendation names
    a publisher, only `source` does. Omitting it writes `"source": null` with no error
    anywhere, so `test_a_standalone_producer_passes_the_source_through` asserts it per
    producer and `test_the_pipeline_carries_the_catalog_into_a_written_record` covers
    the pipeline.
    `make published-comparison` renders the report. It is the *only* comparison against
    a repository's own values, having replaced `generate_validation_report`'s
    `compare_anvil` (#424), whose two value maps are #414's seed. Its vocabulary is
    repository-neutral on purpose (contract 7.11): `add` / `keep` / `review` / `none`
    name what a data team should do, never who publishes.
  - The **catalog identity** — `entry_id`, `file_id`, `drs_uri` — is one set with one
    name, `records.CATALOG_IDENTITY_FIELDS`, reached through `records.identity_from`
    (`coerce=True` for the `unmatched_files` diagnostic, which echoes a drifted value the
    way `excluded_files.json` does). Drive a producer's identity keys from it rather than
    spelling the three; #433 had to add two fields to seven hand-written copies, which is
    what the tuple exists to prevent a third time. `entry_id` is regenerated when the
    catalog is re-indexed and the other two are not, which is why a consumer joins on
    `file_id` — the schema's slot descriptions carry that, not the tuple.
  - **Every producer builds `records.OutputRecord`** (#450) — the pipeline through
    `from_work_item`, the four standalone producers through `from_record`. A per-record
    field added there reaches all eleven outputs; one wired into a producer does not.
    That is why the two sweeps `published` (#424) and the catalog identity (#433) needed
    are gone: `test_output_shape` pins the record's key set across all eleven instead.
    Add a new standalone producer to `STANDALONE_PRODUCERS` in `tests/producer_sweep`
    and that test picks it up.
  - **Output records carry no `dataset_id`** (#450). It is an input-contract slot and
    stays on the index producer's `unmatched_files` diagnostic, but it is not a slot of
    `ClassificationRecord` and no reader of a run wants it: consumers group on
    `dataset_title` and join on `file_id`. Do not add it back to a record.
  - **`derived_from` is the index producer's typed edge** (#450): `relation` is always
    `index_of` and required, the grounding (`parent_file` / `parent_md5sum`) is null
    where #438 took no parent, and `parent_kind` comes from the matched parent's
    extension — or, with no parent, from what `INDEX_TO_PARENT` declares when those
    agree. No other producer emits an edge; widening it is #371.
  - **A producer is declared once**, in `producers.PRODUCERS` — the eleven writers of a
    run's `*_classifications.json` files. Add one there, never to a second list:
    `build_parallel_jobs` and `output_utils.CLASSIFICATION_FILES` are derived from it,
    and the three hand-maintained lists they replaced are what let a registered type
    never run (#151).
  - **A source's record key is declared once**, in `pipeline.SOURCE_RECORD_KEYS`, keyed by the
    input envelope's `repository` and read through `pipeline.record_key` (#446). It is
    the field the source guarantees unique per file, in both spellings a run uses: AnVIL's
    is `file_id` (durable across a re-index, #433; not `entry_id`, not `file_name`), HPRC's
    is `file_md5sum` / `md5sum`, a hash of the file's URL that the HPRC builder writes
    because its catalogs issue no identifier — no catalog identity is minted for an HPRC
    record. Four readers use it and none may hard-code a field: the input gate
    (`scripts/validate_metadata.py`), the catch-all producer's skip set
    (`scripts/classify_remaining_files.py`), the index producer's parent join
    (`scripts/classify_index_files.py`, #486) and the post-run one-row-per-file check
    (#445). The two producers read another producer's rows through `pipeline.keyed_rows`
    and the input record each compares against those rows — every record for the
    catch-all, the matched parent for the index producer — through
    `pipeline.input_key_value`; both raise on a missing key rather than skip. An
    envelope naming no repository is refused before a run starts.
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

- Classification (root): Python 3.10+, `pyproject.toml`; runtime deps `pyyaml`, `requests`; dev `pytest`, `ruff`
- Schema (`schema/`): a separate uv project (Python 3.10+) with linkml/linkml-validator; kept out of the runtime env
