"""Reconcile: a stored inference run plus source evidence, settled by agreement (#432).

Beside the slots, reconcile builds each file's ``generated_by`` from the imported lineage
(#577): :mod:`reconcile_lineage` translates and resolves it, sharing the records scan
below, and ``edges.merge_steps`` merges it with inference's own step. Across that step a
file inherits what its activity passes from its parents (contract 4.9, #571,
:mod:`reconcile_inherit`), so after the join's scan (which runs when there is evidence or
lineage to place) the run is read twice more: once to settle every record's own answer and
step, then, the parents settled before their children, to write each record with its
inherited declarations weighed in.

The stage after inference (contract 6.1): **infer → reconcile**. Reading the sources is
the join below, reconcile's first step, and its per-source counts are a line of the
report (6.7). Reconcile reads a stored run and never
re-infers or fetches, so answering a review item costs a reconcile, not a corpus run
(6.4). It writes its own artifact beside the inference output and never touches it
(6.3): one NDJSON file per inference file under ``<run>/reconciled/`` (6.11), with an
envelope on line 1, plus ``reconcile_report.json``.

**The join** is an equality lookup on the key each evidence envelope names
(``target_key``), against that field of our output records. A line whose key value is
carried by exactly one record attaches to it; by two or more, to none — it is counted
ambiguous, and the report names every carrier for the first few such lines per file (the
#371 problem, seen from the evidence side). The join runs within the envelope's target
dataset when it names one.
An evidence file none of whose lines match is an error naming its source and dataset:
silence is not success (5.3). The record's identity in the report is the repository's
record key (``record_keys.SOURCE_RECORD_KEYS``), never a hard-coded field.

**Which evidence applies** is read from the input envelope the run was classified from:
a file applies when its ``target.system`` is the envelope's ``repository``. Where the
envelope names a ``catalog``, only files whose ``target.version`` equals it are read; a
file for another catalog is an older generation's history and is left unread. A
repository with no catalog (HPRC, which will never have one) reads every file about its
own files. That the stored run was actually made from this input is not provable
here — recording it on the run is #404.

**Translation**: a matched line's raw value selects a row of the translation table
(``value_map``, #414). An authored row yields claims through ``value_map.claims_from``;
a seeded or absent row yields none and the value stays on ``make review-queue``. For the
published source (``published_value``, contract 7.12) that absence still moves the slot:
see :func:`resolve_slot`.

**Resolution** (contract 4.3-4.6, and the second 2026-09-22 amendment of #432): inference's
own conclusion (already tier-resolved) and every source claim reconcile by agreement, with
no ranking. :func:`resolve_slot` is the whole rule. Every slot also carries ``use``, which
tells the indexer whether to take meta-disco's value or keep the repository's published
one (:func:`use_for`) — computed here so the export (#444) is structure only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path

from . import activities
from .activity_map import ActivityMap, load_activity_map
from .azul_manifest import REPOSITORY as ANVIL_REPOSITORY
from .deployments import DEFAULT_DEPLOYMENT, DEPLOYMENTS
from .edges import LineageStep, StepConflict, generic_only, merge_steps, misfits
from .inputs import load_envelope
from .lineage_evidence import DEFAULT_LINEAGE_EVIDENCE_ROOT
from .models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    CONFLICT,
    MIXED,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_DERIVATION_INHERITANCE,
    SOURCE_PRECEDENCE,
    SOURCE_PUBLISHED_VALUE,
    UNMAPPED,
    field_detail,
    field_label,
)
from .output_utils import (
    RECONCILED_DIR,
    find_latest_run,
    iter_records,
    iter_run_files,
    reconciled_name,
    relative_to,
    run_file_metadata,
    write_reconciled_file,
)
from .producers import PRODUCERS
from .reconcile_inherit import (
    REFERENCE_ASSEMBLY,
    InheritanceCycle,
    Inherited,
    Interner,
    Settled,
    Step,
    build_detail,
    build_for,
    inherit,
    reference_build,
)
from .reconcile_lineage import Carrier, Locator, PendingLineage, applies, resolve_lineage, translate_lineage
from .record_keys import PUBLISHED_TABLES, RecordKey, is_key_value, record_key
from .records import JOIN_KEY_OUTPUT_FIELDS, STEP_OUTCOMES_KEY
from .rule_engine import CONFLICT_MARKER, make_claim
from .schema.classification_model import EvidenceFileEnvelope
from .schema_vocab import most_specific
from .slot_map import load_slot_map, published_slot_map_resource
from .source_evidence import (
    DEFAULT_SOURCE_EVIDENCE_ROOT,
    EvidenceEntry,
    EvidenceFileStatus,
    iter_evidence,
    list_cell,
    report_evidence_files,
    require_one_published_source,
)
from .value_map import ValueMap, claims_from, load_value_map

REPORT_FILE = "reconcile_report.json"

# The per-slot instruction to the indexer (#432, second 2026-09-22 amendment).
USE_META_DISCO = "meta_disco"
USE_PUBLISHED = "published"

INFERENCE = "inference"

# Report labels. The per-input outcomes are never stored on a record; the per-slot
# category is, as the slot's `credited_to` (:func:`credited_to`, #552).
#
# Per input, scored against the other inputs' declarations for the same slot. Two
# declarations agree when they are equal or nest in the slot's `is_a` hierarchy
# (`schema_vocab.most_specific`, #473): `CHM13` agrees with `T2T-CHM13v2.0`. A source:
# match or harmonized (it declared, and every other input's declaration agrees with it),
# disagreed (another input's does not), unreviewed (its value has no authored row),
# no_claim (its value's authored row declares nothing for the slot, or declares
# `not_classified`, which is no answer), silent. A source's `not_applicable` counts toward
# match/harmonized like a value, so its harmonized total also covers slots whose category
# is `not_applicable`; a source beside inference's own conflict is scored against the
# other sources only, since that conflict declares nothing. Inference: agreed (a source declared
# an agreeing value), added (every source was silent), unconfirmed (no source declared a value,
# but one spoke — unreviewed or no_claim — so it was not silent), disagreed (another
# input's declaration does not agree with it, or its own rules conflicted), silent.
#
# Per slot: :func:`credited_to`, which states the rule.
MATCH = "match"
HARMONIZED = "harmonized"
UNREVIEWED = "unreviewed"
NO_CLAIM = "no_claim"
SILENT = "silent"
AGREED = "agreed"
ADDED = "added"
UNCONFIRMED = "unconfirmed"
DISAGREED = "disagreed"
FILLED_BY_INFERENCE = "filled_by_inference"
# The value came from the file's parents across its `generated_by` (contract 4.9, #571).
INHERITED = "inherited"
PUBLISHED_UNREVIEWED = "published_unreviewed"
CONFLICT_INFERENCE = "conflict_inference"
CONFLICT_PUBLISHED = "conflict_published"
CONFLICT_SOURCES = "conflict_sources"
CONFLICT_CATEGORIES = (CONFLICT_INFERENCE, CONFLICT_SOURCES, CONFLICT_PUBLISHED)
# The report's name for evidence that names no dataset, and so covers every one.
EVERY_DATASET = "(every dataset)"


def fill_category(name: str, harmonized: bool) -> str:
    """The slot category crediting a delivered value to the source named ``name`` in SOURCE_PRECEDENCE."""
    return f"filled_by_{name}_harmonized" if harmonized else f"filled_by_{name}"


# Every category ``credited_to`` returns, in the order a report reads them: each
# source's fills by precedence, inference's, inheritance's, the three kinds of conflict,
# then the slot's other outcomes. Exactly one per slot, so a dimension's counts sum to the
# files.
SLOT_CATEGORIES = (
    *(fill_category(name, harmonized) for _, name in SOURCE_PRECEDENCE for harmonized in (False, True)),
    FILLED_BY_INFERENCE,
    INHERITED,
    *CONFLICT_CATEGORIES,
    PUBLISHED_UNREVIEWED,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
)

# Each repository's published slot map, whose columns are the slots its published source
# speaks to (#497). Read for those slots rather than inferred from the evidence, whose
# importer writes no line for an empty cell, so a column empty everywhere leaves none.
PUBLISHED_SLOT_MAPS = {ANVIL_REPOSITORY: published_slot_map_resource}


def published_slots(repository: str) -> frozenset[str]:
    """The slots ``repository``'s published source speaks to, from its published slot map; none if it has no map."""
    resource = PUBLISHED_SLOT_MAPS.get(repository)
    if resource is None:
        return frozenset()
    return frozenset(slot for entry in load_slot_map(resource()).entries for slot in entry.slots)


# How many unmatched and ambiguous key values the report names per evidence file.
MAX_EXAMPLES = 5


class ReconcileError(Exception):
    """A refusal: the inputs cannot be reconciled as given, and nothing was written."""


# --- resolution ---------------------------------------------------------------------


def declaration(entry: dict) -> str | None:
    """What a claim, or inference's conclusion, declares for resolution: a value, ``not_applicable``, or None.

    Reads ``value`` then ``status``. ``not_classified`` declares no answer (4.6) and
    ``conflict`` is not a declaration, so both are None, like a claim declaring nothing.
    A conclusion carries a value only when it is ``classified`` (the schema's rule), so
    one function serves both.
    """
    if entry.get("value") is not None:
        return entry["value"]
    if entry.get("status") == NOT_APPLICABLE:
        return NOT_APPLICABLE
    return None


def resolve_slot(
    slot: str,
    inferred: dict,
    source_claims: Iterable[dict],
    published_unreviewed: bool,
    inherited: Iterable[dict] = (),
) -> tuple[str, str | None]:
    """The reconciled ``(status, value)`` of one slot of one file, from inference's ``{value, status}``.

    ``inherited`` are the slot's inherited claims (contract 4.9, :mod:`reconcile_inherit`),
    weighed as any other declaration; one in state ``mixed`` declares no value but takes
    part. The rule is :func:`settle`'s.
    """
    inherited = list(inherited)
    inference_conflict, declared = own_inputs(inferred, source_claims)
    declared |= {d for d in map(declaration, inherited) if d is not None}
    mixed = any(c.get("claim_state") == MIXED for c in inherited)
    return settle(slot, inference_conflict, declared, mixed, published_unreviewed)


def own_inputs(inferred: dict, source_claims: Iterable[dict]) -> tuple[bool, frozenset[str]]:
    """What a slot's own inputs give :func:`settle`: whether inference concluded ``conflict``, and every declaration.

    Inference's and the sources', before anything is inherited; the first pass keeps it for
    a child, and :func:`resolve_slot` adds the inherited declarations to it.
    """
    declared = {d for d in map(declaration, source_claims) if d is not None}
    if (own := declaration(inferred)) is not None:
        declared.add(own)
    return inferred["status"] == CONFLICT, frozenset(declared)


def settle(
    slot: str, inference_conflict: bool, declared: AbstractSet[str], mixed: bool, published_unreviewed: bool
) -> tuple[str, str | None]:
    """One slot's ``(status, value)`` from every input's declaration: the whole resolution rule.

    ``declared`` holds each input's declaration (a value or ``not_applicable``: inference's,
    every source's, every inherited one's); ``mixed`` whether an inherited declaration is
    the state ``mixed``. In order:

    1. Inference itself concluded ``conflict``: the conflict stands, whatever a source
       says — agreeing with one of two disagreeing rules is not resolving them, which 4.7
       reserves for a curator rule (open question 1, decided 2026-09-22).
    2. The declarations differ — two values, or a value beside ``not_applicable`` (4.6):
       ``conflict``, unless the values nest in the slot's ``is_a`` hierarchy
       (:func:`~.schema_vocab.most_specific`, #473): ``CHM13`` beside
       ``T2T-CHM13v2.0`` is one answer at two levels of detail, and the deepest is
       the value (4.4).
    3. An inherited ``mixed`` beside any declaration: ``conflict``, since one value
       contradicts a lineage that has none, and ``not_applicable`` stands for the values
       it would contradict (4.9). Alone it declares nothing, and the slot goes on.
    4. The published source spoke with a value no authored row reads (unreviewed): a
       ``conflict`` if any other input declared something, else ``not_classified`` —
       missing work, not a challenge.
    5. One value: ``classified``. Otherwise ``not_applicable`` if anyone declared it, and
       ``not_classified`` if nobody declared anything. ``not_classified`` never conflicts
       and yields to ``not_applicable`` (4.6).

    ``value`` is null unless the status is ``classified``.
    """
    if inference_conflict:
        return CONFLICT, None
    if len(declared) > 1:
        deepest = most_specific(slot, declared)
        if deepest is None:
            return CONFLICT, None
        declared = {deepest}
    if mixed and declared:
        return CONFLICT, None
    if published_unreviewed:
        return (CONFLICT, None) if declared else (NOT_CLASSIFIED, None)
    if not declared:
        return NOT_CLASSIFIED, None
    (only,) = declared
    if only == NOT_APPLICABLE:
        return NOT_APPLICABLE, None
    return CLASSIFIED, only


def use_for(status: str) -> str:
    """Take meta-disco's answer where it has one; keep the published value where it does not.

    ``classified`` and ``not_applicable`` are answers. ``conflict`` and ``not_classified``
    are not, and the indexer keeps what the repository already publishes — the not-worse
    path, until curator rules (#397) answer conflicts.
    """
    return USE_META_DISCO if status in (CLASSIFIED, NOT_APPLICABLE) else USE_PUBLISHED


def is_harmonized(claim: dict) -> bool:
    """Whether a source claim's raw value differs from the term it declared.

    Verbatim means the raw value, or a one-element list cell's element, is exactly the
    declared term; anything else — case, an added annotation, a different name — is the
    same meaning spelled differently, which is what an authored row records.
    """
    raw = claim.get("raw_value")
    term = declaration(claim)
    if raw is None or term is None:
        return False
    elements = list_cell(raw)
    if elements is not None and len(elements) == 1:
        raw = elements[0]
    return raw != term


# --- the join -----------------------------------------------------------------------


@dataclass
class EvidenceFile:
    """One applicable evidence file, and what the join made of it."""

    path: Path
    envelope: EvidenceFileEnvelope
    offered: int = 0
    matched: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    unmatched_examples: list[str] = field(default_factory=list)
    ambiguous_examples: list[dict] = field(default_factory=list)

    @property
    def source_type(self) -> str:
        return str(self.envelope.source_type)

    @property
    def dataset(self) -> str | None:
        return self.envelope.target.dataset

    @property
    def target_key(self) -> str:
        return str(self.envelope.target_key)

    @property
    def record_field(self) -> str:
        """The output-row field this file's ``target_key`` is read from."""
        return JOIN_KEY_OUTPUT_FIELDS[self.target_key]

    def identity(self, root: Path) -> dict:
        """What names the file: where it is, what kind of source it is, and which dataset and version."""
        return {
            "path": relative_to(self.path, root),
            "source_type": self.source_type,
            "dataset": self.dataset,
            "source_version": self.envelope.source_version,
        }

    def summary(self, root: Path) -> dict:
        """:meth:`identity` plus the join's counts for the file, as the report lists it."""
        return {
            **self.identity(root),
            "source": self.envelope.source.repository,
            "table": self.envelope.source.table,
            "key": self.target_key,
            "offered": self.offered,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "ambiguous": self.ambiguous,
            "unmatched_examples": self.unmatched_examples,
            "ambiguous_examples": self.ambiguous_examples,
        }


def select_evidence(
    statuses: Iterable[EvidenceFileStatus], repository: str, catalog: str | None
) -> tuple[list[EvidenceFile], list[dict]]:
    """The evidence files for this repository's catalog, and the ones about another repository.

    ``statuses`` is what :func:`source_evidence.report_evidence_files` found. Where the
    input names a catalog, only files resolved against that catalog are read: a file for
    another catalog (an older generation's history, kept on disk) is not this run's
    evidence, and is neither read nor listed. A repository with no catalog (HPRC) reads
    every file about its own files. A file about another repository is skipped and listed:
    it is about files this run does not hold. Refuses (``ReconcileError``) a file whose
    envelope could not be read, and a selected file whose ``target_key`` no output-row
    field holds (criterion 5, ``records.JOIN_KEY_OUTPUT_FIELDS``).
    """
    applicable: list[EvidenceFile] = []
    skipped: list[dict] = []
    for status in statuses:
        envelope = status.envelope
        if envelope is None:
            raise ReconcileError(f"{status.path}: evidence envelope could not be read: {status.error}")
        if envelope.target.system != repository:
            skipped.append({"path": status.path, "target_system": envelope.target.system})
            continue
        if not applies(envelope.target, repository, catalog):
            continue
        key = str(envelope.target_key)
        if key not in JOIN_KEY_OUTPUT_FIELDS:
            raise ReconcileError(
                f"{status.path}: target_key {key!r} is not held by any field of our output records "
                f"(joinable keys: {sorted(JOIN_KEY_OUTPUT_FIELDS)}); nothing to join it against"
            )
        applicable.append(EvidenceFile(status.path, envelope))
    return applicable, skipped


@dataclass(slots=True)
class SlotEvidence:
    """What the sources said about one slot of one file."""

    claims: list[dict] = field(default_factory=list)
    # Source types that spoke to the slot with a value no authored row reads.
    unreviewed: set[str] = field(default_factory=set)
    # Source types that spoke to the slot with a value whose authored row declares
    # nothing for it (`declares: {}`, or declares only other slots): reviewed, no claim.
    no_claim: set[str] = field(default_factory=set)


# The slot evidence of a slot no source spoke to. Shared and never written: every reader
# only reads it.
NO_EVIDENCE = SlotEvidence()


@dataclass
class Joined:
    """The join's result: per record identity, per slot, what the sources said."""

    slots: dict[str, dict[str, SlotEvidence]]
    # Per locator the caller asked for besides the evidence's (``extra``), every record carrying it.
    carriers: dict[_Key, list[Carrier]]
    # Per source type, the (dataset, slot) pairs its evidence speaks to: a line's field,
    # and every slot a row it selected declares (3.10). Dataset None for a file scoped to
    # no dataset, which speaks to that slot in every dataset.
    coverage: dict[str, set[tuple[str | None, str]]]


# A key a line is matched by: the output-row field, the dataset the envelope scopes the
# join to (None when it names none), and the value.
_Key = Locator


def content_step_counts(run_dir: Path) -> dict[str, dict[str, dict[str, int]]]:
    """Per producer and dataset, the outcomes of the producer's step reader (#609, #621).

    Read from each classification file's ``metadata.details.producer_steps``, which a
    producer whose type states a step writes (``FileTypeConfig.step``): the VCF producer's
    outcomes are ``producer_steps.OUTCOMES``, the tar and sample-map producers'
    ``cohort_steps.OUTCOMES``, so each producer's are kept apart. Empty for a run written
    before the readers, or with no such producer.
    """
    found: dict[str, dict[str, dict[str, int]]] = {}
    for producer in PRODUCERS.values():
        path = run_dir / producer.output
        if not path.exists():
            continue
        details = (run_file_metadata(path) or {}).get("details") or {}
        per_dataset = details.get(STEP_OUTCOMES_KEY) or {}
        if per_dataset:
            found[producer.name] = {dataset: dict(counts) for dataset, counts in sorted(per_dataset.items())}
    return found


def join(
    evidence: list[EvidenceFile], run_dir: Path, key: RecordKey, table: ValueMap, extra: set[_Key] | None = None
) -> Joined:
    """Attach each evidence line whose key value exactly one record carries to that record, and translate it.

    The join runs within the envelope's target dataset when it names one — the scope
    ``EvidenceTarget.dataset`` declares — matched against the record's ``dataset_title``.
    A line whose key no record carries is unmatched; one whose key several records carry
    is ambiguous and attaches to none, and the report names every carrier for the first
    few such keys per file. ``evidence`` is updated in place with each file's counts.

    The evidence is read into memory first — it is small beside the run — and then one
    pass over the run's records finds which records carry each key — and each of ``extra``,
    the lineage pass's locators (``reconcile_lineage``), so the run is scanned once for both.
    Refuses
    (``ReconcileError``) a carrying record with no usable record key, which it could not
    name, and an evidence file none of whose lines matched, an empty one included
    (contract 5.3).
    """
    wanted: dict[_Key, list[tuple[int, EvidenceEntry]]] = defaultdict(list)
    coverage: dict[str, set[tuple[str | None, str]]] = defaultdict(set)
    for n, ev in enumerate(evidence):
        for entry in iter_evidence(ev.path):
            ev.offered += 1
            wanted[(ev.record_field, ev.dataset, entry.target_key_value)].append((n, entry))
            coverage[ev.source_type].add((ev.dataset, entry.field))
    extra = extra or set()
    found_by_key = _carriers(run_dir, key, set(wanted) | extra)
    carriers = {k: [c.key for c in found] for k, found in found_by_key.items() if k in wanted}

    slots: dict[str, dict[str, SlotEvidence]] = defaultdict(lambda: defaultdict(SlotEvidence))
    for wanted_key, lines in wanted.items():
        record_field, _, value = wanted_key
        found = carriers.get(wanted_key, [])
        for n, entry in lines:
            ev = evidence[n]
            if not found:
                ev.unmatched += 1
                if len(ev.unmatched_examples) < MAX_EXAMPLES and value not in ev.unmatched_examples:
                    ev.unmatched_examples.append(value)
            elif len(found) > 1:
                ev.ambiguous += 1
                example = {record_field: value, key.output_field: sorted(found)}
                if len(ev.ambiguous_examples) < MAX_EXAMPLES and example not in ev.ambiguous_examples:
                    ev.ambiguous_examples.append(example)
            else:
                ev.matched += 1
                for slot in _translate(slots[found[0]], entry, ev, table):
                    coverage[ev.source_type].add((ev.dataset, slot))

    for ev in evidence:
        if not ev.matched:
            raise ReconcileError(
                f"{ev.path}: none of the {ev.offered:,} lines of {ev.envelope.source.repository} "
                f"{ev.dataset} ({ev.source_type}, key {ev.target_key}) matched a record of the run — "
                f"silence is not success (contract 5.3), and an evidence file with no lines is silent too"
            )

    return Joined(slots=slots, carriers={k: v for k, v in found_by_key.items() if k in extra}, coverage=dict(coverage))


def _carriers(run_dir: Path, key: RecordKey, wanted: set[_Key]) -> dict[_Key, list[Carrier]]:
    """Every record carrying each of ``wanted``, from one pass over the run's records.

    A key scoped to a dataset is looked for only among that dataset's records (by
    ``dataset_title``), an unscoped one (dataset None) among all. Refuses
    (``ReconcileError``) a carrying record with no usable record key, which could not be named.
    """
    found: dict[_Key, list[Carrier]] = defaultdict(list)
    if not wanted:
        return found
    # The (field, dataset) scopes to look up, grouped by the dataset they need, so a
    # record is looked up only under its own dataset's scopes and the unscoped ones.
    scopes: dict[str | None, set[str]] = defaultdict(set)
    for record_field, dataset, _ in wanted:
        scopes[dataset].add(record_field)
    unscoped = tuple(scopes.pop(None, ()))
    for record in iter_records(run_dir):
        title = record.get("dataset_title")
        scoped = [(f, title) for f in scopes.get(title, ())] if isinstance(title, str) else []
        for record_field, dataset in scoped + [(f, None) for f in unscoped]:
            value = record.get(record_field)
            if not is_key_value(value):
                continue
            at = (record_field, dataset, value)
            if at in wanted:
                identity = record.get(key.output_field)
                if not is_key_value(identity):
                    raise ReconcileError(
                        f"a record carrying {record_field}={value!r} has no usable {key.output_field}, "
                        "the run's record key; it cannot be named"
                    )
                data_type = (record.get("classifications") or {}).get("data_type") or {}
                found[at].append(Carrier(identity, str(record.get("file_name") or ""), data_type.get("value")))
    return found


def _translate(
    record_slots: dict[str, SlotEvidence], entry: EvidenceEntry, ev: EvidenceFile, table: ValueMap
) -> set[str]:
    """Add a matched line's claims to its record's slots, or mark the slot unreviewed by its source type.

    The row is selected here and handed to ``claims_from``, because an authored row
    declaring nothing (``declares: {}``) yields no claim and is still reviewed.

    A line no authored row reads makes no claim (contract 3.7). From the published source
    it still moves the slot (to ``conflict`` or ``not_classified``), so what it said is
    kept in the slot's evidence as an ``unmapped`` entry — its source, raw value and join,
    and no value, status or rule — and the record shows why on its own (6.10). It declares
    nothing, so resolution does not read it. Another source's unreviewed value moves
    nothing, is counted in the report, and is not written to the record.

    Returns the slots the line's claims were made on.
    """
    row = table.select(entry.field, entry.raw_value, entry.source.name, entry.source.dataset)
    if row is None or not row.authored:
        said = record_slots[entry.field]
        said.unreviewed.add(ev.source_type)
        if ev.source_type != SOURCE_PUBLISHED_VALUE:
            return set()
        seen = make_claim(
            source_type=ev.source_type,
            state=UNMAPPED,
            source=entry.source,
            raw_value=entry.raw_value,
            join_key=ev.target_key,
            match_exact=True,
        )
        if seen not in said.claims:
            said.claims.append(seen)
        return set()
    if entry.field not in row.declares:
        record_slots[entry.field].no_claim.add(ev.source_type)
    claimed = set()
    for slot, claim in claims_from(entry, ev.source_type, table, join_key=ev.target_key, row=row):
        claimed.add(slot)
        existing = record_slots[slot].claims
        if claim not in existing:
            existing.append(claim)
    return claimed


# --- the record ---------------------------------------------------------------------


def credited_to(settled: dict, said: SlotEvidence, inherited: Iterable[dict] = ()) -> str:
    """Where a settled slot's answer is credited: one of ``SLOT_CATEGORIES`` (#552).

    Stored on the reconciled slot as ``credited_to`` by :func:`reconcile_record`, and
    counted from there by the report, so a record and the report's "how each slot
    settled" table cannot disagree. Exactly one of, first match wins:

    - ``published_unreviewed``: ``not_classified`` because the published source spoke
      with a value no authored row reads — work to do, not a challenge;
    - a ``conflict``, by kind: ``conflict_inference`` (inference's own rules disagreed),
      ``conflict_published`` (the published source declared a value or spoke with an
      unreviewed one — whichever inputs disagreed, so its value need not be the disputed
      one), else ``conflict_sources``;
    - the slot's status where it is not ``classified`` (``not_applicable``,
      ``not_classified``);
    - ``filled_by_<source>`` or ``filled_by_<source>_harmonized`` for the first source in
      ``SOURCE_PRECEDENCE`` that declared the delivered value — verbatim before
      harmonized;
    - ``filled_by_inference`` where inference declared it;
    - ``inherited`` where only an inherited claim (``inherited``, contract 4.9) did — the
      value came from the file's parents, and nothing read the file itself for it;
    - else ``filled_by_inference``.

    It attributes and never decides: ``resolve_slot`` settled the slot before this reads
    it, and precedence never picks a value (contract 6.8). Where declarations nest, the
    vocabulary picked the deepest (#473), and a source that named only its parent is not
    credited with it. Whether inference agreed is its own outcome, in the report's
    ``inputs``.
    """
    status = settled["status"]
    if status == NOT_CLASSIFIED and SOURCE_PUBLISHED_VALUE in said.unreviewed:
        return PUBLISHED_UNREVIEWED
    if status == CONFLICT:
        if settled["inferred"]["status"] == CONFLICT:
            return CONFLICT_INFERENCE
        published = any(c["source_type"] == SOURCE_PUBLISHED_VALUE and declaration(c) is not None for c in said.claims)
        return CONFLICT_PUBLISHED if published or SOURCE_PUBLISHED_VALUE in said.unreviewed else CONFLICT_SOURCES
    if status != CLASSIFIED:
        return status
    for source_type, name in SOURCE_PRECEDENCE:
        # The source that declared the delivered value: where declarations nest,
        # one naming only the parent did not supply the value (#473).
        declaring = [c for c in said.claims if c["source_type"] == source_type and declaration(c) == settled["value"]]
        if declaring:
            return fill_category(name, harmonized=all(is_harmonized(c) for c in declaring))
    if declaration(settled["inferred"]) != settled["value"] and any(
        declaration(c) == settled["value"] for c in inherited
    ):
        return INHERITED
    return FILLED_BY_INFERENCE


def reconcile_record(
    record: dict, record_slots: dict[str, SlotEvidence], inherited: dict[str, list[Inherited]] | None = None
) -> dict:
    """The reconciled record for one inference record: same identity, each slot settled.

    ``inherited`` is the record's inherited declarations by slot (:mod:`reconcile_inherit`):
    each is weighed with inference's and the sources' and written after them in the slot's
    evidence. A classified slot whose value is not inference's carries the build ``base`` and
    ``version`` of the inherited declaration that declared that value, if one did
    (``reconcile_inherit.build_for``), whoever the slot is credited to.

    Its ``generated_by`` is not settled here: :func:`reconcile_run` merges inference's step
    with the record's lineage steps (``edges.merge_steps``) after this returns, where the
    lineage pass's result is in hand.

    Each slot keeps inference's evidence as it is, adds the source claims after it, and
    gains ``inferred`` (what inference concluded, which its evidence alone cannot rebuild
    without re-running tier resolution), ``use`` and ``credited_to`` (where the answer is
    credited, :func:`credited_to`, #552). Inference's per-dimension detail
    (``models.field_detail``, e.g. ``build``) stays only while the slot still concludes
    inference's value — it describes that value. Keys of
    ``classifications`` that are not slots (a producer's scalar hints) pass through.

    Raises ``ValueError`` on a record missing a slot or a slot's ``status``: every
    producer writes every slot, so a record without one is damaged or was written
    before the slot existed (``instrument_model``, #532), and settling the rest would
    write a reconciled record that silently lacks a dimension.
    """
    out = dict(record)
    classifications = record.get("classifications")
    if not isinstance(classifications, dict):
        raise ValueError(f"record {record.get('file_name')!r} has no classifications block; it is damaged")
    classifications = dict(classifications)
    for slot in CLASSIFICATION_FIELDS:
        entry = classifications.get(slot)
        if not isinstance(entry, dict) or "status" not in entry:
            raise ValueError(
                f"record {record.get('file_name')!r} has no {slot} slot with a status; it is damaged, "
                "or the run predates the slot — re-run `make classify`"
            )
        said = record_slots.get(slot, NO_EVIDENCE)
        passed = (inherited or {}).get(slot, [])
        claims = [i.claim() for i in passed]
        inferred = {"value": entry.get("value"), "status": entry["status"]}
        status, value = resolve_slot(slot, inferred, said.claims, SOURCE_PUBLISHED_VALUE in said.unreviewed, claims)
        settled: dict = {
            "value": value,
            "status": status,
            "use": use_for(status),
            "inferred": inferred,
            "evidence": list(entry.get("evidence") or []) + said.claims + claims,
        }
        settled["credited_to"] = credited_to(settled, said, claims)
        if (status, value) == (inferred["status"], inferred["value"]):
            settled.update(field_detail(record, slot))
        elif status == CLASSIFIED:
            settled.update(build_detail(build_for(value, passed)))
        classifications[slot] = settled
    out["classifications"] = classifications
    return out


# --- the report ---------------------------------------------------------------------


@dataclass
class Report:
    """Counts per dataset and dimension: how each slot settled, and how each input did."""

    coverage: dict[str, set[tuple[str | None, str]]]
    # The slots the published source's map declares (:func:`published_slots`).
    published_slots: frozenset[str] = frozenset()
    files: Counter = field(default_factory=Counter)
    slots: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Counter)))
    # Per dataset and slot, the files where the delivered value is ours and the published
    # source said nothing for the file — silent on a column it has, or without a column for
    # the slot at all: metadata added over what the repository publishes. Counted only when
    # the published source's evidence was read, since otherwise what it publishes is not
    # known. Kept apart from `slots`, whose categories sum to the file count; this one
    # overlaps them.
    added_over_published: dict = field(default_factory=lambda: defaultdict(Counter))
    # Per dataset and slot, the files where inference declared nothing and a source's
    # declaration now answers the slot (`classified` or `not_applicable`): the gaps the
    # sources filled. Also apart from `slots`, whose filled_by_<source> credits a source
    # whether or not inference agreed.
    filled_over_inference: dict = field(default_factory=lambda: defaultdict(Counter))
    inputs: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(Counter))))
    # Per dataset, slot and conflict category, the files per distinct set of competing
    # values (contract 5.1): which input said what, as :meth:`_competing` reads it.
    conflicts: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(Counter))))
    # Per dataset and slot, the files per reconciled value, or per status where the slot
    # has none (`conflict`, `not_applicable`, `not_classified`): what a dataset holds, not
    # how it was filled (#545). Like `slots`, each dataset's counts sum to its file count.
    values: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Counter)))
    # The lineage pass (#577): per source type and dataset, what became of its lines
    # (`reconcile_lineage.OUTCOMES`); per dataset, the files whose `generated_by` each
    # combination of source types named; per dataset and conflict kind, the files and the
    # first few with who said what; per (dataset, activity, problem, detail), the steps that
    # do not fit their declaration (`edges.misfits`).
    lineage_counts: dict = field(default_factory=dict)
    # Per producer and dataset, what its step reader made of each file's content
    # (`producer_steps.OUTCOMES`, #609; `cohort_steps.OUTCOMES`, #621), as the producers'
    # metadata records it.
    content_steps: dict = field(default_factory=dict)
    steps: dict = field(default_factory=lambda: defaultdict(Counter))
    step_conflicts: dict = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(lambda: {"files": 0, "examples": []}))
    )
    misfits: Counter = field(default_factory=Counter)
    # Per dataset, the files whose only step is the generic `Activity`, written as no
    # `generated_by` until reviewed (`edges.merge_steps`).
    generic_only: Counter = field(default_factory=Counter)
    # Inheritance (#571): per dataset and slot, what each role's parents gave a child
    # (`reconcile_inherit.OUTCOMES`), once per role that passes the slot.
    inheritance: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Counter)))
    # The same, per dataset, role and slot (#621): what one role gave, apart from the rest.
    inheritance_by_role: dict = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))
    )
    # Per (dataset, slot), the source types whose evidence speaks to it: only those are
    # scored there.
    _covering: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)

    def covering(self, dataset: str, slot: str) -> tuple[str, ...]:
        """The source types that speak to ``slot`` in ``dataset``.

        Read off the evidence lines, except for the published source: it is one table with
        the same columns in every dataset of its repository (contract 7.12,
        ``record_keys.PUBLISHED_TABLES``), and its importer skips an empty cell and writes no
        file for a dataset whose columns are all empty. So it speaks to every slot its
        published slot map declares, and every slot it has a line for, in every dataset
        of the run — a dataset with no published file is one where the repository
        publishes nothing, which is still that source's silence.
        """
        at = (dataset, slot)
        if at not in self._covering:
            covering = []
            for source_type, pairs in self.coverage.items():
                if source_type == SOURCE_PUBLISHED_VALUE:
                    speaks = slot in self.published_slots or slot in {s for _, s in pairs}
                else:
                    speaks = at in pairs or (None, slot) in pairs
                if speaks:
                    covering.append(source_type)
            self._covering[at] = tuple(sorted(covering))
        return self._covering[at]

    def add(self, reconciled: dict, record_slots: dict[str, SlotEvidence]) -> None:
        dataset = str(reconciled.get("dataset_title") or "")
        self.files[dataset] += 1
        for slot in CLASSIFICATION_FIELDS:
            settled = reconciled["classifications"][slot]
            said = record_slots.get(slot, NO_EVIDENCE)
            own = declaration(settled["inferred"])
            covering = self.covering(dataset, slot)
            category = settled["credited_to"]
            self.slots[dataset][slot][category] += 1
            self.values[dataset][slot][field_label(reconciled, slot)] += 1
            if category in CONFLICT_CATEGORIES:
                self.conflicts[dataset][slot][category][self._competing(settled, said, own)] += 1
            if (
                own is None
                and settled["inferred"]["status"] != CONFLICT
                and settled["status"] in (CLASSIFIED, NOT_APPLICABLE)
                # A source's, not an inherited one's (#571): the answer a source declared.
                and any(declaration(c) == (settled["value"] or settled["status"]) for c in said.claims)
            ):
                self.filled_over_inference[dataset][slot] += 1
            per_input = self.inputs[dataset][slot]
            lineage = _inherited_declarations(settled)
            per_input[INFERENCE][self._inference_outcome(slot, settled, said, own, lineage)] += 1
            published_silent = SOURCE_PUBLISHED_VALUE in self.coverage and SOURCE_PUBLISHED_VALUE not in covering
            for source_type in covering:
                outcome = self._source_outcome(slot, said, own, source_type, lineage)
                per_input[source_type][outcome] += 1
                if source_type == SOURCE_PUBLISHED_VALUE and outcome == SILENT:
                    published_silent = True
            if published_silent and settled["status"] == CLASSIFIED:
                self.added_over_published[dataset][slot] += 1

    def add_inheritance(self, reconciled: dict, outcomes: Iterable[tuple[str, str, str]]) -> None:
        """Count what each role's parents gave one child, per slot and per role and slot (``reconcile_inherit.OUTCOMES``)."""
        dataset = str(reconciled.get("dataset_title") or "")
        for role, slot, outcome in outcomes:
            self.inheritance[dataset][slot][outcome] += 1
            self.inheritance_by_role[dataset][role][slot][outcome] += 1

    def add_step(self, reconciled: dict, conflict: StepConflict | None, steps: list[LineageStep]) -> None:
        """Count one record's settled step: who named it, a conflict with who said what, or how it misfits.

        ``steps`` are the record's lineage steps, whose parents' ``data_type`` the misfit
        check reads; an input only inference names has none, so its kind is not judged. A
        parent's ``data_type`` is inference's, read in the records scan, while the child's is
        the reconciled one: the parents are not reconciled before the scan. A misfit is
        counted once per file, however many inputs show it.
        """
        dataset = str(reconciled.get("dataset_title") or "")
        step = reconciled.get("generated_by")
        if step is None and conflict is None and generic_only(None, steps):
            self.generic_only[dataset] += 1
            return
        if conflict is not None:
            tally = self.step_conflicts[dataset][conflict.kind]
            tally["files"] += 1
            examples = tally["examples"]
            if len(examples) < MAX_EXAMPLES:
                examples.append(
                    {
                        "file_name": reconciled.get("file_name"),
                        "role": conflict.role,
                        "said": [{"said": what, "by": by} for what, by in conflict.said],
                    }
                )
            return
        if not step:
            return
        self.steps[dataset]["+".join(sorted({n["source_type"] for n in step["named_by"]}))] += 1
        child_kind = reconciled["classifications"]["data_type"].get("value")
        kinds = {s.parent_key: s.parent_data_type for s in steps}
        for problem, detail in dict.fromkeys(misfits(step, child_kind, kinds)):
            self.misfits[(dataset, step["activity"], problem, detail)] += 1

    @staticmethod
    def _competing(settled: dict, said: SlotEvidence, own: str | None) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Who said what on a conflicted slot, as sorted ``(input, values)`` pairs.

        Four kinds of input are listed:

        - inference: its value, or where its own rules conflicted, the ``competing_values``
          of its conflict marker. An index file's conflict copied from its parent at
          inference, in a run made before #571, carries no marker (#413), so there inference
          is listed with no values;
        - each source type: the values it declared;
        - ``<source type> (unreviewed)``: the raw values of that source type's unmapped
          entries — only the published source's are kept on a record (:func:`_translate`);
        - ``derivation_inheritance``: what the file's parents gave it (contract 4.9), a value,
          ``not_applicable`` or ``mixed``, read off the slot's inherited claims.

        A source that declared nothing is left out. Values, not the rules behind them: a rule id per
        value would multiply the distinct sets.
        """
        said_by: dict[str, set[str]] = defaultdict(set)
        if settled["inferred"]["status"] == CONFLICT:
            said_by[INFERENCE] = set()
            for entry in settled["evidence"]:
                if entry.get("marker") == CONFLICT_MARKER:
                    said_by[INFERENCE].update(entry.get("competing_values") or ())
        elif own is not None:
            said_by[INFERENCE].add(own)
        for claim in said.claims:
            if claim.get("claim_state") == UNMAPPED:
                said_by[f"{claim['source_type']} (unreviewed)"].add(str(claim.get("raw_value")))
            elif (declared := declaration(claim)) is not None:
                said_by[claim["source_type"]].add(declared)
        said_by[SOURCE_DERIVATION_INHERITANCE].update(_inherited_declarations(settled))
        if not said_by[SOURCE_DERIVATION_INHERITANCE]:
            del said_by[SOURCE_DERIVATION_INHERITANCE]
        return tuple(sorted((name, tuple(sorted(values))) for name, values in said_by.items()))

    @staticmethod
    def _inference_outcome(slot: str, settled: dict, said: SlotEvidence, own: str | None, lineage: set[str]) -> str:
        """Inference's outcome; ``lineage`` (the slot's inherited declarations) counts only toward disagreeing."""
        if settled["inferred"]["status"] == CONFLICT:
            return DISAGREED
        if own is None:
            return SILENT
        others = {d for c in said.claims if (d := declaration(c)) is not None}
        # Agreement is nesting over every declaration, as resolve_slot has it (#473): a
        # source's CHM13 agrees with inference's T2T-CHM13v2.0, but not when another
        # source's sibling release, or a disagreeing or mixed inheritance (#571), makes the
        # slot a conflict. Agreeing with an inherited value alone is not a source agreeing.
        if _disagree(slot, others | {own}, lineage):
            return DISAGREED
        if others:
            return AGREED
        spoke = said.unreviewed or said.no_claim or any(c.get("status") == NOT_CLASSIFIED for c in said.claims)
        return UNCONFIRMED if spoke else ADDED

    @staticmethod
    def _source_outcome(slot: str, said: SlotEvidence, own: str | None, source_type: str, lineage: set[str]) -> str:
        """A source's outcome; ``lineage`` (the slot's inherited declarations) counts only toward disagreeing."""
        mine = [c for c in said.claims if c.get("source_type") == source_type and declaration(c) is not None]
        if mine:
            declared = {d for c in mine if (d := declaration(c)) is not None}
            others = {
                d for c in said.claims if c.get("source_type") != source_type and (d := declaration(c)) is not None
            }
            if own is not None:
                others.add(own)
            # Agreement is nesting over every declaration, as resolve_slot has it (#473).
            if _disagree(slot, declared | others, lineage):
                return DISAGREED
            # The same rule the slot's category uses: verbatim if any claim is verbatim.
            return MATCH if any(not is_harmonized(c) for c in mine) else HARMONIZED
        if source_type in said.unreviewed:
            return UNREVIEWED
        if source_type in said.no_claim or any(
            c.get("source_type") == source_type and c.get("status") == NOT_CLASSIFIED for c in said.claims
        ):
            return NO_CLAIM
        return SILENT

    def to_dict(self) -> dict:
        def plain(d):
            return {k: plain(v) for k, v in sorted(d.items())} if isinstance(d, dict) else d

        conflict_rate = {
            dataset: {
                slot: round(sum(counts.get(k, 0) for k in CONFLICT_CATEGORIES) / self.files[dataset], 6)
                if self.files[dataset]
                else 0.0
                for slot, counts in sorted(per_slot.items())
            }
            for dataset, per_slot in sorted(self.slots.items())
        }
        return {
            "files": dict(sorted(self.files.items())),
            "slots": plain(self.slots),
            "values": plain(self.values),
            "inputs": plain(self.inputs),
            "added_over_published": plain(self.added_over_published),
            "filled_over_inference": plain(self.filled_over_inference),
            "conflict_rate": conflict_rate,
            "conflicts": {
                dataset: {
                    slot: {
                        category: [
                            {"inputs": {name: list(values) for name, values in competing}, "files": n}
                            for competing, n in sorted(tally.items(), key=lambda item: (-item[1], item[0]))
                        ]
                        for category, tally in sorted(per_category.items())
                    }
                    for slot, per_category in sorted(per_slot.items())
                }
                for dataset, per_slot in sorted(self.conflicts.items())
            },
            "lineage": {
                "sources": plain(self.lineage_counts),
                "content_steps": self.content_steps,
                "steps": plain(self.steps),
                "conflicts": {
                    dataset: {kind: dict(tally) for kind, tally in sorted(per_kind.items())}
                    for dataset, per_kind in sorted(self.step_conflicts.items())
                },
                "generic_only": dict(sorted(self.generic_only.items())),
                "misfits": [
                    {"dataset": d, "activity": a, "problem": p, "detail": x, "files": n}
                    for (d, a, p, x), n in sorted(self.misfits.items())
                ],
            },
            "inheritance": plain(self.inheritance),
            "inheritance_by_role": plain(self.inheritance_by_role),
            "coverage": {
                source_type: {
                    dataset or EVERY_DATASET: sorted(slot for d, slot in pairs if d == dataset)
                    for dataset in sorted({d for d, _ in pairs}, key=lambda d: d or "")
                }
                for source_type, pairs in sorted(self.coverage.items())
            },
        }


def _inherited_declarations(settled: dict) -> set[str]:
    """What a settled slot's inherited claims declare: values, ``not_applicable``, or ``mixed``."""
    return {
        declaration(e) or MIXED
        for e in settled["evidence"]
        if e.get("source_type") == SOURCE_DERIVATION_INHERITANCE and "parent_keys" in e
    }


def _disagree(slot: str, declared: set[str], lineage: set[str]) -> bool:
    """Whether ``declared`` and the inherited ``lineage`` fail to nest, as :func:`settle` judges them (mixed included)."""
    if MIXED in lineage:
        return True
    return most_specific(slot, declared | lineage) is None


# --- the stage ----------------------------------------------------------------------


class _Graph:
    """The first pass's memory: every record's own settled answers, and each child's step and own declarations.

    ``base`` holds a :class:`reconcile_inherit.Settled` per record key, ``steps`` a
    :class:`reconcile_inherit.Step` per record with a ``generated_by``. A child also keeps,
    per carried slot in ``carried`` order, what :func:`settle` needs to weigh an inherited
    declaration with its own (:func:`own_inputs`, and whether the published source spoke
    unreviewed). Most records share one of a few answers, so each distinct one is held once
    (``intern``) and a record keeps a reference.
    """

    def __init__(self) -> None:
        self.carried = activities.carried()
        self.base: dict[str, Settled] = {}
        self.steps: dict[str, Step] = {}
        self.own: dict[str, tuple[tuple[bool, frozenset[str], bool], ...]] = {}
        self.intern = Interner()

    def add(self, identity: str, record: dict, record_slots: dict[str, SlotEvidence], step: dict | None) -> None:
        classifications = record.get("classifications") or {}
        answers: dict[str, tuple[str, str | None]] = {}
        own = []
        build = inferred_reference = None
        for slot in self.carried:
            entry = classifications.get(slot) or {}
            said = record_slots.get(slot, NO_EVIDENCE)
            inferred = {"value": entry.get("value"), "status": entry.get("status")}
            inference_conflict, declared = own_inputs(inferred, said.claims)
            unreviewed = SOURCE_PUBLISHED_VALUE in said.unreviewed
            answers[slot] = self.intern(settle(slot, inference_conflict, declared, False, unreviewed))
            own.append(self.intern((inference_conflict, declared, unreviewed)))
            if slot == REFERENCE_ASSEMBLY and inferred["status"] == CLASSIFIED:
                detail = field_detail(record, slot).get("build")
                # Only a resolved build passes on: observations alone (a header's reference name)
                # are the file's own, so a build with neither base nor version is none.
                pair = (detail.get("base"), detail.get("version")) if isinstance(detail, dict) else (None, None)
                own_build = self.intern(pair) if pair != (None, None) else None
                inferred_reference = self.intern(((inferred["status"], inferred["value"]), own_build))
                build = reference_build(answers[slot], inferred_reference, [])
        self.base[identity] = self.intern.settled(answers, build, inferred_reference)
        if step is not None:
            self.steps[identity] = Step.of(step, self.intern)
            self.own[identity] = self.intern(tuple(own))

    def resolve(self, identity: str, slot: str, inherited: list[Inherited]) -> tuple[str, str | None]:
        """A child's answer for ``slot`` with ``inherited`` weighed in; status ``mixed`` where only a mixed one spoke."""
        inference_conflict, declared, unreviewed = self.own[identity][self.carried.index(slot)]
        values = {i.declared for i in inherited if i.declared != MIXED}
        mixed = any(i.declared == MIXED for i in inherited)
        answer = settle(slot, inference_conflict, declared | values, mixed, unreviewed)
        return (MIXED, None) if mixed and answer == (NOT_CLASSIFIED, None) else answer


def reconcile_run(
    run_dir: Path,
    metadata: Path,
    evidence_root: Path | None = DEFAULT_SOURCE_EVIDENCE_ROOT,
    table: ValueMap | None = None,
    lineage_root: Path | None = None,
    activity_table: ActivityMap | None = None,
) -> dict:
    """Reconcile one stored run into ``<run>/reconciled/`` and return its report; ``evidence_root=None`` excludes all evidence.

    The inference files are read and never written. The output is written to a staging
    directory and renamed into place only when complete, so a failure leaves any earlier
    reconciled artifact recoverable: untouched, or moved aside as ``reconciled.replaced`` if
    the process dies between the two renames of the swap, and restored by the next run. No request is made and no written byte depends on the
    clock — the evidence report printed on the way in shows file ages, and nothing
    written does — so the same run, evidence, lineage, translation table, activity map and
    input paths write the same bytes (criterion 16); both tables' sha256 are in the envelope
    and the report. The report echoes the input path as given and evidence paths
    relative to ``evidence_root``.

    Lineage (#577, :mod:`reconcile_lineage`) is read from ``lineage_root``, by default the
    ``lineage_evidence`` directory beside ``evidence_root``, translated through
    ``activity_table`` (the bundled activity map by default), and merged per record with
    inference's own step (``edges.merge_steps``) into the reconciled ``generated_by``. A
    record no lineage names keeps inference's step as it is. ``evidence_root=None``
    excludes lineage too, and inheritance still crosses the steps inference wrote (6.6).

    Inheritance (#571, :mod:`reconcile_inherit`) needs every parent's answer before its
    child is written, and the records come file by file, so inheritance reads the run twice,
    after the join's own scan (made when there is evidence or lineage to place). The
    first pass settles each record's own answer and step and keeps, per record, only its
    settled answer for the carried slots (and, for a child, what its own declarations
    are), each distinct one held once. The second settles each record again, now with its
    inherited declarations, and writes it. Refuses (``ReconcileError``) a run whose steps
    form a cycle.
    """
    if not run_dir.is_dir():
        raise ReconcileError(f"run directory not found: {run_dir}")
    out_dir = run_dir / RECONCILED_DIR
    staging = run_dir / f"{RECONCILED_DIR}.partial"
    replaced = run_dir / f"{RECONCILED_DIR}.replaced"
    # A swap interrupted after the earlier artifact was moved aside and before the new one
    # moved in leaves only `.replaced`. Put it back first, so it is readable again even if
    # this run then fails, and before anything below could delete it.
    if replaced.exists() and not out_dir.exists():
        replaced.rename(out_dir)
    envelope = load_envelope(metadata)
    key = record_key(envelope, metadata)
    repository = envelope["repository"]
    catalog = envelope.get("catalog")
    table = table if table is not None else load_value_map()
    activity_table = activity_table if activity_table is not None else load_activity_map()

    if evidence_root is None:
        applicable, skipped = [], []
        pending = PendingLineage()
    else:
        statuses = report_evidence_files(evidence_root)
        require_one_published_source(statuses, PUBLISHED_TABLES)
        applicable, skipped = select_evidence(statuses, repository, catalog)
        if lineage_root is None:
            lineage_root = evidence_root.parent / DEFAULT_LINEAGE_EVIDENCE_ROOT.name
        pending = translate_lineage(lineage_root, evidence_root, repository, catalog, activity_table)
    joined = join(applicable, run_dir, key, table, extra=pending.wanted)
    lineage = resolve_lineage(pending, joined.carriers)
    report = Report(
        coverage=joined.coverage,
        published_slots=published_slots(repository),
        lineage_counts=lineage.counts,
        content_steps=content_step_counts(run_dir),
    )

    root = evidence_root or Path()
    header = {
        "run": run_dir.name,
        "input": str(metadata),
        "repository": repository,
        "catalog": catalog,
        "evidence_excluded": evidence_root is None,
        "evidence": [ev.identity(root) for ev in applicable],
        "value_map_sha256": table.digest,
        "activity_map_sha256": activity_table.digest,
        "lineage_files": lineage.files,
    }

    # Every row must carry its own record key: joined evidence is keyed by it, so a row
    # without one could receive nothing, and two rows sharing one would both receive what
    # matched either. `make classify` fails such a run
    # (#445), but its directory is still on disk to be named here.
    def identity_of(record: dict, seen: set[str]) -> str:
        identity = record.get(key.output_field)
        if not is_key_value(identity):
            raise ValueError(
                f"{run_dir}: row {record.get('file_name')!r} has no usable {key.output_field}, the run's record "
                "key; it cannot be joined or checked for a second row"
            )
        if identity in seen:
            raise ValueError(
                f"{run_dir}: two rows share {key.output_field} {identity!r}; a run must hold one row per file (#445)"
            )
        seen.add(identity)
        return identity

    def step_of(record: dict, identity: str) -> tuple[dict | None, StepConflict | None]:
        if identity in lineage.steps:
            return merge_steps(record.get("generated_by"), lineage.steps[identity])
        return record.get("generated_by"), None

    # The first pass: each record's own settled answers, and each child's step.
    graph = _Graph()
    seen: set[str] = set()
    for _, records in iter_run_files(run_dir, strict=True):
        for record in records:
            identity = identity_of(record, seen)
            step, _ = step_of(record, identity)
            graph.add(identity, record, joined.slots.get(identity, {}), step)
    try:
        inheritance = inherit(graph.steps, graph.base.get, graph.resolve, graph.intern)
    except InheritanceCycle as exc:
        raise ReconcileError(str(exc)) from None
    del graph

    def reconciled_rows(records: list[dict]):
        for record in records:
            identity = str(record[key.output_field])
            record_slots = joined.slots.get(identity, {})
            reconciled = reconcile_record(record, record_slots, inheritance.declarations.get(identity))
            reconciled["generated_by"], conflict = step_of(record, identity)
            report.add(reconciled, record_slots)
            report.add_step(reconciled, conflict, lineage.steps.get(identity, []))
            report.add_inheritance(reconciled, inheritance.outcomes.get(identity, ()))
            yield reconciled

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    for fname, records in iter_run_files(run_dir, strict=True):
        write_reconciled_file(staging / reconciled_name(fname), header, reconciled_rows(records))

    full_report = {
        **header,
        "evidence": [ev.summary(root) for ev in applicable],
        "skipped_evidence": [{**s, "path": relative_to(s["path"], root)} for s in skipped],
        **report.to_dict(),
    }
    (staging / REPORT_FILE).write_text(json.dumps(full_report, indent=2, sort_keys=True) + "\n")
    # Swap by renames: the earlier artifact is moved aside, the new one moved in, and only
    # then the earlier one deleted. Between the two renames only `.replaced` exists, and
    # the next run restores it (above) before it would be deleted.
    if replaced.exists():
        shutil.rmtree(replaced)
    if out_dir.exists():
        out_dir.rename(replaced)
    staging.rename(out_dir)
    if replaced.exists():
        shutil.rmtree(replaced)
    return full_report


def render_summary(report: dict) -> str:
    """The report's headline numbers as plain text: the join, then each dimension's totals."""
    lines = []
    if report["evidence_excluded"]:
        lines.append(
            "Evidence excluded: the reconciled artifact concludes what inference concluded, plus what "
            "inheritance carried across the steps inference wrote."
        )
    elif not report["evidence"]:
        catalog = f" for catalog {report['catalog']}" if report["catalog"] else ""
        lines.append(f"No evidence{catalog} about {report['repository']}'s files: nothing to reconcile against.")
    for ev in report["evidence"]:
        lines.append(
            f"  {ev['source_type']:<20} {ev['dataset'] or '-':<24} {ev['table'] or '-':<28} key={ev['key']:<9} "
            f"offered={ev['offered']:>8,} "
            f"matched={ev['matched']:>8,} unmatched={ev['unmatched']:>6,} ambiguous={ev['ambiguous']:>4,}"
        )
    totals: dict[str, Counter] = defaultdict(Counter)
    for per_slot in report["slots"].values():
        for slot, counts in per_slot.items():
            totals[slot].update(counts)
    files = sum(report["files"].values())
    lines.append(f"Files: {files:,}")
    for slot in CLASSIFICATION_FIELDS:
        counts = totals.get(slot, Counter())
        parts = ", ".join(f"{k}={v:,}" for k, v in sorted(counts.items()))
        lines.append(f"  {slot:<20} {parts}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile a stored inference run with source evidence (#432).")
    parser.add_argument("--run", type=Path, default=None, help="Run directory (default: latest under output/anvil)")
    parser.add_argument(
        "--deployment",
        choices=sorted(DEPLOYMENTS),
        default=DEFAULT_DEPLOYMENT,
        help=f"Read this deployment's input envelope for the repository and catalog (default: {DEFAULT_DEPLOYMENT})",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=None,
        help="The input file the run was classified from (default: the deployment's); its envelope "
        "names the repository and catalog",
    )
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_SOURCE_EVIDENCE_ROOT)
    parser.add_argument(
        "--lineage-root",
        type=Path,
        default=None,
        help="Lineage evidence (default: lineage_evidence beside the evidence root)",
    )
    parser.add_argument(
        "--no-evidence",
        action="store_true",
        help="Exclude all source evidence and lineage (--lineage-root is then not read): the reconciled "
        "artifact concludes what inference did, plus what inheritance carries across the steps inference "
        "wrote (6.6)",
    )
    args = parser.parse_args(argv)
    # A run's output root is prod's until a deployment names its own (#480), so the latest
    # run under it is only prod's; another deployment must say which run it means.
    if args.run is None and args.deployment != DEFAULT_DEPLOYMENT:
        parser.error(
            f"--deployment {args.deployment} needs --run: output/anvil holds {DEFAULT_DEPLOYMENT}'s runs (#480)"
        )
    try:
        run_dir = args.run or find_latest_run(Path("output/anvil"))
        metadata = args.metadata or DEPLOYMENTS[args.deployment].input_file
        report = reconcile_run(
            run_dir, metadata, None if args.no_evidence else args.evidence_root, lineage_root=args.lineage_root
        )
    except (ReconcileError, ValueError, FileNotFoundError) as exc:
        print(f"reconcile refused: {exc}", file=sys.stderr)
        return 1
    print(f"Reconciled {run_dir} -> {run_dir / RECONCILED_DIR}")
    print(render_summary(report))
    return 0
