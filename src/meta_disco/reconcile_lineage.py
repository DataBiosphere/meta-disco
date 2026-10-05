"""Reconcile's lineage pass: the steps the source tables state, resolved to the run's files (#577).

The lineage importer (#583) writes what each source said about how a file was made;
the activity translation table (#584) says what step those words mean and the role
the parent takes. This pass is the join between those and a stored run, beside
reconcile's slot-evidence join (``reconcile.join``) and shaped like it:

1. **Translate.** Every lineage line of the run's repository and catalog is keyed and
   selects an activity-map row (``activity_map.keyed_lines``, which also joins each
   file's raw ``data_type``). A line selecting no authored row is counted
   ``untranslated`` and gives nothing. A line whose parent is a sample
   (``parent_key_type: biosample_id``) is counted ``sample_parent`` and gives nothing:
   only file parents become inputs here (#582).
2. **Resolve, within the child's dataset.** The child by the envelope's ``target_key``
   and the parent by its ``parent_key_type`` (``file_id`` or ``drs_uri``; an IGVF
   accession was already written as its DRS URI by the importer), each against that
   field of the run's records whose ``dataset_title`` is the envelope's target dataset.
   The one exception is a line naming its parent's dataset (``parent_dataset``, #594):
   its parent is looked for in that dataset where the run lineage map declares the line's
   source and the child's dataset taking its reads from it
   (``run_lineage_map.RunLineageMap.declares``), and any other such line is counted
   ``undeclared_dataset`` and gives nothing.
   One carrier resolves it; none is ``not_in_dataset``, several ``several_match``, and
   either gives no input (counted, never written onto a record). A line naming no locator
   for its parent (``parent`` absent) is ``not_in_dataset``. A child no record carries is
   ``child_not_in_run``, one several carry ``child_several_match``, and a parent that is
   the child itself ``parent_is_child``.
3. **Hand each resolved line to its child** as an ``edges.LineageStep``, cited by
   ``edges.lineage_attribution``. Merging them with inference's own step is
   ``edges.merge_steps``, called per record by reconcile.

The pass is two halves around reconcile's one scan of the run's records:
:func:`translate_lineage` reads the lines and names the locators it needs, the scan
(``reconcile.join``, whose slot-evidence locators share it) finds every record carrying
one, and :func:`resolve_lineage` hands each resolved line to its child. The run is never
held whole.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .activity_map import ActivityMap, Row, generation_stamp, keyed_lines
from .edges import LineageStep, lineage_attribution, parent_kind_of
from .lineage_evidence import read_lineage_envelope
from .output_utils import relative_to
from .records import JOIN_KEY_OUTPUT_FIELDS
from .run_lineage_map import RunLineageMap
from .schema.classification_model import EvidenceTarget, LineageParentKeyEnum
from .source_evidence import claim_source_for, discover

# The per-source outcome of a line, after `offered`.
RESOLVED = "resolved"
NOT_IN_DATASET = "not_in_dataset"
SEVERAL_MATCH = "several_match"
UNTRANSLATED = "untranslated"
SAMPLE_PARENT = "sample_parent"
UNDECLARED_DATASET = "undeclared_dataset"
CHILD_NOT_IN_RUN = "child_not_in_run"
CHILD_SEVERAL_MATCH = "child_several_match"
PARENT_IS_CHILD = "parent_is_child"
OUTCOMES = (
    RESOLVED,
    NOT_IN_DATASET,
    SEVERAL_MATCH,
    UNTRANSLATED,
    SAMPLE_PARENT,
    UNDECLARED_DATASET,
    CHILD_NOT_IN_RUN,
    CHILD_SEVERAL_MATCH,
    PARENT_IS_CHILD,
)

# A value a record is looked up by: the output-row field, the dataset the lookup is scoped
# to (None for every dataset), and the value. ``reconcile.join``'s key; a lineage line's is
# scoped to its child's dataset, or to the dataset a declared line names for its parent.
Locator = tuple[str, str | None, str]


@dataclass(frozen=True)
class Carrier:
    """A record that carries a locator: its record key, its own name, and its inferred ``data_type``."""

    key: str
    file_name: str
    data_type: str | None


def applies(target: EvidenceTarget, repository: str, catalog: str | None) -> bool:
    """Whether evidence about ``target`` is this run's: about ``repository``'s files, of ``catalog`` where the input names one.

    The one rule for slot evidence (``reconcile.select_evidence``) and lineage alike: a file
    for another catalog is an older catalog's history and is not read.
    """
    return target.system == repository and (catalog is None or target.version == catalog)


@dataclass
class PendingLineage:
    """The first half's result: the translated lines waiting for their files, and the locators they need."""

    # Per line: its source's counts, its attribution, its row, and its child's and parent's locators.
    lines: list[tuple[Counter, dict, Row, Locator, Locator | None]] = field(default_factory=list)
    wanted: set[Locator] = field(default_factory=set)
    # Per source type and dataset: offered lines, and each outcome's count.
    counts: dict[str, dict[str, Counter]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(Counter)))
    # The lineage files read, relative to the lineage root.
    files: list[str] = field(default_factory=list)


@dataclass
class LineageJoin:
    """The pass's result: per child record key, its resolved steps; and per source, what became of its lines."""

    steps: dict[str, list[LineageStep]] = field(default_factory=lambda: defaultdict(list))
    counts: dict[str, dict[str, Counter]] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)


def latest_catalog(paths: list[Path]) -> list[Path]:
    """The ``paths`` of the catalog holding the newest generation stamp, as ``activity_map.lineage_paths`` chooses it."""
    by_catalog: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        by_catalog[str(read_lineage_envelope(path).target.version)].append(path)
    if not by_catalog:
        return []
    return by_catalog[max(by_catalog, key=lambda c: max(generation_stamp(p) for p in by_catalog[c]))]


def translate_lineage(
    lineage_root: Path,
    evidence_root: Path,
    repository: str,
    catalog: str | None,
    table: ActivityMap,
    run_map: RunLineageMap,
) -> PendingLineage:
    """Read and translate every lineage line that :func:`applies` to the run; see the module docstring, steps 1 and 2.

    Where the input names no catalog, only the latest catalog's lineage about this
    repository is read (:func:`latest_catalog`): lineage is read one catalog at a time.
    ``run_map`` says which lines naming their parent's dataset are declared.
    """
    pending = PendingLineage()
    paths = [p for p in discover(lineage_root) if applies(read_lineage_envelope(p).target, repository, catalog)]
    if catalog is None:
        paths = latest_catalog(paths)
    pending.files = [relative_to(p, lineage_root) for p in paths]
    for keyed in keyed_lines(lineage_root, evidence_root, paths):
        envelope, line = keyed.envelope, keyed.line
        # Scoped by the target's name for the dataset, as `reconcile.join` scopes slot evidence.
        dataset = str(envelope.target.dataset)
        counts = pending.counts[str(envelope.source_type)][dataset]
        counts["offered"] += 1
        if str(line.parent_key_type) == LineageParentKeyEnum.biosample_id.value:
            counts[SAMPLE_PARENT] += 1
            continue
        # Before the activity map, so a forbidden crossing is counted as one, not as a step to author.
        if line.parent_dataset is not None and not run_map.declares(envelope, line.parent_dataset):
            counts[UNDECLARED_DATASET] += 1
            continue
        row = table.select(keyed.key)
        if row is None or not row.authored:
            counts[UNTRANSLATED] += 1
            continue
        child = (JOIN_KEY_OUTPUT_FIELDS[str(envelope.target_key)], dataset, line.target_key_value)
        parent_dataset = line.parent_dataset or dataset
        parent = None
        if line.parent is not None and line.parent_key_type is not None:
            parent = (JOIN_KEY_OUTPUT_FIELDS[str(line.parent_key_type)], parent_dataset, line.parent)
            pending.wanted.add(parent)
        pending.wanted.add(child)
        source = claim_source_for(envelope.source, line.parent_column)
        attribution = lineage_attribution(str(envelope.source_type), row.id, source, line.activity_id)
        pending.lines.append((counts, attribution, row, child, parent))
    return pending


def resolve_lineage(pending: PendingLineage, carriers: dict[Locator, list[Carrier]]) -> LineageJoin:
    """Hand each translated line whose child and parent each one record carries to that child; count the rest."""
    result = LineageJoin(counts=pending.counts, files=pending.files)
    for counts, attribution, row, child, parent in pending.lines:
        children = carriers.get(child, [])
        if len(children) != 1:
            counts[CHILD_NOT_IN_RUN if not children else CHILD_SEVERAL_MATCH] += 1
            continue
        parents = carriers.get(parent, []) if parent is not None else []
        if len(parents) != 1:
            counts[NOT_IN_DATASET if not parents else SEVERAL_MATCH] += 1
            continue
        ((found_child,), (found_parent,)) = children, parents
        if found_parent.key == found_child.key:
            counts[PARENT_IS_CHILD] += 1
            continue
        counts[RESOLVED] += 1
        result.steps[found_child.key].append(
            LineageStep(
                str(row.activity),
                str(row.role),
                found_parent.key,
                found_parent.file_name,
                parent_kind_of(found_parent.file_name),
                attribution,
                found_parent.data_type,
            )
        )
    return result
