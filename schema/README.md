# Meta-Disco Schema Validation

This directory contains the LinkML schema validation component for the Meta-Disco project.

## Overview

The schema validation component is responsible for validating metadata extracted by the LLM component against the LinkML schema defined in `src/meta_disco/schema/anvil_file.yaml`.

## Setup

To set up the schema validation component:

1. Make sure Poetry is installed on your system
2. Run the setup script:

```bash
./setup.sh
```

## Usage

You can use the provided Makefile to run common tasks:

### Validating Metadata

To validate a metadata file against the schema:

```bash
# Using the Makefile (IMPORTANT: use the INSTANCE= syntax)
make validate INSTANCE=path/to/metadata.yaml

# Example with test data
make validate INSTANCE=tests/test_data/valid_file.yaml

# Or directly with Poetry
poetry run python scripts/validate_outputs.py path/to/metadata.yaml
```

### Running Tests

To run the validation tests:

```bash
# Using the Makefile
make test

# Or directly with Poetry
poetry run pytest tests/test_validation.py
```

## Directory Structure

- `src/meta_disco/schema/` - Contains the LinkML schema definitions
- `scripts/` - Contains validation scripts
- `tests/` - Test files and test data

## Dependencies

This component uses Poetry for dependency management and requires Python 3.10 or later. The main dependencies are:

- linkml-runtime
- linkml-validator
- linkml
- pyyaml
