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


@dataclass(frozen=True)
class FileTypeConfig:
    """Configuration for a file type that can be classified via header inspection."""

    name: str
    extensions: tuple[str, ...]
    fetcher: Callable
    classifier: Callable
    summary_printer: Callable | None = None


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
        evidence_base: Path = Path("data/evidence"),
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
        evidence_base: Path = Path("data/evidence"),
    ) -> dict | None:
        """Classify a single file by MD5. Does not require a full pipeline instance."""
        evidence_dir = evidence_base / config.name
        evidence_dir.mkdir(parents=True, exist_ok=True)

        raw_data = config.fetcher(
            evidence_dir, md5sum, file_name=file_name,
            is_gzipped=is_gzipped, use_cache=use_cache,
        )
        if raw_data is None:
            return None

        classifications = config.classifier(
            raw_data, file_name=file_name, file_size=file_size,
            file_format=file_format,
        )
        return {
            "file_name": file_name,
            "md5sum": md5sum,
            "file_size": file_size,
            "file_format": file_format,
            "classifications": classifications,
        }

    # --- Internal ---

    def _load_input(self) -> list[dict]:
        """Load NDJSON or JSON input, extracting records array."""
        with open(self.input_path) as f:
            if self.input_path.suffix == ".ndjson":
                return [json.loads(line) for line in f if line.strip()]
            data = json.load(f)
            if not isinstance(data, dict):
                raise TypeError(
                    f"Expected JSON object with 'results' key, got {type(data).__name__}"
                )
            return data.get("results", data.get("files", data))

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

    def _process_single_record(self, record: dict) -> tuple[dict | None, bool]:
        """Fetch, classify, and build output for one record."""
        md5 = record.get("file_md5sum")
        file_name = record.get("file_name") or ""
        file_size = record.get("file_size")
        file_format = record.get("file_format") or ""
        entry_id = record.get("entry_id")

        has_gz_ext = any(ext.endswith(".gz") for ext in self.config.extensions)
        if has_gz_ext:
            is_gzipped = file_name.endswith(".gz") or file_format.endswith(".gz")
        else:
            is_gzipped = True

        was_cached = self.resume and self._is_cached(md5)

        raw_data = self.config.fetcher(
            self.evidence_dir, md5, file_name=file_name,
            is_gzipped=is_gzipped, use_cache=self.resume,
        )
        if raw_data is None:
            return None, was_cached

        classifications = self.config.classifier(
            raw_data, file_name=file_name, file_size=file_size,
            file_format=file_format,
        )

        result = {
            "file_name": file_name,
            "md5sum": md5,
            "file_size": file_size,
            "file_format": file_format,
            "classifications": classifications,
            "entry_id": entry_id,
            "original_record": {
                "file_format": file_format,
                "file_size": file_size,
                "dataset_title": record.get("dataset_title"),
            },
            "from_cache": was_cached,
        }
        return result, was_cached

    def _run_parallel(self, records: list[dict]) -> list[dict]:
        """ThreadPoolExecutor with progress tracking, returns classifications."""
        writer = NdjsonWriter(self.output_path)
        successful = 0
        failed = 0
        from_cache = 0
        processed = 0
        lock = Lock()
        total = len(records)

        print(f"Using {self.workers} parallel workers")

        def update_progress(result, was_cached, file_name):
            nonlocal successful, failed, from_cache, processed
            with lock:
                processed += 1
                if result:
                    writer.write(result)
                    successful += 1
                    if was_cached:
                        from_cache += 1
                else:
                    failed += 1
                cache_indicator = "[cached] " if was_cached else ""
                print(f"\r[{processed}/{total}] {cache_indicator}{file_name[:45]:<52}",
                      end="", flush=True)

        if self.workers == 1:
            for record in records:
                result, was_cached = self._process_single_record(record)
                update_progress(result, was_cached, record.get("file_name", ""))
        else:
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                future_to_record = {
                    executor.submit(self._process_single_record, record): record
                    for record in records
                }
                for future in as_completed(future_to_record):
                    record = future_to_record[future]
                    try:
                        result, was_cached = future.result()
                        update_progress(result, was_cached, record.get("file_name", ""))
                    except Exception as e:
                        print(f"\nError processing {record.get('file_name')}: {e}")
                        with lock:
                            processed += 1
                            failed += 1

        print(f"\n\nSuccessfully classified: {successful}")
        print(f"  From cache: {from_cache}")
        print(f"  New fetches: {successful - from_cache}")
        print(f"Failed to fetch header: {failed}")

        writer.close()
        classifications = self._save_final(total, successful, failed, from_cache)

        print(f"\nSaved to {self.output_path}")
        print(f"Evidence cached in: {self.evidence_dir}/")

        return classifications

    def _save_final(self, total: int, successful: int, failed: int, from_cache: int) -> list[dict]:
        """Write final JSON output from NDJSON progress file."""
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
                    "processed": successful + failed,
                    "successful": successful,
                    "failed": failed,
                    "from_cache": from_cache,
                    "complete": True,
                },
                "classifications": classifications,
            }, f, indent=2)

        if ndjson.exists():
            ndjson.unlink()
        return classifications
