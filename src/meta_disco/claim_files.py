"""Claim files: what an out-of-band importer writes and a run reads (issue #401).

An importer runs *out of band* from classification — when a catalog refreshes, with
network — and writes a claim file. The main loop reads it. Classification stays
offline and deterministic while the importers do the networked work, the same shape
as the evidence cache, and either side can be re-run without forcing the other::

    inference  →  import (read claim files, match to our files)  →  one claim stream
                  →  resolve  →  output

This module is the artefact and its IO: the layout on disk, the envelope, the line
format, the streaming writer and reader, and the report a run prints of what it
consumed. Anything that needs to find or write a claim file should come through here
rather than re-deriving the layout. Matching a claim to one of our files is #400b,
and the importers that will produce these files are #369 (AnVIL manifests) and #394
(external catalogs).

**Currency is not decided here.** A run reports each file's source, version, catalog
and age and imports from all of them. It cannot do better offline: the sources share
no version to compare, and AnVIL deletes a superseded catalog rather than keeping it
to be matched against. The two places that can act on the question own it instead —
the importer, which compares its file's ``corpus_catalog`` against the configured one
when deciding to re-fetch, and the run's output, which records the catalog it
enhances so that an enhancement offered to a catalog that has moved on is refused at
that boundary.

**The file.** One ``.ndjson`` file: line 1 is the envelope, every later line is one
claim. NDJSON rather than a JSON array because 708,088 files by 5 dimensions by
several sources is millions of claims, and a whole-file ``json.load`` is already the
memory ceiling this corpus keeps hitting (#374); ``anvil_files_metadata.ndjson`` is
the existing precedent. Putting the envelope on line 1 rather than in a sidecar
keeps the claims inseparable from their provenance, and lets a reader have the whole
of it after a single ``readline``.

**What a claim line carries, and what it does not.** The line holds the dimension,
the source's *own* key and its value, and the claim itself. The key is the source's
because an importer emits claims keyed by whatever the source publishes and needs no
knowledge of our corpus (#400b); the claim's own ``join_key``/``match_exact`` are
filled in by the join, when a match actually happens, not here. The claim's ``source``
is factored into the envelope on write and rehydrated on read — name, url and table
are constant across the file, so only ``column`` survives per line.
"""

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from .models import CLASSIFICATION_FIELDS, JOIN_KEYS, ClaimFileEnvelope, ClaimSource

# The key line 1 is wrapped in. An envelope is structurally distinguishable from a
# claim rather than distinguishable by position alone, so a truncated or concatenated
# file fails as a shape violation instead of reading an envelope as a claim.
ENVELOPE_KEY = "claim_file"

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

# Write buffer for a claim file. The default 8 KB would mean a syscall every few
# claims across a multi-gigabyte sequential write.
_WRITE_BUFFER_BYTES = 1 << 20


@dataclass(frozen=True, slots=True)
class ClaimEntry:
    """One line of a claim file: a claim, its dimension, and the key it is keyed by.

    ``field`` is one of ``CLASSIFICATION_FIELDS``. ``join_key`` names which key
    ``key_value`` is (``file_name``, ``file_md5sum``, …) — the source's own key, not
    a statement that anything matched. ``claim`` is a claim dict as
    ``rule_engine.make_claim`` builds it, carrying the :class:`ClaimSource` it came
    from; :func:`write_claim_file` factors that source into the envelope and
    :func:`iter_claims` puts it back, so a caller on either side always holds a whole
    claim.

    ``slots=True`` because :func:`iter_claims` builds one of these per claim: a few
    million per source, each of which would otherwise carry its own ``__dict__``.
    """

    field: str
    join_key: str
    key_value: str
    claim: dict


@dataclass(frozen=True)
class ClaimFileStatus:
    """One claim file as a run sees it: its provenance, or why it could not be read.

    Exactly one of the two is set. ``error`` is the envelope's own parse or IO
    failure, held rather than raised so that one unreadable file does not hide the
    provenance of the ones behind it in the report.

    A run does not judge a claim file beyond this. Whether the claims still describe
    the catalog being classified is settled downstream — the run's output records
    which catalog it enhances, and an enhancement offered to a catalog that has moved
    on is refused there — and by the importer, which compares its own file's
    ``corpus_catalog`` against the configured one when deciding to re-fetch.
    """

    path: Path
    envelope: ClaimFileEnvelope | None
    error: str | None = None


def write_claim_file(path: Path, envelope: ClaimFileEnvelope, entries: Iterable[ClaimEntry]) -> int:
    """Write one claim file, streaming; return the number of claims written.

    ``entries`` is consumed once and no more than the current entry is held, so an
    importer can stream a catalog straight through. The file is written to a
    temporary path and renamed into place only after every claim is out — as
    ``azul_manifest.write_input_files`` does — so a source that raises part-way
    through leaves the previous claim file untouched rather than half-replaced.

    Every entry is validated against the envelope as it is written
    (:func:`_claim_line`): an unknown dimension or join key, or a claim whose source
    is not the source the envelope names, raises rather than being written and
    discovered by a reader later. The envelope's own source is serialized once, here,
    and compared against per claim — it is constant for the file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    file_source = _without_column(envelope.source.to_dict())
    written = 0
    try:
        with tmp.open("w", encoding="utf-8", buffering=_WRITE_BUFFER_BYTES) as f:
            f.write(_encode({ENVELOPE_KEY: envelope.to_dict()}))
            f.write("\n")
            for entry in entries:
                written += 1
                f.write(_encode(_claim_line(file_source, entry, f"{path.name} claim {written}")))
                f.write("\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)
    return written


def read_envelope(path: Path) -> ClaimFileEnvelope:
    """The claim file's envelope, read from its first line alone.

    A run decides whether to refuse a file from its provenance, so that decision
    costs one line and not the file. Raises ``ValueError`` naming the file when line
    1 is absent or is not an envelope.
    """
    with path.open(encoding="utf-8") as f:
        return _read_envelope(path, f)


def iter_claims(path: Path) -> Iterator[ClaimEntry]:
    """Every claim in one claim file on disk, in file order, streamed.

    Line 1 is consumed as the envelope before any claim is yielded, because the
    source it carries is what each claim's ``source`` is rehydrated from — so a file
    whose envelope is malformed fails at once rather than after some claims have been
    handed out. A blank line carries no claim and is passed over. Any other line that
    will not parse, or that is not a claim, raises ``ValueError`` naming the file and
    the line — the shape ``azul_manifest.iter_verbatim_entities`` uses, and for its
    reason: an import that silently dropped claims would understate what a source
    said, which is the one thing it must not do.
    """
    with path.open(encoding="utf-8") as f:
        file_source = _without_column(_read_envelope(path, f).source.to_dict())
        for n, line in enumerate(f, start=2):
            if line.isspace():
                continue
            yield _entry_from_line(path, n, line, file_source)


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
    if it names one, fetch date and age — so a run says which claim files it consumed
    and how old they were. Returns the statuses in the order printed.

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
    """One report line for one claim file: its provenance and age, or why it would not read."""
    name = status.path.relative_to(root)
    if status.envelope is None:
        return f"UNREADABLE {name} — {status.error}"
    envelope = status.envelope
    source = envelope.source
    where = f"{source.name}/{source.table}" if source.table else source.name
    built_for = f"for catalog {envelope.corpus_catalog}, " if envelope.corpus_catalog is not None else ""
    return (
        f"{name} — {where}, version {envelope.source_version}, {built_for}"
        f"fetched {envelope.fetched_at.isoformat()} ({_age_phrase(envelope.fetched_at, now)})"
    )


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


def _claim_line(file_source: dict, entry: ClaimEntry, where: str) -> dict:
    """Serialize one entry, factoring its claim's source into the file's.

    ``file_source`` is the envelope's source without its column, serialized once by
    :func:`write_claim_file`. The claim keeps every key ``make_claim`` gave it except
    ``source``, which is replaced by that source's ``column`` alone — the only member
    that varies within one file, and omitted too when the source has none. Writing
    the other three on every line would be the envelope's content repeated a few
    million times.

    That factoring is also a check: a claim whose source is not the source the
    envelope names does not belong in this file, and saying so here is cheaper than
    a reader discovering that every claim it rehydrated was attributed to the wrong
    table.
    """
    _check_entry(where, entry.field, entry.join_key, entry.key_value, entry.claim)
    claim = dict(entry.claim)
    source = claim.pop("source", None)
    if not isinstance(source, dict):
        raise ValueError(f"{where}: carries no source — a claim file holds claims from an external source")
    if _without_column(source) != file_source:
        raise ValueError(f"{where}: comes from {_without_column(source)}, but this file's envelope names {file_source}")
    if (column := source.get("column")) is not None:
        claim["column"] = column
    return {"field": entry.field, "join_key": entry.join_key, "key_value": entry.key_value, "claim": claim}


def _entry_from_line(path: Path, n: int, line: str, file_source: dict) -> ClaimEntry:
    """Parse one claim line, rehydrating its source from the file's.

    ``file_source`` is the envelope's source without its column, serialized once by
    :func:`iter_claims`. The claim comes back whole — that source, with this line's
    ``column`` — so a consumer reads the same claim the importer built and never has
    to consult the envelope itself. Each claim gets its own copy of the source rather
    than a shared one, so a consumer that edits one claim cannot reach the others.
    """
    try:
        entry = json.loads(line)
        field, join_key, key_value, claim = (entry["field"], entry["join_key"], entry["key_value"], entry["claim"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"{path.name} line {n}: not a claim: {exc!r}") from None
    _check_entry(f"{path.name} line {n}", field, join_key, key_value, claim)
    column = claim.pop("column", None)
    claim["source"] = dict(file_source) if column is None else {**file_source, "column": column}
    return ClaimEntry(field=field, join_key=join_key, key_value=key_value, claim=claim)


def _check_entry(where: str, field: Any, join_key: Any, key_value: Any, claim: Any) -> None:
    """Check the four members of a claim line, in whichever direction it is crossing.

    One definition of the line's shape for the writer and the reader both, so the two
    cannot drift into accepting different files; ``where`` is what each side calls the
    line it is refusing (``…ndjson claim 3`` writing, ``…ndjson line 4`` reading).
    """
    if field not in _FIELDS:
        raise ValueError(f"{where}: unknown dimension {field!r} (expected one of {sorted(CLASSIFICATION_FIELDS)})")
    if join_key not in JOIN_KEYS:
        raise ValueError(f"{where}: unknown join_key {join_key!r} (expected one of {sorted(JOIN_KEYS)})")
    if not isinstance(key_value, str) or not key_value:
        raise ValueError(f"{where}: no {join_key} value to key the claim by")
    if not isinstance(claim, dict):
        raise ValueError(f"{where}: claim is {type(claim).__name__}, not an object")


def _without_column(source: dict) -> dict:
    """A source dict minus its column — the part a claim file's envelope factors out."""
    return {k: v for k, v in source.items() if k != "column"}


def _read_envelope(path: Path, f: TextIO) -> ClaimFileEnvelope:
    """Consume line 1 of an open claim file as its envelope.

    The one place a claim file's first line is turned into provenance, shared by
    :func:`read_envelope` (which wants only that) and :func:`iter_claims` (which
    reads on from there), so a file with no first line is refused in the same words
    either way.
    """
    first = f.readline()
    if not first.strip():
        raise ValueError(f"{path.name}: line 1 must be the {ENVELOPE_KEY} envelope, and this file starts empty")
    return _envelope_from_line(path, first)


def _envelope_from_line(path: Path, line: str) -> ClaimFileEnvelope:
    """Parse and validate line 1 as an envelope, or raise naming the file.

    Every member is checked here rather than where a consumer reads it: an envelope
    is read once per file and is what the refusal decision rests on, so an
    unparseable ``fetched_at`` or a source with no name must fail as a malformed
    claim file, not as a report that cannot render.
    """
    try:
        block = json.loads(line)[ENVELOPE_KEY]
        source, fetched_at = block["source"], block["fetched_at"]
        name, version = source["name"], block["source_version"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"{path.name} line 1: not a {ENVELOPE_KEY} envelope: {exc!r}") from None
    try:
        fetched = datetime.fromisoformat(fetched_at)
    except (TypeError, ValueError):
        raise ValueError(
            f"{path.name} line 1: envelope fetched_at {fetched_at!r} is not an ISO 8601 datetime"
        ) from None
    return ClaimFileEnvelope(
        source=ClaimSource(
            name=_required_str(path, "source name", name),
            url=_optional_str(path, "source url", source.get("url")),
            table=_optional_str(path, "source table", source.get("table")),
            column=_optional_str(path, "source column", source.get("column")),
        ),
        fetched_at=fetched,
        source_version=_required_str(path, "source_version", version),
        corpus_catalog=_optional_str(path, "corpus_catalog", block.get("corpus_catalog")),
    )


def _required_str(path: Path, label: str, value: Any) -> str:
    """Return an envelope member that must be a non-empty string, or raise.

    An explicit ``null`` is rejected here rather than in the key check above: a
    ``"name": null`` is a present key, so it survives the ``KeyError`` guard, and a
    source with no name identifies nothing.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path.name} line 1: envelope {label} is {value!r}, not a non-empty string")
    return value


def _optional_str(path: Path, label: str, value: Any) -> str | None:
    """Return an envelope member a source may not have, validated when it has one."""
    return None if value is None else _required_str(path, label, value)
