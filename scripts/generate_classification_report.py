#!/usr/bin/env python3
"""Generate classification coverage report with charts."""

import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


def _val(rec, field):
    """Extract value from per-field or flat format."""
    cls = rec.get("classifications", {})
    if isinstance(cls, dict) and field in cls:
        v = cls[field]
        return v["value"] if isinstance(v, dict) and "value" in v else v
    v = rec.get(field)
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


# =============================================================================
# FILE FORMAT CATEGORY RULES
# =============================================================================

# Extension -> category mapping (first match wins for extension lookups)
FORMAT_CATEGORY_RULES = [
    # Index files
    {"extensions": [".bai", ".tbi", ".csi", ".crai", ".pbi"], "category": "Index"},
    # Alignment files
    {"extensions": [".bam", ".cram"], "category": "BAM/CRAM"},
    # Variant files
    {"extensions": [".vcf", ".vcf.gz", ".bcf", ".gvcf", ".gvcf.gz", ".g.vcf.gz"], "category": "VCF"},
    # Sequence files
    {"extensions": [".fastq", ".fastq.gz", ".fq", ".fq.gz"], "category": "FASTQ"},
    # BED files
    {"extensions": [".bed", ".bed.gz"], "category": "BED"},
    # Image files
    {"extensions": [".svs", ".png", ".jpg", ".jpeg", ".tiff", ".tif"], "category": "Images"},
    # Raw signal files (ONT)
    {"extensions": [".fast5", ".pod5"], "category": "Auxiliary", "name_contains": ".fast5"},
    # PLINK files
    {"extensions": [".pvar", ".psam", ".pgen", ".bim", ".fam"], "category": "Auxiliary"},
    # Skip files (checksums, logs, documentation)
    {"extensions": [".md5", ".log", ".txt", ".html", ".pdf", ".json", ".csv", ".tsv"], "category": "Skipped"},
    # Archive files (need extraction to classify)
    {"extensions": [".tar", ".tar.gz", ".zip"], "category": "Skipped"},
]


def load_source_metadata(path: Path) -> list[dict]:
    """Load source metadata file."""
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("files", data.get("results", []))


def load_classifications(output_dir: Path) -> dict[str, list[dict]]:
    """Load all classification outputs."""
    classifications = {}

    files_to_load = {
        "BAM/CRAM": "bam_classifications.json",
        "VCF": "vcf_classifications.json",
        "FASTQ": "fastq_classifications.json",
        "BED": "bed_classifications.json",
        "Images": "image_classifications.json",
        "Auxiliary": "auxiliary_classifications.json",
        "Index": "index_classifications.json",
    }

    for name, filename in files_to_load.items():
        path = output_dir / filename
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            classifications[name] = data.get("classifications", [])
        else:
            classifications[name] = []

    return classifications


def get_file_format_category(fmt: str, name: str = "") -> str:
    """Categorize file format using FORMAT_CATEGORY_RULES."""
    fmt_lower = fmt.lower() if fmt else ""
    name_lower = name.lower() if name else ""

    for rule in FORMAT_CATEGORY_RULES:
        # Check extension match
        if fmt_lower in rule["extensions"]:
            return rule["category"]
        # Check optional name_contains pattern
        if "name_contains" in rule and rule["name_contains"] in name_lower:
            return rule["category"]

    return "Other"


def generate_report(source_path: Path, output_dir: Path, report_path: Path):
    """Generate classification coverage report."""

    # Load data
    print("Loading source metadata...")
    source_files = load_source_metadata(source_path)
    total_files = len(source_files)
    print(f"  Total files: {total_files:,}")

    print("Loading classifications...")
    classifications = load_classifications(output_dir)

    # Count classified files by category
    classified_counts = {name: len(items) for name, items in classifications.items()}
    total_classified = sum(classified_counts.values())

    print(f"  Classified: {total_classified:,}")
    for name, count in classified_counts.items():
        print(f"    {name}: {count:,}")

    # Categorize source files
    print("\nCategorizing source files...")
    source_categories = Counter()
    for f in source_files:
        fmt = f.get("file_format", "")
        name = f.get("file_name", "")
        category = get_file_format_category(fmt, name)
        source_categories[category] += 1

    # Merge all classifications for analysis
    all_classified = []
    for name, items in classifications.items():
        for item in items:
            item["_source"] = name
            all_classified.append(item)

    # Create figure with subplots (4 rows x 2 cols for 7 panels + spacing)
    fig = plt.figure(figsize=(16, 24))
    fig.suptitle("Meta-disco Classification Coverage Report", fontsize=16, fontweight="bold", y=0.98)

    # Color palette
    colors = plt.cm.Set3(np.linspace(0, 1, 12))

    # === Panel 1: Input Overview (pie chart) ===
    ax1 = fig.add_subplot(4, 2, 1)

    # Prepare data for pie chart
    categories_for_pie = {k: v for k, v in source_categories.items() if v > 1000}
    small_categories = sum(v for k, v in source_categories.items() if v <= 1000)
    if small_categories > 0:
        categories_for_pie["Other (<1k each)"] = small_categories

    labels = list(categories_for_pie.keys())
    sizes = list(categories_for_pie.values())

    wedges, texts, autotexts = ax1.pie(
        sizes,
        labels=None,
        autopct=lambda p: f'{p:.1f}%' if p > 3 else '',
        colors=colors[:len(sizes)],
        startangle=90
    )
    ax1.set_title(f"Input Files by Category\n(Total: {total_files:,})", fontweight="bold")

    # Add legend
    legend_labels = [f"{l}: {s:,}" for l, s in zip(labels, sizes)]
    ax1.legend(wedges, legend_labels, loc="center left", bbox_to_anchor=(1, 0.5), fontsize=8)

    # === Panel 2: Classification Coverage (horizontal bar) ===
    ax2 = fig.add_subplot(4, 2, 2)

    # Calculate coverage per category
    coverage_data = []
    for category in ["BAM/CRAM", "VCF", "FASTQ", "BED", "Images", "Auxiliary", "Index"]:
        source_count = source_categories.get(category, 0)
        classified_count = classified_counts.get(category, 0)
        if source_count > 0:
            coverage_data.append({
                "category": category,
                "source": source_count,
                "classified": classified_count,
                "coverage": classified_count / source_count * 100 if source_count > 0 else 0
            })

    # Sort by source count
    coverage_data.sort(key=lambda x: x["source"], reverse=True)

    y_pos = np.arange(len(coverage_data))
    source_counts = [d["source"] for d in coverage_data]
    classified_counts_list = [d["classified"] for d in coverage_data]
    categories_list = [d["category"] for d in coverage_data]

    bars1 = ax2.barh(y_pos, source_counts, alpha=0.3, color="steelblue", label="Total in source")
    bars2 = ax2.barh(y_pos, classified_counts_list, color="steelblue", label="Classified")

    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(categories_list)
    ax2.set_xlabel("Number of Files")
    ax2.set_title("Classification Coverage by File Type", fontweight="bold")
    ax2.legend(loc="lower right")

    # Add coverage percentages
    for i, d in enumerate(coverage_data):
        ax2.text(d["source"] + 1000, i, f'{d["coverage"]:.1f}%', va="center", fontsize=9)

    ax2.set_xlim(0, max(source_counts) * 1.15)

    # === Panel 3: data_modality distribution ===
    ax3 = fig.add_subplot(4, 2, 3)

    modality_counts = Counter()
    for item in all_classified:
        mod = _val(item, "data_modality") or "N/A"
        modality_counts[mod] += 1

    # Sort by count
    modality_sorted = sorted(modality_counts.items(), key=lambda x: x[1], reverse=True)
    mod_labels = [m[0] for m in modality_sorted]
    mod_values = [m[1] for m in modality_sorted]

    y_pos = np.arange(len(mod_labels))
    bars = ax3.barh(y_pos, mod_values, color=colors[:len(mod_labels)])
    ax3.set_yticks(y_pos)
    ax3.set_yticklabels(mod_labels, fontsize=9)
    ax3.set_xlabel("Number of Files")
    ax3.set_title("Distribution by data_modality", fontweight="bold")
    ax3.invert_yaxis()

    # Add counts
    for i, v in enumerate(mod_values):
        ax3.text(v + 500, i, f'{v:,}', va="center", fontsize=8)

    # === Panel 4: reference_assembly distribution ===
    ax4 = fig.add_subplot(4, 2, 4)

    ref_counts = Counter()
    for item in all_classified:
        ref = _val(item, "reference_assembly") or "N/A"
        ref_counts[ref] += 1

    ref_sorted = sorted(ref_counts.items(), key=lambda x: x[1], reverse=True)
    ref_labels = [r[0] for r in ref_sorted]
    ref_values = [r[1] for r in ref_sorted]

    y_pos = np.arange(len(ref_labels))
    bars = ax4.barh(y_pos, ref_values, color=["#2ecc71", "#e74c3c", "#3498db", "#95a5a6", "#9b59b6"][:len(ref_labels)])
    ax4.set_yticks(y_pos)
    ax4.set_yticklabels(ref_labels)
    ax4.set_xlabel("Number of Files")
    ax4.set_title("Distribution by reference_assembly", fontweight="bold")
    ax4.invert_yaxis()

    for i, v in enumerate(ref_values):
        ax4.text(v + 500, i, f'{v:,}', va="center", fontsize=8)

    # === Panel 5: platform distribution ===
    ax5 = fig.add_subplot(4, 2, 5)

    platform_counts = Counter()
    for item in all_classified:
        plat = _val(item, "platform") or "N/A"
        platform_counts[plat] += 1

    plat_sorted = sorted(platform_counts.items(), key=lambda x: x[1], reverse=True)
    plat_labels = [p[0] for p in plat_sorted]
    plat_values = [p[1] for p in plat_sorted]

    y_pos = np.arange(len(plat_labels))
    bars = ax5.barh(y_pos, plat_values, color=colors[:len(plat_labels)])
    ax5.set_yticks(y_pos)
    ax5.set_yticklabels(plat_labels)
    ax5.set_xlabel("Number of Files")
    ax5.set_title("Distribution by platform", fontweight="bold")
    ax5.invert_yaxis()

    for i, v in enumerate(plat_values):
        ax5.text(v + 500, i, f'{v:,}', va="center", fontsize=8)

    # === Panel 6: data_type distribution ===
    ax6 = fig.add_subplot(4, 2, 6)

    # For data_type, infer from source if not present
    dtype_counts = Counter()
    for item in all_classified:
        dtype = _val(item, "data_type")
        if not dtype:
            # Infer from source
            source = item.get("_source", "")
            if source == "BAM/CRAM":
                dtype = "alignments"
            elif source == "VCF":
                vtype = item.get("variant_type", "")
                if vtype in ["structural", "cnv"]:
                    dtype = "structural_variants"
                else:
                    dtype = "variant_calls"
            elif source == "FASTQ":
                dtype = "reads"
            elif source == "Images":
                dtype = "images"
            elif source == "Index":
                dtype = "index"
            else:
                dtype = "other"
        dtype_counts[dtype] += 1

    dtype_sorted = sorted(dtype_counts.items(), key=lambda x: x[1], reverse=True)
    dtype_labels = [d[0] for d in dtype_sorted]
    dtype_values = [d[1] for d in dtype_sorted]

    y_pos = np.arange(len(dtype_labels))
    bars = ax6.barh(y_pos, dtype_values, color=colors[:len(dtype_labels)])
    ax6.set_yticks(y_pos)
    ax6.set_yticklabels(dtype_labels)
    ax6.set_xlabel("Number of Files")
    ax6.set_title("Distribution by data_type", fontweight="bold")
    ax6.invert_yaxis()

    for i, v in enumerate(dtype_values):
        ax6.text(v + 500, i, f'{v:,}', va="center", fontsize=8)

    # === Panel 7: assay_type distribution ===
    ax7 = fig.add_subplot(4, 2, 7)

    # For assay_type, infer from source/platform if not present
    assay_counts = Counter()
    for item in all_classified:
        assay = _val(item, "assay_type")
        if not assay:
            # Infer from source and platform
            source = item.get("_source", "")
            platform = _val(item, "platform")
            modality = _val(item, "data_modality") or ""

            if platform in ["PACBIO", "ONT"]:
                assay = "WGS"
            elif "transcriptomic" in modality:
                assay = "RNA-seq"
            elif source == "Images":
                assay = "Histology"
            else:
                assay = "N/A"
        assay_counts[assay] += 1

    assay_sorted = sorted(assay_counts.items(), key=lambda x: x[1], reverse=True)
    assay_labels = [a[0] for a in assay_sorted]
    assay_values = [a[1] for a in assay_sorted]

    y_pos = np.arange(len(assay_labels))
    bars = ax7.barh(y_pos, assay_values, color=colors[:len(assay_labels)])
    ax7.set_yticks(y_pos)
    ax7.set_yticklabels(assay_labels)
    ax7.set_xlabel("Number of Files")
    ax7.set_title("Distribution by assay_type", fontweight="bold")
    ax7.invert_yaxis()

    for i, v in enumerate(assay_values):
        ax7.text(v + 500, i, f'{v:,}', va="center", fontsize=8)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    # Save figure
    report_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(report_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"\nSaved report to {report_path}")

    # Print summary stats
    print("\n" + "=" * 70)
    print("CLASSIFICATION SUMMARY")
    print("=" * 70)
    print(f"\nTotal source files: {total_files:,}")
    print(f"Total classified:   {total_classified:,} ({total_classified/total_files*100:.1f}%)")

    skipped = source_categories.get("Skipped", 0) + source_categories.get("Other", 0)
    classifiable = total_files - skipped
    print(f"Classifiable files: {classifiable:,} ({classifiable/total_files*100:.1f}%)")
    print(f"Skipped/Other:      {skipped:,} ({skipped/total_files*100:.1f}%)")

    print("\n--- Coverage by Axis ---")

    with_modality = sum(1 for item in all_classified if _val(item, "data_modality"))
    with_ref = sum(1 for item in all_classified if _val(item, "reference_assembly"))
    with_platform = sum(1 for item in all_classified if _val(item, "platform"))
    with_dtype = sum(1 for item in all_classified if _val(item, "data_type") or item.get("_source") in ["BAM/CRAM", "VCF", "FASTQ"])
    with_assay = sum(1 for item in all_classified if _val(item, "assay_type"))

    print(f"data_modality:      {with_modality:,} / {total_classified:,} ({with_modality/total_classified*100:.1f}%)")
    print(f"reference_assembly: {with_ref:,} / {total_classified:,} ({with_ref/total_classified*100:.1f}%)")
    print(f"platform:           {with_platform:,} / {total_classified:,} ({with_platform/total_classified*100:.1f}%)")
    print(f"data_type:          {with_dtype:,} / {total_classified:,} ({with_dtype/total_classified*100:.1f}%)")
    print(f"assay_type:         {with_assay:,} / {total_classified:,} ({with_assay/total_classified*100:.1f}%)")

    return fig


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate classification report")
    parser.add_argument(
        "--source", "-s",
        type=Path,
        default=Path("data/anvil_files_metadata.json"),
        help="Source metadata file",
    )
    parser.add_argument(
        "--output-dir", "-d",
        type=Path,
        default=Path("output"),
        help="Directory containing classification outputs",
    )
    parser.add_argument(
        "--report", "-r",
        type=Path,
        default=Path("output/classification_report.png"),
        help="Output report path",
    )
    args = parser.parse_args()

    generate_report(args.source, args.output_dir, args.report)


if __name__ == "__main__":
    main()
