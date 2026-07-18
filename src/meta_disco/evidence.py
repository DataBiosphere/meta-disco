"""Typed cached-evidence records the fetchers persist to the local evidence cache.

Each fetcher reads a header/metadata sample from a file on S3 and caches what it
found under ``evidence_dir/<md5[:2]>/<md5>.json`` for resumability and audit. The
cache used to be five hand-rolled ``dict`` builders in ``fetchers.py`` whose shapes
had already drifted apart (#206): BAM omitted the ``raw_bytes_fetched`` every other
fetcher wrote, the per-type element count was named three different ways
(``header_line_count`` / ``contig_count`` / ``tagged_segment_count``), and each
cache-hit read was a bespoke silently-defaulting probe over a per-type payload key —
a key mismatch just missed the cache and re-fetched.

:class:`CachedEvidence` is the shared core (the ``md5sum`` cache key + fetch provenance
+ the save/load persistence boundary); each subclass adds its one typed payload field and
names it via the ``PAYLOAD_KEY`` classvar, which drives both the ``.payload`` accessor
and the on-disk key. The element count is a derived :pyattr:`~CachedEvidence.count`
property, no longer persisted, so the three-way count-key drift is gone by
construction. ``raw_bytes_fetched`` is ``int | None`` and stays ``None`` for BAM,
which reads a samtools stream and has no byte-range count to report — modeled, not
fabricated.

On-disk format is backward-readable: payload keys keep their names, so an evidence
file written before #206 loads fine — :meth:`~CachedEvidence.from_json` reads the
required keys and ``.get``-optional provenance, and simply ignores the dropped count.
This is not a compatibility shim: it parses the current schema and ignores audit
extras it no longer stores.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, ClassVar


def get_evidence_path(evidence_dir: Path, md5sum: str) -> Path:
    """Get path for cached evidence file.

    Uses first 2 chars of MD5 as subdirectory to avoid too many files in one dir.
    """
    return evidence_dir / md5sum[:2] / f"{md5sum}.json"


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass(frozen=True, kw_only=True)
class CachedEvidence:
    """Shared core of a fetcher's cached evidence: the cache key, provenance, persistence.

    Subclasses add exactly one typed payload field and set :pyattr:`PAYLOAD_KEY` to
    its name; that classvar is the single source of the on-disk payload key and backs
    the :pyattr:`payload` accessor, so no consumer hard-codes a per-type key.

    The cache is keyed by ``md5sum`` alone (the on-disk path is ``md5[:2]/md5.json``);
    a hit needs only ``md5sum`` plus a payload. ``file_name`` is echoed *audit*
    metadata — no consumer reads it back (the fetcher returns the payload) — so a file
    missing it still hits rather than forcing an expensive re-fetch over a non-key
    field. ``raw_bytes_fetched`` is the size of the byte range a range-request fetcher
    read; it is ``None`` for BAM, whose ``samtools`` stream has no such count.
    ``source_url`` is recorded only when the fetch used a direct URL rather than the S3
    mirror. ``fetch_timestamp`` defaults to now at construction and is preserved
    verbatim on a round-trip through :meth:`from_json`; a file that lacks it loads with
    ``""`` (unknown fetch time), never a fabricated current timestamp.
    """

    # Set by each subclass to its payload field name; also the on-disk key.
    PAYLOAD_KEY: ClassVar[str]
    # When True, an empty payload is a cache miss, not a hit: BAM/VCF/FASTQ never
    # persist an empty payload (they raise FetchError instead), so an empty one on
    # disk is a corrupt artifact and the fetcher must re-fetch. FASTA/GFA leave this
    # False — an empty list is a valid read (a plain GFA has no tags; a head may hold
    # no contig line). This restores the per-type truthiness the pre-#206 cache-hit
    # guards had.
    _EMPTY_IS_MISS: ClassVar[bool] = False

    md5sum: str
    file_name: str
    raw_bytes_fetched: int | None = None
    source_url: str | None = None
    fetch_timestamp: str = field(default_factory=_timestamp)

    @property
    def payload(self) -> Any:
        """The typed per-type payload (e.g. header text, read names, segment tags)."""
        return getattr(self, self.PAYLOAD_KEY)

    @property
    def count(self) -> int:
        """Number of payload elements — list length for the list payloads.

        Overridden for the text payloads (BAM/VCF), where the meaningful count is
        header lines, not characters.
        """
        return len(self.payload)

    def to_json(self) -> dict:
        """Serialize to the cached JSON dict: identity, payload, and present provenance.

        ``raw_bytes_fetched``/``source_url`` are omitted when ``None`` (BAM never
        records bytes; a mirror fetch records no source URL), matching the old
        conditional-insert behavior.
        """
        data: dict = {
            "md5sum": self.md5sum,
            "file_name": self.file_name,
            self.PAYLOAD_KEY: self.payload,
            "fetch_timestamp": self.fetch_timestamp,
        }
        if self.raw_bytes_fetched is not None:
            data["raw_bytes_fetched"] = self.raw_bytes_fetched
        if self.source_url is not None:
            data["source_url"] = self.source_url
        return data

    @classmethod
    def from_json(cls, data: object) -> Any:
        """Build from a cached JSON dict, or return ``None`` for a cache miss.

        Structural validation of an external artifact at the cache boundary — not a
        defensive default over our own inputs. Returns ``None`` (the fetcher then
        re-fetches) when the top-level JSON is not an object, the required ``md5sum``
        (the cache key) or payload key is absent, or the payload is empty for a type
        that never persists an empty one (``_EMPTY_IS_MISS``). ``file_name`` and the
        provenance fields are non-key audit metadata, read with ``.get`` and absent-
        tolerant, so a file missing them still hits; payload *value types* are not
        checked, and a dropped count key (pre-#206 files) is simply not read.
        """
        if not isinstance(data, dict) or "md5sum" not in data or cls.PAYLOAD_KEY not in data:
            return None
        if cls._EMPTY_IS_MISS and not data[cls.PAYLOAD_KEY]:
            return None
        return cls(
            md5sum=data["md5sum"],
            file_name=data.get("file_name", ""),
            raw_bytes_fetched=data.get("raw_bytes_fetched"),
            source_url=data.get("source_url"),
            fetch_timestamp=data.get("fetch_timestamp", ""),
            **{cls.PAYLOAD_KEY: data[cls.PAYLOAD_KEY]},
        )

    def save(self, evidence_dir: Path) -> None:
        """Write this evidence to its cache path under ``evidence_dir``."""
        path = get_evidence_path(evidence_dir, self.md5sum)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2)

    @classmethod
    def load(cls, evidence_dir: Path, md5sum: str) -> Any:
        """Load cached evidence for ``md5sum``, or ``None`` on any miss.

        A missing file, an unreadable file, one that is not valid UTF-8 or not valid
        JSON, or one lacking this type's required keys all yield ``None`` so the caller
        re-fetches — the cache is an optimization, never a trusted source.
        """
        path = get_evidence_path(evidence_dir, md5sum)
        if not path.exists():
            return None
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        return cls.from_json(data)


@dataclass(frozen=True, kw_only=True)
class _TextEvidence(CachedEvidence):
    """Shared core of the two header-text payloads (BAM/VCF).

    Their payload is a header *string*, so the meaningful :pyattr:`count` is header
    lines rather than the base's element count, and both name their payload
    ``header_text``. That shared trio (payload field, key, count) lives here so the
    two subclasses don't each re-declare it.
    """

    PAYLOAD_KEY: ClassVar[str] = "header_text"
    _EMPTY_IS_MISS: ClassVar[bool] = True  # a valid BAM/VCF always has header lines

    header_text: str

    @property
    def count(self) -> int:
        """Header line count (the meaningful tally for a text payload)."""
        return len(self.header_text.splitlines())


@dataclass(frozen=True, kw_only=True)
class BamEvidence(_TextEvidence):
    """Cached SAM header text from a BAM/CRAM read. ``raw_bytes_fetched`` is always None."""


@dataclass(frozen=True, kw_only=True)
class VcfEvidence(_TextEvidence):
    """Cached VCF header text, plus the optional per-chromosome max-position audit map.

    ``max_positions`` is written for audit when the fetcher extracted it; it is not
    read back from the cache (the returned payload is the header text), so it is an
    optional provenance extra rather than part of :pyattr:`payload`.
    """

    max_positions: dict | None = None

    def to_json(self) -> dict:
        data = super().to_json()
        if self.max_positions:
            data["max_positions"] = self.max_positions
        return data

    @classmethod
    def from_json(cls, data: object) -> Any:
        # Delegate the shared identity/payload/provenance parse (and the cache-miss
        # guard) to the base, then graft on the one Vcf-only audit field, so a new
        # base provenance field can't silently miss this subclass on load.
        base = super().from_json(data)
        if base is None:
            return None
        assert isinstance(data, dict)  # base returned non-None ⇒ data parsed as a dict
        return replace(base, max_positions=data.get("max_positions"))


@dataclass(frozen=True, kw_only=True)
class FastqEvidence(CachedEvidence):
    """Cached FASTQ read-name lines. Empty is a miss — the fetcher raises without any."""

    PAYLOAD_KEY: ClassVar[str] = "read_names"
    _EMPTY_IS_MISS: ClassVar[bool] = True

    read_names: list[str]


@dataclass(frozen=True, kw_only=True)
class FastaEvidence(CachedEvidence):
    """Cached FASTA contig names. An empty list is a valid hit (a head with no contig line)."""

    PAYLOAD_KEY: ClassVar[str] = "contig_names"

    contig_names: list[str]


@dataclass(frozen=True)
class SegmentTag:
    """The rGFA stable-sequence tags on one GFA segment (S) line (#207).

    In rGFA each segment carries a stable rank ``SR`` naming which sequence it came
    from — rank ``"0"`` is the reference backbone — and ``SN`` names its contig. Both
    are kept as the strings they are on disk: ``sr`` is compared as ``"0"`` and ``sn``
    is sorted as text, so coercing ``sr`` to ``int`` would break the comparison and
    change the JSON. Either may be absent (``None``); ``parse_gfa_segment_tags`` only
    emits a tag when at least one is present.

    :pyattr:`is_reference_backbone` moves the "rank 0 ⇒ reference backbone" semantics —
    which used to live only in the reader — onto the type.
    """

    sn: str | None = None
    sr: str | None = None

    @property
    def is_reference_backbone(self) -> bool:
        """True when this segment is a named rank-0 (reference-backbone) segment.

        ``bool(self.sn)`` (not ``sn is not None``) preserves the reader's original
        truthy ``t.get("SN")`` test: a blank ``SN:Z:`` (empty-string name) does not
        anchor a reference claim, exactly as before #207.
        """
        return self.sr == "0" and bool(self.sn)

    def to_json(self) -> dict:
        """Serialize to the on-disk tag dict, omitting absent keys (``SN`` before ``SR``).

        Reproduces the exact dict ``parse_gfa_segment_tags`` used to build, so the
        cached ``gfa_segment_tags`` array is byte-identical to the pre-#207 format.
        """
        data: dict = {}
        if self.sn is not None:
            data["SN"] = self.sn
        if self.sr is not None:
            data["SR"] = self.sr
        return data

    @classmethod
    def from_json(cls, data: dict) -> SegmentTag:
        """Build from an on-disk tag dict (absent ``SN``/``SR`` become ``None``)."""
        return cls(sn=data.get("SN"), sr=data.get("SR"))


@dataclass(frozen=True, kw_only=True)
class GfaEvidence(CachedEvidence):
    """Cached rGFA segment tags. An empty list is a valid hit (a plain GFA carries none)."""

    PAYLOAD_KEY: ClassVar[str] = "gfa_segment_tags"

    gfa_segment_tags: list[SegmentTag]

    def to_json(self) -> dict:
        # The payload is typed SegmentTags; serialize each to its on-disk dict.
        data = super().to_json()
        data[self.PAYLOAD_KEY] = [tag.to_json() for tag in self.gfa_segment_tags]
        return data

    @classmethod
    def from_json(cls, data: object) -> Any:
        # Delegate identity/provenance parse + the cache-miss guard to the base, then
        # rebuild the payload as typed SegmentTags (base built it as raw dicts).
        base = super().from_json(data)
        if base is None:
            return None
        assert isinstance(data, dict)  # base returned non-None ⇒ data parsed as a dict
        return replace(base, gfa_segment_tags=[SegmentTag.from_json(x) for x in data[cls.PAYLOAD_KEY]])
