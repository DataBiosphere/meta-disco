"""Shared utilities for working with classification output directories."""

import json
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
    "tar_classifications.json",
    "remaining_classifications.json",
]


def find_latest_run(output_dir: Path) -> Path:
    """Find the most recent timestamped run directory.

    Looks for subdirectories whose names start with a digit (e.g., 20260322_112336)
    and returns the one that sorts last (most recent). By convention, full
    `make classify` runs write digit-prefixed dirs while the `partials/` folder
    (standalone/per-type test runs from `make classify-<type>`) starts with a
    letter, so this digit-prefix filter skips it. The filter keys only on the
    leading character, so any other digit-prefixed dir here — e.g. one an operator
    passes via `--run-dir` — would also be considered.

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


def iter_records(run_dir: Path):
    """Yield every classification record (a dict) across a run's classification files.

    Unwraps the ``{"metadata", "classifications"}`` envelope with the same key
    precedence as the coverage/validation report loaders — ``classifications``,
    then a legacy ``results`` key, then nothing — but tolerates more than they do.
    A file a run did not write is skipped, so is one whose record list is not a
    list at all (a null, a number, a bare object), and within a list, any element
    that is not a record dict. An unexpected shape therefore yields nothing from
    that file, where those loaders iterate whatever they find and raise.

    Lives here, beside ``CLASSIFICATION_FILES``, so every reader of a run directory
    (the consistency linter, the corpus diff) shares one definition of the envelope
    rather than each re-deriving it.
    """
    for fname in CLASSIFICATION_FILES:
        path = run_dir / fname
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        records = data.get("classifications", data.get("results", [])) if isinstance(data, dict) else data
        # A scalar or null here is iterable only by accident (a string) or not at
        # all (a number, None) — either way it holds no records, so skip the file
        # rather than raising on a shape this function promises to tolerate.
        if not isinstance(records, list):
            continue
        for record in records:
            if isinstance(record, dict):
                yield record
