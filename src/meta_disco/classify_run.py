"""The single classification run — shared by every source.

A source (AnVIL, HPRC, …) maps its native metadata into the meta-disco record shape and
calls :func:`run_all_classifications`; there is no per-source classifier. This module holds
the orchestration — Phase 1 (header types + the non-header scripts), Phase 2 (index
inheritance), Phase 3 (the remaining catch-all). ``scripts/rerun_all_classifications.py``
(AnVIL) and ``scripts/classify_hprc_files.py`` (HPRC) are thin CLI wrappers over it, so the
shared path lives in the package alongside the rest of the pipeline rather than being
imported across scripts.
"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from meta_disco.file_types import FILE_TYPE_REGISTRY

# This module is <root>/src/meta_disco/classify_run.py; the classifier scripts it shells
# out to live at <root>/scripts/, so the subprocess cwd is the repo root three levels up.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Phase 1 classifiers that are NOT header-based, so they have their own script
# rather than a FILE_TYPE_REGISTRY entry.
NON_HEADER_JOBS = (
    ("classify_bed_files.py", "bed_classifications.json"),
    ("classify_images.py", "image_classifications.json"),
    ("classify_auxiliary_genomic.py", "auxiliary_classifications.json"),
)


def build_parallel_jobs(
    metadata: Path, output_dir: Path, evidence_base: Path, workers: int | None = None
) -> list[tuple]:
    """Phase 1 jobs: one per header-based file type, plus the non-header scripts.

    The header jobs are derived from FILE_TYPE_REGISTRY rather than hand-listed,
    so registering a new file type cannot silently skip production. That is what
    happened to `gfa` in #151: it was added to the registry and to nothing else,
    so `make classify` never invoked it and graph files fell through to the
    filename-only Phase 3 catch-all.

    ``evidence_base`` is the per-source header cache root (``data/evidence/anvil`` for
    AnVIL, ``data/evidence/hprc`` for HPRC) and ``workers`` (when set) the header-fetch
    concurrency; both are passed only to the header jobs — the ones that fetch headers.
    The non-header scripts take neither: image/auxiliary classify from the filename, and
    bed reads a *separate* pre-fetched coordinate-evidence cache (hardcoded to the AnVIL
    dir today, not this ``evidence_base`` — see #279).

    Every output filename here must also appear in output_utils.CLASSIFICATION_FILES
    or the reports will not read it — pinned by tests/test_orchestration.py.
    """
    header_args = ["--evidence-base", str(evidence_base)]
    if workers is not None:
        header_args += ["-w", str(workers)]
    jobs = [
        (
            "classify_headers.py",
            output_dir / f"{ftype}_classifications.json",
            ["--type", ftype, "--input", str(metadata), *header_args],
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

    result = subprocess.run(cmd, cwd=_REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {script_name} failed with code {result.returncode}")
        if result.stderr:
            print(f"  stderr: {result.stderr[-500:]}")
        return script_name, False
    print(f"  Done: {script_name}")
    return script_name, True


def run_all_classifications(
    metadata: Path, output_dir_base: Path, evidence_base: Path, workers: int | None = None
) -> bool:
    """Run the full classification pipeline over one meta-disco metadata file.

    This is the single classification path shared by every source. A source (AnVIL,
    HPRC, …) maps its native metadata into the meta-disco record shape and calls this;
    there is no per-source classifier. It writes a timestamped run dir under
    ``output_dir_base`` and caches header evidence under ``evidence_base``, running
    Phase 1 (header types + non-header scripts), Phase 2 (index inheritance), and
    Phase 3 (the remaining catch-all). ``workers`` sets the header-fetch concurrency
    (``None`` = the pipeline default). Returns True only if every phase succeeded.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_dir_base / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Re-running classifications with timestamp: {timestamp}")
    print(f"Output directory: {output_dir}")
    print(f"Evidence cache: {evidence_base}")

    parallel_jobs = build_parallel_jobs(metadata, output_dir, evidence_base, workers)

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
            ["--metadata", str(metadata), "--classifications", *[str(p) for p in all_classification_files]],
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
            ["--metadata", str(metadata), "--classifications", *[str(p) for p in all_classification_files]],
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

    return success
