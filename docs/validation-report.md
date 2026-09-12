# Validation Report

Comparing meta-disco rule engine classifications against external ground truth.
Classification run: **2026-09-12 15:24:14**

| Source | Files Matched | Dimensions | Agree | Discrepancies |
|---|---:|---:|---:|---:|
| HPRC | 6,048 | 4 | 12,690 | 233 |

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
| Reference Assembly | 2,574 |
| Assay Type | 6,048 |

### Data Modality Validation

- **5,848** files available from HPRC with ground truth Data Modality
- **2,054** files comparable (both source and rule engine have values)
- **3,794** files not classified by rule engine
- **2,054** inferred data modality values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 5,848 files on HPRC with ground truth data modality, we inferred data modality values for 2,054 files. 3,794 files remain unclassifiable by the rule engine.
Of the 2,054 inferred data modality values, 2,054 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in data modality between meta-disco and HPRC.

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
- **6,044** files comparable (both source and rule engine have values)
- **4** files not classified by rule engine
- **6,044** inferred platform values match HPRC
- **0** discrepancies
- **100.0%** accuracy

Of the 6,048 files on HPRC with ground truth platform, we inferred platform values for 6,044 files. 4 files remain unclassifiable by the rule engine.
Of the 6,044 inferred platform values, 6,044 (100.0%) matched HPRC. There were 0 discrepancies (0.0%) in platform between meta-disco and HPRC.

### Reference Assembly Validation

- **2,574** files available from HPRC with ground truth Reference Assembly
- **2,571** files comparable (both source and rule engine have values)
- **3** files not classified by rule engine
- **2,563** inferred reference assembly values match HPRC
- **8** discrepancies
- **99.7%** accuracy

Of the 2,574 files on HPRC with ground truth reference assembly, we inferred reference assembly values for 2,571 files. 3 files remain unclassifiable by the rule engine.
Of the 2,571 inferred reference assembly values, 2,563 (99.7%) matched HPRC. There were 8 discrepancies (0.3%) in reference assembly between meta-disco and HPRC.

#### Discrepancies

| Count | Inferred | HPRC | Example |
|---:|---|---|---|
| 7 | GRCh38 | CHM13 | hprc-v1.0-mc-chm13.grch38.vcf.gz.tbi |
| 1 | CHM13 | GRCh38 | hprc-v1.0-mc-chm13-minaf.0.1.min.old |

### Assay Type Validation

- **6,048** files available from HPRC with ground truth Assay Type
- **2,254** files comparable (both source and rule engine have values)
- **3,794** files not classified by rule engine
- **2,029** inferred assay type values match HPRC
- **225** discrepancies
- **90.0%** accuracy

Of the 6,048 files on HPRC with ground truth assay type, we inferred assay type values for 2,254 files. 3,794 files remain unclassifiable by the rule engine.
Of the 2,254 inferred assay type values, 2,029 (90.0%) matched HPRC. There were 225 discrepancies (10.0%) in assay type between meta-disco and HPRC.

#### Discrepancies

| Count | Inferred | HPRC | Example |
|---:|---|---|---|
| 225 | RNA-seq | ISO-seq | HG00126.lymph.m84081_240728_071012_s1-m84081_240728_051033_s2.flnc.bam |


