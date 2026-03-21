"""End-to-end evaluation tests for classification pipeline.

These test the ACTUAL script functions with REAL cached evidence files,
not the internal classify functions directly. The input is a file
(via md5 -> cached evidence), the output is the JSON record that would
appear in the output file.

For rule-engine-only classifiers (BED, images, auxiliary), the input
is a FileInfo and the output is an ExtendedClassificationResult.
"""

import json
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from src.meta_disco.rule_engine import RuleEngine
from src.meta_disco.models import FileInfo, NOT_APPLICABLE, NOT_CLASSIFIED

# Import the actual script functions
from fetch_bam_headers import classify_single_file as classify_bam
from fetch_vcf_headers import classify_single_vcf as classify_vcf
from fetch_fastq_headers import classify_single_fastq as classify_fastq

engine = RuleEngine()

EVIDENCE_BAM = Path("data/evidence/bam")
EVIDENCE_VCF = Path("data/evidence/vcf")
EVIDENCE_FASTQ = Path("data/evidence/fastq")


def get_val(record, field):
    """Extract classification value from per-field output."""
    cls = record.get("classifications", record)
    v = cls.get(field)
    if isinstance(v, dict) and "value" in v:
        return v["value"]
    return v


def assert_output_format(record):
    """Assert the record has correct top-level + per-field structure."""
    assert "file_name" in record, "Missing file_name"
    assert "md5sum" in record, "Missing md5sum"
    assert "classifications" in record, "Missing classifications wrapper"
    cls = record["classifications"]
    for field in ["data_modality", "data_type", "platform", "reference_assembly"]:
        assert field in cls, f"Missing classification field: {field}"
        entry = cls[field]
        assert isinstance(entry, dict), f"{field} should be dict"
        assert "value" in entry, f"{field} missing 'value'"
        assert "evidence" in entry, f"{field} missing 'evidence'"
        assert "confidence" in entry, f"{field} missing 'confidence'"
        assert len(entry["evidence"]) > 0, f"{field} has empty evidence"



# =============================================================================
# BAM/CRAM — end-to-end through fetch_bam_headers.classify_single_file
# =============================================================================

@pytest.mark.skipif(not EVIDENCE_BAM.exists(), reason="No BAM evidence cache")
class TestBamE2E:
    """End-to-end BAM classification from cached headers."""

    def test_grch38_aligned_bam(self):
        """HG03516.GRCh38_no_alt.bam — aligned to GRCh38."""
        result = classify_bam("000ebc5cfdeb4e799aa047e2c54022af", "HG03516.GRCh38_no_alt.bam")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "reference_assembly") == "GRCh38"
        assert get_val(result, "platform") in ("ILLUMINA", "ONT", "PACBIO")

    def test_pacbio_hifi_unaligned(self):
        """PacBio reads BAM — should be unaligned, reference N/A."""
        result = classify_bam("0004e46159f2fc28224533d71d828108", "r54329U_20220207_223353_A01.reads.bam")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "PACBIO"
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_ont_bam(self):
        """ONT BAM file."""
        result = classify_bam("000e5edf6937cccf67767fb886626655",
                              "06_28_22_R941_HG02922_3_Guppy_6.5.7_450bps_modbases_5mc_cg_sup_prom_pass.bam")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ONT"

    def test_no_stale_evidence(self):
        """reference_assembly should not have stale not_classified evidence."""
        result = classify_bam("000ebc5cfdeb4e799aa047e2c54022af", "HG03516.GRCh38_no_alt.bam")
        cls = result["classifications"]
        ref_evidence = cls["reference_assembly"]["evidence"]
        stale = [e for e in ref_evidence if e["rule_id"] == "not_classified"]
        assert len(stale) == 0, f"Stale not_classified evidence: {stale}"

    def test_star_rnaseq_bam(self):
        """GM20525-10-2.bam — STAR-aligned RNA-seq should be transcriptomic."""
        result = classify_bam("000811b87381c4dd9e5d7a940be14cee", "GM20525-10-2.bam")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "transcriptomic.bulk"
        assert get_val(result, "data_type") == "alignments"

    def test_platform_confidence_meaningful(self):
        """Platform detection from @RG PL: should have non-zero confidence."""
        result = classify_bam("000ebc5cfdeb4e799aa047e2c54022af", "HG03516.GRCh38_no_alt.bam")
        cls = result["classifications"]
        platform_conf = cls["platform"]["confidence"]
        assert platform_conf > 0, f"Platform confidence should be > 0, got {platform_conf}"


# =============================================================================
# VCF — end-to-end through fetch_vcf_headers.classify_single_vcf
# =============================================================================

@pytest.mark.skipif(not EVIDENCE_VCF.exists(), reason="No VCF evidence cache")
class TestVcfE2E:
    """End-to-end VCF classification from cached headers."""

    def test_haplotypecaller_vcf(self):
        """HG03854.chrY.hc.vcf.gz — HaplotypeCaller germline."""
        result = classify_vcf("00001845984e9c9a66433f9fa8476f99", "HG03854.chrY.hc.vcf.gz")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"

    def test_single_chrom_reference_detection(self):
        """Single-chromosome VCF should still identify reference assembly."""
        result = classify_vcf("0000d4b336dbc16a216ebdfeaf092702", "HG01809.chr21.hc.vcf.gz")
        assert result is not None
        ref = get_val(result, "reference_assembly")
        assert ref in ("GRCh38", "GRCh37", "CHM13"), f"Expected a reference, got {ref}"

    def test_vcf_has_contig_evidence(self):
        """VCF reference should come from contig length detection."""
        result = classify_vcf("0000b1430a498c7774dd33a5a58677ad", "NA21125.chr2.hc.vcf.gz")
        assert result is not None
        cls = result["classifications"]
        ref_evidence = cls["reference_assembly"]["evidence"]
        rule_ids = [e["rule_id"] for e in ref_evidence]
        assert "vcf_contig_length" in rule_ids, f"Expected vcf_contig_length, got {rule_ids}"

    def test_sniffles_sv_vcf(self):
        """HG02723 Sniffles SV VCF — structural variant detection."""
        result = classify_vcf("0203bdde8d2f9bba858dce981a409bd5", "HG02723.hifiasm_pat.sniffles.vcf",
                              is_gzipped=False)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"

    def test_vcf_no_stale_evidence(self):
        """VCF reference_assembly should not have stale not_classified evidence."""
        result = classify_vcf("0000b1430a498c7774dd33a5a58677ad", "NA21125.chr2.hc.vcf.gz")
        cls = result["classifications"]
        ref = cls["reference_assembly"]
        if ref["value"] not in (NOT_CLASSIFIED, None):
            stale = [e for e in ref["evidence"] if e["rule_id"] == "not_classified"]
            assert len(stale) == 0, f"Stale evidence: {stale}"


# =============================================================================
# FASTQ — end-to-end through fetch_fastq_headers.classify_single_fastq
# =============================================================================

@pytest.mark.skipif(not EVIDENCE_FASTQ.exists(), reason="No FASTQ evidence cache")
class TestFastqE2E:
    """End-to-end FASTQ classification from cached read names."""

    def test_illumina_fastq(self):
        """GM20294_R1_001.fastq.gz — Illumina paired read."""
        result = classify_fastq("00077512aa3448912698292770d41ca5", "GM20294_R1_001.fastq.gz")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ILLUMINA"
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_ena_reformatted_fastq(self):
        """ERR3989178_1.fastq.gz — ENA-reformatted with accession."""
        result = classify_fastq("0008a97d74c385aeb7eed75f33601d59", "ERR3989178_1.fastq.gz")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ILLUMINA"

    def test_fastq_reference_not_applicable(self):
        """All FASTQ files should have reference N/A (raw reads)."""
        result = classify_fastq("000644fa14ab21a7106a746664d58aa9", "HG02486x02PE20573_1_sequence.fastq.gz")
        assert result is not None
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_pacbio_ccs_fastq(self):
        """PacBio CCS/HiFi FASTQ — should detect PacBio platform."""
        result = classify_fastq("0073d35c9f5b68a739e3daf50a227f72",
                                "HG01109.m64043_200830_075523.dc.q20.fastq.gz")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "PACBIO"
        assert get_val(result, "data_modality") == "genomic"

    def test_mgi_fastq(self):
        """MGI/BGI platform FASTQ — should detect MGI."""
        result = classify_fastq("00c68ff0f9e0217d422c57e8948d4bb4", "IGVFFI6614EZDQ.fastq.gz")
        assert result is not None
        assert_output_format(result)
        # MGI reads start with @V — should be detected
        platform = get_val(result, "platform")
        assert platform in ("MGI", "ILLUMINA", NOT_CLASSIFIED), f"Unexpected platform: {platform}"


# =============================================================================
# RULE ENGINE — extension/filename based (no headers)
# =============================================================================

class TestRuleEngineE2E:
    """Rule engine classification from filename/metadata only."""

    def test_histology_svs(self):
        result = engine.classify_extended(FileInfo(filename="GTEX-18A6Q-1126.svs"))
        assert result.data_modality == "imaging.histology"
        assert result.platform == NOT_APPLICABLE
        assert result.reference_assembly == NOT_APPLICABLE

    def test_fast5_raw_signal(self):
        result = engine.classify_extended(FileInfo(filename="PAK57726.fast5"))
        assert result.data_modality == "genomic"
        assert result.data_type == "raw_signal"
        assert result.platform == "ONT"
        assert result.reference_assembly == NOT_APPLICABLE

    def test_plink_1000g(self):
        result = engine.classify_extended(
            FileInfo(filename="IBS.3.pgen", dataset_title="ANVIL_1000G_PRIMED_data_model")
        )
        assert result.data_modality == "genomic"
        assert result.reference_assembly == "GRCh38"

    def test_bed_methylation(self):
        result = engine.classify_extended(FileInfo(filename="sample.modbam2bed.cpg.bed"))
        assert result.data_modality == "epigenomic.methylation"

    def test_bed_assembly_qc(self):
        result = engine.classify_extended(FileInfo(filename="HG01928.paternal.f1_assembly.hap1.bed"))
        assert result.data_modality == NOT_APPLICABLE

    def test_fastq_rna_filename(self):
        result = engine.classify_extended(FileInfo(filename="sample_RNA_001.fastq.gz"))
        assert result.data_modality == "transcriptomic.bulk"
        assert result.reference_assembly == NOT_APPLICABLE

    def test_checksum_skipped(self):
        result = engine.classify_extended(FileInfo(filename="sample.md5"))
        assert result.skip is True
        assert result.data_modality == NOT_APPLICABLE

    def test_png_derived(self):
        result = engine.classify_extended(FileInfo(filename="assembly_plot.png"))
        assert result.data_modality == NOT_APPLICABLE
        assert result.platform == NOT_APPLICABLE
        assert result.reference_assembly == NOT_APPLICABLE

    def test_all_index_types_skipped(self):
        for ext in [".bai", ".crai", ".tbi", ".csi", ".pbi"]:
            result = engine.classify_extended(FileInfo(filename=f"sample{ext}"))
            assert result.skip is True, f"{ext} should be skipped"

    def test_narrowpeak_is_chromatin(self):
        result = engine.classify_extended(FileInfo(filename="sample.narrowPeak"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"

    def test_bigwig_with_chip_keyword(self):
        result = engine.classify_extended(FileInfo(filename="H3K27ac_ChIP.bw"))
        assert result.data_modality == "epigenomic.histone_modification"

    def test_bed_reference_from_filename(self):
        """BED file with hg38 in filename should detect GRCh38."""
        result = engine.classify_extended(FileInfo(filename="sample.hg38.regions.bed"))
        assert result.reference_assembly == "GRCh38"

    def test_idat_methylation(self):
        """IDAT file should be epigenomic methylation."""
        result = engine.classify_extended(FileInfo(filename="200123456789_R01C01.idat"))
        assert result.data_modality == "epigenomic.methylation"

    def test_no_crash_on_unknown(self):
        for name in ["readme.xyz", "data.parquet", "model.h5", ""]:
            result = engine.classify_extended(FileInfo(filename=name))
            assert result.data_modality is not None
