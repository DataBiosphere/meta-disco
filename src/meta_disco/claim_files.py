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

**What a run does with these today.** It discovers them and reports each one's
source, version, catalog and age — ``classify_run.run_all_classifications`` calls
:func:`report_claim_files` and never :func:`iter_claims`. No claim reaches
classification, so a run with claim files present writes the same output as one
without. Matching claims to our files is #402; the writer and reader here exist so
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
claim. NDJSON rather than a JSON array because 708,088 files by 5 dimensions by
several sources is millions of claims, and a whole-file ``json.load`` is already the
memory ceiling this corpus keeps hitting (#374); ``anvil_files_metadata.ndjson`` is
the existing precedent. Putting the envelope on line 1 rather than in a sidecar
keeps the claims inseparable from their provenance, and lets a reader have the whole
of it after a single ``readline``::

    {
        "claim_file": {
            "source": {
                "repository": "HPRC Data Explorer",
                "dataset": "R2",
                "table": "sequencing-data",
                "url": "https://…",
            },
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
        "claim": {
            "rule_id": "map_hprc_platform_v1",
            "value": "PACBIO",
            "raw_value": "Revio",
            "column": "platform",
            "source_type": "repository_metadata",
        },
    }

**The envelope names both sides of the join.** A line reads: *this row is about the
row in* ``target`` *whose* ``target_key`` *equals its* ``target_key_value``. The key
*names* live on the envelope because they do not change within a file — every claim
an importer writes is keyed the same way — so only the value is on the line. The
same factoring keeps the source's repository, url and table on the envelope while
``column`` stays per claim, since one table's claims are read from several columns.

**The importer owns the mapping between the two keys** and writes
``target_key_value`` already in the target's value space; where a source's own value
needs transforming to get there, the importer does it. The run performs equality
lookup and nothing else. That is what keeps corpus knowledge out of the importer and
transform logic out of the join — and it is why a source keyed by an ENA run
accession adds no term to the key vocabulary: it maps that accession to
``archive_accession`` itself.

**What a claim line does not carry.** No ``tier``: an imported claim does not compete
on the rule tiers (#391), so a tier on one is a number the importer invents and the
policy discards. No ``join_key`` or ``match_exact``: those are what the join fills in
once a match has actually happened, and a file asserting them would be claiming a
match that has not occurred. No ``reason`` prose: an imported claim cites the
``rule_id`` of the mapping that produced it — including an identity mapping, since
there is no implicit copy — and the text is resolved from that rule, so output stays
readable while the file stays small. The mapping table itself is #395/#399.
"""

import json
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from .models import CLASSIFICATION_FIELDS, ClaimFileEnvelope, ClaimFileSource, ClaimSource, optional_str
from .rule_engine import make_claim

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

# What each side calls the claim it is refusing (`_where`). A writer counts claims,
# because it has no line numbers to give; a reader counts lines, because that is what
# a person opening the file can act on.
_WRITING = "claim"
_READING = "line"

# The three members of a claim line. `_claim_line` writes exactly these, so a file
# carrying anything else beside them was not written by this module. The key names
# are not among them: they are on the envelope, constant for the file.
_LINE_KEYS = frozenset({"field", "target_key_value", "claim"})

# Claim members the join fills in, which a claim file must therefore not carry. A
# producer writing them would be asserting a match that has not happened, and an
# outer key of `file_name` beside an inner `join_key` of `file_md5sum` is two
# contradictory join descriptions in one line (#401).
_POST_JOIN_KEYS = ("join_key", "match_exact")


@dataclass(frozen=True, slots=True)
class ClaimEntry:
    """One line of a claim file: which dimension, which target row, and the claim.

    Reads as: *this row is about the row in the envelope's* ``target`` *whose*
    ``target_key`` *equals* ``target_key_value`` *; here is the claim.*

    ``field`` is one of ``CLASSIFICATION_FIELDS``. ``target_key_value`` is the value
    to match on, already in the target's value space — the importer owns the mapping
    between its own key and the target's, and any transform needed to get there, so
    the run performs equality lookup only. The key *names* are on the envelope,
    because they do not change within a file; only the value varies per claim.

    ``claim`` is a claim dict as ``rule_engine.make_claim`` builds it, carrying the
    :class:`ClaimSource` it came from; :func:`write_claim_file` factors that source
    into the envelope and :func:`iter_claims` puts it back, so a caller on either
    side always holds a whole claim.

    ``slots=True`` because :func:`iter_claims` builds one of these per claim: a few
    million per source, each of which would otherwise carry its own ``__dict__``.
    """

    field: str
    target_key_value: str
    claim: dict


@dataclass(frozen=True)
class ClaimFileStatus:
    """One claim file as a run sees it: its provenance, or why it could not be read.

    Exactly one of the two is set. ``error`` is the envelope's own parse or IO
    failure, held rather than raised so that one unreadable file does not hide the
    provenance of the ones behind it in the report.

    A run does not judge a claim file beyond this. Whether the claims still describe
    the catalog being classified is left to the importer, which compares its own
    file's ``target.version`` against the configured catalog when deciding to re-fetch,
    and to the boundary where an enhancement is offered back to a catalog — which
    requires the run's output to record which catalog it enhances, and that is #404,
    not something this PR added. Nothing enforces it today.
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
    and compared against per claim — it is constant for the file. The envelope was
    checked when it was built (``ClaimFileEnvelope.__post_init__``).

    ``path`` must end in ``.ndjson``, because that is what :func:`discover` looks for.
    Writing ``catalog.json`` otherwise succeeds, returns a claim count, and is then
    invisible to every run — an importer's one-character mistake becoming a silent
    no-op with a success return, which is the one failure mode an import must not
    have (#401 review).
    """
    if path.suffix != CLAIM_FILE_GLOB.lstrip("*"):
        raise ValueError(
            f"{path.name}: a claim file must be named {CLAIM_FILE_GLOB} — "
            f"a {path.suffix or 'suffixless'} file is written but never discovered"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    name = path.name
    # The source a claim in this file must have come from, by its column, as both the
    # record and the dict it serializes to. The envelope's source is constant for the
    # file and one table's claims are read from a handful of columns, so this is a few
    # objects per file rather than two per claim. Holding the dict too is what lets
    # the check below be a dict compare rather than a parse: `ClaimSource.from_dict`
    # per claim was the single largest cost in the write loop. (A plain dict closed
    # over here rather than `lru_cache` on a method, which would keep the envelope
    # alive for the process.)
    by_column: dict[str | None, tuple[ClaimSource, dict]] = {}

    def expected_source(column: str | None) -> tuple[ClaimSource, dict]:
        if (known := by_column.get(column)) is None:
            source = envelope.source.as_claim_source(column)
            known = by_column[column] = (source, source.to_dict())
        return known

    written = 0
    try:
        with tmp.open("w", encoding="utf-8", buffering=_WRITE_BUFFER_BYTES) as f:
            f.write(_encode({ENVELOPE_KEY: envelope.to_dict()}))
            f.write("\n")
            for entry in entries:
                written += 1
                f.write(_encode(_claim_line(expected_source, entry, name, written)))
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
    with path.open("rb") as f:
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

    The file is opened as bytes and each line decoded here, rather than opened as
    text. A text handle decodes inside its own iterator, so one corrupt byte in a
    later record raised ``UnicodeDecodeError`` from the ``for`` statement — a codec
    traceback with a byte offset, escaping the promise above that every bad line is
    named by file and line number (#401 review).
    """
    name = path.name
    with path.open("rb") as f:
        envelope_source = _read_envelope(path, f).source
        for n, raw in enumerate(f, start=2):
            line = _decode(raw, _where(name, _READING, n))
            if line.isspace():
                continue
            yield _entry_from_line(name, n, line, envelope_source)


def _decode(raw: bytes, where: str) -> str:
    """One line of a claim file as text, or a ``ValueError`` naming it.

    A claim file is written by another process, so a truncated write or a source that
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
    """One report line for one claim file: both sides of its join, and its age.

    Reads as *what it came from* → *what it is about*, because a person checking a
    run's claim files wants to see which corpus each one will attach to as much as
    where it was fetched from.
    """
    name = status.path.relative_to(root)
    if status.envelope is None:
        return f"UNREADABLE {name} — {status.error}"
    envelope = status.envelope
    return (
        f"{name} — {_join_side(envelope.source.to_dict(), envelope.source_key)}"
        f" -> {_join_side(envelope.target.to_dict(), envelope.target_key)},"
        f" version {envelope.source_version},"
        f" fetched {envelope.fetched_at.isoformat()} ({_age_phrase(envelope.fetched_at, now)})"
    )


def _join_side(members: dict, key: str) -> str:
    """One side of the join as ``a/b/c[key]``, skipping the levels it does not have.

    Both sides are flat records of optional strings, so one renderer serves them —
    ``HPRC Data Explorer/R2/sequencing-data[filename]`` and
    ``anvil/AnVIL_HPRC_R2[file_name]``. ``url`` is dropped: it is provenance a reader
    can go and look at, not something to carry across every line of a report.
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


def _claim_line(
    expected_source: Callable[[str | None], tuple[ClaimSource, dict]], entry: ClaimEntry, name: str, n: int
) -> dict:
    """Serialize one entry, factoring its claim's source into the file's.

    The claim keeps every key ``make_claim`` gave it except ``source``, which is
    replaced by that source's ``column`` alone — the only member that varies within
    one file, and omitted too when the source has none. Writing the repository, url
    and table on every line would be the envelope's content repeated a few million
    times.

    That factoring is also a check: a claim whose source is not the source the
    envelope names does not belong in this file, and saying so here is cheaper than a
    reader discovering that every claim it rehydrated was attributed to the wrong
    table. The comparison goes through
    :meth:`ClaimFileSource.as_claim_source`, so the writer's notion of "the same
    source" is the reader's own.

    The claim is put through ``make_claim`` before it is written, exactly as
    :func:`_entry_from_line` does on the way back in. An importer can hand-build a
    ``ClaimEntry``, and a claim citing no mapping rule, or carrying a tier it may not
    have, would otherwise write cleanly and be refused by the reader — the writer
    producing a file its own reader will not take, which is the failure this contract
    exists to prevent.

    ``name`` and ``n`` locate the entry for a refusal and are formatted into one only
    when there is one (:func:`_where`) — this runs a few million times per source, and
    a label built per claim is a string nothing reads.
    """
    where = _where(name, _WRITING, n)
    _check_entry(where, entry.field, entry.target_key_value, entry.claim)
    claim = dict(entry.claim)
    source = claim.pop("source", None)
    if not isinstance(source, dict):
        raise ValueError(f"{where}: carries no source — a claim file holds claims from an external source")
    # A dict compare against the envelope's own serialization, not a parse. The
    # claim's source came from `make_claim`, so it is already a `ClaimSource.to_dict`
    # — equal to the expected one exactly when it is the same source. Parsing it back
    # into a record first cost more than everything else on this line put together,
    # to learn the same thing. `column` is checked because it is the one member that
    # is this line's rather than the envelope's.
    column = optional_str(source.get("column"), "source column", where)
    expected, expected_dict = expected_source(column)
    if source != expected_dict:
        raise ValueError(f"{where}: comes from {source}, but this file's envelope names {expected_dict}")
    # What is written is the *rebuilt* claim, not the caller's dict. `make_claim`
    # omits a key whose argument is None, so a hand-built claim carrying an explicit
    # `"raw_value": None` would otherwise be written with that key and read back
    # without it — validated on the way out and still not a round trip.
    written = _rebuild_claim(claim, expected, where)
    written.pop("source", None)
    if column is not None:
        written["column"] = column
    return {"field": entry.field, "target_key_value": entry.target_key_value, "claim": written}


def _rebuild_claim(claim: dict, source: ClaimSource, where: str) -> dict:
    """Put a claim dict back through ``make_claim``, or raise naming ``where``.

    The one place a claim that did not come from ``make_claim`` in this process is
    made to satisfy it, used by both directions: the writer calls it so it cannot
    publish a claim its reader refuses, the reader so a claim off disk is
    reconstructed rather than trusted. ``claim`` is the claim without its ``source``,
    which is passed separately because a claim file factors it into the envelope.

    ``claim_state`` is the key ``make_claim`` writes; ``state`` is the argument it
    takes, so the one rename happens here. Any other unexpected key reaches
    ``make_claim`` as an unknown keyword and is refused as a malformed claim, which is
    what it is.
    """
    kwargs = dict(claim)
    state = kwargs.pop("claim_state", None)
    try:
        return make_claim(**kwargs, state=state, source=source)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{where}: not a valid claim: {exc}") from None


def _entry_from_line(name: str, n: int, line: str, envelope_source: ClaimFileSource) -> ClaimEntry:
    """Parse one claim line, rebuilding its claim through ``make_claim``.

    ``envelope_source`` is the file's source, read once by :func:`iter_claims`. The
    claim comes back whole — that source as a :class:`ClaimSource`, with this line's
    ``column`` — so a consumer reads the same claim the importer built and never has
    to consult the envelope itself.

    **The claim is reconstructed, not trusted.** A claim file is bytes on disk written
    by an out-of-band process, and the record that comes off it goes on to
    ``evaluate_claims``; passing the parsed dict straight through would make this the
    one producer in the codebase that bypasses ``make_claim``, against CLAUDE.md's
    "one claim record, any source". A claim with no ``tier`` would then reach
    resolution and take the tier-0 default that #150/#151 exist to prevent.
    Rebuilding costs a ``make_claim`` per claim on read and buys every invariant it
    enforces: exactly one of value/status/state, a tier iff the claim competes and an
    integer where there is one, known status/state/source_type/join_key, string-typed
    free text, a producer handle (#401 review).

    **What it does not buy is a trustworthy tier.** ``make_claim`` checks that a tier
    is an integer, not that it is one of the tiers this engine has, so a claim file
    can name ``999`` and — on the day imported claims reach ``evaluate_claims`` —
    outrank every rule and content claim by being the unique highest. That is not
    guarded here on purpose. Where an imported claim ranks is epic #391's question,
    already answered on measured evidence: imports are *not* tier participants, and
    the 12 known disagreements on ``AnVIL_HPRC_R2`` are why — they sit at rule tiers
    1-2, so admitting imports at ``CONTENT_TIER`` would have produced 1 conflict and
    11 silent wrong overrides. Under that policy an imported claim's tier is a number
    nothing reads. Clamping it to a range here would encode a *reversible* policy
    decision as an invariant of the record, in the one place that cannot know what
    the allowed answer is; the guard belongs with the policy, in #396, which is also
    what decides whether the number means anything at all. Nothing imported reaches
    resolution until the join lands (#402).

    A line that carries its own ``source`` is refused rather than silently
    overwritten. The envelope names the file's source; a line may add a ``column`` to
    it and nothing else. The write side already refuses a claim whose source is not
    the envelope's, and a reader that quietly re-attributed one would undo that check
    for exactly the files it cannot vouch for.

    ``name`` is the file's name, hoisted out of the read loop by :func:`iter_claims`,
    and is formatted with ``n`` into a label only on a refusal — see
    :func:`_claim_line` for why.
    """
    where = _where(name, _READING, n)
    try:
        entry = json.loads(line)
        field, target_key_value, claim = (entry["field"], entry["target_key_value"], entry["claim"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"{where}: not a claim: {exc!r}") from None
    # A member the line does not have is refused, not dropped. `make_claim` already
    # refuses an unknown key *inside* the claim, and a reader that silently discarded
    # one beside it would normalize a malformed file into an apparently valid claim
    # (#401 review).
    if extra := sorted(set(entry) - _LINE_KEYS):
        raise ValueError(f"{where}: line has unknown member(s) {extra} (expected {sorted(_LINE_KEYS)})")
    _check_entry(where, field, target_key_value, claim)
    if "source" in claim:
        raise ValueError(
            f"{where}: claim carries its own source {claim['source']!r} — "
            "the envelope names this file's source, and a line may only add a column to it"
        )
    body = dict(claim)
    # The column is checked here rather than trusted: `"column": 7` would otherwise
    # ride through as a claim's source member. `as_claim_source` then supplies the
    # three facts the envelope holds.
    source = envelope_source.as_claim_source(optional_str(body.pop("column", None), "source column", where))
    return ClaimEntry(field=field, target_key_value=target_key_value, claim=_rebuild_claim(body, source, where))


def _where(name: str, unit: str, n: int) -> str:
    """Name the claim being refused: ``…ndjson claim 3`` writing, ``…ndjson line 4`` reading.

    Called only from a raise. The two sides count differently on purpose — a writer
    has no line numbers yet and a reader's ``n`` includes the envelope — so the unit
    travels with the count rather than being inferred from it.
    """
    return f"{name} {unit} {n}"


def _check_entry(where: str, field: Any, target_key_value: Any, claim: Any) -> None:
    """Check the three members of a claim line, in whichever direction it is crossing.

    One definition of the line's shape for the writer and the reader both, so the two
    cannot drift into accepting different files. ``where`` is what the caller calls
    this line — ``…ndjson claim 3`` writing, ``…ndjson line 4`` reading.

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
            f"{where}: target_key_value is {target_key_value!r} — a claim with nothing to match on can attach to no row"
        )
    if not isinstance(claim, dict):
        raise ValueError(f"{where}: claim is {type(claim).__name__}, not an object")
    # Membership first, the sorted list only inside the raise: this runs on both
    # paths, a few million times each, and every non-error call was allocating a
    # generator and an empty list.
    if "join_key" in claim or "match_exact" in claim:
        raise ValueError(
            f"{where}: claim carries {sorted(k for k in _POST_JOIN_KEYS if k in claim)}, "
            "which the join fills in — a claim file records the key to match on, "
            "not a match that has happened"
        )


def _read_envelope(path: Path, f: BinaryIO) -> ClaimFileEnvelope:
    """Consume line 1 of an open claim file as its envelope.

    The one place a claim file's first line is turned into provenance, shared by
    :func:`read_envelope` (which wants only that) and :func:`iter_claims` (which
    reads on from there), so a file with no first line is refused in the same words
    either way. ``f`` is a byte handle for the reason :func:`iter_claims` opens one:
    a decode failure is reported as a malformed line, not raised from inside a file
    iterator.
    """
    first = _decode(f.readline(), f"{path.name} line 1")
    if not first.strip():
        raise ValueError(f"{path.name}: line 1 must be the {ENVELOPE_KEY} envelope, and this file starts empty")
    return _envelope_from_line(path, first)


def _envelope_from_line(path: Path, line: str) -> ClaimFileEnvelope:
    """Parse line 1 as an envelope, or raise naming the file.

    This owns only the file layout — unwrap the JSON, find the ``claim_file`` key —
    and hands the block to :meth:`ClaimFileEnvelope.from_dict`, which owns what an
    envelope's members must be. The same rules then run when an importer *builds* an
    envelope (``ClaimFileEnvelope.__post_init__``), so a writer cannot produce a file
    this reader will refuse (#401 review).

    The line is closed as well as the envelope inside it: ``claim_file`` must be its
    only key. Extracting the block and ignoring its siblings would let
    ``{"claim_file": …, "unexpected": 1}`` through while an unknown member *within*
    the envelope is refused — the same malformed provenance, discarded rather than
    reported, depending only on which side of one brace it sat (#401 review).
    """
    where = f"{path.name} line 1"
    try:
        wrapper = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{where}: not a {ENVELOPE_KEY} envelope: {exc!r}") from None
    if not isinstance(wrapper, dict) or set(wrapper) != {ENVELOPE_KEY}:
        raise ValueError(
            f"{where}: line 1 must be an object whose only key is {ENVELOPE_KEY!r}, "
            f"and this one is {sorted(wrapper) if isinstance(wrapper, dict) else type(wrapper).__name__}"
        )
    return ClaimFileEnvelope.from_dict(wrapper[ENVELOPE_KEY], where)
