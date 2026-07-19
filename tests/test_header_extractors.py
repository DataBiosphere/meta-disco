"""Tests for VCF header extraction and its typed line records."""

from meta_disco.validators.header_extractors import (
    VcfSimpleMeta,
    VcfStructuredMeta,
    get_contig_lines,
    match_vcf_header_pattern,
    parse_vcf_header,
    parse_vcf_header_line,
)


class TestParseVcfHeaderLine:
    """Test parse_vcf_header_line's simple/structured/None dispatch."""

    def test_simple_line_returns_simple_meta(self):
        parsed = parse_vcf_header_line("##fileformat=VCFv4.2")
        assert parsed == VcfSimpleMeta(type="fileformat", value="VCFv4.2")

    def test_structured_line_returns_structured_meta(self):
        parsed = parse_vcf_header_line("##contig=<ID=chr1,length=248956422>")
        assert parsed == VcfStructuredMeta(type="contig", fields={"ID": "chr1", "length": "248956422"})

    def test_structured_line_strips_quotes(self):
        parsed = parse_vcf_header_line('##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">')
        assert isinstance(parsed, VcfStructuredMeta)
        assert parsed.fields["ID"] == "DP"
        assert parsed.fields["Description"] == "Total Depth"

    def test_unparseable_line_returns_none(self):
        assert parse_vcf_header_line("#CHROM\tPOS\tID") is None


class TestParseVcfHeader:
    """Test parse_vcf_header building a typed VCFHeader."""

    HEADER = "\n".join(
        [
            "##fileformat=VCFv4.2",
            "##reference=file:///GRCh38.fa",
            "##source=MyCaller",
            "##contig=<ID=chr1,length=248956422>",
            '##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">',
            "##FORMAT=<ID=GT,Number=1,Type=String>",
            '##FILTER=<ID=PASS,Description="All filters passed">',
            "##fileDate=20090805",
        ]
    )

    def test_simple_fields_extracted(self):
        header = parse_vcf_header(self.HEADER)
        assert header.fileformat == "VCFv4.2"
        assert header.reference == "file:///GRCh38.fa"
        assert header.source == "MyCaller"

    def test_structured_fields_are_typed(self):
        header = parse_vcf_header(self.HEADER)
        assert header.contigs == [VcfStructuredMeta(type="contig", fields={"ID": "chr1", "length": "248956422"})]
        assert header.info_fields is not None
        assert header.info_fields[0].fields["ID"] == "DP"
        assert header.format_fields is not None
        assert header.format_fields[0].fields["ID"] == "GT"
        assert header.filter_fields is not None
        assert header.filter_fields[0].fields["ID"] == "PASS"

    def test_unrecognized_simple_line_falls_to_other_meta(self):
        header = parse_vcf_header(self.HEADER)
        assert header.other_meta == ["##fileDate=20090805"]


class TestMatchVcfHeaderPattern:
    """Test match_vcf_header_pattern over the typed header."""

    HEADER = "\n".join(
        [
            "##reference=file:///GRCh38.fa",
            "##source=MyCaller_v2",
            "##contig=<ID=chr1,length=248956422,assembly=GRCh38>",
            "##INFO=<ID=DP,Number=1,Type=Integer>",
            "##FORMAT=<ID=GT,Number=1,Type=String>",
            '##FILTER=<ID=LowQual,Description="Low quality">',
            "##fileDate=20090805",
        ]
    )

    def test_reference_pattern_matches(self):
        header = parse_vcf_header(self.HEADER)
        assert match_vcf_header_pattern(header, "##reference", "GRCh38")

    def test_source_pattern_matches(self):
        header = parse_vcf_header(self.HEADER)
        assert match_vcf_header_pattern(header, "##source", "MyCaller")

    def test_contig_assembly_pattern_matches(self):
        # ##contig matches against the parsed ``assembly`` subfield, so the
        # shipped bare-name rule pattern (no ``assembly=`` prefix) fires (#221).
        header = parse_vcf_header(self.HEADER)
        assert match_vcf_header_pattern(header, "##contig", r"(?i)(grch38|hg38|hs38|GCA_000001405\.15)")

    def test_contig_non_assembly_subfield_does_not_match(self):
        # Only the assembly subfield is scanned: a bare contig length value is
        # not matchable, which is what made the pre-#221 scanner unable to see
        # the ``assembly=`` rules.
        header = parse_vcf_header(self.HEADER)
        assert not match_vcf_header_pattern(header, "##contig", "248956422")

    def test_contig_wrong_assembly_does_not_match(self):
        header = parse_vcf_header(self.HEADER)
        assert not match_vcf_header_pattern(header, "##contig", r"(?i)(grch37|hg19|hs37|GCA_000001405\.[^5]|b37)")

    def test_info_id_pattern_matches(self):
        header = parse_vcf_header(self.HEADER)
        assert match_vcf_header_pattern(header, "##INFO", "DP")

    def test_format_id_pattern_matches(self):
        header = parse_vcf_header(self.HEADER)
        assert match_vcf_header_pattern(header, "##FORMAT", "GT")

    def test_filter_id_pattern_matches(self):
        header = parse_vcf_header(self.HEADER)
        assert match_vcf_header_pattern(header, "##FILTER", "LowQual")

    def test_other_meta_fallback_matches_raw_line(self):
        # An unrecognized ## line lands in other_meta; the fallback branch
        # matches on the raw line by its ## prefix.
        header = parse_vcf_header(self.HEADER)
        assert match_vcf_header_pattern(header, "##fileDate", "20090805")

    def test_no_match_returns_false(self):
        header = parse_vcf_header(self.HEADER)
        assert not match_vcf_header_pattern(header, "##reference", "GRCh37")


class TestGetContigLines:
    """Test get_contig_lines reconstruction from typed contigs."""

    def test_reconstructs_all_fields(self):
        header = parse_vcf_header("##contig=<ID=chr1,length=248956422>")
        assert get_contig_lines(header) == ["##contig=<ID=chr1,length=248956422>"]

    def test_empty_when_no_contigs(self):
        header = parse_vcf_header("##fileformat=VCFv4.2")
        assert get_contig_lines(header) == []
