"""Tests for the ENA validator's join key and vocabulary mapping (#330)."""

import json
from pathlib import Path

import pytest
import validate_ena_accessions as ena
import yaml

from meta_disco.validation_maps import ENA_LIBRARY_STRATEGY_MAP

SCHEMA = Path(__file__).parent.parent / "src" / "meta_disco" / "schema" / "classification.yaml"


class TestStrategyMap:
    def test_values_are_valid_assay_enum_spellings(self):
        enum = yaml.safe_load(SCHEMA.read_text())["enums"]["assay_type_enum"]["permissible_values"]
        for strategy, assay in ENA_LIBRARY_STRATEGY_MAP.items():
            assert assay in enum, f"{strategy!r} maps to {assay!r}, not in assay_type_enum"

    def test_expected_strategies_present(self):
        for strategy in ("WGS", "WXS", "RNA-Seq"):
            assert strategy in ENA_LIBRARY_STRATEGY_MAP


class TestExpectedModality:
    """What ENA's metadata says about modality, if anything (#563)."""

    @pytest.mark.parametrize("strategy", ["WGS", "WXS", "WGA"])
    def test_a_genome_or_exome_strategy_says_genomic(self, strategy):
        assert ena.expected_modality_from_ena("GENOMIC", strategy) == "genomic"

    @pytest.mark.parametrize("strategy", ["Hi-C", "Bisulfite-Seq", "ATAC-seq", "ChIP-Seq", None])
    def test_a_genomic_source_alone_says_nothing(self, strategy):
        # GENOMIC names the molecule, which Hi-C, bisulfite, ATAC and ChIP libraries share
        assert ena.expected_modality_from_ena("GENOMIC", strategy) is None

    @pytest.mark.parametrize(("source", "strategy"), [("TRANSCRIPTOMIC", None), (None, "RNA-Seq"), (None, "FL-cDNA")])
    def test_an_rna_source_or_strategy_says_transcriptomic(self, source, strategy):
        assert ena.expected_modality_from_ena(source, strategy) == "transcriptomic"

    def test_no_metadata_says_nothing(self):
        assert ena.expected_modality_from_ena(None, None) is None


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


class TestAssayVerdict:
    """The assay verdict reads assay_type's is_a tree (#533)."""

    def _validate(self, tmp_path, monkeypatch, assay):
        record = {
            "file_name": "ERR123456_1.fastq.gz",
            "classifications": {
                "platform": {"value": "ILLUMINA", "status": "classified"},
                "assay_type": {"value": assay, "status": "classified"},
            },
        }
        source = tmp_path / "in.json"
        source.write_text(json.dumps([record]))
        ena_run = {"instrument_platform": "ILLUMINA", "library_strategy": "RNA-Seq", "library_source": ""}
        monkeypatch.setattr(ena, "fetch_ena_metadata", lambda acc: ena_run)
        return ena.validate_against_ena(source, tmp_path / "out.json", workers=1)

    @pytest.mark.parametrize("assay", ["RNA-seq", "snRNA-seq", "SHARE-seq"])
    def test_a_term_at_or_below_enas_matches(self, tmp_path, monkeypatch, assay):
        assert self._validate(tmp_path, monkeypatch, assay)["assay_match"] == 1

    def test_a_term_outside_enas_subtree_mismatches(self, tmp_path, monkeypatch):
        assert self._validate(tmp_path, monkeypatch, "snATAC-seq")["assay_mismatch"] == 1
