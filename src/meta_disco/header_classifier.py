"""BAM/CRAM, VCF, FASTQ, FASTA, and BED header-based classification.

This module provides functions to classify sequencing files based on their headers.
The actual classification rules are defined in rules/unified_rules.yaml and executed
by the RuleEngine. This module provides:

1. Public API functions (classify_from_header, classify_from_vcf_header, etc.)
2. Consistency checking for detecting convergent/conflicting signals
3. Re-exports of read name parsers from validators.read_name_parsers
"""

import re
from dataclasses import dataclass, replace

from .models import NOT_APPLICABLE, NOT_CLASSIFIED
from .validators.read_name_parsers import (  # noqa: F401 — re-exported for backward compat
    detect_paired_end_indicators,
    extract_archive_accession,
    infer_illumina_instrument_model,
    parse_illumina_read_name,
    parse_ont_read_name,
    parse_pacbio_read_name,
)


def _get_engine():
    """Get a cached RuleEngine instance (avoids re-parsing YAML on every call)."""
    if not hasattr(_get_engine, "_instance"):
        from .rule_engine import RuleEngine
        _get_engine._instance = RuleEngine()
    return _get_engine._instance




# =============================================================================
# CONSISTENCY RULES
# =============================================================================

@dataclass
class ConsistencyRule:
    """A rule defining expected consistency between header signals."""
    id: str
    signal_a: str  # Rule ID or signal type
    signal_b: str  # Rule ID or signal type
    relationship: str  # "convergent" or "conflicting"
    expected_agreement: str | None  # What they should agree on (for convergent)
    rationale: str


CONVERGENT_RULES = [
    ConsistencyRule(
        id="pacbio_platform_readtype",
        signal_a="platform_pacbio",
        signal_b="pacbio_hifi",
        relationship="convergent",
        expected_agreement="genomic",
        rationale="PL:PACBIO and READTYPE=CCS both indicate PacBio HiFi sequencing, "
                  "which is used for whole genome sequencing. These signals reinforce each other."
    ),
    ConsistencyRule(
        id="pacbio_platform_ccs_program",
        signal_a="platform_pacbio",
        signal_b="program_ccs",
        relationship="convergent",
        expected_agreement="genomic",
        rationale="PL:PACBIO platform with ccs program confirms PacBio HiFi data generation."
    ),
    ConsistencyRule(
        id="pacbio_hifi_ccs_program",
        signal_a="pacbio_hifi",
        signal_b="program_ccs",
        relationship="convergent",
        expected_agreement="genomic",
        rationale="READTYPE=CCS and PN:ccs both indicate HiFi consensus calling was performed."
    ),
    ConsistencyRule(
        id="illumina_bwa",
        signal_a="platform_illumina",
        signal_b="program_bwa",
        relationship="convergent",
        expected_agreement="genomic",
        rationale="Illumina platform with BWA aligner is the standard WGS/WES pipeline. "
                  "Both indicate short-read DNA sequencing."
    ),
    ConsistencyRule(
        id="illumina_star",
        signal_a="platform_illumina",
        signal_b="program_star",
        relationship="convergent",
        expected_agreement="transcriptomic.bulk",
        rationale="Illumina platform with STAR aligner indicates standard RNA-seq workflow."
    ),
    ConsistencyRule(
        id="pacbio_minimap2",
        signal_a="platform_pacbio",
        signal_b="program_minimap2",
        relationship="convergent",
        expected_agreement="genomic",
        rationale="PacBio platform with minimap2 is the standard long-read alignment pipeline."
    ),
    ConsistencyRule(
        id="ont_minimap2",
        signal_a="platform_ont",
        signal_b="program_minimap2",
        relationship="convergent",
        expected_agreement="genomic",
        rationale="ONT platform with minimap2 is the standard nanopore alignment pipeline."
    ),
    ConsistencyRule(
        id="pacbio_isoseq",
        signal_a="platform_pacbio",
        signal_b="program_isoseq",
        relationship="convergent",
        expected_agreement="transcriptomic.bulk",
        rationale="PacBio platform with IsoSeq program indicates long-read RNA sequencing."
    ),
]

CONFLICTING_RULES = [
    ConsistencyRule(
        id="pacbio_star_conflict",
        signal_a="platform_pacbio",
        signal_b="program_star",
        relationship="conflicting",
        expected_agreement=None,
        rationale="STAR is a short-read splice-aware aligner not designed for PacBio long reads. "
                  "This combination is unexpected and may indicate a pipeline error or misannotation."
    ),
    ConsistencyRule(
        id="illumina_ccs_conflict",
        signal_a="platform_illumina",
        signal_b="pacbio_hifi",
        relationship="conflicting",
        expected_agreement=None,
        rationale="READTYPE=CCS is PacBio-specific. Finding it with PL:ILLUMINA indicates "
                  "a header error or file corruption."
    ),
    ConsistencyRule(
        id="illumina_ccs_program_conflict",
        signal_a="platform_illumina",
        signal_b="program_ccs",
        relationship="conflicting",
        expected_agreement=None,
        rationale="The ccs program is PacBio-specific. Finding it with Illumina platform "
                  "indicates a header error."
    ),
    ConsistencyRule(
        id="ont_ccs_conflict",
        signal_a="platform_ont",
        signal_b="pacbio_hifi",
        relationship="conflicting",
        expected_agreement=None,
        rationale="READTYPE=CCS is PacBio-specific and incompatible with ONT platform."
    ),
    ConsistencyRule(
        id="bwa_star_conflict",
        signal_a="program_bwa",
        signal_b="program_star",
        relationship="conflicting",
        expected_agreement=None,
        rationale="BWA (DNA aligner) and STAR (RNA aligner) in the same file suggests "
                  "mixed or incorrectly processed data. Files should use one or the other."
    ),
    ConsistencyRule(
        id="dna_rna_aligner_conflict",
        signal_a="program_bowtie2",
        signal_b="program_star",
        relationship="conflicting",
        expected_agreement=None,
        rationale="Bowtie2 (DNA/ChIP aligner) and STAR (RNA aligner) indicate conflicting "
                  "data modalities in the same file."
    ),
]

ALL_CONSISTENCY_RULES = CONVERGENT_RULES + CONFLICTING_RULES


def check_consistency(matched_rules: list[str], evidence: list[dict]) -> dict:
    """
    Check for consistency between matched rules.

    Returns dict with:
        - convergent_signals: list of matching convergent rule pairs
        - conflicting_signals: list of matching conflicting rule pairs
        - confidence_boost: float adjustment based on convergent signals
        - warnings: list of warning messages for conflicts
        - reference_consistency: bool indicating if all @SQ refs agree
    """
    result = {
        "convergent_signals": [],
        "conflicting_signals": [],
        "confidence_boost": 0.0,
        "warnings": [],
        "reference_consistency": True,
    }

    matched_set = set(matched_rules)

    for rule in ALL_CONSISTENCY_RULES:
        # Check if both signals are present
        a_present = rule.signal_a in matched_set
        b_present = rule.signal_b in matched_set

        if a_present and b_present:
            if rule.relationship == "convergent":
                result["convergent_signals"].append({
                    "rule_id": rule.id,
                    "signal_a": rule.signal_a,
                    "signal_b": rule.signal_b,
                    "expected": rule.expected_agreement,
                    "rationale": rule.rationale,
                })
                result["confidence_boost"] += 0.05
            else:  # conflicting
                result["conflicting_signals"].append({
                    "rule_id": rule.id,
                    "signal_a": rule.signal_a,
                    "signal_b": rule.signal_b,
                    "rationale": rule.rationale,
                })
                result["warnings"].append(
                    f"CONFLICT: {rule.signal_a} + {rule.signal_b} - {rule.rationale}"
                )
                result["confidence_boost"] -= 0.15

    # Check reference consistency from evidence
    refs_found = set()
    for e in evidence:
        if "reference_assembly" in e.get("classification", ""):
            refs_found.add(e.get("classification"))
    if len(refs_found) > 1:
        result["reference_consistency"] = False
        result["warnings"].append(
            f"INCONSISTENT: Multiple references found: {refs_found}"
        )

    return result


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
        Dict with:
            - data_modality: str or None
            - data_type: str (typically "alignments")
            - assay_type: str or None (WGS, WES, RNA-seq, etc.)
            - reference_assembly: str or None
            - platform: str or None (ILLUMINA, PACBIO, ONT)
            - confidence: float
            - is_aligned: bool or None
            - matched_rules: list of rule IDs that matched
            - evidence: list of dicts with rule details
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
    is_aligned = bool(sq_lines) if lines else None

    from .validators.contig_lengths import detect_reference_from_contig_lengths as detect_from_contigs
    contig_ref = None
    contig_conf = 0.0
    contig_matches = 0
    if sq_lines:
        contig_ref, contig_matches, contig_conf = detect_from_contigs(sq_lines)

    # Run classification with tier 3 (header rules)
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=True)

    # Apply contig-based reference (overrides everything — definitive signal)
    if contig_ref:
        result.reference_assembly = contig_ref
        result.confidence = max(result.confidence, contig_conf)
        reason = f"Reference {contig_ref} detected from {contig_matches} matching contig lengths (definitive)"
        # Replace any previous evidence (e.g., stale not_classified from finalization)
        result.field_evidence["reference_assembly"] = [{
            "rule_id": "contig_length_detection",
            "reason": reason,
            "confidence": contig_conf,
        }]

    # Infer assay type
    assay_type = engine.infer_assay_type(result, file_info)

    # Check consistency using flattened rule list
    flat_rules = [e["rule_id"] for entries in result.field_evidence.values() for e in entries]
    consistency = check_consistency(flat_rules, [])

    # Apply confidence boost/penalty from consistency
    final_confidence = min(1.0, max(0.0, result.confidence + consistency["confidence_boost"]))

    # Default to genomic if platform detected but no modality
    if result.data_modality in (None, NOT_CLASSIFIED) and result.platform not in (None, NOT_CLASSIFIED):
        result.data_modality = "genomic"
        result.field_evidence["data_modality"].append({
            "rule_id": "platform_default_genomic",
            "reason": "Platform detected but no modality — defaulting to genomic",
            "confidence": 0.5,
        })

    # Apply inferred assay type only if not already set by a rule
    if assay_type and result.assay_type in (None, NOT_CLASSIFIED):
        result.assay_type = assay_type
        result.field_evidence["assay_type"] = [{
            "rule_id": "infer_assay_type",
            "reason": f"Inferred {assay_type} from platform/modality/file size signals",
            "confidence": 0.70,
        }]

    result.confidence = final_confidence
    classifications = result.to_output_dict()
    classifications["is_aligned"] = is_aligned
    classifications["consistency"] = consistency
    return classifications


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
        Dict with:
            - data_modality: str (typically "genomic")
            - data_type: str (germline_variants, somatic_variants, etc.)
            - reference_assembly: str or None
            - confidence: float
            - matched_rules: list of rule IDs
            - evidence: list of dicts
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
    contig_conf = 0.0
    contig_matches = 0
    if header_text:
        contig_lines = [line for line in header_text.split("\n") if line.startswith("##contig")]
        if contig_lines:
            contig_ref, contig_matches, contig_conf = detect_from_contigs(contig_lines)

    # Run classification with tier 3 (header rules)
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=True)

    # Apply contig-based reference (overrides everything — definitive signal)
    if contig_ref:
        result.reference_assembly = contig_ref
        result.confidence = max(result.confidence, contig_conf)
        reason = f"Reference {contig_ref} detected from {contig_matches} matching contig lengths (definitive)"
        result.field_evidence["reference_assembly"] = [{
            "rule_id": "vcf_contig_length",
            "reason": reason,
            "confidence": contig_conf,
        }]

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
            - confidence: float
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

    # Handle empty input — return per-field format with empty evidence
    if not reads or not reads[0]:
        def empty_field(v):
            return {"value": v, "confidence": 0.0, "evidence": []}
        return {
            "data_modality": empty_field(None),
            "data_type": empty_field("reads"),
            "platform": empty_field(None),
            "reference_assembly": empty_field(None),
            "assay_type": empty_field(None),
            "is_paired_end": None,
            "instrument_model": None,
            "instrument_hint": None,
            "archive_accession": None,
            "archive_source": None,
        }

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
    if (not result.platform or result.platform == NOT_CLASSIFIED) and accession and remainder.strip():
        stripped_read = "@" + remainder.strip()
        file_info_stripped = replace(file_info, fastq_first_read=stripped_read)
        result_stripped = engine.classify_extended(file_info_stripped, include_tier3=True)
        if result_stripped.platform:
            # Merge results - keep the platform and modality from stripped version
            result.platform = result_stripped.platform
            result.data_modality = result_stripped.data_modality or result.data_modality
            result.confidence = max(result.confidence, result_stripped.confidence)
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
            instrument_model = parsed.get("instrument_model")
            instrument_hint = parsed.get("instrument")
            if parsed.get("archive_accession"):
                archive_accession = parsed["archive_accession"]
                archive_source = parsed["archive_source"]
            break

        # Try to parse as PacBio
        parsed = parse_pacbio_read_name(read)
        if parsed:
            instrument_model = parsed.get("instrument_model")
            break

    classifications = result.to_output_dict()
    classifications["is_paired_end"] = is_paired_end
    classifications["instrument_model"] = instrument_model
    classifications["instrument_hint"] = instrument_hint
    classifications["archive_accession"] = archive_accession
    classifications["archive_source"] = archive_source
    return classifications


# Pre-compiled patterns for FASTA contig classification
_ASSEMBLER_PATTERN = re.compile(
    r'(^|#\d#)(h[12]tg|ptg|utg|ctg|tig\d|utig)'
    r'|^(scaffold[_.]|contig[_.]|asm\d|haplotype\d|mat-|pat-|unassigned-)',
    re.IGNORECASE
)
_TRANSCRIPT_PATTERN = re.compile(
    r'^(ENST\d|NM_\d|NR_\d|XM_\d|rna-)',
    re.IGNORECASE
)


def _get_ref_chrom_names() -> set[str]:
    """Get cached set of all known reference chromosome names."""
    if not hasattr(_get_ref_chrom_names, "_cache"):
        from .validators.contig_lengths import REFERENCE_CONTIG_LENGTHS
        names = set()
        for ref_contigs in REFERENCE_CONTIG_LENGTHS.values():
            names.update(ref_contigs.keys())
        _get_ref_chrom_names._cache = names
    return _get_ref_chrom_names._cache


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
        result.data_modality = "transcriptomic.bulk"
        result.data_type = "sequence"
        if result.reference_assembly in (None, NOT_CLASSIFIED):
            result.reference_assembly = NOT_CLASSIFIED
        result.field_evidence["data_modality"] = [{
            "rule_id": "fasta_transcript_contigs",
            "reason": f"Found {len(transcript_contigs)} transcript IDs (e.g., {transcript_contigs[0]})",
            "confidence": 0.90,
        }]
        result.field_evidence["data_type"] = [{
            "rule_id": "fasta_transcript_contigs",
            "reason": "Transcript sequences in FASTA",
            "confidence": 0.90,
        }]
        result.confidence = 0.90
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
            elif result.reference_assembly and result.reference_assembly not in (NOT_CLASSIFIED, NOT_APPLICABLE):
                # Rule engine already detected reference from filename (e.g., "chm13" in name)
                best_ref = result.reference_assembly
            else:
                # Can't distinguish — contigs match multiple references equally
                best_ref = None

            result.data_modality = "genomic"
            result.data_type = "reference_genome"
            if best_ref:
                result.reference_assembly = best_ref
                result.confidence = 0.95
            else:
                result.confidence = 0.80
            result.field_evidence["reference_assembly"] = [{
                "rule_id": "fasta_reference_contigs",
                "reason": f"Matched {best_count} contigs to reference chromosomes"
                          + (f" ({best_ref})" if best_ref else " (ambiguous — multiple references share these names)"),
                "confidence": 0.95 if best_ref else 0.50,
            }]
            result.field_evidence["data_modality"] = [{
                "rule_id": "fasta_reference_contigs",
                "reason": "Contig names match known reference genome",
                "confidence": 0.95,
            }]
            result.field_evidence["data_type"] = [{
                "rule_id": "fasta_reference_contigs",
                "reason": "FASTA contains reference genome sequences",
                "confidence": 0.95,
            }]
            return result.to_output_dict()

    # 3. Assembler output contigs → de novo assembly
    if assembler_contigs:
        result.data_modality = "genomic"
        result.data_type = "assembly"
        result.reference_assembly = NOT_APPLICABLE
        result.confidence = 0.90
        sample = assembler_contigs[0]
        result.field_evidence["data_modality"] = [{
            "rule_id": "fasta_assembler_contigs",
            "reason": f"Found {len(assembler_contigs)} assembler-named contigs (e.g., {sample})",
            "confidence": 0.90,
        }]
        result.field_evidence["data_type"] = [{
            "rule_id": "fasta_assembler_contigs",
            "reason": "Contig names indicate assembler output",
            "confidence": 0.90,
        }]
        result.field_evidence["reference_assembly"] = [{
            "rule_id": "fasta_assembler_contigs",
            "reason": "De novo assembly — no reference genome applicable",
            "confidence": 0.90,
        }]
        return result.to_output_dict()

    # 4. Many non-standard contigs → likely de novo assembly
    if num_contigs > 50 and not ref_matches:
        result.data_modality = "genomic"
        result.data_type = "assembly"
        result.reference_assembly = NOT_APPLICABLE
        result.confidence = 0.75
        result.field_evidence["data_modality"] = [{
            "rule_id": "fasta_many_contigs",
            "reason": f"Large number of contigs ({num_contigs}) with non-standard names suggests de novo assembly",
            "confidence": 0.75,
        }]
        result.field_evidence["data_type"] = [{
            "rule_id": "fasta_many_contigs",
            "reason": "High contig count suggests assembly",
            "confidence": 0.75,
        }]
        result.field_evidence["reference_assembly"] = [{
            "rule_id": "fasta_many_contigs",
            "reason": "De novo assembly — no reference genome applicable",
            "confidence": 0.75,
        }]
        return result.to_output_dict()

    # 5. Default: preserve rule engine results if they set modality/type,
    #    otherwise fall back to genomic/sequence
    if result.data_modality in (None, NOT_CLASSIFIED):
        result.data_modality = "genomic"
        result.field_evidence["data_modality"] = [{
            "rule_id": "fasta_default_genomic",
            "reason": f"FASTA with {num_contigs} contigs — defaulting to genomic",
            "confidence": 0.50,
        }]
    if result.data_type in (None, NOT_CLASSIFIED):
        result.data_type = "sequence"
        result.field_evidence["data_type"] = [{
            "rule_id": "fasta_default_genomic",
            "reason": "Unable to determine specific FASTA type from headers",
            "confidence": 0.50,
        }]
    result.confidence = max(result.confidence, 0.50)
    return result.to_output_dict()


# =============================================================================
# BED COORDINATE-BASED CLASSIFICATION
# =============================================================================

_STANDARD_CHROM_PATTERN = re.compile(r'^(chr)?(\d{1,2}|X|Y|M|MT)$', re.IGNORECASE)


def _pick_closest_reference(
    max_coords: dict[str, int],
    ref_lengths: dict[str, dict[str, int]],
    candidates: list[str],
) -> str | None:
    """Pick the reference whose chromosome lengths best match observed max coordinates.

    When max coordinates don't rule out multiple references, we pick the one where
    coordinates come closest to (but don't exceed) the chromosome lengths. Files
    covering the full chromosome will have max coordinates near the chromosome length.
    """
    scores = {}
    for assembly in candidates:
        chrom_lengths = ref_lengths[assembly]
        score = 0
        matched = 0

        for chrom, max_coord in max_coords.items():
            chrom_key = chrom if chrom in chrom_lengths else f"chr{chrom}"
            if chrom_key not in chrom_lengths:
                continue

            ref_len = chrom_lengths[chrom_key]
            ratio = max_coord / ref_len
            if ratio <= 1.0:
                score += ratio
                matched += 1

        if matched > 0:
            scores[assembly] = score / matched

    if not scores:
        return None

    best_score = max(scores.values())
    tied = [a for a, s in scores.items() if abs(s - best_score) < 0.001]
    if len(tied) > 1:
        return None  # Ambiguous — don't guess
    return tied[0]


def _infer_bed_reference(signals: dict) -> tuple[str | None, float, str]:
    """Infer reference assembly from BED coordinate signals.

    Uses max coordinates to rule out references where coordinates exceed
    chromosome lengths. The remaining reference(s) are candidates.

    Returns:
        Tuple of (assembly, confidence, rationale)
    """
    max_coords = signals.get("max_coordinates", {})
    has_chr_prefix = signals.get("has_chr_prefix", True)

    if not max_coords:
        return None, 0.0, "No coordinates found"

    standard_chroms = [c for c in signals.get("chromosomes", [])
                       if _STANDARD_CHROM_PATTERN.match(c)]

    if not standard_chroms:
        return None, 0.0, ("Non-standard chromosome names — likely de novo assembly, "
                           "not aligned to a standard reference")

    if not has_chr_prefix:
        return "GRCh37", 0.85, "Chromosomes lack 'chr' prefix, consistent with GRCh37/b37 naming"

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
                evidence_details.append(
                    f"{chrom}:{max_coord} exceeds {assembly} {chrom_key} length {ref_length}"
                )
                break

    candidates = [a for a in ref_lengths if a not in ruled_out]

    if has_chr_prefix and "GRCh37" in candidates and len(candidates) > 1:
        candidates.remove("GRCh37")
        evidence_details.append("chr prefix rules out GRCh37 (b37 convention uses bare names)")

    if len(candidates) == 1:
        rationale = f"Only {candidates[0]} not ruled out. {'; '.join(evidence_details)}"
        return candidates[0], 0.92, rationale
    elif len(candidates) == 0:
        return None, 0.0, f"All references ruled out: {'; '.join(evidence_details)}"
    else:
        best = _pick_closest_reference(max_coords, ref_lengths, candidates)
        if best:
            return best, 0.80, (f"Multiple references possible ({', '.join(candidates)}), "
                                f"{best} is closest match by coordinates")
        return None, 0.0, f"Cannot distinguish between {', '.join(candidates)}"


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
        coord_ref, coord_conf, coord_rationale = _infer_bed_reference(signals)

        if coord_ref and coord_conf > 0:
            existing_ref_evidence = result.field_evidence.get("reference_assembly") or []
            existing_ref_conf = max(
                (ev.get("confidence", 0.0) for ev in existing_ref_evidence),
                default=0.0,
            )
            if result.reference_assembly in (None, NOT_CLASSIFIED) or coord_conf > existing_ref_conf:
                result.reference_assembly = coord_ref
                result.confidence = max(result.confidence, coord_conf)
                result.field_evidence["reference_assembly"] = [{
                    "rule_id": "bed_coordinate_reference",
                    "reason": coord_rationale,
                    "confidence": coord_conf,
                }]
        elif coord_ref is None and coord_conf == 0.0:
            if "Non-standard chromosome" in coord_rationale:
                result.reference_assembly = NOT_APPLICABLE
                result.field_evidence["reference_assembly"] = [{
                    "rule_id": "bed_nonstandard_contigs",
                    "reason": coord_rationale,
                    "confidence": 0.0,
                }]

    return result.to_output_dict()


def get_rules_documentation() -> str:
    """Generate documentation pointing to the unified rules file."""
    return """# BAM/CRAM, VCF, FASTQ, FASTA, and BED Header Classification Rules

## Overview

Classification rules are defined in `rules/unified_rules.yaml`.

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
- `confidence`: 0.0-1.0
- `rationale`: Explanation

## Viewing Rules

To view the full rules, see:
- `rules/unified_rules.yaml` - All classification rules
- The documentation header in that file explains the rule engine

## Consistency Validation

The classifier also checks for consistency between matched signals.
See `CONVERGENT_RULES` and `CONFLICTING_RULES` in this module for
signal pairs that should (or should not) appear together.
"""
