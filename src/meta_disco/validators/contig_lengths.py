"""Reference assembly detection from chromosome contig lengths.

Chromosome lengths are unique to each reference assembly. This provides
definitive reference detection even when ##reference or assembly= tags
are missing. We use a subset of chromosomes for efficiency.

Sources:
- GRCh38: https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.40
- GRCh37: https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.13
- CHM13: https://www.ncbi.nlm.nih.gov/assembly/GCF_009914755.1
"""

import re

# Chromosome lengths for each reference assembly
# Uses a subset of chromosomes for efficient matching
REFERENCE_CONTIG_LENGTHS: dict[str, dict[str, int]] = {
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
_CONTIG_LENGTH_TO_ASSEMBLY: dict[tuple[str, int], str] = {}
for _assembly, _contigs in REFERENCE_CONTIG_LENGTHS.items():
    for _contig, _length in _contigs.items():
        # Normalize contig name (remove chr prefix)
        _normalized = _contig.replace("chr", "")
        _key = (_normalized, _length)
        _CONTIG_LENGTH_TO_ASSEMBLY[_key] = _assembly


# Maximum chromosome lengths for position-based exclusion
# (grch37_len, grch38_len, chm13_len) for key chromosomes
CHROMOSOME_MAX_LENGTHS: dict[str, tuple[int, int, int]] = {
    "1": (249250621, 248956422, 248387497),
    "2": (243199373, 242193529, 242696747),
    "3": (198022430, 198295559, 201106605),
    "10": (135534747, 133797422, 134758134),
    "22": (51304566, 50818468, 51324926),
}


def detect_reference_from_contig_lengths(
    contig_lines: list[str],
    tolerance: int = 1000
) -> tuple[str | None, int, float]:
    """
    Detect reference assembly from contig lengths in VCF ##contig lines or BAM @SQ lines.

    This is a definitive signal - chromosome lengths are unique to each assembly.
    Uses fuzzy matching with tolerance to handle minor version differences
    (e.g., CHM13 v1.0 vs v2.0 differ by < 1000bp per chromosome).

    Args:
        contig_lines: List of ##contig=<...> lines from VCF header or @SQ lines from BAM
        tolerance: Max difference in bp to consider a match (default 1000)

    Returns:
        Tuple of (assembly, vote_count, confidence)
        - assembly: "GRCh38", "GRCh37", "CHM13", or None
        - vote_count: Number of contigs that matched
        - confidence: 0.98 for exact match, 0.95 for fuzzy match
    """
    votes: dict[str, int] = {}
    exact_matches = 0

    # VCF contig fields can appear in any order: ##contig=<ID=chr1,length=248387497>
    # or ##contig=<ID=chr1,assembly=GRCh38,length=248387497>
    vcf_id_pattern = r'ID=([^,>]+)'
    vcf_len_pattern = r'length=(\d+)'
    # BAM @SQ tags can appear in any order, so match SN and LN independently
    bam_sn_pattern = r'SN:([^\t]+)'
    bam_ln_pattern = r'LN:(\d+)'

    for line in contig_lines:
        contig = None
        length = None

        # Try VCF format first (ID and length fields matched independently)
        if line.startswith("##contig"):
            id_match = re.search(vcf_id_pattern, line)
            len_match = re.search(vcf_len_pattern, line)
            if id_match and len_match:
                contig = id_match.group(1).replace("chr", "")
                length = int(len_match.group(1))
        else:
            # Try BAM format (SN and LN tags can appear in any order)
            sn_match = re.search(bam_sn_pattern, line)
            ln_match = re.search(bam_ln_pattern, line)
            if sn_match and ln_match:
                contig = sn_match.group(1).replace("chr", "")
                length = int(ln_match.group(1))

        if contig is None or length is None:
            continue

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


def detect_reference_from_max_positions(
    max_positions: dict[str, int],
) -> tuple[str | None, int, float]:
    """
    Detect reference assembly by ruling out references where variant
    positions exceed chromosome lengths.

    When header-based detection fails, we can use max variant positions to
    rule out references. If a variant exists at a position beyond a reference's
    chromosome length, that reference is ruled out.

    Args:
        max_positions: Dict mapping chromosome (without 'chr') to max position seen

    Returns:
        Tuple of (assembly, evidence_count, confidence)
        - assembly: "GRCh38", "GRCh37", "CHM13", or None if inconclusive
        - evidence_count: Number of chromosomes used for ruling out
        - confidence: 0.90 when narrowed to one reference
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
        ruled_out_any = False
        if max_pos > chm13_len:
            possible.discard("CHM13")
            ruled_out_any = True
        if max_pos > grch38_len:
            possible.discard("GRCh38")
            ruled_out_any = True
        if max_pos > grch37_len:
            possible.discard("GRCh37")
            ruled_out_any = True
        if ruled_out_any:
            evidence_count += 1

    # If narrowed to exactly one reference
    if len(possible) == 1 and evidence_count > 0:
        return possible.pop(), evidence_count, 0.90

    return None, 0, 0.0
