#!/usr/bin/env python3
"""Publish the translation review queue as a report (#524).

Reads the current evidence files and the value translation table, the way
``make review-queue`` always has (``meta_disco.value_map.review_queue``), and writes
``docs/review-queue-report.md`` and the static page ``docs/review-queue.html`` (from
``docs/review-queue-template.html``): every source value no authored row reads yet,
grouped by the kind of source it came from, the catalog's published columns or the
submitter tables; and below it every authored translation row with what it declares and
how many files it matched. The markdown is not named ``review-queue.md``: Jekyll would render it to
``review-queue.html``, the static page's path, as the other reports' ``-report.md`` /
``-dashboard.html`` names avoid.

Usage:
    python scripts/generate_review_queue.py
    python scripts/generate_review_queue.py --dataset AnVIL_IGVF_Mouse_R1
"""

from __future__ import annotations

import argparse
import html
import sys
from collections.abc import Iterable
from pathlib import Path

from meta_disco.source_evidence import DEFAULT_SOURCE_EVIDENCE_ROOT
from meta_disco.value_map import (
    MAPPING_COLUMNS,
    MAPPINGS_HEADING,
    MAPPINGS_INTRO,
    QUEUE_COLUMNS,
    MappingLine,
    QueueEntry,
    by_slot,
    default_value_map_resource,
    load_value_map,
    queue_groups,
    queue_intro,
    queue_summary,
    render_queue,
    review,
)

PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE = PROJECT_ROOT / "docs" / "review-queue-template.html"
PLACEHOLDER = "QUEUE_PLACEHOLDER"


def _table(columns, items) -> str:
    esc = html.escape
    head = "".join(f"<th>{esc(c.header)}</th>" for c in columns)
    rows = "".join(
        "<tr>" + "".join(f'<td class="{c.kind}">{esc(c.cell(i))}</td>' for c in columns) + "</tr>" for i in items
    )
    return f'<div class="scroll"><table><tr>{head}</tr>{rows}</table></div>'


def render_html(
    entries: list[QueueEntry],
    evidence_root: Path,
    template: str,
    datasets: list[str] | None = None,
    mappings: list[MappingLine] | None = None,
    read: Iterable[str] = (),
) -> str:
    """The queue as a static page: ``template`` with its placeholder replaced by the groups' tables.

    The same groups, columns and mappings section as the markdown (``value_map.render_queue``). Every value
    passes through ``html.escape`` here, so none renders as markup; no script runs on the page.
    """
    esc = html.escape
    parts = [f'<p class="note">{esc(queue_intro(entries, evidence_root, datasets))}</p>']
    for label, description, group in queue_groups(entries, read):
        parts.append(f"<h2>{esc(label)}: {esc(description)}</h2>")
        if not group:
            parts.append("<p>No unreviewed values.</p>")
        for slot, entries_in_slot in by_slot(group, lambda e: e.slot):
            parts += [f"<h3>{esc(slot)}</h3>", _table(QUEUE_COLUMNS, entries_in_slot)]
    if mappings is not None:
        parts += [f"<h2>{esc(MAPPINGS_HEADING)}</h2>", f'<p class="note">{esc(MAPPINGS_INTRO)}</p>']
        if not mappings:
            parts.append("<p>No authored rules.</p>")
        for slot, rules in by_slot(mappings, lambda m: m.row.slot):
            parts += [f"<h3>{esc(slot)}</h3>", _table(MAPPING_COLUMNS, rules)]
    return template.replace(PLACEHOLDER, "\n".join(parts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish the translation review queue (#524)")
    parser.add_argument("--table", type=Path, default=None, help="Table file (default: the bundled value_map.yaml)")
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_SOURCE_EVIDENCE_ROOT)
    parser.add_argument("--dataset", action="append", help="Only this dataset's evidence (repeatable)")
    parser.add_argument("--markdown", type=Path, default=PROJECT_ROOT / "docs" / "review-queue-report.md")
    parser.add_argument("--html", type=Path, default=PROJECT_ROOT / "docs" / "review-queue.html")
    args = parser.parse_args(argv)
    table_path = args.table if args.table is not None else Path(str(default_value_map_resource()))
    found = review(args.evidence_root, load_value_map(table_path), args.dataset)
    entries = found.queue
    args.markdown.write_text(
        render_queue(entries, args.evidence_root, args.dataset, found.mappings, found.source_types)
    )
    page = render_html(
        entries, args.evidence_root, TEMPLATE.read_text(), args.dataset, found.mappings, found.source_types
    )
    args.html.write_text(page)
    print(f"Review queue -> {args.markdown}, {args.html}")
    print("\n".join(queue_summary(entries, found.source_types)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
