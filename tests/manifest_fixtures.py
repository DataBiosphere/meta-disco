"""Synthetic AnVIL verbatim manifests on disk, in the layout the importers read.

Shared by the slot importer's tests (`test_anvil_evidence`) and the lineage importer's
(`test_anvil_lineage`).
"""

import json
from pathlib import Path
from typing import Any

from meta_disco.azul_manifest import FORMAT_VERBATIM, load_sidecar, manifest_dir, manifest_path, save_sidecar
from meta_disco.deployments import PROD

CATALOG = "anvil15"
# The Azul service the fixture manifests stand for; written into every envelope.
SERVICE = "https://azul.test"
FETCHED = "2026-09-03T21:45:47.517283"
REAL_MANIFESTS = PROD.input_root / "manifest" / CATALOG


def drs(n: int) -> str:
    return f"drs://drs.anv0:v2_{n:08d}-0000-0000-0000-000000000000"


def write_dataset(root: Path, title: str, entities: list[tuple[str, dict]], fetched: str | None = FETCHED) -> None:
    """One dataset's verbatim manifest and its sidecar entry, in the layout the importer reads."""
    manifest_dir(root, CATALOG).mkdir(parents=True, exist_ok=True)
    manifest_path(root, CATALOG, title, FORMAT_VERBATIM).write_text(
        "".join(json.dumps({"value": value, "type": entity_type}) + "\n" for entity_type, value in entities)
    )
    sidecar = load_sidecar(root, CATALOG)
    entry: dict[str, Any] = {"file_count": sum(1 for t, _ in entities if t == "anvil_file")}
    if fetched is not None:
        entry[FORMAT_VERBATIM] = {"requested_at": fetched, "rows": entry["file_count"]}
    sidecar["datasets"][title] = entry
    save_sidecar(root, CATALOG, sidecar)


def anvil_file(n: int) -> tuple[str, dict]:
    return "anvil_file", {"file_id": f"f{n}", "file_name": f"f{n}.bam", "drs_uri": drs(n), "file_ref": drs(n)}
