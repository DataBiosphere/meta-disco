"""The step that made a VCF, read from the command lines in its own header (#609, #359).

A VCF header carries a line per program that touched the data, each read once, on first
use, by ``VCFHeader.commands`` into a **step** with inputs and an output (how a line is
read, and what each tool's arguments mean, is ``validators.command_lines``, #615).
Lines pile up: a file carries its first input's lines as well as its own, and GATK sorts
its lines, so no line's position says which step made the file, with one exception for
bcftools (below, #771).

**The producing step is the end of the data flow.** Steps chain where one's output is
another's input, compared by base name with any ``.gz`` or ``.bgz`` dropped (``chr1.genotyped.vcf``
is consumed as ``…/chr1.genotyped.vcf.gz``). An end is a step whose output no other step
consumes. An end whose output names a file other than this one did not make this file
(a ``GenomicsDBImport`` workspace whose consumer's line is not in the header), so it is
set aside, and exactly one end naming this file must remain. An end with no named output
(bcftools writing to stdout, GATK 3's ``HaplotypeCaller``) is taken only when it is the
one end of the flow: beside one set aside, nothing says it made this file rather than
that one. Otherwise the reader declines. Identical repeated lines are one step. A header
with a step the parse could not read (its tool undeclared) is declined: that step's
inputs and output are unknown, so the chain cannot be read.

**Where the flow names no step, a bcftools view on the header's last line is taken** (#771):
for want of one end, or for a line it cannot read (:data:`LAST_LINE_AFTER`). Views writing to
stdout leave several unnamed ends, but bcftools appends its line and GATK and
Picard re-sort a header they rewrite, so a view on the last ``##`` line was the last step to write
it (:func:`last_line_view`). The one line whose position is read, and only where the end of the
flow (:func:`end_of_flow`) names no step; :func:`producing_step` gives either, for every reader; ``code_rules.VARIANT_SUBSET_BY_LAST_LINE`` states its assumptions.

**Which producing step is a step we write** is :data:`STEP_RULES`: a ``HaplotypeCaller``
with exactly one alignment input is a ``VariantCallActivity``, and a bcftools ``concat``
joining two or more VCFs is a ``MergeActivity`` with each input a ``shard`` (#610). A bcftools
``view`` of one VCF is a ``VariantSubsetActivity`` where its options keep samples or regions and a
``VariantFilterActivity`` where they test the calls, with the VCF ``processed`` (:func:`view_rule`). Each
parent is found by file name within the child's dataset (#438's rule), and a step is
written only when every input names exactly one file there. Every other producing step
gives no step. Each file's outcome is one of :data:`OUTCOMES`, which the VCF producer
counts per dataset.

**A name several alignments carry is settled by their contigs** (#620), on a GATK 4 line
(GATK 3's own check is not relied on). GATK 4 refuses an alignment with a contig its reference lacks or gives another length (unless the line turns
that check off, which no header we hold does), and writes that reference's contigs into the VCF as ``##contig``
lines. So where a ``HaplotypeCaller``'s input names several alignments of the dataset
(T2T's re-alignments of one sample to two references share a name), the parent is the
one whose every ``@SQ`` name and length is among the VCF's ``##contig`` names and
lengths, read from that alignment's own header: from the BAM header cache (``bam/``
under the run's evidence base), or on a miss fetched with samtools into it, as the BAM
producer fetches it. The reader declines
as :data:`PARENT_AMBIGUOUS` when none or several fit, or when the VCF names no contig or
any contig without a length; and as :data:`PARENT_UNREADABLE` when a candidate's header
cannot be read, or names no contig or any contig without a length (it may be the parent,
so no other is taken).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import code_rules, edges
from .code_rules import EdgeRule
from .fetchers import GZIP_SUFFIXES, FetchError, fetch_bam_header, fetch_vcf_header
from .plink import is_pvar
from .record_keys import RecordKey
from .validators.command_lines import BCFTOOLS, GATK, GATK3, Step
from .validators.header_extractors import VCFHeader, parse_vcf_head
from .validators.reference_builds import ContigSignature, observe_sam, observe_vcf_header

# Why a file got the step it did, or none. Counted per dataset by the VCF producer.
STEPPED = "stepped"
NO_COMMAND_LINE = "no_command_line"
UNKNOWN_TOOL = "unknown_tool"
NO_SINGLE_END = "no_single_end"
OUTPUT_NOT_THIS_FILE = "output_not_this_file"
NO_ACTIVITY = "no_activity"
PARENT_NOT_FOUND = "parent_not_found"
PARENT_AMBIGUOUS = "parent_ambiguous"
PARENT_UNREADABLE = "parent_unreadable"
# A view whose named parent's header, with the view's own lines added, is not this file's (#771,
# :func:`fits_parent`): another step came between, a later tool rewrote it, or it was cut short.
PARENT_HEADER_DIFFERS = "parent_header_differs"
# A PLINK 2 `.pvar` keeps the `##` command lines of the VCF it was converted from and adds
# none of its own, so its header never names the step that made it (#561).
NOT_A_VCF = "not_a_vcf"

OUTCOMES = (
    STEPPED,
    NO_COMMAND_LINE,
    UNKNOWN_TOOL,
    NO_SINGLE_END,
    OUTPUT_NOT_THIS_FILE,
    NO_ACTIVITY,
    PARENT_NOT_FOUND,
    PARENT_AMBIGUOUS,
    PARENT_UNREADABLE,
    PARENT_HEADER_DIFFERS,
    NOT_A_VCF,
)


@dataclass(frozen=True)
class StepRule:
    """A producing step we write: the edge rule that states it, the tool families it is read
    from, the kind (`edges.parent_kind_of`) every input must be, whether it takes several
    inputs (two or more: a merge of one file is not a merge) or exactly one, and whether a
    name several files carry is settled by which one's contigs fit the VCF's (#620)."""

    edge_rule: EdgeRule
    families: frozenset[str]
    kind: str
    many: bool = False
    same_contigs: bool = False

    def __post_init__(self):
        # A shared name is settled for a step's one input; of several, which carrier is which is unknown.
        if self.same_contigs and self.many:
            raise ValueError(
                f"{self.edge_rule.id}: a rule taking several inputs cannot settle a shared name by contigs"
            )


# The producing steps that are a step we write, by tool.
STEP_RULES: dict[str, StepRule] = {
    "HaplotypeCaller": StepRule(
        code_rules.VARIANT_CALL_BY_HEADER, frozenset({GATK, GATK3}), "alignment", same_contigs=True
    ),
    "concat": StepRule(code_rules.MERGE_BY_HEADER, frozenset({BCFTOOLS}), "variants", many=True),
}

# A bcftools view's options, by what they make of the one VCF it reads (#771). Subsetting keeps
# samples' columns or regions' rows whatever the calls are; filtering keeps the rows whose calls
# pass a test. The output options change only how the output is written, and ``--force-samples``
# only lets ``-S`` name samples the file lacks, so none changes which calls are kept. A view giving an option
# in none of these, both a subset and a filter option, or neither, gives no step.
VIEW_SUBSET_OPTIONS = frozenset(
    {"-s", "--samples", "-S", "--samples-file", "-r", "--regions", "-R", "--regions-file"}
    | {"-t", "--targets", "-T", "--targets-file"}
)
VIEW_FILTER_OPTIONS = frozenset(
    {"-f", "--apply-filters", "-i", "--include", "-e", "--exclude", "-c", "--min-ac", "-C", "--max-ac"}
    | {"-q", "--min-af", "-Q", "--max-af", "-v", "--types", "-V", "--exclude-types"}
    | {"-m", "--min-alleles", "-M", "--max-alleles", "-g", "--genotype", "-k", "--known", "-n", "--novel"}
    | {"-p", "--phased", "-P", "--exclude-phased", "-u", "--uncalled", "-U", "--exclude-uncalled"}
    | {"-x", "--private", "-X", "--exclude-private"}
)
VIEW_OUTPUT_OPTIONS = frozenset(
    {"-o", "--output", "-O", "--output-type", "--threads", "-W", "--write-index", "--no-version"}
    | {"-l", "--compression-level", "--force-samples"}
)
# The options of bcftools view's in ``command_lines.TOOL_ARGUMENTS`` that are neither a subset, a
# filter nor an output option (genotypes dropped, alleles trimmed, the header alone or none, INFO
# left as it was): declared here so each parser option has a stated effect; a view giving one gives no step.
VIEW_NO_STEP_OPTIONS = frozenset(
    {"-G", "--drop-genotypes", "-h", "--header-only", "-H", "--no-header", "-a", "--trim-alt-alleles"}
    | {"-A", "--trim-unseen-allele", "-I", "--no-update"}
)
# The view rules, (subset, filter), as the end of the flow found the view and as the last line did:
# their own ids, so the edges that rest on the last line's assumptions can be found (#771).
VIEW_RULES = (
    StepRule(code_rules.VARIANT_SUBSET_BY_HEADER, frozenset({BCFTOOLS}), "variants"),
    StepRule(code_rules.VARIANT_FILTER_BY_HEADER, frozenset({BCFTOOLS}), "variants"),
)
LAST_LINE_VIEW_RULES = (
    StepRule(code_rules.VARIANT_SUBSET_BY_LAST_LINE, frozenset({BCFTOOLS}), "variants"),
    StepRule(code_rules.VARIANT_FILTER_BY_LAST_LINE, frozenset({BCFTOOLS}), "variants"),
)
VIEWS = frozenset((*VIEW_RULES, *LAST_LINE_VIEW_RULES))
# Where :func:`end_of_flow` names no step, the outcomes after which the header's last line is read.
LAST_LINE_AFTER = frozenset({NO_SINGLE_END, UNKNOWN_TOOL})


def view_rule(step: Step, by_last_line: bool = False) -> StepRule | None:
    """The rule a bcftools ``view`` step is, by its options and whether the header's last line named it
    (:data:`LAST_LINE_VIEW_RULES`) or the end of the flow did (:data:`VIEW_RULES`); None for any other step, or a view
    whose options give both a subset and a filter, neither, or one in none of :data:`VIEW_SUBSET_OPTIONS`,
    :data:`VIEW_FILTER_OPTIONS` and :data:`VIEW_OUTPUT_OPTIONS` (as :data:`VIEW_NO_STEP_OPTIONS`'s are)."""
    if step.family != BCFTOOLS or step.tool != "view":
        return None
    options = set(step.options)
    if options - VIEW_SUBSET_OPTIONS - VIEW_FILTER_OPTIONS - VIEW_OUTPUT_OPTIONS:
        return None
    subset, filtered = bool(options & VIEW_SUBSET_OPTIONS), bool(options & VIEW_FILTER_OPTIONS)
    if subset == filtered:
        return None
    subset_rule, filter_rule = LAST_LINE_VIEW_RULES if by_last_line else VIEW_RULES
    return subset_rule if subset else filter_rule


def last_line_view(header: VCFHeader, file_name: str) -> Step | None:
    """The bcftools ``view`` on the header's last ``##`` line, where it made ``file_name``; else None.

    Only for a header read to a VCF's ``#CHROM`` line, one cut short having no last line, and
    never for a PLINK ``.pvar``, which keeps the lines of the VCF it was converted from. The view
    made the file where it names no output (stdout) or names this file, compared as
    :func:`data_name` compares a chain.
    """
    if is_pvar(file_name) or not header.vcf_columns or header.last_meta_line is None:
        return None
    command = next((c for c in header.commands if c.line == header.last_meta_line), None)
    if command is None:
        return None
    step = command.step
    if step.family != BCFTOOLS or step.tool != "view":
        return None
    if step.output is not None and data_name(step.output) != data_name(file_name):
        return None
    return step


def steps_of(header: VCFHeader) -> list[Step] | None:
    """Every command line in a parsed VCF header as a step, or None if one is unread.

    Identical steps are kept once; two alike but for their set of option names (``Step.options``,
    not compared) are two, so one view's options never stand for another's kind of view (#771).
    Two alike but for an option's value (``-S a.txt``, ``-S b.txt``) are one.
    """
    steps: list[Step] = []
    seen: set[tuple[Step, frozenset[str]]] = set()
    for command in header.commands:
        step = command.step
        if not step.read:
            return None
        if (step, frozenset(step.options)) not in seen:
            seen.add((step, frozenset(step.options)))
            steps.append(step)
    return steps


def data_name(path: str) -> str:
    """A path as a chain compares it: its base name, case-folded, less any ``.gz`` or ``.bgz`` and GATK's ``gendb://``."""
    name = PurePosixPath(path.removeprefix("gendb://")).name.lower()
    return name.removesuffix(".gz").removesuffix(".bgz")


def producing_step(header: VCFHeader, file_name: str) -> tuple[Step | None, str]:
    """The step in a VCF header that made ``file_name``, and the outcome: the one end of its data
    flow or, where that names none for an outcome in :data:`LAST_LINE_AFTER`, the bcftools view on
    its last ``##`` line (:func:`last_line_view`, #771).

    See the module docstring for the rule. ``(step, STEPPED)``, or ``(None, reason)``:
    :data:`NOT_A_VCF`, :data:`NO_COMMAND_LINE`, :data:`UNKNOWN_TOOL`, :data:`NO_SINGLE_END` or
    :data:`OUTPUT_NOT_THIS_FILE`, the end of the flow's outcome.
    """
    step, outcome, _ = found_step(header, file_name)
    return step, outcome


def found_step(header: VCFHeader, file_name: str) -> tuple[Step | None, str, bool]:
    """:func:`producing_step`'s step and outcome, and whether the header's last line named the step."""
    step, outcome = end_of_flow(header, file_name)
    if step is None and outcome in LAST_LINE_AFTER:
        view = last_line_view(header, file_name)
        if view is not None:
            return view, STEPPED, True
    return step, outcome, False


def end_of_flow(header: VCFHeader, file_name: str) -> tuple[Step | None, str]:
    """The one end of a VCF header's data flow that made ``file_name``, as :func:`producing_step` gives it before the last line is read."""
    if is_pvar(file_name):
        return None, NOT_A_VCF
    steps = steps_of(header)
    if steps is None:
        return None, UNKNOWN_TOOL
    if not steps:
        return None, NO_COMMAND_LINE
    # Consumed by another step: a recompression step's own input (`view -Oz -o x.vcf.gz x.vcf`)
    # shares its output's name less `.gz`, and does not make it consume itself.
    ends = [
        s
        for s in steps
        if s.output is None or data_name(s.output) not in {data_name(p) for o in steps if o is not s for p in o.inputs}
    ]
    this_file = data_name(file_name)
    named_here = [s for s in ends if s.output is not None and data_name(s.output) == this_file]
    unnamed = [s for s in ends if s.output is None]
    named_elsewhere = len(ends) - len(named_here) - len(unnamed)
    if len(named_here) == 1 and not unnamed:
        return named_here[0], STEPPED
    # An end with no named output is taken only when it is the one end: beside an end set
    # aside for naming another file, nothing says it made this file rather than that one.
    if len(unnamed) == 1 and not named_here and not named_elsewhere:
        return unnamed[0], STEPPED
    return None, OUTPUT_NOT_THIS_FILE if ends and not named_here and not unnamed else NO_SINGLE_END


# A sequence dictionary: each sequence's name and length, as a VCF's ``##contig`` lines or an
# alignment's ``@SQ`` lines state it.
Contigs = frozenset[tuple[str, int]]


def vcf_contigs(header: VCFHeader) -> Contigs | None:
    """A VCF header's ``##contig`` names and lengths, as ``reference_builds`` reads them; None if
    it names none, or one without a length."""
    return _contigs(observe_vcf_header(header)[0])


def sam_contigs(header_text: str) -> Contigs | None:
    """A SAM header's ``@SQ`` names and lengths, as ``reference_builds`` reads them; None if it
    names none, or one without a length."""
    return _contigs(observe_sam(header_text)[0])


def _contigs(signatures: list[ContigSignature]) -> Contigs | None:
    contigs: set[tuple[str, int]] = set()
    for signature in signatures:
        if signature.length is None:
            return None
        contigs.add((signature.name, signature.length))
    return frozenset(contigs) or None


class AlignmentContigs:
    """Each alignment's ``@SQ`` contigs, read once per file in a run: from the BAM producer's cache,
    or on a miss fetched with samtools into it (``fetch_bam_header``).

    Called from the VCF producer's worker threads, so reads are made one at a time under a
    lock: a sample's gVCFs (one per chromosome) all ask after the same alignments.
    """

    def __init__(self, evidence_dir: Path):
        self.evidence_dir = evidence_dir
        self._read: dict[str, Contigs | None] = {}
        self._lock = threading.Lock()

    def __call__(self, record: dict) -> Contigs | None:
        """The alignment's contigs; None if its header cannot be read, or names no contig or any without a length."""
        md5 = record["file_md5sum"]
        with self._lock:
            if md5 not in self._read:
                try:
                    text = fetch_bam_header(
                        self.evidence_dir, md5, file_name=record["file_name"], url=record.get("url")
                    )
                except FetchError:
                    self._read[md5] = None
                else:
                    self._read[md5] = sam_contigs(text)
            return self._read[md5]


VIEW_COMMAND_LINE = "##bcftools_viewCommand="
VIEW_VERSION_LINE = "##bcftools_viewVersion="


def fits_parent(child: VCFHeader, parent: VCFHeader, made_by: Step | None = None) -> bool:
    """Whether ``child``'s header is ``parent``'s with one bcftools view's own lines added, and its samples are among the parent's.

    False for a child whose header was not read to a VCF's ``#CHROM`` line (cut short), or a parent with no ``#CHROM`` line.

    What a bcftools view of ``parent`` writes (#771): every contig, INFO, FORMAT, ALT, reference
    and ``##source`` line as the parent has it, and the parent's other ``##`` lines, with exactly
    one view command line added and, on bcftools' first pass, its version line. Its FILTER lines
    are compared less ``PASS``, which htslib writes in its own words, and ``##fileformat`` is not
    compared: bcftools writes its own. A header another step wrote between the parent and the
    view (a ``norm`` of a file of the parent's name) adds that step's line, and does not fit. Where
    ``made_by`` is given, the one view line added must be that step (its inputs, output and option
    names), so a view line the parent's header already held never stands for the one that made the child.
    """
    if not child.vcf_columns or child.sample_columns is None or parent.sample_columns is None:
        return False
    if not set(child.sample_columns) <= set(parent.sample_columns):
        return False
    same = (
        child.contig_lines == parent.contig_lines
        and child.info_fields == parent.info_fields
        and child.format_fields == parent.format_fields
        and child.alt_fields == parent.alt_fields
        and child.reference == parent.reference
        and child.sources == parent.sources
        and child.unkeyed_meta == parent.unkeyed_meta
        and _filters(child) == _filters(parent)
    )
    child_other, parent_other = set(child.other_meta or ()), set(parent.other_meta or ())
    added = child_other - parent_other
    views = [x for x in added if x.startswith(VIEW_COMMAND_LINE)]
    return (
        same
        and parent_other <= child_other
        and len(views) == 1
        and all(x.startswith((VIEW_COMMAND_LINE, VIEW_VERSION_LINE)) for x in added)
        and (made_by is None or _is_step(child, views[0], made_by))
    )


def _is_step(header: VCFHeader, line: str, step: Step) -> bool:
    """Whether the command ``header`` read from ``line`` is ``step``, its option names included."""
    command = next((c for c in header.commands if c.line == line), None)
    return command is not None and command.step == step and set(command.step.options) == set(step.options)


def _filters(header: VCFHeader) -> list:
    return [f for f in header.filter_fields or () if f.fields.get("ID") != "PASS"]


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


class ParentHeaders:
    """Each VCF parent's header, read once per file in a run: from the VCF producer's cache, or on a
    miss fetched into it (``fetch_vcf_header``), under a lock, as :class:`AlignmentContigs` reads alignments."""

    def __init__(self, evidence_dir: Path):
        self.evidence_dir = evidence_dir
        self._read: dict[str, VCFHeader | None] = {}
        self._lock = threading.Lock()

    def __call__(self, record: dict) -> VCFHeader | None:
        """The parent's parsed header; None if it cannot be read."""
        md5 = record["file_md5sum"]
        with self._lock:
            if md5 not in self._read:
                name = record["file_name"]
                try:
                    head = fetch_vcf_header(
                        self.evidence_dir,
                        md5,
                        file_name=name,
                        is_gzipped=any(
                            n.lower().endswith(GZIP_SUFFIXES) for n in (name, _text(record.get("file_format")))
                        ),
                        url=record.get("url"),
                    )
                except FetchError:
                    self._read[md5] = None
                else:
                    self._read[md5] = parse_vcf_head(head)
            return self._read[md5]


class HeaderSteps:
    """A run's reader of the step each VCF's header states, with what it resolves parents against.

    Built once per run from every loaded record (:meth:`for_run`), and called per file.
    It keeps only the records a rule in :data:`STEP_RULES`, or a view's, could take as a parent, and of
    each only what an edge reads and what reading its header takes (its md5 and any
    content URL), so the run's other records are not held.
    """

    def __init__(
        self,
        index: edges.NameIndex,
        key: RecordKey,
        contigs_of: Callable[[dict], Contigs | None],
        header_of: Callable[[dict], VCFHeader | None],
    ):
        self.index = index
        self.key = key
        self.contigs_of = contigs_of
        self.header_of = header_of

    @classmethod
    def for_run(
        cls, records: Iterable[dict], key: RecordKey, evidence_base: Path, *, alignments: str, variants: str
    ) -> HeaderSteps:
        """The run's reader, reading an alignment's header from the cache ``alignments`` names under
        ``evidence_base``, and a VCF parent's from the one ``variants`` names."""
        kinds = {rule.kind for rule in (*STEP_RULES.values(), *VIEW_RULES, *LAST_LINE_VIEW_RULES)}

        def keep(name: str) -> bool:
            return edges.parent_kind_of(name) in kinds

        index = edges.parent_index(
            records, key, keep, "ground a header step's input on its parent", also=("file_md5sum", "url", "file_format")
        )
        return cls(index, key, AlignmentContigs(evidence_base / alignments), ParentHeaders(evidence_base / variants))

    def __call__(
        self, header: VCFHeader, file_name: str, dataset_id: str, folder: str | None
    ) -> tuple[dict | None, str]:
        """A VCF's ``generated_by`` from its header, and the outcome (one of :data:`OUTCOMES`).

        A producing step (:func:`producing_step`) in :data:`STEP_RULES`, or a ``view`` that :func:`view_rule`
        names a rule for, of a family its rule names, reading nothing
        from stdin, whose inputs are all of the kind its rule names (exactly one, or two or
        more where the rule takes several) gives that rule's step, each parent the one file of
        ``dataset_id`` carrying the input's base name, case-folded, as ``edges.matches``
        settles it by the VCF's ``folder``. A path listed twice is
        one input. An input no such file carries gives no step, as :data:`PARENT_NOT_FOUND`;
        otherwise an input several files carry, or two inputs at different paths with one
        name, give none, as :data:`PARENT_AMBIGUOUS` — except that, for a rule that settles a
        shared name by contigs, a GATK 4 line's one input's parent is the one carrier whose
        contigs fit the VCF's (:meth:`by_contigs`). Any other producing step gives none, as
        :data:`NO_ACTIVITY`, as does an input named as this file. A view is written only where its
        parent's header fits (:func:`fits_parent`), whether the end of the flow or the last line named
        it: as :data:`PARENT_UNREADABLE` where the parent's header cannot be read, or was not read to
        its ``#CHROM`` line, as :data:`PARENT_HEADER_DIFFERS` where it does not fit (this file's own
        header cut short among the ways). A step a lifting tool wrote no line for
        leaves its header's contigs and reference other than its parent's.
        """
        step, outcome, by_last_line = found_step(header, file_name)
        if step is None:
            return None, outcome
        rule = view_rule(step, by_last_line) or STEP_RULES.get(step.tool)
        if rule is None or step.family not in rule.families or step.stdin:
            return None, NO_ACTIVITY
        paths = list(dict.fromkeys(step.inputs))
        if not paths or (len(paths) > 1) != rule.many:
            return None, NO_ACTIVITY
        names = [PurePosixPath(path).name for path in paths]
        if any(edges.parent_kind_of(name) != rule.kind for name in names):
            return None, NO_ACTIVITY
        # An input of this file's own name (a copy from another folder) would resolve, as parents
        # resolve, to the file itself: a parent of its own, which stops reconcile.
        if any(name.lower() == PurePosixPath(file_name).name.lower() for name in names):
            return None, NO_ACTIVITY
        # GATK 4 refuses an alignment with a contig its reference lacks; GATK 3's check is
        # not relied on (it may accept a partial overlap), so its lines keep the name rule.
        # Where the contigs can settle a shared name they do, before the folder: content
        # outranks the storage layout, which only breaks a tie the contigs leave (#717).
        by_content = rule.same_contigs and step.family == GATK
        parents, outcome = resolve_names(self.index, dataset_id, names, None if by_content else folder)
        if outcome == PARENT_AMBIGUOUS and by_content:
            parents, outcome = self.by_contigs(header, dataset_id, names[0], folder)
        if parents is None:
            return None, outcome
        if rule in VIEWS:
            parent = self.header_of(parents[0])
            if parent is None or not parent.vcf_columns:
                return None, PARENT_UNREADABLE
            if not fits_parent(header, parent, made_by=step):
                return None, PARENT_HEADER_DIFFERS
        return edges.generated_by(rule.edge_rule, parents, self.key), STEPPED

    def by_contigs(
        self, header: VCFHeader, dataset_id: str, name: str, folder: str | None
    ) -> tuple[list[dict] | None, str]:
        """The one file of ``dataset_id`` carrying ``name`` whose contigs fit the VCF's, and :data:`STEPPED`.

        A carrier fits where each of its contigs is among the VCF's, with the same length;
        where several fit, the one of them in the VCF's ``folder`` is taken (``edges.in_folder``).
        ``(None, PARENT_AMBIGUOUS)`` where the VCF names no contig or any contig without a
        length (no carrier is then read); otherwise ``(None, PARENT_UNREADABLE)`` where a
        carrier's header cannot be read, or names no contig or any contig without a length;
        otherwise ``(None, PARENT_AMBIGUOUS)`` where none fit, or several do and the folder
        does not settle them.
        """
        contigs = vcf_contigs(header)
        if contigs is None:
            return None, PARENT_AMBIGUOUS
        fits = []
        for carrier in edges.matches(self.index, dataset_id, name, None):
            read = self.contigs_of(carrier)
            if read is None:
                return None, PARENT_UNREADABLE
            if read <= contigs:
                fits.append(carrier)
        fits = edges.in_folder(fits, folder)
        return ([fits[0]], STEPPED) if len(fits) == 1 else (None, PARENT_AMBIGUOUS)


def resolve_names(
    index: edges.NameIndex, dataset_id: str, names: list[str], folder: str | None
) -> tuple[list[dict] | None, str]:
    """Each of ``names``' one file in ``dataset_id``, up to case, and :data:`STEPPED`; or None and why not.

    Each name's files are those :func:`edges.matches` gives with the child's ``folder`` (#717).

    A name no file carries gives :data:`PARENT_NOT_FOUND`; otherwise a name several files
    carry, or two of ``names`` that are one name, give :data:`PARENT_AMBIGUOUS` (#438's rule).
    """
    found = [edges.matches(index, dataset_id, name, folder) for name in names]
    if any(not parents for parents in found):
        return None, PARENT_NOT_FOUND
    # Two paths with one name (scatter shards all called `out.vcf.gz`) cannot be told
    # apart by name, so neither can be matched to a file.
    if len({name.lower() for name in names}) < len(names) or any(len(parents) > 1 for parents in found):
        return None, PARENT_AMBIGUOUS
    return [parents[0] for parents in found], STEPPED


class NameStepReader:
    """A run's reader of a step whose parents a file's own content names (``cohort_steps``, #621;
    ``bcftools_stats``, #683): the name index its parents resolve in, built once per run from every
    loaded record (:meth:`for_run`), keeping the records :meth:`keeps` takes (a subclass may keep
    more, as ``cohort_steps.TarSteps`` keeps the gVCFs a rebuilt list could name), and called per file."""

    PURPOSE = "ground a step's input on its parent"

    def __init__(self, index: edges.NameIndex, key: RecordKey):
        self.index = index
        self.key = key

    @staticmethod
    def keeps(name: str) -> bool:
        raise NotImplementedError

    @classmethod
    def for_run(cls, records: Iterable[dict], key: RecordKey, evidence_base: Path):
        # ``evidence_base`` is every step reader's third argument; these read no other file's content.
        return cls(edges.parent_index(records, key, cls.keeps, cls.PURPOSE), key)

    def step(self, rule: EdgeRule, paths: list[str], dataset_id: str, folder: str | None) -> tuple[dict | None, str]:
        """``rule``'s step with each of ``paths``' base names an input, and :data:`STEPPED`; or None and why not.

        Each base name resolves as :func:`resolve_names` settles it, by the child's ``folder``.
        """
        names = [PurePosixPath(path).name for path in paths]
        parents, outcome = resolve_names(self.index, dataset_id, names, folder)
        if parents is None:
            return None, outcome
        return edges.generated_by(rule, parents, self.key), STEPPED
