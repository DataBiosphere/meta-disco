"""Read AnVIL's tables into evidence files, through a slot map (#369, #497).

The verbatim manifests (#368) carry the submitter tables unaltered, and the slot map
(`slot_map`) says which of their columns and names speak to which slot. This module is
the importer between the two: it checks the map against the manifests, then writes,
per dataset, one generation of evidence files with one file per mapped table. It is an
importer in the contract's sense (1.2, 1.3): it transcribes what a source wrote and
maps structure, never meaning. No vocabulary, no value mapping, no claim — ``PACBIO_SMRT``
is written as ``PACBIO_SMRT`` and what it means is the translation table's (#414).

**Transcription** (contract 1.4) is :func:`_transcribe`'s: a string verbatim, the
empty string included; a list as its JSON array; a null or empty-list cell skipped and
counted once per row and column. A name span is written in the name's casing.

**Provenance** names the value's column. An evidence row's ``column`` is the cell the
raw value came from, not the file-link column that reached the file; a ``table_name``
source has no column, and a ``column_name`` source names the column whose name it is.
The file itself is named by its DRS URI, which the submitter wrote in the link column
and AnVIL's ``anvil_file`` entity carries in ``drs_uri`` or ``file_ref``
(``ANVIL_FILE_HANDLE_COLUMNS``) — so ``source_key`` and ``target_key`` are the same
string, resolved here against the dataset's own ``anvil_file`` entities:
a link an importer cannot resolve is counted per column and not written.

**A folder entry** (``slot_map``, #604) reaches its files by storage path instead: a row's
cell names a top folder, and the files are the dataset's ``anvil_file`` entities whose
``file_path`` begins with the entry's prefix for it (:meth:`DatasetFiles.under`), each
named by its ``file_ref`` as the published map names it. The evidence row is the same
row a link would have written; it does not record how the file was reached, as a link
entry's row does not record its link column.

**An import is a generation** (`source_evidence.generation_dir`): written once, never
over an earlier one, and read by ``discover`` as the newest per dataset. Within-source
contradictions pass through — a file reached by two tables of one dataset that spell
different assemblies receives both spans, and which is right is the resolver's (4.8).

**One importer, two maps** (#497). A map's ``source_type`` is every envelope's
``source_type`` and picks the directory (:data:`EVIDENCE_DIRS`); :func:`_check_kind`
holds each map to AnVIL's published table (``PUBLISHED_TABLE``, contract 7.12), at
``check`` and at import.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .azul_manifest import (
    ANVIL_FILE_HANDLE_COLUMNS,
    DRS_PREFIX,
    FORMAT_COMPACT,
    FORMAT_VERBATIM,
    PUBLISHED_TABLE,
    REPOSITORY,
    VERBATIM_FILE,
    cell_as_written,
    iter_verbatim_entities,
    link_handles,
    manifest_path,
    sidecar_datasets,
    sidecar_requested_at,
)
from .models import JOIN_KEY_DRS_URI, SAMPLES_FIELD, SOURCE_PUBLISHED_VALUE, SOURCE_REPOSITORY_METADATA, ClaimSource
from .sample_identity import SAMPLE, Identifier, IdentifierRuleSet, identifier_rules, name_contradicts
from .schema.classification_model import ImporterSourceTypeEnum, JoinKeyEnum
from .slot_map import SOURCE_CELL, SOURCE_COLUMN_NAME, ColumnEntry, SlotMap, SlotSource
from .source_evidence import (
    EvidenceEntry,
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    claim_source_for,
    evidence_file_path,
    generation_dir,
    new_generation,
    staged_generation,
    write_evidence_file,
)

# Where a map's generations go under the evidence root, by the kind of source the map
# declares. `source_evidence.discover` keys supersession on source directory, version and
# dataset, and this directory is the part of that key a map's kind decides, so it is
# derived from the map rather than passed beside it: two maps of one kind supersede
# each other's generations of a dataset, and that is the intent; two kinds never do.
PUBLISHED_DIR = f"{REPOSITORY}_published"
EVIDENCE_DIRS = {SOURCE_REPOSITORY_METADATA: REPOSITORY, SOURCE_PUBLISHED_VALUE: PUBLISHED_DIR}

# The `anvil_file` columns a folder entry reads (#604): the file's storage path within its
# dataset (#717), and the DRS URI it names the file by — TDR's own column, which a
# snapshot-derived record's `drs_uri` is (`snapshot_input`) and the published map keys by.
FILE_PATH = "file_path"
FILE_REF = "file_ref"


def evidence_dir(slot_map: SlotMap) -> str:
    """The directory under the evidence root a map's generations go to (:data:`EVIDENCE_DIRS`)."""
    directory = EVIDENCE_DIRS.get(slot_map.source_type)
    if directory is None:
        raise ValueError(f"map kind {slot_map.source_type!r} has no evidence directory here: {sorted(EVIDENCE_DIRS)}")
    return directory


def chosen_datasets(mapped: list[str], datasets: list[str] | None) -> list[str]:
    """A map's datasets (``mapped``), or ``datasets`` each once in order — not checked against the map.

    Shared with the lineage importer (``anvil_lineage``, #583).
    """
    return mapped if datasets is None else list(dict.fromkeys(datasets))


def verbatim_manifest(manifest_root: Path, catalog: str, dataset: str, named: dict) -> Path | str:
    """The dataset's verbatim manifest, or why an importer cannot read it.

    ``named`` is the catalog's sidecar datasets (``sidecar_datasets``). Returns the path
    when the sidecar names the dataset and its verbatim manifest is on disk; otherwise
    one line, a string, saying which: not named, only the compact manifest (which
    is Azul's join and not a source an importer reads), or no manifest at all. Shared
    with the lineage importer (``anvil_lineage``, #583), so both refuse the same state in
    the same words.
    """
    if dataset not in named:
        return f"{dataset}: not a dataset the {catalog} sidecar names"
    path = manifest_path(manifest_root, catalog, dataset, FORMAT_VERBATIM)
    if path.is_file():
        return path
    compact = manifest_path(manifest_root, catalog, dataset, FORMAT_COMPACT)
    if compact.is_file():
        return (
            f"{dataset}: only the compact manifest is on disk ({compact}), which is Azul's join and not a "
            f"source this importer reads; no verbatim manifest at {path}"
        )
    return f"{dataset}: no verbatim manifest at {path}"


@dataclass
class TableImport:
    """What one mapped table produced, and what it could not.

    ``no_link``, ``not_link`` and ``unresolved`` are per file-link column: rows whose link
    cell held nothing, rows whose cell held something that is not a DRS URI (which
    ``check`` reports and an import still counts, so ``describe`` shows it), and handles
    not among the dataset's own files. A folder column (#604) counts its empty cells in
    ``no_link`` too, and has two of its own: ``not_folder``, rows whose cell is not a top
    folder's name, and ``empty_folder``, rows whose folder reaches none of the dataset's
    files; ``check`` reports both. ``null_cells`` is per cell column, once per row
    and column, counting null and empty-list cells on the rows whose link resolved.
    ``files`` is the distinct files that received at least one evidence row;
    ``written`` counts the rows, and exceeds it wherever a file receives more than one.
    """

    table: str
    path: Path
    rows: int = 0
    written: int = 0
    files: set[str] = field(default_factory=set)
    no_link: Counter = field(default_factory=Counter)
    not_link: Counter = field(default_factory=Counter)
    unresolved: Counter = field(default_factory=Counter)
    not_folder: Counter = field(default_factory=Counter)
    empty_folder: Counter = field(default_factory=Counter)
    null_cells: Counter = field(default_factory=Counter)


@dataclass
class DatasetImport:
    """One generation of one dataset: where it went and what each table produced."""

    dataset: str
    generation: str
    directory: Path
    tables: list[TableImport]

    @property
    def files(self) -> int:
        """Distinct files that received at least one evidence row, across the tables."""
        return len(set().union(*(table.files for table in self.tables)))


@dataclass(frozen=True)
class DatasetFiles:
    """A dataset's own files: every DRS URI its ``anvil_file`` entities carry
    (``ANVIL_FILE_HANDLE_COLUMNS``), and each file's storage path with its ``file_ref``,
    sorted by path for :meth:`under`. A file with no path or no ``file_ref`` is in
    ``handles`` only."""

    handles: frozenset[str]
    by_path: tuple[tuple[str, str], ...]

    def under(self, prefix: str) -> list[str]:
        """The ``file_ref`` of each file whose storage path begins with ``prefix``, in path order."""
        found = []
        for i in range(bisect_left(self.by_path, (prefix,)), len(self.by_path)):
            path, handle = self.by_path[i]
            if not path.startswith(prefix):
                break
            found.append(handle)
        return found


def dataset_files(path: Path) -> DatasetFiles:
    """The dataset's own files, from its verbatim manifest's ``anvil_file`` entities."""
    handles: set[str] = set()
    by_path = []
    for _table, value in iter_verbatim_entities(path, {VERBATIM_FILE}):
        for column in ANVIL_FILE_HANDLE_COLUMNS:
            handles.update(link_handles(value.get(column)) or [])
        file_path, ref = value.get(FILE_PATH), link_handles(value.get(FILE_REF))
        if isinstance(file_path, str) and file_path and ref:
            by_path.extend((file_path, handle) for handle in ref)
    return DatasetFiles(handles=frozenset(handles), by_path=tuple(sorted(by_path)))


def top_folder(value: object) -> str | None:
    """``value`` where it names a top folder of a dataset's storage — a non-empty string with no
    ``/``, not ``.`` or ``..``, and not a DRS URI — else None."""
    if (
        isinstance(value, str)
        and value not in ("", ".", "..")
        and "/" not in value
        and not value.startswith(DRS_PREFIX)
    ):
        return value
    return None


def _no_cell(value: object) -> bool:
    """A cell that holds nothing, as :func:`link_handles` reads one: null, the empty string or the empty list."""
    return value is None or value == "" or value == []


# --- checking the map against the manifests -----------------------------------


def check(slot_map: SlotMap, manifest_root: Path, catalog: str, datasets: list[str] | None = None) -> list[str]:
    """How the map disagrees with the manifests on disk, one line per problem; empty when none.

    First :func:`_check_kind` (contract 7.12), then per mapped dataset (or those in
    ``datasets``, which must be in the map): the sidecar names it and its verbatim
    manifest is on disk — a compact manifest alone is named as not a source this
    importer reads. Per mapped table: at least one row of that type exists. Per
    file-link column: it appears on some row, and every non-empty value it holds is a
    DRS URI or a list of them. Per folder column (#604), what :func:`_check_folders`
    checks. Per cell: the column appears on some row of its table
    and is not itself a file-link column — a column is one kind, never two (contract
    2.7). Every chosen dataset is checked, and within one every table and column, so a
    map edited in one sitting is answered in one pass; a dataset whose manifest is
    missing, or a table with no rows, masks the problems beneath it until that one is
    fixed.
    """
    named = sidecar_datasets(manifest_root, catalog)
    known = slot_map.datasets()
    chosen = chosen_datasets(known, datasets)
    problems = _check_kind(slot_map, set(chosen))
    for dataset in chosen:
        if dataset not in known:
            problems.append(f"{dataset}: not in the slot map")
            continue
        path = verbatim_manifest(manifest_root, catalog, dataset, named)
        if isinstance(path, str):
            problems.append(path)
            continue
        problems += _check_dataset(slot_map, dataset, path)
    return problems


def _check_kind(slot_map: SlotMap, datasets: set[str]) -> list[str]:
    """The map's kind against this importer, over ``datasets``' entries only.

    It has an evidence directory here, and it holds to the published-table declaration:
    a ``published_value`` map maps exactly ``REPOSITORY``'s published table — the entry
    ``record_keys.PUBLISHED_TABLES`` carries for the repository this importer's evidence is
    about — and a ``repository_metadata`` map does not map it.
    """
    try:
        evidence_dir(slot_map)
    except ValueError as exc:
        return [str(exc)]
    published = PUBLISHED_TABLE
    tables = {(e.dataset, e.table) for e in slot_map.entries if e.dataset in datasets}
    if slot_map.source_type == SOURCE_PUBLISHED_VALUE:
        return [
            f"{dataset}/{table}: a {SOURCE_PUBLISHED_VALUE} map maps only {REPOSITORY}'s published table, {published!r}"
            for dataset, table in sorted(tables)
            if table != published
        ]
    return [
        f"{dataset}/{table}: {REPOSITORY}'s published table is the {SOURCE_PUBLISHED_VALUE} map's, not a "
        f"{slot_map.source_type} map's"
        for dataset, table in sorted(tables)
        if table == published
    ]


def _check_dataset(slot_map: SlotMap, dataset: str, path: Path) -> list[str]:
    tables = slot_map.tables(dataset)
    wanted = {table: [e.column for e in slot_map.columns(dataset, table) if not e.is_folder] for table in tables}
    cells = {table: sorted(slot_map.cells(dataset, table)) for table in tables}
    rows: Counter = Counter()
    columns_seen: dict[str, set[str]] = {table: set() for table in tables}
    not_links: dict[tuple[str, str], object] = {}
    # A cell is a link column when every non-empty value it holds is a link: `None`
    # until a non-empty value is seen, then whether all of them so far were links.
    cell_is_link: dict[tuple[str, str], bool | None] = {(t, c): None for t in tables for c in cells[t]}
    for table, row in iter_verbatim_entities(path, tables):
        rows[table] += 1
        columns_seen[table].update(row)
        for column in wanted[table]:
            if (table, column) not in not_links and link_handles(row.get(column)) == []:
                not_links[(table, column)] = row[column]
        for cell in cells[table]:
            handles = link_handles(row.get(cell))
            if handles is not None and cell_is_link[(table, cell)] is not False:
                cell_is_link[(table, cell)] = handles != []
    problems = _check_sample_names(slot_map, dataset, path) + _check_folders(slot_map, dataset, path)
    for table in tables:
        if not rows[table]:
            problems.append(f"{dataset}/{table}: no row of this type in the manifest")
            continue
        for column in wanted[table]:
            if column not in columns_seen[table]:
                problems.append(f"{dataset}/{table}/{column}: no row carries this column")
            elif (table, column) in not_links:
                problems.append(
                    f"{dataset}/{table}/{column}: holds {not_links[(table, column)]!r}, "
                    "not a DRS URI or a list of them — not a file-link column"
                )
        for cell in cells[table]:
            if cell not in columns_seen[table]:
                problems.append(f"{dataset}/{table}: cell {cell!r} is not a column of this table")
            elif cell_is_link[(table, cell)]:
                problems.append(
                    f"{dataset}/{table}: cell {cell!r} holds DRS URIs — a file-link column, not a metadata value"
                )
    return problems


def _check_folders(slot_map: SlotMap, dataset: str, path: Path) -> list[str]:
    """How the dataset's folder columns (#604) disagree with its manifest, one line per problem.

    Per folder column: it appears on some row of its table; every non-empty cell names a top
    folder (:func:`top_folder`); each folder reaches at least one of the dataset's files; and
    no file is reached from two rows, which would give one file two rows' values from one
    entry — the one-to-one a folder entry is declared on.
    """
    entries = [e for e in slot_map.entries if e.dataset == dataset and e.is_folder]
    if not entries:
        return []
    files = dataset_files(path)
    seen: set[tuple[str, str]] = set()
    not_folder: dict[tuple[str, str], object] = {}
    empty: dict[tuple[str, str], list[str]] = {}
    reached: dict[tuple[str, str], Counter] = {(e.table, e.column): Counter() for e in entries}
    for table, row in iter_verbatim_entities(path, {e.table for e in entries}):
        for entry in entries:
            if entry.table != table or entry.column not in row:
                continue
            key = (table, entry.column)
            seen.add(key)
            value = row[entry.column]
            if _no_cell(value):
                continue
            folder = top_folder(value)
            if folder is None:
                not_folder.setdefault(key, value)
                continue
            handles = files.under(entry.folder_prefix(folder))
            if not handles:
                empty.setdefault(key, []).append(folder)
            reached[key].update(handles)
    problems = []
    for entry in entries:
        key, at = (entry.table, entry.column), f"{dataset}/{entry.table}/{entry.column}"
        if key not in seen:
            problems.append(f"{at}: no row carries this column")
            continue
        if key in not_folder:
            problems.append(f"{at}: holds {not_folder[key]!r}, not a top folder's name — not a folder column")
        if key in empty:
            folders = ", ".join(repr(entry.folder_prefix(f)) for f in sorted(set(empty[key])))
            problems.append(f"{at}: reaches none of the dataset's files under {folders}")
        twice = sum(1 for n in reached[key].values() if n > 1)
        if twice:
            problems.append(f"{at}: {twice:,} files are reached from more than one row")
    return problems


def _check_sample_names(slot_map: SlotMap, dataset: str, path: Path) -> list[str]:
    """A ``samples`` column whose cell most of its files' names contradict, one line each (#357).

    For each file-link column the map reads ``samples`` for, each file whose name carries
    exactly one identifier is compared with the samples the row's cell names (each element of
    a list cell, all recognised, as reconcile reads it), where a sample shares the name's
    namespace (``sample_identity``): ``HG01105.final.cram`` in a row whose cell is ``HG01106``
    disagrees. A row whose cell holds a string no rule recognises is not compared. A column where more of these files disagree than agree holds
    another row's files under the cell it is mapped to — a parent's reads in its child's row
    (`mat_ilmn` read as `sample_id`) — and is a problem. A few disagreeing files are not
    (a submitter's slip); reconcile reports a file whose name contradicts the samples it
    settles to.
    """
    sampled = {
        (entry.table, entry.column): entry.slots[SAMPLES_FIELD][0].value
        for entry in slot_map.entries
        if entry.dataset == dataset and SAMPLES_FIELD in entry.slots
    }
    if not sampled:
        return []
    rules = identifier_rules()
    names: dict[str, str] = {}
    compared: list[tuple[str, str, frozenset[Identifier], list[str]]] = []
    tables = {table for table, _ in sampled}
    for table, row in iter_verbatim_entities(path, tables | {VERBATIM_FILE}):
        if table == VERBATIM_FILE:
            for column in ANVIL_FILE_HANDLE_COLUMNS:
                for handle in link_handles(row.get(column)) or []:
                    names[handle] = str(row.get("file_name") or "")
            continue
        for (mapped_table, column), cell in sampled.items():
            members = _cell_samples(row.get(cell), dataset, rules) if mapped_table == table else None
            if members:
                compared.append((table, column, members, link_handles(row.get(column)) or []))
    agree: Counter = Counter()
    disagree: Counter = Counter()
    example: dict[tuple[str, str], str] = {}
    for table, column, members, handles in compared:
        for handle in handles:
            named = rules.in_name_one(names.get(handle, ""))
            if named is not None and named in members:
                agree[(table, column)] += 1
            elif named is not None and name_contradicts(named, members):
                disagree[(table, column)] += 1
                cell = ", ".join(sorted(m.id for m in members))
                example.setdefault((table, column), f"{names[handle]!r} in the row whose cell is {cell!r}")
    return [
        f"{dataset}/{table}/{column}: samples read from {sampled[(table, column)]!r}, but {n:,} of "
        f"{n + agree[(table, column)]:,} files whose name names one sample name another (e.g. "
        f"{example[(table, column)]}) — the column holds files of another row's sample"
        for (table, column), n in sorted(disagree.items())
        if n > agree[(table, column)]
    ]


def _cell_samples(value: object, dataset: str, rules: IdentifierRuleSet) -> frozenset[Identifier] | None:
    """The samples a cell names, each element of a list cell, as reconcile reads them; None where any is unrecognised."""
    elements = value if isinstance(value, list) else [value]
    members = set()
    for element in elements:
        got = rules.recognise(element, dataset, SAMPLE) if isinstance(element, str) else None
        if got is None:
            return None
        members.add(got.identifier)
    return frozenset(members) or None


# --- importing -----------------------------------------------------------------


def import_all(
    slot_map: SlotMap,
    manifest_root: Path,
    catalog: str,
    service: str,
    evidence_root: Path,
    datasets: list[str] | None = None,
    generation: str | None = None,
) -> list[DatasetImport]:
    """Import every dataset the map names (or ``datasets``), each as one new generation.

    The stamp is shared across the datasets of one run so the run is one generation on
    disk; each dataset is still imported whole and independently, and once however many
    times it is named. Raises before writing anything if a named dataset is not in the map.
    """
    known = slot_map.datasets()
    chosen = chosen_datasets(known, datasets)
    unknown = [d for d in chosen if d not in known]
    if unknown:
        raise ValueError(f"not in the slot map: {unknown}")
    stamp = generation if generation is not None else new_generation()
    return [
        import_dataset(slot_map, manifest_root, catalog, service, dataset, evidence_root, stamp) for dataset in chosen
    ]


def import_dataset(
    slot_map: SlotMap,
    manifest_root: Path,
    catalog: str,
    service: str,
    dataset: str,
    evidence_root: Path,
    generation: str | None = None,
) -> DatasetImport:
    """Write one generation of evidence files for one dataset.

    Two kinds of pass over the manifest: one to collect the dataset's own files
    (:func:`dataset_files`: its ``anvil_file`` DRS URIs and storage paths), then one per mapped table to write that table's file.
    Per-table passes rather than one pass fanning out to every table's writer, so each
    file keeps ``write_evidence_file``'s write-then-rename guarantee on its own; each
    pass parses only the lines that name its table (``iter_verbatim_entities``'s gate).

    The generation directory must not exist: an import never writes over another. It
    is a generation only once every table is written: the files go to a staging
    directory (``source_evidence.staging_dir``) that is renamed into place at the end,
    so a generation exists whole or not at all. A failure part-way — a bad row, a full
    disk, an interrupt — removes the staging directory before the error propagates; a
    hard kill leaves it as ``<stamp>.partial``, which ``discover`` never reads, the run
    reports as unfinished, and this refuses to write over. A mapped table that writes
    no row at all is such a failure: a table the map names should reach files, and one
    that reaches none is the map disagreeing with the catalog (contract 5.3), not an
    empty result.
    The target system and the envelope's source repository are both ``REPOSITORY``, the
    repository the manifests came from, and the envelope's source ``url`` is ``service``,
    the Azul service the manifests under ``manifest_root`` were pulled from (a
    deployment's ``service``, #500) — passed in, because nothing on disk records it; the envelope's ``source_type`` is the map's, and
    so is the directory under the evidence root (:func:`evidence_dir`). The map's kind
    is held to :func:`_check_kind` here as well as at ``check``, so this cannot write a
    file the run would refuse.
    """
    problems = _check_kind(slot_map, {dataset})
    if problems:
        raise ValueError("; ".join(problems))
    stamp = generation if generation is not None else new_generation()
    directory = generation_dir(evidence_root, evidence_dir(slot_map), catalog, dataset, stamp)
    path = manifest_path(manifest_root, catalog, dataset, FORMAT_VERBATIM)
    # When the *source* was fetched — the manifest's request time, not the import's. A
    # sidecar that cannot say is refused: an evidence file must record it, and inventing
    # the import time would be a fetch the file never made.
    fetched_at = sidecar_requested_at(manifest_root, catalog, dataset, FORMAT_VERBATIM)
    if fetched_at is None:
        raise ValueError(
            f"{dataset}: the {catalog} sidecar records no {FORMAT_VERBATIM} requested_at to write as fetched_at"
        )
    files = dataset_files(path)
    # What every table's envelope shares. The generated model types the two vocabulary
    # members as its enums and stores their values (`use_enum_values`), so the runtime
    # constants are wrapped for the type checker and read back as the plain strings
    # they are; the timestamp is carried as the schema declares it, an ISO 8601 string,
    # and the sidecar's `+00:00`/naive form round-trips unchanged.
    source_type = ImporterSourceTypeEnum(slot_map.source_type)
    target = EvidenceTarget(system=REPOSITORY, dataset=dataset, version=catalog)
    target_key = JoinKeyEnum(JOIN_KEY_DRS_URI)
    fetched = fetched_at.isoformat()
    tables = []
    with staged_generation(directory) as staging:
        for table in slot_map.tables(dataset):
            file_source = EvidenceFileSource(repository=REPOSITORY, dataset=dataset, table=table, url=service)
            envelope = EvidenceFileEnvelope(
                source=file_source,
                source_type=source_type,
                source_version=catalog,
                source_key=JOIN_KEY_DRS_URI,
                target=target,
                target_key=target_key,
                fetched_at=fetched,
            )
            result = TableImport(table=table, path=evidence_file_path(directory, table))
            entries = _table_entries(path, table, slot_map.columns(dataset, table), files, file_source, result)
            result.written = write_evidence_file(evidence_file_path(staging, table), envelope, entries)
            if not result.written:
                raise ValueError(
                    f"{dataset}/{table}: no evidence row written — every link was empty or outside the "
                    f"dataset's files, or every mapped cell was null; the map disagrees with {catalog} here"
                )
            tables.append(result)
    return DatasetImport(dataset=dataset, generation=stamp, directory=directory, tables=tables)


def _table_entries(
    path: Path,
    table: str,
    columns: list[ColumnEntry],
    files: DatasetFiles,
    source: EvidenceFileSource,
    result: TableImport,
) -> Iterator[EvidenceEntry]:
    """Every evidence row one table yields, streamed row by row, counting into ``result``."""
    by_column: dict[str | None, ClaimSource] = {}
    for _type, row in iter_verbatim_entities(path, {table}):
        result.rows += 1
        nulls: set[str] = set()
        for entry in columns:
            for handle in _reached(entry, row, files, result):
                if handle not in files.handles:
                    result.unresolved[entry.column] += 1
                    continue
                for slot, sources in entry.slots.items():
                    for spec in sources:
                        raw, column = _transcribe(spec, row, entry.column, nulls, result)
                        if raw is None:
                            continue
                        claim_source = by_column.get(column)
                        if claim_source is None:
                            claim_source = by_column[column] = claim_source_for(source, column)
                        # Counted here and not when the link resolved: a file whose every
                        # mapped cell is null receives nothing, and is not "a file with evidence".
                        result.files.add(handle)
                        yield EvidenceEntry(field=slot, target_key_value=handle, raw_value=raw, source=claim_source)


def _reached(entry: ColumnEntry, row: dict, files: DatasetFiles, result: TableImport) -> list[str]:
    """The files one row reaches through one entry, counting into ``result`` the rows that reach none.

    A link entry's are the DRS URIs its cell holds; a folder entry's are the files under the
    folder its cell names (:meth:`DatasetFiles.under`).
    """
    value = row.get(entry.column)
    if _no_cell(value):
        result.no_link[entry.column] += 1
        return []
    if not entry.is_folder:
        links = link_handles(value)
        if not links:
            result.not_link[entry.column] += 1
        return links or []
    folder = top_folder(value)
    if folder is None:
        result.not_folder[entry.column] += 1
        return []
    handles = files.under(entry.folder_prefix(folder))
    if not handles:
        result.empty_folder[entry.column] += 1
    return handles


def _transcribe(
    spec: SlotSource, row: dict, link_column: str, nulls: set[str], result: TableImport
) -> tuple[str | None, str | None]:
    """The raw value one source yields for this row, and the column to record for it.

    ``None`` for a null or empty-list cell, counted once per row against its column:
    ``nulls`` is the row's own set, shared across every slot and file the row feeds. An
    empty list is treated as null and not as the JSON ``[]`` because it observes
    nothing; the empty string is kept because the source wrote it. A non-string cell — a
    number, a boolean, a nested object — is written as ``json.dumps`` spells it, still
    what the source wrote.
    """
    if spec.form == SOURCE_CELL:
        raw = cell_as_written(row.get(spec.value))
        if raw is None:
            if spec.value not in nulls:
                nulls.add(spec.value)
                result.null_cells[spec.value] += 1
            return None, None
        return raw, spec.value
    if spec.form == SOURCE_COLUMN_NAME:
        return spec.value, link_column
    return spec.value, None


# --- reporting -----------------------------------------------------------------


def describe(imports: list[DatasetImport]) -> list[str]:
    """One block per dataset: the generation, then each table's counts."""
    lines = []
    for run in imports:
        lines.append(f"{run.dataset} -> {run.directory} ({run.files:,} files)")
        for table in run.tables:
            lines.append(f"  {table.table}: {table.rows:,} rows, {table.written:,} evidence rows")
            for column, n in sorted(table.no_link.items()):
                lines.append(f"    {column}: no link on {n:,} rows")
            for column, n in sorted(table.not_link.items()):
                lines.append(f"    {column}: not a DRS URI on {n:,} rows")
            for column, n in sorted(table.unresolved.items()):
                lines.append(f"    {column}: {n:,} links not among the dataset's files")
            for column, n in sorted(table.not_folder.items()):
                lines.append(f"    {column}: not a top folder's name on {n:,} rows")
            for column, n in sorted(table.empty_folder.items()):
                lines.append(f"    {column}: folder reaches no file on {n:,} rows")
            for column, n in sorted(table.null_cells.items()):
                lines.append(f"    {column}: null on {n:,} rows")
    return lines
