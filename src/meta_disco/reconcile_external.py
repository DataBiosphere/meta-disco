"""Reconcile's external lists: sample maps held outside AnVIL for a dataset, read through as its own are (#710).

**A workaround** until AnVIL holds the maps (#624; ``external_files`` says how it ends). A
lineage line may name, as a workspace tar's parent, a sample map declared in
``sources/external_files.yaml`` (``external_lineage`` writes such lines). That map is no file
of the run, so reconcile holds it itself. For each map a line names that is declared for the
line's dataset (``ExternalFiles.by_ref``), the cached copy's rows are parsed as a catalog map's
are (``external_files.read_sample_map``; a missing or changed copy refuses the run), and give:

- **a carrier** (:func:`carriers`), so the tar's line resolves to it, as an input whose
  ``parent_ref`` is the map's address;
- **its own step** (:func:`hold`), a ``CohortDefinitionActivity`` with each row's gVCF a
  ``member``: the one file of the dataset carrying the row's path's base name, exactly. Where any
  row's name is carried by no file or by several, or two rows name one file, there is no step: a cohort missing a member is
  not the cohort, and a tar reading through the map passes nothing (``list_unresolved``);
- **its samples**, the rows' first column read through the identifier rules, all or none
  (``sample_identity.EXTERNAL_SAMPLE_MAP_SAMPLES``).

Reconcile holds each in its graph under the map's address, so a tar reads its values and
samples through it, and writes each once to ``reconciled/external_lists.ndjson.gz``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import activities, code_rules, edges
from .edges import PARENT_REF
from .external_files import ExternalFile, ExternalFiles, read_sample_map
from .models import NOT_CLASSIFIED
from .reconcile_lineage import Carrier, Locator
from .record_keys import RecordKey
from .sample_identity import EXTERNAL_SAMPLE_MAP_SAMPLES, HeaderSamples

# The run record field a member is looked up by: the row's path's base name.
MEMBER_FIELD = "file_name"
LIST_DATA_TYPE = "sample_map"


@dataclass(frozen=True)
class ExternalList:
    """One declared map a lineage line names: the file, each row's path's base name in row order, and what its rows name as samples."""

    file: ExternalFile
    names: tuple[str, ...]
    samples: HeaderSamples


def read_lists(named: Iterable[tuple[str, str]], declared: ExternalFiles, root: Path) -> list[ExternalList]:
    """Each map of ``named`` (``(dataset, address)`` pairs) that ``declared`` declares for that dataset, read from the cache under ``root``.

    An address not declared for its dataset is left out; its lines are counted
    ``external_undeclared`` (``reconcile_lineage``). ``ExternalFileError`` where a declared map
    is not cached, has changed, or is no sample map.
    """
    found = []
    for dataset, ref in sorted(set(named)):
        file = declared.by_ref(dataset, ref)
        if file is None:
            continue
        rows = read_sample_map(file, root)
        names = tuple(PurePosixPath(path).name for _, path in rows)
        found.append(ExternalList(file, names, EXTERNAL_SAMPLE_MAP_SAMPLES.read(rows, dataset)))
    return found


def member_locators(lists: Iterable[ExternalList]) -> set[Locator]:
    """What the join's scan looks up for the lists' members: each row's name, among the list's dataset's records."""
    return {(MEMBER_FIELD, x.file.dataset, name) for x in lists for name in x.names}


def carriers(lists: Iterable[ExternalList]) -> dict[Locator, list[Carrier]]:
    """Each list as the one carrier of its address in its dataset, so a lineage line naming it resolves."""
    return {(PARENT_REF, x.file.dataset, x.file.ref): [Carrier(x.file.ref, x.file.name, LIST_DATA_TYPE)] for x in lists}


@dataclass(frozen=True)
class Held:
    """A list as reconcile holds it: its record-shaped stand-in for the graph, its step, its samples, and how its rows resolved."""

    list: ExternalList
    record: dict
    step: dict | None
    unresolved: int
    several: int

    def row(self, written: set[str]) -> dict:
        """The list's ``ExternalList`` line; its samples only where their list is among ``written``, the run's sample lists."""
        file = self.list.file
        row: dict = {"ref": file.ref, "dataset": file.dataset, "file_name": file.name, "sha256": file.sha256}
        if self.step is not None:
            row["generated_by"] = self.step
        reference = self.list.samples.reference()
        if reference is not None and reference["list_id"] in written:
            row["samples"] = reference
        return row


def hold(lists: Iterable[ExternalList], found: dict[Locator, list[Carrier]], key: RecordKey) -> list[Held]:
    """Each list's step from its rows' carriers in ``found`` (the join's), and its stand-in record.

    The stand-in names the list's file and dataset, every carried slot ``not_classified`` (a
    list passes nothing itself, ``CohortDefinitionActivity``), and its samples where its rows
    name them all.
    """
    held = []
    for x in lists:
        members, unresolved, several = [], 0, 0
        for name in x.names:
            matched = found.get((MEMBER_FIELD, x.file.dataset, name), [])
            if len(matched) == 1:
                members.append({"file_name": matched[0].file_name, key.input_field: matched[0].key})
            elif matched:
                several += 1
            else:
                unresolved += 1
        # Two rows naming one file would list it twice: as ambiguous as two files carrying one name.
        several += len(x.names) - len(set(x.names))
        step = None
        if not unresolved and not several:
            step = edges.generated_by(code_rules.COHORT_BY_EXTERNAL_SAMPLE_MAP, members, key)
        held.append(Held(x, stand_in(x.file.name, x.file.dataset, x.samples.reference()), step, unresolved, several))
    return held


def stand_in(file_name: str, dataset: str, samples: dict | None = None) -> dict:
    """A list's stand-in record for reconcile's graph (external, or rebuilt, #726): passing nothing, with its ``samples``."""
    record: dict = {
        "file_name": file_name,
        "dataset_title": dataset,
        "classifications": {s: {"status": NOT_CLASSIFIED, "value": None} for s in activities.carried()},
    }
    if samples is not None:
        record["samples"] = samples
    return record


def report(held: Iterable[Held]) -> dict:
    """The report's ``external_lists`` block: per dataset, the lists read, those with a step, and their rows that did not resolve."""
    block: dict[str, Counter] = defaultdict(Counter)
    for h in held:
        counts = block[h.list.file.dataset]
        counts["lists"] += 1
        counts["stepped"] += h.step is not None
        counts["rows"] += len(h.list.names)
        counts["rows_not_in_dataset"] += h.unresolved
        counts["rows_several_match"] += h.several
        counts["samples_named"] += h.list.samples.sample_list is not None
    return {dataset: dict(sorted(counts.items())) for dataset, counts in sorted(block.items())}
