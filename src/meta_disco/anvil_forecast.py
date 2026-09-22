"""What a submitter name would claim, forecast against a stored run (#369).

Two measurements, one join. Both take a stored classification run, index it by
``drs_uri``, and ask of each claim a source would make: does the run have a value for
that file and slot, and does it agree?

- :func:`name_signals` needs **no map**. For every dataset the catalog's sidecar names
  (or ``datasets``) it reads every submitter table, and for every file-link column it takes what the table
  name and the column name would claim by `manifest_survey.NAME_TOKENS` — the survey's
  reading aid, which says what a name *mentions* — and reports, per dataset and slot,
  how many claims join a run record, agree, disagree, meet a ``not_applicable``, or land
  where inference has no value. It also says plainly which tokens it cannot translate,
  because the vocabulary has no term for them.
- :func:`evidence_forecast` reads the **written** evidence — what ``discover`` returns
  under the evidence root — and reports the same join over what the importer produced,
  plus every raw value by slot as the translation table's input (#414).

**This forecasts; it never authors.** A disagreement here is the resolver's to record
(contract 4.5) and an agreement is what 4.4 records; neither is grounds to change
the map, which is authored from the source's own schema and from nothing a run
concluded (3.4). :func:`name_signals` applies the two structural exclusions the
loader enforces, through the one predicate that states them
(`slot_map.structural_exclusion`); :func:`evidence_forecast` reads evidence the loader
already admitted and applies nothing. The authoring rule the map follows beyond those
two is a judgment neither applies, so `name_signals` can forecast more than the map says.

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
from .models import CLASSIFICATION_FIELDS, CLASSIFIED, JOIN_KEY_DRS_URI, NOT_APPLICABLE, field_status, field_value
from .output_utils import iter_records_with_source
from .producers import PRODUCERS
from .slot_map import DERIVATIVE, ENTITY, structural_exclusion
from .source_evidence import discover, iter_evidence, read_envelope
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
    what a within-source contradiction looks like from here (4.8). A dataset named twice
    is measured once; one whose manifest is not on disk is refused by name.
    """
    titles = sorted(sidecar_datasets(manifest_root, catalog)) if datasets is None else list(dict.fromkeys(datasets))
    results = []
    for dataset in titles:
        path = manifest_path(manifest_root, catalog, dataset, FORMAT_VERBATIM)
        if not path.is_file():
            raise ValueError(f"{dataset}: no verbatim manifest at {path} — run `make download` for {catalog} first")
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

    ``by_verdict`` holds the claims whose raw value spells a name token, as
    ``(file, slot, term)``, under each of :data:`VERDICTS` except ``gap`` — a translated
    claim on a slot inference left open is in ``gaps`` with every other such pair.
    ``raw_values`` counts every row by ``(slot, raw_value)``, joined or not;
    ``translated`` maps the pairs a token covers to its term, joined or not.
    """

    files: set[str] = field(default_factory=set)
    unjoined: set[str] = field(default_factory=set)
    skipped: list[Path] = field(default_factory=list)  # evidence files not keyed by drs_uri
    rows: int = 0
    gaps: set[tuple[str, str]] = field(default_factory=set)  # (file, slot) inference left without a value
    not_applicable: set[tuple[str, str]] = field(default_factory=set)
    fastq_modality: set[str] = field(default_factory=set)
    by_verdict: dict[str, set[tuple[str, str, str]]] = field(default_factory=lambda: defaultdict(set))
    raw_values: Counter = field(default_factory=Counter)  # (slot, raw_value) -> rows, every row
    translated: dict[tuple[str, str], str] = field(default_factory=dict)  # (slot, raw_value) -> token term


def evidence_forecast(evidence_root: Path, run: dict[str, RunRecord]) -> EvidenceForecast:
    """Join every current evidence file under ``evidence_root`` to ``run``.

    Only a file whose envelope keys its rows by ``drs_uri`` is joined — that is what
    ``run`` is indexed by; a file keyed otherwise is listed as skipped rather than
    counted as files that never join. A raw value is compared only when, lowercased, it
    is one name token with a term in that row's slot (``CHM13v2``, ``grch38``, ``hifi``,
    and a cell value such as ``ILLUMINA``); every raw value is counted by slot either
    way, so the translation table's authors see everything that arrives — the published
    map's files (#497) included. Those are counted and never compared: every published
    cell is a list, written as its JSON array, which is not one name token.
    """
    forecast = EvidenceForecast()
    for path in discover(evidence_root):
        if read_envelope(path).target_key != JOIN_KEY_DRS_URI:
            forecast.skipped.append(path)
            continue
        for entry in iter_evidence(path):
            forecast.rows += 1
            handle, slot = entry.target_key_value, entry.field
            forecast.files.add(handle)
            # Counted before the join: what arrives for #414 does not depend on which run
            # the forecast happens to be measured against.
            forecast.raw_values[(slot, entry.raw_value)] += 1
            meaning = NAME_TOKENS.get(entry.raw_value.lower())
            term = meaning[1] if meaning is not None and meaning[0] == slot else None
            if term is not None:
                forecast.translated[(slot, entry.raw_value)] = term
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
            if term is None:
                continue
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
    if forecast.skipped:
        out += [
            f"Skipped {len(forecast.skipped)} evidence file(s) not keyed by `drs_uri`: "
            + ", ".join(f"`{p.relative_to(evidence_root)}`" for p in forecast.skipped),
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
            [
                "claims whose raw value spells a name token, agreeing with inference",
                f"{len(forecast.by_verdict[AGREE]):,}",
            ],
            [
                "claims whose raw value spells a name token, disagreeing with an inferred value (a conflict, 4.5)",
                f"{len(forecast.by_verdict[DISAGREE]):,}",
            ],
            [
                "claims whose raw value spells a name token, against an inferred not_applicable (a conflict, 4.6)",
                f"{len(forecast.by_verdict[NOT_APPLICABLE]):,}",
            ],
        ],
        align="right",
    )
    out += [
        "",
        "Every raw value that arrives, by slot — the translation table's input (#414). The last column "
        "is the term `NAME_TOKENS` gives the value where it spells a token, which is what the counts "
        "above compared; blank means no translation exists yet.",
        "",
    ]
    out += md_table(
        ["slot", "raw value", "rows", "token term"],
        [
            [slot, f"`{raw}`", f"{n:,}", forecast.translated.get((slot, raw), "")]
            for (slot, raw), n in sorted(forecast.raw_values.items(), key=lambda i: (i[0][0], -i[1]))
        ],
        align="right",
    )
    return "\n".join(out) + "\n"
