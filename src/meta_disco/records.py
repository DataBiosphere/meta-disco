"""Typed record views passed past the pipeline's load boundary (#172).

The pipeline used to pass raw ``dict``s downstream and re-derive field safety at
every consumer, because it validated a record against the Pydantic contract and
then threw the model away and kept the dict (#171's scattered ``str(... or "")``
guards were point fixes for that one root cause). Instead, ``run()`` splits the
filtered records into two typed streams at the boundary:

* **valid** (no classifier-relevant contract violation) -> :class:`ClassifierRecord`,
  whose classifier-relevant fields are ``str``/``int`` by construction, so the
  fetch/classify path reads typed attributes with no per-field guards.
* **invalid** (a classifier-relevant field violates the input contract, the drift
  #161 exists to catch) -> :class:`InvalidRecord`, which coerces the echoed string
  identity fields in one constructor and carries the blocking reasons for the
  ``validation_failed`` row.

A record with no usable ``file_md5sum`` reaches neither stream: it is excluded before
the split (``exclusions.has_usable_checksum``, #376), because it can be neither fetched
nor cache-keyed and a row echoing a null md5 would have no usable identity. So every
``InvalidRecord`` carries a well-formed md5 and is invalid on some other field.

The split criterion is ``classification_blocking_reasons`` (unchanged from #161):
a record that violates the full contract only on a field the classifier never
reads (e.g. ``drs_uri``) is *not* diverted — it still classifies, and the
whole-corpus ``validate_metadata`` gate reports that drift. So the "valid" stream
is modeled over exactly the classifier-relevant fields, not the full contract.

Both classes expose the same six identity attributes (``file_name``,
``file_format``, ``file_md5sum``, ``file_size``, ``dataset_title``, ``entry_id``),
so ``_build_record`` and the work-list steps read them uniformly regardless of
stream. They also both expose ``data_modality`` and ``reference_assembly`` — the
published values (#424), not identity and not classifier input — for the same
reason: ``_build_record`` reads them off either stream without asking which it has,
and a record that failed the input contract is still one the repository publishes
values for.

The module also holds the two write-side dataclasses the pipeline serializes at
its output boundary, which follow the same frozen / field-order-is-output-order /
``to_dict`` discipline: :class:`OutputRecord`, the per-file output envelope (#204),
and :class:`RunMetadata`, the per-run tally block (#205).
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

from .file_name import FileName
from .schema_vocab import value_in_vocabulary

# The two dimensions the repository publishes of its own accord, in the order the
# ``published`` block emits them. Not the classifier's input and not its answer: the
# published output (#424). Two of the five CLASSIFICATION_FIELDS, deliberately not
# derived from that tuple — it is the set the repository's file index happens to carry,
# and it moves when the repository moves, not when our dimensions do.
PUBLISHED_FIELDS = ("data_modality", "reference_assembly")


def published_from(record: dict, source: str | None) -> dict | None:
    """The ``published`` block for one raw input record (contract 7.7's one-liner).

    The form every producer calls, so a producer states *which record* it is building
    the block for and nothing else. Reading the field list from :data:`PUBLISHED_FIELDS` here is
    what makes that tuple authoritative: a producer cannot read a stale subset of the
    dimensions, and adding a third one does not touch a single call site.

    The two fields are read with ``.get`` because they are outside the input contract
    (#424 — they are not input), so no validation has run on them and no caller
    guarantee covers them.
    """
    return build_published({field: record.get(field) for field in PUBLISHED_FIELDS}, source)


def build_published(values: dict[str, Any], source: str | None) -> dict | None:
    """The ``published`` block for one file, or None when the repository publishes none.

    Carries a repository's own values into the output (#424): what it publishes for
    this file today, transcribed exactly as written and as a list wherever it
    published a list. This is not a claim and nothing resolves against it —
    classification does not read it, and a file's ``value`` is whatever inference
    concluded, block or no. It exists so the two can be compared per file, and
    precisely because a published value may produce nothing else: ``GRCm39`` is a term
    this project has no word for, so without this block those 220 values would appear
    in the output nowhere at all.

    ``in_vocabulary`` names, per dimension, the subset of that dimension's published
    values that *are* terms in its enum. An empty list means the repository published
    something this vocabulary cannot say — the case for every published value in the
    corpus today, and what makes the gap countable from the output rather than
    asserted. A dimension the repository publishes nothing for is absent from the map
    rather than carrying an empty list, so the map's keys are exactly the dimensions it
    speaks to.

    Returns None — and the envelope emits ``"published": null`` — when the repository
    publishes nothing for either dimension, which is ~98% of the corpus.

    **Shape is checked in three places, and this is the middle one.** These two fields
    are outside the input contract (#424 — they are not input), so ``validate_metadata``
    passes them through unexamined and no caller guarantee covers them. What does check
    them: ``pipeline.refuse_bad_published_shape`` scans a whole snapshot at the load
    boundary and is what actually refuses a pre-#424 spelling — before any record is
    fetched or written, which is the only point at which "refuse the snapshot" can be
    true. The output schema's ``Published`` class refuses a bad shape at the far end,
    once a record exists. This guard sits between them, at the single construction site,
    and covers a caller that reached it without passing through that loader.

    It is not redundant with either. Both bad shapes are quiet without it: a bare string
    is *iterable*, so it would be walked character by character and report ``GRCh38`` — a
    real term — as one this vocabulary lacks, then render as ``G || R || C || h || 3 || 8``;
    a non-iterable such as an int would raise a bare ``TypeError`` from the comprehension
    below. Raising here names the field and the value instead. Note this raise is *not*
    by itself a refusal on the pipeline path: it happens inside a worker, and
    ``_run_parallel`` catches every worker exception and writes no row, so a snapshot
    that reached here would lose rows rather than fail — which is why the load-boundary
    check exists and why it, not this, is what the snapshot is refused by.

    ``values`` is typed ``Any`` rather than ``list[str] | None``: the looser type is the
    true one, since a caller reads these straight off a raw record and can promise
    nothing about them — this function is where the narrowing happens, and annotating the
    promise instead of the check would only hide that.
    """
    published = {}
    for field in PUBLISHED_FIELDS:
        value = values.get(field)
        if value is not None and not isinstance(value, list):
            # The str case has a known cause worth naming; any other type is drift with
            # no story, so it gets no invented one.
            hint = (
                " A snapshot built before #424 spells these as scalars; rebuild it with"
                " scripts/download_anvil_manifest.py."
                if isinstance(value, str)
                else ""
            )
            raise ValueError(f"published {field} is {type(value).__name__}, not a list: {value!r}.{hint}")
        if value is not None and not all(isinstance(v, str) for v in value):
            raise ValueError(f"published {field} holds a non-string value: {value!r}")
        if value is not None and not all(value):
            # The manifest reader drops empty elements, so a cell of nothing but
            # separators arrives as no published value at all. A list holding one did
            # not come from that reader, and treating it as a published value would put
            # a blank in the comparison as though the repository had said something.
            # Refused rather than dropped: silently transforming a value here is what
            # `_first()` did wrong.
            raise ValueError(f"published {field} holds an empty value: {value!r}")
        published[field] = value

    if not any(published.values()):
        return None
    return {
        "source": source,
        **published,
        "in_vocabulary": {
            field: [value for value in field_values if value_in_vocabulary(field, value)]
            for field, field_values in published.items()
            if field_values
        },
    }


def coerce_identity(value: Any) -> str:
    """Stringify a drifted identity value for echo; null (``None``) becomes ``""``.

    Distinguishes null from a falsy-but-present value on purpose: a ``str(value or
    "")`` would collapse ``0``/``False`` to ``""`` and lose the drifted value, so a
    ``file_name`` of ``0`` here becomes ``"0"``, not ``""``. Only genuine ``None``
    (absent/null) maps to the empty string.
    """
    return "" if value is None else str(value)


@dataclass(frozen=True)
class ClassifierRecord:
    """A filtered record whose classifier-relevant fields passed the input contract.

    Built only from a record with no ``classification_blocking_reasons``, so
    ``file_name``/``file_format`` are ``str``, ``file_size`` is a non-negative
    ``int``, and ``file_md5sum`` is a well-formed md5 ``str`` — all by construction
    (the md5 doubly so: a record without one is excluded at load, #376).
    That post-condition is what lets the fetch/classify path drop the per-field
    guards #171 added.

    ``dataset_title``/``entry_id`` are *not* classifier-relevant, so a record with
    either drifted still reaches the valid stream. They are echoed into the output
    row untouched — typed ``Any`` and passed through as-is, exactly as the raw-dict
    path did.

    ``name`` is the raw ``file_name`` parsed into a :class:`FileName` once, here at
    the load boundary (epic #242), and threaded through the fetch/classify path so
    nothing downstream re-parses. The raw ``file_name`` string is kept alongside it:
    it is the identity echoed into the output row and the shared attribute the
    ``InvalidRecord`` stream also exposes (``name`` is a valid-stream-only fact).

    ``url`` is an optional explicit content URL (#276). It is ``None`` for the AnVIL
    path, where the fetcher derives the S3-mirror URL from ``file_md5sum``; a caller
    whose files are not on that mirror (the HPRC catalogs, keyed on a hash of their
    full path and served from their own S3 paths) supplies it here and the fetcher
    streams from it instead. Not a classifier-relevant field, so its absence never
    diverts a record.

    ``data_modality`` / ``reference_assembly`` are the published values (#424),
    carried from the input record to the output's ``published`` block. Nothing on the
    classify path reads either one — they are not evidence, not a claim and not a
    tier participant; they are what AnVIL publishes today, kept so the run's answer
    can be compared against it. ``None`` where the repository publishes nothing, which is
    most of the corpus and all of the HPRC path.
    """

    file_name: str
    file_format: str
    file_size: int
    file_md5sum: str
    dataset_title: Any
    entry_id: Any
    name: FileName
    url: str | None = None
    data_modality: list[str] | None = None
    reference_assembly: list[str] | None = None

    @classmethod
    def from_record(cls, record: dict) -> ClassifierRecord:
        """Build from a raw record already known to have no blocking reasons.

        The four classifier-relevant fields are read by subscript, not ``.get(...)
        or ""``: the caller's blocking check guarantees each is present and
        well-typed, so a missing/mistyped value here is a bug in the caller, not
        input to defend against (CLAUDE.md error-handling philosophy). A ``KeyError``
        or wrong type surfacing here means the split routed a record it should not
        have.

        ``file_name`` is parsed into a :class:`FileName` exactly once here — the
        single parse site on the pipeline path (#242). ``url`` is optional (#276) and
        absent on the AnVIL path, so it is read with ``.get`` and defaults to ``None``.

        The two published dimensions are read with ``.get`` for a stronger reason than
        optionality: they are not slots of the input contract at all (#424 — they are
        not input, they are the published output), so ``validate_metadata`` never looks
        at them. The shared loader does — ``pipeline.refuse_bad_published_shape`` refuses
        a bad shape before either stream is built — but a caller reaching this
        constructor another way has had no such check. A record that carries neither reads as
        ``None`` on both, exactly like one from a source that declares nothing.
        """
        return cls(
            file_name=record["file_name"],
            file_format=record["file_format"],
            file_size=record["file_size"],
            file_md5sum=record["file_md5sum"],
            dataset_title=record.get("dataset_title"),
            entry_id=record.get("entry_id"),
            name=FileName.parse(record["file_name"]),
            url=record.get("url"),
            data_modality=record.get("data_modality"),
            reference_assembly=record.get("reference_assembly"),
        )


@dataclass(frozen=True)
class InvalidRecord:
    """A filtered record whose classifier-relevant fields violate the input contract.

    Diverted at the load boundary and never fetched or classified (#161): it carries
    the identity fields for the ``validation_failed`` output row and progress label,
    plus the blocking ``reasons`` used as that row's evidence. Like
    ``ClassifierRecord`` it exposes all six identity attributes ready to echo —
    ``file_name``/``file_format`` are coerced to ``str`` in :meth:`from_record`
    (the two fields downstream does string operations on), the rest are echoed as
    the record carried them, since a ``validation_failed`` row may carry their
    drifted (non-string) types.

    It carries the published values too (#424), and is typed ``Any`` for it rather than
    ``list[str] | None``: the two are outside the input contract, so the contract has
    checked their shape on this stream no more than on the other, and this stream is the
    one built from records already known to be drifted. (The shared loader does check
    them, but the annotation describes what this class can promise, not what one caller
    happens to have run.) A file
    the repository publishes a modality for does not stop being published by failing our
    contract on ``file_size``, so the row still reports what the repository publishes.
    """

    file_name: str
    file_format: str
    file_md5sum: Any
    file_size: Any
    dataset_title: Any
    entry_id: Any
    reasons: list[str]
    data_modality: Any = None
    reference_assembly: Any = None

    @classmethod
    def from_record(cls, record: dict, reasons: list[str]) -> InvalidRecord:
        """Build from a raw record whose classifier-relevant fields may be drifted.

        ``file_name``/``file_format`` may be null (present-but-None) or a drifted
        non-string (an int); ``coerce_identity`` maps null to ``""`` and stringifies
        any other value — the sole coercion site the #171 point fixes are replaced
        by — so neither can raise in the downstream path/extension operations or the
        progress-label slice.
        """
        return cls(
            file_name=coerce_identity(record.get("file_name")),
            file_format=coerce_identity(record.get("file_format")),
            file_md5sum=record.get("file_md5sum"),
            file_size=record.get("file_size"),
            dataset_title=record.get("dataset_title"),
            entry_id=record.get("entry_id"),
            reasons=reasons,
            data_modality=record.get("data_modality"),
            reference_assembly=record.get("reference_assembly"),
        )


@dataclass(frozen=True)
class OutputRecord:
    """The per-file output envelope: identity fields wrapping a classifications payload.

    The shape ``ClassifyPipeline`` writes per record. Both of *its* producers construct
    it — the batch path (``_build_record`` over a ``ClassifierRecord``/``InvalidRecord``
    work item) and the single-file path (``classify_single``) — and serialize through
    ``to_dict``, so the eight-key envelope can no longer drift between them (#204).

    **It is not the shape of every classification record in a run.** #204 covers the
    seven file types the pipeline classifies (bam, vcf, fastq, fasta, gfa, tar, bed);
    the four standalone producers build their output dicts by hand and emit wider
    records — ``dataset_id`` on auxiliary/image/remaining (nine keys), and
    ``dataset_id`` plus ``parent_file``/``parent_md5sum`` on index (eleven), which also
    writes a third envelope key, ``unmatched_files``. Their run ``metadata`` blocks
    differ too: five distinct shapes across the eleven files, sharing only ``complete``.
    So a run has three record shapes, not one, and ``test_output_shape.RECORD_KEYS``
    pins only this one. What all eleven *do* share is ``classifications``,
    the six identity fields this module's docstring names, and ``published`` — which is
    what lets ``output_utils.iter_records``, ``field_label`` and ``corpus_diff`` read them
    uniformly. Unifying the four on this record is #429.

    ``published`` is the repository's own values (#424) — what it publishes for this file
    today, beside what this run concluded. It is ``None`` on most records and on the
    whole single-file path, and is emitted as ``"published": null`` rather than
    omitted, so the envelope keeps one shape for every row (the reason ``RunMetadata``
    still emits a retired ``dropped: 0``). It is not part of ``classifications`` and
    never merges into it: the dimensions block is this project's answer, and mixing
    the published values into it is the confusion #424 exists to undo.

    Identity typing mirrors the two paths it is built from: ``file_name`` is ``str``
    on both (the batch work item types it; ``classify_single`` defaults it to ``""``).
    ``file_format`` is ``str`` on the batch path but ``str | None`` on the single-file
    path (its argument is optional). The remaining fields — ``md5sum`` (echoed from
    ``file_md5sum``), ``file_size``, ``dataset_title``, ``entry_id`` — are passed
    through as carried, so they are ``Any``: the ``validation_failed`` path may carry
    drifted (non-string) values, and the classifiable path's guarantee already lives
    upstream in ``ClassifierRecord``. This record does no string operations on the
    identity fields (``to_dict`` only echoes them), so the looser typing is safe.
    ``classifications`` is the dimensions payload plus any per-type extras a classifier
    merged into it (e.g. the fastq scalar hints), which live inside this dict, never as
    new envelope keys.
    """

    # Field order is the serialized envelope order — ``to_dict`` derives the output
    # dict from these fields, so the two cannot drift and a new field is emitted
    # automatically. Every field name is also its output key.
    file_name: str
    md5sum: Any
    file_size: Any
    file_format: str | None
    dataset_title: Any
    classifications: dict
    entry_id: Any
    published: dict | None = None

    @classmethod
    def from_work_item(
        cls,
        item: ClassifierRecord | InvalidRecord,
        classifications: dict,
        source: str | None = None,
    ) -> OutputRecord:
        """Build from a parsed work item and its classifications payload.

        Reads the six identity attributes both streams expose (see the module
        docstring), so it is agnostic to which stream produced ``item`` — and the two
        published dimensions, which both streams expose for that same reason.

        ``source`` names the repository the values were read from (#424), and is
        the caller's to supply because it is a fact about the run's input snapshot,
        not about this record: the pipeline reads it from the input envelope. ``None``
        where the input carried no envelope to name one, which is honest — better an
        unnamed repository than a guessed catalog.
        """
        return cls(
            file_name=item.file_name,
            file_format=item.file_format,
            md5sum=item.file_md5sum,
            file_size=item.file_size,
            dataset_title=item.dataset_title,
            entry_id=item.entry_id,
            classifications=classifications,
            published=build_published({field: getattr(item, field) for field in PUBLISHED_FIELDS}, source),
        )

    @classmethod
    def from_single(
        cls,
        *,
        md5sum: str,
        file_name: str,
        file_size: int | None,
        file_format: str | None,
        classifications: dict,
    ) -> OutputRecord:
        """Build from a standalone ``classify_single`` call (no work item, no source record).

        ``dataset_title``/``entry_id`` have no source here and serialize as ``None`` —
        the envelope's one canonical shape, which is why the single-file path's output
        carries the same eight keys as the batch path. ``published`` is ``None`` for the
        same reason and one more: this path has no input record, so there is no
        published values to carry even in principle.
        """
        return cls(
            file_name=file_name,
            file_format=file_format,
            md5sum=md5sum,
            file_size=file_size,
            dataset_title=None,
            entry_id=None,
            classifications=classifications,
        )

    def to_dict(self) -> dict:
        """Serialize to the output envelope dict (the eight-key shape written to JSON).

        Derived from the dataclass fields (a shallow copy — ``classifications`` is not
        deep-copied), so every field is emitted, in declaration order, and ``to_dict``
        cannot drift from the field list.
        """
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class RunMetadata:
    """The per-run tally block written under ``"metadata"`` in the final JSON output.

    The pipeline used to build this as a 10-key literal in ``_save_final`` whose
    derived keys carried their invariants only in prose comments. :meth:`from_counts`
    is now the single site that computes those derived tallies, so the invariants are
    code, asserted in isolation by ``test_records.py`` (#205):

    * ``dropped`` is retired — a fetch failure is written as a ``content_unreadable``
      row, never dropped (#155) — but the key is still emitted as ``0`` for
      output-schema stability.
    * ``failed`` is every record that produced no row: ``dropped + errored``. Since
      ``dropped`` is always ``0``, only a raising worker (``errored``) counts, so
      ``failed == errored``.
    * ``processed`` is ``successful + errored + validation_failed``: a
      ``validation_failed`` row (failed the input contract, #161) is counted neither
      in ``successful`` nor in ``failed``, so it is added in explicitly here.
    """

    # Field order is the serialized ``metadata`` key order — ``to_dict`` derives the
    # output dict from these fields, so the two cannot drift. Every field name is also
    # its output key.
    total_to_process: int
    processed: int
    successful: int
    failed: int
    dropped: int
    errored: int
    validation_failed: int
    from_cache: int
    content_unreadable: int
    complete: bool

    @classmethod
    def from_counts(
        cls,
        *,
        total: int,
        successful: int,
        from_cache: int,
        content_unreadable: int,
        errored: int = 0,
        validation_failed: int = 0,
        complete: bool = True,
    ) -> RunMetadata:
        """Build a run's metadata from the raw counts, computing the derived tallies once.

        The three derived keys (``dropped``, ``failed``, ``processed``) are computed
        here and only here (see the class docstring for each invariant), so a caller
        supplies only the counts it actually measured.
        """
        dropped = 0
        return cls(
            total_to_process=total,
            processed=successful + errored + validation_failed,
            successful=successful,
            failed=dropped + errored,
            dropped=dropped,
            errored=errored,
            validation_failed=validation_failed,
            from_cache=from_cache,
            content_unreadable=content_unreadable,
            complete=complete,
        )

    def to_dict(self) -> dict:
        """Serialize to the ``metadata`` dict (the ten-key shape written to JSON).

        Derived from the dataclass fields, so every field is emitted, in declaration
        order, and ``to_dict`` cannot drift from the field list.
        """
        return {f.name: getattr(self, f.name) for f in fields(self)}
