"""Tests for the header classifier module."""

import pytest

from meta_disco.file_name import FileName
from meta_disco.header_classifier import (
    # Result models
    FastqReadMetadata,
    # Classification functions
    classify_from_fasta_header,
    classify_from_fastq_header,
    classify_from_header,
    classify_from_tar_members,
    classify_from_vcf_header,
    detect_paired_end_indicators,
    # Helper functions
    extract_archive_accession,
    parse_illumina_read_name,
    parse_ont_read_name,
    parse_pacbio_read_name,
)
from meta_disco.models import CLASSIFIED, CONFLICT, NOT_APPLICABLE, NOT_CLASSIFIED, field_status, field_value
from meta_disco.validators.read_name_parsers import IlluminaFormat, PacBioFormat


def val(result: dict, field: str):
    """Extract a classification value (or a derived test aggregate) from output.

    Field values delegate to models.field_value. One test-only pseudo-field is
    derived from the per-field structure:
    - "matched_rules": flattened, de-duplicated rule_ids from all evidence
    """
    if field == "matched_rules" and result.get(field) is None:
        rules = []
        for fld_val in result.values():
            if isinstance(fld_val, dict) and "evidence" in fld_val:
                for e in fld_val["evidence"]:
                    # Synthetic markers carry no rule_id (issue #228); skip them.
                    rid = e.get("rule_id")
                    if rid is not None and rid not in rules:
                        rules.append(rid)
        return rules
    return field_value(result, field)


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================


@pytest.mark.parametrize(
    ("read_name", "accession", "source", "remainder"),
    [
        pytest.param(
            "@ERR3242571.1 A00297:44:HFKH3DSXX:2:1354:30508:28839/1",
            "ERR3242571",
            "ENA",
            "A00297:44:HFKH3DSXX:2:1354:30508:28839/1",
            id="ENA (ERR) accession",
        ),
        pytest.param("@SRR12345678.1 original_read_name", "SRR12345678", "SRA", "original_read_name", id="SRA (SRR)"),
        pytest.param("@DRR000001.1 some_data", "DRR000001", "DDBJ", "some_data", id="DDBJ (DRR)"),
        pytest.param(
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839",
            None,
            None,
            "A00297:44:HFKH3DSXX:2:1354:30508:28839",
            id="no accession in a native read name",
        ),
        pytest.param(
            "ERR3242571.1 A00297:44:HFKH3DSXX:2:1354",
            "ERR3242571",
            "ENA",
            "A00297:44:HFKH3DSXX:2:1354",
            id="read name without the @ prefix",
        ),
        pytest.param("@SRR123.1", "SRR123", "SRA", "", id="accession without an original read name"),
    ],
)
def test_extract_archive_accession(read_name, accession, source, remainder):
    """Archive accession extraction from FASTQ read names."""
    assert extract_archive_accession(read_name) == (accession, source, remainder)


@pytest.mark.parametrize(
    ("read_name", "paired"),
    [
        pytest.param("read_name/1", True, id="/1 suffix"),
        pytest.param("read_name/2", True, id="/2 suffix"),
        pytest.param("sample_R1_001.fastq", True, id="_R1_ pattern"),
        pytest.param("sample_R2_001.fastq", True, id="_R2_ pattern"),
        pytest.param("sample.R1.fastq", True, id=".R1. pattern"),
        pytest.param("sample_r1_001.fastq", True, id="lowercase _r1_"),
        pytest.param("sample.fastq", False, id="no indicator"),
        pytest.param("single_read", False, id="no indicator, no extension"),
    ],
)
def test_detect_paired_end_indicators(read_name, paired):
    """Paired-end indicator detection."""
    assert detect_paired_end_indicators(read_name) is paired


def _assert_parsed(result, expected):
    """Assert the parse matches ``expected``: ``None`` means no parse; otherwise every field
    named in ``expected`` holds the value given, and fields it does not name are not checked.
    """
    if expected is None:
        assert result is None
        return
    assert result is not None
    assert {field: getattr(result, field) for field in expected} == expected


@pytest.mark.parametrize(
    ("read_name", "expected"),
    [
        pytest.param(
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839 1:N:0:ATCACG",
            {
                "format": IlluminaFormat.MODERN,
                "instrument": "A00297",
                "run_number": 44,
                "flowcell": "HFKH3DSXX",
                "lane": 2,
                "tile": 1354,
                "read": 1,
                "filtered": False,
                "index": "ATCACG",
            },
            id="modern format with all fields",
        ),
        pytest.param(
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839",
            {"instrument": "A00297", "read": None},
            id="modern format without the optional second part",
        ),
        pytest.param(
            "@HWUSI-EAS100R:6:73:941:1973#ATCACG/1",
            {"format": IlluminaFormat.LEGACY, "instrument": "HWUSI-EAS100R", "lane": 6, "index": "ATCACG", "read": 1},
            id="legacy format",
        ),
        pytest.param(
            "@ERR3242571.1 A00297:44:HFKH3DSXX:2:1354:30508:28839",
            {"archive_accession": "ERR3242571", "archive_source": "ENA", "instrument": "A00297"},
            id="archive-reformatted read",
        ),
        pytest.param("@m64011_190830/1/ccs", None, id="a PacBio name is not Illumina"),
        pytest.param("random_text", None, id="random text is not Illumina"),
    ],
)
def test_parse_illumina_read_name(read_name, expected):
    """Illumina read name parsing."""
    _assert_parsed(parse_illumina_read_name(read_name), expected)


@pytest.mark.parametrize(
    ("read_name", "expected"),
    [
        pytest.param(
            "@m64011_190830_220126/1/ccs",
            {"format": PacBioFormat.CCS, "movie": "m64011_190830_220126", "zmw": 1, "read_type": "CCS"},
            id="CCS/HiFi read name",
        ),
        pytest.param(
            "@m64011_190830_220126/1234/0_5000",
            {
                "format": PacBioFormat.CLR,
                "movie": "m64011_190830_220126",
                "zmw": 1234,
                "start": 0,
                "end": 5000,
                "read_type": "CLR",
            },
            id="CLR subread name",
        ),
        pytest.param(
            "@m64011_190830_220126/1234", {"format": PacBioFormat.GENERIC, "zmw": 1234}, id="generic PacBio read name"
        ),
        pytest.param(
            "@m64011e_210101_120000/1/ccs", {"movie": "m64011e_210101_120000"}, id="Sequel II movie name with e suffix"
        ),
        pytest.param("@A00297:44:HFKH3DSXX", None, id="an Illumina name is not PacBio"),
    ],
)
def test_parse_pacbio_read_name(read_name, expected):
    """PacBio read name parsing."""
    _assert_parsed(parse_pacbio_read_name(read_name), expected)


@pytest.mark.parametrize(
    ("read_name", "expected"),
    [
        pytest.param(
            "@a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            {"format": "ont", "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"},
            id="UUID read name",
        ),
        pytest.param(
            "@a1b2c3d4-e5f6-7890-abcd-ef1234567890 runid=abc123 read=456 ch=789",
            {
                "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "metadata": {"runid": "abc123", "read": "456", "ch": "789"},
            },
            id="UUID with key=value metadata",
        ),
        pytest.param("@A00297:44:HFKH3DSXX", None, id="an Illumina name is not ONT"),
        pytest.param("not-a-uuid", None, id="a non-UUID is not ONT"),
    ],
)
def test_parse_ont_read_name(read_name, expected):
    """Oxford Nanopore read name parsing."""
    _assert_parsed(parse_ont_read_name(read_name), expected)


# =============================================================================
# FASTQ CLASSIFICATION TESTS
# =============================================================================


class TestFastqReadMetadata:
    """Test the FastqReadMetadata merge into a classification result dict."""

    # The flat scalar keys FastqReadMetadata owns, in the order it writes them.
    SCALAR_KEYS = (
        "is_paired_end",
        "instrument_hint",
        "archive_accession",
        "archive_source",
    )

    def test_empty_metadata_merges_all_none(self):
        """A default (all-None) instance splices four None-valued scalar keys."""
        entries = {"data_type": "reads"}
        FastqReadMetadata().merge_into(entries)
        assert list(entries.keys()) == ["data_type", *self.SCALAR_KEYS]
        for key in self.SCALAR_KEYS:
            assert entries[key] is None

    def test_populated_metadata_merges_values(self):
        """A populated instance splices its field values under the flat keys."""
        entries = {"data_type": "reads"}
        FastqReadMetadata(
            is_paired_end=True,
            instrument_hint="A00297",
            archive_accession="ERR3242571",
            archive_source="ENA",
        ).merge_into(entries)
        assert entries == {
            "data_type": "reads",
            "is_paired_end": True,
            "instrument_hint": "A00297",
            "archive_accession": "ERR3242571",
            "archive_source": "ENA",
        }

    def test_empty_input_path_produces_ten_keys_in_order(self):
        """The empty-reads path returns the six entry keys then the four scalars.

        Asserts insertion order, not just the key set: the output is json-dumped
        to NDJSON and the PR's contract is byte-identical output, so key order is
        part of what must not regress.
        """
        result = classify_from_fastq_header([])
        assert list(result.keys()) == [
            "data_modality",
            "data_type",
            "platform",
            "reference_assembly",
            "assay_type",
            "instrument_model",
            *self.SCALAR_KEYS,
        ]
        for key in self.SCALAR_KEYS:
            assert result[key] is None


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
        assert val(result, "platform") == "ILLUMINA"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED
        assert val(result, "data_type") == "reads"

    @pytest.mark.parametrize(
        "read",
        [
            pytest.param("@A00297:44:HFKH3DSXX:2:1354:30508:28839 1:N:0:ATCACG", id="illumina serial A00297"),
            pytest.param("@m84046_230828_225743_s2/1234/ccs", id="pacbio movie m84046"),
        ],
    )
    def test_a_read_name_serial_does_not_classify_the_instrument_model(self, read):
        """The serial prefix is a vendor numbering convention, not the model (#532).

        The dimension is an entry like the other five, and stays ``not_classified``
        because no rule reads a model from a read name.
        """
        result = classify_from_fastq_header([read])
        assert field_status(result, "instrument_model") == NOT_CLASSIFIED
        assert field_value(result, "instrument_model") is None

    def test_ena_reformatted(self):
        """Classify ENA-reformatted FASTQ with accession extraction."""
        reads = [
            "@ERR3242571.1 A00297:44:HFKH3DSXX:2:1354:30508:28839/1",
            "@ERR3242571.2 A00297:44:HFKH3DSXX:2:1354:30509:28840/1",
        ]
        result = classify_from_fastq_header(reads)
        assert val(result, "platform") == "ILLUMINA"
        assert result["archive_accession"] == "ERR3242571"
        assert result["archive_source"] == "ENA"

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
        assert val(result, "platform") == "ILLUMINA"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED
        assert result["archive_accession"] == "ERR1395578"

    def test_ena_hiseq_2500(self):
        """Classify ENA-reformatted FASTQ with HiSeq 2500 instrument."""
        reads = [
            "@ERR9999999.1 HS2500-1234_100:2:1101:5000:5000/1",
        ]
        result = classify_from_fastq_header(reads)
        assert val(result, "platform") == "ILLUMINA"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED

    def test_pacbio_ccs(self):
        """Classify PacBio CCS/HiFi FASTQ."""
        reads = [
            "@m64011_190830_220126/1/ccs",
            "@m64011_190830_220126/2/ccs",
            "@m64011_190830_220126/3/ccs",
        ]
        result = classify_from_fastq_header(reads)
        assert val(result, "platform") == "PACBIO"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED
        assert val(result, "data_type") == "reads"

    def test_pacbio_clr(self):
        """Classify PacBio CLR FASTQ."""
        reads = [
            "@m64011_190830_220126/1234/0_5000",
            "@m64011_190830_220126/1234/5001_10000",
        ]
        result = classify_from_fastq_header(reads)
        assert val(result, "platform") == "PACBIO"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED

    def test_pacbio_generic(self):
        """Classify generic PacBio FASTQ (movie/zmw without CCS or CLR suffix)."""
        reads = [
            "@m64011_190830_220126/1234",
            "@m64011_190830_220126/5678",
        ]
        result = classify_from_fastq_header(reads)
        assert val(result, "platform") == "PACBIO"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED
        assert val(result, "data_type") == "reads"

    def test_ont_uuid(self):
        """Classify ONT FASTQ by UUID read names only."""
        reads = [
            "@a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "@b2c3d4e5-f6a7-8901-bcde-f12345678901",
        ]
        result = classify_from_fastq_header(reads)
        assert val(result, "platform") == "ONT"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED

    def test_ont_runid(self):
        """Classify ONT FASTQ by runid metadata only."""
        reads = [
            "@somereadname runid=abcdef1234567890abcdef1234567890",
            "@anotherread runid=abcdef1234567890abcdef1234567890",
        ]
        result = classify_from_fastq_header(reads)
        assert val(result, "platform") == "ONT"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED

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
        result = classify_from_fastq_header(reads, name=FileName.parse("sample_R1_001.fastq.gz"))
        assert result["is_paired_end"] is True

    def test_empty_input(self):
        """Handle empty input gracefully."""
        result = classify_from_fastq_header([])
        assert val(result, "platform") is None
        # The empty-input fallback mirrors to_output_dict's Stage 3 shape (#116):
        # sentinels live in `status`, `value` is None unless CLASSIFIED.
        assert "status" in result["data_modality"]
        assert field_status(result, "data_modality") == NOT_CLASSIFIED
        assert field_status(result, "data_type") == CLASSIFIED  # value "reads"
        assert val(result, "data_type") == "reads"
        # #131: empty reads are still unaligned → reference_assembly not_applicable,
        # matching the non-empty fastq path (not not_classified).
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE
        assert val(result, "reference_assembly") is None

    def test_platform_on_agreement(self):
        """Platform should be classified when all reads agree."""
        reads = [
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839",
            "@A00297:44:HFKH3DSXX:2:1354:30509:28840",
            "@A00297:44:HFKH3DSXX:2:1354:30510:28841",
        ]
        result = classify_from_fastq_header(reads)
        # Consistent reads should classify platform as ILLUMINA
        assert val(result, "platform") == "ILLUMINA"


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
        assert val(result, "reference_assembly") == "GRCh38"

    def test_grch37_reference(self):
        """Detect GRCh37/hg19 reference."""
        header = """##fileformat=VCFv4.2
##reference=file:///refs/hg19.fasta
##contig=<ID=1,length=249250621,assembly=GRCh37>
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert val(result, "reference_assembly") == "GRCh37"

    def test_haplotypecaller_germline(self):
        """Detect GATK HaplotypeCaller as germline."""
        header = """##fileformat=VCFv4.2
##source=HaplotypeCaller
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "variants.germline"
        matched = val(result, "matched_rules")
        assert matched is not None and "vcf_gatk_haplotypecaller" in matched

    def test_manta_sv(self):
        """Detect Manta as structural variants."""
        header = """##fileformat=VCFv4.2
##source=Manta
##INFO=<ID=SVTYPE,Number=1,Type=String,Description="Type of structural variant">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "variants.structural"

    def test_sv_info_fields(self):
        """Detect SV from INFO fields."""
        header = """##fileformat=VCFv4.2
##INFO=<ID=SVTYPE,Number=1,Type=String,Description="SV type">
##INFO=<ID=SVLEN,Number=1,Type=Integer,Description="SV length">
##INFO=<ID=END,Number=1,Type=Integer,Description="End position">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "variants.structural"

    def test_empty_header(self):
        """Handle minimal VCF header."""
        header = """##fileformat=VCFv4.2
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        # Should still produce a well-formed result
        assert "data_modality" in result

    def test_real_filename_drives_reference_rule(self):
        """The real file_name feeds the filename rules — a header with no
        ##contig lengths still resolves CHM13 from a chm13 token in the name
        (#152). Before the fix the classifier synthesized `sample.vcf.gz`."""
        header = """##fileformat=VCFv4.2
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header, name=FileName.parse("1kgp.chr20.chm13.vcf.gz"))
        assert val(result, "reference_assembly") == "CHM13"


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
        assert val(result, "platform") == "ILLUMINA"

    def test_pacbio_platform(self):
        """Detect PacBio platform from @RG."""
        header = """@HD\tVN:1.6\tSO:coordinate
@RG\tID:sample1\tPL:PACBIO\tSM:sample1"""
        result = classify_from_header(header)
        assert val(result, "platform") == "PACBIO"

    def test_ont_platform(self):
        """Detect ONT platform from @RG."""
        header = """@HD\tVN:1.6
@RG\tID:sample1\tPL:ONT\tSM:sample1"""
        result = classify_from_header(header)
        assert val(result, "platform") == "ONT"

    @pytest.mark.parametrize(
        ("pl", "pm", "model"),
        [
            pytest.param("PACBIO", "REVIO", "Revio", id="REVIO names Revio"),
            pytest.param("PACBIO", "SEQUEL", "Sequel", id="SEQUEL names the first Sequel"),
            pytest.param("ILLUMINA", "NovaSeq X", "Illumina NovaSeq X", id="NovaSeq X"),
            pytest.param("PACBIO", "SEQUELII", None, id="SEQUELII is Sequel II or IIe"),
            pytest.param("ILLUMINA", "NovaSeq", None, id="NovaSeq is a family"),
            pytest.param("ILLUMINA", "NovaSeq X Plus", None, id="NovaSeq X Plus is not NovaSeq X"),
            pytest.param("ILLUMINA", "Unknown", None, id="Unknown names nothing"),
            pytest.param("ONT", "1A", None, id="an ONT flow-cell position is not a model"),
        ],
    )
    def test_instrument_model_from_rg_pm(self, pl, pm, model):
        """@RG PM claims a model only where the whole value names exactly one (#532)."""
        header = f"@HD\tVN:1.6\n@RG\tID:rg1\tPL:{pl}\tPM:{pm}\tSM:s"
        result = classify_from_header(header)
        assert field_value(result, "instrument_model") == model
        assert field_status(result, "instrument_model") == (CLASSIFIED if model else NOT_CLASSIFIED)

    def test_grch38_from_sq(self):
        """Detect GRCh38 from @SQ AS field."""
        header = """@HD\tVN:1.6
@SQ\tSN:chr1\tLN:248956422\tAS:GRCh38"""
        result = classify_from_header(header)
        assert val(result, "reference_assembly") == "GRCh38"

    def test_grch37_from_sq(self):
        """Detect GRCh37 from @SQ AS field."""
        header = """@HD\tVN:1.6
@SQ\tSN:1\tLN:249250621\tAS:GRCh37
@SQ\tSN:2\tLN:243199373\tAS:GRCh37"""
        result = classify_from_header(header)
        assert val(result, "reference_assembly") == "GRCh37"

    def test_star_aligner_rnaseq(self):
        """Detect RNA-seq from STAR aligner in @PG."""
        header = """@HD\tVN:1.6
@PG\tID:STAR\tPN:STAR\tVN:2.7.9a"""
        result = classify_from_header(header)
        assert val(result, "data_modality") == "transcriptomic.bulk"
        assert val(result, "data_type") == "alignments"

    def test_bwa_aligner_genomic(self):
        """Detect genomic from BWA aligner."""
        header = """@HD\tVN:1.6
@PG\tID:bwa\tPN:bwa\tVN:0.7.17"""
        result = classify_from_header(header)
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "alignments"

    def test_readtype_ccs_no_modality_inference(self):
        """READTYPE=CCS no longer implies genomic — modality left to other signals."""
        header = """@HD\tVN:1.6
@RG\tID:sample1\tPL:PACBIO\tDS:READTYPE=CCS"""
        result = classify_from_header(header)
        assert val(result, "platform") == "PACBIO"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED
        assert field_status(result, "assay_type") == NOT_CLASSIFIED

    def test_ont_basecall_dna_modality(self):
        """ONT basecall_model=dna_* implies genomic modality."""
        header = """@HD\tVN:1.6
@RG\tID:sample1\tPL:ONT\tDS:basecall_model=dna_r10.4.1_e8.2_400bps_sup@v4.3.0"""
        result = classify_from_header(header)
        assert val(result, "platform") == "ONT"
        assert val(result, "data_modality") == "genomic"

    def test_ont_basecall_dna_legacy(self):
        """Legacy Guppy basecall model with date prefix still detected as genomic."""
        header = """@HD\tVN:1.6
@RG\tID:sample1\tPL:ONT\tDS:runid=92ad6c38 basecall_model=2021-05-05_dna_r9.4.1_promethion_768_922a514b"""
        result = classify_from_header(header)
        assert val(result, "platform") == "ONT"
        assert val(result, "data_modality") == "genomic"

    def test_assay_type_rnaseq(self):
        """Detect RNA-seq assay_type from STAR aligner."""
        header = """@HD\tVN:1.6
@PG\tID:STAR\tPN:STAR\tVN:2.7.9a"""
        result = classify_from_header(header)
        assert val(result, "assay_type") == "RNA-seq"

    def test_minimap2_long_read(self):
        """Detect long-read alignment from minimap2."""
        header = """@HD\tVN:1.6
@PG\tID:minimap2\tPN:minimap2\tVN:2.24"""
        result = classify_from_header(header)
        # minimap2 is used for long reads (genomic)
        assert val(result, "data_modality") == "genomic"

    def test_pacbio_platform_with_ccs_program(self):
        """PacBio platform + CCS program both confirm PACBIO."""
        header = """@HD\tVN:1.6
@RG\tID:sample1\tPL:PACBIO
@PG\tID:ccs\tPN:ccs\tVN:6.4.0"""
        result = classify_from_header(header)
        assert val(result, "platform") == "PACBIO"

    def test_illumina_platform_with_ccs_program_conflict(self):
        """Illumina platform + PacBio CCS program = platform conflict (#88)."""
        header = """@HD\tVN:1.6
@RG\tID:sample1\tPL:ILLUMINA
@PG\tID:ccs\tPN:ccs\tVN:6.4.0"""
        result = classify_from_header(header)
        assert field_status(result, "platform") == CONFLICT

    def test_empty_header(self):
        """Handle empty header — treated as unaligned."""
        result = classify_from_header("")
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE

    def test_real_filename_drives_tier2_rule(self):
        """The real file_name feeds the filename rules — a header carrying no
        modality signal still classifies IsoSeq from the name (#152). Before the
        fix the classifier synthesized `sample.bam` and dropped the name."""
        header = "@HD\tVN:1.6"
        result = classify_from_header(header, name=FileName.parse("sample.flnc.bam"))
        assert val(result, "data_modality") == "transcriptomic.bulk"
        assert val(result, "data_type") == "alignments"

    def test_real_filename_recovers_pacbio_platform(self):
        """A hifi filename recovers platform even when the header names none —
        the ~110-file platform bucket in #152."""
        header = "@HD\tVN:1.6"
        result = classify_from_header(header, name=FileName.parse("HG02055.paternal.hifi.bam"))
        assert val(result, "platform") == "PACBIO"

    def test_header_signal_not_clobbered_by_filename(self):
        """A header aligner signal must still win where the filename is silent —
        the fix adds filename coverage, it does not displace header rules (#152)."""
        header = """@HD\tVN:1.6
@PG\tID:STAR\tPN:STAR\tVN:2.7.9a"""
        result = classify_from_header(header, name=FileName.parse("sample.bam"))
        assert val(result, "data_modality") == "transcriptomic.bulk"


# =============================================================================
# EDGE CASES
# =============================================================================


class TestContigLengthDetection:
    """Test reference assembly detection from contig lengths.

    Both classifiers pass their parsed contigs — @SQ SN/LN for BAM, ##contig
    ID/length for VCF — to detect_reference_from_contigs(), which matches them
    against known chromosome sizes. VCF additionally has rule-based pattern
    matching on ##contig assembly= and ##reference= fields.
    """

    def test_bam_sq_standard_order(self):
        """Detect GRCh38 from BAM @SQ lines with SN before LN."""
        header = "@HD\tVN:1.6\tSO:coordinate\n"
        header += "@SQ\tSN:chr1\tLN:248956422\n"
        header += "@SQ\tSN:chr2\tLN:242193529\n"
        header += "@SQ\tSN:chr3\tLN:198295559\n"
        header += "@SQ\tSN:chr10\tLN:133797422\n"
        header += "@SQ\tSN:chr22\tLN:50818468"
        result = classify_from_header(header)
        assert val(result, "reference_assembly") == "GRCh38"

    def test_bam_sq_reordered_tags(self):
        """Detect GRCh38 from BAM @SQ lines with LN before SN."""
        header = "@HD\tVN:1.6\tSO:coordinate\n"
        header += "@SQ\tLN:248956422\tSN:chr1\n"
        header += "@SQ\tLN:242193529\tSN:chr2\n"
        header += "@SQ\tLN:198295559\tSN:chr3\n"
        header += "@SQ\tLN:133797422\tSN:chr10\n"
        header += "@SQ\tLN:50818468\tSN:chr22"
        result = classify_from_header(header)
        assert val(result, "reference_assembly") == "GRCh38"

    def test_bam_sq_extra_tags(self):
        """Detect GRCh38 from BAM @SQ with extra tags between SN and LN."""
        header = "@HD\tVN:1.6\tSO:coordinate\n"
        header += "@SQ\tSN:chr1\tM5:abc123\tLN:248956422\n"
        header += "@SQ\tSN:chr2\tM5:def456\tLN:242193529\n"
        header += "@SQ\tSN:chr3\tM5:ghi789\tLN:198295559\n"
        header += "@SQ\tSN:chr10\tM5:jkl012\tLN:133797422\n"
        header += "@SQ\tSN:chr22\tM5:mno345\tLN:50818468"
        result = classify_from_header(header)
        assert val(result, "reference_assembly") == "GRCh38"

    def test_bam_sq_chm13(self):
        """Detect CHM13 from BAM @SQ contig lengths."""
        header = "@HD\tVN:1.6\tSO:coordinate\n"
        header += "@SQ\tSN:chr1\tLN:248387497\n"
        header += "@SQ\tSN:chr2\tLN:242696747\n"
        header += "@SQ\tSN:chr3\tLN:201106605\n"
        header += "@SQ\tSN:chr10\tLN:134758134\n"
        header += "@SQ\tSN:chr22\tLN:51324926"
        result = classify_from_header(header)
        assert val(result, "reference_assembly") == "CHM13"

    def test_bam_sq_single_contig_identifies_assembly(self):
        """A single contig with exact length match definitively identifies assembly."""
        # chr22 length 50818468 is unique to GRCh38 (CHM13=51324926, GRCh37=51304566)
        header = "@HD\tVN:1.6\tSO:coordinate\n"
        header += "@SQ\tSN:chr22\tLN:50818468"
        result = classify_from_header(header)
        assert val(result, "reference_assembly") == "GRCh38"

    def test_bam_sq_clear_winner(self):
        """When one assembly clearly wins by vote count, return it."""
        # All 5 reference chromosomes with GRCh38 lengths
        header = "@HD\tVN:1.6\tSO:coordinate\n"
        header += "@SQ\tSN:chr1\tLN:248956422\n"
        header += "@SQ\tSN:chr2\tLN:242193529\n"
        header += "@SQ\tSN:chr3\tLN:198295559\n"
        header += "@SQ\tSN:chr10\tLN:133797422\n"
        header += "@SQ\tSN:chr22\tLN:50818468"
        result = classify_from_header(header)
        assert val(result, "reference_assembly") == "GRCh38"

    def test_vcf_contig_with_assembly_tag(self):
        """VCF ##contig assembly= is matched via contig pattern rules."""
        header = """##fileformat=VCFv4.2
##contig=<ID=chr1,assembly=GRCh38,length=248956422>
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        # Currently assembly= in contig is matched by vcf_contig_assembly rules
        # The ##reference line is the primary detection path
        assert (
            val(result, "reference_assembly") == "GRCh38"
            or field_status(result, "reference_assembly") == NOT_CLASSIFIED
        )

    def test_vcf_reference_field(self):
        """VCF reference detection from ##reference= line."""
        header = """##fileformat=VCFv4.2
##reference=file:///refs/GRCh38.fasta
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"""
        result = classify_from_vcf_header(header)
        assert val(result, "reference_assembly") == "GRCh38"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_fastq_malformed_reads(self):
        """Handle malformed FASTQ read names."""
        reads = ["not_a_valid_read", "another_invalid", ""]
        result = classify_from_fastq_header(reads)
        assert field_status(result, "platform") == NOT_CLASSIFIED

    def test_vcf_minimal(self):
        """Handle minimal VCF with just column header."""
        header = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO"
        result = classify_from_vcf_header(header)
        # Should not crash
        assert "data_modality" in result

    def test_mixed_platform_first_read(self):
        """Classify based on first read when multiple platforms present."""
        reads = [
            "@A00297:44:HFKH3DSXX:2:1354:30508:28839",  # Illumina
            "@m64011_190830_220126/1/ccs",  # PacBio
        ]
        result = classify_from_fastq_header(reads)
        # Should classify based on first read (Illumina)
        assert val(result, "platform") == "ILLUMINA"

    def test_unicode_in_header(self):
        """Handle unicode characters in headers."""
        header = """@HD\tVN:1.6
@RG\tID:sample_\u00e9\tPL:ILLUMINA"""
        result = classify_from_header(header)
        assert val(result, "platform") == "ILLUMINA"


class TestTarClassifier:
    """classify_from_tar_members: classify a tar archive by its contents (#255)."""

    def test_genomicsdb_store_from_schema_files(self):
        """A GenomicsDB store recognized by its schema files (the common case)."""
        members = ["./chr22.1_2/vidmap.json", "./chr22.1_2/callset.json", "./chr22.1_2/vcfheader.vcf"]
        result = classify_from_tar_members(members)
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "variants"

    def test_genomicsdb_store_from_vcf_field_arrays_only(self):
        """A large store whose schema files are past the head is still caught by its
        VCF-attribute TileDB arrays (e.g. PL/GQ/DP_FORMAT), incl. the `_var` pairs."""
        members = [
            "./chr4.1_2/chr4$1$2/__coords.tdb",
            "./chr4.1_2/chr4$1$2/PL.tdb",
            "./chr4.1_2/chr4$1$2/DP_FORMAT.tdb",
            "./chr4.1_2/chr4$1$2/MLEAC_var.tdb",
        ]
        result = classify_from_tar_members(members)
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "variants"

    def test_genomicsdb_array_name_in_mid_path_is_caught(self):
        """A TileDB array is a directory (`PL.tdb/`), so the variant-array name is a
        mid-path segment; when the directory entry itself is omitted, only the deeper
        files remain — the all-segments check still recognizes it."""
        members = [
            "chr4.1_2/chr4$1$2/PL.tdb/__array_schema.tdb",
            "chr4.1_2/chr4$1$2/PL.tdb/__fragment/a.tdb",
        ]
        result = classify_from_tar_members(members)
        assert val(result, "data_type") == "variants"

    def test_bare_tiledb_is_not_called_variants(self):
        """Honesty: a `.tdb` is a *generic* TileDB array — a head of only generic TileDB
        structure files (no schema, no VCF-field array) is not read as variants."""
        members = ["store/__tiledb_workspace.tdb", "store/__array_schema.tdb", "store/__coords.tdb"]
        result = classify_from_tar_members(members)
        assert field_status(result, "data_type") == NOT_CLASSIFIED
        assert field_status(result, "data_modality") == NOT_CLASSIFIED

    def test_generic_dominant_inner_extension(self):
        """A tar of FASTA members → the inner format's classification (sequence)."""
        result = classify_from_tar_members(["asm/hap1.fasta", "asm/hap2.fasta", "asm/readme.txt"])
        assert val(result, "data_type") == "sequence"

    def test_unrecognized_contents_stay_not_classified(self):
        """Read it, but no GenomicsDB signal and no recognized inner extension → not_classified."""
        result = classify_from_tar_members(["blob/x.dat", "blob/y.bin"])
        assert field_status(result, "data_type") == NOT_CLASSIFIED

    def test_empty_member_list_is_not_classified(self):
        """A non-tar / empty head read as no members → not_classified, not a crash."""
        result = classify_from_tar_members([])
        assert field_status(result, "data_type") == NOT_CLASSIFIED


# =============================================================================
# FASTA CONTIG CLASSIFICATION
# =============================================================================


class TestFastaContigClassification:
    """classify_from_fasta_header: classify a FASTA by the contig names in its head.

    These cases used to live in ``test_evals.TestFastaE2E``, pinned to real files. No
    fixture in the anvil15 catalog can reproduce their contig lists: every FASTA in it is
    a whole-genome file of 773 MB or more, and a 256 KiB head of one yields exactly one
    contig (971 of the 973 cached FASTA evidence records hold a single name; the other
    two hold two). The catalog does still contain reference genomes — what it cannot
    supply through the fetch path is the multi-contig head they would need. So the shapes
    below are driven directly instead (#381).

    The mitochondrial contig counts and exemplar names are real, recovered from the
    ``output/anvil/20260321_002155`` run, which classified those files before they left
    the corpus; the siblings follow each exemplar's own naming pattern.
    """

    # A whole-genome reference's primary chromosomes. Every assembly in
    # REFERENCE_CONTIG_LENGTHS shares these names, so a filename signal is what
    # separates them — which is exactly what the first two tests exercise.
    REFERENCE_CHROMOSOMES = [f"chr{n}" for n in range(1, 23)] + ["chrX", "chrY", "chrM"]

    def test_grch38_reference_genome(self):
        """Reference chromosomes plus a GRCh38 filename → a GRCh38 reference genome.

        Replaces the e2e fixture grch38.XX.fasta. This exercises the classifier only: the
        ``>= 20`` reference-contig threshold it depends on cannot be met by any file the
        pipeline classifies today, because a 256 KiB head of a whole-genome FASTA yields
        one contig (#382). Passing here is not evidence the production path works.
        """
        result = classify_from_fasta_header(self.REFERENCE_CHROMOSOMES, name=FileName.parse("grch38.XX.fasta"))
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "assembly.reference"
        assert val(result, "reference_assembly") == "GRCh38"
        assert field_status(result, "assay_type") == NOT_APPLICABLE

    def test_chm13_reference_genome(self):
        """The same chromosomes with a CHM13 filename → a CHM13 reference genome.

        Replaces the e2e fixture chm13v2.0.fasta; unreachable in production for the same
        reason as the GRCh38 case above (#382).
        """
        result = classify_from_fasta_header(self.REFERENCE_CHROMOSOMES, name=FileName.parse("chm13v2.0.fasta"))
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "assembly.reference"
        assert val(result, "reference_assembly") == "CHM13"
        assert field_status(result, "assay_type") == NOT_APPLICABLE

    def test_reference_contigs_without_a_filename_signal_stay_ambiguous(self):
        """Honesty: the contigs say "a reference", but not which one.

        GRCh37, GRCh38 and CHM13 all use these chromosome names, so with no filename to
        break the tie the file is still a reference genome — the data_type claim stands —
        while reference_assembly is left unclassified rather than guessed.
        """
        result = classify_from_fasta_header(self.REFERENCE_CHROMOSOMES, name=FileName.parse("unnamed.fasta"))
        assert val(result, "data_type") == "assembly.reference"
        assert field_status(result, "reference_assembly") == NOT_CLASSIFIED

    def test_verkko_mito_contigs(self):
        """12 verkko-named contigs → de novo assembly, no reference.

        Replaces the e2e fixture HG002_verkko_gfase_mito.fasta.gz (38 KB); the exemplar
        haplotype1-0000068 is its recorded contig name.
        """
        contigs = [f"haplotype1-{n:07d}" for n in range(68, 80)]
        result = classify_from_fasta_header(contigs, name=FileName.parse("HG002_verkko_gfase_mito.fasta.gz"))
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "assembly"
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE

    def test_hifiasm_mito_contigs(self):
        """7 hifiasm-named contigs → de novo assembly, no reference.

        Replaces the e2e fixture HG002.hifiasm_0.19.0_trio.diploid.mito.fa.gz (26 KB);
        the exemplar h1tg000083l is its recorded contig name.
        """
        contigs = [f"h1tg0000{n}l" for n in range(83, 90)]
        result = classify_from_fasta_header(
            contigs, name=FileName.parse("HG002.hifiasm_0.19.0_trio.diploid.mito.fa.gz")
        )
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "assembly"
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE

    def test_single_assembler_contig(self):
        """One assembler contig is enough to call de novo assembly.

        Replaces the e2e fixture HG02809_verkko_asm_mito_exemplar.fasta.gz (3.5 KB);
        mat-0000222 is its recorded contig name.
        """
        result = classify_from_fasta_header(
            ["mat-0000222"], name=FileName.parse("HG02809_verkko_asm_mito_exemplar.fasta.gz")
        )
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "assembly"
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE

    def test_verkko_diploid_assembly(self):
        """A verkko diploid assembly, classified from its contig naming.

        Replaces the e2e fixture HG02300_verkko_gfase_diploid.fasta.gz.
        """
        result = classify_from_fasta_header(
            ["haplotype1-0000001", "haplotype2-0000001"],
            name=FileName.parse("HG02300_verkko_gfase_diploid.fasta.gz"),
        )
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "assembly"
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE

    def test_no_contigs_falls_back_to_the_filename(self):
        """An empty contig list is a readable result, not a failure: the filename rules
        still classify the file, and no content claim is invented on top of them.

        Replaces the e2e fixture HG02647.hifiasm_0.19.3_hic.diploid.mito.fa.gz — a valid
        20-byte gzip whose decompressed content holds no header line. The name is the
        catalog's own `f1_assembly_v2` form now, since the assembler-name alternatives
        matched nothing in either catalog and were dropped (#430).
        """
        result = classify_from_fasta_header([], name=FileName.parse("HG02647.f1_assembly_v2.mito.fa.gz"))
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "assembly"
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE
        # Nothing was read, so none of the three content classifiers may have claimed.
        content_rules = {"fasta_reference_contigs", "fasta_assembler_contigs", "fasta_transcript_contigs"}
        matched = val(result, "matched_rules")
        assert matched is not None and content_rules.isdisjoint(matched)


class TestAVcfHeaderIsParsedOnce:
    """The VCF classifier parses the header once, on file_info, and the rule engine,
    the contig-length detector and the build resolver all read that parse (#488).
    Before, the engine and the resolver each parsed and the detector re-split the
    raw text: three passes over every header in the corpus."""

    def test_one_parse_per_classification(self, monkeypatch):
        from meta_disco.validators import header_extractors, reference_builds

        real = header_extractors.parse_vcf_header
        calls = []

        def counting(text):
            calls.append(text)
            return real(text)

        # Patched at every site that bound the name: the engine imports it at call
        # time, but reference_builds bound it at import, so a resolver that parsed
        # again would be invisible to a patch on header_extractors alone.
        monkeypatch.setattr(header_extractors, "parse_vcf_header", counting)
        monkeypatch.setattr(reference_builds, "parse_vcf_header", counting)
        header = (
            "##fileformat=VCFv4.2\n##source=HaplotypeCaller\n##reference=file:///ref/hg38.fa\n"
            '##contig=<ID=chr1,length=248956422>\n##INFO=<ID=DP,Number=1,Type=Integer,Description="depth">\n'
        )
        result = classify_from_vcf_header(header, name=FileName.parse("sample.vcf.gz"))
        assert result["reference_assembly"]["value"] == "GRCh38"
        assert result["data_type"]["value"] == "variants.germline"
        assert len(calls) == 1
