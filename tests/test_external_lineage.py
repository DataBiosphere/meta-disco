"""Sample maps held outside AnVIL for a dataset (#710, a workaround until #624): the declaration and
its cache (``external_files``), the importer gating each workspace tar on its own ``callset.json``
(``external_lineage``), and reconcile reading a tar's values and samples through such a map
(``reconcile_external``)."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from meta_disco import code_rules
from meta_disco import external_lineage as xl
from meta_disco.activity_map import load_activity_map
from meta_disco.deployments import Deployment
from meta_disco.evidence import TarEvidence
from meta_disco.external_files import (
    ExternalFileError,
    ExternalFiles,
    fetch,
    load_external_files,
    read_text,
)
from meta_disco.fetchers import FetchError
from meta_disco.lineage_evidence import iter_lineage, read_lineage_envelope, write_lineage_file
from meta_disco.models import SOURCE_EXTERNAL_GROUND_TRUTH
from meta_disco.output_utils import (
    EXTERNAL_LISTS_FILE,
    SAMPLES_FILE,
    iter_reconciled_artifact,
    iter_reconciled_records,
    iter_reconciled_sample_lists,
)
from meta_disco.reconcile import ReconcileError, reconcile_run
from meta_disco.reconcile_lineage import EXTERNAL_UNDECLARED, RESOLVED
from meta_disco.schema.classification_model import ExternalList, GeneratedBy, LineageParentKeyEnum, LineageRow
from meta_disco.source_evidence import evidence_file_path, generation_dir
from meta_disco.tdr import Snapshot
from tests.manifest_fixtures import CATALOG, write_dataset
from tests.metadata_fixtures import write_metadata
from tests.run_fixtures import output_record, write_run
from tests.test_producer_steps import gatk4, header_text

STAMP = "20261018T000000Z"
COMMIT = "a" * 40
MAP_PATH = "gs://gone/sample_maps/chr1_sample_map.tsv"
OTHER_MAP_PATH = "gs://other/uploads/sample_maps/chr1_sample_map.tsv"
MAP_TEXT = "HG00096\tgs://b/chr1/HG00096.chr1.hc.vcf.gz\nHG00097\tgs://b/chr1/HG00097.chr1.hc.vcf.gz\n"
SHA = hashlib.sha256(MAP_TEXT.encode()).hexdigest()
REF = f"github:o/r@{COMMIT}/maps/chr1_sample_map.tsv"


def declaration(sha: str = SHA, extra: str = "") -> str:
    return f"""
catalog: anvil15
datasets:
  C:
    host: github
    repository: o/r
    commit: {COMMIT}
    directory: maps
    sample_maps:
      chr1_sample_map.tsv:
        sha256: {sha}
        named_as: [{MAP_PATH}]
{extra}"""


def load(tmp_path: Path, text: str) -> ExternalFiles:
    path = tmp_path / "external_files.yaml"
    path.write_text(text)
    return load_external_files(path)


@pytest.fixture
def declared(tmp_path) -> ExternalFiles:
    return load(tmp_path, declaration())


@pytest.fixture
def cached(tmp_path, declared) -> Path:
    root = tmp_path / "data" / "external"
    (file,) = declared.entries[0].sample_maps
    assert fetch(file, root, get=lambda _url: MAP_TEXT.encode()) is True
    return root


# --- the declaration and its cache ---------------------------------------------------------------


def test_a_declared_file_is_addressed_by_its_commit_and_kept_under_its_dataset_first(tmp_path, declared):
    (file,) = declared.entries[0].sample_maps
    assert file.ref == REF
    assert file.url == f"https://raw.githubusercontent.com/o/r/{COMMIT}/maps/chr1_sample_map.tsv"
    assert file.cache_path(tmp_path) == tmp_path / "C" / "github" / "o" / "r" / COMMIT / "maps" / "chr1_sample_map.tsv"
    assert declared.entries[0].named(MAP_PATH) is file and declared.entries[0].named(OTHER_MAP_PATH) is None
    # A file is held for its dataset alone.
    assert declared.by_ref("C", REF) is file and declared.by_ref("OTHER", REF) is None


@pytest.mark.parametrize(
    ("text", "fault"),
    [
        (declaration().replace("host: github", "host: gitlab"), "the one host"),
        (declaration().replace(COMMIT, "abc123"), "full 40-character commit"),
        (declaration(sha="xyz"), "64 lowercase hex"),
        (declaration().replace("repository: o/r", "repository: r"), "owner/name"),
        (declaration().replace("repository: o/r", "repository: o/.."), "'..'"),
        (declaration().replace("directory: maps", "directory: maps/../.."), "'..'"),
        (declaration().replace("  C:\n", "  ../x:\n"), "one directory name"),
        (declaration().replace("chr1_sample_map.tsv:", "chr1.tsv:"), "_sample_map.tsv"),
        (
            declaration(extra=f"      chr2_sample_map.tsv:\n        sha256: {SHA}\n        named_as: [{MAP_PATH}]\n"),
            "also named for chr1_sample_map.tsv",
        ),
    ],
)
def test_the_declaration_refuses_a_malformed_entry(tmp_path, text, fault):
    with pytest.raises(ValueError, match=fault):
        load(tmp_path, text)


def test_one_file_declared_for_two_datasets_is_refused(tmp_path):
    second = declaration().split("datasets:\n", 1)[1].replace("  C:\n", "  D:\n", 1)
    with pytest.raises(ValueError, match="declared for both C and D"):
        load(tmp_path, declaration() + second)


def test_the_bundled_declaration_names_each_1000_genomes_map_once():
    (entry,) = load_external_files().entries
    assert (entry.dataset, entry.repository) == ("ANVIL_T2T_CHRY", "schatzlab/t2t-chm13-chry")
    assert len(entry.sample_maps) == 25
    named = [p for f in entry.sample_maps for p in f.named_as]
    # 22 autosomes, chrY and chrX's non-PAR map each once; the one chrX_PAR map for the tars' two.
    assert len(named) == len(set(named)) == 26


def test_a_download_whose_sha256_differs_is_refused_and_nothing_is_kept(tmp_path, declared):
    (file,) = declared.entries[0].sample_maps
    root = tmp_path / "ext"
    with pytest.raises(ExternalFileError, match="sha256"):
        fetch(file, root, get=lambda _url: b"edited upstream\n")
    assert not root.exists() or not any(p.is_file() for p in root.rglob("*"))


def test_a_cached_file_is_kept_and_not_downloaded_again(declared, cached):
    (file,) = declared.entries[0].sample_maps
    assert fetch(file, cached, get=lambda _url: pytest.fail("downloaded a cached file")) is False
    assert read_text(file, cached) == MAP_TEXT


def test_reading_a_missing_or_changed_file_is_refused(tmp_path, declared, cached):
    (file,) = declared.entries[0].sample_maps
    with pytest.raises(ExternalFileError, match="fetch-external-files"):
        read_text(file, tmp_path / "elsewhere")
    file.cache_path(cached).write_text(MAP_TEXT + "HG00099\tgs://b/x.hc.vcf.gz\n")
    with pytest.raises(ExternalFileError, match="declared"):
        read_text(file, cached)


# --- the importer ----------------------------------------------------------------------------------


def md5(tag: str) -> str:
    return hashlib.md5(tag.encode()).hexdigest()


def workspace_header(n: int, sample_map: str = MAP_PATH) -> str:
    return header_text(
        gatk4("GenomicsDBImport", f"--genomicsdb-workspace-path ./chr1.{n} --sample-name-map {sample_map}")
    )


def callset(*samples: str) -> str:
    return json.dumps({"callsets": [{"sample_name": s, "row_idx": i} for i, s in enumerate(samples)]})


# Per tar n (chr1.<n>.tar, file t<n>): its cached header (None: no cache entry) and its callset.json
# (an exception to raise instead).
TARS: dict[int, tuple[str | None, object]] = {
    1: (workspace_header(1), callset("HG00096", "HG00097")),  # linked
    2: (workspace_header(2), callset("HG00096")),  # one sample short
    3: (workspace_header(3), callset("HG00096", "HG00097", "HG00096")),  # a sample twice
    4: (workspace_header(4, OTHER_MAP_PATH), callset("HG00096", "HG00097")),  # a map no declared file is
    5: (None, None),  # nothing cached
    6: (workspace_header(6), FetchError("HTTP 404")),  # its callset.json cannot be read
    7: (workspace_header(7), None),  # no callset.json in either window
}


def manifest_entities():
    return [
        ("anvil_file", {"file_id": f"t{n}", "file_name": f"chr1.{n}.tar", "file_md5sum": md5(f"t{n}")}) for n in TARS
    ] + [("anvil_file", {"file_id": "g1", "file_name": "HG00096.chr1.hc.vcf.gz", "file_md5sum": md5("g1")})]


def read_member(checksum: str):
    n = next(n for n in TARS if md5(f"t{n}") == checksum)
    found = TARS[n][1]
    if isinstance(found, Exception):
        raise found
    return found


@pytest.fixture
def importing(tmp_path, cached):
    manifests = tmp_path / "m"
    write_dataset(manifests, "C", manifest_entities())
    tar_cache = tmp_path / "tar_cache"
    for n, (text, _) in TARS.items():
        if text is not None:
            TarEvidence(
                md5sum=md5(f"t{n}"),
                file_name=f"chr1.{n}.tar",
                member_names=[f"./chr1.{n}/vcfheader.vcf", f"./chr1.{n}/callset.json"],
                vcf_header=text,
                vcf_header_read=True,
            ).save(tar_cache)
    return manifests, tar_cache, cached


def run_import(tmp_path, declared, importing, read=read_member, stored=None, generation=STAMP):
    manifests, tar_cache, external = importing
    (result,) = xl.import_all(
        declared,
        manifests,
        tmp_path / "lin",
        tar_cache,
        external,
        read_member=read,
        stored=stored,
        generation=generation,
    )
    return result


def lines(result) -> list[dict]:
    return [r.model_dump(exclude_none=True) for r in iter_lineage(evidence_file_path(result.directory, xl.TABLE))]


def test_each_tar_is_counted_once_by_why(tmp_path, declared, importing):
    result = run_import(tmp_path, declared, importing)
    assert dict(result.outcomes) == {
        xl.LINKED: 1,
        xl.SAMPLES_DIFFER: 2,
        xl.MAP_NOT_DECLARED: 1,
        xl.NO_HEADER: 1,
        xl.CALLSET_UNREADABLE: 1,
        xl.NO_CALLSET: 1,
    }


def test_a_tar_whose_callset_names_exactly_the_maps_samples_gets_a_line_naming_the_map(tmp_path, declared, importing):
    result = run_import(tmp_path, declared, importing)
    assert lines(result) == [
        {
            "target_key_value": "t1",
            "parent": REF,
            "parent_key_type": "external_file",
            "parent_source_identifier": MAP_PATH,
            "raw_activity": "GenomicsDBImport",
            "raw_activity_column": "vcfheader.vcf",
            "child_column": "file_id",
            "parent_column": "--sample-name-map",
        }
    ]
    envelope = read_lineage_envelope(evidence_file_path(result.directory, xl.TABLE))
    assert (envelope.source.repository, envelope.source_version) == ("github:o/r", COMMIT)
    assert str(envelope.source_type) == SOURCE_EXTERNAL_GROUND_TRUTH
    assert result.directory == generation_dir(tmp_path / "lin", "external", CATALOG, "C", STAMP)


def test_a_tar_naming_no_declared_map_is_not_read(tmp_path, declared, importing):
    read: list[str] = []

    def reading(checksum):
        read.append(checksum)
        return read_member(checksum)

    run_import(tmp_path, declared, importing, read=reading)
    assert md5("t4") not in read and md5("t5") not in read


def test_a_reimport_from_the_kept_inputs_reads_no_network_and_writes_the_same_lines(tmp_path, declared, importing):
    first = run_import(tmp_path, declared, importing)
    stored = xl.load_inputs([first.directory / f"{xl.TABLE}.inputs.json"])
    again = run_import(
        tmp_path,
        declared,
        importing,
        read=lambda _md5: pytest.fail("a re-import read the network"),
        stored=stored,
        generation="20261019T000000Z",
    )
    assert lines(again) == lines(first) and again.outcomes == first.outcomes


def test_a_reimport_refuses_a_reading_of_another_file(tmp_path, declared, importing):
    first = run_import(tmp_path, declared, importing)
    path = first.directory / f"{xl.TABLE}.inputs.json"
    document = json.loads(path.read_text())
    document["tars"][0]["md5"] = md5("replaced")
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="not the tar its kept reading read"):
        run_import(tmp_path, declared, importing, stored=xl.load_inputs([path]), generation="20261019T000000Z")


def test_an_import_linking_nothing_writes_nothing(tmp_path, declared, importing):
    with pytest.raises(ValueError, match="no tar linked"):
        run_import(tmp_path, declared, importing, read=lambda _md5: callset("NA12878"))
    assert not (tmp_path / "lin").exists()


def test_check_refuses_a_map_not_in_the_cache(tmp_path, declared, importing):
    manifests, _, _ = importing
    deployment = Deployment(
        name="test",
        service="https://azul.test",
        catalog=CATALOG,
        input_root=Path("unused"),
        snapshots={"C": Snapshot("p", "C")},
    )
    assert xl.check(declared, deployment, manifests, importing[2]) == []
    (problem,) = xl.check(declared, deployment, manifests, tmp_path / "empty")
    assert "fetch-external-files" in problem


@pytest.mark.parametrize(
    ("text", "samples"),
    [
        (callset("A", "B"), ["A", "B"]),
        (json.dumps({"callsets": {"A": {"row_idx": 0}, "B": {"row_idx": 1}}}), ["A", "B"]),
    ],
)
def test_a_callset_names_its_samples_in_either_shape(text, samples):
    assert xl.callset_samples(text) == samples


@pytest.mark.parametrize("text", ["[]", json.dumps({"callsets": [{"row_idx": 0}]}), json.dumps({"callsets": []})])
def test_a_callset_naming_no_sample_is_refused(text):
    with pytest.raises(ValueError):
        xl.callset_samples(text)


# --- reconcile -------------------------------------------------------------------------------------

GVCF = {"assay_type": "WGS", "platform": "ILLUMINA", "instrument_model": "Illumina NovaSeq 6000"}


def tar_line(child: str = "t1", parent: str = REF):
    return LineageRow(
        target_key_value=child,
        parent=parent,
        parent_key_type=LineageParentKeyEnum.external_file,
        parent_source_identifier=MAP_PATH,
        raw_activity="GenomicsDBImport",
        raw_activity_column="vcfheader.vcf",
        child_column="file_id",
        parent_column="--sample-name-map",
    )


def reconcile(tmp_path, declared, rows, lineage_rows, external_root=None):
    evidence = tmp_path / "data" / "source_evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    lineage = tmp_path / "data" / "lineage_evidence"
    directory = generation_dir(lineage, xl.SOURCE, CATALOG, "C", STAMP)
    directory.mkdir(parents=True)
    write_lineage_file(
        evidence_file_path(directory, xl.TABLE),
        xl.envelope(CATALOG, declared.entries[0], datetime(2026, 10, 18, tzinfo=timezone.utc)),
        lineage_rows,
    )
    run_dir = write_run(tmp_path / "output" / "20261018_000000", rows)
    metadata = write_metadata(tmp_path / "input.json", [], repository="anvil", catalog=CATALOG)
    report = reconcile_run(
        run_dir,
        metadata,
        evidence,
        external_files=declared,
        external_root=external_root,
        activity_table=load_activity_map(),
    )
    return run_dir, {r["file_name"]: r for r in iter_reconciled_records(run_dir)}, report


def run_rows(*gvcfs: str):
    return [
        output_record("chr1.1.tar", md5("t1"), dataset="C", file_id="t1", data_type="variants.gvcf"),
        *(
            output_record(name, md5(name), dataset="C", file_id=f"g_{name}", data_type="variants.gvcf", **GVCF)
            for name in gvcfs
        ),
    ]


BOTH = ("HG00096.chr1.hc.vcf.gz", "HG00097.chr1.hc.vcf.gz")


def test_a_tar_reads_its_values_through_the_map_held_outside_anvil(tmp_path, declared, cached):
    run_dir, rows, report = reconcile(tmp_path, declared, run_rows(*BOTH), [tar_line()])
    tar = rows["chr1.1.tar"]
    step = tar["generated_by"]
    assert step["activity"] == "CohortMergeActivity"
    (used,) = step["inputs"]
    assert used["role"] == "input_list" and used["parent_ref"] == REF and "parent_key" not in used
    for dimension, value in GVCF.items():
        entry = tar["classifications"][dimension]
        assert (entry["value"], entry["credited_to"]) == (value, "inherited"), dimension
    assert report["lineage"]["sources"][SOURCE_EXTERNAL_GROUND_TRUTH]["C"][RESOLVED] == 1
    assert report["external_lists"] == {
        "C": {
            "lists": 1,
            "rows": 2,
            "rows_not_in_dataset": 0,
            "rows_several_match": 0,
            "samples_named": 1,
            "stepped": 1,
        }
    }
    (listed,) = iter_reconciled_artifact(run_dir, EXTERNAL_LISTS_FILE)
    assert (listed["ref"], listed["dataset"], listed["sha256"]) == (REF, "C", SHA)
    assert listed["generated_by"]["activity"] == "CohortDefinitionActivity"
    assert sorted(i["parent_key"] for i in listed["generated_by"]["inputs"]) == [f"g_{n}" for n in BOTH]
    assert {n["rule_id"] for n in listed["generated_by"]["named_by"]} == {code_rules.COHORT_BY_EXTERNAL_SAMPLE_MAP.id}
    # Both shapes are the schema's: an input naming its parent by `parent_ref`, and the list's own line.
    GeneratedBy.model_validate(step)
    ExternalList.model_validate(listed)


def test_a_tar_takes_the_samples_its_map_held_outside_anvil_names(tmp_path, declared, cached):
    run_dir, rows, _ = reconcile(tmp_path, declared, run_rows(*BOTH), [tar_line()])
    samples = rows["chr1.1.tar"]["samples"]
    (listed,) = [s for s in iter_reconciled_sample_lists(run_dir) if s["list_id"] == samples["list_id"]]
    assert sorted(m["id"] for m in listed["members"]) == ["HG00096", "HG00097"]
    (external,) = iter_reconciled_artifact(run_dir, EXTERNAL_LISTS_FILE)
    assert external["samples"]["list_id"] == samples["list_id"]
    assert external["samples"]["named_by"] == [
        {"source_type": SOURCE_EXTERNAL_GROUND_TRUTH, "rule_id": code_rules.EXTERNAL_SAMPLE_MAP_ROWS.id}
    ]


def test_a_map_whose_member_the_dataset_lacks_has_no_step_and_passes_nothing(tmp_path, declared, cached):
    run_dir, rows, report = reconcile(tmp_path, declared, run_rows(BOTH[0]), [tar_line()])
    tar = rows["chr1.1.tar"]
    assert tar["generated_by"]["inputs"][0]["parent_ref"] == REF
    assert tar["classifications"]["assay_type"]["status"] == "not_classified"
    assert report["external_lists"]["C"]["rows_not_in_dataset"] == 1
    (listed,) = iter_reconciled_artifact(run_dir, EXTERNAL_LISTS_FILE)
    assert "generated_by" not in listed


def test_a_map_not_declared_for_the_tars_dataset_is_counted_and_gives_nothing(tmp_path, declared, cached):
    _, rows, report = reconcile(tmp_path, declared, run_rows(*BOTH), [tar_line(parent=REF.replace("@", "@x"))])
    assert rows["chr1.1.tar"]["generated_by"] is None
    assert report["lineage"]["sources"][SOURCE_EXTERNAL_GROUND_TRUTH]["C"][EXTERNAL_UNDECLARED] == 1


def test_reconcile_refuses_a_declared_map_missing_from_the_cache(tmp_path, declared):
    with pytest.raises(ReconcileError, match="fetch-external-files"):
        reconcile(tmp_path, declared, run_rows(*BOTH), [tar_line()], external_root=tmp_path / "nowhere")


def test_a_callset_read_is_tried_again_only_where_the_connection_failed(monkeypatch):
    calls: list[str] = []

    def fails(cause):
        def fetch(md5, member):
            calls.append(member)
            if cause is None:
                raise FetchError("HTTP 404 from AnVIL S3 mirror range request")
            raise FetchError("tar member: ConnectionError") from cause

        return fetch

    monkeypatch.setattr(xl.time, "sleep", lambda _s: None)
    monkeypatch.setattr(xl, "fetch_tar_member", fails(requests.ConnectionError("reset")))
    with pytest.raises(FetchError):
        xl.read_callset(md5("t1"))
    assert calls == [xl.CALLSET_MEMBER] * xl.ATTEMPTS
    calls.clear()
    monkeypatch.setattr(xl, "fetch_tar_member", fails(None))
    with pytest.raises(FetchError, match="404"):
        xl.read_callset(md5("t1"))
    assert calls == [xl.CALLSET_MEMBER]


def test_kept_inputs_naming_a_sample_set_they_do_not_hold_are_refused(tmp_path, declared, importing):
    first = run_import(tmp_path, declared, importing)
    path = first.directory / f"{xl.TABLE}.inputs.json"
    document = json.loads(path.read_text())
    document["sample_sets"] = {}
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="does not hold"):
        xl.load_inputs([path])


def test_a_maps_samples_no_reconciled_file_settles_to_are_not_written(tmp_path, declared, cached):
    """The line's tar is not in the run, so no file settles to the map's samples: no list, no sample records."""
    gvcfs_only = run_rows(*BOTH)[1:]
    run_dir, _, report = reconcile(tmp_path, declared, gvcfs_only, [tar_line()])
    assert report["lineage"]["sources"][SOURCE_EXTERNAL_GROUND_TRUTH]["C"]["child_not_in_run"] == 1
    assert list(iter_reconciled_sample_lists(run_dir)) == []
    assert list(iter_reconciled_artifact(run_dir, SAMPLES_FILE)) == []
    (listed,) = iter_reconciled_artifact(run_dir, EXTERNAL_LISTS_FILE)
    assert "samples" not in listed and "generated_by" in listed
