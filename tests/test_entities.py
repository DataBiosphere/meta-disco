"""Donor and sample records (#693, #669, #582): the entity map, entity evidence files, the importer, the
value map's donor slots, and the reconcile pass that settles each donor and its family, links each sample
to its donor, and lists on each record the repository's own identifiers for it.

Synthetic manifests and a test translation table, so the tests check the mechanism and not the
bundled rows."""

import gzip
import json
import re
from pathlib import Path

import pytest
import yaml

from meta_disco import anvil_entities as ae
from meta_disco import code_rules
from meta_disco.anvil_evidence import EVIDENCE_DIRS
from meta_disco.azul_manifest import FORMAT_VERBATIM, manifest_path
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
    DONOR_REPOSITORY_ID,
    FAMILY_FIELDS,
    JOIN_KEY_DRS_URI,
    JOIN_KEY_ENTITY_IDENTIFIER,
    NOT_CLASSIFIED,
    REPOSITORY_ID_FIELDS,
    REPOSITORY_IDS,
    SAMPLE_REPOSITORY_ID,
    SOURCE_IDENTIFIER_RULE,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_METADATA,
)
from meta_disco.output_utils import DONORS_FILE, RECONCILED_DIR, SAMPLES_FILE, iter_reconciled_artifact
from meta_disco.reconcile import ENTITIES_KEY, reconcile_run
from meta_disco.reconcile_entities import gather, reconcile_entities, select_entity_evidence
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
    generation_dir,
    write_evidence_file,
)
from meta_disco.value_map import review, seed
from tests.manifest_fixtures import CATALOG, REAL_MANIFESTS, SERVICE, write_dataset
from tests.run_fixtures import write_run
from tests.test_reconcile import go, record, write_input
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
    sample:
      identifier: library_name
  {R2}:
    sample_metadata:
      identifier: sample_metadata_id
      phenotypic_sex: [sex]
      genetic_ancestry: [population_abbreviation]
published:
  donor:
    table: anvil_donor
    source_rows: source_datarepo_row_ids
    repository_id: donor_id
    phenotypic_sex: [phenotypic_sex]
  sample:
    table: anvil_biosample
    source_rows: source_datarepo_row_ids
    repository_id: biosample_id
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


def donor(sources, sex, donor_id="d0"):
    return "anvil_donor", {"donor_id": donor_id, "source_datarepo_row_ids": sources, "phenotypic_sex": sex}


def biosample(sources, biosample_id):
    return "anvil_biosample", {"biosample_id": biosample_id, "source_datarepo_row_ids": sources}


def g1k_sample(identifier, row_id):
    return "sample", {"datarepo_row_id": row_id, "library_name": identifier, "sample_id": "SRS1"}


def write_manifests(root: Path) -> None:
    write_dataset(
        root,
        G1K,
        [
            pedigree("HG00096", 1, "GBR", "EUR", "p1"),
            pedigree("HG02300", 1, None, None, "p2"),
            pedigree("NOT_A_DONOR", 1, None, None, "p3"),
            pedigree("HG00097", None, None, None, "p4"),
            donor(["pedigree:p1"], None, "g1k-d1"),
            g1k_sample("HG00096", "q1"),
            biosample(["sample:q1"], "g1k-b1"),
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
            donor(["sample_metadata:s1"], "Male", "r2-d1"),
            donor(["sample_metadata:s2"], "Female", "r2-d2"),
            donor([], None, "r2-d3"),
            donor(["sample_metadata:gone"], "Male", "r2-d4"),
            biosample(["sample_metadata:s1"], "r2-b1"),
            biosample(["sample_metadata:s2"], "r2-b2"),
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
    assert {slot for t in entity_map.tables for slot in t.slots} <= {*DONOR_FIELDS, *FAMILY_FIELDS}
    assert {slot for p in entity_map.published for slot in p.slots} <= set(DONOR_FIELDS)
    assert [(p.kind, p.table, p.repository_id) for p in entity_map.published] == [
        ("donor", "anvil_donor", "donor_id"),
        ("sample", "anvil_biosample", "biosample_id"),
    ]


@pytest.mark.skipif(not REAL_MANIFESTS.is_dir(), reason="the anvil15 manifests are not on disk")
def test_the_bundled_map_agrees_with_the_anvil15_manifests():
    assert ae.check(load_entity_map(), REAL_MANIFESTS.parent.parent, CATALOG) == []


@pytest.mark.parametrize(
    ("datasets", "message"),
    [
        ("  D:\n    anvil_donor: {identifier: x, phenotypic_sex: [y]}\n", "harmonized table"),
        ("  D:\n    t: {identifier: x}\n", "no table reads a slot"),
        ("  D:\n    t: {identifier: x, phenotypic_sex: []}\n", "non-empty list"),
        ("  D:\n    t: {identifier: x, phenotypic_sex: [y, y]}\n", "lists a column twice"),
        ("  D:\n    t: {identifier: x, phenotypic_sex: [x]}\n", "read as the identifier"),
        ("  D:\n    t: {identifier: x, data_type: [y]}\n", "keys are"),
        ("  D:\n    t: {phenotypic_sex: [y]}\n", "keys are"),
    ],
)
def test_the_loader_refuses_a_malformed_table(tmp_path, datasets, message):
    path = tmp_path / "map.yaml"
    published = "published: {donor: {table: anvil_donor, source_rows: s, repository_id: i, phenotypic_sex: [p]}}\n"
    path.write_text(f"catalog: anvil15\ndatasets:\n{datasets}{published}")
    with pytest.raises(ValueError, match=message):
        load_entity_map(path)


def test_a_table_may_name_only_its_identifier(tmp_path):
    """For the repository's records made from its rows to tie to; whether one does is the check's to say."""
    path = tmp_path / "map.yaml"
    published = "published: {sample: {table: anvil_biosample, source_rows: s, repository_id: i}}\n"
    tables = "  D:\n    t: {identifier: x}\n    u: {identifier: y, phenotypic_sex: [s]}\n"
    path.write_text(f"catalog: anvil15\ndatasets:\n{tables}{published}")
    ((table, _), (sample,)) = (load_entity_map(path).tables, load_entity_map(path).published)
    assert (table.identifier, dict(table.slots)) == ("x", {})
    assert (sample.kind, sample.repository_id) == ("sample", "i")


@pytest.mark.parametrize(
    ("published", "message"),
    [
        ("{}", "names no kind"),
        ("{person: {table: t, source_rows: s, repository_id: i}}", "keys are"),
        ("{donor: {table: t, source_rows: s}}", "keys are"),
        ("{sample: {table: t, source_rows: s, repository_id: i, phenotypic_sex: [p]}}", "keys are"),
        ("{donor: {table: t, source_rows: s, repository_id: i, mother: [m]}}", "keys are"),
        ("{donor: {table: t, source_rows: s, repository_id: s}}", "source rows and the repository identifier"),
        ("{donor: {table: t, source_rows: s, repository_id: i, phenotypic_sex: [i]}}", "read as the identifier"),
        (
            "{donor: {table: t, source_rows: s, repository_id: i}, sample: {table: t, source_rows: s, repository_id: i}}",
            "two kinds name one table",
        ),
    ],
)
def test_the_loader_refuses_a_malformed_published_table(tmp_path, published, message):
    path = tmp_path / "map.yaml"
    path.write_text(f"catalog: anvil15\ndatasets:\n  D:\n    t: {{identifier: x}}\npublished: {published}\n")
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
        f"{G1K}/sample: no row of this type in the manifest",
        f"{G1K}/anvil_donor: donors made from 'participant', which the map does not name",
        f"{R2}: not a dataset the anvil15 sidecar names",
    ]


def test_the_check_names_a_published_column_no_row_fills(tmp_path, entity_map):
    """A misnamed repository_id or source_rows column would otherwise import no identifier, silently."""
    rows = [pedigree("HG00096", 1, "GBR", "EUR", "p1"), g1k_sample("HG00096", "q1")]
    biosample_without_id = ("anvil_biosample", {"source_datarepo_row_ids": ["sample:q1"]})
    write_dataset(tmp_path / "m", G1K, [*rows, biosample_without_id, ("anvil_donor", {"donor_id": "d1"})])
    assert ae.check(entity_map, tmp_path / "m", CATALOG, [G1K]) == [
        f"{G1K}/anvil_donor: column 'source_datarepo_row_ids' holds a value on no row",
        f"{G1K}/anvil_biosample: column 'biosample_id' holds a value on no row",
    ]


def test_the_check_holds_a_table_to_each_kind_it_serves(tmp_path, entity_map):
    """A table reading no slot must be a published table's source, and its identifiers that kind."""
    rows = [pedigree("HG00096", 1, "GBR", "EUR", "p1")]
    write_dataset(tmp_path / "m", G1K, [*rows, g1k_sample("HG00096", "q1")])
    assert ae.check(entity_map, tmp_path / "m", CATALOG, [G1K]) == [
        f"{G1K}/sample: reads no slot, and no published table's records are made from its rows"
    ]
    # IGVFDO… is a donor accession, never a sample's: the sample table's column names no sample.
    write_dataset(tmp_path / "m", G1K, [*rows, g1k_sample("IGVFDO2696EIGV", "q1"), biosample(["sample:q1"], "b1")])
    assert ae.check(entity_map, tmp_path / "m", CATALOG, [G1K]) == [
        f"{G1K}/sample: 1 of 1 values of 'library_name' are not a sample any identifier rule recognises "
        "(e.g. ['IGVFDO2696EIGV'])"
    ]
    write_dataset(tmp_path / "m", G1K, [*rows, g1k_sample("HG00096", "q1"), biosample(["participant:x"], "b1")])
    assert ae.check(entity_map, tmp_path / "m", CATALOG, [G1K]) == [
        f"{G1K}/sample: reads no slot, and no published table's records are made from its rows",
        f"{G1K}/anvil_biosample: samples made from 'participant', which the map does not name",
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
    # The sample table reads no slot: it writes no file, and is read for identifiers only.
    (table, sample, published, _) = g1k.tables
    assert (sample.table, sample.path, sample.rows, sample.no_identifier) == ("sample", None, 1, 0)
    assert "  sample: 1 rows, read for identifiers only" in ae.describe([g1k])
    assert table.null_cells == {"population": 3, "superpopulation": 3, "sex": 1}
    # 1000 Genomes' donors carry no published sex: their one line is AnVIL's donor_id.
    assert published.rows == 1 and published.written == 1
    assert published.null_cells == {"phenotypic_sex": 1}


def test_a_published_donor_takes_the_identifier_of_the_row_it_was_made_from(imported, tmp_path):
    got = lines(tmp_path / "entity_evidence", "anvil_published", R2, "anvil_donor")
    tied = {"identifier_column": "sample_metadata_id", "identifier_table": "sample_metadata"}
    assert got == [
        {
            "field": DONOR_REPOSITORY_ID,
            "target_key_value": "HG00096",
            "raw_value": "r2-d1",
            "column": "donor_id",
            **tied,
        },
        {
            "field": "phenotypic_sex",
            "target_key_value": "HG00096",
            "raw_value": "Male",
            "column": "phenotypic_sex",
            **tied,
        },
        {
            "field": DONOR_REPOSITORY_ID,
            "target_key_value": "HG02300",
            "raw_value": "r2-d2",
            "column": "donor_id",
            **tied,
        },
        {
            "field": "phenotypic_sex",
            "target_key_value": "HG02300",
            "raw_value": "Female",
            "column": "phenotypic_sex",
            **tied,
        },
    ]
    (_, r2) = imported
    published = r2.tables[-2]
    assert published.table == "anvil_donor"
    assert (published.unmapped, published.unresolved, published.ambiguous) == (1, 1, 0)


def test_a_record_made_from_two_mapped_tables_naming_one_identifier_names_the_first_table(tmp_path, entity_map):
    """As NIA CARD's biosamples, made from its `sample` and `subject` rows: one line, from the table first by name."""
    rows = [pedigree("HG00096", 1, "GBR", "EUR", "p1"), g1k_sample("HG00096", "q1")]
    write_dataset(tmp_path / "m", G1K, [*rows, biosample(["sample:q1", "pedigree:p1"], "b1")])
    ae.import_all(entity_map, tmp_path / "m", CATALOG, SERVICE, tmp_path / "ev", datasets=[G1K], generation=STAMP)
    (line,) = lines(tmp_path / "ev", "anvil_published", G1K, "anvil_biosample")
    assert (line["identifier_table"], line["identifier_column"]) == ("pedigree", "pedigree_id")


def test_a_published_sample_takes_the_identifier_of_the_row_it_was_made_from(imported, tmp_path):
    """Through a table reading no slot, which writes no file of its own."""
    assert lines(tmp_path / "entity_evidence", "anvil_published", G1K, "anvil_biosample") == [
        {
            "field": SAMPLE_REPOSITORY_ID,
            "target_key_value": "HG00096",
            "raw_value": "g1k-b1",
            "column": "biosample_id",
            "identifier_column": "library_name",
            "identifier_table": "sample",
        }
    ]
    assert not (tmp_path / "entity_evidence" / "anvil" / CATALOG / G1K / STAMP / "sample.ndjson").exists()


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
        source=EvidenceFileSource(repository="anvil", dataset=dataset or "D", table="t", url="https://example.org"),
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


def test_the_entity_row_field_pattern_lists_every_entity_field():
    schema = yaml.safe_load(default_schema_path().read_text())
    pattern = schema["classes"]["EntityEvidenceRow"]["attributes"]["field"]["pattern"]
    match = re.fullmatch(r"\^\((.*)\)\\Z", pattern)
    assert match is not None, pattern
    assert set(match.group(1).split("|")) == {*DONOR_FIELDS, *FAMILY_FIELDS, *REPOSITORY_ID_FIELDS}


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
    # A repository's identifier is no slot's value: it is neither queued nor seeded.
    assert not {e.slot for e in found.queue} & set(REPOSITORY_ID_FIELDS)
    result = seed(table_path, evidence_root)
    assert "genetic_ancestry.asl" in result.rows_added
    assert not [r for r in result.rows_added if r.split(".")[0] in REPOSITORY_ID_FIELDS]


# --- reconcile -----------------------------------------------------------------------


def settled(imported_root: Path, tmp_path: Path, sample_lists=()):
    paths, skipped = select_entity_evidence(imported_root, "anvil", CATALOG)
    rules = identifier_rules()
    return reconcile_entities(gather(paths, imported_root, load(tmp_path, TABLE), rules), rules, sample_lists, skipped)


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
    assert result.report["unreviewed_donors"] == {"genetic_ancestry": 1}


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
    # HG02300 is named by no file, only by AnVIL's biosample, and has a record too.
    assert result.report["samples"] == {"total": 4, "named_by_files": 3, "collected_from": {"coriell": 3}}
    for sample in result.samples:
        SampleRecord(**sample)


def test_every_repository_identifier_is_listed_on_the_one_record_it_ties_to(imported, tmp_path):
    """Many to one: a person's AnVIL donor in each dataset, and a sample no file names gets a record for its own."""
    result = settled(tmp_path / "entity_evidence", tmp_path)
    donors, samples = by_id(result.donors), by_id(result.samples)
    assert donors["HG00096"][REPOSITORY_IDS] == [
        {"id": "g1k-d1", "repository": "anvil", "dataset": G1K, "table": "anvil_donor"},
        {"id": "r2-d1", "repository": "anvil", "dataset": R2, "table": "anvil_donor"},
    ]
    assert [r["id"] for r in donors["HG02300"][REPOSITORY_IDS]] == ["r2-d2"]
    assert REPOSITORY_IDS not in donors["HG06807"]
    assert [r["id"] for r in samples["HG00096"][REPOSITORY_IDS]] == ["g1k-b1", "r2-b1"]
    assert samples["HG02300"] == {
        "identifier": {"id": "HG02300", "namespace": "coriell"},
        "collected_from": {
            "donor": {"id": "HG02300", "namespace": "coriell"},
            "named_by": [{"source_type": SOURCE_IDENTIFIER_RULE, "rule_id": "coriell_hg"}],
        },
        REPOSITORY_IDS: [{"id": "r2-b2", "repository": "anvil", "dataset": R2, "table": "anvil_biosample"}],
    }
    for donor_record in result.donors:
        DonorRecord(**donor_record)
    for sample_record in result.samples:
        SampleRecord(**sample_record)
    assert result.report[REPOSITORY_IDS] == {
        "donor": {
            "records": 2,
            "ids": 3,
            "ids_per_record": {"1": 1, "2": 1},
            "by_dataset": {G1K: {"ids": 1, "records": 1}, R2: {"ids": 2, "records": 2}},
        },
        "sample": {
            "records": 2,
            "ids": 3,
            "ids_per_record": {"1": 1, "2": 1},
            "by_dataset": {G1K: {"ids": 1, "records": 1}, R2: {"ids": 2, "records": 2}},
        },
    }


def write_entity_lines(
    root: Path, dataset: str, field: str, lines: list[tuple[str, str]], source_type: str = SOURCE_PUBLISHED_VALUE
) -> None:
    """One entity file of ``source_type`` in ``dataset``, a line per ``(raw_value, identifier string)`` for ``field``."""
    directory = generation_dir(root, EVIDENCE_DIRS[source_type], CATALOG, dataset, STAMP)
    directory.mkdir(parents=True)
    rows = [
        EntityEvidenceRow(field=field, target_key_value=ident, raw_value=raw, column="c", identifier_column="x")
        for raw, ident in lines
    ]
    write_entity_file(directory / "t.ndjson", envelope(source_type=source_type, dataset=dataset), rows)


def gathered(root: Path, tmp_path: Path, table: str = TABLE):
    paths, _ = select_entity_evidence(root, "anvil", CATALOG)
    return gather(paths, root, load(tmp_path, table), identifier_rules())


def test_a_repository_identifier_tying_to_two_records_is_refused_not_chosen(tmp_path):
    root = tmp_path / "entity_evidence"
    write_entity_lines(root, "D1", DONOR_REPOSITORY_ID, [("u1", "HG00096")])
    write_entity_lines(root, "D2", DONOR_REPOSITORY_ID, [("u1", "HG00097")])
    with pytest.raises(ValueError, match=r"'u1' ties to .* which is not chosen"):
        gathered(root, tmp_path)


@pytest.mark.parametrize("raw", ["", "u1\nu2", "u1\ru2"])
def test_a_repository_identifier_empty_or_on_two_lines_is_refused(tmp_path, raw):
    """It would be no `RepositoryIdentifier.id`, and two empty ones would seem to tie two records."""
    root = tmp_path / "entity_evidence"
    write_entity_lines(root, "D1", DONOR_REPOSITORY_ID, [(raw, "HG00096")])
    with pytest.raises(ValueError, match="is not an identifier: empty, or more than one line"):
        gathered(root, tmp_path)


def test_a_repository_identifier_outside_a_published_table_is_refused(tmp_path):
    """Only the repository's own table issues its identifiers; a submitter table's line claiming one is refused."""
    root = tmp_path / "entity_evidence"
    write_entity_lines(root, "D1", DONOR_REPOSITORY_ID, [("u1", "HG00096")], SOURCE_REPOSITORY_METADATA)
    with pytest.raises(ValueError, match="only the repository's published table issues one"):
        gathered(root, tmp_path)


def test_one_repository_identifier_in_two_datasets_tying_to_one_record_is_listed_for_each(tmp_path):
    """PRIMED and T2T give a person the same AnVIL donor_id; a GM and an NA name one Coriell sample."""
    root = tmp_path / "entity_evidence"
    write_entity_lines(root, "D1", DONOR_REPOSITORY_ID, [("u1", "HG00096")])
    write_entity_lines(root, "D2", DONOR_REPOSITORY_ID, [("u1", "HG00096")])
    write_entity_lines(root, "D3", SAMPLE_REPOSITORY_ID, [("b1", "GM19908"), ("b2", "NA19908")])
    result = reconcile_entities(gathered(root, tmp_path), identifier_rules(), [])
    assert [(r["dataset"], r["id"]) for r in by_id(result.donors)["HG00096"][REPOSITORY_IDS]] == [
        ("D1", "u1"),
        ("D2", "u1"),
    ]
    assert [r["id"] for r in by_id(result.samples)["NA19908"][REPOSITORY_IDS]] == ["b1", "b2"]
    assert result.report[REPOSITORY_IDS]["donor"]["ids_per_record"] == {"1": 1}
    # One identifier, listed twice: the report counts it once.
    assert result.report[REPOSITORY_IDS]["donor"]["ids"] == 1


def test_one_uuid_as_a_donor_id_and_a_sample_id_ties_once_per_kind(tmp_path):
    """AnVIL gives a donor and a biosample made from one row key the same UUID (PRIMED's HG00183): no refusal."""
    root = tmp_path / "entity_evidence"
    write_entity_lines(root, "D1", DONOR_REPOSITORY_ID, [("u1", "HG00096")])
    write_entity_lines(root, "D2", SAMPLE_REPOSITORY_ID, [("u1", "IGVFSM9197PTER")])
    result = reconcile_entities(gathered(root, tmp_path), identifier_rules(), [])
    assert [r["id"] for r in by_id(result.donors)["HG00096"][REPOSITORY_IDS]] == ["u1"]
    assert [r["id"] for r in by_id(result.samples)["IGVFSM9197PTER"][REPOSITORY_IDS]] == ["u1"]


def test_a_repository_identifier_naming_no_recognised_identifier_of_its_kind_is_counted(tmp_path):
    """A sample line is recognised as a sample: a donor accession is not one, and is counted, never a record."""
    root = tmp_path / "entity_evidence"
    write_entity_lines(root, "D1", SAMPLE_REPOSITORY_ID, [("b1", "IGVFDO2696EIGV"), ("b2", "IGVFSM9197PTER")])
    result = reconcile_entities(gathered(root, tmp_path), identifier_rules(), [])
    (sample,) = result.samples
    assert sample["identifier"] == {"id": "IGVFSM9197PTER", "namespace": "igvf"}
    assert result.donors == []
    assert result.report["unrecognised"] == [
        {"dataset": "D1", "table": "t", "lines": 1, "examples": {"IGVFDO2696EIGV": 1}}
    ]


def test_a_dataset_the_map_leaves_out_is_listed_with_its_records(imported, tmp_path, entity_map):
    write_dataset(tmp_path / "m", "AnVIL_ENCORE_293T", [donor(["donor:x"], None, "e1"), biosample([], "e2")])
    write_dataset(tmp_path / "m", "ANVIL_nhp_dGTEx_V1", [])
    write_dataset(tmp_path / "m", "AnVIL_Elsewhere", [])
    manifest_path(tmp_path / "m", CATALOG, "AnVIL_Elsewhere", FORMAT_VERBATIM).unlink()
    (nhp, left, gone) = ae.left_out(entity_map, tmp_path / "m", CATALOG)
    assert (left.dataset, left.records) == ("AnVIL_ENCORE_293T", {"anvil_donor": 1, "anvil_biosample": 1})
    assert nhp.records == {"anvil_donor": 0, "anvil_biosample": 0}
    assert (gone.dataset, gone.records) == ("AnVIL_Elsewhere", {})
    # A dataset with no published record has none to tie, and is not listed; one not on disk is.
    assert ae.describe_left_out([nhp, left, gone]) == [
        "AnVIL_ENCORE_293T: not in the entity map, so none of its records tie (1 anvil_donor, 1 anvil_biosample)",
        "AnVIL_Elsewhere: not in the entity map, so none of its records tie (not on disk)",
    ]


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

    donors = by_id(list(iter_reconciled_artifact(run, DONORS_FILE)))
    assert donors["HG00096"]["phenotypic_sex"]["value"] == "Male"
    samples = by_id(list(iter_reconciled_artifact(run, SAMPLES_FILE)))
    assert samples["HG00096"]["collected_from"]["donor"] == {"id": "HG00096", "namespace": "coriell"}
    assert {r["id"] for r in samples["HG00096"][REPOSITORY_IDS]} == {"g1k-b1", "r2-b1"}
    assert report[ENTITIES_KEY]["donors"] == len(donors)
    first = json.loads(gzip.decompress((run / RECONCILED_DIR / DONORS_FILE).read_bytes()).splitlines()[0])
    assert "reconcile" in first

    # Without evidence the samples and the donors they point to are still written, unsettled.
    go(run, tmp_path, None, load(tmp_path, TABLE))
    (only,) = iter_reconciled_artifact(run, DONORS_FILE)
    assert only["phenotypic_sex"]["status"] == NOT_CLASSIFIED


def test_a_reviewed_no_op_value_is_not_unreviewed(imported, tmp_path):
    """An authored row declaring nothing (`declares: {}`) reviewed the value: it moves nothing and is not queued."""
    noop = TABLE + (
        "  - id: genetic_ancestry.asl\n    match: {slot: genetic_ancestry, value: ASL}\n    declares: {}\n    reason: r\n"
    )
    result = reconcile_entities(gathered(tmp_path / "entity_evidence", tmp_path, noop), identifier_rules(), [])
    assert "genetic_ancestry" not in result.report["unreviewed_donors"]
    assert by_id(result.donors)["HG06807"]["genetic_ancestry"]["status"] == NOT_CLASSIFIED


def test_a_published_value_no_row_reads_is_kept_as_unmapped_and_challenges_the_rest(imported, tmp_path):
    """As on a file (contract 6.10): the published value is on the record, and beside a declaration it is a conflict."""
    without_male = TABLE.replace("  - id: phenotypic_sex.male\n    match: {slot: phenotypic_sex, value: male}\n", "")
    without_male = without_male.replace("    declares: {phenotypic_sex: Male}\n    reason: test\n", "", 1)
    result = reconcile_entities(gathered(tmp_path / "entity_evidence", tmp_path, without_male), identifier_rules(), [])
    sex = by_id(result.donors)["HG00096"]["phenotypic_sex"]
    assert sex["status"] == CONFLICT
    (unmapped,) = [c for c in sex["evidence"] if c.get("claim_state") == "unmapped"]
    assert (unmapped["source_type"], unmapped["raw_value"]) == (SOURCE_PUBLISHED_VALUE, "Male")


def test_a_dataset_with_no_published_donor_still_writes_its_published_file(tmp_path, entity_map):
    """So a re-import supersedes both kinds, never leaving an older published generation current."""
    write_dataset(tmp_path / "m", G1K, [pedigree("HG00096", 1, "GBR", "EUR", "p1")])
    (run,) = ae.import_all(
        entity_map, tmp_path / "m", CATALOG, SERVICE, tmp_path / "entity_evidence", datasets=[G1K], generation=STAMP
    )
    assert lines(tmp_path / "entity_evidence", "anvil_published", G1K, "anvil_donor") == []
    assert lines(tmp_path / "entity_evidence", "anvil_published", G1K, "anvil_biosample") == []
    assert [(t.table, t.rows) for t in run.tables[-2:]] == [("anvil_donor", 0), ("anvil_biosample", 0)]


def test_every_reconciled_files_envelope_names_the_entity_files_read(imported, tmp_path):
    run = tmp_path / "output" / "20261016_000000"
    write_run(run, [record(1)])
    (tmp_path / "source_evidence").mkdir()
    go(run, tmp_path, tmp_path / "source_evidence", load(tmp_path, TABLE))
    first = json.loads(gzip.decompress((run / RECONCILED_DIR / DONORS_FILE).read_bytes()).splitlines()[0])
    named = {(e["dataset"], e["table"], e["source_type"]) for e in first["reconcile"]["entity_evidence"]}
    assert (R2, "anvil_donor", SOURCE_PUBLISHED_VALUE) in named and len(named) == 6
    assert (G1K, "anvil_biosample", SOURCE_PUBLISHED_VALUE) in named


def test_a_failed_published_write_leaves_neither_kind_of_the_new_generation(
    imported, tmp_path, entity_map, monkeypatch
):
    """The submitter generation never becomes current beside an older published one."""
    root = tmp_path / "entity_evidence"
    before = sorted(discover(root))

    def broken(*args, **kwargs):
        raise OSError("disk full")
        yield  # pragma: no cover

    monkeypatch.setattr(ae, "_published_rows", broken)
    with pytest.raises(OSError, match="disk full"):
        ae.import_all(entity_map, tmp_path / "m", CATALOG, SERVICE, root, datasets=[R2], generation="20261017T000000Z")
    assert sorted(discover(root)) == before
    assert not list(root.rglob("*.partial"))


def test_a_claim_joined_through_a_rewritten_identifier_is_not_an_exact_match(tmp_path):
    """`GM19908` reaches donor `NA19908` through the Coriell rule's rewrite; `NA19908` itself matches exactly."""
    root = tmp_path / "entity_evidence"
    lines = [("male", "GM19908"), ("male", "NA19908")]
    write_entity_lines(root, "D", "phenotypic_sex", lines, SOURCE_REPOSITORY_METADATA)
    result = reconcile_entities(gathered(root, tmp_path), identifier_rules(), [])
    (donor,) = result.donors
    assert donor["identifier"] == {"id": "NA19908", "namespace": "coriell"}
    assert sorted(c["match_exact"] for c in donor["phenotypic_sex"]["evidence"]) == [False, True]


def test_the_report_counts_each_slot_overall_and_by_the_datasets_naming_its_donors(imported, tmp_path):
    """A dataset's counts are of the donors it names, each at its overall settled status."""
    result = settled(tmp_path / "entity_evidence", tmp_path)
    report = result.report
    assert [d["identifier"]["id"] for d in result.donors] == ["HG00096", "HG02300", "HG06807"]
    assert report["statuses"] == {
        "phenotypic_sex": {CLASSIFIED: 2, CONFLICT: 1},
        "genetic_ancestry": {CLASSIFIED: 1, NOT_CLASSIFIED: 2},
        **{slot: {NOT_CLASSIFIED: 3} for slot in FAMILY_FIELDS},
    }
    assert report["by_dataset"] == {
        G1K: {
            "phenotypic_sex": {"donors": 2, CLASSIFIED: 1, CONFLICT: 1},
            "genetic_ancestry": {"donors": 1, CLASSIFIED: 1},
        },
        R2: {
            "phenotypic_sex": {"donors": 3, CLASSIFIED: 2, CONFLICT: 1},
            "genetic_ancestry": {"donors": 2, CLASSIFIED: 1, NOT_CLASSIFIED: 1},
        },
    }
    pedigree_file = next(f for f in report["files"] if f["table"] == "pedigree")
    assert (pedigree_file["lines"], pedigree_file["unrecognised"]) == (5, 1)


def test_the_importer_counts_what_it_cannot_write(tmp_path, entity_map):
    """A row naming no donor is counted, and a published donor whose rows name two donors is dropped as ambiguous."""
    write_dataset(
        tmp_path / "m",
        R2,
        [
            sample_metadata("HG00096", "male", None, "s1"),
            sample_metadata("HG00097", "male", None, "s2"),
            sample_metadata(None, "male", None, "s3"),
            donor(["sample_metadata:s1", "sample_metadata:s2"], "Male"),
        ],
    )
    (run,) = ae.import_all(
        entity_map, tmp_path / "m", CATALOG, SERVICE, tmp_path / "entity_evidence", datasets=[R2], generation=STAMP
    )
    table, published, _ = run.tables
    assert (table.rows, table.no_identifier, table.written) == (3, 1, 2)
    assert (published.ambiguous, published.written) == (1, 0)


def test_a_mapped_table_writing_nothing_fails_the_import_and_leaves_nothing(tmp_path, entity_map):
    write_dataset(tmp_path / "m", G1K, [pedigree("HG00096", None, None, None, "p1")])
    root = tmp_path / "entity_evidence"
    with pytest.raises(ValueError, match="no line written"):
        ae.import_all(entity_map, tmp_path / "m", CATALOG, SERVICE, root, datasets=[G1K], generation=STAMP)
    assert not list(root.rglob("*.ndjson"))


def test_the_check_accepts_a_column_half_of_whose_values_are_donors(tmp_path, entity_map):
    write_dataset(
        tmp_path / "m",
        G1K,
        [
            pedigree("HG00096", 1, "GBR", "EUR", "p1"),
            pedigree("S1", 1, "GBR", "EUR", "p2"),
            g1k_sample("HG00096", "q1"),
            biosample(["sample:q1"], "b1"),
        ],
    )
    assert ae.check(entity_map, tmp_path / "m", CATALOG, [G1K]) == []


def test_entity_evidence_leaves_every_file_record_as_it_was(imported, tmp_path):
    """File records are the same, byte for byte from line 2, with the entity evidence and without it."""
    run = tmp_path / "output" / "20261016_000000"
    row = record(1)
    members = [Identifier("coriell", "HG00096")]
    row["samples"] = reference(members, [{"source_type": "content_read", "rule_id": "bam_read_group_samples"}])
    write_run(run, [row])
    body = json.loads((run / "bam_classifications.json").read_text())
    body["sample_lists"] = [sample_list(members)]
    (run / "bam_classifications.json").write_text(json.dumps(body))
    (tmp_path / "source_evidence").mkdir()

    def records_written(entity_root):
        reconcile_run(
            run, write_input(tmp_path), tmp_path / "source_evidence", load(tmp_path, TABLE), entity_root=entity_root
        )
        return gzip.decompress((run / RECONCILED_DIR / "bam_classifications.ndjson.gz").read_bytes()).splitlines()[1:]

    with_entities = records_written(tmp_path / "entity_evidence")
    assert records_written(tmp_path / "nowhere") == with_entities


# --- a donor's family (#582) ----------------------------------------------------------


def family_lines(root: Path, dataset: str, field: str, lines: list[tuple[str, str]]) -> None:
    write_entity_lines(root, dataset, field, lines, SOURCE_REPOSITORY_METADATA)


def recognised_by(raw: str) -> str:
    got = identifier_rules().recognise(raw, "D", "donor")
    assert got is not None
    return got.rule_id


def test_a_parent_settles_to_its_identifier_citing_the_rule_that_recognised_it(tmp_path):
    root = tmp_path / "entity_evidence"
    family_lines(root, "D", "mother", [("NA12892", "NA12878")])
    family_lines(root, "E", "father", [("GM12891", "NA12878")])
    result = reconcile_entities(gathered(root, tmp_path), identifier_rules(), [])
    child = by_id(result.donors)["NA12878"]
    assert (child["mother"]["status"], child["mother"]["value"]) == (
        CLASSIFIED,
        {"id": "NA12892", "namespace": "coriell"},
    )
    # The parent is rewritten as its rule writes it; the claim keeps what the source wrote.
    assert child["father"]["value"] == {"id": "NA12891", "namespace": "coriell"}
    ((claim,),) = [child["father"]["evidence"]]
    assert (claim["rule_id"], claim["raw_value"], claim["source_type"]) == (
        recognised_by("GM12891"),
        "GM12891",
        SOURCE_REPOSITORY_METADATA,
    )
    assert (claim["join_key"], claim["match_exact"]) == (JOIN_KEY_ENTITY_IDENTIFIER, True)
    for donor_record in result.donors:
        DonorRecord(**donor_record)


def test_each_parent_named_has_a_record_of_its_own(tmp_path):
    root = tmp_path / "entity_evidence"
    family_lines(root, "D", "mother", [("NA12892", "NA12878")])
    family_lines(root, "E", "mother", [("NA12878", "NA12877")])
    result = reconcile_entities(gathered(root, tmp_path), identifier_rules(), [])
    assert [d["identifier"]["id"] for d in result.donors] == ["NA12877", "NA12878", "NA12892"]
    assert by_id(result.donors)["NA12892"]["mother"] == {"value": None, "status": NOT_CLASSIFIED, "evidence": []}
    # NA12878 is a parent with a claim of its own (its mother); NA12892 has none.
    assert result.report["family"]["parents_named"] == 2
    assert result.report["family"]["parents_with_no_claims"] == 1


def test_a_ped_unknown_parent_makes_no_claim_and_is_counted_apart(tmp_path):
    root = tmp_path / "entity_evidence"
    family_lines(root, "D", "mother", [("0", "HG00096"), ("mHomSap2", "HG00097")])
    result = reconcile_entities(gathered(root, tmp_path), identifier_rules(), [])
    for child in ("HG00096", "HG00097"):
        assert by_id(result.donors)[child]["mother"] == {"value": None, "status": NOT_CLASSIFIED, "evidence": []}
    assert [d["identifier"]["id"] for d in result.donors] == ["HG00096", "HG00097"]
    family = result.report["family"]
    assert family["unknown_parent_lines"] == [{"dataset": "D", "table": "t", "lines": 1}]
    assert family["unrecognised_parents"] == [{"dataset": "D", "table": "t", "lines": 1, "examples": {"mHomSap2": 1}}]
    assert family["parents_named"] == 0


def test_two_sources_naming_different_parents_are_a_conflict_and_agreeing_ones_are_each_kept(tmp_path):
    """HPRC names HG002's mother HG004; HPRC_R2 names NA24695."""
    root = tmp_path / "entity_evidence"
    family_lines(root, "D", "mother", [("HG004", "HG002"), ("NA12892", "NA12878")])
    family_lines(root, "E", "mother", [("NA24695", "HG002"), ("NA12892", "NA12878")])
    result = reconcile_entities(gathered(root, tmp_path), identifier_rules(), [])
    donors = by_id(result.donors)
    assert (donors["HG002"]["mother"]["status"], donors["HG002"]["mother"]["value"]) == (CONFLICT, None)
    assert donors["NA12878"]["mother"]["status"] == CLASSIFIED
    assert sorted(c["source"]["dataset"] for c in donors["NA12878"]["mother"]["evidence"]) == ["D", "E"]
    (conflict,) = result.report["conflicts"]
    assert (conflict["identifier"]["id"], conflict["slot"]) == ("HG002", "mother")
    assert sorted(c["raw_value"] for c in conflict["evidence"]) == ["HG004", "NA24695"]


def test_a_family_id_is_the_answer_as_written_and_two_ids_conflict(tmp_path):
    root = tmp_path / "entity_evidence"
    family_lines(root, "D", "family_id", [("PR25", "HG01106"), ("1463", "NA12878")])
    family_lines(root, "E", "family_id", [("PR25", "HG01106"), ("CEPH1463", "NA12878")])
    result = reconcile_entities(gathered(root, tmp_path), identifier_rules(), [])
    donors = by_id(result.donors)
    family = donors["HG01106"]["family_id"]
    assert (family["status"], family["value"]) == (CLASSIFIED, "PR25")
    assert {c["rule_id"] for c in family["evidence"]} == {code_rules.FAMILY_ID_AS_WRITTEN.id}
    assert donors["NA12878"]["family_id"]["status"] == CONFLICT
    for donor_record in result.donors:
        DonorRecord(**donor_record)


FAMILY_MAP = f"""
catalog: anvil15
datasets:
  {G1K}:
    pedigree:
      identifier: pedigree_id
      phenotypic_sex: [sex]
      mother: [motherid]
      father: [fatherid]
      family_id: [familyid]
published:
  donor:
    table: anvil_donor
    source_rows: source_datarepo_row_ids
    repository_id: donor_id
"""


def test_the_importer_writes_each_family_cell_as_written_ped_unknown_included(tmp_path):
    path = tmp_path / "entity_map.yaml"
    path.write_text(FAMILY_MAP)
    entity_map = load_entity_map(path)
    rows = [
        (
            "pedigree",
            {
                "datarepo_row_id": "p1",
                "pedigree_id": "NA12878",
                "sex": 2,
                "motherid": "NA12892",
                "fatherid": "NA12891",
                "familyid": "1463",
            },
        ),
        (
            "pedigree",
            {
                "datarepo_row_id": "p2",
                "pedigree_id": "NA12892",
                "sex": 2,
                "motherid": "0",
                "fatherid": "0",
                "familyid": "1463",
            },
        ),
    ]
    write_dataset(tmp_path / "m", G1K, rows)
    assert ae.check(entity_map, tmp_path / "m", CATALOG) == []
    ae.import_all(entity_map, tmp_path / "m", CATALOG, SERVICE, tmp_path / "entity_evidence", generation=STAMP)
    written = lines(tmp_path / "entity_evidence", "anvil", G1K, "pedigree")
    assert [(r["target_key_value"], r["field"], r["raw_value"]) for r in written if r["field"] in FAMILY_FIELDS] == [
        ("NA12878", "mother", "NA12892"),
        ("NA12878", "father", "NA12891"),
        ("NA12878", "family_id", "1463"),
        ("NA12892", "mother", "0"),
        ("NA12892", "father", "0"),
        ("NA12892", "family_id", "1463"),
    ]


def test_a_family_line_is_never_the_value_maps_to_seed_or_queue(tmp_path):
    root = tmp_path / "entity_evidence"
    family_lines(root, "D", "family_id", [("PR25", "HG01106")])
    assert list(entries(next(root.rglob("*.ndjson")))) == []
