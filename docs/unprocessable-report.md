# Unprocessable files

What run `output/anvil/20260904_010319` could not classify, and why (#376).

## Summary

| reason | files | row elsewhere? |
|---|---:|---|
| No usable checksum (excluded) | 0 | no — excluded |
| Input-contract violation | 0 | yes |
| Content unreadable | 23 | yes |
| **Total** | **23** | |

Read from 708,203 classification record(s) in the run.

## By reason

### No usable checksum (excluded)

The record carries no well-formed `file_md5sum`, so it can be neither fetched (the content URL is built from the md5) nor cached (the evidence cache is keyed by md5). It is excluded from classification rather than written as a row with no usable identity.

**No row exists anywhere else** — this listing is the only record of these files.

This run predates the exclusion (#376) and wrote no `excluded_files.json`, so whether it shed any checksum-less file is unknown. Re-run to find out.

### Input-contract violation

The record violates the input contract on a field the classifier reads (`file_size`, `file_format`, `file_name`), so it is never fetched. Its provenance is untrusted wholesale, so every dimension is marked `not_classified`.

A row exists in the run's output, with the violation as each dimension's evidence.

None in this run (708,203 classification records read).

### Content unreadable

The record passed the contract, but its content could not be read — a 404 from the mirror, a DNS or connection failure, a timeout. Nothing is asserted about a file we could not read, not even what the filename alone would support.

A row exists in the run's output, with the fetch failure as each dimension's evidence.

**23 file(s)** across 1 dataset(s), counted per dataset with up to 5 example(s) each.

| dataset | files | examples |
|---|---:|---|
| ANVIL_T2T | 23 | `20201028_CCDG_14151_B01_GRM_WGS_2020-08-05_chr1.recalibrated_variants_GRCh38p13_unique_75mer_coverage.vcf.gz`, `20201028_CCDG_14151_B01_GRM_WGS_2020-08-05_chr16.recalibrated_variants_GRCh38p13_unique_75mer_coverage.vcf.gz`, `20201028_CCDG_14151_B01_GRM_WGS_2020-08-05_chr4.recalibrated_variants_GRCh38p13_unique_75mer_coverage.vcf.gz`, `20201028_CCDG_14151_B01_GRM_WGS_2020-08-05_chr8.recalibrated_variants_GRCh38p13_unique_75mer_coverage.vcf.gz`, `20201028_CCDG_14151_B01_GRM_WGS_2020-08-05_chr10.recalibrated_variants_GRCh38p13_unique_75mer_coverage.vcf.gz` … (+18 more) |
