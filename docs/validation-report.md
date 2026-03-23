# Validation Report

Comparing meta-disco rule engine classifications against external ground truth.
Classification run: **2026-03-22 19:57:03**

| Source | Files Matched | Dimensions | Agree | Discrepancies |
|---|---:|---:|---:|---:|
| AnVIL (Azul metadata) | 11,231 | 2 | 983 | 4 |
| HPRC (sequencing catalog) | 6,040 | 4 | 4,327 | 2 |

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

## HPRC (sequencing catalog)

Validated against sequencing, alignment, and annotation catalogs from the [HPRC Data Explorer](https://data.humanpangenome.org/).

### Metadata Overview

HPRC's open-access datasets currently populate the following genomic metadata dimensions:

| Dimension | Files with dimension in HPRC |
|---|---:|
| Data Modality | 5,840 |
| Data Type | 0 |
| Platform | 6,040 |
| Reference Assembly | 13 |
| Assay Type | 6,040 |

### Data Modality Validation

- **5,840** files available from HPRC with ground truth Data Modality
- **0** files comparable (both source and rule engine have values)
- **5,840** files not classified by rule engine
- **0** inferred data modality values match HPRC
- **0** discrepancies
- **-** accuracy

Of the 5,840 files on HPRC with ground truth data modality, we inferred data modality values for 0 files. 5,840 files remain unclassifiable by the rule engine.

### Data Type Validation

- **0** files available from HPRC with ground truth Data Type
- **0** files comparable (both source and rule engine have values)
- **0** files not classified by rule engine
- **0** inferred data type values match HPRC
- **0** discrepancies
- **-** accuracy

HPRC does not currently provide ground truth for data type.

### Platform Validation

- **6,040** files available from HPRC with ground truth Platform
- **3,660** files comparable (both source and rule engine have values)
- **2,380** files not classified by rule engine
- **3,660** inferred platform values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 6,040 files on HPRC with ground truth platform, we inferred platform values for 3,660 files. 2,380 files remain unclassifiable by the rule engine.
Of the 3,660 inferred platform values, 3,660 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in platform between meta-disco and HPRC.

### Reference Assembly Validation

- **13** files available from HPRC with ground truth Reference Assembly
- **10** files comparable (both source and rule engine have values)
- **3** files not classified by rule engine
- **8** inferred reference assembly values match HPRC
- **2** discrepancies
- **80.0%** accuracy

Of the 13 files on HPRC with ground truth reference assembly, we inferred reference assembly values for 10 files. 3 files remain unclassifiable by the rule engine.
Of the 10 inferred reference assembly values, 8 (80.0%) matched HPRC. There were 2 discrepancies (20.0%) in reference assembly between meta-disco and HPRC.

#### Discrepancies

| Count | Inferred | HPRC | Example |
|---:|---|---|---|
| 2 | GRCh38 | CHM13 | hprc-v1.0-mc-chm13.grch38.vcf.gz |

### Assay Type Validation

- **6,040** files available from HPRC with ground truth Assay Type
- **659** files comparable (both source and rule engine have values)
- **5,381** files not classified by rule engine
- **659** inferred assay type values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 6,040 files on HPRC with ground truth assay type, we inferred assay type values for 659 files. 5,381 files remain unclassifiable by the rule engine.
Of the 659 inferred assay type values, 659 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in assay type between meta-disco and HPRC.


