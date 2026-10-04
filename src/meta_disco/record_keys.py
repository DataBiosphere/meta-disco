"""The field each source guarantees unique per file, and its readers (#446).

Declared here, below ``pipeline``, so that a module ``pipeline`` reaches through the
file-type registry (``edges``, ``producer_steps``) can read a record's key without
importing ``pipeline`` back (#615).
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import NamedTuple, TypeGuard

from .azul_manifest import PUBLISHED_TABLE as ANVIL_PUBLISHED_TABLE
from .azul_manifest import REPOSITORY as ANVIL_REPOSITORY
from .models import JOIN_KEY_FILE_ID, JOIN_KEY_FILE_MD5SUM
from .records import OUTPUT_MD5SUM_FIELD


class RecordKey(NamedTuple):
    """The field a source guarantees unique per file, in both spellings a run uses.

    ``input_field`` is its name on an input record; ``output_field`` its name on the
    output row a producer writes. They differ only where ``records.OutputRecord``
    renames a field on the way out (``file_md5sum`` becomes ``md5sum``).
    """

    input_field: str
    output_field: str


HPRC_REPOSITORY = "hprc"

# One declaration per source of the identity that names a file exactly once in that
# source's snapshot, keyed by the ``repository`` its input envelope carries (#446). It
# serves the input gate (``scripts/validate_metadata.py``, which checks the key is
# unique), the catch-all producer's skip set, an edge's ``parent_key`` (``edges``, for the
# index producer, the catch-all and the VCF producer's header steps in
# ``producer_steps``), the post-run one-row-per-file check (#445) and reconcile, and each
# reads it through :func:`record_key`, never a hard-coded field, because the unique field
# differs by source:
#
# - AnVIL: ``file_id``, the repository's own durable identifier — unique on every
#   record and unchanged by a catalog re-index (#433), which is why the duplicate check
#   chose it. Not ``entry_id``, equally unique but regenerated per index: one key serves
#   every reader only if it is the durable one. Not ``file_name``, which identifies a
#   file only about 60% of the time there.
# - HPRC: ``file_md5sum``. The HPRC catalogs issue no file identifier and none is
#   minted — ``entry_id``, ``file_id`` and ``drs_uri`` are Azul's catalog identity and
#   stay null on an HPRC record. What the source does guarantee unique is the file's
#   URL, and ``scripts/classify_hprc_files.py`` writes its hash into ``file_md5sum``.
#   So this key is a hash of the full URL, not a content checksum: identical bytes at
#   two paths are two keys, and the value cannot be compared with a real md5.
SOURCE_RECORD_KEYS: dict[str, RecordKey] = {
    ANVIL_REPOSITORY: RecordKey(JOIN_KEY_FILE_ID, JOIN_KEY_FILE_ID),
    HPRC_REPOSITORY: RecordKey(JOIN_KEY_FILE_MD5SUM, OUTPUT_MD5SUM_FIELD),
}

# The other per-repository declaration: the table that is the repository's published
# source (#497, contract 7.12 — why exactly one, and why not the compact manifest, is
# there), keyed like the record keys by the repository whose files it is about. Read by
# the run's preflight (`source_evidence.require_one_published_source`), which must judge
# files no map wrote; an importer reads its own repository's entry from that
# repository's module (`azul_manifest.PUBLISHED_TABLE`) rather than this dict, so it
# need not import the classification stack. HPRC's is not declared yet.
PUBLISHED_TABLES: dict[str, str] = {
    ANVIL_REPOSITORY: ANVIL_PUBLISHED_TABLE,
}


def _declared_key(metadata: dict) -> RecordKey | None:
    """The :data:`SOURCE_RECORD_KEYS` entry for the repository the envelope names, or
    ``None`` where it names no declared one. The one lookup behind :func:`key_field`,
    which tolerates ``None``, and :func:`record_key`, which refuses it."""
    repository = metadata.get("repository")
    return SOURCE_RECORD_KEYS.get(repository) if isinstance(repository, str) else None


def key_field(metadata: dict) -> str | None:
    """The input-record field the envelope's repository declares as its record key, or
    ``None`` where the envelope names no declared repository (an ``.ndjson`` input, a
    pre-#424 snapshot). For a diagnostic that names a record: the durable identity
    differs by source (AnVIL's ``file_id``, HPRC's ``file_md5sum``, per
    :data:`SOURCE_RECORD_KEYS`), so no diagnostic may hard-code one. Unlike
    :func:`record_key` this does not refuse — a report over a file with no usable
    envelope still wants to run, and labels its records as unidentified."""
    key = _declared_key(metadata)
    return None if key is None else key.input_field


def record_key(metadata: dict, input_path: Path) -> RecordKey:
    """The :data:`SOURCE_RECORD_KEYS` entry for the repository an input envelope names.

    Raises ``ValueError`` naming ``input_path`` when the envelope names no repository —
    an ``.ndjson`` input, or a JSON snapshot written before #424 added the field — or
    one the table does not declare. Unlike :func:`key_field`, this cannot be
    ``None``: a reader that needs the key cannot do its job without one, and guessing
    a field is how a file gets a second row.
    """
    key = _declared_key(metadata)
    if key is None:
        repository = metadata.get("repository")
        raise ValueError(
            f"{input_path}: the input envelope names repository {repository!r}, which declares no "
            f"record key — the field that identifies a file uniquely, which a run needs to know "
            f"which files are already classified and to check that no file has two rows. Declare "
            f'`"metadata": {{"repository": ...}}` as one of {sorted(SOURCE_RECORD_KEYS)} '
            f"(record_keys.SOURCE_RECORD_KEYS)."
        )
    return key


def is_key_value(value) -> TypeGuard[str]:
    """Whether ``value`` can serve as a record key: a non-empty string, nothing else."""
    return isinstance(value, str) and bool(value)


def keyed_rows(paths: Iterable[Path], key: RecordKey) -> Iterator[tuple[str, dict]]:
    """``(key value, row)`` for every row of the ``*_classifications.json`` files named.

    For a reader keyed on :data:`SOURCE_RECORD_KEYS` over another producer's output.
    The key is read under its output spelling. A row without it raises rather than
    being skipped, because a skip is silent: the caller sees one row fewer and cannot
    tell. How a row comes to lack it differs by source. AnVIL's ``file_id`` is
    deliberately *not* classifier-relevant (``records.ClassifierRecord``), so a drifted
    one reaches the valid stream and is echoed into a producer's row untouched;
    ``make validate-metadata`` rejects it before ``make classify``, so seeing one means
    that gate was bypassed. HPRC's key is the checksum field, which the shared load
    excludes when unusable (#376), so a row without one means the producer omitted the
    field.

    A path that is not a file yields nothing: a run writes only the producers that ran.
    The envelope's record list is read under ``classifications``, then a legacy
    ``results``, the precedence ``output_utils._records_in`` uses; unlike that tolerant
    reader, a file of any other shape — no list under either key, a bare list, a
    non-dict row — raises rather than reading as empty, since a reader keyed on identity
    cannot count a row it did not read.
    """
    for path in paths:
        if not path.is_file():
            continue
        with path.open() as f:
            data = json.load(f)
        rows = data.get("classifications", data.get("results")) if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError(
                f"{path}: not a classification file — no list under `classifications` (or the "
                f"legacy `results`); a reader keyed on identity cannot treat that as empty."
            )
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{path}: classification row is not an object: {row!r}")
            value = row.get(key.output_field)
            if not is_key_value(value):
                raise ValueError(
                    f"{path}: classification row for {row.get('file_name')!r} has "
                    f"{key.output_field} {value!r}; this reader keys on it and cannot skip the "
                    f"row. Either the input carried a drifted {key.input_field} that no gate "
                    f"refused, or the producer that wrote this file omitted the field and "
                    f"needs re-running."
                )
            yield value, row


def input_key_value(record: dict, key: RecordKey, purpose: str) -> str:
    """The source's key as an input record carries it, or a ``ValueError``.

    The input side of :func:`keyed_rows`: a producer that compares its input records
    against rows keyed that way. A drifted key here would match nothing, silently, so
    it raises instead. ``purpose`` completes "this producer keys on it to ..." in the
    message. The input gate rejects such a record before ``make classify``; reaching
    here means that gate was bypassed.
    """
    value = record.get(key.input_field)
    if not is_key_value(value):
        raise ValueError(
            f"input record for {record.get('file_name', '')!r} has {key.input_field} {value!r}; "
            f"this producer keys on it to {purpose}. `make validate-metadata` rejects this "
            f"before `make classify` runs."
        )
    return value


def repeated_key_values(records: list, key: RecordKey) -> dict[str, int]:
    """Values of the source's key that more than one input record carries, with counts.

    What the declaration in :data:`SOURCE_RECORD_KEYS` promises and this checks: the
    key is unique per file in the source's snapshot. Values that are not non-empty
    strings are not counted — the record contract reports those. Read by the input
    gate (``scripts/validate_metadata.py``), so a repeated key stops a run before it
    starts rather than failing it at the post-run one-row-per-file check (#445).
    """
    counts = Counter(
        value
        for record in records
        if isinstance(record, dict)
        for value in (record.get(key.input_field),)
        if is_key_value(value)
    )
    return {value: n for value, n in counts.items() if n > 1}
