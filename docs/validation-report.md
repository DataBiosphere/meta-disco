# Validation Report

Comparing meta-disco rule engine classifications against external ground truth.
Classification run: **2026-09-22 23:05:21**

| Source | Files Matched | Dimensions | Agree | Discrepancies |
|---|---:|---:|---:|---:|
| HPRC | 6,048 | 4 | 8,823 | 230 |

---

## HPRC

Validated against sequencing, alignment, and annotation catalogs from the [HPRC Data Explorer](https://data.humanpangenome.org/).

### Metadata Overview

HPRC's open-access datasets currently populate the following genomic metadata dimensions:

| Dimension | Files with dimension in HPRC |
|---|---:|
| Data Modality | 5,848 |
| Data Type | 0 |
| Platform | 6,048 |
| Reference Assembly | 2,569 |
| Assay Type | 6,048 |

### Data Modality Validation

- **5,848** files available from HPRC with ground truth Data Modality
- **1,151** files comparable (both source and rule engine have values)
- **4,697** files not classified by rule engine
- **1,151** inferred data modality values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 5,848 files on HPRC with ground truth data modality, we inferred data modality values for 1,151 files. 4,697 files remain unclassifiable by the rule engine.
Of the 1,151 inferred data modality values, 1,151 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in data modality between meta-disco and HPRC.

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
- **6,039** files comparable (both source and rule engine have values)
- **9** files not classified by rule engine
- **6,039** inferred platform values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 6,048 files on HPRC with ground truth platform, we inferred platform values for 6,039 files. 9 files remain unclassifiable by the rule engine.
Of the 6,039 inferred platform values, 6,039 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in platform between meta-disco and HPRC.

### Reference Assembly Validation

- **2,569** files available from HPRC with ground truth Reference Assembly
- **1,638** files comparable (both source and rule engine have values)
- **931** files not classified by rule engine
- **1,633** inferred reference assembly values match HPRC
- **5** discrepancies
- **99.7%** accuracy

Of the 2,569 files on HPRC with ground truth reference assembly, we inferred reference assembly values for 1,638 files. 931 files remain unclassifiable by the rule engine.
Of the 1,638 inferred reference assembly values, 1,633 (99.7%) matched HPRC. There were 5 discrepancies (0.3%) in reference assembly between meta-disco and HPRC.

#### Discrepancies

| Count | Inferred | HPRC | Example |
|---:|---|---|---|
| 4 | GRCh38 | CHM13 | hprc-v1.0-mc-chm13.grch38.vcf.gz.tbi |
| 1 | CHM13 | GRCh38 | hprc-v1.0-mc-chm13-minaf.0.1.min.old |

### Assay Type Validation

- **6,048** files available from HPRC with ground truth Assay Type
- **225** files comparable (both source and rule engine have values)
- **5,823** files not classified by rule engine
- **0** inferred assay type values match HPRC
- **225** discrepancies
- **0.0%** accuracy

Of the 6,048 files on HPRC with ground truth assay type, we inferred assay type values for 225 files. 5,823 files remain unclassifiable by the rule engine.
Of the 225 inferred assay type values, 0 (0.0%) matched HPRC. There were 225 discrepancies (100.0%) in assay type between meta-disco and HPRC.

#### Discrepancies

| Count | Inferred | HPRC | Example |
|---:|---|---|---|
| 225 | RNA-seq | ISO-seq | HG00099.lymph.m84081_240722_230051_s3-m84081_240723_010018_s4.flnc.bam |


