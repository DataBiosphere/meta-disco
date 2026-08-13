"""Self-consistency linter (#314): cross-field semantic invariants over records.

Each rule is declarative data in ``rules/consistency_rules.yaml`` — a ``when``
(field matchers that make the rule active) and a ``require`` (what must then
hold). A violation is a concrete internal contradiction: it names the offending
field, its value/status, and the evidence behind it, caught with no ground truth.

Report-only for now (the #314 spike); wiring it into a hard gate is a follow-up
once the violation landscape is known.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import yaml

from meta_disco.models import CLASSIFIED, _entry_value, _field_entry, status_for_value
from meta_disco.output_utils import CLASSIFICATION_FILES, find_latest_run


@dataclass
class Violation:
    """One record failing one rule's ``require`` clause."""

    md5sum: str
    file_name: str
    rule_id: str
    when: dict  # field -> the value that activated the rule
    offending_field: str
    offending_value: str | None  # None unless the offending field is classified
    offending_status: str
    evidence: str | None  # rule_id/marker of the offending field's first evidence


def default_consistency_rules_resource():
    """The bundled ``consistency_rules.yaml`` as an ``importlib.resources`` resource.

    Anchored on this module's package (``{__package__}.rules``) so it resolves from
    an installed wheel/zip rather than a ``__file__`` walk — mirroring
    ``rule_loader.default_rules_resource`` (the package-data convention, #164/#166).
    """
    return files(f"{__package__}.rules") / "consistency_rules.yaml"


# Recognized matcher keys per clause -> the value type each requires. `when` also
# accepts a bare string (exact-value shorthand). Kept in lockstep with the branches
# in _matches / _violates, so a matcher the evaluator can't interpret is rejected at
# load time rather than silently ignored.
_WHEN_MATCHERS = {"prefix": str, "value_in": list, "status": str}
_REQUIRE_MATCHERS = {"value_in": list, "value_not_in": list, "status_not": str, "status": str}


def _check_matcher(rule_id: str, clause: str, field: str, matcher, allowed: dict, allow_str: bool) -> None:
    """Validate one field matcher against the keys/types the evaluator understands."""
    if allow_str and isinstance(matcher, str):
        return
    if not isinstance(matcher, dict) or len(matcher) != 1:
        shape = "a string or a single-key mapping" if allow_str else "a single-key mapping"
        raise ValueError(f"consistency rule {rule_id!r}: {clause}.{field} must be {shape}")
    ((key, value),) = matcher.items()
    if key not in allowed:
        raise ValueError(
            f"consistency rule {rule_id!r}: {clause}.{field} has unknown matcher {key!r}; "
            f"expected one of {sorted(allowed)}"
        )
    if not isinstance(value, allowed[key]):
        raise ValueError(f"consistency rule {rule_id!r}: {clause}.{field}.{key} must be {allowed[key].__name__}")


def load_rules(resource=None) -> list[dict]:
    """Load and shape-validate the declarative invariant set (defaults to the bundled
    package resource).

    Raises ``ValueError`` on a malformed file — an unrecognized shape, a missing/
    duplicate ``id``, a non-mapping ``when``/``require``, or a matcher whose key/type
    the evaluator can't interpret — so an authoring typo fails loudly instead of
    silently disabling a check (a false negative, the worst failure mode for a QA
    linter).
    """
    resource = resource or default_consistency_rules_resource()
    data = yaml.safe_load(resource.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise ValueError("consistency rules file must be a mapping with a 'rules' list")
    seen: set[str] = set()
    for i, rule in enumerate(data["rules"]):
        if not isinstance(rule, dict):
            raise ValueError(f"consistency rule #{i} is not a mapping")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError(f"consistency rule #{i} is missing a non-empty string 'id'")
        if rule_id in seen:
            raise ValueError(f"duplicate consistency rule id: {rule_id!r}")
        seen.add(rule_id)
        if not isinstance(rule.get("when"), dict) or not isinstance(rule.get("require"), dict):
            raise ValueError(f"consistency rule {rule_id!r} must have mapping 'when' and 'require'")
        for field, matcher in rule["when"].items():
            _check_matcher(rule_id, "when", field, matcher, _WHEN_MATCHERS, allow_str=True)
        for field, matcher in rule["require"].items():
            _check_matcher(rule_id, "require", field, matcher, _REQUIRE_MATCHERS, allow_str=False)
    return data["rules"]


def _dim(record: dict, name: str) -> tuple[str | None, str, list]:
    """Return the RAW ``(value, status, evidence)`` for one dimension of a record.

    Reuses ``models`` for layout normalization (``_field_entry``) and the status
    vocabulary (``status_for_value``), so the linter reads records the same way
    every other consumer does. Deliberately reads the emitted ``status`` verbatim
    (falling back to ``status_for_value`` only when absent) rather than via
    ``_entry_status``: that path runs a coherence assertion that *raises* on an
    incoherent entry, which would abort the whole run on one malformed record. A
    linter must read what is actually there and keep going — within-field
    incoherence is caught upstream (``build_field_entry`` / schema validation), not
    here. Evidence has no shared accessor and is read off the entry.
    """
    entry = _field_entry(record, name)
    value = _entry_value(entry)
    if isinstance(entry, dict):
        status = entry.get("status") or status_for_value(value)
        ev = entry.get("evidence")
        evidence = ev if isinstance(ev, list) else []
    else:
        status, evidence = status_for_value(value), []
    return value, status, evidence


def _matches(value: str | None, status: str, matcher) -> bool:
    """Whether a field's (value, status) satisfies a ``when`` matcher."""
    if isinstance(matcher, str):
        return status == CLASSIFIED and value == matcher
    if "prefix" in matcher:
        return status == CLASSIFIED and isinstance(value, str) and value.startswith(matcher["prefix"])
    if "value_in" in matcher:
        return status == CLASSIFIED and value in matcher["value_in"]
    if "status" in matcher:
        return status == matcher["status"]
    return False


def _violates(value: str | None, status: str, matcher: dict) -> bool:
    """Whether a field's (value, status) UNsatisfies a ``require`` matcher."""
    if "value_in" in matcher:
        return status == CLASSIFIED and value not in matcher["value_in"]
    if "value_not_in" in matcher:
        return status == CLASSIFIED and value in matcher["value_not_in"]
    if "status_not" in matcher:
        return status == matcher["status_not"]
    if "status" in matcher:
        return status != matcher["status"]
    return False


def rule_activation(record: dict, rule: dict) -> dict | None:
    """If the rule's ``when`` matches this record, return the activating field->value
    map; otherwise None. A rule only tests a record when it is active."""
    activated = {}
    for fieldname, matcher in (rule.get("when") or {}).items():
        value, status, _ = _dim(record, fieldname)
        if not _matches(value, status, matcher):
            return None
        activated[fieldname] = value if status == CLASSIFIED else f"<{status}>"
    return activated


def _check_active(record: dict, rule: dict, activated: dict) -> list[Violation]:
    """Violations from an already-activated rule against a record.

    Takes the ``activated`` map from :func:`rule_activation` so the ``when`` clause
    is never re-evaluated by the caller.
    """
    violations: list[Violation] = []
    for req_field, matcher in (rule.get("require") or {}).items():
        value, status, evidence = _dim(record, req_field)
        if not _violates(value, status, matcher):
            continue
        first = evidence[0] if evidence else {}
        evidence_ref = (first.get("rule_id") or first.get("marker")) if isinstance(first, dict) else None
        violations.append(
            Violation(
                md5sum=record.get("md5sum") or "",
                file_name=record.get("file_name") or "",
                rule_id=rule["id"],
                when=dict(activated),
                offending_field=req_field,
                offending_value=value if status == CLASSIFIED else None,
                offending_status=status,
                evidence=evidence_ref,
            )
        )
    return violations


def check_record(record: dict, rules: list[dict]) -> list[Violation]:
    """Return every consistency violation for one classified record."""
    violations: list[Violation] = []
    for rule in rules:
        activated = rule_activation(record, rule)
        if activated is not None:
            violations.extend(_check_active(record, rule, activated))
    return violations


def iter_records(run_dir: Path):
    """Yield every classification record (a dict) across a run's classification files.

    Unwraps the ``{"metadata", "classifications"}`` envelope the same way the
    coverage/validation report loaders do (falling back to a ``results`` key, then
    an empty list), and skips any non-dict element so an unexpected top-level shape
    yields nothing rather than iterating stray keys.
    """
    for fname in CLASSIFICATION_FILES:
        path = run_dir / fname
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        records = data.get("classifications", data.get("results", [])) if isinstance(data, dict) else data
        for record in records:
            if isinstance(record, dict):
                yield record


def render_report(
    run_dir: Path,
    total: int,
    violations: list[Violation],
    activations: Counter,
    rules: list[dict],
    examples: int = 3,
) -> str:
    """Render the consistency result as a committed markdown report.

    A per-rule table of violations + activations (a 0-violation rule that never
    activated is marked vacuous, not verified-clean) plus a capped set of example
    contradictions. Committing this gives a diffable baseline: a future run that
    regresses shows violations going 0 -> N in the report diff.
    """
    by_rule = Counter(v.rule_id for v in violations)
    lines = [
        "# Self-Consistency Report",
        "",
        f"Run: **{run_dir}** — {total:,} records, {len(rules)} rules  ",
        f"**Total violations: {len(violations):,}**",
        "",
        "Cross-field invariants over classified records (#314). *Active* is how many "
        "records a rule tested; a rule with 0 active is **vacuous** (no matching data "
        "in this run), not verified-clean.",
        "",
        "| Violations | Active | Rule |",
        "|---:|---:|---|",
    ]
    for rule in rules:
        count = by_rule.get(rule["id"], 0)
        active = activations.get(rule["id"], 0)
        note = " ⚠" if count else (" _(vacuous)_" if active == 0 else "")
        lines.append(f"| {count:,} | {active:,} | `{rule['id']}`{note} |")

    lines += ["", "## Examples", ""]
    if not violations:
        lines.append("_No violations._")
    else:
        shown: Counter = Counter()
        for v in violations:
            if shown[v.rule_id] >= examples:
                continue
            shown[v.rule_id] += 1
            when_str = ", ".join(f"{k}={val}" for k, val in v.when.items())
            offending = v.offending_value if v.offending_status == CLASSIFIED else f"<{v.offending_status}>"
            evidence = f" (evidence: {v.evidence})" if v.evidence else ""
            lines.append(
                f"- **{v.rule_id}** — `{v.file_name}` ({v.md5sum[:8]}): "
                f"when {when_str} → `{v.offending_field}={offending}`{evidence}"
            )
    return "\n".join(lines) + "\n"


def check_run(
    run_dir: Path | None = None, rules: list[dict] | None = None
) -> tuple[Path, int, list[Violation], Counter]:
    """Run every rule over every record in a run.

    Returns ``(run_dir, record_count, violations, activations)`` where
    ``activations`` counts, per rule id, how many records the rule was active on —
    so a zero-violation rule that never activated (vacuous, no such data) is
    distinguishable from one that was genuinely exercised and stayed clean.

    Activation is evaluated once per (record, rule) and drives both the counter and
    the ``require`` check.
    """
    run_dir = run_dir or find_latest_run(Path("output/anvil"))
    rules = rules if rules is not None else load_rules()
    violations: list[Violation] = []
    activations: Counter = Counter()
    total = 0
    for record in iter_records(run_dir):
        total += 1
        for rule in rules:
            activated = rule_activation(record, rule)
            if activated is None:
                continue
            activations[rule["id"]] += 1
            violations.extend(_check_active(record, rule, activated))
    return run_dir, total, violations, activations
