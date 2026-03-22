#!/usr/bin/env python3 -u
"""Validate classifications against HPRC metadata.

Cross-references our classifications with the official HPRC Data Explorer
catalogs (sequencing-data, alignments, annotations, assemblies).

Validates platform, data_modality, assay_type, and reference_assembly
using file-level matching by filename.

Usage:
    python scripts/validate_hprc_samples.py
    python scripts/validate_hprc_samples.py --catalog-dir data/hprc
    python scripts/validate_hprc_samples.py --fetch --limit 100

Output saved to: output/hprc_validation_results.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.meta_disco.validation_maps import (
    HPRC_CATALOG_BASE_URL,
    HPRC_CATALOG_NAMES,
    HPRC_LIBRARY_SOURCE_MAP,
    HPRC_LIBRARY_STRATEGY_MAP,
    HPRC_PLATFORM_MAP,
    HPRC_REF_COORDINATES_MAP,
    extract_ref_from_annotation_type,
    get_classification_value,
)


def load_catalog(name: str, catalog_dir: Path | None, fetch: bool) -> list[dict]:
    """Load a single HPRC catalog from cache or fetch live."""
    if catalog_dir and not fetch:
        path = catalog_dir / f"{name}.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            print(f"  {name}: {len(data):,} records (cached)")
            return data

    url = f"{HPRC_CATALOG_BASE_URL}/{name}.json"
    print(f"  {name}: fetching...", end=" ", flush=True)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    print(f"{len(data):,} records")

    if catalog_dir:
        catalog_dir.mkdir(parents=True, exist_ok=True)
        (catalog_dir / f"{name}.json").write_text(json.dumps(data, separators=(",", ":")))

    return data


def load_all_catalogs(
    catalog_dir: Path | None, fetch: bool
) -> dict[str, list[dict]]:
    """Load all HPRC catalogs."""
    print("Loading HPRC catalogs...")
    catalogs = {}
    for name in HPRC_CATALOG_NAMES:
        try:
            catalogs[name] = load_catalog(name, catalog_dir, fetch)
        except Exception as e:
            print(f"  {name}: ERROR {e}")
            catalogs[name] = []
    return catalogs


def build_sequencing_lookup(records: list[dict]) -> dict[str, dict]:
    """Build filename -> metadata from sequencing-data catalog."""
    lookup = {}
    for r in records:
        fn = r.get("filename", "")
        if not fn:
            continue
        hprc_platform = r.get("platform", "")
        library_source = (r.get("librarySource") or "").upper()
        library_strategy = r.get("libraryStrategy") or ""
        lookup[fn] = {
            "platform": HPRC_PLATFORM_MAP.get(hprc_platform, hprc_platform),
            "data_modality": HPRC_LIBRARY_SOURCE_MAP.get(library_source),
            "assay_type": HPRC_LIBRARY_STRATEGY_MAP.get(library_strategy),
            "instrument_model": r.get("instrumentModel"),
            "sample_id": r.get("sampleId"),
        }
    return lookup


def build_alignments_lookup(records: list[dict]) -> dict[str, dict]:
    """Build filename -> metadata from alignments catalog."""
    lookup = {}
    for r in records:
        fn = r.get("filename", "")
        if not fn:
            continue
        ref_coords = (r.get("referenceCoordinates") or "").lower()
        ref = HPRC_REF_COORDINATES_MAP.get(ref_coords)
        if ref:
            lookup[fn] = {"reference_assembly": ref}
    return lookup


def build_annotations_lookup(records: list[dict]) -> dict[str, dict]:
    """Build filename -> metadata from annotations catalog."""
    lookup = {}
    for r in records:
        fn = r.get("filename", "")
        if not fn:
            continue
        annotation_type = r.get("annotationType", "")
        ref = extract_ref_from_annotation_type(annotation_type)
        if ref:
            lookup[fn] = {
                "reference_assembly": ref,
                "annotation_type": annotation_type,
            }
    return lookup


def build_assemblies_lookup(records: list[dict]) -> set[str]:
    """Build set of filenames from assemblies catalog (presence tracking only)."""
    return {r.get("filename", "") for r in records} - {""}


def validate_dimension(
    our_value: str | None,
    expected_value: str | None,
    counters: Counter,
    dim_name: str,
) -> dict | None:
    """Validate a single dimension. Returns mismatch info or None."""
    if not expected_value:
        return None  # HPRC has no ground truth for this dimension

    if not our_value:
        counters[f"{dim_name}_unknown"] += 1
        return None

    if our_value.upper() == expected_value.upper():
        counters[f"{dim_name}_match"] += 1
        return None

    counters[f"{dim_name}_mismatch"] += 1
    return {"ours": our_value, "expected": expected_value}


def validate_against_hprc(
    input_paths: list[Path],
    output_path: Path,
    catalog_dir: Path | None,
    fetch: bool = False,
    limit: int | None = None,
):
    """Validate classifications against all HPRC catalogs."""

    # Load catalogs
    catalogs = load_all_catalogs(catalog_dir, fetch)

    # Build per-catalog lookups
    seq_lookup = build_sequencing_lookup(catalogs.get("sequencing-data", []))
    align_lookup = build_alignments_lookup(catalogs.get("alignments", []))
    annot_lookup = build_annotations_lookup(catalogs.get("annotations", []))
    asm_lookup = build_assemblies_lookup(catalogs.get("assemblies", []))

    print("\nFilename lookups built:")
    print(f"  sequencing-data: {len(seq_lookup):,} files")
    print(f"  alignments:      {len(align_lookup):,} files (with reference)")
    print(f"  annotations:     {len(annot_lookup):,} files (with reference)")
    print(f"  assemblies:      {len(asm_lookup):,} files")

    # Load our classifications
    all_classifications = []
    for input_path in input_paths:
        if not input_path.exists():
            print(f"  Skipping {input_path} (not found)")
            continue
        print(f"Loading {input_path}...", flush=True)
        with open(input_path) as f:
            data = json.load(f)
        classifications = data.get("classifications", data)
        if isinstance(classifications, list):
            all_classifications.extend(classifications)

    print(f"Loaded {len(all_classifications):,} total classifications")

    if limit:
        all_classifications = all_classifications[:limit]
        print(f"Limiting to {limit} files")

    # Validate
    counters: Counter = Counter()
    mismatches: list[dict] = []
    catalog_stats = {name: {"matched": 0} for name in HPRC_CATALOG_NAMES}

    print("\nValidating...", flush=True)

    for c in all_classifications:
        filename = c.get("file_name", "")
        file_mismatches = {}

        # --- sequencing-data: platform, data_modality, assay_type ---
        if filename in seq_lookup:
            catalog_stats["sequencing-data"]["matched"] += 1
            meta = seq_lookup[filename]

            our_platform = get_classification_value(c, "platform") or ""
            m = validate_dimension(our_platform, meta["platform"], counters, "platform")
            if m:
                m["hprc_instrument"] = meta.get("instrument_model")
                m["our_instrument"] = get_classification_value(c, "instrument_model")
                file_mismatches["platform"] = m

            our_modality = get_classification_value(c, "data_modality") or ""
            m = validate_dimension(
                our_modality, meta["data_modality"], counters, "data_modality"
            )
            if m:
                file_mismatches["data_modality"] = m

            our_assay = get_classification_value(c, "assay_type") or ""
            m = validate_dimension(
                our_assay, meta["assay_type"], counters, "assay_type"
            )
            if m:
                file_mismatches["assay_type"] = m

        # --- alignments: reference_assembly ---
        if filename in align_lookup:
            catalog_stats["alignments"]["matched"] += 1
            meta = align_lookup[filename]

            our_ref = get_classification_value(c, "reference_assembly") or ""
            m = validate_dimension(our_ref, meta["reference_assembly"], counters, "reference_assembly")
            if m:
                m["source"] = "alignments"
                file_mismatches["reference_assembly"] = m

        # --- annotations: reference_assembly ---
        if filename in annot_lookup:
            catalog_stats["annotations"]["matched"] += 1
            meta = annot_lookup[filename]

            our_ref = get_classification_value(c, "reference_assembly") or ""
            m = validate_dimension(our_ref, meta["reference_assembly"], counters, "reference_assembly")
            if m:
                m["source"] = "annotations"
                m["annotation_type"] = meta.get("annotation_type")
                file_mismatches["reference_assembly"] = m

        # --- assemblies: presence tracking ---
        if filename in asm_lookup:
            catalog_stats["assemblies"]["matched"] += 1

        if file_mismatches:
            mismatches.append({"file": filename, **file_mismatches})

    # --- Summary ---
    print()
    print("=" * 60)
    print("HPRC VALIDATION RESULTS")
    print("=" * 60)

    print("\nCatalog coverage:")
    for name in HPRC_CATALOG_NAMES:
        n_records = len(catalogs.get(name, []))
        n_matched = catalog_stats[name]["matched"]
        print(f"  {name:20s}: {n_matched:,} matched / {n_records:,} records")

    dimensions = ["platform", "data_modality", "assay_type", "reference_assembly"]
    dim_results = {}

    print("\nDimension accuracy:")
    for dim in dimensions:
        match = counters.get(f"{dim}_match", 0)
        mismatch = counters.get(f"{dim}_mismatch", 0)
        unknown = counters.get(f"{dim}_unknown", 0)
        validated = match + mismatch

        dim_results[dim] = {
            "match": match,
            "mismatch": mismatch,
            "unknown": unknown,
            "validated": validated,
        }

        if validated > 0:
            accuracy = 100 * match / validated
            dim_results[dim]["accuracy"] = f"{accuracy:.2f}%"
            print(f"  {dim:25s}: {match:,}/{validated:,} ({accuracy:.2f}%)")
            if unknown:
                print(f"  {'':25s}  + {unknown:,} unclassified")
        else:
            print(f"  {dim:25s}: no matches")

    if mismatches:
        print(f"\nMismatches: {len(mismatches):,}")
        print("Sample mismatches (first 10):")
        for m in mismatches[:10]:
            print(f"  {m['file'][:60]}")
            for dim_name in dimensions:
                if dim_name in m:
                    info = m[dim_name]
                    print(f"    {dim_name}: ours={info['ours']} expected={info['expected']}")

    print("=" * 60)

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(
            {
                "metadata": {
                    "catalogs_loaded": {
                        name: len(catalogs.get(name, []))
                        for name in HPRC_CATALOG_NAMES
                    },
                    "source": HPRC_CATALOG_BASE_URL,
                },
                "by_catalog": catalog_stats,
                "dimensions": dim_results,
                "mismatches": mismatches,
            },
            f,
            indent=2,
        )

    print(f"\nResults saved to: {output_path}")
    return dim_results


def main():
    parser = argparse.ArgumentParser(
        description="Validate classifications against HPRC catalogs"
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        nargs="+",
        default=[
            Path("output/bam_classifications.json"),
            Path("output/fastq_classifications.json"),
            Path("output/bed_classifications.json"),
            Path("output/auxiliary_classifications.json"),
            Path("output/fasta_classifications.json"),
        ],
        help="Input classification files",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output/hprc_validation_results.json"),
        help="Output file",
    )
    parser.add_argument(
        "--catalog-dir",
        type=Path,
        default=Path("data/hprc"),
        help="Directory with cached HPRC catalogs (default: data/hprc)",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch catalogs fresh from GitHub (ignoring cache)",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Limit files to validate",
    )
    args = parser.parse_args()

    validate_against_hprc(
        args.input, args.output, args.catalog_dir, args.fetch, args.limit
    )


if __name__ == "__main__":
    main()
