"""Donor and sample records, settled at reconcile from entity evidence (#693, ADR-0002 decision 1).

A donor is a record keyed by its identifier (``coriell:HG00096``), so one record gathers
what every dataset's tables say about one person. Each line of an entity evidence file
(``entity_evidence``) names a donor by the string the source wrote; the identifier rules
recognise it as a donor in the line's dataset (``sample_identity``, ``DONOR``), the value map
translates its value into claims (``value_map.claims_from``), and each of the donor's slots
is settled from every claim on it by :func:`reconcile.settle`, the rule a file's dimensions
are settled by. A line whose identifier no rule recognises as a donor is counted, never
guessed; a line whose value no authored row reads makes no claim and is counted.

A sample record is written for every sample a reconciled file names (the run's sample
lists), with the donor it was collected from where an identifier rule naming both says so
(``IdentifierRuleSet.collected_from``). A donor record is written for every donor the
evidence names and every donor a sample's ``collected_from`` points to, so a join from a
file to its donors finds a record for each.

Nothing here reads or writes a file record: a file reaches its donors through its
``samples`` (epic #692, decision 5).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from .entity_evidence import claim_source, iter_entity_evidence, read_entity_envelope
from .models import (
    CLASSIFIED,
    CONFLICT,
    DONOR_FIELDS,
    JOIN_KEY_ENTITY_IDENTIFIER,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    SOURCE_IDENTIFIER_RULE,
    SOURCE_PUBLISHED_VALUE,
)
from .output_utils import relative_to
from .reconcile_lineage import applies
from .resolution import declaration, settle
from .sample_identity import DONOR, Identifier, IdentifierRuleSet, members_of, most_frequent
from .source_evidence import EvidenceEntry, discover
from .value_map import ValueMap, claims_from

# How many unrecognised identifiers the report names per table.
MAX_EXAMPLES = 5
STATUSES = (CLASSIFIED, NOT_APPLICABLE, CONFLICT, NOT_CLASSIFIED)


def _key(identifier: Identifier) -> tuple[str, str, str]:
    return (identifier.namespace, identifier.id, identifier.dataset or "")


@dataclass
class _Slot:
    """What one donor's slot gathered: its claims, and whether the published source spoke unreviewed."""

    claims: list[dict] = field(default_factory=list)
    published_unreviewed: bool = False


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


def reconcile_entities(
    paths: Iterable[Path],
    entity_root: Path,
    table: ValueMap,
    rules: IdentifierRuleSet,
    sample_lists: Iterable[dict],
    skipped: list[dict] | None = None,
) -> EntityResult:
    """Settle every donor ``paths`` name, link every sample ``sample_lists`` hold, and count what was done.

    ``paths`` are entity files (:func:`select_entity_evidence`); ``sample_lists`` are the
    run's reconciled ``SampleList`` dicts. Each claim cites its value-map row and carries the
    line's source and raw value, joined by ``entity_identifier``.
    """
    slots: dict[Identifier, dict[str, _Slot]] = defaultdict(lambda: {s: _Slot() for s in DONOR_FIELDS})
    named_in: dict[tuple[str, str], set[Identifier]] = defaultdict(set)
    files, unrecognised, unreviewed = [], defaultdict(Counter), Counter()
    for path in paths:
        envelope = read_entity_envelope(path)
        dataset = envelope.target.dataset
        source_type = envelope.source_type
        counts = Counter()
        for row in iter_entity_evidence(path):
            counts["lines"] += 1
            got = rules.recognise(row.target_key_value, dataset, DONOR)
            if got is None:
                counts["unrecognised"] += 1
                unrecognised[(dataset, envelope.source.table)][row.target_key_value] += 1
                continue
            donor = got.identifier
            named_in[(str(dataset), row.field)].add(donor)
            entry = EvidenceEntry(row.field, row.target_key_value, row.raw_value, claim_source(envelope, row))
            claims = claims_from(entry, source_type, table, join_key=JOIN_KEY_ENTITY_IDENTIFIER)
            if not claims:
                counts["unreviewed"] += 1
                unreviewed[row.field] += 1
                if source_type == SOURCE_PUBLISHED_VALUE:
                    slots[donor][row.field].published_unreviewed = True
            for slot, claim in claims:
                slots[donor][slot].claims.append(claim)
        files.append(
            {
                "path": relative_to(path, entity_root),
                "source_type": source_type,
                "dataset": dataset,
                "table": envelope.source.table,
                **{k: counts[k] for k in ("lines", "unrecognised", "unreviewed")},
            }
        )

    samples = sorted({m for entry in sample_lists for m in members_of(entry)}, key=_key)
    sample_records, linked = [], Counter()
    for sample in samples:
        record: dict = {"identifier": sample.to_dict()}
        found = rules.collected_from(sample)
        if found is not None:
            record["collected_from"] = {
                "donor": found.identifier.to_dict(),
                "named_by": [{"source_type": SOURCE_IDENTIFIER_RULE, "rule_id": found.rule_id}],
            }
            linked[sample.namespace] += 1
            slots[found.identifier]  # a donor a sample points to has a record, evidence or none
        sample_records.append(record)

    donors, statuses, conflicts = [], {s: Counter() for s in DONOR_FIELDS}, []
    settled: dict[Identifier, dict[str, str]] = {}
    for donor in sorted(slots, key=_key):
        record = {"identifier": donor.to_dict()}
        for slot, gathered in slots[donor].items():
            declared = {d for d in map(declaration, gathered.claims) if d is not None}
            status, value = settle(slot, False, declared, False, gathered.published_unreviewed)
            record[slot] = {"value": value, "status": status, "evidence": gathered.claims}
            statuses[slot][status] += 1
            settled.setdefault(donor, {})[slot] = status
            if status == CONFLICT:
                conflicts.append({"identifier": donor.to_dict(), "slot": slot, "evidence": gathered.claims})
        donors.append(record)

    by_dataset: dict[str, dict[str, dict]] = defaultdict(dict)
    for (dataset, slot), named in sorted(named_in.items()):
        by_dataset[dataset][slot] = {
            "donors": len(named),
            **Counter(settled[d][slot] for d in named),
        }
    report = {
        "files": files,
        "skipped_files": skipped or [],
        "donors": len(donors),
        "statuses": {slot: {s: statuses[slot][s] for s in STATUSES if statuses[slot][s]} for slot in DONOR_FIELDS},
        "by_dataset": dict(by_dataset),
        "conflicts": conflicts,
        "unrecognised": [
            {"dataset": dataset, "table": tbl, "lines": sum(c.values()), "examples": most_frequent(c, MAX_EXAMPLES)}
            for (dataset, tbl), c in sorted(unrecognised.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))
        ],
        "unreviewed_lines": {slot: unreviewed[slot] for slot in DONOR_FIELDS if unreviewed[slot]},
        "samples": {"total": len(sample_records), "collected_from": dict(sorted(linked.items()))},
    }
    return EntityResult(donors, sample_records, report)
