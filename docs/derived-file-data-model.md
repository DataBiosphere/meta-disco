# Design: Data Model for Derived Files

**Date:** 2026-06-25
**Status:** Proposed (decision record for [#109](https://github.com/DataBiosphere/meta-disco/issues/109))
**Related:** [#90](https://github.com/DataBiosphere/meta-disco/issues/90) (provenance), [#88](https://github.com/DataBiosphere/meta-disco/issues/88) (conflict surfacing), [#16](https://github.com/DataBiosphere/meta-disco/issues/16) (DuckDB output)

---

## 1. What this document decides

Meta-disco classifies files into five dimensions: `data_modality`, `data_type`,
`reference_assembly`, `assay_type`, `platform`. Most of our thinking has been
about *primary* data files — a BAM, a VCF, a FASTQ — where the question "what is
this file?" has a direct answer.

This document is about a particular class of files: indexes (`.bai`, `.tbi`,
`.crai`), summary statistics (samtools stats), interval sets (targets BED),
checksums (`.md5`), logs. We loosely call them **derived files**, but — and this
matters — *derivation is not the defining property*. An assembly is derived from
reads; a BAM is derived from reads + a reference; a VCF is derived from a BAM.
Almost every interesting file is derived, and most of them carry real biological
content.

The real axis is **what the file's content is *about*:**

- **Biological content** — the bytes *are* the signal: reads, alignments,
  variants, sequence, assembly, expression matrices.
- **Descriptive content** — the bytes are *about another file* (or a process): an
  index points *into* a file, a checksum is a hash *of* a file, stats *summarize*
  a file, a log records the *process*.

This document is about that second group — descriptive-content files. (We keep
"derived file" as shorthand because it's familiar, but read it as "descriptive
companion file.") The open question (#109) is what our five dimensions should even
*mean* for them.

The decision recorded here is fourfold: **(1)** separate a file's *identity* from
its *origin* and store the origin as a link to the parent rather than copied-in
values; **(2)** `data_type` carries the file's content type in *both* classes, so
a `.bai` is `data_type: index`, not `not_applicable`; **(3)** the three truly
biological dimensions (`data_modality`, `assay_type`, `platform`) are
`not_applicable` for descriptive files; **(4)** `reference_assembly` is special —
read it from the file itself when possible, inherit it otherwise. The rest of this
document explains each, slowly and with concrete files.

---

## 2. The problem, stated plainly

Take an index file, `NA12878.bam.bai`, sitting next to its alignment,
`NA12878.bam`. The BAM is genomic, aligned to GRCh38. What should the index's
`data_modality` be?

There are two tempting answers, and each is half-right:

- **"What the file is."** The `.bai` contains seek offsets — a lookup structure,
  not genomic sequence. So `data_modality` should be `not_applicable`. Clean and
  honest. But now a user who filters the Explorer for "genomic data" won't see
  the index, even though it's part of the genomic dataset they're looking for.

- **"What it came from."** The `.bai` belongs to a genomic BAM, so call it
  genomic too. Useful for discovery. But now the index *claims to be* genomic
  sequence data when it isn't, and we've mixed "where this file came from" into
  "what this file is."

The current code (after #106) is an unexplained blend: derived files get
`data_modality / data_type / assay_type / platform: not_applicable`, but
`reference_assembly` is left open. That inconsistency — four fields closed, one
field open, no stated reason — is what this document resolves. (Spoiler: the
resolution also corrects `data_type`, which *shouldn't* be `not_applicable` — a
`.bai` does have a content type, namely `index`. See Sections 7b and 8.)

---

## 3. Core assumption: identity and origin are two different questions

The mistake is treating it as one question with one answer. There are two
questions, they have different answers, and they should be stored in different
places:

| Layer | The question it answers | Where it lives |
| --- | --- | --- |
| **Identity** | *What is this file?* | The file's own classification record — literal and clean |
| **Derivation** | *Where did it come from, and what can it inherit?* | A link to the parent file — **not** values copied onto this file |

Under this split, a `.bai`'s **identity** is honest and complete: its content type
is `data_type: index` (a real value, in the *descriptive* class), while the three
biological dimensions `data_modality / assay_type / platform` are `not_applicable`
because the file holds no biological signal. The discovery need — "show me the
index when I search for the genomic data it belongs to" — is met not by lying
about the index's identity, but by storing a **link** from the index to its parent
BAM that the search layer can follow when it wants to.

This is the single most important assumption in this document. Everything below
is a consequence of it.

---

## 4. The derivation link, as a typed edge

A derivation link is an **edge** with three parts, and they cost very different
amounts to produce. Keeping them separate is what makes the model practical.

```
NA12878.bam.bai          ──[ relation: index_of | parent_kind: alignment ]──►  NA12878.bam
data_type: index               the edge's TYPE (verb + what it attaches to)        the GROUNDING
(on the file itself)              knowable from filename / convention             best-effort, may be null
```

Note where each fact lives. *What the file is* — `data_type: index` — sits on the
file's own identity record (Section 3); it is **not** part of the link. The edge
carries facts about the *relationship*: the **verb** (`relation`), what kind of
thing it attaches to (`parent_kind`), and which specific file (the grounding).

### 4a. The edge's type — a verb plus a parent kind

Two facts about the relationship can be read without resolving the parent file:

- **relation** — *what kind of derivation is this?* The verb. For `.bai`,
  `index_of`. For `.md5`, `checksum_of`. For a samtools-stats file, `summarizes`.
  For a GRCh38→GRCh37 BED, `lifted_over_from`. This is the strongly-typed link —
  the part a bare "parent"/"about" throws away. (Section 8d defines the enum and,
  crucially, which verbs we can actually *detect*.)
- **parent_kind** — *what kind of file does it attach to?* For `.bai`, `alignment`.
  For `.fai`, `sequence`. For `.tbi`, one of a small set (vcf / bed / gff).

We already encode the `parent_kind` half, today, in
`scripts/classify_index_files.py`:

```python
INDEX_TO_PARENT = {
    ".bai":  [".bam"],
    ".tbi":  [".vcf.gz", ".bed.gz", ".txt.gz", ".tsv.gz", ".gff.gz", ".gtf.gz"],
    ".csi":  [".vcf.gz", ".bcf", ".bed.gz"],
    ".crai": [".cram"],
    ".pbi":  [".bam"],
}
```

Read it as sentences: *"a `.bai` is an index of a `.bam`; a `.crai` is an index
of a `.cram`."* The key is the descriptive file; mapping it to its extension
category gives the file's own `data_type` (`index`); mapping the *value* to its
category gives the `parent_kind` (`.bam` → `alignment`). The proposal is to lift
this out of the one index script and make `parent_kind` a first-class property of
**every** descriptive file, extended beyond indexes to stats, intervals,
checksums, and logs.

> **Why isn't the parent encoded *in* `data_type` (e.g. `bam_index`)?** Because
> that bundles two facts — "it's an index" and "of an alignment" — into one opaque
> token, and forces an enum that grows as the *product* of {index, checksum,
> stats…} × {bam, vcf, bed…}. Factoring it (`data_type: index` on the file +
> `parent_kind` on the link) keeps the enum additive and lets you query each fact
> independently. Section 8c works through this tradeoff in full.

The important property: **the type is always available.** You never need to find
the parent file to know that a `.bai` is "an index of an alignment." That alone
turns out to be useful for search (Section 6).

### 4b. The grounding — best-effort, may be absent

The grounding is the pointer to the *specific* parent file. We get it by
filename convention, scoped to the same dataset — again, something
`classify_index_files.py` already does in `get_parent_candidates()`:

1. The index is `NA12878.bam.bai`. Its extension `.bai` maps (via the table) to a
   `.bam` parent.
2. Strip `.bai` → candidate parent name `NA12878.bam`. (The function also handles
   the `sample.bai → sample.bam` form where the index extension *replaces* rather
   than *appends*.)
3. Look for a real file named `NA12878.bam` **in the same dataset**. If found, note
   its `md5sum`.
4. That `md5sum` is the grounding.

If step 3 finds nothing — or finds two equally-good candidates — the grounding is
`null`. The link is then *typed but ungrounded*: we know it's an index of an
alignment, we just couldn't say which alignment.

#### A deliberate distinction: process *type* vs process *instance*

We are **not** trying to track which pipeline run produced a file. The source
data carries no provenance trail, so reconstructing "this `.bai` was produced by
this exact `samtools index` invocation" (a process *instance*) is not feasible
and not attempted.

What we *can* do is far cheaper and almost as useful:

- The **process type** ("this is an index derived from an alignment") comes free
  from the filename — Section 4a.
- The **parent file** comes from name-pairing within the dataset — Section 4b.
  This identifies the parent *file*, not the process *run*, and it's allowed to
  fail.

So when we say "link to the parent," we mean a pointer to a parent *file* plus the
*type* of the relationship — never a claim about a specific process execution.

### 4c. Why the edge needs its own verb (it isn't redundant with `data_type`)

For the simplest files the `relation` verb and the file's `data_type` look
parallel — a `.bai` is `data_type: index` and the edge is `index_of` — which
tempts you to drop one. Don't: they answer different questions (*what is this
file?* vs *how does it relate to its parent?*) and **come apart** exactly where
derivation gets interesting:

| File | node `data_type` | edge `relation` |
| --- | --- | --- |
| `NA12878.bam.bai` | `index` | `index_of` |
| `sample.bam.stats` | `statistics` | `summarizes` |
| a **subset** BAM carved from a larger BAM | `alignments` | `subset_of` |
| a **liftover** BED (GRCh38→GRCh37) | `intervals` | `lifted_over_from` |
| a **merged** VCF | `variants` | `merged_from` (many parents) |

Look at the bottom three: their `data_type` is a perfectly ordinary *biological*
type (`alignments`, `intervals`, `variants`) — because they genuinely *are* that
content — yet they are also derivations, and the **only** place that shows is the
edge. A subset-BAM is a real alignment file *and* `subset_of` another; the node
cannot say the second part, the edge can. So `relation` is not duplicating
`data_type`; it captures derivations that have no distinct content type at all.

This also rescues a case that currently breaks. Issue #88's
`chm13_..._uncoveredByGRCh38...bed` files mention two references and today resolve
to a *conflict* (ambiguous `reference_assembly`). As a typed edge —
`relation: lifted_over_from`, parent reference `GRCh38`, own reference `CHM13` —
the "conflict" becomes structured provenance instead of an error.

---

## 5. How the link is represented and followed

### 5a. Representation — one pointer, not copied values

A classification record is keyed by `md5sum`. The BAM:

```json
{
  "md5sum": "aaa111",
  "file_name": "NA12878.bam",
  "classifications": {
    "data_modality":      { "value": "genomic" },
    "reference_assembly": { "value": "GRCh38" }
  }
}
```

Its index is a separate record with its own `md5sum`. The link is one block that
points at the parent:

```json
{
  "md5sum": "bbb222",
  "file_name": "NA12878.bam.bai",
  "classifications": {
    "data_type":          { "value": "index" },
    "data_modality":      { "value": "not_applicable" },
    "assay_type":         { "value": "not_applicable" },
    "platform":           { "value": "not_applicable" },
    "reference_assembly": { "value": "not_applicable" }
  },
  "derived_from": {
    "relation":      "index_of",
    "parent_md5sum": "aaa111",
    "parent_file":   "NA12878.bam",
    "parent_kind":   "alignment"
  }
}
```

Two things to notice. First, the index's own identity is complete and honest:
`data_type: index` (its real content type), and the three biological dimensions
`not_applicable`. Nothing about the parent is copied into these values. Second,
the `derived_from` block is a **typed edge**: `relation` is the verb (`index_of`),
`parent_md5sum` is the pointer to the record where the parent's real values live,
and `parent_file` / `parent_kind` ride along so a human or a report can read the
relationship without a second lookup.

The crucial difference from today's behavior: the index's own `data_modality`
stays `not_applicable`. We store a **pointer** to where "genomic" lives, we do
**not** copy "genomic" onto the index.

**What already exists vs. what changes (verified 2026-06-25).** Good news — half
of this is already built. `classify_index_files.py` already writes
`parent_md5sum` and `parent_file` onto each index record (lines 309–310), so the
*link itself already exists*. What it *also* does, and what this design removes,
is **materialize** the parent's values: lines 214–218 copy the parent's
`data_modality / data_type / assay_type / platform / reference_assembly` onto the
index, and lines 311–316 wrap them in per-field `classifications` blocks carrying
an `inherited_from_parent` evidence entry. So the refactor is
narrower than it first appears: keep the pointer (already there), stop treating
the copied-in values as the index's own identity, and move "what it inherits" to
query time (next section).

For an *ungrounded* link, `parent_md5sum` is `null` but the file's own `data_type`,
the edge's `relation`, and the `parent_kind` are still present — the type-level
facts survive even when the grounding fails.

### 5b. Following the link — one extra lookup at query time

"Follow the link at query time" sounds abstract; concretely it is one dictionary
lookup performed *when someone searches*, instead of a value pre-copied into the
record. Trace the query **"show me all genomic files":**

Without links, the search makes one pass over own-values:

- `NA12878.bam` → own `data_modality` is `genomic` → **include**.
- `NA12878.bam.bai` → own `data_modality` is `not_applicable` → **exclude**.
  (The index is missing — the #109 discovery complaint.)

With links, the search makes the same pass, then does **one follow-up for derived
files** that didn't match on their own:

- `NA12878.bam` → own value `genomic` → **include**.
- `NA12878.bam.bai` → own value `not_applicable`. Before discarding, check for a
  `derived_from`. It has one: `parent_md5sum: aaa111`. Look up record `aaa111` —
  that's the BAM, which is `genomic`. So **include the index too**, labeled
  "genomic (inherited from NA12878.bam)."

"Look up record `aaa111`" — `records["aaa111"]` — *is* following the link. It
happens at search time precisely so we don't have to bake the value into storage.

### 5c. Why follow at query time instead of copying once?

Because the two questions from Section 3 stay answerable only if we *don't* copy:

- *"Genomic sequence files"* → the own-values pass only → BAM, **not** the index.
- *"Everything connected to genomic data"* → own-values **plus** following links →
  BAM **and** its index, stats, checksums.

If we pre-copy "genomic" onto the index (today's behavior), the index permanently
*is* genomic in storage, and the first question can never be answered cleanly
again. Storing a pointer instead of a copy is exactly what preserves the
distinction.

> **The consuming layer (verified 2026-06-25).** There is **no search layer
> inside this repo** — meta-disco produces classification JSON; the actual
> filtering UI is the external AnVIL Explorer / TDR. The in-repo consumers are the
> batch **report generators**, and they already load every classification into a
> dict keyed by `md5sum` (see `classify_index_files.py:load_classifications`), so
> "follow the link" is a trivial dict lookup they can already do — no new
> infrastructure needed to compute an inherited view for the reports.
>
> The real decision is **what meta-disco hands to the Explorer**: records with
> inherited values pre-copied in (today), or clean identity records plus links
> that the Explorer follows. If the Explorer can't follow links (a downstream
> system this repo doesn't own), the fallback is to ship an "inherited view" as a
> separate materialized table built *from* the links at write time — still keeping
> the canonical identity records clean. Either way the link is the source of
> truth; materialization, if needed, becomes a derived artifact rather than the
> primary record.

---

## 6. What the link buys discovery — three levels

The link's type-level facts (`relation` + `parent_kind`) and its grounding pay off
at three increasing levels of precision. The first two need only the type — no
parent file resolved at all.

**Level 1 — companion co-selection (type only).** Because every descriptive file
carries its own `data_type` (`index`, `stats`, …) and a `parent_kind`, the UI can
offer "include companion files" on any primary-file result: *"genomic alignments (1,240) — also show their 1,238
indexes and 410 stats files."* This needs no resolved parent, inherits no values,
and already covers the core "the `.bai` should appear alongside its BAM" case.

**Level 2 — bounded inheritance as a filter constraint (type only).**
`parent_kind` *limits* what a derived file could possibly inherit, even when
ungrounded. An index-of-alignment can only inherit modalities that alignments
carry (`genomic`, `transcriptomic`) — never `imaging.histology`. So a
`data_modality = genomic` filter can safely include ungrounded indexes whose
`parent_kind` is *compatible* with genomic, and exclude those that can't be (a
checksum of an image). A partial, correct constraint from pure type.

**Level 3 — exact inherited values (grounded).** When the parent *is* resolved,
the search surfaces the parent's concrete dimensions on the derived file as
clearly-labeled inherited values ("genomic, inherited from NA12878.bam"). This is
the existing `inherited_from_parent` evidence idea — kept, but expressed as a
*provenance record produced by following a link*, not as an identity overwrite.
That framing drops straight into the provenance model of #90 (authority =
`derivation_inheritance`, trust capped by the parent's own trust).

---

## 7. Why `reference_assembly` is the odd one out

The post-#106 state leaves `reference_assembly` open while the other contextual
fields are `not_applicable`. That is **correct** — it just was never explained.
The explanation is a single question asked of every field:

> *Can I determine this field by looking at **this file's own contents**?*

Apply it to a samtools-stats file, `NA12878.bam.stats`, whose contents look like:

```
SN  raw total sequences:  789456123
SN  reads mapped:         780112000
SN  insert size average:  412.3
chr1   248956422   12043
chr2   242193529   11890
```

- **`data_modality`** — is "genomic" anywhere in this file? No. It's read counts
  and insert sizes. The only way to know it's genomic is to know the parent BAM
  was. → not readable from self → **inherit**.
- **`assay_type`** — is "WGS" in this file? No. A WGS stats file and a WES stats
  file are structurally identical. → not readable from self → **inherit**.
- **`platform`** — is "ILLUMINA" in this file? No. The stats text doesn't name the
  sequencer. → not readable from self → **inherit**.
- **`reference_assembly`** — is "GRCh38" in this file? **Yes.** The lines
  `chr1 248956422`, `chr2 242193529` *are* GRCh38 — chr1 at 248,956,422 bp is the
  GRCh38 length (GRCh37's chr1 is 249,250,621). The reference is sitting in the
  file's own content. → **readable from self.**

The asymmetry is a fact about the files, not a special case we invented: **three
of the fields describe the experiment that produced the upstream data — which
leaves no fingerprint in the derived file — while `reference_assembly` describes
the coordinate system the derived file's own numbers are written in, which is
necessarily present in those numbers.**

This generalizes beyond stats files:

- A **targets/interval BED** has rows like `chr1  10000  248900000`. A coordinate
  of 248.9M on chr1 is impossible under GRCh37 and consistent with GRCh38 — the
  reference is recoverable from the coordinates. (Our BED coordinate detector and
  the VCF max-position detector already do exactly this kind of inference.)
- A **`.fai`** literally lists `chr1<TAB>248956422<TAB>…` — the lengths *are* its
  content.

In each case the reference is baked into what the file contains, because the
file's numbers are meaningless without it. That is what "intrinsic to
interpretation" means: you cannot read a stats / BED / `.fai` file correctly
without knowing its reference, so the reference is genuinely part of the file's
own content — not merely part of its history.

### 7a. The resolution procedure for `reference_assembly`

Because it can sometimes be read from the file itself, try the most reliable
source first:

1. **Read from self.** Can the reference be detected from this file's own content
   (chromosome lengths in the stats, coordinates in the BED)? If yes → use it and
   store it as the file's **own** value. This is the most reliable source and it
   honors our "accuracy over efficiency" principle: read the real evidence rather
   than trust a secondhand value.
2. **Inherit.** If the file's content can't reveal it (a `.bai` is binary offsets
   we don't parse) → follow the derivation link and take the parent's reference,
   surfaced as an inherited value just like modality.
3. **Neither** → `not_classified`.

The other three contextual fields skip step 1 entirely, because step 1 always
fails for them — there is nothing in the file to read.

### 7b. `not_applicable` vs "open" — a real distinction

`not_applicable` is a strong claim: *this field has no meaning for this file.*
That is true for `assay_type` on a `.bai` — an index has no assay, full stop.

But stamping `reference_assembly: not_applicable` on a stats or BED file would be
**wrong**, because the reference *does* carry meaning there: a GRCh38 stats file
and a CHM13 stats file are genuinely different objects, and a user may rightly
want "stats files aligned to CHM13." Marking it `not_applicable` would erase a
real, useful distinction. So we leave it **open** instead:

- **`not_applicable`** = "don't ask — there is no answer." → `data_modality`,
  `assay_type`, `platform` on a descriptive file (it has no modality, assay, or
  platform of its own).
- **a real value** = "this field has a direct answer about the file itself." →
  `data_type` on a descriptive file, which is its content type (`index`,
  `checksum`, `statistics`, `log`) — *not* `not_applicable`.
- **open** = "there is an answer; go find it via read-from-self or inherit." →
  `reference_assembly` on a stats / BED / index / `.fai` file.

So a `.bai` is not "four fields closed, one open" — it is `data_type: index`
(answered directly), `data_modality / assay_type / platform: not_applicable`
(genuinely absent), and `reference_assembly` open (read-from-self or inherit).

---

## 8. Taxonomy: content types, parent kinds, relations, and where allowed values live

This design adds a little vocabulary — some new `data_type` values for descriptive
files, plus a `parent_kind` for the link — and the question "where do the allowed
values live?" turns out to be the same question as #33 (expand the schema). So
this section covers both: the taxonomy itself, and the (currently weak) machinery
that's supposed to constrain our slot values.

### 8a. The vocabulary mostly already exists — in `extension_map`

The single most useful finding from verification: **we are not inventing these
content types from scratch.** The `extension_map` document in
`rules/unified_rules.yaml` already sorts every extension into a category, and
several of those categories *are* descriptive-content types:

| Existing `extension_map` category | Extensions | Becomes `data_type` (descriptive class) |
| --- | --- | --- |
| `index` | `.bai .crai .tbi .csi .fai .idx .pbi` | `index` |
| `checksum` | `.md5` | `checksum` |
| `log_file` | `.log` | `log` |
| `archive` | `.tar .tar.gz .zip` | `archive` |

So for these, the content type is just the extension_map category we already
assign. The proposal is to *promote* that category from an internal routing detail
to a stored `data_type` value.

`parent_kind` reuses the **primary-file categories that already exist** — both in
`extension_map` (`alignment`, `variant`, `reads`, `sequence`, `intervals`,
`signal`, …) and in the biological `data_type` values the rules already emit
(`alignments`, `variants.*`, `reads`, `sequence`, `annotations`,
`expression_matrix`, …). And `INDEX_TO_PARENT` already encodes the
content-type→parent_kind mapping *at the extension level* (`.bai → .bam`, i.e.
index → alignment).

### 8b. What genuinely needs adding

Only a little new vocabulary is actually required:

- **`statistics`** as a `data_type`. Samtools stats / flagstat / `*.stats` files
  currently fall under `.txt`/`.tsv` → `text_ambiguous`, so they have no distinct
  content type today. This value is new, and detecting it needs filename/content
  signals, not just extension.
- **`interval_set`** as a `data_type` — *but with care*. A `.bed` is `intervals`
  in `extension_map`, yet BED is often **primary** data (peaks, annotations), not
  descriptive. Only *capture/targets* BEDs are companions. So `interval_set` is not
  "all BED"; it's a content/filename-gated subset. This ambiguity is exactly why
  BED isn't a clean case and should be treated carefully.

Proposed enumerations (starting point, to be ratified):

```
data_type (descriptive class)  ∈ { index, statistics, checksum, log, archive, interval_set }
data_type (biological class)   ∈ { alignments, variants.*, reads, sequence,
                                   assembly, expression_matrix, … }   (already in use)
parent_kind                    ∈ { alignment, variants, reads, sequence, intervals,
                                   signal, expression_matrix, genotypes, any }
```

### 8c. Two content classes, and why we factor instead of subtype

The corrected model puts **all** content types in one field, `data_type`, but
recognizes they fall into two **classes**:

- **biological** — the bytes are the signal (`alignments`, `variants`, `sequence`,
  `assembly`, …);
- **descriptive** — the bytes are about another file (`index`, `checksum`,
  `statistics`, `log`).

The class is a property *of each value*, not a separate dimension a classifier has
to guess — `index` is always descriptive, `alignments` always biological. It's
useful mainly as a grouping for queries ("show me only files with biological
content") and as the rule for which other dimensions apply (descriptive ⇒
`data_modality / assay_type / platform` are `not_applicable`).

That leaves one real fork, the one worth recording: for a descriptive file, do we
**subtype** the content type to name its parent (`data_type: bam_index`,
`vcf_index`), or **factor** it (`data_type: index` on the file + `parent_kind` on
the link)? Both are coherent. The tradeoffs:

**Subtyping (`bam_index`, `vcf_index`, `bam_stats`, …)**

- 👍 One field, one self-explanatory value; reads well at a glance.
- 👍 Matches how `extension_map` already works (one category per extension).
- 👎 **Combinatorial blowup** — the enum is the *product* {index, checksum, stats,
  log} × {bam, vcf, bed, cram, gff, …}, and every new parent format multiplies it.
- 👎 **Queries need string surgery** — "all indexes" = match `*_index`;
  "everything about alignments" has no shared token across `bam_index`,
  `bam_stats`, `bam_md5`.
- 👎 **Double-encodes the parent**, and the two copies can disagree: the parent is
  already named by the link (`parent_md5sum`), so a `bam_` prefix restates it from
  a *filename guess* rather than the *resolved* parent.

**Factoring (`data_type: index` + `parent_kind` via the link) — recommended**

- 👍 **Additive, not multiplicative** — {index, checksum, stats, log} *plus*
  {alignment, variants, sequence, …} = M+N values, not M×N.
- 👍 **Orthogonal queries, no parsing** — filter by content type (`index`), by
  what-it's-about (follow the link to the parent's `data_type`), or both.
- 👍 **Single source for "of what"** — `parent_kind` comes from the *resolved*
  parent, so it can't drift from a filename guess.
- 👎 Two things to populate, and a glance at one record shows `data_type: index` +
  a `parent_md5sum` rather than a tidy `bam_index`.

**Decision:** factor it. Keep `data_type` a single field spanning both classes,
put the descriptive content type there (`index`, not `not_applicable`), and let the
parent come from the link — never from a `bam_` prefix. The only place subtyping
wins is if the downstream Explorer can filter on *one flat facet only* and cannot
follow links; in that case synthesize a display value like `bam_index` from
`data_type` + parent at presentation time — generated, never the stored truth
(same escape-hatch pattern as the inherited-view fallback in Section 5c).

(Aside: today's `data_type` vocabulary already mixes the two classes a little
unevenly — `archive` and `images` are arguably container/medium types. Tidying
that is follow-up, not part of this decision.)

### 8d. Typed relations on the edge — and which we can actually detect

The edge's `relation` verb (Section 4) is the strongly-typed link. The discipline
that keeps it from becoming aspirational fiction is our own *accuracy over
coverage* principle: **only mint a relation we can actually detect, and provide a
generic fallback.** A rich vocabulary of verbs we can never populate would be
modeling for its own sake.

| `relation` | detectable from | confidence | mint now? |
| --- | --- | --- | --- |
| `index_of` | naming convention (already done) | strong | ✅ |
| `checksum_of` | `.md5` naming | strong | ✅ |
| `summarizes` | `.stats` / `.flagstat` filename | moderate | ✅ |
| `lifted_over_from` | filename hints (`hg38ToHg19`, `liftover`, `uncoveredBy…`) | sometimes | ✅ (low-confidence) |
| `subset_of` | rarely inferable from filename + header | weak | ⛔ not yet |
| `merged_from` | not inferable from current signals | — | ⛔ not yet |
| `member_of` | only if we expand archives | — | ⛔ not yet |
| `derived_from` | generic fallback: "related, verb unknown" | — | ✅ (fallback) |

Mint the top group; leave the bottom group out until evidence exists; degrade to a
bare `derived_from` when we know there's a parent but can't name the verb. That is
a small, fully-populatable enum — not aspirational typing.

```
relation ∈ { index_of, checksum_of, summarizes, lifted_over_from, derived_from }
           # subset_of, merged_from, member_of held back until detectable
```

**This is the seed of the provenance model (#90), not a detour.** A provenance
claim *is* a typed, sourced edge: *"this file `index_of` that file, authority =
naming_convention, confidence = strong."* Building derivation as
`{relation, parent, authority, confidence}` now means #109 and #90 share one
structure instead of growing two — so the verb reduces future work rather than
adding it. When #90 lands, `relation` edges and inherited-value claims flow through
the same machinery.

### 8e. Where allowed values *should* live (this is #33)

Verification turned up that we have **no real single source of truth** for
permissible slot values:

- The **LinkML schema** (then `schema/src/meta_disco/schema/anvil_file.yaml`) was a
  stub. It defined only `File` with `id / filename / reference_assembly /
  data_modality` — **two of our five dimensions**. `data_type`, `assay_type`, and
  `platform` had no slots at all. `data_modality_enum` listed only `genomic` and
  `transcriptomic`, while the rules actually emit `transcriptomic.bulk`,
  `transcriptomic.single_cell`, `epigenomic.chromatin_accessibility`,
  `epigenomic.histone_modification`, `epigenomic.methylation`, `imaging.histology`.
  Neither `not_applicable` nor `not_classified` was modeled anywhere in the schema.
  **Resolved:** `anvil_file.yaml` was retired (#134) and replaced by
  `classification.yaml`, which models all five dimensions, the full vocabulary, and
  `classification_status_enum`; whole records now validate against it.
- The **de-facto vocabulary** therefore lives, unenforced, in the `then:` blocks
  of `rules/unified_rules.yaml` (plus partial external mappings in
  `validation_maps.py`). Nothing checks that a rule emits a value the schema knows
  about.

This matters for the taxonomy because the new descriptive `data_type` values, the
`parent_kind` enum, and the `relation` enum all need a home, and that home should
be the *same* place the dimension enums live — we shouldn't add a scattered
fourth vocabulary.

#### LinkML vs JSON Schema — compile, don't switch

The instinct to drop LinkML for plain JSON Schema is worth taking seriously, but
it rests on a false choice: **LinkML is a modeling layer that *generates* JSON
Schema** (and Pydantic, SQL DDL, docs). So "switch to JSON Schema" really means
"hand-author the JSON Schema instead of generating it." Framed that way:

- **JSON Schema** validates JSON documents — universal, ubiquitous tooling, every
  dev knows it — but it is *structural validation only*: no ontology mappings, no
  multi-target generation, weak as a shared modeling/communication artifact.
- **LinkML** authors the model once and generates the rest. It is the native
  language of the NIH/biomedical data-commons world (Biolink, NMDC, CCDH) — i.e.
  exactly AnVIL/TDR's ecosystem.

Three things specific to meta-disco tilt this toward keeping LinkML:

1. **Domain fit.** The core problem *is* a controlled vocabulary of biomedical
   metadata, and several values map to ontology terms (`data_modality`→OBI/EDAM,
   `assay_type`→OBI). LinkML expresses those mappings; JSON Schema can't.
2. **Interop.** AnVIL Explorer and Terra/TDR speak schema; LinkML is the shared
   language and JSON Schema is the artifact you hand them.
3. **The roadmap already wants generation.** DuckDB (#16) wants SQL DDL; rule-file
   validation wants Pydantic; output validation wants JSON Schema — LinkML
   generates all three from one source.

The honest counterpoints: LinkML is more esoteric (smaller community, heavier
toolchain), and our schema **rotted** because nothing forced it current. But note
*why* it rotted — it wasn't load-bearing — and **switching tools would not fix
that**; a hand-written JSON Schema rots identically if nothing checks it. The real
fix is wiring a drift check into CI, which is needed regardless of tool.

#### Decision

**Keep LinkML as the source of truth; compile down; make it load-bearing.**

1. **LinkML = canonical vocabulary** (the five dimension enums, `classification_status`,
   `parent_kind`, `relation`, and the record/edge/evidence classes). Model sentinels
   as a separate `classification_status` rather than smuggling `not_applicable` into
   every value enum (see #56/#88). This subsumes #33.
2. **Generate JSON Schema + Pydantic** (and later SQL DDL for #16) from it. *Those*
   generated artifacts are what validate output records and the rules file — so
   day-to-day devs touch familiar JSON Schema/Pydantic, and the esoteric layer stays
   thin and rarely-edited.
3. **CI drift check** — rule `then:` values must be members of the schema enums (and
   the rule `when:` keys validated too, catching typos). This makes the schema
   load-bearing so it cannot rot again, and is the actual fix for what went wrong.

A working prototype of step 1 lives at
`src/meta_disco/schema/classification.yaml`; `make gen` (in `schema/`)
regenerates the JSON Schema and Pydantic from it (both gitignored as build
outputs). The rule drift check (step 3) lives in `tests/test_rule_vocabulary.py`
and reads the LinkML enums directly.

**Escape hatch:** if Explorer/TDR interop and ontology mapping are judged
irrelevant forever, collapse to hand-authored JSON Schema + Pydantic and delete
LinkML — a simple tool that gets used beats a rich tool that rots. But that
forfeits the one thing that makes this project fit its ecosystem, right as the
roadmap starts to cash in on generation.

## 9. Summary of the data-model assumptions

1. **The axis is content, not derivation.** What separates these files is whether
   their content is *biological* (the bytes are the signal) or *descriptive* (the
   bytes are about another file). Derivation isn't the criterion — an assembly is
   derived but biological.
2. **Two layers.** A file's *identity* (what it is) and its *derivation* (where it
   came from) are separate. Identity is stored literally on the record; derivation
   is stored as a link to the parent.
3. **Identity stays honest and complete.** `data_type` carries the content type in
   *both* classes — a descriptive file is `data_type: index` (or `checksum` /
   `statistics` / `log`), **not** `not_applicable`. Only the genuinely biological
   dimensions `data_modality / assay_type / platform` are `not_applicable` for a
   descriptive file.
4. **Factor, don't subtype.** The parent is named by the link (`parent_kind` +
   `parent_md5sum`), never baked into the content type as `bam_index`. This keeps
   the `data_type` enum additive (M+N) and the parent single-sourced.
5. **The link is a typed edge.** It carries a `relation` verb (`index_of`,
   `summarizes`, `lifted_over_from`, …), a `parent_kind`, and a grounding
   (`parent_md5sum`, best-effort and possibly `null`). The verb is not redundant
   with `data_type` — it captures derivations like subset/liftover/merge that have
   no distinct content type. Only relations we can actually detect are minted;
   everything else degrades to a generic `derived_from`.
6. **We track process *type*, not process *instance*.** We identify the parent
   *file* and the *kind* of relationship, never the specific pipeline run.
7. **Store a pointer, not a copy.** Inherited values are computed by following the
   link at query time, so the two distinct questions ("what is it" vs "what's
   connected to it") both stay answerable.
8. **`reference_assembly` is intrinsic to interpretation.** It is often readable
   from the descriptive file's own content, so it is resolved read-from-self first
   and inherited second — which is why it stays *open* while `data_modality /
   assay_type / platform` are `not_applicable`.

---

## 10. Verification findings and remaining questions

### Confirmed (verified against the code 2026-06-25)

- **The link already exists.** `classify_index_files.py` already writes
  `parent_md5sum` + `parent_file` per index record (lines 309–310). The refactor
  doesn't *add* the link — it stops the materialization that sits next to it.
- **Materialization is real and localized.** Parent values are copied at lines
  214–218 and re-wrapped as per-field `classifications` with an
  `inherited_from_parent` evidence entry at lines 311–316.
  That's the exact code this design changes.
- **No in-repo search layer.** Discovery lives in the external Explorer/TDR.
  In-repo consumers are the report generators, which already index everything by
  `md5sum` and can follow links trivially (Section 5c). So "compute at query
  time" needs no new infrastructure *for the reports*; the open part is purely
  what we hand the Explorer.
- **The content-type vocabulary largely pre-exists.** `extension_map` already
  assigns `index / checksum / log_file / archive` (Section 8a) — these become
  descriptive `data_type` values. We promote, not invent.
- **The schema is a stub.** Only 2 of 5 dimensions, a stale `data_modality_enum`,
  no sentinels — the real vocabulary is unenforced in the rules YAML (Section 8e).
  This is #33 and the taxonomy work should land with it.

### Still genuinely open

- **`statistics` data_type detection.** Stats files are `text_ambiguous` today; we
  have reference detectors for BED coordinates and VCF positions, but parsing a
  samtools-stats per-chromosome table for `reference_assembly` (Section 7's
  read-from-self step) is **not yet implemented** and is new work.
- **`interval_set` boundary.** Deciding which BEDs are descriptive companions vs.
  primary data (peaks/annotations) needs a content/filename rule, not just an
  extension (Section 8b).
- **Canonical vocabulary home.** Choose LinkML-canonical (recommended) vs.
  rules-YAML-canonical, and add the drift check either way (Section 8e).
- **Sentinel modeling.** Whether `not_applicable` / `not_classified` become a
  separate `classification_status` field rather than values inside every enum —
  intersects #56 (confidence removal) and #88 (conflict surfacing).
- **What ships to the Explorer.** Clean records + links, or a materialized
  inherited-view table — a product decision with the downstream consumer.
- **Relation detection.** `index_of` / `checksum_of` are already detectable;
  `summarizes` needs a stats-file signal; `lifted_over_from` needs filename
  heuristics (and overlaps the #88 conflict cases). Each detector is new work and
  should be added only at a confidence we can defend.
- **Share machinery with provenance (#90).** Inherited values *and* `relation`
  edges are both typed, sourced claims; they should reuse one provenance model
  (`{relation, parent, authority, confidence}`), not grow parallel ones.
