"""Tests for the self-consistency linter (#314)."""

import json

from meta_disco.consistency import check_record, iter_records, load_rules

RULES = load_rules()

_DIMS = ("data_modality", "data_type", "reference_assembly", "assay_type", "platform")


def _rec(md5="m", name="f.bam", **dims):
    """Build a record; each dim kwarg is a (value, status) tuple, default not_classified."""
    classifications = {}
    for dim in _DIMS:
        value, status = dims.get(dim, (None, "not_classified"))
        classifications[dim] = {"value": value, "status": status, "evidence": []}
    return {"md5sum": md5, "file_name": name, "classifications": classifications}


def _c(value):
    return (value, "classified")


NA = (None, "not_applicable")
NC = (None, "not_classified")


def _rule_ids(record):
    return {v.rule_id for v in check_record(record, RULES)}


def test_rules_file_loads_and_is_nonempty():
    assert RULES, "consistency_rules.yaml produced no rules"
    assert all("id" in r and "when" in r and "require" in r for r in RULES)


def test_clean_genomic_wgs_has_no_violations():
    rec = _rec(data_modality=_c("genomic"), data_type=_c("alignments"), assay_type=_c("WGS"))
    assert check_record(rec, RULES) == []


def test_genomic_with_unclassified_assay_is_not_flagged():
    # value_in only fires on a classified field — absence is never a contradiction.
    rec = _rec(data_modality=_c("genomic"), assay_type=NC)
    assert check_record(rec, RULES) == []


def test_transcriptomic_with_wgs_assay_flags_assay_rule():
    rec = _rec(data_modality=_c("transcriptomic.bulk"), assay_type=_c("WGS"))
    ids = _rule_ids(rec)
    assert "assay_for_transcriptomic" in ids
    [v] = [x for x in check_record(rec, RULES) if x.rule_id == "assay_for_transcriptomic"]
    assert v.offending_field == "assay_type"
    assert v.offending_value == "WGS"


def test_histology_with_sequencing_fields_flags_imaging_and_platform_rules():
    rec = _rec(
        data_modality=_c("imaging.histology"),
        data_type=_c("images"),
        assay_type=_c("Histology"),
        platform=_c("ILLUMINA"),
        reference_assembly=NC,
    )
    ids = _rule_ids(rec)
    assert "imaging_exclusive" in ids  # platform must not be classified
    assert "platform_implies_sequencing_modality" in ids  # sequencing platform vs histology


def test_clean_histology_has_no_violations():
    rec = _rec(
        data_modality=_c("imaging.histology"),
        data_type=_c("images"),
        assay_type=_c("Histology"),
        platform=NA,
        reference_assembly=NA,
    )
    assert check_record(rec, RULES) == []


def test_checksum_classified_genomic_flags_auxiliary_inert():
    rec = _rec(md5="abc", name="x.md5", data_type=_c("checksum"), data_modality=_c("genomic"))
    ids = _rule_ids(rec)
    assert "auxiliary_inert" in ids
    [v] = [x for x in check_record(rec, RULES) if x.rule_id == "auxiliary_inert"]
    assert v.offending_field == "data_modality"
    assert v.offending_value == "genomic"


def test_inert_checksum_with_all_not_applicable_is_clean():
    rec = _rec(data_type=_c("checksum"), data_modality=NA, reference_assembly=NA, assay_type=NA, platform=NA)
    assert check_record(rec, RULES) == []


def test_incoherent_entry_does_not_crash():
    # An incoherent entry (status 'classified' but value None) is a malformed record
    # a QA linter must read and keep going on, not abort the whole run over.
    rec = _rec(data_modality=(None, "classified"), data_type=_c("alignments"))
    assert check_record(rec, RULES) == []  # reads raw status, no ValueError raised


def test_malformed_evidence_does_not_crash():
    # A record whose offending field carries a non-list `evidence` must still be
    # flagged (with no evidence ref), not abort the run.
    rec = _rec(data_modality=_c("transcriptomic.bulk"), assay_type=_c("WGS"))
    rec["classifications"]["assay_type"]["evidence"] = "oops-not-a-list"
    [viol] = [v for v in check_record(rec, RULES) if v.rule_id == "assay_for_transcriptomic"]
    assert viol.evidence is None


def test_iter_records_unwraps_shapes_and_skips_non_dicts(tmp_path):
    # A 'results'-keyed envelope, plus a stray non-dict element, must not crash and
    # must yield only the dict records.
    run = tmp_path
    good = _rec(md5="a", data_modality=_c("genomic"))
    (run / "bam_classifications.json").write_text(json.dumps({"results": [good, "stray"]}))
    records = list(iter_records(run))
    assert records == [good]
