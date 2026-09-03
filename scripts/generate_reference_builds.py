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

The pair does not separate every build it emits; some pairs rely on the declared
name. See the resolver module docstring for the kinds, and
``NAME_DEPENDENT_PAIRS`` in tests/test_reference_builds.py for the pinned list.
#342's contig-set digest is the structural fix.

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
import sys
from collections import Counter, defaultdict
from pathlib import Path

from meta_disco.evidence import BamEvidence, VcfEvidence
from meta_disco.validators.reference_builds import (
    FIELD_CONTIG,
    KEY_CONTIGS,
    SIGNATURE_FIELDS,
    observe_sam,
    observe_vcf,
)

# (evidence directory, observer, evidence class). The observers — and the key
# and field layout the table is written in — are imported from the resolver
# rather than reimplemented here: this script measures the table the resolver
# matches against, so a parser or key that differed would produce a table describing
# headers the resolver reads differently. That divergence is not hypothetical —
# an earlier version of this script used a stricter ##contig pattern than the
# resolver and would silently have under-populated the table.
EVIDENCE_SOURCES = (
    (Path("data/evidence/anvil/bam"), observe_sam, BamEvidence),
    (Path("data/evidence/anvil/vcf"), observe_vcf, VcfEvidence),
)

# Reference-name -> (family, version). The measured signatures are facts; this
# mapping is the one place a human judgement enters, so it is explicit and
# reviewable rather than inferred from a filename at classify time.
#
# `version` is free text because the families version themselves differently:
# T2T releases (v1.0, v1.1, v2.0) and GRC patches (p12, p13) are not the same
# kind of thing, and CHM13 has no patch concept at all.
#
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

# Key contigs a build has *no contig named that* for (issue #351), by bare name.
# This is the one declared — not measured — fact in the table: a header can show
# that a file listed no chrY, never that the reference lacks one. So it is stated
# here, in one place, and can only be *falsified*: `check_absences` refuses the
# table if any cached header for one of these builds lists the contig after all.
#
# CHM13 is assembled from a female cell line and has no chrY of its own. v1.0 and
# v1.1 ship without one; v2.0 is the first release to carry a chrY (HG002's). The
# HG002-grafted v1.0 does carry a Y, but names it `chrY_hg002`, so no file aligned
# to it lists a contig called `chrY` either.
KNOWN_ABSENT: dict[tuple[str, str | None], tuple[str, ...]] = {
    ("CHM13", "v1.0"): (KEY_CONTIGS[1],),
    ("CHM13", "v1.0+HG002chrY"): (KEY_CONTIGS[1],),
    ("CHM13", "v1.1"): (KEY_CONTIGS[1],),
}


def collect() -> dict[str, Counter]:
    """Observed (chr1 len, chr1 m5, chrY len, chrY m5) per reference name.

    Reads through the ``CachedEvidence`` classes rather than raw JSON so a
    structurally wrong entry is skipped at the boundary. That check is
    structural only — ``from_json`` does not validate payload *types* — so a
    corrupt entry whose ``header_text`` is not a string still arrives here, and
    is skipped explicitly below. One bad cache file must not abort a table
    generation that reads hundreds of thousands of them.
    """
    observed: dict[str, Counter] = defaultdict(Counter)
    for directory, observe, evidence_cls in EVIDENCE_SOURCES:
        for path in directory.glob("*/*"):
            if not path.is_file():
                continue
            try:
                with path.open() as handle:
                    entry = evidence_cls.from_json(json.load(handle))
            except (OSError, ValueError):
                # ValueError covers JSONDecodeError and UnicodeDecodeError — a
                # cache member that is not valid UTF-8 raises the latter, which
                # is not an OSError and would otherwise abort a run over hundreds
                # of thousands of files. CachedEvidence.load treats the same case
                # as a miss; this read matches that.
                continue
            if entry is None or not isinstance(entry.header_text, str):
                continue
            signatures, name = observe(entry.header_text)
            if not name:
                continue
            by_contig = {sig.bare_name: sig for sig in signatures}
            chr1 = by_contig.get(KEY_CONTIGS[0])
            chry = by_contig.get(KEY_CONTIGS[1])
            observed[name][
                (
                    chr1.length if chr1 else None,
                    chr1.md5 if chr1 else None,
                    chry.length if chry else None,
                    chry.md5 if chry else None,
                )
            ] += 1
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
                "absent": KNOWN_ABSENT.get((family, version), ()),
            },
        )
        row["aliases"].add(name)
        for signature in counter:
            for field, value in zip(SIGNATURE_FIELDS, signature, strict=True):
                if value is not None:
                    row[field].add(value)
    return list(rows.values())


def check_absences(observed: dict[str, Counter]) -> list[str]:
    """Every corpus observation that contradicts a ``KNOWN_ABSENT`` declaration.

    A declaration says a build has no contig by that name; one cached header for
    that build listing the contig is enough to falsify it. Returns one line per
    contradiction naming the build, the reference name, and the contig, so the
    declaration can be corrected rather than silently mis-resolving files.
    """
    contradictions = []
    declared = {name: build for name, build in NAME_TO_BUILD.items() if build in KNOWN_ABSENT}
    for name, build in sorted(declared.items()):
        for contig in KNOWN_ABSENT[build]:
            seen = sum(
                count
                for sig, count in observed.get(name, Counter()).items()
                if any(v is not None for f, v in zip(SIGNATURE_FIELDS, sig, strict=True) if FIELD_CONTIG[f] == contig)
            )
            if seen:
                contradictions.append(
                    f"{build[0]}/{build[1]} declares chr{contig} absent, but {seen} header(s) naming {name} list it"
                )
    return contradictions


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
        "  #",
        "  # `absent` (issue #351) lists key contigs the reference has NO contig named",
        "  # that for, so a header listing one rules the build out. Declared, not",
        "  # measured — see KNOWN_ABSENT in the generator, which checks it against the",
        "  # corpus. Distinct from an empty list, which constrains nothing.",
    ]
    for row in sorted(rows, key=lambda r: (r["family"], str(r["version"]))):
        version = f'"{row["version"]}"' if row["version"] else "null"
        lines.append(f"  - family: {row['family']}")
        lines.append(f"    version: {version}")
        for field in SIGNATURE_FIELDS:
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
        if row["absent"]:
            lines.append("    absent:")
            for contig in sorted(row["absent"]):
                lines.append(f'      - "{contig}"')
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

    contradictions = check_absences(observed)
    if contradictions:
        print("KNOWN_ABSENT is contradicted by the corpus; no table emitted:", file=sys.stderr)
        for line in contradictions:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(emit_yaml(build_rows(observed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
