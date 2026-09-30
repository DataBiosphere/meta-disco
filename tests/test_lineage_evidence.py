"""Lineage evidence files (#583): the writer and reader agree, a line declares nothing,
the rules the generated model drops are enforced both ways, a slot evidence file
refuses the lineage-only kind, and the two kinds are written under separate roots."""

import json

import pytest

from meta_disco.lineage_evidence import (
    DEFAULT_LINEAGE_EVIDENCE_ROOT,
    iter_lineage,
    read_lineage_envelope,
    write_lineage_file,
)
from meta_disco.models import SOURCE_PUBLISHED_VALUE, SOURCE_REPOSITORY_ACTIVITY
from meta_disco.schema.classification_model import (
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    ImporterSourceTypeEnum,
    JoinKeyEnum,
    LineageRow,
)
from meta_disco.source_evidence import DEFAULT_SOURCE_EVIDENCE_ROOT, iter_evidence, write_evidence_file


def envelope(source_type=SOURCE_REPOSITORY_ACTIVITY):
    return EvidenceFileEnvelope(
        source=EvidenceFileSource(repository="anvil", dataset="D", table="anvil_activity", url="https://azul.test"),
        source_type=ImporterSourceTypeEnum(source_type),
        source_version="anvil15",
        source_key="file_id",
        target=EvidenceTarget(system="anvil", dataset="D", version="anvil15"),
        target_key=JoinKeyEnum("file_id"),
        fetched_at="2026-09-03T21:45:47",
    )


def row(**members) -> LineageRow:
    base: dict = {
        "target_key_value": "child",
        "parent": "parent",
        "parent_key_type": "file_id",
        "child_column": "generated_file_id",
        "parent_column": "used_file_id",
    }
    return LineageRow.model_validate({**base, **members})


def lines_of(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_file_round_trips(tmp_path):
    path = tmp_path / "anvil_activity.ndjson"
    rows = [
        row(raw_activity="Indexing", raw_activity_column="activity_type", activity_id="a1"),
        row(parent=None, parent_key_type=None, parent_source_identifier="IGVFFI0000AAAA"),
        row(raw_activity="", raw_activity_column="activity_type"),
    ]
    assert write_lineage_file(path, envelope(), rows) == 3
    assert list(iter_lineage(path)) == rows
    assert read_lineage_envelope(path).source_type == SOURCE_REPOSITORY_ACTIVITY
    # Absent members are omitted, not written as nulls.
    assert "parent" not in lines_of(path)[2]


@pytest.mark.parametrize(
    ("members", "message"),
    [
        ({"parent": None, "parent_key_type": None}, "names no parent"),
        ({"parent_key_type": None}, "parent_key_type is present exactly when parent is"),
        ({"raw_activity": "Indexing"}, "raw_activity_column is present exactly when raw_activity is"),
    ],
)
def test_the_rules_the_model_drops_are_enforced_at_write(tmp_path, members, message):
    with pytest.raises(ValueError, match=message):
        write_lineage_file(tmp_path / "t.ndjson", envelope(), [row(**members)])
    assert not (tmp_path / "t.ndjson").exists()


def write_raw(path, *line_dicts):
    header = json.dumps({"evidence_file": envelope().model_dump(exclude_none=True)})
    path.write_text("\n".join([header, *(json.dumps(d) for d in line_dicts)]) + "\n")


@pytest.mark.parametrize("member", ["activity", "role", "value", "status", "rule_id", "tier", "parent_key"])
def test_a_line_carrying_an_answer_is_refused_by_name(tmp_path, member):
    path = tmp_path / "t.ndjson"
    write_raw(path, {**row().model_dump(exclude_none=True), member: "x"})
    with pytest.raises(ValueError, match=f"line 2: carries '{member}'"):
        list(iter_lineage(path))


def test_an_unknown_member_and_a_broken_rule_are_refused_at_read(tmp_path):
    path = tmp_path / "t.ndjson"
    write_raw(path, {**row().model_dump(exclude_none=True), "colour": "x"})
    with pytest.raises(ValueError, match="colour: unknown member"):
        list(iter_lineage(path))
    write_raw(path, {**row().model_dump(exclude_none=True), "raw_activity": "Indexing"})
    with pytest.raises(ValueError, match="line 2: raw_activity_column"):
        list(iter_lineage(path))


def test_a_lineage_file_declares_a_lineage_kind(tmp_path):
    with pytest.raises(ValueError, match="not a lineage source"):
        write_lineage_file(tmp_path / "t.ndjson", envelope(SOURCE_PUBLISHED_VALUE), [row()])


def test_a_slot_evidence_file_may_not_declare_a_lineage_only_kind(tmp_path):
    with pytest.raises(ValueError, match="written only as lineage evidence"):
        write_evidence_file(tmp_path / "t.ndjson", envelope(), [])
    path = tmp_path / "t.ndjson"
    write_raw(path)
    with pytest.raises(ValueError, match="written only as lineage evidence"):
        list(iter_evidence(path))


def test_the_lineage_root_is_outside_the_slot_root():
    """Every reader of the slot root reads each file there as slot lines; a lineage file must not be one of them."""
    assert not DEFAULT_LINEAGE_EVIDENCE_ROOT.is_relative_to(DEFAULT_SOURCE_EVIDENCE_ROOT)
    assert not DEFAULT_SOURCE_EVIDENCE_ROOT.is_relative_to(DEFAULT_LINEAGE_EVIDENCE_ROOT)
