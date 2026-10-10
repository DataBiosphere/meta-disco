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
PRODUCER_STEPS = "src/meta_disco/producer_steps.py"
COHORT_STEPS = "src/meta_disco/cohort_steps.py"
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
_RECORDS_NOT_HEADER = (
    "Records, not the header: a header declaring structural-variant INFO fields (SVTYPE, SVLEN, CIPOS, "
    "CIEND, MATEID, IMPRECISE) says structural variants may appear, not that the file holds only them. "
    "1000G's SNV_INDEL_SV phased panels and phase 3 integrated callsets declare them and hold mostly "
    "SNVs and indels; Broad's known-indels resources carry them over from a 1000G phase 1 header and "
    "hold indels; NIA CARD's harmonized_variants name SVIM in their header and hold small-variant "
    "calls. "
)
_DECLARED_ONLY = (
    "Only what the caller declared makes an allele a structural variant (a symbolic ALT such as <DEL>, "
    "a breakend, or SVTYPE in the record's INFO), never its length: in 449 sampled callsets that are "
    "not structural, a 50 bp length test flagged 30 (CCDG recalibrated_variants, chr*.genotyped, 1kGP "
    "snp_indel, ClinVar), because small-variant callers write long indels too. "
)
_FIRST_RECORDS = (
    "Reading the first 100 records is a sampling trade-off, not a guarantee. The records need only tell "
    "a file of structural variants alone from one that is not: one small allele among them proves it is "
    "not, and an SV caller's file is expected to hold structural variants throughout, so its first "
    "records stand for the rest. The one known miss is a mixed file whose first 100 records "
    "are all declared structural variants, say an SV callset concatenated in front of a small-variant "
    "one without re-sorting; it would be labelled structural. Of 599 VCFs sampled for #630, none "
    "outside the SV callers' own files read as structural variants alone."
)
VCF_RECORDS_STRUCTURAL = CodeRule(
    id="vcf_records_structural",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads="VCF records: the ALT and INFO of the first records the head read",
    sets=("data_type",),
    rationale=(
        "Every variant allele counted in the records read is a structural variant its caller declared, "
        "one at least, so the file is structural variant calls. Alleles that are no variant (*, ., "
        "<NON_REF>, <*>) are not counted. " + _RECORDS_NOT_HEADER + _DECLARED_ONLY + _FIRST_RECORDS
    ),
)
VCF_RECORDS_SMALL_VARIANTS = CodeRule(
    id="vcf_records_small_variants",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header: its ##INFO declarations of structural-variant fields; and VCF records: the ALT "
        "and INFO of the first records the head read"
    ),
    sets=("data_type",),
    rationale=(
        "The header declares structural-variant INFO fields, but a record read holds a small variant "
        "(an SNV, indel or MNV its caller did not declare a structural variant), so the file is not "
        "structural variants alone: variants. It overrides an SV caller named in the header, as the "
        "records are read from the file itself. The header gate keeps this rule to files that say they "
        "may hold structural variants (203 of the 204,219 cached VCF heads when #630 measured), so a "
        "small-variant callset, gVCF or HaplotypeCaller file that declares none of those fields is not "
        "touched. " + _RECORDS_NOT_HEADER + _DECLARED_ONLY + _FIRST_RECORDS
    ),
)
_CALLER_KINDS = (
    "The caller calls one kind of variant, so its kind is the file's, looked up in "
    "rules/caller_kinds.yaml; a tool the table does not list gives no kind (#654). The records "
    "cannot settle it: a mixed callset shows a structural variant in its first records only by "
    "chance (#630). "
)
VCF_STEP_CALLER_KIND = CodeRule(
    id="vcf_step_caller_kind",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header: its command lines, as steps; the producing step (the end of their data flow), "
        "walked back through steps that keep the kind (SelectVariants, ApplyVQSR, ApplyRecalibration, "
        "bcftools view, norm, annotate) to the step that called the variants"
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
    reads="VCF header with no command line: its ##source lines and a ##DeepVariant_version line",
    sets=("variant_kind",),
    rationale=(
        _CALLER_KINDS + "Structural-variant callers (Sniffles, SVIM) and DeepVariant record "
        "themselves only so. Taken only where they name exactly one tool: a header naming two "
        "(SVIM-asm beside DeepVariant, in a concatenation of their calls) gives no kind."
    ),
)
VCF_MERGE_SMALL_CALLERS = CodeRule(
    id="vcf_merge_small_callers",
    module=HEADER_CLASSIFIER,
    basis=BASIS_CONTENT,
    source_type=SOURCE_CONTENT_READ,
    reads=(
        "VCF header whose caller is a merge (bcftools concat, merge): every caller its command lines "
        "and ##source lines name, and its ##INFO and ##ALT declarations of structural variants"
    ),
    sets=("variant_kind",),
    rationale=(
        "A merge holds what its inputs held. It is small variants where every caller the header names "
        "calls small variants and the header declares no structural-variant field: a merged header can "
        "lose an input's ##source line, but the VCF spec requires a structural variant to be declared, "
        "so an input's structural variants leave their declarations behind (#654)."
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
        "A container has no format of its own (#245), so it takes its contents'. A "
        "GenomicsDB member layout is a variant store (genomic, variants); otherwise the "
        "archive takes what the rules resolve for its dominant recognized member "
        "extension."
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
    ),
    rationale=(
        "A file whose rows are a sample name and a VCF path is a list of files, not their "
        "data (#621): its data_type is sample_map, and the six dimensions of the data do "
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
    VCF_RECORDS_STRUCTURAL,
    VCF_RECORDS_SMALL_VARIANTS,
    VCF_STEP_CALLER_KIND,
    VCF_SOURCE_CALLER_KIND,
    VCF_MERGE_SMALL_CALLERS,
    BED_COORDINATE_REFERENCE,
    BED_NONSTANDARD_CONTIGS,
    FASTA_TRANSCRIPT_CONTIGS,
    FASTA_REFERENCE_CONTIGS,
    FASTA_ASSEMBLER_CONTIGS,
    FASTA_MANY_CONTIGS,
    RGFA_STABLE_RANK_REFERENCE,
    TAR_INNER_FORMAT,
    SAMPLE_MAP_CONTENT,
    IDAT_CHIP_TYPE,
    IDAT_SCANNER,
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
        "VCF's ##contig names and lengths and each of those alignments' @SQ names and lengths"
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
        "its parent (#620)."
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
        "within the dataset"
    ),
    rationale=(
        "bcftools concat records its inputs in its own command line, written into the VCF it writes: "
        "T2T's chromosome VCFs name every region VCF they join. The step is taken only when it joins "
        "two or more VCFs, none read from stdin, and every input is a VCF that exactly one file of the "
        "dataset carries, so a merge never names part of its inputs (#610)."
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
        "dataset's sample maps"
    ),
    rationale=(
        "GenomicsDBImport writes its own command line into the workspace it builds, so the tar says "
        "which list of gVCFs it merged. The tar names the list, not each gVCF: one step per tar with "
        "3,202 inputs would be about 100M links, so the list is the input and its members' answers are "
        "read through it (#621). A workspace naming another directory than the tar, or given gVCFs one "
        "by one, gives no step."
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
        "base name matched case-insensitively within the dataset"
    ),
    rationale=(
        "A sample-name map lists the gVCFs one joint calling imports: it is the record of who was "
        "computed together. The paths are where the workflow ran, so only the name is matched. A file "
        "that is not such a list, or a member no file or two files of the dataset carry, gives no step: "
        "a cohort missing a member is not the cohort (#621)."
    ),
)

EDGE_RULES = (
    INDEX_BY_NAME,
    CHECKSUM_BY_NAME,
    VARIANT_CALL_BY_HEADER,
    MERGE_BY_HEADER,
    MERGE_BY_WORKSPACE_HEADER,
    COHORT_BY_SAMPLE_MAP,
)

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
