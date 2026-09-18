"""Shared utilities for working with classification output directories."""

import json
from collections import defaultdict
from dataclasses import dataclass, field
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


def iter_records_with_source(run_dir: Path):
    """Yield ``(classification file name, record)`` for every record a run wrote.

    Unwraps the ``{"metadata", "classifications"}`` envelope with the same key
    precedence as the coverage/validation report loaders — ``classifications``,
    then a legacy ``results`` key, then nothing — but tolerates more than they do.
    A file a run did not write is skipped, so is one whose record list is not a
    list at all (a null, a number, a bare object), and within a list, any element
    that is not a record dict. An unexpected shape therefore yields nothing from
    that file, where those loaders iterate whatever they find and raise.

    Lives here, beside ``CLASSIFICATION_FILES``, so every reader of a run directory
    (the consistency linter, the corpus diff) shares one definition of the envelope
    rather than each re-deriving it. The file name is yielded for the readers that
    must name which producer wrote a record; :func:`iter_records` drops it.
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
                yield fname, record


def iter_records(run_dir: Path):
    """Yield every classification record (a dict) across a run's classification files."""
    for _fname, record in iter_records_with_source(run_dir):
        yield record


@dataclass
class RowIdentities:
    """What a run's rows say about their own identity.

    ``duplicates`` maps a ``file_id`` carried by more than one row to the classification
    file names that wrote it, in output order and with repeats, so a producer that wrote
    the same file twice on its own is visible as such. ``without_file_id`` counts rows
    carrying no usable ``file_id`` — not checkable for uniqueness, which is a different
    fact from being unique.
    """

    total_rows: int = 0
    without_file_id: int = 0
    duplicates: dict[str, list[str]] = field(default_factory=dict)


def row_identities(run_dir: Path) -> RowIdentities:
    """Report which ``file_id`` values more than one of a run's rows carries."""
    sources: dict[str, list[str]] = defaultdict(list)
    identities = RowIdentities()
    for fname, record in iter_records_with_source(run_dir):
        identities.total_rows += 1
        file_id = record.get("file_id")
        if not isinstance(file_id, str) or not file_id:
            identities.without_file_id += 1
            continue
        sources[file_id].append(fname)
    identities.duplicates = {fid: names for fid, names in sources.items() if len(names) > 1}
    return identities
