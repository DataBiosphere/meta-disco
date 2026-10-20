"""SGDP's donors for ANVIL_T2T_CHRY's SGDP genomes (#559): the importer, which writes a sample's lines only where
SGDP's sex and T2T_CHRY's karyotype agree, and reconcile's two identity links: a sample's donor named by a line,
and a donor's main identifier, its own kept as a synonym.

Synthetic manifests, a synthetic SGDP file and a test translation table, so the tests check the mechanism and not
the bundled rows."""

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from meta_disco import sgdp_entities as se
from meta_disco.entity_evidence import iter_entity_evidence, write_entity_file
from meta_disco.models import (
    CLASSIFIED,
    COLLECTED_FROM,
    CONFLICT,
    JOIN_KEY_ENTITY_IDENTIFIER,
    SAME_DONOR_AS,
    SOURCE_EXTERNAL_GROUND_TRUTH,
    SOURCE_IDENTIFIER_RULE,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_METADATA,
    SYNONYMS,
)
from meta_disco.output_utils import DONORS_FILE, RECONCILED_DIR, SAMPLES_FILE, iter_reconciled_artifact
from meta_disco.reconcile import ENTITIES_KEY
from meta_disco.reconcile_entities import gather, reconcile_entities, select_entity_evidence
from meta_disco.sample_identity import Identifier, identifier_rules, reference, sample_list
from meta_disco.schema.classification_model import (
    DonorRecord,
    EntityEvidenceRow,
    ImporterSourceTypeEnum,
    JoinKeyEnum,
    SampleRecord,
)
from meta_disco.source_evidence import EvidenceFileEnvelope, EvidenceFileSource, EvidenceTarget, generation_dir
from tests.manifest_fixtures import CATALOG, write_dataset
from tests.run_fixtures import write_run
from tests.test_reconcile import go, record
from tests.test_value_map import load

STAMP = "20261020T000000Z"
T2T = se.DATASET
TABLE = """rows:
  - id: phenotypic_sex.sgdp_m
    match: {slot: phenotypic_sex, value: M}
    scope: {source: sgdp}
    declares: {phenotypic_sex: Male}
    reason: test
  - id: phenotypic_sex.sgdp_f
    match: {slot: phenotypic_sex, value: F}
    scope: {source: sgdp}
    declares: {phenotypic_sex: Female}
    reason: test
  - id: phenotypic_sex.male
    match: {slot: phenotypic_sex, value: male}
    declares: {phenotypic_sex: Male}
    reason: test
  - id: phenotypic_sex.female
    match: {slot: phenotypic_sex, value: female}
    declares: {phenotypic_sex: Female}
    reason: test
"""

# SGDP's file: its key, the three columns read, and one it is not (with a Latin-1 character in it).
HEADER = "Sample_ID\tSGDP_ID\tPopulation_ID\tGender\tCountry"
SGDP = [
    ("HG01504", "S_Spanish-2", "Spanish", "M", "Spain"),
    ("HGDP01163", "S_Tuscan-2", "Tuscan", "F", "Italy"),
    ("HGDP00725", "S_Palestinian-2", "Palestinian", "M", "Israel"),
    ("NOR111", "S_Norwegian-1", "Norwegian", "U", "Norway"),
    ("DNK05", "S_Dinka-1", "Dinka", "M", "Sudan"),
    ("DNK07", "S_Dinka-2", "", "M", "Côte"),
]


def sgdp_bytes(rows=SGDP, header=HEADER) -> bytes:
    return ("\n".join([header, *("\t".join(r) for r in rows)]) + "\n").encode(se.ENCODING)


def t2t(table: str, sample: str, sgdp_id: str, karyotype: str) -> tuple[str, dict]:
    return table, {se.SAMPLE_TABLES[table]: sample, "sgdp_id": sgdp_id, "karyotype": karyotype}


CHM13, GRCH38 = se.SAMPLE_TABLES
T2T_ROWS = [
    # Both tables, agreeing, and SGDP's sex agreeing: confirmed.
    t2t(CHM13, "simons_data_sample_1", "S_Spanish-2", "XY"),
    t2t(GRCH38, "simons_data_sample_1", "S_Spanish-2", "XY"),
    t2t(CHM13, "simons_data_sample_2", "S_Tuscan-2", "XX"),
    # SGDP says M, the karyotype XX.
    t2t(CHM13, "simons_data_sample_3", "S_Palestinian-2", "XX"),
    # SGDP says U.
    t2t(CHM13, "simons_data_sample_4", "S_Norwegian-1", "XX"),
    # Not in SGDP's file.
    t2t(CHM13, "simons_data_sample_5", "S_Naxi-2", "XY"),
    # The two tables give the sample different karyotypes.
    t2t(CHM13, "simons_data_sample_6", "S_Dinka-1", "XY"),
    t2t(GRCH38, "simons_data_sample_6", "S_Dinka-1", "XX"),
    # Confirmed; SGDP names the person by a contributor's own name, and gives no population.
    t2t(CHM13, "simons_data_sample_7", "S_Dinka-2", "XY"),
]


def read(content: bytes = sgdp_bytes()):
    return lambda: se.SgdpFile(content, se.datetime(2026, 10, 20, tzinfo=se.timezone.utc))


@pytest.fixture
def imported(tmp_path):
    write_dataset(tmp_path / "m", T2T, T2T_ROWS)
    return se.import_sgdp(tmp_path / "m", CATALOG, tmp_path / "entity_evidence", read(), generation=STAMP)


def written(root: Path) -> list[dict]:
    path = generation_dir(root, se.SOURCE, CATALOG, T2T, STAMP) / f"{se.TABLE}.ndjson"
    return [row.model_dump(exclude_none=True) for row in iter_entity_evidence(path)]


# --- the importer ---------------------------------------------------------------------


def test_a_sample_is_written_only_where_sgdp_and_the_karyotype_agree_and_every_other_is_counted(imported):
    assert imported.outcomes == {
        se.CONFIRMED: ["simons_data_sample_1", "simons_data_sample_2", "simons_data_sample_7"],
        se.SEX_CONTRADICTS: ["simons_data_sample_3"],
        se.SEX_NOT_STATED: ["simons_data_sample_4"],
        se.NOT_IN_SGDP_FILE: ["simons_data_sample_5"],
        se.TABLES_DISAGREE: ["simons_data_sample_6"],
    }
    lines = se.describe(imported)
    assert "  confirmed: 3" in lines and "  sex_contradicts: 1: simons_data_sample_3" in lines


def test_a_confirmed_sample_names_its_genome_and_the_genome_its_sex_population_and_person(imported, tmp_path):
    got = written(tmp_path / "entity_evidence")
    assert got[:4] == [
        {
            "field": COLLECTED_FROM,
            "target_key_value": "simons_data_sample_1",
            "raw_value": "S_Spanish-2",
            "column": "SGDP_ID",
            "identifier_column": "sgdp_chm13v2_sample_id",
            "identifier_table": CHM13,
        },
        {
            "field": "phenotypic_sex",
            "target_key_value": "S_Spanish-2",
            "raw_value": "M",
            "column": "Gender",
            "identifier_column": "SGDP_ID",
        },
        {
            "field": "genetic_ancestry",
            "target_key_value": "S_Spanish-2",
            "raw_value": "Spanish",
            "column": "Population_ID",
            "identifier_column": "SGDP_ID",
        },
        {
            "field": SAME_DONOR_AS,
            "target_key_value": "S_Spanish-2",
            "raw_value": "HG01504",
            "column": "Sample_ID",
            "identifier_column": "SGDP_ID",
        },
    ]
    # An empty cell writes nothing: S_Dinka-2 has no population.
    assert [g["field"] for g in got if g["target_key_value"] == "S_Dinka-2"] == ["phenotypic_sex", SAME_DONOR_AS]
    assert {g["target_key_value"] for g in got} == {
        "simons_data_sample_1",
        "S_Spanish-2",
        "simons_data_sample_2",
        "S_Tuscan-2",
        "simons_data_sample_7",
        "S_Dinka-2",
    }
    assert imported.written == len(got)


def test_the_file_is_kept_beside_its_lines_and_imports_again_from_the_copy(imported, tmp_path, monkeypatch):
    kept = imported.directory / se.KEPT_FILE
    assert kept.read_bytes() == sgdp_bytes()
    monkeypatch.setattr(se, "SHA256", hashlib.sha256(sgdp_bytes()).hexdigest())
    again = se.import_sgdp(tmp_path / "m", CATALOG, tmp_path / "again", lambda: se.load_kept(kept), generation=STAMP)
    assert written(tmp_path / "again") == written(tmp_path / "entity_evidence")
    assert again.outcomes == imported.outcomes


def test_a_file_whose_sha256_is_not_the_pinned_one_is_refused(tmp_path):
    path = tmp_path / se.KEPT_FILE
    path.write_bytes(sgdp_bytes())
    with pytest.raises(ValueError, match=r"not the .* this importer was measured against"):
        se.load_kept(path)


def test_the_envelope_names_sgdp_its_version_and_the_target(imported, tmp_path):
    path = generation_dir(tmp_path / "entity_evidence", se.SOURCE, CATALOG, T2T, STAMP) / f"{se.TABLE}.ndjson"
    (first,) = [json.loads(line) for line in path.read_text().splitlines()[:1]]
    envelope = first["evidence_file"]
    assert envelope["source"] == {"repository": "sgdp", "table": se.TABLE, "url": se.URL}
    assert (envelope["source_type"], envelope["source_version"], envelope["source_key"]) == (
        SOURCE_EXTERNAL_GROUND_TRUTH,
        se.SHA256,
        "SGDP_ID",
    )
    assert envelope["target"] == {"system": "anvil", "dataset": T2T, "version": CATALOG}
    assert envelope["target_key"] == JOIN_KEY_ENTITY_IDENTIFIER


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (sgdp_bytes([*SGDP, SGDP[0]]), "names 'S_Spanish-2' twice"),
        (sgdp_bytes(header="Sample_ID\tSGDP_ID\tPopulation_ID\tSex\tCountry"), r"no column \['Gender'\]"),
    ],
)
def test_a_file_naming_a_genome_twice_or_lacking_a_column_is_refused(tmp_path, content, message):
    write_dataset(tmp_path / "m", T2T, T2T_ROWS)
    with pytest.raises(ValueError, match=message):
        se.import_sgdp(tmp_path / "m", CATALOG, tmp_path / "e", read(content), generation=STAMP)


def test_an_import_confirming_no_sample_fails_and_writes_nothing(tmp_path):
    write_dataset(tmp_path / "m", T2T, [t2t(CHM13, "simons_data_sample_3", "S_Palestinian-2", "XX")])
    with pytest.raises(ValueError, match="no SGDP sample confirmed"):
        se.import_sgdp(tmp_path / "m", CATALOG, tmp_path / "e", read(), generation=STAMP)
    assert not (tmp_path / "e").exists() or not any((tmp_path / "e").rglob("*.ndjson"))


# --- reconcile: a donor's main identifier and a sample's donor ------------------------


def settled(root: Path, tmp_path: Path, sample_lists=()):
    paths, skipped = select_entity_evidence(root, "anvil", CATALOG)
    rules = identifier_rules()
    return reconcile_entities(gather(paths, root, load(tmp_path, TABLE), rules), rules, sample_lists, skipped)


def by_id(records: list[dict]) -> dict[str, dict]:
    return {r["identifier"]["id"]: r for r in records}


def lines_file(
    root: Path,
    dataset: str,
    rows: list[tuple[str, str, str]],
    source_type: str = SOURCE_REPOSITORY_METADATA,
    repository: str = "anvil",
    name: str = "t",
) -> None:
    """One entity file, a line per ``(field, identifier string, raw value)``."""
    directory = generation_dir(root, f"{repository}_{source_type}", CATALOG, dataset, STAMP)
    directory.mkdir(parents=True, exist_ok=True)
    envelope = EvidenceFileEnvelope(
        source=EvidenceFileSource(repository=repository, dataset=dataset, table=name, url="https://example.org"),
        source_type=ImporterSourceTypeEnum(source_type),
        source_version="v",
        source_key="id",
        target=EvidenceTarget(system="anvil", dataset=dataset, version=CATALOG),
        target_key=JoinKeyEnum(JOIN_KEY_ENTITY_IDENTIFIER),
        fetched_at="2026-10-20T00:00:00Z",
    )
    write_entity_file(
        directory / f"{name}.ndjson",
        envelope,
        [
            EntityEvidenceRow(field=f, target_key_value=ident, raw_value=raw, column=f"c_{f}", identifier_column="x")
            for f, ident, raw in rows
        ],
    )


def test_a_donor_is_keyed_by_its_main_identifier_and_keeps_its_own_as_a_synonym(imported, tmp_path):
    root = tmp_path / "entity_evidence"
    # 1000 Genomes' own line about the same person, by the Coriell number.
    lines_file(root, "G", [("phenotypic_sex", "HG01504", "male")])
    result = settled(root, tmp_path)
    donors = by_id(result.donors)
    assert "S_Spanish-2" not in donors
    person = donors["HG01504"]
    assert person["identifier"] == {"id": "HG01504", "namespace": "coriell"}
    ((synonym,),) = [person[SYNONYMS]]
    assert synonym["identifier"] == {"id": "S_Spanish-2", "namespace": "sgdp"}
    (attribution,) = synonym["named_by"]
    assert (attribution["source_type"], attribution["rule_id"]) == (SOURCE_EXTERNAL_GROUND_TRUTH, "coriell_hg")
    assert (attribution["source"]["name"], attribution["source"]["column"]) == ("sgdp", "Sample_ID")
    # What SGDP said under its own name is settled on the person's record, beside 1000 Genomes'.
    sex = person["phenotypic_sex"]
    assert (sex["status"], sex["value"]) == (CLASSIFIED, "Male")
    exact = sorted((c["source"]["name"], c["raw_value"], c["match_exact"]) for c in sex["evidence"])
    assert exact == [("anvil", "male", True), ("sgdp", "M", False)]
    # The CEPH-HGDP number is the Tuscan genome's main identifier.
    assert donors["HGDP01163"]["identifier"] == {"id": "HGDP01163", "namespace": "hgdp"}
    assert donors["HGDP01163"]["phenotypic_sex"]["value"] == "Female"
    for record_ in result.donors:
        DonorRecord(**record_)


def test_a_main_identifier_no_rule_recognises_leaves_the_donor_under_its_own_and_is_counted(imported, tmp_path):
    result = settled(tmp_path / "entity_evidence", tmp_path)
    dinka = by_id(result.donors)["S_Dinka-2"]
    assert dinka["identifier"] == {"id": "S_Dinka-2", "namespace": "sgdp"}
    assert SYNONYMS not in dinka
    assert result.report["unrecognised_links"] == [
        {"dataset": T2T, "table": se.TABLE, "lines": 1, "examples": {"DNK07": 1}}
    ]
    assert result.report[SYNONYMS] == {
        "records": 2,
        "synonyms": 2,
        "by_namespace": {"coriell": 1, "hgdp": 1},
        "unjoined": [],
    }


def test_a_sample_is_collected_from_its_donors_main_identifier_citing_the_line(imported, tmp_path):
    members = [Identifier("dataset_local", f"simons_data_sample_{n}", T2T) for n in (1, 3)]
    result = settled(tmp_path / "entity_evidence", tmp_path, [sample_list(members)])
    samples = by_id(result.samples)
    linked = samples["simons_data_sample_1"][COLLECTED_FROM]
    assert linked["donor"] == {"id": "HG01504", "namespace": "coriell"}
    (attribution,) = linked["named_by"]
    assert (attribution["source_type"], attribution["rule_id"]) == (SOURCE_EXTERNAL_GROUND_TRUTH, "sgdp_id")
    assert (attribution["source"]["table"], attribution["source"]["column"]) == (se.TABLE, "SGDP_ID")
    # A sample no line names (its sex disagreed at import) has no donor.
    assert COLLECTED_FROM not in samples["simons_data_sample_3"]
    # A sample a line names has a record though no file names it.
    assert samples["simons_data_sample_7"][COLLECTED_FROM]["donor"] == {"id": "S_Dinka-2", "namespace": "sgdp"}
    assert result.report["samples"]["collected_from"] == {"dataset_local": 3}
    assert result.report["samples"]["collected_from_by_source"] == {SOURCE_EXTERNAL_GROUND_TRUTH: 3}
    for record_ in result.samples:
        SampleRecord(**record_)


def test_a_line_and_an_identifier_rule_naming_one_donor_are_both_listed(tmp_path):
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [(COLLECTED_FROM, "HG00096", "HG00096")], SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    result = settled(root, tmp_path)
    linked = by_id(result.samples)["HG00096"][COLLECTED_FROM]
    assert linked["donor"] == {"id": "HG00096", "namespace": "coriell"}
    assert [a["source_type"] for a in linked["named_by"]] == [SOURCE_IDENTIFIER_RULE, SOURCE_EXTERNAL_GROUND_TRUTH]


def test_sources_naming_different_donors_give_a_sample_none_and_are_counted(tmp_path):
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [(COLLECTED_FROM, "HG00096", "HG00097")], SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    result = settled(root, tmp_path)
    assert COLLECTED_FROM not in by_id(result.samples)["HG00096"]
    assert result.report["samples"]["collected_from_conflicts"] == [
        {
            "identifier": {"id": "HG00096", "namespace": "coriell"},
            "donors": [{"id": "HG00096", "namespace": "coriell"}, {"id": "HG00097", "namespace": "coriell"}],
        }
    ]


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        (
            [(SAME_DONOR_AS, "S_Spanish-2", "HG01504"), (SAME_DONOR_AS, "S_Spanish-2", "HG01503")],
            "names two main identifiers",
        ),
        (
            [(SAME_DONOR_AS, "S_Spanish-2", "S_Spanish-1"), (SAME_DONOR_AS, "S_Spanish-1", "HG01504")],
            "its main identifier is itself a synonym",
        ),
    ],
)
def test_a_synonym_naming_two_main_identifiers_or_a_synonym_joins_none_and_is_listed(tmp_path, rows, reason):
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [*rows, ("phenotypic_sex", "S_Spanish-2", "M")], SOURCE_EXTERNAL_GROUND_TRUTH, "sgdp")
    result = settled(root, tmp_path)
    donors = by_id(result.donors)
    assert donors["S_Spanish-2"]["phenotypic_sex"]["value"] == "Male"
    assert SYNONYMS not in donors["S_Spanish-2"]
    (unjoined,) = [u for u in result.report[SYNONYMS]["unjoined"] if u["identifier"]["id"] == "S_Spanish-2"]
    assert unjoined["reason"] == reason


def test_a_parent_or_a_repository_identifier_naming_a_synonym_reaches_the_main_record(tmp_path):
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [(SAME_DONOR_AS, "S_Spanish-2", "HG01504")], SOURCE_EXTERNAL_GROUND_TRUTH, "sgdp")
    lines_file(root, "D", [("mother", "HG00096", "S_Spanish-2")], name="family")
    lines_file(root, "D", [("donor_repository_id", "S_Spanish-2", "u1")], SOURCE_PUBLISHED_VALUE, name="anvil_donor")
    result = settled(root, tmp_path)
    donors = by_id(result.donors)
    assert donors["HG00096"]["mother"]["value"] == {"id": "HG01504", "namespace": "coriell"}
    assert [r["id"] for r in donors["HG01504"]["repository_ids"]] == ["u1"]
    assert "S_Spanish-2" not in donors


def test_two_sources_disagreeing_on_a_donor_named_two_ways_are_a_conflict(imported, tmp_path):
    root = tmp_path / "entity_evidence"
    lines_file(root, "G", [("phenotypic_sex", "HG01504", "female")])
    assert by_id(settled(root, tmp_path).donors)["HG01504"]["phenotypic_sex"]["status"] == CONFLICT


def test_a_run_reaches_an_sgdp_files_donor_through_its_sample_and_the_synonym(imported, tmp_path):
    run = tmp_path / "output" / "20261020_000000"
    row = record(1)
    members = [Identifier("dataset_local", "simons_data_sample_1", T2T)]
    row["samples"] = reference(members, [{"source_type": "content_read", "rule_id": "vcf_sample_columns"}])
    write_run(run, [row])
    body = json.loads((run / "bam_classifications.json").read_text())
    body["sample_lists"] = [sample_list(members)]
    (run / "bam_classifications.json").write_text(json.dumps(body))
    (tmp_path / "source_evidence").mkdir()
    report = go(run, tmp_path, tmp_path / "source_evidence", load(tmp_path, TABLE))

    samples = by_id(list(iter_reconciled_artifact(run, SAMPLES_FILE)))
    assert samples["simons_data_sample_1"][COLLECTED_FROM]["donor"] == {"id": "HG01504", "namespace": "coriell"}
    donors = by_id(list(iter_reconciled_artifact(run, DONORS_FILE)))
    assert donors["HG01504"][SYNONYMS][0]["identifier"] == {"id": "S_Spanish-2", "namespace": "sgdp"}
    assert report[ENTITIES_KEY][SYNONYMS]["synonyms"] == 2
    first = json.loads(gzip.decompress((run / RECONCILED_DIR / DONORS_FILE).read_bytes()).splitlines()[0])
    assert {f["source_type"] for f in first["reconcile"]["entity_evidence"]} == {SOURCE_EXTERNAL_GROUND_TRUTH}
