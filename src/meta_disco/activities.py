"""What each kind of step takes in, makes, and passes to its output, declared once (#580).

The vocabulary is ``activity_type_enum`` in the LinkML schema: AnVIL FSS's activity
types plus four of our own. The declarations are ``rules/activities.yaml``, whose shape
is the schema's ``ActivityDeclarations``: per term, its output and its inputs by role,
each role with its form (file or identifier), the ``data_type`` kinds it may carry,
whether it is required, whether an output has many of it, and what it passes.

**Checked when it loads.** The file is read through the pydantic model generated from
that class, which refuses an unknown key, a missing member, and a term, kind, form or
dimension outside its enum; ``data_type`` is not among the dimensions an input can pass.
PyYAML's silent keeping of the last of a repeated key is refused before that. The
checks that need the whole file are here, raising ``ValueError``: every term of the enum
declared exactly once, a role named once within a term, and ``Activity``, the step not
known, passing nothing. What it declares is then trusted: a reader does not re-check it.

**Who reads it today**: the index producer's inheritance (``INHERITED_FIELDS``) and its
code rule's ``sets`` are what ``IndexingActivity`` passes. Inheritance across the other
terms is #571's.
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
    """A YAML loader that refuses a key given twice, which PyYAML would otherwise keep the last of."""

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
    """The declarations by term, from ``text`` or the bundled file.

    Raises ``ValueError`` (pydantic's ``ValidationError`` is one) on any check the
    module docstring lists.
    """
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
