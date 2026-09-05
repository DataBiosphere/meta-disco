"""One answer to "what did this run not classify, and why?" (#376).

Before this, the answer was scattered: a ``validation_failed`` tally in each output
file's metadata block, a ``content_unreadable`` tally beside it, and the actual reason
buried in per-record evidence — with no list a person could read. This module gathers
every unprocessable file in a run under one taxonomy and renders it as markdown.

Three reasons, as things stand:

======================  ==================================  =========================
reason                  row in a ``*_classifications.json``  where this reads it from
======================  ==================================  =========================
no checksum             no — excluded (#376)                ``excluded_files.json``
input-contract          yes, all dimensions not_classified  evidence ``rule_id``
content unreadable      yes, all dimensions not_classified  evidence ``rule_id``
======================  ==================================  =========================

The excluded files are listed individually and the other two only counted per dataset
with a bounded sample. That asymmetry is deliberate: an excluded file exists in no
other output, so this report is the only place it is ever named, while a
``content_unreadable`` category can run to thousands and is already row-by-row in the
run's own output.

Both row-backed reasons are detected by the ``rule_id`` their producer stamps on the
evidence — ``metadata_schema.VALIDATION_RULE_ID`` and
``header_classifier.FETCH_FAILED_RULE_ID`` — not by the shape of the classifications
they produce. The two produce the *same* all-not_classified shape, so shape could not
tell them apart, and a third producer of that shape would be misattributed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .exclusions import ExcludedFile, read_excluded
from .header_classifier import FETCH_FAILED_RULE_ID
from .metadata_schema import VALIDATION_RULE_ID
from .models import CLASSIFICATION_FIELDS, field_evidence
from .output_utils import iter_records
from .records import coerce_identity
from .summaries import escape_md_cell

# Datasets and examples are capped so a category running to thousands of files stays a
# readable report. The excluded category is exempt — it is listed in full, because it
# is named nowhere else.
DEFAULT_EXAMPLES = 5

# Fallback label for a record whose dataset_title is absent or empty. Both row-backed
# reasons can carry one (the HPRC source has no dataset_title at all), and grouping
# them under a named bucket keeps them visible instead of collapsing into "".
UNKNOWN_DATASET = "(no dataset_title)"


@dataclass(frozen=True)
class Reason:
    """One class of unprocessable file: how it is named, and what it means.

    ``row_exists`` is the fact a reader most needs and cannot infer: whether the run's
    classification output still holds a row for these files, or whether this report is
    the only place they appear.
    """

    key: str
    title: str
    explanation: str
    row_exists: str


NO_CHECKSUM = Reason(
    key="no_checksum",
    title="No usable checksum (excluded)",
    explanation=(
        "The record carries no well-formed `file_md5sum`, so it can be neither fetched "
        "(the content URL is built from the md5) nor cached (the evidence cache is keyed "
        "by md5). It is excluded from classification rather than written as a row with no "
        "usable identity."
    ),
    row_exists="**No row exists anywhere else** — this listing is the only record of these files.",
)

CONTRACT_VIOLATION = Reason(
    key="contract_violation",
    title="Input-contract violation",
    explanation=(
        "The record violates the input contract on a field the classifier reads "
        "(`file_size`, `file_format`, `file_name`), so it is never fetched. Its provenance "
        "is untrusted wholesale, so every dimension is marked `not_classified`."
    ),
    row_exists="A row exists in the run's output, with the violation as each dimension's evidence.",
)

CONTENT_UNREADABLE = Reason(
    key="content_unreadable",
    title="Content unreadable",
    explanation=(
        "The record passed the contract, but its content could not be read — a 404 from the "
        "mirror, a DNS or connection failure, a timeout. Nothing is asserted about a file we "
        "could not read, not even what the filename alone would support."
    ),
    row_exists="A row exists in the run's output, with the fetch failure as each dimension's evidence.",
)

# The reasons whose files still have a row in the run's classification output, and are
# therefore read from those rows rather than from the exclusions file. Named separately
# from REASONS so the loops that only make sense for them iterate a list that says so,
# instead of iterating REASONS and skipping the odd member out.
ROW_REASONS = (CONTRACT_VIOLATION, CONTENT_UNREADABLE)

# Report order: excluded first, since it is the only category with no row elsewhere.
REASONS = (NO_CHECKSUM, *ROW_REASONS)

# The evidence rule_id each row-backed reason is recognized by.
_ROW_REASON_RULE_IDS = {
    VALIDATION_RULE_ID: CONTRACT_VIOLATION,
    FETCH_FAILED_RULE_ID: CONTENT_UNREADABLE,
}


def _dataset_label(dataset_title) -> str:
    """The bucket a record's ``dataset_title`` is grouped under.

    One definition so the excluded listing and the row-backed tables name the untitled
    bucket identically — they are read side by side in one report.

    Only an absent (``None``) or empty title falls into the untitled bucket. A present
    but drifted one — ``0``, ``False`` — keeps its own bucket via
    ``records.coerce_identity``, the same rule the output rows echo identities by: a
    ``dataset_title`` of ``0`` is drift this report exists to surface, and folding it in
    with the genuinely untitled would hide it.
    """
    return coerce_identity(dataset_title) or UNKNOWN_DATASET


def _section_header(reason: Reason) -> list[str]:
    """The lines every reason's section opens with: title, what it means, whether a row
    for it exists elsewhere."""
    return [f"### {reason.title}", "", reason.explanation, "", reason.row_exists, ""]


@dataclass
class RowGroup:
    """Per-dataset tally of one row-backed reason, with a bounded sample of filenames."""

    dataset: str
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def add(self, file_name: str, max_examples: int) -> None:
        self.count += 1
        if len(self.examples) < max_examples:
            self.examples.append(file_name)


@dataclass
class RunUnprocessable:
    """Everything a run could not classify, grouped by reason.

    ``excluded`` holds the :class:`ExcludedFile` rows that were recoverable; ``rows``
    maps a row-backed reason key to its per-dataset groups.

    ``excluded_count`` is the number of files excluded, or ``None`` when that is not
    known — carried straight from :attr:`ExcludedIndex.count`, which is the one place it
    is derived, rather than recomputed here. It is ``None`` both for a run predating #376
    (no exclusions file) and for one whose file could not be read; ``exclusions_present``
    separates those two reasons so the report can say which unknown it is.
    """

    run_dir: Path
    excluded: list[ExcludedFile]
    exclusions_present: bool
    excluded_count: int | None
    total_input: int
    rows: dict[str, dict[str, RowGroup]]
    total_records: int


def _reason_for(record: dict) -> Reason | None:
    """The row-backed reason a classification record represents, or None if it is fine.

    Reads the evidence ``rule_id`` on the classification fields, through
    ``models.field_evidence`` — the same layout normalization every other reader of a
    classification record uses, so this report sees a record's evidence wherever the
    other readers would. Both producers stamp the same rule_id on every one of the five
    dimensions, so the first field carrying a recognized id settles it; scanning them
    all rather than assuming a fixed field keeps this correct if a producer ever marks
    a subset.
    """
    for dimension in CLASSIFICATION_FIELDS:
        for item in field_evidence(record, dimension):
            if isinstance(item, dict):
                rule_id = item.get("rule_id")
                if isinstance(rule_id, str) and rule_id in _ROW_REASON_RULE_IDS:
                    return _ROW_REASON_RULE_IDS[rule_id]
    return None


def reason_total(data: RunUnprocessable, reason: Reason) -> int:
    """How many files ``data`` holds under one row-backed reason.

    The single place the per-dataset groups are summed, so the report body, the summary
    table and the CLI's stdout line cannot disagree — and so a caller names a
    :class:`Reason` rather than repeating its ``key`` as a string literal.

    Raises ValueError for :data:`NO_CHECKSUM`, whose files are not row-backed and are
    counted from ``data.excluded`` instead. Returning ``0`` for it would be a wrong
    answer with no signal, since its key is never in ``data.rows``.
    """
    if reason not in ROW_REASONS:
        raise ValueError(f"{reason.key} is not row-backed; its count comes from data.excluded")
    return sum(group.count for group in (data.rows.get(reason.key) or {}).values())


def gather(run_dir: Path, *, max_examples: int = DEFAULT_EXAMPLES) -> RunUnprocessable:
    """Collect every unprocessable file in ``run_dir``, from both sources.

    The excluded files come from the run's ``excluded_files.json``; the two row-backed
    reasons come from a single pass over the run's classification records via
    ``output_utils.iter_records``, so this reads the same set of output files the
    coverage and consistency readers do. It is *more* tolerant of shape than the
    coverage loader, which iterates whatever it finds and raises: ``iter_records``
    yields nothing from a file whose record list is not a list.

    Raises FileNotFoundError if the run directory does not exist — an empty report over
    a mistyped path would otherwise read as a run with nothing to report.
    """
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    index = read_excluded(run_dir)
    rows: dict[str, dict[str, RowGroup]] = {reason.key: {} for reason in ROW_REASONS}
    total_records = 0
    for record in iter_records(run_dir):
        total_records += 1
        reason = _reason_for(record)
        if reason is None:
            continue
        dataset = _dataset_label(record.get("dataset_title"))
        group = rows[reason.key].setdefault(dataset, RowGroup(dataset=dataset))
        group.add(str(record.get("file_name") or ""), max_examples)

    return RunUnprocessable(
        run_dir=run_dir,
        excluded=index.files,
        exclusions_present=index.present,
        excluded_count=index.count,
        total_input=index.total_input,
        rows=rows,
        total_records=total_records,
    )


def _render_excluded(data: RunUnprocessable) -> list[str]:
    """Render the excluded category: every file named, grouped by dataset."""
    lines = _section_header(NO_CHECKSUM)
    if data.excluded_count is None:
        why = (
            "holds no `excluded_files.json`. Every producer has written that file since #376, "
            "so this is a run directory from before then."
            if not data.exclusions_present
            else "holds an `excluded_files.json` that could not be read, so no count from it "
            "can be trusted. Any rows that were still recoverable are listed below."
        )
        lines += [
            f"**Unknown** — this run directory {why} Re-classify the corpus to get an answer.",
            "",
        ]
        lines += _excluded_tables(data.excluded) if data.excluded else []
        return lines
    if not data.excluded:
        # Reached only when the count is known (the unknown cases returned above), so it
        # is stated even when it is zero — an empty input is a real answer, not a missing
        # one.
        lines += [f"None in this run ({data.total_input:,} input records checked).", ""]
        return lines

    lines += _excluded_tables(data.excluded)
    return lines


def _excluded_tables(excluded: list[ExcludedFile]) -> list[str]:
    """Every excluded file named, grouped by dataset, one table per dataset.

    Split out because it is rendered both for a run whose exclusions are known and for
    one whose file was damaged — in the second case the rows that survived are still
    worth naming, since no other output holds them.
    """
    by_dataset: dict[str, list[ExcludedFile]] = defaultdict(list)
    for excluded_file in excluded:
        by_dataset[_dataset_label(excluded_file.dataset_title)].append(excluded_file)

    lines = [f"**{len(excluded):,} file(s)** across {len(by_dataset):,} dataset(s), listed in full.", ""]
    for dataset in sorted(by_dataset):
        files = by_dataset[dataset]
        lines += [f"#### {escape_md_cell(dataset)} — {len(files):,} file(s)", ""]
        lines += ["| file_name | entry_id | file_id | file_size | drs_uri |", "|---|---|---|---|---|"]
        for f in sorted(files, key=lambda x: x.file_name):
            lines.append(
                "| {} | {} | {} | {} | {} |".format(
                    escape_md_cell(f.file_name) or "—",
                    escape_md_cell(str(f.entry_id)) if f.entry_id is not None else "—",
                    escape_md_cell(str(f.file_id)) if f.file_id is not None else "—",
                    f"{f.file_size:,}" if isinstance(f.file_size, int) else "—",
                    escape_md_cell(str(f.drs_uri)) if f.drs_uri is not None else "—",
                )
            )
        lines.append("")
    return lines


def _render_rows(data: RunUnprocessable, reason: Reason, max_examples: int) -> list[str]:
    """Render one row-backed category: per-dataset counts with a bounded sample."""
    lines = _section_header(reason)
    groups = data.rows.get(reason.key) or {}
    total = reason_total(data, reason)
    if not total:
        lines += [f"None in this run ({data.total_records:,} classification records read).", ""]
        return lines

    lines += [
        f"**{total:,} file(s)** across {len(groups):,} dataset(s), "
        f"counted per dataset with up to {max_examples} example(s) each.",
        "",
        "| dataset | files | examples |",
        "|---|---:|---|",
    ]
    for group in sorted(groups.values(), key=lambda g: (-g.count, g.dataset)):
        examples = ", ".join(f"`{escape_md_cell(name)}`" for name in group.examples)
        more = group.count - len(group.examples)
        if more > 0:
            examples += f" … (+{more:,} more)"
        lines.append(f"| {escape_md_cell(group.dataset)} | {group.count:,} | {examples} |")
    lines.append("")
    return lines


def render_report(data: RunUnprocessable, *, max_examples: int = DEFAULT_EXAMPLES) -> str:
    """Render the full markdown report for one run.

    Every reason gets a section whether or not it has files, so a category that is empty
    says so in words rather than showing an empty table — an absent section would read
    as "not checked".
    """
    # A run with no exclusions file has an unknown excluded count, not a zero one. It is
    # rendered as "?" and left out of the total, so the summary cannot contradict the
    # section below it — which says plainly that the answer is unknown.
    excluded_count = data.excluded_count
    row_counts = {r.key: reason_total(data, r) for r in ROW_REASONS}
    counts: dict[str, str] = {
        NO_CHECKSUM.key: "?" if excluded_count is None else f"{excluded_count:,}",
        **{key: f"{value:,}" for key, value in row_counts.items()},
    }
    grand_total = (excluded_count or 0) + sum(row_counts.values())
    total_cell = f"**{grand_total:,}+**" if excluded_count is None else f"**{grand_total:,}**"

    lines = [
        "# Unprocessable files",
        "",
        f"What run `{data.run_dir}` could not classify, and why (#376).",
        "",
        "## Summary",
        "",
        "| reason | files | row elsewhere? |",
        "|---|---:|---|",
    ]
    for reason in REASONS:
        has_row = "yes" if reason in ROW_REASONS else "no — excluded"
        lines.append(f"| {reason.title} | {counts[reason.key]} | {has_row} |")
    lines += [
        f"| **Total** | {total_cell} | |",
        "",
        f"Read from {data.total_records:,} classification record(s) in the run"
        # Same distinction as the excluded section: the input count is known exactly when
        # the run recorded its exclusions, including when that count is zero.
        + (f", against {data.total_input:,} input record(s)." if data.excluded_count is not None else "."),
        "",
        "## By reason",
        "",
    ]
    lines += _render_excluded(data)
    for reason in ROW_REASONS:
        lines += _render_rows(data, reason, max_examples)
    return "\n".join(lines).rstrip() + "\n"
