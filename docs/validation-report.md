# Validation Report

Comparing meta-disco rule engine classifications against external ground truth.
Classification run: **2026-09-04 01:03:19**

| Source | Files Matched | Dimensions | Agree | Discrepancies |
|---|---:|---:|---:|---:|
| AnVIL (Azul metadata) | 11,231 | 2 | 1,047 | 4 |
| HPRC | 6,048 | 4 | 12,690 | 233 |

---

## AnVIL (Azul metadata)

Validated against file-level metadata from the [AnVIL Data Explorer](https://explore.anvilproject.org/)'s open-access projects with **708,088** files across **12** datasets:

- ANVIL_T2T_CHRY (309,979 files)
- ANVIL_T2T (289,204 files)
- ANVIL_1000G_high_coverage_2019 (26,016 files)
- ANVIL_HPRC (23,185 files)
- AnVIL_HPRC_R2 (16,271 files)
- ANVIL_NIA_CARD_Coriell_Cell_Lines_Open (12,534 files)
- ANVIL_1000G_PRIMED_data_model (11,493 files)
- AnVIL_IGVF_Mouse_R1 (6,786 files)
- AnVIL_ENCORE_RS293 (3,752 files)
- ANVIL_nhp_dGTEx_V1 (3,591 files)
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
- **417** files comparable (both source and rule engine have values)
- **6,338** files not classified by rule engine
- **413** inferred data modality values match AnVIL
- **4** discrepancies
- **99.0%** accuracy

Of the 6,755 files on AnVIL with ground truth data modality, we inferred data modality values for 417 files. 6,338 files remain unclassifiable by the rule engine.
Of the 417 inferred data modality values, 413 (99.0%) matched AnVIL. There were 4 discrepancies (1.0%) in data modality between meta-disco and AnVIL.

#### Discrepancies

| Count | Inferred | AnVIL | Example |
|---:|---|---|---|
| 2 | genomic | epigenomic.chromatin_accessibility | 9a2afd8bc8423535f42201ba189540fb |
| 2 | transcriptomic.single_cell | epigenomic.chromatin_accessibility | f92b42c30ff64edb444dfece410630d2 |

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


