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

from .models import NOT_APPLICABLE, NOT_CLASSIFIED

# Sentinel values that rules currently emit as classification *values*. Per the
# schema these are slated to move into a separate ``status`` field (issues #56,
# #88); until that migration lands, the vocabulary check accepts them alongside
# real enum values.
SENTINEL_VALUES = frozenset({NOT_APPLICABLE, NOT_CLASSIFIED})

# Classification field -> the enum that defines its permissible values.
DIMENSION_ENUMS = {
    "data_modality": "data_modality_enum",
    "data_type": "data_type_enum",
    "reference_assembly": "reference_assembly_enum",
    "assay_type": "assay_type_enum",
    "platform": "platform_enum",
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
    with open(default_schema_path()) as f:
        schema = yaml.safe_load(f)
    return {
        name: frozenset((defn.get("permissible_values") or {}).keys())
        for name, defn in schema.get("enums", {}).items()
    }


def dimension_values(field: str) -> frozenset[str]:
    """Return the permissible values for a classification dimension field."""
    return _load_enums()[DIMENSION_ENUMS[field]]
