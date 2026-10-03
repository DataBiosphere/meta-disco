"""Derivation edges inference states, and the name index their parents resolve in (ADR-0002, #356).

Three producers write one. Two work out the parent's name from the child's own: the index
producer (``IndexActivity``; its candidates are its own, ``get_parent_candidates``) and the
catch-all, for a checksum file (``ChecksumActivity``). The VCF producer reads it from a
command line in the child's header (``producer_steps``, #609). Each looks the name up in
the child's dataset; the name index, that lookup and the edge it yields are built here.

**An edge is written only where the parent resolves**: exactly one file of the child's
dataset carries the name. The edge then carries the parent's record key
(``pipeline.SOURCE_RECORD_KEYS``) as ``parent_key``. Where no file carries it, or two do,
no edge is written. ADR-0002 keeps an edge whose parent does not resolve (an ``external``
one) only for a source that names the parent independently of the child: a header line, a
table row. The two name rules work the name out from the child's own — its name less a
suffix, or with the suffix replaced (``sample.bai`` -> ``sample.bam``) — so an unresolved
edge would restate what the child's name, extension and ``data_type`` already say. The
header rule does name its parent independently, but by a path where the workflow ran,
which says nothing a reader could follow, so it too writes no unresolved edge.

**Merging every source's step** (#577) is here too: reconcile hands :func:`merge_steps`
inference's step and the steps the source tables state (``reconcile_lineage``), and it
returns the one ``generated_by`` they agree on, or the conflict that prevents one.
:func:`misfits` flags a step that does not fit its activity's declaration.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace

from . import activities, code_rules
from .code_rules import EdgeRule
from .file_name import EXTENSION_MAP, FileName
from .models import ClaimSource
from .pipeline import RecordKey, input_key_value
from .records import dataset_of

# The `EXTENSION_MAP` category of a checksum file's extension. The extension decides
# whether a checksum edge is looked for, not whether a rule fired on the file.
CHECKSUM_CATEGORY = "checksum"

# An extension category (``file_name.EXTENSION_MAP``) to the derivation model's
# ``parent_kind_enum``: the two vocabularies overlap but are not the same words. A
# category with no enum member is deliberately absent, so it yields a null
# ``parent_kind`` — we cannot tell, rather than a guessed kind.
PARENT_KIND_BY_CATEGORY = {
    "alignment": "alignment",
    "variant": "variants",
    "reads": "reads",
    "sequence": "sequence",
    "intervals": "intervals",
    "signal": "signal",
    "genotype_plink": "genotypes",
    "single_cell_matrix": "expression_matrix",
}

NameIndex = dict[tuple[str, str], list[dict]]


def files_by_folded_name(records: Iterable[dict]) -> NameIndex:
    """Every input record by ``(dataset_id, file_name case-folded)``, all of them per key.

    A dict keyed that way to one record would silently collapse a name two files share,
    which is what let an index inherit from a parent picked by iteration order (#438);
    keeping the list makes "this name identifies one file" a thing a caller can test.

    The name half of the key is case-folded, so this agrees with ``route``, which has
    folded case since #449 (#455). Folding makes two names differing only by case
    identify neither file, which is #438's rule read case-insensitively.

    A record whose ``file_name`` is not a string is left out: folding reads every record
    in the dataset, companion or not, and a drifted name can be no file's parent — an
    edge's ``parent_file`` is a string, and ``parent_kind_of`` parses it. Leaving it out
    does not make a drifted name safe to *classify*.
    """
    index: NameIndex = defaultdict(list)
    for record in records:
        name = record.get("file_name")
        if isinstance(name, str) and name:
            index[(dataset_of(record), name.lower())].append(record)
    return index


def parent_kind_of(parent_name: str) -> str | None:
    """What kind of file the parent is, from its own extension, or None when that cannot be told.

    None for a parent whose category has no ``parent_kind`` term.
    """
    return PARENT_KIND_BY_CATEGORY.get(_category_of(parent_name) or "")


def _category_of(file_name: str) -> str | None:
    """The extension category of one filename, trying shorter suffixes of a compound one.

    ``FileName.parse`` keeps a compound core whole — a gVCF is ``.g.vcf`` — and
    ``EXTENSION_MAP`` keys the simple form, so an exact lookup misses every gVCF parent
    and calls it a kind we cannot tell. Dropping leading segments finds ``.vcf``.

    The map is the rules vocabulary and is deliberately not edited to suit this: adding
    a key there would move what the rules match on, and the kind of a parent is the
    edge's question.
    """
    parsed = FileName.parse(file_name).extension or ""
    segments = parsed.split(".")
    for start in range(1, len(segments)):
        category = EXTENSION_MAP.get("." + ".".join(segments[start:]))
        if category:
            return category
    return None


def generated_by(rule: EdgeRule, parent: dict, key: RecordKey) -> dict:
    """The child's ``generated_by``: ``rule``'s step, with ``parent`` as its one input.

    ``parent_file`` is the catalog's spelling, not the folded name (#455); a parent with
    no record key raises rather than giving an ungrounded input.
    """
    parent_name = parent["file_name"]
    named_by = [{"source_type": rule.source_type, "rule_id": rule.id}]
    used = {
        "role": rule.role,
        "parent_file": parent_name,
        "parent_key": input_key_value(parent, key, f"ground a {rule.activity} input on its parent"),
        "parent_kind": parent_kind_of(parent_name),
        "named_by": named_by,
    }
    return {"activity": rule.activity, "named_by": [dict(n) for n in named_by], "inputs": [used]}


def matches(index: NameIndex, dataset_id: str, name: str) -> list[dict]:
    """Every input record of ``dataset_id`` carrying ``name`` up to case."""
    return index.get((dataset_id, name.lower()), [])


def resolve(index: NameIndex, dataset_id: str, name: str) -> dict | None:
    """The one input record of ``dataset_id`` carrying ``name`` up to case, or None if none or several do."""
    found = matches(index, dataset_id, name)
    return found[0] if len(found) == 1 else None


def checksum_generated_by(record: dict, name: FileName, index: NameIndex, key: RecordKey) -> dict | None:
    """A checksum file's ``generated_by``, a ``ChecksumActivity`` with its one input, or None.

    A file is a checksum when ``EXTENSION_MAP`` calls its extension one (``.md5``), read
    off ``name`` as ``FileName.parse`` peeled it. Its parent is ``name``'s stem, the name
    less that extension and any wrapper (``sample.bam.md5`` and ``sample.bam.md5.gz`` ->
    ``sample.bam``), taken only when exactly one file of its dataset carries it;
    otherwise None, as for any other file.
    """
    if EXTENSION_MAP.get(name.extension or "") != CHECKSUM_CATEGORY or not name.stem:
        return None
    parent = resolve(index, dataset_of(record), name.stem)
    if parent is None:
        return None
    return generated_by(code_rules.CHECKSUM_BY_NAME, parent, key)


# --- merging every source's step (#577) ------------------------------------------------


@dataclass(frozen=True)
class LineageStep:
    """One source's step for one child, as one input: a resolved lineage line, or one input of inference's step.

    ``parent_kind`` is the parent's ``parent_kind_enum`` term, read off its name as inference
    reads it (:func:`parent_kind_of`); ``parent_data_type`` its inferred ``data_type``,
    which :func:`misfits` judges against the role's declared kinds, None where not known.
    ``attribution`` is the ``Attribution`` the source gets, from :func:`lineage_attribution`
    for a lineage line.
    """

    activity: str
    role: str
    parent_key: str
    parent_file: str
    parent_kind: str | None
    attribution: dict
    parent_data_type: str | None = None


def lineage_attribution(source_type: str, row_id: str, source: ClaimSource, activity_id: str | None) -> dict:
    """How a lineage source is cited: its kind, the activity-map row that translated its words, and where it said it.

    ``source`` is a ``ClaimSource`` — the dataset, table and the column the parent was read
    from — the shape a value claim cites its source in (contract 3.8).
    """
    attribution: dict = {"source_type": source_type, "rule_id": row_id}
    if activity_id is not None:
        attribution["activity_id"] = activity_id
    attribution["source"] = source.to_dict()
    return attribution


@dataclass(frozen=True)
class StepConflict:
    """Why a file's sources give no one step: two activities; two parents in a role that takes one; a source
    naming other parents than inference names in a role, any role (#609); or, beside a specific activity, a
    generic ``Activity`` step whose parent no specific source names (in the generic step's role).

    ``said`` is who said what: per source, the activity (an activity conflict) or the
    parent's name (an edge conflict), with the source's attribution.
    """

    kind: str
    role: str | None
    said: tuple[tuple[str, dict], ...]


ACTIVITY_CONFLICT = "activity"
EDGE_CONFLICT = "edge"


def inferred_steps(step: dict | None) -> list[LineageStep]:
    """Inference's ``generated_by`` as one :class:`LineageStep` per input and attribution, in order.

    An input naming no source of its own is attributed to the step's sources, so it is not lost.
    """
    if step is None:
        return []
    return [
        LineageStep(
            step["activity"],
            used["role"],
            used["parent_key"],
            used["parent_file"],
            used.get("parent_kind"),
            attribution,
        )
        for used in step["inputs"]
        for attribution in used.get("named_by") or step.get("named_by") or []
    ]


def merge_steps(inferred: dict | None, lineage: Iterable[LineageStep]) -> tuple[dict | None, StepConflict | None]:
    """The one ``generated_by`` every source's step for a file agrees on, or the conflict that prevents one.

    ``inferred`` is the step inference wrote, from the child's name or its header (or None); ``lineage``
    the steps the source tables state. Sources agree when their activities agree
    (``activities.agreed``: the generic ``Activity`` agrees with any) and, in a role that
    takes one input, name the same parent; in any role where inference names parents, a
    source naming parents there must name the same set, since inference's step names every
    input of the step it read. Beside a specific activity, a generic step's parent
    must be one a specific source names: it then adds its attribution to that input, and a
    parent no specific source names is an edge conflict in its role — never an input in a role
    the activity does not declare. A file whose only steps are generic gets no ``generated_by``
    and no conflict: such a link is held back until an activity-map row naming ``Activity`` is
    reviewed against what it links (:func:`generic_only` tells the caller to count it).
    Agreeing sources of one input are listed together
    in its ``named_by``, and of the step in the step's; a role that takes several inputs
    keeps one input per parent. A conflict is returned, never settled: the file then gets no
    ``generated_by``. Attributions are listed inference's first, then in the order
    ``lineage`` gives them, each once.
    """
    lineage = list(lineage)
    from_inference = inferred_steps(inferred)
    said = [*from_inference, *lineage]
    if not said:
        return None, None
    activity = activities.agreed(s.activity for s in said)
    if activity == activities.UNKNOWN:
        return None, None
    if activity is None:
        return None, StepConflict(ACTIVITY_CONFLICT, None, _distinct((s.activity, s.attribution) for s in said))
    # Beside a specific activity (the generic-only case returned above), a generic step must match a parent.
    specific = [s for s in said if s.activity != activities.UNKNOWN]
    named = {s.parent_key: s for s in specific}
    for s in said:
        if s.activity != activities.UNKNOWN:
            continue
        if s.parent_key not in named:
            return None, StepConflict(
                EDGE_CONFLICT,
                s.role,
                _distinct([(s.parent_file, s.attribution), *((o.parent_file, o.attribution) for o in specific)]),
            )
    # A generic step whose parent matches stands in that parent's input, as another of its sources.
    said = [
        s if s.activity != activities.UNKNOWN else replace(named[s.parent_key], attribution=s.attribution) for s in said
    ]
    declared = {i.role: i for i in activities.declarations()[activity].inputs}
    inferred_parents = {s.role: set() for s in from_inference}
    for s in from_inference:
        inferred_parents[s.role].add(s.parent_key)
    for role in dict.fromkeys(s.role for s in said):
        in_role = [s for s in said if s.role == role]
        if len({s.parent_key for s in in_role}) > 1 and role in declared and not declared[role].many:
            return None, StepConflict(EDGE_CONFLICT, role, _distinct((s.parent_file, s.attribution) for s in in_role))
        # Inference names every input of the step it read (a name rule its one parent, a
        # header command line all its inputs), so a source naming other parents in that
        # role contradicts it rather than adding to it, in a role that takes several too.
        from_sources = {s.parent_key for s in said[len(from_inference) :] if s.role == role}
        if role in inferred_parents and from_sources and from_sources != inferred_parents[role]:
            return None, StepConflict(EDGE_CONFLICT, role, _distinct((s.parent_file, s.attribution) for s in in_role))
    inputs: dict[tuple[str, str], dict] = {}
    for s in said:
        used = inputs.setdefault(
            (s.role, s.parent_key),
            {
                "role": s.role,
                "parent_file": s.parent_file,
                "parent_key": s.parent_key,
                "parent_kind": s.parent_kind,
                "named_by": [],
            },
        )
        used["named_by"] = list(_distinct([*used["named_by"], s.attribution]))
    step_named_by = _distinct([*((inferred or {}).get("named_by") or []), *(s.attribution for s in lineage)])
    return {"activity": activity, "named_by": list(step_named_by), "inputs": list(inputs.values())}, None


def generic_only(inferred: dict | None, lineage: Iterable[LineageStep]) -> bool:
    """Whether every source's step for a file is the generic ``Activity``: :func:`merge_steps` writes none for it."""
    activities_named = [s.activity for s in [*inferred_steps(inferred), *lineage]]
    return bool(activities_named) and all(a == activities.UNKNOWN for a in activities_named)


def _distinct(items):
    """``items`` in order, each once (dicts compare by value, so a list, not a set)."""
    out: list = []
    for item in items:
        if item not in out:
            out.append(item)
    return tuple(out)


def _outside(kind: str | None, allowed: set[str]) -> bool:
    """Whether a known ``data_type`` ``kind`` falls outside ``allowed``, judged by its top term: the dotted path is the vocabulary's hierarchy."""
    return bool(allowed) and kind is not None and kind.split(".")[0] not in allowed


def misfits(step: dict, child_kind: str | None, parent_kinds: dict[str, str | None]) -> list[tuple[str, str]]:
    """How a step does not fit its activity's declaration, as ``(problem, detail)`` pairs; flagged, never refused.

    ``child_kind`` is the child's ``data_type`` value and ``parent_kinds`` each input's
    by its ``parent_key``; a kind is judged by its top term (``annotations.coverage`` is
    ``annotations``), and an unknown one (None, or a key ``parent_kinds`` lacks) is not
    judged. A one-input role given several parents is not here: :func:`merge_steps` returns
    it as an edge conflict.
    """
    declaration = activities.declarations()[step["activity"]]
    roles = {r.role: r for r in declaration.inputs}
    found: list[tuple[str, str]] = []
    if _outside(child_kind, {str(k) for k in declaration.output.kind or ()}):
        found.append(("output kind", str(child_kind)))
    present = {used["role"] for used in step["inputs"]}
    found += [("required role missing", r.role) for r in declaration.inputs if r.required and r.role not in present]
    for used in step["inputs"]:
        role = roles.get(used["role"])
        kind = parent_kinds.get(used["parent_key"])
        if role is not None and _outside(kind, {str(k) for k in role.kind or ()}):
            found.append((f"input kind ({used['role']})", str(kind)))
    return found
