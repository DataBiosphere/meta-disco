#!/usr/bin/env python3
"""Report cross-field self-consistency violations over a classification run (#314).

Report-only spike: prints per-rule violation counts + example contradictions
(with the offending field, its value, and the evidence behind it). Exits 0 —
gating is a follow-up once the violation landscape is known.

    uv run python scripts/check_consistency.py                     # latest run
    uv run python scripts/check_consistency.py --run-dir output/anvil/20260802_170826
"""

import argparse
from collections import Counter
from pathlib import Path

from meta_disco.consistency import check_run, load_rules


def main():
    parser = argparse.ArgumentParser(description="Cross-field self-consistency report over a classification run")
    parser.add_argument("--run-dir", type=Path, default=None, help="Run directory (default: latest under output/anvil)")
    parser.add_argument("--examples", type=int, default=3, help="Example violations to show per rule")
    args = parser.parse_args()

    rules = load_rules()
    run_dir, total, violations, activations = check_run(args.run_dir, rules)

    print(f"Consistency check over {run_dir} — {total:,} records, {len(rules)} rules")
    print(f"Total violations: {len(violations):,}\n")

    # "active" = records the rule tested; 0 active means vacuous (no such data),
    # not verified-clean. Distinguishing the two is the point of showing both.
    by_rule = Counter(v.rule_id for v in violations)
    print(f"{'violations':>11}  {'active':>10}  rule")
    for rule in rules:
        count = by_rule.get(rule["id"], 0)
        active = activations.get(rule["id"], 0)
        note = "  ⚠" if count else ("  (vacuous — no matching records)" if active == 0 else "")
        print(f"{count:>11,}  {active:>10,}  {rule['id']}{note}")

    if not violations:
        print("\nNo violations. ✅")
        return

    print("\nExamples:")
    shown: Counter = Counter()
    for v in violations:
        if shown[v.rule_id] >= args.examples:
            continue
        shown[v.rule_id] += 1
        when_str = ", ".join(f"{k}={val}" for k, val in v.when.items())
        offending = v.offending_value if v.offending_status == "classified" else f"<{v.offending_status}>"
        evidence = f"  (evidence: {v.evidence})" if v.evidence else ""
        print(f"  [{v.rule_id}] {v.file_name} ({v.md5sum[:8]})")
        print(f"      when {when_str}  →  {v.offending_field}={offending}{evidence}")


if __name__ == "__main__":
    main()
