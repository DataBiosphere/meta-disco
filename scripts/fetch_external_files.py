#!/usr/bin/env python3
"""Fetch the files ``sources/external_files.yaml`` declares into the external files cache (#710).

Each declared file is downloaded at its pinned commit into
``data/external/<dataset>/<host>/<owner>/<repo>/<commit>/<path>`` and refused unless its
sha256 is the declared one; a file already cached with that sha256 is kept as it is. A
workaround until AnVIL holds the files (#624). The logic lives in ``meta_disco.external_files``::

    uv run python scripts/fetch_external_files.py
"""

import argparse
import sys
from pathlib import Path

from meta_disco.external_files import DEFAULT_EXTERNAL_ROOT, ExternalFileError, fetch, load_external_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the declared external files into their cache")
    parser.add_argument("--external-root", type=Path, default=DEFAULT_EXTERNAL_ROOT)
    args = parser.parse_args()
    declared = load_external_files()
    fetched = kept = 0
    for entry in declared.entries:
        for file in entry.sample_maps:
            try:
                if fetch(file, args.external_root):
                    fetched += 1
                else:
                    kept += 1
            except ExternalFileError as exc:
                print(str(exc), file=sys.stderr)
                return 1
    print(f"External files: {fetched} fetched, {kept} already cached, under {args.external_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
