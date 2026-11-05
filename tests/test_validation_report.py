"""The validation report's discrepancies, whatever order the validator listed its mismatches in (#732)."""

import json

from generate_validation_report import build_source_section, load_hprc_results


def test_discrepancies_rank_ties_by_category_and_show_the_smallest_file(tmp_path):
    mismatches = [
        {"file": "c.bam", "platform": {"ours": "ONT", "expected": "PACBIO"}},
        {"file": "a.bam", "platform": {"ours": "ONT", "expected": "PACBIO"}},
        {"file": "b.bam", "platform": {"ours": "ILLUMINA", "expected": "PACBIO"}},
        {"file": "d.bam", "platform": {"ours": "ILLUMINA", "expected": "PACBIO"}},
    ]
    sections = []
    for name, order in (("forward", mismatches), ("backward", mismatches[::-1])):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"dimensions": {"platform": {"match": 1, "mismatch": 4}}, "mismatches": order}))
        results = load_hprc_results(path)
        assert results["dimensions"]["platform"]["discrepancy_categories"]["ONT vs PACBIO"]["example"] == "a.bam"
        sections.append(build_source_section("HPRC", results))
    assert sections[0] == sections[1]
