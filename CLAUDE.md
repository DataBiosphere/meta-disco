# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Meta-disco extracts and validates metadata from biological data files (BAM, CRAM, FASTQ, etc.) for the AnVIL Explorer and Terra Data Repository. It uses LLMs to infer `data_modality` (genomic/transcriptomic) and `reference_genome` (GRCh38/GRCh37/CHM13) from filenames and BAM/SAM headers.

## Architecture

The project has two main components:

1. **LLM Inference** (root directory): Uses Ollama to run local LLMs for metadata extraction
   - `metadisco-inference.py`: Main inference script that queries Ollama's `/api/chat` endpoint
   - `anvil-harmonizer/modelfiles/`: Custom Ollama Modelfiles with domain-specific system prompts
   - Expects Ollama running on `localhost:11434`

2. **Schema Validation** (`schema/` directory): LinkML-based validation of extracted metadata
   - `src/meta_disco/schema/anvil_file.yaml`: LinkML schema defining File class with required `reference_assembly` and `data_modality` fields
   - `scripts/validate_outputs.py`: Validates YAML instances against the schema
   - Uses Poetry for dependency management (Python 3.10+)

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

### LLM Inference (run from root directory)

```bash
# Requires Conda environment and Ollama running
python metadisco-inference.py <row_index> <model_name> <output_tsv_path>
```

## Schema Details

The LinkML schema (`anvil_file.yaml`) defines:
- **reference_assembly_enum**: GRCh37, GRCh38, CHM13
- **data_modality_enum**: genomic, transcriptomic
- Both fields are required on the `File` class

## Design Principles

- **Accuracy over efficiency**: Always prefer reading actual file content (headers, indices, range requests) over guessing from filenames. If there is an exact method to determine a classification — even if it requires downloading headers or running compute — use it.
- **Accuracy over coverage**: It is better to leave a file as `not_classified` than to guess wrong. Only classify when evidence supports it.
- **No speculation as fact**: Never confidently assert something unless you actually know it. If inferring or guessing, say "I think" or "it could be". This applies to root cause analysis, data interpretation, and codebase history.

## Environment

- LLM component: Conda (`environment.yaml`) with Python 3.8, pandas, requests
- Schema component: Poetry with Python 3.10+, linkml, linkml-validator
