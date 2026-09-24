"""Tests for index file metadata propagation."""

import json

import pytest
from classify_index_files import (
    AMBIGUOUS_PARENT,
    NO_MATCHING_PARENT,
    get_parent_candidates,
    load_classifications,
    parent_kind_of,
    propagate_to_index_files,
)

from meta_disco.models import (
    CLASSIFIED,
    CONFLICT,
    NOT_APPLICABLE,
    NOT_CLASSIFIED,
    build_field_entry,
    field_status,
    field_value,
)
from meta_disco.pipeline import SOURCE_RECORD_KEYS
from meta_disco.producers import INDEX_TO_PARENT
from tests.metadata_fixtures import write_metadata as _write_metadata
from tests.producer_sweep import run_index_producer
from tests.run_fixtures import OUTPUT_FILE, output_record, write_run

ANVIL_KEY = SOURCE_RECORD_KEYS["anvil"]
HPRC_KEY = SOURCE_RECORD_KEYS["hprc"]


def _assert_declined(output: dict, file_name: str) -> dict:
    """An index file that took no parent: `index` by extension, the rest unknown.

    `data_type` is knowable without a parent — the extension says so — and the other
    four are properties of the data the index points into, so they are not_classified
    rather than not_applicable: they apply, and nothing here can determine them (#438).
    """
    records = [r for r in output["classifications"] if r["file_name"] == file_name]
    assert len(records) == 1, f"{file_name} should get exactly one record"
    cls = records[0]["classifications"]
    assert field_status(cls, "data_type") == CLASSIFIED
    assert field_value(cls, "data_type") == "index"
    for fld in ("data_modality", "platform", "reference_assembly", "assay_type"):
        assert field_status(cls, fld) == NOT_CLASSIFIED, f"{fld} should be not_classified, not asserted"
    # A declined record still carries a typed edge — the extension says it indexes
    # something — with the grounding null (#450).
    assert records[0]["derived_from"]["relation"] == "index_of"
    assert records[0]["derived_from"]["parent_file"] is None
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

    Carries `file_id` because the input contract requires it and the parent join
    keys on it (`classify_index_files.load_classifications`). It defaults to `_fid(md5)`,
    so a fixture's two sides join without either spelling an identifier; pass it
    explicitly where two records share one md5.
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


_PARENT_VALUES = {
    "data_modality": "genomic",
    "data_type": "alignments",
    "platform": "ILLUMINA",
    "assay_type": "WGS",
}


def _classified_record(
    md5: str, assembly, file_name: str = "sample.bam", file_id: str | None = None, build: dict | None = None, **dims
) -> dict:
    """A parent classification whose ``reference_assembly`` is ``assembly``.

    The row and its entries come from :func:`run_fixtures.output_record`, which builds
    every entry through :func:`models.build_field_entry` — the single place that
    assembles the ``{value, status, evidence}`` shape — so the fixture follows the
    output shape rather than restating it. What this adds is the parent's identity
    and the defaults in ``_PARENT_VALUES``.

    Any other dimension may be overridden by keyword, as for
    :func:`run_fixtures.classifications`; ``reference_assembly`` is the positional
    ``assembly`` and is refused as a keyword, so a row cannot name two. ``build`` is the
    resolved build detail (#340) carried beside the reference_assembly value.

    ``file_id`` is what the index producer joins a parent on, so a fixture without
    one would be joined by nothing.
    """
    if "reference_assembly" in dims:
        raise TypeError("pass the assembly positionally, not as reference_assembly=")
    record = output_record(
        file_name, md5, file_id=file_id or _fid(md5), **{**_PARENT_VALUES, "reference_assembly": assembly, **dims}
    )
    if build:
        record["classifications"]["reference_assembly"] = build_field_entry(assembly, detail={"build": build})
    return record


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
    assert parent_kind_of("NA20872.haplotypeCalls.er.raw.g.vcf.gz", ".tbi") == "variants"
    assert parent_kind_of("HG002.vcf.gz", ".tbi") == "variants"


def test_a_parent_whose_kind_is_genuinely_unknown_stays_none():
    """The fallback must not guess: `.txt.gz` is a category with no parent_kind term,
    and a `.tbi` with no parent indexes several kinds."""
    assert parent_kind_of("annotations.txt.gz", ".tbi") is None
    assert parent_kind_of(None, ".tbi") is None
    # ...while an index extension that declares one kind answers without a parent.
    assert parent_kind_of(None, ".bai") == "alignment"


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


class TestLoadClassifications:
    """Test that load_classifications loads from multiple sources."""

    def test_loads_from_single_file(self, tmp_path):
        """Load classifications from one JSON file."""
        cls_file = write_run(tmp_path, [_classified_record("abc123", "GRCh38")]) / OUTPUT_FILE
        result = load_classifications(cls_file, key=ANVIL_KEY)
        assert _fid("abc123") in result
        assert result[_fid("abc123")]["data_modality"] == "genomic"
        assert result[_fid("abc123")]["platform"] == "ILLUMINA"

    def test_loads_from_multiple_files(self, tmp_path):
        """Load classifications from BAM + BED files."""
        bam_file = write_run(tmp_path, [_classified_record("bam_md5", "GRCh38")], fname="bam.json") / "bam.json"
        bed = _classified_record(
            "bed_md5",
            "GRCh38",
            "sample.regions.bed.gz",
            data_type="annotations",
            platform=NOT_CLASSIFIED,
            assay_type=NOT_CLASSIFIED,
        )
        bed_file = write_run(tmp_path, [bed], fname="bed.json") / "bed.json"
        result = load_classifications(bam_file, bed_file, key=ANVIL_KEY)
        bed_key = _fid("bed_md5")
        assert _fid("bam_md5") in result
        assert bed_key in result
        assert result[bed_key]["data_modality"] == "genomic"
        # The map holds only what an index inherits. `data_type` is not inherited
        # since #437 — an index has its own — so the parent's is not read at all.
        assert "data_type" not in result[bed_key]
        assert set(result[bed_key]) == {
            "data_modality",
            "assay_type",
            "platform",
            "reference_assembly",
            "detail",
        }

    def test_skips_missing_files(self, tmp_path):
        """Missing files are silently skipped."""
        result = load_classifications(tmp_path / "nonexistent.json", key=ANVIL_KEY)
        assert result == {}

    @pytest.mark.parametrize(
        "document",
        [{"metadata": {}}, {"classifications": None}, {"classifications": {"a": 1}}, ["bare", "list"], "text"],
        ids=["no-list-key", "null-list", "object-not-list", "bare-list", "scalar"],
    )
    def test_a_file_that_is_not_a_classification_file_is_refused(self, tmp_path, document):
        """A present file with no record list raises rather than reading as empty.

        Read as empty, every index parented in it would inherit nothing and the
        catch-all would write its files a second row; only an absent file means
        "that producer did not run".
        """
        cls_file = tmp_path / "bam_classifications.json"
        cls_file.write_text(json.dumps(document))
        with pytest.raises(ValueError, match="not a classification file"):
            load_classifications(cls_file, key=ANVIL_KEY)

    def test_a_legacy_results_envelope_is_read(self, tmp_path):
        """The parent map reads the legacy `results` key too, as the catch-all does."""
        cls_file = tmp_path / "bam_classifications.json"
        cls_file.write_text(json.dumps({"results": [_classified_record("a" * 32, "GRCh38", "sample.bam")]}))
        assert set(load_classifications(cls_file, key=ANVIL_KEY)) == {_fid("a" * 32)}

    def test_a_row_that_is_not_an_object_is_refused(self, tmp_path):
        cls_file = write_run(tmp_path, ["stray"]) / OUTPUT_FILE
        with pytest.raises(ValueError, match="row is not an object"):
            load_classifications(cls_file, key=ANVIL_KEY)

    def test_csi_inherits_from_bed_parent(self, tmp_path):
        """End-to-end: a .csi index file inherits classification from its .bed.gz parent.

        This is the regression that #41 fixes — previously BED classifications were
        not loaded, so .csi files for .bed.gz parents got None for all fields."""
        output = run_index_producer(
            tmp_path,
            [
                _file("HG03652.regions.bed.gz", ".bed.gz", "3" * 32, "entry_bed"),
                _file("HG03652.regions.bed.gz.csi", ".csi", "4" * 32, "entry_csi"),
            ],
            [
                _classified_record(
                    "3" * 32,
                    "CHM13",
                    "HG03652.regions.bed.gz",
                    data_type="annotations",
                    platform=NOT_CLASSIFIED,
                    assay_type=NOT_CLASSIFIED,
                )
            ],
        )
        index_cls = output["classifications"]
        assert len(index_cls) == 1
        csi = index_cls[0]
        assert csi["file_name"] == "HG03652.regions.bed.gz.csi"
        assert csi["derived_from"]["parent_file"] == "HG03652.regions.bed.gz"
        # `.csi` indexes variants or intervals, so the type alone cannot say which;
        # the matched parent does.
        assert csi["derived_from"]["parent_kind"] == "intervals"
        cls = csi["classifications"]
        assert field_value(cls, "data_modality") == "genomic"
        # The parent is annotations; the index is an index (#437). The parent is still
        # reachable, through the `derived_from` edge.
        assert field_value(cls, "data_type") == "index"
        assert field_value(cls, "reference_assembly") == "CHM13"
        assert cls["data_modality"]["evidence"][0]["rule_id"] == "inherited_from_parent"
        # Propagated entries carry the Stage 2 `status` key (epic #116), like to_output_dict.
        assert "status" in cls["data_modality"]
        assert field_status(cls, "data_modality") == CLASSIFIED

    def test_an_hprc_parent_joins_on_the_url_hash(self, tmp_path):
        """Where the source declares the checksum field its key, the join uses it.

        The HPRC catalog issues no `file_id`; what it guarantees unique is the file's
        URL, whose hash its builder writes as the checksum (`pipeline.SOURCE_RECORD_KEYS`).
        Read off the envelope rather than guessed from which fields a record carries.
        """
        parent = _file("sample.bam", ".bam", "a" * 32, "e1")
        index = _file("sample.bam.bai", ".bai", "b" * 32, "e2")
        for record in (parent, index):
            del record["file_id"]
        metadata_file = _write_metadata(tmp_path / "metadata.json", [parent, index], repository="hprc")

        cls = _classified_record("a" * 32, "GRCh38", "sample.bam")
        del cls["file_id"]
        cls_file = write_run(tmp_path, [cls]) / OUTPUT_FILE

        output_file = tmp_path / "out.json"
        propagate_to_index_files(metadata_file, [cls_file], output_file)
        rows = {r["file_name"]: r for r in json.loads(output_file.read_text())["classifications"]}
        assert field_value(rows["sample.bam.bai"]["classifications"], "reference_assembly") == "GRCh38"

    def test_a_parent_row_without_the_key_is_refused(self, tmp_path):
        """A parent row missing the source's key raises rather than being left out.

        Left out, the index file it parents would inherit nothing and no one would
        know. Under both keys, so the parent map is pinned to the shared reader for
        HPRC too, not only for the AnVIL default the fixtures write.
        """
        cls = _classified_record("a" * 32, "GRCh38", "sample.bam")
        cls["file_id"] = None
        cls_file = write_run(tmp_path, [cls]) / OUTPUT_FILE
        with pytest.raises(ValueError, match="file_id"):
            load_classifications(cls_file, key=ANVIL_KEY)
        del cls["md5sum"]
        write_run(tmp_path, [cls])
        with pytest.raises(ValueError, match="md5sum"):
            load_classifications(cls_file, key=HPRC_KEY)

    def test_a_key_two_parent_rows_carry_is_refused(self, tmp_path):
        """Two rows with one key raise rather than the last one winning.

        Last-wins on a shared key is the order-dependent choice #486 removed; a repeat
        can only reach here on a run that bypassed the input gate, and the post-run
        one-row-per-file check would fail it later — after this producer had written.
        """
        rows = [
            _classified_record("a" * 32, "GRCh38", "one.bam", file_id="fid-dup"),
            _classified_record("b" * 32, "CHM13", "two.bam", file_id="fid-dup"),
        ]
        cls_file = write_run(tmp_path, rows) / OUTPUT_FILE
        with pytest.raises(ValueError, match=r"file_id 'fid-dup' is carried by more than one.*'two\.bam'"):
            load_classifications(cls_file, key=ANVIL_KEY)

    def test_a_matched_parent_with_no_row_says_so_in_the_evidence(self, tmp_path):
        """A parent with no classification row is told apart from one that said nothing.

        A `.txt.gz` under a `.tbi` is written by the catch-all, after this producer, so
        it has no row here. The index still inherits nothing, but its evidence names
        the absent row rather than claiming the parent had no value.
        """
        txt = _file("notes.txt.gz", ".txt.gz", "c" * 32, "e3")
        index = _file("notes.txt.gz.tbi", ".tbi", "b" * 32, "e2")
        output = run_index_producer(tmp_path, [txt, index])
        [row] = [r for r in output["classifications"] if r["file_name"] == "notes.txt.gz.tbi"]
        assert row["derived_from"]["parent_file"] == "notes.txt.gz"
        for fld in ("data_modality", "platform", "reference_assembly", "assay_type"):
            entry = row["classifications"][fld]
            assert field_status(row["classifications"], fld) == NOT_CLASSIFIED
            assert entry["evidence"][0]["reason"] == "No classification row for parent file notes.txt.gz"

    def test_a_parent_row_lacking_a_value_still_says_had_no_value(self, tmp_path):
        parent = _file("sample.bam", ".bam", "a" * 32, "e1")
        index = _file("sample.bam.bai", ".bai", "b" * 32, "e2")
        cls = _classified_record("a" * 32, "GRCh38", "sample.bam", platform=NOT_CLASSIFIED)
        output = run_index_producer(tmp_path, [parent, index], [cls])
        [row] = [r for r in output["classifications"] if r["file_name"] == "sample.bam.bai"]
        assert row["classifications"]["platform"]["evidence"][0]["reason"] == (
            "Parent file sample.bam had no value for platform"
        )

    def test_a_key_two_input_records_carry_is_refused(self, tmp_path):
        """A repeated input key is refused before any parent is joined.

        `load_classifications` catches a repeat only among Phase 1 rows; a duplicate
        whose row the catch-all writes later is absent there, so an index matched to it
        would find the other record's labels under the shared key and inherit them.
        """
        bam = _file("sample.bam", ".bam", "a" * 32, "e1", file_id="fid-dup")
        txt = _file("notes.txt.gz", ".txt.gz", "c" * 32, "e3", file_id="fid-dup")
        index = _file("notes.txt.gz.tbi", ".tbi", "b" * 32, "e2")
        metadata_file = _write_metadata(tmp_path / "metadata.json", [bam, txt, index])
        cls_file = tmp_path / "bam_classifications.json"
        cls_file.write_text(
            json.dumps({"classifications": [_classified_record("a" * 32, "GRCh38", "sample.bam", file_id="fid-dup")]})
        )
        with pytest.raises(ValueError, match=r"1 value\(s\) of file_id are carried by more than one.*fid-dup \(x2\)"):
            propagate_to_index_files(metadata_file, [cls_file], tmp_path / "out.json")

    def test_a_matched_parent_without_the_key_is_refused(self, tmp_path):
        """The guard is symmetric: a drifted key on the *input* parent raises too.

        `file_id` is not classifier-relevant, so a drifted one reaches this producer.
        Matched by name, such a parent would match nothing in the map and the index
        would inherit nothing — the same silent miss, entering by the other side.
        """
        parent = _file("sample.bam", ".bam", "a" * 32, "e1")
        parent["file_id"] = None
        index = _file("sample.bam.bai", ".bai", "b" * 32, "e2")
        metadata_file = _write_metadata(tmp_path / "metadata.json", [parent, index])
        cls_file = write_run(tmp_path, [_classified_record("a" * 32, "GRCh38", "sample.bam")]) / OUTPUT_FILE
        with pytest.raises(ValueError, match=r"'sample\.bam' has file_id None"):
            propagate_to_index_files(metadata_file, [cls_file], tmp_path / "out.json")

    def test_an_envelope_naming_no_repository_is_refused_before_any_record_loads(self, tmp_path):
        """No repository, no key to join on; guessing a field is what #486 removed.

        Refused before the snapshot loads, so nothing — not even `excluded_files.json`
        — is written into the run directory for an input the producer cannot join.
        """
        metadata_file = tmp_path / "metadata.json"
        metadata_file.write_text(json.dumps({"files": [_file("sample.bam.bai", ".bai", "b" * 32, "e2")]}))
        with pytest.raises(ValueError, match=r"metadata\.json.*repository None, which declares no record key"):
            propagate_to_index_files(metadata_file, [], tmp_path / "out.json")
        assert not (tmp_path / "excluded_files.json").exists()

    def test_same_md5_parents_do_not_share_a_classification(self, tmp_path):
        """Two byte-identical parents with different names keep their own answers.

        Keyed by md5 alone, whichever row the producer wrote last won for both, so one
        `.fai` took the other's answer — which one depending on a write order nothing
        guarantees (#486). Keyed on the source's record key, each `.fai` finds the
        parent whose identity it names.
        """
        # One md5 for two files, so `_fid`'s md5-derived default would collapse them —
        # these are the fixtures that pass their ids explicitly. The assembly parent
        # carries the sentinel, which the builder turns into a status with a null value.
        shared_md5 = "7" * 32
        output = run_index_producer(
            tmp_path,
            [
                _file("grch38.fasta", ".fasta", shared_md5, "entry_ref", file_id="fid-ref"),
                _file("Homo_sapiens_assembly38.fasta", ".fasta", shared_md5, "entry_asm", file_id="fid-asm"),
                _file("grch38.fasta.fai", ".fai", "8" * 32, "entry_ref_fai"),
                _file("Homo_sapiens_assembly38.fasta.fai", ".fai", "9" * 32, "entry_asm_fai"),
            ],
            [
                _classified_record(shared_md5, "GRCh38", "grch38.fasta", file_id="fid-ref"),
                _classified_record(shared_md5, NOT_APPLICABLE, "Homo_sapiens_assembly38.fasta", file_id="fid-asm"),
            ],
        )
        rows = {r["file_name"]: r for r in output["classifications"]}
        ref_fai = rows["grch38.fasta.fai"]["classifications"]
        asm_fai = rows["Homo_sapiens_assembly38.fasta.fai"]["classifications"]
        assert field_value(ref_fai, "reference_assembly") == "GRCh38"
        assert field_value(asm_fai, "reference_assembly") is None
        assert field_status(asm_fai, "reference_assembly") == NOT_APPLICABLE

    def test_tbi_inherits_from_vcf_parent(self, tmp_path):
        """End-to-end: a .tbi index inherits from its .vcf.gz parent.

        The parent row is deliberately in the pre-#116 shape — a sentinel or value in
        ``value`` and no ``status`` key — so the reader's derived-status path
        (``models._entry_status`` through ``status_for_value``) is exercised against a
        row a producer wrote before the split. The other parent rows in this file come
        from ``_classified_record`` and carry a ``status``.
        """
        legacy_parent = {
            "md5sum": "7" * 32,
            "file_id": _fid("7" * 32),
            "file_name": "sample.vcf.gz",
            "classifications": {
                "data_modality": {"value": "genomic", "evidence": []},
                "data_type": {"value": "variants.germline", "evidence": []},
                "platform": {"value": "not_classified", "evidence": []},
                "reference_assembly": {"value": "GRCh38", "evidence": []},
                "assay_type": {"value": "not_classified", "evidence": []},
            },
        }
        output = run_index_producer(
            tmp_path,
            [_file("sample.vcf.gz", ".vcf.gz", "7" * 32, "e1"), _file("sample.vcf.gz.tbi", ".tbi", "6" * 32, "e2")],
            [legacy_parent],
        )
        assert len(output["classifications"]) == 1
        cls = output["classifications"][0]["classifications"]
        assert field_value(cls, "data_modality") == "genomic"
        assert field_value(cls, "data_type") == "index"
        assert field_value(cls, "reference_assembly") == "GRCh38"

    def test_bai_inherits_from_bam_parent(self, tmp_path):
        """End-to-end: a .bai index inherits from its .bam parent."""
        output = run_index_producer(
            tmp_path,
            [_file("sample.bam", ".bam", "2" * 32, "e1"), _file("sample.bam.bai", ".bai", "1" * 32, "e2")],
            [_classified_record("2" * 32, "GRCh38", data_modality="transcriptomic.bulk", assay_type="RNA-seq")],
        )
        assert len(output["classifications"]) == 1
        cls = output["classifications"][0]["classifications"]
        assert field_value(cls, "data_modality") == "transcriptomic.bulk"
        assert field_value(cls, "platform") == "ILLUMINA"
        assert field_value(cls, "assay_type") == "RNA-seq"

    def test_bai_inherits_the_parent_reference_build(self, tmp_path):
        """The parent's resolved build (#340) must reach the index record; an
        index that names only the coarse family describes its parent's reference
        less precisely than the parent does."""
        build = {
            "base": "CHM13",
            "version": "v2.0",
            "chr1_m5": "e469247288ceb332aee524caec92bb22",
            "chry_m5": "dd7264df17e7e4a4dac5b0f1f19dcfe0",
            "name": "chm13v2.0.fasta",
        }
        parent = _classified_record("2" * 32, "CHM13", "s.bam", build=build)
        # A row carrying only this one dimension: the parent map must read a missing
        # entry as nothing to inherit rather than raise, so this parent is deliberately
        # partial — the only one in the file that is.
        parent["classifications"] = {"reference_assembly": parent["classifications"]["reference_assembly"]}
        output = run_index_producer(
            tmp_path,
            [_file("s.bam", ".bam", "2" * 32, "e1"), _file("s.bam.bai", ".bai", "1" * 32, "e2")],
            [parent],
        )
        entry = output["classifications"][0]["classifications"]["reference_assembly"]
        assert entry["value"] == "CHM13"
        assert entry["build"] == build

    def test_a_parent_in_conflict_propagates_the_status_not_a_value(self, tmp_path):
        """``field_label`` hands back ``conflict`` as a label; the index record must
        re-emit it as a status with a null value, never as a classified value."""
        output = run_index_producer(
            tmp_path,
            [_file("s.bam", ".bam", "2" * 32, "e1"), _file("s.bam.bai", ".bai", "1" * 32, "e2")],
            [_classified_record("2" * 32, CONFLICT, "s.bam")],
        )
        cls = output["classifications"][0]["classifications"]
        assert field_status(cls, "reference_assembly") == CONFLICT
        assert field_value(cls, "reference_assembly") is None
        assert cls["reference_assembly"]["evidence"][0]["status"] == CONFLICT

    def test_no_matching_parent_goes_to_unmatched(self, tmp_path):
        """Index file with no parent in metadata goes to unmatched_files, not classifications."""
        output = run_index_producer(tmp_path, [_file("orphan.bam.bai", ".bai", "5" * 32, "e1")])
        _assert_declined(output, "orphan.bam.bai")
        assert len(output["unmatched_files"]) == 1
        assert output["unmatched_files"][0]["file_name"] == "orphan.bam.bai"
        assert output["unmatched_files"][0]["reason"] == NO_MATCHING_PARENT
        assert output["metadata"]["details"]["ambiguous_parent"] == 0

    def test_parent_found_but_not_classified(self, tmp_path):
        """Parent exists in metadata but has no classification — index gets not_classified."""
        # The parent is in the metadata but in no classification file.
        output = run_index_producer(
            tmp_path,
            [_file("sample.bam", ".bam", "2" * 32, "e1"), _file("sample.bam.bai", ".bai", "1" * 32, "e2")],
        )
        # Parent filename matched but its key is in no classification file → not_classified,
        # and the evidence says the row was absent, not that the parent had no value.
        assert len(output["classifications"]) == 1
        cls = output["classifications"][0]["classifications"]
        # `data_type` does not depend on the parent being classified — the extension
        # settles it (#437). The other four have nothing to inherit.
        assert field_status(cls, "data_type") == CLASSIFIED
        assert field_value(cls, "data_type") == "index"
        for fld in ["data_modality", "platform", "reference_assembly", "assay_type"]:
            assert field_status(cls, fld) == NOT_CLASSIFIED, f"{fld} should be not_classified"
        assert cls["data_modality"]["evidence"][0]["reason"] == "No classification row for parent file sample.bam"

    def test_ambiguous_parent_takes_no_parent_at_all(self, tmp_path):
        """Two files sharing the name an index points at: no parent is chosen (#438)."""
        # Same name, different files — as ANVIL_T2T_CHRY calls one sample against both
        # CHM13v2 and GRCh38 and stores the outputs under different paths. Both candidate
        # parents are classified, and they disagree: whichever the old lookup kept, the
        # index would have inherited a confident answer from it.
        output = run_index_producer(
            tmp_path,
            [
                _file("sample.bam", ".bam", "1" * 32, "e1"),
                _file("sample.bam", ".bam", "2" * 32, "e2"),
                _file("sample.bam.bai", ".bai", "3" * 32, "e3"),
            ],
            [_classified_record("1" * 32, "GRCh38"), _classified_record("2" * 32, "CHM13")],
        )
        # Neither parent's answer reaches it — not GRCh38, not CHM13, not a coin flip.
        record = _assert_declined(output, "sample.bam.bai")
        assert record["classifications"]["reference_assembly"]["value"] is None
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
            [_classified_record("1" * 32, "GRCh38")],
        )
        assert output["unmatched_files"] == []
        assert len(output["classifications"]) == 1
        record = output["classifications"][0]
        assert record["derived_from"]["parent_md5sum"] == "1" * 32
        assert record["classifications"]["reference_assembly"]["value"] == "GRCh38"

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
            [
                _classified_record("1" * 32, "GRCh38", "sample.vcf.gz"),
                _classified_record("2" * 32, "CHM13", "sample.vcf.gz"),
                # The fall-through parent, deliberately a third assembly: if this
                # value ever reaches the index file, the stopping rule is broken.
                _classified_record("3" * 32, "GRCh37", "sample.bed.gz"),
            ],
        )
        # GRCh37 is the fall-through parent's answer; it must not appear anywhere.
        record = _assert_declined(output, "sample.tbi")
        assert record["classifications"]["reference_assembly"]["value"] is None
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
            [
                _classified_record("1" * 32, "GRCh38", "sample.bed.gz"),
                _classified_record("2" * 32, "CHM13", "sample.bed.gz"),
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


def _assert_inherited(output, index_name, parent_name, parent_md5):
    """`index_name` took `parent_name` as its parent and inherited from it.

    Also asserts the run declined nothing at all, which for these one-index fixtures is
    the same statement: if this file had taken no parent it would be listed there.
    """
    records = [r for r in output["classifications"] if r["file_name"] == index_name]
    assert len(records) == 1, f"{index_name} should get exactly one record"
    record = records[0]
    assert output["unmatched_files"] == []
    assert field_value(record["classifications"], "reference_assembly") == "GRCh38"
    # The edge names the parent as the catalog spells it, not as the candidate that
    # found it — see `get_parent_candidates` on why a candidate is only a probe.
    assert record["derived_from"]["parent_file"] == parent_name
    assert record["derived_from"]["parent_md5sum"] == parent_md5
    # The parent's kind still resolves off an upper-case extension, because
    # `FileName.parse` lowers the extension it returns.
    assert record["derived_from"]["parent_kind"] == "alignment"


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
            [_classified_record("1" * 32, "GRCh38", "Sample.Bam")],
        )
        _assert_inherited(output, "SAMPLE.BAI", "Sample.Bam", "1" * 32)

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
            [_classified_record("1" * 32, "GRCh38")],
        )
        _assert_inherited(output, "SAMPLE.BAM.BAI", "sample.bam", "1" * 32)

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
            [_classified_record("1" * 32, "GRCh38"), _classified_record("2" * 32, "CHM13", "SAMPLE.BAM")],
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
