"""Validators for complex classification logic.

This package contains Python validators for classification logic that is
too complex to express in YAML rules, such as:
- Reference detection from chromosome contig lengths
- Read name parsing for different sequencing platforms
- Header field extraction from BAM/VCF files
"""

from .contig_lengths import (
    REFERENCE_CONTIG_LENGTHS,
    detect_reference_from_contig_lengths,
    detect_reference_from_max_positions,
)
from .header_extractors import (
    SAMHeader,
    VCFHeader,
    parse_sam_header,
    parse_vcf_header,
    extract_sam_field,
    match_sam_header_pattern,
    match_vcf_header_pattern,
    has_sam_section,
    get_contig_lines,
)
from .read_name_parsers import (
    extract_archive_accession,
    infer_illumina_instrument_model,
    parse_illumina_read_name,
    parse_ont_read_name,
    parse_pacbio_read_name,
    parse_mgi_read_name,
    detect_paired_end_indicators,
    detect_platform_from_read_name,
)

__all__ = [
    # Contig length validators
    "REFERENCE_CONTIG_LENGTHS",
    "detect_reference_from_contig_lengths",
    "detect_reference_from_max_positions",
    # Header extractors
    "SAMHeader",
    "VCFHeader",
    "parse_sam_header",
    "parse_vcf_header",
    "extract_sam_field",
    "match_sam_header_pattern",
    "match_vcf_header_pattern",
    "has_sam_section",
    "get_contig_lines",
    # Read name parsers
    "extract_archive_accession",
    "infer_illumina_instrument_model",
    "parse_illumina_read_name",
    "parse_ont_read_name",
    "parse_pacbio_read_name",
    "parse_mgi_read_name",
    "detect_paired_end_indicators",
    "detect_platform_from_read_name",
]
