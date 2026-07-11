"""Hard gate: real pipeline output conforms to the status-required schema.

Epic #116 Stage 4a (#122). Stage 0's golden guardrail checked output *shape* and
values-in-vocabulary but deferred full schema validation to here. This validates
each per-field classification entry from the golden output against its
``Classification`` subclass in ``classification.yaml`` — enforcing the Stage 3
contract at the schema level: ``status`` is required and drawn from
``classification_status_enum``, and ``value`` is either null or a member of that
dimension's enum.

Two levels of validation:

* per-field *entries* (value/status/evidence) against their
  ``Classification`` subclass, and
* the whole record against ``ClassificationRecord`` — enabled by #134, which added
  the ``classifications`` container so the schema matches the pipeline output shape
  (``{..., "classifications": {...}}``).

Both run ``closed=False``: structure, required slots, and enum ranges are enforced,
but keys the schema does not model — the fastq scalar hints inside
``classifications`` (``is_paired_end``, ``instrument_model``, ``archive_*``) — are
tolerated. Modeling those and tightening to ``closed=True`` is a #134 follow-up.
(Evidence's ``value``/``status``/``tier`` are modeled, so they are validated, not
merely tolerated.)

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
_SCHEMA = _REPO_ROOT / "src/meta_disco/schema/classification.yaml"
_GOLDEN = _REPO_ROOT / "tests/fixtures/golden/expected_output.json"


def _dimension_classes() -> dict:
    """Map each output dimension to the schema class that constrains its entry.

    Derived from the ``Classifications`` container's slot_usage (the single source
    of truth) rather than hardcoded, so a dimension added to the schema is picked
    up automatically. (A dimension present in the *output* but absent from
    slot_usage would still not be validated per-entry — but the whole-record test
    validates the container as a whole, catching such a divergence there.)
    """
    assert _SCHEMA.exists(), f"classification schema not found at {_SCHEMA}"
    schema = yaml.safe_load(_SCHEMA.read_text(encoding="utf-8"))
    slot_usage = schema["classes"]["Classifications"]["slot_usage"]
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


def _golden_records():
    """Yield (label, record) for every classification record in the golden.

    Guard here (not just in test_golden_present) so a missing fixture fails with a
    clear message regardless of test order, never a bare FileNotFoundError. Assert
    the nested shape too, so a producer/fixture drift fails legibly rather than a
    bare KeyError.
    """
    assert _GOLDEN.exists(), f"golden fixture not found at {_GOLDEN}"
    data = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    for ftype, payload in data.items():
        assert "classifications" in payload, f"{ftype}: golden payload missing 'classifications'"
        records = payload["classifications"]
        assert isinstance(records, list), f"{ftype}: 'classifications' is not a list"
        for i, record in enumerate(records):
            assert isinstance(record, dict), f"{ftype}[{i}]: record is not a mapping"
            yield f"{ftype}[{i}]", record


def _golden_entries():
    """Yield (label, dimension, entry) for every dimension entry in the golden."""
    for label, record in _golden_records():
        classifications = record.get("classifications")
        assert isinstance(classifications, dict), \
            f"{label}: record missing a 'classifications' dict"
        for dim in DIMENSION_CLASS:
            assert dim in classifications, f"{label}: missing dimension {dim!r}"
            yield f"{label}.{dim}", dim, classifications[dim]


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


def test_output_records_validate_against_schema(validator):
    # Whole-record gate (#134): each golden record validates against
    # ClassificationRecord, exercising the `classifications` container end to end.
    failures = []
    checked = 0
    for label, record in _golden_records():
        checked += 1
        report = validator.validate(record, target_class="ClassificationRecord")
        for result in report.results:
            failures.append(f"{label}: {result.severity}: {result.message}")

    assert checked > 0, "no golden records were validated"
    assert not failures, "Pipeline output violates the record schema:\n  " + \
        "\n  ".join(failures)


def test_record_gate_rejects_missing_classifications(validator):
    # The record gate must bite: a record without the required `classifications`
    # container fails (proves whole-record validation is actually enforced).
    bad = {"md5sum": "x", "file_name": "f.bam"}
    report = validator.validate(bad, target_class="ClassificationRecord")
    assert report.results, "a record missing 'classifications' should have failed"


def test_record_gate_rejects_bad_dimension_value(validator):
    # A bad enum value nested inside the container must fail record validation.
    entry = {"value": "not_a_real_modality", "status": "classified",
             "evidence": []}
    ok = {"value": None, "status": "not_classified", "evidence": []}
    classifications = {dim: (entry if dim == "data_modality" else ok)
                       for dim in DIMENSION_CLASS}
    bad = {"md5sum": "x", "file_name": "f.bam", "classifications": classifications}
    report = validator.validate(bad, target_class="ClassificationRecord")
    # Assert it fails *because of* the bad enum value, not some unrelated reason —
    # otherwise a regression in nested enum validation could leave this test green.
    assert any("not_a_real_modality" in r.message for r in report.results), \
        f"expected a failure citing the bad enum value, got: {[r.message for r in report.results]}"


def test_gate_rejects_missing_status(validator):
    # status is required — an entry without it must fail (proves the gate bites).
    bad = {"value": "genomic", "evidence": []}
    report = validator.validate(bad, target_class="DataModalityClassification")
    assert report.results, "missing status should have failed validation"


def test_gate_rejects_out_of_enum_value(validator):
    bad = {"value": "not_a_real_modality", "status": "classified",
           "evidence": []}
    report = validator.validate(bad, target_class="DataModalityClassification")
    assert report.results, "an out-of-enum value should have failed validation"
