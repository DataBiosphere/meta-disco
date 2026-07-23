"""The parsed filename fact and the extension vocabulary it parses against.

A file's name answers several unrelated questions at once — what tokens it
carries (`rnaseq`, `chm13`), what its extension is, whether it is compressed or
archived, and what file *format* it therefore is. ``FileName`` parses those
apart so a caller reads a structured fact instead of re-deriving from a raw
string (epic #242).

``FileName`` is a pure data type and its parse is a **pure function**:
``FileName.parse(name)`` needs no loaded ``UnifiedRules`` — the whole extension
vocabulary (``COMPOUND_EXTENSIONS`` / ``WRAPPER_SUFFIXES`` / ``EXTENSION_TO_FORMAT``
/ ``EXTENSION_MAP`` and the derived ``CORE_EXTENSIONS``) lives here in-code as a
self-contained leaf (#252). ``extension`` is syntactic — the exact core suffix,
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

# Compound extensions in priority order (longest first).
COMPOUND_EXTENSIONS: tuple[str, ...] = (
    ".g.vcf.gz",  # Must come before .vcf.gz
    ".gvcf.gz",
    ".vcf.gz",
    ".fastq.gz",
    ".fq.gz",
    ".fasta.gz",
    ".fa.gz",
    ".bed.gz",
    ".sam.gz",
    ".rgfa.gz",
    ".gfa.gz",
    ".fast5.tar.gz",  # Must come before .tar.gz
    ".fast5.tar",  # Must come before .tar
    ".tar.gz",
    ".mtx.gz",
)

# Compression and archive suffixes — "wrappers" around the format, not the
# format itself. Since #244 these do the real work of the extension/format
# split: the parse splits a recognized extension token into its clean core
# suffix and these trailing wrappers (".vcf.gz" -> ".vcf" + (".gz",)). Ordered
# longest-first: the split/peel loop takes the first `endswith` match, so `.bgz`
# must precede `.gz` or a `.bgz` token would mis-peel as `.gz` and leave a
# dangling `b` on the core.
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
# — the last YAML-loaded parse vocabulary. Still carries the compound spellings
# (.vcf.gz, ...) that #249 deferred pruning to #245 (they back filename_for_rules'
# fallback). The parse consumes only its *keys* (via CORE_EXTENSIONS); the
# category values feed get_file_type and the when.file_format validation (#114).
EXTENSION_MAP: dict[str, str] = {
    ".bam": "alignment",
    ".cram": "alignment",
    ".sam": "alignment",
    ".sam.gz": "alignment",
    ".vcf": "variant",
    ".vcf.gz": "variant",
    ".bcf": "variant",
    ".gvcf": "variant",
    ".gvcf.gz": "variant",
    ".g.vcf.gz": "variant",
    ".fastq": "reads",
    ".fq": "reads",
    ".fastq.gz": "reads",
    ".fq.gz": "reads",
    ".bed": "intervals",
    ".bed.gz": "intervals",
    ".narrowpeak": "intervals",
    ".broadpeak": "intervals",
    ".bigwig": "signal",
    ".bw": "signal",
    ".bigWig": "signal",
    ".bedGraph": "signal",
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
    ".mtx.gz": "single_cell_matrix",
    ".idat": "methylation_array",
    ".fast5": "nanopore",
    ".pod5": "nanopore",
    ".fast5.tar": "nanopore",
    ".fast5.tar.gz": "nanopore",
    ".svs": "histology_image",
    ".tiff": "image",
    ".tif": "image",
    ".png": "image",
    ".jpg": "image",
    ".fasta": "sequence",
    ".fa": "sequence",
    ".fasta.gz": "sequence",
    ".fa.gz": "sequence",
    ".gfa": "pangenome",
    ".gfa.gz": "pangenome",
    ".rgfa": "pangenome",
    ".rgfa.gz": "pangenome",
    ".gbz": "pangenome",
    ".vg": "pangenome",
    ".gbwt": "pangenome",
    ".xg": "pangenome",
    ".tar": "archive",
    ".tar.gz": "archive",
    ".zip": "archive",
    ".sf": "quantification",
    ".txt": "text_ambiguous",
    ".tsv": "text_ambiguous",
    ".csv": "text_ambiguous",
    ".log": "log_file",
}


def _peel_wrappers(token: str, *, keep_last: bool) -> tuple[str, tuple[str, ...]]:
    """Peel trailing compression/archive ``WRAPPER_SUFFIXES`` off ``token``.

    Peels longest-first and returns ``(remainder, wrappers)`` with the wrappers
    in name order. ``keep_last`` chooses between the two uses:

    - ``keep_last=True`` splits a *recognized* extension token into its core and
      wrappers, stopping before the last remaining token so an archive extension
      keeps its own suffix: ``.vcf.gz`` -> (``.vcf``, ``(".gz",)``);
      ``.fast5.tar.gz`` -> (``.fast5``, ``(".tar", ".gz")``); ``.tar.gz`` ->
      (``.tar``, ``(".gz",)``); ``.tar`` -> (``.tar``, ``()``).
    - ``keep_last=False`` peels *every* trailing wrapper off an unrecognized
      name, where no core is claimed and the remainder is only used to trim the
      stem: ``notes.txt.gz`` -> (``notes.txt``, ``(".gz",)``).
    """
    rest = token
    wrappers: list[str] = []
    while True:
        for suffix in WRAPPER_SUFFIXES:
            if rest.endswith(suffix) and not (keep_last and rest == suffix):
                wrappers.append(suffix)
                rest = rest[: -len(suffix)]
                break
        else:
            break
    wrappers.reverse()  # name order: ".tar.gz" -> (".tar", ".gz")
    return rest, tuple(wrappers)


# The explicit set of producible core extensions (#249). The single source of
# truth for which clean core suffixes the parse can yield. Derived from every
# in-code source of core truth, so it cannot drift: every compound extension
# wrapper-stripped (which is where the multi-dot core ``.g.vcf`` comes from —
# ``peel(".g.vcf.gz")``), the single-dot ``EXTENSION_MAP`` keys, and the
# ``EXTENSION_TO_FORMAT`` keys (a format-mapped extension is a producible core by
# definition). Lower-cased, since recognition matches a lower-cased name.
CORE_EXTENSIONS: frozenset[str] = frozenset(
    {_peel_wrappers(c, keep_last=True)[0] for c in COMPOUND_EXTENSIONS}
    | {k.lower() for k in EXTENSION_MAP if k.count(".") == 1}
    | {k.lower() for k in EXTENSION_TO_FORMAT}
)

# The cores with more than one dot (e.g. ``.g.vcf``), longest-first — the only
# cores a last-dot-token lookup cannot recognize, so the parse scans just these
# before the O(1) single-dot lookup; longest-first lets a multi-dot core win
# over a shorter multi-dot tail.
_MULTI_DOT_CORES: tuple[str, ...] = tuple(
    sorted((c for c in CORE_EXTENSIONS if c.count(".") > 1), key=len, reverse=True)
)


def extract_extension(filename: str) -> str:
    """Extract the file extension, handling compound extensions.

    The legacy compound-or-junk extractor (returns the whole compound ``.vcf.gz``,
    or the junk last-dot suffix for an unknown name). Kept for the record-routing
    / ``filename_for_rules`` path that still works on raw names; the rule-matching
    path uses :meth:`FileName.parse` (clean core + wrappers) instead.
    """
    filename_lower = filename.lower()

    # Check compound extensions first (in priority order)
    for ext in COMPOUND_EXTENSIONS:
        if filename_lower.endswith(ext):
            return ext

    # Fall back to simple extension
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    return ""


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
    ``None`` when the name carries no known extension — never the junk last-dot
    suffix ``extract_extension`` returns (``"hprc-v1.0-mc-grch38"`` →
    ``".0-mc-grch38"``). ``wrappers`` are the trailing compression/archive
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

    @classmethod
    def parse(cls, filename: str) -> "FileName":
        """Parse ``filename`` into a :class:`FileName` against the in-code vocabulary.

        Pure — no ``UnifiedRules`` instance (#252). Recognition is a wrapper-bearing
        ``COMPOUND_EXTENSIONS`` match, else the known core the name ends with — the
        multi-dot cores scanned longest-first, then an O(1) lookup of the single-dot
        last token (#249); an unknown suffix yields ``None`` here, where
        ``extract_extension`` returns the junk last-dot suffix (which matched no rule
        anyway). #244 made the *representation* a clean core ``extension`` (``.vcf``)
        plus the ``wrappers`` it bundled (``(".gz",)``), not the whole compound
        (``.vcf.gz``); #249 made the core set explicit, which also lets a multi-dot
        core be recognized in its uncompressed spelling (``sample.g.vcf`` →
        ``.g.vcf``, matching the compressed ``.g.vcf.gz`` form). ``format`` is the
        stage-1 derivation from the core extension (``extension_to_format``), with
        ``format_source`` recording the provenance — set together or both ``None``.
        """
        lower = filename.lower()

        recognized = None
        for ext in COMPOUND_EXTENSIONS:
            if lower.endswith(ext):
                recognized = ext
                break
        if recognized is None:
            # No wrapper-bearing compound matched — recognize the known core the
            # name ends with (#249). Multi-dot cores (".g.vcf") are scanned first,
            # longest-first, so one wins over its shorter tail (".vcf"); the common
            # single-dot case is then an O(1) lookup of the last dot-token. Every
            # core's leading dot makes both a genuine extension-boundary match, so
            # the single-dot path is equivalent to the old extension_map gate and
            # only the multi-dot scan is new (an uncompressed ".g.vcf").
            for core in _MULTI_DOT_CORES:
                if lower.endswith(core):
                    recognized = core
                    break
            else:
                if "." in filename:
                    simple = "." + filename.rsplit(".", 1)[-1].lower()
                    if simple in CORE_EXTENSIONS:
                        recognized = simple

        if recognized is not None:
            # Split the recognized token into its clean core and wrappers (#244).
            # The stem drops the whole recognized token (core + wrappers), so it
            # carries only the name's tokens — unchanged from before the split.
            extension, wrappers = _peel_wrappers(recognized, keep_last=True)
            stem = filename[: -len(recognized)]
        else:
            # No known extension: peel every trailing wrapper as informational
            # advice and strip them from the stem, but claim no core extension.
            extension = None
            _, wrappers = _peel_wrappers(lower, keep_last=False)
            wrapper_len = sum(len(w) for w in wrappers)
            stem = filename[:-wrapper_len] if wrapper_len else filename

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
