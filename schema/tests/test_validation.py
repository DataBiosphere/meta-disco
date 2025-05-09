# tests/test_validation.py

import subprocess
import os

def test_valid_file():
    # Get the directory of this test file
    test_dir = os.path.dirname(os.path.abspath(__file__))
    schema_dir = os.path.dirname(test_dir)  # Parent directory of tests
    
    result = subprocess.run(
        ["poetry", "run", "python", os.path.join(schema_dir, "scripts/validate_outputs.py"), 
         os.path.join(test_dir, "test_data/valid_file.yaml")],
        capture_output=True, text=True,
        cwd=schema_dir  # Run from the schema directory
    )
    assert "VALID" in result.stdout

def test_invalid_file():
    # Get the directory of this test file
    test_dir = os.path.dirname(os.path.abspath(__file__))
    schema_dir = os.path.dirname(test_dir)  # Parent directory of tests
    
    result = subprocess.run(
        ["poetry", "run", "python", os.path.join(schema_dir, "scripts/validate_outputs.py"), 
         os.path.join(test_dir, "test_data/invalid_file.yaml")],
        capture_output=True, text=True,
        cwd=schema_dir  # Run from the schema directory
    )
    assert "INVALID" in result.stdout
