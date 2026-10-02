#!/usr/bin/env python3
"""Classify index files, and name each one's parent.

An index file's ``data_type`` is ``index``, from its extension. The dimensions
``IndexActivity`` passes (``INHERITED_FIELDS``, from ``rules/activities.yaml``) describe
the data it points into, so they are its parent's to say. This producer finds the parent
by filename within a dataset and writes the edge to it as the record's ``generated_by``;
the reconcile stage carries the parent's settled answer across it (contract 4.9, #571).
Here those dimensions are ``not_classified``. ``INDEX_TO_PARENT`` declares which index
extensions have which parent extensions.

It reads no other producer's rows: until #571 it copied the parent's answer from them
(#413), which could see neither a parent's reconciled answer nor a parent only the
catch-all writes.

A filename does not always identify one file. Names are compared case-insensitively,
as routing compares extensions (#449), so two files in a dataset whose names differ
only by case identify neither (#455). Where two files in a dataset share — up to case —
the name an index points at, no parent is chosen. Such a file still gets a record,
with no edge: ``declined_record`` gives it ``data_type: index``, which the extension
establishes without a parent, and ``not_classified`` on the others, which only a parent
could supply. Why no parent was taken is listed separately in ``unmatched_files``, with
reason ``AMBIGUOUS_PARENT`` or ``NO_MATCHING_PARENT`` (#438). So this module has two
behaviours, and they differ only in the edge: with a unique parent the record names it,
without one it names none. The slots are the same either way (#437).

The lookup used to keep whichever file load order visited last. Measured on the
anvil15 corpus, 15,006 index files took a parent picked that way, and 7,422 of
them were wrong about their reference assembly — verified against the storage
paths in the manifest's ``file_inventory`` table, which name the true parent.
``ANVIL_T2T_CHRY`` is why: it calls one sample against both CHM13v2 and GRCh38
and stores the outputs under the same filename in different directories.

Telling such files apart needs a path or a declared parent-child relationship,
and this producer can see neither — the compact manifest it reads carries no
storage path and no sibling relation. So it declines rather than guesses. The source
tables' lineage does better at reconcile: ``anvil_activity`` names one parent for every
``ANVIL_T2T_CHRY`` index declined here, measured on anvil15 (#571).
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from meta_disco import activities, code_rules, edges
from meta_disco.deployments import PROD
from meta_disco.models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    NOT_CLASSIFIED,
    SOURCE_FILENAME_RULE,
    build_field_entry,
)
from meta_disco.pipeline import (
    load_classifiable_records,
    load_envelope,
    record_key,
    repeated_key_values,
)
from meta_disco.producers import INDEX_TO_PARENT, PRODUCERS
from meta_disco.records import OutputRecord, RunMetadata, coerce_identity, identity_from
from meta_disco.rule_engine import make_claim
from meta_disco.rule_loader import get_unified_rules

# Why an index file took no parent, as the markers `code_rules` declares. Written into
# each `unmatched_files` entry and read back by this module's diagnostics and its tests.
NO_MATCHING_PARENT = code_rules.NO_MATCHING_PARENT.id
AMBIGUOUS_PARENT = code_rules.AMBIGUOUS_PARENT.id

# Routes through the shared predicate — see meta_disco.producers, which declares this
# producer's extensions as the keys of `INDEX_TO_PARENT`, so what it routes on and what
# it inherits from cannot drift apart.
INDEX = PRODUCERS["index"]


def get_parent_candidates(index_name: str, index_ext: str) -> list[str]:
    """Get possible parent filenames for an index file.

    Handles both patterns:
    - sample.bam.bai -> sample.bam (Pattern 1: index appended to parent)
    - sample.bai -> sample.bam (Pattern 2: index replaces parent ext)

    Extensions are matched case-insensitively, as routing matches them, so a
    ``SAMPLE.BAM.BAI`` that reaches this producer can find its parent instead of being
    declined for a missing one. A candidate keeps whatever casing it was built with —
    Pattern 1 the name's own, Pattern 2 the name's stem plus a lowercase extension from
    ``INDEX_TO_PARENT``, which is therefore a spelling no file need carry. So a candidate
    is a lookup probe and not a filename: the caller matches it against a case-folded name
    index and reads the real name off the file it finds (#455).
    """
    candidates = []
    # Folded here, not just at the comparisons below: `INDEX_TO_PARENT` is keyed in
    # lowercase, so an unfolded `index_ext` would find no parent extensions at all.
    index_ext = index_ext.lower()
    parent_exts = INDEX_TO_PARENT.get(index_ext, [])

    if index_name.lower().endswith(index_ext):
        base = index_name[: -len(index_ext)]

        # Pattern 1: index ext appended to parent (sample.bam.bai -> sample.bam)
        # This is the most common pattern
        pattern1_matched = False
        for parent_ext in parent_exts:
            if base.lower().endswith(parent_ext):
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
    ``dataset_id`` is defaulted the same way the grouping key is, so an entry names the
    bucket its file was matched in rather than a different spelling of absent.
    """
    return {
        "file_name": coerce_identity(record.get("file_name")),
        "file_format": coerce_identity(record.get("file_format")),
        "file_md5sum": coerce_identity(record.get("file_md5sum")),
        **identity_from(record, coerce=True),
        "dataset_id": record.get("dataset_id", "unknown"),
        "dataset_title": coerce_identity(record.get("dataset_title")),
        "index_extension": index_ext,
        "candidates_tried": candidates,
        "reason": reason,
        **extra,
    }


DATA_TYPE = "data_type"
# The dimensions an index file takes from its parent: every one but its own kind, as
# `IndexActivity` declares them (`rules/activities.yaml`, #580).
INHERITED_FIELDS = activities.passes(activities.INDEXING)
INDEX_DATA_TYPE = "index"  # a term in `data_type_enum`, and what an index file is
# The tier of `index_file`, the extension-scope rule whose claim this producer makes for the
# files it owns (#437): read from the rule set rather than restated, so the two cannot drift.
INDEX_FILE_RULE = "index_file"
INDEX_FILE_TIER = next((rule.tier for rule in get_unified_rules().rules if rule.id == INDEX_FILE_RULE), None)
if INDEX_FILE_TIER is None:
    raise ImportError(f"rules/unified_rules.yaml declares no {INDEX_FILE_RULE!r} rule, whose tier an index claim takes")

# Written verbatim into a declined record's evidence, so it is read by someone deciding
# what to do about the file. Both say "carries", matched case-insensitively (#455): two
# files can be ambiguous here without carrying the same name literally, and a reason that
# sent a reader looking for two identical names would misdescribe the cause — the defect
# this producer's own `no_matching_parent_in_dataset` had before #455.
DECLINED_REASON_TEXT = {
    NO_MATCHING_PARENT: "no file in this dataset carries a candidate parent name, matched case-insensitively",
    AMBIGUOUS_PARENT: "more than one file in this dataset carries that parent name, matched case-insensitively",
}


def index_data_type_entry(index_ext: str) -> dict:
    """The ``data_type`` entry every index file carries, matched or not.

    An index file *is* an index. That is knowable from the extension without a parent,
    which is how this producer finds the file in the first place, and ``index`` is a
    term in ``data_type_enum``. Claimed through ``make_claim`` the way the ``index_file``
    rule would claim it: ``SOURCE_FILENAME_RULE`` (``rule_engine._RULE_SOURCE_TYPES``) at
    that rule's tier.

    Before #437 a *matched* index inherited this dimension with the rest, so a ``.crai``
    reported ``alignments`` and a ``.tbi`` reported ``variants.germline`` — the parent's kind
    copied onto a file that is not of that kind. The other dimensions inherit
    honestly, because they describe the data the index points into; ``data_type``
    describes the file itself, and is the one that must not be borrowed.

    Nothing is lost by dropping the borrowed value. What a matched file indexes is on
    the record as ``generated_by`` — the activity, the parent's name and its record key,
    which joins to its record — more than a copied category said. A declined row carries
    no edge (ADR-0002 decision 2), and never had a borrowed ``data_type`` to lose: it has
    no parent, which is what declined means.
    """
    return build_field_entry(
        INDEX_DATA_TYPE,
        status=CLASSIFIED,
        evidence=[
            make_claim(
                source_type=SOURCE_FILENAME_RULE,
                rule_id=code_rules.INDEX_BY_EXTENSION.id,
                reason=f"{index_ext} identifies an index file",
                value=INDEX_DATA_TYPE,
                tier=INDEX_FILE_TIER,
            )
        ],
    )


def declined_record(record: dict, index_ext: str, reason: str) -> dict:
    """One output record for an index file this producer took no parent for.

    Says the one thing that is known and declines the rest, which are not. The extension
    identifies the file as an index without any parent — it is how this producer found
    it — so ``data_type`` is ``index``, claimed the way an ``extension``-scope rule
    would claim it (``SOURCE_FILENAME_RULE``, per ``rule_engine._RULE_SOURCE_TYPES``).
    The other dimensions are properties of the data the index points into, which
    only the parent can supply, so they are ``not_classified``: they *apply*, and
    nothing here can determine them. ``not_applicable`` would assert they cannot apply,
    which the matched case disproves by filling them in.

    Each of those dimensions carries a note, not a claim: a marker's ``rule_id`` and the
    reason, declaring nothing, as a fetch failure's note does (#413). The markers name no
    rule in ``unified_rules.yaml``: they are declared in ``code_rules`` (#572), which
    ``tests/test_code_rules.py`` holds this producer to.

    Writing this record is what keeps such a file out of the catch-all producer. When
    #438 added it, that mattered because the catch-all's rule then stamped four
    dimensions ``not_applicable`` — ``data_type`` among them — on the strength of the
    extension alone, and coverage counts ``not_applicable`` as classified, so a file
    was reported as determined precisely where it is not.

    #437 removed that hazard at the source: the rule is now ``index_file`` and claims
    only ``data_type: index``, leaving the dimensions a parent supplies open. It is the
    engine's backstop for an index this producer misses; it fires on nothing today
    because this producer misses nothing, and that is why it stays (#430). So the three
    ways an index file can be classified — inherited from a matched parent, declined
    here, or reached by the rule — now agree on its kind and never deny a dimension
    that applies. The record is still written, because it carries what this producer
    knows about the file and keeps every index file in one output.
    """
    why = DECLINED_REASON_TEXT[reason]
    classifications = {DATA_TYPE: index_data_type_entry(index_ext)}
    for fld in INHERITED_FIELDS:
        classifications[fld] = build_field_entry(
            None,
            status=NOT_CLASSIFIED,
            evidence=[{"rule_id": reason, "reason": f"No parent to inherit {fld} from: {why}"}],
        )
    # No edge: an edge exists only where the parent resolves (`meta_disco.edges`). The
    # names this index points at are worked out from its own, so an unresolved edge
    # would restate the file.
    return OutputRecord.from_record(record, every_field(classifications)).to_dict()


def every_field(classifications: dict[str, dict]) -> dict[str, dict]:
    """Every slot, in field order; one ``IndexActivity`` does not pass is ``not_classified`` (#580)."""
    return {
        fld: classifications.get(fld) or build_field_entry(None, status=NOT_CLASSIFIED) for fld in CLASSIFICATION_FIELDS
    }


def propagate_to_index_files(metadata_path: Path, output_path: Path):
    """Write one record per index file: its kind, and the edge to its parent where one name resolves.

    The parent's answer is not read: reconcile carries it across the edge (#571).
    """

    # Before the load: an envelope naming no repository is refused without parsing the
    # corpus or writing anything into the run directory, as the catch-all producer does.
    key = record_key(load_envelope(metadata_path), metadata_path)

    # Load source metadata
    # Records with no usable file_md5sum are excluded here, at the shared load path,
    # so no classification output can name a file the run could never fetch (#376).
    # The load also records what it excluded into the run directory this output lands in.
    files = load_classifiable_records(metadata_path, output_path.parent)
    print(f"Loaded {len(files):,} files from metadata")

    # A key two input records share would ground an edge on whichever record carries it:
    # the edge's `parent_key` would name two files. Refused here, as the catch-all refuses
    # it, for a run started outside `make classify`; `make validate-metadata` reports it
    # before one.
    repeated = repeated_key_values(files, key)
    if repeated:
        examples = ", ".join(f"{value} (x{n})" for value, n in sorted(repeated.items())[:10])
        raise ValueError(
            f"{metadata_path}: {len(repeated):,} value(s) of {key.input_field} are carried by more "
            f"than one input record, but this producer grounds a parent on it as unique per file: {examples}"
        )

    # Group files by dataset for matching
    by_dataset = defaultdict(list)
    for f in files:
        ds = f.get("dataset_id", "unknown")
        by_dataset[ds].append(f)

    # Every file a `(dataset_id, file_name)` names, case-folded, not just the last one
    # written: `edges.files_by_folded_name` says why. Every *record* here has a
    # well-formed md5 — `load_classifiable_records` excluded the rest (#376) — which says
    # nothing about names: a name reaching more than one record is the case this exists
    # to detect. A drifted non-string name on a record this producer owns still raises
    # below, as the three sibling filename producers do via `FileInfo.from_filename`,
    # which is what lets `OutputRecord.from_record` promise no producer hands it one.
    files_by_folded_name = edges.files_by_folded_name(files)

    # Find index files and match to parents
    matched: list[tuple[dict, str, dict]] = []
    unmatched = []  # Track failed lookups
    # Index files this producer took no parent for. They still get a record — the
    # extension says what they are, even when nothing says what they are of (#438).
    declined: list[tuple[dict, str, str]] = []
    stats = defaultdict(lambda: {"total": 0, "matched": 0, "unmatched": 0, "ambiguous": 0})

    for ds, ds_files in by_dataset.items():
        for f in ds_files:
            index_ext = INDEX.claim(f)
            if index_ext is None:
                continue
            name = f.get("file_name", "")

            stats[index_ext]["total"] += 1

            # The parent is the *first* candidate present, and only that one. Where that
            # candidate names more than one file, this stops rather than trying the next,
            # because a later candidate is a different guess and not a better one —
            # falling through would swap one guess for another instead of declining to
            # guess (#438).
            #
            # `get_parent_candidates` orders Pattern 1 (index extension appended to the
            # parent name) before Pattern 2 (index extension replacing it), and within
            # Pattern 2 by `INDEX_TO_PARENT` declaration order, which asserts no
            # preference. So "first" is well defined but only Pattern-1-over-Pattern-2 is
            # a reasoned ranking. On the anvil15 corpus the rule has no observable effect:
            # every ambiguous decline hits a Pattern-1 candidate, and in no case would
            # falling through have found a unique later one. It is here for the shape of
            # the decision, not for a measured save.
            parent_candidates = get_parent_candidates(name, index_ext)
            candidate_tried, parent_files = next(
                ((c, found) for c in parent_candidates if (found := edges.matches(files_by_folded_name, ds, c))),
                (None, []),
            )

            if candidate_tried is None:
                stats[index_ext]["unmatched"] += 1
                unmatched.append(unmatched_entry(f, index_ext, parent_candidates, NO_MATCHING_PARENT))
                declined.append((f, index_ext, NO_MATCHING_PARENT))
                continue

            if len(parent_files) > 1:
                # Not a failed lookup: the parent is present, and present more than once.
                # Listed beside the no-parent case because the outcome is the same — no
                # parent taken, so `declined_record` writes what is known without one —
                # and told apart by `reason`, because the causes are not the same.
                #
                # Under a folded key the two files need not share a name literally, only
                # up to case (#455), and the reason cannot say which. `parent_names_matched`
                # is what does: one name means a true duplicate, several mean case was the
                # difference. Echoed through `coerce_identity`, as every other name in the
                # entry is. `ambiguous_candidate` is the candidate as tried rather than the
                # folded key, which is a lookup key and not a filename at all.
                stats[index_ext]["ambiguous"] += 1
                unmatched.append(
                    unmatched_entry(
                        f,
                        index_ext,
                        parent_candidates,
                        AMBIGUOUS_PARENT,
                        ambiguous_candidate=candidate_tried,
                        files_sharing_that_name=len(parent_files),
                        parent_names_matched=sorted({coerce_identity(p.get("file_name")) for p in parent_files}),
                    )
                )
                declined.append((f, index_ext, AMBIGUOUS_PARENT))
                continue

            # The matched file itself, not the candidate that found it: its own name
            # reaches the edge, which names the file as the catalog spells it (#455).
            stats[index_ext]["matched"] += 1
            matched.append((f, index_ext, parent_files[0]))

    # Print stats
    print("\n" + "=" * 70)
    print("INDEX FILE PARENTS")
    print("=" * 70)

    total_all = 0
    matched_all = 0
    unmatched_all = 0
    ambiguous_all = 0

    for ext in INDEX_TO_PARENT:
        s = stats[ext]
        if s["total"] > 0:
            match_pct = s["matched"] / s["total"] * 100
            unmatch_pct = s["unmatched"] / s["total"] * 100
            amb_pct = s["ambiguous"] / s["total"] * 100
            print(f"\n{ext}:")
            print(f"  Total:              {s['total']:>7,}")
            print(f"  Matched to parent:  {s['matched']:>7,} ({match_pct:.1f}%)")
            print(f"  Unmatched:          {s['unmatched']:>7,} ({unmatch_pct:.1f}%)")
            print(f"  Ambiguous parent:   {s['ambiguous']:>7,} ({amb_pct:.1f}%)")

            total_all += s["total"]
            matched_all += s["matched"]
            unmatched_all += s["unmatched"]
            ambiguous_all += s["ambiguous"]

    print(f"\n{'=' * 70}")
    print("TOTAL:")
    print(f"  Index files:        {total_all:>7,}")
    if total_all > 0:
        print(f"  Matched to parent:  {matched_all:>7,} ({matched_all / total_all * 100:.1f}%)")
        print(f"  Unmatched:          {unmatched_all:>7,} ({unmatched_all / total_all * 100:.1f}%)")
        print(f"  Ambiguous parent:   {ambiguous_all:>7,} ({ambiguous_all / total_all * 100:.1f}%)")
    else:
        print("  No index files found")
    print("=" * 70)

    # Print sample of unmatched files for diagnostics
    if unmatched:
        # Sampled per reason, not off the head of the list. One reason outnumbers the
        # other by orders of magnitude, so a flat head would let dataset iteration order
        # decide whether a true orphan is ever seen — and this section exists for those.
        sample = [
            u
            for reason in (NO_MATCHING_PARENT, AMBIGUOUS_PARENT)
            for u in [x for x in unmatched if x["reason"] == reason][:5]
        ]
        print("\nSample index files with no parent taken (up to 5 per reason):")
        for u in sample:
            print(f"  {u['file_name']}")
            print(f"    Dataset: {u['dataset_id']}")
            print(f"    Reason: {u['reason']}")
            if u["reason"] == AMBIGUOUS_PARENT:
                # The matched spellings, not just the probe: the probe is a Pattern 2
                # construction that no file need carry, and naming the real ones is what
                # tells an operator a case collision from a true duplicate (#455).
                print(
                    f"    Ambiguous: {u['ambiguous_candidate']} matched "
                    f"{u['files_sharing_that_name']} files: {', '.join(u['parent_names_matched'])}"
                )
            else:
                print(f"    Tried: {u['candidates_tried']}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    standard_results = []
    for record, index_ext, parent in matched:
        # `data_type` is the file's own kind (#437); the dimensions `IndexActivity` passes
        # are `not_classified` here and filled at reconcile across the edge (#571). The
        # index file's own identity, not the parent's (#433): this row resolves to this
        # file's bytes, and the parent is the edge's grounding.
        standard_results.append(
            OutputRecord.from_record(
                record,
                every_field({DATA_TYPE: index_data_type_entry(index_ext)}),
                generated_by=edges.generated_by(code_rules.INDEX_BY_NAME, parent, key),
            ).to_dict()
        )

    for rec, index_ext, reason in declined:
        standard_results.append(declined_record(rec, index_ext, reason))

    with output_path.open("w") as f:
        json.dump(
            {
                "metadata": RunMetadata.from_counts(
                    total=total_all,
                    successful=len(standard_results),
                    from_cache=0,
                    content_unreadable=0,
                    details={
                        "matched_to_parent": matched_all,
                        "unmatched": unmatched_all,
                        "ambiguous_parent": ambiguous_all,
                    },
                ).to_dict(),
                "classifications": standard_results,
                "unmatched_files": unmatched,
            },
            f,
            indent=2,
        )

    print(
        f"\nSaved {len(standard_results):,} index file records to {output_path}: "
        f"{matched_all:,} name their parent; {unmatched_all:,} found none and "
        f"{ambiguous_all:,} found more than one, so those {unmatched_all + ambiguous_all:,} "
        f"carry `index` and no edge, and are listed in unmatched_files with why"
    )


def main():
    parser = argparse.ArgumentParser(description="Classify index files and name each one's parent")
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
        default=Path("output/anvil") / INDEX.output,
        help="Output path for index classifications",
    )
    args = parser.parse_args()
    propagate_to_index_files(args.metadata, args.output)


if __name__ == "__main__":
    main()
