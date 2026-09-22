"""The TDR BigQuery layer (issue #498): list, count and stream a snapshot's tables
against a fake client, and the layer importing without the client library.

One test per acceptance criterion on the issue, plus the stream's row-count
check and the probe script's report against the same fake. That the package
and this module import without the extra is exercised by this file's own import
lines: the dev environment carries no `google` package (CI syncs the same lock,
without extras)."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from meta_disco import tdr

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import probe_tdr_snapshot as probe

SNAPSHOT = tdr.Snapshot(project="datarepo-ce3811eb", name="ANVIL_1000G_2019_Dev")


class FakeTableItem:
    def __init__(self, table_id: str):
        self.table_id = table_id


class FakeResult:
    """Rows handed out lazily, with a count of how many were pulled."""

    def __init__(self, rows):
        self._rows = rows
        self.pulled = 0

    def __iter__(self):
        for row in self._rows:
            self.pulled += 1
            yield row


class FakeClient:
    """Tables → rows. Records every query issued, its page size, and the result handed out."""

    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables
        self.queries: list[str] = []
        self.page_sizes: list = []
        self.results: list[FakeResult] = []
        self.listed: list[str] = []

    def list_tables(self, dataset: str):
        self.listed.append(dataset)
        return [FakeTableItem(name) for name in self._tables]

    def query_and_wait(self, query: str, page_size=None):
        self.queries.append(query)
        self.page_sizes.append(page_size)
        rows = self._tables[query.rsplit(".", 1)[1].rstrip("`")]
        result = FakeResult([{"n": len(rows)}] if query.startswith("SELECT COUNT(*)") else rows)
        self.results.append(result)
        return result


WHEN = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)

FILE_ROWS = [
    {"file_id": "f1", "file_name": "a.bam", "file_size": 10, "is_supplementary": False, "tags": ["x"], "t": WHEN},
    {"file_id": "f2", "file_name": "b.bam", "file_size": None, "is_supplementary": True, "tags": [], "t": WHEN},
    {"file_id": "f3", "file_name": "c.bam", "file_size": 30, "is_supplementary": False, "tags": ["y"], "t": None},
]


@pytest.fixture
def client():
    return FakeClient({"anvil_file": FILE_ROWS, "anvil_dataset": [{"title": "1000G"}], "anvil_donor": []})


class TestListTables:
    def test_every_table_is_named_an_empty_one_included(self, client):
        assert tdr.list_tables(client, SNAPSHOT) == ["anvil_file", "anvil_dataset", "anvil_donor"]
        assert client.listed == ["datarepo-ce3811eb.ANVIL_1000G_2019_Dev"]


class TestCountRows:
    def test_the_count_is_a_count_star_query_and_never_tables(self, client):
        assert tdr.count_rows(client, SNAPSHOT, "anvil_file") == 3
        assert tdr.count_rows(client, SNAPSHOT, "anvil_donor") == 0
        assert client.queries == [
            "SELECT COUNT(*) AS n FROM `datarepo-ce3811eb.ANVIL_1000G_2019_Dev.anvil_file`",
            "SELECT COUNT(*) AS n FROM `datarepo-ce3811eb.ANVIL_1000G_2019_Dev.anvil_donor`",
        ]
        assert not any("__TABLES__" in q for q in client.queries)


class TestIterRows:
    def test_rows_come_one_at_a_time_under_tdr_column_names(self, client):
        rows = tdr.iter_rows(client, SNAPSHOT, "anvil_file")
        first = next(rows)
        # One pulled so far: the table was not fetched whole before the first row.
        (result,) = client.results
        assert result.pulled == 1
        assert client.page_sizes == [tdr.PAGE_SIZE]
        assert client.queries == ["SELECT * FROM `datarepo-ce3811eb.ANVIL_1000G_2019_Dev.anvil_file`"]
        # The client's own types, untouched: list, None, datetime, bool.
        assert first == FILE_ROWS[0]
        assert list(rows) == FILE_ROWS[1:]
        assert result.pulled == 3

    def test_a_row_is_a_fresh_dict_not_the_client_object(self, client):
        rows = list(tdr.iter_rows(client, SNAPSHOT, "anvil_file"))
        assert all(row is not source for row, source in zip(rows, FILE_ROWS, strict=True))

    def test_a_stream_that_disagrees_with_its_expected_count_raises_after_the_last_row(self, client):
        rows = tdr.iter_rows(client, SNAPSHOT, "anvil_file", expect=99)
        assert next(rows) == FILE_ROWS[0]
        with pytest.raises(tdr.RowCountMismatch, match=r"anvil_file: streamed 3 row\(s\) but COUNT\(\*\) said 99"):
            list(rows)
        assert list(tdr.iter_rows(client, SNAPSHOT, "anvil_file", expect=3)) == FILE_ROWS

    def test_a_name_that_is_not_an_identifier_is_refused_before_any_query(self, client):
        with pytest.raises(ValueError, match="table name"):
            tdr.iter_rows(client, SNAPSHOT, "anvil_file` UNION ALL SELECT * FROM `x")  # at the call, not the first row
        with pytest.raises(ValueError, match="snapshot name"):
            tdr.count_rows(client, tdr.Snapshot(project="p", name="a.b"), "anvil_file")
        assert client.queries == []


class TestImportWithoutTheExtra:
    def test_only_a_live_client_needs_the_client_library(self, monkeypatch):
        # A None entry in sys.modules makes `from google.cloud import bigquery`
        # raise ImportError — the runtime environment, where the extra is absent.
        monkeypatch.setitem(sys.modules, "google", None)
        monkeypatch.setitem(sys.modules, "google.cloud", None)
        with pytest.raises(ImportError, match="uv sync --extra tdr"):
            tdr.default_client()


class TestProbeScript:
    def test_the_probe_reports_each_table_and_the_streamed_one(self, client):
        lines: list[str] = []
        assert probe.probe(client, SNAPSHOT, "anvil_file", log=lines.append) == 0
        report = "\n".join(lines)
        assert "3 table(s) listed" in report
        assert "anvil_file: 3 row(s)" in report
        assert "anvil_donor: 0 row(s)" in report
        assert "3 row(s) streamed" in report
        assert "columns: file_id, file_name, file_size, is_supplementary, tags, t" in report
        # No cell value reaches the report.
        assert "a.bam" not in report

    def test_a_table_not_in_the_snapshot_is_reported_and_fails(self, client):
        lines: list[str] = []
        assert probe.probe(client, SNAPSHOT, "anvil_nope", log=lines.append) == 1
        assert "'anvil_nope' is not in the snapshot" in lines[-1]
        assert client.queries == []  # refused before any COUNT(*) is billed

    def test_a_row_count_mismatch_is_reported_and_fails(self, client):
        class Disagreeing(FakeClient):
            def query_and_wait(self, query, page_size=None):
                result = super().query_and_wait(query, page_size)
                if query.startswith("SELECT COUNT(*)"):
                    result._rows = [{"n": 99}]
                return result

        lines: list[str] = []
        assert probe.probe(Disagreeing({"anvil_file": FILE_ROWS}), SNAPSHOT, "anvil_file", log=lines.append) == 1
        assert "anvil_file: streamed 3 row(s) but COUNT(*) said 99" in lines[-1]

    def test_arguments(self):
        args = probe.parse_args(["--project", "datarepo-x", "--snapshot", "S"])
        assert (args.project, args.snapshot, args.table, args.billing_project) == (
            "datarepo-x",
            "S",
            "anvil_file",
            None,
        )
