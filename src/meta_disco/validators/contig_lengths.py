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
# All 22 autosomes + X + Y with both chr-prefixed and bare names.
# Every chromosome has a unique length per assembly (min diff 41Kbp).
# TODO: Consolidate with reference_contig_lengths in unified_rules.yaml
REFERENCE_CONTIG_LENGTHS: dict[str, dict[str, int]] = {
    "GRCh38": {
        "chr1": 248956422, "1": 248956422,
        "chr2": 242193529, "2": 242193529,
        "chr3": 198295559, "3": 198295559,
        "chr4": 190214555, "4": 190214555,
        "chr5": 181538259, "5": 181538259,
        "chr6": 170805979, "6": 170805979,
        "chr7": 159345973, "7": 159345973,
        "chr8": 145138636, "8": 145138636,
        "chr9": 138394717, "9": 138394717,
        "chr10": 133797422, "10": 133797422,
        "chr11": 135086622, "11": 135086622,
        "chr12": 133275309, "12": 133275309,
        "chr13": 114364328, "13": 114364328,
        "chr14": 107043718, "14": 107043718,
        "chr15": 101991189, "15": 101991189,
        "chr16": 90338345, "16": 90338345,
        "chr17": 83257441, "17": 83257441,
        "chr18": 80373285, "18": 80373285,
        "chr19": 58617616, "19": 58617616,
        "chr20": 64444167, "20": 64444167,
        "chr21": 46709983, "21": 46709983,
        "chr22": 50818468, "22": 50818468,
        "chrX": 156040895, "X": 156040895,
        "chrY": 57227415, "Y": 57227415,
    },
    "GRCh37": {
        "chr1": 249250621, "1": 249250621,
        "chr2": 243199373, "2": 243199373,
        "chr3": 198022430, "3": 198022430,
        "chr4": 191154276, "4": 191154276,
        "chr5": 180915260, "5": 180915260,
        "chr6": 171115067, "6": 171115067,
        "chr7": 159138663, "7": 159138663,
        "chr8": 146364022, "8": 146364022,
        "chr9": 141213431, "9": 141213431,
        "chr10": 135534747, "10": 135534747,
        "chr11": 135006516, "11": 135006516,
        "chr12": 133851895, "12": 133851895,
        "chr13": 115169878, "13": 115169878,
        "chr14": 107349540, "14": 107349540,
        "chr15": 102531392, "15": 102531392,
        "chr16": 90354753, "16": 90354753,
        "chr17": 81195210, "17": 81195210,
        "chr18": 78077248, "18": 78077248,
        "chr19": 59128983, "19": 59128983,
        "chr20": 63025520, "20": 63025520,
        "chr21": 48129895, "21": 48129895,
        "chr22": 51304566, "22": 51304566,
        "chrX": 155270560, "X": 155270560,
        "chrY": 59373566, "Y": 59373566,
    },
    "CHM13": {
        "chr1": 248387497, "1": 248387497,
        "chr2": 242696747, "2": 242696747,
        "chr3": 201106605, "3": 201106605,
        "chr4": 193574945, "4": 193574945,
        "chr5": 182045439, "5": 182045439,
        "chr6": 172126628, "6": 172126628,
        "chr7": 160567428, "7": 160567428,
        "chr8": 146259331, "8": 146259331,
        "chr9": 150617247, "9": 150617247,
        "chr10": 134758134, "10": 134758134,
        "chr11": 135127769, "11": 135127769,
        "chr12": 133324548, "12": 133324548,
        "chr13": 113566686, "13": 113566686,
        "chr14": 101161492, "14": 101161492,
        "chr15": 99753195, "15": 99753195,
        "chr16": 96330374, "16": 96330374,
        "chr17": 84276897, "17": 84276897,
        "chr18": 80542538, "18": 80542538,
        "chr19": 61707364, "19": 61707364,
        "chr20": 66210255, "20": 66210255,
        "chr21": 45090682, "21": 45090682,
        "chr22": 51324926, "22": 51324926,
        "chrX": 154259566, "X": 154259566,
        "chrY": 62460029, "Y": 62460029,
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
        top_count = votes[winner]
        # If multiple assemblies are tied, evidence is ambiguous — don't guess
        if sum(1 for v in votes.values() if v == top_count) > 1:
            return None, 0, 0.0
        # Lower confidence if no exact matches (fuzzy only)
        confidence = 0.98 if exact_matches > 0 else 0.95
        return winner, top_count, confidence

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
