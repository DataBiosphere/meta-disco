"""The rules report (#572): every rule, with its basis, and what it fired on in a reconciled run."""

from pathlib import Path

import generate_rules_report as grr
import pytest
import yaml

from meta_disco import code_rules
from meta_disco.models import SOURCE_PUBLISHED_VALUE, SOURCE_REPOSITORY_METADATA
from meta_disco.output_utils import CLASSIFICATION_FILES, RECONCILED_DIR, reconciled_name, write_reconciled_file
from meta_disco.rule_loader import RuleLoader, default_rules_resource
from meta_disco.value_map import default_value_map_resource

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
    },
]


def reconciled_run(tmp_path: Path, records=RECORDS) -> Path:
    run_dir = tmp_path / "20260928_000000"
    (run_dir / RECONCILED_DIR).mkdir(parents=True)
    write_reconciled_file(
        run_dir / RECONCILED_DIR / reconciled_name(CLASSIFICATION_FILES[0]), {"catalog": "t"}, records
    )
    return run_dir


@pytest.fixture
def data(tmp_path):
    from meta_disco.output_utils import iter_reconciled_records

    run_dir = reconciled_run(tmp_path)
    return grr.build(RULES, VALUE_MAP, iter_reconciled_records(run_dir), run_dir)


def by_id(data):
    return {r["id"]: r for r in [*data["rules"], *data["markers"], *data["undeclared"]]}


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
    ],
)
def test_the_most_specific_condition_decides_the_basis(when, basis):
    assert grr.basis_of("r", when) == basis


def test_a_when_key_with_no_basis_or_only_a_gate_is_refused():
    with pytest.raises(grr.ReportError, match="no basis"):
        grr.basis_of("r", {"extensions": [".bam"], "new_key": 1})
    with pytest.raises(grr.ReportError, match="names nothing it reads"):
        grr.basis_of("r", {"file_size_min_gb": 1})


def test_when_and_then_are_the_file_s_own_text(data):
    rules = by_id(data)
    assert rules["hifi_name"]["condition"] == 'extensions: [".bam"]\nfilename_pattern: "(?i)hifi"'
    # The nested status keeps its indentation, and the comment before `rationale` is not part of `then`.
    assert rules["hifi_name"]["effect"] == "platform: PACBIO\nstatus:\n  assay_type: not_applicable"
    assert rules["platform.revio"]["condition"] == '{slot: platform, value: "Revio"}'
    assert rules["platform.revio"]["rationale"] == "Revio is a PacBio instrument"


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
    rules_text = default_rules_resource().read_text(encoding="utf-8")
    value_map_text = default_value_map_resource().read_text(encoding="utf-8")
    data = grr.build(rules_text, value_map_text, [], Path("run"))
    yaml_rules = next(d for d in yaml.safe_load_all(rules_text) if isinstance(d, dict) and "rules" in d)["rules"]
    rows = yaml.safe_load(value_map_text)["rows"]
    assert len(data["rules"]) == len(yaml_rules) + len(code_rules.CODE_RULES) + len(rows)
    # A slice without an alias (`*name`) parses back to what the rule loaded.
    loaded = {r["id"]: r for r in yaml_rules}
    for r in data["rules"]:
        if r["kind"] == "yaml" and "*" not in r["condition"]:
            assert yaml.safe_load(r["condition"]) == loaded[r["id"]]["when"], r["id"]
            assert yaml.safe_load(r["effect"]) == loaded[r["id"]]["then"], r["id"]


def test_the_markdown_and_dashboard_render(tmp_path):
    run_dir = reconciled_run(tmp_path)
    rules, value_map = tmp_path / "rules.yaml", tmp_path / "value_map.yaml"
    rules.write_text(RULES)
    value_map.write_text(VALUE_MAP)
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
