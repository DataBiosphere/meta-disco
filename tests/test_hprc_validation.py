"""Tests for HPRC validation mappings and helpers."""

import pytest

from meta_disco.models import field_value
from meta_disco.validation_maps import (
    HPRC_CATALOG_BASE_URL,
    HPRC_CATALOG_NAMES,
    HPRC_LIBRARY_SOURCE_MAP,
    HPRC_LIBRARY_STRATEGY_MAP,
    HPRC_PLATFORM_MAP,
    HPRC_REF_COORDINATES_MAP,
    extract_ref_from_annotation_type,
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
        assert HPRC_LIBRARY_SOURCE_MAP["TRANSCRIPTOMIC"] == "transcriptomic.bulk"


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


class TestFieldValue:
    def test_per_field_format(self):
        record = {"classifications": {"platform": {"value": "PACBIO"}}}
        assert field_value(record, "platform") == "PACBIO"

    def test_flat_format(self):
        record = {"platform": "ILLUMINA"}
        assert field_value(record, "platform") == "ILLUMINA"

    def test_nested_dict_value(self):
        record = {"platform": {"value": "ONT"}}
        assert field_value(record, "platform") == "ONT"

    def test_missing_field(self):
        record = {"classifications": {"platform": {"value": "PACBIO"}}}
        assert field_value(record, "data_modality") is None

    def test_empty_record(self):
        assert field_value({}, "platform") is None


class TestSharedConstants:
    def test_catalog_names_has_four(self):
        assert len(HPRC_CATALOG_NAMES) == 4

    def test_catalog_base_url(self):
        assert "human-pangenomics" in HPRC_CATALOG_BASE_URL


class TestValidateDimension:
    """A value more specific than HPRC's truth, under it in the vocabulary, matches (#473)."""

    def _score(self, ours, expected):
        from collections import Counter

        from validate_against_hprc import validate_dimension

        counters = Counter()
        mismatch = validate_dimension(ours, expected, counters, "reference_assembly")
        return mismatch, counters

    def test_a_release_under_the_truth_matches(self):
        mismatch, counters = self._score("T2T-CHM13v2.0", "CHM13")
        assert mismatch is None and counters["reference_assembly_match"] == 1

    def test_another_family_still_mismatches(self):
        mismatch, counters = self._score("GRCh38", "CHM13")
        assert mismatch == {"ours": "GRCh38", "expected": "CHM13"}
        assert counters["reference_assembly_mismatch"] == 1


class TestReportRunTime:
    """The validation report names the run its HPRC results were read from (#550)."""

    def _results(self, tmp_path, runs):
        import json

        path = tmp_path / "hprc_validation_results.json"
        path.write_text(json.dumps({"metadata": {"runs": runs}, "dimensions": {}}))
        return path

    def test_the_run_the_results_name(self, tmp_path):
        from generate_validation_report import report_run_time

        path = self._results(tmp_path, ["output/hprc/20260926_121312"])
        assert report_run_time(None, path) == "2026-09-26 12:13:12"

    def test_no_single_run_is_unrecorded_not_borrowed(self, tmp_path):
        from generate_validation_report import report_run_time

        assert report_run_time(None, self._results(tmp_path, [])) == "unrecorded"
        two = ["output/hprc/20260926_121312", "output/hprc/20260926_063656"]
        assert report_run_time(None, self._results(tmp_path, two)) == "unrecorded"

    def test_an_explicit_run_dir_wins(self, tmp_path):
        from pathlib import Path

        from generate_validation_report import report_run_time

        path = self._results(tmp_path, ["output/hprc/20260926_121312"])
        assert report_run_time(Path("output/hprc/20260101_000000"), path) == "2026-01-01 00:00:00"


def test_a_skipped_input_contributes_no_run(tmp_path):
    """Only inputs actually loaded name the validated runs: a missing path from another run is skipped (#550)."""
    import json

    from validate_against_hprc import validate_against_hprc

    from meta_disco.validation_maps import HPRC_CATALOG_NAMES

    catalogs = tmp_path / "catalogs"
    catalogs.mkdir()
    for name in HPRC_CATALOG_NAMES:  # cached and empty, so nothing is fetched
        (catalogs / f"{name}.json").write_text("[]")
    loaded = tmp_path / "hprc" / "20260926_121312" / "bam_classifications.json"
    loaded.parent.mkdir(parents=True)
    loaded.write_text(json.dumps({"classifications": []}))
    missing = tmp_path / "hprc" / "20260926_063656" / "vcf_classifications.json"

    out = tmp_path / "results.json"
    validate_against_hprc([loaded, missing], out, catalogs)
    assert json.loads(out.read_text())["metadata"]["runs"] == [loaded.parent.as_posix()]
