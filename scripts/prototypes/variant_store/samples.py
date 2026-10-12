# /// script
# requires-python = ">=3.10"
# dependencies = ["duckdb==1.5.5"]
# ///
"""Build the stand-in sample table and time carrier queries joined to it (#663).

The sample table is a hand-made stand-in for the subject/sample graph: each panel
sample's sex, population and superpopulation from the 1000 Genomes pedigree, and the
AnVIL datasets holding a file whose name carries the sample's id, matched in the prod
input (``data/anvil/prod/anvil_files_metadata.ndjson``). "Has RNA-seq" is read as "named
in a file of AnVIL_MAGE" and "has long reads" as "named in a file of ANVIL_HPRC or
AnVIL_HPRC_R2"; both are what the file names say, not a classification.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

import duckdb
import truth
from common import GENOTYPES, PARQUET_OPTIONS, PEDIGREE, PROD_INPUT, SAMPLES, Checker, machine, save, size
from duck import measure, modes

RNA_SEQ = ["AnVIL_MAGE"]
LONG_READS = ["ANVIL_HPRC", "AnVIL_HPRC_R2"]
SAMPLE_ID = re.compile(r"(?<![A-Za-z0-9])((?:HG|NA)\d{5})(?!\d)")


def datasets_by_sample(panel: set[str]) -> dict[str, list[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    with PROD_INPUT.open() as f:
        for line in f:
            record = json.loads(line)
            for sample in SAMPLE_ID.findall(record.get("file_name") or ""):
                if sample in panel:
                    found[sample].add(record["dataset_title"])
    return {s: sorted(ds) for s, ds in found.items()}


def build() -> dict[str, list[str]]:
    panel = set(truth.sample_names())
    datasets = datasets_by_sample(panel)
    rows = []
    for line in PEDIGREE.read_text().splitlines()[1:]:
        _, sample, _, _, sex, population, superpopulation = line.split()
        if sample in panel:
            rows.append((sample, int(sex), population, superpopulation, datasets.get(sample, [])))
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE samples (sample VARCHAR, sex INTEGER, population VARCHAR, superpopulation VARCHAR, datasets VARCHAR[])"
    )
    con.executemany("INSERT INTO samples VALUES (?, ?, ?, ?, ?)", rows)
    con.execute(f"COPY samples TO '{SAMPLES}' ({PARQUET_OPTIONS})")
    return {sample: ds for sample, _, _, _, ds in rows}


def joined_sql(genotypes: str, samples: str, vs: list[truth.Variant], wanted: list[str]) -> str:
    positions = ", ".join(str(v.pos) for v in vs)
    ids = ", ".join(f"'{v.id}'" for v in vs)
    wanted_list = ", ".join(f"'{d}'" for d in wanted)
    return f"""
        SELECT g.sample, any_value(s.population)
        FROM read_parquet('{genotypes}') g JOIN read_parquet('{samples}') s USING (sample)
        WHERE g.chrom = '{truth.CHROM}' AND g.pos IN ({positions}) AND g.variant_id IN ({ids})
          AND list_has_any(s.datasets, [{wanted_list}])
        GROUP BY g.sample HAVING count(*) = {len(vs)}
    """


def main() -> None:
    table = build()
    answers = truth.answers()
    singles, sets, _ = truth.questions()
    common_sv = max((v for v in singles if v.kind == "SV"), key=lambda v: v.ac)
    first_set_name, first_set = next(iter(sets.items()))
    questions = [
        (f"carriers of {common_sv.id} with RNA-seq", [common_sv], set(answers.carriers[common_sv.id]), RNA_SEQ),
        (
            f"carriers of all of '{first_set_name}' with long reads",
            first_set,
            answers.carriers_of_all[first_set_name],
            LONG_READS,
        ),
    ]
    result: dict[str, Any] = {
        "machine": machine(),
        "samples": len(table),
        "samples_by_dataset": {
            d: sum(d in ds for ds in table.values()) for d in sorted({d for ds in table.values() for d in ds})
        },
        "samples_bytes": size(SAMPLES),
        "joins": [],
    }
    check = Checker()
    for label, vs, carriers, wanted in questions:
        want = {s for s in carriers if set(table.get(s, [])) & set(wanted)}
        entry: dict[str, Any] = {"question": label, "carriers": len(carriers), "answer": len(want)}
        for mode, source in modes():
            m = measure(joined_sql(source(GENOTYPES), source(SAMPLES), vs, wanted), source, f"{label} ({mode})")
            # A capped run (rows None) has no answer to check; the report shows it as capped.
            if (rows := m.pop("rows")) is not None:
                check(f"{label} ({mode})", {r[0] for r in rows}, want)
            entry[mode] = m
        result["joins"].append(entry)
    result["mismatches"] = check.mismatches
    print(save("samples", result))
    check.exit_on_mismatch()


if __name__ == "__main__":
    main()
