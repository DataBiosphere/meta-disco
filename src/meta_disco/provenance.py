"""What a producer classified and what classified it, written in its output's ``metadata`` (#404).

Per file, not per run: ``make classify-bam RUN_DIR=…`` rewrites one file of a stored run at
whatever commit is checked out then. A fact that cannot be determined is ``null`` under its
key, never left out or guessed: HPRC's input names no catalog; a copy may have no git.
"""

import subprocess
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .inputs import load_envelope

DISTRIBUTION = "meta-disco"
# The checkout the running code was imported from, not the shell's working directory.
_PACKAGE_DIR = Path(__file__).resolve().parent


def _git(directory: Path, *args: str) -> str | None:
    """``git -C directory <args>``'s stdout, stripped, taking no index lock (producers start together); None on failure."""
    try:
        done = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(directory), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def code_identity(directory: Path = _PACKAGE_DIR) -> dict:
    """The installed meta-disco ``version`` and the ``commit`` and ``dirty`` flag of the checkout holding ``directory``.

    ``dirty`` counts changes to tracked files, staged or not, and not untracked files, so a
    scratch file in a clone does not mark its runs dirty. ``commit`` and ``dirty`` are
    None when ``directory`` is in no git checkout or git cannot be run; ``version`` is
    None when the distribution is not installed. Assumes the package is installed from its
    checkout (``uv sync``'s editable install): a copy inside another checkout reads that one's.
    """
    commit = _git(directory, "rev-parse", "HEAD")
    status = _git(directory, "status", "--porcelain", "--untracked-files=no") if commit else None
    try:
        installed = version(DISTRIBUTION)
    except PackageNotFoundError:
        installed = None
    return {"version": installed, "commit": commit, "dirty": None if status is None else bool(status)}


def input_identity(input_path: Path) -> dict:
    """The input file's path as given, and its envelope's ``repository``, ``catalog`` and ``downloaded_at`` (None where absent)."""
    envelope = load_envelope(input_path)
    return {
        "path": str(input_path),
        "repository": envelope.get("repository"),
        "catalog": envelope.get("catalog"),
        "downloaded_at": envelope.get("downloaded_at"),
    }


def run_provenance(input_path: Path) -> dict:
    """A producer's ``metadata.provenance``, taken as it starts: its ``input``, ``started_at`` (UTC) and ``code``."""
    return {
        "input": input_identity(input_path),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": code_identity(),
    }
