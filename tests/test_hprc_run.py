"""An HPRC run completes every phase without a catalog identity (#446).

HPRC is a source like AnVIL: ``scripts/classify_hprc_files.py`` maps its catalogs into
the one record shape and calls the one run. Its records carry no ``entry_id``,
``file_id`` or ``drs_uri`` — the catalogs issue none, and none is minted — so a run
that keyed Phase 3 on ``entry_id`` refused every one of them. The key is now the
source's own (``pipeline.RECORD_KEYS``): for HPRC, the URL hash the builder writes as
the checksum.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from classify_hprc_files import build_metadata_records, path_key

from meta_disco.classify_run import run_all_classifications
from meta_disco.exclusions import read_excluded
from meta_disco.output_utils import CLASSIFICATION_FILES, iter_records_with_source
from meta_disco.pipeline import HPRC_REPOSITORY, RECORD_KEYS, record_key

# Catalog rows in the shape the assemblies catalog has (`awsFasta` is its location
# field, `fileSize` present so no S3 HEAD is made). Names chosen so each lands with a
# producer that reads no file content: an image, a PLINK auxiliary, an index with no
# parent in the run (declined, #438), and one no producer claims (the catch-all).
_CATALOG = [
    {"filename": name, "awsFasta": f"s3://bucket/{name}", "fileSize": 1}
    for name in ("HG002.png", "HG002.pvar", "HG002.bam.bai", "HG002.readme")
]
# The exact failure from the issue: a record with no location has no URL to hash, so no
# key at all. It must be excluded and named, never reach a phase.
_NO_LOCATION = {"filename": "orphan.readme", "fileSize": 1}


def _hprc_input(tmp_path, catalog):
    records = build_metadata_records(catalog, "awsFasta", workers=1)
    metadata = tmp_path / "hprc_files_metadata.json"
    # The envelope the builder's `main` writes.
    metadata.write_text(json.dumps({"metadata": {"repository": HPRC_REPOSITORY}, "files": records}))
    return metadata, records


def test_the_builders_records_carry_no_catalog_identity():
    """What the shape is, pinned: the source-neutral fields and nothing Azul issues."""
    [record] = build_metadata_records(_CATALOG[:1], "awsFasta", workers=1)
    assert set(record) == {"file_name", "file_format", "file_md5sum", "url", "file_size"}
    assert record["file_md5sum"] == path_key("https://s3-us-west-2.amazonaws.com/bucket/HG002.png")


def test_hprc_shaped_records_complete_every_phase(tmp_path, capsys):
    """The reproduction from the issue, as the regression test: every phase runs, every
    producer writes, the run exits well, and the duplicate check keyed on the source's
    field reports what it checked rather than "not checked"."""
    metadata, _records = _hprc_input(tmp_path, [*_CATALOG, _NO_LOCATION])
    output_base = tmp_path / "output"

    assert run_all_classifications(metadata, output_base, tmp_path / "evidence") is True

    [run_dir] = output_base.iterdir()
    # The header producers write nothing when no record routes to them, so what is
    # pinned is that every producer these four files route to wrote its file.
    written = {p.name for p in run_dir.glob("*_classifications.json")}
    assert written == {f"{name}_classifications.json" for name in ("image", "auxiliary", "index", "remaining")}
    assert written <= set(CLASSIFICATION_FILES)
    rows = list(iter_records_with_source(run_dir))
    by_name = {row["file_name"]: (fname, row) for fname, row in rows}
    assert set(by_name) == {"HG002.png", "HG002.pvar", "HG002.bam.bai", "HG002.readme"}
    assert by_name["HG002.readme"][0] == "remaining_classifications.json", "Phase 3 wrote its row"
    for _fname, row in rows:
        # The identity is the URL hash, spelled `md5sum` on the way out; nothing is minted.
        assert row["md5sum"] == path_key(f"https://s3-us-west-2.amazonaws.com/bucket/{row['file_name']}")
        assert row["entry_id"] is None and row["file_id"] is None and row["drs_uri"] is None

    out = capsys.readouterr().out
    assert "One row per file: 4 rows, no repeated md5sum." in out
    assert "not checked" not in out


def test_a_record_with_no_key_is_excluded_and_named_before_any_phase(tmp_path):
    """A catalog entry with no location gets no URL hash, so no key. It is excluded at
    the shared load (#376) and listed in the run's `excluded_files.json` — the same act
    that excludes a null-md5 AnVIL record — so no null key ever reaches Phase 3."""
    metadata, records = _hprc_input(tmp_path, [*_CATALOG, _NO_LOCATION])
    assert [r["file_name"] for r in records if r["file_md5sum"] is None] == ["orphan.readme"]

    assert run_all_classifications(metadata, tmp_path / "output", tmp_path / "evidence") is True

    [run_dir] = (tmp_path / "output").iterdir()
    excluded = read_excluded(run_dir)
    assert [f.file_name for f in excluded.files] == ["orphan.readme"]
    assert excluded.total_input == 5
    assert "orphan.readme" not in {row["file_name"] for _f, row in iter_records_with_source(run_dir)}


def test_the_hprc_key_is_the_url_hash_not_a_content_checksum(tmp_path):
    """Two identical files at different paths are two files under this key: the
    declaration says a hash of the URL, and that is what the builder writes."""
    same_bytes = [
        {"filename": "HG002.readme", "awsFasta": "s3://bucket/a/HG002.readme", "fileSize": 1},
        {"filename": "HG002.readme", "awsFasta": "s3://bucket/b/HG002.readme", "fileSize": 1},
    ]
    metadata, records = _hprc_input(tmp_path, same_bytes)
    key = record_key({"repository": HPRC_REPOSITORY}, metadata)
    assert key == RECORD_KEYS["hprc"]
    assert len({r[key.input_field] for r in records}) == 2


def test_an_input_naming_no_repository_stops_the_run_before_it_writes_anything(tmp_path):
    """The preflight: Phase 3 would refuse this input after every earlier phase had run,
    so the run refuses it first — no output directory, no half-run to mistake for one."""
    records = build_metadata_records(_CATALOG, "awsFasta", workers=1)
    metadata = tmp_path / "hprc_files_metadata.json"
    metadata.write_text(json.dumps({"files": records}))

    with pytest.raises(ValueError, match="names no repository"):
        run_all_classifications(metadata, tmp_path / "output", tmp_path / "evidence")
    assert not (tmp_path / "output").exists()
