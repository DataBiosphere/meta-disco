"""File type configurations for the classification pipeline.

Each config defines extensions, fetcher, classifier, and summary printer
for one file type. These are used by ClassifyPipeline and the unified
classify_headers.py script.
"""

from .fetchers import (
    fetch_bam_header,
    fetch_fasta_headers,
    fetch_fastq_reads,
    fetch_gfa_segment_tags,
    fetch_vcf_header,
    require_samtools,
)
from .header_classifier import (
    BAM_EXTENSIONS,
    FASTA_EXTENSIONS,
    FASTQ_EXTENSIONS,
    GRAPH_TEXT_EXTENSIONS,
    VCF_EXTENSIONS,
    classify_from_fasta_header,
    classify_from_fastq_header,
    classify_from_gfa_segment_tags,
    classify_from_header,
    classify_from_vcf_header,
)
from .pipeline import FileTypeConfig
from .summaries import print_bam_summary, print_fastq_summary, print_vcf_summary

BAM_CONFIG = FileTypeConfig(
    name="bam",
    extensions=BAM_EXTENSIONS,
    fetcher=fetch_bam_header,
    classifier=classify_from_header,
    summary_printer=print_bam_summary,
    # @SQ contig lengths, @RG platform; assay_type is inferred from those.
    content_fields=("data_modality", "data_type", "reference_assembly", "platform", "assay_type"),
    # samtools reads BAM/CRAM headers — fail fast if it is not installed.
    preflight=require_samtools,
)

VCF_CONFIG = FileTypeConfig(
    name="vcf",
    extensions=VCF_EXTENSIONS,
    fetcher=fetch_vcf_header,
    classifier=classify_from_vcf_header,
    summary_printer=print_vcf_summary,
    # ##contig lengths and header tokens; the VCF header names no platform.
    content_fields=("data_modality", "data_type", "reference_assembly"),
)

FASTQ_CONFIG = FileTypeConfig(
    name="fastq",
    extensions=FASTQ_EXTENSIONS,
    fetcher=fetch_fastq_reads,
    classifier=classify_from_fastq_header,
    # Read names give the instrument, hence platform; reads name no assembly.
    content_fields=("data_modality", "platform", "assay_type"),
    summary_printer=print_fastq_summary,
)

FASTA_CONFIG = FileTypeConfig(
    name="fasta",
    extensions=FASTA_EXTENSIONS,
    fetcher=fetch_fasta_headers,
    classifier=classify_from_fasta_header,
    # Contig names distinguish reference / assembly / transcriptome.
    content_fields=("data_modality", "data_type", "reference_assembly"),
)

# Text GFA only (GRAPH_TEXT_EXTENSIONS). The other graph extensions the
# `pangenome` rules cover (.gbz, .vg, .gbwt, .xg) are binary vg/GBWT formats
# that this fetcher cannot parse; they classify from extension and filename alone.
GFA_CONFIG = FileTypeConfig(
    name="gfa",
    extensions=GRAPH_TEXT_EXTENSIONS,
    fetcher=fetch_gfa_segment_tags,
    classifier=classify_from_gfa_segment_tags,
    # rGFA stable-rank tags refine data_type to pangenome.reference. Nothing
    # else: reference_assembly comes only from the filename (no lengths are
    # parsed, and the visible stable name `chr1` is shared across assemblies).
    content_fields=("data_type",),
)

FILE_TYPE_REGISTRY = {
    "bam": BAM_CONFIG,
    "vcf": VCF_CONFIG,
    "fastq": FASTQ_CONFIG,
    "fasta": FASTA_CONFIG,
    "gfa": GFA_CONFIG,
}
