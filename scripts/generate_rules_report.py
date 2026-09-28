#!/usr/bin/env python3
"""List every rule that classifies a file, with how often each fired in a run (#572).

Three kinds of rule, each read from where it is declared:

- **yaml**: ``rules/unified_rules.yaml``. Its ``when`` and ``then`` are copied from the
  file's own text, sliced at each node's position, so they read exactly as authored,
  unless they use a YAML alias: then the value it stands for is written out, and the
  report says which alias it expanded. Its ``rationale`` is the loaded string.
- **code**: ``meta_disco.code_rules.CODE_RULES``, the rules written in Python.
- **mapping**: ``rules/value_map.yaml``, the translation rows reconcile applies to a
  source's values. Its ``match`` and ``declares`` are sliced the same way, its ``reason``
  is the loaded string.

Each rule's **basis** is what it reads to reach its answer (``code_rules.BASES``). A
YAML rule's is worked out from its ``when`` keys by :data:`WHEN_BASIS`, the most specific
key deciding: a header condition makes it ``content``, else a ``dataset_pattern``
``dataset``, else a ``filename_pattern`` ``file_name``, else an extension or format
condition ``extension``. A code rule declares its own, and a translation row is always
``mapping``. A ``when`` key missing from ``WHEN_BASIS`` fails the report, rather than
going unclassified.

The counts come from one streamed pass over a reconciled run (``iter_reconciled_records``).
For each claim carrying a ``rule_id``, per rule:

- **claims**, and **files** (the records it appeared on, each counted once, overall and
  per dataset).
- **won**: the files where what it declares is the slot's answer, or a broader term of it
  in the dimension's ``is_a`` tree. A rule of ours is held to the slot's ``inferred``
  answer, which is what inference concluded; a translation row competes in reconcile, so
  it is held to the slot's resolved answer. A claim that declares no answer
  (``not_classified``, or a copied ``conflict``) is not counted at all.
- For a translation row, its claims by ``source_type``, since one row serves every
  source whose value it matches: a submitter table (``repository_metadata``) and the
  published columns (``published_value``) among them.

Markers are counted in a table of their own: the ``code_rules.MARKERS`` a producer writes
as a ``rule_id``, and the engine's two placeholders written as ``marker``. An id or marker
the run carries and nothing declares (a rule retired since the run, say) is listed rather
than dropped.

Writes ``docs/rules-report.md`` and ``docs/rules-dashboard.html`` (from
``docs/rules-dashboard-template.html``).

Usage:
    python scripts/generate_rules_report.py
    python scripts/generate_rules_report.py --run-dir output/anvil/20260928_013215
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from meta_disco import code_rules
from meta_disco.output_utils import find_latest_run, iter_reconciled_records
from meta_disco.reconcile import declaration
from meta_disco.rule_engine import CONFLICT_MARKER, CONTENT_TIER, NOT_CLASSIFIED_MARKER
from meta_disco.rule_loader import RuleLoader, default_rules_resource
from meta_disco.schema_vocab import marker_values, value_ancestors, value_in_vocabulary
from meta_disco.summaries import embed_json, md_code, md_table
from meta_disco.value_map import default_value_map_resource, load_value_map

PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE = PROJECT_ROOT / "docs" / "rules-dashboard-template.html"
PLACEHOLDER = "RULES_DATA_PLACEHOLDER"

KIND_YAML, KIND_CODE, KIND_MAPPING = "yaml", "code", "mapping"
GENERAL = "general"
# What a rule's condition and effect are called, by kind: a code rule has no `when`, only what it reads.
LABELS = {KIND_YAML: ("When", "Then"), KIND_CODE: ("Reads", "Sets"), KIND_MAPPING: ("Match", "Declares")}

# Every key ``RuleLoader.VALID_WHEN_KEYS`` accepts, and the basis it gives a rule. A key
# mapped to None narrows when a rule applies without saying what it reads: a size bound,
# or ``always``. A rule with only such keys has no basis, and the report refuses it.
# ``test_rules_report`` holds these keys to VALID_WHEN_KEYS, so a key added there fails
# until it is listed here.
WHEN_BASIS = {
    "header_section": code_rules.BASIS_CONTENT,
    "header_field": code_rules.BASIS_CONTENT,
    "header_pattern": code_rules.BASIS_CONTENT,
    "header_match_all": code_rules.BASIS_CONTENT,
    "header_absent": code_rules.BASIS_CONTENT,
    "header_present": code_rules.BASIS_CONTENT,
    "vcf_header_type": code_rules.BASIS_CONTENT,
    "vcf_pattern": code_rules.BASIS_CONTENT,
    "fastq_pattern": code_rules.BASIS_CONTENT,
    "dataset_pattern": code_rules.BASIS_DATASET,
    "filename_pattern": code_rules.BASIS_FILE_NAME,
    "extensions": code_rules.BASIS_EXTENSION,
    "format": code_rules.BASIS_EXTENSION,
    "file_format": code_rules.BASIS_EXTENSION,
    "file_size_min_gb": None,
    "file_size_max_gb": None,
    "always": None,
}
# Most specific first: the first basis a rule's `when` has is its basis.
BASIS_PRECEDENCE = (
    code_rules.BASIS_CONTENT,
    code_rules.BASIS_DATASET,
    code_rules.BASIS_FILE_NAME,
    code_rules.BASIS_EXTENSION,
)

# The report's prose, written once: the markdown uses it, and the dashboard reads it from
# the data it is given. Worded for a reader who does not know the pipeline's terms.
INTRO = (
    'Every rule meta-disco uses to describe a file, such as "a .bam file holds alignments" or "a CRAM whose '
    'chromosome lengths match GRCh38 is aligned to GRCh38". Each row shows what the rule looks at, what it '
    "concludes and why, and how often it applied in the classification named below."
)
KEY = [
    (
        "Kind",
        "where the rule is written: yaml, the rules file; code, in Python, for checks a rules file cannot express, "
        'such as comparing chromosome lengths; mapping, a translation from a value a submitter wrote ("Revio") '
        'to our term ("PACBIO").',
    ),
    (
        "Basis",
        "what the rule looks at: the file's extension, its name, the dataset it belongs to, its contents (headers, "
        "chromosome names and lengths, what a tar archive holds), the answer for the file it was made from "
        "(parent_file, for an index), or a submitter's value (mapping).",
    ),
    ("Files", "how many files the rule gave an answer for."),
    (
        "Won",
        "how many of those files ended up with the rule's answer, or a more specific form of it (a rule saying "
        "CHM13 on a file found to be T2T-CHM13v2.0). It can be lower when a stronger rule, or the "
        "submitter's metadata, gave a different answer. For our own rules, this compares with the answer "
        "meta-disco worked out on its own, before the submitter's metadata; for a mapping, with the file's final "
        "answer.",
    ),
]
# The dashboard colours a count that is zero; the markdown has no colour to explain.
DASHBOARD_KEY = [*KEY, ("Highlighted", "a rule that gave no answer for any file this time.")]
MARKERS_NOTE = "Not rules. Each is a reason a field of a file was left without an answer."
UNDECLARED_HEAD = "Rule names with no rule behind them"
UNDECLARED_NOTE = (
    "The counts name these rules, but the rule files in this version of meta-disco do not contain them. That "
    "happens when a rule was renamed or removed after the files were classified, or when a change still under "
    "review added it. There is nothing to show for them but the count. Once the files are classified again with "
    "the current rules, this list is empty."
)
NONE_NOTE = "None: every rule the counts name is in the rule files."
# The engine's two placeholders, worded for the reader. Held to the schema's marker enum
# (`schema_vocab.marker_values`) when the report is built, so a marker added there fails
# the report until it is worded here.
PLACEHOLDER_MARKERS = {
    NOT_CLASSIFIED_MARKER: "No rule gave this field an answer.",
    CONFLICT_MARKER: "Equally strong rules gave different answers, so the field is marked as a conflict.",
}


class ReportError(Exception):
    """The report cannot be built from what is declared and on disk."""


def basis_of(rule_id: str, when: dict) -> str:
    bases = set()
    for key in when:
        if key not in WHEN_BASIS:
            raise ReportError(f"rule {rule_id}: `when` key {key!r} has no basis in WHEN_BASIS")
        if WHEN_BASIS[key]:
            bases.add(WHEN_BASIS[key])
    for basis in BASIS_PRECEDENCE:
        if basis in bases:
            return basis
    raise ReportError(f"rule {rule_id}: its `when` ({sorted(when)}) names nothing it reads")


def _source_slice(text: str, node: yaml.Node) -> str:
    """The text a node was parsed from, shifted left by the node's own column.

    A block node's end is where the next key starts, so comment lines between the two
    are cut from the end; a comment inside the node stays, as authored.
    """
    lines = text[node.start_mark.index : node.end_mark.index].split("\n")
    while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("#")):
        lines.pop()
    column = node.start_mark.column
    return "\n".join([lines[0], *(line[min(column, len(line) - len(line.lstrip())) :] for line in lines[1:])])


def _uses_alias(node: yaml.Node, start: int, end: int) -> bool:
    """Whether a node below this one was written elsewhere: a YAML alias (``*name``).

    ``compose`` resolves an alias to the anchored node itself, so its text lies outside
    the span of the node that refers to it.
    """
    children = []
    if isinstance(node, yaml.MappingNode):
        children = [n for pair in node.value for n in pair]
    elif isinstance(node, yaml.SequenceNode):
        children = list(node.value)
    return any(not start <= c.start_mark.index <= end or _uses_alias(c, start, end) for c in children)


ALIAS = re.compile(r"(?:^|[:\-\[,]\s*)\*([A-Za-z_][\w-]*)", re.MULTILINE)


def _shown(text: str, node: yaml.Node) -> tuple[str, list[str]]:
    """What the report shows for a node, and the aliases it expanded to show it.

    The file's own text, unless an alias stands in it for a list or mapping defined
    elsewhere. Then the text would name the alias and not what it holds, so the node's
    value is shown instead, written out as YAML, with the aliases it expanded.
    """
    raw = _source_slice(text, node)
    if not _uses_alias(node, node.start_mark.index, node.end_mark.index):
        return raw, []
    value = yaml.SafeLoader("").construct_document(node)
    return yaml.safe_dump(value, sort_keys=False, width=110).rstrip(), sorted(set(ALIAS.findall(raw)))


def _mapping_items(node: yaml.MappingNode) -> dict:
    return {key.value: value for key, value in node.value}


def _sliced_entries(text: str, top_key: str, id_key: str, fields: tuple[str, ...]) -> dict[str, dict]:
    """For each entry of the ``top_key`` list in the first document holding it, ``fields`` as shown.

    Each field maps to ``_shown``'s ``(text, expanded aliases)``. Only the text is taken
    from here. What an entry means is read through its loader (``RuleLoader``,
    ``load_value_map``), which the callers run first, so the report shows only a file the
    engine accepts.
    """
    for document in yaml.compose_all(text):
        items = _mapping_items(document) if isinstance(document, yaml.MappingNode) else {}
        if top_key in items:
            out = {}
            for entry in items[top_key].value:
                entry_items = _mapping_items(entry)
                out[entry_items[id_key].value] = {f: _shown(text, entry_items[f]) for f in fields if f in entry_items}
            return out
    raise ReportError(f"no `{top_key}` list in the file")


def yaml_rules(path: Path | None) -> list[dict]:
    # Loaded first, so a file the engine refuses fails with the loader's message, not a slicing error.
    loaded = RuleLoader(path).load().rules
    text = (path or default_rules_resource()).read_text(encoding="utf-8")
    sliced = _sliced_entries(text, "rules", "id", ("when", "then"))
    return [
        {
            "id": r.id,
            "kind": KIND_YAML,
            "defined_in": str(path) if path else "src/meta_disco/rules/unified_rules.yaml",
            "basis": basis_of(r.id, r.when),
            "tier": r.tier,
            "condition": sliced[r.id]["when"][0],
            "effect": sliced[r.id]["then"][0],
            "expanded": sliced[r.id]["when"][1] + sliced[r.id]["then"][1],
            "rationale": r.rationale,
            "dataset": f"dataset_pattern {r.when['dataset_pattern']}" if "dataset_pattern" in r.when else GENERAL,
        }
        for r in loaded
    ]


def code_rule_rows() -> list[dict]:
    return [
        {
            "id": r.id,
            "kind": KIND_CODE,
            "defined_in": r.module,
            "basis": r.basis,
            "tier": CONTENT_TIER if r.basis == code_rules.BASIS_CONTENT else None,
            "condition": r.reads,
            "expanded": [],
            "effect": ", ".join(r.sets),
            "rationale": r.rationale,
            "dataset": GENERAL,
        }
        for r in code_rules.CODE_RULES
    ]


def mapping_rows(path: Path | None) -> list[dict]:
    loaded = load_value_map(path).rows  # first, as in `yaml_rules`
    text = (path or default_value_map_resource()).read_text(encoding="utf-8")
    sliced = _sliced_entries(text, "rows", "id", ("match", "declares"))
    out = []
    for row in loaded:
        scope = row.scope
        where = (
            ", ".join(f"{k} {v}" for k, v in (("source", scope.source), ("dataset", scope.dataset)) if v)
            if scope
            else ""
        )
        out.append(
            {
                "id": row.id,
                "kind": KIND_MAPPING,
                "defined_in": str(path) if path else "src/meta_disco/rules/value_map.yaml",
                "basis": code_rules.BASIS_MAPPING,
                "tier": None,
                "condition": sliced[row.id]["match"][0],
                "effect": sliced[row.id]["declares"][0] if "declares" in sliced[row.id] else None,
                "expanded": sliced[row.id]["match"][1]
                + (sliced[row.id]["declares"][1] if "declares" in sliced[row.id] else []),
                "rationale": row.reason,
                "dataset": where or GENERAL,
                "seeded": not row.authored,
            }
        )
    return out


def _won(field_name: str, claimed: str, answer: dict) -> bool:
    """Whether a claim's declaration is the slot's answer, or a broader term of it.

    A rule that says ``CHM13`` agrees with a file resolved to ``T2T-CHM13v2.0``, whose
    ancestor it is, as resolution itself treats it (``schema_vocab.most_specific``). An
    answer outside today's vocabulary (a term retired since the run) has no ancestors
    to compare with, so only equality counts for it.
    """
    answered = declaration(answer)
    if answered is None:
        return False
    if claimed == answered:
        return True
    return value_in_vocabulary(field_name, answered) and claimed in value_ancestors(field_name, answered)


@dataclass
class Tally:
    """What one rule id or marker fired on."""

    claims: int = 0
    files: int = 0
    won: int = 0
    datasets: Counter = field(default_factory=Counter)
    source_types: Counter = field(default_factory=Counter)


def tally(records, rule_ids: set[str], mapping_ids: set[str]) -> tuple[int, dict[str, Tally]]:
    """One pass over the reconciled records: the record count, and per rule id and per marker, what fired where.

    For a rule or a translation row, only a claim that declares something counts: a value,
    or ``not_applicable`` (``reconcile.declaration``). One that declares ``not_classified``
    or copies a ``conflict`` gave the file no answer, as the index producer's
    ``inherited_from_parent`` does for a parent with none. A marker is counted wherever it
    appears, since recording no answer is what a marker does. An id in neither set (one
    nothing declares) is counted like a marker and never judged as having won.
    """
    stats: defaultdict[str, Tally] = defaultdict(Tally)
    n = 0
    for record in records:
        n += 1
        dataset = record.get("dataset_title") or ""
        fired, won = set(), set()
        for field_name, slot in record["classifications"].items():
            if not isinstance(slot, dict):
                continue
            for claim in slot.get("evidence") or []:
                key = claim.get("rule_id") or claim.get("marker")
                if not key:
                    continue
                judged = key in mapping_ids or key in rule_ids
                claimed = declaration(claim) if judged else None
                if judged and claimed is None:
                    continue
                stats[key].claims += 1
                fired.add(key)
                if key in mapping_ids:
                    stats[key].source_types[claim.get("source_type")] += 1
                    answer = slot
                elif key in rule_ids:
                    if "inferred" not in slot:
                        raise ReportError("a reconciled slot has no `inferred` answer: the run predates #432")
                    answer = slot["inferred"]
                else:
                    continue
                if claimed is not None and _won(field_name, claimed, answer):
                    won.add(key)
        for key in fired:
            stats[key].files += 1
            stats[key].datasets[dataset] += 1
        for key in won:
            stats[key].won += 1
    return n, stats


def _counted(entry: Tally | None) -> dict:
    entry = entry or Tally()
    return {
        "claims": entry.claims,
        "files": entry.files,
        "won": entry.won,
        "datasets": dict(entry.datasets.most_common()),
        "source_types": {k or "(none)": v for k, v in entry.source_types.most_common()},
    }


def run_date(name: str) -> str | None:
    """A run directory's date, from its ``YYYYMMDD_HHMMSS`` name, as "28 September 2026"; None for another name."""
    try:
        when = datetime.strptime(name, "%Y%m%d_%H%M%S")
    except ValueError:
        return None
    return f"{when.day} {when:%B %Y}"


def build(rules_path: Path | None, value_map_path: Path | None, records, run_dir: Path) -> dict:
    """The report's data. A path left None reads the bundled file."""
    if set(PLACEHOLDER_MARKERS) != marker_values():
        raise ReportError(f"the schema's markers {sorted(marker_values())} are not the ones worded here")
    rules = yaml_rules(rules_path) + code_rule_rows() + mapping_rows(value_map_path)
    ids = [r["id"] for r in rules]
    duplicates = sorted(i for i, c in Counter(ids).items() if c > 1)
    if duplicates:
        raise ReportError(f"rule ids declared twice: {duplicates}")
    markers = [{"id": m.id, "written_as": "rule_id", "meaning": m.meaning} for m in code_rules.MARKERS]
    markers += [{"id": k, "written_as": "marker", "meaning": v} for k, v in PLACEHOLDER_MARKERS.items()]
    n, stats = tally(
        records,
        rule_ids={r["id"] for r in rules if r["kind"] != KIND_MAPPING},
        mapping_ids={r["id"] for r in rules if r["kind"] == KIND_MAPPING},
    )
    for r in [*rules, *markers]:
        r.update(_counted(stats.get(r["id"])))
    known = set(ids) | {m["id"] for m in markers}
    date = run_date(run_dir.name)
    return {
        "run": run_dir.name,
        "records": n,
        "provenance": f"{len(rules)} rules. Counts from classifying {n:,} files"
        + (f" on {date}" if date else "")
        + f" (output folder {run_dir.name}).",
        "rules": rules,
        "markers": markers,
        "undeclared": [{"id": k, **_counted(v)} for k, v in sorted(stats.items()) if k not in known],
        "labels": LABELS,
        "text": {
            "intro": INTRO,
            "key": DASHBOARD_KEY,
            "markers_note": MARKERS_NOTE,
            "undeclared_head": UNDECLARED_HEAD,
            "undeclared_note": UNDECLARED_NOTE,
            "none_note": NONE_NOTE,
        },
    }


def _n(value: int) -> str:
    return f"{value:,}"


def _where(datasets: dict, limit: int = 3) -> str:
    # A dataset title is catalog text, so a code span: Jekyll would render markup in it.
    shown = [f"{md_code(d or '(no dataset title)')} {c:,}" for d, c in list(datasets.items())[:limit]]
    more = len(datasets) - limit
    return "; ".join(shown) + (f"; and {more} more" if more > 0 else "")


def _fence(text: str | None, lang: str = "yaml") -> list[str]:
    body = text or ""
    fence = "~~~" if "```" in body else "```"
    return [fence + lang, body, fence]


def render_markdown(data: dict) -> str:
    rules = data["rules"]
    ours = [r for r in rules if r["kind"] != KIND_MAPPING]
    maps = [r for r in rules if r["kind"] == KIND_MAPPING]
    lines = [
        "# Rules report",
        "",
        INTRO,
        "",
        f"{data['provenance']} Generated by `make rules-report` (#572).",
        "",
        *[f"- **{k}**: {v}" for k, v in KEY],
        "",
        "## Summary",
        "",
    ]
    summary = Counter((r["kind"], r["basis"]) for r in rules)
    never = Counter((r["kind"], r["basis"]) for r in rules if not r["files"])
    lines += md_table(
        ["kind", "basis", "rules", "gave no answer"],
        [[k, b, _n(c), _n(never[(k, b)])] for (k, b), c in sorted(summary.items())],
        align="right",
    )
    lines += ["", "## Rules", ""]
    lines += md_table(
        ["rule", "kind", "basis", "tier", "rationale", "dataset", "files", "won", "datasets"],
        [
            [
                md_code(r["id"]),
                r["kind"],
                r["basis"],
                str(r["tier"] or ""),
                r["rationale"],
                r["dataset"],
                _n(r["files"]),
                _n(r["won"]),
                _where(r["datasets"]),
            ]
            for r in ours
        ],
    )
    lines += ["", "## Translation rows", ""]
    lines += md_table(
        ["mapping", "reason", "dataset", "seeded", "files", "won", "datasets", "answers by source"],
        [
            [
                md_code(r["id"]),
                r["rationale"] or "",
                r["dataset"],
                "yes" if r["seeded"] else "",
                _n(r["files"]),
                _n(r["won"]),
                _where(r["datasets"]),
                "; ".join(f"{k} {v:,}" for k, v in r["source_types"].items()),
            ]
            for r in maps
        ],
    )
    lines += ["", "## Markers", "", MARKERS_NOTE, ""]
    lines += md_table(
        ["id", "written as", "files", "meaning"],
        [[md_code(m["id"]), m["written_as"], _n(m["files"]), m["meaning"]] for m in data["markers"]],
    )
    lines += ["", f"## {UNDECLARED_HEAD}", "", UNDECLARED_NOTE, ""]
    if data["undeclared"]:
        lines += md_table(
            ["id", "files", "claims"], [[md_code(u["id"]), _n(u["files"]), _n(u["claims"])] for u in data["undeclared"]]
        )
    else:
        lines.append(NONE_NOTE)
    lines += ["", "## Rule details", ""]
    for r in rules:
        first, second = LABELS[r["kind"]]
        lang = "text" if r["kind"] == KIND_CODE else "yaml"
        lines += [
            f"### {md_code(r['id'])}",
            "",
            f"{r['kind']}, basis {r['basis']}, in `{r['defined_in']}`",
            "",
            *(
                [f"Written with {', '.join(f'`*{a}`' for a in r['expanded'])}, shown expanded.", ""]
                if r["expanded"]
                else []
            ),
            f"{first}:",
            "",
            *_fence(r["condition"], lang),
            "",
            f"{second}:",
            "",
            *_fence(r["effect"], lang),
            "",
        ]
        if r["rationale"]:
            lines += ["Rationale:", "", *_fence(r["rationale"], "text"), ""]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List every rule, with how often it fired in a reconciled run (#572)")
    parser.add_argument("--run-dir", type=Path, help="Reconciled run directory (default: latest under output/anvil)")
    parser.add_argument("--rules", type=Path, help="Rule file (default: the bundled unified_rules.yaml)")
    parser.add_argument("--value-map", type=Path, help="Translation table (default: the bundled value_map.yaml)")
    parser.add_argument("--markdown", type=Path, default=PROJECT_ROOT / "docs" / "rules-report.md")
    parser.add_argument("--html", type=Path, default=PROJECT_ROOT / "docs" / "rules-dashboard.html")
    args = parser.parse_args(argv)
    try:
        run_dir = args.run_dir or find_latest_run(Path("output/anvil"))
        data = build(args.rules, args.value_map, iter_reconciled_records(run_dir), run_dir)
    except (ReportError, FileNotFoundError, ValueError) as exc:
        print(f"rules-report: {exc}", file=sys.stderr)
        return 1
    args.markdown.write_text(render_markdown(data), encoding="utf-8")
    args.html.write_text(embed_json(TEMPLATE.read_text(encoding="utf-8"), PLACEHOLDER, data), encoding="utf-8")
    print(f"Rules report for {run_dir.name}: {len(data['rules'])} rules -> {args.markdown}, {args.html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
