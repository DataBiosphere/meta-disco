"""Files held outside AnVIL that a dataset's files were made from: declared, pinned and cached (#710).

**A workaround.** ANVIL_T2T_CHRY's 1000 Genomes GenomicsDB workspace tars were imported from
GATK sample-name maps the dataset does not hold, in a bucket that no longer exists. The
Schatz lab published those maps on GitHub. Until AnVIL holds them (#624), this module
declares the published copies and keeps them for the dataset; when it does, the catalog
maps take over through #621's code and this module, its declaration and its cache are
deleted.

**The declaration** is ``sources/external_files.yaml``, one entry per dataset::

    catalog: anvil15
    datasets:
      ANVIL_T2T_CHRY:
        - host: github
          repository: schatzlab/t2t-chm13-chry           # owner/name
          commit: efad08780736405640560e96322479af549e15bf
          directory: alignment_variant_calling_pipeline/example_sample_maps
          sample_maps:
            chr19_sample_map.tsv:
              sha256: e7f73e01…
              named_as:                                  # the paths a tar's header names it by
                - gs://fc-c58482ad-…/sample_maps/full_sample/chr19_sample_map.tsv

**Each declared file has an address and a place.** Its address, ``ref``
(``github:schatzlab/t2t-chm13-chry@<commit>/<directory>/<name>``), is what a lineage line and
a step's input name it by. Its place in the cache is
``data/external/<dataset>/github/<owner>/<repo>/<commit>/<directory>/<name>``: the dataset
first, because the file is held for that dataset alone, as a file's parents are looked for
in its own dataset (ADR-0002 decision 2). The commit is in both, so an edit upstream is
another address and another file, never an overwrite of this one.

:func:`fetch` downloads a declared file into the cache and refuses one whose sha256 is not
the declared one; :func:`read_text` reads a cached file and refuses one that is missing or
has changed. :func:`load_external_files` checks the declaration's shape as it loads it.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path, PurePosixPath

import requests

from .cohort_steps import SAMPLE_MAP_SUFFIX
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


@dataclass(frozen=True)
class ExternalFiles:
    """A loaded declaration: the AnVIL catalog it was authored against, and one entry per dataset."""

    catalog: str
    entries: tuple[Entry, ...]

    def entry(self, dataset: str) -> Entry | None:
        return next((e for e in self.entries if e.dataset == dataset), None)

    def named(self, dataset: str, path: str) -> ExternalFile | None:
        """The sample map of ``dataset`` a file names by ``path`` (one of its ``named_as``), or None."""
        entry = self.entry(dataset)
        return next((f for f in entry.sample_maps if path in f.named_as), None) if entry is not None else None

    def by_ref(self, dataset: str, ref: str) -> ExternalFile | None:
        """The sample map of ``dataset`` whose address is ``ref``, or None: a file is held for its dataset alone."""
        entry = self.entry(dataset)
        return next((f for f in entry.sample_maps if f.ref == ref), None) if entry is not None else None


def default_external_files_resource():
    """The bundled declaration, as a package-data resource."""
    return files(f"{__package__}.sources") / "external_files.yaml"


_UniqueKeyLoader = unique_key_loader(_WHERE)


def load_external_files(source: Readable | None = None) -> ExternalFiles:
    """Load and check the declaration, the bundled one by default; ``ValueError`` naming where it is wrong.

    Checked here: the top level (``lineage_map.map_document``); one entry per dataset; the
    host, ``github`` the one there is; a repository ``owner/name``; a 40-hex commit; a
    directory; and per sample map a name ending ``_sample_map.tsv``, a 64-hex sha256 and a
    non-empty list of distinct paths, no path named for two maps of the dataset.
    """
    resource = source if source is not None else default_external_files_resource()
    document = map_document(resource, _UniqueKeyLoader, _WHERE, set())
    entries = []
    for dataset, listed in document["datasets"].items():
        at = f"{_WHERE} {dataset}"
        # The importer writes one lineage file per dataset, so a dataset has one source.
        if not isinstance(listed, list) or len(listed) != 1:
            raise ValueError(f"{at}: must be a list of one entry — one dataset, one lineage file")
        entries.append(_entry(dataset, listed[0], f"{at} entry"))
    return ExternalFiles(catalog=document["catalog"], entries=tuple(entries))


def _entry(dataset: str, entry: object, at: str) -> Entry:
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
