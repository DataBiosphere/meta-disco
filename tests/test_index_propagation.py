"""Tests for index file metadata propagation."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from classify_index_files import INDEX_TO_PARENT, get_parent_candidates, load_classifications, propagate_to_index_files


class TestParentCandidateGeneration:
    """Test parent filename candidate generation."""

    def test_vcf_gz_tbi(self):
        """VCF.gz.tbi should find VCF.gz parent."""
        candidates = get_parent_candidates("sample.vcf.gz.tbi", ".tbi")
        assert "sample.vcf.gz" in candidates
        assert len(candidates) == 1  # No junk candidates

    def test_bed_gz_tbi(self):
        """BED.gz.tbi should find BED.gz parent."""
        candidates = get_parent_candidates("sample.bed.gz.tbi", ".tbi")
        assert "sample.bed.gz" in candidates
        assert len(candidates) == 1

    def test_txt_gz_tbi(self):
        """TXT.gz.tbi (tabix-indexed TSV) should find TXT.gz parent."""
        candidates = get_parent_candidates("sample.txt.gz.tbi", ".tbi")
        assert "sample.txt.gz" in candidates
        assert len(candidates) == 1

    def test_bam_bai(self):
        """BAM.bai should find BAM parent."""
        candidates = get_parent_candidates("sample.bam.bai", ".bai")
        assert "sample.bam" in candidates
        assert len(candidates) == 1

    def test_cram_crai(self):
        """CRAM.crai should find CRAM parent."""
        candidates = get_parent_candidates("sample.cram.crai", ".crai")
        assert "sample.cram" in candidates
        assert len(candidates) == 1

    def test_pbi_index(self):
        """PBI (PacBio index) should find BAM parent."""
        candidates = get_parent_candidates("movie.subreads.bam.pbi", ".pbi")
        assert "movie.subreads.bam" in candidates

    def test_csi_bed_gz(self):
        """CSI index for BED.gz should find BED.gz parent."""
        candidates = get_parent_candidates("HG03652.regions.bed.gz.csi", ".csi")
        assert "HG03652.regions.bed.gz" in candidates
        assert len(candidates) == 1

    def test_pattern2_replacement(self):
        """Pattern 2: index extension replaces parent (rare case)."""
        # sample.bai -> sample.bam (no .bam in original name)
        candidates = get_parent_candidates("sample.bai", ".bai")
        assert "sample.bam" in candidates

    def test_complex_filename(self):
        """Complex filename with dots should work."""
        candidates = get_parent_candidates("HG01874.chr17.hc.vcf.gz.tbi", ".tbi")
        assert "HG01874.chr17.hc.vcf.gz" in candidates
        assert len(candidates) == 1


class TestNoJunkCandidates:
    """Regression tests to ensure no junk candidates are generated."""

    def test_no_double_gz(self):
        """Should not generate .gz.gz candidates."""
        candidates = get_parent_candidates("sample.vcf.gz.tbi", ".tbi")
        assert not any(".gz.gz" in c for c in candidates)

    def test_no_double_vcf_gz(self):
        """Should not generate .vcf.gz.vcf.gz candidates."""
        candidates = get_parent_candidates("sample.vcf.gz.tbi", ".tbi")
        assert not any(".vcf.gz.vcf.gz" in c for c in candidates)

    def test_no_double_bam(self):
        """Should not generate .bam.bam candidates."""
        candidates = get_parent_candidates("sample.bam.bai", ".bai")
        assert not any(".bam.bam" in c for c in candidates)

    def test_no_double_cram(self):
        """Should not generate .cram.cram candidates."""
        candidates = get_parent_candidates("sample.cram.crai", ".crai")
        assert not any(".cram.cram" in c for c in candidates)


class TestIndexToParentMapping:
    """Test the INDEX_TO_PARENT mapping is complete."""

    def test_tbi_has_common_extensions(self):
        """TBI should support common tabix-indexed formats."""
        tbi_exts = INDEX_TO_PARENT[".tbi"]
        assert ".vcf.gz" in tbi_exts
        assert ".bed.gz" in tbi_exts
        assert ".txt.gz" in tbi_exts

    def test_csi_has_vcf(self):
        """CSI should support VCF."""
        csi_exts = INDEX_TO_PARENT[".csi"]
        assert ".vcf.gz" in csi_exts

    def test_csi_has_bed_gz(self):
        """CSI should support BED.gz files."""
        csi_exts = INDEX_TO_PARENT[".csi"]
        assert ".bed.gz" in csi_exts

    def test_no_bare_gz(self):
        """Should not have bare .gz as a parent extension."""
        for index_ext, parent_exts in INDEX_TO_PARENT.items():
            assert ".gz" not in parent_exts, f"{index_ext} has bare .gz"


class TestLoadClassifications:
    """Test that load_classifications loads from multiple sources."""

    def test_loads_from_single_file(self, tmp_path):
        """Load classifications from one JSON file."""
        cls_file = tmp_path / "bam.json"
        cls_file.write_text(json.dumps({
            "classifications": [{
                "md5sum": "abc123",
                "file_name": "sample.bam",
                "classifications": {
                    "data_modality": {"value": "genomic", "confidence": 0.9, "evidence": []},
                    "data_type": {"value": "alignments", "confidence": 0.9, "evidence": []},
                    "platform": {"value": "ILLUMINA", "confidence": 0.9, "evidence": []},
                    "reference_assembly": {"value": "GRCh38", "confidence": 0.9, "evidence": []},
                    "assay_type": {"value": "WGS", "confidence": 0.9, "evidence": []},
                },
            }],
        }))
        result = load_classifications(cls_file)
        assert "abc123" in result
        assert result["abc123"]["data_modality"] == "genomic"
        assert result["abc123"]["platform"] == "ILLUMINA"

    def test_loads_from_multiple_files(self, tmp_path):
        """Load classifications from BAM + BED files."""
        bam_file = tmp_path / "bam.json"
        bam_file.write_text(json.dumps({
            "classifications": [{
                "md5sum": "bam_md5",
                "file_name": "sample.bam",
                "classifications": {
                    "data_modality": {"value": "genomic", "confidence": 0.9, "evidence": []},
                    "data_type": {"value": "alignments", "confidence": 0.9, "evidence": []},
                    "platform": {"value": "ILLUMINA", "confidence": 0.9, "evidence": []},
                    "reference_assembly": {"value": "GRCh38", "confidence": 0.9, "evidence": []},
                    "assay_type": {"value": "WGS", "confidence": 0.9, "evidence": []},
                },
            }],
        }))
        bed_file = tmp_path / "bed.json"
        bed_file.write_text(json.dumps({
            "classifications": [{
                "md5sum": "bed_md5",
                "file_name": "sample.regions.bed.gz",
                "classifications": {
                    "data_modality": {"value": "genomic", "confidence": 0.8, "evidence": []},
                    "data_type": {"value": "annotations", "confidence": 0.8, "evidence": []},
                    "platform": {"value": "not_classified", "confidence": 0.0, "evidence": []},
                    "reference_assembly": {"value": "GRCh38", "confidence": 0.8, "evidence": []},
                    "assay_type": {"value": "not_classified", "confidence": 0.0, "evidence": []},
                },
            }],
        }))
        result = load_classifications(bam_file, bed_file)
        assert "bam_md5" in result
        assert "bed_md5" in result
        assert result["bed_md5"]["data_modality"] == "genomic"
        assert result["bed_md5"]["data_type"] == "annotations"

    def test_skips_missing_files(self, tmp_path):
        """Missing files are silently skipped."""
        result = load_classifications(tmp_path / "nonexistent.json")
        assert result == {}

    def test_csi_inherits_from_bed_parent(self, tmp_path):
        """End-to-end: a .csi index file inherits classification from its .bed.gz parent.

        This is the regression that #41 fixes — previously BED classifications were
        not loaded, so .csi files for .bed.gz parents got None for all fields."""
        # Create metadata with a BED parent and its CSI index in the same dataset
        metadata_file = tmp_path / "metadata.json"
        metadata_file.write_text(json.dumps([
            {
                "file_name": "HG03652.regions.bed.gz",
                "file_format": ".bed.gz",
                "file_md5sum": "bed_parent_md5",
                "dataset_id": "ds1",
                "dataset_title": "test_dataset",
                "entry_id": "entry_bed",
            },
            {
                "file_name": "HG03652.regions.bed.gz.csi",
                "file_format": ".csi",
                "file_md5sum": "csi_child_md5",
                "dataset_id": "ds1",
                "dataset_title": "test_dataset",
                "entry_id": "entry_csi",
            },
        ]))

        # Create BED classification output
        bed_cls_file = tmp_path / "bed_classifications.json"
        bed_cls_file.write_text(json.dumps({
            "classifications": [{
                "md5sum": "bed_parent_md5",
                "file_name": "HG03652.regions.bed.gz",
                "classifications": {
                    "data_modality": {"value": "genomic", "confidence": 0.8, "evidence": []},
                    "data_type": {"value": "annotations", "confidence": 0.8, "evidence": []},
                    "platform": {"value": "not_classified", "confidence": 0.0, "evidence": []},
                    "reference_assembly": {"value": "CHM13", "confidence": 0.9, "evidence": []},
                    "assay_type": {"value": "not_classified", "confidence": 0.0, "evidence": []},
                },
            }],
        }))

        # Run propagation with BED as a source
        output_file = tmp_path / "index_output.json"
        propagate_to_index_files(metadata_file, [bed_cls_file], output_file)

        # Verify the CSI index inherited from the BED parent
        with open(output_file) as f:
            output = json.load(f)
        index_cls = output["classifications"]
        assert len(index_cls) == 1
        csi = index_cls[0]
        assert csi["file_name"] == "HG03652.regions.bed.gz.csi"
        assert csi["parent_file"] == "HG03652.regions.bed.gz"
        cls = csi["classifications"]
        assert cls["data_modality"]["value"] == "genomic"
        assert cls["data_type"]["value"] == "annotations"
        assert cls["reference_assembly"]["value"] == "CHM13"
        assert cls["data_modality"]["evidence"][0]["rule_id"] == "inherited_from_parent"

    def test_tbi_inherits_from_vcf_parent(self, tmp_path):
        """End-to-end: a .tbi index inherits from its .vcf.gz parent."""
        metadata_file = tmp_path / "metadata.json"
        metadata_file.write_text(json.dumps([
            {"file_name": "sample.vcf.gz", "file_format": ".vcf.gz",
             "file_md5sum": "vcf_md5", "dataset_id": "ds1",
             "dataset_title": "test", "entry_id": "e1"},
            {"file_name": "sample.vcf.gz.tbi", "file_format": ".tbi",
             "file_md5sum": "tbi_md5", "dataset_id": "ds1",
             "dataset_title": "test", "entry_id": "e2"},
        ]))
        vcf_cls = tmp_path / "vcf.json"
        vcf_cls.write_text(json.dumps({"classifications": [{
            "md5sum": "vcf_md5", "file_name": "sample.vcf.gz",
            "classifications": {
                "data_modality": {"value": "genomic", "confidence": 0.85, "evidence": []},
                "data_type": {"value": "variants.germline", "confidence": 0.9, "evidence": []},
                "platform": {"value": "not_classified", "confidence": 0.0, "evidence": []},
                "reference_assembly": {"value": "GRCh38", "confidence": 0.98, "evidence": []},
                "assay_type": {"value": "not_classified", "confidence": 0.0, "evidence": []},
            },
        }]}))
        output_file = tmp_path / "out.json"
        propagate_to_index_files(metadata_file, [vcf_cls], output_file)
        with open(output_file) as f:
            output = json.load(f)
        assert len(output["classifications"]) == 1
        cls = output["classifications"][0]["classifications"]
        assert cls["data_modality"]["value"] == "genomic"
        assert cls["data_type"]["value"] == "variants.germline"
        assert cls["reference_assembly"]["value"] == "GRCh38"

    def test_bai_inherits_from_bam_parent(self, tmp_path):
        """End-to-end: a .bai index inherits from its .bam parent."""
        metadata_file = tmp_path / "metadata.json"
        metadata_file.write_text(json.dumps([
            {"file_name": "sample.bam", "file_format": ".bam",
             "file_md5sum": "bam_md5", "dataset_id": "ds1",
             "dataset_title": "test", "entry_id": "e1"},
            {"file_name": "sample.bam.bai", "file_format": ".bai",
             "file_md5sum": "bai_md5", "dataset_id": "ds1",
             "dataset_title": "test", "entry_id": "e2"},
        ]))
        bam_cls = tmp_path / "bam.json"
        bam_cls.write_text(json.dumps({"classifications": [{
            "md5sum": "bam_md5", "file_name": "sample.bam",
            "classifications": {
                "data_modality": {"value": "transcriptomic.bulk", "confidence": 0.95, "evidence": []},
                "data_type": {"value": "alignments", "confidence": 0.9, "evidence": []},
                "platform": {"value": "ILLUMINA", "confidence": 0.95, "evidence": []},
                "reference_assembly": {"value": "GRCh38", "confidence": 0.98, "evidence": []},
                "assay_type": {"value": "RNA-seq", "confidence": 0.95, "evidence": []},
            },
        }]}))
        output_file = tmp_path / "out.json"
        propagate_to_index_files(metadata_file, [bam_cls], output_file)
        with open(output_file) as f:
            output = json.load(f)
        assert len(output["classifications"]) == 1
        cls = output["classifications"][0]["classifications"]
        assert cls["data_modality"]["value"] == "transcriptomic.bulk"
        assert cls["platform"]["value"] == "ILLUMINA"
        assert cls["assay_type"]["value"] == "RNA-seq"

    def test_no_matching_parent_goes_to_unmatched(self, tmp_path):
        """Index file with no parent in metadata goes to unmatched_files, not classifications."""
        metadata_file = tmp_path / "metadata.json"
        metadata_file.write_text(json.dumps([
            {"file_name": "orphan.bam.bai", "file_format": ".bai",
             "file_md5sum": "orphan_md5", "dataset_id": "ds1",
             "dataset_title": "test", "entry_id": "e1"},
        ]))
        # No classifications to load — empty file
        empty_cls = tmp_path / "empty.json"
        empty_cls.write_text(json.dumps({"classifications": []}))
        output_file = tmp_path / "out.json"
        propagate_to_index_files(metadata_file, [empty_cls], output_file)
        with open(output_file) as f:
            output = json.load(f)
        assert len(output["classifications"]) == 0
        assert len(output["unmatched_files"]) == 1
        assert output["unmatched_files"][0]["file_name"] == "orphan.bam.bai"
        assert output["unmatched_files"][0]["reason"] == "no_matching_parent_in_dataset"

    def test_parent_found_but_not_classified(self, tmp_path):
        """Parent exists in metadata but has no classification — index inherits None values."""
        metadata_file = tmp_path / "metadata.json"
        metadata_file.write_text(json.dumps([
            {"file_name": "sample.bam", "file_format": ".bam",
             "file_md5sum": "bam_md5", "dataset_id": "ds1",
             "dataset_title": "test", "entry_id": "e1"},
            {"file_name": "sample.bam.bai", "file_format": ".bai",
             "file_md5sum": "bai_md5", "dataset_id": "ds1",
             "dataset_title": "test", "entry_id": "e2"},
        ]))
        # Parent exists in metadata but not in classifications
        empty_cls = tmp_path / "empty.json"
        empty_cls.write_text(json.dumps({"classifications": []}))
        output_file = tmp_path / "out.json"
        propagate_to_index_files(metadata_file, [empty_cls], output_file)
        with open(output_file) as f:
            output = json.load(f)
        # Parent filename matched but md5 not in classifications → inherits None
        assert len(output["classifications"]) == 1
        cls = output["classifications"][0]["classifications"]
        assert cls["data_modality"]["value"] is None
        assert cls["data_modality"]["evidence"][0]["reason"].startswith("Parent file")
