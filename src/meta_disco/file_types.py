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


# --- Classifier adapters ---
# Each classifier has a different signature; these normalize to
# (raw_data, file_name=, file_size=, file_format=, **kw)

def _classify_bam(raw_data, file_name="", file_size=None, file_format=None, **kw):
    return classify_from_header(raw_data, file_size=file_size, file_format=file_format)


def _classify_vcf(raw_data, file_name="", file_size=None, file_format=None, **kw):
    return classify_from_vcf_header(raw_data, file_size=file_size, file_format=file_format)


def _classify_fastq(raw_data, file_name="", file_size=None, file_format=None, **kw):
    return classify_from_fastq_header(raw_data, file_name)


def _classify_fasta(raw_data, file_name="", file_size=None, file_format=None, **kw):
    return classify_from_fasta_header(raw_data, file_name)


# --- Config singletons ---

BAM_CONFIG = FileTypeConfig(
    name="bam",
    extensions=(".bam", ".cram"),
    evidence_subdir="bam",
    default_output="bam_classifications.json",
    default_workers=4,
    fetcher=fetch_bam_header,
    classifier=_classify_bam,

    summary_printer=print_bam_summary,
    detect_gzip=False,
)

VCF_CONFIG = FileTypeConfig(
    name="vcf",
    extensions=(".vcf", ".vcf.gz", ".g.vcf.gz", ".gvcf.gz"),
    evidence_subdir="vcf",
    default_output="vcf_classifications.json",
    default_workers=10,
    fetcher=fetch_vcf_header,
    classifier=_classify_vcf,

    summary_printer=print_vcf_summary,
    detect_gzip=True,
)

FASTQ_CONFIG = FileTypeConfig(
    name="fastq",
    extensions=(".fastq", ".fastq.gz", ".fq", ".fq.gz"),
    evidence_subdir="fastq",
    default_output="fastq_classifications.json",
    default_workers=10,
    fetcher=fetch_fastq_reads,
    classifier=_classify_fastq,

    summary_printer=print_fastq_summary,
    detect_gzip=True,
)

FASTA_CONFIG = FileTypeConfig(
    name="fasta",
    extensions=(".fasta", ".fasta.gz", ".fa", ".fa.gz"),
    evidence_subdir="fasta",
    default_output="fasta_classifications.json",
    default_workers=10,
    fetcher=fetch_fasta_headers,
    classifier=_classify_fasta,

    summary_printer=None,
    detect_gzip=True,
)

FILE_TYPE_REGISTRY = {
    "bam": BAM_CONFIG,
    "vcf": VCF_CONFIG,
    "fastq": FASTQ_CONFIG,
    "fasta": FASTA_CONFIG,
}
