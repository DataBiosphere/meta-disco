"""Reference assembly detection from chromosome contig lengths.

A chromosome name two reference assemblies share has a different length in each.
This provides definitive reference detection even when ##reference or assembly=
tags are missing. The table holds each assembly's autosomes, X and Y.

Sources:
- GRCh38: https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.40
- GRCh37: https://www.ncbi.nlm.nih.gov/assembly/GCF_000001405.13
- CHM13: https://www.ncbi.nlm.nih.gov/assembly/GCF_009914755.1 (T2T-CHM13v2.0; an
  earlier release matches it on most chromosomes, not all — see
  ``CONTIG_LENGTH_TOLERANCE`` and #473)
- Mmul_10 (rhesus macaque): https://www.ncbi.nlm.nih.gov/assembly/GCF_003339765.1 (#636)
- mCalJa1.2.pat.X (common marmoset): https://www.ncbi.nlm.nih.gov/assembly/GCF_011100555.1

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
# Every autosome + X + Y, with both chr-prefixed and bare names. How far apart the
# assemblies' lengths sit is in the table's comment in unified_rules.yaml.
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


# What BED coordinate elimination (``header_classifier._infer_bed_reference``) rules out
# among: the human rows, as no BED in the corpus is from a monkey. Elimination is sound
# only over every assembly a file could be on, so a monkey BED can be called human (#640).
HUMAN_ASSEMBLIES: tuple[str, ...] = ("GRCh37", "GRCh38", "CHM13")
# Their rows as the YAML spells them (``chr``-prefixed only), in the table's order, which
# is the order a BED reason names ruled-out assemblies in; built at import, so a name the
# table lacks fails there rather than on the first BED.
if _missing := set(HUMAN_ASSEMBLIES) - set(get_unified_rules().reference_contig_lengths):
    raise KeyError(f"HUMAN_ASSEMBLIES names rows reference_contig_lengths lacks: {sorted(_missing)}")
HUMAN_CONTIG_LENGTHS: dict[str, dict[str, int]] = {
    assembly: lengths
    for assembly, lengths in get_unified_rules().reference_contig_lengths.items()
    if assembly in HUMAN_ASSEMBLIES
}


# How far, in bp, a length may sit from a table row and still match it: small drift
# between releases matches, while the families differ by at least 16,408 bp on every
# chromosome. CHM13 v1.0 is within it of the v2.0 row on 18 of 23 chromosomes, and
# not on the acrocentrics (chr13, 14, 15, 21, 22: 28,980-737,009 bp longer), so a
# v1.0 file matches on its other chromosomes (#473). BED coordinate detection rules
# an assembly out past the same allowance.
CONTIG_LENGTH_TOLERANCE = 1000


def detect_reference_from_contigs(
    contigs: Iterable[tuple[str, int | None]], tolerance: int = CONTIG_LENGTH_TOLERANCE
) -> tuple[str | None, int]:
    """
    Detect reference assembly from ``(contig name, length)`` pairs.

    This is a definitive signal - a chromosome name two assemblies share has a different
    length in each.
    Uses fuzzy matching with tolerance to handle minor version differences, so a
    file from an earlier release matches its family's row on most chromosomes;
    the vote is per contig, so the ones that do not match (CHM13 v1.0's
    acrocentrics, see ``CONTIG_LENGTH_TOLERANCE``) are outvoted rather than fatal.

    Each contig is one dictionary lookup: the closest of its name's candidates —
    at most one per assembly — within ``tolerance`` votes, an exact length being
    the closest, a tie going to the first assembly in table order; a name the
    table does not hold, or a pair with no length, votes for nothing.

    Args:
        contigs: ``(name, length)`` pairs, the name with or without a ``chr`` prefix
        tolerance: Max difference in bp to consider a match (default CONTIG_LENGTH_TOLERANCE)

    Returns:
        Tuple of (assembly, vote_count)
        - assembly: a ``reference_contig_lengths`` row's name, or None
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
