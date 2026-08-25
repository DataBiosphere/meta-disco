"""Reference build identity resolution (issue #340).

Every signature in these fixtures is real — measured from the cached evidence
headers by ``scripts/generate_reference_builds.py`` — so a test failing here means
either the resolver or the build table drifted from what the corpus actually
contains, not that a made-up example stopped matching.

The defect this guards against: ``ANVIL_T2T`` and ``ANVIL_T2T_CHRY`` are sibling
workspaces whose files both classify as ``CHM13`` while being aligned to builds
whose chr1 differs by 169 bases. ``test_the_two_chm13_builds_separate`` is the
one that fails if that regresses.
"""

from meta_disco.header_classifier import classify_from_header, classify_from_vcf_header
from meta_disco.validators.reference_builds import ReferenceIdentity, resolve_identity

# --- Real signatures, as measured from the corpus ---------------------------

CHM13_V1_GRCH38Y = (
    "@HD\tVN:1.6\tSO:coordinate\n"
    "@SQ\tSN:chr1\tLN:248387497\tM5:8646cb1d7b7085a82d50bf991c0962c4"
    "\tUR:file:///ref/t2t-chm13.20200921.withGRCh38chrY.chrEBV.chrYKI270740v1r.fasta\n"
    "@SQ\tSN:chrY\tLN:57227415\tM5:ce3e31103314a704255f3cd90369ecce\n"
)

CHM13_V2 = (
    "@HD\tVN:1.6\tSO:coordinate\n"
    "@SQ\tSN:chr1\tLN:248387328\tM5:e469247288ceb332aee524caec92bb22\tUR:file:///ref/chm13v2.0.fasta\n"
    "@SQ\tSN:chrY\tLN:62460029\tM5:dd7264df17e7e4a4dac5b0f1f19dcfe0\n"
)

GRCH38_ANALYSIS_SET = (
    "@HD\tVN:1.6\tSO:coordinate\n"
    "@SQ\tSN:chr1\tLN:248956422\tM5:6aef897c3d6ff0c78aff06ac189178dd"
    "\tUR:file:///ref/GRCh38_full_analysis_set_plus_decoy_hla.fa\n"
    "@SQ\tSN:chrY\tLN:57227415\tM5:ce3e31103314a704255f3cd90369ecce\n"
)


class TestBuildSeparation:
    """The defect itself."""

    def test_the_two_chm13_builds_separate(self):
        """Files both classified CHM13 must not report the same build.

        This is the whole point of the issue: sibling T2T workspaces aligned to
        CHM13 v1.0-with-grafted-chrY and to v2.0, indistinguishable in output
        before this change.
        """
        v1 = resolve_identity(CHM13_V1_GRCH38Y, is_bam=True)
        v2 = resolve_identity(CHM13_V2, is_bam=True)

        assert v1.base == v2.base == "CHM13"
        assert v1.version != v2.version
        assert v1.version == "v1.0+GRCh38chrY"
        assert v2.version == "v2.0"

    def test_grch38_resolves_to_its_family(self):
        identity = resolve_identity(GRCH38_ANALYSIS_SET, is_bam=True)
        assert identity.base == "GRCh38"
        assert identity.chr1_m5 == "6aef897c3d6ff0c78aff06ac189178dd"

    def test_chry_source_is_part_of_the_build(self):
        """CHM13 has no chrY of its own, so where one came from is a real
        difference between builds — not a footnote on a shared build."""
        identity = resolve_identity(CHM13_V1_GRCH38Y, is_bam=True)
        assert identity.version is not None
        assert "chrY" in identity.version


class TestRefusesToGuess:
    """Accuracy over coverage: no answer beats a wrong one."""

    def test_ambiguous_evidence_withholds_the_version(self):
        """chr1 alone cannot separate CHM13 v1.1 from v2.0 — they share it.

        A VCF carrying only that length is consistent with both builds, so no
        version is reported. The family still is: both candidates are CHM13, so
        saying so cannot be wrong.
        """
        header = "##fileformat=VCFv4.2\n##contig=<ID=chr1,length=248387328>\n"
        identity = resolve_identity(header, is_bam=False)
        assert identity.version is None
        assert identity.base == "CHM13"

    def test_family_is_withheld_when_candidates_disagree_on_it(self):
        """A signature matching no build at all fixes nothing."""
        identity = resolve_identity("@SQ\tSN:chr1\tLN:12345\n", is_bam=True)
        assert identity.base is None
        assert identity.version is None

    def test_unknown_reference_keeps_its_observations(self):
        """An unrecognised reference must not be assigned a nearest match — and
        must keep what was seen, so a later table row can resolve it from stored
        output without re-fetching the header."""
        header = "@SQ\tSN:chr1\tLN:999999999\tM5:deadbeefdeadbeefdeadbeefdeadbeef\tUR:file:///ref/mystery.fa\n"
        identity = resolve_identity(header, is_bam=True)
        assert identity.base is None
        assert identity.version is None
        assert identity.chr1_m5 == "deadbeefdeadbeefdeadbeefdeadbeef"
        assert identity.name == "mystery.fa"

    def test_header_without_contigs_yields_an_empty_identity(self):
        identity = resolve_identity("@HD\tVN:1.6\n", is_bam=True)
        assert identity.is_empty()

    def test_empty_header(self):
        assert resolve_identity("", is_bam=True).is_empty()


class TestNameAsTiebreak:
    """The declared name narrows candidates; it never introduces one."""

    def test_name_breaks_a_tie_the_checksums_left_open(self):
        header = "##fileformat=VCFv4.2\n##reference=file:///ref/chm13v2.0.fasta\n##contig=<ID=chr1,length=248387328>\n"
        identity = resolve_identity(header, is_bam=False)
        assert identity.version == "v2.0"
        assert identity.name == "chm13v2.0.fasta"

    def test_a_name_cannot_override_a_contradicting_signature(self):
        """Signatures rule out builds; a name only chooses among survivors. A
        header naming one reference while carrying another's chr1 must resolve to
        the checksum's build, not the name's."""
        header = (
            "@SQ\tSN:chr1\tLN:248387328\tM5:e469247288ceb332aee524caec92bb22"
            "\tUR:file:///ref/t2t-chm13.20200921.withGRCh38chrY.chrEBV.chrYKI270740v1r.fasta\n"
        )
        identity = resolve_identity(header, is_bam=True)
        assert identity.version != "v1.0+GRCh38chrY"

    def test_uri_and_bare_path_reduce_to_the_same_name(self):
        bare = CHM13_V2.replace("file:///ref/", "/some/other/dir/")
        assert resolve_identity(bare, is_bam=True).name == "chm13v2.0.fasta"


class TestAdditive:
    """The coarse value is untouched — this change only ever adds detail."""

    def test_coarse_value_is_unchanged_when_the_build_resolves(self):
        entry = classify_from_header(CHM13_V2)["reference_assembly"]
        assert entry["value"] == "CHM13"
        assert entry["status"] == "classified"
        assert entry["build"]["version"] == "v2.0"

    def test_coarse_value_survives_an_unresolvable_build(self):
        """A reference we cannot pin down must not cost the file its family.

        The lengths here still match CHM13 within the coarse detector's
        tolerance, so the dimension stays classified while the build does not
        resolve — the two paths are independent.
        """
        header = "@SQ\tSN:chr1\tLN:248387328\n@SQ\tSN:chr2\tLN:242696747\n@SQ\tSN:chr3\tLN:201106605\n"
        entry = classify_from_header(header)["reference_assembly"]
        assert entry["value"] == "CHM13"
        assert entry.get("build", {}).get("version") is None

    def test_only_reference_assembly_carries_a_build(self):
        classifications = classify_from_header(CHM13_V2)
        for field, entry in classifications.items():
            if isinstance(entry, dict) and field != "reference_assembly":
                assert "build" not in entry, field

    def test_build_is_omitted_when_nothing_was_observed(self):
        """Absent, not a dict of nulls: an empty answer should not look like an
        answer."""
        entry = classify_from_header("@HD\tVN:1.6\n")["reference_assembly"]
        assert "build" not in entry


class TestVcfPath:
    """VCF gives the resolver less than BAM does, and says so."""

    def test_vcf_has_no_checksums(self):
        """``##contig``'s md5 attribute is optional in the spec and unpopulated
        across all 203,719 cached headers, so a VCF build rests on length alone."""
        header = "##fileformat=VCFv4.2\n##reference=file:///ref/chm13v2.0.fasta\n##contig=<ID=chr1,length=248387328>\n"
        identity = resolve_identity(header, is_bam=False)
        assert identity.chr1_m5 is None
        assert identity.chry_m5 is None
        assert identity.name == "chm13v2.0.fasta"

    def test_vcf_classifier_emits_the_build(self):
        header = "##fileformat=VCFv4.2\n##reference=file:///ref/chm13v2.0.fasta\n##contig=<ID=chr1,length=248387328>\n"
        entry = classify_from_vcf_header(header)["reference_assembly"]
        assert entry["build"]["base"] == "CHM13"
        assert entry["build"]["version"] == "v2.0"

    def test_contig_field_order_does_not_matter(self):
        """``##contig`` attributes may appear in any order — an ``assembly=``
        field between ``ID`` and ``length`` must not defeat the parse."""
        header = "##fileformat=VCFv4.2\n##contig=<ID=chr1,assembly=CHM13,length=248387497>\n"
        identity = resolve_identity(header, is_bam=False)
        # 248,387,497 is shared by all three CHM13 v1.0 variants, so the family
        # resolves and the version does not.
        assert identity.base == "CHM13"
        assert identity.version is None


class TestSerialization:
    def test_to_dict_always_carries_every_key(self):
        """So a consumer can tell "looked, found nothing" from "no such field"."""
        assert set(ReferenceIdentity().to_dict()) == {"base", "version", "chr1_m5", "chry_m5", "name"}

    def test_is_empty_is_false_when_only_an_observation_survives(self):
        assert not ReferenceIdentity(name="mystery.fa").is_empty()
        assert ReferenceIdentity().is_empty()
