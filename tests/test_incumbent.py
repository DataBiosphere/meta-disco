"""The incumbent comparison: what AnVIL declares, beside what a run concluded (#424).

Covers the three joints the feature has: the declaration surviving from an input
record into the output envelope (``records.build_declared``), the recommendation for
one file and one dimension (``incumbent.recommendation``), and the report gathered
over a run directory (``incumbent.gather``).
"""

import json
import pathlib

import pytest

from meta_disco.incumbent import (
    ADD,
    COMPARE,
    MULTI_VALUE_SEP,
    NONE,
    TAKE_AZUL,
    gather,
    recommendation,
    render_report,
    render_tsv,
    spoke,
)
from meta_disco.models import NOT_APPLICABLE, NOT_CLASSIFIED
from meta_disco.pipeline import incumbent_source
from meta_disco.records import ClassifierRecord, InvalidRecord, OutputRecord, build_declared
from tests.metadata_fixtures import valid_record


def _entry(value=None, status=None):
    """One dimension entry in the output's per-field layout."""
    return {"value": value, "status": status or ("classified" if value else NOT_CLASSIFIED)}


def _record(name, *, modality=None, assembly=None, declared=None, dataset="AnVIL_IGVF_Mouse_R1"):
    """One output record as a run writes it."""
    return {
        "file_name": name,
        "md5sum": name,
        "entry_id": name,
        "dataset_title": dataset,
        "classifications": {"data_modality": _entry(modality), "reference_assembly": _entry(assembly)},
        "declared": declared,
    }


def _write_run(run_dir, records):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "bam_classifications.json").write_text(json.dumps({"metadata": {}, "classifications": records}))
    return run_dir


class TestBuildDeclared:
    def test_a_declaration_is_transcribed_verbatim_as_a_list(self):
        block = build_declared(
            {
                "data_modality": ["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"],
                "reference_assembly": None,
            },
            "anvil/anvil15",
        )
        assert block is not None
        assert block["data_modality"] == ["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"]
        assert block["reference_assembly"] is None
        assert block["source"] == "anvil/anvil15"

    def test_a_file_that_declared_nothing_gets_no_block(self):
        assert build_declared({"data_modality": None, "reference_assembly": None}, "anvil/anvil15") is None

    def test_in_vocabulary_names_only_the_values_that_are_terms(self):
        block = build_declared(
            {"data_modality": ["genomic", "single-nucleus ATAC-seq"], "reference_assembly": ["GRCm39"]}, None
        )
        assert block is not None
        # `genomic` is a data_modality_enum term; the other two are not.
        assert block["in_vocabulary"] == {"data_modality": ["genomic"], "reference_assembly": []}

    def test_every_value_the_corpus_declares_today_is_outside_our_vocabulary(self):
        # The measured state at #424, and the reason the translation table (#414) is
        # owed: not one incumbent value is a term this schema knows.
        block = build_declared(
            {
                "data_modality": ["single-nucleus RNA sequencing assay", "single-nucleus ATAC-seq"],
                "reference_assembly": ["GRCh38 + Gencode40", "GRCm39"],
            },
            "anvil/anvil15",
        )
        assert block is not None
        assert block["in_vocabulary"] == {"data_modality": [], "reference_assembly": []}

    def test_a_dimension_that_declared_nothing_is_absent_from_in_vocabulary(self):
        block = build_declared({"data_modality": ["genomic"], "reference_assembly": None}, None)
        assert block is not None
        assert set(block["in_vocabulary"]) == {"data_modality"}


class TestDeclarationReachesTheOutput:
    def test_a_classifier_record_carries_it_into_the_envelope(self):
        item = ClassifierRecord.from_record(valid_record(reference_assembly=["GRCh38 + Gencode40"]))
        out = OutputRecord.from_work_item(item, {}, source="anvil/anvil15").to_dict()
        assert out["declared"]["reference_assembly"] == ["GRCh38 + Gencode40"]
        assert out["declared"]["in_vocabulary"] == {"reference_assembly": []}

    def test_a_validation_failed_record_still_reports_what_was_declared(self):
        # Failing our contract on file_size does not stop AnVIL from declaring a
        # modality, and the row must still say so.
        item = InvalidRecord.from_record(valid_record(file_size="big", data_modality=["genomic"]), ["file_size: bad"])
        out = OutputRecord.from_work_item(item, {}, source="anvil/anvil15").to_dict()
        assert out["declared"]["data_modality"] == ["genomic"]

    def test_the_envelope_carries_the_key_even_when_nothing_was_declared(self):
        item = ClassifierRecord.from_record(valid_record())
        out = OutputRecord.from_work_item(item, {}, source="anvil/anvil15").to_dict()
        assert "declared" in out and out["declared"] is None


class TestIncumbentSource:
    def test_it_names_the_catalog_the_snapshot_recorded(self):
        assert incumbent_source({"catalog": "anvil15"}) == "anvil/anvil15"

    @pytest.mark.parametrize("metadata", [{}, {"catalog": None}, {"catalog": ""}])
    def test_an_input_that_named_no_catalog_leaves_the_incumbent_unnamed(self, metadata):
        # An unnamed incumbent is a fact; a guessed one is the drift #335 exists to catch.
        assert incumbent_source(metadata) is None


class TestRecommendation:
    @pytest.mark.parametrize(
        "declared,label,expected",
        [
            (None, "genomic", ADD),
            (["GRCm39"], NOT_CLASSIFIED, TAKE_AZUL),
            (["GRCh38 + Gencode40"], "GRCh38", COMPARE),
            (None, NOT_CLASSIFIED, NONE),
            (None, None, NONE),
        ],
    )
    def test_the_four_states(self, declared, label, expected):
        assert recommendation(declared, label) == expected

    def test_not_applicable_counts_as_us_having_spoken(self):
        # The four .bai/.tbi rows: AnVIL carries the set's modality, we say the
        # dimension does not apply. That is a comparison to make, not a gap to fill —
        # filing it under take_azul would claim we had no opinion.
        assert spoke(NOT_APPLICABLE)
        assert recommendation(["single-nucleus ATAC-seq"], NOT_APPLICABLE) == COMPARE

    def test_not_classified_is_the_only_silence(self):
        assert not spoke(NOT_CLASSIFIED)
        assert not spoke(None)


class TestGather:
    def test_it_counts_every_file_and_rows_only_the_declared_ones(self, tmp_path):
        run = _write_run(
            tmp_path / "run",
            [
                _record("a.bam", modality="genomic"),
                _record(
                    "b.bam",
                    declared=build_declared(
                        {"data_modality": ["single-nucleus ATAC-seq"], "reference_assembly": None}, "anvil/anvil15"
                    ),
                ),
            ],
        )
        report = gather(run)
        assert report.files == 2
        assert report.declared_files == 1
        assert report.sources == {"anvil/anvil15"}
        assert report.counts[("AnVIL_IGVF_Mouse_R1", "data_modality", ADD)] == 1
        assert report.counts[("AnVIL_IGVF_Mouse_R1", "data_modality", TAKE_AZUL)] == 1
        # b.bam declared no assembly and we classified none: neither side spoke.
        assert report.counts[("AnVIL_IGVF_Mouse_R1", "reference_assembly", NONE)] == 2

    def test_a_file_written_twice_is_counted_once(self, tmp_path):
        run = tmp_path / "run"
        run.mkdir()
        record = _record("t.tar", modality="genomic")
        for name in ("tar_classifications.json", "auxiliary_classifications.json"):
            (run / name).write_text(json.dumps({"metadata": {}, "classifications": [record]}))
        report = gather(run)
        assert report.files == 1
        assert report.duplicate_records == 1

    def test_compare_rows_group_by_the_value_pair_they_share(self, tmp_path):
        declared = build_declared(
            {"data_modality": None, "reference_assembly": ["GRCh38 + Gencode40"]}, "anvil/anvil15"
        )
        run = _write_run(
            tmp_path / "run",
            [
                _record(f"e{i}.bam", assembly="GRCh38", declared=declared, dataset="AnVIL_ENCORE_RS293")
                for i in range(3)
            ],
        )
        pairs = gather(run).compare_pairs()
        assert list(pairs) == [("reference_assembly", "GRCh38 + Gencode40", "GRCh38")]
        assert len(pairs[("reference_assembly", "GRCh38 + Gencode40", "GRCh38")]) == 3

    def test_a_multi_valued_declaration_is_rejoined_into_the_cell_azul_published(self, tmp_path):
        declared = build_declared(
            {
                "data_modality": ["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"],
                "reference_assembly": None,
            },
            "anvil/anvil15",
        )
        run = _write_run(
            tmp_path / "run", [_record("x.h5ad", modality="transcriptomic.single_cell", declared=declared)]
        )
        [row] = [r for r in gather(run).rows if r.slot == "data_modality"]
        assert row.azul_cell == "single-nucleus ATAC-seq || single-nucleus RNA sequencing assay"
        assert row.recommendation == COMPARE
        assert row.vocabulary_standing == "no"


class TestRender:
    def test_the_tsv_has_one_row_per_declared_file_and_dimension(self, tmp_path):
        declared = build_declared({"data_modality": ["GRCm39"], "reference_assembly": ["GRCm39"]}, "anvil/anvil15")
        run = _write_run(tmp_path / "run", [_record("m.bam", declared=declared), _record("n.bam", modality="genomic")])
        lines = render_tsv(gather(run)).strip().split("\n")
        assert lines[0].split("\t") == [
            "file_name",
            "dataset",
            "slot",
            "azul_value",
            "our_value",
            "recommendation",
            "azul_in_vocab",
        ]
        # Only the declared file appears, once per dimension.
        assert len(lines) == 3
        assert all(line.startswith("m.bam\t") for line in lines[1:])

    def test_the_report_names_the_vocabulary_gap(self, tmp_path):
        declared = build_declared({"data_modality": None, "reference_assembly": ["GRCm39"]}, "anvil/anvil15")
        run = _write_run(tmp_path / "run", [_record("m.bam", declared=declared)])
        text = render_report(gather(run))
        assert "`GRCm39`" in text
        assert "1 of 1 distinct incumbent values are terms our vocabulary does not have" in text
        assert "anvil/anvil15" in text


class TestEveryProducerCarriesTheDeclaration:
    """Every `*_classifications.json` must carry `declared`, not just the header pipeline.

    The claim is about the whole run, and the catch-all is what makes it non-trivial:
    it classifies every input record no earlier producer named, and it alone holds
    5,817 of the corpus's 11,231 declared files. Wiring only the header pipeline
    produced a report that silently counted 5,403 declared files instead of 11,231 —
    no error, just a wrong number — which is why this is a sweep and not one test.
    """

    @staticmethod
    def _metadata(tmp_path, records):
        """The input envelope with a catalog, so the incumbent is named as in a real run."""
        path = tmp_path / "metadata.json"
        path.write_text(json.dumps({"metadata": {"catalog": "anvil15"}, "files": records}))
        return path

    @staticmethod
    def _declared_blocks(output_path):
        return [r.get("declared") for r in json.loads(output_path.read_text())["classifications"]]

    @staticmethod
    def _input(name, fmt):
        return valid_record(
            file_name=name,
            file_format=fmt,
            file_md5sum="a" * 32,
            file_size=10,
            entry_id="e1",
            dataset_id="ds1",
            dataset_title="AnVIL_IGVF_Mouse_R1",
            data_modality=["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"],
            reference_assembly=["GRCm39"],
        )

    @pytest.mark.parametrize(
        "producer,name,fmt",
        [
            ("classify_images", "slide.svs", ".svs"),
            ("classify_auxiliary_genomic", "cohort.pvar", ".pvar"),
            ("classify_remaining", "mystery.xyz", ".xyz"),
        ],
    )
    def test_a_standalone_producer_writes_the_declaration(self, tmp_path, producer, name, fmt):
        import sys

        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))
        from classify_auxiliary_genomic import classify_auxiliary_genomic
        from classify_images import classify_images
        from classify_remaining_files import classify_remaining

        funcs = {
            "classify_images": classify_images,
            "classify_auxiliary_genomic": classify_auxiliary_genomic,
            "classify_remaining": lambda m, o: classify_remaining(m, o, []),
        }
        metadata = self._metadata(tmp_path, [self._input(name, fmt)])
        output = tmp_path / "out_classifications.json"
        funcs[producer](metadata, output)

        [block] = self._declared_blocks(output)
        assert block is not None, f"{producer} dropped the declaration"
        assert block["data_modality"] == ["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"]
        assert block["reference_assembly"] == ["GRCm39"]
        assert block["source"] == "anvil/anvil15"

    def test_the_index_producer_writes_the_index_files_own_declaration(self, tmp_path):
        # Not the parent's: AnVIL carries the set's modality on a .bai, and that row is
        # where the two sides most often both speak.
        import sys

        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "scripts"))
        from classify_index_files import propagate_to_index_files

        parent = valid_record(
            file_name="sample.bam", file_format=".bam", file_md5sum="b" * 32, entry_id="p1", dataset_id="ds1"
        )
        index = self._input("sample.bam.bai", ".bai")
        metadata = self._metadata(tmp_path, [parent, index])
        parents = tmp_path / "bam_classifications.json"
        parents.write_text(json.dumps({"classifications": []}))
        output = tmp_path / "index_classifications.json"
        propagate_to_index_files(metadata, [parents], output)

        [block] = self._declared_blocks(output)
        assert block is not None
        assert block["reference_assembly"] == ["GRCm39"]


def test_the_display_join_matches_the_manifest_reader():
    """The report rejoins a declared list with the separator the reader split on.

    `incumbent` holds its own copy rather than importing `azul_manifest`, which opens a
    `requests` session at import. That duplication is only safe while the two agree: if
    Azul's separator moved and only the reader were updated, every `azul_cell` in the
    report would silently stop matching what Azul published. Imported inside the test so
    the report keeps its offline import graph.
    """
    from meta_disco import azul_manifest

    assert MULTI_VALUE_SEP == azul_manifest._MULTI_VALUE_SEP


def test_two_files_sharing_a_name_in_one_dataset_are_counted_twice(tmp_path):
    """The headline counts files on the identity `gather` deduplicated on.

    The corpus admits a repeated name within a dataset — `corpus_diff` keys on
    (dataset, name, md5) and keeps such a pair as a multiset — so counting by name
    would report one file while the recommendation tables counted two.
    """
    declared = build_declared({"data_modality": None, "reference_assembly": ["GRCm39"]}, "anvil/anvil15")
    twins = []
    for entry in ("e1", "e2"):
        rec = _record("same.bam", declared=declared)
        rec["entry_id"], rec["md5sum"] = entry, entry
        twins.append(rec)
    report = gather(_write_run(tmp_path / "run", twins))

    assert report.files == 2
    assert report.duplicate_records == 0
    assert report.declared_files == 2
    assert report.counts[("AnVIL_IGVF_Mouse_R1", "reference_assembly", TAKE_AZUL)] == 2
