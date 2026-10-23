# Review queue

Source values the slot map or the entity map routed to a slot but that no authored translation rule reads yet, so they make no claim (contract 5.2), by kind of source and then by slot. A value is listed once per source, dataset, table and column it was found in; "rule it would use" names the seeded rule that matches it, or — where none does. For a donor's slot (phenotypic_sex, genetic_ancestry, organism_type, reported_ethnicity), files counts donors, and for a sample's slot (biosample_type), samples, each dataset's identifiers apart. 157 listed, from evidence under data/source_evidence and data/entity_evidence.

## Published: the catalog's published columns

### reference_assembly

| files | raw value | source | dataset | table | column | rule it would use |
| --- | --- | --- | --- | --- | --- | --- |
| 220 | `'["GRCm39"]'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `anvil_file` | `reference_assembly` | — |

### biosample_type

| files | raw value | source | dataset | table | column | rule it would use |
| --- | --- | --- | --- | --- | --- | --- |
| 282 | `'Tissue, Unknown'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `anvil_biosample` | `biosample_type` | — |
| 3 | `'Blood'` | `anvil` | `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open` | `anvil_biosample` | `biosample_type` | — |

## Submitter: the submitter tables

### data_modality

| files | raw value | source | dataset | table | column | rule it would use |
| --- | --- | --- | --- | --- | --- | --- |
| 230 | `'transcriptomic'` | `anvil` | `AnVIL_HPRC_R2` | `kinnex` | `library_source` | data_modality.transcriptomic |

### data_type

| files | raw value | source | dataset | table | column | rule it would use |
| --- | --- | --- | --- | --- | --- | --- |
| 8,562 | `'plink'` | `anvil` | `ANVIL_1000G_PRIMED_data_model` | `plink_file_wide` |  | — |
| 3,959 | `'reads'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `content_type` | — |
| 1,949 | `'seqspec'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `content_type` | — |
| 462 | `'alignments'` | `anvil` | `AnVIL_HPRC_R2` | `alignments_winnowmap` |  | data_type.alignments |
| 462 | `'chains'` | `anvil` | `AnVIL_HPRC_R2` | `chains_to_chm13_mc` |  | data_type.chains |
| 462 | `'chains'` | `anvil` | `AnVIL_HPRC_R2` | `chains_to_grch38_mc` |  | data_type.chains |
| 462 | `'gaps'` | `anvil` | `AnVIL_HPRC_R2` | `gaps` |  | data_type.gaps |
| 462 | `'sequences'` | `anvil` | `AnVIL_HPRC_R2` | `t2t_sequences` |  | data_type.sequences |
| 25 | `'barcode to sample mapping'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `content_type` | — |
| 12 | `'alignments'` | `anvil` | `AnVIL_HPRC_R2` | `alignments_v2` |  | data_type.alignments |
| 11 | `'Nanopore reads'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `content_type` | — |
| 4 | `'barcode onlist'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `content_type` | — |
| 4 | `'index'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `content_type` | — |
| 2 | `'alignments'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `content_type` | data_type.alignments |
| 2 | `'barcode replacement'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `content_type` | — |

### platform

| files | raw value | source | dataset | table | column | rule it would use |
| --- | --- | --- | --- | --- | --- | --- |
| 3 | `'Nanopore_R10'` | `anvil` | `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open` | `sequencing` | `sequencing_platform` | — |
| 3 | `'Nanopore_R9'` | `anvil` | `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open` | `sequencing` | `sequencing_platform` | — |

### reference_assembly

| files | raw value | source | dataset | table | column | rule it would use |
| --- | --- | --- | --- | --- | --- | --- |
| 220 | `'GRCm39'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `reference_assembly` | — |
| 6 | `'hg38, chm13'` | `anvil` | `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open` | `sequencing` | `reference_genome_build` | — |

### assay_type

| files | raw value | source | dataset | table | column | rule it would use |
| --- | --- | --- | --- | --- | --- | --- |
| 230 | `'isoseq'` | `anvil` | `AnVIL_HPRC_R2` | `kinnex` | `library_strategy` | assay_type.isoseq |
| 6 | `'Nanopore'` | `anvil` | `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open` | `sequencing` | `sequencing_strategy` | — |

### genetic_ancestry

| files | raw value | source | dataset | table | column | rule it would use |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `'ASL'` | `anvil` | `AnVIL_HPRC_R2` | `sample_metadata` | `population_abbreviation` | — |
| 1 | `'MKK'` | `anvil` | `AnVIL_HPRC_R2` | `sample_metadata` | `population_abbreviation` | — |

## External: other catalogs

### genetic_ancestry

| files | raw value | source | dataset | table | column | rule it would use |
| --- | --- | --- | --- | --- | --- | --- |
| 15 | `'Papuan'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 4 | `'Dai'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 4 | `'Ju_hoan_North'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 4 | `'Mbuti'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 4 | `'Punjabi'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Dinka'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Even'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Finnish'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'French'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Han'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Japanese'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Jordanian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Karitiana'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Mandenka'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Mixe'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Palestinian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Quechua'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Sardinian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 3 | `'Yoruba'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Abkhasian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Adygei'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Aleut'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Ami'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Armenian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Australian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Balochi'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'BantuHerero'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'BantuKenya'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'BantuTswana'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Basque'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'BedouinB'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Bengali'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Bergamo'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Biaka'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Bougainville'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Brahmin'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Brahui'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Bulgarian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Burmese'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Burusho'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Cambodian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Crete'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Druze'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Dusun'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'English'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Esan'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Eskimo_Naukan'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Eskimo_Sireniki'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Estonian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Gambian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Georgian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Greek'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Hazara'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Hezhen'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Hungarian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Icelandic'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Igorot'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Iranian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Iraqi_Jew'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Irula'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Kalash'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Kapu'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Khomani_San'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Kinh'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Korean'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Kusunda'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Kyrgyz'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Lahu'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Lezgin'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Luhya'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Luo'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Madiga'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Makrani'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Mala'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Mansi'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Masai'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Mayan'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Mende'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Miao'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Mixtec'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Mongola'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Mozabite'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Naxi'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'North_Ossetian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Orcadian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Oroqen'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Pathan'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Piapoco'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Pima'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Relli'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Russian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Saami'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Saharawi'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'She'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Sindhi'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Spanish'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Surui'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Tajik'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Thai'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Tlingit'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Tu'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Tubalar'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Tujia'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Turkish'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Tuscan'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Ulchi'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Uygur'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Xibo'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Yadava'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Yakut'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Yemenite_Jew'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Yi'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 2 | `'Zapotec'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Albanian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Altaian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Atayal'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Chane'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Chechen'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Chukchi'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Czech'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Daur'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Eskimo_Chaplin'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Hawaiian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Itelman'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Khonda_Dora'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Maori'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Norwegian'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Polish'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Samaritan'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |
| 1 | `'Somali'` | `sgdp` |  | `SGDP_metadata` | `Population_ID` | — |

## Authored mappings: what each translation rule declares

Every authored translation rule, by slot and most files first: the source values it matches in that slot, wherever the slot map or the entity map found them, and what it declares. Files are those it matched in the same evidence as the queue above, per kind of source; a row that matched nothing shows 0.

### data_modality

| files | published | submitter | external | rule | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9,603 | 0 | 9,603 | 0 | data_modality.genomic_1000g_high_coverage | `anvil / ANVIL_1000G_high_coverage_2019` | `'GENOMIC'` | nothing (reviewed, no claim) | The `sample` table's `library_source` column, the same SRA value as `data_modality.genomic_hprc_r2`, for the same reason. Measured on run 20260927_225823: none of the 9,603 files it reached depended on it alone for data_modality. |
| 6,962 | 0 | 0 | 6,962 | data_modality.genomic_ena | `ena` | `'GENOMIC'` | nothing (reviewed, no claim) | ENA's `library_source` for a run, the same SRA value as `data_modality.genomic_hprc_r2`, for the same reason: it names the molecule sequenced, not a MODAL modality (#563). A WGS run's modality comes from its `library_strategy` instead (`assay_type.wgs`). |
| 6,733 | 6,733 | 0 | 0 | data_modality.single_nucleus_rna_sequencing_assay | `any` | `['single-nucleus RNA sequencing assay']` | assay_type: snRNA-seq; data_modality: transcriptomic | AnVIL's published `anvil_file.data_modality`, which carries IGVF's assay titles. Single-nucleus RNA sequencing, EFO:0009809 (#533); RNA-seq measures the transcriptome. |
| 5,619 | 0 | 5,619 | 0 | data_modality.genomic_hprc_r2 | `anvil / AnVIL_HPRC_R2` | `'GENOMIC'` | nothing (reviewed, no claim) | The `library_source` column's SRA value. It names the molecule sequenced, not the information measured: SRA files WGS, bisulfite, ATAC, ChIP and Hi-C alike under GENOMIC, because each sequences DNA, so it is no evidence of a MODAL modality (#563). Hi-C arrived under it here (the `hic` table). Scoped to the datasets whose library_source columns carry it: elsewhere the value selects no row, and so enters the review queue rather than being declined unreviewed. Measured on run 20260927_225823: none of the 5,619 files it reached here depended on it alone for data_modality. |
| 462 | 0 | 462 | 0 | data_modality.methylation | `any` | `'methylation'` | data_modality: epigenomic.methylation | The `ont_methylation` table-name span; its files are bigwig methylation tracks. |
| 12 | 12 | 0 | 0 | data_modality.single_nucleus_atac_seq+single_nucleus_rna_sequencing_assay | `anvil / AnVIL_IGVF_Mouse_R1` | `['single-nucleus ATAC-seq', 'single-nucleus RNA sequencing assay']` | assay_type: SHARE-seq | AnVIL's published `anvil_file.data_modality`, which carries IGVF's assay titles. Both assays of one SHARE-seq experiment: IGVF's analysis sets that carry the pair (IGVFDS5339UKYM, IGVFDS5530HYKI) give `preferred_assay_titles: ["SHARE-seq"]`, EFO:0022962. Nothing is declared for data_modality. The value is the analysis set's label, on every file of the set, and each file holds one half: the count matrices and kallisto outputs are RNA, the fragment files ATAC. Any one modality would be wrong for some of them, and the vocabulary holds one per file, so each file's own evidence decides. Scoped to this dataset: the two titles alone do not name the protocol, since another joint assay (10x Multiome for one) could carry the same pair, so elsewhere the value selects no row and is queued. |
| 10 | 10 | 0 | 0 | data_modality.single_nucleus_atac_seq | `any` | `['single-nucleus ATAC-seq']` | assay_type: snATAC-seq; data_modality: epigenomic.chromatin_accessibility | AnVIL's published `anvil_file.data_modality`, which carries IGVF's assay titles. Single-nucleus ATAC-seq: our own term, under EFO's sc/snATAC-seq, which has no single-nucleus child (#533). ATAC-seq measures open chromatin. In AnVIL_IGVF_Mouse_R1 the value is on the reads (FASTQ) and seqspec files of the ATAC half of a SHARE-seq experiment. |

### data_type

| files | published | submitter | external | rule | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4,690 | 0 | 4,690 | 0 | data_type.unaligned_reads | `any` | `'unaligned reads'` | data_type: reads | Reads, as the source says; whether aligned is not the data type. |
| 1,018 | 0 | 1,018 | 0 | data_type.repeat_masker | `any` | `'repeat_masker'` | data_type: annotations | RepeatMasker repeat annotations of an assembly (BED and .out). |
| 881 | 0 | 881 | 0 | data_type.annotation | `any` | `'annotation'` | data_type: annotations | The `assembly_annotation` table-name span; its files are feature annotations of an assembly. |
| 641 | 0 | 641 | 0 | data_type.unaligned_reads_with_5mc_mods | `any` | `'unaligned reads with 5mC mods'` | data_type: reads | Reads carrying base-modification calls; the modification tags do not change the data type. |
| 516 | 0 | 516 | 0 | data_type.sparse_gene_count_matrix | `anvil / AnVIL_IGVF_Mouse_R1` | `'sparse gene count matrix'` | data_type: expression_matrix; data_modality: transcriptomic | IGVF's `file.content_type`. A cell-by-gene count matrix, as IGVF's `summary` on these files says. In AnVIL_IGVF_Mouse_R1 each is RNA: the files titled with snRNA-seq alone, and the two of the SHARE-seq pair (#570), which IGVF derives from the same reads as that experiment's kallisto RNA output. Scoped to this dataset: a gene matrix alone does not say RNA, since one can hold ATAC gene-activity scores. |
| 466 | 0 | 466 | 0 | data_type.assembly | `any` | `'assembly'` | data_type: assembly | The `assembly` table-name span; its files are the de-novo assemblies (.fa.gz). |
| 462 | 0 | 462 | 0 | data_type.censat | `any` | `'censat'` | data_type: annotations | Centromeric satellite annotation tracks (BED) of an assembly. |
| 462 | 0 | 462 | 0 | data_type.censat_centromeres | `any` | `'censat_centromeres'` | data_type: annotations | Centromere annotation tracks (BED) of an assembly. |
| 462 | 0 | 462 | 0 | data_type.liftoff | `any` | `'liftoff'` | data_type: annotations | Gene annotations lifted onto an assembly with Liftoff (GFF3). |
| 462 | 0 | 462 | 0 | data_type.segdups | `any` | `'segdups'` | data_type: annotations | Segmental duplication tracks (BED) of an assembly. |
| 304 | 0 | 304 | 0 | data_type.kallisto_single_cell_rnaseq_output | `anvil / AnVIL_IGVF_Mouse_R1` | `'kallisto single cell RNAseq output'` | data_modality: transcriptomic | IGVF's `file.content_type`. kallisto's single-cell RNA-seq output, as IGVF names it, so RNA. Most of these files are titled snRNA-seq alone, which already says transcriptomic; on the two of the SHARE-seq pair it is what says which half the file holds (#570). Scoped to this dataset, the one whose vocabulary it is. No data_type: the tar is a bundle of kallisto's outputs — the cached tar heads hold, variously, BUS files, `matrix.ec`, `kb_info.json` and cells × genes `.mtx` matrices — not one data type, though IGVF files it as a cell-by-gene `MatrixFile`. |
| 288 | 0 | 288 | 0 | data_type.unaligned_reads_with_5mcg_5hmcg_mods | `any` | `'unaligned reads with 5mCG_5hmCG mods'` | data_type: reads | Reads carrying base-modification calls; the modification tags do not change the data type. |
| 230 | 0 | 230 | 0 | data_type.bam | `any` | `'bam'` | nothing (reviewed, no claim) | A file format, not a data type: the kinnex table's data_type column holds what its filetype column should. Ruled to mean nothing here rather than left queued. |
| 8 | 0 | 8 | 0 | data_type.transcript_quantifications | `anvil / AnVIL_IGVF_Mouse_R1` | `'transcript quantifications'` | data_type: quantification; data_modality: transcriptomic | IGVF's `file.content_type`. Per-transcript abundances quantify RNA. Scoped to this dataset, the one whose vocabulary it is. |
| 2 | 0 | 2 | 0 | data_type.fragments | `anvil / AnVIL_IGVF_Mouse_R1` | `'fragments'` | data_modality: epigenomic.chromatin_accessibility | IGVF's `file.content_type`. A fragment file: one line per transposase-cut fragment, with its cell barcode. In AnVIL_IGVF_Mouse_R1 the two such files are the ATAC half of a SHARE-seq experiment, whose assay_titles pair declares no modality (#570), and ATAC-seq measures open chromatin. Scoped to this dataset: the word names a file layout, which other chromatin assays (CUT&Tag for one) write too, so elsewhere it does not say accessibility. |

### platform

| files | published | submitter | external | rule | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 21,209 | 0 | 14,805 | 6,404 | platform.illumina_novaseq_6000 | `any` | `'Illumina NovaSeq 6000'` | platform: ILLUMINA; instrument_model: Illumina NovaSeq 6000 | An Illumina instrument model, spelled as ENA/SRA's; the model implies the platform. |
| 16,562 | 0 | 9,600 | 6,962 | platform.illumina | `any` | `'ILLUMINA' · 'illumina'` | platform: ILLUMINA | Spelled as our term, as SRA's platform value and as a table-name span. Identity by ruling. |
| 1,688 | 0 | 1,688 | 0 | platform.pacbio_smrt | `any` | `'PACBIO_SMRT'` | platform: PACBIO | SRA's platform value for PacBio. |
| 1,680 | 0 | 1,680 | 0 | platform.illumina_novaseq_x | `any` | `'Illumina NovaSeq X'` | platform: ILLUMINA; instrument_model: Illumina NovaSeq X | An Illumina instrument model, spelled as ENA/SRA's; the model implies the platform. |
| 1,396 | 0 | 1,396 | 0 | platform.illumina_novaseq_6001_to_6698 | `any` | `'Illumina NovaSeq 6001' · 'Illumina NovaSeq 6002' · 'Illumina NovaSeq 6003' · 'Illumina NovaSeq 6004' · 'Illumina NovaSeq 6005' · 'Illumina NovaSeq 6006' · 'Illumina NovaSeq 6007' · 'Illumina NovaSeq 6008' · 'Illumina NovaSeq 6009' · 'Illumina NovaSeq 6010' · 'Illumina NovaSeq 6011' · 'Illumina NovaSeq 6012' · 'Illumina NovaSeq 6013' · 'Illumina NovaSeq 6014' · 'Illumina NovaSeq 6015' · 'Illumina NovaSeq 6016' · 'Illumina NovaSeq 6017' · 'Illumina NovaSeq 6018' · 'Illumina NovaSeq 6019' · 'Illumina NovaSeq 6020' · 'Illumina NovaSeq 6021' · 'Illumina NovaSeq 6022' · 'Illumina NovaSeq 6023' · 'Illumina NovaSeq 6024' · 'Illumina NovaSeq 6025' · 'Illumina NovaSeq 6026' · 'Illumina NovaSeq 6027' · 'Illumina NovaSeq 6028' · 'Illumina NovaSeq 6029' · 'Illumina NovaSeq 6030' · 'Illumina NovaSeq 6031' · 'Illumina NovaSeq 6032' · 'Illumina NovaSeq 6033' · 'Illumina NovaSeq 6034' · 'Illumina NovaSeq 6035' · 'Illumina NovaSeq 6036' · 'Illumina NovaSeq 6037' · 'Illumina NovaSeq 6038' · 'Illumina NovaSeq 6039' · 'Illumina NovaSeq 6040' · 'Illumina NovaSeq 6041' · 'Illumina NovaSeq 6042' · 'Illumina NovaSeq 6043' · 'Illumina NovaSeq 6044' · 'Illumina NovaSeq 6045' · 'Illumina NovaSeq 6046' · 'Illumina NovaSeq 6047' · 'Illumina NovaSeq 6048' · 'Illumina NovaSeq 6049' · 'Illumina NovaSeq 6050' · 'Illumina NovaSeq 6051' · 'Illumina NovaSeq 6052' · 'Illumina NovaSeq 6053' · 'Illumina NovaSeq 6054' · 'Illumina NovaSeq 6055' · 'Illumina NovaSeq 6056' · 'Illumina NovaSeq 6057' · 'Illumina NovaSeq 6058' · 'Illumina NovaSeq 6059' · 'Illumina NovaSeq 6060' · 'Illumina NovaSeq 6061' · 'Illumina NovaSeq 6062' · 'Illumina NovaSeq 6063' · 'Illumina NovaSeq 6064' · 'Illumina NovaSeq 6065' · 'Illumina NovaSeq 6066' · 'Illumina NovaSeq 6067' · 'Illumina NovaSeq 6068' · 'Illumina NovaSeq 6069' · 'Illumina NovaSeq 6070' · 'Illumina NovaSeq 6071' · 'Illumina NovaSeq 6072' · 'Illumina NovaSeq 6073' · 'Illumina NovaSeq 6074' · 'Illumina NovaSeq 6075' · 'Illumina NovaSeq 6076' · 'Illumina NovaSeq 6077' · 'Illumina NovaSeq 6078' · 'Illumina NovaSeq 6079' · 'Illumina NovaSeq 6080' · 'Illumina NovaSeq 6081' · 'Illumina NovaSeq 6082' · 'Illumina NovaSeq 6083' · 'Illumina NovaSeq 6084' · 'Illumina NovaSeq 6085' · 'Illumina NovaSeq 6086' · 'Illumina NovaSeq 6087' · 'Illumina NovaSeq 6088' · 'Illumina NovaSeq 6089' · 'Illumina NovaSeq 6090' · 'Illumina NovaSeq 6091' · 'Illumina NovaSeq 6092' · 'Illumina NovaSeq 6093' · 'Illumina NovaSeq 6094' · 'Illumina NovaSeq 6095' · 'Illumina NovaSeq 6096' · 'Illumina NovaSeq 6097' · 'Illumina NovaSeq 6098' · 'Illumina NovaSeq 6099' · 'Illumina NovaSeq 6100' · 'Illumina NovaSeq 6101' · 'Illumina NovaSeq 6102' · 'Illumina NovaSeq 6103' · 'Illumina NovaSeq 6104' · 'Illumina NovaSeq 6105' · 'Illumina NovaSeq 6106' · 'Illumina NovaSeq 6107' · 'Illumina NovaSeq 6108' · 'Illumina NovaSeq 6109' · 'Illumina NovaSeq 6110' · 'Illumina NovaSeq 6111' · 'Illumina NovaSeq 6112' · 'Illumina NovaSeq 6113' · 'Illumina NovaSeq 6114' · 'Illumina NovaSeq 6115' · 'Illumina NovaSeq 6116' · 'Illumina NovaSeq 6117' · 'Illumina NovaSeq 6118' · 'Illumina NovaSeq 6119' · 'Illumina NovaSeq 6120' · 'Illumina NovaSeq 6121' · 'Illumina NovaSeq 6122' · 'Illumina NovaSeq 6123' · 'Illumina NovaSeq 6124' · 'Illumina NovaSeq 6125' · 'Illumina NovaSeq 6126' · 'Illumina NovaSeq 6127' · 'Illumina NovaSeq 6128' · 'Illumina NovaSeq 6129' · 'Illumina NovaSeq 6130' · 'Illumina NovaSeq 6131' · 'Illumina NovaSeq 6132' · 'Illumina NovaSeq 6133' · 'Illumina NovaSeq 6134' · 'Illumina NovaSeq 6135' · 'Illumina NovaSeq 6136' · 'Illumina NovaSeq 6137' · 'Illumina NovaSeq 6138' · 'Illumina NovaSeq 6139' · 'Illumina NovaSeq 6140' · 'Illumina NovaSeq 6141' · 'Illumina NovaSeq 6142' · 'Illumina NovaSeq 6143' · 'Illumina NovaSeq 6144' · 'Illumina NovaSeq 6145' · 'Illumina NovaSeq 6146' · 'Illumina NovaSeq 6147' · 'Illumina NovaSeq 6148' · 'Illumina NovaSeq 6149' · 'Illumina NovaSeq 6150' · 'Illumina NovaSeq 6151' · 'Illumina NovaSeq 6152' · 'Illumina NovaSeq 6153' · 'Illumina NovaSeq 6154' · 'Illumina NovaSeq 6155' · 'Illumina NovaSeq 6156' · 'Illumina NovaSeq 6157' · 'Illumina NovaSeq 6158' · 'Illumina NovaSeq 6159' · 'Illumina NovaSeq 6160' · 'Illumina NovaSeq 6161' · 'Illumina NovaSeq 6162' · 'Illumina NovaSeq 6163' · 'Illumina NovaSeq 6164' · 'Illumina NovaSeq 6165' · 'Illumina NovaSeq 6166' · 'Illumina NovaSeq 6167' · 'Illumina NovaSeq 6168' · 'Illumina NovaSeq 6169' · 'Illumina NovaSeq 6170' · 'Illumina NovaSeq 6171' · 'Illumina NovaSeq 6172' · 'Illumina NovaSeq 6173' · 'Illumina NovaSeq 6174' · 'Illumina NovaSeq 6175' · 'Illumina NovaSeq 6176' · 'Illumina NovaSeq 6177' · 'Illumina NovaSeq 6178' · 'Illumina NovaSeq 6179' · 'Illumina NovaSeq 6180' · 'Illumina NovaSeq 6181' · 'Illumina NovaSeq 6182' · 'Illumina NovaSeq 6183' · 'Illumina NovaSeq 6184' · 'Illumina NovaSeq 6185' · 'Illumina NovaSeq 6186' · 'Illumina NovaSeq 6187' · 'Illumina NovaSeq 6188' · 'Illumina NovaSeq 6189' · 'Illumina NovaSeq 6190' · 'Illumina NovaSeq 6191' · 'Illumina NovaSeq 6192' · 'Illumina NovaSeq 6193' · 'Illumina NovaSeq 6194' · 'Illumina NovaSeq 6195' · 'Illumina NovaSeq 6196' · 'Illumina NovaSeq 6197' · 'Illumina NovaSeq 6198' · 'Illumina NovaSeq 6199' · 'Illumina NovaSeq 6200' · 'Illumina NovaSeq 6201' · 'Illumina NovaSeq 6202' · 'Illumina NovaSeq 6203' · 'Illumina NovaSeq 6204' · 'Illumina NovaSeq 6205' · 'Illumina NovaSeq 6206' · 'Illumina NovaSeq 6207' · 'Illumina NovaSeq 6208' · 'Illumina NovaSeq 6209' · 'Illumina NovaSeq 6210' · 'Illumina NovaSeq 6211' · 'Illumina NovaSeq 6212' · 'Illumina NovaSeq 6213' · 'Illumina NovaSeq 6214' · 'Illumina NovaSeq 6215' · 'Illumina NovaSeq 6216' · 'Illumina NovaSeq 6217' · 'Illumina NovaSeq 6218' · 'Illumina NovaSeq 6219' · 'Illumina NovaSeq 6220' · 'Illumina NovaSeq 6221' · 'Illumina NovaSeq 6222' · 'Illumina NovaSeq 6223' · 'Illumina NovaSeq 6224' · 'Illumina NovaSeq 6225' · 'Illumina NovaSeq 6226' · 'Illumina NovaSeq 6227' · 'Illumina NovaSeq 6228' · 'Illumina NovaSeq 6229' · 'Illumina NovaSeq 6230' · 'Illumina NovaSeq 6231' · 'Illumina NovaSeq 6232' · 'Illumina NovaSeq 6233' · 'Illumina NovaSeq 6234' · 'Illumina NovaSeq 6235' · 'Illumina NovaSeq 6236' · 'Illumina NovaSeq 6237' · 'Illumina NovaSeq 6238' · 'Illumina NovaSeq 6239' · 'Illumina NovaSeq 6240' · 'Illumina NovaSeq 6241' · 'Illumina NovaSeq 6242' · 'Illumina NovaSeq 6243' · 'Illumina NovaSeq 6244' · 'Illumina NovaSeq 6245' · 'Illumina NovaSeq 6246' · 'Illumina NovaSeq 6247' · 'Illumina NovaSeq 6248' · 'Illumina NovaSeq 6249' · 'Illumina NovaSeq 6250' · 'Illumina NovaSeq 6251' · 'Illumina NovaSeq 6252' · 'Illumina NovaSeq 6253' · 'Illumina NovaSeq 6254' · 'Illumina NovaSeq 6255' · 'Illumina NovaSeq 6256' · 'Illumina NovaSeq 6257' · 'Illumina NovaSeq 6258' · 'Illumina NovaSeq 6259' · 'Illumina NovaSeq 6260' · 'Illumina NovaSeq 6261' · 'Illumina NovaSeq 6262' · 'Illumina NovaSeq 6263' · 'Illumina NovaSeq 6264' · 'Illumina NovaSeq 6265' · 'Illumina NovaSeq 6266' · 'Illumina NovaSeq 6267' · 'Illumina NovaSeq 6268' · 'Illumina NovaSeq 6269' · 'Illumina NovaSeq 6270' · 'Illumina NovaSeq 6271' · 'Illumina NovaSeq 6272' · 'Illumina NovaSeq 6273' · 'Illumina NovaSeq 6274' · 'Illumina NovaSeq 6275' · 'Illumina NovaSeq 6276' · 'Illumina NovaSeq 6277' · 'Illumina NovaSeq 6278' · 'Illumina NovaSeq 6279' · 'Illumina NovaSeq 6280' · 'Illumina NovaSeq 6281' · 'Illumina NovaSeq 6282' · 'Illumina NovaSeq 6283' · 'Illumina NovaSeq 6284' · 'Illumina NovaSeq 6285' · 'Illumina NovaSeq 6286' · 'Illumina NovaSeq 6287' · 'Illumina NovaSeq 6288' · 'Illumina NovaSeq 6289' · 'Illumina NovaSeq 6290' · 'Illumina NovaSeq 6291' · 'Illumina NovaSeq 6292' · 'Illumina NovaSeq 6293' · 'Illumina NovaSeq 6294' · 'Illumina NovaSeq 6295' · 'Illumina NovaSeq 6296' · 'Illumina NovaSeq 6297' · 'Illumina NovaSeq 6298' · 'Illumina NovaSeq 6299' · 'Illumina NovaSeq 6300' · 'Illumina NovaSeq 6301' · 'Illumina NovaSeq 6302' · 'Illumina NovaSeq 6303' · 'Illumina NovaSeq 6304' · 'Illumina NovaSeq 6305' · 'Illumina NovaSeq 6306' · 'Illumina NovaSeq 6307' · 'Illumina NovaSeq 6308' · 'Illumina NovaSeq 6309' · 'Illumina NovaSeq 6310' · 'Illumina NovaSeq 6311' · 'Illumina NovaSeq 6312' · 'Illumina NovaSeq 6313' · 'Illumina NovaSeq 6314' · 'Illumina NovaSeq 6315' · 'Illumina NovaSeq 6316' · 'Illumina NovaSeq 6317' · 'Illumina NovaSeq 6318' · 'Illumina NovaSeq 6319' · 'Illumina NovaSeq 6320' · 'Illumina NovaSeq 6321' · 'Illumina NovaSeq 6322' · 'Illumina NovaSeq 6323' · 'Illumina NovaSeq 6324' · 'Illumina NovaSeq 6325' · 'Illumina NovaSeq 6326' · 'Illumina NovaSeq 6327' · 'Illumina NovaSeq 6328' · 'Illumina NovaSeq 6329' · 'Illumina NovaSeq 6330' · 'Illumina NovaSeq 6331' · 'Illumina NovaSeq 6332' · 'Illumina NovaSeq 6333' · 'Illumina NovaSeq 6334' · 'Illumina NovaSeq 6335' · 'Illumina NovaSeq 6336' · 'Illumina NovaSeq 6337' · 'Illumina NovaSeq 6338' · 'Illumina NovaSeq 6339' · 'Illumina NovaSeq 6340' · 'Illumina NovaSeq 6341' · 'Illumina NovaSeq 6342' · 'Illumina NovaSeq 6343' · 'Illumina NovaSeq 6344' · 'Illumina NovaSeq 6345' · 'Illumina NovaSeq 6346' · 'Illumina NovaSeq 6347' · 'Illumina NovaSeq 6348' · 'Illumina NovaSeq 6349' · 'Illumina NovaSeq 6350' · 'Illumina NovaSeq 6351' · 'Illumina NovaSeq 6352' · 'Illumina NovaSeq 6353' · 'Illumina NovaSeq 6354' · 'Illumina NovaSeq 6355' · 'Illumina NovaSeq 6356' · 'Illumina NovaSeq 6357' · 'Illumina NovaSeq 6358' · 'Illumina NovaSeq 6359' · 'Illumina NovaSeq 6360' · 'Illumina NovaSeq 6361' · 'Illumina NovaSeq 6362' · 'Illumina NovaSeq 6363' · 'Illumina NovaSeq 6364' · 'Illumina NovaSeq 6365' · 'Illumina NovaSeq 6366' · 'Illumina NovaSeq 6367' · 'Illumina NovaSeq 6368' · 'Illumina NovaSeq 6369' · 'Illumina NovaSeq 6370' · 'Illumina NovaSeq 6371' · 'Illumina NovaSeq 6372' · 'Illumina NovaSeq 6373' · 'Illumina NovaSeq 6374' · 'Illumina NovaSeq 6375' · 'Illumina NovaSeq 6376' · 'Illumina NovaSeq 6377' · 'Illumina NovaSeq 6378' · 'Illumina NovaSeq 6379' · 'Illumina NovaSeq 6380' · 'Illumina NovaSeq 6381' · 'Illumina NovaSeq 6382' · 'Illumina NovaSeq 6383' · 'Illumina NovaSeq 6384' · 'Illumina NovaSeq 6385' · 'Illumina NovaSeq 6386' · 'Illumina NovaSeq 6387' · 'Illumina NovaSeq 6388' · 'Illumina NovaSeq 6389' · 'Illumina NovaSeq 6390' · 'Illumina NovaSeq 6391' · 'Illumina NovaSeq 6392' · 'Illumina NovaSeq 6393' · 'Illumina NovaSeq 6394' · 'Illumina NovaSeq 6395' · 'Illumina NovaSeq 6396' · 'Illumina NovaSeq 6397' · 'Illumina NovaSeq 6398' · 'Illumina NovaSeq 6399' · 'Illumina NovaSeq 6400' · 'Illumina NovaSeq 6401' · 'Illumina NovaSeq 6402' · 'Illumina NovaSeq 6403' · 'Illumina NovaSeq 6404' · 'Illumina NovaSeq 6405' · 'Illumina NovaSeq 6406' · 'Illumina NovaSeq 6407' · 'Illumina NovaSeq 6408' · 'Illumina NovaSeq 6409' · 'Illumina NovaSeq 6410' · 'Illumina NovaSeq 6411' · 'Illumina NovaSeq 6412' · 'Illumina NovaSeq 6413' · 'Illumina NovaSeq 6414' · 'Illumina NovaSeq 6415' · 'Illumina NovaSeq 6416' · 'Illumina NovaSeq 6417' · 'Illumina NovaSeq 6418' · 'Illumina NovaSeq 6419' · 'Illumina NovaSeq 6420' · 'Illumina NovaSeq 6421' · 'Illumina NovaSeq 6422' · 'Illumina NovaSeq 6423' · 'Illumina NovaSeq 6424' · 'Illumina NovaSeq 6425' · 'Illumina NovaSeq 6426' · 'Illumina NovaSeq 6427' · 'Illumina NovaSeq 6428' · 'Illumina NovaSeq 6429' · 'Illumina NovaSeq 6430' · 'Illumina NovaSeq 6431' · 'Illumina NovaSeq 6432' · 'Illumina NovaSeq 6433' · 'Illumina NovaSeq 6434' · 'Illumina NovaSeq 6435' · 'Illumina NovaSeq 6436' · 'Illumina NovaSeq 6437' · 'Illumina NovaSeq 6438' · 'Illumina NovaSeq 6439' · 'Illumina NovaSeq 6440' · 'Illumina NovaSeq 6441' · 'Illumina NovaSeq 6442' · 'Illumina NovaSeq 6443' · 'Illumina NovaSeq 6444' · 'Illumina NovaSeq 6445' · 'Illumina NovaSeq 6446' · 'Illumina NovaSeq 6447' · 'Illumina NovaSeq 6448' · 'Illumina NovaSeq 6449' · 'Illumina NovaSeq 6450' · 'Illumina NovaSeq 6451' · 'Illumina NovaSeq 6452' · 'Illumina NovaSeq 6453' · 'Illumina NovaSeq 6454' · 'Illumina NovaSeq 6455' · 'Illumina NovaSeq 6456' · 'Illumina NovaSeq 6457' · 'Illumina NovaSeq 6458' · 'Illumina NovaSeq 6459' · 'Illumina NovaSeq 6460' · 'Illumina NovaSeq 6461' · 'Illumina NovaSeq 6462' · 'Illumina NovaSeq 6463' · 'Illumina NovaSeq 6464' · 'Illumina NovaSeq 6465' · 'Illumina NovaSeq 6466' · 'Illumina NovaSeq 6467' · 'Illumina NovaSeq 6468' · 'Illumina NovaSeq 6469' · 'Illumina NovaSeq 6470' · 'Illumina NovaSeq 6471' · 'Illumina NovaSeq 6472' · 'Illumina NovaSeq 6473' · 'Illumina NovaSeq 6474' · 'Illumina NovaSeq 6475' · 'Illumina NovaSeq 6476' · 'Illumina NovaSeq 6477' · 'Illumina NovaSeq 6478' · 'Illumina NovaSeq 6479' · 'Illumina NovaSeq 6480' · 'Illumina NovaSeq 6481' · 'Illumina NovaSeq 6482' · 'Illumina NovaSeq 6483' · 'Illumina NovaSeq 6484' · 'Illumina NovaSeq 6485' · 'Illumina NovaSeq 6486' · 'Illumina NovaSeq 6487' · 'Illumina NovaSeq 6488' · 'Illumina NovaSeq 6489' · 'Illumina NovaSeq 6490' · 'Illumina NovaSeq 6491' · 'Illumina NovaSeq 6492' · 'Illumina NovaSeq 6493' · 'Illumina NovaSeq 6494' · 'Illumina NovaSeq 6495' · 'Illumina NovaSeq 6496' · 'Illumina NovaSeq 6497' · 'Illumina NovaSeq 6498' · 'Illumina NovaSeq 6499' · 'Illumina NovaSeq 6500' · 'Illumina NovaSeq 6501' · 'Illumina NovaSeq 6502' · 'Illumina NovaSeq 6503' · 'Illumina NovaSeq 6504' · 'Illumina NovaSeq 6505' · 'Illumina NovaSeq 6506' · 'Illumina NovaSeq 6507' · 'Illumina NovaSeq 6508' · 'Illumina NovaSeq 6509' · 'Illumina NovaSeq 6510' · 'Illumina NovaSeq 6511' · 'Illumina NovaSeq 6512' · 'Illumina NovaSeq 6513' · 'Illumina NovaSeq 6514' · 'Illumina NovaSeq 6515' · 'Illumina NovaSeq 6516' · 'Illumina NovaSeq 6517' · 'Illumina NovaSeq 6518' · 'Illumina NovaSeq 6519' · 'Illumina NovaSeq 6520' · 'Illumina NovaSeq 6521' · 'Illumina NovaSeq 6522' · 'Illumina NovaSeq 6523' · 'Illumina NovaSeq 6524' · 'Illumina NovaSeq 6525' · 'Illumina NovaSeq 6526' · 'Illumina NovaSeq 6527' · 'Illumina NovaSeq 6528' · 'Illumina NovaSeq 6529' · 'Illumina NovaSeq 6530' · 'Illumina NovaSeq 6531' · 'Illumina NovaSeq 6532' · 'Illumina NovaSeq 6533' · 'Illumina NovaSeq 6534' · 'Illumina NovaSeq 6535' · 'Illumina NovaSeq 6536' · 'Illumina NovaSeq 6537' · 'Illumina NovaSeq 6538' · 'Illumina NovaSeq 6539' · 'Illumina NovaSeq 6540' · 'Illumina NovaSeq 6541' · 'Illumina NovaSeq 6542' · 'Illumina NovaSeq 6543' · 'Illumina NovaSeq 6544' · 'Illumina NovaSeq 6545' · 'Illumina NovaSeq 6546' · 'Illumina NovaSeq 6547' · 'Illumina NovaSeq 6548' · 'Illumina NovaSeq 6549' · 'Illumina NovaSeq 6550' · 'Illumina NovaSeq 6551' · 'Illumina NovaSeq 6552' · 'Illumina NovaSeq 6553' · 'Illumina NovaSeq 6554' · 'Illumina NovaSeq 6555' · 'Illumina NovaSeq 6556' · 'Illumina NovaSeq 6557' · 'Illumina NovaSeq 6558' · 'Illumina NovaSeq 6559' · 'Illumina NovaSeq 6560' · 'Illumina NovaSeq 6561' · 'Illumina NovaSeq 6562' · 'Illumina NovaSeq 6563' · 'Illumina NovaSeq 6564' · 'Illumina NovaSeq 6565' · 'Illumina NovaSeq 6566' · 'Illumina NovaSeq 6567' · 'Illumina NovaSeq 6568' · 'Illumina NovaSeq 6569' · 'Illumina NovaSeq 6570' · 'Illumina NovaSeq 6571' · 'Illumina NovaSeq 6572' · 'Illumina NovaSeq 6573' · 'Illumina NovaSeq 6574' · 'Illumina NovaSeq 6575' · 'Illumina NovaSeq 6576' · 'Illumina NovaSeq 6577' · 'Illumina NovaSeq 6578' · 'Illumina NovaSeq 6579' · 'Illumina NovaSeq 6580' · 'Illumina NovaSeq 6581' · 'Illumina NovaSeq 6582' · 'Illumina NovaSeq 6583' · 'Illumina NovaSeq 6584' · 'Illumina NovaSeq 6585' · 'Illumina NovaSeq 6586' · 'Illumina NovaSeq 6587' · 'Illumina NovaSeq 6588' · 'Illumina NovaSeq 6589' · 'Illumina NovaSeq 6590' · 'Illumina NovaSeq 6591' · 'Illumina NovaSeq 6592' · 'Illumina NovaSeq 6593' · 'Illumina NovaSeq 6594' · 'Illumina NovaSeq 6595' · 'Illumina NovaSeq 6596' · 'Illumina NovaSeq 6597' · 'Illumina NovaSeq 6598' · 'Illumina NovaSeq 6599' · 'Illumina NovaSeq 6600' · 'Illumina NovaSeq 6601' · 'Illumina NovaSeq 6602' · 'Illumina NovaSeq 6603' · 'Illumina NovaSeq 6604' · 'Illumina NovaSeq 6605' · 'Illumina NovaSeq 6606' · 'Illumina NovaSeq 6607' · 'Illumina NovaSeq 6608' · 'Illumina NovaSeq 6609' · 'Illumina NovaSeq 6610' · 'Illumina NovaSeq 6611' · 'Illumina NovaSeq 6612' · 'Illumina NovaSeq 6613' · 'Illumina NovaSeq 6614' · 'Illumina NovaSeq 6615' · 'Illumina NovaSeq 6616' · 'Illumina NovaSeq 6617' · 'Illumina NovaSeq 6618' · 'Illumina NovaSeq 6619' · 'Illumina NovaSeq 6620' · 'Illumina NovaSeq 6621' · 'Illumina NovaSeq 6622' · 'Illumina NovaSeq 6623' · 'Illumina NovaSeq 6624' · 'Illumina NovaSeq 6625' · 'Illumina NovaSeq 6626' · 'Illumina NovaSeq 6627' · 'Illumina NovaSeq 6628' · 'Illumina NovaSeq 6629' · 'Illumina NovaSeq 6630' · 'Illumina NovaSeq 6631' · 'Illumina NovaSeq 6632' · 'Illumina NovaSeq 6633' · 'Illumina NovaSeq 6634' · 'Illumina NovaSeq 6635' · 'Illumina NovaSeq 6636' · 'Illumina NovaSeq 6637' · 'Illumina NovaSeq 6638' · 'Illumina NovaSeq 6639' · 'Illumina NovaSeq 6640' · 'Illumina NovaSeq 6641' · 'Illumina NovaSeq 6642' · 'Illumina NovaSeq 6643' · 'Illumina NovaSeq 6644' · 'Illumina NovaSeq 6645' · 'Illumina NovaSeq 6646' · 'Illumina NovaSeq 6647' · 'Illumina NovaSeq 6648' · 'Illumina NovaSeq 6649' · 'Illumina NovaSeq 6650' · 'Illumina NovaSeq 6651' · 'Illumina NovaSeq 6652' · 'Illumina NovaSeq 6653' · 'Illumina NovaSeq 6654' · 'Illumina NovaSeq 6655' · 'Illumina NovaSeq 6656' · 'Illumina NovaSeq 6657' · 'Illumina NovaSeq 6658' · 'Illumina NovaSeq 6659' · 'Illumina NovaSeq 6660' · 'Illumina NovaSeq 6661' · 'Illumina NovaSeq 6662' · 'Illumina NovaSeq 6663' · 'Illumina NovaSeq 6664' · 'Illumina NovaSeq 6665' · 'Illumina NovaSeq 6666' · 'Illumina NovaSeq 6667' · 'Illumina NovaSeq 6668' · 'Illumina NovaSeq 6669' · 'Illumina NovaSeq 6670' · 'Illumina NovaSeq 6671' · 'Illumina NovaSeq 6672' · 'Illumina NovaSeq 6673' · 'Illumina NovaSeq 6674' · 'Illumina NovaSeq 6675' · 'Illumina NovaSeq 6676' · 'Illumina NovaSeq 6677' · 'Illumina NovaSeq 6678' · 'Illumina NovaSeq 6679' · 'Illumina NovaSeq 6680' · 'Illumina NovaSeq 6681' · 'Illumina NovaSeq 6682' · 'Illumina NovaSeq 6683' · 'Illumina NovaSeq 6684' · 'Illumina NovaSeq 6685' · 'Illumina NovaSeq 6686' · 'Illumina NovaSeq 6687' · 'Illumina NovaSeq 6688' · 'Illumina NovaSeq 6689' · 'Illumina NovaSeq 6690' · 'Illumina NovaSeq 6691' · 'Illumina NovaSeq 6692' · 'Illumina NovaSeq 6693' · 'Illumina NovaSeq 6694' · 'Illumina NovaSeq 6695' · 'Illumina NovaSeq 6696' · 'Illumina NovaSeq 6697' · 'Illumina NovaSeq 6698'` | platform: ILLUMINA | Every number from 6001 to 6698 in 1000G's participant.instrument_model, two files each, beside 14,605 lines of `Illumina NovaSeq 6000`. They look like a spreadsheet fill series run down from that value; no such models exist. The vendor is certain, so platform is declared. The model most likely is the NovaSeq 6000, but that is a guess, so instrument_model is not (#532). The correction belongs at the source. |
| 1,391 | 0 | 1,391 | 0 | platform.ont | `any` | `'ont'` | platform: ONT | Spelled as our term, as a table-name span. Identity by ruling. |
| 1,292 | 0 | 1,292 | 0 | platform.hifi | `any` | `'hifi'` | platform: PACBIO | HiFi reads are PacBio's; the span says platform only and implies no assay (#430). |
| 1,235 | 0 | 1,235 | 0 | platform.sequel_ii | `any` | `'Sequel II'` | platform: PACBIO; instrument_model: Sequel II | A PacBio instrument, spelled as ENA/SRA's model. |
| 929 | 0 | 929 | 0 | platform.oxford_nanopore | `any` | `'OXFORD_NANOPORE'` | platform: ONT | SRA's platform value for Oxford Nanopore. |
| 925 | 0 | 925 | 0 | platform.promethion | `any` | `'PromethION'` | platform: ONT; instrument_model: PromethION | An Oxford Nanopore instrument, spelled as ENA/SRA's model. |
| 683 | 0 | 683 | 0 | platform.revio | `any` | `'Revio' · 'REVIO'` | platform: PACBIO; instrument_model: Revio | A PacBio instrument, spelled as ENA/SRA's model; the kinnex table spells it in capitals. |
| 619 | 0 | 619 | 0 | platform.deepconsensus | `any` | `'deepconsensus'` | platform: PACBIO | DeepConsensus is PacBio's HiFi read-polishing method; the span names PacBio data. Platform only. |
| 558 | 0 | 0 | 558 | platform.illumina_hiseq_2000 | `any` | `'Illumina HiSeq 2000'` | platform: ILLUMINA; instrument_model: Illumina HiSeq 2000 | An Illumina instrument model, spelled as ENA/SRA's; the model implies the platform. |
| 268 | 0 | 268 | 0 | platform.illumina_nextseq_2000 | `any` | `'Illumina NextSeq 2000'` | platform: ILLUMINA; instrument_model: NextSeq 2000 | An Illumina instrument model; ENA/SRA spells it without the vendor, as `NextSeq 2000`. |
| 230 | 0 | 230 | 0 | platform.kinnex | `any` | `'kinnex'` | platform: PACBIO | Kinnex is a PacBio library kit; the span names PacBio data. Platform only. |
| 230 | 0 | 230 | 0 | platform.pacbio | `any` | `'PACBIO'` | platform: PACBIO | Spelled as our term (the kinnex table's spelling). Identity by ruling. |
| 120 | 0 | 120 | 0 | platform.nanopore | `any` | `'nanopore'` | platform: ONT | A column-name span naming Oxford Nanopore data. |
| 20 | 0 | 20 | 0 | platform.ont_gridion_x5 | `any` | `'ONT GridION X5'` | platform: ONT; instrument_model: GridION | The GridION X5, ONT's GridION with five flow-cell positions. ENA/SRA has one GridION model and no separate X5, so the model is GridION. |
| 2 | 0 | 2 | 0 | platform.gridion | `any` | `'GridION'` | platform: ONT; instrument_model: GridION | An Oxford Nanopore instrument, spelled as ENA/SRA's model. |
| 2 | 0 | 2 | 0 | platform.minion | `any` | `'MinION'` | platform: ONT; instrument_model: MinION | An Oxford Nanopore instrument, spelled as ENA/SRA's model. |
| 2 | 0 | 2 | 0 | platform.ont_promethion_2_solo | `any` | `'ONT PromethION 2 Solo'` | platform: ONT; instrument_model: PromethION | The PromethION 2 Solo, a two-flow-cell PromethION device. ENA/SRA has one PromethION model and no separate P2 Solo, so the model is PromethION. |

### reference_assembly

| files | published | submitter | external | rule | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 262,595 | 0 | 262,595 | 0 | reference_assembly.chm13v2 | `any` | `'CHM13v2'` | reference_assembly: T2T-CHM13v2.0 | The submitter's name for NCBI's T2T-CHM13v2.0, in the ANVIL_T2T_CHRY table names; `v2` names the release (#473). |
| 48,055 | 0 | 48,055 | 0 | reference_assembly.grch38 | `any` | `'grch38' · 'hg38'` | reference_assembly: GRCh38 | Column-name spans naming the GRCh38 assembly; hg38 is UCSC's name for the same assembly. |
| 8,952 | 4,476 | 4,476 | 0 | reference_assembly.grch38_gencode40 | `any` | `'GRCh38 + Gencode40'` | reference_assembly: GRCh38 | GRCh38 with a GENCODE annotation release. The annotation is not part of the assembly and does not imply a patch, so the assembly is GRCh38 (#473). |
| 3,002 | 0 | 3,002 | 0 | reference_assembly.unaligned | `any` | `'unaligned'` | reference_assembly: not_applicable | The source's word for a file with no reference; the slot does not apply. |
| 816 | 0 | 816 | 0 | reference_assembly.chm13 | `any` | `'chm13'` | reference_assembly: CHM13 | Names CHM13 and no release, so it is the release-unknown term (#473). |
| 0 | 0 | 0 | 0 | reference_assembly.chm13_v1_0_grch38_chry | `any` | `'t2t-chm13.20200921.withGRCh38chrY.chrEBV.chrYKI270740v1r' · 'chm13.draft_v1.0_plus38Y'` | reference_assembly: t2t-chm13.20200921.withGRCh38chrY.chrEBV.chrYKI270740v1r | The term itself, and the T2T 1KGP files' own label for the same reference: CHM13 v1.0 with GRCh38's chrY (#473). |
| 0 | 0 | 0 | 0 | reference_assembly.chm13_v1_0_hg002_chry | `any` | `'t2t-chm13.20200921.HG002chrY.chrEBV'` | reference_assembly: t2t-chm13.20200921.HG002chrY.chrEBV | The term itself, CHM13 v1.0 with HG002's chrY (#473). |
| 0 | 0 | 0 | 0 | reference_assembly.chm13_v1_1_grch38_chry | `any` | `'CHM13Y_EBV_v1.1'` | reference_assembly: CHM13Y_EBV_v1.1 | The term itself, CHM13 v1.1 with GRCh38's chrY (#473). |

### assay_type

| files | published | submitter | external | rule | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 31,805 | 0 | 24,843 | 6,962 | assay_type.wgs | `any` | `'WGS'` | assay_type: WGS; data_modality: genomic | Whole-genome sequencing, spelled as our term; a WGS library is genomic DNA. |
| 6,733 | 0 | 6,733 | 0 | assay_type.single_nucleus_rna_sequencing_assay | `any` | `['single-nucleus RNA sequencing assay']` | assay_type: snRNA-seq; data_modality: transcriptomic | IGVF's `file.assay_titles`. Single-nucleus RNA sequencing, EFO:0009809 (#533); RNA-seq measures the transcriptome. |
| 3,770 | 0 | 3,770 | 0 | assay_type.hi_c | `any` | `'Hi-C' · 'hic'` | data_modality: epigenomic.3d_contact_maps | Hi-C measures chromatin contacts, which MODAL's `3D contact maps` names (#563); the modality is the information measured, not the use HPRC puts it to (scaffolding). The vocabulary has no assay term for it yet (#399), so nothing is declared for assay_type. `hic` is the table-name span of the same data. |
| 12 | 0 | 12 | 0 | assay_type.single_nucleus_atac_seq+single_nucleus_rna_sequencing_assay | `anvil / AnVIL_IGVF_Mouse_R1` | `['single-nucleus ATAC-seq', 'single-nucleus RNA sequencing assay']` | assay_type: SHARE-seq | IGVF's `file.assay_titles`. Both assays of one SHARE-seq experiment: IGVF's analysis sets that carry the pair (IGVFDS5339UKYM, IGVFDS5530HYKI) give `preferred_assay_titles: ["SHARE-seq"]`, EFO:0022962. Nothing is declared for data_modality. The value is the analysis set's label, on every file of the set, and each file holds one half: the count matrices and kallisto outputs are RNA, the fragment files ATAC. Any one modality would be wrong for some of them, and the vocabulary holds one per file, so each file's own evidence decides. Scoped to this dataset: the two titles alone do not name the protocol, since another joint assay (10x Multiome for one) could carry the same pair, so elsewhere the value selects no row and is queued. |
| 10 | 0 | 10 | 0 | assay_type.single_nucleus_atac_seq | `any` | `['single-nucleus ATAC-seq']` | assay_type: snATAC-seq; data_modality: epigenomic.chromatin_accessibility | IGVF's `file.assay_titles`. Single-nucleus ATAC-seq: our own term, under EFO's sc/snATAC-seq, which has no single-nucleus child (#533). ATAC-seq measures open chromatin. In AnVIL_IGVF_Mouse_R1 the value is on the reads (FASTQ) and seqspec files of the ATAC half of a SHARE-seq experiment. |

### phenotypic_sex

| files | published | submitter | external | rule | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5,293 | 1,845 | 3,448 | 0 | phenotypic_sex.female | `any` | `'female'` | phenotypic_sex: Female | The term itself, as T2T, HPRC and NIA_CARD write it lower case and PRIMED and AnVIL capitalised. |
| 5,243 | 1,822 | 3,421 | 0 | phenotypic_sex.male | `any` | `'male'` | phenotypic_sex: Male | The term itself, as T2T, HPRC and NIA_CARD write it lower case and PRIMED and AnVIL capitalised. |
| 1,603 | 0 | 1,603 | 0 | phenotypic_sex.pedigree_2 | `anvil / ANVIL_1000G_high_coverage_2019` | `'2'` | phenotypic_sex: Female | 1000 Genomes' `pedigree.sex` is a PED file's sex column, where 1 is male and 2 female; scoped to the dataset, since a bare `2` means this only in a PED file. |
| 1,599 | 0 | 1,599 | 0 | phenotypic_sex.pedigree_1 | `anvil / ANVIL_1000G_high_coverage_2019` | `'1'` | phenotypic_sex: Male | 1000 Genomes' `pedigree.sex` is a PED file's sex column, where 1 is male and 2 female; scoped to the dataset, since a bare `1` means this only in a PED file. |
| 175 | 0 | 0 | 175 | phenotypic_sex.sgdp_m | `sgdp` | `'M'` | phenotypic_sex: Male | SGDP's metadata file writes a genome's sex in `Gender` as M, F or U (not known); scoped to SGDP, since a bare `M` means male only there (#559). |
| 101 | 0 | 0 | 101 | phenotypic_sex.sgdp_f | `sgdp` | `'F'` | phenotypic_sex: Female | SGDP's metadata file writes a genome's sex in `Gender` as M, F or U (not known); scoped to SGDP, since a bare `F` means female only there (#559). |
| 2 | 0 | 0 | 2 | phenotypic_sex.sgdp_u | `sgdp` | `'U'` | nothing (reviewed, no claim) | SGDP's `U` is "not known": reviewed, and no claim. Two genomes linked by their genotypes (#718), S_Norwegian-1 and B_Australian-3, have it. |

### genetic_ancestry

| files | published | submitter | external | rule | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 893 | 0 | 893 | 0 | genetic_ancestry.afr | `any` | `'AFR'` | genetic_ancestry: AFR | 1000 Genomes' superpopulation code, the term itself (HANCESTRO:2000). |
| 633 | 0 | 633 | 0 | genetic_ancestry.eur | `any` | `'EUR'` | genetic_ancestry: EUR | 1000 Genomes' superpopulation code, the term itself (HANCESTRO:2003). |
| 601 | 0 | 601 | 0 | genetic_ancestry.sas | `any` | `'SAS'` | genetic_ancestry: SAS | 1000 Genomes' superpopulation code, the term itself (HANCESTRO:2004). |
| 587 | 0 | 587 | 0 | genetic_ancestry.gwd | `any` | `'GWD' · 'GWD \| AFR'` | genetic_ancestry: GWD | 1000 Genomes' population code, the term itself (HANCESTRO:0664); PRIMED's `population_label` writes it with its superpopulation, `GWD \| AFR`, which the term sits under. |
| 585 | 0 | 585 | 0 | genetic_ancestry.eas | `any` | `'EAS'` | genetic_ancestry: EAS | 1000 Genomes' superpopulation code, the term itself (HANCESTRO:2002). |
| 572 | 0 | 572 | 0 | genetic_ancestry.yri | `any` | `'YRI' · 'YRI \| AFR'` | genetic_ancestry: YRI | 1000 Genomes' population code, the term itself (HANCESTRO:0668); PRIMED's `population_label` writes it with its superpopulation, `YRI \| AFR`, which the term sits under. |
| 567 | 0 | 567 | 0 | genetic_ancestry.ceu | `any` | `'CEU' · 'CEU \| EUR'` | genetic_ancestry: CEU | 1000 Genomes' population code, the term itself (HANCESTRO:0766); PRIMED's `population_label` writes it with its superpopulation, `CEU \| EUR`, which the term sits under. |
| 531 | 0 | 531 | 0 | genetic_ancestry.chs | `any` | `'CHS' · 'CHS \| EAS'` | genetic_ancestry: CHS | 1000 Genomes' population code, the term itself (HANCESTRO:0756); PRIMED's `population_label` writes it with its superpopulation, `CHS \| EAS`, which the term sits under. |
| 502 | 0 | 502 | 0 | genetic_ancestry.ibs | `any` | `'IBS' · 'IBS \| EUR'` | genetic_ancestry: IBS | 1000 Genomes' population code, the term itself (HANCESTRO:0768); PRIMED's `population_label` writes it with its superpopulation, `IBS \| EUR`, which the term sits under. |
| 490 | 0 | 490 | 0 | genetic_ancestry.amr | `any` | `'AMR'` | genetic_ancestry: AMR | 1000 Genomes' superpopulation code, the term itself (HANCESTRO:2001). |
| 486 | 0 | 486 | 0 | genetic_ancestry.esn | `any` | `'ESN' · 'ESN \| AFR'` | genetic_ancestry: ESN | 1000 Genomes' population code, the term itself (HANCESTRO:0661); PRIMED's `population_label` writes it with its superpopulation, `ESN \| AFR`, which the term sits under. |
| 477 | 0 | 477 | 0 | genetic_ancestry.pjl | `any` | `'PJL' · 'PJL \| SAS'` | genetic_ancestry: PJL | 1000 Genomes' population code, the term itself (HANCESTRO:0804); PRIMED's `population_label` writes it with its superpopulation, `PJL \| SAS`, which the term sits under. |
| 469 | 0 | 469 | 0 | genetic_ancestry.pur | `any` | `'PUR' · 'PUR \| AMR'` | genetic_ancestry: PUR | 1000 Genomes' population code, the term itself (HANCESTRO:0687); PRIMED's `population_label` writes it with its superpopulation, `PUR \| AMR`, which the term sits under. |
| 439 | 0 | 439 | 0 | genetic_ancestry.clm | `any` | `'CLM' · 'CLM \| AMR'` | genetic_ancestry: CLM | 1000 Genomes' population code, the term itself (HANCESTRO:0684); PRIMED's `population_label` writes it with its superpopulation, `CLM \| AMR`, which the term sits under. |
| 431 | 0 | 431 | 0 | genetic_ancestry.beb | `any` | `'BEB' · 'BEB \| SAS'` | genetic_ancestry: BEB | 1000 Genomes' population code, the term itself (HANCESTRO:0802); PRIMED's `population_label` writes it with its superpopulation, `BEB \| SAS`, which the term sits under. |
| 413 | 0 | 413 | 0 | genetic_ancestry.pel | `any` | `'PEL' · 'PEL \| AMR'` | genetic_ancestry: PEL | 1000 Genomes' population code, the term itself (HANCESTRO:0686); PRIMED's `population_label` writes it with its superpopulation, `PEL \| AMR`, which the term sits under. |
| 408 | 0 | 408 | 0 | genetic_ancestry.khv | `any` | `'KHV' · 'KHV \| EAS'` | genetic_ancestry: KHV | 1000 Genomes' population code, the term itself (HANCESTRO:0755); PRIMED's `population_label` writes it with its superpopulation, `KHV \| EAS`, which the term sits under. |
| 395 | 0 | 395 | 0 | genetic_ancestry.acb | `any` | `'ACB' · 'ACB \| AFR'` | genetic_ancestry: ACB | 1000 Genomes' population code, the term itself (HANCESTRO:0660); PRIMED's `population_label` writes it with its superpopulation, `ACB \| AFR`, which the term sits under. |
| 375 | 0 | 375 | 0 | genetic_ancestry.stu | `any` | `'STU' · 'STU \| SAS'` | genetic_ancestry: STU | 1000 Genomes' population code, the term itself (HANCESTRO:0805); PRIMED's `population_label` writes it with its superpopulation, `STU \| SAS`, which the term sits under. |
| 357 | 0 | 357 | 0 | genetic_ancestry.tsi | `any` | `'TSI' · 'TSI \| EUR'` | genetic_ancestry: TSI | 1000 Genomes' population code, the term itself (HANCESTRO:0769); PRIMED's `population_label` writes it with its superpopulation, `TSI \| EUR`, which the term sits under. |
| 356 | 0 | 356 | 0 | genetic_ancestry.jpt | `any` | `'JPT' · 'JPT \| EAS'` | genetic_ancestry: JPT | 1000 Genomes' population code, the term itself (HANCESTRO:0754); PRIMED's `population_label` writes it with its superpopulation, `JPT \| EAS`, which the term sits under. |
| 352 | 0 | 352 | 0 | genetic_ancestry.itu | `any` | `'ITU' · 'ITU \| SAS'` | genetic_ancestry: ITU | 1000 Genomes' population code, the term itself (HANCESTRO:0806); PRIMED's `population_label` writes it with its superpopulation, `ITU \| SAS`, which the term sits under. |
| 344 | 0 | 344 | 0 | genetic_ancestry.gih | `any` | `'GIH' · 'GIH \| SAS'` | genetic_ancestry: GIH | 1000 Genomes' population code, the term itself (HANCESTRO:0803); PRIMED's `population_label` writes it with its superpopulation, `GIH \| SAS`, which the term sits under. |
| 342 | 0 | 342 | 0 | genetic_ancestry.chb | `any` | `'CHB' · 'CHB \| EAS'` | genetic_ancestry: CHB | 1000 Genomes' population code, the term itself (HANCESTRO:0753); PRIMED's `population_label` writes it with its superpopulation, `CHB \| EAS`, which the term sits under. |
| 338 | 0 | 338 | 0 | genetic_ancestry.msl | `any` | `'MSL' · 'MSL \| AFR'` | genetic_ancestry: MSL | 1000 Genomes' population code, the term itself (HANCESTRO:0667); PRIMED's `population_label` writes it with its superpopulation, `MSL \| AFR`, which the term sits under. |
| 334 | 0 | 334 | 0 | genetic_ancestry.fin | `any` | `'FIN' · 'FIN \| EUR'` | genetic_ancestry: FIN | 1000 Genomes' population code, the term itself (HANCESTRO:0767); PRIMED's `population_label` writes it with its superpopulation, `FIN \| EUR`, which the term sits under. |
| 331 | 0 | 331 | 0 | genetic_ancestry.lwk | `any` | `'LWK' · 'LWK \| AFR'` | genetic_ancestry: LWK | 1000 Genomes' population code, the term itself (HANCESTRO:0666); PRIMED's `population_label` writes it with its superpopulation, `LWK \| AFR`, which the term sits under. |
| 322 | 0 | 322 | 0 | genetic_ancestry.mxl | `any` | `'MXL' · 'MXL \| AMR'` | genetic_ancestry: MXL | 1000 Genomes' population code, the term itself (HANCESTRO:0685); PRIMED's `population_label` writes it with its superpopulation, `MXL \| AMR`, which the term sits under. |
| 313 | 0 | 313 | 0 | genetic_ancestry.cdx | `any` | `'CDX' · 'CDX \| EAS'` | genetic_ancestry: CDX | 1000 Genomes' population code, the term itself (HANCESTRO:0752); PRIMED's `population_label` writes it with its superpopulation, `CDX \| EAS`, which the term sits under. |
| 311 | 0 | 311 | 0 | genetic_ancestry.gbr | `any` | `'GBR' · 'GBR \| EUR'` | genetic_ancestry: GBR | 1000 Genomes' population code, the term itself (HANCESTRO:0765); PRIMED's `population_label` writes it with its superpopulation, `GBR \| EUR`, which the term sits under. |
| 257 | 0 | 257 | 0 | genetic_ancestry.asw | `any` | `'ASW' · 'ASW \| AFR'` | genetic_ancestry: ASW | 1000 Genomes' population code, the term itself (HANCESTRO:0659); PRIMED's `population_label` writes it with its superpopulation, `ASW \| AFR`, which the term sits under. |

### organism_type

| files | published | submitter | external | rule | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9,656 | 9,656 | 0 | 0 | organism_type.human | `any` | `'Human'` | organism_type: Human | The term itself, as AnVIL's `anvil_donor.organism_type` writes it. |
| 183 | 183 | 0 | 0 | organism_type.mouse | `any` | `'Mouse'` | organism_type: Mouse | The term itself, as AnVIL's `anvil_donor.organism_type` writes it; every Mouse donor in anvil15 is IGVF's, whose donors are laboratory mice (Mus musculus). |

### reported_ethnicity

| files | published | submitter | external | rule | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 1 | 1 | 0 | reported_ethnicity.black_or_african_american | `any` | `'Black or African American'` | reported_ethnicity: Black or African American | The term itself, as AnVIL's `anvil_donor.reported_ethnicity` writes it, and NIA_CARD's `subject.race_ethnicity` it is made from. |
| 2 | 1 | 1 | 0 | reported_ethnicity.hispanic_or_latino | `any` | `'Hispanic or Latino'` | reported_ethnicity: Hispanic or Latino | The term itself, as AnVIL's `anvil_donor.reported_ethnicity` writes it, and NIA_CARD's `subject.race_ethnicity` it is made from. |
| 2 | 1 | 1 | 0 | reported_ethnicity.white | `any` | `'White'` | reported_ethnicity: White | The term itself, as AnVIL's `anvil_donor.reported_ethnicity` writes it, and NIA_CARD's `subject.race_ethnicity` it is made from. |

### biosample_type

| files | published | submitter | external | rule | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1,518 | 1,518 | 0 | 0 | biosample_type.tissue | `any` | `'Tissue'` | biosample_type: Tissue | The term itself, as AnVIL's `anvil_biosample.biosample_type` writes it. |
| 365 | 365 | 0 | 0 | biosample_type.unknown | `any` | `'Unknown'` | nothing (reviewed, no claim) | AnVIL's `Unknown` names no type: reviewed, and no claim. On anvil15 it is every filled HPRC_R2 biosample's (230 of 234; 4 are null) and 135 of IGVF's. |

## Lineage: what each step is (the activity map)

Lineage lines (a file made from a parent) whose step no authored activity-map row names yet, so reconcile cannot say what the parent passes on. One entry per key: the source's table, its words for the step, the columns the child and parent came from, and the data type the same table gives each. 28 keys listed, from the lineage evidence.

### Repository activity: the repository's own record of each step

| lines | table | raw_activity | child_column | parent_column | child_data_type | parent_data_type | datasets | rule it would use |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 52,453 | `'anvil_activity'` | `'Unknown'` | `'generated_file_id'` | `'used_biosample_id'` |  |  | `ANVIL_1000G_high_coverage_2019, ANVIL_HPRC, ANVIL_T2T` | activity.anvil_activity_unknown_generated_file_id_used_biosample_id |
| 14,843 | `'anvil_activity'` |  | `'generated_file_id'` | `'used_biosample_id'` |  |  | `AnVIL_HPRC_R2` | activity.anvil_activity_generated_file_id_used_biosample_id |
| 8,957 | `'anvil_activity'` | `'Sequencing'` | `'generated_file_id'` | `'used_biosample_id'` |  |  | `AnVIL_IGVF_Mouse_R1` | activity.anvil_activity_sequencing_generated_file_id_used_biosample_id |
| 2,536 | `'anvil_activity'` | `'Track: bedGraphToBigWig'` | `'generated_file_id'` | `'used_biosample_id'` |  |  | `AnVIL_ENCORE_293T, AnVIL_ENCORE_RS293` | activity.anvil_activity_track_bedgraphtobigwig_generated_file_id_used_biosample_id |
| 1,734 | `'anvil_activity'` | `'Unknown'` | `'generated_file_id'` | `'used_file_id'` |  |  | `ANVIL_HPRC, ANVIL_T2T, ANVIL_T2T_CHRY, AnVIL_HPRC_R2` | activity.anvil_activity_unknown_generated_file_id_used_file_id |
| 1,344 | `'anvil_activity'` | `'AlternativeSplicing: rMATS'` | `'generated_file_id'` | `'used_biosample_id'` |  |  | `AnVIL_ENCORE_293T, AnVIL_ENCORE_RS293` | activity.anvil_activity_alternativesplicing_rmats_generated_file_id_used_biosample_id |
| 1,344 | `'anvil_activity'` | `'AlternativeSplicing: rMATS'` | `'generated_file_id'` | `'used_file_id'` |  |  | `AnVIL_ENCORE_293T, AnVIL_ENCORE_RS293` | activity.anvil_activity_alternativesplicing_rmats_generated_file_id_used_file_id |
| 1,344 | `'anvil_activity'` | `'DifferentialExpression: deseq2'` | `'generated_file_id'` | `'used_biosample_id'` |  |  | `AnVIL_ENCORE_293T, AnVIL_ENCORE_RS293` | activity.anvil_activity_differentialexpression_deseq2_generated_file_id_used_biosample_id |
| 1,344 | `'anvil_activity'` | `'DifferentialExpression: deseq2'` | `'generated_file_id'` | `'used_file_id'` |  |  | `AnVIL_ENCORE_293T, AnVIL_ENCORE_RS293` | activity.anvil_activity_differentialexpression_deseq2_generated_file_id_used_file_id |
| 1,260 | `'anvil_activity'` | `'Sequence: NovaSeq6000'` | `'generated_file_id'` | `'used_biosample_id'` |  |  | `AnVIL_ENCORE_293T, AnVIL_ENCORE_RS293` | activity.anvil_activity_sequence_novaseq6000_generated_file_id_used_biosample_id |
| 634 | `'anvil_activity'` | `'Alignment: STAR'` | `'generated_file_id'` | `'used_biosample_id'` |  |  | `AnVIL_ENCORE_293T, AnVIL_ENCORE_RS293` | activity.anvil_activity_alignment_star_generated_file_id_used_biosample_id |
| 634 | `'anvil_activity'` | `'Quantificatioin: salmon'` | `'generated_file_id'` | `'used_biosample_id'` |  |  | `AnVIL_ENCORE_293T, AnVIL_ENCORE_RS293` | activity.anvil_activity_quantificatioin_salmon_generated_file_id_used_biosample_id |
| 16 | `'anvil_activity'` | `''` | `'generated_file_id'` | `'used_biosample_id'` |  |  | `AnVIL_IGVF_Mouse_R1` | activity.anvil_activity_generated_file_id_used_biosample_id_ca9968 |
| 8 | `'anvil_activity'` | `'Merger: multiple FASTQ files'` | `'generated_file_id'` | `'used_biosample_id'` |  |  | `AnVIL_ENCORE_293T` | activity.anvil_activity_merger_multiple_fastq_files_generated_file_id_used_biosample_id |

### Submitter: the submitter tables

| lines | table | raw_activity | child_column | parent_column | child_data_type | parent_data_type | datasets | rule it would use |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5,861 | `'file'` |  | `'file_path'` | `'derived_from'` | `'sparse gene count matrix'` | `'reads'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_sparse_gene_count_matrix_reads |
| 3,864 | `'file'` |  | `'file_path'` | `'derived_from'` | `'kallisto single cell RNAseq output'` | `'reads'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_kallisto_single_cell_rnaseq_output_reads |
| 1,936 | `'file'` |  | `'file_path'` | `'derived_from'` | `'kallisto single cell RNAseq output'` | `'seqspec'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_kallisto_single_cell_rnaseq_output_seqspec |
| 1,936 | `'file'` |  | `'file_path'` | `'derived_from'` | `'sparse gene count matrix'` | `'seqspec'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_sparse_gene_count_matrix_seqspec |
| 745 | `'file'` |  | `'file_path'` | `'derived_from'` | `'sparse gene count matrix'` | `'sparse gene count matrix'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_sparse_gene_count_matrix_sparse_gene_count_matrix |
| 318 | `'file'` |  | `'file_path'` | `'derived_from'` | `'sparse gene count matrix'` | `'barcode replacement'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_sparse_gene_count_matrix_barcode_replacement |
| 302 | `'file'` |  | `'file_path'` | `'derived_from'` | `'kallisto single cell RNAseq output'` | `'barcode replacement'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_kallisto_single_cell_rnaseq_output_barcode_replacement |
| 30 | `'file'` |  | `'file_path'` | `'derived_from'` | `'transcript quantifications'` | `'reads'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_transcript_quantifications_reads |
| 11 | `'file'` |  | `'file_path'` | `'derived_from'` | `'reads'` | `'Nanopore reads'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_reads_nanopore_reads |
| 6 | `'file'` |  | `'file_path'` | `'derived_from'` | `'fragments'` | `'reads'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_fragments_reads |
| 2 | `'file'` |  | `'file_path'` | `'derived_from'` | `'alignments'` | `'seqspec'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_alignments_seqspec |
| 2 | `'file'` |  | `'file_path'` | `'derived_from'` | `'barcode onlist'` | `'barcode onlist'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_barcode_onlist_barcode_onlist |
| 2 | `'file'` |  | `'file_path'` | `'derived_from'` | `'barcode replacement'` | `'barcode onlist'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_barcode_replacement_barcode_onlist |
| 2 | `'file'` |  | `'file_path'` | `'derived_from'` | `'fragments'` | `'seqspec'` | `AnVIL_IGVF_Mouse_R1` | activity.file_file_path_derived_from_fragments_seqspec |

### Archive: an archive's run records (ENA's, #594)

No unreviewed steps.

### Authored activity mappings

| lines | rule | matches | declares | reason |
| --- | --- | --- | --- | --- |
| 223,724 | activity.indexing | `source_type: 'repository_activity'; table: 'anvil_activity'; raw_activity: 'Indexing'; parent_column: 'used_file_id'` | IndexActivity / indexed | AnVIL's Indexing step makes an index of the one file it used (a CRAM, a VCF, a mosdepth regions BED). Named with its file parent column, so a sample parent is not read as one. |
| 104,302 | activity.t2t_index | `source_type: 'repository_metadata'; table: '1KGP_CHM13v2_sample' · 'SGDP_CHM13v2_sample' · 'SGDP_GRCh38_sample' · 'participant'; child_column: 'chr10_hcvcf_index' · 'chr11_hcvcf_index' · 'chr12_hcvcf_index' · 'chr13_hcvcf_index' · 'chr14_hcvcf_index' · 'chr15_hcvcf_index' · 'chr16_hcvcf_index' · 'chr17_hcvcf_index' · 'chr18_hcvcf_index' · 'chr19_hcvcf_index' · 'chr1_hcvcf_index' · 'chr20_hcvcf_index' · 'chr21_hcvcf_index' · 'chr22_hcvcf_index' · 'chr2_hcvcf_index' · 'chr3_hcvcf_index' · 'chr4_hcvcf_index' · 'chr5_hcvcf_index' · 'chr6_hcvcf_index' · 'chr7_hcvcf_index' · 'chr8_hcvcf_index' · 'chr9_hcvcf_index' · 'cram_index' · 'mosdepth_regions_bed_idx' · 'mosdepth_regions_index' · 'xx_x_hcvcf_index' · 'xy_x_nonpar_hcvcf_index' · 'xy_x_par_hcvcf_index' · 'xy_y_nonpar_hcvcf_index'; parent_column: 'chr10_hcvcf_gz' · 'chr11_hcvcf_gz' · 'chr12_hcvcf_gz' · 'chr13_hcvcf_gz' · 'chr14_hcvcf_gz' · 'chr15_hcvcf_gz' · 'chr16_hcvcf_gz' · 'chr17_hcvcf_gz' · 'chr18_hcvcf_gz' · 'chr19_hcvcf_gz' · 'chr1_hcvcf_gz' · 'chr20_hcvcf_gz' · 'chr21_hcvcf_gz' · 'chr22_hcvcf_gz' · 'chr2_hcvcf_gz' · 'chr3_hcvcf_gz' · 'chr4_hcvcf_gz' · 'chr5_hcvcf_gz' · 'chr6_hcvcf_gz' · 'chr7_hcvcf_gz' · 'chr8_hcvcf_gz' · 'chr9_hcvcf_gz' · 'cram' · 'mosdepth_regions_bed' · 'xx_x_hcvcf_gz' · 'xy_x_nonpar_hcvcf_gz' · 'xy_x_par_hcvcf_gz' · 'xy_y_nonpar_hcvcf_gz'` | IndexActivity / indexed | Each index column on a sample row indexes the file in the column it is named after (`cram_index` the `cram`, `chr1_hcvcf_index` the `chr1_hcvcf_gz`). The two lists match every combination, not only those pairs: no other pair occurs, and any index of one of these files is an index of it. |
| 90,378 | activity.t2t_variant_call | `source_type: 'repository_metadata'; table: '1KGP_CHM13v2_sample' · 'SGDP_CHM13v2_sample' · 'SGDP_GRCh38_sample' · 'participant'; child_column: 'chr10_hcvcf_gz' · 'chr11_hcvcf_gz' · 'chr12_hcvcf_gz' · 'chr13_hcvcf_gz' · 'chr14_hcvcf_gz' · 'chr15_hcvcf_gz' · 'chr16_hcvcf_gz' · 'chr17_hcvcf_gz' · 'chr18_hcvcf_gz' · 'chr19_hcvcf_gz' · 'chr1_hcvcf_gz' · 'chr20_hcvcf_gz' · 'chr21_hcvcf_gz' · 'chr22_hcvcf_gz' · 'chr2_hcvcf_gz' · 'chr3_hcvcf_gz' · 'chr4_hcvcf_gz' · 'chr5_hcvcf_gz' · 'chr6_hcvcf_gz' · 'chr7_hcvcf_gz' · 'chr8_hcvcf_gz' · 'chr9_hcvcf_gz' · 'xx_x_hcvcf_gz' · 'xy_x_nonpar_hcvcf_gz' · 'xy_x_par_hcvcf_gz' · 'xy_y_nonpar_hcvcf_gz'; parent_column: 'cram'` | VariantCallActivity / calls_from | HaplotypeCaller's per-chromosome VCFs are called from the sample row's CRAM. |
| 39,611 | activity.t2t_quality_control | `source_type: 'repository_metadata'; table: '1KGP_CHM13v2_sample' · 'SGDP_CHM13v2_sample' · 'SGDP_GRCh38_sample' · 'participant'; child_column: 'chrx_samtools_stats' · 'chry_samtools_stats' · 'full_samtools_stats' · 'mosdepth_global_dist' · 'mosdepth_regions_bed' · 'mosdepth_regions_dist' · 'mosdepth_summary' · 'samtools_stats'; parent_column: 'cram'` | QualityControlActivity / reported_on | samtools stats and mosdepth read the CRAM on the same sample row and report on its content. |
| 31,158 | activity.external_sample_map_import | `source_type: 'external_ground_truth'; table: 'sample_maps'; raw_activity: 'GenomicsDBImport'; child_column: 'file_id'; parent_column: '--sample-name-map'` | CohortMergeActivity / input_list | A workspace tar's own vcfheader.vcf says GenomicsDBImport read this sample-name map, and the tar's callset.json names exactly the samples the map's published copy lists: the tar merges the gVCFs the map lists, read through it (#710, a workaround until AnVIL holds the map, #624). |
| 31,155 | activity.t2t_joint_genotype | `source_type: 'repository_metadata'; table: 'interval'; child_column: 'genotyped_bgzip'; parent_column: 'genomics_db_tar'` | JointGenotypingActivity / genotyped_from | The interval row's VCF is its GenomicsDB workspace genotyped across every sample (GATK GenotypeGVCFs reads the workspace) and trimmed to the interval (SelectVariants). The VCF's header carries the workspace's GenomicsDBImport line and SelectVariants', but not GenotypeGVCFs', so the row is what states the link (#610), and with it the calls' kind and origin, which the header no longer names (#678). The SelectVariants step selects intervals, not types (no T2T header names --select-type), so the kind passes. |
| 14,174 | activity.checksum | `source_type: 'repository_activity'; table: 'anvil_activity'; raw_activity: 'Checksum'; parent_column: 'used_file_id'` | ChecksumActivity / checked | AnVIL's Checksum step makes the checksum file of the one file it used. |
| 7,520 | activity.t2t_alignment | `source_type: 'repository_metadata'; table: '1KGP_CHM13v2_sample' · 'SGDP_CHM13v2_sample' · 'SGDP_GRCh38_sample' · 'participant'; child_column: 'cram'; parent_column: 'read_1_fastq' · 'read_2_fastq'` | AlignmentActivity / reads | The sample row's CRAM is its two FASTQs aligned. |
| 6,404 | activity.ena_run_bwa_mem | `source_type: 'external_ground_truth'; table: 'read_run'; raw_activity: 'bwa mem'; child_column: 'cram'; parent_column: 'fastq_ftp'` | AlignmentActivity / reads | A T2T_CHRY CRAM holds the ENA run whose read and base counts its samtools stats equal, and its own @PG says bwa mem took FASTQs: the run's reads, aligned (#594). |
| 2,536 | activity.track_bedgraphtobigwig | `source_type: 'repository_activity'; table: 'anvil_activity'; raw_activity: 'Track: bedGraphToBigWig'; parent_column: 'used_file_id'` | CoverageActivity / covered | Each step used one STAR BAM and generated its four `Signal.{Unique,UniqueMultiple}.strand±` bigWigs: STAR's per-strand coverage of that BAM, converted by bedGraphToBigWig, so the raw words name the conversion, not what was computed. |
| 1,268 | activity.alignment_star | `source_type: 'repository_activity'; table: 'anvil_activity'; raw_activity: 'Alignment: STAR'; parent_column: 'used_file_id'` | AlignmentActivity / reads | STAR aligns reads; every file this step used in anvil15 is a trimmed FASTQ. Its sample parents (`used_biosample_id`) are not matched here. |
| 1,268 | activity.quantification_salmon | `source_type: 'repository_activity'; table: 'anvil_activity'; raw_activity: 'Quantificatioin: salmon'; parent_column: 'used_file_id'` | ExpressionActivity / quantified | salmon quantifies the reads it used; every file this step used in anvil15 is a trimmed FASTQ. `Quantificatioin` is AnVIL's spelling, matched as written. |
| 72 | activity.t2t_variant_filter | `source_type: 'repository_metadata'; table: 'chromosome'; child_column: 'chm13_pass_vcf_gz' · 'chm13_recalibrated_vcf_gz' · 'grch38_pass_vcf_gz'; parent_column: 'chm13_raw_vcf_gz' · 'chm13_recalibrated_vcf_gz' · 'grch38_recalibrated_vcf_gz'` | VariantFilterActivity / processed | On a chromosome row, the recalibrated callset is the raw one with every row labelled by GATK's ApplyVQSR (its header records both passes), and the PASS callset is the recalibrated one with only its passing rows kept (`bcftools view -f PASS`). The row holds CHM13's raw, recalibrated and PASS callsets and GRCh38's recalibrated and PASS ones. The lists match every combination, but the lineage map pairs each chain only within itself, so no line pairs a CHM13 file with a GRCh38 one (#610). |
| 20 | activity.merger_fastq | `source_type: 'repository_activity'; table: 'anvil_activity'; raw_activity: 'Merger: multiple FASTQ files'; parent_column: 'used_file_id'` | MergeActivity / shard | The step joins the FASTQs it used into one FASTQ. |
| 6 | activity.igvf_alignment | `source_type: 'repository_metadata'; table: 'file'; child_column: 'file_path'; parent_column: 'derived_from'; child_data_type: 'alignments'; parent_data_type: 'reads'` | AlignmentActivity / reads | IGVF alignments derived from reads are those reads aligned. |
| 4 | activity.igvf_index | `source_type: 'repository_metadata'; table: 'file'; child_column: 'file_path'; parent_column: 'derived_from'; child_data_type: 'index'; parent_data_type: 'alignments' · 'fragments'` | IndexActivity / indexed | An IGVF index is derived from the alignments or fragments file it indexes. |
