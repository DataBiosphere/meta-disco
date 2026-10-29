"""Entity evidence files: a source saying what it wrote about a donor or a sample, or its own identifier for one (#693, #669, #699).

Where a slot evidence file (``source_evidence``) is keyed by a file's key, an entity file is
keyed by the identifier the source wrote for a donor or a sample (``HG00096``): line 1 is the same
``EvidenceFileEnvelope`` with ``target_key: entity_identifier``, every later line an
``EntityEvidenceRow``. The files go under their own root, ``data/entity_evidence/``, because
every reader of ``data/source_evidence/`` takes each file there as a file's slot lines; the
layout is the slot root's generation layout, so ``discover`` reads it too.

**A line declares nothing** (contract 1.1): the identifier is recognised at reconcile, the
value translated by the value map, and a line carrying an answer is refused by name.
:func:`entries` gives the lines naming the fields asked for, each as a
``source_evidence.EvidenceEntry``, so the value map's seeding and review queue read both roots alike. Like
``source_evidence.iter_evidence``, it yields by default only the lines the value map
translates (a donor's slots, and a sample's translated ones, #699). Every other line goes only
to a reader that asks for it, which today is reconcile: an untranslated slot's (a family's, #582;
a sample's site), one carrying a repository's own identifier for a donor or sample
(``models.REPOSITORY_ID_FIELDS``, #669), and an identity link (``models.IDENTITY_LINK_FIELDS``, #559): a sample's
donors, by their identifiers or the repository's identifiers for them (#770), or another identifier for a donor.

A generation's :data:`OUTCOMES_FILE` (#718) is not ``.ndjson``, so no evidence reader takes it as
evidence; reconcile reads it only to report why a sample has no donor.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Collection, Iterable, Iterator
from pathlib import Path

from .models import (
    DONOR_FIELDS,
    JOIN_KEY_ENTITY_IDENTIFIER,
    SAMPLE_FIELDS,
    SOURCE_EXTERNAL_GROUND_TRUTH,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_METADATA,
    ClaimSource,
)
from .schema.classification_model import EntityEvidenceRow, EvidenceFileEnvelope
from .source_evidence import (
    DEFAULT_SOURCE_EVIDENCE_ROOT,
    EvidenceEntry,
    claim_source_for,
    iter_model_rows,
    parse_iso_datetime,
    read_envelope_from,
    write_model_rows,
)

DEFAULT_ENTITY_EVIDENCE_ROOT = DEFAULT_SOURCE_EVIDENCE_ROOT.parent / "entity_evidence"

# The kinds an entity file may declare: a submitter's table, what the repository publishes
# for the donor (AnVIL's `anvil_donor`), and a source outside the repository that names the
# same people (SGDP's metadata file, #559).
ENTITY_SOURCE_TYPES = frozenset({SOURCE_REPOSITORY_METADATA, SOURCE_PUBLISHED_VALUE, SOURCE_EXTERNAL_GROUND_TRUTH})

# Members a line would carry if it declared an answer, each with why it may not.
_REFUSED_LINE_KEYS = {
    "value": "an entity line maps nothing onto our vocabulary; the value map does (contract 1.1, 1.3)",
    "status": "a status is a rule's to declare, never a source's (contract 3.6)",
    "claim_state": "an entity line is an observation, not a claim",
    "rule_id": "there is no rule at import time; the claim reconcile makes cites one",
    "tier": "imported evidence does not compete on the rule tiers (#391)",
    "identifier": "which identifier a string is, is the identifier rules' to say at reconcile",
    "source_type": "one file is one kind of source, so it is on the envelope, not on every line",
}

OUTCOMES_FILE = "outcomes.json"


def entity_root_beside(evidence_root: Path) -> Path:
    """The entity evidence root beside a slot evidence root (``data/entity_evidence`` beside ``data/source_evidence``)."""
    return evidence_root.parent / DEFAULT_ENTITY_EVIDENCE_ROOT.name


def _check_envelope(envelope: EvidenceFileEnvelope, where: str) -> None:
    parse_iso_datetime(envelope.fetched_at, "envelope fetched_at", where)
    if envelope.source_type not in ENTITY_SOURCE_TYPES:
        raise ValueError(
            f"{where}: source_type {envelope.source_type!r} is not an entity source ({sorted(ENTITY_SOURCE_TYPES)})"
        )
    if envelope.target_key != JOIN_KEY_ENTITY_IDENTIFIER:
        raise ValueError(f"{where}: target_key is {envelope.target_key!r}; an entity file is keyed by an identifier")
    if envelope.target.dataset is None:
        raise ValueError(
            f"{where}: names no target dataset — a dataset_local identifier is recognised only in its dataset"
        )


def write_entity_file(path: Path, envelope: EvidenceFileEnvelope, rows: Iterable[EntityEvidenceRow]) -> int:
    """Write one entity file, streaming, its envelope checked first; return how many lines."""
    return write_model_rows(path, envelope, rows, EntityEvidenceRow, _check_envelope)


def read_entity_envelope(path: Path) -> EvidenceFileEnvelope:
    """An entity file's envelope, from line 1 alone, checked as :func:`iter_entity_evidence` checks it."""
    with path.open("rb") as f:
        envelope = read_envelope_from(path, f)
    _check_envelope(envelope, f"{path.name} line 1")
    return envelope


def iter_entity_evidence(path: Path) -> Iterator[EntityEvidenceRow]:
    """Every line of one entity file after the envelope, streamed; ``ValueError`` naming the line that
    will not parse or carries an answer (:data:`_REFUSED_LINE_KEYS`)."""
    return iter_model_rows(path, EntityEvidenceRow, _REFUSED_LINE_KEYS, _check_envelope)


def entries(
    path: Path, envelope: EvidenceFileEnvelope | None = None, fields: Collection[str] = (*DONOR_FIELDS, *SAMPLE_FIELDS)
) -> Iterator[EvidenceEntry]:
    """Every line of one entity file naming one of ``fields``, as an ``EvidenceEntry``, one ``ClaimSource`` per column;
    ``envelope`` where the caller holds it. Every line is still checked, whichever field it names."""
    envelope = envelope if envelope is not None else read_entity_envelope(path)
    by_column: dict[str, ClaimSource] = {}
    for row in iter_entity_evidence(path):
        if row.field not in fields:
            continue
        source = by_column.get(row.column)
        if source is None:
            source = by_column[row.column] = claim_source_for(envelope.source, row.column)
        yield EvidenceEntry(row.field, row.target_key_value, row.raw_value, source)


def write_outcomes(directory: Path, source: str, dataset: str, samples: Iterable[dict]) -> None:
    """Write a generation's :data:`OUTCOMES_FILE`: what ``source`` found of each sample of ``dataset``, each a dict
    naming its ``sample`` as the source wrote it."""
    rows = list(samples)
    if not all(isinstance(r.get("sample"), str) and r["sample"] and "source" not in r for r in rows):
        # Refused before the generation is written: reconcile refuses to read such a file.
        raise ValueError(f"{directory}: every outcome names its sample, and none its own source")
    text = json.dumps({"source": source, "dataset": dataset, "samples": rows}, indent=1, sort_keys=True)
    (directory / OUTCOMES_FILE).write_text(text + "\n", encoding="utf-8")


def read_outcomes(paths: Iterable[Path]) -> dict[tuple[str, str], list[dict]]:
    """The outcomes of the generations ``paths`` (entity files) are in, by (dataset, sample as written), one per
    source that wrote one, each naming its ``source``; a generation without :data:`OUTCOMES_FILE` gives none.
    ``ValueError`` where one is malformed."""
    found: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for directory in sorted({p.parent for p in paths}):
        path = directory / OUTCOMES_FILE
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        source, dataset, samples = document.get("source"), document.get("dataset"), document.get("samples")
        if not isinstance(source, str) or not isinstance(dataset, str) or not isinstance(samples, list):
            raise ValueError(f"{path}: not a source, a dataset and a list of samples")
        for row in samples:
            sample = row.get("sample") if isinstance(row, dict) else None
            if not isinstance(sample, str) or not sample:
                raise ValueError(f"{path}: an outcome names no sample")
            if "source" in row:
                raise ValueError(f"{path}: an outcome names its own source; the file's is {source!r}")
            found[(dataset, sample)].append({"source": source, **row})
    return dict(found)
