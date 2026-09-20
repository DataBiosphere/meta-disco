#!/usr/bin/env python3
"""Propagate metadata from parent files to index files.

An index file's ``data_type`` is ``index``, from its extension. The other four of
``CLASSIFICATION_FIELDS`` describe the data it points into, so they are inherited from
its parent, found by filename within a dataset. ``INDEX_TO_PARENT`` declares which
index extensions have which parent extensions.

A filename does not always identify one file. Names are compared case-insensitively,
as routing compares extensions (#449), so two files in a dataset whose names differ
only by case identify neither (#455). Where two files in a dataset share — up to case —
the name an index points at, no parent is chosen. Such a file still gets a record,
but it inherits nothing: ``declined_record`` gives it ``data_type: index``, which the
extension establishes without a parent, and ``not_classified`` on the other four,
which only a parent could supply. Why no parent was taken is listed separately in
``unmatched_files``, with reason ``AMBIGUOUS_PARENT`` or ``NO_MATCHING_PARENT``
(#438). So this module has two behaviours, and they differ only in the four inherited
dimensions: with a unique parent they are the parent's, without one they are
``not_classified``. ``data_type`` is the same either way (#437).

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
import functools
import json
from collections import defaultdict
from pathlib import Path

from meta_disco.file_name import EXTENSION_MAP, FileName
from meta_disco.models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    CONFLICT,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_DERIVATION_INHERITANCE,
    SOURCE_FILENAME_RULE,
    build_field_entry,
    field_detail,
    field_label,
    status_for_value,
)
from meta_disco.pipeline import load_classifiable_snapshot
from meta_disco.producers import INDEX_TO_PARENT, PRODUCERS
from meta_disco.records import OutputRecord, RunMetadata, coerce_identity, identity_from

# Why an index file took no parent. Written into each `unmatched_files` entry and
# read back by this module's diagnostics and its tests, so it is named rather than
# spelled three times.
NO_MATCHING_PARENT = "no_matching_parent_in_dataset"
AMBIGUOUS_PARENT = "ambiguous_parent_in_dataset"

# Routes through the shared predicate — see meta_disco.producers, which declares this
# producer's extensions as the keys of `INDEX_TO_PARENT`, so what it routes on and what
# it inherits from cannot drift apart.
INDEX = PRODUCERS["index"]


# An extension category (``file_name.EXTENSION_MAP``) to the derivation model's
# ``parent_kind_enum``: the two vocabularies overlap but are not the same words. A
# category with no enum member is deliberately absent, so it yields a null
# ``parent_kind`` — we cannot tell, rather than a guessed kind.
_PARENT_KIND_BY_CATEGORY = {
    "alignment": "alignment",
    "variant": "variants",
    "reads": "reads",
    "sequence": "sequence",
    "intervals": "intervals",
    "signal": "signal",
    "genotype_plink": "genotypes",
    "single_cell_matrix": "expression_matrix",
}


def parent_kind_of(parent_name: str | None, index_ext: str) -> str | None:
    """What kind of file this index points at, or None when that cannot be told.

    The matched parent's own extension answers it where there is one — or leaves it
    None, for a parent whose category has no ``parent_kind`` term. Without a parent it
    falls back to the type-level answer — what the extensions ``INDEX_TO_PARENT``
    declares for this index agree on, if they agree — which is the data model's claim
    that you need not find the parent to know a ``.bai`` indexes an alignment
    (docs/derived-file-data-model.md 4a). A ``.tbi`` indexes several kinds, so only a
    match resolves it and the fallback gives None.
    """
    if not parent_name:
        return _declared_kind(index_ext)
    return _agreed_kind([parent_name])


@functools.cache
def _declared_kind(index_ext: str) -> str | None:
    """The kind every parent ``INDEX_TO_PARENT`` declares for this index agrees on.

    Cached: this is a pure function of the seven index extensions, and the declined path
    asks it once per record.
    """
    return _agreed_kind(INDEX_TO_PARENT.get(index_ext, []))


def _agreed_kind(names: list[str]) -> str | None:
    """The one kind these names agree on, or None.

    A `None` stays in the set rather than being discarded, so a name this cannot map is
    one that disagrees: `{variants, None}` is ambiguous, not `variants`. A lone `None`
    pops as `None`, which is the same answer either way.
    """
    kinds = {_PARENT_KIND_BY_CATEGORY.get(_category_of(name) or "") for name in names}
    return kinds.pop() if len(kinds) == 1 else None


def _category_of(file_name: str) -> str | None:
    """The extension category of one filename, trying shorter suffixes of a compound one.

    ``FileName.parse`` keeps a compound core whole — a gVCF is ``.g.vcf`` — and
    ``EXTENSION_MAP`` keys the simple form, so an exact lookup misses every gVCF parent
    and calls it a kind we cannot tell. Dropping leading segments finds ``.vcf``.

    The map is the rules vocabulary and is deliberately not edited to suit this: adding
    a key there would move what the rules match on, and the kind of a parent is this
    producer's question.
    """
    parsed = FileName.parse(file_name).extension or ""
    segments = parsed.split(".")
    for start in range(1, len(segments)):
        category = EXTENSION_MAP.get("." + ".".join(segments[start:]))
        if category:
            return category
    return None


def derivation_edge(parent_name: str | None, parent_md5sum: str | None, index_ext: str) -> dict:
    """The typed derivation edge for one index file (#450, data model 4a).

    ``relation`` is always ``index_of``: this producer classifies index files, and the
    schema requires the verb, so there is no half-edge to emit. The grounding —
    ``parent_file`` and ``parent_md5sum`` — is null where no parent was taken (#438),
    which is the ungrounded edge ``parent_md5sum``'s own schema description anticipates:
    the *type* of the link is known from the extension even when the parent is not.
    """
    return {
        "relation": INDEX_RELATION,
        "parent_md5sum": parent_md5sum,
        "parent_file": parent_name,
        "parent_kind": parent_kind_of(parent_name, index_ext),
    }


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
INDEX_DATA_TYPE = "index"  # a term in `data_type_enum`, and what an index file is
# The derivation verb this producer emits, a term in `relation_enum`. Pinned to the
# schema by `test_rule_vocabulary`, as `INDEX_DATA_TYPE` is.
INDEX_RELATION = "index_of"

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
    term in ``data_type_enum``. Claimed the way an ``extension``-scope rule would claim
    it (``SOURCE_FILENAME_RULE``, per ``rule_engine._RULE_SOURCE_TYPES``).

    Before #437 a *matched* index inherited this dimension with the rest, so a ``.crai``
    reported ``alignments`` and a ``.tbi`` reported ``variants.germline`` — the parent's kind
    copied onto a file that is not of that kind. The other four dimensions inherit
    honestly, because they describe the data the index points into; ``data_type``
    describes the file itself, and is the one that must not be borrowed.

    Nothing is lost by dropping the borrowed value. What the file indexes is on the
    record as ``derived_from`` — the verb, and where the parent is resolvable its name
    and md5, which join to its record — more than a copied category said. A declined row
    carries the edge without its grounding, and never had a borrowed ``data_type`` to
    lose: it has no parent, which is what declined means.
    """
    return build_field_entry(
        INDEX_DATA_TYPE,
        status=CLASSIFIED,
        evidence=[
            {
                "rule_id": "index_by_extension",
                "reason": f"{index_ext} identifies an index file",
                "value": INDEX_DATA_TYPE,
                "source_type": SOURCE_FILENAME_RULE,
            }
        ],
    )


def declined_record(record: dict, index_ext: str, reason: str, source: str | None) -> dict:
    """One output record for an index file this producer took no parent for.

    Says the one thing that is known and refuses the four that are not. The extension
    identifies the file as an index without any parent — it is how this producer found
    it — so ``data_type`` is ``index``, claimed the way an ``extension``-scope rule
    would claim it (``SOURCE_FILENAME_RULE``, per ``rule_engine._RULE_SOURCE_TYPES``).
    The other four dimensions are properties of the data the index points into, which
    only the parent can supply, so they are ``not_classified``: they *apply*, and
    nothing here can determine them. ``not_applicable`` would assert they cannot apply,
    which the matched case disproves by filling them in.

    Like ``inherited_evidence`` below, this builds its evidence by hand rather than
    through ``make_claim``, and so is the second path outside it; CLAUDE.md names both.
    Same reason as that one:
    an index file has exactly one claim per dimension and never reaches
    ``evaluate_claims``, so there is no tier to carry. Folding both in belongs to #413.
    Its ``rule_id`` values name no rule in ``unified_rules.yaml``, as
    ``inherited_from_parent`` already does not; nothing validates emitted rule ids
    against that file.

    Writing this record is what keeps such a file out of the catch-all producer. When
    #438 added it, that mattered because the catch-all's rule then stamped four
    dimensions ``not_applicable`` — ``data_type`` among them — on the strength of the
    extension alone, and coverage counts ``not_applicable`` as classified, so a file
    was reported as determined precisely where it is not.

    #437 removed that hazard at the source: the rule is now ``index_file`` and claims
    only ``data_type: index``, leaving the four a parent supplies open. So the three
    ways an index file can be classified — inherited from a matched parent, declined
    here, or reached by the rule — now agree on its kind and never deny a dimension
    that applies. The record is still written, because it carries what this producer
    knows about the file and keeps every index file in one output.
    """
    why = DECLINED_REASON_TEXT[reason]
    classifications = {DATA_TYPE: index_data_type_entry(index_ext)}
    for fld in CLASSIFICATION_FIELDS:
        if fld == DATA_TYPE:
            continue
        classifications[fld] = build_field_entry(
            None,
            status=NOT_CLASSIFIED,
            evidence=[
                {
                    "rule_id": reason,
                    "reason": f"No parent to inherit {fld} from: {why}",
                    "status": NOT_CLASSIFIED,
                    "source_type": SOURCE_DERIVATION_INHERITANCE,
                }
            ],
        )
    # The edge is still typed without a parent: the extension says this is an index of
    # something, and for an unambiguous one it says of what (`parent_kind_of`). Only the
    # grounding is missing, which is the ungrounded edge the schema anticipates.
    return OutputRecord.from_record(
        record,
        {fld: classifications[fld] for fld in CLASSIFICATION_FIELDS},
        source,
        derived_from=derivation_edge(None, None, index_ext),
    ).to_dict()


def parent_key(file_id, md5sum, file_name):
    """The identity a parent joins on: ``file_id`` where the catalog carries one.

    ``file_id`` is the catalog identity a consumer joins on
    (``records.CATALOG_IDENTITY_FIELDS``), and the only key here that is one.
    ``md5sum`` is not: two differently-named files can hold the same bytes and
    classify differently — ``grch38.fasta`` takes ``GRCh38`` from a filename rule
    while the byte-identical ``Homo_sapiens_assembly38.fasta`` takes
    ``not_applicable`` from the assembly rule. Keyed by md5 alone, whichever record
    load order reached last won for both, so the two ``.fai`` files that index them
    inherited one answer between them — one right, one wrong, the loser decided by
    a file order nothing here guarantees.

    Not every catalog has one, which is why this falls back rather than requiring it.
    The AnVIL input contract mandates ``file_id`` (``schema/metadata.yaml``) and every
    AnVIL output record has carried it since #433, but the HPRC catalog carries none
    on any of its 15,436 records — keying on ``file_id`` alone silently cost every
    HPRC index file its parent. ``(md5sum, file_name)`` is the weaker fallback: it
    separates the two FASTAs above, but 3,733 such pairs cover more than one AnVIL
    entry, and it matches exactly where the parent match upstream folds case (#455).

    A non-string ``file_id`` is not an identity either. ``file_id`` is not a
    classifier-blocking field, so a drifted value survives to a ``validation_failed``
    row, and a truthy one — ``["x"]`` — would raise ``TypeError`` as a dict key rather
    than miss. Only a non-empty string is taken.
    """
    if isinstance(file_id, str) and file_id:
        return file_id
    return (md5sum, file_name)


def load_classifications(*paths: Path) -> dict[str | tuple, dict]:
    """Load classifications from one or more classification JSON files.

    Keyed by ``parent_key``, which the caller uses to look a parent up.
    """
    classifications = {}

    for path in paths:
        if not path.is_file():
            continue
        with path.open() as f:
            data = json.load(f)
        for c in data.get("classifications", []):
            md5 = c.get("md5sum")
            if md5 or c.get("file_id"):
                classifications[parent_key(c.get("file_id"), md5, c.get("file_name"))] = {
                    "data_modality": field_label(c, "data_modality"),
                    "assay_type": field_label(c, "assay_type"),
                    "platform": field_label(c, "platform"),
                    "reference_assembly": field_label(c, "reference_assembly"),
                    # Per-field detail (the first is reference_assembly's build, #340)
                    # rides along with the labels: an index record must not describe
                    # its parent less precisely than the parent does.
                    "detail": {fld: field_detail(c, fld) for fld in CLASSIFICATION_FIELDS},
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
    snapshot = load_classifiable_snapshot(metadata_path, output_path.parent)
    source, files = snapshot.source, snapshot.records
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
    # Every *record* here has a well-formed md5 — `load_classifiable_snapshot` excluded
    # the rest (#376) — so reading one off a chosen file never needs a guard. That says
    # nothing about names: a name reaching more than one record is the case this exists
    # to detect.
    #
    # The name half of the key is case-folded, so this agrees with `route`, which has
    # folded case since #449 (#455). Folding makes two names differing only by case
    # identify neither file, which is #438's rule read case-insensitively.
    #
    # `str` only because folding reads every record in the dataset, index file or not: an
    # exact key took a drifted non-string name as-is, and `.lower()` would not, so one
    # bystander could take the producer down. It does not make a drifted name safe to
    # *classify* — a record this producer owns still raises below, as the three sibling
    # filename producers do via `FileInfo.from_filename`, which is what lets
    # `OutputRecord.from_record` promise no producer hands it a drifted `file_name`.
    files_by_folded_name: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
    for ds, ds_files in by_dataset.items():
        for f in ds_files:
            name = f.get("file_name")
            if name:
                files_by_folded_name[(ds, str(name).lower())].append(f)

    # Find index files and match to parents
    results = []
    unmatched = []  # Track failed lookups
    # Index files this producer took no parent for. They still get a record — the
    # extension says what they are, even when nothing says what they are of (#438).
    declined: list[tuple[dict, str, str]] = []
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
            candidate_tried = next((c for c in parent_candidates if (ds, c.lower()) in files_by_folded_name), None)

            if candidate_tried is None:
                stats[index_ext]["unmatched"] += 1
                unmatched.append(unmatched_entry(f, index_ext, parent_candidates, NO_MATCHING_PARENT))
                declined.append((f, index_ext, NO_MATCHING_PARENT))
                continue

            parent_files = files_by_folded_name[(ds, candidate_tried.lower())]

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

            # The matched file's own name, not the candidate that found it: this reaches
            # the row and the `derived_from` edge, which name the file as the catalog
            # spells it (#455).
            parent = parent_files[0]
            parent_name = parent["file_name"]
            parent_md5 = parent["file_md5sum"]
            stats[index_ext]["matched"] += 1

            # Joined on the parent's identity, by the same rule that keyed the map —
            # its `file_id` where the catalog has one, its bytes and name where not.
            parent_class = classifications.get(parent_key(parent.get("file_id"), parent_md5, parent_name), {})

            result = {
                # The raw input record this row is about; the output is built from it.
                # This intermediate adds only the parent's labels, and the two must stay
                # apart: reading `published` off this dict would publish the parent's
                # answer as the index file's own.
                "record": f,
                # The extension this file matched on, which is not always `file_format`:
                # every `.fai` in the corpus carries `file_format: "Other"` (#437).
                "index_extension": index_ext,
                "parent_file": parent_name,
                "parent_md5sum": parent_md5,
                "data_modality": parent_class.get("data_modality") or nc,
                "assay_type": parent_class.get("assay_type") or nc,
                "platform": parent_class.get("platform") or nc,
                "reference_assembly": parent_class.get("reference_assembly") or nc,
                "detail": parent_class.get("detail", {}),
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
            # `data_type` is the file's own kind and is never inherited (#437); the other
            # four are properties of the data the index points into, so they are.
            if fld == DATA_TYPE:
                classifications[fld] = index_data_type_entry(r["index_extension"])
                continue
            label = r.get(fld)
            evidence = inherited_evidence(fld, label, parent)
            status = _inherited_status(label)
            classifications[fld] = build_field_entry(
                None if status == CONFLICT else label, status=status, evidence=evidence, detail=r["detail"].get(fld)
            )
        # The index file's own identity, not the parent's (#433): this row resolves to
        # this file's bytes. The parent is the edge's grounding, and nothing else.
        standard_results.append(
            OutputRecord.from_record(
                r["record"],
                classifications,
                source,
                derived_from=derivation_edge(parent, r["parent_md5sum"], r["index_extension"]),
            ).to_dict()
        )

    for rec, index_ext, reason in declined:
        standard_results.append(declined_record(rec, index_ext, reason, source))

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
                        "with_data_modality": modality_all,
                        "with_reference_assembly": ref_all,
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
        f"{matched_all:,} inherited from a parent; {unmatched_all:,} found none and "
        f"{ambiguous_all:,} found more than one, so those {unmatched_all + ambiguous_all:,} "
        f"carry `index` and nothing else, and are listed in unmatched_files with why"
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
        default=Path("output/anvil") / PRODUCERS["bam"].output,
        help="Path to BAM classifications (used when --classifications not provided)",
    )
    parser.add_argument(
        "--vcf",
        "-v",
        type=Path,
        default=Path("output/anvil") / PRODUCERS["vcf"].output,
        help="Path to VCF classifications (used when --classifications not provided)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output/anvil") / INDEX.output,
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
