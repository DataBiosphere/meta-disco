"""The ENA run lineage map and importer (#594), and reconcile resolving its declared cross-dataset parents.

Synthetic manifests (``manifest_fixtures``), ENA rows, stats counts and SAM headers stand
in for the network: one alignment per outcome, the lines a linked one gets, the kept
inputs re-imported offline, the map's refusals, and reconcile carrying a run's reads'
answer across datasets only where the map declares it.
"""

import dataclasses
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from meta_disco import ena_lineage as el
from meta_disco.deployments import Deployment
from meta_disco.fetchers import FetchError
from meta_disco.lineage_evidence import check_row, iter_lineage, read_lineage_envelope, write_lineage_file
from meta_disco.models import SOURCE_EXTERNAL_GROUND_TRUTH
from meta_disco.output_utils import iter_reconciled_records
from meta_disco.reconcile import ReconcileError, reconcile_run
from meta_disco.reconcile_lineage import UNDECLARED_DATASET
from meta_disco.run_lineage_map import RunLineageMap, load_run_lineage_map
from meta_disco.schema.classification_model import LineageParentKeyEnum, LineageRow
from meta_disco.tdr import Snapshot
from tests.lineage_fixtures import envelope, write_lineage
from tests.manifest_fixtures import CATALOG, drs, write_dataset
from tests.metadata_fixtures import write_metadata
from tests.run_fixtures import output_record, write_run

STAMP = "20261005T000000Z"


def md5(tag: str) -> str:
    """A well-formed md5 standing for ``tag``: the importer reads only those, as the pipeline does (#376)."""
    return hashlib.md5(tag.encode()).hexdigest()


REQUESTED = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

MAP = """
catalog: anvil15
source: ena
datasets:
  C:
    sample:
      - child: {column: cram}
        counts: {column: stats}
        ena_studies: [PRJEB1]
        reads_in: R
"""

DEPLOYMENT = Deployment(
    name="test",
    service="https://azul.test",
    catalog=CATALOG,
    input_root=Path("unused"),
    snapshots={"C": Snapshot("p", "C_snapshot"), "R": Snapshot("p", "R_snapshot")},
)

BWA = (
    "@PG\tID:bwa\tPN:bwa\tVN:0.7.17\tCL:bwa mem -Y -t 16 ./ref.fasta ./s_1_lane_A.1.fastq.gz ./s_2_lane_A.1.fastq.gz\n"
)
FIXMATE = "@PG\tID:samtools\tPN:samtools\tPP:bwa\tCL:samtools fixmate -m in.bam out.bam\n"
MINIMAP = "@PG\tID:mm2\tPN:minimap2\tCL:minimap2 -ax sr ref.fa x_1.fq.gz x_2.fq.gz\n"

# Per alignment n (its CRAM is file n, its stats file 10+n): the counts its stats file
# gives (an exception to raise instead), and its header (one to raise instead).
STATS = {
    1: (100, 1500),  # one run, both FASTQs in R, bwa mem: linked
    2: (200, 3000),  # no run has these counts
    3: (300, 4500),  # two runs have them
    4: (400, 6000),  # its run's second FASTQ is not in R
    5: (500, 7500),  # its header names no FASTQ step
    6: FetchError("HTTP 404 from AnVIL S3 mirror range request"),
    8: (800, 12000),  # two FASTQ steps in its header
    9: (900, 13500),  # its header cannot be read
}
HEADERS = {1: BWA + FIXMATE, 4: BWA, 5: FIXMATE, 8: BWA + MINIMAP, 9: FetchError("samtools view -H exited 1")}


def run(accession, reads, bases, *files, study="PRJEB1"):
    return {
        "run_accession": accession,
        "study_accession": study,
        "read_count": str(reads),
        "base_count": str(bases),
        "fastq_ftp": ";".join(f"ftp.sra.ebi.ac.uk/vol1/fastq/{accession}/{name}" for name, _ in files),
        "fastq_md5": ";".join(md5 for _, md5 in files),
    }


RUNS = {
    r["run_accession"]: r
    for r in (
        run("ERR1", 100, 1500, ("ERR1_1.fastq.gz", md5("a1")), ("ERR1_2.fastq.gz", md5("a2"))),
        run("ERR3a", 300, 4500, ("ERR3a_1.fastq.gz", md5("b1"))),
        run("ERR3b", 300, 4500, ("ERR3b_1.fastq.gz", md5("b2"))),
        run("ERR4", 400, 6000, ("ERR4_1.fastq.gz", md5("c1")), ("ERR4_2.fastq.gz", md5("c2"))),
        run("ERR5", 500, 7500, ("ERR5_1.fastq.gz", md5("d1"))),
        run("ERR8", 800, 12000, ("ERR8_1.fastq.gz", md5("e1"))),
        run("ERR9", 900, 13500, ("ERR9_1.fastq.gz", md5("g1"))),
        run("ERR_other", 100, 1500, ("o.fastq.gz", md5("zz")), study="PRJEB2"),  # same counts, another study
    )
}


def child_entities():
    files = []
    for n in range(1, 10):
        files.append(
            (
                "anvil_file",
                {"file_id": f"c{n}", "file_name": f"s{n}.cram", "file_md5sum": md5(f"m{n}"), "drs_uri": drs(n)},
            )
        )
        files.append(
            (
                "anvil_file",
                {
                    "file_id": f"st{n}",
                    "file_name": f"s{n}.stats.txt",
                    "file_md5sum": md5(f"s{n}"),
                    "drs_uri": drs(10 + n),
                },
            )
        )
    rows = [("sample", {"cram": drs(n), "stats": None if n == 7 else drs(10 + n)}) for n in range(1, 10)]
    return files + rows


def reads_entities():
    present = [
        ("ERR1_1.fastq.gz", md5("a1")),
        ("ERR1_2.fastq.gz", md5("a2")),
        ("ERR4_1.fastq.gz", md5("c1")),
        ("ERR5_1.fastq.gz", md5("d1")),
    ]
    present += [("ERR8_1.fastq.gz", md5("e1")), ("ERR9_1.fastq.gz", md5("g1"))]
    return [
        ("anvil_file", {"file_id": f"r_{name}", "file_name": name, "file_md5sum": md5, "drs_uri": drs(100 + i)})
        for i, (name, md5) in enumerate(present)
    ]


def stats_of(checksum: str):
    found = STATS[next(n for n in STATS if md5(f"s{n}") == checksum)]
    if isinstance(found, Exception):
        raise found
    return found


def header_of(file: el.CatalogFile) -> str:
    found = HEADERS[int(file.file_id[1:])]
    if isinstance(found, Exception):
        raise found
    return found


def must_not_fetch(*_args):
    raise AssertionError("a re-import from kept inputs read the network")


@pytest.fixture
def run_map(tmp_path):
    path = tmp_path / "map.yaml"
    path.write_text(MAP)
    return load_run_lineage_map(path)


@pytest.fixture
def manifests(tmp_path):
    root = tmp_path / "m"
    write_dataset(root, "C", child_entities())
    write_dataset(root, "R", reads_entities())
    return root


@pytest.fixture
def imported(tmp_path, run_map, manifests):
    (result,) = el.import_all(
        run_map,
        manifests,
        tmp_path / "lin",
        tmp_path / "cache",
        fetch_runs=lambda studies, _progress: (
            REQUESTED,
            {a: r for a, r in RUNS.items() if r["study_accession"] in studies},
        ),
        read_stats_of=stats_of,
        read_header=header_of,
        generation=STAMP,
    )
    return result


def lines(result) -> list[dict]:
    return [row.model_dump(exclude_none=True) for row in iter_lineage(result.directory / "sample.ndjson")]


# --- the importer ----------------------------------------------------------------------


def test_each_alignment_is_counted_once_by_why(imported):
    assert dict(imported.outcomes) == {
        el.LINKED: 1,
        el.NO_RUN: 1,
        el.SEVERAL_RUNS: 1,
        el.READS_NOT_IN_DATASET: 1,
        el.NO_READ_STEP: 1,
        el.STATS_UNREADABLE: 1,
        el.NO_STATS: 1,
        el.SEVERAL_READ_STEPS: 1,
        el.HEADER_UNREADABLE: 1,
    }


def test_a_linked_alignment_gets_a_line_per_fastq_of_its_run_naming_the_reads_dataset(imported):
    common = {
        "target_key_value": "c1",
        "parent_key_type": "file_id",
        "parent_dataset": "R",
        "parent_source_identifier": "ERR1",
        "raw_activity": "bwa mem",
        "raw_activity_column": "@PG",
        "child_column": "cram",
        "parent_column": "fastq_ftp",
    }
    assert lines(imported) == [
        {**common, "parent": "r_ERR1_1.fastq.gz"},
        {**common, "parent": "r_ERR1_2.fastq.gz"},
    ]
    assert imported.written == 2


def test_the_envelope_is_enas_about_the_childs_dataset(imported):
    envelope = read_lineage_envelope(imported.directory / "sample.ndjson")
    assert (envelope.source.repository, envelope.source.table) == ("ena", "read_run")
    assert str(envelope.source_type) == SOURCE_EXTERNAL_GROUND_TRUTH
    assert (envelope.target.dataset, envelope.target.version, str(envelope.target_key)) == ("C", CATALOG, "file_id")


def test_a_run_of_an_undeclared_study_is_no_candidate(imported):
    """ERR_other has alignment 1's counts but is PRJEB2's; were it a candidate, 1 would be several_runs."""
    assert {line["parent_source_identifier"] for line in lines(imported)} == {"ERR1"}


def test_a_reimport_from_the_kept_inputs_reads_no_network_and_writes_the_same_lines(
    tmp_path, run_map, manifests, imported
):
    stored = el.load_inputs([imported.directory / "sample.inputs.json"])
    (again,) = el.import_all(
        run_map,
        manifests,
        tmp_path / "lin2",
        tmp_path / "cache",
        fetch_runs=must_not_fetch,
        read_stats_of=must_not_fetch,
        read_header=must_not_fetch,
        stored=stored,
        generation=STAMP,
    )
    assert lines(again) == lines(imported)
    assert again.outcomes == imported.outcomes


def test_an_import_linking_nothing_writes_nothing(tmp_path, run_map, manifests):
    with pytest.raises(ValueError, match="no alignment linked"):
        el.import_all(
            run_map,
            manifests,
            tmp_path / "lin",
            tmp_path / "cache",
            fetch_runs=lambda studies, _progress: (REQUESTED, {}),
            read_stats_of=stats_of,
            read_header=header_of,
            generation=STAMP,
        )
    assert not (tmp_path / "lin").exists() or not any((tmp_path / "lin").rglob("*.ndjson"))


def test_read_steps_takes_the_program_and_subcommand_of_each_line_naming_a_fastq():
    assert el.read_steps(BWA + FIXMATE) == ["bwa mem"]
    assert el.read_steps(FIXMATE) == []
    assert el.read_steps(BWA + MINIMAP) == ["bwa mem", "minimap2"]


def test_stats_counts_reads_raw_total_sequences_and_total_length():
    text = "# This file was produced by samtools stats\nSN\traw total sequences:\t697525866\nSN\ttotal length:\t104628879900\t# ignores clipping\n"
    assert el.stats_counts(text) == (697525866, 104628879900)
    with pytest.raises(ValueError, match="not samtools stats"):
        el.stats_counts("SN\traw total sequences:\t1\n")


# --- the map ---------------------------------------------------------------------------


def load(tmp_path, text: str) -> RunLineageMap:
    path = tmp_path / "m.yaml"
    path.write_text(text)
    return load_run_lineage_map(path)


ENTRY = "      - {{child: {{column: cram}}, counts: {{column: stats}}, ena_studies: [PRJEB1], reads_in: {reads}}}\n"


def two_way(child: str, reads: str, *more: tuple[str, str]) -> str:
    text = "catalog: anvil15\nsource: ena\ndatasets:\n"
    for c, r in ((child, reads), *more):
        text += f"  {c}:\n    sample:\n" + ENTRY.format(reads=r)
    return text


@pytest.mark.parametrize(
    "arrows, loop",
    [
        ([("A", "A")], "A -> A"),
        ([("A", "B"), ("B", "A")], "A -> B -> A"),
        ([("A", "B"), ("B", "C"), ("C", "A")], "A -> B -> C -> A"),
    ],
)
def test_the_map_refuses_a_loop_among_its_reads_datasets(tmp_path, arrows, loop):
    with pytest.raises(ValueError, match=f"reads_in loops {loop}"):
        load(tmp_path, two_way(*arrows[0], *arrows[1:]))


def test_a_chain_without_a_loop_loads(tmp_path):
    assert len(load(tmp_path, two_way("A", "B", ("B", "C"))).entries) == 2


@pytest.mark.parametrize(
    "text, fault",
    [
        (MAP.replace("[PRJEB1]", "[ERP1]"), "not a non-empty list of study accessions"),
        (MAP.replace("reads_in: R", "reads_in: R\n        notes: x"), "no notes member"),
        (MAP.replace("        reads_in: R\n", ""), "keys are"),
        (MAP.replace("{column: stats}", "{column: cram}"), "child and counts are both column"),
        (MAP.replace("catalog: anvil15\n", ""), "top-level keys"),
        (MAP + ENTRY.format(reads="R"), "a list of one entry"),
    ],
)
def test_the_map_refuses_a_malformed_entry(tmp_path, text, fault):
    with pytest.raises(ValueError, match=fault):
        load(tmp_path, text)


def test_the_map_declares_only_its_pairs_from_its_source_for_its_catalog(run_map):
    ena = {"source_type": SOURCE_EXTERNAL_GROUND_TRUTH, "repository": "ena"}
    assert run_map.declares(envelope("read_run", dataset="C", **ena), "R")
    assert not run_map.declares(envelope("read_run", dataset="C", **ena), "X")
    assert not run_map.declares(envelope("read_run", dataset="R", **ena), "C")
    assert not run_map.declares(envelope("read_run", dataset="C", version="anvil16", **ena), "R")
    assert not run_map.declares(envelope("sample", dataset="C", source_type=SOURCE_EXTERNAL_GROUND_TRUTH), "R")


def test_check_passes_a_map_the_deployment_and_manifests_agree_with(run_map, manifests):
    assert el.check(run_map, DEPLOYMENT, manifests) == []


def test_check_refuses_a_dataset_the_deployment_does_not_declare(run_map, manifests):
    only_c = dataclasses.replace(DEPLOYMENT, snapshots={"C": Snapshot("p", "C_snapshot")})
    assert el.check(run_map, only_c, manifests) == ["R: not a dataset the test deployment declares"]


def test_check_refuses_a_missing_table_or_column(tmp_path, manifests):
    no_table = load(tmp_path, MAP.replace("    sample:", "    samples:"))
    assert el.check(no_table, DEPLOYMENT, manifests) == ["C/samples: no row of this type in the manifest"]
    no_column = load(tmp_path, MAP.replace("{column: stats}", "{column: full_stats}"))
    assert el.check(no_column, DEPLOYMENT, manifests) == ["C/sample/full_stats: no row carries this column"]


def test_check_refuses_a_map_authored_against_another_catalog(run_map, manifests):
    newer = dataclasses.replace(DEPLOYMENT, catalog="anvil16")
    assert "run lineage map: authored against anvil15, not anvil16" in el.check(run_map, newer, manifests)


def test_a_run_holding_the_child_but_not_its_reads_dataset_is_refused(run_map):
    with pytest.raises(ValueError, match="C takes its reads from R, which the run does not hold"):
        run_map.require_in_run("anvil", CATALOG, ["C"])
    run_map.require_in_run("anvil", CATALOG, ["C", "R"])
    run_map.require_in_run("anvil", CATALOG, ["X"])
    run_map.require_in_run("anvil", "anvil16", ["C"])
    run_map.require_in_run("hprc", None, ["C"])


def test_the_bundled_map_loads():
    bundled = load_run_lineage_map()
    line = envelope("read_run", dataset="ANVIL_T2T_CHRY", version=bundled.catalog, repository=bundled.source)
    assert bundled.source == "ena" and bundled.declares(line, "ANVIL_T2T")


# --- reconcile -------------------------------------------------------------------------


def ena_lineage_file(lineage: Path, rows: list[LineageRow], repository: str = "ena") -> None:
    write_lineage(
        lineage, "read_run", rows, dataset="C", source_type=SOURCE_EXTERNAL_GROUND_TRUTH, repository=repository
    )


def read_line(parent: str, parent_dataset: str = "R") -> LineageRow:
    return LineageRow(
        target_key_value="c1",
        parent=parent,
        parent_key_type=LineageParentKeyEnum.file_id,
        parent_dataset=parent_dataset,
        parent_source_identifier="ERR1",
        raw_activity="bwa mem",
        raw_activity_column="@PG",
        child_column="cram",
        parent_column="fastq_ftp",
    )


def reconcile(tmp_path: Path, roots, run_map, datasets=None) -> tuple[dict[str, dict], dict]:
    evidence, _ = roots
    reads = {"assay_type": "WGS", "platform": "ILLUMINA", "instrument_model": "Illumina NovaSeq 6000"}
    rows = [
        output_record("s.cram", "m1", dataset="C", file_id="c1", data_type="alignments"),
        output_record("ERR1_1.fastq.gz", "a1", dataset="R", file_id="r1", data_type="reads", **reads),
        output_record("ERR1_2.fastq.gz", "a2", dataset="R", file_id="r2", data_type="reads", **reads),
    ]
    run_dir = write_run(tmp_path / "output" / "20261005_000000", rows)
    metadata = write_metadata(tmp_path / "input.json", [], repository="anvil", catalog=CATALOG)
    if datasets is not None:
        document = json.loads(metadata.read_text())
        document["metadata"]["datasets"] = {d: {} for d in datasets}
        metadata.write_text(json.dumps(document))
    report = reconcile_run(run_dir, metadata, evidence, run_lineage_map=run_map)
    return {r["file_name"]: r for r in iter_reconciled_records(run_dir)}, report


def test_a_declared_parent_in_another_dataset_gives_the_alignment_its_reads_answer(tmp_path, roots, run_map):
    _, lineage = roots
    ena_lineage_file(lineage, [read_line("r1"), read_line("r2")])
    rows, report = reconcile(tmp_path, roots, run_map)
    step = rows["s.cram"]["generated_by"]
    assert step["activity"] == "AlignmentActivity"
    assert sorted((i["role"], i["parent_key"]) for i in step["inputs"]) == [("reads", "r1"), ("reads", "r2")]
    for dimension, value in (("assay_type", "WGS"), ("instrument_model", "Illumina NovaSeq 6000")):
        entry = rows["s.cram"]["classifications"][dimension]
        assert (entry["value"], entry["credited_to"]) == (value, "inherited"), dimension
    assert report["lineage"]["sources"][SOURCE_EXTERNAL_GROUND_TRUTH]["C"]["resolved"] == 2


def test_an_undeclared_parent_dataset_is_counted_and_gives_nothing(tmp_path, roots, run_map):
    _, lineage = roots
    ena_lineage_file(lineage, [read_line("r1", parent_dataset="X")])
    rows, report = reconcile(tmp_path, roots, run_map)
    assert rows["s.cram"]["generated_by"] is None
    assert rows["s.cram"]["classifications"]["assay_type"]["status"] == "not_classified"
    assert report["lineage"]["sources"][SOURCE_EXTERNAL_GROUND_TRUTH]["C"][UNDECLARED_DATASET] == 1


def test_a_parent_dataset_from_a_source_other_than_ena_is_undeclared(tmp_path, roots, run_map):
    _, lineage = roots
    ena_lineage_file(lineage, [read_line("r1")], repository="somewhere")
    rows, report = reconcile(tmp_path, roots, run_map)
    assert rows["s.cram"]["generated_by"] is None
    assert report["lineage"]["sources"][SOURCE_EXTERNAL_GROUND_TRUTH]["C"][UNDECLARED_DATASET] == 1


def test_reconcile_refuses_a_run_holding_the_child_but_not_its_reads_dataset(tmp_path, roots, run_map):
    with pytest.raises(ReconcileError, match="C takes its reads from R"):
        reconcile(tmp_path, roots, run_map, datasets=["C"])


def test_progress_is_told_how_many_stats_files_and_headers_were_read(tmp_path, run_map, manifests):
    messages: list[str] = []
    el.import_all(
        run_map,
        manifests,
        tmp_path / "lin",
        tmp_path / "cache",
        fetch_runs=lambda studies, _progress: (REQUESTED, dict(RUNS)),
        read_stats_of=stats_of,
        read_header=header_of,
        generation=STAMP,
        progress=messages.append,
    )
    # Alignment 7 has no stats file; only 1, 5, 8 and 9 reach a run whose reads are in R, so only theirs are read.
    assert messages == ["C/sample: read 8 of 8 stats files", "C/sample: read 4 of 4 headers"]


class FlakyEna:
    """A session whose first ``failures`` file reports answer 500, then a report of ``RUNS``."""

    def __init__(self, failures: int):
        self.failures = failures
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, url, params, timeout):
        self.calls += 1
        response = requests.Response()
        response.url = url
        if self.calls <= self.failures:
            response.status_code = 500
            response._content, response._content_consumed = b"", True
            return response
        response.status_code = 200
        header = "\t".join(el.FIELDS)
        body = [header] + ["\t".join(run[f] for f in el.FIELDS) for run in RUNS.values()]
        response._content = ("\n".join(body) + "\n").encode()
        return response


def test_ena_server_errors_are_waited_out_then_raise(monkeypatch):
    monkeypatch.setattr(el.time, "sleep", lambda _s: None)
    flaky = FlakyEna(failures=3)
    monkeypatch.setattr(el.requests, "Session", lambda: flaky)
    waits: list[str] = []
    _, rows = el.fetch_study_runs(["PRJEB1"], waits.append)
    assert len(waits) == 3 and waits[0].startswith("ENA PRJEB1: HTTP 500; waiting")
    assert set(rows) == set(RUNS) and flaky.calls == 4
    monkeypatch.setattr(el.requests, "Session", lambda: FlakyEna(failures=1_000))
    with pytest.raises(RuntimeError, match="still returning HTTP 500"):
        el.fetch_study_runs(["PRJEB1"], lambda _m: None)


def test_a_dropped_connection_reading_a_stats_file_is_retried(monkeypatch):
    monkeypatch.setattr(el.time, "sleep", lambda _s: None)
    calls = []

    def head(md5, length):
        calls.append(md5)
        if len(calls) < el.STATS_ATTEMPTS:
            raise requests.ConnectionError("reset")
        return "SN\traw total sequences:\t5\nSN\ttotal length:\t750\n"

    monkeypatch.setattr(el, "fetch_head_text", head)
    assert el.read_stats("m") == (5, 750) and len(calls) == el.STATS_ATTEMPTS


def test_a_connection_dropped_on_every_try_is_a_fetch_error(monkeypatch):
    monkeypatch.setattr(el.time, "sleep", lambda _s: None)

    def head(md5, length):
        raise requests.ConnectionError("reset")

    monkeypatch.setattr(el, "fetch_head_text", head)
    with pytest.raises(FetchError, match="ConnectionError"):
        el.read_stats("m")


def test_a_stats_file_the_mirror_does_not_hold_is_not_retried(monkeypatch):
    calls = []

    def head(md5, length):
        calls.append(md5)
        raise FetchError("HTTP 404 from AnVIL S3 mirror range request")

    monkeypatch.setattr(el, "fetch_head_text", head)
    with pytest.raises(FetchError, match="404"):
        el.read_stats("m")
    assert len(calls) == 1


def test_a_malformed_md5_is_no_identity_to_read_by(tmp_path):
    """As the pipeline's load path holds (#376): the md5 is the S3 key and the header cache's file name."""
    entities = [
        ("anvil_file", {"file_id": "x", "file_name": "x.txt", "file_md5sum": "../../etc/passwd", "drs_uri": drs(1)}),
        ("anvil_file", {"file_id": "y", "file_name": "y.txt", "file_md5sum": md5("y").upper(), "drs_uri": drs(2)}),
    ]
    write_dataset(tmp_path / "m", "C", entities)
    path = tmp_path / "m" / "manifest" / CATALOG
    (manifest,) = path.glob("C*verbatim*")
    files = el.files_by_drs(manifest)
    assert files[drs(1)].md5 is None
    assert files[drs(2)].md5 is None  # uppercase, which the pipeline excludes too


def test_a_reimport_lacking_a_datasets_kept_inputs_is_refused_before_any_read(tmp_path, run_map, manifests):
    with pytest.raises(ValueError, match=r"no kept inputs for \['C'\]"):
        el.import_all(run_map, manifests, tmp_path / "lin", tmp_path / "cache", stored={}, generation=STAMP)


def test_an_import_reading_headers_itself_needs_samtools_up_front(tmp_path, run_map, manifests, monkeypatch):
    monkeypatch.setattr(el, "require_samtools", lambda: (_ for _ in ()).throw(RuntimeError("samtools not found")))
    with pytest.raises(RuntimeError, match="samtools not found"):
        el.import_all(run_map, manifests, tmp_path / "lin", tmp_path / "cache", fetch_runs=must_not_fetch)


def test_a_stats_file_is_the_one_the_rows_naming_the_alignment_give(tmp_path, run_map):
    files = [
        ("anvil_file", {"file_id": f"f{n}", "file_name": f"f{n}", "file_md5sum": md5(f"f{n}"), "drs_uri": drs(n)})
        for n in (1, 2, 3, 4)
    ]
    rows = [
        ("sample", {"cram": drs(1), "stats": None}),
        ("sample", {"cram": drs(1), "stats": drs(2)}),  # a second row of the same CRAM gives its stats file
        ("sample", {"cram": drs(3), "stats": [drs(2), drs(4)]}),  # two stats files: none is its one
    ]
    write_dataset(tmp_path / "m", "C", files + rows)
    (manifest,) = (tmp_path / "m" / "manifest" / CATALOG).glob("C*verbatim*")
    found = {c.file_id: s for c, s in el.alignments(manifest, run_map.entries[0], el.files_by_drs(manifest))}
    assert found["f1"] is not None and found["f1"].file_id == "f2"
    assert found["f3"] is None


def test_a_line_naming_its_own_dataset_is_refused():
    ena = envelope("read_run", dataset="C", source_type=SOURCE_EXTERNAL_GROUND_TRUTH, repository="ena")
    with pytest.raises(ValueError, match="child's own dataset"):
        write_lineage_file(Path("unused.ndjson"), ena, [read_line("r1", parent_dataset="C")])


def test_a_parent_dataset_without_a_parent_is_refused():
    line = LineageRow(
        target_key_value="c1",
        parent_source_identifier="ERR1",
        parent_dataset="R",
        child_column="cram",
        parent_column="fastq_ftp",
    )
    with pytest.raises(ValueError, match="present only with parent"):
        check_row(line, "line")


def test_an_undeclared_crossing_is_counted_before_the_activity_map(tmp_path, roots, run_map):
    """A line no authored row reads is still counted as the crossing it is, not as a step to author."""
    _, lineage = roots
    unread = read_line("r1", parent_dataset="X").model_copy(update={"raw_activity": "mystery"})
    ena_lineage_file(lineage, [unread])
    _, report = reconcile(tmp_path, roots, run_map)
    counts = report["lineage"]["sources"][SOURCE_EXTERNAL_GROUND_TRUTH]["C"]
    assert counts[UNDECLARED_DATASET] == 1 and "untranslated" not in counts
