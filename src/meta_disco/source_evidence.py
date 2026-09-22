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
(``value_map``, #414), whose ``claims_from`` is built for the reconcile stage (#432)
and is called by nothing in a run until that stage exists; the table checks a declared
term against its slot's vocabulary when it loads.

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
it is checked once against ``IMPORTER_SOURCE_TYPES`` rather than a few million times,
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
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from pydantic import ValidationError

from .models import (
    CLASSIFICATION_FIELDS,
    JOIN_KEY_FILE_NAME,
    SOURCE_PUBLISHED_VALUE,
    ClaimSource,
    _reject_unknown,
    member_optional_str,
    parse_iso_datetime,
)
from .schema.classification_model import EvidenceFileEnvelope, EvidenceFileSource, EvidenceTarget

__all__ = ["EvidenceFileEnvelope", "EvidenceFileSource", "EvidenceTarget"]

# The key line 1 is wrapped in. An envelope is structurally distinguishable from an
# evidence row rather than distinguishable by position alone, so a truncated or
# concatenated file fails as a shape violation instead of reading an envelope as a row.
ENVELOPE_KEY = "evidence_file"

# What `discover` treats as an evidence file. NDJSON is the format, so the suffix is the
# membership test — a README or a scratch .json beside them is not picked up.
EVIDENCE_FILE_SUFFIX = ".ndjson"
EVIDENCE_FILE_GLOB = f"*{EVIDENCE_FILE_SUFFIX}"

# Where an importer leaves the evidence files a run reads. One directory per source
# under it (`data/source_evidence/hprc/`, `.../anvil/`): an evidence file is the same
# kind of artefact whoever wrote it, so a run discovers them all by walking one root
# rather than by knowing which sources exist. `source_evidence` and not `evidence`,
# which `data/` already uses for the fetched-header cache — two unrelated things, and
# a shared name would have read as one. This module is
# <root>/src/meta_disco/source_evidence.py, so the repo root is three levels up.
DEFAULT_SOURCE_EVIDENCE_ROOT = Path(__file__).resolve().parents[2] / "data" / "source_evidence"

# An import is a generation (#369). An importer writes
# `<root>/<source>/<version>/<dataset>/<generation>/<table>.ndjson` and never overwrites
# (`anvil_evidence.import_dataset` refuses an existing generation directory; nothing here does):
# a mapping removed between two imports is absent from the next generation rather than
# left on disk as a valid-looking file. `discover` returns the newest generation of each
# dataset and only that one; the ones behind it are kept as history. The generation sits
# under the dataset, not above it, because a dataset is imported whole while a run may
# import one or all. Three "when"s stay distinct: `version` is the source's own (a
# catalog such as anvil15), the generation is ours (when we imported), and the
# envelope's `fetched_at` is when the source was fetched.
GENERATION_FORMAT = "%Y%m%dT%H%M%SZ"
_GENERATION = re.compile(r"\d{8}T\d{6}Z")
# A generation being written sits beside its final name with this suffix and is renamed
# into place only once every file is out, so a generation exists whole or not at all:
# a kill part-way leaves a `<stamp>.partial` directory, which `discover` never reads and
# `report_evidence_files` names as an unfinished import.
PARTIAL_SUFFIX = ".partial"

# The dimension names as a set, for the membership check every row pays twice — on
# the way in and on the way out. `CLASSIFICATION_FIELDS` stays the tuple it is
# because its order is the canonical output order; this is the same five names.
_FIELDS = frozenset(CLASSIFICATION_FIELDS)

# One encoder for the write loop, built once. Compact separators drop ~7% of the
# bytes across millions of lines, and `json.dumps(..., separators=...)` cannot be
# used for it: that constructs a fresh encoder on every call.
_encode = json.JSONEncoder(separators=(",", ":")).encode

# Write buffer for an evidence file. A written line measures around 126 bytes — a row
# stopped carrying a claim in #421 — so the default 8 KB is a syscall every 65 rows or
# so across a multi-gigabyte sequential write; a megabyte is one per 8,300.
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
_EXPECTED_LINE_KEYS = tuple(sorted(_LINE_KEYS))

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


# --- The envelope and its parts -----------------------------------------------
#
# `EvidenceFileEnvelope`, `EvidenceFileSource` and `EvidenceTarget` are the classes
# gen-pydantic emits from the schema (`schema/classification_model.py`, #494), used
# as they are and re-exported here for the importers. The schema is what an envelope
# is — which members, which are required, that none carries a line break, that
# `source_type` is a kind an importer may write and `target_key` a key of the target
# — and the generated model carries every one of those, `extra="forbid"` included, so
# the reader and the schema refuse the same files by construction. Until #494 three
# frozen dataclasses re-stated all of that by hand, with a test pinning the two copies
# of the `fetched_at` pattern equal; the drift test in `schema/tests` now holds the
# model to the schema instead.
#
# `fetched_at` is a string on the model, as it is in the schema, which pins it by
# pattern rather than `range: datetime` so that a date with no time of day is refused
# instead of read as midnight. The one place a run wants an instant — the age in the
# evidence report — parses it through `parse_iso_datetime`, and the reader parses it
# once at line 1 so a well-shaped timestamp that is not a real day fails as a
# malformed file rather than inside the report.
#
# What the generator cannot express is one rule and lives in one function:
# `require_scoped_target`, which the schema declares under `rules:` and gen-pydantic
# drops. `ClaimSource` stays a dataclass in `models`: it names where a raw value came
# from on a real claim in output evidence, which the rule engine builds and every
# consumer reads, and its serializer runs once per imported claim.


def claim_source_for(source: EvidenceFileSource, column: str | None) -> ClaimSource:
    """The per-claim :class:`ClaimSource` a row in a file with this source carries.

    A field copy — the envelope's four facts, plus the column this particular row
    was read from. ``dataset`` crosses with the rest: it is what makes the column
    legible, since the same column name means different things in different
    datasets, and a consumer reading the output ``evidence`` array cannot go back to
    the evidence file to find it.

    Called once per distinct column by the reader, which caches what it returns for
    the whole file (:func:`iter_evidence`); the envelope stores these once for the
    same reason, rather than repeating them on a few million lines.
    """
    return ClaimSource(
        name=source.repository, url=source.url, dataset=source.dataset, table=source.table, column=column
    )


def require_scoped_target(envelope: EvidenceFileEnvelope, where: str) -> None:
    """Refuse an envelope keyed by ``file_name`` that names no target dataset.

    A key that is not unique across the target cannot be matched without a scope,
    and ``file_name`` is the one in the vocabulary that is not: present on every
    record but non-unique on 69.4% of the corpus's 708,088 rows, against 2 rows in
    16,271 within a single dataset. Writing an unscoped one produces a file whose rows
    the join cannot attach to a single file — refused where the file is written and
    where it is read rather than discovered when the join fans out (#401 review).

    The schema declares the same rule on ``EvidenceFileEnvelope`` and the schema gate
    enforces it; gen-pydantic does not emit class rules, so the generated model does
    not, and this is the runtime's copy (#494).
    """
    if envelope.target_key == JOIN_KEY_FILE_NAME and envelope.target.dataset is None:
        raise ValueError(
            f"{where}: target_key {JOIN_KEY_FILE_NAME!r} needs a target dataset to scope it — "
            "a bare file name is non-unique on 69% of the corpus and matches no single row"
        )


def _envelope_from_block(block: object, where: str) -> EvidenceFileEnvelope:
    """Validate line 1's block as an envelope, or raise a ``ValueError`` naming ``where``.

    The generated model does the checking; this re-words its refusal. A
    ``ValidationError`` names the model and lists each fault by location, which is
    right for a caller holding the object and wrong for a person reading a run's
    report, who needs the file and the line in front of it and one message per fault
    behind. An unknown member is named as such rather than as pydantic's "extra
    inputs are not permitted", because it is the mistake a producer makes.
    """
    try:
        envelope = EvidenceFileEnvelope.model_validate(block)
    except ValidationError as exc:
        faults = []
        for error in exc.errors():
            location = " ".join(str(part) for part in error["loc"])
            if error["type"] == "extra_forbidden":
                faults.append(f"unknown member {location!r}")
            else:
                faults.append(f"{location}: {error['msg']}")
        raise ValueError(f"{where}: envelope {'; '.join(faults)}") from None
    require_scoped_target(envelope, where)
    parse_iso_datetime(envelope.fetched_at, "envelope fetched_at", where)
    return envelope


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

    A run does not judge an evidence file beyond this and the published-source check
    (:func:`require_one_published_source`, #497). Whether the rows still describe
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
    (:func:`_evidence_line`): an unknown dimension, a non-string ``raw_value``, an
    empty ``target_key_value``, or a row whose source is not the source the envelope
    names, raises rather than being written and discovered by a reader later. The
    envelope's four source facts are flattened once, here, and compared against per
    row — they are constant for the file. The envelope was checked when it was built
    (:func:`require_scoped_target`; the generated model checked the rest when the
    envelope was built).

    A *retired* member — a mapped ``value``, a ``tier``, a ``join_key`` — is not
    refused here because it cannot get this far: ``EvidenceEntry`` has four members
    and none of them is an answer. Refusing one by name is the reader's job
    (:func:`_entry_from_line`), where a hand-edited line can carry it.

    ``path`` must end in ``.ndjson``, because that is what :func:`discover` looks for.
    Writing ``catalog.json`` otherwise succeeds, returns a row count, and is then
    invisible to every run — an importer's one-character mistake becoming a silent
    no-op with a success return, which is the one failure mode an import must not
    have (#401 review).
    """
    if path.suffix != EVIDENCE_FILE_SUFFIX:
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
    # The four facts a row's source must agree with, flattened once for the file.
    # They are the whole of the envelope's source — only `column` varies per row, and
    # a row's column is what it is compared against itself, so it cannot disagree.
    # Taken from `claim_source_for` rather than read off the envelope directly, so the
    # writer's notion of "the same source" stays the reader's own.
    expected = claim_source_for(envelope.source, None)
    expected_facts = (expected.name, expected.url, expected.dataset, expected.table)
    require_scoped_target(envelope, "evidence file envelope")

    written = 0
    try:
        with tmp.open("w", encoding="utf-8", buffering=_WRITE_BUFFER_BYTES) as f:
            # Null members are omitted, not written out: a source either has a
            # dataset or does not, and the schema reads an absent one the same way.
            f.write(_encode({ENVELOPE_KEY: envelope.model_dump(exclude_none=True)}))
            f.write("\n")
            for entry in entries:
                written += 1
                f.write(_encode(_evidence_line(expected_facts, envelope.source, entry, name, written)))
                f.write("\n")
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return written


def list_cell(raw_value: str) -> list[str] | None:
    """The elements of a list-valued cell, or None where ``raw_value`` is one scalar.

    The inverse of how ``anvil_evidence._transcribe`` writes a list cell: a string is
    written verbatim and anything else as its JSON, so a list arrives as a JSON array
    of strings. Only that shape is a list here; a scalar that happens to start with
    ``[`` and is not one stays a scalar, and so does the text ``[]`` — the importer
    writes no line for an empty list, so one that arrives is a string the source
    wrote. Kept beside the line format so the encoding and its decoding are one fact
    in one module.
    """
    if not raw_value.lstrip().startswith("["):
        return None
    try:
        parsed = json.loads(raw_value)
    except ValueError:
        return None
    if parsed and isinstance(parsed, list) and all(isinstance(e, str) for e in parsed):
        return parsed
    return None


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


def new_generation(now: datetime | None = None) -> str:
    """A generation stamp for an import starting now, in UTC: ``20260920T031500Z``.

    Second resolution: two imports of one dataset within a second is not a case worth
    a longer name, and `anvil_evidence.import_dataset` refuses to write over one that
    exists. ``now`` fixes the clock for tests.
    """
    moment = now if now is not None else datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime(GENERATION_FORMAT)


def is_generation(name: str) -> bool:
    """Whether a directory name is a generation stamp as :func:`new_generation` writes one."""
    return _GENERATION.fullmatch(name) is not None


def generation_dir(root: Path, source: str, version: str, dataset: str, generation: str) -> Path:
    """Where one import of one dataset writes its files: the generation layout (contract
    2.5), spelled once.

    ``generation`` must be a stamp :func:`is_generation` accepts, because that is what
    :func:`discover` keys on: a directory named otherwise would be read as history-less
    flat files and never superseded.
    """
    if not is_generation(generation):
        raise ValueError(f"{generation!r} is not a generation stamp ({GENERATION_FORMAT}); see new_generation")
    return root / source / version / dataset / generation


def evidence_file_path(directory: Path, table: str) -> Path:
    """The file one table's rows go to inside a generation directory: ``<table>.ndjson``."""
    return directory / f"{table}{EVIDENCE_FILE_SUFFIX}"


def staging_dir(directory: Path) -> Path:
    """Where a generation is written before it is renamed to ``directory``."""
    return directory.with_name(directory.name + PARTIAL_SUFFIX)


def unfinished_imports(root: Path) -> list[Path]:
    """Every ``<stamp>.partial`` directory under ``root``: an import that was killed part-way.

    Left for a person to remove; nothing reads what is inside, and the import that
    made it did not finish. Empty when ``root`` is missing.
    """
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob(f"*{PARTIAL_SUFFIX}") if p.is_dir())


def discover(root: Path) -> list[Path]:
    """Every current evidence file under ``root``, in a stable order; empty when there are none.

    *Current* means: of the files written in the generation layout
    (:func:`generation_dir` — a stamp-named directory exactly four levels under
    ``root``), only those of the newest generation of each dataset — an older
    generation is history, kept on disk and never read by a run. A file anywhere else
    has no history to supersede it and is always current, a stamp-named directory at
    another depth included. A file under a ``.partial`` directory — an import that was
    killed before it finished — is never current. Newest is by stamp, which sorts as
    time because of the format; the run does not consult mtimes.

    A missing ``root`` is not an error: no evidence files present is the ordinary state
    of a run today, and it means the run imports nothing — not that it is
    misconfigured.
    """
    if not root.is_dir():
        return []
    found = sorted(
        p
        for p in root.rglob(EVIDENCE_FILE_GLOB)
        if p.is_file() and not any(part.endswith(PARTIAL_SUFFIX) for part in p.relative_to(root).parts)
    )
    newest: dict[Path, str] = {}
    for path in found:
        if (generation := _generation_of(root, path)) is not None:
            newest[path.parent.parent] = max(newest.get(path.parent.parent, ""), generation)
    return [p for p in found if (g := _generation_of(root, p)) is None or g == newest[p.parent.parent]]


def _generation_of(root: Path, path: Path) -> str | None:
    """The generation stamp a file sits under in the generation layout, or None where it does not.

    The layout is ``<root>/<source>/<version>/<dataset>/<generation>/<file>``, so the
    stamp is the fourth segment under ``root`` and nothing else: a version or dataset
    that happened to be spelled like a stamp would otherwise read as one.
    """
    parts = path.relative_to(root).parts
    return parts[3] if len(parts) == 5 and is_generation(parts[3]) else None


def report_evidence_files(root: Path, now: datetime | None = None) -> list[EvidenceFileStatus]:
    """Report every current evidence file under ``root``, and return what each one's status is.

    *Current* as :func:`discover` defines it: a superseded generation is neither
    reported nor read. An unfinished import (:func:`unfinished_imports`) is named as
    such and not read.

    Prints one line per file — source, table, version, the catalog it was built for
    if it names one, fetch date and age — so a run says which evidence files it found
    and how old they were. *Found* and not *consumed*: no claim reaches classification
    until the join lands (#402), and this report is the whole of what a run does with
    one today. Returns the statuses in the order printed.

    The report does not judge currency, and nothing here stops the run. Whether an evidence file has
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
    for partial in unfinished_imports(root):
        print(f"Unfinished import, not read (remove it by hand): {partial.relative_to(root)}")
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


def require_one_published_source(statuses: list[EvidenceFileStatus], published_tables: Mapping[str, str]) -> None:
    """Refuse the current evidence unless each repository's published source is the one declared (#497).

    ``published_tables`` is ``pipeline.PUBLISHED_TABLES`` — the repository whose files
    the evidence is about (``EvidenceTarget.system``) to its published table — or a
    test's stand-in; taken as a parameter so this module stays free of the pipeline
    and of any one repository's constants. Over the
    current files a run found (:func:`report_evidence_files`), the declaration is held
    in both directions, with ``ValueError``. A file from a repository's own declared
    table that carries any label but ``published_value`` is refused, the mislabelling
    ``anvil_evidence._check_kind`` refuses in a map. A ``published_value`` file is
    refused when its source repository is not the one its rows are about (a published
    source is that repository's own); when its source table is not the one declared for
    that repository, undeclared included; and when a second current one exists for the
    same target — repository, catalog version and dataset — naming both. The version is
    part of the key because *current* is per version
    (:func:`discover`): an anvil15 and an anvil16 generation are both current, and
    which describes the run's catalog is not decided here (module docstring, currency).
    A file whose envelope could not be read is already named in the report.

    The importer refuses a map that would write the wrong label (``anvil_evidence``),
    so what this catches is a file placed by hand or written by another tool.
    """
    # Keyed by the target's three members and not the target: the generated model is
    # not hashable (it is not frozen), and one file per (system, dataset, version) is
    # what the check means (#494).
    current: dict[tuple[str, str | None, str | None], Path] = {}
    for status in statuses:
        envelope = status.envelope
        if envelope is None:
            continue
        target = envelope.target
        repository = target.system
        # `declared` is None for a repository with no declaration, and a source's `table`
        # may be None too, so the two are never compared as equal: an undeclared
        # repository has no published table for a file to be from.
        declared = published_tables.get(repository)
        if envelope.source_type != SOURCE_PUBLISHED_VALUE:
            if declared is not None and envelope.source.repository == repository and envelope.source.table == declared:
                raise ValueError(
                    f"{status.path}: carries {envelope.source_type} from {repository}'s published table "
                    f"{envelope.source.table!r}, which carries {SOURCE_PUBLISHED_VALUE} and nothing else "
                    "(contract 7.12)"
                )
            continue
        if envelope.source.repository != repository:
            raise ValueError(
                f"{status.path}: carries {SOURCE_PUBLISHED_VALUE} from repository {envelope.source.repository!r} "
                f"about {repository}'s files — a published source is the repository's own (contract 7.12)"
            )
        if declared is None or envelope.source.table != declared:
            expected = (
                f"{repository}'s published source is {declared!r}"
                if declared is not None
                else f"{repository}'s published source is not declared"
            )
            raise ValueError(
                f"{status.path}: carries {SOURCE_PUBLISHED_VALUE} from table {envelope.source.table!r}, but "
                f"{expected} — a repository has exactly one published source (contract 7.12)"
            )
        key = (target.system, target.dataset, target.version)
        if key in current:
            raise ValueError(
                f"two current evidence files carry {SOURCE_PUBLISHED_VALUE} for {repository}/{target.dataset} "
                f"@{target.version}: {current[key]} and {status.path} — a repository has exactly one "
                "published source (contract 7.12), so one of them is not it"
            )
        current[key] = status.path


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
    # Every status a run builds holds an envelope read through `_envelope_from_block`,
    # which parsed this already, so for those this cannot raise.
    fetched_at = parse_iso_datetime(envelope.fetched_at, "envelope fetched_at", str(name))
    scope = f"{target.system}/{target.dataset}" if target.dataset else target.system
    generation = f" @{target.version}" if target.version else ""
    return (
        f"{name} — {_join_side(envelope.source.model_dump(), envelope.source_key)}"
        f" v{envelope.source_version}"
        f" -> {scope}[{envelope.target_key}]{generation},"
        f" fetched {envelope.fetched_at} ({_age_phrase(fetched_at, now)})"
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
    expected_facts: tuple[str | None, ...],
    envelope_source: EvidenceFileSource,
    entry: EvidenceEntry,
    name: str,
    n: int,
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
    table. ``expected_facts`` is what :func:`write_evidence_file` flattened out of the
    envelope for it; ``envelope_source`` is only for wording the refusal.

    What it does *not* check is anything a row could declare. An `EvidenceEntry` has
    four members and none of them is an answer, so a mapped ``value`` or a ``tier`` is
    unwritable rather than refused — :func:`_entry_from_line` is where a hand-edited
    line carrying one is turned away (:data:`_RETIRED_LINE_KEYS`).

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
    # A tuple compare against the four facts hoisted once per file, not a record
    # compare: `ClaimSource` has no `__slots__`, so its `__eq__` builds two 5-tuples
    # out of two `__dict__`s and cost 0.42 us a row — 41% of this function, against
    # 0.11 us here. `column` is left out because it is this row's own and is compared
    # against itself. The record was validated when it was built
    # (`ClaimSource.__post_init__`), so nothing here re-checks its members.
    if (source.name, source.url, source.dataset, source.table) != expected_facts:
        raise ValueError(
            f"{where}: comes from {source.to_dict()}, but this file's envelope names "
            f"{claim_source_for(envelope_source, source.column).to_dict()}"
        )
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
    the translation table (``value_map``, #414); ``make_claim``'s invariants apply
    there, and the vocabulary check when the table loads.

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
        if not isinstance(entry, dict):
            raise TypeError(f"line is a {type(entry).__name__}, not an object")
    # `ValueError` rather than `json.JSONDecodeError`, which is a subclass of it:
    # `json.loads` also raises a bare `ValueError` for an integer past the
    # interpreter's digit limit (4,300 by default, since 3.10.7), and that one escaped
    # without the file and line this module promises on every malformed line. The
    # decoder raises `RecursionError` past ~1000 levels of nesting, which is not a
    # `ValueError` at all (#401 review).
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError(f"{where}: not an evidence row: {exc!r}") from None
    # The member check runs *before* the three are read out, and that order is the
    # whole point of `_RETIRED_LINE_KEYS`. A line in #401's format carries `claim` and
    # no `raw_value`, so reading first raised `KeyError('raw_value')` and the named
    # refusal below — written for exactly that producer — could never fire (#421
    # review). A member the line does not have is refused rather than dropped, because
    # a reader that silently discarded one would normalize a malformed file into an
    # apparently valid row (#401 review).
    #
    # Membership before allocation, as `_check_entry` and the old `_rebuild_claim`
    # both were: `set(entry) - _LINE_KEYS` built two sets and a list on every
    # well-formed row, 0.22 us against 0.10 for the subset test.
    if not entry.keys() <= _LINE_KEYS:
        retired = next((key for key in sorted(entry) if key in _RETIRED_LINE_KEYS), None)
        if retired is not None:
            raise ValueError(f"{where}: {retired!r} is not a member of an evidence row — {_RETIRED_LINE_KEYS[retired]}")
        _reject_unknown(entry, _LINE_KEYS, _EXPECTED_LINE_KEYS, where, "line")
    try:
        field, target_key_value, raw_value = (entry["field"], entry["target_key_value"], entry["raw_value"])
    except KeyError as exc:
        raise ValueError(f"{where}: evidence row has no {exc.args[0]!r}") from None
    _check_entry(where, field, target_key_value, raw_value)
    # The column is checked here rather than trusted: `"column": 7` would otherwise
    # ride through as a source member. `claim_source_for` then supplies the four facts
    # the envelope holds.
    column = member_optional_str(entry, "column", "source column", where)
    if (source := by_column.get(column)) is None:
        source = by_column[column] = claim_source_for(envelope_source, column)
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
    # A line break is refused with it, because the schema's `EvidenceRow.target_key_value`
    # carries `pattern: "^[^\r\n]+\Z"` and without this the reader would accept a row
    # the gate rejects — the disagreement this module exists to prevent, in the
    # direction that is *not* safe (#421 review). It is the same rule the schema's
    # pattern applies to the envelope's identifiers, and for a stronger reason here: every key
    # in `JOIN_KEYS` is a file name, checksum, URI or accession, and none of them
    # contains one.
    if "\n" in target_key_value or "\r" in target_key_value:
        raise ValueError(
            f"{where}: target_key_value is {target_key_value!r}, which carries a line break — "
            "no key of the target contains one"
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
    and hands the block to :func:`_envelope_from_block`, where the generated model
    owns what an envelope's members must be. The same model runs when an importer
    *builds* an envelope, so a writer cannot produce a file this reader will refuse
    (#401 review).

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
    return _envelope_from_block(wrapper[ENVELOPE_KEY], where)
