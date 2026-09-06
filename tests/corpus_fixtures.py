"""Corpus-drift guard for the ``@pytest.mark.e2e`` eval fixtures (issue #381).

The eval tests in ``test_evals.py`` pin a file by ``md5sum`` and classify it through
the real script functions, which read the evidence cache the pipeline wrote. Both
ends of that drift: a catalog migration replaces the corpus, so a pinned md5 stops
being a file AnVIL has, and its cached evidence is never rewritten. Before this
module such a fixture fell through to a live S3 range request that 404'd, and the
suite reported a puzzling fetch failure instead of naming the cause.

:func:`require_corpus_file` turns both cases into a skip whose reason says which one
it is. It also keeps the eval tests off the network altogether: a fixture with no
cached evidence is one whose classify call would fetch, so it skips rather than try.
Every fetching call in ``test_evals.py`` goes through a wrapper that calls this first.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest

# The corpus snapshot `make classify` runs against, and the evidence cache it writes.
# Both are CWD-relative, mirroring the code's own defaults (Makefile, pipeline.py), so
# the guard looks exactly where a real run would.
SNAPSHOT = Path("data/anvil/anvil_files_metadata.json")
EVIDENCE_BASE = Path("data/evidence/anvil")

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


@lru_cache(maxsize=1)
def snapshot_md5s() -> frozenset[bytes]:
    """Every ``file_md5sum`` in the corpus snapshot, or an empty set if it is absent.

    Scanned with a regex over fixed-size chunks rather than ``json.load``: the snapshot
    is ~376 MB and holds ~708K records, which would parse into hundreds of MB of dicts
    to answer a membership test. The chunked scan reads it in ~0.7s and never
    materializes the parsed document — only the digests it returns. Chunks overlap by
    :data:`_OVERLAP` bytes so a match spanning a boundary is not missed; the result is a
    set, so seeing a digest twice in the overlap is harmless.

    An absent snapshot yields an empty set, which :func:`require_corpus_file` reads as
    "cannot check" rather than "the corpus contains nothing" — a checkout without the
    downloaded corpus must not report every fixture as drifted.
    """
    if not SNAPSHOT.is_file():
        return frozenset()

    found: set[bytes] = set()
    with SNAPSHOT.open("rb") as handle:
        tail = b""
        while chunk := handle.read(_CHUNK):
            buffer = tail + chunk
            found.update(match.group(1) for match in _MD5_FIELD.finditer(buffer))
            tail = buffer[-_OVERLAP:]
    return frozenset(found)


def require_corpus_file(md5sum: str, file_type: str) -> None:
    """Skip the calling test unless ``md5sum`` is a file this checkout can classify offline.

    Two distinct causes, each named in its own skip reason:

    * The digest is not in the corpus snapshot — the catalog moved and the fixture
      points at a file AnVIL no longer serves. Re-pin it.
    * The digest has no cached evidence under ``data/evidence/anvil/<file_type>/`` —
      classifying it would fetch from S3.

    When the snapshot is absent only the second check applies, so a checkout without the
    downloaded corpus still runs whatever its cache can answer rather than reporting
    every fixture as drifted.
    """
    known = snapshot_md5s()
    if known and md5sum.encode() not in known:
        pytest.skip(
            f"fixture md5 {md5sum} is absent from the corpus snapshot {SNAPSHOT} — "
            "the catalog moved under it; re-pin the fixture (issue #381)"
        )

    evidence = EVIDENCE_BASE / file_type / md5sum[:2] / f"{md5sum}.json"
    if not evidence.is_file():
        pytest.skip(
            f"fixture md5 {md5sum} has no cached evidence at {evidence} — "
            "classifying it would require a live S3 fetch (issue #381)"
        )
