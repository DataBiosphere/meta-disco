"""Donor and sample records (#693): the entity map, entity evidence files, the importer, the value
map's donor slots, and the reconcile pass that settles each donor and links each sample to its donor.

Synthetic manifests and a test translation table, so the tests check the mechanism and not the
bundled rows."""

import gzip
import json
import re
from pathlib import Path

import pytest
import yaml

from meta_disco import anvil_entities as ae
from meta_disco.entity_evidence import (
    entries,
    iter_entity_evidence,
    read_entity_envelope,
    write_entity_file,
)
from meta_disco.entity_map import load_entity_map
from meta_disco.lineage_evidence import write_lineage_file
from meta_disco.models import (
    CLASSIFIED,
    CONFLICT,
    DONOR_FIELDS,
    JOIN_KEY_DRS_URI,
    JOIN_KEY_ENTITY_IDENTIFIER,
    NOT_CLASSIFIED,
    SOURCE_IDENTIFIER_RULE,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_METADATA,
)
from meta_disco.output_utils import DONORS_FILE, RECONCILED_DIR, SAMPLES_FILE, iter_reconciled_entities
from meta_disco.reconcile import ENTITIES_KEY
from meta_disco.reconcile_entities import reconcile_entities, select_entity_evidence
from meta_disco.sample_identity import Identifier, identifier_rules, reference, sample_list
from meta_disco.schema.classification_model import (
    DonorRecord,
    EntityEvidenceRow,
    ImporterSourceTypeEnum,
    JoinKeyEnum,
    LineageParentKeyEnum,
    LineageRow,
    SampleRecord,
)
from meta_disco.schema_vocab import default_schema_path, most_specific, value_ancestors, value_meaning
from meta_disco.source_evidence import (
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    discover,
    write_evidence_file,
)
from meta_disco.value_map import review, seed
from tests.manifest_fixtures import CATALOG, REAL_MANIFESTS, SERVICE, write_dataset
from tests.run_fixtures import write_run
from tests.test_reconcile import go, record
from tests.test_value_map import load

STAMP = "20261016T000000Z"
G1K = "ANVIL_1000G_high_coverage_2019"
R2 = "AnVIL_HPRC_R2"

MAP = f"""
catalog: anvil15
datasets:
  {G1K}:
    pedigree:
      identifier: pedigree_id
      phenotypic_sex: [sex]
      genetic_ancestry: [population, superpopulation]
  {R2}:
    sample_metadata:
      identifier: sample_metadata_id
      phenotypic_sex: [sex]
      genetic_ancestry: [population_abbreviation]
published:
  table: anvil_donor
  source_rows: source_datarepo_row_ids
  phenotypic_sex: [phenotypic_sex]
"""

# A translation table for the tests' values: the mechanism, not the bundled rows.
TABLE = f"""rows:
  - id: phenotypic_sex.male
    match: {{slot: phenotypic_sex, value: male}}
    declares: {{phenotypic_sex: Male}}
    reason: test
  - id: phenotypic_sex.female
    match: {{slot: phenotypic_sex, value: female}}
    declares: {{phenotypic_sex: Female}}
    reason: test
  - id: phenotypic_sex.ped_1
    match: {{slot: phenotypic_sex, value: "1"}}
    scope: {{source: anvil, dataset: {G1K}}}
    declares: {{phenotypic_sex: Male}}
    reason: test
  - id: genetic_ancestry.gbr
    match: {{slot: genetic_ancestry, value: GBR}}
    declares: {{genetic_ancestry: GBR}}
    reason: test
  - id: genetic_ancestry.eur
    match: {{slot: genetic_ancestry, value: EUR}}
    declares: {{genetic_ancestry: EUR}}
    reason: test
"""


def pedigree(identifier, sex, population, superpopulation, row_id):
    return "pedigree", {
        "datarepo_row_id": row_id,
        "pedigree_id": identifier,
        "sex": sex,
        "population": population,
        "superpopulation": superpopulation,
    }


def sample_metadata(identifier, sex, population, row_id):
    return "sample_metadata", {
        "datarepo_row_id": row_id,
        "sample_metadata_id": identifier,
        "sex": sex,
        "population_abbreviation": population,
    }


def donor(sources, sex):
    return "anvil_donor", {"donor_id": "uuid", "source_datarepo_row_ids": sources, "phenotypic_sex": sex}


def write_manifests(root: Path) -> None:
    write_dataset(
        root,
        G1K,
        [
            pedigree("HG00096", 1, "GBR", "EUR", "p1"),
            pedigree("HG02300", 1, None, None, "p2"),
            pedigree("NOT_A_DONOR", 1, None, None, "p3"),
            pedigree("HG00097", None, None, None, "p4"),
            donor(["pedigree:p1"], None),
        ],
    )
    write_dataset(
        root,
        R2,
        [
            sample_metadata("HG00096", "male", "GBR", "s1"),
            sample_metadata("HG02300", "female", None, "s2"),
            sample_metadata("HG06807", "female", "ASL", "s3"),
            sample_metadata("GRCh38", None, None, "s4"),
            donor(["sample_metadata:s1"], "Male"),
            donor(["sample_metadata:s2"], "Female"),
            donor([], None),
            donor(["sample_metadata:gone"], "Male"),
        ],
    )


@pytest.fixture
def entity_map(tmp_path):
    path = tmp_path / "entity_map.yaml"
    path.write_text(MAP)
    return load_entity_map(path)


@pytest.fixture
def imported(tmp_path, entity_map):
    write_manifests(tmp_path / "m")
    assert ae.check(entity_map, tmp_path / "m", CATALOG) == []
    return ae.import_all(entity_map, tmp_path / "m", CATALOG, SERVICE, tmp_path / "entity_evidence", generation=STAMP)


def lines(root: Path, kind: str, dataset: str, table: str) -> list[dict]:
    path = root / kind / CATALOG / dataset / STAMP / f"{table}.ndjson"
    return [row.model_dump(exclude_none=True) for row in iter_entity_evidence(path)]


# --- the map -------------------------------------------------------------------------


def test_the_bundled_map_loads_and_reads_only_donor_slots():
    entity_map = load_entity_map()
    assert entity_map.catalog == "anvil15"
    assert {slot for t in entity_map.tables for slot in t.slots} <= set(DONOR_FIELDS)
    assert entity_map.published.table == "anvil_donor"


@pytest.mark.skipif(not REAL_MANIFESTS.is_dir(), reason="the anvil15 manifests are not on disk")
def test_the_bundled_map_agrees_with_the_anvil15_manifests():
    assert ae.check(load_entity_map(), REAL_MANIFESTS.parent.parent, CATALOG) == []


@pytest.mark.parametrize(
    ("datasets", "message"),
    [
        ("  D:\n    anvil_donor: {identifier: x, phenotypic_sex: [y]}\n", "harmonized table"),
        ("  D:\n    t: {identifier: x}\n", "reads no slot"),
        ("  D:\n    t: {identifier: x, phenotypic_sex: []}\n", "non-empty list"),
        ("  D:\n    t: {identifier: x, phenotypic_sex: [y, y]}\n", "lists a column twice"),
        ("  D:\n    t: {identifier: x, phenotypic_sex: [x]}\n", "read as the identifier too"),
        ("  D:\n    t: {identifier: x, data_type: [y]}\n", "keys are"),
        ("  D:\n    t: {phenotypic_sex: [y]}\n", "keys are"),
    ],
)
def test_the_loader_refuses_a_malformed_table(tmp_path, datasets, message):
    path = tmp_path / "map.yaml"
    published = "published: {table: anvil_donor, source_rows: s, phenotypic_sex: [p]}\n"
    path.write_text(f"catalog: anvil15\ndatasets:\n{datasets}{published}")
    with pytest.raises(ValueError, match=message):
        load_entity_map(path)


def test_the_check_names_every_problem(tmp_path, entity_map):
    write_dataset(
        tmp_path / "m",
        G1K,
        [
            ("pedigree", {"pedigree_id": "S1", "sex": None, "population": "X"}),
            ("pedigree", {"pedigree_id": "S2", "population": "X"}),
            donor(["participant:x"], "Male"),
        ],
    )
    assert ae.check(entity_map, tmp_path / "m", CATALOG) == [
        f"{G1K}/pedigree: column 'sex' holds a value on no row",
        f"{G1K}/pedigree: column 'superpopulation' holds a value on no row",
        f"{G1K}/pedigree: 2 of 2 values of 'pedigree_id' are not a donor any identifier rule recognises "
        "(e.g. ['S1', 'S2'])",
        f"{G1K}/anvil_donor: donors made from 'participant', which the map does not name",
        f"{R2}: not a dataset the anvil15 sidecar names",
    ]


# --- the importer --------------------------------------------------------------------


def test_a_line_is_a_cell_as_written_keyed_by_the_identifier_as_written(imported, tmp_path):
    got = lines(tmp_path / "entity_evidence", "anvil", G1K, "pedigree")
    assert got[:3] == [
        {
            "field": "phenotypic_sex",
            "target_key_value": "HG00096",
            "raw_value": "1",
            "column": "sex",
            "identifier_column": "pedigree_id",
        },
        {
            "field": "genetic_ancestry",
            "target_key_value": "HG00096",
            "raw_value": "GBR",
            "column": "population",
            "identifier_column": "pedigree_id",
        },
        {
            "field": "genetic_ancestry",
            "target_key_value": "HG00096",
            "raw_value": "EUR",
            "column": "superpopulation",
            "identifier_column": "pedigree_id",
        },
    ]
    # Not recognised here: an identifier no rule knows is still written, and counted at reconcile.
    assert {line["target_key_value"] for line in got} == {"HG00096", "HG02300", "NOT_A_DONOR"}
    (g1k, _) = imported
    (table, published) = g1k.tables
    assert table.null_cells == {"population": 3, "superpopulation": 3, "sex": 1}
    # 1000 Genomes' donors carry no published sex, and the empty published file says so.
    assert published.rows == 1 and published.written == 0


def test_a_published_donor_takes_the_identifier_of_the_row_it_was_made_from(imported, tmp_path):
    got = lines(tmp_path / "entity_evidence", "anvil_published", R2, "anvil_donor")
    assert got == [
        {
            "field": "phenotypic_sex",
            "target_key_value": "HG00096",
            "raw_value": "Male",
            "column": "phenotypic_sex",
            "identifier_column": "sample_metadata_id",
            "identifier_table": "sample_metadata",
        },
        {
            "field": "phenotypic_sex",
            "target_key_value": "HG02300",
            "raw_value": "Female",
            "column": "phenotypic_sex",
            "identifier_column": "sample_metadata_id",
            "identifier_table": "sample_metadata",
        },
    ]
    (_, r2) = imported
    published = r2.tables[-1]
    assert (published.unmapped, published.unresolved, published.ambiguous) == (1, 1, 0)


def test_each_file_names_its_kind_and_is_keyed_by_an_identifier(imported, tmp_path):
    root = tmp_path / "entity_evidence"
    kinds = {(p.parent.parent.name, read_entity_envelope(p).source_type) for p in discover(root)}
    assert kinds == {
        (G1K, SOURCE_REPOSITORY_METADATA),
        (G1K, SOURCE_PUBLISHED_VALUE),
        (R2, SOURCE_REPOSITORY_METADATA),
        (R2, SOURCE_PUBLISHED_VALUE),
    }
    assert {read_entity_envelope(p).target_key for p in discover(root)} == {JOIN_KEY_ENTITY_IDENTIFIER}


def test_an_import_never_overwrites_a_generation(imported, tmp_path, entity_map):
    with pytest.raises(FileExistsError, match="never overwrites"):
        ae.import_all(entity_map, tmp_path / "m", CATALOG, SERVICE, tmp_path / "entity_evidence", generation=STAMP)


# --- the file format -----------------------------------------------------------------


def envelope(
    target_key: str = JOIN_KEY_ENTITY_IDENTIFIER,
    source_type: str = SOURCE_REPOSITORY_METADATA,
    dataset: str | None = "D",
) -> EvidenceFileEnvelope:
    return EvidenceFileEnvelope(
        source=EvidenceFileSource(repository="anvil", dataset="D", table="t", url="https://example.org"),
        source_type=ImporterSourceTypeEnum(source_type),
        source_version="anvil15",
        source_key="id",
        target=EvidenceTarget(system="anvil", dataset=dataset, version="anvil15"),
        target_key=JoinKeyEnum(target_key),
        fetched_at="2026-10-16T00:00:00Z",
    )


ROW = EntityEvidenceRow(
    field="phenotypic_sex", target_key_value="HG00096", raw_value="male", column="sex", identifier_column="id"
)


def test_a_file_reads_back_as_it_was_written_and_as_entries(tmp_path):
    path = tmp_path / "t.ndjson"
    assert write_entity_file(path, envelope(), [ROW]) == 1
    assert list(iter_entity_evidence(path)) == [ROW]
    (entry,) = entries(path)
    assert (entry.field, entry.target_key_value, entry.raw_value) == ("phenotypic_sex", "HG00096", "male")
    assert (entry.source.dataset, entry.source.table, entry.source.column) == ("D", "t", "sex")


@pytest.mark.parametrize(
    ("built", "message"),
    [
        (lambda: envelope(target_key=JOIN_KEY_DRS_URI), "keyed by an identifier"),
        (lambda: envelope(dataset=None), "names no target dataset"),
        (lambda: envelope(source_type="external_ground_truth"), "not an entity source"),
    ],
)
def test_an_envelope_an_entity_reader_cannot_read_is_never_written(tmp_path, built, message):
    with pytest.raises(ValueError, match=message):
        write_entity_file(tmp_path / "t.ndjson", built(), [ROW])


@pytest.mark.parametrize("member", ["value", "status", "rule_id", "identifier", "tier"])
def test_a_line_carrying_an_answer_is_refused_by_name(tmp_path, member):
    path = tmp_path / "t.ndjson"
    write_entity_file(path, envelope(), [ROW])
    line = {**ROW.model_dump(exclude_none=True), member: "x"}
    path.write_text(path.read_text().splitlines()[0] + "\n" + json.dumps(line) + "\n")
    with pytest.raises(ValueError, match=f"carries '{member}'"):
        list(iter_entity_evidence(path))


def test_a_file_keyed_by_an_identifier_is_no_files_evidence(tmp_path):
    with pytest.raises(ValueError, match="keys an entity evidence file"):
        write_evidence_file(tmp_path / "t.ndjson", envelope(), [])
    row = LineageRow(
        target_key_value="x",
        parent="y",
        parent_key_type=LineageParentKeyEnum(JOIN_KEY_DRS_URI),
        child_column="a",
        parent_column="b",
    )
    with pytest.raises(ValueError, match="keys an entity evidence file"):
        write_lineage_file(tmp_path / "l.ndjson", envelope(), [row])


def test_the_entity_row_field_pattern_lists_every_donor_field():
    schema = yaml.safe_load(default_schema_path().read_text())
    pattern = schema["classes"]["EntityEvidenceRow"]["attributes"]["field"]["pattern"]
    match = re.fullmatch(r"\^\((.*)\)\\Z", pattern)
    assert match is not None, pattern
    assert set(match.group(1).split("|")) == set(DONOR_FIELDS)


# --- the vocabulary and the value map ------------------------------------------------


def test_a_population_nests_under_its_superpopulation_and_the_deeper_is_kept():
    assert value_ancestors("genetic_ancestry", "GBR") == ("EUR",)
    assert most_specific("genetic_ancestry", {"GBR", "EUR"}) == "GBR"
    assert most_specific("genetic_ancestry", {"GBR", "FIN"}) is None
    assert value_meaning("genetic_ancestry", "GBR") == "HANCESTRO:0765"


def test_a_row_declares_only_slots_of_the_kind_it_matches(tmp_path):
    with pytest.raises(ValueError, match="declares only slots of the kind it matches"):
        load(
            tmp_path,
            "rows:\n  - id: phenotypic_sex.m\n    match: {slot: phenotypic_sex, value: m}\n"
            "    declares: {data_modality: genomic}\n    reason: r\n",
        )
    with pytest.raises(ValueError, match="declares only slots of the kind it matches"):
        load(
            tmp_path,
            "rows:\n  - id: platform.m\n    match: {slot: platform, value: m}\n"
            "    declares: {phenotypic_sex: Male}\n    reason: r\n",
        )


def test_the_seeder_and_the_queue_read_the_entity_root_beside_the_slot_root(imported, tmp_path):
    table_path = tmp_path / "table.yaml"
    table_path.write_text(TABLE)
    evidence_root = tmp_path / "source_evidence"
    found = review(evidence_root, load(tmp_path, TABLE))
    queued = {(e.slot, e.raw_value): e.files for e in found.queue}
    # ASL has no authored row; it waits in the queue, counted by the donors written with it.
    assert queued[("genetic_ancestry", "ASL")] == 1
    assert ("phenotypic_sex", "1") not in queued
    result = seed(table_path, evidence_root)
    assert "genetic_ancestry.asl" in result.rows_added


# --- reconcile -----------------------------------------------------------------------


def settled(imported_root: Path, tmp_path: Path, sample_lists=()):
    paths, skipped = select_entity_evidence(imported_root, "anvil", CATALOG)
    return reconcile_entities(paths, imported_root, load(tmp_path, TABLE), identifier_rules(), sample_lists, skipped)


def by_id(records: list[dict]) -> dict[str, dict]:
    return {r["identifier"]["id"]: r for r in records}


def test_a_donor_settles_every_source_naming_it(imported, tmp_path):
    result = settled(tmp_path / "entity_evidence", tmp_path)
    hg00096 = by_id(result.donors)["HG00096"]
    sex = hg00096["phenotypic_sex"]
    assert (sex["status"], sex["value"]) == (CLASSIFIED, "Male")
    assert sorted((c["source"]["dataset"], c["source"]["table"], c["raw_value"]) for c in sex["evidence"]) == [
        (G1K, "pedigree", "1"),
        (R2, "anvil_donor", "Male"),
        (R2, "sample_metadata", "male"),
    ]
    assert {c["join_key"] for c in sex["evidence"]} == {JOIN_KEY_ENTITY_IDENTIFIER}
    ancestry = hg00096["genetic_ancestry"]
    assert (ancestry["status"], ancestry["value"]) == (CLASSIFIED, "GBR")
    for donor_record in result.donors:
        DonorRecord(**donor_record)


def test_two_sources_disagreeing_on_a_donor_are_a_conflict_listed_with_every_source(imported, tmp_path):
    result = settled(tmp_path / "entity_evidence", tmp_path)
    assert by_id(result.donors)["HG02300"]["phenotypic_sex"]["status"] == CONFLICT
    (conflict,) = result.report["conflicts"]
    assert (conflict["identifier"], conflict["slot"]) == ({"id": "HG02300", "namespace": "coriell"}, "phenotypic_sex")
    assert sorted(c["value"] for c in conflict["evidence"]) == ["Female", "Female", "Male"]


def test_a_value_no_authored_row_reads_leaves_the_slot_unclassified_and_is_counted(imported, tmp_path):
    result = settled(tmp_path / "entity_evidence", tmp_path)
    ancestry = by_id(result.donors)["HG06807"]["genetic_ancestry"]
    assert (ancestry["status"], ancestry["evidence"]) == (NOT_CLASSIFIED, [])
    assert result.report["unreviewed_lines"] == {"genetic_ancestry": 1}


def test_an_identifier_no_rule_recognises_as_a_donor_is_counted_never_a_record(imported, tmp_path):
    result = settled(tmp_path / "entity_evidence", tmp_path)
    assert "NOT_A_DONOR" not in by_id(result.donors)
    assert result.report["unrecognised"] == [
        {"dataset": G1K, "table": "pedigree", "lines": 1, "examples": {"NOT_A_DONOR": 1}}
    ]


def test_a_sample_is_collected_from_its_same_identifier_donor_which_then_has_a_record(imported, tmp_path):
    members = [Identifier("coriell", "HG00096"), Identifier("coriell", "NA12878"), Identifier("sra_sample", "SRS1")]
    result = settled(tmp_path / "entity_evidence", tmp_path, [sample_list(members)])
    samples = by_id(result.samples)
    assert samples["HG00096"]["collected_from"] == {
        "donor": {"id": "HG00096", "namespace": "coriell"},
        "named_by": [{"source_type": SOURCE_IDENTIFIER_RULE, "rule_id": "coriell_hg"}],
    }
    assert "collected_from" not in samples["SRS1"]
    # A donor no evidence names still has a record, so the join from the sample finds one.
    na12878 = by_id(result.donors)["NA12878"]
    assert na12878["phenotypic_sex"] == {"value": None, "status": NOT_CLASSIFIED, "evidence": []}
    assert result.report["samples"] == {"total": 3, "collected_from": {"coriell": 2}}
    for sample in result.samples:
        SampleRecord(**sample)


def test_a_file_for_another_catalog_or_repository_is_left_unread(imported, tmp_path):
    root = tmp_path / "entity_evidence"
    assert select_entity_evidence(root, "anvil", "anvil16") == ([], [])
    paths, skipped = select_entity_evidence(root, "hprc", None)
    assert paths == [] and {s["target_system"] for s in skipped} == {"anvil"}


def test_a_run_writes_donors_and_samples_beside_its_records(imported, tmp_path):
    run = tmp_path / "output" / "20261016_000000"
    row = record(1)
    members = [Identifier("coriell", "HG00096")]
    row["samples"] = reference(members, [{"source_type": "content_read", "rule_id": "bam_read_group_samples"}])
    write_run(run, [row])
    body = json.loads((run / "bam_classifications.json").read_text())
    body["sample_lists"] = [sample_list(members)]
    (run / "bam_classifications.json").write_text(json.dumps(body))
    (tmp_path / "source_evidence").mkdir()
    report = go(run, tmp_path, tmp_path / "source_evidence", load(tmp_path, TABLE))

    donors = by_id(list(iter_reconciled_entities(run, DONORS_FILE)))
    assert donors["HG00096"]["phenotypic_sex"]["value"] == "Male"
    (sample,) = iter_reconciled_entities(run, SAMPLES_FILE)
    assert sample["collected_from"]["donor"] == {"id": "HG00096", "namespace": "coriell"}
    assert report[ENTITIES_KEY]["donors"] == len(donors)
    first = json.loads(gzip.decompress((run / RECONCILED_DIR / DONORS_FILE).read_bytes()).splitlines()[0])
    assert "reconcile" in first

    # Without evidence the samples and the donors they point to are still written, unsettled.
    go(run, tmp_path, None, load(tmp_path, TABLE))
    (only,) = iter_reconciled_entities(run, DONORS_FILE)
    assert only["phenotypic_sex"]["status"] == NOT_CLASSIFIED
