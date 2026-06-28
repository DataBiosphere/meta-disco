"""Validate the rules against the LinkML schema vocabulary (issue #111).

Two layers of protection:

1. The loader (rule_loader) rejects unknown ``when``/``then`` *keys* — catching
   typo'd condition/effect names that would otherwise be silently ignored.
2. This module checks that every classification *value* a rule emits is a member
   of the matching enum in the canonical LinkML schema
   (``schema/src/meta_disco/schema/classification.yaml``) — catching typos, stale
   values, and new values introduced without updating the schema.

Together they keep the rules and the schema from drifting apart.
"""

import pytest
import yaml

from src.meta_disco import schema_vocab
from src.meta_disco.rule_loader import RuleLoader, get_unified_rules


def test_rule_then_values_in_vocabulary():
    """Every value a rule emits must be in the schema vocabulary (or a sentinel)."""
    rules = get_unified_rules()
    violations = []
    for rule in rules.rules:
        for field, value in (rule.then or {}).items():
            if field not in schema_vocab.DIMENSION_ENUMS or value is None:
                continue
            allowed = schema_vocab.dimension_values(field) | schema_vocab.SENTINEL_VALUES
            if value not in allowed:
                violations.append(f"{rule.id}: {field}={value!r}")

    assert not violations, (
        "Rules emit classification values not in the LinkML schema vocabulary.\n"
        "Add them to classification.yaml or fix the rule:\n  "
        + "\n  ".join(violations)
    )


def test_assay_type_inference_values_in_vocabulary():
    """assay_type_rules (the inference block) must also use vocabulary values."""
    rules = get_unified_rules()
    allowed = schema_vocab.dimension_values("assay_type") | schema_vocab.SENTINEL_VALUES
    violations = [
        f"{r.id}: assay_type={r.assay_type!r}"
        for r in rules.assay_type_rules
        if r.assay_type and r.assay_type not in allowed
    ]
    assert not violations, (
        "assay_type inference rules emit values not in the schema vocabulary:\n  "
        + "\n  ".join(violations)
    )


def test_dimension_values_unknown_field_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown classification dimension"):
        schema_vocab.dimension_values("not_a_field")


def _write_rules_file(tmp_path, rule):
    """Write a minimal two-document rules file containing a single rule."""
    path = tmp_path / "rules.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump_all([{"extension_map": {}}, {"rules": [rule]}], f)
    return path


def test_loader_rejects_unknown_when_key(tmp_path):
    path = _write_rules_file(tmp_path, {
        "id": "typo_when", "tier": 2, "scope": "filename",
        "when": {"filename_patern": "x"},  # typo: should be filename_pattern
        "then": {"data_modality": "genomic"},
    })
    with pytest.raises(ValueError, match="unknown 'when' condition key"):
        RuleLoader(path).load()


def test_loader_rejects_unknown_then_key(tmp_path):
    path = _write_rules_file(tmp_path, {
        "id": "typo_then", "tier": 1, "scope": "extension",
        "when": {"extensions": [".bam"]},
        "then": {"data_modalty": "genomic"},  # typo: should be data_modality
    })
    with pytest.raises(ValueError, match="unknown 'then' effect key"):
        RuleLoader(path).load()


@pytest.mark.parametrize("bad_when", ["always", "", [], 0])
def test_loader_rejects_non_mapping_when(tmp_path, bad_when):
    # Any non-mapping `when` (scalar, empty string, empty list, ...) must raise a
    # clear error — not a TypeError, not a per-character "unknown key" message,
    # and crucially not silently coerce to {} (an unconditional match).
    path = _write_rules_file(tmp_path, {
        "id": "bad_when", "tier": 1, "scope": "extension",
        "when": bad_when,
        "then": {"data_modality": "genomic"},
    })
    with pytest.raises(ValueError, match="'when' must be a mapping"):
        RuleLoader(path).load()


def test_loader_accepts_null_when_and_then(tmp_path):
    # Empty/null when/then blocks must not crash the load (set(None) TypeError).
    path = _write_rules_file(tmp_path, {
        "id": "null_blocks", "tier": 1, "scope": "extension",
        "when": None, "then": None,
    })
    loaded = RuleLoader(path).load()
    assert loaded.rules[0].when == {} and loaded.rules[0].then == {}


def test_loader_accepts_known_keys(tmp_path):
    path = _write_rules_file(tmp_path, {
        "id": "good_rule", "tier": 2, "scope": "filename",
        "when": {"extensions": [".bam"], "filename_pattern": "rnaseq"},
        "then": {"data_modality": "transcriptomic.bulk", "data_type": "alignments"},
    })
    loaded = RuleLoader(path).load()
    assert loaded.rules[0].id == "good_rule"
