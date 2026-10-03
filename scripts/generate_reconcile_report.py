#!/usr/bin/env python3
"""Render a reconciled run's report as markdown and an HTML dashboard (#395).

Reads ``<run>/reconciled/reconcile_report.json``, which ``make reconcile`` writes (#432),
and nothing else of the run: no record is re-read. Writes ``docs/reconcile-report.md``
and ``docs/reconcile-dashboard.html`` (from ``docs/reconcile-dashboard-template.html``).

Both show, for the whole run and per dataset: how each slot of each dimension settled
(the slot categories of ``meta_disco.reconcile``), the conflict rate, the join per
evidence file, and the conflicts listed by their distinct competing values (contract
5.1), per dimension the values each dataset holds (#545), the lineage (#577) and what
each file's parents gave it across its step (#571). With a previous reconciled
run, each category's change per dimension, and the counts of a value in a dataset that
moved. The markdown groups a wide dimension's dotted terms under their top-level term and
lists at most MARKDOWN_MOVED_CELLS moved counts; the dashboard shows every term and count.

Usage:
    python scripts/generate_reconcile_report.py
    python scripts/generate_reconcile_report.py --run-dir output/anvil/20260922_230521
    python scripts/generate_reconcile_report.py --previous output/anvil/20260922_221819
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from meta_disco.models import CLASSIFICATION_FIELDS, NOT_APPLICABLE, SOURCE_PUBLISHED_VALUE, STATUS_LABELS
from meta_disco.output_utils import RECONCILED_DIR, find_latest_run, list_runs
from meta_disco.reconcile import (
    CONFLICT_CATEGORIES,
    EVERY_DATASET,
    FILLED_GROUPS,
    INFERENCE,
    REPORT_FILE,
    SILENT,
    SLOT_CATEGORIES,
    SOURCE_PRECEDENCE,
    fill_category,
    published_slots,
)
from meta_disco.reconcile_inherit import OUTCOMES as INHERITANCE_COLUMNS
from meta_disco.reconcile_lineage import OUTCOMES
from meta_disco.summaries import embed_json, md_code, md_table

PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE = PROJECT_ROOT / "docs" / "reconcile-dashboard-template.html"
PLACEHOLDER = "RECONCILE_DATA_PLACEHOLDER"
ALL = EVERY_DATASET
# Beside the categories, overlapping them: our value where the published source said nothing
# for the file, and the gaps inference left that a source filled.
ADDED = "added_over_published"
FILLED_OVER = "filled_over_inference"
# A slot's statuses in the order a values table shows them, after its values: a file
# counted under one has no value for the slot. Read from STATUS_LABELS, so a status added
# there is never counted as a value here.
VALUE_STATUSES = tuple(sorted(STATUS_LABELS))
# A slot with more values than this, some of them dotted, is shown in the markdown with each
# dotted term under its top-level term (`variants.germline` under `variants`); the dashboard
# shows every term. It triggers the grouping and does not bound the table's width: a slot
# with many top-level terms stays wide.
MARKDOWN_VALUE_COLUMNS = 12
# The most moved cells the markdown lists; the dashboard lists them all.
MARKDOWN_MOVED_CELLS = 40


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
    So is one written before the conflict tally or the per-value counts (#545), unless it
    is only the ``previous`` run the change is computed against, which reads neither
    conflicts nor, where they are missing, values.
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
    if "values" not in report and not previous:
        raise ReportError(f"{path} predates the per-value counts (#545): run `make reconcile RUN_DIR={run_dir}` again")
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


def totals(rows: list[dict]) -> dict:
    """:func:`headline`'s rows summed over the dimensions: each category's count, added over published, filled over inference."""
    counts = {c: sum(r["counts"][c] for r in rows) for c in SLOT_CATEGORIES}
    return {"counts": counts, ADDED: sum(r[ADDED] for r in rows), FILLED_OVER: sum(r[FILLED_OVER] for r in rows)}


def completeness(counts: dict[str, int]) -> dict[str, int]:
    """Each of ``FILLED_GROUPS``'s slot count, in its order, then ``filled``: their sum."""
    groups = {group: sum(counts[c] for c in categories) for group, categories in FILLED_GROUPS.items()}
    return {**groups, "filled": sum(groups.values())}


def catalog_alone(report: dict, dataset: str | None = None) -> dict | None:
    """How complete the catalog's own metadata is, before ours: its dimensions, their slots, and how many it fills.

    Its dimensions are the ones its published source has a column for
    (:func:`meta_disco.reconcile.published_slots`), and a slot is filled where that source
    was not silent for the file: it publishes a value, whether or not a translation row
    reads it. None where the repository has no published source.
    """
    dimensions = sorted(published_slots(report["repository"]))
    if not dimensions:
        return None
    names = _datasets(report, dataset)
    filled = sum(
        n
        for d in names
        for slot in dimensions
        for outcome, n in report["inputs"].get(d, {}).get(slot, {}).get(SOURCE_PUBLISHED_VALUE, {}).items()
        if outcome != SILENT
    )
    files = sum(report["files"].get(d, 0) for d in names)
    return {"dimensions": dimensions, "slots": files * len(dimensions), "filled": filled}


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


def values_matrix(report: dict, slot: str) -> dict:
    """One dimension's values per dataset: its values, its statuses, a row per dataset, and a totals row.

    ``values`` are the slot's values, most files first; ``statuses`` the
    :data:`VALUE_STATUSES` present in the run. A table's columns are the two in that order,
    and a row's counts, keyed by both, sum to its dataset's files. *Has a value* is the share
    with a value; *filled* adds ``not_applicable``, a slot settled as having no value.
    """
    per_dataset = {d: report["values"].get(d, {}).get(slot, {}) for d in sorted(report["files"])}
    totals: dict[str, int] = {}
    for counts in per_dataset.values():
        for value, n in counts.items():
            totals[value] = totals.get(value, 0) + n
    values = sorted((v for v in totals if v not in VALUE_STATUSES), key=lambda v: (-totals[v], v))
    statuses = [v for v in VALUE_STATUSES if v in totals]
    return {
        "values": values,
        "statuses": statuses,
        "rows": [_values_row(d, c, values, statuses) for d, c in per_dataset.items()],
        "total": _values_row(ALL, totals, values, statuses),
    }


def _values_row(name: str, counts: dict[str, int], values: list[str], statuses: list[str]) -> dict:
    files = sum(counts.values())
    valued = sum(counts.get(v, 0) for v in values)
    return {
        "dataset": name,
        "counts": {c: counts.get(c, 0) for c in (*values, *statuses)},
        "files": files,
        "has_value": valued / files if files else 0.0,
        "filled": (valued + counts.get(NOT_APPLICABLE, 0)) / files if files else 0.0,
    }


def _slots_counted(report: dict) -> set[str]:
    return {slot for per_slot in report["values"].values() for slot in per_slot}


def new_dimensions(new: dict, old: dict) -> list[str]:
    """The dimensions ``new`` counts values for and ``old`` does not: added since, so not compared."""
    if "values" not in old:
        return []
    had = _slots_counted(old)
    return [slot for slot in CLASSIFICATION_FIELDS if slot in _slots_counted(new) and slot not in had]


def values_change(new: dict, old: dict) -> list[dict] | None:
    """Every (dataset, slot, value) count that differs between ``old`` and ``new``, largest change first.

    None when ``old`` predates the per-value counts (#545), so nothing can be compared. A
    dimension ``old`` counts nothing for is left out (:func:`new_dimensions`): every one of
    its counts would read as moved from zero.
    """
    if "values" not in old:
        return None
    compared = [slot for slot in CLASSIFICATION_FIELDS if slot not in new_dimensions(new, old)]
    moved = []
    for dataset in sorted(set(new["values"]) | set(old["values"])):
        for slot in compared:
            now = new["values"].get(dataset, {}).get(slot, {})
            was = old["values"].get(dataset, {}).get(slot, {})
            for value in sorted(set(now) | set(was)):
                before, after = was.get(value, 0), now.get(value, 0)
                if before != after:
                    moved.append(
                        {
                            "dataset": dataset,
                            "dimension": slot,
                            "value": value,
                            "before": before,
                            "after": after,
                            "delta": after - before,
                        }
                    )
    return sorted(moved, key=lambda m: (-abs(m["delta"]), m["dataset"], m["dimension"], m["value"]))


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


LINEAGE_COLUMNS = ("offered", *OUTCOMES)


def lineage_rows(report: dict) -> dict | None:
    """The lineage section (#577) as tables over the whole run, or None for a report written before it.

    ``sources``: per source type and dataset, the lines offered and what became of them;
    ``steps``: per dataset, the files whose ``generated_by`` each combination of source
    types named; ``conflicts``: per dataset and kind, the files and the first few with who
    said what; ``misfits``: the steps that do not fit their activity's declaration.
    """
    lineage = report.get("lineage")
    if lineage is None:
        return None
    sources = [
        {"source_type": source_type, "dataset": dataset, **{k: counts.get(k, 0) for k in LINEAGE_COLUMNS}}
        for source_type, per_dataset in sorted(lineage["sources"].items())
        for dataset, counts in sorted(per_dataset.items())
    ]
    steps = [
        {"dataset": dataset, "named_by": named_by, "files": files}
        for dataset, per in sorted(lineage["steps"].items())
        for named_by, files in sorted(per.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    conflicts = [
        {"dataset": dataset, "kind": kind, "files": c["files"], "examples": c["examples"]}
        for dataset, per in sorted(lineage["conflicts"].items())
        for kind, c in sorted(per.items())
    ]
    return {
        "sources": sources,
        "steps": steps,
        "conflicts": conflicts,
        "misfits": lineage["misfits"],
        # Written before the generic-only count: none to show.
        "generic_only": sum(lineage.get("generic_only", {}).values()),
    }


def inheritance_rows(report: dict) -> list[dict] | None:
    """What each role's parents gave a child, per dataset and dimension (#571); None for a report written before it.

    One row per dataset and dimension that any step passes, its counts keyed by
    ``reconcile_inherit.OUTCOMES``: *declared* (a value or ``not_applicable``), *mixed*
    (the parents disagree), and the three reasons nothing passed.
    """
    inheritance = report.get("inheritance")
    if inheritance is None:
        return None
    return [
        {"dataset": dataset, "slot": slot, **{k: counts.get(k, 0) for k in INHERITANCE_COLUMNS}}
        for dataset, per_slot in sorted(inheritance.items())
        for slot, counts in sorted(per_slot.items(), key=lambda kv: CLASSIFICATION_FIELDS.index(kv[0]))
    ]


def dashboard_data(report: dict, previous: dict | None, source: Path) -> dict:
    """The payload ``reconcile-dashboard-template.html`` reads, and the markdown renders: the tables precomputed.

    These key names are the contract with that template's JavaScript. ``values`` holds
    each dimension's :func:`values_matrix` across all datasets, which the template narrows
    to the chosen dataset's row, and ``values_change`` the moved cells, None where there is
    no previous run or it predates the per-value counts. ``run`` is the
    whole run's scope and ``datasets`` a list of each dataset's, carrying its title as
    ``name`` — apart from the run, so no title can stand in for it, and a list rather than
    a map, so no title is read as a JavaScript object key (``__proto__``). A scope's ``change`` is None where there is no previous run
    or the dataset is not in it.
    """

    def scope(dataset: str | None) -> dict:
        files = sum(report["files"].get(d, 0) for d in _datasets(report, dataset))
        rows = headline(report, dataset)
        conflicts = sum(r["conflicts"] for r in rows)
        summed = totals(rows)
        slots = files * len(rows)
        old = previous if previous and (dataset is None or dataset in previous["files"]) else None
        return {
            "files": files,
            "headline": rows,
            "totals": summed,
            "completeness": completeness(summed["counts"]),
            "catalog_alone": catalog_alone(report, dataset),
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
        "filled_groups": [{"key": g, "label": g.replace("_", " ")} for g in FILLED_GROUPS],
        "all": ALL,
        "run": scope(None),
        "datasets": [{"name": dataset, **scope(dataset)} for dataset in sorted(report["files"])],
        "values": {slot: values_matrix(report, slot) for slot in CLASSIFICATION_FIELDS},
        "values_change": values_change(report, previous) if previous else None,
        "values_new_dimensions": new_dimensions(report, previous) if previous else [],
        "lineage": lineage_rows(report),
        "lineage_columns": list(LINEAGE_COLUMNS),
        "inheritance": inheritance_rows(report),
        "inheritance_columns": list(INHERITANCE_COLUMNS),
    }


# --- markdown -----------------------------------------------------------------------


def _n(value: int) -> str:
    return f"{value:,}"


def _signed(value: int) -> str:
    return "0" if value == 0 else f"{value:+,}"


def _headline_table(rows: list[dict], cols: list[dict], fmt=_n, scope: dict | None = None) -> list[str]:
    """The per-dimension table; with ``scope``, closed by its totals and each total's share of its slots."""
    header = ["dimension", *(c["label"] for c in cols), "added over published", "filled over inference"]

    def cells(r: dict, f) -> list[str]:
        return [*(f(r["counts"][c["key"]]) for c in cols), f(r[ADDED]), f(r[FILLED_OVER])]

    body = [[r["dimension"], *cells(r, fmt)] for r in rows]
    if scope is not None:
        body += [
            ["**all dimensions**", *(f"**{v}**" for v in cells(scope["totals"], _n))],
            ["**% of slots**", *(f"**{v}**" for v in cells(scope["totals"], lambda v: _of_slots(v, scope["slots"])))],
        ]
    return md_table(header, body, align="right")


def _pct(share: float) -> str:
    """A share to one decimal, rounded down, so a dataset short of every file never reads 100%."""
    return "100%" if share >= 1 else f"{math.floor(share * 1000) / 10:.1f}%"


def _of_slots(count: int, slots: int) -> str:
    """``count``'s share of ``slots`` by :func:`_pct`, but "<0.1%" where a non-zero count would read 0.0%."""
    if count and count < slots / 1000:
        return "<0.1%"
    return _pct(count / slots) if slots else "0.0%"


def _catalog_dimensions(scope: dict) -> list[str]:
    alone = scope["catalog_alone"]
    if alone is None:
        return []
    dimensions = ", ".join(md_code(d) for d in alone["dimensions"])
    return [
        "",
        f"*Catalog alone* is the catalog's own metadata, before ours: only the dimensions it publishes a column "
        f"for ({dimensions}), so fewer slots, and a slot is filled where it publishes a value for the file, read "
        "by a translation row or not. It is not split by credit, so those rows read —.",
    ]


def _completeness_table(scope: dict) -> list[str]:
    """Ours by credit, then filled and all slots; beside them, where there is one, the catalog alone's."""
    c, slots, alone = scope["completeness"], scope["slots"], scope["catalog_alone"]
    header = ["", "slots", "% of all slots"]
    body = [[group.replace("_", " "), _n(c[group]), _of_slots(c[group], slots)] for group in FILLED_GROUPS]
    filled = ["**filled**", f"**{_n(c['filled'])}**", f"**{_of_slots(c['filled'], slots)}**"]
    every = ["**all slots**", f"**{_n(slots)}**", "**100%**"]
    if alone is not None:
        header += ["catalog alone", "% of its slots"]
        body = [[*row, "—", "—"] for row in body]
        filled += [f"**{_n(alone['filled'])}**", f"**{_of_slots(alone['filled'], alone['slots'])}**"]
        every += [f"**{_n(alone['slots'])}**", "**100%**"]
    return md_table(header, [*body, filled, every], align="right")


def _grouped(matrix: dict) -> tuple[dict, dict[str, list[str]]]:
    """``matrix`` with each dotted value summed under its top-level term, and the terms each group holds.

    Only the values are grouped; the statuses stay as they are. The groups returned are
    those holding a dotted term, the ones a reader needs spelled out.
    """
    groups: dict[str, list[str]] = {}
    for value in matrix["values"]:
        groups.setdefault(value.split(".", 1)[0], []).append(value)
    total = matrix["total"]["counts"]
    values = sorted(groups, key=lambda g: (-sum(total[v] for v in groups[g]), g))

    def regroup(row: dict) -> dict:
        counts = {g: sum(row["counts"][v] for v in groups[g]) for g in values}
        counts.update({c: row["counts"][c] for c in matrix["statuses"]})
        return {**row, "counts": counts}

    grouped = {
        "values": values,
        "statuses": matrix["statuses"],
        "rows": [regroup(r) for r in matrix["rows"]],
        "total": regroup(matrix["total"]),
    }
    return grouped, {g: members for g, members in groups.items() if members != [g]}


def _values_table(matrix: dict) -> list[str]:
    columns = [*matrix["values"], *matrix["statuses"]]
    header = ["dataset", *(md_code(c) for c in columns), "files", "has a value", "filled"]

    def cells(row: dict, name: str) -> list[str]:
        return [
            name,
            *(_n(row["counts"][c]) if row["counts"][c] else "·" for c in columns),
            _n(row["files"]),
            _pct(row["has_value"]),
            _pct(row["filled"]),
        ]

    body = [cells(r, md_code(shown(r["dataset"]))) for r in matrix["rows"]]
    body.append(cells(matrix["total"], f"**{ALL}**"))
    return md_table(header, body, align="right")


def _values_section(values: dict[str, dict]) -> list[str]:
    lines = [
        "## Values by dataset",
        "",
        "What each dataset holds, per dimension: every file counted once, under its reconciled value or, "
        "where it has none, its status (#545). *Has a value* is the share of the dataset's files with a value; "
        "*filled* adds `not_applicable`, a slot settled as having no value.",
        "",
    ]
    for slot in CLASSIFICATION_FIELDS:
        matrix = values[slot]
        lines += [f"### {slot}", ""]
        if len(matrix["values"]) > MARKDOWN_VALUE_COLUMNS and any("." in v for v in matrix["values"]):
            count = len(matrix["values"])
            matrix, groups = _grouped(matrix)
            lines += [
                f"{count} values, shown with each dotted term under its top-level term "
                "(the dashboard shows every term): "
                + "; ".join(f"{md_code(g)} = {', '.join(md_code(m) for m in members)}" for g, members in groups.items())
                + ".",
                "",
            ]
        lines += [*_values_table(matrix), ""]
    return lines


def _moved_cells(moved: list[dict]) -> list[str]:
    if not moved:
        return ["No dataset's count of any value moved."]
    shown_cells = moved[:MARKDOWN_MOVED_CELLS]
    lines = md_table(
        ["dataset", "dimension", "value", "before", "after", "change"],
        [
            [
                md_code(shown(m["dataset"])),
                m["dimension"],
                md_code(m["value"]),
                _n(m["before"]),
                _n(m["after"]),
                _signed(m["delta"]),
            ]
            for m in shown_cells
        ],
    )
    if len(moved) > len(shown_cells):
        lines += ["", f"{len(moved) - len(shown_cells):,} more cells moved; the dashboard lists every one."]
    return lines


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
            "- **Evidence excluded:** the reconciled artifact concludes what inference concluded, plus what "
            "inheritance carried across the steps inference wrote (contract 6.6)."
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
        *_headline_table(whole["headline"], cols, scope=whole),
        "",
        "**How complete the metadata is.** A slot is one file in one dimension. It is *filled* when it settled "
        "with a value or as not applicable, which is an answer (the dimension does not apply to the file), unlike "
        "not classified. A filled slot is counted once, by where its answer is credited: *original*, a source's "
        "value spelled exactly as the term its translation row declares (the *published* and *submitter* columns "
        "above); *mapped*, one spelled differently that its row translates (the *harmonized* columns); "
        "*inferred*, inference's, where no source declared it; *inherited*, only the file's parents' across its "
        "`generated_by`; *not applicable*, which is not credited to any input. A slot not classified, published "
        "unreviewed or in conflict is not filled.",
        "",
        *_completeness_table(whole),
        *_catalog_dimensions(whole),
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
        *_values_section(data["values"]),
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
            "",
            "### Values that moved, by dataset",
            "",
        ]
        if data["values_change"] is None:
            lines.append(f"`{q['run']}`'s report predates the per-value counts (#545): nothing to compare.")
        else:
            if data["values_new_dimensions"]:
                added = ", ".join(md_code(s) for s in data["values_new_dimensions"])
                lines += [f"New since `{q['run']}`, so not compared: {added}.", ""]
            lines += _moved_cells(data["values_change"])
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
    lines += ["", *_lineage_section(data["lineage"])]
    lines += ["", *_inheritance_section(data["inheritance"])]
    lines += ["", "## Per dataset", ""]
    for scope in data["datasets"]:
        name = scope["name"]
        lines += [
            f"### {md_code(shown(name))}",
            "",
            f"{scope['files']:,} files.",
            "",
            *_headline_table(scope["headline"], cols, scope=scope),
            "",
            *_completeness_table(scope),
        ]
        if scope["conflict_rows"]:
            lines += ["", *_conflict_table(scope["conflict_rows"], with_dataset=False)]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _said(example: dict) -> str:
    """Who said what in one conflict example; what a source said (a file name or an activity) is catalog text, so a code span."""
    return "; ".join(
        f"{s['by']['source_type']} ({s['by']['rule_id']}): {md_code(str(s['said']))}" for s in example["said"]
    )


def _lineage_section(lineage: dict | None) -> list[str]:
    """The lineage section (#577): what became of each source's lines, who named each step, conflicts, misfits."""
    lines = [
        "## Lineage: how each file was made",
        "",
        "Each lineage line says a file was made from a parent, in the source's words (#583). Reconcile translates "
        "it through the activity map (#584), finds the parent in the child's dataset, and merges every source's "
        "step for a file into its `generated_by` (#577). *untranslated*: no authored activity-map row reads the "
        "line (the [review queue](review-queue-report.md) lists them); *sample_parent*: the parent is a sample, "
        "which becomes an input later (#582); *not_in_dataset* / *several_match*: no file, or more than one, of "
        "the child's dataset is the parent; *child_not_in_run* / *child_several_match*: no file, or more than "
        "one, is the child; *parent_is_child*: the parent named is the child itself. Only *resolved* lines give "
        "a step.",
        "",
    ]
    if lineage is None:
        return [*lines, "This run's report predates lineage at reconcile (#577): run `make reconcile` again."]
    if not lineage["sources"]:
        lines.append("No lineage was read.")
    else:
        lines += md_table(
            ["source type", "dataset", *LINEAGE_COLUMNS],
            [
                [md_code(r["source_type"]), md_code(shown(r["dataset"]))] + [_n(r[k]) for k in LINEAGE_COLUMNS]
                for r in lineage["sources"]
            ],
        )
    lines += [
        "",
        "### Who named each file's step",
        "",
        "Files with a `generated_by`, by the kinds of source that named it: `filename_rule` is inference's name "
        "rule; two kinds joined by `+` agreed on the step.",
        "",
        *md_table(
            ["dataset", "named by", "files"],
            [[md_code(shown(r["dataset"])), md_code(r["named_by"]), _n(r["files"])] for r in lineage["steps"]],
        ),
        "",
        "### Conflicts",
        "",
    ]
    if not lineage["conflicts"]:
        lines.append("None: wherever two sources named a file's step, they agreed.")
    else:
        lines += [
            "A file whose sources name two activities, or two parents in a role that takes one, or a generic "
            "`Activity` step naming a parent no specific source names, gets no "
            "`generated_by`; the first few are listed with who said what.",
            "",
            *md_table(
                ["dataset", "kind", "files", "e.g."],
                [
                    [
                        md_code(shown(c["dataset"])),
                        c["kind"],
                        _n(c["files"]),
                        "<br>".join(f"{md_code(str(e['file_name']))}: {_said(e)}" for e in c["examples"][:2]),
                    ]
                    for c in lineage["conflicts"]
                ],
            ),
        ]
    lines += [
        "",
        f"**Generic only:** {_n(lineage['generic_only'])} files whose only step is the generic `Activity` "
        "(the step not known) get no `generated_by` until an activity-map row naming it is reviewed.",
    ]
    lines += ["", "### Steps that do not fit their activity", ""]
    if not lineage["misfits"]:
        lines.append("None.")
    else:
        lines += [
            "Flagged only: the step is still written. *required role missing* counts the steps that cannot pass "
            "what that role would (an alignment with no `reference` input cannot pass its reference assembly).",
            "",
            *md_table(
                ["dataset", "activity", "problem", "detail", "files"],
                [
                    [
                        md_code(shown(m["dataset"])),
                        md_code(m["activity"]),
                        m["problem"],
                        md_code(m["detail"]),
                        _n(m["files"]),
                    ]
                    for m in lineage["misfits"]
                ],
            ),
        ]
    return lines


def _inheritance_section(rows: list[dict] | None) -> list[str]:
    """What each file's parents gave it across its step (#571), per dataset and dimension."""
    lines = [
        "## Inheritance: what each file takes from its parents",
        "",
        "Across a file's `generated_by`, each input role passes the dimensions its activity declares "
        "(`rules/activities.yaml`), and the parents in that role settle among themselves (contract 4.9). "
        "*declared*: they agree, and give the file their value or `not_applicable`, weighed with its own "
        "(a slot it fills is credited *inherited* above); *mixed*: they disagree, which leaves the slot "
        "`not_classified`, or a conflict beside a value; *parent_conflict* / *parent_not_classified*: a parent "
        "in conflict, or with no answer, so nothing passes; *parent_not_in_run*: a parent no record of the "
        "run carries. Counted once per file, dimension and role.",
        "",
    ]
    if rows is None:
        return [*lines, "This run's report predates inheritance at reconcile (#571): run `make reconcile` again."]
    if not rows:
        return [*lines, "No file has a step that passes a dimension."]
    return lines + md_table(
        ["dataset", "dimension", *INHERITANCE_COLUMNS],
        [[md_code(shown(r["dataset"])), md_code(r["slot"])] + [_n(r[k]) for k in INHERITANCE_COLUMNS] for r in rows],
    )


def render_html(data: dict, template: str) -> str:
    return embed_json(template, PLACEHOLDER, data)


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
