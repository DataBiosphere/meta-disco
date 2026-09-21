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
    python scripts/classify_remaining_files.py --metadata data/anvil/anvil_files_metadata.json
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from meta_disco.metadata_schema import (
    classification_blocking_reasons,
    validation_failed_classifications,
)
from meta_disco.models import FileInfo
from meta_disco.pipeline import RecordKey, load_classifiable_snapshot, record_key
from meta_disco.producers import PRODUCERS
from meta_disco.records import InvalidRecord, OutputRecord, RunMetadata
from meta_disco.rule_engine import RuleEngine


def load_already_classified(classification_paths: list[Path], key: RecordKey) -> set[str]:
    """The identities already carrying a classification record from another producer.

    Keyed on the field the run's source guarantees unique per file
    (``pipeline.RECORD_KEYS``, read from the input envelope by the caller) and never on
    ``file_name``: in the AnVIL corpus a name identifies a file only about 60% of the
    time — 708,088 records under 442,865 distinct names — so a name-keyed set skips a
    file because a *different* file elsewhere shares its name, and that file then
    appears in no ``classifications`` array at all. For AnVIL the key is ``file_id``,
    unique across the corpus and durable across a re-index (#433); for HPRC it is the
    URL hash the source writes as the checksum, because its catalogs issue no
    identifier (#446).

    The name-collision hazard is dormant and this guards it pre-emptively: measured over
    the stored run, no file is silently skipped today. #438's first draft would have
    woken it — declining an ambiguous parent sent 15,006 index files here, 140 of whose
    names are also carried by matched index records in other datasets — but that draft
    was replaced. Those files now get a declined record from ``classify_index_files``
    and never arrive, so keying on identity has no measured effect on this corpus. It
    stays because the collision is real and the next producer to send a colliding name
    here would hit it silently.
    """
    field = key.output_field
    seen = set()
    for path in classification_paths:
        if not path.is_file():
            continue
        with path.open() as f:
            data = json.load(f)
        for r in data.get("classifications", data.get("results", [])):
            value = r.get(field)
            # Raise rather than skip. The catalog identity is deliberately *not*
            # classifier-relevant (`records.ClassifierRecord`), so a drifted one still
            # reaches the valid stream and is echoed into a producer's output untouched —
            # unlike `file_name`, the key this replaced, which the contract guarantees
            # non-empty. Skipping such a row would drop it from this set and hand the
            # file a *second* classification record, inflating coverage and making
            # `corpus_diff` report a phantom gain. `make validate-metadata` rejects a
            # null `file_id` before `make classify`, and the shared load excludes an HPRC
            # record with no URL hash (#376), so reaching here means a producer wrote a
            # row neither gate would have let through.
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"{path}: classification row for {r.get('file_name')!r} has {field} "
                    f"{value!r}; this producer keys on it and cannot skip a row without "
                    f"risking a duplicate record. Either the input carried a drifted "
                    f"{key.input_field} — `make validate-metadata` rejects that — or the "
                    f"producer that wrote this file omitted the field and needs re-running."
                )
            seen.add(value)
    return seen


def classify_remaining(metadata_path: Path, output_path: Path, classification_paths: list[Path]):
    """Classify files not handled by other classifiers."""

    # Records with no usable file_md5sum are excluded here, at the shared load path,
    # so no classification output can name a file the run could never fetch (#376).
    # The load also records what it excluded into the run directory this output lands in.
    snapshot = load_classifiable_snapshot(metadata_path, output_path.parent)
    source, files = snapshot.source, snapshot.records
    print(f"Loaded {len(files):,} files from metadata")

    # Which field identifies a file is the source's to say (pipeline.RECORD_KEYS); an
    # envelope that names no repository is refused here, naming the file.
    key = record_key(snapshot.metadata, metadata_path)
    already = load_already_classified(classification_paths, key)
    print(f"Already classified by other scripts: {len(already):,}")

    engine = RuleEngine()
    results = []
    ext_counts = Counter()
    validation_failed = 0

    for rec in files:
        name = rec.get("file_name", "")
        identity = rec.get(key.input_field)
        # The same guard `load_already_classified` applies to the other side of this
        # comparison. A drifted key here would match nothing in `already`, so an
        # already-classified file would be classified a second time — the failure the
        # key change was made to prevent, entering by the input rather than the output.
        if not isinstance(identity, str) or not identity:
            raise ValueError(
                f"input record for {name!r} has {key.input_field} {identity!r}; this producer "
                f"keys on it to know what another producer already classified. "
                f"`make validate-metadata` rejects this before `make classify` runs."
            )
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
            results.append(
                OutputRecord.from_work_item(item, validation_failed_classifications(item.reasons), source).to_dict()
            )
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
        results.append(OutputRecord.from_record(rec, result.to_output_dict(), source).to_dict())

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
        default=Path("data/anvil/anvil_files_metadata.json"),
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
