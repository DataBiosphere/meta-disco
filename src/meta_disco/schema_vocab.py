"""Read the controlled classification vocabulary from the LinkML schema.

The LinkML schema ``classification.yaml`` is the canonical source of truth for the
permissible values of each classification dimension. It ships as package data of
``meta_disco.schema`` — it lives with the runtime that reads it — so this loads it
via ``importlib.resources`` and works whether installed as a wheel or run from a
checkout. The rule engine's emitted values are validated against these enums (see
``tests/test_rule_vocabulary.py``), keeping the rules and the schema in lockstep.
The ``schema/`` project is the LinkML tooling that maintains and validates it.
"""

from collections.abc import Iterable
from functools import cache
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

# The enum defining the permissible synthetic-marker kinds on an evidence entry
# (issue #228): not_classified / conflict.
MARKER_ENUM = "evidence_marker_enum"
# The reference-build ``name_source`` vocabulary (issue #354).
NAME_SOURCE_ENUM = "reference_name_source_enum"
# The assembly families a reference build's ``base`` may name (issue #473).
REFERENCE_FAMILY_ENUM = "reference_family_enum"

# The claim-record vocabularies (issue #392): the kind of source behind a claim,
# the states a claim can take when it consulted a source and produced no value,
# and the keys an external claim can be joined to one of our files by.
SOURCE_TYPE_ENUM = "source_type_enum"
IMPORTER_SOURCE_TYPE_ENUM = "importer_source_type_enum"
CLAIM_STATE_ENUM = "claim_state_enum"
JOIN_KEY_ENUM = "join_key_enum"

# The derivation edge's two vocabularies (issue #450): the verb, and the kind of file
# the edge points at.
RELATION_ENUM = "relation_enum"
PARENT_KIND_ENUM = "parent_kind_enum"


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


@cache
def _load_schema_enums() -> dict[str, dict]:
    """Load the schema's ``enums`` block, each permissible value with its definition."""
    resource = None
    try:
        resource = default_schema_path()
        text = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, KeyError, ModuleNotFoundError) as e:
        # The schema ships as package data of this module's package; a missing file
        # here means the build/install dropped it, not that the caller did anything
        # wrong. KeyError: a zip-backed resource reports a missing entry that way
        # rather than as FileNotFoundError. ModuleNotFoundError: files() raises it if
        # the meta_disco.schema package was dropped entirely, leaving resource None.
        # Name the package dynamically, matching the {__package__} anchor above.
        lead = (
            f"Classification schema not found at {resource}"
            if resource is not None
            else f"Classification schema not found in the {__package__}.schema package"
        )
        raise FileNotFoundError(
            f"{lead}. It should ship as package data of {__package__}.schema — "
            "reinstall/rebuild the package (uv sync), or run from a checkout where "
            "src/meta_disco/schema/ is present."
        ) from e
    schema = yaml.safe_load(text)
    return {name: dict((defn or {}).get("permissible_values") or {}) for name, defn in schema.get("enums", {}).items()}


@cache
def _load_enums() -> dict[str, frozenset[str]]:
    """Load all enums from the schema as ``{enum_name: {permissible values}}``."""
    return {name: frozenset(values) for name, values in _load_schema_enums().items()}


def dimension_values(field: str) -> frozenset[str]:
    """Return the permissible values for a classification dimension field.

    Raises ValueError for an unrecognized field, and KeyError (with the schema
    path) if the schema is missing the expected ``<field>_enum`` — so schema/rule
    drift fails with a diagnosable message rather than a bare lookup error.
    """
    if field not in DIMENSION_ENUMS:
        raise ValueError(f"Unknown classification dimension {field!r}; expected one of {sorted(DIMENSION_ENUMS)}")
    enum_name = DIMENSION_ENUMS[field]
    enums = _load_enums()
    if enum_name not in enums:
        raise KeyError(f"Schema at {default_schema_path()} is missing enum {enum_name!r} for dimension {field!r}")
    return enums[enum_name]


def value_ancestors(field: str, value: str) -> tuple[str, ...]:
    """The terms above ``value`` in its dimension's ``is_a`` hierarchy, nearest first.

    Empty for a term with no parent, which is every term of an enum that declares no
    ``is_a``. ``reference_assembly_enum`` is the one that does (#473): a hybrid's
    ancestors are its T2T release and then ``CHM13``. Raises ValueError for a value
    outside the dimension's vocabulary or an ``is_a`` chain that names a missing
    term or loops, and the same errors as ``dimension_values`` for an unrecognized
    field or a missing enum.
    """
    if not value_in_vocabulary(field, value):
        raise ValueError(f"{value!r} is not a {field} term")
    values = _load_schema_enums()[DIMENSION_ENUMS[field]]
    ancestors: list[str] = []
    parent = (values[value] or {}).get("is_a")
    while parent is not None:
        if parent not in values or parent in ancestors or parent == value:
            raise ValueError(f"{field} term {value!r} has a broken is_a chain at {parent!r}")
        ancestors.append(parent)
        parent = (values[parent] or {}).get("is_a")
    return tuple(ancestors)


def most_specific(field: str, values: Iterable[str]) -> str | None:
    """The one of ``values`` that every other is, or sits below in the ``is_a`` hierarchy; None if they do not nest.

    Values that nest are one answer at two levels of detail — ``CHM13`` and
    ``T2T-CHM13v2.0`` are both true of a v2.0 file — so the deepest is the answer
    (#473). Two siblings (``T2T-CHM13v1.0`` beside ``T2T-CHM13v2.0``) do not nest,
    and neither does anything outside the vocabulary (``not_applicable``) beside a
    different value. A single value is returned as it is, in the vocabulary or not.
    """
    distinct = set(values)
    if len(distinct) == 1:
        return next(iter(distinct))
    if not all(value_in_vocabulary(field, v) for v in distinct):
        return None
    for candidate in distinct:
        above = value_ancestors(field, candidate)
        if all(v == candidate or v in above for v in distinct):
            return candidate
    return None


def status_values() -> frozenset[str]:
    """Return the permissible per-field ``status`` values from the schema.

    The single source of truth for the status vocabulary (classified /
    not_applicable / not_classified / conflict), mirroring dimension_values for
    the ``status`` field the sentinel→status migration adds (epic #116). Raises
    KeyError (with the schema path) if the schema is missing the status enum.
    """
    return _enum_values(STATUS_ENUM)


def marker_values() -> frozenset[str]:
    """Return the permissible synthetic-marker kinds from the schema.

    The single source of truth for the evidence ``marker`` vocabulary
    (not_classified / conflict, issue #228), so ``rule_engine``'s marker constants
    stay pinned to the schema. Raises KeyError (with the schema path) if the schema
    is missing the marker enum.
    """
    return _enum_values(MARKER_ENUM)


def name_source_values() -> frozenset[str]:
    """Return the permissible ``ReferenceBuild.name_source`` values from the schema.

    The single source of truth for where a declared reference name may come
    from (reference_field / command_line, issue #354), so the resolver's
    ``NAME_SOURCE_*`` constants stay pinned to the schema. Raises KeyError (with
    the schema path) if the schema is missing the enum.
    """
    return _enum_values(NAME_SOURCE_ENUM)


def reference_family_values() -> frozenset[str]:
    """Return the assembly families from the schema, the values ``ReferenceBuild.base`` may take.

    The ``reference_assembly_enum`` terms with no ``is_a`` parent, listed as their own
    enum so the schema can range ``base`` over them (#473). Raises KeyError (with the
    schema path) if the schema is missing the enum.
    """
    return _enum_values(REFERENCE_FAMILY_ENUM)


def relation_values() -> frozenset[str]:
    """Return the permissible derivation verbs from the schema.

    The single source of truth for ``DerivationEdge.relation`` (issue #450), so a
    producer emitting an edge stays pinned to the schema. Raises KeyError (with the
    schema path) if the schema is missing the enum.
    """
    return _enum_values(RELATION_ENUM)


def parent_kind_values() -> frozenset[str]:
    """Return the permissible ``DerivationEdge.parent_kind`` values from the schema.

    The single source of truth for what kind of file an edge may point at (issue #450),
    so the index producer's category-to-kind map stays pinned to the schema. Raises
    KeyError (with the schema path) if the schema is missing the enum.
    """
    return _enum_values(PARENT_KIND_ENUM)


def source_type_values() -> frozenset[str]:
    """Return the permissible claim ``source_type`` values from the schema.

    The single source of truth for the kind-of-source vocabulary (issue #392), so
    ``models``' ``SOURCE_*`` constants stay pinned to the schema and ``make_claim``
    rejects a source_type the schema does not define. Raises KeyError (with the
    schema path) if the schema is missing the enum.
    """
    return _enum_values(SOURCE_TYPE_ENUM)


def importer_source_type_values() -> frozenset[str]:
    """Return the permissible values of an evidence file's envelope ``source_type``.

    The kinds an importer may write (#421): a strict subset of
    :func:`source_type_values`, excluding both the inference kinds and
    ``wrangler_annotation``, which enters as rules rather than as evidence (contract
    1.6). ``models``' ``IMPORTER_SOURCE_TYPES`` is pinned to it so the envelope check
    and the schema gate refuse the same files. Raises KeyError (with the schema path)
    if the schema is missing the enum.
    """
    return _enum_values(IMPORTER_SOURCE_TYPE_ENUM)


def claim_state_values() -> frozenset[str]:
    """Return the permissible ``claim_state`` values from the schema.

    The single source of truth for the states a claim takes when it consulted a
    source and produced no vocabulary value (unmapped / no_vocabulary_term /
    declined, issue #392). Distinct from ``status_values`` — these never appear as
    a dimension's status. Raises KeyError (with the schema path) if the schema is
    missing the enum.
    """
    return _enum_values(CLAIM_STATE_ENUM)


def join_key_values() -> frozenset[str]:
    """Return the permissible ``join_key`` values from the schema.

    The single source of truth for the keys an external claim may be attached to
    one of our files by (issue #392/#390). Raises KeyError (with the schema path)
    if the schema is missing the enum.
    """
    return _enum_values(JOIN_KEY_ENUM)


def _enum_values(enum_name: str) -> frozenset[str]:
    """The permissible values of one named schema enum; KeyError (with the schema path) if it is missing."""
    enums = _load_enums()
    if enum_name not in enums:
        raise KeyError(f"Schema at {default_schema_path()} is missing enum {enum_name!r}")
    return enums[enum_name]


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
