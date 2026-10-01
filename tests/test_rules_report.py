"""The rules report (#572): every rule, with its basis, and what it fired on in a reconciled run."""

from pathlib import Path

import generate_rules_report as grr
import pytest
import yaml

from meta_disco import code_rules
from meta_disco.activity_map import load_activity_map
from meta_disco.models import SOURCE_PUBLISHED_VALUE, SOURCE_REPOSITORY_METADATA
from meta_disco.output_utils import (
    CLASSIFICATION_FILES,
    RECONCILED_DIR,
    iter_reconciled_records,
    reconciled_name,
    write_reconciled_file,
)
from meta_disco.rule_loader import RuleLoader
from meta_disco.schema_vocab import marker_values
from meta_disco.value_map import load_value_map

RULES = """\
rules:
  - id: bam_ext
    tier: 1
    scope: extension
    when:
      extensions: [".bam"]
    then:
      data_type: alignments
    rationale: "A BAM holds alignments"
  - id: hifi_name
    tier: 2
    scope: filename
    when:
      extensions: [".bam"]
      filename_pattern: "(?i)hifi"
    then:
      platform: PACBIO
      status:
        assay_type: not_applicable
    # a comment before the next key, not part of `then`
    rationale: "hifi names a PacBio run"
  - id: study_ref
    tier: 2
    scope: filename
    when:
      extensions: [".bam"]
      dataset_pattern: "STUDY_A"
    then:
      reference_assembly: GRCh38
    rationale: "Study A is on GRCh38"
  - id: never_fires
    tier: 3
    scope: header
    when:
      header_section: "@PG"
      header_pattern: "nothing"
    then:
      data_modality: genomic
    rationale: "never matched"
---
validators: {}
"""

VALUE_MAP = """\
rows:
  - id: "platform.revio"
    match: {slot: platform, value: "Revio"}
    scope: {source: anvil, dataset: STUDY_A}
    declares: {platform: PACBIO}
    reason: "Revio is a PacBio instrument"
  - id: "platform.unknown"
    match: {slot: platform, value: "unknown"}
"""


def slot(value=None, status="classified", evidence=(), inferred=None):
    status = status if value is None else "classified"
    entry = {"value": value, "status": status, "evidence": list(evidence)}
    entry["inferred"] = inferred or {"value": value, "status": status}
    return entry


def claim(rule_id, value=None, status=None, source_type="filename_rule"):
    c = {"rule_id": rule_id, "reason": "r", "source_type": source_type}
    c.update({"value": value} if value is not None else {"status": status})
    return c


RECORDS = [
    # bam_ext wins data_type; hifi_name wins platform, which a submitter's Revio agrees with.
    {
        "dataset_title": "STUDY_A",
        "classifications": {
            "data_type": slot("alignments", evidence=[claim("bam_ext", "alignments")]),
            "platform": slot(
                "PACBIO",
                evidence=[
                    claim("hifi_name", "PACBIO"),
                    claim("platform.revio", "PACBIO", source_type=SOURCE_REPOSITORY_METADATA),
                    claim("platform.revio", "PACBIO", source_type=SOURCE_PUBLISHED_VALUE),
                ],
            ),
            "assay_type": slot(status="not_applicable", evidence=[claim("hifi_name", status="not_applicable")]),
        },
    },
    # The contig lengths outrank the dataset rule, and a retired rule id is still in the run.
    {
        "dataset_title": "STUDY_A",
        "classifications": {
            "data_type": slot("alignments", evidence=[claim("bam_ext", "alignments")]),
            "reference_assembly": slot(
                "CHM13",
                evidence=[claim("study_ref", "GRCh38"), claim(code_rules.CONTIG_LENGTH_DETECTION.id, "CHM13")],
            ),
            "platform": slot(status="not_classified", evidence=[claim("retired_rule", "ILLUMINA")]),
        },
    },
    {
        "dataset_title": "STUDY_B",
        "classifications": {
            "data_type": slot("alignments", evidence=[claim("bam_ext", "alignments")]),
            "platform": slot(
                status="not_classified", evidence=[{"marker": "not_classified", "status": "not_classified"}]
            ),
            "data_modality": slot(
                status="not_classified", evidence=[claim(code_rules.FETCH_FAILED.id, status="not_classified")]
            ),
        },
        "generated_by": {
            "activity": "IndexActivity",
            "inputs": [{"named_by": [{"rule_id": code_rules.INDEX_BY_NAME.id}]}],
        },
    },
]


def reconciled_run(tmp_path: Path, records=RECORDS) -> Path:
    run_dir = tmp_path / "20260928_000000"
    (run_dir / RECONCILED_DIR).mkdir(parents=True)
    write_reconciled_file(
        run_dir / RECONCILED_DIR / reconciled_name(CLASSIFICATION_FILES[0]), {"catalog": "t"}, records
    )
    return run_dir


def rule_files(tmp_path: Path) -> tuple[Path, Path]:
    rules, value_map = tmp_path / "rules.yaml", tmp_path / "value_map.yaml"
    rules.write_text(RULES)
    value_map.write_text(VALUE_MAP)
    return rules, value_map


@pytest.fixture
def data(tmp_path):
    run_dir = reconciled_run(tmp_path)
    return grr.build(*rule_files(tmp_path), iter_reconciled_records(run_dir), run_dir)


def by_id(data):
    return {r["id"]: r for r in [*data["rules"], *data["markers"], *data["edge_rules"], *data["undeclared"]]}


def test_every_when_key_the_loader_accepts_has_a_basis_entry():
    assert set(grr.WHEN_BASIS) == RuleLoader.VALID_WHEN_KEYS


@pytest.mark.parametrize(
    ("when", "basis"),
    [
        ({"extensions": [".bam"]}, "extension"),
        ({"format": "FASTA"}, "extension"),
        ({"extensions": [".bam"], "filename_pattern": "x"}, "file_name"),
        ({"extensions": [".bam"], "dataset_pattern": "x", "filename_pattern": "y"}, "dataset"),
        ({"extensions": [".bam"], "header_section": "@PG", "filename_pattern": "y"}, "content"),
        ({"extensions": [".fastq"], "file_size_min_gb": 1}, "extension"),
        ({"file_size_min_gb": 1, "file_size_max_gb": 5}, "file_size"),
    ],
)
def test_the_most_specific_condition_decides_the_basis(when, basis):
    assert grr.basis_of("r", when) == basis


def test_a_when_key_with_no_basis_or_only_a_gate_is_refused():
    with pytest.raises(grr.ReportError, match="no basis"):
        grr.basis_of("r", {"extensions": [".bam"], "new_key": 1})
    with pytest.raises(grr.ReportError, match="names nothing it reads"):
        grr.basis_of("r", {"always": True})


def test_when_and_then_are_the_file_s_own_text(data):
    rules = by_id(data)
    assert rules["hifi_name"]["condition"] == 'extensions: [".bam"]\nfilename_pattern: "(?i)hifi"'
    # The nested status keeps its indentation, and the comment before `rationale` is not part of `then`.
    assert rules["hifi_name"]["effect"] == "platform: PACBIO\nstatus:\n  assay_type: not_applicable"
    assert rules["platform.revio"]["condition"] == '{slot: platform, value: "Revio"}'
    assert rules["platform.revio"]["rationale"] == "Revio is a PacBio instrument"
    # Where a rule is defined names the file the report was given, not the bundled one.
    assert rules["hifi_name"]["defined_in"].endswith("rules.yaml") and "src/" not in rules["hifi_name"]["defined_in"]
    assert (
        rules["platform.revio"]["defined_in"].endswith("value_map.yaml")
        and "src/" not in rules["platform.revio"]["defined_in"]
    )


def test_each_kind_is_listed_with_its_basis_and_declared_dataset(data):
    rules = by_id(data)
    assert {(i, rules[i]["kind"], rules[i]["basis"]) for i in ("bam_ext", "hifi_name", "study_ref", "never_fires")} == {
        ("bam_ext", "yaml", "extension"),
        ("hifi_name", "yaml", "file_name"),
        ("study_ref", "yaml", "dataset"),
        ("never_fires", "yaml", "content"),
    }
    assert rules["study_ref"]["dataset"] == "dataset_pattern STUDY_A" and rules["bam_ext"]["dataset"] == "general"
    assert rules["platform.revio"]["dataset"] == "source anvil, dataset STUDY_A"
    assert rules["platform.unknown"]["seeded"] and not rules["platform.revio"]["seeded"]
    assert {r.id for r in code_rules.CODE_RULES} <= set(rules)
    assert rules[code_rules.INHERITED_FROM_PARENT.id]["basis"] == "parent_file"


def test_files_won_and_datasets_are_counted_per_rule(data):
    rules = by_id(data)
    assert (rules["bam_ext"]["files"], rules["bam_ext"]["won"]) == (3, 3)
    assert rules["bam_ext"]["datasets"] == {"STUDY_A": 2, "STUDY_B": 1}
    # One file, two claims (platform and assay_type status), both the answer.
    assert (rules["hifi_name"]["files"], rules["hifi_name"]["claims"], rules["hifi_name"]["won"]) == (1, 2, 1)
    # Outranked by the contig lengths: fired, did not win.
    assert (rules["study_ref"]["files"], rules["study_ref"]["won"]) == (1, 0)
    assert rules[code_rules.CONTIG_LENGTH_DETECTION.id]["won"] == 1
    assert rules["never_fires"]["files"] == 0


def test_a_translation_row_is_counted_by_source_type(data):
    revio = by_id(data)["platform.revio"]
    assert (revio["files"], revio["won"]) == (1, 1)
    assert revio["source_types"] == {SOURCE_REPOSITORY_METADATA: 1, SOURCE_PUBLISHED_VALUE: 1}


def test_markers_are_counted_apart_and_an_undeclared_id_is_listed(data):
    rows = by_id(data)
    assert rows["not_classified"]["files"] == 1 and rows[code_rules.FETCH_FAILED.id]["files"] == 1
    assert [u["id"] for u in data["undeclared"]] == ["retired_rule"]


def test_the_bundled_rules_all_get_a_row_and_a_basis():
    data = grr.build(None, None, [], Path("run"))
    yaml_rules = RuleLoader().load().rules
    assert len(data["rules"]) == len(yaml_rules) + len(code_rules.CODE_RULES) + len(load_value_map().rows)
    # A slice without an alias (`*name`) parses back to what the rule loaded.
    loaded = {r.id: r for r in yaml_rules}
    for r in data["rules"]:
        if r["kind"] == "yaml" and "*" not in r["condition"]:
            rule = loaded[r["id"]]
            assert yaml.safe_load(r["condition"]) == rule.when, r["id"]
            then = yaml.safe_load(r["effect"])
            assert then.pop("status", {}) == rule.then_status and then == rule.then, r["id"]


def test_edge_rules_are_listed_and_counted_by_the_edges_they_stated(data):
    rows = by_id(data)
    authored = [row.id for row in load_activity_map().rows if row.authored]
    assert [e["id"] for e in data["edge_rules"]] == [r.id for r in code_rules.EDGE_RULES] + authored
    assert (rows[code_rules.INDEX_BY_NAME.id]["files"], rows[code_rules.CHECKSUM_BY_NAME.id]["files"]) == (1, 0)
    assert rows[code_rules.INDEX_BY_NAME.id]["datasets"] == {"STUDY_B": 1}


def test_a_run_from_before_edge_rules_is_still_read(tmp_path):
    """A pre-#580 record carries `derived_from`, not `generated_by`: read, and counted for no edge rule."""
    legacy = {**RECORDS[0], "derived_from": {"relation": "index_of", "parent_file": "s.bam", "parent_md5sum": None}}
    run_dir = reconciled_run(tmp_path, [legacy])
    data = grr.build(*rule_files(tmp_path), iter_reconciled_records(run_dir), run_dir)
    assert all(e["files"] == 0 for e in data["edge_rules"])


def test_every_schema_marker_is_worded():
    assert set(grr.PLACEHOLDER_MARKERS) == marker_values()


def test_the_markdown_and_dashboard_render(tmp_path):
    run_dir = reconciled_run(tmp_path)
    rules, value_map = rule_files(tmp_path)
    md, html = tmp_path / "r.md", tmp_path / "r.html"
    argv = ["--run-dir", str(run_dir), "--rules", str(rules), "--value-map", str(value_map)]
    assert grr.main([*argv, "--markdown", str(md), "--html", str(html)]) == 0
    text = md.read_text()
    assert "`retired_rule`" in text and "### `hifi_name`" in text and "Reads:" in text
    assert grr.PLACEHOLDER not in html.read_text()


def test_a_run_with_no_reconciled_output_is_refused(tmp_path, capsys):
    run_dir = tmp_path / "20260928_000000"
    run_dir.mkdir()
    assert grr.main(["--run-dir", str(run_dir), "--markdown", str(tmp_path / "m"), "--html", str(tmp_path / "h")]) == 1
    assert "make reconcile" in capsys.readouterr().err


def test_a_dataset_title_is_a_code_span_in_the_markdown(tmp_path):
    title = "x <img src=x onerror=alert(1)>"
    record = {
        "dataset_title": title,
        "classifications": {"data_type": slot("alignments", evidence=[claim("bam_ext", "alignments")])},
    }
    run_dir = reconciled_run(tmp_path, [record])
    text = grr.render_markdown(grr.build(*rule_files(tmp_path), iter_reconciled_records(run_dir), run_dir))
    assert f"`{title}` 1" in text and f" {title} " not in text


def run_of(tmp_path, *classifications):
    run_dir = reconciled_run(tmp_path, [{"dataset_title": "STUDY_A", "classifications": c} for c in classifications])
    return by_id(grr.build(*rule_files(tmp_path), iter_reconciled_records(run_dir), run_dir))


def test_a_broader_term_of_the_answer_counts_as_won(tmp_path):
    rows = run_of(tmp_path, {"reference_assembly": slot("T2T-CHM13v2.0", evidence=[claim("study_ref", "CHM13")])})
    assert (rows["study_ref"]["files"], rows["study_ref"]["won"]) == (1, 1)


def test_a_claim_that_declares_no_answer_is_not_counted(tmp_path):
    inherited = code_rules.INHERITED_FROM_PARENT.id
    rows = run_of(
        tmp_path,
        {"platform": slot(status="not_classified", evidence=[claim(inherited, status="not_classified")])},
        {"platform": slot(status="conflict", evidence=[claim(inherited, status="conflict")])},
    )
    assert (rows[inherited]["files"], rows[inherited]["claims"], rows[inherited]["won"]) == (0, 0, 0)


def test_a_rule_written_with_an_alias_is_shown_expanded(tmp_path):
    value_map = rule_files(tmp_path)[1]
    rules = tmp_path / "aliased_rules.yaml"
    rules.write_text(
        RULES.replace(
            '    when:\n      extensions: [".bam"]\n    then:\n      data_type: alignments',
            '    when:\n      extensions: &bams [".bam", ".cram"]\n    then:\n      data_type: alignments',
        ).replace(
            '    when:\n      extensions: [".bam"]\n      dataset_pattern',
            "    when:\n      extensions: *bams\n      dataset_pattern",
        )
    )
    rows = by_id(grr.build(rules, value_map, [], Path("run")))
    assert rows["study_ref"]["expanded"] == ["bams"]
    assert yaml.safe_load(rows["study_ref"]["condition"]) == {
        "extensions": [".bam", ".cram"],
        "dataset_pattern": "STUDY_A",
    }
    # The anchor's own rule shows its text as written: nothing in it is borrowed.
    assert rows["bam_ext"]["expanded"] == [] and "&bams" in rows["bam_ext"]["condition"]


def test_a_rule_named_like_a_marker_is_refused(tmp_path):
    rules, value_map = rule_files(tmp_path)
    rules.write_text(RULES.replace("id: never_fires", f"id: {code_rules.FETCH_FAILED.id}"))
    with pytest.raises(grr.ReportError, match="declared twice"):
        grr.build(rules, value_map, [], Path("run"))
