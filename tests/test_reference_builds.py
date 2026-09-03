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

import sys
from collections import Counter
from importlib.resources import files
from itertools import combinations
from pathlib import Path
from typing import ClassVar

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from generate_reference_builds import KNOWN_ABSENT, check_absences

from meta_disco import schema_vocab
from meta_disco.header_classifier import classify_from_header, classify_from_vcf_header
from meta_disco.models import field_status, field_value
from meta_disco.rule_loader import KEY_CONTIGS, SIGNATURE_FIELDS, RuleLoader, get_unified_rules
from meta_disco.validators.reference_builds import (
    IDENTITY_FIELDS,
    NAME_SOURCE_COMMAND_LINE,
    NAME_SOURCE_REFERENCE_FIELD,
    ContigSignature,
    DeclaredReference,
    ReferenceIdentity,
    _candidates,
    _consistent,
    _has_signatures,
    identity_from_sam,
    identity_from_vcf,
    observe_sam,
    observe_vcf,
    reference_from_command_line,
    resolve_identity,
)

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

# Per-chromosome VCFs from the two T2T workspaces. No ##reference line; the
# ##contig block lists every contig, so chr1 and chrY are both observed even
# for a chr22 VCF. These are the 159K headers issue #351 is about.
T2T_VCF = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=chr1,length=248387497>\n"
    "##contig=<ID=chr22,length=51324926>\n"
    "##contig=<ID=chrY,length=57227415>\n"
)
T2T_CHRY_VCF = (
    "##fileformat=VCFv4.2\n"
    "##contig=<ID=chr1,length=248387328>\n"
    "##contig=<ID=chr22,length=51324926>\n"
    "##contig=<ID=chrY,length=62460029>\n"
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
        v1 = identity_from_sam(CHM13_V1_GRCH38Y)
        v2 = identity_from_sam(CHM13_V2)

        assert v1.base == v2.base == "CHM13"
        assert v1.version != v2.version
        assert v1.version == "v1.0+GRCh38chrY"
        assert v2.version == "v2.0"

    def test_grch38_resolves_to_its_family(self):
        identity = identity_from_sam(GRCH38_ANALYSIS_SET)
        assert identity.base == "GRCh38"
        assert identity.chr1_m5 == "6aef897c3d6ff0c78aff06ac189178dd"

    def test_chry_source_is_part_of_the_build(self):
        """CHM13 has no chrY of its own, so where one came from is a real
        difference between builds — not a footnote on a shared build."""
        identity = identity_from_sam(CHM13_V1_GRCH38Y)
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
        identity = identity_from_vcf(header)
        assert identity.version is None
        assert identity.base == "CHM13"

    def test_nothing_is_fixed_when_no_build_matches(self):
        """A signature matching no build at all fixes neither family nor version."""
        identity = identity_from_sam("@SQ\tSN:chr1\tLN:12345\n")
        assert identity.base is None
        assert identity.version is None

    def test_family_is_withheld_when_candidates_disagree_on_it(self):
        """The `len(families) == 1` guard: candidates spanning two families fix
        neither. chrY 57,227,415 with no chr1 is consistent with GRCh38 and with
        CHM13 v1.0+GRCh38chrY, which borrowed that chrY from it."""
        identity = identity_from_sam("@SQ\tSN:chrY\tLN:57227415\n")
        assert identity.base is None
        assert identity.version is None

    def test_a_thin_table_row_does_not_lose_to_a_fuller_one(self):
        """The regression that shipped once: CHM13 v1.1's row records no chrY
        signature, and treating that *empty* set as a contradiction eliminated
        v1.1 on any chrY evidence — resolving a v1.1 file as v2.0, the exact
        collapse this module exists to prevent. (Since #351 a row that truly has
        no chrY says so with ``absent``; an empty set still means "unobserved".)"""
        header = "@SQ\tSN:chr1\tLN:248387328\tM5:e469247288ceb332aee524caec92bb22\tUR:file:///ref/chm13.v1.1.fasta\n"
        assert identity_from_sam(header).version == "v1.1"

    def test_a_name_alone_resolves_nothing(self):
        """A name is what a file claims. A chr20-only BAM naming chm13v2.0.fasta
        has offered no evidence that it is one, so the name is kept as an
        observation and nothing is derived from it."""
        identity = identity_from_sam("@SQ\tSN:chr20\tLN:66210255\tUR:file:///ref/chm13v2.0.fasta\n")
        assert identity.base is None
        assert identity.version is None
        assert identity.name == "chm13v2.0.fasta"

    def test_unknown_reference_keeps_its_observations(self):
        """An unrecognised reference must not be assigned a nearest match — and
        must keep what was seen, so a later table row can resolve it from stored
        output without re-fetching the header."""
        header = "@SQ\tSN:chr1\tLN:999999999\tM5:deadbeefdeadbeefdeadbeefdeadbeef\tUR:file:///ref/mystery.fa\n"
        identity = identity_from_sam(header)
        assert identity.base is None
        assert identity.version is None
        assert identity.chr1_m5 == "deadbeefdeadbeefdeadbeefdeadbeef"
        assert identity.name == "mystery.fa"

    def test_header_without_contigs_yields_an_empty_identity(self):
        identity = identity_from_sam("@HD\tVN:1.6\n")
        assert identity.is_empty()

    def test_empty_header(self):
        assert identity_from_sam("").is_empty()


class TestNameAsTiebreak:
    """The declared name narrows candidates; it never introduces one."""

    def test_name_breaks_a_tie_the_checksums_left_open(self):
        header = "##fileformat=VCFv4.2\n##reference=file:///ref/chm13v2.0.fasta\n##contig=<ID=chr1,length=248387328>\n"
        identity = identity_from_vcf(header)
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
        identity = identity_from_sam(header)
        assert identity.version != "v1.0+GRCh38chrY"

    def test_uri_and_bare_path_reduce_to_the_same_name(self):
        bare = CHM13_V2.replace("file:///ref/", "/some/other/dir/")
        assert identity_from_sam(bare).name == "chm13v2.0.fasta"


# The HPRC assembly-to-reference BAMs: no UR on any @SQ, the reference named
# only positionally on the minimap2 line (issue #354 scenario 3). Lengths are
# CHM13 v1.1's chr1 beside GRCh38's chrY, as measured on the 94 cached headers.
CHM13Y_EBV_BAM = (
    "@HD\tVN:1.6\tSO:coordinate\n"
    "@SQ\tSN:chr1\tLN:248387328\n"
    "@SQ\tSN:chrY\tLN:57227415\n"
    "@PG\tID:minimap2\tPN:minimap2\tVN:2.24-r1122"
    "\tCL:minimap2 -x asm5 -a --eqx --cs -t 36 /path/CHM13Y_EBV_v1.1.fasta /path/reads.fa\n"
)

GATK_LINE = (
    '##GATKCommandLine=<ID=HaplotypeCaller,CommandLine="HaplotypeCaller --sample-ploidy 2 '
    '--output HG.chr10.vcf --intervals chr10 --reference {ref} --input HG.cram",'
    'Version="4.2.0.0",Date="2021-06-01">\n'
)


class TestCommandLineName:
    """Issue #354: the declared name falls back to the program command line."""

    def test_a_vcf_without_reference_takes_the_gatk_line(self):
        """Scenario 1."""
        header = "##fileformat=VCFv4.2\n" + GATK_LINE.format(ref="/ref/chm13v2.0.XY.fasta")
        header += "##contig=<ID=chr1,length=248387328>\n"
        _, declared = observe_vcf(header)
        assert declared == DeclaredReference("chm13v2.0.XY.fasta", NAME_SOURCE_COMMAND_LINE)

    def test_the_dedicated_field_wins_over_the_command_line(self):
        """Scenario 2."""
        header = (
            "##fileformat=VCFv4.2\n##reference=file:///a/chm13v2.0.fasta\n"
            + GATK_LINE.format(ref="/b/other.fasta")
            + "##contig=<ID=chr1,length=248387328>\n"
        )
        _, declared = observe_vcf(header)
        assert declared == DeclaredReference("chm13v2.0.fasta", NAME_SOURCE_REFERENCE_FIELD)

    def test_a_minimap2_bam_takes_its_positional_reference(self):
        """Scenario 3: no UR anywhere, the reference is the first FASTA argument."""
        _, declared = observe_sam(CHM13Y_EBV_BAM)
        assert declared == DeclaredReference("CHM13Y_EBV_v1.1.fasta", NAME_SOURCE_COMMAND_LINE)

    def test_a_command_line_name_resolves_like_any_other(self):
        """Scenario 4: the HPRC CHM13Y_EBV files resolve to the row #352 asked for."""
        entry = classify_from_header(CHM13Y_EBV_BAM)["reference_assembly"]
        assert entry["build"]["base"] == "CHM13"
        assert entry["build"]["version"] == "v1.1+GRCh38chrY"
        assert entry["build"]["name_source"] == NAME_SOURCE_COMMAND_LINE

    def test_a_sex_specific_spelling_maps_to_the_parent_build(self):
        """Scenario 5: XY masking changes the sequence, not the coordinates."""
        header = (
            "##fileformat=VCFv4.2\n"
            + GATK_LINE.format(ref="/ref/chm13v2.0.XY.fasta")
            + "##contig=<ID=chr1,length=248387328>\n##contig=<ID=chrY,length=62460029>\n"
        )
        assert identity_from_vcf(header).version == "v2.0"
        plain = header.replace("chm13v2.0.XY.fasta", "chm13v2.0.fasta")
        assert identity_from_vcf(plain).version == "v2.0"

    def test_a_lifted_vcf_takes_no_name_from_the_caller_line(self):
        """Scenario 6: the caller line names the pre-liftover reference."""
        header = (
            "##fileformat=VCFv4.2\n"
            '##INFO=<ID=OriginalContig,Number=1,Type=String,Description="The name of the source contig">\n'
            + GATK_LINE.format(ref="/ref/chm13v2.0.fasta")
            + "##contig=<ID=chr1,length=248387328>\n"
        )
        _, declared = observe_vcf(header)
        assert declared is None
        with_field = header.replace("##fileformat=VCFv4.2\n", "##fileformat=VCFv4.2\n##reference=/ref/lifted.fa\n")
        _, declared = observe_vcf(with_field)
        assert declared == DeclaredReference("lifted.fa", NAME_SOURCE_REFERENCE_FIELD)

    def test_a_header_without_contigs_takes_no_command_line_name(self):
        """The guard that keeps an unaligned PacBio BAM from being named after
        its adapter file: a name describes a contig dictionary, and there is none."""
        header = "@HD\tVN:1.6\n@PG\tID:lima\tPN:lima\tCL:lima --hifi-preset movie.bam adapters.fasta out.bam\n"
        _, declared = observe_sam(header)
        assert declared is None

    def test_disagreeing_command_lines_yield_no_name(self):
        """Two lines, two references, and no way to say whose word counts."""
        header = (
            "@SQ\tSN:chr1\tLN:248387328\n"
            "@PG\tID:bwa\tCL:bwa mem -t 16 /ref/chm13v2.0.XY.fasta r1.fq r2.fq\n"
            "@PG\tID:samtools\tCL:samtools view -C -T /ref/chm13v2.0.fasta -o out.cram in.bam\n"
        )
        _, declared = observe_sam(header)
        assert declared is None

    def test_agreeing_command_lines_yield_the_shared_name(self):
        header = (
            "@SQ\tSN:chr1\tLN:248387328\n"
            "@PG\tID:bwa\tCL:bwa mem -t 16 /a/chm13v2.0.fasta r1.fq r2.fq\n"
            "@PG\tID:samtools\tCL:samtools view -C -T /b/chm13v2.0.fasta -o out.cram in.bam\n"
        )
        _, declared = observe_sam(header)
        assert declared == DeclaredReference("chm13v2.0.fasta", NAME_SOURCE_COMMAND_LINE)

    def test_a_gatk3_line_is_read(self):
        """GATK3 wrote a dotted key the VCF line parser rejects, and spelled the
        attribute ``CommandLineOptions`` with ``key=value`` content — the shape
        every one of the 3,252 dotted lines in the cache has."""
        header = (
            "##fileformat=VCFv4.2\n"
            '##GATKCommandLine.HaplotypeCaller=<ID=HaplotypeCaller,Version=3.5-0-g36282e4,Date="Tue Mar 01",'
            'Epoch=1456876433588,CommandLineOptions="analysis_type=HaplotypeCaller input_file=[in.bam] '
            'reference_sequence=/ref/Homo_sapiens_assembly38.fasta out=out.vcf">\n'
            "##contig=<ID=chr1,length=248956422>\n"
        )
        _, declared = observe_vcf(header)
        assert declared == DeclaredReference("Homo_sapiens_assembly38.fasta", NAME_SOURCE_COMMAND_LINE)

    def test_a_quoted_simple_command_line_is_unquoted(self):
        """freebayes writes ``##commandline="..."``; the quotes must not fuse the
        whole line into one argument."""
        header = (
            "##fileformat=VCFv4.2\n"
            '##commandline="freebayes -f /ref/GRCh38_no_alt.fa --min-alternate-count 2 in.bam"\n'
            "##contig=<ID=chr1,length=248956422>\n"
        )
        _, declared = observe_vcf(header)
        assert declared == DeclaredReference("GRCh38_no_alt.fa", NAME_SOURCE_COMMAND_LINE)

    def test_source_is_null_when_there_is_no_name(self):
        identity = identity_from_sam("@SQ\tSN:chr1\tLN:248387328\tM5:e469247288ceb332aee524caec92bb22\n")
        assert identity.name is None and identity.name_source is None

    def test_the_field_source_is_recorded_in_output(self):
        entry = classify_from_header(CHM13_V2)["reference_assembly"]
        assert entry["build"]["name_source"] == NAME_SOURCE_REFERENCE_FIELD


class TestReferenceFromCommandLine:
    """The parse itself, tool by tool. Corpus lines, trimmed, except the three
    marked synthetic."""

    @pytest.mark.parametrize(
        ("command_line", "expected"),
        [
            # bwa: -R is the read-group string, the reference is positional
            (
                "bwa mem -Y -K 100000000 -t 16 -R @RG\\tID:NA21127\\tPL:illumina /ref/chm13v2.0.XX.fasta r1.fq.gz r2.fq.gz",
                "chm13v2.0.XX.fasta",
            ),
            ("bwa mem -R '@RG\\tID:x\\tSM:y' /ref/GRCh38.fa r1.fq", "GRCh38.fa"),
            # GATK: --reference
            (
                "HaplotypeCaller --intervals chr10 --reference /ref/chm13v2.0.XY.fasta --input HG.cram",
                "chm13v2.0.XY.fasta",
            ),
            # synthetic: the --flag=value form, which nothing in the corpus writes
            ("HaplotypeCaller --reference=/ref/chm13v2.0.fasta --input HG.cram", "chm13v2.0.fasta"),
            # synthetic: a quoted value — what shlex is there for
            ('gatk HaplotypeCaller --reference="/ref/hg38.fa" -I in.bam', "hg38.fa"),
            # samtools CRAM conversion: -T is not a flag this knows; the path is still the first FASTA
            ("samtools view -@ 16 -C -T /cromwell_root/t2t.fasta -o HG00453.cram", "t2t.fasta"),
            # minimap2 / winnowmap: a no-argument flag right before the positional reference
            (
                "minimap2 -a -xasm5 --cs -t8 GCA_000001405.15_GRCh38_no_alt_analysis_set.fna HG03516.fa",
                "GCA_000001405.15_GRCh38_no_alt_analysis_set.fna",
            ),
            ("winnowmap -a -xasm5 --cs -t8 -r2k -W repetitive_k19.txt CHM13v2.fa HG01175_mat.fa.gz", "CHM13v2.fa"),
            # gzip-compressed reference
            ("minimap2 -a ref.fa.gz reads.fq", "ref.fa.gz"),
            # nothing FASTA-like
            ("samtools sort -@ 8 -o out.bam in.bam", None),
            ("STAR --genomeDir /idx --readFilesIn r1.fq", None),
            # synthetic: a reference flag whose value is not a FASTA path falls through to the positional rule
            ("dragen -r /ref/hash_table --output-dir out /ref/genome.fa", "genome.fa"),
            # synthetic: an unbalanced quote does not raise
            ("bwa mem -R '@RG\\tID:x /ref/GRCh38.fa r1.fq", "GRCh38.fa"),
        ],
    )
    def test_reference_from_command_line(self, command_line, expected):
        assert reference_from_command_line(command_line) == expected


class TestAdditive:
    """The coarse value is untouched — this change only ever adds detail."""

    def test_coarse_value_is_unchanged_when_the_build_resolves(self):
        entry = classify_from_header(CHM13_V2)["reference_assembly"]
        assert field_value({"reference_assembly": entry}, "reference_assembly") == "CHM13"
        assert field_status({"reference_assembly": entry}, "reference_assembly") == "classified"
        assert entry["build"]["version"] == "v2.0"

    def test_coarse_value_survives_an_unresolvable_build(self):
        """A reference we cannot pin down must not cost the file its family.

        The lengths here still match CHM13 within the coarse detector's
        tolerance, so the dimension stays classified while the build does not
        resolve — the two paths are independent.
        """
        header = "@SQ\tSN:chr1\tLN:248387328\n@SQ\tSN:chr2\tLN:242696747\n@SQ\tSN:chr3\tLN:201106605\n"
        entry = classify_from_header(header)["reference_assembly"]
        assert field_value({"reference_assembly": entry}, "reference_assembly") == "CHM13"
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
        identity = identity_from_vcf(header)
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
        identity = identity_from_vcf(header)
        # 248,387,497 is shared by all three CHM13 v1.0 variants, so the family
        # resolves and the version does not.
        assert identity.base == "CHM13"
        assert identity.version is None


class TestUntrustedHeaders:
    """Header text is fetched from public catalogs and is not trusted."""

    def test_a_malformed_checksum_is_not_recorded_as_one(self):
        """An ``M5`` tag is whatever sat between two tabs. Only a well-formed MD5
        is kept, so junk cannot be reported as a checksum or reach the build
        table the generator writes from these same observations."""
        header = '@SQ\tSN:chr1\tLN:248387328\tM5:not-a-checksum"; injected\n'
        assert identity_from_sam(header).chr1_m5 is None

    def test_a_non_ascii_digit_length_does_not_raise(self):
        """``"²".isdigit()`` is True but ``int("²")`` raises, so guarding with
        isdigit alone would fail mid-classification on a malformed header."""
        signatures, _ = observe_sam("@SQ\tSN:chr1\tLN:\u00b2\n")
        assert signatures[0].length is None

    def test_an_uppercase_checksum_is_normalised(self):
        """The SAM specification does not require a case for ``M5``; the table is
        lowercase, and matching is exact string membership."""
        header = (
            "@SQ\tSN:chr1\tLN:248387328\tM5:E469247288CEB332AEE524CAEC92BB22"
            "\tUR:file:///ref/chm13v2.0.fasta\n"
            "@SQ\tSN:chrY\tLN:62460029\tM5:DD7264DF17E7E4A4DAC5B0F1F19DCFE0\n"
        )
        identity = identity_from_sam(header)
        assert identity.chr1_m5 == "e469247288ceb332aee524caec92bb22"
        assert identity.version == "v2.0"

    def test_a_real_checksum_still_resolves(self):
        """The guard must not reject the values the corpus actually carries."""
        assert identity_from_sam(CHM13_V2).version == "v2.0"


class TestCoarseValueReconciliation:
    """One entry must not assert two families.

    The coarse value and the build are derived independently and can disagree.
    Where they do, the derivations are withheld and the observations kept — the
    same treatment any other ambiguity gets.
    """

    # chrY-only, from the CHM13 build that grafted GRCh38's chrY. The coarse
    # detector sees only that borrowed chrY and says GRCh38; the signature and
    # name identify the CHM13 build it actually belongs to.
    GRAFTED_CHRY_ONLY = (
        "@SQ\tSN:chrY\tLN:57227415\tM5:ce3e31103314a704255f3cd90369ecce"
        "\tUR:file:///r/t2t-chm13.20200921.withGRCh38chrY.chrEBV.chrYKI270740v1r.fasta\n"
    )

    def test_a_record_never_asserts_two_families(self):
        entry = classify_from_header(self.GRAFTED_CHRY_ONLY)["reference_assembly"]
        build = entry.get("build") or {}
        assert build.get("base") in (None, entry["value"])

    def test_the_observations_survive_the_disagreement(self):
        """Withholding the derivation must not discard the evidence — a later
        pass has to be able to resolve this from stored output."""
        entry = classify_from_header(self.GRAFTED_CHRY_ONLY)["reference_assembly"]
        build = entry["build"]
        assert build["base"] is None and build["version"] is None
        assert build["chry_m5"] == "ce3e31103314a704255f3cd90369ecce"
        assert build["name"].startswith("t2t-chm13")

    def test_an_agreeing_build_is_untouched(self):
        entry = classify_from_header(CHM13_V2)["reference_assembly"]
        assert entry["value"] == "CHM13"
        assert entry["build"]["base"] == "CHM13"
        assert entry["build"]["version"] == "v2.0"


class TestDeclaredAbsence:
    """Issue #351: a row can say "this reference has no chrY", and a header
    that lists one with a length or checksum then rules the build out. Scenario
    numbers are the issue's."""

    def test_t2t_vcf_resolves_to_the_grafted_grch38_chry_build(self):
        """Scenario 1. chr1 says a v1.0 variant; a chrY at GRCh38's length says
        which — it fits the GRCh38-grafted build and contradicts v1.0 and the
        HG002-grafted build, both declared to have no contig named chrY."""
        entry = classify_from_vcf_header(T2T_VCF)["reference_assembly"]
        assert entry["value"] == "CHM13"
        assert entry["build"]["base"] == "CHM13"
        assert entry["build"]["version"] == "v1.0+GRCh38chrY"

    def test_t2t_chry_vcf_resolves_to_v2(self):
        """Scenario 2. chr1 says v1.1 or v2.0; a chrY at HG002's length fits
        v2.0 and contradicts v1.1, which is declared to have no chrY."""
        entry = classify_from_vcf_header(T2T_CHRY_VCF)["reference_assembly"]
        assert entry["value"] == "CHM13"
        assert entry["build"]["base"] == "CHM13"
        assert entry["build"]["version"] == "v2.0"

    def test_a_chr1_only_header_still_withholds_the_version(self):
        """Scenario 3. Without a chrY observation nothing separates v1.1 from v2.0."""
        identity = identity_from_vcf("##fileformat=VCFv4.2\n##contig=<ID=chr1,length=248387328>\n")
        assert identity.base == "CHM13"
        assert identity.version is None

    def test_absence_is_not_a_contradiction_when_nothing_was_observed(self):
        """Scenario 4. A build declared absent for chrY stays a candidate for a
        header that lists no chrY."""
        v1_1 = next(b for b in get_unified_rules().reference_builds if (b.family, b.version) == ("CHM13", "v1.1"))
        assert _consistent(v1_1, "chry_length", None)

    def test_a_thin_row_is_still_not_a_contradiction(self):
        """Scenario 5. Empty signature sets without a declaration keep their
        #344 meaning: never observed, constrains nothing."""
        (thin,) = RuleLoader()._parse_reference_builds([{"family": "CHM13", "version": "thin", "chr1_length": [1]}])
        assert _consistent(thin, "chry_length", 62460029)

    def test_the_hg002_grafted_build_is_ruled_out_by_a_chry_line(self):
        """Scenario 6. Its Y contig is chrY_hg002, so a header listing chrY did
        not come from it."""
        candidates = {(b.family, b.version) for b in _candidates({"chr1_length": 248387497, "chry_length": 57227415})}
        assert candidates == {("CHM13", "v1.0+GRCh38chrY")}

    def test_generation_fails_when_the_corpus_contradicts_a_declaration(self):
        """Scenario 7, hermetically: one header naming a chrY-absent build that
        lists a chrY is enough to refuse the table."""
        observed = {"chm13.v1.1.fasta": Counter({(248387328, None, 62460029, None): 1})}
        (line,) = [p for p in check_absences(observed) if "list it" in p]
        assert "CHM13/v1.1" in line and "chm13.v1.1.fasta" in line and "chrY" in line

    def test_generation_fails_when_a_declaration_would_vanish(self):
        """A declared build with no cached header naming it gets no row at all,
        so its absence would silently disappear from the table. Refuse instead."""
        observed = {"chm13.v1.1.fasta": Counter({(248387328, None, None, None): 3})}
        problems = check_absences(observed)
        assert any("CHM13/v1.0 declares absence, but no cached header names it" in p for p in problems)
        assert not any("chm13.v1.1.fasta" in p for p in problems)

    def test_generation_passes_when_the_contig_is_simply_unobserved(self):
        observed = {
            "chm13.v1.1.fasta": Counter({(248387328, None, None, None): 3}),
            "chm13.draft_v1.0.fasta": Counter({(248387497, None, None, None): 1}),
            "t2t-chm13.20200921.HG002chrY.chrEBV.fasta": Counter({(248387497, "8646cb1d", None, None): 1}),
        }
        assert check_absences(observed) == []

    def test_exactly_the_declared_rows_carry_absent(self):
        """Scenario 8's table half: the YAML declares absence on the three
        builds KNOWN_ABSENT names and on no other."""
        in_table = {(b.family, b.version): set(b.absent) for b in get_unified_rules().reference_builds if b.absent}
        assert in_table == {key: set(contigs) for key, contigs in KNOWN_ABSENT.items()}

    def test_a_scalar_absent_fails_at_load(self):
        """Same contract as the signature fields: a list, or fail attributably."""
        row = {"family": "CHM13", "version": "x", "aliases": [], "absent": "Y"}
        with pytest.raises(ValueError, match="absent must be a list"):
            RuleLoader()._parse_reference_builds([row])

    def test_an_absent_name_that_is_not_a_key_contig_fails_at_load(self):
        """``"chrY"`` is how every comment spells it and ``"Y"`` is how the table
        does; the wrong one would load as an inert declaration."""
        row = {"family": "CHM13", "version": "x", "absent": ["chrY"]}
        with pytest.raises(ValueError, match=r"absent names \['chrY'\]; key contigs are \['1', 'Y'\]"):
            RuleLoader()._parse_reference_builds([row])
        assert "Y" in KEY_CONTIGS

    def test_absent_over_a_recorded_signature_fails_at_load(self):
        """A stale ``absent`` line surviving a re-pasted table would make the
        row's chrY signatures dead; refuse the contradiction instead."""
        row = {"family": "CHM13", "version": "x", "chry_length": [62460029], "absent": ["Y"]}
        with pytest.raises(ValueError, match="declares chrY absent but records a signature for it"):
            RuleLoader()._parse_reference_builds([row])


class TestKeyDiscrimination:
    """How much the (chr1, chrY) key actually discriminates — pinned, not assumed.

    The key is fitted to the references this corpus contains. The risk that
    creates is not that it is imperfect today, but that a build added to the
    table later silently stops being distinguishable from an existing one — the
    collapse this module exists to prevent, arriving by a different route.

    These pin the current state so that degradation fails loudly. If a new build
    widens the name-dependent set, the expected list below has to be edited
    deliberately, which is the point.
    """

    #: Pairs (by family/version) that no signature can separate, so resolution
    #: depends on the declared reference name. Every pair with GRCh38.p12 (no
    #: signature at all), plus the two CHM13 v1.0 builds that share chr1 and
    #: both lack a contig named chrY. (#351 removed three pairs from this set
    #: by letting a row declare chrY absent; #354 added one, the CHM13
    #: v1.1+GRCh38chrY row, against p12 like every other signatured row.)
    NAME_DEPENDENT_PAIRS: ClassVar[set[tuple[str, str]]] = {
        ("CHM13/v1.0", "CHM13/v1.0+HG002chrY"),
        ("CHM13/v1.0", "GRCh38/p12"),
        ("CHM13/v1.0+GRCh38chrY", "GRCh38/p12"),
        ("CHM13/v1.0+HG002chrY", "GRCh38/p12"),
        ("CHM13/v1.1", "GRCh38/p12"),
        ("CHM13/v1.1+GRCh38chrY", "GRCh38/p12"),
        ("CHM13/v2.0", "GRCh38/p12"),
        ("GRCh38/None", "GRCh38/p12"),
    }

    @staticmethod
    def _label(build):
        return f"{build.family}/{build.version}"

    @staticmethod
    def _signature_separable(a, b):
        """True when, for some field, every recorded value fits exactly one of the two builds.

        Asks the resolver's own predicate rather than re-deriving its rules, so
        this pin stays honest if ``_consistent`` learns a new case. Every value
        either row records for a field is tried against both; the field
        separates the pair only if no value fits both (or neither). One shared
        value is enough to make the pair name-dependent, because a file carrying
        that value cannot tell them apart. An empty set ("never observed") offers
        nothing to try, and a declared absence (#351) rejects what the other
        row records.
        """
        return any(
            (values := getattr(a, f) | getattr(b, f))
            and all(_consistent(a, f, value) != _consistent(b, f, value) for value in values)
            for f in SIGNATURE_FIELDS
        )

    def test_the_name_dependent_set_has_not_widened(self):
        observed = {
            tuple(sorted((self._label(a), self._label(b))))
            for a, b in combinations(get_unified_rules().reference_builds, 2)
            if not self._signature_separable(a, b)
        }
        assert observed == self.NAME_DEPENDENT_PAIRS, (
            "the set of build pairs that no signature separates has changed.\n"
            f"  newly name-dependent: {sorted(observed - self.NAME_DEPENDENT_PAIRS)}\n"
            f"  no longer:            {sorted(self.NAME_DEPENDENT_PAIRS - observed)}\n"
            "A pair that becomes name-dependent means a nameless file can no longer "
            "tell those builds apart. Widen the key, or accept it deliberately by "
            "editing NAME_DEPENDENT_PAIRS."
        )

    #: Rows the resolver cannot reach: no signature was ever observed for them,
    #: and a name alone resolves nothing (``_has_signatures``). Pinned so a row
    #: that silently becomes unreachable fails here instead of resolving nothing.
    UNREACHABLE_ROWS: ClassVar[set[str]] = {"GRCh38/p12"}

    @staticmethod
    def _one_observation_of(build) -> list[ContigSignature]:
        """A header's worth of evidence drawn from the row itself: one recorded
        value per signature field. Each field is matched by membership
        independently, so pairing a length with any recorded checksum is valid."""
        return [
            ContigSignature(name=name, length=min(lengths, default=None), md5=min(checksums, default=None))
            for name, lengths, checksums in (
                ("chr1", build.chr1_length, build.chr1_m5),
                ("chrY", build.chry_length, build.chry_m5),
            )
            if lengths or checksums
        ]

    def test_every_signatured_build_resolves_from_its_own_evidence(self):
        """Every row must be reachable by actually resolving: its own recorded
        signatures plus one alias have to come back as that row, or the table
        holds a build nothing can ever be classified as. Rows the resolver's own
        predicate excludes are pinned, not skipped."""
        builds = get_unified_rules().reference_builds
        assert {self._label(b) for b in builds if not _has_signatures(b)} == self.UNREACHABLE_ROWS
        for build in filter(_has_signatures, builds):
            declared = DeclaredReference(min(build.aliases), NAME_SOURCE_REFERENCE_FIELD)
            identity = resolve_identity(self._one_observation_of(build), declared)
            assert (identity.base, identity.version) == (build.family, build.version), self._label(build)

    def test_a_nameless_file_withholds_a_version_it_cannot_prove(self):
        """The genuine case: CHM13 v1.1 and v2.0 share chr1. Without a name, the
        family resolves and the version does not."""
        header = "@SQ\tSN:chr1\tLN:248387328\tM5:e469247288ceb332aee524caec92bb22\n"
        identity = identity_from_sam(header)
        assert identity.base == "CHM13"
        assert identity.version is None


class TestSchemaContract:
    """The emitted build must satisfy the contract the schema declares.

    The golden fixture in test_output_shape carries no ``build`` — its stub
    headers resolve none — so without these the new ReferenceBuild contract would
    never be exercised by any test.
    """

    def test_every_table_family_is_a_vocabulary_value(self):
        """``ReferenceBuild.base`` is range-constrained to reference_assembly_enum
        in the schema, so a table entry outside the vocabulary would emit a build
        that fails validation."""
        for build in get_unified_rules().reference_builds:
            assert schema_vocab.value_in_vocabulary("reference_assembly", build.family), build.family

    def test_an_emitted_base_is_a_vocabulary_value(self):
        """The same constraint on the path that actually produces output."""
        entry = classify_from_header(CHM13_V2)["reference_assembly"]
        assert schema_vocab.value_in_vocabulary("reference_assembly", entry["build"]["base"])

    def test_the_emitted_build_carries_exactly_the_declared_attributes(self):
        """The schema declares five class-local attributes; the emitted object
        must match them, or output and schema have drifted apart."""
        schema = yaml.safe_load((files("meta_disco.schema") / "classification.yaml").read_text(encoding="utf-8"))
        declared = set(schema["classes"]["ReferenceBuild"]["attributes"])
        entry = classify_from_header(CHM13_V2)["reference_assembly"]
        assert set(entry["build"]) == declared == set(IDENTITY_FIELDS)


class TestSerialization:
    def test_to_dict_always_carries_every_key(self):
        """So a consumer can tell "looked, found nothing" from "no such field"."""
        assert set(ReferenceIdentity().to_dict()) == set(IDENTITY_FIELDS)

    def test_is_empty_is_false_when_only_an_observation_survives(self):
        assert not ReferenceIdentity(name="mystery.fa").is_empty()
        assert ReferenceIdentity().is_empty()
