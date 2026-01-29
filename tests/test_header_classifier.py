"""Tests for the header classifier module."""

import pytest

from src.meta_disco.header_classifier import (
    # Helper functions
    extract_archive_accession,
    infer_illumina_instrument_model,
    detect_paired_end_indicators,
    parse_illumina_read_name,
    parse_pacbio_read_name,
    parse_ont_read_name,
    # Classification functions
    classify_from_fastq_header,
    classify_from_vcf_header,
    classify_from_header,
)


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestExtractArchiveAccession:
    """Test archive accession extraction from FASTQ read names."""

    def test_ena_accession(self):
        """Extract ENA (ERR) accession."""
        accession, source, remainder = extract_archive_accession(
            "@ERR3242571.1 A00297:44:HFKH3DSXX:2:1354:30508:28839/1"
        )
        assert accession == "ERR3242571"
        assert source == "ENA"
        assert remainder == "A00297:44:HFKH3DSXX:2:1354:30508:28839/1"

    def test_sra_accession(self):
        """Extract SRA (SRR) accession."""
        accession, source, remainder = extract_archive_accession(
            "@SRR12345678.1 original_read_name"
        )
        assert accession == "SRR12345678"
        assert source == "SRA"
        assert remainder == "original_read_name"

    def test_ddbj_accession(self):
        """Extract DDBJ (DRR) accession."""
        accession, source, remainder = extract_archive_accession(
            "@DRR000001.1 some_data"
        )
        assert accession == "DRR000001"
        assert source == "DDBJ"

    def test_no_accession(self):
        """No accession in native read name."""
        accession, source, remainder = extract_archive_accession(
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839"
        )
        assert accession is None
        assert source is None
        assert remainder == "A00297:44:HFKH3DSXX:2:1354:30508:28839"

    def test_without_at_prefix(self):
        """Handle read name without @ prefix."""
        accession, source, _ = extract_archive_accession(
            "ERR3242571.1 A00297:44:HFKH3DSXX:2:1354"
        )
        assert accession == "ERR3242571"
        assert source == "ENA"

    def test_accession_only(self):
        """Handle accession without original read name."""
        accession, source, remainder = extract_archive_accession("@SRR123.1")
        assert accession == "SRR123"
        assert source == "SRA"
        assert remainder == ""


class TestInferIlluminaInstrumentModel:
    """Test Illumina instrument model inference from ID."""

    def test_novaseq_6000(self):
        """NovaSeq 6000 IDs start with A0."""
        assert infer_illumina_instrument_model("A00297") == "NovaSeq 6000"
        assert infer_illumina_instrument_model("A01234") == "NovaSeq 6000"

    def test_novaseq_generic(self):
        """Other A-prefix IDs are generic NovaSeq."""
        assert infer_illumina_instrument_model("A23456") == "NovaSeq"

    def test_miseq(self):
        """MiSeq IDs start with M."""
        assert infer_illumina_instrument_model("M00123") == "MiSeq"
        assert infer_illumina_instrument_model("M70001") == "MiSeq"

    def test_hiseq_2500(self):
        """HiSeq 2500 IDs start with D."""
        assert infer_illumina_instrument_model("D00123") == "HiSeq 2500"

    def test_hiseq_x(self):
        """HiSeq X IDs start with E."""
        assert infer_illumina_instrument_model("E00123") == "HiSeq X"

    def test_nextseq_500(self):
        """NextSeq 500/550 IDs start with N."""
        assert infer_illumina_instrument_model("N00123") == "NextSeq"

    def test_nextseq_2000(self):
        """NextSeq 2000 IDs start with VH."""
        assert infer_illumina_instrument_model("VH00123") == "NextSeq 2000"

    def test_hiseq_4000(self):
        """HiSeq 4000 IDs start with K."""
        assert infer_illumina_instrument_model("K00123") == "HiSeq 4000"

    def test_unknown(self):
        """Unknown prefix returns None."""
        assert infer_illumina_instrument_model("X00123") is None
        assert infer_illumina_instrument_model("") is None

    def test_case_insensitive(self):
        """Should handle lowercase input."""
        assert infer_illumina_instrument_model("a00297") == "NovaSeq 6000"


class TestDetectPairedEndIndicators:
    """Test paired-end indicator detection."""

    def test_slash_suffix(self):
        """Detect /1 and /2 suffixes."""
        assert detect_paired_end_indicators("read_name/1") is True
        assert detect_paired_end_indicators("read_name/2") is True

    def test_underscore_r1_r2(self):
        """Detect _R1_ and _R2_ patterns."""
        assert detect_paired_end_indicators("sample_R1_001.fastq") is True
        assert detect_paired_end_indicators("sample_R2_001.fastq") is True

    def test_dot_r1_r2(self):
        """Detect .R1. and .R2. patterns."""
        assert detect_paired_end_indicators("sample.R1.fastq") is True

    def test_lowercase(self):
        """Detect lowercase _r1_ and _r2_."""
        assert detect_paired_end_indicators("sample_r1_001.fastq") is True

    def test_no_indicator(self):
        """No paired-end indicator."""
        assert detect_paired_end_indicators("sample.fastq") is False
        assert detect_paired_end_indicators("single_read") is False


class TestParseIlluminaReadName:
    """Test Illumina read name parsing."""

    def test_modern_format_full(self):
        """Parse modern Illumina format with all fields."""
        result = parse_illumina_read_name(
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839 1:N:0:ATCACG"
        )
        assert result is not None
        assert result["format"] == "modern"
        assert result["instrument"] == "A00297"
        assert result["run_number"] == 44
        assert result["flowcell"] == "HFKH3DSXX"
        assert result["lane"] == 2
        assert result["tile"] == 1354
        assert result["read"] == 1
        assert result["filtered"] is False
        assert result["index"] == "ATCACG"

    def test_modern_format_minimal(self):
        """Parse modern format without optional second part."""
        result = parse_illumina_read_name(
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839"
        )
        assert result is not None
        assert result["instrument"] == "A00297"
        assert "read" not in result

    def test_legacy_format(self):
        """Parse legacy Illumina format."""
        result = parse_illumina_read_name(
            "@HWUSI-EAS100R:6:73:941:1973#ATCACG/1"
        )
        assert result is not None
        assert result["format"] == "legacy"
        assert result["instrument"] == "HWUSI-EAS100R"
        assert result["lane"] == 6
        assert result["index"] == "ATCACG"
        assert result["read"] == 1

    def test_archive_reformatted(self):
        """Parse archive-reformatted Illumina read."""
        result = parse_illumina_read_name(
            "@ERR3242571.1 A00297:44:HFKH3DSXX:2:1354:30508:28839"
        )
        assert result is not None
        assert result["archive_accession"] == "ERR3242571"
        assert result["archive_source"] == "ENA"
        assert result["instrument"] == "A00297"

    def test_non_illumina(self):
        """Return None for non-Illumina format."""
        assert parse_illumina_read_name("@m64011_190830/1/ccs") is None
        assert parse_illumina_read_name("random_text") is None


class TestParsePacbioReadName:
    """Test PacBio read name parsing."""

    def test_ccs_format(self):
        """Parse CCS/HiFi read name."""
        result = parse_pacbio_read_name("@m64011_190830_220126/1/ccs")
        assert result is not None
        assert result["format"] == "ccs"
        assert result["movie"] == "m64011_190830_220126"
        assert result["zmw"] == 1
        assert result["read_type"] == "CCS"

    def test_clr_format(self):
        """Parse CLR subread name."""
        result = parse_pacbio_read_name("@m64011_190830_220126/1234/0_5000")
        assert result is not None
        assert result["format"] == "clr"
        assert result["movie"] == "m64011_190830_220126"
        assert result["zmw"] == 1234
        assert result["start"] == 0
        assert result["end"] == 5000
        assert result["read_type"] == "CLR"

    def test_generic_format(self):
        """Parse generic PacBio read name."""
        result = parse_pacbio_read_name("@m64011_190830_220126/1234")
        assert result is not None
        assert result["format"] == "generic"
        assert result["zmw"] == 1234

    def test_sequel_ii_movie(self):
        """Parse Sequel II movie name (with 'e' suffix)."""
        result = parse_pacbio_read_name("@m64011e_210101_120000/1/ccs")
        assert result is not None
        assert result["movie"] == "m64011e_210101_120000"

    def test_non_pacbio(self):
        """Return None for non-PacBio format."""
        assert parse_pacbio_read_name("@A00297:44:HFKH3DSXX") is None


class TestParseOntReadName:
    """Test Oxford Nanopore read name parsing."""

    def test_uuid_format(self):
        """Parse ONT UUID read name."""
        result = parse_ont_read_name(
            "@a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        )
        assert result is not None
        assert result["format"] == "ont"
        assert result["uuid"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_uuid_with_metadata(self):
        """Parse ONT read name with key=value metadata."""
        result = parse_ont_read_name(
            "@a1b2c3d4-e5f6-7890-abcd-ef1234567890 runid=abc123 read=456 ch=789"
        )
        assert result is not None
        assert result["uuid"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert result["runid"] == "abc123"
        assert result["read"] == "456"
        assert result["ch"] == "789"

    def test_non_ont(self):
        """Return None for non-ONT format."""
        assert parse_ont_read_name("@A00297:44:HFKH3DSXX") is None
        assert parse_ont_read_name("not-a-uuid") is None


# =============================================================================
# FASTQ CLASSIFICATION TESTS
# =============================================================================

class TestFastqClassification:
    """Test FASTQ header classification."""

    def test_illumina_modern(self):
        """Classify modern Illumina FASTQ."""
        reads = [
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839 1:N:0:ATCACG",
            "@A00297:44:HFKH3DSXX:2:1354:30509:28840 1:N:0:ATCACG",
            "@A00297:44:HFKH3DSXX:2:1354:30510:28841 1:N:0:ATCACG",
        ]
        result = classify_from_fastq_header(reads)
        assert result["platform"] == "ILLUMINA"
        assert result["data_modality"] == "genomic"
        assert result["data_type"] == "reads"
        assert result["confidence"] >= 0.90

    def test_illumina_instrument_model(self):
        """Extract Illumina instrument model."""
        reads = ["@A00297:44:HFKH3DSXX:2:1354:30508:28839 1:N:0:ATCACG"]
        result = classify_from_fastq_header(reads)
        assert result["instrument_model"] == "NovaSeq 6000"
        assert result["instrument_hint"] == "A00297"

    def test_illumina_legacy(self):
        """Classify legacy Illumina FASTQ."""
        reads = [
            "@HWUSI-EAS100R:6:73:941:1973#ATCACG/1",
            "@HWUSI-EAS100R:6:73:942:1974#ATCACG/1",
        ]
        result = classify_from_fastq_header(reads)
        assert result["platform"] == "ILLUMINA"
        assert result["confidence"] >= 0.85

    def test_ena_reformatted(self):
        """Classify ENA-reformatted FASTQ with accession extraction."""
        reads = [
            "@ERR3242571.1 A00297:44:HFKH3DSXX:2:1354:30508:28839/1",
            "@ERR3242571.2 A00297:44:HFKH3DSXX:2:1354:30509:28840/1",
        ]
        result = classify_from_fastq_header(reads)
        assert result["platform"] == "ILLUMINA"
        assert result["archive_accession"] == "ERR3242571"
        assert result["archive_source"] == "ENA"
        assert result["instrument_model"] == "NovaSeq 6000"

    def test_sra_reformatted(self):
        """Classify SRA-reformatted FASTQ."""
        reads = ["@SRR12345678.1 M00123:1:000000000-A1BC2:1:1:1:1"]
        result = classify_from_fastq_header(reads)
        assert result["archive_accession"] == "SRR12345678"
        assert result["archive_source"] == "SRA"

    def test_ena_hiseq_2000(self):
        """Classify ENA-reformatted FASTQ with HiSeq 2000 instrument."""
        reads = [
            "@ERR1395578.1 HS2000-1260_220:1:1101:10000:10158/1",
            "@ERR1395578.2 HS2000-1260_220:1:1101:10001:10159/1",
        ]
        result = classify_from_fastq_header(reads)
        assert result["platform"] == "ILLUMINA"
        assert result["data_modality"] == "genomic"
        assert result["archive_accession"] == "ERR1395578"
        assert result["confidence"] >= 0.85

    def test_ena_hiseq_2500(self):
        """Classify ENA-reformatted FASTQ with HiSeq 2500 instrument."""
        reads = [
            "@ERR9999999.1 HS2500-1234_100:2:1101:5000:5000/1",
        ]
        result = classify_from_fastq_header(reads)
        assert result["platform"] == "ILLUMINA"
        assert result["data_modality"] == "genomic"

    def test_pacbio_ccs(self):
        """Classify PacBio CCS/HiFi FASTQ."""
        reads = [
            "@m64011_190830_220126/1/ccs",
            "@m64011_190830_220126/2/ccs",
            "@m64011_190830_220126/3/ccs",
        ]
        result = classify_from_fastq_header(reads)
        assert result["platform"] == "PACBIO"
        assert result["data_modality"] == "genomic"
        assert result["data_type"] == "reads"
        assert result["confidence"] >= 0.95

    def test_pacbio_clr(self):
        """Classify PacBio CLR FASTQ."""
        reads = [
            "@m64011_190830_220126/1234/0_5000",
            "@m64011_190830_220126/1234/5001_10000",
        ]
        result = classify_from_fastq_header(reads)
        assert result["platform"] == "PACBIO"
        assert result["data_modality"] == "genomic"

    def test_ont(self):
        """Classify Oxford Nanopore FASTQ."""
        reads = [
            "@a1b2c3d4-e5f6-7890-abcd-ef1234567890 runid=abc123",
            "@b2c3d4e5-f6a7-8901-bcde-f12345678901 runid=abc123",
        ]
        result = classify_from_fastq_header(reads)
        assert result["platform"] == "ONT"
        assert result["data_modality"] == "genomic"

    def test_mgi(self):
        """Classify MGI/BGI FASTQ."""
        reads = [
            "@V350012345L1C001R0010000001/1",
            "@V350012345L1C001R0010000002/1",
        ]
        result = classify_from_fastq_header(reads)
        assert result["platform"] == "MGI"

    def test_paired_end_detection(self):
        """Detect paired-end from read names."""
        reads = [
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839/1",
            "@A00297:44:HFKH3DSXX:2:1354:30509:28840/1",
        ]
        result = classify_from_fastq_header(reads)
        assert result["is_paired_end"] is True

    def test_paired_end_from_filename(self):
        """Detect paired-end from filename."""
        reads = ["@A00297:44:HFKH3DSXX:2:1354:30508:28839"]
        result = classify_from_fastq_header(reads, file_name="sample_R1_001.fastq.gz")
        assert result["is_paired_end"] is True

    def test_empty_input(self):
        """Handle empty input gracefully."""
        result = classify_from_fastq_header([])
        assert result["platform"] is None
        assert result["confidence"] == 0.0

    def test_confidence_boost_on_agreement(self):
        """Confidence should increase when all reads agree."""
        reads = [
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839",
            "@A00297:44:HFKH3DSXX:2:1354:30509:28840",
            "@A00297:44:HFKH3DSXX:2:1354:30510:28841",
        ]
        result = classify_from_fastq_header(reads)
        # Should get boost for consistent reads
        assert result["confidence"] >= 0.90


# =============================================================================
# VCF CLASSIFICATION TESTS
# =============================================================================

class TestVcfClassification:
    """Test VCF header classification."""

    def test_grch38_reference(self):
        """Detect GRCh38 reference from contig header."""
        header = """##fileformat=VCFv4.2
##reference=GRCh38
##contig=<ID=chr1,length=248956422,assembly=GRCh38>
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert result["reference_assembly"] == "GRCh38"
        # Reference detection is lower confidence than caller detection
        assert result["confidence"] >= 0.50

    def test_grch37_reference(self):
        """Detect GRCh37/hg19 reference."""
        header = """##fileformat=VCFv4.2
##reference=file:///refs/hg19.fasta
##contig=<ID=1,length=249250621,assembly=GRCh37>
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert result["reference_assembly"] == "GRCh37"

    def test_haplotypecaller_germline(self):
        """Detect GATK HaplotypeCaller as germline."""
        header = """##fileformat=VCFv4.2
##source=HaplotypeCaller
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert result["data_modality"] == "genomic"
        assert result["data_type"] == "germline_variants"
        assert "HaplotypeCaller" in result["caller"] or "haplotypecaller" in result["caller"].lower()

    def test_deepvariant_germline(self):
        """Detect DeepVariant as germline."""
        header = """##fileformat=VCFv4.2
##source=DeepVariant
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert result["data_modality"] == "genomic"
        assert result["data_type"] == "germline_variants"

    def test_mutect2_somatic(self):
        """Detect Mutect2 as somatic."""
        header = """##fileformat=VCFv4.2
##source=Mutect2
##tumor_sample=TUMOR
##normal_sample=NORMAL
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert result["data_modality"] == "genomic"
        assert result["data_type"] == "somatic_variants"

    def test_manta_sv(self):
        """Detect Manta as structural variants."""
        header = """##fileformat=VCFv4.2
##source=Manta
##INFO=<ID=SVTYPE,Number=1,Type=String,Description="Type of structural variant">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert result["data_modality"] == "genomic"
        assert result["data_type"] == "structural_variants"

    def test_sv_info_fields(self):
        """Detect SV from INFO fields."""
        header = """##fileformat=VCFv4.2
##INFO=<ID=SVTYPE,Number=1,Type=String,Description="SV type">
##INFO=<ID=SVLEN,Number=1,Type=Integer,Description="SV length">
##INFO=<ID=END,Number=1,Type=Integer,Description="End position">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert result["data_modality"] == "genomic"
        assert result["data_type"] == "structural_variants"

    def test_cnvkit_cnv(self):
        """Detect CNVkit as copy number variants."""
        header = """##fileformat=VCFv4.2
##source=CNVkit
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert result["data_modality"] == "genomic"
        assert result["data_type"] == "cnv_variants"

    def test_empty_header(self):
        """Handle minimal VCF header."""
        header = """##fileformat=VCFv4.2
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        # Should still work but with lower confidence
        assert "data_modality" in result


# =============================================================================
# BAM/CRAM CLASSIFICATION TESTS
# =============================================================================

class TestBamCramClassification:
    """Test BAM/CRAM header classification."""

    def test_illumina_platform(self):
        """Detect Illumina platform from @RG."""
        header = """@HD\tVN:1.6\tSO:coordinate
@SQ\tSN:chr1\tLN:248956422
@RG\tID:sample1\tPL:ILLUMINA\tSM:sample1"""
        result = classify_from_header(header)
        assert result["platform"] == "ILLUMINA"

    def test_pacbio_platform(self):
        """Detect PacBio platform from @RG."""
        header = """@HD\tVN:1.6\tSO:coordinate
@RG\tID:sample1\tPL:PACBIO\tSM:sample1"""
        result = classify_from_header(header)
        assert result["platform"] == "PACBIO"

    def test_ont_platform(self):
        """Detect ONT platform from @RG."""
        header = """@HD\tVN:1.6
@RG\tID:sample1\tPL:ONT\tSM:sample1"""
        result = classify_from_header(header)
        assert result["platform"] == "ONT"

    def test_grch38_from_sq(self):
        """Detect GRCh38 from @SQ AS field."""
        header = """@HD\tVN:1.6
@SQ\tSN:chr1\tLN:248956422\tAS:GRCh38"""
        result = classify_from_header(header)
        assert result["reference_assembly"] == "GRCh38"

    def test_grch37_from_sq(self):
        """Detect GRCh37 from @SQ AS field."""
        header = """@HD\tVN:1.6
@SQ\tSN:1\tLN:249250621\tAS:GRCh37
@SQ\tSN:2\tLN:243199373\tAS:GRCh37"""
        result = classify_from_header(header)
        assert result["reference_assembly"] == "GRCh37"

    def test_star_aligner_rnaseq(self):
        """Detect RNA-seq from STAR aligner in @PG."""
        header = """@HD\tVN:1.6
@PG\tID:STAR\tPN:STAR\tVN:2.7.9a"""
        result = classify_from_header(header)
        assert result["data_modality"] == "transcriptomic.bulk"
        assert result["data_type"] == "alignments"

    def test_bwa_aligner_genomic(self):
        """Detect genomic from BWA aligner."""
        header = """@HD\tVN:1.6
@PG\tID:bwa\tPN:bwa\tVN:0.7.17"""
        result = classify_from_header(header)
        assert result["data_modality"] == "genomic"
        assert result["data_type"] == "alignments"

    def test_pacbio_hifi_readtype(self):
        """Detect PacBio HiFi from READTYPE tag."""
        header = """@HD\tVN:1.6
@RG\tID:sample1\tPL:PACBIO\tDS:READTYPE=CCS"""
        result = classify_from_header(header)
        assert result["platform"] == "PACBIO"
        assert result["data_modality"] == "genomic"
        assert result["assay_type"] == "WGS"

    def test_assay_type_rnaseq(self):
        """Detect RNA-seq assay_type from STAR aligner."""
        header = """@HD\tVN:1.6
@PG\tID:STAR\tPN:STAR\tVN:2.7.9a"""
        result = classify_from_header(header)
        assert result["assay_type"] == "RNA-seq"

    def test_minimap2_long_read(self):
        """Detect long-read alignment from minimap2."""
        header = """@HD\tVN:1.6
@PG\tID:minimap2\tPN:minimap2\tVN:2.24"""
        result = classify_from_header(header)
        # minimap2 is used for long reads (genomic)
        assert result["data_modality"] == "genomic"

    def test_consistency_convergent(self):
        """Test convergent signal boosts confidence."""
        header = """@HD\tVN:1.6
@RG\tID:sample1\tPL:PACBIO\tDS:READTYPE=CCS
@PG\tID:ccs\tPN:ccs\tVN:6.4.0"""
        result = classify_from_header(header)
        # Multiple PacBio indicators should boost confidence
        assert result["confidence"] >= 0.90

    def test_consistency_conflicting(self):
        """Test conflicting signals add warnings."""
        header = """@HD\tVN:1.6
@RG\tID:sample1\tPL:ILLUMINA
@PG\tID:ccs\tPN:ccs\tVN:6.4.0"""
        result = classify_from_header(header)
        # Illumina platform + PacBio CCS program is conflicting
        # Warnings are nested in the consistency dict
        assert len(result["consistency"]["warnings"]) > 0

    def test_empty_header(self):
        """Handle empty header."""
        result = classify_from_header("")
        assert result["confidence"] == 0.0


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_fastq_malformed_reads(self):
        """Handle malformed FASTQ read names."""
        reads = ["not_a_valid_read", "another_invalid", ""]
        result = classify_from_fastq_header(reads)
        assert result["platform"] is None

    def test_vcf_minimal(self):
        """Handle minimal VCF with just column header."""
        header = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"
        result = classify_from_vcf_header(header)
        # Should not crash
        assert "data_modality" in result

    def test_mixed_platform_warning(self):
        """Warn when mixed platforms detected in FASTQ."""
        reads = [
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839",  # Illumina
            "@m64011_190830_220126/1/ccs",              # PacBio
        ]
        result = classify_from_fastq_header(reads)
        assert len(result["warnings"]) > 0
        assert "INCONSISTENCY" in result["warnings"][0]

    def test_unicode_in_header(self):
        """Handle unicode characters in headers."""
        header = """@HD\tVN:1.6
@RG\tID:sample_\u00e9\tPL:ILLUMINA"""
        result = classify_from_header(header)
        assert result["platform"] == "ILLUMINA"
