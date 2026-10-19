"""Files held outside AnVIL that a dataset's files were made from: declared, pinned and cached (#710).

**A workaround.** ANVIL_T2T_CHRY's 1000 Genomes GenomicsDB workspace tars were imported from
sample-name maps the dataset does not hold; the Schatz lab published them on GitHub. Until
AnVIL holds them (#624), this module declares and keeps the published copies; then the
catalog maps take over (#621) and this module, its declaration and its cache are deleted.

**The declaration** is ``sources/external_files.yaml``, one entry per dataset::

    catalog: anvil15
    datasets:
      ANVIL_T2T_CHRY:
        host: github
        repository: schatzlab/t2t-chm13-chry           # owner/name
        commit: efad08780736405640560e96322479af549e15bf
        directory: alignment_variant_calling_pipeline/example_sample_maps
        sample_maps:
          chr19_sample_map.tsv:
            sha256: e7f73e01…
            named_as:                                  # the paths a tar's header names it by
              - gs://fc-c58482ad-…/sample_maps/full_sample/chr19_sample_map.tsv

**A declared file's address**, ``ref`` (``github:<owner>/<repo>@<commit>/<path>``), is what a
lineage line and a step's input name it by; its cache path puts the dataset first
(``data/external/<dataset>/github/…``), as it is held for that dataset alone (ADR-0002 decision
2). The commit is in both, so an edit upstream is another file, never an overwrite.

:func:`fetch` downloads a declared file into the cache and refuses one whose sha256 is not
the declared one; :func:`read_text` reads a cached file and refuses one that is missing or
has changed, and :func:`read_sample_map` reads its rows. :func:`load_external_files` checks the declaration's shape as it loads it.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path, PurePosixPath

import requests

from .cohort_steps import SAMPLE_MAP_SUFFIX, parse_sample_map
from .lineage_map import expect_keys, expect_mapping, expect_name, map_document
from .slot_map import Readable, unique_key_loader

DEFAULT_EXTERNAL_ROOT = Path(__file__).resolve().parents[2] / "data" / "external"
GITHUB = "github"
# Where a GitHub file is downloaded from, at a commit.
GITHUB_RAW = "https://raw.githubusercontent.com"

_WHERE = "external files"
_ENTRY_KEYS = {"host", "repository", "commit", "directory", "sample_maps"}
_MAP_KEYS = {"sha256", "named_as"}
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_COMMIT = re.compile(r"^[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"^[0-9a-f]{64}\Z")


class ExternalFileError(ValueError):
    """A declared file that is not in the cache, or whose content is not the declared one."""


@dataclass(frozen=True)
class ExternalFile:
    """One declared file: the dataset it is held for, where it is published, and its pinned content."""

    dataset: str
    host: str
    repository: str
    commit: str
    path: str
    sha256: str
    # Every path a file of the dataset names this one by (a tar header's `--sample-name-map`).
    named_as: tuple[str, ...]

    @property
    def name(self) -> str:
        return PurePosixPath(self.path).name

    @property
    def ref(self) -> str:
        """The file's address: ``<host>:<owner>/<repo>@<commit>/<path>``."""
        return f"{self.host}:{self.repository}@{self.commit}/{self.path}"

    @property
    def url(self) -> str:
        """Where the file is downloaded from, at its commit."""
        return f"{GITHUB_RAW}/{self.repository}/{self.commit}/{self.path}"

    def cache_path(self, root: Path) -> Path:
        """Where the file is kept under ``root``: the dataset first, then its address's parts."""
        return root / self.dataset / self.host / self.repository / self.commit / self.path


@dataclass(frozen=True)
class Entry:
    """One dataset's declared source: a repository at a commit, and the sample maps of one directory in it."""

    dataset: str
    host: str
    repository: str
    commit: str
    directory: str
    sample_maps: tuple[ExternalFile, ...]

    @property
    def url(self) -> str:
        """The directory's page at the commit, as the lineage file's envelope names its source."""
        return f"https://github.com/{self.repository}/tree/{self.commit}/{self.directory}"

    def named(self, path: str) -> ExternalFile | None:
        """The sample map a file names by ``path`` (one of its ``named_as``), or None."""
        return next((f for f in self.sample_maps if path in f.named_as), None)

    def by_ref(self, ref: str) -> ExternalFile | None:
        """The sample map whose address is ``ref``, or None."""
        return next((f for f in self.sample_maps if f.ref == ref), None)


@dataclass(frozen=True)
class ExternalFiles:
    """A loaded declaration: the AnVIL catalog it was authored against, and one entry per dataset."""

    catalog: str
    entries: tuple[Entry, ...]

    def by_ref(self, dataset: str, ref: str) -> ExternalFile | None:
        """The sample map of ``dataset`` whose address is ``ref``, or None: a file is held for its dataset alone."""
        entry = next((e for e in self.entries if e.dataset == dataset), None)
        return entry.by_ref(ref) if entry is not None else None


def default_external_files_resource():
    """The bundled declaration, as a package-data resource."""
    return files(f"{__package__}.sources") / "external_files.yaml"


_UniqueKeyLoader = unique_key_loader(_WHERE)


def load_external_files(source: Readable | None = None) -> ExternalFiles:
    """Load and check the declaration, the bundled one by default; ``ValueError`` naming where it is wrong.

    Checked here: the top level (``lineage_map.map_document``); a dataset name that is one
    directory name; per dataset its entry's
    host, ``github`` the one there is; a repository ``owner/name``; a 40-hex commit; a
    directory, no part of it or of the repository ``.`` or ``..``; and per sample map a name ending ``_sample_map.tsv``, a 64-hex sha256 and a
    non-empty list of distinct paths, no path named for two maps of the dataset; and no file
    declared for two datasets.
    """
    resource = source if source is not None else default_external_files_resource()
    document = map_document(resource, _UniqueKeyLoader, _WHERE, set())
    entries = []
    held: dict[str, str] = {}
    for dataset, entry in document["datasets"].items():
        entries.append(_entry(dataset, entry, f"{_WHERE} {dataset}"))
        for file in entries[-1].sample_maps:
            # Reconcile holds a file under its address alone, so one address serves one dataset.
            if file.ref in held:
                raise ValueError(f"{_WHERE}: {file.ref} is declared for both {held[file.ref]} and {dataset}")
            held[file.ref] = dataset
    return ExternalFiles(catalog=document["catalog"], entries=tuple(entries))


def _entry(dataset: str, entry: object, at: str) -> Entry:
    if not isinstance(dataset, str) or dataset in (".", "..") or "/" in dataset or not dataset:
        raise ValueError(f"{at}: the dataset {dataset!r} is not one directory name")
    expect_keys(entry, _ENTRY_KEYS, _ENTRY_KEYS, at)
    assert isinstance(entry, dict)
    host = expect_name(entry["host"], f"{at} host")
    if host != GITHUB:
        raise ValueError(f"{at} host: is {host!r}; {GITHUB!r} is the one host declared files are fetched from")
    repository = expect_name(entry["repository"], f"{at} repository")
    if not _REPOSITORY.match(repository):
        raise ValueError(f"{at} repository: is {repository!r}, not owner/name")
    commit = entry["commit"]
    if not isinstance(commit, str) or not _COMMIT.match(commit):
        raise ValueError(f"{at} commit: is {commit!r}, not a full 40-character commit hash")
    directory = expect_name(entry["directory"], f"{at} directory").strip("/")
    if any(part in (".", "..", "") for part in (*repository.split("/"), *directory.split("/"))):
        raise ValueError(f"{at}: a repository or directory part is '.', '..' or empty")
    expect_mapping(entry["sample_maps"], f"{at} sample_maps", "file")
    maps = []
    seen: dict[str, str] = {}
    for name, declared in entry["sample_maps"].items():
        where = f"{at} sample_maps {name}"
        if not isinstance(name, str) or "/" in name or not name.lower().endswith(SAMPLE_MAP_SUFFIX):
            raise ValueError(f"{where}: not a file name ending {SAMPLE_MAP_SUFFIX}")
        expect_keys(declared, _MAP_KEYS, _MAP_KEYS, where)
        sha256 = declared["sha256"]
        if not isinstance(sha256, str) or not _SHA256.match(sha256):
            raise ValueError(f"{where} sha256: is {sha256!r}, not 64 lowercase hex characters")
        named_as = declared["named_as"]
        if not isinstance(named_as, list) or not named_as or not all(isinstance(p, str) and p for p in named_as):
            raise ValueError(f"{where} named_as: must be a non-empty list of paths")
        for path in named_as:
            if path in seen:
                raise ValueError(f"{where} named_as: {path} is also named for {seen[path]}")
            seen[path] = name
        maps.append(ExternalFile(dataset, host, repository, commit, f"{directory}/{name}", sha256, tuple(named_as)))
    return Entry(dataset, host, repository, commit, directory, tuple(maps))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


Download = Callable[[str], bytes]


def download(url: str) -> bytes:
    """The bytes at ``url``; ``requests.HTTPError`` on a status other than 200."""
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


def fetch(file: ExternalFile, root: Path, get: Download = download) -> bool:
    """Put ``file`` in the cache under ``root``; return whether it was downloaded (False: already there).

    A cached copy whose sha256 is the declared one is kept as it is. Otherwise the file is
    downloaded, and refused (``ExternalFileError``, nothing written) unless its sha256 is
    the declared one; it is written beside its place and renamed into it, so a cut-off
    write leaves no file that looks whole.
    """
    path = file.cache_path(root)
    if path.is_file() and _sha256(path.read_bytes()) == file.sha256:
        return False
    data = get(file.url)
    found = _sha256(data)
    if found != file.sha256:
        raise ExternalFileError(f"{file.url}: sha256 {found}, declared {file.sha256}; not kept")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_bytes(data)
    partial.replace(path)
    return True


def read_sample_map(file: ExternalFile, root: Path) -> tuple[tuple[str, str], ...]:
    """The rows, ``(sample, path)``, of a cached declared sample map (``cohort_steps.parse_sample_map``).

    ``ExternalFileError`` where :func:`read_text` refuses it, or it is no sample map.
    """
    rows = parse_sample_map(read_text(file, root))
    if rows is None:
        raise ExternalFileError(f"{file.ref}: not a sample map (rows of a sample and a VCF path)")
    return rows


def read_text(file: ExternalFile, root: Path) -> str:
    """The cached text of ``file`` under ``root``.

    ``ExternalFileError`` where it is not cached (``make fetch-external-files`` puts it
    there) or its sha256 is not the declared one.
    """
    path = file.cache_path(root)
    if not path.is_file():
        raise ExternalFileError(f"{file.ref}: not in the cache at {path}; run `make fetch-external-files`")
    data = path.read_bytes()
    if _sha256(data) != file.sha256:
        raise ExternalFileError(f"{path}: sha256 {_sha256(data)}, declared {file.sha256}")
    return data.decode("utf-8")
