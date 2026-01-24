#!/usr/bin/env python3
"""Re-run all classification scripts with timestamped output.

Uses cached headers from previous runs and applies updated classification rules.
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_script(script_name: str, output_path: Path, extra_args: list[str] = None):
    """Run a classification script."""
    cmd = [sys.executable, f"scripts/{script_name}", "--output", str(output_path)]
    if extra_args:
        cmd.extend(extra_args)

    print(f"\n{'='*70}")
    print(f"Running: {script_name}")
    print(f"Output:  {output_path}")
    print("="*70)

    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent)
    if result.returncode != 0:
        print(f"ERROR: {script_name} failed with code {result.returncode}")
        return False
    return True


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

    success = True

    # 1. Classify BED files (fixed maternal pattern bug)
    success &= run_script(
        "classify_bed_files.py",
        output_dir / "bed_classifications.json",
        ["--metadata", str(args.metadata)]
    )

    # 2. Classify image files
    success &= run_script(
        "classify_images.py",
        output_dir / "image_classifications.json",
        ["--metadata", str(args.metadata)]
    )

    # 3. Classify auxiliary genomic files (FAST5, PLINK)
    success &= run_script(
        "classify_auxiliary_genomic.py",
        output_dir / "auxiliary_genomic_classifications.json",
        ["--metadata", str(args.metadata)]
    )

    # 4. Propagate index metadata (uses cached header files)
    success &= run_script(
        "propagate_index_metadata.py",
        output_dir / "index_file_classifications.json",
        [
            "--metadata", str(args.metadata),
            "--bam", "output/bam_headers.json",
            "--vcf", "output/vcf_headers.json",
        ]
    )

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
