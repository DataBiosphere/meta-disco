"""The producers of a classification run, and the one rule that routes a file to one.

A *producer* is one thing that writes one ``*_classifications.json`` file, holding one
row per file it claims. There are eleven: the seven header/content types, which share
``ClassifyPipeline`` and differ only in the fetcher and classifier they plug in, and the
four standalone scripts. This module is where all eleven are declared, and where the
question every one of them asks — "is this file mine?" — is answered.

Who owns a file used to be decided independently in four places, and the four were not
the same rule (``ClassifyPipeline._filter_records`` matched a suffix of either
``file_format`` or ``file_name``; the three standalone scripts matched the format by
equality and the name by suffix, two of them without case-folding). Overlap was
therefore possible *by construction* and detectable only after the fact — #445 is what
that cost: ``.fast5.tar`` was claimed by both the auxiliary producer and the tar type,
115 files got two rows each, and no identifier in the run's output was unique. One
predicate makes a file have exactly one owner because one function said so (#449).

Who the producers *are* was three hand-maintained lists — ``NON_HEADER_JOBS``,
``output_utils.CLASSIFICATION_FILES`` and ``FILE_TYPE_REGISTRY`` — none authoritative
and only one derived from another. #151 is what happens when they drift: ``gfa`` was
added to the registry and to nothing else, so ``make classify`` never invoked it and
graph files fell through to the filename-only catch-all. :data:`PRODUCERS` is the one
list those three now read.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from .file_types import FILE_TYPE_REGISTRY, FileTypeConfig

# Extensions the image producer claims.
IMAGE_EXTENSIONS = frozenset({".svs", ".png", ".jpg", ".tiff"})

# Extensions the auxiliary-genomic producer claims: ONT raw signal and PLINK2 genotypes.
AUXILIARY_EXTENSIONS = frozenset({".fast5", ".pod5", ".pvar", ".psam", ".pgen"})

# Index extension -> parent extension mapping.
# List specific compound extensions to avoid false candidates from bare .gz.
#
# Lives here rather than in the producer's script because its keys are what the index
# producer *claims* — the registry's `extensions` for that entry reads them off this
# map, so what the producer routes on and what it inherits from cannot drift apart.
INDEX_TO_PARENT = {
    ".bai": [".bam"],
    ".tbi": [".vcf.gz", ".bed.gz", ".txt.gz", ".tsv.gz", ".gff.gz", ".gtf.gz"],
    ".csi": [".vcf.gz", ".bcf", ".bed.gz"],  # CSI can index BED files too
    ".crai": [".cram"],
    ".pbi": [".bam"],
    # `.fai` and `.idx` are in the `index_file` rule's extension list and were missing
    # here, so 477 `.fai` files never reached this producer at all. They are declared
    # so those files can *inherit*: every one of the 477 has a present, unambiguous
    # parent, so the four dimensions a parent supplies are answered rather than left
    # to the catch-all, which sees only the extension. (When the gap was found, the
    # catch-all's rule also stamped four `not_applicable` on them — the outcome #438
    # exists to prevent. #437 removed that, so today the cost of the gap is lost
    # inheritance rather than a wrong answer.)
    ".fai": [".fa.gz", ".fasta", ".fa"],
    ".idx": [".vcf"],
}


@dataclass(frozen=True)
class Producer:
    """One writer of one ``*_classifications.json`` file.

    ``extensions`` is what this producer claims; ``()`` means it claims nothing by
    extension. Exactly one producer is declared that way — the catch-all, which takes
    every record no other producer wrote a row for, so :func:`producer_of` returning
    ``None`` *is* its claim.

    ``phase`` is when it runs: 1 alongside the other Phase 1 producers, 2 for the index
    producer (which reads Phase 1's output to inherit a parent's classifications), 3 for
    the catch-all (which must see every earlier producer's output to know what is left).

    ``config`` is the header/content type this producer runs through ``ClassifyPipeline``,
    and is ``None`` for the four standalone scripts. When it is set, ``extensions`` is
    read off it, so a header type declares what it claims in exactly one place.
    """

    name: str
    script: str
    output: str
    phase: int
    extensions: tuple[str, ...] = ()
    config: FileTypeConfig | None = None

    @property
    def fetches_headers(self) -> bool:
        """Whether this producer reads file content, and so needs the evidence cache.

        The header jobs are the only ones handed ``--evidence-base`` and ``--workers``:
        the other four classify from the filename and fetch nothing.
        """
        return self.config is not None

    def claims(self, record: dict) -> bool:
        """Whether this producer owns ``record`` — the public "does this type take this file".

        Asks :func:`route`, so a producer cannot answer this differently from the way the
        run routes. The catch-all answers ``False`` for everything: what it takes is
        decided by what the other ten did not write, not by anything on the record.
        """
        routed = route(record, _routing_peers(self))
        return routed is not None and routed.producer is self


def _header_producer(config: FileTypeConfig) -> Producer:
    """The registry entry for one header/content type.

    All seven are invoked identically — ``classify_headers.py --type <name>`` — and write
    ``<name>_classifications.json``, which is the name ``classify_headers.py`` derives
    from ``--type``. Deriving both here rather than spelling them per type is what makes
    registering a type enough to get it produced (#151).
    """
    return Producer(
        name=config.name,
        script="classify_headers.py",
        output=f"{config.name}_classifications.json",
        phase=1,
        extensions=tuple(config.extensions),
        config=config,
    )


PRODUCERS: dict[str, Producer] = {
    **{name: _header_producer(config) for name, config in FILE_TYPE_REGISTRY.items()},
    "images": Producer(
        name="images",
        script="classify_images.py",
        output="image_classifications.json",
        phase=1,
        extensions=tuple(sorted(IMAGE_EXTENSIONS)),
    ),
    "auxiliary": Producer(
        name="auxiliary",
        script="classify_auxiliary_genomic.py",
        output="auxiliary_classifications.json",
        phase=1,
        extensions=tuple(sorted(AUXILIARY_EXTENSIONS)),
    ),
    "index": Producer(
        name="index",
        script="classify_index_files.py",
        output="index_classifications.json",
        phase=2,
        extensions=tuple(sorted(INDEX_TO_PARENT)),
    ),
    "remaining": Producer(
        name="remaining",
        script="classify_remaining_files.py",
        output="remaining_classifications.json",
        phase=3,
    ),
}


def producers_in_phase(phase: int) -> list[Producer]:
    """The producers that run in one phase, in registry order."""
    return [producer for producer in PRODUCERS.values() if producer.phase == phase]


class Route(NamedTuple):
    """Who owns a record, and the extension they own it by.

    The extension is what the producer matched on, which several producers report per
    extension (the image and auxiliary summaries) or look up (the index producer's
    parent map). Carried out of the one match rather than re-derived afterwards, so a
    producer's own stats cannot disagree with what routed the file.
    """

    producer: Producer
    extension: str


def _routing_peers(producer: Producer) -> list[Producer]:
    """Every producer that competes with ``producer`` for a record.

    The registry, normally. A ``Producer`` that is not the registry's own entry for its
    name stands in for that namesake instead of competing with it — which is what a
    ``ClassifyPipeline`` built on a modified ``FileTypeConfig`` needs (a stub fetcher, a
    disabled preflight), and what an unregistered config needs to route at all. Without
    the substitution such a producer would lose every record to the registered entry and
    silently classify nothing.
    """
    if PRODUCERS.get(producer.name) is producer:
        return list(PRODUCERS.values())
    return [peer for peer in PRODUCERS.values() if peer.name != producer.name] + [producer]


def producer_for(config: FileTypeConfig) -> Producer:
    """The producer that runs ``config`` — the registry's entry, or one standing in for it.

    A config the registry does not hold, or holds under different extensions, gets a
    detached entry so a ``ClassifyPipeline`` over it still routes (see
    :func:`_routing_peers`). Every config in a real run is the registered one.
    """
    registered = PRODUCERS.get(config.name)
    if registered is not None and registered.extensions == tuple(config.extensions):
        return registered
    return _header_producer(config)


def _claiming(value: str, producers: list[Producer]) -> Route | None:
    """The producer whose declared extension is the longest suffix of ``value``, or None.

    At most one producer can match at all: :func:`validate_registry` refuses a registry
    where one producer's extension is a suffix of another's, and two producers both
    matching one string would require exactly that. Length therefore arbitrates only
    *within* a producer, picking the most specific of its own extensions — ``.g.vcf.gz``
    over ``.vcf.gz`` — which is what its per-extension reporting wants.
    """
    best: Route | None = None
    for producer in producers:
        for extension in producer.extensions:
            if value.endswith(extension) and (best is None or len(extension) > len(best.extension)):
                best = Route(producer, extension)
    return best


def route(record: dict, producers: list[Producer] | None = None) -> Route | None:
    """The one producer that owns ``record`` and the extension it owns it by, or None.

    The file *name* decides. ``file_format`` is consulted only when no producer claims
    the name, so the two fields are no longer matched independently — the shape that let
    one file answer two producers with no shared extension at all, which is how 115
    ``.fast5.tar`` files got two rows each (#445). A source may declare the *core*
    extension for an archive (``.fast5`` for ``x.fast5.tar``); the name says what the
    file actually is, and the format is what a source can be wrong about.

    That ordering is also the whole of the container rule (#242): ``x.fast5.tar`` is the
    tar type's because ``.tar`` is the tar type's declared extension and ``.fast5`` is
    not a suffix of that name — no producer needs to know that an archive of fast5s is
    an archive first. A ``.tar.xz`` is claimed by no producer on its name, so the format
    fallback applies and it stays with the producer that claims its core extension.

    Both fields are case-folded, as every other reader of an extension is
    (``FileName.parse``). Non-string values are coerced rather than refused: routing runs
    before validation, so a drifted ``file_format`` must not raise here — the record is
    still to be written as a ``validation_failed`` row (#155/#161).

    ``None`` means no producer claims it by extension, which is the catch-all's claim:
    ``classify_remaining_files.py`` writes a row for every record the other ten did not.
    A record marked ``skip`` is routed nowhere for the same reason — the marker is
    honored uniformly here, where only ``ClassifyPipeline`` honored it before.

    ``producers`` is who competes for the record, defaulting to the whole registry. It
    is passed only by :meth:`Producer.claims`, for a producer standing in for a registry
    entry (see :func:`_routing_peers`).
    """
    if not isinstance(record, dict) or record.get("skip"):
        return None
    if producers is None:
        producers = list(PRODUCERS.values())
    name = str(record.get("file_name") or "").lower()
    file_format = str(record.get("file_format") or "").lower()
    return _claiming(name, producers) or _claiming(file_format, producers)


def producer_of(record: dict) -> Producer | None:
    """The one producer that owns ``record``, or None for the catch-all (:func:`route`)."""
    routed = route(record)
    return routed.producer if routed else None


def matched_extension(record: dict) -> str | None:
    """The extension ``record`` was routed by, or None if no producer claims it."""
    routed = route(record)
    return routed.extension if routed else None


def classification_files() -> list[str]:
    """Every file a run's producers write, in registry order.

    ``output_utils.CLASSIFICATION_FILES`` is this list. The coverage and validation
    report generators read exactly it, so an output missing from it is silently excluded
    from both reports — which is half of what #151 cost.
    """
    return [producer.output for producer in PRODUCERS.values()]


def _overlapping_claims() -> Iterator[str]:
    """Describe each pair of producers where one's extension is a suffix of another's."""
    claims = [(producer.name, extension) for producer in PRODUCERS.values() for extension in producer.extensions]
    for index, (one_name, one) in enumerate(claims):
        for other_name, other in claims[index + 1 :]:
            if one_name != other_name and (one.endswith(other) or other.endswith(one)):
                yield f"{one_name} {one} / {other_name} {other}"


def validate_registry() -> None:
    """Raise if two producers claim overlapping extensions.

    The preflight for a run, called before Phase 1 rather than checked afterwards: #445's
    own bug would otherwise burn a multi-hour run before saying anything.

    A suffix relation between two producers' extensions is the overlap that matters. It
    would make :func:`producer_of` arbitrate between two producers on one name, and
    whichever it picked, the other producer's files would be a population that quietly
    changed hands. Refusing the registry keeps that decision at declaration time, where
    a person can make it, and is what lets :func:`producer_of` be a rule about names
    rather than a precedence table.
    """
    overlaps = list(_overlapping_claims())
    if overlaps:
        raise ValueError(
            "Producers claim overlapping extensions, so no rule about a file name can "
            f"say which of them owns a file: {overlaps}. One of them must give the "
            "extension up."
        )


def output_paths(run_dir: Path, phase: int | None = None) -> list[Path]:
    """Where each producer's output lands in ``run_dir`` — all of them, or one phase's."""
    producers = PRODUCERS.values() if phase is None else producers_in_phase(phase)
    return [run_dir / producer.output for producer in producers]
