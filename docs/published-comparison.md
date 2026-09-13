# Published values compared with inferred

Repository: `anvil/anvil15` · run `20260912_190744` · 708,088 files

**11,231 files have a published value**, across 11,463 file/dimension rows. For every other file the
repository publishes nothing for these dimensions.

Nothing here changes a classification: each file's inferred value is what the rule engine
resolved. A `keep` recommends that the published value should stand — it is not an adoption
of it, and no inferred value is altered by this report.

| recommendation | meaning |
| --- | --- |
| `add` | nothing published; meta-disco inferred a value |
| `keep` | a value is published; meta-disco inferred none |
| `review` | both have a value |
| `none` | neither has a value |

## Totals

| dimension | add | keep | review | none |
| --- | --- | --- | --- | --- |
| data_modality | 650,704 | 6,334 | 421 | 50,629 |
| reference_assembly | 525,907 | 4,062 | 634 | 177,485 |

## By dataset

Datasets for which the repository publishes nothing are omitted.

| dataset | dimension | add | keep | review | none |
| --- | --- | --- | --- | --- | --- |
| ANVIL_1000G_PRIMED_data_model | data_modality | 11,483 | 0 | 0 | 10 |
| ANVIL_1000G_PRIMED_data_model | reference_assembly | 11,493 | 0 | 0 | 0 |
| ANVIL_1000G_high_coverage_2019 | data_modality | 25,916 | 0 | 0 | 100 |
| ANVIL_1000G_high_coverage_2019 | reference_assembly | 25,916 | 0 | 0 | 100 |
| ANVIL_HPRC | data_modality | 9,957 | 0 | 0 | 13,228 |
| ANVIL_HPRC | reference_assembly | 13,712 | 0 | 0 | 9,473 |
| ANVIL_NIA_CARD_Coriell_Cell_Lines_Open | data_modality | 119 | 0 | 0 | 12,415 |
| ANVIL_NIA_CARD_Coriell_Cell_Lines_Open | reference_assembly | 12,494 | 0 | 0 | 40 |
| ANVIL_T2T | data_modality | 281,723 | 0 | 0 | 7,481 |
| ANVIL_T2T | reference_assembly | 239,700 | 0 | 0 | 49,504 |
| ANVIL_T2T_CHRY | data_modality | 309,411 | 0 | 0 | 568 |
| ANVIL_T2T_CHRY | reference_assembly | 201,662 | 0 | 0 | 108,317 |
| ANVIL_nhp_dGTEx_V1 | data_modality | 1,376 | 0 | 0 | 2,215 |
| AnVIL_ENCORE_293T | data_modality | 464 | 0 | 0 | 1,528 |
| AnVIL_ENCORE_293T | reference_assembly | 448 | 1,320 | 224 | 0 |
| AnVIL_ENCORE_RS293 | data_modality | 820 | 0 | 0 | 2,932 |
| AnVIL_ENCORE_RS293 | reference_assembly | 820 | 2,522 | 410 | 0 |
| AnVIL_HPRC_R2 | data_modality | 7,842 | 0 | 0 | 8,429 |
| AnVIL_HPRC_R2 | reference_assembly | 12,560 | 0 | 0 | 3,711 |
| AnVIL_IGVF_Mouse_R1 | data_modality | 0 | 6,334 | 421 | 31 |
| AnVIL_IGVF_Mouse_R1 | reference_assembly | 3,970 | 220 | 0 | 2,596 |
| AnVIL_MAGE | data_modality | 1,593 | 0 | 0 | 1,692 |
| AnVIL_MAGE | reference_assembly | 3,132 | 0 | 0 | 153 |

## Vocabulary coverage

**4 of 4 distinct published values have no term in the schema vocabulary**, carried by 11,463 file/dimension rows.
Each is a value mapping that is owed (#414); its row count is what that mapping is worth.

| dimension | published value | files | in vocabulary |
| --- | --- | --- | --- |
| data_modality | `single-nucleus RNA sequencing assay` | 6,745 | **no** |
| reference_assembly | `GRCh38 + Gencode40` | 4,476 | **no** |
| reference_assembly | `GRCm39` | 220 | **no** |
| data_modality | `single-nucleus ATAC-seq` | 22 | **no** |

## Rows needing review

Both sides have a value. Whether they agree cannot be decided until the value mappings exist
(#414) — no published value above is a term the schema knows, so every pair below is an
unmapped string rather than a disagreement about meaning.

| dimension | published | inferred | files |
| --- | --- | --- | --- |
| reference_assembly | `GRCh38 + Gencode40` | `GRCh38` | 634 |
| data_modality | `single-nucleus RNA sequencing assay` | `transcriptomic.single_cell` | 413 |
| data_modality | `single-nucleus ATAC-seq \|\| single-nucleus RNA sequencing assay` | `not_applicable` | 4 |
| data_modality | `single-nucleus ATAC-seq \|\| single-nucleus RNA sequencing assay` | `genomic` | 2 |
| data_modality | `single-nucleus ATAC-seq \|\| single-nucleus RNA sequencing assay` | `transcriptomic.single_cell` | 2 |

### Named individually (pairs of 20 files or fewer)

| file | dataset | dimension | we say |
| --- | --- | --- | --- |
| IGVFFI1426BOOW.tbi | AnVIL_IGVF_Mouse_R1 | data_modality | `not_applicable` |
| IGVFFI3781KRJF.bai | AnVIL_IGVF_Mouse_R1 | data_modality | `not_applicable` |
| IGVFFI4655VGST.bai | AnVIL_IGVF_Mouse_R1 | data_modality | `not_applicable` |
| IGVFFI9465DJGD.tbi | AnVIL_IGVF_Mouse_R1 | data_modality | `not_applicable` |
| IGVFFI1548FAFQ.bed.gz | AnVIL_IGVF_Mouse_R1 | data_modality | `genomic` |
| IGVFFI9441WCCN.bed.gz | AnVIL_IGVF_Mouse_R1 | data_modality | `genomic` |
| IGVFFI2080ESEF.h5ad | AnVIL_IGVF_Mouse_R1 | data_modality | `transcriptomic.single_cell` |
| IGVFFI8515HKDP.h5ad | AnVIL_IGVF_Mouse_R1 | data_modality | `transcriptomic.single_cell` |

---

115 record(s) were written by the run more than once and counted once here
(a tar archive is written to both `tar_` and `auxiliary_classifications.json`). Pre-existing, and
none of them declares anything, so no figure above depends on it.
