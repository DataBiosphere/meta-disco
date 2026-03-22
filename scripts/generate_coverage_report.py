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

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.output_utils import find_latest_run
from src.meta_disco.rule_loader import UnifiedRules

CLASSIFICATION_FILES = [
    "bam_classifications.json",
    "vcf_classifications.json",
    "fastq_classifications.json",
    "bed_classifications.json",
    "image_classifications.json",
    "auxiliary_classifications.json",
    "index_classifications.json",
    "fasta_classifications.json",
]

COMPOUND_EXTENSIONS = UnifiedRules.COMPOUND_EXTENSIONS

DIMENSIONS = [
    ("data_modality", "Data Modality", ""),
    ("data_type", "Data Type", ""),
    ("reference_assembly", "Reference Assembly", ""),
    ("platform", "Platform",
     "**Note**: Platform is inherently unknowable for most derived formats "
     "(VCF, BED, PLINK). Only BAM/CRAM (via `@RG PL` header) and FASTQ "
     "(via read name patterns) can encode platform. The high not-classified "
     "rate is expected."),
    ("assay_type", "Assay Type",
     "**Note**: Like platform, assay type is inherently unknowable for most "
     "derived formats. Only BAM/CRAM (via `@PG` programs and file size "
     "heuristics) and filename patterns can determine assay. The high "
     "not-classified rate is expected."),
]


def escape_md_cell(text: str) -> str:
    """Escape characters that break markdown table cells."""
    return text.replace("|", "\\|").replace("\n", " ")


def get_extension(filename: str) -> str:
    name = filename.lower()
    for ext in COMPOUND_EXTENSIONS:
        if name.endswith(ext):
            return ext
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    return "(none)"


def load_records(run_dir: Path) -> list[dict]:
    records = []
    for fname in CLASSIFICATION_FILES:
        path = run_dir / fname
        if not path.is_file():
            continue
        with open(path) as f:
            data = json.load(f)
        for r in data.get("classifications", data.get("results", [])):
            cls = r.get("classifications", r)
            rec = {"file_name": r.get("file_name", "")}
            for field in ["data_modality", "data_type", "platform", "reference_assembly", "assay_type"]:
                v = cls.get(field)
                if isinstance(v, dict) and "value" in v:
                    rec[field] = v["value"]
                    # Store the first evidence reason (used for not_classified aggregation)
                    evidence = v.get("evidence", [])
                    if evidence:
                        rec[f"{field}_reason"] = evidence[0].get("reason", "")
                else:
                    rec[field] = v
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
        r"Inherited from parent file: .+",
        "Inherited from parent file",
        reason,
    )
    return reason


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


def build_section(records: list[dict], field_name: str,
                  label: str, extra_notes: str = "") -> tuple[str, int, int]:
    total = len(records)
    by_ext = defaultdict(Counter)
    totals = Counter()
    for r in records:
        val = r.get(field_name) or "None"
        by_ext[val][r["ext"]] += 1
        totals[val] += 1

    classified = sum(c for v, c in totals.items() if v not in ("not_classified", "None"))
    nc = totals.get("not_classified", 0) + totals.get("None", 0)

    lines = []
    lines.append(f"## {label}")
    lines.append("")
    lines.append("| | count | % |")
    lines.append("|---|---:|---:|")
    lines.append(f"| **Classified** | {classified:,} | {100 * classified / total:.1f}% |")
    lines.append(f"| **Not classified** | {nc:,} | {100 * nc / total:.1f}% |")

    nc_exts = by_ext.get("not_classified", Counter()) + by_ext.get("None", Counter())
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

    return "\n".join(lines), classified, nc


def main():
    parser = argparse.ArgumentParser(description="Generate classification coverage report")
    parser.add_argument("--run-dir", type=Path, help="Path to classification run directory")
    parser.add_argument("--output", type=Path, default=Path("docs/anvil-coverage-report.md"),
                        help="Output markdown file")
    args = parser.parse_args()

    try:
        run_dir = args.run_dir or find_latest_run(Path("output"))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
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

    sections = []
    summary_rows = []

    for field, label, notes in DIMENSIONS:
        section, classified, nc = build_section(records, field, label, notes)
        sections.append(section)
        summary_rows.append(
            f"| **{label}** | {classified:,} ({100 * classified / total:.1f}%) "
            f"| {nc:,} ({100 * nc / total:.1f}%) |"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as out:
        out.write("# AnVIL Classification Coverage Report\n\n")
        out.write(f"Coverage of {total:,} classified file records across {len(DIMENSIONS)} dimensions.\n")
        out.write(f"Classification run: **{run_time}**\n\n")
        out.write("**Classified** includes all files with a determined value, including `not_applicable` ")
        out.write("(e.g., FASTQ files have no reference assembly). ")
        out.write("**Not classified** means no rule or signal could determine a value.\n\n")
        out.write("| Dimension | Classified | Not Classified |\n")
        out.write("|---|---:|---:|\n")
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
    generate_html_dashboard(records, run_time, html_output)
    print(f"Written to {html_output}")


def generate_html_dashboard(records: list[dict],
                            run_time: str, output_path: Path):
    """Generate HTML dashboard with embedded chart data."""
    total = len(records)
    dashboard_data = {"total": total, "run_time": run_time, "dimensions": []}

    for field, label, notes in DIMENSIONS:
        by_ext = defaultdict(Counter)
        totals = Counter()
        for r in records:
            val = r.get(field) or "None"
            by_ext[val][r["ext"]] += 1
            totals[val] += 1

        classified = sum(c for v, c in totals.items() if v not in ("not_classified", "None"))
        nc = totals.get("not_classified", 0) + totals.get("None", 0)

        values = [
            {"name": val, "count": count,
             "extensions": [{"ext": e, "count": c} for e, c in by_ext[val].most_common()]}
            for val, count in totals.most_common()
        ]

        nc_exts = by_ext.get("not_classified", Counter()) + by_ext.get("None", Counter())
        reasons_by_ext = get_nc_reasons(records, field)
        nc_breakdown = []
        for ext, count in nc_exts.most_common():
            ext_reasons = reasons_by_ext.get(ext, Counter())
            top_reason = ext_reasons.most_common(1)[0][0] if ext_reasons else "No reason recorded"
            nc_breakdown.append({"ext": ext, "count": count, "why": top_reason})

        dashboard_data["dimensions"].append({
            "field": field,
            "label": label,
            "classified": classified,
            "not_classified": nc,
            "values": values,
            "not_classified_breakdown": nc_breakdown,
            "notes": notes,
        })

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
