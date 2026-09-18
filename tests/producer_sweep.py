"""The producers themselves — how to run each standalone one.

Every producer builds `OutputRecord` now (#450), so a field reaching some of the eleven
outputs and not others is no longer a thing to sweep for: `test_output_shape` pins the
record's key set across all of them. What still needs running a producer is what
structure cannot settle — whose identity a record carries where a producer has two in
hand, and the values it wrote.

It lives apart from `metadata_fixtures` deliberately: importing the producers means
putting `scripts/` on the path, and only the modules here and the tests over them
need that.
"""

import functools
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))

from classify_auxiliary_genomic import classify_auxiliary_genomic
from classify_images import classify_images
from classify_index_files import propagate_to_index_files
from classify_remaining_files import classify_remaining

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


def write_snapshot(tmp_path, records):
    """The input envelope with a catalog, so the repository is named as in a real run."""
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps({"metadata": {"repository": "anvil", "catalog": "anvil15"}, "files": records}))
    return path


def run_producer(producer, tmp_path, records):
    """Run one of :data:`STANDALONE_PRODUCERS` over ``records``; return the rows it wrote."""
    output = tmp_path / "out_classifications.json"
    producer(write_snapshot(tmp_path, records), output)
    return json.loads(output.read_text())["classifications"]


def run_index_producer(tmp_path, records):
    """Run the index producer over ``records``; return its whole output envelope.

    The parent classifications file is empty, so a matched index inherits nothing. Both
    sweeps are about what this producer echoes off the index file's *own* record, not
    what it inherits from a parent, so there is nothing to put in it.

    The envelope rather than the rows, because this producer writes a second key —
    ``unmatched_files`` — that a sweep may want to read.
    """
    parents = tmp_path / "bam_classifications.json"
    parents.write_text(json.dumps({"classifications": []}))
    output = tmp_path / "index_classifications.json"
    propagate_to_index_files(write_snapshot(tmp_path, records), [parents], output)
    return json.loads(output.read_text())
