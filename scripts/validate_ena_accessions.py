#!/usr/bin/env python3 -u
"""Validate FASTQ classifications against ENA metadata.

Cross-references our platform and modality classifications with the
authoritative ENA (European Nucleotide Archive) metadata.

Usage:
    python scripts/validate_ena_accessions.py

Output saved to: output/ena_validation_results.json
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.meta_disco.header_classifier import classify_from_fastq_header

ENA_API = "https://www.ebi.ac.uk/ena/portal/api/filereport"
FIELDS = "run_accession,instrument_platform,library_strategy,library_source"


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
        return dict(zip(headers, values))
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
    with open(input_path) as f:
        data = json.load(f)

    classifications = data.get("classifications", data)
    with_acc = [c for c in classifications if c.get("archive_accession")]

    print(f"Found {len(with_acc):,} files with ENA accessions", flush=True)

    if limit:
        with_acc = with_acc[:limit]
        print(f"Limiting to first {limit} files", flush=True)

    print(f"Using {workers} parallel workers", flush=True)

    # Results tracking
    results = {
        "platform_match": 0,
        "platform_mismatch": 0,
        "modality_match": 0,
        "modality_mismatch": 0,
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
        """Process a single record and return validation result."""
        acc = rec["archive_accession"]
        sample_reads = rec.get("sample_reads", [])
        file_name = rec.get("file_name", "")

        # Re-classify with current rules
        if sample_reads:
            new_class = classify_from_fastq_header(sample_reads, file_name=file_name)
            our_platform = (new_class.get("platform") or "").upper()
            our_modality = new_class.get("data_modality") or ""
        else:
            our_platform = (rec.get("platform") or "").upper()
            our_modality = rec.get("data_modality") or ""

        # Fetch ENA metadata
        ena = fetch_ena_metadata(acc)
        if not ena:
            return {"error": True, "accession": acc, "file": file_name, "reason": "api_failed"}

        ena_platform = (ena.get("instrument_platform") or "").upper()
        ena_source = ena.get("library_source") or ""
        ena_strategy = ena.get("library_strategy") or ""

        if not ena_platform:
            return {"error": True, "accession": acc, "file": file_name, "reason": "no_platform"}

        # Validate
        platform_match = our_platform == ena_platform
        expected_modality = "transcriptomic" if (
            ena_source == "TRANSCRIPTOMIC" or
            ena_strategy in ["RNA-Seq", "FL-cDNA"]
        ) else "genomic"
        modality_match = our_modality and our_modality.startswith(expected_modality)

        result = {
            "error": False,
            "platform_match": platform_match,
            "modality_match": modality_match,
        }

        if not platform_match:
            result["platform_mismatch"] = {
                "accession": acc,
                "file": file_name,
                "type": "platform",
                "ours": our_platform or "(empty)",
                "ena": ena_platform,
            }

        if not modality_match:
            result["modality_mismatch"] = {
                "accession": acc,
                "file": file_name,
                "type": "modality",
                "ours": our_modality or "(empty)",
                "ena_source": ena_source,
                "ena_strategy": ena_strategy,
                "expected": expected_modality,
            }

        return result

    # Process in parallel
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_record, rec): rec for rec in with_acc}

        for future in as_completed(futures):
            completed += 1
            result = future.result()

            if result.get("error"):
                results["api_errors"] += 1
                api_errors.append({
                    "accession": result.get("accession"),
                    "file": result.get("file"),
                    "reason": result.get("reason"),
                })
            else:
                results["total_validated"] += 1
                if result["platform_match"]:
                    results["platform_match"] += 1
                else:
                    results["platform_mismatch"] += 1
                    if result.get("platform_mismatch"):
                        mismatches.append(result["platform_mismatch"])

                if result["modality_match"]:
                    results["modality_match"] += 1
                else:
                    results["modality_mismatch"] += 1
                    if result.get("modality_mismatch"):
                        mismatches.append(result["modality_mismatch"])

            # Progress update
            progress_interval = 10 if len(with_acc) <= 100 else 100
            if completed % progress_interval == 0 or completed == len(with_acc):
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (len(with_acc) - completed) / rate if rate > 0 else 0

                n = results["total_validated"]
                if n > 0:
                    plat_pct = 100 * results["platform_match"] / n
                    mod_pct = 100 * results["modality_match"] / n
                else:
                    plat_pct = mod_pct = 0

                print(
                    f"\r[{completed:,}/{len(with_acc):,}] "
                    f"{rate:.1f}/sec | "
                    f"Platform: {plat_pct:.1f}% | "
                    f"Modality: {mod_pct:.1f}% | "
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
    print(f"Time elapsed:                   {elapsed:.1f}s ({len(with_acc)/elapsed:.1f} files/sec)")
    print()

    if n > 0:
        plat_pct = 100 * results["platform_match"] / n
        mod_pct = 100 * results["modality_match"] / n
        print(f"PLATFORM ACCURACY:  {results['platform_match']:,}/{n:,} ({plat_pct:.2f}%)")
        print(f"MODALITY ACCURACY:  {results['modality_match']:,}/{n:,} ({mod_pct:.2f}%)")

    if results["platform_mismatch"] > 0:
        print(f"\nPlatform mismatches: {results['platform_mismatch']:,}")
    if results["modality_mismatch"] > 0:
        print(f"Modality mismatches: {results['modality_mismatch']:,}")

    # Show sample mismatches
    platform_mismatches = [m for m in mismatches if m["type"] == "platform"]
    modality_mismatches = [m for m in mismatches if m["type"] == "modality"]

    if platform_mismatches:
        print("\nSample platform mismatches (first 10):")
        for m in platform_mismatches[:10]:
            print(f"  {m['accession']}: ours={m['ours']} vs ENA={m['ena']}")

    if modality_mismatches:
        print("\nSample modality mismatches (first 10):")
        for m in modality_mismatches[:10]:
            print(f"  {m['accession']}: ours={m['ours']} vs ENA={m['ena_source']}/{m['ena_strategy']}")

    print("=" * 60)

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_files": len(with_acc),
                "validated": n,
                "api_errors": results["api_errors"],
                "elapsed_seconds": elapsed,
            },
            "results": results,
            "mismatches": mismatches,
            "api_errors": api_errors,
        }, f, indent=2)

    print(f"\nResults saved to: {output_path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Validate FASTQ classifications against ENA metadata"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=Path("output/fastq_classifications.json"),
        help="Input FASTQ classifications file",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("output/ena_validation_results.json"),
        help="Output validation results file",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=None,
        help="Limit number of files to validate (for testing)",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=10,
        help="Number of parallel workers (default: 10)",
    )
    args = parser.parse_args()

    validate_against_ena(
        args.input,
        args.output,
        limit=args.limit,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
