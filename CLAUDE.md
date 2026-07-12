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

## Team roster

| Name   | GitHub handle |
|--------|---------------|
| Dave   | NoopDog       |
| Fran   | frano-m       |
| Hunter | hunterckx     |
| Mim    | MillenniumFalconMechanic |

"Assign to Fran" always means the GitHub handle in this table. Never guess a
handle. If someone is not in this table, ask.

## Error handling philosophy

Validate at trust boundaries only, and trust everything inside them.

- The trust boundaries are: user input, network responses, file contents,
  environment variables, CLI arguments, and data crossing a public API.
  Validate at the boundary, once, and fail with a clear error that names
  what was wrong.
- Inside the boundary, where our functions call our functions, do not check
  for null, missing, or wrong-typed values. A caller passing bad input is a
  bug in the caller, so let the code throw. A stack trace at the real call
  site is what enables the fix. A defensive fallback hides the bug.
- Never silently coerce, default, or catch-and-continue to "handle" bad
  input, and never rewrite a caller's input for backward compatibility. The
  removal of the `classification_rules.yaml` legacy redirect (#169, #170)
  is the model: update callers or fail loudly, do not add a silent shim.
- When a reviewer suggests defensive handling of internal inputs, decline
  and cite this section.

## Workflow

1. Create a GitHub issue for every change, with a definition-of-done
   checklist. The issue is the record the result is checked against.
2. Create a feature branch `noopdog/{issue#}-short-description`.
3. Implement with tests. Run `make test-all` before committing. It is the
   root-level aggregator that runs both the root suite and the schema
   suite. Plain `make test` runs the root suite only, so it is not
   sufficient before pushing.
4. When the code is complete, announce it and run `/cc:auto-review`. That
   skill runs the local reviews, has you triage the findings, stops at a
   push gate, opens the PR, and drives the Copilot feedback rounds to
   merge-ready. It is the canonical definition of the review and PR cycle;
   do not hand-run those steps here.

A human reads the PR against the issue's definition of done and merges it.
Claude never merges.

## Surprises

You may encounter an environment, tool, dependency, or constraint that the
user never mentioned and that changes your approach. Examples: an unexpected
conda environment, a missing credential, a second uv project. When that
happens, STOP and ask before proceeding. Do not work around the surprise
silently.

## Communication

- Do not use analogies or metaphors.
- Lead with the outcome in one sentence.
- Keep status updates to one line.
- Flag your assumptions explicitly.

## GitHub API discipline

- Never enumerate a full project board, and never paginate more than two
  pages to find one item.
- Never fetch issues or pull requests in a loop. Use a single search or
  list call with filters instead.
- If you get a rate-limit response, STOP and tell the user. Do not retry.

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
