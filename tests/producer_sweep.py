"""The producers themselves — how to run each standalone one.

Every producer builds `OutputRecord` now (#450), so a field reaching some of the eleven
outputs and not others is no longer a thing to sweep for: `test_output_shape` pins the
record's key set across all of them. What still needs running a producer is what
structure cannot settle — whose identity a record carries where a producer has two in
hand, and the values it wrote.

It lives apart from `metadata_fixtures`, which builds input records and imports no
producer; this module imports the four standalone producers from `scripts/`, which
pytest puts on the path (`pythonpath` in pyproject).
"""

import functools
import json

import pytest
from classify_auxiliary_genomic import classify_auxiliary_genomic
from classify_images import classify_images
from classify_index_files import propagate_to_index_files
from classify_remaining_files import classify_remaining

from tests.metadata_fixtures import write_metadata
from tests.run_fixtures import OUTPUT_FILE, write_run

# The three producers that take `(metadata_path, output_path)` and write one row per
# input record, with a file name and format each one routes on. The index producer takes
# a third argument and needs a parent to match against, so it has its own runner.
#
# Each param's id is the producer's registry name, so a test can check this list against
# `producers.PRODUCERS` and notice a producer nothing here runs.
STANDALONE_PRODUCERS = [
    pytest.param(classify_images, "slide.svs", ".svs", id="images"),
    pytest.param(classify_auxiliary_genomic, "cohort.pvar", ".pvar", id="auxiliary"),
    pytest.param(
        functools.partial(classify_remaining, classification_paths=[]),
        "mystery.xyz",
        ".xyz",
        id="remaining",
    ),
]


def run_producer_envelope(producer, tmp_path, records):
    """Run one of :data:`STANDALONE_PRODUCERS` over ``records``; return the whole envelope.

    The envelope rather than the rows, for the callers that read the ``metadata`` tally
    beside them or commit the whole thing as a fixture (#465) — matching
    :func:`run_index_producer`, which returns one for its own reason.
    """
    output = tmp_path / "out_classifications.json"
    producer(write_metadata(tmp_path / "metadata.json", records), output)
    return json.loads(output.read_text())


def run_producer(producer, tmp_path, records):
    """Run one of :data:`STANDALONE_PRODUCERS` over ``records``; return the rows it wrote."""
    return run_producer_envelope(producer, tmp_path, records)["classifications"]


def run_index_producer(tmp_path, records, parent_classifications=()):
    """Run the index producer over ``records``; return its whole output envelope.

    ``parent_classifications`` are the parent rows a matched index inherits from, in the
    shape ``load_classifications`` reads. It defaults to none, because most callers are
    about what this producer echoes off the index file's *own* record rather than what it
    inherits — with none, a matched index inherits nothing.

    The envelope rather than the rows, because this producer writes a second key —
    ``unmatched_files`` — that a sweep may want to read.
    """
    parents = write_run(tmp_path, parent_classifications) / OUTPUT_FILE
    output = tmp_path / "index_classifications.json"
    propagate_to_index_files(write_metadata(tmp_path / "metadata.json", records), [parents], output)
    return json.loads(output.read_text())
