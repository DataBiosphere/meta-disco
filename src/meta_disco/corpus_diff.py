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

The two comparisons identify a file differently, on purpose. The run diff
identifies it by *content* — ``(dataset_title, file_name, md5sum)`` — so a file
whose bytes changed is a different file for classification purposes and appears as
one ``lost`` plus one ``gained`` rather than as a label change. Parity identifies
it by ``(dataset_title, file_name)`` and *compares* md5, which is the only way it
can report an md5 change at all. So the two tables' columns are not joinable: read
them together, and when parity reports no md5 changes, the run diff's
``lost``/``gained`` are purely catalog membership.

A repeated identity (the same name and md5 twice within one dataset) is kept as a
multiset, so multiplicities are compared rather than collapsed, and the per-run
totals here match the ones the coverage report prints.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .models import CLASSIFICATION_FIELDS, STATUS_LABELS, field_label
from .output_utils import iter_records
from .pipeline import load_snapshot
from .summaries import escape_md_cell

# A file's identity across generations: (dataset_title, file_name, md5sum).
FileKey = tuple[str, str, str]
# One dimension's label: its value when classified, else its status.
# ``field_label``'s return type admits ``None``, and this module reads stored runs
# it cannot itself verify, so the type is widened rather than fabricating a
# stand-in string. (Through a well-formed run it does not arrive: the
# entry-coherence check in ``models`` raises on a classified entry with no value.)
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

        ``field_label`` renders a classified field as its value and any other field
        as its status, so a label outside ``models.STATUS_LABELS`` is a value.
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


def _is_value(label: Label) -> bool:
    """True when a ``field_label`` string is a real value rather than a status.

    The status vocabulary is ``models.STATUS_LABELS``, so a status added there is
    excluded here too rather than being counted as a value.
    """
    return label is not None and label not in STATUS_LABELS


def _as_int(value) -> int | None:
    """Coerce an envelope count to ``int``, or ``None`` when it is not a number.

    ``total_files`` is the one envelope fact rendered with a numeric format, so a
    snapshot that stored it as a string would otherwise fail at render time —
    after both files have been parsed. Reported as unrecorded instead.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_snapshot(path: Path) -> tuple[SnapshotMeta, list]:
    """Read an input snapshot's envelope facts and its records in one parse.

    These files are several hundred megabytes, so the header and the records come
    from the same ``pipeline.load_snapshot`` call rather than two full parses. An
    ``.ndjson`` input carries no envelope, so its facts beyond the path are
    ``None``.
    """
    metadata, records = load_snapshot(path)
    return (
        SnapshotMeta(
            path=path,
            catalog=metadata.get("catalog"),
            downloaded_at=metadata.get("downloaded_at"),
            total_files=_as_int(metadata.get("total_files")),
        ),
        records,
    )


def _snapshot_index(records: list) -> dict[tuple[str, str], Counter[str]]:
    """Index snapshot records as ``(dataset, file_name) -> Counter of md5``.

    Non-dict entries and records missing a name are skipped: this is a parity
    report, not the input-contract gate (``validate_metadata``), which is where a
    malformed record is meant to surface.

    Every record is assumed to carry a ``file_md5sum``. The input contract
    requires one and ``validate_metadata`` reports any record that lacks it, but
    nothing forces that gate to run before this report — ``make classify`` has no
    such prerequisite — so the assumption is *measured*, not enforced: as of
    2026-09-04 no snapshot on disk held such a record (#375). One that did would
    be counted under the empty string, and two of them sharing a dataset and name
    would read as ``unchanged``. #376 turns the measurement into a guarantee by excluding
    checksum-less files from processing; until it lands, this is the accepted risk
    recorded on #375.
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

    tallies: dict[str, Counter[str]] = defaultdict(Counter)
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
        tallies[dataset].update(
            unchanged=unchanged,
            md5_changed=md5_changed,
            removed=old_left - md5_changed,
            added=new_left - md5_changed,
        )

    # Read the four fields by name rather than splatting the tally: DatasetParity's
    # fields then stay independent of the tally's keys, which a bare ``**tally``
    # would silently couple.
    rows = [
        DatasetParity(
            dataset=dataset,
            unchanged=tally["unchanged"],
            md5_changed=tally["md5_changed"],
            removed=tally["removed"],
            added=tally["added"],
        )
        for dataset, tally in tallies.items()
    ]
    return sorted(rows, key=lambda row: (-(row.md5_changed + row.removed + row.added), row.dataset))


def run_labels(run_dir: Path) -> dict[FileKey, Counter[Labels]]:
    """Read a run directory into ``file identity -> multiset of label tuples``.

    Reads the run through ``output_utils.iter_records``, so it covers the same
    files and tolerates the same shapes as the consistency linter. Labels are read
    with ``models.field_label``, so a classified field contributes its value and an
    unclassified one its status.

    Every record is assumed to carry an ``md5sum`` (the output echo of the input
    contract's ``file_md5sum``). That is not guaranteed by the contract alone: a
    record violating it is not dropped but diverted to a ``validation_failed``
    row, which is still written with its md5 echoed as-is (#155), so a null md5
    can in principle reach this reader. None did when last measured — 0 of 1.4M records
    across every run on disk, 2026-09-04 (#375) — and #376 excludes such files
    from classification, which makes it a guarantee rather than a measurement.

    Only md5 matters for the join: ``dataset_title`` is a qualifier and is
    legitimately ``None`` for the HPRC source, so it is normalized to the empty
    string rather than required — requiring it would drop that corpus entirely.

    Raises FileNotFoundError if the run directory does not exist — an empty result
    would otherwise read as a run with no coverage.
    """
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    labels: dict[FileKey, Counter[Labels]] = defaultdict(Counter)
    # The corpus holds ~700K records but only a few dozen distinct label tuples, so
    # each tuple is interned: one shared object per distinct combination instead of
    # a fresh tuple and five fresh strings per record.
    interned: dict[Labels, Labels] = {}
    for record in iter_records(run_dir):
        key: FileKey = (
            str(record.get("dataset_title") or ""),
            str(record.get("file_name") or ""),
            str(record.get("md5sum") or ""),
        )
        label_tuple: Labels = tuple(field_label(record, field) for field in CLASSIFICATION_FIELDS)
        labels[key][interned.setdefault(label_tuple, label_tuple)] += 1
    return dict(labels)


def _sort_key(label_tuple: Labels) -> str:
    """Order label tuples for pairing, tolerating a ``None`` label.

    ``sorted`` on the tuples directly would raise as soon as one position holds a
    ``None`` and another a string. Rendering the tuple is a total order over every
    shape, and the order only decides which leftover pairs with which, so any total
    order does.
    """
    return str(label_tuple)


def classified_by_dataset(labels: dict[FileKey, Counter[Labels]]) -> dict[str, Counter[str]]:
    """Per dataset, how many records carry a real value for each dimension.

    One pass over the run. The per-dataset table reports coverage only, so it does
    not need the identity join or the multiset pairing ``diff_runs`` does — running
    that per dataset would be a second full attribution pass for two numbers.
    """
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for (dataset, _, _), tuples in labels.items():
        # Bind the bucket before the value test, so a dataset whose files carry no
        # classified value on any dimension is still a key — otherwise it would
        # vanish from the per-dataset table, which is exactly the case (a dataset
        # the classifier recognises nothing in) the table exists to show.
        bucket = counts[dataset]
        for label_tuple, n in tuples.items():
            for index, field in enumerate(CLASSIFICATION_FIELDS):
                if _is_value(label_tuple[index]):
                    bucket[field] += n
    return dict(counts)


def diff_runs(
    old_labels: dict[FileKey, Counter[Labels]],
    new_labels: dict[FileKey, Counter[Labels]],
) -> dict[str, DimensionDiff]:
    """Diff two runs' labels per dimension, attributing the delta.

    Where an identity carries several copies (the same name and md5 twice in a
    dataset), the copies are matched pairwise as multisets: identical label tuples
    cancel, the remaining copies pair up into label changes, and any copy left
    unpaired — because the two runs hold different numbers of it — counts as lost
    or gained. A file identity in only one run contributes to ``lost`` or
    ``gained`` and never to ``changed``.
    """
    # Per-dimension accumulators, held as lists indexed the same way a label tuple
    # is, so the inner loops index rather than re-look-up a field name per record.
    old_counts: list[Counter[Label]] = [Counter() for _ in CLASSIFICATION_FIELDS]
    new_counts: list[Counter[Label]] = [Counter() for _ in CLASSIFICATION_FIELDS]
    lost: list[Counter[Label]] = [Counter() for _ in CLASSIFICATION_FIELDS]
    gained: list[Counter[Label]] = [Counter() for _ in CLASSIFICATION_FIELDS]
    changed: list[Counter[tuple[Label, Label]]] = [Counter() for _ in CLASSIFICATION_FIELDS]
    dimensions = range(len(CLASSIFICATION_FIELDS))

    # One pass per run for the histograms: every dimension is tallied per record,
    # rather than re-walking the corpus once per dimension.
    for counts, run in ((old_counts, old_labels), (new_counts, new_labels)):
        for labels in run.values():
            for label_tuple, count in labels.items():
                for index in dimensions:
                    counts[index][label_tuple[index]] += count

    for key, labels in old_labels.items():
        counterpart = new_labels.get(key)
        if counterpart is None:
            for label_tuple, count in labels.items():
                for index in dimensions:
                    lost[index][label_tuple[index]] += count
            continue
        if labels == counterpart:
            # The overwhelmingly common case: nothing about this file changed, so
            # there is no pairing work to do.
            continue
        # Identical label tuples cancel; what is left on each side pairs up, in a
        # stable order, into the label changes for this identity.
        old_left = sorted((labels - counterpart).elements(), key=_sort_key)
        new_left = sorted((counterpart - labels).elements(), key=_sort_key)
        for old_tuple, new_tuple in zip(old_left, new_left, strict=False):
            for index in dimensions:
                if old_tuple[index] != new_tuple[index]:
                    changed[index][(old_tuple[index], new_tuple[index])] += 1
        # An identity carried by unequal numbers of copies in the two runs has
        # leftovers with nothing to pair against: those copies genuinely left or
        # arrived, so they belong in lost/gained, not in changed.
        for extra in old_left[len(new_left) :]:
            for index in dimensions:
                lost[index][extra[index]] += 1
        for extra in new_left[len(old_left) :]:
            for index in dimensions:
                gained[index][extra[index]] += 1

    for key, labels in new_labels.items():
        if key in old_labels:
            continue
        for label_tuple, count in labels.items():
            for index in dimensions:
                gained[index][label_tuple[index]] += count

    return {
        field: DimensionDiff(
            dimension=field,
            old=old_counts[index],
            new=new_counts[index],
            lost=lost[index],
            gained=gained[index],
            changed=changed[index],
        )
        for index, field in enumerate(CLASSIFICATION_FIELDS)
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
        "A file is matched on `(dataset, file name)`, and md5 is what is compared.",
        "`md5 changed` counts files that kept their name within a dataset but changed",
        "content — the run diff, by contrast, treats those as two different files.",
        "",
        "| dataset | old | new | unchanged | md5 changed | removed | added |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {escape_md_cell(row.dataset) or '(none)'} | {row.old_total:,} | {row.new_total:,} | "
            f"{row.unchanged:,} | {row.md5_changed:,} | {row.removed:,} | {row.added:,} |"
        )
    unchanged = sum(row.unchanged for row in rows)
    md5_changed = sum(row.md5_changed for row in rows)
    removed = sum(row.removed for row in rows)
    added = sum(row.added for row in rows)
    lines.append(
        f"| **total** | **{sum(row.old_total for row in rows):,}** | **{sum(row.new_total for row in rows):,}** | "
        f"**{unchanged:,}** | **{md5_changed:,}** | **{removed:,}** | **{added:,}** |"
    )
    lines.append("")
    return lines


def render_coverage_section(diffs: dict[str, DimensionDiff], old_total: int, new_total: int) -> list[str]:
    """Markdown for the per-dimension coverage table and its attribution.

    ``classified`` here means the field carries a real value.
    ``docs/anvil-coverage-report.md`` counts differently — its Classified row is
    everything that is not ``not_classified``, so it folds every other status in —
    hence the ``n/a`` columns. ``not_applicable`` is the only other status the
    corpus carries today, so the two reconcile as ``classified`` plus ``n/a``; were
    another status to surface (``conflict``, once #88 promotes it), that report
    would count it too and the identity would no longer hold.
    """
    lines = [
        "## Coverage by dimension",
        "",
        f"Files classified out of {old_total:,} (old) and {new_total:,} (new).",
        "`classified` counts a real value; `n/a` counts `not_applicable`, which the",
        "coverage report folds into its own Classified row along with any other status.",
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

    Every dataset in either run gets a row — including one with nothing classified
    at all (``classified_by_dataset`` keys it regardless) — so a dataset that left
    the catalog reports its old counts against zero.
    """
    old_by_dataset = classified_by_dataset(old_labels)
    new_by_dataset = classified_by_dataset(new_labels)
    lines = [
        "## Per-dataset classified counts",
        "",
        "| dataset | dimension | old | new | delta |",
        "|---|---|---:|---:|---:|",
    ]
    for dataset in sorted(set(old_by_dataset) | set(new_by_dataset)):
        old_counts = old_by_dataset.get(dataset, Counter())
        new_counts = new_by_dataset.get(dataset, Counter())
        for field in CLASSIFICATION_FIELDS:
            old_count, new_count = old_counts[field], new_counts[field]
            lines.append(
                f"| {escape_md_cell(dataset) or '(none)'} | {field} | {old_count:,} | "
                f"{new_count:,} | {new_count - old_count:+,} |"
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
