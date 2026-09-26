"""The reconcile stage (#432): the join, translation, resolution, the artifact and the report.

A test for each acceptance criterion a fixture can check, numbered ``ac<N>`` in its name;
criterion 22 is the real run, whose numbers are on the pull request. Fixtures
are a few output rows written through ``run_fixtures.write_run`` and a few evidence lines
written through ``write_evidence_file`` into the generation layout, so reconcile reads
them the way it reads a real run and a real import.
"""

import json
from pathlib import Path

import pytest

from meta_disco.corpus_diff import run_labels
from meta_disco.models import (
    CLASSIFICATION_FIELDS,
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
    SLOT_CATEGORIES,
    USE_META_DISCO,
    USE_PUBLISHED,
    ReconcileError,
    Report,
    SlotEvidence,
    is_harmonized,
    reconcile_run,
    resolve_slot,
    use_for,
)
from meta_disco.rule_engine import conflict_marker, make_claim
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
  - id: reference_assembly.chm13v2
    match: {slot: reference_assembly, value: CHM13v2}
    declares: {reference_assembly: T2T-CHM13v2.0}
    reason: The v2.0 release.
  - id: reference_assembly.chm13v1
    match: {slot: reference_assembly, value: CHM13v1}
    declares: {reference_assembly: T2T-CHM13v1.0}
    reason: The v1.0 release.
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
    write_evidence(evidence, [("platform", "SRR1", "PACBIO_SMRT")], target_key="file_path")
    with pytest.raises(ReconcileError, match="file_path"):
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


def test_a_row_declaring_two_slots_claims_the_slot_its_line_does_not_name(tmp_path, run, evidence):
    """A line on `platform` reaches `instrument_model` through a two-slot row (contract 3.10, #532)."""
    two_slots = load(
        tmp_path,
        TABLE
        + """  - id: platform.revio
    match: {slot: platform, value: Revio}
    declares: {platform: PACBIO, instrument_model: Revio}
    reason: A PacBio instrument model.
""",
    )
    write_run(run, [record(1)])
    write_evidence(evidence, [("platform", drs(1), "Revio")], table="hifi", column="instrument_model")
    go(run, tmp_path, evidence, two_slots)
    model = slot(run, 1, "instrument_model")
    assert (model["status"], model["value"]) == (CLASSIFIED, "Revio")
    (claim,) = [e for e in model["evidence"] if "source" in e]
    assert claim["rule_id"] == "platform.revio" and claim["raw_value"] == "Revio"
    assert claim["source"]["column"] == "instrument_model"
    assert slot(run, 1, "platform")["value"] == "PACBIO"


def test_ac7_a_seeded_row_makes_no_claim(tmp_path, run, evidence, table):
    write_run(run, [record(1)])
    write_evidence(evidence, [("platform", drs(1), "MYSTERY")])
    result = go(run, tmp_path, evidence, table)
    platform = slot(run, 1, "platform")
    # No claim, and a submitter value moves nothing, so the record carries nothing of it.
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
    assert resolve_slot("reference_assembly", inferred(CLASSIFIED, "GRCh38"), [claim("GRCh38")], False) == (
        CLASSIFIED,
        "GRCh38",
    )


def test_ac9_a_source_fills_a_gap_inference_left():
    assert resolve_slot("platform", inferred(NOT_CLASSIFIED, None), [claim("PACBIO")], False) == (CLASSIFIED, "PACBIO")


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


def test_the_report_counts_each_datasets_values_and_they_sum_to_its_files(tmp_path, run, evidence, table):
    """Per dataset and slot, a file is counted under its reconciled value, or its status where it has none (#545)."""
    write_run(run, [record(1, reference_assembly="GRCh38"), record(2, reference_assembly="GRCh38"), record(3)])
    write_evidence(evidence, [("reference_assembly", drs(1), "CHM13")])
    report = go(run, tmp_path, evidence, table)
    assert report["values"][DATASET]["reference_assembly"] == {"GRCh38": 1, CONFLICT: 1, NOT_CLASSIFIED: 1}
    assert set(report["values"][DATASET]) == set(CLASSIFICATION_FIELDS)
    for slot, counts in report["values"][DATASET].items():
        assert sum(counts.values()) == report["files"][DATASET], slot


def test_ac11_not_applicable_beside_a_value_is_a_conflict():
    assert resolve_slot("reference_assembly", inferred(NOT_APPLICABLE, None), [claim("GRCh38")], False) == (
        CONFLICT,
        None,
    )
    assert use_for(CONFLICT) == USE_PUBLISHED


def test_ac12_not_classified_yields_to_not_applicable():
    assert resolve_slot(
        "reference_assembly", inferred(NOT_CLASSIFIED, None), [claim(status=NOT_APPLICABLE)], False
    ) == (NOT_APPLICABLE, None)


def test_ac13_two_agreeing_sources_and_a_silent_inference():
    two = [claim("PACBIO"), claim("PACBIO", source_type=SOURCE_PUBLISHED_VALUE)]
    assert resolve_slot("platform", inferred(NOT_CLASSIFIED, None), two, False) == (CLASSIFIED, "PACBIO")


def test_ac14_an_inference_conflict_stands_beside_a_source_value():
    assert resolve_slot("platform", inferred(CONFLICT, None), [claim("PACBIO")], False) == (CONFLICT, None)


def test_values_that_nest_agree_and_the_deepest_is_the_value():
    """``CHM13`` and one of its releases are one answer at two levels of detail (#473), either way round."""
    release = "T2T-CHM13v2.0"
    assert resolve_slot("reference_assembly", inferred(CLASSIFIED, release), [claim("CHM13")], False) == (
        CLASSIFIED,
        release,
    )
    assert resolve_slot("reference_assembly", inferred(CLASSIFIED, "CHM13"), [claim(release)], False) == (
        CLASSIFIED,
        release,
    )


def test_sibling_releases_still_conflict():
    """Two releases do not nest: neither is the other's parent (#473)."""
    got = resolve_slot("reference_assembly", inferred(CLASSIFIED, "T2T-CHM13v1.0"), [claim("T2T-CHM13v2.0")], False)
    assert got == (CONFLICT, None)


def test_a_source_naming_the_parent_agrees_but_is_not_credited_with_the_release(tmp_path, run, evidence, table):
    write_run(run, [record(1, reference_assembly="T2T-CHM13v2.0")])
    write_evidence(evidence, [("reference_assembly", drs(1), "CHM13")])
    result = go(run, tmp_path, evidence, table)
    ref = slot(run, 1, "reference_assembly")
    assert (ref["status"], ref["value"], ref["use"]) == (CLASSIFIED, "T2T-CHM13v2.0", USE_META_DISCO)
    assert result["slots"][DATASET]["reference_assembly"] == {"filled_by_inference": 1}
    scored = result["inputs"][DATASET]["reference_assembly"]
    assert scored["inference"] == {"agreed": 1} and scored[SOURCE_REPOSITORY_METADATA] == {"match": 1}


def test_a_source_naming_the_release_fills_it_over_inferences_family(tmp_path, run, evidence, table):
    write_run(run, [record(1, reference_assembly="CHM13")])
    write_evidence(evidence, [("reference_assembly", drs(1), "CHM13v2")])
    result = go(run, tmp_path, evidence, table)
    ref = slot(run, 1, "reference_assembly")
    assert (ref["status"], ref["value"]) == (CLASSIFIED, "T2T-CHM13v2.0")
    assert result["slots"][DATASET]["reference_assembly"] == {"filled_by_submitter_harmonized": 1}


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
        resolve_slot("reference_assembly", inferred(CLASSIFIED, "GRCh38"), [claim("CHM13")], False),
        resolve_slot("reference_assembly", inferred(NOT_CLASSIFIED, None), [], True),
        resolve_slot("reference_assembly", inferred(NOT_APPLICABLE, None), [], False),
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
    # The record shows why on its own (6.10): what the published source said, declaring nothing.
    (seen,) = [e for e in ref["evidence"] if "source" in e]
    assert seen["claim_state"] == "unmapped" and seen["raw_value"] == '["GRCm39"]'
    assert seen["source_type"] == SOURCE_PUBLISHED_VALUE and "value" not in seen and "rule_id" not in seen


def test_ac26_an_unreviewed_published_value_alone_is_missing_work_not_a_conflict(tmp_path, run, evidence, table):
    write_run(run, [record(1)])
    published(evidence, [("reference_assembly", drs(1), '["GRCm39"]')])
    result = go(run, tmp_path, evidence, table)
    ref = slot(run, 1, "reference_assembly")
    assert (ref["status"], ref["value"], ref["use"]) == (NOT_CLASSIFIED, None, USE_PUBLISHED)
    counts = result["slots"][DATASET]["reference_assembly"]
    assert counts == {"published_unreviewed": 1}


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
    # Files 1 and 2 are attributed to the submitter (verbatim PACBIO_SMRT -> PACBIO is harmonized), whether
    # or not inference agreed; file 3's ILLUMINA is inference alone.
    assert counts == {"filled_by_submitter_harmonized": 2, "filled_by_inference": 1}
    assert result["inputs"][DATASET]["platform"]["inference"] == {"agreed": 1, "added": 1, "silent": 1}
    assert result["conflict_rate"][DATASET]["platform"] == 0.0


def test_a_source_is_scored_only_on_slots_it_speaks_to(tmp_path, run, evidence, table):
    write_run(run, [record(1, platform="PACBIO", data_type="alignments")])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT")])
    result = go(run, tmp_path, evidence, table)
    assert result["slots"][DATASET]["data_type"] == {"filled_by_inference": 1}
    assert SOURCE_REPOSITORY_METADATA not in result["inputs"][DATASET]["data_type"]


def test_the_published_source_speaks_to_its_columns_in_every_dataset(tmp_path, run, evidence, table):
    """A published column empty for a whole dataset leaves no line there, and is still that source's silence."""
    write_run(run, [record(1, reference_assembly="GRCh38", data_modality="genomic")])
    published(evidence, [("reference_assembly", drs(1), '["GRCh38 + Gencode40"]')])
    other = published_envelope(dataset="AnVIL_OTHER", table=PUBLISHED_TABLE)
    write_generation(
        evidence,
        "AnVIL_OTHER",
        PUBLISHED_TABLE,
        lines_of(other.source, [("data_modality", drs(9), '["genomic"]')], "data_modality"),
        envelope=other,
        source="anvil_published",
    )
    write_run(run, [record(1, reference_assembly="GRCh38", data_modality="genomic"), record(9, dataset="AnVIL_OTHER")])
    result = go(run, tmp_path, evidence, table)
    assert result["inputs"][DATASET]["data_modality"][SOURCE_PUBLISHED_VALUE] == {"silent": 1}
    assert result["added_over_published"][DATASET] == {"data_modality": 1}


def test_an_input_is_scored_disagreed_only_when_another_input_declared_differently(tmp_path, run, evidence, table):
    """A conflict made by an unreviewed published value is nobody's disagreement; a different value is."""
    write_run(run, [record(1, reference_assembly="GRCh38"), record(2, reference_assembly="GRCh38")])
    write_evidence(evidence, [("reference_assembly", drs(1), "GRCh38"), ("reference_assembly", drs(2), "CHM13")])
    published(evidence, [("reference_assembly", drs(1), '["GRCm39"]')])
    result = go(run, tmp_path, evidence, table)
    assert slot(run, 1, "reference_assembly")["status"] == slot(run, 2, "reference_assembly")["status"] == CONFLICT
    scored = result["inputs"][DATASET]["reference_assembly"]
    assert scored["inference"] == {"agreed": 1, "disagreed": 1}
    assert scored[SOURCE_REPOSITORY_METADATA] == {"match": 1, "disagreed": 1}


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


def test_an_inferred_value_outside_its_dimensions_vocabulary_is_refused(tmp_path, run, table):
    write_run(run, [record(1, data_modality="genomic")])
    go(run, tmp_path, None, table)
    (row,) = iter_reconciled_records(run)
    row["classifications"]["data_modality"]["inferred"]["value"] = "PACBIO"
    with pytest.raises(ValueError, match="PACBIO"):
        ClassificationRecord(**row)


def test_an_empty_evidence_file_is_refused(tmp_path, run, evidence, table):
    write_run(run, [record(1)])
    write_evidence(evidence, [])
    with pytest.raises(ReconcileError, match="no lines is silent too"):
        go(run, tmp_path, evidence, table)


def test_a_record_missing_a_slot_is_refused(tmp_path, run, table):
    row = record(1)
    del row["classifications"]["platform"]["status"]
    write_run(run, [row])
    with pytest.raises(ValueError, match="platform"):
        go(run, tmp_path, None, table)
    assert not (run / RECONCILED_DIR).exists()


def test_metadata_added_over_published_counts_our_values_where_the_published_source_was_silent(
    tmp_path, run, evidence, table
):
    write_run(run, [record(1, reference_assembly="GRCh38"), record(2, reference_assembly="GRCh38")])
    published(evidence, [("reference_assembly", drs(1), '["GRCh38 + Gencode40"]')])
    result = go(run, tmp_path, evidence, table)
    # File 1: published spoke (harmonized). File 2: published covers the slot here and said nothing.
    assert result["added_over_published"] == {DATASET: {"reference_assembly": 1}}


def test_a_value_where_the_published_source_has_no_column_is_added_over_published(tmp_path, run, evidence, table):
    """The published map declares no platform column, so every platform value we deliver is added."""
    write_run(run, [record(1, platform="PACBIO", reference_assembly="GRCh38")])
    published(evidence, [("reference_assembly", drs(1), '["GRCh38 + Gencode40"]')])
    result = go(run, tmp_path, evidence, table)
    assert result["added_over_published"] == {DATASET: {"platform": 1}}


def test_nothing_is_added_over_published_where_its_evidence_was_not_read(tmp_path, run, table):
    """Without the published source's evidence what it publishes is not known, so nothing is counted."""
    write_run(run, [record(1, platform="PACBIO")])
    assert go(run, tmp_path, None, table)["added_over_published"] == {}


def test_an_interrupted_swap_is_restored_not_lost(tmp_path, run, table):
    write_run(run, [record(1)])
    go(run, tmp_path, None, table)
    (run / RECONCILED_DIR).rename(run / f"{RECONCILED_DIR}.replaced")  # died between the renames
    real = run / "bam_classifications.json"
    real.write_text("not json")  # the next run fails before its swap
    with pytest.raises(ValueError):
        go(run, tmp_path, None, table)
    assert (run / RECONCILED_DIR / "bam_classifications.ndjson").exists()


def test_a_value_is_attributed_by_source_precedence_verbatim_before_harmonized(tmp_path, run, evidence, table):
    write_run(run, [record(n, reference_assembly="GRCh38") for n in (1, 2, 3)])
    write_evidence(evidence, [("reference_assembly", drs(1), "GRCh38"), ("reference_assembly", drs(2), "GRCh38")])
    published(evidence, [("reference_assembly", drs(2), '["GRCh38 + Gencode40"]')])
    result = go(run, tmp_path, evidence, table)
    # 1: submitter verbatim. 2: published (harmonized) outranks submitter verbatim. 3: inference alone.
    assert result["slots"][DATASET]["reference_assembly"] == {
        "filled_by_submitter": 1,
        "filled_by_published_harmonized": 1,
        "filled_by_inference": 1,
    }


def test_a_dataset_with_no_published_file_is_one_where_the_published_source_is_silent(tmp_path, run, evidence, table):
    """The importer writes no file for a dataset whose published columns are all empty."""
    write_run(
        run,
        [
            record(1, reference_assembly="GRCh38"),
            record(2, dataset="AnVIL_NOTHING_PUBLISHED", reference_assembly="CHM13"),
        ],
    )
    published(evidence, [("reference_assembly", drs(1), '["GRCh38 + Gencode40"]')])
    result = go(run, tmp_path, evidence, table)
    assert result["added_over_published"] == {"AnVIL_NOTHING_PUBLISHED": {"reference_assembly": 1}}
    assert result["inputs"]["AnVIL_NOTHING_PUBLISHED"]["reference_assembly"][SOURCE_PUBLISHED_VALUE] == {"silent": 1}


def test_a_conflict_is_counted_by_who_disagreed(tmp_path, run, evidence, table):
    write_run(
        run,
        [
            record(1, reference_assembly=CONFLICT),  # inference's own rules disagreed
            record(2, reference_assembly="GRCh38"),  # the submitter says CHM13
            record(3, reference_assembly="GRCh38"),  # the published value is unreviewed
            record(4, reference_assembly="GRCh38"),  # the published value says CHM13
        ],
    )
    write_evidence(evidence, [("reference_assembly", drs(1), "GRCh38"), ("reference_assembly", drs(2), "CHM13")])
    published(evidence, [("reference_assembly", drs(3), '["GRCm39"]'), ("reference_assembly", drs(4), "CHM13")])
    result = go(run, tmp_path, evidence, table)
    assert result["slots"][DATASET]["reference_assembly"] == {
        "conflict_inference": 1,
        "conflict_sources": 1,
        "conflict_published": 2,
    }
    assert result["conflict_rate"][DATASET]["reference_assembly"] == 1.0


def test_a_value_mapped_to_not_classified_is_scored_no_claim(tmp_path, run, evidence):
    table = load(
        tmp_path,
        TABLE
        + """
  - id: platform.unknown
    match: {slot: platform, value: unknown}
    declares: {platform: not_classified}
    reason: The source's word for a platform it did not record.
""",
    )
    write_run(run, [record(1)])
    write_evidence(evidence, [("platform", drs(1), "unknown")])
    result = go(run, tmp_path, evidence, table)
    assert result["inputs"][DATASET]["platform"][SOURCE_REPOSITORY_METADATA] == {"no_claim": 1}


def test_the_published_source_speaks_to_every_column_its_map_declares(tmp_path, run, evidence, table):
    """A published column empty in every dataset writes no line; the map still says the source covers it."""
    write_run(run, [record(1, reference_assembly="GRCh38", data_modality="genomic")])
    published(evidence, [("reference_assembly", drs(1), '["GRCh38 + Gencode40"]')])  # no data_modality line anywhere
    result = go(run, tmp_path, evidence, table)
    assert result["inputs"][DATASET]["data_modality"][SOURCE_PUBLISHED_VALUE] == {"silent": 1}
    assert result["added_over_published"][DATASET] == {"data_modality": 1}


def test_a_run_with_two_rows_for_one_file_is_refused(tmp_path, run, table):
    write_run(run, [record(1), {**record(2), "file_id": "file-1"}])
    with pytest.raises(ValueError, match="file-1"):
        go(run, tmp_path, None, table)
    assert not (run / RECONCILED_DIR).exists()


def test_a_row_without_a_record_key_is_refused(tmp_path, run, table):
    row = record(1)
    del row["file_id"]
    write_run(run, [row])
    with pytest.raises(ValueError, match="file_id"):
        go(run, tmp_path, None, table)


def test_inference_is_unconfirmed_not_added_when_a_source_spoke_without_declaring(tmp_path, run, evidence, table):
    write_run(run, [record(1, platform="ILLUMINA"), record(2, platform="ILLUMINA")])
    write_evidence(evidence, [("platform", drs(1), "MYSTERY")])  # a seeded row: unreviewed
    result = go(run, tmp_path, evidence, table)
    assert result["inputs"][DATASET]["platform"]["inference"] == {"unconfirmed": 1, "added": 1}


def test_inference_detail_is_kept_while_its_value_stands_and_reconcile_keys_are_not_detail(
    tmp_path, run, evidence, table
):
    from meta_disco.models import field_detail

    agreed, overruled = record(1, reference_assembly="GRCh38"), record(2, reference_assembly="GRCh38")
    for row in (agreed, overruled):
        row["classifications"]["reference_assembly"]["build"] = {"base": "GRCh38"}
        row["classifications"]["reference_assembly"]["other_detail"] = 7
    write_run(run, [agreed, overruled])
    write_evidence(evidence, [("reference_assembly", drs(2), "CHM13")])
    go(run, tmp_path, evidence, table)
    rows = reconciled(run)
    assert field_detail(rows["file-1"], "reference_assembly") == {"build": {"base": "GRCh38"}, "other_detail": 7}
    assert field_detail(rows["file-2"], "reference_assembly") == {}


def test_a_source_with_one_verbatim_and_one_harmonized_claim_is_verbatim_in_both_places(tmp_path, run, evidence):
    table = load(
        tmp_path,
        TABLE
        + """
  - id: platform.pacbio
    match: {slot: platform, value: PACBIO}
    declares: {platform: PACBIO}
    reason: Identity.
""",
    )
    write_run(run, [record(1)])
    write_evidence(evidence, [("platform", drs(1), "PACBIO"), ("platform", drs(1), "PACBIO_SMRT")])
    result = go(run, tmp_path, evidence, table)
    assert result["slots"][DATASET]["platform"] == {"filled_by_submitter": 1}
    assert result["inputs"][DATASET]["platform"][SOURCE_REPOSITORY_METADATA] == {"match": 1}


def test_filled_over_inference_counts_only_the_gaps_sources_filled(tmp_path, run, evidence, table):
    write_run(run, [record(1), record(2, platform="PACBIO")])
    write_evidence(evidence, [("platform", drs(1), "PACBIO_SMRT"), ("platform", drs(2), "PACBIO_SMRT")])
    result = go(run, tmp_path, evidence, table)
    # Both are credited to the submitter; only file 1 was a gap inference left.
    assert result["slots"][DATASET]["platform"] == {"filled_by_submitter_harmonized": 2}
    assert result["filled_over_inference"] == {DATASET: {"platform": 1}}


def test_the_artifact_names_the_translation_table_it_was_built_from(tmp_path, run, table):
    write_run(run, [record(1)])
    result = go(run, tmp_path, None, table)
    assert result["value_map_sha256"] == table.digest and len(table.digest) == 64


def test_every_importer_source_type_has_a_place_in_the_precedence():
    from meta_disco.models import IMPORTER_SOURCE_TYPES
    from meta_disco.reconcile import SOURCE_PRECEDENCE

    assert {t for t, _ in SOURCE_PRECEDENCE} == set(IMPORTER_SOURCE_TYPES)


def test_the_report_lists_each_conflict_by_its_competing_values(tmp_path, run, evidence, table):
    """Contract 5.1: every conflict listable with its competing values, counted per distinct set."""
    write_run(
        run,
        [
            record(1, reference_assembly="GRCh38"),
            record(2, reference_assembly="GRCh38"),
            record(3, reference_assembly="GRCh38"),
        ],
    )
    write_evidence(evidence, [("reference_assembly", drs(1), "CHM13"), ("reference_assembly", drs(2), "CHM13")])
    published(evidence, [("reference_assembly", drs(3), '["GRCm39"]')])
    result = go(run, tmp_path, evidence, table)
    assert result["conflicts"][DATASET]["reference_assembly"] == {
        "conflict_published": [
            {"inputs": {"inference": ["GRCh38"], f"{SOURCE_PUBLISHED_VALUE} (unreviewed)": ['["GRCm39"]']}, "files": 1}
        ],
        "conflict_sources": [{"inputs": {"inference": ["GRCh38"], SOURCE_REPOSITORY_METADATA: ["CHM13"]}, "files": 2}],
    }
    # Every category a slot settles in is one SLOT_CATEGORIES declares, which the report renders by.
    assert {c for per_slot in result["slots"].values() for counts in per_slot.values() for c in counts} <= set(
        SLOT_CATEGORIES
    )


def test_an_inference_conflict_lists_its_competing_values_or_none_when_inherited():
    marked = {
        "inferred": {"value": None, "status": CONFLICT},
        "evidence": [conflict_marker("reference_assembly", ["CHM13", "GRCh38"])],
    }
    assert Report._competing(marked, SlotEvidence(claims=[claim("GRCh38")]), None) == (
        ("inference", ("CHM13", "GRCh38")),
        (SOURCE_REPOSITORY_METADATA, ("GRCh38",)),
    )
    # An index file's conflict inherited from its parent carries no marker, so no values.
    inherited = {"inferred": {"value": None, "status": CONFLICT}, "evidence": [{"status": CONFLICT}]}
    assert Report._competing(inherited, SlotEvidence(), None) == (("inference", ()),)


def test_a_parent_beside_two_sibling_releases_is_scored_disagreed(tmp_path, run, evidence, table):
    """Scoring nests over every declaration, as the slot does: the slot is a conflict, so no input agreed (#473)."""
    write_run(run, [record(1, reference_assembly="CHM13")])
    write_evidence(evidence, [("reference_assembly", drs(1), "CHM13v2")])
    published(evidence, [("reference_assembly", drs(1), "CHM13v1")])
    result = go(run, tmp_path, evidence, table)
    assert slot(run, 1, "reference_assembly")["status"] == CONFLICT
    scored = result["inputs"][DATASET]["reference_assembly"]
    assert scored["inference"] == {"disagreed": 1}
