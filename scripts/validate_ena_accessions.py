#!/usr/bin/env python3 -u
"""Validate stored FASTQ classifications against ENA metadata.

Cross-references the classification output with the European Nucleotide
Archive record for every FASTQ whose name carries a run accession
([ESD]RRnnnnnn), which the join also verifies resolves.

What each comparison means today (#330):
- platform — the meaningful check: our value is byte-derived (read-name
  grammar), ENA's is submitter-declared; two independent routes to the
  same fact.
- modality / assay — reported, but expected to score unknown-by-design
  under current rules: FASTQ modality/assay is not recoverable from
  content (the content ceiling), so our side is a sentinel. The
  comparisons are wired now so they activate once import work fills
  those dimensions.
- Circularity rule: ENA may only validate modality/assay values that
  were imported from a DIFFERENT source (e.g. the HPRC Catalog or a
  study's methods paper) — never values imported from ENA itself.

Usage:
    python scripts/validate_ena_accessions.py -i output/anvil/<run>/fastq_classifications.json

Output saved to: output/anvil/ena_validation_results.json
"""

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from meta_disco.output_utils import find_latest_run
from meta_disco.validation_maps import ENA_LIBRARY_STRATEGY_MAP

ENA_API = "https://www.ebi.ac.uk/ena/portal/api/filereport"
FIELDS = "run_accession,instrument_platform,library_strategy,library_source"
# No trailing \b: names like ERR3988887_1.fastq.gz put a word character
# (the underscore) right after the digits, which \b rejects.
ACCESSION_RE = re.compile(r"\b([ESD]RR\d{6,})(?!\d)")
_SENTINEL_STATUSES = {"not_classified", "not_applicable", "conflict"}


def extract_accession(rec: dict) -> str | None:
    """The record's run accession: the stored field, else parsed from file_name."""
    acc = rec.get("archive_accession")
    if acc:
        return str(acc)
    m = ACCESSION_RE.search(str(rec.get("file_name") or ""))
    return m.group(1) if m else None


def our_field(rec: dict, field: str) -> tuple[str, str]:
    """(value, status) for one dimension, tolerating the legacy flat shape."""
    c = rec.get("classifications")
    if isinstance(c, dict):
        f = c.get(field) or {}
        status = f.get("status") or ""
        value = f.get("value") or ""
        return str(value), str(status)
    value = rec.get(field) or ""
    return str(value), ("classified" if value else "")


def fetch_ena_metadata(acc: str) -> dict | None:
    """Fetch metadata for a single accession from ENA API."""
    try:
        resp = requests.get(
            ENA_API,
            params={"accession": acc, "result": "read_run", "fields": FIELDS},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        lines = resp.text.strip().split("\n")
        if len(lines) < 2:
            return None
        headers = lines[0].split("\t")
        values = lines[1].split("\t")
        return dict(zip(headers, values, strict=True))
    except (requests.RequestException, ValueError):
        return None


def validate_against_ena(
    input_path: Path,
    output_path: Path,
    limit: int | None = None,
    workers: int = 10,
):
    """Validate FASTQ classifications against ENA metadata."""

    # Load classifications
    print(f"Loading classifications from {input_path}...")
    with input_path.open() as f:
        data = json.load(f)

    classifications = data.get("classifications", data)
    with_acc = [c for c in classifications if isinstance(c, dict) and extract_accession(c)]

    print(f"Found {len(with_acc):,} files with ENA accessions", flush=True)

    if limit:
        with_acc = with_acc[:limit]
        print(f"Limiting to first {limit} files", flush=True)

    print(f"Using {workers} parallel workers", flush=True)

    # Results tracking. "unknown" = our side is a sentinel (nothing committed),
    # excluded from both match and mismatch (#330; same policy direction as #329).
    results = {
        "platform_match": 0,
        "platform_mismatch": 0,
        "platform_unknown": 0,
        "modality_match": 0,
        "modality_mismatch": 0,
        "modality_unknown": 0,
        "assay_match": 0,
        "assay_mismatch": 0,
        "assay_unknown": 0,
        "api_errors": 0,
        "total_validated": 0,
    }
    mismatches = []
    api_errors = []

    print()
    print("Validating against ENA API...")
    print("-" * 60)

    start_time = time.time()
    completed = 0

    def process_record(rec):
        """Compare one stored record against its ENA run record.

        Per-dimension verdicts are "match" / "mismatch" / "unknown" — unknown
        when our side is a sentinel, or (assay only) when ENA's strategy has
        no mapping into our vocabulary.
        """
        acc = extract_accession(rec)
        file_name = str(rec.get("file_name") or "")
        if not acc:  # with_acc filtering makes this unreachable; guards the type
            return {"error": True, "accession": None, "file": file_name, "reason": "no_accession"}

        ena = fetch_ena_metadata(acc)
        if not ena:
            return {"error": True, "accession": acc, "file": file_name, "reason": "api_failed"}

        ena_platform = (ena.get("instrument_platform") or "").upper()
        ena_source = ena.get("library_source") or ""
        ena_strategy = ena.get("library_strategy") or ""

        if not ena_platform:
            return {"error": True, "accession": acc, "file": file_name, "reason": "no_platform"}

        result: dict = {"error": False}

        def verdict(dim: str, ours: str, status: str, expected: str | None, detail: dict) -> None:
            if not ours or status in _SENTINEL_STATUSES or status == "":
                result[dim] = "unknown"
                return
            if expected is None:
                result[dim] = "unknown"  # nothing comparable on the ENA side
                return
            matched = ours == expected if dim != "modality" else ours.startswith(expected)
            result[dim] = "match" if matched else "mismatch"
            if not matched:
                result[f"{dim}_detail"] = {
                    "accession": acc,
                    "file": file_name,
                    "type": dim,
                    "ours": ours,
                    **detail,
                }

        our_platform, platform_status = our_field(rec, "platform")
        verdict("platform", our_platform.upper(), platform_status, ena_platform, {"ena": ena_platform})

        expected_modality = (
            "transcriptomic"
            if (ena_source == "TRANSCRIPTOMIC" or ena_strategy in ["RNA-Seq", "FL-cDNA"])
            else "genomic"
        )
        our_modality, modality_status = our_field(rec, "data_modality")
        verdict(
            "modality",
            our_modality,
            modality_status,
            expected_modality,
            {"ena_source": ena_source, "ena_strategy": ena_strategy, "expected": expected_modality},
        )

        # Dormant until import fills assay (#330): activates the moment our
        # side holds concrete values. Circularity rule in the module docstring.
        our_assay, assay_status = our_field(rec, "assay_type")
        expected_assay = ENA_LIBRARY_STRATEGY_MAP.get(ena_strategy)
        verdict(
            "assay",
            our_assay,
            assay_status,
            expected_assay,
            {"ena_strategy": ena_strategy, "expected": expected_assay},
        )

        return result

    # Process in parallel
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_record, rec): rec for rec in with_acc}

        for future in as_completed(futures):
            completed += 1
            result = future.result()

            if result.get("error"):
                results["api_errors"] += 1
                api_errors.append(
                    {
                        "accession": result.get("accession"),
                        "file": result.get("file"),
                        "reason": result.get("reason"),
                    }
                )
            else:
                results["total_validated"] += 1
                for dim in ("platform", "modality", "assay"):
                    results[f"{dim}_{result[dim]}"] += 1
                    detail = result.get(f"{dim}_detail")
                    if detail:
                        mismatches.append(detail)

            # Progress update
            progress_interval = 10 if len(with_acc) <= 100 else 100
            if completed % progress_interval == 0 or completed == len(with_acc):
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (len(with_acc) - completed) / rate if rate > 0 else 0

                scored = results["platform_match"] + results["platform_mismatch"]
                plat_pct = 100 * results["platform_match"] / scored if scored else 0

                print(
                    f"\r[{completed:,}/{len(with_acc):,}] "
                    f"{rate:.1f}/sec | "
                    f"Platform: {plat_pct:.1f}% | "
                    f"ETA: {remaining:.0f}s   ",
                    end="",
                    flush=True,
                )

    elapsed = time.time() - start_time
    n = results["total_validated"]

    print()
    print()
    print("=" * 60)
    print("FULL ENA VALIDATION RESULTS")
    print("=" * 60)
    print(f"Total files with ENA accession: {len(with_acc):,}")
    print(f"Successfully validated:         {n:,}")
    print(f"API errors (no data):           {results['api_errors']:,}")
    print(f"Time elapsed:                   {elapsed:.1f}s ({len(with_acc) / elapsed:.1f} files/sec)")
    print()

    for dim, label in (("platform", "PLATFORM"), ("modality", "MODALITY"), ("assay", "ASSAY")):
        match, mismatch = results[f"{dim}_match"], results[f"{dim}_mismatch"]
        unknown = results[f"{dim}_unknown"]
        scored = match + mismatch
        if scored:
            print(f"{label}: {match:,}/{scored:,} agree ({100 * match / scored:.2f}%), {unknown:,} unknown")
        else:
            print(f"{label}: nothing scored — {unknown:,} unknown (our side uncommitted; see module docstring)")

    # Show sample mismatches per dimension
    for dim in ("platform", "modality", "assay"):
        dim_mismatches = [m for m in mismatches if m["type"] == dim]
        if dim_mismatches:
            print(f"\nSample {dim} mismatches (first 10):")
            for m in dim_mismatches[:10]:
                print(f"  {m['accession']}: ours={m['ours']} vs expected={m.get('expected', m.get('ena'))}")

    print("=" * 60)

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(
            {
                "metadata": {
                    "total_files": len(with_acc),
                    "validated": n,
                    "api_errors": results["api_errors"],
                    "elapsed_seconds": elapsed,
                },
                "results": results,
                "mismatches": mismatches,
                "api_errors": api_errors,
            },
            f,
            indent=2,
        )

    print(f"\nResults saved to: {output_path}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Validate FASTQ classifications against ENA metadata")
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=None,
        help="Input FASTQ classifications file (default: the latest run's fastq_classifications.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("output/anvil/ena_validation_results.json"),
        help="Output validation results file",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Limit number of files to validate (for testing)",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=10,
        help="Number of parallel workers (default: 10)",
    )
    args = parser.parse_args()

    input_path = args.input or find_latest_run(Path("output/anvil")) / "fastq_classifications.json"
    validate_against_ena(
        input_path,
        args.output,
        limit=args.limit,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
