"""SGDP's donors for ANVIL_T2T_CHRY's SGDP genomes (#559): the importer, which writes a sample's lines only where
a check confirms its pairing (SGDP's sex and T2T_CHRY's karyotype agree, or a recorded genotype match, #718), and
reconcile's two identity links: a sample's donor named by a line, and a donor's main identifier, its own kept as a
synonym.

Synthetic manifests, a synthetic SGDP file and a test translation table, so the tests check the mechanism and not
the bundled rows."""

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from meta_disco import code_rules
from meta_disco import sgdp_entities as se
from meta_disco.azul_manifest import FORMAT_VERBATIM, manifest_path
from meta_disco.entity_evidence import (
    OUTCOMES_FILE,
    iter_entity_evidence,
    read_outcomes,
    write_entity_file,
    write_outcomes,
)
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
from meta_disco.reconcile_entities import DONOR_REACH, NO_DONOR, gather, reconcile_entities, select_entity_evidence
from meta_disco.sample_identity import Identifier, identifier_rules, reference, sample_list
from meta_disco.schema.classification_model import DonorRecord, EntityEvidenceRow, SampleRecord
from meta_disco.source_evidence import discover, generation_dir
from tests import test_entities
from tests.manifest_fixtures import CATALOG, FETCHED, SERVICE, write_dataset
from tests.run_fixtures import write_run
from tests.test_entities import by_id
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
    ("HGDP01163", "S_Tuscan-2", "Toscàna", "F", "Italy"),
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
    # SGDP says M, the karyotype XX; the genotype record confirms the pairing.
    t2t(CHM13, "simons_data_sample_3", "S_Palestinian-2", "XX"),
    # SGDP says U.
    t2t(CHM13, "simons_data_sample_4", "S_Norwegian-1", "XX"),
    # Not in SGDP's file, and the genotype record matches it to no genome.
    t2t(CHM13, "simons_data_sample_5", "S_Naxi-2", "XY"),
    # The two tables state different karyotypes: no sex check, and no genotype record to confirm it.
    t2t(CHM13, "simons_data_sample_6", "S_Dinka-1", "XY"),
    t2t(GRCH38, "simons_data_sample_6", "S_Dinka-1", "XX"),
    # Confirmed; SGDP names the person by a contributor's own name, and gives no population.
    t2t(CHM13, "simons_data_sample_7", "S_Dinka-2", "XY"),
]


DOWNLOADED = se.datetime(2026, 10, 20, tzinfo=se.timezone.utc)
SEX, GENOTYPE = code_rules.SGDP_SEX_AGREES.id, code_rules.SGDP_GENOTYPE_MATCHES.id


def checks(*entries: tuple[str, str, str | None], catalog: str = CATALOG) -> se.GenotypeChecks:
    """A genotype record, an entry per ``(sample, the genome its tables paired it with, the genome it matched)``."""
    return se.GenotypeChecks(
        catalog, {sample: se.GenotypeCheck(sgdp_id, matched) for sample, sgdp_id, matched in entries}
    )


CHECKS = checks(
    ("simons_data_sample_3", "S_Palestinian-2", "S_Palestinian-2"),
    ("simons_data_sample_5", "S_Naxi-2", None),
)


def read(content: bytes = sgdp_bytes()):
    return lambda: se.SgdpFile(content, DOWNLOADED)


def run(tmp_path: Path, root: str, reader=None, rows=T2T_ROWS, record: se.GenotypeChecks = CHECKS) -> se.Import:
    write_dataset(tmp_path / "m", T2T, rows)
    return se.import_sgdp(
        tmp_path / "m", CATALOG, tmp_path / root, SERVICE, reader or read(), generation=STAMP, checks=record
    )


@pytest.fixture
def imported(tmp_path):
    return run(tmp_path, "entity_evidence")


def path_of(root: Path, table: str) -> Path:
    return generation_dir(root, se.SOURCE, CATALOG, T2T, STAMP) / f"{table}.ndjson"


def written(root: Path, table: str = se.TABLE) -> list[dict]:
    return [row.model_dump(exclude_none=True) for row in iter_entity_evidence(path_of(root, table))]


def envelope_of(root: Path, table: str) -> dict:
    return json.loads(path_of(root, table).read_text().splitlines()[0])["evidence_file"]


# --- the importer ---------------------------------------------------------------------


def test_a_sample_is_written_only_where_a_check_confirms_it_and_every_sample_says_why(imported):
    found = {
        s: (o.sgdp_id, o.pairing, o.sex_check, o.genotype_check, o.confirmed_by) for s, o in imported.outcomes.items()
    }
    assert found == {
        "simons_data_sample_1": ("S_Spanish-2", se.PAIRED, se.SEX_AGREES, se.NOT_CHECKED, (SEX,)),
        "simons_data_sample_2": ("S_Tuscan-2", se.PAIRED, se.SEX_AGREES, se.NOT_CHECKED, (SEX,)),
        # The genotypes confirm what the sexes cannot.
        "simons_data_sample_3": ("S_Palestinian-2", se.PAIRED, se.SEX_CONTRADICTS, se.GENOTYPE_MATCHES, (GENOTYPE,)),
        "simons_data_sample_4": ("S_Norwegian-1", se.PAIRED, se.SEX_NOT_STATED, se.NOT_CHECKED, ()),
        # Not a pairing to check by sex; the record is still read.
        "simons_data_sample_5": ("S_Naxi-2", se.NOT_IN_SGDP_FILE, se.NOT_CHECKED, se.GENOTYPE_NO_MATCH, ()),
        "simons_data_sample_6": ("S_Dinka-1", se.PAIRED, se.KARYOTYPES_DISAGREE, se.NOT_CHECKED, ()),
        "simons_data_sample_7": ("S_Dinka-2", se.PAIRED, se.SEX_AGREES, se.NOT_CHECKED, (SEX,)),
    }
    assert imported.linked == [
        "simons_data_sample_1",
        "simons_data_sample_2",
        "simons_data_sample_3",
        "simons_data_sample_7",
    ]
    assert imported.written == {CHM13: 4, GRCH38: 1, se.TABLE: 11}
    assert se.describe(imported) == [
        f"{T2T} -> {imported.directory} (7 SGDP samples)",
        f"  {CHM13}: 4 lines",
        f"  {GRCH38}: 1 lines",
        f"  {se.TABLE}: 11 lines",
        "  linked: 4",
        f"    confirmed by {SEX}: 3",
        f"    confirmed by {GENOTYPE}: 1",
        "  left out: 3",
        "    simons_data_sample_4 (S_Norwegian-1): paired, sex not_stated, genotype not_checked",
        "    simons_data_sample_5 (S_Naxi-2): not_in_sgdp_file, sex not_checked, genotype no_match",
        "    simons_data_sample_6 (S_Dinka-1): paired, sex karyotypes_disagree, genotype not_checked",
    ]


def test_every_samples_outcome_is_written_beside_the_evidence_and_read_as_no_evidence(imported, tmp_path):
    root = tmp_path / "entity_evidence"
    document = json.loads((imported.directory / OUTCOMES_FILE).read_text())
    assert (document["source"], document["dataset"]) == (se.SOURCE, T2T)
    assert [o["sample"] for o in document["samples"]] == sorted(imported.outcomes)
    assert document["samples"][2] == {
        "sample": "simons_data_sample_3",
        "sgdp_id": "S_Palestinian-2",
        "pairing": se.PAIRED,
        "sex_check": se.SEX_CONTRADICTS,
        "genotype_check": se.GENOTYPE_MATCHES,
        "confirmed_by": [GENOTYPE],
    }
    assert all(p.suffix == ".ndjson" for p in discover(root))
    outcomes = read_outcomes(discover(root))
    ((said,),) = [outcomes[(T2T, "simons_data_sample_5")]]
    assert (said["source"], said["genotype_check"]) == (se.SOURCE, se.GENOTYPE_NO_MATCH)


def test_a_recorded_non_match_leaves_out_a_sample_whose_sex_agrees(tmp_path):
    result = run(tmp_path, "e", record=checks(("simons_data_sample_1", "S_Spanish-2", "S_Dinka-1")))
    assert result.outcomes["simons_data_sample_1"].genotype_check == se.GENOTYPE_NO_MATCH
    assert "simons_data_sample_1" not in result.linked
    assert "simons_data_sample_1" not in {g["target_key_value"] for g in written(tmp_path / "e", CHM13)}


@pytest.mark.parametrize(
    ("record", "message"),
    [
        # The tables now pair the sample with another genome than the one measured.
        (checks(("simons_data_sample_3", "S_Tuscan-2", "S_Tuscan-2")), "was measured as S_Tuscan-2"),
        (checks(("simons_data_sample_99", "S_X-1", "S_X-1")), "names simons_data_sample_99, which no T2T_CHRY"),
        (checks(catalog="anvil14"), "measured on anvil14's files"),
        # Sample 6's tables name S_Dinka-1 alone; sample 8's below name none.
        (checks(("simons_data_sample_6", "", "S_X-1")), "was measured as , but"),
    ],
)
def test_a_genotype_record_the_tables_do_not_bear_out_is_refused_and_nothing_written(tmp_path, record, message):
    with pytest.raises(ValueError, match=message):
        run(tmp_path, "e", record=record)
    assert not (tmp_path / "e").exists() or not any((tmp_path / "e").rglob("*.ndjson"))


def test_the_bundled_genotype_record_loads():
    record = se.load_genotype_checks()
    assert record.catalog == CATALOG
    assert all(sample.startswith("simons_data_sample_") for sample in record.by_sample)


GOOD = """catalog: anvil15
datasets:
  ANVIL_T2T_CHRY:
    measured: "2026-10-22"
    region: chr22:1-2
    references: {sgdp: "https://s/x.bcf"}
    samples:
      simons_data_sample_3:
        sgdp_id: S_Palestinian-2
        matched: null
        best: {sgdp: [{genome: S_X-1, concordance: 0.5, sites: 10}]}
"""


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (("  ANVIL_T2T_CHRY:", "  ANVIL_T2T:"), "not ANVIL_T2T_CHRY alone"),
        (("        matched: null", "        matched: null\n        extra: 1"), "keys are"),
        (("        matched: null", "        matched: ''"), "matched a genome or null"),
        (("        sgdp_id: S_Palestinian-2", "        sgdp_id: ''"), "sgdp_id must name a genome"),
        (("      simons_data_sample_3:", "      7:"), "a sample is named by a non-empty string"),
        (
            ("        sgdp_id: S_Palestinian-2\n", "        sgdp_id: S_Palestinian-2\n        sgdp_id: S_X-1\n"),
            "duplicate key",
        ),
    ],
)
def test_a_malformed_genotype_record_is_refused(tmp_path, change, message):
    good, bad = tmp_path / "good.yaml", tmp_path / "bad.yaml"
    good.write_text(GOOD)
    bad.write_text(GOOD.replace(*change))
    assert se.load_genotype_checks(good).by_sample["simons_data_sample_3"] == se.GenotypeCheck("S_Palestinian-2", None)
    with pytest.raises(ValueError, match=message):
        se.load_genotype_checks(bad)


def test_each_table_cites_the_pairing_it_states_and_sgdp_its_genomes(imported, tmp_path):
    root = tmp_path / "entity_evidence"
    # T2T_CHRY's tables pair each confirmed sample with its SGDP genome, each table for its own rows.
    assert written(root, CHM13)[0] == {
        "field": COLLECTED_FROM,
        "target_key_value": "simons_data_sample_1",
        "raw_value": "S_Spanish-2",
        "column": "sgdp_id",
        "identifier_column": "sgdp_chm13v2_sample_id",
    }
    assert [g["target_key_value"] for g in written(root, CHM13)] == [
        "simons_data_sample_1",
        "simons_data_sample_2",
        "simons_data_sample_3",
        "simons_data_sample_7",
    ]
    assert [g["target_key_value"] for g in written(root, GRCH38)] == ["simons_data_sample_1"]
    # SGDP's file speaks only of its genomes, by its names, a cell each.
    got = written(root)
    dinka = [(g["field"], g["raw_value"], g["column"]) for g in got if g["target_key_value"] == "S_Dinka-2"]
    # An empty cell writes nothing: S_Dinka-2 has no population.
    assert dinka == [("phenotypic_sex", "M", "Gender"), (SAME_DONOR_AS, "DNK07", "Sample_ID")]
    assert {g["identifier_column"] for g in got} == {"SGDP_ID"}
    assert {g["target_key_value"] for g in got} == {"S_Spanish-2", "S_Tuscan-2", "S_Palestinian-2", "S_Dinka-2"}
    assert len(got) == 11


def test_each_file_names_its_source_kind_and_when_its_source_was_fetched(imported, tmp_path):
    root = tmp_path / "entity_evidence"
    t2t_envelope = envelope_of(root, CHM13)
    assert t2t_envelope["source"] == {"repository": "anvil", "dataset": T2T, "table": CHM13, "url": SERVICE}
    assert (t2t_envelope["source_type"], t2t_envelope["source_key"]) == (
        SOURCE_REPOSITORY_METADATA,
        "sgdp_chm13v2_sample_id",
    )
    assert t2t_envelope["fetched_at"].startswith(FETCHED)
    sgdp_envelope = envelope_of(root, se.TABLE)
    assert sgdp_envelope["source"] == {"repository": "sgdp", "table": se.TABLE, "url": se.URL}
    assert (sgdp_envelope["source_type"], sgdp_envelope["source_version"], sgdp_envelope["source_key"]) == (
        SOURCE_EXTERNAL_GROUND_TRUTH,
        se.SHA256,
        "SGDP_ID",
    )
    assert sgdp_envelope["fetched_at"] == DOWNLOADED.isoformat()
    for envelope in (t2t_envelope, sgdp_envelope):
        assert envelope["target"] == {"system": "anvil", "dataset": T2T, "version": CATALOG}
        assert envelope["target_key"] == JOIN_KEY_ENTITY_IDENTIFIER


def test_the_file_is_kept_and_imports_again_from_the_copy_with_its_download_time(imported, tmp_path, monkeypatch):
    kept = imported.directory / se.KEPT_FILE
    assert kept.read_bytes() == sgdp_bytes()
    monkeypatch.setattr(se, "SHA256", hashlib.sha256(sgdp_bytes()).hexdigest())
    again = run(tmp_path, "again", lambda: se.load_kept(kept))
    for table in (CHM13, GRCH38, se.TABLE):
        assert written(tmp_path / "again", table) == written(tmp_path / "entity_evidence", table)
    assert again.outcomes == imported.outcomes
    assert (again.directory / OUTCOMES_FILE).read_text() == (imported.directory / OUTCOMES_FILE).read_text()
    # When SGDP's file was downloaded, not when it was imported again.
    assert envelope_of(tmp_path / "again", se.TABLE)["fetched_at"] == DOWNLOADED.isoformat()


def test_a_copy_with_another_sha256_or_no_generation_beside_it_is_refused(tmp_path, monkeypatch):
    path = tmp_path / se.KEPT_FILE
    path.write_bytes(sgdp_bytes())
    with pytest.raises(ValueError, match=r"not the .* this importer was measured against"):
        se.load_kept(path)
    monkeypatch.setattr(se, "SHA256", hashlib.sha256(sgdp_bytes()).hexdigest())
    with pytest.raises(ValueError, match="to say when it was downloaded"):
        se.load_kept(path)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (sgdp_bytes([*SGDP, SGDP[0]]), "names 'S_Spanish-2' twice"),
        (sgdp_bytes(header="Sample_ID\tSGDP_ID\tPopulation_ID\tSex\tCountry"), r"no column \['Gender'\]"),
    ],
)
def test_a_file_naming_a_genome_twice_or_lacking_a_column_is_refused(tmp_path, content, message):
    with pytest.raises(ValueError, match=message):
        run(tmp_path, "e", read(content))


def test_an_import_confirming_no_sample_fails_and_writes_nothing(tmp_path):
    with pytest.raises(ValueError, match="no SGDP sample confirmed"):
        run(tmp_path, "e", rows=[t2t(CHM13, "simons_data_sample_3", "S_Palestinian-2", "XX")], record=checks())
    assert not any((tmp_path / "e").rglob("*.ndjson"))


# --- reconcile: a donor's main identifier and a sample's donor ------------------------


def settled(root: Path, tmp_path: Path, sample_lists=()):
    return test_entities.settled(root, tmp_path, sample_lists, TABLE)


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
    write_entity_file(
        directory / f"{name}.ndjson",
        test_entities.envelope(source_type=source_type, dataset=dataset, repository=repository, table=name),
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
        "records": 3,
        "synonyms": 3,
        "by_namespace": {"coriell": 1, "hgdp": 2},
        "unjoined": [],
    }


def test_a_sample_is_collected_from_its_donors_main_identifier_citing_each_table_pairing_them(imported, tmp_path):
    members = [Identifier("dataset_local", f"simons_data_sample_{n}", T2T) for n in (1, 4)]
    result = settled(tmp_path / "entity_evidence", tmp_path, [sample_list(members)])
    samples = by_id(result.samples)
    linked = samples["simons_data_sample_1"][COLLECTED_FROM]
    assert linked["donor"] == {"id": "HG01504", "namespace": "coriell"}
    # Each T2T_CHRY table pairing the sample with its genome, cited by the rule recognising the genome's name.
    assert [
        (a["source_type"], a["rule_id"], a["source"]["table"], a["source"]["column"]) for a in linked["named_by"]
    ] == [
        (SOURCE_REPOSITORY_METADATA, "sgdp_id", CHM13, "sgdp_id"),
        (SOURCE_REPOSITORY_METADATA, "sgdp_id", GRCH38, "sgdp_id"),
    ]
    # A sample no line names (no check confirmed it at import) has no donor.
    assert COLLECTED_FROM not in samples["simons_data_sample_4"]
    # One the genotype record confirmed has its donor, as one whose sex agrees does.
    assert samples["simons_data_sample_3"][COLLECTED_FROM]["donor"] == {"id": "HGDP00725", "namespace": "hgdp"}
    # A sample a line names has a record though no file names it.
    assert samples["simons_data_sample_7"][COLLECTED_FROM]["donor"] == {"id": "S_Dinka-2", "namespace": "sgdp"}
    assert result.report["samples"]["collected_from"] == {"dataset_local": 4}
    assert result.report["samples"]["collected_from_by_source"] == {SOURCE_REPOSITORY_METADATA: 4}
    for record_ in result.samples:
        SampleRecord(**record_)


def test_a_line_and_an_identifier_rule_naming_one_donor_are_both_listed(tmp_path):
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [(COLLECTED_FROM, "HG00096", "HG00096")], SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    result = settled(root, tmp_path)
    linked = by_id(result.samples)["HG00096"][COLLECTED_FROM]
    assert linked["donor"] == {"id": "HG00096", "namespace": "coriell"}
    assert [a["source_type"] for a in linked["named_by"]] == [SOURCE_IDENTIFIER_RULE, SOURCE_EXTERNAL_GROUND_TRUTH]


def test_sources_naming_different_donors_give_a_sample_none_each_donor_a_record_and_are_counted(tmp_path):
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [(COLLECTED_FROM, "HG00096", "HG00097")], SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    result = settled(root, tmp_path)
    assert COLLECTED_FROM not in by_id(result.samples)["HG00096"]
    # Each donor a source named has a record, though the sample is linked to neither.
    assert {"HG00096", "HG00097"} <= set(by_id(result.donors))
    (conflict,) = result.report["samples"]["collected_from_conflicts"]
    assert conflict["identifier"] == {"id": "HG00096", "namespace": "coriell"}
    # Who named which donor.
    assert [(d["donor"]["id"], [a["source_type"] for a in d["named_by"]]) for d in conflict["donors"]] == [
        ("HG00096", [SOURCE_IDENTIFIER_RULE]),
        ("HG00097", [SOURCE_EXTERNAL_GROUND_TRUTH]),
    ]


def test_each_identifier_a_branching_chain_names_has_a_record(tmp_path):
    root = tmp_path / "entity_evidence"
    rows = [(SAME_DONOR_AS, "S_Tuscan-2", "HG01504"), (SAME_DONOR_AS, "S_Tuscan-2", "HG01503")]
    lines_file(root, "D", rows, SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    assert {"S_Tuscan-2", "HG01503", "HG01504"} <= set(by_id(settled(root, tmp_path).donors))


def test_synonyms_are_followed_to_the_end_of_their_chain_each_keeping_its_own_steps_source(tmp_path):
    root = tmp_path / "entity_evidence"
    chain = [
        (SAME_DONOR_AS, "S_Spanish-2", "S_Spanish-1"),
        (SAME_DONOR_AS, "S_Spanish-1", "HG01504"),
        (SAME_DONOR_AS, "HG01504", "NA99999"),
        ("phenotypic_sex", "S_Spanish-2", "M"),
    ]
    lines_file(root, "D", chain, SOURCE_EXTERNAL_GROUND_TRUTH, "sgdp")
    result = settled(root, tmp_path)
    donors = by_id(result.donors)
    assert set(donors) == {"NA99999"}
    person = donors["NA99999"]
    assert person["phenotypic_sex"]["value"] == "Male"
    steps = [(s["identifier"]["id"], [a["rule_id"] for a in s["named_by"]]) for s in person[SYNONYMS]]
    # In identifier order, each cited by the rule recognising the identifier its own line named.
    assert steps == [
        ("HG01504", ["coriell_cell_line_or_dna"]),
        ("S_Spanish-1", ["coriell_hg"]),
        ("S_Spanish-2", ["sgdp_id"]),
    ]
    # One record, three synonyms, counted by the record's namespace.
    assert result.report[SYNONYMS] == {"records": 1, "synonyms": 3, "by_namespace": {"coriell": 3}, "unjoined": []}


@pytest.mark.parametrize(
    ("rows", "refused", "reason"),
    [
        (
            [(SAME_DONOR_AS, "S_Spanish-2", "HG01504"), (SAME_DONOR_AS, "S_Spanish-2", "HG01503")],
            {"S_Spanish-2"},
            "its chain reaches sgdp:S_Spanish-2, which names 2 identifiers",
        ),
        (
            # S_Spanish-1's chain branches at HG01504, so it joins nothing either.
            [
                (SAME_DONOR_AS, "S_Spanish-1", "HG01504"),
                (SAME_DONOR_AS, "HG01504", "NA99999"),
                (SAME_DONOR_AS, "HG01504", "NA88888"),
                (SAME_DONOR_AS, "S_Spanish-2", "HG01504"),
            ],
            {"S_Spanish-1", "S_Spanish-2", "HG01504"},
            "its chain reaches coriell:HG01504, which names 2 identifiers",
        ),
        (
            [(SAME_DONOR_AS, "S_Spanish-2", "S_Spanish-1"), (SAME_DONOR_AS, "S_Spanish-1", "S_Spanish-2")],
            {"S_Spanish-1", "S_Spanish-2"},
            "its chain comes back on itself",
        ),
    ],
)
def test_a_chain_that_branches_or_loops_joins_none_and_each_synonym_on_it_is_listed(tmp_path, rows, refused, reason):
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [*rows, ("phenotypic_sex", "S_Spanish-2", "M")], SOURCE_EXTERNAL_GROUND_TRUTH, "sgdp")
    result = settled(root, tmp_path)
    donors = by_id(result.donors)
    assert donors["S_Spanish-2"]["phenotypic_sex"]["value"] == "Male"
    assert not any(SYNONYMS in d for d in donors.values())
    unjoined = {u["identifier"]["id"]: u["reason"] for u in result.report[SYNONYMS]["unjoined"]}
    assert set(unjoined) == refused
    assert set(unjoined.values()) == {reason}


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
    named_by = [{"source_type": "content_read", "rule_id": "vcf_sample_columns"}]

    def sample(n: int) -> Identifier:
        return Identifier("dataset_local", f"simons_data_sample_{n}", T2T)

    # A file of one linked sample, twice; one of a sample left out; one of a linked and a left-out sample.
    lists = [[sample(1)], [sample(1)], [sample(5)], [sample(1), sample(5)]]
    rows = [record(n + 1, dataset=T2T) for n in range(len(lists))]
    for row, members in zip(rows, lists, strict=True):
        row["samples"] = reference(members, named_by)
    write_run(run, rows)
    body = json.loads((run / "bam_classifications.json").read_text())
    body["sample_lists"] = [sample_list(members) for members in lists[1:]]
    (run / "bam_classifications.json").write_text(json.dumps(body))
    (tmp_path / "source_evidence").mkdir()
    report = go(run, tmp_path, tmp_path / "source_evidence", load(tmp_path, TABLE))

    samples = by_id(list(iter_reconciled_artifact(run, SAMPLES_FILE)))
    assert samples["simons_data_sample_1"][COLLECTED_FROM]["donor"] == {"id": "HG01504", "namespace": "coriell"}
    donors = by_id(list(iter_reconciled_artifact(run, DONORS_FILE)))
    assert donors["HG01504"][SYNONYMS][0]["identifier"] == {"id": "S_Spanish-2", "namespace": "sgdp"}
    assert report[ENTITIES_KEY][SYNONYMS]["synonyms"] == 3
    # Whether each file's samples reach a donor, and why the one that does not has none.
    assert report[ENTITIES_KEY][DONOR_REACH] == {
        T2T: {
            # Each file is counted, the two settling to one list both.
            "files_with_samples": 4,
            "every_sample_has_a_donor": 2,
            "one_sample_without_donor": 1,
            "several_samples_some_without_donor": 1,
        }
    }
    (said,) = report[ENTITIES_KEY]["samples"][NO_DONOR][T2T]
    assert said["identifier"] == sample(5).to_dict()
    ((outcome,),) = [said["outcomes"]]
    assert (outcome["source"], outcome["pairing"], outcome["genotype_check"]) == (
        se.SOURCE,
        se.NOT_IN_SGDP_FILE,
        se.GENOTYPE_NO_MATCH,
    )
    first = json.loads(gzip.decompress((run / RECONCILED_DIR / DONORS_FILE).read_bytes()).splitlines()[0])
    assert {f["source_type"] for f in first["reconcile"]["entity_evidence"]} == {
        SOURCE_EXTERNAL_GROUND_TRUTH,
        SOURCE_REPOSITORY_METADATA,
    }


def test_a_karyotype_or_a_cell_the_file_leaves_out_states_no_sex_and_writes_nothing(tmp_path):
    rows = [
        t2t(CHM13, "simons_data_sample_1", "S_Spanish-2", "XY"),
        t2t(CHM13, "simons_data_sample_2", "S_Tuscan-2", ""),
    ]
    # S_Spanish-2's row stops after Sample_ID and SGDP_ID: DictReader gives its other cells as None.
    short = sgdp_bytes([("HG01504", "S_Spanish-2"), SGDP[1]])
    with pytest.raises(ValueError, match="no SGDP sample confirmed"):
        run(tmp_path, "e", read(short), rows, checks())
    found = se.outcome("s", [se.T2tRow(CHM13, "s", "S_Tuscan-2", None)], se.sgdp_rows(sgdp_bytes()), checks())
    assert found.sex_check == se.SEX_NOT_STATED


def test_a_sample_or_donor_a_failed_link_names_still_has_a_record(tmp_path):
    """A link line is its subject's only evidence here: the link fails, the record stays, and the failure is counted."""
    root = tmp_path / "entity_evidence"
    rows = [
        (COLLECTED_FROM, "HG00096", "NOT_A_DONOR"),  # a donor no rule recognises
        (SAME_DONOR_AS, "S_Spanish-2", "NOT_A_DONOR"),  # a main identifier no rule recognises
        (SAME_DONOR_AS, "S_Tuscan-2", "HG01504"),  # a chain that branches
        (SAME_DONOR_AS, "S_Tuscan-2", "HG01503"),
    ]
    lines_file(root, "D", rows, SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    result = settled(root, tmp_path)
    assert {"S_Spanish-2", "S_Tuscan-2"} <= set(by_id(result.donors))
    sample = by_id(result.samples)["HG00096"]
    # Its identifier rule still links it to its own donor; the failed line adds nothing.
    assert [a["source_type"] for a in sample[COLLECTED_FROM]["named_by"]] == [SOURCE_IDENTIFIER_RULE]
    assert result.report["unrecognised_links"] == [
        {"dataset": "D", "table": "t", "lines": 2, "examples": {"NOT_A_DONOR": 2}}
    ]
    assert [u["identifier"]["id"] for u in result.report[SYNONYMS]["unjoined"]] == ["S_Tuscan-2"]


def test_a_dataset_local_sample_a_failed_link_names_still_has_a_record(tmp_path):
    root = tmp_path / "entity_evidence"
    lines_file(root, T2T, [(COLLECTED_FROM, "simons_data_sample_9", "NOT_A_DONOR")], SOURCE_REPOSITORY_METADATA)
    sample = by_id(settled(root, tmp_path).samples)["simons_data_sample_9"]
    assert COLLECTED_FROM not in sample


def test_a_chain_whose_tail_loops_joins_none_and_does_not_hang(tmp_path):
    root = tmp_path / "entity_evidence"
    rows = [
        (SAME_DONOR_AS, "S_Spanish-2", "HG01504"),
        (SAME_DONOR_AS, "HG01504", "NA99999"),
        (SAME_DONOR_AS, "NA99999", "HG01504"),
    ]
    lines_file(root, "D", rows, SOURCE_EXTERNAL_GROUND_TRUTH, "sgdp")
    unjoined = {u["identifier"]["id"]: u["reason"] for u in settled(root, tmp_path).report[SYNONYMS]["unjoined"]}
    assert unjoined == dict.fromkeys(["HG01504", "NA99999", "S_Spanish-2"], "its chain comes back on itself")


def test_a_line_naming_its_own_identifier_says_nothing(tmp_path):
    """`GM19908` is written `NA19908`: one identifier, so the line joins nothing and is not a loop."""
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [(SAME_DONOR_AS, "GM19908", "NA19908")], SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    result = settled(root, tmp_path)
    assert result.report[SYNONYMS]["unjoined"] == [] and result.report[SYNONYMS]["synonyms"] == 0


def test_the_identifier_rules_donor_is_read_as_its_main_identifier_too(tmp_path):
    """A file's sample `coriell:HG01504` is its own donor by rule; HG01504 being a synonym, the link points to the
    main identifier and agrees with a line naming it."""
    root = tmp_path / "entity_evidence"
    rows = [(SAME_DONOR_AS, "HG01504", "NA99999"), (COLLECTED_FROM, "HG01504", "NA99999")]
    lines_file(root, "D", rows, SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    result = settled(root, tmp_path, [sample_list([Identifier("coriell", "HG01504")])])
    linked = by_id(result.samples)["HG01504"][COLLECTED_FROM]
    assert linked["donor"] == {"id": "NA99999", "namespace": "coriell"}
    assert [a["source_type"] for a in linked["named_by"]] == [SOURCE_IDENTIFIER_RULE, SOURCE_EXTERNAL_GROUND_TRUTH]
    assert "HG01504" not in by_id(result.donors)


def test_a_line_repeated_is_cited_once(tmp_path):
    root = tmp_path / "entity_evidence"
    rows = [(SAME_DONOR_AS, "S_Spanish-2", "HG01504")] * 2 + [
        (COLLECTED_FROM, "simons_data_sample_1", "S_Spanish-2")
    ] * 2
    lines_file(root, T2T, rows, SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    result = settled(root, tmp_path)
    (synonym,) = by_id(result.donors)["HG01504"][SYNONYMS]
    assert len(synonym["named_by"]) == 1
    assert len(by_id(result.samples)["simons_data_sample_1"][COLLECTED_FROM]["named_by"]) == 1


def test_each_table_names_its_samples_by_its_own_column(imported, tmp_path):
    for table, column in se.SAMPLE_TABLES.items():
        assert {g["identifier_column"] for g in written(tmp_path / "entity_evidence", table)} == {column}


def test_a_blank_or_missing_cell_writes_no_line_and_a_row_naming_no_sample_is_passed_over(tmp_path):
    sgdp = {"S_X-1": {"Gender": "M", "Population_ID": "  ", "Sample_ID": None}}
    assert [r.field for r in se.donor_lines(["S_X-1"], sgdp)] == ["phenotypic_sex"]  # type: ignore[arg-type]
    write_dataset(tmp_path / "m", T2T, [(CHM13, {"sgdp_id": "S_X-1", "karyotype": "XY"}), *T2T_ROWS[:1]])
    manifest = manifest_path(tmp_path / "m", CATALOG, T2T, FORMAT_VERBATIM)
    assert list(se.t2t_rows(manifest)) == ["simons_data_sample_1"]


def test_a_link_whose_field_is_spelled_with_a_json_escape_is_still_read(tmp_path):
    """JSON may escape any character of a key: `same\\u005fdonor_as` is `same_donor_as`, and is read as one."""
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [(SAME_DONOR_AS, "S_Spanish-2", "HG01504")], SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    (path,) = root.rglob("*.ndjson")
    text = path.read_text()
    assert '"same_donor_as"' in text
    path.write_text(text.replace('"same_donor_as"', '"same\\u005fdonor_as"'))
    assert '"same_donor_as"' not in path.read_text()
    donors = by_id(settled(root, tmp_path).donors)
    assert [s["identifier"]["id"] for s in donors["HG01504"][SYNONYMS]] == ["S_Spanish-2"]


def test_tables_naming_different_genomes_for_a_sample_disagree_whatever_the_karyotypes(tmp_path):
    rows = [
        t2t(CHM13, "simons_data_sample_2", "S_Tuscan-2", "XX"),
        t2t(CHM13, "simons_data_sample_9", "S_Spanish-2", "XY"),
        t2t(GRCH38, "simons_data_sample_9", "S_Dinka-2", "XY"),
    ]
    # A genotype record for the sample cannot settle which genome the tables mean.
    result = run(tmp_path, "e", rows=rows, record=checks(("simons_data_sample_9", "S_Spanish-2", "S_Spanish-2")))
    assert result.outcomes["simons_data_sample_9"] == se.Outcome("simons_data_sample_9", None, se.TABLES_DISAGREE)
    assert result.linked == ["simons_data_sample_2"]
    # Its only GRCh38 row writes no link, and no table writes one for it.
    assert not path_of(tmp_path / "e", GRCH38).exists()
    assert [g["target_key_value"] for g in written(tmp_path / "e", CHM13)] == ["simons_data_sample_2"]


def test_a_download_whose_sha256_is_not_the_pinned_one_is_refused(monkeypatch):
    class Response:
        content = b"another file"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(se.requests, "get", lambda *a, **k: Response())
    with pytest.raises(ValueError, match="this importer was measured against"):
        se.fetch()


def test_one_repository_identifier_tied_through_a_synonym_and_its_main_names_one_record(tmp_path):
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [(SAME_DONOR_AS, "S_Spanish-2", "HG01504")], SOURCE_EXTERNAL_GROUND_TRUTH, "sgdp")
    lines_file(root, "D", [("donor_repository_id", "S_Spanish-2", "u1")], SOURCE_PUBLISHED_VALUE, name="anvil_donor")
    lines_file(root, "D", [("donor_repository_id", "HG01504", "u1")], SOURCE_PUBLISHED_VALUE, name="anvil_donor_2")
    donors = by_id(settled(root, tmp_path).donors)
    assert {r["id"] for r in donors["HG01504"]["repository_ids"]} == {"u1"}
    assert "S_Spanish-2" not in donors


def test_a_population_in_latin_1_is_written_as_sgdp_wrote_it(imported, tmp_path):
    (line,) = [
        g
        for g in written(tmp_path / "entity_evidence")
        if g["target_key_value"] == "S_Tuscan-2" and g["field"] == "genetic_ancestry"
    ]
    assert line["raw_value"] == "Toscàna"


def test_a_link_line_about_an_unrecognised_donor_is_counted_once_and_read_no_further(tmp_path):
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [(SAME_DONOR_AS, "NOT-AN-ID", "HG01504")], SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    result = settled(root, tmp_path)
    assert result.report["unrecognised_links"] == []
    assert [u["examples"] for u in result.report["unrecognised"]] == [{"NOT-AN-ID": 1}]
    assert "HG01504" not in by_id(result.donors)


@pytest.mark.parametrize("row", [{"sample": ""}, {"genotype_check": "matches"}, {"sample": "s", "source": "other"}])
def test_an_outcome_naming_no_sample_or_its_own_source_is_refused_before_it_is_written(tmp_path, row):
    with pytest.raises(ValueError, match="every outcome names its sample"):
        write_outcomes(tmp_path, se.SOURCE, T2T, [row])
    assert not (tmp_path / OUTCOMES_FILE).exists()


def test_an_outcomes_file_whose_row_names_its_own_source_is_refused_at_read(tmp_path):
    (tmp_path / "x.ndjson").write_text("")
    document = {"source": se.SOURCE, "dataset": T2T, "samples": [{"sample": "s", "source": "other"}]}
    (tmp_path / OUTCOMES_FILE).write_text(json.dumps(document))
    with pytest.raises(ValueError, match="names its own source"):
        read_outcomes([tmp_path / "x.ndjson"])


def test_a_blank_cell_disagrees_with_no_other_and_two_stated_karyotypes_leave_the_genotype_to_confirm(tmp_path):
    rows = [
        # One table states the karyotype, the other leaves it blank: the sex check reads the one stated.
        t2t(CHM13, "simons_data_sample_1", "S_Spanish-2", "XY"),
        t2t(GRCH38, "simons_data_sample_1", "S_Spanish-2", ""),
        # One table names the genome, the other leaves it blank: paired.
        t2t(CHM13, "simons_data_sample_2", "S_Tuscan-2", "XX"),
        t2t(GRCH38, "simons_data_sample_2", "", "XX"),
        # Two karyotypes stated: the genotype record confirms the pairing.
        t2t(CHM13, "simons_data_sample_3", "S_Palestinian-2", "XY"),
        t2t(GRCH38, "simons_data_sample_3", "S_Palestinian-2", "XX"),
        # No genome named at all.
        t2t(CHM13, "simons_data_sample_8", "", "XY"),
    ]
    two_genomes = [
        t2t(CHM13, "simons_data_sample_9", "S_Spanish-2", "XY"),
        t2t(GRCH38, "simons_data_sample_9", "S_Dinka-2", "XY"),
    ]
    result = run(
        tmp_path, "e", rows=rows, record=checks(("simons_data_sample_3", "S_Palestinian-2", "S_Palestinian-2"))
    )
    found = {s: (o.pairing, o.sex_check, o.confirmed_by) for s, o in result.outcomes.items()}
    assert found == {
        "simons_data_sample_1": (se.PAIRED, se.SEX_AGREES, (SEX,)),
        "simons_data_sample_2": (se.PAIRED, se.SEX_AGREES, (SEX,)),
        "simons_data_sample_3": (se.PAIRED, se.KARYOTYPES_DISAGREE, (GENOTYPE,)),
        "simons_data_sample_8": (se.NO_SGDP_ID, se.NOT_CHECKED, ()),
    }
    # A record entry for a sample whose tables name no genome, or two genomes neither of them its own, is stale.
    for entry, stale in (
        (("simons_data_sample_8", "S_X-1", "S_X-1"), rows),
        (("simons_data_sample_9", "S_X-1", "S_X-1"), [*rows, *two_genomes]),
    ):
        with pytest.raises(ValueError, match="measure it again"):
            run(tmp_path, f"stale_{entry[0]}", rows=stale, record=checks(entry))
    # A recorded match for a genome SGDP's file lacks links nothing: there is no donor line to write.
    lacking = run(
        tmp_path,
        "lacking",
        rows=[*rows, t2t(CHM13, "simons_data_sample_5", "S_Naxi-2", "XY")],
        record=checks(("simons_data_sample_5", "S_Naxi-2", "S_Naxi-2")),
    )
    assert lacking.outcomes["simons_data_sample_5"].genotype_check == se.GENOTYPE_MATCHES
    assert "simons_data_sample_5" not in lacking.linked
    # A blank row writes no link; the row naming the genome does.
    assert [g["target_key_value"] for g in written(tmp_path / "e", GRCH38)] == [
        "simons_data_sample_1",
        "simons_data_sample_3",
    ]


def test_a_file_of_a_sample_whose_sources_name_two_donors_reaches_none(tmp_path):
    root = tmp_path / "entity_evidence"
    lines_file(root, "D", [(COLLECTED_FROM, "HG00096", "HG00097")], SOURCE_EXTERNAL_GROUND_TRUTH, "ext")
    entry = sample_list([Identifier("coriell", "HG00096")])
    paths, skipped = select_entity_evidence(root, "anvil", CATALOG)
    rules = identifier_rules()
    evidence = gather(paths, root, load(tmp_path, TABLE), rules)
    files = Counter({("D", entry["list_id"]): 1})
    result = reconcile_entities(evidence, rules, [entry], skipped, files_by_list=files)
    assert result.report[DONOR_REACH] == {"D": {"files_with_samples": 1, "one_sample_without_donor": 1}}
