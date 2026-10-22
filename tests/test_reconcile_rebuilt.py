"""Reconcile's rebuilt lists (#726): a sample map inference rebuilt from the workspace tars that read it,
held under its address so a tar reads its gVCFs' values through it, and written once."""

import hashlib
import json

import pytest

from meta_disco import code_rules
from meta_disco.edges import PARENT_REF, generated_by, generated_by_ref, inferred_steps, parent_node
from meta_disco.output_utils import (
    REBUILT_LISTS_FILE,
    iter_reconciled_artifact,
    iter_reconciled_records,
    iter_run_files,
)
from meta_disco.reconcile import reconcile_run
from meta_disco.record_keys import RecordKey
from meta_disco.records import REBUILT_LISTS_KEY, SAMPLE_LISTS_KEY
from meta_disco.schema.classification_model import RebuiltList
from tests.manifest_fixtures import CATALOG
from tests.metadata_fixtures import write_metadata
from tests.run_fixtures import output_record

KEY = RecordKey("file_id", "file_id")
MAP = "chr1_sample_map.tsv"
REF = f"rebuilt:ANVIL_T2T_CHRY/SGDP_CHM13v2/{MAP}#0123456789abcdef"
GVCF = {
    "assay_type": "WGS",
    "platform": "ILLUMINA",
    "instrument_model": "Illumina NovaSeq 6000",
    "reference_assembly": "T2T-CHM13v2.0",
}
NAMES = ("simons_data_sample_1.chr1.hc.vcf.gz", "simons_data_sample_2.chr1.hc.vcf.gz")


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def rebuilt_list(*names: str) -> dict:
    members = [{"file_name": n, "file_id": f"g_{n}"} for n in names]
    step = generated_by(code_rules.COHORT_BY_REBUILT_SAMPLE_MAP, members, KEY)
    return {"ref": REF, "dataset": "ANVIL_T2T_CHRY", "file_name": MAP, "generated_by": step}


def write_run(run_dir, gvcf_values: list[dict], rebuilt: list[dict]):
    run_dir.mkdir(parents=True)
    tar = output_record("chr1.1.tar", md5("t1"), dataset="ANVIL_T2T_CHRY", file_id="t1", data_type="variants.gvcf")
    tar["generated_by"] = generated_by_ref(code_rules.MERGE_BY_WORKSPACE_HEADER, MAP, REF)
    gvcfs = [
        output_record(n, md5(n), dataset="ANVIL_T2T_CHRY", file_id=f"g_{n}", data_type="variants.gvcf", **values)
        for n, values in zip(NAMES, gvcf_values, strict=True)
    ]
    (run_dir / "tar_classifications.json").write_text(
        json.dumps({"metadata": {}, "classifications": [tar], SAMPLE_LISTS_KEY: [], REBUILT_LISTS_KEY: rebuilt})
    )
    (run_dir / "vcf_classifications.json").write_text(json.dumps({"metadata": {}, "classifications": gvcfs}))
    return run_dir


def reconcile(tmp_path, gvcf_values, rebuilt):
    run_dir = write_run(tmp_path / "output" / "20261022_000000", gvcf_values, rebuilt)
    metadata = write_metadata(tmp_path / "input.json", [], repository="anvil", catalog=CATALOG)
    report = reconcile_run(run_dir, metadata, None)
    return run_dir, {r["file_name"]: r for r in iter_reconciled_records(run_dir)}, report


def test_a_tar_reads_its_values_through_the_list_inference_rebuilt(tmp_path):
    run_dir, rows, report = reconcile(tmp_path, [GVCF, GVCF], [rebuilt_list(*NAMES)])
    tar = rows["chr1.1.tar"]
    (used,) = tar["generated_by"]["inputs"]
    assert used["parent_ref"] == REF and "parent_key" not in used
    for dimension, value in GVCF.items():
        entry = tar["classifications"][dimension]
        assert (entry["value"], entry["credited_to"]) == (value, "inherited"), dimension
        (inherited,) = [e for e in entry["evidence"] if e.get("rule_id") == "inherited_from_parent"]
        assert inherited["parent_keys"] == [REF]
    assert report["rebuilt_lists"] == {"ANVIL_T2T_CHRY": {"lists": 1, "members": 2}}
    # The list names no samples by design: counted apart from a parent no source named samples for.
    assert report["samples"]["by_dataset"]["ANVIL_T2T_CHRY"]["inheritance"] == {
        "CohortMergeActivity": {"list_names_none": 1}
    }
    (listed,) = iter_reconciled_artifact(run_dir, REBUILT_LISTS_FILE)
    assert listed == rebuilt_list(*NAMES)
    RebuiltList.model_validate(listed)


def test_each_list_is_written_once_in_address_order(tmp_path):
    first = rebuilt_list(*NAMES)
    later = {**rebuilt_list(NAMES[0]), "ref": REF.replace("#0", "#f")}
    run_dir, _, report = reconcile(tmp_path, [GVCF, GVCF], [later, first, first])
    assert [r["ref"] for r in iter_reconciled_artifact(run_dir, REBUILT_LISTS_FILE)] == [REF, later["ref"]]
    assert report["rebuilt_lists"] == {"ANVIL_T2T_CHRY": {"lists": 2, "members": 3}}


def test_members_that_differ_give_the_tar_mixed_not_either_value(tmp_path):
    other = {**GVCF, "reference_assembly": "GRCh38"}
    _, rows, _ = reconcile(tmp_path, [GVCF, other], [rebuilt_list(*NAMES)])
    entry = rows["chr1.1.tar"]["classifications"]["reference_assembly"]
    assert entry["value"] is None and entry["status"] == "not_classified"


def test_a_tar_whose_list_is_not_in_the_run_inherits_nothing(tmp_path):
    run_dir, rows, report = reconcile(tmp_path, [GVCF, GVCF], [])
    assert rows["chr1.1.tar"]["classifications"]["platform"]["status"] == "not_classified"
    assert report["rebuilt_lists"] == {}
    assert list(iter_reconciled_artifact(run_dir, REBUILT_LISTS_FILE)) == []


def test_a_run_file_whose_rebuilt_lists_are_damaged_is_refused(tmp_path):
    run_dir = write_run(tmp_path / "run", [GVCF, GVCF], [{"no": "ref"}])
    with pytest.raises(ValueError, match="rebuilt_lists"):
        list(iter_run_files(run_dir, strict=True))


def test_inferences_step_naming_a_list_by_address_is_one_lineage_step_held_by_it():
    step = generated_by_ref(code_rules.MERGE_BY_WORKSPACE_HEADER, MAP, REF)
    (used,) = step["inputs"]
    assert parent_node(used) == REF and used[PARENT_REF] == REF
    (inferred,) = inferred_steps(step)
    assert (inferred.parent_key, inferred.external, inferred.role) == (REF, True, "input_list")
