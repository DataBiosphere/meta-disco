#!/usr/bin/env python3
"""Generate AnVIL classification coverage report.

Reads classification outputs and produces docs/anvil-coverage-report.md
showing coverage stats and root cause analysis for each dimension.

Usage:
    python scripts/generate_coverage_report.py
    python scripts/generate_coverage_report.py --run-dir output/20260321_220733
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from meta_disco.file_name import FileName
from meta_disco.models import CONFLICT, NOT_CLASSIFIED, field_label
from meta_disco.output_utils import CLASSIFICATION_FILES, find_latest_run
from meta_disco.rule_engine import CONFLICT_MARKER
from meta_disco.summaries import escape_md_cell

DIMENSIONS = [
    ("data_modality", "Data Modality", ""),
    ("data_type", "Data Type", ""),
    ("reference_assembly", "Reference Assembly", ""),
    (
        "platform",
        "Platform",
        "**Note**: Platform is inherently unknowable for most derived formats "
        "(VCF, BED, PLINK). Only BAM/CRAM (via `@RG PL` header) and FASTQ "
        "(via read name patterns) can encode platform. The high not-classified "
        "rate is expected.",
    ),
    (
        "assay_type",
        "Assay Type",
        "**Note**: Like platform, assay type is inherently unknowable for most "
        "derived formats. It is determined by a STAR `@PG` line or a transcriptomic "
        "modality (RNA-seq), by filename patterns (STAR output), and by extension "
        "where the format implies it (`.idat` is a methylation array); no rule reads "
        "file size or infers WGS from a long-read platform (#430). The high "
        "not-classified rate is expected.",
    ),
]


def get_extension(filename: str) -> str:
    # Group by the parsed clean core extension (#245); an archive/compression-only
    # or extensionless name has no core and groups under "(none)".
    return FileName.parse(filename).extension or "(none)"


def load_records(run_dir: Path) -> list[dict]:
    records = []
    for fname in CLASSIFICATION_FILES:
        path = run_dir / fname
        if not path.is_file():
            continue
        with path.open() as f:
            data = json.load(f)
        for r in data.get("classifications", data.get("results", [])):
            cls = r.get("classifications", r)
            rec = {"file_name": r.get("file_name", "")}
            for field in ["data_modality", "data_type", "platform", "reference_assembly", "assay_type"]:
                rec[field] = field_label(r, field)
                # Store the first evidence reason (used for not_classified aggregation)
                v = cls.get(field)
                if isinstance(v, dict):
                    evidence = v.get("evidence", [])
                    if evidence:
                        rec[f"{field}_reason"] = evidence[0].get("reason", "")
                    # A field in conflict carries a marker naming the disagreeing
                    # values (#88); the conflict table groups on them.
                    for e in evidence:
                        if e.get("marker") == CONFLICT_MARKER:
                            rec[f"{field}_competing"] = " vs ".join(sorted(e.get("competing_values", [])))
            rec["ext"] = get_extension(rec["file_name"])
            records.append(rec)
    return records


def _normalize_reason(reason: str) -> str:
    """Normalize evidence reasons so they aggregate well.

    Strips specific filenames from inherited-from-parent reasons so they
    don't create thousands of unique reasons that each count as 1.
    """
    import re

    reason = re.sub(
        r"Parent file .+ had no value for (this field|\w+)",
        r"Parent file had no value for \1",
        reason,
    )
    reason = re.sub(
        r"Parent file .+ marks (\w+) not applicable",
        r"Parent file marks \1 not applicable",
        reason,
    )
    reason = re.sub(
        r"No classification row for parent file .+",
        "No classification row for parent file",
        reason,
    )
    return re.sub(
        r"Inherited from parent file: .+",
        "Inherited from parent file",
        reason,
    )


def get_nc_reasons(records: list[dict], field_name: str) -> dict[str, Counter]:
    """Aggregate actual evidence reasons for not-classified files, grouped by extension."""
    reasons_by_ext = defaultdict(Counter)
    for r in records:
        val = r.get(field_name)
        if val in (None, "not_classified"):
            ext = r["ext"]
            reason = _normalize_reason(r.get(f"{field_name}_reason", "No reason recorded"))
            reasons_by_ext[ext][reason] += 1
    return reasons_by_ext


class Tally:
    """One dimension's labels counted three ways: per label, per label and
    extension, and split into the three buckets the report shows. ``classified``
    is every label that is neither ``not_classified`` nor ``conflict`` — so it
    includes ``not_applicable``, a determined answer — and ``conflict`` (#88) is
    counted on its own rather than folded into either neighbour."""

    def __init__(self, records: list[dict], field_name: str):
        self.by_ext: defaultdict[str, Counter] = defaultdict(Counter)
        self.totals: Counter = Counter()
        for r in records:
            val = r.get(field_name) or "None"
            self.by_ext[val][r["ext"]] += 1
            self.totals[val] += 1
        self.conflict = self.totals.get(CONFLICT, 0)
        self.nc = self.totals.get(NOT_CLASSIFIED, 0) + self.totals.get("None", 0)
        self.classified = sum(self.totals.values()) - self.nc - self.conflict

    @property
    def nc_exts(self) -> Counter:
        return self.by_ext.get(NOT_CLASSIFIED, Counter()) + self.by_ext.get("None", Counter())


# What the conflict table shows for a record in conflict whose evidence names no
# competing values: an index file re-emitting its parent's conflict carries the
# parent's status and no marker (classify_index_files), so the values are on the
# parent's record, not this one.
COMPETING_NOT_RECORDED = "(not recorded on this record)"


def get_conflict_breakdown(records: list[dict], field_name: str) -> list["_ConflictRow"]:
    """The dimension's conflicts grouped by extension and the disagreeing values,
    most frequent first. Empty when nothing is in conflict."""
    counts: Counter = Counter()
    for r in records:
        if r.get(field_name) == CONFLICT:
            counts[(r["ext"], r.get(f"{field_name}_competing") or COMPETING_NOT_RECORDED)] += 1
    return [{"ext": ext, "competing": competing, "count": n} for (ext, competing), n in counts.most_common()]


def build_section(records: list[dict], field_name: str, label: str, extra_notes: str = "") -> tuple[str, Tally]:
    total = len(records)
    tally = Tally(records, field_name)
    by_ext, totals = tally.by_ext, tally.totals

    lines = []
    lines.append(f"## {label}")
    lines.append("")
    lines.append("| | count | % |")
    lines.append("|---|---:|---:|")
    lines.append(f"| **Classified** | {tally.classified:,} | {100 * tally.classified / total:.1f}% |")
    lines.append(f"| **Not classified** | {tally.nc:,} | {100 * tally.nc / total:.1f}% |")
    lines.append(f"| **Conflict** | {tally.conflict:,} | {100 * tally.conflict / total:.1f}% |")

    nc_exts = tally.nc_exts
    if nc_exts:
        reasons_by_ext = get_nc_reasons(records, field_name)
        lines.append("")
        lines.append("### What's not classified?")
        lines.append("")
        lines.append("| extension | count | reason (from evidence) |")
        lines.append("|---|---:|---|")
        for ext, count in nc_exts.most_common():
            # Get the most common reason for this ext
            ext_reasons = reasons_by_ext.get(ext, Counter())
            top_reason = ext_reasons.most_common(1)[0][0] if ext_reasons else "No reason recorded"
            lines.append(f"| {ext} | {count:,} | {escape_md_cell(top_reason)} |")

    conflicts = get_conflict_breakdown(records, field_name)
    if conflicts:
        lines.append("")
        lines.append("### What's in conflict?")
        lines.append("")
        lines.append("Rules at the same tier disagreed and no curator rule has answered it; no value is asserted.")
        lines.append("")
        lines.append("| extension | competing values | count |")
        lines.append("|---|---|---:|")
        for row in conflicts:
            lines.append(f"| {row['ext']} | {escape_md_cell(row['competing'])} | {row['count']:,} |")

    lines.append("")
    lines.append(f"| {label} | count | % | extensions |")
    lines.append("|---|---:|---:|---|")

    for val, count in totals.most_common():
        pct = 100 * count / total
        all_exts = by_ext[val].most_common()
        ext_str = "<br>".join(f"{e} ({c:,})" for e, c in all_exts)
        lines.append(f"| `{val}` | {count:,} | {pct:.1f}% | {ext_str} |")

    if extra_notes:
        lines.append("")
        lines.append(extra_notes)

    return "\n".join(lines), tally


def main():
    parser = argparse.ArgumentParser(description="Generate classification coverage report")
    parser.add_argument("--run-dir", type=Path, help="Path to classification run directory")
    parser.add_argument(
        "--output", type=Path, default=Path("docs/anvil-coverage-report.md"), help="Output markdown file"
    )
    args = parser.parse_args()

    try:
        run_dir = args.run_dir or find_latest_run(Path("output/anvil"))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None
    print(f"Loading from: {run_dir}")

    records = load_records(run_dir)
    if not records:
        print("No records found", file=sys.stderr)
        sys.exit(1)

    total = len(records)
    print(f"Loaded {total:,} records")

    # Parse run timestamp from directory name (e.g., 20260322_005526)
    try:
        run_time = datetime.strptime(run_dir.name, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        run_time = run_dir.name

    # Load dataset stats from source metadata
    metadata_path = Path("data/anvil/anvil_files_metadata.ndjson")
    dataset_counts = Counter()
    if metadata_path.is_file():
        with metadata_path.open() as f:
            for line in f:
                r = json.loads(line)
                dataset_counts[r.get("dataset_title") or "unknown"] += 1

    sections = []
    summary_rows = []

    for field, label, notes in DIMENSIONS:
        section, tally = build_section(records, field, label, notes)
        sections.append(section)
        summary_rows.append(
            f"| **{label}** | {tally.classified:,} ({100 * tally.classified / total:.1f}%) "
            f"| {tally.nc:,} ({100 * tally.nc / total:.1f}%) "
            f"| {tally.conflict:,} ({100 * tally.conflict / total:.1f}%) |"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as out:
        out.write("# AnVIL Classification Coverage Report\n\n")
        out.write(f"Classification run: **{run_time}**\n\n")

        if dataset_counts:
            n_datasets = len(dataset_counts)
            n_files = sum(dataset_counts.values())
            unprocessed = n_files - total
            out.write(
                f"Source: **{n_files:,}** files across **{n_datasets}** open-access datasets "
                f"on [explore.anvilproject.org](https://explore.anvilproject.org/).\n"
            )
            out.write(f"Processed **{total:,}** files")
            if unprocessed > 0:
                # This difference is source files minus classified records. It mixes
                # files no classifier routed with files the run deliberately excluded
                # for having no usable checksum (#376), which are not the same thing —
                # so it points at the report that separates them rather than naming
                # only one of the two causes.
                out.write(
                    f" ({unprocessed:,} with no classification record — "
                    "see [unprocessable files](unprocessable-report.md) for why)"
                )
            out.write(".\n\n")
            for title, count in dataset_counts.most_common():
                out.write(f"- {title} ({count:,} files)\n")
            out.write("\n")
        else:
            out.write(f"Coverage of {total:,} classified file records across {len(DIMENSIONS)} dimensions.\n\n")

        out.write("**Classified** includes all files with a determined value, including `not_applicable` ")
        out.write("(e.g., FASTQ files have no reference assembly). ")
        out.write("**Not classified** means no rule or signal could determine a value. ")
        out.write("**Conflict** means rules at the same tier disagreed and nothing has answered it (#88).\n\n")
        out.write("| Dimension | Classified | Not Classified | Conflict |\n")
        out.write("|---|---:|---:|---:|\n")
        for row in summary_rows:
            out.write(row + "\n")
        out.write("\n")
        for section in sections:
            out.write("---\n\n")
            out.write(section)
            out.write("\n\n")

    print(f"Written to {args.output}")

    # Generate HTML dashboard
    html_output = args.output.with_name("coverage-dashboard.html")
    generate_html_dashboard(records, run_time, dataset_counts, html_output)
    print(f"Written to {html_output}")


class _NamedCount(TypedDict):
    name: str
    count: int


class _ExtensionCount(TypedDict):
    ext: str
    count: int


class _ValueBreakdown(_NamedCount):
    extensions: list[_ExtensionCount]


class _NotClassifiedRow(_ExtensionCount):
    why: str


class _ConflictRow(_ExtensionCount):
    competing: str


class _DimensionPanel(TypedDict):
    field: str
    label: str
    classified: int
    not_classified: int
    conflict: int
    values: list[_ValueBreakdown]
    not_classified_breakdown: list[_NotClassifiedRow]
    conflict_breakdown: list[_ConflictRow]
    notes: str


class _DashboardData(TypedDict):
    """The payload `coverage-dashboard-template.html` reads.

    These key names are the contract with that template's JavaScript, which no
    type can reach across — renaming one here still breaks the page silently.
    Declaring the shape at least holds the Python side to one spelling.
    """

    total: int
    run_time: str
    datasets: list[_NamedCount]
    dimensions: list[_DimensionPanel]


def generate_html_dashboard(records: list[dict], run_time: str, dataset_counts: Counter, output_path: Path):
    """Generate HTML dashboard with embedded chart data."""
    total = len(records)
    datasets: list[_NamedCount] = (
        [{"name": name, "count": count} for name, count in dataset_counts.most_common()] if dataset_counts else []
    )
    dashboard_data: _DashboardData = {
        "total": total,
        "run_time": run_time,
        "datasets": datasets,
        "dimensions": [],
    }

    for field, label, notes in DIMENSIONS:
        tally = Tally(records, field)
        by_ext, totals = tally.by_ext, tally.totals

        values: list[_ValueBreakdown] = [
            {"name": val, "count": count, "extensions": [{"ext": e, "count": c} for e, c in by_ext[val].most_common()]}
            for val, count in totals.most_common()
        ]

        reasons_by_ext = get_nc_reasons(records, field)
        nc_breakdown: list[_NotClassifiedRow] = []
        for ext, count in tally.nc_exts.most_common():
            ext_reasons = reasons_by_ext.get(ext, Counter())
            top_reason = ext_reasons.most_common(1)[0][0] if ext_reasons else "No reason recorded"
            nc_breakdown.append({"ext": ext, "count": count, "why": top_reason})

        dashboard_data["dimensions"].append(
            {
                "field": field,
                "label": label,
                "classified": tally.classified,
                "not_classified": tally.nc,
                "conflict": tally.conflict,
                "values": values,
                "not_classified_breakdown": nc_breakdown,
                "conflict_breakdown": get_conflict_breakdown(records, field),
                "notes": notes,
            }
        )

    project_root = Path(__file__).parent.parent
    template_path = project_root / "docs" / "coverage-dashboard-template.html"
    if template_path.is_file():
        template = template_path.read_text()
    else:
        print(f"Warning: {template_path} not found, skipping HTML dashboard")
        return

    # Escape </ to prevent breaking out of <script> tag
    json_data = json.dumps(dashboard_data).replace("</", r"<\/")
    html = template.replace("COVERAGE_DATA_PLACEHOLDER", json_data)
    output_path.write_text(html)


if __name__ == "__main__":
    main()
