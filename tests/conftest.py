# tests/conftest.py

from pathlib import Path

import pytest

# The @pytest.mark.e2e eval tests classify by MD5 through the script functions,
# which read real fetched headers from the evidence cache ClassifyPipeline writes
# under data/evidence/anvil/ (evidence_base default in pipeline.py; gitignored).
# Without that cache a lookup misses and falls through to a live S3 + samtools
# fetch of the real (hundreds-of-GB) files — unavailable in CI. We mirror the
# code's own CWD-relative default so the gate is present exactly when the code
# would find the cache: run these where it exists, skip them where it does not.
_EVIDENCE_CACHE = Path("data/evidence/anvil")


def pytest_collection_modifyitems(items):
    """Skip e2e-marked tests when the local evidence cache is absent (e.g. CI).

    pytest injects only the hook arguments a plugin declares, so we request just
    `items` and omit the unused `session`/`config`.
    """
    if _EVIDENCE_CACHE.is_dir():
        return
    skip_e2e = pytest.mark.skip(
        reason=f"evidence cache {_EVIDENCE_CACHE}/ absent; e2e eval tests are local-only (issue #180)"
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)
