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
