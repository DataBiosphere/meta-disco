"""The rules and schema ship as importable package data (wheel-safe).

Guards #164 (schema) and #166 (rules): both files were moved into the meta_disco
package and are read via importlib.resources, so `pip install meta_disco` yields a
package whose RuleEngine and vocabulary load without a source checkout. A build
config that stops shipping either file — or a regression back to a __file__ walk —
fails here rather than at first classify in an installed environment.
"""

from meta_disco.rule_loader import default_rules_resource, get_unified_rules
from meta_disco.schema_vocab import default_schema_path, dimension_values


def test_rules_resource_is_readable_package_data():
    resource = default_rules_resource()
    text = resource.read_text(encoding="utf-8")  # raises if not shipped
    assert "extension_map" in text and "rules:" in text


def test_schema_resource_is_readable_package_data():
    resource = default_schema_path()
    text = resource.read_text(encoding="utf-8")
    assert "enums:" in text


def test_rules_load_from_the_bundled_resource():
    """The engine's default path resolves the package resource, not a repo walk."""
    rules = get_unified_rules()
    assert len(rules.rules) > 100
    assert rules.extension_map  # extension_map document loaded


def test_schema_vocab_loads_from_the_bundled_resource():
    assert "variants" in dimension_values("data_type")
