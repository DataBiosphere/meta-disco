"""Read SGDP's metadata file into entity evidence for ANVIL_T2T_CHRY's SGDP genomes, where two sources agree on who each is (#559).

ANVIL_T2T_CHRY sequenced 279 genomes of the Simons Genome Diversity Project (SGDP) and names each
sample ``simons_data_sample_N``. Its ``SGDP_CHM13v2_sample`` and ``SGDP_GRCh38_sample`` tables pair
each sample with SGDP's own name for the genome (``sgdp_id``, ``S_Spanish-2``) and its karyotype.
SGDP's metadata file (:data:`URL`, Mallick et al. 2016) gives, per SGDP name, the person behind it
(``Sample_ID``: a Coriell or CEPH-HGDP cell line number, or the contributor's own name), their sex
(``Gender``) and population. No AnVIL table holds a donor for these genomes; this file is the source.

**The join is on SGDP's name** (contract 2.10): the target publishes it (``sgdp_id``), so the file's
``SGDP_ID`` is joined on it as written. The pairing of a sample with an SGDP name rests on T2T_CHRY's
tables alone (the files' headers name only ``simons_data_sample_N``), so **a sample is written only where
a check confirms the pairing** (``code_rules.IDENTITY_CHECKS``), in every table naming the sample:

- ``code_rules.SGDP_SEX_AGREES``: SGDP's ``Gender`` (``M``, ``F``) is T2T_CHRY's ``karyotype`` (``XY``,
  ``XX``, :data:`KARYOTYPE`), the one fact both sides state about the genome. 275 of 279 samples agree
  (#559).
- ``code_rules.SGDP_GENOTYPE_MATCHES``: the sample's genotypes match the paired genome's in SGDP's or
  HGDP's public release, as recorded in ``sources/sgdp_genotype_checks.yaml`` (:func:`load_genotype_checks`,
  #718). It confirms three samples the sex check cannot: one whose karyotype contradicts SGDP's sex, and
  two SGDP gives no sex for. A recorded non-match leaves a sample out whatever its sex check says.

A sample SGDP's file does not hold, or whose tables disagree, is written nothing. Every sample's
:class:`Outcome` (both checks, and which confirmed it) is written beside the evidence
(``entity_evidence.OUTCOMES_FILE``), where reconcile reads why a sample has no donor.

**Each line is cited to the source that wrote it** (contract 1.1), one file per source in a generation:

- T2T_CHRY's tables (one file each, ``repository_metadata``): about each confirmed sample, ``collected_from``,
  the ``sgdp_id`` the table pairs it with;
- SGDP's file (``external_ground_truth``): about each confirmed genome, by SGDP's name, ``phenotypic_sex``
  (``Gender``), ``genetic_ancestry`` (``Population_ID``), and ``same_donor_as`` (``Sample_ID``), the donor's
  main identifier where an identifier rule recognises it, so the record is keyed by ``coriell:HG01504`` and
  keeps ``sgdp:S_Spanish-2`` as a synonym.

The file is pinned (:data:`SHA256`) and kept in each generation, beside its evidence files (:data:`KEPT_FILE`); ``discover``
reads only ``*.ndjson``, so no evidence reader takes the copy as evidence.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

import requests
import yaml

from . import code_rules
from .anvil_evidence import verbatim_manifest
from .azul_manifest import FORMAT_VERBATIM, REPOSITORY, iter_verbatim_entities, sidecar_datasets, sidecar_requested_at
from .entity_evidence import read_entity_envelope, write_entity_file, write_outcomes
from .lineage_map import expect_keys, expect_mapping, expect_name
from .models import (
    COLLECTED_FROM,
    JOIN_KEY_ENTITY_IDENTIFIER,
    SAME_DONOR_AS,
    SOURCE_EXTERNAL_GROUND_TRUTH,
    SOURCE_REPOSITORY_METADATA,
)
from .schema.classification_model import EntityEvidenceRow, ImporterSourceTypeEnum, JoinKeyEnum
from .slot_map import Readable, unique_key_loader
from .source_evidence import (
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    evidence_file_path,
    generation_dir,
    new_generation,
    parse_iso_datetime,
    staged_generation,
)

# The source's name: the evidence directory, the envelope's repository, and the `source` a
# translation row's scope names.
SOURCE = "sgdp"
DATASET = "ANVIL_T2T_CHRY"
# SGDP's metadata file, from the Reich lab's SGDP page (https://reichdata.hms.harvard.edu/pub/datasets/sgdp/),
# as downloaded on 2026-10-20: a header and 344 rows, Latin-1, tab-separated.
URL = (
    "https://sharehost.hms.harvard.edu/genetics/reich_lab/sgdp/SGDP_metadata.279public.21signedLetter.44Fan.samples.txt"
)
SHA256 = "1e4f0076ddadc57ce9feb252c1f9a782ea9d5ba4e6606627fcd60e9c5bf2ef33"
ENCODING = "latin-1"
# SGDP's evidence file's table, and the name the file is kept under beside it.
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

# What the sex check found for a sample; the first three mean the tables name one genome, which SGDP's file holds.
SEX_AGREES = "agrees"
SEX_CONTRADICTS = "contradicts"
SEX_NOT_STATED = "not_stated"
NOT_IN_SGDP_FILE = "not_in_sgdp_file"
TABLES_DISAGREE = "tables_disagree"
SEX_CHECKS = (SEX_AGREES, SEX_CONTRADICTS, SEX_NOT_STATED, NOT_IN_SGDP_FILE, TABLES_DISAGREE)
# What the genotype record says of the sample's pairing.
GENOTYPE_MATCHES = "matches"
GENOTYPE_NO_MATCH = "no_match"
GENOTYPE_NOT_CHECKED = "not_checked"
GENOTYPE_CHECKS = (GENOTYPE_MATCHES, GENOTYPE_NO_MATCH, GENOTYPE_NOT_CHECKED)


@dataclass(frozen=True)
class SgdpFile:
    """SGDP's metadata file as read: its bytes, and when they were downloaded."""

    content: bytes
    fetched_at: datetime


@dataclass(frozen=True)
class Outcome:
    """One sample's checks: the SGDP genome its tables pair it with (None where they disagree), what the sex check
    found (:data:`SEX_CHECKS`) and what the genotype record says (:data:`GENOTYPE_CHECKS`)."""

    sample: str
    sgdp_id: str | None
    sex_check: str
    genotype_check: str

    @property
    def confirmed_by(self) -> tuple[str, ...]:
        """The ids of the checks that confirm the pairing, where it can be written: the tables name one genome SGDP's
        file holds, and no genotype record says the sample is someone else."""
        if self.sex_check in (NOT_IN_SGDP_FILE, TABLES_DISAGREE) or self.genotype_check == GENOTYPE_NO_MATCH:
            return ()
        checks = []
        if self.sex_check == SEX_AGREES:
            checks.append(code_rules.SGDP_SEX_AGREES.id)
        if self.genotype_check == GENOTYPE_MATCHES:
            checks.append(code_rules.SGDP_GENOTYPE_MATCHES.id)
        return tuple(checks)

    def to_dict(self) -> dict:
        """The outcome as the generation's outcomes file holds it."""
        return {
            "sample": self.sample,
            "sgdp_id": self.sgdp_id,
            "sex_check": self.sex_check,
            "genotype_check": self.genotype_check,
            "confirmed_by": list(self.confirmed_by),
        }


@dataclass
class Import:
    """One import: where it went, each sample's outcome, and the lines written to each file."""

    directory: Path
    outcomes: dict[str, Outcome] = field(default_factory=dict)
    written: dict[str, int] = field(default_factory=dict)

    @property
    def linked(self) -> list[str]:
        """The samples written, in order."""
        return [sample for sample, o in self.outcomes.items() if o.confirmed_by]


@dataclass(frozen=True)
class GenotypeCheck:
    """One sample's genotype record: the SGDP genome its tables paired it with when measured, and the genome its
    genotypes match, None where none does."""

    sample: str
    sgdp_id: str
    matched: str | None


@dataclass(frozen=True)
class GenotypeChecks:
    """The genotype record (``sources/sgdp_genotype_checks.yaml``): the catalog whose files were measured, and each
    sample's check."""

    catalog: str
    by_sample: dict[str, GenotypeCheck]


Fetch = Callable[[], SgdpFile]


def check_sha256(content: bytes, where: str) -> None:
    """Refuse ``content`` whose sha256 is not :data:`SHA256`: a changed file is another source, to be measured first."""
    got = hashlib.sha256(content).hexdigest()
    if got != SHA256:
        raise ValueError(f"{where}: sha256 {got}, not the {SHA256} this importer was measured against")


def fetch() -> SgdpFile:
    """Download SGDP's metadata file from :data:`URL`, refused unless its sha256 is :data:`SHA256`."""
    fetched_at = datetime.now(timezone.utc)
    response = requests.get(URL, timeout=60)
    response.raise_for_status()
    check_sha256(response.content, URL)
    return SgdpFile(response.content, fetched_at)


def load_kept(path: Path) -> SgdpFile:
    """A kept copy of the file (:data:`KEPT_FILE`), refused unless its sha256 is :data:`SHA256`, with the download
    time its generation's SGDP evidence file records; ``ValueError`` where that file is not beside it."""
    content = path.read_bytes()
    check_sha256(content, str(path))
    beside = evidence_file_path(path.parent, TABLE)
    if not beside.is_file():
        raise ValueError(f"{path}: no {beside.name} beside it to say when it was downloaded")
    fetched_at = read_entity_envelope(beside).fetched_at
    return SgdpFile(content, parse_iso_datetime(fetched_at, "fetched_at", str(beside)))


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


_GENOTYPE_WHERE = "sgdp genotype checks"
_GENOTYPE_KEYS = {"catalog", "dataset", "measured", "region", "references", "samples"}
_GENOTYPE_SAMPLE_KEYS = {"sgdp_id", "matched", "best"}
_GENOTYPE_SCORE_KEYS = {"genome", "concordance", "sites"}


def default_genotype_checks_resource():
    """The bundled genotype record, as a package-data resource."""
    return files(f"{__package__}.sources") / "sgdp_genotype_checks.yaml"


def load_genotype_checks(source: Readable | None = None) -> GenotypeChecks:
    """Load and check the genotype record, the bundled one by default; ``ValueError`` naming where it is wrong.

    Checked: its top-level keys, ``dataset`` :data:`DATASET`, ``references`` a mapping of names to URLs; per sample an
    ``sgdp_id``, a ``matched`` genome or null, and under ``best`` each declared reference's scores, each a genome, a
    concordance from 0 to 1 and a count of sites. The scores are the measurement's record; the importer reads only
    ``sgdp_id`` and ``matched``.
    """
    resource = source if source is not None else default_genotype_checks_resource()
    document = yaml.load(resource.read_text(encoding="utf-8"), Loader=unique_key_loader(_GENOTYPE_WHERE))
    expect_keys(document, _GENOTYPE_KEYS, _GENOTYPE_KEYS, _GENOTYPE_WHERE)
    assert isinstance(document, dict)
    catalog = expect_name(document["catalog"], f"{_GENOTYPE_WHERE} catalog")
    if document["dataset"] != DATASET:
        raise ValueError(f"{_GENOTYPE_WHERE}: dataset is {document['dataset']!r}, not {DATASET}")
    for key in ("measured", "region"):
        expect_name(document[key], f"{_GENOTYPE_WHERE} {key}")
    references = document["references"]
    expect_mapping(references, f"{_GENOTYPE_WHERE} references", "reference")
    if not all(isinstance(u, str) and u.startswith("https://") for u in references.values()):
        raise ValueError(f"{_GENOTYPE_WHERE} references: each is a reference's https URL")
    expect_mapping(document["samples"], f"{_GENOTYPE_WHERE} samples", "sample")
    checks = {}
    for sample, entry in document["samples"].items():
        at = f"{_GENOTYPE_WHERE} {sample}"
        expect_keys(entry, _GENOTYPE_SAMPLE_KEYS, _GENOTYPE_SAMPLE_KEYS, at)
        assert isinstance(entry, dict)
        sgdp_id = expect_name(entry["sgdp_id"], f"{at} sgdp_id")
        matched = entry["matched"]
        if matched is not None:
            matched = expect_name(matched, f"{at} matched")
        best = entry["best"]
        if not isinstance(best, dict) or set(best) != set(references):
            raise ValueError(f"{at} best: needs the scores of each reference, {sorted(references)}")
        for reference, scores in best.items():
            if not isinstance(scores, list) or not scores:
                raise ValueError(f"{at} best {reference}: a non-empty list of scores")
            for score in scores:
                expect_keys(score, _GENOTYPE_SCORE_KEYS, _GENOTYPE_SCORE_KEYS, f"{at} best {reference}")
                expect_name(score["genome"], f"{at} best {reference} genome")
                concordance, sites = score["concordance"], score["sites"]
                if not isinstance(concordance, (int, float)) or not 0 <= concordance <= 1:
                    raise ValueError(f"{at} best {reference}: concordance {concordance!r} is not from 0 to 1")
                if not isinstance(sites, int) or isinstance(sites, bool) or sites < 1:
                    raise ValueError(f"{at} best {reference}: sites {sites!r} is not a positive count")
        checks[sample] = GenotypeCheck(str(sample), sgdp_id, matched)
    return GenotypeChecks(catalog, checks)


def outcome(sample: str, rows: list[T2tRow], sgdp: dict[str, dict[str, str]], checks: GenotypeChecks) -> Outcome:
    """One sample's :class:`Outcome`. The sex check: ``tables_disagree`` unless every T2T_CHRY row naming the sample
    names one SGDP genome and one karyotype; ``not_in_sgdp_file`` unless SGDP's file holds the genome;
    ``not_stated`` where SGDP's sex or the karyotype is neither of :data:`KARYOTYPE`'s; else whether they agree.
    The genotype check: ``not_checked`` where the record has no entry for the sample or its tables disagree, else
    whether the genome it matched is the one the tables pair it with.

    ``ValueError`` where the record's entry was measured against another pairing than the tables state: the
    tables have changed since, and the sample is to be measured again.
    """
    pairs = {(r.sgdp_id, r.karyotype) for r in rows}
    if len(pairs) != 1:
        return Outcome(sample, None, TABLES_DISAGREE, GENOTYPE_NOT_CHECKED)
    ((sgdp_id, karyotype),) = pairs
    check = checks.by_sample.get(sample)
    genotype = GENOTYPE_NOT_CHECKED
    if check is not None:
        if check.sgdp_id != sgdp_id:
            raise ValueError(
                f"{_GENOTYPE_WHERE}: {sample} was measured as {check.sgdp_id}, but T2T_CHRY's tables pair it with "
                f"{sgdp_id!r}; measure it again"
            )
        genotype = GENOTYPE_MATCHES if check.matched == sgdp_id else GENOTYPE_NO_MATCH
    found = sgdp.get(sgdp_id) if sgdp_id else None
    if found is None:
        return Outcome(sample, sgdp_id, NOT_IN_SGDP_FILE, genotype)
    sex = KARYOTYPE.get(found[GENDER] or "")
    if sex is None or karyotype not in KARYOTYPE.values():
        return Outcome(sample, sgdp_id, SEX_NOT_STATED, genotype)
    return Outcome(sample, sgdp_id, SEX_AGREES if sex == karyotype else SEX_CONTRADICTS, genotype)


def link_lines(rows: list[T2tRow]) -> Iterator[EntityEvidenceRow]:
    """One T2T_CHRY table's ``collected_from`` lines: each confirmed sample's row naming its SGDP genome."""
    for row in rows:
        if row.sgdp_id:
            yield EntityEvidenceRow(
                field=COLLECTED_FROM,
                target_key_value=row.sample,
                raw_value=row.sgdp_id,
                column=T2T_SGDP_ID,
                identifier_column=SAMPLE_TABLES[row.table],
            )


def donor_lines(genomes: list[str], sgdp: dict[str, dict[str, str]]) -> Iterator[EntityEvidenceRow]:
    """SGDP's lines about each confirmed genome, by its name: a cell each, an empty or missing cell writing nothing."""
    for sgdp_id in genomes:
        found = sgdp[sgdp_id]
        for slot, column in DONOR_COLUMNS.items():
            if (found[column] or "").strip():
                yield EntityEvidenceRow(
                    field=slot,
                    target_key_value=sgdp_id,
                    raw_value=found[column],
                    column=column,
                    identifier_column=SGDP_ID,
                )


def envelope(
    source: EvidenceFileSource, source_type: str, version: str, key: str, catalog: str, fetched_at: datetime
) -> EvidenceFileEnvelope:
    """The envelope of one file of lines about ANVIL_T2T_CHRY's SGDP genomes, keyed by an identifier."""
    return EvidenceFileEnvelope(
        source=source,
        source_type=ImporterSourceTypeEnum(source_type),
        source_version=version,
        source_key=key,
        target=EvidenceTarget(system=REPOSITORY, dataset=DATASET, version=catalog),
        target_key=JoinKeyEnum(JOIN_KEY_ENTITY_IDENTIFIER),
        fetched_at=fetched_at.isoformat(),
    )


def import_sgdp(
    manifest_root: Path,
    catalog: str,
    entity_root: Path,
    service: str,
    read: Fetch = fetch,
    generation: str | None = None,
    checks: GenotypeChecks | None = None,
) -> Import:
    """Write one generation for the samples a check confirms (:attr:`Outcome.confirmed_by`): each T2T_CHRY table's
    links, SGDP's lines, the file as read, and every sample's outcome beside them. ``checks`` is the genotype record,
    the bundled one by default.

    A T2T_CHRY file's source is the table, its url ``service`` (the Azul service the manifest came from), its
    ``fetched_at`` the verbatim manifest's request time; SGDP's file's version is its sha256, since SGDP
    publishes none, and its ``fetched_at`` when it was downloaded. Raises, writing nothing, where T2T_CHRY's
    verbatim manifest cannot be read or has no request time, the genotype record was measured against another
    catalog, names a sample the tables do not or pairs one differently (:func:`outcome`), or no sample is
    confirmed: a generation confirming no sample would supersede an older one with no links at all, so the import
    is refused and any older generation stays current for a person to look at.
    """
    checks = checks if checks is not None else load_genotype_checks()
    if checks.catalog != catalog:
        raise ValueError(f"{_GENOTYPE_WHERE}: measured against {checks.catalog}'s files, not {catalog}'s")
    manifest = verbatim_manifest(manifest_root, catalog, DATASET, sidecar_datasets(manifest_root, catalog))
    if isinstance(manifest, str):
        raise ValueError(manifest)
    requested_at = sidecar_requested_at(manifest_root, catalog, DATASET, FORMAT_VERBATIM)
    if requested_at is None:
        raise ValueError(f"{DATASET}: the {catalog} sidecar records no {FORMAT_VERBATIM} requested_at")
    t2t = t2t_rows(manifest)
    if unknown := sorted(set(checks.by_sample) - set(t2t)):
        raise ValueError(f"{_GENOTYPE_WHERE}: names {', '.join(unknown)}, which no T2T_CHRY SGDP table names")
    got = read()
    sgdp = sgdp_rows(got.content)
    result = Import(generation_dir(entity_root, SOURCE, catalog, DATASET, generation or new_generation()))
    confirmed: list[T2tRow] = []
    for sample in sorted(t2t):
        result.outcomes[sample] = found = outcome(sample, t2t[sample], sgdp, checks)
        if found.confirmed_by:
            confirmed.extend(t2t[sample])
    if not confirmed:
        counts = Counter(o.sex_check for o in result.outcomes.values())
        said = ", ".join(f"{check} {n:,}" for check, n in sorted(counts.items()))
        raise ValueError(f"{DATASET}: no SGDP sample confirmed ({said or 'no SGDP rows'}); nothing written")
    genomes = sorted({r.sgdp_id for r in confirmed if r.sgdp_id})
    with staged_generation(result.directory) as staging:
        for table, identifier in SAMPLE_TABLES.items():
            rows = [r for r in confirmed if r.table == table]
            if not rows:
                continue
            source = EvidenceFileSource(repository=REPOSITORY, dataset=DATASET, table=table, url=service)
            result.written[table] = write_entity_file(
                evidence_file_path(staging, table),
                envelope(source, SOURCE_REPOSITORY_METADATA, catalog, identifier, catalog, requested_at),
                link_lines(rows),
            )
        source = EvidenceFileSource(repository=SOURCE, table=TABLE, url=URL)
        result.written[TABLE] = write_entity_file(
            evidence_file_path(staging, TABLE),
            envelope(source, SOURCE_EXTERNAL_GROUND_TRUTH, SHA256, SGDP_ID, catalog, got.fetched_at),
            donor_lines(genomes, sgdp),
        )
        (staging / KEPT_FILE).write_bytes(got.content)
        write_outcomes(staging, DATASET, (o.to_dict() for o in result.outcomes.values()))
    return result


def describe(result: Import) -> list[str]:
    """Where the import went, each file's lines, how many samples each check confirmed, and each sample left out with
    both checks' findings."""
    out = [f"{DATASET} -> {result.directory} ({len(result.outcomes):,} SGDP samples)"]
    out += [f"  {table}: {n:,} lines" for table, n in result.written.items()]
    linked = result.linked
    out.append(f"  linked: {len(linked):,}")
    for check in code_rules.IDENTITY_CHECKS:
        n = sum(check.id in result.outcomes[s].confirmed_by for s in linked)
        out.append(f"    confirmed by {check.id}: {n:,}")
    left = [o for o in result.outcomes.values() if not o.confirmed_by]
    out.append(f"  left out: {len(left):,}")
    out += [f"    {o.sample} ({o.sgdp_id}): sex {o.sex_check}, genotype {o.genotype_check}" for o in left]
    return out
