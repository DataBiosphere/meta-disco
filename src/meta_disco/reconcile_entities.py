"""Donor and sample records, settled at reconcile from entity evidence (#693, ADR-0002 decision 1).

A donor is a record keyed by its identifier (``coriell:HG00096``), so one record gathers
what every dataset's tables say about one person. Each line of an entity evidence file
(``entity_evidence``) names a donor by the string the source wrote; the identifier rules
recognise it as a donor in the line's dataset (``sample_identity``, ``DONOR``), the line is
translated into claims as a file's line is (``resolution.translate``), and each of the donor's
slots is settled from every claim on it by :func:`reconcile.settle`, the rule a file's
dimensions are settled by. A line whose identifier no rule recognises as a donor is counted,
never guessed; a value no authored row reads makes no claim, and the donors it was written
for are counted.

A donor's family (``models.FAMILY_FIELDS``, #582) is settled by the same rule, but never
translated. A ``mother`` or ``father`` line's value names the parent, recognised as a donor in
the line's dataset by the identifier rules, and its claim declares the parent's identifier and
cites the rule that recognised it; PED's ``0`` ("not known") makes no claim, and a parent no
rule recognises is counted, never guessed. A ``family_id`` line's value is the answer as written
(``code_rules.FAMILY_ID_AS_WRITTEN``), but an empty or blank one names no family, makes no claim
and is counted. Each parent named has a donor record of its own.

A sample's slots (``models.SAMPLE_SLOTS``, #699) come from the repository's own record of it, a line
naming the sample: ``biosample_type`` is translated as a donor's slot is, and ``anatomical_site``
taken as written (``code_rules.ANATOMICAL_SITE_AS_WRITTEN``), AnVIL's ``Unknown`` or a blank making
no claim and counted. Every donor and sample slot carries ``use`` (``resolution.use_for``).

A repository's own record of a donor or sample (AnVIL's ``anvil_donor`` and
``anvil_biosample``, #669) reaches ours through a line carrying its identifier
(``models.REPOSITORY_ID_FIELDS``), keyed by the identifier of the submitter row it was made
from: recognised as a donor or a sample by the line's field, it is listed on that record's
``repository_ids``, never translated. Many may tie to one record (a person has an AnVIL donor
in each dataset whose donors are made from a row naming them, under one or more distinct
ids); one tying to two records is refused, never chosen.

A sample record is written for every sample a reconciled file names (the run's sample
lists), every sample a repository's identifier ties to and every sample a slot line names, with the donor it was collected
from where an identifier rule naming both says so (``IdentifierRuleSet.collected_from``). A
donor record is written for every donor the evidence names and every donor a sample's
``collected_from`` or a donor's ``mother`` or ``father`` points to, so a join from a file to its
donors, or from a donor to its parents, finds a record for each.

Nothing here reads or writes a file record: a file reaches its donors through its
``samples`` (epic #692, decision 5).
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from . import code_rules
from .entity_evidence import entries, read_entity_envelope
from .models import (
    ANATOMICAL_SITE,
    CONFLICT,
    DONOR_SLOTS,
    FAMILY_FIELDS,
    FAMILY_ID,
    JOIN_KEY_ENTITY_IDENTIFIER,
    KIND_OF_SLOT,
    PARENT_FIELDS,
    REPOSITORY_ID_FIELDS,
    REPOSITORY_IDS,
    SAMPLE_SLOTS,
    SOURCE_IDENTIFIER_RULE,
    SOURCE_PUBLISHED_VALUE,
    UNKNOWN_PARENT,
    UNKNOWN_SITE,
    UNTRANSLATED_SLOTS,
)
from .output_utils import relative_to
from .reconcile_lineage import applies
from .resolution import NO_EVIDENCE, SlotEvidence, declaration, settle, translate, use_for
from .rule_engine import make_claim
from .sample_identity import (
    DONOR,
    KIND_OF_REPOSITORY_ID,
    SAMPLE,
    EntityKind,
    Identifier,
    IdentifierRuleSet,
    identifier_order,
    members_of,
    most_frequent,
)
from .source_evidence import EvidenceEntry, discover
from .value_map import ValueMap

# How many unrecognised identifiers the report names per table.
MAX_EXAMPLES = 5

# Every field an entity line may name, for :func:`gather`'s one read of each file.
_ENTITY_FIELDS = (*DONOR_SLOTS, *SAMPLE_SLOTS, *REPOSITORY_ID_FIELDS)
# The entity rule a slot taken as written cites.
_AS_WRITTEN_RULES = {slot: rule.id for rule in code_rules.ENTITY_RULES for slot in rule.sets}
# The report's labels for the lines that name no value (:func:`_names_no_value`).
UNKNOWN_PARENT_LINES = "unknown_parent_lines"
BLANK_FAMILY_ID_LINES = "blank_family_id_lines"
UNKNOWN_SITE_LINES = "unknown_site_lines"
# What a repository identifier must be to be listed: the schema's `RepositoryIdentifier.id` pattern.
_ONE_LINE = re.compile(r"[^\r\n]+")


@dataclass(frozen=True, order=True)
class RepositoryId:
    """A repository's own identifier for a donor or sample, and the dataset and table holding it (the schema's ``RepositoryIdentifier``).

    A dataclass and not the generated model: it is hashed into a record's set and sorted, and
    ``to_dict`` is the generated model's shape, held to it by the tests' ``DonorRecord`` and
    ``SampleRecord`` checks.
    """

    repository: str
    dataset: str
    table: str
    id: str

    @property
    def key(self) -> tuple[str, str]:
        """What makes it one identifier: its repository and id, whichever dataset holds it."""
        return self.repository, self.id

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EntityEvidence:
    """What the entity evidence said, per recognised donor and slot, the repository identifiers per
    recognised donor or sample, and what each file gave: :func:`gather`'s result.

    ``sample_slots`` is the samples' (#699), as ``slots`` is the donors'. ``no_value_lines`` counts, per report
    label (:data:`UNKNOWN_PARENT_LINES`, :data:`BLANK_FAMILY_ID_LINES`, :data:`UNKNOWN_SITE_LINES`), the
    lines that name no value, and ``unrecognised_parents`` the parent strings no rule recognises, each
    per dataset and table.
    """

    slots: dict[Identifier, dict[str, SlotEvidence]]
    sample_slots: dict[Identifier, dict[str, SlotEvidence]]
    named_in: dict[tuple[str, str], set[Identifier]]
    files: list[dict]
    unrecognised: dict[tuple[str | None, str | None], Counter]
    repository_ids: dict[tuple[EntityKind, Identifier], set[RepositoryId]]
    no_value_lines: dict[str, Counter]
    unrecognised_parents: dict[tuple[str | None, str | None], Counter]


@dataclass
class EntityResult:
    """The donor and sample records, in identifier order, and the report's ``entities`` block."""

    donors: list[dict]
    samples: list[dict]
    report: dict


def select_entity_evidence(entity_root: Path, repository: str, catalog: str | None) -> tuple[list[Path], list[dict]]:
    """The current entity files about ``repository``'s ``catalog``, and those about another repository, listed.

    The rule ``reconcile.select_evidence`` holds a file's evidence to
    (``reconcile_lineage.applies``): a file for another catalog is neither read nor listed,
    and one about another repository is skipped and listed.
    """
    applicable, skipped = [], []
    for path in discover(entity_root):
        target = read_entity_envelope(path).target
        if target.system != repository:
            skipped.append({"path": relative_to(path, entity_root), "target_system": target.system})
        elif applies(target, repository, catalog):
            applicable.append(path)
    return applicable, skipped


def gather(paths: Iterable[Path], entity_root: Path, table: ValueMap, rules: IdentifierRuleSet) -> EntityEvidence:
    """Every line of ``paths`` (:func:`select_entity_evidence`), recognised, and translated into its donor's or
    sample's slots, read as an untranslated slot's (:func:`_untranslated_claim`: a donor's family, a sample's
    site), or listed among its donor's or sample's repository identifiers.

    Reads every line, so a malformed file or line, an identifier two rules match, a family line
    in a published table's file, or a repository identifier that is empty or more than one line,
    in a file other than a published table's, or tying to two records raises here: reconcile calls this before it
    writes anything. A translated claim cites its value-map row, a parent's the identifier rule
    that recognised the parent, and a family id's or a site's its entity rule (``code_rules.ENTITY_RULES``); each carries
    the line's source and raw value, joined by ``entity_identifier``. A repository identifier is one record's by its kind,
    repository and id: the same one in two datasets ties to one record, or raises.
    """
    slots: dict[Identifier, dict[str, SlotEvidence]] = defaultdict(lambda: defaultdict(SlotEvidence))
    sample_slots: dict[Identifier, dict[str, SlotEvidence]] = defaultdict(lambda: defaultdict(SlotEvidence))
    named_in: dict[tuple[str, str], set[Identifier]] = defaultdict(set)
    files, unrecognised = [], defaultdict(Counter)
    repository_ids: dict[tuple[EntityKind, Identifier], set[RepositoryId]] = defaultdict(set)
    tied: dict[tuple[EntityKind, str, str], tuple[Identifier, Path]] = {}
    no_value_lines: dict[str, Counter] = defaultdict(Counter)
    unrecognised_parents: dict[tuple[str | None, str | None], Counter] = defaultdict(Counter)
    for path in paths:
        envelope = read_entity_envelope(path)
        dataset = envelope.target.dataset
        lines = misses = 0
        for entry in entries(path, envelope, _ENTITY_FIELDS):
            lines += 1
            alias_kind = KIND_OF_REPOSITORY_ID.get(entry.field)
            if alias_kind is not None and envelope.source_type != SOURCE_PUBLISHED_VALUE:
                raise ValueError(
                    f"{relative_to(path, entity_root)}: carries {entry.field}, a repository's own identifier, in a "
                    f"{envelope.source_type} file; only the repository's published table issues one"
                )
            if entry.field in FAMILY_FIELDS and envelope.source_type == SOURCE_PUBLISHED_VALUE:
                raise ValueError(
                    f"{relative_to(path, entity_root)}: carries {entry.field} in a published file; the repository's "
                    "model has no family, which only a submitter table states (#582)"
                )
            if alias_kind is not None and _ONE_LINE.fullmatch(entry.raw_value) is None:
                raise ValueError(
                    f"{relative_to(path, entity_root)}: {entry.field} {entry.raw_value!r} for "
                    f"{entry.target_key_value!r} is not an identifier: empty, or more than one line"
                )
            kind = alias_kind or KIND_OF_SLOT[entry.field]  # whose slot the line names
            got = rules.recognise(entry.target_key_value, dataset, kind)
            if got is None:
                misses += 1
                unrecognised[(dataset, envelope.source.table)][entry.target_key_value] += 1
                continue
            if alias_kind is not None:
                alias = RepositoryId(
                    envelope.source.repository, str(dataset), str(envelope.source.table), entry.raw_value
                )
                earlier, earlier_path = tied.setdefault((kind, *alias.key), (got.identifier, path))
                if earlier != got.identifier:
                    raise ValueError(
                        f"{relative_to(path, entity_root)}: {alias.repository} {kind} {alias.id!r} ties to "
                        f"{got.identifier.to_dict()} here and to {earlier.to_dict()} on an earlier line of "
                        f"{relative_to(earlier_path, entity_root)}; a repository's identifier names one record, "
                        "and which is not chosen"
                    )
                repository_ids[(kind, got.identifier)].add(alias)
                continue
            exact = got.identifier.id == entry.target_key_value  # not where a rule rewrote it (GM19908 -> NA19908)
            # The donor or sample the line names counts toward its dataset's slot, whatever the line's value gives.
            named_in[(str(dataset), entry.field)].add(got.identifier)
            # A donor or sample a line names has a record, whatever the line's value gives.
            record_slots = (sample_slots if kind == SAMPLE else slots)[got.identifier]
            if entry.field not in UNTRANSLATED_SLOTS:
                translate(record_slots, entry, envelope.source_type, JOIN_KEY_ENTITY_IDENTIFIER, table, exact)
                continue
            where = (dataset, envelope.source.table)
            if (label := _names_no_value(entry)) is not None:
                no_value_lines[label][where] += 1
                continue
            claim = _untranslated_claim(entry, envelope.source_type, dataset, rules, exact)
            if claim is None:
                unrecognised_parents[where][entry.raw_value] += 1
                continue
            if claim not in record_slots[entry.field].claims:
                record_slots[entry.field].claims.append(claim)
        files.append(
            {
                "path": relative_to(path, entity_root),
                "source_type": envelope.source_type,
                "dataset": dataset,
                "table": envelope.source.table,
                "lines": lines,
                "unrecognised": misses,
            }
        )
    return EntityEvidence(
        slots=slots,
        sample_slots=sample_slots,
        named_in=named_in,
        files=files,
        unrecognised=unrecognised,
        repository_ids=repository_ids,
        no_value_lines=no_value_lines,
        unrecognised_parents=unrecognised_parents,
    )


def _names_no_value(entry: EvidenceEntry) -> str | None:
    """The report label of an untranslated line that names no value, or None: PED's ``0`` for a parent,
    an empty or blank family id, AnVIL's ``Unknown`` or a blank site."""
    raw = entry.raw_value
    if entry.field in PARENT_FIELDS:
        return UNKNOWN_PARENT_LINES if raw == UNKNOWN_PARENT else None
    if entry.field == FAMILY_ID:
        return BLANK_FAMILY_ID_LINES if not raw.strip() else None
    if entry.field == ANATOMICAL_SITE:
        return UNKNOWN_SITE_LINES if raw.strip() in ("", UNKNOWN_SITE) else None
    raise ValueError(f"{entry.field!r} is not an untranslated slot this reads")


def _untranslated_claim(
    entry: EvidenceEntry, source_type: str, dataset: str | None, rules: IdentifierRuleSet, exact: bool
) -> dict | None:
    """The claim one untranslated line makes (``models.UNTRANSLATED_SLOTS``); None for a parent no rule recognises.

    A parent is recognised as a donor in the line's dataset, and its claim declares the parent's
    identifier and cites the rule that recognised it. A family id or a site is the answer as written,
    citing its entity rule.
    """
    if entry.field in PARENT_FIELDS:
        recognised = rules.recognise(entry.raw_value, dataset, DONOR)
        if recognised is None:
            return None
        rule_id, value = recognised.rule_id, recognised.identifier.to_dict()
    else:
        rule_id, value = _AS_WRITTEN_RULES[entry.field], entry.raw_value
    return make_claim(
        source_type=source_type,
        rule_id=rule_id,
        value=value,
        source=entry.source,
        raw_value=entry.raw_value,
        join_key=JOIN_KEY_ENTITY_IDENTIFIER,
        match_exact=exact,
    )


def _settle_slot(slot: str, said: SlotEvidence) -> dict:
    """One donor or sample slot from its claims' declarations, by :func:`reconcile.settle`: its value,
    status, ``use`` (:func:`reconcile.use_for`, #699) and evidence.

    A slot with no vocabulary (``models.UNTRANSLATED_SLOTS``) has its answer settled as its JSON spelling
    and stored decoded: a parent's claims declare an identifier, which :func:`declaration` already spells
    so, and a string as written is quoted here, so one written ``not_applicable`` stays the source's
    string, never the status.
    """
    declared = {d for d in map(declaration, said.claims) if d is not None}
    if slot in _AS_WRITTEN_RULES:
        declared = {json.dumps(d) for d in declared}
    status, value = settle(slot, False, declared, False, SOURCE_PUBLISHED_VALUE in said.unreviewed)
    if value is not None and slot in UNTRANSLATED_SLOTS:
        value = json.loads(value)
    return {"value": value, "status": status, "use": use_for(status), "evidence": list(said.claims)}


def _settle_record(
    record: dict, said: dict[str, SlotEvidence], slots: tuple[str, ...], conflicts: list[dict], unreviewed: Counter
) -> dict[str, str]:
    """Settle each of ``slots`` onto ``record`` from ``said`` (:func:`_settle_slot`), listing its conflicts and
    counting the slots a source spoke to with a value no authored row reads; return each slot's status."""
    statuses = {}
    for slot in slots:
        evidence = said.get(slot, NO_EVIDENCE)
        record[slot] = _settle_slot(slot, evidence)
        statuses[slot] = record[slot]["status"]
        unreviewed[slot] += bool(evidence.unreviewed)
        if statuses[slot] == CONFLICT:
            conflicts.append({"identifier": record["identifier"], "slot": slot, "evidence": record[slot]["evidence"]})
    return statuses


def _parents(slots: dict[Identifier, dict[str, SlotEvidence]]) -> set[Identifier]:
    """Every donor a ``mother`` or ``father`` claim in ``slots`` names."""
    return {
        Identifier(**claim["value"])
        for donor_slots in slots.values()
        for slot in PARENT_FIELDS
        if slot in donor_slots
        for claim in donor_slots[slot].claims
        if isinstance(claim.get("value"), dict)
    }


def reconcile_entities(
    evidence: EntityEvidence,
    rules: IdentifierRuleSet,
    sample_lists: Iterable[dict],
    skipped: list[dict] | None = None,
) -> EntityResult:
    """Settle every donor ``evidence`` names, link every sample ``sample_lists`` hold or a repository identifier
    ties to, list each record's repository identifiers, and count what was done.

    ``evidence`` is :func:`gather`'s; ``sample_lists`` are the run's reconciled ``SampleList``
    dicts. A donor a sample's ``collected_from`` points to, or a donor's ``mother`` or ``father``
    claim names, gets a record, evidence or none.
    """
    slots, named_in, files, unrecognised = evidence.slots, evidence.named_in, evidence.files, evidence.unrecognised
    repository_ids = evidence.repository_ids
    named_by_files = {m for entry in sample_lists for m in members_of(entry)}
    tied_samples = {ident for kind, ident in repository_ids if kind == SAMPLE}
    sample_slots = evidence.sample_slots
    sample_records, linked, conflicts = [], Counter(), []
    sample_settled: dict[Identifier, dict[str, str]] = {}
    unreviewed: dict[EntityKind, Counter] = {DONOR: Counter(), SAMPLE: Counter()}
    for sample in sorted(named_by_files | tied_samples | set(sample_slots), key=identifier_order):
        record: dict = {"identifier": sample.to_dict()}
        found = rules.collected_from(sample)
        if found is not None:
            record["collected_from"] = {
                "donor": found.identifier.to_dict(),
                "named_by": [{"source_type": SOURCE_IDENTIFIER_RULE, "rule_id": found.rule_id}],
            }
            linked[sample.namespace] += 1
            slots[found.identifier]  # a donor a sample points to has a record, evidence or none
        sample_settled[sample] = _settle_record(
            record, sample_slots.get(sample, {}), SAMPLE_SLOTS, conflicts, unreviewed[SAMPLE]
        )
        _list_repository_ids(record, repository_ids.get((SAMPLE, sample)))
        sample_records.append(record)
    for kind, ident in repository_ids:
        if kind == DONOR:
            slots[ident]  # a donor a repository identifier ties to has a record, slots or none
    parents = _parents(slots)
    for parent in parents:
        slots[parent]  # a donor named as a parent has a record, slots or none

    donors = []
    settled: dict[Identifier, dict[str, str]] = {}
    for donor in sorted(slots, key=identifier_order):
        record = {"identifier": donor.to_dict()}
        settled[donor] = _settle_record(record, slots[donor], DONOR_SLOTS, conflicts, unreviewed[DONOR])
        _list_repository_ids(record, repository_ids.get((DONOR, donor)))
        donors.append(record)

    # Per dataset and slot: the donors (or samples) the dataset's lines name, each counted at its overall
    # settled status, so a dataset agreeing with a conflicted record still shows the conflict.
    by_dataset: dict[str, dict[str, dict]] = defaultdict(dict)
    for (dataset, slot), named in named_in.items():
        noun, statuses = ("samples", sample_settled) if KIND_OF_SLOT[slot] == SAMPLE else ("donors", settled)
        by_dataset[dataset][slot] = {noun: len(named), **Counter(statuses[r][slot] for r in named)}
    report = {
        "files": files,
        "skipped_files": skipped or [],
        "donors": len(donors),
        "statuses": {slot: dict(Counter(s[slot] for s in settled.values())) for slot in DONOR_SLOTS},
        "by_dataset": dict(by_dataset),
        "conflicts": conflicts,
        "unrecognised": _per_table(unrecognised),
        "unreviewed_donors": {slot: n for slot, n in unreviewed[DONOR].items() if n},
        "family": {
            "parents_named": len(parents),
            "parents_with_no_claims": sum(1 for p in parents if not any(e.claims for e in slots[p].values())),
            **{
                label: _lines_per_table(evidence.no_value_lines.get(label, Counter()))
                for label in (UNKNOWN_PARENT_LINES, BLANK_FAMILY_ID_LINES)
            },
            "unrecognised_parents": _per_table(evidence.unrecognised_parents),
        },
        "samples": {
            "total": len(sample_records),
            "named_by_files": len(named_by_files),
            "collected_from": dict(linked),
            "statuses": {slot: dict(Counter(s[slot] for s in sample_settled.values())) for slot in SAMPLE_SLOTS},
            UNKNOWN_SITE_LINES: _lines_per_table(evidence.no_value_lines.get(UNKNOWN_SITE_LINES, Counter())),
            "unreviewed": {slot: n for slot, n in unreviewed[SAMPLE].items() if n},
        },
        REPOSITORY_IDS: {kind: _repository_id_counts(repository_ids, kind) for kind in (DONOR, SAMPLE)},
    }
    return EntityResult(donors, sample_records, report)


def _by_place(item: tuple[tuple[str | None, str | None], object]) -> tuple[str, str]:
    """A ``((dataset, table), count)`` item's sort key, a missing part sorting first."""
    (dataset, table), _ = item
    return dataset or "", table or ""


def _lines_per_table(counts: Counter) -> list[dict]:
    """Per dataset and table, in that order: how many lines."""
    return [
        {"dataset": dataset, "table": tbl, "lines": n} for (dataset, tbl), n in sorted(counts.items(), key=_by_place)
    ]


def _per_table(counts: dict[tuple[str | None, str | None], Counter]) -> list[dict]:
    """Per dataset and table, in that order: the strings counted, how many lines, and the most frequent as examples."""
    return [
        {"dataset": dataset, "table": tbl, "lines": sum(c.values()), "examples": most_frequent(c, MAX_EXAMPLES)}
        for (dataset, tbl), c in sorted(counts.items(), key=_by_place)
    ]


def _list_repository_ids(record: dict, aliases: set[RepositoryId] | None) -> None:
    """Put ``aliases`` on ``record``, in order, where there are any."""
    if aliases:
        record[REPOSITORY_IDS] = [a.to_dict() for a in sorted(aliases)]


def _repository_id_counts(
    repository_ids: dict[tuple[EntityKind, Identifier], set[RepositoryId]], kind: EntityKind
) -> dict:
    """The repository identifiers tied to records of ``kind``: the records holding one, the distinct identifiers,
    the records by how many distinct identifiers each holds, and per dataset its identifiers and the records they tie to."""
    held = {ident: aliases for (k, ident), aliases in repository_ids.items() if k == kind}
    per_record = Counter(len({a.key for a in aliases}) for aliases in held.values())
    ids_in: dict[str, set[tuple[str, str]]] = defaultdict(set)
    records_in: dict[str, set[Identifier]] = defaultdict(set)
    for ident, aliases in held.items():
        for alias in aliases:
            ids_in[alias.dataset].add(alias.key)
            records_in[alias.dataset].add(ident)
    return {
        "records": len(held),
        "ids": len({a.key for aliases in held.values() for a in aliases}),
        "ids_per_record": {str(n): count for n, count in sorted(per_record.items())},
        "by_dataset": {d: {"ids": len(ids_in[d]), "records": len(records_in[d])} for d in sorted(ids_in)},
    }
