"""Tests for the index producer: each index file's kind, and the edge to its parent.

What an index takes from its parent is carried at reconcile (#571), and tested there
(``tests/test_reconcile_inherit.py``); this producer names the parent and nothing more.
"""

import json

import pytest
from classify_index_files import (
    AMBIGUOUS_PARENT,
    INHERITED_FIELDS,
    NO_MATCHING_PARENT,
    get_parent_candidates,
    propagate_to_index_files,
)

from meta_disco.edges import parent_kind_of
from meta_disco.models import (
    CLASSIFICATION_FIELDS,
    CLASSIFIED,
    NOT_CLASSIFIED,
    field_status,
    field_value,
)
from meta_disco.producers import INDEX_TO_PARENT
from tests.metadata_fixtures import write_metadata as _write_metadata
from tests.producer_sweep import run_index_producer


def _assert_declined(output: dict, file_name: str) -> dict:
    """An index file that took no parent: `index` by extension, the rest unknown.

    `data_type` is knowable without a parent — the extension says so — and the others
    are properties of the data the index points into, so they are not_classified
    rather than not_applicable: they apply, and nothing here can determine them (#438).
    """
    records = [r for r in output["classifications"] if r["file_name"] == file_name]
    assert len(records) == 1, f"{file_name} should get exactly one record"
    cls = records[0]["classifications"]
    assert field_status(cls, "data_type") == CLASSIFIED
    assert field_value(cls, "data_type") == "index"
    for fld in INHERITED_FIELDS:
        assert field_status(cls, fld) == NOT_CLASSIFIED, f"{fld} should be not_classified, not asserted"
    # A declined record carries no edge: an edge exists only where the parent resolves
    # (ADR-0002 decision 2, #356), and the name it points at is its own less the extension.
    assert records[0]["generated_by"] is None
    return records[0]


def _fid(md5: str) -> str:
    """The catalog identity a fixture's two sides join on, derived from its md5.

    Distinct files have distinct md5s in every fixture but the same-bytes one, which
    passes its ids explicitly — so deriving here keeps the join right without any
    fixture inventing a second identifier by hand.
    """
    return f"fid-{md5[:8]}"


def _file(name: str, fmt: str, md5: str, entry_id: str, dataset_id: str = "ds1", file_id: str | None = None) -> dict:
    """One input metadata record, in the shape `write_metadata` expects.

    Carries `file_id` because the input contract requires it and the edge grounds the
    parent on it (`parent_key`). It defaults to `_fid(md5)`; pass it explicitly where two
    records share one md5.
    """
    return {
        "file_name": name,
        "file_format": fmt,
        "file_md5sum": md5,
        "file_id": file_id or _fid(md5),
        "dataset_id": dataset_id,
        "dataset_title": "test",
        "entry_id": entry_id,
    }


def _assert_matched(output: dict, file_name: str) -> dict:
    """An index file that took a parent: `index` by extension, the rest left to reconcile, and an edge."""
    records = [r for r in output["classifications"] if r["file_name"] == file_name]
    assert len(records) == 1, f"{file_name} should get exactly one record"
    cls = records[0]["classifications"]
    assert list(cls) == list(CLASSIFICATION_FIELDS)
    assert field_value(cls, "data_type") == "index"
    for fld in INHERITED_FIELDS:
        # Not copied from the parent: reconcile carries it across the edge (#571).
        assert field_status(cls, fld) == NOT_CLASSIFIED, fld
        assert cls[fld]["evidence"] == [], fld
    assert records[0]["generated_by"]["activity"] == "IndexActivity"
    return records[0]


@pytest.mark.parametrize(
    ("index_name", "extension", "parent", "only_candidate"),
    [
        pytest.param("sample.vcf.gz.tbi", ".tbi", "sample.vcf.gz", True, id="vcf.gz.tbi finds vcf.gz"),
        pytest.param("sample.bed.gz.tbi", ".tbi", "sample.bed.gz", True, id="bed.gz.tbi finds bed.gz"),
        pytest.param("sample.txt.gz.tbi", ".tbi", "sample.txt.gz", True, id="txt.gz.tbi (tabix TSV) finds txt.gz"),
        pytest.param("sample.bam.bai", ".bai", "sample.bam", True, id="bam.bai finds bam"),
        pytest.param("sample.cram.crai", ".crai", "sample.cram", True, id="cram.crai finds cram"),
        pytest.param("movie.subreads.bam.pbi", ".pbi", "movie.subreads.bam", False, id="pbi (PacBio index) finds bam"),
        pytest.param("HG03652.regions.bed.gz.csi", ".csi", "HG03652.regions.bed.gz", True, id="csi finds bed.gz"),
        pytest.param(
            "NA20799_hap2_hprc_r2_v1.0.1.fa.gz.gzi",
            ".gzi",
            "NA20799_hap2_hprc_r2_v1.0.1.fa.gz",
            True,
            id="gzi (bgzip index) finds fa.gz",
        ),
        # Pattern 2: the index extension replaces the parent's (rare); no .bam in the name.
        pytest.param("sample.bai", ".bai", "sample.bam", False, id="pattern 2 replaces the extension"),
        pytest.param(
            "HG01874.chr17.hc.vcf.gz.tbi", ".tbi", "HG01874.chr17.hc.vcf.gz", True, id="dotted name still works"
        ),
        pytest.param(
            "ALL.chr19.genotypes.vcf.bgz.tbi", ".tbi", "ALL.chr19.genotypes.vcf.bgz", True, id="vcf.bgz.tbi (#561)"
        ),
    ],
)
def test_parent_candidate_generation(index_name, extension, parent, only_candidate):
    """The parent name an index name yields; ``only_candidate`` pins that it is the sole one."""
    candidates = get_parent_candidates(index_name, extension)
    assert parent in candidates
    if only_candidate:
        assert len(candidates) == 1


@pytest.mark.parametrize(
    ("index_name", "extension", "junk"),
    [
        pytest.param("sample.vcf.gz.tbi", ".tbi", ".gz.gz", id="no .gz.gz"),
        pytest.param("sample.vcf.gz.tbi", ".tbi", ".vcf.gz.vcf.gz", id="no .vcf.gz.vcf.gz"),
        pytest.param("sample.bam.bai", ".bai", ".bam.bam", id="no .bam.bam"),
        pytest.param("sample.cram.crai", ".crai", ".cram.cram", id="no .cram.cram"),
    ],
)
def test_no_junk_candidates(index_name, extension, junk):
    """Regression: candidate generation never doubles an extension."""
    assert not any(junk in c for c in get_parent_candidates(index_name, extension))


def test_a_gvcf_parent_is_variants_not_unknown():
    """`FileName.parse` keeps a compound core whole — a gVCF is `.g.vcf` — and
    `EXTENSION_MAP` keys `.vcf`, so an exact lookup called 2,504 real gVCF parents a
    kind we could not tell."""
    assert parent_kind_of("NA20872.haplotypeCalls.er.raw.g.vcf.gz") == "variants"
    assert parent_kind_of("HG002.vcf.gz") == "variants"


def test_a_parent_whose_kind_is_genuinely_unknown_stays_none():
    """No guess: `.txt.gz` is a category with no parent_kind term."""
    assert parent_kind_of("annotations.txt.gz") is None


def test_every_index_record_carries_its_own_file_size(tmp_path):
    """The index file's own bytes, on both record paths.

    Every index record carried `file_size: null` until #439 populated the intermediate
    record this producer builds from. Nothing pinned it, so the fix was incidental and
    could be undone the same way.
    """
    envelope = run_index_producer(
        tmp_path,
        [
            {**_file("sample.bam", ".bam", "b" * 32, "p1"), "file_size": 900},
            {**_file("sample.bam.bai", ".bai", "a" * 32, "i1"), "file_size": 17},
            {**_file("orphan.bam.bai", ".bai", "c" * 32, "i2"), "file_size": 23},
        ],
    )
    sizes = {r["file_name"]: r["file_size"] for r in envelope["classifications"]}
    assert sizes == {"sample.bam.bai": 17, "orphan.bam.bai": 23}


class TestIndexToParentMapping:
    """Test the INDEX_TO_PARENT mapping is complete."""

    def test_tbi_has_common_extensions(self):
        """TBI should support common tabix-indexed formats."""
        tbi_exts = INDEX_TO_PARENT[".tbi"]
        assert ".vcf.gz" in tbi_exts
        assert ".bed.gz" in tbi_exts
        assert ".txt.gz" in tbi_exts

    def test_csi_has_vcf(self):
        """CSI should support VCF."""
        csi_exts = INDEX_TO_PARENT[".csi"]
        assert ".vcf.gz" in csi_exts

    def test_csi_has_bed_gz(self):
        """CSI should support BED.gz files."""
        csi_exts = INDEX_TO_PARENT[".csi"]
        assert ".bed.gz" in csi_exts

    def test_no_bare_gz(self):
        """Should not have bare .gz as a parent extension."""
        for index_ext, parent_exts in INDEX_TO_PARENT.items():
            assert ".gz" not in parent_exts, f"{index_ext} has bare .gz"


class TestTheEdge:
    """The edge each matched index gets, and the refusals before one is written."""

    def test_csi_names_its_bed_parent(self, tmp_path):
        """A .csi index's edge names the .bed.gz it indexes (#41's case: a BED parent)."""
        output = run_index_producer(
            tmp_path,
            [
                _file("HG03652.regions.bed.gz", ".bed.gz", "3" * 32, "entry_bed"),
                _file("HG03652.regions.bed.gz.csi", ".csi", "4" * 32, "entry_csi"),
            ],
        )
        assert len(output["classifications"]) == 1
        csi = _assert_matched(output, "HG03652.regions.bed.gz.csi")
        assert csi["generated_by"]["inputs"][0]["parent_file"] == "HG03652.regions.bed.gz"
        # `.csi` indexes variants or intervals, so the type alone cannot say which;
        # the matched parent does.
        assert csi["generated_by"]["inputs"][0]["parent_kind"] == "intervals"
        assert field_status(csi["classifications"], "data_type") == CLASSIFIED

    def test_an_hprc_parent_is_grounded_on_the_url_hash(self, tmp_path):
        """Where the source declares the checksum field its key, the edge grounds on it.

        The HPRC catalog issues no `file_id`; what it guarantees unique is the file's
        URL, whose hash its builder writes as the checksum (`record_keys.SOURCE_RECORD_KEYS`).
        Read off the envelope rather than guessed from which fields a record carries.
        """
        parent = _file("sample.bam", ".bam", "a" * 32, "e1")
        index = _file("sample.bam.bai", ".bai", "b" * 32, "e2")
        for record in (parent, index):
            del record["file_id"]
        metadata_file = _write_metadata(tmp_path / "metadata.json", [parent, index], repository="hprc")
        output_file = tmp_path / "out.json"
        propagate_to_index_files(metadata_file, output_file)
        rows = {r["file_name"]: r for r in json.loads(output_file.read_text())["classifications"]}
        assert rows["sample.bam.bai"]["generated_by"]["inputs"][0]["parent_key"] == "a" * 32

    def test_a_parent_only_the_catch_all_writes_still_gets_its_edge(self, tmp_path):
        """A `.txt.gz` under a `.tbi` is classified by the catch-all, after this producer.

        Before #571 such an index inherited nothing, because the parent had no row when
        this producer ran; it reads no rows now, so the edge is written like any other and
        reconcile carries the parent's answer.
        """
        txt = _file("notes.txt.gz", ".txt.gz", "c" * 32, "e3")
        index = _file("notes.txt.gz.tbi", ".tbi", "b" * 32, "e2")
        output = run_index_producer(tmp_path, [txt, index])
        row = _assert_matched(output, "notes.txt.gz.tbi")
        assert row["generated_by"]["inputs"][0]["parent_file"] == "notes.txt.gz"

    def test_a_key_two_input_records_carry_is_refused(self, tmp_path):
        """A repeated input key is refused before any edge is written: it would name two files."""
        bam = _file("sample.bam", ".bam", "a" * 32, "e1", file_id="fid-dup")
        txt = _file("notes.txt.gz", ".txt.gz", "c" * 32, "e3", file_id="fid-dup")
        index = _file("notes.txt.gz.tbi", ".tbi", "b" * 32, "e2")
        metadata_file = _write_metadata(tmp_path / "metadata.json", [bam, txt, index])
        with pytest.raises(ValueError, match=r"1 value\(s\) of file_id are carried by more than one.*fid-dup \(x2\)"):
            propagate_to_index_files(metadata_file, tmp_path / "out.json")

    def test_a_matched_parent_without_the_key_is_refused(self, tmp_path):
        """A drifted key on the input parent raises rather than writing an ungrounded edge.

        `file_id` is not classifier-relevant, so a drifted one reaches this producer.
        """
        parent = _file("sample.bam", ".bam", "a" * 32, "e1")
        parent["file_id"] = None
        index = _file("sample.bam.bai", ".bai", "b" * 32, "e2")
        metadata_file = _write_metadata(tmp_path / "metadata.json", [parent, index])
        with pytest.raises(ValueError, match=r"'sample\.bam' has file_id None"):
            propagate_to_index_files(metadata_file, tmp_path / "out.json")

    def test_an_envelope_naming_no_repository_is_refused_before_any_record_loads(self, tmp_path):
        """No repository, no key to ground an edge on; guessing a field is what #486 removed.

        Refused before the snapshot loads, so nothing — not even `excluded_files.json`
        — is written into the run directory for an input the producer cannot ground.
        """
        metadata_file = tmp_path / "metadata.json"
        metadata_file.write_text(json.dumps({"files": [_file("sample.bam.bai", ".bai", "b" * 32, "e2")]}))
        with pytest.raises(ValueError, match=r"metadata\.json.*repository None, which declares no record key"):
            propagate_to_index_files(metadata_file, tmp_path / "out.json")
        assert not (tmp_path / "excluded_files.json").exists()

    def test_same_md5_parents_are_told_apart_by_their_keys(self, tmp_path):
        """Two byte-identical parents with different names each get their own index's edge.

        Keyed by md5 alone, one `.fai` took the other's answer, which one depending on a
        write order nothing guarantees (#486). The edge grounds on the source's record key.
        """
        shared_md5 = "7" * 32
        output = run_index_producer(
            tmp_path,
            [
                _file("grch38.fasta", ".fasta", shared_md5, "entry_ref", file_id="fid-ref"),
                _file("Homo_sapiens_assembly38.fasta", ".fasta", shared_md5, "entry_asm", file_id="fid-asm"),
                _file("grch38.fasta.fai", ".fai", "8" * 32, "entry_ref_fai"),
                _file("Homo_sapiens_assembly38.fasta.fai", ".fai", "9" * 32, "entry_asm_fai"),
            ],
        )
        rows = {r["file_name"]: r for r in output["classifications"]}
        assert rows["grch38.fasta.fai"]["generated_by"]["inputs"][0]["parent_key"] == "fid-ref"
        assert rows["Homo_sapiens_assembly38.fasta.fai"]["generated_by"]["inputs"][0]["parent_key"] == "fid-asm"

    def test_gzi_names_its_fasta_parent(self, tmp_path):
        """A bgzip index takes its data_type from its own extension and names the `.fa.gz` (#526)."""
        output = run_index_producer(
            tmp_path,
            [
                _file("chm13v2.0.fa.gz", ".fa.gz", "7" * 32, "e1"),
                _file("chm13v2.0.fa.gz.gzi", ".gzi", "6" * 32, "e2"),
            ],
        )
        row = _assert_matched(output, "chm13v2.0.fa.gz.gzi")
        assert row["generated_by"]["inputs"][0]["parent_file"] == "chm13v2.0.fa.gz"
        assert row["generated_by"]["inputs"][0]["parent_kind"] == "sequence"

    def test_no_matching_parent_goes_to_unmatched(self, tmp_path):
        """Index file with no parent in metadata goes to unmatched_files, not classifications."""
        output = run_index_producer(tmp_path, [_file("orphan.bam.bai", ".bai", "5" * 32, "e1")])
        _assert_declined(output, "orphan.bam.bai")
        assert len(output["unmatched_files"]) == 1
        assert output["unmatched_files"][0]["file_name"] == "orphan.bam.bai"
        assert output["unmatched_files"][0]["reason"] == NO_MATCHING_PARENT
        assert output["metadata"]["details"]["ambiguous_parent"] == 0

    def test_ambiguous_parent_takes_no_parent_at_all(self, tmp_path):
        """Two files sharing the name an index points at: no parent is chosen (#438)."""
        # Same name, different files — as ANVIL_T2T_CHRY calls one sample against both
        # CHM13v2 and GRCh38 and stores the outputs under different paths. Whichever the
        # old lookup kept, the index would have inherited a confident answer from it.
        output = run_index_producer(
            tmp_path,
            [
                _file("sample.bam", ".bam", "1" * 32, "e1"),
                _file("sample.bam", ".bam", "2" * 32, "e2"),
                _file("sample.bam.bai", ".bai", "3" * 32, "e3"),
            ],
        )
        # Neither parent is named — not the first, not the second, not a coin flip.
        _assert_declined(output, "sample.bam.bai")
        assert len(output["unmatched_files"]) == 1
        entry = output["unmatched_files"][0]
        assert entry["file_name"] == "sample.bam.bai"
        assert entry["reason"] == AMBIGUOUS_PARENT
        assert entry["ambiguous_candidate"] == "sample.bam"
        assert entry["files_sharing_that_name"] == 2
        assert output["metadata"]["details"]["ambiguous_parent"] == 1
        assert output["metadata"]["details"]["unmatched"] == 0

    def test_same_name_in_another_dataset_is_not_ambiguous(self, tmp_path):
        """The lookup key is per dataset, so a name reused across datasets still matches."""
        output = run_index_producer(
            tmp_path,
            [
                _file("sample.bam", ".bam", "1" * 32, "e1"),
                _file("sample.bam", ".bam", "2" * 32, "e2", dataset_id="ds2"),
                _file("sample.bam.bai", ".bai", "3" * 32, "e3"),
            ],
        )
        assert output["unmatched_files"] == []
        assert len(output["classifications"]) == 1
        record = output["classifications"][0]
        assert record["generated_by"]["inputs"][0]["parent_key"] == _fid("1" * 32)

    def test_does_not_fall_through_to_a_later_candidate(self, tmp_path):
        """An ambiguous first candidate declines; it does not take the next one (#438).

        `sample.tbi` is a Pattern 2 name, so `get_parent_candidates` offers several
        parents in `INDEX_TO_PARENT` order — `.vcf.gz` before `.bed.gz`. The `.vcf.gz`
        name covers two files, so no parent is taken. Falling through to the unique
        `.bed.gz` would resume guessing with a *worse* reading of the name, which is
        what this issue forbids, and this test is what fails if someone does.
        """
        output = run_index_producer(
            tmp_path,
            [
                _file("sample.vcf.gz", ".vcf.gz", "1" * 32, "e1"),
                _file("sample.vcf.gz", ".vcf.gz", "2" * 32, "e2"),
                _file("sample.bed.gz", ".bed.gz", "3" * 32, "e3"),
                _file("sample.tbi", ".tbi", "4" * 32, "e4"),
            ],
        )
        # The fall-through parent, `sample.bed.gz`, must not be named: the stopping rule.
        _assert_declined(output, "sample.tbi")
        entry = output["unmatched_files"][0]
        assert entry["reason"] == AMBIGUOUS_PARENT
        assert entry["ambiguous_candidate"] == "sample.vcf.gz"
        assert "sample.bed.gz" in entry["candidates_tried"]

    def test_ambiguity_is_judged_on_the_first_candidate_present(self, tmp_path):
        """The candidate that decides is the first one present, not the first one tried."""
        # No `sample.vcf.gz` at all, so the first *present* candidate is .bed.gz.
        output = run_index_producer(
            tmp_path,
            [
                _file("sample.bed.gz", ".bed.gz", "1" * 32, "e1"),
                _file("sample.bed.gz", ".bed.gz", "2" * 32, "e2"),
                _file("sample.tbi", ".tbi", "3" * 32, "e3"),
            ],
        )
        _assert_declined(output, "sample.tbi")
        entry = output["unmatched_files"][0]
        assert entry["reason"] == AMBIGUOUS_PARENT
        assert entry["ambiguous_candidate"] == "sample.bed.gz"
        assert entry["files_sharing_that_name"] == 2
        # Two files with the literally same name still list one: `parent_names_matched`
        # is on every ambiguous entry, so a reader tells a case collision from a plain
        # duplicate by its length rather than by its absence (#455).
        assert entry["parent_names_matched"] == ["sample.bed.gz"]


def _assert_edge(output, index_name, parent_name, parent_md5):
    """`index_name` took `parent_name` as its parent.

    Also asserts the run declined nothing at all, which for these one-index fixtures is
    the same statement: if this file had taken no parent it would be listed there.
    """
    records = [r for r in output["classifications"] if r["file_name"] == index_name]
    assert len(records) == 1, f"{index_name} should get exactly one record"
    record = records[0]
    assert output["unmatched_files"] == []
    # The edge names the parent as the catalog spells it, not as the candidate that
    # found it — see `get_parent_candidates` on why a candidate is only a probe.
    step = record["generated_by"]
    [edge] = step["inputs"]
    assert edge["parent_file"] == parent_name
    # Grounded by the parent's record key, not its md5 (ADR-0002 decision 2, #356).
    assert edge["parent_key"] == _fid(parent_md5)
    [named] = edge["named_by"]
    assert (step["activity"], edge["role"], named["source_type"], named["rule_id"]) == (
        "IndexActivity",
        "indexed",
        "filename_rule",
        "index_by_name",
    )
    # The parent's kind still resolves off an upper-case extension, because
    # `FileName.parse` lowers the extension it returns.
    assert record["generated_by"]["inputs"][0]["parent_kind"] == "alignment"


class TestMixedCaseNames:
    """Parent lookup folds case, so an index and its parent may disagree about it (#455).

    Nothing covered mixed case before this, and nothing in the corpus exercises it today
    — these are fixtures, not samples. The bug they pin: a Pattern 2 candidate is built by
    appending an extension from the lowercase-keyed `INDEX_TO_PARENT`, so `SAMPLE.BAI`
    yields `SAMPLE.bam`, which an exact lookup could never match against a real
    `SAMPLE.BAM`. The file was then declined for a missing parent that was present.
    """

    def test_pattern2_index_finds_a_differently_cased_parent(self, tmp_path):
        """`SAMPLE.BAI` -> `Sample.Bam`. The issue's bug: this declined before #455.

        The parent is cased differently from the index file *and* from the candidate
        built for it (`SAMPLE.bam`), so this also pins that the row takes the matched
        file's own name rather than the probe's spelling.
        """
        output = run_index_producer(
            tmp_path,
            [
                _file("Sample.Bam", ".bam", "1" * 32, "e1"),
                _file("SAMPLE.BAI", ".BAI", "2" * 32, "e2"),
            ],
        )
        _assert_edge(output, "SAMPLE.BAI", "Sample.Bam", "1" * 32)

    def test_pattern1_index_finds_a_differently_cased_parent(self, tmp_path):
        """`SAMPLE.BAM.BAI` -> `sample.bam`.

        A Pattern 1 candidate is a slice of the index file's own name, so it was already
        spelled like a real sibling — but only like *that* sibling. This is the guard that
        folding did not disturb the pattern that already worked, and that it now also
        reaches a parent spelled the other way.
        """
        output = run_index_producer(
            tmp_path,
            [
                _file("sample.bam", ".bam", "1" * 32, "e1"),
                _file("SAMPLE.BAM.BAI", ".BAI", "2" * 32, "e2"),
            ],
        )
        _assert_edge(output, "SAMPLE.BAM.BAI", "sample.bam", "1" * 32)

    def test_two_parents_differing_only_by_case_are_ambiguous(self, tmp_path):
        """The one decline folding creates: neither parent is picked (#438 read for case).

        `sample.bam` and `SAMPLE.BAM` are two files an exact lookup told apart. Folded,
        the name identifies neither, so the index takes no parent rather than the one that
        happens to match literally — the same rule as for a name two files share.
        """
        output = run_index_producer(
            tmp_path,
            [
                _file("sample.bam", ".bam", "1" * 32, "e1"),
                _file("SAMPLE.BAM", ".bam", "2" * 32, "e2"),
                _file("sample.bam.bai", ".bai", "3" * 32, "e3"),
            ],
        )
        _assert_declined(output, "sample.bam.bai")
        assert len(output["unmatched_files"]) == 1
        entry = output["unmatched_files"][0]
        assert entry["reason"] == AMBIGUOUS_PARENT
        assert entry["ambiguous_candidate"] == "sample.bam"
        assert entry["files_sharing_that_name"] == 2
        # Both spellings, which is what says case was the difference here.
        assert entry["parent_names_matched"] == ["SAMPLE.BAM", "sample.bam"]

    def test_an_upper_case_index_with_no_parent_still_reports_no_parent(self, tmp_path):
        """Folding widens what matches; it does not invent a parent that is absent.

        The `candidates_tried` echo is the end-to-end half of
        `test_candidates_keep_the_casing_they_were_built_with`: the diagnostic reports the
        probe as it was built, not the folded key it was looked up by.
        """
        output = run_index_producer(tmp_path, [_file("ORPHAN.BAM.BAI", ".BAI", "1" * 32, "e1")])
        _assert_declined(output, "ORPHAN.BAM.BAI")
        entry = output["unmatched_files"][0]
        assert entry["reason"] == NO_MATCHING_PARENT
        assert entry["candidates_tried"] == ["ORPHAN.BAM"]

    def test_candidates_keep_the_casing_they_were_built_with(self):
        """`get_parent_candidates` does not lower the name; the lookup folds instead."""
        assert get_parent_candidates("SAMPLE.BAM.BAI", ".BAI") == ["SAMPLE.BAM"]
        assert get_parent_candidates("SAMPLE.BAI", ".BAI") == ["SAMPLE" + ext for ext in INDEX_TO_PARENT[".bai"]]

    def test_a_drifted_bystander_name_does_not_take_the_producer_down(self, tmp_path):
        """Folding reads every record in the dataset, not only the index files (#455).

        An exact key took a drifted non-string `file_name` as-is and `.lower()` does not,
        so without the coercion one bystander record anywhere in a dataset would raise
        and lose the whole producer. It cannot become a parent either way: no candidate
        probe equals `"12345"`.

        This is only about a record this producer does *not* classify. A drifted name on
        an index file still raises — see
        `test_a_drifted_name_on_a_file_this_producer_owns_still_raises`.
        """
        output = run_index_producer(
            tmp_path,
            [
                {**_file("placeholder", ".bam", "1" * 32, "e1"), "file_name": 12345},
                _file("sample.bam.bai", ".bai", "2" * 32, "e2"),
            ],
        )
        entry = output["unmatched_files"][0]
        assert entry["file_name"] == "sample.bam.bai"
        assert entry["reason"] == NO_MATCHING_PARENT

    def test_a_drifted_name_on_a_file_this_producer_owns_still_raises(self, tmp_path):
        """A drifted name on a file this producer classifies fails loudly, as elsewhere.

        `route` falls back to `file_format` when the name claims nothing, so a record with
        a drifted `file_name` and an index `file_format` is routed here. It raises, which
        is what the three sibling filename producers do through `FileInfo.from_filename`,
        and what lets `OutputRecord.from_record` promise that no producer hands it a
        drifted `file_name` for a field typed `str`. Coercing here instead would write a
        row whose `file_name` is an int, swallowing a drift that currently fails loudly.
        """
        with pytest.raises(AttributeError):
            run_index_producer(
                tmp_path,
                [{**_file("placeholder", ".bai", "1" * 32, "e1"), "file_name": 67890}],
            )


class TestEverySlot:
    """Both kinds of record keep every slot, in field order (#580)."""

    def test_a_matched_index_keeps_every_slot(self, tmp_path):
        output = run_index_producer(
            tmp_path,
            [_file("sample.bam", ".bam", "1" * 32, "e1"), _file("sample.bam.bai", ".bai", "2" * 32, "e2")],
        )
        _assert_matched(output, "sample.bam.bai")

    def test_a_declined_index_keeps_every_slot(self, tmp_path):
        output = run_index_producer(tmp_path, [_file("orphan.bai", ".bai", "3" * 32, "e3")])
        [record] = output["classifications"]
        assert list(record["classifications"]) == list(CLASSIFICATION_FIELDS)
        assert record["classifications"]["reference_assembly"]["status"] == NOT_CLASSIFIED
