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

from meta_disco.file_types import FILE_TYPE_REGISTRY

# Phase 1 classifiers that are NOT header-based, so they have their own script
# rather than a FILE_TYPE_REGISTRY entry.
NON_HEADER_JOBS = (
    ("classify_bed_files.py", "bed_classifications.json"),
    ("classify_images.py", "image_classifications.json"),
    ("classify_auxiliary_genomic.py", "auxiliary_classifications.json"),
)


def build_parallel_jobs(metadata: Path, output_dir: Path) -> list[tuple]:
    """Phase 1 jobs: one per header-based file type, plus the non-header scripts.

    The header jobs are derived from FILE_TYPE_REGISTRY rather than hand-listed,
    so registering a new file type cannot silently skip production. That is what
    happened to `gfa` in #151: it was added to the registry and to nothing else,
    so `make classify` never invoked it and graph files fell through to the
    filename-only Phase 3 catch-all.

    Every output filename here must also appear in output_utils.CLASSIFICATION_FILES
    or the reports will not read it — pinned by tests/test_orchestration.py.
    """
    jobs = [
        (
            "classify_headers.py",
            output_dir / f"{ftype}_classifications.json",
            ["--type", ftype, "--input", str(metadata)],
        )
        for ftype in FILE_TYPE_REGISTRY
    ]
    jobs += [(script, output_dir / out, ["--metadata", str(metadata)]) for script, out in NON_HEADER_JOBS]
    return jobs


def run_script(script_name: str, output_path: Path, extra_args: list[str] | None = None):
    """Run a classification script."""
    cmd = [sys.executable, f"scripts/{script_name}", "--output", str(output_path)]
    if extra_args:
        cmd.extend(extra_args)

    print(f"  Starting: {script_name}")

    result = subprocess.run(cmd, cwd=Path(__file__).parent.parent, capture_output=True, text=True)
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
        "--output-dir",
        "-o",
        type=Path,
        default=Path("output/anvil"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--metadata",
        "-m",
        type=Path,
        default=Path("data/anvil/anvil_files_metadata.json"),
        help="Source metadata file (JSON format)",
    )
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Re-running classifications with timestamp: {timestamp}")
    print(f"Output directory: {output_dir}")

    parallel_jobs = build_parallel_jobs(args.metadata, output_dir)

    # Track all classification output paths for Phase 3
    all_classification_files = [path for _, path, _ in parallel_jobs]

    print(f"\nPhase 1: Running {len(parallel_jobs)} classifiers in parallel...")
    success = True
    with ThreadPoolExecutor(max_workers=len(parallel_jobs)) as executor:
        futures = {executor.submit(run_script, name, path, extra): name for name, path, extra in parallel_jobs}
        for future in as_completed(futures):
            _script_name, ok = future.result()
            success &= ok

    # Phase 2: Index classification (inherits from parent file classifications)
    index_output = output_dir / "index_classifications.json"
    if not success:
        print("\nPhase 2: SKIPPED — one or more Phase 1 classifiers failed")
    else:
        print("\nPhase 2: Classifying index files...")
        _, ok = run_script(
            "classify_index_files.py",
            index_output,
            [
                "--metadata",
                str(args.metadata),
                "--classifications",
                *[str(p) for p in all_classification_files],
            ],
        )
        success &= ok
        all_classification_files.append(index_output)

    # Phase 3: Catch-all for files not handled by any other classifier
    if not success:
        print("\nPhase 3: SKIPPED — one or more earlier classifiers failed")
    else:
        print("\nPhase 3: Classifying remaining files...")
        _, ok = run_script(
            "classify_remaining_files.py",
            output_dir / "remaining_classifications.json",
            [
                "--metadata",
                str(args.metadata),
                "--classifications",
                *[str(p) for p in all_classification_files],
            ],
        )
        success &= ok

    print(f"\n{'=' * 70}")
    if success:
        print("All classifications complete!")
        print(f"Results saved to: {output_dir}/")
    else:
        print("Some classifications failed - check output above")
    print("=" * 70)

    # List output files
    print("\nOutput files:")
    for f in sorted(output_dir.glob("*.json")):
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name}: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
