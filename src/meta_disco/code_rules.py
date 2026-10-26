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

A **sample rule** (#357) reads which samples a file's data comes from, so it sets no
dimension either: out of the file's own content (a header, a GATK sample map's rows, a GenomicsDB
workspace's ``callset.json``), or, at
reconcile, out of its parent's settled samples (#668), the repository's record of the step that
generated it (#698), or its PLINK fileset's ``.psam`` (#751). It is declared in ``SAMPLE_RULES``; its
id is what a file's ``samples.named_by`` carries for that source.

An **entity rule** (#582) gives a donor's slot an answer, not a file's dimension. It is
declared in ``ENTITY_RULES``; its id is what the slot's claims carry as ``rule_id``. A donor's
parent claims cite instead the identifier rule (``rules/sample_namespaces.yaml``) that
recognised the parent.

An **identity check** (#718) lets an importer write an identity link it could not otherwise
confirm: it sets no slot and no claim cites it, since an importer writes no ``rule_id``
(contract 1.1). It is declared in ``IDENTITY_CHECKS``; its id is what the importer's
per-sample outcomes name as the check that linked the sample.

``basis`` says what a rule reads to reach its answer, in the report's terms
(``BASES``). A YAML rule's basis is worked out from its ``when`` by the report. A code
rule's is declared, because a code rule has no ``when`` to work it out from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import activities
from .models import (
    ANATOMICAL_SITE,
    FAMILY_ID,
    SOURCE_CONTENT_READ,
    SOURCE_CONTIG_DETECTION,
    SOURCE_DERIVATION_INHERITANCE,
    SOURCE_EXTERNAL_GROUND_TRUTH,
    SOURCE_FILENAME_RULE,
    SOURCE_PUBLISHED_VALUE,
    SOURCE_REPOSITORY_ACTIVITY,
    SOURCE_REPOSITORY_METADATA,
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
PRODUCER_STEPS = "src/meta_disco/producer_steps.py"
COHORT_STEPS = "src/meta_disco/cohort_steps.py"
BCFTOOLS_STATS = "src/meta_disco/bcftools_stats.py"
METADATA_SCHEMA = "src/meta_disco/metadata_schema.py"
SAMPLE_IDENTITY = "src/meta_disco/sample_identity.py"
RECONCILE_SAMPLES = "src/meta_disco/reconcile_samples.py"
RECONCILE_LINEAGE = "src/meta_disco/reconcile_lineage.py"
RECONCILE_ENTITIES = "src/meta_disco/reconcile_entities.py"
RECONCILE_EXTERNAL = "src/meta_disco/reconcile_external.py"
SGDP_ENTITIES = "src/meta_disco/sgdp_entities.py"


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
    """A rule that states a derivation edge (ADR-0002), from the child's own name or its header.

    ``activity`` and ``role`` are the step it states and the parent's part in it (#580).
    ``reads`` says where the parent's name is read: from the child's own name
    (``filename_rule``, the index and checksum rules) or from a command line in the
    child's header (``content_read``, #609). ``rationale`` says why that names the parent.
    """

    id: str
    module: str
    activity: str
    role: str
    source_type: str
    reads: str
    rationale: str


@dataclass(frozen=True)
class SampleRule:
    """A rule that reads which samples a file's data comes from (#357): out of the file's own
    content (a header, a sample map's rows, a workspace's ``callset.json``, a ``.psam``'s rows), or at
    reconcile its parent's settled samples (#668), the repository's record of the step that generated it
    (#698) or its PLINK fileset's ``.psam``'s (#751).

    ``reads`` says where; ``rationale`` says why that names the samples. Each string a content
    reader reads becomes a sample only through ``rules/sample_namespaces.yaml``.
    """

    id: str
    module: str
    source_type: str
    reads: str
    rationale: str


@dataclass(frozen=True)
class EntityRule:
    """A rule that gives a donor's slot an answer from entity evidence (#582), at reconcile.

    ``sets`` is the donor slots it can claim; ``reads`` and ``rationale`` as a code rule's.
    """

    id: str
    module: str
    source_type: str
    reads: str
    sets: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class IdentityCheck:
    """A check that confirms an identity link an importer writes (#718): ``reads`` says what it compares,
    ``rationale`` why agreement confirms the link."""

    id: str
    module: str
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
        "and a primary chromosome's length differs between the reference_contig_lengths "
        "assemblies that share its name, so matching them identifies the reference family. Where the build within it "
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
VCF_GVCF = CodeRule(
    id="vcf_gvcf",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header: the reference-confidence mode (-ERC) on the command line of the step that made "
        "the file (the end of its data flow), where that step is a GATK HaplotypeCaller; and the ALT "
        "column of the first records the head read"
    ),
    sets=("data_type",),
    rationale=(
        "A gVCF represents every site, variant or not, each in a record of its own or in a block "
        "record covering a run of sites with no variant, and carries the symbolic <NON_REF> "
        "allele in every record's ALT (GATK, 'GVCF - Genomic Variant Call Format', "
        "https://gatk.broadinstitute.org/hc/en-us/articles/360035531812). HaplotypeCaller writes one "
        "when run with -ERC GVCF (non-variant sites condensed into blocks) or -ERC BP_RESOLUTION (a "
        "record per site); NONE, the default, is regular calling (GATK, 'HaplotypeCaller', "
        "https://gatk.broadinstitute.org/hc/en-us/articles/360037225632). Both must say so: the step "
        "that made the file is a HaplotypeCaller in one of those modes; and every record read has "
        "<NON_REF> among its ALT alleles, at least one with it alone, a site with no variant (#607). "
        "The step alone is not enough: a tool that writes no command line leaves the header's last "
        "step in place, so a gVCF filtered to its variant sites would still read as made by "
        "HaplotypeCaller; its records then have no site with <NON_REF> alone. The records alone are "
        "not either: GenotypeGVCFs drops <NON_REF> in a normal run, but keeps it at some sites under "
        "--include-non-variant-sites (GATK forum, "
        "https://gatk.broadinstitute.org/hc/en-us/community/posts/360056352871). The "
        "##ALT=<ID=NON_REF> and ##GVCFBlock header lines, and an earlier step's -ERC GVCF line, carry "
        "over into the joint-called VCFs and PLINK .pvar files made from gVCFs, so none of them is read."
    ),
)
_CALLER_KINDS = (
    "The caller calls one kind of variant, so its kind is the file's, looked up in "
    "rules/callers.yaml; a tool the table does not list gives no kind (#654). The records "
    "cannot settle it: a mixed callset shows a structural variant in its first records only by "
    "chance (#630). "
)
VCF_SAMPLE_COLUMN_COUNT = CodeRule(
    id="vcf_sample_column_count",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header: the #CHROM line's fixed columns and the sample columns after FORMAT; for one or more, the ALT "
        "column of the first records the head read. Not a PLINK 2 .pvar, by its name"
    ),
    sets=("data_type",),
    rationale=(
        "The VCF specification gives each sample whose genotypes a file holds a column after FORMAT, "
        "and a file with no FORMAT column holds no genotypes (VCF 4.3, section 1.5, the header line). "
        "None is sites-only; one is single-sample and two or more multi-sample (#655), only where no "
        "record read has <NON_REF> or <*> among its ALT alleles. A gVCF's records carry GATK's "
        "<NON_REF> (GATK, 'GVCF - Genomic Variant Call Format') or the specification's <*>, which "
        "DeepVariant and bcftools write (VCF 4.3, section 5.5), whether it holds one sample or, "
        "combined (CombineGVCFs), several; a file whose records carry either is left to the content "
        "that says what it is. A file with one column and no records read gets no claim, since so "
        "many one-sample files are gVCFs. The count is of columns, not people: HPRC's "
        ".pair.vcf.gz files hold one person's two haplotypes in two columns. A .pvar is read through "
        "the VCF reader for its ##contig lines (#561) but is a PLINK file, whose data_type is the "
        "PLINK extension rule's."
    ),
)
VCF_STEP_CALLER_KIND = CodeRule(
    id="vcf_step_caller_kind",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header: its command lines, as steps; the producing step (the end of their data flow), "
        "walked back through steps that keep the kind (SelectVariants, GenotypeGVCFs, FilterMutectCalls, "
        "ApplyVQSR, ApplyRecalibration, bcftools view, norm, annotate) to the step that called the variants"
    ),
    sets=("variant_kind",),
    rationale=(
        _CALLER_KINDS + "Where the chain names no caller (no one producing step, or a kept step's "
        "input written by no step the header records), the header's steps that do not keep the kind "
        "name it: a merge among them (vcf_merge_small_callers), else the one tool they are, if they are "
        "exactly one. A command line the reader does not know gives no kind."
    ),
)
VCF_SOURCE_CALLER_KIND = CodeRule(
    id="vcf_source_caller_kind",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header whose command lines name no caller (or that has none): its ##source lines and a "
        "##DeepVariant_version line"
    ),
    sets=("variant_kind",),
    rationale=(
        _CALLER_KINDS + "Structural-variant callers (Sniffles, SVIM) and DeepVariant record "
        "themselves only so. Taken only where they name exactly one tool, spellings of one caller "
        "counted once: a header naming two tools gives no kind."
    ),
)
VCF_MERGE_SMALL_CALLERS = CodeRule(
    id="vcf_merge_small_callers",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header whose caller is a merge (bcftools concat, merge; GATK GenomicsDBImport, CombineGVCFs): "
        "every caller its command lines and ##source lines name, and its ##INFO and ##ALT declarations "
        "of structural variants"
    ),
    sets=("variant_kind",),
    rationale=(
        "A merge holds what its inputs held. It is small variants where every caller the header names "
        "calls small variants and the header declares no structural-variant field: a merged header can "
        "lose an input's ##source line, but the VCF spec requires a structural variant to be declared, "
        "so an input's structural variants leave their declarations behind (#654)."
    ),
)
_CALLER_ORIGINS = (
    "Each caller the table lists calls variants of one origin, germline or somatic, or, for one "
    "listed with a somatic mode, of one origin unless a mode flag is set (a caller that mixes "
    "them, as Mutect2 can, is not listed), so its origin is the file's, "
    "looked up in rules/callers.yaml; a tool the table does not list gives no origin (#658). A "
    "caller with a somatic mode (Sniffles2's --non-germline, --mosaic and two more) gives its origin only where "
    "the header records its command line without the mode's flags, or names it by a ##source "
    "spelling of a version without the mode (Sniffles 1). A germline reading is refused where the "
    "header declares the SOMATIC INFO flag or ##tumor_sample / ##normal_sample. "
)
VCF_STEP_CALLER_ORIGIN = CodeRule(
    id="vcf_step_caller_origin",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header: its command lines, as steps; the caller vcf_step_caller_kind finds behind the "
        "producing step, and that caller's own command line for a somatic mode's flags; its ##source "
        "spellings; and its SOMATIC INFO, ##tumor_sample and ##normal_sample declarations"
    ),
    sets=("variant_origin",),
    rationale=(
        _CALLER_ORIGINS + "The caller is found as for the kind; the header's one other step, taken "
        "where the chain names none, is refused where the header names itself a tool of another origin, "
        "or a caller whose somatic mode it leaves open."
    ),
)
VCF_SOURCE_CALLER_ORIGIN = CodeRule(
    id="vcf_source_caller_origin",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header whose command lines name no caller (or that has none): its ##source lines and a "
        "##DeepVariant_version line, and its SOMATIC INFO, ##tumor_sample and ##normal_sample declarations"
    ),
    sets=("variant_origin",),
    rationale=(_CALLER_ORIGINS + "Taken only where they name exactly one tool, as for vcf_source_caller_kind."),
)
VCF_MERGE_GERMLINE_CALLERS = CodeRule(
    id="vcf_merge_germline_callers",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header whose caller is a merge (bcftools concat, merge; GATK GenomicsDBImport, CombineGVCFs): "
        "every caller its command lines and ##source lines name, those callers' command lines for a "
        "somatic mode's flags, and its declarations of somatic calls"
    ),
    sets=("variant_origin",),
    rationale=(
        "A merge holds what its inputs held. It is germline where every caller the header names "
        "calls germline variants, none in a somatic mode, and the header declares neither the "
        "SOMATIC INFO flag nor a tumour or normal sample: a merged header can lose an input's "
        "##source line, so a somatic input is also looked for in what the header declares (#658)."
    ),
)
# The six tar rules mirror the six VCF caller rules: per dimension, one per way the caller is found (#678).
_WORKSPACE_HEADER = (
    "GenomicsDB workspace tar: its vcfheader.vcf, the header GenomicsDBImport writes, which records the "
    "import's command line beside command lines carried over from its gVCFs' headers, read as "
)
_WORKSPACE = (
    "A workspace holds the calls it imported, and its header records the steps behind it, so its caller "
    "is read as a VCF's (#678), the workspace's name (the tar's, less .tar and any .gz) standing for the "
    "file's, since the import's output is the directory the tar was made from; a tar named otherwise "
    "reads the same, through the header's import, a merge. "
)


# Each VCF caller rule's tar twin, by id: a twin's text names the twins, not the VCF rules.
_TAR_TWIN_IDS = {
    VCF_STEP_CALLER_KIND.id: "tar_step_caller_kind",
    VCF_SOURCE_CALLER_KIND.id: "tar_source_caller_kind",
    VCF_MERGE_SMALL_CALLERS.id: "tar_merge_small_callers",
    VCF_STEP_CALLER_ORIGIN.id: "tar_step_caller_origin",
    VCF_SOURCE_CALLER_ORIGIN.id: "tar_source_caller_origin",
    VCF_MERGE_GERMLINE_CALLERS.id: "tar_merge_germline_callers",
}


def _as_tar(text: str) -> str:
    """``text`` with each VCF caller rule's id it names replaced by its tar twin's."""
    return re.sub(r"\b(" + "|".join(_TAR_TWIN_IDS) + r")\b", lambda m: _TAR_TWIN_IDS[m.group(1)], text)


def _tar_twin(vcf_rule: CodeRule, unread: str = "") -> CodeRule:
    """The tar rule that reads a workspace's header as ``vcf_rule`` reads a VCF's (``unread``: what a header not read gives)."""
    return CodeRule(
        id=_TAR_TWIN_IDS[vcf_rule.id],
        module=HEADER_CLASSIFIER,
        basis=BASIS_CONTENT,
        source_type=SOURCE_CONTENT_READ,
        reads=f"{_WORKSPACE_HEADER}a VCF's is: {_as_tar(vcf_rule.reads)}",
        sets=vcf_rule.sets,
        rationale=_WORKSPACE + _as_tar(vcf_rule.rationale) + unread,
    )


TAR_STEP_CALLER_KIND = _tar_twin(VCF_STEP_CALLER_KIND, " A workspace whose header was not read gives no kind.")
TAR_SOURCE_CALLER_KIND = _tar_twin(VCF_SOURCE_CALLER_KIND)
TAR_MERGE_SMALL_CALLERS = _tar_twin(VCF_MERGE_SMALL_CALLERS)
TAR_STEP_CALLER_ORIGIN = _tar_twin(VCF_STEP_CALLER_ORIGIN, " A workspace whose header was not read gives no origin.")
TAR_SOURCE_CALLER_ORIGIN = _tar_twin(VCF_SOURCE_CALLER_ORIGIN)
TAR_MERGE_GERMLINE_CALLERS = _tar_twin(VCF_MERGE_GERMLINE_CALLERS)
BED_COORDINATE_REFERENCE = CodeRule(
    id="bed_coordinate_reference",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTIG_DETECTION,
    reads="BED body: the largest coordinate seen per chromosome, and whether names carry a chr prefix",
    sets=_REFERENCE,
    rationale=(
        "A coordinate past a chromosome's end in a human reference rules that reference out, "
        "whether the names carry a chr prefix or not; where more than one is left, a chr prefix "
        "also rules out GRCh37; and a reference is claimed only when exactly one is left."
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
        "A container has no format of its own (#245), so it takes its contents': what the rules "
        "resolve for its dominant recognized member extension. A GenomicsDB workspace is "
        "tar_genomicsdb_workspace's."
    ),
)
TAR_GENOMICSDB_WORKSPACE = CodeRule(
    id="tar_genomicsdb_workspace",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "tar archive head: its member names, for a GenomicsDB workspace's layout (VCF-attribute "
        "TileDB arrays or its schema files)"
    ),
    sets=("data_modality", "data_type"),
    rationale=(
        "GATK's GenomicsDBImport writes a workspace of TileDB arrays holding the calls of the gVCFs "
        "it imported, with its own schema files beside them (GATK, 'GenomicsDBImport'), so the "
        "layout names a store of variant calls: genomic, variants.genomicsdb (#655)."
    ),
)
SAMPLE_MAP_CONTENT = CodeRule(
    id="sample_map_content",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads="a GATK sample-name map's rows: two or three tab-separated columns, the second a VCF path",
    sets=(
        "data_type",
        "data_modality",
        "reference_assembly",
        "assay_type",
        "platform",
        "instrument_model",
        "variant_kind",
        "variant_origin",
    ),
    rationale=(
        "A file whose rows are a sample name and a VCF path is a list of files, not their "
        "data (#621): its data_type is sample_map, and the seven dimensions of the data do "
        "not apply to it, as for a checksum (#596). Read from the content, so a file that "
        "is only named like a map keeps what its name says."
    ),
)
IDAT_CHIP_TYPE = CodeRule(
    id="idat_chip_type",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads="an Illumina IDAT's header: its chip type (field 403) and its number of probes (field 1000)",
    sets=("data_modality", "assay_type"),
    rationale=(
        "Genotyping and methylation BeadChips both write IDAT, so the extension cannot say "
        "which (#603). A chip is recognised only as the exact chip type and probe count read "
        "from real files: 1-95um_multi-swath_for_8x2-5M with 2,522,340 probes is the HPRC's "
        "Infinium Omni2.5-8 v1.3 genotyping BeadChip, as its methods name it (Liao et al. "
        "2023, PMC10172123). Any other chip, a methylation chip included, is left "
        "not_classified with what was read."
    ),
)
IDAT_SCANNER = CodeRule(
    id="idat_scanner",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads="an Illumina IDAT's run log (field 300): the software each Scan row names",
    sets=("platform", "instrument_model"),
    rationale=(
        "The run log records the software that scanned the chip, not the scanner's model, so "
        "the model is inferred from the software: iScan Control Software is the software of "
        "Illumina's iScan System, the scanner the HPRC's methods name for its arrays (#603). "
        "If another Illumina scanner ran the same software, its files would be called iScan; "
        "a source naming the scanner would settle it. Every Scan row must name the same "
        "recognised software; otherwise platform and instrument are left not_classified with "
        "what was read."
    ),
)
FAST5_DEVICE_TYPE = CodeRule(
    id="fast5_device_type",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads="a nanopore FAST5's first 64 KiB: each attribute named device_type (MinKNOW writes it in tracking_id)",
    sets=("instrument_model",),
    rationale=(
        "MinKNOW records the kind of device that ran the sequencing run as every read's tracking_id "
        "device_type, beside the sample_id (#747). Its promethion, minion and gridion are Oxford "
        "Nanopore's PromethION, MinION and GridION. A head holding one of them names the instrument; "
        "one holding none, another value, two or more values or one laid out otherwise is left not_classified "
        "with what was read. Found by name in the bytes already read for the sample, its "
        "message parsed whole."
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
    VCF_GVCF,
    VCF_SAMPLE_COLUMN_COUNT,
    VCF_STEP_CALLER_KIND,
    VCF_SOURCE_CALLER_KIND,
    VCF_MERGE_SMALL_CALLERS,
    VCF_STEP_CALLER_ORIGIN,
    VCF_SOURCE_CALLER_ORIGIN,
    VCF_MERGE_GERMLINE_CALLERS,
    TAR_STEP_CALLER_KIND,
    TAR_SOURCE_CALLER_KIND,
    TAR_MERGE_SMALL_CALLERS,
    TAR_STEP_CALLER_ORIGIN,
    TAR_SOURCE_CALLER_ORIGIN,
    TAR_MERGE_GERMLINE_CALLERS,
    BED_COORDINATE_REFERENCE,
    BED_NONSTANDARD_CONTIGS,
    FASTA_TRANSCRIPT_CONTIGS,
    FASTA_REFERENCE_CONTIGS,
    FASTA_ASSEMBLER_CONTIGS,
    FASTA_MANY_CONTIGS,
    RGFA_STABLE_RANK_REFERENCE,
    TAR_INNER_FORMAT,
    TAR_GENOMICSDB_WORKSPACE,
    SAMPLE_MAP_CONTENT,
    IDAT_CHIP_TYPE,
    IDAT_SCANNER,
    FAST5_DEVICE_TYPE,
    INDEX_BY_EXTENSION,
    INHERITED_FROM_PARENT,
)

# How a name rule settles a name several files of the dataset carry (#717, ``edges.matches``),
# in each rule's ``reads`` and ``rationale``.
_FOLDER_READ = (
    "; where several files carry the name, the folder of each one's storage path (the input's "
    "file_path) against the child's"
)
_FOLDER_RATIONALE = (
    "unless exactly one of them is in the child's own folder (#717): a dataset can store one "
    "pipeline's outputs under the same names in a folder per cohort, as ANVIL_T2T_CHRY does"
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
        "(sample.bai -> sample.bam), matched case-insensitively within the dataset" + _FOLDER_READ
    ),
    rationale=(
        "An index is named after the file it indexes, so the first candidate name any file "
        "of the dataset carries names its parent. Where two files carry that name it names "
        "neither and no edge is written, " + _FOLDER_RATIONALE + "; a later candidate is not tried (#438)."
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
        "case-insensitively within the dataset" + _FOLDER_READ
    ),
    rationale=(
        "A checksum file is its file's name plus .md5, so the name without it, carried by "
        "exactly one file of the dataset, is the file it checks. A name two files carry "
        "names neither, and no edge is written, " + _FOLDER_RATIONALE + "."
    ),
)

VARIANT_CALL_BY_HEADER = EdgeRule(
    id="variant_call_by_header",
    module=PRODUCER_STEPS,
    activity=activities.VARIANT_CALL,
    role="calls_from",
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "the VCF's own header: its producer command lines (##GATKCommandLine, ##bcftools_*Command) "
        "chained by matching outputs to inputs, the one end of that flow being the step that made the "
        "file; where that step is HaplotypeCaller with one alignment input, the input's base name, "
        "matched case-insensitively within the dataset; where several alignments carry that name, the "
        "VCF's ##contig names and lengths and each of those alignments' @SQ names and lengths (on a "
        "GATK 4 line)" + _FOLDER_READ
    ),
    rationale=(
        "HaplotypeCaller records the alignment it called from in its own command line, written into "
        "the VCF it writes. A file that carries several command lines carries its inputs' too, and GATK "
        "sorts them, so the step is the end of the data flow, never the last line. The paths are where "
        "the workflow ran, so only the name is matched, and a name two files of the dataset carry names "
        "neither (#438), unless, on a GATK 4 line, exactly one of them fits the VCF's contigs: GATK 4 refuses an alignment "
        "with a contig its reference lacks or gives another length (unless the line turns that check "
        "off, which no header we hold does), and writes that reference's contigs into the VCF, so of two "
        "re-alignments of one sample's reads the one whose every contig is the VCF's, at its length, is "
        "its parent (#620). Where the contigs leave several, or a GATK 3 line (whose contigs are not "
        "relied on) names a shared name, it names neither " + _FOLDER_RATIONALE + "; the folder "
        "never overrides the contigs."
    ),
)

MERGE_BY_HEADER = EdgeRule(
    id="merge_by_header",
    module=PRODUCER_STEPS,
    activity=activities.MERGE,
    role="shard",
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "the VCF's own header, its producing step found as for variant_call_by_header; where that "
        "step is bcftools concat, each of its input VCFs' base names, matched case-insensitively "
        "within the dataset" + _FOLDER_READ
    ),
    rationale=(
        "bcftools concat records its inputs in its own command line, written into the VCF it writes: "
        "T2T's chromosome VCFs name every region VCF they join. The step is taken only when it joins "
        "two or more VCFs, none read from stdin, and every input is a VCF that exactly one file of the "
        "dataset carries (or, of several, exactly one in the merged VCF's own folder, #717), so a merge "
        "never names part of "
        "its inputs (#610)."
    ),
)

MERGE_BY_WORKSPACE_HEADER = EdgeRule(
    id="merge_by_workspace_header",
    module=COHORT_STEPS,
    activity=activities.COHORT_MERGE,
    role="input_list",
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "a GenomicsDB workspace tar's own vcfheader.vcf member: its one GenomicsDBImport command line, "
        "whose --genomicsdb-workspace-path names the tar (its name less .tar) and whose --sample-name-map "
        "names the list of gVCFs it imported, that list's base name matched case-insensitively among the "
        "dataset's sample maps" + _FOLDER_READ
    ),
    rationale=(
        "GenomicsDBImport writes its own command line into the workspace it builds, so the tar says "
        "which list of gVCFs it merged. The tar names the list, not each gVCF: one step per tar with "
        "3,202 inputs would be about 100M links, so the list is the input and its members' answers are "
        "read through it (#621). A workspace naming another directory than the tar, or given gVCFs one "
        "by one, gives no step. In a folder whose lists are rebuilt (cohort_by_rebuilt_sample_map) the "
        "list is the one rebuilt for the tar, never a catalog map."
    ),
)

# The step of a sample map no one holds, rebuilt from the workspace tars that read it (#726).
COHORT_BY_REBUILT_SAMPLE_MAP = EdgeRule(
    id="cohort_by_rebuilt_sample_map",
    module=COHORT_STEPS,
    activity=activities.COHORT_DEFINITION,
    role="member",
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "a GenomicsDB workspace tar in a folder cohort_steps.REBUILT_MAP_FOLDERS declares: the sample-name map "
        "its own vcfheader.vcf names, and the samples its own callset.json lists; each sample's gVCF is the one "
        "file of the dataset at the path the declared layout gives for that map and sample, under the tar's "
        "reference folder (SGDP_CHM13v2/haplotype_calling_vcfs/chr1/simons_data_sample_1.chr1.hc.vcf.gz for "
        "chr1_sample_map.tsv), matched by base name up to case and by folder exactly"
    ),
    rationale=(
        "ANVIL_T2T_CHRY's SGDP workspace tars name sample maps whose bucket is deleted, both reference runs naming "
        "the same paths, so no map says which gVCFs a tar read (#624). The tar's own callset.json says which "
        "samples, its header's map which region, and its folder which reference; the run wrote one gVCF per "
        "sample, region and reference, so these name each input. The layout is the pipeline's: rebuilt the same "
        "way, all 78,447 rows of the 1000 Genomes run's published maps come out as published, its one chrX_PAR "
        "map read as the PAR1 and PAR2 maps the tars name, as sources/external_files.yaml reads it (measured "
        "2026-10-22). A sample whose gVCF no file or two files carry, or a sample listed twice, gives no list: "
        "a cohort missing a member is not the cohort."
    ),
)

COHORT_BY_SAMPLE_MAP = EdgeRule(
    id="cohort_by_sample_map",
    module=COHORT_STEPS,
    activity=activities.COHORT_DEFINITION,
    role="member",
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "a GATK sample-name map's own rows, each a sample name and a VCF path, tab-separated; each path's "
        "base name matched case-insensitively within the dataset" + _FOLDER_READ
    ),
    rationale=(
        "A sample-name map lists the gVCFs one joint calling imports: it is the record of who was "
        "computed together. The paths are where the workflow ran, so only the name is matched. A file "
        "that is not such a list, or a member no file or two files of the dataset carry (the folder not "
        "settling it, #717), gives no step: a cohort missing a member is not the cohort (#621)."
    ),
)

# A workaround until AnVIL holds the maps (#624): the step of a sample map held outside AnVIL for
# a dataset, built at reconcile from the declared copy (#710).
COHORT_BY_EXTERNAL_SAMPLE_MAP = EdgeRule(
    id="cohort_by_external_sample_map",
    module=RECONCILE_EXTERNAL,
    activity=activities.COHORT_DEFINITION,
    role="member",
    source_type=SOURCE_EXTERNAL_GROUND_TRUTH,
    reads=(
        "the rows, at reconcile, of a GATK sample-name map held outside AnVIL for the dataset "
        "(sources/external_files.yaml, pinned by commit and sha256): each path's base name, exactly, "
        "among the dataset's files"
    ),
    rationale=(
        "A published copy of the sample-name map a workspace tar was imported from lists the gVCFs that "
        "import joint-called, as a catalog map does (#621); a tar is linked to the copy only where its own "
        "callset.json names exactly the copy's samples (external_lineage). A row whose name no file or "
        "two files of the dataset carry gives no step: a cohort missing a member is not the cohort."
    ),
)

QC_REPORT_BY_CONTENT = EdgeRule(
    id="qc_report_by_content",
    module=BCFTOOLS_STATS,
    activity=activities.QUALITY_CONTROL,
    role="reported_on",
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "a bcftools stats report's own text: line 1 naming bcftools stats, and its one ID line's input path, "
        "the path's base name matched case-insensitively among the dataset's VCFs" + _FOLDER_READ
    ),
    rationale=(
        "bcftools stats writes the path of each file it reports on as an ID line of its report, so the "
        "report names the VCF its numbers describe (#683). The path is where the workflow ran, so only the "
        "name is matched. A report on two or more inputs, or whose input no file or two files of the dataset "
        "carry (the folder not settling it, #717), gives no step."
    ),
)

EDGE_RULES = (
    INDEX_BY_NAME,
    CHECKSUM_BY_NAME,
    VARIANT_CALL_BY_HEADER,
    MERGE_BY_HEADER,
    MERGE_BY_WORKSPACE_HEADER,
    COHORT_BY_SAMPLE_MAP,
    COHORT_BY_REBUILT_SAMPLE_MAP,
    COHORT_BY_EXTERNAL_SAMPLE_MAP,
    QC_REPORT_BY_CONTENT,
)

BAM_READ_GROUP_SAMPLES = SampleRule(
    id="bam_read_group_samples",
    module=SAMPLE_IDENTITY,
    source_type=SOURCE_CONTENT_READ,
    reads="a BAM/CRAM header's @RG lines: each distinct SM, every read group having one",
    rationale=(
        "SM is the SAM specification's field for the sample a read group's reads come from. A "
        "header whose every read group has an SM, each recognised, names the file's samples; one "
        "with a read group without SM, or an SM no identifier rule recognises (`Sample`, "
        "`BioSample_3`), names none."
    ),
)
VCF_SAMPLE_COLUMNS = SampleRule(
    id="vcf_sample_columns",
    module=SAMPLE_IDENTITY,
    source_type=SOURCE_CONTENT_READ,
    reads="a VCF header's #CHROM line: each column after FORMAT",
    rationale=(
        "The VCF specification gives each sample whose genotypes a file holds a column after "
        "FORMAT, named for the sample. A header whose every column is recognised names the "
        "file's samples; one with a column no identifier rule recognises (a BAM path, "
        "`syndip`) names none, and a sites-only file has no sample columns."
    ),
)

SAMPLE_MAP_ROWS = SampleRule(
    id="sample_map_rows",
    module=SAMPLE_IDENTITY,
    source_type=SOURCE_CONTENT_READ,
    reads="a GATK sample-name map's rows: the sample name in each row's first column",
    rationale=(
        "A sample-name map gives each sample a GenomicsDB import joint-calls a row, the sample's name "
        "first and its gVCF second; the import writes that name as the sample's column in what it "
        "makes (#668). A map whose every name is recognised names the samples of the cohort it "
        "lists; one with a name no identifier rule recognises names none."
    ),
)
FAST5_TRACKING_SAMPLE = SampleRule(
    id="fast5_tracking_sample",
    module=SAMPLE_IDENTITY,
    source_type=SOURCE_CONTENT_READ,
    reads="a nanopore FAST5's first 64 KiB: each attribute named sample_id (MinKNOW writes it in tracking_id)",
    rationale=(
        "MinKNOW writes one sequencing run's reads to a FAST5, and records the sample the run "
        "sequenced as every read's tracking_id sample_id; the one NIA_CARD file read whole stores it "
        "once, shared by its 4,000 reads (#605). A head holding one recognised value names the file's sample; one holding "
        "none, an unrecognised value or two or more values names none. The attribute is found by its name and "
        "its message parsed whole, not reached by walking the file, which would read about 7.5 MB."
    ),
)
TAR_CALLSET_SAMPLES = SampleRule(
    id="tar_callset_samples",
    module=SAMPLE_IDENTITY,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "a GenomicsDB workspace tar's callset.json: each callset's sample_name, read only for the workspaces "
        "header_classifier.CALLSET_FOLDERS declares (ANVIL_T2T_CHRY's SGDP cohort)"
    ),
    rationale=(
        "GenomicsDBImport writes one callset per sample it imports into the workspace, named for the "
        "sample, so the list names whose genotypes the tar holds (#724). A list whose every name is "
        "recognised names the tar's samples; one with a name no identifier rule recognises names none. "
        "Read where nothing else names the tar's samples: SGDP's sample maps are not public (#624)."
    ),
)
PSAM_SAMPLE_IDS = SampleRule(
    id="psam_sample_ids",
    module=SAMPLE_IDENTITY,
    source_type=SOURCE_CONTENT_READ,
    reads="a PLINK 2 .psam read whole: the IID of each row after its #FID or #IID header line",
    rationale=(
        "A .psam is a PLINK 2 fileset's sample table, one row per sample whose genotypes its .pgen holds, "
        "each named by its IID (#751). A table whose every IID is recognised names the file's samples; one "
        "with an IID no identifier rule recognises names none, and one with no #FID or #IID header is not read."
    ),
)
BCFTOOLS_STATS_SAMPLES = SampleRule(
    id="bcftools_stats_samples",
    module=BCFTOOLS_STATS,
    source_type=SOURCE_CONTENT_READ,
    reads="a bcftools stats report's PSC lines: the sample name on each",
    rationale=(
        "Given samples, bcftools stats reports on exactly those samples' genotypes, one PSC line each, named "
        "for the sample (#683). A report whose every name is recognised names the file's samples; one with "
        "a name no identifier rule recognises names none. One with no PSC line names none of its own: where "
        "its step resolves, its samples are those of the VCF it reports on, passed across it (#668)."
    ),
)

SAMPLES_INHERITED_FROM_PARENT = SampleRule(
    id="samples_inherited_from_parent",
    module=RECONCILE_SAMPLES,
    source_type=SOURCE_DERIVATION_INHERITANCE,
    reads=(
        "the settled samples, at reconcile, of the parent in an input role of the file's generated_by that "
        "passes samples (rules/activities.yaml's passes_samples)"
    ),
    rationale=(
        "An index, checksum, QC report or coverage track describes exactly the file it was made from, "
        "and a cohort's merge exactly the samples its list names, so the file holds that parent's "
        "samples (#668). A parent with none, or parents naming different lists, pass nothing; the "
        "file's own sources and the parent's settle as any two sources do."
    ),
)

SAMPLES_FROM_ACTIVITY_BIOSAMPLE = SampleRule(
    id="samples_from_activity_biosample",
    module=RECONCILE_LINEAGE,
    source_type=SOURCE_REPOSITORY_ACTIVITY,
    reads=(
        "at reconcile, the repository's own record of the steps that generated the file (AnVIL's "
        "anvil_activity rows, or anvil_sequencingactivity where a dataset's transform wrote that, naming it "
        "as a generated_file_id): each row's used_biosample_id, tied to one of our sample records through "
        "that record's repository_ids"
    ),
    rationale=(
        "A step that used a biosample and generated a file made the file from that biosample's material, "
        "so the repository says the file holds that sample's data (#698). The biosamples every such row "
        "names are one source; a biosample tying to no sample record names none, and the file is "
        "counted. It settles with the file's other sources as any two do, so where it disagrees the file "
        "has no samples and is listed: ANVIL_HPRC's activities generate a parent's reads from the child's "
        "biosample."
    ),
)

SAMPLES_FROM_FILESET_SAMPLE_TABLE = SampleRule(
    id="samples_from_fileset_sample_table",
    module=RECONCILE_SAMPLES,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "at reconcile, the settled samples of the PLINK 2 .psam inference paired the file with "
        "(plink.filesets): the .psam in the file's own folder whose stem is the file's, for a .pgen, .pvar or .log; "
        "what it passes is decided as a step's parents' is"
    ),
    rationale=(
        "One plink2 --make-pgen writes a fileset's .pgen, .pvar, .psam and .log under one prefix, in one folder, "
        "and the .psam's rows are the samples whose genotypes the .pgen holds and whose variants the .pvar "
        "lists; the .log records the run that wrote them (#751). The samples are the .psam's rows, read from "
        "its content, and the folder and stem say whose they are. The .psam is no parent: the four files are "
        "written together, so no step is crossed. A .psam with none, or in conflict, passes nothing; the "
        "file's own sources and the .psam's settle as any two sources do."
    ),
)

EXTERNAL_SAMPLE_MAP_ROWS = SampleRule(
    id="external_sample_map_rows",
    module=SAMPLE_IDENTITY,
    source_type=SOURCE_EXTERNAL_GROUND_TRUTH,
    reads=(
        "the rows, at reconcile, of a GATK sample-name map held outside AnVIL for the dataset "
        "(sources/external_files.yaml): the sample name in each row's first column"
    ),
    rationale=(
        "A sample-name map's first column names the samples its import joint-called, as a catalog "
        "map's does (sample_map_rows, #668). A map whose every name is recognised names them; one with "
        "a name no identifier rule recognises names none. A workaround until AnVIL holds the map (#624)."
    ),
)

SAMPLE_RULES = (
    BAM_READ_GROUP_SAMPLES,
    VCF_SAMPLE_COLUMNS,
    SAMPLE_MAP_ROWS,
    FAST5_TRACKING_SAMPLE,
    TAR_CALLSET_SAMPLES,
    PSAM_SAMPLE_IDS,
    BCFTOOLS_STATS_SAMPLES,
    SAMPLES_INHERITED_FROM_PARENT,
    SAMPLES_FROM_ACTIVITY_BIOSAMPLE,
    SAMPLES_FROM_FILESET_SAMPLE_TABLE,
    EXTERNAL_SAMPLE_MAP_ROWS,
)

FAMILY_ID_AS_WRITTEN = EntityRule(
    id="family_id_as_written",
    module=RECONCILE_ENTITIES,
    source_type=SOURCE_REPOSITORY_METADATA,
    reads="a submitter table's family id column (a PED file's `familyid`), on the row naming the donor",
    sets=(FAMILY_ID,),
    rationale=(
        "A family id is a name for a group of relatives, with no vocabulary to translate it into, so the "
        "string is the answer as the source wrote it. It means something only among datasets sharing a "
        "numbering: HPRC and HPRC_R2 reuse 1000 Genomes' ids, and two sources writing different ids for "
        "one donor are a conflict, never a choice."
    ),
)

ANATOMICAL_SITE_AS_WRITTEN = EntityRule(
    id="anatomical_site_as_written",
    module=RECONCILE_ENTITIES,
    source_type=SOURCE_PUBLISHED_VALUE,
    reads="the repository's own record of a sample: AnVIL's `anvil_biosample.anatomical_site`",
    sets=(ANATOMICAL_SITE,),
    rationale=(
        "AnVIL's sites are not yet mapped to an ontology (#702), so the string is the answer as AnVIL wrote "
        "it; its `Unknown` names no site and makes no claim. A pooled sample's site is AnVIL's join of its "
        "members' (`Brain, Heart`), kept as one string until #702 makes the slot a list."
    ),
)

ENTITY_RULES = (FAMILY_ID_AS_WRITTEN, ANATOMICAL_SITE_AS_WRITTEN)

SGDP_SEX_AGREES = IdentityCheck(
    id="sgdp_sex_agrees",
    module=SGDP_ENTITIES,
    reads=(
        "SGDP's metadata file's `Gender` for the genome T2T_CHRY's `SGDP_*_sample` tables pair a sample with, "
        "and the tables' `karyotype` for the sample: M with XY, F with XX"
    ),
    rationale=(
        "The pairing of a sample with an SGDP genome rests on T2T_CHRY's tables alone; no file's header names "
        "the genome. Sex is the one fact both sides state about it, and a mislabelled row would disagree about "
        "half the time: 275 of 279 samples agree (#559)."
    ),
)

SGDP_GENOTYPE_MATCHES = IdentityCheck(
    id="sgdp_genotype_matches",
    module=SGDP_ENTITIES,
    reads=(
        "sources/sgdp_genotype_checks.yaml: a sample's chr22 gVCF genotypes compared with every genome of SGDP's "
        "and HGDP's public releases, recorded with the genome they match"
    ),
    rationale=(
        "Two genomes whose genotypes match are one person, whatever either side says about sex: of the nine "
        "samples measured by bcftools gtcheck, each matching pairing differed at 0-60 of 25,000-31,000 sites and "
        "every other genome at 1.98% of sites or more "
        "(docs/studies/sgdp-genome-identity.md, #718). The record is a measurement, not a source: it adds no "
        "value to a record. It confirms the pairing T2T_CHRY's table states, or, recording that the genotypes match "
        "another genome or none, leaves the sample out whatever its sex check says."
    ),
)

IDENTITY_CHECKS = (SGDP_SEX_AGREES, SGDP_GENOTYPE_MATCHES)

FETCH_FAILED = CodeMarker(
    id="fetch_failed",
    module=HEADER_CLASSIFIER,
    meaning=(
        "The file's content could not be read, so every dimension is not_classified (#293); a type whose "
        "dimensions come from its name keeps its answers from the name, the marker on the rest (#605)."
    ),
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
