"""Tests for HPRC validation mappings and helpers."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.meta_disco.validation_maps import (
    HPRC_CATALOG_BASE_URL,
    HPRC_CATALOG_NAMES,
    HPRC_LIBRARY_SOURCE_MAP,
    HPRC_LIBRARY_STRATEGY_MAP,
    HPRC_PLATFORM_MAP,
    HPRC_REF_COORDINATES_MAP,
    extract_ref_from_annotation_type,
    get_classification_value,
)


class TestPlatformMap:
    def test_pacbio(self):
        assert HPRC_PLATFORM_MAP["PACBIO_SMRT"] == "PACBIO"

    def test_ont(self):
        assert HPRC_PLATFORM_MAP["OXFORD_NANOPORE"] == "ONT"

    def test_illumina(self):
        assert HPRC_PLATFORM_MAP["ILLUMINA"] == "ILLUMINA"


class TestLibrarySourceMap:
    def test_genomic(self):
        assert HPRC_LIBRARY_SOURCE_MAP["GENOMIC"] == "genomic"

    def test_transcriptomic(self):
        assert HPRC_LIBRARY_SOURCE_MAP["TRANSCRIPTOMIC"] == "transcriptomic"


class TestLibraryStrategyMap:
    def test_wgs(self):
        assert HPRC_LIBRARY_STRATEGY_MAP["WGS"] == "WGS"

    def test_hic(self):
        assert HPRC_LIBRARY_STRATEGY_MAP["Hi-C"] == "Hi-C"

    def test_isoseq_lowercase(self):
        assert HPRC_LIBRARY_STRATEGY_MAP["isoseq"] == "ISO-seq"

    def test_isoseq_mixed_case(self):
        assert HPRC_LIBRARY_STRATEGY_MAP["Iso-Seq"] == "ISO-seq"


class TestRefCoordinatesMap:
    def test_chm13(self):
        assert HPRC_REF_COORDINATES_MAP["chm13"] == "CHM13"

    def test_grch38(self):
        assert HPRC_REF_COORDINATES_MAP["grch38"] == "GRCh38"

    def test_grch37(self):
        assert HPRC_REF_COORDINATES_MAP["grch37"] == "GRCh37"


class TestExtractRefFromAnnotationType:
    """Test reference extraction from HPRC annotation type strings."""

    @pytest.mark.parametrize(
        "annotation_type,expected",
        [
            ("CAT_genes_chm13", "CHM13"),
            ("CAT_genes_hg38", "GRCh38"),
            ("chains CHM13", "CHM13"),
            ("chains GRCh38", "GRCh38"),
            ("Reference Mappings CHM13", "CHM13"),
            ("Reference Mappings GRCh38", "GRCh38"),
            ("ChromAlias T2T", "CHM13"),
        ],
    )
    def test_types_with_reference(self, annotation_type, expected):
        assert extract_ref_from_annotation_type(annotation_type) == expected

    @pytest.mark.parametrize(
        "annotation_type",
        [
            "CenSat",
            "DNA_BRNN",
            "Flagger_HiFi",
            "Flagger_ONT",
            "NucFlag",
            "Seg_Dups",
            "liftoff",
            "methylation",
            "ASat",
            "HSat",
            "Repeat_masker",
            "Repeat_masker Bed",
            "Repeat_masker Out",
            "TRF",
            "CAT Genes",
            "ChromAlias",
            "ChromAlias Gaps",
            "flagger_all_file_location",
            "flagger_unreliable_only_file_location",
            "flagger_unreliable_only_no_MT_file_location",
        ],
    )
    def test_de_novo_types_return_none(self, annotation_type):
        assert extract_ref_from_annotation_type(annotation_type) is None

    def test_empty_string(self):
        assert extract_ref_from_annotation_type("") is None


class TestGetClassificationValue:
    def test_per_field_format(self):
        record = {"classifications": {"platform": {"value": "PACBIO", "confidence": 0.9}}}
        assert get_classification_value(record, "platform") == "PACBIO"

    def test_flat_format(self):
        record = {"platform": "ILLUMINA"}
        assert get_classification_value(record, "platform") == "ILLUMINA"

    def test_nested_dict_value(self):
        record = {"platform": {"value": "ONT"}}
        assert get_classification_value(record, "platform") == "ONT"

    def test_missing_field(self):
        record = {"classifications": {"platform": {"value": "PACBIO"}}}
        assert get_classification_value(record, "data_modality") is None

    def test_empty_record(self):
        assert get_classification_value({}, "platform") is None


class TestSharedConstants:
    def test_catalog_names_has_four(self):
        assert len(HPRC_CATALOG_NAMES) == 4

    def test_catalog_base_url(self):
        assert "human-pangenomics" in HPRC_CATALOG_BASE_URL
