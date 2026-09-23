#!/usr/bin/env python3
"""Render a reconciled run's report as markdown and an HTML dashboard (#395).

Reads ``<run>/reconciled/reconcile_report.json``, which ``make reconcile`` writes (#432),
and nothing else of the run: no record is re-read. Writes ``docs/reconcile-report.md``
and ``docs/reconcile-dashboard.html`` (from ``docs/reconcile-dashboard-template.html``).

Both show, for the whole run and per dataset: how each slot of each dimension settled
(the slot categories of ``meta_disco.reconcile``), the conflict rate, the join per
evidence file, and the conflicts listed by their distinct competing values (contract
5.1). With a previous reconciled run, each category's change per dimension.

Usage:
    python scripts/generate_reconcile_report.py
    python scripts/generate_reconcile_report.py --run-dir output/anvil/20260922_230521
    python scripts/generate_reconcile_report.py --previous output/anvil/20260922_221819
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from meta_disco.models import CLASSIFICATION_FIELDS
from meta_disco.output_utils import RECONCILED_DIR, find_latest_run, list_runs
from meta_disco.reconcile import (
    CONFLICT_CATEGORIES,
    EVERY_DATASET,
    INFERENCE,
    REPORT_FILE,
    SLOT_CATEGORIES,
    SOURCE_PRECEDENCE,
    fill_category,
)
from meta_disco.summaries import md_code, md_table

PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE = PROJECT_ROOT / "docs" / "reconcile-dashboard-template.html"
PLACEHOLDER = "RECONCILE_DATA_PLACEHOLDER"
ALL = EVERY_DATASET
# Beside the categories, overlapping them: our value where the published source said nothing
# for the file, and the gaps inference left that a source filled.
ADDED = "added_over_published"
FILLED_OVER = "filled_over_inference"


def shown(dataset: str) -> str:
    """A dataset's name as displayed: reconcile counts a record with no ``dataset_title`` under ""."""
    return dataset or "(no dataset title)"


def label(category: str) -> str:
    """A slot category as a column heading: ``filled_by_submitter_harmonized`` is "submitter harmonized"."""
    if category.startswith("conflict_"):
        return f"conflict ({category.removeprefix('conflict_')})"
    return category.removeprefix("filled_by_").replace("_", " ")


class ReportError(Exception):
    """The report cannot be rendered from what is on disk."""


def load_report(run_dir: Path, previous: bool = False) -> dict:
    """A run's reconcile report, refused if this code cannot render it.

    A report with a slot category or conflict kind this code does not know is refused.
    So is one written before the conflict tally, unless it is only the ``previous`` run
    the change is computed against, which reads no conflicts.
    """
    path = run_dir / RECONCILED_DIR / REPORT_FILE
    if not path.is_file():
        raise ReportError(f"{path} not found: run `make reconcile RUN_DIR={run_dir}` first")
    try:
        report = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ReportError(f"{path} is not JSON ({exc}): run `make reconcile RUN_DIR={run_dir}` again") from None
    unknown = {
        category
        for per_slot in report["slots"].values()
        for counts in per_slot.values()
        for category in counts
        if category not in SLOT_CATEGORIES
    }
    if unknown:
        raise ReportError(f"{path}: slot categories this report does not know: {sorted(unknown)}")
    if "conflicts" not in report and not previous:
        raise ReportError(f"{path} predates the conflict tally: run `make reconcile RUN_DIR={run_dir}` again")
    kinds = {
        kind
        for per_slot in report.get("conflicts", {}).values()
        for per_kind in per_slot.values()
        for kind in per_kind
        if kind not in CONFLICT_CATEGORIES
    }
    if kinds:
        raise ReportError(f"{path}: conflict kinds this report does not know: {sorted(kinds)}")
    return report


def find_previous(run_dir: Path) -> Path | None:
    """The newest run before ``run_dir``, beside it, that holds a reconcile report; None if there is none."""
    # Resolved, so a symlink (`latest`) is read as the run it points at, among that run's siblings.
    run = run_dir.resolve()
    return max(
        (d for d in list_runs(run.parent) if d.name < run.name and (d / RECONCILED_DIR / REPORT_FILE).is_file()),
        key=lambda d: d.name,
        default=None,
    )


def _datasets(report: dict, dataset: str | None) -> list[str]:
    return sorted(report["files"]) if dataset is None else [dataset]


def columns(*reports: dict) -> list[str]:
    """The categories shown: all of them, less the fill columns of a source no evidence file of these reports came from.

    Such a source (the external one, today) can fill nothing, so its two columns would be
    zero by construction. A source that was read and filled nothing keeps its zeros: they
    say its values have no authored row yet.
    """
    read = {ev["source_type"] for report in reports for ev in report["evidence"]}
    unread = {
        fill_category(name, harmonized)
        for source_type, name in SOURCE_PRECEDENCE
        if source_type not in read
        for harmonized in (False, True)
    }
    return [c for c in SLOT_CATEGORIES if c not in unread]


def headline(report: dict, dataset: str | None = None) -> list[dict]:
    """Per dimension: each category's count, added over published, filled over inference, conflict rate."""
    names = _datasets(report, dataset)
    files = sum(report["files"].get(d, 0) for d in names)
    rows = []
    for slot in CLASSIFICATION_FIELDS:
        counts = dict.fromkeys(SLOT_CATEGORIES, 0)
        for d in names:
            for category, n in report["slots"].get(d, {}).get(slot, {}).items():
                counts[category] += n
        conflicts = sum(counts[k] for k in CONFLICT_CATEGORIES)
        rows.append(
            {
                "dimension": slot,
                "counts": counts,
                ADDED: sum(report[ADDED].get(d, {}).get(slot, 0) for d in names),
                FILLED_OVER: sum(report[FILLED_OVER].get(d, {}).get(slot, 0) for d in names),
                "inference_agreed": sum(
                    report["inputs"].get(d, {}).get(slot, {}).get(INFERENCE, {}).get("agreed", 0) for d in names
                ),
                "conflicts": conflicts,
                "conflict_rate": conflicts / files if files else 0.0,
            }
        )
    return rows


def conflict_rows(report: dict, dataset: str | None = None) -> list[dict]:
    """Every distinct set of competing values, most files first."""
    rows: list[dict] = [
        {"dataset": d, "dimension": slot, "kind": kind, "inputs": entry["inputs"], "files": entry["files"]}
        for d in _datasets(report, dataset)
        for slot, per_kind in report["conflicts"].get(d, {}).items()
        for kind, entries in per_kind.items()
        for entry in entries
    ]
    return sorted(rows, key=lambda r: (-r["files"], r["dataset"], r["dimension"], r["kind"]))


def evidence_rows(report: dict, dataset: str | None = None) -> list[dict]:
    keys = ("source_type", "dataset", "table", "key", "offered", "matched", "unmatched", "ambiguous")
    return [
        {k: ev.get(k) for k in keys}
        for ev in report["evidence"]
        if dataset is None or ev.get("dataset") in (dataset, None)
    ]


def change(new: dict, old: dict, dataset: str | None = None) -> list[dict]:
    """Per dimension, each category's count in ``new`` minus ``old``, and the same for added over published and filled over inference."""
    before = {row["dimension"]: row for row in headline(old, dataset)}
    rows = []
    for row in headline(new, dataset):
        was = before[row["dimension"]]
        delta = {k: row["counts"][k] - was["counts"][k] for k in SLOT_CATEGORIES}
        rows.append(
            {
                "dimension": row["dimension"],
                "counts": delta,
                ADDED: row[ADDED] - was[ADDED],
                FILLED_OVER: row[FILLED_OVER] - was[FILLED_OVER],
            }
        )
    return rows


def provenance(report: dict) -> dict:
    return {
        "run": report["run"],
        "input": report["input"],
        "repository": report["repository"],
        "catalog": report["catalog"],
        "value_map_sha256": report["value_map_sha256"],
        "evidence_excluded": report["evidence_excluded"],
        "files": sum(report["files"].values()),
    }


def dashboard_data(report: dict, previous: dict | None, source: Path) -> dict:
    """The payload ``reconcile-dashboard-template.html`` reads, and the markdown renders: every table precomputed per scope.

    These key names are the contract with that template's JavaScript. ``run`` is the
    whole run's scope and ``datasets`` a list of each dataset's, carrying its title as
    ``name`` — apart from the run, so no title can stand in for it, and a list rather than
    a map, so no title is read as a JavaScript object key (``__proto__``). A scope's ``change`` is None where there is no previous run
    or the dataset is not in it.
    """

    def scope(dataset: str | None) -> dict:
        files = sum(report["files"].get(d, 0) for d in _datasets(report, dataset))
        rows = headline(report, dataset)
        conflicts = sum(r["conflicts"] for r in rows)
        slots = files * len(rows)
        old = previous if previous and (dataset is None or dataset in previous["files"]) else None
        return {
            "files": files,
            "headline": rows,
            "conflicts": conflicts,
            "slots": slots,
            "conflict_rate": conflicts / slots if slots else 0.0,
            "conflict_rows": conflict_rows(report, dataset),
            "evidence": evidence_rows(report, dataset),
            "change": change(report, old, dataset) if old else None,
        }

    cols = columns(report, previous) if previous else columns(report)
    return {
        "source": str(source),
        "provenance": provenance(report),
        "previous": provenance(previous) if previous else None,
        "skipped_evidence": len(report.get("skipped_evidence", [])),
        "columns": [{"key": c, "label": label(c)} for c in cols],
        "conflict_categories": list(CONFLICT_CATEGORIES),
        "all": ALL,
        "run": scope(None),
        "datasets": [{"name": dataset, **scope(dataset)} for dataset in sorted(report["files"])],
    }


# --- markdown -----------------------------------------------------------------------


def _n(value: int) -> str:
    return f"{value:,}"


def _signed(value: int) -> str:
    return "0" if value == 0 else f"{value:+,}"


def _headline_table(rows: list[dict], cols: list[dict], fmt=_n) -> list[str]:
    header = ["dimension", *(c["label"] for c in cols), "added over published", "filled over inference"]
    body = [
        [r["dimension"], *(fmt(r["counts"][c["key"]]) for c in cols), fmt(r[ADDED]), fmt(r[FILLED_OVER])] for r in rows
    ]
    return md_table(header, body, align="right")


def competing(inputs: dict[str, list[str]]) -> str:
    return "; ".join(
        f"{name}: {', '.join(values) if values else '(no values carried)'}" for name, values in inputs.items()
    )


def _conflict_table(rows: list[dict], with_dataset: bool) -> list[str]:
    if not rows:
        return ["No conflicts."]
    header = (["dataset"] if with_dataset else []) + ["dimension", "kind", "files", "competing values"]
    body = [
        ([md_code(shown(r["dataset"]))] if with_dataset else [])
        + [r["dimension"], label(r["kind"]), _n(r["files"]), md_code(competing(r["inputs"]))]
        for r in rows
    ]
    return md_table(header, body)


def render_markdown(data: dict) -> str:
    p, cols, whole = data["provenance"], data["columns"], data["run"]
    catalog = p["catalog"] or "none"
    lines = [
        "# Reconciliation report",
        "",
        f"Generated by `make reconcile-report` from `{data['source']}` (#395).",
        "",
        f"- **Run:** `{p['run']}`, {p['files']:,} files",
        f"- **Input:** `{p['input']}` (repository `{p['repository']}`, catalog `{catalog}`)",
        f"- **Translation table sha256:** `{p['value_map_sha256']}`",
    ]
    if p["evidence_excluded"]:
        lines.append(
            "- **Evidence excluded:** the reconciled artifact concludes what inference concluded (contract 6.6)."
        )
    if data["skipped_evidence"]:
        lines.append(f"- **Evidence files skipped** (another system or catalog): {data['skipped_evidence']}")
    lines += [
        "",
        "## How each slot settled",
        "",
        "Every file is counted once per dimension, in one of the columns from *published* to *not classified*, "
        "so those columns add up to the file count. An answer the inputs agreed on is credited to where it came "
        "from: the published column first, then a submitter table (verbatim before harmonized), and inference "
        "only when no source gave it.",
        "",
        "- **Published unreviewed:** the catalog publishes a value that no translation row reads yet, and no "
        "other input gave an answer, so the file has none. Beside another input's answer, the same value counts "
        "as *conflict (published)*. The values themselves are in the "
        "[review queue](review-queue-report.md).",
        "",
        "The last two columns are extra counts laid over those, not part of the sum:",
        "",
        "- **Added over published:** files where we deliver a value and the catalog publishes none for that "
        "file, because its published column is empty there or it has no published column for the dimension: "
        "metadata the catalog does not show today.",
        "- **Filled over inference:** files where inference found no answer (`not_classified`) but a source table "
        "supplied one (a value, or not applicable): gaps inference alone would have left empty. For example, "
        "`ANVIL_T2T_CHRY` files whose reference assembly only the submitter's table names.",
        "",
        *_headline_table(whole["headline"], cols),
        "",
        "## Conflict rate",
        "",
    ]
    lines += [
        f"**{whole['conflicts']:,} of {whole['slots']:,} slots ({whole['conflict_rate']:.3%})** "
        "are a conflict across the run.",
        "",
        *md_table(
            ["dimension", "conflicts", "rate", "inference agreed with a source"],
            [
                [r["dimension"], _n(r["conflicts"]), f"{r['conflict_rate']:.3%}", _n(r["inference_agreed"])]
                for r in whole["headline"]
            ],
            align="right",
        ),
        "",
        "## Conflicts by competing values",
        "",
        "Each distinct set of values the inputs declared on a conflicted slot (contract 5.1). "
        "*Inference* lists its value, or its rules' competing values where they disagreed among themselves; "
        "an input marked *(unreviewed)* spoke with a raw value no authored translation row reads.",
        "",
        *_conflict_table(whole["conflict_rows"], with_dataset=True),
        "",
        "## Change since the previous reconciled run",
        "",
    ]
    if whole["change"] is None:
        lines.append("No earlier reconciled run to compare with.")
    else:
        q = data["previous"]
        same = "the same" if q["value_map_sha256"] == p["value_map_sha256"] else "a different"
        lines += [
            f"Against `{q['run']}` ({q['files']:,} files; {same} translation table). "
            "Each cell is this run's count minus that run's.",
            "",
            *_headline_table(whole["change"], cols, fmt=_signed),
        ]
    lines += [
        "",
        "## The join, per evidence file",
        "",
        "Whether each value from the source tables found its file in this run. "
        "A value that found no file, or more than one, is not used.",
        "",
    ]
    evidence = whole["evidence"]
    header = ["source type", "dataset", "table", "key", "offered", "matched", "unmatched", "ambiguous"]

    def evidence_table(rows: list[dict]) -> list[str]:
        return md_table(
            header,
            [
                [md_code(e["source_type"]), md_code(e["dataset"] or ALL), md_code(e["table"] or "-"), md_code(e["key"])]
                + [_n(e[k]) for k in ("offered", "matched", "unmatched", "ambiguous")]
                for e in rows
            ],
        )

    if not evidence:
        lines.append("No evidence was read.")
    else:
        problems = [e for e in evidence if e["unmatched"] or e["ambiguous"]]
        offered = sum(e["offered"] for e in evidence)
        if not problems:
            lines.append(
                f"**All {offered:,} values in the {len(evidence)} evidence files joined their file;** "
                "none unmatched or ambiguous."
            )
        else:
            lines += [
                f"**{len(problems)} of {len(evidence)} evidence files have values that did not join their file** "
                f"({offered:,} values in all):",
                "",
                *evidence_table(problems),
            ]
        lines += [
            "",
            '<details markdown="1">',
            f"<summary>Evidence files read ({len(evidence)})</summary>",
            "",
            "*offered*: values read from the table; *matched*: found their file; *unmatched*: found no file; "
            "*ambiguous*: found more than one file.",
            "",
            *evidence_table(evidence),
            "",
            "</details>",
        ]
    lines += ["", "## Per dataset", ""]
    for scope in data["datasets"]:
        name = scope["name"]
        lines += [
            f"### {md_code(shown(name))}",
            "",
            f"{scope['files']:,} files.",
            "",
            *_headline_table(scope["headline"], cols),
        ]
        if scope["conflict_rows"]:
            lines += ["", *_conflict_table(scope["conflict_rows"], with_dataset=False)]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(data: dict, template: str) -> str:
    # Every < as \u003c, which JSON and JavaScript read back as <: no value can then close
    # the <script> tag the payload sits in, or open an HTML comment inside it.
    return template.replace(PLACEHOLDER, json.dumps(data).replace("<", "\\u003c"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a reconciled run's report (#395)")
    parser.add_argument("--run-dir", type=Path, help="Reconciled run directory (default: latest under output/anvil)")
    parser.add_argument(
        "--previous", type=Path, help="Run to compare with (default: the newest earlier run holding a reconcile report)"
    )
    parser.add_argument("--no-previous", action="store_true", help="Compare with no earlier run")
    parser.add_argument("--markdown", type=Path, default=PROJECT_ROOT / "docs" / "reconcile-report.md")
    parser.add_argument("--html", type=Path, default=PROJECT_ROOT / "docs" / "reconcile-dashboard.html")
    args = parser.parse_args(argv)
    try:
        run_dir = args.run_dir or find_latest_run(Path("output/anvil"))
        report = load_report(run_dir)
        previous_dir = None if args.no_previous else (args.previous or find_previous(run_dir))
        previous = load_report(previous_dir, previous=True) if previous_dir else None
    except (ReportError, FileNotFoundError) as exc:
        print(f"reconcile-report: {exc}", file=sys.stderr)
        return 1
    data = dashboard_data(report, previous, run_dir / RECONCILED_DIR / REPORT_FILE)
    args.markdown.write_text(render_markdown(data))
    args.html.write_text(render_html(data, TEMPLATE.read_text()))
    compared = f", compared with {previous_dir.name}" if previous_dir else ""
    print(f"Reconcile report for {run_dir.name}{compared} -> {args.markdown}, {args.html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
