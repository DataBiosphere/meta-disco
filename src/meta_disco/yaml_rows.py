"""The YAML-node walk and the append-only seeding the two translation tables share.

``value_map`` (raw slot values, #414) and ``activity_map`` (lineage's raw words, #584)
are each a document whose one key is ``rows``, walked as YAML nodes rather than loaded
to dicts so that a key given twice *inside* a row can be refused naming that row, and
each seeded by appending rows after the last one without rewriting any. ``where`` is
the table's name in an error message (``"value map"``, ``"activity map"``).
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import yaml

STR_TAG = "tag:yaml.org,2002:str"
NULL_TAG = "tag:yaml.org,2002:null"
_ROW_DASH = re.compile(r"^( *)- ", re.MULTILINE)


def parse_rows(text: str, where: str) -> list[yaml.Node]:
    """The row nodes of the document, checked down to the top-level shape."""
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    if root is None:
        raise ValueError(f"{where}: the document is empty; it needs a `rows` key")
    document = mapping(root, where)
    if set(document) != {"rows"}:
        raise ValueError(f"{where}: top-level keys are {sorted(document)}, expected exactly ['rows']")
    rows_node = document["rows"]
    if rows_node.tag == NULL_TAG:
        return []
    if not isinstance(rows_node, yaml.SequenceNode):
        raise ValueError(f"{where}: `rows` is not a list (line {rows_node.start_mark.line + 1})")
    return list(rows_node.value)


def mapping(node: yaml.Node, at: str) -> dict[str, yaml.Node]:
    """A mapping node's entries by string key, refusing anything else and any key given twice."""
    if not isinstance(node, yaml.MappingNode):
        raise ValueError(f"{at}: expected a mapping, got {kind(node)} (line {node.start_mark.line + 1})")
    entries: dict[str, yaml.Node] = {}
    for key_node, value_node in node.value:
        key = scalar(key_node, at)
        if key in entries:
            raise ValueError(f"{at}: key {key!r} given twice (line {key_node.start_mark.line + 1})")
        entries[key] = value_node
    return entries


def scalar(node: yaml.Node, at: str) -> str:
    if not isinstance(node, yaml.ScalarNode) or node.tag != STR_TAG:
        raise ValueError(f"{at}: expected a string, got {kind(node)} (line {node.start_mark.line + 1})")
    return node.value


def kind(node: yaml.Node) -> str:
    if isinstance(node, yaml.ScalarNode):
        return f"{node.tag.rsplit(':', 1)[-1]} {node.value!r}"
    return type(node).__name__.replace("Node", "").lower()


def read_reason(node: yaml.Node, at: str) -> str:
    text = scalar(node, f"{at} reason")
    if not text.strip():
        raise ValueError(f"{at}: reason is empty — an authored row records why; a seeded row has no `reason` key")
    return text


def read_seeded_from(node: yaml.Node, at: str) -> tuple[str, ...]:
    if not isinstance(node, yaml.SequenceNode):
        raise ValueError(f"{at}: seeded_from is not a list (line {node.start_mark.line + 1})")
    return tuple(scalar(item, f"{at} seeded_from") for item in node.value)


def fresh_id(candidate: str, digest_of: str, taken: set[str], where: str) -> str:
    """``candidate``, or ``candidate_<digest>`` where another key already slugged to it (``a-b`` and ``a_b``).

    The digest is of ``digest_of``, the key's own text, so the id a key gets does not
    depend on how many others collided before it — the same scan on a fresh table mints
    the same ids. Six hex characters, extended one at a time while the result is taken,
    so a table that already holds the short form still gets an unused id.
    """
    if candidate not in taken:
        return candidate
    digest = hashlib.sha1(digest_of.encode()).hexdigest()
    for n in range(6, len(digest) + 1):
        if (id := f"{candidate}_{digest[:n]}") not in taken:
            return id
    raise ValueError(f"{where}: no unused id for {candidate!r} — the table already holds every digest of {digest_of}")


def open_rows(text: str, where: str, empty: bool) -> str:
    """``text`` ready for row items to be appended: an empty ``rows`` value cut out, a final newline ensured.

    ``rows: []``, ``rows: null`` and their multi-line spellings load as an empty table,
    but a block item cannot follow any of them, so the empty value is cut out by its
    source marks, leaving the bare key (and any comment after the value). ``empty`` is
    whether the table loaded with no rows, which the caller already knows.
    """
    if not empty:
        return text if text.endswith("\n") else text + "\n"
    rows_node = mapping(yaml.compose(text, Loader=yaml.SafeLoader), where)["rows"]
    start, end = rows_node.start_mark.index, rows_node.end_mark.index
    after = text[end:].lstrip(" \t")
    text = text[:start].rstrip(" \t") + ("  " if after.startswith("#") else "") + after
    return text if text.endswith("\n") or not text else text + "\n"


def row_indent(text: str) -> str:
    """The indentation of the existing row items, or two spaces where there are none."""
    found = _ROW_DASH.search(text)
    return found.group(1) if found else "  "


def row_text(row: dict, indent: str) -> str:
    """One row as YAML, emitted by PyYAML so every escape is the library's, indented under the others."""
    # ASCII-only output: PyYAML then escapes every non-ASCII and non-printable character
    # itself, and what it writes reads back to the same string.
    text = yaml.safe_dump([row], sort_keys=False, allow_unicode=False, default_flow_style=None, width=10**6)
    return "".join(f"{indent}{line}\n" for line in text.splitlines())


def generation_name(root: Path, path: Path) -> str:
    """The generation directory a file sits in, as a seeded row's ``seeded_from`` names it: relative to ``root``."""
    try:
        return path.parent.relative_to(root).as_posix()
    except ValueError:
        return path.parent.as_posix()


def replace_checked(
    table_path: Path, new_text: str, reload: Callable[[Path], int], expected_rows: int, where: str
) -> None:
    """Write ``new_text`` beside the table and rename it over the table only once it loads with ``expected_rows`` rows.

    ``reload`` loads a path and returns its row count. An interrupted write or a table
    that would not load leaves the original untouched rather than truncated or
    half-replaced; the failure raises naming the table.
    """
    tmp = table_path.with_name(f"{table_path.name}.{os.getpid()}.{uuid4().hex[:8]}.tmp")
    try:
        tmp.write_text(new_text, encoding="utf-8")
        loaded = reload(tmp)
        if loaded != expected_rows:
            raise ValueError(f"reloaded {loaded} rows, expected {expected_rows}")
        tmp.replace(table_path)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise ValueError(
            f"{where}: seeding {table_path} produced a table that does not load; left unchanged: {exc}"
        ) from exc
