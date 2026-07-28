#!/usr/bin/env python3
"""Ingest the HPRC Data Explorer catalogs and classify them with the shared pipeline.

HPRC is a *source*, like AnVIL. This script maps its four GitHub catalogs into the one
**meta-disco record shape** and calls the single classifier
(``meta_disco.classify_run.run_all_classifications``) — there is no HPRC-specific
classification logic. Every source maps its native metadata into that shape and calls
the same path.

AnVIL's own catalog includes the HPRC dataset, and the HPRC Data Explorer's metadata is
richer ground truth, so classifying the HPRC catalogs and comparing against them
(``validate_against_hprc.py``) is how we quality-check our calls on the AnVIL HPRC files.

Steps (issue #276):
  1. Load the catalogs (downloaded by ``download_hprc_catalogs.py`` / ``make download-hprc``).
  2. Fill ``file_size`` from S3 (HTTP HEAD) where the catalog omits it — only the
     sequencing-data catalog does; assemblies/alignments/annotations carry ``fileSize``.
  3. Map every record into the meta-disco shape (``file_name``, ``file_format``,
     ``file_md5sum``, ``url``, ``file_size``) and write one metadata file.
  4. Run the shared classifier over it, exactly as AnVIL does.
"""

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from meta_disco.classify_run import run_all_classifications
from meta_disco.fetchers import FetchError, fetch_content_length
from meta_disco.file_name import FileName

# The S3 location field differs per HPRC catalog; each maps to the meta-disco ``url``.
# alignments/annotations also carry it, so every catalog record gets a real content URL.
CATALOG_URL_FIELD = {
    "sequencing-data": "path",
    "assemblies": "awsFasta",
    "alignments": "loc",
    "annotations": "fileLocation",
}


def s3_to_https(s3_path: str) -> str:
    """Convert s3://bucket/key to https://s3-us-west-2.amazonaws.com/bucket/key."""
    if s3_path.startswith("s3://"):
        parts = s3_path[5:]
        return f"https://s3-us-west-2.amazonaws.com/{parts}"
    return s3_path


def path_key(path: str) -> str:
    """Stable cache key hashed from a file's FULL path/url (HPRC catalogs have no md5).

    Keyed on the full path, not the basename: basenames collide across sample
    directories (e.g. two ``…grch38.vcf.gz`` at different paths — 5 such HPRC files),
    which would alias them in the evidence cache; full paths are unique (issue #276).
    Returns a valid lowercase-hex md5, so it satisfies the input contract's
    ``file_md5sum`` pattern and keys the evidence cache like a real md5. The uniform
    ``hash(full path)`` cache key across all sources is the follow-up (#277).
    """
    return hashlib.md5(path.encode()).hexdigest()


def build_metadata_records(catalog: list[dict], url_field: str, *, workers: int) -> list[dict]:
    """Map one HPRC catalog into meta-disco records, S3-HEAD-filling any missing file_size.

    Each record carries the meta-disco fields the classifier reads: ``file_name``,
    ``file_format``, ``file_md5sum`` (synthesized as the cache key — a hash of the full
    path, not the basename, so same-named files at different paths don't collide),
    ``url`` (explicit S3, from the catalog's own location field), and ``file_size``. A
    size the catalog omits is read from S3 in parallel (HEAD); a size that cannot be
    obtained is left ``None`` — never fabricated — so the classifier's contract gate
    marks the file not_classified rather than guessing (issue #276). In practice only
    the sequencing-data catalog lacks ``fileSize``; the others supply it and are never HEADed.
    """
    records = []
    needs_size = []  # records missing a catalog fileSize — filled by S3 HEAD below
    for rec in catalog:
        fn = rec.get("filename", "")
        s3_path = rec.get(url_field, "")
        url = s3_to_https(s3_path) if s3_path else None
        size = rec.get("fileSize")
        record = {
            "file_name": fn,
            # file_format is the parsed core extension from the canonical FileName model
            # (.bam/.cram/.fastq/.fa/.vcf/.gfa …), or "" when the name carries no known
            # extension — never a junk last-dot suffix. The content-fetched types need it
            # for the contract gate; the rest classify from the name via the catch-all.
            "file_format": FileName.parse(fn).extension or "",
            # Cache key = hash of the full path (the unique identity). No location means the
            # file can't be read and can't be keyed, so file_md5sum is left None and the
            # contract gate marks it not_classified — never a fabricated basename key (#276).
            "file_md5sum": path_key(url) if url else None,
            "url": url,
            "file_size": size if isinstance(size, int) else None,
        }
        records.append(record)
        if record["file_size"] is None and url:
            needs_size.append(record)

    if needs_size:
        print(f"Fetching {len(needs_size)} file sizes from S3 (HEAD, {workers} workers)...", flush=True)

        def fill_size(record: dict) -> bool:
            try:
                record["file_size"] = fetch_content_length(record["url"])
                return True
            except FetchError:
                return False  # leave file_size None → the contract gate marks it not_classified

        with ThreadPoolExecutor(max_workers=workers) as executor:
            failed = sum(1 for ok in executor.map(fill_size, needs_size) if not ok)
        if failed:
            print(f"  {failed} size lookups failed — those files are not_classified (size unavailable)")

    return records


def main():
    parser = argparse.ArgumentParser(
        description="Map the HPRC catalogs into the meta-disco shape and run the shared classifier",
    )
    parser.add_argument(
        "--catalog-dir",
        type=Path,
        default=Path("data/hprc"),
        help="Directory containing the downloaded HPRC catalog JSON files",
    )
    parser.add_argument(
        "--metadata-out",
        type=Path,
        default=Path("data/hprc/hprc_files_metadata.json"),
        help="Where to write the mapped meta-disco metadata file (the classifier's input)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/hprc"),
        help="Base output directory for classification run dirs",
    )
    parser.add_argument(
        "--evidence-base",
        type=Path,
        default=Path("data/evidence/hprc"),
        help="Evidence cache base directory for HPRC header fetches",
    )
    parser.add_argument(
        "--limit",
        "-l",
        type=int,
        default=None,
        help="Limit records per catalog (for testing)",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=30,
        help="Parallel workers for the S3 HEAD size lookups and the header fetches",
    )
    args = parser.parse_args()

    all_records = []
    for catalog_name, url_field in CATALOG_URL_FIELD.items():
        catalog_path = args.catalog_dir / f"{catalog_name}.json"
        if not catalog_path.exists():
            print(f"  Skipping {catalog_name} (not found: {catalog_path}); run `make download-hprc` first")
            continue
        with catalog_path.open() as f:
            catalog = json.load(f)
        if args.limit is not None:
            catalog = catalog[: args.limit]
        print(f"Mapping {len(catalog)} {catalog_name} records into the meta-disco shape...")
        all_records += build_metadata_records(catalog, url_field, workers=args.workers)

    args.metadata_out.parent.mkdir(parents=True, exist_ok=True)
    with args.metadata_out.open("w") as f:
        # "files" is the canonical meta-disco metadata key (what the AnVIL source emits);
        # every classifier loads it, so the mapped HPRC input is shape-identical to AnVIL's.
        json.dump({"files": all_records}, f)
    print(f"Wrote {len(all_records):,} meta-disco records to {args.metadata_out}")

    # Step 4: call the one classifier, exactly as AnVIL does; propagate its success.
    ok = run_all_classifications(args.metadata_out, args.output_dir, args.evidence_base, workers=args.workers)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
