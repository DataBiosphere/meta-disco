"""The parsed filename fact and the extension vocabulary it parses against.

A file's name answers several unrelated questions at once — what tokens it
carries (`rnaseq`, `chm13`), what its extension is, whether it is compressed or
archived, and what file *format* it therefore is. ``FileName`` parses those
apart so a caller reads a structured fact instead of re-deriving from a raw
string (epic #242).

``FileName`` is a pure data type and its parse is a **pure function**:
``FileName.parse(name)`` needs no loaded ``UnifiedRules`` — the whole extension
vocabulary (``WRAPPER_SUFFIXES`` / ``EXTENSION_TO_FORMAT`` / ``EXTENSION_MAP`` and
the derived ``CORE_EXTENSIONS``) lives here in-code as a self-contained leaf (#252). ``extension`` is syntactic — the exact core suffix,
``.cram`` distinct from ``.bam`` — with any compression/archive kept apart in
``wrappers`` (#244: ``sample.vcf.gz`` → extension ``.vcf`` + wrappers ``(".gz",)``).
``format`` is *derived*: what the file actually is, collapsing spelling and
compression variants of one format to a single identity (``.fa``/``.fasta`` →
``FASTA``). #243 derives the stage-1 format (from the core extension alone, at
parse time, no I/O) and records that provenance in ``format_source``; the
remaining follow-up threads the parsed ``FileName`` from the load boundary (#246).
"""

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


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


# ---------------------------------------------------------------------------
# Extension vocabulary (#252)
#
# Hoisted in-code from unified_rules.yaml so the parse is pure — three of these
# four were already static ClassVars on UnifiedRules; EXTENSION_MAP was the last
# YAML-loaded piece, and moving it here is what lets FileName.parse run with no
# rules instance. UnifiedRules re-exposes these as thin delegators.
# ---------------------------------------------------------------------------

# Compression and archive suffixes — "wrappers" (containers) around the format,
# not the format itself. The parse peels *every* trailing wrapper off the name
# first, then recognizes the core the remainder ends with (#245): a container is
# always stripped, so ``.fast5.tar.gz`` -> core ``.fast5`` + (``.tar``, ``.gz``)
# falls out with no per-combination allowlist, and an archive with no inner format
# (``graph.tar.gz``) leaves ``extension=None``. Ordered longest-first: the peel loop
# takes the first `endswith` match, so `.bgz` must precede `.gz` or a `.bgz` token
# would mis-peel as `.gz` and leave a dangling `b`. `.tar`/`.zip` are containers
# here, never content extensions (#245).
WRAPPER_SUFFIXES: tuple[str, ...] = (".bgz", ".bz2", ".zip", ".tar", ".gz", ".xz")

# Known core extension -> canonical file Format (#243). Keyed on the clean core
# suffix the parse yields (#244): the compression/archive variants (.vcf.gz,
# .fastq.gz, .fast5.tar.gz, ...) collapse to their core at parse time, so a
# single core key (.vcf) covers every compressed spelling. Formats the
# size-threshold assay rules must tell apart stay distinct (.bam vs .cram).
# Seeded with the core sequencing formats; core extensions with no clean
# canonical collapse are absent, so their format is None until a migrating group
# adds its identity (see Format). Keys are lower-case: extension_to_format lowers
# its argument before the lookup.
EXTENSION_TO_FORMAT: dict[str, Format] = {
    ".bam": Format.BAM,
    ".cram": Format.CRAM,
    ".sam": Format.SAM,
    ".vcf": Format.VCF,
    ".bcf": Format.BCF,
    ".gvcf": Format.GVCF,
    ".g.vcf": Format.GVCF,
    ".fastq": Format.FASTQ,
    ".fq": Format.FASTQ,
    ".fasta": Format.FASTA,
    ".fa": Format.FASTA,
    ".bed": Format.BED,
    ".gfa": Format.GFA,
    ".rgfa": Format.RGFA,
}

# Extension -> file-type category. Hoisted in-code from unified_rules.yaml (#252)
# — the last YAML-loaded parse vocabulary. Keyed only on *clean cores* (#245): the
# compression/archive spellings (.vcf.gz, .fast5.tar.gz, ...) were pruned once the
# parse peels every wrapper before recognizing the core, so the compound keys were
# unreferenced. Archive containers (.tar, .tar.gz, .zip) are not cores — they carry
# no content format of their own (#245). The parse consumes only these *keys* (via
# CORE_EXTENSIONS); the category values feed get_file_type and the when.file_format
# validation (#114).
EXTENSION_MAP: dict[str, str] = {
    ".bam": "alignment",
    ".cram": "alignment",
    ".sam": "alignment",
    ".vcf": "variant",
    ".bcf": "variant",
    ".gvcf": "variant",
    ".fastq": "reads",
    ".fq": "reads",
    ".bed": "intervals",
    ".narrowpeak": "intervals",
    ".broadpeak": "intervals",
    ".bigwig": "signal",
    ".bw": "signal",
    ".bedgraph": "signal",
    ".bai": "index",
    ".crai": "index",
    ".tbi": "index",
    ".csi": "index",
    ".fai": "index",
    ".idx": "index",
    ".pbi": "index",
    ".md5": "checksum",
    ".pgen": "genotype_plink",
    ".pvar": "genotype_plink",
    ".psam": "genotype_plink",
    ".h5ad": "single_cell_matrix",
    ".loom": "single_cell_matrix",
    ".mtx": "single_cell_matrix",
    ".idat": "methylation_array",
    ".fast5": "nanopore",
    ".pod5": "nanopore",
    ".svs": "histology_image",
    ".tiff": "image",
    ".tif": "image",
    ".png": "image",
    ".jpg": "image",
    ".fasta": "sequence",
    ".fa": "sequence",
    ".gfa": "pangenome",
    ".rgfa": "pangenome",
    ".gbz": "pangenome",
    ".vg": "pangenome",
    ".gbwt": "pangenome",
    ".xg": "pangenome",
    ".sf": "quantification",
    ".txt": "text_ambiguous",
    ".tsv": "text_ambiguous",
    ".csv": "text_ambiguous",
    ".log": "log_file",
}


def _peel_wrappers(token: str) -> tuple[str, tuple[str, ...]]:
    """Peel *every* trailing container/compression ``WRAPPER_SUFFIXES`` off ``token``.

    Peels longest-first and returns ``(remainder, wrappers)`` with the wrappers in
    name order: ``notes.txt.gz`` -> (``notes.txt``, ``(".gz",)``); ``run.fast5.tar.gz``
    -> (``run.fast5``, ``(".tar", ".gz")``); ``graph.tar.gz`` -> (``graph``, ``(".tar",
    ".gz")``). Containers are always stripped — the caller then recognizes whatever
    core the remainder ends with (#245).
    """
    rest = token
    wrappers: list[str] = []
    while True:
        for suffix in WRAPPER_SUFFIXES:
            if rest.endswith(suffix):
                wrappers.append(suffix)
                rest = rest[: -len(suffix)]
                break
        else:
            break
    wrappers.reverse()  # name order: ".tar.gz" -> (".tar", ".gz")
    return rest, tuple(wrappers)


# The explicit set of producible core extensions (#249). The single source of
# truth for which clean core suffixes the parse can yield, once every container
# wrapper is peeled (#245). Derived from the single-dot ``EXTENSION_MAP`` keys and
# the ``EXTENSION_TO_FORMAT`` keys (a format-mapped extension is a producible core
# by definition — and the only multi-dot core, ``.g.vcf``, lives there). Lower-cased,
# since recognition matches a lower-cased name.
CORE_EXTENSIONS: frozenset[str] = frozenset(
    {k.lower() for k in EXTENSION_MAP if k.count(".") == 1} | {k.lower() for k in EXTENSION_TO_FORMAT}
)

# The cores with more than one dot (e.g. ``.g.vcf``), longest-first — the only
# cores a last-dot-token lookup cannot recognize, so the parse scans just these
# before the O(1) single-dot lookup; longest-first lets a multi-dot core win
# over a shorter multi-dot tail.
_MULTI_DOT_CORES: tuple[str, ...] = tuple(
    sorted((c for c in CORE_EXTENSIONS if c.count(".") > 1), key=len, reverse=True)
)


def extension_to_format(extension: str | None) -> Format | None:
    """Derive the canonical :class:`Format` for an extension (#243).

    The stage-1 derivation — from the extension alone, no I/O. Returns ``None``
    when the extension is ``None`` or maps to no seeded format
    (``EXTENSION_TO_FORMAT``), so an unmapped or absent extension leaves the
    format honestly unresolved rather than guessed.
    """
    if extension is None:
        return None
    return EXTENSION_TO_FORMAT.get(extension.lower())


@dataclass(frozen=True)
class FileName:
    """A filename parsed into its parts.

    ``raw`` is the name as given. In the pipeline it is never empty — the input
    contract (``^.+$``) diverts a nameless record to ``validation_failed`` before
    it is parsed — though ``FileName`` itself does not re-validate. ``extension``
    is the clean core suffix the rules key on (``.vcf``, not ``.vcf.gz``), or
    ``None`` when the name carries no known extension — never a junk last-dot
    suffix (``"hprc-v1.0-mc-grch38"`` has no extension, not ``".0-mc-grch38"``).
    ``wrappers`` are the trailing compression/archive
    suffixes split off that core, in name order (#244: ``sample.vcf.gz`` →
    extension ``.vcf``, wrappers ``(".gz",)``). ``stem`` is the token-carrying
    part: the name with its whole recognized extension (core + wrappers) removed,
    or — when there is none — its trailing ``wrappers`` stripped (an unknown
    suffix like ``.xyz`` is kept, since it is neither a known extension nor a
    wrapper).

    ``format`` is the derived canonical format (see :class:`Format`), ``None``
    when the extension maps to no seeded format (or there is no known extension).
    ``format_source`` records how it was derived — ``FormatSource.EXTENSION`` for
    the stage-1 (extension-only) derivation, ``None`` when ``format`` is
    unresolved. As built by :meth:`parse` the two move together — both set or both
    ``None`` — though ``FileName`` itself does not enforce that of a
    directly-constructed instance.
    """

    raw: str
    stem: str
    extension: str | None
    wrappers: tuple[str, ...]
    format: Format | None = None
    format_source: FormatSource | None = None

    # The nameless FileName — a header-only call with no filename. Assigned below the
    # class; ``raw`` is "" and ``extension`` is None. Its *extension* is None like any
    # name with no known extension, so extension-based readers (the file_format
    # fallback in classify_extended) treat "no name" and "unrecognized name"
    # uniformly. It differs in ``raw``: an unrecognized-but-present name keeps its
    # truthy raw and still matches filename_pattern rules, whereas the sentinel's ""
    # matches none — exactly the header-only intent. Threading it as the "no name"
    # value avoids a ``FileName | None`` branch at every reader.
    EMPTY: ClassVar["FileName"]

    @classmethod
    def parse(cls, filename: str) -> "FileName":
        """Parse ``filename`` into a :class:`FileName` against the in-code vocabulary.

        Pure — no ``UnifiedRules`` instance (#252). Recognition is "peel every
        container, then recognize the core underneath" (#245): strip all trailing
        ``WRAPPER_SUFFIXES`` (compression/archive), then match the remainder against
        the known cores — multi-dot cores (``.g.vcf``) scanned longest-first so one
        wins over its shorter tail (``.vcf``), then an O(1) lookup of the last
        dot-token against ``CORE_EXTENSIONS``. An archive with no inner format
        (``graph.tar.gz`` → the remainder ``graph`` has no known core) yields
        ``extension=None`` with ``.tar``/``.gz`` recorded as wrappers, because a
        container carries no content format of its own. ``format`` is the stage-1
        derivation from the core (``extension_to_format``), with ``format_source``
        recording the provenance — set together or both ``None``.
        """
        # Peel every trailing container/compression wrapper first, then recognize
        # the core the wrapper-stripped remainder ends with. Recognition runs against
        # the lowercased name; the stem is sliced by ASCII suffix length below, so it
        # does not rely on lowercasing preserving length (see the stem computation).
        base, wrappers = _peel_wrappers(filename.lower())

        extension = None
        for core in _MULTI_DOT_CORES:
            if base.endswith(core):
                extension = core
                break
        else:
            if "." in base:
                simple = "." + base.rsplit(".", 1)[-1]
                if simple in CORE_EXTENSIONS:
                    extension = simple

        # The stem is the original-case name minus its recognized suffix (wrappers +
        # core), so it carries only the name's tokens. Slice by the ASCII suffix
        # lengths off the *original* name rather than by ``len(base)``: ``str.lower()``
        # is not guaranteed to preserve length for every Unicode char (e.g. ``"İ"``),
        # but the wrappers and core are ASCII, so their lengths index the original
        # name correctly regardless.
        suffix_len = sum(len(w) for w in wrappers) + len(extension or "")
        stem = filename[: len(filename) - suffix_len]

        fmt = extension_to_format(extension)
        format_source = FormatSource.EXTENSION if fmt is not None else None
        return cls(
            raw=filename,
            stem=stem,
            extension=extension,
            wrappers=wrappers,
            format=fmt,
            format_source=format_source,
        )


FileName.EMPTY = FileName.parse("")
