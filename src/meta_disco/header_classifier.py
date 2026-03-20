"""BAM/CRAM, VCF, and FASTQ header-based classification.

This module provides functions to classify sequencing files based on their headers.
The actual classification rules are defined in rules/unified_rules.yaml and executed
by the RuleEngine. This module provides:

1. Public API functions (classify_from_header, classify_from_vcf_header, classify_from_fastq_header)
2. Helper functions for parsing read names and detecting references
3. Consistency checking for detecting convergent/conflicting signals
"""

import re
from dataclasses import dataclass, replace

from .models import NOT_CLASSIFIED


def _get_engine():
    """Get a cached RuleEngine instance (avoids re-parsing YAML on every call)."""
    if not hasattr(_get_engine, "_instance"):
        from .rule_engine import RuleEngine
        _get_engine._instance = RuleEngine()
    return _get_engine._instance


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def extract_archive_accession(read_name: str) -> tuple[str | None, str | None, str]:
    """
    Extract ENA/SRA/DDBJ accession from a FASTQ read name.

    Args:
        read_name: A FASTQ read name line (with or without @ prefix)

    Returns:
        Tuple of (accession, source, remainder) where:
        - accession: e.g., "ERR3242571" or None if not found
        - source: "ENA", "SRA", or "DDBJ" or None
        - remainder: the rest of the read name after accession
    """
    # Remove @ prefix if present
    if read_name.startswith("@"):
        read_name = read_name[1:]

    # ENA format: ERR/ERS followed by numbers
    match = re.match(r"^(ERR\d+|ERS\d+)\.?\d*\s*(.*)", read_name)
    if match:
        return match.group(1), "ENA", match.group(2)

    # SRA format: SRR/SRS followed by numbers
    match = re.match(r"^(SRR\d+|SRS\d+)\.?\d*\s*(.*)", read_name)
    if match:
        return match.group(1), "SRA", match.group(2)

    # DDBJ format: DRR/DRS followed by numbers
    match = re.match(r"^(DRR\d+|DRS\d+)\.?\d*\s*(.*)", read_name)
    if match:
        return match.group(1), "DDBJ", match.group(2)

    return None, None, read_name


def infer_illumina_instrument_model(instrument_id: str) -> str | None:
    """
    Infer Illumina instrument model from instrument ID prefix.

    Args:
        instrument_id: The instrument ID from a read name (e.g., "A00297")

    Returns:
        Model name (e.g., "NovaSeq 6000") or None if unknown
    """
    from .rule_loader import get_unified_rules

    rules = get_unified_rules()
    instrument_id_upper = instrument_id.upper()
    for instrument in rules.illumina_instruments:
        if instrument_id_upper.startswith(instrument.prefix.upper()):
            return instrument.model
    return None


def detect_paired_end_indicators(text: str) -> bool:
    """
    Check if text contains paired-end read indicators.

    Args:
        text: Filename or read name to check

    Returns:
        True if paired-end indicators found
    """
    patterns = [
        r"_R[12]_",       # _R1_, _R2_
        r"_R[12]\.",      # _R1., _R2.
        r"\.R[12]\.",     # .R1., .R2.
        r"_[12]\.",       # _1., _2.
        r"[/\s][12]$",    # /1, /2 at end
        r"[/\s][12]:",    # /1:, /2: in Illumina format
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def parse_illumina_read_name(read_name: str) -> dict | None:
    """
    Parse an Illumina read name into its components.

    Modern format (Casava 1.8+):
        @<instrument>:<run>:<flowcell>:<lane>:<tile>:<x>:<y> <read>:<filtered>:<control>:<index>

    Legacy format (pre-Casava 1.8):
        @<instrument>:<lane>:<tile>:<x>:<y>#<index>/<read>

    Args:
        read_name: A FASTQ read name line (with or without @ prefix)

    Returns:
        Dict with parsed components or None if not Illumina format
    """
    if read_name.startswith("@"):
        read_name = read_name[1:]

    # Check for archive-reformatted reads first (e.g., @ERR123.1 A00297:...)
    archive_accession = None
    archive_source = None
    accession, source, remainder = extract_archive_accession(read_name)
    if accession:
        archive_accession = accession
        archive_source = source
        read_name = remainder.strip()

    # Try modern format first (Casava 1.8+)
    modern_pattern = r"^([A-Z0-9-]+):(\d+):([A-Z0-9]+):(\d+):(\d+):(\d+):(\d+)"
    match = re.match(modern_pattern, read_name)
    if match:
        instrument_id = match.group(1)
        result = {
            "format": "modern",
            "instrument": instrument_id,
            "run_number": int(match.group(2)),
            "flowcell": match.group(3),
            "lane": int(match.group(4)),
            "tile": int(match.group(5)),
            "x_pos": int(match.group(6)),
            "y_pos": int(match.group(7)),
            "instrument_model": infer_illumina_instrument_model(instrument_id),
        }

        # Add archive info if present
        if archive_accession:
            result["archive_accession"] = archive_accession
            result["archive_source"] = archive_source

        # Parse the second part if present (after space)
        space_idx = read_name.find(" ")
        if space_idx > 0:
            second_part = read_name[space_idx + 1:]
            second_pattern = r"^([12]):([YN]):(\d+):([ACGTN+]+)?"
            second_match = re.match(second_pattern, second_part)
            if second_match:
                result["read"] = int(second_match.group(1))
                result["filtered"] = second_match.group(2) == "Y"
                result["control"] = int(second_match.group(3))
                result["index"] = second_match.group(4)

        return result

    # Try legacy format
    legacy_pattern = r"^([A-Z0-9-]+):(\d+):(\d+):(\d+):(\d+)#([ACGTN0]+)/([12])"
    match = re.match(legacy_pattern, read_name)
    if match:
        instrument_id = match.group(1)
        result = {
            "format": "legacy",
            "instrument": instrument_id,
            "lane": int(match.group(2)),
            "tile": int(match.group(3)),
            "x_pos": int(match.group(4)),
            "y_pos": int(match.group(5)),
            "index": match.group(6),
            "read": int(match.group(7)),
            "instrument_model": infer_illumina_instrument_model(instrument_id),
        }

        # Add archive info if present
        if archive_accession:
            result["archive_accession"] = archive_accession
            result["archive_source"] = archive_source

        return result

    return None


def parse_pacbio_read_name(read_name: str) -> dict | None:
    """
    Parse a PacBio read name into its components.

    CCS/HiFi format:
        @<movie>/<zmw>/ccs

    CLR format:
        @<movie>/<zmw>/<start>_<end>

    Movie name format: m{instrument}_{date}_{time}
        - Sequel: m54XXX_YYMMDD_HHMMSS
        - Sequel II: m64XXX_YYMMDD_HHMMSS
        - Revio: m84XXX_YYMMDD_HHMMSS

    Args:
        read_name: A FASTQ read name line (with or without @ prefix)

    Returns:
        Dict with parsed components or None if not PacBio format
    """
    if read_name.startswith("@"):
        read_name = read_name[1:]

    # CCS/HiFi format: movie/zmw/ccs
    ccs_pattern = r"^(m\d+[A-Za-z]*_\d+_\d+)/(\d+)/ccs"
    match = re.match(ccs_pattern, read_name)
    if match:
        movie = match.group(1)
        instrument_prefix = movie.split("_")[0] if "_" in movie else movie

        # Infer instrument model from prefix
        model = None
        if instrument_prefix.startswith("m84"):
            model = "Revio"
        elif instrument_prefix.startswith("m64"):
            model = "Sequel II/IIe"
        elif instrument_prefix.startswith("m54"):
            model = "Sequel"

        return {
            "format": "ccs",
            "read_type": "CCS",
            "movie": movie,
            "zmw": int(match.group(2)),
            "instrument_model": model,
        }

    # CLR format: movie/zmw/start_end
    clr_pattern = r"^(m\d+[A-Za-z]*_\d+_\d+)/(\d+)/(\d+)_(\d+)"
    match = re.match(clr_pattern, read_name)
    if match:
        movie = match.group(1)
        instrument_prefix = movie.split("_")[0] if "_" in movie else movie

        model = None
        if instrument_prefix.startswith("m84"):
            model = "Revio"
        elif instrument_prefix.startswith("m64"):
            model = "Sequel II/IIe"
        elif instrument_prefix.startswith("m54"):
            model = "Sequel"

        return {
            "format": "clr",
            "read_type": "CLR",
            "movie": movie,
            "zmw": int(match.group(2)),
            "start": int(match.group(3)),
            "end": int(match.group(4)),
            "instrument_model": model,
        }

    # Generic PacBio movie pattern (without /ccs or /start_end)
    generic_pattern = r"^(m\d+[A-Za-z]*_\d+_\d+)/(\d+)"
    match = re.match(generic_pattern, read_name)
    if match:
        movie = match.group(1)
        return {
            "format": "generic",
            "movie": movie,
            "zmw": int(match.group(2)),
        }

    return None


def parse_ont_read_name(read_name: str) -> dict | None:
    """
    Parse an Oxford Nanopore read name into its components.

    UUID format:
        @<uuid> runid=<runid> ...

    Args:
        read_name: A FASTQ read name line (with or without @ prefix)

    Returns:
        Dict with parsed components or None if not ONT format
    """
    if read_name.startswith("@"):
        read_name = read_name[1:]

    # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    uuid_pattern = r"^([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})"
    match = re.match(uuid_pattern, read_name)
    if match:
        result = {
            "format": "ont",
            "uuid": match.group(1),
        }

        # Parse optional metadata fields
        if "runid=" in read_name:
            runid_match = re.search(r"runid=([a-f0-9]+)", read_name)
            if runid_match:
                result["runid"] = runid_match.group(1)

        if "sampleid=" in read_name:
            sample_match = re.search(r"sampleid=([^\s]+)", read_name)
            if sample_match:
                result["sampleid"] = sample_match.group(1)

        if "ch=" in read_name:
            ch_match = re.search(r"ch=(\d+)", read_name)
            if ch_match:
                result["ch"] = ch_match.group(1)

        if "read=" in read_name:
            read_match = re.search(r"read=(\d+)", read_name)
            if read_match:
                result["read"] = read_match.group(1)

        return result

    return None


def detect_reference_from_contig_lengths(
    contig_lines: list[str],
    tolerance: int = 1000
) -> tuple[str | None, int, float]:
    """
    Detect reference genome assembly from @SQ contig lengths.

    Each reference genome has characteristic chromosome lengths. By comparing
    the lengths in the BAM header to known reference lengths, we can identify
    the genome assembly with high confidence.

    Args:
        contig_lines: List of @SQ lines from BAM header
        tolerance: Allowed difference in length (bases) for matching

    Returns:
        Tuple of (assembly_name, matches_found, confidence) where:
        - assembly_name: "GRCh38", "GRCh37", "CHM13", or None
        - matches_found: Number of chromosomes matched
        - confidence: 0.0-1.0 based on match quality
    """
    from .rule_loader import get_unified_rules

    rules = get_unified_rules()
    reference_lengths = rules.reference_contig_lengths

    # Parse contig lengths from @SQ lines
    contig_lengths = {}
    for line in contig_lines:
        sn_match = re.search(r"SN:(\S+)", line)
        ln_match = re.search(r"LN:(\d+)", line)
        if sn_match and ln_match:
            contig_name = sn_match.group(1)
            length = int(ln_match.group(1))
            # Normalize contig names (remove chr prefix if present for comparison)
            normalized = contig_name.lower().replace("chr", "")
            contig_lengths[normalized] = length
            contig_lengths[contig_name] = length

    if not contig_lengths:
        return None, 0, 0.0

    # Score each reference
    scores = {}
    for assembly, ref_lengths in reference_lengths.items():
        matches = 0
        for chrom, expected_len in ref_lengths.items():
            # Try both with and without chr prefix
            normalized = chrom.lower().replace("chr", "")
            actual_len = contig_lengths.get(chrom) or contig_lengths.get(normalized)
            if actual_len and abs(actual_len - expected_len) <= tolerance:
                matches += 1
        if matches > 0:
            scores[assembly] = matches

    if not scores:
        return None, 0, 0.0

    best_matches = max(scores.values())
    # If multiple assemblies tied for best, evidence is ambiguous
    tied = [a for a, m in scores.items() if m == best_matches]
    if len(tied) > 1:
        return None, 0, 0.0

    best_assembly = tied[0]
    # Confidence based on number of matching contigs (not fraction of reference)
    # 1 match = 0.80, 2 = 0.85, 3+ = 0.90, 5+ = 0.95
    if best_matches >= 5:
        best_confidence = 0.95
    elif best_matches >= 3:
        best_confidence = 0.90
    elif best_matches >= 2:
        best_confidence = 0.85
    else:
        best_confidence = 0.80
    return best_assembly, best_matches, best_confidence


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
        file_size_gb=file_size / 1e9 if file_size else None,
        bam_header=header_text,
    )

    # Detect reference from contig lengths first — definitive signal
    lines = header_text.strip().split("\n") if header_text else []
    sq_lines = [l for l in lines if l.startswith("@SQ")]
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

    # Apply contig-based reference (overrides rule-based detection if available)
    if contig_ref:
        result.reference_assembly = contig_ref
        result.confidence = max(result.confidence, contig_conf)
        reason = f"Reference {contig_ref} detected from {contig_matches} matching contig lengths (definitive)"
        result.rules_matched.append("contig_length_detection")
        result.reasons.append(reason)
        result.rule_evidence.append({"rule_id": "contig_length_detection", "reason": reason, "confidence": contig_conf})

    # Infer assay type
    assay_type = engine.infer_assay_type(result, file_info)

    # Build evidence list from matched rules
    evidence = []
    for rule_id in result.rules_matched:
        evidence.append({
            "rule_id": rule_id,
            "matched": True,
        })

    # Check consistency
    consistency = check_consistency(result.rules_matched, evidence)

    # Apply confidence boost/penalty from consistency
    final_confidence = min(1.0, max(0.0, result.confidence + consistency["confidence_boost"]))

    # Default to genomic if platform detected but no modality
    data_modality = result.data_modality
    if data_modality in (None, NOT_CLASSIFIED) and result.platform not in (None, NOT_CLASSIFIED):
        data_modality = "genomic"

    return {
        "data_modality": data_modality,
        "data_type": result.data_type or "alignments",
        "assay_type": assay_type or result.assay_type,
        "reference_assembly": result.reference_assembly,
        "platform": result.platform,
        "confidence": final_confidence,
        "is_aligned": is_aligned,
        "matched_rules": result.rules_matched,
        "reasons": result.reasons,
        "evidence": evidence,
        "consistency": consistency,
    }


def classify_from_vcf_header(
    header_text: str,
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
        file_size_gb=file_size / 1e9 if file_size else None,
        vcf_header=header_text,
    )

    # Detect reference from contig lengths — definitive signal, no guessing.
    from .validators.contig_lengths import detect_reference_from_contig_lengths as detect_from_contigs

    contig_ref = None
    contig_conf = 0.0
    contig_matches = 0
    if header_text:
        contig_lines = [l for l in header_text.split("\n") if l.startswith("##contig")]
        if contig_lines:
            contig_ref, contig_matches, contig_conf = detect_from_contigs(contig_lines)

    # Run classification with tier 3 (header rules)
    engine = _get_engine()
    result = engine.classify_extended(file_info, include_tier3=True)

    # Apply contig-based reference (overrides any rule-based guess)
    if contig_ref:
        result.reference_assembly = contig_ref
        result.confidence = max(result.confidence, contig_conf)
        reason = f"Reference {contig_ref} detected from {contig_matches} matching contig lengths (definitive)"
        result.rules_matched.append("vcf_contig_length")
        result.reasons.append(reason)
        result.rule_evidence.append({"rule_id": "vcf_contig_length", "reason": reason, "confidence": contig_conf})

    # Build evidence list
    evidence = []
    for rule_id in result.rules_matched:
        evidence.append({
            "rule_id": rule_id,
            "matched": True,
        })

    # Default to genomic for VCF files
    data_modality = result.data_modality or "genomic"
    data_type = result.data_type or "germline_variants"

    return {
        "data_modality": data_modality,
        "data_type": data_type,
        "reference_assembly": result.reference_assembly,
        "confidence": result.confidence,
        "matched_rules": result.rules_matched,
        "reasons": result.reasons,
        "evidence": evidence,
    }


def classify_from_fastq_header(
    reads: list[str],
    file_name: str | None = None,
    file_size: int | None = None,
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

    # Handle empty input
    if not reads or not reads[0]:
        return {
            "data_modality": None,
            "data_type": "reads",
            "platform": None,
            "confidence": 0.0,
            "is_paired_end": None,
            "instrument_model": None,
            "instrument_hint": None,
            "archive_accession": None,
            "archive_source": None,
            "matched_rules": [],
            "evidence": [],
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
        file_size_gb=file_size / 1e9 if file_size else None,
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
            result.rules_matched.extend(result_stripped.rules_matched)

    # Build evidence list
    evidence = []
    for rule_id in result.rules_matched:
        evidence.append({
            "rule_id": rule_id,
            "matched": True,
        })

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

    return {
        "data_modality": result.data_modality,
        "data_type": result.data_type or "reads",
        "platform": result.platform,
        "confidence": result.confidence,
        "is_paired_end": is_paired_end,
        "instrument_model": instrument_model,
        "instrument_hint": instrument_hint,
        "archive_accession": archive_accession,
        "archive_source": archive_source,
        "matched_rules": result.rules_matched,
        "evidence": evidence,
    }


def get_rules_documentation() -> str:
    """Generate documentation pointing to the unified rules file."""
    return """# BAM/CRAM, VCF, and FASTQ Header Classification Rules

## Overview

Classification rules are defined in `rules/unified_rules.yaml`.

This file contains all rules organized by:
- **Tier 1**: Extension-based rules (fastest)
- **Tier 2**: Filename pattern and file size rules
- **Tier 3**: Header-based rules (BAM @RG/@PG/@SQ, VCF ##, FASTQ read names)

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
