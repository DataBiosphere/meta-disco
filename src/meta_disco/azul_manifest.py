"""Pull AnVIL file metadata from Azul manifests (issue #368).

Azul serves two manifests over its file index, and this module knows how to ask
for them, where to keep them, and how to turn one of them into the classifier's
input records:

- ``compact`` — one tab-separated row per file: the harmonized join Azul
  materializes from its bundle structure (file, dataset, donor, biosample,
  activity columns). This is the source of ``anvil_files_metadata.json``.
- ``verbatim.jsonl`` — one ``{"type", "value"}`` line per entity: the harmonized
  ``anvil_*`` entities plus the submitter's own Terra tables, unaltered. Stored
  beside the compact manifest as the import-primary source. This module reads it
  only to count ``anvil_file`` lines for parity and to stream its entities
  (:func:`iter_verbatim_entities`); what those entities mean is #384's survey.

The two are complementary, not nested: verbatim carries every entity but not
Azul's join pre-materialized, so rebuilding a per-file record from it means
walking the activity chain yourself. How far that walk goes decides what it
costs: on 1000G the compact join reaches a donor for 25,616 files, and so does
the verbatim chain under transitive closure — but only 9,603 files are reached
if the walk stops at the activity that directly generated the file, which is the
single-hop figure #337 recorded and #384 re-measured. Verbatim entities also
carry no dataset field, which is why manifests are requested one dataset at a
time — the request's filter is what attributes a raw table to its dataset.

A manifest is a job, not a download: ``PUT /fetch/manifest/files`` answers with
JSON carrying ``Status`` 301 and a ``Location`` to poll after ``Retry-After``
seconds, until a ``Status`` 302 whose ``Location`` is a signed, expiring URL for
the payload. :func:`fetch_manifest` follows that and streams the payload to a file.

On disk, a catalog's manifests live under ``<root>/manifest/<catalog>/`` as
``<dataset>.compact.tsv`` and ``<dataset>.verbatim.jsonl`` beside a sidecar,
``manifests.json``, recording per dataset the catalog file count each manifest
was requested against and, per format, when it was fetched and how many files
it holds. Anything that needs to find a dataset's manifest — #369's registry
loader, #270's change check — should come through :func:`manifest_path` and
:func:`load_sidecar` rather than re-deriving the layout.

The HTTP session and the sleep are injected so the job-following logic and the
discovery parse are testable against fakes; the defaults are a :mod:`requests`
session and :func:`time.sleep`.
"""

from __future__ import annotations

import csv
import json
import re
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Protocol

import requests

API_URL = "https://service.explore.anvilproject.org"
FILES_URL = f"{API_URL}/index/files"
MANIFEST_URL = f"{API_URL}/fetch/manifest/files"
# Who publishes the files this module downloads. Written into every snapshot's envelope
# so a reader names the publisher rather than assuming one (#424).
REPOSITORY = "anvil"

# The catalog generation the tooling reads by default. Named once here; the
# Makefile's `CATALOG ?= anvil15` is the same value for `make download`.
DEFAULT_CATALOG = "anvil15"

FORMAT_COMPACT = "compact"
FORMAT_VERBATIM = "verbatim.jsonl"
FORMATS = (FORMAT_COMPACT, FORMAT_VERBATIM)
# On-disk suffix per format.
FORMAT_SUFFIX = {FORMAT_COMPACT: "compact.tsv", FORMAT_VERBATIM: "verbatim.jsonl"}
SIDECAR = "manifests.json"

# Verbatim entity types this package names. The manifest carries many more —
# every submitter table — but these three are the harmonized entities whose
# shape is part of the format rather than of one submitter's workspace.
VERBATIM_FILE = "anvil_file"
VERBATIM_ACTIVITY = "anvil_activity"
VERBATIM_BIOSAMPLE = "anvil_biosample"
# Every harmonized entity type starts with this; every other type is a submitter's
# own table, carried through unaltered.
HARMONIZED_PREFIX = "anvil_"
# The two columns of an `anvil_file` entity that carry the file's DRS URI; both are
# read because a submitter table may point at a file by either.
ANVIL_FILE_HANDLE_COLUMNS = ("drs_uri", "file_ref")
# What a file pointer in a submitter cell starts with.
DRS_PREFIX = "drs://"

# Azul joins a multi-valued field with this in a compact cell.
_MULTI_VALUE_SEP = " || "
# How a compact cell spells a boolean (all 708,088 anvil15 rows use one of these).
_BOOL_CELL = {"True": True, "False": False}

# Responses worth waiting out. The manifest endpoint has a usage quota. What was
# measured on 2026-09-03: sixteen consecutive jobs went through, the seventeenth
# request drew 429 with ``Retry-After: 30`` and so did every request for the next
# few minutes; the endpoint reopened within five minutes, accepted one job, and
# throttled the next; a later resume of eight jobs saw no 429 at all. I think
# that is a refilling quota of some kind, but the refill rule is not known, so a
# request waits for however long the server keeps asking, up to a budget. A
# gateway hiccup is likewise not a reason to abandon a multi-gigabyte run.
# Anything else is raised at once.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_WAIT = 1800.0  # seconds a single request may spend waiting to be accepted
_BACKOFF_BASE = 5.0  # seconds; doubled per attempt, capped, when the server names no Retry-After
_BACKOFF_CAP = 60.0
_CHUNK_BYTES = 1 << 20  # payload download chunk


class HttpSession(Protocol):
    """The two calls this module makes, keyword arguments only; ``requests.Session``
    satisfies it, and so can a test fake. Responses are typed ``Any``: they need
    ``status_code``, ``headers``, ``raise_for_status()``, ``json()``,
    ``iter_content(chunk_size)`` and ``close()``, which both provide."""

    def get(self, url: str, **kwargs: Any) -> Any: ...
    def put(self, url: str, **kwargs: Any) -> Any: ...


Sleep = Callable[[float], None]
Log = Callable[[str], None]


def _request(
    http: HttpSession,
    method: str,
    url: str,
    sleep: Sleep,
    max_wait: float = DEFAULT_MAX_WAIT,
    log: Log | None = None,
    **kwargs: Any,
) -> Any:
    """One HTTP call, waited out on a rate-limit or gateway status.

    Waits the server's ``Retry-After`` when it names one, else ``_BACKOFF_BASE``
    doubled per attempt up to ``_BACKOFF_CAP``, and keeps trying until the
    request is accepted or the waits would exceed ``max_wait`` seconds in
    total, at which point ``RuntimeError`` names the status and the time spent.
    Each wait is reported through ``log`` when one is given, so a run riding
    out a quota is visibly waiting rather than hung. Any other error status
    raises at once.
    """
    waited = 0.0
    attempt = 0
    while True:
        resp = getattr(http, method)(url, **kwargs)
        if resp.status_code not in _RETRY_STATUSES:
            resp.raise_for_status()
            return resp
        # Release the connection before waiting; a long throttled run must not pin the pool.
        resp.close()
        wait = _retry_after_seconds(resp.headers.get("Retry-After"))
        if wait is None:
            wait = min(_BACKOFF_BASE * (2**attempt), _BACKOFF_CAP)
        if waited + wait > max_wait:
            raise RuntimeError(
                f"{method.upper()} {url} still returning HTTP {resp.status_code} after {waited:.0f}s of waiting"
            )
        if log:
            log(f"HTTP {resp.status_code}; waiting {wait:.0f}s ({waited + wait:.0f}s of {max_wait:.0f}s)")
        sleep(wait)
        waited += wait
        attempt += 1


def _retry_after_seconds(value: Any) -> float | None:
    """A ``Retry-After`` as seconds to wait, at least one; ``None`` if absent or not a number.

    The header may also be an HTTP date (RFC 7231); that form is not parsed and
    falls back to the caller's backoff rather than aborting a long run. The
    floor keeps a server saying ``0`` from turning the wait into a tight loop
    that never consumes the budget.
    """
    if value is None:
        return None
    try:
        return max(float(value), 1.0)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Dataset:
    """One accessible dataset as the files facet reports it."""

    title: str
    file_count: int


def discover_datasets(
    catalog: str,
    session: HttpSession | None = None,
    sleep: Sleep = time.sleep,
    max_wait: float = DEFAULT_MAX_WAIT,
    log: Log | None = None,
) -> list[Dataset]:
    """The datasets with accessible files in ``catalog``, with their file counts.

    Read from the ``datasets.title`` term facet of a one-hit ``/index/files``
    query. An unauthenticated caller sees only accessible files, so a dataset
    with none (``ANVIL_GTEx_public_data`` since anvil15) is simply absent here.
    Sorted by file count descending, then title, so a run's order is stable.
    """
    http: HttpSession = session if session is not None else requests.Session()
    resp = _request(http, "get", FILES_URL, sleep, max_wait, log, params={"catalog": catalog, "size": 1}, timeout=60)
    terms = resp.json()["termFacets"]["datasets.title"]["terms"]
    datasets = [Dataset(title=t["term"], file_count=int(t["count"])) for t in terms if t.get("term")]
    return sorted(datasets, key=lambda d: (-d.file_count, d.title))


def manifest_filters(dataset_title: str) -> str:
    """The ``filters`` query value scoping a manifest to one dataset."""
    return json.dumps({"datasets.title": {"is": [dataset_title]}})


def fetch_manifest(
    catalog: str,
    fmt: str,
    dataset_title: str,
    destination: Path,
    session: HttpSession | None = None,
    sleep: Sleep = time.sleep,
    timeout: float = 3600,
    max_wait: float = DEFAULT_MAX_WAIT,
    log: Log | None = None,
) -> int:
    """Request one manifest, follow its job, and stream the payload to ``destination``.

    Polls while the job reports ``Status`` 301, waiting ``Retry-After`` seconds
    (at least one) between polls, and downloads the 302 ``Location`` at once,
    because that URL is signed and expires. The payload is streamed to a
    temporary file in chunks and renamed into place when complete — the largest
    verbatim manifest is half a gigabyte, and a download that dies partway must
    not leave a truncated file that a rerun would take for a finished one. Each
    HTTP call goes through :func:`_request`, so a 429 or gateway error is waited
    out for up to ``max_wait`` seconds per call, each wait reported through
    ``log``. Returns the bytes written. Raises ``TimeoutError`` if the job has
    not finished after ``timeout`` seconds of polling, and ``RuntimeError`` on
    any other job status.
    """
    if fmt not in FORMATS:
        raise ValueError(f"unknown manifest format {fmt!r}; expected one of {FORMATS}")
    http: HttpSession = session if session is not None else requests.Session()
    call = partial(_request, http, sleep=sleep, max_wait=max_wait, log=log)
    resp = call(
        "put",
        MANIFEST_URL,
        params={"catalog": catalog, "format": fmt, "filters": manifest_filters(dataset_title)},
        timeout=120,
    )
    body = resp.json()
    waited = 0.0
    while body.get("Status") == 301:
        wait = _retry_after_seconds(body.get("Retry-After")) or 1.0
        if waited + wait > timeout:
            raise TimeoutError(f"manifest job for {dataset_title!r} ({fmt}) still running after {waited:.0f}s")
        sleep(wait)
        waited += wait
        body = call("get", body["Location"], timeout=120).json()
    if body.get("Status") != 302:
        raise RuntimeError(f"unexpected manifest job response for {dataset_title!r} ({fmt}): {body}")
    resp = call("get", body["Location"], timeout=1800, stream=True)
    tmp = destination.with_name(destination.name + ".tmp")
    written = 0
    try:
        with tmp.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=_CHUNK_BYTES):
                f.write(chunk)
                written += len(chunk)
    except BaseException:
        # A half-written verbatim manifest is hundreds of megabytes; do not leave it behind.
        tmp.unlink(missing_ok=True)
        raise
    finally:
        # Streamed responses hold their connection until read out or closed.
        resp.close()
    tmp.replace(destination)
    return written


# --- on-disk layout ----------------------------------------------------------


def manifest_dir(root: Path, catalog: str) -> Path:
    """Where ``catalog``'s manifests and sidecar live under ``root`` (``data/anvil``)."""
    return root / "manifest" / catalog


def manifest_path(root: Path, catalog: str, dataset_title: str, fmt: str) -> Path:
    """The on-disk path of one dataset's manifest in one format.

    The title comes from the API's facet, so it is refused if it could name a
    path outside the catalog directory: ``pathlib`` honours ``..`` segments in
    a joined string and replaces the left side entirely for a leading ``/``.
    Every title seen so far is plain ``[A-Za-z0-9_ .-]``.
    """
    if fmt not in FORMAT_SUFFIX:
        raise ValueError(f"unknown manifest format {fmt!r}; expected one of {FORMATS}")
    if "/" in dataset_title or "\\" in dataset_title or dataset_title in ("", ".", ".."):
        raise ValueError(f"dataset title {dataset_title!r} cannot be used as a file name")
    return manifest_dir(root, catalog) / f"{dataset_title}.{FORMAT_SUFFIX[fmt]}"


def load_sidecar(root: Path, catalog: str) -> dict[str, Any]:
    """The sidecar for ``catalog``, or an empty one if none has been written.

    Shape: ``{"catalog": str, "datasets": {title: {"file_count": int, <fmt>:
    {"requested_at": iso, "bytes": int, "seconds": int, "rows": int}}}}``.
    ``file_count`` is the catalog's count for the dataset at the time its
    manifests were requested; it is what parity is checked against, so a
    catalog that has since moved on — or been deleted, as anvil14 was — does
    not stop the manifests on disk from being rebuilt into an input file.
    """
    path = manifest_dir(root, catalog) / SIDECAR
    if path.is_file():
        with path.open() as f:
            return json.load(f)
    return {"catalog": catalog, "datasets": {}}


def sidecar_requested_at(root: Path, catalog: str, dataset_title: str, fmt: str) -> datetime | None:
    """When one dataset's manifest in one format was requested, per the sidecar; None if unrecorded.

    Read here rather than by a consumer unpacking the sidecar, for the reason
    :func:`sidecar_datasets` exists: this module writes the shape. The importer (#369)
    writes it into an evidence file's envelope as ``fetched_at`` — when the *source*
    was fetched, which is the manifest's request time and not the import's.
    """
    entry = (load_sidecar(root, catalog).get("datasets") or {}).get(dataset_title) or {}
    requested = (entry.get(fmt) or {}).get("requested_at")
    if not isinstance(requested, str):
        return None
    try:
        return datetime.fromisoformat(requested)
    except ValueError:
        raise ValueError(
            f"{catalog} sidecar, {dataset_title} ({fmt}): requested_at {requested!r} is not an ISO 8601 datetime"
        ) from None


def sidecar_datasets(root: Path, catalog: str) -> dict[str, Dataset]:
    """Each dataset the catalog's sidecar records, keyed by title.

    The read-only view of :func:`load_sidecar`, so a consumer that only wants
    "which datasets, how many files each" does not unpack the sidecar's inner
    shape itself — this module owns that shape because it writes it. The
    downloader still takes the raw dict from ``load_sidecar``: it *edits* the
    sidecar in place, which a view of immutable :class:`Dataset` values cannot
    express.
    """
    entries: dict[str, Any] = load_sidecar(root, catalog).get("datasets") or {}
    return {
        title: Dataset(title=title, file_count=int(entry.get("file_count") or 0)) for title, entry in entries.items()
    }


def save_sidecar(root: Path, catalog: str, sidecar: dict[str, Any]) -> None:
    directory = manifest_dir(root, catalog)
    directory.mkdir(parents=True, exist_ok=True)
    _write_atomically(directory / SIDECAR, lambda f: json.dump(sidecar, f, indent=2, sort_keys=True))


def _write_atomically(path: Path, write: Callable[[Any], None]) -> None:
    """Write through a temporary file and rename, so a failure mid-write leaves the previous file."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w") as f:
            write(f)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(path)


# --- reading manifests ---------------------------------------------------------


def count_rows(fmt: str, path: Path) -> int:
    """Files a manifest on disk describes: compact data rows, or verbatim ``anvil_file`` lines.

    Streams the file rather than loading it — the largest verbatim manifest is
    half a gigabyte — and only parses a verbatim line that mentions
    ``anvil_file`` at all, which the submitter-table lines that make up most of
    such a file do not.
    """
    with path.open("rb") as f:
        if fmt == FORMAT_COMPACT:
            return max(sum(1 for _ in f) - 1, 0)
        needle = f'"{VERBATIM_FILE}"'.encode()
        return sum(1 for line in f if needle in line and json.loads(line).get("type") == VERBATIM_FILE)


def parity_problems(datasets: Iterable[Dataset], counts: dict[tuple[str, str], int]) -> list[str]:
    """One line per (dataset, format) whose row count disagrees with the dataset's file count.

    ``counts`` maps ``(dataset title, format)`` to the count :func:`count_rows`
    measured. A format with no entry is reported as missing rather than passed
    over: the input file must not be built from an incomplete set.
    """
    problems = []
    for dataset in datasets:
        for fmt in FORMATS:
            got = counts.get((dataset.title, fmt))
            if got is None:
                problems.append(f"{dataset.title}: no {fmt} manifest on disk")
            elif got != dataset.file_count:
                problems.append(
                    f"{dataset.title}: {fmt} has {got:,} files, the catalog said {dataset.file_count:,} when requested"
                )
    return problems


def _first(cell: str) -> str | None:
    """The first of a ``||``-joined multi-value cell, or None for an empty cell.

    Used for ``organism_type`` and ``phenotypic_sex`` only — the two donor fields
    the page downloader also emitted, which the input contract does not model and
    ignores as extra keys. Taking element zero of a list is lossy, so it is kept
    only where nothing reads the result: the two fields AnVIL *declares* about a
    file went through here too until #424, where element zero was not dropping
    data but manufacturing a wrong answer (twelve IGVF files declare two
    modalities and all twelve arrived as the first one). Those two read
    :func:`_published` instead.
    """
    if not cell:
        return None
    return cell.split(_MULTI_VALUE_SEP, 1)[0] or None


def _published(cell: str) -> list[str] | None:
    """Every value of a ``||``-joined multi-value cell, or None for an empty cell.

    The published values transcribed as Azul published it (#424): a list
    where Azul published a list, and each value exactly as it was written — no
    mapping, no normalization, no casefolding. Splitting on the full ``" || "``
    separator rather than ``"||"`` is what keeps a value free of the separator's
    own padding.

    An empty element is dropped rather than transcribed: it declares nothing, and
    a cell of nothing but separators yields ``None`` like a blank one. That is the
    only case in which the returned list is not the cell split verbatim, and the
    only value this can ever drop.
    """
    if not cell:
        return None
    return [value for value in cell.split(_MULTI_VALUE_SEP) if value] or None


SOURCE_ID_COLUMN = "sources.source_id"
SOURCE_SPEC_COLUMN = "sources.source_spec"


def dataset_source(path: Path) -> tuple[str, str] | None:
    """The TDR snapshot one dataset's compact manifest names, or None if no row names one.

    Columns 3 and 4 of every compact manifest name the snapshot the dataset was
    materialised from: ``sources.source_id`` is its uuid and ``sources.source_spec``
    the addressable form, ``tdr:bigquery:gcp:<project>:<snapshot>``. Neither reaches
    :func:`record_from_compact_manifest_row`, so until #434 a run could say which Azul
    *catalog* surfaced its files but not which snapshot it classified — and the catalog
    is a view over snapshots rather than the thing itself.

    Read verbatim. ``source_spec`` packs a provider, a cloud, a BigQuery project, a
    snapshot name and its date, and this does not split them: the format is TDR's, not
    ours, and the whole string is what addresses the snapshot.

    **Every row is read, not just the first, because the point is to refuse rather than
    guess.** One snapshot per dataset is what makes #434's envelope shape correct — the
    fact is worth 12 values, not 708,088 — so a manifest carrying two is the assumption
    breaking, and it raises naming both. Measured over anvil15 when this was written:
    12 datasets, 12 distinct ``(source_id, source_spec)`` pairs, none with more than one.

    None means no row named a snapshot — an empty manifest, or one whose source cells
    are all blank, which is how Azul writes an absent value. :func:`metadata_block`
    records that as nulls rather than omitting the keys, so a reader never has to tell
    "no snapshot" from "this build predates #434". A *missing column* is a different
    thing and raises, because it means the manifest's shape changed rather than that
    this dataset has nothing to say.
    """
    # A header fact, checked once against the header. It used to sit in the row loop,
    # where it could not fire on a manifest with a header and no data rows — so a
    # dropped column was recorded as "this dataset has no snapshot", the one confusion
    # the null contract above exists to prevent. Checking here also drops two
    # membership tests per row, which is 17.4M of them on the largest manifest.
    header = compact_header(path)
    missing = [c for c in (SOURCE_ID_COLUMN, SOURCE_SPEC_COLUMN) if c not in header]
    if missing:
        raise ValueError(
            f"{path}: compact manifest has no {' or '.join(missing)} column. "
            f"Azul writes it on every row; a manifest without it cannot say which "
            f"TDR snapshot the dataset came from (#434)."
        )

    found: tuple[str, str] | None = None
    for line_number, row in iter_compact_manifest_rows(path):
        pair = (row[SOURCE_ID_COLUMN], row[SOURCE_SPEC_COLUMN])
        # Azul writes an absent value as the empty string (see
        # `iter_compact_manifest_rows`), so a row that does not fill *both* cells names
        # no snapshot and is passed over rather than compared. `all`, not `any`: a
        # half-filled pair would otherwise put "" into the envelope as a real-looking
        # value, and would then differ from the next fully-filled row and abort the
        # download as a second, contradicting snapshot — over one blank cell. It also
        # passes over a separators-only line, which that reader deliberately yields as
        # a full row of empty cells.
        if not all(pair):
            continue
        if found is None:
            found = pair
        elif pair != found:
            raise ValueError(
                f"{path}: line {line_number} names snapshot {pair[0]} ({pair[1]}), "
                f"but an earlier row named {found[0]} ({found[1]}). A dataset is "
                f"expected to come from exactly one TDR snapshot, and the per-dataset "
                f"envelope shape (#434) depends on it; two means that assumption is wrong."
            )
    return found


def record_from_compact_manifest_row(row: dict[str, str]) -> dict[str, Any]:
    """One classifier input record from one compact manifest row.

    The keys are the input contract (``schema/metadata.yaml``) plus four fields the
    contract does not model and ignores as extra keys: the two dimensions the
    repository publishes, and the two donor fields the page downloader also emitted.
    ``file_size`` is an int and ``is_supplementary`` a bool, as the contract's strict
    validation requires; a cell that is not one of Azul's ``True`` / ``False``
    spellings raises rather than silently becoming ``False``.

    Four fields read an empty cell as ``None``, and they split a multi-valued one two
    different ways. ``data_modality`` and ``reference_assembly`` are what the repository
    publishes for this file today — classification reads them as nothing and the output
    carries them as its ``published`` block (#424) — so they are transcribed as the full
    list (:func:`_published`). ``organism_type`` and ``phenotypic_sex`` still keep
    element zero (:func:`_first`), which nothing reads. Every other field is passed
    through as the cell's text, and the contract's non-empty patterns are what reject a
    blank one.
    """
    return {
        "entry_id": row["files.document_id"],
        "file_id": row["files.file_id"],
        "file_name": row["files.file_name"],
        "file_format": row["files.file_format"],
        "file_size": int(row["files.file_size"]),
        "file_md5sum": row["files.file_md5sum"],
        "data_modality": _published(row.get("files.data_modality", "")),
        "reference_assembly": _published(row.get("files.reference_assembly", "")),
        "is_supplementary": _BOOL_CELL[row["files.is_supplementary"]],
        "drs_uri": row["files.drs_uri"],
        "dataset_id": row["datasets.dataset_id"],
        "dataset_title": row["datasets.title"],
        "organism_type": _first(row.get("donors.organism_type", "")),
        "phenotypic_sex": _first(row.get("donors.phenotypic_sex", "")),
    }


def _fields(count: int) -> str:
    """``"1 field"`` / ``"2 fields"`` — the width messages can land on either."""
    return f"{count} field{'' if count == 1 else 's'}"


def iter_compact_manifest_rows(path: Path) -> Iterator[tuple[int, dict[str, str]]]:
    """Every row of one compact manifest on disk as its raw cells, with its line number.

    The cells are exactly what Azul wrote — every column, unmapped and
    unconverted, a multi-valued cell still ``||``-joined and an absent one still
    the empty string. :func:`iter_compact_records` narrows this to the
    classifier's input contract; #384's survey needs the full 60 columns, so the
    two share this reader rather than parsing the manifest twice over.

    The line number is the file's own (the header is line 1), for error messages
    that a person can act on. It comes from the reader rather than from counting
    yielded rows, which would drift past any line the reader dropped.

    A row that does not have exactly the header's fields raises, naming the line,
    rather than being yielded — which is what lets every cell be typed ``str``.
    :class:`csv.DictReader` represents the two mismatches differently and neither
    is a cell a consumer can use: surplus fields arrive under a ``None`` key as a
    *list*, and missing trailing columns arrive as ``None`` values. A short row is
    a malformed manifest rather than a row with absent cells: an absent value is
    written as the empty string, and the 12 manifests measured for #384 have no
    short row at all.

    Two lines that look empty are not short rows. A wholly blank one is dropped
    by the underlying :mod:`csv` reader, inside the same ``next()`` that returns
    the row after it — which is why the line number still names that row and not
    the blank. A line of separators alone parses as a full row of empty cells and
    is yielded like any other; only a line with fewer separators than the header,
    whitespace or not, is short and raises.
    """
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        columns = reader.fieldnames or []
        width = len(columns)
        # A short row is detected on its last column alone: DictReader pads only
        # *trailing* columns, so a last cell that is not ``None`` means no cell
        # is. Not the same as filled — a row ending in a separator has an empty
        # last cell, which is a value the manifest wrote, not a missing column.
        # The full list of missing names costs a pass over the row, and is worth
        # it only in the message — this runs over 17.4M cells on the largest
        # manifest, where survey_compact already hand-inlines its own hot test.
        last = columns[-1] if columns else None
        for row in reader:
            n = reader.line_num
            surplus = row.pop(None, None)
            if surplus is not None:
                raise ValueError(f"{path.name} line {n}: {_fields(width + len(surplus))} for a {width}-column header")
            if last is not None and row[last] is None:
                missing = [name for name, cell in row.items() if cell is None]
                raise ValueError(
                    f"{path.name} line {n}: {_fields(width - len(missing))} for a {width}-column header, "
                    f"missing {', '.join(missing)}"
                )
            yield n, row


def compact_header(path: Path) -> list[str]:
    """The column names of one compact manifest, from its header line alone.

    Reading the header rather than inferring it from the first data row is what
    lets a caller report a manifest that has a header and no rows: its columns
    exist and are 0% filled, which is a different statement from having no
    columns at all.
    """
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t").fieldnames or [])


def iter_compact_records(path: Path) -> Iterator[dict[str, Any]]:
    """Every record in one compact manifest on disk, in manifest order, streamed.

    The exceptions are caught only to be re-raised carrying the manifest line
    number, which is what makes them actionable. ``KeyError`` is a column the
    mapper requires that the header lacks, or a ``files.is_supplementary``
    spelling that is not Azul's ``True``/``False``; ``ValueError`` is ``int()``
    on a ``files.file_size`` that is not a number. ``TypeError`` is kept as a
    guard rather than for a known path: it was how a short row used to surface,
    and :func:`iter_compact_manifest_rows` now refuses those outright, already naming the
    line.
    """
    for n, row in iter_compact_manifest_rows(path):
        try:
            yield record_from_compact_manifest_row(row)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path.name} line {n}: cannot map row to a record: {exc!r}") from None


def is_submitter_table(entity_type: str) -> bool:
    """Whether a verbatim entity type is a submitter's own table rather than a harmonized one."""
    return not entity_type.startswith(HARMONIZED_PREFIX)


def link_handles(value: Any) -> list[str] | None:
    """The DRS URIs a submitter cell holds, or None where the cell holds no link.

    Contract 2.7's definition of a file-link column, spelled once: a cell is a link
    when it is a ``drs://`` URI or a list of them. An empty string, an empty list or
    a null is "no link" and reads as None; a non-empty value that is not a link — a
    name, an accession, a list holding one — reads as an empty list, which is how a
    caller tells "nothing here" from "something here that is not a pointer".
    """
    if value is None or value == "" or value == []:
        return None
    handles = value if isinstance(value, list) else [value]
    return list(handles) if all(isinstance(h, str) and h.startswith(DRS_PREFIX) for h in handles) else []


def iter_verbatim_entities(path: Path, types: Iterable[str] | None = None) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every ``(type, value)`` pair in one verbatim manifest on disk, streamed.

    One JSON object per line, ``{"value": {...}, "type": ...}``. Both harmonized
    ``anvil_*`` entities and the submitter's own tables come through here; the
    caller decides which types it cares about. A blank line carries no entity and
    is passed over. Any other line whose JSON will not parse, or that is not that
    shape, raises with its line number rather than being skipped — a survey that
    silently dropped entities would understate coverage, which is the one thing
    it must not do.

    ``types`` narrows the stream to those entity types, and cheaply: a line is
    parsed only if it contains one of the quoted type names, which keeps a pass
    over a half-gigabyte manifest that wants one table from parsing every line.
    The substring test is a gate, not the decision — a submitter cell that happens
    to hold the same word costs one extra parse and nothing else, and the parsed
    type is what selects the row. :func:`count_rows` uses the same trick.
    """
    wanted = None if types is None else set(types)
    gate = None if wanted is None else re.compile("|".join(re.escape(f'"{t}"') for t in sorted(wanted)))
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            if not line.strip():
                continue
            if gate is not None and gate.search(line) is None:
                continue
            try:
                entity = json.loads(line)
                entity_type, value = entity["type"], entity["value"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"{path.name} line {n}: not a verbatim entity: {exc!r}") from None
            if not isinstance(entity_type, str):
                raise ValueError(f"{path.name} line {n}: entity type is {type(entity_type).__name__}, not a string")
            if not isinstance(value, dict):
                raise ValueError(f"{path.name} line {n}: entity value is {type(value).__name__}, not an object")
            if wanted is None or entity_type in wanted:
                yield entity_type, value


def metadata_block(catalog: str, datasets: dict[str, dict[str, Any]], downloaded_at: datetime) -> dict[str, Any]:
    """The ``metadata`` envelope written beside ``files`` in ``anvil_files_metadata.json``.

    Records the catalog generation the files came from (issue #335: the July
    2026 snapshot could not say it was anvil14 once anvil14 was deleted), that
    they came through the manifest path, and what each dataset contributed.

    ``repository`` names who published these files, so nothing downstream has to infer
    it (#424). ``pipeline.published_source`` reads it with ``catalog`` to name the
    repository a run's ``published`` blocks came from; it used to prefix a hard-coded
    ``anvil`` there, which would have mislabelled any other repository's snapshot loaded
    through the same shared path.

    ``datasets`` maps a title to ``file_count`` plus the TDR snapshot it was
    materialised from (#434, from :func:`dataset_source`). It used to map a title to
    the bare count; the object form is the shape the sidecar already uses for the same
    key, so the two now read alike.

    **The snapshot is deliberately not on any record.** It is one value per dataset —
    12 across anvil15, measured — so a ~90-byte ``source_spec`` on each of 708,088
    records would be ~60 MB to say twelve things, and the identical string on 309,979
    consecutive rows in the ``ANVIL_T2T_CHRY`` case. Every record a corpus run writes
    already carries ``dataset_title``, which joins to this map — not *every* record, as
    ``records.OutputRecord.from_single`` leaves it None by design on the
    ``classify_single`` path. Contrast #433, whose fact genuinely varies per file and
    therefore belongs on the record.
    """
    return {
        "downloaded_at": downloaded_at.isoformat(),
        "total_files": sum(int(entry["file_count"]) for entry in datasets.values()),
        "api_url": MANIFEST_URL,
        "repository": REPOSITORY,
        "catalog": catalog,
        "source": "manifest",
        "datasets": {title: datasets[title] for title in sorted(datasets)},
    }


def write_input_files(root: Path, block: dict[str, Any], records: Iterable[dict[str, Any]]) -> int:
    """Write ``anvil_files_metadata.json`` and ``.ndjson`` under ``root`` in one streaming pass.

    ``records`` is consumed once; no more than the current record is held. The
    JSON envelope is ``{"metadata": block, "files": [...]}`` (the shape
    ``pipeline.load_records`` reads); the NDJSON is one record per line. Both
    are written to temporary files and renamed into place only after every
    record is out, so an exception mid-stream — a cell the mapping rejects —
    leaves the previous input files untouched. Returns the number written.
    """
    json_path, nd_path = root / "anvil_files_metadata.json", root / "anvil_files_metadata.ndjson"
    json_tmp, nd_tmp = json_path.with_suffix(".json.tmp"), nd_path.with_suffix(".ndjson.tmp")
    n = 0
    try:
        with json_tmp.open("w") as js, nd_tmp.open("w") as nd:
            js.write('{"metadata": ')
            json.dump(block, js)
            js.write(', "files": [')
            for record in records:
                line = json.dumps(record)
                js.write(("" if n == 0 else ", ") + line)
                nd.write(line + "\n")
                n += 1
            js.write("]}")
    except BaseException:
        # Both or neither: the previous pair stays, and the partial pair does not linger.
        json_tmp.unlink(missing_ok=True)
        nd_tmp.unlink(missing_ok=True)
        raise
    json_tmp.replace(json_path)
    nd_tmp.replace(nd_path)
    return n
