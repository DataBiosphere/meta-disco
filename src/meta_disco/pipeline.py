"""Shared classification pipeline infrastructure.

ClassifyPipeline replaces the duplicated process loops across the 4 header
classify scripts. Each file type is described by a FileTypeConfig dataclass
which carries extension filters, fetcher, classifier, and summary printer.
"""

import json
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Any, NamedTuple, TypeGuard

from .exclusions import MD5_RE, partition_records, write_excluded
from .fetchers import FetchError
from .file_name import FileName
from .file_types import FileTypeConfig
from .header_classifier import classify_without_content
from .inputs import load_envelope, load_records
from .metadata_schema import (
    classification_blocking_reasons,
    validation_failed_classifications,
)
from .producers import producer_for
from .record_keys import record_key
from .records import (
    STEP_OUTCOMES_KEY,
    ClassifierRecord,
    InvalidRecord,
    OutputRecord,
    RunMetadata,
)


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
    :func:`inputs.load_snapshot` unfiltered, or it could never report the very records it
    exists to report.

    Unlike :func:`inputs.load_records`, every element of the result is a ``dict``: a non-dict
    element cannot carry a checksum, so the exclusion removes it. That is why the
    producers downstream — the catch-all reads records with ``.get`` — no longer need
    to defend against one.

    The index and catch-all producers also need the source's record key, an envelope
    fact; they read it through :func:`inputs.load_envelope` before this load, because resolving
    it is a refusal where no repository is named and that refusal belongs before the
    parse.
    """
    raw = load_records(input_path)
    records, excluded = partition_records(raw)
    if run_dir is not None:
        write_excluded(run_dir, excluded, total_input=len(records) + len(excluded))
    if excluded:
        print(f"Excluded {len(excluded):,} record(s) with no usable file_md5sum (#376)")
    return records


class RecordOutcome(NamedTuple):
    """The outcome of processing one record, tallied by ``_run_parallel``.

    ``result`` is the ``OutputRecord`` for this item (a record is only diverted to
    ``errored`` in ``_run_parallel`` by *raising*, which produces no ``RecordOutcome``).
    The three flags are mutually exclusive and only one, at most, is set:
    ``validation_failed`` (failed the input contract), ``was_cached`` (evidence already
    on disk), ``content_unreadable`` (fetch failed; the record is fully not_classified,
    #293), or none of these (a fresh fetch). Named so the fields cannot be transposed
    at the unpack sites.
    """

    result: OutputRecord
    was_cached: bool
    content_unreadable: bool
    validation_failed: bool
    # Why the file got the step it did, or none, where its type states one
    # (``FileTypeConfig.step``, #609); None for every other type and for a file not read.
    step_outcome: str | None = None


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
) -> tuple[dict, bool, Any]:
    """Fetch a file's content and classify it.

    Returns ``(classifications, content_unreadable, payload)``, ``payload`` being what
    the classifier read — the fetcher's payload, or its parse for a type with a
    ``FileTypeConfig.parser``, made once here (#615) — for a type that reads more from it
    (``FileTypeConfig.step``):

    * content read        -> ``(classifications, False, payload)``
    * content unreadable  -> ``(all-not_classified classifications, True, None)``, when the
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
        return classify_without_content(e.reason), True, None

    content = raw_data if config.parser is None else config.parser(raw_data)
    classifications = config.classifier(content, name=name, file_size=file_size, file_format=file_format)
    return classifications, False, content


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
        # The per-file step reader of a type that states one (``FileTypeConfig.step``,
        # #609), built by ``run`` from the whole input, not this type's share of it — a
        # VCF's parent is a CRAM. None for every other type.
        self._step: Callable | None = None

    def run(self) -> list[dict]:
        """Execute the full pipeline: load -> filter -> parse -> fetch+classify -> write.

        After routing, records are parsed into typed work items at the load boundary
        (#172): a ``ClassifierRecord`` per valid record and an ``InvalidRecord`` per
        record whose classifier-relevant fields violate the input contract (#161).
        Everything downstream reads typed attributes, not raw ``dict`` keys.
        """
        # A type that states a step needs the source's record key, which the input's envelope
        # names: refused here, before any work, where the envelope names none (an `.ndjson`
        # input), as the index producer and the catch-all refuse it.
        key = record_key(load_envelope(self.input_path), self.input_path) if self.config.step is not None else None
        loaded = self._load_input()
        records = self._filter_records(loaded)

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

        if self.config.step is not None:
            self._step = self.config.step(loaded, key)
        # The step reader keeps what it needs of the input; the rest need not outlive the load.
        del loaded

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

        classifications, _unreadable, _payload = _fetch_and_classify(
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

        Reads through the shared ``load_classifiable_records`` (#376), so a record with
        no usable ``file_md5sum`` never reaches routing, validation, the evidence cache
        or a fetcher — and every element of the result is a ``dict``.

        The run directory is this pipeline's output directory, so the load also records
        what it excluded there — including on a standalone ``make classify-<type>`` run,
        which no orchestrator wraps.
        """
        return load_classifiable_records(self.input_path, self.output_path.parent)

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
                OutputRecord.from_work_item(item, classifications),
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

        classifications, content_unreadable, payload = _fetch_and_classify(
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

        generated_by, step_outcome = None, None
        if self._step is not None and not content_unreadable:
            generated_by, step_outcome = self._step(payload, item.file_name, item.dataset_id)
        return RecordOutcome(
            OutputRecord.from_work_item(item, classifications, generated_by=generated_by),
            was_cached,
            content_unreadable,
            validation_failed=False,
            step_outcome=step_outcome,
        )

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
        # Per dataset, each outcome's files, for a type that states a step (#609).
        step_counts: dict[str, Counter] = defaultdict(Counter)

        print(f"Using {self.workers} parallel workers")

        with NdjsonWriter(self.output_path) as writer:

            def update_progress(outcome: RecordOutcome, file_name: str):
                nonlocal successful, from_cache, processed, unreadable, invalid
                with lock:
                    processed += 1
                    writer.write(outcome.result.to_dict())
                    if outcome.step_outcome is not None:
                        # As reconcile names a record with no title: "" (HPRC has none).
                        step_counts[str(outcome.result.dataset_title or "")][outcome.step_outcome] += 1
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
        details = None
        if self._step is not None:
            details = {STEP_OUTCOMES_KEY: {dataset: dict(counts) for dataset, counts in sorted(step_counts.items())}}
            for dataset, counts in details[STEP_OUTCOMES_KEY].items():
                print(f"  Producer steps, {dataset}: {', '.join(f'{k} {v:,}' for k, v in counts.items())}")
        classifications = self._save_final(
            total,
            successful,
            from_cache=from_cache,
            unreadable=unreadable,
            errored=errored,
            validation_failed=invalid,
            details=details,
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
        details: dict | None = None,
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
                        details=details,
                    ).to_dict(),
                    "classifications": classifications,
                },
                f,
                indent=2,
            )

        if ndjson.exists():
            ndjson.unlink()
        return classifications
