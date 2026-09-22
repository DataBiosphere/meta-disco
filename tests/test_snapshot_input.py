"""The canonical input shape and its two readers (issue #499): a snapshot's tables
read in place through a fake BigQuery client, or through the Azul verbatim manifest,
and the records derived from either.

One test per acceptance criterion on the issue, in the issue's order, plus the
refusals the derivation makes. All offline: the direct reader runs against
``tests.tdr_fixtures.FakeClient``; the two parity checks over prod's manifests
read ``data/anvil/manifest/anvil15/`` and skip where it is absent, as the
evidence-importer tests do. Their comparison side is derived from the compact
manifests through the reader the downloader uses, so they compare the two
derivations rather than a derivation against a file that may be stale.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import validate_metadata

from meta_disco import snapshot_input as si
from meta_disco import tdr
from meta_disco.azul_manifest import (
    FORMAT_COMPACT,
    FORMAT_VERBATIM,
    INPUT_SOURCE_AZUL_COMPACT,
    INPUT_SOURCE_TDR_DIRECT,
    iter_compact_records,
    manifest_path,
    metadata_block,
    write_input_files,
)
from tests.metadata_fixtures import valid_record
from tests.tdr_fixtures import DisagreeingClient, FakeClient

SNAPSHOT = tdr.Snapshot(project="datarepo-ce3811eb", name="ANVIL_1000G_2019_Dev")
REAL_MANIFESTS = Path("data/anvil/manifest/anvil15")
CATALOG = "anvil15"

# The six per-file fields the issue's parity criteria compare: what the compact join
# and the snapshot's `anvil_file` row both carry for a file, under the record's names.
COMPARED_FIELDS = ("file_name", "file_format", "file_size", "file_md5sum", "drs_uri", "is_supplementary")

DATASET_ROW: dict[str, Any] = {
    "datarepo_row_id": "5671c9ff-1045-4467-88d6-7e56ca77668c",
    "dataset_id": "8a756d17-c54c-3b33-312b-c767552a8516",
    "title": "ANVIL_1000G_2019_Dev",
    "consent_group": ["NRES"],
    "data_modality": ["whole genome"],
}


def file_row(i: int, **overrides) -> dict[str, Any]:
    """One ``anvil_file`` row as TDR holds it: every column, `file_path` included."""
    row = {
        "datarepo_row_id": f"row-{i}",
        "file_id": f"file-{i}",
        "file_name": f"NA{i:05d}.cram",
        "file_format": ".cram",
        "file_size": 1000 + i,
        "file_md5sum": f"{i:032x}",
        "file_ref": f"drs://drs.anv0:v2_file-{i}",
        "file_path": f"CCDG_13607/Sample_NA{i:05d}/NA{i:05d}.cram",
        "is_supplementary": False,
        "data_modality": [],
        "reference_assembly": [],
        "source_datarepo_row_ids": [f"file_inventory:{i}"],
    }
    row.update(overrides)
    return row


FILE_ROWS = [file_row(1), file_row(2, data_modality=["whole genome", ""], is_supplementary=True), file_row(3)]
TABLES = {"anvil_dataset": [DATASET_ROW], "anvil_file": FILE_ROWS, "anvil_donor": []}


def verbatim_manifest(path: Path, tables: dict[str, list[dict]]) -> Path:
    """Write the tables as Azul's verbatim manifest would carry them: `version` on
    every entity, `drs_uri` beside `file_ref` on `anvil_file`, `file_path` dropped,
    and Azul's own `duos_dataset_registration` entity."""
    lines = []
    for table, rows in tables.items():
        for row in rows:
            value = {k: v for k, v in row.items() if k != "file_path"}
            value["version"] = "2022-06-01T00:00:00.000000Z"
            if table == "anvil_file":
                value["drs_uri"] = row["file_ref"]
            lines.append(json.dumps({"value": value, "type": table}))
    lines.append(json.dumps({"value": {"duos_id": "DUOS-1", "version": "v"}, "type": "duos_dataset_registration"}))
    path.write_text("\n".join(lines) + "\n")
    return path


@pytest.fixture
def client():
    return FakeClient(TABLES)


@pytest.fixture
def verbatim(tmp_path):
    return verbatim_manifest(tmp_path / "ds.verbatim.jsonl", TABLES)


class TestDirectRead:
    def test_each_file_row_yields_one_record_in_the_contracts_names(self, client):
        # AC 1: the row's own values under the record's names, `drs_uri` from `file_ref`,
        # the dataset's title from the one `anvil_dataset` row — and no `entry_id`.
        records = list(si.derive_records(si.TdrDirect(client, SNAPSHOT)))
        assert len(records) == 3
        for record, row in zip(records, FILE_ROWS, strict=True):
            assert record["drs_uri"] == row["file_ref"]
            for field in ("file_id", "file_name", "file_format", "file_size", "file_md5sum", "is_supplementary"):
                assert record[field] == row[field]
            assert record["dataset_title"] == DATASET_ROW["title"]
            assert record["dataset_id"] == DATASET_ROW["dataset_id"]
            assert "entry_id" not in record
        # The published lists under the compact path's rule: empty is None, and an
        # empty element is dropped.
        assert records[0]["data_modality"] is None
        assert records[1]["data_modality"] == ["whole genome"]

    def test_file_path_is_kept_on_the_record(self, client):
        # AC 2: the one column Azul's manifests drop reaches the record.
        [first, *_] = si.derive_records(si.TdrDirect(client, SNAPSHOT))
        assert first["file_path"] == FILE_ROWS[0]["file_path"]

    def test_a_count_that_disagrees_with_the_stream_fails_naming_the_table_and_both_counts(self):
        # AC 4: raised after the last row, from the query layer's own check.
        client = DisagreeingClient(TABLES, count=99, table="anvil_file")
        records = si.derive_records(si.TdrDirect(client, SNAPSHOT))
        with pytest.raises(tdr.RowCountMismatch, match=r"anvil_file: streamed 3 row\(s\) but COUNT\(\*\) said 99"):
            list(records)

    def test_a_snapshot_without_the_file_table_fails_before_any_record_or_query(self):
        # AC 5: refused at the call, naming the missing table; no COUNT(*) is billed.
        client = FakeClient({"anvil_dataset": [DATASET_ROW], "anvil_donor": []})
        with pytest.raises(
            ValueError, match=r"snapshot has no anvil_file table; it lists \['anvil_dataset', 'anvil_donor'\]"
        ):
            si.derive_records(si.TdrDirect(client, SNAPSHOT))
        assert client.queries == []

    def test_rows_are_consumed_one_at_a_time(self, client):
        # AC 6: after the first record, the file table's result has handed out one row.
        records = si.derive_records(si.TdrDirect(client, SNAPSHOT))
        next(records)
        file_stream = client.results[-1]
        assert client.queries[-1] == "SELECT * FROM `datarepo-ce3811eb.ANVIL_1000G_2019_Dev.anvil_file`"
        assert file_stream.pulled == 1
        assert len(list(records)) == 2
        assert file_stream.pulled == 3

    def test_every_streamed_table_is_checked_against_its_count(self, client):
        list(si.derive_records(si.TdrDirect(client, SNAPSHOT)))
        counts = [q for q in client.queries if q.startswith("SELECT COUNT(*)")]
        assert [q.rsplit(".", 1)[1].rstrip("`") for q in counts] == ["anvil_dataset", "anvil_file"]


class TestTheGate:
    def test_a_tdr_sourced_input_with_no_entry_id_passes(self, tmp_path, client, capsys):
        # AC 3, first half: the derived input on disk, through the gate as a run would.
        entries = {DATASET_ROW["title"]: {"file_count": 3, "source_id": None, "source_spec": None}}
        block = metadata_block("anvil", entries, datetime(2026, 9, 22), INPUT_SOURCE_TDR_DIRECT)
        n = write_input_files(tmp_path, block, si.derive_records(si.TdrDirect(client, SNAPSHOT)))
        assert n == 3
        written = json.loads((tmp_path / "anvil_files_metadata.json").read_text())
        assert written["metadata"]["input_source"] == "tdr-direct"
        assert all("entry_id" not in record for record in written["files"])
        assert validate_metadata.main(["-i", str(tmp_path / "anvil_files_metadata.json")]) == 0
        assert "OK — no problems." in capsys.readouterr().out

    def test_a_compact_sourced_record_without_entry_id_passes_too(self, tmp_path, capsys):
        # AC 3, second half, as decided on the issue: `entry_id` is required of no
        # source. It is Azul's per-index id, and nothing keys on it (#446).
        record = valid_record()
        del record["entry_id"]
        envelope = {"repository": "anvil", "input_source": INPUT_SOURCE_AZUL_COMPACT}
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"metadata": envelope, "files": [record]}))
        assert validate_metadata.main(["-i", str(path)]) == 0
        assert "OK — no problems." in capsys.readouterr().out


class TestVerbatimAdapter:
    def test_the_tables_come_out_in_the_snapshots_shape(self, verbatim):
        # AC 7: Azul's three additions are gone; nothing else is. `anvil_donor` has no
        # rows, so the manifest has no line for it and the adapter cannot list it.
        adapter = si.AzulVerbatim(verbatim)
        assert adapter.tables() == ["anvil_dataset", "anvil_file"]
        for table in adapter.tables():
            for row in adapter.rows(table):
                assert "version" not in row
        files = list(adapter.rows("anvil_file"))
        assert all("drs_uri" not in row for row in files)
        assert [row["file_ref"] for row in files] == [row["file_ref"] for row in FILE_ROWS]
        assert list(adapter.rows("anvil_dataset")) == [DATASET_ROW]
        with pytest.raises(ValueError, match="'duos_dataset_registration' is an entity Azul adds"):
            adapter.rows("duos_dataset_registration")

    def test_the_listing_is_read_once_and_a_type_not_at_the_lines_end_is_still_read(self, tmp_path):
        path = tmp_path / "odd.verbatim.jsonl"
        path.write_text(
            json.dumps({"type": "anvil_dataset", "value": DATASET_ROW})
            + "\n\n"
            + json.dumps({"value": {}, "type": "x"})
            + "\n"
        )
        adapter = si.AzulVerbatim(path)
        assert adapter.tables() == ["anvil_dataset", "x"]
        path.unlink()
        assert adapter.tables() == ["anvil_dataset", "x"]  # kept, not re-scanned

    def test_a_line_that_is_not_an_entity_is_refused_naming_the_line(self, tmp_path):
        path = tmp_path / "bad.verbatim.jsonl"
        path.write_text(json.dumps({"value": {}, "type": "a"}) + "\n" + "{not json\n")
        with pytest.raises(ValueError, match=r"bad\.verbatim\.jsonl line 2: not a verbatim entity"):
            si.AzulVerbatim(path).tables()

    def test_both_readers_derive_the_same_records_but_for_file_path(self, client, verbatim):
        # AC 10: the same snapshot through both readers.
        direct = list(si.derive_records(si.TdrDirect(client, SNAPSHOT)))
        adapted = list(si.derive_records(si.AzulVerbatim(verbatim)))
        assert all("file_path" not in record for record in adapted)
        assert [{k: v for k, v in record.items() if k != "file_path"} for record in direct] == adapted


class TestDerivationRefusals:
    @pytest.mark.parametrize("dataset_rows", [[], [DATASET_ROW, DATASET_ROW]], ids=["none", "two"])
    def test_other_than_one_dataset_row_is_refused_before_any_record(self, dataset_rows):
        client = FakeClient({"anvil_dataset": dataset_rows, "anvil_file": FILE_ROWS})
        with pytest.raises(
            ValueError, match=f"anvil_dataset holds {len(dataset_rows)} rows; a snapshot is one dataset"
        ):
            si.derive_records(si.TdrDirect(client, SNAPSHOT))
        assert not any(q.startswith("SELECT * FROM") and q.endswith("anvil_file`") for q in client.queries)

    def test_a_row_lacking_a_column_the_record_needs_is_refused_naming_it(self):
        row = {k: v for k, v in file_row(1).items() if k != "file_ref"}
        with pytest.raises(ValueError, match="cannot map an anvil_file row to a record: no 'file_ref' column"):
            si.record_from_file_row(row, DATASET_ROW)

    def test_a_null_value_is_transcribed_not_refused(self):
        # A null md5 stays null: the load path excludes it (#376), the way the compact
        # path's empty cell is excluded, and this is not the place to decide that.
        record = si.record_from_file_row(file_row(1, file_md5sum=None), DATASET_ROW)
        assert record["file_md5sum"] is None


def _compact_side(datasets: list[str]) -> dict[str, tuple]:
    side = {}
    for dataset in datasets:
        for record in iter_compact_records(
            manifest_path(REAL_MANIFESTS.parent.parent, CATALOG, dataset, FORMAT_COMPACT)
        ):
            side[record["file_id"]] = tuple(record[f] for f in COMPARED_FIELDS)
    return side


def _adapted_side(datasets: list[str]) -> dict[str, tuple]:
    side = {}
    for dataset in datasets:
        path = manifest_path(REAL_MANIFESTS.parent.parent, CATALOG, dataset, FORMAT_VERBATIM)
        for record in si.derive_records(si.AzulVerbatim(path)):
            assert record["file_id"] not in side, f"{dataset}: {record['file_id']} derived twice"
            side[record["file_id"]] = tuple(record[f] for f in COMPARED_FIELDS)
    return side


@pytest.mark.skipif(not REAL_MANIFESTS.is_dir(), reason="anvil15 manifests are not on disk (make download)")
class TestParityWithTheCompactPath:
    def test_prod_1000g_derives_the_same_26016_records(self):
        # AC 8: one dataset, every compared field equal on every file.
        dataset = "ANVIL_1000G_high_coverage_2019"
        adapted, compact = _adapted_side([dataset]), _compact_side([dataset])
        assert len(adapted) == 26_016
        assert adapted == compact

    def test_all_twelve_prod_manifests_derive_todays_input(self):
        # AC 9: 708,088 records, the same `file_id`s, no compared field differing.
        # Measured 2026-09-21 at 708,088 of 708,088 with zero differences; a failure
        # here is a regression.
        datasets = sorted(p.name.removesuffix(".compact.tsv") for p in REAL_MANIFESTS.glob("*.compact.tsv"))
        assert len(datasets) == 12
        adapted, compact = _adapted_side(datasets), _compact_side(datasets)
        assert len(adapted) == 708_088
        assert set(adapted) == set(compact)
        differing = [file_id for file_id, fields in adapted.items() if compact[file_id] != fields]
        assert differing == []
