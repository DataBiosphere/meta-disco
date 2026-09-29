"""Loads ``rules/activities.yaml``: what each activity takes in and passes on (#580).

Its shape is the schema's ``ActivityDeclarations``, enforced by the generated model.
The checks that need the whole file are here: every term declared once, roles unique
within a term, and ``Activity`` passing nothing. Readers trust the result.
"""

from __future__ import annotations

from functools import cache
from importlib.resources import files

import yaml

from .models import CLASSIFICATION_FIELDS
from .schema.classification_model import ActivityDeclaration, ActivityDeclarations
from .schema_vocab import activity_values

UNKNOWN = "Activity"
INDEXING = "IndexingActivity"
CHECKSUM = "ChecksumActivity"


class _UniqueKeyLoader(yaml.SafeLoader):
    """Refuses a repeated key, which PyYAML would silently keep the last of."""

    def construct_mapping(self, node, deep=False):
        seen: set = set()
        for key_node, _value in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ValueError(f"activities file line {key_node.start_mark.line + 1}: key {key!r} given twice")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def default_activities_resource():
    """The bundled declarations, as package data beside the rule set."""
    return files(f"{__package__}.rules") / "activities.yaml"


def load_activities(text: str | None = None) -> dict[str, ActivityDeclaration]:
    """The declarations by term, from ``text`` or the bundled file; ``ValueError`` when invalid."""
    if text is None:
        text = default_activities_resource().read_text(encoding="utf-8")
    document = ActivityDeclarations.model_validate(yaml.load(text, Loader=_UniqueKeyLoader))
    declared: dict[str, ActivityDeclaration] = {}
    for declaration in document.activities:
        term = str(declaration.term)
        if term in declared:
            raise ValueError(f"activity {term!r}: declared twice")
        roles = [i.role for i in declaration.inputs]
        if len(set(roles)) != len(roles):
            raise ValueError(f"activity {term!r}: a role is named twice in {roles}")
        declared[term] = declaration
    missing = sorted(activity_values() - set(declared))
    if missing:
        raise ValueError(f"activity_type_enum terms with no declaration: {missing}")
    unknown = _passes(declared[UNKNOWN])
    if unknown:
        raise ValueError(f"activity {UNKNOWN!r}: the step not known passes nothing, not {unknown}")
    return declared


def _passes(declaration: ActivityDeclaration) -> tuple[str, ...]:
    passed = {str(slot) for i in declaration.inputs for slot in i.passes or ()}
    return tuple(slot for slot in CLASSIFICATION_FIELDS if slot in passed)


@cache
def declarations() -> dict[str, ActivityDeclaration]:
    """The bundled declarations, loaded once."""
    return load_activities()


def passes(term: str) -> tuple[str, ...]:
    """The dimensions an output of ``term`` takes from any of its inputs, in ``CLASSIFICATION_FIELDS`` order."""
    return _passes(declarations()[term])
