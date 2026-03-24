"""End-to-end evaluation tests for classification pipeline.

These test the ACTUAL script functions with REAL cached evidence files,
not the internal classify functions directly. The input is a file
(via md5 -> cached evidence), the output is the JSON record that would
appear in the output file.

For rule-engine-only classifiers (BED, images, auxiliary), the input
is a FileInfo and the output is an ExtendedClassificationResult.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# Import the actual script functions
from classify_bam_files import classify_single_file as classify_bam
from classify_fasta_files import classify_single_fasta as classify_fasta
from classify_fastq_files import classify_single_fastq as classify_fastq
from classify_vcf_files import classify_single_vcf as classify_vcf

from src.meta_disco.models import NOT_APPLICABLE, NOT_CLASSIFIED, FileInfo
from src.meta_disco.rule_engine import RuleEngine

engine = RuleEngine()


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
    for field in ["data_modality", "data_type", "platform", "reference_assembly", "assay_type"]:
        assert field in cls, f"Missing classification field: {field}"
        entry = cls[field]
        assert isinstance(entry, dict), f"{field} should be dict"
        assert "value" in entry, f"{field} missing 'value'"
        assert "evidence" in entry, f"{field} missing 'evidence'"
        assert "confidence" in entry, f"{field} missing 'confidence'"
        # assay_type may be set by post-hoc inference which doesn't produce evidence
        if field != "assay_type":
            assert len(entry["evidence"]) > 0, f"{field} has empty evidence"



# =============================================================================
# BAM/CRAM — end-to-end through classify_bam_files.classify_single_file
# =============================================================================

class TestBamE2E:
    """End-to-end BAM classification from cached headers."""

    def test_grch38_aligned_bam(self):
        """HG03516.GRCh38_no_alt.bam — 239.6 GB ONT BAM aligned to GRCh38."""
        result = classify_bam("000ebc5cfdeb4e799aa047e2c54022af", "HG03516.GRCh38_no_alt.bam",
                              file_size=239579784536, file_format=".bam")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "reference_assembly") == "GRCh38"
        assert get_val(result, "platform") in ("ILLUMINA", "ONT", "PACBIO")
        # TODO #73: aligned BAM with reference contigs should infer genomic modality,
        # which would then enable WGS assay_type inference

    def test_pacbio_hifi_unaligned(self):
        """PacBio reads BAM — 229.4 GB, unaligned, reference N/A."""
        result = classify_bam("0004e46159f2fc28224533d71d828108", "r54329U_20220207_223353_A01.reads.bam",
                              file_size=229421051106, file_format=".bam")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "PACBIO"
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE
        assert get_val(result, "assay_type") == "WGS"

    def test_ont_bam(self):
        """ONT BAM file — 69.8 GB."""
        result = classify_bam("000e5edf6937cccf67767fb886626655",
                              "06_28_22_R941_HG02922_3_Guppy_6.5.7_450bps_modbases_5mc_cg_sup_prom_pass.bam",
                              file_size=69806670027, file_format=".bam")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ONT"
        assert get_val(result, "assay_type") == "WGS"

    def test_no_stale_evidence(self):
        """reference_assembly should not have stale not_classified evidence."""
        result = classify_bam("000ebc5cfdeb4e799aa047e2c54022af", "HG03516.GRCh38_no_alt.bam",
                              file_size=239579784536, file_format=".bam")
        cls = result["classifications"]
        ref_evidence = cls["reference_assembly"]["evidence"]
        stale = [e for e in ref_evidence if e["rule_id"] == "not_classified"]
        assert len(stale) == 0, f"Stale not_classified evidence: {stale}"

    def test_star_rnaseq_bam(self):
        """GM20525-10-2.bam — 6.7 GB STAR-aligned RNA-seq."""
        result = classify_bam("000811b87381c4dd9e5d7a940be14cee", "GM20525-10-2.bam",
                              file_size=6694895254, file_format=".bam")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "transcriptomic.bulk"
        assert get_val(result, "data_type") == "alignments"
        assert get_val(result, "assay_type") == "RNA-seq"

    def test_platform_confidence_meaningful(self):
        """Platform detection from @RG PL: should have non-zero confidence."""
        result = classify_bam("000ebc5cfdeb4e799aa047e2c54022af", "HG03516.GRCh38_no_alt.bam",
                              file_size=239579784536, file_format=".bam")
        cls = result["classifications"]
        platform_conf = cls["platform"]["confidence"]
        assert platform_conf > 0, f"Platform confidence should be > 0, got {platform_conf}"

    def test_illumina_cram_wgs_assay_type(self):
        """HG00741.final.cram — 15.9 GB Illumina CRAM should infer WGS.

        Assay type inference depends on platform (from tier 3 header rules)
        and file size, so it runs in the post-hoc assay_type_rules phase.
        """
        result = classify_bam("cce22695c03f0f583384e5335a9965d7", "HG00741.final.cram",
                              file_size=15868198733, file_format=".cram")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ILLUMINA"
        assert get_val(result, "assay_type") == "WGS"

    def test_rnaseq_bam_assay_type(self):
        """HG03382.bam — 5.5 GB STAR-aligned RNA-seq."""
        result = classify_bam("60fbc0142751adebc0aa81a22ff3c9fd", "HG03382.bam",
                              file_size=5521863634, file_format=".bam")
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "transcriptomic.bulk"
        assert get_val(result, "assay_type") == "RNA-seq"


# =============================================================================
# VCF — end-to-end through classify_vcf_files.classify_single_vcf
# =============================================================================

class TestVcfE2E:
    """End-to-end VCF classification from cached headers."""

    def test_haplotypecaller_vcf(self):
        """HG03854.chrY.hc.vcf.gz — 3.7 MB HaplotypeCaller germline."""
        result = classify_vcf("00001845984e9c9a66433f9fa8476f99", "HG03854.chrY.hc.vcf.gz",
                              file_size=3748178)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "assay_type") == NOT_CLASSIFIED

    def test_single_chrom_reference_detection(self):
        """Single-chromosome VCF should still identify reference assembly."""
        result = classify_vcf("0000d4b336dbc16a216ebdfeaf092702", "HG01809.chr21.hc.vcf.gz",
                              file_size=76348632)
        assert result is not None
        ref = get_val(result, "reference_assembly")
        assert ref in ("GRCh38", "GRCh37", "CHM13"), f"Expected a reference, got {ref}"

    def test_vcf_has_contig_evidence(self):
        """VCF reference should come from contig length detection."""
        result = classify_vcf("0000b1430a498c7774dd33a5a58677ad", "NA21125.chr2.hc.vcf.gz",
                              file_size=443147740)
        assert result is not None
        cls = result["classifications"]
        ref_evidence = cls["reference_assembly"]["evidence"]
        rule_ids = [e["rule_id"] for e in ref_evidence]
        assert "vcf_contig_length" in rule_ids, f"Expected vcf_contig_length, got {rule_ids}"

    def test_sniffles_sv_vcf(self):
        """HG02723 Sniffles SV VCF — 35 MB structural variant detection."""
        result = classify_vcf("0203bdde8d2f9bba858dce981a409bd5", "HG02723.hifiasm_pat.sniffles.vcf",
                              file_size=35257072, is_gzipped=False)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"

    def test_vcf_no_stale_evidence(self):
        """VCF reference_assembly should not have stale not_classified evidence."""
        result = classify_vcf("0000b1430a498c7774dd33a5a58677ad", "NA21125.chr2.hc.vcf.gz",
                              file_size=443147740)
        cls = result["classifications"]
        ref = cls["reference_assembly"]
        if ref["value"] not in (NOT_CLASSIFIED, None):
            stale = [e for e in ref["evidence"] if e["rule_id"] == "not_classified"]
            assert len(stale) == 0, f"Stale evidence: {stale}"


# =============================================================================
# FASTQ — end-to-end through classify_fastq_files.classify_single_fastq
# =============================================================================

class TestFastqE2E:
    """End-to-end FASTQ classification from cached read names."""

    def test_illumina_fastq(self):
        """GM20294_R1_001.fastq.gz — 2.1 GB Illumina paired read."""
        result = classify_fastq("00077512aa3448912698292770d41ca5", "GM20294_R1_001.fastq.gz",
                                file_size=2054321679)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ILLUMINA"
        assert get_val(result, "data_modality") == NOT_CLASSIFIED
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE
        assert get_val(result, "assay_type") == NOT_CLASSIFIED  # modality unknown, so no WES/WGS inference

    def test_ena_reformatted_fastq(self):
        """ERR3989178_1.fastq.gz — 13.5 GB ENA-reformatted with accession."""
        result = classify_fastq("0008a97d74c385aeb7eed75f33601d59", "ERR3989178_1.fastq.gz",
                                file_size=13477702401)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ILLUMINA"

    def test_fastq_reference_not_applicable(self):
        """All FASTQ files should have reference N/A (raw reads)."""
        result = classify_fastq("000644fa14ab21a7106a746664d58aa9", "HG02486x02PE20573_1_sequence.fastq.gz",
                                file_size=84212465)
        assert result is not None
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_pacbio_ccs_fastq(self):
        """PacBio CCS/HiFi FASTQ — 28.6 GB, should detect PacBio platform."""
        result = classify_fastq("0073d35c9f5b68a739e3daf50a227f72",
                                "HG01109.m64043_200830_075523.dc.q20.fastq.gz",
                                file_size=28614484832)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "PACBIO"
        assert get_val(result, "data_modality") == NOT_CLASSIFIED
        assert get_val(result, "assay_type") == NOT_CLASSIFIED  # modality unknown, so no WGS inference

    def test_mgi_fastq(self):
        """MGI/BGI platform FASTQ — 32.3 GB."""
        result = classify_fastq("00c68ff0f9e0217d422c57e8948d4bb4", "IGVFFI6614EZDQ.fastq.gz",
                                file_size=32327542019)
        assert result is not None
        assert_output_format(result)
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
        assert result.data_modality == NOT_CLASSIFIED
        assert result.data_type == "raw_signal"
        assert result.platform == "ONT"
        assert result.reference_assembly == NOT_APPLICABLE

    def test_pod5_raw_signal(self):
        result = engine.classify_extended(FileInfo(filename="sample_run.pod5"))
        assert result.data_modality == NOT_CLASSIFIED
        assert result.data_type == "raw_signal"
        assert result.platform == "ONT"
        assert result.reference_assembly == NOT_APPLICABLE

    def test_flnc_bam_is_transcriptomic(self):
        """IsoSeq flnc BAM should be transcriptomic, not genomic."""
        result = engine.classify_extended(FileInfo(
            filename="HG00097.lymph.m84203_240914_042802_s4.flnc.bam"
        ))
        assert result.data_modality == "transcriptomic.bulk"

    def test_isoseq_bam_is_transcriptomic(self):
        """BAM with isoseq in filename should be transcriptomic."""
        result = engine.classify_extended(FileInfo(filename="sample.isoseq.bam"))
        assert result.data_modality == "transcriptomic.bulk"

    def test_plain_bam_no_modality(self):
        """BAM without header or platform signals should not get genomic modality."""
        result = engine.classify_extended(FileInfo(filename="sample.reads.bam"))
        assert result.data_modality == NOT_CLASSIFIED

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
        assert result.data_modality == "genomic"

    def test_fastq_rna_filename(self):
        result = engine.classify_extended(FileInfo(filename="sample_RNA_001.fastq.gz"))
        assert result.data_modality == "transcriptomic.bulk"
        assert result.reference_assembly == NOT_APPLICABLE

    def test_checksum_skipped(self):
        result = engine.classify_extended(FileInfo(filename="sample.md5"))
        assert result.skip is True
        assert result.data_modality == NOT_APPLICABLE

    def test_chunked_upload_skipped(self):
        result = engine.classify_extended(FileInfo(
            filename="c5ff4e67-1db9-4fd1.gs-chunked-io-part.000013"
        ))
        assert result.skip is True
        assert result.data_modality == NOT_APPLICABLE

    def test_timestamp_filename_skipped(self):
        result = engine.classify_extended(FileInfo(
            filename="2020-11-20T212208.245537Z"
        ))
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

    def test_fasta_base_rule(self):
        """FASTA files should get base rule classification."""
        for ext in [".fa", ".fasta", ".fa.gz", ".fasta.gz"]:
            result = engine.classify_extended(FileInfo(filename=f"sample{ext}"))
            assert result.data_type == "sequence", f"{ext} should be sequence"
            assert result.platform == NOT_APPLICABLE
            assert result.assay_type == NOT_APPLICABLE

    def test_fasta_assembly_filename(self):
        """FASTA with assembly keyword in filename."""
        result = engine.classify_extended(FileInfo(filename="HG00673.paternal.f1_assembly_v1.fa.gz"))
        assert result.data_modality == "genomic"
        assert result.data_type == "assembly"
        assert result.reference_assembly == NOT_APPLICABLE

    def test_fasta_haplotype_filename(self):
        """FASTA with haplotype keyword in filename."""
        result = engine.classify_extended(FileInfo(filename="hapdup_contigs_2.fasta"))
        assert result.data_modality == "genomic"
        assert result.data_type == "assembly"
        assert result.reference_assembly == NOT_APPLICABLE

    def test_fasta_verkko_filename(self):
        """FASTA with verkko assembler keyword."""
        result = engine.classify_extended(FileInfo(filename="HG02300_verkko_gfase_diploid.fasta.gz"))
        assert result.data_modality == "genomic"
        assert result.data_type == "assembly"
        assert result.reference_assembly == NOT_APPLICABLE


# =============================================================================
# FASTA — end-to-end through classify_fasta_files.classify_single_fasta
# =============================================================================

class TestFastaE2E:
    """End-to-end FASTA classification from cached contig names."""

    def test_hprc_paternal_assembly(self):
        """HG00673.paternal.f1_assembly_v1.fa.gz — 851 MB HPRC de novo assembly."""
        result = classify_fasta("7ace6a53c63fdc2b99fba3f5f6be383d",
                                "HG00673.paternal.f1_assembly_v1.fa.gz",
                                file_size=851264823)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "assembly"
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE
        assert get_val(result, "assay_type") == NOT_APPLICABLE

    def test_verkko_diploid_assembly(self):
        """HG02300_verkko_gfase_diploid.fasta.gz — verkko assembler output."""
        result = classify_fasta("0fb14e01d1f886f8ebb6d5ea0f5a7853",
                                "HG02300_verkko_gfase_diploid.fasta.gz",
                                file_size=0)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "assembly"
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_hapdup_contigs(self):
        """hapdup_contigs_2.fasta — hapdup output, contig name is just "0".
        Real evidence: single contig "0" from S3 range request.
        Classification relies on filename "hapdup" keyword (tier 2 rule)."""
        result = classify_fasta("1eff1ed22b7b2d794b9e4d2edc9b4bfa",
                                "hapdup_contigs_2.fasta",
                                file_size=0)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "assembly"
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_grch38_reference_genome(self):
        """grch38.XX.fasta — 3.2 GB GRCh38 reference genome."""
        result = classify_fasta("c20f4108273910a8eac78b6f2d5cb2b3",
                                "grch38.XX.fasta",
                                file_size=3249604816)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "reference_genome"
        assert get_val(result, "reference_assembly") == "GRCh38"
        assert get_val(result, "assay_type") == NOT_APPLICABLE

    def test_chm13_reference_genome(self):
        """chm13v2.0.fasta — 3.2 GB CHM13 T2T reference."""
        result = classify_fasta("597207bc60de08a8535b0fcc23466ebc",
                                "chm13v2.0.fasta",
                                file_size=3156259347)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "reference_genome"
        assert get_val(result, "reference_assembly") == "CHM13"
        assert get_val(result, "assay_type") == NOT_APPLICABLE

    def test_hifiasm_mito_contigs(self):
        """HG002.hifiasm_0.19.0_trio.diploid.mito.fa.gz — 26 KB, 7 mitochondrial contigs."""
        result = classify_fasta("e3518b0e9056278b3e3e77fca0d20739",
                                "HG002.hifiasm_0.19.0_trio.diploid.mito.fa.gz",
                                file_size=25943)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "assembly"
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_verkko_mito_contigs(self):
        """HG002_verkko_gfase_mito.fasta.gz — 38 KB, 12 verkko contigs."""
        result = classify_fasta("77918ce8d61e250943bd2b363caee845",
                                "HG002_verkko_gfase_mito.fasta.gz",
                                file_size=37923)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "assembly"
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_verkko_mito_single_contig(self):
        """HG02809_verkko_asm_mito_exemplar.fasta.gz — 3.5 KB single contig."""
        result = classify_fasta("dbfd70b99346b4897a2d6f27dee309c9",
                                "HG02809_verkko_asm_mito_exemplar.fasta.gz",
                                file_size=3538)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "assembly"
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_empty_gzip_fasta(self):
        """HG02647.hifiasm_0.19.3_hic.diploid.mito.fa.gz — valid gzip, 20 bytes."""
        result = classify_fasta("7029066c27ac6f5ef18d660d5741979a",
                                "HG02647.hifiasm_0.19.3_hic.diploid.mito.fa.gz",
                                file_size=20)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "assembly"
        assert get_val(result, "reference_assembly") == NOT_APPLICABLE

    def test_genbank_single_region(self):
        """hg002-f1-assembly-v2-genbank-dip-s2c20h1l-mat.fa — 2.3 MB single GenBank region."""
        result = classify_fasta("5255a14542a8931eb6b393af8486a2b9",
                                "hg002-f1-assembly-v2-genbank-dip-s2c20h1l-mat.fa",
                                file_size=2310976)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
