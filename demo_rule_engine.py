#!/usr/bin/env python3
"""Demo script showing rule engine classification."""

from src.meta_disco import RuleEngine, FileInfo

engine = RuleEngine("rules/classification_rules.yaml")

# Sample filenames to classify
test_files = [
    # Alignment files
    ("m64043_210211_005516.hifi_reads.bam", None),
    ("sample_RNA_aligned.hg38.bam", None),
    ("sample.Aligned.sortedByCoord.out.bam", None),
    ("HG002.wgs.grch38.cram", 80_000_000_000),

    # Variant files
    ("NA19189.chr2.hc.vcf.gz", None),
    ("sample.hg19.vcf", None),

    # Skip files
    ("HG02558.final.cram.md5", None),
    ("sample.bam.bai", None),

    # Special types
    ("GTEX-18A6Q-1126.svs", None),
    ("sample.h5ad", None),
    ("sample_atac.h5ad", None),
    ("sample.idat", None),

    # Ambiguous
    ("sample.fastq.gz", None),
    ("data.txt", None),
]

print("=" * 80)
print("Rule Engine Classification Demo")
print("=" * 80)

for filename, size in test_files:
    file_info = FileInfo(filename=filename, file_size=size)
    result = engine.classify(file_info)

    print(f"\n📄 {filename}")
    if size:
        print(f"   Size: {size:,} bytes")

    if result.skip:
        print(f"   ⏭️  SKIP - {result.reasons[0] if result.reasons else 'No reason'}")
    else:
        print(f"   Modality:  {result.data_modality or '❓ Unknown'}")
        print(f"   Reference: {result.reference_assembly or '❓ Unknown'}")
        print(f"   Confidence: {result.confidence:.0%}")

        if result.needs_header_inspection:
            print("   ⚠️  Needs header inspection")
        if result.needs_study_context:
            print("   ⚠️  Needs study context")
        if result.needs_manual_review:
            print("   ⚠️  Needs manual review")

    if result.reasons:
        print(f"   Reasons:")
        for reason in result.reasons:
            print(f"     • {reason}")

print("\n" + "=" * 80)
