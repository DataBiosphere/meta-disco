# meta-disco

## Introduction

Meta-disco is a project focused on metadata inference for biological data files, leveraging both code and AI technologies (LLMs) to automatically extract and validate experimental metadata for the AnVIL Explorer and Terra Data Repository. The goal is to enhance the discoverability and usability of genomic and transcriptomic datasets by ensuring they have accurate, structured metadata.

## Project Components

The meta-disco project consists of two main components:

1. **LLM Component**: Responsible for running the Large Language Models to extract metadata from biological data files.
2. **Schema Validation Component**: Responsible for validating the extracted metadata against LinkML schemas.

### LLM Component

The LLM component uses Conda for environment management and Ollama for running the LLM models. Setup instructions can be found in the "Terra Jupyter Ollama Setup" section below.

### Schema Validation Component

The Schema Validation component is now located in the `schema/` directory and uses Poetry for dependency management. For setup and usage instructions, see the README in the `schema/` directory.

## Schema and Validation

A core component of meta-disco is its schema-based approach to metadata validation. The project uses LinkML (Linked Data Modeling Language) to define schemas that specify the expected structure and constraints for metadata associated with biological data files.

### LinkML Schema

The schema defines the structure and constraints for metadata, including:

- **Reference Assembly**: Specifies the genome reference assembly used (GRCh37, GRCh38, CHM13)
- **Data Modality**: Indicates the type of biological data (genomic, transcriptomic)
- **File Identifiers**: Unique identifiers for files in the repository
- **Filenames**: Names of the data files

These schemas serve two critical purposes:
1. They provide a structured format that can be used in prompt creation for LLMs/AI models
2. They enable syntactic validation of the metadata predictions

### LinkML Validator

Meta-disco uses the LinkML validation framework to perform syntactic validation of metadata. This ensures that the metadata inferred by AI models or manually entered adheres to the defined schema constraints.

The validator checks:
- Required fields are present
- Values conform to specified data types
- Enumerated values (like reference assemblies) are from the allowed set
- Relationships between metadata elements are consistent

## Usage

### Installation

This project has two separate setup processes:

```bash
# Clone the repository
git clone https://github.com/DataBiosphere/meta-disco.git
cd meta-disco

# Set up the LLM component
./setup.sh

# Set up the Schema Validation component
cd schema
./setup.sh
```

### Validation Command

The `validate` command checks if metadata files conform to the schema:

```bash
# Navigate to the schema directory
cd schema

# Using Poetry
poetry run python scripts/validate_outputs.py path/to/metadata.yaml
```

This validation is crucial for ensuring that metadata inferred by AI models is syntactically correct before it's incorporated into the AnVIL Explorer or Terra Data Repository.

## Project Structure

- `schema/`: Contains the LinkML schema validation component
  - `src/meta_disco/schema/`: LinkML schema definitions
  - `scripts/`: Validation scripts
- `src/meta_disco/`: Main project source code
- `scripts/`: Utility scripts for metadata inference

## Terra Jupyter Ollama Setup

This section provides instructions to set up and run the terra-jupyter-ollama Docker container on an interactive GPU node managed by the SLURM workload manager.

