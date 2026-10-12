"""What a producer records about what it classified and what classified it (#404)."""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

from meta_disco import provenance
from meta_disco.provenance import DISTRIBUTION, code_identity, input_identity, run_provenance
from tests.metadata_fixtures import write_metadata

# No inherited GIT_DIR or GIT_WORK_TREE can point a test's git at another repository.
_ENV = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}


def git(repo: Path, *args: str) -> str:
    # Identity and signing set here, so a test does not depend on the machine's git config.
    command = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.org"]
    command += ["-c", "commit.gpgsign=false", *args]
    return subprocess.run(command, capture_output=True, text=True, check=True, env=_ENV).stdout.strip()


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "checkout"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "rules.yaml").write_text("a: 1\n")
    git(repo, "add", "rules.yaml")
    git(repo, "commit", "-q", "-m", "first")
    return repo


def test_a_clean_checkout_records_its_commit_and_is_not_dirty(checkout):
    code = code_identity(checkout)
    assert code["commit"] == git(checkout, "rev-parse", "HEAD")
    assert code["dirty"] is False


def test_a_changed_tracked_file_is_dirty_staged_or_not(checkout):
    (checkout / "rules.yaml").write_text("a: 2\n")
    assert code_identity(checkout)["dirty"] is True
    git(checkout, "add", "rules.yaml")
    assert code_identity(checkout)["dirty"] is True


def test_an_untracked_file_alone_is_not_dirty(checkout):
    (checkout / "scratch.txt").write_text("notes\n")
    assert code_identity(checkout)["dirty"] is False


def test_outside_a_checkout_the_commit_and_dirty_flag_are_unknown(tmp_path, monkeypatch):
    # So a temporary directory inside some checkout still has none above it.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    code = code_identity(tmp_path)
    assert code["commit"] is None and code["dirty"] is None
    assert set(code) == {"version", "commit", "dirty"}


def test_without_git_the_commit_and_dirty_flag_are_unknown(checkout, monkeypatch):
    def no_git(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(provenance.subprocess, "run", no_git)
    code = code_identity(checkout)
    assert code["commit"] is None and code["dirty"] is None


def test_the_version_is_the_installed_distributions_and_unknown_when_it_is_not_installed(checkout, monkeypatch):
    assert code_identity(checkout)["version"] == version(DISTRIBUTION)

    def not_installed(_name):
        raise PackageNotFoundError(DISTRIBUTION)

    monkeypatch.setattr(provenance, "version", not_installed)
    assert code_identity(checkout)["version"] is None


def test_an_input_naming_its_catalog_records_it_and_when_it_was_downloaded(tmp_path):
    path = tmp_path / "anvil_files_metadata.json"
    envelope = {"repository": "anvil", "catalog": "anvil15", "downloaded_at": "2026-09-17T22:27:26"}
    path.write_text(json.dumps({"metadata": envelope, "files": []}))
    assert input_identity(path) == {"path": str(path), **envelope}


def test_an_input_naming_no_catalog_records_that_it_has_none(tmp_path):
    # HPRC's envelope names its repository and nothing else.
    path = write_metadata(tmp_path / "hprc_files_metadata.json", [], repository="hprc")
    assert input_identity(path) == {"path": str(path), "repository": "hprc", "catalog": None, "downloaded_at": None}


def test_a_producers_provenance_is_its_input_its_start_and_its_code(tmp_path):
    path = write_metadata(tmp_path / "input.json", [], catalog="anvil15")
    before = datetime.now(timezone.utc)
    recorded = run_provenance(path)
    assert recorded["input"] == input_identity(path)
    assert recorded["code"] == code_identity()
    started = datetime.fromisoformat(recorded["started_at"])
    assert started.utcoffset() == timedelta(0)
    assert before - timedelta(seconds=1) <= started <= datetime.now(timezone.utc)
