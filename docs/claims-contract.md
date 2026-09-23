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
    This fan-out is **structural**, per 1.3. A single value *implying* a term in a second slot is a
    different act, and belongs to 3.10.

2.4 The slot map is a curated judgment about what a source's tables and columns actually speak to,
    **authored from the source's own schema and from nothing a classification run concluded** (3.4). A
    column, or a slot on a column, that the map does not name is **not mapped**, and that is the whole
    statement: the map is authored against a named catalog with every column of it considered, so
    absence means considered and not mapped rather than overlooked. Choosing to map a column and
    choosing not to are the same act, and the reasoning behind either is recorded where it is read — the
    pull request and the issue — not in the map, which carries no prose.

2.5 Evidence **imported from a source** is fetched out of band, with network, and read offline and deterministically.
    An import is a **generation**, written once and never over an earlier one; a reader takes the newest
    generation of each dataset, so a mapping removed between two imports is absent from the next rather
    than left on disk as valid-looking evidence.
    Inference fetches its own headers and content during the run, through the evidence cache, where a classifier
    needs them. Not every classifier does; a fetch failure the fetchers signal falls back to classifying
    without content, which yields `not_classified`; and an unwrapped error — a missing tool, say — propagates.

2.6 A table name and a column name are evidence, the same as a cell value — but never evidence a mapping
    rule reads, which sees only the slot, the raw value and `(source, dataset)` (3.4). A name routes
    evidence rather than saying what a value means. Which reader it routes to is 2.7's and 2.8's, and 2.8
    leaves one case open.

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
    Such a name is *also* slot evidence, and the map declares which span of it speaks to which slot
    (#369). Measured on files inference can read it is an agreeing input, which 4.4 records; where
    inference has a content ceiling, or a source's tables carry no metadata values at all — the T2T
    datasets, 85% of the corpus — it is the only signal there is. Two exclusions are structural, read
    off the source's own naming and enforced by the map's loader: an **entity-shaped** token
    (`interval`) describes a row, not its files, and a **derivative** column (`*_index`, `*_bai`,
    `*_md5`) carries no `data_type` of its own payload while keeping the payload's `reference_assembly`.
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
    neither could the runtime LLM this project removed. It is the whole reason input kinds 3 and 4
    exist, and the reason 4.2 makes them equal to inference rather than subordinate: they are not
    a second opinion on what inference already knows, they are the only opinion where it is blind.
    Retired from ADR-0001, which measured it; that document is deleted and its salvage is #422.

## 3. Claims

3.1 A claim is a rule's declaration about a slot, derived from source evidence (2.1), from inference's own
    signals, or from a curator's decision. It declares a **value** or a **status**.

3.2 Every claim names the rule that made it — including an identity mapping. There is no implicit copy.

3.3 A claim that declares a value declares a term in **that slot's** vocabulary, or it is not a claim.
    The vocabularies are per slot, and a term of one slot is not a term of another.

3.4 A rule that maps imported evidence matches on `(slot, raw_value)`, normalized per 3.5, and may
    condition on provenance — on `(source, dataset)`, and no finer. Table and column belong to the slot map
    (2.4, reviewed under 5.4): a value meaning different things in two of one source's tables is a routing
    error, not two mappings.
    It sees nothing else — not the file's extension, not its header, not another source's claim.
    **Sources stay pure**: what a source is taken to have said never depends on what we think of the file.
    This is also what keeps an *unscoped* mapping working across every source; a scoped one narrows on
    purpose (3.12).
    Inference rules match their own signals — extension, filename, header, content, file size — as they do today.

3.5 A rule mapping imported evidence fires only on an exact match, over spellings it declares explicitly.
    Nothing fires by similarity. Inference rules keep their own matchers, regexes included.
    Matching compares a **normalized** form; the normalizer must not be able to merge two distinct terms in
    our vocabulary, `WGS` and `WES` being one letter apart.

3.6 Both rule-authorable statuses — `not_applicable` and `not_classified` — are a rule's to declare.
    No source asserts either in evidence.

3.7 Evidence whose selected row (3.12) is not an authored one produces no claim and enters the review
    queue. Selection reads the evidence's `(slot, raw_value)` *and* its provenance, so one pair can be
    ruled on under one source or dataset and queued under another. A seeded row is a key match and not a
    ruling (3.11), so evidence selecting one is queued as surely as evidence with no row at all.
    From the published source, such evidence still moves the slot (7.13), so the reconciled record keeps
    what it said, as an entry in `claim_state: unmapped` carrying its source, raw value and join and
    declaring nothing (#432): a slot it made `conflict` or `not_classified` must show why on the record
    (6.10). It is a record of what was seen, not a claim, and resolution does not read it.

3.8 "Rule" means whatever makes a claim and is cited by it. An authored row in a translation table that
    declares something is one (3.9). A seeded row is not, nor is an authored row declaring nothing:
    neither makes a claim.
    It need not be an entry in `unified_rules.yaml`, and a mapping rule shares none of that engine's
    tiers, file-attribute conditions or extension filtering.

3.9 A mapping **row** is: an id; a match key of `(slot, normalized raw_value)`, with alternate spellings
    listed explicitly; an optional scope of a source, or a source and dataset; a **declaration** of at most
    one pair per slot, each a term in **that slot's** vocabulary or one of 3.6's two statuses; and, where
    an author has ruled on it, a recorded reason — required for the same reason 2.4 requires one, and the
    mark that separates an authored row from a seeded one (3.11).
    An authored row that declares something is a mapping rule in 3.8's sense. A seeded row is not, nor is
    an authored row declaring nothing: neither makes a claim, so nothing cites either. Every row carries an
    id regardless, which is how an author refers to one — and an authored no-op is still a ruling, so 5.2
    takes it out of the queue.

3.10 A declaration may name slots other than the match slot, and may name several: an implication like
     `library_strategy = Hi-C` ⇒ `data_modality: genomic` belongs to the **value**, not to the column it
     arrived in. A row may also declare nothing for its own match slot and declare only another.

3.11 Every `(slot, raw_value)` present at a seeding scan has a row, and **identity is where it starts**.
     A **seeded** row declares nothing, whatever it spells, and carries no reason; an **authored** row
     carries one, and claims each declaration it holds — an identity mapping included (3.2).
     Authorship is the test and vocabulary is not: spelling one of our terms is a coincidence, not an
     agreement about meaning. 3.7 covers a key no row matches, a later scan having reached it or not.

3.12 Scope is optional and **nests**: unscoped, a source, then a source and dataset. Never a dataset
     alone, a dataset belonging to a source. A row with no scope is the default; **specificity selects the
     narrowest matching row** and takes its declaration whole, and because the three forms nest, "narrowest"
     is a total order rather than something that can tie. Two rows whose normalized values collide on the
     same slot at the same scope, alternate spellings included, are a rule set that cannot be loaded. This
     selects which row fires before any claim exists, so it is not a tier ladder and 4.3 is unaffected.

## 4. Sources and resolution

4.1 There are five input kinds:
    1. inference (filename, extension, header, content, file size, and signals already resolved)
    2. published repository metadata — what the repository itself publishes for a file, read from its
       system of record by its one published importer (7.12; `published_value`)
    3. non-canonical repository metadata (submitter tables; `repository_metadata`)
    4. external repository (HPRC Data Explorer, ENA, IGSR)
    5. curator

    Inherited results (`SOURCE_DERIVATION_INHERITANCE`) are not a sixth kind. What they are is #413.

    **Kind 2 was retired by #424 and reinstated by #472 and #497.** The retirement argued that a
    target's current state is not an input to producing it. It is an input once the circularity it
    feared cannot happen: our output goes to a separate table set (#444) and the repository's own tables
    are never written by us — but that holds only while the published value is read from the
    **system of record**. AnVIL's is its TDR snapshot tables, not the compact Azul manifest, which is a
    product of an index that may already carry our last output back to us (#432's decisions). So kind 2
    is read from the `anvil_file` table of the TDR snapshot — today as the verbatim manifest copies it
    row for row (7.12) — and the compact manifest is not a source.
    Kinds 2 and 3 are different sources with different labels: a submitter's table and what the
    repository publishes may disagree, and reconcile is where that is seen.

    A source is an input kind only if it says something about **our files**. A table that describes the world —
    an assembly's contig lengths, an ontology — is a lookup inference uses, not an input with an opinion.
    That is why the reference validator is input kind 1: it reads our bytes and looks the answer up.

4.2 Inputs 1, 2, 3 and 4 are equal. Being ours confers no rank; being external confers no rank; being
    what the repository publishes confers no rank. (Kind 5 is deliberately outside this list, because
    a curator does not compete with the others — 4.7 has a curator *answer* a conflict rather than
    produce one, and 4.5 keeps conflict production to these four.)

4.3 Resolution has two stages. Inference resolves its own competing claims by tier, as it does today.
    Every declaration that survives — inference's, and each source's — then reconciles by agreement.
    Only inference has a tier ladder. No other input has one, and none is given one.

4.4 Sources that agree classify the slot, and every agreeing source is recorded.
    A slot on which only one input speaks takes that input's declaration — a value classifies it, a status is
    preserved as that status. Filling a gap is not a disagreement.

4.5 Inputs 1, 2, 3 and 4 that disagree produce a **conflict**. No value is asserted from them, and every
    competing declaration is recorded with the rule behind it.

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

4.8 A source may disagree with itself, and that is a conflict like any other. One value may declare
    several slots (3.10), and two cells or names of one row may reach one slot, so one source can hold
    two declarations for a file and slot. They reconcile **per claim**, as 4.4 and 4.5 reconcile any
    other declarations: agreeing ones classify, disagreeing ones conflict, and **nothing ranks them** —
    a direct column does not beat an implied one, which would be a tier ladder only inference has (4.3).
    A wrong implication is fixed by editing its row. Every claim records its column and raw value, not
    only the rule that made it, so the two can be told apart in the record.

## 5. Review

5.1 Every conflict is listable, with every competing declaration and the rule behind each.
    A conflict is not always two, and not always two values: a value against a status is one, and three
    inputs can disagree.

5.2 Every unmatched raw value is listable, with its source, dataset, table, column, slot, and the number of
    files it affects. Dataset is not optional: the same column name means different things in different
    datasets. Slot is not optional either: by 2.3 one raw value can be mapped for one slot and unmatched
    for another.
    "Unmatched" means the row 3.12 **selects** is not an authored one: a seeded row nobody has ruled on
    (3.11), or no row at all (3.7). Selection decides it, not whether an authored row exists somewhere —
    an authored default beneath a seeded scoped row loses to it, and the value stays queued. An authored
    row that deliberately declares nothing for the slot — the 3.10 case — has been ruled on, and leaves.
    The listing is therefore driven by the evidence rather than by the rows, which cannot see a value that
    has none; table, column and file count come from the evidence too, a mapping row carrying none.

5.3 A source that produces evidence matching no file is an error, not a silent zero.

5.4 The *value* mapping a person must review is the rule set.
    The slot map is reviewable too — a wrong table-or-column-to-slot mapping misroutes evidence before any rule runs.

5.5 **An LLM drafts rules and slot maps; it never classifies at runtime.** Turning a novel source
    schema into a mapping is what it is good at, and the output is a durable artifact a person
    reviews under 5.4 and the engine then executes deterministically. Flexibility is spent once,
    at authoring; determinism holds at every run. A runtime LLM is not one of 4.1's input kinds
    and may not become one: it would produce a claim no rule backs and nothing could review,
    against 3.2. Retired from ADR-0001, which decided it; that document is deleted and its salvage is #422.

5.6 **Review precedes a deploy.** The conflict list (5.1) and the unmatched-value list (5.2) are reviewed
    before a reconciled artifact is deployed. Review answers a conflict with a curator rule (4.7) or leaves
    it standing; either is a recorded outcome. Answering costs a reconcile (6.4), never a corpus run.
    The conflicts are listed by `make reconcile-report` (#395), by their competing values but not yet the
    rule behind each. Until curator rules (#397) exist, this is a stated rule and not a gate; the gate
    belongs with `make check-catalog` (#405).

## 6. The pipeline

6.1 A run has two stages: **infer**, then **reconcile**. Reading the sources — joining their evidence to
    our files — is reconcile's first step, not a stage of its own (6.7, #432).

6.2 Inference output is a kept artifact, not an intermediate. It is what inference alone concluded, and it is provenance.

6.3 Reconciliation writes its own output. It never rewrites inference output.

6.4 Reconciliation is re-runnable against a stored inference run, without re-inferring.
    Inference is the expensive half — network, headers, 708K files. Editing a rule that maps imported
    evidence must not cost a corpus run. Editing an inference rule changes the inference artifact, and does.

6.5 Both artifacts validate against the same schema. A reconciled record is a classification record like any other.

6.6 A run with no inputs but inference — no source evidence and no curator rules — produces a reconciled
    record that concludes exactly what its inference record concluded: the same value or status on every
    slot, from the same claims. It is not the same record: it hands inference's conclusions back unchanged
    and adds its reconciliation (6.10) — here, that no source declared anything and that each slot resolved
    to inference's answer. Sameness here is of what was concluded, not of the record or its bytes.

6.7 Reading sources is the reconcile stage's join, not a stage of its own (#432, which absorbed #402), and
    its measurement is a line of reconcile's report: per source and dataset, evidence offered, matched,
    unmatched and ambiguous, and by which key. The join is an equality lookup on the key the evidence
    envelope names; a line whose key two records carry attaches to neither.

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
    consistency reports, the md5 cross-registration check (#520), and every downstream consumer.
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

## 7. Published values

#424 built a `published` block on every output record and a report comparing it with the inferred
values; #497 made the published values an input (7.1, 7.2, 7.12). #513 deleted the block and the
report: once the values are an input, reconcile is where they meet the others (4.4, 4.5), and a
second place carrying them beside the answer only repeats it. 7.4–7.9 and 7.11 described that block and
report. Their numbers are kept, marked retired, so a citation of 7.12 still points where it did.

Written for **a repository**, not for AnVIL. AnVIL is the only publisher today, but nothing here
depends on that, and a second repository needs no change to these assertions.

7.1 The values a repository publishes for a dimension this project infers are its **published output**,
    the answer its users see today — and they are an input, kind 2 of 4.1, read from the repository's
    system of record by its published importer (7.12). Their mapping is a claim like any other: it goes
    through the translation table (3.9), and an authored row claims what it declares. 4.1 says why
    #424's retirement reversed.

7.2 **Inference never reads them.** They produce no claim inside inference, compete at no tier, and
    change no inferred value: the inference artifact (6.2) is the same with them present as without,
    the guarantee 6.6 makes about a run with no sources. They enter at reconcile, as evidence with the
    published importer's envelope as provenance, and are compared there with every other input (4.4,
    4.5).

7.3 They are transcribed **verbatim**: as the repository wrote them, a list wherever it published a
    list. Keeping element zero of a multi-valued cell is not dropping data, it is manufacturing a wrong
    answer, and 1.4's transcribe-verbatim rule governs them as it governs every other source's evidence.

7.4–7.9, 7.11 **Retired by #513.** They placed the values in a `published` block beside the inferred
    ones (7.4), carried them even where they yield no claim (7.5), recorded their vocabulary standing
    per file (7.6), required every producer to write the block (7.7), and ran a comparison after
    resolution that recommended without adopting (7.8, 7.9), in a repository-neutral vocabulary (7.11).
    Each described the block or the report, and neither exists. What they protected is kept elsewhere:
    the values reach the answer only through reconcile, as one input equal to the others (4.2);
    a published value no authored row maps, such as `GRCm39`, is listed with its file count in the
    review queue (5.2) rather than on a record; and which repository published a value is its evidence
    envelope's to say (2.1), not a field a run fills in.

7.10 Agreement is only decidable **after mapping**. `GRCh38 + Gencode40` and `GRCh38` are the same
     assembly and different strings, so reconcile compares a published value only through the
     translation table's row for it (3.9); guessing at equality would be 3.5's similarity matching by
     another route.

7.12 **Every repository has exactly one published source**, and exactly one importer reads it. Which
     table it is, is declared once (`pipeline.PUBLISHED_TABLES`: AnVIL's is the `anvil_file` table of
     its TDR snapshot) and its evidence carries `published_value`, a kind of its own so a reader of a
     conflict can tell the repository's value from a submitter's (kind 3). The declaration holds in both
     directions: a current evidence file that carries the label from any other table or from a
     repository other than the one its rows are about, one from the declared table under any other
     label, or a second one for a dataset of one catalog version, is refused before a run starts
     (`source_evidence.require_one_published_source`). A repository whose published source is not yet
     declared — HPRC today, see "What is not true yet" — can have no file claim one until it is. The
     compact Azul manifest is
     not a published source: it is a join AnVIL's index produces, and may hand a run its own output back.
     Until the published importer reads a snapshot's tables through either reader (#508), the verbatim
     manifest — the TDR tables synced down as a file, one row per line in TDR's column names — stands
     in for the tables, and the published importer is the
     submitter-table importer run over a second slot map (`anvil_published_slot_map.yaml`).

7.13 **A conflict is deliverable.** A slot in `conflict` is delivered as it is: no value, status
     `conflict`, every competing declaration in its evidence, and `use: published`, which tells the
     indexer to keep the value the repository already publishes. A `not_classified` slot carries the same
     instruction. A delivery never picks a side, and shipping a conflict does not make the delivered answer
     worse than the published one: our value is null and the published value is untouched (#432). A slot
     that is `classified` or `not_applicable` carries `use: meta_disco`. `use` is computed by reconcile, so an
     export (#444) is structure only; the published value never enters our record, whose values stay in
     our vocabulary.

---

## What is not true yet

No code reads this document, and parts of the pipeline it describes do not exist. In section 7, the
importer's half is built — 7.12 is enforced (below), and the published importer reads the system of record
(7.1, today through the verbatim manifest, 7.12) and transcribes verbatim (7.3, #497, #421) — and what 7.1,
7.2, 7.10 and 7.13 say about claims, comparison and delivery is the reconcile stage's (#432), which is built. Parts of it *are* enforced independently: `make_claim` refuses a claim that declares two things at once, or that carries a tier where none belongs, and `source_evidence` refuses a line that carries a mapped value at all (#421) — its record has no member for one, and `_entry_from_line` turns away a hand-written line that has. A declared term is checked against its slot's vocabulary when the translation table loads (`value_map`, #414) — on authored rows, per 3.11; no runtime constructor checks it. 3.3 is enforced for rule claims anyway — `test_rule_vocabulary` checks every rule's `then` value against the LinkML enums at CI time, and output is validated at the schema gate — but **no runtime constructor checks it**. Nothing checks these assertions as a set. Enumerated rather than asserted, because "the contract holds" is the obvious sentence and it is false in each place below:

- **1.1 is already violated.** `scripts/classify_index_files.py` builds value- and status-bearing evidence outside the rule engine, stamping `rule_id: inherited_from_parent` and its `source_type` by hand. CLAUDE.md documents this as a deliberate exception, because it copies a parent's *already-resolved* status — `conflict` included — which `make_claim` cannot express. Moving it into the engine is its own work and interacts with #371 — filed as #413, which also asks whether the honest fix is a clause here rather than a code move.
- **The slot maps and their importer exist for AnVIL only** (#369, #497): `slot_map` loads
  `sources/anvil_slot_map.yaml` (kind 3) and `sources/anvil_published_slot_map.yaml` (kind 2),
  `anvil_evidence` writes generations of evidence files under `data/source_evidence/anvil/` and
  `.../anvil_published/`, and `source_evidence.discover` reads the newest per dataset. So 2.4's
  absence-is-the-statement half, 2.5's generations and 2.8's two exclusions are enforced for that one
  repository, and 7.12 at the map for AnVIL and at the run for every repository; that a map was
  authored from nothing a run concluded is
  not enforceable, and a test greps each file for the strings that would say otherwise. No other source
  has a map and there is no rule scope for source evidence. Inference consumes none of what is written;
  the value map's seeder and review queue read it, and so does reconcile (#432).
- **The translation table is read by reconcile alone** (#414, #432). `value_map` holds 3.9's row,
  enforces 3.11's split, 3.12's scope and collision rules and 3.5's bound, seeds from evidence and lists
  5.2's queue; `claims_from` builds a line's claims through `make_claim`, and reconcile is its caller.
  Which values have a row is `make review-queue`'s to say, not this document's. 3.7's queue is still a
  listing a person runs, not a place a run sends a value to: reconcile counts an unreviewed value in its
  report and, for the published source, lets it move the slot (7.13), but writes no queue.
- **HPRC's published source is not declared** (7.12). `PUBLISHED_TABLES` names AnVIL only; which HPRC
  catalog is the system of record for what HPRC publishes is undecided, so the HPRC run has no published
  evidence and a file claiming to be it is refused until the declaration exists.
- **Reconcile is a command, not a phase of `make classify`** (#432). `make reconcile` runs it against a stored run; nothing runs it after inference on its own, and a stored run does not record which input it was classified from (#404), so reconcile reads the deployment's input envelope and cannot prove it is the run's.
- **6.9 holds for `corpus_diff` only.** It is told which artifact it compares; the coverage, validation and consistency reports still read the inference artifact.
- **6.11 holds for the reconciled artifact only.** It is NDJSON under `<run>/reconciled/`; inference output is still pretty-printed JSON at the run root (#448, #271).
- **No curator rule exists** (4.7, #397). Every conflict stands unanswered, which 7.13 makes deliverable.
- **5.1 is met for values, not rules.** `make reconcile-report` (#395) lists each conflict's competing values
  per input, counted per distinct set; the rule behind each value is on the reconciled record, not in the list.

A line leaves this section when the assertion above it is enforced, not when it is merely intended.

---

## What this changes

- **A claim file becomes an evidence file.** *Done in #421.* #401's envelope, NDJSON discipline, and both-sides-of-the-join naming survived; the per-line record stopped being a claim and became an observation carrying `raw_value` and no mapped value. `source_type` moved to the envelope, where it is constant for the file.
- **"The importer owns the mapping" is reversed.** Rules own it. The importer owns the slot map.
- **`declined` moves to the slot map.** A table name or column judged not to speak to a slot is not mapped, and its absence is the statement (2.4); the reason is recorded on the issue and the pull request, not in the map. It is not a claim, not a rule, and never reaches resolution. The decline is scoped to the column, as the schema's own `declined` definition already scopes it.
- **A conflict is not a reason to decline** (4.8, #369). A name that disagrees with inference is a source saying something the resolver records under 4.5; dropping it at import would author one input from another, which 3.4 forbids.
- **#408 dissolves.** There are no imported claims, so there is no no-tier-on-an-imported-claim rule to place.
- **#396 folds into the engine.** Cross-source comparison is resolution stage two, not a separate step.
- **#369 shrinks** to the AnVIL slot map plus a reader. No vocabulary in it.
- **`output/anvil/<run>/*_classifications.json` stops being the answer.** It becomes inference output, kept as provenance. The reconciled artifact is the answer.
- **`manifest_survey.NAME_TOKENS` splits** — the name→slot half to the slot map, the token→term half to rules. *The name→slot half is in the AnVIL map (#369), which declares each span under its slot and is tested against the survey's list; the token→term half is in
  `value_map.yaml` (#414), authored for the two HPRC datasets.*

## Open

- ~~Rule-id namespace: unique across the whole rule set, or namespaced per source.~~ **Answered by #414: one
  namespace, kept disjoint by shape.** A claim cites either kind by `rule_id`. A row id is `<slot>.<slug>`
  and the value map's loader requires the slot prefix; no rule id contains a dot, and `test_value_map` checks
  that against the loaded rule set, so neither loader reads the other.
- ~~What an inference-resolved `conflict` does in stage two.~~ **Answered by #432 (maintainer, 2026-09-22):
  it stands.** A source agreeing with one of two disagreeing rules is agreement with a claim, not resolution
  of a conflict, which 4.7 reserves for a curator rule; the source's claim is recorded beside it.
- ~~The conflict rate on a second dataset.~~ **Measured by #432** over the ten datasets with evidence: 3,291
  conflicting slots across the corpus, concentrated in a few places a person can read — unaligned BAMs
  inference calls `alignments` where the submitter says `unaligned reads` (1,539, `AnVIL_HPRC_R2`), FASTQs
  inference calls `not_applicable` beside a declared assembly (558, `ANVIL_T2T_CHRY`), published values no
  authored row reads yet (1,048, the ENCORE and IGVF datasets), and inference's own conflicts carried through
  (138). The numbers are on the PR.
- ~~Whether input kind 2 (AnVIL harmonized fields) is read today at all.~~ **Answered twice** — #424 no,
  #472/#497 yes (maintainer, 2026-09-21); 4.1 carries the reasoning. The number was never reused.
- What a sentinel raw value (`""`, null, `unspecified`, `NA`) produces. Currently: an ordinary rule, yielding a state to be decided.
- ~~How the review queue (3.7, 5.2) distinguishes *we have no word for this* from *no rule has ever seen
  this*.~~ **Answered by 3.11 (#435): neither is recorded, because authorship is.** The question assumed
  two recorded states, and nothing marks a value as examined, so no producer could have written either
  honestly. A seeded row nobody has authored and a value with no row are both simply unauthored, and 5.2
  lists them the same way.
- How the review queue keeps the raw value through the retirement of `unmapped` and `no_vocabulary_term`.
  3.7 retires both `claim_state` entries — a value no rule matched produces no claim at all, so there is no
  claim left to carry a state — and the queue must hold the raw value some other way. A migration to
  describe, not a gap to fill. Split out of the item above, which answered a different question.
- Whether instrument model deserves a slot of its own. It is a finer fact than `platform`, our vocabulary has
  no word for it, and today it survives only as the `raw_value` behind a `platform` claim. A dimension
  question for #364 rather than a mapping one.
- Whether a subject-level key and subject-level slots are worth adding. Without them IGSR, which keys by sample id, cannot be imported at all — correctly, but at the cost of a source. Related to the instrument-model question above, to #336 and to #361.
- What the two artifacts are called. `*_classifications.json` means inference today and the name should be corrected rather than inherited. This is #271's scope — it already covers naming drift in `output/`, and it says it can land independently of the rest of #268.
- ~~How many files carry a source-declared value for a slot inference calls `not_applicable`.~~ **Measured by
  #432:** 564 slots — 558 FASTQs in `ANVIL_T2T_CHRY` with a declared `GRCh38`, and 6 `assay_type` slots in
  `ANVIL_NIA_CARD_Coriell_Cell_Lines_Open`. Small enough that 4.6 stands.
