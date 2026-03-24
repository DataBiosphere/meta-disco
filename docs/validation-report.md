# Validation Report

Comparing meta-disco rule engine classifications against external ground truth.
Classification run: **2026-03-24 00:41:06**

| Source | Files Matched | Dimensions | Agree | Discrepancies |
|---|---:|---:|---:|---:|
| AnVIL (Azul metadata) | 11,231 | 2 | 983 | 4 |
| HPRC | 5,872 | 4 | 11,928 | 5 |

---

## AnVIL (Azul metadata)

Validated against file-level metadata from the [AnVIL Data Explorer](https://explore.anvilproject.org/)'s open-access projects with **758,658** files across **11** datasets:

- ANVIL_T2T_CHRY (309,979 files)
- ANVIL_T2T (289,204 files)
- ANVIL_HPRC (67,830 files)
- ANVIL_1000G_high_coverage_2019 (26,016 files)
- ANVIL_GTEx_public_data (25,789 files)
- ANVIL_NIA_CARD_Coriell_Cell_Lines_Open (12,534 files)
- ANVIL_1000G_PRIMED_data_model (11,493 files)
- AnVIL_IGVF_Mouse_R1 (6,784 files)
- AnVIL_ENCORE_RS293 (3,752 files)
- AnVIL_MAGE (3,285 files)
- AnVIL_ENCORE_293T (1,992 files)

### Metadata Overview

AnVIL's open-access datasets currently populate the following genomic metadata dimensions:

| Dimension | Files with dimension in AnVIL |
|---|---:|
| Data Modality | 6,755 |
| Data Type | 0 |
| Platform | 0 |
| Reference Assembly | 4,696 |
| Assay Type | 0 |

### Data Modality Validation

- **6,755** files available from AnVIL with ground truth Data Modality
- **353** files comparable (both source and rule engine have values)
- **6,402** files not classified by rule engine
- **349** inferred data modality values match AnVIL
- **4** discrepancies
- **98.9%** accuracy

Of the 6,755 files on AnVIL with ground truth data modality, we inferred data modality values for 353 files. 6,402 files remain unclassifiable by the rule engine.
Of the 353 inferred data modality values, 349 (98.9%) matched AnVIL. There were 4 discrepancies (1.1%) in data modality between meta-disco and AnVIL.

#### Discrepancies

| Count | Inferred | AnVIL | Example |
|---:|---|---|---|
| 2 | transcriptomic.single_cell | epigenomic.chromatin_accessibility | f92b42c30ff64edb444dfece410630d2 |
| 2 | genomic | epigenomic.chromatin_accessibility | 9a2afd8bc8423535f42201ba189540fb |

### Data Type Validation

- **0** files available from AnVIL with ground truth Data Type
- **0** files comparable (both source and rule engine have values)
- **0** files not classified by rule engine
- **0** inferred data type values match AnVIL
- **0** discrepancies
- **-** accuracy

AnVIL does not currently provide ground truth for data type.

### Platform Validation

- **0** files available from AnVIL with ground truth Platform
- **0** files comparable (both source and rule engine have values)
- **0** files not classified by rule engine
- **0** inferred platform values match AnVIL
- **0** discrepancies
- **-** accuracy

AnVIL does not currently provide ground truth for platform.

### Reference Assembly Validation

- **4,696** files available from AnVIL with ground truth Reference Assembly
- **634** files comparable (both source and rule engine have values)
- **4,062** files not classified by rule engine
- **634** inferred reference assembly values match AnVIL
- **0** discrepancies
- **100.0%** accuracy

Of the 4,696 files on AnVIL with ground truth reference assembly, we inferred reference assembly values for 634 files. 4,062 files remain unclassifiable by the rule engine.
Of the 634 inferred reference assembly values, 634 (100.0%) matched AnVIL. There were 0 discrepancies (0.0%) in reference assembly between meta-disco and AnVIL.

### Assay Type Validation

- **0** files available from AnVIL with ground truth Assay Type
- **0** files comparable (both source and rule engine have values)
- **0** files not classified by rule engine
- **0** inferred assay type values match AnVIL
- **0** discrepancies
- **-** accuracy

AnVIL does not currently provide ground truth for assay type.


---

## HPRC

Validated against sequencing, alignment, and annotation catalogs from the [HPRC Data Explorer](https://data.humanpangenome.org/).

### Metadata Overview

HPRC's open-access datasets currently populate the following genomic metadata dimensions:

| Dimension | Files with dimension in HPRC |
|---|---:|
| Data Modality | 5,511 |
| Data Type | 0 |
| Platform | 5,872 |
| Reference Assembly | 2,578 |
| Assay Type | 5,872 |

### Data Modality Validation

- **5,511** files available from HPRC with ground truth Data Modality
- **2,032** files comparable (both source and rule engine have values)
- **3,479** files not classified by rule engine
- **2,032** inferred data modality values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 5,511 files on HPRC with ground truth data modality, we inferred data modality values for 2,032 files. 3,479 files remain unclassifiable by the rule engine.
Of the 2,032 inferred data modality values, 2,032 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in data modality between meta-disco and HPRC.

### Data Type Validation

- **0** files available from HPRC with ground truth Data Type
- **0** files comparable (both source and rule engine have values)
- **0** files not classified by rule engine
- **0** inferred data type values match HPRC
- **0** discrepancies
- **-** accuracy

HPRC does not currently provide ground truth for data type.

### Platform Validation

- **5,872** files available from HPRC with ground truth Platform
- **5,872** files comparable (both source and rule engine have values)
- **0** files not classified by rule engine
- **5,872** inferred platform values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 5,872 files on HPRC with ground truth platform, we inferred platform values for 5,872 files. 0 files remain unclassifiable by the rule engine.
Of the 5,872 inferred platform values, 5,872 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in platform between meta-disco and HPRC.

### Reference Assembly Validation

- **2,578** files available from HPRC with ground truth Reference Assembly
- **1,636** files comparable (both source and rule engine have values)
- **942** files not classified by rule engine
- **1,631** inferred reference assembly values match HPRC
- **5** discrepancies
- **99.7%** accuracy

Of the 2,578 files on HPRC with ground truth reference assembly, we inferred reference assembly values for 1,636 files. 942 files remain unclassifiable by the rule engine.
Of the 1,636 inferred reference assembly values, 1,631 (99.7%) matched HPRC. There were 5 discrepancies (0.3%) in reference assembly between meta-disco and HPRC.

#### Discrepancies

| Count | Inferred | HPRC | Example |
|---:|---|---|---|
| 3 | GRCh38 | CHM13 | hprc-v1.0-mc-grch38-minaf.0.1.dist.old |
| 2 | CHM13 | GRCh38 | hprc-v1.0-mc-chm13-minaf.0.1.min.old |

### Assay Type Validation

- **5,872** files available from HPRC with ground truth Assay Type
- **2,393** files comparable (both source and rule engine have values)
- **3,479** files not classified by rule engine
- **2,393** inferred assay type values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 5,872 files on HPRC with ground truth assay type, we inferred assay type values for 2,393 files. 3,479 files remain unclassifiable by the rule engine.
Of the 2,393 inferred assay type values, 2,393 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in assay type between meta-disco and HPRC.


