"""Differential harness: old fixed-window fetchers vs the new streaming path (#264).

Runs both read paths against live S3 on a per-type sample of real files and reports where
they diverge — at the fetcher-output level (header text / read names / contig names /
segment tags / member names) and at the final classification level (the acceptance gate
for the #263 cutover). Read-depth differences that flip no classification are expected and
fine; anything that changes a classification is listed for investigation.

This is a manual tool (it needs the network); it is not imported by the pipeline or run in
CI. BAM/CRAM is out of scope (#263) — it stays on samtools — so it is skipped here.

    uv run python scripts/compare_streaming.py --per-type 40
"""

import argparse
import json
import tempfile
from collections import Counter
from dataclasses import replace
from pathlib import Path

from meta_disco.fetchers import FetchError
from meta_disco.file_types import FILE_TYPE_REGISTRY
from meta_disco.pipeline import ClassifyPipeline
from meta_disco.streaming import (
    fetch_fasta_headers_streaming,
    fetch_fastq_reads_streaming,
    fetch_gfa_segment_tags_streaming,
    fetch_tar_headers_streaming,
    fetch_vcf_header_streaming,
)

DEFAULT_METADATA = Path("data/anvil/anvil_files_metadata.ndjson")

# The streaming counterpart of each in-scope config's fetcher, keyed by config name.
STREAMING_FETCHERS = {
    "vcf": fetch_vcf_header_streaming,
    "fastq": fetch_fastq_reads_streaming,
    "fasta": fetch_fasta_headers_streaming,
    "gfa": fetch_gfa_segment_tags_streaming,
    "tar": fetch_tar_headers_streaming,
}


def _route(rec: dict) -> str | None:
    """The in-scope config name whose extensions match this record, or None.

    Uses production's match rule (``ClassifyPipeline._filter_records``): case-sensitive, on
    either ``file_format`` or ``file_name`` — so a record whose extension lives only in
    ``file_format`` is still sampled, and a mixed-case name is not spuriously matched.
    Production runs that rule per config and may match one file to several; the harness needs a
    single bucket per file, so it additionally picks the config with the longest matching
    extension (``.vcf.gz`` -> vcf, not a bare ``.gz``). That extra disambiguation is the
    harness's, not production's.
    """
    fmt = str(rec.get("file_format") or "")
    name = str(rec.get("file_name") or "")
    best, best_len = None, 0
    for cfg_name in STREAMING_FETCHERS:
        for ext in FILE_TYPE_REGISTRY[cfg_name].extensions:
            if (fmt.endswith(ext) or name.endswith(ext)) and len(ext) > best_len:
                best, best_len = cfg_name, len(ext)
    return best


def _sample(metadata: Path, per_type: int) -> dict[str, list[dict]]:
    """First ``per_type`` records of each in-scope file type, by extension routing."""
    buckets: dict[str, list[dict]] = {name: [] for name in STREAMING_FETCHERS}
    remaining = len(buckets)
    with metadata.open() as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            cfg_name = _route(rec)
            if cfg_name is None or len(buckets[cfg_name]) >= per_type:
                continue
            buckets[cfg_name].append(rec)
            if len(buckets[cfg_name]) == per_type:
                remaining -= 1
                if remaining == 0:
                    break
    return buckets


def _is_gzipped(config, file_name: str, file_format: str | None) -> bool:
    """Mirror the pipeline's gzip determination so the diff reflects production, not a guess.

    Same rule as ``ClassifyPipeline._process_single_record`` (pipeline.py): if the config has
    no ``.gz`` extension at all, treat the file as gzipped; otherwise it is gzipped only when
    its name or ``file_format`` ends in ``.gz``.
    """
    has_gz_ext = any(ext.endswith(".gz") for ext in config.extensions)
    if not has_gz_ext:
        return True
    return file_name.endswith(".gz") or (file_format or "").endswith(".gz")


def _norm_payload(payload):
    """Normalize a fetcher payload for equality (SegmentTags -> their on-disk dicts)."""
    if isinstance(payload, list):
        return [item.to_json() if hasattr(item, "to_json") else item for item in payload]
    return payload


def _fetch_payload(fetcher, config, rec: dict, is_gzipped: bool, evidence_dir: Path):
    """Run one fetcher; return its normalized payload, or an ``("error", reason)`` marker."""
    try:
        out = fetcher(
            evidence_dir,
            rec["file_md5sum"],
            file_name=rec.get("file_name", ""),
            is_gzipped=is_gzipped,
            use_cache=False,
            head_detector=config.head_detector,
        )
        return _norm_payload(out)
    except FetchError as e:
        return ("error", e.reason)


def _classifications(config, rec: dict, is_gzipped: bool, evidence_base: Path) -> dict:
    """The five-dimension classification block for one file under ``config``."""
    record = ClassifyPipeline.classify_single(
        config,
        rec["file_md5sum"],
        file_name=rec.get("file_name", ""),
        file_size=rec.get("file_size"),
        file_format=rec.get("file_format"),
        is_gzipped=is_gzipped,
        use_cache=False,
        evidence_base=evidence_base,
    )
    return record["classifications"]


def _class_key(classifications: dict) -> dict:
    """Reduce a classification block to per-dimension ``(value, status)``, dropping evidence.

    The cutover gate is whether the verdict matches, not whether the audit prose is identical:
    when both paths agree a file is unreadable, their fetch-failure reason wording differs (and
    lands in the evidence), which must NOT read as a regression. Comparing only value+status
    measures what the cutover actually cares about.
    """
    return {
        dim: ((entry.get("value"), entry.get("status")) if isinstance(entry, dict) else entry)
        for dim, entry in classifications.items()
    }


def compare(buckets: dict[str, list[dict]], workdir: Path) -> None:
    for cfg_name, records in buckets.items():
        config = FILE_TYPE_REGISTRY[cfg_name]
        streaming_config = replace(config, fetcher=STREAMING_FETCHERS[cfg_name])
        tally: Counter = Counter()
        print(f"\n=== {cfg_name}: {len(records)} files ===")

        for rec in records:
            md5 = rec.get("file_md5sum")
            if not md5:
                tally["skipped_no_md5"] += 1
                continue
            file_name = rec.get("file_name", "")
            try:
                is_gzipped = _is_gzipped(config, file_name, rec.get("file_format"))
                ev = workdir / cfg_name / md5
                old_payload = _fetch_payload(config.fetcher, config, rec, is_gzipped, ev / "old_fetch")
                new_payload = _fetch_payload(STREAMING_FETCHERS[cfg_name], config, rec, is_gzipped, ev / "new_fetch")
                old_class = _class_key(_classifications(config, rec, is_gzipped, ev / "old_cls"))
                new_class = _class_key(_classifications(streaming_config, rec, is_gzipped, ev / "new_cls"))
            except Exception as e:  # one pathological file must not abort the whole live-S3 run
                tally["error"] += 1
                print(f"  ERROR {md5} {file_name}: {type(e).__name__}: {e}")
                continue

            tally["payload_match" if old_payload == new_payload else "payload_diff"] += 1
            if old_class == new_class:
                tally["class_match"] += 1
            else:
                tally["class_diff"] += 1
                print(f"  CLASS DIFF {md5} {file_name}")
                print(f"    old: {old_class}")
                print(f"    new: {new_class}")

        print(f"  payload: {tally['payload_match']} match / {tally['payload_diff']} diff")
        print(f"  class:   {tally['class_match']} match / {tally['class_diff']} diff")
        if tally["skipped_no_md5"]:
            print(f"  skipped (no md5): {tally['skipped_no_md5']}")
        if tally["error"]:
            print(f"  errors (logged, skipped): {tally['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA, help="AnVIL metadata NDJSON")
    parser.add_argument("--per-type", type=int, default=40, help="files to sample per file type")
    args = parser.parse_args()

    buckets = _sample(args.metadata, args.per_type)
    with tempfile.TemporaryDirectory(prefix="compare-streaming-") as tmp:
        compare(buckets, Path(tmp))


if __name__ == "__main__":
    main()
