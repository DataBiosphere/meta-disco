"""The extended claim record holds a claim from any source (issue #392).

Epic #391's point is that our own inference, a submitter manifest and an external
catalog should say what they say in *one* format, so the three can be compared and
their mappings audited. The risk is that "one format" turns out to mean "the rule
format, plus a bespoke extension per source" — which is what the record looked
like before #392, when ``rule_id`` was the only producer handle.

So these build a claim from each of the three producers the `AnVIL_HPRC_R2` spike
covered, through the one public constructor, with no source-specific argument and
no post-hoc key added to the dict. Every raw value here is one the spike actually
observed. Unit-level by intent: the acceptance criterion asks for the record to be
demonstrated by tests rather than by a pipeline run, and no producer exists yet —
the AnVIL manifest importer is #369 and the HPRC catalog importer is #394.
"""

import pytest

from meta_disco.models import (
    DECLINED,
    JOIN_KEY_FILE_NAME,
    JOIN_KEY_FILE_PATH,
    NO_VOCABULARY_TERM,
    SOURCE_CONTIG_DETECTION,
    SOURCE_EXTERNAL_GROUND_TRUTH,
    SOURCE_REPOSITORY_METADATA,
    UNMAPPED,
    ClaimSource,
)
from meta_disco.rule_engine import CONTENT_TIER, make_claim

# The three producers the spike compared. Inference has no ClaimSource: it is not
# an external source, and its producer handle is the rule_id it already carried.
ANVIL_MANIFEST = ClaimSource(
    name="AnVIL",
    url="https://service.explore.anvilproject.org/",
    table="alignments_v2",
    column="location",
)
HPRC_CATALOG = ClaimSource(
    name="HPRC Data Explorer",
    url="https://data.humanpangenome.org/",
    table="assemblies",
    column="annotationType",
)


class TestInferenceClaim:
    """Producer 1: our own inference, the record's original inhabitant."""

    def test_content_claim_keeps_its_shape(self):
        claim = make_claim(
            rule_id="contig_length_detection",
            reason="Reference GRCh38 detected from 24 matching contig lengths (definitive)",
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            value="GRCh38",
        )
        assert claim["rule_id"] == "contig_length_detection"
        assert claim["value"] == "GRCh38"
        assert claim["tier"] == CONTENT_TIER
        assert claim["source_type"] == SOURCE_CONTIG_DETECTION
        # Nothing external is invented for it: an inference claim was never joined
        # to anything and read no raw value from a source.
        assert not {"source", "raw_value", "join_key", "match_exact"} & set(claim)


class TestManifestClaim:
    """Producer 2: the AnVIL verbatim manifest — a repository's own metadata."""

    def test_mapped_claim_records_the_raw_value_and_the_join(self):
        claim = make_claim(
            rule_id="map_anvil_instrument_model_v1",
            source_type=SOURCE_REPOSITORY_METADATA,
            source=ClaimSource(
                name="AnVIL",
                url="https://service.explore.anvilproject.org/",
                table="sequencing_activities",
                column="instrument_model",
            ),
            value="PACBIO",
            raw_value="Revio",
            join_key=JOIN_KEY_FILE_PATH,
            match_exact=True,
        )
        # The mapping is the reviewable decision, so both halves of Revio → PACBIO
        # are on the claim. Storing only the mapped value makes it unauditable.
        assert (claim["raw_value"], claim["value"]) == ("Revio", "PACBIO")
        assert claim["source"]["table"] == "sequencing_activities"
        assert claim["source"]["column"] == "instrument_model"
        assert (claim["join_key"], claim["match_exact"]) == (JOIN_KEY_FILE_PATH, True)
        # The mapping that produced it *is* a rule, so the claim names it — that is
        # where `Revio -> PACBIO` is written down and reviewed, and citing it is what
        # makes the claim reproducible (#401). It carries no tier: an imported claim
        # does not compete on the rule tiers.
        assert claim["rule_id"] == "map_anvil_instrument_model_v1"
        assert "tier" not in claim

    def test_unmapped_claim_carries_what_the_source_said(self):
        # library_selection=RANDOM: the source said something and no map entry
        # covers it. The raw value is the whole content of the claim — this is the
        # review queue, and without it there is nothing to review.
        claim = make_claim(
            reason="no map entry for library_selection=RANDOM",
            source_type=SOURCE_REPOSITORY_METADATA,
            source=ClaimSource(name="AnVIL", table="sequencing_activities", column="library_selection"),
            state=UNMAPPED,
            raw_value="RANDOM",
            join_key=JOIN_KEY_FILE_PATH,
            match_exact=True,
        )
        assert claim["claim_state"] == UNMAPPED
        assert claim["raw_value"] == "RANDOM"
        assert not {"value", "status", "tier"} & set(claim)
        # And no rule: `unmapped` means exactly that no mapping entry fired, which is
        # what makes the review queue derivable rather than curated by hand (#401).
        assert "rule_id" not in claim

    def test_declined_column_is_expressible_without_a_value(self):
        # The spike's 12 disagreements all came from one column: alignments_v2 has
        # a single `location` pointing at .gbz and .gfa.gz pangenome graphs *and* a
        # .wave.vcf.gz of variants, so the column is not an authority on data_type
        # whatever it holds. No value-level mapping and no finer key can fix that,
        # which is why `declined` is a state and not a mapped-to value.
        claim = make_claim(
            rule_id="decline_anvil_alignments_v2_location_v1",
            reason="alignments_v2.location is not an authority on data_type",
            source_type=SOURCE_REPOSITORY_METADATA,
            source=ANVIL_MANIFEST,
            state=DECLINED,
        )
        assert claim["claim_state"] == DECLINED
        assert claim["source"]["table"] == "alignments_v2"
        assert claim["source"]["column"] == "location"
        assert "value" not in claim


class TestCatalogClaim:
    """Producer 3: the HPRC Data Explorer — an external catalog."""

    def test_file_name_join_is_recorded_as_such(self):
        # The catalog publishes only file names (79.6% coverage on HPRC_R2), the
        # weakest key of the four. Which key was used is recorded per claim, so a
        # reader is never left assuming the join was on something stronger (#390).
        claim = make_claim(
            reason="platform from the catalog's sequencing technology",
            source_type=SOURCE_EXTERNAL_GROUND_TRUTH,
            source=HPRC_CATALOG,
            rule_id="map_hprc_platform_v1",
            value="PACBIO",
            raw_value="Revio",
            join_key=JOIN_KEY_FILE_NAME,
            match_exact=True,
        )
        assert claim["join_key"] == JOIN_KEY_FILE_NAME
        assert claim["source"]["name"] == "HPRC Data Explorer"

    def test_no_vocabulary_term_is_a_decision_not_a_gap(self):
        # CenSat and Hi-C are concepts our vocabulary has no term for. Mapping them
        # deliberately to nothing is a recorded decision, distinct from `unmapped`,
        # which means a mapping may still be owed (#391 sub-issue 8).
        claim = make_claim(
            rule_id="map_hprc_annotation_type_v1",
            reason="no data_type term for a centromeric satellite annotation",
            source_type=SOURCE_EXTERNAL_GROUND_TRUTH,
            source=HPRC_CATALOG,
            state=NO_VOCABULARY_TERM,
            raw_value="CenSat",
            join_key=JOIN_KEY_FILE_NAME,
            match_exact=True,
        )
        assert claim["claim_state"] == NO_VOCABULARY_TERM
        assert claim["raw_value"] == "CenSat"
        # Mapped deliberately to nothing is still a mapping, so it names the rule
        # that decided it — which is what distinguishes it from `unmapped` in the
        # record itself, not only by the label (#401).
        assert claim["rule_id"] == "map_hprc_annotation_type_v1"


class TestOneRecordAcrossProducers:
    """The three fit the same record, rather than three shapes that resemble one."""

    def test_the_three_producers_differ_only_in_what_they_fill_in(self):
        # The point of the epic: one key set, occupied differently. Inference names
        # a rule and no source; the manifest names a source and declares a state;
        # the catalog names a source, maps a value, and records its join. No
        # producer needs a key the others cannot use.
        inference = make_claim(
            rule_id="contig_length_detection",
            reason="contigs",
            tier=CONTENT_TIER,
            source_type=SOURCE_CONTIG_DETECTION,
            value="GRCh38",
        )
        manifest = make_claim(
            rule_id="decline_v1",
            reason="manifest",
            source_type=SOURCE_REPOSITORY_METADATA,
            source=ANVIL_MANIFEST,
            state=DECLINED,
        )
        catalog = make_claim(
            rule_id="map_v1",
            source_type=SOURCE_EXTERNAL_GROUND_TRUTH,
            source=HPRC_CATALOG,
            value="PACBIO",
            raw_value="Revio",
            join_key=JOIN_KEY_FILE_NAME,
            match_exact=False,
        )
        assert set(inference) == {"rule_id", "reason", "tier", "value", "source_type"}
        assert set(manifest) == {"rule_id", "reason", "claim_state", "source_type", "source"}
        # The catalog claim's text is resolved from the rule it names rather than
        # stored, so it carries no `reason`; and no `tier`, because it does not
        # compete on the rule tiers (#401).
        assert set(catalog) == {
            "rule_id",
            "value",
            "source_type",
            "source",
            "raw_value",
            "join_key",
            "match_exact",
        }

    @pytest.mark.parametrize(
        "member,value,expected",
        [
            ("name", None, "name"),
            ("name", "", "name"),
            ("name", 7, "name"),
            ("dataset", 7, "dataset"),
            ("column", 7, "column"),
        ],
    )
    def test_a_source_member_of_the_wrong_type_is_refused_when_it_is_built(self, member, value, expected):
        # A dataclass annotation is not a runtime check, and this is the one
        # evidence-file record that reaches output evidence without passing an
        # envelope — `ClaimSource(name="HPRC", dataset=7)` would serialize a number
        # into the schema's `Evidence` and be caught at no boundary before it.
        with pytest.raises(ValueError, match=f"claim source: {expected}"):
            ClaimSource(**{"name": "HPRC", member: value})

    def test_source_omits_members_it_does_not_have(self):
        # ClaimSource drops nulls, so a source with no column structure carries no
        # empty `column` key rather than a null one.
        assert ClaimSource(name="HPRC Data Explorer").to_dict() == {"name": "HPRC Data Explorer"}
        assert set(HPRC_CATALOG.to_dict()) == {"name", "url", "table", "column"}
