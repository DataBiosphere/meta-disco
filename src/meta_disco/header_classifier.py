"""BAM/CRAM, VCF, FASTQ, FASTA, and BED header-based classification.

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

from .evidence import SegmentTag
from .file_name import FileName
from .models import CLASSIFIED, NOT_APPLICABLE, NOT_CLASSIFIED, build_field_entry
from .validators.read_name_parsers import (
    detect_paired_end_indicators,
    extract_archive_accession,
    infer_illumina_instrument_model,  # noqa: F401  re-exported for backward compat
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

    The five scalars ``classify_from_fastq_header`` derives while inspecting a
    file's reads: the paired-end flag (from read names, falling back to the
    filename), the instrument model (from the Illumina or PacBio read-name
    parse), the Illumina instrument hint, and the ENA/SRA archive accession and
    source. Both build sites in that function construct this and call
    ``merge_into``, so the key set is declared in one place instead of two
    literals that must be kept in sync.
    """

    is_paired_end: bool | None = None
    instrument_model: str | None = None
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
        name: Optional parsed :class:`FileName`; its tokens (hifi_reads / rnaseq /
            assembly) drive the tier-2 filename rules
        file_size: Optional file size in bytes (used for WGS/WES inference)
        file_format: Optional file format string (e.g., ".bam", ".cram");
            accepted for call uniformity but not consulted — the extension is
            hardcoded ".bam" below

    Returns:
        Dict with per-field classifications:
            - {field}: {value, status, evidence[]} for each of
              data_modality, data_type, assay_type, reference_assembly, platform
    """
    from .rule_engine import CONTENT_TIER, ExtendedFileInfo

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

    # Detect reference from contig lengths first — definitive signal
    lines = header_text.strip().split("\n") if header_text else []
    sq_lines = [line for line in lines if line.startswith("@SQ")]

    from .validators.contig_lengths import detect_reference_from_contig_lengths as detect_from_contigs

    contig_ref = None
    contig_matches = 0
    if sq_lines:
        contig_ref, contig_matches = detect_from_contigs(sq_lines)

    # Run classification with tier 3 (header rules)
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=True)

    # Apply contig-based reference. Read from the @SQ contig lengths, so it lands
    # at CONTENT_TIER and out-ranks any disagreeing filename/header rule; add_claim
    # re-resolves from the full list, so a filename_ref rule that agrees stays in
    # the evidence chain rather than being clobbered (#226/#227).
    if contig_ref:
        reason = f"Reference {contig_ref} detected from {contig_matches} matching contig lengths (definitive)"
        result.add_claim(
            "reference_assembly",
            rule_id="contig_length_detection",
            tier=CONTENT_TIER,
            reason=reason,
            value=contig_ref,
        )
        # Aligned to a known reference genome = genomic data. Guarded so a header
        # rule that already declared a modality (e.g. transcriptomic) is not
        # overridden by this genomic claim.
        if not result.is_declared("data_modality"):
            result.add_claim(
                "data_modality",
                rule_id="aligned_to_reference",
                tier=CONTENT_TIER,
                reason=f"Aligned to {contig_ref} — file contains genomic alignments",
                value="genomic",
            )

    # Infer assay type
    engine.infer_assay_type(result, file_info)

    return result.to_output_dict()


def classify_from_vcf_header(
    header_text: str,
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Classify VCF file based on header content.

    This function uses the RuleEngine with rules from unified_rules.yaml
    to classify VCF files based on their headers.

    Args:
        header_text: VCF header text (lines starting with ##)
        name: Optional parsed :class:`FileName`; its tokens (e.g. a chm13 assembly
            hint) drive the tier-2 filename rules
        file_size: Optional file size in bytes
        file_format: Optional file format string (e.g., ".vcf", ".vcf.gz");
            accepted for call uniformity but not consulted — the extension is
            hardcoded ".vcf.gz" below

    Returns:
        Dict with per-field classifications:
            - {field}: {value, status, evidence[]} for each of
              data_modality, data_type, assay_type, reference_assembly, platform
    """
    from .rule_engine import CONTENT_TIER, ExtendedFileInfo

    # Use the real filename so its tokens reach the tier-2 filename rules. The
    # AnVIL file_format is redundant with the name and not consulted (#157). When
    # there is no name (a header-only call), the engine reads the extension from
    # the file_format we set — the known ".vcf.gz" — instead of a fabricated name.
    file_info = ExtendedFileInfo(
        name=name,
        file_format=".vcf.gz",
        file_size=file_size,
        vcf_header=header_text,
    )

    # Detect reference from contig lengths — definitive signal, no guessing.
    from .validators.contig_lengths import detect_reference_from_contig_lengths as detect_from_contigs

    contig_ref = None
    contig_matches = 0
    if header_text:
        contig_lines = [line for line in header_text.split("\n") if line.startswith("##contig")]
        if contig_lines:
            contig_ref, contig_matches = detect_from_contigs(contig_lines)

    # Run classification with tier 3 (header rules)
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=True)

    # Apply contig-based reference. Read from the ##contig lengths, so it lands at
    # CONTENT_TIER and out-ranks any disagreeing filename/header rule; add_claim
    # re-resolves from the full list (#226/#227).
    if contig_ref:
        reason = f"Reference {contig_ref} detected from {contig_matches} matching contig lengths (definitive)"
        result.add_claim(
            "reference_assembly",
            rule_id="vcf_contig_length",
            tier=CONTENT_TIER,
            reason=reason,
            value=contig_ref,
        )

    return result.to_output_dict()


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
            - data_modality: str or None
            - data_type: str (typically "reads")
            - platform: str or None (ILLUMINA, PACBIO, ONT, etc.)
            - is_paired_end: bool or None
            - instrument_model: str or None (for Illumina)
            - instrument_hint: str or None (instrument ID from read name)
            - archive_accession: str or None (ENA/SRA accession if present)
            - archive_source: str or None (ENA, SRA, DDBJ)
            - matched_rules: list of rule IDs
            - evidence: list of dicts
    """
    from .rule_engine import ExtendedFileInfo

    # Handle empty input — no reads to classify. Statuses are known directly, so
    # pass them explicitly to build_field_entry (epic #116 Stage 3 shape).
    # data_type is the classified "reads"; reference_assembly is not_applicable
    # (reads are unaligned), matching the non-empty path (#131); the remaining
    # dimensions are not_classified.
    if not reads or not reads[0]:
        entries = {
            "data_modality": build_field_entry(None, status=NOT_CLASSIFIED),
            "data_type": build_field_entry("reads", status=CLASSIFIED),
            "platform": build_field_entry(None, status=NOT_CLASSIFIED),
            "reference_assembly": build_field_entry(None, status=NOT_APPLICABLE),
            "assay_type": build_field_entry(None, status=NOT_CLASSIFIED),
        }
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

    # If no platform detected and this is archive-reformatted, try the stripped version
    # This handles cases like @ERR... A00297:... where the Illumina pattern is after the space
    if not result.is_declared("platform") and accession and remainder.strip():
        stripped_read = "@" + remainder.strip()
        file_info_stripped = replace(file_info, fastq_first_read=stripped_read)
        result_stripped = engine.classify_extended(file_info_stripped, include_tier3=True)
        if result_stripped.platform:
            # Merge results - keep the platform and modality from stripped version.
            # Adopt the stripped modality whenever it made a definitive statement
            # (a real value or not_applicable), carrying its status — a status-only
            # declaration has data_modality=None, so a truthiness check would drop it.
            result.set_field("platform", result_stripped.platform)
            if result_stripped.is_declared("data_modality"):
                result.set_field(
                    "data_modality", result_stripped.data_modality, result_stripped.status_of("data_modality")
                )
            # Merge per-field evidence
            for fld, entries in result_stripped.field_evidence.items():
                result.field_evidence[fld].extend(entries)

    # Detect paired-end from read names or filename
    is_paired_end = None
    for read in reads[:10]:
        if detect_paired_end_indicators(read):
            is_paired_end = True
            break
    if is_paired_end is None and name.raw:
        is_paired_end = detect_paired_end_indicators(name.raw)

    # Extract instrument model and archive info from read names
    instrument_model = None
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
            instrument_model = parsed.instrument_model
            instrument_hint = parsed.instrument
            if parsed.archive_accession:
                archive_accession = parsed.archive_accession
                archive_source = parsed.archive_source
            break

        # Try to parse as PacBio
        pacbio = parse_pacbio_read_name(read)
        if pacbio:
            instrument_model = pacbio.instrument_model
            break

    classifications = result.to_output_dict()
    FastqReadMetadata(
        is_paired_end=is_paired_end,
        instrument_model=instrument_model,
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


def classify_without_content(
    reason: str,
    *,
    name: FileName = FileName.EMPTY,
    file_size: int | None = None,
    file_format: str | None = None,
    content_fields: tuple[str, ...] = (),
) -> dict:
    """Classify a file whose content could not be read, from its name alone.

    Keeps the file in the output with a stated cause instead of dropping its row
    — a missing record is indistinguishable from a file that was never seen.

    Runs the tier-1/2 (extension and filename) rules only, so everything knowable
    without reading bytes is still classified: a `.gfa` is still `pangenome`,
    still `genomic`, still `not_applicable` for platform and assay. The parsed
    ``name`` and the declared ``file_format`` are handed to the engine, which
    reconciles them (name-extension wins, else ``file_format``); an archive name
    with no inner format (``x.tar.gz`` → ``extension=None``) falls through to
    ``file_format`` or, failing that, stays unclassified — we do not classify a
    container we could not read (#245).

    ``content_fields`` names the dimensions *this file type's content* can
    determine (``FileTypeConfig.content_fields``). Only those carry the
    ``fetch_failed`` note, so the evidence says which answers the unread bytes
    would have informed. Annotating every unresolved dimension instead would lie:
    GFA content never determines reference_assembly (see
    ``classify_from_gfa_segment_tags``), so a note there would tell a reader that
    re-fetching could resolve an assembly the filename alone must supply.

    The note is attached whether or not the dimension is already classified — a
    filename-derived `pangenome` may be an unrefined `pangenome.reference`. It
    declares a status, not a value, so ``evaluate_claims`` treats it as
    non-assertive and it never competes with a real claim.

    ``reason`` should name the cause (e.g. ``"HTTP 404 from AnVIL S3 mirror ..."``).
    """
    from .rule_engine import ExtendedFileInfo

    file_info = ExtendedFileInfo(
        name=name,
        file_format=file_format,
        file_size=file_size,
    )
    result = _get_engine().classify_extended(file_info, include_tier3=False)

    output = result.to_output_dict()
    for fld in content_fields:
        if fld in output:
            output[fld]["evidence"].append(
                {
                    "rule_id": "fetch_failed",
                    "reason": reason,
                    "status": NOT_CLASSIFIED,
                }
            )
    return output


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
    extracts no sequence lengths, so `detect_reference_from_contig_lengths` — the
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
    # graph (``graph.tar.gz`` → extension=None, #245) falls through to ``.gfa.gz``. A
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
        # _make_claim for the derive-from-claims and required-tier invariants.)
        result.add_claim(
            "data_type",
            rule_id="rgfa_stable_rank_reference",
            tier=CONTENT_TIER,
            reason=(
                f"{len(rank0)} rGFA {phrase} stable rank 0 "
                f"(SR:i:0) on {preview} — graph defines a reference "
                f"coordinate system"
            ),
            value="pangenome.reference",
        )

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
            rule_id="fasta_transcript_contigs",
            tier=CONTENT_TIER,
            reason=f"Found {len(transcript_contigs)} transcript IDs (e.g., {transcript_contigs[0]})",
            value="transcriptomic.bulk",
        )
        result.add_claim(
            "data_type",
            rule_id="fasta_transcript_contigs",
            tier=CONTENT_TIER,
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
            # If multiple assemblies tied (all use same chr names), use filename to disambiguate
            tied = [a for a, c in assembly_counts.items() if c == best_count]
            if len(tied) == 1:
                best_ref = tied[0]
            elif result.reference_assembly:
                # Rule engine already detected reference from filename (e.g., "chm13" in name)
                best_ref = result.reference_assembly
            else:
                # Can't distinguish — contigs match multiple references equally
                best_ref = None

            ref_reason = f"Matched {best_count} contigs to reference chromosomes" + (
                f" ({best_ref})" if best_ref else " (ambiguous — multiple references share these names)"
            )
            if best_ref:
                result.add_claim(
                    "reference_assembly",
                    rule_id="fasta_reference_contigs",
                    tier=CONTENT_TIER,
                    reason=ref_reason,
                    value=best_ref,
                )
            else:
                result.add_claim(
                    "reference_assembly",
                    rule_id="fasta_reference_contigs",
                    tier=CONTENT_TIER,
                    reason=ref_reason,
                    status=NOT_CLASSIFIED,
                )
            result.add_claim(
                "data_modality",
                rule_id="fasta_reference_contigs",
                tier=CONTENT_TIER,
                reason="Contig names match known reference genome",
                value="genomic",
            )
            result.add_claim(
                "data_type",
                rule_id="fasta_reference_contigs",
                tier=CONTENT_TIER,
                reason="FASTA contains reference genome sequences",
                value="assembly.reference",
            )
            return result.to_output_dict()

    # 3. Assembler output contigs → de novo assembly
    if assembler_contigs:
        sample = assembler_contigs[0]
        result.add_claim(
            "data_modality",
            rule_id="fasta_assembler_contigs",
            tier=CONTENT_TIER,
            reason=f"Found {len(assembler_contigs)} assembler-named contigs (e.g., {sample})",
            value="genomic",
        )
        result.add_claim(
            "data_type",
            rule_id="fasta_assembler_contigs",
            tier=CONTENT_TIER,
            reason="Contig names indicate assembler output",
            value="assembly",
        )
        result.add_claim(
            "reference_assembly",
            rule_id="fasta_assembler_contigs",
            tier=CONTENT_TIER,
            reason="De novo assembly — no reference genome applicable",
            status=NOT_APPLICABLE,
        )
        return result.to_output_dict()

    # 4. Many non-standard contigs → likely de novo assembly
    if num_contigs > 50 and not ref_matches:
        result.add_claim(
            "data_modality",
            rule_id="fasta_many_contigs",
            tier=CONTENT_TIER,
            reason=f"Large number of contigs ({num_contigs}) with non-standard names suggests de novo assembly",
            value="genomic",
        )
        result.add_claim(
            "data_type",
            rule_id="fasta_many_contigs",
            tier=CONTENT_TIER,
            reason="High contig count suggests assembly",
            value="assembly",
        )
        result.add_claim(
            "reference_assembly",
            rule_id="fasta_many_contigs",
            tier=CONTENT_TIER,
            reason="De novo assembly — no reference genome applicable",
            status=NOT_APPLICABLE,
        )
        return result.to_output_dict()

    # 5. Default: preserve rule engine results if they set modality/type,
    #    otherwise fall back to genomic/sequence. Guarded so a filename rule that
    #    already declared the field is not overridden by the content default.
    if not result.is_declared("data_modality"):
        result.add_claim(
            "data_modality",
            rule_id="fasta_default_genomic",
            tier=CONTENT_TIER,
            reason=f"FASTA with {num_contigs} contigs — defaulting to genomic",
            value="genomic",
        )
    if not result.is_declared("data_type"):
        result.add_claim(
            "data_type",
            rule_id="fasta_default_genomic",
            tier=CONTENT_TIER,
            reason="Unable to determine specific FASTA type from headers",
            value="sequence",
        )
    return result.to_output_dict()


# =============================================================================
# BED COORDINATE-BASED CLASSIFICATION
# =============================================================================

_STANDARD_CHROM_PATTERN = re.compile(r"^(chr)?(\d{1,2}|X|Y|M|MT)$", re.IGNORECASE)


@dataclass(frozen=True)
class BedSignals:
    """Reference-assembly signals extracted from a BED file's coordinate lines.

    The three logic fields are required: a missing ``has_chr_prefix`` used to
    default to ``True`` via ``.get``, silently asserting chr-prefixed naming and
    flipping the GRCh37 reference call. Requiring it makes an absent signal raise
    at the boundary instead. ``line_count`` is diagnostic only — never read for
    classification — and is retained so ``dataclasses.asdict`` reproduces the
    persisted evidence JSON shape unchanged.
    """

    chromosomes: list[str]
    has_chr_prefix: bool
    max_coordinates: dict[str, int]
    line_count: int = 0

    @classmethod
    def from_evidence(cls, raw: dict) -> "BedSignals":
        """Parse cached evidence JSON into typed signals (file-content boundary).

        Reads required keys directly so a malformed or truncated evidence record
        raises here rather than silently defaulting downstream.
        """
        return cls(
            chromosomes=raw["chromosomes"],
            has_chr_prefix=raw["has_chr_prefix"],
            max_coordinates=raw["max_coordinates"],
            line_count=raw["line_count"],
        )

    @classmethod
    def empty(cls) -> "BedSignals":
        """Signals for a BED file with no coordinate evidence (never fetched).

        Yields filename-only classification: with empty ``max_coordinates`` the
        coordinate block that would read ``has_chr_prefix`` is skipped, so its
        value here is an unread placeholder.
        """
        return cls(chromosomes=[], has_chr_prefix=False, max_coordinates={})


def _infer_bed_reference(signals: BedSignals) -> tuple[str | None, str]:
    """Infer reference assembly from BED coordinate signals.

    Uses max coordinates to rule out references where coordinates exceed
    chromosome lengths. The remaining reference(s) are candidates.

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

    if not has_chr_prefix:
        return "GRCh37", "Chromosomes lack 'chr' prefix, consistent with GRCh37/b37 naming"

    ref_lengths = _get_engine().rules.reference_contig_lengths

    tolerance = 500
    ruled_out = set()
    evidence_details = []

    for assembly, chrom_lengths in ref_lengths.items():
        for chrom, max_coord in max_coords.items():
            chrom_key = chrom if chrom in chrom_lengths else f"chr{chrom}"
            if chrom_key not in chrom_lengths:
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
    dataset_title: str | None = None,
) -> dict:
    """Classify BED file based on coordinate signals.

    Combines rule engine classification (extension/filename patterns) with
    coordinate-based reference detection (elimination algorithm).

    Args:
        signals: Typed BED coordinate signals
        name: Parsed :class:`FileName` for pattern matching
        file_size: Optional file size in bytes
        dataset_title: Optional dataset title for context rules

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

        if coord_ref and result.status_of("reference_assembly") != NOT_APPLICABLE:
            # Coordinate detection reads the actual file content, so at CONTENT_TIER
            # it overrides a filename-based reference guess (CLAUDE.md design
            # principle: prefer reading actual file content over guessing from
            # filenames). The guard preserves an existing not_applicable — a positive
            # determination ("no reference applies"), not a filename guess — which a
            # CONTENT_TIER value claim would otherwise out-rank.
            result.add_claim(
                "reference_assembly",
                rule_id="bed_coordinate_reference",
                tier=CONTENT_TIER,
                reason=coord_rationale,
                value=coord_ref,
            )
        elif "Non-standard chromosome" in coord_rationale:
            result.add_claim(
                "reference_assembly",
                rule_id="bed_nonstandard_contigs",
                tier=CONTENT_TIER,
                reason=coord_rationale,
                status=NOT_APPLICABLE,
            )

    return result.to_output_dict()


def get_rules_documentation() -> str:
    """Generate documentation pointing to the unified rules file."""
    return """# BAM/CRAM, VCF, FASTQ, FASTA, and BED Header Classification Rules

## Overview

Classification rules are defined in the bundled `unified_rules.yaml` (package data of `meta_disco.rules`).

This file contains all rules organized by:
- **Tier 1**: Extension-based rules (fastest)
- **Tier 2**: Filename pattern and file size rules
- **Tier 3**: Header-based rules (BAM @RG/@PG/@SQ, VCF ##, FASTQ read names)
- **FASTA**: Contig name analysis (heuristic, not YAML rules) for assembly/reference/transcriptome detection

## Rule Schema

Each rule has:
- `id`: Unique identifier
- `tier`: 1, 2, or 3
- `scope`: extension, filename, header, vcf_header, fastq_header, or file_size
- `when`: Conditions that must match
- `then`: Effects to apply
- `rationale`: Explanation

## Viewing Rules

To view the full rules, see:
- `unified_rules.yaml`, package data of `meta_disco.rules` (at `src/meta_disco/rules/` in a source checkout) - All classification rules
- The documentation header in that file explains the rule engine

"""
