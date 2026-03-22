# Validation Report

Comparing meta-disco rule engine classifications against external ground truth.
Classification run: **2026-03-22 11:23:36**

| Source | Files Matched | Dimensions | Agree | Discrepancies |
|---|---:|---:|---:|---:|
| AnVIL (Azul metadata) | 4,608 | 2 | 635 | 24 |
| HPRC (sequencing catalog) | 5,852 | 4 | 12,033 | 0 |

---

## AnVIL (Azul metadata)

Validated against file-level metadata from the [AnVIL Data Explorer](https://explore.anvilproject.org/).

Matched **4,608** files (6,623 in source but not in our classifications).

### Data Modality

- **3,974** values available from source
- **25** also classified by rule engine
- **3,949** not classified by rule engine (no rule applies)
- **1** agreed
- **24** discrepancies
- **4.0%** accuracy

#### Discrepancies

| Count | Inferred | AnVIL | Example |
|---:|---|---|---|
| 22 | genomic | transcriptomic.single_cell | f87d31aeb3cf7963a733fef1779b1c5e |
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

- **638** values available from source
- **634** also classified by rule engine
- **4** not classified by rule engine (no rule applies)
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

Matched **5,852** files (9,584 in source but not in our classifications).

### Data Modality

- **5,491** values available from source
- **2,908** also classified by rule engine
- **2,583** not classified by rule engine (no rule applies)
- **2,908** agreed
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


