"""The name-signals forecast (#369 R8): what a name would claim, with the map's two
structural exclusions applied and counted; the join to a stored run; and the same join
over written evidence — on a synthetic run and manifests."""

import json
from pathlib import Path

from meta_disco import anvil_forecast as af
from meta_disco.anvil_evidence import import_dataset
from meta_disco.models import CLASSIFIED, NOT_APPLICABLE, NOT_CLASSIFIED
from meta_disco.slot_map import load_slot_map
from tests.test_anvil_evidence import CATALOG, anvil_file, drs, write_dataset

DATASET = "SGDP_CHM13v2_sample"


def classification(slot_values: dict[str, tuple[str, str | None]]) -> dict:
    return {slot: {"status": status, "value": value, "evidence": []} for slot, (status, value) in slot_values.items()}


def write_run(root: Path) -> Path:
    """Three records: a CRAM on CHM13, a FASTQ with no assembly, and a BED with no value."""
    run = root / "20260101_000000"
    run.mkdir(parents=True)
    bam = [
        {
            "drs_uri": drs(1),
            "classifications": classification(
                {"reference_assembly": (CLASSIFIED, "CHM13"), "data_type": (CLASSIFIED, "alignments")}
            ),
        },
        {
            "drs_uri": drs(4),
            "classifications": classification({"reference_assembly": (CLASSIFIED, "GRCh38")}),
        },
    ]
    fastq = [
        {
            "drs_uri": drs(2),
            "classifications": classification(
                {"reference_assembly": (NOT_APPLICABLE, None), "data_modality": (NOT_CLASSIFIED, None)}
            ),
        }
    ]
    bed = [{"drs_uri": drs(3), "classifications": classification({"reference_assembly": (NOT_CLASSIFIED, None)})}]
    for name, records in (("bam", bam), ("fastq", fastq), ("bed", bed)):
        (run / f"{name}_classifications.json").write_text(json.dumps({"metadata": {}, "classifications": records}))
    return run


def test_index_run_keeps_status_value_and_whether_the_record_is_a_fastq(tmp_path):
    run = af.index_run(write_run(tmp_path))
    assert set(run) == {drs(1), drs(2), drs(3), drs(4)}
    assert run[drs(2)].is_fastq and not run[drs(1)].is_fastq
    assert run[drs(1)].slots["reference_assembly"] == (CLASSIFIED, "CHM13")


def test_verdicts():
    record = af.RunRecord(
        is_fastq=False,
        slots={
            "reference_assembly": (CLASSIFIED, "CHM13"),
            "platform": (NOT_APPLICABLE, None),
            "data_type": (NOT_CLASSIFIED, None),
        },
    )
    assert record.verdict("reference_assembly", "CHM13") == af.AGREE
    assert record.verdict("reference_assembly", "GRCh38") == af.DISAGREE
    assert record.verdict("platform", "ONT") == NOT_APPLICABLE
    assert record.verdict("data_type", "reads") == af.GAP
    assert record.verdict("assay_type", "WGS") == af.GAP, "a slot the record does not carry is a gap"


class TestNameClaims:
    def test_a_word_in_both_names_is_one_claim(self):
        claims, entity, derivative = af.name_claims("1KGP_CHM13v2_chromosome", "chm13v2_pass_vcf_gz")
        assert claims == [("reference_assembly", "chm13v2", "CHM13")]
        assert (entity, derivative) == (0, 0)

    def test_an_entity_token_is_excluded_and_counted(self):
        claims, entity, _ = af.name_claims("PAR_interval_CHM13v2", "sgdp_genomics_db_tar")
        assert claims == [("reference_assembly", "chm13v2", "CHM13")]
        assert entity == 1

    def test_data_type_on_a_derivative_column_is_excluded_and_counted(self):
        claims, _, derivative = af.name_claims("assembly", "assembly_fai")
        assert claims == []
        assert derivative == 1

    def test_a_token_without_a_term_is_kept_as_untranslatable(self):
        assert af.name_claims("chains_to_chm13_mc", "location")[0] == [
            ("data_type", "chains", None),
            ("reference_assembly", "chm13", "CHM13"),
        ]


def test_name_signals_needs_no_map_and_reports_every_verdict(tmp_path):
    run = af.index_run(write_run(tmp_path))
    write_dataset(
        tmp_path,
        "D",
        [
            anvil_file(1),
            anvil_file(2),
            anvil_file(3),
            anvil_file(4),
            (DATASET, {"cram": drs(1), "read_1_fastq": drs(2), "mosdepth_regions_bed": drs(3), "cram_index": drs(9)}),
            ("SGDP_GRCh38_sample", {"cram": drs(4)}),
            ("PAR_interval_CHM13v2", {"sgdp_genomics_db_tar": drs(5)}),
            ("chains_to_chm13_mc", {"location": drs(1)}),
        ],
    )
    (signals,) = af.name_signals(tmp_path, CATALOG, run)
    reference = signals.slots["reference_assembly"]
    # cram agrees, the fastq meets not_applicable, the bed is a gap, cram_index is unjoined,
    # the GRCh38 cram agrees, the interval tar is unjoined, and chains' `chm13` on drs(1) is a
    # second token for the same file and slot, so it is a claim of its own and agrees too.
    assert reference.claimed == 7
    assert reference.unjoined == 2
    assert reference.verdicts == {af.AGREE: 3, NOT_APPLICABLE: 1, af.GAP: 1}
    assert signals.slots["data_type"].untranslatable == {"chains": 1}
    assert signals.excluded_entity == 1
    report = af.render_name_signals([signals], Path("run"))
    assert "| D | reference_assembly | 7 | 2 | 3 | 0 | 1 | 1 | 0 |" in report
    assert "`chains`" in report


def test_evidence_forecast_counts_what_the_import_is_judged_on(tmp_path):
    run = af.index_run(write_run(tmp_path))
    write_dataset(
        tmp_path,
        "D",
        [
            anvil_file(1),
            anvil_file(2),
            anvil_file(3),
            (DATASET, {"cram": drs(1), "read_1_fastq": drs(2), "mosdepth_regions_bed": drs(3)}),
            ("hifi", {"path": drs(2), "library_source": "GENOMIC"}),
        ],
    )
    text = (
        "catalog: anvil15\ndatasets:\n  D:\n"
        f"    {DATASET}:\n"
        "      cram: &t\n        reference_assembly:\n          - {table_name: CHM13v2}\n"
        "      read_1_fastq: *t\n      mosdepth_regions_bed: *t\n"
        "    hifi:\n      path:\n        data_modality:\n          - {cell: library_source}\n"
    )
    path = tmp_path / "map.yaml"
    path.write_text(text)
    import_dataset(load_slot_map(path), tmp_path, CATALOG, "D", tmp_path / "ev", "20260920T000000Z")

    forecast = af.evidence_forecast(tmp_path / "ev", run)
    assert forecast.rows == 4
    assert forecast.files == {drs(1), drs(2), drs(3)}
    assert forecast.gaps == {(drs(3), "reference_assembly"), (drs(2), "data_modality")}
    assert forecast.not_applicable == {(drs(2), "reference_assembly")}
    assert forecast.fastq_modality == {drs(2)}
    assert forecast.agree == {(drs(1), "reference_assembly", "CHM13")}
    assert forecast.disagree == set()
    assert forecast.against_not_applicable == {(drs(2), "reference_assembly", "CHM13")}
    assert forecast.untranslated == {("data_modality", "GENOMIC"): 1}
    report = af.render_evidence_forecast(forecast, tmp_path / "ev", Path("run"))
    assert "| FASTQs receiving data_modality | 1 |" in report
    assert "| data_modality | `GENOMIC` | 1 |" in report
