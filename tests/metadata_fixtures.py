"""Shared builder for contract-valid AnVIL input records (issue #161).

The classification run validates every routed record and diverts a contract
violation to the validation_failed output before it reaches the fetcher. Tests
that need a record to reach the fetcher (or to be accepted by the validator)
start from a valid record and override only the fields under test, so a change to
the contract's field set touches one place rather than every test file.
"""

import json


def valid_record(**overrides):
    """A record satisfying the input-metadata contract; override to introduce a defect."""
    record = {
        "entry_id": "e1",
        "file_id": "f1",
        "file_name": "sample.test",
        "file_format": ".test",
        "file_size": 1000,
        "file_md5sum": "0" * 32,
        "drs_uri": "drs://example/abc",
        "dataset_id": "d1",
        "dataset_title": "A Dataset",
        "is_supplementary": False,
        "data_modality": None,
        "reference_assembly": None,
    }
    record.update(overrides)
    return record


def write_metadata(path, records):
    """Write records into the ``files`` envelope every classification producer reads.

    The producers load through ``pipeline.load_classifiable_records`` (#376), which reads
    the documented envelope — a bare top-level list is the shape the ``validate_metadata``
    gate exists to reject. Shared so the envelope is pinned in one place rather than in
    each producer's test module.
    """
    path.write_text(json.dumps({"files": records}))
    return path
