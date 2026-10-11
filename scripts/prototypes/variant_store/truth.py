"""The questions asked of every layout, and bcftools's answers to them (#663).

The questions are drawn once, from the VCF's own sites with :data:`common.SEED`, and
saved to ``results/questions.json`` so every script asks the same ones. The answers
come straight from the VCF with ``bcftools ... -i 'GT="alt"'`` (a tabix region per
variant, a full pass per sample), timed, and saved to ``results/truth.json`` with the
fingerprint of the questions they answer; each layout is checked against them exactly.
"""

from __future__ import annotations

import random
import subprocess
from collections import Counter
from dataclasses import dataclass
from typing import Any

from common import CHROM, SEED, VCF, WORK, cached_lines, fingerprint, load, save, sh, time_ms

AN = 6404  # 3,202 samples, diploid on chr22
ANSWERS_FORMAT = 2  # 2: a sample's answer is a sorted list of pairs


@dataclass(frozen=True)
class Variant:
    pos: int
    ref: str
    alt: str
    ac: int

    @property
    def key(self) -> tuple[int, str, str]:
        return (self.pos, self.ref, self.alt)

    @property
    def id(self) -> str:
        return variant_id(self.pos, self.ref, self.alt)

    @property
    def kind(self) -> str:
        if self.alt.startswith("<") or max(len(self.ref), len(self.alt)) > 50:
            return "SV"
        return "SNV" if len(self.ref) == len(self.alt) == 1 else "indel"


def variant_id(pos: int, ref: str, alt: str) -> str:
    """The id every layout answers by, ``chrom:pos:ref:alt``."""
    return f"{CHROM}:{pos}:{ref}:{alt}"


def sites() -> list[Variant]:
    """Every site of the VCF with its allele count, cached in ``sites.tsv``."""
    rows = cached_lines(
        WORK / "sites.tsv", f"bcftools query -f '%POS\\t%REF\\t%ALT\\t%INFO/AC\\n' {sh(VCF)} 2>/dev/null"
    )
    return [Variant(int(pos), ref, alt, int(ac)) for pos, ref, alt, ac in rows]


AC_BINS = [(1, 1), (2, 10), (11, 100), (101, 1000), (1001, AN)]


def choose() -> dict[str, Any]:
    """Draw the questions: single variants by kind and allele count, three sets of 50, and samples."""
    rng = random.Random(SEED)
    all_sites = sites()
    singles = []
    for kind in ("SNV", "indel", "SV"):
        for lo, hi in AC_BINS:
            pool = [v for v in all_sites if v.kind == kind and lo <= v.ac <= hi]
            if pool:
                singles.append(rng.choice(pool))
    frequent = [v for v in all_sites if v.ac > 0.3 * AN]
    start = rng.randrange(len(frequent) - 50)
    sets = {
        "50 consecutive common (AF>0.3) variants": frequent[start : start + 50],
        "50 random variants with AF>0.5": rng.sample([v for v in all_sites if v.ac > 0.5 * AN], 50),
        "50 random variants": rng.sample(all_sites, 50),
    }
    questions = {
        "singles": [v.__dict__ for v in singles],
        "sets": {name: [v.__dict__ for v in vs] for name, vs in sets.items()},
        "samples": sorted(rng.sample(sample_names(), 3)),
    }
    save("questions", questions)
    return questions


def _raw_questions() -> dict[str, Any]:
    return load("questions") or choose()


def questions() -> tuple[list[Variant], dict[str, list[Variant]], list[str]]:
    """The saved questions (drawn on first use).

    Raises SystemExit where a question names a (pos, ref, alt) two VCF records share: the
    layouts key on it, so their answers there would merge both records.
    """
    raw = _raw_questions()
    singles = [Variant(**v) for v in raw["singles"]]
    sets = {name: [Variant(**v) for v in vs] for name, vs in raw["sets"].items()}
    counts = Counter(v.key for v in sites())
    duplicated = {v.key for v in [*singles, *(v for vs in sets.values() for v in vs)] if counts[v.key] > 1}
    if duplicated:
        raise SystemExit(f"questions ask about a (pos, ref, alt) two records share: {duplicated}")
    return singles, sets, raw["samples"]


def sample_names() -> list[str]:
    return subprocess.run(
        ["bcftools", "query", "-l", str(VCF)], capture_output=True, text=True, check=True
    ).stdout.split()


def _query(args: list[str]) -> list[str]:
    out = subprocess.run(["bcftools", "query", *args, str(VCF)], capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def carriers(v: Variant) -> dict[str, str]:
    """``{sample: genotype}`` of every carrier of ``v``."""
    lines = _query(["-r", f"{CHROM}:{v.pos}-{v.pos}", "-i", 'GT="alt"', "-f", r"%POS\t%REF\t%ALT[\t%SAMPLE=%GT]\n"])
    found: dict[str, str] = {}
    for line in lines:
        pos, ref, alt, *calls = line.split("\t")
        if (int(pos), ref, alt) == v.key:
            found = dict(call.split("=", 1) for call in calls)
    return found


def carriers_of_all(vs: list[Variant]) -> set[str]:
    """The samples carrying every variant of ``vs`` (an intersection of :func:`carriers`)."""
    result: set[str] | None = None
    for v in vs:
        found = set(carriers(v))
        result = found if result is None else result & found
    return result or set()


def variants_of(sample: str) -> list[tuple[str, str]]:
    """``(variant id, genotype)`` of every non-reference genotype of ``sample``, sorted.

    A list, not a map: where two records share a variant id, a sample can carry both.
    """
    lines = _query(["-s", sample, "-i", 'GT="alt"', "-f", r"%CHROM:%POS:%REF:%ALT\t[%GT]\n"])
    return sorted(tuple(line.split("\t")) for line in lines)


@dataclass
class Answers:
    """bcftools's answers to the saved questions, and how long bcftools took to give each (ms)."""

    carriers: dict[str, dict[str, str]]  # by variant id
    carriers_of_all: dict[str, set[str]]  # by set name
    variants_of: dict[str, list[tuple[str, str]]]  # by sample, sorted
    bcftools_ms: dict[str, dict[str, float]]


def answers() -> Answers:
    """The answers, from ``results/truth.json`` where it answers the current questions, else from bcftools."""
    # The answers' format is part of what they were made for, so a format change recomputes them.
    asked = fingerprint([_raw_questions(), ANSWERS_FORMAT])
    saved: dict[str, Any] | None = load("truth")
    if not saved or saved["questions"] != asked:
        singles, sets, samples = questions()
        saved = {"questions": asked, "carriers": {}, "carriers_of_all": {}, "variants_of": {}, "bcftools_ms": {}}
        for section, items in (
            ("carriers", [(v.id, lambda v=v: carriers(v)) for v in singles]),
            ("carriers_of_all", [(name, lambda vs=vs: sorted(carriers_of_all(vs))) for name, vs in sets.items()]),
            ("variants_of", [(s, lambda s=s: variants_of(s)) for s in samples]),
        ):
            saved["bcftools_ms"][section] = {}
            for key, fn in items:
                saved[section][key], (ms,) = time_ms(fn, 1)
                saved["bcftools_ms"][section][key] = round(ms, 1)
        save("truth", saved)
    return Answers(
        carriers=saved["carriers"],
        carriers_of_all={name: set(found) for name, found in saved["carriers_of_all"].items()},
        variants_of={sample: [tuple(pair) for pair in pairs] for sample, pairs in saved["variants_of"].items()},
        bcftools_ms=saved["bcftools_ms"],
    )
