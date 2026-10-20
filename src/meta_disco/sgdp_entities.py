"""Read SGDP's metadata file into entity evidence for ANVIL_T2T_CHRY's SGDP genomes, where two sources agree on who each is (#559).

ANVIL_T2T_CHRY sequenced 279 genomes of the Simons Genome Diversity Project (SGDP) and names each
sample ``simons_data_sample_N``. Its ``SGDP_CHM13v2_sample`` and ``SGDP_GRCh38_sample`` tables pair
each sample with SGDP's own name for the genome (``sgdp_id``, ``S_Spanish-2``) and its karyotype.
SGDP's metadata file (:data:`URL`, Mallick et al. 2016) gives, per SGDP name, the person behind it
(``Sample_ID``: a Coriell or CEPH-HGDP cell line number, or the contributor's own name), their sex
(``Gender``) and population. No AnVIL table holds a donor for these genomes; this file is the source.

**The join is on SGDP's name** (contract 2.10): the target publishes it (``sgdp_id``), so the file's
``SGDP_ID`` is joined on it as written. **A line is written only where both sides agree on sex**:
SGDP's ``Gender`` (``M``, ``F``) and T2T_CHRY's ``karyotype`` (``XY``, ``XX``, :data:`KARYOTYPE`), in
every table naming the sample. The pairing of a sample with an SGDP name rests on T2T_CHRY's tables
alone (the files' headers name only ``simons_data_sample_N``), and sex is the one fact both sides
state about the genome. Measured on 2026-10-20 (#559): 275 of 279 samples agree. The others are each
counted by :data:`OUTCOMES` and written nothing; #718 holds them.

**Lines are observations** (contract 1.1), as SGDP wrote them, in one file per generation:

- about the sample (``simons_data_sample_64``, its identifier read from T2T_CHRY's table):
  ``collected_from``, SGDP's name for the genome;
- about the donor, by SGDP's name: ``phenotypic_sex`` (``Gender``), ``genetic_ancestry``
  (``Population_ID``), and ``same_donor_as`` (``Sample_ID``), the donor's main identifier where an
  identifier rule recognises it (#559), so the record is keyed by ``coriell:HG01504`` and keeps
  ``sgdp:S_Spanish-2`` as a synonym.

**The file is pinned and kept**: :func:`fetch` refuses a download whose sha256 is not
:data:`SHA256`, and each generation holds the file as read (:data:`KEPT_FILE`) beside its evidence,
so an import can be run again from it without the network. ``discover`` reads only ``*.ndjson``, so no
evidence reader takes it as evidence.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from .anvil_evidence import verbatim_manifest
from .azul_manifest import REPOSITORY, iter_verbatim_entities, sidecar_datasets
from .entity_evidence import write_entity_file
from .models import (
    COLLECTED_FROM,
    JOIN_KEY_ENTITY_IDENTIFIER,
    SAME_DONOR_AS,
    SOURCE_EXTERNAL_GROUND_TRUTH,
)
from .schema.classification_model import EntityEvidenceRow, ImporterSourceTypeEnum, JoinKeyEnum
from .source_evidence import (
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    evidence_file_path,
    generation_dir,
    new_generation,
    staged_generation,
)

# The source's name: the evidence directory, the envelope's repository, and the `source` a
# translation row's scope names.
SOURCE = "sgdp"
DATASET = "ANVIL_T2T_CHRY"
# SGDP's metadata file, from the Reich lab's SGDP page (https://reichdata.hms.harvard.edu/pub/datasets/sgdp/),
# as downloaded on 2026-10-20: 345 rows, Latin-1, tab-separated.
URL = (
    "https://sharehost.hms.harvard.edu/genetics/reich_lab/sgdp/SGDP_metadata.279public.21signedLetter.44Fan.samples.txt"
)
SHA256 = "1e4f0076ddadc57ce9feb252c1f9a782ea9d5ba4e6606627fcd60e9c5bf2ef33"
ENCODING = "latin-1"
# The evidence file's table, and the name the file is kept under beside it.
TABLE = "SGDP_metadata"
KEPT_FILE = f"{TABLE}.txt"
# SGDP's columns read: its key, and the three a donor line is written from.
SGDP_ID = "SGDP_ID"
SAMPLE_ID = "Sample_ID"
GENDER = "Gender"
POPULATION = "Population_ID"
DONOR_COLUMNS = {"phenotypic_sex": GENDER, "genetic_ancestry": POPULATION, SAME_DONOR_AS: SAMPLE_ID}
# T2T_CHRY's tables naming each SGDP genome, and in each the column naming the sample.
SAMPLE_TABLES = {"SGDP_CHM13v2_sample": "sgdp_chm13v2_sample_id", "SGDP_GRCh38_sample": "sgdp_grch38_sample_id"}
T2T_SGDP_ID = "sgdp_id"
KARYOTYPE_COLUMN = "karyotype"
# The karyotype each of SGDP's sexes is: the check both sides must pass.
KARYOTYPE = {"M": "XY", "F": "XX"}

CONFIRMED = "confirmed"
NOT_IN_SGDP_FILE = "not_in_sgdp_file"
SEX_NOT_STATED = "sex_not_stated"
SEX_CONTRADICTS = "sex_contradicts"
TABLES_DISAGREE = "tables_disagree"
# Every outcome a sample can have, the order :func:`describe` lists them in.
OUTCOMES = (CONFIRMED, NOT_IN_SGDP_FILE, SEX_NOT_STATED, SEX_CONTRADICTS, TABLES_DISAGREE)


@dataclass(frozen=True)
class SgdpFile:
    """SGDP's metadata file as read: its bytes, and when they were read."""

    content: bytes
    read_at: datetime


@dataclass
class Import:
    """One import: where it went, each sample's outcome, and the lines written."""

    directory: Path
    outcomes: dict[str, list[str]] = field(default_factory=dict)
    written: int = 0


Fetch = Callable[[], SgdpFile]


def check_sha256(content: bytes, where: str) -> None:
    """Refuse ``content`` whose sha256 is not :data:`SHA256`: a changed file is another source, to be measured first."""
    got = hashlib.sha256(content).hexdigest()
    if got != SHA256:
        raise ValueError(f"{where}: sha256 {got}, not the {SHA256} this importer was measured against")


def fetch() -> SgdpFile:
    """Download SGDP's metadata file from :data:`URL`, refused unless its sha256 is :data:`SHA256`."""
    read_at = datetime.now(timezone.utc)
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    check_sha256(response.content, URL)
    return SgdpFile(response.content, read_at)


def load_kept(path: Path) -> SgdpFile:
    """A kept copy of the file (:data:`KEPT_FILE`), refused unless its sha256 is :data:`SHA256`; read now."""
    content = path.read_bytes()
    check_sha256(content, str(path))
    return SgdpFile(content, datetime.now(timezone.utc))


def sgdp_rows(content: bytes) -> dict[str, dict[str, str]]:
    """The file's rows by ``SGDP_ID``; ``ValueError`` where a column read is missing or an ``SGDP_ID`` repeats."""
    reader = csv.DictReader(io.StringIO(content.decode(ENCODING)), delimiter="\t")
    missing = {SGDP_ID, *DONOR_COLUMNS.values()} - set(reader.fieldnames or ())
    if missing:
        raise ValueError(f"SGDP's metadata file has no column {sorted(missing)}")
    rows: dict[str, dict[str, str]] = {}
    for row in reader:
        key = row[SGDP_ID]
        if key in rows:
            raise ValueError(f"SGDP's metadata file names {key!r} twice")
        rows[key] = row
    return rows


@dataclass(frozen=True)
class T2tRow:
    """One T2T_CHRY row naming an SGDP genome: the table, its sample identifier, SGDP's name and the karyotype."""

    table: str
    sample: str
    sgdp_id: str | None
    karyotype: str | None


def t2t_rows(manifest: Path) -> dict[str, list[T2tRow]]:
    """Every row of T2T_CHRY's SGDP tables (:data:`SAMPLE_TABLES`), by its sample identifier; a row naming no
    sample is passed over."""
    rows: dict[str, list[T2tRow]] = {}
    for table, row in iter_verbatim_entities(manifest, set(SAMPLE_TABLES)):
        sample = row.get(SAMPLE_TABLES[table])
        if not isinstance(sample, str) or not sample:
            continue
        rows.setdefault(sample, []).append(T2tRow(table, sample, row.get(T2T_SGDP_ID), row.get(KARYOTYPE_COLUMN)))
    return rows


def outcome(rows: list[T2tRow], sgdp: dict[str, dict[str, str]]) -> str:
    """One sample's outcome (:data:`OUTCOMES`): ``confirmed`` where every T2T_CHRY row naming it names one SGDP
    genome and one karyotype, SGDP's file has the genome, and its sex is that karyotype's."""
    if len({(r.sgdp_id, r.karyotype) for r in rows}) != 1:
        return TABLES_DISAGREE
    first = rows[0]
    found = sgdp.get(first.sgdp_id) if first.sgdp_id else None
    if found is None:
        return NOT_IN_SGDP_FILE
    karyotype = KARYOTYPE.get(found[GENDER])
    if karyotype is None:
        return SEX_NOT_STATED
    return CONFIRMED if karyotype == first.karyotype else SEX_CONTRADICTS


def lines(confirmed: list[tuple[T2tRow, str]], sgdp: dict[str, dict[str, str]]) -> Iterator[EntityEvidenceRow]:
    """Each confirmed sample's ``collected_from`` line, then its donor's lines, a cell each, an empty cell writing nothing.

    ``confirmed`` pairs each sample's first T2T_CHRY row, which :func:`outcome` has shown every other agrees
    with, with the SGDP name it gives.
    """
    for row, sgdp_id in confirmed:
        yield EntityEvidenceRow(
            field=COLLECTED_FROM,
            target_key_value=row.sample,
            raw_value=sgdp_id,
            column=SGDP_ID,
            identifier_column=SAMPLE_TABLES[row.table],
            identifier_table=row.table,
        )
        found = sgdp[sgdp_id]
        for slot, column in DONOR_COLUMNS.items():
            if found[column].strip():
                yield EntityEvidenceRow(
                    field=slot,
                    target_key_value=sgdp_id,
                    raw_value=found[column],
                    column=column,
                    identifier_column=SGDP_ID,
                )


def envelope(catalog: str, read_at: datetime) -> EvidenceFileEnvelope:
    """The envelope of SGDP's lines about ANVIL_T2T_CHRY's SGDP genomes, keyed by an identifier.

    Its ``source_version`` is the file's sha256, since SGDP publishes no version of it, and ``fetched_at`` when
    it was read.
    """
    return EvidenceFileEnvelope(
        source=EvidenceFileSource(repository=SOURCE, table=TABLE, url=URL),
        source_type=ImporterSourceTypeEnum(SOURCE_EXTERNAL_GROUND_TRUTH),
        source_version=SHA256,
        source_key=SGDP_ID,
        target=EvidenceTarget(system=REPOSITORY, dataset=DATASET, version=catalog),
        target_key=JoinKeyEnum(JOIN_KEY_ENTITY_IDENTIFIER),
        fetched_at=read_at.isoformat(),
    )


def import_sgdp(
    manifest_root: Path,
    catalog: str,
    entity_root: Path,
    read: Fetch = fetch,
    generation: str | None = None,
) -> Import:
    """Write one generation of SGDP's lines for the samples both sides agree on, and the file as read beside them.

    Raises, writing nothing, where T2T_CHRY's verbatim manifest cannot be read or no sample is confirmed: an
    evidence file with no lines is refused by reconcile (contract 5.3), and no generation would leave an older
    one current.
    """
    manifest = verbatim_manifest(manifest_root, catalog, DATASET, sidecar_datasets(manifest_root, catalog))
    if isinstance(manifest, str):
        raise ValueError(manifest)
    t2t = t2t_rows(manifest)
    got = read()
    sgdp = sgdp_rows(got.content)
    result = Import(generation_dir(entity_root, SOURCE, catalog, DATASET, generation or new_generation()))
    confirmed: list[tuple[T2tRow, str]] = []
    for sample in sorted(t2t):
        verdict = outcome(t2t[sample], sgdp)
        result.outcomes.setdefault(verdict, []).append(sample)
        first = t2t[sample][0]
        if verdict == CONFIRMED and first.sgdp_id is not None:
            confirmed.append((first, first.sgdp_id))
    if not confirmed:
        counts = ", ".join(f"{verdict} {len(s):,}" for verdict, s in sorted(result.outcomes.items()))
        raise ValueError(f"{DATASET}: no SGDP sample confirmed ({counts or 'no SGDP rows'}); nothing written")
    with staged_generation(result.directory) as staging:
        result.written = write_entity_file(
            evidence_file_path(staging, TABLE), envelope(catalog, got.read_at), lines(confirmed, sgdp)
        )
        (staging / KEPT_FILE).write_bytes(got.content)
    return result


def describe(result: Import) -> list[str]:
    """Where the import went, each outcome's count, and the samples of every outcome but ``confirmed``."""
    total = sum(len(s) for s in result.outcomes.values())
    out = [f"{DATASET} -> {result.directory} ({total:,} SGDP samples, {result.written:,} lines)"]
    for verdict in OUTCOMES:
        samples = result.outcomes.get(verdict, [])
        if not samples:
            continue
        named = "" if verdict == CONFIRMED else f": {', '.join(samples)}"
        out.append(f"  {verdict}: {len(samples):,}{named}")
    return out
