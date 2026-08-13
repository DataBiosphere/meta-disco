# Self-Consistency Report

Run: **output/anvil/20260802_170826** — 733,992 records, 8 rules  
**Total violations: 0**

Cross-field invariants over classified records (#314). *Active* is how many records a rule tested; a rule with 0 active is **vacuous** (no matching data in this run), not verified-clean.

| Violations | Active | Rule |
|---:|---:|---|
| 0 | 5,173 | `assay_for_transcriptomic` |
| 0 | 586,752 | `assay_for_genomic` |
| 0 | 0 | `assay_for_chromatin_accessibility` _(vacuous)_ |
| 0 | 0 | `assay_for_histone_modification` _(vacuous)_ |
| 0 | 188 | `assay_for_methylation` |
| 0 | 25,708 | `imaging_exclusive` |
| 0 | 57,973 | `platform_implies_sequencing_modality` |
| 0 | 0 | `auxiliary_inert` _(vacuous)_ |

## Examples

_No violations._
