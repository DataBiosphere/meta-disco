# Published values compared with inferred

Repository: `anvil/anvil15` · run `20260920_001618` · 708,088 files

**11,231 files have a published value**, across 11,451 file/dimension rows. For every other file the
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
| data_modality | 635,650 | 6,339 | 416 | 65,683 |
| reference_assembly | 511,318 | 4,062 | 634 | 192,074 |

## By dataset

Datasets for which the repository publishes nothing are omitted.

| dataset | dimension | add | keep | review | none |
| --- | --- | --- | --- | --- | --- |
| AnVIL_ENCORE_293T | reference_assembly | 448 | 1,320 | 224 | 0 |
| AnVIL_ENCORE_RS293 | reference_assembly | 820 | 2,522 | 410 | 0 |
| AnVIL_IGVF_Mouse_R1 | data_modality | 0 | 6,339 | 416 | 31 |
| AnVIL_IGVF_Mouse_R1 | reference_assembly | 3,970 | 220 | 0 | 2,596 |

## Vocabulary coverage

**4 of 4 distinct published values have no term in the schema vocabulary**, carried by 11,463 published values.
Counted per value, not per row, so a cell publishing two values contributes two — which is the
right denominator for a mapping table. There are 11,451 file/dimension rows.
Each of the 4 is a value mapping that is owed (#414); its row count is what
that mapping is worth.

| dimension | published value | files | in vocabulary |
| --- | --- | --- | --- |
| data_modality | `single-nucleus RNA sequencing assay` | 6,745 | **no** |
| reference_assembly | `GRCh38 + Gencode40` | 4,476 | **no** |
| reference_assembly | `GRCm39` | 220 | **no** |
| data_modality | `single-nucleus ATAC-seq` | 22 | **no** |

## Rows needing review

Both sides have a value. Whether they agree cannot be decided until the value mappings exist
(#414), so each pair is named rather than judged.

None of the published values above is a term the schema knows, so every pair below is an
unmapped string rather than a disagreement about meaning.

| dimension | published | inferred | files |
| --- | --- | --- | --- |
| reference_assembly | `GRCh38 + Gencode40` | `GRCh38` | 634 |
| data_modality | `single-nucleus RNA sequencing assay` | `transcriptomic.single_cell` | 412 |
| data_modality | `single-nucleus ATAC-seq \|\| single-nucleus RNA sequencing assay` | `genomic` | 2 |
| data_modality | `single-nucleus ATAC-seq \|\| single-nucleus RNA sequencing assay` | `transcriptomic.single_cell` | 2 |

### The files behind the small pairs

Listed where a pair covers 20 files or fewer, which is where an individual
file is the fact rather than the count.

| file | dataset | dimension | inferred |
| --- | --- | --- | --- |
| IGVFFI1548FAFQ.bed.gz | AnVIL_IGVF_Mouse_R1 | data_modality | `genomic` |
| IGVFFI9441WCCN.bed.gz | AnVIL_IGVF_Mouse_R1 | data_modality | `genomic` |
| IGVFFI2080ESEF.h5ad | AnVIL_IGVF_Mouse_R1 | data_modality | `transcriptomic.single_cell` |
| IGVFFI8515HKDP.h5ad | AnVIL_IGVF_Mouse_R1 | data_modality | `transcriptomic.single_cell` |
