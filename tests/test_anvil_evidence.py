"""The AnVIL evidence importer (#369): the map checked against the manifests with every
problem at once, transcription as the contract states it, provenance naming the value's
column, and an import that is a generation — on synthetic manifests small enough to
read, plus the bundled map against the real anvil15 manifests where they are on disk."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from meta_disco import anvil_evidence as ae
from meta_disco.azul_manifest import FORMAT_VERBATIM, load_sidecar, manifest_dir, manifest_path, save_sidecar
from meta_disco.models import JOIN_KEY_DRS_URI, SOURCE_REPOSITORY_METADATA
from meta_disco.slot_map import load_slot_map
from meta_disco.source_evidence import discover, is_generation, iter_evidence, read_envelope, unfinished_imports

CATALOG = "anvil15"
FETCHED = "2026-09-03T21:45:47.517283"
REAL_MANIFESTS = Path("data/anvil/manifest") / CATALOG


def drs(n: int) -> str:
    return f"drs://drs.anv0:v2_{n:08d}-0000-0000-0000-000000000000"


def write_dataset(root: Path, title: str, entities: list[tuple[str, dict]], fetched: str | None = FETCHED) -> None:
    """One dataset's verbatim manifest and its sidecar entry, in the layout the importer reads."""
    manifest_dir(root, CATALOG).mkdir(parents=True, exist_ok=True)
    manifest_path(root, CATALOG, title, FORMAT_VERBATIM).write_text(
        "".join(json.dumps({"value": value, "type": entity_type}) + "\n" for entity_type, value in entities)
    )
    sidecar = load_sidecar(root, CATALOG)
    entry: dict[str, Any] = {"file_count": sum(1 for t, _ in entities if t == "anvil_file")}
    if fetched is not None:
        entry[FORMAT_VERBATIM] = {"requested_at": fetched, "rows": entry["file_count"]}
    sidecar["datasets"][title] = entry
    save_sidecar(root, CATALOG, sidecar)


def anvil_file(n: int) -> tuple[str, dict]:
    return "anvil_file", {"file_id": f"f{n}", "file_name": f"f{n}.bam", "drs_uri": drs(n), "file_ref": drs(n)}


def slot_map(tmp_path: Path, text: str):
    path = tmp_path / "map.yaml"
    path.write_text(text)
    return load_slot_map(path)


HIFI_MAP = """
catalog: anvil15
datasets:
  D:
    hifi:
      path:
        platform:
          - {cell: platform}
          - {cell: instrument_model}
          - {table_name: hifi}
        data_modality:
          - {cell: library_source}
        assay_type:
          - {cell: library_source}
"""

HIFI_ROWS = [
    anvil_file(1),
    anvil_file(2),
    anvil_file(3),
    (
        "hifi",
        {
            "hifi_id": "a",
            "path": drs(1),
            "platform": "PACBIO_SMRT",
            "instrument_model": "Revio",
            "library_source": "GENOMIC",
        },
    ),
    ("hifi", {"hifi_id": "b", "path": drs(2), "platform": "", "instrument_model": None, "library_source": None}),
    (
        "hifi",
        {
            "hifi_id": "c",
            "path": "",
            "platform": "PACBIO_SMRT",
            "instrument_model": "Revio",
            "library_source": "GENOMIC",
        },
    ),
    (
        "hifi",
        {
            "hifi_id": "d",
            "path": drs(9),
            "platform": "PACBIO_SMRT",
            "instrument_model": "Revio",
            "library_source": "GENOMIC",
        },
    ),
]


def rows_of(path: Path) -> list[tuple[str, str, str, str | None]]:
    return [(e.field, e.target_key_value, e.raw_value, e.source.column) for e in iter_evidence(path)]


# --- check ---------------------------------------------------------------------


class TestCheck:
    def test_a_map_that_agrees_with_the_manifests_has_no_problems(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        assert ae.check(slot_map(tmp_path, HIFI_MAP), tmp_path, CATALOG) == []

    def test_every_problem_is_reported_at_once(self, tmp_path):
        write_dataset(tmp_path, "D", [anvil_file(1), ("hifi", {"path": drs(1), "platform": "x", "coverage": "10"})])
        text = """
catalog: anvil15
datasets:
  D:
    hifi:
      path:
        platform:
          - {cell: platform}
          - {cell: instrument_model}
      coverage:
        platform:
          - {cell: platform}
      nowhere:
        platform:
          - {cell: platform}
    ont:
      path:
        platform:
          - {cell: platform}
  E:
    t:
      c:
        platform:
          - {cell: p}
"""
        problems = ae.check(slot_map(tmp_path, text), tmp_path, CATALOG)
        assert problems == [
            "D/hifi/coverage: holds '10', not a DRS URI or a list of them — not a file-link column",
            "D/hifi/nowhere: no row carries this column",
            "D/hifi: cell 'instrument_model' is not a column of this table",
            "D/ont: no row of this type in the manifest",
            "E: not a dataset the anvil15 sidecar names",
        ]

    def test_a_named_dataset_whose_manifest_is_not_on_disk(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        manifest_path(tmp_path, CATALOG, "D", FORMAT_VERBATIM).unlink()
        (problem,) = ae.check(slot_map(tmp_path, HIFI_MAP), tmp_path, CATALOG)
        assert problem.startswith("D: no verbatim manifest at ")

    def test_a_cell_that_is_itself_a_file_link_column_is_a_problem(self, tmp_path):
        """A column is one kind, never two (contract 2.7): `cram` holds pointers, not a value."""
        write_dataset(tmp_path, "D", [anvil_file(1), anvil_file(2), ("sample", {"gvcf": drs(1), "cram": drs(2)})])
        text = "catalog: anvil15\ndatasets:\n  D:\n    sample:\n      gvcf:\n        reference_assembly:\n          - {cell: cram}\n"
        assert ae.check(slot_map(tmp_path, text), tmp_path, CATALOG) == [
            "D/sample: cell 'cram' holds DRS URIs — a file-link column, not a metadata value"
        ]

    def test_check_can_be_narrowed_to_the_datasets_an_import_will_touch(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        text = HIFI_MAP + "  E:\n    hifi:\n      path:\n        platform:\n          - {cell: platform}\n"
        m = slot_map(tmp_path, text)
        assert ae.check(m, tmp_path, CATALOG) == ["E: not a dataset the anvil15 sidecar names"]
        assert ae.check(m, tmp_path, CATALOG, datasets=["D"]) == []
        assert ae.check(m, tmp_path, CATALOG, datasets=["Z"]) == ["Z: not in the slot map"]

    def test_a_list_of_drs_uris_is_a_file_link(self, tmp_path):
        write_dataset(tmp_path, "D", [anvil_file(1), anvil_file(2), ("sample", {"hifi": [drs(1), drs(2)]})])
        text = "catalog: anvil15\ndatasets:\n  D:\n    sample:\n      hifi:\n        platform:\n          - {column_name: hifi}\n"
        assert ae.check(slot_map(tmp_path, text), tmp_path, CATALOG) == []


# --- import --------------------------------------------------------------------


class TestTranscription:
    def test_a_string_cell_is_verbatim_and_the_empty_string_is_kept(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        result = ae.import_dataset(
            slot_map(tmp_path, HIFI_MAP), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        (table,) = result.tables
        rows = rows_of(table.path)
        assert ("platform", drs(1), "PACBIO_SMRT", "platform") in rows
        assert ("platform", drs(2), "", "platform") in rows  # an empty cell is something the source published

    def test_a_null_cell_is_skipped_and_counted_once_per_row_and_column(self, tmp_path):
        """`library_source` feeds two slots; row b is null on it and counts once, not twice (R6)."""
        write_dataset(tmp_path, "D", HIFI_ROWS)
        result = ae.import_dataset(
            slot_map(tmp_path, HIFI_MAP), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        (table,) = result.tables
        assert table.null_cells == {"instrument_model": 1, "library_source": 1}
        assert not any(
            target == drs(2) and field in ("data_modality", "assay_type") for field, target, _, _ in rows_of(table.path)
        )

    def test_a_file_whose_only_cell_is_null_receives_nothing_and_is_not_counted(self, tmp_path):
        """ENCORE's FASTQs carry a null reference_assembly: reached, but not a file with evidence."""
        write_dataset(
            tmp_path,
            "D",
            [
                anvil_file(1),
                anvil_file(2),
                ("file", {"file_ref": drs(1), "ra": "GRCh38"}),
                ("file", {"file_ref": drs(2), "ra": None}),
            ],
        )
        text = "catalog: anvil15\ndatasets:\n  D:\n    file:\n      file_ref:\n        reference_assembly:\n          - {cell: ra}\n"
        result = ae.import_dataset(
            slot_map(tmp_path, text), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        assert result.files == 1
        assert result.tables[0].null_cells == {"ra": 1}
        assert [r[1] for r in rows_of(result.tables[0].path)] == [drs(1)]

    def test_a_list_cell_is_its_json_array(self, tmp_path):
        titles = ["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"]
        write_dataset(tmp_path, "D", [anvil_file(1), ("file", {"file_path": drs(1), "assay_titles": titles})])
        text = "catalog: anvil15\ndatasets:\n  D:\n    file:\n      file_path:\n        assay_type:\n          - {cell: assay_titles}\n"
        result = ae.import_dataset(
            slot_map(tmp_path, text), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        (row,) = rows_of(result.tables[0].path)
        assert row == ("assay_type", drs(1), json.dumps(titles), "assay_titles")
        assert json.loads(row[2]) == titles

    def test_an_empty_list_cell_observes_nothing_and_is_counted_with_the_nulls(self, tmp_path):
        """IGVF's assay_titles is `[]` on 31 rows: not a set of titles, and not written as one."""
        write_dataset(
            tmp_path,
            "D",
            [
                anvil_file(1),
                anvil_file(2),
                ("file", {"file_path": drs(1), "assay_titles": []}),
                ("file", {"file_path": drs(2), "assay_titles": ""}),
            ],
        )
        text = "catalog: anvil15\ndatasets:\n  D:\n    file:\n      file_path:\n        assay_type:\n          - {cell: assay_titles}\n"
        result = ae.import_dataset(
            slot_map(tmp_path, text), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        assert rows_of(result.tables[0].path) == [("assay_type", drs(2), "", "assay_titles")]
        assert result.tables[0].null_cells == {"assay_titles": 1}

    def test_a_non_string_scalar_is_its_json_literal(self, tmp_path):
        write_dataset(tmp_path, "D", [anvil_file(1), ("t", {"c": drs(1), "depth": 30, "flag": True})])
        text = "catalog: anvil15\ndatasets:\n  D:\n    t:\n      c:\n        platform:\n          - {cell: depth}\n          - {cell: flag}\n"
        result = ae.import_dataset(
            slot_map(tmp_path, text), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        assert [r[2] for r in rows_of(result.tables[0].path)] == ["30", "true"]


class TestProvenance:
    def test_the_column_is_the_cell_the_value_came_from_not_the_link(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        result = ae.import_dataset(
            slot_map(tmp_path, HIFI_MAP), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        rows = rows_of(result.tables[0].path)
        assert ("platform", drs(1), "Revio", "instrument_model") in rows
        assert ("data_modality", drs(1), "GENOMIC", "library_source") in rows

    def test_a_table_name_span_has_no_column_and_a_column_name_span_names_its_column(self, tmp_path):
        write_dataset(
            tmp_path,
            "D",
            [anvil_file(1), anvil_file(2), ("SGDP_CHM13v2_sample", {"cram": drs(1), "read_1_fastq": drs(2)})],
        )
        text = (
            "catalog: anvil15\ndatasets:\n  D:\n    SGDP_CHM13v2_sample:\n"
            "      cram:\n        reference_assembly:\n          - {table_name: CHM13v2}\n"
            "      read_1_fastq:\n        reference_assembly:\n          - {table_name: CHM13v2}\n"
            "        data_type:\n          - {column_name: fastq}\n"
        )
        result = ae.import_dataset(
            slot_map(tmp_path, text), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        rows = rows_of(result.tables[0].path)
        assert ("reference_assembly", drs(1), "CHM13v2", None) in rows
        assert ("reference_assembly", drs(2), "CHM13v2", None) in rows
        assert ("data_type", drs(2), "fastq", "read_1_fastq") in rows

    def test_the_envelope_names_both_sides_of_the_join(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        result = ae.import_dataset(
            slot_map(tmp_path, HIFI_MAP), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        envelope = read_envelope(result.tables[0].path)
        assert (envelope.source.repository, envelope.source.dataset, envelope.source.table) == ("anvil", "D", "hifi")
        assert envelope.source_type == SOURCE_REPOSITORY_METADATA
        assert (envelope.source_version, envelope.target.version) == (CATALOG, CATALOG)
        assert (envelope.source_key, envelope.target_key) == (JOIN_KEY_DRS_URI, JOIN_KEY_DRS_URI)
        assert (envelope.target.system, envelope.target.dataset) == ("anvil", "D")
        # When the source was fetched: the manifest's request time, not the import's.
        assert envelope.fetched_at == datetime.fromisoformat(FETCHED)

    def test_a_sidecar_that_cannot_say_when_the_manifest_was_fetched_is_refused(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS, fetched=None)
        with pytest.raises(ValueError, match="requested_at"):
            ae.import_dataset(slot_map(tmp_path, HIFI_MAP), tmp_path, CATALOG, "D", tmp_path / "ev")


class TestLinks:
    def test_an_empty_link_is_no_link_and_an_unknown_one_is_unresolved(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        result = ae.import_dataset(
            slot_map(tmp_path, HIFI_MAP), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        (table,) = result.tables
        assert table.rows == 4
        assert table.no_link == {"path": 1}
        assert table.unresolved == {"path": 1}
        assert result.files == 2
        assert {r[1] for r in rows_of(table.path)} == {drs(1), drs(2)}

    def test_a_value_that_is_not_a_link_is_counted_not_passed_over(self, tmp_path):
        """`check` reports such a column; an import that runs anyway still says how many rows it met."""
        write_dataset(
            tmp_path,
            "D",
            [anvil_file(1), ("hifi", {"path": drs(1), "platform": "x"}), ("hifi", {"path": "HG002", "platform": "x"})],
        )
        text = "catalog: anvil15\ndatasets:\n  D:\n    hifi:\n      path:\n        platform:\n          - {cell: platform}\n"
        result = ae.import_dataset(
            slot_map(tmp_path, text), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        (table,) = result.tables
        assert table.not_link == {"path": 1}
        assert table.written == 1
        assert "    path: not a DRS URI on 1 rows" in ae.describe([result])

    def test_a_list_link_fans_one_row_out_to_every_file_in_it(self, tmp_path):
        write_dataset(tmp_path, "D", [anvil_file(1), anvil_file(2), ("sample", {"hifi": [drs(1), drs(2), drs(7)]})])
        text = "catalog: anvil15\ndatasets:\n  D:\n    sample:\n      hifi:\n        platform:\n          - {column_name: hifi}\n"
        result = ae.import_dataset(
            slot_map(tmp_path, text), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
        )
        (table,) = result.tables
        assert rows_of(table.path) == [("platform", drs(1), "hifi", "hifi"), ("platform", drs(2), "hifi", "hifi")]
        assert table.unresolved == {"hifi": 1}


class TestGenerations:
    def test_a_second_import_is_a_new_generation_and_only_it_is_discovered(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        m = slot_map(tmp_path, HIFI_MAP)
        first = ae.import_dataset(m, tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z")
        second = ae.import_dataset(m, tmp_path, CATALOG, "D", tmp_path / "ev", "20260921T000000Z")
        assert first.tables[0].path.is_file(), "the earlier generation is kept as history"
        assert discover(tmp_path / "ev") == [second.tables[0].path]
        assert is_generation(second.generation)
        assert second.directory == tmp_path / "ev" / "anvil" / CATALOG / "D" / "20260921T000000Z"

    def test_importing_one_dataset_leaves_another_datasets_evidence_current(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        write_dataset(tmp_path, "E", HIFI_ROWS)
        text = HIFI_MAP + "  E:\n    hifi:\n      path:\n        platform:\n          - {cell: platform}\n"
        m = slot_map(tmp_path, text)
        both = ae.import_all(m, tmp_path, CATALOG, tmp_path / "ev", generation="20260920T000000Z")
        assert [i.dataset for i in both] == ["D", "E"]
        only_d = ae.import_all(m, tmp_path, CATALOG, tmp_path / "ev", datasets=["D"], generation="20260921T000000Z")
        current = discover(tmp_path / "ev")
        assert only_d[0].tables[0].path in current
        assert both[1].tables[0].path in current, "E's evidence did not disappear because D was re-imported"
        assert both[0].tables[0].path not in current

    def test_an_import_never_writes_over_a_generation(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        m = slot_map(tmp_path, HIFI_MAP)
        ae.import_dataset(m, tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z")
        with pytest.raises(FileExistsError, match="never overwrites"):
            ae.import_dataset(m, tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z")

    def test_a_failure_part_way_leaves_no_half_written_generation(self, tmp_path, monkeypatch):
        """The previous complete generation stays current; the partial one is removed."""
        write_dataset(tmp_path, "D", HIFI_ROWS)
        text = HIFI_MAP + "    ont:\n      path:\n        platform:\n          - {cell: platform}\n"
        m = slot_map(tmp_path, text)
        write_dataset(tmp_path, "D", [*HIFI_ROWS, ("ont", {"path": drs(3), "platform": "OXFORD_NANOPORE"})])
        first = ae.import_dataset(m, tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z")
        real = ae.write_evidence_file
        calls = []

        def failing(path, envelope, entries):
            calls.append(path.name)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(path, envelope, entries)

        monkeypatch.setattr(ae, "write_evidence_file", failing)
        with pytest.raises(OSError, match="disk full"):
            ae.import_dataset(m, tmp_path, CATALOG, "D", tmp_path / "ev", "20260921T000000Z")
        assert calls == ["hifi.ndjson", "ont.ndjson"]
        assert not (tmp_path / "ev" / "anvil" / CATALOG / "D" / "20260921T000000Z").exists()
        assert discover(tmp_path / "ev") == [t.path for t in first.tables]

    def test_a_generation_exists_whole_or_not_at_all(self, tmp_path, monkeypatch):
        """The files are written to `<stamp>.partial` and renamed into place at the end; a
        kill part-way leaves the staging directory, which nothing reads and a re-import refuses."""
        write_dataset(tmp_path, "D", HIFI_ROWS)
        m = slot_map(tmp_path, HIFI_MAP)
        seen: list[bool] = []
        real = ae.write_evidence_file

        def observing(path, envelope, entries):
            seen.append(path.parent.name.endswith(".partial"))
            return real(path, envelope, entries)

        monkeypatch.setattr(ae, "write_evidence_file", observing)
        result = ae.import_dataset(m, tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z")
        assert seen == [True], "written under the staging name"
        assert result.tables[0].path.is_file() and result.tables[0].path.parent.name == "20260920T000000Z"
        # A kill part-way: the staging directory is left behind.
        killed = tmp_path / "ev" / "anvil" / CATALOG / "D" / "20260921T000000Z.partial"
        killed.mkdir()
        (killed / "hifi.ndjson").write_text("")
        assert discover(tmp_path / "ev") == [result.tables[0].path], "the unfinished import is never current"
        assert unfinished_imports(tmp_path / "ev") == [killed]
        with pytest.raises(FileExistsError, match="unfinished import"):
            ae.import_dataset(m, tmp_path, CATALOG, "D", tmp_path / "ev", "20260921T000000Z")

    def test_a_mapped_table_that_reaches_no_file_is_an_error_not_an_empty_file(self, tmp_path):
        """Contract 5.3: evidence matching no file is the map disagreeing with the catalog."""
        write_dataset(tmp_path, "D", [anvil_file(1), ("hifi", {"path": drs(9), "platform": "PACBIO_SMRT"})])
        text = "catalog: anvil15\ndatasets:\n  D:\n    hifi:\n      path:\n        platform:\n          - {cell: platform}\n"
        with pytest.raises(ValueError, match="D/hifi: no evidence row written"):
            ae.import_dataset(slot_map(tmp_path, text), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z")
        assert discover(tmp_path / "ev") == []

    def test_import_all_refuses_a_dataset_the_map_does_not_name(self, tmp_path):
        write_dataset(tmp_path, "D", HIFI_ROWS)
        with pytest.raises(ValueError, match="not in the slot map"):
            ae.import_all(slot_map(tmp_path, HIFI_MAP), tmp_path, CATALOG, tmp_path / "ev", datasets=["Z"])


def test_describe_names_the_generation_and_each_tables_counts(tmp_path):
    write_dataset(tmp_path, "D", HIFI_ROWS)
    result = ae.import_dataset(
        slot_map(tmp_path, HIFI_MAP), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z"
    )
    lines = ae.describe([result])
    assert lines[0].startswith("D -> ") and lines[0].endswith("(2 files)")
    assert "  hifi: 4 rows, 7 evidence rows" in lines
    assert "    path: no link on 1 rows" in lines
    assert "    path: 1 links not among the dataset's files" in lines
    assert "    library_source: null on 1 rows" in lines


# --- the bundled map against the real manifests -----------------------------------


@pytest.mark.skipif(not REAL_MANIFESTS.is_dir(), reason="anvil15 manifests are not on disk (make download)")
def test_the_bundled_map_agrees_with_the_anvil15_manifests():
    assert ae.check(load_slot_map(), Path("data/anvil"), CATALOG) == []
