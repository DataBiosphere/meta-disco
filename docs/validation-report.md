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

The source currently populates the following metadata dimensions:

| Dimension | Files with metadata |
|---|---:|
| Data Modality | 6,755 |
| Data Type | 0 |
| Platform | 0 |
| Reference Assembly | 4,696 |
| Assay Type | 0 |

### Data Modality

- **6,755** values available from source
- **353** also classified by rule engine
- **6,402** not classified by rule engine (no rule applies)
- **349** agreed
- **4** discrepancies
- **98.9%** accuracy

#### Discrepancies

| Count | Inferred | AnVIL | Example |
|---:|---|---|---|
| 2 | transcriptomic.single_cell | epigenomic.chromatin_accessibility | f92b42c30ff64edb444dfece410630d2 |
| 2 | genomic | epigenomic.chromatin_accessibility | 9a2afd8bc8423535f42201ba189540fb |

### Data Type

- **0** values available from source
- **0** also classified by rule engine
- **0** not classified by rule engine (no rule applies)
- **0** agreed
- **0** discrepancies
- **-** accuracy

### Platform

- **0** values available from source
- **0** also classified by rule engine
- **0** not classified by rule engine (no rule applies)
- **0** agreed
- **0** discrepancies
- **-** accuracy

### Reference Assembly

- **4,696** values available from source
- **634** also classified by rule engine
- **4,062** not classified by rule engine (no rule applies)
- **634** agreed
- **0** discrepancies
- **100.0%** accuracy

### Assay Type

- **0** values available from source
- **0** also classified by rule engine
- **0** not classified by rule engine (no rule applies)
- **0** agreed
- **0** discrepancies
- **-** accuracy


---

## HPRC (sequencing catalog)

Validated against sequencing, alignment, and annotation catalogs from the [HPRC Data Explorer](https://data.humanpangenome.org/).

Comparing against the following catalogs:

| Catalog | Records | Files Matched | Dimensions Validated |
|---|---:|---:|---|
| sequencing-data | 6,048 | 5,852 | Platform, Data Modality, Assay Type |
| alignments | 89 | 4 | Reference Assembly |
| annotations | 8,739 | 0 | Reference Assembly |
| assemblies | 560 | 188 | presence only |

### Data Modality

- **5,491** values available from source
- **2,012** also classified by rule engine
- **3,479** not classified by rule engine (no rule applies)
- **2,012** agreed
- **0** discrepancies
- **100.0%** accuracy

### Data Type

- **0** values available from source
- **0** also classified by rule engine
- **0** not classified by rule engine (no rule applies)
- **0** agreed
- **0** discrepancies
- **-** accuracy

### Platform

- **5,852** values available from source
- **5,852** also classified by rule engine
- **0** not classified by rule engine (no rule applies)
- **5,852** agreed
- **0** discrepancies
- **100.0%** accuracy

### Reference Assembly

- **4** values available from source
- **4** also classified by rule engine
- **0** not classified by rule engine (no rule applies)
- **4** agreed
- **0** discrepancies
- **100.0%** accuracy

### Assay Type

- **5,852** values available from source
- **3,269** also classified by rule engine
- **2,583** not classified by rule engine (no rule applies)
- **3,269** agreed
- **0** discrepancies
- **100.0%** accuracy


