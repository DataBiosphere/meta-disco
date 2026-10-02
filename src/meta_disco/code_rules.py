"""The rules and markers written in Python, declared once (#572).

A YAML rule is declared in ``rules/unified_rules.yaml``, with its ``when``, ``then`` and
``rationale``. The rules here make a claim from code instead. Most read file content a ``when``
cannot express (contig lengths, BED coordinates, tar members). The index producer's
is in code because that producer builds its records itself: ``index_by_extension`` reads the
extension. ``inherited_from_parent`` is reconcile's: it carries a parent's settled answer
across a file's ``generated_by`` (contract 4.9, #571). Before #572 each one's id was a
string literal at its call site, so nothing listed them. Now every call site names its
rule through a constant here (``code_rules.VCF_CONTIG_LENGTH.id``), and
``tests/test_code_rules.py`` fails on a rule id written as a string literal elsewhere in
``src/`` or ``scripts/``: as a ``rule_id=`` keyword, as the ``rule_id`` of an evidence
dict, or as a ``*_RULE_ID`` module constant. An id reaching a call site some other way
(a constant named otherwise, say) is not caught by that test, which is a check on the
source and not on the output.

A **marker** carries a ``rule_id`` and names no rule. It records why a slot has no
value: the file could not be read, the input record broke the contract, or the index
producer took no parent. ``make rules-report`` lists markers in a table of their own.
The ``not_classified`` placeholder carries no ``rule_id`` at all, so it is not declared
here.

An **edge rule** states a derivation edge (ADR-0002) rather than a claim, so it sets no
dimension. It is declared here, in ``EDGE_RULES``, for the same reason the rules are: its id
is what an edge's ``rule_id`` carries, and nothing else lists it.

``basis`` says what a rule reads to reach its answer, in the report's terms
(``BASES``). A YAML rule's basis is worked out from its ``when`` by the report. A code
rule's is declared, because a code rule has no ``when`` to work it out from.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import activities
from .models import (
    SOURCE_CONTENT_READ,
    SOURCE_CONTIG_DETECTION,
    SOURCE_DERIVATION_INHERITANCE,
    SOURCE_FILENAME_RULE,
)

# What a rule reads to reach its answer. All but the last describe a rule of ours; a
# translation row (`rules/value_map.yaml`) is always `mapping`.
BASIS_EXTENSION = "extension"
BASIS_FILE_SIZE = "file_size"
BASIS_FILE_NAME = "file_name"
BASIS_DATASET = "dataset"
BASIS_CONTENT = "content"
BASIS_PARENT_FILE = "parent_file"
BASIS_MAPPING = "mapping"
BASES = (
    BASIS_EXTENSION,
    BASIS_FILE_SIZE,
    BASIS_FILE_NAME,
    BASIS_DATASET,
    BASIS_CONTENT,
    BASIS_PARENT_FILE,
    BASIS_MAPPING,
)

HEADER_CLASSIFIER = "src/meta_disco/header_classifier.py"
INDEX_PRODUCER = "scripts/classify_index_files.py"
RECONCILE_INHERIT = "src/meta_disco/reconcile_inherit.py"
EDGES = "src/meta_disco/edges.py"
METADATA_SCHEMA = "src/meta_disco/metadata_schema.py"


@dataclass(frozen=True)
class CodeRule:
    """One rule written in Python.

    ``module`` is the repository path of the file whose call sites emit it. ``reads`` is
    the content or input it decides from, and ``sets`` the dimensions it can claim.
    ``rationale`` says why what it reads supports what it claims, as a YAML rule's
    ``rationale`` does.
    """

    id: str
    module: str
    basis: str
    source_type: str
    reads: str
    sets: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class CodeMarker:
    """A ``rule_id`` that names no rule: why a slot was left without a value."""

    id: str
    module: str
    meaning: str


@dataclass(frozen=True)
class EdgeRule:
    """A rule that states a derivation edge from the child's own name (ADR-0002).

    ``activity`` and ``role`` are the step it states and the parent's part in it (#580).
    ``reads`` says how the
    parent's name is worked out from the child's, and ``rationale`` why that names the
    parent. Its ``source_type`` is ``filename_rule``: both edge rules read the name.
    """

    id: str
    module: str
    activity: str
    role: str
    source_type: str
    reads: str
    rationale: str


_REFERENCE = ("reference_assembly",)

CONTIG_LENGTH_DETECTION = CodeRule(
    id="contig_length_detection",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTIG_DETECTION,
    reads=(
        "BAM/CRAM/SAM header: the @SQ contig names and lengths for the family; for the build within "
        "it, chr1 and chrY's lengths and M5 checksums, and the reference name @SQ UR or an @PG "
        "command line declares"
    ),
    sets=_REFERENCE,
    rationale=(
        "An alignment's @SQ lines list the reference it was aligned to, contig by contig, "
        "and the lengths of the primary chromosomes differ between GRCh37, GRCh38 and "
        "CHM13, so matching them identifies the reference family. Where the build within it "
        "has a term of its own (#473), chr1 and chrY's lengths and checksums pick it, and a "
        "declared reference name only breaks a tie among the builds those allow."
    ),
)
VCF_CONTIG_LENGTH = CodeRule(
    id="vcf_contig_length",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTIG_DETECTION,
    reads=(
        "VCF header: the ##contig names and lengths for the family; for the build within it, chr1 "
        "and chrY's lengths, and the reference name ##reference or a command line declares (not for "
        "a lifted-over VCF)"
    ),
    sets=_REFERENCE,
    rationale=(
        "A VCF's ##contig lines declare the reference its positions are on. Their lengths "
        "identify the reference family as @SQ lengths do. ##contig carries no checksum, so "
        "builds that differ only in sequence are told apart only by a declared reference "
        "name, and without one the value is the family."
    ),
)
BED_COORDINATE_REFERENCE = CodeRule(
    id="bed_coordinate_reference",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTIG_DETECTION,
    reads="BED body: the largest coordinate seen per chromosome, and whether names carry a chr prefix",
    sets=_REFERENCE,
    rationale=(
        "Bare chromosome names (1, X) are the b37 convention, so they are claimed GRCh37. "
        "With a chr prefix, a coordinate past a chromosome's end in a reference rules that "
        "reference out, the prefix rules out GRCh37, and a reference is claimed only when "
        "exactly one is left."
    ),
)
BED_NONSTANDARD_CONTIGS = CodeRule(
    id="bed_nonstandard_contigs",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTIG_DETECTION,
    reads="BED body: chromosome names",
    sets=_REFERENCE,
    rationale=(
        "When no chromosome name is a standard one (1-22, X, Y, M or MT, with or without "
        "chr), the intervals are on an assembly's own contigs, not a standard reference, "
        "so reference_assembly does not apply."
    ),
)
FASTA_TRANSCRIPT_CONTIGS = CodeRule(
    id="fasta_transcript_contigs",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTIG_DETECTION,
    reads="FASTA header lines: sequence names",
    sets=("data_modality", "data_type"),
    rationale=(
        "Sequence names in transcript id form (ENST, NM_, NR_, XM_, rna-) outnumbering "
        "reference chromosome names mean the file holds transcript sequences: "
        "transcriptomic, data_type sequence."
    ),
)
FASTA_REFERENCE_CONTIGS = CodeRule(
    id="fasta_reference_contigs",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTIG_DETECTION,
    reads="FASTA header lines: sequence names",
    sets=("reference_assembly", "data_modality", "data_type"),
    rationale=(
        "At least 20 sequence names that are one known reference's chromosomes mean the "
        "file is that reference genome. A tie between references names none (#88)."
    ),
)
FASTA_ASSEMBLER_CONTIGS = CodeRule(
    id="fasta_assembler_contigs",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTIG_DETECTION,
    reads="FASTA header lines: sequence names",
    sets=("data_modality", "data_type", "reference_assembly"),
    rationale=(
        "Sequence names in the form assemblers write (h1tg, ptg, utg, ctg, scaffold_, "
        "contig_) mean a de novo assembly: genomic, data_type assembly, and no reference "
        "applies, since an assembly is its own."
    ),
)
FASTA_MANY_CONTIGS = CodeRule(
    id="fasta_many_contigs",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTIG_DETECTION,
    reads="FASTA header lines: how many sequences, and whether any is a reference chromosome",
    sets=("data_modality", "data_type", "reference_assembly"),
    rationale=(
        "More than 50 sequences, none of them a reference chromosome and none named as a "
        "transcript or by an assembler, are read as a de novo assembly: genomic, data_type "
        "assembly, no reference applies."
    ),
)
RGFA_STABLE_RANK_REFERENCE = CodeRule(
    id="rgfa_stable_rank_reference",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTIG_DETECTION,
    reads="rGFA segments: the SR (stable rank) and SN (stable name) tags",
    sets=("data_type",),
    rationale=(
        "Segments at stable rank 0 are the backbone that defines the graph's coordinate "
        "system, so a graph that has them is a reference pangenome (pangenome.reference)."
    ),
)
TAR_INNER_FORMAT = CodeRule(
    id="tar_inner_format",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads="tar archive head: its member names",
    sets=("data_modality", "data_type", "assay_type"),
    rationale=(
        "A container has no format of its own (#245), so it takes its contents'. A "
        "GenomicsDB member layout is a variant store (genomic, variants); otherwise the "
        "archive takes what the rules resolve for its dominant recognized member "
        "extension."
    ),
)
INDEX_BY_EXTENSION = CodeRule(
    id="index_by_extension",
    module=INDEX_PRODUCER,
    basis=BASIS_EXTENSION,
    source_type=SOURCE_FILENAME_RULE,
    reads="file extension: .bai, .crai, .tbi, .csi, .pbi and the others INDEX_TO_PARENT declares",
    sets=("data_type",),
    rationale=(
        "An index file is an index whatever it indexes, and its extension says so, with or "
        "without a parent (#437). The YAML rule index_file says the same for an index this "
        "producer misses."
    ),
)
INHERITED_FROM_PARENT = CodeRule(
    id="inherited_from_parent",
    module=RECONCILE_INHERIT,
    basis=BASIS_PARENT_FILE,
    source_type=SOURCE_DERIVATION_INHERITANCE,
    reads="the settled answers, at reconcile, of the parents in one input role of the file's generated_by",
    sets=activities.carried(),
    rationale=(
        "A file's step passes what its activity declares for each input role (rules/activities.yaml), "
        "from the parents in that role. "
        "Parents that agree give their value; parents that differ give mixed; a parent not_classified or "
        "in conflict gives nothing (contract 4.9). The claim is weighed with the file's own (4.2-4.6)."
    ),
)

CODE_RULES = (
    CONTIG_LENGTH_DETECTION,
    VCF_CONTIG_LENGTH,
    BED_COORDINATE_REFERENCE,
    BED_NONSTANDARD_CONTIGS,
    FASTA_TRANSCRIPT_CONTIGS,
    FASTA_REFERENCE_CONTIGS,
    FASTA_ASSEMBLER_CONTIGS,
    FASTA_MANY_CONTIGS,
    RGFA_STABLE_RANK_REFERENCE,
    TAR_INNER_FORMAT,
    INDEX_BY_EXTENSION,
    INHERITED_FROM_PARENT,
)

INDEX_BY_NAME = EdgeRule(
    id="index_by_name",
    module=INDEX_PRODUCER,
    activity=activities.INDEXING,
    role="indexed",
    source_type=SOURCE_FILENAME_RULE,
    reads=(
        "the index file's name: the name without its index extension (sample.bam.bai -> "
        "sample.bam), or with it replaced by a parent extension INDEX_TO_PARENT declares "
        "(sample.bai -> sample.bam), matched case-insensitively within the dataset"
    ),
    rationale=(
        "An index is named after the file it indexes, so the first candidate name any file "
        "of the dataset carries names its parent. Where two files carry that name it names "
        "neither and no edge is written; a later candidate is not tried (#438)."
    ),
)
CHECKSUM_BY_NAME = EdgeRule(
    id="checksum_by_name",
    module=EDGES,
    activity=activities.CHECKSUM,
    role="checked",
    source_type=SOURCE_FILENAME_RULE,
    reads=(
        "the name of a file whose extension EXTENSION_MAP calls a checksum, less that "
        "extension and any wrapper (sample.bam.md5 -> sample.bam), matched "
        "case-insensitively within the dataset"
    ),
    rationale=(
        "A checksum file is its file's name plus .md5, so the name without it, carried by "
        "exactly one file of the dataset, is the file it checks. A name two files carry "
        "names neither, and no edge is written."
    ),
)

EDGE_RULES = (INDEX_BY_NAME, CHECKSUM_BY_NAME)

FETCH_FAILED = CodeMarker(
    id="fetch_failed",
    module=HEADER_CLASSIFIER,
    meaning="The file's content could not be read, so every dimension is not_classified (#293).",
)
INPUT_VALIDATION = CodeMarker(
    id="input_validation",
    module=METADATA_SCHEMA,
    meaning="The input record broke the input contract, so every dimension is not_classified (#161).",
)
NO_MATCHING_PARENT = CodeMarker(
    id="no_matching_parent_in_dataset",
    module=INDEX_PRODUCER,
    meaning="An index file for which no file in its dataset carries a candidate parent name (#438).",
)
AMBIGUOUS_PARENT = CodeMarker(
    id="ambiguous_parent_in_dataset",
    module=INDEX_PRODUCER,
    meaning="An index file for which more than one file in its dataset carries the parent name (#438).",
)

MARKERS = (FETCH_FAILED, INPUT_VALIDATION, NO_MATCHING_PARENT, AMBIGUOUS_PARENT)
