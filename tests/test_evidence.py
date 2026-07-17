"""Tests for the typed cached-evidence records the fetchers persist (#206)."""

from meta_disco.evidence import (
    BamEvidence,
    FastaEvidence,
    FastqEvidence,
    GfaEvidence,
    VcfEvidence,
    get_evidence_path,
)


class TestGetEvidencePath:
    def test_shards_by_first_two_md5_chars(self, tmp_path):
        p = get_evidence_path(tmp_path, "ab" + "c" * 30)
        assert p == tmp_path / "ab" / f"{'ab' + 'c' * 30}.json"


class TestRoundTrip:
    def test_bam_round_trips_and_omits_bytes(self, tmp_path):
        ev = BamEvidence(md5sum="a" * 32, file_name="x.bam", header_text="@HD\tVN:1.6\n@SQ\tSN:chr1")
        ev.save(tmp_path)
        loaded = BamEvidence.load(tmp_path, "a" * 32)
        assert isinstance(loaded, BamEvidence)
        assert loaded.payload == "@HD\tVN:1.6\n@SQ\tSN:chr1"
        assert loaded.count == 2  # header line count, not char count
        assert loaded.raw_bytes_fetched is None  # samtools stream: no byte count
        # None aux keys are not written to disk.
        on_disk = get_evidence_path(tmp_path, "a" * 32).read_text()
        assert "raw_bytes_fetched" not in on_disk
        assert "source_url" not in on_disk

    def test_vcf_round_trips_with_max_positions_and_source_url(self, tmp_path):
        ev = VcfEvidence(
            md5sum="b" * 32,
            file_name="x.vcf.gz",
            header_text="##fileformat=VCFv4.2\n#CHROM\tPOS",
            max_positions={"1": 1000, "2": 2000},
            raw_bytes_fetched=4096,
            source_url="https://example/x.vcf.gz",
        )
        ev.save(tmp_path)
        loaded = VcfEvidence.load(tmp_path, "b" * 32)
        assert isinstance(loaded, VcfEvidence)
        assert loaded.payload == "##fileformat=VCFv4.2\n#CHROM\tPOS"
        assert loaded.count == 2
        assert loaded.max_positions == {"1": 1000, "2": 2000}
        assert loaded.raw_bytes_fetched == 4096
        assert loaded.source_url == "https://example/x.vcf.gz"

    def test_vcf_without_max_positions_omits_the_key(self, tmp_path):
        VcfEvidence(md5sum="c" * 32, file_name="x.vcf", header_text="#CHROM").save(tmp_path)
        assert "max_positions" not in get_evidence_path(tmp_path, "c" * 32).read_text()
        assert VcfEvidence.load(tmp_path, "c" * 32).max_positions is None

    def test_fastq_round_trips(self, tmp_path):
        ev = FastqEvidence(md5sum="d" * 32, file_name="x.fastq.gz", read_names=["@r1", "@r2"], raw_bytes_fetched=256)
        ev.save(tmp_path)
        loaded = FastqEvidence.load(tmp_path, "d" * 32)
        assert loaded.payload == ["@r1", "@r2"]
        assert loaded.count == 2

    def test_fasta_round_trips(self, tmp_path):
        FastaEvidence(md5sum="e" * 32, file_name="x.fa", contig_names=["chr1", "chr2", "chrM"]).save(tmp_path)
        loaded = FastaEvidence.load(tmp_path, "e" * 32)
        assert loaded.payload == ["chr1", "chr2", "chrM"]
        assert loaded.count == 3

    def test_gfa_round_trips(self, tmp_path):
        tags = [{"SN": "chr1", "SR": "0"}, {"SN": "chr1", "SR": "1"}]
        GfaEvidence(md5sum="f" * 32, file_name="x.gfa.gz", gfa_segment_tags=tags).save(tmp_path)
        loaded = GfaEvidence.load(tmp_path, "f" * 32)
        assert loaded.payload == tags
        assert loaded.count == 2


class TestEmptyPayloadIsAHit:
    def test_fasta_empty_contig_list_loads_as_a_hit(self, tmp_path):
        # A head with no contig line is a valid readable result, not a miss.
        FastaEvidence(md5sum="a" * 32, file_name="x.fa", contig_names=[]).save(tmp_path)
        loaded = FastaEvidence.load(tmp_path, "a" * 32)
        assert loaded is not None
        assert loaded.payload == []
        assert loaded.count == 0

    def test_gfa_empty_tag_list_loads_as_a_hit(self, tmp_path):
        # A plain GFA carries no rGFA tags — an empty list is a successful read.
        GfaEvidence(md5sum="b" * 32, file_name="x.gfa", gfa_segment_tags=[]).save(tmp_path)
        loaded = GfaEvidence.load(tmp_path, "b" * 32)
        assert loaded is not None
        assert loaded.payload == []


class TestCacheMiss:
    def test_missing_file_is_a_miss(self, tmp_path):
        assert BamEvidence.load(tmp_path, "a" * 32) is None

    def test_undecodable_file_is_a_miss(self, tmp_path):
        path = get_evidence_path(tmp_path, "a" * 32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ not json")
        assert BamEvidence.load(tmp_path, "a" * 32) is None

    def test_missing_payload_key_is_a_miss(self, tmp_path):
        # An empty dict (or a file lacking this type's payload key) is not a hit.
        path = get_evidence_path(tmp_path, "a" * 32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        assert FastaEvidence.load(tmp_path, "a" * 32) is None
        assert FastaEvidence.from_json({}) is None

    def test_missing_md5_key_is_a_miss(self):
        assert BamEvidence.from_json({"header_text": "@HD"}) is None

    def test_non_dict_top_level_json_is_a_miss(self, tmp_path):
        # A cache file whose top-level JSON is not an object must not raise out of
        # load() — the contract is "any miss -> None", so the fetcher re-fetches.
        for raw in ("5", "true", "null", '"header_text"', "[1, 2]"):
            path = get_evidence_path(tmp_path, "a" * 32)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw)
            assert BamEvidence.load(tmp_path, "a" * 32) is None, raw
        assert BamEvidence.from_json(5) is None
        assert BamEvidence.from_json(["header_text"]) is None


class TestLegacyFileLoad:
    def test_legacy_bam_file_loads_without_refetch(self, tmp_path):
        # Pre-#206 BAM evidence: carries the dropped header_line_count, no
        # raw_bytes_fetched. It must load, ignore the stale count, and expose
        # the right payload/count — no re-fetch.
        path = get_evidence_path(tmp_path, "a" * 32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"md5sum": "%s", "file_name": "old.bam", "header_text": "@HD\\n@SQ\\n@SQ", '
            '"header_line_count": 3, "fetch_timestamp": "2020-01-01T00:00:00Z"}' % ("a" * 32)
        )
        loaded = BamEvidence.load(tmp_path, "a" * 32)
        assert isinstance(loaded, BamEvidence)
        assert loaded.payload == "@HD\n@SQ\n@SQ"
        assert loaded.count == 3  # derived from payload, not the stale stored key
        assert loaded.raw_bytes_fetched is None
        assert loaded.fetch_timestamp == "2020-01-01T00:00:00Z"

    def test_legacy_fasta_file_with_contig_count_loads(self, tmp_path):
        path = get_evidence_path(tmp_path, "b" * 32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"md5sum": "%s", "file_name": "old.fa", "contig_names": ["chr1", "chr2"], '
            '"contig_count": 2, "raw_bytes_fetched": 100, "fetch_timestamp": "2020-01-01T00:00:00Z"}' % ("b" * 32)
        )
        loaded = FastaEvidence.load(tmp_path, "b" * 32)
        assert loaded.payload == ["chr1", "chr2"]
        assert loaded.count == 2
        assert loaded.raw_bytes_fetched == 100


class TestPayloadKeyIsTheOnDiskKey:
    def test_each_subclass_writes_its_named_payload_key(self):
        cases = [
            (BamEvidence(md5sum="a" * 32, file_name="f", header_text="@HD"), "header_text"),
            (VcfEvidence(md5sum="a" * 32, file_name="f", header_text="#C"), "header_text"),
            (FastqEvidence(md5sum="a" * 32, file_name="f", read_names=["@r"]), "read_names"),
            (FastaEvidence(md5sum="a" * 32, file_name="f", contig_names=["c"]), "contig_names"),
            (GfaEvidence(md5sum="a" * 32, file_name="f", gfa_segment_tags=[{"SN": "c"}]), "gfa_segment_tags"),
        ]
        for ev, key in cases:
            assert key == ev.PAYLOAD_KEY
            assert key in ev.to_json()
