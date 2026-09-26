# Self-Consistency Report

Run: **output/anvil/20260926_120321** — 708,088 records, 8 rules  
**Total violations: 0**

Cross-field invariants over classified records (#314). *Active* is how many records a rule tested; a rule with 0 active is **vacuous** (no matching data in this run), not verified-clean.

| Violations | Active | Rule |
|---:|---:|---|
| 0 | 7,407 | `assay_for_transcriptomic` |
| 0 | 553,024 | `assay_for_genomic` |
| 0 | 0 | `assay_for_chromatin_accessibility` _(vacuous)_ |
| 0 | 0 | `assay_for_histone_modification` _(vacuous)_ |
| 0 | 188 | `assay_for_methylation` |
| 0 | 0 | `imaging_exclusive` _(vacuous)_ |
| 0 | 57,230 | `sequencing_platform_excludes_histology` |
| 0 | 17,870 | `auxiliary_inert` |

## Examples

_No violations._
