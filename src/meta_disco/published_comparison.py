"""Compare a run's inferred values against the ones the repository publishes (#424).

A repository publishes values for some of the dimensions this project infers — AnVIL
serves `data_modality` and `reference_assembly` as facets on its file index. Those
values are not a second *source* to reconcile with: this project has exactly one
source, inference, and one source has nothing to reconcile with. They are the
**published output** — the answer the repository's users see today, which a run's own
answer can be compared against and a recommendation made about.

So nothing here resolves anything. Inference resolves by tier exactly as it does
without this module, and every file's `value` is what inference concluded. This reads
the `published` block the pipeline carried into the output (`records.build_published`)
and reports, per file and per dimension, what each side has and what the repository
should do about the difference.

Deliberately repository-neutral. AnVIL is the only publisher today, but the report is
addressed to whichever repository's data team reads it, so no name appears in the
vocabulary — only in the `source` a run records.

**Four recommendations, and why there are not five.** `add`, `keep` and `none` are
decidable from which side has a value. Whether two values *agree* is not: `GRCh38 +
Gencode40` and `GRCh38` are the same assembly and different strings, so splitting
`review` into agrees/disagrees needs the value mappings (#414), which do not exist
yet. Rather than guess at equality, `review` names the pair and the report lists every
one — 1,055 files across five distinct pairs, small enough to read and exactly the row
set #414 is owed.

**`keep` is a recommendation, not an adoption.** The inferred `value` on those files
stays `not_classified`. Nothing here is merged into the answer; the recommendation
records that this project has no opinion and the published value should stand.
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .models import NOT_CLASSIFIED, field_label
from .output_utils import iter_records
from .records import PUBLISHED_FIELDS
from .summaries import md_table

# The separator the repository joins a multi-valued facet cell with, used here to render
# a published value list back into the cell as published. Held separately from
# ``azul_manifest._MULTI_VALUE_SEP`` rather than imported, because that module is the
# manifest *fetcher* — it imports `requests` at module scope — and this is an offline
# report that should not pull the HTTP client in to read one constant; the two are pinned
# together by ``test_published_comparison.test_the_display_join_matches_the_manifest_reader``,
# which is what actually stops them drifting — a comment would not.
MULTI_VALUE_SEP = " || "


def _code(value: str) -> str:
    """A markdown code span holding ``value``, whatever it contains.

    Published values are transcribed verbatim (contract 7.3), so nothing stops one
    containing a backtick, which would terminate a single-backtick span and spill the
    rest of the value into the table as markup. CommonMark's rule is that a code span
    may be fenced by any run of backticks not appearing in the content, so the fence is
    one longer than the longest run inside; a value starting or ending with a backtick
    additionally needs a space, which the reader strips.

    A pipe needs no handling here: ``md_table`` escapes it, and GFM processes that escape
    when it parses the table row — including inside a code span, which its own spec
    demonstrates. Escaping it a second time here would put a visible backslash in the
    rendered cell, so do not "fix" that.
    """
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if value.startswith("`") or value.endswith("`") else ""
    return f"{fence}{pad}{value}{pad}{fence}"


# The repository publishes nothing; this run inferred a value. Nothing is owed.
ADD = "add"
# The repository publishes a value; this run inferred none. The published value should
# stand — a recommendation about a value we do not publish, not a change to one we do.
KEEP = "keep"
# Both have a value. Whether they agree is undecidable without #414's value mappings,
# so the pair is named rather than judged.
REVIEW = "review"
# Neither has a value. The residual backlog.
NONE = "none"

# Report order. `add` leads because it is the headline for the reader: the values
# this project has and the repository does not.
RECOMMENDATIONS = (ADD, KEEP, REVIEW, NONE)

# A `review` pair listed file by file rather than only counted. Above this a pair is
# bulk (the two 400+ and 600+ cohorts, one value pair each) and the count is the fact;
# below it the individual files are, and that is where the eight interesting rows live
# — four .bai/.tbi, two intervals_fallback BEDs, two .h5ad.
MAX_NAMED_PER_PAIR = 20


def spoke(label: str | None) -> bool:
    """Whether a run's label counts as this project having said something.

    ``not_classified`` is silence and everything else is speech — including
    ``not_applicable``, which is a positive claim that the dimension does not apply to
    this file, and ``conflict``, which is a positive claim that our own rules disagree.
    Both are opinions the published value can be compared against, and treating either as
    silence would file a real disagreement under ``keep`` as though we had
    nothing to say. The four ``.bai``/``.tbi`` rows are exactly this case.
    """
    return label is not None and label != NOT_CLASSIFIED


def recommendation(published_values: list[str] | None, label: str | None) -> str:
    """The recommendation for one file and one dimension. See the module docstring."""
    if published_values and spoke(label):
        return REVIEW
    if published_values:
        return KEEP
    return ADD if spoke(label) else NONE


@dataclass(frozen=True)
class ComparisonRow:
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
    dimension: str
    published_values: tuple[str, ...]
    inferred_value: str | None
    recommendation: str
    in_vocabulary: tuple[str, ...]

    @property
    def published_cell(self) -> str:
        """The published values rejoined into the cell the repository published."""
        return MULTI_VALUE_SEP.join(self.published_values)

    @property
    def vocabulary_standing(self) -> str:
        """``yes`` / ``no`` / ``partial`` — how much of the published value the schema can say."""
        if len(self.in_vocabulary) == len(self.published_values):
            return "yes"
        return "no" if not self.in_vocabulary else "partial"


@dataclass
class ComparisonReport:
    """Everything the report renders, gathered in one pass over a run."""

    run_dir: Path
    # Rows for files with a published value, in the order the run wrote them.
    rows: list[ComparisonRow] = field(default_factory=list)
    # (dataset_title, dimension, recommendation) -> file count, over every file in the run.
    counts: Counter = field(default_factory=Counter)
    # (dimension, value) -> file count, over every distinct value the repository publishes.
    published_value_counts: Counter = field(default_factory=Counter)
    # (dimension, value) -> whether the run recorded it as a term in that dimension's vocabulary.
    # Read from each record's `published.in_vocabulary` (contract 7.6), never recomputed:
    # a report describes the run it reads, and once #414 maps a value, a stored "no" and
    # a freshly computed "yes" would disagree about the same stored run.
    value_in_vocab: dict[tuple[str, str], bool] = field(default_factory=dict)
    # The repositories named by the records' own published blocks.
    sources: set[str] = field(default_factory=set)
    files: int = 0
    # Files written more than once by the run, counted once here and reported as a
    # caveat. Pre-existing: a tar is also written to auxiliary_classifications.json.
    duplicate_records: int = 0

    @property
    def published_files(self) -> int:
        """Files with a published value on at least one dimension.

        Counted on the same identity ``gather`` deduplicated on, so this headline and
        the recommendation tables always describe the same set of files.
        """
        return len({row.file_key for row in self.rows})

    def compare_pairs(self) -> dict[tuple[str, str, str | None], list[ComparisonRow]]:
        """``review`` rows grouped by the (dimension, published cell, inferred value) they share."""
        pairs: dict[tuple[str, str, str | None], list[ComparisonRow]] = defaultdict(list)
        for row in self.rows:
            if row.recommendation == REVIEW:
                pairs[(row.dimension, row.published_cell, row.inferred_value)].append(row)
        return dict(sorted(pairs.items(), key=lambda kv: (-len(kv[1]), kv[0][0], kv[0][1])))


def gather(run_dir: Path) -> ComparisonReport:
    """Read a run's output and compare every file against the published values.

    One pass. Every file is tallied into ``counts`` — including the ~98% the repository
    publishes nothing for, since ``add`` and ``none`` are the bulk of the answer — while ``rows`` is
    built only for files with a published value, which is what the flat report lists.

    A file the run wrote more than once is counted once, keyed by ``(entry_id,
    md5sum)``. That happens today for 115 tar archives, which are written to both
    ``tar_`` and ``auxiliary_classifications.json``, and it is here so every total is a
    file count rather than a row count. Being precise about what it moves: none of the
    115 has a published value, so the published-value figures and the ``keep`` /
    ``review`` counts are identical either way — but ``counts`` is tallied for *every*
    file, so the ``add`` and ``none`` totals are 115 lower than the row count, which is
    the correct answer and not the same as being unaffected.

    ``entry_id`` is stringified before it is hashed. It is *not* guaranteed to be a
    string: it is not classifier-relevant, so a record whose ``entry_id`` drifted to a
    list or dict still classifies and is still written (``InvalidRecord`` echoes it
    un-coerced), and an unhashable one would otherwise raise here — the same hazard
    ``ClassifyPipeline.run``'s ``skip_cached`` filter already avoids by not hashing a raw
    ``file_md5sum`` against a set. ``md5sum`` needs no such treatment here: #376 excludes
    any record without a well-formed one.
    """
    report = ComparisonReport(run_dir=run_dir)
    seen: set[tuple] = set()
    for record in iter_records(run_dir):
        key = (str(record.get("entry_id")), record.get("md5sum"))
        if key in seen:
            report.duplicate_records += 1
            continue
        seen.add(key)
        report.files += 1

        published = record.get("published") or {}
        if published.get("source"):
            report.sources.add(published["source"])
        in_vocabulary = published.get("in_vocabulary") or {}
        dataset = str(record.get("dataset_title") or "")

        for dimension in PUBLISHED_FIELDS:
            values = published.get(dimension)
            label = field_label(record, dimension)
            rec = recommendation(values, label)
            report.counts[(dataset, dimension, rec)] += 1
            if not values:
                continue
            recorded = set(in_vocabulary.get(dimension) or ())
            for value in values:
                report.published_value_counts[(dimension, value)] += 1
                report.value_in_vocab[(dimension, value)] = value in recorded
            report.rows.append(
                ComparisonRow(
                    file_key=key,
                    file_name=str(record.get("file_name") or ""),
                    dataset_title=dataset,
                    dimension=dimension,
                    published_values=tuple(values),
                    inferred_value=label,
                    recommendation=rec,
                    in_vocabulary=tuple(in_vocabulary.get(dimension) or ()),
                )
            )
    return report


TSV_HEADER = (
    "entry_id",
    "md5sum",
    "file_name",
    "dataset",
    "dimension",
    "published_value",
    "inferred_value",
    "recommendation",
    "published_in_vocabulary",
)


def render_tsv(report: ComparisonReport) -> str:
    """The flat per-file table: one row per published (file, dimension).

    The shape the retired pipeline's ``classification_results_*.tsv`` had — the
    published beside inferred, per file — which the move to per-field JSON lost. Only
    files with a published value appear: a row for each of the other ~697k would say that
    neither side has a value, or that only inference does, which the counts already say.

    Led by the identity ``gather`` deduplicated on, because name and dataset do not
    identify a file: 226,416 names in this corpus appear on more than one record, and
    ``corpus_diff`` keys on ``(dataset, name, md5)`` for that reason. Without these two
    columns a reader could not tell which file a recommendation applies to, nor join a
    row back to the catalog (``entry_id``) or to a corpus diff (``md5sum``).
    """
    buffer = io.StringIO()
    # A real writer, not `"\t".join`: published values are transcribed verbatim (7.3) and
    # nothing constrains them to exclude a tab or a newline, so one such value would add
    # a column or split a row and the file would stop being parseable. No value in the
    # corpus contains one today, which is exactly when it is cheap to stop relying on
    # that. `QUOTE_MINIMAL` leaves every current row byte-identical to the joined form.
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(TSV_HEADER)
    for row in report.rows:
        entry_id, md5sum = row.file_key
        writer.writerow(
            (
                entry_id,
                str(md5sum),
                row.file_name,
                row.dataset_title,
                row.dimension,
                row.published_cell,
                row.inferred_value or "",
                row.recommendation,
                row.vocabulary_standing,
            )
        )
    return buffer.getvalue()


def _counts_table(report: ComparisonReport) -> list[str]:
    """Per dataset and dimension, a file count for each recommendation."""
    datasets = sorted({dataset for dataset, _, _ in report.counts})
    rows = []
    for dataset in datasets:
        for dimension in PUBLISHED_FIELDS:
            counts = {rec: report.counts.get((dataset, dimension, rec), 0) for rec in RECOMMENDATIONS}
            # A dataset the repository publishes nothing for says nothing this report is
            # about; its files are already in the totals above. Keyed by recommendation
            # rather than by position: RECOMMENDATIONS is a presentation order, and
            # reading `add` out of it by index is how this filter once let every dataset
            # through when `add` was moved to the front.
            if not (counts[KEEP] or counts[REVIEW]):
                continue
            rows.append([dataset, dimension] + [f"{counts[rec]:,}" for rec in RECOMMENDATIONS])
    return md_table(["dataset", "dimension", *RECOMMENDATIONS], rows)


def _totals_table(report: ComparisonReport) -> list[str]:
    """The same counts over the whole corpus, per dimension."""
    rows = []
    for dimension in PUBLISHED_FIELDS:
        cells = [
            sum(c for (_, s, r), c in report.counts.items() if s == dimension and r == rec) for rec in RECOMMENDATIONS
        ]
        rows.append([dimension] + [f"{c:,}" for c in cells])
    return md_table(["dimension", *RECOMMENDATIONS], rows)


def _vocabulary_table(report: ComparisonReport) -> list[str]:
    """Every distinct value the repository publishes, and whether the schema can say it.

    The handoff to #414: each `no` row is a translation row that is owed, and its file
    count is what that row would be worth.
    """
    rows = []
    for (dimension, value), count in sorted(report.published_value_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        sayable = report.value_in_vocab.get((dimension, value), False)
        rows.append([dimension, _code(value), f"{count:,}", "yes" if sayable else "**no**"])
    return md_table(["dimension", "published value", "files", "in vocabulary"], rows)


def _compare_section(report: ComparisonReport) -> list[str]:
    """Every `review` pair, and the files behind the small ones."""
    lines: list[str] = []
    pairs = report.compare_pairs()
    if not pairs:
        return ["No file has a value on both sides.", ""]

    rows = [
        [dimension, _code(published), _code(inferred or ""), f"{len(members):,}"]
        for (dimension, published, inferred), members in pairs.items()
    ]
    lines += md_table(["dimension", "published", "inferred", "files"], rows)
    lines.append("")

    small = {key: members for key, members in pairs.items() if len(members) <= MAX_NAMED_PER_PAIR}
    if small:
        lines.append("### The files behind the small pairs")
        lines.append("")
        lines.append(f"Listed where a pair covers {MAX_NAMED_PER_PAIR} files or fewer, which is where an individual")
        lines.append("file is the fact rather than the count.")
        lines.append("")
        named = [
            [row.file_name, row.dataset_title, row.dimension, _code(str(row.inferred_value))]
            for members in small.values()
            for row in sorted(members, key=lambda r: r.file_name)
        ]
        lines += md_table(["file", "dataset", "dimension", "inferred"], named)
        lines.append("")
    return lines


def render_report(report: ComparisonReport) -> str:
    """The markdown report. See the module docstring for what each state means."""
    # Read off the published blocks, so a run in which no file has a published value
    # names no repository even when its input envelope did. Say that rather than blaming
    # the input: the two are different facts and only one is visible from here.
    sources = ", ".join(f"`{s}`" for s in sorted(report.sources)) or "not named by any file in this run"
    distinct = len(report.published_value_counts)
    unsayable = {key for key in report.published_value_counts if not report.value_in_vocab.get(key, False)}
    distinct_unsayable = len(unsayable)
    files_unsayable = sum(c for key, c in report.published_value_counts.items() if key in unsayable)

    lines = [
        "# Published values compared with inferred",
        "",
        f"Repository: {sources} · run `{report.run_dir.name}` · {report.files:,} files",
        "",
        f"**{report.published_files:,} files have a published value**, across "
        f"{len(report.rows):,} file/dimension rows. For every other file the",
        "repository publishes nothing for these dimensions.",
        "",
        "Nothing here changes a classification: each file's inferred value is what the rule engine",
        "resolved. A `keep` recommends that the published value should stand — it is not an adoption",
        "of it, and no inferred value is altered by this report.",
        "",
        *md_table(
            ["recommendation", "meaning"],
            [
                ["`add`", "nothing published; meta-disco inferred a value"],
                ["`keep`", "a value is published; meta-disco inferred none"],
                ["`review`", "both have a value"],
                ["`none`", "neither has a value"],
            ],
        ),
        "",
        "## Totals",
        "",
        *_totals_table(report),
        "",
        "## By dataset",
        "",
        "Datasets for which the repository publishes nothing are omitted.",
        "",
        *_counts_table(report),
        "",
        "## Vocabulary coverage",
        "",
        f"**{distinct_unsayable} of {distinct} distinct published values have no term in the schema "
        f"vocabulary**, carried by {files_unsayable:,} published values.",
        "Counted per value, not per row, so a cell publishing two values contributes two — which is the",
        f"right denominator for a mapping table. There are {len(report.rows):,} file/dimension rows.",
        f"Each of the {distinct_unsayable} is a value mapping that is owed (#414); its row count is what",
        "that mapping is worth.",
        "",
        *_vocabulary_table(report),
        "",
        "## Rows needing review",
        "",
        "Both sides have a value. Whether they agree cannot be decided until the value mappings exist",
        "(#414), so each pair is named rather than judged.",
        "",
        # Derived, not asserted. Every other number in this report is computed from the
        # run; this sentence used to claim outright that no published value is in
        # vocabulary, which is true of today's corpus and would silently contradict the
        # vocabulary table above the day #414 lands a term or a repository publishes a
        # bare `GRCh38`.
        *(
            [
                "None of the published values above is a term the schema knows, so every pair below is an",
                "unmapped string rather than a disagreement about meaning.",
                "",
            ]
            if distinct_unsayable == distinct
            else [
                f"{distinct - distinct_unsayable} of {distinct} published values *are* terms the schema knows, so a",
                "pair below may be a real disagreement rather than an unmapped string. Check the vocabulary",
                "table above before reading one as either.",
                "",
            ]
        ),
        *_compare_section(report),
    ]
    if report.duplicate_records:
        lines += [
            "---",
            "",
            f"{report.duplicate_records:,} record(s) were written by the run more than once and counted once here",
            "(a tar archive is written to both `tar_` and `auxiliary_classifications.json`). Pre-existing, and",
            "none has a published value, so no figure above depends on it.",
            "",
        ]
    return "\n".join(lines)
