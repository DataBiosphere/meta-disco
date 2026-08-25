#!/usr/bin/env python3
"""Generate the ``reference_builds`` block of unified_rules.yaml from cached evidence.

Issue #340. The build table is *measured*, not hand-typed: every length and
checksum below is read from headers already in ``data/evidence/anvil``, so a row
can be checked against the corpus that produced it.

Why chr1 + chrY (the key this emits)
------------------------------------
A reference is identified here by the pair (chr1 signature, chrY signature).
Neither alone is sufficient, and the corpus shows why:

- **chr1 alone cannot separate CHM13 v1.1 from v2.0.** v2.0 is v1.1 plus an
  HG002-derived chrY, so the autosomes are byte-identical and chr1 is
  248,387,328 in both. The same holds for the two ``20200921`` builds at
  248,387,497, which differ only in where chrY came from.
- **chrY alone cannot separate GRCh38 from CHM13-with-grafted-GRCh38-chrY**,
  which share a chrY exactly because one borrowed it from the other.

The pair separates every reference observed in this corpus. That is a fitted
result, not a general identity: a reference differing from another only on, say,
chr7 would collide. #342's contig-set digest is the principled successor and
should supersede this key when it lands.

What this deliberately does not decide
--------------------------------------
Some reference *names* appear with two different chrY checksums at identical
chrY length — ``Homo_sapiens_assembly38.fasta`` and ``chm13v2.0.fasta`` both do.
PAR-masking would explain it, but the header cannot confirm that: telling a
masked chrY from an unmasked one needs the sequence itself, to look for N-runs
in the pseudoautosomal region. So this script records both checksums as
observations and asserts nothing about the cause. Consumers comparing
``chry_m5`` see the difference without us naming it.

Usage:
    python scripts/generate_reference_builds.py            # print the YAML block
    python scripts/generate_reference_builds.py --report   # per-reference evidence

Refreshing: re-run after the evidence cache gains headers from a reference not
already in the table, and paste the emitted block over ``reference_builds`` in
``src/meta_disco/rules/unified_rules.yaml``. The script never writes the YAML
itself — the table is reviewed input to the classifier, not a build artifact.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

EVIDENCE_GLOBS = (
    "data/evidence/anvil/bam/*/*",
    "data/evidence/anvil/vcf/*/*",
)

# Reference-name -> (family, version). The measured signatures below are facts;
# this mapping is the one place a human judgement enters, so it is explicit and
# reviewable rather than inferred from a filename at classify time.
#
# `version` is free text because the families version themselves differently:
# T2T releases (v1.0, v1.1, v2.0) and GRC patches (p12, p13) are not the same
# kind of thing, and CHM13 has no patch concept at all.
# CHM13 is derived from a female cell line and so has no chrY of its own. Builds
# that carry one grafted it from somewhere, and *where from* is a real difference
# in the reference even though the autosomes are identical — so those are separate
# builds here, not one build with a footnote. Collapsing them would reproduce, on
# chrY, exactly the collapse this issue exists to fix.
NAME_TO_BUILD: dict[str, tuple[str, str | None]] = {
    "chm13.draft_v1.0.fasta": ("CHM13", "v1.0"),
    "T2T_CHM13.v1.0": ("CHM13", "v1.0"),
    "t2t-chm13.20200921.withGRCh38chrY.chrEBV.chrYKI270740v1r.fasta": ("CHM13", "v1.0+GRCh38chrY"),
    "t2t-chm13.20200921.HG002chrY.chrEBV.fasta": ("CHM13", "v1.0+HG002chrY"),
    "chm13.v1.1.fasta": ("CHM13", "v1.1"),
    "chm13v2.0.fasta": ("CHM13", "v2.0"),
    # One assembly, several packagings. Packaging is #342's composition work; all
    # three are the same build as far as coordinates are concerned.
    "GRCh38_full_analysis_set_plus_decoy_hla.fa": ("GRCh38", None),
    "Homo_sapiens_assembly38.fasta": ("GRCh38", None),
    "GCA_000001405.15_GRCh38_no_alt_analysis_set.fna": ("GRCh38", None),
    "GRCh38.p12": ("GRCh38", "p12"),
}

_SQ_UR = re.compile(r"\tUR:(\S+)")
_VCF_REF = re.compile(r"##reference=(?:file://)?(\S+)")


def _sq_signature(header: str, contig: str) -> tuple[int | None, str | None]:
    """(length, md5) for one contig from a SAM ``@SQ`` block, or (None, None)."""
    pattern = re.compile(rf"\tSN:(?:chr)?{contig}\t")
    for line in header.split("\n"):
        if line.startswith("@SQ") and pattern.search(line):
            length = re.search(r"\tLN:(\d+)", line)
            md5 = re.search(r"\tM5:(\w+)", line)
            return (int(length.group(1)) if length else None, md5.group(1) if md5 else None)
    return (None, None)


def _vcf_signature(header: str, contig: str) -> tuple[int | None, str | None]:
    """(length, None) for one contig from VCF ``##contig`` lines.

    VCF carries no checksum: the ``md5`` attribute of ``##contig`` is optional in
    the spec and is populated on none of the cached headers, so length is the
    only in-band signal this format offers.
    """
    match = re.search(rf"##contig=<ID=(?:chr)?{contig},length=(\d+)", header)
    return (int(match.group(1)) if match else None, None)


def _reference_name(header: str, is_bam: bool) -> str | None:
    """The reference path the header declares, reduced to a basename."""
    if is_bam:
        for line in header.split("\n"):
            if line.startswith("@SQ"):
                match = _SQ_UR.search(line)
                return PurePosixPath(match.group(1)).name if match else None
        return None
    match = _VCF_REF.search(header)
    return PurePosixPath(match.group(1)).name if match else None


def collect() -> dict[str, Counter]:
    """Observed (chr1 len, chr1 m5, chrY len, chrY m5) per reference name."""
    observed: dict[str, Counter] = defaultdict(Counter)
    for pattern in EVIDENCE_GLOBS:
        is_bam = "/bam/" in pattern
        root, _, leaf = pattern.partition("*")
        for path in Path(root.rstrip("/")).glob("*" + leaf):
            if not path.is_file():
                continue
            try:
                with path.open() as handle:
                    record = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            header = record.get("header_text") or ""
            name = _reference_name(header, is_bam)
            if not name:
                continue
            sig = _sq_signature if is_bam else _vcf_signature
            chr1_len, chr1_m5 = sig(header, "1")
            chry_len, chry_m5 = sig(header, "Y")
            observed[name][(chr1_len, chr1_m5, chry_len, chry_m5)] += 1
    return observed


def build_rows(observed: dict[str, Counter]) -> list[dict]:
    """One row per *build*, holding the set of signatures observed for it.

    Grouped by (family, version) rather than by reference name, because several
    names denote one build — ``GRCh38_full_analysis_set_plus_decoy_hla.fa`` and
    ``Homo_sapiens_assembly38.fasta`` are the same assembly, differently packaged.

    Each signature field is a *set*, not a single value, for two reasons:

    - headers vary in completeness (a chromosome-subset BAM has no chr1; only
      some carry M5 at all), so no one header supplies a whole signature;
    - a build legitimately appears with more than one chrY checksum at identical
      length — see the module docstring on what we do not conclude from that.

    A majority vote would paper over the second case by picking whichever variant
    happened to be more common, so matching is set membership instead.
    """
    rows: dict[tuple[str, str | None], dict] = {}
    for name, counter in sorted(observed.items()):
        if name not in NAME_TO_BUILD:
            print(f"# WARNING: unmapped reference name, skipped: {name}", file=sys.stderr)
            continue
        family, version = NAME_TO_BUILD[name]
        row = rows.setdefault(
            (family, version),
            {
                "family": family,
                "version": version,
                "chr1_length": set(),
                "chr1_m5": set(),
                "chry_length": set(),
                "chry_m5": set(),
                "aliases": set(),
                "files_seen": 0,
            },
        )
        row["aliases"].add(name)
        row["files_seen"] += sum(counter.values())
        for signature in counter:
            for field, value in zip(("chr1_length", "chr1_m5", "chry_length", "chry_m5"), signature, strict=True):
                if value is not None:
                    row[field].add(value)
    return list(rows.values())


def emit_yaml(rows: list[dict]) -> str:
    lines = [
        "reference_builds:",
        "  # Generated by scripts/generate_reference_builds.py (issue #340) from the",
        "  # cached evidence headers — every length and checksum here was measured, not",
        "  # transcribed. Re-run that script to refresh; see its docstring for why the",
        "  # key is (chr1, chrY) and what it deliberately does not decide.",
        "  #",
        "  # `family` matches reference_assembly_enum and is what the coarse classifier",
        "  # already emits. `version` is free text: T2T versions (v1.0/v1.1/v2.0) and GRC",
        "  # patches (p12) are different kinds of thing, and CHM13 has no patch concept.",
        "  # A null version means the observed evidence does not pin one down.",
        "  #",
        "  # Signature fields are LISTS of observed values and match by membership. A",
        "  # build can carry more than one chrY checksum at the same chrY length; the",
        "  # header cannot say why, so both are recorded and neither is preferred.",
        "  # An empty list means that part was never observed for this build.",
    ]
    for row in sorted(rows, key=lambda r: (r["family"], str(r["version"]))):
        version = f'"{row["version"]}"' if row["version"] else "null"
        lines.append(f"  - family: {row['family']}")
        lines.append(f"    version: {version}")
        for field in ("chr1_length", "chr1_m5", "chry_length", "chry_m5"):
            values = sorted(row[field])
            if not values:
                lines.append(f"    {field}: []")
                continue
            lines.append(f"    {field}:")
            for value in values:
                lines.append(f"      - {value}" if isinstance(value, int) else f'      - "{value}"')
        lines.append("    aliases:")
        for alias in sorted(row["aliases"]):
            lines.append(f'      - "{alias}"')
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="print per-reference evidence instead of YAML")
    args = parser.parse_args()

    observed = collect()
    if not observed:
        print("No cached evidence found under data/evidence/anvil — nothing to generate.", file=sys.stderr)
        return 1

    if args.report:
        header = f"{'reference':60s} {'chr1 len':>10} {'chr1 m5':14s} {'chrY len':>10} {'chrY m5':14s} files"
        print(header)
        for name in sorted(observed):
            for (c1l, c1m, cyl, cym), count in observed[name].most_common():
                print(f"{name[:60]:60s} {c1l!s:>10} {str(c1m)[:12]:14s} {cyl!s:>10} {str(cym)[:12]:14s} {count}")
        return 0

    print(emit_yaml(build_rows(observed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
