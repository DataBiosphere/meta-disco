#!/usr/bin/env python3
"""Fetch VCF headers from S3 mirror for files needing header inspection."""

import argparse
import gzip
import json
import subprocess
import sys
import time
from pathlib import Path
from io import BytesIO

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from src.meta_disco.header_classifier import classify_from_vcf_header, get_rules_documentation

S3_MIRROR_URL = "https://anvilproject.s3.amazonaws.com/file"


def get_vcf_header(md5sum: str, is_gzipped: bool = True) -> str | None:
    """
    Read VCF header from S3 mirror.

    VCF headers are all lines starting with # at the beginning of the file.
    For gzipped VCFs, we fetch the first chunk and decompress.
    """
    import zlib

    url = f"{S3_MIRROR_URL}/{md5sum}.md5"

    try:
        # Fetch first 1MB - should be enough for headers
        headers = {"Range": "bytes=0-1048576"}
        resp = requests.get(url, headers=headers, timeout=60)

        if resp.status_code not in [200, 206]:
            return None

        content = resp.content

        # Decompress if gzipped
        if is_gzipped and content[:2] == b'\x1f\x8b':
            try:
                # Use zlib with gzip header handling for partial data
                decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                content = decompressor.decompress(content)
            except zlib.error:
                # Maybe it's not actually gzipped or corrupted
                pass

        # Decode and extract header lines
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1')

        # Extract header lines (starting with #)
        header_lines = []
        for line in text.split('\n'):
            if line.startswith('#'):
                header_lines.append(line)
            elif line.strip() and not line.startswith('#'):
                # First non-header line, stop
                break

        if header_lines:
            return '\n'.join(header_lines)
        return None

    except requests.Timeout:
        print(f"Timeout reading header for {md5sum}")
        return None
    except Exception as e:
        print(f"Error reading header for {md5sum}: {e}")
        return None


def classify_single_vcf(
    md5sum: str,
    file_name: str = "",
    file_size: int | None = None,
    is_gzipped: bool = True,
) -> dict | None:
    """Fetch header and classify a single VCF file by MD5."""
    header_text = get_vcf_header(md5sum, is_gzipped)
    if not header_text:
        return None

    classification = classify_from_vcf_header(header_text, file_size=file_size)
    classification["file_name"] = file_name
    classification["md5sum"] = md5sum
    classification["file_size"] = file_size
    classification["header_line_count"] = len(header_text.split('\n'))
    classification["header_preview"] = header_text[:1000] + "..." if len(header_text) > 1000 else header_text

    return classification


def process_vcf_files(input_path: Path, output_path: Path, limit: int | None = None):
    """Process VCF files that need header inspection."""

    # Load classification results or raw metadata
    with open(input_path) as f:
        if input_path.suffix == ".ndjson":
            results = [json.loads(line) for line in f if line.strip()]
        else:
            data = json.load(f)
            results = data.get("results", data.get("files", data))

    # Filter to VCF files with MD5
    vcf_extensions = [".vcf", ".vcf.gz", ".g.vcf.gz", ".gvcf.gz"]
    needs_inspection = [
        r for r in results
        if r.get("file_md5sum")  # Must have MD5
        and any(r.get("file_format", "").endswith(ext) or r.get("file_name", "").endswith(ext)
                for ext in vcf_extensions)
        and not r.get("skip")
    ]

    print(f"Found {len(needs_inspection)} VCF files with MD5 for header inspection")

    if limit:
        needs_inspection = needs_inspection[:limit]
        print(f"Processing first {limit} files")

    classifications = []
    successful = 0
    failed = 0

    for i, record in enumerate(needs_inspection):
        md5 = record.get("file_md5sum")
        file_name = record.get("file_name", "")
        file_size = record.get("file_size")
        file_format = record.get("file_format", "")
        entry_id = record.get("entry_id")

        # Check if gzipped
        is_gzipped = file_name.endswith(".gz") or file_format.endswith(".gz")

        print(f"\r[{i+1}/{len(needs_inspection)}] {file_name[:50]:<52}", end="", flush=True)

        result = classify_single_vcf(md5, file_name, file_size=file_size, is_gzipped=is_gzipped)

        if result:
            result["entry_id"] = entry_id
            result["original_record"] = {
                "file_format": file_format,
                "file_size": file_size,
                "dataset_title": record.get("dataset_title"),
            }
            classifications.append(result)
            successful += 1
        else:
            failed += 1

        # Brief delay to be nice to servers
        time.sleep(0.1)

    print(f"\n\nSuccessfully classified: {successful}")
    print(f"Failed to fetch header: {failed}")

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "total_processed": len(needs_inspection),
                "successful": successful,
                "failed": failed,
            },
            "classifications": classifications,
        }, f, indent=2)

    print(f"\nSaved to {output_path}")

    # Print summary
    print_vcf_classification_summary(classifications)


def print_vcf_classification_summary(classifications: list[dict]):
    """Print summary statistics of VCF classifications."""
    print("\n" + "=" * 70)
    print("VCF HEADER CLASSIFICATION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications to summarize.")
        return

    # Aggregate stats
    modalities = {}
    variant_types = {}
    references = {}
    callers = {}

    for c in classifications:
        mod = c.get("data_modality") or "unknown"
        modalities[mod] = modalities.get(mod, 0) + 1

        vtype = c.get("variant_type") or "unknown"
        variant_types[vtype] = variant_types.get(vtype, 0) + 1

        ref = c.get("reference_assembly") or "unknown"
        references[ref] = references.get(ref, 0) + 1

        caller = c.get("caller") or "unknown"
        # Truncate long caller names
        caller = caller[:40] + "..." if len(caller) > 40 else caller
        callers[caller] = callers.get(caller, 0) + 1

    print(f"\nTotal files classified: {len(classifications)}")

    print("\nData Modalities:")
    for mod, count in sorted(modalities.items(), key=lambda x: -x[1]):
        print(f"  {mod:<40} {count:>5}")

    print("\nVariant Types:")
    for vtype, count in sorted(variant_types.items(), key=lambda x: -x[1]):
        print(f"  {vtype:<40} {count:>5}")

    print("\nReference Assemblies:")
    for ref, count in sorted(references.items(), key=lambda x: -x[1]):
        print(f"  {ref:<40} {count:>5}")

    print("\nVariant Callers:")
    for caller, count in sorted(callers.items(), key=lambda x: -x[1])[:15]:
        print(f"  {caller:<40} {count:>5}")

    # Show sample evidence
    print("\n" + "-" * 70)
    print("SAMPLE EVIDENCE (first 3 files):")
    print("-" * 70)

    for c in classifications[:3]:
        print(f"\nFile: {c.get('file_name', 'unknown')}")
        print(f"  Modality: {c.get('data_modality')} (confidence: {c.get('confidence', 0):.0%})")
        print(f"  Variant Type: {c.get('variant_type')}")
        print(f"  Reference: {c.get('reference_assembly')}")
        print(f"  Caller: {c.get('caller')}")
        print(f"  Rules matched: {', '.join(c.get('matched_rules', [])[:5])}")
        if c.get("warnings"):
            print(f"  Warnings: {c['warnings']}")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Fetch VCF headers and classify")
    parser.add_argument("--input", "-i", type=str,
                        help="Input file (classification JSON or metadata NDJSON)")
    parser.add_argument("--output", "-o", type=str, default="output/vcf_headers.json",
                        help="Output file for classifications")
    parser.add_argument("--limit", "-l", type=int, default=None,
                        help="Limit number of files to process")
    parser.add_argument("--md5", type=str,
                        help="Classify a single file by MD5 hash")
    parser.add_argument("--gzipped", action="store_true", default=True,
                        help="File is gzipped (default: True)")
    parser.add_argument("--no-gzip", action="store_true",
                        help="File is not gzipped")
    parser.add_argument("--docs", action="store_true",
                        help="Print rules documentation and exit")
    args = parser.parse_args()

    if args.docs:
        print(get_rules_documentation())
        return

    if args.md5:
        is_gzipped = not args.no_gzip
        print(f"Classifying VCF with MD5: {args.md5} (gzipped={is_gzipped})")
        result = classify_single_vcf(args.md5, is_gzipped=is_gzipped)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Failed to fetch or classify header")
        return

    if not args.input:
        parser.error("--input required unless using --md5 or --docs")

    process_vcf_files(
        Path(args.input),
        Path(args.output),
        args.limit
    )


if __name__ == "__main__":
    main()
