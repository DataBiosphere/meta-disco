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

The source currently has **758,658** open-access files. The following shows how many files have each metadata dimension populated:

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


