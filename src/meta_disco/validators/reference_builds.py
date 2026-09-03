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
two kinds: pairs involving ``GRCh38.p12``, which records no signature at all,
and CHM13 v1.0 against the HG002-grafted v1.0, which share chr1 and both declare
chrY absent (see "Declared absence" below). CHM13 v1.1 and v2.0 share chr1 too,
so a *nameless* file carrying only chr1 resolves to the family and withholds the
version — the honest outcome, and the ceiling of a two-contig key.

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

Declared absence (issue #351)
-----------------------------
An empty signature set on a table row means "never observed" and constrains
nothing, which is right for a thin row. But some rows are not thin: CHM13 v1.0
and v1.1 have no chrY at all (CHM13 is a female cell line; v2.0 is the first
release to carry one), and the HG002-grafted v1.0 names its Y contig
``chrY_hg002``. A header that lists ``chrY`` with a length or checksum cannot
have come from any of them. ``ReferenceBuild.absent`` says so, and
:func:`_consistent` treats such an observation as a contradiction. Absence is
only evidence when the contig *is* observed with a value: a header with no chrY
line — or a bare ``##contig=<ID=chrY>`` carrying no length — is consistent with
a reference that has no chrY. The declaration is human knowledge, not a
measurement, so it lives in one place in the generator, which checks it against
every cached header whose declared reference name maps to one of these builds.

What "unresolved" preserves
---------------------------
A file whose build cannot be determined still gets its *observations* back:
the key-contig checksums seen and the reference name declared, with where the
name was read from. Keeping them means a later table row can resolve such a
file from stored output, without re-reading its header. That holds for BAM/CRAM, which usually carry ``M5``; it
does not yet hold for a VCF, whose only signature is contig *length* and which
:class:`ReferenceIdentity` does not serialize — issue #349.

Format neutrality
-----------------
Resolution runs over :class:`ContigSignature` values, not over header text, so
this module holds no SAM or VCF parsing of its own — ``header_extractors`` owns
that, and the two observers below are the only place the formats are told apart.
The generator that *builds* the table imports those same observers, which is what
keeps a table measured one way from being matched another.

Where the declared name comes from (issue #354)
-----------------------------------------------
Each format has a field that exists to name the reference — SAM ``@SQ UR``,
VCF ``##reference`` — and it is read first. Many headers leave it empty (issue
#354 has the corpus counts) while the command line of the aligner or caller
(``@PG CL``, ``##GATKCommandLine``) names the reference anyway, so the
observers fall back to that, format-neutrally: :func:`reference_from_command_line` knows two
conventions (a reference flag, else the first FASTA-looking argument) and no
tool names. What makes a command-line name safe to record is not the parse but
the guards around it — a header with no contigs takes none, command lines that
disagree yield none, a lifted VCF's are not consulted — and the fact that a
name only ever breaks a tie the signatures left open. The identity records the
source (``name_source``) so a consumer can weight the two differently.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import asdict, astuple, dataclass, fields
from itertools import pairwise
from pathlib import PurePosixPath

# The key contigs and the row layout live beside ``ReferenceBuild`` in the
# loader, which validates ``absent`` against them at load (#351).
from ..rule_loader import FIELD_CONTIG, KEY_CONTIGS, ReferenceBuild, get_unified_rules
from .header_extractors import is_lifted, parse_sam_header, parse_vcf_header, sam_command_lines, vcf_command_lines

# A SAM ``M5`` is the hex MD5 of the sequence. Header text is untrusted — the tag
# is whatever sat between two tabs — so a value that is not a checksum is dropped
# rather than recorded as one. Either case is accepted here (the SAM
# specification does not require one) and normalised below; contrast
# ``pipeline._MD5_RE``, which is lowercase-only because it validates md5s this
# project generated rather than ones a third party wrote.
_M5_RE = re.compile(r"^[0-9a-fA-F]{32}$")

# Where a declared reference name was read from (issue #354). A name from the
# field that exists to carry it (SAM ``@SQ UR``, VCF ``##reference``) is one
# step closer to the file than one recovered from the command line of the
# program that produced it; the source is recorded so a consumer can weight
# them differently. The values are the ``reference_name_source_enum`` in the
# schema.
NAME_SOURCE_REFERENCE_FIELD = "reference_field"
NAME_SOURCE_COMMAND_LINE = "command_line"

# The reference-flag spellings issue #354 names, and what a reference path
# looks like; the rule that uses them is :func:`reference_from_command_line`.
# The extension set is kept apart from ``file_name.EXTENSION_TO_FORMAT`` on
# purpose: that vocabulary says which files this pipeline classifies, and
# ``.fna`` — common for reference FASTAs named on command lines — is not one
# of them. Widening it here would change classification, not just this parse.
_REFERENCE_FLAGS = frozenset({"--reference", "-R", "-r"})
_FASTA_PATH_RE = re.compile(r"\.(fa|fasta|fna)(\.gz)?$", re.IGNORECASE)


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
class DeclaredReference:
    """A reference name as a header declares it, and where in the header it was read.

    ``name`` is the filename only (see :func:`_basename`); ``source`` is one of
    the ``NAME_SOURCE_*`` values.
    """

    name: str
    source: str


@dataclass(frozen=True)
class ReferenceIdentity:
    """What a file says it was aligned to.

    ``chr1_m5``, ``chry_m5``, ``name`` and ``name_source`` are *observed* — read
    straight from the header. ``base`` and ``version`` are *derived* by matching
    those observations against the build table. ``version`` is ``None`` unless
    the evidence identifies exactly one build; ``base`` is filled whenever every
    candidate build agrees on the family, which is often true when the version
    is not — several CHM13 builds share a chr1.

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
    name_source: str | None = None

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


def observe_sam(header_text: str) -> tuple[list[ContigSignature], DeclaredReference | None]:
    """Contig signatures and the declared reference name from a SAM/BAM header.

    Reads the ``@SQ`` dictionary through ``parse_sam_header`` rather than
    re-tokenizing it, so tag order and optional tags behave here exactly as they
    do everywhere else in the project.

    The name comes from ``@SQ UR`` when any record carries one, and otherwise
    from the ``@PG`` command lines (#354) under the guards in
    :func:`_declared_from_command_lines`.
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
    declared = _declared_from_field(next((sq["UR"] for sq in sq_records if sq.get("UR")), None))
    if declared is None:
        declared = _declared_from_command_lines(sam_command_lines(header), signatures)
    return signatures, declared


def observe_vcf(header_text: str) -> tuple[list[ContigSignature], DeclaredReference | None]:
    """Contig signatures and the declared reference name from a VCF header.

    ``##contig`` attributes are unordered, which is why this reads the parsed
    fields rather than matching a positional pattern.

    The name comes from ``##reference`` when present, and otherwise from the
    header's command lines (#354) under the guards in
    :func:`_declared_from_command_lines` — unless the header carries liftover
    INFO fields, in which case the command lines describe the file before it
    was lifted and are not consulted.
    """
    header = parse_vcf_header(header_text)
    signatures = []
    for contig in header.contigs or []:
        contig_id = contig.fields.get("ID")
        if not contig_id:
            continue
        signatures.append(ContigSignature(name=contig_id, length=_length(contig.fields.get("length"))))
    declared = _declared_from_field(header.reference)
    # A lifted VCF's command lines name the reference the *caller* was given,
    # which is the pre-liftover build, so they are not consulted.
    if declared is None and not is_lifted(header):
        declared = _declared_from_command_lines(vcf_command_lines(header), signatures)
    return signatures, declared


def _declared_from_field(reference: str | None) -> DeclaredReference | None:
    """The dedicated reference field's value as a declaration, or ``None`` if it is empty."""
    name = _basename(reference)
    return DeclaredReference(name, NAME_SOURCE_REFERENCE_FIELD) if name else None


def _declared_from_command_lines(
    command_lines: list[str], signatures: list[ContigSignature]
) -> DeclaredReference | None:
    """The one reference name a header's command lines agree on, or ``None`` (#354).

    Two guards, both structural rather than tool-specific:

    - **no contigs, no name.** A name is an observation about a contig
      dictionary; a header that declares none has nothing for it to describe.
      In practice this is the unaligned-reads BAM whose only FASTA argument is
      an adapter or barcode file.
    - **disagreement yields nothing.** Command lines naming two different files
      cannot be reduced to one declaration without knowing which tool's word
      counts, and this function does not know tools. Accuracy over coverage.

    Each command line contributes at most one name, via
    :func:`reference_from_command_line`; lines naming nothing are ignored.
    """
    if not signatures:
        return None
    names = {name for name in map(reference_from_command_line, command_lines) if name}
    if len(names) != 1:
        return None
    return DeclaredReference(names.pop(), NAME_SOURCE_COMMAND_LINE)


def reference_from_command_line(command_line: str) -> str | None:
    """The reference filename a program command line names, or ``None`` (#354).

    Deliberately tool-agnostic — two conventions and no aligner or caller
    names:

    - the argument after a reference flag (``--reference``, ``-R``, ``-r``;
      ``--reference=path`` counts too) when it looks like a FASTA path. The
      FASTA check is what stops bwa's ``-R``, a read-group string, from ever
      matching;
    - otherwise the first argument that looks like a FASTA path, which is where
      aligners that take the reference positionally (bwa, minimap2, winnowmap)
      put it — and, without either being named here, where samtools' ``-T`` and
      bcftools' ``-f`` values fall.

    Precision comes from :func:`_declared_from_command_lines`'s guards, not from
    this parse. Splitting is ``str.split`` unless the line contains a quote
    character: ``shlex`` is two hundred times slower and only matters when a
    quoted argument (a read-group string) must stay one token; a line ``shlex``
    rejects (an unbalanced quote) falls back to whitespace splitting.
    """
    argv = _split_command_line(command_line)
    # ``--reference=path`` as the two tokens the flag loop expects.
    argv = [part for arg in argv for part in (arg.split("=", 1) if arg.startswith("--reference=") else (arg,))]
    for flag, value in pairwise(argv):
        if flag in _REFERENCE_FLAGS and _FASTA_PATH_RE.search(value):
            return _basename(value)
    return next((_basename(arg) for arg in argv[1:] if _FASTA_PATH_RE.search(arg)), None)


def _split_command_line(command_line: str) -> list[str]:
    if '"' not in command_line and "'" not in command_line:
        return command_line.split()
    try:
        return shlex.split(command_line)
    except ValueError:
        return command_line.split()


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

    Four cases, and the third is where this went wrong once:

    - **nothing observed** — no constraint. A header without ``M5`` must still be
      able to match on lengths.
    - **the build declares the contig absent** (#351) — a contradiction; see
      "Declared absence" in the module docstring. Only reached when something
      *was* observed, per the first case.
    - **the build records nothing for this contig** — no constraint. An empty
      set means "never observed for this build", not "known to be absent" —
      that is what ``absent`` is for. Treating it as a contradiction eliminates
      builds whose table row is merely thinner than another's, which is how a
      CHM13 v1.1 file — whose chr1 is byte-identical to v2.0's — came to resolve
      as v2.0, reproducing the exact collapse this module exists to prevent.
    - **both known** — must match, and a mismatch eliminates the build. That is
      what makes an unknown reference resolve to nothing rather than to its
      nearest neighbour.
    """
    if value is None:
        return True
    if FIELD_CONTIG[field] in build.absent:
        return False
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


def resolve_identity(signatures: list[ContigSignature], declared: DeclaredReference | None) -> ReferenceIdentity:
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

    name = declared.name if declared else None
    source = declared.source if declared else None

    # With no key-contig evidence at all there is nothing to narrow, and every
    # build would trivially be a candidate. The declared name must not resolve a
    # build by itself: a name is what a file claims, and a chr20-only BAM naming
    # chm13v2.0.fasta has offered no evidence that it is one. Keep the name as an
    # observation and derive nothing from it.
    if not any(value is not None for value in observed.values()):
        return ReferenceIdentity(name=name, name_source=source)

    matches = _candidates(observed)

    # The declared name breaks a tie the signatures left open — narrowing an
    # existing candidate set, never introducing a build they ruled out. Where it
    # was read from does not change that: a command-line name is one step
    # further from the file, but it is still only ever choosing among builds
    # the signatures already allow.
    if len(matches) > 1 and name:
        by_name = [build for build in matches if name in build.aliases]
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
        name=name,
        name_source=source,
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
