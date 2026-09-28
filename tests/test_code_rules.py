"""The rules and markers written in Python are declared once, in ``code_rules`` (#572)."""

import ast
from pathlib import Path

import pytest

from meta_disco import code_rules, models
from meta_disco.models import CLASSIFICATION_FIELDS, SOURCE_TYPES
from meta_disco.rule_loader import get_unified_rules

DECLARED = (*code_rules.CODE_RULES, *code_rules.MARKERS)
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
        elif isinstance(node, ast.Assign) and is_text(node.value):
            if any(isinstance(t, ast.Name) and t.id.endswith("RULE_ID") for t in node.targets):
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


def test_each_declaration_is_named_in_the_module_it_says_emits_it():
    names = {
        obj: name
        for name, obj in vars(code_rules).items()
        if isinstance(obj, (code_rules.CodeRule, code_rules.CodeMarker))
    }
    assert set(names) == set(DECLARED), "every CodeRule and CodeMarker is in CODE_RULES or MARKERS"
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


def test_the_index_producer_rules_declare_what_the_producer_writes():
    import classify_index_files as cif

    assert code_rules.INHERITED_FROM_PARENT.sets == cif.INHERITED_FIELDS
    assert code_rules.INDEX_BY_EXTENSION.sets == (cif.DATA_TYPE,)
    # Its evidence is built as dicts, not through add_claim: read each one's source_type.
    written: dict[str, set[str]] = {}
    for node in ast.walk(ast.parse(Path(code_rules.INDEX_PRODUCER).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Dict):
            keys = {k.value: v for k, v in zip(node.keys, node.values, strict=True) if isinstance(k, ast.Constant)}
            if (name := _rule_constant(keys.get("rule_id"))) and "source_type" in keys:
                written.setdefault(name, set()).add(ast.unparse(keys["source_type"]))
    declared = _declared([code_rules.INHERITED_FROM_PARENT, code_rules.INDEX_BY_EXTENSION])
    assert written == {name: {source_type} for name, (_, source_type) in declared.items()}
