"""Tests for BED file classification patterns using RuleEngine."""

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.header_classifier import classify_from_bed_signals
from src.meta_disco.models import NOT_APPLICABLE, NOT_CLASSIFIED, FileInfo
from src.meta_disco.rule_engine import RuleEngine

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
        assert result["data_modality"] == "genomic"

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


def _get_val(result: dict, field: str):
    """Extract classification value from per-field output."""
    v = result.get(field, {})
    return v.get("value") if isinstance(v, dict) else v


class TestBedCoordinateClassification:
    """Test coordinate-based reference detection via classify_from_bed_signals."""

    def test_grch38_coordinates(self):
        """GRCh38 coordinates with chr prefix should detect GRCh38."""
        signals = {
            "chromosomes": ["chr1", "chr2", "chr3"],
            "has_chr_prefix": True,
            # GRCh38 chr1=248956422; use a value close but under
            "max_coordinates": {"chr1": 248956000, "chr2": 242193000},
        }
        result = classify_from_bed_signals(signals, file_name="sample.regions.bed.gz")
        ref = _get_val(result, "reference_assembly")
        assert ref in ("GRCh38", "CHM13"), f"Expected GRCh38 or CHM13, got {ref}"

    def test_no_chr_prefix_grch37(self):
        """No chr prefix on standard chroms -> GRCh37."""
        signals = {
            "chromosomes": ["1", "2", "3"],
            "has_chr_prefix": False,
            "max_coordinates": {"1": 200000000},
        }
        result = classify_from_bed_signals(signals, file_name="sample.bed")
        assert _get_val(result, "reference_assembly") == "GRCh37"

    def test_nonstandard_chroms_not_applicable(self):
        """Non-standard chromosome names -> reference is not_applicable."""
        signals = {
            "chromosomes": ["HG01106#1#JAHAMC010000001.1", "HG01106#1#JAHAMC010000002.1"],
            "has_chr_prefix": False,
            "max_coordinates": {"HG01106#1#JAHAMC010000001.1": 92310948},
        }
        result = classify_from_bed_signals(signals, file_name="sample.bed")
        assert _get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_empty_signals_preserves_filename_classification(self):
        """Empty signals still returns rule engine classification from filename."""
        result = classify_from_bed_signals({}, file_name="sample.modbam2bed.cpg.bed")
        assert _get_val(result, "data_modality") == "epigenomic.methylation"

    def test_empty_signals_no_reference(self):
        """Empty signals should leave reference as not_classified."""
        result = classify_from_bed_signals({}, file_name="sample.bed")
        assert _get_val(result, "reference_assembly") == NOT_CLASSIFIED

    def test_coordinates_exceeding_grch38_rule_it_out(self):
        """Coordinates exceeding GRCh38 chr lengths should rule out GRCh38."""
        # CHM13 chr8=146259331, GRCh38 chr8=145138636, GRCh37 chr8=146364022
        # A coordinate of 145500000 exceeds GRCh38 but not CHM13 or GRCh37
        # chr prefix rules out GRCh37
        signals = {
            "chromosomes": ["chr8"],
            "has_chr_prefix": True,
            "max_coordinates": {"chr8": 145500000},
        }
        result = classify_from_bed_signals(signals, file_name="sample.bed")
        ref = _get_val(result, "reference_assembly")
        assert ref != "GRCh38", f"GRCh38 should be ruled out, got {ref}"

    def test_no_coordinates_no_crash(self):
        """Signals with empty max_coordinates should not crash."""
        signals = {
            "chromosomes": ["chr1"],
            "has_chr_prefix": True,
            "max_coordinates": {},
        }
        result = classify_from_bed_signals(signals, file_name="sample.bed")
        assert _get_val(result, "reference_assembly") == NOT_CLASSIFIED
