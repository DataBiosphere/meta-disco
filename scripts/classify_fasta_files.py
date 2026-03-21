#!/usr/bin/env python3
"""Fetch FASTA headers from S3 mirror for files needing header inspection.

Headers are cached in data/evidence/fasta/ for:
- Resumability after interruption
- Audit trail of classification evidence
"""

import argparse
import json
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from src.meta_disco.header_classifier import classify_from_fasta_header

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"
EVIDENCE_DIR = Path("data/evidence/fasta")


def get_evidence_path(md5sum: str) -> Path:
    """Get path for cached header evidence file."""
    return EVIDENCE_DIR / md5sum[:2] / f"{md5sum}.json"


def load_cached_header(md5sum: str) -> dict | None:
    """Load cached header if it exists."""
    path = get_evidence_path(md5sum)
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    return None


def save_header_evidence(md5sum: str, file_name: str, contig_names: list[str], raw_bytes: int):
    """Save fetched header as evidence for audit trail."""
    path = get_evidence_path(md5sum)
    path.parent.mkdir(parents=True, exist_ok=True)

    evidence = {
        "md5sum": md5sum,
        "file_name": file_name,
        "contig_names": contig_names,
        "contig_count": len(contig_names),
        "raw_bytes_fetched": raw_bytes,
        "fetch_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(path, "w") as f:
        json.dump(evidence, f, indent=2)


def get_fasta_headers(md5sum: str, file_name: str = "", is_gzipped: bool = True,
                      use_cache: bool = True) -> list[str] | None:
    """
    Read contig names from a FASTA file on S3.

    For gzipped files, fetches first chunk and decompresses.
    Returns list of contig names (from > header lines, without the > prefix).

    Headers are cached in data/evidence/fasta/ for resumability.
    """
    # Check cache first
    if use_cache:
        cached = load_cached_header(md5sum)
        if cached and "contig_names" in cached:
            return cached["contig_names"]

    url = f"{S3_MIRROR_URL}/{md5sum}.md5"

    try:
        # Fetch first 256KB - should contain many contig headers
        headers = {"Range": "bytes=0-262144"}
        resp = requests.get(url, headers=headers, timeout=60)

        if resp.status_code not in [200, 206]:
            return None

        content = resp.content
        raw_bytes = len(content)

        # Decompress if gzipped
        if is_gzipped and content[:2] == b'\x1f\x8b':
            try:
                decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                content = decompressor.decompress(content)
            except zlib.error:
                return None

        # Decode
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')

        # Extract contig names (lines starting with >)
        contig_names = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('>'):
                # Take the first word after > as the contig name
                name = line[1:].split()[0] if line[1:].strip() else line[1:].strip()
                if name:
                    contig_names.append(name)

        # Save to cache (including empty results — valid file with no contigs)
        save_header_evidence(md5sum, file_name, contig_names, raw_bytes)

        return contig_names

    except requests.Timeout:
        print(f"Timeout reading FASTA for {md5sum}")
        return None
    except Exception as e:
        print(f"Error reading FASTA for {md5sum}: {e}")
        return None


def classify_single_fasta(
    md5sum: str,
    file_name: str = "",
    file_size: int | None = None,
    is_gzipped: bool = True,
    use_cache: bool = True,
) -> dict | None:
    """Fetch headers and classify a single FASTA file by MD5."""
    contig_names = get_fasta_headers(md5sum, file_name, is_gzipped, use_cache=use_cache)
    if contig_names is None:
        return None

    full = classify_from_fasta_header(contig_names, file_name)

    return {
        "file_name": file_name,
        "md5sum": md5sum,
        "file_size": file_size,
        "classifications": full,
    }


def process_single_record(record: dict, resume: bool) -> tuple[dict | None, bool]:
    """Process a single FASTA record. Returns (classification, was_cached)."""
    md5 = record.get("file_md5sum")
    file_name = record.get("file_name", "")
    file_size = record.get("file_size")
    file_format = record.get("file_format", "")
    entry_id = record.get("entry_id")

    is_gzipped = file_name.endswith(".gz") or file_format.endswith(".gz")

    was_cached = load_cached_header(md5) is not None

    result = classify_single_fasta(md5, file_name, file_size=file_size,
                                    is_gzipped=is_gzipped, use_cache=resume)

    if result:
        result["entry_id"] = entry_id
        result["original_record"] = {
            "file_format": file_format,
            "file_size": file_size,
            "dataset_title": record.get("dataset_title"),
        }
        result["from_cache"] = was_cached
        return result, was_cached

    return None, was_cached


def process_fasta_files(input_path: Path, output_path: Path, limit: int | None = None,
                        resume: bool = True, workers: int = 1, skip_complete: bool = False,
                        skip_cached: bool = False):
    """Process FASTA files that need header inspection."""

    with open(input_path) as f:
        if input_path.suffix == ".ndjson":
            results = [json.loads(line) for line in f if line.strip()]
        else:
            data = json.load(f)
            results = data.get("results", data.get("files", data))

    fasta_extensions = [".fasta", ".fasta.gz", ".fa", ".fa.gz"]
    needs_inspection = [
        r for r in results
        if r.get("file_md5sum")
        and any(r.get("file_format", "").endswith(ext) or r.get("file_name", "").endswith(ext)
                for ext in fasta_extensions)
        and not r.get("skip")
    ]

    if skip_complete and output_path.exists():
        try:
            with open(output_path) as f:
                existing = json.load(f)
            existing_count = len(existing.get("classifications", []))
            if existing.get("metadata", {}).get("complete") and existing_count >= len(needs_inspection):
                print(f"Output already complete with {existing_count} classifications. Skipping.")
                return
        except (json.JSONDecodeError, IOError):
            pass

    print(f"Found {len(needs_inspection)} FASTA files with MD5 for header inspection")

    cached_count = sum(1 for r in needs_inspection
                       if load_cached_header(r.get("file_md5sum")) is not None)
    print(f"  Already cached: {cached_count}")
    print(f"  Remaining to fetch: {len(needs_inspection) - cached_count}")

    if skip_cached and cached_count > 0:
        needs_inspection = [r for r in needs_inspection
                          if load_cached_header(r.get("file_md5sum")) is None]
        print(f"  Skipping cached files, processing only {len(needs_inspection)} new files")

    if limit:
        needs_inspection = needs_inspection[:limit]
        print(f"Processing first {limit} files")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    writer = NdjsonWriter(output_path)

    successful = 0
    failed = 0
    from_cache = 0
    processed = 0

    lock = Lock()

    print(f"Using {workers} parallel workers")

    def update_progress(result, was_cached, file_name):
        nonlocal successful, failed, from_cache, processed
        with lock:
            processed += 1
            if result:
                writer.write(result)
                successful += 1
                if was_cached:
                    from_cache += 1
            else:
                failed += 1

            cache_indicator = "[cached] " if was_cached else ""
            print(f"\r[{processed}/{len(needs_inspection)}] {cache_indicator}{file_name[:45]:<52}", end="", flush=True)

    if workers == 1:
        for record in needs_inspection:
            result, was_cached = process_single_record(record, resume)
            update_progress(result, was_cached, record.get("file_name", ""))
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_record = {
                executor.submit(process_single_record, record, resume): record
                for record in needs_inspection
            }

            for future in as_completed(future_to_record):
                record = future_to_record[future]
                try:
                    result, was_cached = future.result()
                    update_progress(result, was_cached, record.get("file_name", ""))
                except Exception as e:
                    print(f"\nError processing {record.get('file_name')}: {e}")
                    with lock:
                        processed += 1
                        failed += 1

    print(f"\n\nSuccessfully classified: {successful}")
    print(f"  From cache: {from_cache}")
    print(f"  New fetches: {successful - from_cache}")
    print(f"Failed to fetch header: {failed}")

    writer.close()
    save_final(output_path, len(needs_inspection), successful, failed, from_cache)

    print(f"\nSaved to {output_path}")
    print(f"Evidence cached in: {EVIDENCE_DIR}/")


def _ndjson_path(output_path: Path) -> Path:
    return output_path.with_suffix(".ndjson")


class NdjsonWriter:
    def __init__(self, output_path: Path):
        self.path = _ndjson_path(output_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w")
        self._count = 0

    def write(self, record: dict):
        self._fh.write(json.dumps(record) + "\n")
        self._count += 1
        if self._count % 500 == 0:
            self._fh.flush()

    def close(self):
        self._fh.flush()
        self._fh.close()


def save_final(output_path: Path, total: int, successful: int, failed: int, from_cache: int):
    ndjson = _ndjson_path(output_path)
    classifications = []
    if ndjson.exists():
        with open(ndjson) as f:
            for line in f:
                if line.strip():
                    classifications.append(json.loads(line))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_to_process": total,
                "processed": successful + failed,
                "successful": successful,
                "failed": failed,
                "from_cache": from_cache,
                "complete": True,
            },
            "classifications": classifications,
        }, f, indent=2)
    if ndjson.exists():
        ndjson.unlink()


def main():
    parser = argparse.ArgumentParser(description="Fetch FASTA headers and classify")
    parser.add_argument("--input", "-i", type=str,
                        help="Input file (classification JSON or metadata NDJSON)")
    parser.add_argument("--output", "-o", type=str, default="output/fasta_classifications.json",
                        help="Output file for classifications")
    parser.add_argument("--limit", "-l", type=int, default=None,
                        help="Limit number of files to process")
    parser.add_argument("--md5", type=str,
                        help="Classify a single file by MD5 hash")
    parser.add_argument("--filename", type=str, default="",
                        help="Filename for single-file classification (used with --md5)")
    parser.add_argument("--no-gzip", action="store_true",
                        help="File is not gzipped (default: assume gzipped)")
    parser.add_argument("--no-resume", action="store_true",
                        help="Don't use cached headers, re-fetch all")
    parser.add_argument("--workers", "-w", type=int, default=10,
                        help="Number of parallel workers (default: 10)")
    parser.add_argument("--skip-complete", action="store_true",
                        help="Skip if output file already has all files classified")
    parser.add_argument("--skip-cached", action="store_true",
                        help="Skip files entirely if header is already cached (no re-analysis)")
    args = parser.parse_args()

    if args.md5:
        is_gzipped = not args.no_gzip
        print(f"Classifying FASTA with MD5: {args.md5} (gzipped={is_gzipped})")
        result = classify_single_fasta(args.md5, file_name=args.filename, is_gzipped=is_gzipped)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Failed to fetch or classify FASTA")
        return

    if not args.input:
        parser.error("--input required unless using --md5")

    process_fasta_files(
        Path(args.input),
        Path(args.output),
        args.limit,
        resume=not args.no_resume,
        workers=args.workers,
        skip_complete=args.skip_complete,
        skip_cached=args.skip_cached
    )


if __name__ == "__main__":
    main()
