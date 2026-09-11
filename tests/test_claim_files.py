"""The claim file: envelope, provenance and NDJSON (#401).

A claim file is how an importer that ran yesterday, against a network catalog, hands
claims to a run happening today. Three things have to hold for that to be safe, and
they are what these tests cover.

*It must say where it came from.* Provenance is per file, recorded once, and read
back whole — including the ``ClaimSource`` each claim's own record carries, which the
writer factors into the envelope and the reader puts back.

*Its age must be visible.* A run says what it consumed and how old each one was. It
does not adjudicate currency: nothing offline can, since the sources share no version
to compare and AnVIL deletes a superseded catalog rather than keeping it to be matched
against. That question belongs to the importer's re-fetch decision and to the catalog
an enhancement is offered back to. Note what these tests therefore do *not* cover: a
run reports its claim files and imports nothing from them — ``iter_claims`` has no
caller in the run — so nothing here asserts that a claim reaches classification, and
nothing does until the identity join lands (#402).

*It must stream.* Millions of claims cannot go through a whole-file parse (#374), so
the reader yields claims as it reads them and a malformed line fails naming the file
and the line rather than taking the file down.

Unit-level by intent: no importer exists yet (#369, #394) and the join to our files
is #400b, so the producers here are hand-built claims from the ``AnVIL_HPRC_R2``
spike's two external sources.
"""

import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from meta_disco.claim_files import (
    DEFAULT_CLAIMS_ROOT,
    ENVELOPE_KEY,
    ClaimEntry,
    discover,
    iter_claims,
    read_envelope,
    report_claim_files,
    write_claim_file,
)
from meta_disco.models import (
    JOIN_KEY_FILE_MD5SUM,
    JOIN_KEY_FILE_NAME,
    NO_VOCABULARY_TERM,
    SOURCE_REPOSITORY_METADATA,
    SOURCE_WRANGLER_ANNOTATION,
    UNMAPPED,
    ClaimFileEnvelope,
    ClaimFileSource,
    ClaimSource,
    ClaimTarget,
)
from meta_disco.rule_engine import make_claim

HPRC_CATALOG = ClaimFileSource(
    repository="HPRC Data Explorer",
    dataset="R2",
    table="sequencing-data",
    url="https://data.humanpangenome.org/",
)
ANVIL_MANIFEST = ClaimFileSource(
    repository="AnVIL",
    dataset="AnVIL_HPRC_R2",
    table="alignments_v2",
    url="https://service.explore.anvilproject.org/",
)
ANVIL_TARGET = ClaimTarget(system="anvil", dataset="AnVIL_HPRC_R2", version="anvil15")
FETCHED_AT = datetime(2026, 9, 1, 9, 14, 3)
# A fetch time as an envelope on disk carries it. Used wherever a case needs a
# *valid* fetched_at so that it isolates the member actually under test — a bare
# date is refused in its own right, for having no time of day.
ISO_NOW = FETCHED_AT.isoformat()


def claim_file_envelope(**overrides) -> ClaimFileEnvelope:
    """An HPRC catalog envelope: filenames the catalog publishes, matched against
    AnVIL's ``file_name`` within the dataset that makes that key usable."""
    return ClaimFileEnvelope(
        **{
            "source": HPRC_CATALOG,
            "source_version": "2026-09-01",
            "source_key": "filename",
            "target": ANVIL_TARGET,
            "target_key": JOIN_KEY_FILE_NAME,
            "fetched_at": FETCHED_AT,
            **overrides,
        }
    )


def _entry(column="platform", raw="Revio", value="PACBIO", name="HG002.bam", source=HPRC_CATALOG) -> ClaimEntry:
    """One mapped platform claim, keyed by the file name the catalog publishes."""
    return ClaimEntry(
        field="platform",
        target_key_value=name,
        claim=make_claim(
            source_type=SOURCE_REPOSITORY_METADATA,
            source=source.as_claim_source(column),
            rule_id="map_hprc_platform_v1",
            raw_value=raw,
            value=value,
        ),
    )


class TestRoundTrip:
    """A claim file says where it came from, and gives back the claims put into it."""

    def test_envelope_carries_source_table_fetch_date_and_version(self, tmp_path):
        path = tmp_path / "hprc" / "sequencing_data.ndjson"
        write_claim_file(path, claim_file_envelope(), [_entry()])

        envelope = read_envelope(path)
        assert envelope.source == HPRC_CATALOG
        assert envelope.source.dataset == "R2"
        assert envelope.source.url == "https://data.humanpangenome.org/"
        assert envelope.fetched_at == FETCHED_AT
        assert envelope.source_version == "2026-09-01"
        # Both sides of the join, and which key pairs with which.
        assert (envelope.source_key, envelope.target_key) == ("filename", JOIN_KEY_FILE_NAME)
        assert envelope.target == ANVIL_TARGET

    def test_a_claim_comes_back_whole(self, tmp_path):
        """The claim read back is the claim written, source and all."""
        path = tmp_path / "claims.ndjson"
        entry = _entry()
        write_claim_file(path, claim_file_envelope(), [entry])

        assert list(iter_claims(path)) == [entry]

    def test_a_rehydrated_claim_can_interpret_its_own_column(self, tmp_path):
        """The dataset crosses onto the claim, not only onto the envelope.

        The same column name means different things in different datasets, so a claim
        naming only its column could not be read without going back to the file it
        arrived in — which nothing reading the output evidence array can do (#401).
        """
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, claim_file_envelope(), [_entry(column="platform")])

        (source,) = [entry.claim["source"] for entry in iter_claims(path)]
        assert (source["name"], source["dataset"], source["table"], source["column"]) == (
            "HPRC Data Explorer",
            "R2",
            "sequencing-data",
            "platform",
        )

    def test_each_claim_gets_its_own_rehydrated_source(self, tmp_path):
        """The reader factors the source in per claim, so claims cannot alias one dict."""
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, claim_file_envelope(), [_entry(name="a.bam"), _entry(name="b.bam")])

        first, second = (entry.claim["source"] for entry in iter_claims(path))
        assert first == second
        first["table"] = "edited"
        assert second["table"] == "sequencing-data"

    def test_the_raw_value_survives_beside_the_mapped_one(self, tmp_path):
        """The mapping is the reviewable decision, so `Revio` must outlive the file."""
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, claim_file_envelope(), [_entry(raw="Revio", value="PACBIO")])

        (claim,) = [entry.claim for entry in iter_claims(path)]
        assert (claim["raw_value"], claim["value"]) == ("Revio", "PACBIO")

    def test_a_state_claim_survives_the_round_trip(self, tmp_path):
        """`Hi-C` mapped deliberately to nothing is the review queue — it must be kept."""
        path = tmp_path / "claims.ndjson"
        entry = ClaimEntry(
            field="assay_type",
            target_key_value="HG002.hic.bam",
            claim=make_claim(
                source_type=SOURCE_REPOSITORY_METADATA,
                source=HPRC_CATALOG.as_claim_source("assayType"),
                rule_id="map_hprc_assay_v1",
                raw_value="Hi-C",
                state=NO_VOCABULARY_TERM,
            ),
        )
        write_claim_file(path, claim_file_envelope(), [entry])

        assert list(iter_claims(path)) == [entry]

    def test_the_count_written_is_returned(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        assert write_claim_file(path, claim_file_envelope(), [_entry(name=f"HG{n:04d}.bam") for n in range(7)]) == 7


class TestTheEnvelopeIsFactoredOut:
    """Name, url and table are recorded once; only `column` stays on a claim."""

    def test_a_written_claim_repeats_no_envelope_field(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, claim_file_envelope(), [_entry(column="platform")])

        claim = json.loads(path.read_text().splitlines()[1])["claim"]
        assert "source" not in claim
        assert claim["column"] == "platform"

    def test_line_one_is_the_envelope_and_is_labelled_as_one(self, tmp_path):
        """An envelope is told from a claim by its shape, not by being first."""
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, claim_file_envelope(), [_entry()])

        assert list(json.loads(path.read_text().splitlines()[0])) == [ENVELOPE_KEY]

    def test_a_claim_from_another_source_is_refused_at_write(self, tmp_path):
        """A file's claims must have come from the source its envelope names."""
        path = tmp_path / "claims.ndjson"
        with pytest.raises(ValueError, match="envelope names"):
            write_claim_file(path, claim_file_envelope(), [_entry(source=ANVIL_MANIFEST)])

    def test_nothing_is_left_behind_when_a_claim_is_refused(self, tmp_path):
        """The temp-file-and-rename write leaves the previous file, or none at all."""
        path = tmp_path / "claims.ndjson"
        with pytest.raises(ValueError):
            write_claim_file(path, claim_file_envelope(), [_entry(source=ANVIL_MANIFEST)])

        assert not path.exists()
        assert list(tmp_path.iterdir()) == []

    def test_the_caller_s_claim_is_not_mutated(self, tmp_path):
        """Factoring the source out is the file's business, not the importer's."""
        entry = _entry()
        before = json.loads(json.dumps(entry.claim))
        write_claim_file(tmp_path / "claims.ndjson", claim_file_envelope(), [entry])

        assert entry.claim == before


class TestMalformedFiles:
    """A file that will not read fails naming itself and the line."""

    def test_a_malformed_line_names_the_file_and_the_line(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, claim_file_envelope(), [_entry(), _entry()])
        path.write_text(path.read_text() + "{not json\n")

        with pytest.raises(ValueError, match=r"claims\.ndjson line 4: not a claim"):
            list(iter_claims(path))

    def test_claims_before_a_malformed_line_are_yielded_first(self, tmp_path):
        """Proof the reader streams: it cannot have parsed line 5 before yielding line 2."""
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, claim_file_envelope(), [_entry(name=f"HG{n}.bam") for n in range(3)])
        path.write_text(path.read_text() + "{not json\n")

        read = []
        with pytest.raises(ValueError):
            for entry in iter_claims(path):
                read.append(entry.target_key_value)
        assert read == ["HG0.bam", "HG1.bam", "HG2.bam"]

    def test_an_invalid_byte_is_named_by_line_not_raised_as_a_codec_error(self, tmp_path):
        """A text handle decodes inside its own iterator, so a bad byte in a later
        record escaped as `UnicodeDecodeError` with a byte offset — a traceback
        rather than the line-numbered ValueError this module promises. The file is
        opened as bytes and decoded where the line number is known."""
        path = tmp_path / "c.ndjson"
        envelope = json.dumps({ENVELOPE_KEY: claim_file_envelope().to_dict()}).encode() + b"\n"
        path.write_bytes(envelope + b'{"field":"platform","target_key_value":"\xff\xfe","claim":{}}\n')

        with pytest.raises(ValueError, match=r"c\.ndjson line 2: not valid UTF-8"):
            list(iter_claims(path))

    def test_a_blank_line_carries_no_claim(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, claim_file_envelope(), [_entry()])
        path.write_text(path.read_text() + "\n")

        assert len(list(iter_claims(path))) == 1

    def test_an_empty_file_is_a_missing_envelope_not_an_empty_claim_set(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        path.write_text("")

        with pytest.raises(ValueError, match="line 1 must be the claim_file envelope"):
            read_envelope(path)
        with pytest.raises(ValueError, match="line 1 must be the claim_file envelope"):
            list(iter_claims(path))

    @pytest.mark.parametrize(
        "envelope,expected",
        [
            ({"source": {"url": "u"}}, "source repository"),
            ({"source": {"repository": ""}}, "source repository"),
            ({"source": {"repository": None}}, "source repository"),
            ({"source": {"repository": "HPRC", "table": 7}}, "source table"),
            ({"fetched_at": None}, "fetched_at"),
            ({"fetched_at": "yesterday"}, "not an ISO 8601"),
            ({"fetched_at": "2026-09-01"}, "no time of day"),
            ({"source_version": ""}, "source_version"),
            ({"source_key": None}, "source_key"),
            ({"target": {"system": ""}}, "target system"),
            ({"target": {"system": "anvil", "dataset": 7}}, "target dataset"),
            ({"target_key": "sample_id"}, "not a key of the target"),
        ],
    )
    def test_an_envelope_missing_a_fact_is_refused(self, tmp_path, envelope, expected):
        """Every envelope member is checked on read: the report rests on all of them.

        Each case overrides one member of a valid envelope, so what it asserts is
        that member and not an unrelated one that happened to be missing too.
        """
        path = tmp_path / "claims.ndjson"
        path.write_text(json.dumps({ENVELOPE_KEY: {**claim_file_envelope().to_dict(), **envelope}}) + "\n")

        with pytest.raises(ValueError, match=expected):
            read_envelope(path)

    def test_a_claim_for_an_unknown_dimension_is_refused_both_ways(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        entry = _entry()
        with pytest.raises(ValueError, match="unknown dimension"):
            write_claim_file(path, claim_file_envelope(), [ClaimEntry("data_moddality", "x", entry.claim)])

        write_claim_file(path, claim_file_envelope(), [entry])
        path.write_text(path.read_text().replace('"platform"', '"data_moddality"', 1))
        with pytest.raises(ValueError, match="line 2: unknown dimension"):
            list(iter_claims(path))

    def test_a_line_with_nothing_to_match_on_is_refused(self, tmp_path):
        """A claim whose target_key_value is empty can attach to no row."""
        entry = _entry()
        with pytest.raises(ValueError, match="target_key_value"):
            write_claim_file(tmp_path / "c.ndjson", claim_file_envelope(), [ClaimEntry(entry.field, "", entry.claim)])

    def test_an_envelope_naming_a_key_the_target_does_not_have_is_refused(self, tmp_path):
        """`target_key` is a key of the *target*. A source keyed by something else maps
        it to one of these itself rather than adding a term here."""
        with pytest.raises(ValueError, match="not a key of the target"):
            claim_file_envelope(target_key="sample_id")


class TestAWriterCannotProduceWhatTheReaderRefuses:
    """The two sides of the contract agree, so a fault surfaces at the importer (#401 review).

    The write path used to check every claim and never the envelope, so a networked
    import could spend its run writing millions of claims behind a header its own
    reader would reject — discovered at the next classification run, far from the
    cause.
    """

    @pytest.mark.parametrize("version", ["", None])
    def test_an_envelope_with_no_usable_version_is_refused_when_it_is_built(self, version):
        """`None` was the trap: `to_dict` drops nulls, so the key vanished entirely."""
        with pytest.raises(ValueError, match="source_version"):
            claim_file_envelope(source_version=version)

    def test_an_envelope_with_a_nameless_source_is_refused_when_it_is_built(self):
        with pytest.raises(ValueError, match="source repository"):
            claim_file_envelope(source=ClaimFileSource(repository=""))

    def test_an_envelope_with_a_non_datetime_fetch_time_is_refused_when_it_is_built(self):
        with pytest.raises(ValueError, match="fetched_at"):
            claim_file_envelope(fetched_at="2026-09-01")

    def test_an_envelope_cannot_name_a_column_at_all(self):
        """A column belongs to a claim, not to a file — the type says so.

        `ClaimFileSource` has no `column` member, so an envelope naming one is not a
        value to be refused at runtime but a shape that cannot be expressed. One
        table's claims are read from several columns, so a column on the envelope
        could disagree with every line in the file.
        """
        assert "column" not in {f.name for f in fields(ClaimFileSource)}
        with pytest.raises(TypeError):
            ClaimFileSource(repository="HPRC", table="t", column="platform")  # type: ignore[call-arg]

    def test_an_envelope_whose_source_has_a_non_string_member_is_refused_when_it_is_built(self):
        """The annotation says `str | None`, so the ignore is the point of the test:
        type hints do not run, and an importer mapping a source's own JSON can hand
        over whatever that JSON held."""
        with pytest.raises(ValueError, match="source table"):
            claim_file_envelope(source=ClaimFileSource(repository="HPRC", table=7))  # type: ignore[arg-type]

    def test_a_hand_built_claim_the_reader_would_refuse_is_refused_at_write(self, tmp_path):
        """An importer can build a ClaimEntry by hand; the writer holds it to make_claim."""
        entry = ClaimEntry(
            field="platform",
            target_key_value="HG002.bam",
            claim={
                "source_type": SOURCE_REPOSITORY_METADATA,
                "value": "PACBIO",
                "source": HPRC_CATALOG.as_claim_source("platform").to_dict(),
            },
        )

        with pytest.raises(ValueError, match="cites no mapping rule"):
            write_claim_file(tmp_path / "c.ndjson", claim_file_envelope(), [entry])

    def test_a_file_the_run_would_never_find_is_refused_at_write(self, tmp_path):
        """`discover` matches *.ndjson, so any other suffix is a silent no-op."""
        with pytest.raises(ValueError, match="must be named"):
            write_claim_file(tmp_path / "hprc" / "catalog.json", claim_file_envelope(), [_entry()])

    @pytest.mark.parametrize("block", [{"rank": 9}, {"source": {"name": "HPRC", "column": None}}])
    def test_an_unknown_envelope_member_is_refused_with_the_file_and_line(self, tmp_path, block):
        """The schema validates the envelope `closed=True`; the reader must agree.

        A `"column": null` on an envelope source used to be accepted here and
        silently stripped while the schema rejected it. Refusing it in `from_dict`
        also names the file and line, which `__post_init__` cannot — it validates a
        constructed envelope and does not know where one came from.
        """
        path = tmp_path / "c.ndjson"
        envelope = {**claim_file_envelope().to_dict(), **block}
        path.write_text(json.dumps({ENVELOPE_KEY: envelope}) + "\n")

        with pytest.raises(ValueError, match=r"c\.ndjson line 1: .*unknown member"):
            read_envelope(path)

    @pytest.mark.parametrize(
        "wrapper",
        [
            {ENVELOPE_KEY: "ENVELOPE", "unexpected": 1},
            {"not_the_key": "ENVELOPE"},
            ["ENVELOPE"],
        ],
    )
    def test_line_one_must_be_the_envelope_and_nothing_else(self, tmp_path, wrapper):
        """An unknown member *within* the envelope is refused; a sibling of it must be too.

        Otherwise the same malformed provenance is discarded rather than reported
        depending only on which side of one brace it sat.
        """
        envelope = claim_file_envelope().to_dict()
        payload = (
            [envelope if v == "ENVELOPE" else v for v in wrapper]
            if isinstance(wrapper, list)
            else {k: (envelope if v == "ENVELOPE" else v) for k, v in wrapper.items()}
        )
        path = tmp_path / "c.ndjson"
        path.write_text(json.dumps(payload) + "\n")

        with pytest.raises(ValueError, match=r"c\.ndjson line 1"):
            read_envelope(path)

    def test_a_utc_z_suffix_reads_back_on_every_supported_interpreter(self, tmp_path):
        """`fromisoformat` rejects `Z` on 3.10 (the floor and what CI runs), takes it on 3.11+.

        Our writer emits `+00:00`, but the importers in #369/#394 read web APIs that
        emit `Z` almost universally — a claim file must not parse on a dev box and
        fail on CI.
        """
        path = tmp_path / "c.ndjson"
        block = {**claim_file_envelope().to_dict(), "fetched_at": "2026-09-01T09:14:03Z"}
        path.write_text(json.dumps({ENVELOPE_KEY: block}) + "\n")

        assert read_envelope(path).fetched_at == datetime(2026, 9, 1, 9, 14, 3, tzinfo=timezone.utc)


class TestAClaimIsRebuiltNotTrusted:
    """A claim read off disk goes through `make_claim`, like every other claim (#401 review).

    A claim file is bytes written by an out-of-band process, and what comes off it
    reaches `evaluate_claims`. Passing the parsed dict through would make this the one
    producer that bypasses the single construction site.
    """

    def _write_raw(self, tmp_path, claim: dict) -> Path:
        """A claim file whose one line carries `claim` verbatim, bypassing the writer."""
        path = tmp_path / "c.ndjson"
        line = {"field": "platform", "target_key_value": "HG002.bam", "claim": claim}
        path.write_text(
            json.dumps({ENVELOPE_KEY: claim_file_envelope().to_dict()}) + "\n" + json.dumps(line) + "\n",
        )
        return path

    def test_a_claim_citing_no_mapping_rule_is_refused(self, tmp_path):
        """Every imported claim that declares anything names the mapping that made it.

        Including an identity mapping: there is no implicit copy, because a source
        value that happens to spell a vocabulary term is a coincidence of spelling
        rather than an agreement about meaning (#401).
        """
        path = self._write_raw(tmp_path, {"source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO"})

        with pytest.raises(ValueError, match="cites no mapping rule"):
            list(iter_claims(path))

    def test_a_claim_carrying_a_tier_is_refused(self, tmp_path):
        """An imported claim does not compete on the rule tiers, so a tier on one is a
        number the policy discards — and one a file could forge to outrank every rule."""
        claim = {"source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "rule_id": "m1", "tier": 999}
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match="does not"):
            list(iter_claims(path))

    def test_a_claim_with_an_unknown_source_type_is_refused(self, tmp_path):
        path = self._write_raw(tmp_path, {"source_type": "hearsay", "value": "PACBIO", "rule_id": "m1"})

        with pytest.raises(ValueError, match="unknown source_type"):
            list(iter_claims(path))

    def test_a_claim_declaring_both_a_value_and_a_status_is_refused(self, tmp_path):
        claim = {
            "source_type": SOURCE_REPOSITORY_METADATA,
            "value": "PACBIO",
            "status": "not_applicable",
            "rule_id": "m1",
        }
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match="exactly one of value/status/state"):
            list(iter_claims(path))

    def test_a_line_carrying_its_own_source_is_refused_not_re_attributed(self, tmp_path):
        """The writer refuses a foreign source; a reader that overwrote one would undo that."""
        claim = {
            "source_type": SOURCE_REPOSITORY_METADATA,
            "value": "PACBIO",
            "rule_id": "m1",
            "source": {"name": "SOMEONE ELSE", "table": "other"},
        }
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match="carries its own source"):
            list(iter_claims(path))

    def test_an_unknown_key_on_a_claim_is_refused(self, tmp_path):
        claim = {"source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "rule_id": "m1", "rank": 9}
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match="not a valid claim"):
            list(iter_claims(path))

    @pytest.mark.parametrize("tier", ["1", True, 1.5])
    def test_a_tier_that_is_not_an_integer_is_refused(self, tmp_path, tier):
        """A string tier passes the None check, then fails inside the tier comparison.

        `evaluate_claims` would raise while ordering this claim against an unrelated
        one, so the line that caused it is never named. `bool` is an `int` in Python
        and is not a tier.
        """
        claim = {"source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "rule_id": "m1", "tier": tier}
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match="does not"):
            list(iter_claims(path))

    def test_a_line_whose_column_is_not_a_string_is_refused(self, tmp_path):
        """The per-line `column` is a source member and is checked like the rest."""
        claim = {"source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "rule_id": "m1", "column": 7}
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match="source column"):
            list(iter_claims(path))

    @pytest.mark.parametrize(
        "member,bad",
        [("value", 7), ("raw_value", []), ("reason", 3), ("rule_id", 9)],
    )
    def test_a_member_of_the_wrong_type_is_refused(self, tmp_path, member, bad):
        """The schema's Evidence says strings and a boolean; nothing else pinned these.

        A numeric `value` would otherwise reach resolution and be written to output as
        a classification.
        """
        claim = {"source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "rule_id": "m1"}
        claim[member] = bad
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match=r"not a string"):
            list(iter_claims(path))

    def test_an_unknown_member_beside_the_claim_is_refused(self, tmp_path):
        """`make_claim` refuses an unknown key inside the claim; the line must match.

        A reader that dropped one silently would normalize a malformed file into an
        apparently valid claim.
        """
        path = tmp_path / "c.ndjson"
        line = {
            "field": "platform",
            "target_key_value": "HG002.bam",
            "claim": {"source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "rule_id": "m1"},
            "rank": 9,
        }
        path.write_text(json.dumps({ENVELOPE_KEY: claim_file_envelope().to_dict()}) + "\n" + json.dumps(line) + "\n")

        with pytest.raises(ValueError, match=r"unknown member\(s\) \['rank'\]"):
            list(iter_claims(path))

    def test_an_unhashable_line_member_is_refused_by_name_not_by_traceback(self, tmp_path):
        """`field: []` raises TypeError from the frozenset lookup unless type is checked first.

        That escapes as a codec-style traceback rather than the ValueError naming the
        file and the line, which is the one thing this module promises about a
        malformed file.
        """
        path = tmp_path / "c.ndjson"
        line = {"field": [], "target_key_value": "HG002.bam", "claim": {}}
        path.write_text(json.dumps({ENVELOPE_KEY: claim_file_envelope().to_dict()}) + "\n" + json.dumps(line) + "\n")

        with pytest.raises(ValueError, match=r"c\.ndjson line 2: unknown dimension"):
            list(iter_claims(path))


class TestDiscovery:
    """What a run finds under the claims root."""

    def test_a_missing_root_is_no_claim_files_not_an_error(self, tmp_path):
        assert discover(tmp_path / "claims") == []

    def test_claim_files_are_found_per_source_and_ordered(self, tmp_path):
        for name in ("hprc/catalog.ndjson", "anvil/manifest.ndjson", "hprc/notes.json"):
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")

        assert [p.relative_to(tmp_path).as_posix() for p in discover(tmp_path)] == [
            "anvil/manifest.ndjson",
            "hprc/catalog.ndjson",
        ]


class TestTheRunReport:
    """What a run says about the claim files it consumed.

    It reports and does not judge. A run cannot tell offline whether a claim file has
    outlived what it describes — the sources share no version to compare, and AnVIL
    deletes a superseded catalog rather than keeping it to be matched against — so
    every file is named with its provenance and age, and nothing is refused.
    """

    def test_no_claim_files_is_said_rather_than_passed_over(self, tmp_path, capsys):
        assert report_claim_files(tmp_path / "claims") == []
        assert "none under" in capsys.readouterr().out

    def test_provenance_and_age_are_reported_per_file(self, tmp_path, capsys):
        write_claim_file(tmp_path / "hprc" / "catalog.ndjson", claim_file_envelope(), [_entry()])

        statuses = report_claim_files(tmp_path, now=FETCHED_AT + timedelta(days=8))
        out = capsys.readouterr().out
        assert [s.error for s in statuses] == [None]
        assert "hprc/catalog.ndjson" in out.replace("\\", "/")
        # Both sides of the join, in the order a reader needs them: what it came from,
        # then what it is about, each with the key that pairs them.
        assert "HPRC Data Explorer/R2/sequencing-data[filename]" in out
        assert "anvil/AnVIL_HPRC_R2/anvil15[file_name]" in out
        assert "version 2026-09-01" in out
        assert "8 days ago" in out

    def test_a_target_generation_is_reported_as_provenance(self, tmp_path, capsys):
        """The generation a file was built against is said, not checked."""
        target = ClaimTarget(system="anvil", dataset="AnVIL_HPRC_R2", version="anvil14")
        write_claim_file(tmp_path / "anvil" / "manifest.ndjson", claim_file_envelope(target=target), [])

        (status,) = report_claim_files(tmp_path)
        out = capsys.readouterr().out
        assert status.error is None
        assert "anvil14" in out
        assert "UNREADABLE" not in out

    def test_an_unreadable_file_is_named_rather_than_hiding_the_rest(self, tmp_path, capsys):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "broken.ndjson").write_text("{not json\n")
        write_claim_file(tmp_path / "b" / "good.ndjson", claim_file_envelope(), [_entry()])

        broken, good = report_claim_files(tmp_path)
        assert broken.envelope is None and broken.error is not None
        assert good.error is None
        assert "envelope could not be read" in capsys.readouterr().out

    def test_an_aware_fetch_time_is_aged_without_a_type_error(self, tmp_path, capsys):
        """Ages are taken in the envelope's own timezone, so either kind subtracts."""
        aware = datetime(2026, 9, 1, 9, 14, 3, tzinfo=timezone.utc)
        write_claim_file(tmp_path / "c.ndjson", claim_file_envelope(fetched_at=aware), [])

        report_claim_files(tmp_path)
        out = capsys.readouterr().out
        assert "ago" in out or "today" in out

    def test_a_naive_now_ages_an_aware_fetch_time(self, tmp_path, capsys):
        """A caller's clock and an envelope's need not agree on awareness.

        That disagreement used to raise inside `_describe`, which would have taken
        every other file's line down with it — the opposite of what the report is for.
        """
        aware = datetime(2026, 9, 1, 9, 14, 3, tzinfo=timezone.utc)
        write_claim_file(tmp_path / "c.ndjson", claim_file_envelope(fetched_at=aware), [])

        report_claim_files(tmp_path, now=datetime(2026, 9, 9, 9, 14, 3))
        assert "days ago" in capsys.readouterr().out

    def test_a_fetch_time_in_the_future_is_said_not_clamped(self, tmp_path, capsys):
        write_claim_file(tmp_path / "c.ndjson", claim_file_envelope(), [])

        report_claim_files(tmp_path, now=FETCHED_AT - timedelta(days=2))
        assert "dated in the future" in capsys.readouterr().out


class TestAClaimFileIsWrittenBySomeoneElse:
    """The curator table (#397) is another claim file, not a special case."""

    def test_a_wrangler_table_with_no_url_round_trips(self, tmp_path):
        # A curator table has no public address and no dataset level, and keys its
        # overrides by the strongest key the target has rather than by a name.
        curator = ClaimFileSource(repository="meta-disco curator table", table="overrides")
        entry = ClaimEntry(
            field="data_type",
            target_key_value="a" * 32,
            claim=make_claim(
                # A curator's reason is not derivable from the mapping, so it is
                # written — the one case where an imported claim carries prose (#401).
                reason="curator override: alignments_v2.location is not an authority on data_type",
                source_type=SOURCE_WRANGLER_ANNOTATION,
                source=curator.as_claim_source("data_type"),
                rule_id="curator_override_rev3",
                value="variant_calls",
            ),
        )
        path = tmp_path / "curator.ndjson"
        write_claim_file(
            path,
            ClaimFileEnvelope(
                source=curator,
                source_version="rev-3",
                source_key="file_md5sum",
                target=ClaimTarget(system="anvil"),
                target_key=JOIN_KEY_FILE_MD5SUM,
                fetched_at=FETCHED_AT,
            ),
            [entry],
        )

        envelope = read_envelope(path)
        assert envelope.source.url is None and envelope.source.dataset is None
        # No dataset scope. An md5 is not unique corpus-wide (2,026 are registered
        # in more than one dataset), but those rows are the same bytes catalogued
        # twice, so a curator's claim about the content is true of all of them. What
        # a join should do with that is #402's — see `ClaimTarget.dataset`.
        assert envelope.target.dataset is None
        assert list(iter_claims(path)) == [entry]


def test_the_claims_root_the_run_uses_is_under_data():
    """The default root is `data/claims`, one directory per source under it."""
    assert DEFAULT_CLAIMS_ROOT.parts[-2:] == ("data", "claims")
    assert DEFAULT_CLAIMS_ROOT.parent == Path(__file__).resolve().parents[1] / "data"
