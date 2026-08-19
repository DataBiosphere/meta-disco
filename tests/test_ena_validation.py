"""Tests for the ENA validator's join key and vocabulary mapping (#330)."""

import sys
from pathlib import Path

import yaml

from meta_disco.validation_maps import ENA_LIBRARY_STRATEGY_MAP

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import validate_ena_accessions as ena

SCHEMA = Path(__file__).parent.parent / "src" / "meta_disco" / "schema" / "classification.yaml"


class TestStrategyMap:
    def test_values_are_valid_assay_enum_spellings(self):
        enum = yaml.safe_load(SCHEMA.read_text())["enums"]["assay_type_enum"]["permissible_values"]
        for strategy, assay in ENA_LIBRARY_STRATEGY_MAP.items():
            assert assay in enum, f"{strategy!r} maps to {assay!r}, not in assay_type_enum"

    def test_expected_strategies_present(self):
        for strategy in ("WGS", "WXS", "RNA-Seq"):
            assert strategy in ENA_LIBRARY_STRATEGY_MAP


class TestExtractAccession:
    def test_trailing_underscore_read_suffix(self):
        # underscore right after the digits defeats a trailing \b
        assert ena.extract_accession({"file_name": "ERR3988887_1.fastq.gz"}) == "ERR3988887"

    def test_sample_prefix_before_accession(self):
        # underscore before the accession defeats a leading \b
        assert ena.extract_accession({"file_name": "HG002_ERR123456.fastq.gz"}) == "ERR123456"

    def test_dot_separated(self):
        assert ena.extract_accession({"file_name": "HG00405.SRR1596638.fastq.gz"}) == "SRR1596638"

    def test_embedded_in_word_is_not_an_accession(self):
        assert ena.extract_accession({"file_name": "XERR123456.fastq.gz"}) is None
        assert ena.extract_accession({"file_name": "2ERR123456.fastq.gz"}) is None

    def test_drr_prefix(self):
        assert ena.extract_accession({"file_name": "DRR000001.fastq.gz"}) == "DRR000001"

    def test_short_digit_run_rejected(self):
        assert ena.extract_accession({"file_name": "ERR12345.fastq.gz"}) is None

    def test_stored_field_preferred_over_name(self):
        rec = {"archive_accession": "ERR999999", "file_name": "ERR111111_1.fastq.gz"}
        assert ena.extract_accession(rec) == "ERR999999"

    def test_stored_field_nested_under_classifications(self):
        # the current pipeline output stores the accession beside the
        # dimension entries, not at the top level
        rec = {
            "file_name": "ERR111111_1.fastq.gz",
            "classifications": {
                "archive_accession": "ERR999999",
                "platform": {"value": "ILLUMINA", "status": "classified"},
            },
        }
        assert ena.extract_accession(rec) == "ERR999999"

    def test_top_level_stored_field_wins_over_nested(self):
        rec = {
            "archive_accession": "ERR222222",
            "classifications": {"archive_accession": "ERR999999"},
            "file_name": "ERR111111_1.fastq.gz",
        }
        assert ena.extract_accession(rec) == "ERR222222"

    def test_non_string_stored_value_falls_back_to_name(self):
        rec = {
            "classifications": {"archive_accession": {"value": "ERR999999"}},
            "file_name": "ERR111111_1.fastq.gz",
        }
        assert ena.extract_accession(rec) == "ERR111111"

    def test_no_accession(self):
        assert ena.extract_accession({"file_name": "HG002.hifi_reads.fastq.gz"}) is None


class TestOurField:
    def test_per_field_shape(self):
        rec = {"classifications": {"platform": {"value": "ILLUMINA", "status": "classified"}}}
        assert ena.our_field(rec, "platform") == ("ILLUMINA", "classified")

    def test_sentinel_status(self):
        rec = {"classifications": {"platform": {"value": None, "status": "not_classified"}}}
        value, status = ena.our_field(rec, "platform")
        assert value == ""
        assert status == "not_classified"

    def test_incoherent_pair_reads_as_uncommitted(self):
        # models' coherence check raises ValueError; the validator must not crash
        rec = {"classifications": {"platform": {"value": None, "status": "classified"}}}
        assert ena.our_field(rec, "platform") == ("", "")
