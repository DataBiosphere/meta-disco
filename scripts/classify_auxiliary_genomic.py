#!/usr/bin/env python3
"""Classify auxiliary genomic files using RuleEngine.

Uses rules from the bundled unified_rules.yaml (package data of meta_disco.rules) for:
- .fast5, .pod5 -> genomic.raw_signal (ONT raw signal data)
- .pvar, .psam, .pgen -> genomic.genotypes (PLINK2 genotype data)
"""

import argparse
import json
from pathlib import Path

# Add project root to path for imports
from meta_disco.models import FileInfo, field_label
from meta_disco.pipeline import load_classifiable_snapshot
from meta_disco.producers import PRODUCERS, matched_extension
from meta_disco.records import identity_from, published_from
from meta_disco.rule_engine import RuleEngine

# What this producer claims is declared in the producer registry, and asked through the
# one routing predicate every producer asks (#449) — so no file can be this producer's
# and another's at once.
#
# This is also where an archive of fast5s stops being this producer's problem. It used
# to need its own guard (`_is_archived`), because a source may declare the *core*
# extension for an archive (`.fast5` for `x.fast5.tar`) and this producer matched the
# format while the tar type matched the name, writing the file twice (#445). The shared
# predicate routes on the name first, so `x.fast5.tar` is the tar type's for the same
# reason any `.tar` is, and a container is not its contents (#242) without this producer
# knowing that tar exists.
AUXILIARY = PRODUCERS["auxiliary"]


def classify_auxiliary_genomic(metadata_path: Path, output_path: Path):
    """Classify auxiliary genomic files using RuleEngine."""

    # Records with no usable file_md5sum are excluded here, at the shared load path,
    # so no classification output can name a file the run could never fetch (#376).
    # The load also records what it excluded into the run directory this output lands in.
    source, files = load_classifiable_snapshot(metadata_path, output_path.parent)
    print(f"Loaded {len(files):,} files from metadata")

    engine = RuleEngine()
    results = []
    stats = {ext: {"total": 0, "with_ref": 0} for ext in AUXILIARY.extensions}

    for f in files:
        if not AUXILIARY.claims(f):
            continue
        name = f.get("file_name", "")
        fmt = f.get("file_format", "")
        dataset_title = f.get("dataset_title", "")

        matched_ext = matched_extension(f)
        stats[matched_ext]["total"] += 1

        # Classify using RuleEngine
        file_info = FileInfo.from_filename(
            name,
            file_size=f.get("file_size"),
            dataset_title=dataset_title,
        )
        result = engine.classify_extended(file_info)

        # reference_assembly holds a real value or None (the sentinel lives in
        # status now — epic #116 / #136), so truthiness = a real reference.
        if result.reference_assembly:
            stats[matched_ext]["with_ref"] += 1

        results.append(
            {
                "file_name": name,
                "file_format": fmt,
                "md5sum": f.get("file_md5sum"),
                "file_size": f.get("file_size"),
                **identity_from(f),
                "dataset_id": f.get("dataset_id"),
                "dataset_title": dataset_title,
                "classifications": result.to_output_dict(),
                # What AnVIL declares about this file today, carried beside what this
                # run concluded. Contract 7.7 binds every producer: omitting it does
                # not fail, it under-reports.
                "published": published_from(f, source),
            }
        )

    # Print summary
    print("\n" + "=" * 70)
    print("AUXILIARY GENOMIC FILE CLASSIFICATION RESULTS")
    print("=" * 70)

    total_all = 0
    ref_all = 0

    for ext in sorted(AUXILIARY.extensions):
        s = stats[ext]
        if s["total"] > 0:
            total_all += s["total"]
            ref_all += s["with_ref"]
            ref_pct = s["with_ref"] / s["total"] * 100 if s["total"] > 0 else 0
            print(f"\n{ext}:")
            print(f"  Total:      {s['total']:>7,}")
            print(f"  With ref:   {s['with_ref']:>7,} ({ref_pct:.1f}%)")

    print(f"\n{'=' * 70}")
    print(f"Total auxiliary genomic files: {total_all:,}")
    print(f"With reference_assembly: {ref_all:,}")
    print("=" * 70)

    # Count by modality
    modalities = {}
    for r in results:
        mod = field_label(r, "data_modality")
        modalities[mod] = modalities.get(mod, 0) + 1

    print("\nBy modality:")
    for mod, count in sorted(modalities.items(), key=lambda x: -x[1]):
        print(f"  {mod}: {count:,}")

    # Count by reference
    refs = {}
    for r in results:
        ref = field_label(r, "reference_assembly")
        refs[ref] = refs.get(ref, 0) + 1

    print("\nBy reference_assembly:")
    for ref, count in sorted(refs.items(), key=lambda x: -x[1]):
        print(f"  {ref}: {count:,}")

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(
            {
                "metadata": {
                    "total_files": total_all,
                    # Sorted: a set's iteration order varies between processes, and two
                    # runs over the same input must not write differently ordered output.
                    "by_extension": {
                        ext: stats[ext]["total"] for ext in sorted(AUXILIARY.extensions) if stats[ext]["total"] > 0
                    },
                    "with_reference": ref_all,
                    "complete": True,
                },
                "classifications": results,
            },
            f,
            indent=2,
        )

    print(f"\nSaved {len(results):,} classifications to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Classify auxiliary genomic files")
    parser.add_argument(
        "--metadata",
        "-m",
        type=Path,
        default=Path("data/anvil/anvil_files_metadata.json"),
        help="Path to source metadata JSON",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output/anvil/auxiliary_classifications.json"),
        help="Output path for classifications",
    )
    args = parser.parse_args()

    classify_auxiliary_genomic(args.metadata, args.output)


if __name__ == "__main__":
    main()
