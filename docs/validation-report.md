# Validation Report

Comparing meta-disco rule engine classifications against external ground truth.
Classification run: **2026-09-27 23:09:29**

| Source | Files Matched | Dimensions | Agree | Discrepancies |
|---|---:|---:|---:|---:|
| HPRC | 6,048 | 4 | 7,441 | 2 |

---

## HPRC

Validated against sequencing, alignment, and annotation catalogs from the [HPRC Data Explorer](https://data.humanpangenome.org/).

### Metadata Overview

HPRC's open-access datasets currently populate the following genomic metadata dimensions:

| Dimension | Files with dimension in HPRC |
|---|---:|
| Data Modality | 225 |
| Data Type | 0 |
| Platform | 6,048 |
| Reference Assembly | 2,569 |
| Assay Type | 6,048 |

### Data Modality Validation

- **225** files available from HPRC with ground truth Data Modality
- **225** files comparable (both source and rule engine have values)
- **0** files not classified by rule engine
- **225** inferred data modality values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 225 files on HPRC with ground truth data modality, we inferred data modality values for 225 files. 0 files remain unclassifiable by the rule engine.
Of the 225 inferred data modality values, 225 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in data modality between meta-disco and HPRC.

### Data Type Validation

- **0** files available from HPRC with ground truth Data Type
- **0** files comparable (both source and rule engine have values)
- **0** files not classified by rule engine
- **0** inferred data type values match HPRC
- **0** discrepancies
- **-** accuracy

HPRC does not currently provide ground truth for data type.

### Platform Validation

- **6,048** files available from HPRC with ground truth Platform
- **6,045** files comparable (both source and rule engine have values)
- **3** files not classified by rule engine
- **6,045** inferred platform values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 6,048 files on HPRC with ground truth platform, we inferred platform values for 6,045 files. 3 files remain unclassifiable by the rule engine.
Of the 6,045 inferred platform values, 6,045 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in platform between meta-disco and HPRC.

### Reference Assembly Validation

- **2,569** files available from HPRC with ground truth Reference Assembly
- **1,173** files comparable (both source and rule engine have values)
- **1,396** files not classified by rule engine
- **1,171** inferred reference assembly values match HPRC
- **2** discrepancies
- **99.8%** accuracy

Of the 2,569 files on HPRC with ground truth reference assembly, we inferred reference assembly values for 1,173 files. 1,396 files remain unclassifiable by the rule engine.
Of the 1,173 inferred reference assembly values, 1,171 (99.8%) matched HPRC. There were 2 discrepancies (0.2%) in reference assembly between meta-disco and HPRC.

#### Discrepancies

| Count | Inferred | HPRC | Example |
|---:|---|---|---|
| 2 | GRCh38 | CHM13 | hprc-v1.0-mc-chm13.grch38.vcf.gz.tbi |

### Assay Type Validation

- **6,048** files available from HPRC with ground truth Assay Type
- **0** files comparable (both source and rule engine have values)
- **6,048** files not classified by rule engine
- **0** inferred assay type values match HPRC
- **0** discrepancies
- **-** accuracy

Of the 6,048 files on HPRC with ground truth assay type, we inferred assay type values for 0 files. 6,048 files remain unclassifiable by the rule engine.


