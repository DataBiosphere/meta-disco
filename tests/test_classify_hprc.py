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


class TestOneRecordPerUrl:
    """The alignments catalog lists a file more than once; the input carries it once."""

    def test_the_same_location_in_two_spellings_is_one_record(self):
        """The shape the catalog actually has: `https://` and `s3://` forms of one key."""
        rows = [
            {"filename": "x.vcf.gz", "loc": "https://s3-us-west-2.amazonaws.com/bucket/x.vcf.gz", "fileSize": 1},
            {"filename": "x.vcf.gz", "loc": "s3://bucket/x.vcf.gz", "fileSize": 1},
            {"filename": "y.vcf.gz", "loc": "s3://bucket/y.vcf.gz", "fileSize": 1},
        ]
        records = hprc.build_metadata_records(rows, "loc", workers=1)
        assert records[0] == records[1], "one URL, one key, one record"

        kept, collapsed = hprc.one_record_per_url(records)
        assert collapsed == 1
        assert [r["file_name"] for r in kept] == ["x.vcf.gz", "y.vcf.gz"]

    def test_two_rows_that_differ_at_one_url_are_refused_not_halved(self):
        """The collapse is argued from the records being identical, so it checks that: a
        row that differs is a second fact about the file, and dropping it would lose it."""
        records = hprc.build_metadata_records(
            [
                {"filename": "x.vcf.gz", "loc": "s3://bucket/x.vcf.gz", "fileSize": 1},
                {"filename": "x.vcf.gz", "loc": "s3://bucket/x.vcf.gz", "fileSize": 2},
            ],
            "loc",
            workers=1,
        )
        with pytest.raises(ValueError, match="different records"):
            hprc.one_record_per_url(records)

    def test_records_with_no_url_are_not_collapsed_together(self):
        """Two files with no location are two files the run cannot read, not one."""
        records = hprc.build_metadata_records(
            [{"filename": "a.readme", "fileSize": 1}, {"filename": "b.readme", "fileSize": 1}], "loc", workers=1
        )
        assert [r["file_md5sum"] for r in records] == [None, None]
        kept, collapsed = hprc.one_record_per_url(records)
        assert collapsed == 0 and len(kept) == 2

    def test_a_repeated_url_without_a_size_is_headed_once(self, monkeypatch):
        """The collapse runs on mapped records, before the size fill: one HEAD per URL,
        and a lookup that failed on one copy cannot make the two records differ."""
        calls = []

        def head(url, **kw):
            calls.append(url)
            return 7

        monkeypatch.setattr(hprc, "fetch_content_length", head)
        rows = [{"filename": "r.bam", "path": "s3://bucket/r.bam"}] * 2
        kept, collapsed = hprc.one_record_per_url(hprc.map_catalog(rows, "path"))
        hprc.fill_sizes(kept, workers=1)
        assert collapsed == 1
        assert [r["file_size"] for r in kept] == [7]
        assert len(calls) == 1
