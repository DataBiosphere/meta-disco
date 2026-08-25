"""Resolve the specific reference *build* a file was aligned to (issue #340).

This sits beside :mod:`validators.contig_lengths` and answers a narrower
question. That module answers "which reference *family*" — GRCh38, GRCh37, CHM13
— and answers it robustly, on purpose: it matches contig lengths with a 1000 bp
tolerance precisely so that minor build differences do not defeat detection. This
module answers "which *build*", and so it does the opposite: exact matching only,
and ``None`` rather than a nearest neighbour.

The two never interact. The coarse value this project already emits is produced
entirely by ``contig_lengths`` and is unchanged by anything here; a build that
cannot be resolved leaves that value exactly as it was and simply adds no detail.

The key is (chr1, chrY)
-----------------------
Neither contig alone identifies a build, and the corpus shows why:

- **chr1 cannot separate CHM13 v1.1 from v2.0.** v2.0 is v1.1 plus an
  HG002-derived chrY, so their autosomes are identical and chr1 is 248,387,328
  in both.
- **chrY cannot separate GRCh38 from CHM13-with-grafted-GRCh38-chrY**, which
  share a chrY exactly because the latter borrowed it from the former.

The pair separates every reference observed in this corpus. That is a fitted
result rather than a general identity — two builds differing only on, say, chr7
would collide, and this module would correctly report the ambiguity rather than
pick one. #342's contig-set digest is the principled successor.

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
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import PurePosixPath

from ..rule_loader import get_unified_rules

_SQ_UR = re.compile(r"\tUR:(\S+)")
_VCF_REFERENCE = re.compile(r"##reference=(?:file://)?(\S+)")

# Contigs the build key is computed over, in the order they are reported.
KEY_CONTIGS = ("1", "Y")


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
        whose every member is null, which would say nothing while looking like
        an answer.
        """
        return not any((self.base, self.version, self.chr1_m5, self.chry_m5, self.name))

    def to_dict(self) -> dict:
        """Serialize for output. Every key is always present, so a consumer can
        distinguish "we looked and found nothing" (null) from "this shape has no
        such field" — the field is only omitted upstream when nothing was found
        at all."""
        return {
            "base": self.base,
            "version": self.version,
            "chr1_m5": self.chr1_m5,
            "chry_m5": self.chry_m5,
            "name": self.name,
        }


@cache
def _builds() -> tuple[dict, ...]:
    """The build table from unified_rules.yaml, signature fields as frozensets."""
    rows = []
    for row in get_unified_rules().reference_builds:
        rows.append(
            {
                "family": row.get("family"),
                "version": row.get("version"),
                "chr1_length": frozenset(row.get("chr1_length") or ()),
                "chr1_m5": frozenset(row.get("chr1_m5") or ()),
                "chry_length": frozenset(row.get("chry_length") or ()),
                "chry_m5": frozenset(row.get("chry_m5") or ()),
                "aliases": frozenset(row.get("aliases") or ()),
            }
        )
    return tuple(rows)


def _sq_signature(header_lines: list[str], contig: str) -> tuple[int | None, str | None]:
    """``(length, md5)`` for one contig from SAM ``@SQ`` lines."""
    pattern = re.compile(rf"\tSN:(?:chr)?{contig}\t")
    for line in header_lines:
        if line.startswith("@SQ") and pattern.search(line):
            length = re.search(r"\tLN:(\d+)", line)
            md5 = re.search(r"\tM5:(\w+)", line)
            return (int(length.group(1)) if length else None, md5.group(1) if md5 else None)
    return (None, None)


def _vcf_signature(header_lines: list[str], contig: str) -> tuple[int | None, str | None]:
    """``(length, None)`` for one contig from VCF ``##contig`` lines.

    Always ``None`` for the checksum: ``md5`` is an optional attribute of
    ``##contig`` in the VCF specification and is populated on none of the cached
    headers, so length is the only in-band signal this format offers. VCF builds
    are therefore resolvable only where lengths differ between builds — which is
    why, for instance, CHM13 v1.1 and v2.0 stay ambiguous from a VCF alone.
    """
    for line in header_lines:
        if line.startswith("##contig"):
            match = re.match(rf"##contig=<ID=(?:chr)?{contig},.*?length=(\d+)", line)
            if match:
                return (int(match.group(1)), None)
    return (None, None)


def _declared_name(header_lines: list[str], is_bam: bool) -> str | None:
    """The reference path the header declares, reduced to a basename.

    A name is an observation about the file, not a statement about the
    reference's content: one name can denote references that differ, and
    references with different names can be identical. It is recorded and used
    only to break a tie that the checksums leave open.
    """
    if is_bam:
        for line in header_lines:
            if line.startswith("@SQ"):
                match = _SQ_UR.search(line)
                return PurePosixPath(match.group(1)).name if match else None
        return None
    for line in header_lines:
        if line.startswith("##reference="):
            match = _VCF_REFERENCE.match(line)
            return PurePosixPath(match.group(1)).name if match else None
    return None


def _candidates(observed: dict[str, object]) -> list[dict]:
    """Builds consistent with every part of the evidence we actually have.

    Parts that were not observed do not constrain: a header without ``M5`` must
    still be able to match on lengths. A part that *was* observed and matches no
    build eliminates that build, which is what makes an unknown reference resolve
    to nothing rather than to its nearest neighbour.
    """
    matches = []
    for build in _builds():
        for field, value in observed.items():
            if value is None:
                continue
            if value not in build[field]:
                break
        else:
            matches.append(build)
    return matches


def resolve_identity(header_text: str, *, is_bam: bool) -> ReferenceIdentity:
    """Identify the reference build behind a BAM/CRAM or VCF header.

    Returns an identity whose ``base``/``version`` are filled only when the
    evidence matches exactly one build. Ambiguous evidence — several builds
    consistent with what was observed — resolves to ``None`` for both, keeping
    the observations. Accuracy over coverage: a wrong build is worse than none.
    """
    lines = header_text.strip().split("\n") if header_text else []
    if not lines:
        return ReferenceIdentity()

    signature = _sq_signature if is_bam else _vcf_signature
    chr1_length, chr1_m5 = signature(lines, KEY_CONTIGS[0])
    chry_length, chry_m5 = signature(lines, KEY_CONTIGS[1])
    name = _declared_name(lines, is_bam)

    matches = _candidates(
        {
            "chr1_length": chr1_length,
            "chr1_m5": chr1_m5,
            "chry_length": chry_length,
            "chry_m5": chry_m5,
        }
    )

    # The declared name breaks a tie the checksums left open — but only narrows an
    # existing candidate set, never introduces a build the signatures ruled out.
    if len(matches) > 1 and name:
        by_name = [build for build in matches if name in build["aliases"]]
        if len(by_name) == 1:
            matches = by_name

    # Ambiguous evidence still fixes the family when every surviving candidate
    # agrees on one — a VCF carrying only chr1=248,387,497 cannot say which CHM13
    # v1.0 variant it is, but all three candidates are CHM13, so reporting that is
    # informative and cannot be wrong. Only `version` is withheld.
    families = {build["family"] for build in matches}
    build = matches[0] if len(matches) == 1 else None
    return ReferenceIdentity(
        base=families.pop() if len(families) == 1 else None,
        version=build["version"] if build else None,
        chr1_m5=chr1_m5,
        chry_m5=chry_m5,
        name=name,
    )
