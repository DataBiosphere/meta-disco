"""System-level evaluation tests for classification functions.

These test the full classification pipeline end-to-end with realistic inputs,
verifying that the output format is correct and values make sense.
Unlike unit tests, these treat the classifier as a black box.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.header_classifier import (
    classify_from_header,
    classify_from_vcf_header,
    classify_from_fastq_header,
)
from src.meta_disco.rule_engine import RuleEngine
from src.meta_disco.models import FileInfo, NOT_APPLICABLE, NOT_CLASSIFIED


# Shared engine for rule-only classifiers
engine = RuleEngine()


def assert_valid_classification(result, expected_fields):
    """Assert that a classification result has the expected per-field structure."""
    for field, expected_value in expected_fields.items():
        assert field in result, f"Missing field: {field}"
        entry = result[field]
        if isinstance(entry, dict) and "value" in entry:
            actual = entry["value"]
            assert actual == expected_value, (
                f"{field}: expected {expected_value!r}, got {actual!r}"
            )
            # Every field should have evidence
            assert "evidence" in entry, f"{field} missing evidence"
            assert len(entry["evidence"]) > 0, f"{field} has empty evidence"
            # Every evidence entry should have rule_id and reason
            for e in entry["evidence"]:
                assert "rule_id" in e, f"{field} evidence missing rule_id"
                assert "reason" in e, f"{field} evidence missing reason"
        else:
            # Flat value (non-classification field like is_aligned)
            assert entry == expected_value, (
                f"{field}: expected {expected_value!r}, got {entry!r}"
            )


# =============================================================================
# BAM/CRAM CLASSIFICATION
# =============================================================================

class TestBamEval:
    """End-to-end BAM/CRAM classification tests."""

    def test_illumina_wgs_grch38(self):
        """Standard Illumina WGS CRAM aligned to GRCh38."""
        header = "\n".join([
            "@HD\tVN:1.6\tSO:coordinate",
            "@SQ\tSN:chr1\tLN:248956422",
            "@SQ\tSN:chr2\tLN:242193529",
            "@SQ\tSN:chr3\tLN:198295559",
            "@SQ\tSN:chr10\tLN:133797422",
            "@SQ\tSN:chr22\tLN:50818468",
            "@RG\tID:sample1\tPL:ILLUMINA\tSM:NA12878",
            "@PG\tID:bwa\tPN:bwa\tVN:0.7.17",
        ])
        result = classify_from_header(header)
        assert_valid_classification(result, {
            "data_modality": "genomic",
            "reference_assembly": "GRCh38",
            "platform": "ILLUMINA",
            "data_type": "alignments",
            "is_aligned": True,
        })

    def test_pacbio_hifi_chm13(self):
        """PacBio HiFi BAM aligned to CHM13."""
        header = "\n".join([
            "@HD\tVN:1.6\tSO:coordinate",
            "@SQ\tSN:chr1\tLN:248387497",
            "@SQ\tSN:chr2\tLN:242696747",
            "@SQ\tSN:chr3\tLN:201106605",
            "@RG\tID:movie1\tPL:PACBIO\tDS:READTYPE=CCS",
            "@PG\tID:pbmm2\tPN:pbmm2\tVN:1.9.0",
        ])
        result = classify_from_header(header)
        assert_valid_classification(result, {
            "data_modality": "genomic",
            "reference_assembly": "CHM13",
            "platform": "PACBIO",
            "is_aligned": True,
        })

    def test_star_rnaseq_grch38(self):
        """STAR-aligned RNA-seq BAM."""
        header = "\n".join([
            "@HD\tVN:1.6\tSO:coordinate",
            "@SQ\tSN:chr1\tLN:248956422",
            "@SQ\tSN:chr2\tLN:242193529",
            "@PG\tID:STAR\tPN:STAR\tVN:2.7.10a",
        ])
        result = classify_from_header(header)
        assert_valid_classification(result, {
            "data_modality": "transcriptomic.bulk",
            "reference_assembly": "GRCh38",
            "data_type": "alignments",
        })

    def test_unaligned_pacbio(self):
        """Unaligned PacBio HiFi BAM (no @SQ lines)."""
        header = "\n".join([
            "@HD\tVN:1.6",
            "@RG\tID:movie1\tPL:PACBIO\tDS:READTYPE=CCS",
            "@PG\tID:ccs\tPN:ccs\tVN:6.4.0",
        ])
        result = classify_from_header(header)
        assert_valid_classification(result, {
            "data_modality": "genomic",
            "platform": "PACBIO",
            "reference_assembly": NOT_APPLICABLE,
            "is_aligned": False,
        })

    def test_empty_header(self):
        """Empty header should produce valid structure with low confidence."""
        result = classify_from_header("")
        # Should still have all classification fields
        for field in ["data_modality", "reference_assembly", "platform"]:
            assert field in result

    def test_platform_confidence_not_zero(self):
        """Platform detection from @RG PL: should have meaningful confidence."""
        header = "\n".join([
            "@HD\tVN:1.6\tSO:coordinate",
            "@SQ\tSN:chr1\tLN:248956422",
            "@RG\tID:sample1\tPL:ILLUMINA\tSM:sample1",
        ])
        result = classify_from_header(header)
        platform = result["platform"]
        assert platform["value"] == "ILLUMINA"
        # We're certain it's Illumina — confidence should reflect that
        assert platform["confidence"] > 0, (
            f"Platform ILLUMINA detected but confidence is {platform['confidence']} — "
            f"should be > 0 since PL:ILLUMINA is a definitive signal"
        )

    def test_no_stale_not_classified_evidence(self):
        """When a field gets a real value, it shouldn't also have a stale
        not_classified evidence entry from finalization."""
        header = "\n".join([
            "@HD\tVN:1.6\tSO:coordinate",
            "@SQ\tSN:chr1\tLN:248956422",
            "@SQ\tSN:chr2\tLN:242193529",
            "@RG\tID:sample1\tPL:ILLUMINA",
            "@PG\tID:bwa\tPN:bwa",
        ])
        result = classify_from_header(header)
        ref = result["reference_assembly"]
        assert ref["value"] == "GRCh38"
        # Should NOT have a not_classified evidence entry alongside the real one
        stale = [e for e in ref["evidence"] if e["rule_id"] == "not_classified"]
        assert len(stale) == 0, (
            f"reference_assembly has value GRCh38 but also has stale "
            f"not_classified evidence: {stale}"
        )

    def test_assay_type_inferred_for_illumina_wgs(self):
        """Illumina + BWA + large CRAM should get assay_type WGS."""
        header = "\n".join([
            "@HD\tVN:1.6\tSO:coordinate",
            "@SQ\tSN:chr1\tLN:248956422",
            "@SQ\tSN:chr2\tLN:242193529",
            "@RG\tID:sample1\tPL:ILLUMINA",
            "@PG\tID:bwa\tPN:bwa",
        ])
        result = classify_from_header(header, file_size=50_000_000_000)  # 50GB
        assay = result["assay_type"]
        assert assay["value"] != NOT_CLASSIFIED, (
            f"assay_type should be inferred for Illumina/BWA/50GB but got "
            f"not_classified. Evidence: {assay['evidence']}"
        )


# =============================================================================
# VCF CLASSIFICATION
# =============================================================================

class TestVcfEval:
    """End-to-end VCF classification tests."""

    def test_haplotypecaller_chm13(self):
        """GATK HaplotypeCaller VCF with CHM13 contigs."""
        header = "\n".join([
            "##fileformat=VCFv4.2",
            "##source=HaplotypeCaller",
            "##contig=<ID=chr1,length=248387497>",
            "##contig=<ID=chr2,length=242696747>",
            "##contig=<ID=chr3,length=201106605>",
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        ])
        result = classify_from_vcf_header(header)
        assert_valid_classification(result, {
            "data_modality": "genomic",
            "data_type": "variants.germline",
            "reference_assembly": "CHM13",
        })

    def test_mutect2_somatic(self):
        """Mutect2 somatic VCF."""
        header = "\n".join([
            "##fileformat=VCFv4.2",
            "##source=Mutect2",
            "##contig=<ID=chr1,length=248956422>",
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        ])
        result = classify_from_vcf_header(header)
        assert_valid_classification(result, {
            "data_modality": "genomic",
            "data_type": "variants.somatic",
            "reference_assembly": "GRCh38",
        })

    def test_structural_variants(self):
        """SV VCF with SVTYPE INFO field."""
        header = "\n".join([
            "##fileformat=VCFv4.2",
            "##INFO=<ID=SVTYPE,Number=1,Type=String,Description=\"SV type\">",
            "##contig=<ID=chr1,length=248956422>",
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        ])
        result = classify_from_vcf_header(header)
        assert_valid_classification(result, {
            "data_modality": "genomic",
            "data_type": "variants.structural",
            "reference_assembly": "GRCh38",
        })

    def test_grch37_bare_contigs(self):
        """GRCh37 VCF with bare chromosome names (no chr prefix)."""
        header = "\n".join([
            "##fileformat=VCFv4.2",
            "##contig=<ID=1,length=249250621>",
            "##contig=<ID=2,length=243199373>",
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        ])
        result = classify_from_vcf_header(header)
        assert_valid_classification(result, {
            "reference_assembly": "GRCh37",
        })


# =============================================================================
# FASTQ CLASSIFICATION
# =============================================================================

class TestFastqEval:
    """End-to-end FASTQ classification tests."""

    def test_illumina_novaseq(self):
        """Modern Illumina NovaSeq reads."""
        reads = [
            "@A00297:44:HFKH3DSXX:2:1101:1904:1000 1:N:0:ATCACG",
            "@A00297:44:HFKH3DSXX:2:1101:2880:1000 1:N:0:ATCACG",
        ]
        result = classify_from_fastq_header(reads)
        assert_valid_classification(result, {
            "platform": "ILLUMINA",
            "data_modality": "genomic",
            "data_type": "reads",
            "reference_assembly": NOT_APPLICABLE,
        })
        assert result["instrument_model"] == "NovaSeq 6000"

    def test_pacbio_hifi_reads(self):
        """PacBio CCS/HiFi reads."""
        reads = ["@m64011_190830_220126/1/ccs"]
        result = classify_from_fastq_header(reads)
        assert_valid_classification(result, {
            "platform": "PACBIO",
            "data_modality": "genomic",
            "data_type": "reads",
            "reference_assembly": NOT_APPLICABLE,
        })

    def test_ont_reads(self):
        """Oxford Nanopore reads."""
        reads = ["@a1b2c3d4-e5f6-7890-abcd-ef1234567890 runid=abc123"]
        result = classify_from_fastq_header(reads)
        assert_valid_classification(result, {
            "platform": "ONT",
            "data_modality": "genomic",
            "data_type": "reads",
            "reference_assembly": NOT_APPLICABLE,
        })

    def test_ena_reformatted_illumina(self):
        """ENA-reformatted reads with archive accession."""
        reads = ["@ERR3242571.1 A00297:44:HFKH3DSXX:2:1354:30508:28839/1"]
        result = classify_from_fastq_header(reads)
        assert_valid_classification(result, {
            "platform": "ILLUMINA",
            "reference_assembly": NOT_APPLICABLE,
        })
        assert result["archive_accession"] == "ERR3242571"
        assert result["archive_source"] == "ENA"


# =============================================================================
# RULE ENGINE (extension/filename based)
# =============================================================================

class TestRuleEngineEval:
    """End-to-end rule engine classification tests for non-header file types."""

    def test_histology_svs(self):
        """GTEx whole-slide histology image."""
        result = engine.classify_extended(FileInfo(filename="GTEX-18A6Q-1126.svs"))
        assert result.data_modality == "imaging.histology"
        assert result.platform == NOT_APPLICABLE
        assert result.reference_assembly == NOT_APPLICABLE
        assert result.data_type == "images"

    def test_fast5_raw_signal(self):
        """ONT FAST5 raw signal file."""
        result = engine.classify_extended(FileInfo(filename="PAK57726.fast5"))
        assert result.data_modality == "genomic"
        assert result.data_type == "raw_signal"
        assert result.platform == "ONT"
        assert result.reference_assembly == NOT_APPLICABLE

    def test_plink_pgen(self):
        """PLINK2 pgen genotype file."""
        result = engine.classify_extended(
            FileInfo(filename="IBS.3.pgen", dataset_title="ANVIL_1000G_PRIMED_data_model")
        )
        assert result.data_modality == "genomic"
        assert result.reference_assembly == "GRCh38"

    def test_bed_methylation(self):
        """BED file with methylation pattern."""
        result = engine.classify_extended(FileInfo(filename="sample.modbam2bed.cpg.bed"))
        assert result.data_modality == "epigenomic.methylation"

    def test_bed_assembly_qc(self):
        """BED file that's assembly QC (not primary data)."""
        result = engine.classify_extended(
            FileInfo(filename="HG01928.paternal.f1_assembly.hap1.bed")
        )
        assert result.data_modality == NOT_APPLICABLE

    def test_fastq_rna_filename(self):
        """FASTQ with RNA indicator in filename."""
        result = engine.classify_extended(FileInfo(filename="sample_RNA_001.fastq.gz"))
        assert result.data_modality == "transcriptomic.bulk"
        assert result.data_type == "reads"
        assert result.reference_assembly == NOT_APPLICABLE

    def test_checksum_skipped(self):
        """MD5 checksum file should be skipped."""
        result = engine.classify_extended(FileInfo(filename="sample.md5"))
        assert result.skip is True
        assert result.data_modality == NOT_APPLICABLE

    def test_png_derived(self):
        """PNG QC plot — derived artifact."""
        result = engine.classify_extended(FileInfo(filename="assembly_plot.png"))
        assert result.data_modality == NOT_APPLICABLE
        assert result.platform == NOT_APPLICABLE
        assert result.reference_assembly == NOT_APPLICABLE


# =============================================================================
# CORNER CASES
# =============================================================================

class TestCornerCases:
    """Edge cases and tricky inputs that have caused bugs."""

    def test_vcf_single_chromosome_identifies_assembly(self):
        """A VCF with only one chromosome contig should still identify assembly."""
        header = "\n".join([
            "##fileformat=VCFv4.2",
            "##contig=<ID=chr17,length=83257441>",
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        ])
        result = classify_from_vcf_header(header)
        assert_valid_classification(result, {
            "reference_assembly": "GRCh38",
        })

    def test_vcf_contig_with_extra_fields(self):
        """VCF contig line with assembly= between ID= and length=."""
        header = "\n".join([
            "##fileformat=VCFv4.2",
            "##contig=<ID=chr1,assembly=GRCh38,md5=abc,length=248956422>",
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
        ])
        result = classify_from_vcf_header(header)
        assert_valid_classification(result, {
            "reference_assembly": "GRCh38",
        })

    def test_bam_grch37_bare_contig_names(self):
        """GRCh37 BAM uses bare chromosome names (no chr prefix)."""
        header = "\n".join([
            "@HD\tVN:1.6\tSO:coordinate",
            "@SQ\tSN:1\tLN:249250621",
            "@SQ\tSN:2\tLN:243199373",
            "@SQ\tSN:3\tLN:198022430",
        ])
        result = classify_from_header(header)
        assert_valid_classification(result, {
            "reference_assembly": "GRCh37",
        })

    def test_conflicting_platform_and_program(self):
        """Illumina platform with PacBio CCS program — should warn."""
        header = "\n".join([
            "@HD\tVN:1.6",
            "@RG\tID:sample1\tPL:ILLUMINA",
            "@PG\tID:ccs\tPN:ccs\tVN:6.4.0",
        ])
        result = classify_from_header(header)
        assert "consistency" in result
        assert len(result["consistency"]["warnings"]) > 0

    def test_ena_accession_without_dot_suffix(self):
        """ENA accession without .1 suffix should still detect platform."""
        reads = ["@ERR3242571 A00297:44:HFKH3DSXX:2:1354:30508:28839/1"]
        result = classify_from_fastq_header(reads)
        assert_valid_classification(result, {
            "platform": "ILLUMINA",
        })
        assert result["archive_accession"] == "ERR3242571"

    def test_fastq_with_trailing_tokens(self):
        """Illumina read name with extra trailing content."""
        reads = ["@A00297:44:HFKH3DSXX:2:1354:30508:28839 1:N:0:ATCACG extra_stuff"]
        result = classify_from_fastq_header(reads)
        assert_valid_classification(result, {
            "platform": "ILLUMINA",
        })

    def test_hifi_bam_with_size(self):
        """PacBio HiFi BAM with file size should get WGS assay type."""
        header = "\n".join([
            "@HD\tVN:1.6",
            "@RG\tID:movie1\tPL:PACBIO\tDS:READTYPE=CCS",
        ])
        result = classify_from_header(header, file_size=100_000_000_000)
        assert_valid_classification(result, {
            "platform": "PACBIO",
            "data_modality": "genomic",
            "assay_type": "WGS",
        })

    def test_all_index_types_skipped(self):
        """All index types should be skipped."""
        for ext in [".bai", ".crai", ".tbi", ".csi", ".pbi"]:
            result = engine.classify_extended(FileInfo(filename=f"sample{ext}"))
            assert result.skip is True, f"{ext} should be skipped"
            assert result.data_modality == NOT_APPLICABLE

    def test_log_and_checksum_skipped(self):
        """Non-data files should be skipped."""
        for name in ["run.log", "sample.md5"]:
            result = engine.classify_extended(FileInfo(filename=name))
            assert result.skip is True, f"{name} should be skipped"

    def test_narrowpeak_is_chromatin(self):
        """narrowPeak BED files should be chromatin accessibility."""
        result = engine.classify_extended(FileInfo(filename="sample.narrowPeak"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"

    def test_bigwig_with_chip_keyword(self):
        """BigWig with ChIP in filename should be histone modification."""
        result = engine.classify_extended(FileInfo(filename="H3K27ac_ChIP.bw"))
        assert result.data_modality == "epigenomic.histone_modification"

    def test_dataset_context_1000g(self):
        """1000G PRIMED dataset should set GRCh38 reference for PLINK files."""
        result = engine.classify_extended(
            FileInfo(filename="EUR.pgen", dataset_title="ANVIL_1000G_PRIMED_data_model")
        )
        assert result.reference_assembly == "GRCh38"

    def test_no_crash_on_unknown_extension(self):
        """Completely unknown file types shouldn't crash."""
        for name in ["readme.xyz", "data.parquet", "model.h5", ""]:
            result = engine.classify_extended(FileInfo(filename=name))
            assert result.data_modality is not None
