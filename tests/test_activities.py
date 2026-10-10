"""The activity declarations (#580): what the loader refuses, and how it reads what passes.

The loader's checks are tested on declarations written here, never by restating the
bundled file's rows: which dimensions a term passes is the file's to say.
"""

import pytest
import yaml

from meta_disco import activities, code_rules, schema_vocab
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
        (
            _every_term(IndexActivity=_entry("IndexActivity", [_input(form=["identifier"], passes=["platform"])])),
            "nothing to pass",
        ),
        (
            _every_term(IndexActivity={"term": "IndexActivity", "output": {"form": ["file"]}, "reason": "why"}),
            "declares one of output and inputs",
        ),
        (
            _every_term(
                VariantProcessingActivity={"term": "VariantProcessingActivity", "abstract": True, "reason": "why"}
            ),
            "abstract, so it declares",
        ),
        (_every_term(Activity={"term": "Activity", "reason": "why"}), "no ancestor does"),
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
        "identifier-passes",
        "output-without-inputs",
        "abstract-takes",
        "nothing-to-take",
    ],
)
def test_the_loader_refuses(entries, message):
    with pytest.raises(ValueError, match=message):
        activities.load_activities(_text(entries))


def test_the_loader_refuses_a_key_given_twice():
    text = _text(_every_term()) + "- term: Activity\n  reason: a\n  reason: b\n"
    with pytest.raises(ValueError, match="duplicate key"):
        activities.load_activities(text)


def _taking(term):
    """``term`` declared by its reason alone, taking its output and inputs from an ancestor."""
    return {"term": term, "reason": f"{term}'s own reason"}


def test_a_term_declared_by_its_reason_alone_takes_its_abstract_parents_inputs():
    parent = _entry("VariantProcessingActivity", [_input("processed", passes=["platform"])], abstract=True)
    entries = _every_term(VariantProcessingActivity=parent, VariantFilterActivity=_taking("VariantFilterActivity"))
    loaded = activities.load_activities(_text(entries))
    assert loaded["VariantFilterActivity"].inputs == loaded["VariantProcessingActivity"].inputs
    assert activities._passes(loaded["VariantFilterActivity"]) == ("platform",)
    assert not loaded["VariantFilterActivity"].abstract


def test_a_term_declared_by_its_reason_alone_under_a_concrete_parent_is_refused():
    """The nearest ancestor that declares is concrete (AnalysisActivity), so its declaration is not taken."""
    entries = _every_term(VariantProcessingActivity=_taking("VariantProcessingActivity"))
    with pytest.raises(ValueError, match="'VariantProcessingActivity': declares no output or inputs, and its parent"):
        activities.load_activities(_text(entries))


def test_a_step_may_not_name_an_abstract_term():
    entries = _every_term(
        VariantProcessingActivity=_entry("VariantProcessingActivity", abstract=True),
        VariantFilterActivity=_taking("VariantFilterActivity"),
    )
    loaded = activities.load_activities(_text(entries))
    with pytest.raises(ValueError, match=r"row x: 'VariantProcessingActivity' is abstract; .*VariantFilterActivity"):
        activities.require_writable("VariantProcessingActivity", "row x", loaded)
    activities.require_writable("VariantFilterActivity", "row x", loaded)


def test_no_edge_rule_names_an_abstract_term():
    for rule in code_rules.EDGE_RULES:
        activities.require_writable(rule.activity, rule.id)


def test_an_activitys_ancestors_are_its_is_a_chain_nearest_first():
    assert schema_vocab.activity_ancestors("VariantFilterActivity") == (
        "VariantProcessingActivity",
        "AnalysisActivity",
        "Activity",
    )
    assert schema_vocab.activity_ancestors("Activity") == ()
    with pytest.raises(ValueError, match="CoffeeActivity"):
        schema_vocab.activity_ancestors("CoffeeActivity")


# --- read-through (#621) -------------------------------------------------------------------


def _read_through_terms(through=None, member=None):
    """Every term, MergeActivity's one role reading through CohortDefinitionActivity's ``member``."""
    lst = {**_input("input_list", read_through="member", passes=["platform"]), **(through or {})}
    listed = {**_input("member", many=True), **(member or {})}
    return _every_term(
        MergeActivity=_entry("MergeActivity", [lst]),
        CohortDefinitionActivity=_entry("CohortDefinitionActivity", [listed]),
    )


def test_a_role_reads_through_a_role_some_term_declares():
    loaded = activities.load_activities(_text(_read_through_terms()))
    assert [i.read_through for i in loaded["MergeActivity"].inputs] == ["member"]


@pytest.mark.parametrize(
    "entries, message",
    [
        (_read_through_terms(through={"passes": None}), "reads through 'member' but passes nothing"),
        (_read_through_terms(through={"read_through": "listed"}), "which no term declares"),
        (_read_through_terms(member={"passes": ["platform"]}), "passes from its own inputs"),
    ],
    ids=["passes-nothing", "undeclared-role", "role-passes-itself"],
)
def test_the_loader_refuses_a_read_through(entries, message):
    with pytest.raises(ValueError, match=message):
        activities.load_activities(_text(entries))


def test_read_through_names_each_role_of_a_term_that_reads_through_its_parent():
    roles = activities.read_through(activities.COHORT_MERGE)
    assert roles and set(roles) <= {i.role for i in activities.declarations()[activities.COHORT_MERGE].inputs}
    for through in roles.values():
        assert any(through in {i.role for i in d.inputs} for d in activities.declarations().values())


def test_the_variant_kind_passes_across_an_index_a_merge_and_a_cohort_merge_only():
    """A call creates a kind and a filter can narrow one, so neither passes it (#654)."""
    passing = {term for term in activities.declarations() if "variant_kind" in activities.passes(term)}
    assert passing == {activities.INDEXING, activities.MERGE, activities.COHORT_MERGE}
