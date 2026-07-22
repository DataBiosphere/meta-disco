"""The parsed filename fact.

A file's name answers several unrelated questions at once — what tokens it
carries (`rnaseq`, `chm13`), what its extension is, whether it is compressed or
archived. ``FileName`` parses those apart once so the rest of the system reads a
structured fact instead of re-deriving from a raw string (epic #242).

``FileName`` is a pure data type; it is built by ``UnifiedRules.parse_file_name``
(the parse is vocabulary-gated, so it lives with the rules). This is the
foundation increment (#241): the engine consumes ``extension``; the follow-ups
separate a derived ``format`` from the extension (#243), split the
compression/archive wrappers out of the extension vocabulary (#244), and thread
the parsed ``FileName`` from the load boundary (#246).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FileName:
    """A filename parsed into its parts.

    ``raw`` is the name as given (never empty — the input contract guarantees
    ``^.+$``, so a nameless record is diverted to ``validation_failed`` and
    never reaches a parser). ``extension`` is the known extension the rules key
    on, or ``None`` when the name carries no known extension — never the junk
    last-dot suffix ``UnifiedRules.extract_extension`` returns
    (``"hprc-v1.0-mc-grch38"`` → ``".0-mc-grch38"``). ``wrappers`` are the
    trailing compression/archive suffixes, in name order. ``stem`` is the
    token-carrying part: the name with its known ``extension`` removed, or —
    when there is none — its trailing ``wrappers`` stripped (an unknown suffix
    like ``.xyz`` is kept, since it is neither a known extension nor a wrapper).
    """

    raw: str
    stem: str
    extension: str | None
    wrappers: tuple[str, ...]
