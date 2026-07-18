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
# GFA_CONFIG.extensions is this same tuple — defined here so the classifier and
# the config cannot disagree about which names it may trust.
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
    file_name: str | None = None,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Classify data modality and reference from BAM header text.

    This function uses the RuleEngine with rules from unified_rules.yaml
    to classify BAM/CRAM files based on their headers.

    Args:
        header_text: Raw SAM/BAM header text (lines starting with @)
        file_size: Optional file size in bytes (used for WGS/WES inference)
        file_format: Optional file format string (e.g., ".bam", ".cram")

    Returns:
        Dict with per-field classifications:
            - {field}: {value, status, evidence[]} for each of
              data_modality, data_type, assay_type, reference_assembly, platform
    """
    from .rule_engine import ExtendedFileInfo

    # Determine filename for extension-based rules
    filename = "sample.bam"
    if file_format:
        filename = f"sample{file_format}"

    # Create file info with header
    file_info = ExtendedFileInfo(
        filename=filename,
        file_size=file_size,
        file_size_gb=file_size / 1e9 if file_size is not None else None,
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

    # Apply contig-based reference (overrides everything — definitive signal)
    if contig_ref:
        result.set_field("reference_assembly", contig_ref)
        reason = f"Reference {contig_ref} detected from {contig_matches} matching contig lengths (definitive)"
        result.field_evidence["reference_assembly"] = [
            {
                "rule_id": "contig_length_detection",
                "reason": reason,
                "value": contig_ref,
            }
        ]
        # Aligned to a known reference genome = genomic data
        if not result.is_declared("data_modality"):
            result.set_field("data_modality", "genomic")
            result.field_evidence["data_modality"] = [
                {
                    "rule_id": "aligned_to_reference",
                    "reason": f"Aligned to {contig_ref} — file contains genomic alignments",
                    "value": "genomic",
                }
            ]

    # Infer assay type
    engine.infer_assay_type(result, file_info)

    return result.to_output_dict()


def classify_from_vcf_header(
    header_text: str,
    *,
    file_name: str | None = None,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Classify VCF file based on header content.

    This function uses the RuleEngine with rules from unified_rules.yaml
    to classify VCF files based on their headers.

    Args:
        header_text: VCF header text (lines starting with ##)
        file_size: Optional file size in bytes
        file_format: Optional file format string (e.g., ".vcf", ".vcf.gz")

    Returns:
        Dict with per-field classifications:
            - {field}: {value, status, evidence[]} for each of
              data_modality, data_type, assay_type, reference_assembly, platform
    """
    from .rule_engine import ExtendedFileInfo

    # Determine filename for extension-based rules
    filename = "sample.vcf.gz"
    if file_format:
        filename = f"sample{file_format}"

    # Create file info with VCF header
    file_info = ExtendedFileInfo(
        filename=filename,
        file_size=file_size,
        file_size_gb=file_size / 1e9 if file_size is not None else None,
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

    # Apply contig-based reference (overrides everything — definitive signal)
    if contig_ref:
        result.set_field("reference_assembly", contig_ref)
        reason = f"Reference {contig_ref} detected from {contig_matches} matching contig lengths (definitive)"
        result.field_evidence["reference_assembly"] = [
            {
                "rule_id": "vcf_contig_length",
                "reason": reason,
                "value": contig_ref,
            }
        ]

    return result.to_output_dict()


def classify_from_fastq_header(
    reads: list[str],
    *,
    file_name: str | None = None,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Classify FASTQ file based on read names.

    This function uses the RuleEngine with rules from unified_rules.yaml
    to classify FASTQ files based on their read names.

    Args:
        reads: List of read name lines (first few reads from file)
        file_name: Optional filename for pattern matching
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

    # Use provided filename or generate one
    filename = file_name or "sample.fastq.gz"

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

    # Create file info with FASTQ header - try original first
    file_info = ExtendedFileInfo(
        filename=filename,
        file_size=file_size,
        file_size_gb=file_size / 1e9 if file_size is not None else None,
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
    if is_paired_end is None and file_name:
        is_paired_end = detect_paired_end_indicators(file_name)

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


def filename_for_rules(
    file_name: str | None,
    file_format: str | None,
    default: str,
    allowed_extensions: tuple[str, ...] | None = None,
) -> str:
    """The filename to hand the rule engine, which reads the extension from it.

    ``ClassifyPipeline._filter_records`` selects a record when *either* its
    ``file_name`` or its ``file_format`` carries a matching extension, so a
    selected record's ``file_name`` may not carry one. The engine derives
    ``file_format`` strictly from the filename (``UnifiedRules.extract_extension``),
    so an extensionless name silently disables every extension-scoped rule — and
    worse, ``extract_extension("hprc-v1.0-mc-grch38")`` returns ``".0-mc-grch38"``,
    a nonsense suffix taken from the last dot.

    So: keep ``file_name`` when it already yields a *usable* extension, otherwise
    append ``file_format`` to it, preserving the filename tokens the tier-2 rules
    match (``-mc-``, ``grch38``). Testing "already usable" rather than "ends with
    file_format" matters: 5,227 corpus records are named ``*.fastq.gz`` while
    declaring ``file_format: ".fastq"``, and appending there would produce
    ``*.fastq.gz.fastq``.

    ``allowed_extensions`` narrows "usable" to the extensions the caller can
    actually handle. Without it, a graph record named ``graph.tar.gz`` would be
    trusted verbatim: the tar rules run, ``pangenome_graph`` never fires, and a
    content-derived ``data_type`` claim then lands on a record whose
    ``data_modality`` is not_classified. Pass the calling config's extensions.

    ``file_format`` is only grafted on when it looks like an extension. The
    corpus carries ``file_format: "Other"`` on ~108k records; appending that
    would yield ``graphOther``, which matches nothing.
    """
    rules = _get_engine().rules
    if file_name:
        ext = rules.extract_extension(file_name)
        usable = ext in allowed_extensions if allowed_extensions else ext in rules.extension_map
        if usable:
            return file_name
    if file_format and file_format.startswith("."):
        return f"{file_name or 'file'}{file_format}"
    return file_name or default


def classify_without_content(
    reason: str,
    *,
    file_name: str | None = None,
    file_size: int | None = None,
    file_format: str | None = None,
    allowed_extensions: tuple[str, ...] | None = None,
    content_fields: tuple[str, ...] = (),
) -> dict:
    """Classify a file whose content could not be read, from its name alone.

    Keeps the file in the output with a stated cause instead of dropping its row
    — a missing record is indistinguishable from a file that was never seen.

    Runs the tier-1/2 (extension and filename) rules only, so everything knowable
    without reading bytes is still classified: a `.gfa` is still `pangenome`,
    still `genomic`, still `not_applicable` for platform and assay.

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

    filename = filename_for_rules(file_name, file_format, default="", allowed_extensions=allowed_extensions)
    file_info = ExtendedFileInfo(
        filename=filename,
        file_size=file_size,
        file_size_gb=file_size / 1e9 if file_size is not None else None,
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
    file_name: str | None = None,
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
        file_name: Optional filename for extension/filename rules
        file_format: Optional extension (e.g. ".rgfa.gz"), used to drive the
            extension rules when file_name carries no known extension
            (see filename_for_rules)
        file_size: Unused. Accepted because ``pipeline._fetch_and_classify`` calls
            every classifier with the same keyword arguments; no graph rule keys
            on file size. ``classify_from_fasta_header`` accepts it unused too.

    Returns:
        Per-field classification dict (same format as classify_from_fasta_header)
    """
    from .rule_engine import ExtendedFileInfo

    filename = filename_for_rules(
        file_name,
        file_format,
        default="graph.gfa",
        allowed_extensions=GRAPH_TEXT_EXTENSIONS,
    )

    # Tier 1/2 rules give the `pangenome` base, the `-mc-` reference refinement,
    # and reference_assembly from the filename.
    file_info = ExtendedFileInfo(filename=filename)
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=False)

    rank0 = [t for t in segment_tags if t.is_reference_backbone]
    if rank0:
        # is_reference_backbone guarantees a non-empty sn; the `if t.sn` narrows the
        # optional type for the checker without changing the runtime set.
        contigs = sorted({t.sn for t in rank0 if t.sn})
        preview = ", ".join(contigs[:3])
        phrase = "segment carries" if len(rank0) == 1 else "segments carry"
        # Appended as a tier-3 claim, not assigned over the list, so the tier-1
        # `pangenome_graph` claim survives and the derivation chain reads the same
        # as the engine-resolved `-mc-` case. The tier matters: evaluate_claims
        # defaults a missing tier to 0, which would lose to the tier-1 `pangenome`
        # claim and undo this refinement once #150 resolves this path from claims.
        result.field_evidence["data_type"].append(
            {
                "rule_id": "rgfa_stable_rank_reference",
                "tier": 3,
                "reason": (
                    f"{len(rank0)} rGFA {phrase} stable rank 0 "
                    f"(SR:i:0) on {preview} — graph defines a reference "
                    f"coordinate system"
                ),
                "value": "pangenome.reference",
            }
        )
        # Still set imperatively rather than resolved from the claims above;
        # conflict detection for data_type is bypassed here (see #150).
        result.set_field("data_type", "pangenome.reference")

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
    file_name: str | None = None,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Classify FASTA file based on contig/sequence names from > header lines.

    Determines whether the file is a de novo assembly, reference genome extract,
    or transcriptome FASTA by analyzing contig naming patterns and counts.

    Args:
        contig_names: List of contig/sequence names (without > prefix)
        file_name: Optional filename for pattern matching

    Returns:
        Per-field classification dict (same format as classify_from_fastq_header)
    """
    from .rule_engine import ExtendedFileInfo
    from .validators.contig_lengths import REFERENCE_CONTIG_LENGTHS

    filename = file_name or "sample.fa.gz"

    # Run rule engine for extension/filename-based rules
    file_info = ExtendedFileInfo(filename=filename)
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

    for name in contig_names:
        if name in ref_chrom_names:
            ref_matches.append(name)
        elif _ASSEMBLER_PATTERN.search(name):
            assembler_contigs.append(name)
        elif _TRANSCRIPT_PATTERN.match(name):
            transcript_contigs.append(name)

    # Classification logic

    # 1. Transcript IDs → transcriptomic
    if transcript_contigs and len(transcript_contigs) > len(ref_matches):
        result.set_field("data_modality", "transcriptomic.bulk")
        result.set_field("data_type", "sequence")
        if not result.is_declared("reference_assembly"):
            result.set_field("reference_assembly", status=NOT_CLASSIFIED)
        result.field_evidence["data_modality"] = [
            {
                "rule_id": "fasta_transcript_contigs",
                "reason": f"Found {len(transcript_contigs)} transcript IDs (e.g., {transcript_contigs[0]})",
                "value": "transcriptomic.bulk",
            }
        ]
        result.field_evidence["data_type"] = [
            {
                "rule_id": "fasta_transcript_contigs",
                "reason": "Transcript sequences in FASTA",
                "value": "sequence",
            }
        ]
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

            result.set_field("data_modality", "genomic")
            result.set_field("data_type", "assembly.reference")
            ref_entry = {
                "rule_id": "fasta_reference_contigs",
                "reason": f"Matched {best_count} contigs to reference chromosomes"
                + (f" ({best_ref})" if best_ref else " (ambiguous — multiple references share these names)"),
            }
            if best_ref:
                result.set_field("reference_assembly", best_ref)
                ref_entry["value"] = best_ref
            else:
                result.set_field("reference_assembly", status=NOT_CLASSIFIED)
                ref_entry["status"] = NOT_CLASSIFIED
            result.field_evidence["reference_assembly"] = [ref_entry]
            result.field_evidence["data_modality"] = [
                {
                    "rule_id": "fasta_reference_contigs",
                    "reason": "Contig names match known reference genome",
                    "value": "genomic",
                }
            ]
            result.field_evidence["data_type"] = [
                {
                    "rule_id": "fasta_reference_contigs",
                    "reason": "FASTA contains reference genome sequences",
                    "value": "assembly.reference",
                }
            ]
            return result.to_output_dict()

    # 3. Assembler output contigs → de novo assembly
    if assembler_contigs:
        result.set_field("data_modality", "genomic")
        result.set_field("data_type", "assembly")
        result.set_field("reference_assembly", status=NOT_APPLICABLE)
        sample = assembler_contigs[0]
        result.field_evidence["data_modality"] = [
            {
                "rule_id": "fasta_assembler_contigs",
                "reason": f"Found {len(assembler_contigs)} assembler-named contigs (e.g., {sample})",
                "value": "genomic",
            }
        ]
        result.field_evidence["data_type"] = [
            {
                "rule_id": "fasta_assembler_contigs",
                "reason": "Contig names indicate assembler output",
                "value": "assembly",
            }
        ]
        result.field_evidence["reference_assembly"] = [
            {
                "rule_id": "fasta_assembler_contigs",
                "reason": "De novo assembly — no reference genome applicable",
                "status": NOT_APPLICABLE,
            }
        ]
        return result.to_output_dict()

    # 4. Many non-standard contigs → likely de novo assembly
    if num_contigs > 50 and not ref_matches:
        result.set_field("data_modality", "genomic")
        result.set_field("data_type", "assembly")
        result.set_field("reference_assembly", status=NOT_APPLICABLE)
        result.field_evidence["data_modality"] = [
            {
                "rule_id": "fasta_many_contigs",
                "reason": f"Large number of contigs ({num_contigs}) with non-standard names suggests de novo assembly",
                "value": "genomic",
            }
        ]
        result.field_evidence["data_type"] = [
            {
                "rule_id": "fasta_many_contigs",
                "reason": "High contig count suggests assembly",
                "value": "assembly",
            }
        ]
        result.field_evidence["reference_assembly"] = [
            {
                "rule_id": "fasta_many_contigs",
                "reason": "De novo assembly — no reference genome applicable",
                "status": NOT_APPLICABLE,
            }
        ]
        return result.to_output_dict()

    # 5. Default: preserve rule engine results if they set modality/type,
    #    otherwise fall back to genomic/sequence
    if not result.is_declared("data_modality"):
        result.set_field("data_modality", "genomic")
        result.field_evidence["data_modality"] = [
            {
                "rule_id": "fasta_default_genomic",
                "reason": f"FASTA with {num_contigs} contigs — defaulting to genomic",
                "value": "genomic",
            }
        ]
    if not result.is_declared("data_type"):
        result.set_field("data_type", "sequence")
        result.field_evidence["data_type"] = [
            {
                "rule_id": "fasta_default_genomic",
                "reason": "Unable to determine specific FASTA type from headers",
                "value": "sequence",
            }
        ]
    return result.to_output_dict()


# =============================================================================
# BED COORDINATE-BASED CLASSIFICATION
# =============================================================================

_STANDARD_CHROM_PATTERN = re.compile(r"^(chr)?(\d{1,2}|X|Y|M|MT)$", re.IGNORECASE)


def _infer_bed_reference(signals: dict) -> tuple[str | None, str]:
    """Infer reference assembly from BED coordinate signals.

    Uses max coordinates to rule out references where coordinates exceed
    chromosome lengths. The remaining reference(s) are candidates.

    Returns:
        Tuple of (assembly, rationale)
    """
    max_coords = signals.get("max_coordinates", {})
    has_chr_prefix = signals.get("has_chr_prefix", True)

    if not max_coords:
        return None, "No coordinates found"

    standard_chroms = [c for c in signals.get("chromosomes", []) if _STANDARD_CHROM_PATTERN.match(c)]

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
    signals: dict,
    *,
    file_name: str | None = None,
    file_size: int | None = None,
    dataset_title: str | None = None,
) -> dict:
    """Classify BED file based on coordinate signals.

    Combines rule engine classification (extension/filename patterns) with
    coordinate-based reference detection (elimination algorithm).

    Args:
        signals: Dict with keys: chromosomes, max_coordinates, has_chr_prefix
        file_name: Filename for pattern matching
        file_size: Optional file size in bytes
        dataset_title: Optional dataset title for context rules

    Returns:
        Per-field classification dict with evidence
    """
    from .rule_engine import ExtendedFileInfo

    filename = file_name or "sample.bed"
    max_coordinates = signals.get("max_coordinates", {})

    file_info = ExtendedFileInfo(
        filename=filename,
        file_size=file_size,
        file_size_gb=file_size / 1e9 if file_size is not None else None,
        dataset_title=dataset_title,
    )

    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=False)

    if max_coordinates:
        coord_ref, coord_rationale = _infer_bed_reference(signals)

        if coord_ref and result.status_of("reference_assembly") != NOT_APPLICABLE:
            # Coordinate detection reads the actual file content, so it overrides
            # a filename-based reference guess (CLAUDE.md design principle: prefer
            # reading actual file content over guessing from filenames). But it does
            # not overturn an existing not_applicable — that is a positive
            # determination ("no reference applies"), not a filename guess.
            result.set_field("reference_assembly", coord_ref)
            result.field_evidence["reference_assembly"] = [
                {
                    "rule_id": "bed_coordinate_reference",
                    "reason": coord_rationale,
                    "value": coord_ref,
                }
            ]
        elif "Non-standard chromosome" in coord_rationale:
            result.set_field("reference_assembly", status=NOT_APPLICABLE)
            result.field_evidence["reference_assembly"] = [
                {
                    "rule_id": "bed_nonstandard_contigs",
                    "reason": coord_rationale,
                    "status": NOT_APPLICABLE,
                }
            ]

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
