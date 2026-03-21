#!/usr/bin/env python3
"""Re-run all classification scripts with timestamped output.

Uses cached headers from previous runs and applies updated classification rules.
Runs independent classifiers in parallel for speed.
"""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path


def run_script(script_name: str, output_path: Path, extra_args: list[str] = None):
    """Run a classification script."""
    cmd = [sys.executable, f"scripts/{script_name}", "--output", str(output_path)]
    if extra_args:
        cmd.extend(extra_args)

    print(f"  Starting: {script_name}")

    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent,
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {script_name} failed with code {result.returncode}")
        if result.stderr:
            print(f"  stderr: {result.stderr[-500:]}")
        return script_name, False
    print(f"  Done: {script_name}")
    return script_name, True


def main():
    parser = argparse.ArgumentParser(description="Re-run all classification scripts")
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("output"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--metadata", "-m",
        type=Path,
        default=Path("data/anvil_files_metadata.json"),
        help="Source metadata file (JSON format)",
    )
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Re-running classifications with timestamp: {timestamp}")
    print(f"Output directory: {output_dir}")

    # Phase 1: Run 6 independent classifiers in parallel
    parallel_jobs = [
        ("fetch_bam_headers.py", output_dir / "bam_classifications.json",
         ["--input", str(args.metadata)]),
        ("fetch_vcf_headers.py", output_dir / "vcf_classifications.json",
         ["--input", str(args.metadata)]),
        ("fetch_fastq_headers.py", output_dir / "fastq_classifications.json",
         ["--input", str(args.metadata)]),
        ("classify_bed_files.py", output_dir / "bed_classifications.json",
         ["--metadata", str(args.metadata)]),
        ("classify_images.py", output_dir / "image_classifications.json",
         ["--metadata", str(args.metadata)]),
        ("classify_auxiliary_genomic.py", output_dir / "auxiliary_classifications.json",
         ["--metadata", str(args.metadata)]),
        ("fetch_fasta_headers.py", output_dir / "fasta_classifications.json",
         ["--input", str(args.metadata)]),
    ]

    print(f"\nPhase 1: Running {len(parallel_jobs)} classifiers in parallel...")
    success = True
    with ThreadPoolExecutor(max_workers=len(parallel_jobs)) as executor:
        futures = {
            executor.submit(run_script, name, path, extra): name
            for name, path, extra in parallel_jobs
        }
        for future in as_completed(futures):
            script_name, ok = future.result()
            success &= ok

    # Phase 2: Index propagation (depends on BAM + VCF from phase 1)
    print(f"\nPhase 2: Propagating index metadata...")
    _, ok = run_script(
        "propagate_index_metadata.py",
        output_dir / "index_classifications.json",
        [
            "--metadata", str(args.metadata),
            "--bam", str(output_dir / "bam_classifications.json"),
            "--vcf", str(output_dir / "vcf_classifications.json"),
        ]
    )
    success &= ok

    print(f"\n{'='*70}")
    if success:
        print(f"All classifications complete!")
        print(f"Results saved to: {output_dir}/")
    else:
        print("Some classifications failed - check output above")
    print("="*70)

    # List output files
    print("\nOutput files:")
    for f in sorted(output_dir.glob("*.json")):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name}: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
