"""What a submitter name would claim, forecast against a stored run (#369, R8).

Two measurements, one join. Both take a stored classification run, index it by
``drs_uri``, and ask of each claim a source would make: does the run have a value for
that file and slot, and does it agree?

- :func:`name_signals` needs **no map**. For every dataset the catalog's sidecar names it
  reads every submitter table, and for every file-link column it takes what the table
  name and the column name would claim by `manifest_survey.NAME_TOKENS` — the survey's
  reading aid, which says what a name *mentions* — and reports, per dataset and slot,
  how many claims join a run record, agree, disagree, meet a ``not_applicable``, or land
  where inference has no value. It also says plainly which tokens it cannot translate,
  because the vocabulary has no term for them.
- :func:`evidence_forecast` reads the **written** evidence — the newest generation of
  each dataset under the evidence root — and reports the same join over what the
  importer actually produced: files with evidence, file-and-slot pairs where inference
  reaches no value, FASTQs that received a ``data_modality``, and the name-derived
  claims that disagree with an inferred value or meet an inferred ``not_applicable`` —
  the two kinds of conflict, 4.5's and 4.6's, reported apart because the second is a
  within-source contradiction the map passes through on purpose (R9). Only a raw value
  that is a name token is compared; a cell value such as ``PACBIO_SMRT`` has no
  translation until #414 and is counted as untranslated.

**This forecasts; it never authors.** A disagreement here is the resolver's to record
(contract 4.5) and an agreement is a source earning trust (4.4); neither is grounds to
change the map, which is authored from the source's own schema and from nothing a run
concluded (R1, 3.4). Both measurements apply the map's structural exclusions through
the one predicate that states them (`slot_map.structural_exclusion`), so that what they
forecast is what the map can say.

The run is read through ``output_utils.iter_records_with_source``, which loads each
producer's file whole; that is the run's existing reader and its memory ceiling
(#374), not this module's.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .azul_manifest import (
    FORMAT_VERBATIM,
    is_submitter_table,
    iter_verbatim_entities,
    link_handles,
    manifest_path,
    sidecar_datasets,
)
from .manifest_survey import NAME_TOKENS, NO_VOCABULARY_TERM, name_tokens
from .models import CLASSIFICATION_FIELDS, CLASSIFIED, NOT_APPLICABLE, field_status, field_value
from .output_utils import iter_records_with_source
from .producers import PRODUCERS
from .slot_map import DERIVATIVE, ENTITY, structural_exclusion
from .source_evidence import discover, iter_evidence
from .summaries import md_table

AGREE = "agree"
DISAGREE = "disagree"
GAP = "gap"
# The four verdicts a joined claim can meet, in report order. `not_applicable` is its
# own column because contract 4.6 makes it a conflict with a value, where `gap` is a
# slot inference left open and a source fills (4.4).
VERDICTS = (AGREE, DISAGREE, NOT_APPLICABLE, GAP)
_FASTQ_OUTPUT = PRODUCERS["fastq"].output


@dataclass(frozen=True, slots=True)
class RunRecord:
    """One run record, reduced to what the join needs: per slot, its status and value."""

    is_fastq: bool
    slots: dict[str, tuple[str, str | None]]

    def verdict(self, slot: str, term: str) -> str:
        status, value = self.slots.get(slot, (None, None))
        if status == CLASSIFIED:
            return AGREE if value == term else DISAGREE
        if status == NOT_APPLICABLE:
            return NOT_APPLICABLE
        return GAP


def index_run(run_dir: Path) -> dict[str, RunRecord]:
    """A run's records by ``drs_uri`` — the last seen per key; a record without one cannot be joined."""
    index: dict[str, RunRecord] = {}
    for fname, record in iter_records_with_source(run_dir):
        drs = record.get("drs_uri")
        if not isinstance(drs, str) or not drs:
            continue
        slots = {slot: (field_status(record, slot), field_value(record, slot)) for slot in CLASSIFICATION_FIELDS}
        index[drs] = RunRecord(is_fastq=fname == _FASTQ_OUTPUT, slots=slots)
    return index


# --- names, without a map ---------------------------------------------------------


@dataclass
class SlotSignals:
    """One dataset's name-derived claims on one slot, and how they met the run."""

    claimed: int = 0
    unjoined: int = 0
    verdicts: Counter = field(default_factory=Counter)
    untranslatable: Counter = field(default_factory=Counter)  # token -> claims it made


@dataclass
class DatasetSignals:
    """One dataset's signals per slot, plus what the structural rules excluded.

    The two ``excluded_*`` counts are per row and link, not per distinct file: an
    exclusion is counted where it would have been applied, which is each time a link
    is read. ``claimed`` in :class:`SlotSignals` is per distinct ``(file, slot, token)``.
    """

    dataset: str
    slots: dict[str, SlotSignals] = field(default_factory=lambda: defaultdict(SlotSignals))
    excluded_entity: int = 0
    excluded_derivative: int = 0


def name_claims(table: str, column: str) -> tuple[list[tuple[str, str, str | None]], int, int]:
    """What the table name and the column name would claim for a file in this column.

    Returns ``(claims, entity_excluded, derivative_excluded)``: each claim is
    ``(slot, token, term)`` with ``term`` None where the vocabulary has no word for the
    token; a token spelled in both names counts once per slot, excluded or not; and the
    structural exclusions the slot map enforces are applied and counted rather than
    silently dropped.
    """
    distinct: dict[tuple[str, str], str | None] = {}
    for name in (table, column):
        for token in name_tokens(name):
            meaning = NAME_TOKENS.get(token)
            if meaning is not None:
                distinct.setdefault((meaning[0], token), meaning[1])
    claims: list[tuple[str, str, str | None]] = []
    entity = derivative = 0
    for (slot, token), term in distinct.items():
        excluded = structural_exclusion(slot, column, token)
        if excluded == ENTITY:
            entity += 1
        elif excluded == DERIVATIVE:
            derivative += 1
        else:
            claims.append((slot, token, term))
    return claims, entity, derivative


def name_signals(
    manifest_root: Path, catalog: str, run: dict[str, RunRecord], datasets: Iterable[str] | None = None
) -> list[DatasetSignals]:
    """Measure every dataset's name-derived claims against ``run``; no map needed.

    A claim is one ``(file, slot, token)``, counted once however many rows reach the
    file — a file in two tables that spell different assemblies is two claims, which is
    what a within-source contradiction looks like from here (R9).
    """
    titles = sorted(sidecar_datasets(manifest_root, catalog)) if datasets is None else list(datasets)
    results = []
    for dataset in titles:
        path = manifest_path(manifest_root, catalog, dataset, FORMAT_VERBATIM)
        signals = DatasetSignals(dataset=dataset)
        claims: set[tuple[str, str, str, str | None]] = set()
        by_names: dict[tuple[str, str], tuple] = {}
        for table, row in iter_verbatim_entities(path):
            if not is_submitter_table(table):
                continue
            for column, value in row.items():
                links = link_handles(value)
                if not links:
                    continue
                if (table, column) not in by_names:
                    by_names[(table, column)] = name_claims(table, column)
                column_claims, entity, derivative = by_names[(table, column)]
                signals.excluded_entity += entity * len(links)
                signals.excluded_derivative += derivative * len(links)
                for handle in links:
                    for slot, token, term in column_claims:
                        claims.add((handle, slot, token, term))
        for handle, slot, token, term in claims:
            per_slot = signals.slots[slot]
            per_slot.claimed += 1
            if term is None:
                per_slot.untranslatable[token] += 1
                continue
            record = run.get(handle)
            if record is None:
                per_slot.unjoined += 1
                continue
            per_slot.verdicts[record.verdict(slot, term)] += 1
        results.append(signals)
    return results


def render_name_signals(results: list[DatasetSignals], run_dir: Path) -> str:
    out = [
        "# Name signals",
        "",
        f"What a submitter table or column name would claim, by `manifest_survey.NAME_TOKENS`, "
        f"measured against `{run_dir}`. A claim is one (file, slot, token). A forecast for the "
        "translation table and the resolver, never an input to the slot map (#369 R8).",
        "",
    ]
    rows = []
    for signals in results:
        for slot, s in sorted(signals.slots.items()):
            rows.append(
                [
                    signals.dataset,
                    slot,
                    f"{s.claimed:,}",
                    f"{s.unjoined:,}",
                    *[f"{s.verdicts[v]:,}" for v in VERDICTS],
                    f"{sum(s.untranslatable.values()):,}",
                ]
            )
    out += md_table(["dataset", "slot", "claimed", "unjoined", *VERDICTS, "untranslatable"], rows, align="right")
    excluded = [
        [signals.dataset, f"{signals.excluded_entity:,}", f"{signals.excluded_derivative:,}"]
        for signals in results
        if signals.excluded_entity or signals.excluded_derivative
    ]
    if excluded:
        out += ["", "Excluded before counting, by the map's structural rules (per row and link):", ""]
        out += md_table(
            ["dataset", "entity-shaped token", "data_type on an index or checksum column"], excluded, align="right"
        )
    untranslatable: Counter = Counter()
    for signals in results:
        for slot, s in signals.slots.items():
            for token, n in s.untranslatable.items():
                untranslatable[(slot, token)] += n
    if untranslatable:
        out += ["", f"Tokens with no term in the vocabulary {NO_VOCABULARY_TERM}, with the claims they would make:", ""]
        out += md_table(
            ["slot", "token", "claims"],
            [[slot, f"`{token}`", f"{n:,}"] for (slot, token), n in sorted(untranslatable.items())],
            align="right",
        )
    return "\n".join(out) + "\n"


# --- the written evidence -----------------------------------------------------------


@dataclass
class EvidenceForecast:
    """The written evidence joined to a run: the numbers the import is judged on.

    ``by_verdict`` holds the name-derived claims, as ``(file, slot, term)``, under each
    of :data:`VERDICTS` except ``gap`` — a translated claim on a slot inference left open
    is in ``gaps`` with every other such pair.
    """

    files: set[str] = field(default_factory=set)
    unjoined: set[str] = field(default_factory=set)
    rows: int = 0
    gaps: set[tuple[str, str]] = field(default_factory=set)  # (file, slot) inference left without a value
    not_applicable: set[tuple[str, str]] = field(default_factory=set)
    fastq_modality: set[str] = field(default_factory=set)
    by_verdict: dict[str, set[tuple[str, str, str]]] = field(default_factory=lambda: defaultdict(set))
    untranslated: Counter = field(default_factory=Counter)  # (slot, raw_value) -> rows


def evidence_forecast(evidence_root: Path, run: dict[str, RunRecord]) -> EvidenceForecast:
    """Join every current evidence file under ``evidence_root`` to ``run``.

    A raw value is compared only when it is a name token with a term (``CHM13v2``,
    ``grch38``, ``hifi``); every other raw value is counted as untranslated, with its
    slot, so the translation table's authors can see what arrives.
    """
    forecast = EvidenceForecast()
    for path in discover(evidence_root):
        for entry in iter_evidence(path):
            forecast.rows += 1
            handle, slot = entry.target_key_value, entry.field
            forecast.files.add(handle)
            record = run.get(handle)
            if record is None:
                forecast.unjoined.add(handle)
                continue
            status, _value = record.slots.get(slot, (None, None))
            if status == NOT_APPLICABLE:
                forecast.not_applicable.add((handle, slot))
            elif status != CLASSIFIED:
                forecast.gaps.add((handle, slot))
            if slot == "data_modality" and record.is_fastq:
                forecast.fastq_modality.add(handle)
            meaning = NAME_TOKENS.get(entry.raw_value.lower())
            if meaning is None or meaning[0] != slot or meaning[1] is None:
                forecast.untranslated[(slot, entry.raw_value)] += 1
                continue
            term = meaning[1]
            verdict = record.verdict(slot, term)
            if verdict != GAP:
                forecast.by_verdict[verdict].add((handle, slot, term))
    return forecast


def render_evidence_forecast(forecast: EvidenceForecast, evidence_root: Path, run_dir: Path) -> str:
    out = [
        "# Evidence forecast",
        "",
        f"The newest generation of each dataset under `{evidence_root}`, joined by `drs_uri` to `{run_dir}`.",
        "",
    ]
    out += md_table(
        ["measure", "count"],
        [
            ["evidence rows", f"{forecast.rows:,}"],
            ["files with evidence", f"{len(forecast.files):,}"],
            ["files not in the run", f"{len(forecast.unjoined):,}"],
            [
                "file-and-slot pairs where inference reaches no value (not_classified or conflict)",
                f"{len(forecast.gaps):,}",
            ],
            ["file-and-slot pairs where inference says not_applicable", f"{len(forecast.not_applicable):,}"],
            ["FASTQs receiving data_modality", f"{len(forecast.fastq_modality):,}"],
            ["name-derived claims agreeing with inference", f"{len(forecast.by_verdict[AGREE]):,}"],
            [
                "name-derived claims disagreeing with an inferred value (a conflict, 4.5)",
                f"{len(forecast.by_verdict[DISAGREE]):,}",
            ],
            [
                "name-derived claims against an inferred not_applicable (a conflict, 4.6)",
                f"{len(forecast.by_verdict[NOT_APPLICABLE]):,}",
            ],
        ],
        align="right",
    )
    out += ["", "Raw values with no name-token translation, by slot (the translation table's input, #414):", ""]
    out += md_table(
        ["slot", "raw value", "rows"],
        [
            [slot, f"`{raw}`", f"{n:,}"]
            for (slot, raw), n in sorted(forecast.untranslated.items(), key=lambda i: (i[0][0], -i[1]))
        ],
        align="right",
    )
    return "\n".join(out) + "\n"
