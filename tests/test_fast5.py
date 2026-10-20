"""Reading a nanopore FAST5's sample from its first bytes, and the file's samples from it (#605).

The FAST5 bytes are built here: the HDF5 signature, padding standing in for the superblock
and the other objects, and attribute messages laid out as NIA_CARD's files lay them out.
``REAL_MESSAGE`` is one such message copied byte for byte from a real file.
"""

import gzip
import json
import struct

import pytest

from meta_disco import code_rules, fast5, fetchers
from meta_disco.evidence import Fast5Evidence, Fast5Header
from meta_disco.fast5 import Fast5Error, sample_ids
from meta_disco.fetchers import FetchError, fetch_fast5_header
from meta_disco.file_name import FileName
from meta_disco.file_types import FAST5_CONFIG
from meta_disco.header_classifier import classify_from_fast5_header
from meta_disco.models import CLASSIFIED, NOT_APPLICABLE
from meta_disco.pipeline import ClassifyPipeline
from meta_disco.producers import producer_of
from meta_disco.sample_identity import FAST5_SAMPLES, NAMED, SEVERAL_SAMPLE_IDS, UNREAD, UNRECOGNISED, Identifier
from meta_disco.unprocessable import CONTENT_UNREADABLE
from meta_disco.unprocessable import _reason_for as reason_for
from tests.metadata_fixtures import valid_record, write_metadata
from tests.test_fetchers import _install, _raise_transport
from tests.test_idat import _reader

MD5 = "c" * 32
NAME = "PAK57726_28c8475f_fcf1fc64_1284.fast5"

# The `sample_id` attribute message of PAK57726_28c8475f_fcf1fc64_1284.fast5 (NIA_CARD), at
# byte 4,928: the object header's message prefix, the attribute message's header, the name
# padded to 16, a string datatype of 8 bytes, a scalar dataspace, the value.
REAL_MESSAGE = bytes.fromhex(
    "0c00300000000000"  # message type 0x000C (attribute), a 48-byte body
    "01000a0008000800"  # attribute message version 1; name 10 bytes, datatype 8, dataspace 8
    "73616d706c655f696400000000000000"  # "sample_id\0", padded to 16
    "1300000008000000"  # a version 1 string, 8 bytes
    "0100000000000000"  # a version 1 scalar dataspace
    "4847303237323300"  # "HG02723\0"
)


def _attribute(
    name: str,
    value: str,
    *,
    version: int = 1,
    datatype_class: int = fast5.STRING_CLASS,
    datatype_version: int = 1,
    rank: int = 0,
    kind: int = fast5.ATTRIBUTE_MESSAGE,
) -> bytes:
    """An attribute message, its object-header prefix included, laid out as NIA_CARD's are."""
    raw_name = name.encode() + b"\x00"
    raw_value = value.encode() + b"\x00"
    size = (len(raw_value) + 7) // 8 * 8
    body = (
        struct.pack("<BxHHH", version, len(raw_name), 8, 8)
        + raw_name.ljust((len(raw_name) + 7) // 8 * 8, b"\x00")
        + struct.pack("<B3sI", datatype_version << 4 | datatype_class, b"\x00\x00\x00", size)
        + struct.pack("<BBB5x", 1, rank, 0)
        + raw_value.ljust(size, b"\x00")
    )
    return struct.pack("<HHB3x", kind, len(body), 0) + body


def _fast5(*messages: bytes, pad: int = 4096) -> bytes:
    return fast5.SIGNATURE + b"\x00" * pad + b"".join(messages) + b"\x00" * 1024


# --- the reader ---------------------------------------------------------------


def test_the_real_message_is_the_layout_the_builder_writes():
    assert _attribute("sample_id", "HG02723") == REAL_MESSAGE


def test_the_sample_id_is_read_from_a_real_message():
    assert sample_ids(_fast5(REAL_MESSAGE)) == ["HG02723"]


def test_the_other_attributes_are_not_read():
    head = _fast5(_attribute("flow_cell_id", "PAK57726"), REAL_MESSAGE, _attribute("protocol_group_id", "HG02723"))
    assert sample_ids(head) == ["HG02723"]


def test_each_distinct_value_is_listed_once_in_the_order_found():
    head = _fast5(_attribute("sample_id", "HG00733"), REAL_MESSAGE, _attribute("sample_id", "HG00733"))
    assert sample_ids(head) == ["HG00733", "HG02723"]


def test_a_head_holding_no_sample_id_gives_none():
    assert sample_ids(_fast5(_attribute("run_id", "fcf1fc64"))) == []


@pytest.mark.parametrize(
    "stray",
    [
        pytest.param(b"some text naming sample_id\x00 in passing", id="no message header before it"),
        pytest.param(_attribute("barcode_sample_id", "HG00096"), id="a longer name ending in it"),
        pytest.param(_attribute("sample_id", "HG00096", kind=0x0003), id="another message type"),
    ],
)
def test_the_name_outside_a_sample_id_attribute_message_is_skipped(stray):
    assert sample_ids(_fast5(stray, REAL_MESSAGE)) == ["HG02723"]


@pytest.mark.parametrize(
    "blob, match",
    [
        pytest.param(b"not a fast5 at all", "not the HDF5 signature", id="no signature"),
        pytest.param(gzip.compress(_fast5(REAL_MESSAGE)), "not the HDF5 signature", id="gzipped"),
        pytest.param(_fast5(_attribute("sample_id", "HG02723", version=3)), "version 3", id="attribute version"),
        pytest.param(
            _fast5(_attribute("sample_id", "HG02723", datatype_class=0)), "datatype class 0", id="not a string"
        ),
        pytest.param(
            _fast5(_attribute("sample_id", "HG02723", datatype_version=2)), "version 2", id="datatype version"
        ),
        pytest.param(_fast5(_attribute("sample_id", "HG02723", rank=1)), "rank 1", id="not a scalar"),
    ],
)
def test_bytes_this_reader_does_not_read_are_refused(blob, match):
    with pytest.raises(Fast5Error, match=match):
        sample_ids(blob)


def test_a_message_running_past_the_bytes_read_is_unread_not_refused():
    head = fast5.SIGNATURE + b"\x00" * 64 + REAL_MESSAGE
    assert sample_ids(head[:-4]) == [] and sample_ids(head[:-20]) == []


def test_a_space_padded_value_loses_its_padding():
    message = bytearray(_attribute("sample_id", "HG02723"))
    struct.pack_into("<B", message, 33, fast5.SPACE_PAD)  # the datatype's padding type
    message[48:56] = b"HG02723 "
    assert sample_ids(_fast5(bytes(message))) == ["HG02723"]


def test_a_value_longer_than_its_message_is_refused():
    message = bytearray(REAL_MESSAGE)
    struct.pack_into("<H", message, 2, 40)  # the message's body length, 8 short of what it holds
    with pytest.raises(Fast5Error, match="runs past its message"):
        sample_ids(_fast5(bytes(message)))


def test_the_reader_reads_one_range_from_the_start():
    calls = []
    fetch = _reader(_fast5(REAL_MESSAGE, pad=100_000), calls)
    assert fast5.read_header(fetch) == Fast5Header(sample_ids=[])  # the attribute sits past the head
    assert calls == [(0, fast5.HEAD_LENGTH - 1)]


# --- the fetcher --------------------------------------------------------------


def test_the_fetcher_reads_and_caches_the_header(monkeypatch, tmp_path):
    _install(monkeypatch, _fast5(REAL_MESSAGE) + b"\x00" * 200_000)
    header = fetch_fast5_header(tmp_path, MD5, file_name=NAME)
    assert header.sample_ids == ["HG02723"]
    cached = Fast5Evidence.load(tmp_path, MD5)
    assert cached.header == header and cached.raw_bytes_fetched == fast5.HEAD_LENGTH
    monkeypatch.setattr(fetchers, "_fetch_range", _raise_transport)
    assert fetch_fast5_header(tmp_path, MD5) == header


def test_a_cached_header_of_the_wrong_type_is_a_cache_miss():
    assert Fast5Evidence.from_json({"md5sum": MD5, "header": {"sample_ids": "HG02723"}}) is None
    assert Fast5Evidence.from_json({"md5sum": MD5, "header": {}}) is None


def test_bytes_that_are_no_fast5_are_a_fetch_error(monkeypatch, tmp_path):
    _install(monkeypatch, b"not a fast5 at all, just text")
    with pytest.raises(FetchError, match="FAST5 header: Fast5Error"):
        fetch_fast5_header(tmp_path, MD5, is_gzipped=True)


# --- the file's samples ---------------------------------------------------------


def test_one_recognised_sample_id_names_the_files_sample():
    reading = FAST5_SAMPLES.read(Fast5Header(sample_ids=["GM24385"]), "ANVIL_NIA_CARD_Coriell_Cell_Lines_Open")
    assert reading.outcome == NAMED
    assert reading.members == frozenset({Identifier("coriell", "NA24385")})


def test_a_head_holding_none_is_unread():
    assert FAST5_SAMPLES.read(Fast5Header(sample_ids=[]), "d").outcome == UNREAD


@pytest.mark.parametrize(
    "ids, unrecognised",
    [
        pytest.param(["HG02723", "HG00733"], (SEVERAL_SAMPLE_IDS,), id="two values"),
        pytest.param(["no_sample"], ("no_sample",), id="a value no rule recognises"),
    ],
)
def test_two_values_or_an_unrecognised_one_name_no_sample(ids, unrecognised):
    reading = FAST5_SAMPLES.read(Fast5Header(sample_ids=ids), "d")
    assert (reading.outcome, reading.unrecognised, reading.reference()) == (UNRECOGNISED, unrecognised, None)


# --- routing, classifying and the pipeline ----------------------------------------


@pytest.mark.parametrize(
    "name, producer",
    [("x.fast5", "fast5"), ("X.FAST5", "fast5"), ("x.pod5", "auxiliary"), ("x.fast5.tar", "tar")],
)
def test_a_fast5_is_the_fast5_types_and_its_neighbours_stay_where_they_were(name, producer):
    routed = producer_of({"file_name": name})
    assert routed is not None and routed.name == producer


def test_the_classifier_gives_what_the_extension_gives():
    result = classify_from_fast5_header(Fast5Header(sample_ids=["HG02723"]), name=FileName.parse(NAME))
    assert {slot: (result[slot]["value"], result[slot]["status"]) for slot in ("data_type", "platform")} == {
        "data_type": ("raw_signal", CLASSIFIED),
        "platform": ("ONT", CLASSIFIED),
    }
    assert result["reference_assembly"]["status"] == NOT_APPLICABLE
    assert {e.get("rule_id") for entry in result.values() for e in entry["evidence"]} <= {"nanopore_fast5", None}


def _run(tmp_path, record) -> dict:
    pipeline = ClassifyPipeline(
        FAST5_CONFIG,
        write_metadata(tmp_path / "in.json", [record]),
        tmp_path / "out.json",
        evidence_base=tmp_path / "ev",
        workers=1,
    )
    (row,) = pipeline.run()
    return row


def test_a_failed_read_keeps_what_the_name_gives_and_is_counted_unreadable(monkeypatch, tmp_path):
    """A fast5's dimensions come from its name, so a read that fails costs it only its samples."""
    monkeypatch.setattr(fetchers, "_fetch_range", _raise_transport)
    row = _run(tmp_path, valid_record(file_name=NAME, file_format=".fast5", file_md5sum=MD5))
    assert row["samples"] is None
    assert row["classifications"]["data_type"]["value"] == "raw_signal"
    assert row["classifications"]["reference_assembly"]["status"] == NOT_APPLICABLE
    assert reason_for(row) is CONTENT_UNREADABLE
    envelope = json.loads((tmp_path / "out.json").read_text())
    assert envelope["metadata"]["content_unreadable"] == 1


def test_an_archive_declaring_fast5_that_no_type_claims_keeps_what_its_name_gives(monkeypatch, tmp_path):
    """`x.fast5.tar.xz` declaring `.fast5` routes here by its format, and its bytes are no HDF5."""
    _install(monkeypatch, b"\xfd7zXZ\x00 an xz stream")
    record = valid_record(file_name="HG02148_1.fast5.tar.xz", file_format=".fast5", file_md5sum=MD5)
    row = _run(tmp_path, record)
    assert (row["classifications"]["data_type"]["value"], row["classifications"]["platform"]["value"]) == (
        "raw_signal",
        "ONT",
    )
    assert reason_for(row) is CONTENT_UNREADABLE


def test_the_pipeline_writes_the_sample_a_real_fast5_names(monkeypatch, tmp_path):
    """The batch path, with the real fetcher: the row carries the sample, credited to the content rule."""
    _install(monkeypatch, _fast5(REAL_MESSAGE))
    record = valid_record(
        file_name=NAME, file_format=".fast5", file_md5sum=MD5, dataset_title="ANVIL_NIA_CARD_Coriell_Cell_Lines_Open"
    )
    pipeline = ClassifyPipeline(
        FAST5_CONFIG,
        write_metadata(tmp_path / "in.json", [record]),
        tmp_path / "out.json",
        evidence_base=tmp_path / "ev",
        workers=1,
    )
    (row,) = pipeline.run()
    assert row["samples"]["count"] == 1
    assert row["samples"]["named_by"] == [
        {"source_type": "content_read", "rule_id": code_rules.FAST5_TRACKING_SAMPLE.id}
    ]
    assert row["classifications"]["data_type"]["value"] == "raw_signal"
