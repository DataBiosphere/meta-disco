# ADR-0003: One slot per axis — facets, not combined terms

- **Status:** Accepted (2026-10-10, with #654's PR #661); proposed 2026-10-09, when the storage and user model were decided by Dave
- **Amended by:** [#756](https://github.com/DataBiosphere/meta-disco/issues/756) (2026-10-25): MODAL's four children of `genomic` are dropped, so `data_modality` is MODAL less those four, not MODAL as published (decision 4); [#655](https://github.com/DataBiosphere/meta-disco/issues/655) (2026-10-25): variant files are named in `data_type` by what they hold, not by a format slot and a sample-count slot ("How #655 names variant files")
- **Decision record for:** [#654](https://github.com/DataBiosphere/meta-disco/issues/654) (variant kind), [#658](https://github.com/DataBiosphere/meta-disco/issues/658) (variant origin), and the vocabularies it touches
- **Related:** #630, #651, #652, #607 (gVCF), #657 (subterms retired), #580 (activity vocabulary), #563 (MODAL), #533 (EFO), #655 (variant files named), #760 (joint-called)

## Context

A controlled vocabulary in `classification.yaml` is a single-parent `is_a` tree, and a record holds
one term per dimension. Where one tree carries two independent axes, a file that has a value on
both cannot be named, and the fix that suggests itself, a combined term, multiplies with every new
axis. #630 met this in `data_type`: `variants.germline` and `variants.somatic` are an **origin**,
`variants.structural` and `variants.cnv` a **kind**, and a germline callset of SVs, or a callset of
small variants and SVs, has no term.

The same shape is already in other vocabularies (read from the enums, 2026-10-09):

| vocabulary | second axis inside the tree | terms |
|---|---|---|
| `data_type` (ours) | origin | `variants.germline`, `variants.somatic` |
| | kind | `variants.structural`, `variants.cnv` |
| | representation | `variants.germline.gvcf` |
| | role | `assembly.reference`, `pangenome.reference`; next would be variant resources (dbSNP, ClinVar, known-indels, about 220 VCFs) |
| `activity_type` (ours) | the data or scope acted on | `MergeActivity` / `CohortMergeActivity`; `VariantProcessingActivity` / `VariantFilterActivity` |
| `data_modality` (MODAL, adopted) | assay scope; resolution | `genomic.exome`, `genomic.whole_genome` (dropped by #756); `transcriptomic.spatial`, `.targeted` |
| `assay_type` (EFO, adopted) | resolution × molecule | `RNA-seq`, `sc/snRNA-seq`, `snRNA-seq`; the same for ATAC; `SHARE-seq` |

### How ontologies avoid the explosion (from memory unless marked)

- OWL ontologies (CL, Mondo) assert a single-parent tree per axis and *define* a combination by its
  properties; a reasoner computes where it sits. CL's "CD4-positive, alpha-beta T cell" is a T cell
  with CD4 on its membrane, not a class hand-placed under two parents. Mondo generates combination
  classes from design patterns (DOSDP), each with a logical definition.
- A metadata schema without a reasoner keeps axes apart as separate slots, each with its own value
  set; LinkML supports this directly, and binds a slot to an ontology branch with a dynamic enum
  (`reachable_from`), so a large vocabulary need not be listed.

### What EDAM says (read, EDAM 1.25 release of 2026-06-27, `EDAM.owl`)

EDAM is itself faceted: four sub-ontologies, Data, Format, Operation and Topic. For variants:

- **Data** has one term, `data_3498` *Sequence variations*. No subtypes by kind or origin.
- **Format**: `format_3016` *VCF*, with `format_4018` *gVCF* as its subclass. gVCF is a format.
- **Operation**: `operation_3227` *Variant calling*, with children `operation_0484` *SNP detection* and
  `operation_0452` *Indel detection*; beside it `operation_3228` *Structural variation detection*,
  with child `operation_3961` *Copy number variation detection*. *Variant calling*'s own definition
  also names structural variants, and carries "Somatic variant calling" only as a narrow synonym.
- **Topic**: `topic_0199` *Genetic variation* ⊃ `topic_3175` *Structural variation* ⊃ `topic_3958`
  *Copy number variation*.
- **No origin** (germline, somatic) and **no role** (reference) terms. These operations carry no
  `has_input`/`has_output` restrictions in the release.

So EDAM states the kind of a callset through the *operation* that made it, and its representation
through the *format*; it does not subtype the data.

## Decision

1. **One slot per axis.** A dimension holds one axis. An `is_a` tree is used only within an axis.
   Where a file can hold values on two axes at once, each axis is its own slot.
2. **The test:** can one file truly have a value on each axis at once? If yes, split. If each term
   is a named real-world thing (an assembly build, an instrument model), one tree is right.
3. **Bind a slot to an outside ontology where one fits:** EDAM for operations and formats, SO if a
   per-variant class is ever stored; record the term as `meaning`, or bind the slot with a dynamic enum.
4. **Adopted vocabularies stay as published** (MODAL for `data_modality`, EFO for `assay_type`): we
   do not facet them ourselves, and we note where they overlap our facets (`genomic.exome` and `WES`).
   *Amended by #756:* MODAL's four children of `genomic`, the example above among them, are dropped
   rather than kept as overlaps; `docs/anvil-fss-departures.md` gives the reason and lists each
   place our values depart from AnVIL's FSS.
5. **Our own vocabularies are faceted** when a new axis appears, rather than gaining combined terms.

### First application: variants (#654)

| axis | slot | values | from |
|---|---|---|---|
| what it is | `data_type` | `variants` (EDAM `data_3498`) | extension, content |
| representation | file format (VCF, gVCF) | EDAM `format_3016`, `format_4018` | content (#607) |
| kind | `variant_kind` (multivalued) | small, structural (#654); CNV later, when a rule can give it. Bound to EDAM operations `0484`/`0452`, `3228` (and `3961` for CNV) | the producing step's caller (#654); whole-file scan (#652) |
| origin | `variant_origin` | germline, somatic (no EDAM term; SO:0001778, SO:0001777 under SO's `variant_origin`, SO:0001762) | the caller (#658) |

### Storage (decided by Dave, 2026-10-09)

- **A column per facet, dense.** Every record carries every dimension with `{value, status,
  evidence}`, as today; a file outside a facet's scope carries `not_applicable`. The size this adds
  is accepted for now.
- **Single-valued, except where a file truly holds several values.** `variant_kind` is
  multivalued: a mixed callset is `["small", "structural"]`, so a search for either finds it, and no
  combined term exists. `variant_origin` is single-valued. The schema marks a multivalued slot
  (`multivalued: true`), and for such a dimension the claims at the winning tier are unioned rather
  than a conflict. By grep, about 15 modules read a dimension's value (`reconcile.py` most), and the
  settling engine sits in three.
- **A kind is set only when known.** A merge whose inputs are known to differ in kind, or a file #652
  has scanned, gets both values. One whose mix is not known stays `not_classified`, with its reason.
- **Later option, not taken now:** sparse declared keys (a tag table, or multivalued keyword fields in
  a search index), which drop the `not_applicable` rows. Free tags are not an option: a key keeps a
  controlled vocabulary, and each value keeps its status and evidence.

### What users see

Users pick from one list of named concepts, each a stored filter over the facets, rather than
combining facets themselves. One declared table holds each concept's name, its filter and a sentence
describing it, and only combinations present in the data get a row:

| concept | filter |
|---|---|
| Germline small-variant calls | kind ∋ small, origin = germline |
| gVCFs for joint calling | data type = gVCF (#655) |
| Structural variant calls | kind ∋ structural |
| Callsets mixing small variants and SVs | kind ∋ small and kind ∋ structural |
| Variants, kind not determined | data type = variants, kind not classified |

The facets stay underneath for the API. "Not applicable" is never shown as a value; "not classified"
is shown as "Not determined".

### Later applications

- **Role:** `.reference` leaves `data_type` for a role slot, which the variant resources also need.
- **Activities:** the operation and the data it acts on as separate facets, as EDAM keeps them.
- **Sample count** (#655): proposed here as an axis of its own, since format and sample count combine
  freely. #655 decided against it: see "How #655 names variant files".

### How #654 builds it (decided 2026-10-09)

- **`variant_kind` only.** `variant_origin` waits for its own issue and rules; no corpus file is
  somatic, so origin has nothing to tell apart yet.
- **The `variants.*` subterms stay in `data_type`**, each described with its axis and what assigns
  it, until their consumers move; `.gvcf` also waits for a format slot.
- **A claim declares one kind, a string; the record stores the settled value as a list**
  (`models.stored_value` / `settled_value`). Settling, reconcile and inheritance run over strings as
  for any dimension. The union rule (several kinds at the winning tier) waits for #652, its first
  real source; until then two kinds at one tier are a conflict.
- **`not_applicable` is declared by the rules that know a file holds no variants** (reads, alignments,
  images, logs, checksums, and the annotation rules that know their content: methylation, expression,
  read depth, assembly QC), never derived from `data_type`. Other annotations, genotypes and pangenomes,
  which can hold variants, stay `not_classified`.
- **The kind is the caller's,** read from the header by three content rules and looked up in
  `rules/caller_kinds.yaml` (now `rules/callers.yaml`, #658); a GenomicsDB workspace's own header
  is read the same way by three tar rules (#678). Reconcile carries it across index, merge and cohort-merge steps, and across a
  joint genotyping of gVCFs (#678), which calls nothing the gVCFs did not hold: a filter can narrow
  a kind, and a call from alignments creates one.
- **Reference resources** (dbSNP, ClinVar, known-indels) name no caller and stay `not_classified`; a
  curator knowledge base keyed on md5 is a later option.

### How #658 builds the origin (decided 2026-10-10)

- **The caller only, never the dataset.** A dataset rule guesses for every file in it, as the
  dataset reference rule #561 removed did. The caller is found as for the kind, and
  `rules/caller_kinds.yaml` became `rules/callers.yaml`, each row giving its origin beside its
  kind (`meta_disco.callers`, `meta_disco.variant_origins`).
- **The slot is named for SO's term**, `variant_origin` (SO:0001762); GENO's and ClinVar's
  "allele origin" describes one allele, and its other values (maternal, paternal, de novo) are
  not in a callset's header.
- **A caller with a somatic mode** (Sniffles2's `--non-germline`, `--mosaic`) gives its origin
  only where its command line shows the mode off, or where its `##source` spelling is a version's
  without the mode (Sniffles 1's plain `Sniffles`, whose 1.0.12 options were read). A run in the
  mode, or a mode not stated, is `not_classified`.
- **A germline reading is refused** where the header declares the `SOMATIC` INFO flag or
  Mutect2's tumour and normal sample lines; a merge is germline only where every caller is.
- **No somatic caller is in the table yet.** Mutect2 is not always somatic (its mitochondria mode
  calls germline variants, and a tumour-only run mixes germline calls in), and no corpus file has
  a somatic caller to write its rule from; the step reader knows Mutect2 and FilterMutectCalls,
  so a Mutect2 file is `not_classified` as a caller the table does not list, until a somatic
  dataset's own issue adds the row from its headers.
- **Reconcile carries the origin** across index, merge and cohort-merge steps, across
  variant processing (filters), which can drop calls but not change where they arose, and across
  a joint genotyping of gVCFs (#678).
- **GATK's gVCF gatherers are not callers** (#678): GenomicsDBImport and CombineGVCFs are merges,
  settled by the callers the header names, and GenotypeGVCFs keeps its input's calls: GATK's
  panel-of-normals workflow imports Mutect2's VCFs with GenomicsDBImport, and CombineGVCFs and
  GenotypeGVCFs take Mutect2's gVCFs with `--input-is-somatic`. A header
  that names the gatherer but not the caller behind it gives no kind or origin.

### How #657 retires the subterms (decided 2026-10-13)

- **Kind and origin leave `data_type`.** `variants.structural`, `variants.cnv`,
  `variants.germline` and `variants.somatic` are gone from the vocabulary: once the explorer read
  `variant_kind` and `variant_origin`, every file holding one held the same fact in those slots.
  The rules that wrote them go too: the `##source` rules for HaplotypeCaller, SVIM and Sniffles,
  and the two record rules from #630, whose only use was to set `.structural` or to overrule a
  header rule that did.
- **gVCF becomes `variants.gvcf`, under `variants`**, the one format term left in `data_type`.
  No slot holds a file's format read from its content (`file_format` is the source's extension),
  so it stays here until one does.

### How #655 names variant files (decided 2026-10-25)

- **Users see one data-type facet of named values, not a format and a sample count to combine.** Dave:
  "user doesn't care about this schema, we shouldn't make them care about it." The portals surveyed in
  #655 (GDC, ICGC ARGO, UK Biobank, All of Us) each give one "what is this file" facet of named things,
  with the variant kind as a facet beside it. None asks users to filter on a sample count or on a format
  read from the content.
- **So `data_type` names five things under `variants`,** each read from content: `variants.gvcf` (gVCF,
  as before), `variants.multi_sample`, `variants.single_sample` and `variants.sites_only` (from the
  sample columns after `FORMAT` on the `#CHROM` line, `vcf_sample_column_count`), and
  `variants.genomicsdb` (a GenomicsDB workspace tar, `tar_genomicsdb_workspace`). Kind and origin stay
  in `variant_kind` and `variant_origin`. This departs from decision 1: format and sample count can
  combine, as in a multi-sample gVCF. No corpus file has both: every gVCF #655 measured holds one sample.
- **`variants.gvcf` stays.** It no longer waits for a format slot.
- **The names say what the file holds, not how it was made.** "Multi-sample", not "joint-called":
  HPRC's `.pair.vcf.gz` holds one person's two haplotypes in two columns, and the pangenome VCFs are
  not joint calls either. Whether a multi-sample VCF is a joint call is #760's question. "Sites-only",
  not "reference resource": 1000G's 25 are a callset's sites-only files.
- **A gVCF also has one sample column**, and two content rules at one tier that disagree resolve to a
  conflict. The single-sample rule does not read the gVCF rule's answer (rule independence). It makes
  its own reading: one column, and no record read with `<NON_REF>` among its ALT alleles. On the
  2026-10-25 run, every one-column VCF had `<NON_REF>` in all of its records read or in none.

## Consequences

- The `variants.*` terms other than `variants` retire from `data_type`; their files carry the same
  information in `variant_kind`, `variant_origin` and the format. #657 retired the kind and origin
  terms; `variants.gvcf` stays, beside the four terms #655 adds.
- Each new slot is a new dimension: the schema, the 13 producers' output shape, reconcile, the reports
  and the explorer's data dictionary all change. That cost is paid once per axis, not once per
  combination.
- Consumers that filtered on `variants.structural` filter on `variant_kind` instead.
