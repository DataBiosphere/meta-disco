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

Runs in the schema/ uv project, which has linkml installed (the runtime
does not).
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


@pytest.fixture(scope="session")
def envelope_validator():
    """A `closed=True` validator, for the claim-file envelope only (#401).

    The gates above run `closed=False` because the golden output carries keys the
    schema does not model (the fastq scalar hints). The envelope has no such
    tolerance to extend: it is a small, complete contract that `claim_files` writes
    and reads whole, and an unmodeled key in it is a claim file the reader will
    refuse. Validating it `closed=False` would let `ClaimFileSource` and
    `ClaimSource` differ on paper while accepting the same documents — which is the
    mismatch the separate class exists to prevent.
    """
    return Validator(
        schema=str(_SCHEMA),
        validation_plugins=[PydanticValidationPlugin(closed=True)],
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
        assert isinstance(classifications, dict), f"{label}: record missing a 'classifications' dict"
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
    assert not failures, "Pipeline output violates the classification schema:\n  " + "\n  ".join(failures)


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
    assert not failures, "Pipeline output violates the record schema:\n  " + "\n  ".join(failures)


def test_record_gate_rejects_missing_classifications(validator):
    # The record gate must bite: a record without the required `classifications`
    # container fails (proves whole-record validation is actually enforced).
    bad = {"md5sum": "x", "file_name": "f.bam"}
    report = validator.validate(bad, target_class="ClassificationRecord")
    assert report.results, "a record missing 'classifications' should have failed"


def test_record_gate_rejects_bad_dimension_value(validator):
    # A bad enum value nested inside the container must fail record validation.
    entry = {"value": "not_a_real_modality", "status": "classified", "evidence": []}
    ok = {"value": None, "status": "not_classified", "evidence": []}
    classifications = {dim: (entry if dim == "data_modality" else ok) for dim in DIMENSION_CLASS}
    bad = {"md5sum": "x", "file_name": "f.bam", "classifications": classifications}
    report = validator.validate(bad, target_class="ClassificationRecord")
    # Assert it fails *because of* the bad enum value, not some unrelated reason —
    # otherwise a regression in nested enum validation could leave this test green.
    assert any("not_a_real_modality" in r.message for r in report.results), (
        f"expected a failure citing the bad enum value, got: {[r.message for r in report.results]}"
    )


def test_gate_rejects_missing_status(validator):
    # status is required — an entry without it must fail (proves the gate bites).
    bad = {"value": "genomic", "evidence": []}
    report = validator.validate(bad, target_class="DataModalityClassification")
    assert report.results, "missing status should have failed validation"


def test_gate_rejects_out_of_enum_value(validator):
    bad = {"value": "not_a_real_modality", "status": "classified", "evidence": []}
    report = validator.validate(bad, target_class="DataModalityClassification")
    assert report.results, "an out-of-enum value should have failed validation"


# --- ClaimFileEnvelope (#401) ------------------------------------------------
#
# The envelope is a standalone class: it describes an artefact exchanged *between*
# runs and is referenced by no slot in ClassificationRecord, so the golden-output
# gates above never reach it. Without these, a typo in its required members or
# ranges would pass the schema gate even though this class defines the on-disk
# claim-file contract (#401 review).


def _envelope(**overrides) -> dict:
    """A valid claim-file envelope as `ClaimFileEnvelope.to_dict` writes one.

    The HPRC Data Explorer's R2 sequencing-data table, keyed by the filenames it
    publishes, matched against AnVIL's `file_name` within the dataset that makes that
    key usable.
    """
    return {
        "source": {
            "repository": "HPRC Data Explorer",
            "dataset": "R2",
            "table": "sequencing-data",
            "url": "https://data.humanpangenome.org/",
        },
        "source_version": "2026-09-01",
        "source_key": "filename",
        "target": {"system": "anvil", "dataset": "AnVIL_HPRC_R2", "version": "anvil15"},
        "target_key": "file_name",
        "fetched_at": "2026-09-01T09:14:03",
        **overrides,
    }


def test_claim_file_envelope_validates(envelope_validator):
    report = envelope_validator.validate(_envelope(), target_class="ClaimFileEnvelope")
    assert not report.results, "a well-formed envelope should validate: " + str([r.message for r in report.results])


def test_claim_file_envelope_accepts_a_target_with_no_scope(envelope_validator):
    # Null for a source whose key is unique across the whole target (`file_id`,
    # `entry_id`, `drs_uri`), where a corpus-wide match is correct.
    report = envelope_validator.validate(
        _envelope(target={"system": "anvil"}, target_key="file_id"), target_class="ClaimFileEnvelope"
    )
    assert not report.results, str([r.message for r in report.results])


def test_claim_file_envelope_refuses_a_target_key_outside_the_vocabulary(envelope_validator):
    # `target_key` is a key of the *target*, drawn from join_key_enum. A source keyed
    # by an ENA run accession maps it to one of these rather than adding a term here.
    report = envelope_validator.validate(_envelope(target_key="run_accession"), target_class="ClaimFileEnvelope")
    assert report.results, "a target_key outside join_key_enum should have failed"


def test_claim_file_envelope_accepts_a_derived_target_key(envelope_validator):
    # archive_accession is read from a fastq's read headers rather than from the
    # input record, which is why the join runs after inference.
    report = envelope_validator.validate(_envelope(target_key="archive_accession"), target_class="ClaimFileEnvelope")
    assert not report.results, str([r.message for r in report.results])


@pytest.mark.parametrize("missing", ["source", "fetched_at", "source_version", "source_key", "target", "target_key"])
def test_claim_file_envelope_requires_its_provenance(envelope_validator, missing):
    # Each is required: a claim file that cannot say where it came from, when, or
    # from what version cannot be reasoned about later.
    bad = _envelope()
    del bad[missing]
    report = envelope_validator.validate(bad, target_class="ClaimFileEnvelope")
    assert report.results, f"an envelope missing {missing!r} should have failed"


@pytest.mark.parametrize("slot", ["source", "target"])
@pytest.mark.parametrize("shape", ["a name", [{"repository": "HPRC"}]])
def test_claim_file_envelope_refuses_a_nested_record_given_as_a_reference(envelope_validator, slot, shape):
    # Line 1 carries the whole source and target objects, because a claim file is
    # read by itself: there is no registry a name could be resolved against, and a
    # list would say the file has two of something it has one of.
    report = envelope_validator.validate(_envelope(**{slot: shape}), target_class="ClaimFileEnvelope")
    assert report.results, f"a {slot} given as {shape!r} should have failed"


def test_claim_file_envelope_refuses_a_non_datetime_fetched_at(envelope_validator):
    # The slot's pattern refuses what ClaimFileEnvelope.from_dict refuses rather
    # than accepting free text the reader will not take.
    report = envelope_validator.validate(_envelope(fetched_at="yesterday"), target_class="ClaimFileEnvelope")
    assert report.results, "a non-datetime fetched_at should have failed"


# The schema must refuse what the reader refuses. Each of these was a value that
# passed LinkML validation and was then rejected by `ClaimFileEnvelope.from_dict`
# or `__post_init__`, so a claim file could clear the schema gate and still be
# reported unreadable (#401 review).


def test_claim_file_envelope_refuses_an_empty_source_version(envelope_validator):
    # `required` alone admits ""; `required_str` does not.
    report = envelope_validator.validate(_envelope(source_version=""), target_class="ClaimFileEnvelope")
    assert report.results, "an empty source_version should have failed"


def test_claim_file_envelope_refuses_an_empty_target_version(envelope_validator):
    # Absent is fine; present-and-empty is not, matching `optional_str`.
    report = envelope_validator.validate(
        _envelope(target={"system": "anvil", "version": ""}), target_class="ClaimFileEnvelope"
    )
    assert report.results, "an empty target version should have failed"


def test_claim_file_envelope_refuses_a_source_with_no_repository(envelope_validator):
    bad = _envelope()
    bad["source"] = {"url": "https://data.humanpangenome.org/"}
    report = envelope_validator.validate(bad, target_class="ClaimFileEnvelope")
    assert report.results, "a source with no repository should have failed"


def test_claim_file_envelope_refuses_a_source_naming_a_column(envelope_validator):
    # `ClaimFileSource` has no `column`: a column belongs to a claim, and an
    # envelope carrying one could disagree with every line in the file.
    bad = _envelope()
    bad["source"] = {**bad["source"], "column": "platform"}
    report = envelope_validator.validate(bad, target_class="ClaimFileEnvelope")
    assert report.results, "an envelope source naming a column should have failed"


def test_claim_file_envelope_refuses_a_date_only_fetched_at(envelope_validator):
    # A date with no time of day reads back as midnight — a precision the file never
    # stated. The slot is constrained by a pattern rather than `range: datetime`,
    # which would accept one, so the schema and `ClaimFileEnvelope.from_dict` refuse
    # the same strings.
    report = envelope_validator.validate(_envelope(fetched_at="2026-09-01"), target_class="ClaimFileEnvelope")
    assert report.results, "a date-only fetched_at should have failed"
