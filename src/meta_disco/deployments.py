"""The AnVIL deployments meta-disco reads: which Azul service, which catalog, which
input root, and which TDR snapshot each dataset comes from (issue #500).

The repo used to have one slot for "the AnVIL corpus": a constant service URL, a
constant catalog, and ``data/anvil/`` as the one place the derived input could be
written. A pull from the dev deployment would have overwritten prod's, and the
catalog name (``anvil15`` for prod, ``anvil`` for dev) does not identify a
deployment. A :class:`Deployment` names all four together, and the input root is
the deployment's own — ``data/anvil/prod/`` and ``data/anvil/dev/`` — so one
deployment's input can never land in another's.

**A deployment declares its snapshots, and the declaration is checked, not
consulted.** ``tdr-direct`` has no manifest to read a snapshot from, so it reads the
ones declared here. ``azul-compact`` reads the snapshot the compact manifest names
on every row (``azul_manifest.dataset_source``) and refuses the download when that
disagrees with the declaration, naming both, rather than writing the manifest's and
carrying on. Decision of 2026-09-22 on #500: a snapshot change is the drift the
catalog pin in #335 exists to catch, and the fix is updating the line here.
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

The output root and the header cache are not here: a classification run is not yet
given a deployment (#480), and the content route and cache section are #479's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

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

    @property
    def input_file(self) -> Path:
        return self.input_root / INPUT_FILE_NAME

    @property
    def input_ndjson(self) -> Path:
        return self.input_root / INPUT_NDJSON_NAME

    def snapshot(self, dataset_title: str) -> Snapshot:
        """The declared snapshot of ``dataset_title``; ``ValueError`` if none is declared."""
        try:
            return self.snapshots[dataset_title]
        except KeyError:
            raise ValueError(
                f"deployment {self.name!r} declares no snapshot for dataset {dataset_title!r}; "
                f"it declares {sorted(self.snapshots)}"
            ) from None


def _snapshots(**by_title: tuple[str, str]) -> Mapping[str, Snapshot]:
    return MappingProxyType({title: Snapshot(project, name) for title, (project, name) in by_title.items()})


PROD = Deployment(
    name="prod",
    service="https://service.explore.anvilproject.org",
    catalog="anvil15",
    input_root=Path("data/anvil/prod"),
    snapshots=_snapshots(
        ANVIL_1000G_PRIMED_data_model=("datarepo-37bfbb88", "ANVIL_1000G_PRIMED_data_model_20240410_ANV6_202607071448"),
        ANVIL_1000G_high_coverage_2019=(
            "datarepo-6ec8e094",
            "ANVIL_1000G_high_coverage_2019_20230517_ANV6_202607071430",
        ),
        ANVIL_HPRC=("datarepo-6e7af669", "ANVIL_HPRC_20260121_ANV6_202607080129"),
        ANVIL_NIA_CARD_Coriell_Cell_Lines_Open=(
            "datarepo-169cfa42",
            "ANVIL_NIA_CARD_Coriell_Cell_Lines_Open_20230727_ANV6_202607061735",
        ),
        ANVIL_T2T=("datarepo-ad75fc28", "ANVIL_T2T_20230714_ANV6_202607080209"),
        ANVIL_T2T_CHRY=("datarepo-fb71bcfe", "ANVIL_T2T_CHRY_20240301_ANV6_202607080303"),
        ANVIL_nhp_dGTEx_V1=("datarepo-65b9f2b6", "ANVIL_nhp_dGTEx_V1_20260416_ANV6_202607080448"),
        AnVIL_ENCORE_293T=("datarepo-ce3811eb", "ANVIL_ENCORE_293T_20260708_ANV6_202607081759"),
        AnVIL_ENCORE_RS293=("datarepo-42923ab3", "ANVIL_ENCORE_RS293_20260708_ANV6_202607081737"),
        AnVIL_HPRC_R2=("datarepo-1aba48ac", "ANVIL_HPRC_R2_20260708_ANV6_202607080422"),
        AnVIL_IGVF_Mouse_R1=("datarepo-e5cd60e0", "ANVIL_IGVF_Mouse_R1_20260709_ANV6_202607091541"),
        AnVIL_MAGE=("datarepo-c1a69d87", "ANVIL_MAGE_20260708_ANV6_202607080402"),
    ),
)

DEV = Deployment(
    name="dev",
    service="https://service.anvil.gi.ucsc.edu",
    catalog="anvil",
    input_root=Path("data/anvil/dev"),
    snapshots=_snapshots(
        ANVIL_1000G_2019_Dev=("datarepo-dev-e53e74aa", "ANVIL_1000G_2019_Dev_20230609_ANV5_202306121732"),
    ),
)

DEPLOYMENTS: Mapping[str, Deployment] = MappingProxyType({d.name: d for d in (PROD, DEV)})

#: What every entry point reads when no deployment is named: today's behaviour.
DEFAULT_DEPLOYMENT = PROD.name


def deployment(name: str) -> Deployment:
    """The deployment called ``name``; ``ValueError`` naming the known ones otherwise."""
    try:
        return DEPLOYMENTS[name]
    except KeyError:
        raise ValueError(f"unknown deployment {name!r}; known deployments: {sorted(DEPLOYMENTS)}") from None
