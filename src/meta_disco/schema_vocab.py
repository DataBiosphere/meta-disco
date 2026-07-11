"""Read the controlled classification vocabulary from the LinkML schema.

The LinkML schema ``classification.yaml`` is the canonical source of truth for the
permissible values of each classification dimension. It ships as package data of
``meta_disco.schema`` — it lives with the runtime that reads it — so this loads it
via ``importlib.resources`` and works whether installed as a wheel or run from a
checkout. The rule engine's emitted values are validated against these enums (see
``tests/test_rule_vocabulary.py``), keeping the rules and the schema in lockstep.
The ``schema/`` project is the LinkML tooling that maintains and validates it.
"""

from functools import lru_cache
from importlib.resources import files

import yaml

from .models import CLASSIFICATION_FIELDS

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


def default_schema_path():
    """The canonical LinkML classification schema, as a package-data resource.

    Returns an ``importlib.resources`` traversable (a filesystem path for a
    source/editable install), suitable for ``.read_text()`` and for naming the
    schema in error messages.

    Anchored on this module's own package (``{__package__}.schema``) rather than a
    hard-coded ``"meta_disco.schema"``, so it keeps resolving under whatever
    (import) package name the code is loaded under.
    """
    return files(f"{__package__}.schema") / "classification.yaml"


@lru_cache(maxsize=None)
def _load_enums() -> dict[str, frozenset[str]]:
    """Load all enums from the schema as ``{enum_name: {permissible values}}``."""
    resource = default_schema_path()
    try:
        text = resource.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        # The schema ships as package data of this module's package; a bare errno-2
        # here means the build/install dropped it, not that the caller did anything
        # wrong. Name the package dynamically, matching the {__package__} anchor above.
        raise FileNotFoundError(
            f"Classification schema not found at {resource}. It should ship as "
            f"package data of {__package__}.schema — reinstall/rebuild the package "
            "(uv sync), or run from a checkout where src/meta_disco/schema/ is present."
        ) from e
    schema = yaml.safe_load(text)
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
    """True if ``value`` is a permissible *value* for the dimension (strict).

    Membership against the dimension's enum only — the single value check for
    every classification value, on all sides:
    - *antecedent* values (``when`` / assay ``conditions``, matched against actual
      values in the rule engine, where a status is a typo — #115),
    - *emitted* values (``then`` values, inferred ``assay_type``), which since
      #133 are always real dimension values (a field a rule declares
      non-classified is authored in ``then.status``, not as a sentinel value), and
    - *output* values (real-or-null since Stage 3, #116).
    A status (``not_applicable`` / ``not_classified`` / ``classified`` /
    ``conflict``) never belongs in a value slot, so it is correctly rejected here.

    Permissible values are always strings, so a non-string value (e.g. a list from
    a malformed rule like ``platform: [ILLUMINA, PACBIO]``) is reported as
    not-in-vocabulary rather than raising ``TypeError`` on the set membership test.
    Raises the same errors as ``dimension_values`` for an unrecognized field or a
    schema missing the expected enum.
    """
    return isinstance(value, str) and value in dimension_values(field)
