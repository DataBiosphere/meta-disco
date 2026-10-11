# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy==2.3.3", "pgenlib==0.94.1"]
# ///
"""Build the 2-bit layouts and time the same questions on them (#663).

Two layouts, both built from the VCF:

- **pgen**: PLINK 2's ``.pgen`` (``plink2 --make-pgen``), 2 bits per genotype plus phase,
  read in-process with ``pgenlib`` so the timings compare with DuckDB's rather than with
  a process start.
- **bitmap file**: one carrier mask per variant (3,202 bits, packed to 401 bytes), built
  from the ``.pgen`` and memory-mapped. It holds carriers only, not zygosity or phase.

"Carriers of all of V1…V50" is answered three ways: read the 50 variants from the
``.pgen`` and filter the genotype array (**read + filter**); read the same 50, pack each
to a carrier mask and AND the masks (**masks at query time**); and AND the 50 masks of
the bitmap file (**bitmap file**).

Answers are checked against bcftools: on the ``.pgen``, the carrier set and each
carrier's zygosity (allele dosage 1 or 2; phase is stored but not compared); on the
bitmap file, the carrier set. ``pgenlib`` reads local files only, so neither layout has
simulated-S3 timings.

Each question is timed two ways, as the Parquet side is: **fresh**, opening the file
(a ``PgenReader``, or a mapping of the bitmap file) on every run, which is what a request
pays when nothing stays open; and **warm**, with the file opened once beforehand, which
is what a running server pays. Only the read and its arithmetic are inside the timing:
turning sample indices into names and variant ids, which the check against bcftools
needs, happens after it.

It also times KING kinship (``plink2 --make-king``) on chr22, the cost of precomputing
sample similarity.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np
import pgenlib
import truth
from common import PGEN_PREFIX, REPEATS, VCF, Checker, load, machine, save, size, stale, summarize, time_ms

CHUNK = 10_000  # variants read at a time while building the bitmap file
BITMAP = PGEN_PREFIX.with_suffix(".carriers.bitmap")


def dosage(gt: str) -> int:
    return sum(a == "1" for a in gt.replace("/", "|").split("|"))


def plink2(*args: str) -> float:
    start = time.perf_counter()
    subprocess.run(["plink2", *args], check=True, stdout=subprocess.DEVNULL)
    return time.perf_counter() - start


def built(output: Path, source: Path, key: str, saved: dict[str, Any], build: Any) -> float:
    """The seconds ``build()`` took to write ``output`` from ``source``.

    The saved figure where ``output`` exists, is no older than ``source`` and has one.
    """
    if not stale(output, source) and key in saved:
        return saved[key]
    return round(build(), 1)


def pvar_keys() -> tuple[list[tuple[int, str, str]], float]:
    """Each variant's (pos, ref, alt) in ``.pvar`` order, and the seconds it took to load.

    A list, not a map: two symbolic SVs of the panel share (pos, ref, alt) with another
    record, so the key does not name one variant there.
    """
    start = time.perf_counter()
    keys = []
    with PGEN_PREFIX.with_suffix(".pvar").open() as f:
        for line in f:
            if not line.startswith("#"):
                _, pos, _, ref, alt = line.split("\t", 5)[:5]
                keys.append((int(pos), ref, alt.rstrip("\n")))
    return keys, time.perf_counter() - start


def build_bitmap(pgen: bytes, variant_ct: int, sample_ct: int) -> float:
    """Write one packed carrier mask per variant to :data:`BITMAP`; return the seconds it took."""
    start = time.perf_counter()
    r = pgenlib.PgenReader(pgen)
    buf = np.empty((CHUNK, sample_ct), dtype=np.int32)
    with BITMAP.open("wb") as out:
        for lo in range(0, variant_ct, CHUNK):
            hi = min(lo + CHUNK, variant_ct)
            r.read_range(lo, hi, buf[: hi - lo])
            out.write(np.packbits(buf[: hi - lo] > 0, axis=1).tobytes())
    return time.perf_counter() - start


def main() -> None:
    PGEN_PREFIX.parent.mkdir(parents=True, exist_ok=True)
    # A rerun keeps each output that is no older than what it is made from, with its saved build time.
    saved = load("pgen") or {}
    pgen_file = PGEN_PREFIX.with_suffix(".pgen")
    king = PGEN_PREFIX.with_name("king")
    result: dict[str, Any] = {"machine": machine(), "repeats": REPEATS}
    # pvar-cols=cm keeps the .pvar to its required columns (and an all-zero CM): the
    # panel's INFO, which plink2 would otherwise copy, is not in the Parquet table either.
    result["build_seconds"] = built(
        pgen_file,
        VCF,
        "build_seconds",
        saved,
        lambda: plink2("--vcf", str(VCF), "--make-pgen", "pvar-cols=cm", "--out", str(PGEN_PREFIX)),
    )
    result["bytes"] = {ext: size(PGEN_PREFIX.with_suffix(f".{ext}")) for ext in ("pgen", "pvar", "psam")}
    result["king_seconds"] = built(
        king.with_suffix(".king.bin"),
        pgen_file,
        "king_seconds",
        saved,
        lambda: plink2("--pfile", str(PGEN_PREFIX), "--make-king", "triangle", "bin", "--out", str(king)),
    )
    result["king_bytes"] = size(king.with_suffix(".king.bin"))

    keys, load_seconds = pvar_keys()
    result["variant_index_load_seconds"] = round(load_seconds, 2)
    # truth.questions() refuses a question about a duplicated key, so a map is safe for them.
    index = {key: i for i, key in enumerate(keys)}
    names = truth.sample_names()
    n_samples = len(names)
    result["samples"] = n_samples
    pgen = str(f"{PGEN_PREFIX}.pgen").encode()
    result["bitmap_build_seconds"] = built(
        BITMAP, pgen_file, "bitmap_build_seconds", saved, lambda: build_bitmap(pgen, len(keys), n_samples)
    )
    result["bitmap_bytes"] = size(BITMAP)
    mask_bytes = (n_samples + 7) // 8

    answers = truth.answers()
    singles, sets, samples = truth.questions()
    check = Checker()

    def reader(subset: np.ndarray | None = None) -> Any:
        return pgenlib.PgenReader(pgen, sample_subset=subset)

    def bitmap() -> np.ndarray:
        return np.memmap(BITMAP, dtype=np.uint8, mode="r").reshape(-1, mask_bytes)

    def timed(open_file: Any, query: Any) -> tuple[Any, dict[str, Any]]:
        """``query(open_file())``'s last result, and its fresh and warm timings."""
        _, fresh = time_ms(lambda: query(open_file()), REPEATS)
        opened = open_file()
        result, warm = time_ms(lambda: query(opened), REPEATS)
        return result, {"fresh": summarize(fresh), "warm": summarize(warm)}

    def set_bits(mask: np.ndarray) -> np.ndarray:
        """The sample indices whose bit is set in a packed carrier mask."""
        return np.flatnonzero(np.unpackbits(mask)[:n_samples])

    def named(found: np.ndarray) -> set[str]:
        return {names[i] for i in found}

    def indices(vs: list[truth.Variant]) -> np.ndarray:
        return np.array(sorted(index[v.key] for v in vs), dtype=np.uint32)

    def read_one(r: Any, v: truth.Variant) -> tuple[np.ndarray, np.ndarray]:
        """The carriers of ``v`` and their dosages."""
        buf = np.empty(n_samples, dtype=np.int32)
        r.read(np.uint32(index[v.key]), buf)
        found = np.flatnonzero(buf > 0)
        return found, buf[found]

    def read_list(r: Any, vs: list[truth.Variant]) -> np.ndarray:
        idx = indices(vs)
        buf = np.empty((len(idx), n_samples), dtype=np.int32)
        r.read_list(idx, buf)
        return buf

    def read_sample(r: Any) -> tuple[np.ndarray, np.ndarray]:
        """The variants the reader's one sample carries, and its dosages there."""
        n = r.get_variant_ct()
        buf = np.empty((n, 1), dtype=np.int32)
        r.read_range(0, n, buf)
        found = np.flatnonzero(buf[:, 0] > 0)
        return found, buf[found, 0]

    result["carriers"] = []
    for v in singles:
        want = {s: dosage(gt) for s, gt in answers.carriers[v.id].items()}
        (found, dosages), pgen_times = timed(reader, lambda r, v=v: read_one(r, v))
        check(f"carriers {v.id}", {names[i]: int(d) for i, d in zip(found, dosages, strict=True)}, want)
        found, bitmap_times = timed(bitmap, lambda bm, v=v: set_bits(bm[index[v.key]]))
        check(f"carriers {v.id} (bitmap file)", named(found), set(want))
        result["carriers"].append(
            {
                "variant": v.id,
                "kind": v.kind,
                "ac": v.ac,
                "carriers": len(want),
                "pgen": pgen_times,
                "bitmap_file": bitmap_times,
            }
        )
    result["carriers_of_all"] = []
    for name, vs in sets.items():
        want_set = answers.carriers_of_all[name]
        entry: dict[str, Any] = {"set": name, "carriers": len(want_set)}
        found, entry["read_filter"] = timed(reader, lambda r, vs=vs: np.flatnonzero((read_list(r, vs) > 0).all(axis=0)))
        check(f"carriers of all: {name} (read_filter)", named(found), want_set)
        found, entry["masks_at_query"] = timed(
            reader,
            lambda r, vs=vs: set_bits(np.bitwise_and.reduce(np.packbits(read_list(r, vs) > 0, axis=1), axis=0)),
        )
        check(f"carriers of all: {name} (masks_at_query)", named(found), want_set)
        found, entry["bitmap_file"] = timed(
            bitmap, lambda bm, vs=vs: set_bits(np.bitwise_and.reduce(bm[indices(vs)], axis=0))
        )
        check(f"carriers of all: {name} (bitmap_file)", named(found), want_set)
        result["carriers_of_all"].append(entry)
    result["sample"] = []
    for sample in samples:
        want = sorted((vid, dosage(gt)) for vid, gt in answers.variants_of[sample])
        subset = np.array([names.index(sample)], dtype=np.uint32)
        (found, dosages), times = timed(lambda subset=subset: reader(subset), read_sample)
        got = sorted((truth.variant_id(*keys[i]), int(d)) for i, d in zip(found, dosages, strict=True))
        check(f"variants of {sample}", got, want)
        result["sample"].append({"sample": sample, "variants": len(want), **times})
    result["mismatches"] = check.mismatches
    print(save("pgen", result))
    check.exit_on_mismatch()


if __name__ == "__main__":
    main()
