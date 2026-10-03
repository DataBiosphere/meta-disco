"""The step that made a VCF, read from the command lines in its own header (#609, #359).

A VCF header carries a line per program that touched the data: GATK writes
``##GATKCommandLine``, bcftools ``##bcftools_<subcommand>Command``, and other tools other
``##…command…=`` keys, all found by ``header_extractors.vcf_commands``. Each line is a
**step** with inputs and an output. Lines pile up: a file carries its first input's lines
as well as its own, and GATK sorts its lines, so neither the last line nor any one line's
position says which step made the file.

**The producing step is the end of the data flow.** Steps chain where one's output is
another's input, compared by base name with any ``.gz`` dropped (``chr1.genotyped.vcf``
is consumed as ``…/chr1.genotyped.vcf.gz``). An end is a step whose output no other step
consumes. An end whose output names a file other than this one did not make this file
(a ``GenomicsDBImport`` workspace whose consumer's line is not in the header), so it is
set aside, and exactly one end naming this file must remain. An end with no named output
(bcftools writing to stdout, GATK 3's ``HaplotypeCaller``) is taken only when it is the
one end of the flow: beside one set aside, nothing says it made this file rather than
that one. Otherwise the reader declines. Identical repeated lines are one step.

**What a tool's arguments mean is declared once**, in :data:`TOOL_ARGUMENTS`, about tools
and not datasets: which options name an input, which the output, and for a tool that
takes its inputs as positional arguments, which options take no value. A header with a
command line whose tool is not declared there is declined: an undeclared step's inputs
and output cannot be read, so the chain cannot be.

**Only what the tool wrote is read.** A command line is the tool recording its own
invocation; the values another program carried into it (bwa's ``-R`` read group, say)
are not read here (contract 3.13).

**Which producing step is a step we write** is :data:`STEP_RULES`: a ``HaplotypeCaller``
with exactly one alignment input is a ``VariantCallActivity``, its parent found by file
name within the child's dataset (#438's rule). Every other producing step gives no step
yet (#610). Each file's outcome is one of :data:`OUTCOMES`, which the VCF producer counts
per dataset.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from . import code_rules, edges
from .code_rules import EdgeRule
from .pipeline import RecordKey, input_key_value
from .records import dataset_of
from .validators.header_extractors import VcfCommand, split_command_line, vcf_commands_in_text

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

GATK = "gatk"
GATK3 = "gatk3"
BCFTOOLS = "bcftools"


@dataclass(frozen=True)
class ToolArguments:
    """Which of a tool's arguments name its data inputs and its output.

    ``inputs`` and ``outputs`` are option names whose value is a file (GATK 3's are its
    ``key=value`` keys). ``positional`` marks a tool whose inputs are its positional
    arguments; ``no_value`` then lists the options that take no value, so a positional
    argument is told from an option's value. An option not in ``no_value`` is read as
    taking one.
    """

    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    positional: bool = False
    no_value: frozenset[str] = field(default_factory=frozenset)


_GATK_VARIANTS = ToolArguments(inputs=("-V", "--variant"), outputs=("-O", "--output"))

# Keyed by (family, tool). The tools are the ones the corpus's VCF headers carry
# (measured 2026-10-03 over the cached headers): GATK 4 and 3, and the bcftools
# subcommands the T2T joint-calling files carry. Anything else declines.
TOOL_ARGUMENTS: dict[tuple[str, str], ToolArguments] = {
    (GATK, "HaplotypeCaller"): ToolArguments(inputs=("-I", "--input"), outputs=("-O", "--output")),
    (GATK, "SelectVariants"): _GATK_VARIANTS,
    (GATK, "ApplyVQSR"): _GATK_VARIANTS,
    (GATK, "GenotypeGVCFs"): _GATK_VARIANTS,
    (GATK, "CombineGVCFs"): _GATK_VARIANTS,
    (GATK, "GenomicsDBImport"): ToolArguments(
        inputs=("-V", "--variant", "--sample-name-map"), outputs=("--genomicsdb-workspace-path",)
    ),
    (GATK3, "HaplotypeCaller"): ToolArguments(inputs=("input_file",), outputs=("out",)),
    (GATK3, "GenotypeGVCFs"): ToolArguments(inputs=("variant",), outputs=("out",)),
    (GATK3, "CombineGVCFs"): ToolArguments(inputs=("variant",), outputs=("out",)),
    (BCFTOOLS, "concat"): ToolArguments(
        inputs=("-f", "--file-list"),
        outputs=("-o", "--output"),
        positional=True,
        no_value=frozenset(
            {"-a", "--allow-overlaps", "-c", "--compact-PS", "-D", "--remove-duplicates", "-l", "--ligate"}
            | {"-n", "--naive", "--naive-force", "--no-version", "-W", "--write-index"}
        ),
    ),
    (BCFTOOLS, "view"): ToolArguments(
        outputs=("-o", "--output"),
        positional=True,
        no_value=frozenset(
            {"-G", "--drop-genotypes", "-h", "--header-only", "-H", "--no-header", "--no-version"}
            | {"-a", "--trim-alt-alleles", "-A", "--trim-unseen-allele", "-I", "--no-update"}
            | {"-k", "--known", "-n", "--novel", "-p", "--phased", "-P", "--exclude-phased"}
            | {"-u", "--uncalled", "-U", "--exclude-uncalled", "-x", "--private", "-X", "--exclude-private"}
            | {"--force-samples", "-W", "--write-index"}
        ),
    ),
}

# The producing steps that are a step we write: the tool, the edge rule that states it,
# and the kind (`edges.parent_kind_of`) its one input must be. Any family of the tool.
STEP_RULES: dict[str, tuple[EdgeRule, str]] = {
    "HaplotypeCaller": (code_rules.VARIANT_CALL_BY_HEADER, "alignment"),
}


@dataclass(frozen=True)
class Step:
    """One command line: the tool, its inputs and its output, each a path as the line wrote it.

    ``output`` is None where the tool wrote to stdout (bcftools with no ``-o``) or the
    line names no single output (GATK 3's HaplotypeCaller names none).
    """

    family: str
    tool: str
    inputs: tuple[str, ...]
    output: str | None


_BCFTOOLS_KEY = re.compile(r"^bcftools_(\w+)Command$")
_GATK3_PAIR = re.compile(r"\b([\w.]+)=(\[[^\]]*\]|\S+)")
_GATK3_SOURCE = re.compile(r"source=([^\s)]+)")


def steps_of(header_text: str) -> list[Step] | None:
    """Every command line in a VCF header as a step, or None if one names an undeclared tool.

    Identical steps are kept once.
    """
    steps: list[Step] = []
    for command in vcf_commands_in_text(header_text):
        step = _step(command)
        if step is None:
            return None
        if step not in steps:
            steps.append(step)
    return steps


def _step(command: VcfCommand) -> Step | None:
    """One command line as a step, or None if its tool is not in :data:`TOOL_ARGUMENTS`."""
    if command.key.lower().startswith("gatkcommandline"):
        if command.options_form:
            return _gatk3_step(command)
        tool = command.tool_id or ""
        arguments = TOOL_ARGUMENTS.get((GATK, tool))
        # The attribute is a quoted string, so a quote inside the command is written `\"`.
        words = split_command_line(command.text.replace('\\"', '"'))
        return None if arguments is None else _option_step(GATK, tool, words, arguments)
    if bcftools := _BCFTOOLS_KEY.match(command.key):
        subcommand = bcftools.group(1)
        arguments = TOOL_ARGUMENTS.get((BCFTOOLS, subcommand))
        words = split_command_line(command.text.split("; Date=", 1)[0])
        return None if arguments is None else _option_step(BCFTOOLS, subcommand, words, arguments)
    return None


def _gatk3_step(command: VcfCommand) -> Step | None:
    """A GATK 3 ``CommandLineOptions="key=value …"`` line as a step."""
    pairs = dict(_GATK3_PAIR.findall(command.text))
    tool = pairs.get("analysis_type") or command.tool_id or ""
    arguments = TOOL_ARGUMENTS.get((GATK3, tool))
    if arguments is None:
        return None
    inputs = tuple(p for key in arguments.inputs for p in _gatk3_values(pairs.get(key)))
    outputs = [p for key in arguments.outputs for p in _gatk3_values(pairs.get(key))]
    return Step(GATK3, tool, inputs, _sole(outputs))


def _gatk3_values(value: str | None) -> list[str]:
    """The paths in one GATK 3 option value: ``[a, b]`` or a bare value; none for null or GATK's writer stub."""
    if value is None or value in ("null", "[]"):
        return []
    items = value[1:-1].split(",") if value.startswith("[") else [value]
    paths = []
    for item in (i.strip() for i in items):
        # A RodBinding reads `(RodBinding name=variant source=/path/x.g.vcf.gz)`.
        source = _GATK3_SOURCE.search(item)
        path = source.group(1) if source else item
        if path and not path.startswith("org.broadinstitute."):
            paths.append(path)
    return paths


def _option_step(family: str, tool: str, words: list[str], arguments: ToolArguments) -> Step:
    """A step from a command's words, read through ``arguments``.

    A leading word naming the tool itself (GATK 4 writes it; bcftools repeats its
    subcommand) is skipped. A value is the word after its option, or the part after
    ``=`` in ``--option=value``.
    """
    if words and words[0] == tool:
        words = words[1:]
    inputs: list[str] = []
    outputs: list[str] = []
    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        if not word.startswith("-") or word == "-":
            # A positional argument; `-` is stdin, which names no file.
            if arguments.positional and word != "-":
                inputs.append(word)
            continue
        if word.startswith("--") and "=" in word:
            option, value = word.split("=", 1)
        elif word in arguments.no_value:
            continue
        elif arguments.positional and not word.startswith("--") and len(word) > 2:
            # A short option with its value attached, as bcftools writes `-Oz` or `-Wtbi`.
            option, value = word[:2], word[2:]
        else:
            option, value = word, words[i] if i < len(words) else None
            i += 1
        if value is not None and option in arguments.inputs:
            inputs.append(value)
        elif value is not None and option in arguments.outputs:
            outputs.append(value)
    return Step(family, tool, tuple(inputs), _sole(outputs))


def _sole(paths: list[str]) -> str | None:
    """The one path, or None for none or several: a step naming two outputs names no output."""
    return paths[0] if len(paths) == 1 else None


def data_name(path: str) -> str:
    """A path as a chain compares it: its base name, case-folded, less any ``.gz`` and GATK's ``gendb://``."""
    name = PurePosixPath(path.removeprefix("gendb://")).name.lower()
    return name.removesuffix(".gz")


def producing_step(header_text: str, file_name: str) -> tuple[Step | None, str]:
    """The step in a VCF header that made ``file_name``, the one end of its data flow, and the outcome.

    See the module docstring for the rule. ``(step, STEPPED)``, or ``(None, reason)``:
    :data:`NO_COMMAND_LINE`, :data:`UNKNOWN_TOOL`, :data:`NO_SINGLE_END` or
    :data:`OUTPUT_NOT_THIS_FILE`.
    """
    steps = steps_of(header_text)
    if steps is None:
        return None, UNKNOWN_TOOL
    if not steps:
        return None, NO_COMMAND_LINE
    consumed = {data_name(p) for s in steps for p in s.inputs}
    ends = [s for s in steps if s.output is None or data_name(s.output) not in consumed]
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

    def __call__(self, header_text: str, file_name: str, dataset_id: str) -> tuple[dict | None, str]:
        """A VCF's ``generated_by`` from its header, and the outcome (one of :data:`OUTCOMES`).

        A producing step in :data:`STEP_RULES` with exactly one input of the kind its rule
        names gives that rule's step, its parent the one file of ``dataset_id`` carrying the
        input's base name, case-folded. None or several such files give no step. Any other
        producing step gives none either, as :data:`NO_ACTIVITY`.
        """
        step, outcome = producing_step(header_text, file_name)
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
