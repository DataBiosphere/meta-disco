"""BAM/CRAM and VCF header-based classification rules with rationales."""

import re
from dataclasses import dataclass, field


# =============================================================================
# RULE DEFINITIONS (externalized for configurability)
# =============================================================================

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

# Assay type inference rules (priority-ordered, first match wins)
# Conditions supported:
#   - matched_rules_any: list of rule IDs, any must be in matched_rules
#   - data_modality: exact match
#   - data_modality_contains: substring match
#   - platform: exact match
#   - platform_in: list of platforms, any must match
#   - file_size_gb_gt: file size greater than (in GB)
#   - file_size_gb_lt: file size less than (in GB)
#   - file_format: exact match (e.g., ".cram")
ASSAY_TYPE_RULES = [
    {
        "id": "rnaseq_program",
        "priority": 100,
        "conditions": {
            "matched_rules_any": [
                "program_star", "program_hisat2", "program_tophat",
                "program_salmon", "program_kallisto", "program_isoseq"
            ]
        },
        "assay_type": "RNA-seq",
    },
    {
        "id": "rnaseq_modality",
        "priority": 95,
        "conditions": {"data_modality_contains": "transcriptomic"},
        "assay_type": "RNA-seq",
    },
    {
        "id": "wgs_longread",
        "priority": 80,
        "conditions": {"platform_in": ["PACBIO", "ONT"]},
        "assay_type": "WGS",
    },
    {
        "id": "wgs_illumina_bam_large",
        "priority": 50,
        "conditions": {"platform": "ILLUMINA", "file_format_not": ".cram", "file_size_gb_gt": 50},
        "assay_type": "WGS",
    },
    {
        "id": "wes_illumina_bam_small",
        "priority": 50,
        "conditions": {"platform": "ILLUMINA", "file_format_not": ".cram", "file_size_gb_lt": 20},
        "assay_type": "WES",
    },
    {
        "id": "wgs_illumina_cram_large",
        "priority": 50,
        "conditions": {"platform": "ILLUMINA", "file_format": ".cram", "file_size_gb_gt": 20},
        "assay_type": "WGS",
    },
    {
        "id": "wes_illumina_cram_small",
        "priority": 50,
        "conditions": {"platform": "ILLUMINA", "file_format": ".cram", "file_size_gb_lt": 8},
        "assay_type": "WES",
    },
]


# =============================================================================
# HELPER FUNCTIONS (extracted for testability)
# =============================================================================

def extract_archive_accession(read_name: str) -> tuple[str | None, str | None, str]:
    """
    Extract ENA/SRA/DDBJ accession from a FASTQ read name.

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


@dataclass
class HeaderRule:
    """A classification rule based on BAM header content."""
    id: str
    header_section: str  # @HD, @RG, @PG, @SQ
    field: str | None    # e.g., PL, PN, SN
    pattern: str | None  # regex or substring to match
    classification: str | None  # modality or reference
    confidence: float
    rationale: str       # explanation of why this indicates the classification


@dataclass
class VCFHeaderRule:
    """A classification rule based on VCF header content."""
    id: str
    header_type: str     # ##reference, ##source, ##contig, ##INFO, ##FORMAT
    pattern: str         # regex pattern to match
    classification: str | None  # modality, reference, or variant_type
    confidence: float
    rationale: str


# =============================================================================
# HEADER FIELD REFERENCE
# =============================================================================
#
# @HD (Header) - File-level metadata
#   VN: SAM format version
#   SO: Sort order (coordinate, queryname, unsorted, unknown)
#
# @SQ (Sequence Dictionary) - Reference sequences the reads are aligned to
#   SN: Sequence name (e.g., chr1, NC_000001.11)
#   LN: Sequence length
#   AS: Genome assembly identifier (e.g., GRCh38)
#   M5: MD5 checksum of sequence
#   SP: Species
#   UR: URI of the sequence
#
# @RG (Read Group) - Metadata about a set of reads
#   ID: Read group identifier
#   PL: Platform/technology (ILLUMINA, PACBIO, ONT, etc.)
#   PM: Platform model (e.g., SEQUELII, NovaSeq, MinION)
#   PU: Platform unit (flowcell-barcode.lane)
#   LB: Library name
#   SM: Sample name
#   DS: Description (PacBio uses this for READTYPE=CCS, etc.)
#   CN: Sequencing center
#   DT: Date of sequencing
#
# @PG (Program) - Software used to create/modify the file
#   ID: Program record identifier
#   PN: Program name
#   VN: Program version
#   CL: Command line
#   PP: Previous program ID (for tracking pipeline order)
#
# =============================================================================


# Platform rules - from @RG PL field
PLATFORM_RULES = [
    HeaderRule(
        id="platform_pacbio",
        header_section="@RG",
        field="PL",
        pattern="PACBIO",
        classification="genomic",  # Default, refined by read type
        confidence=0.70,
        rationale="PL:PACBIO indicates PacBio long-read sequencing. PacBio is primarily "
                  "used for whole genome sequencing, structural variant detection, and "
                  "de novo assembly due to its long read lengths (10-25kb average for HiFi). "
                  "Can also be used for IsoSeq (transcriptomics) but this is less common."
    ),
    HeaderRule(
        id="platform_illumina",
        header_section="@RG",
        field="PL",
        pattern="ILLUMINA",
        classification=None,  # Ambiguous - Illumina does WGS, WES, RNA-seq, ChIP-seq, etc.
        confidence=0.0,
        rationale="PL:ILLUMINA indicates Illumina short-read sequencing. Illumina platforms "
                  "are used for diverse applications including WGS, WES, RNA-seq, ChIP-seq, "
                  "ATAC-seq, bisulfite sequencing, and more. Platform alone is insufficient "
                  "to determine modality - requires program info or study context."
    ),
    HeaderRule(
        id="platform_ont",
        header_section="@RG",
        field="PL",
        pattern="ONT",
        classification="genomic",  # Default for Oxford Nanopore
        confidence=0.70,
        rationale="PL:ONT indicates Oxford Nanopore long-read sequencing. ONT is primarily "
                  "used for whole genome sequencing, structural variants, and direct RNA "
                  "sequencing. The ultra-long reads (>100kb possible) make it valuable for "
                  "resolving complex genomic regions and phasing."
    ),
    HeaderRule(
        id="platform_ont_alt",
        header_section="@RG",
        field="PL",
        pattern="NANOPORE",
        classification="genomic",
        confidence=0.70,
        rationale="Alternative platform identifier for Oxford Nanopore Technology."
    ),
]


# PacBio read type rules - from @RG DS field
PACBIO_READTYPE_RULES = [
    HeaderRule(
        id="pacbio_hifi",
        header_section="@RG",
        field="DS",
        pattern="READTYPE=CCS",
        classification="genomic",
        confidence=0.85,
        rationale="READTYPE=CCS indicates PacBio HiFi (High-Fidelity) reads. CCS (Circular "
                  "Consensus Sequencing) generates highly accurate long reads (>Q20, ~99% accuracy) "
                  "by sequencing the same molecule multiple times. HiFi is the current standard "
                  "for PacBio WGS, used extensively in projects like HPRC for diploid assembly."
    ),
    HeaderRule(
        id="pacbio_clr",
        header_section="@RG",
        field="DS",
        pattern="READTYPE=SUBREAD",
        classification="genomic",
        confidence=0.80,
        rationale="READTYPE=SUBREAD indicates PacBio CLR (Continuous Long Read) data. "
                  "These are raw subreads from a single pass around the circular molecule, "
                  "longer but less accurate than HiFi. Still used for some assembly applications."
    ),
]


# RNA-seq aligner programs - from @PG PN field
RNASEQ_PROGRAM_RULES = [
    HeaderRule(
        id="program_star",
        header_section="@PG",
        field="PN",
        pattern="STAR",
        classification="transcriptomic.bulk",
        confidence=0.95,
        rationale="STAR (Spliced Transcripts Alignment to a Reference) is the most widely "
                  "used RNA-seq aligner. It performs splice-aware alignment essential for "
                  "mapping reads across exon-exon junctions. Presence of STAR in @PG strongly "
                  "indicates RNA-seq data."
    ),
    HeaderRule(
        id="program_hisat2",
        header_section="@PG",
        field="PN",
        pattern="hisat2",
        classification="transcriptomic.bulk",
        confidence=0.95,
        rationale="HISAT2 is a splice-aware aligner optimized for RNA-seq. It uses a graph-based "
                  "index that incorporates known splice sites and SNPs. Like STAR, its presence "
                  "strongly indicates transcriptomic data."
    ),
    HeaderRule(
        id="program_tophat",
        header_section="@PG",
        field="PN",
        pattern="tophat",
        classification="transcriptomic.bulk",
        confidence=0.95,
        rationale="TopHat was an early splice-aware aligner for RNA-seq (now superseded by "
                  "HISAT2). It identifies splice junctions and aligns reads across them. "
                  "Legacy RNA-seq data may still have TopHat in the header."
    ),
    HeaderRule(
        id="program_salmon",
        header_section="@PG",
        field="PN",
        pattern="salmon",
        classification="transcriptomic.bulk",
        confidence=0.95,
        rationale="Salmon is a transcript-level quantification tool for RNA-seq. It uses "
                  "quasi-mapping for fast, accurate abundance estimation. Presence indicates "
                  "processed RNA-seq data."
    ),
    HeaderRule(
        id="program_kallisto",
        header_section="@PG",
        field="PN",
        pattern="kallisto",
        classification="transcriptomic.bulk",
        confidence=0.95,
        rationale="Kallisto performs rapid transcript quantification using pseudoalignment. "
                  "Like Salmon, it's specifically designed for RNA-seq analysis."
    ),
]


# DNA aligner programs - from @PG PN field
DNA_PROGRAM_RULES = [
    HeaderRule(
        id="program_bwa",
        header_section="@PG",
        field="PN",
        pattern="bwa",
        classification="genomic",
        confidence=0.80,
        rationale="BWA (Burrows-Wheeler Aligner) is the standard short-read aligner for DNA "
                  "sequencing. It's optimized for aligning reads to a reference genome without "
                  "splice awareness. Commonly used for WGS, WES, and ChIP-seq. Confidence is "
                  "not 100% because BWA can technically be used for non-spliced RNA alignment."
    ),
    HeaderRule(
        id="program_minimap2",
        header_section="@PG",
        field="PN",
        pattern="minimap2",
        classification="genomic",
        confidence=0.75,
        rationale="Minimap2 is a versatile aligner for long reads (PacBio, ONT) and assemblies. "
                  "While primarily used for genomic alignment, it can also be used for direct "
                  "RNA sequencing with appropriate presets (-ax splice). Confidence moderate "
                  "due to this dual use."
    ),
    HeaderRule(
        id="program_bowtie2",
        header_section="@PG",
        field="PN",
        pattern="bowtie2",
        classification="genomic",
        confidence=0.75,
        rationale="Bowtie2 is a fast short-read aligner commonly used for ChIP-seq, ATAC-seq, "
                  "and WGS. It doesn't handle spliced alignment, so presence suggests genomic "
                  "or epigenomic data rather than RNA-seq. However, it's sometimes used for "
                  "small RNA sequencing."
    ),
]


# PacBio-specific program rules
PACBIO_PROGRAM_RULES = [
    HeaderRule(
        id="program_ccs",
        header_section="@PG",
        field="PN",
        pattern="ccs",
        classification="genomic",
        confidence=0.85,
        rationale="The 'ccs' program generates HiFi reads from PacBio subreads. Its presence "
                  "confirms this is PacBio HiFi data, typically used for high-quality genome "
                  "assembly and variant calling."
    ),
    HeaderRule(
        id="program_isoseq",
        header_section="@PG",
        field="PN",
        pattern="isoseq",
        classification="transcriptomic.bulk",
        confidence=0.95,
        rationale="IsoSeq is PacBio's full-length transcript sequencing method. The 'isoseq' "
                  "program in @PG indicates this is long-read RNA-seq data for transcript "
                  "discovery and isoform characterization."
    ),
    HeaderRule(
        id="program_lima",
        header_section="@PG",
        field="PN",
        pattern="lima",
        classification=None,  # Demultiplexer, doesn't indicate modality
        confidence=0.0,
        rationale="Lima is PacBio's barcode demultiplexer. It separates multiplexed samples "
                  "but doesn't indicate data modality. Other header info needed."
    ),
]


# Reference assembly rules - from @SQ SN or AS fields
REFERENCE_RULES = [
    HeaderRule(
        id="ref_grch38_hg38",
        header_section="@SQ",
        field="SN",
        pattern=r"(?i)(grch38|hg38|hs38)",
        classification="GRCh38",
        confidence=0.95,
        rationale="Contig names containing 'GRCh38', 'hg38', or 'hs38' indicate alignment to "
                  "the GRCh38 human reference genome (released 2013, current standard). The @SQ "
                  "lines list all reference sequences the reads are aligned against."
    ),
    HeaderRule(
        id="ref_grch37_hg19",
        header_section="@SQ",
        field="SN",
        pattern=r"(?i)(grch37|hg19|hs37)",
        classification="GRCh37",
        confidence=0.95,
        rationale="Contig names containing 'GRCh37', 'hg19', or 'hs37' indicate alignment to "
                  "the GRCh37 human reference (released 2009). Still used for legacy data and "
                  "some clinical pipelines for compatibility."
    ),
    HeaderRule(
        id="ref_chm13_t2t",
        header_section="@SQ",
        field="SN",
        pattern=r"(?i)(chm13|t2t|hs1)",
        classification="CHM13",
        confidence=0.95,
        rationale="Contig names containing 'CHM13', 'T2T', or 'hs1' indicate alignment to the "
                  "T2T-CHM13 reference (released 2022). This is the first complete human genome "
                  "assembly, filling gaps in GRCh38 including centromeres and telomeres."
    ),
    HeaderRule(
        id="ref_assembly_tag",
        header_section="@SQ",
        field="AS",
        pattern=r".*",  # Any AS field indicates reference info
        classification=None,  # Extracted from value
        confidence=0.90,
        rationale="The AS (Assembly) tag in @SQ lines explicitly names the reference assembly. "
                  "When present, it provides definitive reference identification."
    ),
]


# Unaligned indicator
UNALIGNED_RULES = [
    HeaderRule(
        id="unaligned_no_sq",
        header_section="@SQ",
        field=None,  # Absence of @SQ
        pattern=None,
        classification="unaligned",
        confidence=0.90,
        rationale="Absence of @SQ lines in the header indicates unaligned reads. The BAM "
                  "contains raw sequencing data not yet mapped to a reference genome. Common "
                  "for PacBio HiFi deliverables before alignment."
    ),
]


# =============================================================================
# FILE SIZE RULES FOR WGS vs WES DISTINCTION
# =============================================================================
#
# File size can help distinguish WGS from WES:
# - WGS 30x coverage: ~50-150 GB BAM, ~15-50 GB CRAM
# - WES 100x coverage: ~5-15 GB BAM, ~2-8 GB CRAM
#
# The ~10:1 ratio exists because WGS covers the whole genome (~3B bases)
# while WES only covers exons (~1-2% of genome, ~30-60M bases).
#
# Caveats:
# - Coverage depth varies (higher coverage = larger files)
# - CRAM is ~60-70% smaller than BAM
# - Some files may be subsets or downsampled
# - Long-read BAMs (PacBio/ONT) are typically larger due to read length

@dataclass
class FileSizeRule:
    """A rule based on file size for WGS vs WES distinction."""
    id: str
    min_size_gb: float | None  # Minimum file size in GB
    max_size_gb: float | None  # Maximum file size in GB
    file_format: str | None    # .bam, .cram, or None for any
    platform: str | None       # ILLUMINA, PACBIO, ONT, or None for any
    classification: str
    confidence: float
    rationale: str


FILE_SIZE_RULES = [
    # Illumina BAM size rules
    FileSizeRule(
        id="illumina_bam_wgs_large",
        min_size_gb=50.0,
        max_size_gb=None,
        file_format=".bam",
        platform="ILLUMINA",
        classification="genomic",
        confidence=0.80,
        rationale="Illumina BAM files >50 GB strongly suggest WGS. At 30x coverage, a human "
                  "WGS BAM is typically 80-120 GB. WES files rarely exceed 20 GB even at high coverage."
    ),
    FileSizeRule(
        id="illumina_bam_wgs_medium",
        min_size_gb=30.0,
        max_size_gb=50.0,
        file_format=".bam",
        platform="ILLUMINA",
        classification="genomic",
        confidence=0.65,
        rationale="Illumina BAM files 30-50 GB likely indicate WGS at lower coverage (15-20x) "
                  "or WES at very high coverage (200x+). WGS is more common in this range."
    ),
    FileSizeRule(
        id="illumina_bam_wes_likely",
        min_size_gb=5.0,
        max_size_gb=20.0,
        file_format=".bam",
        platform="ILLUMINA",
        classification="genomic",
        confidence=0.60,
        rationale="Illumina BAM files 5-20 GB are typical for WES at 80-150x coverage. "
                  "Could also be low-coverage WGS, but WES is more common in this size range."
    ),

    # Illumina CRAM size rules (CRAM is ~60-70% smaller than BAM)
    FileSizeRule(
        id="illumina_cram_wgs_large",
        min_size_gb=20.0,
        max_size_gb=None,
        file_format=".cram",
        platform="ILLUMINA",
        classification="genomic",
        confidence=0.80,
        rationale="Illumina CRAM files >20 GB strongly suggest WGS. CRAM compression reduces "
                  "file size by 60-70% vs BAM, so a 20 GB CRAM corresponds to ~50-70 GB BAM."
    ),
    FileSizeRule(
        id="illumina_cram_wgs_medium",
        min_size_gb=10.0,
        max_size_gb=20.0,
        file_format=".cram",
        platform="ILLUMINA",
        classification="genomic",
        confidence=0.65,
        rationale="Illumina CRAM files 10-20 GB likely indicate WGS at moderate coverage."
    ),
    FileSizeRule(
        id="illumina_cram_wes_likely",
        min_size_gb=2.0,
        max_size_gb=8.0,
        file_format=".cram",
        platform="ILLUMINA",
        classification="genomic",
        confidence=0.60,
        rationale="Illumina CRAM files 2-8 GB are typical for WES. This corresponds to "
                  "~5-20 GB BAM, the standard WES size range."
    ),

    # PacBio long-read rules (typically larger due to read length)
    FileSizeRule(
        id="pacbio_large_wgs",
        min_size_gb=20.0,
        max_size_gb=None,
        file_format=None,
        platform="PACBIO",
        classification="genomic",
        confidence=0.75,
        rationale="Large PacBio files (>20 GB) typically indicate WGS. PacBio is rarely used "
                  "for WES due to cost; it's primarily used for WGS and structural variant detection."
    ),

    # ONT long-read rules
    FileSizeRule(
        id="ont_large_wgs",
        min_size_gb=20.0,
        max_size_gb=None,
        file_format=None,
        platform="ONT",
        classification="genomic",
        confidence=0.75,
        rationale="Large ONT files (>20 GB) typically indicate WGS. ONT is rarely used for "
                  "targeted sequencing; its strength is in long-range structural analysis."
    ),
]


# =============================================================================
# VCF HEADER CLASSIFICATION RULES
# =============================================================================
#
# VCF files have rich metadata in ## header lines:
#
# ##fileformat=VCFv4.2              - VCF version
# ##reference=file:///path/to/ref   - Reference genome path/URL
# ##contig=<ID=chr1,length=N,assembly=GRCh38>  - Contig definitions with assembly
# ##source=GATK HaplotypeCaller     - Variant caller used
# ##INFO=<ID=...,Description=...>   - INFO field definitions
# ##FORMAT=<ID=...,Description=...> - FORMAT field definitions
#
# Key signals:
# - ##reference and ##contig lines reveal reference genome
# - ##source reveals variant caller (germline vs somatic, SNV vs SV)
# - Specific INFO/FORMAT fields indicate variant type
#

# =============================================================================
# REFERENCE ASSEMBLY DETECTION BY CONTIG LENGTH
# =============================================================================
#
# Chromosome lengths are unique to each reference assembly. This provides
# definitive reference detection even when ##reference or assembly= tags
# are missing. We use a subset of chromosomes for efficiency.
#
# Sources:
# - GRCh38: https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.40
# - GRCh37: https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.13
# - CHM13: https://www.ncbi.nlm.nih.gov/assembly/GCF_009914755.1

REFERENCE_CONTIG_LENGTHS = {
    "GRCh38": {
        "chr1": 248956422, "1": 248956422,
        "chr2": 242193529, "2": 242193529,
        "chr3": 198295559, "3": 198295559,
        "chr10": 133797422, "10": 133797422,
        "chr22": 50818468, "22": 50818468,
    },
    "GRCh37": {
        "chr1": 249250621, "1": 249250621,
        "chr2": 243199373, "2": 243199373,
        "chr3": 198022430, "3": 198022430,
        "chr10": 135534747, "10": 135534747,
        "chr22": 51304566, "22": 51304566,
    },
    "CHM13": {
        "chr1": 248387497, "1": 248387497,
        "chr2": 242696747, "2": 242696747,
        "chr3": 201106605, "3": 201106605,
        "chr10": 134758134, "10": 134758134,
        "chr22": 51324926, "22": 51324926,
    }
}

# Build reverse lookup: (normalized_contig, length) -> assembly
_CONTIG_LENGTH_TO_ASSEMBLY = {}
for _assembly, _contigs in REFERENCE_CONTIG_LENGTHS.items():
    for _contig, _length in _contigs.items():
        # Normalize contig name (remove chr prefix)
        _normalized = _contig.replace("chr", "")
        _key = (_normalized, _length)
        _CONTIG_LENGTH_TO_ASSEMBLY[_key] = _assembly


def detect_reference_from_contig_lengths(contig_lines: list[str], tolerance: int = 1000) -> tuple[str | None, int, float]:
    """
    Detect reference assembly from contig lengths in VCF ##contig lines.

    This is a definitive signal - chromosome lengths are unique to each assembly.
    Uses fuzzy matching with tolerance to handle minor version differences
    (e.g., CHM13 v1.0 vs v2.0 differ by < 1000bp per chromosome).

    Args:
        contig_lines: List of ##contig=<...> lines from VCF header
        tolerance: Max difference in bp to consider a match (default 1000)

    Returns:
        Tuple of (assembly, vote_count, confidence)
        - assembly: "GRCh38", "GRCh37", "CHM13", or None
        - vote_count: Number of contigs that matched
        - confidence: 0.98 for exact match, 0.95 for fuzzy match
    """
    import re

    votes: dict[str, int] = {}
    exact_matches = 0

    # Parse ##contig=<ID=chr1,length=248387497>
    pattern = r'##contig=<ID=([^,>]+),length=(\d+)'
    for line in contig_lines:
        match = re.search(pattern, line)
        if match:
            contig = match.group(1).replace("chr", "")
            length = int(match.group(2))

            # Try exact match first
            key = (contig, length)
            if key in _CONTIG_LENGTH_TO_ASSEMBLY:
                assembly = _CONTIG_LENGTH_TO_ASSEMBLY[key]
                votes[assembly] = votes.get(assembly, 0) + 1
                exact_matches += 1
            else:
                # Fuzzy match: find closest assembly within tolerance
                best_match = None
                best_diff = tolerance + 1
                for ref_assembly, ref_contigs in REFERENCE_CONTIG_LENGTHS.items():
                    # Check both chr-prefixed and non-prefixed versions
                    for ref_contig, ref_length in ref_contigs.items():
                        ref_norm = ref_contig.replace("chr", "")
                        if ref_norm == contig:
                            diff = abs(ref_length - length)
                            if diff <= tolerance and diff < best_diff:
                                best_match = ref_assembly
                                best_diff = diff
                if best_match:
                    votes[best_match] = votes.get(best_match, 0) + 1

    if votes:
        # Return assembly with most votes
        winner = max(votes.keys(), key=lambda k: votes[k])
        # Lower confidence if no exact matches (fuzzy only)
        confidence = 0.98 if exact_matches > 0 else 0.95
        return winner, votes[winner], confidence

    return None, 0, 0.0


# =============================================================================
# REFERENCE ASSEMBLY DETECTION BY VARIANT POSITIONS
# =============================================================================
#
# When header-based detection fails, we can use max variant positions to
# rule out references. If a variant exists at a position beyond a reference's
# chromosome length, that reference is ruled out.
#
# Key chromosome 1 lengths:
#   GRCh37: 249,250,621
#   GRCh38: 248,956,422
#   CHM13:  248,387,497

# (grch37_len, grch38_len, chm13_len) for key chromosomes
CHROMOSOME_MAX_LENGTHS = {
    "1": (249250621, 248956422, 248387497),
    "2": (243199373, 242193529, 242696747),
    "3": (198022430, 198295559, 201106605),
    "10": (135534747, 133797422, 134758134),
    "22": (51304566, 50818468, 51324926),
}


def detect_reference_from_max_positions(
    max_positions: dict[str, int],
) -> tuple[str | None, int, float]:
    """
    Detect reference assembly by ruling out references where variant
    positions exceed chromosome lengths.

    Args:
        max_positions: Dict mapping chromosome (without 'chr') to max position seen

    Returns:
        Tuple of (assembly, evidence_count, confidence)
    """
    if not max_positions:
        return None, 0, 0.0

    possible = {"GRCh37", "GRCh38", "CHM13"}
    evidence_count = 0

    for chrom, max_pos in max_positions.items():
        chrom = chrom.replace("chr", "")
        if chrom not in CHROMOSOME_MAX_LENGTHS:
            continue

        grch37_len, grch38_len, chm13_len = CHROMOSOME_MAX_LENGTHS[chrom]

        # Rule out references where position exceeds chromosome length
        if max_pos > chm13_len:
            possible.discard("CHM13")
            evidence_count += 1
        if max_pos > grch38_len:
            possible.discard("GRCh38")
            evidence_count += 1
        if max_pos > grch37_len:
            possible.discard("GRCh37")
            evidence_count += 1

    # If narrowed to exactly one reference
    if len(possible) == 1 and evidence_count > 0:
        return possible.pop(), evidence_count, 0.90

    return None, 0, 0.0


# Reference assembly rules from VCF headers
VCF_REFERENCE_RULES = [
    VCFHeaderRule(
        id="vcf_ref_grch38",
        header_type="##reference",
        pattern=r"(?i)(grch38|hg38|hs38|GCA_000001405\.15)",
        classification="GRCh38",
        confidence=0.95,
        rationale="##reference line containing GRCh38, hg38, or the GRCh38 GenBank accession "
                  "(GCA_000001405.15) indicates variants were called against the GRCh38 reference."
    ),
    VCFHeaderRule(
        id="vcf_ref_grch37",
        header_type="##reference",
        pattern=r"(?i)(grch37|hg19|hs37|GCA_000001405\.1[^5]|b37)",
        classification="GRCh37",
        confidence=0.95,
        rationale="##reference line containing GRCh37, hg19, b37, or earlier GRCh37 accessions "
                  "indicates variants were called against the GRCh37 reference."
    ),
    VCFHeaderRule(
        id="vcf_ref_chm13",
        header_type="##reference",
        pattern=r"(?i)(chm13|t2t|hs1)",
        classification="CHM13",
        confidence=0.95,
        rationale="##reference line containing CHM13 or T2T indicates variants called against "
                  "the T2T-CHM13 complete human genome assembly."
    ),
    VCFHeaderRule(
        id="vcf_contig_grch38",
        header_type="##contig",
        pattern=r"(?i)assembly=(grch38|hg38|GCA_000001405\.15)",
        classification="GRCh38",
        confidence=0.95,
        rationale="##contig lines with assembly=GRCh38 explicitly declare the reference genome."
    ),
    VCFHeaderRule(
        id="vcf_contig_grch37",
        header_type="##contig",
        pattern=r"(?i)assembly=(grch37|hg19|b37)",
        classification="GRCh37",
        confidence=0.95,
        rationale="##contig lines with assembly=GRCh37 explicitly declare the reference genome."
    ),
    VCFHeaderRule(
        id="vcf_contig_chm13",
        header_type="##contig",
        pattern=r"(?i)assembly=(chm13|t2t|hs1)",
        classification="CHM13",
        confidence=0.95,
        rationale="##contig lines with assembly=CHM13 explicitly declare the reference genome."
    ),
]

# Variant caller rules - germline callers
VCF_GERMLINE_CALLER_RULES = [
    VCFHeaderRule(
        id="vcf_gatk_haplotypecaller",
        header_type="##source",
        pattern=r"(?i)haplotypecaller",
        classification="genomic.germline_variants",
        confidence=0.90,
        rationale="GATK HaplotypeCaller is the standard germline SNV/indel caller. It performs "
                  "local de novo assembly to call variants, optimized for diploid germline samples."
    ),
    VCFHeaderRule(
        id="vcf_deepvariant",
        header_type="##source",
        pattern=r"(?i)deepvariant",
        classification="genomic.germline_variants",
        confidence=0.90,
        rationale="DeepVariant is Google's deep learning-based germline variant caller. "
                  "It's trained on truth sets and excels at both SNVs and indels."
    ),
    VCFHeaderRule(
        id="vcf_gatk_genotypegvcfs",
        header_type="##source",
        pattern=r"(?i)genotypegvcfs",
        classification="genomic.germline_variants",
        confidence=0.90,
        rationale="GATK GenotypeGVCFs performs joint genotyping on gVCF files, "
                  "used in cohort germline variant calling workflows."
    ),
    VCFHeaderRule(
        id="vcf_glnexus",
        header_type="##source",
        pattern=r"(?i)glnexus",
        classification="genomic.germline_variants",
        confidence=0.90,
        rationale="GLnexus is a scalable gVCF merging and joint genotyping tool, "
                  "commonly used with DeepVariant for population-scale germline calling."
    ),
    VCFHeaderRule(
        id="vcf_bcftools_call",
        header_type="##source",
        pattern=r"(?i)bcftools.*call",
        classification="genomic.germline_variants",
        confidence=0.85,
        rationale="bcftools call is a lightweight germline variant caller using "
                  "the multiallelic or consensus caller models."
    ),
    VCFHeaderRule(
        id="vcf_freebayes",
        header_type="##source",
        pattern=r"(?i)freebayes",
        classification="genomic.germline_variants",
        confidence=0.85,
        rationale="FreeBayes is a Bayesian haplotype-based germline variant caller "
                  "that can handle pooled or mixed samples."
    ),
    VCFHeaderRule(
        id="vcf_strelka2_germline",
        header_type="##source",
        pattern=r"(?i)strelka2.*germline|strelka2(?!.*somatic)",
        classification="genomic.germline_variants",
        confidence=0.85,
        rationale="Strelka2 in germline mode calls SNVs and indels from germline samples."
    ),
]

# Variant caller rules - somatic callers
VCF_SOMATIC_CALLER_RULES = [
    VCFHeaderRule(
        id="vcf_mutect2",
        header_type="##source",
        pattern=r"(?i)mutect2?",
        classification="genomic.somatic_variants",
        confidence=0.95,
        rationale="GATK Mutect2 is the standard somatic SNV/indel caller for tumor-normal "
                  "or tumor-only analysis. Its presence strongly indicates cancer genomics data."
    ),
    VCFHeaderRule(
        id="vcf_strelka_somatic",
        header_type="##source",
        pattern=r"(?i)strelka.*somatic|strelka(?!.*germline)",
        classification="genomic.somatic_variants",
        confidence=0.90,
        rationale="Strelka/Strelka2 in somatic mode calls somatic variants from tumor-normal pairs."
    ),
    VCFHeaderRule(
        id="vcf_varscan_somatic",
        header_type="##source",
        pattern=r"(?i)varscan.*somatic",
        classification="genomic.somatic_variants",
        confidence=0.90,
        rationale="VarScan somatic mode calls somatic variants from tumor-normal pairs "
                  "using a heuristic/statistical approach."
    ),
    VCFHeaderRule(
        id="vcf_somaticsniper",
        header_type="##source",
        pattern=r"(?i)somaticsniper",
        classification="genomic.somatic_variants",
        confidence=0.90,
        rationale="SomaticSniper identifies somatic point mutations in tumor-normal pairs."
    ),
    VCFHeaderRule(
        id="vcf_muse",
        header_type="##source",
        pattern=r"(?i)muse",
        classification="genomic.somatic_variants",
        confidence=0.90,
        rationale="MuSE calls somatic point mutations using a Markov substitution model, "
                  "designed for tumor-normal pairs."
    ),
]

# Structural variant caller rules
VCF_SV_CALLER_RULES = [
    VCFHeaderRule(
        id="vcf_manta",
        header_type="##source",
        pattern=r"(?i)manta",
        classification="genomic.structural_variants",
        confidence=0.90,
        rationale="Manta calls structural variants (deletions, insertions, inversions, "
                  "translocations) and large indels from short-read data."
    ),
    VCFHeaderRule(
        id="vcf_delly",
        header_type="##source",
        pattern=r"(?i)delly",
        classification="genomic.structural_variants",
        confidence=0.90,
        rationale="DELLY discovers structural variants using paired-end and split-read analysis."
    ),
    VCFHeaderRule(
        id="vcf_lumpy",
        header_type="##source",
        pattern=r"(?i)lumpy",
        classification="genomic.structural_variants",
        confidence=0.90,
        rationale="LUMPY is a probabilistic SV caller using multiple alignment signals."
    ),
    VCFHeaderRule(
        id="vcf_smoove",
        header_type="##source",
        pattern=r"(?i)smoove",
        classification="genomic.structural_variants",
        confidence=0.90,
        rationale="Smoove simplifies SV calling by wrapping LUMPY with additional filtering."
    ),
    VCFHeaderRule(
        id="vcf_svim",
        header_type="##source",
        pattern=r"(?i)svim",
        classification="genomic.structural_variants",
        confidence=0.90,
        rationale="SVIM detects structural variants from long-read sequencing data (PacBio/ONT)."
    ),
    VCFHeaderRule(
        id="vcf_sniffles",
        header_type="##source",
        pattern=r"(?i)sniffles",
        classification="genomic.structural_variants",
        confidence=0.90,
        rationale="Sniffles is a long-read SV caller optimized for PacBio and ONT data, "
                  "detecting complex SVs that short reads miss."
    ),
    VCFHeaderRule(
        id="vcf_pbsv",
        header_type="##source",
        pattern=r"(?i)pbsv",
        classification="genomic.structural_variants",
        confidence=0.90,
        rationale="PBSV is PacBio's structural variant caller for HiFi and CLR data."
    ),
    VCFHeaderRule(
        id="vcf_cutesv",
        header_type="##source",
        pattern=r"(?i)cutesv",
        classification="genomic.structural_variants",
        confidence=0.90,
        rationale="CuteSV is a fast long-read SV caller using clustering of signatures."
    ),
]

# Copy number variant caller rules
VCF_CNV_CALLER_RULES = [
    VCFHeaderRule(
        id="vcf_cnvkit",
        header_type="##source",
        pattern=r"(?i)cnvkit",
        classification="genomic.copy_number_variants",
        confidence=0.90,
        rationale="CNVkit detects copy number variants from targeted/exome or WGS data."
    ),
    VCFHeaderRule(
        id="vcf_gatk_cnv",
        header_type="##source",
        pattern=r"(?i)gatk.*(cnv|copynumber)|modelsegments",
        classification="genomic.copy_number_variants",
        confidence=0.90,
        rationale="GATK CNV tools (ModelSegments, etc.) call copy number variants "
                  "from read depth data."
    ),
    VCFHeaderRule(
        id="vcf_canvas",
        header_type="##source",
        pattern=r"(?i)canvas",
        classification="genomic.copy_number_variants",
        confidence=0.90,
        rationale="Canvas is Illumina's CNV caller for WGS and tumor-normal analysis."
    ),
]

# INFO field indicators
VCF_INFO_RULES = [
    VCFHeaderRule(
        id="vcf_info_somatic",
        header_type="##INFO",
        pattern=r"ID=(SOMATIC|TUMOR_|NORMAL_|TumorVAF|NormalVAF)",
        classification="genomic.somatic_variants",
        confidence=0.85,
        rationale="INFO fields with SOMATIC, TUMOR_, or NORMAL_ prefixes indicate "
                  "this VCF contains somatic variant calls from tumor-normal analysis."
    ),
    VCFHeaderRule(
        id="vcf_info_sv",
        header_type="##INFO",
        pattern=r"ID=(SVTYPE|SVLEN|END|CIPOS|CIEND|MATEID|IMPRECISE)",
        classification="genomic.structural_variants",
        confidence=0.80,
        rationale="Standard SV INFO fields (SVTYPE, SVLEN, CIPOS, etc.) indicate "
                  "this VCF contains structural variant calls."
    ),
    VCFHeaderRule(
        id="vcf_info_cnv",
        header_type="##INFO",
        pattern=r"ID=(CN|FOLD_CHANGE|PROBES|LOG2_COPY_RATIO)",
        classification="genomic.copy_number_variants",
        confidence=0.80,
        rationale="CNV-specific INFO fields indicate copy number variant calls."
    ),
]

# Combine all VCF rules
ALL_VCF_RULES = (
    VCF_REFERENCE_RULES +
    VCF_GERMLINE_CALLER_RULES +
    VCF_SOMATIC_CALLER_RULES +
    VCF_SV_CALLER_RULES +
    VCF_CNV_CALLER_RULES +
    VCF_INFO_RULES
)


# =============================================================================
# FASTQ HEADER CLASSIFICATION RULES
# =============================================================================
#
# FASTQ read names have platform-specific formats that can identify:
# - Sequencing platform (Illumina, PacBio, ONT, MGI/BGI)
# - Instrument model
# - Run/flowcell information
# - Read type (single-end, paired-end, CCS, etc.)
#
# Format examples:
#
# ILLUMINA (modern Casava 1.8+):
#   @A00488:61:HFWFVDSXX:1:1101:1000:1000 1:N:0:ATCACG
#   @instrument:run:flowcell:lane:tile:x:y read:filtered:control:index
#
# ILLUMINA (legacy):
#   @HWUSI-EAS100R:6:73:941:1973#0/1
#   @instrument:lane:tile:x:y#index/read
#
# PACBIO CCS/HiFi:
#   @m64011_190830_220126/1/ccs
#   @movie/zmw/ccs
#
# PACBIO CLR (subreads):
#   @m64011_190830_220126/1234/0_5000
#   @movie/zmw/start_end
#
# ONT:
#   @a1b2c3d4-e5f6-7890-abcd-ef1234567890 runid=abc123...
#   @uuid [key=value pairs]
#
# MGI/BGI:
#   @V350012345L1C001R0010000001/1
#   @flowcell_lane_column_row_readnum/pair
#

@dataclass
class FASTQHeaderRule:
    """A classification rule based on FASTQ read name format."""
    id: str
    pattern: str         # regex pattern to match read name
    classification: str | None  # platform or modality
    platform: str | None  # detected platform
    confidence: float
    rationale: str


# Illumina read name patterns
FASTQ_ILLUMINA_RULES = [
    FASTQHeaderRule(
        id="fastq_illumina_modern",
        pattern=r"^@[A-Z0-9-]+:\d+:[A-Z0-9]+:\d+:\d+:\d+:\d+",
        classification="genomic",
        platform="ILLUMINA",
        confidence=0.90,
        rationale="Modern Illumina read names (Casava 1.8+) follow the format "
                  "@instrument:run:flowcell:lane:tile:x:y. This format is used by "
                  "HiSeq 2500+, NovaSeq, NextSeq, and MiSeq instruments."
    ),
    FASTQHeaderRule(
        id="fastq_illumina_legacy",
        pattern=r"^@[A-Z0-9-]+:\d+:\d+:\d+:\d+#",
        classification="genomic",
        platform="ILLUMINA",
        confidence=0.85,
        rationale="Legacy Illumina read names follow @instrument:lane:tile:x:y#index format. "
                  "Used by older instruments like GA, GAIIx, HiSeq 2000."
    ),
    FASTQHeaderRule(
        id="fastq_illumina_srr",
        pattern=r"^@SRR\d+\.\d+",
        classification="genomic",
        platform="ILLUMINA",
        confidence=0.70,
        rationale="SRA-reformatted read names starting with @SRR typically indicate Illumina data "
                  "downloaded from NCBI SRA. Lower confidence as original platform info is lost."
    ),
    FASTQHeaderRule(
        id="fastq_illumina_ena_hiseq",
        pattern=r"^@[EDS]RR\d+\.\d+ HS2[05]00",
        classification="genomic",
        platform="ILLUMINA",
        confidence=0.90,
        rationale="ENA/SRA-reformatted read names with HiSeq 2000/2500 instrument ID "
                  "(HS2000/HS2500) in the description field. Format: @ERRxxxxxx.n HSxxxx-..."
    ),
    FASTQHeaderRule(
        id="fastq_illumina_hiseq_desc",
        pattern=r" HS2[05]00[-_]",
        classification="genomic",
        platform="ILLUMINA",
        confidence=0.85,
        rationale="HiSeq 2000/2500 instrument identifier (HS2000/HS2500) found in read "
                  "description. Common in ENA/SRA-reformatted files from older Illumina runs."
    ),
]

# PacBio read name patterns
# Movie ID format: m{instrument}_{date}_{time} where instrument can have letter suffixes:
#   m64011   - Sequel
#   m54329U  - Sequel II (U suffix)
#   m54306Ue - Sequel IIe (Ue suffix)
#   m84046   - Revio
FASTQ_PACBIO_RULES = [
    FASTQHeaderRule(
        id="fastq_pacbio_ccs",
        pattern=r"^@m\d+[A-Za-z]*_\d+_\d+/\d+/ccs",
        classification="genomic",
        platform="PACBIO",
        confidence=0.95,
        rationale="PacBio CCS (HiFi) read names follow @movie/zmw/ccs format. The 'ccs' suffix "
                  "indicates Circular Consensus Sequencing was performed, producing high-accuracy "
                  "long reads (>Q20). Movie names start with 'm' followed by instrument ID and timestamp."
    ),
    FASTQHeaderRule(
        id="fastq_pacbio_clr",
        pattern=r"^@m\d+[A-Za-z]*_\d+_\d+/\d+/\d+_\d+",
        classification="genomic",
        platform="PACBIO",
        confidence=0.90,
        rationale="PacBio CLR (Continuous Long Read) subread names follow @movie/zmw/start_end format. "
                  "The start_end coordinates indicate the position within the ZMW polymerase read."
    ),
    FASTQHeaderRule(
        id="fastq_pacbio_generic",
        pattern=r"^@m\d+[A-Za-z]*_\d+_\d+/\d+",
        classification="genomic",
        platform="PACBIO",
        confidence=0.85,
        rationale="Generic PacBio read names follow @movie/zmw format. The movie name encodes "
                  "the instrument (m=RSII/Sequel, followed by instrument ID) and run timestamp."
    ),
]

# ONT read name patterns
FASTQ_ONT_RULES = [
    FASTQHeaderRule(
        id="fastq_ont_uuid",
        pattern=r"^@[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
        classification="genomic",
        platform="ONT",
        confidence=0.95,
        rationale="ONT read names are UUIDs (format: 8-4-4-4-12 hex characters). "
                  "This uniquely identifies Oxford Nanopore data. Additional metadata "
                  "like runid, read number, and channel may follow as key=value pairs."
    ),
    FASTQHeaderRule(
        id="fastq_ont_metadata",
        pattern=r"runid=[a-f0-9]+",
        classification="genomic",
        platform="ONT",
        confidence=0.95,
        rationale="ONT reads often include 'runid=' metadata in the header line, "
                  "providing the unique run identifier from MinKNOW."
    ),
]

# MGI/BGI read name patterns
FASTQ_MGI_RULES = [
    FASTQHeaderRule(
        id="fastq_mgi",
        pattern=r"^@[A-Z]\d{9}L\dC\d{3}R\d{3}\d+",
        classification="genomic",
        platform="MGI",
        confidence=0.90,
        rationale="MGI/BGI-SEQ read names follow @flowcellLaneCcolumnRrow format. "
                  "MGI (formerly BGI) instruments use this distinctive naming convention "
                  "with embedded lane (L), column (C), and row (R) identifiers."
    ),
    FASTQHeaderRule(
        id="fastq_mgi_alt",
        pattern=r"^@[A-Z]\d+L\d+C\d+R\d+",
        classification="genomic",
        platform="MGI",
        confidence=0.85,
        rationale="Alternative MGI/BGI read name format with varying digit lengths."
    ),
]

# Element Biosciences read name patterns
FASTQ_ELEMENT_RULES = [
    FASTQHeaderRule(
        id="fastq_element",
        pattern=r"^@[A-Z0-9]+:[A-Z0-9]+:\d+:\d+:\d+:\d+:\d+",
        classification="genomic",
        platform="ELEMENT",
        confidence=0.80,
        rationale="Element Biosciences AVITI read names follow a similar format to Illumina "
                  "but with different instrument ID patterns."
    ),
]

# Ultima Genomics read name patterns
FASTQ_ULTIMA_RULES = [
    FASTQHeaderRule(
        id="fastq_ultima",
        pattern=r"^@[A-Z0-9]+_\d+_\d+_\d+_[ACGT]+",
        classification="genomic",
        platform="ULTIMA",
        confidence=0.80,
        rationale="Ultima Genomics read names include flow-space encoded sequences "
                  "in the read identifier."
    ),
]

# ENA/SRA archive accession patterns
# When data is submitted to ENA/SRA, read names get prefixed with accession IDs
# but the original instrument info is usually preserved after a space
FASTQ_ARCHIVE_RULES = [
    FASTQHeaderRule(
        id="fastq_ena_err",
        pattern=r"^@ERR\d+\.\d+",
        classification=None,  # Platform determined from text after accession
        platform=None,
        confidence=0.60,
        rationale="ERR accessions indicate data from the European Nucleotide Archive (ENA). "
                  "The accession can be used to look up study metadata via ENA API. "
                  "Original platform info may be preserved after the accession."
    ),
    FASTQHeaderRule(
        id="fastq_sra_srr",
        pattern=r"^@SRR\d+\.\d+",
        classification=None,
        platform=None,
        confidence=0.60,
        rationale="SRR accessions indicate data from NCBI Sequence Read Archive (SRA). "
                  "The accession can be used to query SRA metadata. "
                  "Original instrument info may follow after a space."
    ),
    FASTQHeaderRule(
        id="fastq_ddbj_drr",
        pattern=r"^@DRR\d+\.\d+",
        classification=None,
        platform=None,
        confidence=0.60,
        rationale="DRR accessions indicate data from DDBJ Sequence Read Archive (Japan). "
                  "The accession links to DDBJ metadata resources."
    ),
]

# Paired-end detection (works across platforms)
FASTQ_PAIREDEND_RULES = [
    FASTQHeaderRule(
        id="fastq_paired_r1",
        pattern=r"[/\s][12]$|[/\s][12]:|_R[12]_|\.R[12]\.|_r[12]_|\.r[12]\.",
        classification=None,  # Doesn't change modality
        platform=None,
        confidence=0.80,
        rationale="Read 1 or Read 2 indicators (/1, /2, _R1_, _R2_) suggest paired-end sequencing. "
                  "This is common for Illumina WGS, WES, and RNA-seq workflows."
    ),
]

# Combine all FASTQ rules
ALL_FASTQ_RULES = (
    FASTQ_ILLUMINA_RULES +
    FASTQ_PACBIO_RULES +
    FASTQ_ONT_RULES +
    FASTQ_MGI_RULES +
    FASTQ_ELEMENT_RULES +
    FASTQ_ULTIMA_RULES +
    FASTQ_ARCHIVE_RULES +
    FASTQ_PAIREDEND_RULES
)


# All BAM/CRAM rules combined for easy iteration
ALL_RULES = (
    PLATFORM_RULES +
    PACBIO_READTYPE_RULES +
    RNASEQ_PROGRAM_RULES +
    DNA_PROGRAM_RULES +
    PACBIO_PROGRAM_RULES +
    REFERENCE_RULES +
    UNALIGNED_RULES
)


# =============================================================================
# CONSISTENCY VALIDATION RULES
# =============================================================================
#
# These rules define expected relationships between header signals.
# Convergent signals should agree and increase confidence.
# Conflicting signals indicate errors or unusual edge cases.

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
        "reference_assemblies_found": set(),
    }

    matched_set = set(matched_rules)

    # Check convergent rules
    for rule in CONVERGENT_RULES:
        if rule.signal_a in matched_set and rule.signal_b in matched_set:
            result["convergent_signals"].append({
                "rule_id": rule.id,
                "signal_a": rule.signal_a,
                "signal_b": rule.signal_b,
                "agreement": rule.expected_agreement,
                "rationale": rule.rationale,
            })
            # Boost confidence for each convergent pair (diminishing returns)
            result["confidence_boost"] += 0.05 * (0.8 ** len(result["convergent_signals"]))

    # Check conflicting rules
    for rule in CONFLICTING_RULES:
        if rule.signal_a in matched_set and rule.signal_b in matched_set:
            result["conflicting_signals"].append({
                "rule_id": rule.id,
                "signal_a": rule.signal_a,
                "signal_b": rule.signal_b,
                "rationale": rule.rationale,
            })
            result["warnings"].append(
                f"CONFLICT [{rule.id}]: {rule.signal_a} + {rule.signal_b} - {rule.rationale}"
            )

    # Check reference consistency from evidence
    for e in evidence:
        if e["rule_id"].startswith("ref_") and e["classification"]:
            result["reference_assemblies_found"].add(e["classification"])

    if len(result["reference_assemblies_found"]) > 1:
        result["reference_consistency"] = False
        refs = ", ".join(sorted(result["reference_assemblies_found"]))
        result["warnings"].append(
            f"REFERENCE INCONSISTENCY: Multiple reference assemblies detected: {refs}. "
            "This may indicate mixed data or incorrect reference annotation."
        )

    # Convert set to list for JSON serialization
    result["reference_assemblies_found"] = list(result["reference_assemblies_found"])

    return result


def classify_from_header(
    header_text: str,
    file_size: int | None = None,
    file_format: str | None = None,
) -> dict:
    """
    Classify data modality and reference from BAM header text.

    Returns dict with:
        - data_modality: str or None
        - reference_assembly: str or None
        - confidence: float
        - matched_rules: list of rule IDs that matched
        - evidence: list of dicts with rule details and rationales
    """
    import re

    result = {
        "data_modality": None,
        "data_type": "alignments",  # BAM/CRAM files contain aligned reads
        "assay_type": None,  # WGS, WES, RNA-seq, etc.
        "reference_assembly": None,
        "confidence": 0.0,
        "is_aligned": None,
        "platform": None,
        "matched_rules": [],
        "evidence": [],
    }

    lines = header_text.strip().split("\n")

    # Parse header into sections
    sq_lines = [l for l in lines if l.startswith("@SQ")]
    rg_lines = [l for l in lines if l.startswith("@RG")]
    pg_lines = [l for l in lines if l.startswith("@PG")]

    # Check for unaligned (no @SQ)
    if not sq_lines:
        result["is_aligned"] = False
        result["evidence"].append({
            "rule_id": "unaligned_no_sq",
            "matched": "No @SQ lines present",
            "classification": "unaligned",
            "confidence": 0.90,
            "rationale": UNALIGNED_RULES[0].rationale,
        })
        result["matched_rules"].append("unaligned_no_sq")
    else:
        result["is_aligned"] = True

    # Check platform from @RG
    for rg in rg_lines:
        for rule in PLATFORM_RULES:
            if f"PL:{rule.pattern}" in rg.upper():
                result["platform"] = rule.pattern
                result["evidence"].append({
                    "rule_id": rule.id,
                    "matched": f"PL:{rule.pattern}",
                    "classification": rule.classification,
                    "confidence": rule.confidence,
                    "rationale": rule.rationale,
                })
                result["matched_rules"].append(rule.id)
                if rule.classification and rule.confidence > result["confidence"]:
                    result["data_modality"] = rule.classification
                    result["confidence"] = rule.confidence

    # Check PacBio read type from @RG DS
    for rg in rg_lines:
        for rule in PACBIO_READTYPE_RULES:
            if rule.pattern in rg:
                result["evidence"].append({
                    "rule_id": rule.id,
                    "matched": rule.pattern,
                    "classification": rule.classification,
                    "confidence": rule.confidence,
                    "rationale": rule.rationale,
                })
                result["matched_rules"].append(rule.id)
                if rule.confidence > result["confidence"]:
                    result["data_modality"] = rule.classification
                    result["confidence"] = rule.confidence

    # Check programs from @PG
    all_program_rules = RNASEQ_PROGRAM_RULES + DNA_PROGRAM_RULES + PACBIO_PROGRAM_RULES
    for pg in pg_lines:
        for rule in all_program_rules:
            # Match PN field case-insensitively
            if re.search(rf"PN:{rule.pattern}", pg, re.IGNORECASE):
                result["evidence"].append({
                    "rule_id": rule.id,
                    "matched": f"PN:{rule.pattern}",
                    "classification": rule.classification,
                    "confidence": rule.confidence,
                    "rationale": rule.rationale,
                })
                result["matched_rules"].append(rule.id)
                if rule.classification and rule.confidence > result["confidence"]:
                    result["data_modality"] = rule.classification
                    result["confidence"] = rule.confidence

    # Check reference assembly from @SQ
    for sq in sq_lines:
        for rule in REFERENCE_RULES:
            if rule.field == "SN" and re.search(rule.pattern, sq, re.IGNORECASE):
                result["evidence"].append({
                    "rule_id": rule.id,
                    "matched": f"SN matches {rule.pattern}",
                    "classification": rule.classification,
                    "confidence": rule.confidence,
                    "rationale": rule.rationale,
                })
                result["matched_rules"].append(rule.id)
                if rule.classification and not result["reference_assembly"]:
                    result["reference_assembly"] = rule.classification

    # Check file size rules for WGS vs WES distinction
    if file_size is not None:
        file_size_gb = file_size / (1024 ** 3)  # Convert bytes to GB
        for rule in FILE_SIZE_RULES:
            # Check platform match (if rule specifies one)
            if rule.platform and result["platform"] != rule.platform:
                continue
            # Check file format match (if rule specifies one)
            if rule.file_format and file_format and rule.file_format != file_format:
                continue
            # Check size range
            if rule.min_size_gb is not None and file_size_gb < rule.min_size_gb:
                continue
            if rule.max_size_gb is not None and file_size_gb >= rule.max_size_gb:
                continue

            # Rule matches
            result["evidence"].append({
                "rule_id": rule.id,
                "matched": f"file_size={file_size_gb:.1f}GB",
                "classification": rule.classification,
                "confidence": rule.confidence,
                "rationale": rule.rationale,
            })
            result["matched_rules"].append(rule.id)

            # Update modality if this rule has higher confidence and modality is still generic
            # Note: assay_type (WGS/WES) is inferred separately, data_modality stays as "genomic"
            if rule.classification and result["data_modality"] in [None, "genomic"]:
                if rule.confidence > 0.5:  # Only apply if reasonably confident
                    result["evidence"].append({
                        "rule_id": f"{rule.id}_applied",
                        "matched": f"Refined modality based on {file_size_gb:.1f}GB file size",
                        "classification": rule.classification,
                        "confidence": rule.confidence,
                        "rationale": f"File size suggests {rule.classification}. {rule.rationale}",
                    })
                    # Don't override high-confidence classifications
                    if result["confidence"] < 0.85:
                        result["data_modality"] = rule.classification
            break  # Only apply first matching size rule

    # Run consistency validation
    consistency = check_consistency(result["matched_rules"], result["evidence"])
    result["consistency"] = {
        "convergent_signals": consistency["convergent_signals"],
        "conflicting_signals": consistency["conflicting_signals"],
        "reference_consistency": consistency["reference_consistency"],
        "warnings": consistency["warnings"],
    }

    # Apply confidence boost from convergent signals
    if consistency["convergent_signals"] and not consistency["conflicting_signals"]:
        result["confidence"] = min(0.99, result["confidence"] + consistency["confidence_boost"])

    # Reduce confidence if there are conflicts
    if consistency["conflicting_signals"]:
        result["confidence"] = max(0.1, result["confidence"] - 0.2)

    # Infer assay_type from platform, programs, and modality
    _infer_assay_type(result, file_size, file_format)

    return result


def _evaluate_assay_condition(condition: dict, context: dict) -> bool:
    """Evaluate a single assay type rule condition against context.

    Args:
        condition: Dict with condition keys (matched_rules_any, platform, etc.)
        context: Dict with platform, data_modality, matched_rules, file_size_gb, file_format

    Returns:
        True if all conditions in the dict are satisfied
    """
    for key, value in condition.items():
        if key == "matched_rules_any":
            matched = context.get("matched_rules", [])
            if not any(r in matched for r in value):
                return False
        elif key == "data_modality":
            if context.get("data_modality") != value:
                return False
        elif key == "data_modality_contains":
            modality = context.get("data_modality") or ""
            if value not in modality:
                return False
        elif key == "platform":
            if context.get("platform") != value:
                return False
        elif key == "platform_in":
            if context.get("platform") not in value:
                return False
        elif key == "file_size_gb_gt":
            file_size_gb = context.get("file_size_gb")
            if file_size_gb is None or file_size_gb <= value:
                return False
        elif key == "file_size_gb_lt":
            file_size_gb = context.get("file_size_gb")
            if file_size_gb is None or file_size_gb >= value:
                return False
        elif key == "file_format":
            if context.get("file_format") != value:
                return False
        elif key == "file_format_not":
            if context.get("file_format") == value:
                return False
    return True


def _infer_assay_type(result: dict, file_size: int | None, file_format: str | None) -> None:
    """Infer assay_type from classification signals using ASSAY_TYPE_RULES.

    Modifies result dict in place to set assay_type field.
    Rules are evaluated in priority order (highest first), first match wins.
    """
    # Build context for rule evaluation
    context = {
        "platform": result.get("platform"),
        "data_modality": result.get("data_modality") or "",
        "matched_rules": result.get("matched_rules", []),
        "file_format": file_format,
        "file_size_gb": file_size / (1024 ** 3) if file_size is not None else None,
    }

    # Sort rules by priority (highest first) and evaluate
    sorted_rules = sorted(ASSAY_TYPE_RULES, key=lambda r: r.get("priority", 0), reverse=True)

    for rule in sorted_rules:
        if _evaluate_assay_condition(rule["conditions"], context):
            result["assay_type"] = rule["assay_type"]
            return


def classify_from_vcf_header(
    header_text: str,
    file_size: int | None = None,
    max_positions: dict[str, int] | None = None,
) -> dict:
    """
    Classify data modality, variant type, and reference from VCF header text.

    Args:
        header_text: The VCF header (lines starting with ##)
        file_size: Optional file size in bytes
        max_positions: Optional dict of max variant positions per chromosome
                       (for fallback reference detection)

    Returns dict with:
        - data_modality: str or None (e.g., genomic.germline_variants)
        - variant_type: str or None (germline, somatic, structural, cnv)
        - reference_assembly: str or None
        - confidence: float
        - matched_rules: list of rule IDs that matched
        - evidence: list of dicts with rule details and rationales
        - caller: str or None (detected variant caller)
    """
    import re

    result = {
        "data_modality": None,
        "data_type": None,  # Set based on variant_type below
        "assay_type": None,  # Usually can't determine for VCF without upstream context
        "variant_type": None,
        "reference_assembly": None,
        "confidence": 0.0,
        "caller": None,
        "matched_rules": [],
        "evidence": [],
        "warnings": [],
    }

    lines = header_text.strip().split("\n")

    # Parse header lines by type
    reference_lines = [l for l in lines if l.startswith("##reference=")]
    contig_lines = [l for l in lines if l.startswith("##contig=")]
    source_lines = [l for l in lines if l.startswith("##source=")]
    info_lines = [l for l in lines if l.startswith("##INFO=")]
    format_lines = [l for l in lines if l.startswith("##FORMAT=")]

    # Check reference assembly
    for line in reference_lines + contig_lines:
        for rule in VCF_REFERENCE_RULES:
            if re.search(rule.pattern, line, re.IGNORECASE):
                result["evidence"].append({
                    "rule_id": rule.id,
                    "matched": line[:100] + "..." if len(line) > 100 else line,
                    "classification": rule.classification,
                    "confidence": rule.confidence,
                    "rationale": rule.rationale,
                })
                result["matched_rules"].append(rule.id)
                if rule.classification and not result["reference_assembly"]:
                    result["reference_assembly"] = rule.classification
                break  # Only match first reference rule per line

    # Fallback: detect reference from contig lengths if not found by patterns
    if not result["reference_assembly"] and contig_lines:
        assembly, vote_count, confidence = detect_reference_from_contig_lengths(contig_lines)
        if assembly:
            result["reference_assembly"] = assembly
            result["evidence"].append({
                "rule_id": "vcf_contig_length",
                "matched": f"{vote_count} contigs matched {assembly} chromosome lengths",
                "classification": assembly,
                "confidence": confidence,
                "rationale": "Chromosome lengths are unique to each reference assembly. "
                            "Matching contig lengths against known reference sizes provides "
                            "definitive assembly identification.",
            })
            result["matched_rules"].append("vcf_contig_length")

    # Fallback: detect reference from max variant positions (requires variant content)
    if not result["reference_assembly"] and max_positions:
        assembly, evidence_count, confidence = detect_reference_from_max_positions(max_positions)
        if assembly:
            result["reference_assembly"] = assembly
            result["evidence"].append({
                "rule_id": "vcf_max_positions",
                "matched": f"Ruled out assemblies based on {evidence_count} chromosome position(s)",
                "classification": assembly,
                "confidence": confidence,
                "rationale": "Variant positions exceeding chromosome lengths rule out "
                            "references where those positions cannot exist.",
            })
            result["matched_rules"].append("vcf_max_positions")

    # Check variant caller from ##source
    all_caller_rules = (
        VCF_GERMLINE_CALLER_RULES +
        VCF_SOMATIC_CALLER_RULES +
        VCF_SV_CALLER_RULES +
        VCF_CNV_CALLER_RULES
    )
    for line in source_lines:
        for rule in all_caller_rules:
            if re.search(rule.pattern, line, re.IGNORECASE):
                result["evidence"].append({
                    "rule_id": rule.id,
                    "matched": line,
                    "classification": rule.classification,
                    "confidence": rule.confidence,
                    "rationale": rule.rationale,
                })
                result["matched_rules"].append(rule.id)

                # Extract caller name
                caller_match = re.search(r"##source=(.+)", line)
                if caller_match and not result["caller"]:
                    result["caller"] = caller_match.group(1).strip()

                # Update classification if higher confidence
                if rule.classification and rule.confidence > result["confidence"]:
                    result["data_modality"] = rule.classification
                    result["confidence"] = rule.confidence

                    # Set variant type and data_type based on classification
                    if "germline" in rule.classification:
                        result["variant_type"] = "germline"
                        result["data_type"] = "variant_calls"
                    elif "somatic" in rule.classification:
                        result["variant_type"] = "somatic"
                        result["data_type"] = "variant_calls"
                    elif "structural" in rule.classification:
                        result["variant_type"] = "structural"
                        result["data_type"] = "structural_variants"
                    elif "copy_number" in rule.classification:
                        result["variant_type"] = "cnv"
                        result["data_type"] = "structural_variants"

    # Check INFO fields for variant type hints
    info_text = "\n".join(info_lines)
    for rule in VCF_INFO_RULES:
        if re.search(rule.pattern, info_text, re.IGNORECASE):
            result["evidence"].append({
                "rule_id": rule.id,
                "matched": f"INFO field pattern: {rule.pattern}",
                "classification": rule.classification,
                "confidence": rule.confidence,
                "rationale": rule.rationale,
            })
            result["matched_rules"].append(rule.id)

            # Only use INFO rules if no caller was detected
            if not result["data_modality"] and rule.classification:
                result["data_modality"] = rule.classification
                result["confidence"] = rule.confidence

    # Default to genomic if no specific modality detected but we have evidence
    if not result["data_modality"] and result["evidence"]:
        result["data_modality"] = "genomic"
        result["data_type"] = "variant_calls"  # Default for VCF files
        result["confidence"] = 0.5

    # Check for conflicting signals
    variant_types_found = set()
    for e in result["evidence"]:
        classification = e.get("classification", "")
        if classification:
            if "germline" in classification:
                variant_types_found.add("germline")
            elif "somatic" in classification:
                variant_types_found.add("somatic")

    if len(variant_types_found) > 1:
        result["warnings"].append(
            f"VARIANT TYPE CONFLICT: Both {' and '.join(variant_types_found)} signals detected. "
            "This may indicate a multi-caller VCF or annotation error."
        )
        result["confidence"] = max(0.3, result["confidence"] - 0.2)

    return result


def classify_from_fastq_header(
    read_lines: list[str],
    file_name: str = "",
) -> dict:
    """
    Classify data modality and platform from FASTQ read name format.

    Args:
        read_lines: List of read name lines (starting with @)
        file_name: Optional filename for additional context

    Returns dict with:
        - data_modality: str or None
        - platform: str or None (ILLUMINA, PACBIO, ONT, MGI, etc.)
        - confidence: float
        - matched_rules: list of rule IDs that matched
        - evidence: list of dicts with rule details and rationales
        - is_paired_end: bool or None
        - instrument_hint: str or None (extracted instrument ID if available)
    """
    import re

    result = {
        "data_modality": None,
        "data_type": "reads",  # FASTQ files contain raw reads
        "assay_type": None,  # WGS for long-read, ambiguous for Illumina
        "platform": None,
        "confidence": 0.0,
        "is_paired_end": None,
        "instrument_hint": None,
        "archive_accession": None,  # ENA/SRA/DDBJ accession if present
        "archive_source": None,     # "ENA", "SRA", or "DDBJ"
        "matched_rules": [],
        "evidence": [],
        "warnings": [],
    }

    if not read_lines:
        return result

    # Check multiple reads for consistency (use first 10)
    sample_reads = read_lines[:10]
    platform_votes = {}

    # First pass: extract archive accession if present
    accession_pattern = re.compile(r"^@(ERR|SRR|DRR)(\d+)\.\d+\s*(.*)$")
    archive_sources = {"ERR": "ENA", "SRR": "SRA", "DRR": "DDBJ"}

    for read_name in sample_reads:
        if not read_name.startswith("@"):
            continue
        match = accession_pattern.match(read_name)
        if match:
            prefix, acc_num, remainder = match.groups()
            result["archive_accession"] = f"{prefix}{acc_num}"
            result["archive_source"] = archive_sources[prefix]
            break  # All reads should have the same accession

    for read_name in sample_reads:
        if not read_name.startswith("@"):
            continue

        # Check platform-specific patterns
        all_platform_rules = (
            FASTQ_ILLUMINA_RULES +
            FASTQ_PACBIO_RULES +
            FASTQ_ONT_RULES +
            FASTQ_MGI_RULES +
            FASTQ_ELEMENT_RULES +
            FASTQ_ULTIMA_RULES
        )

        # For archive-reformatted reads, also check the text after the accession
        # Format: @ERR123456.1 A00297:44:HFKH3DSXX:... -> original is after space
        texts_to_check = [read_name]
        acc_match = accession_pattern.match(read_name)
        if acc_match and acc_match.group(3):
            # Add the remainder (original read name after accession) with @ prefix
            remainder = "@" + acc_match.group(3).strip()
            if remainder != "@":
                texts_to_check.append(remainder)

        for text in texts_to_check:
            for rule in all_platform_rules:
                if re.search(rule.pattern, text):
                    platform_votes[rule.platform] = platform_votes.get(rule.platform, 0) + 1

                    # Only add evidence once per rule
                    if rule.id not in result["matched_rules"]:
                        matched_text = text[:80] + "..." if len(text) > 80 else text
                        if text != read_name:
                            matched_text = f"(from original: {matched_text})"
                        result["evidence"].append({
                            "rule_id": rule.id,
                            "matched": matched_text,
                            "classification": rule.classification,
                            "platform": rule.platform,
                            "confidence": rule.confidence,
                            "rationale": rule.rationale,
                        })
                        result["matched_rules"].append(rule.id)

                        # Update classification if higher confidence
                        if rule.confidence > result["confidence"]:
                            result["data_modality"] = rule.classification
                            result["platform"] = rule.platform
                            result["confidence"] = rule.confidence

        # Check for paired-end indicators
        for rule in FASTQ_PAIREDEND_RULES:
            if re.search(rule.pattern, read_name):
                result["is_paired_end"] = True
                if rule.id not in result["matched_rules"]:
                    result["evidence"].append({
                        "rule_id": rule.id,
                        "matched": "Paired-end indicator found",
                        "classification": None,
                        "platform": None,
                        "confidence": rule.confidence,
                        "rationale": rule.rationale,
                    })
                    result["matched_rules"].append(rule.id)

    # Extract instrument hint for Illumina
    if result["platform"] == "ILLUMINA" and sample_reads:
        first_read = sample_reads[0]
        # Modern format: @instrument:run:flowcell:...
        # Also check after archive accession: @ERR123.1 A00297:44:...
        match = re.match(r"@([A-Z0-9-]+):", first_read)
        if not match:
            # Try extracting from text after archive accession
            acc_match = accession_pattern.match(first_read)
            if acc_match and acc_match.group(3):
                remainder = acc_match.group(3).strip()
                match = re.match(r"([A-Z0-9-]+):", remainder)
        if match:
            result["instrument_hint"] = match.group(1)

            # Infer instrument model from ID prefix
            inst_id = match.group(1)
            if inst_id.startswith("A"):
                result["instrument_model"] = "NovaSeq 6000" if inst_id.startswith("A0") else "NovaSeq"
            elif inst_id.startswith("M"):
                result["instrument_model"] = "MiSeq"
            elif inst_id.startswith("D"):
                result["instrument_model"] = "HiSeq 2500"
            elif inst_id.startswith("E"):
                result["instrument_model"] = "HiSeq X"
            elif inst_id.startswith("N"):
                result["instrument_model"] = "NextSeq"
            elif inst_id.startswith("V"):
                result["instrument_model"] = "NextSeq 2000"

    # Check for platform consistency
    if len(platform_votes) > 1:
        result["warnings"].append(
            f"PLATFORM INCONSISTENCY: Multiple platforms detected in reads: "
            f"{', '.join(f'{p}({c})' for p, c in platform_votes.items())}. "
            "This may indicate mixed data or format conversion artifacts."
        )
        result["confidence"] = max(0.3, result["confidence"] - 0.2)

    # Boost confidence if all reads agree
    elif platform_votes and len(sample_reads) >= 3:
        dominant_platform = max(platform_votes.keys(), key=lambda k: platform_votes[k])
        if platform_votes[dominant_platform] == len([r for r in sample_reads if r.startswith("@")]):
            result["confidence"] = min(0.99, result["confidence"] + 0.05)

    # Check filename for additional hints
    if file_name:
        file_lower = file_name.lower()
        if "_r1" in file_lower or "_r2" in file_lower or ".r1." in file_lower or ".r2." in file_lower:
            result["is_paired_end"] = True
        if "ccs" in file_lower or "hifi" in file_lower:
            result["data_modality"] = "genomic"
            result["assay_type"] = "WGS"  # CCS/HiFi are WGS assays

    # Infer assay_type from platform
    if result["platform"] in ["PACBIO", "ONT"]:
        result["assay_type"] = "WGS"
    # Check filename for assay hints
    if file_name:
        file_lower = file_name.lower()
        if "rnaseq" in file_lower or "rna-seq" in file_lower or "rna_seq" in file_lower:
            result["assay_type"] = "RNA-seq"
        elif "scrna" in file_lower or "sc_rna" in file_lower or "10x" in file_lower:
            result["assay_type"] = "scRNA-seq"
        elif "atac" in file_lower:
            result["assay_type"] = "ATAC-seq"
        elif "chip" in file_lower:
            result["assay_type"] = "ChIP-seq"
        elif "wgs" in file_lower or "whole_genome" in file_lower or "wholegenome" in file_lower:
            result["assay_type"] = "WGS"
        elif "wes" in file_lower or "exome" in file_lower:
            result["assay_type"] = "WES"

    return result


def get_rules_documentation() -> str:
    """Generate markdown documentation of all header classification rules."""
    doc = """# BAM/CRAM, VCF, and FASTQ Header Classification Rules

## Overview

This document describes the rules used to classify BAM/CRAM, VCF, and FASTQ files based on their
header content. Headers contain metadata about sequencing platform, alignment
software, and reference genome that can definitively identify data modality and reference assembly.

## Header Sections Reference

### @HD (Header)
File-level metadata including SAM format version and sort order.

### @SQ (Sequence Dictionary)
Reference sequences the reads are aligned to. Key fields:
- **SN**: Sequence name (e.g., chr1, NC_000001.11)
- **LN**: Sequence length
- **AS**: Genome assembly identifier (e.g., GRCh38)
- **M5**: MD5 checksum of sequence

### @RG (Read Group)
Metadata about a set of reads. Key fields:
- **ID**: Read group identifier
- **PL**: Platform/technology (ILLUMINA, PACBIO, ONT)
- **PM**: Platform model (e.g., SEQUELII, NovaSeq)
- **SM**: Sample name
- **DS**: Description (PacBio uses for READTYPE)

### @PG (Program)
Software used to create/modify the file. Key fields:
- **ID**: Program record identifier
- **PN**: Program name (e.g., bwa, STAR, minimap2)
- **VN**: Program version
- **CL**: Command line used

---

## Classification Rules

"""

    sections = [
        ("Platform Detection", "@RG PL field", PLATFORM_RULES),
        ("PacBio Read Type", "@RG DS field", PACBIO_READTYPE_RULES),
        ("RNA-seq Programs", "@PG PN field", RNASEQ_PROGRAM_RULES),
        ("DNA Alignment Programs", "@PG PN field", DNA_PROGRAM_RULES),
        ("PacBio Programs", "@PG PN field", PACBIO_PROGRAM_RULES),
        ("Reference Assembly", "@SQ SN/AS fields", REFERENCE_RULES),
        ("Unaligned Detection", "@SQ absence", UNALIGNED_RULES),
    ]

    for section_name, header_location, rules in sections:
        doc += f"### {section_name}\n\n"
        doc += f"*Source: {header_location}*\n\n"

        for rule in rules:
            pattern = rule.pattern or "(absent)"
            classification = rule.classification or "N/A (ambiguous)"
            doc += f"#### `{rule.id}`\n\n"
            doc += f"- **Pattern**: `{pattern}`\n"
            doc += f"- **Classification**: {classification}\n"
            doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
            doc += f"**Rationale**: {rule.rationale}\n\n"

        doc += "---\n\n"

    # Add consistency validation rules
    doc += """## Consistency Validation Rules

The classifier validates that multiple signals in the same header are consistent.
Convergent signals (that agree) increase confidence, while conflicting signals
indicate potential errors and reduce confidence.

### Convergent Signals (Should Agree)

These signal pairs reinforce each other when both are present:

"""

    for rule in CONVERGENT_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Signal A**: `{rule.signal_a}`\n"
        doc += f"- **Signal B**: `{rule.signal_b}`\n"
        doc += f"- **Expected Agreement**: {rule.expected_agreement}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### Conflicting Signals (Indicate Errors)\n\n"
    doc += "These signal pairs should NOT appear together. If found, confidence is reduced:\n\n"

    for rule in CONFLICTING_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Signal A**: `{rule.signal_a}`\n"
        doc += f"- **Signal B**: `{rule.signal_b}`\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += """---

## File Size Rules (WGS vs WES)

File size helps distinguish Whole Genome Sequencing (WGS) from Whole Exome Sequencing (WES):

| Type | Typical BAM Size | Typical CRAM Size |
|------|------------------|-------------------|
| WGS 30x | 50-150 GB | 15-50 GB |
| WES 100x | 5-15 GB | 2-8 GB |

The ~10:1 ratio exists because WGS covers the whole genome (~3 billion bases) while
WES only covers exons (~1-2% of genome, ~30-60 million bases).

**Caveats:**
- Coverage depth varies (higher coverage = larger files)
- CRAM is ~60-70% smaller than BAM
- Some files may be subsets or downsampled
- Long-read BAMs (PacBio/ONT) are typically larger due to read length

"""

    for rule in FILE_SIZE_RULES:
        min_size = f"{rule.min_size_gb:.0f} GB" if rule.min_size_gb else "any"
        max_size = f"{rule.max_size_gb:.0f} GB" if rule.max_size_gb else "any"
        size_range = f"{min_size} - {max_size}"
        platform = rule.platform or "any"
        file_format = rule.file_format or "any"

        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Size Range**: {size_range}\n"
        doc += f"- **Platform**: {platform}\n"
        doc += f"- **File Format**: {file_format}\n"
        doc += f"- **Classification**: {rule.classification}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += """---

## VCF Header Classification Rules

VCF files contain rich metadata in `##` header lines that can identify:
- Reference genome (from `##reference=` and `##contig=` lines)
- Variant caller (from `##source=` line)
- Variant type (germline, somatic, structural, CNV)

### VCF Header Line Reference

| Line Type | Description | Example |
|-----------|-------------|---------|
| `##fileformat` | VCF version | `##fileformat=VCFv4.2` |
| `##reference` | Reference genome path | `##reference=file:///path/to/GRCh38.fa` |
| `##contig` | Contig definitions | `##contig=<ID=chr1,length=248956422,assembly=GRCh38>` |
| `##source` | Variant caller | `##source=GATK HaplotypeCaller` |
| `##INFO` | INFO field definitions | `##INFO=<ID=DP,Number=1,Type=Integer,...>` |
| `##FORMAT` | FORMAT field definitions | `##FORMAT=<ID=GT,Number=1,Type=String,...>` |

### Reference Assembly Detection

"""

    for rule in VCF_REFERENCE_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Header Type**: `{rule.header_type}`\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Classification**: {rule.classification}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### Germline Variant Callers\n\n"

    for rule in VCF_GERMLINE_CALLER_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Classification**: {rule.classification}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### Somatic Variant Callers\n\n"

    for rule in VCF_SOMATIC_CALLER_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Classification**: {rule.classification}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### Structural Variant Callers\n\n"

    for rule in VCF_SV_CALLER_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Classification**: {rule.classification}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### Copy Number Variant Callers\n\n"

    for rule in VCF_CNV_CALLER_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Classification**: {rule.classification}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### INFO Field Indicators\n\n"

    for rule in VCF_INFO_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Classification**: {rule.classification}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += """---

## FASTQ Read Name Classification Rules

FASTQ read names have platform-specific formats that can identify the sequencing platform,
instrument model, and read type without inspecting the sequence data.

### Read Name Format Examples

| Platform | Example Read Name | Format |
|----------|------------------|--------|
| **Illumina (modern)** | `@A00488:61:HFWFVDSXX:1:1101:1000:1000` | `@instrument:run:flowcell:lane:tile:x:y` |
| **Illumina (legacy)** | `@HWUSI-EAS100R:6:73:941:1973#0/1` | `@instrument:lane:tile:x:y#index/read` |
| **ENA/SRA reformatted** | `@ERR123456.1 A00297:44:HFKH3DSXX:...` | `@accession.seq [original read name]` |
| **PacBio CCS/HiFi** | `@m64011_190830_220126/1/ccs` | `@movie/zmw/ccs` |
| **PacBio CLR** | `@m64011_190830_220126/1234/0_5000` | `@movie/zmw/start_end` |
| **ONT** | `@a1b2c3d4-e5f6-7890-abcd-ef1234567890` | `@uuid [key=value...]` |
| **MGI/BGI** | `@V350012345L1C001R0010000001/1` | `@flowcellLaneCcolumnRrow/pair` |

### Illumina Read Names

"""

    for rule in FASTQ_ILLUMINA_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Platform**: {rule.platform}\n"
        doc += f"- **Classification**: {rule.classification or 'N/A'}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### PacBio Read Names\n\n"

    for rule in FASTQ_PACBIO_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Platform**: {rule.platform}\n"
        doc += f"- **Classification**: {rule.classification or 'N/A'}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### Oxford Nanopore (ONT) Read Names\n\n"

    for rule in FASTQ_ONT_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Platform**: {rule.platform}\n"
        doc += f"- **Classification**: {rule.classification or 'N/A'}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### MGI/BGI Read Names\n\n"

    for rule in FASTQ_MGI_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Platform**: {rule.platform}\n"
        doc += f"- **Classification**: {rule.classification or 'N/A'}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### Other Platforms\n\n"

    for rule in FASTQ_ELEMENT_RULES + FASTQ_ULTIMA_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Platform**: {rule.platform}\n"
        doc += f"- **Classification**: {rule.classification or 'N/A'}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### Archive Accessions (ENA/SRA/DDBJ)\n\n"
    doc += """When FASTQ files are submitted to public archives (ENA, SRA, DDBJ), read names are
prefixed with accession IDs. The original instrument information is often preserved after the accession.

**Example**: `@ERR3242571.1 A00297:44:HFKH3DSXX:2:1354:30508:28839/1`
- Archive accession: `ERR3242571` (ENA)
- Original read name: `A00297:44:HFKH3DSXX:2:1354:30508:28839/1` (NovaSeq)

The accession can be used to query archive APIs for study metadata:
- **ENA**: `https://www.ebi.ac.uk/ena/browser/api/xml/ERRxxxxxxx`
- **SRA**: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra&id=SRRxxxxxxx`
- **DDBJ**: `https://ddbj.nig.ac.jp/resource/sra-run/DRRxxxxxxx`

"""

    for rule in FASTQ_ARCHIVE_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Archive**: {rule.id.split('_')[1].upper()}\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n### Paired-End Detection\n\n"

    for rule in FASTQ_PAIREDEND_RULES:
        doc += f"#### `{rule.id}`\n\n"
        doc += f"- **Pattern**: `{rule.pattern}`\n"
        doc += f"- **Confidence**: {rule.confidence:.0%}\n\n"
        doc += f"**Rationale**: {rule.rationale}\n\n"

    doc += "---\n\n"

    return doc
