#!/usr/bin/env python3
"""Propagate metadata from parent files to index files.

Index files inherit all five of ``CLASSIFICATION_FIELDS`` from their parent,
which is found by filename within a dataset. ``INDEX_TO_PARENT`` declares which
index extensions have which parent extensions.

A filename does not always identify one file. Where two files in a dataset share
the name an index points at, no parent is chosen: the index inherits nothing and
is listed in ``unmatched_files`` with reason ``AMBIGUOUS_PARENT`` (#438).

The lookup used to keep whichever file load order visited last. Measured on the
anvil15 corpus, 15,006 index files took a parent picked that way, and 7,422 of
them were wrong about their reference assembly — verified against the storage
paths in the manifest's ``file_inventory`` table, which name the true parent.
``ANVIL_T2T_CHRY`` is why: it calls one sample against both CHM13v2 and GRCh38
and stores the outputs under the same filename in different directories.

Telling such files apart needs a path or a declared parent-child relationship,
and this producer can see neither — the compact manifest it reads carries no
storage path and no sibling relation. So it declines rather than guesses. Doing
better is import work (#369, #402).
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from meta_disco.models import (
    CLASSIFICATION_FIELDS,
    CONFLICT,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_DERIVATION_INHERITANCE,
    build_field_entry,
    field_detail,
    field_label,
    status_for_value,
)
from meta_disco.pipeline import load_classifiable_snapshot
from meta_disco.records import coerce_identity, published_from

# Why an index file took no parent. Written into each `unmatched_files` entry and
# read back by this module's diagnostics and its tests, so it is named rather than
# spelled three times.
NO_MATCHING_PARENT = "no_matching_parent_in_dataset"
AMBIGUOUS_PARENT = "ambiguous_parent_in_dataset"

# Index extension -> parent extension mapping
# List specific compound extensions to avoid false candidates from bare .gz
INDEX_TO_PARENT = {
    ".bai": [".bam"],
    ".tbi": [".vcf.gz", ".bed.gz", ".txt.gz", ".tsv.gz", ".gff.gz", ".gtf.gz"],
    ".csi": [".vcf.gz", ".bcf", ".bed.gz"],  # CSI can index BED files too
    ".crai": [".cram"],
    ".pbi": [".bam"],
}


def get_parent_candidates(index_name: str, index_ext: str) -> list[str]:
    """Get possible parent filenames for an index file.

    Handles both patterns:
    - sample.bam.bai -> sample.bam (Pattern 1: index appended to parent)
    - sample.bai -> sample.bam (Pattern 2: index replaces parent ext)
    """
    candidates = []
    parent_exts = INDEX_TO_PARENT.get(index_ext, [])

    if index_name.endswith(index_ext):
        base = index_name[: -len(index_ext)]

        # Pattern 1: index ext appended to parent (sample.bam.bai -> sample.bam)
        # This is the most common pattern
        pattern1_matched = False
        for parent_ext in parent_exts:
            if base.endswith(parent_ext):
                candidates.append(base)
                pattern1_matched = True
                break  # Only add once

        # Pattern 2: index ext replaces parent ext (sample.bai -> sample.bam)
        # Only try this if Pattern 1 didn't match (avoids junk like sample.vcf.gz.vcf.gz)
        if not pattern1_matched:
            for parent_ext in parent_exts:
                candidate = base + parent_ext
                if candidate not in candidates:
                    candidates.append(candidate)

    return candidates


def unmatched_entry(record: dict, index_ext: str, candidates: list[str], reason: str, **extra: object) -> dict:
    """One ``unmatched_files`` entry: an index file that took no parent, and why.

    Both reasons share an identity echo, so the shape is built once here rather than
    spelled per branch — a field added to the entry reaches every reason. Identity is
    echoed through :func:`coerce_identity`, as ``excluded_files.json`` echoes one
    (#376), so a drifted ``file_name`` of ``0`` renders as ``"0"`` and not ``""``.
    ``dataset_id`` is the lookup key this producer groups by and is passed through as
    it was read.
    """
    return {
        "file_name": coerce_identity(record.get("file_name")),
        "file_format": coerce_identity(record.get("file_format")),
        "file_md5sum": coerce_identity(record.get("file_md5sum")),
        "entry_id": coerce_identity(record.get("entry_id")),
        "dataset_id": record.get("dataset_id", "unknown"),
        "dataset_title": coerce_identity(record.get("dataset_title")),
        "index_extension": index_ext,
        "candidates_tried": candidates,
        "reason": reason,
        **extra,
    }


def load_classifications(*paths: Path) -> dict[str, dict]:
    """Load classifications from one or more classification JSON files, keyed by md5sum."""
    classifications = {}

    for path in paths:
        if not path.is_file():
            continue
        with path.open() as f:
            data = json.load(f)
        for c in data.get("classifications", []):
            md5 = c.get("md5sum")
            if md5:
                classifications[md5] = {
                    "data_modality": field_label(c, "data_modality"),
                    "data_type": field_label(c, "data_type"),
                    "assay_type": field_label(c, "assay_type"),
                    "platform": field_label(c, "platform"),
                    "reference_assembly": field_label(c, "reference_assembly"),
                    # Per-field detail (the first is reference_assembly's build, #340)
                    # rides along with the labels: an index record must not describe
                    # its parent less precisely than the parent does.
                    "detail": {fld: field_detail(c, fld) for fld in CLASSIFICATION_FIELDS},
                    "source_file": c.get("file_name"),
                }

    return classifications


def propagate_to_index_files(
    metadata_path: Path,
    classification_paths: list[Path],
    output_path: Path,
):
    """Propagate metadata from parent files to index files."""

    # Load source metadata
    # Records with no usable file_md5sum are excluded here, at the shared load path,
    # so no classification output can name a file the run could never fetch (#376).
    # The load also records what it excluded into the run directory this output lands in.
    source, files = load_classifiable_snapshot(metadata_path, output_path.parent)
    print(f"Loaded {len(files):,} files from metadata")

    # Load classifications
    classifications = load_classifications(*classification_paths)
    print(f"Loaded {len(classifications):,} parent classifications")

    # Group files by dataset for matching
    by_dataset = defaultdict(list)
    for f in files:
        ds = f.get("dataset_id", "unknown")
        by_dataset[ds].append(f)

    # Every file a `(dataset_id, file_name)` names, not just the last one written.
    # A dict keyed that way silently collapses a name two files share, which is what
    # let an index inherit from a parent picked by iteration order (#438); keeping the
    # list makes "this name identifies one file" a thing the match loop can test.
    # Every record here has a well-formed md5 — `load_classifiable_snapshot` excluded
    # the rest (#376) — so a name present here is always resolvable to one.
    files_by_name: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
    for ds, ds_files in by_dataset.items():
        for f in ds_files:
            name = f.get("file_name")
            if name:
                files_by_name[(ds, name)].append(f)

    # Find index files and match to parents
    results = []
    unmatched = []  # Track failed lookups
    stats = defaultdict(
        lambda: {"total": 0, "matched": 0, "unmatched": 0, "ambiguous": 0, "with_modality": 0, "with_ref": 0}
    )
    nc = NOT_CLASSIFIED
    # Labels field_label() returns for a field that is *not* classified. They are
    # statuses, not values, and must be re-emitted as such — a parent in
    # conflict must not become an index file classified as "conflict".
    _sentinels = {NOT_CLASSIFIED, NOT_APPLICABLE, CONFLICT}

    for ds, ds_files in by_dataset.items():
        for f in ds_files:
            name = f.get("file_name", "")
            fmt = f.get("file_format", "")

            # Check if this is an index file
            index_ext = None
            for ext in INDEX_TO_PARENT:
                if fmt == ext or name.endswith(ext):
                    index_ext = ext
                    break

            if not index_ext:
                continue

            stats[index_ext]["total"] += 1

            # The parent is the *first* candidate present, and only that one. Pattern 1
            # (index extension appended to the parent name) is tried before Pattern 2
            # (index extension replacing it), so an earlier candidate is the better
            # reading of the name. Where that candidate names more than one file, this
            # stops rather than trying the next: a later candidate is a worse reading,
            # so falling through would swap one guess for another instead of declining
            # to guess (#438).
            parent_candidates = get_parent_candidates(name, index_ext)
            parent_key = next(((ds, c) for c in parent_candidates if (ds, c) in files_by_name), None)

            if parent_key is None:
                stats[index_ext]["unmatched"] += 1
                unmatched.append(unmatched_entry(f, index_ext, parent_candidates, NO_MATCHING_PARENT))
                continue

            if len(files_by_name[parent_key]) > 1:
                # Not a failed lookup: the parent is present, and present more than once.
                # Listed beside the no-parent case because the outcome is the same — no
                # record here, and the file falls to the catch-all producer — and told
                # apart by `reason`, because the causes are not.
                stats[index_ext]["ambiguous"] += 1
                unmatched.append(
                    unmatched_entry(
                        f,
                        index_ext,
                        parent_candidates,
                        AMBIGUOUS_PARENT,
                        ambiguous_candidate=parent_key[1],
                        files_sharing_that_name=len(files_by_name[parent_key]),
                    )
                )
                continue

            parent_name = parent_key[1]
            parent_md5 = files_by_name[parent_key][0]["file_md5sum"]
            stats[index_ext]["matched"] += 1

            # Get parent classification
            parent_class = classifications.get(parent_md5, {})

            result = {
                "entry_id": f.get("entry_id"),
                "file_name": name,
                "file_format": fmt,
                "file_md5sum": f.get("file_md5sum"),
                "dataset_id": ds,
                "dataset_title": f.get("dataset_title"),
                "parent_file": parent_name,
                "parent_md5sum": parent_md5,
                "data_modality": parent_class.get("data_modality") or nc,
                "data_type": parent_class.get("data_type") or nc,
                "assay_type": parent_class.get("assay_type") or nc,
                "platform": parent_class.get("platform") or nc,
                "reference_assembly": parent_class.get("reference_assembly") or nc,
                "detail": parent_class.get("detail", {}),
                "inheritance_source": "parent_file",
                # The index file's own published values, not the parent's (#424). The
                # repository publishes for 4 index files in this corpus and all four are
                # unmatched here, so today this block is null on every row this producer
                # writes and the catch-all is what carries those four. It is wired anyway
                # because contract 7.7 is about the producer, not about today's corpus:
                # a matched index with a published value would otherwise lose it silently.
                "published": published_from(f, source),
            }

            if result["data_modality"] not in _sentinels:
                stats[index_ext]["with_modality"] += 1
            if result["reference_assembly"] not in _sentinels:
                stats[index_ext]["with_ref"] += 1

            results.append(result)

    # Print stats
    print("\n" + "=" * 70)
    print("INDEX FILE INHERITANCE RESULTS")
    print("=" * 70)

    total_all = 0
    matched_all = 0
    unmatched_all = 0
    ambiguous_all = 0
    modality_all = 0
    ref_all = 0

    for ext in INDEX_TO_PARENT:
        s = stats[ext]
        if s["total"] > 0:
            match_pct = s["matched"] / s["total"] * 100
            unmatch_pct = s["unmatched"] / s["total"] * 100
            amb_pct = s["ambiguous"] / s["total"] * 100
            mod_pct = s["with_modality"] / s["total"] * 100
            ref_pct = s["with_ref"] / s["total"] * 100
            print(f"\n{ext}:")
            print(f"  Total:              {s['total']:>7,}")
            print(f"  Matched to parent:  {s['matched']:>7,} ({match_pct:.1f}%)")
            print(f"  Unmatched:          {s['unmatched']:>7,} ({unmatch_pct:.1f}%)")
            print(f"  Ambiguous parent:   {s['ambiguous']:>7,} ({amb_pct:.1f}%)")
            print(f"  With data_modality: {s['with_modality']:>7,} ({mod_pct:.1f}%)")
            print(f"  With reference:     {s['with_ref']:>7,} ({ref_pct:.1f}%)")

            total_all += s["total"]
            matched_all += s["matched"]
            unmatched_all += s["unmatched"]
            ambiguous_all += s["ambiguous"]
            modality_all += s["with_modality"]
            ref_all += s["with_ref"]

    print(f"\n{'=' * 70}")
    print("TOTAL:")
    print(f"  Index files:        {total_all:>7,}")
    if total_all > 0:
        print(f"  Matched to parent:  {matched_all:>7,} ({matched_all / total_all * 100:.1f}%)")
        print(f"  Unmatched:          {unmatched_all:>7,} ({unmatched_all / total_all * 100:.1f}%)")
        print(f"  Ambiguous parent:   {ambiguous_all:>7,} ({ambiguous_all / total_all * 100:.1f}%)")
        print(f"  With data_modality: {modality_all:>7,} ({modality_all / total_all * 100:.1f}%)")
        print(f"  With reference:     {ref_all:>7,} ({ref_all / total_all * 100:.1f}%)")
    else:
        print("  No index files found")
    print("=" * 70)

    # Print sample of unmatched files for diagnostics
    if unmatched:
        print("\nSample index files with no parent taken (showing up to 10):")
        for u in unmatched[:10]:
            print(f"  {u['file_name']}")
            print(f"    Dataset: {u['dataset_id']}")
            print(f"    Reason: {u['reason']}")
            if u["reason"] == AMBIGUOUS_PARENT:
                print(f"    Ambiguous: {u['ambiguous_candidate']} names {u['files_sharing_that_name']} files")
            else:
                print(f"    Tried: {u['candidates_tried']}")

    # Save results in same format as other classification outputs
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to standard classification format (matching bam_classifications.json / vcf_classifications.json)

    def inherited_evidence(field_name, field_val, parent):
        """Build evidence entry for an inherited classification field.

        Hand-built rather than routed through ``make_claim``, for two reasons.
        These entries carry no tier — an index file has exactly one per dimension
        and never goes through ``evaluate_claims`` — and the status branch can emit
        ``conflict``, which ``make_claim`` rejects as a status no producer may
        author. Both follow from what this is: a copy of the parent's *resolved*
        answer, not a declaration for resolution to weigh. They do carry the
        ``source_type`` every claim carries (#392) — this file's classification was
        inherited from a related file, not determined for it.
        """
        if field_val and field_val not in _sentinels:
            return [
                {
                    "rule_id": "inherited_from_parent",
                    "reason": f"Inherited from parent file: {parent}",
                    "value": field_val,
                    "source_type": SOURCE_DERIVATION_INHERITANCE,
                }
            ]
        status = _inherited_status(field_val)
        # An explicit not_applicable parent isn't "no value" — the field is
        # determined (not applicable). Keep "had no value" for the not_classified /
        # missing case. (generate_coverage_report normalizes both reason forms.)
        if status == NOT_APPLICABLE:
            reason = f"Parent file {parent} marks {field_name} not applicable"
        elif status == CONFLICT:
            reason = f"Parent file {parent} had conflicting evidence for {field_name}"
        else:
            reason = f"Parent file {parent} had no value for {field_name}"
        return [
            {
                "rule_id": "inherited_from_parent",
                "reason": reason,
                "status": status,
                "source_type": SOURCE_DERIVATION_INHERITANCE,
            }
        ]

    def _inherited_status(field_val):
        """Status for an inherited label. ``status_for_value`` knows the two
        sentinels a value can carry; ``conflict`` is a status a label can carry
        that a value never does, so it is mapped here."""
        return CONFLICT if field_val == CONFLICT else status_for_value(field_val)

    standard_results = []
    for r in results:
        parent = r["parent_file"]
        # Field entries share to_output_dict's builder (epic #116): `status`
        # carries the sentinel, `value` is None unless CLASSIFIED (Stage 3).
        classifications = {}
        for fld in CLASSIFICATION_FIELDS:
            label = r.get(fld)
            evidence = inherited_evidence(fld, label, parent)
            status = _inherited_status(label)
            classifications[fld] = build_field_entry(
                None if status == CONFLICT else label, status=status, evidence=evidence, detail=r["detail"].get(fld)
            )
        standard_results.append(
            {
                "file_name": r["file_name"],
                "file_format": r["file_format"],
                "md5sum": r.get("file_md5sum"),
                "file_size": r.get("file_size"),
                "entry_id": r["entry_id"],
                "dataset_id": r["dataset_id"],
                "dataset_title": r["dataset_title"],
                "parent_file": parent,
                "parent_md5sum": r["parent_md5sum"],
                "classifications": classifications,
                # Carried through the reshape, not rebuilt: the intermediate record
                # above already holds the index file's own declaration (#424).
                "published": r["published"],
            }
        )

    with output_path.open("w") as f:
        json.dump(
            {
                "metadata": {
                    "total_index_files": total_all,
                    "matched_to_parent": matched_all,
                    "unmatched": unmatched_all,
                    "ambiguous_parent": ambiguous_all,
                    "with_data_modality": modality_all,
                    "with_reference_assembly": ref_all,
                    "complete": True,
                },
                "classifications": standard_results,
                "unmatched_files": unmatched,
            },
            f,
            indent=2,
        )

    print(
        f"\nSaved {len(standard_results):,} matched index files to {output_path}; "
        f"{unmatched_all:,} had no parent and {ambiguous_all:,} had an ambiguous one, "
        f"both listed in unmatched_files"
    )


def main():
    parser = argparse.ArgumentParser(description="Propagate metadata to index files")
    parser.add_argument(
        "--metadata",
        "-m",
        type=Path,
        default=Path("data/anvil/anvil_files_metadata.json"),
        help="Path to source metadata JSON",
    )
    parser.add_argument(
        "--classifications",
        "-c",
        type=Path,
        nargs="+",
        help="Paths to classification JSON files (BAM, VCF, BED, FASTQ, FASTA, etc.)",
    )
    # Backwards-compatible args (default to standard output paths)
    parser.add_argument(
        "--bam",
        "-b",
        type=Path,
        default=Path("output/anvil/bam_classifications.json"),
        help="Path to BAM classifications (used when --classifications not provided)",
    )
    parser.add_argument(
        "--vcf",
        "-v",
        type=Path,
        default=Path("output/anvil/vcf_classifications.json"),
        help="Path to VCF classifications (used when --classifications not provided)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output/anvil/index_classifications.json"),
        help="Output path for index classifications",
    )
    args = parser.parse_args()

    # Build list of classification paths (deduplicated)
    cls_paths = list(dict.fromkeys(args.classifications)) if args.classifications else [args.bam, args.vcf]

    propagate_to_index_files(
        args.metadata,
        cls_paths,
        args.output,
    )


if __name__ == "__main__":
    main()
