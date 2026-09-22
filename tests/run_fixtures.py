"""A run directory and the output rows in it, for the reports that read a run.

`metadata_fixtures` builds *input* records; this builds what a run *writes* — the
`{"metadata", "classifications"}` file a producer publishes and one row of it — so the
report tests (`test_corpus_diff`, `test_unprocessable`, `test_published_comparison`)
share one spelling of that shape. `test_anvil_forecast` shares the writer and the
`classifications` block but keys its rows by `drs_uri`, which its report joins on, so
it assembles the row itself.

Two builders stay local on purpose, and say so in their docstrings:
`test_consistency._rec` writes entries with no `evidence` and whatever `status` a case
names, because the linter must read malformed rows; `test_published_comparison._record`
carries two dimensions and a `published` block, because that report reads only those.
"""

import json
from pathlib import Path

from meta_disco.models import CLASSIFICATION_FIELDS, build_field_entry

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
    """The five-dimension ``classifications`` block, each entry from ``build_field_entry``.

    A dimension not named is ``not_classified``. A named one takes a real value, a
    sentinel (which the builder turns into a status with a null value), or a
    ``(value, status)`` pair for a status the builder cannot derive, such as
    ``(None, CONFLICT)``.
    """
    block = {}
    for dim in CLASSIFICATION_FIELDS:
        cell = dims.get(dim)
        value, status = cell if isinstance(cell, tuple) else (cell, None)
        block[dim] = build_field_entry(value, status)
    return block


def output_record(file_name: str, md5: str, dataset: str | None = "test", **dims) -> dict:
    """One output row: the identity the reports read plus a ``classifications`` block.

    ``dataset`` may be None because the HPRC source publishes no ``dataset_title`` and
    the reports keep such a row rather than dropping it. ``dims`` are as for
    :func:`classifications`.
    """
    return {"file_name": file_name, "md5sum": md5, "dataset_title": dataset, "classifications": classifications(**dims)}
