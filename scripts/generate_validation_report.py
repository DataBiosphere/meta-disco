#!/usr/bin/env python3
"""Generate validation report comparing classifications against ground truth.

Compares our classification outputs against external metadata sources
(AnVIL Azul, HPRC catalogs) and reports agreement, discrepancies,
and coverage gaps.

Usage:
    python scripts/generate_validation_report.py
    python scripts/generate_validation_report.py --run-dir output/20260322_112336
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.output_utils import find_latest_run

CLASSIFICATION_FILES = [
    "bam_classifications.json",
    "vcf_classifications.json",
    "fastq_classifications.json",
    "bed_classifications.json",
    "image_classifications.json",
    "auxiliary_classifications.json",
    "index_classifications.json",
    "fasta_classifications.json",
    "remaining_classifications.json",
]

DIMENSIONS = ["data_modality", "data_type", "platform", "reference_assembly", "assay_type"]

DIMENSION_LABELS = {
    "data_modality": "Data Modality",
    "data_type": "Data Type",
    "platform": "Platform",
    "reference_assembly": "Reference Assembly",
    "assay_type": "Assay Type",
}

# =============================================================================
# Field mapping: normalize external vocabulary to ours
# =============================================================================

# AnVIL maps are small and specific to this script
ANVIL_MODALITY_MAP = {
    "single-nucleus RNA sequencing assay": "transcriptomic.single_cell",
    "single-nucleus ATAC-seq": "epigenomic.chromatin_accessibility",
}

ANVIL_REFERENCE_MAP = {
    "GRCh38 + Gencode40": "GRCh38",
    "GRCh38": "GRCh38",
    "GRCh37": "GRCh37",
    "CHM13": "CHM13",
    "GRCm39": "GRCm39",  # mouse — we don't support yet
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
        with open(path) as f:
            data = json.load(f)
        for r in data.get("classifications", data.get("results", [])):
            cls = r.get("classifications", r)
            rec = {}
            for field in DIMENSIONS:
                v = cls.get(field)
                if isinstance(v, dict) and "value" in v:
                    rec[field] = v["value"]
                else:
                    rec[field] = v
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


def compare_field(our_value, truth_value) -> str:
    """Compare a single field value against ground truth.

    Returns one of: agree, discrepancy, we_inferred, not_classified, no_truth
    """
    has_truth = truth_value is not None and truth_value != ""
    classified = our_value not in SENTINELS

    if not has_truth:
        if classified:
            return "we_inferred"
        return "no_truth"  # neither has a value, nothing to compare

    # Ground truth exists
    if not classified:
        return "not_classified"  # we couldn't classify but truth exists

    if our_value == truth_value:
        return "agree"

    return "discrepancy"


def compare_source(our_by_key: dict, truth_records: list[dict],
                   key_field: str, field_mappings: dict[str, dict],
                   dimensions: list[str]) -> dict:
    """Compare our classifications against a ground truth source.

    Args:
        our_by_key: our classifications keyed by md5 or filename
        truth_records: list of ground truth records
        key_field: field in truth records to match against our keys
        field_mappings: {our_dimension: {truth_field, value_map}}
        dimensions: which dimensions to compare

    Returns dict with per-dimension comparison stats and sample discrepancies.
    """
    results = {
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

            our_value = ours.get(dim)
            outcome = compare_field(our_value, mapped_truth)

            results["dimensions"][dim][outcome] += 1

            if outcome == "discrepancy":
                cat_key = f"{our_value} vs {mapped_truth}"
                cats = results["dimensions"][dim]["discrepancy_categories"]
                if cat_key not in cats:
                    cats[cat_key] = {
                        "ours": our_value,
                        "truth_mapped": mapped_truth,
                        "count": 0,
                        "example": key,
                    }
                cats[cat_key]["count"] += 1

    return results


# =============================================================================
# AnVIL comparison
# =============================================================================

def compare_anvil(our_by_md5: dict, metadata_path: Path) -> dict:
    """Compare against AnVIL Azul metadata."""
    total_files = 0
    metadata_coverage = {}
    truth_records = []
    with open(metadata_path) as f:
        for line in f:
            r = json.loads(line)
            total_files += 1
            if r.get("data_modality") or r.get("reference_assembly"):
                truth_records.append({
                    "md5": r.get("file_md5sum"),
                    "file_name": r.get("file_name"),
                    "data_modality": r.get("data_modality"),
                    "reference_assembly": r.get("reference_assembly"),
                })

    # Count how many files have each dimension populated in AnVIL metadata
    for dim in DIMENSIONS:
        count = sum(1 for r in truth_records if r.get(dim))
        metadata_coverage[dim] = count

    field_mappings = {
        "data_modality": {
            "truth_field": "data_modality",
            "value_map": ANVIL_MODALITY_MAP,
        },
        "reference_assembly": {
            "truth_field": "reference_assembly",
            "value_map": ANVIL_REFERENCE_MAP,
        },
    }

    result = compare_source(
        our_by_md5, truth_records, "md5",
        field_mappings, ["data_modality", "reference_assembly"],
    )
    result["total_source_files"] = total_files
    result["metadata_coverage"] = metadata_coverage
    return result


# =============================================================================
# HPRC comparison — load pre-computed results from validate_against_hprc.py
# =============================================================================

def load_hprc_results(hprc_results_path: Path) -> dict:
    """Load pre-computed HPRC validation results and convert to report format.

    Reads from output/hprc_validation_results.json (produced by validate_against_hprc.py)
    and converts to the same format used by compare_source().
    """
    if not hprc_results_path.is_file():
        return {"matched": 0, "unmatched": 0, "dimensions": {}}

    with open(hprc_results_path) as f:
        data = json.load(f)

    # Handle both old format (results.total_validated) and new format (dimensions.*)
    dim_results = data.get("dimensions", {})
    mismatches = data.get("mismatches", [])

    total_matched = 0
    dimensions = {}

    for dim, stats in dim_results.items():
        match = stats.get("match", 0)
        mismatch = stats.get("mismatch", 0)
        unknown = stats.get("unknown", 0)
        total_matched = max(total_matched, match + mismatch + unknown)

        # Group discrepancies by category
        discrepancy_categories = {}
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
                        "example": m.get("file", ""),
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

    return {
        "matched": total_matched,
        "unmatched": 0,  # not meaningful across multiple HPRC catalogs
        "dimensions": dimensions,
    }


# =============================================================================
# Report generation
# =============================================================================

def escape_md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


SOURCE_INFO = {
    "AnVIL (Azul metadata)": {
        "text": "Validated against file-level metadata from the",
        "link_label": "AnVIL Data Explorer",
        "url": "https://explore.anvilproject.org/",
    },
    "HPRC (sequencing catalog)": {
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


def build_source_section(name: str, results: dict) -> str:
    # Short label for column headers: "AnVIL (Azul metadata)" -> "AnVIL"
    source_label = name.split("(")[0].strip() if "(" in name else name

    lines = []
    lines.append(f"## {name}")
    lines.append("")
    desc = source_desc_md(name)
    if desc:
        lines.append(desc)
        lines.append("")

    # Show metadata coverage if available
    total_source = results.get("total_source_files", 0)
    metadata_coverage = results.get("metadata_coverage", {})
    if total_source and metadata_coverage:
        lines.append(f"The source currently has **{total_source:,}** open-access files. "
                     f"The following shows how many files have each metadata dimension populated:")
        lines.append("")
        lines.append("| Dimension | Files with metadata |")
        lines.append("|---|---:|")
        for dim in DIMENSIONS:
            label = DIMENSION_LABELS.get(dim, dim)
            count = metadata_coverage.get(dim, 0)
            lines.append(f"| {label} | {count:,} |")
        lines.append("")

    if not results.get("dimensions"):
        lines.append("No dimensions to compare.")
        return "\n".join(lines)

    EMPTY_DIM = {"agree": 0, "discrepancy": 0, "we_inferred": 0,
                 "not_classified": 0, "no_truth": 0, "discrepancy_categories": {}}

    # Per-dimension summary
    for dim in DIMENSIONS:
        stats = results["dimensions"].get(dim, EMPTY_DIM)
        label = DIMENSION_LABELS.get(dim, dim)
        comparable = stats["agree"] + stats["discrepancy"]
        available = comparable + stats["not_classified"]
        accuracy = f"{100 * stats['agree'] / comparable:.1f}%" if comparable else "-"

        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- **{available:,}** values available from source")
        lines.append(f"- **{comparable:,}** also classified by rule engine")
        lines.append(f"- **{stats['not_classified']:,}** not classified by rule engine (no rule applies)")
        lines.append(f"- **{stats['agree']:,}** agreed")
        lines.append(f"- **{stats['discrepancy']:,}** discrepancies")
        lines.append(f"- **{accuracy}** accuracy")
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
        "source_descriptions": {
            name: source_desc_html(name)
            for name in all_results
            if source_desc_html(name)
        },
    }
    json_data = json.dumps(dashboard_data).replace("</", r"<\/")
    html = template.replace("VALIDATION_DATA_PLACEHOLDER", json_data)
    output_path.write_text(html)


def main():
    parser = argparse.ArgumentParser(description="Generate validation report")
    parser.add_argument("--run-dir", type=Path, help="Classification run directory")
    parser.add_argument("--metadata", type=Path,
                        default=Path("data/anvil_files_metadata.ndjson"),
                        help="AnVIL metadata NDJSON")
    parser.add_argument("--hprc-results", type=Path,
                        default=Path("output/hprc_validation_results.json"),
                        help="Pre-computed HPRC validation results")
    parser.add_argument("--output", type=Path,
                        default=Path("docs/validation-report.md"),
                        help="Output markdown file")
    args = parser.parse_args()

    try:
        run_dir = args.run_dir or find_latest_run(Path("output"))
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
    print(f"Loading classifications from: {run_dir}")

    our_by_md5, _ = load_our_classifications(run_dir)
    print(f"Loaded {len(our_by_md5):,} classifications by MD5")

    try:
        run_time = datetime.strptime(run_dir.name, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        run_time = run_dir.name

    # Run comparisons
    all_results = {}

    if args.metadata.is_file():
        print("Comparing against AnVIL metadata...")
        anvil_results = compare_anvil(our_by_md5, args.metadata)
        all_results["AnVIL (Azul metadata)"] = anvil_results
        print(f"  Matched: {anvil_results['matched']:,}, "
              f"Unmatched: {anvil_results['unmatched']:,}")

    if args.hprc_results.is_file():
        print("Loading HPRC validation results...")
        hprc_results = load_hprc_results(args.hprc_results)
        all_results["HPRC (sequencing catalog)"] = hprc_results
        print(f"  Matched: {hprc_results['matched']:,}, "
              f"Unmatched: {hprc_results['unmatched']:,}")

    if not all_results:
        print("No validation sources found", file=sys.stderr)
        sys.exit(1)

    # Generate markdown report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as out:
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
