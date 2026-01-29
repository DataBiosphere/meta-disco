"""Tests for BED file classification patterns using RuleEngine."""

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.rule_engine import RuleEngine
from src.meta_disco.models import FileInfo


# Create a shared engine instance
engine = RuleEngine()


def classify_bed(filename: str, dataset_title: str = "") -> dict:
    """Classify a BED file and return the result as a dict."""
    file_info = FileInfo(
        filename=filename,
        dataset_title=dataset_title,
    )
    result = engine.classify_extended(file_info)
    return {
        "data_modality": result.data_modality,
        "data_type": result.data_type,
        "assay_type": result.assay_type,
        "reference_assembly": result.reference_assembly,
        "confidence": result.confidence,
        "rules_matched": result.rules_matched,
    }


def get_matched_rule_id(filename: str) -> str | None:
    """Get the first matching rule ID for a filename."""
    result = classify_bed(filename)
    # Return the first BED-specific rule (not fallback or extension rules)
    for rule_id in result["rules_matched"]:
        if rule_id.startswith("bed_"):
            return rule_id
    return None


class TestAssemblyQCPattern:
    """Test assembly QC pattern matching - regression tests for maternal bug fix."""

    def test_maternal_haplotype_matches(self):
        """Maternal haplotype files should match assembly_qc rule."""
        filename = "HG01928.maternal.f1_assembly_v2_genbank.HSat2and3_Regions.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"
        result = classify_bed(filename)
        assert result["data_modality"] is None  # N/A for derived QC

    def test_paternal_haplotype_matches(self):
        """Paternal haplotype files should match assembly_qc rule."""
        filename = "HG01928.paternal.f1_assembly_v2_genbank.HSat2and3_Regions.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"

    def test_hap1_matches(self):
        """Hap1 files should match assembly_qc rule."""
        filename = "sample.hap1.regions.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"

    def test_hap2_matches(self):
        """Hap2 files should match assembly_qc rule."""
        filename = "sample.hap2.regions.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"

    def test_dip_bed_matches(self):
        """Diploid BED files should match assembly_qc rule."""
        filename = "HG002.dip.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"

    def test_switch_error_matches(self):
        """Switch error files should match assembly_qc rule."""
        filename = "sample.switch.errors.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"

    def test_flagger_matches(self):
        """Flagger output files should match assembly_qc rule."""
        filename = "HG002_flagger_final.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"

    def test_lowq_matches(self):
        """Low quality region files should match assembly_qc rule."""
        filename = "sample.lowQ.regions.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"

    def test_unreliable_matches(self):
        """Unreliable region files should match assembly_qc rule."""
        filename = "sample_unreliable_regions.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"

    def test_issues_bed_matches(self):
        """Issues BED files should match assembly_qc rule."""
        filename = "sample_issues.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"

    def test_genbank_matches(self):
        """Genbank annotation files should match assembly_qc rule."""
        filename = "HG01928.paternal.f1_assembly_v2_genbank.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_assembly_qc"


class TestMethylationPattern:
    """Test methylation pattern matching."""

    def test_modbam2bed_matches(self):
        """modbam2bed output should match methylation rule."""
        filename = "sample.modbam2bed.cpg.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_methylation"
        result = classify_bed(filename)
        assert result["data_modality"] == "epigenomic.methylation"

    def test_cpg_matches(self):
        """CpG files should match methylation rule."""
        filename = "sample_cpg_islands.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_methylation"

    def test_bisulfite_matches(self):
        """Bisulfite files should match methylation rule."""
        filename = "sample_bisulfite_regions.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_methylation"


class TestExpressionPattern:
    """Test expression/transcriptomic pattern matching."""

    def test_tpm_matches(self):
        """TPM files should match expression rule."""
        filename = "genes_TPM.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_expression"
        result = classify_bed(filename)
        assert result["data_modality"] == "transcriptomic.bulk"

    def test_leafcutter_matches(self):
        """Leafcutter files should match expression rule."""
        filename = "sample_leafcutter_introns.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_expression"

    def test_tss_matches(self):
        """TSS files should match expression rule."""
        filename = "sample.TSS.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_expression"


class TestPeakPattern:
    """Test peak/chromatin accessibility pattern matching."""

    def test_narrowpeak_matches(self):
        """narrowPeak files should match peaks rule."""
        filename = "sample.narrowPeak.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_peaks_generic"
        result = classify_bed(filename)
        assert result["data_modality"] == "epigenomic.chromatin_accessibility"

    def test_broadpeak_matches(self):
        """broadPeak files should match peaks rule."""
        filename = "sample.broadPeak.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_peaks_generic"

    def test_summit_matches(self):
        """Summit files should match peaks rule."""
        filename = "sample_summit.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_peaks_generic"


class TestRegionsPattern:
    """Test regions pattern matching."""

    def test_regions_bed_matches(self):
        """Regions BED files should match regions rule."""
        filename = "HG04191.regions.bed.gz"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_regions"
        result = classify_bed(filename)
        assert result["data_modality"] == "genomic"


class TestReferencePatterns:
    """Test reference assembly pattern matching."""

    def test_grch38_in_filename(self):
        """GRCh38 in filename should match reference rule."""
        result = classify_bed("sample.GRCh38.bed")
        assert result["reference_assembly"] == "GRCh38"

    def test_hg38_in_filename(self):
        """hg38 in filename should match reference rule."""
        result = classify_bed("sample.hg38.regions.bed")
        assert result["reference_assembly"] == "GRCh38"

    def test_chm13_in_filename(self):
        """CHM13 in filename should match reference rule."""
        result = classify_bed("sample.chm13.bed")
        assert result["reference_assembly"] == "CHM13"

    def test_hg19_in_filename(self):
        """hg19 in filename should match reference rule."""
        result = classify_bed("sample.hg19.bed")
        assert result["reference_assembly"] == "GRCh37"


class TestRulePrecedence:
    """Test that rule precedence works correctly."""

    def test_methylation_before_regions(self):
        """Methylation pattern should match before regions pattern."""
        # This file has both .cpg. and .regions.bed
        filename = "sample.cpg.regions.bed"
        rule_id = get_matched_rule_id(filename)
        assert rule_id == "bed_methylation"  # Should match first

    def test_assembly_qc_before_regions(self):
        """Assembly QC should match before regions rule."""
        # This could match regions but should match assembly_qc first
        filename = "sample.hap1.callable.regions.bed"
        rule_id = get_matched_rule_id(filename)
        # hap1 should trigger assembly_qc since it comes before regions in the list
        assert rule_id == "bed_assembly_qc"

    def test_no_specific_pattern_gets_default(self):
        """Files that don't match any specific pattern should get default classification."""
        result = classify_bed("generic_file.bed")
        # Should still have a modality from extension-based classification
        assert result["data_modality"] is not None or result["data_type"] is not None


class TestPatternEdgeCases:
    """Test edge cases and potential false positives."""

    def test_maternal_not_in_word(self):
        """maternal as part of another word should not match assembly_qc."""
        # This is actually correct - we want .maternal. with dots or word boundary
        filename = "sample_maternally_derived.bed"
        rule_id = get_matched_rule_id(filename)
        # Should NOT match assembly_qc because pattern requires .maternal. with dots
        assert rule_id != "bed_assembly_qc"

    def test_peak_in_filename_matches(self):
        """'peak' anywhere in filename should match."""
        filename = "chipseq_peak_calls.bed"
        rule_id = get_matched_rule_id(filename)
        # Matches ChIP-seq specific rule due to "chipseq" in filename
        assert rule_id == "bed_chip_peaks"
