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
        # The published values. Not slots of the contract (#424 — they are not
        # input), so they are here because a real record carries them and the
        # validator must go on ignoring them, not because validity depends on them.
        "data_modality": None,
        "reference_assembly": None,
    }
    record.update(overrides)
    return record


def write_metadata(path, records, repository="anvil", input_source=None):
    """Write records into the ``files`` envelope every classification producer reads.

    The producers load through ``pipeline.load_classifiable_snapshot`` (#376), which reads
    the documented envelope — a bare top-level list is the shape the ``validate_metadata``
    gate exists to reject. Shared so the envelope is pinned in one place rather than in
    each producer's test module.

    The envelope names its ``repository`` and nothing else: the catch-all producer reads
    the source's record key off it (#446), while ``published_source`` needs a ``catalog``
    too and so still resolves to None, which keeps every record's ``published.source``
    null as these fixtures pin it. ``input_source`` adds the field ``metadata_block``
    writes (#499) for a test that wants an envelope shaped like a derived input's.
    """
    metadata = {"repository": repository}
    if input_source is not None:
        metadata["input_source"] = input_source
    path.write_text(json.dumps({"metadata": metadata, "files": records}))
    return path


# Every key an output record carries, for the eleven producers alike (#450). Written out
# rather than derived from `OutputRecord`'s fields on purpose: every producer now
# serializes through `to_dict`, so deriving it would make each assertion over it vacuous.
RECORD_KEYS = {
    "file_name",
    "md5sum",
    "file_size",
    "file_format",
    "dataset_title",
    "classifications",
    "entry_id",
    # The durable identity (#433): `file_id` survives a catalog re-index, which
    # `entry_id` does not, and `drs_uri` is the handle a resolver dereferences.
    "file_id",
    "drs_uri",
    # The repository's published values (#424). Present on every record, null on most —
    # `valid_record` declares none, so a record built straight off it pins null. Two of
    # the golden's inputs and the standalone producers' override that, so those fixtures
    # pin the populated block for the schema gate (#465).
    "published",
    # The typed derivation edge (#450). Null on every producer but the index one, which
    # is the only one that resolves a parent; emitted rather than omitted so the
    # envelope keeps one shape across all eleven files.
    "derived_from",
}


# Every key a producer's run `metadata` block carries (#450), in emit order. The record's
# twin above: five ad-hoc shapes became one, and nothing else pins that across producers.
METADATA_KEYS = [
    "total_to_process",
    "processed",
    "successful",
    "failed",
    "dropped",
    "errored",
    "validation_failed",
    "from_cache",
    "content_unreadable",
    "complete",
    # Whatever a producer counts beyond the shared tally (#450).
    "details",
]
