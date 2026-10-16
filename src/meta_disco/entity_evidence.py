"""Entity evidence files: a source saying what it wrote about a donor (#693).

A slot evidence file (``source_evidence``) says what a source wrote about one of a
file's dimensions, keyed by a file's key. An entity evidence file says what a source wrote
about one of a donor's slots (``models.DONOR_FIELDS``), keyed by the identifier the source
wrote for the donor (``HG00096``). The envelope on line 1 is the same
``EvidenceFileEnvelope``, keyed by ``entity_identifier``; every later line is an
``EntityEvidenceRow``, the class the schema declares and gen-pydantic emits, used as it is.

**A separate root.** Entity files go under ``data/entity_evidence/``, never under
``data/source_evidence/``: every reader of the slot root reads each file there as a file's
slot lines, and an entity line is not one. The layout under the root is the slot root's
generation layout (``source_evidence.generation_dir``), so ``discover`` finds the newest
generation per dataset here too.

**A line declares nothing** (contract 1.1). ``target_key_value`` is the identifier as the
source wrote it, recognised through ``rules/sample_namespaces.yaml`` at reconcile, in the
envelope's target dataset; ``raw_value`` is the value as written, which the value map
translates. A line carrying an answer is refused by name, as ``source_evidence`` refuses
one on a slot line.

:func:`entries` gives each line as a ``source_evidence.EvidenceEntry``, the shape the value
map's seeding and review queue read a slot line in, so they read both roots alike.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from pydantic import ValidationError

from .models import JOIN_KEY_ENTITY_IDENTIFIER, SOURCE_PUBLISHED_VALUE, SOURCE_REPOSITORY_METADATA, ClaimSource
from .schema.classification_model import EntityEvidenceRow, EvidenceFileEnvelope
from .source_evidence import (
    DEFAULT_SOURCE_EVIDENCE_ROOT,
    EVIDENCE_FILE_SUFFIX,
    EvidenceEntry,
    claim_source_for,
    decode_line,
    parse_iso_datetime,
    read_envelope_from,
    write_ndjson,
)

DEFAULT_ENTITY_EVIDENCE_ROOT = DEFAULT_SOURCE_EVIDENCE_ROOT.parent / "entity_evidence"

# The kinds an entity file may declare: a submitter's table, and what the repository
# publishes for the donor (AnVIL's `anvil_donor`).
ENTITY_SOURCE_TYPES = frozenset({SOURCE_REPOSITORY_METADATA, SOURCE_PUBLISHED_VALUE})

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
    """Write one entity file, streaming; return the number of lines after the envelope.

    Written through ``source_evidence.write_ndjson``, the slot writer's own path: to a
    temporary name, renamed into place only once every row is out. The envelope is checked
    before anything is written, so this cannot write a file :func:`iter_entity_evidence`
    refuses.
    """
    if path.suffix != EVIDENCE_FILE_SUFFIX:
        raise ValueError(f"{path.name}: an entity file must end in {EVIDENCE_FILE_SUFFIX}, or discover never finds it")
    _check_envelope(envelope, "entity file envelope")
    return write_ndjson(path, envelope, (_line(row, f"{path.name} row {n}") for n, row in enumerate(rows, start=1)))


def _line(row: EntityEvidenceRow, where: str) -> dict:
    if not isinstance(row, EntityEvidenceRow):
        raise ValueError(f"{where}: is a {type(row).__name__}, not an EntityEvidenceRow")
    return row.model_dump(exclude_none=True)


def read_entity_envelope(path: Path) -> EvidenceFileEnvelope:
    """An entity file's envelope, from line 1 alone, checked as :func:`iter_entity_evidence` checks it."""
    with path.open("rb") as f:
        envelope = read_envelope_from(path, f)
    _check_envelope(envelope, f"{path.name} line 1")
    return envelope


def iter_entity_evidence(path: Path) -> Iterator[EntityEvidenceRow]:
    """Every line of one entity file after the envelope, in file order, streamed.

    A blank line is passed over. Any other line that will not parse, carries an answer
    (:data:`_REFUSED_LINE_KEYS`) or carries a member ``EntityEvidenceRow`` does not have
    raises ``ValueError`` naming the file and line.
    """
    with path.open("rb") as f:
        envelope = read_envelope_from(path, f)
        _check_envelope(envelope, f"{path.name} line 1")
        for n, raw in enumerate(f, start=2):
            where = f"{path.name} line {n}"
            line = decode_line(raw, where)
            if line.isspace():
                continue
            try:
                block = json.loads(line)
            except (ValueError, RecursionError) as exc:
                raise ValueError(f"{where}: not JSON: {exc!r}") from None
            if not isinstance(block, dict):
                raise ValueError(f"{where}: is {type(block).__name__}, not an object")
            refused = next((key for key in sorted(block) if key in _REFUSED_LINE_KEYS), None)
            if refused is not None:
                raise ValueError(f"{where}: carries {refused!r} — {_REFUSED_LINE_KEYS[refused]}")
            try:
                yield EntityEvidenceRow.model_validate(block)
            except ValidationError as exc:
                faults = "; ".join(
                    f"{' '.join(str(p) for p in e['loc']) or 'line'}: "
                    f"{'unknown member' if e['type'] == 'extra_forbidden' else e['msg']}"
                    for e in exc.errors()
                )
                raise ValueError(f"{where}: {faults}") from None


def claim_source(envelope: EvidenceFileEnvelope, row: EntityEvidenceRow) -> ClaimSource:
    """The ``ClaimSource`` a claim from ``row`` carries: the envelope's source and the row's column."""
    return claim_source_for(envelope.source, row.column)


def entries(path: Path) -> Iterator[EvidenceEntry]:
    """Every line of one entity file as an ``EvidenceEntry``, for a reader of both evidence roots.

    ``target_key_value`` is the identifier as the source wrote it; the source carries the
    line's column.
    """
    envelope = read_entity_envelope(path)
    by_column: dict[str, ClaimSource] = {}
    for row in iter_entity_evidence(path):
        source = by_column.get(row.column)
        if source is None:
            source = by_column[row.column] = claim_source(envelope, row)
        yield EvidenceEntry(row.field, row.target_key_value, row.raw_value, source)
