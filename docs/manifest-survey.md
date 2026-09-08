# What the AnVIL manifests carry

Measured from the `anvil15` manifests on disk by `scripts/generate_manifest_survey.py` (issue #384). No network: every figure below comes from `data/anvil/manifest/`. Regenerate with `make manifest-survey`; the same numbers unrounded are in `docs/manifest-survey.json`.

This document measures. It classifies nothing and proposes no mapping — that is #369, #336 and #361, which it exists to scope.

## Datasets and row counts

| key | dataset | compact rows | snapshot file count | agree |
| --- | ---: | ---: | ---: | ---: |
| D1 | ANVIL_1000G_PRIMED_data_model | 11,493 | 11,493 | yes |
| D2 | ANVIL_1000G_high_coverage_2019 | 26,016 | 26,016 | yes |
| D3 | ANVIL_HPRC | 23,185 | 23,185 | yes |
| D4 | ANVIL_NIA_CARD_Coriell_Cell_Lines_Open | 12,534 | 12,534 | yes |
| D5 | ANVIL_T2T | 289,204 | 289,204 | yes |
| D6 | ANVIL_T2T_CHRY | 309,979 | 309,979 | yes |
| D7 | ANVIL_nhp_dGTEx_V1 | 3,591 | 3,591 | yes |
| D8 | AnVIL_ENCORE_293T | 1,992 | 1,992 | yes |
| D9 | AnVIL_ENCORE_RS293 | 3,752 | 3,752 | yes |
| D10 | AnVIL_HPRC_R2 | 16,271 | 16,271 | yes |
| D11 | AnVIL_IGVF_Mouse_R1 | 6,786 | 6,786 | yes |
| D12 | AnVIL_MAGE | 3,285 | 3,285 | yes |

12 datasets, 708,088 compact rows in total, matching the snapshot exactly.

A note on the sidecar: `manifests.json` records a verbatim `rows` count that is the number of `anvil_file` entities, not the number of lines — a verbatim manifest holds every entity, so it has several times as many lines as the dataset has files.

## Compact column coverage

Percentage of each dataset's rows where the column holds something. A cell counts as absent if, stripped and lowercased, it is one of ['', '[]', 'n/a', 'na', 'none', 'null', '{}']. Columns are the manifests' own 60, in manifest order; a dataset missing one of them reads as 0 for it.

Keys: **D1** 1000G_PRIMED_data_model, **D2** 1000G_high_coverage_2019, **D3** HPRC, **D4** NIA_CARD_Coriell_Cell_Lines_Open, **D5** T2T, **D6** T2T_CHRY, **D7** nhp_dGTEx_V1, **D8** ENCORE_293T, **D9** ENCORE_RS293, **D10** HPRC_R2, **D11** IGVF_Mouse_R1, **D12** MAGE

| column | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | D11 | D12 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bundles.bundle_uuid | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| bundles.bundle_version | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| sources.source_id | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| sources.source_spec | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| datasets.document_id | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| datasets.source_datarepo_row_ids | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 0 | 100 | 0 | 0 |
| datasets.dataset_id | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| datasets.consent_group | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| datasets.data_use_permission | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| datasets.owner | 0 | 100 | 0 | 100 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| datasets.principal_investigator | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| datasets.registered_identifier | 0 | 0 | 0 | 100 | 0 | 0 | 0 | 100 | 100 | 0 | 100 | 0 |
| datasets.title | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| datasets.data_modality | 100 | 100 | 100 | 0 | 100 | 100 | 0 | 0 | 0 | 0 | 0 | 0 |
| donors.document_id | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| donors.source_datarepo_row_ids | 0 | 98 | 18 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| donors.donor_id | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| donors.organism_type | 0 | 98 | 18 | <1 | 11 | 0 | 0 | 100 | 100 | 0 | >99 | 0 |
| donors.phenotypic_sex | 0 | 0 | 18 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| donors.reported_ethnicity | 0 | 0 | 0 | <1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| donors.genetic_ancestry | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnoses.document_id | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnoses.source_datarepo_row_ids | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnoses.diagnosis_id | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnoses.disease | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnoses.diagnosis_age_unit | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnoses.diagnosis_age | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnoses.onset_age_unit | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnoses.onset_age | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnoses.phenotype | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnoses.phenopacket | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| biosamples.document_id | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| biosamples.source_datarepo_row_ids | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| biosamples.biosample_id | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| biosamples.anatomical_site | 0 | 0 | 0 | <1 | 0 | 0 | 0 | 0 | 0 | 91 | >99 | 0 |
| biosamples.apriori_cell_type | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| biosamples.biosample_type | 0 | 0 | 0 | <1 | 0 | 0 | 0 | 0 | 0 | 91 | >99 | 0 |
| biosamples.disease | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| biosamples.donor_age_at_collection_unit | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 100 | 100 | 0 | 0 | 0 |
| biosamples.donor_age_at_collection | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| activities.document_id | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| activities.source_datarepo_row_ids | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| activities.activity_id | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| activities.activity_type | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 23 | >99 | 0 |
| activities.assay_type | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| activities.data_modality | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| activities.reference_assembly | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| files.document_id | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| files.source_datarepo_row_ids | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| files.file_id | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| files.data_modality | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | >99 | 0 |
| files.file_format | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| files.file_size | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| files.file_md5sum | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| files.reference_assembly | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 78 | 78 | 0 | 3 | 0 |
| files.file_name | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| files.is_supplementary | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| files.drs_uri | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| files.azul_url | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| files.azul_mirror_uri | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |

### The harmonized dimension columns

These are the columns a classifier would not need to exist if they were filled. Their emptiness has been the standing justification for inferring at all; here it is measured.

| column | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | D11 | D12 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| files.data_modality | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | >99 | 0 |
| files.reference_assembly | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 78 | 78 | 0 | 3 | 0 |
| activities.assay_type | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| activities.data_modality | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| activities.reference_assembly | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| datasets.data_modality | 100 | 100 | 100 | 0 | 100 | 100 | 0 | 0 | 0 | 0 | 0 | 0 |

### The provenance join

`donors.donor_id`, `biosamples.biosample_id` and `activities.activity_id` are filled at an identical rate on 12 of 12 datasets, so the join arrives whole or not at all: a dataset that can reach a donor can reach its biosample and the activity that produced the file, and one that cannot reach any of them is missing all three.

| column | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | D11 | D12 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| donors.donor_id | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| biosamples.biosample_id | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |
| activities.activity_id | 0 | 98 | 20 | <1 | 11 | 0 | 0 | 100 | 100 | 91 | >99 | 0 |

### Governance columns

What #336 wants to import.

| column | D1 | D2 | D3 | D4 | D5 | D6 | D7 | D8 | D9 | D10 | D11 | D12 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| datasets.consent_group | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| datasets.data_use_permission | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| datasets.registered_identifier | 0 | 0 | 0 | 100 | 0 | 0 | 0 | 100 | 100 | 0 | 100 | 0 |

### Which absent spellings actually occur

Across every dataset: `(empty)` 25,734,133. Any spelling in the absence rule that does not appear here cost nothing; one that appears in quantity is worth checking against the column it came from, in case a real value is being read as a gap.

## Verbatim entity census

Every entity `type` in each dataset's verbatim manifest with its row count. `anvil_*` types are Azul's harmonized entities; everything else is the submitter's own Terra table, carried through unaltered.

### ANVIL_1000G_PRIMED_data_model

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 11,493 | — | — | — |
| `file_inventory` | submitter | 11,493 | 11,493 | — | — |
| `sequencing_file` | submitter | 8,634 | 8,634 | — | — |
| `anvil_biosample` | harmonized | 3,202 | — | — | — |
| `anvil_donor` | harmonized | 3,202 | — | — | — |
| `population_descriptor` | submitter | 3,202 | 0 | — | — |
| `sample` | submitter | 3,202 | 0 | — | — |
| `subject` | submitter | 3,202 | 0 | — | — |
| `plink_file_wide` | submitter | 2,854 | 8,562 | data_type = (no vocabulary term) | — |
| `sequencing_dataset` | submitter | 126 | 0 | — | `reference_assembly` → reference_assembly; `seq_platform` → platform; `sequencing_assay` → assay_type |
| `sample_set` | submitter | 64 | 0 | — | — |
| `anvil_activity` | harmonized | 23 | — | — | — |
| `workspace_attributes` | submitter | 5 | 0 | — | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |

- **`file_inventory`** (11,493 rows): `content_type` 100%, `crc32c` 100%, `datarepo_row_id` 100%, `file_id` 100%, `file_ref` 100%, `full_extension` 100%, `ingest_provenance` 100%, `md5_hash` 100%, `name` 100%, `path` 100%, `size_in_bytes` 100%, `uri` 100%, `version` 100%
- **`sequencing_file`** (8,634 rows): `datarepo_row_id` 100%, `file_path` 100%, `file_type` 100%, `ingest_provenance` 100%, `md5sum` 100%, `sequencing_dataset_id` 100%, `sequencing_file_id` 100%, `version` 100%, `chromosome` >99%
- **`population_descriptor`** (3,202 rows): `country_of_recruitment` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `population_descriptor` 100%, `population_descriptor_id` 100%, `population_label` 100%, `subject_id` 100%, `version` 100%
- **`sample`** (3,202 rows): `datarepo_row_id` 100%, `ingest_provenance` 100%, `sample_id` 100%, `subject_id` 100%, `tissue_source` 100%, `version` 100%
- **`subject`** (3,202 rows): `consent_code` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `reported_sex` 100%, `study_nickname` 100%, `subject_id` 100%, `version` 100%
- **`plink_file_wide`** (2,854 rows): `chromosome` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `pgen` 100%, `plink_file_wide_id` 100%, `psam` 100%, `pvar` 100%, `sequencing_dataset_id` 100%, `version` 100%
- **`sequencing_dataset`** (126 rows): `alignment_method` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `reference_assembly` 100%, `sample_set_id` 100%, `seq_center` 100%, `seq_platform` 100%, `sequencing_assay` 100%, `sequencing_dataset_id` 100%, `version` 100%, `average_target_depth` 50%
- **`sample_set`** (64 rows): `datarepo_row_id` 100%, `ingest_provenance` 100%, `sample_set_id` 100%, `samples` 100%, `version` 100%
- **`workspace_attributes`** (5 rows): `attribute` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `version` 100%, `value` 80%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%

### ANVIL_1000G_high_coverage_2019

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 26,016 | — | — | — |
| `file_inventory` | submitter | 26,016 | 26,016 | — | — |
| `anvil_activity` | harmonized | 25,863 | — | — | — |
| `anvil_biosample` | harmonized | 6,404 | — | — | — |
| `anvil_donor` | harmonized | 3,202 | — | — | — |
| `participant` | submitter | 3,202 | 6,398 | — | `instrument_model` → platform; `instrument_platform` → platform |
| `pedigree` | submitter | 3,202 | 0 | — | — |
| `sample` | submitter | 3,202 | 9,603 | — | `instrument_model` → platform; `library_selection` → assay_type; `library_source` → data_modality; `library_strategy` → assay_type |
| `qc_result_sample` | submitter | 3,184 | 3,184 | — | — |
| `workspace_attributes` | submitter | 24 | 0 | — | — |
| `sample_set` | submitter | 2 | 0 | — | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |

- **`file_inventory`** (26,016 rows): `content_type` 100%, `crc32c` 100%, `datarepo_row_id` 100%, `file_id` 100%, `file_ref` 100%, `full_extension` 100%, `ingest_provenance` 100%, `md5_hash` 100%, `name` 100%, `path` 100%, `size_in_bytes` 100%, `uri` 100%, `version` 100%
- **`participant`** (3,202 rows): `center_name` 100%, `datarepo_row_id` 100%, `experiment_id` 100%, `ingest_provenance` 100%, `insert_size` 100%, `instrument_model` 100%, `instrument_platform` 100%, `library_layout` 100%, `library_name` 100%, `md5sum` 100%, `participant` 100%, `participant_id` 100%, `population` 100%, `run_id` 100%, `run_name` 100%, `sample_name` 100%, `study_id` 100%, `study_name` 100%, `submission_date` 100%, `submission_id` 100%, `version` 100%, `gvcf` >99%, `gvcf_tbi` >99%
- **`pedigree`** (3,202 rows): `datarepo_row_id` 100%, `familyid` 100%, `fatherid` 100%, `ingest_provenance` 100%, `motherid` 100%, `pedigree_id` 100%, `population` 100%, `sex` 100%, `superpopulation` 100%, `version` 100%
- **`sample`** (3,202 rows): `cram` 100%, `datarepo_row_id` 100%, `gvcf` 100%, `ingest_provenance` 100%, `insert_size` 100%, `instrument_model` 100%, `library_construction_protocol` 100%, `library_layout` 100%, `library_name` 100%, `library_selection` 100%, `library_source` 100%, `library_strategy` 100%, `participant` 100%, `sample_alias` 100%, `sample_id` 100%, `version` 100%, `gvcf_tbi` >99%, `gvcf_index` <1%
- **`qc_result_sample`** (3,184 rows): `cram` 100%, `datarepo_row_id` 100%, `freemix` 100%, `ingest_provenance` 100%, `mean_coverage` 100%, `median_absolute_deviation` 100%, `median_insert_size` 100%, `pct_10x` 100%, `pct_20x` 100%, `pct_30x` 100%, `pct_chimeras` 100%, `percent_duplication` 100%, `q20_bases` 100%, `qc_result_sample` 100%, `qc_result_sample_id` 100%, `qc_status` 100%, `read1_pf_mismatch_rate` 100%, `read2_pf_mismatch_rate` 100%, `version` 100%
- **`workspace_attributes`** (24 rows): `attribute` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `version` 100%, `value` 88%
- **`sample_set`** (2 rows): `datarepo_row_id` 100%, `ingest_provenance` 100%, `sample_set_id` 100%, `samples` 100%, `version` 100%, `downsampled_gds` 50%, `downsampled_vcf` 50%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%

### ANVIL_HPRC

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 23,185 | — | — | — |
| `file_inventory` | submitter | 23,185 | 23,185 | — | — |
| `anvil_activity` | harmonized | 1,897 | — | — | — |
| `anvil_biosample` | harmonized | 57 | — | — | — |
| `anvil_donor` | harmonized | 57 | — | — | — |
| `sample` | submitter | 57 | 4,432 | — | — |
| `assembly_annotation` | submitter | 47 | 881 | data_type = assembly; data_type = annotations | — |
| `assembly_sample` | submitter | 47 | 469 | data_type = assembly | — |
| `participant` | submitter | 47 | 0 | — | — |
| `workspace_attributes` | submitter | 37 | 0 | — | — |
| `minigraph_cactus` | submitter | 6 | 60 | data_type = pangenome | — |
| `minigraph` | submitter | 2 | 6 | data_type = pangenome | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |
| `pggb` | submitter | 1 | 3 | data_type = pangenome | — |

- **`file_inventory`** (23,185 rows): `content_type` 100%, `crc32c` 100%, `datarepo_row_id` 100%, `file_id` 100%, `file_ref` 100%, `ingest_provenance` 100%, `md5_hash` 100%, `name` 100%, `path` 100%, `size_in_bytes` 100%, `uri` 100%, `version` 100%, `full_extension` >99%
- **`sample`** (57 rows): `cohort` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `maternal_id` 100%, `paternal_id` 100%, `sample_id` 100%, `version` 100%, `hifi` 91%, `mat_ilmn` 89%, `pat_ilmn` 89%, `child_ilmn` 86%, `bionano_cmap` 74%, `hic` 74%, `bionano_bnx` 72%, `nanopore` 68%, `notes` 18%, `strandseq` 14%
- **`assembly_annotation`** (47 rows): `all_flagger` 100%, `assembly_annotation_id` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `mat_asat` 100%, `mat_dna_brnn` 100%, `mat_hsat` 100%, `mat_repeat_masker` 100%, `mat_seg_dups` 100%, `mat_trf` 100%, `pat_asat` 100%, `pat_dna_brnn` 100%, `pat_hsat` 100%, `pat_repeat_masker` 100%, `pat_seg_dups` 100%, `pat_trf` 100%, `unreliable_only_flagger` 100%, `unreliable_only_no_mt_flagger` 100%, `version` 100%, `mat_chm13_cat_genes` 94%, `mat_hg38_cat_genes` 94%, `pat_chm13_cat_genes` 94%, `pat_hg38_cat_genes` 94%
- **`assembly_sample`** (47 rows): `assembly_sample_id` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `mat_chm13_aln_bai` 100%, `mat_chm13_aln_bam` 100%, `mat_fasta` 100%, `mat_grch38_aln_bai` 100%, `mat_grch38_aln_bam` 100%, `pat_chm13_aln_bai` 100%, `pat_chm13_aln_bam` 100%, `pat_fasta` 100%, `pat_grch38_aln_bai` 100%, `pat_grch38_aln_bam` 100%, `version` 100%
- **`participant`** (47 rows): `cohort` 100%, `datarepo_row_id` 100%, `familyid` 100%, `ingest_provenance` 100%, `participant_id` 100%, `sex` 100%, `version` 100%, `subpopulation` 94%, `superpopulation` 94%, `notes` 6%
- **`workspace_attributes`** (37 rows): `attribute` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `version` 100%, `value` 19%
- **`minigraph_cactus`** (6 rows): `datarepo_row_id` 100%, `dist` 100%, `gbwt` 100%, `gfa` 100%, `gg` 100%, `ingest_provenance` 100%, `min` 100%, `minigraph_cactus_id` 100%, `snarls` 100%, `trans` 100%, `version` 100%, `xg` 100%, `grch38_xg` 33%, `hal` 33%, `masking` 33%, `vcf` 33%, `vcf_index` 33%, `grch38_vcf` 17%, `grch38_vcf_index` 17%
- **`minigraph`** (2 rows): `bed` 100%, `bed_index` 100%, `datarepo_row_id` 100%, `gfa` 100%, `ingest_provenance` 100%, `minigraph_id` 100%, `version` 100%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%
- **`pggb`** (1 row): `datarepo_row_id` 100%, `gfa` 100%, `ingest_provenance` 100%, `pggb_id` 100%, `untangle_delta` 100%, `untangle_paf` 100%, `version` 100%

### ANVIL_NIA_CARD_Coriell_Cell_Lines_Open

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 12,534 | — | — | — |
| `file_inventory` | submitter | 12,534 | 12,534 | — | — |
| `workspace_attributes` | submitter | 24 | 0 | — | — |
| `anvil_sequencingactivity` | harmonized | 6 | — | — | — |
| `sequencing` | submitter | 6 | 6 | — | `reference_genome_build` → reference_assembly; `sequencing_assay` → assay_type; `sequencing_platform` → platform; `sequencing_strategy` → assay_type |
| `anvil_biosample` | harmonized | 3 | — | — | — |
| `anvil_donor` | harmonized | 3 | — | — | — |
| `sample` | submitter | 3 | 0 | — | — |
| `subject` | submitter | 3 | 0 | — | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |

- **`file_inventory`** (12,534 rows): `crc32c` 100%, `datarepo_row_id` 100%, `file_id` 100%, `file_ref` 100%, `full_extension` 100%, `ingest_provenance` 100%, `md5_hash` 100%, `name` 100%, `path` 100%, `size_in_bytes` 100%, `uri` 100%, `version` 100%, `content_type` 39%
- **`workspace_attributes`** (24 rows): `attribute` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `version` 100%, `value` 96%
- **`sequencing`** (6 rows): `alignment_method` 100%, `analyte_type` 100%, `data_processing_pipeline` 100%, `datarepo_row_id` 100%, `date_data_generation` 100%, `ingest_provenance` 100%, `library_prep_kit_method` 100%, `number_of_independent_libraries` 100%, `read_length` 100%, `reference_genome_build` 100%, `sample_id` 100%, `seq_filename` 100%, `sequencer_id` 100%, `sequencing_assay` 100%, `sequencing_id` 100%, `sequencing_id_fileref` 100%, `sequencing_platform` 100%, `sequencing_strategy` 100%, `sex` 100%, `submitter_id` 100%, `target_depth` 100%, `tissue_source` 100%, `version` 100%
- **`sample`** (3 rows): `datarepo_row_id` 100%, `dbgap_sample_id` 100%, `ingest_provenance` 100%, `sample_id` 100%, `sample_provider` 100%, `sample_source` 100%, `subject_id` 100%, `version` 100%
- **`subject`** (3 rows): `datarepo_row_id` 100%, `dbgap_study_id` 100%, `dbgap_subject_id` 100%, `ingest_provenance` 100%, `race_ethnicity` 100%, `race_ethnicity_detail` 100%, `sequencing_center` 100%, `sex` 100%, `subject_id` 100%, `version` 100%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%

### ANVIL_T2T

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `file_inventory` | submitter | 290,135 | 289,204 | — | — |
| `anvil_file` | harmonized | 289,204 | — | — | — |
| `anvil_activity` | harmonized | 119,454 | — | — | — |
| `interval` | submitter | 31,155 | 93,465 | data_type = interval_set | — |
| `anvil_biosample` | harmonized | 3,202 | — | — | — |
| `anvil_donor` | harmonized | 3,202 | — | — | — |
| `participant` | submitter | 3,202 | 32,020 | — | — |
| `workspace_attributes` | submitter | 79 | 0 | — | — |
| `chromosome` | submitter | 24 | 120 | — | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |

- **`file_inventory`** (290,135 rows): `crc32c` 100%, `datarepo_row_id` 100%, `file_id` 100%, `file_ref` 100%, `ingest_provenance` 100%, `md5_hash` 100%, `name` 100%, `path` 100%, `size_in_bytes` 100%, `uri` 100%, `version` 100%, `full_extension` >99%, `content_type` >99%
- **`interval`** (31,155 rows): `chromosome` 100%, `datarepo_row_id` 100%, `genomics_db_tar` 100%, `genotyped_bcftools_index` 100%, `genotyped_bgzip` 100%, `ingest_provenance` 100%, `interval_id` 100%, `margined_end` 100%, `margined_start` 100%, `start` 100%, `t_end` 100%, `version` 100%
- **`participant`** (3,202 rows): `cram` 100%, `cram_index` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `mosdepth_global_dist` 100%, `mosdepth_regions_bed` 100%, `mosdepth_regions_bed_idx` 100%, `mosdepth_regions_dist` 100%, `mosdepth_summary` 100%, `participant_id` 100%, `read_1_fastq` 100%, `read_2_fastq` 100%, `samtools_stats` 100%, `sex` 100%, `version` 100%
- **`workspace_attributes`** (79 rows): `attribute` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `version` 100%, `value` 65%
- **`chromosome`** (24 rows): `chm13_pass_vcf_gz` 100%, `chm13_raw_vcf_gz` 100%, `chm13_recalibrated_vcf_gz` 100%, `chromosome_id` 100%, `datarepo_row_id` 100%, `grch38_pass_vcf_gz` 100%, `grch38_recalibrated_vcf_gz` 100%, `ingest_provenance` 100%, `version` 100%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%

### ANVIL_T2T_CHRY

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 309,979 | — | — | — |
| `file_inventory` | submitter | 309,979 | 309,979 | — | — |
| `anvil_activity` | harmonized | 98,144 | — | — | — |
| `PAR_interval_CHM13v2` | submitter | 31,158 | 62,316 | data_type = interval_set; reference_assembly = CHM13 | — |
| `PAR_interval_GRCh38` | submitter | 30,864 | 30,864 | data_type = interval_set; reference_assembly = GRCh38 | — |
| `1KGP_CHM13v2_sample` | submitter | 3,202 | 184,105 | reference_assembly = CHM13 | — |
| `SGDP_CHM13v2_sample` | submitter | 279 | 16,324 | reference_assembly = CHM13 | — |
| `SGDP_GRCh38_sample` | submitter | 279 | 16,324 | reference_assembly = GRCh38 | — |
| `workspace_attributes` | submitter | 67 | 0 | — | — |
| `1KGP_CHM13v2_chromosome` | submitter | 24 | 240 | reference_assembly = CHM13 | — |
| `SGDP_CHM13v2_chromosome` | submitter | 24 | 168 | reference_assembly = CHM13 | — |
| `SGDP_GRCh38_chromosome` | submitter | 24 | 168 | reference_assembly = GRCh38 | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |

- **`file_inventory`** (309,979 rows): `content_type` 100%, `crc32c` 100%, `datarepo_row_id` 100%, `file_id` 100%, `file_ref` 100%, `full_extension` 100%, `ingest_provenance` 100%, `md5_hash` 100%, `name` 100%, `path` 100%, `size_in_bytes` 100%, `uri` 100%, `version` 100%
- **`PAR_interval_CHM13v2`** (31,158 rows): `chromosome` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `margined_end` 100%, `margined_start` 100%, `par_interval_chm13v2_id` 100%, `region_type` 100%, `sgdp_genomics_db_tar` 100%, `start` 100%, `t_1kgp_genomics_db_tar` 100%, `t_end` 100%, `version` 100%
- **`PAR_interval_GRCh38`** (30,864 rows): `chromosome` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `margined_end` 100%, `margined_start` 100%, `par_interval_grch38_id` 100%, `region_type` 100%, `sgdp_genomics_db_tar` 100%, `start` 100%, `t_end` 100%, `version` 100%
- **`1KGP_CHM13v2_sample`** (3,202 rows): `chr10_hcvcf_gz` 100%, `chr10_hcvcf_index` 100%, `chr11_hcvcf_gz` 100%, `chr11_hcvcf_index` 100%, `chr12_hcvcf_gz` 100%, `chr12_hcvcf_index` 100%, `chr13_hcvcf_gz` 100%, `chr13_hcvcf_index` 100%, `chr14_hcvcf_gz` 100%, `chr14_hcvcf_index` 100%, `chr15_hcvcf_gz` 100%, `chr15_hcvcf_index` 100%, `chr16_hcvcf_gz` 100%, `chr16_hcvcf_index` 100%, `chr17_hcvcf_gz` 100%, `chr17_hcvcf_index` 100%, `chr18_hcvcf_gz` 100%, `chr18_hcvcf_index` 100%, `chr19_hcvcf_gz` 100%, `chr19_hcvcf_index` 100%, `chr1_hcvcf_gz` 100%, `chr1_hcvcf_index` 100%, `chr20_hcvcf_gz` 100%, `chr20_hcvcf_index` 100%, `chr21_hcvcf_gz` 100%, `chr21_hcvcf_index` 100%, `chr22_hcvcf_gz` 100%, `chr22_hcvcf_index` 100%, `chr2_hcvcf_gz` 100%, `chr2_hcvcf_index` 100%, `chr3_hcvcf_gz` 100%, `chr3_hcvcf_index` 100%, `chr4_hcvcf_gz` 100%, `chr4_hcvcf_index` 100%, `chr5_hcvcf_gz` 100%, `chr5_hcvcf_index` 100%, `chr6_hcvcf_gz` 100%, `chr6_hcvcf_index` 100%, `chr7_hcvcf_gz` 100%, `chr7_hcvcf_index` 100%, `chr8_hcvcf_gz` 100%, `chr8_hcvcf_index` 100%, `chr9_hcvcf_gz` 100%, `chr9_hcvcf_index` 100%, `chrx_samtools_stats` 100%, `cram` 100%, `cram_index` 100%, `datarepo_row_id` 100%, `full_samtools_stats` 100%, `ingest_provenance` 100%, `karyotype` 100%, `mosdepth_global_dist` 100%, `mosdepth_regions_bed` 100%, `mosdepth_regions_dist` 100%, `mosdepth_regions_index` 100%, `mosdepth_summary` 100%, `population` 100%, `superpopulation` 100%, `t_1kgp_chm13v2_sample_id` 100%, `unrelated` 100%, `version` 100%, `xx_x_hcvcf_gz` 50%, `xx_x_hcvcf_index` 50%, `chry_samtools_stats` 50%, `xy_x_nonpar_hcvcf_gz` 50%, `xy_x_nonpar_hcvcf_index` 50%, `xy_x_par_hcvcf_gz` 50%, `xy_x_par_hcvcf_index` 50%, `xy_y_nonpar_hcvcf_gz` 50%, `xy_y_nonpar_hcvcf_index` 50%
- **`SGDP_CHM13v2_sample`** (279 rows): `chr10_hcvcf_gz` 100%, `chr10_hcvcf_index` 100%, `chr11_hcvcf_gz` 100%, `chr11_hcvcf_index` 100%, `chr12_hcvcf_gz` 100%, `chr12_hcvcf_index` 100%, `chr13_hcvcf_gz` 100%, `chr13_hcvcf_index` 100%, `chr14_hcvcf_gz` 100%, `chr14_hcvcf_index` 100%, `chr15_hcvcf_gz` 100%, `chr15_hcvcf_index` 100%, `chr16_hcvcf_gz` 100%, `chr16_hcvcf_index` 100%, `chr17_hcvcf_gz` 100%, `chr17_hcvcf_index` 100%, `chr18_hcvcf_gz` 100%, `chr18_hcvcf_index` 100%, `chr19_hcvcf_gz` 100%, `chr19_hcvcf_index` 100%, `chr1_hcvcf_gz` 100%, `chr1_hcvcf_index` 100%, `chr20_hcvcf_gz` 100%, `chr20_hcvcf_index` 100%, `chr21_hcvcf_gz` 100%, `chr21_hcvcf_index` 100%, `chr22_hcvcf_gz` 100%, `chr22_hcvcf_index` 100%, `chr2_hcvcf_gz` 100%, `chr2_hcvcf_index` 100%, `chr3_hcvcf_gz` 100%, `chr3_hcvcf_index` 100%, `chr4_hcvcf_gz` 100%, `chr4_hcvcf_index` 100%, `chr5_hcvcf_gz` 100%, `chr5_hcvcf_index` 100%, `chr6_hcvcf_gz` 100%, `chr6_hcvcf_index` 100%, `chr7_hcvcf_gz` 100%, `chr7_hcvcf_index` 100%, `chr8_hcvcf_gz` 100%, `chr8_hcvcf_index` 100%, `chr9_hcvcf_gz` 100%, `chr9_hcvcf_index` 100%, `country` 100%, `cram` 100%, `cram_index` 100%, `datarepo_row_id` 100%, `full_samtools_stats` 100%, `ingest_provenance` 100%, `karyotype` 100%, `mosdepth_global_dist` 100%, `mosdepth_regions_bed` 100%, `mosdepth_regions_dist` 100%, `mosdepth_regions_index` 100%, `mosdepth_summary` 100%, `panel` 100%, `population_id` 100%, `read_1_fastq` 100%, `read_2_fastq` 100%, `region` 100%, `sgdp_chm13v2_sample_id` 100%, `sgdp_id` 100%, `version` 100%, `xy_x_nonpar_hcvcf_gz` 63%, `xy_x_nonpar_hcvcf_index` 63%, `xy_x_par_hcvcf_gz` 63%, `xy_x_par_hcvcf_index` 63%, `xy_y_nonpar_hcvcf_gz` 63%, `xy_y_nonpar_hcvcf_index` 63%, `xx_x_hcvcf_gz` 37%, `xx_x_hcvcf_index` 37%
- **`SGDP_GRCh38_sample`** (279 rows): `chr10_hcvcf_gz` 100%, `chr10_hcvcf_index` 100%, `chr11_hcvcf_gz` 100%, `chr11_hcvcf_index` 100%, `chr12_hcvcf_gz` 100%, `chr12_hcvcf_index` 100%, `chr13_hcvcf_gz` 100%, `chr13_hcvcf_index` 100%, `chr14_hcvcf_gz` 100%, `chr14_hcvcf_index` 100%, `chr15_hcvcf_gz` 100%, `chr15_hcvcf_index` 100%, `chr16_hcvcf_gz` 100%, `chr16_hcvcf_index` 100%, `chr17_hcvcf_gz` 100%, `chr17_hcvcf_index` 100%, `chr18_hcvcf_gz` 100%, `chr18_hcvcf_index` 100%, `chr19_hcvcf_gz` 100%, `chr19_hcvcf_index` 100%, `chr1_hcvcf_gz` 100%, `chr1_hcvcf_index` 100%, `chr20_hcvcf_gz` 100%, `chr20_hcvcf_index` 100%, `chr21_hcvcf_gz` 100%, `chr21_hcvcf_index` 100%, `chr22_hcvcf_gz` 100%, `chr22_hcvcf_index` 100%, `chr2_hcvcf_gz` 100%, `chr2_hcvcf_index` 100%, `chr3_hcvcf_gz` 100%, `chr3_hcvcf_index` 100%, `chr4_hcvcf_gz` 100%, `chr4_hcvcf_index` 100%, `chr5_hcvcf_gz` 100%, `chr5_hcvcf_index` 100%, `chr6_hcvcf_gz` 100%, `chr6_hcvcf_index` 100%, `chr7_hcvcf_gz` 100%, `chr7_hcvcf_index` 100%, `chr8_hcvcf_gz` 100%, `chr8_hcvcf_index` 100%, `chr9_hcvcf_gz` 100%, `chr9_hcvcf_index` 100%, `country` 100%, `cram` 100%, `cram_index` 100%, `datarepo_row_id` 100%, `full_samtools_stats` 100%, `ingest_provenance` 100%, `karyotype` 100%, `mosdepth_global_dist` 100%, `mosdepth_regions_bed` 100%, `mosdepth_regions_dist` 100%, `mosdepth_regions_index` 100%, `mosdepth_summary` 100%, `panel` 100%, `population_id` 100%, `read_1_fastq` 100%, `read_2_fastq` 100%, `region` 100%, `sgdp_grch38_sample_id` 100%, `sgdp_id` 100%, `version` 100%, `xy_x_nonpar_hcvcf_gz` 63%, `xy_x_nonpar_hcvcf_index` 63%, `xy_x_par_hcvcf_gz` 63%, `xy_x_par_hcvcf_index` 63%, `xy_y_nonpar_hcvcf_gz` 63%, `xy_y_nonpar_hcvcf_index` 63%, `xx_x_hcvcf_gz` 37%, `xx_x_hcvcf_index` 37%
- **`workspace_attributes`** (67 rows): `attribute` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `version` 100%, `value` 96%
- **`1KGP_CHM13v2_chromosome`** (24 rows): `chm13v2_pass_index` 100%, `chm13v2_pass_stats` 100%, `chm13v2_pass_unrelated_index` 100%, `chm13v2_pass_unrelated_stats` 100%, `chm13v2_pass_unrelated_vcf_gz` 100%, `chm13v2_pass_vcf_gz` 100%, `chm13v2_raw_index` 100%, `chm13v2_raw_vcf_gz` 100%, `chm13v2_recalibrated_index` 100%, `chm13v2_recalibrated_vcf_gz` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `t_1kgp_chm13v2_chromosome_id` 100%, `version` 100%
- **`SGDP_CHM13v2_chromosome`** (24 rows): `chm13v2_pass_index` 100%, `chm13v2_pass_stats` 100%, `chm13v2_pass_vcf_gz` 100%, `chm13v2_raw_index` 100%, `chm13v2_raw_vcf_gz` 100%, `chm13v2_recalibrated_index` 100%, `chm13v2_recalibrated_vcf_gz` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `sgdp_chm13v2_chromosome_id` 100%, `version` 100%
- **`SGDP_GRCh38_chromosome`** (24 rows): `datarepo_row_id` 100%, `grch38_pass_index` 100%, `grch38_pass_stats` 100%, `grch38_pass_vcf_gz` 100%, `grch38_raw_index` 100%, `grch38_raw_vcf_gz` 100%, `grch38_recalibrated_index` 100%, `grch38_recalibrated_vcf_gz` 100%, `ingest_provenance` 100%, `sgdp_grch38_chromosome_id` 100%, `version` 100%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%

### ANVIL_nhp_dGTEx_V1

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 3,591 | — | — | — |
| `file_inventory` | submitter | 3,591 | 3,591 | — | — |
| `anvil_activity` | harmonized | 756 | — | — | — |
| `workspace_attributes` | submitter | 2 | 0 | — | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |

- **`file_inventory`** (3,591 rows): `content_type` 100%, `crc32c` 100%, `datarepo_row_id` 100%, `file_id` 100%, `file_ref` 100%, `full_extension` 100%, `ingest_provenance` 100%, `md5_hash` 100%, `name` 100%, `path` 100%, `size_in_bytes` 100%, `uri` 100%, `version` 100%
- **`workspace_attributes`** (2 rows): `attribute` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `version` 100%, `value` 50%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%

### AnVIL_ENCORE_293T

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 1,992 | — | — | `reference_assembly` → reference_assembly |
| `file` | submitter | 1,992 | 1,992 | — | `reference_assembly` → reference_assembly |
| `activity` | submitter | 1,100 | 1,096 | — | — |
| `anvil_activity` | harmonized | 1,100 | — | — | — |
| `anvil_biosample` | harmonized | 224 | — | — | — |
| `biosample` | submitter | 224 | 0 | — | — |
| `ingestion_reference` | submitter | 2 | 0 | — | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_donor` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `donor` | submitter | 1 | 0 | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |
| `project` | submitter | 1 | 0 | — | — |

- **`file`** (1,992 rows): `associated_biosample_id` 100%, `datarepo_row_id` 100%, `file_format` 100%, `file_id` 100%, `file_md5sum` 100%, `file_name` 100%, `file_ref` 100%, `file_size` 100%, `version` 100%, `reference_assembly` 78%
- **`activity`** (1,100 rows): `activity_id` 100%, `activity_type` 100%, `datarepo_row_id` 100%, `generated_file_id` 100%, `used_biosample_id` 100%, `version` 100%, `used_file_id` 80%
- **`biosample`** (224 rows): `biosample_id` 100%, `datarepo_row_id` 100%, `donor_id` 100%, `version` 100%, `donor_age_at_collection_lower_bound` 98%, `donor_age_at_collection_unit` 98%, `donor_age_at_collection_upper_bound` 98%
- **`ingestion_reference`** (2 rows): `datarepo_row_id` 100%, `key` 100%, `value` 100%, `version` 100%
- **`donor`** (1 row): `datarepo_row_id` 100%, `donor_id` 100%, `donor_type` 100%, `organism_type` 100%, `phenotypic_sex` 100%, `version` 100%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%
- **`project`** (1 row): `datarepo_row_id` 100%, `funded_by` 100%, `principal_investigator` 100%, `project_id` 100%, `registered_identifier` 100%, `title` 100%, `version` 100%

### AnVIL_ENCORE_RS293

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 3,752 | — | — | `reference_assembly` → reference_assembly |
| `file` | submitter | 3,752 | 3,752 | — | `reference_assembly` → reference_assembly |
| `activity` | submitter | 2,112 | 2,112 | — | — |
| `anvil_activity` | harmonized | 2,112 | — | — | — |
| `anvil_biosample` | harmonized | 410 | — | — | — |
| `biosample` | submitter | 410 | 0 | — | — |
| `anvil_donor` | harmonized | 2 | — | — | — |
| `donor` | submitter | 2 | 0 | — | — |
| `ingestion_reference` | submitter | 2 | 0 | — | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |
| `project` | submitter | 1 | 0 | — | — |

- **`file`** (3,752 rows): `associated_biosample_id` 100%, `datarepo_row_id` 100%, `file_format` 100%, `file_id` 100%, `file_md5sum` 100%, `file_name` 100%, `file_ref` 100%, `file_size` 100%, `version` 100%, `reference_assembly` 78%
- **`activity`** (2,112 rows): `activity_id` 100%, `activity_type` 100%, `datarepo_row_id` 100%, `generated_file_id` 100%, `used_biosample_id` 100%, `version` 100%, `used_file_id` 81%
- **`biosample`** (410 rows): `biosample_id` 100%, `datarepo_row_id` 100%, `donor_age_at_collection_lower_bound` 100%, `donor_age_at_collection_unit` 100%, `donor_age_at_collection_upper_bound` 100%, `donor_id` 100%, `version` 100%
- **`donor`** (2 rows): `datarepo_row_id` 100%, `donor_id` 100%, `donor_type` 100%, `organism_type` 100%, `phenotypic_sex` 100%, `version` 100%
- **`ingestion_reference`** (2 rows): `datarepo_row_id` 100%, `key` 100%, `value` 100%, `version` 100%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%
- **`project`** (1 row): `datarepo_row_id` 100%, `funded_by` 100%, `principal_investigator` 100%, `project_id` 100%, `registered_identifier` 100%, `title` 100%, `version` 100%

### AnVIL_HPRC_R2

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 16,271 | — | — | — |
| `file_inventory` | submitter | 16,271 | 16,271 | — | — |
| `anvil_activity` | harmonized | 15,769 | — | — | — |
| `hic` | submitter | 3,002 | 3,002 | assay_type = (no vocabulary term) | `assembly` → reference_assembly; `data_type` → data_type; `instrument_model` → platform; `library_selection` → assay_type; `library_source` → data_modality; `library_strategy` → assay_type; `platform` → platform |
| `hifi` | submitter | 1,069 | 1,596 | platform = PACBIO | `data_type` → data_type; `instrument_model` → platform; `library_selection` → assay_type; `library_source` → data_modality; `library_strategy` → assay_type; `platform` → platform |
| `ont` | submitter | 929 | 929 | platform = ONT | `data_type` → data_type; `instrument_model` → platform; `library_selection` → assay_type; `library_source` → data_modality; `library_strategy` → assay_type; `platform` → platform |
| `deepconsensus` | submitter | 619 | 619 | platform = PACBIO | `data_type` → data_type; `instrument_model` → platform; `library_selection` → assay_type; `library_source` → data_modality; `library_strategy` → assay_type; `platform` → platform |
| `assembly` | submitter | 466 | 1,864 | data_type = assembly | `assembly` → reference_assembly |
| `alignments_winnowmap` | submitter | 462 | 462 | data_type = alignments | — |
| `censat` | submitter | 462 | 462 | data_type = (no vocabulary term) | — |
| `censat_centromeres` | submitter | 462 | 462 | data_type = (no vocabulary term) | — |
| `chains_to_chm13_mc` | submitter | 462 | 462 | data_type = (no vocabulary term); reference_assembly = CHM13 | — |
| `chains_to_grch38_mc` | submitter | 462 | 462 | data_type = (no vocabulary term); reference_assembly = GRCh38 | — |
| `gaps` | submitter | 462 | 462 | data_type = (no vocabulary term) | — |
| `liftoff_genes` | submitter | 462 | 462 | data_type = annotations | — |
| `ont_methylation` | submitter | 462 | 462 | platform = ONT; data_modality = epigenomic.methylation | — |
| `repeat_masker_bed` | submitter | 462 | 462 | data_type = (no vocabulary term) | — |
| `repeat_masker_out` | submitter | 462 | 462 | data_type = (no vocabulary term) | — |
| `segdups` | submitter | 462 | 462 | data_type = (no vocabulary term) | — |
| `t2t_sequences` | submitter | 462 | 462 | data_type = sequence | — |
| `to_ref_chm13_winnowmap` | submitter | 462 | 462 | reference_assembly = CHM13 | — |
| `to_ref_grch38_winnowmap` | submitter | 462 | 462 | reference_assembly = GRCh38 | — |
| `to_ref_grch38_winnowmap_bai` | submitter | 462 | 462 | reference_assembly = GRCh38 | — |
| `anvil_biosample` | harmonized | 234 | — | — | — |
| `anvil_donor` | harmonized | 234 | — | — | — |
| `sample_metadata` | submitter | 234 | 0 | — | — |
| `kinnex` | submitter | 230 | 230 | platform = PACBIO | `data_type` → data_type; `instrument_model` → platform; `library_selection` → assay_type; `library_source` → data_modality; `library_strategy` → assay_type; `platform` → platform |
| `illumina` | submitter | 200 | 200 | platform = ILLUMINA | `instrument_model` → platform; `library_strategy` → assay_type; `platform` → platform |
| `alignments_v2` | submitter | 12 | 12 | data_type = alignments | `reference_coordinates` → reference_assembly |
| `workspace_attributes` | submitter | 8 | 0 | — | — |
| `ingestion_reference` | submitter | 2 | 0 | — | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |

- **`file_inventory`** (16,271 rows): `content_type` 100%, `crc32c` 100%, `datarepo_row_id` 100%, `file_id` 100%, `file_ref` 100%, `full_extension` 100%, `ingest_provenance` 100%, `md5_hash` 100%, `name` 100%, `path` 100%, `size_in_bytes` 100%, `uri` 100%, `version` 100%
- **`hic`** (3,002 rows): `assembly` 100%, `bioproject_accession` 100%, `coverage` 100%, `data_type` 100%, `datarepo_row_id` 100%, `design_description` 100%, `filetype` 100%, `generator_contact` 100%, `generator_facility` 100%, `hic_id` 100%, `ingest_provenance` 100%, `instrument_model` 100%, `library_id` 100%, `library_layout` 100%, `library_selection` 100%, `library_source` 100%, `library_strategy` 100%, `ntsm_score` 100%, `path` 100%, `platform` 100%, `production` 100%, `sample_id` 100%, `shear_method` 100%, `study` 100%, `title` 100%, `total_bp` 100%, `total_gbp` 100%, `version` 100%, `biosample_accession` >99%, `accession` 56%
- **`hifi`** (1,069 rows): `basecaller` 100%, `basecaller_version` 100%, `ccs_algorithm` 100%, `coverage` 100%, `data_type` 100%, `datarepo_row_id` 100%, `design_description` 100%, `filetype` 100%, `generator_contact` 100%, `generator_facility` 100%, `hifi_id` 100%, `ingest_provenance` 100%, `instrument_model` 100%, `library_source` 100%, `library_strategy` 100%, `max` 100%, `mean` 100%, `min` 100%, `mm_remove` 100%, `mm_review` 100%, `mm_tag` 100%, `n25` 100%, `n50` 100%, `n75` 100%, `path` 100%, `platform` 100%, `production` 100%, `quartile_25` 100%, `quartile_50` 100%, `quartile_75` 100%, `sample_id` 100%, `total_bp` 100%, `total_gbp` 100%, `total_reads` 100%, `version` 100%, `bioproject_accession` 96%, `study` 96%, `library_id` 94%, `library_layout` 94%, `library_selection` 94%, `shear_method` 94%, `size_selection` 94%, `accession` 90%, `biosample_accession` 90%, `polymerase_version` 87%, `seq_plate_chemistry_version` 87%, `lima_float_version` 60%, `lima_version` 60%, `deepconsensus_coverage` 49%, `deepconsensus_filename` 49%, `deepconsensus_path` 49%, `ntsm_score` 46%, `primrose_filename` 16%
- **`ont`** (929 rows): `basecaller` 100%, `basecaller_model` 100%, `basecaller_version` 100%, `coverage` 100%, `coverage_over_100kb` 100%, `coverage_over_1mb` 100%, `coverage_over_200kb` 100%, `coverage_over_300kb` 100%, `coverage_over_400kb` 100%, `coverage_over_500kb` 100%, `data_type` 100%, `datarepo_row_id` 100%, `design_description` 100%, `filetype` 100%, `generator_contact` 100%, `generator_facility` 100%, `ingest_provenance` 100%, `instrument_model` 100%, `library_id` 100%, `library_layout` 100%, `library_selection` 100%, `library_source` 100%, `library_strategy` 100%, `n50` 100%, `ont_id` 100%, `path` 100%, `platform` 100%, `production` 100%, `sample_id` 100%, `seq_kit` 100%, `sequencing_chemistry` 100%, `shear_method` 100%, `size_selection` 100%, `total_gbp` 100%, `version` 100%, `whales` 100%, `ntsm_score` >99%, `bioproject_accession` 95%, `study` 95%, `biosample_accession` 86%, `accession` 77%
- **`deepconsensus`** (619 rows): `basecaller` 100%, `basecaller_version` 100%, `coverage` 100%, `data_type` 100%, `datarepo_row_id` 100%, `deepconsensus_id` 100%, `design_description` 100%, `filetype` 100%, `ingest_provenance` 100%, `instrument_model` 100%, `library_layout` 100%, `library_selection` 100%, `library_source` 100%, `library_strategy` 100%, `max` 100%, `mean` 100%, `min` 100%, `n25` 100%, `n50` 100%, `n75` 100%, `path` 100%, `platform` 100%, `production` 100%, `quartile_25` 100%, `quartile_50` 100%, `quartile_75` 100%, `sample_id` 100%, `total_bp` 100%, `total_gbp` 100%, `total_reads` 100%, `version` 100%, `bioproject_accession` 99%, `study` 99%, `biosample_accession` 98%, `generator_contact` 98%, `generator_facility` 98%, `library_id` 98%, `shear_method` 98%, `size_selection` 98%, `title` 98%, `polymerase_version` 77%, `seq_plate_chemistry_version` 77%, `accession` 69%, `ntsm_score` 53%, `notes` 1%
- **`assembly`** (466 rows): `assembly` 100%, `assembly_fai` 100%, `assembly_gzi` 100%, `assembly_id` 100%, `assembly_md5` 100%, `datarepo_row_id` 100%, `genbank_accession` 100%, `haplotype` 100%, `ingest_provenance` 100%, `sample_id` 100%, `source` 100%, `version` 100%, `assembly_date` >99%, `assembly_method` >99%, `assembly_method_version` >99%, `phasing` >99%
- **`alignments_winnowmap`** (462 rows): `alignments_winnowmap_id` 100%, `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `version` 100%
- **`censat`** (462 rows): `censat_id` 100%, `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `version` 100%
- **`censat_centromeres`** (462 rows): `censat_centromeres_id` 100%, `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `version` 100%
- **`chains_to_chm13_mc`** (462 rows): `chains_to_chm13_mc_id` 100%, `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `version` 100%
- **`chains_to_grch38_mc`** (462 rows): `chains_to_grch38_mc_id` 100%, `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `version` 100%
- **`gaps`** (462 rows): `datarepo_row_id` 100%, `gaps_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `version` 100%
- **`liftoff_genes`** (462 rows): `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `liftoff_genes_id` 100%, `location` 100%, `sample_id` 100%, `version` 100%
- **`ont_methylation`** (462 rows): `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `ont_methylation_id` 100%, `sample_id` 100%, `version` 100%
- **`repeat_masker_bed`** (462 rows): `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `repeat_masker_bed_id` 100%, `sample_id` 100%, `version` 100%
- **`repeat_masker_out`** (462 rows): `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `repeat_masker_out_id` 100%, `sample_id` 100%, `version` 100%
- **`segdups`** (462 rows): `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `segdups_id` 100%, `version` 100%
- **`t2t_sequences`** (462 rows): `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `t2t_sequences_id` 100%, `version` 100%
- **`to_ref_chm13_winnowmap`** (462 rows): `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `to_ref_chm13_winnowmap_id` 100%, `version` 100%
- **`to_ref_grch38_winnowmap`** (462 rows): `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `to_ref_grch38_winnowmap_id` 100%, `version` 100%
- **`to_ref_grch38_winnowmap_bai`** (462 rows): `datarepo_row_id` 100%, `haplotype` 100%, `ingest_provenance` 100%, `location` 100%, `sample_id` 100%, `to_ref_grch38_winnowmap_bai_id` 100%, `version` 100%
- **`sample_metadata`** (234 rows): `biosample_id` 100%, `contributors` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `project` 100%, `sample_metadata_id` 100%, `trio_available` 100%, `version` 100%, `sex` 99%, `collection` 99%, `population_abbreviation` 98%, `population_descriptor` 98%, `tissue` 98%, `paternal_id` 56%, `maternal_id` 55%, `family_id` 53%, `alternative_id` 1%, `notes` <1%
- **`kinnex`** (230 rows): `barcode` 100%, `basecaller_version` 100%, `bioproject_accession` 100%, `ccs_algorithm` 100%, `cell_type` 100%, `check_flncreads` 100%, `data_type` 100%, `datarepo_row_id` 100%, `design_description` 100%, `filetype` 100%, `generator_contact` 100%, `generator_facility` 100%, `ingest_provenance` 100%, `instrument_model` 100%, `iso_filename` 100%, `iso_library_id` 100%, `jasmine_version` 100%, `kinnex_id` 100%, `library_id` 100%, `library_layout` 100%, `library_selection` 100%, `library_source` 100%, `library_strategy` 100%, `lima_version` 100%, `ntsm_score` 100%, `path` 100%, `pbtrim_version` 100%, `platform` 100%, `platform_unit_1` 100%, `polymerase_version` 100%, `pool` 100%, `production` 100%, `refine_version` 100%, `sample_id` 100%, `seq_plate_chemistry_version` 100%, `similarity` 100%, `study` 100%, `title` 100%, `total_reads` 100%, `version` 100%, `platform_unit_2` 79%
- **`illumina`** (200 rows): `coverage` 100%, `datarepo_row_id` 100%, `family_id` 100%, `filetype` 100%, `gender` 100%, `illumina_id` 100%, `ingest_provenance` 100%, `instrument_model` 100%, `library_construction_protocol` 100%, `library_layout` 100%, `library_strategy` 100%, `maternal_id` 100%, `other_comments` 100%, `paternal_id` 100%, `path` 100%, `phasing` 100%, `phenotype` 100%, `platform` 100%, `read_length` 100%, `relationship` 100%, `sample_id` 100%, `second_order` 100%, `siblings` 100%, `third_order` 100%, `total_bp` 100%, `total_gbp` 100%, `version` 100%
- **`alignments_v2`** (12 rows): `alignment` 100%, `alignments_v2_id` 100%, `datarepo_row_id` 100%, `file_size` 100%, `filetype` 100%, `hprc_version` 100%, `ingest_provenance` 100%, `location` 100%, `pipeline` 100%, `reference_coordinates` 100%, `version` 100%
- **`workspace_attributes`** (8 rows): `attribute` 100%, `datarepo_row_id` 100%, `ingest_provenance` 100%, `version` 100%, `value` 88%
- **`ingestion_reference`** (2 rows): `datarepo_row_id` 100%, `key` 100%, `value` 100%, `version` 100%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%

### AnVIL_IGVF_Mouse_R1

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 6,786 | — | — | `reference_assembly` → reference_assembly |
| `file` | submitter | 6,786 | 6,786 | — | `assay_titles` → assay_type; `reference_assembly` → reference_assembly; `sequencing_platform` → platform |
| `anvil_biosample` | harmonized | 1,935 | — | — | — |
| `sample` | submitter | 1,935 | 0 | — | — |
| `anvil_activity` | harmonized | 823 | — | — | — |
| `file_set` | submitter | 823 | 0 | — | `assay_term` → assay_type; `assay_titles` → assay_type; `preferred_assay_titles` → assay_type |
| `anvil_donor` | harmonized | 183 | — | — | — |
| `donor` | submitter | 183 | 0 | — | — |
| `ingestion_reference` | submitter | 2 | 0 | — | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |

- **`file`** (6,786 rows): `content_type` 100%, `datarepo_row_id` 100%, `file_format` 100%, `file_id` 100%, `file_md5sum` 100%, `file_name` 100%, `file_path` 100%, `file_set` 100%, `file_size` 100%, `igvf_portal_url` 100%, `summary` 100%, `type` 100%, `version` 100%, `assay_titles` >99%, `sequencing_kit` 59%, `sequencing_platform` 59%, `sequencing_run` 59%, `flowcell_id` 58%, `mean_read_length` 58%, `illumina_read_type` 58%, `seqspecs` 58%, `lane` 56%, `derived_from` 13%, `workflows` 12%, `transcriptome_annotation` 12%, `reference_assembly` 3%, `file_format_type` <1%
- **`sample`** (1,935 rows): `biosample_type` 100%, `datarepo_row_id` 100%, `donors` 100%, `igvf_portal_url` 100%, `sample_id` 100%, `sample_terms` 100%, `summary` 100%, `type` 100%, `version` 100%, `donor_age_at_collection_unit` 84%, `donor_age_at_collection_unit_lower_bound` 84%, `donor_age_at_collection_unit_upper_bound` 84%, `embryonic` 84%, `barcode_map` 16%, `multiplexed_samples` 16%
- **`file_set`** (823 rows): `award` 100%, `datarepo_row_id` 100%, `file_set_id` 100%, `file_set_type` 100%, `files` 100%, `igvf_portal_url` 100%, `lab` 100%, `summary` 100%, `type` 100%, `version` 100%, `samples` 97%, `assay_titles` 97%, `preferred_assay_titles` 97%, `description` 62%, `input_file_sets` 60%, `sample_summary` 60%, `assay_term` 38%, `sequencing_library_types` 37%
- **`donor`** (183 rows): `datarepo_row_id` 100%, `donor_id` 100%, `igvf_portal_url` 100%, `organism_type` 100%, `phenotypic_sex` 100%, `strain` 100%, `strain_background` 100%, `type` 100%, `version` 100%
- **`ingestion_reference`** (2 rows): `datarepo_row_id` 100%, `key` 100%, `value` 100%, `version` 100%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%

### AnVIL_MAGE

| type | origin | rows | files named | name encodes | dimension fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| `anvil_file` | harmonized | 3,285 | — | — | — |
| `file_metadata` | submitter | 3,285 | 3,285 | — | — |
| `anvil_biosample` | harmonized | 1,510 | — | — | — |
| `anvil_activity` | harmonized | 831 | — | — | — |
| `sequencing_library` | submitter | 779 | 3,116 | — | — |
| `kgp_sample` | submitter | 731 | 2,924 | — | — |
| `ingestion_reference` | submitter | 2 | 0 | — | — |
| `anvil_dataset` | harmonized | 1 | — | — | — |
| `anvil_project` | harmonized | 1 | — | — | — |
| `duos_dataset_registration` | submitter | 1 | 0 | — | — |

- **`file_metadata`** (3,285 rows): `content_type` 100%, `datarepo_row_id` 100%, `file_metadata_id` 100%, `file_name` 100%, `file_path` 100%, `md5_hash` 100%, `size_in_bytes` 100%, `version` 100%, `file_extension` 99%
- **`sequencing_library`** (779 rows): `RIN` 100%, `RNAQubitConc_ng_ul` 100%, `RNAQubitTotalAmount_ng` 100%, `SRA_biosample` 100%, `SRA_run` 100%, `bam` 100%, `bam_index` 100%, `continentalGroup` 100%, `coriell_id` 100%, `datarepo_row_id` 100%, `kgp_sample_id` 100%, `numReads` 100%, `population` 100%, `read_1_fastq` 100%, `read_2_fastq` 100%, `sequencing_batch` 100%, `sequencing_library_id` 100%, `sex` 100%, `totalVolume_ul` 100%, `version` 100%
- **`kgp_sample`** (731 rows): `RIN` 100%, `RNAQubitConc_ng_ul` 100%, `RNAQubitTotalAmount_ng` 100%, `SRA_biosample` 100%, `SRA_run` 100%, `bam` 100%, `bam_index` 100%, `continentalGroup` 100%, `coriell_id` 100%, `datarepo_row_id` 100%, `has_replicates` 100%, `kgp_sample_id` 100%, `numReads` 100%, `population` 100%, `read_1_fastq` 100%, `read_2_fastq` 100%, `sequencing_batch` 100%, `sequencing_library_id` 100%, `sex` 100%, `totalVolume_ul` 100%, `version` 100%
- **`ingestion_reference`** (2 rows): `datarepo_row_id` 100%, `key` 100%, `value` 100%, `version` 100%
- **`duos_dataset_registration`** (1 row): `dataset_id` 100%, `description` 100%, `duos_id` 100%, `version` 100%

### Table names the vocabulary cannot express

Tokens in use whose dimension is clear but for which `classification.yaml` has no term. The survey records the dimension and leaves the value null rather than inventing a string, so nothing downstream reads a term the schema does not define. Each of these is a submitter classification #369 would have to either map to an existing term or add one for.

| dimension | tokens in use |
| --- | --- |
| assay_type | `hic` |
| data_type | `censat`, `centromeres`, `chains`, `gaps`, `masker`, `plink`, `repeat`, `segdups` |

## Reach: how many files resolve to a biosample and a donor

Three measurements of one question, per dataset.

- **compact** — the file's own row carries a non-empty `biosamples.biosample_id` / `donors.donor_id`. This is Azul's materialized join.
- **verbatim, single hop** — the file appears in some `anvil_activity`'s `generated_file_id`, and that same activity names a `used_biosample_id`. This is the traversal behind the 9,603 figure #337 recorded for 1000G.
- **verbatim, transitive** — the file is in a connected component of the file/activity graph that contains an activity naming a biosample, where an activity connects every file it used or generated. Undirected, so it is an upper bound; single hop bounds the same quantity from below.

| dataset | files | compact biosample | compact donor | 1-hop biosample | 1-hop donor | transitive biosample | transitive donor |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1000G_PRIMED_data_model | 11,493 | 0 | 0 | 0 | 0 | 0 | 0 |
| 1000G_high_coverage_2019 | 26,016 | 25,616 | 25,616 | 9,603 | 9,603 | 25,616 | 25,616 |
| HPRC | 23,185 | 4,746 | 4,746 | 4,432 | 4,432 | 4,746 | 4,746 |
| NIA_CARD_Coriell_Cell_Lines_Open | 12,534 | 6 | 6 | 0 | 0 | 0 | 0 |
| T2T | 289,204 | 32,020 | 32,020 | 32,020 | 32,020 | 32,020 | 32,020 |
| T2T_CHRY | 309,979 | 0 | 0 | 0 | 0 | 0 | 0 |
| nhp_dGTEx_V1 | 3,591 | 0 | 0 | 0 | 0 | 0 | 0 |
| ENCORE_293T | 1,992 | 1,992 | 1,992 | 1,992 | 1,992 | 1,992 | 1,992 |
| ENCORE_RS293 | 3,752 | 3,752 | 3,752 | 3,752 | 3,752 | 3,752 | 3,752 |
| HPRC_R2 | 16,271 | 14,843 | 14,843 | 14,843 | 14,843 | 14,843 | 14,843 |
| IGVF_Mouse_R1 | 6,786 | 6,757 | 6,757 | 6,757 | 6,757 | 6,757 | 6,757 |
| MAGE | 3,285 | 0 | 0 | 0 | 0 | 0 | 0 |

## Consumer readiness

`yes` at or above 90%, `partial` at or above 10%, `no` below it. Every cell carries the number it was judged on.

- **#369 dimension import** — share of the dataset's verbatim files named by a submitter table that points at a dimension, through its own name (`hifi`, `chains_to_chm13_mc`) or through a populated field named for one (`reference_assembly`, `instrument_model`). The count in brackets says how many of those tables carry it in the name, which is the stronger signal: a name applies to every row, a field only to the rows where it is filled.
- **#336 governance import** — consent group and data use permission, whichever is lower, with the phs accession reported beside it.
- **#361 donor edges** — the compact join's donor reach. The verbatim transitive walk is reported beside it but does not set the verdict: it is an upper bound, and a go/no-go should not rest on one.

| dataset | #369 dimensions | #336 governance | #361 donor edges |
| --- | --- | --- | --- |
| 1000G_PRIMED_data_model | partial (74% of verbatim files, 2 tables (1 by name)) | yes (consent/DUO 100%, phs 0%) | no (0 of 11,493 compact rows (0%), verbatim transitive 0%) |
| 1000G_high_coverage_2019 | partial (37% of verbatim files, 2 tables (0 by name)) | yes (consent/DUO 100%, phs 0%) | yes (25,616 of 26,016 compact rows (98%), verbatim transitive 98%) |
| HPRC | no (6% of verbatim files, 5 tables (5 by name)) | yes (consent/DUO 100%, phs 0%) | partial (4,746 of 23,185 compact rows (20%), verbatim transitive 20%) |
| NIA_CARD_Coriell_Cell_Lines_Open | no (<1% of verbatim files, 1 table (0 by name)) | yes (consent/DUO 100%, phs 100%) | no (6 of 12,534 compact rows (<1%), verbatim transitive 0%) |
| T2T | partial (32% of verbatim files, 1 table (1 by name)) | yes (consent/DUO 100%, phs 0%) | partial (32,020 of 289,204 compact rows (11%), verbatim transitive 11%) |
| T2T_CHRY | yes (>99% of verbatim files, 8 tables (8 by name)) | yes (consent/DUO 100%, phs 0%) | no (0 of 309,979 compact rows (0%), verbatim transitive 0%) |
| nhp_dGTEx_V1 | no (0% of verbatim files, 0 tables (0 by name)) | yes (consent/DUO 100%, phs 0%) | no (0 of 3,591 compact rows (0%), verbatim transitive 0%) |
| ENCORE_293T | yes (100% of verbatim files, 1 table (0 by name)) | yes (consent/DUO 100%, phs 100%) | yes (1,992 of 1,992 compact rows (100%), verbatim transitive 100%) |
| ENCORE_RS293 | yes (100% of verbatim files, 1 table (0 by name)) | yes (consent/DUO 100%, phs 100%) | yes (3,752 of 3,752 compact rows (100%), verbatim transitive 100%) |
| HPRC_R2 | yes (91% of verbatim files, 23 tables (23 by name)) | yes (consent/DUO 100%, phs 0%) | yes (14,843 of 16,271 compact rows (91%), verbatim transitive 91%) |
| IGVF_Mouse_R1 | yes (100% of verbatim files, 2 tables (0 by name)) | yes (consent/DUO 100%, phs 100%) | yes (6,757 of 6,786 compact rows (>99%), verbatim transitive >99%) |
| MAGE | no (0% of verbatim files, 0 tables (0 by name)) | yes (consent/DUO 100%, phs 0%) | no (0 of 3,285 compact rows (0%), verbatim transitive 0%) |

Every dataset supports at least one of the three.

Governance is the flat one: consent group and data use permission are filled on every row of every dataset, so #336 is unblocked corpus-wide and only the phs accession varies.

No dimension-carrying submitter table at all: nhp_dGTEx_V1, MAGE.

Some dimension-carrying tables but under the 10% bar: HPRC, NIA_CARD_Coriell_Cell_Lines_Open.

No donor reachable from either manifest: 1000G_PRIMED_data_model, T2T_CHRY, nhp_dGTEx_V1, MAGE.

Some donors reachable but under the 10% bar: NIA_CARD_Coriell_Cell_Lines_Open.

## Contradictions

Where these measurements disagree with something already written down. Each is re-checked on every run, so one that a later manifest pull resolves stops appearing here rather than lingering as stale prose.

### docs/briefs/comparability-gap.html

**Claimed:** Donor sex, ancestry, biosample type and anatomical site are null on every indexed row.

**Measured:** Not null in the compact manifest: donor sex 18% in ANVIL_HPRC; donor sex <1% in ANVIL_NIA_CARD_Coriell_Cell_Lines_Open; donor sex 11% in ANVIL_T2T; donor sex 100% in AnVIL_ENCORE_293T; donor sex 100% in AnVIL_ENCORE_RS293; donor sex 91% in AnVIL_HPRC_R2; donor sex >99% in AnVIL_IGVF_Mouse_R1; donor ancestry <1% in ANVIL_NIA_CARD_Coriell_Cell_Lines_Open; biosample type <1% in ANVIL_NIA_CARD_Coriell_Cell_Lines_Open; biosample type 91% in AnVIL_HPRC_R2; biosample type >99% in AnVIL_IGVF_Mouse_R1; anatomical site <1% in ANVIL_NIA_CARD_Coriell_Cell_Lines_Open; anatomical site 91% in AnVIL_HPRC_R2; anatomical site >99% in AnVIL_IGVF_Mouse_R1. The brief measured a different extract than these manifests, or an older catalog; it needs scoping to whichever it measured.

### #337 / #368 (azul_manifest docstring), on ANVIL_1000G_high_coverage_2019

**Claimed:** The verbatim entity chain reaches fewer files than the compact join, so verbatim is not a superset of compact.

**Measured:** Single hop reaches 9,603 files, but transitive closure over the same activities reaches 25,616 against the compact join's 25,616. The shortfall is the traversal, not the manifest.

### #337 / #368 (azul_manifest docstring), on ANVIL_HPRC

**Claimed:** The verbatim entity chain reaches fewer files than the compact join, so verbatim is not a superset of compact.

**Measured:** Single hop reaches 4,432 files, but transitive closure over the same activities reaches 4,746 against the compact join's 4,746. The shortfall is the traversal, not the manifest.

### #384 (this issue's own body)

**Claimed:** AnVIL_HPRC_R2 carries ~20 per-file-type tables, each 462 rows.

**Measured:** 8 of them are not 462 rows: hic 3,002, hifi 1,069, ont 929, deepconsensus 619, assembly 466. The tables do not share a row count; 462 is the count of the largest group, not of all of them.

### #384 (this issue's own body)

**Claimed:** AnVIL_HPRC_R2's compact join is 91% for donor and biosample but 23% for activity.

**Measured:** `activities.activity_id` is filled on 91% of its rows, the same share as donor and biosample. Across all 12 datasets 12 fill the three join columns at an identical rate, so the join arrives whole or not at all — which is what #361 should plan against.

