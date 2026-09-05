"""Records excluded from classification because they carry no usable checksum (#376).

A file with no well-formed ``file_md5sum`` cannot be processed at all: the AnVIL
fetcher builds its content URL from the md5 (``fetchers.py``) and the evidence cache
is keyed by md5 alone (``evidence.get_evidence_path``). Such a record is never
fetched, never cached, and never classified — so it is excluded here rather than
written as a row that misrepresents itself.

This is deliberately *not* the ``dropped`` concept #155 retired. That decision was
made because a missing row is indistinguishable from a file that was never seen —
an observability argument. Every excluded record is written to
``excluded_files.json`` in the run directory and rendered individually by the
unprocessable report (``unprocessable.py``), which answers that argument directly
where a silent drop did not.

Excluding and recording are one act, not two: the shared loader that applies the
predicate is also what writes the file, so a producer cannot shed a record without
naming it. That holds for a standalone ``make classify-bam`` as much as for a full
run — an earlier design had only the orchestrator record, which left every per-type
target silently dropping.

The one thing that must never happen is an excluded record reaching a
classification output: ``corpus_diff`` joins runs on ``(dataset_title, file_name,
md5sum)`` and normalizes a null md5 to the empty string, so two checksum-less rows
would key alike and could be reported as content-identical — the one claim a parity
table must never make without evidence (#375).

This module depends only on ``records`` (for the shared identity coercion), so
``pipeline`` can import :data:`MD5_RE` from here without a cycle. The shared loader
that applies :func:`partition_records` lives in ``pipeline``
(``load_classifiable_records``), so the dependency runs one way.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, TypeGuard

from .records import coerce_identity

# A well-formed md5: lowercase hex, 32 chars, and nothing else. The single definition
# of the shape. Only such a value can address the S3 mirror or key real cached evidence,
# which is why the trailing anchor is ``\Z`` and not the contract's ``$``: Python's
# ``$`` also matches before a trailing newline, so ``"<32 hex>\n"`` would pass and then
# be interpolated into a URL and a cache path (``md5[:2]`` / ``{md5}.json``). This is
# deliberately one notch stricter than the input contract's ``file_md5sum`` pattern
# (``schema/metadata.yaml``), which shares that ``$`` looseness: such a record passes
# the gate and is still excluded here, which is the safe direction of disagreement.
MD5_RE = re.compile(r"^[0-9a-f]{32}\Z")

# Name of the per-run exclusions file, written into the run directory beside the
# classification outputs. Deliberately NOT in ``output_utils.CLASSIFICATION_FILES``:
# an excluded file is not a classification, and the coverage, validation,
# consistency and corpus-diff readers must never treat it as one.
EXCLUDED_FILE = "excluded_files.json"

# The single reason this module excludes a record. Rendered in the report and stored
# on every ``ExcludedFile``; a second reason would come with its own constant.
NO_CHECKSUM_REASON = "no usable file_md5sum"


def _is_count(value: Any) -> TypeGuard[int]:
    """Whether ``value`` is a usable record count: a non-negative, non-bool ``int``.

    ``bool`` is excluded explicitly because it subclasses ``int`` in Python, so a
    ``total_input`` of ``True`` would otherwise pass as the count 1. A ``TypeGuard`` so a
    caller that has checked a value can then use it as the ``int`` it is.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def has_usable_checksum(record: Any) -> bool:
    """Whether ``record`` carries a checksum the run can actually process.

    True only for a ``dict`` whose ``file_md5sum`` is a ``str`` matching
    :data:`MD5_RE`. Absent, null, empty, uppercase, wrong-length and non-string
    values all return False, as does a non-dict record — which cannot carry a
    checksum at all, and which the downstream producers read with ``.get`` and
    would raise on.
    """
    if not isinstance(record, dict):
        return False
    md5 = record.get("file_md5sum")
    return isinstance(md5, str) and MD5_RE.match(md5) is not None


@dataclass(frozen=True)
class ExcludedFile:
    """One record excluded from classification, with whatever identity it does have.

    An excluded record appears in no classification output, so this is the only place
    it is named. It carries the four identifiers the contract defines besides the
    unusable checksum (``entry_id``, ``file_id``, ``file_name``, ``drs_uri``) plus the
    two fields that make a listing readable (``dataset_title``, which the report groups
    by, and ``file_size``). ``dataset_id`` and ``file_format`` are deliberately left
    out: neither adds reach for a person chasing the file. Values are echoed as the record
    carried them and typed ``Any``: a record excluded for a drifted md5 may well have
    drifted elsewhere too, and this row exists to show that, not to normalize it.
    ``file_name`` is the exception — the report groups and sorts on it, so it is
    coerced to ``str``.
    """

    # Field order is the serialized order — ``to_dict`` derives the output dict from
    # these fields, so the two cannot drift and a new field is emitted automatically.
    file_name: str
    dataset_title: Any
    entry_id: Any
    file_id: Any
    drs_uri: Any
    file_size: Any
    reason: str

    @classmethod
    def from_record(cls, record: Any, reason: str = NO_CHECKSUM_REASON) -> ExcludedFile:
        """Build from a raw input record, tolerating any shape.

        ``record`` may be a non-dict (garbage where an object was expected), in which
        case every identity field is ``None`` and ``file_name`` the empty string —
        there is nothing else to say about it. ``None`` maps to ``None`` rather than
        ``""`` for every field but ``file_name``, so "the record had no entry_id" stays
        distinguishable from "it had an empty one".

        ``file_name`` goes through ``records.coerce_identity``, the same null-to-``""``
        rule the ``validation_failed`` row echoes drifted identities by, so the two
        output paths cannot disagree about how a drifted name is rendered.
        """
        if not isinstance(record, dict):
            return cls(
                file_name="",
                dataset_title=None,
                entry_id=None,
                file_id=None,
                drs_uri=None,
                file_size=None,
                reason=reason,
            )
        return cls(
            file_name=coerce_identity(record.get("file_name")),
            dataset_title=record.get("dataset_title"),
            entry_id=record.get("entry_id"),
            file_id=record.get("file_id"),
            drs_uri=record.get("drs_uri"),
            file_size=record.get("file_size"),
            reason=reason,
        )

    def to_dict(self) -> dict:
        """Serialize to the exclusions-file row shape.

        Derived from the dataclass fields (a shallow copy), so every field is emitted,
        in declaration order, and ``to_dict`` cannot drift from the field list.
        """
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, row: dict) -> ExcludedFile:
        """Rebuild from a serialized row, defaulting any key the file omits.

        A serialized row has the same key names as the record it was built from, so this
        reuses :meth:`from_record` rather than re-enumerating the fields — which is what
        keeps adding a field to this class a one-line change. It only has to recover the
        ``reason``, which the row carries and a raw record does not.

        Tolerant on purpose: the report reads exclusions files written by earlier runs,
        and a row missing a key it did not carry must render rather than raise.
        """
        return cls.from_record(row, reason=str(row.get("reason") or NO_CHECKSUM_REASON))


def partition_records(records: list) -> tuple[list[dict], list[ExcludedFile]]:
    """Split input records into the classifiable ones and the excluded ones.

    Order is preserved within each side. The classifiable list holds the original
    record objects untouched (they are handed straight to the producers); the excluded
    side holds :class:`ExcludedFile` views, since the raw record is never processed
    again and only its identity is worth keeping.

    Every element of the classifiable side is a ``dict``: :func:`has_usable_checksum`
    requires one, so a non-dict input element always lands on the excluded side. That
    is what narrows the loaders' ``list`` to ``list[dict]``.
    """
    classifiable = []
    excluded = []
    for record in records:
        if has_usable_checksum(record):
            classifiable.append(record)
        else:
            excluded.append(ExcludedFile.from_record(record))
    return classifiable, excluded


@dataclass(frozen=True)
class ExcludedIndex:
    """A run's exclusions file, as read back by the report.

    Three states, not two, because "we know this run excluded nothing" is a different
    claim from "we cannot tell what this run excluded", and reporting the second as the
    first is exactly the kind of unevidenced assertion #376 exists to stop:

    * ``present=False`` — no file at all, so a run predating #376.
    * ``present=True, readable=False`` — a file that could not be parsed, or whose shape
      is not the one written. Whatever rows were recoverable are in ``files``, but no
      count from it can be trusted.
    * ``present=True, readable=True`` — the counts are known, including a known zero.

    Read :attr:`count` rather than ``len(files)`` whenever the question is "how many did
    this run exclude?" — see that property for why.
    """

    files: list[ExcludedFile]
    total_input: int
    present: bool
    readable: bool = True

    @property
    def counts_known(self) -> bool:
        """Whether this index can support a stated count (as opposed to "unknown")."""
        return self.present and self.readable

    @property
    def count(self) -> int | None:
        """How many files this run excluded, or ``None`` when that is not known.

        **Every consumer of this number reads it here**, not ``len(self.files)``. The
        list holds the rows that were *recoverable*, which is empty both for a run that
        excluded nothing and for one whose record is absent or damaged — so its length
        silently turns "unknown" into a confident zero. Returning ``None`` forces each
        consumer to answer the question rather than default it, which is what four
        review rounds of this exact mistake argued for.
        """
        return len(self.files) if self.counts_known else None


def write_excluded(run_dir: Path, excluded: list[ExcludedFile], *, total_input: int) -> Path:
    """Write a run's exclusions to ``excluded_files.json``; returns the path.

    Written unconditionally, including when nothing was excluded: the file's presence
    is what lets a reader tell "this run excluded nothing" from "this run predates the
    exclusion". The ``metadata`` block carries the count, which is why the per-type
    ``RunMetadata`` blocks do not — exclusion is decided once over the whole input, so
    a per-type copy of a corpus-wide number would read as a per-type figure.

    **Written by every producer, concurrently, and that is safe.** Each producer of a
    run writes this as it loads (``pipeline.load_classifiable_records``), and a full
    ``make classify`` runs nine of them in parallel into one run directory. They all
    read the same input and apply the same predicate, so they all compute the same
    content — the writes are idempotent, and the only hazard is a reader catching a
    half-written file. Hence the write-then-``os.replace``: the rename is atomic within
    a directory, so a concurrent reader sees either the previous file or a complete new
    one, never a partial one. Last writer wins, and every writer had the same answer.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / EXCLUDED_FILE
    payload = {
        "metadata": {
            "total_input": total_input,
            "excluded": len(excluded),
            # A constant, not state: this file is replaced atomically, so there is no
            # partial case for it to describe. It is emitted so the envelope matches the
            # classification outputs beside it, whose readers expect the key.
            "complete": True,
        },
        "excluded": [e.to_dict() for e in excluded],
    }
    # Write to a sibling temp file, then rename onto the target: see the docstring for
    # why. mkstemp (not NamedTemporaryFile) because the file must outlive its handle to
    # be renamed; it shares a directory with the target so the rename stays within one
    # filesystem, and is removed if anything fails before it.
    fd, tmp_name = tempfile.mkstemp(dir=run_dir, prefix=f".{EXCLUDED_FILE}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, indent=2)
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return path


def read_excluded(run_dir: Path) -> ExcludedIndex:
    """Read a run's exclusions file, tolerating absence and unexpected shapes.

    A run directory with no exclusions file yields ``present=False`` and no files.

    A file that exists but cannot be trusted yields ``readable=False`` along with
    whatever rows were recoverable. That covers unparseable JSON, a non-dict envelope, an
    ``excluded`` key that is missing or not a list, a row within it that is not a dict,
    and a ``metadata`` block that is absent or disagrees with those rows — every
    departure from the shape :func:`write_excluded` emits. It never raises: this
    is a report input, not a contract gate, so a malformed file must not stop the report
    that would show it. But it must not be *read* as a zero either, which is why
    ``readable`` exists rather than the rows simply coming back empty.

    :func:`write_excluded` replaces the file atomically, so a torn write is not the
    expected source of an unreadable file — a hand-edited or externally truncated one is.
    """
    path = run_dir / EXCLUDED_FILE
    if not path.is_file():
        return ExcludedIndex(files=[], total_input=0, present=False)
    unreadable = ExcludedIndex(files=[], total_input=0, present=True, readable=False)
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return unreadable
    if not isinstance(data, dict):
        return unreadable
    rows = data.get("excluded")
    if not isinstance(rows, list):
        return unreadable

    # Rows that are not records mean a damaged file, so no count from it can be trusted —
    # but the rows that did survive are still worth showing, since no other output holds
    # them. Hence recovering them rather than returning the empty `unreadable`.
    files = [ExcludedFile.from_dict(row) for row in rows if isinstance(row, dict)]
    recovered = ExcludedIndex(files=files, total_input=0, present=True, readable=False)
    if len(files) != len(rows):
        return recovered

    # The metadata block gets the same scrutiny as the rows. `write_excluded` always
    # emits `total_input` and an `excluded` count, so a file missing either — or carrying
    # one that disagrees with the rows beside it — was not written by this code and has
    # been edited or damaged in a way JSON parsing cannot see. Reporting "0 checked" from
    # such a file would be exactly the confident-but-wrong statement `readable` exists to
    # prevent, so it is unreadable rather than a defaulted zero.
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return recovered
    total_input = metadata.get("total_input")
    if not _is_count(total_input) or metadata.get("excluded") != len(files) or not _is_count(metadata["excluded"]):
        return recovered
    return ExcludedIndex(files=files, total_input=total_input, present=True)
