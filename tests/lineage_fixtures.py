"""Lineage evidence fixtures (#583): envelopes and lines written into the generation layout, as the importer writes them.

Shared by the activity map's tests (#584) and reconcile's lineage pass (#577).
"""

from meta_disco.lineage_evidence import write_lineage_file
from meta_disco.models import SOURCE_REPOSITORY_ACTIVITY
from meta_disco.schema.classification_model import (
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    ImporterSourceTypeEnum,
    JoinKeyEnum,
    LineageRow,
)
from meta_disco.source_evidence import evidence_file_path, generation_dir

STAMP = "20260930T062532Z"


def envelope(table, source_type=SOURCE_REPOSITORY_ACTIVITY, dataset="D", key="file_id", version="anvil15"):
    return EvidenceFileEnvelope(
        source=EvidenceFileSource(repository="anvil", dataset=dataset, table=table, url="https://azul.test"),
        source_type=ImporterSourceTypeEnum(source_type),
        source_version=version,
        source_key=key,
        target=EvidenceTarget(system="anvil", dataset=dataset, version=version),
        target_key=JoinKeyEnum(key),
        fetched_at="2026-09-03T21:45:47",
    )


def line(child, parent, child_column="generated_file_id", parent_column="used_file_id", key="file_id", **more):
    members = {
        "target_key_value": child,
        "parent": parent,
        "parent_key_type": key,
        "child_column": child_column,
        "parent_column": parent_column,
        **more,
    }
    return LineageRow.model_validate(members)


def activity_line(child, parent, raw_activity, parent_column="used_file_id"):
    return line(
        child, parent, parent_column=parent_column, raw_activity=raw_activity, raw_activity_column="activity_type"
    )


def write_lineage(root, table, rows, dataset="D", **envelope_kw):
    """One lineage file in the generation layout, under the envelope's catalog version (``anvil15`` by default)."""
    directory = generation_dir(root, "anvil", envelope_kw.get("version", "anvil15"), dataset, STAMP)
    directory.mkdir(parents=True, exist_ok=True)
    write_lineage_file(evidence_file_path(directory, table), envelope(table, dataset=dataset, **envelope_kw), rows)
