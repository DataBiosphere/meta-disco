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
  same header's callers (``header_classifier.classify_from_tar_head``, #678). In a folder
  :data:`REBUILT_MAP_FOLDERS` declares, whose maps no one holds, the map is rebuilt from the tar's
  own samples and folder (#726) and named by address, the tar producer holding each list once.

A step is written only where every parent resolves: exactly one file of the dataset carries
the name (#438's rule). Each file's outcome is one of :data:`OUTCOMES`, which the tar and
sample-map producers count per dataset.

A workspace's ``callset.json`` lists the samples GenomicsDB imported: where the tar fetcher read
it (``header_classifier.callset_member``, #724), :func:`parse_tar_head` parses it
(:func:`callset_samples`) for the tar producer's sample reader, and the external lineage importer
parses the ones it reads with the same function (#710).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path, PurePosixPath
from threading import Lock

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
from .records import dataset_of, folder_of
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
# Why a tar in a folder whose lists are rebuilt (#726) got no step, beside those above: the map its header
# names is none the layout declares, its `callset.json` gave no samples, or a sample's gVCF is carried by no
# file, or by several, or a sample is listed twice.
MAP_NOT_IN_LAYOUT = "map_not_in_layout"
NO_SAMPLES = "no_samples"
MEMBER_NOT_FOUND = "member_not_found"
MEMBER_AMBIGUOUS = "member_ambiguous"
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
    MAP_NOT_IN_LAYOUT,
    NO_SAMPLES,
    MEMBER_NOT_FOUND,
    MEMBER_AMBIGUOUS,
)


# The workspace tar folders, by dataset, whose sample maps are rebuilt (#726), its gVCFs under the folder's
# parent, the reference folder: ANVIL_T2T_CHRY's SGDP cohort, whose maps' bucket is deleted and whose two
# reference runs name the same map paths (#624). Each must be a folder whose `callset.json` is read
# (`header_classifier.CALLSET_FOLDERS`), the samples being the list's rows; a folder whose callset is read
# need not be rebuilt.
REBUILT_MAP_FOLDERS = {"ANVIL_T2T_CHRY": frozenset({"SGDP_CHM13v2/genomics_db", "SGDP_GRCh38/genomics_db"})}
# Where the run wrote its gVCFs under a reference folder, and the name every one ends in.
GVCF_FOLDER = "haplotype_calling_vcfs"
GVCF_SUFFIX = ".hc.vcf.gz"
# How a rebuilt list is addressed (``edges.PARENT_REF``): `rebuilt:<dataset>/<reference folder>/<map>#<digest>`.
REBUILT_SCHEME = "rebuilt:"


def set_id(values: Iterable[str]) -> str:
    """The id of a set of strings: the first 16 hex of the sha256 of the distinct ones, sorted, one per line."""
    return hashlib.sha256("\n".join(sorted(set(values))).encode("utf-8")).hexdigest()[:16]


def gvcf_layout(map_name: str) -> tuple[tuple[str, str], ...] | None:
    """Where a sample's gVCF for the sample map ``map_name`` is, as ``(folder, name less the sample)`` pairs, or None.

    The layout of T2T's joint-calling run (#726), as its published 1000 Genomes maps list it: per autosome
    one gVCF per sample; on chrX an XX sample's one whole-chrX gVCF, and an XY sample's PAR gVCF for a PAR
    map, its non-PAR gVCF for the non-PAR map; on chrY an XY sample's non-PAR gVCF. ``TarSteps`` takes a sample
    with a file at more than one of the pairs as ambiguous; ``map_name`` is matched exactly, as the header writes it.
    """
    if (match := _AUTOSOME_MAP.fullmatch(map_name)) is not None:
        chrom = match.group(1)
        return ((chrom, f".{chrom}{GVCF_SUFFIX}"),)
    return _SEX_CHROMOSOME_MAPS.get(map_name)


_AUTOSOME_MAP = re.compile(r"(chr[1-9]|chr1[0-9]|chr2[0-2])_sample_map\.tsv")
_XX_CHRX = ("XX_samples_chrX", f".chrX{GVCF_SUFFIX}")
_XY_CHRX_PAR = ("XY_samples_chrX-PAR", f".chrX_PAR{GVCF_SUFFIX}")
_SEX_CHROMOSOME_MAPS = {
    "chrX_PAR1_sample_map.tsv": (_XX_CHRX, _XY_CHRX_PAR),
    "chrX_PAR2_sample_map.tsv": (_XX_CHRX, _XY_CHRX_PAR),
    "chrX_non_PAR_sample_map.tsv": (_XX_CHRX, ("XY_samples_chrX-nonPAR", f".chrX_non_PAR{GVCF_SUFFIX}")),
    "chrY_sample_map.tsv": (("XY_samples_chrY-nonPAR", f".chrY{GVCF_SUFFIX}"),),
}

# Why a workspace whose `callset.json` was wanted names no samples (#724): it was looked for and
# not found, its read failed, or its text is no callset list.
NO_CALLSET = "no_callset"
CALLSET_UNREADABLE = "callset_unreadable"
NOT_A_CALLSET = "not_a_callset"


def callset_samples(text: str) -> list[str]:
    """The sample names a GenomicsDB ``callset.json`` lists, in its order; ``ValueError`` where it is not one.

    Its ``callsets`` is a list of objects each naming its ``sample_name``, or, in older
    workspaces, an object keyed by the sample name.
    """
    document = json.loads(text)
    callsets = document.get("callsets") if isinstance(document, dict) else None
    if isinstance(callsets, dict):
        found: list[object] = list(callsets)
    elif isinstance(callsets, list):
        found = [c.get("sample_name") if isinstance(c, dict) else None for c in callsets]
    else:
        raise ValueError("no callsets list")
    names = [n for n in found if isinstance(n, str) and n]
    if not names or len(names) != len(found):
        raise ValueError("a callset names no sample")
    return names


@dataclass(frozen=True)
class ParsedTarHead:
    """A tar's fetched head as the classifier, the step reader and the sample reader take it: the
    member names, its ``vcfheader.vcf`` parsed where it was read (None where not), and why it
    could not be where its read failed; and the samples its ``callset.json`` names where it was
    read and parses (#724), else why not (:data:`NO_CALLSET`, :data:`CALLSET_UNREADABLE`,
    :data:`NOT_A_CALLSET`), both None where it was not wanted."""

    member_names: list[str]
    header: VCFHeader | None
    vcf_header_unread: str | None = None
    samples: list[str] | None = None
    samples_unread: str | None = None

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
    classifier's caller reader and the step reader both (#678), and its ``callset.json`` for the
    sample reader (#724)."""
    header = parse_vcf_header(head.vcf_header) if head.vcf_header is not None else None
    samples, why = _parse_callset(head)
    return ParsedTarHead(head.member_names, header, head.vcf_header_unread, samples, why)


def _parse_callset(head: TarHead) -> tuple[list[str] | None, str | None]:
    """The samples ``head``'s ``callset.json`` names, or None and why; both None where it was not wanted."""
    if head.callset_unread is not None:
        return None, CALLSET_UNREADABLE
    if not head.callset_read:
        return None, None
    if head.callset is None:
        return None, NO_CALLSET
    names = _callset_names(head.callset)
    return (list(names), None) if names is not None else (None, NOT_A_CALLSET)


# The 62,022 SGDP workspaces hold two distinct callset texts (279 and 175 samples; measured 2026-10-21): each is parsed once.
@lru_cache(maxsize=8)
def _callset_names(text: str) -> tuple[str, ...] | None:
    try:
        return tuple(callset_samples(text))
    except ValueError:
        return None


def sample_name_map(head: ParsedTarHead, file_name: str) -> tuple[str | None, str | None]:
    """The path of the sample-name map a workspace tar's ``vcfheader.vcf`` says it was imported from, as written; or None and why.

    The header's ``GenomicsDBImport`` steps, identical lines once, must be exactly one
    (:data:`NO_ACTIVITY` otherwise; :data:`NO_COMMAND_LINE` with no command line at all),
    whose workspace path's base name is ``file_name`` less ``.tar``
    (:data:`OUTPUT_NOT_THIS_FILE`), and which names one sample-name map and no gVCF one
    by one (:data:`NO_ACTIVITY`). A tar that is no workspace gives None and no outcome; a
    workspace whose header was not read, its ``ParsedTarHead.unread``. Shared by
    :class:`TarSteps` and the external lineage importer (``external_lineage``, #710).
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
    return lists[0], None


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
    loaded record (:meth:`for_run`), keeping the records :meth:`keeps` takes (and, for :class:`TarSteps`,
    the gVCFs a rebuilt list could name), and called per file."""

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
    """A run's reader of the step each GenomicsDB workspace tar's ``vcfheader.vcf`` states, its parents the sample
    maps, or in a folder :data:`REBUILT_MAP_FOLDERS` declares the lists it rebuilds (#726), which it keeps for the
    producer file (:meth:`rebuilt_lists`)."""

    def __init__(self, index: edges.NameIndex, key: RecordKey, titles: dict[str, str] | None = None):
        super().__init__(index, key)
        # Each dataset's title by its id: the declaration names a dataset by title, a record by id.
        self.titles = titles or {}
        self._lock = Lock()
        # Per (dataset, reference folder, map, samples), the list rebuilt for it or why none was:
        # 62,022 tars read 52 lists (measured 2026-10-22), so each is resolved once.
        self._rebuilt: dict[tuple, tuple[dict | None, str]] = {}

    @staticmethod
    def keeps(name: str) -> bool:
        return name.lower().endswith(SAMPLE_MAP_SUFFIX)

    @classmethod
    def for_run(cls, records: Iterable[dict], key: RecordKey, evidence_base: Path):
        """The reader, its index holding the sample maps, and the gVCFs only where a rebuilt list can name them:
        under a declared dataset's reference folders' :data:`GVCF_FOLDER`."""
        titles: dict[str, str] = {}
        kept = []
        for r in records:
            title, dataset = r.get("dataset_title"), dataset_of(r)
            # Every record is read, not only this type's: a drifted id is the input gate's to refuse.
            if isinstance(title, str) and isinstance(dataset, str):
                titles[dataset] = title
            name = r.get("file_name")
            if isinstance(name, str) and (cls.keeps(name) or _rebuilt_member(r, name, title)):
                kept.append(r)
        return cls(edges.parent_index(kept, key, lambda _: True, cls.PURPOSE), key, titles)

    def __call__(
        self, head: ParsedTarHead, file_name: str, dataset_id: str, folder: str | None
    ) -> tuple[dict | None, str | None]:
        """A tar's ``generated_by`` from its ``vcfheader.vcf``, and the outcome (one of :data:`OUTCOMES`).

        A tar whose members are no GenomicsDB store has no step to read, and gives no outcome
        (None): it is not counted.

        The map its header names (:func:`sample_name_map`, whose outcomes it gives where the
        header names none) is, in a ``folder`` :data:`REBUILT_MAP_FOLDERS` declares for the dataset,
        the list rebuilt from the tar's own samples (:meth:`_rebuild`); elsewhere the one sample map of
        ``dataset_id`` carrying its base name, case-folded, as ``edges.matches`` settles it by the tar's
        ``folder`` (:data:`PARENT_NOT_FOUND`, :data:`PARENT_AMBIGUOUS`).
        """
        named, outcome = sample_name_map(head, file_name)
        if named is None:
            return None, outcome
        title = self.titles.get(dataset_id)
        if title is not None and folder is not None and folder in REBUILT_MAP_FOLDERS.get(title, ()):
            reference = PurePosixPath(folder).parent.as_posix()
            return self._rebuild(head, PurePosixPath(named).name, dataset_id, title, reference)
        parents, outcome = resolve_names(self.index, dataset_id, [PurePosixPath(named).name], folder)
        if parents is None:
            return None, outcome
        return edges.generated_by(code_rules.MERGE_BY_WORKSPACE_HEADER, parents, self.key), STEPPED

    def _rebuild(
        self, head: ParsedTarHead, map_name: str, dataset_id: str, title: str, reference: str
    ) -> tuple[dict | None, str]:
        """The tar's step with the list rebuilt for it its one ``input_list``, by its address; or None and why.

        The list's members are, for each sample ``head``'s ``callset.json`` names, the one file of
        ``dataset_id`` that :func:`gvcf_layout` places for ``map_name`` and the sample under
        ``reference``'s :data:`GVCF_FOLDER`: base name up to case, folder exactly. A map the layout
        does not declare gives :data:`MAP_NOT_IN_LAYOUT`; no samples, :data:`NO_SAMPLES`; a sample no
        file is placed for, :data:`MEMBER_NOT_FOUND`; one several are, or a sample listed twice,
        :data:`MEMBER_AMBIGUOUS`.
        """
        samples = tuple(head.samples or ())
        known = (dataset_id, reference, map_name, samples)
        with self._lock:
            rebuilt = self._rebuilt.get(known)
            if rebuilt is None:
                rebuilt = self._rebuilt[known] = self._resolve(map_name, samples, dataset_id, title, reference)
        entry, outcome = rebuilt
        if entry is None:
            return None, outcome
        return edges.generated_by_ref(code_rules.MERGE_BY_WORKSPACE_HEADER, map_name, entry["ref"]), STEPPED

    def _resolve(
        self, map_name: str, samples: tuple[str, ...], dataset_id: str, title: str, reference: str
    ) -> tuple[dict | None, str]:
        layout = gvcf_layout(map_name)
        if layout is None:
            return None, MAP_NOT_IN_LAYOUT
        if not samples:
            return None, NO_SAMPLES
        # Up to case, as the gVCFs are looked up.
        if len({s.lower() for s in samples}) < len(samples):
            return None, MEMBER_AMBIGUOUS
        members = []
        for sample in samples:
            found = [
                r
                for folder, rest in layout
                for r in self.index.get((dataset_id, f"{sample}{rest}".lower()), [])
                if r.get(edges.FOLDER) == f"{reference}/{GVCF_FOLDER}/{folder}"
            ]
            if len(found) != 1:
                return None, MEMBER_NOT_FOUND if not found else MEMBER_AMBIGUOUS
            members.append(found[0])
        step = edges.generated_by(code_rules.COHORT_BY_REBUILT_SAMPLE_MAP, members, self.key)
        digest = set_id(used["parent_key"] for used in step["inputs"])
        ref = f"{REBUILT_SCHEME}{title}/{reference}/{map_name}#{digest}"
        return {"ref": ref, "dataset": title, "file_name": map_name, "generated_by": step}, STEPPED

    def rebuilt_lists(self) -> list[dict]:
        """Each list rebuilt so far, once, by address: a ``RebuiltList`` each."""
        with self._lock:
            entries = {e["ref"]: e for e, _ in self._rebuilt.values() if e is not None}
        return [entries[ref] for ref in sorted(entries)]


def _rebuilt_member(record: dict, name: str, title: object) -> bool:
    """Whether ``record`` is a gVCF a rebuilt list could name: under a declared folder's reference folder's :data:`GVCF_FOLDER`."""
    if not name.lower().endswith(GVCF_SUFFIX) or not isinstance(title, str) or title not in _GVCF_ROOTS:
        return False
    return (folder_of(record) or "").startswith(_GVCF_ROOTS[title])


# Per dataset, the folder prefixes its rebuilt lists' gVCFs are under (:func:`_rebuilt_member`).
_GVCF_ROOTS = {
    title: tuple(f"{PurePosixPath(folder).parent.as_posix()}/{GVCF_FOLDER}/" for folder in sorted(folders))
    for title, folders in REBUILT_MAP_FOLDERS.items()
}


class SampleMapSteps(_StepReader):
    """A run's reader of the cohort each sample map lists, its parents the VCFs."""

    @staticmethod
    def keeps(name: str) -> bool:
        return edges.parent_kind_of(name) == MEMBER_KIND

    def __call__(
        self, rows: tuple[tuple[str, str], ...] | None, file_name: str, dataset_id: str, folder: str | None
    ) -> tuple[dict | None, str]:
        """A sample map's ``generated_by`` from its rows, and the outcome (one of :data:`OUTCOMES`).

        Each row's path gives a ``member``: the one file of ``dataset_id`` carrying its base
        name, case-folded, as ``edges.matches`` settles it by the map's ``folder``. A file that is not a sample map gives :data:`NOT_A_LIST`; a member
        no file carries, :data:`PARENT_NOT_FOUND`; otherwise a member several files carry,
        or two rows naming one base name, :data:`PARENT_AMBIGUOUS`. Any of these gives no
        step, since a cohort missing a member is not the cohort.
        """
        if rows is None:
            return None, NOT_A_LIST
        names = [PurePosixPath(path).name for _, path in rows]
        parents, outcome = resolve_names(self.index, dataset_id, names, folder)
        if parents is None:
            return None, outcome
        return edges.generated_by(code_rules.COHORT_BY_SAMPLE_MAP, parents, self.key), STEPPED
