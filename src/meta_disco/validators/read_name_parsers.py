"""Read name parsers for different sequencing platforms.

These functions parse FASTQ read names to extract platform-specific
information like instrument ID, run number, flowcell, ZMW, etc.

Each parser returns a frozen per-platform dataclass (or None if the read
name does not match that platform), so the fields a branch produces are
declared in one place instead of assembled ad hoc into a bare dict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class IlluminaFormat(Enum):
    """Illumina read-name layout: modern (Casava 1.8+) or legacy."""

    MODERN = "modern"
    LEGACY = "legacy"


class PacBioFormat(Enum):
    """PacBio read-name layout: CCS/HiFi, CLR subread, or generic."""

    CCS = "ccs"
    CLR = "clr"
    GENERIC = "generic"


@dataclass(frozen=True)
class IlluminaReadName:
    """Parsed Illumina read name.

    Covers both modern and legacy layouts in one type: ``run_number`` and
    ``flowcell`` are modern-only and stay None for legacy reads; the second
    modern block (``read``/``filtered``/``control``/``index``) is optional;
    archive fields are set only for ENA/SRA/DDBJ-reformatted reads.
    """

    format: IlluminaFormat
    instrument: str
    instrument_model: str | None
    lane: int
    tile: int
    x: int
    y: int
    run_number: int | None = None
    flowcell: str | None = None
    read: int | None = None
    filtered: bool | None = None
    control: int | None = None
    index: str | None = None
    archive_accession: str | None = None
    archive_source: str | None = None


@dataclass(frozen=True)
class PacBioReadName:
    """Parsed PacBio read name; ``start``/``end`` are CLR-only."""

    format: PacBioFormat
    movie: str
    zmw: int
    instrument_model: str | None
    read_type: str | None = None
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class OntReadName:
    """Parsed Oxford Nanopore read name.

    ``uuid`` is the fixed spine; the arbitrary trailing ``key=value`` pairs
    are kept under ``metadata`` rather than flattened onto attributes.
    """

    uuid: str
    metadata: dict[str, str] = field(default_factory=dict)
    format: str = "ont"


@dataclass(frozen=True)
class MgiReadName:
    """Parsed MGI/BGI read name."""

    flowcell: str
    lane: int
    column: int
    row: int
    read_number: int
    pair: int | None = None
    format: str = "mgi"


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
    archive_sources = {
        "ERR": "ENA",
        "ERS": "ENA",
        "SRR": "SRA",
        "SRS": "SRA",
        "DRR": "DDBJ",
        "DRS": "DDBJ",
    }
    pattern = re.compile(r"^@?(ERR|ERS|SRR|SRS|DRR|DRS)(\d+)(?:\.\d+)?\s*(.*)$")

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
        r"[/\s][12]$",  # /1 or /2 at end
        r"[/\s][12]:",  # /1: or /2:
        r"_R[12]_",  # _R1_ or _R2_
        r"_R[12]\.",  # _R1. or _R2.
        r"\.R[12]\.",  # .R1. or .R2.
        r"_[12]\.fastq",  # _1.fastq or _2.fastq
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def parse_illumina_read_name(read_name: str) -> IlluminaReadName | None:
    """
    Parse an Illumina read name into its components.

    Modern format (Casava 1.8+):
        @instrument:run:flowcell:lane:tile:x:y read:filtered:control:index

    Legacy format:
        @instrument:lane:tile:x:y#index/read

    Args:
        read_name: FASTQ read name starting with @

    Returns:
        IlluminaReadName or None if not Illumina format
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
        r"(?:\s+(\d):([YN]):(\d+):([ACGTN+]+))?"
    )
    match = modern_pattern.match(name)
    if match:
        groups = match.groups()
        instrument_id = groups[0]
        # Optional second block: read:filtered:control:index
        read = filtered = control = index = None
        if groups[7]:
            read = int(groups[7])
            filtered = groups[8] == "Y"
            control = int(groups[9])
            index = groups[10]
        return IlluminaReadName(
            format=IlluminaFormat.MODERN,
            instrument=instrument_id,
            instrument_model=infer_illumina_instrument_model(instrument_id),
            run_number=int(groups[1]),
            flowcell=groups[2],
            lane=int(groups[3]),
            tile=int(groups[4]),
            x=int(groups[5]),
            y=int(groups[6]),
            read=read,
            filtered=filtered,
            control=control,
            index=index,
            archive_accession=accession,
            archive_source=source,
        )

    # Legacy Illumina format: instrument:lane:tile:x:y#index/read
    legacy_pattern = re.compile(r"^([A-Z0-9-]+):(\d+):(\d+):(\d+):(\d+)#([^/]+)/(\d)$")
    match = legacy_pattern.match(name)
    if match:
        groups = match.groups()
        instrument_id = groups[0]
        return IlluminaReadName(
            format=IlluminaFormat.LEGACY,
            instrument=instrument_id,
            instrument_model=infer_illumina_instrument_model(instrument_id),
            lane=int(groups[1]),
            tile=int(groups[2]),
            x=int(groups[3]),
            y=int(groups[4]),
            index=groups[5],
            read=int(groups[6]),
            archive_accession=accession,
            archive_source=source,
        )

    return None


def _infer_pacbio_instrument_model(movie: str) -> str | None:
    """Infer PacBio instrument model from movie name prefix."""
    prefix = movie.split("_")[0] if "_" in movie else movie
    if prefix.startswith("m84"):
        return "Revio"
    if prefix.startswith("m64"):
        return "Sequel II/IIe"
    if prefix.startswith("m54"):
        return "Sequel"
    return None


def parse_pacbio_read_name(read_name: str) -> PacBioReadName | None:
    """
    Parse a PacBio read name into its components.

    CCS/HiFi format:
        @movie/zmw/ccs

    CLR (subread) format:
        @movie/zmw/start_end

    Args:
        read_name: FASTQ read name starting with @

    Returns:
        PacBioReadName or None if not PacBio format
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
        movie = match.group(1)
        return PacBioReadName(
            format=PacBioFormat.CCS,
            movie=movie,
            zmw=int(match.group(2)),
            read_type="CCS",
            instrument_model=_infer_pacbio_instrument_model(movie),
        )

    # CLR (subread) format: m64011_190830_220126/1234/0_5000
    clr_pattern = re.compile(rf"^({MOVIE_PATTERN})/(\d+)/(\d+)_(\d+)$")
    match = clr_pattern.match(name)
    if match:
        movie = match.group(1)
        return PacBioReadName(
            format=PacBioFormat.CLR,
            movie=movie,
            zmw=int(match.group(2)),
            start=int(match.group(3)),
            end=int(match.group(4)),
            read_type="CLR",
            instrument_model=_infer_pacbio_instrument_model(movie),
        )

    # Generic PacBio: m64011_190830_220126/1234
    generic_pattern = re.compile(rf"^({MOVIE_PATTERN})/(\d+)$")
    match = generic_pattern.match(name)
    if match:
        movie = match.group(1)
        return PacBioReadName(
            format=PacBioFormat.GENERIC,
            movie=movie,
            zmw=int(match.group(2)),
            instrument_model=_infer_pacbio_instrument_model(movie),
        )

    return None


def parse_ont_read_name(read_name: str) -> OntReadName | None:
    """
    Parse an Oxford Nanopore read name into its components.

    ONT format:
        @uuid [key=value pairs]

    Args:
        read_name: FASTQ read name starting with @

    Returns:
        OntReadName or None if not ONT format
    """
    name = read_name.lstrip("@")

    # UUID pattern: 8-4-4-4-12 hex characters
    uuid_pattern = re.compile(r"^([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\s*(.*)$")
    match = uuid_pattern.match(name)
    if match:
        # Parse arbitrary key=value pairs if present
        metadata = dict(re.findall(r"(\w+)=([^\s]+)", match.group(2)))
        return OntReadName(uuid=match.group(1), metadata=metadata)

    return None


def parse_mgi_read_name(read_name: str) -> MgiReadName | None:
    """
    Parse an MGI/BGI read name into its components.

    MGI format:
        @flowcellLaneCcolumnRrow/pair

    Args:
        read_name: FASTQ read name starting with @

    Returns:
        MgiReadName or None if not MGI format
    """
    name = read_name.lstrip("@")

    # MGI pattern: V350012345L1C001R0010000001/1
    mgi_pattern = re.compile(r"^([A-Z]\d+)L(\d+)C(\d+)R(\d+)(\d+)(?:/(\d))?$")
    match = mgi_pattern.match(name)
    if match:
        groups = match.groups()
        return MgiReadName(
            flowcell=groups[0],
            lane=int(groups[1]),
            column=int(groups[2]),
            row=int(groups[3]),
            read_number=int(groups[4]),
            pair=int(groups[5]) if groups[5] else None,
        )

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
