# Makefile for meta-disco schema validation component

# This is a separate uv project (its own schema/.venv with linkml, #164). When
# invoked with the root project's venv activated — e.g. `make test-all` from the
# repo root — the inherited VIRTUAL_ENV points at ../.venv and every `uv run`
# below warns that it does not match schema/.venv before ignoring it. Drop it
# from the recipe environment so uv silently resolves this project's own env.
unexport VIRTUAL_ENV

# The canonical schemas are package data of the root meta_disco package; this
# tooling project references them from there (issue #164).
SCHEMA = ../src/meta_disco/schema/classification.yaml
METADATA_SCHEMA = ../src/meta_disco/schema/metadata.yaml
# The input-record Pydantic model is committed and imported by the runtime (the
# validator in metadata_schema.py, issue #161), unlike the output artifacts below.
METADATA_MODEL = ../src/meta_disco/schema/metadata_model.py
GEN_DIR = generated

# Regenerate JSON Schema + Pydantic from the canonical LinkML schema.
# These artifacts are gitignored — they are build outputs, not source.
gen:
	mkdir -p $(GEN_DIR)
	uv run gen-json-schema $(SCHEMA) > $(GEN_DIR)/classification.schema.json.tmp && mv $(GEN_DIR)/classification.schema.json.tmp $(GEN_DIR)/classification.schema.json
	uv run gen-pydantic $(SCHEMA) > $(GEN_DIR)/classification_model.py.tmp && mv $(GEN_DIR)/classification_model.py.tmp $(GEN_DIR)/classification_model.py
	@echo "Generated $(GEN_DIR)/classification.schema.json and classification_model.py"

# Regenerate the input-record Pydantic model from metadata.yaml. Committed (not
# gitignored): the runtime imports it to validate records at load (#161).
gen-metadata:
	uv run gen-pydantic $(METADATA_SCHEMA) > $(METADATA_MODEL).tmp && mv $(METADATA_MODEL).tmp $(METADATA_MODEL)
	@echo "Generated $(METADATA_MODEL)"

validate:
	if [ -z "$(INSTANCE)" ]; then \
		echo "Usage: make validate INSTANCE=path/to/file.yaml"; \
		exit 1; \
	fi
	uv run python scripts/validate_outputs.py $(INSTANCE) $(SCHEMA)

test:
	uv run pytest tests/

lint:
	uv run ruff check scripts/ tests/
