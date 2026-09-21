"""Shared utilities for working with classification output directories."""

import json
from dataclasses import dataclass
from pathlib import Path

from .producers import classification_files

# Every file a Phase 1/2/3 producer writes, derived from the producer registry so it
# cannot drift from what a run actually produces (#449). The coverage and validation
# report generators read exactly this list, so a run's output file missing from it is
# silently excluded from both reports — half of what #151 cost. Registering a producer
# is now the only step: the list follows.
CLASSIFICATION_FILES = classification_files()


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


def _records_in(path: Path):
    """Yield the record dicts inside one classification file, or nothing.

    Unwraps the ``{"metadata", "classifications"}`` envelope with the same key
    precedence as the coverage/validation report loaders — ``classifications``,
    then a legacy ``results`` key, then nothing — but tolerates more than they do.
    A file a run did not write is skipped, so is one whose record list is not a
    list at all (a null, a number, a bare object), and within a list, any element
    that is not a record dict. An unexpected shape therefore yields nothing from
    that file, where those loaders iterate whatever they find and raise.
    """
    if not path.exists():
        return
    data = json.loads(path.read_text())
    records = data.get("classifications", data.get("results", [])) if isinstance(data, dict) else data
    # A scalar or null here is iterable only by accident (a string) or not at
    # all (a number, None) — either way it holds no records, so skip the file
    # rather than raising on a shape this function promises to tolerate.
    if not isinstance(records, list):
        return
    for record in records:
        if isinstance(record, dict):
            yield record


def iter_records(run_dir: Path):
    """Yield every classification record (a dict) across a run's classification files.

    Lives here, beside ``CLASSIFICATION_FILES``, so every reader of a run directory
    (the consistency linter, the corpus diff) shares one definition of the envelope
    rather than each re-deriving it.
    """
    for fname in CLASSIFICATION_FILES:
        yield from _records_in(run_dir / fname)


def iter_records_with_source(run_dir: Path):
    """Yield ``(classification file name, record)``, for a reader that must name the
    producer a record came from."""
    for fname in CLASSIFICATION_FILES:
        for record in _records_in(run_dir / fname):
            yield fname, record


@dataclass(frozen=True)
class RowIdentities:
    """What a run's rows say about their own identity, under the field ``key``.

    ``duplicates`` maps a key value carried by more than one row to the classification
    files that wrote it, in ``CLASSIFICATION_FILES`` order and with repeats, so a producer
    that wrote the same file twice on its own is visible as such. ``without_key`` counts
    rows carrying no usable value under ``key`` — not checkable for uniqueness, which is a
    different fact from being unique.
    """

    total_rows: int
    without_key: int
    duplicates: dict[str, list[str]]


def row_identities(run_dir: Path, key: str) -> RowIdentities:
    """Report which values of ``key`` more than one of a run's rows carries.

    ``key`` is the output-row spelling of the source's record key
    (``pipeline.SOURCE_RECORD_KEYS``). No default: one source's field is not a fallback.
    """
    # Only the first source per key value is kept until a second row claims it: a
    # duplicate is the exception, so the list is paid for only where one occurs.
    first_source: dict[str, str] = {}
    duplicates: dict[str, list[str]] = {}
    total_rows = 0
    without_key = 0
    for fname, record in iter_records_with_source(run_dir):
        total_rows += 1
        value = record.get(key)
        if not isinstance(value, str) or not value:
            without_key += 1
        elif value in duplicates:
            duplicates[value].append(fname)
        elif value in first_source:
            duplicates[value] = [first_source[value], fname]
        else:
            first_source[value] = fname
    return RowIdentities(total_rows, without_key, duplicates)
