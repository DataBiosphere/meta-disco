# The incumbent, beside ours

Run: `output/anvil/20260912_152414` · 708,088 files · incumbent: `anvil/anvil15`

What AnVIL publishes today for `data_modality` and `reference_assembly`, compared with what this
run concluded, per file. Nothing here changes a classification: every file's value is what
inference resolved, and `take_azul` is a recommendation that the incumbent should stand on a
file we call `not_classified` — not an adoption of it.

**11,231 files carry a declaration**; the rest are the incumbent's silence.

| recommendation | meaning |
| --- | --- |
| `add` | the incumbent is silent, we classified — our value is the only one |
| `take_azul` | the incumbent declares, we are `not_classified` — it should stand |
| `compare` | both spoke; whether they agree needs the translation table (#414) |
| `none` | neither spoke — the residual backlog |

## Corpus totals

| dimension | take_azul | compare | add | none |
| --- | --- | --- | --- | --- |
| data_modality | 6,334 | 421 | 650,704 | 50,629 |
| reference_assembly | 4,062 | 634 | 525,907 | 177,485 |

## By dataset

Datasets the incumbent is silent across entirely are omitted.

| dataset | dimension | take_azul | compare | add | none |
| --- | --- | --- | --- | --- | --- |
| AnVIL_ENCORE_293T | reference_assembly | 1,320 | 224 | 448 | 0 |
| AnVIL_ENCORE_RS293 | reference_assembly | 2,522 | 410 | 820 | 0 |
| AnVIL_IGVF_Mouse_R1 | data_modality | 6,334 | 421 | 0 | 31 |
| AnVIL_IGVF_Mouse_R1 | reference_assembly | 220 | 0 | 3,970 | 2,596 |

## Can we even say it?

**4 of 4 distinct incumbent values are terms our vocabulary does not have**, carried by 11,463 file declarations.
Every `no` below is a translation row that is owed (#414), and its file count is what it is worth.
Because none of the incumbent's values is a term we know, not one `compare` pair below is a
term-level disagreement — every one of them is an untranslated string.

| dimension | incumbent value | files | a term in our vocabulary |
| --- | --- | --- | --- |
| data_modality | `single-nucleus RNA sequencing assay` | 6,745 | **no** |
| reference_assembly | `GRCh38 + Gencode40` | 4,476 | **no** |
| reference_assembly | `GRCm39` | 220 | **no** |
| data_modality | `single-nucleus ATAC-seq` | 22 | **no** |

## Where both spoke

| dimension | incumbent says | we say | files |
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
