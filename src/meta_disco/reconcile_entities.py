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
from dataclasses import dataclass
from pathlib import Path

from .entity_evidence import entries, read_entity_envelope
from .models import CONFLICT, DONOR_FIELDS, JOIN_KEY_ENTITY_IDENTIFIER, SOURCE_IDENTIFIER_RULE, SOURCE_PUBLISHED_VALUE
from .output_utils import relative_to
from .reconcile_lineage import applies
from .resolution import NO_EVIDENCE, SlotEvidence, declaration, settle, translate
from .sample_identity import DONOR, Identifier, IdentifierRuleSet, identifier_order, members_of, most_frequent
from .source_evidence import discover
from .value_map import ValueMap

# How many unrecognised identifiers the report names per table.
MAX_EXAMPLES = 5


@dataclass
class EntityEvidence:
    """What the entity evidence said, per recognised donor and slot, and what each file gave: :func:`gather`'s result."""

    slots: dict[Identifier, dict[str, SlotEvidence]]
    named_in: dict[tuple[str, str], set[Identifier]]
    files: list[dict]
    unrecognised: dict[tuple[str | None, str | None], Counter]


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
    """Every line of ``paths`` (:func:`select_entity_evidence`), recognised and translated into its donor's slots.

    Reads every line, so a malformed file or line, or an identifier two rules match, raises
    here: reconcile calls this before it writes anything. Each claim cites its value-map row
    and carries the line's source and raw value, joined by ``entity_identifier``.
    """
    slots: dict[Identifier, dict[str, SlotEvidence]] = defaultdict(lambda: defaultdict(SlotEvidence))
    named_in: dict[tuple[str, str], set[Identifier]] = defaultdict(set)
    files, unrecognised = [], defaultdict(Counter)
    for path in paths:
        envelope = read_entity_envelope(path)
        dataset = envelope.target.dataset
        lines = misses = 0
        for entry in entries(path, envelope):
            lines += 1
            got = rules.recognise(entry.target_key_value, dataset, DONOR)
            if got is None:
                misses += 1
                unrecognised[(dataset, envelope.source.table)][entry.target_key_value] += 1
                continue
            named_in[(str(dataset), entry.field)].add(got.identifier)
            translate(slots[got.identifier], entry, envelope.source_type, JOIN_KEY_ENTITY_IDENTIFIER, table)
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
    return EntityEvidence(slots, named_in, files, unrecognised)


def reconcile_entities(
    evidence: EntityEvidence,
    rules: IdentifierRuleSet,
    sample_lists: Iterable[dict],
    skipped: list[dict] | None = None,
) -> EntityResult:
    """Settle every donor ``evidence`` names, link every sample ``sample_lists`` hold, and count what was done.

    ``evidence`` is :func:`gather`'s; ``sample_lists`` are the run's reconciled ``SampleList``
    dicts. A donor a sample's ``collected_from`` points to gets a record, evidence or none.
    """
    slots, named_in, files, unrecognised = evidence.slots, evidence.named_in, evidence.files, evidence.unrecognised
    sample_records, linked = [], Counter()
    for sample in sorted({m for entry in sample_lists for m in members_of(entry)}, key=identifier_order):
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

    donors, conflicts = [], []
    settled: dict[Identifier, dict[str, str]] = {}
    unreviewed: Counter = Counter()
    for donor in sorted(slots, key=identifier_order):
        record = {"identifier": donor.to_dict()}
        settled[donor] = {}
        for slot in DONOR_FIELDS:
            said = slots[donor].get(slot, NO_EVIDENCE)
            declared = {d for d in map(declaration, said.claims) if d is not None}
            status, value = settle(slot, False, declared, False, SOURCE_PUBLISHED_VALUE in said.unreviewed)
            record[slot] = {"value": value, "status": status, "evidence": list(said.claims)}
            settled[donor][slot] = status
            unreviewed[slot] += bool(said.unreviewed)
            if status == CONFLICT:
                conflicts.append({"identifier": donor.to_dict(), "slot": slot, "evidence": list(said.claims)})
        donors.append(record)

    by_dataset: dict[str, dict[str, dict]] = defaultdict(dict)
    for (dataset, slot), named in named_in.items():
        by_dataset[dataset][slot] = {"donors": len(named), **Counter(settled[d][slot] for d in named)}
    report = {
        "files": files,
        "skipped_files": skipped or [],
        "donors": len(donors),
        "statuses": {slot: dict(Counter(s[slot] for s in settled.values())) for slot in DONOR_FIELDS},
        "by_dataset": dict(by_dataset),
        "conflicts": conflicts,
        "unrecognised": [
            {"dataset": dataset, "table": tbl, "lines": sum(c.values()), "examples": most_frequent(c, MAX_EXAMPLES)}
            for (dataset, tbl), c in unrecognised.items()
        ],
        "unreviewed_donors": {slot: n for slot, n in unreviewed.items() if n},
        "samples": {"total": len(sample_records), "collected_from": dict(linked)},
    }
    return EntityResult(donors, sample_records, report)
