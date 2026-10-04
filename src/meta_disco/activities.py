"""Loads ``rules/activities.yaml``: what each activity takes in and passes on (#580).

Its shape is the schema's ``ActivityDeclarations``, enforced by the generated model.
The checks it cannot state are here: every term declared once, roles unique within a
term, ``Activity`` passing nothing, no role that can only be an identifier passing
anything, and no role passing ``data_type``, which describes the file itself (contract
4.9). Readers trust the result.

**A term may take its declaration from an abstract ancestor** (#610). A term declared
with a reason but no ``output`` and ``inputs`` takes both from its nearest ``is_a``
ancestor that declares them, which must be **abstract**, so a family of steps that pass
the same (filtering, annotating a callset) states what passes once. Terms in between that
declare by reason only are passed over. No step names an abstract term
(:func:`require_writable`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

import yaml

from .models import CLASSIFICATION_FIELDS
from .schema.classification_model import ActivityDeclaration, ActivityDeclarations, ActivityEnd, InputRole
from .schema_vocab import activity_ancestors, activity_values
from .slot_map import unique_key_loader

DATA_TYPE = "data_type"
UNKNOWN = "Activity"
INDEXING = "IndexActivity"
CHECKSUM = "ChecksumActivity"
VARIANT_CALL = "VariantCallActivity"
MERGE = "MergeActivity"


_UniqueKeyLoader = unique_key_loader("activities file")


@dataclass(frozen=True)
class Declared:
    """One term's declaration as its readers see it: what the step makes and its input roles,
    its own or taken from its nearest declaring ancestor."""

    output: ActivityEnd
    inputs: tuple[InputRole, ...]
    abstract: bool = False


def default_activities_resource():
    """The bundled declarations, as package data beside the rule set."""
    return files(f"{__package__}.rules") / "activities.yaml"


def load_activities(text: str | None = None) -> dict[str, Declared]:
    """The declarations by term, from ``text`` or the bundled file; ``ValueError`` when invalid.

    A term declared without ``output`` and ``inputs`` is returned with its nearest declaring
    ancestor's.
    """
    if text is None:
        text = default_activities_resource().read_text(encoding="utf-8")
    document = ActivityDeclarations.model_validate(yaml.load(text, Loader=_UniqueKeyLoader))
    given: dict[str, ActivityDeclaration] = {}
    for declaration in document.activities:
        term = str(declaration.term)
        if term in given:
            raise ValueError(f"activity {term!r}: declared twice")
        if (declaration.output is None) != (declaration.inputs is None):
            raise ValueError(f"activity {term!r}: declares one of output and inputs; it declares both, or takes both")
        if declaration.abstract and declaration.inputs is None:
            raise ValueError(f"activity {term!r}: abstract, so it declares what its children take")
        given[term] = declaration
    missing = sorted(activity_values() - set(given))
    if missing:
        raise ValueError(f"activity_type_enum terms with no declaration: {missing}")
    declared = {term: _inherited(term, given) for term in given}
    for term, declaration in declared.items():
        roles = [i.role for i in declaration.inputs]
        if len(set(roles)) != len(roles):
            raise ValueError(f"activity {term!r}: a role is named twice in {roles}")
        for i in declaration.inputs:
            if i.passes and "file" not in {str(f) for f in i.form}:
                raise ValueError(f"activity {term!r}: role {i.role!r} is an identifier, which has nothing to pass")
            if DATA_TYPE in _role_slots(i):
                raise ValueError(f"activity {term!r}: role {i.role!r} passes {DATA_TYPE}, which is never carried")
    unknown = _passes(declared[UNKNOWN])
    if unknown:
        raise ValueError(f"activity {UNKNOWN!r}: the step not known passes nothing, not {unknown}")
    return declared


def _inherited(term: str, given: dict[str, ActivityDeclaration]) -> Declared:
    """``term``'s declaration, its output and inputs taken from its nearest declaring ancestor where it states none.

    That ancestor must be abstract: a term may not take a concrete term's declaration, so
    a child of one that declares (``AnalysisActivity``) declares its own.
    """
    declaration = given[term]
    for source in (declaration, *(given[a] for a in activity_ancestors(term))):
        if source.output is not None and source.inputs is not None:
            if source is not declaration and not source.abstract:
                raise ValueError(f"activity {term!r}: declares no output or inputs, and its parent is not abstract")
            return Declared(source.output, tuple(source.inputs), bool(declaration.abstract))
    raise ValueError(f"activity {term!r}: declares no output or inputs, and no ancestor does")


def _role_slots(role) -> set[str]:
    """The dimensions one input role declares it passes."""
    return {str(slot) for slot in role.passes or ()}


def _ordered(slots: set[str]) -> tuple[str, ...]:
    return tuple(slot for slot in CLASSIFICATION_FIELDS if slot in slots)


def _passes(declaration: Declared) -> tuple[str, ...]:
    return _ordered({slot for i in declaration.inputs for slot in _role_slots(i)})


@cache
def declarations() -> dict[str, Declared]:
    """The bundled declarations, loaded once."""
    return load_activities()


def require_writable(term: str, at: str, declared: Mapping[str, Declared] | None = None) -> None:
    """Raise ``ValueError`` naming ``at`` where ``term`` is abstract: a step names one of its children.

    ``declared`` defaults to the bundled declarations.
    """
    declared = declarations() if declared is None else declared
    if declared[term].abstract:
        children = sorted(t for t in declared if term in activity_ancestors(t))
        raise ValueError(f"{at}: {term!r} is abstract; a step names one of {children}")


def passes(term: str) -> tuple[str, ...]:
    """The dimensions an output of ``term`` takes from any of its inputs, in ``CLASSIFICATION_FIELDS`` order."""
    return _passes(declarations()[term])


@cache
def role_passes(term: str) -> dict[str, tuple[str, ...]]:
    """Per input role of ``term`` that passes anything, the dimensions it passes, in ``CLASSIFICATION_FIELDS`` order.

    Cached, since reconcile asks once per child; callers must not change the dict.
    """
    return {i.role: _ordered(_role_slots(i)) for i in declarations()[term].inputs if i.passes}


def carried() -> tuple[str, ...]:
    """Every dimension some activity passes from an input, in ``CLASSIFICATION_FIELDS`` order (``data_type`` never is)."""
    return _ordered({slot for term in declarations() for slot in passes(term)})


def agreed(terms: Iterable[str]) -> str | None:
    """The activity every one of ``terms`` agrees on, or None where two disagree.

    The generic :data:`UNKNOWN` (``Activity``, the step not known) agrees with any: the
    agreed activity is the one specific term named, or ``UNKNOWN`` where only it is.
    """
    specific = {t for t in terms if t != UNKNOWN}
    if len(specific) > 1:
        return None
    return next(iter(specific), UNKNOWN)
