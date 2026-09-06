"""End-to-end evaluation tests for classification pipeline.

These test the ACTUAL script functions with REAL cached evidence files,
not the internal classify functions directly. The input is a file
(via md5 -> cached evidence), the output is the JSON record that would
appear in the output file.

For rule-engine-only classifiers (BED, images, auxiliary), the input
is a FileInfo and the output is an ExtendedClassificationResult.

Each fixture below is a real file: an md5 that the corpus snapshot contains and whose
fetched evidence is in the local cache. Both can rot when the catalog moves, so every
call goes through a guarded wrapper (:func:`~tests.corpus_fixtures.require_corpus_file`)
that skips with the cause named rather than falling through to a live fetch (#381).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# Import the actual script functions
from classify_bam_files import classify_single_file as _classify_bam
from classify_fasta_files import classify_single_fasta as _classify_fasta
from classify_fastq_files import classify_single_fastq as _classify_fastq
from classify_vcf_files import classify_single_vcf as _classify_vcf

from meta_disco.evidence import SegmentTag
from meta_disco.fetchers import parse_gfa_segment_tags
from meta_disco.file_name import FileName
from meta_disco.file_types import BAM_CONFIG, FASTA_CONFIG, FASTQ_CONFIG, VCF_CONFIG
from meta_disco.header_classifier import classify_from_gfa_segment_tags
from meta_disco.models import (
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    FileInfo,
    field_status,
    field_value,
)
from meta_disco.rule_engine import CONTENT_TIER, RuleEngine, evaluate_claims
from tests.corpus_fixtures import require_corpus_file

engine = RuleEngine()


# Guarded wrappers around the four script functions. Each checks the fixture against the
# corpus snapshot and the evidence cache before classifying, so a fixture the corpus has
# dropped skips with that reason instead of 404ing its way to an inscrutable failure.
# The tests call these under the script functions' own names, so a test body reads as a
# direct call to the code under test.


def classify_bam(md5sum, file_name, **kwargs):
    """Classify a BAM/CRAM fixture, skipping when the corpus can no longer supply it."""
    require_corpus_file(md5sum, BAM_CONFIG.name)
    return _classify_bam(md5sum, file_name, **kwargs)


def classify_vcf(md5sum, file_name, **kwargs):
    """Classify a VCF fixture, skipping when the corpus can no longer supply it."""
    require_corpus_file(md5sum, VCF_CONFIG.name)
    return _classify_vcf(md5sum, file_name, **kwargs)


def classify_fastq(md5sum, file_name, **kwargs):
    """Classify a FASTQ fixture, skipping when the corpus can no longer supply it."""
    require_corpus_file(md5sum, FASTQ_CONFIG.name)
    return _classify_fastq(md5sum, file_name, **kwargs)


def classify_fasta(md5sum, file_name, **kwargs):
    """Classify a FASTA fixture, skipping when the corpus can no longer supply it."""
    require_corpus_file(md5sum, FASTA_CONFIG.name)
    return _classify_fasta(md5sum, file_name, **kwargs)


def get_val(record, field):
    """Extract a classification field's value (delegates to models.field_value)."""
    return field_value(record, field)


def assert_output_format(record):
    """Assert the record has correct top-level + per-field structure."""
    assert "file_name" in record, "Missing file_name"
    assert "md5sum" in record, "Missing md5sum"
    assert "classifications" in record, "Missing classifications wrapper"
    cls = record["classifications"]
    for field in ["data_modality", "data_type", "platform", "reference_assembly", "assay_type"]:
        assert field in cls, f"Missing classification field: {field}"
        entry = cls[field]
        assert isinstance(entry, dict), f"{field} should be dict"
        assert "value" in entry, f"{field} missing 'value'"
        assert "status" in entry, f"{field} missing 'status'"
        assert "evidence" in entry, f"{field} missing 'evidence'"
        # assay_type may be set by post-hoc inference which doesn't produce evidence
        if field != "assay_type":
            assert len(entry["evidence"]) > 0, f"{field} has empty evidence"


# =============================================================================
# BAM/CRAM — end-to-end through classify_bam_files.classify_single_file
# =============================================================================


@pytest.mark.e2e
class TestBamE2E:
    """End-to-end BAM classification from cached headers."""

    @staticmethod
    def classify_grch38_cram():
        """simons_data_sample_207.cram — 125.5 GB Illumina CRAM aligned to GRCh38.

        Three tests below read this one fixture, so it is pinned here once: a re-pin at
        the next catalog migration is a single edit, not three identical ones.
        """
        return classify_bam(
            "a52a5f60403a9f7796ec8f0d87bd9081",
            "simons_data_sample_207.cram",
            file_size=125476999922,
            file_format=".cram",
        )

    def test_grch38_aligned_bam(self):
        """A GRCh38-aligned Illumina CRAM classifies on all five dimensions."""
        result = self.classify_grch38_cram()
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "reference_assembly") == "GRCh38"
        assert get_val(result, "platform") == "ILLUMINA"
        assert get_val(result, "data_modality") == "genomic"  # from aligned reference contigs
        assert get_val(result, "data_type") == "alignments"
        assert get_val(result, "assay_type") == "WGS"

    def test_pacbio_unaligned_reads(self):
        """PacBio reads BAM — 363.9 GB, unaligned, reference N/A.

        The filename carries no `hifi`/`pacbio` token, so nothing claims a modality and
        the post-hoc assay inference — which needs one — leaves assay_type unclassified.
        Platform comes from the header's @RG PL alone.
        """
        result = classify_bam(
            "722143247e28f39ccac721728e4a0076",
            "m84046_230630_233157_s3.bc2069--bc2069.bam",
            file_size=363856209058,
            file_format=".bam",
        )
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "PACBIO"
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE
        assert field_status(result, "assay_type") == NOT_CLASSIFIED

    def test_ont_bam(self):
        """ONT BAM file — 69.8 GB."""
        result = classify_bam(
            "000e5edf6937cccf67767fb886626655",
            "06_28_22_R941_HG02922_3_Guppy_6.5.7_450bps_modbases_5mc_cg_sup_prom_pass.bam",
            file_size=69806670027,
            file_format=".bam",
        )
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ONT"
        assert get_val(result, "assay_type") == "WGS"

    def test_no_stale_evidence(self):
        """reference_assembly should not have stale not_classified evidence."""
        result = self.classify_grch38_cram()
        assert result is not None
        cls = result["classifications"]
        ref_evidence = cls["reference_assembly"]["evidence"]
        stale = [e for e in ref_evidence if e.get("marker") == "not_classified"]
        assert len(stale) == 0, f"Stale not_classified marker: {stale}"

    def test_star_rnaseq_bam(self):
        """GM20525-10-2.bam — 6.7 GB STAR-aligned RNA-seq."""
        result = classify_bam(
            "000811b87381c4dd9e5d7a940be14cee", "GM20525-10-2.bam", file_size=6694895254, file_format=".bam"
        )
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "transcriptomic.bulk"
        assert get_val(result, "data_type") == "alignments"
        assert get_val(result, "assay_type") == "RNA-seq"

    def test_platform_detection_meaningful(self):
        """Platform detection from @RG PL: should classify a platform value."""
        result = self.classify_grch38_cram()
        assert result is not None
        cls = result["classifications"]
        platform_val = cls["platform"]["value"]
        assert platform_val is not None, f"Platform should be classified, got {platform_val}"

    def test_illumina_cram_wgs_assay_type(self):
        """HG00741.final.cram — 15.9 GB Illumina CRAM should infer WGS.

        Assay type inference depends on platform (from tier 3 header rules)
        and file size, so it runs in the post-hoc assay_type_rules phase.
        """
        result = classify_bam(
            "cce22695c03f0f583384e5335a9965d7", "HG00741.final.cram", file_size=15868198733, file_format=".cram"
        )
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ILLUMINA"
        assert get_val(result, "assay_type") == "WGS"

    def test_rnaseq_bam_assay_type(self):
        """HG03382.bam — 5.5 GB STAR-aligned RNA-seq."""
        result = classify_bam(
            "60fbc0142751adebc0aa81a22ff3c9fd", "HG03382.bam", file_size=5521863634, file_format=".bam"
        )
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "transcriptomic.bulk"
        assert get_val(result, "assay_type") == "RNA-seq"


# =============================================================================
# VCF — end-to-end through classify_vcf_files.classify_single_vcf
# =============================================================================


@pytest.mark.e2e
class TestVcfE2E:
    """End-to-end VCF classification from cached headers."""

    def test_haplotypecaller_vcf(self):
        """HG03854.chrY.hc.vcf.gz — 3.7 MB HaplotypeCaller germline."""
        result = classify_vcf("00001845984e9c9a66433f9fa8476f99", "HG03854.chrY.hc.vcf.gz", file_size=3748178)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert field_status(result, "assay_type") == NOT_CLASSIFIED

    def test_single_chrom_reference_detection(self):
        """Single-chromosome VCF should still identify reference assembly."""
        result = classify_vcf("0000d4b336dbc16a216ebdfeaf092702", "HG01809.chr21.hc.vcf.gz", file_size=76348632)
        assert result is not None
        ref = get_val(result, "reference_assembly")
        assert ref in ("GRCh38", "GRCh37", "CHM13"), f"Expected a reference, got {ref}"

    def test_vcf_has_contig_evidence(self):
        """VCF reference should come from contig length detection."""
        result = classify_vcf("0000b1430a498c7774dd33a5a58677ad", "NA21125.chr2.hc.vcf.gz", file_size=443147740)
        assert result is not None
        cls = result["classifications"]
        ref_evidence = cls["reference_assembly"]["evidence"]
        rule_ids = [e["rule_id"] for e in ref_evidence]
        assert "vcf_contig_length" in rule_ids, f"Expected vcf_contig_length, got {rule_ids}"

    def test_sniffles_sv_vcf(self):
        """Sniffles SV VCF — 13.7 MB uncompressed structural variant calls."""
        result = classify_vcf(
            "4869136a1c7b5b7d01a8b5b7d8f8cca6", "sniffles_sv.vcf", file_size=13726785, is_gzipped=False
        )
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"

    def test_vcf_no_stale_evidence(self):
        """VCF reference_assembly should not have stale not_classified evidence."""
        result = classify_vcf("0000b1430a498c7774dd33a5a58677ad", "NA21125.chr2.hc.vcf.gz", file_size=443147740)
        assert result is not None
        cls = result["classifications"]
        ref = cls["reference_assembly"]
        if field_status(result, "reference_assembly") != NOT_CLASSIFIED:
            stale = [e for e in ref["evidence"] if e.get("marker") == "not_classified"]
            assert len(stale) == 0, f"Stale marker: {stale}"


# =============================================================================
# FASTQ — end-to-end through classify_fastq_files.classify_single_fastq
# =============================================================================


@pytest.mark.e2e
class TestFastqE2E:
    """End-to-end FASTQ classification from cached read names."""

    def test_illumina_fastq(self):
        """GM20294_R1_001.fastq.gz — 2.1 GB Illumina paired read."""
        result = classify_fastq("00077512aa3448912698292770d41ca5", "GM20294_R1_001.fastq.gz", file_size=2054321679)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ILLUMINA"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE
        assert field_status(result, "assay_type") == NOT_CLASSIFIED  # modality unknown, so no WES/WGS inference

    def test_ena_reformatted_fastq(self):
        """ERR3989178_1.fastq.gz — 13.5 GB ENA-reformatted with accession."""
        result = classify_fastq("0008a97d74c385aeb7eed75f33601d59", "ERR3989178_1.fastq.gz", file_size=13477702401)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "ILLUMINA"

    def test_fastq_reference_not_applicable(self):
        """All FASTQ files should have reference N/A (raw reads)."""
        result = classify_fastq(
            "000644fa14ab21a7106a746664d58aa9", "HG02486x02PE20573_1_sequence.fastq.gz", file_size=84212465
        )
        assert result is not None
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE

    def test_pacbio_ccs_fastq(self):
        """PacBio CCS/HiFi FASTQ — 28.6 GB, should detect PacBio platform."""
        result = classify_fastq(
            "0073d35c9f5b68a739e3daf50a227f72", "HG01109.m64043_200830_075523.dc.q20.fastq.gz", file_size=28614484832
        )
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "platform") == "PACBIO"
        assert field_status(result, "data_modality") == NOT_CLASSIFIED
        assert field_status(result, "assay_type") == NOT_CLASSIFIED  # modality unknown, so no WGS inference

    def test_mgi_fastq(self):
        """MGI/BGI platform FASTQ — 32.3 GB."""
        result = classify_fastq("00c68ff0f9e0217d422c57e8948d4bb4", "IGVFFI6614EZDQ.fastq.gz", file_size=32327542019)
        assert result is not None
        assert_output_format(result)
        platform = get_val(result, "platform")
        assert platform in ("MGI", "ILLUMINA") or field_status(result, "platform") == NOT_CLASSIFIED, (
            f"Unexpected platform: {platform}"
        )


# =============================================================================
# RULE ENGINE — extension/filename based (no headers)
# =============================================================================


class TestRuleEngineE2E:
    """Rule engine classification from filename/metadata only."""

    def test_histology_svs(self):
        result = engine.classify_extended(FileInfo.from_filename("GTEX-18A6Q-1126.svs"))
        assert result.data_modality == "imaging.histology"
        assert result.status_of("platform") == NOT_APPLICABLE
        assert result.status_of("reference_assembly") == NOT_APPLICABLE

    def test_fast5_raw_signal(self):
        result = engine.classify_extended(FileInfo.from_filename("PAK57726.fast5"))
        assert result.status_of("data_modality") == NOT_CLASSIFIED
        assert result.data_type == "raw_signal"
        assert result.platform == "ONT"
        assert result.status_of("reference_assembly") == NOT_APPLICABLE

    def test_pod5_raw_signal(self):
        result = engine.classify_extended(FileInfo.from_filename("sample_run.pod5"))
        assert result.status_of("data_modality") == NOT_CLASSIFIED
        assert result.data_type == "raw_signal"
        assert result.platform == "ONT"
        assert result.status_of("reference_assembly") == NOT_APPLICABLE

    def test_flnc_bam_is_transcriptomic(self):
        """IsoSeq flnc BAM should be transcriptomic, not genomic."""
        result = engine.classify_extended(FileInfo.from_filename("HG00097.lymph.m84203_240914_042802_s4.flnc.bam"))
        assert result.data_modality == "transcriptomic.bulk"

    def test_isoseq_bam_is_transcriptomic(self):
        """BAM with isoseq in filename should be transcriptomic."""
        result = engine.classify_extended(FileInfo.from_filename("sample.isoseq.bam"))
        assert result.data_modality == "transcriptomic.bulk"

    def test_plain_bam_no_modality(self):
        """BAM without header or platform signals should not get genomic modality."""
        result = engine.classify_extended(FileInfo.from_filename("sample.reads.bam"))
        assert result.status_of("data_modality") == NOT_CLASSIFIED

    def test_salmon_quant_sf_is_transcriptomic_quantification(self):
        """A Salmon quant.sf is a single-sample transcript abundance table (#157)."""
        result = engine.classify_extended(FileInfo.from_filename("NUFIP1-BGRSLV04-28_quant.sf"))
        assert result.data_modality == "transcriptomic.bulk"
        assert result.data_type == "quantification"
        assert result.assay_type == "RNA-seq"

    def test_bare_sf_stays_not_classified(self):
        """Only a token-boundary `quant.sf` is treated as Salmon output; any other
        `.sf` name stays not_classified rather than being over-claimed.

        So `something.sf` (not Salmon) and `frequant.sf` (a substring match, not a
        token boundary) both stay not_classified.
        """
        for name in ("something.sf", "frequant.sf"):
            result = engine.classify_extended(FileInfo.from_filename(name))
            assert result.status_of("data_type") == NOT_CLASSIFIED, name

    def test_plink_1000g(self):
        result = engine.classify_extended(
            FileInfo.from_filename("IBS.3.pgen", dataset_title="ANVIL_1000G_PRIMED_data_model")
        )
        assert result.data_modality == "genomic"
        assert result.reference_assembly == "GRCh38"

    def test_bed_methylation(self):
        result = engine.classify_extended(FileInfo.from_filename("sample.modbam2bed.cpg.bed"))
        assert result.data_modality == "epigenomic.methylation"

    def test_bed_assembly_qc(self):
        result = engine.classify_extended(FileInfo.from_filename("HG01928.paternal.f1_assembly.hap1.bed"))
        assert result.data_modality == "genomic"

    def test_fastq_rna_filename(self):
        result = engine.classify_extended(FileInfo.from_filename("sample_RNA_001.fastq.gz"))
        assert result.data_modality == "transcriptomic.bulk"
        assert result.status_of("reference_assembly") == NOT_APPLICABLE

    def test_checksum_not_applicable(self):
        result = engine.classify_extended(FileInfo.from_filename("sample.md5"))
        assert result.status_of("data_modality") == NOT_APPLICABLE

    def test_chunked_upload_not_applicable(self):
        result = engine.classify_extended(FileInfo.from_filename("c5ff4e67-1db9-4fd1.gs-chunked-io-part.000013"))
        assert result.status_of("data_modality") == NOT_APPLICABLE

    def test_timestamp_filename_not_applicable(self):
        result = engine.classify_extended(FileInfo.from_filename("2020-11-20T212208.245537Z"))
        assert result.status_of("data_modality") == NOT_APPLICABLE

    def test_png_derived(self):
        result = engine.classify_extended(FileInfo.from_filename("assembly_plot.png"))
        assert result.status_of("data_modality") == NOT_APPLICABLE
        assert result.status_of("platform") == NOT_APPLICABLE
        assert result.status_of("reference_assembly") == NOT_APPLICABLE

    def test_all_index_types_not_applicable(self):
        for ext in [".bai", ".crai", ".tbi", ".csi", ".pbi"]:
            result = engine.classify_extended(FileInfo.from_filename(f"sample{ext}"))
            assert result.status_of("data_modality") == NOT_APPLICABLE, f"{ext} should be not_applicable"

    def test_narrowpeak_is_chromatin(self):
        result = engine.classify_extended(FileInfo.from_filename("sample.narrowPeak"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"

    def test_bigwig_with_chip_keyword(self):
        result = engine.classify_extended(FileInfo.from_filename("H3K27ac_ChIP.bw"))
        assert result.data_modality == "epigenomic.histone_modification"

    def test_bed_reference_from_filename(self):
        """BED file with hg38 in filename should detect GRCh38."""
        result = engine.classify_extended(FileInfo.from_filename("sample.hg38.regions.bed"))
        assert result.reference_assembly == "GRCh38"

    def test_idat_methylation(self):
        """IDAT file should be epigenomic methylation."""
        result = engine.classify_extended(FileInfo.from_filename("200123456789_R01C01.idat"))
        assert result.data_modality == "epigenomic.methylation"

    def test_no_crash_on_unknown(self):
        for name in ["readme.xyz", "data.parquet", "model.h5", ""]:
            result = engine.classify_extended(FileInfo.from_filename(name))
            # Unknown files don't crash and resolve to a not_classified status
            # (the value stays None — the sentinel lives in status now).
            assert result.status_of("data_modality") == NOT_CLASSIFIED

    def test_fasta_base_rule(self):
        """FASTA files should get base rule classification."""
        for ext in [".fa", ".fasta", ".fa.gz", ".fasta.gz"]:
            result = engine.classify_extended(FileInfo.from_filename(f"sample{ext}"))
            assert result.data_type == "sequence", f"{ext} should be sequence"
            assert result.status_of("platform") == NOT_APPLICABLE
            assert result.status_of("assay_type") == NOT_APPLICABLE

    def test_fasta_assembly_filename(self):
        """FASTA with assembly keyword in filename."""
        result = engine.classify_extended(FileInfo.from_filename("HG00673.paternal.f1_assembly_v1.fa.gz"))
        assert result.data_modality == "genomic"
        assert result.data_type == "assembly"
        assert result.status_of("reference_assembly") == NOT_APPLICABLE

    def test_fasta_haplotype_filename(self):
        """FASTA with haplotype keyword in filename."""
        result = engine.classify_extended(FileInfo.from_filename("hapdup_contigs_2.fasta"))
        assert result.data_modality == "genomic"
        assert result.data_type == "assembly"
        assert result.status_of("reference_assembly") == NOT_APPLICABLE

    def test_fasta_verkko_filename(self):
        """FASTA with verkko assembler keyword."""
        result = engine.classify_extended(FileInfo.from_filename("HG02300_verkko_gfase_diploid.fasta.gz"))
        assert result.data_modality == "genomic"
        assert result.data_type == "assembly"
        assert result.status_of("reference_assembly") == NOT_APPLICABLE


# =============================================================================
# Pangenome / sequence graphs (issue #144) — rule engine from filename only
# =============================================================================


class TestPangenomeGraphs:
    """Sequence-graph formats classify as data_type `pangenome`; HPRC
    minigraph-cactus reference graphs refine to `pangenome.reference`."""

    def test_gfa_assembly_graph_is_pangenome(self):
        """A single-sample assembly graph (.gfa) is still a sequence graph."""
        result = engine.classify_extended(FileInfo.from_filename("HG002-full-0.14.1.hap1.p_ctg.gfa"))
        assert result.data_modality == "genomic"
        assert result.data_type == "pangenome"
        assert result.status_of("platform") == NOT_APPLICABLE
        assert result.status_of("assay_type") == NOT_APPLICABLE

    def test_pggb_gfa_gz_is_pangenome(self):
        """PGGB pangenome graph (.gfa.gz compound extension) — not an mc reference."""
        result = engine.classify_extended(FileInfo.from_filename("chr1.hprc-v1.0-pggb.gfa.gz"))
        assert result.data_modality == "genomic"
        assert result.data_type == "pangenome"

    def test_vg_and_xg_are_pangenome(self):
        for name in ("sample.vg", "graph.xg"):
            result = engine.classify_extended(FileInfo.from_filename(name))
            assert result.data_type == "pangenome", name
            assert result.data_modality == "genomic", name

    def test_mc_gbz_is_pangenome_reference(self):
        """HPRC minigraph-cactus GBZ — the published alignment reference graph."""
        result = engine.classify_extended(FileInfo.from_filename("hprc-v1.0-mc-grch38.gbz"))
        assert result.data_modality == "genomic"
        assert result.data_type == "pangenome.reference"
        # reference_assembly comes from the shared filename_ref_* rules
        assert result.reference_assembly == "GRCh38"

    def test_mc_gbwt_chm13_is_pangenome_reference(self):
        result = engine.classify_extended(FileInfo.from_filename("hprc-v1.0-mc-chm13.gbwt"))
        assert result.data_type == "pangenome.reference"
        assert result.reference_assembly == "CHM13"


# =============================================================================
# rGFA content check — pangenome.reference from stable-rank tags (#148)
# =============================================================================


class TestRgfaContentClassification:
    """rGFA segments carrying stable rank 0 (`SR:i:0`) define a reference
    coordinate system, so the graph refines to `pangenome.reference` from file
    content rather than from a filename token."""

    def test_rank0_segments_are_pangenome_reference(self):
        """The real signal: minigraph rGFA, all leading segments SR:i:0 on chr1."""
        tags = [SegmentTag(sn="chr1", sr="0") for _ in range(5)]
        record = classify_from_gfa_segment_tags(tags, name=FileName.parse("hprc-v1.0-minigraph-grch38.gfa.gz"))
        assert get_val(record, "data_type") == "pangenome.reference"
        # reference_assembly still comes from the filename rules, not content
        assert get_val(record, "reference_assembly") == "GRCh38"
        evidence = record["data_type"]["evidence"]
        assert any(e["rule_id"] == "rgfa_stable_rank_reference" for e in evidence)

    def test_content_claim_is_appended_not_clobbered(self):
        """The tier-1 `pangenome_graph` claim must survive the content refinement,
        so the evidence chain matches the engine-resolved `-mc-` case.

        Asserts the tier-1 claim is present and precedes the content claim, rather
        than pinning the exact list: #147 will add graph `data_type` rules, and an
        exact-match assertion would fail for a change unrelated to this behavior.
        """
        record = classify_from_gfa_segment_tags(
            [SegmentTag(sn="chr1", sr="0")], name=FileName.parse("hprc-v1.0-minigraph-grch38.gfa.gz")
        )
        rules = [e["rule_id"] for e in record["data_type"]["evidence"]]
        assert "pangenome_graph" in rules, "the tier-1 claim was clobbered"
        assert "rgfa_stable_rank_reference" in rules
        assert rules.index("pangenome_graph") < rules.index("rgfa_stable_rank_reference"), (
            "the content claim must be appended after the base claim, not prepended"
        )

    def test_content_claim_carries_content_tier(self):
        """The rGFA claim reads segment bytes, so it sits at CONTENT_TIER (#226) —
        above the tier-1 `pangenome` claim it refines. Pin the tier so resolving
        from claims agrees with the value set here."""
        record = classify_from_gfa_segment_tags(
            [SegmentTag(sn="chr1", sr="0")], name=FileName.parse("hprc-v1.0-minigraph-grch38.gfa.gz")
        )
        claims = record["data_type"]["evidence"]
        content = next(c for c in claims if c["rule_id"] == "rgfa_stable_rank_reference")
        assert content["tier"] == CONTENT_TIER
        # Resolving the claim list independently must reach the same value.
        assert evaluate_claims(claims).value == "pangenome.reference"

    def test_nonzero_rank_only_stays_pangenome(self):
        """Non-reference haplotype segments (rank >= 1) do not make a reference graph."""
        tags = [SegmentTag(sn="HG002#1#chr1", sr="1")]
        record = classify_from_gfa_segment_tags(tags, name=FileName.parse("some-graph.gfa.gz"))
        assert get_val(record, "data_type") == "pangenome"

    def test_untagged_gfa_stays_pangenome(self):
        """A plain GFA (pggb) carries no rGFA tags, so parsing yields no segments."""
        record = classify_from_gfa_segment_tags([], name=FileName.parse("chr1.hprc-v1.0-pggb.gfa.gz"))
        assert get_val(record, "data_type") == "pangenome"

    def test_no_segments_falls_back_to_filename_rules(self):
        """No content claim must not downgrade the tier-1/2 result.

        Minigraph-cactus GFA segments are untagged, so the `-mc-` filename rule
        is what keeps this a reference graph.
        """
        record = classify_from_gfa_segment_tags([], name=FileName.parse("hprc-v1.0-mc-grch38.gfa.gz"))
        assert get_val(record, "data_type") == "pangenome.reference"
        assert get_val(record, "reference_assembly") == "GRCh38"

    def test_rank0_without_stable_name_is_not_a_reference_claim(self):
        """SR without SN is malformed rGFA — no contig to anchor the claim."""
        record = classify_from_gfa_segment_tags([SegmentTag(sr="0")], name=FileName.parse("some-graph.gfa"))
        assert get_val(record, "data_type") == "pangenome"

    def test_empty_file_name_falls_back_to_file_format(self):
        """The pipeline selects records on file_format OR file_name, so file_name
        can be empty on a record with a real extension (pipeline._filter_records)."""
        record = classify_from_gfa_segment_tags([], name=FileName.parse(""), file_format=".rgfa.gz")
        assert get_val(record, "data_type") == "pangenome"
        rules = [e["rule_id"] for e in record["data_type"]["evidence"]]
        assert "pangenome_graph" in rules

    def test_file_name_wins_over_file_format(self):
        """A real filename carries the tokens the tier-2 rules need."""
        record = classify_from_gfa_segment_tags(
            [], name=FileName.parse("hprc-v1.0-mc-grch38.gfa.gz"), file_format=".gfa"
        )
        assert get_val(record, "data_type") == "pangenome.reference"
        assert get_val(record, "reference_assembly") == "GRCh38"

    def test_extensionless_file_name_keeps_its_tokens_and_gains_the_extension(self):
        """A selected record's file_name may carry no extension. The name's raw
        tokens (`-mc-`/`grch38`) still reach the tier-2 filename rules, while the
        engine falls back to the declared `file_format` (.gfa.gz) for the extension —
        so the graph is classified and the reference is read from the name."""
        record = classify_from_gfa_segment_tags([], name=FileName.parse("hprc-v1.0-mc-grch38"), file_format=".gfa.gz")
        assert get_val(record, "data_type") == "pangenome.reference"
        assert get_val(record, "reference_assembly") == "GRCh38"

    def test_extensionless_file_name_still_classifies_as_a_graph(self):
        record = classify_from_gfa_segment_tags([], name=FileName.parse("graph"), file_format=".gfa")
        assert get_val(record, "data_type") == "pangenome"
        assert get_val(record, "data_modality") == "genomic"


class TestGfaContentClaimCoherence:
    def test_tar_named_graph_record_is_coherent(self):
        """A ``.tar.gz``-named graph must still classify as a graph, not as an archive.

        Since #245 ``graph.tar.gz`` parses to ``extension=None`` (``.tar``/``.gz`` are
        containers), so the engine falls back to the declared ``.gfa.gz`` file_format
        — ``pangenome_graph`` fires and the rGFA rank-0 claim coherently refines it to
        ``pangenome.reference`` on a ``genomic`` record. (Previously ``.tar`` was a
        core extension a bespoke filename override had to reject.)"""
        record = classify_from_gfa_segment_tags(
            [SegmentTag(sn="chr1", sr="0")],
            name=FileName.parse("hprc-graph.tar.gz"),
            file_format=".gfa.gz",
        )
        assert get_val(record, "data_type") == "pangenome.reference"
        assert get_val(record, "data_modality") == "genomic"
        assert field_status(record, "platform") == NOT_APPLICABLE

    def test_no_file_name_or_format_still_classifies_as_graph(self):
        record = classify_from_gfa_segment_tags([])
        assert get_val(record, "data_type") == "pangenome"

    def test_evidence_reason_is_singular_for_one_segment(self):
        record = classify_from_gfa_segment_tags([SegmentTag(sn="chr1", sr="0")], name=FileName.parse("some-graph.gfa"))
        content = next(e for e in record["data_type"]["evidence"] if e["rule_id"] == "rgfa_stable_rank_reference")
        assert "1 rGFA segment carries" in content["reason"]


class TestGfaSegmentTagParsing:
    """parse_gfa_segment_tags reads S-line rGFA tags from a truncated file head."""

    def test_parses_stable_tags_and_ignores_sequence(self):
        text = (
            "H\tVN:Z:1.0\n"
            "S\ts1\tACGTACGT\tLN:i:8\tSN:Z:chr1\tSO:i:0\tSR:i:0\n"
            "S\ts2\tGGGG\tLN:i:4\tSN:Z:chr1\tSO:i:8\tSR:i:0\n"
            "L\ts1\t+\ts2\t+\t0M\n"
        )
        assert parse_gfa_segment_tags(text) == [
            SegmentTag(sn="chr1", sr="0"),
            SegmentTag(sn="chr1", sr="0"),
        ]

    def test_sequence_column_is_never_read_as_a_tag(self):
        """Tags start at column 4; a tag-shaped sequence must not be picked up.

        A parser that scanned every field would report SN=decoy here.
        """
        text = "S\ts1\tSN:Z:decoy\tSR:i:0\n"
        assert parse_gfa_segment_tags(text) == [SegmentTag(sr="0")]

    def test_drops_truncated_trailing_line(self):
        """A byte-range cut leaves a partial final record — it must not be parsed.

        Without the newline the trailing `SR:i:0` is unreachable, so a naive
        parser would emit a segment whose tags are silently incomplete.
        """
        text = "S\ts1\tACGT\tSN:Z:chr1\tSR:i:0\nS\ts2\tACG\tSN:Z:chr1\tSR"
        assert parse_gfa_segment_tags(text) == [SegmentTag(sn="chr1", sr="0")]

    def test_keeps_unterminated_final_line_when_text_is_not_truncated(self):
        """A small complete rGFA with no trailing newline must keep its last segment.

        The caller has to tell us: a byte-range cut can land exactly on a tag
        boundary, so a truncated line may be syntactically complete and no
        inspection of the text alone can tell the two apart.
        """
        text = "H\tVN:Z:1.0\nS\ts1\tACGT\tSN:Z:chr1\tSR:i:0"
        assert parse_gfa_segment_tags(text, truncated=True) == []
        assert parse_gfa_segment_tags(text, truncated=False) == [SegmentTag(sn="chr1", sr="0")]

    def test_a_truncated_line_can_look_complete(self):
        """Why `truncated` cannot be inferred: this cut lands on a tag boundary."""
        full = "S\ts1\tACGT\tSN:Z:chr1\tSR:i:0\tSO:i:5"
        cut = full[: full.index("\tSO:i:5")]  # a clean, syntactically valid line
        assert cut == "S\ts1\tACGT\tSN:Z:chr1\tSR:i:0"
        # Indistinguishable from the complete line in the test above.
        assert parse_gfa_segment_tags(cut, truncated=False) == [SegmentTag(sn="chr1", sr="0")]

    def test_keeps_complete_trailing_line_when_newline_terminated(self):
        text = "S\ts1\tACGT\tSN:Z:chr1\tSR:i:0\n"
        assert parse_gfa_segment_tags(text) == [SegmentTag(sn="chr1", sr="0")]

    def test_untagged_segments_are_omitted(self):
        """Plain GFA 1.0 (minigraph-cactus): segments with no optional tags."""
        text = "H\tVN:Z:1.0\nS\t1\tAC\nS\t2\tGTGT\n"
        assert parse_gfa_segment_tags(text) == []

    def test_segment_without_tag_columns_is_omitted(self):
        """A 3-column S line has no tag columns at all — no trailing tab to find."""
        assert parse_gfa_segment_tags("S\ts1\tACGT\n") == []

    def test_ignores_non_segment_lines(self):
        text = "H\tVN:Z:1.0\nP\tHG002#1#chr1\ts1+,s2+\t*\nW\tHG002\t1\tchr1\t0\t100\t>s1>s2\n"
        assert parse_gfa_segment_tags(text) == []


# =============================================================================
# FASTA — end-to-end through classify_fasta_files.classify_single_fasta
# =============================================================================


@pytest.mark.e2e
class TestFastaE2E:
    """End-to-end FASTA classification from cached contig names.

    Only the contig shapes the current corpus can still supply are exercised here. The
    reference-genome, mitochondrial and empty-gzip fixtures this class used to hold have
    no counterpart the fetch path can reproduce: every FASTA in the anvil15 catalog is a
    whole-genome file of 773 MB or more, whose 256 KiB head yields a single contig. The
    catalog does still hold reference genomes — it is the *contig list* those fixtures
    needed that is unreachable, not the files. Those cases moved to
    ``test_header_classifier.TestFastaContigClassification``, which drives
    ``classify_from_fasta_header`` with the contig lists directly (#381).
    """

    def test_hprc_paternal_assembly(self):
        """HG00673.paternal.f1_assembly_v1.fa.gz — 851 MB HPRC de novo assembly."""
        result = classify_fasta(
            "7ace6a53c63fdc2b99fba3f5f6be383d", "HG00673.paternal.f1_assembly_v1.fa.gz", file_size=851264823
        )
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "assembly"
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE
        assert field_status(result, "assay_type") == NOT_APPLICABLE

    def test_hapdup_contigs(self):
        """hapdup_contigs_2.fasta — 2.9 GB hapdup output, contig name is just "0".

        Real evidence: a single contig "0" from an S3 range request, which matches no
        assembler pattern, so the classification rests on the filename "hapdup" keyword
        (tier 2 rule) rather than on content.
        """
        result = classify_fasta("2503de005f3cc18709847c27ebb92b52", "hapdup_contigs_2.fasta", file_size=2920261541)
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"
        assert get_val(result, "data_type") == "assembly"
        assert field_status(result, "reference_assembly") == NOT_APPLICABLE

    def test_genbank_assembly(self):
        """HG00621.paternal.f1_assembly_v2_genbank.fa.gz — 835.8 MB GenBank-accessioned assembly."""
        result = classify_fasta(
            "ab44168d3352e2f99b9afa163f2d3124",
            "HG00621.paternal.f1_assembly_v2_genbank.fa.gz",
            file_size=835826203,
        )
        assert result is not None
        assert_output_format(result)
        assert get_val(result, "data_modality") == "genomic"


# =============================================================================
# DERIVED / NOT-APPLICABLE FILES — tier precedence tests
# =============================================================================


class TestDerivedFileTierPrecedence:
    """Verify that not_applicable rules at tier 2 win over filename_ref_* at tier 2,
    and that index files allow reference_assembly from filename patterns."""

    # --- Index files: reference_assembly IS applicable (#106/#107) ---

    def test_index_with_reference_in_filename(self):
        """Index file with GRCh38 in filename should get reference_assembly=GRCh38."""
        result = engine.classify_extended(FileInfo.from_filename("sample.GRCh38.bam.bai"))
        assert result.status_of("data_modality") == NOT_APPLICABLE
        assert result.reference_assembly == "GRCh38"
        assert result.status_of("platform") == NOT_APPLICABLE

    def test_index_with_chm13_in_filename(self):
        """Index file with CHM13 in filename should get reference_assembly=CHM13."""
        result = engine.classify_extended(FileInfo.from_filename("HG01879.CHM13v2.cram.crai"))
        assert result.reference_assembly == "CHM13"
        assert result.status_of("data_modality") == NOT_APPLICABLE

    def test_index_without_reference_in_filename(self):
        """Index file without reference hint should get reference_assembly=not_classified."""
        result = engine.classify_extended(FileInfo.from_filename("sample.bam.bai"))
        assert result.status_of("reference_assembly") == NOT_CLASSIFIED
        assert result.status_of("data_modality") == NOT_APPLICABLE

    # --- Checksum files: all fields not_applicable, even with reference in filename ---

    def test_checksum_ignores_filename_reference(self):
        """Checksum file should stay not_applicable even with GRCh38 in filename."""
        result = engine.classify_extended(FileInfo.from_filename("sample.GRCh38.bam.md5"))
        assert result.status_of("reference_assembly") == NOT_APPLICABLE
        assert result.status_of("data_modality") == NOT_APPLICABLE

    # --- Log files: all fields not_applicable ---

    def test_log_ignores_filename_reference(self):
        """Log file should stay not_applicable even with hg38 in filename."""
        result = engine.classify_extended(FileInfo.from_filename("alignment.hg38.log"))
        assert result.status_of("reference_assembly") == NOT_APPLICABLE
        assert result.status_of("data_modality") == NOT_APPLICABLE

    # --- Image files: reference_assembly not_applicable at tier 2 ---

    def test_svs_ignores_filename_reference(self):
        """SVS histology image should stay not_applicable for reference_assembly."""
        result = engine.classify_extended(FileInfo.from_filename("hg38.sample.svs"))
        assert result.status_of("reference_assembly") == NOT_APPLICABLE
        assert result.data_modality == "imaging.histology"

    def test_png_ignores_filename_reference(self):
        """PNG plot with reference in filename should stay not_applicable."""
        result = engine.classify_extended(FileInfo.from_filename("GRCh38_coverage_plot.png"))
        assert result.status_of("reference_assembly") == NOT_APPLICABLE
        assert result.status_of("data_modality") == NOT_APPLICABLE

    # --- Nanopore raw signal: reference_assembly not_applicable ---

    def test_fast5_ignores_filename_reference(self):
        """FAST5 raw signal with reference in filename should stay not_applicable."""
        result = engine.classify_extended(FileInfo.from_filename("GRCh38_run.fast5"))
        assert result.status_of("reference_assembly") == NOT_APPLICABLE
        assert result.platform == "ONT"

    # --- Stats files: reference_assembly applicable, other fields not_applicable (#106) ---

    def test_stats_with_reference_in_filename(self):
        """Stats file with CHM13 in filename should get reference_assembly=CHM13."""
        result = engine.classify_extended(FileInfo.from_filename("HG01879.CHM13v2.chrX.samtools.stats.txt"))
        assert result.reference_assembly == "CHM13"
        assert result.status_of("data_modality") == NOT_APPLICABLE
        assert result.status_of("platform") == NOT_APPLICABLE

    def test_stats_without_reference_in_filename(self):
        """Stats file without reference hint should get not_classified, not not_applicable."""
        result = engine.classify_extended(FileInfo.from_filename("HG00345.mosdepth.region.dist.txt"))
        assert result.status_of("reference_assembly") == NOT_CLASSIFIED
        assert result.status_of("data_modality") == NOT_APPLICABLE

    # --- BED tier precedence: specific rules beat fallbacks ---

    def test_assembly_qc_beats_intervals_targets(self):
        """Assembly QC BED (tier 2) should override intervals_targets (tier 1)."""
        result = engine.classify_extended(
            FileInfo.from_filename("HG01928.maternal.f1_assembly_v2_genbank.HSat2and3_Regions.bed")
        )
        assert result.data_modality == "genomic"  # not not_applicable

    def test_chip_peaks_beat_generic_peaks(self):
        """ChIP-seq peaks (tier 2) should override generic peaks (tier 1)."""
        result = engine.classify_extended(FileInfo.from_filename("H3K27ac_chip_peaks.bed"))
        assert result.data_modality == "epigenomic.histone_modification"

    def test_capture_targets_not_applicable(self):
        """Capture target BED without competing rules should get not_applicable."""
        result = engine.classify_extended(FileInfo.from_filename("exome_capture_targets.bed"))
        assert result.status_of("data_modality") == NOT_APPLICABLE
