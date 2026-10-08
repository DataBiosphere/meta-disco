"""The ENA importer (#606), on synthetic manifests and a faked portal: the md5 decides, a
name match alone writes nothing, a run's files are read by name, the response is kept and
re-imports offline."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from meta_disco import ena_evidence as ena
from meta_disco.models import SOURCE_EXTERNAL_GROUND_TRUTH
from meta_disco.source_evidence import discover, evidence_file_path, iter_evidence, read_envelope
from tests.manifest_fixtures import CATALOG, write_dataset

STAMP = "20261003T000000Z"
REQUESTED = datetime(2026, 10, 3, 7, 0, tzinfo=timezone.utc)


def fastq(file_id: str, name: str, md5: str | None) -> tuple[str, dict]:
    return "anvil_file", {"file_id": file_id, "file_name": name, "file_md5sum": md5}


def run(accession: str, files: dict[str, str], **fields: str) -> dict:
    """An ENA read_run row whose generated files are ``files`` (name -> md5), in order."""
    base = f"ftp.sra.ebi.ac.uk/vol1/fastq/{accession[:6]}/{accession}"
    return {
        "run_accession": accession,
        "fastq_ftp": ";".join(f"{base}/{name}" for name in files),
        "fastq_md5": ";".join(files.values()),
        "library_strategy": "WGS",
        "library_source": "GENOMIC",
        "instrument_platform": "ILLUMINA",
        "instrument_model": "Illumina NovaSeq 6000",
        "library_construction_protocol": "TruSeq DNA PCR-free",
        **fields,
    }


ROWS = [
    run("ERR000001", {"ERR000001_1.fastq.gz": "aa", "ERR000001_2.fastq.gz": "bb"}),
    # a paired run listing its unpaired file first: matched by name, not position
    run(
        "ERR000002",
        {"ERR000002.fastq.gz": "x0", "ERR000002_1.fastq.gz": "cc", "ERR000002_2.fastq.gz": "dd"},
        instrument_model="",
    ),
    run("ERR000003", {"ERR000003_1.fastq.gz": "ee"}),
]


def entities():
    return [
        fastq("t1", "ERR000001_1.fastq.gz", "AA"),  # md5 case differs only
        fastq("t2", "ERR000001_2.fastq.gz", "bb"),
        fastq("t3", "ERR000002_1.fastq.gz", "cc"),
        fastq("t4", "ERR000003_1.fastq.gz", "zz"),  # md5 differs
        fastq("t5", "ERR000003_2.fastq.gz", "ff"),  # not among the run's files
        fastq("t6", "ERR000004_1.fastq.gz", "gg"),  # no run
        fastq("t7", "ERR000001_1.fastq.gz.bak", "aa"),  # not ENA's name
        fastq("t8", "HG002_ERR000001_1.fastq.gz", "aa"),  # not ENA's name
        fastq("t10", "ERR1_1.fastq.gz", "aa"),  # too short for a run accession
        fastq("t9", "ERR000005_1.fastq.gz", None),  # no catalog md5
    ]


class FakePortal:
    def __init__(self, rows):
        self.rows = {r["run_accession"]: r for r in rows}
        self.asked: list[tuple[str, list[str]]] = []

    def __call__(self, catalog, dataset, accessions):
        self.asked.append((dataset, accessions))
        return ena.Response(catalog, dataset, REQUESTED, {a: self.rows[a] for a in accessions if a in self.rows})


@pytest.fixture
def imported(tmp_path):
    write_dataset(tmp_path / "m", "D", entities())
    write_dataset(tmp_path / "m", "Other", [fastq("o1", "sample.bam", "aa")])
    portal = FakePortal(ROWS)
    imports = ena.import_all(tmp_path / "m", CATALOG, tmp_path / "ev", portal, generation=STAMP)
    return imports, portal, tmp_path


def evidence(directory: Path) -> Path:
    return evidence_file_path(directory, ena.TABLE)


def lines(directory: Path) -> list[tuple[str, str, str, str | None]]:
    return [(e.target_key_value, e.field, e.raw_value, e.source.column) for e in iter_evidence(evidence(directory))]


def test_only_a_file_whose_md5_enas_equals_receives_lines(imported):
    (result,), _, _ = imported
    assert {key for key, *_ in lines(result.directory)} == {"t1", "t2", "t3"}
    assert result.outcomes == {"matched": 3, "md5_differs": 1, "not_in_run": 1, "no_run": 1, "no_catalog_md5": 1}


def test_a_matched_file_gets_each_mapped_field_verbatim_and_an_empty_one_is_skipped(imported):
    (result,), _, _ = imported
    by_file = [line for line in lines(result.directory) if line[0] == "t3"]
    assert by_file == [
        ("t3", "assay_type", "WGS", "library_strategy"),
        ("t3", "data_modality", "GENOMIC", "library_source"),
        ("t3", "platform", "ILLUMINA", "instrument_platform"),
    ]
    assert result.written == len(lines(result.directory)) == 11


def test_a_name_not_enas_or_a_file_without_an_md5_is_never_asked_for_and_a_dataset_without_one_is_skipped(imported):
    imports, portal, _ = imported
    assert [i.dataset for i in imports] == ["D"]
    assert portal.asked == [("D", ["ERR000001", "ERR000002", "ERR000003", "ERR000004"])]


@pytest.mark.parametrize("name", ["SRR1234567_1.fastq.gz", "DRR000001_2.fastq.gz", "ERR123456.fastq.gz"])
def test_a_name_as_ena_generates_it_is_enas(name):
    assert ena.GENERATED_FASTQ.match(name)


@pytest.mark.parametrize(
    "name", ["ERR12345_1.fastq.gz", "HG002_ERR123456_1.fastq.gz", "ERR123456_3.fastq.gz", "XRR123456_1.fastq.gz"]
)
def test_a_name_ena_does_not_generate_is_not_enas(name):
    assert not ena.GENERATED_FASTQ.match(name)


def test_the_envelope_names_ena_and_joins_on_file_id(imported):
    (result,), _, _ = imported
    envelope = read_envelope(evidence(result.directory))
    assert envelope.source.repository == ena.SOURCE
    assert envelope.source.table == ena.TABLE
    assert envelope.source_type == SOURCE_EXTERNAL_GROUND_TRUTH
    assert envelope.source_key == "run_accession"
    assert envelope.source_version == "2026-10-03"
    assert envelope.fetched_at == REQUESTED.isoformat()
    assert (envelope.target.system, envelope.target.dataset, envelope.target.version) == ("anvil", "D", CATALOG)
    assert envelope.target_key == "file_id"


def test_the_response_is_kept_beside_the_evidence_and_is_not_evidence(imported):
    (result,), _, tmp_path = imported
    assert result.directory == tmp_path / "ev" / ena.SOURCE / CATALOG / "D" / STAMP
    assert discover(tmp_path / "ev") == [evidence(result.directory)]
    stored = ena.load_response(result.directory / ena.RESPONSE_FILE)
    assert (stored.catalog, stored.dataset) == (CATALOG, "D")
    assert stored.requested_at == REQUESTED
    assert stored.rows["ERR000001"]["library_construction_protocol"] == "TruSeq DNA PCR-free"


def test_a_stored_response_reimports_the_same_lines_offline(imported):
    (result,), _, tmp_path = imported
    stored = ena.load_response(result.directory / ena.RESPONSE_FILE)
    (again,) = ena.import_all(
        tmp_path / "m", CATALOG, tmp_path / "ev", lambda _c, _d, _a: stored, ["D"], generation="20261004T000000Z"
    )
    assert lines(again.directory) == lines(result.directory)
    assert read_envelope(evidence(again.directory)) == read_envelope(evidence(result.directory))


def test_a_dataset_where_nothing_matches_fails_and_writes_nothing(tmp_path):
    write_dataset(tmp_path / "m", "D", [fastq("t4", "ERR000003_1.fastq.gz", "zz")])
    with pytest.raises(ValueError, match=r"D: no file named as ENA's matched ENA's md5 \(md5_differs 1\)"):
        ena.import_all(tmp_path / "m", CATALOG, tmp_path / "ev", FakePortal(ROWS), generation=STAMP)
    assert not (tmp_path / "ev").exists()


def test_a_dataset_that_cannot_be_read_fails_the_import_before_anything_is_written(tmp_path):
    write_dataset(tmp_path / "m", "D", entities())
    with pytest.raises(ValueError, match="Missing: not a dataset the anvil15 sidecar names"):
        ena.import_all(tmp_path / "m", CATALOG, tmp_path / "ev", FakePortal(ROWS), ["D", "Missing"], STAMP)
    assert not (tmp_path / "ev").exists()


class FakeSession:
    """Stands in for ``requests.Session``: records each POST and answers with the asked-for rows."""

    def __init__(self, rows, status=200):
        self.rows = {r["run_accession"]: r for r in rows}
        self.status = status
        self.posts: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, data, timeout):
        self.posts.append((url, data))
        asked = data["includeAccessions"].split(",")
        response = requests.Response()
        response.status_code = self.status
        response._content = json.dumps([self.rows[a] for a in asked if a in self.rows]).encode()
        return response


def test_fetch_runs_posts_batches_of_the_asked_runs_and_keys_the_rows(monkeypatch):
    accessions = [f"ERR{n:06d}" for n in range(1, ena.BATCH + 3)]
    session = FakeSession([run(a, {f"{a}_1.fastq.gz": "aa"}) for a in accessions[:3]])
    monkeypatch.setattr(ena.requests, "Session", lambda: session)
    response = ena.fetch_runs(CATALOG, "D", accessions)
    assert [len(data["includeAccessions"].split(",")) for _, data in session.posts] == [ena.BATCH, 2]
    url, data = session.posts[0]
    assert url == ena.PORTAL_SEARCH
    assert (data["result"], data["format"], data["limit"]) == ("read_run", "json", 0)
    assert data["fields"].split(",") == list(ena.FIELDS)
    assert (response.catalog, response.dataset) == (CATALOG, "D")
    assert sorted(response.rows) == accessions[:3]


def test_fetch_runs_raises_on_an_http_error(monkeypatch):
    monkeypatch.setattr(ena.requests, "Session", lambda: FakeSession([], status=500))
    with pytest.raises(requests.HTTPError):
        ena.fetch_runs(CATALOG, "D", ["ERR000001"])


def test_a_dataset_that_lost_its_enas_names_fails_while_its_old_generation_is_current(tmp_path):
    write_dataset(tmp_path / "m", "D", entities())
    ena.import_all(tmp_path / "m", CATALOG, tmp_path / "ev", FakePortal(ROWS), generation=STAMP)
    write_dataset(tmp_path / "m", "D", [fastq("o1", "sample.bam", "aa")])
    with pytest.raises(ValueError, match="D: no file named as ENA's, but an earlier ENA generation is current"):
        ena.import_all(tmp_path / "m", CATALOG, tmp_path / "ev", FakePortal(ROWS), generation="20261004T000000Z")
    assert not (tmp_path / "ev" / ena.SOURCE / CATALOG / "D" / "20261004T000000Z").exists()


def test_ena_returning_two_different_rows_for_one_run_is_refused():
    rows: dict[str, dict] = {}
    ena.add_row(rows, ROWS[0], "here")
    ena.add_row(rows, ROWS[0], "here")
    with pytest.raises(ValueError, match="two different rows for ERR000001"):
        ena.add_row(rows, {**ROWS[0], "instrument_model": "Illumina HiSeq 2000"}, "here")


def test_a_run_whose_file_and_md5_lists_differ_in_length_matches_no_file_and_is_counted(tmp_path):
    unpaired = run("ERR000001", {"ERR000001_1.fastq.gz": "aa", "ERR000001_2.fastq.gz": "bb"}, fastq_md5="aa")
    write_dataset(
        tmp_path / "m", "D", [fastq("t1", "ERR000001_1.fastq.gz", "aa"), fastq("t2", "ERR000002_1.fastq.gz", "cc")]
    )
    (result,) = ena.import_all(
        tmp_path / "m", CATALOG, tmp_path / "ev", FakePortal([unpaired, ROWS[1]]), generation=STAMP
    )
    assert result.outcomes == {"md5_unlisted": 1, "matched": 1}
    assert {key for key, *_ in lines(result.directory)} == {"t2"}


def test_matched_files_with_no_mapped_field_fail_and_write_nothing(tmp_path):
    empty = run("ERR000001", {"ERR000001_1.fastq.gz": "aa"}, **dict.fromkeys(ena.FIELD_SLOTS, ""))
    write_dataset(tmp_path / "m", "D", [fastq("t1", "ERR000001_1.fastq.gz", "aa")])
    with pytest.raises(ValueError, match="D: 1 matched files, but ENA states no mapped field for any"):
        ena.import_all(tmp_path / "m", CATALOG, tmp_path / "ev", FakePortal([empty]), generation=STAMP)
    assert not (tmp_path / "ev" / ena.SOURCE / CATALOG / "D" / STAMP).exists()


def test_a_response_for_another_catalog_is_refused(tmp_path):
    write_dataset(tmp_path / "m", "D", entities())
    stored = ena.Response("anvil14", "D", REQUESTED, {r["run_accession"]: r for r in ROWS})
    with pytest.raises(ValueError, match="anvil14/D cannot be imported as anvil15/D"):
        ena.import_all(tmp_path / "m", CATALOG, tmp_path / "ev", lambda _c, _d, _a: stored, generation=STAMP)
    assert not (tmp_path / "ev").exists()


def test_an_enas_name_with_no_file_id_is_refused_naming_its_line(tmp_path):
    no_id = ("anvil_file", {"file_name": "ERR000002_1.fastq.gz"})
    write_dataset(tmp_path / "m", "D", [fastq("t1", "ERR000001_1.fastq.gz", "aa"), no_id])
    with pytest.raises(ValueError, match=r"jsonl:2: anvil_file 'ERR000002_1.fastq.gz' has no file_id"):
        ena.import_all(tmp_path / "m", CATALOG, tmp_path / "ev", FakePortal(ROWS), generation=STAMP)
