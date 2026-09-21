"""Shared classification pipeline infrastructure.

ClassifyPipeline replaces the duplicated process loops across the 4 header
classify scripts. Each file type is described by a FileTypeConfig dataclass
which carries extension filters, fetcher, classifier, and summary printer.
"""

import json
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import NamedTuple, TypeGuard

from .azul_manifest import REPOSITORY as ANVIL_REPOSITORY
from .exclusions import MD5_RE, partition_records, write_excluded
from .fetchers import FetchError
from .file_name import FileName
from .file_types import FileTypeConfig
from .header_classifier import classify_without_content
from .metadata_schema import (
    classification_blocking_reasons,
    validation_failed_classifications,
)
from .models import JOIN_KEY_FILE_ID, JOIN_KEY_FILE_MD5SUM
from .producers import producer_for
from .records import (
    OUTPUT_MD5SUM_FIELD,
    PUBLISHED_FIELDS,
    ClassifierRecord,
    InvalidRecord,
    OutputRecord,
    RunMetadata,
)


def load_records(input_path: Path) -> list:
    """Load the record list from an input file's envelope.

    Elements are not guaranteed to be dicts — an NDJSON line, or an entry inside the
    envelope's ``files``/``results`` list, may be any JSON value. (The envelope itself
    must be an object: a top-level JSON array is rejected by :func:`load_snapshot`.)
    Hence ``list``, not ``list[dict]``: this is the raw read, used by the
    ``validate_metadata`` gate, which must see every element to report on it.
    Classification producers read :func:`load_classifiable_snapshot` instead, which does
    narrow the element type.

    A ``.ndjson`` file is one record per line; otherwise a JSON object with a
    ``files`` (or legacy ``results``) list. Shared by ``ClassifyPipeline`` and the
    ``validate_metadata`` gate so the envelope handling lives in one place.
    """
    return load_snapshot(input_path)[1]


def load_snapshot(input_path: Path) -> tuple[dict, list]:
    """Load an input file's ``metadata`` block and its record list in one parse.

    Same envelope handling and same errors as :func:`load_records`, which is this
    function's record half — a caller that also needs the envelope facts (which
    catalog a snapshot captured, when it was pulled) gets them without parsing a
    several-hundred-megabyte file a second time.

    The metadata block is ``{}`` for an ``.ndjson`` input, which carries no
    envelope, and for a JSON envelope that has no ``metadata`` key. Either loads
    here, but neither can start a classification run, which needs the envelope to
    name its repository (:func:`record_key`); the ``.ndjson`` twin the AnVIL
    downloader writes serves the reports, not the run.
    """
    with input_path.open() as f:
        if input_path.suffix == ".ndjson":
            return {}, [json.loads(line) for line in f if line.strip()]
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"Expected JSON object with 'results' or 'files' key, got {type(data).__name__}")
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    # Check key presence explicitly rather than `results or files`: a present but
    # empty `results: []` is a valid empty corpus, not a missing key — the truthy
    # fallback would misreport it as "must contain a key".
    for key in ("results", "files"):
        if key in data:
            records = data[key]
            if not isinstance(records, list):
                raise TypeError(f"'{key}' must be a list of records, got {type(records).__name__}")
            return metadata, records
    raise ValueError("JSON object must contain a 'results' or 'files' key")


def published_source(metadata: dict) -> str | None:
    """Name the repository an input snapshot's published values came from, or None.

    Both halves come off the snapshot's own envelope: ``repository`` (who published)
    and ``catalog`` (which generation of what they published), giving e.g.
    ``anvil/anvil15``. Neither is inferred. An earlier form prefixed a hard-coded
    ``anvil`` to whatever catalog it found, which was wrong on a shared load path — the
    HPRC run reads the same function, and would have labelled its records ``anvil/...``
    the moment its downloader emitted an envelope. ``source`` is the one field meant to
    name the publisher, so it is the one field that must not guess (contract 7.11).

    ``None`` unless the envelope carries both. That covers an ``.ndjson`` load, which
    has no envelope; a snapshot pulled before #335 added ``catalog``; and one written
    before #424 added ``repository``. This is the *name* only — the values themselves
    come off each record, so such a run still carries a ``published`` block, with
    ``source`` null. Deliberately not defaulted: an unnamed repository is a fact, and a
    guessed one is the drift #335 exists to catch.
    """
    repository, catalog = metadata.get("repository"), metadata.get("catalog")
    if not (isinstance(repository, str) and repository and isinstance(catalog, str) and catalog):
        return None
    return f"{repository}/{catalog}"


class RecordKey(NamedTuple):
    """The field a source guarantees unique per file, in both spellings a run uses.

    ``input_field`` is its name on an input record; ``output_field`` its name on the
    output row a producer writes. They differ only where ``records.OutputRecord``
    renames a field on the way out (``file_md5sum`` becomes ``md5sum``).
    """

    input_field: str
    output_field: str


HPRC_REPOSITORY = "hprc"

# One declaration per source of the identity that names a file exactly once in that
# source's snapshot, keyed by the ``repository`` its input envelope carries (#446). It
# serves the input gate (``scripts/validate_metadata.py``, which checks the key is
# unique), the catch-all producer's skip set, the index producer's parent join (#486)
# and the post-run one-row-per-file check (#445), and each reads it through
# :func:`record_key`, never a hard-coded field, because the unique field differs by
# source:
#
# - AnVIL: ``file_id``, the repository's own durable identifier — unique on every
#   record and unchanged by a catalog re-index (#433), which is why the duplicate check
#   chose it. Not ``entry_id``, equally unique but regenerated per index: one key serves
#   every reader only if it is the durable one. Not ``file_name``, which identifies a
#   file only about 60% of the time there.
# - HPRC: ``file_md5sum``. The HPRC catalogs issue no file identifier and none is
#   minted — ``entry_id``, ``file_id`` and ``drs_uri`` are Azul's catalog identity and
#   stay null on an HPRC record. What the source does guarantee unique is the file's
#   URL, and ``scripts/classify_hprc_files.py`` writes its hash into ``file_md5sum``.
#   So this key is a hash of the full URL, not a content checksum: identical bytes at
#   two paths are two keys, and the value cannot be compared with a real md5.
SOURCE_RECORD_KEYS: dict[str, RecordKey] = {
    ANVIL_REPOSITORY: RecordKey(JOIN_KEY_FILE_ID, JOIN_KEY_FILE_ID),
    HPRC_REPOSITORY: RecordKey(JOIN_KEY_FILE_MD5SUM, OUTPUT_MD5SUM_FIELD),
}


def record_key(metadata: dict, input_path: Path) -> RecordKey:
    """The :data:`SOURCE_RECORD_KEYS` entry for the repository an input envelope names.

    Raises ``ValueError`` naming ``input_path`` when the envelope names no repository —
    an ``.ndjson`` input, or a JSON snapshot written before #424 added the field — or
    one the table does not declare. Unlike :func:`published_source`, this cannot be
    ``None``: a reader that needs the key cannot do its job without one, and guessing
    a field is how a file gets a second row.
    """
    repository = metadata.get("repository")
    key = SOURCE_RECORD_KEYS.get(repository) if isinstance(repository, str) else None
    if key is None:
        raise ValueError(
            f"{input_path}: the input envelope names repository {repository!r}, which declares no "
            f"record key — the field that identifies a file uniquely, which a run needs to know "
            f"which files are already classified and to check that no file has two rows. Declare "
            f'`"metadata": {{"repository": ...}}` as one of {sorted(SOURCE_RECORD_KEYS)} '
            f"(pipeline.SOURCE_RECORD_KEYS)."
        )
    return key


def is_key_value(value) -> TypeGuard[str]:
    """Whether ``value`` can serve as a record key: a non-empty string, nothing else."""
    return isinstance(value, str) and bool(value)


def keyed_rows(paths: Iterable[Path], key: RecordKey) -> Iterator[tuple[str, dict]]:
    """``(key value, row)`` for every row of the ``*_classifications.json`` files named.

    For a reader keyed on :data:`SOURCE_RECORD_KEYS` over another producer's output.
    The key is read under its output spelling. A row without it raises rather than
    being skipped, because a skip is silent: the caller sees one row fewer and cannot
    tell. How a row comes to lack it differs by source. AnVIL's ``file_id`` is
    deliberately *not* classifier-relevant (``records.ClassifierRecord``), so a drifted
    one reaches the valid stream and is echoed into a producer's row untouched;
    ``make validate-metadata`` rejects it before ``make classify``, so seeing one means
    that gate was bypassed. HPRC's key is the checksum field, which the shared load
    excludes when unusable (#376), so a row without one means the producer omitted the
    field.

    A path that is not a file yields nothing: a run writes only the producers that ran.
    The envelope's record list is read under ``classifications``, then a legacy
    ``results``, the precedence ``output_utils._records_in`` uses; unlike that tolerant
    reader, a file of any other shape — no list under either key, a bare list, a
    non-dict row — raises rather than reading as empty, since a reader keyed on identity
    cannot count a row it did not read.
    """
    for path in paths:
        if not path.is_file():
            continue
        with path.open() as f:
            data = json.load(f)
        rows = data.get("classifications", data.get("results")) if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError(
                f"{path}: not a classification file — no list under `classifications` (or the "
                f"legacy `results`); a reader keyed on identity cannot treat that as empty."
            )
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{path}: classification row is not an object: {row!r}")
            value = row.get(key.output_field)
            if not is_key_value(value):
                raise ValueError(
                    f"{path}: classification row for {row.get('file_name')!r} has "
                    f"{key.output_field} {value!r}; this reader keys on it and cannot skip the "
                    f"row. Either the input carried a drifted {key.input_field} that no gate "
                    f"refused, or the producer that wrote this file omitted the field and "
                    f"needs re-running."
                )
            yield value, row


def input_key_value(record: dict, key: RecordKey, purpose: str) -> str:
    """The source's key as an input record carries it, or a ``ValueError``.

    The input side of :func:`keyed_rows`: a producer that compares its input records
    against rows keyed that way. A drifted key here would match nothing, silently, so
    it raises instead. ``purpose`` completes "this producer keys on it to ..." in the
    message. The input gate rejects such a record before ``make classify``; reaching
    here means that gate was bypassed.
    """
    value = record.get(key.input_field)
    if not is_key_value(value):
        raise ValueError(
            f"input record for {record.get('file_name', '')!r} has {key.input_field} {value!r}; "
            f"this producer keys on it to {purpose}. `make validate-metadata` rejects this "
            f"before `make classify` runs."
        )
    return value


def repeated_key_values(records: list, key: RecordKey) -> dict[str, int]:
    """Values of the source's key that more than one input record carries, with counts.

    What the declaration in :data:`SOURCE_RECORD_KEYS` promises and this checks: the
    key is unique per file in the source's snapshot. Values that are not non-empty
    strings are not counted — the record contract reports those. Read by the input
    gate (``scripts/validate_metadata.py``), so a repeated key stops a run before it
    starts rather than failing it at the post-run one-row-per-file check (#445).
    """
    from collections import Counter

    counts = Counter(
        value
        for record in records
        if isinstance(record, dict)
        for value in (record.get(key.input_field),)
        if is_key_value(value)
    )
    return {value: n for value, n in counts.items() if n > 1}


# How much of an input file to read for its envelope: the metadata block of the AnVIL
# snapshot is a few kilobytes and the HPRC one a few bytes, so this is generous.
_ENVELOPE_HEAD = 1 << 20


def load_envelope(input_path: Path) -> dict:
    """An input file's ``metadata`` block without parsing its records.

    Both writers put the block first — ``azul_manifest.write_input_files`` emits the
    literal ``{"metadata": `` before it, and the HPRC builder's ``json.dump`` keeps that
    insertion order — so it decodes off the file's head alone. That is a writer detail,
    not a contract, so a file laid out any other way falls back to :func:`load_snapshot`
    and gives the same answer at the cost of the full parse. Worth having because one
    caller is the run's preflight, whose process lives for the whole run: a full parse
    there leaves the corpus's heap resident beside the producers for its duration, for
    two keys' worth of information. The other is the catch-all producer, which refuses
    an input on this before it loads the records.

    ``{}`` for an ``.ndjson`` input, which carries no envelope, decided by suffix rather
    than by parsing every line to find that out.
    """
    if input_path.suffix == ".ndjson":
        return {}
    prefix = '{"metadata": '
    with input_path.open() as f:
        head = f.read(_ENVELOPE_HEAD)
    if head.startswith(prefix):
        try:
            block, _ = json.JSONDecoder().raw_decode(head, len(prefix))
        except json.JSONDecodeError:
            block = None
        if isinstance(block, dict):
            return block
    return load_snapshot(input_path)[0]


def refuse_bad_published_shape(records: list[dict], input_path: Path, max_examples: int = 5) -> None:
    """Raise if any record's published values are not a list of strings, naming the offenders.

    The published dimensions are outside the input contract (#424 — they are not input),
    so ``validate_metadata`` passes them through unexamined. Without this, the first
    check is ``records.build_published``, which runs *per record inside a worker* — and
    ``_run_parallel`` catches every worker exception, counts it, and writes no row. A
    pre-#424 snapshot would therefore not be refused: every file it publishes a value
    for would silently vanish from the output while the run reported ``complete`` and
    exited 0, which is the failure mode #155 exists to prevent. Worse, it would differ
    by ``--workers``: the single-worker branch has no ``try``, so the same input crashes
    there and truncates at the ``-w 4`` / ``-w 10`` the Makefile uses.

    Checking here makes "refuse the snapshot" true for the records that would be
    classified: the run stops before any of them is fetched or written, and reports how
    many are bad rather than only the first. ``build_published``'s own guard stays as the
    constructor's backstop, for callers that did not come through this path.

    Deliberately *after* ``partition_records``, so it sees the classifiable records
    only. A record excluded for having no usable checksum (#376) produces no output row
    whatever its shape, and is named in ``excluded_files.json``, so a bad value on one
    can lose nothing — refusing a run over it would block a snapshot that classifies
    correctly. Checking before the split would also have to tolerate the non-dict
    elements the split removes. So this validates what will be classified, which is the
    scope that matters, and not the whole file.

    Both halves of the shape are checked — the outer list and its elements — because
    ``build_published`` refuses both, and anything it refuses that this lets through
    raises in a worker and loses the row, which is the failure this exists to close.

    A whole-list scan of a 708k-record corpus costs one pass over two keys per record,
    against a run measured in minutes.
    """
    bad: list[tuple[int, object, str, object, str]] = []
    for position, record in enumerate(records):
        for field in PUBLISHED_FIELDS:
            value = record.get(field)
            if value is None:
                continue
            if not isinstance(value, list):
                bad.append((position, record.get("entry_id"), field, value, f"is {type(value).__name__}, not a list"))
            elif not all(isinstance(element, str) for element in value):
                bad.append((position, record.get("entry_id"), field, value, "holds a non-string value"))
            elif not value:
                # `all([])` is True, so the emptiness test below is blind to this.
                bad.append((position, record.get("entry_id"), field, value, "is an empty list; absent is null"))
            elif not all(value):
                # `build_published` refuses this too, so letting it through here would
                # raise in a worker and lose the row — the failure this function exists
                # to close. The manifest reader never produces it: it drops empty
                # elements, so such a cell arrives as no published value at all.
                bad.append((position, record.get("entry_id"), field, value, "holds an empty value"))
    if not bad:
        return
    # Records, not entries: one record can be wrong on both fields, and calling that two
    # records would misreport how much of the snapshot is bad. Counted by position in the
    # list, not by ``entry_id`` — the input contract requires that to be non-empty but
    # not unique, so deduplicating on it would merge two distinct bad records (and merge
    # every record missing one, which all read as None).
    offenders = len({position for position, _, _, _, _ in bad})
    examples = "; ".join(
        f"record {position} ({entry_id}): {field}={value!r} ({why})"
        for position, entry_id, field, value, why in bad[:max_examples]
    )
    more = f" (+{len(bad) - max_examples:,} more)" if len(bad) > max_examples else ""
    # The pre-#424 hint belongs only to the scalar case, which is the shape a snapshot of
    # that vintage actually has. Offering "rebuild the snapshot" for a list holding a
    # non-string sends an operator at the wrong cause.
    hint = (
        " A snapshot built before #424 spells them as scalars; rebuild it with scripts/download_anvil_manifest.py."
        if any(why.endswith("not a list") for *_, why in bad)
        else ""
    )
    raise ValueError(
        f"{input_path}: {offenders:,} record(s), {len(bad):,} field(s), carry a published value this "
        f"cannot use — each must be a list of strings.{hint} Examples — {examples}{more}"
    )


class ClassifiableSnapshot(NamedTuple):
    """What :func:`load_classifiable_snapshot` resolves off an input file: the
    :func:`published_source` name and the classifiable records. Named, so a caller
    reads ``snapshot.source`` rather than counting tuple positions."""

    source: str | None
    records: list[dict]


def load_classifiable_snapshot(input_path: Path, run_dir: Path | None = None) -> ClassifiableSnapshot:
    """:func:`load_classifiable_records`, plus the repository the snapshot names.

    The form every classification producer calls. It returns the resolved repository name
    rather than only the raw envelope because that is what every caller wants from the
    envelope — and because returning the envelope alone made naming the repository a
    *second* line each producer had to remember, which is precisely the omission
    contract 7.7 exists to catch. Resolved here, a producer cannot forget it. The one
    other envelope fact a producer needs, the source's record key, is read through
    :func:`load_envelope` before this load, because resolving it is a refusal where no
    repository is named and that refusal belongs before the parse.

    Same single parse, same exclusion, same ``excluded_files.json`` write, and the same
    guarantee that every returned element is a ``dict``.

    The name is ``None`` for an ``.ndjson`` input, which carries no envelope, and for an
    envelope that names no catalog (see :func:`published_source`).
    """
    metadata, raw = load_snapshot(input_path)
    records, excluded = partition_records(raw)
    refuse_bad_published_shape(records, input_path)
    if run_dir is not None:
        write_excluded(run_dir, excluded, total_input=len(records) + len(excluded))
    if excluded:
        print(f"Excluded {len(excluded):,} record(s) with no usable file_md5sum (#376)")
    return ClassifiableSnapshot(published_source(metadata), records)


def load_classifiable_records(input_path: Path, run_dir: Path | None = None) -> list[dict]:
    """Load an input file's records, minus the ones excluded for having no checksum.

    The one place the #376 exclusion is applied to a file on disk, and the shared load
    path for every classification producer — the header pipeline and
    the four standalone scripts (images, auxiliary, index, remaining) — so a
    checksum-less record cannot reach any ``*_classifications.json`` (#376, AC1). The
    catch-all (``classify_remaining_files.py``) matters most here: it classifies every
    input record no earlier producer named, so excluding only in the header pipeline
    would relocate the problem into ``remaining_classifications.json`` rather than
    solve it.

    ``run_dir`` is the directory the caller is writing its output into. Given one, this
    also writes that run's ``excluded_files.json`` — so applying the exclusion and
    recording it are the same act, and a producer cannot shed a record without naming
    it. A standalone ``make classify-bam`` therefore records its exclusions exactly as
    a full run does. Every producer of a run writes the file, concurrently and with
    identical content; ``write_excluded`` documents why that is safe. ``None`` is for a
    caller with no run directory to write into (a test, an ad-hoc load).

    The ``validate_metadata`` gate deliberately does *not* call this — it reads
    :func:`load_records` unfiltered, or it could never report the very records it
    exists to report.

    Unlike :func:`load_records`, every element of the result is a ``dict``: a non-dict
    element cannot carry a checksum, so the exclusion removes it. That is why the
    producers downstream — the catch-all reads records with ``.get`` — no longer need
    to defend against one.

    The records half of :func:`load_classifiable_snapshot`, which is what every producer
    now calls — this narrower form has no production caller left and is kept for readers
    that genuinely want only the records (``test_producer_exclusions``). The two share
    one load path, so the exclusion cannot come to mean different things to different
    callers.
    """
    return load_classifiable_snapshot(input_path, run_dir).records


class RecordOutcome(NamedTuple):
    """The outcome of processing one record, tallied by ``_run_parallel``.

    ``result`` is the ``OutputRecord`` for this item (a record is only diverted to
    ``errored`` in ``_run_parallel`` by *raising*, which produces no ``RecordOutcome``).
    The three flags are mutually exclusive and only one, at most, is set:
    ``validation_failed`` (failed the input contract), ``was_cached`` (evidence already
    on disk), ``content_unreadable`` (fetch failed; the record is fully not_classified,
    #293), or none of these (a fresh fetch). Named so the four fields cannot be transposed
    at the unpack sites.
    """

    result: OutputRecord
    was_cached: bool
    content_unreadable: bool
    validation_failed: bool


def _fetch_and_classify(
    config: FileTypeConfig,
    evidence_dir: Path,
    md5sum: str,
    *,
    file_name: str,
    name: FileName,
    file_size: int | None,
    file_format: str | None,
    is_gzipped: bool,
    use_cache: bool,
    url: str | None = None,
) -> tuple[dict, bool]:
    """Fetch a file's content and classify it.

    Returns ``(classifications, content_unreadable)``:

    * content read        -> ``(classifications, False)``
    * content unreadable  -> ``(all-not_classified classifications, True)``, when the
      fetcher raised ``FetchError``; the file stays in the output as a fully
      ``not_classified`` row rather than vanishing (#155), asserting nothing about
      a file we could not read (#293).

    A fetcher signals failure by raising ``FetchError``, not by returning ``None``.
    An exception the fetcher does not wrap (e.g. a missing-tool ``FileNotFoundError``)
    propagates. Shared by ``ClassifyPipeline.classify_single`` and
    ``_process_single_record`` so the fallback cannot drift between the single-file
    and batch paths.

    ``file_name`` (the raw string) goes to the fetcher and the progress line; ``name``
    (the parsed :class:`FileName`, #242) goes to the classifiers, which read the
    extension and filename tokens from it without re-parsing.

    ``url`` is an optional explicit content URL (#276). When ``None`` (the AnVIL path)
    the fetcher derives its URL from ``md5sum`` (the S3 mirror); when supplied (HPRC)
    the fetcher streams from it instead. Every fetcher accepts ``url`` and defaults it
    to ``None``, so passing it unconditionally leaves the AnVIL path byte-for-byte.
    """
    try:
        raw_data = config.fetcher(
            evidence_dir,
            md5sum,
            file_name=file_name,
            is_gzipped=is_gzipped,
            use_cache=use_cache,
            head_detector=config.head_detector,
            url=url,
        )
    except FetchError as e:
        print(f"Content unreadable, classified as nothing — {file_name or md5sum}: {e.reason}")
        return classify_without_content(e.reason), True

    return config.classifier(
        raw_data,
        name=name,
        file_size=file_size,
        file_format=file_format,
    ), False


class NdjsonWriter:
    """Append-only NDJSON writer for real-time progress monitoring."""

    def __init__(self, output_path: Path):
        self.path = output_path.with_suffix(".ndjson")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w")
        self._count = 0

    def write(self, record: dict):
        self._fh.write(json.dumps(record) + "\n")
        self._count += 1
        if self._count % 500 == 0:
            self._fh.flush()

    def close(self):
        self._fh.flush()
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class ClassifyPipeline:
    """Unified pipeline for fetching headers, classifying, and writing output.

    Usage:
        pipeline = ClassifyPipeline(BAM_CONFIG, input_path, output_path)
        pipeline.run()
    """

    def __init__(
        self,
        config: FileTypeConfig,
        input_path: Path,
        output_path: Path,
        *,
        evidence_base: Path = Path("data/evidence/anvil"),
        limit: int | None = None,
        resume: bool = True,
        workers: int | None = None,
        skip_complete: bool = False,
        skip_cached: bool = False,
    ):
        self.config = config
        # Who this pipeline is in the run: the registry entry that routes records to
        # this type (#449), so `_filter_records` asks the same question every other
        # producer asks rather than a predicate of its own.
        self.producer = producer_for(config)
        self.input_path = input_path
        self.output_path = output_path
        self.evidence_dir = evidence_base / config.name
        self.limit = limit
        self.resume = resume
        self.workers = workers or 10
        self.skip_complete = skip_complete
        self.skip_cached = skip_cached
        # Set by _load_input from the input envelope, so it is known before the first
        # record is built. None until then, and None afterwards for an input that
        # named no catalog (see published_source).
        self.published_source: str | None = None

    def run(self) -> list[dict]:
        """Execute the full pipeline: load -> filter -> parse -> fetch+classify -> write.

        After routing, records are parsed into typed work items at the load boundary
        (#172): a ``ClassifierRecord`` per valid record and an ``InvalidRecord`` per
        record whose classifier-relevant fields violate the input contract (#161).
        Everything downstream reads typed attributes, not raw ``dict`` keys.
        """
        records = self._load_input()
        records = self._filter_records(records)

        if not records:
            print(f"No {self.config.name.upper()} files found matching extensions {self.config.extensions}")
            return []

        # Skip-complete only needs the record count, so it runs before parsing: on an
        # already-complete resume run this returns without validating any record.
        if self._should_skip_complete(records):
            return []

        work = self._partition_records(records)

        cached_md5s = self._print_cache_stats(work)

        if self.skip_cached and cached_md5s:
            # Only classifiable records can be cached, so only they are skip-filtered.
            # An InvalidRecord is never fetched or cached and must still be written as
            # validation_failed (#155/#161); it is kept unconditionally, which also
            # avoids hashing its raw (possibly unhashable) file_md5sum against the set.
            work = [w for w in work if isinstance(w, InvalidRecord) or w.file_md5sum not in cached_md5s]
            print(f"  Skipping cached files, processing only {len(work)} new files")

        if self.limit:
            work = work[: self.limit]
            print(f"Processing first {self.limit} files")

        if not work:
            return []

        # Best-effort fast-fail on a missing environment dependency (e.g. samtools
        # for BAM) before the pool starts, so it aborts once with a clear message
        # instead of every record failing to read and vanishing. Skipped when every
        # record is already cached (its evidence file was listed by
        # `cached_md5sums`), since a warm resume run serves from disk without the
        # tool. This is keyed on file existence, not evidence validity: a
        # corrupt/partial evidence file is listed yet the fetcher re-fetches — for
        # that case the per-record passthrough (bam's `FileNotFoundError`) is the
        # backstop, not this guard.
        will_fetch = any(
            not (self.resume and w.file_md5sum in cached_md5s) for w in work if isinstance(w, ClassifierRecord)
        )
        if self.config.preflight is not None and will_fetch:
            self.config.preflight()

        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        classifications = self._run_parallel(work)

        if self.config.summary_printer:
            self.config.summary_printer(classifications)

        return classifications

    @classmethod
    def classify_single(
        cls,
        config: "FileTypeConfig",
        md5sum: str,
        file_name: str = "",
        file_size: int | None = None,
        file_format: str | None = None,
        is_gzipped: bool = True,
        use_cache: bool = True,
        evidence_base: Path = Path("data/evidence/anvil"),
        url: str | None = None,
    ) -> dict:
        """Classify a single file by MD5. Does not require a full pipeline instance.

        Returns the canonical ``OutputRecord`` envelope (#204), the same shape the batch
        path writes; the catalog identity (:data:`records.CATALOG_IDENTITY_FIELDS`) and
        ``dataset_title`` are ``None`` here, since there is no source record to read
        either from.

        ``url`` is an optional explicit content URL (#276): ``None`` derives the URL
        from ``md5sum`` (AnVIL mirror), a value streams from it instead (HPRC).

        Never returns ``None`` (#155): a fetch failure surfaces as a ``FetchError``,
        which yields an all-``not_classified`` record (#293). It does not
        catch everything, though — an environment error (missing samtools raises
        ``FileNotFoundError``) or an unexpected exception from the fetcher/classifier
        propagates rather than returning a record.
        """
        evidence_dir = evidence_base / config.name
        evidence_dir.mkdir(parents=True, exist_ok=True)

        classifications, _unreadable = _fetch_and_classify(
            config,
            evidence_dir,
            md5sum,
            file_name=file_name,
            name=FileName.parse(file_name),
            file_size=file_size,
            file_format=file_format,
            is_gzipped=is_gzipped,
            use_cache=use_cache,
            url=url,
        )
        return OutputRecord.from_single(
            md5sum=md5sum,
            file_name=file_name,
            file_size=file_size,
            file_format=file_format,
            classifications=classifications,
        ).to_dict()

    # --- Internal ---

    def _load_input(self) -> list[dict]:
        """Load NDJSON or JSON input, minus the records excluded for having no checksum.

        Reads through the shared ``load_classifiable_snapshot`` (#376), so a record with
        no usable ``file_md5sum`` never reaches routing, validation, the evidence cache
        or a fetcher — and every element of the result is a ``dict``.

        The run directory is this pipeline's output directory, so the load also records
        what it excluded there — including on a standalone ``make classify-<type>`` run,
        which no orchestrator wraps.

        Reads the snapshot form so the input envelope is parsed in the same pass, and
        records which repository this run's ``published`` blocks came from (#424). That
        is a side effect on ``self``, done here because this is where the envelope is
        in hand and every record built afterwards needs the answer.
        """
        snapshot = load_classifiable_snapshot(self.input_path, self.output_path.parent)
        self.published_source = snapshot.source
        return snapshot.records

    def _filter_records(self, records: list) -> list[dict]:
        """Filter to the records this file type owns.

        Routing is :meth:`producers.Producer.claims`, the one predicate every producer
        asks, so this type takes a record exactly when no other producer does. A record
        with no usable ``file_md5sum`` never reaches here — ``_load_input`` excluded it
        (#376) and named it in the run's ``excluded_files.json``. A contract violation on
        any *other* classifier-relevant field does reach here and is written as
        ``validation_failed`` rather than silently dropped (#155/#161).

        ``skip`` stays this pipeline's own filter rather than the shared predicate's:
        routing answers who owns a file, and a marker saying not to process one is a
        different question. No other producer has ever honored it, so reading it here
        keeps every producer's behavior what it was.

        A non-dict element is routed nowhere, which is defense in depth rather than a live
        path: ``run()`` feeds this from ``_load_input``, whose elements are all dicts.
        """
        return [record for record in records if self.producer.claims(record) and not record.get("skip")]

    def _partition_records(self, records: list[dict]) -> list[ClassifierRecord | InvalidRecord]:
        """Parse routed records into typed work items at the load boundary (#172).

        Each record becomes either a ``ClassifierRecord`` (no classifier-relevant
        contract violation — it will be fetched and classified) or an
        ``InvalidRecord`` (a classifier-relevant field violates the input contract —
        diverted straight to a ``validation_failed`` row, never fetched, per #161).
        The split criterion is ``classification_blocking_reasons``, so a record that
        violates the contract only on a field the classifier never reads is *not*
        diverted here; that drift is surfaced by the whole-corpus ``validate_metadata``
        gate. Input order is preserved so the combined work list keeps the ordering
        the progress and ``limit`` steps assume.

        ``file_md5sum`` is one of the classifier-relevant fields, but a record bad on
        it can no longer reach this split: ``_load_input`` excludes it first (#376). So
        every item on both sides here carries a well-formed md5, and an
        ``InvalidRecord`` is always invalid on some *other* field.
        """
        work: list[ClassifierRecord | InvalidRecord] = []
        for record in records:
            reasons = classification_blocking_reasons(record)
            if reasons:
                work.append(InvalidRecord.from_record(record, reasons))
            else:
                work.append(ClassifierRecord.from_record(record))
        return work

    def _is_cached(self, md5sum) -> TypeGuard[str]:
        """Check if evidence is cached (cheap file-existence check, no JSON parse).

        Only a well-formed md5 (lowercase-hex, 32 chars) can key real cached
        evidence, and ``get_evidence_path`` builds a filesystem path from the md5
        (``md5sum[:2]`` / ``{md5sum}.json``). The type/format guard makes that path
        construction safe regardless of the caller: today every caller passes a
        ``ClassifierRecord``'s md5 (a valid md5 by construction, and one the #376
        exclusion already required at load), but the guard means a null, non-string,
        or non-md5 value simply returns False rather than building a bogus path.
        """
        if not isinstance(md5sum, str) or not MD5_RE.match(md5sum):
            return False
        from .evidence import get_evidence_path

        return get_evidence_path(self.evidence_dir, md5sum).exists()

    def _should_skip_complete(self, records: list[dict]) -> bool:
        """Check if output already has all files classified."""
        if not self.skip_complete or not self.output_path.exists():
            return False
        try:
            with self.output_path.open() as f:
                existing = json.load(f)
            existing_count = len(existing.get("classifications", []))
            if existing.get("metadata", {}).get("complete") and existing_count >= len(records):
                print(f"Output already complete with {existing_count} classifications. Skipping.")
                return True
        except (OSError, json.JSONDecodeError):
            pass
        return False

    def _print_cache_stats(self, work: list[ClassifierRecord | InvalidRecord]) -> set[str]:
        """Print how many files are already cached. Returns set of cached MD5s.

        Counts only the classifiable stream: an ``InvalidRecord`` is never fetched or
        header-inspected, so including it would inflate "files with MD5" and
        "Remaining to fetch". Every counted md5 is a ``ClassifierRecord``'s, a valid
        md5 by construction.
        """
        from .evidence import cached_md5sums

        name = self.config.name.upper()
        classifiable = [w for w in work if isinstance(w, ClassifierRecord)]
        print(f"Found {len(classifiable)} {name} files with MD5 for header inspection")
        # One walk of the cache, not one stat per file: this runs on the main thread
        # before the pool starts, so every second here is wall time (#488).
        cached_md5s = {w.file_md5sum for w in classifiable} & cached_md5sums(self.evidence_dir)
        print(f"  Already cached: {len(cached_md5s)}")
        print(f"  Remaining to fetch: {len(classifiable) - len(cached_md5s)}")
        return cached_md5s

    def _process_single_record(self, item: ClassifierRecord | InvalidRecord) -> RecordOutcome:
        """Fetch, classify, and build output for one parsed work item.

        An ``InvalidRecord`` (a classifier-relevant field violated the input
        contract, issue #161) is neither fetched nor classified: it is built with
        every dimension ``not_classified`` and its blocking reasons as evidence, and
        flagged ``validation_failed`` so the run tallies it. It is still written — a
        missing row is indistinguishable from a file that was never seen (issue
        #155). The valid/invalid split happened at the load boundary
        (``_partition_records``); a record that violates the contract only on a field
        the classifier does not read was never diverted, and drift on records
        ``_filter_records`` did not route is surfaced by the whole-corpus
        ``validate_metadata`` gate, not here.

        A record with no usable ``file_md5sum`` never reaches either branch: it was
        excluded at load (#376) and is named in the run's ``excluded_files.json``, so
        nothing here fetches it or probes the evidence cache for it.

        A ``ClassifierRecord`` reads typed attributes — ``file_md5sum`` is a valid
        md5 ``str``, ``file_name``/``file_format`` are ``str``, ``file_size`` an
        ``int`` — by construction, so this path carries no per-field type guards.

        ``content_unreadable`` is reported explicitly, as the boolean
        ``_fetch_and_classify`` returns on a ``FetchError``, rather than sniffed
        out of the output — detection must not depend on the shape of the
        classifications a fetch failure produces.
        """
        if isinstance(item, InvalidRecord):
            classifications = validation_failed_classifications(item.reasons)
            return RecordOutcome(
                self._build_record(item, classifications),
                was_cached=False,
                content_unreadable=False,
                validation_failed=True,
            )

        has_gz_ext = any(ext.endswith(".gz") for ext in self.config.extensions)
        # Lowercased for the same reason routing is: a `.VCF.GZ` reaches this reader, and
        # read as uncompressed its gzip bytes classify as nothing.
        is_gzipped = (
            (item.file_name.lower().endswith(".gz") or item.file_format.lower().endswith(".gz")) if has_gz_ext else True
        )

        was_cached = self.resume and self._is_cached(item.file_md5sum)

        classifications, content_unreadable = _fetch_and_classify(
            self.config,
            self.evidence_dir,
            item.file_md5sum,
            file_name=item.file_name,
            name=item.name,
            file_size=item.file_size,
            file_format=item.file_format,
            is_gzipped=is_gzipped,
            use_cache=self.resume,
            url=item.url,
        )
        if content_unreadable:
            # was_cached is a file-existence stat taken before the fetch. A fetcher
            # only raises after its own cache check missed, so it went to the
            # network: report was_cached=False, or a stale/corrupt evidence file
            # would count this record under "From cache" and hide it from the
            # unreadable tally.
            was_cached = False

        return RecordOutcome(
            self._build_record(item, classifications), was_cached, content_unreadable, validation_failed=False
        )

    def _build_record(self, item: ClassifierRecord | InvalidRecord, classifications: dict) -> OutputRecord:
        """Wrap a classifications dict in the typed output envelope.

        Reads identity off the typed work item (a ``ClassifierRecord`` on the success
        path, an ``InvalidRecord`` on the ``validation_failed`` path); ``OutputRecord``
        is serialized to the envelope dict at the NDJSON write boundary via
        ``to_dict``. The identity fields are echoed as the item carries them — typed on
        the success path, the raw (possibly drifted) values on the ``validation_failed``
        path — matching what ``classify_single`` writes for the single-file path (#204).

        An instance method rather than a static one because the ``published`` block names
        the repository it was read from, which is a fact about this run's input snapshot
        (#424) and so lives on the pipeline, not on the record.
        """
        return OutputRecord.from_work_item(item, classifications, source=self.published_source)

    def _run_parallel(self, work: list[ClassifierRecord | InvalidRecord]) -> list[dict]:
        """ThreadPoolExecutor with progress tracking, returns classifications."""
        successful = 0
        errored = 0  # worker raised: a cause was printed
        invalid = 0  # failed input validation: written, classified as nothing (#161)
        from_cache = 0
        processed = 0
        unreadable = 0
        lock = Lock()
        total = len(work)

        print(f"Using {self.workers} parallel workers")

        with NdjsonWriter(self.output_path) as writer:

            def update_progress(outcome: RecordOutcome, file_name: str):
                nonlocal successful, from_cache, processed, unreadable, invalid
                with lock:
                    processed += 1
                    writer.write(outcome.result.to_dict())
                    if outcome.validation_failed:
                        invalid += 1
                    else:
                        successful += 1
                        if outcome.was_cached:
                            from_cache += 1
                        elif outcome.content_unreadable:
                            unreadable += 1
                    cache_indicator = "[cached] " if outcome.was_cached else ""
                    # file_name is a str on both work streams (ClassifierRecord types it,
                    # InvalidRecord coerces it), so the slice cannot raise.
                    label = file_name[:45]
                    print(f"\r[{processed}/{total}] {cache_indicator}{label:<52}", end="", flush=True)

            if self.workers == 1:
                for item in work:
                    outcome = self._process_single_record(item)
                    update_progress(outcome, item.file_name)
            else:
                with ThreadPoolExecutor(max_workers=self.workers) as executor:
                    future_to_item = {executor.submit(self._process_single_record, item): item for item in work}
                    for future in as_completed(future_to_item):
                        item = future_to_item[future]
                        try:
                            outcome = future.result()
                            update_progress(outcome, item.file_name)
                        except Exception as e:
                            print(f"\nError processing {item.file_name}: {e}")
                            with lock:
                                processed += 1
                                errored += 1

        print(f"\n\nSuccessfully classified: {successful}")
        print(f"  From cache: {from_cache}")
        print(f"  New fetches: {successful - from_cache - unreadable}")
        print(f"  Content unreadable, classified as nothing: {unreadable}")
        if errored:
            print(f"Errored (cause printed above): {errored}")
        if invalid:
            print(f"Failed input validation (written, classified as nothing): {invalid}")
        classifications = self._save_final(
            total,
            successful,
            from_cache=from_cache,
            unreadable=unreadable,
            errored=errored,
            validation_failed=invalid,
        )

        print(f"\nSaved to {self.output_path}")
        print(f"Evidence cached in: {self.evidence_dir}/")

        return classifications

    def _save_final(
        self,
        total: int,
        successful: int,
        from_cache: int,
        unreadable: int,
        errored: int = 0,
        validation_failed: int = 0,
    ) -> list[dict]:
        """Write final JSON output from NDJSON progress file.

        ``unreadable`` is persisted alongside ``from_cache``: an all-not_classified
        record from a failed fetch is otherwise indistinguishable from one whose
        content was read but yielded no classification, so the count is the only
        signal that its dimensions are blank because the bytes were unreachable.

        The ``metadata`` block's derived tallies (``processed``, ``failed``,
        ``dropped``) are computed in :meth:`RunMetadata.from_counts`, which documents
        each invariant.
        """
        ndjson = self.output_path.with_suffix(".ndjson")
        classifications = []
        if ndjson.exists():
            with ndjson.open() as f:
                for line in f:
                    if line.strip():
                        classifications.append(json.loads(line))

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w") as f:
            json.dump(
                {
                    "metadata": RunMetadata.from_counts(
                        total=total,
                        successful=successful,
                        from_cache=from_cache,
                        content_unreadable=unreadable,
                        errored=errored,
                        validation_failed=validation_failed,
                    ).to_dict(),
                    "classifications": classifications,
                },
                f,
                indent=2,
            )

        if ndjson.exists():
            ndjson.unlink()
        return classifications
