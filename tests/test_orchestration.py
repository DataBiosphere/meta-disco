"""Guards that a registered file type actually reaches production.

Registering a FileTypeConfig makes `classify_headers.py --type X` work, but a
type only runs in a real `make classify` if it also has a Phase 1 job, and its
output only reaches the reports if it is in CLASSIFICATION_FILES. Those are
three separate lists. In #151 `gfa` was added to the registry and to neither of
the others, so the classifier never ran and graph files fell through to the
filename-only Phase 3 catch-all — with every unit test passing, because they
call the classifier directly.

These tests pin the three together.
"""

from pathlib import Path

from meta_disco.classify_run import build_parallel_jobs
from meta_disco.file_types import FILE_TYPE_REGISTRY
from meta_disco.output_utils import CLASSIFICATION_FILES

METADATA = Path("data/anvil/anvil_files_metadata.json")
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
