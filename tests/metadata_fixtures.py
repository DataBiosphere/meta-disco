"""Shared builder for contract-valid AnVIL input records (issue #161).

The classification run validates every routed record and diverts a contract
violation to the validation_failed output before it reaches the fetcher. Tests
that need a record to reach the fetcher (or to be accepted by the validator)
start from a valid record and override only the fields under test, so a change to
the contract's field set touches one place rather than every test file.
"""


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
