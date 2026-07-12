"""Shared utilities for working with classification output directories."""

from pathlib import Path

# Every file a Phase 1/2/3 classifier writes. The coverage and validation report
# generators read exactly this list, so a run's output file that is missing here
# is silently excluded from both reports. Adding a FILE_TYPE_REGISTRY type means
# adding its `{type}_classifications.json` here — pinned by tests/test_orchestration.py.
CLASSIFICATION_FILES = [
    "bam_classifications.json",
    "vcf_classifications.json",
    "fastq_classifications.json",
    "bed_classifications.json",
    "image_classifications.json",
    "auxiliary_classifications.json",
    "index_classifications.json",
    "fasta_classifications.json",
    "gfa_classifications.json",
    "remaining_classifications.json",
]


def find_latest_run(output_dir: Path) -> Path:
    """Find the most recent timestamped run directory.

    Looks for subdirectories whose names start with a digit (e.g., 20260322_112336)
    and returns the one that sorts last (most recent).

    Raises FileNotFoundError if the output directory or run directories don't exist.
    """
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Output directory not found: {output_dir}. Run 'make classify' first.")
    runs = sorted(
        [d for d in output_dir.iterdir() if d.is_dir() and d.name[0].isdigit()],
        key=lambda d: d.name,
        reverse=True,
    )
    if not runs:
        raise FileNotFoundError(f"No run directories found in {output_dir}. Run 'make classify' first.")
    return runs[0]
