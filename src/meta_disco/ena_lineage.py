"""Which ENA run's reads an alignment holds, as lineage into the dataset holding those reads (#594).

ANVIL_T2T_CHRY's 1KGP CRAMs were re-aligned from reads that dataset does not hold, so
no table of it names their reads and no md5 of theirs is ENA's. Each CRAM's own
``samtools stats`` file, on the same sample row, gives the reads and bases in it; a
sequencing run is one event, so the one run of the declared ENA studies with exactly that
read count and base count (the base count mostly the read count times the read length) is
the run whose reads the CRAM holds, whichever copy of them the aligner was given. Those reads are files of another dataset (ANVIL_T2T's
``ERR…_1/_2.fastq.gz``, ENA's own files by md5, #606), so the importer writes each CRAM a
lineage line per FASTQ of its run, naming that dataset as the parent's
(``parent_dataset``), and reconcile carries the run's answer down the CRAM's step (#571).

**Where this is allowed** is the run lineage map's (``run_lineage_map``), the one
declared exception to a file's lineage staying in its dataset (ADR-0002 decision 2).
:func:`check` holds the map to the deployment and the manifests: every dataset it names
declared and on disk, every table and column present.

**The gate is the counts, with the identity checked on both sides** (contract 2.10): a CRAM
is linked only to the one run whose ``read_count`` and ``base_count`` equal its stats
file's ``raw total sequences`` and ``total length``, where the stats file's own command
line read a file of the CRAM's name, every FASTQ ENA lists for that run is a file of the
``reads_in`` dataset with that name and ENA's md5, and the CRAM's ``@RG`` sample is the
sample of the file ENA was submitted (``NA19201.final.cram`` for NA19201). **The step is
the CRAM's own word**: ``raw_activity`` is the program, and its subcommand where it has
one, of the CRAM header's ``@PG`` lines whose command names a FASTQ (``bwa mem``, once
per lane), verbatim, when they all name the same one; what it means is the activity
translation table's (#584). Every CRAM not linked is counted by why (:data:`OUTCOMES`),
never written.

**What was read is kept** beside each generation (``<table>.inputs.json``): ENA's rows
as fetched, and per CRAM what its stats file and header gave, so a re-import from it
(:func:`load_inputs`) reads no network and, against the same map and manifests, writes the
same lines; kept inputs that disagree with the map or the manifests are refused
(:func:`require_inputs_agree`). Stats files and headers are read :data:`WORKERS` at a time.
ENA's portal answers 500 for minutes at a time, so an HTTP 429/5xx from it is waited out
(:data:`ENA_MAX_WAIT`); a stats read cut off by the network is tried again
(:data:`STATS_ATTEMPTS`).
"""

from __future__ import annotations

import csv
import io
import json
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from .anvil_evidence import verbatim_manifest
from .anvil_lineage import cell_values
from .azul_manifest import (
    ANVIL_FILE_HANDLE_COLUMNS,
    VERBATIM_FILE,
    iter_verbatim_entities,
    link_handles,
    request_with_retries,
    sidecar_datasets,
)
from .deployments import Deployment
from .ena_evidence import SOURCE, SOURCE_KEY, TABLE, add_row, ena_envelope, run_md5s
from .exclusions import MD5_RE
from .fetchers import FetchError, fetch_bam_header, fetch_head_text, require_samtools
from .lineage_evidence import write_lineage_file
from .models import JOIN_KEY_FILE_ID
from .run_lineage_map import Entry, RunLineageMap
from .schema.classification_model import LineageParentKeyEnum, LineageRow
from .source_evidence import evidence_file_path, generation_dir, new_generation, staged_generation
from .validators.header_extractors import parse_sam_header, sam_command_words

# ENA's per-accession report of its runs, every run of a study in one response.
PORTAL_FILEREPORT = "https://www.ebi.ac.uk/ena/portal/api/filereport"
# What a line names as the parent's column: ENA's list of the run's files.
PARENT_COLUMN = "fastq_ftp"
# What a line names as raw_activity's column: the child header's program lines.
STEP_COLUMN = "@PG"
# What is asked of ENA for each run of a study.
FIELDS = (SOURCE_KEY, "study_accession", "read_count", "base_count", "fastq_ftp", "fastq_md5", "submitted_ftp")
# A stats file's head holding its summary numbers, which sit in its first ~2 KB.
STATS_HEAD_BYTES = 16 * 1024
_STATS_READS = "SN\traw total sequences:"
_STATS_BASES = "SN\ttotal length:"
_STATS_COMMAND = "# The command line was:"
_ALIGNMENT = (".cram", ".bam", ".sam")
_FASTQ = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
# ENA's portal answers 500 for minutes at a time: seconds one study's report may spend waiting.
ENA_MAX_WAIT = 600.0
# Tries per stats file when the connection drops.
STATS_ATTEMPTS = 3
# Files read at once (stats files, then headers), and how often progress is reported.
WORKERS = 8
PROGRESS_EVERY = 500

# Each alignment's outcome, one per CRAM, in the order they are tested. ``no_stats``: the
# rows naming it give no one stats file (none, or several); ``stats_of_other_file``: the
# stats file's command read a file of another name; ``sample_differs``: the CRAM's @RG
# sample is not the sample of the file ENA was submitted.
LINKED = "linked"
NO_STATS = "no_stats"
STATS_UNREADABLE = "stats_unreadable"
STATS_OF_OTHER_FILE = "stats_of_other_file"
NO_RUN = "no_run"
SEVERAL_RUNS = "several_runs"
READS_NOT_IN_DATASET = "reads_not_in_dataset"
HEADER_UNREADABLE = "header_unreadable"
NO_READ_STEP = "no_read_step"
SEVERAL_READ_STEPS = "several_read_steps"
SAMPLE_DIFFERS = "sample_differs"
OUTCOMES = (
    LINKED,
    NO_STATS,
    STATS_UNREADABLE,
    STATS_OF_OTHER_FILE,
    NO_RUN,
    SEVERAL_RUNS,
    READS_NOT_IN_DATASET,
    HEADER_UNREADABLE,
    NO_READ_STEP,
    SEVERAL_READ_STEPS,
    SAMPLE_DIFFERS,
)


# --- checking the map against a deployment and its manifests ----------------------------


def manifest_paths(run_map: RunLineageMap, manifest_root: Path) -> tuple[dict[str, Path], list[str]]:
    """Every dataset the map names (child or ``reads_in``) to its verbatim manifest, and why any cannot be read."""
    named = sidecar_datasets(manifest_root, run_map.catalog)
    paths: dict[str, Path] = {}
    problems: list[str] = []
    for dataset in dict.fromkeys(d for e in run_map.entries for d in (e.dataset, e.reads_in)):
        path = verbatim_manifest(manifest_root, run_map.catalog, dataset, named)
        if isinstance(path, str):
            problems.append(path)
        else:
            paths[dataset] = path
    return paths, problems


def check(run_map: RunLineageMap, deployment: Deployment, manifest_root: Path) -> list[str]:
    """How the map disagrees with the deployment and the manifests on disk, one line per problem; empty when none.

    The map is ENA's and authored against the deployment's catalog; every child and
    ``reads_in`` dataset is one the deployment declares and the catalog's sidecar names,
    with its verbatim manifest on disk. Each entry's table has rows, and its child and
    counts columns appear on some row, every non-empty value a DRS URI or a list of them.
    """
    problems = []
    if run_map.source != SOURCE:
        problems.append(f"run lineage map: its source is {run_map.source!r}; this importer reads {SOURCE!r}'s runs")
    if run_map.catalog != deployment.catalog:
        problems.append(f"run lineage map: authored against {run_map.catalog}, not {deployment.catalog}")
    for dataset in dict.fromkeys(d for e in run_map.entries for d in (e.dataset, e.reads_in)):
        if dataset not in deployment.snapshots:
            problems.append(f"{dataset}: not a dataset the {deployment.name} deployment declares")
    paths, unreadable = manifest_paths(run_map, manifest_root)
    problems += unreadable
    for dataset in run_map.datasets():
        if dataset in paths:
            problems += _check_tables(run_map.dataset_entries(dataset), dataset, paths[dataset])
    return problems


def _check_tables(entries: list[Entry], dataset: str, path: Path) -> list[str]:
    wanted: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        wanted[entry.table] |= {entry.child_column, entry.counts_column}
    rows: Counter = Counter()
    seen: dict[str, set[str]] = defaultdict(set)
    wrong: dict[tuple[str, str], object] = {}
    for table, row in iter_verbatim_entities(path, set(wanted)):
        rows[table] += 1
        seen[table].update(row)
        for column in wanted[table]:
            if (table, column) not in wrong and cell_values(row.get(column), locator=True) == []:
                wrong[(table, column)] = row[column]
    problems = []
    for table in sorted(wanted):
        if not rows[table]:
            problems.append(f"{dataset}/{table}: no row of this type in the manifest")
            continue
        for column in sorted(wanted[table]):
            if column not in seen[table]:
                problems.append(f"{dataset}/{table}/{column}: no row carries this column")
            elif (table, column) in wrong:
                problems.append(f"{dataset}/{table}/{column}: holds {wrong[(table, column)]!r}, not a DRS URI")
    return problems


# --- reading what the importer reads ---------------------------------------------------


@dataclass(frozen=True)
class CatalogFile:
    """A file of a dataset, as its ``anvil_file`` entity gives it."""

    file_id: str
    file_name: str
    md5: str | None


@dataclass
class CramReading:
    """What was read for one alignment: its stats file's counts and its header's steps, or why not.

    Kept in the inputs file, so a re-import reads none of it again. ``file_name`` and
    ``md5`` are the alignment's as the manifest gave them when it was read, so a re-import
    can tell the manifest still names the same file. ``stats_reads`` is the name of the
    file the stats file's command read, where it names one alignment.
    ``steps`` is each distinct ``@PG`` program (and subcommand) whose command names a
    FASTQ, and ``samples`` each distinct ``@RG`` ``SM``, both sorted and None until the
    header is read.
    """

    file_id: str
    file_name: str | None = None
    md5: str | None = None
    stats_md5: str | None = None
    read_count: int | None = None
    base_count: int | None = None
    stats_reads: str | None = None
    stats_error: str | None = None
    steps: list[str] | None = None
    samples: list[str] | None = None
    header_error: str | None = None


@dataclass
class Inputs:
    """Everything an import of one dataset read: ENA's rows and each alignment's reading."""

    catalog: str
    dataset: str
    requested_at: datetime
    studies: list[str]
    runs: dict[str, dict]
    crams: dict[str, CramReading] = field(default_factory=dict)


FetchRuns = Callable[[list[str], "Progress"], tuple[datetime, dict[str, dict]]]
ReadStats = Callable[[str], "StatsHead"]
ReadHeader = Callable[[CatalogFile], str]
Progress = Callable[[str], None]


def _silent(_message: str) -> None:
    pass


def fetch_study_runs(studies: list[str], progress: Progress) -> tuple[datetime, dict[str, dict]]:
    """ENA's ``read_run`` rows for every run of ``studies``, by run accession, and when they were asked for.

    One file report per study, as tab-separated text, through ``request_with_retries``: a
    server error is waited out for up to :data:`ENA_MAX_WAIT` seconds per study, each wait
    told to ``progress``. A run two studies both return must be the same row both times
    (``ena_evidence.add_row``).
    """
    requested_at = datetime.now(timezone.utc)
    rows: dict[str, dict] = {}
    with requests.Session() as http:
        for study in studies:
            params = {"accession": study, "result": TABLE, "fields": ",".join(FIELDS), "format": "tsv", "limit": 0}
            response = request_with_retries(
                http,
                "get",
                PORTAL_FILEREPORT,
                sleep=time.sleep,
                max_wait=ENA_MAX_WAIT,
                log=lambda message, at=study: progress(f"ENA {at}: {message}"),
                params=params,
                timeout=600,
            )
            for row in csv.DictReader(io.StringIO(response.text), delimiter="\t"):
                add_row(rows, row, f"{PORTAL_FILEREPORT} {study}")
    return requested_at, rows


@dataclass(frozen=True)
class StatsHead:
    """What a ``samtools stats`` file's head says: its counts, and the alignment its command read (None unless one)."""

    read_count: int
    base_count: int
    reads: str | None


def stats_counts(text: str) -> StatsHead:
    """A ``samtools stats`` file's ``raw total sequences`` and ``total length``, and the file its command read.

    ``ValueError`` if either count is absent or not a number: not samtools stats, or a head
    cut off before them. The file read is the one word of the command line naming an
    alignment (``.cram``, ``.bam``, ``.sam``), by its base name.
    """
    counts: dict[str, int] = {}
    command: list[str] = []
    for line in text.splitlines():
        for label in (_STATS_READS, _STATS_BASES):
            if line.startswith(label):
                cells = line.split("\t")
                if len(cells) < 3 or not cells[2].strip().isdigit():
                    raise ValueError(f"{label.strip()!r} holds no count")
                counts[label] = int(cells[2])
        if line.startswith(_STATS_COMMAND):
            command = line[len(_STATS_COMMAND) :].split()
    if len(counts) != 2:
        raise ValueError("no raw total sequences and total length in the file's head; not samtools stats")
    read = {w.rsplit("/", 1)[-1] for w in command if w.endswith(_ALIGNMENT)}
    return StatsHead(counts[_STATS_READS], counts[_STATS_BASES], next(iter(read)) if len(read) == 1 else None)


def read_stats(md5: str) -> StatsHead:
    """What the ``samtools stats`` file with this md5 says (:func:`stats_counts`), read from the AnVIL S3 mirror.

    A transport failure (a dropped connection, a failed name lookup, a body cut off
    mid-read: any ``requests`` exception) is tried :data:`STATS_ATTEMPTS` times in all, then
    raises ``FetchError``; any other failure (an HTTP status, a file that is not samtools
    stats) raises at once.
    """
    for attempt in range(1, STATS_ATTEMPTS + 1):
        try:
            return stats_counts(fetch_head_text(md5, STATS_HEAD_BYTES))
        except requests.RequestException as exc:
            if attempt == STATS_ATTEMPTS:
                raise FetchError(f"head: {type(exc).__name__}: {exc}") from exc
            time.sleep(attempt)
    raise AssertionError("STATS_ATTEMPTS is at least 1")


def header_reader(evidence_dir: Path) -> ReadHeader:
    """Read an alignment's SAM header from the BAM producer's cache under ``evidence_dir``, or with samtools into it."""

    def read(file: CatalogFile) -> str:
        if file.md5 is None:
            raise FetchError("no md5 to read the header by")
        return fetch_bam_header(evidence_dir, file.md5, file_name=file.file_name)

    return read


def read_steps(header_text: str) -> list[str]:
    """The program of each ``@PG`` command that names a FASTQ, with its subcommand where it has one, verbatim, distinct and sorted.

    ``bwa mem`` for ``bwa mem -Y … ref.fa r_1.fq.gz r_2.fq.gz``; ``minimap2`` for
    ``minimap2 ref.fa r.fq.gz``: a second word is taken as a subcommand only where it is
    neither an option nor a file (no ``-`` first, no ``/`` or ``.`` in it). The commands are
    split by ``header_extractors.sam_command_words``, the readers' one command-line splitter (#615).
    """
    steps = set()
    for words in sam_command_words(parse_sam_header(header_text)):
        if not any(w.endswith(_FASTQ) for w in words[1:]):
            continue
        subcommand = len(words) > 1 and not words[1].startswith("-") and not any(c in words[1] for c in "/.")
        steps.add(" ".join(words[:2] if subcommand else words[:1]))
    return sorted(steps)


def read_samples(header_text: str) -> list[str]:
    """The ``SM`` of each ``@RG`` line, distinct and sorted."""
    return sorted({rg["SM"] for rg in parse_sam_header(header_text).rg or [] if rg.get("SM")})


def run_sample(run: dict) -> str | None:
    """The sample of the file ENA was submitted for a run (``NA19201`` of ``…/NA19201.final.cram``), where its files name one."""
    names = {p.rsplit("/", 1)[-1].split(".", 1)[0] for p in (run.get("submitted_ftp") or "").split(";") if p}
    return next(iter(names)) if len(names) == 1 else None


def _catalog_files(path: Path) -> Iterable[tuple[dict, CatalogFile]]:
    for _table, value in iter_verbatim_entities(path, {VERBATIM_FILE}):
        file_id, name, md5 = value.get("file_id"), value.get("file_name"), value.get("file_md5sum")
        if isinstance(file_id, str) and isinstance(name, str):
            # Only a well-formed md5 is an identity, as the pipeline's load path holds (#376): it is
            # the S3 key a stats file and a header are read by, and the header cache's file name.
            yield value, CatalogFile(file_id, name, md5 if isinstance(md5, str) and MD5_RE.match(md5) else None)


def files_by_drs(path: Path) -> dict[str, CatalogFile]:
    """A dataset's files, from its verbatim manifest, by each DRS URI its ``anvil_file`` entity carries."""
    return {
        handle: file
        for value, file in _catalog_files(path)
        for column in ANVIL_FILE_HANDLE_COLUMNS
        for handle in link_handles(value.get(column)) or []
    }


def files_by_md5(path: Path) -> dict[str, list[CatalogFile]]:
    """A dataset's files, from its verbatim manifest, by md5."""
    found: dict[str, list[CatalogFile]] = defaultdict(list)
    for _value, file in _catalog_files(path):
        if file.md5:
            found[file.md5].append(file)
    return dict(found)


def alignments(
    path: Path, entry: Entry, by_drs: dict[str, CatalogFile]
) -> list[tuple[CatalogFile, CatalogFile | None]]:
    """Each alignment the entry's table names, once each, with its one stats file: the one file the rows naming it
    give in the counts column, else None (none, or several). A cell naming no file of the dataset is passed over."""
    children: dict[str, CatalogFile] = {}
    stats: dict[str, set[CatalogFile]] = defaultdict(set)
    for _table, row in iter_verbatim_entities(path, {entry.table}):
        named = {by_drs[h] for h in cell_values(row.get(entry.counts_column), locator=True) or [] if h in by_drs}
        for handle in cell_values(row.get(entry.child_column), locator=True) or []:
            child = by_drs.get(handle)
            if child is not None:
                children.setdefault(child.file_id, child)
                stats[child.file_id] |= named
    return [(child, next(iter(stats[i])) if len(stats[i]) == 1 else None) for i, child in children.items()]


def runs_by_counts(runs: dict[str, dict], studies: Iterable[str]) -> dict[tuple[int, int], list[dict]]:
    """The runs of ``studies`` by their ``(read_count, base_count)``; a run lacking either is left out."""
    wanted = set(studies)
    found: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for row in runs.values():
        if row.get("study_accession") not in wanted:
            continue
        try:
            found[(int(row["read_count"]), int(row["base_count"]))].append(row)
        except (KeyError, TypeError, ValueError):
            continue
    return dict(found)


# --- importing -------------------------------------------------------------------------


@dataclass
class DatasetImport:
    """One dataset's import: each alignment's outcome (:data:`OUTCOMES`), lines written, and where."""

    dataset: str
    directory: Path
    outcomes: Counter = field(default_factory=Counter)
    written: int = 0


def import_all(
    run_map: RunLineageMap,
    manifest_root: Path,
    lineage_root: Path,
    evidence_dir: Path,
    fetch_runs: FetchRuns = fetch_study_runs,
    read_stats_of: ReadStats = read_stats,
    read_header: ReadHeader | None = None,
    stored: dict[str, Inputs] | None = None,
    generation: str | None = None,
    progress: Progress = _silent,
) -> list[DatasetImport]:
    """Import every child dataset of the map, each as one new generation under one shared stamp.

    ``stored`` (by dataset) re-imports from kept inputs instead of the network: its rows
    and readings are used as they are and nothing is fetched, and it must hold every child
    dataset of the map. ``progress`` is told how many stats files and headers have been
    read, every :data:`PROGRESS_EVERY`, and of each wait on ENA. Raises before writing
    anything if the map is not ENA's, a dataset's verbatim manifest cannot be read, a
    child dataset has no kept inputs, or (reading headers itself) samtools is not on PATH.
    """
    if run_map.source != SOURCE:
        raise ValueError(f"the run lineage map's source is {run_map.source!r}; this importer reads {SOURCE!r}'s runs")
    paths, problems = manifest_paths(run_map, manifest_root)
    if problems:
        raise ValueError("; ".join(problems))
    if stored is not None:
        unstored = [d for d in run_map.datasets() if d not in stored]
        if unstored:
            raise ValueError(f"no kept inputs for {unstored}; a re-import from kept inputs reads no network")
    elif read_header is None:
        require_samtools()
    stamp = generation or new_generation()
    return [
        import_dataset(
            run_map,
            dataset,
            paths,
            lineage_root,
            fetch_runs=fetch_runs,
            read_stats_of=read_stats_of,
            read_header=read_header or header_reader(evidence_dir),
            stored=(stored or {}).get(dataset),
            generation=stamp,
            progress=progress,
        )
        for dataset in run_map.datasets()
    ]


def import_dataset(
    run_map: RunLineageMap,
    dataset: str,
    paths: dict[str, Path],
    lineage_root: Path,
    *,
    fetch_runs: FetchRuns,
    read_stats_of: ReadStats,
    read_header: ReadHeader,
    stored: Inputs | None,
    generation: str,
    progress: Progress = _silent,
) -> DatasetImport:
    """Write one generation for one child dataset: a lineage file and an inputs file per table.

    Raises, writing nothing, when no alignment of a table is linked: the map disagrees with
    the catalog or with ENA there, and writing nothing quietly would leave an older
    generation current. With ``stored``, also when the kept inputs disagree with the map or
    the manifests (:func:`require_inputs_agree`).
    """
    catalog = run_map.catalog
    result = DatasetImport(dataset, generation_dir(lineage_root, SOURCE, catalog, dataset, generation))
    entries = run_map.dataset_entries(dataset)
    if stored is not None:
        if (stored.catalog, stored.dataset) != (catalog, dataset):
            raise ValueError(f"inputs for {stored.catalog}/{stored.dataset} cannot be imported as {catalog}/{dataset}")
        inputs = stored
    else:
        studies = sorted({s for e in entries for s in e.ena_studies})
        requested_at, runs = fetch_runs(studies, progress)
        inputs = Inputs(catalog, dataset, requested_at, studies, runs)
    by_drs = files_by_drs(paths[dataset])
    reads_index: dict[str, dict[str, list[CatalogFile]]] = {}
    with staged_generation(result.directory) as staging:
        for entry in entries:
            if entry.reads_in not in reads_index:
                reads_index[entry.reads_in] = files_by_md5(paths[entry.reads_in])
            found = alignments(paths[dataset], entry, by_drs)
            if stored is not None:
                require_inputs_agree(entries, found, stored, f"{dataset}/{entry.table}")
            for child, _stats in found:
                inputs.crams.setdefault(child.file_id, CramReading(child.file_id, child.file_name, child.md5))
            by_counts = runs_by_counts(inputs.runs, entry.ena_studies)
            at = f"{dataset}/{entry.table}"
            if stored is None:
                _read_stats_files(found, inputs, read_stats_of, progress, at)
                _read_headers(found, inputs, by_counts, reads_index[entry.reads_in], read_header, progress, at)
            rows, outcomes = _lines(entry, found, inputs, by_counts, reads_index[entry.reads_in])
            if not rows:
                counts = ", ".join(f"{k} {n:,}" for k, n in sorted(outcomes.items()))
                raise ValueError(f"{at}: no alignment linked to an ENA run ({counts}); nothing written")
            envelope = ena_envelope(dataset, catalog, inputs.requested_at, PORTAL_FILEREPORT)
            result.written += write_lineage_file(evidence_file_path(staging, entry.table), envelope, rows)
            result.outcomes.update(outcomes)
            write_inputs(staging / f"{entry.table}.inputs.json", inputs, [f.file_id for f, _ in found])
    return result


def require_inputs_agree(
    entries: list[Entry], found: list[tuple[CatalogFile, CatalogFile | None]], inputs: Inputs, at: str
) -> None:
    """Refuse kept inputs that would re-import against another map or manifest than they were read for.

    ``ValueError`` when the dataset's studies differ from the map's (a run of a study they
    lack could make a link ambiguous), when an alignment the manifest names has no kept
    reading (it was never read), when its name or md5 is not the one its reading was read
    for (another file under the same id), or when its stats file is not the one the reading read.
    """
    studies = sorted({s for e in entries for s in e.ena_studies})
    if inputs.studies != studies:
        raise ValueError(f"{at}: kept inputs are for studies {inputs.studies}, the map names {studies}")
    for child, stats in found:
        reading = inputs.crams.get(child.file_id)
        if reading is None:
            raise ValueError(f"{at}: {child.file_name} ({child.file_id}) has no kept reading")
        if (reading.file_name, reading.md5) != (child.file_name, child.md5):
            raise ValueError(f"{at}: {child.file_name} ({child.file_id}) is not the file its kept reading read")
        if (stats.md5 if stats is not None else None) != reading.stats_md5:
            raise ValueError(f"{at}: {child.file_name}'s stats file is not the one its kept reading read")


def _in_parallel(tasks: list[Callable[[], None]], progress: Progress, what: str) -> None:
    """Run ``tasks`` :data:`WORKERS` at a time, telling ``progress`` how many of ``what`` are done every :data:`PROGRESS_EVERY` and at the end."""
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(task) for task in tasks]
        for done, future in enumerate(as_completed(futures), start=1):
            future.result()
            if done % PROGRESS_EVERY == 0 or done == len(tasks):
                progress(f"read {done:,} of {len(tasks):,} {what}")


def _read_stats_files(
    found: list[tuple[CatalogFile, CatalogFile | None]],
    inputs: Inputs,
    read_stats_of: ReadStats,
    progress: Progress,
    at: str,
) -> None:
    """Read each alignment's stats file into its reading; one with no stats file, or already read, is passed over."""

    def task(reading: CramReading, md5: str) -> Callable[[], None]:
        def read() -> None:
            reading.stats_md5 = md5
            try:
                head = read_stats_of(md5)
            except (FetchError, ValueError) as exc:
                reading.stats_error = str(exc)
            else:
                reading.read_count, reading.base_count, reading.stats_reads = (
                    head.read_count,
                    head.base_count,
                    head.reads,
                )

        return read

    tasks = [
        task(inputs.crams[child.file_id], stats.md5)
        for child, stats in found
        if stats is not None and stats.md5 is not None and inputs.crams[child.file_id].stats_md5 is None
    ]
    _in_parallel(tasks, lambda message: progress(f"{at}: {message}"), "stats files")


def _read_headers(
    found: list[tuple[CatalogFile, CatalogFile | None]],
    inputs: Inputs,
    by_counts: dict[tuple[int, int], list[dict]],
    reads_by_md5: dict[str, list[CatalogFile]],
    read_header: ReadHeader,
    progress: Progress,
    at: str,
) -> None:
    """Read the header of each alignment whose counts found its run's reads, into its reading, unless already read."""

    def task(child: CatalogFile, reading: CramReading) -> Callable[[], None]:
        def read() -> None:
            try:
                text = read_header(child)
            except FetchError as exc:
                reading.header_error = str(exc)
            else:
                reading.steps, reading.samples = read_steps(text), read_samples(text)

        return read

    tasks = []
    for child, stats in found:
        reading = inputs.crams[child.file_id]
        unread = reading.steps is None and reading.header_error is None
        if unread and _run_match(child, stats, reading, by_counts, reads_by_md5)[0] is None:
            tasks.append(task(child, reading))
    _in_parallel(tasks, lambda message: progress(f"{at}: {message}"), "headers")


def _lines(
    entry: Entry,
    found: list[tuple[CatalogFile, CatalogFile | None]],
    inputs: Inputs,
    by_counts: dict[tuple[int, int], list[dict]],
    reads_by_md5: dict[str, list[CatalogFile]],
) -> tuple[list[LineageRow], Counter]:
    """Each linked alignment's lines, and every alignment's outcome, from what its reading holds."""
    rows: list[LineageRow] = []
    outcomes: Counter = Counter()
    for child, stats in found:
        reading = inputs.crams[child.file_id]
        verdict, run, parents = _run_match(child, stats, reading, by_counts, reads_by_md5)
        if verdict is None:
            assert run is not None
            verdict = _header_outcome(reading, run)
        outcomes[verdict] += 1
        if verdict != LINKED:
            continue
        assert run is not None and reading.steps is not None
        rows += [
            LineageRow(
                target_key_value=child.file_id,
                parent=parent.file_id,
                parent_key_type=LineageParentKeyEnum(JOIN_KEY_FILE_ID),
                parent_dataset=entry.reads_in,
                parent_source_identifier=run[SOURCE_KEY],
                raw_activity=reading.steps[0],
                raw_activity_column=STEP_COLUMN,
                child_column=entry.child_column,
                parent_column=PARENT_COLUMN,
            )
            for parent in parents
        ]
    return rows, outcomes


def _run_match(
    child: CatalogFile,
    stats: CatalogFile | None,
    reading: CramReading,
    by_counts: dict[tuple[int, int], list[dict]],
    reads_by_md5: dict[str, list[CatalogFile]],
) -> tuple[str | None, dict | None, list[CatalogFile]]:
    """The run an alignment's counts name and that run's reads; or why not, as an outcome, with neither."""
    if stats is None or stats.md5 is None:
        return NO_STATS, None, []
    if reading.read_count is None or reading.base_count is None:
        return STATS_UNREADABLE, None, []
    if reading.stats_reads != child.file_name:
        return STATS_OF_OTHER_FILE, None, []
    runs = by_counts.get((reading.read_count, reading.base_count), [])
    if not runs:
        return NO_RUN, None, []
    if len(runs) > 1:
        return SEVERAL_RUNS, None, []
    (run,) = runs
    parents = _run_reads(run, reads_by_md5)
    if parents is None:
        return READS_NOT_IN_DATASET, None, []
    return None, run, parents


def _header_outcome(reading: CramReading, run: dict) -> str:
    """A matched alignment's outcome from its header: linked on exactly one step, and one sample, the run's."""
    if reading.header_error is not None or reading.steps is None:
        return HEADER_UNREADABLE
    if not reading.steps:
        return NO_READ_STEP
    if len(reading.steps) > 1:
        return SEVERAL_READ_STEPS
    sample = run_sample(run)
    return LINKED if sample is not None and reading.samples == [sample] else SAMPLE_DIFFERS


def _run_reads(run: dict, reads_by_md5: dict[str, list[CatalogFile]]) -> list[CatalogFile] | None:
    """The ``reads_in`` dataset's file for every FASTQ ENA lists for the run, by name and ENA's md5; None unless all are there."""
    md5s = run_md5s(run)
    if not md5s:
        return None
    found = []
    for name, md5 in sorted(md5s.items()):
        matches = [f for f in reads_by_md5.get(md5.lower(), []) if f.file_name == name]
        if len(matches) != 1:
            return None
        found.append(matches[0])
    return found


# --- the kept inputs --------------------------------------------------------------------


def write_inputs(path: Path, inputs: Inputs, file_ids: list[str]) -> None:
    """Write what was read for one table's alignments (``file_ids``), with ENA's rows, as fetched."""
    document = {
        "catalog": inputs.catalog,
        "dataset": inputs.dataset,
        "requested_at": inputs.requested_at.isoformat(),
        "url": PORTAL_FILEREPORT,
        "fields": list(FIELDS),
        "studies": inputs.studies,
        "runs": [inputs.runs[a] for a in sorted(inputs.runs)],
        "crams": [asdict(inputs.crams[f]) for f in sorted(set(file_ids)) if f in inputs.crams],
    }
    path.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def load_inputs(paths: Iterable[Path]) -> dict[str, Inputs]:
    """The inputs :func:`write_inputs` kept, by dataset, to import from without the network.

    One dataset's tables share its ENA rows, so their files are merged; two files of one
    dataset that disagree on its catalog, request time or rows raise, as does a file
    holding two different rows for one run (``ena_evidence.add_row``).
    """
    found: dict[str, Inputs] = {}
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        runs: dict[str, dict] = {}
        for row in document["runs"]:
            add_row(runs, row, str(path))
        inputs = Inputs(
            catalog=document["catalog"],
            dataset=document["dataset"],
            requested_at=datetime.fromisoformat(document["requested_at"]),
            studies=document["studies"],
            runs=runs,
            crams={c["file_id"]: CramReading(**c) for c in document["crams"]},
        )
        held = found.get(inputs.dataset)
        if held is None:
            found[inputs.dataset] = inputs
            continue
        if (held.catalog, held.requested_at, held.runs) != (inputs.catalog, inputs.requested_at, inputs.runs):
            raise ValueError(f"{path}: kept inputs for {inputs.dataset} disagree with another file's")
        held.crams.update(inputs.crams)
    return found


def describe(imports: list[DatasetImport]) -> list[str]:
    """One block per dataset: where it went and the lines written, then each outcome's count."""
    lines = []
    for run in imports:
        lines.append(f"{run.dataset} -> {run.directory} ({run.outcomes.total():,} alignments, {run.written:,} lines)")
        for outcome in OUTCOMES:
            lines.append(f"  {outcome}: {run.outcomes[outcome]:,}")
    return lines
