# Corpus comparison

Generated 2026-09-04 01:26 by `scripts/compare_corpus.py` (issue #335).

Runs compared: `output/anvil/20260802_170826` → `output/anvil/20260904_010319`.

## Input snapshots

| | file | catalog | pulled | files |
|---|---|---|---|---:|
| old | `data/anvil/archive/anvil14_20260729/anvil_files_metadata.json` | (unrecorded) | 2026-07-29T23:37:42.260488 | 733,877 |
| new | `data/anvil/anvil_files_metadata.json` | anvil15 | 2026-09-04T00:59:04.915407 | 708,088 |

### Parity by md5, per dataset

A file is matched on `(dataset, file name, md5)`. `md5 changed` counts files
that kept their name within a dataset but changed content.

| dataset | old | new | unchanged | md5 changed | removed | added |
|---|---:|---:|---:|---:|---:|---:|
| ANVIL_GTEx_public_data | 25,789 | 0 | 0 | 0 | 25,789 | 0 |
| ANVIL_1000G_PRIMED_data_model | 11,493 | 11,493 | 11,493 | 0 | 0 | 0 |
| ANVIL_1000G_high_coverage_2019 | 26,016 | 26,016 | 26,016 | 0 | 0 | 0 |
| ANVIL_HPRC | 23,185 | 23,185 | 23,185 | 0 | 0 | 0 |
| ANVIL_NIA_CARD_Coriell_Cell_Lines_Open | 12,534 | 12,534 | 12,534 | 0 | 0 | 0 |
| ANVIL_T2T | 289,204 | 289,204 | 289,204 | 0 | 0 | 0 |
| ANVIL_T2T_CHRY | 309,979 | 309,979 | 309,979 | 0 | 0 | 0 |
| ANVIL_nhp_dGTEx_V1 | 3,591 | 3,591 | 3,591 | 0 | 0 | 0 |
| AnVIL_ENCORE_293T | 1,992 | 1,992 | 1,992 | 0 | 0 | 0 |
| AnVIL_ENCORE_RS293 | 3,752 | 3,752 | 3,752 | 0 | 0 | 0 |
| AnVIL_HPRC_R2 | 16,271 | 16,271 | 16,271 | 0 | 0 | 0 |
| AnVIL_IGVF_Mouse_R1 | 6,786 | 6,786 | 6,786 | 0 | 0 | 0 |
| AnVIL_MAGE | 3,285 | 3,285 | 3,285 | 0 | 0 | 0 |
| **total** | **733,877** | **708,088** | **708,088** | **0** | **25,789** | **0** |

## Coverage by dimension

Files classified out of 733,992 (old) and 708,203 (new).
`classified` counts a real value; `n/a` counts `not_applicable`, which the
coverage report folds into its own Classified row.

| dimension | old | new | old % | new % | delta | old n/a | new n/a |
|---|---:|---:|---:|---:|---:|---:|---:|
| data_modality | 617,821 | 592,104 | 84.2% | 83.6% | -25,717 | 59,021 | 59,021 |
| data_type | 652,265 | 626,548 | 88.9% | 88.5% | -25,717 | 55,947 | 55,947 |
| platform | 57,973 | 57,973 | 7.9% | 8.2% | +0 | 100,137 | 74,429 |
| reference_assembly | 463,794 | 463,793 | 63.2% | 65.5% | -1 | 88,571 | 62,863 |
| assay_type | 54,349 | 28,635 | 7.4% | 4.0% | -25,714 | 74,429 | 74,429 |

### Where the delta comes from

`corpus loss` and `corpus gain` count classified files whose identity is
absent from the other run — catalog membership, not classifier behaviour.
`label change` is the net classified count over files present in **both**
runs, which is the only classifier-behaviour column.

| dimension | delta | corpus loss | corpus gain | label change |
|---|---:|---:|---:|---:|
| data_modality | -25,717 | -25,717 | +0 | +0 |
| data_type | -25,717 | -25,717 | +0 | +0 |
| platform | +0 | -0 | +0 | +0 |
| reference_assembly | -1 | -1 | +0 | +0 |
| assay_type | -25,714 | -25,714 | +0 | +0 |

## Label changes on files present in both runs

### reference_assembly

| old label | new label | files |
|---|---|---:|
| `CHM13` | `GRCh38` | 3,685 |
| `GRCh38` | `CHM13` | 3,681 |

## Per-dataset classified counts

| dataset | dimension | old | new | delta |
|---|---|---:|---:|---:|
| ANVIL_1000G_PRIMED_data_model | data_modality | 8,631 | 8,631 | +0 |
| ANVIL_1000G_PRIMED_data_model | data_type | 8,631 | 8,631 | +0 |
| ANVIL_1000G_PRIMED_data_model | platform | 0 | 0 | +0 |
| ANVIL_1000G_PRIMED_data_model | reference_assembly | 8,641 | 8,641 | +0 |
| ANVIL_1000G_PRIMED_data_model | assay_type | 0 | 0 | +0 |
| ANVIL_1000G_high_coverage_2019 | data_modality | 12,908 | 12,908 | +0 |
| ANVIL_1000G_high_coverage_2019 | data_type | 12,908 | 12,908 | +0 |
| ANVIL_1000G_high_coverage_2019 | platform | 6,404 | 6,404 | +0 |
| ANVIL_1000G_high_coverage_2019 | reference_assembly | 12,908 | 12,908 | +0 |
| ANVIL_1000G_high_coverage_2019 | assay_type | 6,404 | 6,404 | +0 |
| ANVIL_GTEx_public_data | data_modality | 25,717 | 0 | -25,717 |
| ANVIL_GTEx_public_data | data_type | 25,717 | 0 | -25,717 |
| ANVIL_GTEx_public_data | platform | 0 | 0 | +0 |
| ANVIL_GTEx_public_data | reference_assembly | 1 | 0 | -1 |
| ANVIL_GTEx_public_data | assay_type | 25,714 | 0 | -25,714 |
| ANVIL_HPRC | data_modality | 5,294 | 5,294 | +0 |
| ANVIL_HPRC | data_type | 12,178 | 12,178 | +0 |
| ANVIL_HPRC | platform | 5,210 | 5,210 | +0 |
| ANVIL_HPRC | reference_assembly | 2,121 | 2,121 | +0 |
| ANVIL_HPRC | assay_type | 1,057 | 1,057 | +0 |
| ANVIL_NIA_CARD_Coriell_Cell_Lines_Open | data_modality | 119 | 119 | +0 |
| ANVIL_NIA_CARD_Coriell_Cell_Lines_Open | data_type | 12,521 | 12,521 | +0 |
| ANVIL_NIA_CARD_Coriell_Cell_Lines_Open | platform | 12,403 | 12,403 | +0 |
| ANVIL_NIA_CARD_Coriell_Cell_Lines_Open | reference_assembly | 64 | 64 | +0 |
| ANVIL_NIA_CARD_Coriell_Cell_Lines_Open | assay_type | 31 | 31 | +0 |
| ANVIL_T2T | data_modality | 264,104 | 264,104 | +0 |
| ANVIL_T2T | data_type | 270,384 | 270,384 | +0 |
| ANVIL_T2T | platform | 12,878 | 12,878 | +0 |
| ANVIL_T2T | reference_assembly | 233,295 | 233,295 | +0 |
| ANVIL_T2T | assay_type | 6,753 | 6,753 | +0 |
| ANVIL_T2T_CHRY | data_modality | 289,468 | 289,468 | +0 |
| ANVIL_T2T_CHRY | data_type | 290,026 | 290,026 | +0 |
| ANVIL_T2T_CHRY | platform | 8,078 | 8,078 | +0 |
| ANVIL_T2T_CHRY | reference_assembly | 201,104 | 201,104 | +0 |
| ANVIL_T2T_CHRY | assay_type | 7,520 | 7,520 | +0 |
| ANVIL_nhp_dGTEx_V1 | data_modality | 1,376 | 1,376 | +0 |
| ANVIL_nhp_dGTEx_V1 | data_type | 1,376 | 1,376 | +0 |
| ANVIL_nhp_dGTEx_V1 | platform | 136 | 136 | +0 |
| ANVIL_nhp_dGTEx_V1 | reference_assembly | 0 | 0 | +0 |
| ANVIL_nhp_dGTEx_V1 | assay_type | 1,372 | 1,372 | +0 |
| AnVIL_ENCORE_293T | data_modality | 464 | 464 | +0 |
| AnVIL_ENCORE_293T | data_type | 912 | 912 | +0 |
| AnVIL_ENCORE_293T | platform | 448 | 448 | +0 |
| AnVIL_ENCORE_293T | reference_assembly | 224 | 224 | +0 |
| AnVIL_ENCORE_293T | assay_type | 464 | 464 | +0 |
| AnVIL_ENCORE_RS293 | data_modality | 820 | 820 | +0 |
| AnVIL_ENCORE_RS293 | data_type | 1,640 | 1,640 | +0 |
| AnVIL_ENCORE_RS293 | platform | 820 | 820 | +0 |
| AnVIL_ENCORE_RS293 | reference_assembly | 410 | 410 | +0 |
| AnVIL_ENCORE_RS293 | assay_type | 820 | 820 | +0 |
| AnVIL_HPRC_R2 | data_modality | 6,910 | 6,910 | +0 |
| AnVIL_HPRC_R2 | data_type | 8,435 | 8,435 | +0 |
| AnVIL_HPRC_R2 | platform | 6,068 | 6,068 | +0 |
| AnVIL_HPRC_R2 | reference_assembly | 3,452 | 3,452 | +0 |
| AnVIL_HPRC_R2 | assay_type | 2,276 | 2,276 | +0 |
| AnVIL_IGVF_Mouse_R1 | data_modality | 417 | 417 | +0 |
| AnVIL_IGVF_Mouse_R1 | data_type | 4,386 | 4,386 | +0 |
| AnVIL_IGVF_Mouse_R1 | platform | 3,970 | 3,970 | +0 |
| AnVIL_IGVF_Mouse_R1 | reference_assembly | 0 | 0 | +0 |
| AnVIL_IGVF_Mouse_R1 | assay_type | 351 | 351 | +0 |
| AnVIL_MAGE | data_modality | 1,593 | 1,593 | +0 |
| AnVIL_MAGE | data_type | 3,151 | 3,151 | +0 |
| AnVIL_MAGE | platform | 1,558 | 1,558 | +0 |
| AnVIL_MAGE | reference_assembly | 1,574 | 1,574 | +0 |
| AnVIL_MAGE | assay_type | 1,587 | 1,587 | +0 |

