"""The AnVIL deployments meta-disco reads: which Azul service, which catalog, which
input root, and which TDR snapshot each dataset comes from (issue #500).

The repo used to have one slot for "the AnVIL corpus": a constant service URL, a
constant catalog, and ``data/anvil/`` as the one place the derived input could be
written. A pull from the dev deployment would have overwritten prod's, and the
catalog name (``anvil15`` for prod, ``anvil`` for dev) does not identify a
deployment. A :class:`Deployment` names all four together, and the input root is
the deployment's own — ``data/anvil/prod/`` and ``data/anvil/dev/`` — so one
deployment's input can never land in another's.

**A deployment declares its snapshots.** How the declaration is used depends on the
input source. ``tdr-direct`` has no manifest to read a snapshot from, so it reads
the ones declared here. ``azul-verbatim``'s manifest carries no snapshot column, so
its envelope records the declared ones. On ``azul-compact`` the declaration is
checked, not consulted: the compact manifest names the snapshot on every row
(``azul_manifest.dataset_source``), and the download refuses a manifest that names
another than the declared one, or none, naming both, rather than writing the
manifest's and carrying on. Decision of 2026-09-22 on #500: a snapshot change is the drift the
catalog pin in #335 exists to catch, and the fix is updating the line here.

**A deployment declares each dataset's id**, and the downloader asks Azul for a
dataset's manifests by it (``azul_manifest.manifest_filters``, #717): the
``dataset_id`` is the stable name for a dataset, which a title is not. (On 2026-10-21 two
title filters returned compact manifests Azul had stored days earlier, missing files; by
id, both came back complete. The downloader's row-count check is what refuses a short
manifest, by either filter.) The id is
checked against what Azul returns: a record whose dataset is not the declared title
and id refuses the download (``download_anvil_manifest``).

Consequently a catalog dataset this file does not declare is not part of the
deployment: the downloader reports it and skips it, which is how dev's
``ANVIL_CMG_Sample_1`` (fifty copies of one placeholder) stays out.

Where the values came from:

- **prod**: the twelve snapshots are transcribed from the envelope of the input
  derived 2026-09-17 from the anvil15 compact manifests, whose ``source_spec`` column
  Azul fills from TDR.
- **dev**: read 2026-09-22 from dev's Azul service, unauthenticated —
  ``GET /repository/sources?catalog=anvil`` lists two accessible sources, and every
  ``/index/files`` hit for ``ANVIL_1000G_2019_Dev`` carries the same one.
- **dataset ids**: prod's from the ``datasets.dataset_id`` column of the anvil15
  compact manifests fetched 2026-10-21, one id per manifest; dev's from the records of
  dev's input derived 2026-09-22.

The output root and the header cache are not here: a classification run is not yet
given a deployment (#480), and the content route and cache section are #479's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import TypedDict

from .tdr import Snapshot

#: The derived input's file names under a deployment's root, in both shapes a run reads.
INPUT_FILE_NAME = "anvil_files_metadata.json"
INPUT_NDJSON_NAME = "anvil_files_metadata.ndjson"


@dataclass(frozen=True)
class Deployment:
    """One AnVIL deployment: where its Azul service is, which catalog generation it
    serves, where its derived input lives, and which TDR snapshot each of its
    datasets is materialised from."""

    name: str
    #: The Azul service, e.g. ``https://service.explore.anvilproject.org``. The manifest
    #: and files-index URLs are built from it (:mod:`meta_disco.azul_manifest`).
    service: str
    #: The catalog generation this deployment's Azul serves.
    catalog: str
    #: The root the derived input and the manifests are written under.
    input_root: Path
    #: Dataset title -> the TDR snapshot it comes from. Exactly the datasets the
    #: deployment reads: an undeclared one is skipped, a declared one is required.
    snapshots: Mapping[str, Snapshot]
    #: Dataset title -> its ``dataset_id``, which the downloader filters manifests by (#717).
    #: Empty for a deployment that downloads nothing (a test's, or one read in place).
    dataset_ids: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def dataset_id(self, title: str) -> str:
        """The declared ``dataset_id`` of ``title``.

        Raises:
            ValueError: the deployment declares no id for ``title``.
        """
        try:
            return self.dataset_ids[title]
        except KeyError:
            raise ValueError(f"the {self.name} deployment declares no dataset_id for {title!r}") from None

    @property
    def input_file(self) -> Path:
        return self.input_root / INPUT_FILE_NAME

    @property
    def input_ndjson(self) -> Path:
        return self.input_root / INPUT_NDJSON_NAME


class _Datasets(TypedDict):
    snapshots: Mapping[str, Snapshot]
    dataset_ids: Mapping[str, str]


def _datasets(**by_title: tuple[str, str, str]) -> _Datasets:
    """A deployment's ``snapshots`` and ``dataset_ids``, from one ``(project, snapshot, dataset_id)``
    per title, so a dataset is declared in one place."""
    return {
        "snapshots": MappingProxyType({t: Snapshot(project, name) for t, (project, name, _) in by_title.items()}),
        "dataset_ids": MappingProxyType({t: dataset_id for t, (_, _, dataset_id) in by_title.items()}),
    }


PROD = Deployment(
    name="prod",
    service="https://service.explore.anvilproject.org",
    catalog="anvil15",
    input_root=Path("data/anvil/prod"),
    **_datasets(
        ANVIL_1000G_PRIMED_data_model=(
            "datarepo-37bfbb88",
            "ANVIL_1000G_PRIMED_data_model_20240410_ANV6_202607071448",
            "38442466-8bcf-17ed-393e-058a0ed8d25d",
        ),
        ANVIL_1000G_high_coverage_2019=(
            "datarepo-6ec8e094",
            "ANVIL_1000G_high_coverage_2019_20230517_ANV6_202607071430",
            "8a756d17-c54c-3b33-312b-c767552a8516",
        ),
        ANVIL_HPRC=(
            "datarepo-6e7af669",
            "ANVIL_HPRC_20260121_ANV6_202607080129",
            "59960255-cca9-fcd3-d8ca-eb88f2c72f00",
        ),
        ANVIL_NIA_CARD_Coriell_Cell_Lines_Open=(
            "datarepo-169cfa42",
            "ANVIL_NIA_CARD_Coriell_Cell_Lines_Open_20230727_ANV6_202607061735",
            "d72a9163-0cb1-4c90-b5a9-0d4b64d0cd65",
        ),
        ANVIL_T2T=(
            "datarepo-ad75fc28",
            "ANVIL_T2T_20230714_ANV6_202607080209",
            "1c39e90e-463c-9853-793e-7e4c8f081815",
        ),
        ANVIL_T2T_CHRY=(
            "datarepo-fb71bcfe",
            "ANVIL_T2T_CHRY_20240301_ANV6_202607080303",
            "767a9143-8aa1-c7d0-10cb-c8d0140b8f54",
        ),
        ANVIL_nhp_dGTEx_V1=(
            "datarepo-65b9f2b6",
            "ANVIL_nhp_dGTEx_V1_20260416_ANV6_202607080448",
            "93dd6a5a-a977-4723-d0b3-a108ace204ba",
        ),
        AnVIL_ENCORE_293T=(
            "datarepo-ce3811eb",
            "ANVIL_ENCORE_293T_20260708_ANV6_202607081759",
            "a19e4cba-3171-e413-4c1b-73ad7328d236",
        ),
        AnVIL_ENCORE_RS293=(
            "datarepo-42923ab3",
            "ANVIL_ENCORE_RS293_20260708_ANV6_202607081737",
            "1d9283db-632e-8cc7-07e1-f485727dbf23",
        ),
        AnVIL_HPRC_R2=(
            "datarepo-1aba48ac",
            "ANVIL_HPRC_R2_20260708_ANV6_202607080422",
            "f9409a41-e58e-6735-7966-ca1cc54005ae",
        ),
        AnVIL_IGVF_Mouse_R1=(
            "datarepo-e5cd60e0",
            "ANVIL_IGVF_Mouse_R1_20260709_ANV6_202607091541",
            "3201ae89-576f-04ff-14c5-30fdb1a2ac64",
        ),
        AnVIL_MAGE=(
            "datarepo-c1a69d87",
            "ANVIL_MAGE_20260708_ANV6_202607080402",
            "5cba0a49-6b39-60c2-d641-f9f66b195ad1",
        ),
    ),
)

DEV = Deployment(
    name="dev",
    service="https://service.anvil.gi.ucsc.edu",
    catalog="anvil",
    input_root=Path("data/anvil/dev"),
    **_datasets(
        ANVIL_1000G_2019_Dev=(
            "datarepo-dev-e53e74aa",
            "ANVIL_1000G_2019_Dev_20230609_ANV5_202306121732",
            "385290c3-dff5-fb6d-2501-fa0ba3ad1c35",
        ),
    ),
)

DEPLOYMENTS: Mapping[str, Deployment] = MappingProxyType({d.name: d for d in (PROD, DEV)})

#: What every entry point reads when no deployment is named: today's behaviour.
DEFAULT_DEPLOYMENT = PROD.name
