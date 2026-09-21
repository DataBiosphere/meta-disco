"""The contig-length detector consults an index, never the reference table (#488).

On a GATK hg38 header the exact `(name, length)` lookup missed for every decoy, alt
and unplaced contig — thousands per file — and the fuzzy fallback then scanned every
contig of every assembly for each of them. The index keyed by normalised name makes
each contig one lookup with at most one candidate per assembly. These tests pin that
the table is not scanned per call, and that the votes are what the scan produced.
"""

from collections.abc import Mapping

from meta_disco.validators import contig_lengths
from meta_disco.validators.contig_lengths import (
    REFERENCE_CONTIG_LENGTHS,
    detect_reference_from_contigs,
)

GRCH38_CHR1 = REFERENCE_CONTIG_LENGTHS["GRCh38"]["chr1"]
GRCH37_CHR1 = REFERENCE_CONTIG_LENGTHS["GRCh37"]["chr1"]
CHM13_CHR1 = REFERENCE_CONTIG_LENGTHS["CHM13"]["chr1"]


class _NeverIterated(Mapping):
    """A mapping that answers `in` and `[]` but refuses to be scanned."""

    def __init__(self, backing):
        self._backing = backing

    def __getitem__(self, key):
        return self._backing[key]

    def __len__(self):
        return len(self._backing)

    def __iter__(self):
        raise AssertionError("the detector scanned the reference table (#488)")

    def items(self):
        raise AssertionError("the detector scanned the reference table (#488)")


def _unplaced(n):
    """`n` contigs no assembly names, the shape of a GATK header's tail."""
    return [(f"chrUn_KI{270000 + i}v1", 40_000 + i) for i in range(n)]


def test_the_detector_consults_the_index_not_the_table(monkeypatch):
    """Thousands of unplaced contigs plus one fuzzy hit resolve without a table scan."""
    monkeypatch.setattr(contig_lengths, "REFERENCE_CONTIG_LENGTHS", _NeverIterated(REFERENCE_CONTIG_LENGTHS))
    contigs = [*_unplaced(5000), ("chr1", GRCH38_CHR1 + 500)]
    assert detect_reference_from_contigs(contigs) == ("GRCh38", 1)


def test_exact_and_fuzzy_votes():
    assert detect_reference_from_contigs(
        [("chr1", GRCH38_CHR1), ("2", REFERENCE_CONTIG_LENGTHS["GRCh38"]["chr2"])]
    ) == (
        "GRCh38",
        2,
    )
    # Within tolerance votes; beyond it does not.
    assert detect_reference_from_contigs([("chr1", CHM13_CHR1 - 999)]) == ("CHM13", 1)
    assert detect_reference_from_contigs([("chr1", CHM13_CHR1 - 1001)]) == (None, 0)
    # A name the table does not hold, or a pair with no length, votes for nothing.
    assert detect_reference_from_contigs([*_unplaced(3), ("chr1", None)]) == (None, 0)


def test_a_tie_between_assemblies_is_ambiguous():
    assert detect_reference_from_contigs(
        [("chr1", GRCH38_CHR1), ("chr2", REFERENCE_CONTIG_LENGTHS["GRCh37"]["chr2"])]
    ) == (
        None,
        0,
    )


class TestLineEndings:
    """A CRLF header counts every contig, as the regex path this replaced did (#488).

    The shared parser used to split on `\\n` alone, so a `\\r` stayed on each line
    and the `>`-anchored line pattern (VCF) or the digit check on `LN` (SAM) rejected
    every contig but the last, which `.strip()` had cleaned."""

    def test_vcf(self):
        from meta_disco.header_classifier import classify_from_vcf_header

        header = f"##contig=<ID=chr1,length={GRCH38_CHR1}>\r\n##contig=<ID=chr2,length={REFERENCE_CONTIG_LENGTHS['GRCh38']['chr2']}>\r\n"
        result = classify_from_vcf_header(header)
        assert result["reference_assembly"]["value"] == "GRCh38"
        assert "2 matching contig lengths" in result["reference_assembly"]["evidence"][-1]["reason"]

    def test_sam(self):
        from meta_disco.header_classifier import classify_from_header

        header = f"@SQ\tSN:chr1\tLN:{GRCH38_CHR1}\r\n@SQ\tSN:chr2\tLN:{REFERENCE_CONTIG_LENGTHS['GRCh38']['chr2']}\r\n"
        result = classify_from_header(header)
        assert result["reference_assembly"]["value"] == "GRCh38"
        assert "2 matching contig lengths" in result["reference_assembly"]["evidence"][-1]["reason"]
