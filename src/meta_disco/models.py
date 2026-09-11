"""Data models for file classification."""

from dataclasses import MISSING, dataclass, field, fields
from datetime import datetime
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

# Keys an external source's claim may be attached to one of our files by (#392).
JOIN_KEY_FILE_PATH = "file_path"
JOIN_KEY_FILE_MD5SUM = "file_md5sum"
JOIN_KEY_DRS_URI = "drs_uri"
JOIN_KEY_FILE_NAME = "file_name"
JOIN_KEYS = frozenset({JOIN_KEY_FILE_PATH, JOIN_KEY_FILE_MD5SUM, JOIN_KEY_DRS_URI, JOIN_KEY_FILE_NAME})

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


@dataclass(frozen=True)
class ClaimSource:
    """Identity of an external source that produced a claim (issue #392).

    The producer handle for a claim that is not from one of our rules. The schema's
    ``ClaimSource`` class is the definition of what the four members mean and why
    the record is cut at this granularity; this is the Python side of it.

    Frozen because a source's identity is a fact about where a claim came from,
    not state to edit after the claim is built; that also lets one instance be
    shared by every claim read from the same table without aliasing risk.
    """

    name: str
    url: str | None = None
    table: str | None = None
    column: str | None = None

    def to_dict(self) -> dict:
        """Serialize for output, dropping members the source does not have.

        Unlike ``ReferenceBuild.to_dict``, null keys are omitted rather than kept:
        a source either has a column structure or it does not, so there is no
        "we looked and found nothing" state for a reader to distinguish from an
        absent field. ``name`` is required and therefore always present.

        Keys come from ``fields()`` rather than ``asdict()``: this record is flat,
        and ``asdict`` deep-copies recursively, which costs an order of magnitude
        for nothing. It is called once per imported claim, so the difference is
        real once the importers land (#369/#394).
        """
        return {f.name: v for f in fields(self) if (v := getattr(self, f.name)) is not None}

    @classmethod
    def from_dict(cls, block: object, where: str, *, without: tuple[str, ...] = ()) -> "ClaimSource":
        """Rebuild a source from what :meth:`to_dict` wrote, validating each member.

        The inverse of ``to_dict`` and derived from ``fields()`` for the same
        reason: a member added to this dataclass is otherwise written by ``to_dict``
        and silently dropped by a reader that names the members by hand. ``where``
        locates the fault for a caller reading a file — ``claim_files`` passes the
        file and line.

        An absent optional member reads back as None, which is what ``to_dict``
        meant by omitting it. A *present* member that is not a non-empty string
        raises: an explicit ``"name": null`` survives a key check but identifies
        nothing, and a source whose table is ``0`` is a mis-serialized record rather
        than one to interpret.

        A member this class does not have is refused rather than ignored. The schema
        validates a claim file's source ``closed=True``, so a reader that quietly
        dropped an unknown key would accept documents the schema rejects — the two
        must refuse the same files (#401 review).

        ``without`` names members that belong to the dataclass but not to *this*
        position in the format, making them unknown keys rather than optional ones.
        A claim file's envelope passes ``("column",)``: the schema models that
        position as ``ClaimFileSource``, which has no column, because a column
        belongs to a claim — one table's claims are read from several columns.
        """
        if not isinstance(block, dict):
            raise ValueError(f"{where}: source is {type(block).__name__}, not an object")
        known = {f.name for f in fields(cls)} - set(without)
        if extra := sorted(set(block) - known):
            raise ValueError(f"{where}: source has unknown member(s) {extra} (expected {sorted(known)})")
        # Which checker a member gets is decided per field at runtime, from whether the
        # dataclass gives it a default, so the values are only ever `str | None` to a
        # type checker — `required_str` raises rather than returning None, but that is
        # not visible through the splat. Widened here rather than at the helpers, which
        # are precise on their own.
        members: dict[str, Any] = {
            f.name: (required_str if f.default is MISSING else optional_str)(
                block.get(f.name), f"source {f.name}", where
            )
            for f in fields(cls)
            if f.name in known
        }
        return cls(**members)


@dataclass(frozen=True)
class ClaimFileEnvelope:
    """What a claim file records once, for every claim in it (issue #401).

    An importer runs out of band from classification — when a catalog refreshes,
    with network — and writes a claim file; a run reads it. This is the header of
    that artefact: where the claims came from, when, and from which version of the
    source. The schema's ``ClaimFileEnvelope`` class is the definition of what the
    members mean; this is the Python side of it, as ``ClaimSource`` is for a claim's
    source. ``claim_files`` is the reader and writer.

    ``source`` is a :class:`ClaimSource` and not a second spelling of one: name, url
    and table are the same facts a claim carries, factored up to the file because
    they are constant across it. ``column`` is the one member left per claim, since
    one table's claims are read from several columns.

    ``corpus_catalog`` is the AnVIL catalog generation this file was built for. It is
    provenance, not a gate: a run reports it and refuses nothing on it (and today
    imports nothing at all — the join is #402). What reads it is the importer,
    deciding on its next pass whether the configured catalog has moved on and the
    file must be re-fetched. It is null for a source with no
    relationship to our catalog — the HPRC Data Explorer, ENA, IGSR — whose claims
    are about files rather than about a snapshot of ours, and which have no catalog
    generation to record; their ``source_version`` carries what they can say instead.

    Frozen for the reason ``ClaimSource`` is: provenance is a fact about where the
    claims came from, not state to edit after they are read.

    Validated on construction (:meth:`__post_init__`) against the same rules
    :meth:`from_dict` applies on the way back in. The writer used to accept any
    envelope while the reader accepted very little, so an importer could spend a
    networked run writing millions of claims behind a header its own reader would
    refuse — and find out at the next classification run, days later and far from
    the cause. A ``source_version`` of ``None`` was the trap: it is not a string, and
    ``to_dict`` drops null members, so the key vanished and the file read back as
    "not an envelope" rather than naming the field (#401 review).
    """

    source: ClaimSource
    fetched_at: datetime
    source_version: str
    corpus_catalog: str | None = None

    def __post_init__(self) -> None:
        """Refuse an envelope that could not be read back, at the point it is built.

        Type hints do not run, so ``source_version=None`` reaches here intact. This
        runs once per claim file, so its cost is nothing against the write it
        precedes.

        The source is checked by serializing it and reading it back through
        :meth:`ClaimSource.from_dict` — the reader's own definition, applied to the
        reader's own input — rather than by re-listing the members here. Checking only
        ``name`` left the parity half-kept: a ``table`` of ``7`` was written happily
        and refused on read (#401 review).
        """
        where = "claim file envelope"
        if not isinstance(self.source, ClaimSource):
            raise ValueError(f"{where}: source is {type(self.source).__name__}, not a ClaimSource")
        ClaimSource.from_dict(self.source.to_dict(), where)
        if self.source.column is not None:
            raise ValueError(
                f"{where}: source names column {self.source.column!r}, but a column belongs to a claim, "
                "not to the file — one table's claims are read from several columns"
            )
        if not isinstance(self.fetched_at, datetime):
            raise ValueError(f"{where}: fetched_at is {type(self.fetched_at).__name__}, not a datetime")
        required_str(self.source_version, "source_version", where)
        optional_str(self.corpus_catalog, "corpus_catalog", where)

    @classmethod
    def from_dict(cls, block: object, where: str) -> "ClaimFileEnvelope":
        """Rebuild an envelope from what :meth:`to_dict` wrote, validating each member.

        The inverse of ``to_dict``, and the only place a claim file's first line
        becomes provenance. Every member is checked here rather than where a consumer
        reads it: an envelope is read once per file and is what the report rests on,
        so an unparseable ``fetched_at`` or a source with no name must fail as a
        malformed claim file, not later as a report that cannot render.

        A trailing ``Z`` is normalized to ``+00:00`` before parsing.
        ``datetime.fromisoformat`` rejects ``Z`` on Python 3.10, which is this
        project's floor and what CI runs, while accepting it from 3.11 — and the
        importers coming in #369/#394 read web APIs that emit ``Z`` almost
        universally. Without this, a claim file written on a 3.11 machine parses
        there and fails on CI, which is a property of the interpreter rather than of
        the file (#401 review).

        ``fetched_at`` must carry a time of day. ``fromisoformat`` accepts a bare
        ``2026-09-01`` and silently returns midnight, so a date-only value would be
        read back as a fetch that claims to have happened at 00:00:00 — a precision
        the file never stated. Two imports on the same day would also be
        indistinguishable, which is the case where the age report matters most. The
        check is on the string rather than the parsed value, because midnight is a
        real time that a genuine fetch can have.

        A member the envelope does not have is refused rather than ignored, and the
        source is parsed ``without`` a column, so that this reader and the schema —
        which validates the envelope ``closed=True`` against a column-free
        ``ClaimFileSource`` — refuse the same documents. A ``"column": null`` on an
        envelope source used to be accepted here and silently stripped while the
        schema rejected it (#401 review). Refusing it here also puts the file and
        line in the message, which :meth:`__post_init__` cannot do — it validates a
        constructed envelope and has no idea where one came from.
        """
        if not isinstance(block, dict):
            raise ValueError(f"{where}: envelope is {type(block).__name__}, not an object")
        known = {f.name for f in fields(cls)}
        if extra := sorted(set(block) - known):
            raise ValueError(f"{where}: envelope has unknown member(s) {extra} (expected {sorted(known)})")
        fetched_at = block.get("fetched_at")
        if not isinstance(fetched_at, str):
            raise ValueError(f"{where}: envelope fetched_at is {fetched_at!r}, not an ISO 8601 string")
        normalized = fetched_at.removesuffix("Z") + "+00:00" if fetched_at.endswith("Z") else fetched_at
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            raise ValueError(f"{where}: envelope fetched_at {fetched_at!r} is not an ISO 8601 datetime") from None
        # An ISO 8601 date is its first 10 characters; anything longer carries a
        # separator and a time. `isoformat()` on a datetime always writes one, so our
        # own writer cannot trip this.
        if len(fetched_at) <= _ISO_DATE_CHARS:
            raise ValueError(
                f"{where}: envelope fetched_at {fetched_at!r} is a date with no time of day — "
                "record when the fetch happened, not only the day it happened on"
            )
        return cls(
            source=ClaimSource.from_dict(block.get("source"), where, without=("column",)),
            fetched_at=parsed,
            source_version=required_str(block.get("source_version"), "envelope source_version", where),
            corpus_catalog=optional_str(block.get("corpus_catalog"), "envelope corpus_catalog", where),
        )

    def to_dict(self) -> dict:
        """Serialize for the envelope line, dropping an absent ``corpus_catalog``.

        Null members are omitted as in :meth:`ClaimSource.to_dict`, so a claim file
        from a source unrelated to our catalog carries no ``corpus_catalog`` key at
        all rather than an explicit null. The two members that are not already JSON
        are encoded on the way out: ``source`` through its own ``to_dict``, and
        ``fetched_at`` as an ISO 8601 string — the form
        ``azul_manifest.metadata_block`` already writes a fetch time in, and the form
        :func:`claim_files.read_envelope` parses back.

        Keys come from ``fields()`` for the reason ``ClaimSource.to_dict`` and
        ``ExcludedFile.to_dict`` do: a member added to the dataclass and not here
        would otherwise be dropped from every claim file silently.
        """
        encoded = {"source": self.source.to_dict(), "fetched_at": self.fetched_at.isoformat()}
        return {
            f.name: encoded.get(f.name, value) for f in fields(self) if (value := getattr(self, f.name)) is not None
        }


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
