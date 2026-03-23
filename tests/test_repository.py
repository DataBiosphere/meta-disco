"""Tests for repository configuration module."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.repository import ANVIL, HPRC, AnvilConfig, HprcConfig, _s3_to_https, get_repo


class TestS3ToHttps:
    def test_s3_url(self):
        url = _s3_to_https("s3://human-pangenomics/working/file.bam")
        assert url == "https://s3-us-west-2.amazonaws.com/human-pangenomics/working/file.bam"

    def test_https_passthrough(self):
        url = "https://s3-us-west-2.amazonaws.com/bucket/key"
        assert _s3_to_https(url) == url

    def test_unsupported_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            _s3_to_https("ftp://example.com/file")


class TestAnvilConfig:
    def test_evidence_dir(self):
        assert ANVIL.evidence_dir("bam") == Path("data/anvil/evidence/bam")
        assert ANVIL.evidence_dir("vcf") == Path("data/anvil/evidence/vcf")

    def test_get_key_from_anvil_record(self):
        record = {"file_md5sum": "abc123", "file_name": "test.bam"}
        assert ANVIL.get_key(record) == "abc123"

    def test_get_key_missing(self):
        assert ANVIL.get_key({}) is None

    def test_get_url(self):
        record = {"file_md5sum": "abc123"}
        url = ANVIL.get_url(record)
        assert url == "https://anvilproject.s3.amazonaws.com/file/abc123.md5"

    def test_get_url_no_md5(self):
        assert ANVIL.get_url({}) is None

    def test_get_filename_anvil(self):
        assert ANVIL.get_filename({"file_name": "test.bam"}) == "test.bam"

    def test_get_filename_hprc_style(self):
        assert ANVIL.get_filename({"filename": "test.bam"}) == "test.bam"

    def test_get_file_size(self):
        assert ANVIL.get_file_size({"file_size": 1000}) == 1000

    def test_get_file_size_string(self):
        assert ANVIL.get_file_size({"fileSize": "1000"}) == 1000

    def test_get_file_size_none(self):
        assert ANVIL.get_file_size({}) is None


class TestHprcConfig:
    def test_evidence_dir(self):
        assert HPRC.evidence_dir("fasta") == Path("data/hprc/evidence/fasta")

    def test_get_key_from_path(self):
        record = {"path": "s3://human-pangenomics/working/file.bam"}
        key = HPRC.get_key(record)
        assert key is not None
        assert len(key) == 16  # sha256 truncated to 16 hex chars

    def test_get_key_deterministic(self):
        record = {"path": "s3://human-pangenomics/working/file.bam"}
        assert HPRC.get_key(record) == HPRC.get_key(record)

    def test_get_key_different_urls(self):
        r1 = {"path": "s3://bucket/file1.bam"}
        r2 = {"path": "s3://bucket/file2.bam"}
        assert HPRC.get_key(r1) != HPRC.get_key(r2)

    def test_get_key_from_loc(self):
        record = {"loc": "https://s3-us-west-2.amazonaws.com/bucket/file.vcf"}
        assert HPRC.get_key(record) is not None

    def test_get_key_from_fileLocation(self):
        record = {"fileLocation": "s3://human-pangenomics/annotations/file.gff3"}
        assert HPRC.get_key(record) is not None

    def test_get_key_from_awsFasta(self):
        record = {"awsFasta": "s3://human-pangenomics/assemblies/file.fa.gz"}
        assert HPRC.get_key(record) is not None

    def test_get_key_no_url(self):
        assert HPRC.get_key({}) is None

    def test_get_key_na_value(self):
        assert HPRC.get_key({"awsFasta": "N/A"}) is None

    def test_get_url_s3(self):
        record = {"path": "s3://human-pangenomics/working/file.bam"}
        url = HPRC.get_url(record)
        assert url == "https://s3-us-west-2.amazonaws.com/human-pangenomics/working/file.bam"

    def test_get_url_https_passthrough(self):
        record = {"loc": "https://s3-us-west-2.amazonaws.com/bucket/file.vcf"}
        url = HPRC.get_url(record)
        assert url == "https://s3-us-west-2.amazonaws.com/bucket/file.vcf"

    def test_get_url_no_field(self):
        assert HPRC.get_url({}) is None

    def test_get_filename(self):
        assert HPRC.get_filename({"filename": "test.bam"}) == "test.bam"

    def test_get_file_size_string(self):
        assert HPRC.get_file_size({"fileSize": "94601309"}) == 94601309

    def test_get_file_format(self):
        assert HPRC.get_file_format({"filetype": "bam"}) == "bam"


class TestGetRepo:
    def test_anvil(self):
        assert isinstance(get_repo("anvil"), AnvilConfig)

    def test_hprc(self):
        assert isinstance(get_repo("hprc"), HprcConfig)

    def test_unknown(self):
        with pytest.raises(ValueError, match="Unknown repository"):
            get_repo("nonexistent")
