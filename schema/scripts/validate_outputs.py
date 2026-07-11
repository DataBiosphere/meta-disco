# scripts/validate_outputs.py

import logging
import os
import sys

import yaml
from linkml.validator import Validator
from linkml.validator.plugins.pydantic_validation_plugin import PydanticValidationPlugin

logging.basicConfig(level=logging.ERROR)

def validate_instance(instance_file: str, schema_file: str) -> bool:
    try:
        if not os.path.exists(instance_file):
            print(f"File not found: {instance_file}")
            return False

        # Load the YAML file contents first
        try:
            with open(instance_file, 'r') as f:
                instance_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"❌ {instance_file}: INVALID (YAML parsing error)")
            print(f"  - Error: {e}")
            return False

        validator = Validator(
            schema=schema_file,
            validation_plugins=[PydanticValidationPlugin(closed=False)]
        )

        # Validate the loaded data, not the file path
        report = validator.validate(instance_data)

        # Check if validation passed (no errors in results)
        if not report.results:
            print(f"✅ {instance_file}: VALID")
            return True
        else:
            print(f"❌ {instance_file}: INVALID")
            for result in report.results:
                print(f"  - {result.severity}: {result.message}")
            return False

    except Exception as e:
        logging.error(f"Exception during validation of {instance_file}", exc_info=True)
        print(f"❌ {instance_file}: INVALID (Exception during validation)")
        print(f"  - Error: {e}")
        return False

def main():
    # Validate whole records against the classification model (ClassificationRecord
    # is its tree_root). Ran against the legacy anvil_file.yaml stub until #134.
    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_outputs.py <instance_file> [schema_file]")
        sys.exit(1)

    instance_path = sys.argv[1]
    # The caller supplies the schema path (the Makefile passes $(SCHEMA), the one
    # source of truth). Default for a bare CLI run: the schema is package data of
    # the root meta_disco package (../../src from schema/scripts/).
    if len(sys.argv) >= 3:
        schema_path = sys.argv[2]
    else:
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        schema_path = os.path.join(repo_root, "src/meta_disco/schema/classification.yaml")

    result = validate_instance(instance_path, schema_path)
    sys.exit(0 if result else 1)  # Exit with 0 (success) or 1 (failure)

if __name__ == "__main__":
    main()
