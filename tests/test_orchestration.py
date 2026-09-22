"""Guards that a registered producer actually reaches production.

Registering a producer must be enough to get it run and its output read. It was three
separate lists, and in #151 `gfa` was added to one and neither of the others, so the
classifier never ran and graph files fell through to the filename-only catch-all — with
every unit test passing, because they call the classifier directly.

The other two are derived from `producers.PRODUCERS` now, so what these tests pin is that
they stay derived: each is checked against what a run would actually invoke and read, and
the Makefile — still hand-written — against the registry.
"""

import json
from pathlib import Path

import pytest

from meta_disco.classify_run import (
    _report_exclusions,
    build_parallel_jobs,
    run_all_classifications,
)
from meta_disco.deployments import PROD
from meta_disco.exclusions import EXCLUDED_FILE, ExcludedFile, write_excluded
from meta_disco.file_types import FILE_TYPE_REGISTRY
from meta_disco.output_utils import CLASSIFICATION_FILES
from meta_disco.producers import PRODUCERS, Producer, producers_in_phase
from meta_disco.source_evidence import EvidenceTarget, write_evidence_file
from tests.test_source_evidence import evidence_file_envelope, published_envelope

METADATA = PROD.input_file
OUTPUT_DIR = Path("output/anvil/20260101_000000")
EVIDENCE_BASE = Path("data/evidence/anvil")


def _jobs():
    return build_parallel_jobs(METADATA, OUTPUT_DIR, EVIDENCE_BASE)


def test_every_registered_file_type_has_a_phase1_job():
    """Otherwise `make classify` never invokes that type's classifier."""
    typed = {extra[extra.index("--type") + 1] for _, _, extra in _jobs() if "--type" in extra}
    missing = set(FILE_TYPE_REGISTRY) - typed
    assert not missing, (
        f"FILE_TYPE_REGISTRY types with no Phase 1 job: {sorted(missing)}. "
        "They would be classified by the filename-only Phase 3 catch-all."
    )


def test_every_phase1_producer_has_a_job_including_the_ones_that_read_no_headers():
    """The producers that read no headers used to be a second hand-written list, with the
    same drift risk as the registry itself."""
    scripts = {script for script, _, _ in _jobs()}
    missing = [producer.name for producer in producers_in_phase(1) if producer.script not in scripts]
    assert not missing, f"Phase 1 producers with no job: {missing}. `make classify` would never invoke them."


def test_every_producer_runs_in_a_phase_a_run_actually_has():
    """A producer in no phase is declared and never invoked; the run has exactly three."""
    assert {producer.phase for producer in PRODUCERS.values()} <= {1, 2, 3}
    for phase in (1, 2, 3):
        assert producers_in_phase(phase), f"no producer runs in phase {phase}"


def test_the_later_phases_are_invoked_from_the_registry_too():
    """Phase 2 and 3 are one producer each, run in sequence rather than in the pool, so
    they are not in `build_parallel_jobs` — and must still be named from the registry
    rather than spelled in the orchestrator."""
    run_source = (Path(__file__).parent.parent / "src" / "meta_disco" / "classify_run.py").read_text()
    for name in ("index", "remaining"):
        assert f'PRODUCERS["{name}"]' in run_source, (
            f"run_all_classifications does not take the {name} producer from the registry, "
            "so its script or output filename can drift from what the reports read."
        )


def test_header_jobs_receive_the_evidence_base():
    """The per-source evidence cache root (#276) must reach the header jobs — the only
    ones that fetch and cache — so HPRC evidence lands under data/evidence/hprc, not anvil."""
    header_jobs = [extra for _, _, extra in _jobs() if "--type" in extra]
    assert header_jobs, "expected at least one header job"
    for extra in header_jobs:
        assert "--evidence-base" in extra
        assert extra[extra.index("--evidence-base") + 1] == str(EVIDENCE_BASE)


def test_workers_thread_to_header_jobs_only():
    """--workers (#276) reaches the fetching header jobs as `-w`; the non-header scripts,
    which don't fetch, never get it. Omitting workers adds no `-w` anywhere."""
    jobs = build_parallel_jobs(METADATA, OUTPUT_DIR, EVIDENCE_BASE, workers=30)
    header = [extra for _, _, extra in jobs if "--type" in extra]
    non_header = [extra for _, _, extra in jobs if "--type" not in extra]
    assert header, "expected at least one header job"
    for extra in header:
        assert extra[extra.index("-w") + 1] == "30"
    assert all("-w" not in extra for extra in non_header)
    # workers omitted -> no -w on any job
    assert all("-w" not in extra for _, _, extra in build_parallel_jobs(METADATA, OUTPUT_DIR, EVIDENCE_BASE))


def test_every_phase1_output_is_read_by_the_reports():
    """Otherwise the type's records are silently excluded from both reports."""
    outputs = {path.name for _, path, _ in _jobs()}
    missing = outputs - set(CLASSIFICATION_FILES)
    assert not missing, (
        f"Phase 1 outputs absent from CLASSIFICATION_FILES: {sorted(missing)}. "
        "generate_coverage_report.py and generate_validation_report.py iterate "
        "CLASSIFICATION_FILES, so these records would not appear in any report."
    )


def test_every_producer_writes_a_file_the_reports_read():
    """CLASSIFICATION_FILES stays derived rather than re-hardcoded — which is what it
    was before #449, and how a producer's output came to be missing from it (#151)."""
    assert [producer.output for producer in PRODUCERS.values()] == CLASSIFICATION_FILES


def test_no_two_producers_write_the_same_file():
    """One producer, one output file: two sharing a name would have the second overwrite
    the first, losing a whole population with no error."""
    assert len(set(CLASSIFICATION_FILES)) == len(CLASSIFICATION_FILES)


def _makefile_recipe(makefile: str, target: str) -> str | None:
    """Return the recipe body (tab-indented lines) of a Makefile target, or None.

    Scoped to the single stanza so an assertion about one target's recipe can't be
    satisfied by text belonging to a different target.
    """
    lines = makefile.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{target}:"):
            recipe = []
            for follow in lines[i + 1 :]:
                if follow.startswith("\t"):
                    recipe.append(follow)
                elif follow.strip() == "":
                    continue
                else:
                    break
            return "\n".join(recipe)
    return None


def test_every_registered_file_type_has_a_makefile_target():
    """`make classify-<type>` is the other entry point, and it is hand-written.

    Checked against the Makefile text rather than against the same f-string
    build_parallel_jobs uses — comparing a value to itself proves nothing.
    """
    makefile = (Path(__file__).parent.parent / "Makefile").read_text()
    for ftype in FILE_TYPE_REGISTRY:
        assert f"\nclassify-{ftype}:" in makefile, (
            f"No `classify-{ftype}` target in the Makefile for registered type {ftype!r}."
        )
        recipe = _makefile_recipe(makefile, f"classify-{ftype}")
        assert recipe and f"--type {ftype}" in recipe, (
            f"The classify-{ftype} target's recipe does not run classify_headers with "
            f"--type {ftype}; classify_headers.py derives the "
            f"{ftype}_classifications.json name CLASSIFICATION_FILES expects from it."
        )
        assert f"classify-{ftype} " in makefile or f"classify-{ftype}\n" in makefile, (
            f"classify-{ftype} is defined but not listed as a `classify-headers` prerequisite or in .PHONY."
        )


class TestExclusionsAreReported:
    """The orchestrator surfaces what the producers recorded (#376).

    It no longer computes the exclusions itself — each producer writes the file as it
    loads — so what is pinned here is that the orchestrator reads that file rather than
    reporting a number of its own, and that it distinguishes "nothing excluded" from
    "no producer got far enough to record anything".
    """

    def test_reports_the_recorded_count(self, tmp_path, capsys):
        write_excluded(tmp_path, [ExcludedFile.from_record({"file_name": "no-md5.bam"})], total_input=4)
        assert _report_exclusions(tmp_path) == 1
        assert "Excluded 1 of 4 records" in capsys.readouterr().out

    def test_reports_a_recorded_zero(self, tmp_path, capsys):
        write_excluded(tmp_path, [], total_input=9)
        assert _report_exclusions(tmp_path) == 0
        assert "No records excluded (9 checked)." in capsys.readouterr().out

    def test_a_missing_file_reports_an_unknown_count_not_zero(self, tmp_path, capsys):
        """No file leaves the count unknown — a different fact from "this run excluded
        nothing". The message names the path and does not assert why it is absent, since
        the directory cannot establish that."""
        assert _report_exclusions(tmp_path) is None
        out = capsys.readouterr().out
        assert "Excluded count unknown" in out
        assert EXCLUDED_FILE in out

    def test_an_unreadable_file_returns_none_not_a_recovered_subset(self, tmp_path, capsys):
        """The rows that survived are not the run's excluded count, so the return value
        must not offer them as one."""
        (tmp_path / EXCLUDED_FILE).write_text('{"excluded": ["nope", {"file_name": "half.bam"}]}')
        assert _report_exclusions(tmp_path) is None
        assert "could not be read" in capsys.readouterr().out


def test_exclusions_file_is_not_read_as_a_classification():
    """Otherwise the coverage, validation, consistency and corpus-diff readers would
    treat an excluded file as a classified one (#376, AC2)."""
    assert EXCLUDED_FILE not in CLASSIFICATION_FILES
    assert EXCLUDED_FILE not in {path.name for _, path, _ in _jobs()}


class TestTheRunReportsItsEvidenceFiles:
    """A run reads its evidence files and is stopped by none of them (#401) — but one:
    evidence contradicting the repository's declared published source (#497), pinned below.

    What the report *says* is pinned in ``test_source_evidence.py``; what is pinned here
    is the wiring — that ``run_all_classifications`` takes an evidence root, reports it,
    and starts regardless of what it found. Whether an evidence file has outlived its
    catalog is not answerable at a run: it belongs to the importer's re-fetch
    decision and to the catalog the run's output is offered back to.
    """

    def _evidence_file(self, tmp_path, target_version):
        """An evidence file whose target names ``target_version`` as the generation it was
        built against — the envelope factory the evidence-file tests use, so the two
        cannot drift as the shape moves."""
        write_evidence_file(
            tmp_path / "source_evidence" / "anvil" / "manifest.ndjson",
            evidence_file_envelope(
                target=EvidenceTarget(system="anvil", dataset="AnVIL_HPRC_R2", version=target_version)
            ),
            [],
        )
        return tmp_path / "source_evidence"

    def test_an_evidence_file_from_another_catalog_is_reported_not_refused(self, tmp_path, capsys):
        """A run classifying anvil15 still runs beside an anvil14 evidence file.

        Nothing on disk establishes which of the two is current — AnVIL deletes the
        superseded catalog rather than keeping it to be compared against — so the run
        records what it saw and leaves the judgement to the two places that can act
        on it.
        """
        metadata = tmp_path / "anvil_files_metadata.json"
        metadata.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": []}))
        output_base = tmp_path / "output"

        run_all_classifications(
            metadata, output_base, tmp_path / "evidence", source_evidence_root=self._evidence_file(tmp_path, "anvil14")
        )
        assert output_base.exists(), "the run must start regardless of an evidence file's catalog"
        assert "anvil/manifest.ndjson" in capsys.readouterr().out.replace("\\", "/")

    def test_a_published_file_from_an_undeclared_table_stops_the_run_before_it_writes_anything(self, tmp_path):
        """The wiring for `require_one_published_source` (its cases are in
        test_source_evidence.py): a file claiming `published_value` from a table that is
        not AnVIL's declared one refuses the run at preflight, so no run directory exists."""
        write_evidence_file(
            tmp_path / "source_evidence" / "anvil" / "file.ndjson",
            published_envelope(dataset="AnVIL_ENCORE_293T", table="file"),
            [],
        )
        metadata, output_base = _empty_run_input(tmp_path)
        with pytest.raises(ValueError, match="exactly one published source"):
            run_all_classifications(
                metadata, output_base, tmp_path / "evidence", source_evidence_root=tmp_path / "source_evidence"
            )
        assert not output_base.exists()


def _empty_run_input(tmp_path):
    """The metadata file a run needs to start, over an empty corpus."""
    metadata = tmp_path / "anvil_files_metadata.json"
    metadata.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": []}))
    return metadata, tmp_path / "output"


class TestTheRunIsFailedByTheUniquenessCheck:
    """A run that wrote a file twice must not report success (#445).

    `_check_one_row_per_file` is tested on its own in test_row_uniqueness.py; what is
    pinned here is that `run_all_classifications` folds its answer into the value it
    returns, which is what makes `make classify` exit non-zero and stop the reports.
    """

    def test_a_duplicated_run_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr("meta_disco.classify_run._check_one_row_per_file", lambda _output_dir, _key: False)
        metadata, output_base = _empty_run_input(tmp_path)

        assert run_all_classifications(metadata, output_base, tmp_path / "evidence") is False

    def test_the_same_run_succeeds_when_every_file_has_one_row(self, tmp_path):
        """The other half: without the check failing, this same input returns True — so
        the assertion above is about the check's answer and not about the run itself."""
        metadata, output_base = _empty_run_input(tmp_path)

        assert run_all_classifications(metadata, output_base, tmp_path / "evidence") is True


class TestTheRegistryIsCheckedBeforeTheRunStarts:
    """The overlap check is a preflight, not a post-mortem.

    #445's own bug was detectable only from the finished output, so it cost a multi-hour
    run before saying anything. The same fact is available before a single file is
    fetched.
    """

    def _run(self, tmp_path):
        metadata, output_base = _empty_run_input(tmp_path)
        return run_all_classifications(metadata, output_base, tmp_path / "evidence")

    def test_an_overlapping_registry_stops_the_run_before_it_writes_anything(self, tmp_path, monkeypatch):
        """Nothing of the run exists afterwards — no output folder, so no half-run for an
        operator to mistake for one that classified something."""
        monkeypatch.setitem(
            PRODUCERS,
            "archives",
            Producer(name="archives", script="x.py", output="x.json", phase=1, extensions=(".tar.gz",)),
        )
        with pytest.raises(ValueError, match="overlapping extensions"):
            self._run(tmp_path)
        assert not (tmp_path / "output").exists()

    def test_the_same_run_starts_with_the_real_registry(self, tmp_path):
        """The other half: without the overlap, this input runs — so the assertion above
        is about the check and not about the run."""
        assert self._run(tmp_path) is True


def test_no_producer_spells_its_output_filename_outside_the_registry():
    """A standalone `python scripts/classify_x.py` and a `make classify` run must name one
    producer's output the same file.

    The standalone scripts' `--output` defaults used to hardcode their own filenames, so
    the two could drift apart while every test passed — the reports read the registry's
    name, and the standalone run wrote the other one.
    """
    outputs = {producer.output for producer in PRODUCERS.values()}
    offenders = []
    for script in sorted({producer.script for producer in PRODUCERS.values()}):
        source = (Path(__file__).parent.parent / "scripts" / script).read_text()
        offenders += [f"{script}: {name}" for name in outputs if f'"{name}"' in source or f"'{name}'" in source]
    assert not offenders, (
        f"Output filenames spelled as literals instead of read off the registry: {offenders}. "
        "Take them from PRODUCERS so a standalone run and `make classify` agree."
    )
