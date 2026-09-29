"""Derivation edges inference states from a child's own name (ADR-0002, #356).

Two producers write one: the index producer (``IndexActivity``) and the catch-all, for a
checksum file (``ChecksumActivity``). Each works out the parent's name from the child's own
(the index producer's candidates are its own, ``get_parent_candidates``) and looks it up
in the child's dataset; the name index, that lookup and the edge it yields are built here.

**An edge is written only where the parent resolves**: exactly one file of the child's
dataset carries the name. The edge then carries the parent's record key
(``pipeline.SOURCE_RECORD_KEYS``) as ``parent_key``. Where no file carries it, or two do,
no edge is written. ADR-0002 keeps an edge whose parent does not resolve (an ``external``
one) only for a source that names the parent independently of the child: a header line, a
table row. Here the name is worked out from the child's own — its name less a suffix, or
with the suffix replaced (``sample.bai`` -> ``sample.bam``) — so an unresolved edge would
restate what the child's name, extension and ``data_type`` already say.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from . import code_rules
from .code_rules import EdgeRule
from .file_name import EXTENSION_MAP, FileName
from .pipeline import RecordKey, input_key_value

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
            index[(record.get("dataset_id", "unknown"), name.lower())].append(record)
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
    return {"activity": rule.activity, "named_by": named_by, "inputs": [used]}


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
    parent = resolve(index, record.get("dataset_id", "unknown"), name.stem)
    if parent is None:
        return None
    return generated_by(code_rules.CHECKSUM_BY_NAME, parent, key)
