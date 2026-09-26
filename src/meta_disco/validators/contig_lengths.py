"""Reference assembly detection from chromosome contig lengths.

Chromosome lengths are unique to each reference assembly. This provides
definitive reference detection even when ##reference or assembly= tags
are missing. We use a subset of chromosomes for efficiency.

Sources:
- GRCh38: https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.40
- GRCh37: https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.13
- CHM13: https://www.ncbi.nlm.nih.gov/assembly/GCF_009914755.1 (T2T-CHM13v2.0; the
  earlier releases fall inside the matching tolerance, see #473)

Data loaded from the bundled unified_rules.yaml (package data of meta_disco.rules,
single source of truth).
"""

from collections.abc import Iterable

from ..rule_loader import get_unified_rules


def _load_contig_lengths() -> dict[str, dict[str, int]]:
    """Load contig lengths from YAML and generate bare-name variants."""
    yaml_data = get_unified_rules().reference_contig_lengths
    result: dict[str, dict[str, int]] = {}
    for assembly, contigs in yaml_data.items():
        expanded: dict[str, int] = {}
        for name, length in contigs.items():
            expanded[name] = length
            # Generate bare-name variant (e.g., "1" from "chr1")
            bare = name.removeprefix("chr")
            if bare != name:
                expanded[bare] = length
        result[assembly] = expanded
    return result


# Chromosome lengths for each reference assembly
# All 22 autosomes + X + Y with both chr-prefixed and bare names.
# Every chromosome has a unique length per assembly (min diff 16,408 bp, GRCh38
# against GRCh37 on chr16).
REFERENCE_CONTIG_LENGTHS: dict[str, dict[str, int]] = _load_contig_lengths()

# The candidates a normalized contig name can match: each assembly's length for that
# name, in the table's assembly order so a tie still goes to the first one. The scan
# this replaced ran for every contig the exact `(name, length)` lookup missed, and
# compared it against every spelling of every assembly (`chr1` and `1` share one
# length) — on a GATK header, that is every one of its thousands of unplaced
# contigs, most of the VCF producer's work (#488). A name the table does not hold
# — every decoy, alt and unplaced contig — has no entry here.
_CANDIDATES_BY_NAME: dict[str, dict[str, int]] = {}
for _assembly, _contigs in REFERENCE_CONTIG_LENGTHS.items():
    for _contig, _length in _contigs.items():
        _CANDIDATES_BY_NAME.setdefault(_contig.removeprefix("chr"), {})[_assembly] = _length


# Maximum chromosome lengths for position-based exclusion
# (grch37_len, grch38_len, chm13_len) for key chromosomes
# Derived from REFERENCE_CONTIG_LENGTHS to avoid a second hardcoded copy.
CHROMOSOME_MAX_LENGTHS: dict[str, tuple[int, int, int]] = {
    chrom: (
        REFERENCE_CONTIG_LENGTHS["GRCh37"][f"chr{chrom}"],
        REFERENCE_CONTIG_LENGTHS["GRCh38"][f"chr{chrom}"],
        REFERENCE_CONTIG_LENGTHS["CHM13"][f"chr{chrom}"],
    )
    for chrom in ("1", "2", "3", "10", "22")
}


# How far, in bp, a length may sit from a table row and still match it. One row per
# family spans its releases on this allowance: CHM13 v1.0 sits up to 657 bp from the
# v2.0 row (#473), while the families differ by at least 16,408 bp on every chromosome.
# BED coordinate detection rules an assembly out past the same allowance.
CONTIG_LENGTH_TOLERANCE = 1000


def detect_reference_from_contigs(
    contigs: Iterable[tuple[str, int | None]], tolerance: int = CONTIG_LENGTH_TOLERANCE
) -> tuple[str | None, int]:
    """
    Detect reference assembly from ``(contig name, length)`` pairs.

    This is a definitive signal - chromosome lengths are unique to each assembly.
    Uses fuzzy matching with tolerance to handle minor version differences
    (e.g., CHM13 v1.0 vs v2.0 differ by < 1000bp per chromosome).

    Each contig is one dictionary lookup: the closest of its name's candidates —
    at most one per assembly — within ``tolerance`` votes, an exact length being
    the closest, a tie going to the first assembly in table order; a name the
    table does not hold, or a pair with no length, votes for nothing.

    Args:
        contigs: ``(name, length)`` pairs, the name with or without a ``chr`` prefix
        tolerance: Max difference in bp to consider a match (default CONTIG_LENGTH_TOLERANCE)

    Returns:
        Tuple of (assembly, vote_count)
        - assembly: "GRCh38", "GRCh37", "CHM13", or None
        - vote_count: Number of contigs that matched
    """
    votes: dict[str, int] = {}

    for name, length in contigs:
        if length is None:
            continue
        best_match = None
        best_diff = tolerance + 1
        for ref_assembly, ref_length in _CANDIDATES_BY_NAME.get(name.removeprefix("chr"), {}).items():
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
            return None, 0
        return winner, top_count

    return None, 0


def detect_reference_from_max_positions(
    max_positions: dict[str, int],
) -> tuple[str | None, int]:
    """
    Detect reference assembly by ruling out references where variant
    positions exceed chromosome lengths.

    When header-based detection fails, we can use max variant positions to
    rule out references. If a variant sits more than ``CONTIG_LENGTH_TOLERANCE``
    past a reference's chromosome length, that reference is ruled out.

    Args:
        max_positions: Dict mapping chromosome (without 'chr') to max position seen

    Returns:
        Tuple of (assembly, evidence_count)
        - assembly: "GRCh38", "GRCh37", "CHM13", or None if inconclusive
        - evidence_count: Number of chromosomes used for ruling out
    """
    if not max_positions:
        return None, 0

    possible = {"GRCh37", "GRCh38", "CHM13"}
    evidence_count = 0

    for chrom, max_pos in max_positions.items():
        chrom = chrom.removeprefix("chr")
        if chrom not in CHROMOSOME_MAX_LENGTHS:
            continue

        grch37_len, grch38_len, chm13_len = CHROMOSOME_MAX_LENGTHS[chrom]

        # Rule out references where position exceeds chromosome length
        ruled_out_any = False
        if max_pos > chm13_len + CONTIG_LENGTH_TOLERANCE:
            possible.discard("CHM13")
            ruled_out_any = True
        if max_pos > grch38_len + CONTIG_LENGTH_TOLERANCE:
            possible.discard("GRCh38")
            ruled_out_any = True
        if max_pos > grch37_len + CONTIG_LENGTH_TOLERANCE:
            possible.discard("GRCh37")
            ruled_out_any = True
        if ruled_out_any:
            evidence_count += 1

    # If narrowed to exactly one reference
    if len(possible) == 1 and evidence_count > 0:
        return possible.pop(), evidence_count

    return None, 0
