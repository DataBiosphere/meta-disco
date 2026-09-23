"""Reconcile: a stored inference run plus source evidence, settled by agreement (#432).

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
record key (``pipeline.SOURCE_RECORD_KEYS``), never a hard-coded field.

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
from dataclasses import dataclass, field
from pathlib import Path

from .deployments import DEFAULT_DEPLOYMENT, DEPLOYMENTS
from .models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    CONFLICT,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_EXTERNAL_GROUND_TRUTH,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_METADATA,
    UNMAPPED,
)
from .output_utils import (
    RECONCILED_DIR,
    find_latest_run,
    iter_records,
    iter_run_files,
    reconciled_name,
    write_reconciled_file,
)
from .pipeline import ANVIL_REPOSITORY, PUBLISHED_TABLES, RecordKey, is_key_value, load_envelope, record_key
from .records import JOIN_KEY_OUTPUT_FIELDS
from .rule_engine import make_claim
from .schema.classification_model import EvidenceFileEnvelope
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

# Report labels, never stored on a record.
#
# Per input, scored against the other inputs' declarations for the same slot. A source:
# match or harmonized (it declared, and no other input declared differently), disagreed
# (another input declared differently), unreviewed (its value has no authored row),
# no_claim (its value's authored row declares nothing for the slot, or declares
# `not_classified`, which is no answer), silent. Inference: agreed (a source declared
# the same), added (every source was silent), unconfirmed (no source declared a value,
# but one spoke — unreviewed or no_claim — so it was not silent), disagreed (another
# input declared differently, or its own rules conflicted), silent.
#
# Per slot, exactly one of: filled_by_<source> or filled_by_<source>_harmonized for the
# first source in SOURCE_PRECEDENCE that declared the delivered value — verbatim before
# harmonized — else filled_by_inference; published_unreviewed (`not_classified` because the
# published source spoke with a value no authored row reads — work to do, not a
# challenge); one of three kinds of `conflict`, first match wins: conflict_inference
# (inference's own rules disagreed), conflict_published (the published source declared a
# value another input disagrees with, or spoke with an unreviewed value beside another
# input's), conflict_sources (inference and the other sources, or those sources among
# themselves, disagreed); or the slot's other status (`not_applicable`, `not_classified`).
# Precedence only attributes a value every declaring input agreed on; it never picks a
# value (contract 6.8). Whether inference agreed is its own outcome, in `inputs`.
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
PUBLISHED_UNREVIEWED = "published_unreviewed"
CONFLICT_INFERENCE = "conflict_inference"
CONFLICT_PUBLISHED = "conflict_published"
CONFLICT_SOURCES = "conflict_sources"

# The order a delivered value is attributed in, with each source's name in the report:
# what the repository publishes, then what its submitters wrote, then other catalogs.
SOURCE_PRECEDENCE = (
    (SOURCE_PUBLISHED_VALUE, "published"),
    (SOURCE_REPOSITORY_METADATA, "submitter"),
    (SOURCE_EXTERNAL_GROUND_TRUTH, "external"),
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


def resolve_slot(inferred: dict, source_claims: Iterable[dict], published_unreviewed: bool) -> tuple[str, str | None]:
    """The reconciled ``(status, value)`` of one slot of one file, from inference's ``{value, status}``.

    In order:

    1. Inference itself concluded ``conflict``: the conflict stands, whatever a source
       says — agreeing with one of two disagreeing rules is not resolving them, which 4.7
       reserves for a curator rule (open question 1, decided 2026-09-22).
    2. The declarations differ — two values, or a value beside ``not_applicable`` (4.6):
       ``conflict``.
    3. The published source spoke with a value no authored row reads (unreviewed): a
       ``conflict`` if any other input declared something, else ``not_classified`` —
       missing work, not a challenge.
    4. One value: ``classified``. Otherwise ``not_applicable`` if anyone declared it, and
       ``not_classified`` if nobody declared anything. ``not_classified`` never conflicts
       and yields to ``not_applicable`` (4.6).

    ``value`` is null unless the status is ``classified``.
    """
    if inferred["status"] == CONFLICT:
        return CONFLICT, None
    declared = {d for d in map(declaration, source_claims) if d is not None}
    own = declaration(inferred)
    if own is not None:
        declared.add(own)
    if len(declared) > 1:
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
            "path": _relative(self.path, root),
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


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


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
        if catalog is not None and envelope.target.version != catalog:
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
    # Per source type, the (dataset, slot) pairs its evidence speaks to: a line's field,
    # and every slot a row it selected declares (3.10). Dataset None for a file scoped to
    # no dataset, which speaks to that slot in every dataset.
    coverage: dict[str, set[tuple[str | None, str]]]


# A key a line is matched by: the output-row field, the dataset the envelope scopes the
# join to (None when it names none), and the value.
_Key = tuple[str, str | None, str]


def join(evidence: list[EvidenceFile], run_dir: Path, key: RecordKey, table: ValueMap) -> Joined:
    """Attach each evidence line whose key value exactly one record carries to that record, and translate it.

    The join runs within the envelope's target dataset when it names one — the scope
    ``EvidenceTarget.dataset`` declares — matched against the record's ``dataset_title``.
    A line whose key no record carries is unmatched; one whose key several records carry
    is ambiguous and attaches to none, and the report names every carrier for the first
    few such keys per file. ``evidence`` is updated in place with each file's counts.

    The evidence is read into memory first — it is small beside the run — and then one
    pass over the run's records finds which records carry each key. Refuses
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
    # The (field, dataset) scopes to look up, grouped by the dataset they need, so a
    # record is looked up only under its own dataset's scopes and the unscoped ones.
    scopes: dict[str | None, set[str]] = defaultdict(set)
    for ev in evidence:
        scopes[ev.dataset].add(ev.record_field)
    unscoped = tuple(scopes.pop(None, ()))

    carriers: dict[_Key, list[str]] = defaultdict(list)
    if wanted:
        for record in iter_records(run_dir):
            title = record.get("dataset_title")
            scoped = [(f, title) for f in scopes.get(title, ())] if isinstance(title, str) else []
            for record_field, dataset in scoped + [(f, None) for f in unscoped]:
                value = record.get(record_field)
                if not is_key_value(value):
                    continue
                found = (record_field, dataset, value)
                if found in wanted:
                    identity = record.get(key.output_field)
                    if not is_key_value(identity):
                        raise ReconcileError(
                            f"a record carrying {record_field}={value!r} has no usable {key.output_field}, "
                            "the run's record key; it cannot be named"
                        )
                    carriers[found].append(identity)

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

    return Joined(slots=slots, coverage=dict(coverage))


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


def reconcile_record(record: dict, record_slots: dict[str, SlotEvidence]) -> dict:
    """The reconciled record for one inference record: same identity, each slot settled.

    Each slot keeps inference's evidence as it is, adds the source claims after it, and
    gains ``inferred`` (what inference concluded, which its evidence alone cannot rebuild
    without re-running tier resolution) and ``use``. Inference's ``build`` stays only
    while the slot still concludes inference's value — it describes that value. Keys of
    ``classifications`` that are not slots (a producer's scalar hints) pass through.

    Raises ``ValueError`` on a record missing a slot or a slot's ``status``: every
    producer writes all five, so one without is damaged, and settling the rest would
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
            raise ValueError(f"record {record.get('file_name')!r} has no {slot} slot with a status; it is damaged")
        said = record_slots.get(slot, NO_EVIDENCE)
        inferred = {"value": entry.get("value"), "status": entry["status"]}
        status, value = resolve_slot(inferred, said.claims, SOURCE_PUBLISHED_VALUE in said.unreviewed)
        settled: dict = {
            "value": value,
            "status": status,
            "use": use_for(status),
            "inferred": inferred,
            "evidence": list(entry.get("evidence") or []) + said.claims,
        }
        if "build" in entry and (status, value) == (inferred["status"], inferred["value"]):
            settled["build"] = entry["build"]
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
    # source, which speaks to that slot in that dataset, said nothing for the file: metadata
    # added over what the repository publishes. Kept apart from `slots`, whose categories
    # sum to the file count; this one overlaps them.
    added_over_published: dict = field(default_factory=lambda: defaultdict(Counter))
    inputs: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(Counter))))
    # Per (dataset, slot), the source types whose evidence speaks to it: only those are
    # scored there.
    _covering: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)

    def covering(self, dataset: str, slot: str) -> tuple[str, ...]:
        """The source types that speak to ``slot`` in ``dataset``.

        Read off the evidence lines, except for the published source: it is one table with
        the same columns in every dataset of its repository (contract 7.12,
        ``pipeline.PUBLISHED_TABLES``), and its importer skips an empty cell and writes no
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
            self.slots[dataset][slot][self._category(settled, said)] += 1
            per_input = self.inputs[dataset][slot]
            per_input[INFERENCE][self._inference_outcome(settled, said, own)] += 1
            for source_type in covering:
                outcome = self._source_outcome(said, own, source_type)
                per_input[source_type][outcome] += 1
                if source_type == SOURCE_PUBLISHED_VALUE and outcome == SILENT and settled["status"] == CLASSIFIED:
                    self.added_over_published[dataset][slot] += 1

    @staticmethod
    def _category(settled: dict, said: SlotEvidence) -> str:
        status = settled["status"]
        if status == NOT_CLASSIFIED and SOURCE_PUBLISHED_VALUE in said.unreviewed:
            return PUBLISHED_UNREVIEWED
        if status == CONFLICT:
            if settled["inferred"]["status"] == CONFLICT:
                return CONFLICT_INFERENCE
            published = any(
                c["source_type"] == SOURCE_PUBLISHED_VALUE and declaration(c) is not None for c in said.claims
            )
            return CONFLICT_PUBLISHED if published or SOURCE_PUBLISHED_VALUE in said.unreviewed else CONFLICT_SOURCES
        if status != CLASSIFIED:
            return status
        for source_type, name in SOURCE_PRECEDENCE:
            declaring = [c for c in said.claims if c["source_type"] == source_type and declaration(c) is not None]
            if declaring:
                verbatim = any(not is_harmonized(c) for c in declaring)
                return f"filled_by_{name}" if verbatim else f"filled_by_{name}_harmonized"
        return FILLED_BY_INFERENCE

    @staticmethod
    def _inference_outcome(settled: dict, said: SlotEvidence, own: str | None) -> str:
        if settled["inferred"]["status"] == CONFLICT:
            return DISAGREED
        if own is None:
            return SILENT
        others = {declaration(c) for c in said.claims} - {None}
        if others - {own}:
            return DISAGREED
        if own in others:
            return AGREED
        spoke = said.unreviewed or said.no_claim or any(c.get("status") == NOT_CLASSIFIED for c in said.claims)
        return UNCONFIRMED if spoke else ADDED

    @staticmethod
    def _source_outcome(said: SlotEvidence, own: str | None, source_type: str) -> str:
        mine = [c for c in said.claims if c.get("source_type") == source_type and declaration(c) is not None]
        if mine:
            declared = {declaration(c) for c in mine}
            others = {declaration(c) for c in said.claims if c.get("source_type") != source_type} | {own}
            if len(declared) > 1 or (others - {None}) - declared:
                return DISAGREED
            return HARMONIZED if any(is_harmonized(c) for c in mine) else MATCH
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

        conflicts = (CONFLICT_INFERENCE, CONFLICT_PUBLISHED, CONFLICT_SOURCES)
        conflict_rate = {
            dataset: {
                slot: round(sum(counts.get(k, 0) for k in conflicts) / self.files[dataset], 6)
                if self.files[dataset]
                else 0.0
                for slot, counts in sorted(per_slot.items())
            }
            for dataset, per_slot in sorted(self.slots.items())
        }
        return {
            "files": dict(sorted(self.files.items())),
            "slots": plain(self.slots),
            "inputs": plain(self.inputs),
            "added_over_published": plain(self.added_over_published),
            "conflict_rate": conflict_rate,
            "coverage": {
                source_type: {
                    dataset or "(every dataset)": sorted(slot for d, slot in pairs if d == dataset)
                    for dataset in sorted({d for d, _ in pairs}, key=lambda d: d or "")
                }
                for source_type, pairs in sorted(self.coverage.items())
            },
        }


# --- the stage ----------------------------------------------------------------------


def reconcile_run(
    run_dir: Path,
    metadata: Path,
    evidence_root: Path | None = DEFAULT_SOURCE_EVIDENCE_ROOT,
    table: ValueMap | None = None,
) -> dict:
    """Reconcile one stored run into ``<run>/reconciled/`` and return its report; ``evidence_root=None`` excludes all evidence.

    The inference files are read and never written. The output is written to a staging
    directory and renamed into place only when complete, so a failure leaves any earlier
    reconciled artifact recoverable: untouched, or moved aside as ``reconciled.replaced`` if
    the process dies between the two renames of the swap, and restored by the next run. No request is made and no written byte depends on the
    clock — the evidence report printed on the way in shows file ages, and nothing
    written does — so the same run, evidence and input paths write the same bytes
    (criterion 16). The report echoes the input path as given and evidence paths
    relative to ``evidence_root``.
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

    if evidence_root is None:
        applicable, skipped = [], []
    else:
        statuses = report_evidence_files(evidence_root)
        require_one_published_source(statuses, PUBLISHED_TABLES)
        applicable, skipped = select_evidence(statuses, repository, catalog)
    joined = join(applicable, run_dir, key, table)
    report = Report(coverage=joined.coverage, published_slots=published_slots(repository))

    root = evidence_root or Path()
    header = {
        "run": run_dir.name,
        "input": str(metadata),
        "repository": repository,
        "catalog": catalog,
        "evidence_excluded": evidence_root is None,
        "evidence": [ev.identity(root) for ev in applicable],
    }

    # Every row must carry its own record key: joined evidence is keyed by it, so a row
    # without one could receive nothing, and two rows sharing one would both receive what
    # matched either. `make classify` fails such a run
    # (#445), but its directory is still on disk to be named here.
    seen: set[str] = set()

    def settle(records: list[dict]):
        for record in records:
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
            record_slots = joined.slots.get(identity, {})
            reconciled = reconcile_record(record, record_slots)
            report.add(reconciled, record_slots)
            yield reconciled

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    for fname, records in iter_run_files(run_dir, strict=True):
        write_reconciled_file(staging / reconciled_name(fname), header, settle(records))

    full_report = {
        **header,
        "evidence": [ev.summary(root) for ev in applicable],
        "skipped_evidence": [{**s, "path": _relative(s["path"], root)} for s in skipped],
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
        lines.append("Evidence excluded: the reconciled artifact concludes what inference concluded.")
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
        "--no-evidence",
        action="store_true",
        help="Exclude all source evidence: the reconciled artifact then concludes what inference did (6.6)",
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
        report = reconcile_run(run_dir, metadata, None if args.no_evidence else args.evidence_root)
    except (ReconcileError, ValueError, FileNotFoundError) as exc:
        print(f"reconcile refused: {exc}", file=sys.stderr)
        return 1
    print(f"Reconciled {run_dir} -> {run_dir / RECONCILED_DIR}")
    print(render_summary(report))
    return 0
