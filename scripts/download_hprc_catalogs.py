#!/usr/bin/env python3
"""Download HPRC Data Explorer catalogs for validation.

Fetches the four catalog files from the hprc-data-explorer GitHub repository
and saves them locally for use by validate_against_hprc.py.

Usage:
    python scripts/download_hprc_catalogs.py
    python scripts/download_hprc_catalogs.py --catalog sequencing-data
    python scripts/download_hprc_catalogs.py --output-dir data/hprc
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.meta_disco.validation_maps import HPRC_CATALOG_BASE_URL, HPRC_CATALOG_NAMES


def download_catalog(name: str, output_dir: Path) -> int:
    """Download a single catalog and return the record count."""
    url = f"{HPRC_CATALOG_BASE_URL}/{name}.json"
    out_path = output_dir / f"{name}.json"

    print(f"  Downloading {name}...", end=" ", flush=True)
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()

    data = resp.json()
    out_path.write_text(json.dumps(data, separators=(",", ":")))
    print(f"{len(data):,} records")
    return len(data)


def main():
    parser = argparse.ArgumentParser(
        description="Download HPRC Data Explorer catalogs"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/hprc"),
        help="Directory to save catalogs (default: data/hprc)",
    )
    parser.add_argument(
        "--catalog",
        choices=HPRC_CATALOG_NAMES,
        help="Download a single catalog (default: all)",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    catalogs_to_fetch = [args.catalog] if args.catalog else HPRC_CATALOG_NAMES

    print("Downloading HPRC catalogs...")
    counts = {}
    for name in catalogs_to_fetch:
        counts[name] = download_catalog(name, args.output_dir)

    # Write download metadata
    metadata = {
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "source": HPRC_CATALOG_BASE_URL,
        "catalogs": counts,
    }
    meta_path = args.output_dir / "download_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2))

    total = sum(counts.values())
    print(f"\nDone: {total:,} total records across {len(counts)} catalogs")
    print(f"Saved to: {args.output_dir}")


if __name__ == "__main__":
    main()
