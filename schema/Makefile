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
# The two Pydantic models are committed and imported by the runtime — the
# input-record model by the validator in metadata_schema.py (#161), the
# classification model by source_evidence.py for the evidence-file envelope (#494)
# — unlike the JSON Schema below, which is a build output.
METADATA_MODEL = ../src/meta_disco/schema/metadata_model.py
CLASSIFICATION_MODEL = ../src/meta_disco/schema/classification_model.py
GEN_DIR = generated

# Regenerate JSON Schema + Pydantic from the canonical LinkML schema. The JSON
# Schema is gitignored; the Pydantic model is committed (#494), and
# tests/test_model_drift.py fails when it lags the schema.
gen:
	mkdir -p $(GEN_DIR)
	uv run gen-json-schema $(SCHEMA) > $(GEN_DIR)/classification.schema.json.tmp && mv $(GEN_DIR)/classification.schema.json.tmp $(GEN_DIR)/classification.schema.json
	uv run gen-pydantic $(SCHEMA) > $(CLASSIFICATION_MODEL).tmp && mv $(CLASSIFICATION_MODEL).tmp $(CLASSIFICATION_MODEL)
	@echo "Generated $(GEN_DIR)/classification.schema.json and $(CLASSIFICATION_MODEL)"

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
