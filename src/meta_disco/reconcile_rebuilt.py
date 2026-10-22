"""Reconcile's rebuilt lists: sample maps inference rebuilt from the workspace tars that read them (#726).

The tar producer writes each list (``cohort_steps.TarSteps``) once under its file's ``rebuilt_lists``;
a tar's step names it by address (``parent_ref``). Reconcile holds each in its graph under the address,
as it holds an external list (``reconcile_external``), and writes it to ``rebuilt_lists.ndjson.gz``.
A rebuilt list names no samples: they are the tars' own ``callset.json``, which each tar names (#724).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable


def report(entries: Iterable[dict]) -> dict:
    """The report's ``rebuilt_lists`` block: per dataset, the lists the run's tar producer rebuilt, and their members."""
    block: dict[str, Counter] = defaultdict(Counter)
    for entry in entries:
        counts = block[entry["dataset"]]
        counts["lists"] += 1
        counts["members"] += len(entry["generated_by"]["inputs"])
    return {dataset: dict(sorted(counts.items())) for dataset, counts in sorted(block.items())}
