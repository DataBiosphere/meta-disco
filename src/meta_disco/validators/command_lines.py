"""The command lines a VCF header records, each read once into its words and its step (#615).

A VCF header carries a line per program that touched the data: GATK writes
``##GATKCommandLine``, bcftools ``##bcftools_<subcommand>Command``, and other tools other
``##…command…=`` keys, all found by :func:`vcf_commands`. ``VCFHeader.commands`` reads
them once per parsed header, and its readers inspect what it gives rather than splitting
the text again: ``producer_steps`` the steps, ``reference_builds`` the words.

**A step is a tool, its inputs and its output.** What a tool's arguments mean is declared
once, in :data:`TOOL_ARGUMENTS`, about tools and not datasets: which options name an input,
which the output, and for a tool that takes its inputs as positional arguments, which
options take no value. A command line whose tool is not declared there is a step marked
unread (``read=False``) naming no input or output, never a guess.

**A step reads only what the tool wrote.** A command line is the tool recording its own
invocation; the values another program carried into it (bwa's ``-R`` read group, say)
are not read into a step (contract 3.13).

The cache holds the raw header, so a change here reaches every file without a re-fetch.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import cached_property

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
# subcommands the T2T joint-calling files carry. Anything else is an unread step.
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


@dataclass(frozen=True)
class Step:
    """One command line as a step: the tool, its inputs and its output, each a path as the line wrote it.

    ``output`` is None where the tool wrote to stdout (bcftools with no ``-o``) or the
    line names no single output (GATK 3's HaplotypeCaller names none). ``read`` is False
    for a line whose tool :data:`TOOL_ARGUMENTS` does not declare; such a step names no
    input or output. ``family`` is None for a line that is neither GATK's nor bcftools', and
    ``tool`` is then the line's ``ID``, or empty. ``stdin`` is True where a positional
    argument is ``-``: an input read from stdin, which names no file and is not in ``inputs``.
    """

    family: str | None
    tool: str
    inputs: tuple[str, ...]
    output: str | None
    read: bool = True
    stdin: bool = False


# A VCF header line that records how the file was produced. GATK writes
# ``##GATKCommandLine=<ID=Tool,...,CommandLine="...">`` (GATK3 suffixed the key:
# ``##GATKCommandLine.HaplotypeCaller``), bcftools writes
# ``##bcftools_normCommand=norm -f ...``, freebayes ``##commandline=...``. What
# they share is the word "command" in the key, so that is the whole test; the
# tool names are not enumerated. GATK4 spells the attribute ``CommandLine``,
# GATK3 ``CommandLineOptions`` (its value is ``key=value`` pairs, among them
# ``reference_sequence=/path.fa``). The attribute pattern tolerates a
# backslash-escaped quote inside the value, which ``parse_vcf_header_line``'s
# field pattern does not; it is written unrolled because it runs on every
# command line in the corpus.
_VCF_COMMAND_KEY_RE = re.compile(r"^##([^=]*command[^=]*)=(.*)$", re.IGNORECASE)
_VCF_COMMAND_ATTR_RE = re.compile(r'(CommandLine(?:Options)?)="([^"\\]*(?:\\.[^"\\]*)*)"')
_VCF_COMMAND_ID_RE = re.compile(r"(?:^<|,)ID=([^,>]+)")
_BCFTOOLS_KEY = re.compile(r"^bcftools_(\w+)Command$")
_GATK3_PAIR = re.compile(r"\b([\w.]+)=(\[[^\]]*\]|\S+)")
_GATK3_SOURCE = re.compile(r"source=([^\s)]+)")


@dataclass(frozen=True)
class VcfCommand:
    """One ``##<key containing "command">=`` line: its key, the ``ID`` a structured line
    gives, the command it records, and whether that is GATK 3's ``CommandLineOptions``
    (``key=value`` options) rather than a command line.

    ``text`` is the command as recorded, a quote inside a quoted attribute unescaped.
    :attr:`words` and :attr:`step` are read from it once, on first use.
    """

    key: str
    tool_id: str | None
    text: str
    options_form: bool = False

    @cached_property
    def words(self) -> tuple[str, ...]:
        """The command's arguments, less the ``; Date=…`` bcftools appends to its line.

        A tuple, because every reader of the command shares the one cached value.
        """
        text = self.text.split("; Date=", 1)[0] if _BCFTOOLS_KEY.match(self.key) else self.text
        return tuple(split_command_line(text))

    @cached_property
    def step(self) -> Step:
        """The command as a step, unread where :data:`TOOL_ARGUMENTS` does not declare its tool."""
        if self.key.lower().startswith("gatkcommandline"):
            if self.options_form:
                return _gatk3_step(self)
            family, tool = GATK, self.tool_id or ""
        elif bcftools := _BCFTOOLS_KEY.match(self.key):
            family, tool = BCFTOOLS, bcftools.group(1)
        else:
            return _unread(None, self.tool_id or "")
        arguments = TOOL_ARGUMENTS.get((family, tool))
        return _unread(family, tool) if arguments is None else _option_step(family, tool, self.words, arguments)


def vcf_commands(lines: Iterable[str]) -> list[VcfCommand]:
    """The command lines among ``lines``, in order.

    A structured ``<...>`` line contributes its quoted ``CommandLine`` (GATK4) or
    ``CommandLineOptions`` (GATK3) attribute, a ``\\"`` inside it read as ``"``, and is
    skipped if it has neither; a simple ``##key=value`` line contributes its value, minus
    one pair of enclosing double quotes if the whole value is quoted (freebayes writes it
    that way).
    """
    commands = []
    for line in lines:
        match = _VCF_COMMAND_KEY_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if value.startswith("<"):
            attr = _VCF_COMMAND_ATTR_RE.search(value)
            if attr:
                found = _VCF_COMMAND_ID_RE.search(value)
                tool_id = found.group(1) if found else None
                text = attr.group(2).replace('\\"', '"')
                commands.append(VcfCommand(key, tool_id, text, attr.group(1) == "CommandLineOptions"))
        elif len(value) >= 2 and value[0] == value[-1] == '"':
            commands.append(VcfCommand(key, None, value[1:-1]))
        else:
            commands.append(VcfCommand(key, None, value))
    return commands


def split_command_line(command_line: str) -> list[str]:
    """A recorded command line's arguments.

    ``str.split`` unless the line contains a quote character: ``shlex`` is two hundred
    times slower, and what it contributes is stripping the quotes (``--reference="/x.fa"``,
    ``-I "/x/a.cram"``). A line ``shlex`` rejects (an unbalanced quote) falls back to
    whitespace splitting.
    """
    if '"' not in command_line and "'" not in command_line:
        return command_line.split()
    try:
        return shlex.split(command_line)
    except ValueError:
        return command_line.split()


def _unread(family: str | None, tool: str) -> Step:
    return Step(family, tool, (), None, read=False)


def _gatk3_step(command: VcfCommand) -> Step:
    """A GATK 3 ``CommandLineOptions="key=value …"`` line as a step."""
    pairs = dict(_GATK3_PAIR.findall(command.text))
    tool = pairs.get("analysis_type") or command.tool_id or ""
    arguments = TOOL_ARGUMENTS.get((GATK3, tool))
    if arguments is None:
        return _unread(GATK3, tool)
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


def _option_step(family: str, tool: str, words: Sequence[str], arguments: ToolArguments) -> Step:
    """A step from a command's words, read through ``arguments``.

    A leading word naming the tool itself (GATK 4 writes it; bcftools repeats its
    subcommand) is skipped. A value is the word after its option, or the part after
    ``=`` in ``--option=value``.
    """
    if words and words[0] == tool:
        words = words[1:]
    inputs: list[str] = []
    outputs: list[str] = []
    stdin = False
    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        if not word.startswith("-") or word == "-":
            # A positional argument; `-` is stdin, which names no file.
            if arguments.positional:
                if word == "-":
                    stdin = True
                else:
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
    return Step(family, tool, tuple(inputs), _sole(outputs), stdin=stdin)


def _sole(paths: list[str]) -> str | None:
    """The one path, or None for none or several: a step naming two outputs names no output."""
    return paths[0] if len(paths) == 1 else None
