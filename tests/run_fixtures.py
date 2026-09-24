"""A run directory and the output rows in it, for the tests that read a run.

`metadata_fixtures` builds *input* records; this builds what a run *writes*: the
`{"metadata", "classifications"}` file a producer publishes (`write_run`) and one row
of it (`output_record`, its `classifications` block on its own). `write_run` is shared
by every test that writes a run directory for a reader — the report tests
`test_corpus_diff` and `test_unprocessable`, the
post-run one-row-per-file gate in `test_row_uniqueness`, and the index producer's parent file in
`producer_sweep.run_index_producer`, `test_index_propagation` and
`test_producer_exclusions`. `output_record` is shared by the tests whose rows are
full output rows: `test_corpus_diff`, `test_unprocessable` and the three index-producer
modules, which join on the row's `file_id`.

What stays local, and why, is said in each place: `test_consistency._rec` writes
whatever `status` a case names beside the value, and a case may replace an entry's
`evidence` with a non-list, because the linter must read malformed rows;
`test_remaining_skip_key` writes identity-only
rows with no `classifications` block at all, because the catch-all's skip set reads
nothing else.
"""

import json
from pathlib import Path

from meta_disco.models import CLASSIFICATION_FIELDS, STATUS_LABELS, build_field_entry

OUTPUT_FILE = "bam_classifications.json"


def write_run(run_dir: Path, records, fname: str = OUTPUT_FILE) -> Path:
    """Write ``records`` as one classification output file under ``run_dir``.

    Creates the directory if it is absent and leaves other files in it alone, so a
    test can call this once per output file of a run. ``records`` is any iterable of
    output rows; it is serialized, never kept. Returns ``run_dir`` for chaining.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / fname).write_text(json.dumps({"metadata": {}, "classifications": list(records)}))
    return run_dir


def classifications(**dims) -> dict:
    """The ``classifications`` block, one entry per dimension, each entry from ``build_field_entry``.

    A dimension not named, or named as ``None``, is ``not_classified``. Otherwise it takes a real value
    or a status label from ``models.STATUS_LABELS`` (``not_classified``,
    ``not_applicable``, ``conflict``), which becomes that status with a null value. A
    keyword that is not a dimension is refused rather than ignored, so a misspelled
    one cannot leave the dimension it meant silently ``not_classified``.
    """
    unknown = set(dims) - set(CLASSIFICATION_FIELDS)
    if unknown:
        raise TypeError(f"not a classification dimension: {sorted(unknown)}")
    block = {}
    for dim in CLASSIFICATION_FIELDS:
        cell = dims.get(dim)
        block[dim] = build_field_entry(None, cell) if cell in STATUS_LABELS else build_field_entry(cell)
    return block


def output_record(file_name: str, md5: str, dataset: str | None = "test", file_id: str | None = None, **dims) -> dict:
    """One output row: the identity the reports read plus a ``classifications`` block.

    ``dataset`` may be None because the HPRC source publishes no ``dataset_title`` and
    the reports keep such a row rather than dropping it. ``file_id`` is written only
    when given: it is what the index producer joins a parent row on (#486), and the
    report tests do not carry one. ``dims`` are as for :func:`classifications`.
    """
    record: dict[str, object] = {"file_name": file_name, "md5sum": md5, "dataset_title": dataset}
    if file_id is not None:
        record["file_id"] = file_id
    record["classifications"] = classifications(**dims)
    return record
