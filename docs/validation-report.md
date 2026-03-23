# Validation Report

Comparing meta-disco rule engine classifications against external ground truth.
Classification run: **2026-03-22 19:57:03**

| Source | Files Matched | Dimensions | Agree | Discrepancies |
|---|---:|---:|---:|---:|
| AnVIL (Azul metadata) | 11,231 | 2 | 983 | 4 |
| HPRC (sequencing catalog) | 5,852 | 4 | 11,137 | 0 |

---

## AnVIL (Azul metadata)

Validated against file-level metadata from the [AnVIL Data Explorer](https://explore.anvilproject.org/).

Classifying **758,658** files across **11** open-access datasets on the [AnVIL Explorer](https://explore.anvilproject.org/datasets?filter=%5B%7B%22categoryKey%22%3A%22accessible%22%2C%22value%22%3A%5B%22true%22%5D%7D%5D):

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

AnVIL currently populates the following metadata dimensions:

| Dimension | Files with dimension in AnVIL |
|---|---:|
| Data Modality | 6,755 |
| Data Type | 0 |
| Platform | 0 |
| Reference Assembly | 4,696 |
| Assay Type | 0 |

### Data Modality

- **6,755** files available from AnVIL with ground truth Data Modality
- **353** files classified by rule engine
- **6,402** files not classified by rule engine
- **349** inferred data modality values match AnVIL
- **4** discrepancies
- **98.9%** accuracy

Of the 6,755 files on AnVIL with ground truth data modality, we were able to infer a data modality for 353 files. 6,402 files remain unclassifiable by the rule engine.
Of the 353 inferred data modality values, 349 (98.9%) matched AnVIL. There were 4 discrepancies (1.1%) in data modality between meta-disco and AnVIL.

#### Discrepancies

| Count | Inferred | AnVIL | Example |
|---:|---|---|---|
| 2 | transcriptomic.single_cell | epigenomic.chromatin_accessibility | f92b42c30ff64edb444dfece410630d2 |
| 2 | genomic | epigenomic.chromatin_accessibility | 9a2afd8bc8423535f42201ba189540fb |

### Data Type

- **0** files available from AnVIL with ground truth Data Type
- **0** files classified by rule engine
- **0** files not classified by rule engine
- **0** inferred data type values match AnVIL
- **0** discrepancies
- **-** accuracy

AnVIL does not currently provide ground truth for data type.

### Platform

- **0** files available from AnVIL with ground truth Platform
- **0** files classified by rule engine
- **0** files not classified by rule engine
- **0** inferred platform values match AnVIL
- **0** discrepancies
- **-** accuracy

AnVIL does not currently provide ground truth for platform.

### Reference Assembly

- **4,696** files available from AnVIL with ground truth Reference Assembly
- **634** files classified by rule engine
- **4,062** files not classified by rule engine
- **634** inferred reference assembly values match AnVIL
- **0** discrepancies
- **100.0%** accuracy

Of the 4,696 files on AnVIL with ground truth reference assembly, we were able to infer a reference assembly for 634 files. 4,062 files remain unclassifiable by the rule engine.
Of the 634 inferred reference assembly values, 634 (100.0%) matched AnVIL. There were 0 discrepancies (0.0%) in reference assembly between meta-disco and AnVIL.

### Assay Type

- **0** files available from AnVIL with ground truth Assay Type
- **0** files classified by rule engine
- **0** files not classified by rule engine
- **0** inferred assay type values match AnVIL
- **0** discrepancies
- **-** accuracy

AnVIL does not currently provide ground truth for assay type.


---

## HPRC (sequencing catalog)

Validated against sequencing, alignment, and annotation catalogs from the [HPRC Data Explorer](https://data.humanpangenome.org/).

### Metadata Overview

HPRC currently populates the following metadata dimensions:

| Dimension | Files with dimension in HPRC |
|---|---:|
| Data Modality | 5,491 |
| Data Type | 0 |
| Platform | 5,852 |
| Reference Assembly | 4 |
| Assay Type | 5,852 |

Comparing against the following catalogs:

| Catalog | Records | Files Matched | Dimensions Validated |
|---|---:|---:|---|
| sequencing-data | 6,048 | 5,852 | Platform, Data Modality, Assay Type |
| alignments | 89 | 4 | Reference Assembly |
| annotations | 8,739 | 0 | Reference Assembly |
| assemblies | 560 | 188 | presence only |

### Data Modality

- **5,491** files available from HPRC with ground truth Data Modality
- **2,012** files classified by rule engine
- **3,479** files not classified by rule engine
- **2,012** inferred data modality values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 5,491 files on HPRC with ground truth data modality, we were able to infer a data modality for 2,012 files. 3,479 files remain unclassifiable by the rule engine.
Of the 2,012 inferred data modality values, 2,012 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in data modality between meta-disco and HPRC.

### Data Type

- **0** files available from HPRC with ground truth Data Type
- **0** files classified by rule engine
- **0** files not classified by rule engine
- **0** inferred data type values match HPRC
- **0** discrepancies
- **-** accuracy

HPRC does not currently provide ground truth for data type.

### Platform

- **5,852** files available from HPRC with ground truth Platform
- **5,852** files classified by rule engine
- **0** files not classified by rule engine
- **5,852** inferred platform values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 5,852 files on HPRC with ground truth platform, we were able to infer a platform for 5,852 files. 0 files remain unclassifiable by the rule engine.
Of the 5,852 inferred platform values, 5,852 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in platform between meta-disco and HPRC.

### Reference Assembly

- **4** files available from HPRC with ground truth Reference Assembly
- **4** files classified by rule engine
- **0** files not classified by rule engine
- **4** inferred reference assembly values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 4 files on HPRC with ground truth reference assembly, we were able to infer a reference assembly for 4 files. 0 files remain unclassifiable by the rule engine.
Of the 4 inferred reference assembly values, 4 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in reference assembly between meta-disco and HPRC.

### Assay Type

- **5,852** files available from HPRC with ground truth Assay Type
- **3,269** files classified by rule engine
- **2,583** files not classified by rule engine
- **3,269** inferred assay type values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 5,852 files on HPRC with ground truth assay type, we were able to infer a assay type for 3,269 files. 2,583 files remain unclassifiable by the rule engine.
Of the 3,269 inferred assay type values, 3,269 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in assay type between meta-disco and HPRC.


