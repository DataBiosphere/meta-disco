"""Resolve the specific reference *build* a file was aligned to (issue #340).

This sits beside :mod:`validators.contig_lengths` and answers a narrower
question. That module answers "which reference *family*" — GRCh38, GRCh37, CHM13
— and answers it robustly, on purpose: it matches contig lengths with a 1000 bp
tolerance precisely so that minor build differences do not defeat detection. This
module answers "which *build*", and so it does the opposite: exact matching only,
and ``None`` rather than a nearest neighbour.

Nothing here changes the coarse value. It is produced entirely by
``contig_lengths``, and a build that cannot be resolved leaves it exactly as it
was and simply adds no detail. The interaction runs the other way only:
``header_classifier._reconcile_with_coarse_value`` withholds a derived family
that contradicts the coarse value (issue #345).

The key is (chr1, chrY)
-----------------------
Neither contig alone identifies a build, and the corpus shows why:

- **chr1 cannot separate CHM13 v1.1 from v2.0.** v2.0 is v1.1 plus an
  HG002-derived chrY, so their autosomes are identical and chr1 is 248,387,328
  in both.
- **chrY cannot separate GRCh38 from CHM13-with-grafted-GRCh38-chrY**, which
  share a chrY exactly because the latter borrowed it from the former.

The pair does **not** separate every build in the table. Some pairs are
indistinguishable by signature alone and rely on the declared name to resolve —
``TestKeyDiscrimination.NAME_DEPENDENT_PAIRS`` in ``tests/test_reference_builds.py``
is the authoritative list, pinned so it cannot widen unnoticed. They come in
three kinds: pairs involving ``GRCh38.p12``, which records no signature at all;
pairs among the CHM13 v1.0 variants, which share chr1 and where a row records no
chrY; and one genuine collision: CHM13 v1.1 and v2.0 share chr1 and v1.1 has no
chrY recorded, so a *nameless* file carrying only chr1 resolves to the family and
withholds the version. That is the honest outcome, not a failure, but it is the
ceiling of a two-contig key.

Two consequences worth stating plainly:

- This is a **fitted** result, not a general identity. Two builds differing only
  on, say, chr7 would collide, and this module would report the ambiguity rather
  than pick one — correct, but uninformative.
- The fitting is **checked**, not assumed:
  ``tests/test_reference_builds.py`` pins which pairs depend on the name, so a
  build added to the table that widens that set fails loudly instead of quietly
  collapsing two references — which is the failure this module exists to prevent,
  arriving by a different route.

#342's contig-set digest is the structural fix: it keys on the whole contig
composition rather than two chromosomes, and supersedes this key when it lands.

Signatures are sets, not values
-------------------------------
Each build in the table holds a *set* of observed lengths and checksums per
contig, and matching is membership. Two reasons, both observed:

- headers vary in completeness — a chromosome-subset BAM carries no chr1, and
  many carry no ``M5`` at all — so evidence is usually partial;
- a single build appears with more than one chrY checksum at identical chrY
  length. PAR-masking would explain that, but a header cannot confirm it:
  distinguishing a masked chrY from an unmasked one needs the sequence, to find
  N-runs in the pseudoautosomal region. Both checksums are therefore recorded as
  observations and neither is preferred, here or in the table.

What "unresolved" preserves
---------------------------
A file whose build cannot be determined still gets its *observations* back —
the checksums seen and the reference name declared. Discarding those would make
the file unresolvable forever; keeping them means a later table row can resolve
it from stored output, with no re-fetch. That matters because the evidence cache
holds raw headers and re-classifying the corpus is expensive.

Format neutrality
-----------------
Resolution runs over :class:`ContigSignature` values, not over header text, so
this module holds no SAM or VCF parsing of its own — ``header_extractors`` owns
that, and the two observers below are the only place the formats are told apart.
The generator that *builds* the table imports those same observers, which is what
keeps a table measured one way from being matched another.
"""

from __future__ import annotations

import re
from dataclasses import asdict, astuple, dataclass, fields
from pathlib import PurePosixPath

from ..rule_loader import ReferenceBuild, get_unified_rules
from .header_extractors import parse_sam_header, parse_vcf_header

# Contigs the build key is computed over. Changing this set means regenerating
# the table (scripts/generate_reference_builds.py) — ReferenceBuild's signature
# fields are named per contig, so the two have to move together.
KEY_CONTIGS = ("1", "Y")

# A SAM ``M5`` is the hex MD5 of the sequence. Header text is untrusted — the tag
# is whatever sat between two tabs — so a value that is not a checksum is dropped
# rather than recorded as one. Either case is accepted here (the SAM
# specification does not require one) and normalised below; contrast
# ``pipeline._MD5_RE``, which is lowercase-only because it validates md5s this
# project generated rather than ones a third party wrote.
_M5_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _checksum(value: str | None) -> str | None:
    """A header's ``M5`` tag as a lowercase MD5, or None if it is not one.

    Lowercased because matching against the build table is exact string
    membership: an uppercase checksum is the same sequence, and without
    normalising it here it would silently fail to resolve.
    """
    if not value or not _M5_RE.match(value):
        return None
    return value.lower()


def _length(value: str | None) -> int | None:
    """A header's contig length if it is a plain base-10 integer, else None.

    ``str.isdigit`` alone is not enough: it is true for characters like ``²``
    that ``int()`` then refuses, which would raise mid-classification on a
    malformed header. Requiring ASCII makes the guard match what ``int`` accepts.
    """
    if not value or not (value.isascii() and value.isdigit()):
        return None
    return int(value)


@dataclass(frozen=True)
class ContigSignature:
    """One reference contig as a file declares it.

    ``md5`` is ``None`` for VCF: the ``md5`` attribute of ``##contig`` is optional
    in the specification and populated on none of the cached headers, so VCF
    evidence rests on length alone. That is why builds differing only in sequence
    stay ambiguous when the evidence is a VCF.
    """

    name: str
    length: int | None
    md5: str | None = None

    @property
    def bare_name(self) -> str:
        """Contig name without a ``chr`` prefix, which references vary on."""
        return self.name.removeprefix("chr")


@dataclass(frozen=True)
class ReferenceIdentity:
    """What a file says it was aligned to.

    ``chr1_m5``, ``chry_m5`` and ``name`` are *observed* — read straight from the
    header. ``base`` and ``version`` are *derived* by matching those observations
    against the build table. ``version`` is ``None`` unless the evidence
    identifies exactly one build; ``base`` is filled whenever every candidate
    build agrees on the family, which is often true when the version is not —
    several CHM13 builds share a chr1.

    ``base`` duplicates the coarse ``reference_assembly`` value when both are
    known. That is deliberate: this object is meant to be readable on its own,
    and a consumer holding an identity should not have to look elsewhere to learn
    which family it belongs to.
    """

    base: str | None = None
    version: str | None = None
    chr1_m5: str | None = None
    chry_m5: str | None = None
    name: str | None = None

    def is_empty(self) -> bool:
        """True when nothing at all was observed or derived.

        Callers use this to omit the field entirely rather than emit an object
        whose every member is null, which would say nothing while looking like an
        answer. Derived from the declared fields, so adding one cannot leave this
        check behind.
        """
        return not any(astuple(self))

    def to_dict(self) -> dict:
        """Serialize for output, keys derived from the declared fields.

        Every key is always present, so a consumer can tell "we looked and found
        nothing" (null) from "this shape has no such field" — the object is only
        omitted upstream when nothing was found at all.
        """
        return asdict(self)


def observe_sam(header_text: str) -> tuple[list[ContigSignature], str | None]:
    """Contig signatures and the declared reference name from a SAM/BAM header.

    Reads the ``@SQ`` dictionary through ``parse_sam_header`` rather than
    re-tokenizing it, so tag order and optional tags behave here exactly as they
    do everywhere else in the project.
    """
    header = parse_sam_header(header_text)
    sq_records = header.sq or []
    signatures = [
        ContigSignature(
            name=sq["SN"],
            length=_length(sq.get("LN")),
            md5=_checksum(sq.get("M5")),
        )
        for sq in sq_records
        if sq.get("SN")
    ]
    # UR is the reference path, carried per-@SQ and identical across them; the
    # first record that has one speaks for the file.
    declared = next((sq["UR"] for sq in sq_records if sq.get("UR")), None)
    return signatures, _basename(declared)


def observe_vcf(header_text: str) -> tuple[list[ContigSignature], str | None]:
    """Contig signatures and the declared reference name from a VCF header.

    ``##contig`` attributes are unordered, which is why this reads the parsed
    fields rather than matching a positional pattern.
    """
    header = parse_vcf_header(header_text)
    signatures = []
    for contig in header.contigs or []:
        contig_id = contig.fields.get("ID")
        if not contig_id:
            continue
        signatures.append(ContigSignature(name=contig_id, length=_length(contig.fields.get("length"))))
    return signatures, _basename(header.reference)


def _basename(reference: str | None) -> str | None:
    """A declared reference path reduced to its filename.

    ``PurePosixPath`` because these are URIs and posix paths out of file headers:
    they must reduce the same way regardless of the OS running the classifier.

    A name is an observation about the file, not a statement about the
    reference's content — one name can denote references that differ, and
    references with different names can be identical — so it is used only to
    break a tie the checksums leave open.
    """
    if not reference:
        return None
    return PurePosixPath(reference.removeprefix("file://")).name


def _signature_for(signatures: list[ContigSignature], contig: str) -> ContigSignature | None:
    return next((sig for sig in signatures if sig.bare_name == contig), None)


def _consistent(build: ReferenceBuild, field: str, value: object) -> bool:
    """Whether one observation is consistent with one build.

    Three cases, and the middle one is where this went wrong once:

    - **nothing observed** — no constraint. A header without ``M5`` must still be
      able to match on lengths.
    - **the build records nothing for this contig** — no constraint either. An
      empty set means "never observed for this build", not "known to be absent".
      Treating it as a contradiction eliminates builds whose table row is merely
      thinner than another's, which is how a CHM13 v1.1 file — whose chr1 is
      byte-identical to v2.0's — came to resolve as v2.0, reproducing the exact
      collapse this module exists to prevent.
    - **both known** — must match, and a mismatch eliminates the build. That is
      what makes an unknown reference resolve to nothing rather than to its
      nearest neighbour.
    """
    if value is None:
        return True
    known = getattr(build, field)
    return not known or value in known


def _has_signatures(build: ReferenceBuild) -> bool:
    """Whether any contig signature was ever observed for this build.

    A row with none — ``GRCh38.p12`` is one, known only by name — is consistent
    with *every* observation under :func:`_consistent`, so it would join every
    candidate set and drag the family into disagreement.

    Excluding it makes such a row **currently unreachable**: the name narrows an
    existing candidate set rather than selecting outside it, and a file with no
    key-contig evidence returns before matching runs at all. That is the
    consequence of refusing to resolve a build from a filename alone, and it is
    the intended trade — a row like this contributes its aliases to the table's
    documentation but resolves nothing until a signature for it is observed.
    """
    return bool(build.chr1_length or build.chr1_m5 or build.chry_length or build.chry_m5)


def _candidates(observed: dict[str, object]) -> list[ReferenceBuild]:
    """Builds whose recorded signatures are consistent with the evidence."""
    return [
        build
        for build in get_unified_rules().reference_builds
        if _has_signatures(build) and all(_consistent(build, field, value) for field, value in observed.items())
    ]


def resolve_identity(signatures: list[ContigSignature], declared_name: str | None) -> ReferenceIdentity:
    """Identify the reference build behind a file's contig signatures.

    Format-neutral by construction: callers observe once, through
    :func:`observe_sam` or :func:`observe_vcf`, and resolution never learns which
    format the evidence came from.

    Ambiguous evidence — several builds consistent with what was observed —
    leaves ``version`` unset while keeping the observations. Accuracy over
    coverage: a wrong build is worse than none.
    """
    chr1 = _signature_for(signatures, KEY_CONTIGS[0])
    chry = _signature_for(signatures, KEY_CONTIGS[1])
    observed = {
        "chr1_length": chr1.length if chr1 else None,
        "chr1_m5": chr1.md5 if chr1 else None,
        "chry_length": chry.length if chry else None,
        "chry_m5": chry.md5 if chry else None,
    }

    # With no key-contig evidence at all there is nothing to narrow, and every
    # build would trivially be a candidate. The declared name must not resolve a
    # build by itself: a name is what a file claims, and a chr20-only BAM naming
    # chm13v2.0.fasta has offered no evidence that it is one. Keep the name as an
    # observation and derive nothing from it.
    if not any(value is not None for value in observed.values()):
        return ReferenceIdentity(name=declared_name)

    matches = _candidates(observed)

    # The declared name breaks a tie the signatures left open — narrowing an
    # existing candidate set, never introducing a build they ruled out.
    if len(matches) > 1 and declared_name:
        by_name = [build for build in matches if declared_name in build.aliases]
        if len(by_name) == 1:
            matches = by_name

    # Ambiguous evidence still fixes the family when every surviving candidate
    # agrees on one — a VCF carrying only chr1=248,387,497 cannot say which CHM13
    # v1.0 variant it is, but all three candidates are CHM13, so reporting that is
    # informative and cannot be wrong. Only `version` is withheld.
    families = {build.family for build in matches}
    build = matches[0] if len(matches) == 1 else None
    return ReferenceIdentity(
        base=families.pop() if len(families) == 1 else None,
        version=build.version if build else None,
        chr1_m5=chr1.md5 if chr1 else None,
        chry_m5=chry.md5 if chry else None,
        name=declared_name,
    )


def identity_from_sam(header_text: str) -> ReferenceIdentity:
    """Observe a SAM/BAM header and resolve the build behind it."""
    return resolve_identity(*observe_sam(header_text))


def identity_from_vcf(header_text: str) -> ReferenceIdentity:
    """Observe a VCF header and resolve the build behind it."""
    return resolve_identity(*observe_vcf(header_text))


# ReferenceIdentity's field names, derived rather than re-listed so the schema
# and any consumer stay in lockstep with the dataclass.
IDENTITY_FIELDS = tuple(f.name for f in fields(ReferenceIdentity))
