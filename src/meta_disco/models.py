"""Data models for file classification."""

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any

from .file_name import FileName

# Classification status constants. NOT_APPLICABLE / NOT_CLASSIFIED are today
# smuggled into a field's `value`; the sentinel→status migration (epic #116) is
# splitting them into a dedicated `status` field. CLASSIFIED is the status when a
# real value was determined.
CLASSIFIED = "classified"
NOT_APPLICABLE = "not_applicable"
NOT_CLASSIFIED = "not_classified"
# Top-tier claims disagreed and no curator rule has answered it (issue #88; claims
# contract 4.3's tier stage, 4.7). The rule engine resolves such a field to this status with a
# null value, and the index producer re-emits a parent's conflict as it.
CONFLICT = "conflict"

# What field_label emits in place of a value. It renders a classified field as its
# value and any other field as its status, so a label outside this set is a real
# value. Defined here, beside the constants that compose it, so a consumer asking
# "did this label carry a value?" (corpus_diff) tracks the status vocabulary
# instead of re-spelling it — a status added above and not here would otherwise be
# silently counted as a value.
STATUS_LABELS = frozenset({NOT_APPLICABLE, NOT_CLASSIFIED, CONFLICT})

# The two statuses a rule may declare (claims contract 3.6): a rule's `then.status`, a
# value-map row's declaration, and `make_claim`'s status check all read this one set.
AUTHORABLE_STATUSES = frozenset({NOT_APPLICABLE, NOT_CLASSIFIED})

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
# What the repository's system of record publishes for the file, as distinct from a
# submitter's table (`repository_metadata`); contract 4.1 kind 2, 7.12 (#497).
SOURCE_PUBLISHED_VALUE = "published_value"
SOURCE_WRANGLER_ANNOTATION = "wrangler_annotation"
# The kinds that name a source outside this repository. A claim with one of these
# must carry a `ClaimSource`, and only such a claim may: it is what makes a claim an
# import, and every import rule `make_claim` enforces — no tier, cite a mapping rule
# — keys off it. Without the pairing a claim could declare itself repository metadata,
# carry `tier=999` because it has no source object, and outrank every rule in
# `evaluate_claims` — the silent override epic #391 rejected on measured evidence
# (#401 review).
EXTERNAL_SOURCE_TYPES = frozenset(
    {
        SOURCE_EXTERNAL_GROUND_TRUTH,
        SOURCE_REPOSITORY_METADATA,
        SOURCE_PUBLISHED_VALUE,
        SOURCE_WRANGLER_ANNOTATION,
    }
)
# The kinds an *importer* may write, which is narrower. A curator claim is legitimate
# — a curator's decision is reviewed and cited like any other — but a curator does not
# reach us as an evidence file: contract 1.6 and 1.7 say it "is unlike every other in
# how it enters: as rules, not as evidence", and 1.7 makes a decision about a single
# file a rule whose selection matches one file. So the envelope's vocabulary is these
# three, and the format cannot express the one input the contract routes elsewhere
# (#421 review). Not derived by subtracting from EXTERNAL_SOURCE_TYPES: a kind added
# there should not silently become writable to a file.
IMPORTER_SOURCE_TYPES = frozenset(
    {
        SOURCE_EXTERNAL_GROUND_TRUTH,
        SOURCE_REPOSITORY_METADATA,
        SOURCE_PUBLISHED_VALUE,
    }
)
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
        SOURCE_PUBLISHED_VALUE,
        SOURCE_WRANGLER_ANNOTATION,
    }
)

# Keys a claim may be attached to a target row by (#392, extended in #401). One
# vocabulary for two positions: an evidence file's envelope declares which of these it is
# keyed by (`target_key`), and a claim records which one actually attached it
# (`join_key`) once the join has run.
#
# These are keys of the *target*, not names a source publishes. A source keyed by an
# ENA run accession does not add a term here — its importer maps that accession to
# one of these and writes the value in the target's space, which is what keeps corpus
# knowledge in the importer and transform logic out of the join.
#
# Measured on the compact-derived AnVIL corpus (708,088 records,
# `anvil_files_metadata.ndjson`): `file_id`, `entry_id`, `drs_uri`, `file_md5sum` and
# `file_name` are each present on every record, and the first three are unique on every
# record too. `entry_id` is the exception a snapshot-derived corpus (#499) makes: it is
# Azul's per-index id and no such record carries it. What separates
# them is uniqueness: `file_md5sum` is non-unique on 1.72% of rows and `file_name` on
# 69.4%, so a filename is usable only inside a dataset scope (2 collisions in 16,271
# within AnVIL_HPRC_R2, against 99.3% within ANVIL_1000G_PRIMED_data_model). No
# record publishes `file_path` — it is here for a target that does.
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


def _field_entry(record: Mapping[str, Any], field_name: str):
    """Return the per-field classification entry/value from a record, or None.

    ``Mapping``, not ``dict``: this only reads, and a ``TypedDict`` is not
    assignable to ``dict`` at all — whatever its value types (PEP 589) — so a
    caller holding a declared record shape could not pass one. The old parameter
    was bare ``dict``, so value-type variance was never what blocked it.

    The value type stays ``Any``, which is what bare ``dict`` already meant, so
    the widening changes nothing about what callers infer. ``Mapping[str,
    object]`` is the truer type — it surfaces that :func:`field_label` declares
    ``-> str | None`` while returning whatever the record held at that key, a
    claim nothing checks. #464 weighed that and closed not-planned: reads here
    go through ``.get``, which Pyright does not key-check even under ``strict``,
    and the shapes that matter are declared in LinkML and validated against real
    output. Revisit on evidence of a bug a declared shape would have caught, not
    on a count of dict-shaped signatures (#461).

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
    NOT_CLASSIFIED, ``conflict`` → CONFLICT (#88), any real value → CLASSIFIED.
    So every label ``field_label`` can emit maps back to its own status, and a
    ``conflict`` label can never be read as a classified value. Used by the read side
    (``_entry_status``) and by ``build_field_entry`` when a producer carries the
    sentinel in ``value`` and no explicit status is given, so reader and producers
    stay in lockstep as epic #116 moves sentinels out of ``value``.
    """
    if value == NOT_APPLICABLE:
        return NOT_APPLICABLE
    if value == CONFLICT:
        return CONFLICT
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
    present — any of the four statuses, ``conflict`` included, which no value can
    carry. Otherwise derives the status from the sentinel-in-``value`` convention,
    yielding one of CLASSIFIED / NOT_APPLICABLE / NOT_CLASSIFIED; a missing/None
    value reads as NOT_CLASSIFIED.
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


def required_str(value: object, label: str, where: str) -> str:
    """Return ``value`` as a non-empty string, or raise naming ``label`` and ``where``.

    One definition of "this member is a usable string" for :class:`ClaimSource` and
    for ``value_map``'s scope identifiers. The evidence-file envelope used it too until
    #494, when the envelope became the model generated from the schema, whose
    patterns say the same thing; this is the hand-written twin for the records that
    stay dataclasses.

    ``None`` is rejected here rather than by a key check: an explicit ``"name": null``
    is a present key, and ``to_dict`` omits null members entirely, so both arrive as
    an absent value that a key check would read differently from each other. The
    empty string is refused too — a name that identifies nothing.

    A line break is refused with it. These members are identifiers — a repository, a
    dataset, a table — and none of them contains one, while every one can be printed
    on one line of a report, where an embedded newline is a second report line. The
    schema refuses the same value — the slots carry ``pattern: "^[^\\r\\n]+\\Z"``,
    which excludes a line terminator anywhere, including the trailing one that ``$``
    would have allowed through (#401 review).

    ``where`` locates the fault — a file and line for a reader, the constructing call
    for a writer — and prefixes every message.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where}: {label} is {value!r}, not a non-empty string")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{where}: {label} is {value!r}, which carries a line break")
    return value


def optional_str(value: object, label: str, where: str) -> str | None:
    """Return a member a record may not have: None when absent, checked when present.

    None is what :meth:`ClaimSource.to_dict` meant by omitting the key, so it passes.
    Anything else must satisfy :func:`required_str` — a present member that is not a
    non-empty string is a mis-serialized record, not one to interpret.
    """
    return None if value is None else required_str(value, label, where)


def _require_one_of(value: object, vocabulary: frozenset[str], noun: str, label: str, where: str) -> str:
    """Return ``value`` as a member of ``vocabulary``, or raise naming it and ``where``.

    One wording for "this member is not in that closed set", so the vocabularies a
    slot map and a claim pin do not each grow a phrasing of the same fault. ``noun``
    completes the sentence: *is not a key of the target*, *is not a kind of external
    source*. The evidence envelope pins the same two vocabularies through the enums
    of the generated model instead (#494).
    """
    if not isinstance(value, str) or value not in vocabulary:
        raise ValueError(f"{where}: {label} {value!r} is not {noun} (expected one of {sorted(vocabulary)})")
    return value


def require_importer_source_type(value: object, label: str, where: str) -> str:
    """Return ``value`` as a kind of source an importer may write, or raise.

    An evidence file is written by an importer reading something we do not own, so its
    ``source_type`` is one of :data:`IMPORTER_SOURCE_TYPES`. Two kinds are excluded and
    for different reasons. The inference kinds, because a file declaring
    ``filename_rule`` would be naming our own rule engine as its publisher. And
    ``wrangler_annotation``, because a curator enters as **rules**, not as evidence
    (contract 1.6, 1.7) — accepting one here would let #397 be built as an importer
    against a format that takes it and a reconcile stage that has nowhere to put it.

    Checked here for a slot map's declared kind (``slot_map``); the evidence envelope
    that kind is written to holds it to the same vocabulary through the generated
    model's ``ImporterSourceTypeEnum`` (#494). It sits on the envelope rather than on
    every row (#421): one repository, dataset and table is one kind of source, so it
    is checked once per file and reconcile reads it from there when it stamps the
    claim it makes from a row.
    """
    return _require_one_of(value, IMPORTER_SOURCE_TYPES, "a kind of source an importer may write", label, where)


def require_join_key(value: object, label: str, where: str) -> str:
    """Return ``value`` as a key of the target, or raise naming ``label`` and ``where``.

    Checked here for a claim recording which key attached it (``join_key``,
    ``rule_engine.make_claim``); an evidence file's envelope declaring which key it is
    keyed by (``target_key``) is held to the same vocabulary by the generated model's
    ``JoinKeyEnum`` (#494). One vocabulary either way — ``archive_accession`` is the
    live example of a member that moves, a derived fact rather than a record field.
    """
    return _require_one_of(value, JOIN_KEYS, "a key of the target", label, where)


@dataclass(frozen=True, kw_only=True)
class ClaimSource:
    """Identity of an external source that produced a claim (issue #392).

    The producer handle for a claim that is not from one of our rules. The schema's
    ``ClaimSource`` class is the definition of what its members mean and why the
    record is cut at this granularity; this is the Python side of it.

    Four levels of *where*, narrowing: the source, the collection within it, the
    table within that, and the column the raw value was read from. ``dataset`` is
    what makes ``column`` legible — the same column name means different things in
    different datasets, so a claim that named only its column could not be
    interpreted without going back to the file it arrived in, which nothing that
    reads output evidence can do (#401 review).

    An evidence file's envelope holds the first three for a whole file and uses the
    schema's ``EvidenceFileSource`` for it, which has no ``column`` because one table's
    claims are read from several. ``source_evidence.claim_source_for`` copies the
    three across and adds this claim's column. The one asymmetry is deliberate: the
    envelope calls the top level ``repository`` because an evidence file names a system,
    while a claim calls it ``name`` because that is what it has always been and it is
    what the output ``evidence`` array already carries.

    A dataclass and not a generated model like the envelope (#494): ``to_dict`` runs
    once per imported claim in ``rule_engine.make_claim``, and the record is built once
    per column of an evidence file being read — it stays on the cheap side.

    Frozen because a source's identity is a fact about where a claim came from,
    not state to edit after the claim is built; that also lets one instance be
    shared by every claim read from the same table without aliasing risk.
    """

    name: str
    url: str | None = None
    dataset: str | None = None
    table: str | None = None
    column: str | None = None

    def __post_init__(self) -> None:
        """Check the members, because a dataclass annotation is not a runtime check.

        This record reaches output evidence: a ``ClaimSource`` is handed straight to
        ``make_claim``, and ``ClaimSource(name="HPRC", dataset=7)`` would otherwise
        serialize a number into the schema's ``Evidence`` and only be caught at a file
        or schema boundary, if at all (#401 review). Per source object and not per
        claim: an evidence file builds one per column and every claim read from that
        column shares it.
        """
        where = "claim source"
        required_str(self.name, "name", where)
        for member in ("url", "dataset", "table", "column"):
            optional_str(getattr(self, member), member, where)

    def to_dict(self) -> dict:
        """Serialize for output, dropping members the source does not have.

        Keys come from ``fields()`` rather than being listed, so a member added here
        is emitted rather than silently dropped from every claim. Null members are
        omitted rather than written as explicit nulls: a source either has a member
        or does not, and there is no "we looked and found nothing" state for a reader
        to tell apart from an absent one. (``ReferenceBuild.to_dict`` keeps its nulls
        for exactly that reason.)
        """
        return {f.name: v for f in fields(self) if (v := getattr(self, f.name)) is not None}


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
