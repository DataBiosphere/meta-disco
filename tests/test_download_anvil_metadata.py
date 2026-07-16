"""Regression tests for scripts/download_anvil_metadata.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import download_anvil_metadata as dl


def test_keyboard_interrupt_before_count_preserves_checkpoint(tmp_path, monkeypatch):
    """A KeyboardInterrupt during the initial count fetch must resume cleanly.

    ``start_time`` / ``total_files`` / ``hits`` are read by the ``except`` branch
    and the post-loop summary, but were bound only inside the ``try``. An interrupt
    before the count fetch returned left them unbound, so the summary crashed with
    a NameError instead of saving a checkpoint (issue #189). They are now
    initialized before the ``try``.

    Because the count never succeeded, the run is *not* complete: the resume
    checkpoint must survive and no finalized corpus JSON should be written. (With
    ``total_files`` initialized to 0, an unguarded ``total_fetched >= total_files``
    would read 0 >= 0 as "complete" and delete the checkpoint.)
    """

    def interrupt(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(dl, "fetch_page", interrupt)

    # Must return cleanly (no NameError) even though the count fetch never ran.
    dl.download_all_metadata(tmp_path)

    # Interrupted before the count: not complete. Checkpoint kept, no final JSON.
    assert (tmp_path / "checkpoint.json").exists()
    assert not (tmp_path / "anvil_files_metadata.json").exists()
