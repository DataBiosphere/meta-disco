"""The deployment and the input source as named choices (issue #500).

One test class per acceptance criterion of #500, in its order, plus the refusals
the plan added: a compact manifest naming another snapshot than the declared one, a
snapshot holding another dataset than the declared one, and a catalog dataset the
deployment does not declare. Offline except the one marked ``network``.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime
from pathlib import Path

import download_anvil_manifest as dl
import pytest
import validate_metadata

from meta_disco import azul_manifest as am
from meta_disco import tdr
from meta_disco.deployments import DEFAULT_DEPLOYMENT, DEPLOYMENTS, DEV, PROD, Deployment
from meta_disco.pipeline import load_envelope, load_records
from tests.tdr_fixtures import FakeClient, table_of
from tests.test_azul_manifest import (
    SERVICE,
    SNAPSHOT,
    SOURCE_ID,
    FakeSession,
    compact_payload,
    entry,
    no_sleep,
)
from tests.test_azul_manifest import deployment as fixture_deployment
from tests.test_snapshot_input import DATASET_ROW, file_row, verbatim_manifest

COMPACT, VERBATIM, DIRECT = am.INPUT_SOURCE_AZUL_COMPACT, am.INPUT_SOURCE_AZUL_VERBATIM, am.INPUT_SOURCE_TDR_DIRECT


def tables(title: str, n: int) -> dict[str, list[dict]]:
    """A snapshot of dataset ``title`` holding ``n`` files, in TDR's column names."""
    return {"anvil_dataset": [{**DATASET_ROW, "title": title}], "anvil_file": [file_row(i) for i in range(n)]}


def verbatim_bytes(tmp_path: Path, title: str, n: int) -> bytes:
    """The verbatim manifest Azul would serve for ``tables(title, n)``."""
    return verbatim_manifest(tmp_path / f"{title}.served.jsonl", tables(title, n)).read_bytes()


def session_for(tmp_path: Path, counts: dict[str, int], service: str = SERVICE) -> FakeSession:
    """A catalog at ``service`` listing ``counts``, serving both manifests of each dataset."""
    payloads = {}
    for title, n in counts.items():
        payloads[(title, am.FORMAT_COMPACT)] = compact_payload(title, n)
        payloads[(title, am.FORMAT_VERBATIM)] = verbatim_bytes(tmp_path, title, n)
    return FakeSession(dict(counts), payloads, service=service)


def download(dep: Deployment, source: str, session: FakeSession) -> int:
    return dl.download(dep, source, None, force=False, session=session, sleep=no_sleep)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def envelope(dep: Deployment) -> dict:
    return load_envelope(dep.input_file)


def no_network(monkeypatch) -> None:
    """Replace every way a run could reach the outside with a call that fails the test."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("an unknown name must be refused before any request or query")

    monkeypatch.setattr(dl.requests, "Session", refuse)
    monkeypatch.setattr(dl.tdr, "default_client", refuse)


class TestTheDefaultIsTodaysBehaviour:
    """AC 1: nothing named means Azul's manifests from prod, prod's paths, prod's input."""

    def test_no_name_means_prod_through_the_compact_manifest(self):
        args = dl.parse_args([])
        assert (args.deployment, args.input_source) == ("prod", COMPACT) == (DEFAULT_DEPLOYMENT, COMPACT)

    def test_prod_is_the_service_catalog_and_root_the_download_used(self):
        # The service `azul_manifest.API_URL` named and the catalog the Makefile's
        # `CATALOG ?=` pinned before #500. The root moved into prod's own directory.
        assert PROD.service == "https://service.explore.anvilproject.org"
        assert PROD.catalog == "anvil15"
        assert PROD.input_file == Path("data/anvil/prod/anvil_files_metadata.json")

    def test_the_gate_checks_prods_input_when_no_deployment_is_named(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert validate_metadata.main([]) == 2
        assert f"Input not found: {PROD.input_file}" in capsys.readouterr().out

    def test_a_compact_download_writes_the_records_it_always_did(self, tmp_path):
        # The records are the compact join's, row for row, whatever the envelope gained.
        dep = fixture_deployment(tmp_path)
        assert download(dep, COMPACT, session_for(tmp_path, {"ds": 2})) == 0
        expected = list(am.iter_compact_records(am.manifest_path(tmp_path, "anvil15", "ds", am.FORMAT_COMPACT)))
        assert load_records(dep.input_file) == expected == load_records(dep.input_ndjson)
        assert [r["entry_id"] for r in expected] == ["doc-0", "doc-1"]


class TestAnUnknownNameIsRefusedFirst:
    """AC 2: an unknown deployment or input source fails before any request, query or write."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["--deployment", "staging"],
            ["--input-source", "azul-full"],
            ["--deployment", "dev", "--input-source", "tdr"],
        ],
    )
    def test_the_download_refuses_it_before_touching_anything(self, argv, tmp_path, monkeypatch, capsys):
        no_network(monkeypatch)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc:
            dl.main(argv)
        assert exc.value.code == 2
        assert "invalid choice" in capsys.readouterr().err
        assert list(tmp_path.iterdir()) == []

    def test_the_gate_refuses_it(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc:
            validate_metadata.main(["--deployment", "staging"])
        assert exc.value.code == 2
        assert "invalid choice" in capsys.readouterr().err


class TestADevInputLeavesProdsAlone:
    """AC 3: deriving dev's input changes no byte of prod's, and lands under dev's own root."""

    def test_the_two_roots_are_disjoint(self):
        assert PROD.input_root != DEV.input_root
        assert PROD.input_root not in DEV.input_root.parents and DEV.input_root not in PROD.input_root.parents

    def test_deriving_dev_changes_no_byte_of_prods_input(self, tmp_path):
        anvil = tmp_path / "data" / "anvil"
        prod = fixture_deployment(anvil / "prod", ["ds"], "anvil15")
        dev_snapshot = tdr.Snapshot("datarepo-dev-e53e74aa", "ANVIL_DEV")
        dev = fixture_deployment(anvil / "dev", ["dev_ds"], "anvil", dev_snapshot)
        assert download(prod, COMPACT, session_for(tmp_path, {"ds": 2})) == 0
        prod_files = sorted(p for p in prod.input_root.rglob("*") if p.is_file())
        before = {p: digest(p) for p in prod_files}
        assert download(dev, VERBATIM, session_for(tmp_path, {"dev_ds": 3})) == 0
        assert direct_derive(dev, tables("dev_ds", 2)) == 0
        assert sorted(p for p in prod.input_root.rglob("*") if p.is_file()) == prod_files
        assert {p: digest(p) for p in prod_files} == before
        assert dev.input_file.is_file() and dev.input_root == anvil / "dev"
        assert (dev.input_root / "manifest" / "anvil").is_dir()


def direct_derive(dep: Deployment, snapshot_tables: dict[str, list[dict]]) -> int:
    return dl.derive_direct(dep, FakeClient(snapshot_tables))


class TestTheEnvelopeNamesTheChoice:
    """AC 4: the envelope names the input source, the deployment, and each dataset's
    TDR data project and snapshot; an Azul-sourced one still names `api_url` and `catalog`."""

    @pytest.mark.parametrize("source", [COMPACT, VERBATIM])
    def test_an_azul_sourced_envelope(self, source, tmp_path):
        dep = fixture_deployment(tmp_path)
        assert download(dep, source, session_for(tmp_path, {"ds": 2})) == 0
        block = envelope(dep)
        assert (block["input_source"], block["deployment"]) == (source, "test")
        assert (block["api_url"], block["catalog"], block["source"]) == (
            am.manifest_url(SERVICE),
            "anvil15",
            "manifest",
        )
        # The compact manifest names the source's Azul uuid; the verbatim one does not.
        assert block["datasets"] == {"ds": entry(2, SOURCE_ID if source == COMPACT else None)}
        assert (block["datasets"]["ds"]["tdr_project"], block["datasets"]["ds"]["snapshot"]) == (
            SNAPSHOT.project,
            SNAPSHOT.name,
        )

    def test_a_directly_read_envelope(self, tmp_path):
        dep = fixture_deployment(tmp_path)
        assert direct_derive(dep, tables("ds", 3)) == 0
        block = envelope(dep)
        assert (block["input_source"], block["deployment"], block["catalog"]) == (DIRECT, "test", "anvil15")
        assert (block["api_url"], block["source"]) == (None, None)
        assert block["datasets"] == {"ds": entry(3, None)}


class TestTheVerbatimKind:
    def test_it_fetches_the_verbatim_manifest_only_and_derives_through_the_adapter(self, tmp_path):
        dep = fixture_deployment(tmp_path)
        session = session_for(tmp_path, {"ds": 2})
        assert download(dep, VERBATIM, session) == 0
        formats = [params["format"] for method, _, params in session.calls if method == "PUT" and params]
        assert formats == [am.FORMAT_VERBATIM]
        assert not am.manifest_path(tmp_path, "anvil15", "ds", am.FORMAT_COMPACT).exists()
        records = load_records(dep.input_file)
        assert [r["file_id"] for r in records] == ["file-0", "file-1"]
        assert all("entry_id" not in r and "file_path" not in r for r in records)

    def test_a_manifest_holding_another_dataset_is_refused_and_writes_no_input(self, tmp_path, capsys):
        session = session_for(tmp_path, {"ds": 2})
        session.payloads[("ds", am.FORMAT_VERBATIM)] = verbatim_bytes(tmp_path, "other", 2)
        dep = fixture_deployment(tmp_path)
        assert download(dep, VERBATIM, session) == 1
        assert "expected dataset 'ds', but the snapshot holds 'other'" in capsys.readouterr().err
        assert not dep.input_file.exists()


class TestDevThroughTheVerbatimManifest:
    """AC 5: dev's verbatim pull asks dev's service for 1000G_Dev's verbatim manifest
    only, and the rows on disk match what the files facet reports. The offline half
    pins the requests; the network half checks the count against the live service."""

    def test_the_requests_name_devs_service_and_its_one_dataset_only(self, tmp_path):
        dev = dataclasses.replace(DEV, input_root=tmp_path)
        title = "ANVIL_1000G_2019_Dev"
        session = session_for(tmp_path, {title: 3, "ANVIL_CMG_Sample_1": 2}, service=DEV.service)
        assert download(dev, VERBATIM, session) == 0
        puts = [(url, params) for method, url, params in session.calls if method == "PUT"]
        assert puts == [
            (
                am.manifest_url(DEV.service),
                {"catalog": "anvil", "format": am.FORMAT_VERBATIM, "filters": am.manifest_filters(title)},
            )
        ]

    @pytest.mark.network
    def test_the_live_pull_matches_the_files_facet(self, tmp_path):
        dev = dataclasses.replace(DEV, input_root=tmp_path)
        assert dl.download(dev, VERBATIM, None, force=False, pause=0) == 0
        sidecar = am.load_sidecar(tmp_path, "anvil")["datasets"]
        assert list(sidecar) == ["ANVIL_1000G_2019_Dev"]
        stored = sidecar["ANVIL_1000G_2019_Dev"]
        assert stored[am.FORMAT_VERBATIM]["rows"] == stored["file_count"] == 26_016
        assert not am.manifest_path(tmp_path, "anvil", "ANVIL_1000G_2019_Dev", am.FORMAT_COMPACT).exists()
        assert len(load_records(dev.input_ndjson)) == 26_016


class TestDevReadInPlace:
    """AC 6: dev's tdr-direct derivation queries dev's one snapshot only and writes
    under dev's root with the envelope of AC 4. The live derivation is Dave's, in Terra."""

    def test_it_queries_devs_snapshot_only_and_writes_under_devs_root(self, tmp_path):
        dev = dataclasses.replace(DEV, input_root=tmp_path / "data" / "anvil" / "dev")
        (snapshot,) = DEV.snapshots.values()
        client = FakeClient(tables("ANVIL_1000G_2019_Dev", 3))
        assert dl.derive_direct(dev, client) == 0
        assert client.listed == [snapshot.dataset]
        assert all(snapshot.table_ref(table_of(query)) in query for query in client.queries)
        assert {table_of(query) for query in client.queries} == {"anvil_dataset", "anvil_file"}
        block = envelope(dev)
        assert (block["deployment"], block["input_source"], block["catalog"]) == ("dev", DIRECT, "anvil")
        assert block["datasets"] == {"ANVIL_1000G_2019_Dev": am.dataset_entry(3, snapshot)}
        assert [r["file_id"] for r in load_records(dev.input_file)] == ["file-0", "file-1", "file-2"]

    def test_a_snapshot_holding_another_dataset_is_refused_and_writes_nothing(self, tmp_path, capsys):
        dev = dataclasses.replace(DEV, input_root=tmp_path / "dev")
        assert dl.derive_direct(dev, FakeClient(tables("ANVIL_CMG_Sample_1", 2))) == 1
        assert "the snapshot holds 'ANVIL_CMG_Sample_1'" in capsys.readouterr().err
        assert not dev.input_file.exists()

    def test_a_snapshot_without_the_file_table_refuses_before_any_count(self, tmp_path, capsys):
        dev = dataclasses.replace(DEV, input_root=tmp_path / "dev")
        client = FakeClient({"anvil_dataset": [DATASET_ROW]})
        assert dl.derive_direct(dev, client) == 1
        assert "no anvil_file table" in capsys.readouterr().err
        assert not any(query.startswith("SELECT COUNT(*)") for query in client.queries)
        assert not dev.input_root.exists()

    def test_datasets_and_force_have_no_meaning_for_a_direct_read(self, monkeypatch, capsys):
        no_network(monkeypatch)
        assert dl.main(["--input-source", DIRECT, "--force"]) == 2
        assert "no meaning for tdr-direct" in capsys.readouterr().err


class TestTheDeclarationIsChecked:
    def test_a_compact_manifest_naming_another_snapshot_refuses_the_download(self, tmp_path, capsys):
        # Decision of 2026-09-22 on #500: refuse, naming both, rather than write the
        # manifest's snapshot and carry on.
        declared = tdr.Snapshot("datarepo-ce3811eb", "ANVIL_TEST_EARLIER")
        dep = fixture_deployment(tmp_path, snapshot=declared)
        assert download(dep, COMPACT, session_for(tmp_path, {"ds": 2})) == 1
        err = capsys.readouterr().err
        assert f"names snapshot {SNAPSHOT.source_spec}" in err and f"declares {declared.source_spec}" in err
        assert not dep.input_file.exists()

    def test_a_compact_manifest_naming_no_snapshot_refuses_the_download(self, tmp_path, capsys):
        # Decision of 2026-09-22 on #500: Azul writes the snapshot on every row, so none
        # at all cannot confirm the declaration, and writing it would claim it had.
        session = session_for(tmp_path, {"ds": 2})
        blank = session.payloads[("ds", am.FORMAT_COMPACT)].replace(SOURCE_ID.encode(), b"")
        session.payloads[("ds", am.FORMAT_COMPACT)] = blank.replace(SNAPSHOT.source_spec.encode(), b"")
        dep = fixture_deployment(tmp_path)
        assert download(dep, COMPACT, session) == 1
        assert "the compact manifest names no snapshot" in capsys.readouterr().err
        assert not dep.input_file.exists()

    def test_switching_to_compact_after_a_verbatim_pull_fetches_the_dataset_whole(self, tmp_path):
        # The verbatim manifest pulled under the old count is requested again with the
        # compact one, so both are judged against the one count stored for them.
        dep = fixture_deployment(tmp_path)
        assert download(dep, VERBATIM, session_for(tmp_path, {"ds": 2})) == 0
        session = session_for(tmp_path, {"ds": 3})
        assert download(dep, COMPACT, session) == 0
        formats = sorted(params["format"] for method, _, params in session.calls if method == "PUT" and params)
        assert formats == [am.FORMAT_COMPACT, am.FORMAT_VERBATIM]
        assert envelope(dep)["datasets"]["ds"]["file_count"] == 3

    def test_a_compact_manifest_left_behind_by_a_forced_verbatim_pull_is_fetched_again(self, tmp_path):
        # Compact pulled at 2, then a forced verbatim pull at 3 stores the new count; the
        # compact manifest on disk still holds 2 rows, so the next compact run requests
        # the dataset whole instead of failing parity until --force.
        dep = fixture_deployment(tmp_path)
        assert download(dep, COMPACT, session_for(tmp_path, {"ds": 2})) == 0
        grown = session_for(tmp_path, {"ds": 3})
        assert dl.download(dep, VERBATIM, None, force=True, session=grown, sleep=no_sleep) == 0
        session = session_for(tmp_path, {"ds": 3})
        assert download(dep, COMPACT, session) == 0
        formats = sorted(params["format"] for method, _, params in session.calls if method == "PUT" and params)
        assert formats == [am.FORMAT_COMPACT, am.FORMAT_VERBATIM]
        assert len(load_records(dep.input_ndjson)) == 3

    def test_manifests_that_agree_with_the_stored_count_are_not_fetched_again(self, tmp_path):
        dep = fixture_deployment(tmp_path)
        assert download(dep, COMPACT, session_for(tmp_path, {"ds": 2})) == 0
        session = session_for(tmp_path, {"ds": 2})
        assert download(dep, COMPACT, session) == 0
        assert not [c for c in session.calls if c[0] == "PUT"]

    def test_a_catalog_dataset_the_deployment_does_not_declare_is_skipped(self, tmp_path, capsys):
        dep = fixture_deployment(tmp_path, ["ds"])
        session = session_for(tmp_path, {"ds": 2, "placeholders": 50})
        assert download(dep, COMPACT, session) == 0
        assert "Not declared by the test deployment, skipped: placeholders (50 files)" in capsys.readouterr().out
        assert all(
            json.loads(p["filters"])["datasets.title"]["is"] == ["ds"]
            for _, _, p in session.calls
            if p and "filters" in p
        )
        assert list(envelope(dep)["datasets"]) == ["ds"]

    def test_a_declared_dataset_the_catalog_lacks_with_nothing_on_disk_is_refused(self, tmp_path, capsys):
        dep = fixture_deployment(tmp_path, ["ds", "gone"])
        assert download(dep, COMPACT, session_for(tmp_path, {"ds": 2})) == 1
        assert (
            "gone: no manifests on disk, and the catalog does not list it or could not be reached"
            in capsys.readouterr().err
        )
        assert not dep.input_file.exists()

    def test_only_an_azul_kind_downloads(self, tmp_path, capsys):
        assert download(fixture_deployment(tmp_path), DIRECT, FakeSession({}, {})) == 2
        assert "not an input source that downloads manifests" in capsys.readouterr().err


class TestTheDeclarations:
    def test_every_declared_snapshot_round_trips_through_its_spec(self):
        for dep in DEPLOYMENTS.values():
            for snapshot in dep.snapshots.values():
                assert tdr.Snapshot.from_source_spec(snapshot.source_spec) == snapshot

    @pytest.mark.parametrize(
        "spec",
        ["tdr:bigquery:gcp:project", "tdr:bigquery:azure:p:s", "tdr:bigquery:gcp:p:s:extra", "tdr:bigquery:gcp::s"],
    )
    def test_a_spec_of_another_shape_is_refused(self, spec):
        with pytest.raises(ValueError, match="not a TDR BigQuery source spec"):
            tdr.Snapshot.from_source_spec(spec)

    def test_dev_declares_1000g_dev_only(self):
        assert list(DEV.snapshots) == ["ANVIL_1000G_2019_Dev"]
        assert (DEV.service, DEV.catalog) == ("https://service.anvil.gi.ucsc.edu", "anvil")

    @pytest.mark.skipif(not PROD.input_file.is_file(), reason="prod's input is not on disk (make download)")
    def test_prods_declaration_is_the_snapshots_its_input_names(self):
        # The declaration was transcribed from this envelope; a re-derived input that
        # disagrees has been refused by the downloader, so this pins the transcription.
        metadata = load_envelope(PROD.input_file)
        named = {title: tdr.Snapshot.from_source_spec(e["source_spec"]) for title, e in metadata["datasets"].items()}
        assert named == dict(PROD.snapshots)
