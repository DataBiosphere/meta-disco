"""A PLINK 2 fileset's sample table (#751): one ``plink2 --make-pgen --out AFR.19`` writes ``AFR.19.pgen``,
``.pvar``, ``.psam`` and ``.log`` side by side, and the ``.psam``'s rows are the fileset's samples.
:func:`parse_psam` reads them; :func:`filesets` pairs each ``.psam`` with its fileset, by folder and stem,
for reconcile to pass them on (``reconcile_samples.SampleReport.pair``).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from . import edges
from .record_keys import RecordKey, input_key_value
from .records import dataset_of, folder_of

SAMPLE_TABLE_EXTENSION = ".psam"
# The other files one `--make-pgen` writes beside its `.psam`.
MEMBER_EXTENSIONS = (".pgen", ".pvar", ".log")

# Why a `.psam`'s rows were not read (``PsamRows.unread``).
NO_HEADER = "no #FID or #IID header line"
SHORT_ROW = "a row with no IID column"
HASH_ROW = "a # line after the header"

# What became of a `.psam`'s fileset, per dataset (:class:`Filesets`.counts).
SAMPLE_TABLES = "sample_tables"  # `.psam` files paired with at least one member
MEMBERS = "members"  # members paired
NO_PATH = "no_path"  # a `.psam` whose input record has no storage path, so no folder to pair in
SEVERAL_CARRY = "several_carry"  # a member name two files of the `.psam`'s folder carry, paired with neither
UNPAIRED = "unpaired"  # a `.psam` with a path that paired no member


@dataclass(frozen=True)
class PsamRows:
    """A ``.psam``'s IIDs in row order, or None with why they were not read (``unread``)."""

    iids: tuple[str, ...] | None
    unread: str | None = None


def parse_psam(text: str) -> PsamRows:
    """The IIDs a PLINK 2 ``.psam``'s rows give.

    Lines starting ``##`` before the header are skipped. The header is the first
    other line, and must start ``#FID`` or ``#IID`` and name an ``IID`` column; each later non-blank line
    is a sample, its IID in that column. Columns are split on whitespace. A file with no such header (a
    headerless ``.psam``, read by PLINK as ``.fam`` columns), a row too short to hold an IID, or a line
    starting ``#`` after the header gives none, with why: a table read in part names part of its samples.
    """
    lines = (line for line in text.splitlines() if line.strip())
    header = next((line for line in lines if not line.startswith("##")), "").split()
    if not header or header[0] not in ("#FID", "#IID"):
        return PsamRows(None, NO_HEADER)
    names = [header[0][1:], *header[1:]]
    if "IID" not in names:
        return PsamRows(None, NO_HEADER)
    column = names.index("IID")
    iids = []
    for line in lines:
        if line.startswith("#"):
            return PsamRows(None, HASH_ROW)
        fields = line.split()
        if len(fields) <= column:
            return PsamRows(None, SHORT_ROW)
        iids.append(fields[column])
    return PsamRows(tuple(iids))


@dataclass
class Filesets:
    """:func:`filesets`' result: each ``.psam`` paired with members, and per dataset title what became of the pairing."""

    entries: list[dict] = field(default_factory=list)
    counts: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))


def filesets(records: Sequence[dict], key: RecordKey) -> Filesets:
    """Each ``.psam`` among ``records`` with the record keys of the files of its fileset.

    A member is a file of the ``.psam``'s dataset in its folder (``records.folder_of``) named its stem
    with one of :data:`MEMBER_EXTENSIONS`, up to case. The folder is required, unlike ``edges.matches``:
    PRIMED reuses ``AFR.19`` in four folders. A ``.psam`` with no path or no member, and a member name
    two files in the folder carry, pair nothing and are counted. Only bare names pair: a ``.psam.gz`` or
    ``.pvar.zst`` does not (the corpus has none). Entries are ``{"sample_table", "members"}`` by record key,
    in key order. Raises ``ValueError`` (``record_keys.input_key_value``) on a ``.psam``'s or member's
    unusable key.
    """
    purpose = "pair a PLINK fileset's files with its sample table"
    index = edges.parent_index(records, key, lambda n: n.lower().endswith(MEMBER_EXTENSIONS), purpose)
    result = Filesets()
    for table in records:
        name = table.get("file_name")
        if not isinstance(name, str) or not name.lower().endswith(SAMPLE_TABLE_EXTENSION):
            continue
        sample_table = input_key_value(table, key, purpose)
        dataset = dataset_of(table)
        # Counted by title, as a producer counts its outcomes ("" for a record with none).
        title = str(table.get("dataset_title") or "")
        folder = folder_of(table)
        if folder is None:
            result.counts[title][NO_PATH] += 1
            continue
        stem = name[: -len(SAMPLE_TABLE_EXTENSION)]
        members = []
        for extension in MEMBER_EXTENSIONS:
            beside = [r for r in index.get((dataset, (stem + extension).lower()), []) if r.get(edges.FOLDER) == folder]
            if len(beside) == 1:
                members.append(beside[0][key.input_field])
            elif beside:
                result.counts[title][SEVERAL_CARRY] += 1
        if members:
            result.counts[title][SAMPLE_TABLES] += 1
            result.counts[title][MEMBERS] += len(members)
            result.entries.append({"sample_table": sample_table, "members": members})
        else:
            result.counts[title][UNPAIRED] += 1
    result.entries.sort(key=lambda e: e["sample_table"])
    return result
