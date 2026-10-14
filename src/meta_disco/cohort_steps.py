"""The steps of a joint calling's cohort, read from file content (#621).

T2T joint-called its gVCFs region by region: GATK's ``GenomicsDBImport`` merged the gVCFs a
**sample-name map** lists into one GenomicsDB workspace per region, each stored as a tar.
Two steps are read here, each from the file's own content:

- **A sample map's step** is a ``CohortDefinitionActivity`` with each gVCF it lists a
  ``member``. The map is tab-separated columns, a sample name and a VCF path, and
  optionally the VCF's index path, which is no member; the paths
  are where the workflow ran, so each is matched by base name within the map's dataset.
  The map is the record of who was computed together (#619). It passes nothing itself.
- **A workspace tar's step** is a ``CohortMergeActivity`` with the map its one ``input_list``,
  read from the tar's own ``vcfheader.vcf``, which carries the ``GenomicsDBImport`` command
  line: ``--genomicsdb-workspace-path`` must name the tar itself, and ``--sample-name-map``
  names the list, matched by base name among the dataset's sample maps. At reconcile the tar
  takes its values from the map's members, read through the map (``activities.read_through``),
  not from each gVCF as an input of its own; its kind and origin it also reads itself, from the
  same header's callers (``header_classifier.classify_from_tar_head``, #678).

A step is written only where every parent resolves: exactly one file of the dataset carries
the name (#438's rule). Each file's outcome is one of :data:`OUTCOMES`, which the tar and
sample-map producers count per dataset.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path, PurePosixPath

from . import code_rules, edges
from .evidence import TarHead
from .header_classifier import workspace_header_member, workspace_name
from .producer_steps import (
    NO_ACTIVITY,
    NO_COMMAND_LINE,
    OUTPUT_NOT_THIS_FILE,
    PARENT_AMBIGUOUS,
    PARENT_NOT_FOUND,
    STEPPED,
    data_name,
    resolve_names,
)
from .record_keys import RecordKey
from .validators.command_lines import GATK
from .validators.header_extractors import VCFHeader, parse_vcf_header

# The name every sample map the sample-map producer claims ends in, case-folded.
SAMPLE_MAP_SUFFIX = "_sample_map.tsv"
# The kind (`edges.parent_kind_of`) every path a sample map lists must be.
MEMBER_KIND = "variants"
# What a sample map's optional third column, a member's index, may end in.
INDEX_SUFFIXES = (".tbi", ".csi", ".idx")
GENOMICSDB_IMPORT = "GenomicsDBImport"

# Why a file got the step it did, or none, beside `producer_steps`' outcomes.
NO_VCF_HEADER = "no_vcf_header"
VCF_HEADER_UNREADABLE = "vcf_header_unreadable"
NOT_A_LIST = "not_a_list"
OUTCOMES = (
    STEPPED,
    NO_VCF_HEADER,
    VCF_HEADER_UNREADABLE,
    NO_COMMAND_LINE,
    NO_ACTIVITY,
    OUTPUT_NOT_THIS_FILE,
    NOT_A_LIST,
    PARENT_NOT_FOUND,
    PARENT_AMBIGUOUS,
)


@dataclass(frozen=True)
class ParsedTarHead:
    """A tar's fetched head as the classifier and the step reader take it: the member names,
    its ``vcfheader.vcf`` parsed where it was read (None where not), and why it could not be
    where its read failed."""

    member_names: list[str]
    header: VCFHeader | None
    vcf_header_unread: str | None = None

    @cached_property
    def is_workspace(self) -> bool:
        """Whether the members are a GenomicsDB workspace's (``workspace_header_member``), decided once for both readers."""
        return workspace_header_member(self.member_names) is not None

    @property
    def unread(self) -> str | None:
        """Why a workspace's ``vcfheader.vcf`` was not parsed: :data:`VCF_HEADER_UNREADABLE` where its read
        failed (the cause in ``vcf_header_unread``), else :data:`NO_VCF_HEADER`; None where it was, or for
        a tar that is no workspace."""
        if not self.is_workspace or self.header is not None:
            return None
        return NO_VCF_HEADER if self.vcf_header_unread is None else VCF_HEADER_UNREADABLE


def parse_tar_head(head: TarHead) -> ParsedTarHead:
    """``head`` with its ``vcfheader.vcf`` parsed, once per file (``FileTypeConfig.parser``), for the
    classifier's caller reader and the step reader both (#678)."""
    header = parse_vcf_header(head.vcf_header) if head.vcf_header is not None else None
    return ParsedTarHead(head.member_names, header, head.vcf_header_unread)


def parse_sample_map(text: str) -> tuple[tuple[str, str], ...] | None:
    """A sample map's rows, ``(sample, path)``, or None where ``text`` is not one.

    A sample map is lines of two tab-separated fields, a sample name and the path of a VCF
    (a name ``edges.parent_kind_of`` calls ``variants``), or of three, the third the path of
    that VCF's index (``.tbi``, ``.csi`` or ``.idx``), which GATK's map allows and which is no member;
    blank lines are skipped. A file with no row, or any other line, is not one.
    """
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = [f.strip() for f in line.rstrip("\r").split("\t")]
        if len(fields) not in (2, 3) or not fields[0] or not _is_member_path(fields[1]):
            return None
        if len(fields) == 3 and not fields[2].lower().endswith(INDEX_SUFFIXES):
            return None
        rows.append((fields[0], fields[1]))
    return tuple(rows) or None


def _is_member_path(path: str) -> bool:
    return edges.parent_kind_of(PurePosixPath(path).name) == MEMBER_KIND


class _StepReader:
    """A run's step reader: the name index its parents resolve in, built once per run from every
    loaded record (:meth:`for_run`), keeping only the records :meth:`keeps` takes, and called per file."""

    PURPOSE = "ground a cohort step's input on its parent"

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


class TarSteps(_StepReader):
    """A run's reader of the step each GenomicsDB workspace tar's ``vcfheader.vcf`` states, its parents the sample maps."""

    @staticmethod
    def keeps(name: str) -> bool:
        return name.lower().endswith(SAMPLE_MAP_SUFFIX)

    def __call__(self, head: ParsedTarHead, file_name: str, dataset_id: str) -> tuple[dict | None, str | None]:
        """A tar's ``generated_by`` from its ``vcfheader.vcf``, and the outcome (one of :data:`OUTCOMES`).

        A tar whose members are no GenomicsDB store has no step to read, and gives no outcome
        (None): it is not counted.

        Its header's ``GenomicsDBImport`` steps, identical lines once, must be exactly one
        (:data:`NO_ACTIVITY` otherwise; :data:`NO_COMMAND_LINE` with no command line at all),
        whose workspace path's base name is this tar's name less ``.tar``
        (:data:`OUTPUT_NOT_THIS_FILE`), and which names one sample-name map and no gVCF
        one by one (:data:`NO_ACTIVITY`). The map is the one sample map of ``dataset_id``
        carrying its base name, case-folded (:data:`PARENT_NOT_FOUND`,
        :data:`PARENT_AMBIGUOUS`). A workspace whose ``vcfheader.vcf`` was not read gives
        :data:`VCF_HEADER_UNREADABLE` where reading it failed, else :data:`NO_VCF_HEADER`.
        """
        if not head.is_workspace:
            return None, None
        if head.header is None:
            return None, head.unread
        commands = head.header.commands
        if not commands:
            return None, NO_COMMAND_LINE
        imports = list(
            dict.fromkeys(
                c.step for c in commands if c.step.read and c.step.family == GATK and c.step.tool == GENOMICSDB_IMPORT
            )
        )
        if len(imports) != 1:
            return None, NO_ACTIVITY
        (step,) = imports
        if step.output is None or data_name(step.output) != workspace_name(file_name):
            return None, OUTPUT_NOT_THIS_FILE
        lists = list(dict.fromkeys(step.input_lists))
        if step.inputs or len(lists) != 1:
            return None, NO_ACTIVITY
        parents, outcome = resolve_names(self.index, dataset_id, [PurePosixPath(lists[0]).name])
        if parents is None:
            return None, outcome
        return edges.generated_by(code_rules.MERGE_BY_WORKSPACE_HEADER, parents, self.key), STEPPED


class SampleMapSteps(_StepReader):
    """A run's reader of the cohort each sample map lists, its parents the VCFs."""

    @staticmethod
    def keeps(name: str) -> bool:
        return edges.parent_kind_of(name) == MEMBER_KIND

    def __call__(
        self, rows: tuple[tuple[str, str], ...] | None, file_name: str, dataset_id: str
    ) -> tuple[dict | None, str]:
        """A sample map's ``generated_by`` from its rows, and the outcome (one of :data:`OUTCOMES`).

        Each row's path gives a ``member``: the one file of ``dataset_id`` carrying its base
        name, case-folded. A file that is not a sample map gives :data:`NOT_A_LIST`; a member
        no file carries, :data:`PARENT_NOT_FOUND`; otherwise a member several files carry,
        or two rows naming one base name, :data:`PARENT_AMBIGUOUS`. Any of these gives no
        step, since a cohort missing a member is not the cohort.
        """
        if rows is None:
            return None, NOT_A_LIST
        parents, outcome = resolve_names(self.index, dataset_id, [PurePosixPath(path).name for _, path in rows])
        if parents is None:
            return None, outcome
        return edges.generated_by(code_rules.COHORT_BY_SAMPLE_MAP, parents, self.key), STEPPED
