# AnVIL phs studies — Selected-Publications survey (all catalogs)

Regenerated 2026-08-17 from the phs-anchor skill's `studies` subcommand
(the per-study input list: all Azul datasets aggregated on phsid, fully
paginated), joined with the `gap-exchange` + `fhir` + `esummary` sweep
results of 2026-08-15/17. See `findings.md` for methodology and
per-source behavior; the open-access workspaces additionally have full
dossiers in this directory.

- **74 unique phs accessions** (each hosting one study; ADR-0001 recorded 78 — snapshot drift); 13 workspaces carry no phs accession and take the fallback path. When regenerating, check the `studies` output's `invalid_records` is empty before trusting these totals — shape-validation exclusions would silently lower them.
- **42/74 studies have a non-empty dbGaP Selected Publications list** (GapExchange XML).
- The **lead PMID** below is the first Selected Publication — observed to be the marker paper for cohort/project-style studies (GTEx, ClinSeq, MEC), but for sequencing-center studies (e.g. Mendelian Genomics centers) the list opens with individual result papers, so the lead is a *candidate*, not a confirmed marker. `role` confirmation is Epic 2 work.

| phs | dbGaP study title | AnVIL workspaces | pubs | lead PMID (year) — title |
| --- | --- | --- | --- | --- |
| phs000220 | PAGE: Multiethnic Cohort (MEC) | 1: ANVIL_PAGE_MEC_GRU_WGS | 35 | [10695593](https://pubmed.ncbi.nlm.nih.gov/10695593/) (2000) — A multiethnic cohort in Hawaii and Los Angeles: baseline characteristics. |
| phs000298 | Autism Sequencing Consortium (ASC) | 1: ANVIL_ccdg_asc_ndd_daly_talkowski_… | 6 | [22495311](https://pubmed.ncbi.nlm.nih.gov/22495311/) (2012) — Patterns and rates of exonic de novo mutations in autism spectrum disorders. |
| phs000424 | Common Fund (CF) Genotype-Tissue Expression Project (GTEx) | 5: ANVIL_GTEx_V7_hg19… | 9 | [23715323](https://pubmed.ncbi.nlm.nih.gov/23715323/) (2013) — The Genotype-Tissue Expression (GTEx) project. |
| phs000693 | University of Washington Center for Mendelian Genomics (UW-CMG) | 10: ANVIL_CMG_UWASH_DS_BAV_IRB_PUB_RD… | 50 | [33583022](https://pubmed.ncbi.nlm.nih.gov/33583022/) (2021) — Expanding the phenotype, genotype and biochemical knowledge of ALG3-CDG. |
| phs000744 | Yale Center for Mendelian Genomics (YCMG) | 9: ANVIL_CMG_YALE_DS_MC… | 30 | [23359680](https://pubmed.ncbi.nlm.nih.gov/23359680/) (2013) — Recessive loss of function of the neuronal ubiquitin hydrolase UCHL1 leads to early-onset progressive neurodegeneration. |
| phs000906 | eMERGE Network PGx Cohort | 3: ANVIL_eMERGE_PGRNseq_DS_DEM… | 2 | [24001487](https://pubmed.ncbi.nlm.nih.gov/24001487/) (2013) — The Mayo Clinic Biobank: a building block for individualized medicine. |
| phs000925 | PAGE: IPM BioMe Biobank | 1: ANVIL_PAGE_BioMe_GRU_WGS | 22 | [21573225](https://pubmed.ncbi.nlm.nih.gov/21573225/) (2011) — Genetic background of patients from a university medical center in Manhattan: implications for personalized medicine. |
| phs000971 | The ClinSeq Project: Piloting Large-Scale Genome Sequencing for Research in Genomic Medicine | 1: ANVIL_CSER_ClinSeq_GRU | 39 | [19602640](https://pubmed.ncbi.nlm.nih.gov/19602640/) (2009) — The ClinSeq Project: piloting large-scale genome sequencing for research in genomic medicine. |
| phs000979 | HBCC Postmortem Psychiatric Molecular Studies | 1: AnVIL_NIA_CARD_LR_WGS_HBCC | 8 | [15607306](https://pubmed.ncbi.nlm.nih.gov/15607306/) (2005) — Reliability of psychiatric diagnosis in postmortem research. |
| phs001033 | PAGE: Global Reference Panel | 1: ANVIL_PAGE_Stanford_Global_Referen… | 4 | [11954565](https://pubmed.ncbi.nlm.nih.gov/11954565/) (2002) — A human genome diversity cell line panel. |
| phs001222 | CCDG - Whole Genome Sequencing in Type 1 Diabetes (T1DGC) | 1: ANVIL_ccdg_washu_ai_t1d_t1dgc_wgs | 3 | [19430480](https://pubmed.ncbi.nlm.nih.gov/19430480/) (2009) — Genome-wide association study and meta-analysis find that over 40 loci affect risk of type 1 diabetes. |
| phs001227 | Washington University Coronary Artery Disease Study | 2: ANVIL_CCDG_WashU_CVD_EOCAD_WashU_C… | 0 | Selected Publications empty |
| phs001259 | CCDG CVD: VIRGO - Variation in Recover-Role of Gender on Outcomes of Young Acute Myocardial Infarction (AMI) Patients | 1: ANVIL_CCDG_Broad_CVD_EOCAD_VIRGO_W… | 12 | [25271209](https://pubmed.ncbi.nlm.nih.gov/25271209/) (2014) — Effect of low perceived social support on health outcomes in young patients with acute myocardial infarction: results from the VIRGO (Variation in Recovery: Role of Gender on Outcomes of Young AMI Patients) study. |
| phs001272 | Broad Institute Center for Mendelian Genomics | 9: ANVIL_CMG_Broad_Blood_Gazda_WES… | 0 | Selected Publications empty |
| phs001300 | NABEC: North American Brain Expression Consortium | 1: AnVIL_NIA_CARD_LR_WGS_NABEC_GRU_V2 | 48 | [20485568](https://pubmed.ncbi.nlm.nih.gov/20485568/) (2010) — Abundant quantitative trait loci exist for DNA methylation and gene expression in human brain. |
| phs001398 | Center for Common Disease Genomics [CCDG] - Cardiovascular: The Bangladesh Risk of Acute Vascular Events (BRAVE) Study | 2: ANVIL_CCDG_Broad_CVD_Stroke_BRAVE_… | 0 | Selected Publications empty |
| phs001487 | Center Common Disease Genomics [CCDG] - CVD - TAICHI | 1: ANVIL_CCDG_Broad_CVD_EOCAD_TaiChi_… | 0 | Selected Publications empty |
| phs001489 | Center for Common Disease Genomics [CCDG] - Neuropsychiatric: Epilepsy: Epi25 Consortium | 149: ANVIL_CCDG_Broad_NP_Epilepsy_AUSAL… | 4 | [31327507](https://pubmed.ncbi.nlm.nih.gov/31327507/) (2019) — Ultra-Rare Genetic Variation in the Epilepsies: A Whole-Exome Sequencing Study of 17,606 Individuals. |
| phs001579 | Center for Common Disease Genomics (CCDG)-Cardiovascular: METSIM (METabolic Syndrome In Men) Study | 1: ANVIL_CCDG_WashU_CVD_EOCAD_METSIM_… | 0 | no dbGaP FTP directory (HTTP 404) |
| phs001584 | eMERGE Network Phase III: HRC Imputed Array Data | 10: ANVIL_eMERGE_GWAS_DS_CHILDD… | 37 | [17903304](https://pubmed.ncbi.nlm.nih.gov/17903304/) (2007) — Framingham Heart Study 100K project: genome-wide associations for cardiovascular disease outcomes. |
| phs001585 | Identification of ALS Associated Genes Using Whole Genome Sequencing | 1: ANVIL_ALS_FTD_ALS_AssociatedGenes_… | 1 | [27455347](https://pubmed.ncbi.nlm.nih.gov/27455347/) (2016) — NEK1 variants confer susceptibility to amyotrophic lateral sclerosis. |
| phs001592 | Center for Common Disease Genomics [CCDG] - Cardiovascular ATVB: Atherosclerosis Thrombosis and Vascular Biology | 1: ANVIL_CCDG_Broad_MI_ATVB_DS_CVD_WE… | 0 | Selected Publications empty |
| phs001616 | eMERGE Network Phase III Clinical Sequencing: eMERGEseq Panel | 9: ANVIL_eMERGE_eMERGEseq_GRU… | 0 | Selected Publications empty |
| phs001642 | Center for Common Disease Genomics [CCDG] - Autoimmune: Inflammatory Bowel Disease (IBD) Exomes and Genomes | 67: ANVIL_CCDG_Broad_AI_IBD_Brant_HMB_… | 0 | Selected Publications empty |
| phs001676 | CCDG- Neuropsychiatric: Autism - Simons Simplex Collection (SSC) | 1: ANVIL_CCDG_NYGC_NP_Autism_SSC_WGS | 13 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs001740 | CCDG- Neuropsychiatric: Autism- Study of Autism Genetics Exploration (SAGE) | 1: ANVIL_CCDG_NYGC_NP_Autism_SAGE_WGS | 13 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs001741 | CCDG- Neuropsychiatric: Autism- The Autism Simplex Collection (TASC) | 1: ANVIL_ccdg_nygc_np_autism_tasc_wgs | 13 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs001746 | A Genomic Atlas of Systemic Interindividual Epigenetic Variation in Humans (GTEx) | 1: ANVIL_GTEx_BCM_GRU_CoRSIVs | 3 | [34341337](https://pubmed.ncbi.nlm.nih.gov/34341337/) (2021) — A machine learning case-control classifier for schizophrenia based on DNA methylation in blood. |
| phs001766 | CCDG-Neuropsychiatric: Autism- Autism Genetic Resource Exchange (AGRE) | 1: ANVIL_CCDG_NYGC_NP_Autism_AGRE_WGS | 13 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs001871 | Center for Common Disease Genomics (CCDG)-Cardiovascular:Cleveland Clinic | 1: ANVIL_ccdg_washu_cvd_eocad_clevela… | 0 | Selected Publications empty |
| phs001880 | Center for Common Disease Genomics (CCDG) - Cardiovascular: Emory Cohort | 1: ANVIL_ccdg_washu_cvd_eocad_emory_w… | 0 | Selected Publications empty |
| phs001894 | CCDG-Neuropsychiatric: Autism- Genetics of Human Developmental Brain Disorders | 1: ANVIL_ccdg_nygc_np_autism_hmca_wgs | 11 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs001913 | CCDG - Cardiovascular: eMERGE - Northwestern Cohort | 1: ANVIL_ccdg_washu_cvd_eocad_emerge_… | 0 | Selected Publications empty |
| phs001963 | DEMENTIA-SEQ: WGS in Lewy Body Dementia and Frontotemporal Dementia | 1: ANVIL_ALS_FTD_DEMENTIA_SEQ_GRU_v1 | 7 | [16237129](https://pubmed.ncbi.nlm.nih.gov/16237129/) (2005) — Diagnosis and management of dementia with Lewy bodies: third report of the DLB Consortium. |
| phs002004 | CCDG-Neuropsychiatric: A Study of the Genetic Causes of Complex Pediatric Disorders | 1: ANVIL_CCDG_NYGC_NP_Autism_CAG_DS_W… | 13 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs002018 | Center Common Disease Genomics [CCDG] - Cardiovascular: Partners Biobank | 2: ANVIL_CCDG_Broad_CVD_EOCAD_Partner… | 0 | Selected Publications empty |
| phs002032 | Genetic Neuroscience: How Human Genes and Alleles Shape Neuronal Phenotypes | 4: ANVIL_NIMH_Broad_ConvergentNeuro_M… | 2 | [36796362](https://pubmed.ncbi.nlm.nih.gov/36796362/) (2023) — Natural variation in gene expression and viral susceptibility revealed by neural progenitor cell villages. |
| phs002041 | WGSPD Project 1: Whole Genome Sequencing for Schizophrenia and Bipolar Disorder | 5: ANVIL_NIMH_Broad_WGSPD1_McCarroll_… | 0 | Selected Publications empty |
| phs002042 | CCDG Neuropsychiatric: Autism Center of Excellence (ACE II) | 2: ANVIL_CCDG_NYGC_NP_Autism_ACE2_DS_… | 13 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs002043 | CCDG Neuropsychiatric: Multimodal Developmental Neurogenetics of Females | 2: ANVIL_CCDG_NYGC_NP_Autism_PELPHREY… | 13 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs002044 | CCDG-Neuropsychiatric: Victorian Collaborative AuTism Study (CATS) | 1: ANVIL_CCDG_NYGC_NP_Autism_HFA_DS_W… | 13 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs002111 | CSER: Exome Sequencing in Diverse Populations in Colorado and Oregon/CHARM Cancer Health Assessments Reaching Many | 1: ANVIL_CSER_CHARM_GRU | 20 | [30193136](https://pubmed.ncbi.nlm.nih.gov/30193136/) (2018) — The Clinical Sequencing Evidence-Generating Research Consortium: Integrating Genomic Sequencing in Diverse and Medically Underserved Populations. |
| phs002205 | Center for Common Disease Genomics [CCDG] - Inflammatory Bowel Disease (IBD) - Global Microbiome Conservancy Host Exomes | 1: ANVIL_ccdg_broad_ai_ibd_alm_gmc_we… | 0 | Selected Publications empty |
| phs002206 | Genomic Answers for Kids (GA4K) | 1: AnVIL_CMH_GAFK_R5 | 0 | Selected Publications empty |
| phs002236 | Center for Common Disease Genomics [CCDG] - Cardiovascular: Genetic and Phenotypic Determinants of Blood Pressure and Other Cardiovascular Risk Factors | 2: ANVIL_CCDG_Broad_CVD_AF_GAPP_DS_MD… | 0 | Selected Publications empty |
| phs002242 | Center for Common Disease Genomics [CCDG] - Cardiovascular: SWISS-AF/SWISS-AF-PVI/BEAT-AF | 2: ANVIL_CCDG_Broad_CVD_AF_Swiss_Case… | 2 | [17903304](https://pubmed.ncbi.nlm.nih.gov/17903304/) (2007) — Framingham Heart Study 100K project: genome-wide associations for cardiovascular disease outcomes. |
| phs002243 | Center for Common Disease Genomics [CCDG] - Cardiovascular:  PEGASUS-TIMI 54 | 1: ANVIL_CCDG_Broad_CVD_AF_PEGASUS_HM… | 0 | Selected Publications empty |
| phs002307 | CSER: South-Seq: DNA Sequencing for Newborn Nurseries in the South | 1: ANVIL_CSER_SouthSeq_GRU | 0 | Selected Publications empty |
| phs002324 | CSER: Genomic Sequencing to Aid Diagnosis in Pediatric and Prenatal Practice: Examining Clinical Utility, Ethical Implications, Payer Coverage, and Data Integration in a Diverse Population | 1: ANVIL_CSER_P3EGS_GRU | 0 | Selected Publications empty |
| phs002337 | CSER: Incorporating Genomics into the Clinical Care of Diverse NYC Children (NYCKidSeq) | 2: ANVIL_CSER_NYCKIDSEQ_GRU… | 1 | [33446240](https://pubmed.ncbi.nlm.nih.gov/33446240/) (2021) — The NYCKidSeq project: study protocol for a randomized controlled trial incorporating genomics into the clinical care of diverse New York City children. |
| phs002378 | CSER: Evaluating Utility and Improving Implementation of Genomic Sequencing for Pediatric Cancer Patients in the Diverse Population and Healthcare Settings of Texas: The KidsCanSeq Study | 1: ANVIL_CSER_KidsCanSeq_GRU | 5 | [30193136](https://pubmed.ncbi.nlm.nih.gov/30193136/) (2018) — The Clinical Sequencing Evidence-Generating Research Consortium: Integrating Genomic Sequencing in Diverse and Medically Underserved Populations. |
| phs002502 | Center for Common Disease Genomics [CCDG] Neuropsychiatric: Autism Spectrum Disorder (ASD) – Whole Exomes | 34: ANVIL_ccdg_asc_ndd_daly_talkowski_… | 7 | [31981491](https://pubmed.ncbi.nlm.nih.gov/31981491/) (2020) — Large-Scale Exome Sequencing Study Implicates Both Developmental and Functional Changes in the Neurobiology of Autism. |
| phs002509 | Center for Common Disease Genomics [CCDG] - Neuropsychiatric: Genomics of Autism Spectrum Disorder (GASD) | 1: ANVIL_CCDG_NYGC_NP_Autism_GASD_GRU… | 11 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs002511 | Center for Common Disease Genomics [CCDG] - Neuropsychiatric: SPARK Simons Foundation Powering Autism Research for Knowledge | 1: ANVIL_CCDG_NYGC_NP_Autism_SPARK_GR… | 11 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs002512 | Center for Common Disease Genomics [CCDG] - Neuropsychiatric: Simons Searchlight | 1: ANVIL_CCDG_NYGC_NP_Autism_SEARCHLI… | 11 | [28630308](https://pubmed.ncbi.nlm.nih.gov/28630308/) (2017) — Measuring shared variants in cohorts of discordant siblings with applications to autism. |
| phs002726 | Center for Common Disease Genomics [CCDG] - Cardiovascular: Cardiology Biobanking for Biomarker Discovery | 2: ANVIL_CCDG_Broad_CVD_AF_Figtree_Bi… | 0 | Selected Publications empty |
| phs003018 | A Comprehensive Binding and Functional Map of Human RNA-binding Proteins | 2: AnVIL_ENCORE_293T… | 0 | no dbGaP FTP directory (HTTP 404) |
| phs003047 | NHGRI GREGoR Consortium: Genomics Research to Elucidate the Genetics of Rare Disease | 9: ANVIL_GREGoR_R01_HMB… | 2 | [41224980](https://pubmed.ncbi.nlm.nih.gov/41224980/) (2025) — GREGoR: accelerating genomics for rare diseases. |
| phs003181 | NABEC Long-Read Whole-Genome Sequencing | 1: ANVIL_NIA_CARD_LR_WGS_NABEC_GRU | 0 | no dbGaP FTP directory (HTTP 404) |
| phs003184 | ALS Compute | 1: ANVIL_ALSCompute_Collection_GRU | 0 | Selected Publications empty |
| phs003193 | Fetal Genomics Consortium (FGC) | 1: ANVIL_FetalGenomics_PrenatalSEQ | 0 | Selected Publications empty |
| phs003200 | High-Throughput RNA Isoform Sequencing using Programmable cDNA Concatenation | 1: ANVIL_MAS_ISO_seq | 0 | Selected Publications empty |
| phs003224 | NIA CARD Coriell Cell Lines | 1: ANVIL_NIA_CARD_Coriell_Cell_Lines_… | 0 | no dbGaP FTP directory (HTTP 404) |
| phs003444 | The Cancer Dependency Map (DepMap) | 4: ANVIL_DepMap_HMB… | 0 | Selected Publications empty |
| phs003472 | Impact of Genomic Variation on Function (IGVF) Consortium | 6: AnVIL_IGVF_GRU_PUB_NPU_R1… | 0 | Selected Publications empty |
| phs003499 | Center for Common Disease Genomics (CCDG) - Cardiovascular: Multiethnic Cohort | 2: ANVIL_CCDG_WashU_CVD_MultiEthnic_W… | 0 | Selected Publications empty |
| phs003537 | HudsonAlpha Long Read Sequencing Data of Individuals with Rare Suspected Genetic Conditions | 1: ANVIL_HudsonAlpha_LR_v1_GRU | 6 | [38585854](https://pubmed.ncbi.nlm.nih.gov/38585854/) (2024) — Long-read genome sequencing and variant reanalysis increase diagnostic yield in neurodevelopmental disorders. |
| phs003821 | OurHealth - Cardiovascular Disease in South Asians | 2: AnVIL_OurHealth_GRU_R1… | 0 | Selected Publications empty |
| phs003838 | Developmental Genotype Tissue Expression (dGTEx) Project | 1: ANVIL_dGTEx_GRU_v1 | 1 | [39815096](https://pubmed.ncbi.nlm.nih.gov/39815096/) (2025) — The human and non-human primate developmental GTEx projects. |
| phs004000 | Assessment of Complex Chromosomal Changes in De-Identified Cell Lines | 1: AnVIL_Complex_Chromosomal_Changes_… | 0 | Selected Publications empty |
| phs004045 | Genetic Testing to Understand and Address Renal Disease Disparities across the United States (GUARDD-US) | 2: AnVIL_GUARDD_US_GRU_R1… | 2 | [35660539](https://pubmed.ncbi.nlm.nih.gov/35660539/) (2022) — Design and rationale of GUARDD-US: A pragmatic, randomized trial of genetic testing for APOL1 and pharmacogenomic predictors of antihypertensive efficacy in patients with hypertension. |
| phs004058 | A Depression and Opioid Pragmatic Trial in Pharmacogenetics (ADOPT PGx): Acute Pain Trial | 2: AnVIL_ADOPT_PGx_Acute_Pain_GRU_R1… | 2 | [35899435](https://pubmed.ncbi.nlm.nih.gov/35899435/) (2022) — Implementing a pragmatic clinical trial to tailor opioids for acute pain on behalf of the IGNITE ADOPT PGx investigators. |
| phs004069 | A Depression and Opioid Pragmatic Trial in Pharmacogenetics (ADOPT PGx): Depression Trial | 2: AnVIL_ADOPT_PGx_Depression_GRU_R1… | 2 | [38860639](https://pubmed.ncbi.nlm.nih.gov/38860639/) (2024) — Rationale and design for a pragmatic randomized trial to assess gene-based prescribing for SSRIs in the treatment of depression. |
| phs004430 | Center for Common Disease Genomics (CCDG) - Neuropsychiatric: Introduction of Exome/Genome Sequencing | 1: ANVIL_CCDG_NYGC_NP_Autism_AFS_DS_W… | 0 | Selected Publications empty |

## RePORTER probe of the empty-list CCDG studies (2026-08-15)

The 12 CCDG studies with empty Selected Publications lists *known at the
time of this pass* (2026-08-15, before the sweep grew to 74 studies) were
run through the grant channel (study page attribution → grant serials →
`reporter`). Four further empty CCDG-program studies (CCDG in the study
title or, for phs001227, in its workspace names) surfaced in the
regenerated table: phs001227, phs001913, phs002205, phs002726 — probed by
the cohort-name channel in the 2026-08-18 rerun below (BioHEART resolved,
IBD/Alm candidate, WUCADS and NUgene unresolved), still un-probed by the
grant channel. Outcome of the 12-study grant probe: **the channel
resolves but does not isolate cohort papers**:

- 6/12 study pages list **no grant numbers at all** in their fetched
  attribution HTML (phs001398, phs001579, phs001880, phs002018, phs002236,
  phs002243) — the grant channel cannot start.
- 5/12 list exactly **one shared center grant** (Broad `HG008895` ×3, WashU
  `HG008853`, NYGC `HG008901`), so RePORTER returns the *center's* whole
  publication list (47–118 papers) with no ranking signal — a single grant
  gives every paper the same link count, and the papers are center-wide
  (e.g. the same three Broad cardiovascular papers top TAICHI, MI-ATVB, and
  the IBD study alike), not specific to the sub-cohort.
- phs001871 matched serial `HG000885` with 0 linked publications — possibly
  a false-positive match on the page rather than a real grant.

Takeaway for Epic 2: for sequencing-center deposits (CCDG, CMG), neither
the Selected Publications list nor the grant channel identifies a
study-specific marker paper. The working fallback is a **cohort-name
search** — these deposits wrap long-running named cohorts whose founding
papers predate the CCDG deposit. Run below.

## Cohort-name search pass (rerun 2026-08-18 under the query discipline)

Originally run 2026-08-15 over the 12 then-known empty-list CCDG studies;
rerun 2026-08-18 under SKILL.md's query discipline — every query recorded
verbatim (hits and misses alike), ≤5 queries per study — and extended to
the 4 empty-CCDG newcomers the regenerated table surfaced. The verbatim
query log was trimmed from this doc for readability; it lives in this
file's git history (commit 75c8236). Leads came
from the dbGaP study titles and the dataset records (descriptions named
WUCADS, the NUgene biobank, and the Figtree/BioHeart workspaces named
BioHEART). Result: **12/16 studies have a marker candidate** (11 firm
candidates + ATVB retained with a reproducibility caveat); unresolved:
Cleveland GeneBank, Autism AFS, WUCADS, NUgene. Candidate identities were
subsequently checked against study records in the abstract verification
pass below (which caught and corrected one mismatch, phs002205); role
confirmation by reading full papers is Epic 2.

| phs | cohort | candidate PMID (year) — title | strength |
| --- | --- | --- | --- |
| phs001398 | BRAVE | [25930055](https://pubmed.ncbi.nlm.nih.gov/25930055/) (2015) — The Bangladesh Risk of Acute Vascular Events (BRAVE) Study: objectives and design | strong — design paper |
| phs001487 | TAICHI | [26982883](https://pubmed.ncbi.nlm.nih.gov/26982883/) (2016) — Genetics of Coronary Artery Disease in Taiwan: A Cardiometabochip Study by the Taichi Consortium | strong — consortium paper |
| phs001579 | METSIM | [28119442](https://pubmed.ncbi.nlm.nih.gov/28119442/) (2017) — The Metabolic Syndrome in Men study: a resource for studies of metabolic and cardiovascular diseases | strong — resource paper |
| phs001592 | ATVB (Italian) | [12615788](https://pubmed.ncbi.nlm.nih.gov/12615788/) (2003) — early ATVB Italian Study Group genetics paper | unclear role, cohort abstract-verified — the abstract's cohort (1210 first-MI survivors <45, nationwide Italian case-control + 1210 matched controls) matches the deposit; but it is an association paper, not a design paper, and the rerun's 5 queries did not re-surface it |
| phs001642 | IBD (Broad/Daly) | [42180385](https://pubmed.ncbi.nlm.nih.gov/42180385/) (2026) — Exome sequencing directly implicates 68 genes in inflammatory bowel disease | candidate — unread; program-scale flagship |
| phs001871 | Cleveland Clinic GeneBank | — | none — 5 queries; only papers *using* GeneBank samples surfaced, no cohort-profile paper |
| phs001880 | Emory (EmCAB) | [29288185](https://pubmed.ncbi.nlm.nih.gov/29288185/) (2017) — Cohort profile: the Emory Cardiovascular Biobank (EmCAB) | strong — cohort profile |
| phs002018 | Partners Biobank | [26784234](https://pubmed.ncbi.nlm.nih.gov/26784234/) (2016) — Building the Partners HealthCare Biobank at Partners Personalized Medicine | strong — biobank description |
| phs002236 | GAPP | [23299990](https://pubmed.ncbi.nlm.nih.gov/23299990/) (2013) — Genetic and phenotypic determinants of blood pressure and other cardiovascular risk factors (GAPP) | strong — title matches the dbGaP study title verbatim |
| phs002243 | PEGASUS-TIMI 54 | [24655690](https://pubmed.ncbi.nlm.nih.gov/24655690/) (2014) — Design and rationale for the Prevention of Cardiovascular Events… (PEGASUS-TIMI 54) trial | strong — trial design paper |
| phs003499 | Multiethnic Cohort | [10695593](https://pubmed.ncbi.nlm.nih.gov/10695593/) (2000) — A multiethnic cohort in Hawaii and Los Angeles: baseline characteristics | strong — same MEC marker as phs000220 (PAGE MEC) |
| phs004430 | Autism AFS (NYGC) | — | none — 2 queries; cohort identity ("AFS") not resolvable from the title or dataset record, leads exhausted |
| phs001227 | WUCADS (WashU CAD) | — | none — 3 queries; "WUCADS" absent from PubMed, cohort apparently undescribed in the literature |
| phs001913 | NUgene (Northwestern) | — | none — 3 queries; NUgene appears only as a sample source in 12 papers, no biobank-description paper found |
| phs002205 | GMbC (Alm) | [33794144](https://pubmed.ncbi.nlm.nih.gov/33794144/) (2021) — Elevated rates of horizontal gene transfer in the industrialized human microbiome | candidate — GMbC flagship results paper (Groussin/Alm, Cell); no dedicated cohort-profile paper found. Previous candidate 31142855 (iHMP/IBDMDB) was a verification-caught mismatch: the study description names the Global Microbiome Conservancy (gmc = GMbC) and links companion study phs002235 |
| phs002726 | BioHEART-CT | [31537558](https://pubmed.ncbi.nlm.nih.gov/31537558/) (2019) — Biobanking for discovery of novel cardiovascular biomarkers…: protocol for the… BioHEART-CT cohort study | strong — protocol paper |

### Channel ranking and search lessons

Channel ranking that emerges for center-style deposits: cohort-name search
≫ grant channel ≈ Selected Publications (both empty/uninformative). The
skill's SKILL.md fallback ordering already reflects this pattern. Rerun
lessons: recency-sorted esearch buries decades-old markers under the
cohort's ongoing output (a date-range term like `2000:2000[dp]` recovers
them), and acronym collisions ("Bioheart" scaffold trials, tai-chi
papers) make a hyphenated/context-qualified form the better query.

### Abstract verification pass (2026-08-18)

Every candidate's PubMed abstract was fetched and checked against the
study's dbGaP/dataset description on identifying facts (cohort name,
enrollment, geography, institution, design). This is identity
verification only — role confirmation by reading full papers stays
Epic 2.

**Abstract-verified** (the abstract's cohort facts match the study
record): BRAVE (~8000 Bangladeshi first-MI cases + matched controls,
Cambridge-led — the dataset description names the same study), TAICHI
(8556 Taiwanese CAD cases/controls, TAICHI Consortium), METSIM (10,197
Finnish men, Kuopio), EmCAB (~7000 Emory catheterisation patients,
Atlanta), Partners (>30,000-subject Boston biobank launched 2010), GAPP
(1,333 healthy 25–41-year-olds, Liechtenstein; title verbatim in the
dbGaP study title), PEGASUS-TIMI 54 (the 21,000-patient ticagrelor
trial), MEC (215,251 adults, Hawaii/LA, five ethnic groups — the phs003499
dbGaP description names the University of Hawaii/USC Multiethnic Cohort
and links phs002183), BioHEART-CT (5000 CTCA patients, Sydney, Figtree
senior author matching the workspace name), NCGENES2 (both papers: the
UNC pediatric first-line-ES RCT and its 101-participant sequencing-arm
results), and ATVB (cohort verified, role still unclear — see table).

**Mismatch caught and corrected**: phs002205 — the previous candidate
31142855 (iHMP/IBDMDB) describes a 132-subject longitudinal Boston-area
IBD cohort, but the study description names the **Global Microbiome
Conservancy** (diverse/indigenous populations worldwide, gut microbiome +
human WGS/WES, companion microbiome study phs002235). Replaced with the
GMbC flagship 33794144; the workspace's `ibd_alm` tokens reflect the
Broad IBD working group and the Alm lab, not the cohort.

**Consistent but not identity-proof**: IBD-Daly 42180385 (Daly/Broad
authorship and IBD exomes match the program; whether this deposit's
samples are in the 86,213-case meta-analysis is not determinable from the
abstract). **Unverifiable**: ALSCompute 35115730 (the abstract describes
Answer ALS precisely, but the workspace description names no source
consortium, so the collection's identity remains open).

## Fallback pass over the remaining empty-list studies (2026-08-18)

The 13 empty-list studies not covered by the CCDG cohort-name pass or a
dossier had stopped at source 1 — the fallback chain (dataset-record
leads → PubMed title/name search, ≤5 recorded queries per study) had
never run for them. Result: **10/13 have a marker candidate** (8 strong,
SouthSeq as a candidate, P3EGS covered by its program marker);
unresolved: ALS Compute, PrenatalSEQ, and the phs004000 pilot.

| phs | program/cohort | candidate PMID (year) — title | strength |
| --- | --- | --- | --- |
| phs001272 | Broad CMG | [22628075](https://pubmed.ncbi.nlm.nih.gov/22628075/) (2012) — The Centers for Mendelian Genomics: a new large-scale initiative to identify the genes underlying rare Mendelian conditions; also [35148959](https://pubmed.ncbi.nlm.nih.gov/35148959/) (2022) decade retrospective | strong — CMG program markers (program-wide; no Broad-specific description paper surfaced) |
| phs001616 | eMERGEseq panel | [31447099](https://pubmed.ncbi.nlm.nih.gov/31447099/) (2019) — Harmonizing Clinical Sequencing and Interpretation for the eMERGE III Network | strong — the panel's design paper |
| phs002041 | Genomic Psychiatry Cohort (WGSPD1) | [23650244](https://pubmed.ncbi.nlm.nih.gov/23650244/) (2013) — The genomic psychiatry cohort: partners in discovery | strong — cohort marker; the study description names the GPC |
| phs002206 | Genomic Answers for Kids (GA4K) | [35305867](https://pubmed.ncbi.nlm.nih.gov/35305867/) (2022) — Genomic answers for children: Dynamic analyses of >1000 pediatric rare disease genomes | strong — program flagship |
| phs002307 | SouthSeq (CSER) | [34930662](https://pubmed.ncbi.nlm.nih.gov/34930662/) (2022) — Genome sequencing as a first-line diagnostic test for hospitalized infants | candidate — surfaced by the SouthSeq full-text term; title does not name the cohort |
| phs002324 | P3EGS (CSER) | — | no dedicated marker; the CSER consortium marker [30193136](https://pubmed.ncbi.nlm.nih.gov/30193136/) covers the program (2 queries: only perspective/payer papers) |
| phs003181 | NABEC long-read | [39764002](https://pubmed.ncbi.nlm.nih.gov/39764002/) (2024) — Long-read sequencing of hundreds of diverse brains provides insight into the impact of structural variation… | strong candidate — matches the deposit's assay (ONT long-read on NABEC brains) |
| phs003184 | ALS Compute (GRU) | — | unresolved (1 query) — description names no source consortium; the sibling ALSCompute workspaces' Answer ALS candidate may apply |
| phs003193 | FGC PrenatalSEQ | — | unresolved (2 queries) — only a case report citing PrenatalSEQ; no consortium marker found |
| phs003200 | MAS-ISO-seq | [37291427](https://pubmed.ncbi.nlm.nih.gov/37291427/) (2024) — High-throughput RNA isoform sequencing using programmed cDNA concatenation | strong — the method paper; title matches the dbGaP study title |
| phs003444 | DepMap | [28753430](https://pubmed.ncbi.nlm.nih.gov/28753430/) (2017) — Defining a Cancer Dependency Map | strong — program marker |
| phs003821 | OurHealth | [41545632](https://pubmed.ncbi.nlm.nih.gov/41545632/) (2026) — The OurHealth Study: A digital genomic cohort for cardiometabolic risk mechanisms in US South Asians | strong — cohort design paper matching the dbGaP title |
| phs004000 | Coriell complex-chromosomal pilot | — | unresolved (1 query) — 16-sample pilot per its description; no publication found |

## Workspaces with no phs accession

These have no dbGaP anchor; the open-access ones among them have dossiers
here with title-search-based publications. The three controlled-access
no-phs workspaces were searched by cohort name (2026-08-17; rerun
2026-08-18 with queries recorded, ✓ = surfacing query):

- **ANVIL_CSER_NCGENES2_GRU** — resolved: PMID 34127041 (2021,
  clinical-utility trial design matching the workspace description) and
  PMID 41935954 (2026, "Exome sequencing early in outpatient evaluation in
  NCGENES 2" results paper). Strong candidates. Queries: ✓ `NCGENES[tiab]`
  (one query surfaced both).
- **ANVIL_ALSCompute_Collection_HMB** — candidate with caveat: PMID
  35115730 (2022, "Answer ALS, a large-scale resource…"). The workspace
  description names no source consortium, so whether this collection is
  Answer ALS data is unverified — role unclear. Queries:
  ✓ `answer[Title] AND ALS[Title]`; `ALS[tiab] AND compute[tiab]` (miss —
  unrelated computational papers).
- **ANVIL_ccdg_broad_mi_univutah_ds_cvd_wes** — unresolved after 5
  recorded queries: the description's specific cohort (653 early
  MI/revascularization survivors plus matched controls, Utah) surfaced
  only older Utah family-study papers, none clearly describing this
  cohort. Queries (all missed): `myocardial[Title] AND infarction[Title]
  AND Utah[tiab]`; `premature[tiab] AND coronary[tiab] AND Utah[tiab] AND
  families[tiab]`; `early[tiab] AND myocardial infarction[tiab] AND Salt
  Lake City[tiab]`; `myocardial[tiab] AND infarction[tiab] AND
  survivors[tiab] AND Utah[tiab]`; `coronary[tiab] AND disease[tiab] AND
  Utah[tiab] AND pedigrees[tiab]`.

Full list:

- ANVIL_1000G_PRIMED_data_model
- ANVIL_1000G_high_coverage_2019
- ANVIL_ALSCompute_Collection_HMB
- ANVIL_CSER_NCGENES2_GRU
- ANVIL_GTEx_public_data
- ANVIL_HPRC
- ANVIL_NIMH_Broad_ConvNeuro_McCarroll_Nehme_Levy_CIRM_DS_Village
- ANVIL_T2T
- ANVIL_T2T_CHRY
- ANVIL_ccdg_broad_mi_univutah_ds_cvd_wes
- ANVIL_nhp_dGTEx_V1
- AnVIL_HPRC_R2
- AnVIL_MAGE
