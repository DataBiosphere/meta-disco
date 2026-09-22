# tests/test_validation.py

import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_VALIDATE = _HERE.parent / "scripts" / "validate_outputs.py"
_DATA = _HERE / "test_data"


def _run(instance):
    # sys.executable (the current schema-env interpreter, which has linkml) rather
    # than `uv run` — keeps the test hermetic and off an external uv binary, and
    # avoids nesting a uv invocation inside the uv run that already launched pytest.
    return subprocess.run(
        [sys.executable, _VALIDATE, _DATA / instance],
        capture_output=True, text=True,
    )


def test_valid_file():
    result = _run("valid_file.yaml")
    assert result.returncode == 0, result.stderr
    assert "✅" in result.stdout and "INVALID" not in result.stdout


def test_invalid_file():
    result = _run("invalid_file.yaml")
    # validate_outputs.py exits non-zero on a schema violation; assert that too, so
    # a subprocess that errored before printing can't pass on the substring alone.
    assert result.returncode != 0
    assert "INVALID" in result.stdout
