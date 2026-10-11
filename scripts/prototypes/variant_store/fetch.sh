#!/usr/bin/env bash
# Fetch the inputs of the variant-store measurement (#663) into the work directory:
# the chr22 1000 Genomes panel VCF from the AnVIL S3 mirror (by md5, checked), its
# tabix index (built here), and the 1000 Genomes pedigree from EBI.
set -euo pipefail

WORK="${VARIANT_STORE_DIR:-data/prototypes/variant_store}"
MD5=a2653cc7a1c8d03a96ca4f14d0fabdd2
VCF="$WORK/chr22.panel.vcf.gz"
PED_URL=https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/20130606_g1k_3202_samples_ped_population.txt

mkdir -p "$WORK"
if [ ! -s "$VCF" ]; then
    curl -fsS -o "$VCF.part" "https://anvilproject.s3.amazonaws.com/file/$MD5.md5"
    mv "$VCF.part" "$VCF"
fi
got=$(md5 -q "$VCF" 2>/dev/null || md5sum "$VCF" | cut -d' ' -f1)
[ "$got" = "$MD5" ] || { rm -f "$VCF"; echo "md5 mismatch: $got != $MD5 (removed; rerun to download again)" >&2; exit 1; }
[ -s "$VCF.tbi" ] || bcftools index -t "$VCF"
if [ ! -s "$WORK/pedigree.txt" ]; then
    curl -fsS -o "$WORK/pedigree.txt.part" "$PED_URL"
    mv "$WORK/pedigree.txt.part" "$WORK/pedigree.txt"
fi
echo "inputs ready in $WORK"
