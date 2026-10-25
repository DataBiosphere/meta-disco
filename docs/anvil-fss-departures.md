# Where meta-disco's metadata departs from AnVIL's FSS

Last updated 2026-10-25.

AnVIL's Findability Subset Schema (FSS) names the fields a dataset's files, donors, biosamples and activities carry, and for some of them the values to use. meta-disco writes its answers for AnVIL, so it follows FSS where it can. This file lists each place it does not: a value FSS recommends that meta-disco leaves out, one it adds, one it spells another way, or a field it has that FSS does not. Each entry says what differs and what, if anything, we would ask FSS's, MODAL's or AnVIL's maintainers to change; entries 1, 3 and 4 also say why. Nothing here has been sent yet.

This file is the list. Add a departure here by pull request, in the same pull request that makes it, checked against FSS's release schema rather than from memory. That schema is `content/release/anvil/AnVILDataSubmissionFindabilitySubsetSchema.linkml.yaml` in [DataBiosphere/biocore-data-model](https://github.com/DataBiosphere/biocore-data-model), release 1.0, read at commit `e5a231e` (2024-10-11). FSS's `data_modality` values are the Broad's [MODAL](https://github.com/broadinstitute/modal) ontology's labels; MODAL's text below is `DataModality.ttl` at commit `8eef18c` (2025-05-19).

FSS binds a field to its values in one of two ways, and the entries depend on which. `phenotypic_sex` and `biosample_type` have their enum as `range`, so the values are the field's. `data_modality` and `activity_type` have a string `range`, and FSS lists their values as enums (`DataModalityValues`, `ActivityTypes`) without binding them, so those values are recommended rather than required.

| # | Field | Departure | Ask |
| --- | --- | --- | --- |
| 1 | `data_modality` | MODAL's four children of `genomic` left out | MODAL and FSS: drop or deprecate them |
| 2 | `data_modality` | One value per file, spelled as a dotted path | None |
| 3 | `activity_type` | Ten activity types of our own beside FSS's eleven | FSS: whether to adopt them |
| 4 | `phenotypic_sex`, `biosample_type` | AnVIL's published spellings, not FSS's | AnVIL: publish FSS's values |
| 5 | `reference_assembly` | One NCBI assembly name per file | None |
| 6 | Six of ours | Fields FSS does not have | None |

## 1. data\_modality: MODAL's four children of `genomic` left out

MODAL defines a data modality as "the biological nature of information gathered as the result of an experimental activity, independent of the technology or methods used to produce the information", and FSS's `data_modality` field description says the same. Four of MODAL's terms name a method or a product instead (#756):

| MODAL term | MODAL's own text | What it is | Where meta-disco records it |
| --- | --- | --- | --- |
| `assembly` (0000011) | a label, no definition or comment | what a file holds | `data_type: assembly` |
| `exome` (0000012) | altLabel `WES` | an assay | `assay_type: WES` |
| `whole genome` (0000014) | altLabel `WGS` | an assay | `assay_type: WGS` |
| `genotyping` (0000013) | definition from EDAM's operation Genotyping (`operation_3196`); comment: "intended to differentiate from larger scale genomic sequencing -- exome, genome" | an assay, or an analysis | `assay_type: Genotyping array` |

Their biology is `genomic`, so meta-disco gives these files `genomic` and records the method on the dimension that holds methods. This keeps one fact in one place: a file whose modality said `whole genome` and whose assay said `WES` would contradict itself.

**Files.** The one rule that gave any of the four gave `genotyping` to HPRC's 160 Omni2.5 genotyping IDATs, which are now `genomic`, with `assay_type: Genotyping array`.

**Ask.** For MODAL: deprecate the four, or move them out of the modality tree, with a pointer to the assay or data-type term each corresponds to. For FSS: drop `assembly`, `exome`, `genotyping` and `whole genome` from `DataModalityValues`.

## 2. data\_modality: one value per file, spelled as a dotted path

FSS's `data_modality` is multivalued, and its values are MODAL's labels (`DNA methylation`, `whole genome`). meta-disco stores one value per file, the most specific its evidence supports, spelled as the term's path in MODAL's tree (`epigenomic.methylation`). Each value carries its MODAL id as `meaning` (`MODAL:0000008`), and FSS's spelling is that term's MODAL label (`DNA methylation`); `title` is the label with its first letter capitalised (`Genomic` for FSS's `genomic`), so it matches FSS's spelling only where the label already starts with a capital.

## 3. activity\_type: ten activity types of our own

meta-disco's `activity_type` holds FSS's eleven `ActivityTypes` as FSS spells them, plus ten of its own, each under the term it narrows: `AssemblyActivity`, `CohortDefinitionActivity`, `CohortMergeActivity`, `CoverageActivity`, `JointGenotypingActivity`, `LiftoverActivity`, `MergeActivity`, `QualityControlActivity`, `VariantFilterActivity` and `VariantProcessingActivity` (ADR-0002, #580). They exist because what crosses a step from a file's parents depends on the kind of step, and FSS's `AnalysisActivity` is too broad to say what passes (`rules/activities.yaml`).

**Ask.** For FSS: whether any belong in `ActivityTypes`.

## 4. phenotypic\_sex and biosample\_type: AnVIL's published spellings

FSS binds `phenotypic_sex` to `female`, `male`, `intersex` and `prefer not to say`, and `biosample_type` to a list of thirty-two that includes `tissue`. AnVIL's published `anvil_donor` and `anvil_biosample` tables write capitalised values (`Female`, `Male`, `Tissue`), and meta-disco carries those as AnVIL writes them (#693, #699). It lists a sex only where a source writes it, so `intersex` and `prefer not to say` are absent.

**Ask.** For AnVIL: publish FSS's spellings, or say which spelling is canonical.

## 5. reference\_assembly: one NCBI assembly name per file

FSS's `reference_assembly` is a multivalued string that "may be defined by" the GRC, with no list of values. meta-disco stores one value per file, from a tree whose parents span releases (`CHM13` above `T2T-CHM13v2.0`, #473): an assembly as NCBI names it, or, for a reference that grafts another genome's chrY onto a CHM13 release, which NCBI does not name, the basename of the reference FASTA that files declare (`CHM13Y_EBV_v1.1`).

## 6. Fields FSS does not have

meta-disco answers six dimensions of a file that FSS has no field for: `assay_type` (EFO's assay terms, #533), `data_type`, `platform`, `instrument_model`, `variant_kind` and `variant_origin`. FSS's `file_format` is a field meta-disco does not answer.
