"""Typed record views passed past the pipeline's load boundary (#172).

The pipeline used to pass raw ``dict``s downstream and re-derive field safety at
every consumer, because it validated a record against the Pydantic contract and
then threw the model away and kept the dict (#171's scattered ``str(... or "")``
guards were point fixes for that one root cause). Instead, ``run()`` splits the
filtered records into two typed streams at the boundary:

* **valid** (no classifier-relevant contract violation) -> :class:`ClassifierRecord`,
  whose classifier-relevant fields are ``str``/``int`` by construction, so the
  fetch/classify path reads typed attributes with no per-field guards.
* **invalid** (a classifier-relevant field violates the input contract, the drift
  #161 exists to catch) -> :class:`InvalidRecord`, which coerces the echoed string
  identity fields in one constructor and carries the blocking reasons for the
  ``validation_failed`` row.

The split criterion is ``classification_blocking_reasons`` (unchanged from #161):
a record that violates the full contract only on a field the classifier never
reads (e.g. ``drs_uri``) is *not* diverted — it still classifies, and the
whole-corpus ``validate_metadata`` gate reports that drift. So the "valid" stream
is modeled over exactly the classifier-relevant fields, not the full contract.

Both classes expose the same six identity attributes (``file_name``,
``file_format``, ``file_md5sum``, ``file_size``, ``dataset_title``, ``entry_id``),
so ``_build_record`` and the work-list steps read them uniformly regardless of
stream.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any


def _coerce_identity(value: Any) -> str:
    """Stringify a drifted identity value for echo; null (``None``) becomes ``""``.

    Distinguishes null from a falsy-but-present value on purpose: a ``str(value or
    "")`` would collapse ``0``/``False`` to ``""`` and lose the drifted value, so a
    ``file_name`` of ``0`` here becomes ``"0"``, not ``""``. Only genuine ``None``
    (absent/null) maps to the empty string.
    """
    return "" if value is None else str(value)


@dataclass(frozen=True)
class ClassifierRecord:
    """A filtered record whose classifier-relevant fields passed the input contract.

    Built only from a record with no ``classification_blocking_reasons``, so
    ``file_name``/``file_format`` are ``str``, ``file_size`` is a non-negative
    ``int``, and ``file_md5sum`` is a well-formed md5 ``str`` — all by construction.
    That post-condition is what lets the fetch/classify path drop the per-field
    guards #171 added.

    ``dataset_title``/``entry_id`` are *not* classifier-relevant, so a record with
    either drifted still reaches the valid stream. They are echoed into the output
    row untouched — typed ``Any`` and passed through as-is, exactly as the raw-dict
    path did.
    """

    file_name: str
    file_format: str
    file_size: int
    file_md5sum: str
    dataset_title: Any
    entry_id: Any

    @classmethod
    def from_record(cls, record: dict) -> ClassifierRecord:
        """Build from a raw record already known to have no blocking reasons.

        The four classifier-relevant fields are read by subscript, not ``.get(...)
        or ""``: the caller's blocking check guarantees each is present and
        well-typed, so a missing/mistyped value here is a bug in the caller, not
        input to defend against (CLAUDE.md error-handling philosophy). A ``KeyError``
        or wrong type surfacing here means the split routed a record it should not
        have.
        """
        return cls(
            file_name=record["file_name"],
            file_format=record["file_format"],
            file_size=record["file_size"],
            file_md5sum=record["file_md5sum"],
            dataset_title=record.get("dataset_title"),
            entry_id=record.get("entry_id"),
        )


@dataclass(frozen=True)
class InvalidRecord:
    """A filtered record whose classifier-relevant fields violate the input contract.

    Diverted at the load boundary and never fetched or classified (#161): it carries
    the identity fields for the ``validation_failed`` output row and progress label,
    plus the blocking ``reasons`` used as that row's evidence. Like
    ``ClassifierRecord`` it exposes all six identity attributes ready to echo —
    ``file_name``/``file_format`` are coerced to ``str`` in :meth:`from_record`
    (the two fields downstream does string operations on), the rest are echoed as
    the record carried them, since a ``validation_failed`` row may carry their
    drifted (non-string) types.
    """

    file_name: str
    file_format: str
    file_md5sum: Any
    file_size: Any
    dataset_title: Any
    entry_id: Any
    reasons: list[str]

    @classmethod
    def from_record(cls, record: dict, reasons: list[str]) -> InvalidRecord:
        """Build from a raw record whose classifier-relevant fields may be drifted.

        ``file_name``/``file_format`` may be null (present-but-None) or a drifted
        non-string (an int); ``_coerce_identity`` maps null to ``""`` and stringifies
        any other value — the sole coercion site the #171 point fixes are replaced
        by — so neither can raise in the downstream path/extension operations or the
        progress-label slice.
        """
        return cls(
            file_name=_coerce_identity(record.get("file_name")),
            file_format=_coerce_identity(record.get("file_format")),
            file_md5sum=record.get("file_md5sum"),
            file_size=record.get("file_size"),
            dataset_title=record.get("dataset_title"),
            entry_id=record.get("entry_id"),
            reasons=reasons,
        )


@dataclass(frozen=True)
class OutputRecord:
    """The per-file output envelope: identity fields wrapping a classifications payload.

    The single shape the pipeline writes per record. Both producers construct it —
    the batch path (``_build_record`` over a ``ClassifierRecord``/``InvalidRecord``
    work item) and the single-file path (``classify_single``) — and serialize through
    ``to_dict``, so the seven-key envelope can no longer drift between them (#204).

    Identity typing mirrors the two paths it is built from: ``file_name`` is ``str``
    on both (the batch work item types it; ``classify_single`` defaults it to ``""``).
    ``file_format`` is ``str`` on the batch path but ``str | None`` on the single-file
    path (its argument is optional). The remaining fields — ``md5sum`` (echoed from
    ``file_md5sum``), ``file_size``, ``dataset_title``, ``entry_id`` — are passed
    through as carried, so they are ``Any``: the ``validation_failed`` path may carry
    drifted (non-string) values, and the classifiable path's guarantee already lives
    upstream in ``ClassifierRecord``. This record does no string operations on the
    identity fields (``to_dict`` only echoes them), so the looser typing is safe.
    ``classifications`` is the dimensions payload plus any per-type extras a classifier
    merged into it (e.g. the fastq scalar hints), which live inside this dict, never as
    new envelope keys.
    """

    # Field order is the serialized envelope order — ``to_dict`` derives the output
    # dict from these fields, so the two cannot drift and a new field is emitted
    # automatically. Every field name is also its output key.
    file_name: str
    md5sum: Any
    file_size: Any
    file_format: str | None
    dataset_title: Any
    classifications: dict
    entry_id: Any

    @classmethod
    def from_work_item(cls, item: ClassifierRecord | InvalidRecord, classifications: dict) -> OutputRecord:
        """Build from a parsed work item and its classifications payload.

        Reads the six identity attributes both streams expose (see the module
        docstring), so it is agnostic to which stream produced ``item``.
        """
        return cls(
            file_name=item.file_name,
            file_format=item.file_format,
            md5sum=item.file_md5sum,
            file_size=item.file_size,
            dataset_title=item.dataset_title,
            entry_id=item.entry_id,
            classifications=classifications,
        )

    @classmethod
    def from_single(
        cls,
        *,
        md5sum: str,
        file_name: str,
        file_size: int | None,
        file_format: str | None,
        classifications: dict,
    ) -> OutputRecord:
        """Build from a standalone ``classify_single`` call (no work item, no source record).

        ``dataset_title``/``entry_id`` have no source here and serialize as ``None`` —
        the envelope's one canonical shape, which is why the single-file path's output
        carries the same seven keys as the batch path.
        """
        return cls(
            file_name=file_name,
            file_format=file_format,
            md5sum=md5sum,
            file_size=file_size,
            dataset_title=None,
            entry_id=None,
            classifications=classifications,
        )

    def to_dict(self) -> dict:
        """Serialize to the output envelope dict (the seven-key shape written to JSON).

        Derived from the dataclass fields (a shallow copy — ``classifications`` is not
        deep-copied), so every field is emitted, in declaration order, and ``to_dict``
        cannot drift from the field list.
        """
        return {f.name: getattr(self, f.name) for f in fields(self)}
