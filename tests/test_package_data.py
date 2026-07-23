"""The rules and schema are importable package data, loaded via importlib.resources.

Guards #164 (schema) and #166 (rules): both files were moved into the meta_disco
package and are read via importlib.resources rather than a __file__ walk. These
tests run against the source checkout, so they catch a regression back to a
__file__ walk and either file going missing from the package tree — but NOT a
wheel-build misconfig (a hatch exclude), since files() resolves to the src tree
here regardless of packaging. That the built wheel actually ships both files is
verified out of band (build + install into a clean venv); the guard against the
build silently dropping them is the pyproject packages/package-data config.
"""

import pytest

from meta_disco.rule_loader import RuleLoader, default_rules_resource, get_unified_rules
from meta_disco.schema_vocab import default_schema_path, dimension_values


def test_rules_resource_is_readable_package_data():
    resource = default_rules_resource()
    text = resource.read_text(encoding="utf-8")  # raises if not shipped
    assert "rules:" in text
    # The extension_map moved in-code in #252 — it must not be reintroduced as a
    # YAML document (that would resurrect the two-source-of-truth the move removed).
    assert "extension_map:" not in text


def test_schema_resource_is_readable_package_data():
    resource = default_schema_path()
    text = resource.read_text(encoding="utf-8")
    assert "enums:" in text


def test_rules_load_from_the_bundled_resource():
    """The engine's default path resolves the package resource, not a repo walk.

    Asserts the rules and extension_map parsed (both non-empty) rather than a rule
    count, so a legitimate rule refactor (merge/split/removal) doesn't fail this
    package-data guard; rule content is covered by the rule-specific test modules.
    """
    rules = get_unified_rules()
    assert rules.rules  # rules document parsed
    assert rules.extension_map  # extension_map document parsed


def test_schema_vocab_loads_from_the_bundled_resource():
    assert "variants" in dimension_values("data_type")


def test_missing_explicit_path_error_omits_the_reinstall_hint(tmp_path):
    """An explicit path the caller supplied points the message at that path only.

    The reinstall/rebuild guidance is for the bundled-default case (a broken
    install); telling a caller who passed their own path to reinstall the package
    would be misdirected.
    """
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FileNotFoundError) as exc:
        RuleLoader(missing).load()
    msg = str(exc.value)
    assert str(missing) in msg
    assert "uv sync" not in msg and "package data" not in msg


def test_missing_rules_package_raises_friendly_error(monkeypatch):
    """If the whole meta_disco.rules package is dropped, files() raises
    ModuleNotFoundError; load() should still surface the friendly install guidance
    naming the package, not a bare ModuleNotFoundError."""
    import meta_disco.rule_loader as rl

    def boom():
        raise ModuleNotFoundError("No module named 'meta_disco.rules'")

    monkeypatch.setattr(rl, "default_rules_resource", boom)
    with pytest.raises(FileNotFoundError) as exc:
        rl.RuleLoader().load()
    msg = str(exc.value)
    assert "meta_disco.rules" in msg and "uv sync" in msg
