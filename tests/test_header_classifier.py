"""Tests for the header classifier module."""

import importlib
from collections.abc import Mapping
from types import MappingProxyType

import pytest

from meta_disco import callers, code_rules
from meta_disco.cohort_steps import parse_tar_head
from meta_disco.evidence import TarHead, VcfHead
from meta_disco.file_name import FileName
from meta_disco.header_classifier import (
    NO_WORKSPACE_HEADER,
    WORKSPACE_HEADER_UNREADABLE,
    # Result models
    FastqReadMetadata,
    # Classification functions
    classify_from_fasta_header,
    classify_from_fastq_header,
    classify_from_header,
    classify_from_tar_head,
    classify_from_vcf_header,
    detect_paired_end_indicators,
    # Helper functions
    extract_archive_accession,
    parse_illumina_read_name,
    parse_ont_read_name,
    parse_pacbio_read_name,
)
from meta_disco.models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    CONFLICT,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_CONTENT_READ,
    field_evidence,
    field_status,
    field_value,
)
from meta_disco.rule_engine import CONTENT_TIER
from meta_disco.validators.header_extractors import VCFHeader, parse_vcf_head, parse_vcf_header
from meta_disco.validators.read_name_parsers import IlluminaFormat, PacBioFormat
from tests.test_producer_steps import GATK3_HC, HC, IMPORT, gatk4, header_text


def vcf_head(text: str, alts) -> VCFHeader:
    """The header ``text`` parsed, with one record of chr1 per ALT in ``alts``."""
    lines = [f"chr1\t{pos}\t.\tA\t{alt}\t.\tPASS\t." for pos, alt in enumerate(alts, 1)]
    return parse_vcf_head(VcfHead(text, lines))


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


@pytest.mark.parametrize(
    "module", ["meta_disco.header_classifier", "meta_disco.validators", "meta_disco.validators.read_name_parsers"]
)
def test_importing_the_removed_prefix_guess_says_why(module):
    """The break is explicit: the ImportError names #532 rather than a bare missing name."""
    with pytest.raises(ImportError, match="removed in #532"):
        importlib.import_module(module).infer_illumina_instrument_model  # noqa: B018  the access is the test


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
        """The empty-reads path returns the dimension entries then the four scalars.

        Asserts insertion order, not just the key set: the output is json-dumped
        to NDJSON and the PR's contract is byte-identical output, so key order is
        part of what must not regress.
        """
        result = classify_from_fastq_header([])
        assert list(result.keys()) == [*CLASSIFICATION_FIELDS, *self.SCALAR_KEYS]
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

    @pytest.mark.parametrize(
        ("contigs", "reference"),
        [
            # The heads of a hg19 and a hg38 ANVIL_1000G_PRIMED .pvar (#561), first contigs.
            ("##contig=<ID=1,assembly=b37,length=249250621>\n##contig=<ID=2,assembly=b37,length=243199373>", "GRCh37"),
            ("##contig=<ID=1,length=248956422>\n##contig=<ID=2,length=242193529>", "GRCh38"),
        ],
    )
    def test_a_pvar_takes_its_reference_from_its_vcf_style_header_and_stays_genotypes(self, contigs, reference):
        """A PLINK 2 .pvar written from a VCF keeps the VCF's ## header: its contig lengths give
        the reference, and its data_type is the PLINK extension rule's, not a VCF's (#561)."""
        header = f"{contigs}\n#CHROM\tPOS\tID\tREF\tALT"
        result = classify_from_vcf_header(header, name=FileName.parse("ACB.1.pvar"))
        assert val(result, "reference_assembly") == reference
        assert (val(result, "data_type"), val(result, "data_modality")) == ("genotypes", "genomic")

    def test_an_sv_callers_kind_is_variant_kinds_and_its_data_type_is_its_columns(self):
        """The caller gives a callset's kind, never its data_type (#657), which its sample columns give (#655)."""
        text = "##fileformat=VCFv4.2\n##source=Sniffles2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tHG002"
        result = classify_from_vcf_header(vcf_head(text, ["<DEL>", "<INS>"]), name=FileName.parse("HG002.sv.vcf.gz"))
        assert val(result, "data_type") == "variants.single_sample"
        assert val(result, "variant_kind") == "structural"

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
            pytest.param("PACBIO", "SEQUEL", None, id="SEQUEL is not shown to name one model"),
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

    def test_read_groups_naming_two_models_name_neither(self):
        """A BAM merged from runs on two instruments gets no model (#532)."""
        header = "@HD\tVN:1.6\n@RG\tID:a\tPL:PACBIO\tPM:SEQUELII\n@RG\tID:b\tPL:PACBIO\tPM:REVIO"
        result = classify_from_header(header)
        assert field_status(result, "instrument_model") == NOT_CLASSIFIED

    def test_a_read_group_without_pm_leaves_the_model_unknown(self):
        """A second read group that gives no PM could be any instrument (#532)."""
        header = "@HD\tVN:1.6\n@RG\tID:a\tPL:PACBIO\tPM:REVIO\n@RG\tID:b\tPL:PACBIO"
        assert field_status(classify_from_header(header), "instrument_model") == NOT_CLASSIFIED

    def test_every_read_group_naming_one_model_names_it(self):
        header = "@HD\tVN:1.6\n@RG\tID:a\tPL:PACBIO\tPM:REVIO\n@RG\tID:b\tPL:PACBIO\tPM:REVIO"
        assert field_value(classify_from_header(header), "instrument_model") == "Revio"

    @pytest.mark.parametrize(("pm", "platform"), [("REVIO", "PACBIO"), ("NovaSeq X", "ILLUMINA")])
    def test_a_pm_model_declares_its_platform_without_pl(self, pm, platform):
        """The model implies the platform, so a header with PM and no PL still has one."""
        result = classify_from_header(f"@HD\tVN:1.6\n@RG\tID:rg1\tPM:{pm}\tSM:s")
        assert field_value(result, "platform") == platform

    @pytest.mark.parametrize(
        ("command", "platform"),
        [
            pytest.param(
                "winnowmap -W ref_k15 -w 50 -k 15 -t 48 -x map-ont -a --MD ref.fasta r.fastq",
                "ONT",
                id="winnowmap map-ont",
            ),
            pytest.param(
                "winnowmap -W rep.txt -ax map-pb -t 16 --MD ref.fa r.fastq", "PACBIO", id="winnowmap -ax map-pb"
            ),
            pytest.param("/opt/bin/minimap2 -ax map-pb ref.fa r.fq", "PACBIO", id="minimap2 map-pb, with a path"),
            pytest.param("minimap2 -ax map-hifi ref.fa hifi.fq", None, id="map-hifi may be ONT duplex too"),
            pytest.param("minimap2 -xmap-ont ref.fa r.fq", "ONT", id="preset joined to -x"),
            pytest.param("winnowmap -W r.txt -ax map-pb-clr ref.fa r.fq", "PACBIO", id="winnowmap map-pb-clr"),
            pytest.param("minimap2 -aX map-ont ref.fa r.fq", None, id="-X is another flag, not the preset"),
            pytest.param("minimap2 -aYx map-ont ref.fa r.fq", "ONT", id="an upper-case flag grouped before -x"),
            pytest.param("minimap2 -Hax map-pb ref.fa r.fq", "PACBIO", id="-H grouped before -ax"),
            pytest.param("minimap2 -ax asm5 ref.fa asm.fa", None, id="an assembly preset names no platform"),
            pytest.param("minimap2 -ax sr ref.fa r1.fq r2.fq", None, id="sr names no platform"),
            pytest.param("minimap2 -ax splice ref.fa r.fq", None, id="splice names no platform"),
            pytest.param("minimap2 -ax map-ontology ref.fa r.fq", None, id="a longer word is no preset"),
            pytest.param("mytool -x map-ont ref.fa r.fq", None, id="another tool's -x is not read"),
            pytest.param("mytool --aligner minimap2 -x map-ont ref.fa r.fq", None, id="minimap2 named mid-line"),
            pytest.param("minimap2.py -x map-ont ref.fa r.fq", None, id="another program named like minimap2"),
            pytest.param("samtools view -H x.bam", None, id="no aligner and no preset"),
        ],
    )
    def test_platform_from_the_aligner_read_preset(self, command, platform):
        """A minimap2/Winnowmap read preset on an @PG line names the reads' platform (#727)."""
        header = f"@HD\tVN:1.6\n@PG\tID:aln\tPN:aligner\tCL:{command}\n@PG\tID:samtools\tPN:samtools\tCL:samtools sort"
        result = classify_from_header(header)
        assert field_value(result, "platform") == platform
        assert field_status(result, "platform") == (CLASSIFIED if platform else NOT_CLASSIFIED)

    def test_a_cram_reads_the_preset_too(self):
        """The rules apply to a CRAM's header as to a BAM's (#727)."""
        header = "@HD\tVN:1.6\n@PG\tID:aln\tPN:minimap2\tCL:minimap2 -ax map-ont ref.fa r.fq"
        result = classify_from_header(header, name=FileName.parse("sample.cram"))
        assert field_value(result, "platform") == "ONT"

    def test_two_read_presets_in_one_header_conflict(self):
        """ONT and PacBio presets in one header are not settled by either (#727)."""
        header = (
            "@HD\tVN:1.6\n@PG\tID:a\tPN:minimap2\tCL:minimap2 -ax map-ont ref.fa r.fq\n"
            "@PG\tID:b\tPN:minimap2\tCL:minimap2 -ax map-pb ref.fa r.fq"
        )
        assert field_status(classify_from_header(header), "platform") == CONFLICT

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
        assert val(result, "data_modality") == "transcriptomic"

    def test_bwa_aligner_genomic(self):
        """Detect genomic from BWA aligner."""
        header = """@HD\tVN:1.6
@PG\tID:bwa\tPN:bwa\tVN:0.7.17"""
        result = classify_from_header(header)
        assert val(result, "data_modality") == "genomic"

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
        assert val(result, "data_modality") == "transcriptomic"

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
        assert val(result, "data_modality") == "transcriptomic"


class TestAlignedOrUnaligned:
    """`@SQ` alone decides `data_type`: none means reads, some means alignments (#537)."""

    # m64136_210522_014758.hifi_reads.bam: PacBio's CCS output, never aligned.
    HIFI_READS = (
        "@HD\tVN:1.5\tSO:unknown\tpb:3.0.1\n"
        "@RG\tID:1c979136\tPL:PACBIO\tDS:READTYPE=CCS;BINDINGKIT=101-894-200\tPU:m64136_210522_014758\tPM:SEQUELII\n"
        "@PG\tID:ccs-6.0.0\tPN:ccs\tVN:6.0.0\n"
        "@PG\tID:pbmerge-1.6.1\tPN:pbmerge\tVN:1.6.1"
    )
    # Guppy mod-base BAM: Guppy writes a minimap2 `@PG` whether or not it aligned.
    GUPPY_MODBASE = (
        "@HD\tVN:1.6\tSO:coordinate\n"
        "@RG\tID:0017e8d0_2021-05-05_dna_r9.4.1_promethion_768_922a514b\t"
        "DS:runid=0017e8d0 basecall_model=2021-05-05_dna_r9.4.1_promethion_768_922a514b\tPL:ONT\n"
        "@PG\tID:aligner\tPN:minimap2\tVN:2.24-r1122\n"
        "@PG\tID:basecaller\tPN:guppy\tVN:6.4.6+ae70e8f"
    )
    # NA19682.lymph.m84203_…_s4.flnc.bam: Kinnex Iso-Seq full-length reads.
    KINNEX_FLNC = (
        "@HD\tVN:1.6\tSO:coordinate\tpb:5.0.0\n"
        "@RG\tID:70ec1597/2--12\tPL:PACBIO\tDS:READTYPE=SEGMENT;SOURCE=CCS\n"
        "@PG\tID:ccs\tPN:ccs\tVN:8.0.1 (commit v8.0.1)\n"
        "@PG\tID:refine\tVN:4.1.2 (commit v4.1.2)"
    )
    # HG00438.f1_assembly_v2.hap1.bam: an assembly aligned to GRCh38 with minimap2.
    ALIGNED_MINIMAP2 = (
        "@HD\tVN:1.6\tSO:coordinate\n"
        "@SQ\tSN:chr1\tLN:248956422\n"
        "@SQ\tSN:chr2\tLN:242193529\n"
        "@PG\tID:minimap2\tPN:minimap2\tVN:2.17-r941\tCL:minimap2 -a -xasm5 --cs -r2k -t8 "
        "GCA_000001405.15_GRCh38_no_alt_analysis_set.fna HG00438.paternal.f1_assembly_v2.fa"
    )

    @pytest.mark.parametrize(
        ("header", "file_name", "data_type", "rule_id"),
        [
            pytest.param(
                HIFI_READS, "m64136_210522_014758.hifi_reads.bam", "reads", "unaligned_no_sq", id="PacBio hifi_reads"
            ),
            pytest.param(
                GUPPY_MODBASE,
                "08_25_21_R941_HG02004_2_Guppy_6.4.6_450bps_modbases_5mc_cg_sup_prom_pass.bam",
                "reads",
                "unaligned_no_sq",
                id="Guppy mod-base with a minimap2 @PG",
            ),
            pytest.param(
                KINNEX_FLNC,
                "NA19682.lymph.m84203_240912_223637_s3.flnc.bam",
                "reads",
                "unaligned_no_sq",
                id="Kinnex flnc",
            ),
            pytest.param(
                ALIGNED_MINIMAP2,
                "HG00438.f1_assembly_v2.hap1.bam",
                "alignments",
                "aligned_has_sq",
                id="@SQ with a minimap2 @PG",
            ),
        ],
    )
    def test_sq_decides_data_type(self, header, file_name, data_type, rule_id):
        result = classify_from_header(header, name=FileName.parse(file_name))
        assert val(result, "data_type") == data_type
        claims = [e for e in field_evidence(result, "data_type") if "value" in e]
        assert [(e["rule_id"], e["tier"]) for e in claims] == [(rule_id, 3)]


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

    @pytest.mark.parametrize(
        "sq, assembly",
        [
            # ANVIL_nhp_dGTEx's rhesus (RHGTEX…) and marmoset (CJGTEX…) headers (#636);
            # an unplaced contig, which the table does not hold, votes for nothing.
            (
                [("chr1", 223616942), ("chr1_NW_021160094v1_random", 26680), ("chr2", 196197964), ("chrY", 11753682)],
                "Mmul_10",
            ),
            ([("chr1", 216975769), ("chr21", 50614742), ("chrX", 146897247), ("chrY", 4974773)], "mCalJa1.2.pat.X"),
        ],
    )
    def test_bam_sq_monkey_assemblies(self, sq, assembly):
        """A rhesus or marmoset @SQ dictionary is its own assembly, by contig length (#636)."""
        header = "@HD\tVN:1.6\tSO:coordinate\n" + "\n".join(f"@SQ\tSN:{name}\tLN:{length}" for name, length in sq)
        assert val(classify_from_header(header), "reference_assembly") == assembly

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


def classify_members(members: list[str]) -> dict:
    """A tar classified from its member names alone: its head as parsed with no vcfheader.vcf read."""
    return classify_from_tar_head(parse_tar_head(TarHead(members, None)))


class TestTarClassifier:
    """classify_from_tar_head on a head with no vcfheader.vcf read: a tar classified by its members (#255)."""

    def test_genomicsdb_store_from_schema_files(self):
        """A GenomicsDB store recognized by its schema files (the common case)."""
        members = ["./chr22.1_2/vidmap.json", "./chr22.1_2/callset.json", "./chr22.1_2/vcfheader.vcf"]
        result = classify_members(members)
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "variants.genomicsdb"

    def test_genomicsdb_store_from_vcf_field_arrays_only(self):
        """A large store whose schema files are past the head is still caught by its
        VCF-attribute TileDB arrays (e.g. PL/GQ/DP_FORMAT), incl. the `_var` pairs."""
        members = [
            "./chr4.1_2/chr4$1$2/__coords.tdb",
            "./chr4.1_2/chr4$1$2/PL.tdb",
            "./chr4.1_2/chr4$1$2/DP_FORMAT.tdb",
            "./chr4.1_2/chr4$1$2/MLEAC_var.tdb",
        ]
        result = classify_members(members)
        assert val(result, "data_modality") == "genomic"
        assert val(result, "data_type") == "variants.genomicsdb"

    def test_genomicsdb_array_name_in_mid_path_is_caught(self):
        """A TileDB array is a directory (`PL.tdb/`), so the variant-array name is a
        mid-path segment; when the directory entry itself is omitted, only the deeper
        files remain — the all-segments check still recognizes it."""
        members = [
            "chr4.1_2/chr4$1$2/PL.tdb/__array_schema.tdb",
            "chr4.1_2/chr4$1$2/PL.tdb/__fragment/a.tdb",
        ]
        result = classify_members(members)
        assert val(result, "data_type") == "variants.genomicsdb"

    def test_bare_tiledb_is_not_called_variants(self):
        """Honesty: a `.tdb` is a *generic* TileDB array — a head of only generic TileDB
        structure files (no schema, no VCF-field array) is not read as variants."""
        members = ["store/__tiledb_workspace.tdb", "store/__array_schema.tdb", "store/__coords.tdb"]
        result = classify_members(members)
        assert field_status(result, "data_type") == NOT_CLASSIFIED
        assert field_status(result, "data_modality") == NOT_CLASSIFIED

    def test_generic_dominant_inner_extension(self):
        """A tar of FASTA members → the inner format's classification (sequence)."""
        result = classify_members(["asm/hap1.fasta", "asm/hap2.fasta", "asm/readme.txt"])
        assert val(result, "data_type") == "sequence"

    def test_a_tar_of_matrices_takes_the_inner_format_assay(self):
        """The inner format's assay reaches the archive too, not only its modality and type (#533)."""
        result = classify_members(["out/cells_x_genes.mtx", "out/spliced.mtx", "out/genes.txt"])
        assert val(result, "data_modality") == "transcriptomic"
        assert val(result, "assay_type") == "sc/snRNA-seq"

    def test_unrecognized_contents_stay_not_classified(self):
        """Read it, but no GenomicsDB signal and no recognized inner extension → not_classified."""
        result = classify_members(["blob/x.dat", "blob/y.bin"])
        assert field_status(result, "data_type") == NOT_CLASSIFIED

    def test_empty_member_list_is_not_classified(self):
        """A non-tar / empty head read as no members → not_classified, not a crash."""
        result = classify_members([])
        assert field_status(result, "data_type") == NOT_CLASSIFIED


class TestWorkspaceCaller:
    """classify_from_tar_head: a GenomicsDB workspace's kind and origin from the caller its own
    ``vcfheader.vcf`` names (#678), found as a VCF's is."""

    MEMBERS = ("./chr1.100000001_100100000/vcfheader.vcf", "./chr1.100000001_100100000/callset.json")
    # As T2T's workspaces carry them: the import's line, a HaplotypeCaller line carried over
    # from a gVCF's header, and a ##source line naming each tool.
    HEADER = header_text(IMPORT, HC, "##source=GenomicsDBImport", "##source=HaplotypeCaller")
    # GenomicsDBImport is a merge (#678): a workspace's answer is the import of its callers' calls.
    RULES = MappingProxyType(
        {
            "variant_kind": code_rules.TAR_MERGE_SMALL_CALLERS.id,
            "variant_origin": code_rules.TAR_MERGE_GERMLINE_CALLERS.id,
        }
    )
    STEP_RULES = MappingProxyType(
        {
            "variant_kind": code_rules.TAR_STEP_CALLER_KIND.id,
            "variant_origin": code_rules.TAR_STEP_CALLER_ORIGIN.id,
        }
    )

    def classify(self, file_name: str, header: str | None = HEADER, unread: str | None = None, members=None):
        head = parse_tar_head(TarHead(list(self.MEMBERS if members is None else members), header, unread))
        return classify_from_tar_head(head, name=FileName.parse(file_name))

    def claim(self, out: dict, field: str, rules: Mapping[str, str] = RULES) -> dict:
        (claim,) = [e for e in field_evidence(out, field) if e.get("rule_id") == rules[field]]
        return claim

    @pytest.mark.parametrize("file_name", ["chr1.100000001_100100000.tar", "renamed.tar"])
    def test_a_workspace_is_the_import_of_its_callers_calls(self, file_name):
        """Named for its workspace or not: the header's GenomicsDBImport merges what HaplotypeCaller called."""
        out = self.classify(file_name)
        assert out["variant_kind"]["value"] == ["small"]  # stored as a one-item list (models.stored_value)
        assert val(out, "variant_origin") == "germline"
        for field, value, tail in (
            ("variant_kind", "small", "no structural-variant field declared"),
            ("variant_origin", "germline", "no somatic field declared"),
        ):
            claim = self.claim(out, field)
            assert (claim["value"], claim["tier"], claim["source_type"]) == (value, CONTENT_TIER, SOURCE_CONTENT_READ)
            assert claim["reason"] == f"GenomicsDBImport of calls by HaplotypeCaller; {tail}"

    @pytest.mark.parametrize("file_name", ["chr1.100000001_100100000.tar", "CHR1.100000001_100100000.tar.gz"])
    def test_the_caller_is_looked_for_in_what_the_import_wrote(self, file_name, monkeypatch):
        """The import's output is the directory the tar was made from: its name, less .tar and any .gz."""
        import meta_disco.header_classifier as hc

        seen = []
        real = hc.find_caller
        monkeypatch.setattr(hc, "find_caller", lambda header, name: seen.append(name) or real(header, name))
        self.classify(file_name)
        assert seen == ["chr1.100000001_100100000"]

    def test_a_caller_named_only_by_source_is_claimed_under_the_source_rules(self):
        """The VCF path's routing (#654, #658): a header with no command line, its one ##source a caller."""
        out = self.classify("chr1.100000001_100100000.tar", header=header_text("##source=HaplotypeCaller"))
        rules = {
            "variant_kind": code_rules.TAR_SOURCE_CALLER_KIND.id,
            "variant_origin": code_rules.TAR_SOURCE_CALLER_ORIGIN.id,
        }
        assert val(out, "variant_origin") == "germline"
        for field in rules:
            assert (
                self.claim(out, field, rules)["reason"]
                == "called by HaplotypeCaller (named by the header: HaplotypeCaller)"
            )

    def test_an_import_of_mutect2_gvcfs_gives_neither(self):
        """GATK's panel-of-normals workflow imports Mutect2's calls, which the caller table does not list."""
        mutect = '##GATKCommandLine=<ID=Mutect2,CommandLine="Mutect2 -I n.bam -O n.g.vcf.gz -ERC GVCF -R r.fa">'
        out = self.classify("chr1.100000001_100100000.tar", header=header_text(IMPORT, mutect))
        for field in self.RULES:
            assert field_status(out, field) == NOT_CLASSIFIED
            assert self.claim(out, field)["reason"].startswith("a merge whose callers are not all")

    def test_a_workspace_whose_header_was_not_read_says_why(self):
        missing = self.classify("chr1.100000001_100100000.tar", header=None)
        failed = self.classify("chr1.100000001_100100000.tar", header=None, unread="ConnectionError: reset")
        for field in self.STEP_RULES:
            assert field_status(missing, field) == NOT_CLASSIFIED
            assert self.claim(missing, field, self.STEP_RULES)["reason"] == NO_WORKSPACE_HEADER
            assert (
                self.claim(failed, field, self.STEP_RULES)["reason"]
                == f"{WORKSPACE_HEADER_UNREADABLE}: ConnectionError: reset"
            )

    def test_a_tar_that_is_no_workspace_gets_no_caller_claim(self):
        out = self.classify("asm.tar", header=None, members=["asm/hap1.fasta", "asm/hap2.fasta"])
        assert val(out, "data_type") == "sequence"
        for field in self.RULES:
            assert not [e for e in field_evidence(out, field) if str(e.get("rule_id", "")).startswith("tar_")]


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
        from meta_disco import header_classifier
        from meta_disco.validators import header_extractors, reference_builds

        real = header_extractors.parse_vcf_header
        calls = []

        def counting(text):
            calls.append(text)
            return real(text)

        # Patched at every site that bound the name: the engine imports it at call
        # time, but this module and reference_builds bound it at import, so a parse
        # there would be invisible to a patch on header_extractors alone.
        monkeypatch.setattr(header_extractors, "parse_vcf_header", counting)
        monkeypatch.setattr(reference_builds, "parse_vcf_header", counting)
        monkeypatch.setattr(header_classifier, "parse_vcf_header", counting)
        header = (
            "##fileformat=VCFv4.2\n##source=HaplotypeCaller\n##reference=file:///ref/hg38.fa\n"
            '##contig=<ID=chr1,length=248956422>\n##INFO=<ID=DP,Number=1,Type=Integer,Description="depth">\n'
        )
        result = classify_from_vcf_header(header, name=FileName.parse("sample.vcf.gz"))
        assert result["reference_assembly"]["value"] == "GRCh38"
        assert result["data_type"]["value"] == "variants"
        assert len(calls) == 1


class TestGvcf:
    """A gVCF is told by its content: the step that made it is a HaplotypeCaller in a
    reference-confidence mode, and its records all carry `<NON_REF>`, some alone (#607)."""

    GVCF_LINES = (
        '##ALT=<ID=NON_REF,Description="Represents any possible alternative allele not already represented">',
        "##GVCFBlock0-1=minGQ=0(inclusive),maxGQ=1(exclusive)",
    )
    T2T_HC = HC
    NYGC_HC = GATK3_HC.replace("showFullBamList=false", "emitRefConfidence=GVCF showFullBamList=false")
    SELECT = gatk4(
        "SelectVariants", "--output chr10.1_100000.genotyped.vcf --variant chr10.1_100000.margined.genotyped.vcf.gz"
    )
    # The ALTs of a gVCF's first records: sites with no variant (`<NON_REF>` alone) and a
    # variant site, which carries `<NON_REF>` beside its allele.
    GVCF_ALTS = ("<NON_REF>", "<NON_REF>", "C,<NON_REF>", "<NON_REF>")

    @staticmethod
    def classify(*lines: str, file_name: str, alts: tuple[str, ...] | None = GVCF_ALTS) -> dict:
        """Classify a header of ``lines`` whose head read held records of ``alts`` (None: not read)."""
        text = header_text(*lines) + "\tFORMAT\tHG00096"  # one sample column, as a gVCF has
        header = parse_vcf_header(text) if alts is None else vcf_head(text, alts)
        return classify_from_vcf_header(header, name=FileName.parse(file_name))

    @pytest.mark.parametrize(
        ("lines", "file_name"),
        [
            pytest.param((T2T_HC, "##source=HaplotypeCaller"), "HG00096.chr10.hc.vcf.gz", id="GATK 4, a VCF's name"),
            pytest.param((NYGC_HC,), "HG01377.haplotypeCalls.er.raw.g.vcf.gz", id="GATK 3, a gVCF's name"),
            pytest.param((NYGC_HC,), "NA12818.haplotypeCalls.er.raw.vcf.gz", id="GATK 3, a VCF's name"),
            pytest.param(
                (T2T_HC.replace("GVCF", "BP_RESOLUTION"),), "HG00096.chr10.hc.vcf.gz", id="GATK 4, BP_RESOLUTION"
            ),
        ],
    )
    def test_a_haplotypecaller_gvcf_with_reference_records_is_a_gvcf(self, lines, file_name):
        result = self.classify(*self.GVCF_LINES, *lines, file_name=file_name)
        assert val(result, "data_type") == "variants.gvcf"
        claims = [e for e in field_evidence(result, "data_type") if e.get("rule_id") == code_rules.VCF_GVCF.id]
        assert [(e["tier"], e["source_type"]) for e in claims] == [(CONTENT_TIER, SOURCE_CONTENT_READ)]
        # Its one sample column gives no single-sample claim beside it: its records carry <NON_REF> (#655).
        assert code_rules.VCF_SAMPLE_COLUMN_COUNT.id not in val(result, "matched_rules")

    @pytest.mark.parametrize(
        ("lines", "file_name", "alts", "data_type"),
        [
            pytest.param(
                (*GVCF_LINES, T2T_HC, SELECT),
                "chr10.1_100000.genotyped.vcf.gz",
                GVCF_ALTS,
                "variants",
                id="made by SelectVariants, an earlier step in GVCF mode",
            ),
            pytest.param((*GVCF_LINES, T2T_HC), "STU.pvar", GVCF_ALTS, "genotypes", id="a pvar"),
            pytest.param(
                GVCF_LINES, "HG01377.haplotypeCalls.er.raw.g.vcf.gz", GVCF_ALTS, "variants", id="no command line"
            ),
            pytest.param((NYGC_HC,), "", GVCF_ALTS, "variants", id="no file name to check the step against"),
            pytest.param(
                ("##source=HaplotypeCaller", T2T_HC.replace("GVCF", "NONE")),
                "HG00096.chr10.hc.vcf.gz",
                GVCF_ALTS,
                "variants",
                id="HaplotypeCaller, mode NONE",
            ),
            pytest.param(
                (T2T_HC, T2T_HC.replace("GVCF", "NONE").replace("--intervals chr10", "--intervals chr10 -L x")),
                "HG00096.chr10.hc.vcf.gz",
                GVCF_ALTS,
                "variants",
                id="two HaplotypeCaller lines alike but for the mode",
            ),
            pytest.param(
                ("##source=HaplotypeCaller", T2T_HC),
                "HG00096.chr10.hc.vcf.gz",
                ("C,<NON_REF>", "A,<NON_REF>"),
                "variants",
                id="records of variant sites only, as a gVCF filtered to them",
            ),
            pytest.param(
                ("##source=HaplotypeCaller", T2T_HC),
                "HG00096.chr10.hc.vcf.gz",
                ("<NON_REF>", "C"),
                "variants",
                id="a record without <NON_REF>",
            ),
            pytest.param(
                ("##source=HaplotypeCaller", T2T_HC),
                "HG00096.chr10.hc.vcf.gz",
                ("<NON_REF>", "C,T<NON_REF>"),
                "variants",
                id="an allele that contains <NON_REF> without being it",
            ),
            pytest.param(
                ("##source=HaplotypeCaller", T2T_HC), "HG00096.chr10.hc.vcf.gz", (), "variants", id="no record"
            ),
            pytest.param(
                ("##source=HaplotypeCaller", T2T_HC),
                "HG00096.chr10.hc.vcf.gz",
                None,
                "variants",
                id="records not read",
            ),
        ],
    )
    def test_without_both_the_step_and_the_records_no_gvcf_is_claimed(self, lines, file_name, alts, data_type):
        """The `##ALT=<ID=NON_REF>` and `##GVCFBlock` lines, a `.g.vcf` name, and a GVCF-mode
        line of an earlier step all carry over into files that are not gVCFs; a step in GVCF
        mode over records with no site that is `<NON_REF>` alone is not one either."""
        result = self.classify(*lines, file_name=file_name, alts=alts)
        assert val(result, "data_type") == data_type
        assert code_rules.VCF_GVCF.id not in (val(result, "matched_rules") or [])

    def test_another_tools_reference_confidence_mode_is_not_a_germline_gvcf(self, monkeypatch):
        """Mutect2, GATK's somatic caller, takes `-ERC` too: were its mode declared, a file it
        made in GVCF mode would still not be a germline gVCF."""
        from meta_disco.validators import command_lines

        monkeypatch.setitem(
            command_lines.TOOL_ARGUMENTS,
            (command_lines.GATK, "Mutect2"),
            command_lines.ToolArguments(inputs=("-I",), outputs=("-O",), mode=("-ERC", "--emit-ref-confidence")),
        )
        mutect = gatk4("Mutect2", "-ERC GVCF -I tumor.cram -O tumor.chr1.vcf")
        result = self.classify(*self.GVCF_LINES, mutect, file_name="tumor.chr1.vcf.gz")
        assert code_rules.VCF_GVCF.id not in (val(result, "matched_rules") or [])


class TestSampleColumnCount:
    """A VCF's sample columns after FORMAT give its data_type (#655): none, sites-only; two or
    more, multi-sample; one, single-sample where no record read carries <NON_REF>."""

    @staticmethod
    def classify(columns: str, file_name: str = "HG002.calls.vcf.gz", alts=("A", "C,T")) -> dict:
        """Classify a header whose #CHROM line ends in ``columns``, its head's records of ``alts`` (None: not read)."""
        text = header_text() + columns
        header = parse_vcf_header(text) if alts is None else vcf_head(text, alts)
        return classify_from_vcf_header(header, name=FileName.parse(file_name))

    @staticmethod
    def count_claims(result: dict) -> list[dict]:
        return [
            e for e in field_evidence(result, "data_type") if e.get("rule_id") == code_rules.VCF_SAMPLE_COLUMN_COUNT.id
        ]

    @pytest.mark.parametrize(
        ("columns", "data_type", "reason"),
        [
            pytest.param("", "variants.sites_only", "no sample columns", id="no FORMAT column"),
            pytest.param("\tFORMAT", "variants.sites_only", "no sample columns", id="FORMAT and no sample"),
            pytest.param(
                "\tFORMAT\tHG002_hap1\tHG002_hap2",
                "variants.multi_sample",
                "2 sample columns after FORMAT (HG002_hap1, HG002_hap2)",
                id="two",
            ),
            pytest.param(
                "\tFORMAT\tHG00096\tHG00097\tHG00099",
                "variants.multi_sample",
                "3 sample columns after FORMAT (HG00096, HG00097, ...)",
                id="three",
            ),
            pytest.param(
                "\tFORMAT\tHG002",
                "variants.single_sample",
                "1 sample column after FORMAT (HG002), and none of its first 2 records has <NON_REF> or <*>",
                id="one",
            ),
        ],
    )
    def test_the_columns_give_the_data_type(self, columns, data_type, reason):
        result = self.classify(columns)
        assert val(result, "data_type") == data_type
        [claim] = self.count_claims(result)
        assert (claim["tier"], claim["source_type"]) == (CONTENT_TIER, SOURCE_CONTENT_READ)
        assert reason in claim["reason"]
        assert "no records" not in claim["reason"]

    @pytest.mark.parametrize(
        "alts",
        [
            pytest.param(("A", "C,<NON_REF>"), id="a record with <NON_REF>"),
            pytest.param(("<*>", "T,<*>"), id="records with <*>, as a DeepVariant gVCF's"),
            pytest.param((), id="no record"),
            pytest.param(None, id="records not read"),
        ],
    )
    def test_one_column_gives_nothing_unless_its_records_read_carry_no_non_ref(self, alts):
        result = self.classify("\tFORMAT\tHG002", alts=alts)
        assert self.count_claims(result) == []
        assert val(result, "data_type") == "variants"

    @pytest.mark.parametrize("alts", [("C,<NON_REF>", "<NON_REF>"), ("<*>", "T,<*>")], ids=["<NON_REF>", "<*>"])
    def test_a_combined_gvcf_is_not_multi_sample(self, alts):
        """CombineGVCFs' output holds several samples' gVCF records: no VCF term names it."""
        result = self.classify("\tFORMAT\tHG00096\tHG00097", alts=alts)
        assert self.count_claims(result) == []
        assert val(result, "data_type") == "variants"

    @pytest.mark.parametrize(
        ("read_to_end", "data_type"),
        [(True, "variants.multi_sample"), (False, "variants"), (None, "variants")],
        ids=["read to its end", "cut off", "not known"],
    )
    def test_several_columns_with_no_record_need_the_read_to_reach_the_end(self, read_to_end, data_type):
        """An empty region shard read to its end holds no records, and is multi-sample; a read cut off
        before the first record may have missed a combined gVCF's (#655)."""
        text = header_text() + "\tFORMAT\tHG00096\tHG00097"
        header = parse_vcf_head(VcfHead(text, [], read_to_end))
        result = classify_from_vcf_header(header, name=FileName.parse("chrY.1_100000.genotyped.vcf.gz"))
        assert val(result, "data_type") == data_type
        if read_to_end:
            assert self.count_claims(result)[0]["reason"].endswith(
                "2 sample columns after FORMAT (HG00096, HG00097); no records, read to its end"
            )

    @pytest.mark.parametrize("file_name", ["all_phase3_ns.pvar", "chr1.pvar.gz", "ALL.PVAR"])
    def test_a_pvar_keeps_its_plink_data_type(self, file_name):
        """A `.pvar` has no sample columns, and is no sites-only VCF: its data_type is the PLINK rule's."""
        result = self.classify("", file_name=file_name)
        assert self.count_claims(result) == []
        assert val(result, "data_type") == "genotypes"

    @pytest.mark.parametrize(
        "alts", [None, (), ("<NON_REF>", "C,<NON_REF>"), ("<*>",)], ids=["not read", "none", "<NON_REF>", "<*>"]
    )
    def test_no_sample_columns_is_sites_only_whatever_the_records(self, alts):
        """No sample column holds no genotypes, so no gVCF's records: the records are not read for it."""
        assert val(self.classify("", alts=alts), "data_type") == "variants.sites_only"

    @pytest.mark.parametrize("line", ["#CHROM\tPOS\tID\tREF\tALT", "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tCM"])
    def test_a_vcf_with_a_pvars_chrom_line_is_not_sites_only(self, line):
        """A `.pvar`'s columns are not a VCF's line: a VCF named so makes no claim."""
        text = f"##fileformat=VCFv4.2\n{line}"
        result = classify_from_vcf_header(vcf_head(text, ("A",)), name=FileName.parse("calls.vcf.gz"))
        assert self.count_claims(result) == []

    def test_a_malformed_chrom_line_is_not_sites_only(self):
        """Columns after INFO with no FORMAT before them: the line is not read, and no claim made."""
        result = self.classify("\tformat\tHG00096\tHG00097")
        assert self.count_claims(result) == []

    def test_a_header_with_no_chrom_line_gives_nothing(self):
        result = classify_from_vcf_header(vcf_head("##fileformat=VCFv4.2", ("A",)), name=FileName.parse("x.vcf.gz"))
        assert self.count_claims(result) == []
