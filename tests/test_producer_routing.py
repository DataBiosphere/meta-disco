"""Every file has exactly one producer, because one function says so.

Routing used to be four predicates in four places, so two producers could claim one
record and the run wrote it twice (#445). `producers.route` is now the only answer, and
it is a single choice, so a second claimant is not a thing to test for but a thing that
cannot be constructed. What is left to pin is that the choice is the right one, and that
the registry keeps the property the single choice depends on: no two producers claiming
overlapping extensions.
"""

import pytest

from meta_disco.producers import PRODUCERS, Producer, producer_of, validate_registry
from tests.metadata_fixtures import valid_record
from tests.producer_sweep import classify_auxiliary_genomic, run_producer


def _fast5_tar_record(file_name="HG02148_1.fast5.tar", file_format=".fast5.tar"):
    return valid_record(file_name=file_name, file_format=file_format, dataset_title="ANVIL_HPRC")


def test_exactly_one_producer_claims_nothing_by_extension():
    """The catch-all's claim is that `route` found no one — so exactly one producer may
    be declared with no extensions, or "no producer claims this" would name two."""
    claimless = [name for name, producer in PRODUCERS.items() if not producer.extensions]
    assert claimless == ["remaining"]


def test_a_record_is_claimed_by_one_producer_or_none():
    """The property the four predicates could not offer: asking every producer whether a
    file is theirs returns at most one yes, whatever the record says."""
    records = [
        valid_record(file_name="HG002.bam", file_format=".bam"),
        valid_record(file_name="HG002.g.vcf.gz", file_format=".vcf.gz"),
        valid_record(file_name="HG02148_1.fast5.tar", file_format=".fast5"),
        valid_record(file_name="slide.svs", file_format=".svs"),
        valid_record(file_name="HG002.bam.bai", file_format=".bai"),
        valid_record(file_name="mystery.xyz", file_format=".xyz"),
    ]
    for record in records:
        claimants = [name for name, producer in PRODUCERS.items() if producer.claims(record)]
        assert len(claimants) <= 1, f"{record['file_name']} is claimed by {claimants}"


class TestTheNameDecidesBeforeTheFormat:
    """`file_format` is consulted only when no producer claims the name.

    The two used to be matched independently, which is how one file answered two
    producers with no shared extension at all — the shape the overlap check above cannot
    see, and the one that actually cost a run (#445).
    """

    def test_the_name_wins_when_the_two_disagree(self):
        """A source declaring the core extension of an archive does not move the file."""
        record = valid_record(file_name="HG02148_1.fast5.tar", file_format=".fast5")
        assert producer_of(record) is PRODUCERS["tar"]

    def test_the_format_is_used_when_no_producer_claims_the_name(self):
        record = valid_record(file_name="HG02148_1.unknown", file_format=".fast5")
        assert producer_of(record) is PRODUCERS["auxiliary"]

    def test_a_record_claimed_by_neither_is_the_catch_alls(self):
        assert producer_of(valid_record(file_name="notes.xyz", file_format=".xyz")) is None

    def test_a_drifted_format_does_not_raise(self):
        """Routing runs before validation, so a non-string field must not raise here —
        the record is still to be written as a validation_failed row (#155/#161)."""
        assert producer_of(valid_record(file_name="HG002.bam", file_format=17)) is PRODUCERS["bam"]

    def test_the_matched_extension_is_the_most_specific_one(self):
        """Within a producer, the longest matching extension is the one reported — what
        the per-extension summaries and the index producer's parent lookup read."""
        assert PRODUCERS["vcf"].claim(valid_record(file_name="s.g.vcf.gz", file_format=".vcf.gz")) == ".g.vcf.gz"


class TestATarOfFast5sIsATar:
    """An archive is classified as the container it is, by the producer that reads its
    members — not by the producer that knows the inner format's name (#242)."""

    def test_the_auxiliary_producer_writes_no_row_for_it(self, tmp_path):
        assert run_producer(classify_auxiliary_genomic, tmp_path, [_fast5_tar_record()]) == []

    @pytest.mark.parametrize(
        "file_name, file_format",
        [
            ("HG02148_1.fast5.tar", ".fast5"),
            ("HG02148_1.fast5.tar.gz", ".fast5"),
            ("HG02148_1.fast5.TAR", ".fast5"),
        ],
        ids=["tar", "tar.gz", "upper"],
    )
    def test_nor_when_the_source_declares_the_core_extension(self, tmp_path, file_name, file_format):
        """A source may set `file_format` from the parsed core, so the archive arrives
        declaring `.fast5`. Matching that on the format while the tar type matches the
        name is how one file gets two rows with no shared extension to detect."""
        records = [_fast5_tar_record(file_name=file_name, file_format=file_format)]
        assert run_producer(classify_auxiliary_genomic, tmp_path, records) == []

    @pytest.mark.parametrize(
        "file_name",
        ["HG02148_1.fast5", "HG02148_1.fast5.tar.xz"],
        ids=["unwrapped", "tar under another compression"],
    )
    def test_what_the_tar_type_does_not_claim_stays_here(self, tmp_path, file_name):
        """The handover goes exactly as far as `TAR_CONFIG`. A `.tar.xz` is claimed by no
        type, so giving it up would send it to the catch-all for nothing."""
        rows = run_producer(classify_auxiliary_genomic, tmp_path, [_fast5_tar_record(file_name, ".fast5")])
        assert [r["file_name"] for r in rows] == [file_name]

    @pytest.mark.parametrize(
        "file_name, file_format",
        [
            ("HG02148_1.fast5.tar", ".fast5.tar"),
            ("HG02148_1.fast5.TAR", ".fast5"),
        ],
        ids=["lower", "upper"],
    )
    def test_the_tar_type_routes_it(self, file_name, file_format):
        """The other half of the handover, including the cased one: the file the
        auxiliary producer does not write is one the tar type takes, so it is written
        exactly once. Asked through `claims`, the public "does this type take this file"
        — this used to reach into two of ClassifyPipeline's private methods for want of
        one."""
        assert PRODUCERS["tar"].claims(_fast5_tar_record(file_name, file_format))


def _overlapping_producer(extension):
    """A producer claiming an extension that ends with one a real producer claims."""
    return Producer(name="archives", script="x.py", output="x.json", phase=1, extensions=(extension,))


class TestTheRegistryRefusesAnOverlap:
    """`validate_registry` is the check that lets `route` be a rule about names.

    With two producers claiming extensions where one is a suffix of the other, no rule
    about a file name could say which owns a file — so the registry is refused at
    declaration time rather than a precedence table being invented at routing time.
    """

    def test_an_overlapping_claim_is_refused_and_both_sides_are_named(self, monkeypatch):
        monkeypatch.setitem(PRODUCERS, "archives", _overlapping_producer(".fast5.tar"))
        with pytest.raises(ValueError, match="overlapping extensions") as raised:
            validate_registry()
        assert "archives .fast5.tar" in str(raised.value)
        assert "tar .tar" in str(raised.value)

    def test_a_producer_may_hold_two_of_its_own_nested_extensions(self):
        """The relation is refused only *between* producers: `vcf` claims both `.vcf.gz`
        and `.g.vcf.gz`, and picking the longer of its own is not an ownership question.

        The real registry holds that pair and is accepted — importing this module ran
        `validate_registry` over it, so an overlap would have failed collection.
        """
        assert {".vcf.gz", ".g.vcf.gz"} <= set(PRODUCERS["vcf"].extensions)
