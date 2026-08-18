# phs-anchor survey findings (issue #324)

Survey run 2026-08-15 with the `phs-anchor` skill
(`.claude/skills/phs-anchor/`) over the open-access AnVIL datasets. One
dossier per distinct study in this directory; this file is the cross-study
read-out.

## The test set is not what we expected

- Azul filtered to `accessible: true` returned **12 workspaces**, not the 13
  recorded in ADR-0001 (snapshot drift; not re-reconciled this round).
  Reproduction note: this survey predates the adapter rework — today's
  `datasets` subcommand returns the full unfiltered catalog (see
  anvil-phs-marker-papers.md for the all-studies sweep); the 12-workspace
  scope here was the then-current `accessible=true` query.
- Only **3 distinct phs accessions** exist among them: phs003018 (both ENCORE
  workspaces), phs003472 (IGVF Mouse R1), phs003224 (NIA CARD Coriell). The
  other 8 workspaces have `registered_identifier` of `"none"`/null — T2T,
  T2T_CHRY, HPRC, HPRC_R2, 1000G ×2, MAGE, nhp_dGTEx are consortium
  workspaces with **no dbGaP anchor at all**.
- Consequence: for the open-access set, "phsid → paper" is the *minority*
  path; the majority path is "workspace/consortium name → paper". The skill's
  fallback chain, not its accession chain, did most of the work.

## Per-source publication hit rate

Over the 3 phs-anchored studies (accession-based sources) and all 9 study
groups (fallback sources):

| Source | Hits | Notes |
| --- | --- | --- |
| GapExchange XML (dbGaP FTP) | 0/3 | phs003018, phs003224: no FTP dir (404); phs003472: XML exists, zero PMIDs. On mature phs000424 it returns 9 PMIDs with the marker paper listed first — the best source *when populated*. |
| dbGaP study page (static HTML) | 0/3 for publications | Rich prose (species, assays, PIs, grants) every time; "Selected Publications" is JS-loaded and empty in fetched HTML — GapExchange XML is that section's data. |
| PMC full-text accession search | 0/3 | phs000424 control: 1,671 hits. The channel works; the open studies simply have no accession-citing literature yet. |
| PubMed `[SI]` | 0/3 | Sparse even for GTEx (1 hit). Corroboration only. |
| dbGaP FHIR `Citers`/publications | 0/3 | Present on phs000424 (670 citers, title + PMC URL each); absent on all three open studies. |
| NIH RePORTER grant→publications | 2/2 probed | phs003472 (26 grants): 623 distinct PMIDs; ranking by "linked by how many of the study's grants" put the marker papers at the top — of the 4 papers linked by 26/26 grants, two are marker papers (PMIDs 37547663 — which the title search had missed — and 39232149), one is a catalog-description paper (unread, role unclear), one is a variant-specific study. phs003224 (single intramural ZIA grant): resolves and grant-verifies the ONT-pipeline candidate among 417 linked papers, but one grant gives no ranking signal. Not applicable to phs003018 (its study page lists no grants). |
| PubMed title-word search | 9/9 groups got at least a candidate | Markers identified for 7 groups (ENCORE, IGVF, T2T ×2, 1000G-HC, HPRC r1, MAGE, nhp dGTEx); candidates only for NIA CARD (program-matched, role unclear) and 1000G-PRIMED (underlying-data marker); no paper specific to HPRC release 2. Caveat: quoted-phrase queries return 0 for titles missing from PubMed's phrase index — use unquoted ANDed `[Title]` words with stopwords dropped. |

**Headline:** every dbGaP-anchored publication channel returned zero for the
current open-access studies — they are young and thin in dbGaP. Publication
discovery succeeded anyway, but via title/name search with human judgment,
and those assignments are title-matches, not accession-verified links.

## FHIR field coverage (3 open studies + phs000424 control)

Always populated: `title`, `status`, `description`, `category`,
`sponsor.display`, `StudyOverviewUrl`, `Content` counts. Sometimes:
`focus`/`condition`/`keyword` + `StudyConsents` + `ReleaseDate` (IGVF only,
of the three). Only on the mature control: `MolecularDataTypes` (coded
values like "CNV Genotypes"), `Citers`, `enrollment`, `ComputedAncestry`.

So the FHIR record is a reliable source of study *prose* and sponsor/design
context today, and a publication+molecular-data-type source only for mature
studies. The `description` field was the single most metadata-informative
field across the young studies (species, cell lines, platform, assay all
appear there as text).

## Description hoisting measurement (backs the `studies` subcommand)

The `studies` subcommand hoists workspace descriptions to study level.
Measured 2026-08-17 on the live snapshot: grouping the fully-paginated
unfiltered `datasets` output by phsid gave 30 multi-workspace studies, of
which 27 carried descriptions identical after stripping leading/trailing
whitespace across all their
workspaces; the 3 exceptions were blank/"[Description currently not
available]" placeholders plus one study (phs002502) with two near-identical
variants. Hence the hoist policy: longest non-placeholder description wins,
`descriptions_differ` flags disagreement.

## Retired/broken paths (don't retry)

- `elink gap→pubmed` does not work: E-utilities' `einfo` list (raw JSON)
  contains no dbGaP database and `esearch`/`elink` return the API's own
  validation error ("Invalid db name specified: gap"; verified 2026-08-15
  against the raw API — not a bot block: the same client succeeds against
  `db=pubmed`/`db=pmc`). The old Entrez web path
  `www.ncbi.nlm.nih.gov/gap/` now redirects to the standalone
  `dbgap.ncbi.nlm.nih.gov` application. No retirement announcement was
  found — the [NCBI Insights dbGaP archive](https://ncbiinsights.ncbi.nlm.nih.gov/tag/dbgap/)
  had no post about removing Entrez search when checked (2026-08-15); the
  migration context is the site modernization announced in
  ["Beta Now Live! New & Improved dbGaP Homepage Design"](https://ncbiinsights.ncbi.nlm.nih.gov/2025/06/02/beta-improved-dbgap-homepage/)
  (June 2025).

## Sanctioned programmatic access post-Entrez (researched 2026-08-15)

What NCBI documents as the ways to query dbGaP programmatically, and where
this skill stands on each:

- **dbGaP FHIR API** — NCBI's stated interoperability path for dbGaP (NCPI
  FHIR pilot; see the 2025 GIM Open abstract
  ["Enhancing dbGaP interoperability with FHIR APIs"](https://www.gimopen.org/article/S2949-7744(25)00491-1/fulltext)).
  Already the skill's `fhir` subcommand.
- **dbGaP FTP GapExchange XML** — already the skill's `gap-exchange`
  subcommand.
- **[SSTR API](https://ncbiinsights.ncbi.nlm.nih.gov/2023/04/27/dbgap-subject-sample-telemetry-report/)**
  (Subject Sample Telemetry Report, 2023) — per-study subject/sample/consent
  telemetry; not publication-relevant, but a candidate metadata channel for
  later epics.
- **Advanced-search CSV export** — the dbGaP advanced-search UI exports
  study lists as CSV; ncpi-dataset-catalog's `dbGapCSVandFTP.ts` ingests
  exactly this. Not automated here.
- **Undocumented lead**: the new `dbgap.ncbi.nlm.nih.gov` beta app
  configures an `apiBaseUrl` in its page source, so a JSON backend exists;
  obvious route guesses 404 (probed 2026-08-15) and mapping the real routes
  would require reading the app's JS bundle. Future work.
- Quoted-phrase PubMed title queries silently return 0 for phrases absent
  from the phrase index (`quotedphrasesnotfound`).

## Reference implementation found

`NIH-NCPI/ncpi-dataset-catalog` already assembles per-study `publications`
from two channels: the GapExchange XML
(`catalog-build/fetch-dbgap-selected-publications.ts`) and NIH RePORTER
grant→publication links (`catalog-build/fetch-grant-publications.ts`,
API v2). Both are now implemented in the skill (`gap-exchange` and
`reporter` subcommands). The RePORTER probe on IGVF validated the channel
(see the table above): it is the only source that found publications for a
young phs study, and its grant-count ranking surfaced a marker paper the
title search missed. Implementation note: `projects/search` rejected
`*serial*` wildcards in our tests, but `publications/search` accepts
leading-wildcard `core_project_nums` (`*HG012047`) directly.

## Early observations: what the papers/records could justify (informal, ahead of Epic 2/3 extraction)

- Organism: nhp_dGTEx is non-human primate; everything else surveyed is
  human — an organism dimension would be immediately constrainable.
- Modality constraints: 1000G-HC is DNA-only WGS; MAGE is RNA-seq of LCLs
  (per Azul description); ENCORE is RBP-binding + knockdown transcriptomics
  (per dbGaP prose); NIA CARD is ONT long-read WGS with platform stated
  outright.
- Caution learned: study anchor ≠ workspace content (IGVF's dbGaP record
  never states an organism while the workspace is mouse; PRIMED repackages
  another study's callsets). Constraints must attach at the right level.

## Epic 2 go/no-go

**Go, with reframed scope.** Marker papers were identified for 7 of 9 study
groups (candidates only for NIA CARD and 1000G-PRIMED) — identified by title
match, with independent grant-link corroboration only for IGVF and NIA CARD
— and their methods sections plus the dbGaP/Azul
descriptions clearly carry organism/modality/platform facts. But the
accession is not the reliable key for open-access AnVIL — Epic 2 should take
the dossier (paper list + descriptions), not a phsid, as its input, and
extraction should cover the dbGaP/Azul description prose as well as the
paper text.
