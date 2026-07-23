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
        # Called as a bare classmethod — no RuleEngine / UnifiedRules constructed.
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

    def test_archive_extension_keeps_tar_as_core(self):
        """A gzipped tarball: ``.tar`` is the core extension (an archive is a real
        file type), ``.gz`` the wrapper — the last token is never peeled away."""
        fn = parse("hprc-graph.tar.gz")
        assert fn.extension == ".tar"
        assert fn.wrappers == (".gz",)
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

    def test_double_wrapper_peels_both(self):
        """``.fast5.tar.gz`` is tar-archived and gzip-compressed around a
        ``.fast5`` core — both wrappers peel, in name order."""
        fn = parse("run.fast5.tar.gz")
        assert fn.extension == ".fast5"
        assert fn.wrappers == (".tar", ".gz")
        assert fn.stem == "run"

    def test_extensionless_name_is_none_not_junk(self):
        """The bug this fixes: extract_extension returns a junk last-dot suffix
        ('.0-mc-grch38'); the parsed extension is honestly None."""
        fn = parse("hprc-v1.0-mc-grch38")
        assert fn.extension is None
        assert fn.wrappers == ()
        assert fn.stem == "hprc-v1.0-mc-grch38"
        # And the old parser did return the junk suffix — this is the contrast.
        assert RULES.extract_extension("hprc-v1.0-mc-grch38") == ".0-mc-grch38"

    def test_unknown_simple_extension_is_none(self):
        fn = parse("readme.xyz")
        assert fn.extension is None
        assert fn.stem == "readme.xyz"


class TestBehaviorPreservation:
    """For every name with a *known* extension, the core extension plus its
    wrappers reconstruct exactly what the engine derived before (the compound
    ``extract_extension``) — so #244 changes the *representation*, not *which*
    names carry an extension. Rule routing is preserved: the core now stands in
    for the old compound (the rule ``extensions:`` lists were migrated in step)."""

    @pytest.mark.parametrize(
        "name",
        [
            "sample.bam",
            "HG00741.final.cram",
            "cohort.vcf.gz",
            "cohort.g.vcf.gz",
            "reads.fastq.gz",
            "reads.fq.gz",
            "genome.fasta",
            "genome.fa.gz",
            "regions.bed.gz",
            "graph.gfa.gz",
            "graph.rgfa",
            "NUFIP1_quant.sf",
            "archive.tar.gz",
            "run.fast5.tar.gz",
        ],
    )
    def test_core_plus_wrappers_reconstructs_old_compound(self, name):
        fn = parse(name)
        assert fn.extension is not None
        assert fn.extension + "".join(fn.wrappers) == RULES.extract_extension(name)


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
        """No known core extension (.txt isn't in the vocabulary), so extension is
        None; the .gz is captured as a wrapper and stripped from the stem."""
        fn = parse("notes.txt.gz")
        assert fn.extension is None
        assert fn.wrappers == (".gz",)
        assert fn.stem == "notes.txt"

    def test_bgz_is_not_mis_peeled_as_gz(self):
        """`.bgz` ends with `.gz`; the wrapper list is ordered longest-first so
        `.bgz` is captured whole, not mis-peeled as `.gz` leaving a dangling `b`."""
        fn = parse("notes.txt.bgz")
        assert fn.wrappers == (".bgz",)
        assert fn.stem == "notes.txt"
