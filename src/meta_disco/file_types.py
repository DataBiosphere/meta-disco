"""File type configurations for the classification pipeline.

Each config defines extensions, fetcher, classifier, and summary printer for one file
type. They are used by ClassifyPipeline and classify_headers.py, and are the eight header
entries in the producer registry (``producers``).

``FileTypeConfig`` is declared here rather than in ``pipeline`` so that ``pipeline`` can
import the registry to route a record, without the registry — which holds these configs —
importing ``pipeline`` back.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from .cohort_steps import SAMPLE_MAP_SUFFIX, SampleMapSteps, TarSteps, parse_sample_map, parse_tar_head
from .fetchers import (
    fetch_bam_header,
    fetch_bed_signals,
    fetch_fasta_headers,
    fetch_fastq_reads,
    fetch_gfa_segment_tags,
    fetch_sample_map,
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
    classify_from_tar_head,
    classify_from_vcf_header,
    classify_sample_map,
    tar_head_is_conclusive,
    workspace_header_member,
)
from .producer_steps import HeaderSteps
from .summaries import print_bam_summary, print_fastq_summary, print_vcf_summary
from .validators.header_extractors import parse_vcf_header


@dataclass(frozen=True)
class FileTypeConfig:
    """Configuration for a file type that can be classified via header inspection."""

    name: str
    extensions: tuple[str, ...]
    fetcher: Callable
    classifier: Callable
    summary_printer: Callable | None = None
    # Environment check run once before the worker pool (e.g. an external tool
    # must be installed). Raises to abort the run fast, instead of letting every
    # record fail the same way and vanish. None means no check.
    preflight: Callable | None = None
    # Detector for an escalating head-read (#260): given the fetcher's parsed payload,
    # returns whether the head is conclusive (enough to classify). The fetcher reads
    # deeper only while this is False. Injected here rather than imported by the fetcher,
    # so the reader stays decoupled from the classifier's recognition logic. None means
    # the fetcher reads a single fixed head (the default for every type but tar).
    head_detector: Callable | None = None
    # The parse of the fetched payload, made once per file (#615): the classifier and the
    # step reader both take it in place of the payload, so neither parses again. The cache
    # keeps the raw payload. None hands them the payload as fetched.
    parser: Callable | None = None
    # The step that made a file, read from its fetched content (#609). Called once per run
    # with every loaded record, the source's record key and the run's evidence base (where a
    # reader finds another file's cached header, #620), it returns the per-file
    # reader: given the parse, the file's name and dataset, ``(generated_by or None,
    # outcome)``, the outcome None for a file the reader does not apply to (a tar that is no
    # GenomicsDB workspace, #621), which is not counted. None means the type states no step;
    # a type with one needs a ``parser``.
    step: Callable | None = None
    # Given the member names an archive's head walk has read, the base name of the one
    # member whose text the fetcher keeps, or None (#621). Injected like ``head_detector``,
    # so the reader stays ignorant of which archives have a member worth reading. None
    # keeps none.
    kept_member: Callable | None = None

    def __post_init__(self):
        if self.step is not None and self.parser is None:
            raise ValueError(f"file type {self.name!r} reads a step but declares no parser to read it from")


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
    # A `.vcf.bgz` is a bgzipped VCF (1000 Genomes phase 3, in ANVIL_1000G_PRIMED). A PLINK 2
    # `.pvar` is no VCF, but one written from a VCF keeps its `##` header, so its `##contig`
    # lengths give its reference (#561); the VCF header rules, scoped to VCF extensions, do
    # not fire on it, and its data_type stays the PLINK extension rule's `genotypes`. A
    # `.pvar` whose head does not start with a `#` line (a headerless one, in `.bim` column
    # order) is unreadable here, and every dimension of it not_classified, as for any file a
    # header reader cannot read (#155); one whose header is only `#CHROM` is read, and gives no
    # reference. Its step is never read (`NOT_A_VCF`).
    extensions=(".vcf", ".vcf.gz", ".vcf.bgz", ".g.vcf.gz", ".gvcf.gz", ".pvar"),
    fetcher=fetch_vcf_header,
    classifier=classify_from_vcf_header,
    summary_printer=print_vcf_summary,
    parser=parse_vcf_header,
    # A HaplotypeCaller's input several alignments carry is settled from their headers: the
    # BAM producer's cache, or samtools into it on a miss (#620), so every VCF run with work
    # checks for samtools first, its own headers cached or not.
    step=partial(HeaderSteps.for_run, alignments=BAM_CONFIG.name),
    preflight=require_samtools,
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
    extensions=(".fasta", ".fasta.gz", ".fa", ".fa.gz", ".fna", ".fna.gz"),
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
    classifier=classify_from_tar_head,
    # Escalating head-read (#260): read deeper only until the members are classifiable,
    # so a GenomicsDB store whose variant signal sits past the first 256KiB is reached.
    head_detector=tar_head_is_conclusive,
    # A GenomicsDB workspace's `vcfheader.vcf` names the sample map it imported: the tar's
    # step (#621).
    kept_member=workspace_header_member,
    parser=parse_tar_head,
    step=TarSteps.for_run,
)

# GATK sample-name maps (#621): the list of gVCFs one GenomicsDB import joint-calls. Read
# whole for the cohort step it states; a file whose content is a map is a `sample_map`, and
# the data's five dimensions do not apply to it.
SAMPLE_MAP_CONFIG = FileTypeConfig(
    name="sample_map",
    extensions=(SAMPLE_MAP_SUFFIX,),
    fetcher=fetch_sample_map,
    classifier=classify_sample_map,
    parser=parse_sample_map,
    step=SampleMapSteps.for_run,
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
    "sample_map": SAMPLE_MAP_CONFIG,
}
