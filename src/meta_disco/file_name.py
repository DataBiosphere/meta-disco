"""The parsed filename fact.

A file's name answers several unrelated questions at once — what tokens it
carries (`rnaseq`, `chm13`), what its extension is, whether it is compressed or
archived. `FileName` parses those apart once so the rest of the system reads a
structured fact instead of re-deriving from a raw string (epic #242).

This is the foundation increment (#241): the engine consumes ``extension``; the
follow-ups separate a derived ``format`` from the extension (#243), split the
compression/archive wrappers out of the extension vocabulary (#244), and thread
the parsed ``FileName`` from the load boundary (#246).
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .rule_loader import UnifiedRules

# Compression and archive suffixes — "wrappers" around the format, not the
# format itself. Kept as advice; in this foundation they are informational and
# may overlap the (still-compound) ``extension`` — the clean split is #244.
WRAPPER_SUFFIXES = (".gz", ".bgz", ".bz2", ".xz", ".zip", ".tar")


@dataclass(frozen=True)
class FileName:
    """A filename parsed into its parts.

    ``raw`` is the name as given (never empty — the input contract guarantees
    ``^.+$``, so a nameless record is diverted to ``validation_failed`` and
    never reaches a parser). ``extension`` is the known extension the rules key
    on, or ``None`` when the name carries no known extension — never the junk
    last-dot suffix ``UnifiedRules.extract_extension`` returns
    (``"hprc-v1.0-mc-grch38"`` → ``".0-mc-grch38"``). ``wrappers`` are the
    trailing compression/archive suffixes, in name order. ``stem`` is the name
    with the extension removed.
    """

    raw: str
    stem: str
    extension: str | None
    wrappers: tuple[str, ...]

    @classmethod
    def parse(cls, raw: str, rules: "UnifiedRules") -> "FileName":
        """Parse ``raw`` against the rule vocabulary.

        ``extension`` matches ``UnifiedRules.extract_extension`` for every name
        that has a known extension (a compound like ``.vcf.gz``, else a simple
        suffix the ``extension_map`` knows), and is ``None`` otherwise — where
        ``extract_extension`` would have returned a junk last-dot suffix that
        matched no rules anyway. So routing is unchanged; the value is that the
        absence of an extension is now stated honestly.
        """
        lower = raw.lower()

        extension = None
        for ext in rules.COMPOUND_EXTENSIONS:
            if lower.endswith(ext):
                extension = ext
                break
        if extension is None and "." in raw:
            simple = "." + raw.rsplit(".", 1)[1].lower()
            if simple in rules.extension_map:
                extension = simple

        wrappers: list[str] = []
        rest = lower
        while True:
            for suffix in WRAPPER_SUFFIXES:
                if rest.endswith(suffix):
                    wrappers.append(suffix)
                    rest = rest[: -len(suffix)]
                    break
            else:
                break
        wrappers.reverse()  # name order: "x.tar.gz" -> (".tar", ".gz")

        stem = raw[: -len(extension)] if extension else raw
        return cls(raw=raw, stem=stem, extension=extension, wrappers=tuple(wrappers))
