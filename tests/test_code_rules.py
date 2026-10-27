"""The rules and markers written in Python are declared once, in ``code_rules`` (#572)."""

import ast
import re
from pathlib import Path

import pytest

from meta_disco import activities, code_rules, models, schema_vocab
from meta_disco.models import CLASSIFICATION_FIELDS, SOURCE_TYPES
from meta_disco.rule_loader import get_unified_rules

DECLARED = (
    *code_rules.CODE_RULES,
    *code_rules.MARKERS,
    *code_rules.EDGE_RULES,
    *code_rules.SAMPLE_RULES,
    *code_rules.ENTITY_RULES,
    *code_rules.IDENTITY_CHECKS,
)
SOURCES = [*Path("src/meta_disco").rglob("*.py"), *Path("scripts").rglob("*.py")]


def literal_rule_ids(source: str) -> list[tuple[int, str]]:
    """Every rule id written as a string where a claim or marker is built.

    Three spellings: ``rule_id="x"`` passed to a call; ``"rule_id": "x"`` in a dict that
    also carries a ``reason``, which every evidence entry does (a dict without one is
    not an evidence entry: ``source_evidence._RETIRED_LINE_KEYS`` maps the key to why it
    is refused); and a module constant named ``*_RULE_ID`` assigned a string, the form
    ``FETCH_FAILED_RULE_ID`` and ``VALIDATION_RULE_ID`` took before #572. An f-string
    counts as a literal too.
    """
    found = []

    def is_text(node):
        return isinstance(node, ast.JoinedStr) or (isinstance(node, ast.Constant) and isinstance(node.value, str))

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.keyword) and node.arg == "rule_id" and is_text(node.value):
            found.append((node.value.lineno, ast.unparse(node.value)))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and is_text(node.value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id.endswith("RULE_ID") for t in targets):
                found.append((node.value.lineno, ast.unparse(node.value)))
        elif isinstance(node, ast.Dict):
            keys = {k.value: v for k, v in zip(node.keys, node.values, strict=True) if isinstance(k, ast.Constant)}
            if "reason" in keys and "rule_id" in keys and is_text(keys["rule_id"]):
                found.append((keys["rule_id"].lineno, ast.unparse(keys["rule_id"])))
    return found


def test_no_rule_id_is_written_as_a_literal_outside_code_rules():
    stray = {
        f"{path}:{line}": text
        for path in SOURCES
        if path.name != "code_rules.py"
        for line, text in literal_rule_ids(path.read_text(encoding="utf-8"))
    }
    assert stray == {}, "declare the rule in meta_disco.code_rules and name it through its constant"


@pytest.mark.parametrize(
    "snippet",
    [
        'make_claim(rule_id="new_rule", reason="r")',
        'result.add_claim("data_type", rule_id=f"rule_{n}", tier=4)',
        '{"rule_id": "new_rule", "reason": "r", "value": "v"}',
        'NEW_RULE_ID = "platform.new"',
        'NEW_RULE_ID: Final = "new_rule"',
    ],
)
def test_the_search_finds_each_spelling(snippet):
    assert literal_rule_ids(snippet), snippet


def test_a_dict_that_is_not_evidence_is_not_a_rule_id():
    assert literal_rule_ids('{"rule_id": "why the key is refused", "tier": "why"}') == []


def test_ids_are_unique_undotted_and_not_a_yaml_rule_id():
    ids = [d.id for d in DECLARED]
    assert len(ids) == len(set(ids))
    # A dot is what marks a translation row's id (`value_map`), so no rule id has one.
    assert [i for i in ids if "." in i] == []
    assert set(ids) & {rule.id for rule in get_unified_rules().rules} == set()


@pytest.mark.parametrize("rule", code_rules.CODE_RULES, ids=lambda r: r.id)
def test_a_code_rule_says_what_it_reads_sets_and_why(rule):
    assert rule.rationale.strip() and rule.reads.strip()
    assert rule.basis in code_rules.BASES and rule.basis != code_rules.BASIS_MAPPING
    assert rule.sets and set(rule.sets) <= set(CLASSIFICATION_FIELDS)
    assert rule.source_type in SOURCE_TYPES


@pytest.mark.parametrize("marker", code_rules.MARKERS, ids=lambda m: m.id)
def test_a_marker_says_what_it_means(marker):
    assert marker.meaning.strip()


@pytest.mark.parametrize("rule", code_rules.EDGE_RULES, ids=lambda r: r.id)
def test_an_edge_rule_says_what_it_reads_and_why(rule):
    assert rule.rationale.strip() and rule.reads.strip()
    assert rule.source_type in SOURCE_TYPES


@pytest.mark.parametrize("rule", code_rules.SAMPLE_RULES, ids=lambda r: r.id)
def test_a_sample_rule_says_what_it_reads_and_why(rule):
    assert rule.rationale.strip() and rule.reads.strip()
    assert rule.source_type in SOURCE_TYPES


@pytest.mark.parametrize("rule", code_rules.ENTITY_RULES, ids=lambda r: r.id)
def test_an_entity_rule_says_what_it_reads_sets_and_why(rule):
    assert rule.rationale.strip() and rule.reads.strip()
    # Only a slot taken as written cites an entity rule: a translated slot cites its row, a parent its identifier rule.
    assert rule.sets and set(rule.sets) <= set(models.UNTRANSLATED_SLOTS) - set(models.PARENT_FIELDS)
    assert rule.source_type in SOURCE_TYPES


@pytest.mark.parametrize("check", code_rules.IDENTITY_CHECKS, ids=lambda c: c.id)
def test_an_identity_check_says_what_it_reads_and_why(check):
    assert check.rationale.strip() and check.reads.strip()


def test_each_declaration_is_named_in_the_module_it_says_emits_it():
    names = {
        obj: name
        for name, obj in vars(code_rules).items()
        if isinstance(
            obj,
            (
                code_rules.CodeRule,
                code_rules.CodeMarker,
                code_rules.EdgeRule,
                code_rules.SampleRule,
                code_rules.EntityRule,
                code_rules.IdentityCheck,
            ),
        )
    }
    assert set(names) == set(DECLARED), (
        "every CodeRule, CodeMarker, EdgeRule, SampleRule, EntityRule and IdentityCheck is in CODE_RULES, MARKERS, "
        "EDGE_RULES, SAMPLE_RULES, ENTITY_RULES or IDENTITY_CHECKS"
    )
    unused = [d.id for d in DECLARED if f"code_rules.{names[d]}" not in Path(d.module).read_text(encoding="utf-8")]
    assert unused == []


def _rule_constant(node) -> str | None:
    """``X`` for an expression ``code_rules.X.id``, else None."""
    if (
        isinstance(node, ast.Attribute)
        and node.attr == "id"
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "code_rules"
    ):
        return node.value.attr
    return None


def _written(call: ast.Call, name: str) -> str | None:
    """The source text of one keyword argument of a call, or None if it is not passed."""
    return next((ast.unparse(k.value) for k in call.keywords if k.arg == name), None)


def claimed_fields(source: str) -> dict[str, dict[str, set[str]]]:
    """What each code rule's ``add_claim`` calls in ``source`` write, keyed by its constant's name.

    For each rule: the ``fields`` it claims, and the ``source_type`` and ``tier`` arguments
    as written (``SOURCE_CONTIG_DETECTION``, ``CONTENT_TIER``). Three call shapes, all of
    which ``header_classifier`` uses. A literal field with the rule's constant
    (``add_claim("data_type", rule_id=code_rules.X.id)``). A helper that takes the rule id
    as a parameter and claims a literal field with it (``_add_contig_claim``), whose calls
    name the rule. And a helper that claims each of its keyword arguments under one rule
    (``_claim_content``), whose calls name the fields. Any other shape fails, so this
    reader cannot silently miss a claim.
    """
    tree = ast.parse(source)
    functions = {f.name: f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)}
    # Each node's innermost enclosing function: a nested function starts after the one it
    # is in, so walking in line order lets it overwrite its parent's entries.
    enclosing = {}
    for f in sorted(functions.values(), key=lambda f: f.lineno):
        for node in ast.walk(f):
            if node is not f:
                enclosing[node] = f
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    found: dict[str, dict[str, set[str]]] = {}

    def record(rule: str, fields, call: ast.Call) -> None:
        entry = found.setdefault(rule, {"fields": set(), "source_types": set(), "tiers": set()})
        entry["fields"].update(fields)
        entry["source_types"].add(_written(call, "source_type") or "")
        entry["tiers"].add(_written(call, "tier") or "")

    def callers(helper: str):
        return [c for c in calls if isinstance(c.func, ast.Name) and c.func.id == helper]

    for call in calls:
        if not (isinstance(call.func, ast.Attribute) and call.func.attr == "add_claim"):
            continue
        rule_kw = next((k.value for k in call.keywords if k.arg == "rule_id"), None)
        field = call.args[0] if call.args else None
        rule = _rule_constant(rule_kw)
        helper = enclosing[call].name
        if rule and isinstance(field, ast.Constant):
            record(rule, {str(field.value)}, call)
        elif rule and isinstance(field, ast.Name):
            for c in callers(helper):
                record(rule, {k.arg for k in c.keywords if k.arg}, call)
        elif isinstance(rule_kw, ast.Name) and isinstance(field, ast.Constant):
            for c in callers(helper):
                for arg in c.args:
                    if name := _rule_constant(arg):
                        record(name, {str(field.value)}, call)
        else:
            raise AssertionError(f"line {call.lineno}: an add_claim shape claimed_fields does not read")
    return found


def _declared(rules):
    names = {obj: name for name, obj in vars(code_rules).items() if isinstance(obj, code_rules.CodeRule)}
    source_type_names = {getattr(models, n): n for n in dir(models) if n.startswith("SOURCE_")}
    return {names[r]: (r, source_type_names[r.source_type]) for r in rules}


def test_a_header_classifier_rule_declares_what_its_claims_write():
    read = claimed_fields(Path(code_rules.HEADER_CLASSIFIER).read_text(encoding="utf-8"))
    declared = _declared(r for r in code_rules.CODE_RULES if r.module == code_rules.HEADER_CLASSIFIER)
    assert set(read) == set(declared)
    for name, (rule, source_type) in declared.items():
        assert read[name]["fields"] == set(rule.sets), name
        assert read[name]["source_types"] == {source_type}, name
        # The report gives a content rule CONTENT_TIER; this is what makes that true.
        assert read[name]["tiers"] == {"CONTENT_TIER"}, name


def _make_claim_sites(module: str) -> dict[str, set[str]]:
    """Per code rule a module names in a ``make_claim`` call or an evidence dict, the ``source_type`` source texts."""
    written: dict[str, set[str]] = {}
    for node in ast.walk(ast.parse(Path(module).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Dict):
            keys = {k.value: v for k, v in zip(node.keys, node.values, strict=True) if isinstance(k, ast.Constant)}
            if (name := _rule_constant(keys.get("rule_id"))) and "source_type" in keys:
                written.setdefault(name, set()).add(ast.unparse(keys["source_type"]))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "make_claim":
            kw = {k.arg: k.value for k in node.keywords}
            if name := _rule_constant(kw.get("rule_id")):
                written.setdefault(name, set()).add(ast.unparse(kw["source_type"]))
    return written


def test_the_index_producer_rules_declare_what_the_producer_writes():
    import classify_index_files as cif

    assert code_rules.INDEX_BY_EXTENSION.sets == (cif.DATA_TYPE,)
    declared = _declared([code_rules.INDEX_BY_EXTENSION])
    assert _make_claim_sites(code_rules.INDEX_PRODUCER) == {
        name: {source_type} for name, (_, source_type) in declared.items()
    }


def test_the_inheritance_rule_declares_what_reconcile_writes():
    """``inherited_from_parent`` is reconcile's since #571: it may set any dimension an activity passes."""
    assert code_rules.INHERITED_FROM_PARENT.sets == activities.carried()
    assert "data_type" not in code_rules.INHERITED_FROM_PARENT.sets
    declared = _declared([code_rules.INHERITED_FROM_PARENT])
    assert _make_claim_sites(code_rules.RECONCILE_INHERIT) == {
        name: {source_type} for name, (_, source_type) in declared.items()
    }


def _rules_giving(kinds):
    """The unified rules whose ``data_type`` is one of ``kinds`` or a term under one (``annotations.coverage`` under ``annotations``)."""
    return [
        rule
        for rule in get_unified_rules().rules
        if (data_type := str(rule.then.get("data_type") or ""))
        and not kinds.isdisjoint({data_type, *schema_vocab.value_ancestors("data_type", data_type)})
    ]


def _stamped(rule):
    return {slot for slot, status in rule.then_status.items() if status == models.NOT_APPLICABLE}


def _always_not_applicable(role):
    """The dimensions every unified rule giving one of the role's kinds stamps ``not_applicable`` (#682).

    Empty where the role names no kind, a kind no rule gives, or reads through its parent (``read_through``),
    whose values are the parent's members', not the parent's. Only the YAML rules are read, and the role's
    kinds are trusted, though ``edges.misfits`` flags a parent outside them rather than refusing it.
    """
    if role.read_through is not None:
        return set()
    per_kind = [_rules_giving({str(kind)}) for kind in role.kind or ()]
    if not per_kind or not all(per_kind):
        return set()
    return set.intersection(*(_stamped(rule) for rules in per_kind for rule in rules))


def _clashes(declared):
    """``(activity, rule, dimension)`` where a role passes a dimension that a rule giving the output's kind stamps
    ``not_applicable``, unless every rule giving the role's own kinds stamps it too."""
    clashes = []
    for term, declaration in declared.items():
        output_rules = _rules_giving({str(k) for k in declaration.output.kind or ()})
        for role in declaration.inputs:
            passed = activities._role_slots(role) - _always_not_applicable(role)
            clashes += [(term, rule.id, slot) for rule in output_rules for slot in sorted(_stamped(rule) & passed)]
    return sorted(set(clashes))


def test_no_activity_passes_a_dimension_a_rule_makes_not_applicable_on_its_output():
    """What a step passes and what the output's own rule stamps must not meet (#596).

    For each activity's output kind, a rule that gives a file that `data_type` (or a term
    under it, `annotations.coverage` under `annotations`) and stamps a dimension
    `not_applicable` would conflict (contract 4.6) with any value the activity passed for
    that dimension. #571 had to drop `checksum_file`'s stamps when it made `ChecksumActivity`
    pass all five; #596 restores the stamps and has the activity pass nothing. This pins
    that the two never meet again, whichever side changes. A dimension that every unified rule
    giving the role's kinds stamps `not_applicable` is exempt: as far as those rules say, the role
    passes only `not_applicable` there, which agrees with the stamp, so a genome annotation's
    assembly may pass its variant kind and origin (#682). `_always_not_applicable` states what this
    does not see.
    """
    clashes = _clashes(activities.declarations())
    assert clashes == [], f"(activity, rule, dimension) that would always conflict: {clashes}"


def test_the_clash_guard_still_flags_a_role_of_any_kind_passing_what_the_output_s_rule_stamps():
    """#571's case: a checksum's `checked` role takes any kind, so one passing the variant kind meets
    `checksum_file`'s stamp, and the #682 exemption does not cover it."""
    declared = dict(activities.declarations())
    checksum = declared[activities.CHECKSUM]
    (checked,) = checksum.inputs
    declared[activities.CHECKSUM] = activities.Declared(
        checksum.output, (checked.model_copy(update={"passes": ["variant_kind"]}),)
    )
    assert (activities.CHECKSUM, "checksum_file", "variant_kind") in _clashes(declared)


def test_the_clash_guard_flags_a_genome_annotation_whose_input_may_carry_a_value():
    """Were a genome annotation's input any kind, a VCF's variant kind could pass onto a file a rule
    stamps `not_applicable`, so the guard would flag it (#682)."""
    declared = dict(activities.declarations())
    annotation = declared["GenomeAnnotationActivity"]
    (annotated,) = annotation.inputs
    declared["GenomeAnnotationActivity"] = activities.Declared(
        annotation.output, (annotated.model_copy(update={"kind": None}),)
    )
    assert ("GenomeAnnotationActivity", "bed_methylation", "variant_kind") in _clashes(declared)


def test_the_clash_guard_matches_a_kind_and_the_terms_under_it_only():
    """`annotations` finds the rules giving `annotations.coverage`; `annotations.coverage` does not find
    a rule giving `annotations` itself."""
    under = {r.id for r in _rules_giving({"annotations"})}
    narrow = {r.id for r in _rules_giving({"annotations.coverage"})}
    assert {"bed_mosdepth_regions", "star_signal_coverage", "bed_methylation"} <= under
    assert {"bed_mosdepth_regions", "star_signal_coverage"} <= narrow and "bed_methylation" not in narrow


def test_the_clash_guard_exempts_only_what_every_kind_s_rules_stamp():
    """A dimension one kind's rules stamp and another's do not is not exempt (`fasta_base` stamps a
    sequence's platform, an assembly's rules do not); a kind no rule gives exempts nothing."""
    (annotated,) = activities.declarations()["GenomeAnnotationActivity"].inputs
    exempt = _always_not_applicable(annotated.model_copy(update={"kind": ["assembly", "sequence"]}))
    assert {"variant_kind", "variant_origin"} <= exempt and "platform" not in exempt
    assert not _always_not_applicable(annotated.model_copy(update={"kind": ["assembly", "sample_map"]}))


def test_the_clash_guard_exempts_nothing_on_a_role_that_reads_through_its_parent():
    """A cohort merge's list passes its members' values, not its own, so the list's kind exempts nothing."""
    (input_list,) = activities.declarations()[activities.COHORT_MERGE].inputs
    assert not _always_not_applicable(input_list.model_copy(update={"kind": ["assembly"]}))


TAR_CALLER_RULES = (
    code_rules.TAR_STEP_CALLER_KIND,
    code_rules.TAR_SOURCE_CALLER_KIND,
    code_rules.TAR_MERGE_SMALL_CALLERS,
    code_rules.TAR_STEP_CALLER_ORIGIN,
    code_rules.TAR_SOURCE_CALLER_ORIGIN,
    code_rules.TAR_MERGE_GERMLINE_CALLERS,
)


@pytest.mark.parametrize("rule", TAR_CALLER_RULES, ids=lambda r: r.id)
def test_a_tar_caller_rule_names_its_twins_not_the_vcf_rules(rule):
    """A tar rule's text is its VCF rule's, each VCF caller rule it names swapped for the tar twin (#678)."""
    vcf_ids = set(code_rules._TAR_TWIN_IDS)
    named = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", rule.reads + " " + rule.rationale))
    assert not named & vcf_ids
    assert rule.id in code_rules._TAR_TWIN_IDS.values()


def test_only_a_whole_rule_id_is_swapped_for_its_twin():
    assert code_rules._as_tar("vcf_step_caller_kind, vcf_step_caller_kinds") == (
        "tar_step_caller_kind, vcf_step_caller_kinds"
    )
