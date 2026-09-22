"""Derive the classifier's input from a TDR snapshot's tables, read in place from
BigQuery or through the Azul verbatim manifest (issue #499).

The input used to be derivable only from Azul's compact manifest — its harmonized
join, which exists only once Azul has indexed the snapshot. The system of record is
the snapshot itself, in the Terra Data Repository, and dev and prod runs happen from
a checkout inside a Terra workspace (decision of 2026-09-21 on #478), so the input
is now defined as **a snapshot's tables in TDR's own column names**, however they
arrived. That is the one canonical shape here, :class:`SnapshotTables`, and
:func:`derive_records` turns it into input records; the compact path
(``azul_manifest.record_from_compact_manifest_row``) is untouched beside it.

The interface
-------------
A :class:`SnapshotTables` names the snapshot's tables and streams one table's rows,
each a dict keyed by TDR's column names. Two readers implement it:

- :class:`TdrDirect` reads the snapshot in place from BigQuery through the query
  layer in :mod:`meta_disco.tdr`. **What it needs from its environment**: a Google
  identity with BigQuery reader access on the snapshot — Application Default
  Credentials, the workspace's own inside Terra — and the ``tdr`` extra to build a
  live client; that module's docstring is the authority on both, and nothing here
  restates it. The client is injected, so this module and its tests run without
  either. Every table it streams is checked against the table's ``COUNT(*)``: a
  stream that disagrees raises :class:`meta_disco.tdr.RowCountMismatch` after its
  last row, naming the table and both counts.
- :class:`AzulVerbatim` reads the ``{"type", "value"}`` JSONL manifest Azul serves
  and ``scripts/download_anvil_manifest.py`` keeps on disk. **It needs nothing**:
  no identity, no network, no extra. It is the offline stand-in and the parity
  oracle, not the target — Azul's manifest is a product of Azul's index, and reading
  the snapshot is the path once runs happen in Terra. It presents TDR's shape by
  removing what Azul adds (:data:`AZUL_ADDED_COLUMNS`, :data:`AZUL_ADDED_FILE_COLUMNS`,
  :data:`AZUL_ADDED_TABLES`), and it lacks the one column Azul drops,
  ``anvil_file.file_path``; a record derived through it therefore carries none.

Which reader an input came through is recorded on the input's envelope as
``input_source`` (``azul_manifest.INPUT_SOURCES``), so nothing downstream infers it;
choosing the reader for a run is #500's.

The derivation is AnVIL's
-------------------------
The readers are generic — :class:`TdrDirect` would stream any BigQuery dataset's
tables — but :func:`derive_records` is not: it reads ``anvil_file`` and
``anvil_dataset``, AnVIL's data model in TDR, and refuses a snapshot that lacks
either before yielding a record. Another repository hosted in TDR would reuse the
readers and need its own derivation. HPRC has no snapshot and keeps its own producer.

A derived record has no ``entry_id``. That is Azul's per-index document id, which
the snapshot does not hold and nothing in a run keys on since #446; the input
contract (``schema/metadata.yaml``) no longer requires it of any source.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

from . import tdr
from .azul_manifest import (
    VERBATIM_FILE,
    iter_verbatim_entities,
    iter_verbatim_lines,
    parse_verbatim_line,
    published_list,
    verbatim_line_type,
)

#: The two tables the derivation reads. ``anvil_file`` (``azul_manifest.VERBATIM_FILE``,
#: the same name in TDR and in the manifest) is one row per file and is the whole of
#: the per-file record; ``anvil_dataset`` is the snapshot's one dataset row, from which
#: every record takes its ``dataset_id`` and ``dataset_title``.
TABLE_DATASET = "anvil_dataset"
REQUIRED_TABLES = (TABLE_DATASET, VERBATIM_FILE)

# What Azul adds to a snapshot's tables on the way into its verbatim manifest. Measured
# 2026-09-20 and recorded as comments on #477: the TDR side read in BigQuery from a Terra
# notebook, the manifest side diffed against it, for three prod snapshots (1000G,
# nhp_dGTEx_V1, ENCORE_293T — every row of every table, every column but one). Azul adds
# a ``version`` on every entity, ``drs_uri`` on ``anvil_file`` — a copy of TDR's
# ``file_ref``, equal on every row, which the twelve-manifest parity test checks across
# the corpus — and one entity type of its own. :class:`AzulVerbatim` removes each so the
# tables come out in TDR's shape. The one column Azul *drops*, ``anvil_file.file_path``,
# cannot be put back. Nothing offline can re-derive this list: a manifest alone cannot
# tell an Azul addition from a TDR column.
AZUL_ADDED_COLUMNS = frozenset({"version"})
AZUL_ADDED_FILE_COLUMNS = frozenset({"drs_uri"})
AZUL_ADDED_TABLES = frozenset({"duos_dataset_registration"})

#: How many rows of a held table :class:`AzulVerbatim` keeps from its listing scan.
#: Two, because :func:`derive_records` reads at most two rows of ``anvil_dataset`` —
#: the one it needs and the one that would refuse the snapshot — so holding more
#: would serve nothing and a drifted table with thousands would sit in memory.
HELD_ROWS = 2


class SnapshotTables(Protocol):
    """A snapshot's tables: their names, and one table's rows streamed.

    ``rows`` yields each row as a dict keyed by TDR's column names, one at a time,
    holding the reader's own value types — never the table whole. Both readers here
    satisfy it; so can a test double.
    """

    def tables(self) -> list[str]: ...
    def rows(self, table: str) -> Iterator[dict[str, Any]]: ...


class TdrDirect:
    """A snapshot read in place from BigQuery, through :mod:`meta_disco.tdr`.

    ``tables`` is the dataset's table listing. ``rows`` is :func:`tdr.checked_rows`:
    the table counted with ``COUNT(*)`` and then streamed, page by page, with that
    count as the stream's expectation — so a stream that ends short or long raises
    after its last row rather than yielding a partial table as a whole one.
    """

    def __init__(self, client: tdr.BigQueryClient, snapshot: tdr.Snapshot):
        self.client = client
        self.snapshot = snapshot

    def tables(self) -> list[str]:
        return tdr.list_tables(self.client, self.snapshot)

    def rows(self, table: str) -> Iterator[dict[str, Any]]:
        return tdr.checked_rows(self.client, self.snapshot, table)


class AzulVerbatim:
    """A snapshot's tables as Azul's verbatim manifest holds them, in TDR's shape.

    ``tables`` lists the entity types the manifest carries, in first-seen order, less
    :data:`AZUL_ADDED_TABLES`. A table with no rows has no line, so the listing cannot
    name it — the one way this differs from :class:`TdrDirect`, whose listing names
    an empty table too. ``rows`` streams one entity type through
    :func:`azul_manifest.iter_verbatim_entities`, whose type gate parses only the
    lines that can match, and removes :data:`AZUL_ADDED_COLUMNS` from every row and
    :data:`AZUL_ADDED_FILE_COLUMNS` from an ``anvil_file`` row. Asking for a table
    Azul added is refused: it is not a table of the snapshot.

    The listing is one scan of the file, reading each line's type off its tail
    (:func:`azul_manifest.verbatim_line_type`), done once and kept. That scan also
    parses and keeps the rows of the ``held`` tables — by default the one-row
    ``anvil_dataset`` — up to :data:`HELD_ROWS` of each, so ``rows`` on one of those
    answers from memory and :func:`derive_records` reads the file twice rather than
    three times. Two is the floor: the dataset row sits after most of the file rows,
    and the derivation needs it before its first record. A held table that turns out
    to have more rows than the bound is not held at all: ``rows`` streams it from the
    file like any other table, so a drifted manifest with a large dataset table costs
    a pass, never memory.
    """

    def __init__(self, path: Path, held: frozenset[str] = frozenset({TABLE_DATASET})):
        self.path = path
        self.held = held
        self._tables: list[str] | None = None
        # Rows of a held table that fit the bound; a table that overflowed is absent.
        self._held_rows: dict[str, list[dict[str, Any]]] = {}

    def _scan(self) -> list[str]:
        if self._tables is None:
            seen: dict[str, None] = {}
            held: dict[str, list[dict[str, Any]]] = {table: [] for table in self.held}
            for n, line in iter_verbatim_lines(self.path):
                entity_type = verbatim_line_type(self.path, n, line)
                seen.setdefault(entity_type, None)
                kept = held.get(entity_type)
                if kept is None:
                    continue
                if len(kept) == HELD_ROWS:
                    del held[entity_type]  # over the bound: not held, streamed on demand
                    continue
                kept.append(self._strip(entity_type, parse_verbatim_line(self.path, n, line)[1]))
            self._tables = [t for t in seen if t not in AZUL_ADDED_TABLES]
            self._held_rows = held
        return self._tables

    def tables(self) -> list[str]:
        return list(self._scan())

    def rows(self, table: str) -> Iterator[dict[str, Any]]:
        if table in AZUL_ADDED_TABLES:
            raise ValueError(f"{table!r} is an entity Azul adds to its manifest, not a table of the snapshot")
        if table in self.held:
            self._scan()
            if table in self._held_rows:
                return iter(self._held_rows[table])
        return (self._strip(table, value) for _, value in iter_verbatim_entities(self.path, {table}))

    @staticmethod
    def _strip(table: str, value: dict[str, Any]) -> dict[str, Any]:
        dropped = AZUL_ADDED_COLUMNS | (AZUL_ADDED_FILE_COLUMNS if table == VERBATIM_FILE else frozenset())
        return {column: cell for column, cell in value.items() if column not in dropped}


def derive_records(tables: SnapshotTables) -> Iterator[dict[str, Any]]:
    """One input record per ``anvil_file`` row, streamed, from a snapshot's tables.

    Refuses before yielding anything — the checks run at the call, and only the file
    stream is deferred — when a required table is not listed, naming it, or when
    ``anvil_dataset`` holds other than exactly one row: a snapshot is one dataset
    (#434's envelope shape rests on it), so a second row is that assumption breaking
    and picking one would be a guess. The dataset table is read as a stream and only
    its first two rows are ever taken, so a drifted snapshot with a large one is
    refused without being held. ``anvil_file`` is then streamed a row at a time
    through :func:`record_from_file_row`.
    """
    present = tables.tables()
    missing = [table for table in REQUIRED_TABLES if table not in present]
    if missing:
        raise ValueError(f"snapshot has no {', '.join(missing)} table; it lists {present}")
    datasets = tables.rows(TABLE_DATASET)
    dataset = next(datasets, None)
    if dataset is None:
        raise ValueError(f"{TABLE_DATASET} holds no row; a snapshot is one dataset")
    if next(datasets, None) is not None:
        raise ValueError(f"{TABLE_DATASET} holds more than one row; a snapshot is one dataset")
    return (record_from_file_row(row, dataset) for row in tables.rows(VERBATIM_FILE))


def record_from_file_row(row: dict[str, Any], dataset: dict[str, Any]) -> dict[str, Any]:
    """One classifier input record from one ``anvil_file`` row and the dataset row.

    The keys are the input contract (``schema/metadata.yaml``) less ``entry_id``, which
    the snapshot does not hold, plus the two published dimensions the contract does not
    model (#424) and, where the row carries it, ``file_path`` — the column Azul's
    manifests drop, kept as an extra key because it is the full path #277's uniform
    cache key wanted and never had. ``drs_uri`` is read from ``file_ref``, TDR's name
    for it; ``dataset_id`` and ``dataset_title`` come from the dataset row.

    Every other value is transcribed as the reader delivered it, nulls included: a
    null ``file_md5sum`` stays null and is excluded at load (#376), exactly as the
    compact path's empty cell is. The published lists go through
    :func:`azul_manifest.published_list` so a record derived here carries the same
    ``published`` block as one derived from the compact join. A row lacking any column
    the record reads — the two published ones included, since a snapshot whose
    ``anvil_file`` lacks them is schema drift, not a snapshot that publishes nothing —
    raises naming the column and its table; only ``file_path`` is optional. A published
    value that is not a list is refused too (:func:`azul_manifest.published_list`).
    """
    try:
        dataset_id, dataset_title = dataset["dataset_id"], dataset["title"]
    except KeyError as exc:
        raise ValueError(f"cannot map an {TABLE_DATASET} row: no {exc.args[0]!r} column") from None
    try:
        record = {
            "file_id": row["file_id"],
            "file_name": row["file_name"],
            "file_format": row["file_format"],
            "file_size": row["file_size"],
            "file_md5sum": row["file_md5sum"],
            "data_modality": published_list(row["data_modality"]),
            "reference_assembly": published_list(row["reference_assembly"]),
            "is_supplementary": row["is_supplementary"],
            "drs_uri": row["file_ref"],
            "dataset_id": dataset_id,
            "dataset_title": dataset_title,
        }
    except KeyError as exc:
        raise ValueError(f"cannot map an {VERBATIM_FILE} row to a record: no {exc.args[0]!r} column") from None
    if "file_path" in row:
        record["file_path"] = row["file_path"]
    return record
