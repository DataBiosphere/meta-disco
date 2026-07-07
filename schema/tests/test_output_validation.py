"""Hard gate: real pipeline output conforms to the status-required schema.

Epic #116 Stage 4a (#122). Stage 0's golden guardrail checked output *shape* and
values-in-vocabulary but deferred full schema validation to here. This validates
each per-field classification entry from the golden output against its
``Classification`` subclass in ``classification.yaml`` — enforcing the Stage 3
contract at the schema level: ``status`` is required and drawn from
``classification_status_enum``, and ``value`` is either null or a member of that
dimension's enum.

Scoped to the per-field *entries* (value/status/confidence/evidence). Validating
the whole record against ``ClassificationRecord`` is deferred: the schema models
the five dimensions at the top level while the pipeline nests them under a
``classifications`` key — that record-shape reconciliation is tracked in #134.

Runs in the schema/ Poetry component, which has linkml installed (the root
component does not).
"""

import json
from pathlib import Path

import pytest
import yaml
from linkml.validator import Validator
from linkml.validator.plugins.pydantic_validation_plugin import PydanticValidationPlugin

# schema/tests/ -> schema/ -> repo root. This gate deliberately validates the
# root component's golden output (the real classifier shape), so it reads across
# the component boundary — it expects a repo checkout, not a standalone install of
# the schema package. test_golden_present fails loudly if the golden is missing.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = Path(__file__).resolve().parents[1] / "src/meta_disco/schema/classification.yaml"
_GOLDEN = _REPO_ROOT / "tests/fixtures/golden/expected_output.json"


def _dimension_classes() -> dict:
    """Map each output dimension to the schema class that constrains its entry.

    Derived from ``ClassificationRecord``'s slot_usage (the single source of
    truth) rather than hardcoded, so a dimension added to the schema's record is
    picked up automatically. (A dimension present in the *output* but absent from
    slot_usage would still not be validated — but that divergence is exactly the
    schema/output record-shape mismatch tracked in #134.)
    """
    schema = yaml.safe_load(_SCHEMA.read_text())
    slot_usage = schema["classes"]["ClassificationRecord"]["slot_usage"]
    return {dim: cfg["range"] for dim, cfg in slot_usage.items()}


DIMENSION_CLASS = _dimension_classes()


@pytest.fixture(scope="session")
def validator():
    # Building a linkml Validator compiles the schema to pydantic models, which is
    # slow — build it once per session and share it across the tests.
    return Validator(
        schema=str(_SCHEMA),
        validation_plugins=[PydanticValidationPlugin(closed=False)],
    )


def _golden_entries():
    """Yield (label, dimension, entry) for every dimension entry in the golden."""
    # Guard here (not just in test_golden_present) so a missing fixture fails with
    # a clear message regardless of test order, never a bare FileNotFoundError.
    assert _GOLDEN.exists(), f"golden fixture not found at {_GOLDEN}"
    data = json.loads(_GOLDEN.read_text())
    for ftype, payload in data.items():
        for i, record in enumerate(payload["classifications"]):
            classifications = record["classifications"]
            for dim in DIMENSION_CLASS:
                yield f"{ftype}[{i}].{dim}", dim, classifications[dim]


def test_golden_present():
    assert _GOLDEN.exists(), f"golden fixture not found at {_GOLDEN}"


def test_output_entries_validate_against_schema(validator):
    failures = []
    checked = 0
    for label, dim, entry in _golden_entries():
        checked += 1
        report = validator.validate(entry, target_class=DIMENSION_CLASS[dim])
        for result in report.results:
            failures.append(f"{label}: {result.severity}: {result.message}")

    assert checked > 0, "no golden entries were validated"
    assert not failures, "Pipeline output violates the classification schema:\n  " + \
        "\n  ".join(failures)


def test_gate_rejects_missing_status(validator):
    # status is required — an entry without it must fail (proves the gate bites).
    bad = {"value": "genomic", "confidence": 1.0, "evidence": []}
    report = validator.validate(bad, target_class="DataModalityClassification")
    assert report.results, "missing status should have failed validation"


def test_gate_rejects_out_of_enum_value(validator):
    bad = {"value": "not_a_real_modality", "status": "classified",
           "confidence": 1.0, "evidence": []}
    report = validator.validate(bad, target_class="DataModalityClassification")
    assert report.results, "an out-of-enum value should have failed validation"
