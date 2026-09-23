"""The reconcile stage (#432): the join, translation, resolution, the artifact and the report.

One test per acceptance criterion of the issue, numbered ``ac<N>`` in its name. Fixtures
are a few output rows written through ``run_fixtures.write_run`` and a few evidence lines
written through ``write_evidence_file`` into the generation layout, so reconcile reads
them the way it reads a real run and a real import.
"""

import json
from pathlib import Path

import pytest

from meta_disco.corpus_diff import run_labels
from meta_disco.models import (
    CLASSIFIED,
    CONFLICT,
    JOIN_KEY_DRS_URI,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_METADATA,
    ClaimSource,
)
from meta_disco.output_utils import RECONCILED_DIR, iter_reconciled_records
from meta_disco.pipeline import PUBLISHED_TABLES
from meta_disco.reconcile import (
    REPORT_FILE,
    USE_META_DISCO,
    USE_PUBLISHED,
    ReconcileError,
    is_harmonized,
    reconcile_run,
    resolve_slot,
    use_for,
)
from meta_disco.rule_engine import make_claim
from meta_disco.schema.classification_model import ClassificationRecord
from meta_disco.schema_vocab import dimension_values
from meta_disco.source_evidence import EvidenceEntry, EvidenceFileSource, EvidenceTarget, claim_source_for
from tests.metadata_fixtures import write_metadata
from tests.run_fixtures import output_record, write_run
from tests.test_source_evidence import evidence_file_envelope, published_envelope
from tests.test_value_map import load, write_generation

DATASET = "AnVIL_TEST"
PUBLISHED_TABLE = PUBLISHED_TABLES["anvil"]

TABLE = """
rows:
  - id: reference_assembly.grch38
    match: {slot: reference_assembly, value: GRCh38, alternates: ["GRCh38 + Gencode40"]}
    declares: {reference_assembly: GRCh38}
    reason: The GRCh38 assembly, with or without the annotation named beside it.
  - id: reference_assembly.chm13
    match: {slot: reference_assembly, value: CHM13}
    declares: {reference_assembly: CHM13}
    reason: The CHM13 assembly.
  - id: reference_assembly.unaligned
    match: {slot: reference_assembly, value: unaligned}
    declares: {reference_assembly: not_applicable}
    reason: No reference.
  - id: platform.pacbio_smrt
    match: {slot: platform, value: PACBIO_SMRT}
    declares: {platform: PACBIO}
    reason: PacBio's SMRT sequencing.
  - id: platform.seeded_only
    match: {slot: platform, value: MYSTERY}
    seeded_from: ["anvil/anvil15/AnVIL_TEST/20260922T000000Z"]
"""


# --- fixtures -----------------------------------------------------------------------


def drs(n: int) -> str:
    return f"drs://drs.anv0:v2_{n}"


def record(n: int, dataset: str = DATASET, **dims) -> dict:
    row = output_record(f"f{n}.bam", f"md5-{n}", dataset=dataset, file_id=f"file-{n}", **dims)
    row["drs_uri"] = drs(n)
    return row


def write_input(tmp_path: Path, repository: str = "anvil", catalog: str | None = "anvil15") -> Path:
    return write_metadata(tmp_path / "input.json", [], repository=repository, catalog=catalog)


def lines_of(source: EvidenceFileSource, lines: list[tuple[str, str, str]], column: str) -> list[EvidenceEntry]:
    return [
        EvidenceEntry(field=f, target_key_value=key, raw_value=raw, source=claim_source_for(source, column))
        for f, key, raw in lines
    ]


def write_evidence(
    root: Path,
    lines: list[tuple[str, str, str]],
    *,
    table: str = "sequencing",
    column: str = "col",
    dataset: str = DATASET,
    version: str = "anvil15",
    target_key: str = JOIN_KEY_DRS_URI,
) -> None:
    """One submitter-table evidence file of ``(field, target_key_value, raw_value)`` lines."""
    source = EvidenceFileSource(repository="anvil", dataset=dataset, table=table, url="https://example.org")
    envelope = evidence_file_envelope(
        source=source,
        source_type=SOURCE_REPOSITORY_METADATA,
        source_version=version,
        source_key=JOIN_KEY_DRS_URI,
        target=EvidenceTarget(system="anvil", dataset=dataset, version=version),
        target_key=target_key,
    )
    write_generation(root, dataset, table, lines_of(source, lines, column), envelope=envelope)


def published(root: Path, lines: list[tuple[str, str, str]]) -> None:
    """One published-importer evidence file (#497) for ``DATASET``; each line's column is its slot."""
    envelope = published_envelope(dataset=DATASET, table=PUBLISHED_TABLE)
    entries = [e for line in lines for e in lines_of(envelope.source, [line], line[0])]
    write_generation(root, DATASET, PUBLISHED_TABLE, entries, envelope=envelope, source="anvil_published")


@pytest.fixture
def table(tmp_path: Path):
    return load(tmp_path, TABLE)


@pytest.fixture
def run(tmp_path: Path) -> Path:
    return tmp_path / "output" / "20260922_000000"


@pytest.fixture
def evidence(tmp_path: Path) -> Path:
    root = tmp_path / "evidence"
    root.mkdir()
    return root


def reconciled(run_dir: Path) -> dict[str, dict]:
    return {r["file_id"]: r for r in iter_reconciled_records(run_dir)}


def slot(run_dir: Path, n: int, dim: str) -> dict:
    return reconciled(run_dir)[f"file-{n}"]["classifications"][dim]


def go(run_dir: Path, tmp_path: Path, evidence_root: Path | None, table, **input_kwargs):
    return reconcile_run(run_dir, write_input(tmp_path, **input_kwargs), evidence_root, table)


# --- the join -----------------------------------------------------------------------


def test_ac1_line_attaches_to_the_one_record_carrying_its_drs_uri(tmp_path, run, evidence, table):
    write_run(run, [record(1, reference_assembly="GRCh38"), record(2)])
    write_evidence(evidence, [("reference_assembly", drs(1), "GRCh38")])
    go(run, tmp_path, evidence, table)
    records = reconciled(run)
    sources = [e for e in records["file-1"]["classifications"]["reference_assembly"]["evidence"] if "source" in e]
    assert len(sources) == 1 and sources[0]["join_key"] == JOIN_KEY_DRS_URI and sources[0]["match_exact"] is True
    assert not [e for e in records["file-2"]["classifications"]["reference_assembly"]["evidence"] if "source" in e]


def test_ac2_a_key_on_two_records_attaches_to_neither_and_names_both(tmp_path, run, evidence, table):
    one, two = record(1), record(2)
    two["drs_uri"] = drs(1)
    write_run(run, [one, two, record(3)])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT"), ("platform", drs(3), "PACBIO_SMRT")])
    result = go(run, tmp_path, evidence, table)
    (ev,) = result["evidence"]
    assert (ev["matched"], ev["ambiguous"]) == (1, 1)
    assert ev["ambiguous_examples"] == [{"drs_uri": drs(1), "file_id": ["file-1", "file-2"]}]
    assert slot(run, 1, "platform")["status"] == NOT_CLASSIFIED
    assert slot(run, 2, "platform")["status"] == NOT_CLASSIFIED


def test_ac3_an_evidence_file_matching_nothing_is_refused(tmp_path, run, evidence, table):
    write_run(run, [record(1)])
    write_evidence(evidence, [("platform", "drs://nowhere", "PACBIO_SMRT")], dataset="AnVIL_ELSEWHERE")
    with pytest.raises(ReconcileError, match=r"AnVIL_ELSEWHERE.*silence is not success"):
        go(run, tmp_path, evidence, table)
    assert not (run / RECONCILED_DIR).exists()


def test_ac4_the_report_lists_the_join_per_source_and_dataset(tmp_path, run, evidence, table):
    write_run(run, [record(1), record(2)])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT"), ("platform", "drs://gone", "PACBIO_SMRT")])
    published(evidence, [("reference_assembly", drs(2), '["GRCh38 + Gencode40"]')])
    result = go(run, tmp_path, evidence, table)
    rows = {(e["source_type"], e["dataset"]): e for e in result["evidence"]}
    submitter = rows[(SOURCE_REPOSITORY_METADATA, DATASET)]
    assert (submitter["offered"], submitter["matched"], submitter["unmatched"], submitter["ambiguous"]) == (2, 1, 1, 0)
    assert submitter["key"] == JOIN_KEY_DRS_URI and submitter["unmatched_examples"] == ["drs://gone"]
    assert rows[(SOURCE_PUBLISHED_VALUE, DATASET)]["matched"] == 1
    on_disk = json.loads((run / RECONCILED_DIR / REPORT_FILE).read_text())
    assert on_disk["evidence"] == result["evidence"]


def test_ac5_a_target_key_that_is_not_a_record_field_is_refused(tmp_path, run, evidence, table):
    write_run(run, [record(1)])
    write_evidence(evidence, [("platform", "SRR1", "PACBIO_SMRT")], target_key="archive_accession")
    with pytest.raises(ReconcileError, match="archive_accession"):
        go(run, tmp_path, evidence, table)


def test_only_the_inputs_catalog_is_read(tmp_path, run, evidence, table):
    """An older catalog's evidence stays on disk as history; a run on the newer catalog never reads it."""
    write_run(run, [record(1), record(2)])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT")], version="anvil14")
    write_evidence(evidence, [("platform", drs(2), "PACBIO_SMRT")], version="anvil15")
    result = go(run, tmp_path, evidence, table)
    assert [e["source_version"] for e in result["evidence"]] == ["anvil15"]
    assert result["skipped_evidence"] == []
    assert slot(run, 1, "platform")["status"] == NOT_CLASSIFIED
    assert slot(run, 2, "platform")["value"] == "PACBIO"


def test_a_damaged_inference_file_is_refused_not_read_short(tmp_path, run, table):
    write_run(run, [record(1), "not a record"])
    with pytest.raises(ValueError, match=r"bam_classifications\.json"):
        go(run, tmp_path, None, table)
    assert not (run / RECONCILED_DIR).exists()


def test_a_value_whose_authored_row_declares_nothing_is_scored_no_claim(tmp_path, run, evidence):
    table = load(
        tmp_path,
        TABLE
        + """
  - id: platform.bam
    match: {slot: platform, value: bam}
    declares: {}
    reason: A file format, not a platform.
""",
    )
    write_run(run, [record(1)])
    write_evidence(evidence, [("platform", drs(1), "bam")])
    result = go(run, tmp_path, evidence, table)
    assert result["inputs"][DATASET]["platform"][SOURCE_REPOSITORY_METADATA] == {"no_claim": 1}
    assert slot(run, 1, "platform")["status"] == NOT_CLASSIFIED


def test_evidence_about_another_system_is_skipped_and_a_repository_without_a_catalog_is_not_checked(
    tmp_path, run, evidence, table
):
    """HPRC has no catalog and no evidence: AnVIL's evidence is skipped and inference passes through."""
    row = record(1, platform="ILLUMINA")
    write_run(run, [row])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT")])
    result = go(run, tmp_path, evidence, table, repository="hprc", catalog=None)
    assert result["evidence"] == [] and len(result["skipped_evidence"]) == 1
    (only,) = iter_reconciled_records(run)
    assert only["classifications"]["platform"]["value"] == "ILLUMINA"


# --- translation and claims -----------------------------------------------------------


def test_ac6_an_authored_row_makes_one_claim_citing_its_row_raw_value_table_and_column(tmp_path, run, evidence, table):
    write_run(run, [record(1)])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT")], table="hifi", column="platform_name")
    go(run, tmp_path, evidence, table)
    (claim,) = [e for e in slot(run, 1, "platform")["evidence"] if "source" in e]
    assert claim["rule_id"] == "platform.pacbio_smrt" and claim["raw_value"] == "PACBIO_SMRT"
    assert claim["value"] == "PACBIO" and claim["source_type"] == SOURCE_REPOSITORY_METADATA
    assert (claim["source"]["table"], claim["source"]["column"]) == ("hifi", "platform_name")


def test_ac7_a_seeded_row_makes_no_claim(tmp_path, run, evidence, table):
    write_run(run, [record(1)])
    write_evidence(evidence, [("platform", drs(1), "MYSTERY")])
    result = go(run, tmp_path, evidence, table)
    platform = slot(run, 1, "platform")
    assert platform["status"] == NOT_CLASSIFIED and not [e for e in platform["evidence"] if "source" in e]
    assert result["inputs"][DATASET]["platform"][SOURCE_REPOSITORY_METADATA] == {"unreviewed": 1}


# --- resolution -----------------------------------------------------------------------


def claim(value=None, status=None, source_type=SOURCE_REPOSITORY_METADATA, raw=None) -> dict:
    """A source claim as ``claims_from`` makes one: through ``make_claim``, citing a row and carrying its raw value."""
    return make_claim(
        source_type=source_type,
        rule_id="platform.test",
        value=value,
        status=status,
        source=ClaimSource(name="anvil", dataset=DATASET, table="sequencing", column="col"),
        raw_value=raw if raw is not None else (value or status),
    )


def inferred(status: str, value: str | None = None) -> dict:
    return {"value": value, "status": status}


def test_ac8_agreement_classifies():
    assert resolve_slot(inferred(CLASSIFIED, "GRCh38"), [claim("GRCh38")], False) == (CLASSIFIED, "GRCh38")


def test_ac9_a_source_fills_a_gap_inference_left():
    assert resolve_slot(inferred(NOT_CLASSIFIED, None), [claim("PACBIO")], False) == (CLASSIFIED, "PACBIO")


def test_ac10_disagreement_is_a_conflict_with_both_declarations_recorded(tmp_path, run, evidence, table):
    write_run(run, [record(1, reference_assembly="GRCh38")])
    write_evidence(evidence, [("reference_assembly", drs(1), "CHM13")])
    go(run, tmp_path, evidence, table)
    ref = slot(run, 1, "reference_assembly")
    assert (ref["status"], ref["value"], ref["use"]) == (CONFLICT, None, USE_PUBLISHED)
    # Inference's declaration is its conclusion, with its own evidence kept as it was;
    # the source's is the claim citing the translation row behind it.
    assert ref["inferred"] == {"value": "GRCh38", "status": CLASSIFIED}
    (source,) = [e for e in ref["evidence"] if "source" in e]
    assert (source["value"], source["rule_id"]) == ("CHM13", "reference_assembly.chm13")


def test_ac11_not_applicable_beside_a_value_is_a_conflict():
    assert resolve_slot(inferred(NOT_APPLICABLE, None), [claim("GRCh38")], False) == (CONFLICT, None)
    assert use_for(CONFLICT) == USE_PUBLISHED


def test_ac12_not_classified_yields_to_not_applicable():
    assert resolve_slot(inferred(NOT_CLASSIFIED, None), [claim(status=NOT_APPLICABLE)], False) == (NOT_APPLICABLE, None)


def test_ac13_two_agreeing_sources_and_a_silent_inference():
    two = [claim("PACBIO"), claim("PACBIO", source_type=SOURCE_PUBLISHED_VALUE)]
    assert resolve_slot(inferred(NOT_CLASSIFIED, None), two, False) == (CLASSIFIED, "PACBIO")


def test_ac14_an_inference_conflict_stands_beside_a_source_value():
    assert resolve_slot(inferred(CONFLICT, None), [claim("PACBIO")], False) == (CONFLICT, None)


# --- the artifacts ----------------------------------------------------------------------


def test_ac15_without_evidence_reconcile_concludes_what_inference_did_and_leaves_it_untouched(tmp_path, run, table):
    rows = [
        record(1, reference_assembly="GRCh38", platform="ILLUMINA"),
        record(2, reference_assembly=CONFLICT),
        record(3, data_type=NOT_APPLICABLE),
        record(4),
    ]
    write_run(run, rows)
    before = (run / "bam_classifications.json").read_bytes()
    result = go(run, tmp_path, None, table)
    assert (run / "bam_classifications.json").read_bytes() == before
    assert result["evidence_excluded"] is True
    for original, settled in zip(rows, iter_reconciled_records(run), strict=True):
        for dim, entry in original["classifications"].items():
            assert (settled["classifications"][dim]["status"], settled["classifications"][dim]["value"]) == (
                entry["status"],
                entry["value"],
            )


def test_ac16_the_same_inputs_write_the_same_bytes(tmp_path, run, evidence, table):
    write_run(run, [record(1, reference_assembly="GRCh38"), record(2)])
    write_evidence(evidence, [("reference_assembly", drs(1), "CHM13"), ("platform", drs(2), "PACBIO_SMRT")])
    go(run, tmp_path, evidence, table)
    first = {p.name: p.read_bytes() for p in (run / RECONCILED_DIR).iterdir()}
    go(run, tmp_path, evidence, table)
    assert {p.name: p.read_bytes() for p in (run / RECONCILED_DIR).iterdir()} == first


def test_ac17_reconciled_and_inference_records_validate_against_the_schema(tmp_path, run, evidence, table):
    rows = [record(1, reference_assembly="GRCh38"), record(2)]
    write_run(run, rows)
    write_evidence(evidence, [("reference_assembly", drs(1), "CHM13"), ("platform", drs(2), "PACBIO_SMRT")])
    go(run, tmp_path, evidence, table)
    for row in [*rows, *iter_reconciled_records(run)]:
        ClassificationRecord(**row)


def test_ac18_reconcile_writes_ndjson_in_its_own_subdirectory(tmp_path, run, table):
    write_run(run, [record(1)])
    go(run, tmp_path, None, table)
    lines = (run / RECONCILED_DIR / "bam_classifications.ndjson").read_text().splitlines()
    assert "reconcile" in json.loads(lines[0]) and json.loads(lines[1])["file_id"] == "file-1"
    assert (run / "bam_classifications.json").exists()


def test_ac19_a_reconciled_slot_reads_alone(tmp_path, run, evidence, table):
    write_run(run, [record(1, platform="PACBIO")])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT")])
    go(run, tmp_path, evidence, table)
    platform = slot(run, 1, "platform")
    assert platform["inferred"] == {"value": "PACBIO", "status": CLASSIFIED}
    assert {e.get("source_type") for e in platform["evidence"]} >= {SOURCE_REPOSITORY_METADATA}
    assert (platform["status"], platform["value"], platform["use"]) == (CLASSIFIED, "PACBIO", USE_META_DISCO)


def test_ac20_a_published_value_is_a_declaration_citing_its_table_and_column(tmp_path, run, evidence, table):
    write_run(run, [record(1)])
    published(evidence, [("reference_assembly", drs(1), '["GRCh38 + Gencode40"]')])
    go(run, tmp_path, evidence, table)
    ref = slot(run, 1, "reference_assembly")
    (claim_,) = [e for e in ref["evidence"] if "source" in e]
    assert claim_["source_type"] == SOURCE_PUBLISHED_VALUE
    assert (claim_["source"]["table"], claim_["source"]["column"]) == (PUBLISHED_TABLE, "reference_assembly")
    assert (ref["status"], ref["value"]) == (CLASSIFIED, "GRCh38")


def test_ac21_corpus_diff_requires_the_artifact(tmp_path, run, table):
    write_run(run, [record(1, platform="ILLUMINA")])
    with pytest.raises(TypeError):
        run_labels(run)  # type: ignore[call-arg]
    with pytest.raises(FileNotFoundError, match="reconcile"):
        run_labels(run, "reconciled")
    go(run, tmp_path, None, table)
    assert run_labels(run, "reconciled") == run_labels(run, "inference")


def test_ac21_compare_corpus_refuses_without_an_artifact(capsys):
    from compare_corpus import main

    with pytest.raises(SystemExit):
        main([])
    assert "--artifact" in capsys.readouterr().err


# --- delivery ---------------------------------------------------------------------------


def test_ac23_use_follows_the_status_and_value_is_null_unless_classified():
    assert use_for(CLASSIFIED) == use_for(NOT_APPLICABLE) == USE_META_DISCO
    assert use_for(CONFLICT) == use_for(NOT_CLASSIFIED) == USE_PUBLISHED
    for status, value in (
        resolve_slot(inferred(CLASSIFIED, "GRCh38"), [claim("CHM13")], False),
        resolve_slot(inferred(NOT_CLASSIFIED, None), [], True),
        resolve_slot(inferred(NOT_APPLICABLE, None), [], False),
    ):
        assert (value is None) == (status != CLASSIFIED)


def test_ac24_a_harmonized_published_value_agrees_and_is_scored_harmonized(tmp_path, run, evidence, table):
    write_run(run, [record(1, reference_assembly="GRCh38")])
    published(evidence, [("reference_assembly", drs(1), '["GRCh38 + Gencode40"]')])
    result = go(run, tmp_path, evidence, table)
    ref = slot(run, 1, "reference_assembly")
    assert (ref["status"], ref["value"], ref["use"]) == (CLASSIFIED, "GRCh38", USE_META_DISCO)
    scored = result["inputs"][DATASET]["reference_assembly"]
    assert scored[SOURCE_PUBLISHED_VALUE] == {"harmonized": 1} and scored["inference"] == {"agreed": 1}


def test_is_harmonized_reads_a_one_element_list_cell_as_its_element():
    assert not is_harmonized(claim("GRCh38", raw='["GRCh38"]'))
    assert is_harmonized(claim("genomic", raw="GENOMIC"))


def test_ac25_an_unreviewed_published_value_beside_another_input_is_a_conflict(tmp_path, run, evidence, table):
    write_run(run, [record(1, reference_assembly="GRCh38")])
    published(evidence, [("reference_assembly", drs(1), '["GRCm39"]')])
    result = go(run, tmp_path, evidence, table)
    ref = slot(run, 1, "reference_assembly")
    assert (ref["status"], ref["value"], ref["use"]) == (CONFLICT, None, USE_PUBLISHED)
    assert result["inputs"][DATASET]["reference_assembly"][SOURCE_PUBLISHED_VALUE] == {"unreviewed": 1}


def test_ac26_an_unreviewed_published_value_alone_is_missing_work_not_a_conflict(tmp_path, run, evidence, table):
    write_run(run, [record(1)])
    published(evidence, [("reference_assembly", drs(1), '["GRCm39"]')])
    result = go(run, tmp_path, evidence, table)
    ref = slot(run, 1, "reference_assembly")
    assert (ref["status"], ref["value"], ref["use"]) == (NOT_CLASSIFIED, None, USE_PUBLISHED)
    counts = result["slots"][DATASET]["reference_assembly"]
    assert counts.get("missing_work") == 1 and CONFLICT not in counts


def test_ac27_no_reconciled_value_is_outside_the_vocabulary(tmp_path, run, evidence, table):
    write_run(run, [record(1), record(2, reference_assembly="GRCh38")])
    published(evidence, [("reference_assembly", drs(1), '["GRCm39"]'), ("reference_assembly", drs(2), "CHM13")])
    go(run, tmp_path, evidence, table)
    for row in iter_reconciled_records(run):
        for dim, entry in row["classifications"].items():
            assert entry["value"] is None or entry["value"] in dimension_values(dim)


# --- the report ---------------------------------------------------------------------------


def test_the_report_scores_inference_and_counts_filled_and_agreed_slots(tmp_path, run, evidence, table):
    write_run(run, [record(1, platform="PACBIO"), record(2), record(3, platform="ILLUMINA")])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT"), ("platform", drs(2), "PACBIO_SMRT")])
    result = go(run, tmp_path, evidence, table)
    counts = result["slots"][DATASET]["platform"]
    assert (counts["agreed"], counts["filled"], counts["inference_only"]) == (1, 1, 1)
    assert result["inputs"][DATASET]["platform"]["inference"] == {"agreed": 1, "added": 1, "silent": 1}
    assert result["conflict_rate"][DATASET]["platform"] == 0.0


def test_a_source_is_not_scored_on_a_dataset_its_evidence_does_not_cover(tmp_path, run, evidence, table):
    write_run(run, [record(1), record(2, dataset="AnVIL_OTHER")])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT")])
    result = go(run, tmp_path, evidence, table)
    assert SOURCE_REPOSITORY_METADATA not in result["inputs"]["AnVIL_OTHER"]["platform"]


def test_a_file_md5sum_key_is_read_from_the_rows_md5sum(tmp_path, run, evidence, table):
    """The schema's key terms are the input's spellings; the output row renames only the checksum."""
    write_run(run, [record(1)])
    write_evidence(evidence, [("platform", "md5-1", "PACBIO_SMRT")], target_key="file_md5sum")
    result = go(run, tmp_path, evidence, table)
    assert result["evidence"][0]["matched"] == 1
    assert slot(run, 1, "platform")["value"] == "PACBIO"


def test_the_join_runs_within_the_envelopes_target_dataset(tmp_path, run, evidence, table):
    """Two records carrying one key in two datasets are not ambiguous to evidence scoped to one of them."""
    other = record(2, dataset="AnVIL_OTHER")
    other["drs_uri"] = drs(1)
    write_run(run, [record(1), other])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT")])
    result = go(run, tmp_path, evidence, table)
    assert (result["evidence"][0]["matched"], result["evidence"][0]["ambiguous"]) == (1, 0)
    assert slot(run, 1, "platform")["value"] == "PACBIO"
    assert slot(run, 2, "platform")["status"] == NOT_CLASSIFIED
