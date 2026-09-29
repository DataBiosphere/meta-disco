"""The activity declarations (#580): what the loader refuses, and how it reads what passes.

The loader's checks are tested on declarations written here, never by restating the
bundled file's rows: which dimensions a term passes is the file's to say.
"""

import pytest
import yaml

from meta_disco import activities, schema_vocab
from meta_disco.models import CLASSIFICATION_FIELDS
from meta_disco.schema_vocab import activity_values


def _input(role="input", **overrides):
    return {"role": role, "form": ["file"], "required": True, "many": False, **overrides}


def _entry(name, inputs=None, **overrides):
    entry = {"term": name, "output": {"form": ["file"]}, "inputs": inputs or [_input()], "reason": "why"}
    return {**entry, **overrides}


def _every_term(**entries_by_term):
    return [entries_by_term.get(term) or _entry(term) for term in sorted(activity_values())]


def _text(entries):
    return yaml.safe_dump({"activities": entries})


def test_the_bundled_file_loads_and_declares_every_term_of_the_enum():
    assert set(activities.declarations()) == activity_values()


def test_the_dimensions_an_input_can_pass_are_every_dimension_but_data_type():
    """`passed_dimension_enum` is held to `CLASSIFICATION_FIELDS`, so a new dimension cannot fall out of `passes`."""
    assert set(schema_vocab._enum_values("passed_dimension_enum")) == set(CLASSIFICATION_FIELDS) - {"data_type"}


def test_passes_is_every_role_s_in_classification_fields_order():
    reads = _input("reads", many=True, passes=["instrument_model", "platform"])
    reference = _input("reference", passes=["reference_assembly"])
    entries = _every_term(AlignmentActivity=_entry("AlignmentActivity", [reads, reference]))
    loaded = activities.load_activities(_text(entries))
    passed = {"instrument_model", "platform", "reference_assembly"}
    assert activities._passes(loaded["AlignmentActivity"]) == tuple(f for f in CLASSIFICATION_FIELDS if f in passed)


@pytest.mark.parametrize(
    "entries, message",
    [
        (_every_term()[1:], "no declaration"),
        ([*_every_term(), _entry("IndexActivity")], "declared twice"),
        ([*_every_term(), _entry("CoffeeActivity")], "CoffeeActivity"),
        (_every_term(IndexActivity=_entry("IndexActivity", [_input(passes=["data_type"])])), "data_type"),
        (_every_term(IndexActivity=_entry("IndexActivity", [_input(form=["donor"])])), "donor"),
        (_every_term(IndexActivity=_entry("IndexActivity", [_input(kind=["spreadsheet"])])), "spreadsheet"),
        (_every_term(IndexActivity=_entry("IndexActivity", [{"role": "x", "form": ["file"]}])), "required"),
        (_every_term(IndexActivity=_entry("IndexActivity", notes="prose")), "notes"),
        (_every_term(IndexActivity=_entry("IndexActivity", [_input("a"), _input("a")])), "named twice"),
        (_every_term(Activity=_entry("Activity", [_input(passes=["platform"])])), "passes nothing"),
    ],
    ids=[
        "missing-term",
        "duplicate-term",
        "unknown-term",
        "data-type-passes",
        "unknown-form",
        "unknown-kind",
        "missing-member",
        "unknown-key",
        "repeated-role",
        "unknown-step-passes",
    ],
)
def test_the_loader_refuses(entries, message):
    with pytest.raises(ValueError, match=message):
        activities.load_activities(_text(entries))


def test_the_loader_refuses_a_key_given_twice():
    text = _text(_every_term()) + "- term: Activity\n  reason: a\n  reason: b\n"
    with pytest.raises(ValueError, match="given twice"):
        activities.load_activities(text)
