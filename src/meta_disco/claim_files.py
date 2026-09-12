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

This module is the artefact and its IO: the layout on disk, the envelope, the line
format, the streaming writer and reader, and the report a run prints of what it
found — found and not consumed, since no evidence reaches classification until the
join lands (#402). Anything that needs to find or write an evidence file should come
through here rather than re-deriving the layout. Matching a row to one of our files
is #402, and the importers that will produce these files are #369 (AnVIL manifests)
and #394 (external catalogs).

**What a run does with these today.** It discovers them and reports each one's
source, version, catalog and age — ``classify_run.run_all_classifications`` calls
:func:`report_claim_files` and never :func:`iter_claims`. No evidence reaches
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
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from .models import (
    CLASSIFICATION_FIELDS,
    ClaimFileEnvelope,
    ClaimFileSource,
    ClaimSource,
    member_optional_str,
)

# The key line 1 is wrapped in. An envelope is structurally distinguishable from an
# evidence row rather than distinguishable by position alone, so a truncated or
# concatenated file fails as a shape violation instead of reading an envelope as a row.
ENVELOPE_KEY = "evidence_file"

# What `discover` treats as a claim file. NDJSON is the format, so the suffix is the
# membership test — a README or a scratch .json beside them is not picked up.
CLAIM_FILE_GLOB = "*.ndjson"

# Where an importer leaves the claim files a run reads. One directory per source
# under it (`data/claims/hprc/`, `data/claims/anvil/`): a claim file is the same kind
# of artefact whoever wrote it, so a run discovers them all by walking one root
# rather than by knowing which sources exist. This module is
# <root>/src/meta_disco/claim_files.py, so the repo root is three levels up.
DEFAULT_CLAIMS_ROOT = Path(__file__).resolve().parents[2] / "data" / "claims"

# The dimension names as a set, for the membership check every claim pays twice — on
# the way in and on the way out. `CLASSIFICATION_FIELDS` stays the tuple it is
# because its order is the canonical output order; this is the same five names.
_FIELDS = frozenset(CLASSIFICATION_FIELDS)

# One encoder for the write loop, built once. Compact separators drop ~7% of the
# bytes across millions of lines, and `json.dumps(..., separators=...)` cannot be
# used for it: that constructs a fresh encoder on every call.
_encode = json.JSONEncoder(separators=(",", ":")).encode

# Write buffer for a claim file. A written claim line measures around 170 bytes, so
# the default 8 KB is a syscall every 50 claims or so across a multi-gigabyte
# sequential write; a megabyte is one per 6,000.
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
    :func:`write_claim_file` factors it back into the envelope and :func:`iter_claims`
    puts it back, so a caller on either side holds whole provenance without consulting
    line 1. Reconcile needs all four levels — a rule may condition on provenance
    (contract 3.4), and an unmatched value is listed by source, dataset, table and
    column (5.2).

    ``slots=True`` because :func:`iter_claims` builds one of these per row: a few
    million per source, each of which would otherwise carry its own ``__dict__``.
    """

    field: str
    target_key_value: str
    raw_value: str
    source: ClaimSource


@dataclass(frozen=True)
class ClaimFileStatus:
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
    envelope: ClaimFileEnvelope | None
    error: str | None = None


def write_claim_file(path: Path, envelope: ClaimFileEnvelope, entries: Iterable[EvidenceEntry]) -> int:
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
    (``ClaimFileEnvelope.__post_init__``).

    ``path`` must end in ``.ndjson``, because that is what :func:`discover` looks for.
    Writing ``catalog.json`` otherwise succeeds, returns a row count, and is then
    invisible to every run — an importer's one-character mistake becoming a silent
    no-op with a success return, which is the one failure mode an import must not
    have (#401 review).
    """
    if path.suffix != CLAIM_FILE_GLOB.lstrip("*"):
        raise ValueError(
            f"{path.name}: an evidence file must be named {CLAIM_FILE_GLOB} — "
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


def read_envelope(path: Path) -> ClaimFileEnvelope:
    """The evidence file's envelope, read from its first line alone.

    A run decides whether to refuse a file from its provenance, so that decision
    costs one line and not the file. Raises ``ValueError`` naming the file when line
    1 is absent or is not an envelope.
    """
    with path.open("rb") as f:
        return _read_envelope(path, f)


def iter_claims(path: Path) -> Iterator[EvidenceEntry]:
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
        # column (`write_claim_file`). The envelope's members are constant and only
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
    """Every claim file under ``root``, in a stable order; empty when there are none.

    A missing ``root`` is not an error: no claim files present is the ordinary state
    of a run today, and it means the run imports nothing — not that it is
    misconfigured.
    """
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob(CLAIM_FILE_GLOB) if p.is_file())


def report_claim_files(root: Path, now: datetime | None = None) -> list[ClaimFileStatus]:
    """Report every claim file under ``root``, and return what each one's status is.

    Prints one line per file — source, table, version, the catalog it was built for
    if it names one, fetch date and age — so a run says which claim files it found
    and how old they were. *Found* and not *consumed*: no claim reaches classification
    until the join lands (#402), and this report is the whole of what a run does with
    one today. Returns the statuses in the order printed.

    The report does not judge, and the run does not stop. Whether a claim file has
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
            statuses.append(ClaimFileStatus(path, None, f"envelope could not be read: {exc}"))
            continue
        statuses.append(ClaimFileStatus(path, envelope))

    if not statuses:
        print(f"Claim files: none under {root} — this run imports nothing.")
        return statuses
    print(f"Claim files under {root}:")
    for status in statuses:
        print(f"  {_describe(status, root, now)}")
    return statuses


def _describe(status: ClaimFileStatus, root: Path, now: datetime | None) -> str:
    """One report line for one claim file: both sides of its join, and its age.

    Reads as *what it came from* → *what it is about*, because a person checking a
    run's claim files wants to see which corpus each one will attach to as much as
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
    holds one clock and a claim file writes whichever kind its importer had — so
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
    table. The comparison goes through :meth:`ClaimFileSource.as_claim_source`, so the
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
    name: str, n: int, line: str, envelope_source: ClaimFileSource, by_column: dict[str | None, ClaimSource]
) -> EvidenceEntry:
    """Parse one evidence line, attaching the provenance its envelope carries.

    ``envelope_source`` is the file's source, read once by :func:`iter_claims`, and
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

    ``name`` is the file's name, hoisted out of the read loop by :func:`iter_claims`,
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


def _read_envelope(path: Path, f: BinaryIO) -> ClaimFileEnvelope:
    """Consume line 1 of an open evidence file as its envelope.

    The one place a claim file's first line is turned into provenance, shared by
    :func:`read_envelope` (which wants only that) and :func:`iter_claims` (which
    reads on from there), so a file with no first line is refused in the same words
    either way. ``f`` is a byte handle for the reason :func:`iter_claims` opens one:
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


def _envelope_from_line(path: Path, line: str) -> ClaimFileEnvelope:
    """Parse line 1 as an envelope, or raise naming the file.

    This owns only the file layout — unwrap the JSON, find the ``evidence_file`` key —
    and hands the block to :meth:`ClaimFileEnvelope.from_dict`, which owns what an
    envelope's members must be. The same rules then run when an importer *builds* an
    envelope (``ClaimFileEnvelope.__post_init__``), so a writer cannot produce a file
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
    return ClaimFileEnvelope.from_dict(wrapper[ENVELOPE_KEY], where)
