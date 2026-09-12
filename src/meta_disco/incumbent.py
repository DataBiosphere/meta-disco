"""Diff a run's answer against the incumbent AnVIL publishes today (issue #424).

The AnVIL Explorer publishes `data_modality` and `reference_assembly` as facets on
its file index. Those values are not a second *source* to reconcile with — this
project has exactly one source, inference, and one source has nothing to reconcile
with. They are the **incumbent output**: the answer AnVIL publishes right now, which
a run's own answer can be compared against and a recommendation made about.

So nothing here resolves anything. Inference resolves by tier exactly as it does
without this module, and every file's `value` is what inference concluded. This
reads the `declared` block the pipeline carried into the output (`records.
build_declared`) and reports, per file and per dimension, what each side said and
what should be done about the difference.

The shape survives a second source arriving: sources -> reconcile -> our value ->
diff against the incumbent. The diff stays where it is however many sources feed it.

**Four recommendations, and why there are not five.** `add`, `take_azul` and `none`
are decidable from which side spoke. Whether two speakers *agree* is not: `GRCh38 +
Gencode40` and `GRCh38` are the same assembly and different strings, so splitting
`compare` into matches/disagrees needs the value translation table (#414), which
does not exist yet. Rather than guess at equality, `compare` names the pair and the
report lists every one — 1,055 files across five distinct pairs, which is small
enough to read and is exactly the row set #414 is owed.

**`take_azul` is a recommendation, not an adoption.** Our `value` on those files
stays `not_classified`. Nothing here is merged into the answer; the recommendation
records that we have no opinion and the incumbent should stand.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .models import NOT_CLASSIFIED, field_label
from .output_utils import iter_records
from .records import DECLARED_FIELDS
from .summaries import md_table

# The separator Azul joins a multi-valued facet cell with, used here to render a
# declared value list back into the cell Azul published. Held separately from
# ``azul_manifest._MULTI_VALUE_SEP`` rather than imported, because that module opens a
# `requests` session at import and this is an offline report; the two are pinned
# together by ``test_incumbent.test_the_display_join_matches_the_manifest_reader``,
# which is what actually stops them drifting — a comment would not.
MULTI_VALUE_SEP = " || "

# Azul is silent, this run spoke. Nothing is owed; our value stands.
ADD = "add"
# Azul declares, this run is not_classified. The incumbent should stand — which is a
# recommendation about a value we do not publish, not a change to one we do.
TAKE_AZUL = "take_azul"
# Both spoke. Whether they agree is undecidable without #414's translation table, so
# the pair is named rather than judged.
COMPARE = "compare"
# Neither spoke. The residual backlog.
NONE = "none"

# Report order: the two that need action first, then the two that do not.
RECOMMENDATIONS = (TAKE_AZUL, COMPARE, ADD, NONE)

# A `compare` pair listed file by file rather than only counted. Above this a pair is
# bulk (the two 400+ and 600+ cohorts, one value pair each) and the count is the fact;
# below it the individual files are, and that is where the eight interesting rows live
# — four .bai/.tbi, two intervals_fallback BEDs, two .h5ad.
MAX_NAMED_PER_PAIR = 20


def spoke(label: str | None) -> bool:
    """Whether a run's label counts as this project having said something.

    ``not_classified`` is silence and everything else is speech — including
    ``not_applicable``, which is a positive claim that the dimension does not apply to
    this file, and ``conflict``, which is a positive claim that our own rules disagree.
    Both are opinions the incumbent can be compared against, and treating either as
    silence would file a real disagreement under ``take_azul`` as though we had
    nothing to say. The four ``.bai``/``.tbi`` rows are exactly this case.
    """
    return label is not None and label != NOT_CLASSIFIED


def recommendation(declared_values: list[str] | None, label: str | None) -> str:
    """The recommendation for one file and one dimension. See the module docstring."""
    if declared_values and spoke(label):
        return COMPARE
    if declared_values:
        return TAKE_AZUL
    return ADD if spoke(label) else NONE


@dataclass(frozen=True)
class IncumbentRow:
    """One file, one dimension, both sides' answers, and the recommendation.

    ``file_key`` is the identity :func:`gather` deduplicated on, carried here so that
    counting files from these rows and counting them during the pass cannot disagree.
    Name and dataset are *not* that identity: the corpus admits two distinct files with
    one name in one dataset — ``corpus_diff`` keys on ``(dataset, name, md5)`` and
    deliberately keeps such a pair as a multiset — so counting rows by name would
    collapse a pair the recommendation counts twice.
    """

    file_key: tuple[str, object]
    file_name: str
    dataset_title: str
    slot: str
    azul_values: tuple[str, ...]
    our_value: str | None
    recommendation: str
    in_vocabulary: tuple[str, ...]

    @property
    def azul_cell(self) -> str:
        """The declared values rejoined into the cell Azul published."""
        return MULTI_VALUE_SEP.join(self.azul_values)

    @property
    def vocabulary_standing(self) -> str:
        """``yes`` / ``no`` / ``partial`` — how much of what Azul said we can say."""
        if len(self.in_vocabulary) == len(self.azul_values):
            return "yes"
        return "no" if not self.in_vocabulary else "partial"


@dataclass
class IncumbentReport:
    """Everything the report renders, gathered in one pass over a run."""

    run_dir: Path
    # Rows for files that declared something, in the order the run wrote them.
    rows: list[IncumbentRow] = field(default_factory=list)
    # (dataset_title, slot, recommendation) -> file count, over every file in the run.
    counts: Counter = field(default_factory=Counter)
    # (slot, value) -> file count, over every distinct value the incumbent published.
    declared_values: Counter = field(default_factory=Counter)
    # (slot, value) -> whether the run recorded it as a term in that slot's vocabulary.
    # Read from each record's `declared.in_vocabulary` (contract 7.6), never recomputed:
    # a report describes the run it reads, and once #414 maps a value, a stored "no" and
    # a freshly computed "yes" would disagree about the same stored run.
    value_in_vocab: dict[tuple[str, str], bool] = field(default_factory=dict)
    # The incumbents named by the records' own declared blocks.
    sources: set[str] = field(default_factory=set)
    files: int = 0
    # Files written more than once by the run, counted once here and reported as a
    # caveat. Pre-existing: a tar is also written to auxiliary_classifications.json.
    duplicate_records: int = 0

    @property
    def declared_files(self) -> int:
        """Files carrying a declaration on at least one dimension.

        Counted on the same identity ``gather`` deduplicated on, so this headline and
        the recommendation tables always describe the same set of files.
        """
        return len({row.file_key for row in self.rows})

    def compare_pairs(self) -> dict[tuple[str, str, str | None], list[IncumbentRow]]:
        """``compare`` rows grouped by the (slot, azul cell, our value) they share."""
        pairs: dict[tuple[str, str, str | None], list[IncumbentRow]] = defaultdict(list)
        for row in self.rows:
            if row.recommendation == COMPARE:
                pairs[(row.slot, row.azul_cell, row.our_value)].append(row)
        return dict(sorted(pairs.items(), key=lambda kv: (-len(kv[1]), kv[0][0], kv[0][1])))


def gather(run_dir: Path) -> IncumbentReport:
    """Read a run's output and compare every file against the incumbent.

    One pass. Every file is tallied into ``counts`` — including the ~98% that declared
    nothing, since ``add`` and ``none`` are the bulk of the answer — while ``rows`` is
    built only for files that declared something, which is what the flat report lists.

    A file the run wrote more than once is counted once, keyed by ``(entry_id,
    md5sum)``. That happens today for 115 tar archives, which are written to both
    ``tar_`` and ``auxiliary_classifications.json``; none of them declares anything, so
    the deduplication changes no reported figure and is here so the totals are file
    counts rather than row counts.

    ``entry_id`` is stringified before it is hashed. It is *not* guaranteed to be a
    string: it is not classifier-relevant, so a record whose ``entry_id`` drifted to a
    list or dict still classifies and is still written (``InvalidRecord`` echoes it
    un-coerced), and an unhashable one would otherwise raise here — the same hazard
    ``_run_parallel`` already avoids by not hashing a raw ``file_md5sum``. ``md5sum``
    needs no such treatment: #376 excludes any record without a well-formed one.
    """
    report = IncumbentReport(run_dir=run_dir)
    seen: set[tuple] = set()
    for record in iter_records(run_dir):
        key = (str(record.get("entry_id")), record.get("md5sum"))
        if key in seen:
            report.duplicate_records += 1
            continue
        seen.add(key)
        report.files += 1

        declared = record.get("declared") or {}
        if declared.get("source"):
            report.sources.add(declared["source"])
        in_vocabulary = declared.get("in_vocabulary") or {}
        dataset = str(record.get("dataset_title") or "")

        for slot in DECLARED_FIELDS:
            values = declared.get(slot)
            label = field_label(record, slot)
            rec = recommendation(values, label)
            report.counts[(dataset, slot, rec)] += 1
            if not values:
                continue
            recorded = set(in_vocabulary.get(slot) or ())
            for value in values:
                report.declared_values[(slot, value)] += 1
                report.value_in_vocab[(slot, value)] = value in recorded
            report.rows.append(
                IncumbentRow(
                    file_key=key,
                    file_name=str(record.get("file_name") or ""),
                    dataset_title=dataset,
                    slot=slot,
                    azul_values=tuple(values),
                    our_value=label,
                    recommendation=rec,
                    in_vocabulary=tuple(in_vocabulary.get(slot) or ()),
                )
            )
    return report


TSV_HEADER = ("file_name", "dataset", "slot", "azul_value", "our_value", "recommendation", "azul_in_vocab")


def render_tsv(report: IncumbentReport) -> str:
    """The flat per-file table: one row per declared (file, dimension).

    The shape the retired pipeline's ``classification_results_*.tsv`` had — the
    incumbent beside ours, per file — which the move to per-field JSON lost. Only
    declared files appear: a row for each of the other ~697k files would say that
    neither side declared anything, or that only we did, which the counts already say.
    """
    lines = ["\t".join(TSV_HEADER)]
    for row in report.rows:
        lines.append(
            "\t".join(
                (
                    row.file_name,
                    row.dataset_title,
                    row.slot,
                    row.azul_cell,
                    row.our_value or "",
                    row.recommendation,
                    row.vocabulary_standing,
                )
            )
        )
    return "\n".join(lines) + "\n"


def _counts_table(report: IncumbentReport) -> list[str]:
    """Per dataset and dimension, a file count for each recommendation."""
    datasets = sorted({dataset for dataset, _, _ in report.counts})
    rows = []
    for dataset in datasets:
        for slot in DECLARED_FIELDS:
            cells = [report.counts.get((dataset, slot, rec), 0) for rec in RECOMMENDATIONS]
            # A dataset the incumbent is silent across entirely says nothing this
            # report is about; its files are already in the corpus totals below.
            if not (cells[0] or cells[1]):
                continue
            rows.append([dataset, slot] + [f"{c:,}" for c in cells])
    return md_table(["dataset", "dimension", *RECOMMENDATIONS], rows)


def _totals_table(report: IncumbentReport) -> list[str]:
    """The same counts over the whole corpus, per dimension."""
    rows = []
    for slot in DECLARED_FIELDS:
        cells = [sum(c for (_, s, r), c in report.counts.items() if s == slot and r == rec) for rec in RECOMMENDATIONS]
        rows.append([slot] + [f"{c:,}" for c in cells])
    return md_table(["dimension", *RECOMMENDATIONS], rows)


def _vocabulary_table(report: IncumbentReport) -> list[str]:
    """Every distinct value the incumbent publishes, and whether we can say it.

    The handoff to #414: each `no` row is a translation row that is owed, and its file
    count is what that row would be worth.
    """
    rows = []
    for (slot, value), count in sorted(report.declared_values.items(), key=lambda kv: (-kv[1], kv[0])):
        sayable = report.value_in_vocab.get((slot, value), False)
        rows.append([slot, f"`{value}`", f"{count:,}", "yes" if sayable else "**no**"])
    return md_table(["dimension", "incumbent value", "files", "a term in our vocabulary"], rows)


def _compare_section(report: IncumbentReport) -> list[str]:
    """Every `compare` pair, and the files behind the small ones."""
    lines: list[str] = []
    pairs = report.compare_pairs()
    if not pairs:
        return ["No file has a value on both sides.", ""]

    rows = [
        [slot, f"`{azul}`", f"`{ours or ''}`", f"{len(members):,}"] for (slot, azul, ours), members in pairs.items()
    ]
    lines += md_table(["dimension", "incumbent says", "we say", "files"], rows)
    lines.append("")

    small = {key: members for key, members in pairs.items() if len(members) <= MAX_NAMED_PER_PAIR}
    if small:
        lines.append(f"### Named individually (pairs of {MAX_NAMED_PER_PAIR} files or fewer)")
        lines.append("")
        named = [
            [row.file_name, row.dataset_title, row.slot, f"`{row.our_value}`"]
            for members in small.values()
            for row in sorted(members, key=lambda r: r.file_name)
        ]
        lines += md_table(["file", "dataset", "dimension", "we say"], named)
        lines.append("")
    return lines


def render_report(report: IncumbentReport) -> str:
    """The markdown report. See the module docstring for what each state means."""
    sources = ", ".join(f"`{s}`" for s in sorted(report.sources)) or "unnamed (the input carried no catalog)"
    distinct = len(report.declared_values)
    unsayable = {key for key in report.declared_values if not report.value_in_vocab.get(key, False)}
    distinct_unsayable = len(unsayable)
    files_unsayable = sum(c for key, c in report.declared_values.items() if key in unsayable)

    lines = [
        "# The incumbent, beside ours",
        "",
        f"Run: `{report.run_dir}` · {report.files:,} files · incumbent: {sources}",
        "",
        "What AnVIL publishes today for `data_modality` and `reference_assembly`, compared with what this",
        "run concluded, per file. Nothing here changes a classification: every file's value is what",
        "inference resolved, and `take_azul` is a recommendation that the incumbent should stand on a",
        "file we call `not_classified` — not an adoption of it.",
        "",
        f"**{report.declared_files:,} files carry a declaration**; the rest are the incumbent's silence.",
        "",
        *md_table(
            ["recommendation", "meaning"],
            [
                ["`add`", "the incumbent is silent, we classified — our value is the only one"],
                ["`take_azul`", "the incumbent declares, we are `not_classified` — it should stand"],
                ["`compare`", "both spoke; whether they agree needs the translation table (#414)"],
                ["`none`", "neither spoke — the residual backlog"],
            ],
        ),
        "",
        "## Corpus totals",
        "",
        *_totals_table(report),
        "",
        "## By dataset",
        "",
        "Datasets the incumbent is silent across entirely are omitted.",
        "",
        *_counts_table(report),
        "",
        "## Can we even say it?",
        "",
        f"**{distinct_unsayable} of {distinct} distinct incumbent values are terms our vocabulary does not have**, "
        f"carried by {files_unsayable:,} file declarations.",
        "Every `no` below is a translation row that is owed (#414), and its file count is what it is worth.",
        "Because none of the incumbent's values is a term we know, not one `compare` pair below is a",
        "term-level disagreement — every one of them is an untranslated string.",
        "",
        *_vocabulary_table(report),
        "",
        "## Where both spoke",
        "",
        *_compare_section(report),
    ]
    if report.duplicate_records:
        lines += [
            "---",
            "",
            f"{report.duplicate_records:,} record(s) were written by the run more than once and counted once here",
            "(a tar archive is written to both `tar_` and `auxiliary_classifications.json`). Pre-existing, and",
            "none of them declares anything, so no figure above depends on it.",
            "",
        ]
    return "\n".join(lines)
