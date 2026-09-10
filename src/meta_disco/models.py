"""Data models for file classification."""

from dataclasses import dataclass, field, fields
from datetime import datetime

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
    provenance, not a gate: the run reports it and imports regardless. What reads it
    is the importer, deciding on its next pass whether the configured catalog has
    moved on and the file must be re-fetched. It is null for a source with no
    relationship to our catalog — the HPRC Data Explorer, ENA, IGSR — whose claims
    are about files rather than about a snapshot of ours, and which have no catalog
    generation to record; their ``source_version`` carries what they can say instead.

    Frozen for the reason ``ClaimSource`` is: provenance is a fact about where the
    claims came from, not state to edit after they are read.
    """

    source: ClaimSource
    fetched_at: datetime
    source_version: str
    corpus_catalog: str | None = None

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
