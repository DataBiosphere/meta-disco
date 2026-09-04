"""Pull AnVIL file metadata from Azul manifests (issue #368).

Azul serves two manifests over its file index, and this module knows how to ask
for them, where to keep them, and how to turn one of them into the classifier's
input records:

- ``compact`` — one tab-separated row per file: the harmonized join Azul
  materializes from its bundle structure (file, dataset, donor, biosample,
  activity columns). This is the source of ``anvil_files_metadata.json``.
- ``verbatim.jsonl`` — one ``{"type", "value"}`` line per entity: the harmonized
  ``anvil_*`` entities plus the submitter's own Terra tables, unaltered. Stored
  beside the compact manifest as the import-primary source; nothing here reads
  it beyond counting its ``anvil_file`` lines for parity.

The two are complementary, not nested: verbatim carries every entity but not
Azul's join, so a per-file record cannot be rebuilt from it for every dataset
(measured on #337: on 1000G the join reaches a donor for 25,616 files, the
entity chain for 9,603). Verbatim entities also carry no dataset field, which is
why manifests are requested one dataset at a time — the request's filter is
what attributes a raw table to its dataset.

A manifest is a job, not a download: ``PUT /fetch/manifest/files`` answers with
JSON carrying ``Status`` 301 and a ``Location`` to poll after ``Retry-After``
seconds, until a ``Status`` 302 whose ``Location`` is a signed, expiring URL for
the payload. :func:`fetch_manifest` follows that to the bytes.

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

FORMAT_COMPACT = "compact"
FORMAT_VERBATIM = "verbatim.jsonl"
FORMATS = (FORMAT_COMPACT, FORMAT_VERBATIM)
# On-disk suffix per format.
FORMAT_SUFFIX = {FORMAT_COMPACT: "compact.tsv", FORMAT_VERBATIM: "verbatim.jsonl"}
SIDECAR = "manifests.json"

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


class HttpSession(Protocol):
    """The two calls this module makes, keyword arguments only; ``requests.Session``
    satisfies it, and so can a test fake. Responses are typed ``Any``: they need
    ``status_code``, ``headers``, ``raise_for_status()``, ``json()`` and
    ``content``, which both provide."""

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
    session: HttpSession | None = None,
    sleep: Sleep = time.sleep,
    timeout: float = 3600,
    max_wait: float = DEFAULT_MAX_WAIT,
    log: Log | None = None,
) -> bytes:
    """Request one manifest and follow its job to the payload bytes.

    Polls while the job reports ``Status`` 301, waiting ``Retry-After`` seconds
    (at least one) between polls, and downloads the 302 ``Location`` at once,
    because that URL is signed and expires. Each HTTP call goes through
    :func:`_request`, so a 429 or gateway error is waited out for up to
    ``max_wait`` seconds per call, each wait reported through ``log``. Raises
    ``TimeoutError`` if the job has not finished after ``timeout`` seconds of
    polling, and ``RuntimeError`` on any other job status.
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
    return call("get", body["Location"], timeout=1800).content


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


def save_sidecar(root: Path, catalog: str, sidecar: dict[str, Any]) -> None:
    directory = manifest_dir(root, catalog)
    directory.mkdir(parents=True, exist_ok=True)
    _write_atomically(directory / SIDECAR, lambda f: json.dump(sidecar, f, indent=2, sort_keys=True))


def _write_atomically(path: Path, write: Callable[[Any], None]) -> None:
    """Write through a temporary file and rename, so a failure mid-write leaves the previous file."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as f:
        write(f)
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
        return sum(1 for line in f if b'"anvil_file"' in line and json.loads(line).get("type") == "anvil_file")


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

    The retired page downloader took element zero of the list Azul returned for
    ``data_modality`` and ``reference_assembly``; this is the same choice on the
    compact spelling of that list.
    """
    if not cell:
        return None
    return cell.split(_MULTI_VALUE_SEP, 1)[0] or None


def record_from_compact_row(row: dict[str, str]) -> dict[str, Any]:
    """One classifier input record from one compact-manifest row.

    The keys are the input contract (``schema/metadata.yaml``) plus the two
    donor fields the page downloader also emitted and the contract ignores.
    ``file_size`` is an int and ``is_supplementary`` a bool, as the contract's
    strict validation requires; a cell that is not one of Azul's ``True`` /
    ``False`` spellings raises rather than silently becoming ``False``. The
    four nullable fields — ``data_modality``, ``reference_assembly``,
    ``organism_type``, ``phenotypic_sex`` — read an empty cell as ``None`` and
    a multi-valued one as its first value, which is what the page downloader
    emitted for them; every other field is passed through as the cell's text,
    and the contract's non-empty patterns are what reject a blank one.
    """
    return {
        "entry_id": row["files.document_id"],
        "file_id": row["files.file_id"],
        "file_name": row["files.file_name"],
        "file_format": row["files.file_format"],
        "file_size": int(row["files.file_size"]),
        "file_md5sum": row["files.file_md5sum"],
        "data_modality": _first(row.get("files.data_modality", "")),
        "reference_assembly": _first(row.get("files.reference_assembly", "")),
        "is_supplementary": _BOOL_CELL[row["files.is_supplementary"]],
        "drs_uri": row["files.drs_uri"],
        "dataset_id": row["datasets.dataset_id"],
        "dataset_title": row["datasets.title"],
        "organism_type": _first(row.get("donors.organism_type", "")),
        "phenotypic_sex": _first(row.get("donors.phenotypic_sex", "")),
    }


def iter_compact_records(path: Path) -> Iterator[dict[str, Any]]:
    """Every record in one compact manifest on disk, in manifest order, streamed."""
    with path.open(newline="", encoding="utf-8") as f:
        for n, row in enumerate(csv.DictReader(f, delimiter="\t"), start=2):
            try:
                yield record_from_compact_row(row)
            except (KeyError, ValueError) as exc:
                raise ValueError(f"{path.name} line {n}: cannot map row to a record: {exc!r}") from None


def metadata_block(catalog: str, dataset_counts: dict[str, int], downloaded_at: datetime) -> dict[str, Any]:
    """The ``metadata`` envelope written beside ``files`` in ``anvil_files_metadata.json``.

    Records the catalog generation the files came from (issue #335: the July
    2026 snapshot could not say it was anvil14 once anvil14 was deleted), that
    they came through the manifest path, and how many each dataset contributed.
    """
    return {
        "downloaded_at": downloaded_at.isoformat(),
        "total_files": sum(dataset_counts.values()),
        "api_url": MANIFEST_URL,
        "catalog": catalog,
        "source": "manifest",
        "datasets": dict(sorted(dataset_counts.items())),
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
    # Both or neither: a failure above leaves the previous pair in place.
    json_tmp.replace(json_path)
    nd_tmp.replace(nd_path)
    return n
