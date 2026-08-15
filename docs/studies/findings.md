# phs-anchor survey findings (issue #324)

Survey run 2026-08-15 with the `phs-anchor` skill
(`.claude/skills/phs-anchor/`) over the open-access AnVIL datasets. One
dossier per distinct study in this directory; this file is the cross-study
read-out.

## The test set is not what we expected

- Azul (`accessible: true`) returned **12 workspaces**, not the 13 recorded in
  ADR-0001 (snapshot drift; not re-reconciled this round).
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
| GapExchange XML (dbGaP FTP) | 0/3 | phs003018, phs003224: no FTP dir (404); phs003472: XML exists, zero PMIDs. On mature phs000424 it returns 39 PMIDs with the marker paper listed first — the best source *when populated*. |
| dbGaP study page (static HTML) | 0/3 for publications | Rich prose (species, assays, PIs, grants) every time; "Selected Publications" is JS-loaded and empty in fetched HTML — GapExchange XML is that section's data. |
| PMC full-text accession search | 0/3 | phs000424 control: 1,671 hits. The channel works; the open studies simply have no accession-citing literature yet. |
| PubMed `[SI]` | 0/3 | Sparse even for GTEx (1 hit). Corroboration only. |
| dbGaP FHIR `Citers`/publications | 0/3 | Present on phs000424 (670 citers, title + PMC URL each); absent on all three open studies. |
| PubMed title-word search | 8/9 marker or candidate | Found every flagship paper (ENCORE, IGVF, T2T ×2, 1000G-HC, HPRC r1, MAGE, nhp dGTEx); only HPRC release 2 has no identifiable paper. Caveat: quoted-phrase queries return 0 for titles missing from PubMed's phrase index — use unquoted ANDed `[Title]` words with stopwords dropped. |

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

## Retired/broken paths (don't retry)

- Entrez `db=gap` no longer exists — `elink gap→pubmed` is dead
  (E-utilities rejects the db name; verified 2026-08-15).
- Quoted-phrase PubMed title queries silently return 0 for phrases absent
  from the phrase index (`quotedphrasesnotfound`).

## Reference implementation found

`NIH-NCPI/ncpi-dataset-catalog` already assembles per-study `publications`
from exactly two channels: the GapExchange XML
(`catalog-build/fetch-dbgap-selected-publications.ts`) and NIH RePORTER
grant→publication links (`catalog-build/fetch-grant-publications.ts`,
API v2 `projects/search` + `publications/search`). Its built catalog is both
a cross-check and the model for automating our chain. RePORTER was **not
probed** this round — with 26 NHGRI grant numbers on IGVF's attribution
page, it is the most promising untried channel.

## What the papers/records can already justify (Epic 2/3 preview)

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

**Go, with reframed scope.** Marker papers exist and are identifiable for
8/9 study groups, and their methods sections plus the dbGaP/Azul
descriptions clearly carry organism/modality/platform facts. But the
accession is not the reliable key for open-access AnVIL — Epic 2 should take
the dossier (paper list + descriptions), not a phsid, as its input, and
extraction should cover the dbGaP/Azul description prose as well as the
paper text.
