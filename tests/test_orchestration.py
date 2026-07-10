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

from rerun_all_classifications import build_parallel_jobs

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


def test_every_registered_file_type_has_a_makefile_target():
    """`make classify-<type>` is the other entry point, and it is hand-written.

    Checked against the Makefile text rather than against the same f-string
    build_parallel_jobs uses — comparing a value to itself proves nothing.
    """
    makefile = (Path(__file__).parent.parent / "Makefile").read_text()
    for ftype in FILE_TYPE_REGISTRY:
        assert f"\nclassify-{ftype}:" in makefile, (
            f"No `classify-{ftype}` target in the Makefile for registered type "
            f"{ftype!r}."
        )
        assert f"{ftype}_classifications.json" in makefile, (
            f"The classify-{ftype} target does not write "
            f"{ftype}_classifications.json, which CLASSIFICATION_FILES expects."
        )
        assert f"classify-{ftype} " in makefile or f"classify-{ftype}\n" in makefile, (
            f"classify-{ftype} is defined but not listed as a "
            "`classify-headers` prerequisite or in .PHONY."
        )
