"""The single classification run — shared by every source.

A source (AnVIL, HPRC, …) maps its native metadata into the meta-disco record shape and
calls :func:`run_all_classifications`; there is no per-source classifier. This module holds
the orchestration — Phase 1 (the nine producers that route on their own), Phase 2
(index inheritance), Phase 3 (the remaining catch-all). Which producers those are, and
how each is invoked, is declared in :mod:`meta_disco.producers`. ``scripts/rerun_all_classifications.py``
(AnVIL) and ``scripts/classify_hprc_files.py`` (HPRC) are thin CLI wrappers over it, so the
shared path lives in the package alongside the rest of the pipeline rather than being
imported across scripts.
"""

import heapq
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from meta_disco.exclusions import EXCLUDED_FILE, read_excluded
from meta_disco.output_utils import row_identities
from meta_disco.pipeline import PUBLISHED_TABLES, RecordKey, load_envelope, record_key
from meta_disco.producers import PRODUCERS, output_paths, producers_in_phase, validate_registry
from meta_disco.source_evidence import (
    DEFAULT_SOURCE_EVIDENCE_ROOT,
    refuse_second_published_source,
    report_evidence_files,
)

# This module is <root>/src/meta_disco/classify_run.py; the classifier scripts it shells
# out to live at <root>/scripts/, so the subprocess cwd is the repo root three levels up.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def build_parallel_jobs(
    metadata: Path, output_dir: Path, evidence_base: Path, workers: int | None = None
) -> list[tuple]:
    """Phase 1 jobs: one per producer that runs in Phase 1.

    Derived from the producer registry rather than hand-listed, so registering a producer
    cannot silently skip production. That is what happened to `gfa` in #151: registered
    and invoked by nothing, so graph files fell through to the filename-only catch-all.

    ``evidence_base`` is the per-source header cache root and ``workers`` (when set) the
    header-fetch concurrency; both go only to the producers that fetch headers
    (``Producer.fetches_headers``) — the rest classify from the filename.
    """
    header_args = ["--evidence-base", str(evidence_base)]
    if workers is not None:
        header_args += ["-w", str(workers)]
    jobs = []
    for producer in producers_in_phase(1):
        if producer.fetches_headers:
            args = ["--type", producer.name, "--input", str(metadata), *header_args]
        else:
            args = ["--metadata", str(metadata)]
        jobs.append((producer.script, output_dir / producer.output, args))
    return jobs


def run_script(script_name: str, output_path: Path, extra_args: list[str] | None = None):
    """Run a classification script."""
    cmd = [sys.executable, f"scripts/{script_name}", "--output", str(output_path)]
    if extra_args:
        cmd.extend(extra_args)

    print(f"  Starting: {script_name}")

    result = subprocess.run(cmd, cwd=_REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {script_name} failed with code {result.returncode}")
        if result.stderr:
            print(f"  stderr: {result.stderr[-500:]}")
        return script_name, False
    print(f"  Done: {script_name}")
    return script_name, True


def _report_exclusions(output_dir: Path) -> int | None:
    """Print what the run's producers recorded as excluded; return that count.

    Returns ``None`` when the count is not known — no file, or one that could not be
    read — rather than a zero or a recovered subset that a caller could mistake for the
    real figure. The value comes from :attr:`ExcludedIndex.count`, the single derivation
    shared with the report, so the console and the markdown cannot disagree.

    Reads rather than recomputes. Each producer writes ``excluded_files.json`` as it
    loads (``pipeline.load_classifiable_snapshot``), which is what makes the record
    unconditional — a standalone ``make classify-<type>`` records its exclusions too,
    with no orchestrator involved. So the orchestrator's job here is only to surface the
    number: ``run_script`` captures each producer's stdout and prints it only on failure,
    so without this a full run would never show it.

    A missing file leaves the count unknown, which is worth saying rather than reporting
    zero — as does a file that cannot be read. Neither is the same fact as "this run
    excluded nothing". In a full run the likeliest cause of absence is that every Phase 1
    job failed before loading its input, but the directory alone cannot establish that,
    so the message names the path and leaves the cause open.
    """
    index = read_excluded(output_dir)
    if not index.present:
        print(f"Excluded count unknown — no {output_dir / EXCLUDED_FILE} was written.")
    elif not index.readable:
        print(f"Exclusions file at {output_dir / EXCLUDED_FILE} could not be read — count unknown.")
    elif index.count:
        print(
            f"Excluded {index.count:,} of {index.total_input:,} records "
            f"with no usable file_md5sum -> {output_dir / EXCLUDED_FILE}"
        )
    else:
        print(f"No records excluded ({index.total_input:,} checked).")
    return index.count


# Duplicate file_ids to name before printing a count instead.
_DUPLICATES_SHOWN = 10


def _check_one_row_per_file(output_dir: Path, key: RecordKey) -> bool:
    """Print whether every value of the source's key in the run is unique; False if any repeats.

    ``key`` is the source's record key (``pipeline.SOURCE_RECORD_KEYS``), read from the
    run's input envelope. A repeated value means the run holds more than one row for a
    file, so every count over the output double-counts it and no identifier is a primary
    key. The files listed beside each value say which producers wrote those rows — two
    that claimed the same file, or one that wrote it twice.

    Rows carrying no value under the key are counted and not failed here. In a full
    run that count is zero on the path that reaches this check: Phase 3 refuses a row
    with no key before it runs (``scripts/classify_remaining_files.py``). It is
    reported rather than assumed so a run directory assembled any other way says what
    it did not check.
    """
    field = key.output_field
    identities = row_identities(output_dir, field)
    checked = identities.total_rows - identities.without_key
    if identities.without_key:
        print(f"{identities.without_key:,} of {identities.total_rows:,} rows carry no {field} — not checked.")
    if not identities.duplicates:
        # Nothing checkable is not the same fact as one row per file, so it does not
        # get that line.
        if checked:
            print(f"One row per file: {checked:,} rows, no repeated {field}.")
        else:
            print(f"No row carries a {field} — uniqueness was not checked.")
        return True

    print(f"DUPLICATE ROWS: {len(identities.duplicates):,} {field} values appear in more than one row.")
    # nsmallest, not sorted()[:n]: a mis-routed file type duplicates its whole
    # population, so the map this samples can hold hundreds of thousands of entries.
    for value, sources in heapq.nsmallest(_DUPLICATES_SHOWN, identities.duplicates.items()):
        print(f"  {value}: {', '.join(sources)}")
    if len(identities.duplicates) > _DUPLICATES_SHOWN:
        print(f"  ... and {len(identities.duplicates) - _DUPLICATES_SHOWN:,} more")
    print("A file has more than one row — see the files named above. Every count over this output double-counts it.")
    return False


def run_all_classifications(
    metadata: Path,
    output_dir_base: Path,
    evidence_base: Path,
    workers: int | None = None,
    source_evidence_root: Path = DEFAULT_SOURCE_EVIDENCE_ROOT,
) -> bool:
    """Run the full classification pipeline over one meta-disco metadata file.

    This is the single classification path shared by every source. A source (AnVIL,
    HPRC, …) maps its native metadata into the meta-disco record shape and calls this;
    there is no per-source classifier. It writes a timestamped run dir under
    ``output_dir_base`` and caches header evidence under ``evidence_base``, running
    Phase 1 (header types + non-header scripts), Phase 2 (index inheritance), and
    Phase 3 (the remaining catch-all). ``workers`` sets the header-fetch concurrency
    (``None`` = the pipeline default). Returns True only if every phase succeeded and
    no value of the source's record key repeats across the completed run
    (:func:`_check_one_row_per_file`, which passes rows that carry none rather than
    checking them).

    Raises ``ValueError`` before any of that if two producers claim overlapping
    extensions (:func:`producers.validate_registry`) — a run that cannot say who owns a
    file must not start one — or if the input envelope names no repository with a
    declared record key (:func:`pipeline.record_key`), since Phase 3 would refuse the
    same input after every earlier phase had run (#446). That preflight reads the
    envelope alone (:func:`pipeline.load_envelope`), not the records.

    After those two refusals and before the run directory exists, it reports the
    evidence files under ``source_evidence_root``
    (:func:`source_evidence.report_evidence_files`), which says what each one is and how old
    it is — so a run refused at preflight reports none. The one judgement passed on
    them is the third refusal: more than one current file claiming to be a repository's
    published source (:func:`source_evidence.refuse_second_published_source`, #497)
    raises ``ValueError`` before the run directory exists.
    Reporting there, ahead of the run directory, puts what the run found at the top of
    its log rather than behind the phases. *Found*
    and not *consumed*: the rows go no further than that report, because matching
    them to our files is #402, so until then an evidence file changes what a run *says*,
    never what it writes.

    Every producer writes ``excluded_files.json`` into the run directory as it loads,
    naming each input record with no usable ``file_md5sum`` (#376) — the file is where
    those records are named, since they appear in no classification output. This
    function only reports the count after Phase 1, because each producer's own stdout is
    captured.
    """
    # Before anything is fetched or written: no two producers may claim overlapping
    # extensions. A run that violated this wrote some files twice and was told so only
    # at the end, hours in (#445) — the whole point of checking here is that the answer
    # costs nothing and arrives first.
    validate_registry()
    # Same reasoning for the record key: the catch-all raises without one, and the
    # duplicate check reads the same field, so an input that cannot name it fails here.
    key = record_key(load_envelope(metadata), metadata)

    refuse_second_published_source(report_evidence_files(source_evidence_root), PUBLISHED_TABLES)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_dir_base / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Re-running classifications with timestamp: {timestamp}")
    print(f"Output directory: {output_dir}")
    print(f"Evidence cache: {evidence_base}")

    parallel_jobs = build_parallel_jobs(metadata, output_dir, evidence_base, workers)

    # Track all classification output paths for Phase 3
    all_classification_files = output_paths(output_dir, phase=1)

    print(f"\nPhase 1: Running {len(parallel_jobs)} classifiers in parallel...")
    success = True
    with ThreadPoolExecutor(max_workers=len(parallel_jobs)) as executor:
        futures = {executor.submit(run_script, name, path, extra): name for name, path, extra in parallel_jobs}
        for future in as_completed(futures):
            _script_name, ok = future.result()
            success &= ok

    _report_exclusions(output_dir)

    # Phase 2: Index classification (inherits from parent file classifications)
    index_producer = PRODUCERS["index"]
    index_output = output_dir / index_producer.output
    if not success:
        print("\nPhase 2: SKIPPED — one or more Phase 1 classifiers failed")
    else:
        print("\nPhase 2: Classifying index files...")
        _, ok = run_script(
            index_producer.script,
            index_output,
            ["--metadata", str(metadata), "--classifications", *[str(p) for p in all_classification_files]],
        )
        success &= ok
        all_classification_files.append(index_output)

    # Phase 3: Catch-all for files no other producer wrote a row for
    remaining_producer = PRODUCERS["remaining"]
    if not success:
        print("\nPhase 3: SKIPPED — one or more earlier classifiers failed")
    else:
        print("\nPhase 3: Classifying remaining files...")
        _, ok = run_script(
            remaining_producer.script,
            output_dir / remaining_producer.output,
            ["--metadata", str(metadata), "--classifications", *[str(p) for p in all_classification_files]],
        )
        success &= ok

    # Only meaningful once every producer has written: a file claimed twice is visible
    # only when both rows are on disk.
    if success:
        success &= _check_one_row_per_file(output_dir, key)

    print(f"\n{'=' * 70}")
    if success:
        print("All classifications complete!")
        print(f"Results saved to: {output_dir}/")
    else:
        print("Some classifications failed - check output above")
    print("=" * 70)

    # List output files
    print("\nOutput files:")
    for f in sorted(output_dir.glob("*.json")):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name}: {size_mb:.1f} MB")

    return success
