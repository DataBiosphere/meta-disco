"""Read the controlled classification vocabulary from the LinkML schema.

The LinkML schema at ``schema/src/meta_disco/schema/classification.yaml`` is the
canonical source of truth for the permissible values of each classification
dimension. This module loads the enum ``permissible_values`` so the rule engine's
emitted values can be validated against them (see
``tests/test_rule_vocabulary.py``), keeping the rules and the schema in lockstep.
"""

from functools import lru_cache
from pathlib import Path

import yaml

from .models import CLASSIFICATION_FIELDS, NOT_APPLICABLE, NOT_CLASSIFIED

# Sentinel values that rules currently emit as classification *values*. Per the
# schema these are slated to move into a separate ``status`` field (issues #56,
# #88); until that migration lands, the vocabulary check accepts them alongside
# real enum values.
SENTINEL_VALUES = frozenset({NOT_APPLICABLE, NOT_CLASSIFIED})

# Classification field -> the enum that defines its permissible values. By
# convention each dimension's enum is named ``<field>_enum`` in the schema, so
# this derives from the single source of truth rather than re-listing the fields.
DIMENSION_ENUMS = {field: f"{field}_enum" for field in CLASSIFICATION_FIELDS}

# The enum defining the permissible per-field ``status`` values (epic #116's
# sentinel→status split): classified / not_applicable / not_classified / conflict.
STATUS_ENUM = "classification_status_enum"

# ``when`` condition keys whose value must be a member of a dimension enum,
# mapped to that dimension. The rule engine compares these against enum values at
# match time, so a typo'd value silently never matches rather than erroring — the
# same class of bug the ``then``-value check guards against. Only ``platform``
# qualifies today; the other ``when`` keys carry regexes, header field codes,
# numeric bounds, or booleans, none of which are dimension-enum-backed.
# ``when.file_format`` is checked against extension_map keys, not a dimension enum
# (see issue #114). Keep in sync with rule_engine.RuleEngine._rule_matches().
ENUM_BACKED_WHEN_KEYS = {"platform": "platform"}

# assay_type_rules ``conditions`` keys whose value(s) must be dimension-enum
# members, mapped to (dimension, is_list). The same antecedent-value class as
# ENUM_BACKED_WHEN_KEYS, but in the separate assay-inference block. Excluded
# (intentionally): data_modality_contains (substring match, not full-enum
# membership), file_format / file_format_not (extension_map, not a dimension
# enum — see #114), matched_rules_any (rule ids), and numeric size bounds.
# Keep in sync with rule_engine.RuleEngine.infer_assay_type().
ENUM_BACKED_ASSAY_CONDITIONS = {
    "data_modality": ("data_modality", False),
    "platform": ("platform", False),
    "platform_in": ("platform", True),
}


def default_schema_path() -> Path:
    """Path to the canonical LinkML classification schema."""
    return (
        Path(__file__).parent.parent.parent
        / "schema" / "src" / "meta_disco" / "schema" / "classification.yaml"
    )


@lru_cache(maxsize=None)
def _load_enums() -> dict[str, frozenset[str]]:
    """Load all enums from the schema as ``{enum_name: {permissible values}}``."""
    path = default_schema_path()
    if not path.exists():
        raise FileNotFoundError(
            f"LinkML classification schema not found at {path}. schema_vocab expects "
            "to run from a repo checkout with the schema/ directory present."
        )
    with open(path, encoding="utf-8") as f:
        schema = yaml.safe_load(f)
    return {
        name: frozenset(((defn or {}).get("permissible_values") or {}).keys())
        for name, defn in schema.get("enums", {}).items()
    }


def dimension_values(field: str) -> frozenset[str]:
    """Return the permissible values for a classification dimension field.

    Raises ValueError for an unrecognized field, and KeyError (with the schema
    path) if the schema is missing the expected ``<field>_enum`` — so schema/rule
    drift fails with a diagnosable message rather than a bare lookup error.
    """
    if field not in DIMENSION_ENUMS:
        raise ValueError(
            f"Unknown classification dimension {field!r}; "
            f"expected one of {sorted(DIMENSION_ENUMS)}"
        )
    enum_name = DIMENSION_ENUMS[field]
    enums = _load_enums()
    if enum_name not in enums:
        raise KeyError(
            f"Schema at {default_schema_path()} is missing enum {enum_name!r} "
            f"for dimension {field!r}"
        )
    return enums[enum_name]


def status_values() -> frozenset[str]:
    """Return the permissible per-field ``status`` values from the schema.

    The single source of truth for the status vocabulary (classified /
    not_applicable / not_classified / conflict), mirroring dimension_values for
    the ``status`` field the sentinel→status migration adds (epic #116). Raises
    KeyError (with the schema path) if the schema is missing the status enum.
    """
    enums = _load_enums()
    if STATUS_ENUM not in enums:
        raise KeyError(
            f"Schema at {default_schema_path()} is missing enum {STATUS_ENUM!r}"
        )
    return enums[STATUS_ENUM]


def value_in_vocabulary(field: str, value: object) -> bool:
    """True if ``value`` is permissible for the dimension, or a sentinel.

    The membership test the rule drift checks use: a dimension's enum values plus
    SENTINEL_VALUES. Permissible values are always strings, so a non-string value
    (e.g. a list from a malformed rule like ``platform: [ILLUMINA, PACBIO]``) is
    reported as not-in-vocabulary rather than raising ``TypeError`` on the set
    membership test. Raises the same errors as ``dimension_values`` for an
    unrecognized field or a schema missing the expected enum.
    """
    return isinstance(value, str) and value in (dimension_values(field) | SENTINEL_VALUES)
