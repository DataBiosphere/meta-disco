"""File type configurations for the classification pipeline.

Each config defines extensions, fetcher, classifier, and summary printer
for one file type. These are used by ClassifyPipeline and the unified
classify_headers.py script.
"""

from .fetchers import fetch_bam_header, fetch_fasta_headers, fetch_fastq_reads, fetch_vcf_header
from .header_classifier import (
    classify_from_fasta_header,
    classify_from_fastq_header,
    classify_from_header,
    classify_from_vcf_header,
)
from .pipeline import FileTypeConfig
from .summaries import print_bam_summary, print_fastq_summary, print_vcf_summary

BAM_CONFIG = FileTypeConfig(
    name="bam",
    extensions=(".bam", ".cram"),
    fetcher=fetch_bam_header,
    classifier=classify_from_header,
    summary_printer=print_bam_summary,
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

FILE_TYPE_REGISTRY = {
    "bam": BAM_CONFIG,
    "vcf": VCF_CONFIG,
    "fastq": FASTQ_CONFIG,
    "fasta": FASTA_CONFIG,
}
