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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from rerun_all_classifications import NON_HEADER_JOBS, build_parallel_jobs

from src.meta_disco.file_types import FILE_TYPE_REGISTRY
from src.meta_disco.output_utils import CLASSIFICATION_FILES

METADATA = Path("data/anvil/anvil_files_metadata.json")
OUTPUT_DIR = Path("output/anvil/20260101_000000")


def _jobs():
    return build_parallel_jobs(METADATA, OUTPUT_DIR)


def test_every_registered_file_type_has_a_phase1_job():
    """Otherwise `make classify` never invokes that type's classifier."""
    typed = {
        extra[extra.index("--type") + 1]
        for _, _, extra in _jobs()
        if "--type" in extra
    }
    missing = set(FILE_TYPE_REGISTRY) - typed
    assert not missing, (
        f"FILE_TYPE_REGISTRY types with no Phase 1 job: {sorted(missing)}. "
        "They would be classified by the filename-only Phase 3 catch-all."
    )


def test_every_phase1_output_is_read_by_the_reports():
    """Otherwise the type's records are silently excluded from both reports."""
    outputs = {path.name for _, path, _ in _jobs()}
    missing = outputs - set(CLASSIFICATION_FILES)
    assert not missing, (
        f"Phase 1 outputs absent from CLASSIFICATION_FILES: {sorted(missing)}. "
        "generate_coverage_report.py and generate_validation_report.py iterate "
        "CLASSIFICATION_FILES, so these records would not appear in any report."
    )


def test_non_header_jobs_are_also_read_by_the_reports():
    outputs = {out for _, out in NON_HEADER_JOBS}
    assert outputs <= set(CLASSIFICATION_FILES)


def test_phase1_job_output_names_follow_the_registry_convention():
    """`{type}_classifications.json` — the name the Makefile targets also use."""
    for _, path, extra in _jobs():
        if "--type" not in extra:
            continue
        ftype = extra[extra.index("--type") + 1]
        assert path.name == f"{ftype}_classifications.json"
