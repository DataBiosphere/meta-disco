#!/usr/bin/env python3
"""Classify files no other producer wrote a row for.

The catch-all: the one producer claiming nothing by extension. It takes whatever the
other ten left and runs it through the rule engine. Most files get not_classified on
every dimension, which is the point — it makes them visible in coverage reports rather
than absent from the output.

It keys on the rows other producers actually wrote, not on the routing predicate, which
is the stricter of the two: a producer that claimed a file and wrote no row for it leaves
the file here, where asking the predicate would drop it from the run entirely.

Usage:
    python scripts/classify_remaining_files.py
    python scripts/classify_remaining_files.py --metadata data/anvil/prod/anvil_files_metadata.json
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from meta_disco.deployments import PROD
from meta_disco.metadata_schema import (
    classification_blocking_reasons,
    validation_failed_classifications,
)
from meta_disco.models import FileInfo
from meta_disco.pipeline import (
    RecordKey,
    input_key_value,
    keyed_rows,
    load_classifiable_records,
    load_envelope,
    record_key,
    repeated_key_values,
)
from meta_disco.producers import PRODUCERS
from meta_disco.records import InvalidRecord, OutputRecord, RunMetadata
from meta_disco.rule_engine import RuleEngine


def load_already_classified(classification_paths: list[Path], key: RecordKey) -> set[str]:
    """The identities already carrying a classification record from another producer.

    Keyed on the source's record key (``pipeline.SOURCE_RECORD_KEYS``, which says which
    field and why), never on ``file_name``: a name identifies a file only about 60% of
    the time in the AnVIL corpus, so a name-keyed set skips a file because a *different*
    file elsewhere shares its name, and that file then appears in no ``classifications``
    array at all.

    The name-collision hazard is dormant and this guards it pre-emptively: measured over
    the stored run, no file is silently skipped today. #438's first draft would have
    woken it — declining an ambiguous parent sent 15,006 index files here, 140 of whose
    names are also carried by matched index records in other datasets — but that draft
    was replaced. Those files now get a declined record from ``classify_index_files``
    and never arrive, so keying on identity has no measured effect on this corpus. It
    stays because the collision is real and the next producer to send a colliding name
    here would hit it silently.
    """
    # `keyed_rows` raises on a row without the key rather than skipping it: skipped, the
    # row would drop from this set and hand the file a *second* classification record,
    # inflating coverage and making `corpus_diff` report a phantom gain.
    return {value for value, _ in keyed_rows(classification_paths, key)}


def classify_remaining(metadata_path: Path, output_path: Path, classification_paths: list[Path]):
    """Classify files not handled by other classifiers."""

    # Before the load: an envelope naming no repository is refused without parsing the
    # corpus or writing anything into the run directory.
    key = record_key(load_envelope(metadata_path), metadata_path)

    # Records with no usable file_md5sum are excluded here, at the shared load path,
    # so no classification output can name a file the run could never fetch (#376).
    # The load also records what it excluded into the run directory this output lands in.
    files = load_classifiable_records(metadata_path, output_path.parent)
    print(f"Loaded {len(files):,} files from metadata")

    # A key two input records share would let one hide behind the other: the earlier
    # producer writes one, this loop skips both as already classified, and the post-run
    # scan sees one row and passes. `make validate-metadata` reports this before
    # `make classify`; a run started any other way is refused here, before a row is
    # written, rather than dropping a file and reporting success.
    repeated = repeated_key_values(files, key)
    if repeated:
        examples = ", ".join(f"{value} (x{n})" for value, n in sorted(repeated.items())[:10])
        raise ValueError(
            f"{metadata_path}: {len(repeated):,} value(s) of {key.input_field} are carried by more "
            f"than one input record, but this producer keys on it as unique per file and would "
            f"skip a file another producer had not written: {examples}"
        )

    already = load_already_classified(classification_paths, key)
    print(f"Already classified by other scripts: {len(already):,}")

    engine = RuleEngine()
    results = []
    ext_counts = Counter()
    validation_failed = 0

    for rec in files:
        name = rec.get("file_name", "")
        # The same guard `load_already_classified` applies to the other side of this
        # comparison. A drifted key here would match nothing in `already`, so an
        # already-classified file would be classified a second time — the failure the
        # key change was made to prevent, entering by the input rather than the output.
        identity = input_key_value(rec, key, "know what another producer already classified")
        if identity in already:
            continue
        if not name:
            # A record with no file_name violates the input contract, and is written as
            # a validation_failed row exactly as the pipeline writes one (#161): a
            # missing row is indistinguishable from a file that was never seen (#155),
            # and `unprocessable-report` finds such a file by scanning the output.
            # Checked after `already`, or a nameless record another producer claimed on
            # its `file_format` would be written twice.
            validation_failed += 1
            # The pipeline's own path, not an imitation of it: `InvalidRecord` coerces a
            # drifted identity (a null or non-string `file_name`) that `from_record`
            # would echo as-is into a row typed `str`.
            item = InvalidRecord.from_record(rec, classification_blocking_reasons(rec))
            results.append(OutputRecord.from_work_item(item, validation_failed_classifications(item.reasons)).to_dict())
            continue

        file_info = FileInfo.from_filename(
            name,
            file_size=rec.get("file_size"),
            dataset_title=rec.get("dataset_title", ""),
        )
        result = engine.classify_extended(file_info)

        # Leading dot, so a key here reads like the extensions the other producers count
        # by rather than a bare `txt` beside their `.png` — the metadata blocks are one
        # shape now, which invites merging them. It is not their vocabulary: this is the
        # last dot-token of a name no producer claimed, so `x.gff.gz` counts as `.gz`.
        token = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        ext = f".{token}" if token else "(none)"
        ext_counts[ext] += 1

        # One record shape for every producer (#450).
        results.append(OutputRecord.from_record(rec, result.to_output_dict()).to_dict())

    print(f"\nClassified {len(results):,} remaining files")
    print("\nBy extension:")
    for ext, count in ext_counts.most_common(20):
        print(f"  {ext}: {count:,}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as out:
        json.dump(
            {
                "metadata": RunMetadata.from_counts(
                    total=len(results),
                    successful=len(results) - validation_failed,
                    validation_failed=validation_failed,
                    from_cache=0,
                    content_unreadable=0,
                    details={"by_extension": dict(ext_counts.most_common())},
                ).to_dict(),
                "classifications": results,
            },
            out,
            indent=2,
        )

    print(f"\nSaved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Classify files not handled by other classifiers")
    parser.add_argument(
        "--metadata",
        "-m",
        type=Path,
        default=PROD.input_file,
        help="Path to source metadata JSON",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output/anvil") / PRODUCERS["remaining"].output,
        help="Output path for classifications",
    )
    parser.add_argument(
        "--classifications",
        "-c",
        type=Path,
        nargs="+",
        default=None,
        help="Classification files from other scripts (to exclude already-classified files)",
    )
    args = parser.parse_args()

    classify_remaining(args.metadata, args.output, args.classifications or [])


if __name__ == "__main__":
    main()
