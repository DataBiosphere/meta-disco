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
``classifications`` key — that record-shape reconciliation is tracked separately.

Runs in the schema/ Poetry component, which has linkml installed (the root
component does not).
"""

import json
from pathlib import Path

from linkml.validator import Validator
from linkml.validator.plugins.pydantic_validation_plugin import PydanticValidationPlugin

# schema/tests/ -> schema/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = Path(__file__).resolve().parents[1] / "src/meta_disco/schema/classification.yaml"
_GOLDEN = _REPO_ROOT / "tests/fixtures/golden/expected_output.json"

# Each output dimension -> the schema class that constrains its entry.
DIMENSION_CLASS = {
    "data_modality": "DataModalityClassification",
    "data_type": "DataTypeClassification",
    "reference_assembly": "ReferenceAssemblyClassification",
    "assay_type": "AssayTypeClassification",
    "platform": "PlatformClassification",
}


def _golden_entries():
    """Yield (label, dimension, entry) for every dimension entry in the golden."""
    data = json.loads(_GOLDEN.read_text())
    for ftype, payload in data.items():
        for i, record in enumerate(payload["classifications"]):
            classifications = record["classifications"]
            for dim in DIMENSION_CLASS:
                yield f"{ftype}[{i}].{dim}", dim, classifications[dim]


def test_golden_present():
    assert _GOLDEN.exists(), f"golden fixture not found at {_GOLDEN}"


def test_output_entries_validate_against_schema():
    validator = Validator(
        schema=str(_SCHEMA),
        validation_plugins=[PydanticValidationPlugin(closed=False)],
    )
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


def _validator():
    return Validator(
        schema=str(_SCHEMA),
        validation_plugins=[PydanticValidationPlugin(closed=False)],
    )


def test_gate_rejects_missing_status():
    # status is required — an entry without it must fail (proves the gate bites).
    bad = {"value": "genomic", "confidence": 1.0, "evidence": []}
    report = _validator().validate(bad, target_class="DataModalityClassification")
    assert report.results, "missing status should have failed validation"


def test_gate_rejects_out_of_enum_value():
    bad = {"value": "not_a_real_modality", "status": "classified",
           "confidence": 1.0, "evidence": []}
    report = _validator().validate(bad, target_class="DataModalityClassification")
    assert report.results, "an out-of-enum value should have failed validation"
