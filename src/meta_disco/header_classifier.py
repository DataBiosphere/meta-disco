"""BAM/CRAM, VCF, FASTQ, FASTA, BED and IDAT header-based classification.

This module provides functions to classify sequencing files based on their headers.
The actual classification rules are defined in the bundled unified_rules.yaml
(package data of meta_disco.rules) and executed by the RuleEngine. This module provides:

1. Public API functions (classify_from_header, classify_from_vcf_header, etc.)
2. Re-exports of read name parsers from validators.read_name_parsers
"""

import re
from dataclasses import dataclass, fields, replace
from functools import cache
from typing import TYPE_CHECKING

from . import code_rules
from .evidence import BedSignals, IdatHeader, SegmentTag
from .file_name import FileName
from .models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_CONTENT_READ,
    SOURCE_CONTIG_DETECTION,
    all_not_classified,
    build_field_entry,
)
from .producer_steps import producing_step
from .schema_vocab import most_specific
from .validators.header_extractors import VCFHeader, VcfRecord, parse_vcf_header
from .validators.read_name_parsers import (
    detect_paired_end_indicators,
    extract_archive_accession,
    parse_illumina_read_name,
    parse_ont_read_name,  # noqa: F401  re-exported for backward compat
    parse_pacbio_read_name,
)

if TYPE_CHECKING:
    from .rule_engine import RuleEngine

# Text GFA formats this module can parse. The other graph extensions the
# `pangenome` rules cover (.gbz, .vg, .gbwt, .xg) are binary vg/GBWT formats.
# GFA_CONFIG.extensions is this same tuple — the file-type routing filter.
GRAPH_TEXT_EXTENSIONS = (".gfa", ".gfa.gz", ".rgfa", ".rgfa.gz")


@dataclass(frozen=True)
class FastqReadMetadata:
    """FASTQ-specific scalar metadata spliced into a classification result.

    The four scalars ``classify_from_fastq_header`` derives while inspecting a
    file's reads: the paired-end flag (from read names, falling back to the
    filename), the Illumina instrument hint, and the ENA/SRA archive accession and
    source. The instrument *model* is not among them: it is the ``instrument_model``
    dimension, and no rule reads it from a read name (#532). Both build sites in
    that function construct this and call ``merge_into``, so the key set is
    declared in one place instead of two literals that must be kept in sync.
    """

    is_paired_end: bool | None = None
    instrument_hint: str | None = None
    archive_accession: str | None = None
    archive_source: str | None = None

    def merge_into(self, classifications: dict) -> None:
        """Splice the fields into ``classifications`` as flat scalar keys.

        Mutates the passed dict (not ``self``). Keys are derived from the field
        list, so the merged key set cannot drift from the declared fields (the
        ``records.py`` ``to_dict`` convention). The scalars are stored flat — not
        as ``{value, status, evidence}`` entries — because that is how
        ``models.field_value`` reads them and what keeps the output byte-identical.
        """
        classifications.update({f.name: getattr(self, f.name) for f in fields(self)})


@cache
def _get_engine() -> "RuleEngine":
    """Get a cached RuleEngine instance (avoids re-parsing YAML on every call)."""
    from .rule_engine import RuleEngine

    return RuleEngine()


# =============================================================================
# PUBLIC API FUNCTIONS
# =============================================================================


def _add_contig_claim(result, rule_id: str, family: str, matches: int, identity) -> None:
    """Add the contig-detection ``reference_assembly`` claim, at ``CONTENT_TIER``.

    ``family`` is what the contig lengths detected; the claim's value is
    :func:`~.validators.reference_builds.assembly_term` of it: the resolved build's
    term where the build lies inside that family and has one (a CHM13 release or
    hybrid), and ``family`` otherwise (#473). The reason names both readings when they differ, so the evidence says
    which build turned ``CHM13`` into a release.
    """
    from .rule_engine import CONTENT_TIER
    from .validators.reference_builds import assembly_term

    value = assembly_term(family, identity)
    reason = f"Reference {family} detected from {matches} matching contig lengths (definitive)"
    if value != family:
        reason += f"; the header's build is {family} {identity.version}"
    result.add_claim(
        "reference_assembly",
        rule_id=rule_id,
        tier=CONTENT_TIER,
        source_type=SOURCE_CONTIG_DETECTION,
        reason=reason,
        value=value,
    )


def _record_reference_build(result, identity) -> None:
    """Attach the observed reference build to ``reference_assembly``'s detail (#340).

    "Observed" is the precise word: the build is emitted whenever anything
    survives into the identity — a derived ``base``/``version``, an observed
    key-contig checksum, or a declared reference name — and ``base``/``version``
    are null there if nothing resolved. A contig *length* is evidence for
    resolution but is not itself recorded, so a length-only header that
    resolves nothing carries no build at all (issue #349).

    The dimension is named here, in the classifier that observed the build,
    rather than in the generic output assembler — ``build_field_entry`` and
    ``to_output_dict`` stay dimension-agnostic.

    An identity with nothing in it is dropped rather than recorded: an object
    whose every member is null says nothing while looking like an answer, and the
    entry should simply carry no build.

    Where the derived family disagrees with the coarse value, both derivations
    are withheld and only the observations are kept — see
    :func:`_reconcile_with_coarse_value`.
    """
    if identity.is_empty():
        return
    identity = _reconcile_with_coarse_value(result, identity)
    if identity.is_empty():
        return
    result.field_detail["reference_assembly"] = {"build": identity.to_dict()}


def _reconcile_with_coarse_value(result, identity):
    """Drop a derived build that contradicts the resolved ``reference_assembly``.

    The build is compared by its own term (:func:`assembly_term` of its family,
    #473): it agrees with the value when the two nest, as
    :func:`~.schema_vocab.most_specific` has it — one is the other or an ``is_a``
    ancestor of it. A ``T2T-CHM13v2.0`` build agrees with a ``T2T-CHM13v2.0``
    value and with a ``CHM13`` one a filename rule set; a v2.0 build under a
    ``T2T-CHM13v1.0`` value would not.

    The family and the build are derived independently — the family by
    ``contig_lengths``' fuzzy match, the build by exact signature matching — and
    they can disagree; the value is then the family alone, since
    :func:`assembly_term` takes the build's term only inside the detected family. The case that shows up in this corpus is a
    chrY-only header from the CHM13 build carrying a *grafted GRCh38 chrY*: the
    coarse detector sees only that borrowed chrY and says GRCh38, while the
    signature and declared name identify the CHM13 build it actually belongs to.

    The resolver is the better answer there, but it only ever refines the family
    the contig lengths detected (#473) and never replaces it. Emitting both would
    publish a record asserting two families at once, which is worse than
    publishing neither. So the derivations are dropped and the *observations* —
    the checksums seen and the name declared — are kept, exactly as they are for
    any other ambiguity: the evidence survives for a later pass, and nothing
    contradictory is asserted now.

    The underlying gap is in the coarse detector, which cannot tell a genome
    from one that borrowed its chrY — issue #345. When that is fixed this
    reconciliation becomes dead code and should be removed with it: a record that
    cannot contradict itself needs no guard against contradiction.
    """
    from .validators.reference_builds import assembly_term

    coarse = result.reference_assembly
    if identity.base is None or coarse is None:
        return identity
    if most_specific("reference_assembly", {assembly_term(identity.base, identity), coarse}) is not None:
        return identity
    return replace(identity, base=None, version=None)


def classify_from_header(
    header_text: str,
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Classify data modality and reference from BAM header text.

    This function uses the RuleEngine with rules from unified_rules.yaml
    to classify BAM/CRAM files based on their headers.

    Args:
        header_text: Raw SAM/BAM header text (lines starting with @)
        name: Optional parsed :class:`FileName`; its tokens (`hifi`, `.flnc.`,
            STAR output names, reference names) drive the tier-2 filename rules
        file_size: Optional file size in bytes, for `file_size_*` rule
            conditions; no rule declares one (#430)
        file_format: Optional file format string (e.g., ".bam", ".cram");
            accepted for call uniformity but not consulted — the extension is
            hardcoded ".bam" below

    Returns:
        Dict with per-field classifications:
            - {field}: {value, status, evidence[]} for each of
              data_modality, data_type, assay_type, reference_assembly, platform,
              instrument_model
    """
    from .rule_engine import ExtendedFileInfo

    # Use the real filename so its tokens reach the tier-2 filename rules. The
    # AnVIL file_format is redundant with the name and not consulted (#157). When
    # there is no name (a header-only call), the engine reads the extension from
    # the file_format we set — the known ".bam" — instead of a fabricated name.
    file_info = ExtendedFileInfo(
        name=name,
        file_format=".bam",
        file_size=file_size,
        bam_header=header_text,
    )

    # One parse per file (#488): file_info owns it, the engine's tier-3 matchers
    # read the same one, and the contig-length detector and the build resolver
    # share one observation of its @SQ dictionary.
    from .validators.contig_lengths import detect_reference_from_contigs
    from .validators.reference_builds import observe_sam_header, resolve_identity

    signatures, declared = observe_sam_header(file_info.parsed_bam_header)

    # Detect reference from contig lengths first — definitive signal
    contig_ref, contig_matches = detect_reference_from_contigs((s.name, s.length) for s in signatures)

    # Run classification with tier 3 (header rules)
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=True)

    # Resolve the specific build behind the family (#340). Runs whatever the
    # contig detection concluded, including when it concluded nothing — an
    # unresolvable file still keeps its observed checksums so a later table row can
    # resolve it without re-fetching.
    identity = resolve_identity(signatures, declared)

    # Apply contig-based reference. Read from the @SQ contig lengths, so it lands
    # at CONTENT_TIER and out-ranks any disagreeing filename/header rule; add_claim
    # re-resolves from the full list, so a filename_ref rule stays in the evidence
    # chain rather than being clobbered (#226/#227). The value is the
    # resolved build's term where the build lies inside the detected family and has
    # one (CHM13's releases and hybrids), and the family otherwise (#473) — one
    # claim, so the two readings of one header never compete at the same tier.
    if contig_ref:
        _add_contig_claim(result, code_rules.CONTIG_LENGTH_DETECTION.id, contig_ref, contig_matches, identity)
        # No modality claim follows from the contigs: DNA and RNA reads aligned to
        # one genome share its @SQ dictionary, so "aligned to a genome" does not say
        # which the reads are. The "genomic" guess this used to make is removed (#88).

    _record_reference_build(result, identity)

    return result.to_output_dict()


def classify_from_vcf_header(
    header: "str | VCFHeader",
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Classify a VCF file based on header content; also a PLINK 2 ``.pvar``, whose ``##``
    header is a VCF's (#561).

    This function uses the RuleEngine with rules from unified_rules.yaml
    to classify VCF files based on their headers.

    Args:
        header: The VCF header, parsed (the pipeline's one parse per file, which
            its step reader shares, #615) or as text (lines starting with ##),
            which is parsed here
        name: Optional parsed :class:`FileName`; its tokens (e.g. a chm13 assembly
            hint) drive the tier-2 filename rules
        file_size: Optional file size in bytes
        file_format: Optional file format string (e.g., ".vcf", ".vcf.gz");
            accepted for call uniformity but not consulted — the extension is
            hardcoded ".vcf.gz" below

    Returns:
        Dict with per-field classifications:
            - {field}: {value, status, evidence[]} for each of
              data_modality, data_type, assay_type, reference_assembly, platform,
              instrument_model
    """
    from .rule_engine import CONTENT_TIER, ExtendedFileInfo

    # Use the real filename so its tokens reach the tier-2 filename rules. The
    # AnVIL file_format is redundant with the name and not consulted (#157). When
    # there is no name (a header-only call), the engine reads the extension from
    # the file_format we set — the known ".vcf.gz" — instead of a fabricated name.
    parsed = parse_vcf_header(header) if isinstance(header, str) else header
    file_info = ExtendedFileInfo(
        name=name,
        file_format=".vcf.gz",
        file_size=file_size,
        vcf_header=parsed,
    )

    # One parse per file (#488): file_info holds it, the engine's tier-3 matcher
    # reads the same one, the contig-length detector takes the observed contigs
    # rather than re-splitting the raw text, and the build resolver takes the same
    # observation instead of parsing a third time.
    from .validators.contig_lengths import detect_reference_from_contigs
    from .validators.reference_builds import observe_vcf_header, resolve_identity

    signatures, declared = observe_vcf_header(parsed)

    # Detect reference from contig lengths — definitive signal, no guessing.
    contig_ref, contig_matches = detect_reference_from_contigs((s.name, s.length) for s in signatures)

    # Run classification with tier 3 (header rules)
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=True)

    # Resolve the specific build (#340) — see the BAM path. VCF gives the resolver
    # less to work with than BAM does: ##contig carries no checksum, so builds that
    # differ only in sequence stay ambiguous here and resolve to a null version
    # rather than a guess, which leaves the family as the value.
    identity = resolve_identity(signatures, declared)

    # Apply contig-based reference. Read from the ##contig lengths, so it lands at
    # CONTENT_TIER and out-ranks any disagreeing filename/header rule; add_claim
    # re-resolves from the full list (#226/#227). The value is the build's term
    # where it resolved inside the family and has one (#473), as on the BAM path.
    if contig_ref:
        _add_contig_claim(result, code_rules.VCF_CONTIG_LENGTH.id, contig_ref, contig_matches, identity)

    _record_reference_build(result, identity)

    structural_reason = why_structural(parsed)
    if structural_reason is not None:
        result.add_claim(
            "data_type",
            rule_id=code_rules.VCF_RECORDS_STRUCTURAL.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTENT_READ,
            reason=structural_reason,
            value=STRUCTURAL_DATA_TYPE,
        )
    small_variants_reason = why_small_variants(parsed)
    if small_variants_reason is not None:
        result.add_claim(
            "data_type",
            rule_id=code_rules.VCF_RECORDS_SMALL_VARIANTS.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTENT_READ,
            reason=small_variants_reason,
            value=VARIANTS_DATA_TYPE,
        )

    gvcf_reason = why_gvcf(parsed, name.raw)
    if gvcf_reason is not None:
        result.add_claim(
            "data_type",
            rule_id=code_rules.VCF_GVCF.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTENT_READ,
            reason=gvcf_reason,
            value=GVCF_DATA_TYPE,
        )

    return result.to_output_dict()


# A gVCF's data_type (#607); the HaplotypeCaller modes that write one, GVCF (reference
# blocks) and BP_RESOLUTION (a record per position); and the ALT allele a gVCF's every
# record carries.
GVCF_DATA_TYPE = "variants.germline.gvcf"
GVCF_MODES = frozenset({"GVCF", "BP_RESOLUTION"})
NON_REF = "<NON_REF>"


def why_gvcf(header: VCFHeader, file_name: str) -> str | None:
    """Why ``file_name`` is a gVCF, for the claim's reason; None where its header and records do not both say so.

    Both must: the step that made the file, the end of the header's data flow
    (``producer_steps.producing_step``), is a HaplotypeCaller in one of :data:`GVCF_MODES`
    (``Step.mode``); and every record the head read (``VCFHeader.records``) has
    ``<NON_REF>`` among its ALT alleles, and one at least has it alone: a record of a site
    with no variant, which a gVCF has and a VCF filtered to its variant sites does not. The header's ``##ALT=<ID=NON_REF>`` and
    ``##GVCFBlock`` lines, and a GVCF-mode line of an earlier step, are not read: joint-called
    VCFs and ``.pvar`` files carry them over from their gVCFs. None for an empty
    ``file_name`` (a header-only call), which no step's output can be checked against, and
    for a header whose records were not read.
    """
    if not file_name or not header.records:
        return None
    step, _ = producing_step(header, file_name)
    if step is None or step.tool != "HaplotypeCaller" or step.mode not in GVCF_MODES:
        return None
    if not all(NON_REF in record.alts for record in header.records):
        return None
    non_variant = sum(record.alt == NON_REF for record in header.records)
    if not non_variant:
        return None
    return (
        f"made by HaplotypeCaller in {step.mode} mode, as its header's command line records; each of "
        f"its first {len(header.records)} records has {NON_REF} among its ALT alleles, and "
        f"{non_variant} of them are sites with no variant ({NON_REF} alone)"
    )


# The data_type of a VCF whose records read are all structural variants, and of one whose
# header declares structural-variant INFO fields but whose records include a small variant
# (#630); the INFO fields that declaration names; and the ALT alleles that are no variant
# (a spanning deletion's ``*``, no ALT ``.``, and a gVCF's reference-confidence alleles).
STRUCTURAL_DATA_TYPE = "variants.structural"
VARIANTS_DATA_TYPE = "variants"
SV_INFO_IDS = frozenset({"SVTYPE", "SVLEN", "CIPOS", "CIEND", "MATEID", "IMPRECISE"})
NO_VARIANT_ALLELES = frozenset({"*", ".", NON_REF, "<*>"})


def is_declared_sv(record: VcfRecord, allele: str) -> bool:
    """Whether ``allele`` of ``record`` is a structural variant its caller declared as one.

    Declared: the record's INFO has ``SVTYPE``, or the allele is symbolic (``<DEL>``), a
    breakend joined to another position (``G]17:198982]``), or a single breakend (``G.``,
    ``.G``). An allele's length is not read: small-variant callers write long indels too (#630).
    """
    if "SVTYPE" in record.info_keys:
        return True
    if allele.startswith("<") and allele.endswith(">"):
        return True
    if "[" in allele or "]" in allele:
        return True
    return len(allele) > 1 and (allele.startswith(".") or allele.endswith("."))


def allele_counts(header: VCFHeader) -> tuple[int, int]:
    """How many ALT alleles of the records a VCF's head read are declared structural variants, and how many small (#630).

    Each allele is a declared structural variant (:func:`is_declared_sv`), no variant
    (:data:`NO_VARIANT_ALLELES`, not counted), or a small variant. ``(0, 0)`` where no record was read.
    """
    structural = small = 0
    for record in header.records or ():
        for allele in record.alts:
            if allele in NO_VARIANT_ALLELES:
                continue
            if is_declared_sv(record, allele):
                structural += 1
            else:
                small += 1
    return structural, small


def why_structural(header: VCFHeader) -> str | None:
    """Why a VCF is ``variants.structural``, for the claim's reason; None unless every allele counted in the records read is a declared structural variant (#630)."""
    structural, small = allele_counts(header)
    if not structural or small:
        return None
    return (
        f"each of the {structural} alleles in its first {len(header.records or ())} records is a structural "
        "variant its caller declared: a symbolic ALT, a breakend, or SVTYPE in INFO"
    )


def why_small_variants(header: VCFHeader) -> str | None:
    """Why a VCF whose header declares structural-variant INFO fields is ``variants``, for the claim's reason (#630).

    None unless the header declares an INFO field of :data:`SV_INFO_IDS` and the records read
    hold a small variant: such a header says structural variants may appear, and the small
    variant shows the file does not hold them alone.
    """
    _, small = allele_counts(header)
    declared = sorted({info.fields.get("ID", "") for info in header.info_fields or []} & SV_INFO_IDS)
    if not small or not declared:
        return None
    return (
        f"its header declares structural-variant INFO fields ({', '.join(declared)}), but {small} of the "
        f"alleles in its first {len(header.records or ())} records are small variants: no symbolic ALT, "
        "breakend or SVTYPE"
    )


def classify_from_fastq_header(
    reads: list[str],
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Classify FASTQ file based on read names.

    This function uses the RuleEngine with rules from unified_rules.yaml
    to classify FASTQ files based on their read names.

    Args:
        reads: List of read name lines (first few reads from file)
        name: Optional parsed :class:`FileName` for pattern matching
        file_size: Optional file size in bytes

    Returns:
        Dict with:
            - {field}: {value, status, evidence[]} for each of CLASSIFICATION_FIELDS;
              no rule reads ``instrument_model`` from a read name (#532)
            - is_paired_end: bool or None
            - instrument_hint: str or None (instrument ID from read name)
            - archive_accession: str or None (ENA/SRA accession if present)
            - archive_source: str or None (ENA, SRA, DDBJ)
    """
    from .rule_engine import ExtendedFileInfo

    # Handle empty input — no reads to classify. Statuses are known directly, so
    # pass them explicitly to build_field_entry (epic #116 Stage 3 shape).
    # data_type is the classified "reads"; reference_assembly is not_applicable
    # (reads are unaligned), matching the non-empty path (#131); the remaining
    # dimensions are not_classified.
    if not reads or not reads[0]:
        entries = {fld: build_field_entry(None, status=NOT_CLASSIFIED) for fld in CLASSIFICATION_FIELDS}
        entries["data_type"] = build_field_entry("reads", status=CLASSIFIED)
        entries["reference_assembly"] = build_field_entry(None, status=NOT_APPLICABLE)
        FastqReadMetadata().merge_into(entries)
        return entries

    # Get first read for classification
    first_read = reads[0]

    # Check for archive-reformatted reads
    # Archive-reformatted reads look like: @ERR123.1 A00297:44:...
    accession, source, remainder = extract_archive_accession(first_read)

    # Create file info with FASTQ header - try original first. The real filename
    # drives the tier-2 rules; with no name, the engine reads the extension from
    # the known ".fastq.gz" file_format rather than a fabricated name (#152).
    file_info = ExtendedFileInfo(
        name=name,
        file_format=".fastq.gz",
        file_size=file_size,
        fastq_first_read=first_read,
    )

    # Run classification with tier 3 (header rules)
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=True)

    # An archive-reformatted read (@ERR... A00297:...) carries two read names: the
    # archive's and, after the space, the instrument's original. Both are content,
    # and a rule may match either (fastq_illumina_ena_hiseq reads the archive form),
    # so the original is always classified too and its claims resolve by tier with
    # the first pass's — never only when the first found nothing, and never by
    # overwriting it (#88).
    if accession and remainder.strip():
        stripped_read = "@" + remainder.strip()
        file_info_stripped = replace(file_info, fastq_first_read=stripped_read)
        result.merge_claims(engine.classify_extended(file_info_stripped, include_tier3=True))

    # Detect paired-end from read names or filename
    is_paired_end = None
    for read in reads[:10]:
        if detect_paired_end_indicators(read):
            is_paired_end = True
            break
    if is_paired_end is None and name.raw:
        is_paired_end = detect_paired_end_indicators(name.raw)

    # Extract the instrument hint and archive info from read names
    instrument_hint = None
    archive_accession = None
    archive_source = None

    for read in reads[:5]:
        # Check for archive accession
        accession, source, remainder = extract_archive_accession(read)
        if accession:
            archive_accession = accession
            archive_source = source

        # Try to parse as Illumina
        parsed = parse_illumina_read_name(read)
        if parsed:
            instrument_hint = parsed.instrument
            if parsed.archive_accession:
                archive_accession = parsed.archive_accession
                archive_source = parsed.archive_source
            break

        # A PacBio read name carries no hint or accession to read; stop at it
        if parse_pacbio_read_name(read):
            break

    classifications = result.to_output_dict()
    FastqReadMetadata(
        is_paired_end=is_paired_end,
        instrument_hint=instrument_hint,
        archive_accession=archive_accession,
        archive_source=archive_source,
    ).merge_into(classifications)
    return classifications


# Pre-compiled patterns for FASTA contig classification
_ASSEMBLER_PATTERN = re.compile(
    r"(^|#\d#)(h[12]tg|ptg|utg|ctg|tig\d|utig)"
    r"|^(scaffold[_.]|contig[_.]|asm\d|haplotype\d|mat-|pat-|unassigned-)",
    re.IGNORECASE,
)
_TRANSCRIPT_PATTERN = re.compile(r"^(ENST\d|NM_\d|NR_\d|XM_\d|rna-)", re.IGNORECASE)


FETCH_FAILED_RULE_ID = code_rules.FETCH_FAILED.id


def classify_without_content(reason: str) -> dict:
    """Classify a file whose content could not be read: every dimension not_classified.

    We have nothing to say about a file we cannot read (#293). A fetch failure
    (404 from the mirror, DNS/connection failure, timeout) means the content —
    the signal that would refine the classification — is unavailable, so no
    dimension is asserted, not even ones the filename alone could support: a
    filename token is a guess the unread bytes exist to confirm or overturn.

    The record is still written, with the failure ``reason`` as each dimension's
    evidence, rather than dropped — a missing row is indistinguishable from a
    file that was never seen (#155). This is the same all-``not_classified``
    stance ``validation_failed_classifications`` takes for an untrusted record.

    ``reason`` should name the cause (e.g. ``"HTTP 404 from AnVIL S3 mirror ..."``).
    """
    return all_not_classified([{"rule_id": FETCH_FAILED_RULE_ID, "reason": reason}])


def classify_from_gfa_segment_tags(
    segment_tags: list[SegmentTag],
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Refine a sequence graph to `pangenome.reference` from rGFA segment tags.

    In rGFA, each segment carries a stable rank (`SR`) naming which sequence it
    came from; rank 0 is the reference backbone, and `SN` names its contig. A
    graph whose segments carry rank-0 stable sequences therefore defines a
    reference coordinate system — the `pangenome.reference` case. Plain GFA
    segments carry no such tags and stay at the tier-1 `pangenome` base.

    This does not set reference_assembly, for two reasons. `parse_gfa_segment_tags`
    extracts no sequence lengths, so `detect_reference_from_contigs` — the
    definitive signal used for BAM/VCF — cannot run here at all. And the stable
    names that are extracted do not identify an assembly: the fetched head of the
    HPRC minigraph graphs exposes only `chr1`, a name GRCh38 and CHM13 share.
    The assembly is left to the shared filename_ref_* rules.

    Args:
        segment_tags: Per-segment :class:`SegmentTag`s from fetchers.parse_gfa_segment_tags
        name: Optional parsed :class:`FileName` for extension/filename rules
        file_format: Optional declared extension (e.g. ".rgfa.gz"); the engine uses it
            as the fallback when the name carries no known extension. A non-extension
            value ("Other") or absent one falls back to ".gfa" — this is the graph
            classifier, so an unrecognizable graph is still a plain ``pangenome``.
        file_size: Unused. Accepted because ``pipeline._fetch_and_classify`` calls
            every classifier with the same keyword arguments; no graph rule keys
            on file size. ``classify_from_fasta_header`` accepts it unused too.

    Returns:
        Per-field classification dict (same format as classify_from_fasta_header)
    """
    from .rule_engine import CONTENT_TIER, ExtendedFileInfo

    # Hand the engine the parsed name plus a graph file_format fallback: it trusts a
    # known name-extension (``.gfa``/``.rgfa``), else this ``file_format``. A tar-named
    # graph (``graph.tar.gz`` → extension=None, #245) falls through to ``.gfa.gz``,
    # which the engine normalizes to its clean ``.gfa`` core. A
    # file_format that is not a recognized extension — ``"Other"`` or a bare container
    # like ``".tar"`` — defaults to ``.gfa`` so a graph we were routed to is still
    # classified as one. "Recognized" is tested through the shared vocabulary
    # (``FileName.parse``), not a bare ``startswith(".")``. No allowed-extension
    # override is needed now that ``.tar`` is a container, not a content extension.
    format_fallback = file_format if (file_format and FileName.parse(file_format).extension is not None) else ".gfa"

    # Tier 1/2 rules give the `pangenome` base, the `-mc-` reference refinement,
    # and reference_assembly from the filename.
    file_info = ExtendedFileInfo(name=name, file_format=format_fallback)
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=False)

    rank0 = [t for t in segment_tags if t.is_reference_backbone]
    if rank0:
        # is_reference_backbone guarantees a non-empty sn; the `if t.sn` narrows the
        # optional type for the checker without changing the runtime set.
        contigs = sorted({t.sn for t in rank0 if t.sn})
        preview = ", ".join(contigs[:3])
        phrase = "segment carries" if len(rank0) == 1 else "segments carry"
        # Appended as a CONTENT_TIER claim (read from the segments' SR/SN tags, not
        # assigned over the list) so the engine's tier-1 `pangenome_graph` claim
        # survives and the derivation chain reads the same as the engine-resolved
        # `-mc-` case; add_claim re-resolves from the full list so the refinement
        # wins on its own. CONTENT_TIER (above the rule tiers) is the reserved level
        # for byte-derived claims — see rule_engine (#226). (See add_claim /
        # make_claim for the derive-from-claims and required-tier invariants.)
        result.add_claim(
            "data_type",
            rule_id=code_rules.RGFA_STABLE_RANK_REFERENCE.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            reason=(
                f"{len(rank0)} rGFA {phrase} stable rank 0 "
                f"(SR:i:0) on {preview} — graph defines a reference "
                f"coordinate system"
            ),
            value="pangenome.reference",
        )

    return result.to_output_dict()


# A GenomicsDB variant store (the 124K T2T tars, #255) is a directory *database*, not
# a tar of standard files — a GATK GenomicsDB import of gVCFs, built on TileDB. It is
# identified by its member-name layout, not a file extension (`.tdb` is a *generic*
# TileDB array — TileDB also backs single-cell and other stores — so `.tdb` alone must
# not be read as "variants"). The honest, variant-specific signals, either of which
# lands in the archive head:
#   - GenomicsDB metadata files (its own schema; these name variants), and
#   - TileDB arrays named after VCF FORMAT/INFO fields (GenomicsDB stores one array
#     per attribute; GenomicsDB also writes a paired `<field>_var.tdb`, stripped below).
# `__tiledb_workspace.tdb` / `__array_schema.tdb` / `__coords.tdb` are *generic* TileDB
# structure — deliberately excluded, so a non-variant TileDB store is not misread.
# This member-name signature is Python only because the rule engine has no "archive
# contains member X" primitive yet; migrating it to a declarative rule is #257.
_GENOMICSDB_SCHEMA = frozenset({"callset.json", "vidmap.json", "vcfheader.vcf"})
_VCF_FIELD_ARRAYS = frozenset(
    {
        # FORMAT fields
        "gt",
        "ad",
        "dp",
        "gq",
        "pl",
        "min_dp",
        "sb",
        "pgt",
        "pid",
        "ps",
        "rgq",
        "dp_format",
        # INFO / annotation fields (GATK)
        "ac",
        "af",
        "an",
        "qual",
        "filter",
        "id",
        "alt",
        "ref",
        "end",
        "mleac",
        "mleaf",
        "mq",
        "mq0",
        "mqranksum",
        "baseqranksum",
        "clippingranksum",
        "excesshet",
        "fs",
        "inbreedingcoeff",
        "qd",
        "raw_mq",
        "raw_mqanddp",
        "readposranksum",
        "sor",
    }
)


def _is_genomicsdb_variant_store(member_names: list[str]) -> bool:
    """Whether the archive members are a GenomicsDB (TileDB) *variant* store (#255).

    True on a GenomicsDB schema file, or a TileDB array named after a VCF FORMAT/INFO
    field. A bare `.tdb` (generic TileDB) is deliberately *not* enough — those names
    are not variant-specific.

    Checks *every* path segment, not just the basename: a TileDB array is a *directory*
    (``…/PL.tdb/__array_schema.tdb``), so the variant-array name is usually a mid-path
    segment, and a tar may omit the explicit ``…/PL.tdb`` directory entry (or give it a
    trailing slash). A leaf-only check would miss those.
    """
    for member in member_names:
        for segment in member.strip("/").split("/"):
            if segment in _GENOMICSDB_SCHEMA:
                return True
            if segment.endswith(".tdb") and segment[:-4].removesuffix("_var").lower() in _VCF_FIELD_ARRAYS:
                return True
    return False


def _recognized_inner_extensions(member_names: list[str]) -> list[tuple[str, str]]:
    """The archive members whose basename carries a recognized inner extension (#260).

    Returns ``(extension, basename)`` pairs. ``FileName.parse`` reads the extension from
    the basename (peeling any wrappers, yielding a clean core incl. multi-dot cores like
    ``.g.vcf``); parsing the basename rather than the full member path keeps a mid-path
    directory dot out of it. Shared by :func:`classify_from_tar_members` (which picks the
    dominant extension) and :func:`tar_head_is_conclusive` (which only asks whether any
    exists), so the two cannot drift apart in what they count as recognized.
    """
    recognized = []
    for member in member_names:
        basename = member.rsplit("/", 1)[-1]
        ext = FileName.parse(basename).extension
        if ext is not None:
            recognized.append((ext, basename))
    return recognized


def tar_head_is_conclusive(member_names: list[str]) -> bool:
    """Whether the members read so far are signal enough to stop the escalating read (#260).

    The escalating-read stop condition injected into the tar fetcher (via
    ``FileTypeConfig.head_detector``): read deeper only while this is False, so a
    GenomicsDB store whose variant signal sits past the first stage is still reached.

    True on a GenomicsDB variant-store signal — definitive on its own, it fixes the
    archive as a variant store regardless of the other members — or once any member
    carries a recognized inner extension. The recognized-extension case is a
    *first-signal* stop, not a promise about the final value: the generic path in
    :func:`classify_from_tar_members` picks the *dominant* recognized extension over the
    members read, and a deeper read could still shift that dominant. Stopping at the
    first recognized member is deliberate — it keeps the generic path the fixed-head
    sample it always was, while letting the GenomicsDB signal (the #260 target) escalate.
    So "conclusive" means *enough to make the call*, not *classified*: a head of only
    header-only members (e.g. ``.bam``, classified from its own header, not its
    extension) is conclusive yet resolves to ``not_classified``. Uses the same
    recognition helpers as the classifier so the two agree on what counts as recognized.
    """
    return bool(_is_genomicsdb_variant_store(member_names) or _recognized_inner_extensions(member_names))


def classify_from_tar_members(
    member_names: list[str],
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """Classify a tar/tar.gz archive from its member files (#255).

    A container carries no format of its own (#245), so it is classified by its
    *contents*, read from the archive head. Two paths, both emitting ``CONTENT_TIER``
    claims (we read the members, so the signal out-ranks any filename guess); the
    archive name still contributes its own tokens through the base pass:

    1. **GenomicsDB variant store** — a GATK variant database (built on TileDB),
       recognized by its variant-specific member-name signature (schema files or
       VCF-attribute TileDB arrays — see :func:`_is_genomicsdb_variant_store`), not a
       file extension. → ``genomic`` / ``variants``. This is the 124K T2T case.
    2. **Generic** — the dominant recognized inner *extension*, resolved through the
       rule engine (so the format knowledge is not duplicated here), whose
       ``data_modality``, ``data_type`` and ``assay_type`` the archive takes: a tar of
       ``.fasta`` → ``data_type: sequence`` (the ``.fasta`` extension alone leaves
       ``data_modality`` unresolved, since a FASTA may be genomic or transcriptomic).
       An inner type the rules can only classify from its *header* (BAM/CRAM resolve
       to nothing from the extension alone) yields only what its extension supports —
       reading a member's own content is a future refinement.

    No recognizable contents (a head with no GenomicsDB signal and no member with a
    known extension — e.g. only generic TileDB structure files, or a non-tar head that
    read as empty) → left ``not_classified``: we read it and could not type the
    contents. A GenomicsDB store whose variant signal is deeper than the fetched head
    also lands here (~1%); a dynamic, deeper read is the follow-up.

    ``file_size`` and ``file_format`` are unused (a container has no format of its
    own); both are accepted only to match the uniform ``_fetch_and_classify`` call.
    """
    from collections import Counter

    from .rule_engine import CONTENT_TIER, ExtendedFileInfo

    engine = _get_engine()

    # Base pass over the archive's own name — its tokens may still carry a filename
    # signal, and it seeds the result the content claims layer on. A reference comes
    # from it only when the name keeps an inner format the reference rules list
    # (`x.GRCh38.bam.tar.gz`); a bare `grch38.XX.tar.gz` parses to no extension (#523).
    result = engine.classify_extended(ExtendedFileInfo(name=name), include_tier3=False)

    def _claim_content(reason: str, **values: str | None) -> None:
        for fld, value in values.items():
            if value is not None:
                # SOURCE_CONTENT_READ, not SOURCE_CONTIG_DETECTION as the other
                # CONTENT_TIER sites use: this reads the archive head's member
                # names, which are not contig declarations (#392).
                result.add_claim(
                    fld,
                    rule_id=code_rules.TAR_INNER_FORMAT.id,
                    tier=CONTENT_TIER,
                    source_type=SOURCE_CONTENT_READ,
                    reason=reason,
                    value=value,
                )

    # (1) GenomicsDB variant store — a member-name layout signature, caught even when
    # the `.vcf` member / schema files are pushed past the head in the larger stores.
    if _is_genomicsdb_variant_store(member_names):
        _claim_content(
            "GenomicsDB variant store (VCF-attribute TileDB arrays / schema files)",
            data_modality="genomic",
            data_type="variants",
        )
        return result.to_output_dict()

    # (2) Generic: classify by the dominant recognized inner member extension.
    recognized = _recognized_inner_extensions(member_names)  # (inner extension, member basename)
    if not recognized:
        return result.to_output_dict()

    # Counter.most_common breaks ties by first-seen order, so this is deterministic.
    dominant, dom_count = Counter(ext for ext, _ in recognized).most_common(1)[0]
    example = next(basename for ext, basename in recognized if ext == dominant)
    inner = engine.classify_extended(ExtendedFileInfo(name=FileName.EMPTY, file_format=dominant), include_tier3=False)
    _claim_content(
        f"archive head holds {dom_count} {dominant} member(s) (e.g. {example}) — dominant recognized inner format",
        data_modality=inner.data_modality,
        data_type=inner.data_type,
        assay_type=inner.assay_type,
    )
    return result.to_output_dict()


def classify_from_tar_head(head, **kwargs) -> dict:
    """Classify a tar from its parsed head (``cohort_steps.ParsedTarHead``): from its member names alone, as
    :func:`classify_from_tar_members`; the ``vcfheader.vcf`` the head may carry is the step reader's (#621)."""
    return classify_from_tar_members(head.member_names, **kwargs)


# The member a GenomicsDB workspace's GenomicsDBImport command line is read from (#621).
WORKSPACE_HEADER_MEMBER = "vcfheader.vcf"


def workspace_header_member(member_names: list[str]) -> str | None:
    """The base name of the member whose text the tar fetcher keeps (``FileTypeConfig.kept_member``), or None.

    ``vcfheader.vcf`` where the members read so far are a GenomicsDB variant store
    (:func:`_is_genomicsdb_variant_store`), whose step is read from it; no other tar's.
    """
    return WORKSPACE_HEADER_MEMBER if _is_genomicsdb_variant_store(member_names) else None


def classify_sample_map(
    rows,
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """Classify a GATK sample-name map: from its name, and where its content is a map, as a ``sample_map``.

    Where ``rows`` (``cohort_steps.parse_sample_map``) is a map, it is a list of files, not
    their data: ``data_type`` is ``sample_map`` and the other five dimensions are
    ``not_applicable``, at ``CONTENT_TIER`` (#621). Where it is None, the file is classified
    from its name alone. ``file_format`` is accepted to match the uniform
    ``_fetch_and_classify`` call.
    """
    from .rule_engine import CONTENT_TIER, ExtendedFileInfo

    result = _get_engine().classify_extended(ExtendedFileInfo(name=name, file_size=file_size))
    if rows is not None:
        rows_said = "1 row" if len(rows) == 1 else f"{len(rows)} rows"
        why = f"{rows_said} of a sample name and a VCF path: a list of files, not their data"
        # Each field written out, so `test_code_rules` reads what this rule claims.
        result.add_claim(
            "data_type",
            rule_id=code_rules.SAMPLE_MAP_CONTENT.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTENT_READ,
            reason=why,
            value="sample_map",
        )
        result.add_claim(
            "data_modality",
            rule_id=code_rules.SAMPLE_MAP_CONTENT.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTENT_READ,
            reason=why,
            status=NOT_APPLICABLE,
        )
        result.add_claim(
            "reference_assembly",
            rule_id=code_rules.SAMPLE_MAP_CONTENT.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTENT_READ,
            reason=why,
            status=NOT_APPLICABLE,
        )
        result.add_claim(
            "assay_type",
            rule_id=code_rules.SAMPLE_MAP_CONTENT.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTENT_READ,
            reason=why,
            status=NOT_APPLICABLE,
        )
        result.add_claim(
            "platform",
            rule_id=code_rules.SAMPLE_MAP_CONTENT.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTENT_READ,
            reason=why,
            status=NOT_APPLICABLE,
        )
        result.add_claim(
            "instrument_model",
            rule_id=code_rules.SAMPLE_MAP_CONTENT.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTENT_READ,
            reason=why,
            status=NOT_APPLICABLE,
        )
    return result.to_output_dict()


# The IDAT chips recognised, by the exact chip type and probe count read from real files
# (`code_rules.IDAT_CHIP_TYPE`): what each chip is, and the modality and assay of its data.
IDAT_CHIPS: dict[tuple[str, int], tuple[str, str, str]] = {
    # The HPRC's Infinium Omni2.5-8 v1.3, all 160 of its corpus IDATs (#603).
    ("1-95um_multi-swath_for_8x2-5M", 2_522_340): (
        "an Illumina genotyping BeadChip",
        "genomic.genotyping",
        "Genotyping array",
    ),
}
# The scan software recognised (`code_rules.IDAT_SCANNER`), and the platform and instrument
# model of the scanner it is taken to name (the run log names software, not a model).
IDAT_SCANNERS: dict[str, tuple[str, str]] = {
    "iScan Control Software": ("ILLUMINA", "Illumina iScan"),
}
# The longest run of file text an IDAT reason quotes: a chip type or a software name is
# the file's own, and could be up to a read window long.
REASON_TEXT_LIMIT = 200


def _quoted(text: str | None) -> str:
    """``text`` for a reason, cut to ``REASON_TEXT_LIMIT`` characters, as its ``repr``."""
    if text is not None and len(text) > REASON_TEXT_LIMIT:
        text = text[:REASON_TEXT_LIMIT] + "…"
    return repr(text)


def classify_from_idat_header(
    header: IdatHeader,
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """Classify an Illumina IDAT: data_type and reference from the extension, the rest from its header (#603).

    The chip type and probe count decide modality and assay where ``IDAT_CHIPS`` lists the
    pair; the run log's scan software decides platform and instrument where every ``Scan``
    row names one software that ``IDAT_SCANNERS`` lists. Otherwise each of those dimensions
    gets a ``not_classified`` claim at ``CONTENT_TIER`` naming what was read. Reference
    is the extension rule's (``idat_array_signal``: not applicable). ``file_format`` is
    accepted to match the uniform ``_fetch_and_classify`` call, and not read: the format is
    ``.idat``, which routed the file here.
    """
    from .rule_engine import CONTENT_TIER, ExtendedFileInfo

    # The known ".idat" as the format, as for BAM: with no name (a header-only call) the
    # engine reads the extension from it, so the extension rule still runs.
    result = _get_engine().classify_extended(ExtendedFileInfo(name=name, file_format=".idat", file_size=file_size))

    # One helper per rule, each claiming the fields its calls name: a value where one is
    # given, else not_classified. A helper of this shape is one `test_code_rules` reads.
    def _claim_chip(reason: str, **values: str | None) -> None:
        for fld, value in values.items():
            result.add_claim(
                fld,
                rule_id=code_rules.IDAT_CHIP_TYPE.id,
                tier=CONTENT_TIER,
                source_type=SOURCE_CONTENT_READ,
                reason=reason,
                value=value,
                status=NOT_CLASSIFIED if value is None else None,
            )

    def _claim_scanner(reason: str, **values: str | None) -> None:
        for fld, value in values.items():
            result.add_claim(
                fld,
                rule_id=code_rules.IDAT_SCANNER.id,
                tier=CONTENT_TIER,
                source_type=SOURCE_CONTENT_READ,
                reason=reason,
                value=value,
                status=NOT_CLASSIFIED if value is None else None,
            )

    chip = f"chip type {_quoted(header.chip_type)}, {header.probe_count} probes"
    said = (
        IDAT_CHIPS.get((header.chip_type, header.probe_count))
        if header.chip_type is not None and header.probe_count is not None
        else None
    )
    if said is not None:
        what, modality, assay = said
        _claim_chip(f"{chip}: {what}", data_modality=modality, assay_type=assay)
    else:
        _claim_chip(f"{chip}: not a chip this rule recognises", data_modality=None, assay_type=None)

    software = sorted(set(header.scan_software))
    scanner = IDAT_SCANNERS.get(software[0]) if len(software) == 1 else None
    if scanner is not None:
        platform, model = scanner
        why = f"every one of {len(header.scan_software)} Scan rows names {software[0]!r}"
        _claim_scanner(why, platform=platform, instrument_model=model)
    else:
        why = (
            f"the Scan rows name [{', '.join(_quoted(s) for s in software)}]: not one scanner this rule recognises"
            if software
            else "the run log has no Scan row"
        )
        _claim_scanner(why, platform=None, instrument_model=None)
    return result.to_output_dict()


@cache
def _get_ref_chrom_names() -> set[str]:
    """Get cached set of all known reference chromosome names."""
    from .validators.contig_lengths import REFERENCE_CONTIG_LENGTHS

    names = set()
    for ref_contigs in REFERENCE_CONTIG_LENGTHS.values():
        names.update(ref_contigs.keys())
    return names


def classify_from_fasta_header(
    contig_names: list[str],
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Classify FASTA file based on contig/sequence names from > header lines.

    Determines whether the file is a de novo assembly, reference genome extract,
    or transcriptome FASTA by analyzing contig naming patterns and counts.

    Args:
        contig_names: List of contig/sequence names (without > prefix)
        name: Optional parsed :class:`FileName` for pattern matching

    Returns:
        Per-field classification dict (same format as classify_from_fastq_header)
    """
    from .rule_engine import CONTENT_TIER, ExtendedFileInfo
    from .validators.contig_lengths import REFERENCE_CONTIG_LENGTHS

    # Run rule engine for extension/filename-based rules. The real filename drives
    # the tier-2 rules; with no name, the engine reads the extension from the known
    # ".fa.gz" file_format rather than a fabricated name (#152).
    file_info = ExtendedFileInfo(name=name, file_format=".fa.gz")
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=False)

    if not contig_names:
        return result.to_output_dict()

    num_contigs = len(contig_names)
    ref_chrom_names = _get_ref_chrom_names()

    # Categorize contigs
    ref_matches = []
    assembler_contigs = []
    transcript_contigs = []

    for contig in contig_names:
        if contig in ref_chrom_names:
            ref_matches.append(contig)
        elif _ASSEMBLER_PATTERN.search(contig):
            assembler_contigs.append(contig)
        elif _TRANSCRIPT_PATTERN.match(contig):
            transcript_contigs.append(contig)

    # Classification logic

    # 1. Transcript IDs → transcriptomic. Contig names are read from the file, so
    # these land at CONTENT_TIER; add_claim re-resolves from the full list (the
    # tier-1 fasta_base data_type=sequence claim agrees and stays in the chain).
    if transcript_contigs and len(transcript_contigs) > len(ref_matches):
        result.add_claim(
            "data_modality",
            rule_id=code_rules.FASTA_TRANSCRIPT_CONTIGS.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            reason=f"Found {len(transcript_contigs)} transcript IDs (e.g., {transcript_contigs[0]})",
            value="transcriptomic",
        )
        result.add_claim(
            "data_type",
            rule_id=code_rules.FASTA_TRANSCRIPT_CONTIGS.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            reason="Transcript sequences in FASTA",
            value="sequence",
        )
        # No content signal for reference_assembly; it keeps whatever the filename
        # rules resolved (a real value, or not_classified when they found none).
        return result.to_output_dict()

    # 2. Contigs match a known reference set → reference genome
    if ref_matches:
        # Count matches per assembly
        assembly_counts = {}
        for assembly, ref_contigs in REFERENCE_CONTIG_LENGTHS.items():
            count = sum(1 for name in ref_matches if name in ref_contigs)
            if count > 0:
                assembly_counts[assembly] = count

        best_count = max(assembly_counts.values()) if assembly_counts else 0

        # Need a substantial fraction of expected chromosomes to call it a reference
        if best_count >= 20:
            # Assemblies that share chromosome names tie, and a tie names no reference.
            # The contigs say only what they say: no other claim (a filename's, say) is
            # borrowed to break it (#88); a filename rule speaks for itself.
            tied = [a for a, c in assembly_counts.items() if c == best_count]
            best_ref = tied[0] if len(tied) == 1 else None

            ref_reason = f"Matched {best_count} contigs to reference chromosomes" + (
                f" ({best_ref})" if best_ref else " (ambiguous — multiple references share these names)"
            )
            if best_ref:
                result.add_claim(
                    "reference_assembly",
                    rule_id=code_rules.FASTA_REFERENCE_CONTIGS.id,
                    tier=CONTENT_TIER,
                    source_type=SOURCE_CONTIG_DETECTION,
                    reason=ref_reason,
                    value=best_ref,
                )
            else:
                result.add_claim(
                    "reference_assembly",
                    rule_id=code_rules.FASTA_REFERENCE_CONTIGS.id,
                    tier=CONTENT_TIER,
                    source_type=SOURCE_CONTIG_DETECTION,
                    reason=ref_reason,
                    status=NOT_CLASSIFIED,
                )
            result.add_claim(
                "data_modality",
                rule_id=code_rules.FASTA_REFERENCE_CONTIGS.id,
                tier=CONTENT_TIER,
                source_type=SOURCE_CONTIG_DETECTION,
                reason="Contig names match known reference genome",
                value="genomic",
            )
            result.add_claim(
                "data_type",
                rule_id=code_rules.FASTA_REFERENCE_CONTIGS.id,
                tier=CONTENT_TIER,
                source_type=SOURCE_CONTIG_DETECTION,
                reason="FASTA contains reference genome sequences",
                value="assembly.reference",
            )
            return result.to_output_dict()

    # 3. Assembler output contigs → de novo assembly
    if assembler_contigs:
        sample = assembler_contigs[0]
        result.add_claim(
            "data_modality",
            rule_id=code_rules.FASTA_ASSEMBLER_CONTIGS.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            reason=f"Found {len(assembler_contigs)} assembler-named contigs (e.g., {sample})",
            value="genomic",
        )
        result.add_claim(
            "data_type",
            rule_id=code_rules.FASTA_ASSEMBLER_CONTIGS.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            reason="Contig names indicate assembler output",
            value="assembly",
        )
        result.add_claim(
            "reference_assembly",
            rule_id=code_rules.FASTA_ASSEMBLER_CONTIGS.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            reason="De novo assembly — no reference genome applicable",
            status=NOT_APPLICABLE,
        )
        return result.to_output_dict()

    # 4. Many non-standard contigs → likely de novo assembly
    if num_contigs > 50 and not ref_matches:
        result.add_claim(
            "data_modality",
            rule_id=code_rules.FASTA_MANY_CONTIGS.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            reason=f"Large number of contigs ({num_contigs}) with non-standard names suggests de novo assembly",
            value="genomic",
        )
        result.add_claim(
            "data_type",
            rule_id=code_rules.FASTA_MANY_CONTIGS.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            reason="High contig count suggests assembly",
            value="assembly",
        )
        result.add_claim(
            "reference_assembly",
            rule_id=code_rules.FASTA_MANY_CONTIGS.id,
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            reason="De novo assembly — no reference genome applicable",
            status=NOT_APPLICABLE,
        )
        return result.to_output_dict()

    # 5. Nothing above matched: the rule engine's results stand as they are. There is
    #    no content default — a FASTA the contigs say nothing about keeps whatever the
    #    rules concluded, `not_classified` included (#88 removed a genomic/sequence guess).
    return result.to_output_dict()


# =============================================================================
# BED COORDINATE-BASED CLASSIFICATION
# =============================================================================

_STANDARD_CHROM_PATTERN = re.compile(r"^(chr)?(\d{1,2}|X|Y|M|MT)$", re.IGNORECASE)


def _infer_bed_reference(signals: BedSignals) -> tuple[str | None, str]:
    """Infer reference assembly from BED coordinate signals.

    Uses max coordinates to rule out references where coordinates exceed
    chromosome lengths. The remaining reference(s) are candidates. The candidates are
    ``contig_lengths.HUMAN_ASSEMBLIES``, which says why. Bare names (``1``, ``X``) are
    eliminated like ``chr`` ones: a missing prefix is a naming habit, not a reference (#636).

    Returns:
        Tuple of (assembly, rationale)
    """
    max_coords = signals.max_coordinates
    has_chr_prefix = signals.has_chr_prefix

    if not max_coords:
        return None, "No coordinates found"

    standard_chroms = [c for c in signals.chromosomes if _STANDARD_CHROM_PATTERN.match(c)]

    if not standard_chroms:
        return None, ("Non-standard chromosome names — likely de novo assembly, not aligned to a standard reference")

    from .validators.contig_lengths import CONTIG_LENGTH_TOLERANCE, HUMAN_CONTIG_LENGTHS

    ref_lengths = HUMAN_CONTIG_LENGTHS

    # The allowance contig-length matching makes (#473). It covers CHM13 v1.0's
    # small overhangs past the v2.0 row (chr1 169 bp, chr3 657 bp), not its
    # acrocentrics, where a v1.0 position can still rule CHM13 out; no cached BED
    # does so today.
    tolerance = CONTIG_LENGTH_TOLERANCE
    ruled_out = set()
    evidence_details = []

    for assembly, chrom_lengths in ref_lengths.items():
        # Resolve chromosome names case-insensitively. has_chr_prefix detection folds case
        # (Chr1/CHR1), so this lookup must too; otherwise a mixed-case name is treated as an
        # unknown contig and excluded from elimination, leaving reference_assembly
        # not_classified when the coordinates could have ruled assemblies out. The keys keep
        # their canonical casing (chrX/chrY/chrM), so match on a folded index, not str.lower.
        by_folded = {key.lower(): key for key in chrom_lengths}
        for chrom, max_coord in max_coords.items():
            folded = chrom.lower()
            chrom_key = by_folded.get(folded) or by_folded.get(f"chr{folded}")
            if chrom_key is None:
                continue

            ref_length = chrom_lengths[chrom_key]
            if max_coord > ref_length + tolerance:
                ruled_out.add(assembly)
                evidence_details.append(f"{chrom}:{max_coord} exceeds {assembly} {chrom_key} length {ref_length}")
                break

    candidates = [a for a in ref_lengths if a not in ruled_out]

    if has_chr_prefix and "GRCh37" in candidates and len(candidates) > 1:
        candidates.remove("GRCh37")
        evidence_details.append("chr prefix rules out GRCh37 (b37 convention uses bare names)")

    if len(candidates) == 1:
        rationale = f"Only {candidates[0]} not ruled out. {'; '.join(evidence_details)}"
        return candidates[0], rationale
    if len(candidates) == 0:
        return None, f"All references ruled out: {'; '.join(evidence_details)}"
    # More than one reference is still consistent with these coordinates —
    # the file's coordinates don't reach into regions where the candidates'
    # chromosome lengths differ, so we genuinely can't tell them apart. Return
    # "can't tell" (None) rather than guessing a closest match: an undefined
    # coordinate result must not override a filename-based reference.
    return None, (f"Cannot distinguish between {', '.join(candidates)} — coordinates fit multiple references")


def classify_from_bed_signals(
    signals: BedSignals,
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
    dataset_title: str | None = None,
) -> dict:
    """Classify BED file based on coordinate signals.

    Combines rule engine classification (extension/filename patterns) with
    coordinate-based reference detection (elimination algorithm).

    Args:
        signals: Typed BED coordinate signals
        name: Parsed :class:`FileName` for pattern matching
        file_size: Optional file size in bytes
        file_format: Unused. Accepted so this fits the shared pipeline's uniform
            ``classifier(raw, name=, file_size=, file_format=)`` call; the engine reads
            the ``.bed`` format from the fixed ``ExtendedFileInfo`` below, not this arg.
        dataset_title: Optional dataset title for context rules. The shared pipeline
            call omits it, so on that path BED reference comes from the coordinate signal
            and filename alone; a direct caller that passes it can still enable a
            dataset-title rule (#282).

    Returns:
        Per-field classification dict with evidence
    """
    from .rule_engine import CONTENT_TIER, ExtendedFileInfo

    max_coordinates = signals.max_coordinates

    # The real filename drives the tier-2 rules; with no name, the engine reads the
    # extension from the known ".bed" file_format rather than a fabricated name (#152).
    file_info = ExtendedFileInfo(
        name=name,
        file_format=".bed",
        file_size=file_size,
        dataset_title=dataset_title,
    )

    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=False)

    if max_coordinates:
        coord_ref, coord_rationale = _infer_bed_reference(signals)

        if coord_ref:
            # Coordinate detection reads the actual file content, so at CONTENT_TIER
            # it overrides a filename-based reference guess (CLAUDE.md design
            # principle: prefer reading actual file content over guessing from
            # filenames). It claims whatever else was claimed: it never checks
            # another claim first (#88), and resolution settles it against them.
            result.add_claim(
                "reference_assembly",
                rule_id=code_rules.BED_COORDINATE_REFERENCE.id,
                tier=CONTENT_TIER,
                source_type=SOURCE_CONTIG_DETECTION,
                reason=coord_rationale,
                value=coord_ref,
            )
        elif "Non-standard chromosome" in coord_rationale:
            result.add_claim(
                "reference_assembly",
                rule_id=code_rules.BED_NONSTANDARD_CONTIGS.id,
                tier=CONTENT_TIER,
                source_type=SOURCE_CONTIG_DETECTION,
                reason=coord_rationale,
                status=NOT_APPLICABLE,
            )

    return result.to_output_dict()


def __getattr__(name: str):
    """Say why a removed name is gone (``read_name_parsers.REMOVED_NAMES``)."""
    from .validators.read_name_parsers import removed_name

    error = removed_name(__name__, name)
    if error:
        raise error
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
