# Contract: evidence, claims, and who may make them

**Status:** Draft — assertions under discussion
**Date:** 2026-09-11
**Supersedes framing in:** #391 (epic), #392 (PR #403, merged), #401 (PR #407, merged), ADR-0001 (retired, #422)

Importers say what was written. Rules say what it means. Only rules make claims.

---

## 1. Roles

1.1 Only the rule engine makes claims. No importer, script, or external source makes one.

1.2 An importer produces **evidence**, never a claim.

1.3 The importer maps **structure**; the rule engine maps **meaning**.

1.4 Once a column is selected for a slot, an importer transcribes its raw value **verbatim** — it does not
    normalize, translate, correct or suppress it. Declining to select a column at all is a different act,
    made once and recorded in the slot map (2.4).

1.5 An importer needs no knowledge of our controlled vocabulary, and may not contain one.

1.6 A curator justifies itself like any other input, and is unlike every other in how it enters: as rules,
    not as evidence. It is also the only input that wins.

1.7 A curator writes rules. A curation decision is a rule like any other and is reviewed as one;
    a decision about a single file is a rule whose selection matches one file, not an exception to 1.1.

## 2. Source evidence

2.1 Evidence imported from a source is `(slot, raw_value)` plus provenance: source, dataset, table, column.
    A **slot** is one of the five classification dimensions; it is spelled `field` on the wire and in the code.
    The importer names **both ends of the key correspondence** — `source_key` as the source publishes it,
    `target_key` as one of ours — and writes the value already in our space (#401). Evidence is attached to a
    **file** only at the join (6.7), which is what makes an unmatched or ambiguous row representable rather
    than unthinkable.
    This is the same principle as `raw_value` beside a mapped value, applied to identity: the importer maps
    the key and keeps what the source called it, a rule maps the value and keeps what the source said, and
    both stay auditable for the same reason.
    A source that cannot name one of our keys cannot be imported. IGSR keys by sample id, we have no
    subject-level key, and so it writes no evidence — a refusal, not a gap.
    Inference's own signals — an extension, a filename, a header, a contig length, a file size — are not this
    shape, and this section does not govern them.

2.2 The importer decides **which slot** a table or column speaks to. It never decides what the value means.

2.3 One column may speak to more than one slot. One raw value may produce several evidence rows.

2.4 The slot map is a curated judgment about what a source's tables and columns actually speak to.
    A signal judged misleading is **explicitly not mapped**, with its reason recorded in the map — never silently absent.
    Choosing to map a column and choosing not to are the same act; only the recorded reason makes either reviewable.

2.5 Evidence **imported from a source** is fetched out of band, with network, and read offline and deterministically.
    Inference fetches its own headers and content during the run, through the evidence cache, where a classifier
    needs them. Not every classifier does; a fetch failure the fetchers signal falls back to classifying
    without content, which yields `not_classified`; and an unwrapped error — a missing tool, say — propagates.

2.6 A table name and a column name are evidence, the same as a cell value.

2.7 Every column of a source table is one of three kinds, and the meaning sits in a different
    part of each. A column is read as one kind, never two.
    - A **file link** holds a `drs://` URI, or a list of them. Its **name** carries the meaning —
      the role the file plays. Its value is a pointer and says nothing.
    - A **metadata value** holds anything else that is not an identifier. Its **value** carries
      the meaning. Its name is a field label and describes no file.
    - A **foreign key** names another entity. Its value is the subject, or an edge to another
      entity.

2.8 A slot's value comes from a metadata value. A file link's name states a role, which belongs
    to the derivation graph.
    Whether such a name is *also* usable as slot evidence is unsettled, and the contract does
    not forbid it: measured on files inference can read, it added nothing (two slots, 656
    files); where inference has a content ceiling — a FASTQ's modality — it may be the only
    signal there is, and that case is untested. A source whose tables carry no metadata values
    at all has nothing else to offer.
    `docs/interpreting-submitter-tables.md` is the companion reference: what shapes these tables
    come in, why, and what each is worth.

2.9 **A source is read because inference has a ceiling the data sets, not the method.**
    Some dimensions are declared in the submission and invisible in the file. Measured over the
    corpus's 21,270 FASTQs: `platform` resolves on 100% of them from read names, and
    `data_modality` and `assay_type` on 0%. A WGS and an RNA-seq Illumina FASTQ carry no
    dependable in-file marker of which they are — the library type is in the submission's
    metadata, not the reads. BED `reference_assembly` has the same shape: recoverable when a file
    spans whole chromosomes, genuinely ambiguous when it is sparse.
    This is a property of the bytes, so no engine reaches past it — a better rule cannot, and
    neither could the runtime LLM this project removed. It is the whole reason input kinds 2-4
    exist, and the reason 4.2 makes them equal to inference rather than subordinate: they are not
    a second opinion on what inference already knows, they are the only opinion where it is blind.
    Retired from ADR-0001, which measured it; that document is deleted and its salvage is #422.

## 3. Claims

3.1 A claim is a rule's declaration about a slot, derived from source evidence (2.1), from inference's own
    signals, or from a curator's decision. It declares a **value** or a **status**.

3.2 Every claim names the rule that made it — including an identity mapping. There is no implicit copy.

3.3 A claim that declares a value declares a term in the controlled vocabulary, or it is not a claim.

3.4 A rule that maps imported evidence matches on `(slot, raw_value)` and may condition on provenance.
    It sees nothing else — not the file's extension, not its header, not another source's claim.
    **Sources stay pure**: what a source is taken to have said never depends on what we think of the file.
    This is also what keeps one mapping working across every source.
    Inference rules match their own signals — extension, filename, header, content, file size — as they do today.

3.5 A rule mapping imported evidence fires only on an exact match, over spellings it declares explicitly.
    Nothing fires by similarity. Inference rules keep their own matchers, regexes included.

3.6 Both rule-authorable statuses — `not_applicable` and `not_classified` — are a rule's to declare.
    No source asserts either in evidence.

3.7 A raw value no rule matched produces no claim and enters the review queue.

3.8 "Rule" means whatever makes a claim and is cited by it. A row in a translation table is one.
    It need not be an entry in `unified_rules.yaml`, and a mapping rule shares none of that engine's
    tiers, file-attribute conditions or extension filtering.

## 4. Sources and resolution

4.1 There are five input kinds:
    1. inference (filename, extension, header, content, file size, and signals already resolved)
    2. canonical repository metadata (AnVIL harmonized fields)
    3. non-canonical repository metadata (submitter tables)
    4. external repository (HPRC Data Explorer, ENA, IGSR)
    5. curator

    Inherited results (`SOURCE_DERIVATION_INHERITANCE`) are not a sixth kind. What they are is #413.

    A source is an input kind only if it says something about **our files**. A table that describes the world —
    an assembly's contig lengths, an ontology — is a lookup inference uses, not an input with an opinion.
    That is why the reference validator is input kind 1: it reads our bytes and looks the answer up.

4.2 Inputs 1–4 are equal. Being ours confers no rank; being external confers no rank.

4.3 Resolution has two stages. Inference resolves its own competing claims by tier, as it does today.
    Every declaration that survives — inference's, and each source's — then reconciles by agreement.
    Only inference has a tier ladder. No other input has one, and none is given one.

4.4 Sources that agree classify the slot, and every agreeing source is recorded.
    A slot on which only one input speaks takes that input's declaration — a value classifies it, a status is
    preserved as that status. Filling a gap is not a disagreement.

4.5 Inputs 1–4 that disagree produce a **conflict**. No value is asserted from them, and every competing
    declaration is recorded with the rule behind it.

4.6 Statuses reconcile on their own axis, and the two behave differently.
    `not_classified` never conflicts: it declares no answer, so another input having one fills a gap (4.4).
    `not_applicable` **does** conflict with a value — it asserts the slot cannot apply to this file, which a
    value contradicts. That is a conflict like any other: no value asserted, both declarations recorded,
    reviewable. The engine's file-type knowledge is not silently overridden, and neither is a source.
    Two statuses never conflict: `not_classified` yields to `not_applicable`, which is the more specific claim.

4.7 A curator rule **answers** a conflict; it does not erase it.
    The record takes `classified` with the curator's value, and every competing declaration stays in its evidence.
    The conflict itself — that these inputs disagreed, and how it was answered — belongs to the **reconciliation
    output**, which is where 5.1 lists it. So a file can be classified and contested at once without the record
    having to say two things in one field.
    A conflict no curator has answered leaves the record `conflict` with no value, as today.

## 5. Review

5.1 Every conflict is listable, with every competing declaration and the rule behind each.
    A conflict is not always two, and not always two values: a value against a status is one, and three
    inputs can disagree.

5.2 Every unmatched raw value is listable, with its source, dataset, table, column, slot, and the number of
    files it affects. Dataset is not optional: the same column name means different things in different
    datasets. Slot is not optional either: by 2.3 one raw value can be mapped for one slot and unmatched
    for another.

5.3 A source that produces evidence matching no file is an error, not a silent zero.

5.4 The *value* mapping a person must review is the rule set.
    The slot map is reviewable too — a wrong table-or-column-to-slot mapping misroutes evidence before any rule runs.

5.5 **An LLM drafts rules and slot maps; it never classifies at runtime.** Turning a novel source
    schema into a mapping is what it is good at, and the output is a durable artifact a person
    reviews under 5.4 and the engine then executes deterministically. Flexibility is spent once,
    at authoring; determinism holds at every run. A runtime LLM is not one of 4.1's input kinds
    and may not become one: it would produce a claim no rule backs and nothing could review,
    against 3.2. Retired from ADR-0001, which decided it; that document is deleted and its salvage is #422.

## 6. The pipeline

6.1 A run has three stages: **infer**, **read sources**, **reconcile**.

6.2 Inference output is a kept artifact, not an intermediate. It is what inference alone concluded, and it is provenance.

6.3 Reconciliation writes its own output. It never rewrites inference output.

6.4 Reconciliation is re-runnable against a stored inference run, without re-inferring.
    Inference is the expensive half — network, headers, 708K files. Editing a rule that maps imported
    evidence must not cost a corpus run. Editing an inference rule changes the inference artifact, and does.

6.5 Both artifacts validate against the same schema. A reconciled record is a classification record like any other.

6.6 A run with no inputs but inference — no source evidence and no curator rules — produces a reconciled
    record identical to its inference record.

6.7 Reading sources is a stage of its own, separate from reconciling them, and is measured on its own: evidence offered, evidence matched, and by which key.

6.8 Resolution across sources is by agreement, and is not tier math.
    Tier resolution *within* a source applies to inference, which has competing rules at four tiers.
    A source may have several columns reaching one file and slot, and they need not be saying the same thing.
    `participant.instrument_model` and `participant.instrument_platform` both reach `platform` on 3,202 rows,
    but a model and a platform are different facts: a model *implies* a platform, and the rule mapping `Revio`
    to `PACBIO` is where that implication lives. Both are legitimate evidence for the slot. They reconcile like
    any other declarations — agreeing ones classify, disagreeing ones conflict — and neither column takes
    precedence, because nothing has established one.

6.9 Inference output has two readers: **reconcile**, and anything whose purpose is to measure inference itself
    — the eval fixtures and the corpus-drift guard (#381), which would read a mapping-rule edit or a catalog
    refresh as inference drift if they read the reconciled artifact.
    Everything else reads the **reconciled** output, because that is the answer: the coverage, validation and
    consistency reports, the md5 cross-registration check (#395), and every downstream consumer.
    A stage of inference reading an earlier stage's file — Phase 2 over Phase 1 — is inference consuming its
    own intermediate, not a reader of the artifact.
    `corpus_diff` must be told which it is comparing: two runs' answers, or inference's behaviour across runs.

6.10 A reconciled record is **self-contained**: what inference concluded, what each source declared, and the
     resolution, in one record. It necessarily repeats inference's claims, because 4.5 and 4.7 require every
     competing declaration to be present, and that repetition is the price of a record a person can read
     without performing a join.

6.11 Each stage writes into its own subdirectory of the run, and both artifacts are **NDJSON**.
     One run's inference output is already 1.6 GB, with a single 551 MB file; a whole-file `json.load` of that
     is the memory ceiling of #374, and the reconciled artifact is larger still. 6.5 is about the record's
     schema, not its container, so nothing is lost by the change.

---

## What is not true yet

No code reads this document, and the pipeline it describes does not exist. Parts of it *are* enforced independently: `make_claim` refuses a claim that declares two things at once, or that carries a tier where none belongs, and `source_evidence` refuses a line that carries a mapped value at all (#421) — its record has no member for one, and `_entry_from_line` turns away a hand-written line that has. Nothing yet checks a mapped value *against the slot's vocabulary* at runtime; that check is #414's, at the point the translation table loads. 3.3 is enforced for rule claims anyway — `test_rule_vocabulary` checks every rule's `then` value against the LinkML enums at CI time, and output is validated at the schema gate — but **no runtime constructor checks it**. Nothing checks these assertions as a set. Enumerated rather than asserted, because "the contract holds" is the obvious sentence and it is false in five places:

- **1.1 is already violated.** `scripts/classify_index_files.py` builds value- and status-bearing evidence outside the rule engine, stamping `rule_id: inherited_from_parent` and its `source_type` by hand. CLAUDE.md documents this as a deliberate exception, because it copies a parent's *already-resolved* status — `conflict` included — which `make_claim` cannot express. Moving it into the engine is its own work and interacts with #371 — filed as #413, which also asks whether the honest fix is a clause here rather than a code move.
- **There is no slot map**, no rule scope for source evidence, and so no producer for any of section 2.
- **There is no read-sources stage and no reconcile stage** (#402 and an unfiled issue). A run has the three inference phases, plus `report_evidence_files`, which names the evidence files it found and consumes none of them.
- **There is no reconciled artifact.** Inference output is the only output, so 6.3 and 6.6 describe a distinction that does not exist yet.
- **Cross-source conflict does not happen.** `evaluate_claims` produces a conflict only from same-tier disagreement inside inference, and it explicitly drops any claim carrying a `source` — the operational form of the decision this contract reverses.

A line leaves this section when the assertion above it is enforced, not when it is merely intended.

---

## What this changes

- **A claim file becomes an evidence file.** *Done in #421.* #401's envelope, NDJSON discipline, and both-sides-of-the-join naming survived; the per-line record stopped being a claim and became an observation carrying `raw_value` and no mapped value. `source_type` moved to the envelope, where it is constant for the file.
- **"The importer owns the mapping" is reversed.** Rules own it. The importer owns the slot map.
- **`declined` moves to the slot map.** A table name or column judged not to speak to a slot is explicitly not mapped, with its reason recorded there. It is not a claim, not a rule, and never reaches resolution — the files `alignments_v2.location` names receive no `data_type` evidence, rather than a wrong claim for something else to cancel. The decline is scoped to the column, as the schema's own `declined` definition already scopes it.
- **#408 dissolves.** There are no imported claims, so there is no no-tier-on-an-imported-claim rule to place.
- **#396 folds into the engine.** Cross-source comparison is resolution stage two, not a separate step.
- **#369 shrinks** to the AnVIL slot map plus a reader. No vocabulary in it.
- **`output/anvil/<run>/*_classifications.json` stops being the answer.** It becomes inference output, kept as provenance. The reconciled artifact is the answer.
- **`manifest_survey.NAME_TOKENS` splits** — the name→slot half to the slot map, the token→term half to rules.

## Open

- Rule-id namespace: unique across the whole rule set, or namespaced per source.
- What an inference-resolved `conflict` does in stage two. 4.3 sends every surviving declaration to reconciliation, but `conflict` is a status the first stage really produces (`evaluate_claims` → `is_conflict`) and 4.6's axis names only `not_classified` and `not_applicable`. Concrete undefined case: inference resolves `platform` to `conflict` and one source declares `PACBIO`. 4.4 does not apply, 4.5 is about disagreeing inputs, 4.6 names neither arm.
- The conflict rate on a second dataset. The spike measured ~0.1% on `AnVIL_HPRC_R2` alone; at 1% across the corpus the review queue stops being viable and 4.5 needs rethinking.
- Whether input kind 2 (AnVIL harmonized fields) is read today at all.
- What a sentinel raw value (`""`, null, `unspecified`, `NA`) produces. Currently: an ordinary rule, yielding a state to be decided.
- How the review queue (3.7, 5.2) distinguishes *we have no word for this* from *no rule has ever seen this*. The current model already has both, as `claim_state` entries — `unmapped` and `no_vocabulary_term` — visible in evidence and ignored by `evaluate_claims` for resolution. 3.7 says such a value produces *no claim at all*, which retires that representation. So this is a migration to describe, including how the queue keeps the raw value, not a gap to fill.
- Whether instrument model deserves a slot of its own. It is a finer fact than `platform`, our vocabulary has
  no word for it, and today it survives only as the `raw_value` behind a `platform` claim. A dimension
  question for #364 rather than a mapping one.
- Whether a subject-level key and subject-level slots are worth adding. Without them IGSR, which keys by sample id, cannot be imported at all — correctly, but at the cost of a source. Related to the instrument-model question above, to #336 and to #361.
- What the two artifacts are called. `*_classifications.json` means inference today and the name should be corrected rather than inherited. This is #271's scope — it already covers naming drift in `output/`, and it says it can land independently of the rest of #268.
- How many files carry a source-declared value for a slot inference calls `not_applicable` — an unaligned FASTQ
  with a declared assembly is the shape. Measurable from the manifests already on disk. 4.6 makes each one a
  conflict, which is right if the number is small and wrong if it floods the queue.
