"""Evidence files: what an out-of-band importer writes and a run reads (#401, #421).

An importer runs *out of band* from classification — when a catalog refreshes, with
network — and writes an evidence file. The main loop reads it. Classification stays
offline and deterministic while the importers do the networked work, the same shape
as the evidence cache, and either side can be re-run without forcing the other::

    inference  →  read sources (read evidence files, match to our files)
                  →  reconcile  →  output

**A line is an observation, not an answer** (contract 1.1-1.5). An importer
transcribes what a source wrote about a slot and stops; only the rule engine turns
that raw value into one of our terms. #401 shipped the other arrangement — a line
carried a mapped ``value`` and this module refused one outside the dimension's
vocabulary — and #421 amended it. The value mapping lives in the translation table
(#414), applied by reconcile, which is also where that vocabulary check now is.

This module is the artefact and everything about it: the envelope record and its
parts, the layout on disk, the line format, the streaming writer and reader, and the
report a run prints of what it found — found and not consumed, since no evidence reaches classification until the
join lands (#402). Anything that needs to find or write an evidence file should come
through here rather than re-deriving the layout. Matching a row to one of our files
is #402, and the importers that will produce these files are #369 (AnVIL manifests)
and #394 (external catalogs).

**What a run does with these today.** It discovers them and reports each one's
source, version, catalog and age — ``classify_run.run_all_classifications`` calls
:func:`report_evidence_files` and never :func:`iter_evidence`. No evidence reaches
classification, so a run with evidence files present writes the same output as one
without. Matching rows to our files is #402; the writer and reader here exist so
the producers (#369, #394) can be built against a settled contract before that lands.

**Currency is not decided here**, and will not be when the join does: a run will
import from every file it found and refuse none. It cannot do better offline — the
sources share no version to compare, and AnVIL deletes a superseded catalog rather
than keeping it to be matched against. The two places that can act on the question
own it instead: the importer, which compares its file's ``target.version`` against
the configured catalog when deciding to re-fetch, and the run's output, which is to
record the catalog it enhances so that an enhancement offered to a catalog that has
moved on is refused at that boundary — that one is #404 and is not built, so nothing
enforces it yet.

**The file.** One ``.ndjson`` file: line 1 is the envelope, every later line is one
evidence row. NDJSON rather than a JSON array because 708,088 files by 5 dimensions
by several sources is millions of rows, and a whole-file ``json.load`` is already the
memory ceiling this corpus keeps hitting (#374); ``anvil_files_metadata.ndjson`` is
the existing precedent. Putting the envelope on line 1 rather than in a sidecar
keeps the rows inseparable from their provenance, and lets a reader have the whole
of it after a single ``readline``::

    {
        "evidence_file": {
            "source": {
                "repository": "HPRC Data Explorer",
                "dataset": "R2",
                "table": "sequencing-data",
                "url": "https://…",
            },
            "source_type": "repository_metadata",
            "source_version": "2026-09-01",
            "source_key": "filename",
            "target": {"system": "anvil", "dataset": "AnVIL_HPRC_R2", "version": "anvil15"},
            "target_key": "file_name",
            "fetched_at": "2026-09-01T09:14:03",
        }
    }
    {
        "field": "platform",
        "target_key_value": "HG002.hifi.bam",
        "raw_value": "Revio",
        "column": "instrumentModel",
    }

**The envelope names both sides of the join.** A line reads: *this row is about the
row in* ``target`` *whose* ``target_key`` *equals its* ``target_key_value``. The key
*names* live on the envelope because they do not change within a file — every row
an importer writes is keyed the same way — so only the value is on the line. The
same factoring keeps the source's repository, dataset, url and table on the envelope
while ``column`` stays per row, since one table's rows are read from several
columns. ``dataset`` crosses onto each row as well as staying on the envelope: it
is what makes a ``column`` legible, since the same column name means different things
in different datasets. ``source_type`` is on the envelope for the same reason and is
not on the line at all: one repository, dataset and table is one kind of source, so
it is checked once against ``EXTERNAL_SOURCE_TYPES`` rather than a few million times,
and reconcile reads it there when it stamps the claim it makes (#421).

**The importer owns the mapping between the two keys** — and *only* that mapping. It
writes ``target_key_value`` already in the target's value space, transforming a
source's own key where it must, so the run performs equality lookup and nothing else.
That is what keeps corpus knowledge in the importer and transform logic out of the
join, and it is why a source keyed by an ENA run accession adds no term to the key
vocabulary: it maps that accession to ``archive_accession`` itself. Mapping the
*value* is the other half, and the importer does not have it (contract 1.3).

**What a line does not carry, and why each is absent.**

- No ``value``, ``status`` or ``claim_state``. Only the rule engine declares any of
  the three (contract 1.1, 3.6). A raw value no rule matches produces no claim at all
  and enters the review queue (3.7), so there is nothing for an importer to say in
  place of an answer. ``declined`` is not here either: it is a property of a
  ``(source, column, slot)`` triple, decided once in the slot map (#369), not a
  verdict repeated on every row that column produced.
- No ``rule_id``. There is no mapping rule at import time. The claim reconcile builds
  cites the translation-table row that mapped the value (#414), which is a rule by
  contract 3.8.
- No ``tier``. An imported claim does not compete on the rule tiers (#391), so a tier
  on one is a number the importer invents and resolution discards.
- No ``join_key`` or ``match_exact``. Those are what the join fills in once a match
  has actually happened, and a file asserting them would be claiming a match that has
  not occurred.

``raw_value`` is transcribed verbatim (contract 1.4) — not casefolded, trimmed,
corrected or suppressed. Matching normalizes; the file records. An empty cell is
written as the empty string it was rather than dropped: what ``""``, ``NA`` or
``unspecified`` *mean* is a rule's to decide, and a row silently omitted here is a
decision no one can review (#421).
"""

import json
import os
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from .models import (
    CLASSIFICATION_FIELDS,
    JOIN_KEY_FILE_NAME,
    ClaimSource,
    _flat_from_dict,
    _flat_plan,
    _flat_to_dict,
    _reject_unknown,
    member_optional_str,
    require_external_source_type,
    require_join_key,
    required_str,
)

# The key line 1 is wrapped in. An envelope is structurally distinguishable from an
# evidence row rather than distinguishable by position alone, so a truncated or
# concatenated file fails as a shape violation instead of reading an envelope as a row.
ENVELOPE_KEY = "evidence_file"

# What `discover` treats as an evidence file. NDJSON is the format, so the suffix is the
# membership test — a README or a scratch .json beside them is not picked up.
EVIDENCE_FILE_GLOB = "*.ndjson"

# Where an importer leaves the evidence files a run reads. One directory per source
# under it (`data/source_evidence/hprc/`, `.../anvil/`): an evidence file is the same
# kind of artefact whoever wrote it, so a run discovers them all by walking one root
# rather than by knowing which sources exist. `source_evidence` and not `evidence`,
# which `data/` already uses for the fetched-header cache — two unrelated things, and
# a shared name would have read as one. This module is
# <root>/src/meta_disco/source_evidence.py, so the repo root is three levels up.
DEFAULT_SOURCE_EVIDENCE_ROOT = Path(__file__).resolve().parents[2] / "data" / "source_evidence"

# The dimension names as a set, for the membership check every row pays twice — on
# the way in and on the way out. `CLASSIFICATION_FIELDS` stays the tuple it is
# because its order is the canonical output order; this is the same five names.
_FIELDS = frozenset(CLASSIFICATION_FIELDS)

# One encoder for the write loop, built once. Compact separators drop ~7% of the
# bytes across millions of lines, and `json.dumps(..., separators=...)` cannot be
# used for it: that constructs a fresh encoder on every call.
_encode = json.JSONEncoder(separators=(",", ":")).encode

# Write buffer for an evidence file. A written line measures around 170 bytes, so the
# default 8 KB is a syscall every 50 rows or so across a multi-gigabyte sequential
# write; a megabyte is one per 6,000.
_WRITE_BUFFER_BYTES = 1 << 20

# How far `read_envelope` will read looking for the end of line 1. See `_read_envelope`.
_MAX_ENVELOPE_BYTES = 1 << 20

# What each side calls the row it is refusing (`_where`). A writer counts rows,
# because it has no line numbers to give; a reader counts lines, because that is what
# a person opening the file can act on.
_WRITING = "row"
_READING = "line"

# The members of an evidence line. `_evidence_line` writes exactly these, so a file
# carrying anything else beside them was not written by this module. `column` is
# optional — a source whose table has none omits it. The key names are not among
# them: they are on the envelope, constant for the file.
_LINE_KEYS = frozenset({"field", "target_key_value", "raw_value", "column"})

# Members a line carried when it was a claim (#401), each with why it is gone (#421).
# Refused by name rather than as an anonymous unknown member: a producer written
# against the old format, or against the contract's earlier framing, hits exactly
# these, and "unknown member ['value']" would not tell it what to do instead.
_RETIRED_LINE_KEYS = {
    "claim": "a line is an observation, not a claim — write the source's raw_value and let a rule map it",
    "value": "only the rule engine maps a raw value onto our vocabulary (contract 1.1, 1.3)",
    "status": "not_applicable and not_classified are a rule's to declare, never a source's (contract 3.6)",
    "claim_state": "a raw value no rule matched produces no claim and enters the review queue (contract 3.7)",
    "rule_id": "there is no mapping rule at import time; the claim reconcile builds cites one (#414)",
    "tier": "imported evidence does not compete on the rule tiers (#391)",
    "source_type": "one file is one kind of source, so it is on the envelope, not on every row",
    # The two the join fills in once a match has actually happened. An outer key of
    # `file_name` beside an inner `join_key` of `file_md5sum` is two contradictory
    # join descriptions in one line (#401).
    "join_key": "the join records which key attached a row; a file states the key to match on",
    "match_exact": "the join records how a row attached; a file cannot assert a match that has not happened",
    # Not a claim member but the same kind of mistake: the writer already refuses a
    # row whose source is not the envelope's, and a reader that quietly re-attributed
    # one would undo that check for exactly the files it cannot vouch for.
    "source": "the envelope names this file's source, and a line may only add a column to it",
}


# --- The envelope and its parts (moved here from `models` by #409) -----------
#
# These three records and the timestamp they parse describe *this artefact* and
# nothing else, and `source_evidence` is the only module that imports them. They
# sat in `models` because #401 built them there; `models` is what the whole
# package shares, and every serialized format it accumulated made it more so.
#
# `ClaimSource` stays in `models`: it names where a raw value came from on a real
# claim in output evidence, which the rule engine builds and every consumer reads.
# The `_flat_*` helpers stay with it, for the same reason and because it uses
# them — so this module imports them rather than the other way round (#409).

# The shape an evidence file's `fetched_at` must have. This is the schema's `fetched_at`
# pattern, character for character — `test_the_reader_and_the_schema_share_one_pattern`
# reads the slot and compares — because the two must refuse the same strings, and the
# ways they drift apart are not guessable. Matched rather than measured by length:
# `fromisoformat` reads character 10 as the separator whatever it is, and a suffix can
# make a date longer than ten characters without making it a time, so `2026-09-01Z`
# and `2026-09-01+00:00` both parsed to midnight under a length check. Matched in full
# rather than by prefix: `fromisoformat` accepts a basic-format offset (`+0100`) from
# 3.11 and the schema never did, so a prefix check agreed with the gate on 3.10 and
# disagreed on 3.11 — an evidence file that reads differently by interpreter, which is
# what the `Z` normalization below exists to prevent (#401 review).
_FETCHED_AT_PATTERN = (
    r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])[T ]([01]\d|2[0-3]):[0-5]\d"
    r"(:[0-5]\d(\.\d+)?)?([+-]([01]\d|2[0-3]):[0-5]\d(:[0-5]\d(\.\d+)?)?|Z)?\Z"
)
_FETCHED_AT = re.compile(_FETCHED_AT_PATTERN)


def _parse_fetched_at(value: object, where: str) -> datetime:
    """Parse an evidence file's ``fetched_at``, or raise naming ``where``.

    A trailing ``Z`` is normalized to ``+00:00`` first. ``datetime.fromisoformat``
    rejects ``Z`` on Python 3.10 — this project's floor and what CI runs — while
    accepting it from 3.11, and the importers coming in #369/#394 read web APIs that
    emit it almost universally. Without this an evidence file written on a 3.11 machine
    parses there and fails on CI, which is a property of the interpreter rather than
    of the file.

    A time of day is required. ``fromisoformat`` accepts a bare ``2026-09-01`` and
    silently returns midnight, so a date-only value would read back as a fetch
    claiming to have happened at 00:00:00 — a precision the file never stated, and
    one that makes two imports on the same day indistinguishable, which is the case
    the age report exists for. The check is on the string rather than the parsed
    value, because midnight is a real time a genuine fetch can have.

    Both branches name ISO 8601, because which one a value reaches depends on the
    interpreter: ``20260901T091403`` fails the parse on 3.10 and reaches the shape
    check on 3.11, where ``fromisoformat`` accepts basic format. The shape check is
    the whole pattern and not a prefix for the same reason — 3.11 also accepts a
    basic-format offset, ``+0100``, which the schema refuses on every interpreter
    (#401 review).

    It is a *shape* check and not a length one: ``fromisoformat`` treats character 10
    as the date/time separator whatever character it is, so ``2026-09-01X09:14:03``
    parses, and a date can be longer than ten characters without carrying a time at
    all — ``2026-09-01Z`` and ``2026-09-01+00:00`` both read back as midnight (#401
    review). Matching the schema's pattern instead refuses all three on both sides,
    and refuses ``20260901T091403`` — basic-format ISO, which 3.10 rejects and 3.11
    accepts — the same way on every interpreter, which is the divergence the ``Z``
    normalization above exists to prevent.
    """
    if not isinstance(value, str):
        raise ValueError(f"{where}: envelope fetched_at is {value!r}, not an ISO 8601 string")
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise ValueError(f"{where}: envelope fetched_at {value!r} is not an ISO 8601 datetime") from None
    if not _FETCHED_AT.match(value):
        raise ValueError(
            f"{where}: envelope fetched_at {value!r} is not an ISO 8601 date followed by T or a "
            "space and a time of day — record when the fetch happened, not only the day it happened on"
        )
    return parsed


@dataclass(frozen=True, kw_only=True)
class EvidenceFileSource:
    """Where a whole evidence file's rows were read from (issue #401).

    Three levels, because a source is not flat: a **repository** publishes
    **datasets**, and a dataset has **tables**. The AnVIL manifests are
    ``AnVIL / AnVIL_HPRC_R2 / alignments_v2``; the HPRC Data Explorer is
    ``HPRC Data Explorer / R2 / sequencing-data``; ENA is
    ``ENA / <study accession> / read_run`` — where ``read_run`` is literally the
    ``result=`` parameter its API takes, and the fields it returns are the columns.
    A source with no middle level leaves ``dataset`` null, as ``table`` may be null.

    ``dataset`` earns its place twice. It is provenance, and it is what a claim's
    :attr:`column` cannot be read without — the same column name means different
    things in different datasets. It is also the reason the *target* carries a
    dataset: see :class:`EvidenceTarget`.

    Distinct from :class:`ClaimSource` rather than reusing it. A claim's source
    carries a ``column``, which belongs to the row because one table's rows are
    read from several columns; a file's source carries a ``dataset``, which belongs
    to the file because every row in it came from the same one. Modeling them as
    one class would let an envelope name a column that could disagree with every
    line in the file.
    """

    repository: str
    dataset: str | None = None
    table: str | None = None
    url: str | None = None

    def to_dict(self) -> dict:
        """Serialize for the envelope line, dropping members the source does not have."""
        return _flat_to_dict(self)

    @classmethod
    def from_dict(cls, block: object, where: str) -> "EvidenceFileSource":
        """Rebuild a file's source from what :meth:`to_dict` wrote."""
        return _flat_from_dict(cls, block, where, "source")

    def as_claim_source(self, column: str | None) -> ClaimSource:
        """The per-claim :class:`ClaimSource` a claim in this file carries.

        A field copy — the envelope's four facts, plus the column this particular
        row was read from. ``dataset`` crosses with the rest: it is what makes the
        column legible, since the same column name means different things in
        different datasets, and a consumer reading the output ``evidence`` array
        cannot go back to the evidence file to find it.

        Called once per distinct column by the reader, which caches what it returns
        for the whole file (``iter_evidence``); the envelope stores these once for the
        same reason, rather than repeating them on a few million lines.
        """
        return ClaimSource(name=self.repository, url=self.url, dataset=self.dataset, table=self.table, column=column)


@dataclass(frozen=True, kw_only=True)
class EvidenceTarget:
    """The system an evidence file's rows are *about* (issue #401).

    An evidence file says "the row in **this** system whose **this key** is **that
    value**". The target names the system, so an importer is not implicitly bound to
    AnVIL, and the file records which system it resolved its keys against.

    ``dataset`` is the scope the join runs within, and it is not decoration: keyed by
    ``file_name`` alone, 69.4% of the corpus's 708,088 rows carry a non-unique key,
    and 20% remain non-unique even scoped by dataset *title* alone — but within
    ``AnVIL_HPRC_R2`` the collision rate is 2 rows in 16,271. A filename join is
    unusable without a dataset scope and workable with one: those 2 rows are
    ambiguity the join must still record rather than resolve, which is #402's, and
    this scope is what brings it down to something a person can look at.

    Null is correct only where the key is unique across the whole target. Measured,
    that is ``file_id``, ``entry_id`` and ``drs_uri`` — each present and unique on
    every one of the 708,088 records. ``file_md5sum`` is *not*: it is non-unique on
    1.72% of rows, 12,203 of them. Two thirds of those are collisions **inside** one
    dataset — 8,119 rows from 1,118 md5s — which a dataset scope would not separate
    either; the remaining 4,084 rows are 2,026 md5s registered in more than one
    dataset. Leaving it unscoped is defensible for a claim about the file's
    *content*, which is true of every row that has those bytes however they are
    catalogued, and wrong for a claim about one catalogued file. Nothing here
    enforces that distinction; making the join record the ambiguity rather than
    silently fanning out is #402's.

    ``version`` is which generation of the target the importer resolved against — an
    AnVIL catalog such as ``anvil15``. Null when the importer did not resolve against
    a particular generation, which is the ordinary case for a source that simply
    publishes names and values (HPRC, ENA) rather than reading our catalog. It is
    provenance for the importer's own next pass, not a gate on the run: see
    ``source_evidence`` on why currency is not decidable offline.

    The mapping from the source's own names to these is the **importer's**
    knowledge. The source calls its collection ``R2``; the target calls the same
    thing ``AnVIL_HPRC_R2``. The importer records both sides, and the run does
    equality lookup only.
    """

    system: str
    dataset: str | None = None
    version: str | None = None

    def to_dict(self) -> dict:
        """Serialize for the envelope line, dropping members the target does not have."""
        return _flat_to_dict(self)

    @classmethod
    def from_dict(cls, block: object, where: str) -> "EvidenceTarget":
        """Rebuild a target from what :meth:`to_dict` wrote."""
        return _flat_from_dict(cls, block, where, "target")


@dataclass(frozen=True, kw_only=True)
class EvidenceFileEnvelope:
    """What an evidence file records once, for every row in it (issue #401).

    An importer runs out of band from classification — when a catalog refreshes,
    with network — and writes an evidence file; a run reads it. This is the header of
    that artefact, and it names **both sides of the join**, symmetrically::

        source   source_type   source_version      source_key
        target                       target.version    target_key

    A line then reads: *this row is about the row in* ``target`` *whose*
    ``target_key`` *equals its* ``target_key_value`` *; about that row's* ``field``
    *, the source wrote* ``raw_value``.

    ``source_type`` is which kind of external source this is
    (:data:`EXTERNAL_SOURCE_TYPES`). It is here rather than on every row for the
    reason the key names are: one repository, dataset and table is one kind of
    source, so it is checked once per file, and reconcile reads it from here when it
    stamps the claim it makes from a row (#421).

    **The key names are here, not on the line.** They do not change within a file —
    every row an importer writes is keyed the same way — so repeating them on a
    few million lines would be the envelope's content written out again. Only the
    key *value* varies, so only that is on the line. It is the same factoring that
    keeps ``ClaimSource``'s name, url and table here while ``column`` stays per
    row.

    **The importer owns the mapping between the two keys**, and writes
    ``target_key_value`` already in the target's value space. Where a source's own
    value needs transforming to get there — pulling ``NA12878`` out of a path,
    normalizing an accession — the importer does it. The run performs equality
    lookup and nothing else, which is what keeps corpus knowledge in the importer
    and transform logic out of the join.

    ``target_key`` names a key of the target system, drawn from its record fields
    *and* from facts meta-disco derives: ENA run accessions appear in no input
    ``file_name`` at all, but ``archive_accession`` is populated on thousands of
    classified fastq records, read from the read headers. So the join runs after
    inference — which is where the pipeline already puts import.

    Frozen because provenance is a fact about where the rows came from, not state
    to edit after they are read. Validated on construction
    (:meth:`__post_init__`) against the same rules :meth:`from_dict` applies on the
    way back in, so a writer cannot produce a file its own reader would refuse —
    an importer would otherwise spend a networked run writing millions of rows
    behind a header that fails at the next classification run, days later and far
    from the cause.
    """

    source: EvidenceFileSource
    source_type: str
    source_version: str
    source_key: str
    target: EvidenceTarget
    target_key: str
    fetched_at: datetime

    def __post_init__(self) -> None:
        """Refuse an envelope that could not be read back, at the point it is built.

        Type hints do not run, so a ``source_version`` of ``None`` reaches here
        intact — and ``to_dict`` omits null members, so it would vanish from the file
        and read back as a missing key rather than naming the field.

        The two nested records are checked by serializing them and reading them back
        through their own ``from_dict`` — the reader's definition applied to the
        reader's input — rather than by re-listing their members here, which is how
        an earlier version left the parity half-kept.

        Runs once per evidence file, so its cost is nothing beside the write it precedes.
        """
        where = "evidence file envelope"
        if not isinstance(self.source, EvidenceFileSource):
            raise ValueError(f"{where}: source is {type(self.source).__name__}, not a EvidenceFileSource")
        if not isinstance(self.target, EvidenceTarget):
            raise ValueError(f"{where}: target is {type(self.target).__name__}, not a EvidenceTarget")
        EvidenceFileSource.from_dict(self.source.to_dict(), where)
        EvidenceTarget.from_dict(self.target.to_dict(), where)
        if not isinstance(self.fetched_at, datetime):
            raise ValueError(f"{where}: fetched_at is {type(self.fetched_at).__name__}, not a datetime")
        require_external_source_type(self.source_type, "source_type", where)
        required_str(self.source_version, "source_version", where)
        required_str(self.source_key, "source_key", where)
        require_join_key(self.target_key, "target_key", where)
        # A key that is not unique across the target cannot be matched without a
        # scope, and `file_name` is the one in the vocabulary that is not: present on
        # every record but non-unique on 69.4%, against 2 rows in 16,271
        # within a single dataset. Writing an unscoped one produces a file whose
        # rows the join cannot attach to a single file — refused here rather than
        # discovered when the join fans out (#401 review).
        if self.target_key == JOIN_KEY_FILE_NAME and self.target.dataset is None:
            raise ValueError(
                f"{where}: target_key {JOIN_KEY_FILE_NAME!r} needs a target dataset to scope it — "
                "a bare file name is non-unique on 69% of the corpus and matches no single row"
            )

    @classmethod
    def from_dict(cls, block: object, where: str) -> "EvidenceFileEnvelope":
        """Rebuild an envelope from what :meth:`to_dict` wrote, validating each member.

        The only place an evidence file's first line becomes provenance. Every member is
        checked here rather than where a consumer reads it: an envelope is read once
        per file and is what the report rests on, so an unparseable ``fetched_at`` or
        a source with no repository must fail as a malformed evidence file, not later as
        a report that cannot render.

        A member the envelope does not have is refused rather than ignored, because
        the schema validates this record ``closed=True``: a reader that quietly
        dropped an unknown key would accept documents the schema rejects.

        A trailing ``Z`` on ``fetched_at`` is normalized to ``+00:00`` before parsing.
        ``datetime.fromisoformat`` rejects ``Z`` on Python 3.10, this project's floor
        and what CI runs, while accepting it from 3.11 — and the importers coming in
        #369/#394 read web APIs that emit it almost universally. Without this, a claim
        file written on a 3.11 machine parses there and fails on CI, which is a
        property of the interpreter rather than of the file.

        ``fetched_at`` must carry a time of day. ``fromisoformat`` accepts a bare
        ``2026-09-01`` and silently returns midnight, so a date-only value would read
        back as a fetch claiming to have happened at 00:00:00 — a precision the file
        never stated, and one that makes two imports on the same day
        indistinguishable, which is the case the age report exists for. The check is
        on the string rather than the parsed value, because midnight is a real time a
        genuine fetch can have.
        """
        if not isinstance(block, dict):
            raise ValueError(f"{where}: envelope is {type(block).__name__}, not an object")
        known, expected, _ = _flat_plan(cls)
        _reject_unknown(block, known, expected, where, "envelope")
        return cls(
            source=EvidenceFileSource.from_dict(block.get("source"), where),
            source_type=require_external_source_type(block.get("source_type"), "envelope source_type", where),
            source_version=required_str(block.get("source_version"), "envelope source_version", where),
            source_key=required_str(block.get("source_key"), "envelope source_key", where),
            target=EvidenceTarget.from_dict(block.get("target"), where),
            target_key=require_join_key(block.get("target_key"), "envelope target_key", where),
            fetched_at=_parse_fetched_at(block.get("fetched_at"), where),
        )

    def to_dict(self) -> dict:
        """Serialize for the envelope line.

        The three members that are not already JSON are encoded here: ``source`` and
        ``target`` through their own ``to_dict``, and ``fetched_at`` as an ISO 8601
        string — the form ``azul_manifest.metadata_block`` already writes a fetch time
        in, and the form :meth:`from_dict` parses back.

        Keys come from ``fields()`` for the reason the nested records' do: a member
        added to the dataclass and not here would otherwise be dropped from every
        evidence file silently. Every member of this record is required, so none is
        omitted — unlike the nested records, which drop the members they lack.
        """
        encoded = {
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "fetched_at": self.fetched_at.isoformat(),
        }
        return {f.name: encoded.get(f.name, getattr(self, f.name)) for f in fields(self)}


@dataclass(frozen=True, slots=True)
class EvidenceEntry:
    """One line of an evidence file: a slot, a target row, and what the source said.

    Reads as: *this row is about the row in the envelope's* ``target`` *whose*
    ``target_key`` *equals* ``target_key_value`` *; about* ``field`` *, the source
    wrote* ``raw_value``.

    ``field`` is one of ``CLASSIFICATION_FIELDS`` — the slot, spelled ``field`` on the
    wire and in the code (contract 2.1). ``target_key_value`` is the value to match
    on, already in the target's value space: the importer owns the mapping between
    its own key and the target's, and any transform needed to get there, so the run
    performs equality lookup only. The key *names* are on the envelope, because they
    do not change within a file; only the value varies per row.

    ``raw_value`` is what the source wrote, verbatim (contract 1.4). It is **not**
    checked against our vocabulary and must not be: a source's spellings are its own,
    and a value we have no word for is the review queue's input rather than an error
    (contract 3.7). It is not even checked for emptiness — an empty cell is something
    the source published, and what it means is a rule's to decide. The one check is
    that it is a string, which is what the format can hold.

    ``source`` is the file's :class:`ClaimSource` with this row's ``column``:
    :func:`write_evidence_file` factors it back into the envelope and :func:`iter_evidence`
    puts it back, so a caller on either side holds whole provenance without consulting
    line 1. Reconcile needs all four levels — a rule may condition on provenance
    (contract 3.4), and an unmatched value is listed by source, dataset, table and
    column (5.2).

    ``slots=True`` because :func:`iter_evidence` builds one of these per row: a few
    million per source, each of which would otherwise carry its own ``__dict__``.
    """

    field: str
    target_key_value: str
    raw_value: str
    source: ClaimSource


@dataclass(frozen=True)
class EvidenceFileStatus:
    """One evidence file as a run sees it: its provenance, or why it could not be read.

    Exactly one of the two is set. ``error`` is the envelope's own parse or IO
    failure, held rather than raised so that one unreadable file does not hide the
    provenance of the ones behind it in the report.

    A run does not judge an evidence file beyond this. Whether the rows still describe
    the catalog being classified is left to the importer, which compares its own
    file's ``target.version`` against the configured catalog when deciding to re-fetch,
    and to the boundary where an enhancement is offered back to a catalog — which
    requires the run's output to record which catalog it enhances, and that is #404,
    not something this PR added. Nothing enforces it today.
    """

    path: Path
    envelope: EvidenceFileEnvelope | None
    error: str | None = None


def write_evidence_file(path: Path, envelope: EvidenceFileEnvelope, entries: Iterable[EvidenceEntry]) -> int:
    """Write one evidence file, streaming; return the number of rows written.

    ``entries`` is consumed once and no more than the current entry is held, so an
    importer can stream a catalog straight through. The file is written to a
    temporary path and renamed into place only after every row is out — as
    ``azul_manifest.write_input_files`` does — so a source that raises part-way
    through leaves the previous evidence file untouched rather than half-replaced. The
    rename is inside that guard rather than after it: a rename can fail too (a
    directory standing where the file should go), and leaving the temporary behind
    would strand a complete evidence file under a name nothing reads (#401 review).

    Every entry is validated against the envelope as it is written
    (:func:`_evidence_line`): an unknown dimension, a retired member such as a mapped
    ``value`` or a ``join_key``, or a row whose source is not the source the envelope
    names, raises rather than being written and discovered by a reader later. The
    envelope's own source is resolved once per column, here, and compared against per
    row — it is constant for the file. The envelope was checked when it was built
    (``EvidenceFileEnvelope.__post_init__``).

    ``path`` must end in ``.ndjson``, because that is what :func:`discover` looks for.
    Writing ``catalog.json`` otherwise succeeds, returns a row count, and is then
    invisible to every run — an importer's one-character mistake becoming a silent
    no-op with a success return, which is the one failure mode an import must not
    have (#401 review).
    """
    if path.suffix != EVIDENCE_FILE_GLOB.lstrip("*"):
        raise ValueError(
            f"{path.name}: an evidence file must be named {EVIDENCE_FILE_GLOB} — "
            f"a {path.suffix or 'suffixless'} file is written but never discovered"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    # A name unique to this writer, not `<name>.tmp`. Two importers writing one path
    # shared that name: both wrote, one renamed, the other's rename hit a file that
    # was no longer there — and it returned a row count for forty thousand rows
    # that are not on disk, which is the one failure an import must not have. They
    # now race only on the rename, which is atomic: a reader sees one whole file or
    # the other, never a mixture, and no writer's rename can delete a file it did not
    # write (#401 review). Which one survives is decided by completion order and
    # nothing else — *not* by which catalog is newer, since a writer that started
    # from an older one can finish later — so two importers must not be pointed at a
    # single path expecting the newer to win. Nothing here can enforce that: the
    # ordering an importer would need is its own, and it is a re-fetch decision
    # (#369, #394). A crash leaves a `.tmp` behind under a unique name; `discover`
    # looks for `*.ndjson`, so no run reads it.
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid4().hex[:8]}.tmp")
    name = path.name
    # The source a row in this file must have come from, by its column. The
    # envelope's source is constant for the file and one table's rows are read from a
    # handful of columns, so this is a few objects per file rather than one per row.
    # The comparison against it is a record compare: `ClaimSource` is a frozen
    # dataclass, so equality is its members, and an entry now carries the record
    # itself rather than a serialized claim to be parsed back (#421). (A plain dict
    # closed over here rather than `lru_cache` on a method, which would keep the
    # envelope alive for the process.)
    by_column: dict[str | None, ClaimSource] = {}

    def expected_source(column: str | None) -> ClaimSource:
        if (known := by_column.get(column)) is None:
            known = by_column[column] = envelope.source.as_claim_source(column)
        return known

    written = 0
    try:
        with tmp.open("w", encoding="utf-8", buffering=_WRITE_BUFFER_BYTES) as f:
            f.write(_encode({ENVELOPE_KEY: envelope.to_dict()}))
            f.write("\n")
            for entry in entries:
                written += 1
                f.write(_encode(_evidence_line(expected_source, entry, name, written)))
                f.write("\n")
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return written


def read_envelope(path: Path) -> EvidenceFileEnvelope:
    """The evidence file's envelope, read from its first line alone.

    A run decides whether to refuse a file from its provenance, so that decision
    costs one line and not the file. Raises ``ValueError`` naming the file when line
    1 is absent or is not an envelope.
    """
    with path.open("rb") as f:
        return _read_envelope(path, f)


def iter_evidence(path: Path) -> Iterator[EvidenceEntry]:
    """Every evidence row in one file on disk, in file order, streamed.

    Line 1 is consumed as the envelope before any row is yielded, because the
    source it carries is what each row's ``source`` is rehydrated from — so a file
    whose envelope is malformed fails at once rather than after some rows have been
    handed out. A blank line carries no row and is passed over. Any other line that
    will not parse, or that is not an evidence row, raises ``ValueError`` naming the
    file and the line — the shape ``azul_manifest.iter_verbatim_entities`` uses, and
    for its reason: an import that silently dropped rows would understate what a
    source said, which is the one thing it must not do.

    The file is opened as bytes and each line decoded here, rather than opened as
    text. A text handle decodes inside its own iterator, so one corrupt byte in a
    later record raised ``UnicodeDecodeError`` from the ``for`` statement — a codec
    traceback with a byte offset, escaping the promise above that every bad line is
    named by file and line number (#401 review).
    """
    name = path.name
    with path.open("rb") as f:
        envelope_source = _read_envelope(path, f).source
        # One `ClaimSource` per column for the whole file, as the writer keeps one per
        # column (`write_evidence_file`). The envelope's members are constant and only
        # `column` varies, so rebuilding it per line rebuilt and re-validated the same
        # object a few million times; a table's rows come from a handful of columns.
        # Sharing the instance is safe and is why the record is frozen: nothing
        # downstream may edit a row's provenance, and every row gets its own
        # `EvidenceEntry` around it.
        by_column: dict[str | None, ClaimSource] = {}
        for n, raw in enumerate(f, start=2):
            line = _decode(raw, _where(name, _READING, n))
            if line.isspace():
                continue
            yield _entry_from_line(name, n, line, envelope_source, by_column)


def _decode(raw: bytes, where: str) -> str:
    """One line of an evidence file as text, or a ``ValueError`` naming it.

    An evidence file is written by another process, so a truncated write or a source that
    handed an importer bytes in another encoding is a malformed *file*, reported like
    any other malformed line — not a codec error from inside a file iterator.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{where}: not valid UTF-8: {exc}") from None


def discover(root: Path) -> list[Path]:
    """Every evidence file under ``root``, in a stable order; empty when there are none.

    A missing ``root`` is not an error: no evidence files present is the ordinary state
    of a run today, and it means the run imports nothing — not that it is
    misconfigured.
    """
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob(EVIDENCE_FILE_GLOB) if p.is_file())


def report_evidence_files(root: Path, now: datetime | None = None) -> list[EvidenceFileStatus]:
    """Report every evidence file under ``root``, and return what each one's status is.

    Prints one line per file — source, table, version, the catalog it was built for
    if it names one, fetch date and age — so a run says which evidence files it found
    and how old they were. *Found* and not *consumed*: no claim reaches classification
    until the join lands (#402), and this report is the whole of what a run does with
    one today. Returns the statuses in the order printed.

    The report does not judge, and the run does not stop. Whether an evidence file has
    outlived what it describes is not answerable from the file: the sources have no
    common version to compare (HPRC has a major release and may drift from it), and
    AnVIL deletes a superseded catalog outright, so there is nothing offline to check
    against. That question is settled where it can be acted on — the importer decides
    whether to re-fetch, and the run's output records which catalog it enhances, so
    an enhancement offered to a catalog that has moved on is refused there.

    A file whose envelope cannot be read is reported as an error rather than raising:
    the point of the report is to name every file, and one unreadable file should not
    hide the four behind it.

    ``now`` fixes the reference time for the ages (tests); by default each age is
    taken against the current time in the envelope's own timezone, so a naive and an
    aware ``fetched_at`` both work.
    """
    statuses = []
    for path in discover(root):
        try:
            envelope = read_envelope(path)
        except (OSError, ValueError) as exc:
            statuses.append(EvidenceFileStatus(path, None, f"envelope could not be read: {exc}"))
            continue
        statuses.append(EvidenceFileStatus(path, envelope))

    if not statuses:
        print(f"Evidence files: none under {root} — this run imports nothing.")
        return statuses
    print(f"Evidence files under {root}:")
    for status in statuses:
        print(f"  {_describe(status, root, now)}")
    return statuses


def _describe(status: EvidenceFileStatus, root: Path, now: datetime | None) -> str:
    """One report line for one evidence file: both sides of its join, and its age.

    Reads as *what it came from* → *what it is about*, because a person checking a
    run's evidence files wants to see which corpus each one will attach to as much as
    where it was fetched from.
    """
    name = status.path.relative_to(root)
    if status.envelope is None:
        return f"UNREADABLE {name} — {status.error}"
    envelope = status.envelope
    target = envelope.target
    scope = f"{target.system}/{target.dataset}" if target.dataset else target.system
    generation = f" @{target.version}" if target.version else ""
    return (
        f"{name} — {_join_side(envelope.source.to_dict(), envelope.source_key)}"
        f" v{envelope.source_version}"
        f" -> {scope}[{envelope.target_key}]{generation},"
        f" fetched {envelope.fetched_at.isoformat()} ({_age_phrase(envelope.fetched_at, now)})"
    )


def _join_side(members: dict, key: str) -> str:
    """The source side of the join as ``repository/dataset/table[key]``.

    Skips the levels this source does not have, so a curator table with no dataset
    renders as ``meta-disco curator table/overrides[file_md5sum]``. ``url`` is
    dropped: it is provenance a reader can go and look at, not something to carry
    across every line of a report.

    The target renders separately rather than through here. Its ``version`` is a
    catalog generation, not another level of the path — slash-joining it would print
    ``anvil/AnVIL_HPRC_R2/anvil15``, where a reader takes ``anvil15`` for a table.
    """
    levels = [v for k, v in members.items() if k != "url" and v is not None]
    return f"{'/'.join(levels)}[{key}]"


def _age_phrase(fetched_at: datetime, now: datetime | None) -> str:
    """How long ago ``fetched_at`` was, in whole days.

    A ``now`` of None means the current time in the envelope's own timezone. An
    explicit ``now`` need not agree with the envelope about awareness — a caller
    holds one clock and an evidence file writes whichever kind its importer had — so
    where they disagree both are given the local zone, which is what makes them
    subtractable. Getting that wrong would raise inside the report and take every
    other file's line down with it, which is the one thing the report must not do.

    A fetch time in the future is said rather than clamped to zero: it means a clock
    or a hand-edit is wrong, which is worth seeing.
    """
    reference = now if now is not None else datetime.now(fetched_at.tzinfo)
    if (reference.tzinfo is None) != (fetched_at.tzinfo is None):
        reference, fetched_at = reference.astimezone(), fetched_at.astimezone()
    days = (reference - fetched_at).days
    if days < 0:
        return "dated in the future"
    if days == 0:
        return "today"
    return f"{days} day{'s' if days != 1 else ''} ago"


def _evidence_line(
    expected_source: Callable[[str | None], ClaimSource], entry: EvidenceEntry, name: str, n: int
) -> dict:
    """Serialize one entry, factoring its source into the file's.

    The row keeps its slot, its target key value and its raw value; its ``source`` is
    replaced by that source's ``column`` alone — the only member that varies within
    one file, and omitted too when the source has none. Writing the repository,
    dataset, url and table on every line would be the envelope's content repeated a
    few million times.

    That factoring is also a check: a row whose source is not the source the
    envelope names does not belong in this file, and saying so here is cheaper than a
    reader discovering that every row it rehydrated was attributed to the wrong
    table. The comparison goes through :meth:`EvidenceFileSource.as_claim_source`, so the
    writer's notion of "the same source" is the reader's own.

    ``name`` and ``n`` locate the entry for a refusal; :func:`_where` turns them into
    one label per row, shared by every raise below.
    """
    where = _where(name, _WRITING, n)
    # Checked before its members are read, so an importer that yields a tuple or a
    # bare dict is told what is wrong at this row rather than getting an
    # `AttributeError` from the attribute access below (#401 review).
    if not isinstance(entry, EvidenceEntry):
        raise ValueError(f"{where}: is a {type(entry).__name__}, not an EvidenceEntry")
    _check_entry(where, entry.field, entry.target_key_value, entry.raw_value)
    source = entry.source
    if not isinstance(source, ClaimSource):
        raise ValueError(
            f"{where}: carries no source — an evidence file holds rows read from an external source"
            if source is None
            else f"{where}: carries a source that is a {type(source).__name__}, not a ClaimSource"
        )
    # A record compare against the envelope's own, not a parse: `ClaimSource` is
    # frozen, so equality is its five members, and `column` is the one of them this
    # line rather than the envelope decides. The record was validated when it was
    # built (`ClaimSource.__post_init__`), so nothing here re-checks its members.
    if source != (expected := expected_source(source.column)):
        raise ValueError(f"{where}: comes from {source.to_dict()}, but this file's envelope names {expected.to_dict()}")
    line = {"field": entry.field, "target_key_value": entry.target_key_value, "raw_value": entry.raw_value}
    if source.column is not None:
        line["column"] = source.column
    return line


def _entry_from_line(
    name: str, n: int, line: str, envelope_source: EvidenceFileSource, by_column: dict[str | None, ClaimSource]
) -> EvidenceEntry:
    """Parse one evidence line, attaching the provenance its envelope carries.

    ``envelope_source`` is the file's source, read once by :func:`iter_evidence`, and
    ``by_column`` is that caller's cache of the :class:`ClaimSource` each column
    resolves to. The row comes back whole — that source, with this line's ``column``
    — so a consumer reads the provenance the importer recorded and never has to
    consult the envelope itself.

    **What is not rebuilt, and why.** Until #421 a line held a claim, which was put
    back through ``make_claim`` on the way in so that bytes written by an out-of-band
    process could not reach ``evaluate_claims`` as an unvalidated dict. A row is not a
    claim and declares nothing, so there is no claim to rebuild and nothing here can
    reach resolution: the rule engine makes the claim later, from this raw value and
    the translation table (#414), and that is where ``make_claim``'s invariants and
    the vocabulary check now apply.

    What replaces it is smaller and is all the shape a row has: the line's members are
    exactly ``_LINE_KEYS``, ``field`` is a known slot, ``raw_value`` is a string, and
    ``column`` is a string or absent. A member a row carried when it was a claim is
    refused by name (:data:`_RETIRED_LINE_KEYS`).

    A line that carries its own ``source`` is refused rather than silently
    overwritten — it is an unknown member like any other. The envelope names the
    file's source; a line may add a ``column`` to it and nothing else. The write side
    already refuses a row whose source is not the envelope's, and a reader that
    quietly re-attributed one would undo that check for exactly the files it cannot
    vouch for.

    ``name`` is the file's name, hoisted out of the read loop by :func:`iter_evidence`,
    and is formatted with ``n`` into one label per line by :func:`_where`.
    """
    where = _where(name, _READING, n)
    try:
        entry = json.loads(line)
        field, target_key_value, raw_value = (entry["field"], entry["target_key_value"], entry["raw_value"])
    # `ValueError` rather than `json.JSONDecodeError`, which is a subclass of it:
    # `json.loads` also raises a bare `ValueError` for an integer past the
    # interpreter's digit limit (4,300 by default, since 3.10.7), and that one escaped
    # without the file and line this module promises on every malformed line. The
    # decoder raises `RecursionError` past ~1000 levels of nesting, which is not a
    # `ValueError` at all (#401 review).
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        raise ValueError(f"{where}: not an evidence row: {exc!r}") from None
    # A member the line does not have is refused, not dropped: a reader that silently
    # discarded one would normalize a malformed file into an apparently valid row
    # (#401 review). A member the format *used* to have is named for what it was, so
    # a producer written against the claim format is told what to write instead
    # rather than being handed a bare "unknown member" (#421).
    if extra := sorted(set(entry) - _LINE_KEYS):
        if retired := [key for key in extra if key in _RETIRED_LINE_KEYS]:
            raise ValueError(
                f"{where}: {retired[0]!r} is not a member of an evidence row — {_RETIRED_LINE_KEYS[retired[0]]}"
            )
        raise ValueError(f"{where}: line has unknown member(s) {extra} (expected {sorted(_LINE_KEYS)})")
    _check_entry(where, field, target_key_value, raw_value)
    # The column is checked here rather than trusted: `"column": 7` would otherwise
    # ride through as a source member. `as_claim_source` then supplies the four facts
    # the envelope holds.
    column = member_optional_str(entry, "column", "source column", where)
    if (source := by_column.get(column)) is None:
        source = by_column[column] = envelope_source.as_claim_source(column)
    return EvidenceEntry(field=field, target_key_value=target_key_value, raw_value=raw_value, source=source)


def _where(name: str, unit: str, n: int) -> str:
    """Name the row being refused: ``…ndjson row 3`` writing, ``…ndjson line 4`` reading.

    Built once per row by each caller rather than at each raise. Both sides refuse a
    line in several places, so threading the three parts down to every one of them
    cost more in parameters than the f-string costs to build — a judgement that only
    holds because this is one small string against a JSON encode on the same line.

    The two sides count differently on purpose — a writer has no line numbers yet and
    a reader's ``n`` includes the envelope — so the unit travels with the count rather
    than being inferred from it.
    """
    return f"{name} {unit} {n}"


def _check_entry(where: str, field: Any, target_key_value: Any, raw_value: Any) -> None:
    """Check the three members of an evidence line, in whichever direction it crosses.

    One definition of the line's shape for the writer and the reader both, so the two
    cannot drift into accepting different files. ``where`` is what the caller calls
    this line — ``…ndjson row 3`` writing, ``…ndjson line 4`` reading.

    The *key* is not checked here: which key this file is keyed by is the envelope's
    ``target_key``, checked once when the envelope is built, and the line carries only
    its value.
    """
    # Type before membership: an unhashable `field: []` raises TypeError from the
    # frozenset lookup, which escapes as a traceback instead of the ValueError naming
    # the file and the line that this module promises.
    if not isinstance(field, str) or field not in _FIELDS:
        raise ValueError(f"{where}: unknown dimension {field!r} (expected one of {sorted(CLASSIFICATION_FIELDS)})")
    if not isinstance(target_key_value, str) or not target_key_value:
        raise ValueError(
            f"{where}: target_key_value is {target_key_value!r} — a row with nothing to match on can attach to no file"
        )
    # The only check `raw_value` gets, and deliberately the only one. It is not
    # checked against the dimension's vocabulary: a source's spellings are its own,
    # and a value we have no word for is what the review queue is for (contract 3.7,
    # #399). It is not checked for emptiness either: an empty cell is something the
    # source published, and what `""` means is a rule's to decide, not a file
    # format's (#421). Nor for line breaks, which JSON escapes and no report prints —
    # unlike the envelope's identifiers, which `_describe` puts on a report line.
    if not isinstance(raw_value, str):
        raise ValueError(
            f"{where}: raw_value is {type(raw_value).__name__}, not a string — "
            "a row records what the source wrote, verbatim"
        )


def _read_envelope(path: Path, f: BinaryIO) -> EvidenceFileEnvelope:
    """Consume line 1 of an open evidence file as its envelope.

    The one place an evidence file's first line is turned into provenance, shared by
    :func:`read_envelope` (which wants only that) and :func:`iter_evidence` (which
    reads on from there), so a file with no first line is refused in the same words
    either way. ``f`` is a byte handle for the reason :func:`iter_evidence` opens one:
    a decode failure is reported as a malformed line, not raised from inside a file
    iterator.
    """
    # Capped, because `readline` on a file with no newline in it reads the file: a
    # 27 MB evidence file written as one JSON array peaked at 193 MB before the shape
    # check refused it, in the module whose reason for existing is that a corpus of
    # rows must not be loaded whole (#374, #401 review). An envelope is a few
    # hundred bytes; a megabyte is room for an implausibly long url and nothing like
    # a corpus.
    raw = f.readline(_MAX_ENVELOPE_BYTES)
    if len(raw) == _MAX_ENVELOPE_BYTES and not raw.endswith(b"\n"):
        raise ValueError(
            f"{path.name} line 1: no line break in the first {_MAX_ENVELOPE_BYTES} bytes — "
            "an evidence file is one envelope and one row per line, not a single JSON document"
        )
    first = _decode(raw, f"{path.name} line 1")
    if not first.strip():
        raise ValueError(f"{path.name}: line 1 must be the {ENVELOPE_KEY} envelope, and this file starts empty")
    return _envelope_from_line(path, first)


def _envelope_from_line(path: Path, line: str) -> EvidenceFileEnvelope:
    """Parse line 1 as an envelope, or raise naming the file.

    This owns only the file layout — unwrap the JSON, find the ``evidence_file`` key —
    and hands the block to :meth:`EvidenceFileEnvelope.from_dict`, which owns what an
    envelope's members must be. The same rules then run when an importer *builds* an
    envelope (``EvidenceFileEnvelope.__post_init__``), so a writer cannot produce a file
    this reader will refuse (#401 review).

    The line is closed as well as the envelope inside it: ``evidence_file`` must be its
    only key. Extracting the block and ignoring its siblings would let
    ``{"evidence_file": …, "unexpected": 1}`` through while an unknown member *within*
    the envelope is refused — the same malformed provenance, discarded rather than
    reported, depending only on which side of one brace it sat (#401 review).
    """
    where = f"{path.name} line 1"
    try:
        wrapper = json.loads(line)
    # `ValueError` covers `json.JSONDecodeError` and the bare one the decoder raises
    # for an over-long integer; `RecursionError` is neither. See `_entry_from_line`.
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"{where}: not a {ENVELOPE_KEY} envelope: {exc!r}") from None
    if not isinstance(wrapper, dict) or set(wrapper) != {ENVELOPE_KEY}:
        raise ValueError(
            f"{where}: line 1 must be an object whose only key is {ENVELOPE_KEY!r}, "
            f"and this one is {sorted(wrapper) if isinstance(wrapper, dict) else type(wrapper).__name__}"
        )
    return EvidenceFileEnvelope.from_dict(wrapper[ENVELOPE_KEY], where)
