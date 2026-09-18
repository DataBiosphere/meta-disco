"""The producers of a classification run, and the one rule that routes a file to one.

A *producer* writes one ``*_classifications.json`` file, holding one row per file it
claims. There are eleven: the seven header/content types, which share
``ClassifyPipeline``, and the four standalone scripts. All eleven are declared here, and
this is where the question every one of them asks — "is this file mine?" — is answered.

Routing was four predicates in four places, and the producer list was three lists that
could drift apart; #445 and #151 are what those cost. CLAUDE.md tells that story.
"""

from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from .file_types import FILE_TYPE_REGISTRY, FileTypeConfig

# Index extension -> parent extension mapping.
# List specific compound extensions to avoid false candidates from bare .gz.
#
# Lives here rather than in the producer's script because its keys are what the index
# producer *claims* — the registry entry's `extensions` reads them off this map, so what
# the producer routes on and what it inherits from cannot drift apart.
INDEX_TO_PARENT = {
    ".bai": [".bam"],
    ".tbi": [".vcf.gz", ".bed.gz", ".txt.gz", ".tsv.gz", ".gff.gz", ".gtf.gz"],
    ".csi": [".vcf.gz", ".bcf", ".bed.gz"],  # CSI can index BED files too
    ".crai": [".cram"],
    ".pbi": [".bam"],
    # `.fai` and `.idx` are in the `index_file` rule's extension list and were missing
    # here, so those files never reached this producer at all. Declaring them lets the
    # four dimensions a parent supplies be inherited rather than left to the catch-all,
    # which sees only the extension.
    ".fai": [".fa.gz", ".fasta", ".fa"],
    ".idx": [".vcf"],
}


@dataclass(frozen=True)
class Producer:
    """One writer of one ``*_classifications.json`` file.

    ``extensions`` is what this producer claims; ``()`` means it claims nothing by
    extension — only the catch-all is declared that way.

    ``phase`` is when it runs: 1 in the parallel pool, 2 for the index producer, which
    reads Phase 1's output to inherit from a parent, 3 for the catch-all, which must see
    every earlier output to know what is left.

    ``fetches_headers`` marks the producers that read file content, and so are the only
    ones handed ``--evidence-base`` and ``--workers``.
    """

    name: str
    script: str
    output: str
    phase: int
    extensions: tuple[str, ...] = ()
    fetches_headers: bool = False

    def claim(self, record: dict) -> str | None:
        """The extension this producer claims ``record`` by, or None if it is not theirs.

        One route per record, so the extension a caller reports or looks up is the one
        that routed the file rather than a second derivation that could disagree with it.
        """
        routed = route(record, _routing_peers(self))
        return routed.extension if routed is not None and routed.producer is self else None

    def claims(self, record: dict) -> bool:
        """Whether this producer owns ``record`` — the public "does this type take this file".

        The catch-all answers ``False`` for everything, including the records it writes:
        what it takes is decided by what the other ten did not write.
        """
        return self.claim(record) is not None


def _header_producer(config: FileTypeConfig) -> Producer:
    """The registry entry for one header/content type.

    All seven are invoked as ``classify_headers.py --type <name>`` and write
    ``<name>_classifications.json`` — the name that script derives from ``--type``.
    Derived here rather than spelled per type, so registering a type is enough to get it
    produced (#151).
    """
    return Producer(
        name=config.name,
        script="classify_headers.py",
        output=f"{config.name}_classifications.json",
        phase=1,
        extensions=tuple(config.extensions),
        fetches_headers=True,
    )


PRODUCERS: dict[str, Producer] = {
    **{name: _header_producer(config) for name, config in FILE_TYPE_REGISTRY.items()},
    "images": Producer(
        name="images",
        script="classify_images.py",
        output="image_classifications.json",
        phase=1,
        extensions=(".jpg", ".png", ".svs", ".tiff"),
    ),
    # ONT raw signal (.fast5, .pod5) and PLINK2 genotypes (.pgen, .psam, .pvar).
    "auxiliary": Producer(
        name="auxiliary",
        script="classify_auxiliary_genomic.py",
        output="auxiliary_classifications.json",
        phase=1,
        extensions=(".fast5", ".pgen", ".pod5", ".psam", ".pvar"),
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
    """Who owns a record, and the extension they own it by."""

    producer: Producer
    extension: str


def _routing_peers(producer: Producer) -> Collection[Producer]:
    """Every producer that competes with ``producer`` for a record.

    The registry itself, as the live view — so an entry swapped in is routed against, and
    nothing is copied per record.

    A ``Producer`` the registry does not hold under its name goes *first*, ahead of the
    registry and of any namesake it replaces. :func:`_claiming` takes the first producer
    that matches, so a detached producer placed last would lose every record whose
    extension a registered producer also claims — a ``ClassifyPipeline`` over a
    not-yet-registered ``FileTypeConfig`` would write an empty output and report nothing
    wrong. Standing in means winning, which is only ever a test's or a work-in-progress
    type's business: every config in a real run is a registered one.
    """
    if PRODUCERS.get(producer.name) is producer:
        return PRODUCERS.values()
    return [producer] + [peer for peer in PRODUCERS.values() if peer.name != producer.name]


def producer_for(config: FileTypeConfig) -> Producer:
    """The producer that runs ``config`` — the registry's entry, or one standing in for it.

    A config the registry does not hold, or holds under different extensions, gets a
    detached entry, so a pipeline over it routes on the extensions it was actually given.
    """
    registered = PRODUCERS.get(config.name)
    if registered is not None and registered.extensions == tuple(config.extensions):
        return registered
    return _header_producer(config)


def _claiming(value: str, producers: Collection[Producer]) -> Route | None:
    """The producer whose declared extension is the longest suffix of ``value``, or None.

    Returning at the first producer that matches is not a precedence rule:
    :func:`validate_registry` refuses a registry where one producer's extension is a
    suffix of another's, so two producers cannot both match. The inner scan picks the most
    specific of a *single* producer's own extensions — ``.g.vcf.gz`` over ``.vcf.gz``.
    """
    for producer in producers:
        longest = ""
        for extension in producer.extensions:
            if value.endswith(extension) and len(extension) > len(longest):
                longest = extension
        if longest:
            return Route(producer, longest)
    return None


def route(record: dict, producers: Collection[Producer] | None = None) -> Route | None:
    """The one producer that owns ``record`` and the extension it owns it by, or None.

    The file *name* decides; ``file_format`` is consulted only when no producer claims the
    name. Matching the two independently is what let one file answer two producers with no
    shared extension at all (#445): a source may declare the *core* extension for an
    archive (``.fast5`` for ``x.fast5.tar``), and the name is the half it cannot be wrong
    about.

    That ordering is also the whole of the container rule (#242) — ``x.fast5.tar`` is the
    tar type's because ``.tar`` is — so no producer has to know an archive is an archive
    first. A ``.tar.xz`` is claimed by no producer on its name, so the format fallback
    leaves it with the producer claiming its core extension.

    Both fields are case-folded, as every other reader of an extension is. Non-string
    values are coerced rather than refused: routing runs before validation, so a drifted
    ``file_format`` must not raise before the record can be written as a
    ``validation_failed`` row (#155/#161).

    ``None`` is the catch-all's claim — every record the other ten did not write. Whether
    a record is *worth* classifying is a separate question with its own home (the #376
    exclusion at load), so no eligibility marker is read here: this answers only who owns
    the file.

    ``producers`` defaults to the whole registry; only :meth:`Producer.claim` passes it,
    for a producer standing in for an entry.
    """
    if not isinstance(record, dict):
        return None
    if producers is None:
        producers = PRODUCERS.values()
    routed = _claiming(str(record.get("file_name") or "").lower(), producers)
    if routed is not None:
        return routed
    return _claiming(str(record.get("file_format") or "").lower(), producers)


def producer_of(record: dict) -> Producer | None:
    """The one producer that owns ``record``, or None for the catch-all (:func:`route`)."""
    routed = route(record)
    return routed.producer if routed else None


def classification_files() -> list[str]:
    """Every file a run's producers write, in registry order.

    ``output_utils.CLASSIFICATION_FILES`` is this list, and the report generators read
    exactly it — an output missing from it appears in no report (#151).
    """
    return [producer.output for producer in PRODUCERS.values()]


def output_paths(run_dir: Path, phase: int | None = None) -> list[Path]:
    """Where each producer's output lands in ``run_dir`` — all of them, or one phase's."""
    producers = PRODUCERS.values() if phase is None else producers_in_phase(phase)
    return [run_dir / producer.output for producer in producers]


def _overlapping_claims() -> Iterator[str]:
    """Describe each pair of producers where one's extension is a suffix of another's."""
    claims = [(producer.name, extension) for producer in PRODUCERS.values() for extension in producer.extensions]
    for index, (one_name, one) in enumerate(claims):
        for other_name, other in claims[index + 1 :]:
            if one_name != other_name and (one.endswith(other) or other.endswith(one)):
                yield f"{one_name} {one} / {other_name} {other}"


def validate_registry() -> None:
    """Raise if two producers claim overlapping extensions.

    A suffix relation between two producers' extensions would make :func:`route` arbitrate
    between them on one name, and whichever it picked, the other's files would be a
    population that quietly changed hands. Refusing the registry keeps that decision at
    declaration time, where a person can make it.

    Checked at import, so every entry point inherits it; the run calls it again as a
    preflight, which also catches a registry something has since mutated.
    """
    overlaps = list(_overlapping_claims())
    if overlaps:
        raise ValueError(
            "Producers claim overlapping extensions, so no rule about a file name can "
            f"say which of them owns a file: {overlaps}. One of them must give the "
            "extension up."
        )


validate_registry()
