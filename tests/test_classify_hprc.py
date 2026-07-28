"""Tests for the HPRC catalog adapter (scripts/classify_hprc_files.py, #276).

The adapter maps each HPRC catalog into the shared meta-disco record shape: a
synthesized md5 key, an explicit S3 url from the catalog's own location field, and a
file_size taken from the catalog or read from S3 via HEAD. These tests cover that
mapping in isolation, without touching the network (fetch_content_length is monkeypatched).
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import classify_hprc_files as hprc

from meta_disco.metadata_schema import classification_blocking_reasons


class TestPathKey:
    def test_is_contract_valid_md5(self):
        # The synthesized key must satisfy the input contract's file_md5sum pattern.
        key = hprc.path_key("s3://bucket/HG01891/m54329U_200124_193652.ccs.bam")
        assert re.fullmatch(r"[0-9a-f]{32}", key)

    def test_is_stable(self):
        assert hprc.path_key("s3://b/x.bam") == hprc.path_key("s3://b/x.bam")

    def test_distinguishes_same_basename_at_different_paths(self):
        # The collision fix: key on the full path, so two files that share a basename
        # (e.g. the 5 real HPRC cases) do NOT alias in the evidence cache.
        assert hprc.path_key("s3://b/sampleA/x.vcf.gz") != hprc.path_key("s3://b/sampleB/x.vcf.gz")


class TestBuildMetadataRecords:
    def test_maps_url_from_catalog_field_without_head_when_size_present(self, monkeypatch):
        # A catalog fileSize is used as-is and the S3 HEAD is never issued; the url
        # comes from the given catalog location field.
        monkeypatch.setattr(hprc, "fetch_content_length", lambda url, **kw: pytest.fail("should not HEAD"))
        catalog = [{"filename": "asm.fa.gz", "awsFasta": "s3://bucket/asm.fa.gz", "fileSize": 12345}]
        records = hprc.build_metadata_records(catalog, "awsFasta", workers=2)
        assert records[0]["file_size"] == 12345
        assert records[0]["url"] == "https://s3-us-west-2.amazonaws.com/bucket/asm.fa.gz"
        assert records[0]["file_format"] == ".fa"  # FileName.parse core extension (wrappers split off)
        assert records[0]["file_name"] == "asm.fa.gz"

    def test_heads_for_size_when_catalog_omits_it(self, monkeypatch):
        monkeypatch.setattr(hprc, "fetch_content_length", lambda url, **kw: 999)
        catalog = [{"filename": "r.bam", "path": "s3://bucket/r.bam"}]
        records = hprc.build_metadata_records(catalog, "path", workers=2)
        assert records[0]["file_size"] == 999

    def test_head_failure_leaves_size_none_and_unclassifiable(self, monkeypatch):
        # No fabrication (#276): a failed size lookup leaves file_size None, which the
        # contract gate diverts to a not_classified row — an unreadable size makes the
        # file unclassifiable, never a guessed 0 (which would falsely match WES rules).
        def boom(url, **kw):
            raise hprc.FetchError("nope")

        monkeypatch.setattr(hprc, "fetch_content_length", boom)
        catalog = [{"filename": "r.bam", "path": "s3://bucket/r.bam"}]
        records = hprc.build_metadata_records(catalog, "path", workers=2)
        assert records[0]["file_size"] is None
        assert classification_blocking_reasons(records[0])  # diverted to validation_failed

    def test_records_with_size_pass_the_classifier_contract(self, monkeypatch):
        # A record with a real size has no classifier-relevant contract violations, so
        # the pipeline builds a ClassifierRecord (which fetches), not a validation_failed row.
        monkeypatch.setattr(hprc, "fetch_content_length", lambda url, **kw: 100)
        catalog = [{"filename": "r.bam", "path": "s3://bucket/r.bam"}]
        records = hprc.build_metadata_records(catalog, "path", workers=1)
        assert classification_blocking_reasons(records[0]) == []

    def test_same_basename_different_path_get_distinct_keys(self, monkeypatch):
        # Two records with the same basename at different paths (the real HPRC collision
        # case) must get distinct file_md5sum cache keys — keyed on the full path.
        monkeypatch.setattr(hprc, "fetch_content_length", lambda url, **kw: 1)
        catalog = [
            {"filename": "x.vcf.gz", "path": "s3://bucket/sampleA/x.vcf.gz", "fileSize": 1},
            {"filename": "x.vcf.gz", "path": "s3://bucket/sampleB/x.vcf.gz", "fileSize": 1},
        ]
        records = hprc.build_metadata_records(catalog, "path", workers=1)
        assert records[0]["file_md5sum"] != records[1]["file_md5sum"]

    def test_missing_location_leaves_url_none_and_no_head(self, monkeypatch):
        # A record whose catalog omits the location field gets url None and is not HEADed
        # (nothing to fetch a size from); it stays None → unclassifiable.
        monkeypatch.setattr(hprc, "fetch_content_length", lambda url, **kw: pytest.fail("no url to HEAD"))
        catalog = [{"filename": "r.bam"}]  # no "path"
        records = hprc.build_metadata_records(catalog, "path", workers=1)
        assert records[0]["url"] is None
        assert records[0]["file_size"] is None
