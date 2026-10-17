"""Lineage evidence files: a source saying a file was made from a parent (#583).

Where a slot evidence file says what a source wrote about one of a file's dimensions, a lineage
file says how a file was made: this file, from that parent (another file, or a sample by
``parent_key_type: biosample_id``), in a step the source names. Line 1 is the same
``EvidenceFileEnvelope``; every later line a ``LineageRow``, read and written through
``source_evidence``'s model-row reader and writer. The files go under their own root,
``data/lineage_evidence/``, in the slot root's generation layout, because every reader of
``data/source_evidence/`` reads each file there as slot lines.

**A line declares nothing** (contract 1.1): the activity and role are the activity map's (#584),
the parent's resolution reconcile's (#577), and a line carrying an answer is refused by name.
What the generated model cannot carry is :func:`check_row`'s, and ``parent_dataset`` never the
envelope's own target (#594); the envelope's kind is one of :data:`LINEAGE_SOURCE_TYPES`.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from .models import SOURCE_EXTERNAL_GROUND_TRUTH, SOURCE_REPOSITORY_ACTIVITY, SOURCE_REPOSITORY_METADATA
from .schema.classification_model import EvidenceFileEnvelope, LineageRow
from .source_evidence import (
    DEFAULT_SOURCE_EVIDENCE_ROOT,
    iter_model_rows,
    parse_iso_datetime,
    read_envelope_from,
    require_file_key,
    require_scoped_target,
    write_model_rows,
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
    require_file_key(envelope, where)
    parse_iso_datetime(envelope.fetched_at, "envelope fetched_at", where)
    if envelope.source_type not in LINEAGE_SOURCE_TYPES:
        raise ValueError(
            f"{where}: source_type {envelope.source_type!r} is not a lineage source ({sorted(LINEAGE_SOURCE_TYPES)})"
        )


def write_lineage_file(path: Path, envelope: EvidenceFileEnvelope, rows: Iterable[LineageRow]) -> int:
    """Write one lineage file, streaming, each row checked as :func:`iter_lineage` checks it; return how many lines."""
    return write_model_rows(path, envelope, rows, LineageRow, _check_envelope, _check_row_in)


def read_lineage_envelope(path: Path) -> EvidenceFileEnvelope:
    """A lineage file's envelope, from line 1 alone, checked as :func:`iter_lineage` checks it."""
    with path.open("rb") as f:
        envelope = read_envelope_from(path, f)
    _check_envelope(envelope, f"{path.name} line 1")
    return envelope


def iter_lineage(path: Path) -> Iterator[LineageRow]:
    """Every line of one lineage file after the envelope, streamed; ``ValueError`` naming the line that
    will not parse, carries an answer (:data:`_REFUSED_LINE_KEYS`) or breaks :func:`_check_row_in`."""
    return iter_model_rows(path, LineageRow, _REFUSED_LINE_KEYS, _check_envelope, _check_row_in)
