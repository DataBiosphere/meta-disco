"""Tests for the rule engine."""

import pytest

from src.meta_disco.models import NOT_APPLICABLE, NOT_CLASSIFIED, ClassificationResult, FileInfo
from src.meta_disco.rule_engine import ExtendedFileInfo, RuleEngine


@pytest.fixture
def engine():
    """Create a rule engine with the unified rules."""
    return RuleEngine()


class TestExtensionExtraction:
    """Test extension extraction logic."""

    def test_simple_bam(self, engine):
        assert engine.rules.extract_extension("sample.bam") == ".bam"

    def test_compound_vcf_gz(self, engine):
        assert engine.rules.extract_extension("file.vcf.gz") == ".vcf.gz"

    def test_compound_fastq_gz(self, engine):
        assert engine.rules.extract_extension("sample.fastq.gz") == ".fastq.gz"

    def test_cram_with_dots(self, engine):
        assert engine.rules.extract_extension("sample.hg38.cram") == ".cram"

    def test_case_insensitive(self, engine):
        assert engine.rules.extract_extension("SAMPLE.BAM") == ".bam"
        assert engine.rules.extract_extension("File.VCF.GZ") == ".vcf.gz"

    def test_no_extension(self, engine):
        assert engine.rules.extract_extension("filename") == ""

    def test_gvcf_gz(self, engine):
        assert engine.rules.extract_extension("sample.g.vcf.gz") == ".g.vcf.gz"


class TestRuleMatching:
    """Test rule matching logic."""

    def test_alignment_rnaseq_filename(self, engine):
        """RNA-seq indicators in filename should set transcriptomic modality."""
        result = engine.classify(FileInfo(filename="sample_RNA_aligned.bam"))
        assert result.data_modality == "transcriptomic.bulk"
        assert result.confidence >= 0.80
        assert "alignment_rnaseq_filename" in result.rules_matched

    def test_alignment_wgs_filename(self, engine):
        """WGS indicators should set genomic modality with WGS assay_type."""
        result = engine.classify(FileInfo(filename="sample_WGS_aligned.bam"))
        assert result.data_modality == "genomic"
        assert result.confidence >= 0.85

    def test_alignment_ref_grch38(self, engine):
        """hg38/GRCh38 in filename should set reference assembly."""
        result = engine.classify(FileInfo(filename="sample.hg38.cram"))
        assert result.reference_assembly == "GRCh38"
        assert result.confidence >= 0.90

    def test_alignment_ref_grch37(self, engine):
        """hg19/GRCh37 in filename should set reference assembly."""
        result = engine.classify(FileInfo(filename="sample.hg19.bam"))
        assert result.reference_assembly == "GRCh37"

    def test_alignment_ref_chm13(self, engine):
        """CHM13/T2T in filename should set reference assembly."""
        result = engine.classify(FileInfo(filename="sample.chm13.cram"))
        assert result.reference_assembly == "CHM13"

    def test_size_heuristic_wgs(self, engine):
        """Large BAM file should suggest WGS."""
        result = engine.classify(
            FileInfo(filename="sample.bam", file_size=60_000_000_000)
        )
        assert result.data_modality == "genomic"
        assert result.confidence >= 0.60
        assert "alignment_size_wgs" in result.rules_matched

    def test_size_heuristic_not_triggered_when_modality_set(self, engine):
        """Size heuristic should not override explicit modality."""
        result = engine.classify(
            FileInfo(filename="sample_RNA_aligned.bam", file_size=60_000_000_000)
        )
        # RNA indicator should take precedence
        assert result.data_modality == "transcriptomic.bulk"

    def test_alignment_needs_header_inspection(self, engine):
        """BAM without indicators should need header inspection."""
        result = engine.classify(FileInfo(filename="sample.bam"))
        assert result.needs_header_inspection is True
        assert result.confidence == 0.0

    def test_star_aligner_indicates_rnaseq(self, engine):
        """STAR aligner output pattern should indicate RNA-seq."""
        result = engine.classify(
            FileInfo(filename="sample.Aligned.sortedByCoord.out.bam")
        )
        assert result.data_modality == "transcriptomic.bulk"
        assert result.confidence >= 0.90


class TestVariantFiles:
    """Test variant file classification."""

    def test_vcf_default_genomic(self, engine):
        """VCF files should default to genomic."""
        result = engine.classify(FileInfo(filename="sample.vcf"))
        assert result.data_modality == "genomic"
        assert result.confidence >= 0.85

    def test_vcf_gz_default_genomic(self, engine):
        """Compressed VCF files should default to genomic."""
        result = engine.classify(FileInfo(filename="sample.vcf.gz"))
        assert result.data_modality == "genomic"

    def test_vcf_with_ref_grch38(self, engine):
        """VCF with reference in filename."""
        result = engine.classify(FileInfo(filename="NA19189.chr2.hg38.vcf.gz"))
        assert result.data_modality == "genomic"
        assert result.reference_assembly == "GRCh38"


class TestSkipFiles:
    """Test files that should be skipped."""

    def test_index_bai(self, engine):
        """BAI index files should be skipped."""
        result = engine.classify(FileInfo(filename="sample.bam.bai"))
        assert result.skip is True
        assert "index_skip" in result.rules_matched

    def test_index_crai(self, engine):
        """CRAI index files should be skipped."""
        result = engine.classify(FileInfo(filename="sample.cram.crai"))
        assert result.skip is True

    def test_checksum_md5(self, engine):
        """MD5 checksum files should be skipped."""
        result = engine.classify(FileInfo(filename="HG02558.final.cram.md5"))
        assert result.skip is True
        assert "checksum_skip" in result.rules_matched

    def test_log_files(self, engine):
        """Log files should be skipped."""
        result = engine.classify(FileInfo(filename="pipeline.log"))
        assert result.skip is True


class TestSpecialFileTypes:
    """Test special file type classifications."""

    def test_plink_genomic(self, engine):
        """PLINK files should be genomic."""
        for ext in [".pgen", ".pvar", ".psam"]:
            result = engine.classify(FileInfo(filename=f"sample{ext}"))
            assert result.data_modality == "genomic"
            assert result.confidence >= 0.95

    def test_single_cell_matrix(self, engine):
        """Single-cell matrix files should be transcriptomic.single_cell."""
        result = engine.classify(FileInfo(filename="sample.h5ad"))
        assert result.data_modality == "transcriptomic.single_cell"
        assert result.confidence >= 0.90

    def test_single_cell_atac(self, engine):
        """Single-cell ATAC matrix should be epigenomic."""
        result = engine.classify(FileInfo(filename="sample_atac_peaks.h5ad"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"

    def test_methylation_idat(self, engine):
        """IDAT files should be epigenomic.methylation."""
        result = engine.classify(FileInfo(filename="sample.idat"))
        assert result.data_modality == "epigenomic.methylation"
        assert result.confidence >= 0.95

    def test_histology_svs(self, engine):
        """SVS files should be imaging.histology."""
        result = engine.classify(FileInfo(filename="GTEX-18A6Q-1126.svs"))
        assert result.data_modality == "imaging.histology"
        assert result.confidence >= 0.95


class TestFastqFiles:
    """Test FASTQ file classification."""

    def test_fastq_rna(self, engine):
        """FASTQ with RNA indicator."""
        result = engine.classify(FileInfo(filename="sample_rnaseq_R1.fastq.gz"))
        assert result.data_modality == "transcriptomic.bulk"

    def test_fastq_ambiguous(self, engine):
        """FASTQ without indicators needs study context."""
        result = engine.classify(FileInfo(filename="sample_R1.fastq.gz"))
        assert result.needs_study_context is True


class TestSignalTracks:
    """Test signal track classification."""

    def test_bigwig_chip(self, engine):
        """ChIP-seq bigwig files."""
        result = engine.classify(FileInfo(filename="sample_H3K27ac.bigwig"))
        assert result.data_modality == "epigenomic.histone_modification"

    def test_bigwig_atac(self, engine):
        """ATAC-seq bigwig files."""
        result = engine.classify(FileInfo(filename="sample_atac.bw"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"


class TestPeakFiles:
    """Test peak file classification (narrowPeak, broadPeak, etc.)."""

    def test_narrowpeak_chromatin_accessibility(self, engine):
        """narrowPeak files should be epigenomic.chromatin_accessibility."""
        result = engine.classify(FileInfo(filename="sample.narrowPeak"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"
        assert result.confidence >= 0.85

    def test_broadpeak_chromatin_accessibility(self, engine):
        """broadPeak files should be epigenomic.chromatin_accessibility."""
        result = engine.classify(FileInfo(filename="sample.broadPeak"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"

    def test_peaks_bed_chromatin_accessibility(self, engine):
        """BED files with 'peaks' should be epigenomic.chromatin_accessibility."""
        result = engine.classify(FileInfo(filename="atac_peaks.bed"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"

    def test_chip_peaks_histone_modification(self, engine):
        """ChIP-seq peak files should be epigenomic.histone_modification."""
        result = engine.classify(FileInfo(filename="H3K27ac_chip_peaks.bed"))
        assert result.data_modality == "epigenomic.histone_modification"
        assert result.confidence >= 0.90

    def test_summit_bed_chromatin_accessibility(self, engine):
        """Summit files should be epigenomic.chromatin_accessibility."""
        result = engine.classify(FileInfo(filename="sample_summits.bed"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"


class TestTextFiles:
    """Test text/tabular file classification."""

    def test_stats_file(self, engine):
        """QC stats files should be skipped."""
        result = engine.classify(FileInfo(filename="sample.stats.txt"))
        assert result.skip is True

    def test_count_matrix(self, engine):
        """Count matrix files should be transcriptomic."""
        result = engine.classify(FileInfo(filename="gene_counts.txt"))
        assert result.data_modality == "transcriptomic.bulk"

    def test_ambiguous_txt(self, engine):
        """Ambiguous text files need manual review."""
        result = engine.classify(FileInfo(filename="data.txt"))
        assert result.needs_manual_review is True


class TestIntegration:
    """Integration tests against real filenames from API exploration."""

    def test_hifi_bam(self, engine):
        """HiFi reads BAM file."""
        result = engine.classify(
            FileInfo(filename="m64043_210211_005516.hifi_reads.bam")
        )
        assert result.data_modality == "genomic"
        assert result.confidence >= 0.70

    def test_vcf_with_chr(self, engine):
        """VCF with chromosome in filename."""
        result = engine.classify(FileInfo(filename="NA19189.chr2.hc.vcf.gz"))
        assert result.data_modality == "genomic"
        assert result.confidence >= 0.85

    def test_gtex_histology(self, engine):
        """GTEx histology image."""
        result = engine.classify(FileInfo(filename="GTEX-18A6Q-1126.svs"))
        assert result.data_modality == "imaging.histology"
        assert result.confidence >= 0.95

    def test_cram_md5(self, engine):
        """CRAM MD5 checksum should be skipped."""
        result = engine.classify(FileInfo(filename="HG02558.final.cram.md5"))
        assert result.skip is True

    def test_unknown_extension(self, engine):
        """Unknown extensions should need manual review."""
        result = engine.classify(FileInfo(filename="sample.xyz"))
        assert result.needs_manual_review is True


class TestReasonChain:
    """Test that reason chains are properly built."""

    def test_multiple_reasons(self, engine):
        """Multiple matching rules should accumulate reasons."""
        result = engine.classify(FileInfo(filename="sample_RNA.hg38.bam"))
        assert len(result.reasons) >= 2
        assert len(result.rules_matched) >= 2

    def test_reason_explains_decision(self, engine):
        """Reasons should explain why classification was made."""
        result = engine.classify(FileInfo(filename="sample.svs"))
        assert any("histology" in r.lower() or "svs" in r.lower() for r in result.reasons)


class TestSentinelValues:
    """Test that not_applicable/not_classified sentinels are used correctly."""

    def test_skipped_files_get_not_applicable(self, engine):
        """Skipped files (indexes, checksums) should get not_applicable for all fields."""
        result = engine.classify_extended(FileInfo(filename="sample.bam.bai"))
        assert result.skip is True
        assert result.data_modality == NOT_APPLICABLE
        assert result.reference_assembly == NOT_APPLICABLE
        assert result.platform == NOT_APPLICABLE
        assert result.assay_type == NOT_APPLICABLE

    def test_unclassified_fields_get_not_classified(self, engine):
        """Non-skipped files with unset fields should get not_classified."""
        result = engine.classify_extended(FileInfo(filename="sample.xyz"))
        assert result.skip is False
        assert result.data_modality == NOT_CLASSIFIED
        assert result.reference_assembly == NOT_CLASSIFIED

    def test_not_classified_evidence_includes_field_name(self, engine):
        """Evidence reason for not_classified should name the specific field."""
        result = engine.classify_extended(FileInfo(filename="sample.xyz"))
        for fld in ["data_modality", "data_type", "platform", "reference_assembly", "assay_type"]:
            evidence = result.field_evidence[fld]
            nc_evidence = [e for e in evidence if e["rule_id"] == "not_classified"]
            if nc_evidence:
                assert fld in nc_evidence[0]["reason"], \
                    f"Expected '{fld}' in reason, got: {nc_evidence[0]['reason']}"

    def test_images_get_not_applicable_for_genomic_fields(self, engine):
        """Image files should get not_applicable for platform and reference."""
        result = engine.classify_extended(FileInfo(filename="sample.svs"))
        assert result.data_modality == "imaging.histology"
        assert result.platform == NOT_APPLICABLE
        assert result.reference_assembly == NOT_APPLICABLE

    def test_fastq_gets_not_applicable_reference(self, engine):
        """FASTQ files should get not_applicable for reference (unaligned reads)."""
        result = engine.classify_extended(FileInfo(filename="sample.fastq.gz"))
        assert result.reference_assembly == NOT_APPLICABLE

    def test_fast5_gets_not_applicable_reference(self, engine):
        """FAST5 files should get not_applicable for reference (raw signal)."""
        result = engine.classify_extended(FileInfo(filename="sample.fast5"))
        assert result.reference_assembly == NOT_APPLICABLE
        assert result.platform == "ONT"

    def test_modality_not_set_ignores_sentinel(self, engine):
        """modality_not_set guard should treat NOT_CLASSIFIED as 'not set',
        allowing rules to fire on files where no earlier rule set modality."""
        # An unknown file type gets not_classified for modality from finalization.
        # If we then re-run with additional info, modality_not_set rules should still fire.
        result = engine.classify_extended(
            ExtendedFileInfo(filename="sample.bam", file_size_gb=60.0)
        )
        # BAM gets 'genomic' from a fallback rule, and size heuristic confirms WGS
        assert result.data_modality in ("genomic", "genomic.whole_genome")
        assert "alignment_size_wgs" in result.rules_matched

    def test_png_all_fields_not_applicable(self, engine):
        """PNG files should get not_applicable for all non-applicable fields."""
        result = engine.classify_extended(FileInfo(filename="plot.png"))
        assert result.data_modality == NOT_APPLICABLE
        assert result.platform == NOT_APPLICABLE
        assert result.reference_assembly == NOT_APPLICABLE
        assert result.assay_type == NOT_APPLICABLE
