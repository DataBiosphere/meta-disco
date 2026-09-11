# Contract: evidence, claims, and who may make them

**Status:** Draft — assertions under discussion
**Date:** 2026-09-11
**Supersedes framing in:** #391 (epic), #392 (PR #403, merged), #401 (PR #407, merged)

Importers say what was written. Rules say what it means. Only rules make claims.

---

## 1. Roles

1.1 Only the rule engine makes claims. No importer, script, or external source makes one.

1.2 An importer produces **evidence**, never a claim.

1.3 The importer maps **structure**; the rule engine maps **meaning**.

1.4 An importer transcribes a raw value **verbatim** — it does not normalize, translate, correct, or suppress it.

1.5 An importer needs no knowledge of our controlled vocabulary, and may not contain one.

1.6 A curator is a source like any other, and the only one that wins.

1.7 A curator writes rules. A curation decision is a rule like any other and is reviewed as one;
    a decision about a single file is a rule whose selection matches one file, not an exception to 1.1.

## 2. Evidence

2.1 Evidence is `(file, slot, raw_value)` plus provenance: source, dataset, table, column.

2.2 The importer decides **which slot** a table or column speaks to. It never decides what the value means.

2.3 One column may speak to more than one slot. One raw value may produce several evidence rows.

2.4 Evidence records what the source said, **including when we believe the source is wrong.**
    Suppressing at import hides the disagreement from review and smuggles a judgment into the importer.

2.5 Evidence **imported from a source** is fetched out of band, with network, and read offline and deterministically.
    Inference fetches its own headers and content during the run, through the evidence cache, and always has.

2.6 A table name and a column name are evidence, the same as a cell value.

## 3. Claims

3.1 A claim is a rule's declaration about a slot, derived from evidence. It declares a **value** or a **status**.

3.2 Every claim names the rule that made it — including an identity mapping. There is no implicit copy.

3.3 A claim that declares a value declares a term in the controlled vocabulary, or it is not a claim.

3.4 A rule that maps imported evidence matches on `(slot, raw_value)` and may condition on provenance;
    normally it does not. This is what keeps one rule set working across every source.
    Inference rules match their own signals — extension, filename, header, content — as they do today.

3.5 Nothing fires by similarity. Matching is exact, over spellings a rule declares explicitly.

3.6 `not_applicable` is a rule's to declare. No source asserts it in evidence.

3.7 A raw value no rule matched produces no claim and enters the review queue.

## 4. Sources and resolution

4.1 There are five input kinds:
    1. inference (filename, extension, header, content)
    2. canonical repository metadata (AnVIL harmonized fields)
    3. non-canonical repository metadata (submitter tables)
    4. external repository (HPRC Data Explorer, ENA, IGSR, reference sources)
    5. curator

4.2 Inputs 1–4 are equal. Being ours confers no rank; being external confers no rank.

4.3 Resolution has two stages: **within** a source by tier, then **across** sources by agreement.

4.4 Sources that agree classify the slot, and every agreeing source is recorded.
    A slot on which only one input speaks is classified from it: filling a gap is not a disagreement.

4.5 Sources that disagree produce a **conflict**. No value is asserted. Both values and both rules are recorded.

4.6 A curator decision wins a conflict. It is a rule, it carries its reason, and it is recorded like any other rule.

## 5. Review

5.1 Every conflict is listable, with its competing values and the rule behind each.

5.2 Every unmatched raw value is listable, with its source, dataset, table, column, and the number of files it affects.
    Dataset is not optional: the same column name means different things in different datasets.

5.3 A source that produces evidence matching no file is an error, not a silent zero.

5.4 The *value* mapping a person must review is the rule set.
    The slot map is reviewable too — a wrong table-or-column-to-slot mapping misroutes evidence before any rule runs.

## 6. The pipeline

6.1 A run has three stages: **infer**, **read sources**, **reconcile**.

6.2 Inference output is a kept artifact, not an intermediate. It is what inference alone concluded, and it is provenance.

6.3 Reconciliation writes its own output. It never rewrites inference output.

6.4 Reconciliation is re-runnable against a stored inference run, without re-inferring.
    Inference is the expensive half — network, headers, 708K files. Editing a rule that maps imported
    evidence must not cost a corpus run. Editing an inference rule changes the inference artifact, and does.

6.5 Both artifacts validate against the same schema. A reconciled record is a classification record like any other.

6.6 A run with no source evidence produces a reconciled record identical to its inference record.

6.7 Reading sources is a stage of its own, separate from reconciling them, and is measured on its own: evidence offered, evidence matched, and by which key.

6.8 Resolution within a source is by tier. Resolution across sources is by agreement, and is not tier math.

---

## What this changes

- **A claim file becomes an evidence file.** #401's envelope, NDJSON discipline, and both-sides-of-the-join naming survive. The per-line record stops being a claim and becomes an observation: it carries `raw_value` and no mapped value.
- **"The importer owns the mapping" is reversed.** Rules own it. The importer owns the slot map.
- **`declined` has no remaining use.** A column that should not speak to a slot is simply not mapped to it; a source that says the wrong thing is out-argued by a rule that reads more context.
- **#408 dissolves.** There are no imported claims, so there is no no-tier-on-an-imported-claim rule to place.
- **#396 folds into the engine.** Cross-source comparison is resolution stage two, not a separate step.
- **#369 shrinks** to the AnVIL slot map plus a reader. No vocabulary in it.
- **`output/anvil/<run>/*_classifications.json` stops being the answer.** It becomes inference output, kept as provenance. The reconciled artifact is the answer.
- **`manifest_survey.NAME_TOKENS` splits** — the name→slot half to the slot map, the token→term half to rules.

## Open

- Rule-id namespace: unique across the whole rule set, or namespaced per source.
- The conflict rate on a second dataset. The spike measured ~0.1% on `AnVIL_HPRC_R2` alone; at 1% across the corpus the review queue stops being viable and 4.5 needs rethinking.
- Whether input kind 2 (AnVIL harmonized fields) is read today at all.
- What a sentinel raw value (`""`, null, `unspecified`, `NA`) produces. Currently: an ordinary rule, yielding a state to be decided.
- How the review queue (3.7, 5.2) distinguishes *we have no word for this* from *no rule has ever seen this*. Both produce no claim today. #399 needs the first to be an explicit, reasoned decision that stays visible, which the contract does not yet give it a way to say.
- Output naming and layout. "Output" currently means inference output; the reconciled artifact needs a name and a place, and that decision collides with the layout epic (#268 / #271).
- Which consumers read which artifact. `corpus_diff`, the coverage / validation / consistency reports, the ENA validator on stored output (#330) and the eval fixtures each want inference or reconciled output, and today there is only one.
