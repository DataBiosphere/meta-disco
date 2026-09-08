"""What the AnVIL manifests on disk actually carry, measured (issue #384).

#368 downloaded two manifests per dataset — a 60-column ``compact.tsv`` and a
``verbatim.jsonl`` of raw entities — and nothing read them. Three issues each
propose consuming a slice (#369 dimensions from submitter tables, #336
governance fields, #361 donor edges), and each assumed a coverage picture nobody
had written down. This module measures that picture from the manifests on disk,
with no network, and renders it as markdown plus a machine-readable dict of every
number the markdown rounds; ``scripts/generate_manifest_survey.py`` is what
chooses the paths and writes them.

It measures four things per dataset, and one across the survey — the
contradictions in :func:`contradictions`:

- **Compact column coverage.** The non-empty fill rate of each of the 60 compact
  columns. A cell counts as absent if it is empty or one of the placeholder
  spellings in :data:`ABSENT_CELLS`; which spellings actually occurred is itself
  reported, so the rule is auditable rather than assumed.
- **Verbatim entity census.** Every entity ``type`` with its row count, and for
  every submitter (non-``anvil_*``) table the fields present with their fill
  rates, how many of the dataset's files that table names, and what — if
  anything — it says about a dimension, whether in its *name*
  (:data:`NAME_TOKENS`) or in a populated field (:data:`FIELD_TOKENS`).
- **Reach.** How many files can be resolved to a biosample and to a donor, three
  ways: through the compact join, through the verbatim activity chain one hop,
  and through the verbatim activity chain transitively. The three disagree, and
  the disagreement is the point — see :func:`_verbatim_reach`.
- **Consumer readiness.** Per dataset, whether it can support each of #369,
  #336 and #361, each verdict backed by one of the numbers above.

This module measures and reports. It classifies nothing, and deliberately holds
no mapping from a submitter table to a dimension value: :data:`NAME_TOKENS` says
"this table's name mentions CHM13", not "these files are CHM13", and
:data:`FIELD_TOKENS` says "this column exists and is populated", not what its
values mean. Turning any of this into classification is #369's work, not this
survey's.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .azul_manifest import (
    FORMAT_COMPACT,
    FORMAT_VERBATIM,
    FORMATS,
    VERBATIM_ACTIVITY,
    VERBATIM_BIOSAMPLE,
    VERBATIM_FILE,
    compact_header,
    iter_compact_rows,
    iter_verbatim_entities,
    manifest_path,
    sidecar_datasets,
)
from .summaries import md_table

# A cell or field holding one of these, stripped and lowercased, is absent. AC2
# of #384 names empty, ``null`` and ``NA``; the rest are the other spellings a
# JSON-ish serializer reaches for when it has nothing. Every one of these that
# actually occurs in a compact cell is counted per dataset, so a value wrongly
# swallowed by this rule — a literal biosample type of "None", say — is at least
# visible as a count beside the fill rates it deflated.
ABSENT_CELLS = frozenset({"", "null", "na", "n/a", "none", "[]", "{}"})
# Longest placeholder above; a longer value can only be absent by being padded.
_LONGEST_ABSENT = max(len(spelling) for spelling in ABSENT_CELLS)

# The compact columns that carry Azul's materialized join from a file to the rest
# of the model. #361 needs the first two; the third is measured beside them to
# check whether they can come apart. On anvil15 they do not — every dataset fills
# all three at the same rate or none of them — which :func:`join_uniform` measures
# on every run rather than this comment asserting it, since #384's own table
# reported them diverging.
JOIN_DONOR = "donors.donor_id"
JOIN_BIOSAMPLE = "biosamples.biosample_id"
JOIN_ACTIVITY = "activities.activity_id"

# What #336 wants to import. Consent and DUO are the verdict; the phs accession is
# reported beside it, because it is the one of the three that is not universal.
GOVERNANCE_CONSENT = "datasets.consent_group"
GOVERNANCE_DUO = "datasets.data_use_permission"
GOVERNANCE_PHS = "datasets.registered_identifier"

# The harmonized dimension columns whose emptiness is the standing justification
# for inferring at all. Reported as a block so the claim is measured, not asserted.
DIMENSION_COLUMNS = (
    "files.data_modality",
    "files.reference_assembly",
    "activities.assay_type",
    "activities.data_modality",
    "activities.reference_assembly",
    "datasets.data_modality",
)

# Readiness bands, stated here and restated in the rendered doc so a verdict can
# be checked against its backing number.
READY_HIGH = 0.90
READY_LOW = 0.10

# Tokens in a submitter table's *name* that point at one of the five dimensions,
# mapped to the schema's term for what the name says — or to ``None`` where the
# controlled vocabulary has no term for it.
#
# The values are ``classification.yaml``'s, checked against it by
# ``test_manifest_survey``: this survey must not mint a second vocabulary that
# #369 would then have to translate. Where the schema has no term the entry is
# ``None`` rather than a freshly invented string, and the report lists those
# separately — a table name that classifies something the vocabulary cannot
# express is a finding for #369, not a gap to paper over here.
#
# Some terms are coarser than the name: ``hifi`` and ``kinnex`` both map to
# ``PACBIO`` because that is the granularity ``platform_enum`` has. The token
# itself stays visible in the report, so the distinction is not lost, only
# un-vocabularized.
#
# Split the name on non-alphanumeric boundaries, lowercase, and look each token
# up. This says what a name mentions, never what a file is. Entity-shaped tokens
# (``sample``, ``participant``, ``donor``) name no dimension and are absent on
# purpose.
NAME_TOKENS: dict[str, tuple[str, str | None]] = {
    # reference_assembly
    "chm13": ("reference_assembly", "CHM13"),
    "chm13v2": ("reference_assembly", "CHM13"),
    "grch38": ("reference_assembly", "GRCh38"),
    "hg38": ("reference_assembly", "GRCh38"),
    "grch37": ("reference_assembly", "GRCh37"),
    "hg19": ("reference_assembly", "GRCh37"),
    # platform
    "hifi": ("platform", "PACBIO"),
    "deepconsensus": ("platform", "PACBIO"),
    "kinnex": ("platform", "PACBIO"),
    "ont": ("platform", "ONT"),
    "nanopore": ("platform", "ONT"),
    "illumina": ("platform", "ILLUMINA"),
    # assay_type — assay_type_enum has no Hi-C term.
    "hic": ("assay_type", None),
    # data_modality
    "methylation": ("data_modality", "epigenomic.methylation"),
    # data_type
    "assembly": ("data_type", "assembly"),
    "alignments": ("data_type", "alignments"),
    "liftoff": ("data_type", "annotations"),
    "annotation": ("data_type", "annotations"),
    "interval": ("data_type", "interval_set"),
    "sequences": ("data_type", "sequence"),
    "minigraph": ("data_type", "pangenome"),
    "cactus": ("data_type", "pangenome"),
    "pggb": ("data_type", "pangenome"),
    # data_type the vocabulary cannot express. Each is a real content kind a
    # table name asserts; naming what they would map to is #369's decision, not
    # this survey's, so they carry the dimension and no term.
    "chains": ("data_type", None),
    "segdups": ("data_type", None),
    "censat": ("data_type", None),
    "centromeres": ("data_type", None),
    "gaps": ("data_type", None),
    "repeat": ("data_type", None),
    "masker": ("data_type", None),
    "plink": ("data_type", None),
}

# Submitter field names that carry a dimension outright. Matched on the whole
# field name, never as a substring: ``assembly`` is the reference a row's files
# were aligned to, while ``assembly_fai`` and ``assembly_date`` are not
# references at all, and a substring rule would take all three. Like
# :data:`NAME_TOKENS` this is a reading aid — it says the column exists and is
# populated, not what its values mean, which is #369's mapping to write.
FIELD_TOKENS: dict[str, str] = {
    "assembly": "reference_assembly",
    "reference_assembly": "reference_assembly",
    "reference_coordinates": "reference_assembly",
    "reference_genome_build": "reference_assembly",
    "instrument_model": "platform",
    "instrument_platform": "platform",
    "platform": "platform",
    "seq_platform": "platform",
    "sequencing_platform": "platform",
    "assay_term": "assay_type",
    "assay_titles": "assay_type",
    "library_selection": "assay_type",
    "library_strategy": "assay_type",
    "preferred_assay_titles": "assay_type",
    "sequencing_assay": "assay_type",
    "sequencing_strategy": "assay_type",
    "library_source": "data_modality",
    "data_type": "data_type",
}

# What the report prints where a table name classifies something the controlled
# vocabulary has no term for. Spelled once so the report and #369 agree on it.
NO_VOCABULARY_TERM = "(no vocabulary term)"

_NAME_SPLIT = re.compile(r"[^0-9a-z]+")
# The Azul file id inside a DRS URI: ``drs://drs.anv0:v2_<uuid>``. A submitter
# table points at files either this way or by the bare id, so both are looked for.
_DRS_FILE_ID = re.compile(r"v2_([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})", re.IGNORECASE)
_DRS_MARKER = "v2_"  # the cheap substring test that gates the regex above

_HARMONIZED_PREFIX = "anvil_"


# --- measured shapes ----------------------------------------------------------


@dataclass
class ColumnCoverage:
    """One compact column's fill across one dataset."""

    column: str
    filled: int
    rows: int

    @property
    def rate(self) -> float:
        return self.filled / self.rows if self.rows else 0.0


@dataclass
class TableCoverage:
    """One verbatim entity type across one dataset.

    ``fields`` counts, per field name, the rows where that field held something
    (:func:`_is_filled`); a field absent from a row counts as unfilled, so a rate
    is always out of ``rows``. ``files_named`` counts the dataset's own
    ``anvil_file`` ids this table points at, by any handle :class:`FileKeys`
    indexes — a bare id, a DRS URI, or an unambiguous file name. Files the table
    names but the dataset does not hold are not counted.
    """

    name: str
    rows: int
    fields: dict[str, int] = field(default_factory=dict)
    files_named: int = 0
    encodes: list[tuple[str, str | None]] = field(default_factory=list)

    @property
    def is_submitter(self) -> bool:
        return not self.name.startswith(_HARMONIZED_PREFIX)

    @property
    def dimension_fields(self) -> list[tuple[str, str]]:
        """``(field, dimension)`` for each populated field named in :data:`FIELD_TOKENS`.

        A field present on every row but never filled carries nothing, so it is
        not counted: the question this answers is what an importer could read,
        not what the table's header promises.
        """
        return sorted(
            (name, FIELD_TOKENS[name]) for name, filled in self.fields.items() if filled and name in FIELD_TOKENS
        )

    @property
    def carries_dimension(self) -> bool:
        """Whether the table's name or its populated fields point at a dimension."""
        return bool(self.encodes or self.dimension_fields)


@dataclass
class Reach:
    """How many of a dataset's files resolve to a biosample and to a donor.

    Both measurements walk the verbatim manifest: ``single_hop_*`` goes only to
    the activity that generated the file, ``transitive_*`` walks the file/activity
    graph as far as it connects. The compact join is not repeated here — it is
    ``DatasetSurvey.filled`` of the ``JOIN_*`` columns, counted once where every
    other column is.

    ``files`` is the dataset's ``anvil_file`` count, which is the denominator for
    these two and is not always the compact row count.
    """

    files: int = 0
    single_hop_biosample: int = 0
    single_hop_donor: int = 0
    transitive_biosample: int = 0
    transitive_donor: int = 0


@dataclass
class DatasetSurvey:
    """Everything measured for one dataset."""

    title: str
    compact_rows: int = 0
    snapshot_files: int = 0
    columns: list[ColumnCoverage] = field(default_factory=list)
    absent_spellings: Counter = field(default_factory=Counter)
    tables: list[TableCoverage] = field(default_factory=list)
    reach: Reach = field(default_factory=Reach)
    # Files named by at least one dimension-carrying submitter table, counted as a
    # union of ids rather than a sum of per-table counts — the tables overlap.
    dimension_files: int = 0

    @property
    def submitter_tables(self) -> list[TableCoverage]:
        return [t for t in self.tables if t.is_submitter]

    def column(self, name: str) -> ColumnCoverage | None:
        return next((c for c in self.columns if c.column == name), None)

    def filled(self, name: str) -> int:
        """Rows where this column holds something; 0 for a column this dataset lacks."""
        found = self.column(name)
        return found.filled if found else 0

    def rate(self, name: str) -> float:
        found = self.column(name)
        return found.rate if found else 0.0

    @property
    def join_uniform(self) -> bool:
        """Whether the three ``JOIN_*`` columns are filled at the same rate here."""
        return self.rate(JOIN_DONOR) == self.rate(JOIN_BIOSAMPLE) == self.rate(JOIN_ACTIVITY)

    @property
    def name_encoding_tables(self) -> list[TableCoverage]:
        """Submitter tables whose *name* encodes a dimension."""
        return [t for t in self.submitter_tables if t.encodes]

    @property
    def dimension_tables(self) -> list[TableCoverage]:
        """Submitter tables pointing at a dimension by name or by field — #369's raw material."""
        return [t for t in self.submitter_tables if t.carries_dimension]

    @property
    def dimension_file_rate(self) -> float:
        """Share of the dataset's *verbatim* files named by a dimension-carrying table.

        The denominator is ``reach.files`` — the ``anvil_file`` count — not
        ``compact_rows``, because the numerator is a set of verbatim file ids. The
        two differ slightly on some datasets, so the rendered report says which
        denominator each rate uses rather than calling both "of files".

        An upper bound on what an import from submitter tables could reach, not a
        promise that what it reads would be right — a populated
        ``reference_assembly`` column can still hold a value no vocabulary knows.
        """
        return self.dimension_files / self.reach.files if self.reach.files else 0.0


@dataclass
class Survey:
    """The whole run: one entry per dataset, plus what it was measured from."""

    catalog: str
    datasets: list[DatasetSurvey] = field(default_factory=list)
    snapshot_total: int = 0

    @property
    def measured_total(self) -> int:
        return sum(d.compact_rows for d in self.datasets)


# --- absence ------------------------------------------------------------------


def cell_absent(cell: str) -> bool:
    """Whether a compact cell holds nothing, by :data:`ABSENT_CELLS`."""
    return cell.strip().lower() in ABSENT_CELLS


def _is_filled(value: Any) -> bool:
    """Whether a verbatim field holds something.

    ``None``, an empty string or whitespace, and an empty list/dict are nothing.
    ``0`` and ``False`` are values — a coverage of 0.0 or a ``has_replicates`` of
    false is data the submitter recorded, not a gap.
    """
    if value is None:
        return False
    if isinstance(value, str):
        # Same short-circuit as survey_compact: 23M verbatim string fields pass
        # through here, and one longer than any placeholder needs no normalizing.
        if len(value) > _LONGEST_ABSENT and not value[0].isspace() and not value[-1].isspace():
            return True
        return not cell_absent(value)
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


# --- compact ------------------------------------------------------------------


def survey_compact(path: Path) -> tuple[int, list[ColumnCoverage], Counter]:
    """Measure one compact manifest: rows, per-column fill, and the absent spellings seen.

    Streams the file; the largest compact manifest is 270 MB. The absence test is
    inlined rather than calling :func:`cell_absent` per cell, and short-circuits
    the two cases that dominate: an empty cell (61% of the 17.4M cells in the
    largest manifest), and a cell too long to be a placeholder — every member of
    :data:`ABSENT_CELLS` is at most four characters, so a longer cell is absent
    only if it is whitespace-padded. Same counts, measured a third faster.
    """
    rows = 0
    filled: Counter = Counter()
    spellings: Counter = Counter()
    # From the header, not the first data row: a manifest with a header and no
    # rows has columns that are 0% filled, which is not the same as having none.
    columns = compact_header(path)
    for _n, row in iter_compact_rows(path):
        rows += 1
        for name, cell in row.items():
            if not cell:
                # None is a short row: csv.DictReader leaves missing trailing columns unset.
                spellings["(missing column)" if cell is None else "(empty)"] += 1
                continue
            if len(cell) <= _LONGEST_ABSENT or cell[0].isspace() or cell[-1].isspace():
                stripped = cell.strip().lower()
                if stripped in ABSENT_CELLS:
                    spellings[stripped or "(empty)"] += 1
                    continue
            filled[name] += 1
    coverage = [ColumnCoverage(column=name, filled=filled[name], rows=rows) for name in columns]
    return rows, coverage, spellings


# --- verbatim -----------------------------------------------------------------


class _Components:
    """Union-find over file ids, for the transitive reach.

    Files touched by one activity are in one component, so "which files does
    this activity's biosample reach" becomes a mark on a component root rather
    than a graph walk per file. Ids are indexed to ints; a file id referenced by
    an activity but absent from ``anvil_file`` still gets an index, because a
    path through a file the dataset does not itself hold is still a path.
    """

    def __init__(self) -> None:
        self._index: dict[str, int] = {}
        self._parent: list[int] = []

    def index(self, key: str) -> int:
        found = self._index.get(key)
        if found is None:
            found = len(self._parent)
            self._index[key] = found
            self._parent.append(found)
        return found

    def known(self, key: str) -> int | None:
        return self._index.get(key)

    def find(self, item: int) -> int:
        parent = self._parent
        root = item
        while parent[root] != root:
            root = parent[root]
        while parent[item] != root:  # path compression
            parent[item], item = root, parent[item]
        return root

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self._parent[right_root] = left_root


def _table_encodes(name: str) -> list[tuple[str, str | None]]:
    """What a submitter table's name says about a dimension, by :data:`NAME_TOKENS`.

    Returns ``(dimension, value)`` pairs in the order the tokens appear in the
    name, deduplicated on the pair rather than on the dimension: a name
    mentioning both ``chm13`` and ``grch38`` keeps both references, so the caller
    sees the ambiguity instead of having it resolved silently here.
    """
    found: list[tuple[str, str | None]] = []
    for token in _NAME_SPLIT.split(name.lower()):
        meaning = NAME_TOKENS.get(token)
        if meaning is not None and meaning not in found:
            found.append(meaning)
    return found


class FileKeys:
    """Every string that identifies one of a dataset's files, mapped to its ``file_id``.

    A submitter table points at a file by whichever handle the submitter had, and
    the handles are not one namespace. Three are indexed:

    - the ``anvil_file.file_id`` itself;
    - the uuid inside that file's DRS URI. On some datasets it *is* the file id
      (MAGE), and on others it is unrelated to it — ENCORE and IGVF Mouse share
      no uuid at all between the two, so matching a submitter table's DRS URIs
      against file ids alone finds every file on MAGE and none on either of those;
    - the file name, but only where it identifies exactly one file. A name shared
      by two files identifies neither, so a colliding name is dropped rather than
      resolved arbitrarily.

    Files are added one at a time as the manifest streams past, and :meth:`resolved`
    closes the index — the name collisions are only known once every file has been
    seen, so nothing may be looked up before then.
    """

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}
        self._names: dict[str, str | None] = {}

    def add(self, value: dict[str, Any]) -> str:
        """Index one ``anvil_file`` entity, and return its ``file_id``."""
        file_id = value["file_id"]
        self._keys[file_id] = file_id
        for handle in (value.get("drs_uri"), value.get("file_ref")):
            if isinstance(handle, str):
                for match in _DRS_FILE_ID.finditer(handle):
                    self._keys[match.group(1).lower()] = file_id
        name = value.get("file_name")
        if isinstance(name, str) and name:
            # A name already claimed by a different file identifies neither.
            self._names[name] = None if self._names.get(name, file_id) != file_id else file_id
        return file_id

    def resolved(self) -> dict[str, str]:
        """The finished index. An id or DRS uuid wins over a file name that collides with it."""
        keys = dict(self._keys)
        for name, file_id in self._names.items():
            if file_id is not None and name not in keys:
                keys[name] = file_id
        return keys


def _file_ids_in(value: dict[str, Any], keys: dict[str, str]) -> set[str]:
    """The dataset's own files this verbatim row points at, as ``file_id`` values.

    Each string in the row is looked up whole — a bare id, a DRS URI, a file name
    — and any DRS uuid embedded in it is looked up too. Only handles :class:`FileKeys`
    indexed resolve, so a stray uuid in an unrelated field cannot inflate the count.
    """
    found: set[str] = set()
    for item in value.values():
        for text in item if isinstance(item, list) else [item]:
            if not isinstance(text, str):
                continue
            resolved = keys.get(text)
            if resolved is not None:
                found.add(resolved)
            # Most submitter values are names, accessions or numbers. The regex is
            # the expensive part of this loop and only a DRS URI can match it, so
            # the marker is checked first: ~2.7M strings on T2T_CHRY skip the scan.
            if _DRS_MARKER not in text:
                continue
            for match in _DRS_FILE_ID.finditer(text):
                resolved = keys.get(match.group(1).lower())
                if resolved is not None:
                    found.add(resolved)
    return found


def survey_verbatim(path: Path) -> tuple[list[TableCoverage], Reach, int]:
    """Measure one verbatim manifest: entity census, submitter fields, reach.

    Two streaming passes. The first counts entity types and fields, and collects
    the file ids and the biosample-to-donor map; the second needs those, so it
    walks the file again to resolve which files each submitter table names and
    to build the activity graph. Two passes over half a gigabyte cost seconds and
    keep the whole manifest out of memory, which one pass would not.

    Returns the per-type coverage, the reach, and how many of the dataset's files
    at least one dimension-carrying table names — a union over file ids, since a
    file named by both ``hifi`` and ``assembly`` is one file, not two.
    """
    counts: Counter = Counter()
    fields: dict[str, Counter] = defaultdict(Counter)
    file_ids: set[str] = set()
    keys = FileKeys()
    biosample_has_donor: dict[str, bool] = {}
    for entity_type, value in iter_verbatim_entities(path):
        counts[entity_type] += 1
        for name, item in value.items():
            if _is_filled(item):
                fields[entity_type][name] += 1
        if entity_type == VERBATIM_FILE:
            file_ids.add(keys.add(value))
        elif entity_type == VERBATIM_BIOSAMPLE:
            biosample_has_donor[value["biosample_id"]] = bool(value.get("donor_id"))

    reach, named = _verbatim_reach(path, file_ids, keys.resolved(), biosample_has_donor)

    tables = [
        TableCoverage(
            name=name,
            rows=rows,
            fields=dict(fields[name]),
            files_named=len(named[name]),
            encodes=_table_encodes(name) if not name.startswith(_HARMONIZED_PREFIX) else [],
        )
        for name, rows in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    dimension_files: set[str] = set()
    for table in tables:
        if table.is_submitter and table.carries_dimension:
            dimension_files |= named[table.name]
    return tables, reach, len(dimension_files)


def _id_list(value: dict[str, Any], key: str, path: Path) -> list[str]:
    """One activity's multi-valued id field, as the ids it holds.

    Raises on a bare string rather than accepting it: Python would iterate it
    character by character, unioning single-character ids into the component
    graph and quietly corrupting the reach numbers. Every anvil15 activity
    carries lists here, but the sibling harmonized fields (``file_id``,
    ``biosample_id``) are single-valued, so a manifest that changed shape should
    stop the survey rather than publish a wrong figure — the same stance
    :func:`iter_verbatim_entities` takes on a line it cannot read.
    """
    found = value.get(key)
    if found is None:
        return []
    if not isinstance(found, list):
        raise ValueError(f"{path.name}: anvil_activity {key} is {type(found).__name__}, not a list")
    return [item for item in found if isinstance(item, str)]


def _verbatim_reach(
    path: Path,
    file_ids: set[str],
    file_keys: dict[str, str],
    biosample_has_donor: dict[str, bool],
) -> tuple[Reach, dict[str, set[str]]]:
    """Walk the verbatim manifest's second pass: activity graph and table→file links.

    Two reach measurements come out of it, and they are different questions:

    - **single hop** — a file counts if the activity that *generated* it names a
      biosample directly. This is the traversal behind the 9,603 figure #337
      recorded for 1000G and #368's docstring repeated.
    - **transitive** — a file counts if any activity in its connected component
      names a biosample, where an activity connects every file it used or
      generated. Following an activity's inputs back to the biosample they came
      from is what an importer resolving provenance would do, so this is the
      honest answer to "can verbatim reach a donor for this file", and on 1000G
      it is 25,616 where single hop is 9,603.

    The transitive walk is undirected: it does not distinguish a file's ancestors
    from its descendants, so a file sharing an activity with a biosample-linked
    file counts as reaching. That makes it an upper bound; the single-hop count
    bounds the same quantity from below, and reporting both is #384's AC4.

    Returns the reach and, per submitter entity type, the dataset file ids that
    type's rows point at, resolved through ``file_keys``.
    """
    named: dict[str, set[str]] = defaultdict(set)
    components = _Components()
    marks: list[tuple[int, bool, bool]] = []
    single_hop_biosample: set[str] = set()
    single_hop_donor: set[str] = set()

    for entity_type, value in iter_verbatim_entities(path):
        if not entity_type.startswith(_HARMONIZED_PREFIX):
            named[entity_type] |= _file_ids_in(value, file_keys)
            continue
        if entity_type != VERBATIM_ACTIVITY:
            continue
        used = _id_list(value, "used_file_id", path)
        generated = _id_list(value, "generated_file_id", path)
        biosamples = _id_list(value, "used_biosample_id", path)

        seed: int | None = None
        for file_id in used + generated:
            index = components.index(file_id)
            if seed is None:
                seed = index
            else:
                components.union(seed, index)

        if not biosamples:
            continue
        has_donor = any(biosample_has_donor.get(b) for b in biosamples)
        if seed is not None:
            marks.append((seed, True, has_donor))
        # Single hop reaches only what this one activity produced.
        single_hop_biosample.update(generated)
        if has_donor:
            single_hop_donor.update(generated)

    # Components are final only now; a later activity may have merged two of them.
    reaches_biosample: set[int] = set()
    reaches_donor: set[int] = set()
    for seed, biosample, donor in marks:
        root = components.find(seed)
        if biosample:
            reaches_biosample.add(root)
        if donor:
            reaches_donor.add(root)

    reach = Reach(files=len(file_ids))
    for file_id in file_ids:
        index = components.known(file_id)
        if index is not None:
            root = components.find(index)
            reach.transitive_biosample += root in reaches_biosample
            reach.transitive_donor += root in reaches_donor
    reach.single_hop_biosample = len(single_hop_biosample & file_ids)
    reach.single_hop_donor = len(single_hop_donor & file_ids)
    return reach, named


# --- the run ------------------------------------------------------------------


def missing_manifests(root: Path, catalog: str) -> list[str]:
    """Manifests the sidecar names that are not on disk, as ``dataset (format)`` lines.

    Empty when the sidecar names nothing at all — that is :func:`sidecar_is_empty`'s
    question, not this one. Reporting it here as a missing manifest would make the
    caller say one manifest is missing when none was ever named.
    """
    datasets = sidecar_datasets(root, catalog)
    return [
        f"{title} ({fmt}): {manifest_path(root, catalog, title, fmt)}"
        for title in sorted(datasets)
        for fmt in FORMATS
        if not manifest_path(root, catalog, title, fmt).is_file()
    ]


def sidecar_is_empty(root: Path, catalog: str) -> bool:
    """Whether the catalog's sidecar names no dataset at all.

    Distinct from having missing manifests: nothing was ever downloaded here, so
    there is no incomplete set to name — a survey of nothing is still a failure,
    but a differently shaped one.
    """
    return not sidecar_datasets(root, catalog)


def run_survey(root: Path, catalog: str) -> Survey:
    """Measure every dataset the sidecar names. Assumes :func:`missing_manifests` passed."""
    entries = sidecar_datasets(root, catalog)
    survey = Survey(catalog=catalog)
    for title in sorted(entries):
        rows, columns, spellings = survey_compact(manifest_path(root, catalog, title, FORMAT_COMPACT))
        tables, reach, dimension_files = survey_verbatim(manifest_path(root, catalog, title, FORMAT_VERBATIM))
        snapshot = entries[title].file_count
        survey.datasets.append(
            DatasetSurvey(
                title=title,
                compact_rows=rows,
                snapshot_files=snapshot,
                columns=columns,
                absent_spellings=spellings,
                tables=tables,
                reach=reach,
                dimension_files=dimension_files,
            )
        )
        survey.snapshot_total += snapshot
    return survey


# --- formatting ---------------------------------------------------------------


def _pct(value: float) -> str:
    """A rate as a percentage without its sign, keeping both ends honest.

    A dataset where 6 files of 12,534 carry a donor is not the same as one where
    none do, and rounding would print both as ``0``; this prints ``<1``. The same
    goes for the top: this document uses 100% to mean complete — the governance
    sentence is gated on exactly that — so a rate that merely rounds to 100
    prints ``>99`` instead. Only 0 prints as ``0`` and only 1.0 as ``100``.
    """
    if value <= 0:
        return "0"
    if value < 0.005:
        return "<1"
    if value >= 1:
        return "100"
    if value > 0.995:
        return ">99"
    return f"{value * 100:.0f}"


def _plural(count: int, noun: str) -> str:
    return noun if count == 1 else f"{noun}s"


# --- readiness ----------------------------------------------------------------


def join_uniform(datasets: list[DatasetSurvey]) -> list[DatasetSurvey]:
    """The datasets filling all three ``JOIN_*`` columns at one rate.

    Measured rather than assumed: on anvil15 it is every dataset, which is what
    lets the report say the provenance join arrives whole or not at all, and what
    :func:`contradictions` checks #384's own diverging figure against.
    """
    return [d for d in datasets if d.join_uniform]


def _verdict(rate: float) -> str:
    if rate >= READY_HIGH:
        return "yes"
    if rate >= READY_LOW:
        return "partial"
    return "no"


def readiness(dataset: DatasetSurvey) -> dict[str, tuple[str, str]]:
    """Per consumer, a verdict and the number backing it.

    - ``dimensions`` (#369) — the share of files named by a submitter table that
      points at a dimension, either through its own name (``hifi``, ``chains_to_
      chm13_mc``) or through a populated field named for one (``reference_
      assembly``, ``instrument_model``). Both count: a table saying what its
      files are in a column is as importable as one saying it in its name.
    - ``governance`` (#336) — consent group and data use permission, the lower of
      the two. The phs accession is reported beside it rather than folded in: it
      is the one of the three that is not universal, and a dataset without it can
      still have its consent imported.
    - ``edges`` (#361) — the compact join's donor reach, with the verbatim
      transitive walk reported beside it but not used for the verdict. The
      transitive walk is an upper bound (it is undirected, so a file sharing an
      activity with a donor-linked file counts), and under the project's
      accuracy-over-coverage principle a go/no-go should not rest on an upper
      bound. On anvil15 this costs nothing — the compact join reaches at least as
      far as the transitive walk on every dataset — but on a corpus where
      verbatim reached further, this would say so in the basis rather than
      silently promoting the optimistic number to the verdict.
    """
    rate = dataset.dimension_file_rate
    tables = len(dataset.dimension_tables)
    by_name = len(dataset.name_encoding_tables)
    consent = min(dataset.rate(GOVERNANCE_CONSENT), dataset.rate(GOVERNANCE_DUO))
    phs = dataset.rate(GOVERNANCE_PHS)
    # Each count against its own denominator: the compact join is per compact row,
    # the transitive walk per anvil_file entity, and the two are not always the
    # same number. Dividing one by the other's total can exceed 100%.
    compact_donor = dataset.filled(JOIN_DONOR)
    donor_rate = compact_donor / dataset.compact_rows if dataset.compact_rows else 0.0
    transitive_rate = dataset.reach.transitive_donor / dataset.reach.files if dataset.reach.files else 0.0
    beside = f"verbatim transitive {_pct(transitive_rate)}%"
    basis = f"{_pct(rate)}% of verbatim files, {tables} {_plural(tables, 'table')} ({by_name} by name)"
    return {
        "dimensions": (_verdict(rate), basis),
        "governance": (_verdict(consent), f"consent/DUO {_pct(consent)}%, phs {_pct(phs)}%"),
        "edges": (
            _verdict(donor_rate),
            f"{compact_donor:,} of {dataset.compact_rows:,} compact rows ({_pct(donor_rate)}%), {beside}",
        ),
    }


# --- contradictions -----------------------------------------------------------


@dataclass(frozen=True)
class PriorClaim:
    """One claim written down somewhere, and how to test it against a survey.

    ``check`` returns one entry per disagreement, ``(source detail, what the
    manifests say)`` — empty when the survey agrees, or when the data the claim
    is about is not in this catalog. The detail is appended to ``source`` so a
    per-dataset check can name its dataset.

    Claims are data so that recording a new one, or retiring a resolved one, is
    a row in :data:`PRIOR_CLAIMS` rather than a branch inside a function.
    """

    source: str
    claim: str
    check: Callable[[Survey], list[tuple[str, str]]]


def _dataset(survey: Survey, title: str) -> DatasetSurvey | None:
    """One dataset by title, case-insensitively.

    The corpus carries both ``ANVIL_`` and ``AnVIL_`` prefixes, so an exact-case
    lookup is a check that stops running without saying so if the catalog
    re-cases a title.
    """
    return next((d for d in survey.datasets if d.title.casefold() == title.casefold()), None)


def _brief_null_fields(survey: Survey) -> list[tuple[str, str]]:
    """The brief says these are null on every row; report each place they are not."""
    labels = {
        "donors.phenotypic_sex": "donor sex",
        "donors.reported_ethnicity": "donor ancestry",
        "biosamples.biosample_type": "biosample type",
        "biosamples.anatomical_site": "anatomical site",
    }
    populated = [
        f"{label} {_pct(dataset.rate(column))}% in {dataset.title}"
        for column, label in labels.items()
        for dataset in survey.datasets
        if dataset.rate(column) > 0
    ]
    if not populated:
        return []
    return [
        (
            "",
            "Not null in the compact manifest: " + "; ".join(populated) + ". The brief measured a "
            "different extract than these manifests, or an older catalog; it needs scoping to whichever "
            "it measured.",
        )
    ]


def _verbatim_not_weaker(survey: Survey) -> list[tuple[str, str]]:
    """Report each dataset where the shortfall is the traversal, not the manifest.

    Both halves are needed. A single-hop shortfall alone does not refute the
    claim: where transitive closure still falls short of the compact join, the
    claim holds for that dataset and a refutation would be false.
    """
    found = []
    for dataset in survey.datasets:
        reach = dataset.reach
        join = dataset.filled(JOIN_DONOR)
        if reach.single_hop_donor < reach.transitive_donor and reach.transitive_donor >= join:
            found.append(
                (
                    f", on {dataset.title}",
                    f"Single hop reaches {reach.single_hop_donor:,} files, but transitive closure over the "
                    f"same activities reaches {reach.transitive_donor:,} against the compact join's "
                    f"{join:,}. The shortfall is the traversal, not the manifest.",
                )
            )
    return found


def _hprc_r2_table_rows(survey: Survey) -> list[tuple[str, str]]:
    """The claim gives one row count for every per-file-type table; check they share it."""
    dataset = _dataset(survey, "AnVIL_HPRC_R2")
    if dataset is None:
        return []
    off = [t for t in dataset.name_encoding_tables if t.rows != _HPRC_R2_CLAIMED_ROWS]
    if not off:
        return []
    listed = ", ".join(f"{t.name} {t.rows:,}" for t in sorted(off, key=lambda t: -t.rows)[:5])
    return [
        (
            "",
            f"{len(off)} of them are not {_HPRC_R2_CLAIMED_ROWS} rows: {listed}. The tables do not share "
            f"a row count; {_HPRC_R2_CLAIMED_ROWS} is the count of the largest group, not of all of them.",
        )
    ]


def _hprc_r2_join_diverges(survey: Survey) -> list[tuple[str, str]]:
    """The claim has the join columns diverging; check whether they ever do."""
    dataset = _dataset(survey, "AnVIL_HPRC_R2")
    if dataset is None or not dataset.join_uniform:
        return []
    together = join_uniform(survey.datasets)
    return [
        (
            "",
            f"`{JOIN_ACTIVITY}` is filled on {_pct(dataset.rate(JOIN_ACTIVITY))}% of its rows, the same "
            f"share as donor and biosample. Across all {len(survey.datasets)} datasets "
            f"{len(together)} fill the three join columns at an identical rate, so the join arrives "
            "whole or not at all — which is what #361 should plan against.",
        )
    ]


# The row count #384's body attributes to every one of HPRC_R2's per-file-type tables.
_HPRC_R2_CLAIMED_ROWS = 462

PRIOR_CLAIMS: tuple[PriorClaim, ...] = (
    PriorClaim(
        source="docs/briefs/comparability-gap.html",
        claim="Donor sex, ancestry, biosample type and anatomical site are null on every indexed row.",
        check=_brief_null_fields,
    ),
    PriorClaim(
        source="#337 / #368 (azul_manifest docstring)",
        claim="The verbatim entity chain reaches fewer files than the compact join, so verbatim is not "
        "a superset of compact.",
        check=_verbatim_not_weaker,
    ),
    PriorClaim(
        source="#384 (this issue's own body)",
        claim=f"AnVIL_HPRC_R2 carries ~20 per-file-type tables, each {_HPRC_R2_CLAIMED_ROWS} rows.",
        check=_hprc_r2_table_rows,
    ),
    PriorClaim(
        source="#384 (this issue's own body)",
        claim="AnVIL_HPRC_R2's compact join is 91% for donor and biosample but 23% for activity.",
        check=_hprc_r2_join_diverges,
    ),
)


def contradictions(survey: Survey) -> list[tuple[str, str, str]]:
    """Where this survey disagrees with a claim already written down (#384 AC6).

    Each entry is ``(source, the prior claim, what the manifests say)``, from
    running every :data:`PRIOR_CLAIMS` check against the survey. A claim a later
    manifest pull resolves stops being reported, instead of leaving stale prose
    in the document.
    """
    return [
        (prior.source + detail, prior.claim, measured)
        for prior in PRIOR_CLAIMS
        for detail, measured in prior.check(survey)
    ]


# --- rendering ----------------------------------------------------------------


def _short(title: str) -> str:
    """A dataset title with its AnVIL prefix dropped, for a table header."""
    for prefix in ("ANVIL_", "AnVIL_"):
        if title.startswith(prefix):
            return title[len(prefix) :]
    return title


def _rate_table(datasets: list[DatasetSurvey], keys: list[str], columns) -> list[str]:
    """One row per column, one cell per dataset, each the column's fill rate there."""
    return md_table(
        ["column", *keys],
        [[column, *[_pct(d.rate(column)) for d in datasets]] for column in columns],
        align="right",
    )


def render_report(survey: Survey) -> str:
    """The whole survey as markdown."""
    datasets = survey.datasets
    keys = [f"D{i}" for i in range(1, len(datasets) + 1)]
    out: list[str] = [
        "# What the AnVIL manifests carry",
        "",
        f"Measured from the `{survey.catalog}` manifests on disk by "
        "`scripts/generate_manifest_survey.py` (issue #384). No network: every figure below "
        "comes from `data/anvil/manifest/`. Regenerate with `make manifest-survey`; the same "
        "numbers unrounded are in `docs/manifest-survey.json`.",
        "",
        "This document measures. It classifies nothing and proposes no mapping — that is #369, "
        "#336 and #361, which it exists to scope.",
        "",
    ]

    out += ["## Datasets and row counts", ""]
    out += md_table(
        ["key", "dataset", "compact rows", "snapshot file count", "agree"],
        [
            [
                key,
                d.title,
                f"{d.compact_rows:,}",
                f"{d.snapshot_files:,}",
                "yes" if d.compact_rows == d.snapshot_files else "**no**",
            ]
            for key, d in zip(keys, datasets, strict=True)
        ],
        align="right",
    )
    agreement = (
        "matching the snapshot exactly"
        if survey.measured_total == survey.snapshot_total
        else f"**against the snapshot's {survey.snapshot_total:,}**"
    )
    out += [
        "",
        f"{len(datasets)} datasets, {survey.measured_total:,} compact rows in total, {agreement}.",
        "",
        "A note on the sidecar: `manifests.json` records a verbatim `rows` count that is the "
        "number of `anvil_file` entities, not the number of lines — a verbatim manifest holds "
        "every entity, so it has several times as many lines as the dataset has files.",
        "",
    ]

    out += _compact_section(survey, keys)
    out += _verbatim_section(survey)
    out += _vocabulary_gaps(survey)
    out += _reach_section(survey)
    out += _readiness_section(survey)
    out += _contradictions_section(survey)
    return "\n".join(out) + "\n"


def _compact_section(survey: Survey, keys: list[str]) -> list[str]:
    datasets = survey.datasets
    # Union rather than the first dataset's header: a dataset with an extra column
    # must not be silently dropped from the table, and one missing a column reads
    # as 0 for it, which `rate` already returns.
    columns: list[str] = []
    for dataset in datasets:
        columns += [c.column for c in dataset.columns if c.column not in columns]
    out = [
        "## Compact column coverage",
        "",
        "Percentage of each dataset's rows where the column holds something. A cell counts as "
        f"absent if, stripped and lowercased, it is one of {sorted(ABSENT_CELLS)!r}. Columns are "
        f"the manifests' own {len(columns)}, in manifest order; a dataset missing one of them "
        "reads as 0 for it.",
        "",
        "Keys: " + ", ".join(f"**{k}** {_short(d.title)}" for k, d in zip(keys, datasets, strict=True)),
        "",
    ]
    out += _rate_table(datasets, keys, columns)

    out += [
        "",
        "### The harmonized dimension columns",
        "",
        "These are the columns a classifier would not need to exist if they were filled. Their "
        "emptiness has been the standing justification for inferring at all; here it is measured.",
        "",
    ]
    out += _rate_table(datasets, keys, DIMENSION_COLUMNS)

    together = join_uniform(datasets)
    out += [
        "",
        "### The provenance join",
        "",
        f"`{JOIN_DONOR}`, `{JOIN_BIOSAMPLE}` and `{JOIN_ACTIVITY}` are filled at an identical rate on "
        f"{len(together)} of {len(datasets)} datasets"
        + (
            ", so the join arrives whole or not at all: a dataset that can reach a donor can reach its "
            "biosample and the activity that produced the file, and one that cannot reach any of them "
            "is missing all three."
            if len(together) == len(datasets)
            else ", so it can come apart; see the per-column table above for where."
        ),
        "",
    ]
    out += _rate_table(datasets, keys, (JOIN_DONOR, JOIN_BIOSAMPLE, JOIN_ACTIVITY))

    out += [
        "",
        "### Governance columns",
        "",
        "What #336 wants to import.",
        "",
    ]
    out += _rate_table(datasets, keys, (GOVERNANCE_CONSENT, GOVERNANCE_DUO, GOVERNANCE_PHS))

    spellings: Counter = Counter()
    for dataset in datasets:
        spellings.update(dataset.absent_spellings)
    observed = ", ".join(f"`{name}` {count:,}" for name, count in spellings.most_common())
    out += [
        "",
        "### Which absent spellings actually occur",
        "",
        f"Across every dataset: {observed or 'none'}. Any spelling in the absence rule that does "
        "not appear here cost nothing; one that appears in quantity is worth checking against the "
        "column it came from, in case a real value is being read as a gap.",
        "",
    ]
    return out


def _verbatim_section(survey: Survey) -> list[str]:
    out = [
        "## Verbatim entity census",
        "",
        "Every entity `type` in each dataset's verbatim manifest with its row count. `anvil_*` "
        "types are Azul's harmonized entities; everything else is the submitter's own Terra "
        "table, carried through unaltered.",
        "",
    ]
    for dataset in survey.datasets:
        out += [f"### {dataset.title}", ""]
        submitter = dataset.submitter_tables
        if not submitter:
            out += [
                "No submitter tables at all — only harmonized `anvil_*` entities. Verbatim adds "
                "nothing here that compact does not already carry.",
                "",
            ]
        rows = []
        for table in dataset.tables:
            encodes = "; ".join(
                f"{dimension} = {value}" if value else f"{dimension} = {NO_VOCABULARY_TERM}"
                for dimension, value in table.encodes
            )
            carried = "; ".join(f"`{name}` → {dimension}" for name, dimension in table.dimension_fields)
            rows.append(
                [
                    f"`{table.name}`",
                    "submitter" if table.is_submitter else "harmonized",
                    f"{table.rows:,}",
                    f"{table.files_named:,}" if table.is_submitter else "—",
                    encodes or "—",
                    carried or "—",
                ]
            )
        out += md_table(
            ["type", "origin", "rows", "files named", "name encodes", "dimension fields"], rows, align="right"
        )
        out += [""]
        for table in submitter:
            if not table.fields:
                continue
            fields = ", ".join(
                f"`{name}` {_pct(count / table.rows if table.rows else 0)}%"
                for name, count in sorted(table.fields.items(), key=lambda item: (-item[1], item[0]))
            )
            out += [f"- **`{table.name}`** ({table.rows:,} {_plural(table.rows, 'row')}): {fields}"]
        out += [""]
    return out


def _vocabulary_gaps(survey: Survey) -> list[str]:
    """The table-name tokens in use whose meaning the schema has no term for.

    A finding for #369 in its own right: these are classifications a submitter
    already made, in a name, that ``classification.yaml`` cannot currently
    record. Only tokens that actually occur in a table name somewhere in the
    corpus are listed — an unused entry in :data:`NAME_TOKENS` is not a gap.
    """
    seen: dict[str, set[str]] = defaultdict(set)
    for dataset in survey.datasets:
        for table in dataset.name_encoding_tables:
            for token in _NAME_SPLIT.split(table.name.lower()):
                meaning = NAME_TOKENS.get(token)
                if meaning is not None and meaning[1] is None:
                    seen[meaning[0]].add(token)
    if not seen:
        return []
    out = [
        "### Table names the vocabulary cannot express",
        "",
        "Tokens in use whose dimension is clear but for which `classification.yaml` has no "
        "term. The survey records the dimension and leaves the value null rather than inventing "
        "a string, so nothing downstream reads a term the schema does not define. Each of these "
        "is a submitter classification #369 would have to either map to an existing term or add "
        "one for.",
        "",
    ]
    out += md_table(
        ["dimension", "tokens in use"],
        [
            [dimension, ", ".join(f"`{token}`" for token in sorted(tokens))]
            for dimension, tokens in sorted(seen.items())
        ],
    )
    return [*out, ""]


def _reach_section(survey: Survey) -> list[str]:
    out = [
        "## Reach: how many files resolve to a biosample and a donor",
        "",
        "Three measurements of one question, per dataset.",
        "",
        "- **compact** — the file's own row carries a non-empty `biosamples.biosample_id` / "
        "`donors.donor_id`. This is Azul's materialized join.",
        "- **verbatim, single hop** — the file appears in some `anvil_activity`'s "
        "`generated_file_id`, and that same activity names a `used_biosample_id`. This is the "
        "traversal behind the 9,603 figure #337 recorded for 1000G.",
        "- **verbatim, transitive** — the file is in a connected component of the "
        "file/activity graph that contains an activity naming a biosample, where an activity "
        "connects every file it used or generated. Undirected, so it is an upper bound; single "
        "hop bounds the same quantity from below.",
        "",
    ]
    rows = []
    for dataset in survey.datasets:
        reach = dataset.reach
        rows.append(
            [
                _short(dataset.title),
                f"{reach.files:,}",
                f"{dataset.filled(JOIN_BIOSAMPLE):,}",
                f"{dataset.filled(JOIN_DONOR):,}",
                f"{reach.single_hop_biosample:,}",
                f"{reach.single_hop_donor:,}",
                f"{reach.transitive_biosample:,}",
                f"{reach.transitive_donor:,}",
            ]
        )
    out += md_table(
        [
            "dataset",
            "files",
            "compact biosample",
            "compact donor",
            "1-hop biosample",
            "1-hop donor",
            "transitive biosample",
            "transitive donor",
        ],
        rows,
        align="right",
    )
    out += [""]
    return out


def _readiness_section(survey: Survey) -> list[str]:
    out = [
        "## Consumer readiness",
        "",
        f"`yes` at or above {READY_HIGH:.0%}, `partial` at or above {READY_LOW:.0%}, `no` below "
        "it. Every cell carries the number it was judged on.",
        "",
        "- **#369 dimension import** — share of the dataset's verbatim files named by a submitter "
        "table that points at "
        "a dimension, through its own name (`hifi`, `chains_to_chm13_mc`) or through a populated "
        "field named for one (`reference_assembly`, `instrument_model`). The count in brackets "
        "says how many of those tables carry it in the name, which is the stronger signal: a "
        "name applies to every row, a field only to the rows where it is filled.",
        "- **#336 governance import** — consent group and data use permission, whichever is lower, "
        "with the phs accession reported beside it.",
        "- **#361 donor edges** — the compact join's donor reach. The verbatim transitive walk is "
        "reported beside it but does not set the verdict: it is an upper bound, and a go/no-go "
        "should not rest on one.",
        "",
    ]
    judged = [(d, readiness(d)) for d in survey.datasets]
    out += md_table(
        ["dataset", "#369 dimensions", "#336 governance", "#361 donor edges"],
        [
            [
                _short(d.title),
                f"{v['dimensions'][0]} ({v['dimensions'][1]})",
                f"{v['governance'][0]} ({v['governance'][1]})",
                f"{v['edges'][0]} ({v['edges'][1]})",
            ]
            for d, v in judged
        ],
    )

    none_of_them = [_short(d.title) for d, v in judged if all(entry[0] == "no" for entry in v.values())]
    # "no" is a band (below the bar), not a zero. A dataset at 6% belongs in the
    # under-the-bar list, never in a sentence that says it has none — the table
    # directly above prints its non-zero number.
    zero_dimensions = [_short(d.title) for d, _v in judged if d.dimension_files == 0]
    under_dimensions = [_short(d.title) for d, v in judged if v["dimensions"][0] == "no" and d.dimension_files > 0]
    # Zero means neither manifest reaches a donor; the verdict rests on the join
    # alone, but "none at all" must account for both or it would overstate.
    reachable = {d.title: max(d.filled(JOIN_DONOR), d.reach.transitive_donor) for d, _v in judged}
    zero_edges = [_short(d.title) for d, _v in judged if reachable[d.title] == 0]
    under_edges = [_short(d.title) for d, v in judged if v["edges"][0] == "no" and reachable[d.title] > 0]
    complete = all(d.rate(GOVERNANCE_CONSENT) == 1.0 and d.rate(GOVERNANCE_DUO) == 1.0 for d in survey.datasets)
    out += [
        "",
        ("Supports none of the three: " + ", ".join(none_of_them) + ".")
        if none_of_them
        else "Every dataset supports at least one of the three.",
        "",
        "Governance is the flat one: consent group and data use permission are filled on every "
        "row of every dataset, so #336 is unblocked corpus-wide and only the phs accession varies."
        if complete
        else "Consent group and data use permission are not complete everywhere; see the table.",
        "",
    ]
    if zero_dimensions:
        out += ["No dimension-carrying submitter table at all: " + ", ".join(zero_dimensions) + ".", ""]
    if under_dimensions:
        out += [
            f"Some dimension-carrying tables but under the {READY_LOW:.0%} bar: " + ", ".join(under_dimensions) + ".",
            "",
        ]
    if zero_edges:
        out += ["No donor reachable from either manifest: " + ", ".join(zero_edges) + ".", ""]
    if under_edges:
        out += [
            f"Some donors reachable but under the {READY_LOW:.0%} bar: " + ", ".join(under_edges) + ".",
            "",
        ]
    return out


def _contradictions_section(survey: Survey) -> list[str]:
    found = contradictions(survey)
    out = [
        "## Contradictions",
        "",
        "Where these measurements disagree with something already written down. Each is "
        "re-checked on every run, so one that a later manifest pull resolves stops appearing "
        "here rather than lingering as stale prose.",
        "",
    ]
    if not found:
        out += ["Nothing measured here disagrees with a recorded claim.", ""]
        return out
    for source, claim, measured in found:
        out += [f"### {source}", "", f"**Claimed:** {claim}", "", f"**Measured:** {measured}", ""]
    return out


# --- the JSON sidecar ---------------------------------------------------------


def survey_data(survey: Survey) -> dict[str, Any]:
    """Every number the markdown rounds, for a consumer that would rather not parse it."""
    return {
        "catalog": survey.catalog,
        "snapshot_total": survey.snapshot_total,
        "measured_total": survey.measured_total,
        "thresholds": {"yes": READY_HIGH, "partial": READY_LOW},
        "absent_cells": sorted(ABSENT_CELLS),
        "datasets": {
            dataset.title: {
                "compact_rows": dataset.compact_rows,
                "snapshot_files": dataset.snapshot_files,
                "dimension_files": dataset.dimension_files,
                "dimension_file_rate": dataset.dimension_file_rate,
                "compact_columns": {
                    column.column: {"filled": column.filled, "rows": column.rows, "rate": column.rate}
                    for column in dataset.columns
                },
                "absent_spellings": dict(dataset.absent_spellings),
                "verbatim_types": {
                    table.name: {
                        "rows": table.rows,
                        "origin": "submitter" if table.is_submitter else "harmonized",
                        "files_named": table.files_named,
                        # value is null where the vocabulary has no term for what the
                        # name says; the dimension is still known. #369 reads both.
                        "name_encodes": [{"dimension": d, "value": v} for d, v in table.encodes],
                        "dimension_fields": [{"field": f, "dimension": d} for f, d in table.dimension_fields],
                        "fields": {
                            name: {"filled": count, "rate": count / table.rows if table.rows else 0.0}
                            for name, count in sorted(table.fields.items())
                        },
                    }
                    for table in dataset.tables
                },
                # asdict, not a hand-written spelling: a field added to Reach reaches
                # the sidecar without a second edit here. The compact join is not in
                # it — it is under compact_columns, where every column's count lives.
                "reach": asdict(dataset.reach),
                "readiness": {
                    consumer: {"verdict": verdict, "basis": basis}
                    for consumer, (verdict, basis) in readiness(dataset).items()
                },
            }
            for dataset in survey.datasets
        },
        "contradictions": [
            {"source": source, "claim": claim, "measured": measured}
            for source, claim, measured in contradictions(survey)
        ],
    }
