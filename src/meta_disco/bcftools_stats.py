"""The VCF a bcftools stats report reports on, and the samples it reports, read from its own text (#683).

``bcftools stats`` writes a plain-text report: line 1 says bcftools stats produced it, line 2
records its command line, and an ``ID`` line names each input, ``ID\\t0\\t<path>`` for the first.
The path is where the workflow ran, so only its base name is matched, within the report's dataset
(``producer_steps.resolve_names``, the folder settling a name several files carry, #717). A report
on exactly one input that resolves is a ``QualityControlActivity`` with that VCF ``reported_on``
(``code_rules.QC_REPORT_BY_CONTENT``); reconcile carries across it the dimensions and samples
``rules/activities.yaml`` says that role passes.

Given samples (ANVIL_T2T's per-population reports name them with ``--samples-file``), bcftools stats
gives each a ``PSC`` line, ``PSC\\t0\\t<sample>\\t…``: those names are the report's own samples
(:data:`STATS_REPORT_SAMPLES`), read wherever a report has them, not inferred from its command line. A
report with no ``PSC`` line reads none; in ANVIL_T2T exactly the 1,488 run with ``--samples-file`` have
them (measured 2026-10-25).
"""

from __future__ import annotations

from dataclasses import dataclass
from operator import attrgetter
from pathlib import PurePosixPath

from . import code_rules, edges
from .producer_steps import PARENT_AMBIGUOUS, PARENT_NOT_FOUND, STEPPED, NameStepReader
from .sample_identity import SampleReader

# The names the bcftools stats producer claims, case-folded: ANVIL_T2T's and ANVIL_T2T_CHRY's
# reports on a VCF, its per-population reports (`--samples-file`) and its AFR-region reports
# (`--regions-file chm13_AFR.bed`).
REPORT_SUFFIXES = (".bcftools.stats.txt", ".per_sample.stats.txt", ".chm13_afr.stats.txt")
# What line 1 of every report bcftools stats writes starts with.
FIRST_LINE = "# This file was produced by bcftools stats"
# The kind (`edges.parent_kind_of`) a report's input must be.
PARENT_KIND = "variants"

# Why a report got the step it did, or none, beside `producer_steps`' outcomes.
NOT_A_REPORT = "not_a_report"
NO_INPUT = "no_input"
SEVERAL_INPUTS = "several_inputs"
INPUT_NOT_A_VCF = "input_not_a_vcf"
OUTCOMES = (STEPPED, NOT_A_REPORT, NO_INPUT, SEVERAL_INPUTS, INPUT_NOT_A_VCF, PARENT_NOT_FOUND, PARENT_AMBIGUOUS)


@dataclass(frozen=True)
class StatsReport:
    """A bcftools stats report's ``ID`` paths, and its ``PSC`` lines' names in order, None where it has none."""

    inputs: tuple[str, ...]
    samples: tuple[str, ...] | None = None


def parse_stats_report(text: str) -> StatsReport | None:
    """The report ``text`` is, or None where its line 1 is not bcftools stats'.

    An ``ID`` or ``PSC`` line is one whose first tab-separated field is exactly that (``IDD``, the
    indel-length histogram, is no ``ID`` line). ``inputs`` holds every file name of every ``ID`` line.
    """
    lines = text.splitlines()
    if not lines or not lines[0].startswith(FIRST_LINE):
        return None
    inputs, samples = [], []
    for line in lines:
        fields = line.split("\t")
        if fields[0] == "ID":
            # An ID row lists tab-separated file names (bcftools' own `# ID` definition line): keep them all,
            # so a row naming two files is two inputs.
            inputs.extend(fields[2:])
        elif fields[0] == "PSC" and len(fields) >= 3:
            samples.append(fields[2])
    return StatsReport(tuple(inputs), tuple(samples) or None)


# A report's `PSC` names, read only where it has a `PSC` line: one without names no samples of its own.
STATS_REPORT_SAMPLES = SampleReader(
    code_rules.BCFTOOLS_STATS_SAMPLES,
    attrgetter("samples"),
    applies=lambda report: report is not None and report.samples is not None,
)


class StatsReportSteps(NameStepReader):
    """A run's reader of the VCF each bcftools stats report names on its ``ID`` line, its parents the VCFs."""

    @staticmethod
    def keeps(name: str) -> bool:
        return edges.parent_kind_of(name) == PARENT_KIND

    def __call__(
        self, report: StatsReport | None, file_name: str, dataset_id: str, folder: str | None
    ) -> tuple[dict | None, str]:
        """A report's ``generated_by`` from its ``ID`` line, and the outcome (one of :data:`OUTCOMES`).

        A file that is not a report gives :data:`NOT_A_REPORT`; one with no ``ID`` line,
        :data:`NO_INPUT`; with two or more, :data:`SEVERAL_INPUTS` (which input a two-file report's
        numbers describe is per line, not per file); one whose input is not a VCF by name,
        :data:`INPUT_NOT_A_VCF`; otherwise the input's base name resolves as
        ``producer_steps.resolve_names`` settles it, by the report's ``folder``.
        """
        if report is None:
            return None, NOT_A_REPORT
        if not report.inputs:
            return None, NO_INPUT
        path, *others = report.inputs
        if others:
            return None, SEVERAL_INPUTS
        if not self.keeps(PurePosixPath(path).name):
            return None, INPUT_NOT_A_VCF
        return self.step(code_rules.QC_REPORT_BY_CONTENT, [path], dataset_id, folder)
