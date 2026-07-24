"""Tests for the FileName parsed-filename fact (#241, #243)."""

import pytest

from meta_disco.file_name import FileName, Format, FormatSource
from meta_disco.rule_engine import RuleEngine

RULES = RuleEngine().rules


def parse(name: str) -> FileName:
    return RULES.parse_file_name(name)


class TestPureParse:
    """#252: FileName.parse is pure — no UnifiedRules instance."""

    @pytest.mark.parametrize(
        "name",
        [
            "sample.bam",
            "cohort.vcf.gz",
            "HG002.g.vcf.gz",
            "HG002.g.vcf",
            "reads.fastq.gz",
            "readme.xyz",
            "notes.txt.gz",
        ],
    )
    def test_parse_needs_no_rules_and_matches_delegator(self, name):
        # FileName.parse takes no rules instance and needs none — the parse is pure.
        # (The module-level RULES exists only for the delegator-equivalence check.)
        fn = FileName.parse(name)
        assert isinstance(fn, FileName)
        # The UnifiedRules delegator returns the identical fact.
        assert fn == RULES.parse_file_name(name)


class TestExtension:
    def test_simple_known_extension(self):
        fn = parse("HG00741.final.cram")
        assert fn.extension == ".cram"
        assert fn.wrappers == ()
        assert fn.stem == "HG00741.final"

    def test_compound_extension_splits_core_from_wrapper(self):
        """#244: the compression is split off, so extension is the clean core
        (``.vcf``) with ``.gz`` recorded as a wrapper."""
        fn = parse("sample.vcf.gz")
        assert fn.extension == ".vcf"
        assert fn.wrappers == (".gz",)
        assert fn.stem == "sample"

    def test_archive_container_has_no_core(self):
        """#245: an archive with no inner format is a container, not a content
        extension — ``.tar`` and ``.gz`` both peel as wrappers and the extension is
        honestly None (a tar of unknown files is not classifiable from its name)."""
        fn = parse("hprc-graph.tar.gz")
        assert fn.extension is None
        assert fn.wrappers == (".tar", ".gz")
        assert fn.stem == "hprc-graph"

    def test_gvcf_keeps_its_own_core(self):
        """``.g.vcf.gz`` splits to the ``.g.vcf`` core (a distinct gVCF signal),
        not ``.vcf`` — only the ``.gz`` wrapper is peeled."""
        fn = parse("HG002.deepvariant.g.vcf.gz")
        assert fn.extension == ".g.vcf"
        assert fn.wrappers == (".gz",)
        assert fn.stem == "HG002.deepvariant"

    def test_uncompressed_gvcf_recognized_as_core(self):
        """#249: an uncompressed ``sample.g.vcf`` is recognized as the ``.g.vcf``
        core (→ Format.GVCF), consistent with the compressed spelling — where the
        old single-suffix gate resolved it to ``.vcf``. Longest-first core matching
        picks ``.g.vcf`` over its ``.vcf`` tail."""
        fn = parse("HG002.deepvariant.g.vcf")
        assert fn.extension == ".g.vcf"
        assert fn.format is Format.GVCF
        assert fn.wrappers == ()
        assert fn.stem == "HG002.deepvariant"

    def test_double_wrapper_peels_both_to_inner_core(self):
        """``run.fast5.tar.gz`` is tar-archived and gzip-compressed around a
        ``.fast5`` core — both containers peel and the inner ``.fast5`` is
        recognized underneath (#245), with no per-combination allowlist entry."""
        fn = parse("run.fast5.tar.gz")
        assert fn.extension == ".fast5"
        assert fn.wrappers == (".tar", ".gz")
        assert fn.stem == "run"

    def test_extensionless_name_is_none_not_junk(self):
        """A name whose last dot-token is not a known core yields extension None,
        not a junk last-dot suffix (``.0-mc-grch38``)."""
        fn = parse("hprc-v1.0-mc-grch38")
        assert fn.extension is None
        assert fn.wrappers == ()
        assert fn.stem == "hprc-v1.0-mc-grch38"

    def test_unknown_simple_extension_is_none(self):
        fn = parse("readme.xyz")
        assert fn.extension is None
        assert fn.stem == "readme.xyz"

    def test_length_changing_lowercase_char_does_not_skew_the_stem(self):
        """`"İ".lower()` is two chars, so slicing the stem by the lowercased length
        would over-keep. The suffix (wrappers + core) is ASCII, so the stem is sliced
        off the original name by suffix length and stays correct."""
        fn = parse("İ.bam")
        assert fn.extension == ".bam"
        assert fn.stem == "İ"


class TestContainersArePeeled:
    """#245: every compression/archive container is peeled off the name before the
    core is recognized, so a core matches under any container spelling (``.vcf`` for
    ``sample.vcf.gz``) and an archive with no inner format has no core."""

    @pytest.mark.parametrize(
        ("name", "extension", "wrappers"),
        [
            ("sample.bam", ".bam", ()),
            ("cohort.vcf.gz", ".vcf", (".gz",)),
            ("cohort.g.vcf.gz", ".g.vcf", (".gz",)),
            ("reads.fastq.gz", ".fastq", (".gz",)),
            ("genome.fa.gz", ".fa", (".gz",)),
            ("regions.bed.gz", ".bed", (".gz",)),
            ("graph.gfa.gz", ".gfa", (".gz",)),
            ("run.fast5.tar.gz", ".fast5", (".tar", ".gz")),
            # Containers with no inner format → no core, containers as wrappers.
            ("archive.tar.gz", None, (".tar", ".gz")),
            ("bundle.zip", None, (".zip",)),
            ("chr1.0_248956422.tar", None, (".tar",)),
        ],
    )
    def test_container_peeled_then_core_recognized(self, name, extension, wrappers):
        fn = parse(name)
        assert fn.extension == extension
        assert fn.wrappers == wrappers


class TestFormat:
    """The stage-1 derived format (#243): extension -> canonical Format, with
    the provenance recorded in format_source. Set together or both None."""

    def test_spelling_and_compression_variants_collapse_to_one_format(self):
        """The point of format: four extensions, one identity."""
        for name in ("genome.fa", "genome.fasta", "genome.fa.gz", "genome.fasta.gz"):
            fn = parse(name)
            assert fn.format is Format.FASTA
            assert fn.format_source is FormatSource.EXTENSION

    def test_distinct_formats_stay_distinct(self):
        """.bam and .cram are separate identities — the assay rules key on the
        extension to tell them apart, so format must not collapse them."""
        assert parse("x.bam").format is Format.BAM
        assert parse("x.cram").format is Format.CRAM

    def test_compound_extension_resolves_format(self):
        assert parse("cohort.g.vcf.gz").format is Format.GVCF
        assert parse("cohort.vcf.gz").format is Format.VCF

    def test_unmapped_extension_has_no_format(self):
        """A known extension with no seeded format (e.g. an image) is honestly
        unresolved — format and its source are both None."""
        fn = parse("slide.svs")
        assert fn.extension == ".svs"
        assert fn.format is None
        assert fn.format_source is None

    def test_absent_extension_has_no_format(self):
        fn = parse("hprc-v1.0-mc-grch38")
        assert fn.extension is None
        assert fn.format is None
        assert fn.format_source is None


class TestWrappers:
    def test_uncompressed_has_no_wrappers(self):
        assert parse("sample.bam").wrappers == ()

    def test_bare_compression_without_format(self):
        """No known core extension (.xyz isn't in the vocabulary), so extension is
        None; the .gz is captured as a wrapper and stripped from the stem."""
        fn = parse("blob.xyz.gz")
        assert fn.extension is None
        assert fn.wrappers == (".gz",)
        assert fn.stem == "blob.xyz"

    def test_bgz_is_not_mis_peeled_as_gz(self):
        """`.bgz` ends with `.gz`; the wrapper list is ordered longest-first so
        `.bgz` is captured whole, not mis-peeled as `.gz` leaving a dangling `b`."""
        fn = parse("blob.xyz.bgz")
        assert fn.wrappers == (".bgz",)
        assert fn.stem == "blob.xyz"

    def test_compressed_core_is_recognized_under_the_wrapper(self):
        """#245: peel-first recognizes a known core beneath any container spelling —
        a gzipped ``.tsv`` is a ``.tsv``, not an unrecognized blob."""
        fn = parse("expression.tsv.gz")
        assert fn.extension == ".tsv"
        assert fn.wrappers == (".gz",)
        assert fn.stem == "expression"
