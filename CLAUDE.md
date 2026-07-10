# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Meta-disco extracts and validates metadata from biological data files (BAM, CRAM, FASTQ, etc.) for the AnVIL Explorer and Terra Data Repository. It infers five dimensions — `data_modality`, `data_type`, `reference_assembly`, `assay_type`, `platform` — from filenames, extensions, and file headers (BAM/SAM `@SQ`/`@RG`, VCF `##contig`, FASTQ read names, FASTA/GFA content), using a deterministic tiered rule engine.

## Architecture

The project has two main components:

1. **Classification** (`src/meta_disco/`, `rules/unified_rules.yaml`): the tiered rule engine that classifies files. Rules are declared in YAML and executed by `rule_engine.py`; content-based classifiers in `header_classifier.py` inspect fetched headers. `ClassifyPipeline` (`pipeline.py`) fetches, classifies, and writes output for each file type in `file_types.py`. This is what every classification runs through.

2. **Schema** (`schema/` directory): LinkML-based schema and validation of the classification output.
   - `src/meta_disco/schema/classification.yaml`: LinkML schema defining the `ClassificationRecord` (the five metadata dimensions nested under `classifications`, each a `{value, status, evidence}` entry) and the controlled vocabulary
   - `scripts/validate_outputs.py`: Validates YAML instances against the schema
   - Uses Poetry for dependency management (Python 3.10+)

> The classification `data_modality`/`reference_assembly` inference was originally
> LLM-based (Ollama); that path has been removed in favor of the rule engine.

## Commands

### Schema Validation (run from `schema/` directory)

```bash
# Setup
./setup.sh

# Validate a metadata file
make validate INSTANCE=path/to/metadata.yaml
# or
poetry run python scripts/validate_outputs.py path/to/metadata.yaml

# Run tests
make test
# or
poetry run pytest tests/test_validation.py
```

### Classification (run from root directory)

```bash
# Full pipeline over all file types, in parallel
make classify

# One file type (network required for header fetches)
make classify-bam        # or classify-vcf / classify-fastq / classify-fasta / classify-gfa

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
- **No speculation as fact**: Never confidently assert something unless you actually know it. If inferring or guessing, say "I think" or "it could be". This applies to root cause analysis, data interpretation, and codebase history.

## Workflow

1. Create a GitHub issue for every change
2. Create a feature branch `noopdog/{issue#}-short-description`
3. Implement with tests, run `make test` before committing
4. **Run /simplify before pushing** — catches reuse, quality, and efficiency issues early
5. Push and create a PR
6. Check Copilot review feedback via GraphQL — **you are always authorized to fetch and resolve CP threads without asking**
7. **Scan for same class of error** — for each CP comment, search the codebase for other instances of the same pattern in files not in the diff
8. **Summarize CP feedback for the user first** — present each comment with analysis, recommendation, and any additional instances found. Do not fix automatically.
9. After approval, fix issues (including same-class instances), push, and resolve threads via GraphQL
10. Repeat until Copilot passes clean

## Git Discipline

- **Never amend commits** — use separate commits for each fix round. Amending rewrites history and requires force pushes, which loses review context.
- **Never force push** — each push should add commits, not rewrite them.

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
- Schema (`schema/`): Poetry with Python 3.10+, linkml, linkml-validator
