# Makefile for meta-disco schema validation component

SCHEMA = src/meta_disco/schema/classification.yaml
GEN_DIR = generated

# Regenerate JSON Schema + Pydantic from the canonical LinkML schema.
# These artifacts are gitignored — they are build outputs, not source.
gen:
	mkdir -p $(GEN_DIR)
	poetry run gen-json-schema $(SCHEMA) > $(GEN_DIR)/classification.schema.json
	poetry run gen-pydantic $(SCHEMA) > $(GEN_DIR)/classification_model.py
	@echo "Generated $(GEN_DIR)/classification.schema.json and classification_model.py"

validate:
	if [ -z "$(INSTANCE)" ]; then \
		echo "Usage: make validate INSTANCE=path/to/file.yaml"; \
		exit 1; \
	fi
	poetry run python scripts/validate_outputs.py $(INSTANCE)

test:
	poetry run pytest tests/test_validation.py
