"""Reconcile's rebuilt lists: sample maps no one holds, rebuilt by inference from the tars that read them (#726).

The tar producer writes each list it rebuilt (``cohort_steps.TarSteps``) once, under its file's
``rebuilt_lists`` (``records.REBUILT_LISTS_KEY``): the list's address, its dataset, the map's name as
the tars' headers write it, and its own step, a ``CohortDefinitionActivity`` with each gVCF a
``member``. A tar's step names the list by that address (``parent_ref``). Reconcile holds each list in
its graph under the address, as it holds a list held outside AnVIL (``reconcile_external``), so a tar
reads its values through it (``activities.read_through``), and writes each once to
``reconciled/rebuilt_lists.ndjson.gz``.

A rebuilt list names no samples: its rows' samples are the tars' own ``callset.json``, which each tar
already names as its own (#724), and holding them on the list too would count that one reading twice.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from .reconcile_external import stand_in


def record_of(entry: dict) -> dict:
    """The list's record-shaped stand-in for reconcile's graph (``reconcile_external.stand_in``), naming no samples."""
    return stand_in(entry["file_name"], entry["dataset"])


def report(entries: Iterable[dict]) -> dict:
    """The report's ``rebuilt_lists`` block: per dataset, the lists the run's steps name, and their members."""
    block: dict[str, Counter] = defaultdict(Counter)
    for entry in entries:
        counts = block[entry["dataset"]]
        counts["lists"] += 1
        counts["members"] += len(entry["generated_by"]["inputs"])
    return {dataset: dict(sorted(counts.items())) for dataset, counts in sorted(block.items())}
