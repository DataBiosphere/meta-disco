# tests/conftest.py

import re
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

    Two independent gates. Neither runs unless its precondition holds:

    - **e2e** needs the cache directory; it is skipped where that is absent (CI),
      and runs by default where it is present.
    - **network** has no local precondition to test for, so opting in is the
      signal: it runs only when the `-m` expression mentions the marker. A
      default `make test` must not depend on a third-party API being up.

    The `-m` check matches marker *names*, not a substring of the expression, so
    a future marker whose name contains this one (`network_slow`) cannot switch
    the gate off by accident. A `not` anywhere in the expression closes the gate
    too: `-m "not network"` mentions the marker while asking to exclude it, and
    pytest's own deselection is then what keeps those tests out — the gate should
    not be the thing relying on that. The bias is deliberate and one-directional:
    an expression this cannot read as a clear opt-in skips, because the cost of
    skipping is a check not run, and the cost of the opposite is an unasked-for
    call to someone else's API.
    """
    if not _EVIDENCE_CACHE.is_dir():
        skip_e2e = pytest.mark.skip(
            reason=f"evidence cache {_EVIDENCE_CACHE}/ absent; e2e eval tests are local-only (issue #180)"
        )
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)

    selectors = re.findall(r"[A-Za-z_]\w*", config.getoption("-m") or "")
    if "network" not in selectors or "not" in selectors:
        skip_network = pytest.mark.skip(reason="network tests are opt-in; select them with -m network")
        for item in items:
            if "network" in item.keywords:
                item.add_marker(skip_network)
