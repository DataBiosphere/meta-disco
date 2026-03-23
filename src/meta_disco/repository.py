"""Repository configuration for multi-source evidence storage.

Each data repository (AnVIL, HPRC, HCA) stores files at different URLs and
uses different identifiers. RepoConfig encapsulates these differences so
classify scripts can work with any repository.

Evidence layout: data/{repo}/evidence/{filetype}/{key[:2]}/{key}.json
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoConfig:
    """Configuration for a data repository."""

    name: str
    evidence_base: Path

    def evidence_dir(self, filetype: str) -> Path:
        """Evidence directory for a file type (bam, vcf, fastq, fasta, bed)."""
        return self.evidence_base / filetype

    def get_key(self, record: dict) -> str | None:
        """Extract cache key from a record. Override per repo."""
        raise NotImplementedError

    def get_url(self, record: dict) -> str | None:
        """Build fetch URL from a record. Override per repo."""
        raise NotImplementedError

    def get_filename(self, record: dict) -> str:
        """Extract filename from a record."""
        return record.get("file_name", "") or record.get("filename", "")

    def get_file_size(self, record: dict) -> int | None:
        """Extract file size from a record."""
        size = record.get("file_size") or record.get("fileSize")
        if isinstance(size, str):
            try:
                return int(size)
            except ValueError:
                return None
        return size

    def get_file_format(self, record: dict) -> str:
        """Extract file format from a record."""
        return record.get("file_format", "") or record.get("filetype", "")


class AnvilConfig(RepoConfig):
    """AnVIL repository — files keyed by md5, served from S3 mirror."""

    S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"

    def __init__(self):
        super().__init__(
            name="anvil",
            evidence_base=Path("data/anvil/evidence"),
        )

    def get_key(self, record: dict) -> str | None:
        return record.get("file_md5sum")

    def get_url(self, record: dict) -> str | None:
        key = self.get_key(record)
        if not key:
            return None
        return f"{self.S3_MIRROR_URL}/{key}.md5"


class HprcConfig(RepoConfig):
    """HPRC repository — no content hashes, keyed by sha256 of S3 path."""

    # Catalog field name -> URL field in that catalog's records
    _URL_FIELDS = {
        "sequencing-data": "path",
        "alignments": "loc",
        "annotations": "fileLocation",
        "assemblies": "awsFasta",
    }

    def __init__(self):
        super().__init__(
            name="hprc",
            evidence_base=Path("data/hprc/evidence"),
        )

    def get_key(self, record: dict) -> str | None:
        """Hash the S3 path to produce a stable cache key."""
        url = self._raw_url(record)
        if not url:
            return None
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def get_url(self, record: dict) -> str | None:
        raw = self._raw_url(record)
        if not raw:
            return None
        return _s3_to_https(raw)

    def _raw_url(self, record: dict) -> str | None:
        """Extract the raw URL string from whichever catalog field is present."""
        for field in self._URL_FIELDS.values():
            val = record.get(field, "")
            if val and val != "N/A":
                return val
        return None


def _s3_to_https(url: str) -> str:
    """Convert s3://bucket/key to HTTPS. Pass through existing HTTPS URLs."""
    if url.startswith("https://"):
        return url
    if url.startswith("s3://"):
        return f"https://s3-us-west-2.amazonaws.com/{url[5:]}"
    raise ValueError(f"Unsupported URL scheme: {url}")


# Singletons for convenience
ANVIL = AnvilConfig()
HPRC = HprcConfig()

REPOS = {"anvil": ANVIL, "hprc": HPRC}


def get_repo(name: str) -> RepoConfig:
    """Look up a RepoConfig by name."""
    repo = REPOS.get(name)
    if not repo:
        raise ValueError(f"Unknown repository: {name!r}. Choose from: {list(REPOS)}")
    return repo
