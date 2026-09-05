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

The one thing that must never happen is an excluded record reaching a
classification output: ``corpus_diff`` joins runs on ``(dataset_title, file_name,
md5sum)`` and normalizes a null md5 to the empty string, so two checksum-less rows
would key alike and could be reported as content-identical — the one claim a parity
table must never make without evidence (#375).

This module holds no intra-package imports on purpose: ``pipeline`` imports
:data:`MD5_RE` from here, and the shared loader that applies :func:`partition_records`
lives in ``pipeline`` (``load_classifiable_records``), so the dependency runs one way.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

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
    it is named — hence carrying every identity field the input contract defines
    besides the unusable checksum itself (``entry_id``, ``file_id``, ``file_name``,
    ``drs_uri``, ``dataset_title``, ``file_size``). Values are echoed as the record
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
        file_name = record.get("file_name")
        return cls(
            file_name="" if file_name is None else str(file_name),
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

        Tolerant on purpose: the report reads exclusions files written by earlier runs,
        and a row missing a key it did not carry must render rather than raise.
        """
        return cls(
            file_name=str(row.get("file_name") or ""),
            dataset_title=row.get("dataset_title"),
            entry_id=row.get("entry_id"),
            file_id=row.get("file_id"),
            drs_uri=row.get("drs_uri"),
            file_size=row.get("file_size"),
            reason=str(row.get("reason") or NO_CHECKSUM_REASON),
        )


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

    ``present`` distinguishes a run that excluded nothing (file written, empty list)
    from a run predating #376 (no file at all) — the report says different things
    about the two, and a bare empty list could not tell them apart.
    """

    files: list[ExcludedFile]
    total_input: int
    present: bool


def write_excluded(run_dir: Path, excluded: list[ExcludedFile], *, total_input: int) -> Path:
    """Write a run's exclusions to ``excluded_files.json``; returns the path.

    Written unconditionally, including when nothing was excluded: the file's presence
    is what lets a reader tell "this run excluded nothing" from "this run predates the
    exclusion". The ``metadata`` block carries the count, which is why the per-type
    ``RunMetadata`` blocks do not — exclusion is decided once over the whole input, so
    a per-type copy of a corpus-wide number would read as a per-type figure.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / EXCLUDED_FILE
    payload = {
        "metadata": {
            "total_input": total_input,
            "excluded": len(excluded),
            "complete": True,
        },
        "excluded": [e.to_dict() for e in excluded],
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


def read_excluded(run_dir: Path) -> ExcludedIndex:
    """Read a run's exclusions file, tolerating absence and unexpected shapes.

    A run directory with no exclusions file yields ``present=False`` and no files. A
    file whose ``excluded`` key is not a list, or whose rows are not dicts, yields the
    rows it can read and drops the rest — this is a report input, not a contract gate,
    so a malformed file must not stop the report that would show it.
    """
    path = run_dir / EXCLUDED_FILE
    if not path.is_file():
        return ExcludedIndex(files=[], total_input=0, present=False)
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        return ExcludedIndex(files=[], total_input=0, present=True)
    metadata = data.get("metadata")
    total_input = metadata.get("total_input", 0) if isinstance(metadata, dict) else 0
    rows = data.get("excluded", [])
    files = [ExcludedFile.from_dict(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return ExcludedIndex(
        files=files,
        total_input=total_input if isinstance(total_input, int) else 0,
        present=True,
    )
