# tests/test_metadata_model_drift.py
#
# The runtime imports src/meta_disco/schema/metadata_model.py to validate input
# records (issue #161). It is generated from metadata.yaml via `make gen-metadata`
# and committed. This guards it from drifting out of sync with its source schema —
# the same protection tests/test_rule_vocabulary.py gives the rule/schema pair.

import os
import subprocess
import sys

_SCHEMA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The path `make gen-metadata` passes to gen-pydantic, verbatim, so the embedded
# `source_file` line in the output matches the committed file byte-for-byte.
_REL_SCHEMA = "../src/meta_disco/schema/metadata.yaml"
_COMMITTED_MODEL = os.path.join(
    _SCHEMA_ROOT, "..", "src", "meta_disco", "schema", "metadata_model.py"
)


# The gen-pydantic console script from the same venv as the test interpreter (the
# schema env, which has linkml) — hermetic, and exactly what `make gen-metadata` runs.
_GEN_PYDANTIC = os.path.join(os.path.dirname(sys.executable), "gen-pydantic")


def test_committed_model_matches_schema():
    # Run from the schema/ dir with the same relative path `make gen-metadata` uses,
    # so the regenerated text (including the embedded source_file) is comparable
    # byte-for-byte.
    result = subprocess.run(
        [_GEN_PYDANTIC, _REL_SCHEMA],
        cwd=_SCHEMA_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    with open(_COMMITTED_MODEL) as f:
        committed = f.read()
    # Byte-for-byte: the comparison is reproducible because schema/uv.lock pins the
    # linkml version (the generated header carries linkml's metamodel_version). If a
    # linkml bump changes the generated text, regenerate and commit — that is a real,
    # intended update to the shipped model, not a false positive.
    assert result.stdout == committed, (
        "src/meta_disco/schema/metadata_model.py is out of sync with metadata.yaml — "
        "run `make -C schema gen-metadata` and commit the result."
    )
