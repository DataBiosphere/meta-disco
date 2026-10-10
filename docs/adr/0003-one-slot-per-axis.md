# ADR-0003: One slot per axis — facets, not combined terms

- **Status:** Proposed (2026-10-09), to be accepted when #654 merges; storage and user model decided by Dave the same day
- **Decision record for:** [#654](https://github.com/DataBiosphere/meta-disco/issues/654) (variant kind), and the vocabularies it touches
- **Related:** #630, #651, #652, #607 (gVCF), #580 (activity vocabulary), #563 (MODAL), #533 (EFO), #655 (sample count)

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
| `data_modality` (MODAL, adopted) | assay scope; resolution | `genomic.exome`, `genomic.whole_genome`; `transcriptomic.spatial`, `.targeted` |
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
5. **Our own vocabularies are faceted** when a new axis appears, rather than gaining combined terms.

### First application: variants (#654)

| axis | slot | values | from |
|---|---|---|---|
| what it is | `data_type` | `variants` (EDAM `data_3498`) | extension, content |
| representation | file format (VCF, gVCF) | EDAM `format_3016`, `format_4018` | content (#607) |
| kind | `variant_kind` (multivalued) | small, structural (#654); CNV later, when a rule can give it. Bound to EDAM operations `0484`/`0452`, `3228` (and `3961` for CNV) | the producing step's caller (#654); whole-file scan (#652) |
| origin | `variant_origin` | germline, somatic (no EDAM term; SO's, unchecked) | the caller, or the dataset |

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
| gVCFs for joint calling | format = gVCF |
| Structural variant calls | kind ∋ structural |
| Callsets mixing small variants and SVs | kind ∋ small and kind ∋ structural |
| Variants, kind not determined | data type = variants, kind not classified |

The facets stay underneath for the API. "Not applicable" is never shown as a value; "not classified"
is shown as "Not determined".

### Later applications

- **Role:** `.reference` leaves `data_type` for a role slot, which the variant resources also need.
- **Activities:** the operation and the data it acts on as separate facets, as EDAM keeps them.
- **Sample count** (#655): how many samples a file holds (0 for a sites-only VCF, 1 for a single-sample
  VCF or gVCF, more for a project VCF) is an axis of its own by this ADR's test, since format and sample
  count combine freely. It leans towards a count read from the VCF's `#CHROM` line rather than a term.

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
  `rules/caller_kinds.yaml`. Reconcile carries it across index, merge and cohort-merge steps only: a
  filter can narrow a kind, and a call creates one.
- **Reference resources** (dbSNP, ClinVar, known-indels) name no caller and stay `not_classified`; a
  curator knowledge base keyed on md5 is a later option.

## Consequences

- The `variants.*` terms other than `variants` retire from `data_type` over time; their files carry
  the same information in `variant_kind`, `variant_origin` and the format.
- Each new slot is a new dimension: the schema, the 13 producers' output shape, reconcile, the reports
  and the explorer's data dictionary all change. That cost is paid once per axis, not once per
  combination.
- Consumers that filter on `variants.structural` today move to `variant_kind`.
