---
name: phs-anchor
description: Given a dbGaP phs accession (e.g. phs000424), find the study's marker/methods publication(s) and capture its structured dbGaP FHIR record, each fact with provenance. Use when asked to look up a study's publication, survey a study's dbGaP metadata, or build a study dossier under docs/studies/. Issue #324.
---

# phs-anchor: query the phs anchor for a study

Input: one **phsid** (e.g. `phs000424`). Output: a dossier at
`docs/studies/<phsid>.yaml` following the template below.

Two channels, in this order. Publication discovery is the primary goal; the
FHIR record is a separate, additional channel — do not let it substitute for
finding the paper.

Every fact in the dossier carries provenance (which source, which field, or
which page). Never guess a paper: if discovery comes up empty, record
`publications: []` and list the sources checked with their outcomes.

## Phase 1 — find the publication(s)

Try the sources in this order and record hit/miss per source in
`sources_checked`, even for sources tried after a hit — the survey needs
per-source hit rates, not just first-hit provenance.

1. **GapExchange XML (dbGaP FTP)**:
   `python3 .claude/skills/phs-anchor/fetch_phs.py gap-exchange <phsid>` — the
   machine-readable "Selected Publications" list. When present, the marker
   paper is typically listed first (see findings.md). Young studies may have
   no FTP dir yet (a clean `no dbGaP FTP directory` result) or list zero
   PMIDs — record that as a miss.
2. **dbGaP study page**: WebFetch
   `https://www.ncbi.nlm.nih.gov/projects/gap/cgi-bin/study.cgi?study_id=<phsid>`
   — study title, molecular-data prose, attribution (PIs, grant numbers).
   Known limitation: its "Selected Publications" section is JS-loaded and
   empty in fetched HTML — source 1 is that section's data.
3. **PMC full text**: `fetch_phs.py pmc <phsid>` — papers whose indexed full
   text contains the accession. The marker paper usually cites its own
   accession; secondary analyses cite it too, so judge roles from titles/years
   (earliest consortium-titled paper is a marker candidate).
4. **PubMed [SI]**: `fetch_phs.py pubmed-si <phsid>` — papers that registered
   the accession as a secondary source ID. Known sparse (papers
   self-register); treat as corroboration.
5. **FHIR citations**: `Citers` extension entries (title + PMC URL) found in
   the Phase 2 fetch also count as publication provenance — fold them in here.
   Populated only for mature studies (see findings.md for observed coverage).
6. **ncpi-dataset-catalog** (`NIH-NCPI/ncpi-dataset-catalog`): its built
   catalog carries per-study `publications`, assembled from the same
   GapExchange XML plus NIH RePORTER grant→publication links
   (`catalog-build/fetch-dbgap-selected-publications.ts`,
   `catalog-build/fetch-grant-publications.ts`) — consult it as a
   cross-check, and as the reference implementation for both channels.
7. **NIH RePORTER (grant → publications)**:
   `fetch_phs.py reporter <serials>` with the comma-separated grant serials
   from source 2's attribution page (e.g. `HG012047,HG012022`). Output ranks
   PMIDs by how many of the study's grants link them — papers linked by
   (nearly) all grants are consortium/marker candidates (see the phs003472
   example in findings.md). Needs grant numbers to exist on the study page.
   ZIA (intramural) serials resolve too, but a single-grant study yields no
   ranking signal — expect a large undifferentiated list. Resolve the
   top-ranked bare PMIDs to titles/years with `fetch_phs.py esummary
   <pmids>` before judging roles (provenance slug: `pubmed-esummary`).
8. **AnVIL dataset record**: `fetch_phs.py datasets` output for this study —
   description prose often names the consortium/portal to search next.
9. **Fallback**: PubMed title-word search built from the study/consortium
   name (unquoted, stopwords dropped — PubMed's phrase index misses many
   titles and quoted phrases can return 0 for papers that exist); WebSearch.

Do NOT use Entrez `db=gap` — E-utilities no longer exposes a dbGaP database
(`elink gap→pubmed` is dead). See findings.md "Retired/broken paths" for
the evidence, and for the `dbgap.ncbi.nlm.nih.gov` application lead worth
probing as future work.

Label each found publication's `role`: `marker` (describes the study/cohort
itself — the methods paper), `secondary` (uses the data), or `unclear`. Only
assign `marker` when the title/abstract shows the paper describes this study;
otherwise `unclear`.

## Phase 2 — dbGaP FHIR record

`python3 .claude/skills/phs-anchor/fetch_phs.py fhir <phsid>`

From the returned Bundle, record under `dbgap_record`: every populated
metadata-relevant field with its raw value and its FHIR field/extension path
(title, description, category, focus, condition, enrollment, sponsor, keyword,
and any extensions — molecular data types, study design, consent groups,
citers). Also record which of those expected fields came back empty — the
survey question is what this API reliably populates.

## Phase 3 — write the dossier

`docs/studies/<phsid>.yaml`:

```yaml
phsid: phs000424
title: <dbGaP study title>
anvil_datasets: [<AnVIL workspace titles, if this study maps to any>]
publications:
  - pmid: "23715323"
    pmcid: null        # when known
    doi: null          # when known
    title: <paper title>
    year: 2013
    role: marker       # marker | secondary | unclear
    provenance: [pmc-fulltext, pubmed-si]   # every source that surfaced it
secondary_count: 42    # total accession-citing papers found (PMC count)
dbgap_record:
  populated:
    - path: ResearchStudy.title
      value: <...>
    - path: ResearchStudy.extension[.../ResearchStudy-MolecularDataTypes]
      value: [<...>]
  empty: [<field/extension names checked but absent>]
sources_checked:
  # Use these canonical source slugs (one entry per source tried, in order):
  # gap-exchange, dbgap-study-page, pmc-fulltext, pubmed-si, fhir,
  # ncpi-dataset-catalog, reporter, azul, pubmed-title-search, websearch
  - source: gap-exchange
    outcome: <hit | miss | partial — one line on what it gave>
  - source: dbgap-study-page
    outcome: <...>
  - source: pmc-fulltext
    outcome: <...>
  - source: pubmed-si
    outcome: <...>
  - source: fhir
    outcome: <...>
  - source: reporter
    outcome: <...>
notes: <anything surprising, one short paragraph max>
```

For a dataset with no phs accession (Azul `registered_identifier` is
`"none"`), there is no anchor: write the dossier named after the workspace
title instead, note the missing accession, and run only the
publication-fallback sources.
