"""Compare two corpus generations — input snapshots by md5, run outputs by label (#335).

The catalog migration from ``anvil14`` to ``anvil15`` asks two questions that a
single-run coverage report cannot answer:

1. **Did the corpus itself change?** Compare two input snapshots file by file, by
   md5, rather than by the catalog's own dataset counts. ``snapshot_parity``
   answers this per dataset: how many files carry identical content, how many kept
   a name but changed md5, how many left, how many arrived.
2. **If coverage moved, was it the catalog or the classifier?** ``diff_runs``
   splits every per-dimension delta three ways — files that left the corpus
   (``lost``), files that arrived (``gained``), and files present in *both* runs
   whose label changed (``changed``). Only the third is classifier behaviour; the
   first two are catalog membership.

Both comparisons identify a file by ``(dataset_title, file_name, md5sum)``. md5 is
part of the identity on purpose: a file whose content changed is a different file
for classification purposes, so it appears as one ``lost`` plus one ``gained``
rather than as a label change. ``snapshot_parity`` is what quantifies that case —
read the two together, and when parity reports no md5 changes, ``lost``/``gained``
are purely catalog membership.

A repeated identity (the same name and md5 twice within one dataset) is kept as a
multiset, so multiplicities are compared rather than collapsed, and the per-run
totals here match the ones the coverage report prints.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .models import CLASSIFICATION_FIELDS, field_label
from .output_utils import CLASSIFICATION_FILES

# A file's identity across generations: (dataset_title, file_name, md5sum).
FileKey = tuple[str, str, str]
# One dimension's label: its value when classified, else its status.
# ``field_label``'s return type admits ``None``; the entry-coherence check in
# ``models`` makes that unreachable through a well-formed run (it raises on a
# classified entry with no value rather than returning one), so the type is
# widened here instead of fabricating a stand-in string for a case that cannot
# arrive.
Label = str | None
# One file's labels, in CLASSIFICATION_FIELDS order.
Labels = tuple[Label, ...]


@dataclass(frozen=True)
class SnapshotMeta:
    """The envelope facts of an input snapshot, for the report header.

    ``catalog`` is ``None`` for a snapshot pulled before the catalog was recorded
    (the archived anvil14 pull) — reported as unrecorded rather than guessed.
    """

    path: Path
    catalog: str | None
    downloaded_at: str | None
    total_files: int | None


@dataclass(frozen=True)
class DatasetParity:
    """Per-dataset md5 parity between two input snapshots.

    ``unchanged`` counts files matched on name *and* md5. Among the remaining
    copies of a name present in both snapshots, ``md5_changed`` pairs them up; the
    leftovers are ``removed`` (only in the old snapshot) and ``added`` (only in the
    new one).
    """

    dataset: str
    unchanged: int
    md5_changed: int
    removed: int
    added: int

    @property
    def old_total(self) -> int:
        return self.unchanged + self.md5_changed + self.removed

    @property
    def new_total(self) -> int:
        return self.unchanged + self.md5_changed + self.added


@dataclass(frozen=True)
class DimensionDiff:
    """One dimension's before/after labels and the attribution of the difference.

    ``old``/``new`` are label histograms over each run (a label is the field's
    value when classified, else its status — ``models.field_label``). The other
    three cover the difference between them, over file identities:

    * ``lost`` — label in the old run, identity absent from the new run.
    * ``gained`` — label in the new run, identity absent from the old run.
    * ``changed`` — identity in both runs, keyed ``(old_label, new_label)``.

    Together they account for the whole delta: ``new - old`` equals gained minus
    lost plus the net of ``changed``.
    """

    dimension: str
    old: Counter[Label]
    new: Counter[Label]
    lost: Counter[Label]
    gained: Counter[Label]
    changed: Counter[tuple[Label, Label]]

    @staticmethod
    def _classified(counts: Counter[Label]) -> int:
        """Count of labels that represent a real value.

        ``field_label`` renders a classified field as its value and an unclassified
        one as its status, so every label that is not a status string is a value.
        """
        return sum(count for label, count in counts.items() if _is_value(label))

    @property
    def classified_old(self) -> int:
        return self._classified(self.old)

    @property
    def classified_new(self) -> int:
        return self._classified(self.new)

    @property
    def classified_lost(self) -> int:
        """Classified files that left the corpus."""
        return self._classified(self.lost)

    @property
    def classified_gained(self) -> int:
        """Classified files that arrived in the corpus."""
        return self._classified(self.gained)

    @property
    def classified_net_changed(self) -> int:
        """Net classified count from files present in both runs whose label changed.

        Positive when more files became classified than stopped being classified —
        the classifier-behaviour half of the delta.
        """
        net = 0
        for (old_label, new_label), count in self.changed.items():
            net += count * (int(_is_value(new_label)) - int(_is_value(old_label)))
        return net


# The statuses field_label emits in place of a value. Anything else it emits is a
# real value, so a label outside this set means the field was classified.
_STATUS_LABELS = frozenset({"not_classified", "not_applicable", "conflict"})


def _is_value(label: Label) -> bool:
    """True when a ``field_label`` string is a real value rather than a status."""
    return label is not None and label not in _STATUS_LABELS


def snapshot_meta(path: Path) -> SnapshotMeta:
    """Read an input snapshot's ``metadata`` envelope without loading its records.

    Reads the whole JSON file (the envelope's keys precede ``files``, but json does
    not stream), so call it once per snapshot. An ``.ndjson`` input carries no
    envelope and yields all-``None`` facts beyond the path.
    """
    if path.suffix == ".ndjson":
        return SnapshotMeta(path=path, catalog=None, downloaded_at=None, total_files=None)
    with path.open() as handle:
        data = json.load(handle)
    meta = data.get("metadata", {}) if isinstance(data, dict) else {}
    return SnapshotMeta(
        path=path,
        catalog=meta.get("catalog"),
        downloaded_at=meta.get("downloaded_at"),
        total_files=meta.get("total_files"),
    )


def _snapshot_index(records: list) -> dict[tuple[str, str], Counter[str]]:
    """Index snapshot records as ``(dataset, file_name) -> Counter of md5``.

    Non-dict entries and records missing a name are skipped: this is a parity
    report, not the input-contract gate (``validate_metadata``), which is where a
    malformed record is meant to surface.
    """
    index: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for record in records:
        if not isinstance(record, dict):
            continue
        file_name = record.get("file_name")
        if not file_name:
            continue
        dataset = str(record.get("dataset_title") or "")
        index[(dataset, str(file_name))][str(record.get("file_md5sum") or "")] += 1
    return index


def snapshot_parity(old_records: list, new_records: list) -> list[DatasetParity]:
    """Compare two input snapshots by md5, one row per dataset.

    A dataset present in only one snapshot still gets a row, with its files counted
    entirely as ``removed`` or ``added`` — which is how a dataset that lost catalog
    accessibility (``ANVIL_GTEx_public_data``) reports.

    Rows are ordered by the size of the difference (largest first), then by name,
    so a dataset that changed leads the table and the identical ones follow.
    """
    old_index = _snapshot_index(old_records)
    new_index = _snapshot_index(new_records)

    tallies: dict[str, dict[str, int]] = defaultdict(
        lambda: dict.fromkeys(("unchanged", "md5_changed", "removed", "added"), 0)
    )
    for key in set(old_index) | set(new_index):
        dataset, _ = key
        old_md5s = old_index.get(key, Counter())
        new_md5s = new_index.get(key, Counter())
        # Identical content matches first; the remaining copies of this name pair up
        # as an md5 change, and whatever is still left is a removal or an addition.
        unchanged = sum((old_md5s & new_md5s).values())
        old_left = sum(old_md5s.values()) - unchanged
        new_left = sum(new_md5s.values()) - unchanged
        md5_changed = min(old_left, new_left)
        tally = tallies[dataset]
        tally["unchanged"] += unchanged
        tally["md5_changed"] += md5_changed
        tally["removed"] += old_left - md5_changed
        tally["added"] += new_left - md5_changed

    rows = [DatasetParity(dataset=dataset, **tally) for dataset, tally in tallies.items()]
    return sorted(rows, key=lambda row: (-(row.md5_changed + row.removed + row.added), row.dataset))


def run_labels(run_dir: Path) -> dict[FileKey, Counter[Labels]]:
    """Read a run directory into ``file identity -> multiset of label tuples``.

    Covers exactly the files in ``CLASSIFICATION_FILES``; one that a run did not
    write is skipped, the same way the coverage and validation reports skip it.
    Labels are read with ``models.field_label``, so a classified field contributes
    its value and an unclassified one its status.

    Raises FileNotFoundError if the run directory does not exist — an empty result
    would otherwise read as a run with no coverage.
    """
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    labels: dict[FileKey, Counter[Labels]] = defaultdict(Counter)
    for fname in CLASSIFICATION_FILES:
        path = run_dir / fname
        if not path.is_file():
            continue
        with path.open() as handle:
            data = json.load(handle)
        for record in data.get("classifications", data.get("results", [])):
            key: FileKey = (
                str(record.get("dataset_title") or ""),
                str(record.get("file_name") or ""),
                str(record.get("md5sum") or ""),
            )
            labels[key][tuple(field_label(record, field) for field in CLASSIFICATION_FIELDS)] += 1
    return dict(labels)


def _dimension_counts(labels: Counter[Labels], index: int) -> Counter[Label]:
    """Histogram of one dimension's labels across a multiset of label tuples."""
    counts: Counter[Label] = Counter()
    for label_tuple, count in labels.items():
        counts[label_tuple[index]] += count
    return counts


def _sort_key(label_tuple: Labels) -> tuple[str, ...]:
    """Order label tuples for pairing, tolerating a ``None`` label.

    ``sorted`` on the tuples directly would raise as soon as one position holds a
    ``None`` and another a string, so ``None`` sorts as the empty string here. The
    order only decides which leftover pairs with which, so any total order does.
    """
    return tuple("" if label is None else label for label in label_tuple)


def partition_by_dataset(labels: dict[FileKey, Counter[Labels]]) -> dict[str, dict[FileKey, Counter[Labels]]]:
    """Split a run's labels by dataset title, sharing the underlying counters.

    Lets the per-dataset section diff each dataset against its counterpart in one
    pass over the corpus rather than re-scanning every key per dataset.
    """
    partitioned: dict[str, dict[FileKey, Counter[Labels]]] = defaultdict(dict)
    for key, counter in labels.items():
        partitioned[key[0]][key] = counter
    return dict(partitioned)


def diff_runs(
    old_labels: dict[FileKey, Counter[Labels]],
    new_labels: dict[FileKey, Counter[Labels]],
) -> dict[str, DimensionDiff]:
    """Diff two runs' labels per dimension, attributing the delta.

    Pass whole runs, or one dataset's slice of each from
    ``partition_by_dataset``.

    Where an identity carries several copies (the same name and md5 twice in a
    dataset), the copies are matched pairwise as multisets: identical label tuples
    cancel, the remaining copies pair up into label changes, and any copy left
    unpaired — because the two runs hold different numbers of it — counts as lost
    or gained. A file identity in only one run contributes to ``lost`` or
    ``gained`` and never to ``changed``.
    """
    old_counts: dict[str, Counter[Label]] = {field: Counter() for field in CLASSIFICATION_FIELDS}
    new_counts: dict[str, Counter[Label]] = {field: Counter() for field in CLASSIFICATION_FIELDS}
    lost: dict[str, Counter[Label]] = {field: Counter() for field in CLASSIFICATION_FIELDS}
    gained: dict[str, Counter[Label]] = {field: Counter() for field in CLASSIFICATION_FIELDS}
    changed: dict[str, Counter[tuple[Label, Label]]] = {field: Counter() for field in CLASSIFICATION_FIELDS}

    # One pass per run for the histograms: every dimension is tallied per record,
    # rather than re-walking the corpus once per dimension.
    for counts, run in ((old_counts, old_labels), (new_counts, new_labels)):
        for labels in run.values():
            for label_tuple, count in labels.items():
                for index, field in enumerate(CLASSIFICATION_FIELDS):
                    counts[field][label_tuple[index]] += count

    for key, labels in old_labels.items():
        counterpart = new_labels.get(key)
        if counterpart is None:
            for index, field in enumerate(CLASSIFICATION_FIELDS):
                lost[field] += _dimension_counts(labels, index)
            continue
        # Identical label tuples cancel; what is left on each side pairs up, in a
        # stable order, into the label changes for this identity.
        old_left = sorted((labels - counterpart).elements(), key=_sort_key)
        new_left = sorted((counterpart - labels).elements(), key=_sort_key)
        for old_tuple, new_tuple in zip(old_left, new_left, strict=False):
            for index, field in enumerate(CLASSIFICATION_FIELDS):
                if old_tuple[index] != new_tuple[index]:
                    changed[field][(old_tuple[index], new_tuple[index])] += 1
        # An identity carried by unequal numbers of copies in the two runs has
        # leftovers with nothing to pair against: those copies genuinely left or
        # arrived, so they belong in lost/gained, not in changed.
        for extra in old_left[len(new_left) :]:
            for index, field in enumerate(CLASSIFICATION_FIELDS):
                lost[field][extra[index]] += 1
        for extra in new_left[len(old_left) :]:
            for index, field in enumerate(CLASSIFICATION_FIELDS):
                gained[field][extra[index]] += 1

    for key, labels in new_labels.items():
        if key in old_labels:
            continue
        for index, field in enumerate(CLASSIFICATION_FIELDS):
            gained[field] += _dimension_counts(labels, index)

    return {
        field: DimensionDiff(
            dimension=field,
            old=old_counts[field],
            new=new_counts[field],
            lost=lost[field],
            gained=gained[field],
            changed=changed[field],
        )
        for field in CLASSIFICATION_FIELDS
    }


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "—"


def _snapshot_line(label: str, meta: SnapshotMeta) -> str:
    catalog = meta.catalog or "(unrecorded)"
    pulled = meta.downloaded_at or "(unrecorded)"
    total = f"{meta.total_files:,}" if meta.total_files is not None else "(unrecorded)"
    return f"| {label} | `{meta.path}` | {catalog} | {pulled} | {total} |"


def render_parity_section(old_meta: SnapshotMeta, new_meta: SnapshotMeta, rows: list[DatasetParity]) -> list[str]:
    """Markdown for the input-snapshot parity section."""
    lines = [
        "## Input snapshots",
        "",
        "| | file | catalog | pulled | files |",
        "|---|---|---|---|---:|",
        _snapshot_line("old", old_meta),
        _snapshot_line("new", new_meta),
        "",
        "### Parity by md5, per dataset",
        "",
        "A file is matched on `(dataset, file name, md5)`. `md5 changed` counts files",
        "that kept their name within a dataset but changed content.",
        "",
        "| dataset | old | new | unchanged | md5 changed | removed | added |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    totals = dict.fromkeys(("unchanged", "md5_changed", "removed", "added"), 0)
    for row in rows:
        lines.append(
            f"| {row.dataset or '(none)'} | {row.old_total:,} | {row.new_total:,} | "
            f"{row.unchanged:,} | {row.md5_changed:,} | {row.removed:,} | {row.added:,} |"
        )
        totals["unchanged"] += row.unchanged
        totals["md5_changed"] += row.md5_changed
        totals["removed"] += row.removed
        totals["added"] += row.added
    old_total = totals["unchanged"] + totals["md5_changed"] + totals["removed"]
    new_total = totals["unchanged"] + totals["md5_changed"] + totals["added"]
    lines.append(
        f"| **total** | **{old_total:,}** | **{new_total:,}** | **{totals['unchanged']:,}** | "
        f"**{totals['md5_changed']:,}** | **{totals['removed']:,}** | **{totals['added']:,}** |"
    )
    lines.append("")
    return lines


def render_coverage_section(diffs: dict[str, DimensionDiff], old_total: int, new_total: int) -> list[str]:
    """Markdown for the per-dimension coverage table and its attribution.

    ``classified`` here means the field carries a real value.
    ``docs/anvil-coverage-report.md`` counts differently — its Classified row is
    everything that is not ``not_classified``, so it folds ``not_applicable`` in —
    hence the ``n/a`` columns, which reconcile the two: that report's figure is
    ``classified`` plus ``n/a``.
    """
    lines = [
        "## Coverage by dimension",
        "",
        f"Files classified out of {old_total:,} (old) and {new_total:,} (new).",
        "`classified` counts a real value; `n/a` counts `not_applicable`, which the",
        "coverage report folds into its own Classified row.",
        "",
        "| dimension | old | new | old % | new % | delta | old n/a | new n/a |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for field in CLASSIFICATION_FIELDS:
        diff = diffs[field]
        delta = diff.classified_new - diff.classified_old
        lines.append(
            f"| {field} | {diff.classified_old:,} | {diff.classified_new:,} | "
            f"{_pct(diff.classified_old, old_total)} | {_pct(diff.classified_new, new_total)} | {delta:+,} | "
            f"{diff.old['not_applicable']:,} | {diff.new['not_applicable']:,} |"
        )

    lines += [
        "",
        "### Where the delta comes from",
        "",
        "`corpus loss` and `corpus gain` count classified files whose identity is",
        "absent from the other run — catalog membership, not classifier behaviour.",
        "`label change` is the net classified count over files present in **both**",
        "runs, which is the only classifier-behaviour column.",
        "",
        "| dimension | delta | corpus loss | corpus gain | label change |",
        "|---|---:|---:|---:|---:|",
    ]
    for field in CLASSIFICATION_FIELDS:
        diff = diffs[field]
        delta = diff.classified_new - diff.classified_old
        lines.append(
            f"| {field} | {delta:+,} | -{diff.classified_lost:,} | +{diff.classified_gained:,} | "
            f"{diff.classified_net_changed:+,} |"
        )
    lines.append("")
    return lines


def render_changes_section(diffs: dict[str, DimensionDiff], limit: int = 15) -> list[str]:
    """Markdown listing the label changes over files present in both runs.

    These are classifier-behaviour differences: the corpus identity is the same and
    the label moved. Lists at most ``limit`` transitions per dimension, largest
    first, and says how many were elided.
    """
    lines = ["## Label changes on files present in both runs", ""]
    if not any(diff.changed for diff in diffs.values()):
        lines += ["No file present in both runs changed a label.", ""]
        return lines

    for field in CLASSIFICATION_FIELDS:
        changed = diffs[field].changed
        if not changed:
            continue
        lines += [
            f"### {field}",
            "",
            "| old label | new label | files |",
            "|---|---|---:|",
        ]
        for (old_label, new_label), count in changed.most_common(limit):
            lines.append(f"| `{old_label}` | `{new_label}` | {count:,} |")
        remaining = len(changed) - min(limit, len(changed))
        if remaining:
            lines.append(f"| … | {remaining:,} further transitions | |")
        lines.append("")
    return lines


def render_dataset_section(
    old_labels: dict[FileKey, Counter[Labels]],
    new_labels: dict[FileKey, Counter[Labels]],
) -> list[str]:
    """Markdown for per-dataset classified counts, one row per dataset and dimension.

    Every dataset in either run gets a row, so a dataset that left the catalog
    reports its old counts against zero.
    """
    old_by_dataset = partition_by_dataset(old_labels)
    new_by_dataset = partition_by_dataset(new_labels)
    lines = [
        "## Per-dataset classified counts",
        "",
        "| dataset | dimension | old | new | delta |",
        "|---|---|---:|---:|---:|",
    ]
    for dataset in sorted(set(old_by_dataset) | set(new_by_dataset)):
        diffs = diff_runs(old_by_dataset.get(dataset, {}), new_by_dataset.get(dataset, {}))
        for field in CLASSIFICATION_FIELDS:
            diff = diffs[field]
            delta = diff.classified_new - diff.classified_old
            lines.append(
                f"| {dataset or '(none)'} | {field} | {diff.classified_old:,} | {diff.classified_new:,} | {delta:+,} |"
            )
    lines.append("")
    return lines


def _run_total(labels: dict[FileKey, Counter[Labels]]) -> int:
    """Number of records a run classified, counting repeated identities separately."""
    return sum(sum(counter.values()) for counter in labels.values())


def render_report(
    old_meta: SnapshotMeta,
    new_meta: SnapshotMeta,
    parity: list[DatasetParity],
    old_run: Path,
    new_run: Path,
    old_labels: dict[FileKey, Counter[Labels]],
    new_labels: dict[FileKey, Counter[Labels]],
    generated_at: str,
) -> str:
    """Assemble the full comparison report."""
    old_total = _run_total(old_labels)
    new_total = _run_total(new_labels)
    diffs = diff_runs(old_labels, new_labels)

    lines = [
        "# Corpus comparison",
        "",
        f"Generated {generated_at} by `scripts/compare_corpus.py` (issue #335).",
        "",
        f"Runs compared: `{old_run}` → `{new_run}`.",
        "",
    ]
    lines += render_parity_section(old_meta, new_meta, parity)
    lines += render_coverage_section(diffs, old_total, new_total)
    lines += render_changes_section(diffs)
    lines += render_dataset_section(old_labels, new_labels)
    return "\n".join(lines)
