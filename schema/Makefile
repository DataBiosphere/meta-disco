# Makefile for meta-disco schema validation component

validate:
	if [ -z "$(INSTANCE)" ]; then \
		echo "Usage: make validate INSTANCE=path/to/file.yaml"; \
		exit 1; \
	fi
	poetry run python scripts/validate_outputs.py $(INSTANCE)

test:
	poetry run pytest tests/test_validation.py

generate:
	poetry run linkml generate python src/meta_disco/schema/anvil_file.yaml > src/meta_disco/models/anvil_models.py
	
