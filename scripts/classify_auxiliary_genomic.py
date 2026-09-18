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
from meta_disco.producers import PRODUCERS
from meta_disco.records import OutputRecord, RunMetadata
from meta_disco.rule_engine import RuleEngine

# Routes through the shared predicate — see meta_disco.producers.
#
# That is also where an archive of fast5s stopped being this producer's problem. It used
# to need its own guard (`_is_archived`), because a source may declare the *core*
# extension for an archive (`.fast5` for `x.fast5.tar`) and this producer matched the
# format while the tar type matched the name, writing the file twice (#445). The shared
# predicate routes on the name first, so `x.fast5.tar` is the tar type's for the same
# reason any `.tar` is — without this producer knowing that tar exists.
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
        matched_ext = AUXILIARY.claim(f)
        if matched_ext is None:
            continue
        name = f.get("file_name", "")
        dataset_title = f.get("dataset_title", "")

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

        # One record shape for every producer (#450).
        results.append(OutputRecord.from_record(f, result.to_output_dict(), source).to_dict())

    # Print summary
    print("\n" + "=" * 70)
    print("AUXILIARY GENOMIC FILE CLASSIFICATION RESULTS")
    print("=" * 70)

    total_all = 0
    ref_all = 0

    # The registry's tuple, so two runs over one input order the summary identically.
    for ext in AUXILIARY.extensions:
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
                "metadata": RunMetadata.from_counts(
                    total=total_all,
                    successful=len(results),
                    from_cache=0,
                    content_unreadable=0,
                    details={
                        # The registry's tuple, not a set: its order is fixed, so two
                        # runs over the same input cannot write differently ordered output.
                        "by_extension": {
                            ext: stats[ext]["total"] for ext in AUXILIARY.extensions if stats[ext]["total"] > 0
                        },
                        "with_reference": ref_all,
                    },
                ).to_dict(),
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
        default=Path("output/anvil") / AUXILIARY.output,
        help="Output path for classifications",
    )
    args = parser.parse_args()

    classify_auxiliary_genomic(args.metadata, args.output)


if __name__ == "__main__":
    main()
