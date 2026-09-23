"""Reconcile: a stored inference run plus source evidence, settled by agreement (#432).

The third stage of a run (contract 6.1): **infer → read sources → reconcile**. Reading
sources is the join below and lives inside this stage; its per-source counts are a line
of the report, not a stage of their own (6.7). Reconcile reads a stored run and never
re-infers or fetches, so answering a review item costs a reconcile, not a corpus run
(6.4). It writes its own artifact beside the inference output and never touches it
(6.3): one NDJSON file per inference file under ``<run>/reconciled/`` (6.11), with an
envelope on line 1, plus ``reconcile_report.json``.

**The join** is an equality lookup on the key each evidence envelope names
(``target_key``), against that field of our output records. A line whose key value is
carried by exactly one record attaches to it; by two or more, to none — it is counted
ambiguous and both identities are named (the #371 problem, seen from the evidence side).
An evidence file none of whose lines match is an error naming its source and dataset:
silence is not success (5.3). The record's identity in the report is the repository's
record key (``pipeline.SOURCE_RECORD_KEYS``), never a hard-coded field.

**Which evidence applies** is read from the input envelope the run was classified from:
a file applies when its ``target.system`` is the envelope's ``repository``. Where the
envelope names a ``catalog``, the file's ``target.version`` must equal it or reconcile
refuses; a repository with no catalog (HPRC, which will never have one) is not checked
against one. That the stored run was actually made from this input is not provable
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
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, fields
from pathlib import Path

from .deployments import DEFAULT_DEPLOYMENT, DEPLOYMENTS
from .models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    CONFLICT,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_PUBLISHED_VALUE,
)
from .output_utils import (
    CLASSIFICATION_FILES,
    RECONCILED_DIR,
    RECONCILED_ENVELOPE_KEY,
    find_latest_run,
    reconciled_name,
)
from .pipeline import PUBLISHED_TABLES, load_envelope, record_key
from .records import OutputRecord
from .schema.classification_model import EvidenceFileEnvelope
from .source_evidence import (
    DEFAULT_SOURCE_EVIDENCE_ROOT,
    EvidenceEntry,
    discover,
    iter_evidence,
    list_cell,
    read_envelope,
    report_evidence_files,
    require_one_published_source,
)
from .value_map import ValueMap, claims_from, load_value_map

REPORT_FILE = "reconcile_report.json"

# The per-slot instruction to the indexer (#432, second 2026-09-22 amendment).
USE_META_DISCO = "meta_disco"
USE_PUBLISHED = "published"

INFERENCE = "inference"

# Per-input outcomes, scored in the report and never stored on a record.
MATCH = "match"
HARMONIZED = "harmonized"
UNREVIEWED = "unreviewed"
SILENT = "silent"
AGREED = "agreed"
ADDED = "added"

# Slot categories in the report. `missing_work` is a `not_classified` slot the published
# source spoke to with a value no authored row reads — work to do, not a challenge.
AGREED_SLOT = "agreed"
FILLED = "filled"
INFERENCE_ONLY = "inference_only"
MISSING_WORK = "missing_work"

# The fields of our output records an envelope's `target_key` may name.
RECORD_FIELDS = frozenset(f.name for f in fields(OutputRecord))


class ReconcileError(Exception):
    """A refusal: the inputs cannot be reconciled as given, and nothing was written."""


# --- resolution ---------------------------------------------------------------------


def declaration(claim: dict) -> str | None:
    """What a claim declares for resolution: its value, ``not_applicable``, or None.

    ``not_classified`` declares no answer (4.6), so it is None like a claim declaring nothing.
    """
    if claim.get("value") is not None:
        return claim["value"]
    if claim.get("status") == NOT_APPLICABLE:
        return NOT_APPLICABLE
    return None


def inferred_declaration(status: str, value: str | None) -> str | None:
    """Inference's conclusion as a declaration: its value, ``not_applicable``, or None."""
    if status == CLASSIFIED:
        return value
    if status == NOT_APPLICABLE:
        return NOT_APPLICABLE
    return None


def resolve_slot(
    inferred_status: str,
    inferred_value: str | None,
    source_claims: Iterable[dict],
    published_unreviewed: bool,
) -> tuple[str, str | None]:
    """The reconciled ``(status, value)`` of one slot of one file.

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
    if inferred_status == CONFLICT:
        return CONFLICT, None
    declared = {d for d in (declaration(c) for c in source_claims) if d is not None}
    own = inferred_declaration(inferred_status, inferred_value)
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

    def summary(self, root: Path) -> dict:
        return {
            "path": _relative(self.path, root),
            "source_type": self.source_type,
            "source": self.envelope.source.repository,
            "dataset": self.dataset,
            "table": self.envelope.source.table,
            "source_version": self.envelope.source_version,
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
    paths: Iterable[Path], repository: str, catalog: str | None
) -> tuple[list[EvidenceFile], list[dict]]:
    """The evidence files that speak to this repository, and the ones that do not.

    Refuses (``ReconcileError``) a file for this repository whose ``target_key`` is not a
    field of our records (criterion 5), or whose ``target.version`` is not the input's
    catalog when the input names one. A file about another system is skipped, not refused:
    it is about files this run does not hold.
    """
    applicable: list[EvidenceFile] = []
    skipped: list[dict] = []
    for path in paths:
        envelope = read_envelope(path)
        if envelope.target.system != repository:
            skipped.append({"path": str(path), "target_system": envelope.target.system})
            continue
        key = str(envelope.target_key)
        if key not in RECORD_FIELDS:
            raise ReconcileError(
                f"{path}: target_key {key!r} is not a field of our output records "
                f"({sorted(RECORD_FIELDS)}); nothing to join it against"
            )
        if catalog is not None and envelope.target.version != catalog:
            raise ReconcileError(
                f"{path}: evidence resolved against catalog {envelope.target.version!r}, but the input "
                f"names {catalog!r}; re-import the evidence against {catalog!r}"
            )
        applicable.append(EvidenceFile(path, envelope))
    return applicable, skipped


@dataclass
class SlotEvidence:
    """What the sources said about one slot of one file."""

    claims: list[dict] = field(default_factory=list)
    # Source types that spoke to the slot with a value no authored row reads.
    unreviewed: set[str] = field(default_factory=set)


@dataclass
class Joined:
    """The join's result: per record identity, per slot, what the sources said."""

    slots: dict[str, dict[str, SlotEvidence]]
    files: list[EvidenceFile]
    # Per source type, the datasets its evidence covers.
    coverage: dict[str, set[str]]


def join(
    evidence: list[EvidenceFile], run_dir: Path, identity_field: str, table: ValueMap, max_examples: int = 5
) -> Joined:
    """Attach every evidence line to the one record carrying its key value, and translate it.

    Two passes: the evidence is read into memory keyed by ``(target_key, value)`` — it is
    a few hundred thousand lines, where the run is millions of evidence entries across
    ~2 GB — then one pass over the run's records finds which records carry each key value.
    """
    wanted: dict[tuple[str, str], list[tuple[int, EvidenceEntry]]] = defaultdict(list)
    for n, ev in enumerate(evidence):
        for entry in iter_evidence(ev.path):
            ev.offered += 1
            wanted[(ev.target_key, entry.target_key_value)].append((n, entry))
    key_fields = {ev.target_key for ev in evidence}

    carriers: dict[tuple[str, str], list[str]] = defaultdict(list)
    if wanted:
        for record in iter_run_records(run_dir):
            for key_field in key_fields:
                value = record.get(key_field)
                if isinstance(value, str) and (key_field, value) in wanted:
                    carriers[(key_field, value)].append(str(record.get(identity_field)))

    slots: dict[str, dict[str, SlotEvidence]] = defaultdict(lambda: defaultdict(SlotEvidence))
    for (key_field, value), lines in wanted.items():
        found = carriers.get((key_field, value), [])
        for n, entry in lines:
            ev = evidence[n]
            if not found:
                ev.unmatched += 1
                if len(ev.unmatched_examples) < max_examples and value not in ev.unmatched_examples:
                    ev.unmatched_examples.append(value)
                continue
            if len(found) > 1:
                ev.ambiguous += 1
                if len(ev.ambiguous_examples) < max_examples:
                    ev.ambiguous_examples.append({key_field: value, identity_field: sorted(found)})
                continue
            ev.matched += 1
            _translate(slots[found[0]], entry, ev, table)

    for ev in evidence:
        if ev.offered and not ev.matched:
            raise ReconcileError(
                f"{ev.path}: none of the {ev.offered:,} lines of {ev.envelope.source.repository} "
                f"{ev.dataset} ({ev.source_type}, key {ev.target_key}) matched a record of the run — "
                f"silence is not success (contract 5.3)"
            )

    coverage: dict[str, set[str]] = defaultdict(set)
    for ev in evidence:
        if ev.dataset is not None:
            coverage[ev.source_type].add(ev.dataset)
    return Joined(slots=slots, files=evidence, coverage=dict(coverage))


def _translate(record_slots: dict[str, SlotEvidence], entry: EvidenceEntry, ev: EvidenceFile, table: ValueMap) -> None:
    row = table.select(entry.field, entry.raw_value, entry.source.name, entry.source.dataset)
    if row is None or not row.authored:
        record_slots[entry.field].unreviewed.add(ev.source_type)
        return
    for slot, claim in claims_from(entry, ev.source_type, table, join_key=ev.target_key):
        existing = record_slots[slot].claims
        if claim not in existing:
            existing.append(claim)


# --- the run ------------------------------------------------------------------------


def iter_run_records(run_dir: Path) -> Iterator[dict]:
    """Every record of the run's inference files, one file loaded at a time."""
    for _, records in iter_run_files(run_dir):
        yield from records


def iter_run_files(run_dir: Path) -> Iterator[tuple[str, list[dict]]]:
    """``(file name, records)`` for each inference file the run holds, in registry order."""
    for fname in CLASSIFICATION_FILES:
        path = run_dir / fname
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        records = data.get("classifications", []) if isinstance(data, dict) else data
        yield fname, [r for r in records if isinstance(r, dict)]


def reconcile_record(record: dict, record_slots: dict[str, SlotEvidence] | None) -> dict:
    """The reconciled record for one inference record: same identity, each slot settled.

    Each slot keeps inference's evidence as it is, adds the source claims after it, and
    gains ``inferred`` (what inference concluded, which its evidence alone cannot rebuild
    without re-running tier resolution) and ``use``. Inference's ``build`` stays only
    while the slot still concludes inference's value — it describes that value. Keys of
    ``classifications`` that are not slots (a producer's scalar hints) pass through.
    """
    out = dict(record)
    classifications = dict(record.get("classifications") or {})
    for slot in CLASSIFICATION_FIELDS:
        inferred = classifications.get(slot)
        if not isinstance(inferred, dict):
            continue
        said = (record_slots or {}).get(slot) or SlotEvidence()
        status, value = resolve_slot(
            inferred["status"],
            inferred.get("value"),
            said.claims,
            SOURCE_PUBLISHED_VALUE in said.unreviewed,
        )
        settled: dict = {
            "value": value,
            "status": status,
            "use": use_for(status),
            "inferred": {"value": inferred.get("value"), "status": inferred["status"]},
            "evidence": list(inferred.get("evidence") or []) + said.claims,
        }
        if "build" in inferred and value == inferred.get("value") and status == inferred["status"]:
            settled["build"] = inferred["build"]
        classifications[slot] = settled
    out["classifications"] = classifications
    return out


# --- the report ---------------------------------------------------------------------


@dataclass
class Report:
    """Counts per dataset and dimension: how each slot settled, and how each input did."""

    coverage: dict[str, set[str]]
    source_types: tuple[str, ...]
    files: Counter = field(default_factory=Counter)
    slots: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Counter)))
    inputs: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(Counter))))

    def add(self, original: dict, reconciled: dict, record_slots: dict[str, SlotEvidence] | None) -> None:
        dataset = str(original.get("dataset_title") or "")
        self.files[dataset] += 1
        for slot in CLASSIFICATION_FIELDS:
            settled = reconciled["classifications"].get(slot)
            if not isinstance(settled, dict):
                continue
            said = (record_slots or {}).get(slot) or SlotEvidence()
            self.slots[dataset][slot][self._category(settled, said)] += 1
            if settled["value"] is not None and not any(
                c.get("source_type") == SOURCE_PUBLISHED_VALUE for c in said.claims
            ):
                self.slots[dataset][slot]["added_over_published"] += 1
            self.inputs[dataset][slot][INFERENCE][self._inference_outcome(settled, said)] += 1
            for source_type in self.source_types:
                if dataset in self.coverage.get(source_type, set()):
                    self.inputs[dataset][slot][source_type][self._source_outcome(settled, said, source_type)] += 1

    @staticmethod
    def _category(settled: dict, said: SlotEvidence) -> str:
        status = settled["status"]
        if status == NOT_CLASSIFIED and SOURCE_PUBLISHED_VALUE in said.unreviewed:
            return MISSING_WORK
        if status != CLASSIFIED:
            return status
        own = inferred_declaration(settled["inferred"]["status"], settled["inferred"]["value"])
        sources = [c for c in said.claims if declaration(c) is not None]
        if own is None:
            return FILLED
        return AGREED_SLOT if sources else INFERENCE_ONLY

    @staticmethod
    def _inference_outcome(settled: dict, said: SlotEvidence) -> str:
        inferred = settled["inferred"]
        if inferred["status"] == CONFLICT or (
            settled["status"] == CONFLICT and inferred_declaration(inferred["status"], inferred["value"]) is not None
        ):
            return CONFLICT
        own = inferred_declaration(inferred["status"], inferred["value"])
        if own is None:
            return SILENT
        return AGREED if any(declaration(c) == own for c in said.claims) else ADDED

    @staticmethod
    def _source_outcome(settled: dict, said: SlotEvidence, source_type: str) -> str:
        mine = [c for c in said.claims if c.get("source_type") == source_type and declaration(c) is not None]
        if mine:
            if settled["status"] == CONFLICT:
                return CONFLICT
            return HARMONIZED if any(is_harmonized(c) for c in mine) else MATCH
        if source_type in said.unreviewed:
            return UNREVIEWED
        return SILENT

    def to_dict(self) -> dict:
        def plain(d):
            return {k: plain(v) for k, v in sorted(d.items())} if isinstance(d, dict) else d

        conflict_rate = {
            dataset: {
                slot: round(counts.get(CONFLICT, 0) / self.files[dataset], 6) if self.files[dataset] else 0.0
                for slot, counts in sorted(per_slot.items())
            }
            for dataset, per_slot in sorted(self.slots.items())
        }
        return {
            "files": dict(sorted(self.files.items())),
            "slots": plain(self.slots),
            "inputs": plain(self.inputs),
            "conflict_rate": conflict_rate,
            "coverage": {k: sorted(v) for k, v in sorted(self.coverage.items())},
        }


# --- the stage ----------------------------------------------------------------------


@dataclass(frozen=True)
class Result:
    out_dir: Path
    report: dict


def reconcile_run(
    run_dir: Path,
    metadata: Path,
    evidence_root: Path | None = DEFAULT_SOURCE_EVIDENCE_ROOT,
    table: ValueMap | None = None,
) -> Result:
    """Reconcile one stored run and write ``<run>/reconciled/``; ``evidence_root=None`` excludes all evidence.

    The inference files are read and never written. The output is written to a staging
    directory and renamed into place only when complete, so a failure leaves any earlier
    reconciled artifact untouched. Nothing here reads a clock or the network, so the
    same inputs write the same bytes (criterion 16).
    """
    if not run_dir.is_dir():
        raise ReconcileError(f"run directory not found: {run_dir}")
    envelope = load_envelope(metadata)
    key = record_key(envelope, metadata)
    repository = envelope["repository"]
    catalog = envelope.get("catalog")
    table = table if table is not None else load_value_map()

    if evidence_root is None:
        applicable, skipped = [], []
    else:
        require_one_published_source(report_evidence_files(evidence_root), PUBLISHED_TABLES)
        applicable, skipped = select_evidence(discover(evidence_root), repository, catalog)
    joined = join(applicable, run_dir, key.output_field, table)
    source_types = tuple(sorted({ev.source_type for ev in applicable}))
    report = Report(coverage=joined.coverage, source_types=source_types)

    root = evidence_root or Path()
    header = {
        RECONCILED_ENVELOPE_KEY: {
            "run": run_dir.name,
            "input": str(metadata),
            "repository": repository,
            "catalog": catalog,
            "evidence_excluded": evidence_root is None,
            "evidence": [
                {
                    "path": _relative(ev.path, root),
                    "source_type": ev.source_type,
                    "dataset": ev.dataset,
                    "source_version": ev.envelope.source_version,
                }
                for ev in applicable
            ],
        }
    }

    out_dir = run_dir / RECONCILED_DIR
    staging = run_dir / f"{RECONCILED_DIR}.partial"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    for fname, records in iter_run_files(run_dir):
        with (staging / reconciled_name(fname)).open("w") as f:
            f.write(json.dumps(header, sort_keys=True) + "\n")
            for record in records:
                record_slots = joined.slots.get(str(record.get(key.output_field)))
                reconciled = reconcile_record(record, record_slots)
                report.add(record, reconciled, record_slots)
                f.write(json.dumps(reconciled) + "\n")

    full_report = {
        **header[RECONCILED_ENVELOPE_KEY],
        "evidence": [ev.summary(root) for ev in joined.files],
        "skipped_evidence": skipped,
        **report.to_dict(),
    }
    (staging / REPORT_FILE).write_text(json.dumps(full_report, indent=2, sort_keys=True) + "\n")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    staging.rename(out_dir)
    return Result(out_dir=out_dir, report=full_report)


def render_summary(report: dict) -> str:
    """The report's headline numbers as plain text: the join, then each dimension's totals."""
    lines = []
    if report["evidence_excluded"]:
        lines.append("Evidence excluded: the reconciled artifact concludes what inference concluded.")
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
    run_dir = args.run or find_latest_run(Path("output/anvil"))
    try:
        metadata = args.metadata or DEPLOYMENTS[args.deployment].input_file
        result = reconcile_run(run_dir, metadata, None if args.no_evidence else args.evidence_root)
    except ReconcileError as exc:
        print(f"reconcile refused: {exc}", file=sys.stderr)
        return 1
    print(f"Reconciled {run_dir} -> {result.out_dir}")
    print(render_summary(result.report))
    return 0
