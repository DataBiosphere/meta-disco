"""Data models for file classification."""

from dataclasses import MISSING, dataclass, field, fields
from datetime import datetime
from functools import cache
from typing import Any

from .file_name import FileName

# Classification status constants. NOT_APPLICABLE / NOT_CLASSIFIED are today
# smuggled into a field's `value`; the sentinel→status migration (epic #116) is
# splitting them into a dedicated `status` field. CLASSIFIED is the status when a
# real value was determined.
CLASSIFIED = "classified"
NOT_APPLICABLE = "not_applicable"
NOT_CLASSIFIED = "not_classified"
# Top-tier claims disagreed (issue #88). Today the rule engine records this as an
# evidence marker under NOT_CLASSIFIED; the constant exists so consumers that
# re-emit a parent's status can carry it once it becomes a status of its own.
CONFLICT = "conflict"

# What field_label emits in place of a value. It renders a classified field as its
# value and any other field as its status, so a label outside this set is a real
# value. Defined here, beside the constants that compose it, so a consumer asking
# "did this label carry a value?" (corpus_diff) tracks the status vocabulary
# instead of re-spelling it — a status added above and not here would otherwise be
# silently counted as a value.
STATUS_LABELS = frozenset({NOT_APPLICABLE, NOT_CLASSIFIED, CONFLICT})

# Claim states (issue #392): why a claim that consulted a source produced no
# vocabulary value. These are NOT statuses — a claim in one of these states
# declares nothing, so it never competes in resolution and can never become a
# dimension's status.
UNMAPPED = "unmapped"
NO_VOCABULARY_TERM = "no_vocabulary_term"
DECLINED = "declined"
CLAIM_STATES = frozenset({UNMAPPED, NO_VOCABULARY_TERM, DECLINED})

# Kinds of source behind a claim (issue #392). Deliberately not derived from a
# claim's tier: SOURCE_CONTIG_DETECTION and SOURCE_CONTENT_READ share
# CONTENT_TIER, and SOURCE_SIGNAL_INFERENCE fires at a rule tier without being a
# rule.
SOURCE_FILENAME_RULE = "filename_rule"
SOURCE_HEADER_RULE = "header_rule"
SOURCE_CONTIG_DETECTION = "contig_detection"
SOURCE_CONTENT_READ = "content_read"
SOURCE_SIGNAL_INFERENCE = "signal_inference"
SOURCE_DERIVATION_INHERITANCE = "derivation_inheritance"
SOURCE_EXTERNAL_GROUND_TRUTH = "external_ground_truth"
SOURCE_REPOSITORY_METADATA = "repository_metadata"
SOURCE_WRANGLER_ANNOTATION = "wrangler_annotation"
SOURCE_TYPES = frozenset(
    {
        SOURCE_FILENAME_RULE,
        SOURCE_HEADER_RULE,
        SOURCE_CONTIG_DETECTION,
        SOURCE_CONTENT_READ,
        SOURCE_SIGNAL_INFERENCE,
        SOURCE_DERIVATION_INHERITANCE,
        SOURCE_EXTERNAL_GROUND_TRUTH,
        SOURCE_REPOSITORY_METADATA,
        SOURCE_WRANGLER_ANNOTATION,
    }
)

# Keys a claim may be attached to a target row by (#392, extended in #401). One
# vocabulary for two positions: a claim file's envelope declares which of these it is
# keyed by (`target_key`), and a claim records which one actually attached it
# (`join_key`) once the join has run.
#
# These are keys of the *target*, not names a source publishes. A source keyed by an
# ENA run accession does not add a term here — its importer maps that accession to
# one of these and writes the value in the target's space, which is what keeps corpus
# knowledge in the importer and transform logic out of the join.
#
# Measured on the AnVIL corpus (708,088 records) — the three that are both wholly
# present and wholly unique are `file_id`, `entry_id` and `drs_uri`. `file_md5sum` is
# unique on all but 1.7% of rows and absent on 9,059. `file_name` is absent on 37%
# and non-unique on 69%, so it is usable only inside a dataset scope (2 collisions in
# 16,271 within AnVIL_HPRC_R2, against 99.3% within ANVIL_1000G_PRIMED_data_model).
JOIN_KEY_FILE_PATH = "file_path"
JOIN_KEY_FILE_MD5SUM = "file_md5sum"
JOIN_KEY_DRS_URI = "drs_uri"
JOIN_KEY_FILE_NAME = "file_name"
JOIN_KEY_FILE_ID = "file_id"
JOIN_KEY_ENTRY_ID = "entry_id"
# Not a field of the input record but a fact classification *derives* — read from a
# fastq's read headers. ENA run accessions appear in no input file name at all, so a
# claim from ENA or SRA can only be attached by this, which is why the join runs
# after inference rather than over the input corpus.
JOIN_KEY_ARCHIVE_ACCESSION = "archive_accession"
JOIN_KEYS = frozenset(
    {
        JOIN_KEY_FILE_PATH,
        JOIN_KEY_FILE_MD5SUM,
        JOIN_KEY_DRS_URI,
        JOIN_KEY_FILE_NAME,
        JOIN_KEY_FILE_ID,
        JOIN_KEY_ENTRY_ID,
        JOIN_KEY_ARCHIVE_ACCESSION,
    }
)

# The three vocabularies above are validated at runtime against these in-code
# frozensets — the idiom STATUS_LABELS and reference_builds' NAME_SOURCE_* already
# follow — and pinned to their schema enums by test_rule_vocabulary, which is
# where the schema is read. Keeping the LinkML load out of the classification path
# matters: make_claim runs a few million times per corpus, and schema_vocab was
# test- and validation-only before this.

# The five classification dimension fields, in canonical output order. Single
# source of truth for the field set — the rule engine, rule_loader's 'then' key
# validation, and schema_vocab's dimensions all derive from this.
CLASSIFICATION_FIELDS = (
    "data_modality",
    "data_type",
    "platform",
    "reference_assembly",
    "assay_type",
)


def _field_entry(record: dict, field_name: str):
    """Return the per-field classification entry/value from a record, or None.

    Normalizes the layouts classification records appear in:
    - per-field:  record["classifications"][field] -> {"value", ...}
    - nested:     record[field] -> {"value", ...}
    - flat:       record[field] -> value
    Returns whatever is found at the field (a dict entry, a scalar, or None).

    Pipeline output now guarantees the per-field layout (``OutputRecord``, #204); the
    nested/flat fallbacks remain for the other producers this reader serves (e.g. the
    label dicts built in ``classify_index_files``).
    """
    cls = record.get("classifications")
    if isinstance(cls, dict) and field_name in cls:
        return cls[field_name]
    return record.get(field_name)


def _entry_value(entry):
    """Resolved value from a per-field entry (a dict ``{"value": ...}`` or scalar)."""
    return entry.get("value") if isinstance(entry, dict) else entry


def status_for_value(value) -> str:
    """Derive a field's status from its (pre-split) value.

    The one place that maps a sentinel-carrying ``value`` to a status string:
    ``not_applicable`` → NOT_APPLICABLE, ``None``/``not_classified`` →
    NOT_CLASSIFIED, any real value → CLASSIFIED. Used by the read side
    (``_entry_status``) and by ``build_field_entry`` when a producer carries the
    sentinel in ``value`` and no explicit status is given, so reader and producers
    stay in lockstep as epic #116 moves sentinels out of ``value``.
    """
    if value == NOT_APPLICABLE:
        return NOT_APPLICABLE
    if value is None or value == NOT_CLASSIFIED:
        return NOT_CLASSIFIED
    return CLASSIFIED


def _assert_coherent(value, status) -> None:
    """Raise ValueError if (value, status) contradict epic #116's Stage 3 contract.

    The single definition of entry coherence: a CLASSIFIED field must carry a real
    value (not None, not a sentinel string), and a non-CLASSIFIED status must not
    carry one. Enforced on both sides — when building output (``build_field_entry``)
    and when reading an explicit status (``_entry_status``) — so a sentinel can
    never be smuggled into ``value`` under a classified status, or a real value be
    dropped under a non-classified status, from either direction.
    """
    value_is_real = status_for_value(value) == CLASSIFIED
    if status == CLASSIFIED and not value_is_real:
        raise ValueError(f"incoherent entry: CLASSIFIED status requires a real value, got {value!r}")
    if status != CLASSIFIED and value_is_real:
        raise ValueError(f"incoherent entry: {status!r} status must not carry a real value, got {value!r}")


# The keys every per-field entry carries. Anything else on an entry is *detail*
# (``build_field_entry``'s ``detail`` argument), and ``field_detail`` reads it back.
ENTRY_KEYS = frozenset({"value", "status", "evidence"})


def build_field_entry(value, status=None, evidence=None, detail=None) -> dict:
    """Build a serialized per-field classification entry.

    The single place that assembles the ``{value, status, evidence}`` output shape
    and enforces epic #116's Stage 3 invariant: sentinels live only in ``status``
    and ``value`` is ``None`` unless the field is CLASSIFIED. Every producer
    (rule_engine's ``to_output_dict``, the index-propagation script, the
    header_classifier empty-input fallback) goes through here, so the invariant is
    defined once. When an explicit ``status`` is passed it must be coherent with
    ``value``: a CLASSIFIED status requires a real value, and a non-CLASSIFIED
    status must not carry one (a sentinel or ``None`` is fine) — either mismatch
    raises ValueError rather than smuggling a sentinel into ``value`` or silently
    dropping a real value. So the entry is always coherent and the read-side guard
    (``_entry_status``) is never handed a contradictory shape.

    ``status`` defaults to ``status_for_value(value)`` for producers that still
    carry the sentinel in ``value``; pass it explicitly when the status is known
    directly. The derived path is coherent by construction and never raises.

    ``detail`` carries extra, dimension-specific facts *about* the value — the
    first is ``reference_assembly``'s resolved build (#340), and #341/#342 will
    add more. Its keys are merged into the entry, and it is omitted entirely when
    absent or empty, so a dimension with no such facts serializes byte-identically
    to before this argument existed. Detail is never a claim: it carries no tier
    and cannot change which value won.

    This function stays dimension-agnostic on purpose — it is the single place the
    entry shape is assembled, so it must not learn any dimension by name. Which
    dimension gets which detail is decided by whichever classifier observed it.
    """
    if status is None:
        status = status_for_value(value)
    _assert_coherent(value, status)
    entry = {
        "value": value if status == CLASSIFIED else None,
        "status": status,
        "evidence": evidence if evidence is not None else [],
    }
    if detail:
        clashing = set(detail) & set(entry)
        if clashing:
            raise ValueError(f"detail may not shadow the entry's own keys: {sorted(clashing)}")
        entry.update(detail)
    return entry


def all_not_classified(evidence: list[dict]) -> dict:
    """Build a classifications dict marking every dimension ``not_classified``.

    The shared shape for a record we assert *nothing* about — a failed input
    contract (``metadata_schema.validation_failed_classifications``) or an
    unreadable fetch (``header_classifier.classify_without_content``). Each of the
    five dimensions gets ``not_classified`` status and a *fresh copy* of
    ``evidence`` (its cause). The per-field copy is deliberate: one shared list
    aliased across five fields would let a later in-place edit of one mutate all.
    """
    return {
        fld: build_field_entry(None, status=NOT_CLASSIFIED, evidence=[dict(e) for e in evidence])
        for fld in CLASSIFICATION_FIELDS
    }


def _entry_status(entry) -> str:
    """Status from a per-field entry: explicit ``status`` if set, else derived.

    When the entry carries an explicit ``status``, it is validated against ``value``
    via ``_assert_coherent`` — an incoherent pairing (CLASSIFIED without a real
    value, or a non-CLASSIFIED status carrying a real value) raises ValueError.
    Epic #116's Stage 3 invariant is that sentinels live only in ``status``; this
    is the loud-failure counterpart to the declined field_label None-guard (#129):
    reject the self-contradictory shape rather than fabricating a bucket label from
    it. Both field_status and field_label route through here, so both fail loudly
    instead of silently mis-reading a smuggled sentinel as a classified value.
    """
    if isinstance(entry, dict):
        status = entry.get("status")
        if status is not None:
            _assert_coherent(entry.get("value"), status)
            return status
        value = entry.get("value")
    else:
        value = entry
    return status_for_value(value)


def field_value(record: dict, field_name: str):
    """Resolved value of a classification field, normalizing record layout.

    Use this for *value* reads. For "is this field applicable / classified?"
    questions use field_status, and for histogram / aggregation bucket keys that
    should fold unclassified into a sentinel bucket use field_label — so that when
    the sentinel→status migration moves sentinels out of `value` (epic #116),
    value-reads, status-checks, and bucket labels stay correctly separated and
    call sites do not need to change again.
    """
    return _entry_value(_field_entry(record, field_name))


def field_status(record: dict, field_name: str) -> str:
    """Status of a classification field.

    Returns an explicit non-None ``status`` from the field entry verbatim when
    present (the shape the migration is moving toward — this may be values beyond
    the three below, e.g. ``conflict`` in later stages). Otherwise derives the
    status from the current sentinel-in-``value`` convention, yielding one of
    CLASSIFIED / NOT_APPLICABLE / NOT_CLASSIFIED; a missing/None value reads as
    NOT_CLASSIFIED.
    """
    return _entry_status(_field_entry(record, field_name))


def field_detail(record: dict, field_name: str) -> dict:
    """The dimension-specific detail on a field entry: every key beyond ``ENTRY_KEYS``.

    The read-side mirror of ``build_field_entry``'s ``detail`` argument, so a
    consumer that rebuilds an entry (the index-propagation script) can carry the
    detail through without naming any dimension or key. Empty when the entry
    carries none, or is not a dict (the flat layout has nowhere to put detail).
    """
    entry = _field_entry(record, field_name)
    if not isinstance(entry, dict):
        return {}
    return {key: value for key, value in entry.items() if key not in ENTRY_KEYS}


def field_evidence(record: dict, field_name: str) -> list:
    """The evidence list on a field entry; empty when there is none.

    Completes the ``field_value`` / ``field_status`` / ``field_detail`` family so a
    consumer reading *why* a field says what it does goes through the same layout
    normalization as one reading the value (``_field_entry``), rather than reaching
    into ``record["classifications"][field]["evidence"]`` itself. Returns ``[]`` for an
    entry that is not a dict (the flat layout has nowhere to put evidence) and for one
    whose ``evidence`` is missing or not a list.
    """
    entry = _field_entry(record, field_name)
    if not isinstance(entry, dict):
        return []
    evidence = entry.get("evidence")
    return evidence if isinstance(evidence, list) else []


def field_label(record: dict, field_name: str) -> str | None:
    """Display label for a field: its value when classified, else its status.

    Reproduces the pre-split convention where ``value`` held either a real value or
    a sentinel — for histograms / aggregations that bucket by that combined label.
    Returns the field_value when status is CLASSIFIED (which may be None only in the
    future explicit-status shape), otherwise the status string. Survives the
    sentinel→status split (epic #116): the not_applicable / not_classified buckets
    persist via the status once sentinels move out of ``value`` (a non-sentinel
    status such as ``conflict`` would likewise surface here).
    """
    entry = _field_entry(record, field_name)
    status = _entry_status(entry)
    return _entry_value(entry) if status == CLASSIFIED else status


# Length of an ISO 8601 calendar date, `YYYY-MM-DD`. A datetime string is this plus a
# separator and a time, so the date alone is exactly this long.
_ISO_DATE_CHARS = 10


def required_str(value: object, label: str, where: str) -> str:
    """Return ``value`` as a non-empty string, or raise naming ``label`` and ``where``.

    One definition of "this member is a usable string" for the claim-file records,
    applied on both sides of the file: ``ClaimFileEnvelope.__post_init__`` uses it on
    an envelope being built and the ``from_dict`` pair on one being read, so a writer
    cannot produce a file its own reader will refuse (#401 review).

    A required member is one ``to_dict`` would always have written, so its absence is
    a malformed record. ``None`` is rejected here rather than by a key check: an
    explicit ``"name": null`` is a present key, and ``to_dict`` omits null members
    entirely, so both arrive as an absent value that a key check would read
    differently from each other. The empty string is refused too — a version or a
    name that identifies nothing.

    ``where`` locates the fault — a file and line for a reader, the constructing call
    for a writer — and prefixes every message.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: {label} is {value!r}, not a non-empty string")
    return value


def optional_str(value: object, label: str, where: str) -> str | None:
    """Return a member a record may not have: None when absent, checked when present.

    None is what :meth:`ClaimSource.to_dict` meant by omitting the key, so it passes.
    Anything else must satisfy :func:`required_str` — a present member that is not a
    non-empty string is a mis-serialized record, not one to interpret.
    """
    return None if value is None else required_str(value, label, where)


# Missing-key sentinel for `_flat_from_dict`. `None` cannot serve: `_flat_to_dict`
# omits a null member, so an absent key and an explicit `"dataset": null` both read
# as None through `dict.get`, and the second is a record we did not write.
_ABSENT = object()


def require_join_key(value: object, label: str, where: str) -> str:
    """Return ``value`` as a key of the target, or raise naming ``label`` and ``where``.

    One refusal for one vocabulary, used in both positions it appears in: a claim
    file's envelope declaring which key it is keyed by (``target_key``), and a claim
    recording which one attached it (``join_key``) once the join has run. Stating it
    twice would mean two wordings for the same fault and two places to update when
    the vocabulary moves — ``archive_accession`` is the live example, a derived fact
    rather than a record field.
    """
    if not isinstance(value, str) or value not in JOIN_KEYS:
        raise ValueError(f"{where}: {label} {value!r} is not a key of the target (expected one of {sorted(JOIN_KEYS)})")
    return value


def _parse_fetched_at(value: object, where: str) -> datetime:
    """Parse a claim file's ``fetched_at``, or raise naming ``where``.

    A trailing ``Z`` is normalized to ``+00:00`` first. ``datetime.fromisoformat``
    rejects ``Z`` on Python 3.10 — this project's floor and what CI runs — while
    accepting it from 3.11, and the importers coming in #369/#394 read web APIs that
    emit it almost universally. Without this a claim file written on a 3.11 machine
    parses there and fails on CI, which is a property of the interpreter rather than
    of the file.

    A time of day is required. ``fromisoformat`` accepts a bare ``2026-09-01`` and
    silently returns midnight, so a date-only value would read back as a fetch
    claiming to have happened at 00:00:00 — a precision the file never stated, and
    one that makes two imports on the same day indistinguishable, which is the case
    the age report exists for. The check is on the string rather than the parsed
    value, because midnight is a real time a genuine fetch can have: an ISO 8601 date
    is its first ten characters, so anything longer carries a separator and a time,
    and ``isoformat()`` on a datetime always writes one.
    """
    if not isinstance(value, str):
        raise ValueError(f"{where}: envelope fetched_at is {value!r}, not an ISO 8601 string")
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise ValueError(f"{where}: envelope fetched_at {value!r} is not an ISO 8601 datetime") from None
    if len(value) <= _ISO_DATE_CHARS:
        raise ValueError(
            f"{where}: envelope fetched_at {value!r} is a date with no time of day — "
            "record when the fetch happened, not only the day it happened on"
        )
    return parsed


def _flat_to_dict(record) -> dict:
    """Serialize a flat dataclass of optional strings, dropping the absent ones.

    Shared by the claim-file records (``ClaimSource``, ``ClaimFileSource``,
    ``ClaimTarget``). Keys come from ``fields()`` rather than being listed, so a
    member added to one of those dataclasses is emitted rather than silently dropped
    from every claim file — the same reason ``ExcludedFile.to_dict`` derives its keys.

    Null members are omitted rather than written as explicit nulls: these records
    either have a member or do not, and there is no "we looked and found nothing"
    state for a reader to tell apart from an absent one. (``ReferenceBuild.to_dict``
    keeps its nulls for exactly that reason, which is why it is not one of these.)
    """
    return {f.name: v for f in fields(record) if (v := getattr(record, f.name)) is not None}


@cache
def _flat_plan(cls) -> tuple[frozenset, tuple, tuple]:
    """The per-class reading plan for :func:`_flat_from_dict`, computed once.

    ``fields()`` walks the dataclass on every call and is not free; the members and
    which checker each one gets cannot change for a class, so they are derived once
    and cached. This runs per claim on the write path — a few million per source —
    where rebuilding the name set was measurably the largest cost in the line.

    Returns the known names, those names sorted for an error message, and
    ``(name, checker)`` pairs: a member with no dataclass default is required.
    """
    members = tuple((f.name, required_str if f.default is MISSING else optional_str) for f in fields(cls))
    names = frozenset(name for name, _ in members)
    return names, tuple(sorted(names)), members


def _reject_unknown(block: dict, known: frozenset, expected: tuple, where: str, label: str) -> None:
    """Refuse a member the record does not have, rather than ignoring it.

    The schema validates these records ``closed=True``, so a reader that quietly
    dropped an unknown key would accept documents the schema rejects — the two must
    refuse the same files (#401 review). Shared by the flat records and by
    ``ClaimFileEnvelope``, so one refusal is worded one way.
    """
    if extra := sorted(set(block) - known):
        raise ValueError(f"{where}: {label} has unknown member(s) {extra} (expected {list(expected)})")


def _flat_from_dict(cls, block: object, where: str, label: str):
    """Rebuild one of those records from what :func:`_flat_to_dict` wrote.

    The inverse, and derived from ``fields()`` for the same reason. Every member is
    checked: a required one (no dataclass default) must be a non-empty string, an
    optional one must be absent or a non-empty string.

    An explicit ``null`` is refused rather than read as absent. ``_flat_to_dict``
    omits nulls, so a record we wrote never contains one, and a file that does was
    not written by us — accepting it would silently normalize a shape the schema
    rejects. Distinguishing the two needs a sentinel, because ``dict.get`` returns
    ``None`` for both an absent key and a present null.
    """
    if not isinstance(block, dict):
        raise ValueError(f"{where}: {label} is {type(block).__name__}, not an object")
    known, expected, members = _flat_plan(cls)
    _reject_unknown(block, known, expected, where, label)
    # Values are only ever `str | None` to a type checker — `required_str` raises
    # rather than returning None, but that is not visible through the splat.
    values: dict[str, Any] = {}
    for name, checker in members:
        present = block.get(name, _ABSENT)
        if present is None:
            raise ValueError(f"{where}: {label} {name} is an explicit null — an absent member is omitted, not nulled")
        values[name] = checker(None if present is _ABSENT else present, f"{label} {name}", where)
    return cls(**values)


@dataclass(frozen=True)
class ClaimSource:
    """Identity of an external source that produced a claim (issue #392).

    The producer handle for a claim that is not from one of our rules. The schema's
    ``ClaimSource`` class is the definition of what the four members mean and why
    the record is cut at this granularity; this is the Python side of it.

    It answers *who said this*. A claim file's envelope answers a wider question —
    which collection within the source, and which target the claims are about — and
    uses :class:`ClaimFileSource` for it. The two are not duplicates: ``repository``
    fills ``name`` and ``table`` fills ``table`` when a claim is rebuilt from a
    file, while the envelope's ``dataset`` never reaches a claim, because a dataset
    is the scope a claim is matched within rather than part of who produced it.

    Frozen because a source's identity is a fact about where a claim came from,
    not state to edit after the claim is built; that also lets one instance be
    shared by every claim read from the same table without aliasing risk.
    """

    name: str
    url: str | None = None
    table: str | None = None
    column: str | None = None

    def to_dict(self) -> dict:
        """Serialize for output, dropping members the source does not have."""
        return _flat_to_dict(self)

    @classmethod
    def from_dict(cls, block: object, where: str) -> "ClaimSource":
        """Rebuild a source from what :meth:`to_dict` wrote, validating each member."""
        return _flat_from_dict(cls, block, where, "source")


@dataclass(frozen=True)
class ClaimFileSource:
    """Where a whole claim file's claims were read from (issue #401).

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
    dataset: see :class:`ClaimTarget`.

    Distinct from :class:`ClaimSource` rather than reusing it. A claim's source
    carries a ``column``, which belongs to the claim because one table's claims are
    read from several columns; a file's source carries a ``dataset``, which belongs
    to the file because every claim in it came from the same one. Modeling them as
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
    def from_dict(cls, block: object, where: str) -> "ClaimFileSource":
        """Rebuild a file's source from what :meth:`to_dict` wrote."""
        return _flat_from_dict(cls, block, where, "source")

    def as_claim_source(self, column: str | None) -> ClaimSource:
        """The per-claim :class:`ClaimSource` a claim in this file carries.

        The envelope's three facts minus ``dataset``, plus the column this particular
        claim was read from. Called once per claim by the reader, which is why the
        envelope stores these once rather than repeating them a few million times.
        """
        return ClaimSource(name=self.repository, url=self.url, table=self.table, column=column)


@dataclass(frozen=True)
class ClaimTarget:
    """The system a claim file's claims are *about* (issue #401).

    A claim file says "the row in **this** system whose **this key** is **that
    value**". The target names the system, so an importer is not implicitly bound to
    AnVIL, and the file records which system it resolved its keys against.

    ``dataset`` is the scope the join runs within, and it is not decoration: keyed by
    ``file_name`` alone, 69% of the corpus's 708,088 rows carry a non-unique key, and
    20% remain non-unique even scoped by dataset *title* alone — but within
    ``AnVIL_HPRC_R2`` the collision rate is 2 rows in 16,271. A filename join is
    unusable without a dataset scope and reliable with one.

    Null is correct only where the key is unique across the whole target. Measured,
    that is ``file_id``, ``entry_id`` and ``drs_uri`` — each present and unique on
    every one of the 708,088 records. ``file_md5sum`` is *not*: it is non-unique on
    1.7% of rows, because 2,026 md5s are registered in more than one dataset. Leaving
    it unscoped is defensible for a claim about the file's *content*, since those
    rows are the same bytes catalogued twice and a claim about them is true of all of
    them, and wrong for a claim about one catalogued file. Nothing here enforces that
    distinction; making the join record the ambiguity rather than silently fanning
    out is #402's.

    ``version`` is which generation of the target the importer resolved against — an
    AnVIL catalog such as ``anvil15``. Null when the importer did not resolve against
    a particular generation, which is the ordinary case for a source that simply
    publishes names and values (HPRC, ENA) rather than reading our catalog. It is
    provenance for the importer's own next pass, not a gate on the run: see
    ``claim_files`` on why currency is not decidable offline.

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
    def from_dict(cls, block: object, where: str) -> "ClaimTarget":
        """Rebuild a target from what :meth:`to_dict` wrote."""
        return _flat_from_dict(cls, block, where, "target")


@dataclass(frozen=True)
class ClaimFileEnvelope:
    """What a claim file records once, for every claim in it (issue #401).

    An importer runs out of band from classification — when a catalog refreshes,
    with network — and writes a claim file; a run reads it. This is the header of
    that artefact, and it names **both sides of the join**, symmetrically::

        source            source_version      source_key
        target                  target.version    target_key

    A line then reads: *this row is about the row in* ``target`` *whose*
    ``target_key`` *equals its* ``target_key_value`` *; here is the claim.*

    **The key names are here, not on the line.** They do not change within a file —
    every claim an importer writes is keyed the same way — so repeating them on a
    few million lines would be the envelope's content written out again. Only the
    key *value* varies, so only that is on the line. It is the same factoring that
    keeps ``ClaimSource``'s name, url and table here while ``column`` stays per
    claim.

    **The importer owns the mapping between the two keys**, and writes
    ``target_key_value`` already in the target's value space. Where a source's own
    value needs transforming to get there — pulling ``NA12878`` out of a path,
    normalizing an accession — the importer does it. The run performs equality
    lookup and nothing else, which is what keeps corpus knowledge out of the
    importer and transform logic out of the join.

    ``target_key`` names a key of the target system, drawn from its record fields
    *and* from facts meta-disco derives: ENA run accessions appear in no input
    ``file_name`` at all, but ``archive_accession`` is populated on thousands of
    classified fastq records, read from the read headers. So the join runs after
    inference — which is where the pipeline already puts import.

    Frozen because provenance is a fact about where the claims came from, not state
    to edit after they are read. Validated on construction
    (:meth:`__post_init__`) against the same rules :meth:`from_dict` applies on the
    way back in, so a writer cannot produce a file its own reader would refuse —
    an importer would otherwise spend a networked run writing millions of claims
    behind a header that fails at the next classification run, days later and far
    from the cause.
    """

    source: ClaimFileSource
    source_version: str
    source_key: str
    target: ClaimTarget
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

        Runs once per claim file, so its cost is nothing beside the write it precedes.
        """
        where = "claim file envelope"
        if not isinstance(self.source, ClaimFileSource):
            raise ValueError(f"{where}: source is {type(self.source).__name__}, not a ClaimFileSource")
        if not isinstance(self.target, ClaimTarget):
            raise ValueError(f"{where}: target is {type(self.target).__name__}, not a ClaimTarget")
        ClaimFileSource.from_dict(self.source.to_dict(), where)
        ClaimTarget.from_dict(self.target.to_dict(), where)
        if not isinstance(self.fetched_at, datetime):
            raise ValueError(f"{where}: fetched_at is {type(self.fetched_at).__name__}, not a datetime")
        required_str(self.source_version, "source_version", where)
        required_str(self.source_key, "source_key", where)
        require_join_key(self.target_key, "target_key", where)

    @classmethod
    def from_dict(cls, block: object, where: str) -> "ClaimFileEnvelope":
        """Rebuild an envelope from what :meth:`to_dict` wrote, validating each member.

        The only place a claim file's first line becomes provenance. Every member is
        checked here rather than where a consumer reads it: an envelope is read once
        per file and is what the report rests on, so an unparseable ``fetched_at`` or
        a source with no repository must fail as a malformed claim file, not later as
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
            source=ClaimFileSource.from_dict(block.get("source"), where),
            source_version=required_str(block.get("source_version"), "envelope source_version", where),
            source_key=required_str(block.get("source_key"), "envelope source_key", where),
            target=ClaimTarget.from_dict(block.get("target"), where),
            target_key=required_str(block.get("target_key"), "envelope target_key", where),
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
        claim file silently. Every member of this record is required, so none is
        omitted — unlike the nested records, which drop the members they lack.
        """
        encoded = {
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "fetched_at": self.fetched_at.isoformat(),
        }
        return {f.name: encoded.get(f.name, getattr(self, f.name)) for f in fields(self)}


@dataclass
class FileInfo:
    """Input file information for classification.

    Carries the filename as a parsed :class:`FileName` fact rather than a raw string
    (epic #242): the name is parsed once, at whatever boundary constructs the
    ``FileInfo``, and everything downstream reads the parsed attributes instead of
    re-deriving the extension. Build one from a raw filename via
    :meth:`from_filename`, which is the single parse site on this path.
    """

    name: FileName = FileName.EMPTY
    file_size: int | None = None
    dataset_title: str | None = None
    # Future: bam_header, vcf_header for Tier 5

    @classmethod
    def from_filename(cls, filename: str, **kwargs) -> "FileInfo":
        """Build a ``FileInfo`` from a raw filename string, parsing it once.

        The entry-point convenience for callers that hold a raw name (scripts, the
        engine's single-file conveniences, tests): it funnels the raw string through
        ``FileName.parse`` so the parse happens exactly once here, honoring the
        "parse once" invariant of epic #242.
        """
        return cls(name=FileName.parse(filename), **kwargs)


@dataclass
class ClassificationResult:
    """Result of classifying a file."""

    data_modality: str | None = None
    reference_assembly: str | None = None
    reasons: list[str] = field(default_factory=list)
    rules_matched: list[str] = field(default_factory=list)
