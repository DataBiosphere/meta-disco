# ADR-0001: Metadata classification architecture — deterministic engine executing LLM-authored artifacts, import where declarations survive

- **Status:** Accepted (2026-07-31)
- **Deciders:** meta-disco team
- **Related:** #298 (BED reference inference), #299 (unreadable vs read-but-not-this-type), #300 (coverage data_type), #301 (producing method from filename), #302 (import — umbrella), #303 (get ahead of ingestion), #304 (dataset → origin registry), #307 (GTEx import), #310 (HPRC import — first build), #308 (image confidence), #309 (tissue/anatomy schema), #311 (data-format tail), #312 (companion-file resolution)

## Context

meta-disco classifies AnVIL open-access files into five dimensions — `data_modality`, `data_type`, `reference_assembly`, `assay_type`, `platform` — because the source metadata (especially NHGRI AnVIL) has a large hole. Its two purposes are: (1) **reduce ingest burden**, and (2) **classify data whose original submission is long gone**.

Coverage (re-measured on the 2026-08-02 run over the 733,877-file snapshot): of ~734K open-access files, **~669K are classifiable data files and ~97.5% of those receive at least one field** (most two or three). The figures below are the *concrete-value* rate — files whose dimension resolved to `status=classified` (i.e. a real value, **excluding** `not_applicable`), measured over those data files. On that basis meta-disco is strong on `data_type` (~97%), `data_modality` (~92%), and `reference_assembly` (~68%), but **thin on `assay_type` and `platform` (~8–9%)** — which is precisely where import is aimed. (The coverage report's headline instead counts `not_applicable` as classified, so it shows higher rates there — e.g. `assay_type`/`platform` ~18–22%; that is the same concrete signal viewed with a looser denominator, not a different result.) About ~72K files receive no concrete field: ~55K are non-data files (checksums/logs/docs — excluded from the ~669K data-file denominator above, and mostly resolved to `not_applicable`), plus a ~16K tail of data formats without rules yet (#311/#312).

Two engine approaches have existed:
- **Original:** a runtime LLM (local, Ollama) reasoning over diverse inputs. Removed.
- **Current:** a deterministic, tiered rule engine (`unified_rules.yaml`), with rules authored with LLM help ("AI-generated rules").

The question this ADR settles: given the hole, do we lean on the deterministic rules, revive a runtime LLM, or something else?

## Empirical backbone (per-type deep-dive measured 2026-07-30, on the re-pulled catalog)

The decisive evidence is the **ceiling of content-based inference**, which is set by the data, not the method:

- **FASTQ (21,270 files):** `platform` **100% classified** (Illumina/PacBio/ONT, from read names), but `data_modality` **100% not_classified** and `assay_type` **100% not_classified**; `reference_assembly` is `not_applicable` (raw, unaligned reads). A WGS and an RNA-seq Illumina FASTQ **carry no reliable in-file marker of which they are** — the read names/format encode only the instrument (platform), and while sequence composition differs statistically, there is no dependable content signal a classifier can key on. The library type is recorded in the submission's library metadata, not the reads.
- **BED (11,523 files):** `data_modality`/`data_type` 100%, `reference_assembly` 65.6% classified / 34.0% not_applicable (de-novo assemblies) / 0.3% not_classified; `assay_type` and `platform` ~38% not_classified. BED reference is only recoverable when the file spans whole chromosomes (coverage files reach a reference's exact chromosome length); sparse files are genuinely ambiguous.
- **BED reference method:** the current coordinate-*elimination* is a lower-bound method (rules out too-short references, never positively confirms). A length-*matching* prototype **agrees with it on 100% of calls (0 disagreements)** on this corpus — but matching is the *sound* formulation and handles the edge cases (hybrids, sparse, read-depth) elimination gets wrong (#298).

**Conclusion from the data:** the hardest dimensions — FASTQ modality/assay, BED reference — are **declared in the submission but invisible in the content**. No engine (rules or LLM) can extract information that is not in the bytes.

## Structural context: why the metadata is missing (AnVIL/Azul vs UCSC)

The hole is a consequence of *how the two ecosystems are organized*, not an accident:

- **UCSC is reference-centric.** The assembly is the spine — every track hangs off a declared genome (`genomes.txt`); you cannot have a track without stating its assembly. Hierarchy: Hub → Assembly → Group → Track(`type`) → subtracks.
- **AnVIL (Terra/Gen3/Azul) is subject/study-centric.** The spine is dataset → donor/biosample → file, with a producing `activity`. The reference assembly is merely an optional *field* on a file — so it is routinely absent (measured: 13,658/13,660 BED blank). AnVIL's structure never *forces* what UCSC's structure *requires*.

They line up via UCSC's assembly-hub (GenArk) model:

| UCSC | AnVIL/Azul analog |
| --- | --- |
| Hub | dataset (e.g. ANVIL_HPRC) |
| Assembly (genome/`db`) | a standard reference **or** a per-sample de-novo assembly (its own genome) |
| Track (typed file on an assembly) | file |
| `type` (bed / vcfTabix / bigWig / bam) | `file_format` |
| `group` (Variation / Expression / Repeats…) | `data_modality` + `data_type` (+ producing `activity`) |
| subtrack per sample | donor / biosample |
| `bigDataUrl` | `drs_uri` / S3 location |
| `trackDb` (the declaration) | the catalog / Azul index (often *lacking* the declaration) |

So `reference_assembly` is really "which UCSC genome — a standard reference, or `not_applicable` because the file is on a sample-specific assembly." (That is the 34% not_applicable BEDs: per-sample de-novo assembly products.)

**Two domains, two metadata homes.** The file types split, and their declarations live in different systems:

| domain | types | metadata home | content self-describes? |
| --- | --- | --- | --- |
| aligned / reference-anchored | BAM, VCF, BED, bigWig | UCSC `trackDb` + the file header (VCF `##contig`, BAM `@SQ`) | often **yes** |
| raw reads | FASTQ | SRA / ENA / study `library_strategy` | **no** (only platform, from read names) |

UCSC does **not** hold FASTQ (no coordinates → not a track), which is why the browser cannot supply FASTQ modality — that lives in the sequencing-archive world. meta-disco spans **both** domains, so its import strategy needs **both** kinds of source (see Decision 3).

## Decision

1. **The deterministic tiered rule engine remains the runtime backbone.** It is auditable (every call cites its rule/evidence), reproducible (stable across runs and model versions), cheap at 380K+ scale, and cannot hallucinate — all essential for a data repository whose output is citable metadata, and consistent with the standing principles *accuracy over coverage* and *no speculation as fact*.

2. **The LLM's role is at *authoring* time, not runtime.** Its muscle is turning diverse, novel inputs into **durable, auditable artifacts** that the deterministic engine then executes:
   - **classification rules** (the current "AI-generated rules" — the insight that motivated meta-disco), and
   - **import mappings** from heterogeneous source catalogs into the meta-disco model (each source schema is a novel mapping task — exactly LLM-suited).
   LLM flexibility is spent **once**, at authoring; determinism holds **forever**, at runtime.

3. **Import is the primary source of truth wherever a declaration survives (#302).** The dimensions content cannot reveal are precisely the ones the source *declared*:
   - HPRC Data Explorer: `annotationType` (→ data_type / producing method) and `library_strategy` (→ assay/modality — the FASTQ gap).
   - UCSC / GenArk track hubs: `trackDb` tags the T2T-CHM13 annotation tracks (CenSat, RepeatMasker, SegDups) — the same files that arrive untagged as `.bed` in AnVIL.
   - Catalog path / `release` (→ reference), sibling `.dict`/`.fai`/`.genome`, source metadata, MAGE, etc.
   - **SRA / ENA / study `library_strategy` + `library_source`** for the **raw-read** domain — the only home for FASTQ modality/assay (per the two-domain split above). UCSC covers the aligned domain; it never holds FASTQ.
   **Precedence:** imported declaration > content inference > filename guess. Every field carries provenance; import-vs-inference conflicts are surfaced, not silently resolved.
   **Scope is finite and known (#304):** AnVIL is **78 distinct phs studies** (Azul `/index/datasets`), of which **13 are open-access** (`accessible: true`) — the rest are controlled/dbGaP-gated and need authenticated access before their files are reachable. The immediate, actionable scope is those **13 open datasets over ~8 source systems**; ~87% of their files sit in datasets with strong external catalogs (T2T ≈ 82%, plus 1000G, GTEx, HPRC), while ~4% (NIA_CARD/Coriell, MAGE, nhp_dGTEx, ENCORE specifics) have no queryable catalog and stay partly inferred / honestly `not_classified`. AnVIL's own dataset record is the first authoritative anchor (phs → dbGaP, DUOS, coarse dataset-level `data_modality`), from which the import follows the pointer out to the consortium portal or dbGaP study.

4. **A runtime LLM, if used at all, is a bounded fallback for the residual long tail.** It must **decline on ambiguity** (no fabricated confidence — the #56 removal stands), emit outputs labeled `llm-inferred` as **low-precedence hints**, and its best runtime job is to **triage novel clusters for rule/mapping authoring** — never to stamp authoritative metadata.

5. **Get ahead of ingestion (#303).** Capture/import metadata while the source system is still live, serving purpose (1) — not only backfilling purpose (2).

## Consequences

**Positive**
- Reproducible, auditable, scalable classification the repository can stand behind.
- Import raises the content-inference ceiling exactly where it is lowest (FASTQ modality/assay, BED reference) by supplying declared-but-invisible dimensions.
- The LLM's flexibility is captured as durable rules/mappings rather than ephemeral per-file guesses.

**Negative / cost**
- The rule engine only covers what has been authored; the long tail needs ongoing rule/mapping work.
- Import requires per-dataset source access, joins, and mapping maintenance (schemas drift — cf. catalog versioning #270).
- The **truly orphaned** long tail (no surviving declaration, thin content) stays partially unclassifiable. That is honest (accuracy over coverage), not a defect.
- **The inference engine has a hard ceiling per type; import is not optional for full coverage.**

## Alternatives considered

- **Runtime LLM as the primary classifier (the original Ollama path).** Rejected: hallucination conflicts with *no speculation as fact* / *accuracy over coverage*; non-reproducible output undermines citable repository metadata; costly at 380K+ scale; and — decisively — it **cannot extract information absent from the bytes** (FASTQ modality, sparse-BED reference), so it does not overcome the ceiling. Its genuine value is at authoring/triage, captured in Decision 2 & 4.
- **Rules only, no import.** Rejected: leaves the declared-but-invisible dimensions permanently blank (FASTQ `data_modality`/`assay_type` ~100% not_classified). Content inference alone cannot fill them; a surviving source declaration can.

## Revisit when

- Content-derivable signal materially improves (e.g. a reliable content method to separate WGS from RNA-seq FASTQ), or
- Runtime-LLM economics/reproducibility change enough that a bounded fallback earns its keep beyond triage, or
- Import coverage plateaus and the orphaned long tail becomes the dominant cost.
