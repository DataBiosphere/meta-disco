"""Tests for BED file classification patterns."""

import re
import sys
from pathlib import Path

import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from classify_bed_files import MODALITY_RULES, FILENAME_REFERENCE_RULES, DATASET_REFERENCE_RULES


def match_modality_rule(filename: str) -> dict | None:
    """Find the first matching modality rule for a filename."""
    for rule in MODALITY_RULES:
        if re.search(rule["pattern"], filename, re.IGNORECASE):
            return rule
    return None


def match_reference_rule(filename: str) -> dict | None:
    """Find the first matching reference rule for a filename."""
    for rule in FILENAME_REFERENCE_RULES:
        if re.search(rule["pattern"], filename, re.IGNORECASE):
            return rule
    return None


class TestAssemblyQCPattern:
    """Test assembly QC pattern matching - regression tests for maternal bug fix."""

    def test_maternal_haplotype_matches(self):
        """Maternal haplotype files should match assembly_qc rule."""
        filename = "HG01928.maternal.f1_assembly_v2_genbank.HSat2and3_Regions.bed"
        rule = match_modality_rule(filename)
        assert rule is not None, f"Expected {filename} to match a rule"
        assert rule["id"] == "bed_assembly_qc"
        assert rule["data_modality"] is None  # N/A for derived QC

    def test_paternal_haplotype_matches(self):
        """Paternal haplotype files should match assembly_qc rule."""
        filename = "HG01928.paternal.f1_assembly_v2_genbank.HSat2and3_Regions.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"

    def test_hap1_matches(self):
        """Hap1 files should match assembly_qc rule."""
        filename = "sample.hap1.regions.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"

    def test_hap2_matches(self):
        """Hap2 files should match assembly_qc rule."""
        filename = "sample.hap2.regions.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"

    def test_dip_bed_matches(self):
        """Diploid BED files should match assembly_qc rule."""
        filename = "HG002.dip.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"

    def test_switch_error_matches(self):
        """Switch error files should match assembly_qc rule."""
        filename = "sample.switch.errors.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"

    def test_flagger_matches(self):
        """Flagger output files should match assembly_qc rule."""
        filename = "HG002_flagger_final.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"

    def test_lowq_matches(self):
        """Low quality region files should match assembly_qc rule."""
        filename = "sample.lowQ.regions.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"

    def test_unreliable_matches(self):
        """Unreliable region files should match assembly_qc rule."""
        filename = "sample_unreliable_regions.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"

    def test_issues_bed_matches(self):
        """Issues BED files should match assembly_qc rule."""
        filename = "sample_issues.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"

    def test_genbank_matches(self):
        """Genbank annotation files should match assembly_qc rule."""
        filename = "HG01928.paternal.f1_assembly_v2_genbank.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"


class TestMethylationPattern:
    """Test methylation pattern matching."""

    def test_modbam2bed_matches(self):
        """modbam2bed output should match methylation rule."""
        filename = "sample.modbam2bed.cpg.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_methylation"
        assert rule["data_modality"] == "epigenomic.methylation"

    def test_cpg_matches(self):
        """CpG files should match methylation rule."""
        filename = "sample_cpg_islands.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_methylation"

    def test_bisulfite_matches(self):
        """Bisulfite files should match methylation rule."""
        filename = "sample_bisulfite_regions.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_methylation"


class TestExpressionPattern:
    """Test expression/transcriptomic pattern matching."""

    def test_tpm_matches(self):
        """TPM files should match expression rule."""
        filename = "genes_TPM.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_expression"
        assert rule["data_modality"] == "transcriptomic"

    def test_leafcutter_matches(self):
        """Leafcutter files should match expression rule."""
        filename = "sample_leafcutter_introns.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_expression"

    def test_tss_matches(self):
        """TSS files should match expression rule."""
        filename = "sample.TSS.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_expression"


class TestPeakPattern:
    """Test peak/chromatin accessibility pattern matching."""

    def test_narrowpeak_matches(self):
        """narrowPeak files should match peaks rule."""
        filename = "sample.narrowPeak.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_peaks"
        assert rule["data_modality"] == "epigenomic.chromatin_accessibility"

    def test_broadpeak_matches(self):
        """broadPeak files should match peaks rule."""
        filename = "sample.broadPeak.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_peaks"

    def test_summit_matches(self):
        """Summit files should match peaks rule."""
        filename = "sample_summit.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_peaks"


class TestRegionsPattern:
    """Test regions pattern matching."""

    def test_regions_bed_matches(self):
        """Regions BED files should match regions rule."""
        filename = "HG04191.regions.bed.gz"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_regions"
        assert rule["data_modality"] == "genomic"


class TestReferencePatterns:
    """Test reference assembly pattern matching."""

    def test_grch38_in_filename(self):
        """GRCh38 in filename should match reference rule."""
        rule = match_reference_rule("sample.GRCh38.bed")
        assert rule is not None
        assert rule["reference_assembly"] == "GRCh38"

    def test_hg38_in_filename(self):
        """hg38 in filename should match reference rule."""
        rule = match_reference_rule("sample.hg38.regions.bed")
        assert rule is not None
        assert rule["reference_assembly"] == "GRCh38"

    def test_chm13_in_filename(self):
        """CHM13 in filename should match reference rule."""
        rule = match_reference_rule("sample.chm13.bed")
        assert rule is not None
        assert rule["reference_assembly"] == "CHM13"

    def test_hg19_in_filename(self):
        """hg19 in filename should match reference rule."""
        rule = match_reference_rule("sample.hg19.bed")
        assert rule is not None
        assert rule["reference_assembly"] == "GRCh37"


class TestRulePrecedence:
    """Test that rule precedence works correctly."""

    def test_methylation_before_regions(self):
        """Methylation pattern should match before regions pattern."""
        # This file has both .cpg. and .regions.bed
        filename = "sample.cpg.regions.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        assert rule["id"] == "bed_methylation"  # Should match first

    def test_assembly_qc_before_regions(self):
        """Assembly QC should match before regions rule."""
        # This could match regions but should match assembly_qc first
        filename = "sample.hap1.callable.regions.bed"
        rule = match_modality_rule(filename)
        # hap1 should trigger assembly_qc since it comes before regions in the list
        assert rule is not None
        assert rule["id"] == "bed_assembly_qc"

    def test_no_match_gets_none(self):
        """Files that don't match any pattern should return None."""
        rule = match_modality_rule("generic_file.bed")
        assert rule is None  # No match, will use default in main script


class TestPatternEdgeCases:
    """Test edge cases and potential false positives."""

    def test_maternal_not_in_word(self):
        """maternal as part of another word should still match."""
        # This is actually correct - we want .maternal. with dots
        filename = "sample_maternally_derived.bed"
        rule = match_modality_rule(filename)
        # Should NOT match because pattern requires .maternal. with dots
        assert rule is None or rule["id"] != "bed_assembly_qc"

    def test_peak_in_filename_matches(self):
        """'peak' anywhere in filename should match."""
        filename = "chipseq_peak_calls.bed"
        rule = match_modality_rule(filename)
        assert rule is not None
        # Matches ChIP-seq specific rule due to "chipseq" in filename
        assert rule["id"] == "bed_chip_peaks"
