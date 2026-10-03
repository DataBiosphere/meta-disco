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
with exactly one alignment input is a ``VariantCallActivity``, its parent found by file
name within the child's dataset (#438's rule). Every other producing step gives no step
yet (#610). Each file's outcome is one of :data:`OUTCOMES`, which the VCF producer counts
per dataset.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath

from . import code_rules, edges
from .code_rules import EdgeRule
from .record_keys import RecordKey, input_key_value
from .records import dataset_of
from .validators.command_lines import Step
from .validators.header_extractors import VCFHeader

# Why a file got the step it did, or none. Counted per dataset by the VCF producer.
STEPPED = "stepped"
NO_COMMAND_LINE = "no_command_line"
UNKNOWN_TOOL = "unknown_tool"
NO_SINGLE_END = "no_single_end"
OUTPUT_NOT_THIS_FILE = "output_not_this_file"
NO_ACTIVITY = "no_activity"
PARENT_NOT_FOUND = "parent_not_found"
PARENT_AMBIGUOUS = "parent_ambiguous"
OUTCOMES = (
    STEPPED,
    NO_COMMAND_LINE,
    UNKNOWN_TOOL,
    NO_SINGLE_END,
    OUTPUT_NOT_THIS_FILE,
    NO_ACTIVITY,
    PARENT_NOT_FOUND,
    PARENT_AMBIGUOUS,
)

# The producing steps that are a step we write: the tool, the edge rule that states it,
# and the kind (`edges.parent_kind_of`) its one input must be. Any family of the tool.
STEP_RULES: dict[str, tuple[EdgeRule, str]] = {
    "HaplotypeCaller": (code_rules.VARIANT_CALL_BY_HEADER, "alignment"),
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


class HeaderSteps:
    """A run's reader of the step each VCF's header states, with what it resolves parents against.

    Built once per run from every loaded record (:meth:`for_run`), and called per file.
    It keeps only the records a rule in :data:`STEP_RULES` could take as a parent, and of
    each only what an edge reads, so the run's other records are not held.
    """

    def __init__(self, index: edges.NameIndex, key: RecordKey):
        self.index = index
        self.key = key

    @classmethod
    def for_run(cls, records: Iterable[dict], key: RecordKey) -> HeaderSteps:
        kinds = {kind for _, kind in STEP_RULES.values()}
        # Each kept record's key is checked here, so a drifted one stops the run before
        # any file is classified, rather than failing the VCF whose parent it turns out to be.
        parents = (
            {
                "file_name": r["file_name"],
                key.input_field: input_key_value(r, key, "ground a header step's input on its parent"),
                "dataset_id": dataset_of(r),
            }
            for r in records
            if isinstance(r.get("file_name"), str) and edges.parent_kind_of(r["file_name"]) in kinds
        )
        return cls(edges.files_by_folded_name(parents), key)

    def __call__(self, header: VCFHeader, file_name: str, dataset_id: str) -> tuple[dict | None, str]:
        """A VCF's ``generated_by`` from its header, and the outcome (one of :data:`OUTCOMES`).

        A producing step in :data:`STEP_RULES` with exactly one input of the kind its rule
        names gives that rule's step, its parent the one file of ``dataset_id`` carrying the
        input's base name, case-folded. None or several such files give no step. Any other
        producing step gives none either, as :data:`NO_ACTIVITY`.
        """
        step, outcome = producing_step(header, file_name)
        if step is None:
            return None, outcome
        rule = STEP_RULES.get(step.tool)
        if rule is None or len(step.inputs) != 1:
            return None, NO_ACTIVITY
        edge_rule, kind = rule
        parent_name = PurePosixPath(step.inputs[0]).name
        if edges.parent_kind_of(parent_name) != kind:
            return None, NO_ACTIVITY
        parents = edges.matches(self.index, dataset_id, parent_name)
        if len(parents) != 1:
            return None, PARENT_NOT_FOUND if not parents else PARENT_AMBIGUOUS
        return edges.generated_by(edge_rule, parents[0], self.key), STEPPED
