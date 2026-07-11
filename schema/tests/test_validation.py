# tests/test_validation.py

import os
import subprocess
import sys

_VALIDATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts/validate_outputs.py",
)
_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")


def _run(instance):
    # sys.executable (the current schema-env interpreter, which has linkml) rather
    # than `uv run` — keeps the test hermetic and off an external uv binary, and
    # avoids nesting a uv invocation inside the uv run that already launched pytest.
    return subprocess.run(
        [sys.executable, _VALIDATE, os.path.join(_DATA, instance)],
        capture_output=True, text=True,
    )


def test_valid_file():
    result = _run("valid_file.yaml")
    assert "✅" in result.stdout and "INVALID" not in result.stdout


def test_invalid_file():
    result = _run("invalid_file.yaml")
    assert "INVALID" in result.stdout
