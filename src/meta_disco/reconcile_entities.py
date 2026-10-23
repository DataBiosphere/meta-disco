"""Donor and sample records, settled at reconcile from entity evidence (#693, ADR-0002 decision 1).

A donor is a record keyed by its identifier (``coriell:HG00096``), so one record gathers
what every dataset's tables say about one person. Each line of an entity evidence file
(``entity_evidence``) names a donor by the string the source wrote (or, for a sample's slot or
repository id, a sample); the identifier rules recognise it as that kind in the line's dataset
(``sample_identity``, ``DONOR``, ``SAMPLE``), the line is
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

**A donor may be named by more than one identifier** (#559). A ``same_donor_as`` line, about the
donor it names, names another identifier for it: SGDP's metadata file says its genome
``S_Spanish-2`` is the person of Coriell's ``HG01504``. The links are followed to the end of their
chain, whose identifier is the main one: the record is keyed by it and lists the others under
``synonyms``, each with its own line's source; whatever a line keyed by a synonym says, and wherever a
parent, a sample's donor or a repository identifier names it, is read as the main identifier. A
synonym whose chain branches or comes back on itself is joined to none, and counted.

A sample record is written for every sample a reconciled file names (the run's sample
lists), every sample a repository's identifier ties to and every sample a slot or ``collected_from``
line names, with the donor it was collected from where its sources say so: an identifier rule
naming both (``IdentifierRuleSet.collected_from``), and a ``collected_from`` line naming the
donor (#559), each read as the main identifier. Sources naming different donors give none, and
the sample is counted with each donor and who named it. A donor record is written for every donor
the evidence names, every donor a sample's sources name (linked or in conflict), every identifier a
``same_donor_as`` line about a recognised donor names (joined or not; a line whose own identifier no
rule recognises is counted and read no further), and every donor a donor's ``mother`` or ``father``
points to, so a join from a file to its donors, or from a donor to its parents, finds a record for each.

Nothing here reads or writes a file record: a file reaches its donors through its
``samples`` (epic #692, decision 5).
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import code_rules
from .edges import distinct
from .entity_evidence import entries, read_entity_envelope, read_outcomes
from .models import (
    ANATOMICAL_SITE,
    COLLECTED_FROM,
    CONFLICT,
    DONOR_SLOTS,
    FAMILY_FIELDS,
    FAMILY_ID,
    IDENTITY_LINK_FIELDS,
    JOIN_KEY_ENTITY_IDENTIFIER,
    KIND_OF_ENTITY_FIELD,
    KIND_OF_SLOT,
    PARENT_FIELDS,
    REPOSITORY_ID_FIELDS,
    REPOSITORY_IDS,
    SAME_DONOR_AS,
    SAMPLE_SLOTS,
    SOURCE_IDENTIFIER_RULE,
    SOURCE_PUBLISHED_VALUE,
    SYNONYMS,
    UNKNOWN_PARENT,
    UNKNOWN_SITE,
    UNTRANSLATED_SLOTS,
)
from .output_utils import relative_to
from .reconcile_lineage import applies
from .reconcile_samples import attributions
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

# Every field an entity line may name, for :func:`gather`'s read of each file; its ``same_donor_as``
# lines are read first, on their own (:func:`_main_identifiers`), so every later line can be read
# as its donor's main identifier.
_ENTITY_FIELDS = (*DONOR_SLOTS, *SAMPLE_SLOTS, *REPOSITORY_ID_FIELDS, *IDENTITY_LINK_FIELDS)
# The entity rule a slot taken as written cites.
_AS_WRITTEN_RULES = {slot: rule.id for rule in code_rules.ENTITY_RULES for slot in rule.sets}
# The report's keys for whether a file's samples reach a donor (#718): per dataset, and the samples that do not.
DONOR_REACH = "donor_reach"
NO_DONOR = "no_donor"
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
    ``links`` holds the identity links (:class:`IdentityLinks`, #559). ``outcomes`` is what each importer writing
    one said of a sample it linked or left out (``entity_evidence.OUTCOMES_FILE``, #718), by the sample's identifier.
    """

    slots: dict[Identifier, dict[str, SlotEvidence]]
    sample_slots: dict[Identifier, dict[str, SlotEvidence]]
    named_in: dict[tuple[str, str], set[Identifier]]
    files: list[dict]
    unrecognised: dict[tuple[str | None, str | None], Counter]
    repository_ids: dict[tuple[EntityKind, Identifier], set[RepositoryId]]
    no_value_lines: dict[str, Counter]
    unrecognised_parents: dict[tuple[str | None, str | None], Counter]
    links: IdentityLinks
    outcomes: dict[Identifier, list[dict]] = field(default_factory=dict)


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


@dataclass
class IdentityLinks:
    """What the ``collected_from`` and ``same_donor_as`` lines said (#559).

    ``synonyms`` holds, per main identifier, each synonym joined to it and the attributions naming it
    (:func:`_main_identifiers`); ``unjoined`` each synonym joined to none, and why. ``collected_from`` holds, per
    sample, each line's donor, as its main identifier, and attribution. ``unrecognised`` counts, per dataset and
    table, a link's value no rule recognises as a donor.
    """

    synonyms: dict[Identifier, dict[Identifier, tuple[dict, ...]]]
    unjoined: list[dict]
    unrecognised: dict[tuple[str | None, str | None], Counter]
    collected_from: dict[Identifier, list[tuple[Identifier, dict]]] = field(default_factory=lambda: defaultdict(list))

    def __post_init__(self) -> None:
        self._main_of = {synonym: main for main, joined in self.synonyms.items() for synonym in joined}

    def main(self, donor: Identifier) -> Identifier:
        """``donor``'s main identifier: the one it is a synonym of, or itself."""
        return self._main_of.get(donor, donor)

    @property
    def joined(self) -> int:
        """How many synonyms are joined to a main identifier."""
        return len(self._main_of)


def _link_attribution(source_type: str, rule_id: str, entry: EvidenceEntry) -> dict:
    """The attribution an identity link's line gives: its source type, the identifier rule that recognised the donor
    it names, and its source."""
    return attributions(source_type, (rule_id,), entry.source)[0]


def _main_identifiers(paths: Iterable[Path], rules: IdentifierRuleSet) -> IdentityLinks:
    """Every ``same_donor_as`` line of ``paths``: which donor identifier is whose synonym (#559).

    A line about the donor it names (the synonym) names an identifier for the same donor, both recognised
    as donors in the line's dataset. The links are followed to the end of their chain, transitively
    (``S_Spanish-2`` → ``HG01504`` → ``NA99999`` puts both on ``NA99999``), and each synonym keeps the
    attributions of its own step. A synonym whose chain reaches an identifier naming more than one other, or comes
    back on itself, joins none and is listed in ``unjoined`` with why. A line naming its own identifier says
    nothing and is passed over. A line whose synonym no rule recognises is left for :func:`gather` to count;
    one whose named identifier none recognises is counted here.
    """
    named: dict[Identifier, dict[Identifier, list[dict]]] = defaultdict(lambda: defaultdict(list))
    unrecognised_links: dict[tuple[str | None, str | None], Counter] = defaultdict(Counter)
    for path in paths:
        envelope = read_entity_envelope(path)
        dataset = envelope.target.dataset
        for entry in entries(path, envelope, (SAME_DONOR_AS,)):
            synonym = rules.recognise(entry.target_key_value, dataset, DONOR)
            if synonym is None:
                continue
            main = rules.recognise(entry.raw_value, dataset, DONOR)
            if main is None:
                unrecognised_links[(dataset, envelope.source.table)][entry.raw_value] += 1
                continue
            if main.identifier == synonym.identifier:
                continue
            named[synonym.identifier][main.identifier].append(
                _link_attribution(envelope.source_type, main.rule_id, entry)
            )
    synonyms: dict[Identifier, dict[Identifier, tuple[dict, ...]]] = defaultdict(dict)
    unjoined = []
    for synonym in sorted(named, key=identifier_order):
        main, reason = _end_of_chain(synonym, named)
        if main is None:
            unjoined.append({"identifier": synonym.to_dict(), "reason": reason})
            continue
        (said,) = named[synonym].values()  # one, or the chain would have branched here
        synonyms[main][synonym] = distinct(said)
    return IdentityLinks(synonyms, unjoined, unrecognised_links)


def _end_of_chain(
    start: Identifier, named: dict[Identifier, dict[Identifier, list[dict]]]
) -> tuple[Identifier | None, str]:
    """The identifier ``start``'s chain of ``same_donor_as`` links ends at, or None and why."""
    seen = [start]
    current = start
    while current in named:
        nexts = named[current]
        if len(nexts) > 1:
            return None, f"its chain reaches {current.namespace}:{current.id}, which names {len(nexts)} identifiers"
        (current,) = nexts
        if current in seen:
            return None, "its chain comes back on itself"
        seen.append(current)
    return current, ""


def gather(paths: Iterable[Path], entity_root: Path, table: ValueMap, rules: IdentifierRuleSet) -> EntityEvidence:
    """Every line of ``paths`` (:func:`select_entity_evidence`), recognised, and translated into its donor's or
    sample's slots, read as an untranslated slot's (:func:`_untranslated_claim`: a donor's family, a sample's
    site), or listed among its donor's or sample's repository identifiers.

    Reads every line, so a malformed file or line, an identifier two rules match, a family line
    in a published table's file, a sample's slot in any other file, or a repository identifier that is empty or more than one line,
    in a file other than a published table's, or tying to two records raises here: reconcile calls this before it
    writes anything. A translated claim cites its value-map row, a parent's the identifier rule
    that recognised the parent, and a family id's or a site's its entity rule (``code_rules.ENTITY_RULES``); each carries
    the line's source and raw value, joined by ``entity_identifier``. A repository identifier is one record's by its kind,
    repository and id: the same one in two datasets ties to one record, or raises.

    An identity link (#559) may come from any kind of entity file; only the SGDP importer writes one today.
    A donor is read as its main identifier wherever a line names it (:func:`_main_identifiers`): the
    donor a line is about, a parent, a ``collected_from`` line's donor, and a repository identifier's donor. A
    claim made by a line keyed by a synonym is not an exact match, as one joined through a rewritten
    identifier is not.
    """
    paths = list(paths)  # read twice: the main identifiers first
    links = _main_identifiers(paths, rules)
    outcomes: dict[Identifier, list[dict]] = defaultdict(list)
    for (dataset, sample), said in read_outcomes(paths).items():
        # A sample no rule recognises is in no record, so nothing asks why it has no donor.
        if (found := rules.recognise(sample, dataset, SAMPLE)) is not None:
            outcomes[found.identifier].extend(said)
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
            if entry.field in SAMPLE_SLOTS and envelope.source_type != SOURCE_PUBLISHED_VALUE:
                raise ValueError(
                    f"{relative_to(path, entity_root)}: carries {entry.field} in a {envelope.source_type} file; a "
                    "sample's slots are read only from the repository's own record of it (#699)"
                )
            if alias_kind is not None and _ONE_LINE.fullmatch(entry.raw_value) is None:
                raise ValueError(
                    f"{relative_to(path, entity_root)}: {entry.field} {entry.raw_value!r} for "
                    f"{entry.target_key_value!r} is not an identifier: empty, or more than one line"
                )
            kind = KIND_OF_ENTITY_FIELD[entry.field]  # whose identifier the line is keyed by
            got = rules.recognise(entry.target_key_value, dataset, kind)
            if got is None:
                misses += 1
                unrecognised[(dataset, envelope.source.table)][entry.target_key_value] += 1
                continue
            ident = links.main(got.identifier) if kind == DONOR else got.identifier
            where = (dataset, envelope.source.table)
            if entry.field in IDENTITY_LINK_FIELDS:
                # The donor or sample a link names has a record, whether or not the link joins it to another.
                (sample_slots if kind == SAMPLE else slots)[ident]
            if entry.field == SAME_DONOR_AS:
                named = rules.recognise(entry.raw_value, dataset, DONOR)
                if named is not None:
                    slots[links.main(named.identifier)]  # the identifier it names has a record, joined or not
                continue  # the link itself is read by _main_identifiers
            if entry.field == COLLECTED_FROM:
                donor = rules.recognise(entry.raw_value, dataset, DONOR)
                if donor is None:
                    links.unrecognised[where][entry.raw_value] += 1
                    continue
                attribution = _link_attribution(envelope.source_type, donor.rule_id, entry)
                links.collected_from[ident].append((links.main(donor.identifier), attribution))
                continue
            if alias_kind is not None:
                alias = RepositoryId(
                    envelope.source.repository, str(dataset), str(envelope.source.table), entry.raw_value
                )
                earlier, earlier_path = tied.setdefault((kind, *alias.key), (ident, path))
                if earlier != ident:
                    raise ValueError(
                        f"{relative_to(path, entity_root)}: {alias.repository} {kind} {alias.id!r} ties to "
                        f"{ident.to_dict()} here and to {earlier.to_dict()} on an earlier line of "
                        f"{relative_to(earlier_path, entity_root)}; a repository's identifier names one record, "
                        "and which is not chosen"
                    )
                repository_ids[(kind, ident)].add(alias)
                continue
            # Not where a rule rewrote it (GM19908 -> NA19908), nor where it is a synonym of the record's identifier.
            exact = ident.id == entry.target_key_value and ident == got.identifier
            # The donor or sample the line names counts toward its dataset's slot, whatever the line's value gives.
            named_in[(str(dataset), entry.field)].add(ident)
            # A donor or sample a line names has a record, whatever the line's value gives.
            record_slots = (sample_slots if kind == SAMPLE else slots)[ident]
            if entry.field not in UNTRANSLATED_SLOTS:
                translate(record_slots, entry, envelope.source_type, JOIN_KEY_ENTITY_IDENTIFIER, table, exact)
                continue
            if (label := _names_no_value(entry)) is not None:
                no_value_lines[label][where] += 1
                continue
            claim = _untranslated_claim(entry, envelope.source_type, dataset, rules, exact, links)
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
        links=links,
        outcomes=dict(outcomes),
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
    entry: EvidenceEntry,
    source_type: str,
    dataset: str | None,
    rules: IdentifierRuleSet,
    exact: bool,
    links: IdentityLinks,
) -> dict | None:
    """The claim one untranslated line makes (``models.UNTRANSLATED_SLOTS``); None for a parent no rule recognises.

    A parent is recognised as a donor in the line's dataset, and its claim declares the parent's
    identifier, read as its main identifier (:meth:`IdentityLinks.main`, #559), and cites the rule that recognised it.
    A family id or a site is the answer as written, citing its entity rule.
    """
    if entry.field in PARENT_FIELDS:
        recognised = rules.recognise(entry.raw_value, dataset, DONOR)
        if recognised is None:
            return None
        rule_id, value = recognised.rule_id, links.main(recognised.identifier).to_dict()
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


def _collected_from(
    sample: Identifier, rules: IdentifierRuleSet, evidence: EntityEvidence
) -> dict[Identifier, list[dict]]:
    """Every donor ``sample``'s sources say it was collected from, each as its main identifier, with the sources naming
    it, the identifier rule first (#559).

    The sources are an identifier rule naming both a sample and a donor (``IdentifierRuleSet.collected_from``)
    and each ``collected_from`` line about the sample (:func:`gather`). One donor is the sample's; two are a
    conflict, and the caller links none.
    """
    named: list[tuple[Identifier, dict]] = []
    found = rules.collected_from(sample)
    if found is not None:
        named.append(
            (evidence.links.main(found.identifier), {"source_type": SOURCE_IDENTIFIER_RULE, "rule_id": found.rule_id})
        )
    named.extend(evidence.links.collected_from.get(sample, []))
    by_donor: dict[Identifier, list[dict]] = {}
    for donor, attribution in named:
        by_donor.setdefault(donor, []).append(attribution)
    return {donor: list(distinct(attributions)) for donor, attributions in by_donor.items()}


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
    files_by_list: Counter | None = None,
) -> EntityResult:
    """Settle every donor ``evidence`` names and every sample ``sample_lists`` hold, a repository identifier ties
    to or ``evidence`` names, link each sample to its donor, list each record's repository identifiers, and
    count what was done.

    ``evidence`` is :func:`gather`'s; ``sample_lists`` are the run's reconciled ``SampleList``
    dicts. A donor a sample's ``collected_from`` points to, or a donor's ``mother`` or ``father``
    claim names, gets a record, evidence or none; so does a main identifier with a synonym (#559).
    A sample's donor is :func:`_collected_from`'s. ``files_by_list`` counts the reconciled files per (dataset,
    ``list_id``) of the samples they settled to, for :func:`_donor_reach`.
    """
    members = {entry["list_id"]: members_of(entry) for entry in sample_lists}
    slots, named_in, files, unrecognised = evidence.slots, evidence.named_in, evidence.files, evidence.unrecognised
    repository_ids = evidence.repository_ids
    named_by_files: set[Identifier] = set().union(*members.values())
    tied_samples = {ident for kind, ident in repository_ids if kind == SAMPLE}
    sample_slots = evidence.sample_slots
    sample_records, linked, conflicts = [], Counter(), []
    with_donor: set[Identifier] = set()
    linked_by: Counter = Counter()
    collected_conflicts: list[dict] = []
    sample_settled: dict[Identifier, dict[str, str]] = {}
    unreviewed: dict[EntityKind, Counter] = {DONOR: Counter(), SAMPLE: Counter()}
    links = evidence.links
    samples = named_by_files | tied_samples | set(sample_slots)  # gather gives every link's sample a slot entry
    for sample in sorted(samples, key=identifier_order):
        record: dict = {"identifier": sample.to_dict()}
        by_donor = _collected_from(sample, rules, evidence)
        for donor in by_donor:
            slots[donor]  # a donor a source names for a sample has a record, evidence or none, link or conflict
        if len(by_donor) == 1:
            ((donor, named_by),) = by_donor.items()
            record[COLLECTED_FROM] = {"donor": donor.to_dict(), "named_by": named_by}
            with_donor.add(sample)
            linked[sample.namespace] += 1
            linked_by.update({a["source_type"] for a in named_by})
        elif by_donor:
            collected_conflicts.append(
                {
                    "identifier": sample.to_dict(),
                    "donors": [
                        {"donor": d.to_dict(), "named_by": by_donor[d]} for d in sorted(by_donor, key=identifier_order)
                    ],
                }
            )
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
        if synonyms := links.synonyms.get(donor):
            record[SYNONYMS] = [
                {"identifier": synonym.to_dict(), "named_by": list(synonyms[synonym])}
                for synonym in sorted(synonyms, key=identifier_order)
            ]
        donors.append(record)

    # Per dataset and slot: the donors (or samples) the dataset's lines name, each counted at its overall
    # settled status, so a dataset agreeing with a conflicted record still shows the conflict.
    by_dataset: dict[str, dict[str, dict]] = defaultdict(dict)
    for (dataset, slot), named in named_in.items():
        noun, statuses = ("samples", sample_settled) if KIND_OF_SLOT[slot] == SAMPLE else ("donors", settled)
        by_dataset[dataset][slot] = {noun: len(named), **Counter(statuses[r][slot] for r in named)}
    reach, no_donor = _donor_reach(files_by_list or Counter(), members, with_donor, evidence.outcomes)
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
        SYNONYMS: {
            "records": len(links.synonyms),
            "synonyms": links.joined,
            "by_namespace": dict(
                sorted(Counter(main.namespace for main, by_main in links.synonyms.items() for _ in by_main).items())
            ),
            "unjoined": links.unjoined,
        },
        "unrecognised_links": _per_table(links.unrecognised),
        "samples": {
            "total": len(sample_records),
            "named_by_files": len(named_by_files),
            "collected_from": dict(linked),
            "collected_from_by_source": dict(sorted(linked_by.items())),
            "collected_from_conflicts": collected_conflicts,
            "statuses": {slot: dict(Counter(s[slot] for s in sample_settled.values())) for slot in SAMPLE_SLOTS},
            UNKNOWN_SITE_LINES: _lines_per_table(evidence.no_value_lines.get(UNKNOWN_SITE_LINES, Counter())),
            "unreviewed": {slot: n for slot, n in unreviewed[SAMPLE].items() if n},
            NO_DONOR: no_donor,
        },
        DONOR_REACH: reach,
        REPOSITORY_IDS: {kind: _repository_id_counts(repository_ids, kind) for kind in (DONOR, SAMPLE)},
    }
    return EntityResult(donors, sample_records, report)


def _donor_reach(
    files_by_list: Counter,
    members: dict[str, frozenset[Identifier]],
    with_donor: set[Identifier],
    outcomes: dict[Identifier, list[dict]],
) -> tuple[dict, dict]:
    """Per dataset, how many files whose samples settled have a donor for every sample, and how many do not, by
    whether they name one sample or several (``donor_reach``); and each sample those files name with no donor, with
    what each importer said of it where one did (``no_donor``, #718)."""
    reach: dict[str, Counter] = defaultdict(Counter)
    missing: dict[str, set[Identifier]] = defaultdict(set)
    for (dataset, list_id), n in sorted(files_by_list.items()):
        named = members[list_id]  # every list a file settled to is among the run's lists
        lacking = named - with_donor
        counts = reach[dataset]
        counts["files_with_samples"] += n
        if not lacking:
            counts["every_sample_has_a_donor"] += n
            continue
        counts["one_sample_without_donor" if len(named) == 1 else "several_samples_some_without_donor"] += n
        missing[dataset] |= lacking
    no_donor = {
        dataset: [
            {"identifier": s.to_dict(), **({"outcomes": outcomes[s]} if s in outcomes else {})}
            for s in sorted(missing[dataset], key=identifier_order)
        ]
        for dataset in sorted(missing)
    }
    return {dataset: dict(reach[dataset]) for dataset in sorted(reach)}, no_donor


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
