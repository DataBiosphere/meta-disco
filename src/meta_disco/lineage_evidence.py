"""Lineage evidence files: a source saying a file was made from a parent (#583).

A slot evidence file (``source_evidence``) says what a source wrote about one of a
file's eight dimensions. A lineage evidence file says what a source wrote about how a
file was made: this file, from that parent — another file, or a sample
(``parent_key_type: biosample_id``) — in a step the source calls this. The
envelope on line 1 is the same ``EvidenceFileEnvelope``; every later line is a
``LineageRow``, the class the schema declares and gen-pydantic emits, used as it is.

**A separate root.** Lineage files go under ``data/lineage_evidence/``, never under
``data/source_evidence/``: every reader of the slot root — reconcile, the value map's
seeding and review queue, a run's evidence listing — reads each file there as slot
lines, and a lineage line is not one. The layout under the root is the slot root's
generation layout (``source_evidence.generation_dir``), so ``discover`` finds the
newest generation per dataset here too.

**A line declares nothing** (contract 1.1). ``raw_activity`` is what the source calls
the step, verbatim; the activity and role it means are the activity translation
table's (#584), and whether the parent is one of our files is reconcile's (#577). A
line carrying an answer is refused by name, as ``source_evidence`` refuses one on a
slot line.

**The rules the generated model cannot carry** are :func:`check_row`'s, run at write
and at read: at least one of ``parent`` and ``parent_source_identifier``;
``parent_key_type`` exactly when ``parent``; ``raw_activity_column`` exactly when
``raw_activity``; ``parent_dataset`` only with ``parent``; and (``_check_row_in``, which
has the envelope) ``parent_dataset`` never the envelope's own target dataset (#594). The envelope's kind must be one of :data:`LINEAGE_SOURCE_TYPES`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path

from pydantic import ValidationError

from .models import SOURCE_EXTERNAL_GROUND_TRUTH, SOURCE_REPOSITORY_ACTIVITY, SOURCE_REPOSITORY_METADATA
from .schema.classification_model import EvidenceFileEnvelope, LineageRow
from .source_evidence import (
    DEFAULT_SOURCE_EVIDENCE_ROOT,
    EVIDENCE_FILE_SUFFIX,
    decode_line,
    parse_iso_datetime,
    read_envelope_from,
    require_scoped_target,
    write_ndjson,
)

DEFAULT_LINEAGE_EVIDENCE_ROOT = DEFAULT_SOURCE_EVIDENCE_ROOT.parent / "lineage_evidence"

# The kinds a lineage file may declare: a submitter's table (T2T's sample rows, IGVF's
# `file.derived_from`), the repository's own record of a step (`anvil_activity`), and an
# archive's run record (ENA's, naming whose reads an alignment holds; `ena_lineage`, #594).
LINEAGE_SOURCE_TYPES = frozenset({SOURCE_REPOSITORY_METADATA, SOURCE_REPOSITORY_ACTIVITY, SOURCE_EXTERNAL_GROUND_TRUTH})

# Members a line would carry if it declared an answer, each with why it may not.
_REFUSED_LINE_KEYS = {
    "activity": "which activity a raw_activity means is the activity translation table's (#584)",
    "role": "which role a parent takes is the activity translation table's (#584)",
    "value": "a lineage line maps nothing onto our vocabulary (contract 1.1, 1.3)",
    "status": "a status is a rule's to declare, never a source's (contract 3.6)",
    "claim_state": "a lineage line is an observation, not a claim",
    "rule_id": "there is no rule at import time; the step reconcile will build cites one (#577)",
    "tier": "imported evidence does not compete on the rule tiers (#391)",
    "parent_key": "the parent's record key is found by reconcile (#577); a line names the parent as the source did",
    "source_type": "one file is one kind of source, so it is on the envelope, not on every line",
}


def check_row(row: LineageRow, where: str) -> None:
    """The rules gen-pydantic drops from ``LineageRow``, or a ``ValueError`` naming ``where``."""
    if row.parent is None and row.parent_source_identifier is None:
        raise ValueError(f"{where}: names no parent — neither parent nor parent_source_identifier")
    if (row.parent is None) != (row.parent_key_type is None):
        raise ValueError(f"{where}: parent_key_type is present exactly when parent is")
    if (row.raw_activity is None) != (row.raw_activity_column is None):
        raise ValueError(f"{where}: raw_activity_column is present exactly when raw_activity is")
    if row.parent_dataset is not None and row.parent is None:
        raise ValueError(f"{where}: parent_dataset names where parent is, so it is present only with parent")


def _check_row_in(row: LineageRow, envelope: EvidenceFileEnvelope, where: str) -> None:
    """:func:`check_row`, and a ``parent_dataset`` other than the child's own (the envelope's target)."""
    check_row(row, where)
    if row.parent_dataset is not None and row.parent_dataset == envelope.target.dataset:
        raise ValueError(f"{where}: parent_dataset is the child's own dataset; it names only another")


def _check_envelope(envelope: EvidenceFileEnvelope, where: str) -> None:
    require_scoped_target(envelope, where)
    parse_iso_datetime(envelope.fetched_at, "envelope fetched_at", where)
    if envelope.source_type not in LINEAGE_SOURCE_TYPES:
        raise ValueError(
            f"{where}: source_type {envelope.source_type!r} is not a lineage source ({sorted(LINEAGE_SOURCE_TYPES)})"
        )


def write_lineage_file(path: Path, envelope: EvidenceFileEnvelope, rows: Iterable[LineageRow]) -> int:
    """Write one lineage file, streaming; return the number of lines after the envelope.

    Written through ``source_evidence.write_ndjson``, the slot writer's own path: to a
    temporary name, renamed into place only once every row is out. Every row is checked
    (:func:`check_row`, and its ``parent_dataset`` against the envelope's dataset) as it is
    written, so this cannot write a file :func:`iter_lineage` refuses.
    """
    if path.suffix != EVIDENCE_FILE_SUFFIX:
        raise ValueError(f"{path.name}: a lineage file must end in {EVIDENCE_FILE_SUFFIX}, or discover never finds it")
    _check_envelope(envelope, "lineage file envelope")
    return write_ndjson(
        path, envelope, (_line(row, envelope, f"{path.name} row {n}") for n, row in enumerate(rows, start=1))
    )


def _line(row: LineageRow, envelope: EvidenceFileEnvelope, where: str) -> dict:
    if not isinstance(row, LineageRow):
        raise ValueError(f"{where}: is a {type(row).__name__}, not a LineageRow")
    _check_row_in(row, envelope, where)
    return row.model_dump(exclude_none=True)


def read_lineage_envelope(path: Path) -> EvidenceFileEnvelope:
    """A lineage file's envelope, from line 1 alone, checked as :func:`iter_lineage` checks it."""
    with path.open("rb") as f:
        envelope = read_envelope_from(path, f)
    _check_envelope(envelope, f"{path.name} line 1")
    return envelope


def iter_lineage(path: Path) -> Iterator[LineageRow]:
    """Every line of one lineage file after the envelope, in file order, streamed.

    A blank line is passed over. Any other line that will not parse, carries an
    answer (:data:`_REFUSED_LINE_KEYS`), carries a member ``LineageRow`` does not
    have, breaks :func:`check_row`, or names the child's own dataset as ``parent_dataset``
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
                row = LineageRow.model_validate(block)
            except ValidationError as exc:
                faults = "; ".join(
                    f"{' '.join(str(p) for p in e['loc']) or 'line'}: "
                    f"{'unknown member' if e['type'] == 'extra_forbidden' else e['msg']}"
                    for e in exc.errors()
                )
                raise ValueError(f"{where}: {faults}") from None
            _check_row_in(row, envelope, where)
            yield row
