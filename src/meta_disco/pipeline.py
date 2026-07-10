"""Shared classification pipeline infrastructure.

ClassifyPipeline replaces the duplicated process loops across the 4 header
classify scripts. Each file type is described by a FileTypeConfig dataclass
which carries extension filters, fetcher, classifier, and summary printer.
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Callable

from .fetchers import FetchError
from .header_classifier import classify_without_content
from .metadata_schema import validate_pipeline_records


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
) -> tuple[dict | None, bool]:
    """Fetch a file's content and classify it.

    Returns ``(classifications, content_unreadable)``. Three outcomes:

    * content read        -> ``(classifications, False)``
    * content unreadable  -> ``(filename-only classifications, True)``. The fetcher
      raised FetchError naming its cause, so the file stays in the output.
    * fetch returned None -> ``(None, False)``. No cause given, so the caller drops
      the record (see #155).

    Shared by ``ClassifyPipeline.classify_single`` and ``_process_single_record``
    so the fallback cannot drift between the single-file and batch paths.
    """
    try:
        raw_data = config.fetcher(
            evidence_dir, md5sum, file_name=file_name,
            is_gzipped=is_gzipped, use_cache=use_cache,
        )
    except FetchError as e:
        print(f"Content unreadable, classifying from filename — "
              f"{file_name or md5sum}: {e.reason}")
        return classify_without_content(
            e.reason, file_name=file_name, file_size=file_size,
            file_format=file_format,
            allowed_extensions=config.extensions,
            content_fields=config.content_fields,
        ), True

    if raw_data is None:
        return None, False

    return config.classifier(
        raw_data, file_name=file_name, file_size=file_size,
        file_format=file_format,
    ), False


class NdjsonWriter:
    """Append-only NDJSON writer for real-time progress monitoring."""

    def __init__(self, output_path: Path):
        self.path = output_path.with_suffix(".ndjson")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w")
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
        """Execute the full pipeline: load -> filter -> fetch+classify -> write."""
        records = self._load_input()
        records = self._filter_records(records)

        if not records:
            print(f"No {self.config.name.upper()} files found matching extensions {self.config.extensions}")
            return []

        if self._should_skip_complete(records):
            return []

        cached_md5s = self._print_cache_stats(records)

        if self.skip_cached and cached_md5s:
            records = [r for r in records
                       if r.get("file_md5sum") not in cached_md5s]
            print(f"  Skipping cached files, processing only {len(records)} new files")

        if self.limit:
            records = records[:self.limit]
            print(f"Processing first {self.limit} files")

        if not records:
            return []

        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        classifications = self._run_parallel(records)

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
    ) -> dict | None:
        """Classify a single file by MD5. Does not require a full pipeline instance."""
        evidence_dir = evidence_base / config.name
        evidence_dir.mkdir(parents=True, exist_ok=True)

        classifications, _unreadable = _fetch_and_classify(
            config, evidence_dir, md5sum,
            file_name=file_name, file_size=file_size, file_format=file_format,
            is_gzipped=is_gzipped, use_cache=use_cache,
        )
        if classifications is None:
            return None
        return {
            "file_name": file_name,
            "md5sum": md5sum,
            "file_size": file_size,
            "file_format": file_format,
            "classifications": classifications,
        }

    # --- Internal ---

    def _load_input(self) -> list[dict]:
        """Load NDJSON or JSON input, extract the records array, and validate it.

        Validates only the fields this pipeline reads (``validate_pipeline_records``),
        not the full AnVIL record: a derived input may legitimately carry a subset.
        Raises rather than dropping the offenders — a dropped record is
        indistinguishable from a file that was never seen (see #155).
        """
        with open(self.input_path) as f:
            if self.input_path.suffix == ".ndjson":
                records = [json.loads(line) for line in f if line.strip()]
            else:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise TypeError(
                        f"Expected JSON object with 'results' key, got {type(data).__name__}"
                    )
                records = data.get("results") or data.get("files")
                if records is None:
                    raise ValueError(
                        "JSON object must contain a 'results' or 'files' key"
                    )

        report = validate_pipeline_records(records)
        if not report.is_valid:
            raise ValueError(
                f"{self.input_path} holds records this pipeline cannot read.\n"
                f"{report.summary()}"
            )
        return records

    def _filter_records(self, records: list[dict]) -> list[dict]:
        """Filter to records matching file_type.extensions with valid MD5."""
        exts = self.config.extensions

        def matches(r: dict) -> bool:
            if not r.get("file_md5sum"):
                return False
            if r.get("skip"):
                return False
            fmt = r.get("file_format") or ""
            name = r.get("file_name") or ""
            return (any(fmt.endswith(ext) for ext in exts)
                    or any(name.endswith(ext) for ext in exts))

        return [r for r in records if matches(r)]

    def _is_cached(self, md5sum: str) -> bool:
        """Check if evidence is cached (cheap file-existence check, no JSON parse)."""
        from .fetchers import get_evidence_path
        return get_evidence_path(self.evidence_dir, md5sum).exists()

    def _should_skip_complete(self, records: list[dict]) -> bool:
        """Check if output already has all files classified."""
        if not self.skip_complete or not self.output_path.exists():
            return False
        try:
            with open(self.output_path) as f:
                existing = json.load(f)
            existing_count = len(existing.get("classifications", []))
            if existing.get("metadata", {}).get("complete") and existing_count >= len(records):
                print(f"Output already complete with {existing_count} classifications. Skipping.")
                return True
        except (json.JSONDecodeError, IOError):
            pass
        return False

    def _print_cache_stats(self, records: list[dict]) -> set[str]:
        """Print how many files are already cached. Returns set of cached MD5s."""
        name = self.config.name.upper()
        print(f"Found {len(records)} {name} files with MD5 for header inspection")
        cached_md5s = {r.get("file_md5sum") for r in records
                       if self._is_cached(r.get("file_md5sum"))}
        print(f"  Already cached: {len(cached_md5s)}")
        print(f"  Remaining to fetch: {len(records) - len(cached_md5s)}")
        return cached_md5s

    def _process_single_record(self, record: dict) -> tuple[dict | None, bool, bool]:
        """Fetch, classify, and build output for one record.

        Returns ``(record_or_None, was_cached, content_unreadable)``.

        ``content_unreadable`` is reported explicitly rather than sniffed out of
        the output: ``classify_without_content`` annotates only the dimensions
        this file type's *content* can determine, so a type whose
        ``content_fields`` is empty would leave no ``fetch_failed`` evidence at
        all. Detection must not depend on evidence that a config may not emit.
        """
        md5 = record.get("file_md5sum")
        file_name = record.get("file_name") or ""
        file_size = record.get("file_size")
        file_format = record.get("file_format") or ""

        has_gz_ext = any(ext.endswith(".gz") for ext in self.config.extensions)
        if has_gz_ext:
            is_gzipped = file_name.endswith(".gz") or file_format.endswith(".gz")
        else:
            is_gzipped = True

        was_cached = self.resume and self._is_cached(md5)

        classifications, content_unreadable = _fetch_and_classify(
            self.config, self.evidence_dir, md5,
            file_name=file_name, file_size=file_size, file_format=file_format,
            is_gzipped=is_gzipped, use_cache=self.resume,
        )
        if classifications is None:
            return None, was_cached, False

        if content_unreadable:
            # was_cached is a file-existence stat taken before the fetch. A fetcher
            # only raises after its own cache check missed, so it went to the
            # network: report was_cached=False, or a stale/corrupt evidence file
            # would count this record under "From cache" and hide it from the
            # unreadable tally.
            was_cached = False

        return self._build_record(record, classifications), was_cached, content_unreadable

    @staticmethod
    def _build_record(record: dict, classifications: dict) -> dict:
        """Wrap a classifications dict in the output record envelope."""
        return {
            "file_name": record.get("file_name") or "",
            "md5sum": record.get("file_md5sum"),
            "file_size": record.get("file_size"),
            "file_format": record.get("file_format") or "",
            "dataset_title": record.get("dataset_title"),
            "classifications": classifications,
            "entry_id": record.get("entry_id"),
        }

    def _run_parallel(self, records: list[dict]) -> list[dict]:
        """ThreadPoolExecutor with progress tracking, returns classifications."""
        successful = 0
        dropped = 0   # fetcher returned None: no cause given
        errored = 0   # worker raised: a cause was printed
        from_cache = 0
        processed = 0
        unreadable = 0
        lock = Lock()
        total = len(records)

        print(f"Using {self.workers} parallel workers")

        with NdjsonWriter(self.output_path) as writer:
            def update_progress(result, was_cached, content_unreadable, file_name):
                nonlocal successful, dropped, from_cache, processed, unreadable
                with lock:
                    processed += 1
                    if result:
                        writer.write(result)
                        successful += 1
                        if was_cached:
                            from_cache += 1
                        elif content_unreadable:
                            unreadable += 1
                    else:
                        dropped += 1
                    cache_indicator = "[cached] " if was_cached else ""
                    # `or ""`: a record may carry an explicit null file_name, and
                    # `.get(key, "")` returns None for a present-but-null key. Both
                    # callers normalize, but this print is the crash site — and in the
                    # parallel path a raise here would land in the executor's
                    # `except Exception`, discarding a record that classified fine.
                    label = (file_name or "")[:45]
                    print(f"\r[{processed}/{total}] {cache_indicator}{label:<52}",
                          end="", flush=True)

            if self.workers == 1:
                for record in records:
                    result, was_cached, content_unreadable = self._process_single_record(record)
                    update_progress(result, was_cached, content_unreadable,
                                    record.get("file_name") or "")
            else:
                with ThreadPoolExecutor(max_workers=self.workers) as executor:
                    future_to_record = {
                        executor.submit(self._process_single_record, record): record
                        for record in records
                    }
                    for future in as_completed(future_to_record):
                        record = future_to_record[future]
                        try:
                            result, was_cached, content_unreadable = future.result()
                            update_progress(result, was_cached, content_unreadable,
                                            record.get("file_name") or "")
                        except Exception as e:
                            print(f"\nError processing {record.get('file_name')}: {e}")
                            with lock:
                                processed += 1
                                errored += 1

        print(f"\n\nSuccessfully classified: {successful}")
        print(f"  From cache: {from_cache}")
        print(f"  New fetches: {successful - from_cache - unreadable}")
        print(f"  Content unreadable, classified from filename: {unreadable}")
        print(f"Dropped (fetcher gave no cause): {dropped}")
        if errored:
            print(f"Errored (cause printed above): {errored}")
        classifications = self._save_final(
            total, successful, dropped, from_cache, unreadable, errored)

        print(f"\nSaved to {self.output_path}")
        print(f"Evidence cached in: {self.evidence_dir}/")

        return classifications

    def _save_final(self, total: int, successful: int, dropped: int,
                    from_cache: int, unreadable: int, errored: int = 0) -> list[dict]:
        """Write final JSON output from NDJSON progress file.

        ``unreadable`` is persisted alongside ``from_cache``: a record classified
        from its filename after a failed fetch is otherwise indistinguishable from
        one whose content was read, because a file type whose ``content_fields``
        is empty leaves no ``fetch_failed`` evidence behind.

        ``dropped`` (the fetcher returned None, giving no cause) and ``errored``
        (a worker raised, and the cause was printed) are recorded separately, and
        ``failed`` is kept as their sum so existing consumers of that key still
        read the total number of records that produced no row.
        """
        ndjson = self.output_path.with_suffix(".ndjson")
        classifications = []
        if ndjson.exists():
            with open(ndjson) as f:
                for line in f:
                    if line.strip():
                        classifications.append(json.loads(line))

        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, "w") as f:
            json.dump({
                "metadata": {
                    "total_to_process": total,
                    "processed": successful + dropped + errored,
                    "successful": successful,
                    # `failed` = every record that produced no row, whether the
                    # fetcher gave no cause (dropped) or a worker raised (errored).
                    "failed": dropped + errored,
                    "dropped": dropped,
                    "errored": errored,
                    "from_cache": from_cache,
                    "content_unreadable": unreadable,
                    "complete": True,
                },
                "classifications": classifications,
            }, f, indent=2)

        if ndjson.exists():
            ndjson.unlink()
        return classifications
