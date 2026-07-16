"""Regression tests for scripts/download_anvil_metadata.py."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import download_anvil_metadata as dl


def test_keyboard_interrupt_before_count_completes_summary(tmp_path, monkeypatch):
    """A KeyboardInterrupt during the initial count fetch must not NameError.

    ``start_time`` / ``total_files`` / ``hits`` are read by the ``except`` branch
    and the post-loop summary, but were bound only inside the ``try``. An interrupt
    before the count fetch returned left them unbound, so the summary crashed with
    a NameError instead of saving a checkpoint (issue #189). They are now
    initialized before the ``try``; this exercises that path.
    """

    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(dl, "fetch_page", interrupt)

    # Must return cleanly (no NameError) even though the count fetch never ran.
    dl.download_all_metadata(tmp_path)

    # The summary path ran to completion and finalized an (empty) corpus.
    final = tmp_path / "anvil_files_metadata.json"
    assert final.exists()
    assert json.loads(final.read_text())["metadata"]["total_files"] == 0
