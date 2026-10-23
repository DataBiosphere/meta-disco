# Who ANVIL_T2T_CHRY's SGDP genomes are

**Status:** Findings, measured 2026-10-20 (#559) and 2026-10-22 (#718), against catalog `anvil15`.
**Scope:** the 279 Simons Genome Diversity Project (SGDP) genomes ANVIL_T2T_CHRY aligned and called, and how
meta-disco links each to a donor.

ANVIL_T2T_CHRY holds no donor for these genomes. A file reaches one through three links, and the second rests
on one table. This note records what each link rests on, the two checks that confirm the second, what they
found for the four genomes the first check could not settle, and how to measure it again.

---

## 1. The chain from a file to a person

| Link | Example | Stated by |
|---|---|---|
| 1. file → sample | `simons_data_sample_187` | the file's own content: the gVCF's sample column, and the submitter table's row |
| 2. sample → SGDP genome | `S_Palestinian-2` | ANVIL_T2T_CHRY's `SGDP_GRCh38_sample` and `SGDP_CHM13v2_sample` tables, and nothing else |
| 3. SGDP genome → person | `HGDP00725`, male | SGDP's metadata file (Reich lab; Mallick et al., *Nature* 2016) |

**Link 2 rests on one table.** Sample 187's chr22 gVCF names only its own identifier:

```
sample column:  simons_data_sample_187
command line:   HaplotypeCaller --input inputs/simons_data_sample_187.cram
```

Neither `S_Palestinian-2`, `HGDP00725` nor SGDP's sequencing identifier (`LP6005441-DNA_G09`) appears in the
header. ANVIL_T2T_CHRY named each SGDP genome `simons_data_sample_N` before it made its CRAMs; where in its
processing is not stated. Both tables agree on all 279 pairings, but agreeing copies of one table are one
source. So meta-disco writes link 2 only where a check confirms it (contract 2.10).

## 2. What ANVIL_T2T_CHRY holds about these people

There is no `anvil_donor` or `anvil_biosample` table for this dataset. Each genome has one row per reference
build; besides its files, sample 187's says:

| Column | ANVIL_T2T_CHRY | SGDP's metadata file |
|---|---|---|
| `sgdp_id` | `S_Palestinian-2` | `SGDP_ID`: `S_Palestinian-2` |
| `panel`, `population_id`, `region`, `country` | `C`, `Palestinian`, `WestEurasia`, `Israel(Central)` | the same, word for word |
| `karyotype` | `XX` | — |
| — | — | `Gender`: `M`; `Sample_ID`: `HGDP00725`; `DNA_Source`: `Genomic_from_cell_lines` |

The four copied columns suggest the table was built from SGDP's file; `Gender` was not copied, and
`karyotype` is not SGDP's. **`karyotype` is an input to the T2T pipeline, not a result of it**: each sample was
aligned to an XX reference (chrY masked) or an XY one (Y-PARs masked), made with XYalign, and its chrX called
diploid (XX) or haploid outside the PARs (XY). Neither the paper (Rhie et al., *Nature* 2023, and its bioRxiv
supplement), nor its workflow repository (`schatzlab/t2t-chm13-chry`: README, WDLs, SGDP notebook), nor the
workspace description says how each SGDP sample's karyotype was set.

## 3. The two checks

Both are declared in `code_rules.IDENTITY_CHECKS`, and `sgdp_entities` records which confirmed each sample in
the generation's `outcomes.json`.

**`sgdp_sex_agrees`** (#559): SGDP's `Gender` is the table's `karyotype` (M with XY, F with XX). A mislabelled
row would agree about half the time. 275 of 279 samples agree; against whether the sample has a chrY gVCF,
all 279:

| SGDP `Gender` | chrY gVCF | Genomes |
|---|---|---:|
| M | yes | 174 |
| F | no | 101 |
| U | no | 2 (`S_Norwegian-1`, `B_Australian-3`) |
| M | no | 1 (`S_Palestinian-2`) |
| not in SGDP's file | yes | 1 (`S_Naxi-2`) |

The check cannot tell two men, or two women, apart.

**`sgdp_genotype_matches`** (#718): the sample's genotypes match the paired genome's in a public release.
Recorded in `src/meta_disco/sources/sgdp_genotype_checks.yaml`, which the importer reads; it is a measurement,
not a source, and adds no value to any record. Two runs of it:

- **2026-10-20, the 23 SGDP genomes whose `Sample_ID` is a 1000 Genomes person in ANVIL_T2T_CHRY** (#559,
  [comment](https://github.com/DataBiosphere/meta-disco/issues/559#issuecomment-6298019406)): each SGDP chr22
  gVCF against that person's own, both CHM13v2, chr22:25–30 Mb. All 23 are the same person (sites shared
  0.84–0.88, genotype match 98.3–98.8%; the next pair's person, 0.26–0.44 and 52–67%), including pairs from one
  population. These all passed the sex check too, so the record does not list them.
- **2026-10-22, the four the sex check could not settle, and five it did, as controls** (#718): each sample's
  GRCh38 chr22 gVCF against every genome of two public releases, below.

## 4. The genotype search (2026-10-22)

**References.**
- HGDP's high-coverage release (Bergström et al., *Science* 2020), GRCh38 joint calls, 929 genomes:
  `https://ngs.sanger.ac.uk/production/hgdp/hgdp_wgs.20190516/hgdp_wgs.20190516.full.chr22.vcf.gz`.
- SGDP's phased release (2021), 278 genomes, GRCh37 (contig `22`), imputed against 1000 Genomes phase 3:
  `https://sharehost.hms.harvard.edu/genetics/reich_lab/sgdp/phased_data2021/chr.sgdp.pub.22.bcf`.
  Positions lifted to GRCh38 with UCSC's `hg19ToHg38.over.chain.gz` (ungapped blocks, + strand).

**Method.**
- Window: chr22:25,000,000–26,000,000 (GRCh38); each reference's biallelic SNPs, read with
  `bcftools view -r … -v snps -m2 -M2` (HGDP 25,920 sites; SGDP 30,821 in the window after lifting).
- The sample's genotype at each reference site is its gVCF call's where the call's ALT is the site's, 0/0 where a
  reference block covers the site, missing otherwise, written as a plain one-sample VCF of the reference's sites
  with the reference's contig lines. `gtcheck` cannot take the gVCF itself: it compares a site only where position
  and ALT match, and the gVCF's ALTs carry `<NON_REF>`. The gVCFs are read in place from AnVIL's public S3 mirror
  (`https://anvilproject.s3.amazonaws.com/file/<md5>.md5`), the index likewise.
- `bcftools gtcheck -u GT,GT -E 0 -g <reference> <sample>` counts, per reference genome, the **mismatches** among
  the sites where both genotypes are known. Genomes are ranked by the share of sites that mismatch.

**Controls.** Five samples the sex check confirmed, from the four genomes' populations (`B_Australian-4` is not in
HGDP). Mismatches of sites compared:

| Sample | Paired with | HGDP | SGDP | Best other genome |
|---|---|---|---|---|
| `simons_data_sample_209` | `S_Palestinian-1` (HGDP00722) | 0 / 25,445 | 48 / 30,787 | 3.3% |
| `simons_data_sample_166` | `S_Palestinian-3` (HGDP00737) | 0 / 25,475 | 44 / 30,783 | 3.3% |
| `simons_data_sample_171` | `S_Naxi-1` (HGDP01338) | 1 / 25,517 | 53 / 30,792 | 2.7% |
| `simons_data_sample_185` | `S_Naxi-3` (HGDP01345) | 0 / 25,440 | 48 / 30,780 | 3.7% |
| `simons_data_sample_116` | `B_Australian-4` | — | 33 / 30,766 | 2.0% |

The same person differs at 0–1 sites of HGDP's calls and 33–53 of SGDP's (its genotypes are imputed, so a few
differ); every other genome at 1.98% of sites or more, about 600 or more.

**The four.**

| Sample | Paired with | Best match | Best other genome | Verdict |
|---|---|---|---|---|
| `simons_data_sample_187` | `S_Palestinian-2` | HGDP00725 0 / 25,536; S_Palestinian-2 48 / 30,788 | 3.3% | the pairing holds |
| `simons_data_sample_304` | `S_Norwegian-1` | S_Norwegian-1 40 / 30,799 (not in HGDP) | 2.7% | the pairing holds |
| `simons_data_sample_33` | `B_Australian-3` | B_Australian-3 60 / 30,756 (not in HGDP) | 2.9% | the pairing holds |
| `simons_data_sample_273` | `S_Naxi-2` | none: S_Naxi-3 806 / 30,783 (2.6%) | — | no match |

A first pass the same day, scoring allele-dosage concordance over the same sites with a script of mine, gave the
same verdict for all nine (the same person 0.963–1.000, any other genome at most 0.62).

## 5. Each of the four

**`S_Palestinian-2` — linked, on genotype; the karyotype looks wrong.** The genotypes put sample 187 and
HGDP00725 as one person. The sexes disagree, and the content sides with SGDP's `M`:

- ANVIL_T2T_CHRY's own chrX gVCF for sample 187, called diploid, holds few heterozygous calls: on chrX
  40–42 Mb, 155 heterozygous against 921 homozygous-alternate. The female control (sample 166) holds 1,394
  against 420. One X.
- HGDP's calls for HGDP00725 on chrX 20.0–20.3 Mb: 0 heterozygous, as the male control (HGDP00722) has 0 and
  the female (HGDP00737) 16.
- HGDP's metadata gives `M` too, but its library is SGDP's (`source: sgdp`), so it is likely SGDP's label
  carried over, not a second call. HGDP's chrY callset omits HGDP00725, one of 2 of its 612 males omitted.

So the genome has one X, and `XX` is the odd one out. I think it may be a male cell line that lost its Y,
which would leave no chrY reads for a karyotype call to find; that is not checked. Linked as #559 links the
others: donor `hgdp:HGDP00725`, `phenotypic_sex` from SGDP (`M`). The karyotype is not imported as a sex, so
nothing on the donor record conflicts; the outcome records the sex check as `contradicts`.

**`S_Norwegian-1`, `B_Australian-3` — linked, on genotype.** SGDP gives their sex as `U`, so the sex check
has nothing to compare. Each matches its SGDP genome. Their donors carry no sex.

**`S_Naxi-2` — left out.** SGDP's metadata file has `S_Naxi-1` and `S_Naxi-3` but not `S_Naxi-2`, neither
release holds it, and sample 273 matches no genome of either: its best, `S_Naxi-3`, differs at 2.6% of sites, the
range of other genomes of a population. I think that is shared ancestry and not a relative, but a mismatch count
does not measure relatedness; that is not checked. There is no person to link it to. Its 118 single-sample
files, and every multi-sample file naming it (the joint-called files and the SGDP workspace tars), reach no
donor for it; reconcile's `entities.donor_reach` counts them and `entities.samples.no_donor` lists it with its
checks. Not tried: SGDP's paper's supplementary tables.

## 6. Measuring it again

A sample is added to `sgdp_genotype_checks.yaml` by hand, from a run of the method above. The importer refuses an
entry whose `sgdp_id` is not the pairing the tables state today, so a changed table means measuring again; and it
refuses the record on another catalog than the one it names, until a person confirms it still holds there.
The 2026-10-22 run's scripts are not in the repository (#738 would add a re-runnable target). Its steps:

1. the HGDP window, all genomes (7 minutes over HTTP; 121 MB as BCF):
   `bcftools view -r chr22:25000000-26000000 -v snps -m2 -M2 -Ob -o hgdp.bcf <HGDP URL>`;
2. the SGDP window in GRCh37 coordinates covering the GRCh38 window:
   `bcftools view -r 22:25390000-26400000 -v snps -m2 -M2 -Ob -o sgdp.bcf <SGDP URL>`;
3. SGDP's genotypes, lifted to GRCh38 positions with the chain and kept within the window, written as a GRCh38 VCF;
4. each sample's gVCF records over the window:
   `bcftools query -r chr22:25000000-26000000 -f '%POS\t%END\t%REF\t%ALT\t[%GT]\n' '<gVCF URL>##idx##<index URL>'`,
   the gVCF at `SGDP_GRCh38/haplotype_calling_vcfs/chr22/<sample>.chr22.hc.vcf.gz` (its `file_path`), written as
   its genotypes at each reference's sites (Method, above);
5. per reference, `bcftools gtcheck -u GT,GT -E 0 -g <reference>.bcf <sample>.bcf`.
