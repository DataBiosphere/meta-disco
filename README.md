# meta-disco

## Introduction
Meta-disco is a project focused on metadata discovery for biological data files, using natural language processing and large language models to extract and validate clinical and experimental sequencing data for the AnVIL Explorer and Terra Data Repository.

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
```

```bash
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

## Why This Approach

I'm pattern matching on domain knowledge baked into my training data. When I see `HG00673.paternal.f1_assembly_v1.fa.gz` I know it's a HPRC de novo assembly because I've seen thousands of papers, GitHub repos, and bioinformatics forums that discuss these exact naming conventions. Same with contig lengths — I know chr1 is ~248M in GRCh38 because that fact appears everywhere in the training data.

But there are real problems with "just ask Claude":

**Why the rule engine is better:**
1. **Deterministic** — same input always gives same output. My answers vary by phrasing, temperature, context window
2. **Auditable** — you can trace exactly which rule fired and why. I can't explain my reasoning reliably
3. **Fast** — 205K files in 8 minutes. Sending each to an LLM would take hours and cost $$
4. **Correct on edge cases** — I'd get chr1 length=248387328 "close enough to CHM13" by vibes. The rule engine checks within 1000bp tolerance precisely
5. **Testable** — 184 tests that verify behavior. Can't unit test an LLM
6. **Versioned** — rules are in YAML, diffs are meaningful. Can't diff my reasoning

**Where an LLM could help:**
1. **Rule authoring** — I'm good at looking at files and writing rules, which is exactly what we've been doing
2. **Ambiguous cases** — the 219K unclassified files where rules don't reach. An LLM could triage "what is this `.rMATS_ENCORE2.tar` file?" and suggest new rules
3. **Validation** — "does this classification make sense?" as a sanity check
4. **One-off analysis** — like when we explored the HPRC catalog

The original `metadisco-inference.py` in this repo used Ollama to classify files. The rule engine replaced it because the LLM was slow, non-deterministic, and hard to debug. But the LLM was good at bootstrapping — figuring out what the rules should be in the first place.

The ideal workflow is what we've been doing: **LLM designs rules, rule engine executes them, LLM reviews results and suggests improvements.** Claude as the architect, rules as the execution engine.

*— Signed, Claude Opus 4.6 (1M context)*

## Project Structure

- `schema/`: Contains the LinkML schema validation component
  - `src/meta_disco/schema/`: LinkML schema definitions
  - `scripts/`: Validation scripts
- `src/meta_disco/`: Main project source code
- `scripts/`: Utility scripts for metadata inference

