"""Lineage evidence fixtures (#583): envelopes and lines written into the generation layout, as the importer writes them.

Shared by the activity map's tests (#584), reconcile's lineage pass (#577) and inheritance (#571),
which also share :func:`reconcile_fixture` and :func:`lineage_roots` (the ``roots`` fixture, in ``conftest``).
"""

from pathlib import Path

from meta_disco.activity_map import load_activity_map
from meta_disco.lineage_evidence import write_lineage_file
from meta_disco.models import SOURCE_REPOSITORY_ACTIVITY, SOURCE_REPOSITORY_METADATA
from meta_disco.output_utils import iter_reconciled_records
from meta_disco.reconcile import reconcile_run
from meta_disco.schema.classification_model import (
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    ImporterSourceTypeEnum,
    JoinKeyEnum,
    LineageRow,
)
from meta_disco.source_evidence import evidence_file_path, generation_dir
from tests.metadata_fixtures import write_metadata
from tests.run_fixtures import write_run

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


# --- reconciling a fixture run with lineage (shared by the reconcile lineage and inheritance tests) ---


def drs(n: int) -> str:
    """The DRS URI of fixture record ``n``."""
    return f"drs://drs.anv0:v2_{n}"


def sample_line(child: int, parent: int, child_column: str, parent_column: str):
    """A submitter row's line: record ``child`` made from record ``parent``, keyed by DRS URI."""
    return line(drs(child), drs(parent), child_column, parent_column, "drs_uri")


def sample_lines(lineage, *lines, dataset="D") -> None:
    """Write ``lines`` as one ``sample`` table's lineage file under ``lineage``."""
    write_lineage(
        lineage, "sample", list(lines), dataset=dataset, source_type=SOURCE_REPOSITORY_METADATA, key="drs_uri"
    )


def lineage_roots(tmp_path: Path) -> tuple[Path, Path]:
    """The slot evidence root and the lineage root beside it, as reconcile finds them by default."""
    evidence = tmp_path / "data" / "source_evidence"
    evidence.mkdir(parents=True)
    return evidence, tmp_path / "data" / "lineage_evidence"


def reconcile_fixture(tmp_path: Path, rows, evidence, activity_map: str) -> tuple[dict[str, dict], dict]:
    """Reconcile a run of ``rows`` (or the run already written, for None) with ``activity_map``.

    Returns the reconciled records by file name, and the report.
    """
    run_dir = tmp_path / "output" / "20261001_000000"
    if rows is not None:
        write_run(run_dir, rows)
    table = tmp_path / "activity_map.yaml"
    table.write_text(activity_map)
    metadata = write_metadata(tmp_path / "input.json", [], repository="anvil", catalog="anvil15")
    report = reconcile_run(run_dir, metadata, evidence, activity_table=load_activity_map(table))
    return {r["file_name"]: r for r in iter_reconciled_records(run_dir)}, report
