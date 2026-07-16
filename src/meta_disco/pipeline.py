"""Shared classification pipeline infrastructure.

ClassifyPipeline replaces the duplicated process loops across the 4 header
classify scripts. Each file type is described by a FileTypeConfig dataclass
which carries extension filters, fetcher, classifier, and summary printer.
"""

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import NamedTuple, TypeGuard

from .fetchers import FetchError
from .header_classifier import classify_without_content
from .metadata_schema import (
    classification_blocking_reasons,
    validation_failed_classifications,
)
from .records import ClassifierRecord, InvalidRecord

# A well-formed md5: lowercase hex, 32 chars — the same shape the input contract
# (metadata.yaml file_md5sum) requires. Only such a value can key real cached
# evidence; anything else is headed to validation_failed.
_MD5_RE = re.compile(r"^[0-9a-f]{32}$")


def load_records(input_path: Path) -> list:
    """Load the record list from an input file's envelope.

    Elements are not guaranteed to be dicts — an NDJSON line or a JSON array entry
    may be any JSON value; ``_filter_records`` tolerates non-dicts. Hence ``list``,
    not ``list[dict]``.

    A ``.ndjson`` file is one record per line; otherwise a JSON object with a
    ``files`` (or legacy ``results``) list. Shared by ``ClassifyPipeline`` and the
    ``validate_metadata`` gate so the envelope handling lives in one place.
    """
    with input_path.open() as f:
        if input_path.suffix == ".ndjson":
            return [json.loads(line) for line in f if line.strip()]
        data = json.load(f)
    if not isinstance(data, dict):
        raise TypeError(f"Expected JSON object with 'results' or 'files' key, got {type(data).__name__}")
    # Check key presence explicitly rather than `results or files`: a present but
    # empty `results: []` is a valid empty corpus, not a missing key — the truthy
    # fallback would misreport it as "must contain a key".
    for key in ("results", "files"):
        if key in data:
            records = data[key]
            if not isinstance(records, list):
                raise TypeError(f"'{key}' must be a list of records, got {type(records).__name__}")
            return records
    raise ValueError("JSON object must contain a 'results' or 'files' key")


class RecordOutcome(NamedTuple):
    """The outcome of processing one record, tallied by ``_run_parallel``.

    ``result`` is always the output record — every record produces a row now that
    fetchers raise ``FetchError`` instead of returning ``None`` (#155). The three
    flags are mutually exclusive and only one, at most, is set: a record is written
    as ``validation_failed`` (failed the input contract), ``was_cached`` (evidence
    already on disk), ``content_unreadable`` (fetch failed, classified from the
    filename), or none of these (a fresh fetch). Named so the four fields cannot be
    transposed at the unpack sites.
    """

    result: dict
    was_cached: bool
    content_unreadable: bool
    validation_failed: bool


@dataclass(frozen=True)
class FileTypeConfig:
    """Configuration for a file type that can be classified via header inspection."""

    name: str
    extensions: tuple[str, ...]
    fetcher: Callable
    classifier: Callable
    summary_printer: Callable | None = None
    # Dimensions this file type's *content* can determine. Used to attribute a
    # fetch failure to the answers the unread bytes would have informed — never
    # to dimensions only the filename can supply.
    content_fields: tuple[str, ...] = ()
    # Environment check run once before the worker pool (e.g. an external tool
    # must be installed). Raises to abort the run fast, instead of letting every
    # record fail the same way and vanish. None means no check.
    preflight: Callable | None = None


def _fetch_and_classify(
    config: FileTypeConfig,
    evidence_dir: Path,
    md5sum: str,
    *,
    file_name: str,
    file_size: int | None,
    file_format: str | None,
    is_gzipped: bool,
    use_cache: bool,
) -> tuple[dict, bool]:
    """Fetch a file's content and classify it.

    Returns ``(classifications, content_unreadable)``. Two outcomes:

    * content read        -> ``(classifications, False)``
    * content unreadable  -> ``(filename-only classifications, True)``. The fetcher
      raised FetchError naming its cause, so the file stays in the output as a
      ``not_classified`` row rather than vanishing (#155).

    Every record therefore yields a row — a fetcher signals failure by raising, never
    by returning ``None``. Shared by ``ClassifyPipeline.classify_single`` and
    ``_process_single_record`` so the fallback cannot drift between the single-file
    and batch paths.
    """
    try:
        raw_data = config.fetcher(
            evidence_dir,
            md5sum,
            file_name=file_name,
            is_gzipped=is_gzipped,
            use_cache=use_cache,
        )
    except FetchError as e:
        print(f"Content unreadable, classifying from filename — {file_name or md5sum}: {e.reason}")
        return classify_without_content(
            e.reason,
            file_name=file_name,
            file_size=file_size,
            file_format=file_format,
            allowed_extensions=config.extensions,
            content_fields=config.content_fields,
        ), True

    return config.classifier(
        raw_data,
        file_name=file_name,
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
        self.input_path = input_path
        self.output_path = output_path
        self.evidence_dir = evidence_base / config.name
        self.limit = limit
        self.resume = resume
        self.workers = workers or 10
        self.skip_complete = skip_complete
        self.skip_cached = skip_cached

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

        # Fail fast on a missing environment dependency (e.g. samtools for BAM)
        # before the pool starts, so it aborts once with a clear message instead of
        # every record failing to read and vanishing.
        if self.config.preflight is not None:
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
    ) -> dict:
        """Classify a single file by MD5. Does not require a full pipeline instance.

        Always returns a record: a fetch failure yields filename-only
        ``not_classified`` classifications (the fetcher raises ``FetchError``), never
        ``None`` (#155).
        """
        evidence_dir = evidence_base / config.name
        evidence_dir.mkdir(parents=True, exist_ok=True)

        classifications, _unreadable = _fetch_and_classify(
            config,
            evidence_dir,
            md5sum,
            file_name=file_name,
            file_size=file_size,
            file_format=file_format,
            is_gzipped=is_gzipped,
            use_cache=use_cache,
        )
        return {
            "file_name": file_name,
            "md5sum": md5sum,
            "file_size": file_size,
            "file_format": file_format,
            "classifications": classifications,
        }

    # --- Internal ---

    def _load_input(self) -> list:
        """Load NDJSON or JSON input, extracting the records array (elements may be
        non-dict; see ``load_records``)."""
        return load_records(self.input_path)

    def _filter_records(self, records: list) -> list[dict]:
        """Filter to records routed to this file type by extension.

        Routing is by ``file_format``/``file_name`` extension only. A missing or
        invalid ``file_md5sum`` is *not* filtered out: md5 is classifier-relevant, so
        such a record reaches ``_process_single_record`` and is written as
        ``validation_failed`` rather than silently dropped (issues #155/#161). A
        non-dict element cannot be routed by extension and cannot crash the filter;
        the whole-corpus ``validate_metadata`` gate reports it.
        """
        exts = self.config.extensions

        def matches(r) -> bool:
            if not isinstance(r, dict):
                return False
            if r.get("skip"):
                return False
            # str(): a non-string file_format/file_name (drift) must not raise here,
            # before validation can convert the record into a structured failure.
            fmt = str(r.get("file_format") or "")
            name = str(r.get("file_name") or "")
            return any(fmt.endswith(ext) for ext in exts) or any(name.endswith(ext) for ext in exts)

        return [r for r in records if matches(r)]

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
        ``ClassifierRecord``'s md5 (a valid md5 by construction), but the guard means
        a null, non-string, or non-md5 value simply returns False rather than
        building a bogus path.
        """
        if not isinstance(md5sum, str) or not _MD5_RE.match(md5sum):
            return False
        from .fetchers import get_evidence_path

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
        name = self.config.name.upper()
        classifiable = [w for w in work if isinstance(w, ClassifierRecord)]
        print(f"Found {len(classifiable)} {name} files with MD5 for header inspection")
        cached_md5s = {w.file_md5sum for w in classifiable if self._is_cached(w.file_md5sum)}
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

        A ``ClassifierRecord`` reads typed attributes — ``file_md5sum`` is a valid
        md5 ``str``, ``file_name``/``file_format`` are ``str``, ``file_size`` an
        ``int`` — by construction, so this path carries no per-field type guards.

        ``content_unreadable`` is reported explicitly rather than sniffed out of
        the output: ``classify_without_content`` annotates only the dimensions
        this file type's *content* can determine, so a type whose
        ``content_fields`` is empty would leave no ``fetch_failed`` evidence at
        all. Detection must not depend on evidence that a config may not emit.
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
        is_gzipped = (item.file_name.endswith(".gz") or item.file_format.endswith(".gz")) if has_gz_ext else True

        was_cached = self.resume and self._is_cached(item.file_md5sum)

        classifications, content_unreadable = _fetch_and_classify(
            self.config,
            self.evidence_dir,
            item.file_md5sum,
            file_name=item.file_name,
            file_size=item.file_size,
            file_format=item.file_format,
            is_gzipped=is_gzipped,
            use_cache=self.resume,
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

    @staticmethod
    def _build_record(item: ClassifierRecord | InvalidRecord, classifications: dict) -> dict:
        """Wrap a classifications dict in the output record envelope.

        Reads identity off the typed work item (a ``ClassifierRecord`` on the success
        path, an ``InvalidRecord`` on the ``validation_failed`` path). Both guarantee
        ``file_name``/``file_format`` are ``str`` — the two fields downstream
        consumers do string operations on (path building, extension checks) — so no
        coercion happens here. The other identity fields are echoed as the item
        carries them: typed on the success path, the raw (possibly drifted) values on
        the ``validation_failed`` path.
        """
        return {
            "file_name": item.file_name,
            "md5sum": item.file_md5sum,
            "file_size": item.file_size,
            "file_format": item.file_format,
            "dataset_title": item.dataset_title,
            "classifications": classifications,
            "entry_id": item.entry_id,
        }

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
                    writer.write(outcome.result)
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
        print(f"  Content unreadable, classified from filename: {unreadable}")
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

        ``unreadable`` is persisted alongside ``from_cache``: a record classified
        from its filename after a failed fetch is otherwise indistinguishable from
        one whose content was read, because a file type whose ``content_fields``
        is empty leaves no ``fetch_failed`` evidence behind.

        ``errored`` (a worker raised, and the cause was printed) is the only way a
        record now produces no row, so ``failed`` equals it. ``dropped`` is retired —
        a fetch failure is written as a ``content_unreadable`` row, never dropped
        (#155) — but the key is still emitted as ``0`` for output-schema stability.

        ``validation_failed`` (the record failed the input contract, issue #161)
        produced a row — every dimension ``not_classified`` — so it is counted
        neither in ``successful`` nor in ``failed``; it is persisted on its own key.
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
                    "metadata": {
                        "total_to_process": total,
                        "processed": successful + errored + validation_failed,
                        "successful": successful,
                        # `failed` = every record that produced no row. A fetch failure
                        # no longer drops a record (#155), so only a raising worker
                        # (errored) does. `dropped` stays as a constant 0 for consumers.
                        "failed": errored,
                        "dropped": 0,
                        "errored": errored,
                        "validation_failed": validation_failed,
                        "from_cache": from_cache,
                        "content_unreadable": unreadable,
                        "complete": True,
                    },
                    "classifications": classifications,
                },
                f,
                indent=2,
            )

        if ndjson.exists():
            ndjson.unlink()
        return classifications
