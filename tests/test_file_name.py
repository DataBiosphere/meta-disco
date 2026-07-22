"""Tests for the FileName parsed-filename fact (#241)."""

import pytest

from meta_disco.file_name import FileName
from meta_disco.rule_engine import RuleEngine

RULES = RuleEngine().rules


def parse(name: str) -> FileName:
    return RULES.parse_file_name(name)


class TestExtension:
    def test_simple_known_extension(self):
        fn = parse("HG00741.final.cram")
        assert fn.extension == ".cram"
        assert fn.wrappers == ()
        assert fn.stem == "HG00741.final"

    def test_compound_extension_strips_to_stem(self):
        fn = parse("sample.vcf.gz")
        assert fn.extension == ".vcf.gz"
        assert fn.wrappers == (".gz",)
        assert fn.stem == "sample"

    def test_archive_extension(self):
        fn = parse("hprc-graph.tar.gz")
        assert fn.extension == ".tar.gz"
        assert fn.wrappers == (".tar", ".gz")
        assert fn.stem == "hprc-graph"

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
    """For every name that has a *known* extension, the parsed extension matches
    what the engine derived before (extract_extension) — so rule routing is
    unchanged. Only unknown/absent extensions differ (junk suffix -> None)."""

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
        ],
    )
    def test_known_extension_matches_extract_extension(self, name):
        assert parse(name).extension == RULES.extract_extension(name)


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
