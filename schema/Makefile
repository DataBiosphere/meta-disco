# Makefile for meta-disco schema validation component

# The canonical schema is package data of the root meta_disco package; this
# tooling project references it from there (issue #164).
SCHEMA = ../src/meta_disco/schema/classification.yaml
GEN_DIR = generated

# Regenerate JSON Schema + Pydantic from the canonical LinkML schema.
# These artifacts are gitignored — they are build outputs, not source.
gen:
	mkdir -p $(GEN_DIR)
	uv run gen-json-schema $(SCHEMA) > $(GEN_DIR)/classification.schema.json.tmp && mv $(GEN_DIR)/classification.schema.json.tmp $(GEN_DIR)/classification.schema.json
	uv run gen-pydantic $(SCHEMA) > $(GEN_DIR)/classification_model.py.tmp && mv $(GEN_DIR)/classification_model.py.tmp $(GEN_DIR)/classification_model.py
	@echo "Generated $(GEN_DIR)/classification.schema.json and classification_model.py"

validate:
	if [ -z "$(INSTANCE)" ]; then \
		echo "Usage: make validate INSTANCE=path/to/file.yaml"; \
		exit 1; \
	fi
	uv run python scripts/validate_outputs.py $(INSTANCE) $(SCHEMA)

test:
	uv run pytest tests/
