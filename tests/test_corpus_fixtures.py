"""Tests for the eval fixtures' corpus-drift guard (#381).

The guard decides whether an e2e eval test runs at all, so a broken one fails silently
in the worst way: every eval skips and the suite still reports green. These pin both
directions — it skips when it should, and it stays out of the way when it should not.

Every test drives the guard against a temporary snapshot and cache rather than the real
corpus, so they run anywhere, CI included.
"""

import json

import pytest

from tests import corpus_fixtures
from tests.corpus_fixtures import require_corpus_file, snapshot_md5s

# Two well-formed digests, "present" and "absent" only with respect to the temporary
# snapshot each test builds — nothing here reads the real corpus. They are the real
# before/after of one re-pinned fixture (HG03516.GRCh38_no_alt.bam, which the catalog
# dropped, and simons_data_sample_207.cram, which replaced it) purely so the two are
# recognizable next to test_evals.py.
PRESENT = "a52a5f60403a9f7796ec8f0d87bd9081"
ABSENT = "000ebc5cfdeb4e799aa047e2c54022af"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """Point the guard at a temporary snapshot containing PRESENT, and an empty cache.

    Returns the evidence-cache root so a test can add a cached record to it. The
    snapshot-scan cache is cleared on the way in and out, since it is keyed on nothing
    but the (now monkeypatched) module-level path.
    """
    snapshot = tmp_path / "anvil_files_metadata.json"
    snapshot.write_text(json.dumps({"files": [{"file_name": "x.cram", "file_md5sum": PRESENT}]}))
    evidence = tmp_path / "evidence"
    monkeypatch.setattr(corpus_fixtures, "SNAPSHOT", snapshot)
    monkeypatch.setattr(corpus_fixtures, "EVIDENCE_BASE", evidence)
    snapshot_md5s.cache_clear()
    yield evidence
    snapshot_md5s.cache_clear()


def _cache(evidence_root, md5sum, file_type="bam"):
    """Write a stand-in cached-evidence file where the guard looks for one."""
    path = evidence_root / file_type / md5sum[:2] / f"{md5sum}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")


def test_absent_md5_skips_naming_the_snapshot(corpus):
    """The drift case: the catalog moved and the fixture points at a file it dropped."""
    with pytest.raises(pytest.skip.Exception) as excinfo:
        require_corpus_file(ABSENT, "bam")
    assert ABSENT in str(excinfo.value)
    assert "absent from the corpus snapshot" in str(excinfo.value)


def test_uncached_md5_skips_naming_the_fetch(corpus):
    """A current md5 with no cached evidence would hit S3 — skip rather than fetch."""
    with pytest.raises(pytest.skip.Exception) as excinfo:
        require_corpus_file(PRESENT, "bam")
    assert "no cached evidence" in str(excinfo.value)


def test_current_and_cached_md5_does_not_skip(corpus):
    """The guard must stay out of the way of a fixture that can actually run."""
    _cache(corpus, PRESENT)
    require_corpus_file(PRESENT, "bam")


def test_cache_is_per_file_type(corpus):
    """Evidence is cached per type; a BAM record does not satisfy a FASTA lookup."""
    _cache(corpus, PRESENT, "bam")
    with pytest.raises(pytest.skip.Exception) as excinfo:
        require_corpus_file(PRESENT, "fasta")
    assert "no cached evidence" in str(excinfo.value)


def test_missing_snapshot_checks_only_the_cache(tmp_path, monkeypatch):
    """Without a downloaded corpus the guard cannot judge drift, so it must not claim any.

    A checkout with an evidence cache but no snapshot still runs whatever the cache can
    answer; only the fetch check applies.
    """
    evidence = tmp_path / "evidence"
    monkeypatch.setattr(corpus_fixtures, "SNAPSHOT", tmp_path / "does-not-exist.json")
    monkeypatch.setattr(corpus_fixtures, "EVIDENCE_BASE", evidence)
    snapshot_md5s.cache_clear()
    try:
        assert snapshot_md5s() == frozenset()
        _cache(evidence, ABSENT)
        require_corpus_file(ABSENT, "bam")  # absent from the (unreadable) snapshot, but cached
    finally:
        snapshot_md5s.cache_clear()


@pytest.mark.parametrize("separator", ["", " ", "  " * 4])
def test_digest_split_across_a_read_boundary_is_found(tmp_path, monkeypatch, separator):
    """The chunked scan must not lose a match that straddles two chunks.

    The field is padded to end 8 bytes past the first boundary, so the leading chunk
    holds it truncated and the trailing chunk holds only its tail: without the overlap
    the regex sees two halves and matches neither (verified — the scan misses this at an
    overlap of 8, finds it at the configured width). Each separator width is tried, since
    a wider field has to survive the same cut.
    """
    field = f'"file_md5sum":{separator}"{PRESENT}"'
    assert len(field) <= corpus_fixtures._OVERLAP, "test field must fit within the overlap"
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(" " * (corpus_fixtures._CHUNK - len(field) + 8) + field)
    monkeypatch.setattr(corpus_fixtures, "SNAPSHOT", snapshot)
    snapshot_md5s.cache_clear()
    try:
        assert PRESENT.encode() in snapshot_md5s()
    finally:
        snapshot_md5s.cache_clear()
