"""The claim file: envelope, provenance and NDJSON (#401).

A claim file is how an importer that ran yesterday, against a network catalog, hands
claims to a run happening today. Three things have to hold for that to be safe, and
they are what these tests cover.

*It must say where it came from.* Provenance is per file, recorded once, and read
back whole — including the ``ClaimSource`` each claim's own record carries, which the
writer factors into the envelope and the reader puts back.

*Its age must be visible.* A run says what it consumed and how old each one was, and
imports from all of them. It does not adjudicate currency: nothing offline can, since
the sources share no version to compare and AnVIL deletes a superseded catalog rather
than keeping it to be matched against. That question belongs to the importer's
re-fetch decision and to the catalog an enhancement is offered back to.

*It must stream.* Millions of claims cannot go through a whole-file parse (#374), so
the reader yields claims as it reads them and a malformed line fails naming the file
and the line rather than taking the file down.

Unit-level by intent: no importer exists yet (#369, #394) and the join to our files
is #400b, so the producers here are hand-built claims from the ``AnVIL_HPRC_R2``
spike's two external sources.
"""

import json
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
    ClaimFileEnvelope,
    ClaimSource,
)
from meta_disco.rule_engine import make_claim

HPRC_CATALOG = ClaimSource(name="HPRC Data Explorer", url="https://data.humanpangenome.org/", table="sequencing-data")
ANVIL_MANIFEST = ClaimSource(name="AnVIL", url="https://service.explore.anvilproject.org/", table="alignments_v2")
FETCHED_AT = datetime(2026, 9, 1, 9, 14, 3)
# A fetch time as an envelope on disk carries it. Used wherever a case needs a
# *valid* fetched_at so that it isolates the member actually under test — a bare
# date is refused in its own right, for having no time of day.
ISO_NOW = FETCHED_AT.isoformat()


def _envelope(**overrides) -> ClaimFileEnvelope:
    """An HPRC catalog envelope — a source with no relationship to our catalog."""
    return ClaimFileEnvelope(
        **{
            "source": HPRC_CATALOG,
            "fetched_at": FETCHED_AT,
            "source_version": "2026-09-01",
            **overrides,
        }
    )


def _entry(column="platform", raw="Revio", value="PACBIO", name="HG002.bam", source=HPRC_CATALOG) -> ClaimEntry:
    """One mapped platform claim, keyed by the file name the catalog publishes."""
    return ClaimEntry(
        field="platform",
        join_key=JOIN_KEY_FILE_NAME,
        key_value=name,
        claim=make_claim(
            reason=f"{source.table}.{column} = {raw}",
            source_type=SOURCE_REPOSITORY_METADATA,
            source=ClaimSource(name=source.name, url=source.url, table=source.table, column=column),
            raw_value=raw,
            value=value,
            tier=1,
        ),
    )


class TestRoundTrip:
    """A claim file says where it came from, and gives back the claims put into it."""

    def test_envelope_carries_source_table_fetch_date_and_version(self, tmp_path):
        path = tmp_path / "hprc" / "sequencing_data.ndjson"
        write_claim_file(path, _envelope(), [_entry()])

        envelope = read_envelope(path)
        assert envelope.source == HPRC_CATALOG
        assert envelope.source.url == "https://data.humanpangenome.org/"
        assert envelope.fetched_at == FETCHED_AT
        assert envelope.source_version == "2026-09-01"
        assert envelope.corpus_catalog is None

    def test_a_claim_comes_back_whole(self, tmp_path):
        """The claim read back is the claim written, source and all."""
        path = tmp_path / "claims.ndjson"
        entry = _entry()
        write_claim_file(path, _envelope(), [entry])

        assert list(iter_claims(path)) == [entry]

    def test_each_claim_gets_its_own_rehydrated_source(self, tmp_path):
        """The reader factors the source in per claim, so claims cannot alias one dict."""
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, _envelope(), [_entry(name="a.bam"), _entry(name="b.bam")])

        first, second = (entry.claim["source"] for entry in iter_claims(path))
        assert first == second
        first["table"] = "edited"
        assert second["table"] == "sequencing-data"

    def test_the_raw_value_survives_beside_the_mapped_one(self, tmp_path):
        """The mapping is the reviewable decision, so `Revio` must outlive the file."""
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, _envelope(), [_entry(raw="Revio", value="PACBIO")])

        (claim,) = [entry.claim for entry in iter_claims(path)]
        assert (claim["raw_value"], claim["value"]) == ("Revio", "PACBIO")

    def test_a_state_claim_survives_the_round_trip(self, tmp_path):
        """`Hi-C` mapped deliberately to nothing is the review queue — it must be kept."""
        path = tmp_path / "claims.ndjson"
        entry = ClaimEntry(
            field="assay_type",
            join_key=JOIN_KEY_FILE_MD5SUM,
            key_value="d41d8cd98f00b204e9800998ecf8427e",
            claim=make_claim(
                reason="sequencing-data.assayType = Hi-C",
                source_type=SOURCE_REPOSITORY_METADATA,
                source=ClaimSource(
                    name=HPRC_CATALOG.name, url=HPRC_CATALOG.url, table="sequencing-data", column="assayType"
                ),
                raw_value="Hi-C",
                state=NO_VOCABULARY_TERM,
            ),
        )
        write_claim_file(path, _envelope(), [entry])

        assert list(iter_claims(path)) == [entry]

    def test_the_count_written_is_returned(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        assert write_claim_file(path, _envelope(), [_entry(name=f"HG{n:04d}.bam") for n in range(7)]) == 7


class TestTheEnvelopeIsFactoredOut:
    """Name, url and table are recorded once; only `column` stays on a claim."""

    def test_a_written_claim_repeats_no_envelope_field(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, _envelope(), [_entry(column="platform")])

        claim = json.loads(path.read_text().splitlines()[1])["claim"]
        assert "source" not in claim
        assert claim["column"] == "platform"

    def test_line_one_is_the_envelope_and_is_labelled_as_one(self, tmp_path):
        """An envelope is told from a claim by its shape, not by being first."""
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, _envelope(), [_entry()])

        assert list(json.loads(path.read_text().splitlines()[0])) == [ENVELOPE_KEY]

    def test_a_claim_from_another_source_is_refused_at_write(self, tmp_path):
        """A file's claims must have come from the source its envelope names."""
        path = tmp_path / "claims.ndjson"
        with pytest.raises(ValueError, match="envelope names"):
            write_claim_file(path, _envelope(), [_entry(source=ANVIL_MANIFEST)])

    def test_nothing_is_left_behind_when_a_claim_is_refused(self, tmp_path):
        """The temp-file-and-rename write leaves the previous file, or none at all."""
        path = tmp_path / "claims.ndjson"
        with pytest.raises(ValueError):
            write_claim_file(path, _envelope(), [_entry(source=ANVIL_MANIFEST)])

        assert not path.exists()
        assert list(tmp_path.iterdir()) == []

    def test_the_caller_s_claim_is_not_mutated(self, tmp_path):
        """Factoring the source out is the file's business, not the importer's."""
        entry = _entry()
        before = json.loads(json.dumps(entry.claim))
        write_claim_file(tmp_path / "claims.ndjson", _envelope(), [entry])

        assert entry.claim == before


class TestMalformedFiles:
    """A file that will not read fails naming itself and the line."""

    def test_a_malformed_line_names_the_file_and_the_line(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, _envelope(), [_entry(), _entry()])
        path.write_text(path.read_text() + "{not json\n")

        with pytest.raises(ValueError, match=r"claims\.ndjson line 4: not a claim"):
            list(iter_claims(path))

    def test_claims_before_a_malformed_line_are_yielded_first(self, tmp_path):
        """Proof the reader streams: it cannot have parsed line 5 before yielding line 2."""
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, _envelope(), [_entry(name=f"HG{n}.bam") for n in range(3)])
        path.write_text(path.read_text() + "{not json\n")

        read = []
        with pytest.raises(ValueError):
            for entry in iter_claims(path):
                read.append(entry.key_value)
        assert read == ["HG0.bam", "HG1.bam", "HG2.bam"]

    def test_a_blank_line_carries_no_claim(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        write_claim_file(path, _envelope(), [_entry()])
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
            ({"source": {"url": "u"}, "fetched_at": ISO_NOW, "source_version": "1"}, "source name"),
            ({"source": {"name": "HPRC"}, "source_version": "1"}, "fetched_at"),
            ({"source": {"name": "HPRC"}, "fetched_at": "yesterday", "source_version": "1"}, "not an ISO 8601"),
            ({"source": {"name": "HPRC"}, "fetched_at": "2026-09-01", "source_version": "1"}, "no time of day"),
            ({"source": {"name": "HPRC"}, "fetched_at": ISO_NOW}, "source_version"),
            ({"source": {"name": ""}, "fetched_at": ISO_NOW, "source_version": "1"}, "source name"),
            ({"source": {"name": None}, "fetched_at": ISO_NOW, "source_version": "1"}, "source name"),
            ({"source": {"name": "HPRC"}, "fetched_at": ISO_NOW, "source_version": ""}, "source_version"),
            (
                {"source": {"name": "HPRC", "table": 7}, "fetched_at": ISO_NOW, "source_version": "1"},
                "source table",
            ),
        ],
    )
    def test_an_envelope_missing_a_fact_is_refused(self, tmp_path, envelope, expected):
        """Every envelope member is checked on read: the refusal decision rests on them."""
        path = tmp_path / "claims.ndjson"
        path.write_text(json.dumps({ENVELOPE_KEY: envelope}) + "\n")

        with pytest.raises(ValueError, match=expected):
            read_envelope(path)

    def test_a_claim_for_an_unknown_dimension_is_refused_both_ways(self, tmp_path):
        path = tmp_path / "claims.ndjson"
        entry = _entry()
        with pytest.raises(ValueError, match="unknown dimension"):
            write_claim_file(path, _envelope(), [ClaimEntry("data_moddality", entry.join_key, "x", entry.claim)])

        write_claim_file(path, _envelope(), [entry])
        path.write_text(path.read_text().replace('"platform"', '"data_moddality"', 1))
        with pytest.raises(ValueError, match="line 2: unknown dimension"):
            list(iter_claims(path))

    def test_a_claim_with_an_unknown_join_key_is_refused(self, tmp_path):
        entry = _entry()
        with pytest.raises(ValueError, match="unknown join_key"):
            write_claim_file(
                tmp_path / "c.ndjson", _envelope(), [ClaimEntry(entry.field, "sample_id", "x", entry.claim)]
            )


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
            _envelope(source_version=version)

    def test_an_envelope_with_a_nameless_source_is_refused_when_it_is_built(self):
        with pytest.raises(ValueError, match="source name"):
            _envelope(source=ClaimSource(name=""))

    def test_an_envelope_with_a_non_datetime_fetch_time_is_refused_when_it_is_built(self):
        with pytest.raises(ValueError, match="fetched_at"):
            _envelope(fetched_at="2026-09-01")

    def test_an_envelope_naming_a_column_is_refused_when_it_is_built(self):
        """A column belongs to a claim, not to the file.

        `to_dict` would otherwise write it on line 1, where both sides strip it
        before use — a member of the serialized envelope that nothing reads and that
        can disagree with every claim in the file.
        """
        with pytest.raises(ValueError, match="belongs to a claim"):
            _envelope(source=ClaimSource(name="HPRC", table="t", column="platform"))

    def test_an_envelope_whose_source_has_a_non_string_member_is_refused_when_it_is_built(self):
        """Checking only `name` left the parity half-kept: `table=7` wrote, then failed on read.

        The annotation says `str | None`, so the ignore is the point of the test: type
        hints do not run, and an importer mapping a source's own JSON can hand over
        whatever that JSON held.
        """
        with pytest.raises(ValueError, match="source table"):
            _envelope(source=ClaimSource(name="HPRC", table=7))  # type: ignore[arg-type]

    def test_a_hand_built_claim_the_reader_would_refuse_is_refused_at_write(self, tmp_path):
        """An importer can build a ClaimEntry by hand; the writer holds it to make_claim."""
        entry = ClaimEntry(
            field="platform",
            join_key=JOIN_KEY_FILE_NAME,
            key_value="HG002.bam",
            claim={"reason": "r", "source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "source": {}},
        )
        entry.claim["source"] = HPRC_CATALOG.to_dict()

        with pytest.raises(ValueError, match="must carry a tier"):
            write_claim_file(tmp_path / "c.ndjson", _envelope(), [entry])

    def test_a_file_the_run_would_never_find_is_refused_at_write(self, tmp_path):
        """`discover` matches *.ndjson, so any other suffix is a silent no-op."""
        with pytest.raises(ValueError, match="must be named"):
            write_claim_file(tmp_path / "hprc" / "catalog.json", _envelope(), [_entry()])

    def test_a_utc_z_suffix_reads_back_on_every_supported_interpreter(self, tmp_path):
        """`fromisoformat` rejects `Z` on 3.10 (the floor and what CI runs), takes it on 3.11+.

        Our writer emits `+00:00`, but the importers in #369/#394 read web APIs that
        emit `Z` almost universally — a claim file must not parse on a dev box and
        fail on CI.
        """
        path = tmp_path / "c.ndjson"
        block = {"source": {"name": "HPRC"}, "fetched_at": "2026-09-01T09:14:03Z", "source_version": "1"}
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
        line = {"field": "platform", "join_key": JOIN_KEY_FILE_NAME, "key_value": "HG002.bam", "claim": claim}
        path.write_text(
            json.dumps({ENVELOPE_KEY: _envelope().to_dict()}) + "\n" + json.dumps(line) + "\n",
        )
        return path

    def test_a_claim_with_no_tier_is_refused(self, tmp_path):
        """It would otherwise reach resolution and take the tier-0 default of #150/#151."""
        path = self._write_raw(tmp_path, {"reason": "r", "source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO"})

        with pytest.raises(ValueError, match="must carry a tier"):
            list(iter_claims(path))

    def test_a_claim_with_an_unknown_source_type_is_refused(self, tmp_path):
        path = self._write_raw(tmp_path, {"reason": "r", "source_type": "hearsay", "value": "PACBIO", "tier": 1})

        with pytest.raises(ValueError, match="unknown source_type"):
            list(iter_claims(path))

    def test_a_claim_declaring_both_a_value_and_a_status_is_refused(self, tmp_path):
        claim = {
            "reason": "r",
            "source_type": SOURCE_REPOSITORY_METADATA,
            "value": "PACBIO",
            "status": "not_applicable",
            "tier": 1,
        }
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match="exactly one of value/status/state"):
            list(iter_claims(path))

    def test_a_line_carrying_its_own_source_is_refused_not_re_attributed(self, tmp_path):
        """The writer refuses a foreign source; a reader that overwrote one would undo that."""
        claim = {
            "reason": "r",
            "source_type": SOURCE_REPOSITORY_METADATA,
            "value": "PACBIO",
            "tier": 1,
            "source": {"name": "SOMEONE ELSE", "table": "other"},
        }
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match="carries its own source"):
            list(iter_claims(path))

    def test_an_unknown_key_on_a_claim_is_refused(self, tmp_path):
        claim = {"reason": "r", "source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "tier": 1, "rank": 9}
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
        claim = {"reason": "r", "source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "tier": tier}
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match="not an integer"):
            list(iter_claims(path))

    def test_a_line_whose_column_is_not_a_string_is_refused(self, tmp_path):
        """The per-line `column` is a source member and is checked like the rest."""
        claim = {"reason": "r", "source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "tier": 1, "column": 7}
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match="source column"):
            list(iter_claims(path))

    @pytest.mark.parametrize(
        "member,bad",
        [("value", 7), ("raw_value", []), ("reason", 3), ("match_exact", "yes")],
    )
    def test_a_member_of_the_wrong_type_is_refused(self, tmp_path, member, bad):
        """The schema's Evidence says strings and a boolean; nothing else pinned these.

        A numeric `value` would otherwise reach resolution and be written to output as
        a classification.
        """
        claim = {"reason": "r", "source_type": SOURCE_REPOSITORY_METADATA, "value": "PACBIO", "tier": 1}
        if member == "match_exact":
            claim["join_key"] = JOIN_KEY_FILE_NAME
        claim[member] = bad
        path = self._write_raw(tmp_path, claim)

        with pytest.raises(ValueError, match=r"not a string|not a boolean"):
            list(iter_claims(path))

    @pytest.mark.parametrize("member", ["field", "join_key"])
    def test_an_unhashable_line_member_is_refused_by_name_not_by_traceback(self, tmp_path, member):
        """`field: []` used to raise TypeError from the frozenset lookup, uncaught."""
        path = tmp_path / "c.ndjson"
        line = {"field": "platform", "join_key": JOIN_KEY_FILE_NAME, "key_value": "HG002.bam", "claim": {}}
        line[member] = []
        path.write_text(json.dumps({ENVELOPE_KEY: _envelope().to_dict()}) + "\n" + json.dumps(line) + "\n")

        with pytest.raises(ValueError, match=r"c\.ndjson line 2"):
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
        write_claim_file(tmp_path / "hprc" / "catalog.ndjson", _envelope(), [_entry()])

        statuses = report_claim_files(tmp_path, now=FETCHED_AT + timedelta(days=8))
        out = capsys.readouterr().out
        assert [s.error for s in statuses] == [None]
        assert "hprc/catalog.ndjson" in out.replace("\\", "/")
        assert "HPRC Data Explorer/sequencing-data" in out
        assert "version 2026-09-01" in out
        assert "8 days ago" in out

    def test_a_declared_catalog_is_reported_as_provenance(self, tmp_path, capsys):
        """The catalog a file was built for is said, not checked."""
        write_claim_file(tmp_path / "anvil" / "manifest.ndjson", _envelope(corpus_catalog="anvil14"), [])

        (status,) = report_claim_files(tmp_path)
        out = capsys.readouterr().out
        assert status.error is None
        assert "for catalog anvil14" in out
        assert "UNREADABLE" not in out

    def test_a_source_with_no_catalog_reports_no_catalog(self, tmp_path, capsys):
        """HPRC/ENA/IGSR claims are about files, not about a snapshot of ours."""
        write_claim_file(tmp_path / "hprc" / "catalog.ndjson", _envelope(), [_entry()])

        report_claim_files(tmp_path)
        assert "for catalog" not in capsys.readouterr().out

    def test_an_unreadable_file_is_named_rather_than_hiding_the_rest(self, tmp_path, capsys):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "broken.ndjson").write_text("{not json\n")
        write_claim_file(tmp_path / "b" / "good.ndjson", _envelope(), [_entry()])

        broken, good = report_claim_files(tmp_path)
        assert broken.envelope is None and broken.error is not None
        assert good.error is None
        assert "envelope could not be read" in capsys.readouterr().out

    def test_an_aware_fetch_time_is_aged_without_a_type_error(self, tmp_path, capsys):
        """Ages are taken in the envelope's own timezone, so either kind subtracts."""
        aware = datetime(2026, 9, 1, 9, 14, 3, tzinfo=timezone.utc)
        write_claim_file(tmp_path / "c.ndjson", _envelope(fetched_at=aware), [])

        report_claim_files(tmp_path)
        out = capsys.readouterr().out
        assert "ago" in out or "today" in out

    def test_a_naive_now_ages_an_aware_fetch_time(self, tmp_path, capsys):
        """A caller's clock and an envelope's need not agree on awareness.

        That disagreement used to raise inside `_describe`, which would have taken
        every other file's line down with it — the opposite of what the report is for.
        """
        aware = datetime(2026, 9, 1, 9, 14, 3, tzinfo=timezone.utc)
        write_claim_file(tmp_path / "c.ndjson", _envelope(fetched_at=aware), [])

        report_claim_files(tmp_path, now=datetime(2026, 9, 9, 9, 14, 3))
        assert "days ago" in capsys.readouterr().out

    def test_a_fetch_time_in_the_future_is_said_not_clamped(self, tmp_path, capsys):
        write_claim_file(tmp_path / "c.ndjson", _envelope(), [])

        report_claim_files(tmp_path, now=FETCHED_AT - timedelta(days=2))
        assert "dated in the future" in capsys.readouterr().out


class TestAClaimFileIsWrittenBySomeoneElse:
    """The curator table (#397) is another claim file, not a special case."""

    def test_a_wrangler_table_with_no_url_round_trips(self, tmp_path):
        curator = ClaimSource(name="meta-disco curator table", table="overrides")
        entry = ClaimEntry(
            field="data_type",
            join_key=JOIN_KEY_FILE_NAME,
            key_value="HG002.wave.vcf.gz",
            claim=make_claim(
                reason="curator override: alignments_v2.location is not an authority on data_type",
                source_type=SOURCE_WRANGLER_ANNOTATION,
                source=ClaimSource(name=curator.name, table="overrides", column="data_type"),
                value="variant_calls",
                tier=1,
            ),
        )
        path = tmp_path / "curator.ndjson"
        write_claim_file(
            path,
            ClaimFileEnvelope(source=curator, fetched_at=FETCHED_AT, source_version="rev-3"),
            [entry],
        )

        assert read_envelope(path).source.url is None
        assert list(iter_claims(path)) == [entry]


def test_the_claims_root_the_run_uses_is_under_data():
    """The default root is `data/claims`, one directory per source under it."""
    assert DEFAULT_CLAIMS_ROOT.parts[-2:] == ("data", "claims")
    assert DEFAULT_CLAIMS_ROOT.parent == Path(__file__).resolve().parents[1] / "data"
