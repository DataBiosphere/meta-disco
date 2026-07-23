"""Tests for the rule engine."""

import pytest

from meta_disco.file_name import Format
from meta_disco.models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    FileInfo,
)
from meta_disco.rule_engine import (
    CONTENT_TIER,
    ExtendedClassificationResult,
    ExtendedFileInfo,
    ResolutionReason,
    RuleEngine,
    _make_claim,
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
        assert "alignment_rnaseq_filename" in result.rules_matched

    def test_alignment_wgs_filename(self, engine):
        """WGS indicators should set genomic modality with WGS assay_type."""
        result = engine.classify(FileInfo(filename="sample_WGS_aligned.bam"))
        assert result.data_modality == "genomic"

    def test_alignment_ref_grch38(self, engine):
        """hg38/GRCh38 in filename should set reference assembly."""
        result = engine.classify(FileInfo(filename="sample.hg38.cram"))
        assert result.reference_assembly == "GRCh38"

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
        result = engine.classify(FileInfo(filename="sample_RNA_aligned.bam", file_size=60_000_000_000))
        assert result.data_modality == "transcriptomic.bulk"

    def test_star_aligner_indicates_rnaseq(self, engine):
        """STAR aligner output pattern should indicate RNA-seq."""
        result = engine.classify(FileInfo(filename="sample.Aligned.sortedByCoord.out.bam"))
        assert result.data_modality == "transcriptomic.bulk"


class TestVariantFiles:
    """Test variant file classification."""

    def test_vcf_default_genomic(self, engine):
        """VCF files should default to genomic."""
        result = engine.classify(FileInfo(filename="sample.vcf"))
        assert result.data_modality == "genomic"

    def test_vcf_gz_default_genomic(self, engine):
        """Compressed VCF files should default to genomic."""
        result = engine.classify(FileInfo(filename="sample.vcf.gz"))
        assert result.data_modality == "genomic"

    def test_vcf_with_ref_grch38(self, engine):
        """VCF with reference in filename."""
        result = engine.classify(FileInfo(filename="NA19189.chr2.hg38.vcf.gz"))
        assert result.data_modality == "genomic"
        assert result.reference_assembly == "GRCh38"

    def test_vcf_contig_assembly_subfield_sets_reference(self, engine):
        """A ##contig assembly= subfield sets reference_assembly end-to-end (#221).

        Filename carries no reference token, so GRCh38 can only come from the
        tier-3 ``vcf_contig_grch38`` rule reading the parsed assembly subfield.
        """
        ext_info = ExtendedFileInfo(
            filename="sample.vcf.gz",
            vcf_header="##contig=<ID=chr1,length=248956422,assembly=GRCh38>",
        )
        result = engine.classify_extended(ext_info, include_tier3=True)
        assert result.reference_assembly == "GRCh38"
        rule_ids = [e["rule_id"] for e in result.field_evidence["reference_assembly"] if "rule_id" in e]
        assert "vcf_contig_grch38" in rule_ids, f"Expected vcf_contig_grch38, got {rule_ids}"

    @pytest.mark.parametrize(
        ("assembly", "expected"),
        [
            ("GRCh38", "GRCh38"),
            ("hg38", "GRCh38"),
            ("hs38", "GRCh38"),  # alias aligned with ##reference (#221 follow-up)
            ("GRCh37", "GRCh37"),
            ("hs37", "GRCh37"),  # alias aligned with ##reference (#221 follow-up)
            ("hg19", "GRCh37"),
            ("CHM13", "CHM13"),
            ("T2T-CHM13v2.0", "CHM13"),
        ],
    )
    def test_vcf_contig_assembly_aliases_classify(self, engine, assembly, expected):
        """##contig assembly aliases classify to the same set as ##reference (#221)."""
        ext_info = ExtendedFileInfo(
            filename="sample.vcf.gz",
            vcf_header=f"##contig=<ID=chr1,length=248956422,assembly={assembly}>",
        )
        result = engine.classify_extended(ext_info, include_tier3=True)
        assert result.reference_assembly == expected

    @pytest.mark.parametrize(
        ("header_line", "expected"),
        [
            # GCA_000001405 encodes the assembly in its version: .1-.14 are GRCh37
            # (frozen at .14), .15+ are GRCh38 (.15 base, .16+ patches). The rules
            # must split at that boundary, in both the ##contig and ##reference
            # families (#221 review). In particular .16+ are real GRCh38 patch
            # accessions and must NOT fall through to GRCh37.
            ("##contig=<ID=chr1,length=248956422,assembly=GCA_000001405.14>", "GRCh37"),
            ("##contig=<ID=chr1,length=248956422,assembly=GCA_000001405.15>", "GRCh38"),
            ("##contig=<ID=chr1,length=248956422,assembly=GCA_000001405.16>", "GRCh38"),
            ("##contig=<ID=chr1,length=248956422,assembly=GCA_000001405.26>", "GRCh38"),
            ("##reference=file:///ref/GCA_000001405.14.fa", "GRCh37"),
            ("##reference=file:///ref/GCA_000001405.15.fa", "GRCh38"),
            ("##reference=file:///ref/GCA_000001405.16.fa", "GRCh38"),
            ("##reference=file:///ref/GCA_000001405.26.fa", "GRCh38"),
        ],
    )
    def test_vcf_gca_accession_version_maps_to_correct_assembly(self, engine, header_line, expected):
        ext_info = ExtendedFileInfo(filename="sample.vcf.gz", vcf_header=header_line)
        result = engine.classify_extended(ext_info, include_tier3=True)
        assert result.reference_assembly == expected


class TestFormatMatching:
    """Rules keyed on `format` instead of `extensions` (#243). The FASTA rules
    were migrated to `format: FASTA`, so these both prove the new keying works
    and pin the migration as behavior-preserving."""

    @pytest.mark.parametrize("name", ["genome.fa", "genome.fasta", "genome.fa.gz", "genome.fasta.gz"])
    def test_format_keyed_rule_matches_every_spelling(self, engine, name):
        """One `format: FASTA` rule fires for every FASTA spelling/compression
        variant — the collapse the extension list used to enumerate by hand."""
        result = engine.classify_extended(FileInfo(filename=name))
        assert result.data_type == "sequence"

    def test_format_keyed_filename_rule_still_fires(self, engine):
        """A tier-2 rule that pairs `format: FASTA` with a filename_pattern still
        matches on both conditions (fasta_assembly_filename)."""
        result = engine.classify_extended(FileInfo(filename="HG002.hifiasm.bp.p_ctg.fa"))
        assert result.data_modality == "genomic"
        assert result.data_type == "assembly"

    def test_format_keyed_rule_skipped_for_other_formats(self, engine):
        """A format-only rule is considered for every file but must not fire when
        the format differs — a BAM is not classified as FASTA sequence."""
        result = engine.classify_extended(FileInfo(filename="sample.bam"))
        assert result.data_type != "sequence"

    def test_engine_derives_format_from_settled_extension(self, engine):
        """classify_extended sets file_info.format from the extension it settles
        on, agreeing with file_format even on a header-only (name-less) call."""
        ext_info = ExtendedFileInfo(filename="", file_format=".cram")
        engine.classify_extended(ext_info)
        assert ext_info.format is Format.CRAM

    def test_present_but_falsy_format_fails_match(self, engine):
        """A present-but-falsy `when.format` (e.g. an authoring slip `format: ""`
        the loader does not value-check) fails the match rather than being
        silently skipped — the guard keys on presence, not truthiness (#243)."""
        from meta_disco.rule_loader import UnifiedRule

        fasta = ExtendedFileInfo(filename="genome.fa", format=Format.FASTA)
        result = ExtendedClassificationResult()
        empty_fmt = UnifiedRule(id="x", tier=1, scope="extension", when={"format": ""}, then={}, rationale="")
        assert engine._rule_matches(empty_fmt, fasta, result) is False
        # Control: the same rule keyed on the real format still matches.
        real_fmt = UnifiedRule(id="y", tier=1, scope="extension", when={"format": "FASTA"}, then={}, rationale="")
        assert engine._rule_matches(real_fmt, fasta, result) is True

    def test_classify_extended_normalizes_file_format_case(self, engine):
        """A mixed-case header-only file_format is lower-cased once at the source,
        so the extensions / when.file_format / assay conditions all match case-
        insensitively — a `.CRAM` classifies identically to a `.cram` (#243)."""
        upper = ExtendedFileInfo(filename="", file_format=".CRAM")
        lower = ExtendedFileInfo(filename="", file_format=".cram")
        r_upper = engine.classify_extended(upper)
        r_lower = engine.classify_extended(lower)
        assert upper.file_format == ".cram"  # normalized in place
        assert upper.format is Format.CRAM
        assert r_upper.data_type == r_lower.data_type  # downstream matching is case-insensitive
        # A None file_format is left as-is (no crash) and derives no format.
        none_info = ExtendedFileInfo(filename="", file_format=None)
        engine.classify_extended(none_info)
        assert none_info.file_format is None
        assert none_info.format is None


class TestWrapperSplitMatching:
    """#244: rule `extensions:` are the clean core suffix; compression/archive is
    split into wrappers at parse time. A core matches the uncompressed spelling
    and every compressed spelling the parser recognizes (those in
    COMPOUND_EXTENSIONS), so classification is unchanged by whether such a file is
    gzipped — an unlisted spelling like ".bam.gz" is not recognized and matches
    nothing."""

    @pytest.mark.parametrize("name", ["cohort.vcf.gz", "reads.fastq.gz", "reads.fq.gz"])
    def test_core_keyed_rule_matches_compressed_and_uncompressed(self, engine, name):
        """The extension rules list only the core (".vcf"), yet both sample.vcf and
        sample.vcf.gz route through it — the compression no longer needs listing."""
        compressed = engine.classify_extended(FileInfo(filename=name))
        bare = engine.classify_extended(FileInfo(filename=name.replace(".gz", "")))
        assert compressed.data_type == bare.data_type
        assert compressed.data_type is not None

    def test_gvcf_core_keeps_its_distinct_signal(self, engine):
        """`.g.vcf.gz` splits to the `.g.vcf` core, which derives Format.GVCF and
        still matches the VCF rules that list `.g.vcf` (behavior-preserved)."""
        ext_info = ExtendedFileInfo(filename="HG002.deepvariant.g.vcf.gz")
        result = engine.classify_extended(ext_info)
        assert ext_info.format is Format.GVCF
        assert result.data_type == "variants"

    def test_compound_file_format_fallback_normalized_to_core(self, engine):
        """A header-only call passing a compound file_format (".fastq.gz") with no
        filename settles to the core (".fastq") so the core-keyed rules still fire
        — the regression the #244 core-keying would otherwise introduce."""
        ext_info = ExtendedFileInfo(filename="", file_format=".fastq.gz")
        result = engine.classify_extended(ext_info)
        assert ext_info.file_format == ".fastq"
        assert ext_info.format is Format.FASTQ
        assert result.data_type == "reads"

    def test_known_core_file_format_fallback_not_collapsed(self, engine):
        """A header-only fallback that is already a known core (".g.vcf") is kept,
        not re-parsed — re-parsing would collapse it to ".vcf" via the simple-suffix
        gate and derive Format.VCF, contradicting EXTENSION_TO_FORMAT[".g.vcf"]=GVCF
        (Copilot review, #244)."""
        ext_info = ExtendedFileInfo(filename="", file_format=".g.vcf")
        engine.classify_extended(ext_info)
        assert ext_info.file_format == ".g.vcf"
        assert ext_info.format is Format.GVCF


class TestThenStatus:
    """A rule authoring a non-classified status via `then.status` (#133)."""

    def _engine_with_rule(self, tmp_path, then):
        import yaml

        path = tmp_path / "rules.yaml"
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump_all(
                [
                    {"extension_map": {".foo": "foo"}},
                    {
                        "rules": [
                            {
                                "id": "foo_rule",
                                "tier": 1,
                                "scope": "extension",
                                "when": {"extensions": [".foo"]},
                                "then": then,
                            }
                        ]
                    },
                ],
                f,
            )
        return RuleEngine(path)

    def test_status_only_field_is_not_applicable(self, tmp_path):
        engine = self._engine_with_rule(tmp_path, {"status": {"reference_assembly": "not_applicable"}})
        out = engine.classify_extended(FileInfo(filename="x.foo")).to_output_dict()
        assert out["reference_assembly"]["status"] == NOT_APPLICABLE
        assert out["reference_assembly"]["value"] is None

    def test_real_value_and_status_coexist_in_one_rule(self, tmp_path):
        # The mixed case (e.g. nanopore_fast5): a real value and a status in the
        # same then-clause resolve independently and correctly.
        engine = self._engine_with_rule(
            tmp_path,
            {
                "data_type": "raw_signal",
                "status": {"reference_assembly": "not_applicable"},
            },
        )
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

    @pytest.mark.parametrize("accessor", ["status_of", "is_declared", "label"])
    def test_read_accessors_reject_unknown_field(self, accessor):
        # Read helpers raise a consistent ValueError (not a bare KeyError) on a typo.
        result = ExtendedClassificationResult()
        with pytest.raises(ValueError, match="unknown classification field"):
            getattr(result, accessor)("platfrom")


class TestMakeClaim:
    """_make_claim enforces value-xor-status and a required tier."""

    def test_value_claim_shape(self):
        claim = _make_claim(rule_id="r", reason="because", tier=2, value="genomic")
        assert claim == {"rule_id": "r", "reason": "because", "tier": 2, "value": "genomic"}
        assert "status" not in claim

    def test_status_claim_shape(self):
        claim = _make_claim(rule_id="r", reason="n/a", tier=1, status=NOT_APPLICABLE)
        assert claim == {"rule_id": "r", "reason": "n/a", "tier": 1, "status": NOT_APPLICABLE}
        assert "value" not in claim

    def test_rejects_both_value_and_status(self):
        with pytest.raises(ValueError, match="exactly one of value/status"):
            _make_claim(rule_id="r", reason="x", tier=1, value="genomic", status=NOT_APPLICABLE)

    def test_rejects_neither_value_nor_status(self):
        with pytest.raises(ValueError, match="exactly one of value/status"):
            _make_claim(rule_id="r", reason="x", tier=1)

    def test_tier_is_required(self):
        with pytest.raises(TypeError):
            _make_claim(rule_id="r", reason="x", value="genomic")  # type: ignore[call-arg]

    def test_rejects_unknown_status(self):
        # A status claim declares a non-classified sentinel only; a typo would
        # otherwise be read as a real value and resolve the field CLASSIFIED to it.
        with pytest.raises(ValueError, match="unknown status"):
            _make_claim(rule_id="r", reason="x", tier=1, status="not_classifed")  # typo

    def test_rejects_classified_as_status(self):
        with pytest.raises(ValueError, match="unknown status"):
            _make_claim(rule_id="r", reason="x", tier=1, status=CLASSIFIED)


class TestAddClaim:
    """add_claim's own wiring: append accumulates, then the field re-derives from
    the full list. The tier/unanimity/conflict resolution itself is owned by
    TestEvaluateClaims — add_claim forwards the whole list to it unchanged, so
    these test the wrapper, not the resolution rules."""

    def test_single_claim_appends_and_sets_value(self):
        result = ExtendedClassificationResult()
        result.add_claim("data_type", rule_id="r1", reason="x", tier=1, value="reads")
        assert result.data_type == "reads"
        assert result.status_of("data_type") == CLASSIFIED
        assert result.field_evidence["data_type"] == [{"rule_id": "r1", "reason": "x", "tier": 1, "value": "reads"}]

    def test_second_claim_accumulates_and_re_resolves(self):
        # Two calls accumulate (append, not replace) and the field re-derives from
        # the full list — here a same-tier disagreement resolves to not_classified,
        # and _sync_markers records a conflict marker explaining why, so add_claim
        # stays consistent with _finalize_result. The resolution rule itself is
        # TestEvaluateClaims' job.
        result = ExtendedClassificationResult()
        result.add_claim("reference_assembly", rule_id="a", reason="x", tier=2, value="GRCh38")
        result.add_claim("reference_assembly", rule_id="b", reason="y", tier=2, value="GRCh37")
        assert result.reference_assembly is None
        assert result.status_of("reference_assembly") == NOT_CLASSIFIED
        evidence = result.field_evidence["reference_assembly"]
        assert [e.get("rule_id") for e in evidence[:2]] == ["a", "b"]
        assert evidence[-1]["marker"] == "conflict"
        assert "rule_id" not in evidence[-1]
        assert set(evidence[-1]["competing_values"]) == {"GRCh38", "GRCh37"}

    def test_drops_synthetic_not_classified_placeholder_on_assertive_resolution(self):
        # _finalize_result appends a synthetic {marker: "not_classified"} entry for a
        # field no rule matched. A later content claim that resolves the field
        # assertively makes that "no rule determined a value" marker false, so
        # add_claim drops it (#227) — the evidence reads as the derivation, not a
        # value beside a contradiction.
        result = ExtendedClassificationResult()
        result.field_evidence["reference_assembly"].append(
            {"marker": "not_classified", "reason": "No rule determined a value", "status": NOT_CLASSIFIED}
        )
        result.add_claim("reference_assembly", rule_id="vcf_contig_length", reason="contigs", tier=4, value="GRCh38")
        assert result.reference_assembly == "GRCh38"
        rule_ids = [e["rule_id"] for e in result.field_evidence["reference_assembly"]]
        assert rule_ids == ["vcf_contig_length"], f"stale placeholder not dropped: {rule_ids}"

    def test_keeps_rule_authored_not_classified_when_dropping_placeholder(self):
        # Only the *synthetic* placeholder (a marker entry) is dropped; a rule that
        # intentionally declares not_classified carries a real rule_id and no marker,
        # so it stays in the evidence chain even when a higher-tier claim wins.
        result = ExtendedClassificationResult()
        result.field_evidence["data_modality"].append(
            {"rule_id": "fastq_modality_unknown", "reason": "unknown", "status": NOT_CLASSIFIED, "tier": 3}
        )
        result.field_evidence["data_modality"].append(
            {"marker": "not_classified", "reason": "No rule determined a value", "status": NOT_CLASSIFIED}
        )
        result.add_claim("data_modality", rule_id="aligned_to_reference", reason="aligned", tier=4, value="genomic")
        assert result.data_modality == "genomic"
        rule_ids = [e["rule_id"] for e in result.field_evidence["data_modality"]]
        assert rule_ids == ["fastq_modality_unknown", "aligned_to_reference"], rule_ids

    def test_drops_synthetic_placeholder_even_on_non_assertive_add(self):
        # Adding any claim makes the synthetic "no rule determined a value"
        # placeholder false, so it is dropped even when the field stays
        # not_classified — the field still carries the newly added claim, which
        # explains the status better than the generic placeholder.
        result = ExtendedClassificationResult()
        result.field_evidence["reference_assembly"].append(
            {"marker": "not_classified", "reason": "No rule determined a value", "status": NOT_CLASSIFIED}
        )
        result.add_claim("reference_assembly", rule_id="looked_but_unsure", reason="?", tier=4, status=NOT_CLASSIFIED)
        assert result.status_of("reference_assembly") == NOT_CLASSIFIED
        rule_ids = [e["rule_id"] for e in result.field_evidence["reference_assembly"]]
        assert rule_ids == ["looked_but_unsure"], f"synthetic placeholder not dropped: {rule_ids}"

    def test_drops_stale_conflict_marker_on_assertive_resolution(self):
        # A field left in conflict by _finalize_result carries a conflict marker; a
        # later higher-tier claim that resolves it must drop the now-stale marker so
        # the evidence stops asserting ambiguity.
        result = ExtendedClassificationResult()
        result.field_evidence["reference_assembly"].extend(
            [
                {"rule_id": "r1", "value": "GRCh38", "tier": 3},
                {"rule_id": "r2", "value": "GRCh37", "tier": 3},
                {
                    "marker": "conflict",
                    "reason": "Conflicting reference_assembly: ['GRCh37', 'GRCh38'] — ambiguous",
                    "status": NOT_CLASSIFIED,
                    "competing_values": ["GRCh37", "GRCh38"],
                },
            ]
        )
        result.add_claim(
            "reference_assembly", rule_id="contig_length_detection", reason="contigs", tier=4, value="CHM13"
        )
        assert result.reference_assembly == "CHM13"
        rule_ids = [e["rule_id"] for e in result.field_evidence["reference_assembly"]]
        assert rule_ids == ["r1", "r2", "contig_length_detection"], f"stale conflict marker not dropped: {rule_ids}"

    def test_rejects_unknown_field_before_appending(self):
        # add_claim delegates field validation to _require_field and raises rather
        # than appending a claim under a typo'd field.
        result = ExtendedClassificationResult()
        with pytest.raises(ValueError, match="unknown classification field"):
            result.add_claim("data_typo", rule_id="a", reason="x", tier=1, value="reads")


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

    def test_single_cell_matrix(self, engine):
        """Single-cell matrix files should be transcriptomic.single_cell."""
        result = engine.classify(FileInfo(filename="sample.h5ad"))
        assert result.data_modality == "transcriptomic.single_cell"

    def test_single_cell_atac(self, engine):
        """Single-cell ATAC matrix should be epigenomic."""
        result = engine.classify(FileInfo(filename="sample_atac_peaks.h5ad"))
        assert result.data_modality == "epigenomic.chromatin_accessibility"

    def test_methylation_idat(self, engine):
        """IDAT files should be epigenomic.methylation."""
        result = engine.classify(FileInfo(filename="sample.idat"))
        assert result.data_modality == "epigenomic.methylation"

    def test_histology_svs(self, engine):
        """SVS files should be imaging.histology."""
        result = engine.classify(FileInfo(filename="GTEX-18A6Q-1126.svs"))
        assert result.data_modality == "imaging.histology"


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
        result = engine.classify(FileInfo(filename="m64043_210211_005516.hifi_reads.bam"))
        assert result.data_modality == "genomic"

    def test_vcf_with_chr(self, engine):
        """VCF with chromosome in filename."""
        result = engine.classify(FileInfo(filename="NA19189.chr2.hc.vcf.gz"))
        assert result.data_modality == "genomic"

    def test_gtex_histology(self, engine):
        """GTEx histology image."""
        result = engine.classify(FileInfo(filename="GTEX-18A6Q-1126.svs"))
        assert result.data_modality == "imaging.histology"

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
        """Conflict should produce a conflict marker in reference_assembly evidence."""
        result = engine.classify_extended(FileInfo(filename="CHM13.hg38.gff3.gz"))
        ref_evidence = result.field_evidence.get("reference_assembly", [])
        assert any(e.get("marker") == "conflict" for e in ref_evidence)
        # Prior evidence should also be preserved
        assert len(ref_evidence) >= 2


class TestConflictingClassificationFields:
    """Test that conflict detection works for all classification fields, not just reference_assembly."""

    def test_data_modality_conflict(self, engine):
        """Same-tier rules disagreeing on data_modality produce not_classified."""
        result = engine.classify_extended(FileInfo(filename="sample_rnaseq_wgs_aligned.bam"))
        assert result.status_of("data_modality") == NOT_CLASSIFIED
        evidence = result.field_evidence.get("data_modality", [])
        assert any(e.get("marker") == "conflict" for e in evidence)

    def test_conflict_preserves_prior_evidence(self, engine):
        """Conflict marker is appended to existing evidence, not replaced."""
        result = engine.classify_extended(FileInfo(filename="CHM13.hg38.gff3.gz"))
        evidence = result.field_evidence.get("reference_assembly", [])
        rule_ids = [e.get("rule_id") for e in evidence]
        # Both the original rule and the conflict marker should be present
        assert "filename_ref_grch38" in rule_ids or "filename_ref_chm13" in rule_ids
        assert any(e.get("marker") == "conflict" for e in evidence)

    def test_conflict_evidence_has_status_and_competing_values(self, engine):
        """Conflict evidence carries a not_classified status (in the status field,
        not the value slot) and the structured competing_values field."""
        result = engine.classify_extended(FileInfo(filename="CHM13.hg38.gff3.gz"))
        evidence = result.field_evidence.get("reference_assembly", [])
        conflict = next(e for e in evidence if e.get("marker") == "conflict")
        assert conflict["status"] == NOT_CLASSIFIED
        assert "value" not in conflict
        assert set(conflict["competing_values"]) == {"GRCh38", "CHM13"}

    def test_normal_evidence_has_value_field(self, engine):
        """Every evidence entry should include the value that was set."""
        result = engine.classify_extended(FileInfo(filename="sample.GRCh38.bed"))
        evidence = result.field_evidence.get("reference_assembly", [])
        ref_entry = next(e for e in evidence if e["rule_id"] == "filename_ref_grch38")
        assert ref_entry["value"] == "GRCh38"


class TestEvaluateClaims:
    """Test the standalone evaluate_claims() function."""

    def test_no_claims(self):
        """No claims → not_classified (status), no value."""
        result = evaluate_claims([])
        assert result.status == NOT_CLASSIFIED
        assert result.value is None
        assert result.is_conflict is False
        assert result.reason == ResolutionReason.NO_CLAIMS

    def test_single_claim(self):
        """Single claim → use it."""
        result = evaluate_claims(
            [
                {"rule_id": "r1", "value": "genomic", "tier": 2},
            ]
        )
        assert result.value == "genomic"
        assert result.reason == ResolutionReason.SINGLE_CLAIM
        assert result.is_conflict is False

    def test_two_claims_agree(self):
        """Two claims with same value → unanimous."""
        result = evaluate_claims(
            [
                {"rule_id": "r1", "value": "genomic", "tier": 2},
                {"rule_id": "r2", "value": "genomic", "tier": 3},
            ]
        )
        assert result.value == "genomic"
        assert result.reason == ResolutionReason.UNANIMOUS

    def test_disagree_different_tiers(self):
        """Higher tier wins when claims disagree."""
        result = evaluate_claims(
            [
                {"rule_id": "r1", "value": "sequence", "tier": 1},
                {"rule_id": "r2", "value": "assembly", "tier": 2},
            ]
        )
        assert result.value == "assembly"
        assert result.reason == ResolutionReason.HIGHER_SPECIFICITY_OVERRIDE
        assert result.is_conflict is False

    def test_disagree_same_tier(self):
        """Same tier, different values → conflict (not_classified status, no value)."""
        result = evaluate_claims(
            [
                {"rule_id": "r1", "value": "GRCh38", "tier": 2},
                {"rule_id": "r2", "value": "CHM13", "tier": 2},
            ]
        )
        assert result.status == NOT_CLASSIFIED
        assert result.value is None
        assert result.is_conflict is True
        assert result.reason == ResolutionReason.CONFLICT
        assert result.competing_values is not None
        assert set(result.competing_values) == {"GRCh38", "CHM13"}

    def test_three_claims_conflict_at_top_tier(self):
        """Lower tier agrees but top tier has conflict → conflict wins."""
        result = evaluate_claims(
            [
                {"rule_id": "r1", "value": "genomic", "tier": 1},
                {"rule_id": "r2", "value": "genomic", "tier": 3},
                {"rule_id": "r3", "value": "transcriptomic.bulk", "tier": 3},
            ]
        )
        assert result.status == NOT_CLASSIFIED
        assert result.value is None
        assert result.is_conflict is True

    def test_disagreeing_assertive_claim_without_tier_raises(self):
        """A tier is required to resolve disagreeing assertive claims; a missing one
        must raise loudly, not silently resolve at a phantom tier 0 (#228)."""
        with pytest.raises(KeyError):
            evaluate_claims(
                [
                    {"rule_id": "a", "value": "GRCh38"},  # no tier
                    {"rule_id": "b", "value": "CHM13", "tier": 2},
                ]
            )

    def test_not_classified_claims_ignored(self):
        """Claims declaring not_classified (status) don't assert a value."""
        result = evaluate_claims(
            [
                {"rule_id": "r1", "status": NOT_CLASSIFIED},
                {"rule_id": "r2", "value": "genomic", "tier": 2},
            ]
        )
        assert result.value == "genomic"
        assert result.reason == ResolutionReason.SINGLE_CLAIM

    def test_not_applicable_status_declaration(self):
        """A not_applicable status claim resolves to status not_applicable, value None."""
        result = evaluate_claims(
            [
                {"rule_id": "r1", "status": NOT_APPLICABLE, "tier": 1},
            ]
        )
        assert result.status == NOT_APPLICABLE
        assert result.value is None
        assert result.reason == ResolutionReason.SINGLE_CLAIM

    def test_not_applicable_wins_over_real_value_same_tier(self):
        """NOT_APPLICABLE is a terminal declaration — wins without conflict."""
        result = evaluate_claims(
            [
                {"rule_id": "r1", "status": NOT_APPLICABLE, "tier": 1},
                {"rule_id": "r2", "value": "genomic", "tier": 1},
            ]
        )
        assert result.status == NOT_APPLICABLE
        assert result.value is None
        assert result.is_conflict is False
        assert result.reason == ResolutionReason.NOT_APPLICABLE_TERMINAL

    def test_rule_authored_not_classified_is_not_no_claims(self):
        """A rule that intentionally declares not_classified is a real claim, not no_claims."""
        result = evaluate_claims(
            [
                {
                    "rule_id": "fastq_modality_unknown",
                    "status": NOT_CLASSIFIED,
                    "tier": 3,
                    "reason": "FASTQ modality cannot be determined from reads alone",
                },
            ]
        )
        assert result.status == NOT_CLASSIFIED
        assert result.value is None
        assert result.reason == ResolutionReason.SINGLE_CLAIM
        # The claim should NOT be treated as "no_claims"
        assert result.reason != ResolutionReason.NO_CLAIMS

    def test_rule_authored_not_classified_does_not_conflict_with_real(self):
        """A rule's not_classified declaration shouldn't conflict with a real value claim."""
        result = evaluate_claims(
            [
                {"rule_id": "fastq_modality_unknown", "status": NOT_CLASSIFIED, "tier": 3},
                {"rule_id": "some_rule", "value": "genomic", "tier": 3},
            ]
        )
        assert result.value == "genomic"
        assert result.is_conflict is False

    def test_reason_formats_as_wire_value(self):
        """str()/f-string render the underlying value, not the Enum repr."""
        assert str(ResolutionReason.NO_CLAIMS) == "no_claims"
        assert f"{ResolutionReason.CONFLICT}" == "conflict"

    def test_rule_authored_not_classified_in_evidence(self, engine):
        """fastq_modality_unknown rationale should appear in evidence, not generic placeholder."""
        result = engine.classify_extended(FileInfo(filename="sample_R1.fastq.gz"), include_tier3=True)
        dm_evidence = result.field_evidence.get("data_modality", [])
        rule_ids = [e["rule_id"] for e in dm_evidence]
        # Should have the rule's ID, not the generic "not_classified" placeholder
        assert "fastq_modality_unknown" in rule_ids
        assert "not_classified" not in rule_ids


class TestContentTier:
    """The definitive-content tier (issue #226).

    ``CONTENT_TIER`` is a unique tier above the rule tiers (1-3), so
    ``evaluate_claims`` resolves a byte-derived claim over any disagreeing rule
    without a special case. These pin the resolution semantics the migration
    (#227) relies on — that content wins its field, and content ``not_applicable``
    stays terminal — not the rule tiers themselves.
    """

    def test_content_tier_is_above_the_rule_tiers(self):
        """The reserved content tier sits strictly above the tier-3 rule ceiling."""
        assert CONTENT_TIER > 3

    def test_content_claim_overrides_disagreeing_tier3_rule(self):
        """A tier-4 content claim beats a disagreeing tier-3 rule (override, not conflict)."""
        result = evaluate_claims(
            [
                {"rule_id": "header_ref_grch38", "value": "GRCh38", "tier": 3},
                {"rule_id": "contig_length_detection", "value": "CHM13", "tier": CONTENT_TIER},
            ]
        )
        assert result.value == "CHM13"
        assert result.is_conflict is False
        assert result.reason == ResolutionReason.HIGHER_SPECIFICITY_OVERRIDE

    def test_content_not_applicable_beats_tier3_real_value(self):
        """A tier-4 content not_applicable wins terminally over a tier-3 real value."""
        result = evaluate_claims(
            [
                {"rule_id": "filename_ref_grch38", "value": "GRCh38", "tier": 3},
                {"rule_id": "fasta_assembly_no_reference", "status": NOT_APPLICABLE, "tier": CONTENT_TIER},
            ]
        )
        assert result.status == NOT_APPLICABLE
        assert result.value is None
        assert result.is_conflict is False
        assert result.reason == ResolutionReason.NOT_APPLICABLE_TERMINAL

    def test_content_claim_agreeing_with_rule_stays_unanimous(self):
        """When content agrees with the rule, the field is unanimous, not a conflict."""
        result = evaluate_claims(
            [
                {"rule_id": "header_ref_grch38", "value": "GRCh38", "tier": 3},
                {"rule_id": "contig_length_detection", "value": "GRCh38", "tier": CONTENT_TIER},
            ]
        )
        assert result.value == "GRCh38"
        assert result.is_conflict is False
        assert result.reason == ResolutionReason.UNANIMOUS


class TestAssayTypeInference:
    """Test that infer_assay_type records evidence correctly."""

    def test_inferred_assay_type_has_evidence(self, engine):
        """Inferred assay_type should have evidence from the infer_assay_type rule."""
        file_info = ExtendedFileInfo(
            filename="sample.bam",
            file_size=60_000_000_000,
            file_format=".bam",
        )
        result = engine.classify_extended(FileInfo(filename="sample.bam", file_size=60_000_000_000))
        # Set conditions that trigger WGS inference (via set_field to stay coherent)
        result.set_field("data_modality", "genomic")
        result.set_field("platform", "ILLUMINA")
        result.set_field("assay_type", status=NOT_CLASSIFIED)
        result.field_evidence["assay_type"] = []
        engine.infer_assay_type(result, file_info)
        assert result.assay_type == "WGS"
        evidence = result.field_evidence["assay_type"]
        assert len(evidence) == 1
        assert evidence[0]["rule_id"] == "infer_assay_type"

    def test_inferred_assay_type_removes_not_classified_placeholder(self, engine):
        """Inference should remove stale not_classified placeholder evidence."""
        file_info = ExtendedFileInfo(
            filename="sample.bam",
            file_size=60_000_000_000,
            file_format=".bam",
        )
        result = engine.classify_extended(FileInfo(filename="sample.bam", file_size=60_000_000_000))
        result.set_field("data_modality", "genomic")
        result.set_field("platform", "ILLUMINA")
        result.set_field("assay_type", status=NOT_CLASSIFIED)
        result.field_evidence["assay_type"] = [
            {
                "marker": "not_classified",
                "reason": "No rule determined a value for assay_type",
                "status": NOT_CLASSIFIED,
            }
        ]
        engine.infer_assay_type(result, file_info)
        assert result.assay_type == "WGS"
        markers = [e.get("marker") for e in result.field_evidence["assay_type"]]
        assert "not_classified" not in markers
        rule_ids = [e.get("rule_id") for e in result.field_evidence["assay_type"]]
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
            nc_evidence = [e for e in evidence if e.get("marker") == "not_classified"]
            assert nc_evidence, f"Expected not_classified marker for {fld}"
            assert fld in nc_evidence[0]["reason"], f"Expected '{fld}' in reason, got: {nc_evidence[0]['reason']}"
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
        result = engine.classify_extended(ExtendedFileInfo(filename="sample.bam", file_size=60_000_000_000))
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
                assert set(out[fld]) == {"value", "status", "evidence"}

    def test_status_pins_each_sentinel_state(self, engine):
        # Stage 3 shape: a real value classifies (value kept); each sentinel lives
        # in `status` with `value` nulled out — no sentinels in `value`.
        classified = engine.classify_extended(FileInfo(filename="sample_WGS_aligned.bam")).to_output_dict()[
            "data_modality"
        ]
        assert (classified["value"], classified["status"]) == ("genomic", CLASSIFIED)

        n_a = engine.classify_extended(FileInfo(filename="plot.png")).to_output_dict()["reference_assembly"]
        assert (n_a["value"], n_a["status"]) == (None, NOT_APPLICABLE)

        n_c = engine.classify_extended(
            ExtendedFileInfo(filename="sample.bam", file_size=60_000_000_000)
        ).to_output_dict()["data_modality"]
        assert (n_c["value"], n_c["status"]) == (None, NOT_CLASSIFIED)
