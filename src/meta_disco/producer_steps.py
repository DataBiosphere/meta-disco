"""The step that made a VCF, read from the command lines in its own header (#609, #359).

A VCF header carries a line per program that touched the data, each read once, on first
use, by ``VCFHeader.commands`` into a **step** with inputs and an output (how a line is
read, and what each tool's arguments mean, is ``validators.command_lines``, #615).
Lines pile up: a file carries its first input's lines as well as its own, and GATK sorts
its lines, so neither the last line nor any one line's position says which step made the
file.

**The producing step is the end of the data flow.** Steps chain where one's output is
another's input, compared by base name with any ``.gz`` dropped (``chr1.genotyped.vcf``
is consumed as ``…/chr1.genotyped.vcf.gz``). An end is a step whose output no other step
consumes. An end whose output names a file other than this one did not make this file
(a ``GenomicsDBImport`` workspace whose consumer's line is not in the header), so it is
set aside, and exactly one end naming this file must remain. An end with no named output
(bcftools writing to stdout, GATK 3's ``HaplotypeCaller``) is taken only when it is the
one end of the flow: beside one set aside, nothing says it made this file rather than
that one. Otherwise the reader declines. Identical repeated lines are one step. A header
with a step the parse could not read (its tool undeclared) is declined: that step's
inputs and output are unknown, so the chain cannot be read.

**Which producing step is a step we write** is :data:`STEP_RULES`: a ``HaplotypeCaller``
with exactly one alignment input is a ``VariantCallActivity``, and a bcftools ``concat``
joining two or more VCFs is a ``MergeActivity`` with each input a ``shard`` (#610). Each
parent is found by file name within the child's dataset (#438's rule), and a step is
written only when every input names exactly one file there. Every other producing step
gives no step. Each file's outcome is one of :data:`OUTCOMES`, which the VCF producer
counts per dataset.

**A name several alignments carry is settled by their contigs** (#620). GATK refuses an
alignment with a contig its reference lacks or gives another length (unless the line turns
that check off, which no header we hold does), and writes that reference's contigs into the VCF as ``##contig``
lines. So where a ``HaplotypeCaller``'s input names several alignments of the dataset
(T2T's re-alignments of one sample to two references share a name), the parent is the
one whose every ``@SQ`` name and length is among the VCF's ``##contig`` names and
lengths, read from that alignment's own header: from the BAM producer's cache, or on a
miss fetched with samtools into it, as the BAM producer fetches it. The reader declines
as :data:`PARENT_AMBIGUOUS` when none or several fit, or when the VCF names no contig with
a length; and as :data:`PARENT_UNREADABLE` when a
candidate's header cannot be read or names no contig with a length (it may be the parent,
so no other is taken).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import code_rules, edges
from .code_rules import EdgeRule
from .fetchers import FetchError, fetch_bam_header
from .record_keys import RecordKey
from .validators.command_lines import BCFTOOLS, GATK, GATK3, Step
from .validators.header_extractors import VCFHeader
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


def steps_of(header: VCFHeader) -> list[Step] | None:
    """Every command line in a parsed VCF header as a step, or None if one is unread.

    Identical steps are kept once.
    """
    steps: list[Step] = []
    for command in header.commands:
        if not command.step.read:
            return None
        if command.step not in steps:
            steps.append(command.step)
    return steps


def data_name(path: str) -> str:
    """A path as a chain compares it: its base name, case-folded, less any ``.gz`` and GATK's ``gendb://``."""
    name = PurePosixPath(path.removeprefix("gendb://")).name.lower()
    return name.removesuffix(".gz")


def producing_step(header: VCFHeader, file_name: str) -> tuple[Step | None, str]:
    """The step in a VCF header that made ``file_name``, the one end of its data flow, and the outcome.

    See the module docstring for the rule. ``(step, STEPPED)``, or ``(None, reason)``:
    :data:`NO_COMMAND_LINE`, :data:`UNKNOWN_TOOL`, :data:`NO_SINGLE_END` or
    :data:`OUTPUT_NOT_THIS_FILE`.
    """
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
        """The alignment's contigs; None if its header cannot be read, or names none with a length."""
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


class HeaderSteps:
    """A run's reader of the step each VCF's header states, with what it resolves parents against.

    Built once per run from every loaded record (:meth:`for_run`), and called per file.
    It keeps only the records a rule in :data:`STEP_RULES` could take as a parent, and of
    each only what an edge reads and what reading its header takes (its md5 and any
    content URL), so the run's other records are not held.
    """

    def __init__(self, index: edges.NameIndex, key: RecordKey, contigs_of: Callable[[dict], Contigs | None]):
        self.index = index
        self.key = key
        self.contigs_of = contigs_of

    @classmethod
    def for_run(cls, records: Iterable[dict], key: RecordKey, evidence_base: Path, *, alignments: str) -> HeaderSteps:
        """The run's reader, reading an alignment's header from the cache ``alignments`` names under ``evidence_base``."""
        kinds = {rule.kind for rule in STEP_RULES.values()}

        def keep(name: str) -> bool:
            return edges.parent_kind_of(name) in kinds

        index = edges.parent_index(
            records, key, keep, "ground a header step's input on its parent", also=("file_md5sum", "url")
        )
        return cls(index, key, AlignmentContigs(evidence_base / alignments))

    def __call__(self, header: VCFHeader, file_name: str, dataset_id: str) -> tuple[dict | None, str]:
        """A VCF's ``generated_by`` from its header, and the outcome (one of :data:`OUTCOMES`).

        A producing step in :data:`STEP_RULES`, of a family its rule names, reading nothing
        from stdin, whose inputs are all of the kind its rule names (exactly one, or two or
        more where the rule takes several) gives that rule's step, each parent the one file of
        ``dataset_id`` carrying the input's base name, case-folded. A path listed twice is
        one input. An input no such file carries gives no step, as :data:`PARENT_NOT_FOUND`;
        otherwise an input several files carry, or two inputs at different paths with one
        name, give none, as :data:`PARENT_AMBIGUOUS` — except that, for a rule that settles a
        shared name by contigs, the one input's parent is the one carrier whose contigs fit
        the VCF's (:meth:`by_contigs`). Any other producing step gives none, as
        :data:`NO_ACTIVITY`.
        """
        step, outcome = producing_step(header, file_name)
        if step is None:
            return None, outcome
        rule = STEP_RULES.get(step.tool)
        if rule is None or step.family not in rule.families or step.stdin:
            return None, NO_ACTIVITY
        paths = list(dict.fromkeys(step.inputs))
        if not paths or (len(paths) > 1) != rule.many:
            return None, NO_ACTIVITY
        names = [PurePosixPath(path).name for path in paths]
        if any(edges.parent_kind_of(name) != rule.kind for name in names):
            return None, NO_ACTIVITY
        parents, outcome = resolve_names(self.index, dataset_id, names)
        if outcome == PARENT_AMBIGUOUS and rule.same_contigs:
            parents, outcome = self.by_contigs(header, dataset_id, names[0])
        if parents is None:
            return None, outcome
        return edges.generated_by(rule.edge_rule, parents, self.key), STEPPED

    def by_contigs(self, header: VCFHeader, dataset_id: str, name: str) -> tuple[list[dict] | None, str]:
        """The one file of ``dataset_id`` carrying ``name`` whose contigs fit the VCF's, and :data:`STEPPED`.

        A carrier fits where each of its contigs is among the VCF's, with the same length.
        ``(None, PARENT_UNREADABLE)`` where a carrier's contigs cannot be read; otherwise
        ``(None, PARENT_AMBIGUOUS)`` where the VCF names no contigs with lengths, or none or
        several carriers fit.
        """
        contigs = vcf_contigs(header)
        if contigs is None:
            return None, PARENT_AMBIGUOUS
        fits = []
        for carrier in edges.matches(self.index, dataset_id, name):
            read = self.contigs_of(carrier)
            if read is None:
                return None, PARENT_UNREADABLE
            if read <= contigs:
                fits.append(carrier)
        return ([fits[0]], STEPPED) if len(fits) == 1 else (None, PARENT_AMBIGUOUS)


def resolve_names(index: edges.NameIndex, dataset_id: str, names: list[str]) -> tuple[list[dict] | None, str]:
    """Each of ``names``' one file in ``dataset_id``, up to case, and :data:`STEPPED`; or None and why not.

    A name no file carries gives :data:`PARENT_NOT_FOUND`; otherwise a name several files
    carry, or two of ``names`` that are one name, give :data:`PARENT_AMBIGUOUS` (#438's rule).
    """
    found = [edges.matches(index, dataset_id, name) for name in names]
    if any(not parents for parents in found):
        return None, PARENT_NOT_FOUND
    # Two paths with one name (scatter shards all called `out.vcf.gz`) cannot be told
    # apart by name, so neither can be matched to a file.
    if len({name.lower() for name in names}) < len(names) or any(len(parents) > 1 for parents in found):
        return None, PARENT_AMBIGUOUS
    return [parents[0] for parents in found], STEPPED
