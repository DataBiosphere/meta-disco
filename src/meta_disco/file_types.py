"""File type configurations for the classification pipeline.

Each config defines extensions, fetcher, classifier, and summary printer
for one file type. These are used by ClassifyPipeline and the unified
classify_headers.py script.
"""

from .fetchers import (
    fetch_bam_header,
    fetch_bed_signals,
    fetch_fasta_headers,
    fetch_fastq_reads,
    fetch_gfa_segment_tags,
    fetch_tar_headers,
    fetch_vcf_header,
    require_samtools,
)
from .header_classifier import (
    GRAPH_TEXT_EXTENSIONS,
    classify_from_bed_signals,
    classify_from_fasta_header,
    classify_from_fastq_header,
    classify_from_gfa_segment_tags,
    classify_from_header,
    classify_from_tar_members,
    classify_from_vcf_header,
    tar_head_is_conclusive,
)
from .pipeline import FileTypeConfig
from .summaries import print_bam_summary, print_fastq_summary, print_vcf_summary

BAM_CONFIG = FileTypeConfig(
    name="bam",
    extensions=(".bam", ".cram"),
    fetcher=fetch_bam_header,
    classifier=classify_from_header,
    summary_printer=print_bam_summary,
    # samtools reads BAM/CRAM headers — fail fast if it is not installed.
    preflight=require_samtools,
)

VCF_CONFIG = FileTypeConfig(
    name="vcf",
    extensions=(".vcf", ".vcf.gz", ".g.vcf.gz", ".gvcf.gz"),
    fetcher=fetch_vcf_header,
    classifier=classify_from_vcf_header,
    summary_printer=print_vcf_summary,
)

FASTQ_CONFIG = FileTypeConfig(
    name="fastq",
    extensions=(".fastq", ".fastq.gz", ".fq", ".fq.gz"),
    fetcher=fetch_fastq_reads,
    classifier=classify_from_fastq_header,
    summary_printer=print_fastq_summary,
)

FASTA_CONFIG = FileTypeConfig(
    name="fasta",
    extensions=(".fasta", ".fasta.gz", ".fa", ".fa.gz"),
    fetcher=fetch_fasta_headers,
    classifier=classify_from_fasta_header,
)

# Text GFA only (GRAPH_TEXT_EXTENSIONS). The other graph extensions the
# `pangenome` rules cover (.gbz, .vg, .gbwt, .xg) are binary vg/GBWT formats
# that this fetcher cannot parse; they classify from extension and filename alone.
GFA_CONFIG = FileTypeConfig(
    name="gfa",
    extensions=GRAPH_TEXT_EXTENSIONS,
    fetcher=fetch_gfa_segment_tags,
    classifier=classify_from_gfa_segment_tags,
)

# Tar archives (#255). A container carries no format of its own (#245); the head
# is read and the archive is classified from its dominant recognized *inner* member
# format. .zip (a trailing central directory, only 2 corpus files) is not handled.
TAR_CONFIG = FileTypeConfig(
    name="tar",
    extensions=(".tar", ".tar.gz"),
    fetcher=fetch_tar_headers,
    classifier=classify_from_tar_members,
    # Escalating head-read (#260): read deeper only until the members are classifiable,
    # so a GenomicsDB store whose variant signal sits past the first 256KiB is reached.
    head_detector=tar_head_is_conclusive,
)

# BED reference is inferred from coordinate content (chromosome names + per-contig max
# end positions), so it is a header/content type read through the shared pipeline (#282) —
# not a hand-rolled orphan fetcher. reference_assembly is content-derived; data_modality/
# data_type come from the filename/extension rules; platform and assay_type carry no BED signal.
BED_CONFIG = FileTypeConfig(
    name="bed",
    extensions=(".bed", ".bed.gz"),
    fetcher=fetch_bed_signals,
    classifier=classify_from_bed_signals,
)

FILE_TYPE_REGISTRY = {
    "bam": BAM_CONFIG,
    "vcf": VCF_CONFIG,
    "fastq": FASTQ_CONFIG,
    "fasta": FASTA_CONFIG,
    "gfa": GFA_CONFIG,
    "tar": TAR_CONFIG,
    "bed": BED_CONFIG,
}
