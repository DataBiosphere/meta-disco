#!/usr/bin/env python3
"""Generate validation report comparing classifications against ground truth.

Compares our classification outputs against external metadata sources (the HPRC
catalogs) and reports agreement, discrepancies, and coverage gaps.

**The AnVIL comparison moved out of here (#424).** This script used to score our
values against AnVIL's published `data_modality`/`reference_assembly` through two
hand-written dicts, `ANVIL_MODALITY_MAP` and `ANVIL_REFERENCE_MAP`. That comparison
is now `meta_disco.published_comparison` / `make published-comparison`, which reports the same two
dimensions per file against the values the repository publishes. Two reports scoring the
same files by different rules is the drift `docs/claims-contract.md` exists to stop,
so there is one.

The dicts themselves were the only AnVIL value translations in the repo. They were
script-local, carried no row ids, and were validated against no vocabulary, so they
are not the translation table #414 specifies — but they are its seed, and #414 should
start from them rather than rediscover them:

    single-nucleus RNA sequencing assay -> transcriptomic.single_cell
    single-nucleus ATAC-seq            -> epigenomic.chromatin_accessibility
    GRCh38 + Gencode40                 -> GRCh38
    GRCh38 / GRCh37 / CHM13            -> identity
    GRCm39                             -> mouse, no term (#15, #399)

Usage:
    python scripts/generate_validation_report.py
    python scripts/generate_validation_report.py --run-dir output/20260322_112336
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

from meta_disco.models import field_label
from meta_disco.output_utils import CLASSIFICATION_FILES, find_latest_run
from meta_disco.summaries import escape_md_cell

DIMENSIONS = ["data_modality", "data_type", "platform", "reference_assembly", "assay_type"]

DIMENSION_LABELS = {
    "data_modality": "Data Modality",
    "data_type": "Data Type",
    "platform": "Platform",
    "reference_assembly": "Reference Assembly",
    "assay_type": "Assay Type",
}

# =============================================================================
# Load our classifications keyed by MD5 and filename
# =============================================================================


def load_our_classifications(run_dir: Path) -> tuple[dict, dict]:
    """Load classifications keyed by both md5 and filename.

    Returns (by_md5, by_filename) dicts mapping to classification values.
    """
    by_md5 = {}
    by_filename = {}

    for fname in CLASSIFICATION_FILES:
        path = run_dir / fname
        if not path.is_file():
            continue
        with path.open() as f:
            data = json.load(f)
        for r in data.get("classifications", data.get("results", [])):
            rec = {}
            for field in DIMENSIONS:
                rec[field] = field_label(r, field)
            md5 = r.get("md5sum") or r.get("file_md5sum")
            file_name = r.get("file_name", "")
            if md5:
                by_md5[md5] = rec
            if file_name:
                by_filename[file_name] = rec

    return by_md5, by_filename


# =============================================================================
# Comparison logic
# =============================================================================

SENTINELS = {"not_classified", "not_applicable", None}

# The outcome vocabulary, named once. `compare_field` returns one of these and
# `_DimStats` counts one per name. The check runs one way only: an outcome named
# here with no matching `_DimStats` key is an error where the counter is indexed,
# while a key added to `_DimStats` and not named here is not. That index sits in
# `compare_source`, which nothing calls, so nothing reachable enforces the
# correspondence today.
_Outcome = Literal["agree", "discrepancy", "we_inferred", "not_classified", "no_truth"]


class _DiscrepancyCategory(TypedDict):
    """One (ours, truth) pair we disagreed on, with a count and one example."""

    # `ours` and `truth_mapped` are whatever the two sources put in the field:
    # rendered through `str()`, never compared, so `object` is the honest width.
    # `example` is narrower because both writers coerce it — `or ""` rather than
    # a `get` default, which would pass a null through.
    ours: object
    truth_mapped: object
    count: int
    example: str


class _DimStats(TypedDict):
    """Per-dimension outcome counts. The first five keys are exactly `_Outcome`."""

    agree: int
    discrepancy: int
    we_inferred: int
    not_classified: int
    no_truth: int
    discrepancy_categories: dict[str, _DiscrepancyCategory]


class _NamedCount(TypedDict):
    """A name and a file count, as the `datasets` listing renders them."""

    name: str
    count: int


class _CatalogSummary(TypedDict):
    """One catalog's file counts. Written by `load_hprc_results`, read by nothing.

    `validation-dashboard-template.html` contains no reference to it and no Python
    reads it back; it reaches the generated dashboard only inside the `json.dumps`
    of the whole results dict. Same dead payload as `datasets`, from the other end.
    """

    name: str
    total: int
    matched: int


class _ComparisonResultsBase(TypedDict):
    """The three keys every comparison produces."""

    matched: int
    unmatched: int
    dimensions: dict[str, _DimStats]


class _ComparisonResults(_ComparisonResultsBase, total=False):
    """What one ground-truth source's comparison produced.

    Declared once for two builders and one renderer, though only one builder is
    reachable today: `main` populates `all_results` from `load_hprc_results`
    alone, and **`compare_source` has no caller anywhere in the repo**. The type
    is what would hold them in agreement if it were wired back up.

    The optional half is what only `load_hprc_results` writes, though not for one
    reason: `catalog_summary` comes from the per-catalog counts in the file it
    reads, `catalog_dimensions` is a hard-coded literal, and `metadata_coverage`
    is summed from `dimensions`, which `compare_source` could compute just as
    well. Of the three, only `metadata_coverage` has a reader —
    `build_source_section` guards on it before rendering.

    `datasets` is declared because `build_source_section` reads it, but **no
    builder in this file writes it**, so that branch never renders today. It is
    declared rather than omitted so the type says what the renderer expects;
    omitting it would hide a dead branch behind a shape that looks complete.

    Two classes because `NotRequired` needs 3.11 and this targets 3.10.
    """

    metadata_coverage: dict[str, int]
    catalog_summary: list[_CatalogSummary]
    catalog_dimensions: dict[str, list[str]]
    datasets: list[_NamedCount]


def compare_field(inferred_value, truth_value) -> _Outcome:
    """Compare a single field value against ground truth.

    Returns one of: agree, discrepancy, we_inferred, not_classified, no_truth
    """
    has_truth = truth_value is not None and truth_value != ""
    classified = inferred_value not in SENTINELS

    if not has_truth:
        if classified:
            return "we_inferred"
        return "no_truth"  # neither has a value, nothing to compare

    # Ground truth exists
    if not classified:
        return "not_classified"  # we couldn't classify but truth exists

    if inferred_value == truth_value:
        return "agree"

    return "discrepancy"


def compare_source(
    our_by_key: dict, truth_records: list[dict], key_field: str, field_mappings: dict[str, dict], dimensions: list[str]
) -> _ComparisonResults:
    """Compare our classifications against a ground truth source.

    Args:
        our_by_key: our classifications keyed by md5 or filename
        truth_records: list of ground truth records
        key_field: field in truth records to match against our keys
        field_mappings: {our_dimension: {truth_field, value_map}}
        dimensions: which dimensions to compare

    Returns dict with per-dimension comparison stats and sample discrepancies.
    """
    results: _ComparisonResults = {
        "matched": 0,
        "unmatched": 0,
        "dimensions": {},
    }

    for dim in dimensions:
        results["dimensions"][dim] = {
            "agree": 0,
            "discrepancy": 0,
            "we_inferred": 0,
            "not_classified": 0,
            "no_truth": 0,
            "discrepancy_categories": {},  # (ours, truth_mapped) -> {count, example_key}
        }

    for truth_rec in truth_records:
        key = truth_rec.get(key_field)
        if not key:
            continue

        ours = our_by_key.get(key)
        if not ours:
            results["unmatched"] += 1
            continue

        results["matched"] += 1

        for dim in dimensions:
            mapping = field_mappings.get(dim)
            if not mapping:
                continue

            truth_field = mapping["truth_field"]
            value_map = mapping.get("value_map", {})

            raw_truth = truth_rec.get(truth_field)
            mapped_truth = value_map.get(raw_truth, raw_truth) if raw_truth else None

            inferred_value = ours.get(dim)
            outcome = compare_field(inferred_value, mapped_truth)

            results["dimensions"][dim][outcome] += 1

            if outcome == "discrepancy":
                cat_key = f"{inferred_value} vs {mapped_truth}"
                cats = results["dimensions"][dim]["discrepancy_categories"]
                if cat_key not in cats:
                    cats[cat_key] = {
                        "ours": inferred_value,
                        "truth_mapped": mapped_truth,
                        "count": 0,
                        "example": str(key),
                    }
                cats[cat_key]["count"] += 1

    return results


# =============================================================================
# HPRC comparison — load pre-computed results from validate_against_hprc.py
# =============================================================================


def load_hprc_results(hprc_results_path: Path) -> _ComparisonResults:
    """Load pre-computed HPRC validation results and convert to report format.

    Reads from output/hprc/hprc_validation_results.json (produced by validate_against_hprc.py)
    and converts to the same format used by compare_source().
    """
    if not hprc_results_path.is_file():
        return {"matched": 0, "unmatched": 0, "dimensions": {}}

    with hprc_results_path.open() as f:
        data = json.load(f)

    # Handle both old format (results.total_validated) and new format (dimensions.*)
    dim_results = data.get("dimensions", {})
    mismatches = data.get("mismatches", [])

    total_matched = 0
    dimensions: dict[str, _DimStats] = {}

    for dim, stats in dim_results.items():
        match = stats.get("match", 0)
        mismatch = stats.get("mismatch", 0)
        unknown = stats.get("unknown", 0)
        total_matched = max(total_matched, match + mismatch + unknown)

        # Group discrepancies by category
        discrepancy_categories: dict[str, _DiscrepancyCategory] = {}
        for m in mismatches:
            if dim in m:
                info = m[dim]
                ours = info.get("ours", "")
                expected = info.get("expected", "")
                cat_key = f"{ours} vs {expected}"
                if cat_key not in discrepancy_categories:
                    discrepancy_categories[cat_key] = {
                        "ours": ours,
                        "truth_mapped": expected,
                        "count": 0,
                        "example": m.get("file") or "",
                    }
                discrepancy_categories[cat_key]["count"] += 1

        dimensions[dim] = {
            "agree": match,
            "discrepancy": mismatch,
            "we_inferred": 0,
            "not_classified": unknown,
            "no_truth": 0,
            "discrepancy_categories": discrepancy_categories,
        }

    # If old format without dimensions, try legacy fields
    if not dim_results and "results" in data:
        results = data["results"]
        total_matched = results.get("total_validated", 0)
        dimensions["platform"] = {
            "agree": results.get("platform_match", 0),
            "discrepancy": results.get("platform_mismatch", 0),
            "we_inferred": 0,
            "not_classified": results.get("platform_unknown", 0),
            "no_truth": 0,
            "discrepancy_categories": {},
        }

    # Build catalog summary for display
    catalogs_loaded = data.get("metadata", {}).get("catalogs_loaded", {})
    by_catalog = data.get("by_catalog", {})
    catalog_summary: list[_CatalogSummary] = []
    for cat_name, cat_total in catalogs_loaded.items():
        matched = by_catalog.get(cat_name, {}).get("matched", 0)
        catalog_summary.append(
            {
                "name": cat_name,
                "total": cat_total,
                "matched": matched,
            }
        )

    # Which dimensions each catalog provides
    catalog_dimensions = {
        "sequencing-data": ["platform", "data_modality", "assay_type"],
        "alignments": ["reference_assembly"],
        "annotations": ["reference_assembly"],
        "assemblies": [],
    }

    # Build metadata coverage from dimension stats
    # (match + mismatch + unknown = files where HPRC has ground truth)
    metadata_coverage: dict[str, int] = {}
    for dim, stats in dimensions.items():
        metadata_coverage[dim] = stats["agree"] + stats["discrepancy"] + stats["not_classified"]

    return {
        "matched": total_matched,
        "unmatched": 0,
        "dimensions": dimensions,
        "metadata_coverage": metadata_coverage,
        "catalog_summary": catalog_summary,
        "catalog_dimensions": catalog_dimensions,
    }


# =============================================================================
# Report generation
# =============================================================================


SOURCE_INFO = {
    "HPRC": {
        "text": "Validated against sequencing, alignment, and annotation catalogs from the",
        "link_label": "HPRC Data Explorer",
        "url": "https://data.humanpangenome.org/",
    },
}


def source_desc_md(name: str) -> str | None:
    info = SOURCE_INFO.get(name)
    if not info:
        return None
    return f"{info['text']} [{info['link_label']}]({info['url']})."


def source_desc_html(name: str) -> str | None:
    info = SOURCE_INFO.get(name)
    if not info:
        return None
    return f'{info["text"]} <a href="{info["url"]}">{info["link_label"]}</a>.'


def build_source_section(name: str, results: _ComparisonResults) -> str:
    # Short label for column headers: "Some Source (detail)" -> "Some Source"
    source_label = name.split("(")[0].strip() if "(" in name else name

    lines = []
    lines.append(f"## {name}")
    lines.append("")

    # Show source description with dataset listing if available
    datasets = results.get("datasets", [])
    info = SOURCE_INFO.get(name)
    if info and datasets:
        total_files = sum(d["count"] for d in datasets)
        lines.append(
            f"Validated against file-level metadata from the "
            f"[{info['link_label']}]({info['url']})'s open-access projects "
            f"with **{total_files:,}** files across **{len(datasets)}** datasets:"
        )
        lines.append("")
        for d in datasets:
            lines.append(f"- {d['name']} ({d['count']:,} files)")
        lines.append("")
    elif info:
        lines.append(source_desc_md(name))
        lines.append("")

    # Show metadata coverage
    metadata_coverage = results.get("metadata_coverage", {})
    if metadata_coverage:
        lines.append("### Metadata Overview")
        lines.append("")
        lines.append(
            f"{source_label}'s open-access datasets currently populate the following genomic metadata dimensions:"
        )
        lines.append("")
        lines.append(f"| Dimension | Files with dimension in {source_label} |")
        lines.append("|---|---:|")
        for dim in DIMENSIONS:
            label = DIMENSION_LABELS.get(dim, dim)
            count = metadata_coverage.get(dim, 0)
            lines.append(f"| {label} | {count:,} |")
        lines.append("")

    if not results.get("dimensions"):
        lines.append("No dimensions to compare.")
        return "\n".join(lines)

    EMPTY_DIM: _DimStats = {
        "agree": 0,
        "discrepancy": 0,
        "we_inferred": 0,
        "not_classified": 0,
        "no_truth": 0,
        "discrepancy_categories": {},
    }

    # Per-dimension summary
    for dim in DIMENSIONS:
        stats = results["dimensions"].get(dim, EMPTY_DIM)
        label = DIMENSION_LABELS.get(dim, dim)
        label_lower = label.lower()
        comparable = stats["agree"] + stats["discrepancy"]
        available = comparable + stats["not_classified"]

        accuracy = f"{100 * stats['agree'] / comparable:.1f}%" if comparable else "-"
        agree_pct = f"{100 * stats['agree'] / comparable:.1f}" if comparable else "0"
        disc_pct = f"{100 * stats['discrepancy'] / comparable:.1f}" if comparable else "0"

        lines.append(f"### {label} Validation")
        lines.append("")
        lines.append(f"- **{available:,}** files available from {source_label} with ground truth {label}")
        lines.append(f"- **{comparable:,}** files comparable (both source and rule engine have values)")
        lines.append(f"- **{stats['not_classified']:,}** files not classified by rule engine")
        lines.append(f"- **{stats['agree']:,}** inferred {label_lower} values match {source_label}")
        lines.append(f"- **{stats['discrepancy']:,}** discrepancies")
        lines.append(f"- **{accuracy}** accuracy")
        lines.append("")

        # Summary paragraph (only when source has ground truth)
        if available > 0:
            lines.append(
                f"Of the {available:,} files on {source_label} with ground truth "
                f"{label_lower}, we inferred {label_lower} values for "
                f"{comparable:,} files. {stats['not_classified']:,} files remain "
                f"unclassifiable by the rule engine."
            )
            if comparable > 0:
                lines.append(
                    f"Of the {comparable:,} inferred {label_lower} values, "
                    f"{stats['agree']:,} ({agree_pct}%) matched {source_label}. "
                    f"There were {stats['discrepancy']:,} discrepancies "
                    f"({disc_pct}%) in {label_lower} between meta-disco and "
                    f"{source_label}."
                )
            lines.append("")
        else:
            lines.append(f"{source_label} does not currently provide ground truth for {label_lower}.")
            lines.append("")

        # Discrepancy categories ordered by count
        cats = stats.get("discrepancy_categories", {})
        if cats:
            sorted_cats = sorted(cats.values(), key=lambda c: c["count"], reverse=True)
            lines.append("#### Discrepancies")
            lines.append("")
            lines.append(f"| Count | Inferred | {source_label} | Example |")
            lines.append("|---:|---|---|---|")
            for cat in sorted_cats:
                lines.append(
                    f"| {cat['count']:,} "
                    f"| {escape_md_cell(str(cat['ours']))} "
                    f"| {escape_md_cell(str(cat['truth_mapped']))} "
                    f"| {escape_md_cell(cat['example'])} |"
                )
            lines.append("")

    return "\n".join(lines)


def generate_html_dashboard(all_results: dict, run_time: str, output_path: Path):
    """Generate HTML validation dashboard."""
    project_root = Path(__file__).parent.parent
    template_path = project_root / "docs" / "validation-dashboard-template.html"
    if not template_path.is_file():
        print(f"Warning: {template_path} not found, skipping HTML dashboard")
        return

    template = template_path.read_text()
    dashboard_data = {
        "run_time": run_time,
        "sources": all_results,
        "source_descriptions": {name: source_desc_html(name) for name in all_results if source_desc_html(name)},
    }
    json_data = json.dumps(dashboard_data).replace("</", r"<\/")
    html = template.replace("VALIDATION_DATA_PLACEHOLDER", json_data)
    output_path.write_text(html)


def main():
    parser = argparse.ArgumentParser(description="Generate validation report")
    parser.add_argument("--run-dir", type=Path, help="Classification run directory")
    parser.add_argument(
        "--hprc-results",
        type=Path,
        default=Path("output/hprc/hprc_validation_results.json"),
        help="Pre-computed HPRC validation results",
    )
    parser.add_argument("--output", type=Path, default=Path("docs/validation-report.md"), help="Output markdown file")
    args = parser.parse_args()

    try:
        run_dir = args.run_dir or find_latest_run(Path("output/anvil"))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from None
    print(f"Loading classifications from: {run_dir}")

    our_by_md5, _ = load_our_classifications(run_dir)
    print(f"Loaded {len(our_by_md5):,} classifications by MD5")

    try:
        run_time = datetime.strptime(run_dir.name, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        run_time = run_dir.name

    # Run comparisons
    all_results = {}

    if args.hprc_results.is_file():
        print("Loading HPRC validation results...")
        hprc_results = load_hprc_results(args.hprc_results)
        all_results["HPRC"] = hprc_results
        print(f"  Matched: {hprc_results['matched']:,}, Unmatched: {hprc_results['unmatched']:,}")

    if not all_results:
        print("No validation sources found", file=sys.stderr)
        sys.exit(1)

    # Generate markdown report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as out:
        out.write("# Validation Report\n\n")
        out.write("Comparing meta-disco rule engine classifications against external ground truth.\n")
        out.write(f"Classification run: **{run_time}**\n\n")

        # Overall summary
        out.write("| Source | Files Matched | Dimensions | Agree | Discrepancies |\n")
        out.write("|---|---:|---:|---:|---:|\n")
        for source_name, results in all_results.items():
            total_agree = sum(d["agree"] for d in results["dimensions"].values())
            total_disc = sum(d["discrepancy"] for d in results["dimensions"].values())
            out.write(
                f"| {source_name} | {results['matched']:,} "
                f"| {len(results['dimensions'])} "
                f"| {total_agree:,} "
                f"| {total_disc:,} |\n"
            )

        out.write("\n")

        for source_name, results in all_results.items():
            out.write("---\n\n")
            out.write(build_source_section(source_name, results))
            out.write("\n\n")

    print(f"Written to {args.output}")

    # Generate HTML dashboard
    html_output = args.output.with_name("validation-dashboard.html")
    generate_html_dashboard(all_results, run_time, html_output)
    print(f"Written to {html_output}")


if __name__ == "__main__":
    main()
