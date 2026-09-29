"""The activity declarations (#580): the bundled file's invariants, and what the loader refuses.

The loader's checks are tested on declarations written here, never by restating the
bundled file's rows: which dimensions a term passes is the file's to say.
"""

import pytest
import yaml

from meta_disco import activities
from meta_disco.models import CLASSIFICATION_FIELDS
from meta_disco.schema_vocab import activity_values


def _entry(term, **overrides):
    entry = {"term": term, "inputs": "many", "parent": "file", "passes": [], "reason": "why"}
    return {**entry, **overrides}


def _text(entries):
    return yaml.safe_dump({"activities": entries})


def _every_term(**overrides_by_term):
    return [_entry(term, **overrides_by_term.get(term, {})) for term in sorted(activity_values())]


def test_the_bundled_file_declares_every_term_of_the_enum():
    assert set(activities.declarations()) == activity_values()


def test_the_bundled_file_passes_nothing_across_an_unknown_step_and_never_data_type():
    declared = activities.declarations()
    assert declared[activities.UNKNOWN].passes == ()
    assert all("data_type" not in d.passes for d in declared.values())


def test_the_edge_rules_name_declared_terms():
    assert {activities.INDEXING, activities.CHECKSUM} <= set(activities.declarations())


def test_passes_come_back_in_classification_fields_order():
    written = list(reversed([f for f in CLASSIFICATION_FIELDS if f != "data_type"]))
    loaded = activities.load_activities(_text(_every_term(IndexingActivity={"passes": written})))
    assert loaded["IndexingActivity"].passes == tuple(f for f in CLASSIFICATION_FIELDS if f in written)


@pytest.mark.parametrize(
    "entries, message",
    [
        (_every_term()[1:], "no declaration"),
        ([*_every_term(), _entry("IndexingActivity")], "declared twice"),
        ([*_every_term(), _entry("CoffeeActivity")], "not a term"),
        (_every_term(IndexingActivity={"inputs": "several"}), "inputs"),
        (_every_term(IndexingActivity={"parent": "donor"}), "parent"),
        (_every_term(IndexingActivity={"passes": ["data_type"]}), "not slots"),
        (_every_term(IndexingActivity={"passes": ["colour"]}), "not slots"),
        (_every_term(IndexingActivity={"passes": ["platform", "platform"]}), "each slot once"),
        (_every_term(Activity={"passes": ["platform"]}), "passes nothing"),
        (_every_term(IndexingActivity={"reason": " "}), "reason"),
    ],
    ids=[
        "missing-term",
        "duplicate",
        "unknown-term",
        "bad-inputs",
        "bad-parent",
        "data-type",
        "not-a-slot",
        "repeated-slot",
        "unknown-step-passes",
        "no-reason",
    ],
)
def test_the_loader_refuses(entries, message):
    with pytest.raises(ValueError, match=message):
        activities.load_activities(_text(entries))


def test_the_loader_refuses_a_key_it_does_not_know():
    entries = _every_term()
    entries[0] = {**entries[0], "notes": "prose"}
    with pytest.raises(ValueError, match="exactly the keys"):
        activities.load_activities(_text(entries))


def test_the_loader_refuses_a_file_without_its_one_key():
    with pytest.raises(ValueError, match="one key"):
        activities.load_activities(yaml.safe_dump({"rows": []}))
