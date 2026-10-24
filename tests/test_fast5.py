"""Reading a nanopore FAST5's sample and device from its first bytes, the file's samples from the
one (#605) and its instrument model from the other (#747).

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
from meta_disco.fast5 import Fast5Error
from meta_disco.fetchers import FetchError, fetch_fast5_header
from meta_disco.file_name import FileName
from meta_disco.file_types import FAST5_CONFIG
from meta_disco.header_classifier import (
    FAST5_DEVICES,
    classify_from_fast5_header,
    fast5_instrument,
)
from meta_disco.models import CLASSIFIED, NOT_APPLICABLE, NOT_CLASSIFIED
from meta_disco.pipeline import ClassifyPipeline
from meta_disco.producers import producer_of
from meta_disco.rule_engine import CONTENT_TIER
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
    bits: int = 0,
    datatype_length: int = 8,
    dataspace_version: int = 1,
) -> bytes:
    """An attribute message, its object-header prefix included, laid out as NIA_CARD's are.

    ``datatype_length`` past 8 adds that many bytes of datatype properties, padded to 8 as HDF5 pads them."""
    raw_name = name.encode() + b"\x00"
    raw_value = value.encode() + b"\x00"
    size = (len(raw_value) + 7) // 8 * 8
    datatype = struct.pack("<B3sI", datatype_version << 4 | datatype_class, bytes([bits, 0, 0]), size)
    body = (
        struct.pack("<BxHHH", version, len(raw_name), datatype_length, 8)
        + raw_name.ljust((len(raw_name) + 7) // 8 * 8, b"\x00")
        + datatype.ljust((max(datatype_length, 8) + 7) // 8 * 8, b"\x00")
        + struct.pack("<BBB5x", dataspace_version, rank, 0)
        + raw_value.ljust(size, b"\x00")
    )
    return struct.pack("<HHB3x", kind, len(body), 0) + body


def sample_ids(head: bytes) -> list[str]:
    return fast5.attribute_values(head, fast5.SAMPLE_ID)


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
        pytest.param(
            _fast5(_attribute("sample_id", "HG02723", dataspace_version=2)),
            "dataspace version 2",
            id="dataspace version",
        ),
        pytest.param(_fast5(_attribute("sample_id", "HG02723", datatype_length=4)), "cut short", id="datatype short"),
    ],
)
def test_bytes_this_reader_does_not_read_are_refused(blob, match):
    with pytest.raises(Fast5Error, match=match):
        sample_ids(blob)


@pytest.mark.parametrize(
    "message",
    [REAL_MESSAGE, _attribute("sample_id", "HG02723", version=3)],
    ids=["version 1", "a version this reader refuses"],
)
def test_a_message_running_past_the_bytes_read_is_unread_not_refused(message):
    head = fast5.SIGNATURE + b"\x00" * 64 + message
    assert sample_ids(head[:-4]) == [] and sample_ids(head[:-20]) == []


def test_a_message_declaring_more_than_the_bytes_read_hold_is_unread():
    """The value fits, but 16 of the bytes the message declares were never read."""
    message = bytearray(REAL_MESSAGE)
    struct.pack_into("<H", message, 2, 64)  # the message's body length, 16 past its value
    assert sample_ids(fast5.SIGNATURE + b"\x00" * 64 + bytes(message)) == []


def _padded_value(padding: int, value: bytes) -> bytes:
    """The real message with its datatype's padding type and its 8-byte value replaced."""
    message = bytearray(REAL_MESSAGE)
    struct.pack_into("<B", message, 33, padding)
    message[48:56] = value
    return _fast5(bytes(message))


@pytest.mark.parametrize(
    "padding, value, read",
    [
        pytest.param(fast5.NULL_TERM, b"HG02723\x00", "HG02723", id="null-terminated"),
        pytest.param(fast5.NULL_TERM, b"HG027\x00zz", "HG027", id="null-terminated with bytes after"),
        pytest.param(fast5.NULL_PAD, b"HG027\x00\x00\x00", "HG027", id="null-padded"),
        pytest.param(fast5.NULL_PAD, b"HG027\x00ab", "HG027\x00ab", id="null-padded with a NUL inside"),
        pytest.param(fast5.SPACE_PAD, b"HG02723 ", "HG02723", id="space-padded"),
    ],
)
def test_each_padding_type_ends_the_value_where_hdf5_says(padding, value, read):
    assert sample_ids(_padded_value(padding, value)) == [read]


def test_a_datatype_longer_than_8_bytes_is_padded_to_8():
    assert sample_ids(_fast5(_attribute("sample_id", "HG02723", datatype_length=12))) == ["HG02723"]


def test_a_dataspace_declared_too_short_is_refused():
    message = bytearray(REAL_MESSAGE)
    struct.pack_into("<H", message, 14, 4)  # the attribute message's dataspace length
    with pytest.raises(Fast5Error, match="cut short"):
        sample_ids(_fast5(bytes(message)))


def test_a_utf8_value_is_read_with_its_charset_bits_set():
    """The padding type is the low nibble of the class bits; the charset (UTF-8 = 1) is the high one."""
    message = _attribute("sample_id", "HG0272é", bits=1 << 4 | fast5.NULL_PAD)
    assert sample_ids(_fast5(message)) == ["HG0272é"]


def test_the_name_just_after_the_signature_has_no_room_for_a_header():
    assert sample_ids(fast5.SIGNATURE + b"sample_id\x00" + b"\x00" * 64) == []


def test_an_unknown_padding_type_is_refused():
    with pytest.raises(Fast5Error, match="padding type 3"):
        sample_ids(_padded_value(3, b"HG02723\x00"))


def test_a_value_longer_than_its_message_is_refused():
    message = bytearray(REAL_MESSAGE)
    struct.pack_into("<H", message, 2, 40)  # the message's body length, 8 short of what it holds
    with pytest.raises(Fast5Error, match="runs past its message"):
        sample_ids(_fast5(bytes(message)))


def test_the_device_type_is_read_beside_the_sample_id():
    head = _fast5(REAL_MESSAGE, _attribute("device_type", "promethion"))
    assert fast5.read_header(_reader(head, [])) == Fast5Header(sample_ids=["HG02723"], device_types=["promethion"])
    assert fast5.read_header(_reader(_fast5(REAL_MESSAGE), [])).device_types == []


def test_each_distinct_device_type_is_read_once_in_the_order_found():
    head = _fast5(*(_attribute("device_type", v) for v in ("promethion", "minion", "promethion")))
    assert fast5.attribute_values(head, fast5.DEVICE_TYPE) == ["promethion", "minion"]


def test_a_device_type_laid_out_otherwise_is_refused_by_its_name():
    with pytest.raises(Fast5Error, match="a device_type attribute message of version 2"):
        fast5.attribute_values(_fast5(_attribute("device_type", "promethion", version=2)), fast5.DEVICE_TYPE)


def test_a_device_type_laid_out_otherwise_costs_the_device_not_the_sample():
    head = _fast5(REAL_MESSAGE, _attribute("device_type", "promethion", version=2))
    assert fast5.read_header(_reader(head, [])) == Fast5Header(sample_ids=["HG02723"], device_types=None)


def test_the_reader_reads_one_range_from_the_start():
    calls = []
    fetch = _reader(_fast5(REAL_MESSAGE, pad=100_000), calls)
    assert fast5.read_header(fetch) == Fast5Header(sample_ids=[], device_types=[])  # the attribute sits past the head
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
    assert Fast5Evidence.from_json({"md5sum": MD5, "header": {"sample_ids": [1]}}) is None
    assert Fast5Evidence.from_json({"md5sum": MD5, "header": {"sample_ids": [], "device_types": "minion"}}) is None


def test_a_device_type_read_as_unreadable_is_cached_as_null():
    entry = {"md5sum": MD5, "header": {"sample_ids": ["HG02723"], "device_types": None}}
    assert Fast5Evidence.from_json(entry).header == Fast5Header(sample_ids=["HG02723"], device_types=None)


def test_a_cached_header_from_before_the_device_type_is_read_again(monkeypatch, tmp_path):
    """An entry holding only the sample ids (#605) is a miss, so the head is fetched again (#747)."""
    old = {"md5sum": MD5, "file_name": NAME, "raw_bytes_fetched": 1, "header": {"sample_ids": ["HG02723"]}}
    assert Fast5Evidence.from_json(old) is None
    _install(monkeypatch, _fast5(REAL_MESSAGE, _attribute("device_type", "promethion")))
    path = tmp_path / MD5[:2] / f"{MD5}.json"
    path.parent.mkdir()
    path.write_text(json.dumps(old))
    assert fetch_fast5_header(tmp_path, MD5, file_name=NAME).device_types == ["promethion"]


def test_bytes_that_are_no_fast5_are_a_fetch_error(monkeypatch, tmp_path):
    _install(monkeypatch, b"not a fast5 at all, just text")
    with pytest.raises(FetchError, match="FAST5 header: Fast5Error"):
        fetch_fast5_header(tmp_path, MD5, is_gzipped=True)


# --- the file's samples ---------------------------------------------------------


def test_one_recognised_sample_id_names_the_files_sample():
    reading = FAST5_SAMPLES.read(
        Fast5Header(sample_ids=["GM24385"], device_types=[]), "ANVIL_NIA_CARD_Coriell_Cell_Lines_Open"
    )
    assert reading.outcome == NAMED
    assert reading.members == frozenset({Identifier("coriell", "NA24385")})


def test_a_head_holding_none_is_unread():
    assert FAST5_SAMPLES.read(Fast5Header(sample_ids=[], device_types=[]), "d").outcome == UNREAD


@pytest.mark.parametrize(
    "ids, unrecognised",
    [
        pytest.param(["HG02723", "HG00733"], (SEVERAL_SAMPLE_IDS,), id="two values"),
        pytest.param(["no_sample"], ("no_sample",), id="a value no rule recognises"),
    ],
)
def test_two_values_or_an_unrecognised_one_name_no_sample(ids, unrecognised):
    reading = FAST5_SAMPLES.read(Fast5Header(sample_ids=ids, device_types=[]), "d")
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
    result = classify_from_fast5_header(Fast5Header(sample_ids=["HG02723"], device_types=[]), name=FileName.parse(NAME))
    assert {slot: (result[slot]["value"], result[slot]["status"]) for slot in ("data_type", "platform")} == {
        "data_type": ("raw_signal", CLASSIFIED),
        "platform": ("ONT", CLASSIFIED),
    }
    assert result["reference_assembly"]["status"] == NOT_APPLICABLE
    assert {e.get("rule_id") for entry in result.values() for e in entry["evidence"]} <= {
        "nanopore_fast5",
        code_rules.FAST5_DEVICE_TYPE.id,
        None,
    }


def _instrument(device_types: list[str] | None) -> dict:
    return classify_from_fast5_header(Fast5Header(sample_ids=[], device_types=device_types), name=FileName.parse(NAME))[
        "instrument_model"
    ]


@pytest.mark.parametrize("device_type, model", sorted(FAST5_DEVICES.items()))
def test_a_recognised_device_type_gives_the_instrument_model_at_the_content_tier(device_type, model):
    entry = _instrument([device_type])
    assert (entry["value"], entry["status"]) == (model, CLASSIFIED)
    (claim,) = [e for e in entry["evidence"] if e.get("rule_id") == code_rules.FAST5_DEVICE_TYPE.id]
    assert (claim["tier"], claim["source_type"]) == (CONTENT_TIER, "content_read")
    assert fast5_instrument(Fast5Header(sample_ids=[], device_types=[device_type]))[0] == model


@pytest.mark.parametrize(
    "device_types, said",
    [
        pytest.param([], "holds no device_type", id="none"),
        pytest.param(["flongle"], "'flongle': not a device", id="a value the table lacks"),
        pytest.param(["PromethION"], "'PromethION': not a device", id="a value in another case"),
        pytest.param(["promethion", "minion"], "several device_types ['promethion', 'minion']", id="two values"),
        pytest.param(None, "laid out otherwise", id="one laid out otherwise"),
    ],
)
def test_a_head_naming_no_one_recognised_device_is_left_not_classified_with_what_was_read(device_types, said):
    entry = _instrument(device_types)
    assert (entry["value"], entry["status"]) == (None, NOT_CLASSIFIED)
    (claim,) = [e for e in entry["evidence"] if e.get("rule_id") == code_rules.FAST5_DEVICE_TYPE.id]
    assert (claim["tier"], claim["status"]) == (CONTENT_TIER, NOT_CLASSIFIED)
    assert said in claim["reason"]


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
    slots = row["classifications"]
    marked = {s for s, e in slots.items() if any(x.get("rule_id") == code_rules.FETCH_FAILED.id for x in e["evidence"])}
    assert marked and marked == {s for s, e in slots.items() if e["status"] == "not_classified"}
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
    """The batch path, with the real fetcher: the row carries the sample and the instrument, each credited to its
    content rule."""
    _install(monkeypatch, _fast5(REAL_MESSAGE, _attribute("device_type", "promethion")))
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
    assert row["classifications"]["instrument_model"]["value"] == "PromethION"


def test_a_head_with_no_device_type_keeps_its_sample_and_says_why_it_has_no_instrument(monkeypatch, tmp_path):
    _install(monkeypatch, _fast5(REAL_MESSAGE))
    row = _run(tmp_path, valid_record(file_name=NAME, file_format=".fast5", file_md5sum=MD5, dataset_title="d"))
    assert row["samples"]["count"] == 1
    entry = row["classifications"]["instrument_model"]
    assert entry["status"] == NOT_CLASSIFIED
    assert [e["reason"] for e in entry["evidence"] if e.get("rule_id") == code_rules.FAST5_DEVICE_TYPE.id] == [
        "the head read holds no device_type"
    ]
