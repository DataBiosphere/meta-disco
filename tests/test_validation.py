# tests/test_validation.py

import subprocess

def test_valid_file():
    result = subprocess.run(
        ["poetry", "run", "python", "scripts/validate_outputs.py", "tests/test_data/valid_file.yaml"],
        capture_output=True, text=True
    )
    assert "VALID" in result.stdout

def test_invalid_file():
    result = subprocess.run(
        ["poetry", "run", "python", "scripts/validate_outputs.py", "tests/test_data/invalid_file.yaml"],
        capture_output=True, text=True
    )
    assert "INVALID" in result.stdout
