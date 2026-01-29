"""Read name parsers for different sequencing platforms.

These functions parse FASTQ read names to extract platform-specific
information like instrument ID, run number, flowcell, ZMW, etc.
"""

import re


# Illumina instrument ID prefix -> model name mapping
# Order matters: more specific prefixes (A0, A1, VH) must come before less specific (A, N)
ILLUMINA_INSTRUMENT_RULES = [
    {"prefix": "A0", "model": "NovaSeq 6000"},
    {"prefix": "A1", "model": "NovaSeq 6000"},
    {"prefix": "A", "model": "NovaSeq"},
    {"prefix": "M", "model": "MiSeq"},
    {"prefix": "D", "model": "HiSeq 2500"},
    {"prefix": "E", "model": "HiSeq X"},
    {"prefix": "VH", "model": "NextSeq 2000"},
    {"prefix": "N", "model": "NextSeq"},
    {"prefix": "K", "model": "HiSeq 4000"},
    {"prefix": "J", "model": "HiSeq 3000"},
]


def extract_archive_accession(read_name: str) -> tuple[str | None, str | None, str]:
    """
    Extract ENA/SRA/DDBJ accession from a FASTQ read name.

    When data is submitted to ENA/SRA/DDBJ, read names get prefixed with
    accession IDs but the original instrument info is usually preserved
    after a space.

    Args:
        read_name: A FASTQ read name line (with or without @ prefix)

    Returns:
        Tuple of (accession, source, remainder) where:
        - accession: e.g., "ERR3242571" or None if not found
        - source: "ENA", "SRA", or "DDBJ" or None if not found
        - remainder: The text after the accession (original read name), or full input if no accession
    """
    archive_sources = {"ERR": "ENA", "SRR": "SRA", "DRR": "DDBJ"}
    pattern = re.compile(r"^@?(ERR|SRR|DRR)(\d+)\.\d+\s*(.*)$")

    match = pattern.match(read_name)
    if match:
        prefix, acc_num, remainder = match.groups()
        return f"{prefix}{acc_num}", archive_sources[prefix], remainder.strip()

    # No accession found
    return None, None, read_name.lstrip("@")


def infer_illumina_instrument_model(instrument_id: str) -> str | None:
    """
    Infer Illumina instrument model from instrument ID prefix.

    Uses ILLUMINA_INSTRUMENT_RULES for prefix matching.
    Order matters: more specific prefixes are checked first.

    Args:
        instrument_id: The instrument identifier (e.g., "A00297")

    Returns:
        Instrument model name or None if unknown
    """
    if not instrument_id:
        return None

    inst = instrument_id.upper()

    for rule in ILLUMINA_INSTRUMENT_RULES:
        if inst.startswith(rule["prefix"]):
            return rule["model"]

    return None


def detect_paired_end_indicators(text: str) -> bool:
    """
    Check if text contains paired-end read indicators.

    Args:
        text: Read name or filename to check

    Returns:
        True if paired-end indicators found
    """
    patterns = [
        r"[/\s][12]$",       # /1 or /2 at end
        r"[/\s][12]:",       # /1: or /2:
        r"_R[12]_",          # _R1_ or _R2_
        r"\.R[12]\.",        # .R1. or .R2.
        r"_r[12]_",          # _r1_ or _r2_
        r"\.r[12]\.",        # .r1. or .r2.
        r"_[12]\.fastq",     # _1.fastq or _2.fastq
    ]
    return any(re.search(p, text) for p in patterns)


def parse_illumina_read_name(read_name: str) -> dict | None:
    """
    Parse an Illumina read name into its components.

    Modern format (Casava 1.8+):
        @instrument:run:flowcell:lane:tile:x:y read:filtered:control:index

    Legacy format:
        @instrument:lane:tile:x:y#index/read

    Args:
        read_name: FASTQ read name starting with @

    Returns:
        Dict with parsed fields or None if not Illumina format
    """
    # Strip @ prefix if present
    name = read_name.lstrip("@")

    # Check for archive-reformatted reads first
    accession, source, remainder = extract_archive_accession(read_name)
    if accession:
        name = remainder

    # Modern Illumina format: instrument:run:flowcell:lane:tile:x:y [read:filtered:control:index]
    modern_pattern = re.compile(
        r"^([A-Z0-9-]+):(\d+):([A-Z0-9]+):(\d+):(\d+):(\d+):(\d+)"
        r"(?:\s+(\d):([YN]):(\d+):([ACGTN+]+))?$"
    )
    match = modern_pattern.match(name)
    if match:
        groups = match.groups()
        result = {
            "format": "modern",
            "instrument": groups[0],
            "run_number": int(groups[1]),
            "flowcell": groups[2],
            "lane": int(groups[3]),
            "tile": int(groups[4]),
            "x": int(groups[5]),
            "y": int(groups[6]),
        }
        if groups[7]:  # Optional second part
            result.update({
                "read": int(groups[7]),
                "filtered": groups[8] == "Y",
                "control": int(groups[9]),
                "index": groups[10],
            })
        if accession:
            result["archive_accession"] = accession
            result["archive_source"] = source
        return result

    # Legacy Illumina format: instrument:lane:tile:x:y#index/read
    legacy_pattern = re.compile(
        r"^([A-Z0-9-]+):(\d+):(\d+):(\d+):(\d+)#([^/]+)/(\d)$"
    )
    match = legacy_pattern.match(name)
    if match:
        groups = match.groups()
        result = {
            "format": "legacy",
            "instrument": groups[0],
            "lane": int(groups[1]),
            "tile": int(groups[2]),
            "x": int(groups[3]),
            "y": int(groups[4]),
            "index": groups[5],
            "read": int(groups[6]),
        }
        if accession:
            result["archive_accession"] = accession
            result["archive_source"] = source
        return result

    return None


def parse_pacbio_read_name(read_name: str) -> dict | None:
    """
    Parse a PacBio read name into its components.

    CCS/HiFi format:
        @movie/zmw/ccs

    CLR (subread) format:
        @movie/zmw/start_end

    Args:
        read_name: FASTQ read name starting with @

    Returns:
        Dict with parsed fields or None if not PacBio format
    """
    name = read_name.lstrip("@")

    # PacBio movie ID pattern: m{instrument}_{date}_{time}
    # Instrument IDs include:
    #   m64011   - Sequel
    #   m54329U  - Sequel II (U suffix)
    #   m54306Ue - Sequel IIe (Ue suffix)
    #   m84046   - Revio
    MOVIE_PATTERN = r"m\d+[A-Za-z]*_\d+_\d+"

    # CCS format: m64011_190830_220126/1/ccs or m54329U_220116_013607/102/ccs
    ccs_pattern = re.compile(rf"^({MOVIE_PATTERN})/(\d+)/ccs$")
    match = ccs_pattern.match(name)
    if match:
        return {
            "format": "ccs",
            "movie": match.group(1),
            "zmw": int(match.group(2)),
            "read_type": "CCS",
        }

    # CLR (subread) format: m64011_190830_220126/1234/0_5000
    clr_pattern = re.compile(rf"^({MOVIE_PATTERN})/(\d+)/(\d+)_(\d+)$")
    match = clr_pattern.match(name)
    if match:
        return {
            "format": "clr",
            "movie": match.group(1),
            "zmw": int(match.group(2)),
            "start": int(match.group(3)),
            "end": int(match.group(4)),
            "read_type": "CLR",
        }

    # Generic PacBio: m64011_190830_220126/1234
    generic_pattern = re.compile(rf"^({MOVIE_PATTERN})/(\d+)$")
    match = generic_pattern.match(name)
    if match:
        return {
            "format": "generic",
            "movie": match.group(1),
            "zmw": int(match.group(2)),
        }

    return None


def parse_ont_read_name(read_name: str) -> dict | None:
    """
    Parse an Oxford Nanopore read name into its components.

    ONT format:
        @uuid [key=value pairs]

    Args:
        read_name: FASTQ read name starting with @

    Returns:
        Dict with parsed fields or None if not ONT format
    """
    name = read_name.lstrip("@")

    # UUID pattern: 8-4-4-4-12 hex characters
    uuid_pattern = re.compile(
        r"^([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\s*(.*)$"
    )
    match = uuid_pattern.match(name)
    if match:
        result = {
            "format": "ont",
            "uuid": match.group(1),
        }
        # Parse key=value pairs if present
        metadata = match.group(2)
        if metadata:
            pairs = re.findall(r"(\w+)=([^\s]+)", metadata)
            for key, value in pairs:
                result[key] = value
        return result

    return None


def parse_mgi_read_name(read_name: str) -> dict | None:
    """
    Parse an MGI/BGI read name into its components.

    MGI format:
        @flowcellLaneCcolumnRrow/pair

    Args:
        read_name: FASTQ read name starting with @

    Returns:
        Dict with parsed fields or None if not MGI format
    """
    name = read_name.lstrip("@")

    # MGI pattern: V350012345L1C001R0010000001/1
    mgi_pattern = re.compile(
        r"^([A-Z]\d+)L(\d+)C(\d+)R(\d+)(\d+)(?:/(\d))?$"
    )
    match = mgi_pattern.match(name)
    if match:
        groups = match.groups()
        result = {
            "format": "mgi",
            "flowcell": groups[0],
            "lane": int(groups[1]),
            "column": int(groups[2]),
            "row": int(groups[3]),
            "read_number": int(groups[4]),
        }
        if groups[5]:
            result["pair"] = int(groups[5])
        return result

    return None


def detect_platform_from_read_name(read_name: str) -> str | None:
    """
    Detect sequencing platform from a FASTQ read name.

    Args:
        read_name: FASTQ read name starting with @

    Returns:
        Platform name ("ILLUMINA", "PACBIO", "ONT", "MGI") or None if unknown
    """
    if parse_illumina_read_name(read_name):
        return "ILLUMINA"
    if parse_pacbio_read_name(read_name):
        return "PACBIO"
    if parse_ont_read_name(read_name):
        return "ONT"
    if parse_mgi_read_name(read_name):
        return "MGI"
    return None
