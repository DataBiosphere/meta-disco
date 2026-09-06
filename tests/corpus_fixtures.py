"""Corpus-drift guard for the ``@pytest.mark.e2e`` eval fixtures (issue #381).

The eval tests in ``test_evals.py`` pin a file by ``md5sum`` and classify it through
the real script functions, which read the evidence cache the pipeline wrote. Both
ends of that drift: a catalog migration replaces the corpus, so a pinned md5 stops
being a file AnVIL has, and its cached evidence is never rewritten. Before this
module such a fixture fell through to a live S3 range request that 404'd, and the
suite reported a puzzling fetch failure instead of naming the cause.

:func:`require_corpus_file` turns both cases into a skip whose reason says which one
it is. It also keeps the eval tests off the network altogether: it asks the cache the
same question the fetcher will — ``CachedEvidence.load``, not merely "does a file
exist" — so a fixture whose classify call would fetch skips rather than try.
Every fetching call in ``test_evals.py`` goes through a wrapper that calls this first.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest

from meta_disco.evidence import (
    BamEvidence,
    CachedEvidence,
    FastaEvidence,
    FastqEvidence,
    VcfEvidence,
    get_evidence_path,
)

# The corpus snapshot `make classify` runs against, and the evidence cache it writes.
# Both are CWD-relative, mirroring the code's own defaults (Makefile, pipeline.py), so
# the guard looks exactly where a real run would.
SNAPSHOT = Path("data/anvil/anvil_files_metadata.json")
EVIDENCE_BASE = Path("data/evidence/anvil")

# The typed record each fetcher caches, keyed by FileTypeConfig.name. FileTypeConfig
# binds the fetcher rather than the evidence class, and each fetcher names its class
# internally, so the association is restated here. A file type missing from this map
# raises rather than skipping: an unguarded eval test is worth an error, a silently
# skipped one is not.
EVIDENCE_CLASSES: dict[str, type[CachedEvidence]] = {
    "bam": BamEvidence,
    "vcf": VcfEvidence,
    "fastq": FastqEvidence,
    "fasta": FastaEvidence,
}

_MD5_FIELD = re.compile(rb'"file_md5sum":\s*"([0-9a-f]{32})"')
_CHUNK = 4 * 1024 * 1024
# `"file_md5sum":"<32 hex>"` with no separator whitespace — the shortest span the regex
# can match, and the width the overlap is built from.
_MIN_FIELD_BYTES = 48
# Consecutive chunks overlap by this much, so a field straddling a read boundary is
# still seen whole by one of them. That works for any field no longer than the overlap;
# `\s*` after the colon makes the true maximum unbounded, so this is the minimum plus a
# margin for separator whitespace — json.dump writes one space, or none when compact.
_OVERLAP = _MIN_FIELD_BYTES + 16


@lru_cache
def snapshot_md5s(snapshot: Path) -> frozenset[bytes]:
    """Every ``file_md5sum`` in ``snapshot``, or an empty set if it is absent.

    Scanned with a regex over fixed-size chunks rather than ``json.load``: the snapshot
    is ~376 MB and holds ~708K records, which would parse into hundreds of MB of dicts
    to answer a membership test. The chunked scan reads it in ~0.7s and never
    materializes the parsed document — only the digests it returns. Chunks overlap by
    :data:`_OVERLAP` bytes so a match spanning a boundary is not missed; the result is a
    set, so seeing a digest twice in the overlap is harmless.

    The path is a parameter rather than a read of :data:`SNAPSHOT` so the cache is keyed
    by what the result depends on: repointing the module global cannot serve a previous
    path's digests, which would read as "fixture missing" and skip the test silently.
    Only the real corpus is a large entry; a test's temporary snapshot costs nothing.

    An absent snapshot yields an empty set, which :func:`require_corpus_file` reads as
    "cannot check" rather than "the corpus contains nothing" — a checkout without the
    downloaded corpus must not report every fixture as drifted.
    """
    if not snapshot.is_file():
        return frozenset()

    found: set[bytes] = set()
    with snapshot.open("rb") as handle:
        tail = b""
        while chunk := handle.read(_CHUNK):
            buffer = tail + chunk
            found.update(_MD5_FIELD.findall(buffer))
            tail = buffer[-_OVERLAP:]
    return frozenset(found)


def require_corpus_file(md5sum: str, file_type: str) -> None:
    """Skip the calling test unless ``md5sum`` is a file this checkout can classify offline.

    Two distinct causes, each named in its own skip reason:

    * The digest is not in the corpus snapshot — the catalog moved and the fixture
      points at a file AnVIL no longer serves. Re-pin it.
    * The digest has no usable cached evidence under
      ``data/evidence/anvil/<file_type>/`` — classifying it would fetch from S3.

    The second check loads the record rather than stat-ing its path, because those are
    not the same question. ``CachedEvidence.load`` returns ``None`` — sending the fetcher
    to the network — for a file that is present but truncated, not valid JSON, or missing
    this type's keys, and ``save`` is not atomic, so an interrupted ``make classify``
    leaves exactly such a file behind.

    When the snapshot is absent only the second check applies, so a checkout without the
    downloaded corpus still runs whatever its cache can answer rather than reporting
    every fixture as drifted.
    """
    known = snapshot_md5s(SNAPSHOT)
    if known and md5sum.encode() not in known:
        pytest.skip(
            f"fixture md5 {md5sum} is absent from the corpus snapshot {SNAPSHOT} — "
            "the catalog moved under it; re-pin the fixture (issue #381)"
        )

    evidence_dir = EVIDENCE_BASE / file_type
    if EVIDENCE_CLASSES[file_type].load(evidence_dir, md5sum) is None:
        pytest.skip(
            f"fixture md5 {md5sum} has no usable cached evidence at "
            f"{get_evidence_path(evidence_dir, md5sum)} — classifying it would require "
            "a live S3 fetch (issue #381)"
        )
