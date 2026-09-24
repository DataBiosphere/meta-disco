# Review queue

Source values that no authored translation row reads yet, so they make no claim (contract 5.2). A value is listed once per source, dataset, table and column it arrives through; the row column names the seeded row it selects, or — where no row matches. 743 listed, from evidence under data/source_evidence.

## Published: the catalog's published columns

| files | slot | raw value | source | dataset | table | column | row |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6,733 | data_modality | `'["single-nucleus RNA sequencing assay"]'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `anvil_file` | `data_modality` | — |
| 2,932 | reference_assembly | `'["GRCh38 + Gencode40"]'` | `anvil` | `AnVIL_ENCORE_RS293` | `anvil_file` | `reference_assembly` | — |
| 1,544 | reference_assembly | `'["GRCh38 + Gencode40"]'` | `anvil` | `AnVIL_ENCORE_293T` | `anvil_file` | `reference_assembly` | — |
| 220 | reference_assembly | `'["GRCm39"]'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `anvil_file` | `reference_assembly` | — |
| 12 | data_modality | `'["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"]'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `anvil_file` | `data_modality` | — |
| 10 | data_modality | `'["single-nucleus ATAC-seq"]'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `anvil_file` | `data_modality` | — |

## Submitter: the submitter tables

| files | slot | raw value | source | dataset | table | column | row |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 184,105 | reference_assembly | `'CHM13v2'` | `anvil` | `ANVIL_T2T_CHRY` | `1KGP_CHM13v2_sample` |  | — |
| 62,316 | reference_assembly | `'CHM13v2'` | `anvil` | `ANVIL_T2T_CHRY` | `PAR_interval_CHM13v2` |  | — |
| 16,324 | reference_assembly | `'CHM13v2'` | `anvil` | `ANVIL_T2T_CHRY` | `SGDP_CHM13v2_sample` |  | — |
| 8,562 | data_type | `'plink'` | `anvil` | `ANVIL_1000G_PRIMED_data_model` | `plink_file_wide` |  | — |
| 6,733 | assay_type | `'["single-nucleus RNA sequencing assay"]'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `assay_titles` | — |
| 2,932 | reference_assembly | `'GRCh38 + Gencode40'` | `anvil` | `AnVIL_ENCORE_RS293` | `file` | `reference_assembly` | — |
| 1,680 | platform | `'Illumina NovaSeq X'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `sequencing_platform` | — |
| 1,544 | reference_assembly | `'GRCh38 + Gencode40'` | `anvil` | `AnVIL_ENCORE_293T` | `file` | `reference_assembly` | — |
| 462 | data_type | `'alignments'` | `anvil` | `AnVIL_HPRC_R2` | `alignments_winnowmap` |  | data_type.alignments |
| 462 | data_type | `'chains'` | `anvil` | `AnVIL_HPRC_R2` | `chains_to_chm13_mc` |  | data_type.chains |
| 462 | data_type | `'chains'` | `anvil` | `AnVIL_HPRC_R2` | `chains_to_grch38_mc` |  | data_type.chains |
| 462 | data_type | `'gaps'` | `anvil` | `AnVIL_HPRC_R2` | `gaps` |  | data_type.gaps |
| 462 | data_type | `'sequences'` | `anvil` | `AnVIL_HPRC_R2` | `t2t_sequences` |  | data_type.sequences |
| 462 | reference_assembly | `'chm13'` | `anvil` | `AnVIL_HPRC_R2` | `to_ref_chm13_winnowmap` |  | reference_assembly.chm13 |
| 268 | platform | `'Illumina NextSeq 2000'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `sequencing_platform` | — |
| 240 | reference_assembly | `'CHM13v2'` | `anvil` | `ANVIL_T2T_CHRY` | `1KGP_CHM13v2_chromosome` |  | — |
| 230 | assay_type | `'isoseq'` | `anvil` | `AnVIL_HPRC_R2` | `kinnex` | `library_strategy` | assay_type.isoseq |
| 230 | data_modality | `'transcriptomic'` | `anvil` | `AnVIL_HPRC_R2` | `kinnex` | `library_source` | data_modality.transcriptomic |
| 220 | reference_assembly | `'GRCm39'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `reference_assembly` | — |
| 168 | reference_assembly | `'CHM13v2'` | `anvil` | `ANVIL_T2T_CHRY` | `SGDP_CHM13v2_chromosome` |  | — |
| 47 | reference_assembly | `'chm13'` | `anvil` | `ANVIL_HPRC` | `assembly_sample` | `mat_chm13_aln_bai` | reference_assembly.chm13 |
| 47 | reference_assembly | `'chm13'` | `anvil` | `ANVIL_HPRC` | `assembly_sample` | `mat_chm13_aln_bam` | reference_assembly.chm13 |
| 47 | reference_assembly | `'chm13'` | `anvil` | `ANVIL_HPRC` | `assembly_sample` | `pat_chm13_aln_bai` | reference_assembly.chm13 |
| 47 | reference_assembly | `'chm13'` | `anvil` | `ANVIL_HPRC` | `assembly_sample` | `pat_chm13_aln_bam` | reference_assembly.chm13 |
| 44 | reference_assembly | `'chm13'` | `anvil` | `ANVIL_HPRC` | `assembly_annotation` | `mat_chm13_cat_genes` | reference_assembly.chm13 |
| 44 | reference_assembly | `'chm13'` | `anvil` | `ANVIL_HPRC` | `assembly_annotation` | `pat_chm13_cat_genes` | reference_assembly.chm13 |
| 24 | reference_assembly | `'chm13'` | `anvil` | `ANVIL_T2T` | `chromosome` | `chm13_pass_vcf_gz` | reference_assembly.chm13 |
| 24 | reference_assembly | `'chm13'` | `anvil` | `ANVIL_T2T` | `chromosome` | `chm13_raw_vcf_gz` | reference_assembly.chm13 |
| 24 | reference_assembly | `'chm13'` | `anvil` | `ANVIL_T2T` | `chromosome` | `chm13_recalibrated_vcf_gz` | reference_assembly.chm13 |
| 20 | platform | `'ONT GridION X5'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `sequencing_platform` | — |
| 12 | assay_type | `'["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"]'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `assay_titles` | — |
| 12 | data_type | `'alignments'` | `anvil` | `AnVIL_HPRC_R2` | `alignments_v2` |  | data_type.alignments |
| 10 | assay_type | `'["single-nucleus ATAC-seq"]'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `assay_titles` | — |
| 6 | assay_type | `'Nanopore'` | `anvil` | `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open` | `sequencing` | `sequencing_strategy` | — |
| 6 | reference_assembly | `'chm13'` | `anvil` | `AnVIL_HPRC_R2` | `alignments_v2` | `reference_coordinates` | reference_assembly.chm13 |
| 6 | reference_assembly | `'hg38, chm13'` | `anvil` | `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open` | `sequencing` | `reference_genome_build` | — |
| 3 | platform | `'Nanopore_R10'` | `anvil` | `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open` | `sequencing` | `sequencing_platform` | — |
| 3 | platform | `'Nanopore_R9'` | `anvil` | `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open` | `sequencing` | `sequencing_platform` | — |
| 2 | platform | `'Illumina NovaSeq 6001'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6002'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6003'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6004'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6005'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6006'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6007'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6008'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6009'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6010'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6011'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6012'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6013'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6014'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6015'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6016'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6017'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6018'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6019'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6020'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6021'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6022'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6023'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6024'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6025'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6026'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6027'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6028'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6029'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6030'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6031'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6032'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6033'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6034'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6035'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6036'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6037'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6038'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6039'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6040'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6041'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6042'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6043'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6044'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6045'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6046'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6047'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6048'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6049'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6050'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6051'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6052'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6053'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6054'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6055'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6056'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6057'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6058'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6059'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6060'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6061'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6062'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6063'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6064'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6065'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6066'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6067'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6068'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6069'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6070'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6071'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6072'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6073'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6074'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6075'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6076'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6077'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6078'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6079'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6080'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6081'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6082'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6083'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6084'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6085'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6086'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6087'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6088'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6089'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6090'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6091'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6092'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6093'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6094'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6095'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6096'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6097'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6098'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6099'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6100'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6101'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6102'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6103'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6104'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6105'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6106'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6107'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6108'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6109'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6110'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6111'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6112'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6113'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6114'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6115'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6116'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6117'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6118'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6119'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6120'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6121'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6122'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6123'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6124'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6125'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6126'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6127'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6128'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6129'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6130'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6131'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6132'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6133'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6134'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6135'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6136'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6137'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6138'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6139'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6140'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6141'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6142'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6143'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6144'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6145'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6146'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6147'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6148'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6149'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6150'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6151'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6152'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6153'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6154'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6155'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6156'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6157'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6158'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6159'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6160'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6161'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6162'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6163'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6164'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6165'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6166'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6167'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6168'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6169'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6170'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6171'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6172'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6173'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6174'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6175'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6176'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6177'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6178'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6179'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6180'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6181'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6182'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6183'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6184'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6185'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6186'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6187'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6188'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6189'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6190'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6191'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6192'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6193'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6194'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6195'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6196'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6197'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6198'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6199'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6200'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6201'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6202'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6203'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6204'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6205'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6206'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6207'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6208'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6209'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6210'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6211'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6212'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6213'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6214'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6215'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6216'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6217'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6218'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6219'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6220'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6221'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6222'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6223'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6224'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6225'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6226'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6227'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6228'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6229'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6230'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6231'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6232'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6233'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6234'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6235'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6236'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6237'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6238'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6239'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6240'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6241'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6242'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6243'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6244'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6245'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6246'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6247'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6248'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6249'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6250'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6251'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6252'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6253'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6254'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6255'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6256'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6257'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6258'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6259'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6260'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6261'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6262'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6263'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6264'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6265'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6266'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6267'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6268'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6269'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6270'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6271'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6272'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6273'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6274'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6275'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6276'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6277'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6278'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6279'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6280'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6281'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6282'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6283'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6284'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6285'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6286'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6287'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6288'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6289'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6290'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6291'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6292'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6293'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6294'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6295'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6296'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6297'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6298'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6299'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6300'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6301'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6302'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6303'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6304'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6305'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6306'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6307'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6308'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6309'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6310'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6311'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6312'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6313'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6314'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6315'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6316'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6317'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6318'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6319'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6320'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6321'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6322'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6323'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6324'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6325'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6326'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6327'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6328'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6329'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6330'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6331'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6332'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6333'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6334'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6335'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6336'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6337'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6338'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6339'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6340'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6341'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6342'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6343'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6344'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6345'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6346'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6347'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6348'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6349'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6350'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6351'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6352'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6353'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6354'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6355'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6356'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6357'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6358'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6359'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6360'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6361'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6362'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6363'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6364'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6365'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6366'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6367'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6368'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6369'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6370'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6371'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6372'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6373'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6374'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6375'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6376'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6377'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6378'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6379'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6380'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6381'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6382'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6383'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6384'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6385'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6386'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6387'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6388'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6389'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6390'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6391'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6392'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6393'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6394'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6395'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6396'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6397'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6398'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6399'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6400'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6401'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6402'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6403'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6404'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6405'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6406'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6407'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6408'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6409'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6410'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6411'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6412'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6413'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6414'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6415'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6416'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6417'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6418'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6419'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6420'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6421'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6422'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6423'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6424'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6425'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6426'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6427'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6428'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6429'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6430'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6431'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6432'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6433'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6434'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6435'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6436'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6437'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6438'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6439'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6440'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6441'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6442'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6443'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6444'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6445'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6446'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6447'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6448'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6449'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6450'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6451'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6452'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6453'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6454'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6455'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6456'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6457'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6458'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6459'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6460'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6461'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6462'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6463'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6464'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6465'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6466'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6467'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6468'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6469'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6470'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6471'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6472'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6473'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6474'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6475'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6476'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6477'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6478'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6479'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6480'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6481'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6482'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6483'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6484'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6485'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6486'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6487'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6488'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6489'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6490'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6491'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6492'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6493'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6494'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6495'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6496'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6497'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6498'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6499'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6500'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6501'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6502'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6503'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6504'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6505'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6506'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6507'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6508'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6509'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6510'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6511'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6512'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6513'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6514'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6515'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6516'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6517'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6518'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6519'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6520'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6521'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6522'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6523'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6524'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6525'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6526'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6527'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6528'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6529'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6530'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6531'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6532'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6533'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6534'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6535'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6536'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6537'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6538'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6539'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6540'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6541'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6542'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6543'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6544'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6545'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6546'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6547'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6548'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6549'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6550'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6551'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6552'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6553'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6554'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6555'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6556'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6557'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6558'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6559'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6560'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6561'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6562'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6563'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6564'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6565'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6566'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6567'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6568'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6569'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6570'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6571'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6572'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6573'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6574'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6575'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6576'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6577'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6578'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6579'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6580'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6581'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6582'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6583'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6584'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6585'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6586'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6587'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6588'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6589'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6590'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6591'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6592'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6593'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6594'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6595'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6596'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6597'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6598'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6599'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6600'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6601'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6602'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6603'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6604'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6605'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6606'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6607'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6608'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6609'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6610'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6611'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6612'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6613'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6614'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6615'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6616'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6617'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6618'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6619'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6620'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6621'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6622'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6623'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6624'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6625'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6626'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6627'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6628'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6629'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6630'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6631'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6632'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6633'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6634'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6635'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6636'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6637'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6638'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6639'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6640'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6641'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6642'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6643'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6644'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6645'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6646'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6647'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6648'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6649'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6650'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6651'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6652'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6653'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6654'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6655'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6656'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6657'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6658'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6659'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6660'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6661'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6662'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6663'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6664'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6665'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6666'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6667'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6668'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6669'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6670'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6671'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6672'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6673'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6674'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6675'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6676'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6677'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6678'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6679'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6680'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6681'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6682'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6683'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6684'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6685'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6686'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6687'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6688'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6689'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6690'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6691'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6692'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6693'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6694'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6695'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6696'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6697'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'Illumina NovaSeq 6698'` | `anvil` | `ANVIL_1000G_high_coverage_2019` | `participant` | `instrument_model` | — |
| 2 | platform | `'ONT PromethION 2 Solo'` | `anvil` | `AnVIL_IGVF_Mouse_R1` | `file` | `sequencing_platform` | — |

## Authored mappings: what each translation row declares

Every authored translation row, most files first: the source values it matches and what it declares. Files are those it matched in the same evidence as the queue above, from published and from submitter sources; a row that matched nothing shows 0.

| files | published | submitter | row | slot | scope | matches | declares | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 48,613 | 0 | 48,613 | reference_assembly.grch38 | reference_assembly | `any` | `'grch38' · 'hg38'` | reference_assembly: GRCh38 | Column-name spans naming the GRCh38 assembly; hg38 is UCSC's name for the same assembly. |
| 19,807 | 0 | 19,807 | platform.illumina_novaseq_6000 | platform | `any` | `'Illumina NovaSeq 6000'` | platform: ILLUMINA | An Illumina instrument model; the model implies the platform. |
| 15,222 | 0 | 15,222 | data_modality.genomic | data_modality | `any` | `'GENOMIC'` | data_modality: genomic | SRA's library_source value for genomic DNA, spelled as our term. Identity by ruling, not by spelling; if a bisulfite or ATAC library ever arrives under it, narrow this row rather than rank it. |
| 12,426 | 0 | 12,426 | assay_type.wgs | assay_type | `any` | `'WGS'` | assay_type: WGS; data_modality: genomic | Whole-genome sequencing, spelled as our term; a WGS library is genomic DNA. |
| 9,600 | 0 | 9,600 | platform.illumina | platform | `any` | `'ILLUMINA' · 'illumina'` | platform: ILLUMINA | Spelled as our term, as SRA's platform value and as a table-name span. Identity by ruling. |
| 4,690 | 0 | 4,690 | data_type.unaligned_reads | data_type | `any` | `'unaligned reads'` | data_type: reads | Reads, as the source says; whether aligned is not the data type. |
| 3,770 | 0 | 3,770 | assay_type.hi_c | assay_type | `any` | `'Hi-C' · 'hic'` | data_modality: genomic | Hi-C is chromatin-conformation sequencing of genomic DNA, so the modality is genomic. The vocabulary has no assay term for it yet (#399), so nothing is declared for assay_type. `hic` is the table-name span of the same data. |
| 3,002 | 0 | 3,002 | reference_assembly.unaligned | reference_assembly | `any` | `'unaligned'` | reference_assembly: not_applicable | The source's word for a file with no reference; the slot does not apply. |
| 1,688 | 0 | 1,688 | platform.pacbio_smrt | platform | `any` | `'PACBIO_SMRT'` | platform: PACBIO | SRA's platform value for PacBio. |
| 1,391 | 0 | 1,391 | platform.ont | platform | `any` | `'ont'` | platform: ONT | Spelled as our term, as a table-name span. Identity by ruling. |
| 1,292 | 0 | 1,292 | platform.hifi | platform | `any` | `'hifi'` | platform: PACBIO | HiFi reads are PacBio's; the span says platform only and implies no assay (#430). |
| 1,235 | 0 | 1,235 | platform.sequel_ii | platform | `any` | `'Sequel II'` | platform: PACBIO | A PacBio instrument. |
| 1,018 | 0 | 1,018 | data_type.repeat_masker | data_type | `any` | `'repeat_masker'` | data_type: annotations | RepeatMasker repeat annotations of an assembly (BED and .out). |
| 929 | 0 | 929 | platform.oxford_nanopore | platform | `any` | `'OXFORD_NANOPORE'` | platform: ONT | SRA's platform value for Oxford Nanopore. |
| 925 | 0 | 925 | platform.promethion | platform | `any` | `'PromethION'` | platform: ONT | An Oxford Nanopore instrument. |
| 881 | 0 | 881 | data_type.annotation | data_type | `any` | `'annotation'` | data_type: annotations | The `assembly_annotation` table-name span; its files are feature annotations of an assembly. |
| 683 | 0 | 683 | platform.revio | platform | `any` | `'Revio' · 'REVIO'` | platform: PACBIO | A PacBio instrument; the kinnex table spells it in capitals. |
| 641 | 0 | 641 | data_type.unaligned_reads_with_5mc_mods | data_type | `any` | `'unaligned reads with 5mC mods'` | data_type: reads | Reads carrying base-modification calls; the modification tags do not change the data type. |
| 619 | 0 | 619 | platform.deepconsensus | platform | `any` | `'deepconsensus'` | platform: PACBIO | DeepConsensus is PacBio's HiFi read-polishing method; the span names PacBio data. Platform only. |
| 466 | 0 | 466 | data_type.assembly | data_type | `any` | `'assembly'` | data_type: assembly | The `assembly` table-name span; its files are the de-novo assemblies (.fa.gz). |
| 462 | 0 | 462 | data_modality.methylation | data_modality | `any` | `'methylation'` | data_modality: epigenomic.methylation | The `ont_methylation` table-name span; its files are bigwig methylation tracks. |
| 462 | 0 | 462 | data_type.censat | data_type | `any` | `'censat'` | data_type: annotations | Centromeric satellite annotation tracks (BED) of an assembly. |
| 462 | 0 | 462 | data_type.censat_centromeres | data_type | `any` | `'censat_centromeres'` | data_type: annotations | Centromere annotation tracks (BED) of an assembly. |
| 462 | 0 | 462 | data_type.liftoff | data_type | `any` | `'liftoff'` | data_type: annotations | Gene annotations lifted onto an assembly with Liftoff (GFF3). |
| 462 | 0 | 462 | data_type.segdups | data_type | `any` | `'segdups'` | data_type: annotations | Segmental duplication tracks (BED) of an assembly. |
| 288 | 0 | 288 | data_type.unaligned_reads_with_5mcg_5hmcg_mods | data_type | `any` | `'unaligned reads with 5mCG_5hmCG mods'` | data_type: reads | Reads carrying base-modification calls; the modification tags do not change the data type. |
| 230 | 0 | 230 | data_type.bam | data_type | `any` | `'bam'` | nothing (reviewed, no claim) | A file format, not a data type: the kinnex table's data_type column holds what its filetype column should. Ruled to mean nothing here rather than left queued. |
| 230 | 0 | 230 | platform.kinnex | platform | `any` | `'kinnex'` | platform: PACBIO | Kinnex is a PacBio library kit; the span names PacBio data. Platform only. |
| 230 | 0 | 230 | platform.pacbio | platform | `any` | `'PACBIO'` | platform: PACBIO | Spelled as our term (the kinnex table's spelling). Identity by ruling. |
| 120 | 0 | 120 | platform.nanopore | platform | `any` | `'nanopore'` | platform: ONT | A column-name span naming Oxford Nanopore data. |
| 2 | 0 | 2 | platform.gridion | platform | `any` | `'GridION'` | platform: ONT | An Oxford Nanopore instrument. |
| 2 | 0 | 2 | platform.minion | platform | `any` | `'MinION'` | platform: ONT | An Oxford Nanopore instrument. |
