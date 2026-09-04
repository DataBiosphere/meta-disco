"""Pull AnVIL file metadata from Azul manifests (issue #368).

Azul serves two manifests over its file index, and this module knows how to ask
for them and how to turn one of them into the classifier's input records:

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

The HTTP session is injected so the job-following logic and the discovery parse
are testable against a fake; the default is a :mod:`requests` session.
"""

from __future__ import annotations

import csv
import io
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import requests

API_URL = "https://service.explore.anvilproject.org"
FILES_URL = f"{API_URL}/index/files"
MANIFEST_URL = f"{API_URL}/fetch/manifest/files"

FORMAT_COMPACT = "compact"
FORMAT_VERBATIM = "verbatim.jsonl"
FORMATS = (FORMAT_COMPACT, FORMAT_VERBATIM)
# On-disk suffix per format, under data/anvil/manifest/<catalog>/<dataset>.<suffix>
FORMAT_SUFFIX = {FORMAT_COMPACT: "compact.tsv", FORMAT_VERBATIM: "verbatim.jsonl"}

# Azul joins a multi-valued field with this in a compact cell.
_MULTI_VALUE_SEP = " || "


class HttpSession(Protocol):
    """The two calls this module makes, keyword arguments only; ``requests.Session``
    satisfies it, and so can a test fake. Responses are typed ``Any``: they need
    ``raise_for_status()``, ``json()`` and ``content``, which both provide."""

    def get(self, url: str, **kwargs: Any) -> Any: ...
    def put(self, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class Dataset:
    """One accessible dataset as the files facet reports it."""

    title: str
    file_count: int


def discover_datasets(catalog: str, session: HttpSession | None = None) -> list[Dataset]:
    """The datasets with accessible files in ``catalog``, with their file counts.

    Read from the ``datasets.title`` term facet of a one-hit ``/index/files``
    query. An unauthenticated caller sees only accessible files, so a dataset
    with none (``ANVIL_GTEx_public_data`` since anvil15) is simply absent here.
    Sorted by file count descending, then title, so a run's order is stable.
    """
    http: HttpSession = session if session is not None else requests.Session()
    resp = http.get(FILES_URL, params={"catalog": catalog, "size": 1}, timeout=60)
    resp.raise_for_status()
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
    sleep: Callable[[float], None] | None = None,
    timeout: float = 3600,
) -> bytes:
    """Request one manifest and follow its job to the payload bytes.

    Polls while the job reports ``Status`` 301, waiting ``Retry-After`` seconds
    (at least one) between polls, and downloads the 302 ``Location`` at once,
    because that URL is signed and expires. Raises ``TimeoutError`` if the job
    has not finished after ``timeout`` seconds of waiting, and ``RuntimeError``
    on any other status.
    """
    if fmt not in FORMATS:
        raise ValueError(f"unknown manifest format {fmt!r}; expected one of {FORMATS}")
    http: HttpSession = session if session is not None else requests.Session()
    sleep = sleep or time.sleep
    resp = http.put(
        MANIFEST_URL,
        params={"catalog": catalog, "format": fmt, "filters": manifest_filters(dataset_title)},
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    waited = 0.0
    while body.get("Status") == 301:
        wait = max(float(body.get("Retry-After", 1)), 1.0)
        if waited + wait > timeout:
            raise TimeoutError(f"manifest job for {dataset_title!r} ({fmt}) still running after {waited:.0f}s")
        sleep(wait)
        waited += wait
        resp = http.get(body["Location"], timeout=120)
        resp.raise_for_status()
        body = resp.json()
    if body.get("Status") != 302:
        raise RuntimeError(f"unexpected manifest job response for {dataset_title!r} ({fmt}): {body}")
    payload = http.get(body["Location"], timeout=1800)
    payload.raise_for_status()
    return payload.content


def count_rows(fmt: str, payload: bytes) -> int:
    """Files a manifest payload describes: compact data rows, or verbatim ``anvil_file`` lines."""
    if fmt == FORMAT_COMPACT:
        return max(payload.count(b"\n") - 1, 0)
    return sum(1 for line in payload.splitlines() if line.strip() and json.loads(line).get("type") == "anvil_file")


def parity_problems(datasets: Iterable[Dataset], counts: dict[tuple[str, str], int]) -> list[str]:
    """One line per (dataset, format) whose row count disagrees with the facet's file count.

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
                    f"{dataset.title}: {fmt} has {got:,} files, the catalog facet says {dataset.file_count:,}"
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
    Empty cells become ``None``; ``file_size`` is an int and
    ``is_supplementary`` a bool, as the contract's strict validation requires.
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
        "is_supplementary": row["files.is_supplementary"] == "True",
        "drs_uri": row["files.drs_uri"],
        "dataset_id": row["datasets.dataset_id"],
        "dataset_title": row["datasets.title"],
        "organism_type": row.get("donors.organism_type") or None,
        "phenotypic_sex": row.get("donors.phenotypic_sex") or None,
    }


def records_from_compact(payload: bytes) -> list[dict[str, Any]]:
    """Every record in one compact manifest payload, in manifest order."""
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8")), delimiter="\t")
    return [record_from_compact_row(row) for row in reader]


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
