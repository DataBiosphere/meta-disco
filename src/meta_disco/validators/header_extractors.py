"""Header field extraction from BAM/VCF files.

These functions extract specific fields from SAM/BAM headers and VCF headers
for use in classification rules.
"""

import re
from dataclasses import dataclass
from typing import Iterator


@dataclass
class SAMHeader:
    """Parsed SAM/BAM header."""

    hd: dict[str, str] | None = None  # @HD header line
    sq: list[dict[str, str]] | None = None  # @SQ sequence dictionary
    rg: list[dict[str, str]] | None = None  # @RG read groups
    pg: list[dict[str, str]] | None = None  # @PG programs
    co: list[str] | None = None  # @CO comments


@dataclass
class VCFHeader:
    """Parsed VCF header."""

    fileformat: str | None = None  # ##fileformat
    reference: str | None = None  # ##reference
    contigs: list[dict[str, str]] | None = None  # ##contig lines
    source: str | None = None  # ##source
    info_fields: list[dict[str, str]] | None = None  # ##INFO fields
    format_fields: list[dict[str, str]] | None = None  # ##FORMAT fields
    filter_fields: list[dict[str, str]] | None = None  # ##FILTER fields
    other_meta: list[str] | None = None  # Other ## lines


def parse_sam_header_line(line: str) -> tuple[str, dict[str, str]] | None:
    """
    Parse a single SAM header line into its components.

    Args:
        line: A SAM header line starting with @

    Returns:
        Tuple of (record_type, fields_dict) or None if invalid
    """
    if not line.startswith("@"):
        return None

    parts = line.split("\t")
    record_type = parts[0]  # e.g., @HD, @SQ, @RG, @PG

    fields = {}
    for part in parts[1:]:
        if ":" in part:
            key, value = part.split(":", 1)
            fields[key] = value

    return record_type, fields


def parse_sam_header(header_text: str) -> SAMHeader:
    """
    Parse a complete SAM/BAM header.

    Args:
        header_text: The full header text with newline-separated lines

    Returns:
        SAMHeader object with parsed fields
    """
    header = SAMHeader()
    sq_list = []
    rg_list = []
    pg_list = []
    co_list = []

    for line in header_text.strip().split("\n"):
        if not line.startswith("@"):
            continue

        result = parse_sam_header_line(line)
        if result is None:
            continue

        record_type, fields = result

        if record_type == "@HD":
            header.hd = fields
        elif record_type == "@SQ":
            sq_list.append(fields)
        elif record_type == "@RG":
            rg_list.append(fields)
        elif record_type == "@PG":
            pg_list.append(fields)
        elif record_type == "@CO":
            # Comments don't have key:value format
            co_list.append(line[4:])  # Skip "@CO\t"

    if sq_list:
        header.sq = sq_list
    if rg_list:
        header.rg = rg_list
    if pg_list:
        header.pg = pg_list
    if co_list:
        header.co = co_list

    return header


def extract_sam_field(header: SAMHeader, section: str, field: str) -> list[str]:
    """
    Extract all values of a specific field from a SAM header section.

    Args:
        header: Parsed SAMHeader object
        section: Section name (@HD, @SQ, @RG, @PG)
        field: Field name (e.g., PL, PN, SN, AS)

    Returns:
        List of field values found (may be empty)
    """
    values = []

    if section == "@HD" and header.hd:
        if field in header.hd:
            values.append(header.hd[field])
    elif section == "@SQ" and header.sq:
        for sq in header.sq:
            if field in sq:
                values.append(sq[field])
    elif section == "@RG" and header.rg:
        for rg in header.rg:
            if field in rg:
                values.append(rg[field])
    elif section == "@PG" and header.pg:
        for pg in header.pg:
            if field in pg:
                values.append(pg[field])

    return values


def match_sam_header_pattern(
    header: SAMHeader,
    section: str,
    field: str,
    pattern: str
) -> bool:
    """
    Check if any value in a SAM header field matches a regex pattern.

    Args:
        header: Parsed SAMHeader object
        section: Section name (@HD, @SQ, @RG, @PG)
        field: Field name (e.g., PL, PN, SN)
        pattern: Regex pattern to match

    Returns:
        True if any field value matches the pattern
    """
    values = extract_sam_field(header, section, field)
    compiled = re.compile(pattern, re.IGNORECASE)
    return any(compiled.search(v) for v in values)


def has_sam_section(header: SAMHeader, section: str) -> bool:
    """
    Check if a SAM header has a specific section.

    Args:
        header: Parsed SAMHeader object
        section: Section name (@HD, @SQ, @RG, @PG)

    Returns:
        True if the section exists and has entries
    """
    if section == "@HD":
        return header.hd is not None
    elif section == "@SQ":
        return header.sq is not None and len(header.sq) > 0
    elif section == "@RG":
        return header.rg is not None and len(header.rg) > 0
    elif section == "@PG":
        return header.pg is not None and len(header.pg) > 0
    elif section == "@CO":
        return header.co is not None and len(header.co) > 0
    return False


def parse_vcf_header_line(line: str) -> dict[str, str] | None:
    """
    Parse a VCF header line with ID=value,Description="..." format.

    Args:
        line: A VCF header line like ##INFO=<ID=DP,Number=1,Type=Integer,...>

    Returns:
        Dict of parsed fields or None if not parseable
    """
    # Match ##TYPE=<...> format
    match = re.match(r'^##(\w+)=<(.*)>$', line)
    if not match:
        # Handle simple key=value format like ##fileformat=VCFv4.2
        simple_match = re.match(r'^##(\w+)=(.*)$', line)
        if simple_match:
            return {"_type": simple_match.group(1), "_value": simple_match.group(2)}
        return None

    header_type = match.group(1)
    content = match.group(2)

    # Parse key=value pairs (handling quoted values)
    fields = {"_type": header_type}

    # Pattern for key=value or key="value with spaces"
    pattern = r'(\w+)=("[^"]*"|[^,]*)'
    for key, value in re.findall(pattern, content):
        # Remove quotes if present
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        fields[key] = value

    return fields


def parse_vcf_header(header_text: str) -> VCFHeader:
    """
    Parse VCF header lines into a structured object.

    Args:
        header_text: VCF header text (lines starting with ##)

    Returns:
        VCFHeader object with parsed fields
    """
    header = VCFHeader()
    contigs = []
    info_fields = []
    format_fields = []
    filter_fields = []
    other_meta = []

    for line in header_text.strip().split("\n"):
        if not line.startswith("##"):
            continue

        parsed = parse_vcf_header_line(line)
        if parsed is None:
            continue

        header_type = parsed.get("_type", "")

        if header_type == "fileformat":
            header.fileformat = parsed.get("_value")
        elif header_type == "reference":
            header.reference = parsed.get("_value")
        elif header_type == "source":
            header.source = parsed.get("_value")
        elif header_type == "contig":
            contigs.append(parsed)
        elif header_type == "INFO":
            info_fields.append(parsed)
        elif header_type == "FORMAT":
            format_fields.append(parsed)
        elif header_type == "FILTER":
            filter_fields.append(parsed)
        else:
            other_meta.append(line)

    if contigs:
        header.contigs = contigs
    if info_fields:
        header.info_fields = info_fields
    if format_fields:
        header.format_fields = format_fields
    if filter_fields:
        header.filter_fields = filter_fields
    if other_meta:
        header.other_meta = other_meta

    return header


def match_vcf_header_pattern(
    header: VCFHeader,
    header_type: str,
    pattern: str
) -> bool:
    """
    Check if any VCF header line of a given type matches a pattern.

    Args:
        header: Parsed VCFHeader object
        header_type: Type of header line (##reference, ##source, ##contig, ##INFO, ##FORMAT)
        pattern: Regex pattern to match

    Returns:
        True if any matching header line contains the pattern
    """
    compiled = re.compile(pattern, re.IGNORECASE)

    if header_type == "##reference" and header.reference:
        return bool(compiled.search(header.reference))
    elif header_type == "##source" and header.source:
        return bool(compiled.search(header.source))
    elif header_type == "##contig" and header.contigs:
        for contig in header.contigs:
            # Check all fields in the contig line
            for key, value in contig.items():
                if compiled.search(str(value)):
                    return True
    elif header_type == "##INFO" and header.info_fields:
        for info in header.info_fields:
            if "ID" in info and compiled.search(info["ID"]):
                return True
    elif header_type == "##FORMAT" and header.format_fields:
        for fmt in header.format_fields:
            if "ID" in fmt and compiled.search(fmt["ID"]):
                return True
    elif header_type == "##FILTER" and header.filter_fields:
        for flt in header.filter_fields:
            if "ID" in flt and compiled.search(flt["ID"]):
                return True
    elif header.other_meta:
        # header_type already includes ## prefix (e.g., "##reference")
        for line in header.other_meta:
            if line.startswith(header_type) and compiled.search(line):
                return True

    return False


def get_contig_lines(header: VCFHeader) -> list[str]:
    """
    Get contig lines from a VCF header in the original format.

    Args:
        header: Parsed VCFHeader object

    Returns:
        List of ##contig=<...> lines
    """
    if not header.contigs:
        return []

    lines = []
    for contig in header.contigs:
        # Reconstruct the line
        parts = []
        for key, value in contig.items():
            if key.startswith("_"):
                continue
            parts.append(f"{key}={value}")
        lines.append(f"##contig=<{','.join(parts)}>")

    return lines
