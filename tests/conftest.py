# tests/conftest.py

from pathlib import Path

import pytest

# The @pytest.mark.e2e eval tests classify by MD5 through ClassifyPipeline,
# which reads real fetched headers from the evidence cache ClassifyPipeline writes
# under data/evidence/anvil/ (evidence_base default in pipeline.py; gitignored).
# Without that cache a lookup misses and falls through to a live S3 + samtools
# fetch of the real (hundreds-of-GB) files — unavailable in CI. We mirror the
# code's own CWD-relative default so the gate is present exactly when the code
# would find the cache: run these where it exists, skip them where it does not.
_EVIDENCE_CACHE = Path("data/evidence/anvil")


def pytest_collection_modifyitems(config, items):
    """Skip e2e tests without the evidence cache, and network tests unless selected.

    Two independent gates, both defaulting to "do not run":

    - **e2e** is skipped when the cache directory is absent (e.g. CI), per above.
    - **network** is skipped unless `-m` names it. There is no local precondition
      to test for, so opting in is the signal: a default `make test` run must not
      depend on a third-party API being up.
    """
    if not _EVIDENCE_CACHE.is_dir():
        skip_e2e = pytest.mark.skip(
            reason=f"evidence cache {_EVIDENCE_CACHE}/ absent; e2e eval tests are local-only (issue #180)"
        )
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)

    if "network" not in (config.getoption("-m") or ""):
        skip_network = pytest.mark.skip(reason="network tests are opt-in; select them with -m network")
        for item in items:
            if "network" in item.keywords:
                item.add_marker(skip_network)
