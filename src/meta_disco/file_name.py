"""The parsed filename fact.

A file's name answers several unrelated questions at once — what tokens it
carries (`rnaseq`, `chm13`), what its extension is, whether it is compressed or
archived, and what file *format* it therefore is. ``FileName`` parses those
apart so a caller reads a structured fact instead of re-deriving from a raw
string (epic #242).

``FileName`` is a pure data type; it is built by ``UnifiedRules.parse_file_name``
(the parse is vocabulary-gated, so it lives with the rules). ``extension`` is
syntactic — the exact suffix, ``.cram`` distinct from ``.bam`` — while
``format`` is *derived*: what the file actually is, collapsing spelling and
compression variants of one format to a single identity (``.fa``/``.fasta`` →
``FASTA``). This increment (#243) derives the stage-1 format (from the extension
alone, at parse time, no I/O) and records that provenance in ``format_source``;
the follow-ups add the later derivation stages — stem/filename pattern
(``FormatSource.STEM``) and a content/header read (``FormatSource.CONTENT``) —
split the compression/archive wrappers out of the extension vocabulary (#244),
and thread the parsed ``FileName`` from the load boundary (#246).
"""

from dataclasses import dataclass
from enum import Enum


class Format(str, Enum):
    """A canonical file-format identity — what the file *is*, not how its name is
    spelled.

    One format collapses the spelling and compression variants of the same
    format (``.fa``/``.fasta``/``.fa.gz``/``.fasta.gz`` → ``FASTA``), so a rule
    keys on ``format: FASTA`` once instead of re-listing every extension. Formats
    that the size-threshold assay rules must still tell apart stay distinct —
    ``BAM`` and ``CRAM`` are separate identities, keyed at the ``extension``
    level.

    Seeded with the core sequencing formats — the ones with a clear canonical
    identity and the repeated extension groups the rules key on. Extensions with
    no clean collapse (peaks, signal tracks, images, text, archives, single-cell
    matrices, nanopore) are deliberately left unmapped, so their ``format`` is
    ``None`` until a group that needs it migrates and adds its identity here.
    """

    BAM = "BAM"
    CRAM = "CRAM"
    SAM = "SAM"
    VCF = "VCF"
    BCF = "BCF"
    GVCF = "GVCF"
    FASTQ = "FASTQ"
    FASTA = "FASTA"
    BED = "BED"
    GFA = "GFA"
    RGFA = "RGFA"


class FormatSource(str, Enum):
    """How a ``format`` was derived — its resolution stage (epic #242).

    ``format`` resolves on a timeline of increasing cost: from the extension
    alone (no I/O), then from the stem / filename pattern (no I/O), then from a
    content or header read (after fetch, I/O). The source records which stage
    answered, so a cheap answer is never mistaken for one that read bytes.

    Only ``EXTENSION`` is produced today (#243). ``STEM`` and ``CONTENT`` are the
    reserved seam the later stages plug into — defined so the representation is
    settled now, but never set in this increment.
    """

    EXTENSION = "extension"
    STEM = "stem"  # reserved: stage-2 stem / filename-pattern derivation
    CONTENT = "content"  # reserved: stage-3 content / header read


@dataclass(frozen=True)
class FileName:
    """A filename parsed into its parts.

    ``raw`` is the name as given. In the pipeline it is never empty — the input
    contract (``^.+$``) diverts a nameless record to ``validation_failed`` before
    it is parsed — though ``FileName`` itself does not re-validate. ``extension``
    is the known extension the rules key
    on, or ``None`` when the name carries no known extension — never the junk
    last-dot suffix ``UnifiedRules.extract_extension`` returns
    (``"hprc-v1.0-mc-grch38"`` → ``".0-mc-grch38"``). ``wrappers`` are the
    trailing compression/archive suffixes, in name order. ``stem`` is the
    token-carrying part: the name with its known ``extension`` removed, or —
    when there is none — its trailing ``wrappers`` stripped (an unknown suffix
    like ``.xyz`` is kept, since it is neither a known extension nor a wrapper).

    ``format`` is the derived canonical format (see :class:`Format`), ``None``
    when the extension maps to no seeded format (or there is no known extension).
    ``format_source`` records how it was derived — ``FormatSource.EXTENSION`` for
    the stage-1 (extension-only) derivation, ``None`` when ``format`` is
    unresolved. As built by ``UnifiedRules.parse_file_name`` the two move
    together — both set or both ``None`` — though ``FileName`` itself does not
    enforce that of a directly-constructed instance.
    """

    raw: str
    stem: str
    extension: str | None
    wrappers: tuple[str, ...]
    format: Format | None = None
    format_source: FormatSource | None = None
