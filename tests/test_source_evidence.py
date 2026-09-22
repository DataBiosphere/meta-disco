"""The evidence file: envelope, provenance and NDJSON (#401, #421).

An evidence file is how an importer that ran yesterday, against a network catalog,
hands what a source said to a run happening today. It hands over **observations, not
answers**: a row carries the source's ``raw_value`` and no mapped value, because only
the rule engine maps meaning (contract 1.1-1.5). Three things have to hold for that to
be safe, and they are what these tests cover.

*It must say where it came from.* Provenance is per file, recorded once, and read
back whole — including the ``ClaimSource`` each row carries, which the writer factors
into the envelope and the reader puts back.

*Its age must be visible.* A run says what it found and how old each one was. It
does not adjudicate currency: nothing offline can, since the sources share no version
to compare and AnVIL deletes a superseded catalog rather than keeping it to be matched
against. That question belongs to the importer's re-fetch decision and to the catalog
an enhancement is offered back to. Note what these tests therefore do *not* cover: a
run reports its evidence files and imports nothing from them — ``iter_evidence`` has no
caller in the run — so nothing here asserts that a row reaches classification, and
nothing does until the identity join lands (#402).

*It must stream.* Millions of rows cannot go through a whole-file parse (#374), so
the reader yields rows as it reads them and a malformed line fails naming the file
and the line rather than taking the file down.

Unit-level by intent: no importer exists yet (#369, #394) and the join to our files
is #402, so the producers here are hand-built rows from the ``AnVIL_HPRC_R2``
spike's two external sources.
"""

import ast
import json
import threading
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from meta_disco import models, source_evidence
from meta_disco.azul_manifest import API_URL, REPOSITORY, VERBATIM_FILE
from meta_disco.models import (
    CLASSIFICATION_FIELDS,
    JOIN_KEY_DRS_URI,
    JOIN_KEY_FILE_MD5SUM,
    JOIN_KEY_FILE_NAME,
    SOURCE_CONTENT_READ,
    SOURCE_EXTERNAL_GROUND_TRUTH,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_METADATA,
    SOURCE_WRANGLER_ANNOTATION,
    ClaimSource,
)
from meta_disco.pipeline import PUBLISHED_TABLES
from meta_disco.schema_vocab import default_schema_path
from meta_disco.source_evidence import (
    _MAX_ENVELOPE_BYTES,
    DEFAULT_SOURCE_EVIDENCE_ROOT,
    ENVELOPE_KEY,
    EvidenceEntry,
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    claim_source_for,
    discover,
    generation_dir,
    is_generation,
    iter_evidence,
    new_generation,
    read_envelope,
    report_evidence_files,
    require_one_published_source,
    write_evidence_file,
)

HPRC_CATALOG = EvidenceFileSource(
    repository="HPRC Data Explorer",
    dataset="R2",
    table="sequencing-data",
    url="https://data.humanpangenome.org/",
)
ANVIL_MANIFEST = EvidenceFileSource(
    repository="AnVIL",
    dataset="AnVIL_HPRC_R2",
    table="alignments_v2",
    url="https://service.explore.anvilproject.org/",
)
ANVIL_TARGET = EvidenceTarget(system="anvil", dataset="AnVIL_HPRC_R2", version="anvil15")
FETCHED_AT = datetime(2026, 9, 1, 9, 14, 3)
# A fetch time as an envelope carries it, on disk and on the model alike: an ISO 8601
# string, as the schema declares the slot. Used wherever a case needs a *valid*
# fetched_at so that it isolates the member actually under test — a bare date is
# refused in its own right, for having no time of day.
ISO_NOW = FETCHED_AT.isoformat()


def evidence_file_envelope(**overrides) -> EvidenceFileEnvelope:
    """An HPRC catalog envelope: filenames the catalog publishes, matched against
    AnVIL's ``file_name`` within the dataset that makes that key usable.

    Overrides go through the constructor rather than a copy, so a case overriding one
    member with a bad value is refused the way an importer building one would be.
    """
    # Typed `Any` so the merged dict splats past the generated model's enum-typed
    # members; without it pyright infers the union of the values and refuses every one.
    members: dict[str, Any] = {
        "source": HPRC_CATALOG,
        "source_type": SOURCE_REPOSITORY_METADATA,
        "source_version": "2026-09-01",
        "source_key": "filename",
        "target": ANVIL_TARGET,
        "target_key": JOIN_KEY_FILE_NAME,
        "fetched_at": ISO_NOW,
    }
    return EvidenceFileEnvelope(**{**members, **overrides})


def envelope_block(**overrides) -> dict:
    """The envelope as line 1 carries it — the writer's serialization, stated once.

    For the cases that write a file by hand to put a malformed line or member in
    front of the reader.
    """
    return evidence_file_envelope(**overrides).model_dump(exclude_none=True)


def evidence_lines(*lines: object) -> str:
    """A hand-written evidence file's text: the envelope on line 1, then ``lines``."""
    return "".join(json.dumps(line) + "\n" for line in ({ENVELOPE_KEY: envelope_block()}, *lines))


def published_envelope(
    dataset: str = "AnVIL_IGVF_Mouse_R1",
    table: str = VERBATIM_FILE,
    version: str = "anvil15",
    repository: str = REPOSITORY,
    source_type: str = SOURCE_PUBLISHED_VALUE,
) -> EvidenceFileEnvelope:
    """The envelope the published map writes (#497): AnVIL's own ``anvil_file`` table,
    labelled ``published_value``, keyed by DRS URI on both sides and versioned by the
    catalog, about that same dataset's files."""
    return evidence_file_envelope(
        source=EvidenceFileSource(repository=repository, dataset=dataset, table=table, url=API_URL),
        source_type=source_type,
        source_version=version,
        source_key=JOIN_KEY_DRS_URI,
        target=EvidenceTarget(system=REPOSITORY, dataset=dataset, version=version),
        target_key=JOIN_KEY_DRS_URI,
    )


def _entry(column="instrumentModel", raw="Revio", name="HG002.bam", source=HPRC_CATALOG) -> EvidenceEntry:
    """One platform observation, keyed by the file name the catalog publishes.

    `Revio` is what the catalog writes and is carried verbatim; nothing here turns it
    into `PACBIO`, which is a rule's job at reconcile (#414).
    """
    return EvidenceEntry(
        field="platform",
        target_key_value=name,
        raw_value=raw,
        source=claim_source_for(source, column),
    )


class TestRoundTrip:
    """An evidence file says where it came from, and gives back the rows put into it."""

    def test_envelope_carries_source_table_fetch_date_and_version(self, tmp_path):
        path = tmp_path / "hprc" / "sequencing_data.ndjson"
        write_evidence_file(path, evidence_file_envelope(), [_entry()])

        envelope = read_envelope(path)
        assert envelope.source == HPRC_CATALOG
        assert envelope.source.dataset == "R2"
        assert envelope.source.url == "https://data.humanpangenome.org/"
        assert envelope.fetched_at == ISO_NOW
        assert envelope.source_version == "2026-09-01"
        assert envelope.source_type == SOURCE_REPOSITORY_METADATA
        # Both sides of the join, and which key pairs with which.
        assert (envelope.source_key, envelope.target_key) == ("filename", JOIN_KEY_FILE_NAME)
        assert envelope.target == ANVIL_TARGET

    def test_a_row_comes_back_whole(self, tmp_path):
        """The row read back is the row written, source and all."""
        path = tmp_path / "evidence.ndjson"
        entry = _entry()
        write_evidence_file(path, evidence_file_envelope(), [entry])

        assert list(iter_evidence(path)) == [entry]

    def test_a_rehydrated_row_can_interpret_its_own_column(self, tmp_path):
        """The dataset crosses onto the row, not only onto the envelope.

        The same column name means different things in different datasets, so a row
        naming only its column could not be read without going back to the file it
        arrived in — which nothing reading the output evidence array can do (#401).
        """
        path = tmp_path / "evidence.ndjson"
        write_evidence_file(path, evidence_file_envelope(), [_entry(column="instrumentModel")])

        (source,) = [entry.source for entry in iter_evidence(path)]
        assert (source.name, source.dataset, source.table, source.column) == (
            "HPRC Data Explorer",
            "R2",
            "sequencing-data",
            "instrumentModel",
        )

    def test_rows_from_one_column_share_one_frozen_source(self, tmp_path):
        """The reader keeps one `ClaimSource` per column for the whole file.

        Rebuilding it per line rebuilt and re-validated the same object a few million
        times. Sharing one instance is safe because the record is frozen — a consumer
        cannot edit one row's provenance and reach another's — which is why the
        shared object is the record and not a mutable dict.
        """
        path = tmp_path / "evidence.ndjson"
        write_evidence_file(path, evidence_file_envelope(), [_entry(name="a.bam"), _entry(name="b.bam")])

        first, second = (entry.source for entry in iter_evidence(path))
        assert first is second
        with pytest.raises(AttributeError):
            # The type checker refuses the assignment, which is the point: the record
            # is frozen, and this pins that the sharing above is therefore safe.
            first.table = "edited"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "raw",
        [
            "Revio",  # differs from our `PACBIO` by more than spelling
            "GENOMIC",  # differs from our `genomic` only by case
            " Revio ",  # a cell the source padded
            "",  # an empty cell: 63 of them in AnVIL_HPRC_R2.library_selection
            # A decision #399 owes, not a file this can refuse. Until #421 the module
            # refused a *mapped* value outside the dimension's vocabulary, which is why
            # an importer had to reach for a `no_vocabulary_term` state to say this; a
            # row says nothing about its raw value, so the question survives intact.
            "Hi-C",
        ],
    )
    def test_the_raw_value_is_what_the_source_wrote(self, tmp_path, raw):
        """Verbatim, byte for byte (contract 1.4).

        Not casefolded, not trimmed, not dropped for being empty, and not refused for
        being a value we have no word for — that last is the review queue's input
        (contract 3.7), not an error. Matching normalizes; the file records.
        """
        path = tmp_path / "evidence.ndjson"
        write_evidence_file(path, evidence_file_envelope(), [_entry(raw=raw)])

        assert [entry.raw_value for entry in iter_evidence(path)] == [raw]

    def test_the_count_written_is_returned(self, tmp_path):
        path = tmp_path / "evidence.ndjson"
        assert (
            write_evidence_file(path, evidence_file_envelope(), [_entry(name=f"HG{n:04d}.bam") for n in range(7)]) == 7
        )

    def test_a_lazy_source_is_streamed_not_gathered(self, tmp_path):
        """An importer hands over a generator and the writer never holds the corpus.

        A refusal part-way through is what makes the difference visible: the fourth
        entry is one the writer will not take, so a writer that consumes as it goes
        has asked for four and a writer that gathered first would have asked for all
        seven. The corpus is millions of rows (#374), so this is the property that
        keeps an importer from having to hold one.
        """
        produced = []

        def entries():
            for n in range(7):
                produced.append(n)
                yield _entry(name=f"HG{n:04d}.bam", source=ANVIL_MANIFEST if n == 3 else HPRC_CATALOG)

        with pytest.raises(ValueError, match="row 4"):
            write_evidence_file(tmp_path / "evidence.ndjson", evidence_file_envelope(), entries())

        assert produced == [0, 1, 2, 3]


class TestTheEnvelopeIsFactoredOut:
    """Name, url and table are recorded once; only `column` stays on a row."""

    def test_a_written_row_repeats_no_envelope_field(self, tmp_path):
        path = tmp_path / "evidence.ndjson"
        write_evidence_file(path, evidence_file_envelope(), [_entry(column="instrumentModel")])

        line = json.loads(path.read_text().splitlines()[1])
        assert sorted(line) == ["column", "field", "raw_value", "target_key_value"]
        assert line["column"] == "instrumentModel"

    def test_line_one_is_the_envelope_and_is_labelled_as_one(self, tmp_path):
        """An envelope is told from a row by its shape, not by being first."""
        path = tmp_path / "evidence.ndjson"
        write_evidence_file(path, evidence_file_envelope(), [_entry()])

        assert list(json.loads(path.read_text().splitlines()[0])) == [ENVELOPE_KEY]

    def test_a_row_from_another_source_is_refused_at_write(self, tmp_path):
        """A file's rows must have come from the source its envelope names."""
        path = tmp_path / "evidence.ndjson"
        with pytest.raises(ValueError, match="envelope names"):
            write_evidence_file(path, evidence_file_envelope(), [_entry(source=ANVIL_MANIFEST)])

    def test_nothing_is_left_behind_when_a_row_is_refused(self, tmp_path):
        """The temp-file-and-rename write leaves the previous file, or none at all."""
        path = tmp_path / "evidence.ndjson"
        with pytest.raises(ValueError):
            write_evidence_file(path, evidence_file_envelope(), [_entry(source=ANVIL_MANIFEST)])

        assert not path.exists()
        assert list(tmp_path.iterdir()) == []

    def test_two_writers_on_one_path_do_not_share_a_temporary(self, tmp_path):
        """A shared `<name>.tmp` let one writer's rename delete the other's file.

        The loser then returned a row count for rows that are not on disk. They
        race only on the rename now, and the file that survives is whole — but which
        one survives is completion order, not catalog order, which is why the comment
        on `tmp` says two importers must not share a path.
        """
        path = tmp_path / "evidence.ndjson"
        seen = []
        # Two barriers, and both are load-bearing.
        #
        # The first: each writer has opened its temporary and written a row into it by
        # the time it arrives, so neither samples until both are mid-write. Without it
        # the main-thread writer can finish before the other starts (#401 review).
        #
        # The second: arriving together is not sampling together. Released from the
        # first barrier, one writer can run to completion and rename before the other
        # reads the directory — which is what made this test fail intermittently in
        # CI, on a sample that saw the finished `evidence.ndjson` and one `.tmp`
        # instead of two. Holding both here until each has sampled is what makes the
        # assertion below independent of scheduling.
        #
        # Each timeout turns a writer that raises before its barrier into a failure
        # here rather than a hang.
        both_writing = threading.Barrier(2, timeout=10)
        both_sampled = threading.Barrier(2, timeout=10)

        def entries(tag):
            for n in range(3):
                if n == 1:
                    both_writing.wait()
                    seen.append(sorted(p.name for p in tmp_path.iterdir()))
                    both_sampled.wait()
                yield _entry(name=f"{tag}{n}.bam")

        first = threading.Thread(target=write_evidence_file, args=(path, evidence_file_envelope(), entries("a")))
        first.start()
        write_evidence_file(path, evidence_file_envelope(), entries("b"))
        first.join()

        assert [sum(name.endswith(".tmp") for name in sample) for sample in seen] == [2, 2], seen
        assert len(list(iter_evidence(path))) == 3

    def test_a_rename_that_cannot_happen_leaves_no_temporary_behind(self, tmp_path):
        """A rename fails too, and a stray `.tmp` is a whole evidence file nothing reads.

        A directory standing where the file should go is the reachable case: the
        rows are written, every one of them valid, and only the last step fails.
        """
        path = tmp_path / "evidence.ndjson"
        path.mkdir()

        with pytest.raises(OSError):
            write_evidence_file(path, evidence_file_envelope(), [_entry()])

        assert list(tmp_path.iterdir()) == [path]

    def test_something_that_is_not_an_evidence_entry_is_named_not_traced(self, tmp_path):
        """An importer that yields the wrong shape is told which row, as any other."""
        with pytest.raises(ValueError, match="row 1: is a tuple, not an EvidenceEntry"):
            # The type checker refuses this shape, which is the point: the check
            # exists for an importer that is not type-checked.
            write_evidence_file(tmp_path / "evidence.ndjson", evidence_file_envelope(), [("platform", "x", {})])  # type: ignore[list-item]

    def test_the_caller_s_entry_is_not_mutated(self, tmp_path):
        """Factoring the source out is the file's business, not the importer's."""
        entry = _entry()
        before = (entry.field, entry.target_key_value, entry.raw_value, entry.source)
        write_evidence_file(tmp_path / "evidence.ndjson", evidence_file_envelope(), [entry])

        assert (entry.field, entry.target_key_value, entry.raw_value, entry.source) == before


class TestMalformedFiles:
    """A file that will not read fails naming itself and the line."""

    def test_a_malformed_line_names_the_file_and_the_line(self, tmp_path):
        path = tmp_path / "evidence.ndjson"
        write_evidence_file(path, evidence_file_envelope(), [_entry(), _entry()])
        path.write_text(path.read_text() + "{not json\n")

        with pytest.raises(ValueError, match=r"evidence\.ndjson line 4: not an evidence row"):
            list(iter_evidence(path))

    def test_rows_before_a_malformed_line_are_yielded_first(self, tmp_path):
        """Proof the reader streams: it cannot have parsed line 5 before yielding line 2."""
        path = tmp_path / "evidence.ndjson"
        write_evidence_file(path, evidence_file_envelope(), [_entry(name=f"HG{n}.bam") for n in range(3)])
        path.write_text(path.read_text() + "{not json\n")

        read = []
        with pytest.raises(ValueError):
            for entry in iter_evidence(path):
                read.append(entry.target_key_value)
        assert read == ["HG0.bam", "HG1.bam", "HG2.bam"]

    def test_an_invalid_byte_is_named_by_line_not_raised_as_a_codec_error(self, tmp_path):
        """A text handle decodes inside its own iterator, so a bad byte in a later
        record escaped as `UnicodeDecodeError` with a byte offset — a traceback
        rather than the line-numbered ValueError this module promises. The file is
        opened as bytes and decoded where the line number is known."""
        path = tmp_path / "c.ndjson"
        envelope = json.dumps({ENVELOPE_KEY: envelope_block()}).encode() + b"\n"
        path.write_bytes(envelope + b'{"field":"platform","target_key_value":"\xff\xfe","raw_value":"x"}\n')

        with pytest.raises(ValueError, match=r"c\.ndjson line 2: not valid UTF-8"):
            list(iter_evidence(path))

    @pytest.mark.parametrize("line", [1, 2])
    def test_a_line_nested_past_the_decoder_s_limit_is_refused_by_line(self, tmp_path, line):
        """`json.loads` raises RecursionError, not JSONDecodeError, past ~1000 levels.

        `report_evidence_files` runs at the top of every classification run and catches
        `ValueError`, so an escape here aborts the whole run on one malformed file —
        the opposite of the report naming every file it found (#401 review).
        """
        deep = "[" * 2000 + "]" * 2000
        envelope = json.dumps({ENVELOPE_KEY: envelope_block()})
        first = '{"evidence_file":' + deep + "}" if line == 1 else envelope
        second = envelope if line == 1 else '{"field":"platform","target_key_value":"x","raw_value":' + deep + "}"
        path = tmp_path / "evidence.ndjson"
        path.write_text(first + "\n" + second + "\n")

        with pytest.raises(ValueError, match=f"line {line}"):
            list(iter_evidence(path))

    @pytest.mark.parametrize("line", [1, 2])
    def test_a_number_past_the_interpreter_s_digit_limit_is_refused_by_line(self, tmp_path, line):
        """`json.loads` raises a bare ValueError, not a JSONDecodeError, past 4,300 digits.

        A limit on integer parsing since 3.10.7, so this is not a future-interpreter
        case. It escaped the decode handler and reached the caller without the file
        and line every other malformed line carries.
        """
        big = "1" * 5000
        envelope = json.dumps({ENVELOPE_KEY: envelope_block()})
        first = '{"evidence_file":{"n":' + big + "}}" if line == 1 else envelope
        second = envelope if line == 1 else '{"field":"platform","target_key_value":"x","raw_value":' + big + "}"
        path = tmp_path / "evidence.ndjson"
        path.write_text(first + "\n" + second + "\n")

        with pytest.raises(ValueError, match=f"line {line}"):
            list(iter_evidence(path))

    def test_a_file_nested_past_the_decoder_s_limit_is_reported_not_raised(self, tmp_path, capsys):
        """One unreadable evidence file must not hide the ones beside it, or the run."""
        (tmp_path / "deep.ndjson").write_text('{"evidence_file":' + "[" * 2000 + "]" * 2000 + "}\n")
        write_evidence_file(tmp_path / "good.ndjson", evidence_file_envelope(), [_entry()])

        deep, good = report_evidence_files(tmp_path)

        assert deep.envelope is None and "RecursionError" in (deep.error or "")
        assert good.envelope is not None
        assert "envelope could not be read" in capsys.readouterr().out

    def test_a_file_with_no_line_break_is_refused_before_it_is_read(self, tmp_path):
        """`readline` on a file with no newline reads the file — the one thing this
        module exists to avoid. An evidence corpus written as one JSON array is the
        reachable case: valid JSON, one line, and unbounded (#374).
        """
        path = tmp_path / "array.ndjson"
        path.write_text("[" + ",".join(f'{{"n":{n}}}' for n in range(200_000)) + "]")
        assert path.stat().st_size > _MAX_ENVELOPE_BYTES

        with pytest.raises(ValueError, match="no line break in the first"):
            read_envelope(path)

    def test_a_blank_line_carries_no_row(self, tmp_path):
        path = tmp_path / "evidence.ndjson"
        write_evidence_file(path, evidence_file_envelope(), [_entry()])
        path.write_text(path.read_text() + "\n")

        assert len(list(iter_evidence(path))) == 1

    def test_an_empty_file_is_a_missing_envelope_not_an_empty_row_set(self, tmp_path):
        path = tmp_path / "evidence.ndjson"
        path.write_text("")

        with pytest.raises(ValueError, match="line 1 must be the evidence_file envelope"):
            read_envelope(path)
        with pytest.raises(ValueError, match="line 1 must be the evidence_file envelope"):
            list(iter_evidence(path))

    @pytest.mark.parametrize(
        "envelope,expected",
        [
            ({"source": {"url": "u"}}, "source repository: Field required"),
            ({"source": {"repository": ""}}, "source repository: .*Invalid repository format"),
            ({"source": {"repository": None}}, "source repository: Input should be a valid string"),
            ({"source": {"repository": "HPRC", "table": 7}}, "source table: Input should be a valid string"),
            ({"fetched_at": None}, "fetched_at: Input should be a valid string"),
            ({"fetched_at": "yesterday"}, "fetched_at: .*Invalid fetched_at format"),
            ({"fetched_at": "2026-09-01"}, "fetched_at: .*Invalid fetched_at format"),
            # A date can be longer than ten characters without carrying a time:
            # `fromisoformat` read all three of these as midnight, and the first two
            # come straight off an API that stamps a UTC designator on a date (#401
            # review). The third is a real separator's worth of characters in the
            # right place and still not a `T`. The schema's pattern refuses each.
            ({"fetched_at": "2026-09-01Z"}, "fetched_at: .*Invalid fetched_at format"),
            ({"fetched_at": "2026-09-01+00:00"}, "fetched_at: .*Invalid fetched_at format"),
            ({"fetched_at": "2026-09-01X09:14:03"}, "fetched_at: .*Invalid fetched_at format"),
            # Basic-format ISO 8601, which 3.10 refuses to parse and 3.11 accepts.
            # The pattern refuses it before any parser sees it, so the file reads the
            # same on every interpreter.
            ({"fetched_at": "20260901T091403"}, "fetched_at: .*Invalid fetched_at format"),
            # Well-shaped and not a day: the pattern passes it and the parse refuses
            # it, which is the one check no regex can make (#401 review).
            ({"fetched_at": "2026-02-30T09:14:03"}, "fetched_at '2026-02-30T09:14:03' is not an ISO 8601"),
            # The block itself is not an object: no member to name.
            ("not an object at all", "envelope is str, not an object"),
            ({"source_version": ""}, "source_version: .*Invalid source_version format"),
            ({"source_key": None}, "source_key: Input should be a valid string"),
            # An evidence file is written by an importer reading something we do not
            # own, so its source_type is one of IMPORTER_SOURCE_TYPES. `content_read`
            # is the reachable mistake: a real source_type, and our own inference's.
            ({"source_type": SOURCE_CONTENT_READ}, "source_type: Input should be 'external_ground_truth'"),
            ({"source_type": None}, "source_type: Input should be 'external_ground_truth'"),
            ({"target": {"system": ""}}, "target system: .*Invalid system format"),
            ({"target": {"system": "anvil", "dataset": 7}}, "target dataset: Input should be a valid string"),
            ({"target_key": "sample_id"}, "target_key: Input should be 'file_id'"),
        ],
    )
    def test_an_envelope_missing_a_fact_is_refused(self, tmp_path, envelope, expected):
        """Every envelope member is checked on read: the report rests on all of them.

        Each case overrides one member of a valid envelope — or, where the member
        under test is inside ``source`` or ``target``, that whole nested record — so
        what it asserts is the member named and not an unrelated one that happened to
        be missing too. The checks are the generated model's (#494); what this pins is
        that the refusal reaches the reader's caller as a ``ValueError`` naming the
        member and the fault, so a match on the member alone — which every message
        for a block carrying it would satisfy — is not enough.
        """
        path = tmp_path / "evidence.ndjson"
        block = {**envelope_block(), **envelope} if isinstance(envelope, dict) else envelope
        path.write_text(json.dumps({ENVELOPE_KEY: block}) + "\n")

        with pytest.raises(ValueError, match=expected):
            read_envelope(path)

    def test_a_row_for_an_unknown_dimension_is_refused_both_ways(self, tmp_path):
        path = tmp_path / "evidence.ndjson"
        entry = _entry()
        with pytest.raises(ValueError, match="unknown dimension"):
            # `replace` rather than a valid constructor call: an importer that is not
            # type-checked is exactly what this refusal exists for.
            write_evidence_file(path, evidence_file_envelope(), [replace(entry, field="data_moddality")])

        write_evidence_file(path, evidence_file_envelope(), [entry])
        path.write_text(path.read_text().replace('"platform"', '"data_moddality"', 1))
        with pytest.raises(ValueError, match="line 2: unknown dimension"):
            list(iter_evidence(path))

    def test_a_line_with_nothing_to_match_on_is_refused(self, tmp_path):
        """A row whose target_key_value is empty can attach to no file."""
        with pytest.raises(ValueError, match="target_key_value"):
            write_evidence_file(tmp_path / "c.ndjson", evidence_file_envelope(), [_entry(name="")])

    @pytest.mark.parametrize("bad", ["HG002\nb.bam", "HG002\rb.bam", "HG002.bam\n"])
    def test_a_target_key_value_carrying_a_line_break_is_refused(self, tmp_path, bad):
        """The schema always refused it; the reader did not, which is the unsafe way round.

        `EvidenceRow.target_key_value` carries `pattern: "^[^\\r\\n]+\\Z"`, so a row like
        this validated against the gate and was refused by nothing — the writer could
        publish a file its own schema rejects. Every key in `JOIN_KEYS` is a file name,
        checksum, URI or accession and none contains a line break (#421 review). The
        trailing case matters on its own: a Python `$` matches before a final newline,
        which is why the schema pattern ends in `\\Z`.
        """
        with pytest.raises(ValueError, match="carries a line break"):
            write_evidence_file(tmp_path / "c.ndjson", evidence_file_envelope(), [_entry(name=bad)])

    @pytest.mark.parametrize("raw", [None, 7, ["Revio"]])
    def test_a_raw_value_that_is_not_a_string_is_refused_both_ways(self, tmp_path, raw):
        """The one check a raw value gets: the format holds a string.

        Its emptiness and its spelling are deliberately not checked — see
        `TestRoundTrip.test_the_raw_value_is_what_the_source_wrote` — so this is the
        whole of what a malformed raw value can be.
        """
        path = tmp_path / "evidence.ndjson"
        with pytest.raises(ValueError, match="raw_value"):
            write_evidence_file(path, evidence_file_envelope(), [_entry(raw=raw)])

        write_evidence_file(path, evidence_file_envelope(), [_entry()])
        path.write_text(path.read_text().replace('"Revio"', json.dumps(raw), 1))
        with pytest.raises(ValueError, match="line 2: raw_value"):
            list(iter_evidence(path))

    def test_an_envelope_naming_a_key_the_target_does_not_have_is_refused(self, tmp_path):
        """`target_key` is a key of the *target*. A source keyed by something else maps
        it to one of these itself rather than adding a term here."""
        with pytest.raises(ValueError, match="target_key"):
            evidence_file_envelope(target_key="sample_id")


class TestAWriterCannotProduceWhatTheReaderRefuses:
    """The two sides of the contract agree, so a fault surfaces at the importer (#401 review).

    The write path used to check every row and never the envelope, so a networked
    import could spend its run writing millions of rows behind a header its own
    reader would reject — discovered at the next classification run, far from the
    cause.
    """

    @pytest.mark.parametrize("version", ["", None])
    def test_an_envelope_with_no_usable_version_is_refused_when_it_is_built(self, version):
        """`None` was the trap: `to_dict` drops nulls, so the key vanished entirely."""
        with pytest.raises(ValueError, match="source_version"):
            evidence_file_envelope(source_version=version)

    def test_an_envelope_keyed_by_file_name_needs_a_dataset_to_scope_it(self, tmp_path):
        """The guard the whole filename join rests on: 69.4% of rows share a name.

        Refused where the file is written, not where it is joined, because a file
        written without a scope is already unusable by the time a join reads it. The
        schema declares the rule and gen-pydantic drops it, so the constructor accepts
        this envelope and `require_scoped_target` refuses it on both paths (#494).
        """
        unscoped = evidence_file_envelope(
            target=EvidenceTarget(system="anvil", version="anvil15"), target_key="file_name"
        )
        path = tmp_path / "c.ndjson"
        with pytest.raises(ValueError, match="needs a target dataset to scope it"):
            write_evidence_file(path, unscoped, [_entry()])
        assert not path.exists()

        path.write_text(json.dumps({ENVELOPE_KEY: unscoped.model_dump(exclude_none=True)}) + "\n")
        with pytest.raises(ValueError, match=r"c\.ndjson line 1: .*needs a target dataset to scope it"):
            read_envelope(path)

    def test_an_envelope_keyed_by_a_unique_key_needs_no_dataset(self):
        """`file_id` is unique on every one of the 708,088 rows: no scope to add."""
        envelope = evidence_file_envelope(
            target=EvidenceTarget(system="anvil", version="anvil15"), target_key="file_id"
        )

        assert envelope.target.dataset is None

    @pytest.mark.parametrize("forged", ["HPRC\nfake.ndjson — forged source", "HPRC\rfake", "HPRC\n"])
    def test_a_source_member_carrying_a_line_break_is_refused(self, forged):
        """Every one of these is printed in the run's report, one file per line.

        A newline in a repository name is a second report line the evidence file wrote.
        The schema refuses it — the slots carry `pattern: "^[^\\r\\n]+\\Z"` — and the
        generated model carries the same pattern, so the constructor refuses it.
        """
        with pytest.raises(ValueError, match="repository"):
            evidence_file_envelope(source=EvidenceFileSource(repository=forged, dataset="R2", table="t"))

    @pytest.mark.parametrize("bad", [SOURCE_CONTENT_READ, "hearsay", None, ""])
    def test_an_envelope_with_a_source_type_an_importer_cannot_write_is_refused_when_built(self, bad):
        """An importer reads something we do not own, so the kind is one of ``IMPORTER_SOURCE_TYPES``.

        `content_read` is the reachable mistake and the reason this is checked rather
        than assumed: it is a real `source_type`, and it is inference's own — an
        evidence file declaring it would be naming our rule engine as its publisher.
        Refused where the envelope is built as well as where it is read, so a
        networked import fails at its own first line rather than at the next
        classification run.
        """
        with pytest.raises(ValueError, match="source_type"):
            evidence_file_envelope(source_type=bad)

    def test_a_curator_cannot_be_written_as_an_evidence_file(self):
        """A curator enters as rules, not as evidence — contract 1.6, and 1.7.

        `wrangler_annotation` is a legitimate kind for a *claim*: a curator's decision
        is cited and reviewed like any other, and `EXTERNAL_SOURCE_TYPES` still carries
        it. What it may not be is the source of an evidence *file*. The two vocabularies
        differ by exactly this one term, and the difference is the contract's, not an
        oversight — so it is asserted rather than left to be rediscovered when #397
        builds the curator table.
        """
        assert SOURCE_WRANGLER_ANNOTATION in models.EXTERNAL_SOURCE_TYPES
        assert SOURCE_WRANGLER_ANNOTATION not in models.IMPORTER_SOURCE_TYPES
        with pytest.raises(ValueError, match="source_type"):
            evidence_file_envelope(source_type=SOURCE_WRANGLER_ANNOTATION)

    def test_an_envelope_with_a_nameless_source_is_refused_when_it_is_built(self):
        with pytest.raises(ValueError, match="repository"):
            evidence_file_envelope(source=EvidenceFileSource(repository=""))

    def test_an_envelope_with_a_non_datetime_fetch_time_is_refused_when_it_is_built(self):
        with pytest.raises(ValueError, match="fetched_at"):
            evidence_file_envelope(fetched_at="2026-09-01")

    def test_an_envelope_cannot_name_a_column_at_all(self):
        """A column belongs to a row, not to a file — the type says so.

        `EvidenceFileSource` has no `column` member, so an envelope naming one is not a
        value to be refused at runtime but a shape the model does not have — it is
        `extra="forbid"`, as the schema is `closed`. One table's rows are read from
        several columns, so a column on the envelope could disagree with every line in
        the file.
        """
        assert "column" not in EvidenceFileSource.model_fields
        with pytest.raises(ValueError, match="column"):
            EvidenceFileSource(repository="HPRC", table="t", column="platform")  # type: ignore[call-arg]

    def test_an_envelope_whose_source_has_a_non_string_member_is_refused_when_it_is_built(self):
        """The annotation says `str | None`, so the ignore is the point of the test:
        type hints do not run, and an importer mapping a source's own JSON can hand
        over whatever that JSON held."""
        with pytest.raises(ValueError, match="table"):
            evidence_file_envelope(source=EvidenceFileSource(repository="HPRC", table=7))  # type: ignore[arg-type]

    def test_a_hand_built_row_the_reader_would_refuse_is_refused_at_write(self, tmp_path):
        """An importer builds an EvidenceEntry by hand; the writer holds it to the line shape."""
        entry = replace(_entry(), source=ClaimSource(name="HPRC Data Explorer", column="instrumentModel"))

        with pytest.raises(ValueError, match="envelope names"):
            write_evidence_file(tmp_path / "c.ndjson", evidence_file_envelope(), [entry])

    def test_a_file_the_run_would_never_find_is_refused_at_write(self, tmp_path):
        """`discover` matches *.ndjson, so any other suffix is a silent no-op."""
        with pytest.raises(ValueError, match="must be named"):
            write_evidence_file(tmp_path / "hprc" / "catalog.json", evidence_file_envelope(), [_entry()])

    @pytest.mark.parametrize("block", [{"rank": 9}, {"source": {"name": "HPRC", "column": None}}])
    def test_an_unknown_envelope_member_is_refused_with_the_file_and_line(self, tmp_path, block):
        """The schema validates the envelope `closed=True`; the reader must agree.

        A `"column": null` on an envelope source used to be accepted here and
        silently stripped while the schema rejected it. The generated model is
        `extra="forbid"`, and the reader re-words its refusal with the file and line,
        which the model cannot — it validates a block and does not know where one
        came from (#494).
        """
        path = tmp_path / "c.ndjson"
        envelope = {**envelope_block(), **block}
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
        envelope = envelope_block()
        payload = (
            [envelope if v == "ENVELOPE" else v for v in wrapper]
            if isinstance(wrapper, list)
            else {k: (envelope if v == "ENVELOPE" else v) for k, v in wrapper.items()}
        )
        path = tmp_path / "c.ndjson"
        path.write_text(json.dumps(payload) + "\n")

        with pytest.raises(ValueError, match=r"c\.ndjson line 1"):
            read_envelope(path)

    def test_a_well_shaped_fetched_at_that_is_not_a_day_is_refused_at_write(self, tmp_path):
        """The one check beyond the schema's pattern, run on the writer's side too.

        `2026-02-30T09:14:03` matches the pattern, so the generated model builds the
        envelope; the reader would refuse the file at line 1. The writer refuses it
        first, before creating anything (#507 review).
        """
        path = tmp_path / "hprc" / "c.ndjson"
        with pytest.raises(ValueError, match="fetched_at '2026-02-30T09:14:03' is not an ISO 8601"):
            write_evidence_file(path, evidence_file_envelope(fetched_at="2026-02-30T09:14:03"), [_entry()])
        assert not path.parent.exists()

    def test_a_refused_member_carrying_a_line_break_is_reported_on_one_line(self, tmp_path):
        """The report prints one file per line, and a refusal is that file's line.

        The generated pattern validators embed the offending value in their message,
        and the one way to fail the no-line-break pattern is a line break — so the
        refusal would carry the forged second line into the report unescaped (#494
        security review). Escaped, as the removed reader's `!r` escaped it.
        """
        path = tmp_path / "c.ndjson"
        block = {**envelope_block(), "source_version": "1\nforged line"}
        path.write_text(json.dumps({ENVELOPE_KEY: block}) + "\n")

        with pytest.raises(ValueError) as caught:
            read_envelope(path)
        assert "\n" not in str(caught.value)
        assert "source_version" in str(caught.value)

    def test_a_utc_z_suffix_reads_back_on_every_supported_interpreter(self, tmp_path):
        """`fromisoformat` rejects `Z` on 3.10 (the floor and what CI runs), takes it on 3.11+.

        The importers read web APIs that emit `Z` almost universally — an evidence
        file must not parse on a dev box and fail on CI. The envelope carries the
        string as written; the parse to an instant is pydantic's, which is the same on
        every interpreter (#494).
        """
        path = tmp_path / "c.ndjson"
        block = {**envelope_block(), "fetched_at": "2026-09-01T09:14:03Z"}
        path.write_text(json.dumps({ENVELOPE_KEY: block}) + "\n")

        envelope = read_envelope(path)
        assert envelope.fetched_at == "2026-09-01T09:14:03Z"
        assert source_evidence.parse_iso_datetime(envelope.fetched_at, "fetched_at", "c.ndjson") == datetime(
            2026, 9, 1, 9, 14, 3, tzinfo=timezone.utc
        )


class TestALineIsAnObservationNotAClaim:
    """A row records what a source wrote and declares nothing (#421, contract 1.1).

    Until #421 a line held a claim, and this class held the twenty-odd cases that
    made a claim off disk satisfy `make_claim`. None of them can happen now: there is
    no claim on a line to be malformed. What replaces them is the shape a row does
    have, and — because a producer written against the old format is the reachable
    mistake — a refusal that names each retired member and says what to write instead.
    """

    def _write_raw(self, tmp_path, **members) -> Path:
        """An evidence file whose one line carries ``members`` verbatim, bypassing the writer."""
        path = tmp_path / "c.ndjson"
        line = {"field": "platform", "target_key_value": "HG002.bam", "raw_value": "Revio", **members}
        path.write_text(evidence_lines(line))
        return path

    # Over the map itself, not a hand-copied list: a key added there and not here
    # would go untested silently. The value is arbitrary — the refusal fires on the
    # member's presence, before anything looks at what it holds.
    @pytest.mark.parametrize("member", sorted(source_evidence._RETIRED_LINE_KEYS))
    def test_a_retired_member_is_refused_by_name(self, tmp_path, member):
        """Each one is a thing a line used to carry, and the refusal says why it does not.

        A bare "unknown member" would be true and useless: the producer that hits this
        is one written against #401's format, or against the contract's earlier
        framing, and what it needs to be told is where that member went.

        Note `value` and `status`: these are the contract's whole point. A line
        offering either is an importer declaring meaning, which is the rule engine's
        (1.1, 3.6). And `source`: the envelope names this file's source, so a line
        that re-attributed itself would undo the writer's check for exactly the files
        it cannot vouch for.
        """
        path = self._write_raw(tmp_path, **{member: "x"})

        with pytest.raises(ValueError, match=f"{member!r} is not a member of an evidence row"):
            list(iter_evidence(path))

    def test_the_record_offers_nowhere_to_put_a_retired_member(self):
        """The writer cannot publish one either, because the record cannot hold one.

        This is the stronger half of the guarantee: the reader refuses a hand-written
        line, and an importer using the record is refused by the type system before it
        writes anything. The field-set assertion is what carries it — `EvidenceEntry`
        has four members and none of them is an answer — and the `TypeError` is the
        one mechanism that follows from it, not five.
        """
        assert {f.name for f in fields(EvidenceEntry)} == {"field", "target_key_value", "raw_value", "source"}
        with pytest.raises(TypeError):
            EvidenceEntry(
                field="platform",
                target_key_value="HG002.bam",
                raw_value="Revio",
                value="PACBIO",  # type: ignore[call-arg]
            )

    def test_a_line_in_the_retired_format_is_refused_by_name_not_by_keyerror(self, tmp_path):
        """The case `_RETIRED_LINE_KEYS` exists for, written the way #401 wrote it.

        `_write_raw` adds a retired member *beside* a complete row, which is not what a
        producer written against #401 emits: that line carries `claim` and no
        `raw_value` at all. Reading the three members before checking the member set
        made this raise `KeyError('raw_value')`, so the named refusal could never fire
        for the only producer it was written for — the tests passed and the feature
        did not work (#421 review).
        """
        path = tmp_path / "c.ndjson"
        line = {
            "field": "platform",
            "target_key_value": "HG002.bam",
            "claim": {"rule_id": "map_hprc_platform_v1", "value": "PACBIO", "raw_value": "Revio"},
        }
        path.write_text(evidence_lines(line))

        with pytest.raises(ValueError, match="'claim' is not a member of an evidence row"):
            list(iter_evidence(path))

    @pytest.mark.parametrize("missing", ["field", "target_key_value", "raw_value"])
    def test_a_row_missing_one_of_its_three_facts_names_the_member(self, tmp_path, missing):
        """A row short a member is named, not reported as an opaque KeyError."""
        line = {"field": "platform", "target_key_value": "HG002.bam", "raw_value": "Revio"}
        del line[missing]
        path = tmp_path / "c.ndjson"
        path.write_text(evidence_lines(line))

        with pytest.raises(ValueError, match=f"evidence row has no {missing!r}"):
            list(iter_evidence(path))

    def test_a_line_that_is_not_an_object_is_refused(self, tmp_path):
        """A bare list or string parses as JSON and is not a row."""
        path = tmp_path / "c.ndjson"
        path.write_text(evidence_lines(["platform"]))

        with pytest.raises(ValueError, match="not an evidence row"):
            list(iter_evidence(path))

    def test_an_unknown_member_beside_the_row_is_refused(self, tmp_path):
        """A member that was never part of the format, as opposed to a retired one.

        A reader that dropped one silently would normalize a malformed file into an
        apparently valid row.
        """
        path = self._write_raw(tmp_path, rank=9)

        with pytest.raises(ValueError, match=r"unknown member\(s\) \['rank'\]"):
            list(iter_evidence(path))

    @pytest.mark.parametrize("member", ["url", "dataset", "table"])
    def test_an_optional_envelope_member_that_is_an_explicit_null_reads_as_absent(self, tmp_path, member):
        """The envelope agrees with the schema here, and the line does not (next test).

        LinkML models an optional slot as nullable, so the schema admits
        `"table": null` on an envelope source; the reader is the model generated from
        the schema and admits the same (#494). The writer never emits one — it omits
        the member — so the only file this reaches is one written by hand, and reading
        the null as the absent member it means is what the schema says it means.
        """
        source = {**envelope_block()["source"], member: None}
        path = tmp_path / "evidence.ndjson"
        path.write_text(json.dumps({ENVELOPE_KEY: {**envelope_block(), "source": source}}) + "\n")

        assert getattr(read_envelope(path).source, member) is None

    def test_a_line_whose_column_is_an_explicit_null_is_refused(self, tmp_path):
        """Absent is fine; a written-out null is a record the writer could not produce.

        `dict.get` with a default cannot tell the two apart, so collapsing them would
        accept here what every other member refuses.
        """
        path = self._write_raw(tmp_path, column=None)

        with pytest.raises(ValueError, match="explicit null"):
            list(iter_evidence(path))

    def test_a_line_whose_column_is_not_a_string_is_refused(self, tmp_path):
        """The per-line `column` is a source member and is checked like the rest."""
        path = self._write_raw(tmp_path, column=7)

        with pytest.raises(ValueError, match="source column"):
            list(iter_evidence(path))

    def test_an_unhashable_line_member_is_refused_by_name_not_by_traceback(self, tmp_path):
        """`field: []` raises TypeError from the frozenset lookup unless type is checked first.

        That escapes as a codec-style traceback rather than the ValueError naming the
        file and the line, which is the one thing this module promises about a
        malformed file.
        """
        path = self._write_raw(tmp_path, field=[])

        with pytest.raises(ValueError, match=r"c\.ndjson line 2: unknown dimension"):
            list(iter_evidence(path))


class TestDiscovery:
    """What a run finds under the source-evidence root."""

    def test_a_missing_root_is_no_source_evidence_not_an_error(self, tmp_path):
        assert discover(tmp_path / "source_evidence") == []

    def test_source_evidence_are_found_per_source_and_ordered(self, tmp_path):
        for name in ("hprc/catalog.ndjson", "anvil/manifest.ndjson", "hprc/notes.json"):
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")

        assert [p.relative_to(tmp_path).as_posix() for p in discover(tmp_path)] == [
            "anvil/manifest.ndjson",
            "hprc/catalog.ndjson",
        ]

    def test_only_the_newest_generation_of_a_dataset_is_current(self, tmp_path):
        """An import is a generation (#369): the one behind it is history, on disk and unread."""
        for name in (
            "anvil/anvil15/D/20260920T000000Z/hifi.ndjson",
            "anvil/anvil15/D/20260921T000000Z/hifi.ndjson",
            "anvil/anvil15/D/20260921T000000Z/ont.ndjson",
            "anvil/anvil15/E/20260919T000000Z/file.ndjson",
            "hprc/catalog.ndjson",
        ):
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")

        assert [p.relative_to(tmp_path).as_posix() for p in discover(tmp_path)] == [
            "anvil/anvil15/D/20260921T000000Z/hifi.ndjson",
            "anvil/anvil15/D/20260921T000000Z/ont.ndjson",
            "anvil/anvil15/E/20260919T000000Z/file.ndjson",
            "hprc/catalog.ndjson",
        ]

    def test_a_stamp_named_directory_at_another_depth_is_not_a_generation(self, tmp_path):
        """Only the fourth segment under the root is a generation; a stamp elsewhere is a name."""
        for name in (
            "anvil/20260921T000000Z/D/20260920T000000Z/hifi.ndjson",  # a version spelled like a stamp
            "anvil/20260921T000000Z/D/20260921T000000Z/hifi.ndjson",
            "20260919T000000Z/flat.ndjson",  # a stamp one level under the root
            "anvil/anvil15/20260918T000000Z/x.ndjson",  # a dataset spelled like a stamp, no generation
        ):
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        assert [p.relative_to(tmp_path).as_posix() for p in discover(tmp_path)] == [
            "20260919T000000Z/flat.ndjson",
            "anvil/20260921T000000Z/D/20260921T000000Z/hifi.ndjson",
            "anvil/anvil15/20260918T000000Z/x.ndjson",
        ]

    def test_the_generation_layout_is_spelled_once(self, tmp_path):
        stamp = new_generation(datetime(2026, 9, 20, 6, 41, 31, tzinfo=timezone.utc))
        assert stamp == "20260920T064131Z"
        assert is_generation(stamp) and not is_generation("20260920_064131")
        assert generation_dir(tmp_path, "anvil", "anvil15", "D", stamp) == tmp_path / "anvil" / "anvil15" / "D" / stamp
        with pytest.raises(ValueError, match="not a generation stamp"):
            generation_dir(tmp_path, "anvil", "anvil15", "D", "latest")

    def test_a_naive_clock_is_read_as_local_time_and_stamped_in_utc(self):
        stamp = new_generation(datetime(2026, 9, 20, 6, 41, 31))
        assert is_generation(stamp)


class TestTheRunReport:
    """What a run says about the evidence files it found.

    It reports and does not judge. A run cannot tell offline whether an evidence file has
    outlived what it describes — the sources share no version to compare, and AnVIL
    deletes a superseded catalog rather than keeping it to be matched against — so
    every file is named with its provenance and age, and nothing is refused.
    """

    def test_an_unfinished_import_is_named_and_not_read(self, tmp_path, capsys):
        partial = tmp_path / "anvil" / "anvil15" / "D" / "20260920T000000Z.partial"
        partial.mkdir(parents=True)
        (partial / "hifi.ndjson").write_text("not an envelope")
        assert report_evidence_files(tmp_path) == []
        out = capsys.readouterr().out.replace("\\", "/")
        assert "Unfinished import, not read (remove it by hand): anvil/anvil15/D/20260920T000000Z.partial" in out

    def test_no_source_evidence_is_said_rather_than_passed_over(self, tmp_path, capsys):
        assert report_evidence_files(tmp_path / "source_evidence") == []
        assert "none under" in capsys.readouterr().out

    def test_provenance_and_age_are_reported_per_file(self, tmp_path, capsys):
        write_evidence_file(tmp_path / "hprc" / "catalog.ndjson", evidence_file_envelope(), [_entry()])

        statuses = report_evidence_files(tmp_path, now=FETCHED_AT + timedelta(days=8))
        out = capsys.readouterr().out
        assert [s.error for s in statuses] == [None]
        assert "hprc/catalog.ndjson" in out.replace("\\", "/")
        # Both sides of the join, in the order a reader needs them: what it came from,
        # then what it is about, each with the key that pairs them.
        assert "HPRC Data Explorer/R2/sequencing-data[filename]" in out
        # The target's generation reads as `@anvil15`, not as another level of the
        # path — slash-joined it would look like a table.
        assert "anvil/AnVIL_HPRC_R2[file_name] @anvil15" in out
        assert "v2026-09-01" in out
        assert "8 days ago" in out

    def test_a_target_generation_is_reported_as_provenance(self, tmp_path, capsys):
        """The generation a file was built against is said, not checked."""
        target = EvidenceTarget(system="anvil", dataset="AnVIL_HPRC_R2", version="anvil14")
        write_evidence_file(tmp_path / "anvil" / "manifest.ndjson", evidence_file_envelope(target=target), [])

        (status,) = report_evidence_files(tmp_path)
        out = capsys.readouterr().out
        assert status.error is None
        assert "anvil14" in out
        assert "UNREADABLE" not in out

    def test_an_unreadable_file_is_named_rather_than_hiding_the_rest(self, tmp_path, capsys):
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "broken.ndjson").write_text("{not json\n")
        write_evidence_file(tmp_path / "b" / "good.ndjson", evidence_file_envelope(), [_entry()])

        broken, good = report_evidence_files(tmp_path)
        assert broken.envelope is None and broken.error is not None
        assert good.error is None
        assert "envelope could not be read" in capsys.readouterr().out

    def test_an_aware_fetch_time_is_aged_without_a_type_error(self, tmp_path, capsys):
        """Ages are taken in the envelope's own timezone, so either kind subtracts."""
        aware = datetime(2026, 9, 1, 9, 14, 3, tzinfo=timezone.utc).isoformat()
        write_evidence_file(tmp_path / "c.ndjson", evidence_file_envelope(fetched_at=aware), [])

        report_evidence_files(tmp_path)
        out = capsys.readouterr().out
        assert "ago" in out or "today" in out

    def test_a_naive_now_ages_an_aware_fetch_time(self, tmp_path, capsys):
        """A caller's clock and an envelope's need not agree on awareness.

        That disagreement used to raise inside `_describe`, which would have taken
        every other file's line down with it — the opposite of what the report is for.
        """
        aware = datetime(2026, 9, 1, 9, 14, 3, tzinfo=timezone.utc).isoformat()
        write_evidence_file(tmp_path / "c.ndjson", evidence_file_envelope(fetched_at=aware), [])

        report_evidence_files(tmp_path, now=datetime(2026, 9, 9, 9, 14, 3))
        assert "days ago" in capsys.readouterr().out

    def test_a_fetch_time_in_the_future_is_said_not_clamped(self, tmp_path, capsys):
        write_evidence_file(tmp_path / "c.ndjson", evidence_file_envelope(), [])

        report_evidence_files(tmp_path, now=FETCHED_AT - timedelta(days=2))
        assert "dated in the future" in capsys.readouterr().out


class TestAnEvidenceFileIsWrittenBySomeoneElse:
    """A source with no url and no dataset level is not a special case.

    This was the curator table until #421. A curator enters as rules rather than as
    evidence (contract 1.6), so the shape it stood for — a publisher with no public
    address, no middle level, keyed by the strongest key the target has — is tested
    here with a source that may actually write one.
    """

    def test_a_flat_source_with_no_url_round_trips(self, tmp_path):
        # An external authority published as a flat table: no url to cite, no dataset
        # level, and keyed by content rather than by a name it does not publish.
        registry = EvidenceFileSource(repository="1000 Genomes sample registry", table="samples")
        entry = EvidenceEntry(
            field="data_modality",
            target_key_value="a" * 32,
            raw_value="GENOMIC",
            source=claim_source_for(registry, "library_source"),
        )
        path = tmp_path / "registry.ndjson"
        write_evidence_file(
            path,
            evidence_file_envelope(
                source=registry,
                source_type=SOURCE_EXTERNAL_GROUND_TRUTH,
                source_version="rev-3",
                source_key="sample_id",
                target=EvidenceTarget(system="anvil"),
                target_key=JOIN_KEY_FILE_MD5SUM,
            ),
            [entry],
        )

        envelope = read_envelope(path)
        assert envelope.source.url is None and envelope.source.dataset is None
        assert envelope.source_type == SOURCE_EXTERNAL_GROUND_TRUTH
        # No dataset scope. An md5 is not unique corpus-wide — 12,203 rows share one,
        # two thirds of them inside a single dataset — but every row sharing an md5 has
        # the same bytes, so a statement about the content is true of all of them. What
        # a join should do with that is #402's — see `EvidenceTarget.dataset`.
        assert envelope.target.dataset is None
        assert list(iter_evidence(path)) == [entry]


@pytest.fixture(scope="module")
def schema() -> dict:
    """The LinkML schema, parsed once for the tests that read it.

    Through `schema_vocab.default_schema_path()` rather than a hand-built path: it is
    the canonical locator (`test_package_data` uses it the same way) and it does not
    go stale if the package-data anchor moves.
    """
    return yaml.safe_load(default_schema_path().read_text())


def test_the_row_shape_is_one_set_in_three_places(schema):
    """`_LINE_KEYS`, `EvidenceEntry` and the schema's `EvidenceRow` must agree.

    Three hand-maintained statements of the same four members: what the reader accepts
    on a line, what the record can hold, and what the `closed=True` gate validates. A
    fifth member added to one and not the others is written by this module and refused
    by the gate, or accepted by the gate and refused by the reader — the exact
    "schema says yes to what the only reader says no to" failure the rest of these
    tests exist to prevent, and the one drift the PR that added `EvidenceRow` left
    unguarded (#421 review).

    The envelope needs no equivalent: its reader is the model generated from the
    schema, held to it by `schema/tests/test_model_drift.py`, so the two cannot
    disagree by construction (#494).

    `source` maps to `column` across the boundary — the record carries whole
    provenance, the line carries only the member that varies within a file — so that
    one name is translated rather than compared.
    """
    row = schema["classes"]["EvidenceRow"]
    on_the_wire = set(row["attributes"]) | set(row.get("slots") or [])

    assert on_the_wire == set(source_evidence._LINE_KEYS)
    assert {f.name for f in fields(EvidenceEntry)} == (set(source_evidence._LINE_KEYS) - {"column"}) | {"source"}


def test_a_retired_member_is_never_also_a_line_member():
    """The two sets are disjoint, which is what lets the reader pick either message.

    `_entry_from_line` scans the retired map only once it knows the line has a member
    it does not accept; an overlap would make a legal row raise.
    """
    assert not set(source_evidence._RETIRED_LINE_KEYS) & set(source_evidence._LINE_KEYS)


def test_the_row_field_pattern_lists_every_dimension(schema):
    """The schema's `EvidenceRow.field` pattern and `CLASSIFICATION_FIELDS` are one set.

    The pattern spells the five names out rather than pointing at an enum, because
    they are slot *names* in that schema and not a vocabulary it declares. That only
    stays safe while the two agree: a dimension added to the tuple and not to the
    pattern would be written by this module and refused by the gate (#421).
    """
    pattern = schema["classes"]["EvidenceRow"]["attributes"]["field"]["pattern"]

    assert set(pattern.removeprefix("^(").removesuffix(r")\Z").split("|")) == set(CLASSIFICATION_FIELDS)


def test_no_claim_is_constructed_on_either_path():
    """The module makes no claim, and the import graph is what proves it (#421).

    Contract 1.1: only the rule engine makes claims. Reading and writing a row must
    therefore be reachable without `make_claim` and without the vocabulary check —
    both of which this module called on every line until #421, on both directions.

    Asserted over the module's own imports rather than by probing its namespace: a
    `hasattr` check passes while a module-level import sits there unused, and an
    import of `rule_engine` from here is the thing that would make a claim possible
    again.
    """
    tree = ast.parse(Path(source_evidence.__file__).read_text())
    # Every dotted segment any import form touches. Collecting `ImportFrom.module`
    # alone caught `from .rule_engine import make_claim` and missed both
    # `import meta_disco.rule_engine` and `from meta_disco import rule_engine`, so the
    # guard would have passed after the forbidden dependency came back (#421 review).
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    imported = {segment for name in names for segment in name.split(".")}

    assert "rule_engine" not in imported, "reading or writing a row must not be able to make a claim"
    assert "schema_vocab" not in imported, "a raw value is not checked against our vocabulary (#414 owns that)"


def test_the_source_evidence_root_the_run_uses_is_under_data():
    """The default root is `data/source_evidence`, one directory per source under it."""
    assert DEFAULT_SOURCE_EVIDENCE_ROOT.parts[-2:] == ("data", "source_evidence")
    assert DEFAULT_SOURCE_EVIDENCE_ROOT.parent == Path(__file__).resolve().parents[1] / "data"


class TestOnePublishedSourcePerRepository:
    """Every repository has exactly one published source (#497, contract 7.12): the table
    declared for it, and one current file of it per dataset. The run refuses the rest
    at preflight, over the statuses its evidence report already gathered."""

    def _published(self, tmp_path, name, **envelope):
        path = tmp_path / name
        write_evidence_file(path, published_envelope(**envelope), [])
        return path

    def test_one_published_file_per_dataset_from_the_declared_table_passes(self, tmp_path):
        self._published(tmp_path, "a/anvil_file.ndjson")
        self._published(tmp_path, "b/anvil_file.ndjson", dataset="AnVIL_ENCORE_293T")
        write_evidence_file(tmp_path / "c/hifi.ndjson", evidence_file_envelope(), [])
        require_one_published_source(report_evidence_files(tmp_path), PUBLISHED_TABLES)

    def test_a_published_file_from_another_table_is_refused(self, tmp_path):
        self._published(tmp_path, "a/file.ndjson", table="file")
        with pytest.raises(ValueError, match=r"file\.ndjson.*from table 'file'.*published source is 'anvil_file'"):
            require_one_published_source(report_evidence_files(tmp_path), PUBLISHED_TABLES)

    def test_a_published_file_from_another_repository_is_refused(self, tmp_path):
        """A published source is the repository's own: a file labelled `published_value`
        whose source repository is not the one its rows are about is refused before the
        table is even consulted."""
        self._published(tmp_path, "a/anvil_file.ndjson", repository="HPRC Data Explorer")
        with pytest.raises(ValueError, match="from repository 'HPRC Data Explorer' about anvil's files"):
            require_one_published_source(report_evidence_files(tmp_path), PUBLISHED_TABLES)

    def test_the_declared_table_under_any_other_label_is_refused(self, tmp_path):
        """The other direction: AnVIL's own `anvil_file` rows labelled `repository_metadata`
        would reach reconcile as a submitter's opinion. Refused as `_check_kind` refuses
        the same mislabelling in a map."""
        self._published(tmp_path, "a/anvil_file.ndjson", source_type=SOURCE_REPOSITORY_METADATA)
        with pytest.raises(ValueError, match="carries repository_metadata from anvil's published table 'anvil_file'"):
            require_one_published_source(report_evidence_files(tmp_path), PUBLISHED_TABLES)

    def test_a_repository_whose_published_source_is_undeclared_can_have_no_file_claim_it(self, tmp_path):
        self._published(tmp_path, "a/anvil_file.ndjson")
        with pytest.raises(ValueError, match="anvil's published source is not declared"):
            require_one_published_source(report_evidence_files(tmp_path), {})

    def test_an_undeclared_repository_has_no_table_for_a_tableless_file_to_match(self, tmp_path):
        """A source's `table` is optional and an undeclared repository's table is None; the
        two are never taken as equal. A tableless submitter file for such a repository
        passes, and a tableless `published_value` file for it is still refused."""
        write_evidence_file(
            tmp_path / "a/hprc.ndjson",
            evidence_file_envelope(source=EvidenceFileSource(repository="hprc", dataset="R2")),
            [],
        )
        require_one_published_source(report_evidence_files(tmp_path), {})
        write_evidence_file(
            tmp_path / "b/hprc.ndjson",
            evidence_file_envelope(
                source=EvidenceFileSource(repository="hprc", dataset="R2"),
                source_type=SOURCE_PUBLISHED_VALUE,
                target=EvidenceTarget(system="hprc", dataset="R2"),
            ),
            [],
        )
        with pytest.raises(ValueError, match="hprc's published source is not declared"):
            require_one_published_source(report_evidence_files(tmp_path), {})

    def test_two_current_published_files_for_one_dataset_are_refused_naming_both(self, tmp_path):
        """Acceptance criterion 3: two files, both the declared table, one dataset."""
        first = self._published(tmp_path, "a/anvil_file.ndjson")
        second = self._published(tmp_path, "b/anvil_file.ndjson")
        with pytest.raises(ValueError) as exc:
            require_one_published_source(report_evidence_files(tmp_path), PUBLISHED_TABLES)
        assert str(first) in str(exc.value) and str(second) in str(exc.value)
        assert "exactly one published source" in str(exc.value)

    def test_two_catalog_versions_of_one_dataset_are_both_current_and_both_allowed(self, tmp_path):
        """`discover` keeps the newest generation per version, so an anvil15 and an anvil16
        generation are both current; which one the run's catalog is, is not decided here."""
        self._published(tmp_path, "anvil15/anvil_file.ndjson", version="anvil15")
        self._published(tmp_path, "anvil16/anvil_file.ndjson", version="anvil16")
        require_one_published_source(report_evidence_files(tmp_path), PUBLISHED_TABLES)

    def test_submitter_files_and_unreadable_ones_are_not_judged(self, tmp_path):
        write_evidence_file(tmp_path / "a/hifi.ndjson", evidence_file_envelope(), [])
        write_evidence_file(tmp_path / "b/hifi.ndjson", evidence_file_envelope(), [])
        (tmp_path / "c").mkdir()
        (tmp_path / "c" / "broken.ndjson").write_text("{not json\n")
        require_one_published_source(report_evidence_files(tmp_path), PUBLISHED_TABLES)
