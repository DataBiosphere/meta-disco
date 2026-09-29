"""What each kind of step passes from its inputs to its outputs, declared once (#580).

The vocabulary is ``activity_type_enum`` in the LinkML schema: AnVIL FSS's activity
types plus four of our own. This module reads the declarations beside it,
``rules/activities.yaml``, a mapping whose one key is ``activities``::

    activities:
      - term: IndexingActivity
        inputs: one          # an output has one input of the step, or `many`
        parent: file         # an input is a file, or an `identifier` (a sample)
        passes: [data_modality, assay_type, platform, instrument_model, reference_assembly]
        reason: An index describes the data it points into.

**Checked when it loads**, raising ``ValueError`` naming the term: the terms are exactly
the enum's, each once; ``inputs`` and ``parent`` are one of their two values; ``passes``
names classification slots, each once and never ``data_type``, which never passes (a
VCF is not an alignment, ADR-0002 decision 8); ``Activity``, the step not known, passes nothing; and
every term carries a ``reason``. ``passes`` is returned in ``CLASSIFICATION_FIELDS``
order, whatever order the file writes it in, so a reader can compare it with a tuple
built from that constant.

**Who reads it today**: the index producer's inheritance (``INHERITED_FIELDS``) and its
code rule's ``sets`` are ``IndexingActivity``'s ``passes``. Inheritance across the other
terms is #571's.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from importlib.resources import files

import yaml

from .models import CLASSIFICATION_FIELDS
from .schema_vocab import activity_values

UNKNOWN = "Activity"
INDEXING = "IndexingActivity"
CHECKSUM = "ChecksumActivity"

ONE = "one"
MANY = "many"
INPUTS = (ONE, MANY)
PARENT_FILE = "file"
PARENT_IDENTIFIER = "identifier"
PARENTS = (PARENT_FILE, PARENT_IDENTIFIER)

_KEYS = {"term", "inputs", "parent", "passes", "reason"}


@dataclass(frozen=True)
class Declaration:
    """One term's declaration: its inputs' number and form, and what passes to its outputs."""

    term: str
    inputs: str
    parent: str
    passes: tuple[str, ...]
    reason: str


def default_activities_resource():
    """The bundled declarations, as package data beside the rule set."""
    return files(f"{__package__}.rules") / "activities.yaml"


def load_activities(text: str | None = None) -> dict[str, Declaration]:
    """The declarations by term, from ``text`` or the bundled file; ``ValueError`` on any check the module docstring lists."""
    if text is None:
        text = default_activities_resource().read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    if not isinstance(document, dict) or set(document) != {"activities"}:
        raise ValueError("activities file: expected a mapping whose one key is 'activities'")
    entries = document["activities"]
    if not isinstance(entries, list):
        raise ValueError("activities file: 'activities' must be a list")
    declared: dict[str, Declaration] = {}
    for entry in entries:
        declaration = _declaration(entry)
        if declaration.term in declared:
            raise ValueError(f"activity {declaration.term!r}: declared twice")
        declared[declaration.term] = declaration
    terms = activity_values()
    missing = sorted(terms - set(declared))
    if missing:
        raise ValueError(f"activity_type_enum terms with no declaration: {missing}")
    return declared


def _declaration(entry: object) -> Declaration:
    if not isinstance(entry, dict) or set(entry) != _KEYS:
        raise ValueError(f"activity entry {entry!r}: expected exactly the keys {sorted(_KEYS)}")
    term = entry["term"]
    if term not in activity_values():
        raise ValueError(f"activity {term!r}: not a term of activity_type_enum")
    if entry["inputs"] not in INPUTS:
        raise ValueError(f"activity {term!r}: inputs {entry['inputs']!r} is not one of {INPUTS}")
    if entry["parent"] not in PARENTS:
        raise ValueError(f"activity {term!r}: parent {entry['parent']!r} is not one of {PARENTS}")
    passes = entry["passes"]
    if not isinstance(passes, list) or len(set(passes)) != len(passes):
        raise ValueError(f"activity {term!r}: passes must be a list naming each slot once")
    unknown = [slot for slot in passes if slot not in CLASSIFICATION_FIELDS or slot == "data_type"]
    if unknown:
        raise ValueError(f"activity {term!r}: passes {unknown}, which are not slots an output can take")
    if term == UNKNOWN and passes:
        raise ValueError(f"activity {UNKNOWN!r}: the step not known passes nothing, not {passes}")
    reason = entry["reason"]
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError(f"activity {term!r}: needs a reason")
    return Declaration(
        term=term,
        inputs=entry["inputs"],
        parent=entry["parent"],
        passes=tuple(slot for slot in CLASSIFICATION_FIELDS if slot in passes),
        reason=reason,
    )


@cache
def declarations() -> dict[str, Declaration]:
    """The bundled declarations, loaded once."""
    return load_activities()


def passes(term: str) -> tuple[str, ...]:
    """The dimensions an output of ``term`` takes from its inputs, in ``CLASSIFICATION_FIELDS`` order."""
    return declarations()[term].passes
