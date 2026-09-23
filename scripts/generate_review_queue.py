#!/usr/bin/env python3
"""Publish the translation review queue as a report (#524).

Reads the current evidence files and the value translation table, the way
``make review-queue`` always has (``meta_disco.value_map.review_queue``), and writes
``docs/review-queue-report.md`` and the static page ``docs/review-queue.html`` (from
``docs/review-queue-template.html``): every source value no authored row reads yet,
grouped by the kind of source it came from, the catalog's published columns or the
submitter tables. The markdown is not named ``review-queue.md``: Jekyll would render it to
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
from pathlib import Path

from meta_disco.source_evidence import DEFAULT_SOURCE_EVIDENCE_ROOT
from meta_disco.value_map import (
    QUEUE_COLUMNS,
    QueueEntry,
    default_value_map_resource,
    load_value_map,
    queue_groups,
    queue_intro,
    queue_summary,
    render_queue,
    review_queue,
)

PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE = PROJECT_ROOT / "docs" / "review-queue-template.html"
PLACEHOLDER = "QUEUE_PLACEHOLDER"


def render_html(
    entries: list[QueueEntry], evidence_root: Path, template: str, datasets: list[str] | None = None
) -> str:
    """The queue as a static page: ``template`` with its placeholder replaced by the groups' tables.

    The same groups and columns as the markdown (``value_map.render_queue``). Every value
    passes through ``html.escape`` here, so none renders as markup; no script runs on the page.
    """
    esc = html.escape
    parts = [f'<p class="note">{esc(queue_intro(entries, evidence_root, datasets))}</p>']
    head = "".join(f"<th>{esc(c.header)}</th>" for c in QUEUE_COLUMNS)
    for label, description, group in queue_groups(entries):
        parts.append(f"<h2>{esc(label)}: {esc(description)}</h2>")
        if not group:
            parts.append("<p>No unreviewed values.</p>")
            continue
        rows = "".join(
            "<tr>" + "".join(f'<td class="{c.kind}">{esc(c.cell(e))}</td>' for c in QUEUE_COLUMNS) + "</tr>"
            for e in group
        )
        parts.append(f'<div class="scroll"><table><tr>{head}</tr>{rows}</table></div>')
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
    entries = review_queue(args.evidence_root, load_value_map(table_path), args.dataset)
    args.markdown.write_text(render_queue(entries, args.evidence_root, args.dataset))
    args.html.write_text(render_html(entries, args.evidence_root, TEMPLATE.read_text(), args.dataset))
    print(f"Review queue -> {args.markdown}, {args.html}")
    print("\n".join(queue_summary(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
