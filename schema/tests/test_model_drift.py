# tests/test_model_drift.py
#
# The runtime imports two generated Pydantic models and both are committed: the
# input-record model src/meta_disco/schema/metadata_model.py, generated from
# metadata.yaml via `make gen-metadata` to validate input records (issue #161), and
# src/meta_disco/schema/classification_model.py, generated from classification.yaml
# via `make gen` and read by source_evidence.py for the evidence-file envelope
# (#494). This guards each from drifting out of sync with its source schema — the
# same protection tests/test_rule_vocabulary.py gives the rule/schema pair.

import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCHEMA_ROOT = Path(__file__).resolve().parent.parent
_MODELS_DIR = _SCHEMA_ROOT.parent / "src" / "meta_disco" / "schema"

# Each pair is the schema path exactly as the Makefile target passes it to
# gen-pydantic, so the embedded `source_file` line in the output matches the
# committed file byte-for-byte, and the committed model that target writes.
_PAIRS = [
    pytest.param("../src/meta_disco/schema/metadata.yaml", "metadata_model.py", "gen-metadata", id="metadata"),
    pytest.param("../src/meta_disco/schema/classification.yaml", "classification_model.py", "gen", id="classification"),
]


# The gen-pydantic console script from the same venv as the test interpreter (the
# schema env, which has linkml) — hermetic, and exactly what the make targets run.
# On Windows the console script is gen-pydantic.exe.
_GEN_PYDANTIC = Path(sys.executable).parent / ("gen-pydantic.exe" if os.name == "nt" else "gen-pydantic")


@pytest.mark.parametrize("rel_schema, model_name, target", _PAIRS)
def test_committed_model_matches_schema(rel_schema, model_name, target):
    # This needs the schema env's linkml (gen-pydantic). Skip cleanly if run under an
    # interpreter without it (e.g. an explicit `pytest schema/tests` in the root env),
    # so it degrades to a skip rather than a FileNotFoundError.
    if not _GEN_PYDANTIC.is_file():
        pytest.skip("gen-pydantic not found; run under the schema uv env (make test-schema)")
    # Run from the schema/ dir with the same relative path the make target uses,
    # so the regenerated text (including the embedded source_file) is comparable
    # byte-for-byte.
    result = subprocess.run(
        [_GEN_PYDANTIC, rel_schema],
        cwd=_SCHEMA_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    with (_MODELS_DIR / model_name).open() as f:
        committed = f.read()
    # Byte-for-byte: the comparison is reproducible because schema/uv.lock pins the
    # linkml version (the generated header carries linkml's metamodel_version). If a
    # linkml bump changes the generated text, regenerate and commit — that is a real,
    # intended update to the shipped model, not a false positive.
    assert result.stdout == committed, (
        f"src/meta_disco/schema/{model_name} is out of sync with {Path(rel_schema).name} — "
        f"run `make -C schema {target}` and commit the result."
    )
