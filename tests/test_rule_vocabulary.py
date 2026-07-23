"""Validate the rules against the LinkML schema vocabulary (issue #111).

Two layers of protection:

1. The loader (rule_loader) rejects unknown ``when``/``then`` *keys* — catching
   typo'd condition/effect names that would otherwise be silently ignored.
2. This module checks that every classification *value* a rule emits is a member
   of the matching enum in the canonical LinkML schema
   (``src/meta_disco/schema/classification.yaml``) — catching typos, stale
   values, and new values introduced without updating the schema.

Together they keep the rules and the schema from drifting apart.
"""

import pytest
import yaml

from meta_disco import schema_vocab
from meta_disco.file_name import Format
from meta_disco.rule_loader import RuleLoader, get_unified_rules


def _when_value_violations(rules):
    """Enum-backed `when` condition values not in the schema vocabulary.

    The single detection path for the antecedent-value check — exercised by both
    the suite-wide test and the negative test, so the latter load-bears on the
    real logic rather than re-deriving the membership assertion.
    """
    violations = []
    for rule in rules.rules:
        for key, dimension in schema_vocab.ENUM_BACKED_WHEN_KEYS.items():
            value = (rule.when or {}).get(key)
            if value is not None and not schema_vocab.value_in_vocabulary(dimension, value):
                violations.append(f"{rule.id}: when.{key}={value!r}")
    return violations


def _when_format_violations(rules):
    """`when.format` values that are not real Format members.

    The format counterpart to _when_value_violations. Format is an in-code enum
    rather than a LinkML schema dimension, so it is checked directly against the
    enum instead of through schema_vocab (#243) — but it is the same antecedent-
    value drift check, in the same test layer (the loader validates when *keys*,
    values are checked here). Shared by the suite-wide and negative tests.

    A present `format` must be a string in the Format vocabulary; anything else
    is a violation — including ``null`` and non-string types (e.g. a list), which
    the ``isinstance`` guard reports rather than raising ``TypeError`` on the
    ``not in`` hash. Mirrors value_in_vocabulary's non-string handling.
    """
    valid = {f.value for f in Format}
    violations = []
    for rule in rules.rules:
        when = rule.when or {}
        if "format" not in when:
            continue
        value = when["format"]
        if not isinstance(value, str) or value not in valid:
            violations.append(f"{rule.id}: when.format={value!r}")
    return violations


def test_rule_then_values_in_vocabulary():
    """Every value a rule emits must be a real value in the schema vocabulary.

    Since #133, a field a rule declares non-classified is authored in
    ``then.status`` (see test_rule_then_status_values_are_schema_statuses), so a
    ``then``-value is always a real dimension value and the check is strict
    (``value_in_vocabulary``) — a sentinel in a value slot is now a violation.
    """
    rules = get_unified_rules()
    violations = []
    for rule in rules.rules:
        for field, value in (rule.then or {}).items():
            if field not in schema_vocab.DIMENSION_ENUMS or value is None:
                continue
            if not schema_vocab.value_in_vocabulary(field, value):
                violations.append(f"{rule.id}: {field}={value!r}")

    assert not violations, (
        "Rules emit classification values not in the LinkML schema vocabulary.\n"
        "Add them to classification.yaml or fix the rule:\n  " + "\n  ".join(violations)
    )


def test_rule_then_status_values_are_schema_statuses():
    """Every ``then.status`` value a rule authors must be a schema status value.

    The status counterpart to test_rule_then_values_in_vocabulary: rules author
    ``not_applicable`` / ``not_classified`` in ``then.status`` (#133), and those
    must be members of the schema's classification_status_enum — so the loader's
    authorable set and the schema stay in lockstep.
    """
    statuses = schema_vocab.status_values()
    violations = [
        f"{rule.id}: status.{field}={status!r}"
        for rule in get_unified_rules().rules
        for field, status in rule.then_status.items()
        if status not in statuses
    ]
    assert not violations, "Rules author then.status values not in the schema status enum:\n  " + "\n  ".join(
        violations
    )


def test_rule_when_values_in_vocabulary():
    """Enum-backed `when` condition values must also be in the schema vocabulary.

    Mirrors the `then`-value check for the antecedent side (issue #113). Only
    `when` keys in ENUM_BACKED_WHEN_KEYS are dimension-enum-backed; the rest
    (regexes, header codes, numeric bounds, booleans) are not checkable this way.
    """
    violations = _when_value_violations(get_unified_rules())
    assert not violations, (
        "Rules use `when` condition values not in the LinkML schema vocabulary.\n"
        "Add them to classification.yaml or fix the rule:\n  " + "\n  ".join(violations)
    )


def test_rule_when_format_values_valid():
    """Every `when.format` value must be a real Format member (#243).

    The in-code counterpart to test_rule_when_values_in_vocabulary: `format` is
    backed by the Format enum, not the schema, so it is drift-checked directly
    against the enum. Catches a typo'd format (which would silently never match)
    the same way the platform check catches a typo'd platform.
    """
    violations = _when_format_violations(get_unified_rules())
    assert not violations, (
        "Rules use `when.format` values that are not real Format members.\n"
        "Add the format to meta_disco.file_name.Format or fix the rule:\n  " + "\n  ".join(violations)
    )


def test_when_value_check_rejects_bogus_platform(tmp_path):
    """The when-value drift check catches a typo'd enum-backed value (issue #113).

    Runs the real scan (_when_value_violations) over a rule whose when.platform is
    bogus. The loader accepts the *key* (`platform` is a valid when key); this is
    the *value* gap #113 closes.
    """
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bogus_when_platform",
            "tier": 2,
            "scope": "filename",
            "when": {"platform": "ILUMINA"},  # typo: should be ILLUMINA
            "then": {"data_modality": "genomic"},
        },
    )
    violations = _when_value_violations(RuleLoader(path).load())
    assert violations == ["bogus_when_platform: when.platform='ILUMINA'"]


def test_assay_type_inference_values_in_vocabulary():
    """assay_type_rules (the inference block) must also use vocabulary values."""
    rules = get_unified_rules()
    violations = [
        f"{r.id}: assay_type={r.assay_type!r}"
        for r in rules.assay_type_rules
        if r.assay_type and not schema_vocab.value_in_vocabulary("assay_type", r.assay_type)
    ]
    assert not violations, "assay_type inference rules emit values not in the schema vocabulary:\n  " + "\n  ".join(
        violations
    )


def _assay_condition_violations(rules):
    """Enum-backed assay_type_rules *condition* values not in the vocabulary.

    The antecedent side of the assay-inference block — the same class as
    _when_value_violations, for the conditions matched in infer_assay_type.
    """
    violations = []
    for rule in rules.assay_type_rules:
        conditions = rule.conditions or {}
        for key, (dimension, is_list) in schema_vocab.ENUM_BACKED_ASSAY_CONDITIONS.items():
            if key not in conditions:
                continue
            raw = conditions[key]
            values = raw if is_list and isinstance(raw, list) else [raw]
            for value in values:
                if not schema_vocab.value_in_vocabulary(dimension, value):
                    violations.append(f"{rule.id}: conditions.{key}={value!r}")
    return violations


def test_assay_type_condition_values_in_vocabulary():
    """Enum-backed assay_type_rules *conditions* must use vocabulary values too.

    The antecedent-value gap (#113) also exists in the assay-inference block:
    data_modality / platform / platform_in are matched against the schema enums
    in infer_assay_type, so a typo there silently never matches.
    """
    violations = _assay_condition_violations(get_unified_rules())
    assert not violations, (
        "assay_type_rules conditions use values not in the LinkML schema vocabulary:\n  " + "\n  ".join(violations)
    )


def test_assay_condition_check_rejects_bogus_platform(tmp_path):
    """The assay-condition drift check catches a typo'd enum-backed value (#113)."""
    path = tmp_path / "rules.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump_all(
            [
                {"extension_map": {}},
                {"rules": []},
                {"validators": {}},
                {
                    "assay_type_rules": [
                        {
                            "id": "bogus_assay",
                            "priority": 1,
                            "conditions": {"platform_in": ["ILUMINA"]},  # typo: should be ILLUMINA
                            "assay_type": "WGS",
                        }
                    ]
                },
            ],
            f,
        )
    violations = _assay_condition_violations(RuleLoader(path).load())
    assert violations == ["bogus_assay: conditions.platform_in='ILUMINA'"]


def _write_assay_rules_file(tmp_path, assay_rule):
    """Write a rules file whose fourth document holds a single assay_type_rule."""
    path = tmp_path / "rules.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump_all(
            [
                {"extension_map": {}},
                {"rules": []},
                {"validators": {}},
                {"assay_type_rules": [assay_rule]},
            ],
            f,
        )
    return path


@pytest.mark.parametrize("bad_conditions", ["always", "", [], 0])
def test_loader_rejects_non_mapping_assay_conditions(tmp_path, bad_conditions):
    # A non-mapping `conditions` must raise at load time rather than crash
    # infer_assay_type (which assumes a mapping). Mirrors the when/then guard.
    path = _write_assay_rules_file(
        tmp_path,
        {
            "id": "bad_conditions",
            "priority": 1,
            "conditions": bad_conditions,
            "assay_type": "WGS",
        },
    )
    with pytest.raises(ValueError, match="'conditions' must be a mapping"):
        RuleLoader(path).load()


def test_loader_accepts_null_assay_conditions(tmp_path):
    # A null `conditions` block is a catch-all rule; coerced to {}, not a crash.
    path = _write_assay_rules_file(
        tmp_path,
        {
            "id": "null_conditions",
            "priority": 1,
            "conditions": None,
            "assay_type": "WGS",
        },
    )
    loaded = RuleLoader(path).load()
    assert loaded.assay_type_rules[0].conditions == {}


@pytest.mark.parametrize("list_key", ["platform_in", "matched_rules_any"])
def test_loader_rejects_scalar_list_valued_assay_condition(tmp_path, list_key):
    # A scalar where a list is expected would be iterated char-by-char by
    # infer_assay_type and silently mis-match; the loader must reject it.
    path = _write_assay_rules_file(
        tmp_path,
        {
            "id": "scalar_list",
            "priority": 1,
            "conditions": {list_key: "ILLUMINA"},  # should be ["ILLUMINA"]
            "assay_type": "WGS",
        },
    )
    with pytest.raises(ValueError, match=f"condition '{list_key}' must be a list"):
        RuleLoader(path).load()


def test_loader_accepts_list_valued_assay_conditions(tmp_path):
    path = _write_assay_rules_file(
        tmp_path,
        {
            "id": "list_ok",
            "priority": 1,
            "conditions": {"platform_in": ["PACBIO", "ONT"], "matched_rules_any": ["r1"]},
            "assay_type": "WGS",
        },
    )
    loaded = RuleLoader(path).load()
    assert loaded.assay_type_rules[0].conditions["platform_in"] == ["PACBIO", "ONT"]


def test_dimension_values_unknown_field_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown classification dimension"):
        schema_vocab.dimension_values("not_a_field")


def test_status_values_from_schema():
    # The permissible per-field `status` values, loaded from the schema enum —
    # incl. `conflict` (#88), which is not yet produced but is a valid status.
    assert schema_vocab.status_values() == frozenset({"classified", "not_applicable", "not_classified", "conflict"})


def test_marker_constants_match_schema_enum():
    # rule_engine emits synthetic markers whose `marker` kind must be a member of
    # the schema's evidence_marker_enum (else LinkML output validation rejects
    # them). Pin the Python constants to the schema so the two cannot drift (#228).
    from meta_disco.rule_engine import CONFLICT_MARKER, NOT_CLASSIFIED_MARKER

    assert {NOT_CLASSIFIED_MARKER, CONFLICT_MARKER} == schema_vocab.marker_values()


def test_value_in_vocabulary_is_strict_dimension_only():
    # Antecedent/output check: a real dimension value passes; a status does NOT —
    # a status in a when/condition (or an output value) is a bug (#115, Stage 3).
    assert schema_vocab.value_in_vocabulary("reference_assembly", "GRCh38")
    assert not schema_vocab.value_in_vocabulary("reference_assembly", "not_applicable")
    assert not schema_vocab.value_in_vocabulary("data_modality", "not_classified")


def test_value_in_vocabulary_rejects_bogus_and_non_string():
    assert not schema_vocab.value_in_vocabulary("reference_assembly", "GRCh99")
    assert not schema_vocab.value_in_vocabulary("platform", ["ILLUMINA", "PACBIO"])


def test_value_in_vocabulary_rejects_all_statuses():
    # A status never belongs in a value slot — the emitted-value check is now
    # strict too (#133), so then/assay/output values reject every status.
    for status in ("not_applicable", "not_classified", "classified", "conflict"):
        assert not schema_vocab.value_in_vocabulary("platform", status)


def _write_rules_file(tmp_path, rule):
    """Write a minimal two-document rules file containing a single rule."""
    path = tmp_path / "rules.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump_all([{"extension_map": {}}, {"rules": [rule]}], f)
    return path


def test_loader_rejects_unknown_when_key(tmp_path):
    path = _write_rules_file(
        tmp_path,
        {
            "id": "typo_when",
            "tier": 2,
            "scope": "filename",
            "when": {"filename_patern": "x"},  # typo: should be filename_pattern
            "then": {"data_modality": "genomic"},
        },
    )
    with pytest.raises(ValueError, match="unknown 'when' condition key"):
        RuleLoader(path).load()


def test_format_value_check_rejects_bogus_format(tmp_path):
    """The format drift check catches a typo'd Format value (#243).

    The format analogue of test_when_value_check_rejects_bogus_platform. The
    loader accepts the `format` *key* (it is a valid when key); the *value* gap
    is closed by the _when_format_violations scan, so this exercises that scan
    over a rule whose when.format is bogus.
    """
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bogus_format",
            "tier": 1,
            "scope": "extension",
            "when": {"format": "FASTAA"},  # typo: should be FASTA
            "then": {"data_type": "sequence"},
        },
    )
    violations = _when_format_violations(RuleLoader(path).load())
    assert violations == ["bogus_format: when.format='FASTAA'"]


@pytest.mark.parametrize("bad", [None, ["FASTA"]])
def test_format_check_flags_null_and_nonstring(tmp_path, bad):
    """A present `format` that is null or a non-string is flagged, not skipped or
    crashed on — the scan guards the hash with isinstance (#243)."""
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bad_format",
            "tier": 1,
            "scope": "extension",
            "when": {"format": bad},
            "then": {"data_type": "sequence"},
        },
    )
    violations = _when_format_violations(RuleLoader(path).load())
    assert violations == [f"bad_format: when.format={bad!r}"]


def test_loader_rejects_unknown_then_key(tmp_path):
    path = _write_rules_file(
        tmp_path,
        {
            "id": "typo_then",
            "tier": 1,
            "scope": "extension",
            "when": {"extensions": [".bam"]},
            "then": {"data_modalty": "genomic"},  # typo: should be data_modality
        },
    )
    with pytest.raises(ValueError, match="unknown 'then' effect key"):
        RuleLoader(path).load()


def test_loader_parses_then_status(tmp_path):
    # A `then.status` sub-map is parsed into `then_status`; `then` keeps only the
    # real-value effects, with the `status` key stripped out (#133).
    path = _write_rules_file(
        tmp_path,
        {
            "id": "mixed",
            "tier": 2,
            "scope": "extension",
            "when": {"extensions": [".fast5"]},
            "then": {
                "data_type": "raw_signal",
                "platform": "ONT",
                "status": {"reference_assembly": "not_applicable"},
            },
        },
    )
    rule = RuleLoader(path).load().rules[0]
    assert rule.then == {"data_type": "raw_signal", "platform": "ONT"}
    assert rule.then_status == {"reference_assembly": "not_applicable"}


def test_loader_rejects_unknown_then_status_field(tmp_path):
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bad_status_field",
            "tier": 1,
            "scope": "extension",
            "when": {"extensions": [".md5"]},
            "then": {"status": {"data_modalty": "not_applicable"}},  # typo
        },
    )
    with pytest.raises(ValueError, match=r"unknown 'then\.status' field"):
        RuleLoader(path).load()


@pytest.mark.parametrize("bad_status", ["classified", "conflict", "genomic", "typo"])
def test_loader_rejects_non_authorable_then_status_value(tmp_path, bad_status):
    # Only not_applicable / not_classified may be authored; classified is implied
    # by a real value and conflict is engine-derived.
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bad_status_value",
            "tier": 1,
            "scope": "extension",
            "when": {"extensions": [".md5"]},
            "then": {"status": {"data_modality": bad_status}},
        },
    )
    with pytest.raises(ValueError, match=r"'then\.status' values must be one of"):
        RuleLoader(path).load()


def test_loader_rejects_field_in_both_then_and_status(tmp_path):
    # A field is either a real value or a status, never both.
    path = _write_rules_file(
        tmp_path,
        {
            "id": "field_conflict",
            "tier": 2,
            "scope": "extension",
            "when": {"extensions": [".bam"]},
            "then": {
                "data_modality": "genomic",
                "status": {"data_modality": "not_applicable"},
            },
        },
    )
    with pytest.raises(ValueError, match="appear in both 'then'"):
        RuleLoader(path).load()


@pytest.mark.parametrize("bad_status_block", ["not_applicable", [], 0])
def test_loader_rejects_non_mapping_then_status(tmp_path, bad_status_block):
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bad_status_block",
            "tier": 1,
            "scope": "extension",
            "when": {"extensions": [".md5"]},
            "then": {"status": bad_status_block},
        },
    )
    with pytest.raises(ValueError, match=r"'then\.status' must be a mapping"):
        RuleLoader(path).load()


@pytest.mark.parametrize("bad_when", ["always", "", [], 0])
def test_loader_rejects_non_mapping_when(tmp_path, bad_when):
    # Any non-mapping `when` (scalar, empty string, empty list, ...) must raise a
    # clear error — not a TypeError, not a per-character "unknown key" message,
    # and crucially not silently coerce to {} (an unconditional match).
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bad_when",
            "tier": 1,
            "scope": "extension",
            "when": bad_when,
            "then": {"data_modality": "genomic"},
        },
    )
    with pytest.raises(ValueError, match="'when' must be a mapping"):
        RuleLoader(path).load()


def test_loader_accepts_null_when_and_then(tmp_path):
    # Empty/null when/then blocks must not crash the load (set(None) TypeError).
    path = _write_rules_file(
        tmp_path,
        {
            "id": "null_blocks",
            "tier": 1,
            "scope": "extension",
            "when": None,
            "then": None,
        },
    )
    loaded = RuleLoader(path).load()
    assert loaded.rules[0].when == {} and loaded.rules[0].then == {}


def test_loader_accepts_known_keys(tmp_path):
    path = _write_rules_file(
        tmp_path,
        {
            "id": "good_rule",
            "tier": 2,
            "scope": "filename",
            "when": {"extensions": [".bam"], "filename_pattern": "rnaseq"},
            "then": {"data_modality": "transcriptomic.bulk", "data_type": "alignments"},
        },
    )
    loaded = RuleLoader(path).load()
    assert loaded.rules[0].id == "good_rule"
