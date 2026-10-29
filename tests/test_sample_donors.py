"""A sample's donors (#770): IGVF's submitter `sample.donors` and AnVIL's `anvil_biosample.donor_id`, a pooled
sample's several donors among them, imported as entity evidence and settled at reconcile."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from meta_disco import anvil_entities as ae
from meta_disco.entity_map import load_entity_map
from meta_disco.models import (
    COLLECTED_FROM,
    COLLECTED_FROM_REPOSITORY_ID,
    DONOR_REPOSITORY_ID,
    SOURCE_IDENTIFIER_RULE,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_METADATA,
)
from meta_disco.reconcile_entities import DONOR_REACH, UNREACHED, reconcile_entities
from meta_disco.sample_identity import Identifier, identifier_rules, sample_list
from meta_disco.schema.classification_model import SampleRecord
from tests.manifest_fixtures import CATALOG, SERVICE, write_dataset
from tests.test_entities import STAMP, TABLE, by_id, gathered, settled, write_entity_lines

IGVF = "AnVIL_IGVF_Mouse_R1"
# Three mice; S1 was pooled from the first two, S2 collected from the third.
A, B, C = "IGVFDO0000000A", "IGVFDO0000000B", "IGVFDO0000000C"
S1, S2 = "IGVFSM00000001", "IGVFSM00000002"

MAP = f"""
catalog: anvil15
datasets:
  {IGVF}:
    donor:
      identifier: donor_id
      phenotypic_sex: [phenotypic_sex]
    sample:
      identifier: sample_id
      collected_from: [donors]
published:
  donor:
    table: anvil_donor
    source_rows: source_datarepo_row_ids
    repository_id: donor_id
  sample:
    table: anvil_biosample
    source_rows: source_datarepo_row_ids
    repository_id: biosample_id
    collected_from_repository_id: [donor_id]
"""


def igvf(donors_of_s1=(A, B), anvil_donors_of_s1=("u-a", "u-b")) -> list[tuple[str, dict]]:
    """IGVF's manifest: the mice, the samples naming them, and AnVIL's records of both."""
    mice = [("donor", {"datarepo_row_id": f"d{m}", "donor_id": m, "phenotypic_sex": "female"}) for m in (A, B, C)]
    samples = [
        ("sample", {"datarepo_row_id": "s1", "sample_id": S1, "donors": list(donors_of_s1)}),
        ("sample", {"datarepo_row_id": "s2", "sample_id": S2, "donors": [C]}),
    ]
    anvil_donors = [
        ("anvil_donor", {"donor_id": f"u-{m[-1].lower()}", "source_datarepo_row_ids": [f"donor:d{m}"]})
        for m in (A, B, C)
    ]
    biosamples = [
        (
            "anvil_biosample",
            {"biosample_id": "b1", "source_datarepo_row_ids": ["sample:s1"], "donor_id": list(anvil_donors_of_s1)},
        ),
        ("anvil_biosample", {"biosample_id": "b2", "source_datarepo_row_ids": ["sample:s2"], "donor_id": ["u-c"]}),
    ]
    return [*mice, *samples, *anvil_donors, *biosamples]


def imported(tmp_path: Path, **manifest) -> Path:
    """IGVF's manifest imported through :data:`MAP`, checked first; the entity root."""
    map_path = tmp_path / "entity_map.yaml"
    map_path.write_text(MAP)
    entity_map = load_entity_map(map_path)
    write_dataset(tmp_path / "m", IGVF, igvf(**manifest))
    assert ae.check(entity_map, tmp_path / "m", CATALOG) == []
    root = tmp_path / "entity_evidence"
    ae.import_all(entity_map, tmp_path / "m", CATALOG, SERVICE, root, generation=STAMP)
    return root


def ids(identifiers: list[dict]) -> list[str]:
    return [i["id"] for i in identifiers]


def test_a_pooled_sample_is_collected_from_every_mouse_both_sources_name(tmp_path):
    root = imported(tmp_path)
    pooled, single = sample_list([Identifier("igvf", S1)]), sample_list([Identifier("igvf", S2)])
    files = Counter({(IGVF, pooled["list_id"]): 3, (IGVF, single["list_id"]): 1})
    rules = identifier_rules()
    result = reconcile_entities(gathered(root, tmp_path, TABLE), rules, [pooled, single], files_by_list=files)
    samples = by_id(result.samples)
    linked = samples[S1][COLLECTED_FROM]
    assert ids(linked["donors"]) == [A, B]
    # The submitter's list and AnVIL's donor ids, each cited by the rule recognising the mice's accessions.
    assert sorted((a["source_type"], a["rule_id"], a["source"]["table"]) for a in linked["named_by"]) == [
        (SOURCE_PUBLISHED_VALUE, "igvf_donor_accession", "anvil_biosample"),
        (SOURCE_REPOSITORY_METADATA, "igvf_donor_accession", "sample"),
    ]
    assert ids(samples[S2][COLLECTED_FROM]["donors"]) == [C]
    report = result.report["samples"]
    assert (report["collected_from"], report["pooled"], report["collected_from_conflicts"]) == ({"igvf": 2}, 1, [])
    # Every file reaches every mouse of its sample, and no mouse is left unreached.
    assert result.report[DONOR_REACH] == {IGVF: {"files_with_samples": 4, "every_sample_has_a_donor": 4}}
    assert "donor" not in result.report[UNREACHED].get(IGVF, {})
    for sample in result.samples:
        SampleRecord(**sample)


def test_sources_naming_different_sets_of_mice_give_a_pooled_sample_none(tmp_path):
    root = imported(tmp_path, anvil_donors_of_s1=("u-a",))
    result = settled(root, tmp_path)
    assert COLLECTED_FROM not in by_id(result.samples)[S1]
    (conflict,) = result.report["samples"]["collected_from_conflicts"]
    assert [(ids(n["donors"]), [a["source_type"] for a in n["named_by"]]) for n in conflict["named"]] == [
        ([A], [SOURCE_PUBLISHED_VALUE]),
        ([A, B], [SOURCE_REPOSITORY_METADATA]),
    ]
    # Each mouse a source names has a record, linked or in conflict.
    assert {A, B, C} <= set(by_id(result.donors))


def test_a_line_naming_a_mouse_no_rule_recognises_names_none_of_its_mice(tmp_path):
    root = imported(tmp_path, donors_of_s1=(A, "not-a-mouse"))
    result = settled(root, tmp_path)
    # AnVIL's donor ids still name both mice: one source, so the sample is linked by it alone.
    linked = by_id(result.samples)[S1][COLLECTED_FROM]
    assert (ids(linked["donors"]), [a["source_type"] for a in linked["named_by"]]) == (
        [A, B],
        [SOURCE_PUBLISHED_VALUE],
    )
    assert result.report["unrecognised_links"] == [
        {"dataset": IGVF, "table": "sample", "lines": 1, "examples": {"not-a-mouse": 1}}
    ]


def test_a_donor_id_tying_to_no_donor_record_names_none_of_the_lines_mice(tmp_path):
    root = imported(tmp_path, anvil_donors_of_s1=("u-a", "u-gone"))
    result = settled(root, tmp_path)
    linked = by_id(result.samples)[S1][COLLECTED_FROM]
    assert (ids(linked["donors"]), [a["source_type"] for a in linked["named_by"]]) == (
        [A, B],
        [SOURCE_REPOSITORY_METADATA],
    )
    assert result.report["unresolved_repository_links"] == [
        {"dataset": IGVF, "table": "anvil_biosample", "lines": 1, "examples": {"u-gone": 1}}
    ]


def test_a_donor_id_resolves_through_a_donor_record_another_dataset_ties_it_to(tmp_path):
    """The tie is the record's, whichever dataset's line made it, and is read after every file."""
    root = tmp_path / "entity_evidence"
    # D1's file is read first: the line naming u1 comes before the line tying it.
    write_entity_lines(root, "D1", COLLECTED_FROM_REPOSITORY_ID, [('["u1"]', "HG00096")])
    write_entity_lines(root, "D2", DONOR_REPOSITORY_ID, [("u1", "HG00096")])
    result = reconcile_entities(gathered(root, tmp_path), identifier_rules(), [])
    linked = by_id(result.samples)["HG00096"][COLLECTED_FROM]
    # The Coriell rule says so too: one donor, two sources.
    assert ids(linked["donors"]) == ["HG00096"]
    assert [a["source_type"] for a in linked["named_by"]] == [SOURCE_IDENTIFIER_RULE, SOURCE_PUBLISHED_VALUE]
    assert result.report["samples"]["pooled"] == 0


def test_a_donor_id_line_outside_a_published_table_is_refused(tmp_path):
    root = tmp_path / "entity_evidence"
    write_entity_lines(root, "D", COLLECTED_FROM_REPOSITORY_ID, [("u1", "HG00096")], SOURCE_REPOSITORY_METADATA)
    with pytest.raises(ValueError, match="only the repository's published table issues one"):
        gathered(root, tmp_path)


@pytest.mark.parametrize(
    ("table", "message"),
    [
        ("t: {identifier: x, phenotypic_sex: [y], collected_from: [z]}", "a sample's table reads no donor's slot"),
        ("t: {identifier: x, collected_from_repository_id: [z]}", "keys are"),
    ],
)
def test_the_loader_refuses_a_sample_table_reading_more_than_its_donors(tmp_path, table, message):
    path = tmp_path / "map.yaml"
    published = "published: {donor: {table: anvil_donor, source_rows: s, repository_id: i}}\n"
    path.write_text(f"catalog: anvil15\ndatasets:\n  D:\n    {table}\n{published}")
    with pytest.raises(ValueError, match=message):
        load_entity_map(path)


def test_the_check_reads_a_sample_tables_donor_column_as_naming_donors(tmp_path):
    """A table reading ``collected_from`` is keyed by samples, and its cells must name donors."""
    map_path = tmp_path / "entity_map.yaml"
    map_path.write_text(MAP)
    write_dataset(tmp_path / "m", IGVF, igvf(donors_of_s1=("x1", "x2")))
    assert ae.check(load_entity_map(map_path), tmp_path / "m", CATALOG) == [
        f"{IGVF}/sample: 2 of 3 values of donor column 'donors' are not a donor any identifier rule recognises "
        "(e.g. ['x1', 'x2'])"
    ]
