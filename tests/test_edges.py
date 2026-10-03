"""Derivation edges from a child's own name (#356), and merging every source's step into one (#577).

The index producer's ``IndexActivity`` edge is tested with that producer, in
``test_index_propagation``. Here: a checksum file names the file it checks where exactly
one file of its dataset carries its name less ``.md5``, and nothing otherwise; and the rule
that merges inference's step with the source tables' into one (``merge_steps``) and flags a
step that does not fit its declaration (``misfits``).
"""

from meta_disco.edges import (
    ACTIVITY_CONFLICT,
    EDGE_CONFLICT,
    LineageStep,
    generic_only,
    merge_steps,
    misfits,
)
from tests.metadata_fixtures import valid_record
from tests.producer_sweep import CATCH_ALL, run_producer


def _file(name: str, file_id: str, dataset_id: str = "d1") -> dict:
    return valid_record(
        file_name=name, file_format="." + name.rsplit(".", 1)[-1], file_id=file_id, dataset_id=dataset_id
    )


def _rows(tmp_path, records) -> dict[str, dict]:
    return {r["file_name"]: r for r in run_producer(CATCH_ALL, tmp_path, records)}


def test_a_checksum_file_names_the_one_file_it_checks(tmp_path):
    rows = _rows(tmp_path, [_file("sample.bam", "f-bam"), _file("sample.bam.md5", "f-md5")])
    named_by = [{"source_type": "filename_rule", "rule_id": "checksum_by_name"}]
    assert rows["sample.bam.md5"]["generated_by"] == {
        "activity": "ChecksumActivity",
        "named_by": named_by,
        "inputs": [
            {
                "role": "checked",
                "parent_file": "sample.bam",
                "parent_key": "f-bam",
                "parent_kind": "alignment",
                "named_by": named_by,
            }
        ],
    }
    # The parent itself states nothing.
    assert rows["sample.bam"]["generated_by"] is None


def test_the_parent_name_is_matched_across_case_and_named_as_the_catalog_spells_it(tmp_path):
    rows = _rows(tmp_path, [_file("Sample.BAM", "f-bam"), _file("sample.bam.MD5", "f-md5")])
    [edge] = rows["sample.bam.MD5"]["generated_by"]["inputs"]
    assert (edge["parent_file"], edge["parent_key"]) == ("Sample.BAM", "f-bam")


def test_no_file_carrying_the_name_gives_no_edge(tmp_path):
    rows = _rows(tmp_path, [_file("sample.bam.md5", "f-md5")])
    assert rows["sample.bam.md5"]["generated_by"] is None


def test_a_name_two_files_carry_gives_no_edge(tmp_path):
    """#438's rule for an index, applied to a checksum: a shared name names neither file."""
    rows = run_producer(
        CATCH_ALL,
        tmp_path,
        [_file("sample.bam", "f-1"), _file("sample.bam", "f-2"), _file("sample.bam.md5", "f-md5")],
    )
    [md5] = [r for r in rows if r["file_name"] == "sample.bam.md5"]
    assert md5["generated_by"] is None


def test_a_parent_in_another_dataset_is_not_the_parent(tmp_path):
    """A file's lineage lives in its dataset (ADR-0002): the same name elsewhere is not it."""
    rows = _rows(tmp_path, [_file("sample.bam", "f-bam", dataset_id="d2"), _file("sample.bam.md5", "f-md5")])
    assert rows["sample.bam.md5"]["generated_by"] is None


def test_a_wrapped_checksum_names_its_parent_by_stem(tmp_path):
    """The rule matches `.md5` under a wrapper, and the parent is the name's stem."""
    rows = _rows(tmp_path, [_file("sample.bam", "f-bam"), _file("sample.bam.md5.gz", "f-md5")])
    [edge] = rows["sample.bam.md5.gz"]["generated_by"]["inputs"]
    assert edge["parent_key"] == "f-bam"


def test_a_file_that_is_not_a_checksum_gets_no_edge(tmp_path):
    """`sample.bam.txt` strips to a held name too, but only a checksum states the edge."""
    rows = _rows(tmp_path, [_file("sample.bam", "f-bam"), _file("sample.bam.txt", "f-txt")])
    assert rows["sample.bam.txt"]["generated_by"] is None


# --- merging every source's step (#577) ------------------------------------------------


NAME = {"source_type": "filename_rule", "rule_id": "index_by_name"}
TABLE = {"source_type": "repository_activity", "rule_id": "activity.indexing", "source": {"name": "anvil"}}
ROW = {"source_type": "repository_metadata", "rule_id": "activity.t2t_index", "source": {"name": "anvil"}}


def inferred_index(parent_key: str, parent_file: str) -> dict:
    return {
        "activity": "IndexActivity",
        "named_by": [NAME],
        "inputs": [
            {
                "role": "indexed",
                "parent_file": parent_file,
                "parent_key": parent_key,
                "parent_kind": "variants",
                "named_by": [NAME],
            }
        ],
    }


def test_sources_naming_one_parent_give_one_input_named_by_each():
    step, conflict = merge_steps(
        inferred_index("k-vcf", "a.vcf.gz"),
        [
            LineageStep("IndexActivity", "indexed", "k-vcf", "a.vcf.gz", "variants", TABLE),
            LineageStep("IndexActivity", "indexed", "k-vcf", "a.vcf.gz", "variants", ROW),
        ],
    )
    assert conflict is None
    assert step == {
        "activity": "IndexActivity",
        "named_by": [NAME, TABLE, ROW],
        "inputs": [
            {
                "role": "indexed",
                "parent_file": "a.vcf.gz",
                "parent_key": "k-vcf",
                "parent_kind": "variants",
                "named_by": [NAME, TABLE, ROW],
            }
        ],
    }


def test_a_lineage_step_alone_keeps_the_parent_kind_it_was_resolved_with():
    step, _ = merge_steps(None, [LineageStep("IndexActivity", "indexed", "k-vcf", "a.vcf.gz", "variants", TABLE)])
    assert step is not None
    assert step["inputs"][0]["parent_kind"] == "variants"
    assert step["named_by"] == [TABLE]


def test_two_parents_in_a_role_that_takes_one_are_an_edge_conflict_and_give_no_step():
    step, conflict = merge_steps(
        inferred_index("k-a", "a.vcf.gz"),
        [LineageStep("IndexActivity", "indexed", "k-b", "b.vcf.gz", "variants", TABLE)],
    )
    assert step is None
    assert conflict is not None
    assert (conflict.kind, conflict.role) == (EDGE_CONFLICT, "indexed")
    assert conflict.said == (("a.vcf.gz", NAME), ("b.vcf.gz", TABLE))


def test_a_role_that_takes_several_keeps_one_input_per_parent():
    step, conflict = merge_steps(
        None,
        [
            LineageStep("AlignmentActivity", "reads", "k-r1", "s_1.fastq.gz", "reads", ROW),
            LineageStep("AlignmentActivity", "reads", "k-r2", "s_2.fastq.gz", "reads", ROW),
        ],
    )
    assert conflict is None and step is not None
    assert [(i["role"], i["parent_key"]) for i in step["inputs"]] == [("reads", "k-r1"), ("reads", "k-r2")]
    assert step["named_by"] == [ROW]


HEADER = {"source_type": "content_read", "rule_id": "variant_call_by_header"}
SAMPLE = {"source_type": "repository_metadata", "rule_id": "activity.t2t_variant_call", "source": {"name": "anvil"}}


def inferred_call(parent_key: str, parent_file: str) -> dict:
    used = {"role": "calls_from", "parent_file": parent_file, "parent_key": parent_key, "parent_kind": "alignment"}
    return {"activity": "VariantCallActivity", "named_by": [HEADER], "inputs": [{**used, "named_by": [HEADER]}]}


def test_a_source_naming_other_parents_than_inference_is_an_edge_conflict_in_a_role_that_takes_several():
    # `calls_from` takes several parents, but the header names every input of its step.
    step, conflict = merge_steps(
        inferred_call("k-a", "A.cram"),
        [LineageStep("VariantCallActivity", "calls_from", "k-b", "B.cram", "alignment", SAMPLE)],
    )
    assert step is None and conflict is not None
    assert (conflict.kind, conflict.role) == (EDGE_CONFLICT, "calls_from")
    assert conflict.said == (("A.cram", HEADER), ("B.cram", SAMPLE))


def test_a_source_naming_inferences_parent_and_another_is_a_conflict_too():
    step, conflict = merge_steps(
        inferred_call("k-a", "A.cram"),
        [
            LineageStep("VariantCallActivity", "calls_from", "k-a", "A.cram", "alignment", SAMPLE),
            LineageStep("VariantCallActivity", "calls_from", "k-b", "B.cram", "alignment", SAMPLE),
        ],
    )
    assert step is None and conflict is not None and conflict.kind == EDGE_CONFLICT


def test_a_source_naming_inferences_parent_merges_with_it():
    step, conflict = merge_steps(
        inferred_call("k-a", "A.cram"),
        [LineageStep("VariantCallActivity", "calls_from", "k-a", "A.cram", "alignment", SAMPLE)],
    )
    assert conflict is None and step is not None
    assert [i["named_by"] for i in step["inputs"]] == [[HEADER, SAMPLE]]


def test_two_activities_are_an_activity_conflict_and_the_generic_one_agrees_with_either():
    step, conflict = merge_steps(
        inferred_index("k", "a.cram"),
        [LineageStep("QualityControlActivity", "reported_on", "k", "a.cram", "alignment", ROW)],
    )
    assert step is None and conflict is not None
    assert conflict.kind == ACTIVITY_CONFLICT
    assert conflict.said == (("IndexActivity", NAME), ("QualityControlActivity", ROW))
    generic, none = merge_steps(
        inferred_index("k", "a.vcf.gz"), [LineageStep("Activity", "input", "k", "a.vcf.gz", "variants", ROW)]
    )
    assert none is None and generic is not None and generic["activity"] == "IndexActivity"


def test_nothing_named_gives_nothing():
    assert merge_steps(None, []) == (None, None)


def test_misfits_flag_a_missing_required_role_and_a_wrong_kind():
    step = {
        "activity": "AlignmentActivity",
        "named_by": [ROW],
        "inputs": [
            {"role": "reads", "parent_file": "s.bam", "parent_key": "k", "parent_kind": None, "named_by": [ROW]}
        ],
    }
    found = misfits(step, "qc_report", {"k": "alignments"})
    assert ("required role missing", "reference") in found
    assert ("output kind", "qc_report") in found
    assert ("input kind (reads)", "alignments") in found
    # An unknown kind is not judged.
    assert misfits(step, None, {"k": None}) == [("required role missing", "reference")]


def test_an_inferred_input_naming_no_source_is_attributed_to_the_steps():
    inferred = inferred_index("k-vcf", "a.vcf.gz")
    inferred["inputs"][0]["named_by"] = []
    step, conflict = merge_steps(
        inferred, [LineageStep("IndexActivity", "indexed", "k-vcf", "a.vcf.gz", "variants", TABLE)]
    )
    assert conflict is None and step is not None
    assert step["inputs"][0]["named_by"] == [NAME, TABLE]


def test_a_generic_step_naming_the_same_parent_is_another_source_of_that_input():
    generic = LineageStep("Activity", "input", "k-vcf", "a.vcf.gz", "variants", ROW)
    step, conflict = merge_steps(inferred_index("k-vcf", "a.vcf.gz"), [generic])
    assert conflict is None and step is not None
    assert [(i["role"], i["parent_key"], i["named_by"]) for i in step["inputs"]] == [("indexed", "k-vcf", [NAME, ROW])]


def test_a_generic_step_naming_another_parent_is_an_edge_conflict():
    generic = LineageStep("Activity", "input", "k-other", "other.bam", "alignment", ROW)
    step, conflict = merge_steps(inferred_index("k-vcf", "a.vcf.gz"), [generic])
    assert step is None and conflict is not None
    assert (conflict.kind, conflict.role) == (EDGE_CONFLICT, "input")
    assert conflict.said == (("other.bam", ROW), ("a.vcf.gz", NAME))


def test_a_file_whose_only_steps_are_generic_gets_no_step_and_no_conflict():
    generic = LineageStep("Activity", "input", "k", "a.cram", "alignment", ROW)
    assert merge_steps(None, [generic]) == (None, None)
    assert generic_only(None, [generic])
    assert not generic_only(inferred_index("k", "a.cram"), [generic])
