"""Which declared sample map each GenomicsDB workspace tar was imported from, as lineage (#710).

**A workaround** for maps AnVIL does not hold (#624; ``external_files`` says what it is and how
it ends). A workspace tar's ``vcfheader.vcf`` names, in its one ``GenomicsDBImport`` line, the
sample-name map it imported (``cohort_steps.sample_name_map``). Where a dataset's catalog holds
no file of that name, the map may still be a declared external file: one whose ``named_as``
lists the path the header names.

**The gate is the tar's own samples** (contract 2.11). The declared map is a published copy,
not the file the import read, so a tar is linked to it only where the tar's own
``callset.json``, the list of samples GenomicsDB imported, read from AnVIL's S3 mirror, names
exactly the samples the map's rows name, each once. That confirms the cohort; which map is the
one its header's path names (``named_as``), since maps of one cohort share their samples. The tar is then written one lineage line:
made from the map (``parent`` its address, ``parent_key_type: external_file``), the path its
header named kept as ``parent_source_identifier``, and ``raw_activity`` the header's tool,
``GenomicsDBImport``, whose meaning is the activity translation table's (#584). Every other tar
of the dataset is counted by why (:data:`OUTCOMES`), never written: a tar naming a map no
declared file stands for (``map_not_declared``, ANVIL_T2T_CHRY's SGDP tars) is not read.

**What was read is kept** beside each generation (``sample_maps.inputs.json``): per tar read,
its name, md5, the path its header named and its sample set's id, and each distinct sample
set once, and each outcome's count. A re-import from it (:func:`load_inputs`) reads no network,
and refuses kept inputs of another catalog, dataset or commit, a reading whose tar the manifest
or header names otherwise, and a reading whose tar it no longer checks. The tars' headers are read from the tar producer's
cache (``TarEvidence``), never fetched here: ``make classify-tar`` reads them.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from .anvil_evidence import verbatim_manifest
from .azul_manifest import REPOSITORY, sidecar_datasets
from .cohort_steps import (
    CALLSET_UNREADABLE,
    NO_CALLSET,
    NO_VCF_HEADER,
    VCF_HEADER_UNREADABLE,
    callset_samples,
    parse_tar_head,
    sample_name_map,
    set_id,
)
from .deployments import Deployment
from .ena_lineage import CatalogFile, Progress, catalog_files, in_parallel
from .evidence import TarEvidence, TarHead
from .external_files import Entry, ExternalFile, ExternalFiles, read_sample_map
from .fetchers import FetchError, fetch_tar_member
from .header_classifier import CALLSET_MEMBER
from .lineage_evidence import write_lineage_file
from .models import JOIN_KEY_FILE_ID, SOURCE_EXTERNAL_GROUND_TRUTH
from .schema.classification_model import (
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    ImporterSourceTypeEnum,
    JoinKeyEnum,
    LineageParentKeyEnum,
    LineageRow,
)
from .source_evidence import evidence_file_path, generation_dir, new_generation, staged_generation

# The lineage root's directory for these files, and the one table each generation writes.
SOURCE = "external"
TABLE = "sample_maps"
# What the source keys its files by: their path in the repository.
SOURCE_KEY = "path"
# What a line names as its columns: the child by AnVIL's file id, the parent by the header's
# argument, the step by the member it was read from.
CHILD_COLUMN = JOIN_KEY_FILE_ID
PARENT_COLUMN = "--sample-name-map"
STEP_COLUMN = "vcfheader.vcf"
RAW_ACTIVITY = "GenomicsDBImport"
TAR_SUFFIX = ".tar"
# Tars read at once, tries per tar when a read fails, and how often progress is reported.
WORKERS = 32
ATTEMPTS = 3
PROGRESS_EVERY = 1000

# Each tar's outcome, one per tar of the dataset, in the order they are tested. ``no_header``:
# the tar cache holds no entry for it, or no vcfheader.vcf; ``no_import``: its header names no
# one sample map (a cohort_steps outcome); ``not_a_workspace``: its members are no GenomicsDB
# store; ``map_not_declared``: no declared file is named as the map it names.
LINKED = "linked"
NOT_A_WORKSPACE = "not_a_workspace"
NO_HEADER = "no_header"
NO_IMPORT = "no_import"
MAP_NOT_DECLARED = "map_not_declared"
SAMPLES_DIFFER = "samples_differ"
OUTCOMES = (
    LINKED,
    NOT_A_WORKSPACE,
    NO_HEADER,
    NO_IMPORT,
    MAP_NOT_DECLARED,
    CALLSET_UNREADABLE,
    NO_CALLSET,
    SAMPLES_DIFFER,
)


def _silent(_message: str) -> None:
    pass


# --- checking the declaration against a deployment, its manifests and the cache ----------


def check(declared: ExternalFiles, deployment: Deployment, manifest_root: Path, external_root: Path) -> list[str]:
    """How the declaration disagrees with the deployment, the manifests and the cache, one line per problem; empty when none.

    It is authored against the deployment's catalog; each dataset is one the deployment
    declares, with its verbatim manifest on disk; and each declared file is in the cache
    under ``external_root`` with its declared sha256, and is a sample map whose every row is
    a sample and a path, each sample once.
    """
    problems = []
    if declared.catalog != deployment.catalog:
        problems.append(f"external files: authored against {declared.catalog}, not {deployment.catalog}")
    _, problems_with_manifests = manifests(declared, manifest_root)
    problems += problems_with_manifests
    for entry in declared.entries:
        if entry.dataset not in deployment.snapshots:
            problems.append(f"{entry.dataset}: not a dataset the {deployment.name} deployment declares")
        for file in entry.sample_maps:
            try:
                map_samples(file, external_root)
            except ValueError as exc:
                problems.append(str(exc))
    return problems


def manifests(declared: ExternalFiles, manifest_root: Path) -> tuple[dict[str, Path], list[str]]:
    """Each declared dataset's verbatim manifest, and why any cannot be read (``anvil_evidence.verbatim_manifest``)."""
    named = sidecar_datasets(manifest_root, declared.catalog)
    paths: dict[str, Path] = {}
    problems: list[str] = []
    for entry in declared.entries:
        path = verbatim_manifest(manifest_root, declared.catalog, entry.dataset, named)
        if isinstance(path, str):
            problems.append(path)
        else:
            paths[entry.dataset] = path
    return paths, problems


def map_samples(file: ExternalFile, external_root: Path) -> list[str]:
    """The sample of each row of a declared sample map, in row order, from the cache.

    ``ExternalFileError`` where ``external_files.read_sample_map`` refuses it; ``ValueError``
    where it names a sample twice.
    """
    rows = read_sample_map(file, external_root)
    samples = [sample for sample, _ in rows]
    if len(set(samples)) != len(samples):
        raise ValueError(f"{file.ref}: names a sample in two rows")
    return samples


def sample_set_id(samples: Iterable[str]) -> str:
    """The id of a set of sample names: the first 16 hex of the sha256 of the distinct names, sorted, one per line.

    Not a ``sample_identity.list_id``, which digests recognised identifiers: these are the names as written.
    """
    return set_id(samples)


# --- reading what the importer reads ---------------------------------------------------


@dataclass
class TarReading:
    """What was read for one tar: the map path its header named and its callset's sample set, or why not.

    Kept in the inputs file, so a re-import reads none of it again. ``file_name`` and ``md5``
    are the tar's as the manifest gave them when it was read, so a re-import can tell the
    manifest still names the same file.
    """

    file_id: str
    file_name: str
    md5: str | None
    named: str
    callset: str | None = None
    duplicated: bool = False
    error: str | None = None


@dataclass
class Inputs:
    """Everything an import of one dataset read: each tar's reading and each distinct sample set."""

    catalog: str
    dataset: str
    commit: str
    read_at: datetime
    tars: dict[str, TarReading] = field(default_factory=dict)
    sample_sets: dict[str, list[str]] = field(default_factory=dict)


def catalog_tars(path: Path) -> list[CatalogFile]:
    """A dataset's tars, from its verbatim manifest (``ena_lineage.catalog_files``), once each by ``file_id``."""
    found: dict[str, CatalogFile] = {}
    for _value, file in catalog_files(path):
        if file.file_name.lower().endswith(TAR_SUFFIX):
            found.setdefault(file.file_id, file)
    return list(found.values())


def named_map(tar: CatalogFile, evidence_dir: Path) -> tuple[str | None, str | None]:
    """The map path a tar's cached ``vcfheader.vcf`` names, or None and the tar's outcome.

    The header comes from the tar producer's cache: :data:`NO_HEADER` where it holds none,
    :data:`NOT_A_WORKSPACE` where the members are no GenomicsDB store, :data:`NO_IMPORT`
    where the header names no one map (``cohort_steps.sample_name_map``).
    """
    cached = TarEvidence.load(evidence_dir, tar.md5) if tar.md5 is not None else None
    if cached is None:
        return None, NO_HEADER
    named, why = sample_name_map(parse_tar_head(TarHead(cached.member_names, cached.vcf_header)), tar.file_name)
    if named is not None:
        return named, None
    if why is None:
        return None, NOT_A_WORKSPACE
    return None, NO_HEADER if why in (NO_VCF_HEADER, VCF_HEADER_UNREADABLE) else NO_IMPORT


def read_callset(md5: str) -> str | None:
    """A tar's ``callset.json`` text (``fetchers.fetch_tar_member``), tried :data:`ATTEMPTS` times in all where the connection fails.

    A failed read whose cause is a ``requests`` exception (a dropped connection, a stream cut off
    mid-read) is tried again; any other ``FetchError`` (an HTTP status, a member body shorter than
    its header says) raises at once, as ``ena_lineage.read_stats`` does.
    """
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return fetch_tar_member(md5, CALLSET_MEMBER)
        except FetchError as exc:
            if attempt == ATTEMPTS or not isinstance(exc.__cause__, requests.RequestException):
                raise
            time.sleep(attempt)
    raise AssertionError("ATTEMPTS is at least 1")


# --- importing -------------------------------------------------------------------------


@dataclass
class DatasetImport:
    """One dataset's import: each tar's outcome (:data:`OUTCOMES`), lines written, and where."""

    dataset: str
    directory: Path
    outcomes: Counter = field(default_factory=Counter)
    written: int = 0


def import_all(
    declared: ExternalFiles,
    manifest_root: Path,
    lineage_root: Path,
    evidence_dir: Path,
    external_root: Path,
    read_member: Callable[[str], str | None] = read_callset,
    stored: dict[str, Inputs] | None = None,
    generation: str | None = None,
    progress: Progress = _silent,
) -> list[DatasetImport]:
    """Import every dataset of the declaration, each as one new generation under one shared stamp.

    ``stored`` (by dataset) re-imports from kept inputs instead of the network, and must hold
    every dataset. Raises before writing anything if a dataset's verbatim manifest cannot be
    read, a declared map is not cached or has changed, or a dataset has no kept inputs. Each
    dataset's generation is written as it is imported, so one :func:`import_dataset` refuses
    leaves the datasets before it written.
    """
    paths, problems = manifests(declared, manifest_root)
    if problems:
        raise ValueError("; ".join(problems))
    if stored is not None:
        unstored = [e.dataset for e in declared.entries if e.dataset not in stored]
        if unstored:
            raise ValueError(f"no kept inputs for {unstored}; a re-import from kept inputs reads no network")
    sets = {f.ref: sample_set_id(map_samples(f, external_root)) for e in declared.entries for f in e.sample_maps}
    stamp = generation or new_generation()
    return [
        import_dataset(
            declared.catalog,
            entry,
            paths[entry.dataset],
            lineage_root,
            evidence_dir,
            sets,
            read_member=read_member,
            stored=(stored or {}).get(entry.dataset),
            generation=stamp,
            progress=progress,
        )
        for entry in declared.entries
    ]


def import_dataset(
    catalog: str,
    entry: Entry,
    manifest: Path,
    lineage_root: Path,
    evidence_dir: Path,
    map_sets: dict[str, str],
    *,
    read_member: Callable[[str], str | None],
    stored: Inputs | None,
    generation: str,
    progress: Progress = _silent,
) -> DatasetImport:
    """Write one generation for one dataset: its lineage file and its inputs file.

    ``map_sets`` is each declared map's sample set id, by address. Raises, writing nothing,
    when no tar is linked: the declaration disagrees with the catalog there, and writing
    nothing quietly would leave an older generation current. With ``stored``, also when a
    tar to be checked has no kept reading, or one read for another file
    (:func:`require_inputs_agree`).
    """
    result = DatasetImport(entry.dataset, generation_dir(lineage_root, SOURCE, catalog, entry.dataset, generation))
    if stored is not None and (stored.catalog, stored.dataset, stored.commit) != (catalog, entry.dataset, entry.commit):
        raise ValueError(
            f"inputs for {stored.catalog}/{stored.dataset} at {stored.commit} cannot be imported as "
            f"{catalog}/{entry.dataset} at {entry.commit}"
        )
    inputs = stored or Inputs(catalog, entry.dataset, entry.commit, datetime.now(timezone.utc))
    to_check: list[tuple[CatalogFile, ExternalFile, str]] = []
    for tar in catalog_tars(manifest):
        path, outcome = named_map(tar, evidence_dir)
        if path is None:
            result.outcomes[outcome] += 1
            continue
        file = entry.named(path)
        if file is None:
            result.outcomes[MAP_NOT_DECLARED] += 1
            continue
        to_check.append((tar, file, path))
    if stored is not None:
        require_inputs_agree(to_check, stored, entry.dataset)
    else:
        _read_callsets(to_check, inputs, read_member, lambda message: progress(f"{entry.dataset}: {message}"))
    rows: list[LineageRow] = []
    for tar, file, path in to_check:
        reading = inputs.tars[tar.file_id]
        verdict = _outcome(reading, map_sets[file.ref])
        result.outcomes[verdict] += 1
        if verdict == LINKED:
            rows.append(
                LineageRow(
                    target_key_value=tar.file_id,
                    parent=file.ref,
                    parent_key_type=LineageParentKeyEnum.external_file,
                    parent_source_identifier=path,
                    raw_activity=RAW_ACTIVITY,
                    raw_activity_column=STEP_COLUMN,
                    child_column=CHILD_COLUMN,
                    parent_column=PARENT_COLUMN,
                )
            )
    if not rows:
        counts = ", ".join(f"{k} {n:,}" for k, n in sorted(result.outcomes.items()))
        raise ValueError(f"{entry.dataset}: no tar linked to a declared sample map ({counts}); nothing written")
    with staged_generation(result.directory) as staging:
        result.written = write_lineage_file(
            evidence_file_path(staging, TABLE), envelope(catalog, entry, inputs.read_at), rows
        )
        write_inputs(staging / f"{TABLE}.inputs.json", inputs, [t.file_id for t, _, _ in to_check], result.outcomes)
    return result


def envelope(catalog: str, entry: Entry, read_at: datetime) -> EvidenceFileEnvelope:
    """The envelope of a dataset's lines: the declared repository and directory at its commit, about its files by ``file_id``."""
    return EvidenceFileEnvelope(
        source=EvidenceFileSource(repository=f"{entry.host}:{entry.repository}", table=TABLE, url=entry.url),
        source_type=ImporterSourceTypeEnum(SOURCE_EXTERNAL_GROUND_TRUTH),
        source_version=entry.commit,
        source_key=SOURCE_KEY,
        target=EvidenceTarget(system=REPOSITORY, dataset=entry.dataset, version=catalog),
        target_key=JoinKeyEnum(JOIN_KEY_FILE_ID),
        fetched_at=read_at.isoformat(),
    )


def _outcome(reading: TarReading, map_set: str) -> str:
    if reading.error is not None:
        return CALLSET_UNREADABLE
    if reading.callset is None:
        return NO_CALLSET
    if reading.duplicated or reading.callset != map_set:
        return SAMPLES_DIFFER
    return LINKED


def require_inputs_agree(to_check: list[tuple[CatalogFile, ExternalFile, str]], inputs: Inputs, at: str) -> None:
    """``ValueError`` when a tar to be checked has no kept reading, or one read for another file or map path;
    or when a kept reading's tar is not among those to be checked (its cache entry gone, say), whose
    link a re-import would otherwise drop without a word."""
    unreached = sorted(set(inputs.tars) - {tar.file_id for tar, _, _ in to_check})
    if unreached:
        names = ", ".join(f"{inputs.tars[f].file_name} ({f})" for f in unreached[:5])
        raise ValueError(f"{at}: {len(unreached)} kept readings name tars this re-import does not check: {names}")
    for tar, _file, path in to_check:
        reading = inputs.tars.get(tar.file_id)
        if reading is None:
            raise ValueError(f"{at}: {tar.file_name} ({tar.file_id}) has no kept reading")
        if (reading.file_name, reading.md5, reading.named) != (tar.file_name, tar.md5, path):
            raise ValueError(f"{at}: {tar.file_name} ({tar.file_id}) is not the tar its kept reading read")


def _read_callsets(
    to_check: list[tuple[CatalogFile, ExternalFile, str]],
    inputs: Inputs,
    read_member: Callable[[str], str | None],
    progress: Progress,
) -> None:
    """Read each tar's ``callset.json`` into its reading, :data:`WORKERS` at a time."""

    def task(tar: CatalogFile, path: str) -> Callable[[], None]:
        def read() -> None:
            reading = inputs.tars[tar.file_id] = TarReading(tar.file_id, tar.file_name, tar.md5, path)
            if tar.md5 is None:
                reading.error = "no md5 to read the tar by"
                return
            try:
                text = read_member(tar.md5)
                if text is not None:
                    names = callset_samples(text)
                    distinct = sorted(set(names))
                    reading.callset, reading.duplicated = set_id(names), len(distinct) != len(names)
                    if reading.callset not in inputs.sample_sets:
                        inputs.sample_sets[reading.callset] = distinct
            except (FetchError, ValueError) as exc:
                reading.error = str(exc)

        return read

    in_parallel([task(tar, path) for tar, _file, path in to_check], progress, "callsets", WORKERS, PROGRESS_EVERY)


# --- the kept inputs --------------------------------------------------------------------


def write_inputs(path: Path, inputs: Inputs, file_ids: list[str], outcomes: Counter) -> None:
    """Write what was read for the tars ``file_ids``, the sample sets their readings name, and each tar outcome's count."""
    tars = [inputs.tars[f] for f in sorted(file_ids)]
    named_sets = {t.callset for t in tars if t.callset is not None}
    document = {
        "catalog": inputs.catalog,
        "dataset": inputs.dataset,
        "commit": inputs.commit,
        "read_at": inputs.read_at.isoformat(),
        "member": CALLSET_MEMBER,
        "outcomes": {o: outcomes[o] for o in OUTCOMES},
        "tars": [asdict(t) for t in tars],
        "sample_sets": {k: inputs.sample_sets[k] for k in sorted(named_sets)},
    }
    path.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def load_inputs(paths: Iterable[Path]) -> dict[str, Inputs]:
    """The inputs :func:`write_inputs` kept, by dataset; ``ValueError`` on two files for one dataset, or a set no reading's id fits."""
    found: dict[str, Inputs] = {}
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        sets = document["sample_sets"]
        for key, names in sets.items():
            if sample_set_id(names) != key:
                raise ValueError(f"{path}: sample set {key} holds names whose id is {sample_set_id(names)}")
        missing = sorted({t["callset"] for t in document["tars"] if t.get("callset") is not None} - set(sets))
        if missing:
            raise ValueError(f"{path}: readings name sample sets the file does not hold: {missing}")
        inputs = Inputs(
            catalog=document["catalog"],
            dataset=document["dataset"],
            commit=document["commit"],
            read_at=datetime.fromisoformat(document["read_at"]),
            tars={t["file_id"]: TarReading(**t) for t in document["tars"]},
            sample_sets=sets,
        )
        if inputs.dataset in found:
            raise ValueError(f"{path}: a second inputs file for {inputs.dataset}")
        found[inputs.dataset] = inputs
    return found


def describe(imports: list[DatasetImport]) -> list[str]:
    """One block per dataset: where it went and the lines written, then each outcome's count."""
    lines = []
    for run in imports:
        lines.append(f"{run.dataset} -> {run.directory} ({run.outcomes.total():,} tars, {run.written:,} lines)")
        for outcome in OUTCOMES:
            lines.append(f"  {outcome}: {run.outcomes[outcome]:,}")
    return lines
