"""Package-data home for the tiered classification rules.

`unified_rules.yaml` is the single source of truth for the rule engine. It lives
with the runtime that loads it (`rule_loader.py`); this makes it available whether
`meta_disco` is installed as a wheel or run from a checkout (#166, mirroring the
schema move in #164).
"""
