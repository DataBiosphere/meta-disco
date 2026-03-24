#!/usr/bin/env python3
"""Download all file metadata from the AnVIL API with pagination, throttling, and resume support."""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

API_URL = "https://service.explore.anvilproject.org/index/files"
DEFAULT_PAGE_SIZE = 1000
DEFAULT_DELAY = 0.5


def fetch_page(search_after: list | None = None, size: int = DEFAULT_PAGE_SIZE) -> dict:
    """Fetch a single page of results from the API."""
    params = {
        "size": size,
        "sort": "files.file_id",
        "order": "asc",
    }
    if search_after:
        params["search_after"] = json.dumps(search_after)

    resp = requests.get(API_URL, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def extract_file_record(hit: dict) -> dict:
    """Extract relevant fields from an API hit."""
    file_data = hit.get("files", [{}])[0] if hit.get("files") else {}
    datasets = hit.get("datasets", [{}])
    dataset = datasets[0] if datasets else {}

    donors = hit.get("donors", [{}])
    donor = donors[0] if donors else {}

    return {
        "entry_id": hit.get("entryId"),
        "file_id": file_data.get("file_id"),
        "file_name": file_data.get("file_name"),
        "file_format": file_data.get("file_format"),
        "file_size": file_data.get("file_size"),
        "file_md5sum": file_data.get("file_md5sum"),  # Needed for S3 mirror access
        "data_modality": file_data.get("data_modality", [None])[0] if file_data.get("data_modality") else None,
        "reference_assembly": file_data.get("reference_assembly", [None])[0] if file_data.get("reference_assembly") else None,
        "is_supplementary": file_data.get("is_supplementary"),
        "drs_uri": file_data.get("drs_uri"),
        "dataset_id": dataset.get("dataset_id", [None])[0] if dataset.get("dataset_id") else None,
        "dataset_title": dataset.get("title", [None])[0] if dataset.get("title") else None,
        "organism_type": donor.get("organism_type", [None])[0] if donor.get("organism_type") else None,
        "phenotypic_sex": donor.get("phenotypic_sex", [None])[0] if donor.get("phenotypic_sex") else None,
    }


def get_search_after_from_url(next_url: str) -> list | None:
    """Parse search_after parameter from next URL."""
    if not next_url or "search_after=" not in next_url:
        return None
    import urllib.parse
    parsed = urllib.parse.urlparse(next_url)
    params = urllib.parse.parse_qs(parsed.query)
    if "search_after" in params:
        return json.loads(params["search_after"][0])
    return None


def load_checkpoint(output_dir: Path) -> tuple[int, int, list | None]:
    """Load checkpoint if it exists. Returns (page_num, total_fetched, search_after)."""
    checkpoint_path = output_dir / "checkpoint.json"
    if checkpoint_path.exists():
        with open(checkpoint_path) as f:
            data = json.load(f)
        return data["page"], data["total_fetched"], data.get("search_after")
    return 0, 0, None


def save_checkpoint(output_dir: Path, page: int, total_fetched: int, search_after: list | None):
    """Save checkpoint for resume."""
    checkpoint_path = output_dir / "checkpoint.json"
    with open(checkpoint_path, "w") as f:
        json.dump({
            "page": page,
            "total_fetched": total_fetched,
            "search_after": search_after,
            "timestamp": datetime.now().isoformat(),
        }, f)


def download_all_metadata(output_dir: Path, delay: float = DEFAULT_DELAY, max_pages: int | None = None):
    """Download all file metadata, saving incrementally with resume support."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ndjson_path = output_dir / "anvil_files_metadata.ndjson"

    # Check for existing checkpoint
    page_num, total_fetched, search_after = load_checkpoint(output_dir)

    if page_num > 0:
        print(f"Resuming from checkpoint: page {page_num}, {total_fetched:,} files already downloaded")
        # Open in append mode
        ndjson_file = open(ndjson_path, "a")
    else:
        print("Starting fresh download...")
        # Open in write mode (truncate)
        ndjson_file = open(ndjson_path, "w")

    try:
        # Get total count
        print("Fetching total count...")
        first_page = fetch_page(size=1)
        total_files = first_page.get("pagination", {}).get("total", 0)
        print(f"Total files available: {total_files:,}")

        start_time = datetime.now()

        while True:
            page_num += 1

            if max_pages and page_num > max_pages:
                print(f"\nReached max pages limit ({max_pages})")
                break

            try:
                print(f"\rPage {page_num}: {total_fetched:,}/{total_files:,} ({100*total_fetched/total_files:.1f}%)", end="", flush=True)

                data = fetch_page(search_after=search_after, size=DEFAULT_PAGE_SIZE)
                hits = data.get("hits", [])

                if not hits:
                    print("\nNo more results.")
                    break

                # Write each record immediately to NDJSON
                for hit in hits:
                    file_record = extract_file_record(hit)
                    ndjson_file.write(json.dumps(file_record) + "\n")

                total_fetched += len(hits)
                ndjson_file.flush()  # Ensure data is written

                # Get search_after for next page
                pagination = data.get("pagination", {})
                search_after = get_search_after_from_url(pagination.get("next"))

                if not search_after:
                    print("\nNo more pages.")
                    break

                # Save checkpoint every 10 pages
                if page_num % 10 == 0:
                    save_checkpoint(output_dir, page_num, total_fetched, search_after)

                # Throttle
                time.sleep(delay)

            except requests.exceptions.RequestException as e:
                print(f"\nError on page {page_num}: {e}")
                save_checkpoint(output_dir, page_num - 1, total_fetched - len(hits) if 'hits' in dir() else total_fetched, search_after)
                print("Checkpoint saved. Run again to resume.")
                break

    except KeyboardInterrupt:
        print("\n\nInterrupted. Saving checkpoint...")
        save_checkpoint(output_dir, page_num, total_fetched, search_after)
        print("Checkpoint saved. Run again to resume.")

    finally:
        ndjson_file.close()

    # Final stats
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print(f"\n\nDownloaded {total_fetched:,} files to {ndjson_path}")
    if duration > 0:
        print(f"Rate: {total_fetched/duration:.1f} files/sec")

    # Clean up checkpoint if complete
    checkpoint_path = output_dir / "checkpoint.json"
    if total_fetched >= total_files and checkpoint_path.exists():
        checkpoint_path.unlink()
        print("Download complete. Checkpoint removed.")

        # Create final JSON with metadata
        print("Creating final JSON file with metadata...")
        files = []
        with open(ndjson_path) as f:
            for line in f:
                if line.strip():
                    files.append(json.loads(line))

        final_output = {
            "metadata": {
                "downloaded_at": end_time.isoformat(),
                "total_files": len(files),
                "api_url": API_URL,
            },
            "files": files,
        }
        json_path = output_dir / "anvil_files_metadata.json"
        with open(json_path, "w") as f:
            json.dump(final_output, f)
        print(f"Saved {json_path}")


def main():
    parser = argparse.ArgumentParser(description="Download AnVIL file metadata (supports resume)")
    parser.add_argument("--output", "-o", type=str, default="data/anvil",
                        help="Output directory (default: data)")
    parser.add_argument("--delay", "-d", type=float, default=DEFAULT_DELAY,
                        help=f"Delay between requests in seconds (default: {DEFAULT_DELAY})")
    parser.add_argument("--max-pages", "-m", type=int, default=None,
                        help="Maximum number of pages to fetch (default: all)")
    parser.add_argument("--restart", action="store_true",
                        help="Ignore checkpoint and start fresh")
    args = parser.parse_args()

    output_dir = Path(args.output)

    if args.restart:
        checkpoint = output_dir / "checkpoint.json"
        ndjson = output_dir / "anvil_files_metadata.ndjson"
        if checkpoint.exists():
            checkpoint.unlink()
            print("Removed existing checkpoint.")
        if ndjson.exists():
            ndjson.unlink()
            print("Removed existing data file.")

    download_all_metadata(output_dir, delay=args.delay, max_pages=args.max_pages)


if __name__ == "__main__":
    main()
