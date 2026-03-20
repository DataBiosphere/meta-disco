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
