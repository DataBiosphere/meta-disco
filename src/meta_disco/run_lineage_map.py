"""The run lineage map: which datasets take their reads from another dataset (#594).

ADR-0002 decision 2 keeps a file's lineage inside its dataset. This map is its one
declared exception: an entry says a table's alignments hold an archive run's reads,
found by the counts in the same row's ``samtools stats`` file among the listed studies'
runs, and that those reads are files of ``reads_in``, another dataset. The importer
(``ena_lineage``) reads it to write lineage lines naming the parent's dataset;
reconcile reads it to resolve a line's ``parent_dataset`` only where an entry declares
the pair (:meth:`RunLineageMap.declares`). This module holds the declaration and its
structural checks only, so reconcile imports no importer::

    catalog: anvil15
    source: ena                            # the archive whose lines may cross
    datasets:
      ANVIL_T2T_CHRY:                      # the child's dataset
        1KGP_CHM13v2_sample:               # the table naming each alignment
          - child: {column: cram}          # the alignment
            counts: {column: full_samtools_stats}   # its samtools stats file
            ena_studies: [PRJEB31736, PRJEB36890]   # whose runs are the candidates
            reads_in: ANVIL_T2T            # where a run's reads are files

:func:`load_run_lineage_map` refuses a loop among the ``reads_in`` arrows
(:func:`find_loop`); :meth:`RunLineageMap.require_in_run` refuses a run holding an entry's
child dataset but not its ``reads_in`` dataset. Whether the datasets, tables and columns exist
is ``ena_lineage.check``'s, against the deployment and the manifests.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files

from .azul_manifest import REPOSITORY
from .lineage_map import expect_keys, expect_mapping, expect_name, map_document
from .models import JOIN_KEY_FILE_ID, SOURCE_EXTERNAL_GROUND_TRUTH
from .schema.classification_model import EvidenceFileEnvelope, LineageRow
from .slot_map import Readable, unique_key_loader

_WHERE = "run lineage map"
# The one shape a crossing line may have, the run lineage importer's (``ena_lineage``): a file
# of the archive's run records, keyed by AnVIL's file_id, whose parent is a file the run lists.
RUN_TABLE = "read_run"
PARENT_COLUMN = "fastq_ftp"
_ENTRY_KEYS = {"child", "counts", "ena_studies", "reads_in"}
_STUDY = re.compile(r"^PRJ[EDN][A-Z]\d+$")


@dataclass(frozen=True)
class Entry:
    """One declared table: its alignments, their stats files, the studies to look in, and where the reads are."""

    dataset: str
    table: str
    child_column: str
    counts_column: str
    ena_studies: tuple[str, ...]
    reads_in: str


@dataclass(frozen=True)
class RunLineageMap:
    """A loaded map: the AnVIL catalog it was authored against, the source whose lines may cross, and its entries."""

    catalog: str
    source: str
    entries: tuple[Entry, ...]

    def datasets(self) -> list[str]:
        """The child datasets, in file order, each once."""
        return list(dict.fromkeys(e.dataset for e in self.entries))

    def dataset_entries(self, dataset: str) -> list[Entry]:
        return [e for e in self.entries if e.dataset == dataset]

    def declares(self, envelope: EvidenceFileEnvelope, line: LineageRow) -> bool:
        """Whether ``line``, of the file ``envelope`` heads, may name a parent in its ``parent_dataset``.

        Only a line of the run lineage importer's shape: a file of this map's source's run
        records (``external_ground_truth``, table :data:`RUN_TABLE`, keyed by ``file_id``)
        about a file of this map's catalog of AnVIL, whose parent is a ``file_id`` read from
        :data:`PARENT_COLUMN`, where an entry declares the line's dataset and alignment
        column taking their reads from that ``parent_dataset``.
        """
        target = envelope.target
        return (
            line.parent_dataset is not None
            and envelope.source.repository == self.source
            and str(envelope.source_type) == SOURCE_EXTERNAL_GROUND_TRUTH
            and envelope.source.table == RUN_TABLE
            and str(envelope.target_key) == JOIN_KEY_FILE_ID
            and str(line.parent_key_type) == JOIN_KEY_FILE_ID
            and line.parent_column == PARENT_COLUMN
            and (target.system, target.version) == (REPOSITORY, self.catalog)
            and any(
                (e.dataset, e.child_column, e.reads_in) == (target.dataset, line.child_column, line.parent_dataset)
                for e in self.entries
            )
        )

    def require_in_run(self, repository: str, catalog: str | None, datasets: Iterable[str]) -> None:
        """Refuse a run of this map's catalog holding an entry's child dataset but not the dataset its reads are in.

        ``ValueError`` naming both: every line of that entry would find no parent and carry
        nothing, silently. A run of another repository or catalog, or holding none of the
        child datasets, passes.
        """
        if repository != REPOSITORY or catalog not in (None, self.catalog):
            return
        present = set(datasets)
        missing = sorted(
            {(e.dataset, e.reads_in) for e in self.entries if e.dataset in present and e.reads_in not in present}
        )
        if missing:
            named = ", ".join(f"{child} takes its reads from {reads}" for child, reads in missing)
            raise ValueError(f"{_WHERE}: {named}, which the run does not hold")


def default_run_lineage_map_resource():
    """The bundled map, as a package-data resource."""
    return files(f"{__package__}.sources") / "ena_run_lineage_map.yaml"


_UniqueKeyLoader = unique_key_loader(_WHERE)


def load_run_lineage_map(source: Readable | None = None) -> RunLineageMap:
    """Load and check the map, the bundled one by default; ``ValueError`` naming where it is wrong.

    Checked here: the top level (``lineage_map.map_document``) and a ``source`` name, one
    entry per table (the importer writes a lineage file and an inputs file per table), the
    entry shape, study accessions, and no loop among the ``reads_in`` arrows (:func:`find_loop`).
    """
    resource = source if source is not None else default_run_lineage_map_resource()
    document = map_document(resource, _UniqueKeyLoader, _WHERE, {"source"})
    entries = []
    for dataset, tables in document["datasets"].items():
        expect_mapping(tables, f"{_WHERE} {dataset}", "table")
        for table, listed in tables.items():
            at = f"{_WHERE} {dataset}/{table}"
            # The importer writes one lineage file and one inputs file per table, named for it.
            if not isinstance(listed, list) or len(listed) != 1:
                raise ValueError(f"{at}: must be a list of one entry — one table, one lineage file")
            entries.append(_entry(dataset, table, listed[0], f"{at} entry"))
    loop = find_loop((e.dataset, e.reads_in) for e in entries)
    if loop:
        raise ValueError(f"{_WHERE}: reads_in loops {' -> '.join(loop)}; a dataset's reads cannot come from itself")
    return RunLineageMap(
        catalog=document["catalog"], source=expect_name(document["source"], f"{_WHERE} source"), entries=tuple(entries)
    )


def find_loop(arrows: Iterable[tuple[str, str]]) -> list[str] | None:
    """A loop among ``(child dataset, reads dataset)`` arrows, as the datasets around it; None when none.

    A dataset taking its reads from itself is a loop of one arrow.
    """
    following: dict[str, set[str]] = defaultdict(set)
    for child, reads in arrows:
        following[child].add(reads)
    done: set[str] = set()

    def walk(dataset: str, path: list[str]) -> list[str] | None:
        if dataset in path:
            return [*path[path.index(dataset) :], dataset]
        if dataset in done:
            return None
        for reads in sorted(following.get(dataset, ())):
            loop = walk(reads, [*path, dataset])
            if loop:
                return loop
        done.add(dataset)
        return None

    for start in sorted(following):
        loop = walk(start, [])
        if loop:
            return loop
    return None


def _entry(dataset: str, table: str, entry: object, at: str) -> Entry:
    expect_keys(entry, _ENTRY_KEYS, _ENTRY_KEYS, at)
    assert isinstance(entry, dict)
    expect_keys(entry["child"], {"column"}, {"column"}, f"{at} child")
    expect_keys(entry["counts"], {"column"}, {"column"}, f"{at} counts")
    studies = entry["ena_studies"]
    if not isinstance(studies, list) or not studies or not all(isinstance(s, str) and _STUDY.match(s) for s in studies):
        raise ValueError(f"{at} ena_studies: is {studies!r}, not a non-empty list of study accessions (PRJEB…)")
    if len(set(studies)) != len(studies):
        raise ValueError(f"{at} ena_studies: lists a study twice")
    child_column = expect_name(entry["child"]["column"], f"{at} child column")
    counts_column = expect_name(entry["counts"]["column"], f"{at} counts column")
    if child_column == counts_column:
        raise ValueError(f"{at}: child and counts are both column {child_column!r}")
    return Entry(
        dataset=dataset,
        table=table,
        child_column=child_column,
        counts_column=counts_column,
        ena_studies=tuple(studies),
        reads_in=expect_name(entry["reads_in"], f"{at} reads_in"),
    )
