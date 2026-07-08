"""Tests for the rule engine."""

import pytest

from src.meta_disco.models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    ClassificationResult,
    FileInfo,
)
from src.meta_disco.rule_engine import (
    ExtendedClassificationResult,
    ExtendedFileInfo,
    RuleEngine,
    evaluate_claims,
)


@pytest.fixture
def engine():
    """Create a rule engine with the unified rules."""
    return RuleEngine()


class TestExtensionExtraction:
    """Test extension extraction logic."""

    def test_simple_bam(self, engine):
        assert engine.rules.extract_extension("sample.bam") == ".bam"

    def test_compound_vcf_gz(self, engine):
        assert engine.rules.extract_extension("file.vcf.gz") == ".vcf.gz"

    def test_compound_fastq_gz(self, engine):
        assert engine.rules.extract_extension("sample.fastq.gz") == ".fastq.gz"

    def test_cram_with_dots(self, engine):
        assert engine.rules.extract_extension("sample.hg38.cram") == ".cram"

    def test_case_insensitive(self, engine):
        assert engine.rules.extract_extension("SAMPLE.BAM") == ".bam"
        assert engine.rules.extract_extension("File.VCF.GZ") == ".vcf.gz"

    def test_no_extension(self, engine):
        assert engine.rules.extract_extension("filename") == ""

    def test_gvcf_gz(self, engine):
        assert engine.rules.extract_extension("sample.g.vcf.gz") == ".g.vcf.gz"


class TestRuleMatching:
    """Test rule matching logic."""

    def test_alignment_rnaseq_filename(self, engine):
        """RNA-seq indicators in filename should set transcriptomic modality."""
        result = engine.classify(FileInfo(filename="sample_RNA_aligned.bam"))
        assert result.data_modality == "transcriptomic.bulk"
        assert result.confidence >= 0.80
        assert "alignment_rnaseq_filename" in result.rules_matched

    def test_alignment_wgs_filename(self, engine):
        """WGS indicators should set genomic modality with WGS assay_type."""
        result = engine.classify(FileInfo(filename="sample_WGS_aligned.bam"))
        assert result.data_modality == "genomic"
        assert result.confidence >= 0.85

    def test_alignment_ref_grch38(self, engine):
        """hg38/GRCh38 in filename should set reference assembly."""
        result = engine.classify(FileInfo(filename="sample.hg38.cram"))
        assert result.reference_assembly == "GRCh38"
        assert result.confidence >= 0.90

    def test_alignment_ref_grch37(self, engine):
        """hg19/GRCh37 in filename should set reference assembly."""
        result = engine.classify(FileInfo(filename="sample.hg19.bam"))
        assert result.reference_assembly == "GRCh37"

    def test_alignment_ref_chm13(self, engine):
        """CHM13/T2T in filename should set reference assembly."""
        result = engine.classify(FileInfo(filename="sample.chm13.cram"))
        assert result.reference_assembly == "CHM13"

    def test_rna_filename_sets_modality_regardless_of_size(self, engine):
        """RNA filename indicator should set transcriptomic modality."""
        result = engine.classify(
            FileInfo(filename="sample_RNA_aligned.bam", file_size=60_000_000_000)
        )
        assert result.data_modality == "transcriptomic.bulk"

    def test_star_aligner_indicates_rnaseq(self, engine):
        """STAR aligner output pattern should indicate RNA-seq."""
        result = engine.classify(
            FileInfo(filename="sample.Aligned.sortedByCoord.out.bam")
        )
        assert result.data_modality == "transcriptomic.bulk"
        assert result.confidence >= 0.90


class TestVariantFiles:
    """Test variant file classification."""

    def test_vcf_default_genomic(self, engine):
        """VCF files should default to genomic."""
        result = engine.classify(FileInfo(filename="sample.vcf"))
        assert result.data_modality == "genomic"
        assert result.confidence >= 0.85

    def test_vcf_gz_default_genomic(self, engine):
        """Compressed VCF files should default to genomic."""
        result = engine.classify(FileInfo(filename="sample.vcf.gz"))
        assert result.data_modality == "genomic"

    def test_vcf_with_ref_grch38(self, engine):
        """VCF with reference in filename."""
        result = engine.classify(FileInfo(filename="NA19189.chr2.hg38.vcf.gz"))
        assert result.data_modality == "genomic"
        assert result.reference_assembly == "GRCh38"


class TestThenStatus:
    """A rule authoring a non-classified status via `then.status` (#133)."""

    def _engine_with_rule(self, tmp_path, then):
        import yaml
        path = tmp_path / "rules.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump_all([
                {"extension_map": {".foo": "foo"}},
                {"rules": [{
                    "id": "foo_rule", "tier": 1, "scope": "extension",
                    "when": {"extensions": [".foo"]}, "then": then, "confidence": 1.0,
                }]},
            ], f)
        return RuleEngine(path)

    def test_status_only_field_is_not_applicable(self, tmp_path):
        engine = self._engine_with_rule(
            tmp_path, {"status": {"reference_assembly": "not_applicable"}})
        out = engine.classify_extended(FileInfo(filename="x.foo")).to_output_dict()
        assert out["reference_assembly"]["status"] == NOT_APPLICABLE
        assert out["reference_assembly"]["value"] is None

    def test_real_value_and_status_coexist_in_one_rule(self, tmp_path):
        # The mixed case (e.g. nanopore_fast5): a real value and a status in the
        # same then-clause resolve independently and correctly.
        engine = self._engine_with_rule(tmp_path, {
            "data_type": "raw_signal",
            "status": {"reference_assembly": "not_applicable"},
        })
        out = engine.classify_extended(FileInfo(filename="x.foo")).to_output_dict()
        assert out["data_type"]["status"] == CLASSIFIED
        assert out["data_type"]["value"] == "raw_signal"
        assert out["reference_assembly"]["status"] == NOT_APPLICABLE
        assert out["reference_assembly"]["value"] is None


class TestSetFieldValidation:
    """set_field rejects unknown fields/statuses instead of silently mis-storing."""

    def test_rejects_unknown_field(self):
        result = ExtendedClassificationResult()
        with pytest.raises(ValueError, match="unknown classification field"):
            result.set_field("platfrom", "ILLUMINA")  # typo

    def test_rejects_unknown_status(self):
        result = ExtendedClassificationResult()
        with pytest.raises(ValueError, match="unknown status"):
            result.set_field("data_modality", status="confict")  # typo for conflict

    def test_accepts_known_field_and_status(self):
        result = ExtendedClassificationResult()
        result.set_field("platform", "ILLUMINA")
        result.set_field("reference_assembly", status=NOT_APPLICABLE)
        assert result.platform == "ILLUMINA"
        assert result.status_of("platform") == CLASSIFIED
        assert result.reference_assembly is None
        assert result.status_of("reference_assembly") == NOT_APPLICABLE


class TestDerivativeFiles:
    """Test that derivative files (indices, checksums, logs) get not_applicable."""

    def test_index_bai(self, engine):
        """BAI index files should be not_applicable."""
        result = engine.classify_extended(FileInfo(filename="sample.bam.bai"))
        assert result.status_of("data_modality") == NOT_APPLICABLE

    def test_index_crai(self, engine):
        """CRAI index files should be not_applicable."""
        result = engine.classify_extended(FileInfo(filename="sample.cram.crai"))
        assert result.status_of("data_modality") == NOT_APPLICABLE

    def test_checksum_md5(self, engine):
        """MD5 checksum files should be not_applicable."""
        result = engine.classify_extended(FileInfo(filename="HG02558.final.cram.md5"))
        assert result.status_of("data_modality") == NOT_APPLICABLE

    def test_log_files(self, engine):
        """Log files should be not_applicable."""
        result = engine.classify_extended(FileInfo(filename="pipeline.log"))
        assert result.status_of("data_modality") == NOT_APPLICABLE


class TestSpecialFileTypes:
    """Test special file type classifications."""

    def test_plink_genomic(self, engine):
        """PLINK files should be genomic."""
        for ext in [".pgen", ".pvar", ".psam"]:
            result = engine.classify(FileInfo(filename=f"sample{ext}"))
            assert result.data_modality == "genomic"
            assert result.confidence >= 0.95

    def test_single_cell_matrix(self, engine):
        """Single-cell matrix files should be transcriptomic.single_cell."""
        result = engine.classify(FileInfo(filename="sample.h5ad"))
        assert result.data_modality == "transcriptomic.single_cell"
        assert result.confidence >= 0.90

    def test_single_cell_atac(self, engine):
        """Single-cell ATAC matrix should be epigenomic."""
        result = engine.classify(FileInfo(filename="sample_atac_peaks.h5ad"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"

    def test_methylation_idat(self, engine):
        """IDAT files should be epigenomic.methylation."""
        result = engine.classify(FileInfo(filename="sample.idat"))
        assert result.data_modality == "epigenomic.methylation"
        assert result.confidence >= 0.95

    def test_histology_svs(self, engine):
        """SVS files should be imaging.histology."""
        result = engine.classify(FileInfo(filename="GTEX-18A6Q-1126.svs"))
        assert result.data_modality == "imaging.histology"
        assert result.confidence >= 0.95


class TestFastqFiles:
    """Test FASTQ file classification."""

    def test_fastq_rna(self, engine):
        """FASTQ with RNA indicator."""
        result = engine.classify(FileInfo(filename="sample_rnaseq_R1.fastq.gz"))
        assert result.data_modality == "transcriptomic.bulk"

    def test_fastq_ambiguous(self, engine):
        """FASTQ without indicators is not classified for modality."""
        result = engine.classify_extended(FileInfo(filename="sample_R1.fastq.gz"))
        assert result.status_of("data_modality") == NOT_CLASSIFIED


class TestSignalTracks:
    """Test signal track classification."""

    def test_bigwig_chip(self, engine):
        """ChIP-seq bigwig files."""
        result = engine.classify(FileInfo(filename="sample_H3K27ac.bigwig"))
        assert result.data_modality == "epigenomic.histone_modification"

    def test_bigwig_atac(self, engine):
        """ATAC-seq bigwig files."""
        result = engine.classify(FileInfo(filename="sample_atac.bw"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"


class TestPeakFiles:
    """Test peak file classification (narrowPeak, broadPeak, etc.)."""

    def test_narrowpeak_chromatin_accessibility(self, engine):
        """narrowPeak files should be epigenomic.chromatin_accessibility."""
        result = engine.classify(FileInfo(filename="sample.narrowPeak"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"
        assert result.confidence >= 0.85

    def test_broadpeak_chromatin_accessibility(self, engine):
        """broadPeak files should be epigenomic.chromatin_accessibility."""
        result = engine.classify(FileInfo(filename="sample.broadPeak"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"

    def test_peaks_bed_chromatin_accessibility(self, engine):
        """BED files with 'peaks' should be epigenomic.chromatin_accessibility."""
        result = engine.classify(FileInfo(filename="atac_peaks.bed"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"

    def test_chip_peaks_histone_modification(self, engine):
        """ChIP-seq peak files should be epigenomic.histone_modification."""
        result = engine.classify(FileInfo(filename="H3K27ac_chip_peaks.bed"))
        assert result.data_modality == "epigenomic.histone_modification"
        assert result.confidence >= 0.90

    def test_summit_bed_chromatin_accessibility(self, engine):
        """Summit files should be epigenomic.chromatin_accessibility."""
        result = engine.classify(FileInfo(filename="sample_summits.bed"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"


class TestTextFiles:
    """Test text/tabular file classification."""

    def test_stats_file(self, engine):
        """QC stats files should be not_applicable."""
        result = engine.classify_extended(FileInfo(filename="sample.stats.txt"))
        assert result.status_of("data_modality") == NOT_APPLICABLE

    def test_count_matrix(self, engine):
        """Count matrix files should be transcriptomic."""
        result = engine.classify(FileInfo(filename="gene_counts.txt"))
        assert result.data_modality == "transcriptomic.bulk"

    def test_ambiguous_txt(self, engine):
        """Ambiguous text files are not classified for modality."""
        result = engine.classify_extended(FileInfo(filename="data.txt"))
        assert result.status_of("data_modality") == NOT_CLASSIFIED


class TestIntegration:
    """Integration tests against real filenames from API exploration."""

    def test_hifi_bam(self, engine):
        """HiFi reads BAM file."""
        result = engine.classify(
            FileInfo(filename="m64043_210211_005516.hifi_reads.bam")
        )
        assert result.data_modality == "genomic"
        assert result.confidence >= 0.70

    def test_vcf_with_chr(self, engine):
        """VCF with chromosome in filename."""
        result = engine.classify(FileInfo(filename="NA19189.chr2.hc.vcf.gz"))
        assert result.data_modality == "genomic"
        assert result.confidence >= 0.85

    def test_gtex_histology(self, engine):
        """GTEx histology image."""
        result = engine.classify(FileInfo(filename="GTEX-18A6Q-1126.svs"))
        assert result.data_modality == "imaging.histology"
        assert result.confidence >= 0.95

    def test_cram_md5(self, engine):
        """CRAM MD5 checksum should be not_applicable."""
        result = engine.classify_extended(FileInfo(filename="HG02558.final.cram.md5"))
        assert result.status_of("data_modality") == NOT_APPLICABLE

    def test_unknown_extension(self, engine):
        """Unknown extensions are not classified."""
        result = engine.classify_extended(FileInfo(filename="sample.xyz"))
        assert result.status_of("data_modality") == NOT_CLASSIFIED


class TestConflictingReferenceRules:
    """Test that conflicting reference_assembly rules produce not_classified."""

    def test_ambiguous_filename_two_refs(self, engine):
        """Filename with both CHM13 and hg38 should be not_classified."""
        result = engine.classify_extended(FileInfo(filename="CHM13.hg38.gff3.gz"))
        assert result.status_of("reference_assembly") == NOT_CLASSIFIED

    def test_liftover_chain_two_refs(self, engine):
        """Liftover chain with two references should be not_classified."""
        result = engine.classify_extended(FileInfo(filename="liftover.hg19.to.hg38.chain"))
        assert result.status_of("reference_assembly") == NOT_CLASSIFIED

    def test_single_ref_not_affected(self, engine):
        """Single reference in filename should still work."""
        result = engine.classify_extended(FileInfo(filename="sample.GRCh38.bed"))
        assert result.reference_assembly == "GRCh38"

    def test_conflict_evidence_recorded(self, engine):
        """Conflict should produce evidence with conflicting_reference_assembly_rules."""
        result = engine.classify_extended(FileInfo(filename="CHM13.hg38.gff3.gz"))
        ref_evidence = result.field_evidence.get("reference_assembly", [])
        rule_ids = [e["rule_id"] for e in ref_evidence]
        assert "conflicting_reference_assembly_rules" in rule_ids
        # Prior evidence should also be preserved
        assert len(ref_evidence) >= 2


class TestConflictingClassificationFields:
    """Test that conflict detection works for all classification fields, not just reference_assembly."""

    def test_data_modality_conflict(self, engine):
        """Same-tier rules disagreeing on data_modality produce not_classified."""
        result = engine.classify_extended(FileInfo(filename="sample_rnaseq_wgs_aligned.bam"))
        assert result.status_of("data_modality") == NOT_CLASSIFIED
        evidence = result.field_evidence.get("data_modality", [])
        rule_ids = [e["rule_id"] for e in evidence]
        assert "conflicting_data_modality_rules" in rule_ids

    def test_conflict_preserves_prior_evidence(self, engine):
        """Conflict marker is appended to existing evidence, not replaced."""
        result = engine.classify_extended(FileInfo(filename="CHM13.hg38.gff3.gz"))
        evidence = result.field_evidence.get("reference_assembly", [])
        rule_ids = [e["rule_id"] for e in evidence]
        # Both the original rule and the conflict marker should be present
        assert "filename_ref_grch38" in rule_ids or "filename_ref_chm13" in rule_ids
        assert "conflicting_reference_assembly_rules" in rule_ids

    def test_conflict_evidence_has_status_and_competing_values(self, engine):
        """Conflict evidence carries a not_classified status (in the status field,
        not the value slot) and the structured competing_values field."""
        result = engine.classify_extended(FileInfo(filename="CHM13.hg38.gff3.gz"))
        evidence = result.field_evidence.get("reference_assembly", [])
        conflict = [e for e in evidence if "conflicting_" in e["rule_id"]][0]
        assert conflict["status"] == NOT_CLASSIFIED
        assert "value" not in conflict
        assert set(conflict["competing_values"]) == {"GRCh38", "CHM13"}

    def test_normal_evidence_has_value_field(self, engine):
        """Every evidence entry should include the value that was set."""
        result = engine.classify_extended(FileInfo(filename="sample.GRCh38.bed"))
        evidence = result.field_evidence.get("reference_assembly", [])
        ref_entry = [e for e in evidence if e["rule_id"] == "filename_ref_grch38"][0]
        assert ref_entry["value"] == "GRCh38"


class TestEvaluateClaims:
    """Test the standalone evaluate_claims() function."""

    def test_no_claims(self):
        """No claims → not_classified (status), no value."""
        result = evaluate_claims([])
        assert result["status"] == NOT_CLASSIFIED
        assert result["value"] is None
        assert result["is_conflict"] is False
        assert result["reason"] == "no_claims"

    def test_single_claim(self):
        """Single claim → use it."""
        result = evaluate_claims([
            {"rule_id": "r1", "value": "genomic", "confidence": 0.90, "tier": 2},
        ])
        assert result["value"] == "genomic"
        assert result["confidence"] == 0.90
        assert result["reason"] == "single_claim"
        assert result["is_conflict"] is False

    def test_two_claims_agree(self):
        """Two claims with same value → unanimous, max confidence."""
        result = evaluate_claims([
            {"rule_id": "r1", "value": "genomic", "confidence": 0.80, "tier": 2},
            {"rule_id": "r2", "value": "genomic", "confidence": 0.95, "tier": 3},
        ])
        assert result["value"] == "genomic"
        assert result["confidence"] == 0.95
        assert result["reason"] == "unanimous"

    def test_disagree_different_tiers(self):
        """Higher tier wins when claims disagree."""
        result = evaluate_claims([
            {"rule_id": "r1", "value": "sequence", "confidence": 0.30, "tier": 1},
            {"rule_id": "r2", "value": "assembly", "confidence": 0.80, "tier": 2},
        ])
        assert result["value"] == "assembly"
        assert result["confidence"] == 0.80
        assert result["reason"] == "higher_specificity_override"
        assert result["is_conflict"] is False

    def test_disagree_same_tier(self):
        """Same tier, different values → conflict (not_classified status, no value)."""
        result = evaluate_claims([
            {"rule_id": "r1", "value": "GRCh38", "confidence": 0.90, "tier": 2},
            {"rule_id": "r2", "value": "CHM13", "confidence": 0.90, "tier": 2},
        ])
        assert result["status"] == NOT_CLASSIFIED
        assert result["value"] is None
        assert result["is_conflict"] is True
        assert result["reason"] == "conflict"
        assert set(result["competing_values"]) == {"GRCh38", "CHM13"}

    def test_three_claims_conflict_at_top_tier(self):
        """Lower tier agrees but top tier has conflict → conflict wins."""
        result = evaluate_claims([
            {"rule_id": "r1", "value": "genomic", "confidence": 0.30, "tier": 1},
            {"rule_id": "r2", "value": "genomic", "confidence": 0.90, "tier": 3},
            {"rule_id": "r3", "value": "transcriptomic.bulk", "confidence": 0.90, "tier": 3},
        ])
        assert result["status"] == NOT_CLASSIFIED
        assert result["value"] is None
        assert result["is_conflict"] is True

    def test_not_classified_claims_ignored(self):
        """Claims declaring not_classified (status) don't assert a value."""
        result = evaluate_claims([
            {"rule_id": "r1", "status": NOT_CLASSIFIED, "confidence": 0.0},
            {"rule_id": "r2", "value": "genomic", "confidence": 0.90, "tier": 2},
        ])
        assert result["value"] == "genomic"
        assert result["reason"] == "single_claim"

    def test_not_applicable_status_declaration(self):
        """A not_applicable status claim resolves to status not_applicable, value None."""
        result = evaluate_claims([
            {"rule_id": "r1", "status": NOT_APPLICABLE, "confidence": 1.0, "tier": 1},
        ])
        assert result["status"] == NOT_APPLICABLE
        assert result["value"] is None
        assert result["reason"] == "single_claim"

    def test_not_applicable_wins_over_real_value_same_tier(self):
        """NOT_APPLICABLE is a terminal declaration — wins without conflict."""
        result = evaluate_claims([
            {"rule_id": "r1", "status": NOT_APPLICABLE, "confidence": 1.0, "tier": 1},
            {"rule_id": "r2", "value": "genomic", "confidence": 0.90, "tier": 1},
        ])
        assert result["status"] == NOT_APPLICABLE
        assert result["value"] is None
        assert result["is_conflict"] is False
        assert result["reason"] == "not_applicable_terminal"

    def test_rule_authored_not_classified_is_not_no_claims(self):
        """A rule that intentionally declares not_classified is a real claim, not no_claims."""
        result = evaluate_claims([
            {"rule_id": "fastq_modality_unknown", "status": NOT_CLASSIFIED,
             "confidence": 0.0, "tier": 3,
             "reason": "FASTQ modality cannot be determined from reads alone"},
        ])
        assert result["status"] == NOT_CLASSIFIED
        assert result["value"] is None
        assert result["reason"] == "single_claim"
        # The claim should NOT be treated as "no_claims"
        assert result["reason"] != "no_claims"

    def test_rule_authored_not_classified_does_not_conflict_with_real(self):
        """A rule's not_classified declaration shouldn't conflict with a real value claim."""
        result = evaluate_claims([
            {"rule_id": "fastq_modality_unknown", "status": NOT_CLASSIFIED,
             "confidence": 0.0, "tier": 3},
            {"rule_id": "some_rule", "value": "genomic",
             "confidence": 0.90, "tier": 3},
        ])
        assert result["value"] == "genomic"
        assert result["is_conflict"] is False

    def test_rule_authored_not_classified_in_evidence(self, engine):
        """fastq_modality_unknown rationale should appear in evidence, not generic placeholder."""
        result = engine.classify_extended(
            FileInfo(filename="sample_R1.fastq.gz"), include_tier3=True
        )
        dm_evidence = result.field_evidence.get("data_modality", [])
        rule_ids = [e["rule_id"] for e in dm_evidence]
        # Should have the rule's ID, not the generic "not_classified" placeholder
        assert "fastq_modality_unknown" in rule_ids
        assert "not_classified" not in rule_ids


class TestAssayTypeInference:
    """Test that infer_assay_type records evidence correctly."""

    def test_inferred_assay_type_has_evidence(self, engine):
        """Inferred assay_type should have evidence with confidence 0.70."""
        file_info = ExtendedFileInfo(
            filename="sample.bam", file_size=60_000_000_000,
            file_size_gb=60.0, file_format=".bam",
        )
        result = engine.classify_extended(FileInfo(filename="sample.bam", file_size=60_000_000_000))
        # Set conditions that trigger WGS inference
        result.data_modality = "genomic"
        result.platform = "ILLUMINA"
        result.assay_type = None
        result.field_evidence["assay_type"] = []
        engine.infer_assay_type(result, file_info)
        assert result.assay_type == "WGS"
        evidence = result.field_evidence["assay_type"]
        assert len(evidence) == 1
        assert evidence[0]["rule_id"] == "infer_assay_type"
        assert evidence[0]["confidence"] == 0.70

    def test_inferred_assay_type_removes_not_classified_placeholder(self, engine):
        """Inference should remove stale not_classified placeholder evidence."""
        file_info = ExtendedFileInfo(
            filename="sample.bam", file_size=60_000_000_000,
            file_size_gb=60.0, file_format=".bam",
        )
        result = engine.classify_extended(FileInfo(filename="sample.bam", file_size=60_000_000_000))
        result.set_field("data_modality", "genomic")
        result.set_field("platform", "ILLUMINA")
        result.set_field("assay_type", status=NOT_CLASSIFIED)
        result.field_evidence["assay_type"] = [{
            "rule_id": "not_classified",
            "reason": "No rule determined a value for assay_type",
            "confidence": 0.0,
            "status": NOT_CLASSIFIED,
        }]
        engine.infer_assay_type(result, file_info)
        assert result.assay_type == "WGS"
        rule_ids = [e["rule_id"] for e in result.field_evidence["assay_type"]]
        assert "not_classified" not in rule_ids
        assert "infer_assay_type" in rule_ids


class TestReasonChain:
    """Test that reason chains are properly built."""

    def test_multiple_reasons(self, engine):
        """Multiple matching rules should accumulate reasons."""
        result = engine.classify(FileInfo(filename="sample_RNA.hg38.bam"))
        assert len(result.reasons) >= 2
        assert len(result.rules_matched) >= 2

    def test_reason_explains_decision(self, engine):
        """Reasons should explain why classification was made."""
        result = engine.classify(FileInfo(filename="sample.svs"))
        assert any("histology" in r.lower() or "svs" in r.lower() for r in result.reasons)


class TestSentinelValues:
    """Test that not_applicable/not_classified sentinels are used correctly."""

    def test_derivative_files_get_not_applicable(self, engine):
        """Index files get not_applicable for modality/platform/assay but not reference_assembly
        (reference IS applicable to indexes — it's determined by the parent file's alignment)."""
        result = engine.classify_extended(FileInfo(filename="sample.bam.bai"))
        assert result.status_of("data_modality") == NOT_APPLICABLE
        assert result.status_of("reference_assembly") == NOT_CLASSIFIED  # applicable but unknown without filename hint
        assert result.status_of("platform") == NOT_APPLICABLE
        assert result.status_of("assay_type") == NOT_APPLICABLE

    def test_unclassified_fields_get_not_classified(self, engine):
        """Files with unset fields should get not_classified."""
        result = engine.classify_extended(FileInfo(filename="sample.xyz"))
        assert result.status_of("data_modality") == NOT_CLASSIFIED
        assert result.status_of("reference_assembly") == NOT_CLASSIFIED

    def test_not_classified_evidence_includes_field_name(self, engine):
        """Evidence reason for not_classified should name the specific field."""
        result = engine.classify_extended(FileInfo(filename="sample.xyz"))
        checked = 0
        for fld in ["data_modality", "data_type", "platform", "reference_assembly", "assay_type"]:
            evidence = result.field_evidence[fld]
            nc_evidence = [e for e in evidence if e["rule_id"] == "not_classified"]
            assert nc_evidence, f"Expected not_classified evidence for {fld}"
            assert fld in nc_evidence[0]["reason"], \
                f"Expected '{fld}' in reason, got: {nc_evidence[0]['reason']}"
            checked += 1
        assert checked == 5

    def test_images_get_not_applicable_for_genomic_fields(self, engine):
        """Image files should get not_applicable for platform and reference."""
        result = engine.classify_extended(FileInfo(filename="sample.svs"))
        assert result.data_modality == "imaging.histology"
        assert result.status_of("platform") == NOT_APPLICABLE
        assert result.status_of("reference_assembly") == NOT_APPLICABLE

    def test_fastq_gets_not_applicable_reference(self, engine):
        """FASTQ files should get not_applicable for reference (unaligned reads)."""
        result = engine.classify_extended(FileInfo(filename="sample.fastq.gz"))
        assert result.status_of("reference_assembly") == NOT_APPLICABLE

    def test_fast5_gets_not_applicable_reference(self, engine):
        """FAST5 files should get not_applicable for reference (raw signal)."""
        result = engine.classify_extended(FileInfo(filename="sample.fast5"))
        assert result.status_of("reference_assembly") == NOT_APPLICABLE
        assert result.platform == "ONT"

    def test_bam_without_header_not_classified(self, engine):
        """BAM without header should leave modality as not_classified."""
        result = engine.classify_extended(
            ExtendedFileInfo(filename="sample.bam", file_size_gb=60.0)
        )
        # No header = no modality evidence, even for large files
        assert result.status_of("data_modality") == NOT_CLASSIFIED

    def test_png_all_fields_not_applicable(self, engine):
        """PNG files should get not_applicable for all non-applicable fields."""
        result = engine.classify_extended(FileInfo(filename="plot.png"))
        assert result.status_of("data_modality") == NOT_APPLICABLE
        assert result.status_of("platform") == NOT_APPLICABLE
        assert result.status_of("reference_assembly") == NOT_APPLICABLE
        assert result.status_of("assay_type") == NOT_APPLICABLE


class TestOutputDictStatus:
    """to_output_dict splits `status` from `value` (epic #116). Stage 3: sentinels
    live only in `status`; `value` is None unless the field is CLASSIFIED."""

    def test_every_dimension_gets_the_status_key(self, engine):
        # Every dimension entry carries `status` alongside the existing keys,
        # across a spread of file types.
        for filename in ("sample_WGS_aligned.bam", "sample.fastq.gz", "plot.png"):
            out = engine.classify_extended(FileInfo(filename=filename)).to_output_dict()
            for fld in CLASSIFICATION_FIELDS:
                assert set(out[fld]) == {"value", "status", "confidence", "evidence"}

    def test_status_pins_each_sentinel_state(self, engine):
        # Stage 3 shape: a real value classifies (value kept); each sentinel lives
        # in `status` with `value` nulled out — no sentinels in `value`.
        classified = engine.classify_extended(
            FileInfo(filename="sample_WGS_aligned.bam")).to_output_dict()["data_modality"]
        assert (classified["value"], classified["status"]) == ("genomic", CLASSIFIED)

        n_a = engine.classify_extended(
            FileInfo(filename="plot.png")).to_output_dict()["reference_assembly"]
        assert (n_a["value"], n_a["status"]) == (None, NOT_APPLICABLE)

        n_c = engine.classify_extended(
            ExtendedFileInfo(filename="sample.bam", file_size_gb=60.0)).to_output_dict()["data_modality"]
        assert (n_c["value"], n_c["status"]) == (None, NOT_CLASSIFIED)
