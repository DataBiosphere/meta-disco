"""Reading an Illumina IDAT's header, and classifying from it (#603).

The IDAT bytes are built here: a preamble, a field table, and the fields the reader
takes, optionally behind padding that stands in for the per-probe intensities, so a field
past the first read is reached by its own range request.
"""

import gzip
import json
import struct

import pytest

from meta_disco import fetchers, idat
from meta_disco.evidence import IdatEvidence, IdatHeader
from meta_disco.fetchers import FetchError, fetch_idat_header
from meta_disco.file_name import FileName
from meta_disco.file_types import IDAT_CONFIG
from meta_disco.header_classifier import IDAT_CHIPS, IDAT_SCANNERS, classify_from_idat_header
from meta_disco.models import CLASSIFIED, NOT_APPLICABLE, NOT_CLASSIFIED
from meta_disco.pipeline import ClassifyPipeline
from tests.metadata_fixtures import valid_record, write_metadata
from tests.test_fetchers import _install, _raise_transport

MD5 = "b" * 32
SCAN = "iScan Control Software"
CHIP = "1-95um_multi-swath_for_8x2-5M"
PROBES = 2_522_340


def _string(text: str) -> bytes:
    raw = text.encode()
    length, prefix = len(raw), bytearray()
    while True:
        byte = length & 0x7F
        length >>= 7
        prefix.append(byte | (0x80 if length else 0))
        if not length:
            return bytes(prefix) + raw


def _run_info(rows: list[tuple[str, str, str, str, str]]) -> bytes:
    return struct.pack("<i", len(rows)) + b"".join(_string(cell) for row in rows for cell in row)


def _scan(software: str = SCAN) -> list[tuple[str, str, str, str, str]]:
    return [
        ("7/24/2017 6:15:02 AM", "Decoding", "CallsToUsed=1", "AutoDecode", "2.6.2"),
        ("8/14/2020 4:56:32 PM", "Scan", "ScannerID=N0655", software, "3.4.8"),
        ("8/14/2020 4:56:32 PM", "Register", "Algorithm=StandardGeneric", software, "3.4.8"),
    ]


def _idat(
    *,
    probes: int | None = PROBES,
    chip: str | None = CHIP,
    run_info: list | None = None,
    pad: int = 0,
    run_info_first: bool = False,
    magic: bytes = b"IDAT",
    version: int = 3,
) -> bytes:
    """An IDAT whose probe count follows the table and whose text fields follow ``pad`` bytes."""
    head_fields = {} if probes is None else {idat.FIELD_PROBE_COUNT: struct.pack("<i", probes)}
    tail_fields = {}
    if chip is not None:
        tail_fields[idat.FIELD_CHIP_TYPE] = _string(chip)
    if run_info is not None:
        tail_fields[idat.FIELD_RUN_INFO] = _run_info(run_info)
    if run_info_first:
        tail_fields = dict(reversed(tail_fields.items()))
    n = len(head_fields) + len(tail_fields)
    offset = 16 + 10 * n
    table, body = b"", b""
    for code, data in head_fields.items():
        table += struct.pack("<Hq", code, offset + len(body))
        body += data
    body += b"\0" * pad
    for code, data in tail_fields.items():
        table += struct.pack("<Hq", code, offset + len(body))
        body += data
    return struct.pack("<4sqi", magic, version, n) + table + body


def _reader(blob: bytes, calls: list | None = None):
    def fetch(start: int, end: int) -> bytes:
        if calls is not None:
            calls.append((start, end))
        return blob[start : end + 1]

    return fetch


# --- the reader ---------------------------------------------------------------


@pytest.mark.parametrize("run_info_first", [False, True], ids=["chip type first", "run log first"])
def test_the_header_fields_are_read_from_the_head_and_one_window_at_the_tail(run_info_first):
    calls: list = []
    blob = _idat(run_info=_scan(), pad=200_000, run_info_first=run_info_first)
    header = idat.read_header(_reader(blob, calls))
    assert header == IdatHeader(probe_count=PROBES, chip_type=CHIP, scan_software=[SCAN])
    # The head serves the probe count; the chip type and run log share one window.
    assert len(calls) == 2


def test_fields_inside_the_head_need_no_second_read():
    calls: list = []
    assert idat.read_header(_reader(_idat(run_info=_scan()), calls)).chip_type == CHIP
    assert len(calls) == 1


def test_a_field_the_table_does_not_list_is_none():
    header = idat.read_header(_reader(_idat(probes=None, chip=None)))
    assert header == IdatHeader(probe_count=None, chip_type=None, scan_software=[])


def test_a_string_longer_than_127_bytes_reads_its_two_byte_length():
    chip = "x" * 300
    assert idat.read_header(_reader(_idat(chip=chip))).chip_type == chip


@pytest.mark.parametrize(
    ("blob", "match"),
    [
        pytest.param(_idat(magic=b"IDAX"), "not b'IDAT'", id="wrong magic"),
        pytest.param(_idat(version=1), "version 1", id="version 1"),
        pytest.param(b"IDAT", "shorter than the IDAT preamble", id="no preamble"),
        pytest.param(struct.pack("<4sqi", b"IDAT", 3, 1000), "runs past", id="table past the head"),
        pytest.param(_idat(run_info=_scan())[:-3], "runs past the bytes read", id="file cut short"),
    ],
)
def test_bytes_that_are_no_readable_idat_are_refused(blob, match):
    with pytest.raises(idat.IdatError, match=match):
        idat.read_header(_reader(blob))


def test_an_offset_into_the_table_is_refused_rather_than_read():
    # A negative or tiny offset would read the preamble's own bytes as a field.
    blob = bytearray(_idat(chip=None))
    struct.pack_into("<Hq", blob, 16, idat.FIELD_PROBE_COUNT, -8)
    with pytest.raises(idat.IdatError, match="inside the 26-byte preamble and table"):
        idat.read_header(_reader(bytes(blob)))


@pytest.mark.parametrize(
    ("field", "wrong"),
    [("scan_software", None), ("probe_count", True), ("probe_count", "2522340"), ("chip_type", 7)],
    ids=["no software list", "a boolean probe count", "a string probe count", "a numeric chip type"],
)
def test_a_cached_header_with_a_field_of_the_wrong_type_is_a_cache_miss(tmp_path, field, wrong):
    IdatEvidence(md5sum=MD5, file_name="x.idat", header=IdatHeader(1, "c", ["s"])).save(tmp_path)
    path = next(tmp_path.rglob("*.json"))
    cached = json.loads(path.read_text())
    cached["header"][field] = wrong
    path.write_text(json.dumps(cached))
    assert IdatEvidence.load(tmp_path, MD5) is None


def test_text_fields_too_far_apart_for_one_window_are_each_read_in_their_own(monkeypatch):
    monkeypatch.setattr(idat, "FIELD_WINDOW", 256)
    blob = bytearray(_idat(run_info=_scan(), pad=10_000))
    # Push the run log 1,000 bytes past the chip type, beyond one window's reach.
    offsets = idat.field_offsets(bytes(blob[:4096]))
    run_log = bytes(blob[offsets[idat.FIELD_RUN_INFO] :])
    blob = blob[: offsets[idat.FIELD_RUN_INFO]] + b"\0" * 1_000 + run_log
    entry = list(offsets).index(idat.FIELD_RUN_INFO)
    struct.pack_into("<Hq", blob, 16 + 10 * entry, idat.FIELD_RUN_INFO, offsets[idat.FIELD_RUN_INFO] + 1_000)
    calls: list = []
    header = idat.read_header(_reader(bytes(blob), calls))
    assert header == IdatHeader(probe_count=PROBES, chip_type=CHIP, scan_software=[SCAN])
    assert len(calls) == 3


def test_a_negative_run_log_row_count_is_refused():
    blob = bytearray(_idat(run_info=_scan()))
    offset = idat.field_offsets(bytes(blob[:4096]))[idat.FIELD_RUN_INFO]
    struct.pack_into("<i", blob, offset, -1)
    with pytest.raises(idat.IdatError, match="a run log of -1 rows"):
        idat.read_header(_reader(bytes(blob)))


def test_a_field_longer_than_its_window_is_refused(monkeypatch):
    monkeypatch.setattr(idat, "FIELD_WINDOW", 64)
    with pytest.raises(idat.IdatError, match="runs past"):
        idat.read_header(_reader(_idat(chip="y" * 100, pad=10_000)))


# --- the fetcher --------------------------------------------------------------


def test_the_fetcher_reads_and_caches_the_header(monkeypatch, tmp_path):
    blob = _idat(run_info=_scan(), pad=200_000)
    _install(monkeypatch, blob)
    header = fetch_idat_header(tmp_path, MD5, file_name="x_Red.idat")
    assert header.chip_type == CHIP
    cached = IdatEvidence.load(tmp_path, MD5)
    # The head and one tail window, never the padding between them.
    assert cached.header == header and cached.raw_bytes_fetched < idat.HEAD_LENGTH + 1_000
    monkeypatch.setattr(fetchers, "_fetch_range", _raise_transport)
    assert fetch_idat_header(tmp_path, MD5) == header


def test_a_plain_idat_is_read_even_though_the_pipeline_says_it_may_be_gzipped(monkeypatch, tmp_path):
    # The pipeline passes is_gzipped=True for a type with no gzip extension (#603).
    _install(monkeypatch, _idat())
    assert fetch_idat_header(tmp_path, MD5, is_gzipped=True).chip_type == CHIP


def test_a_gzipped_idat_is_refused(monkeypatch, tmp_path):
    _install(monkeypatch, gzip.compress(_idat()))
    with pytest.raises(FetchError, match="gzipped"):
        fetch_idat_header(tmp_path, MD5, is_gzipped=True)


def test_bytes_that_are_no_idat_are_a_fetch_error(monkeypatch, tmp_path):
    _install(monkeypatch, b"not an idat at all, just text")
    with pytest.raises(FetchError, match="IDAT header: IdatError"):
        fetch_idat_header(tmp_path, MD5)


def test_the_pipeline_reads_a_real_idat_through_its_own_fetch_call(monkeypatch, tmp_path):
    """The batch path, with the real fetcher: what the pipeline passes it must not stop the read (#603)."""
    _install(monkeypatch, _idat(run_info=_scan(), pad=10_000))
    record = valid_record(file_name="x_Red.idat", file_format=".idat", file_md5sum=MD5)
    pipeline = ClassifyPipeline(
        IDAT_CONFIG,
        write_metadata(tmp_path / "in.json", [record]),
        tmp_path / "out.json",
        evidence_base=tmp_path / "ev",
        workers=1,
    )
    (row,) = pipeline.run()
    assert {slot: c["value"] for slot, c in row["classifications"].items() if slot != "reference_assembly"} == {
        "data_type": "array_signal",
        "data_modality": IDAT_CHIPS[(CHIP, PROBES)][1],
        "assay_type": IDAT_CHIPS[(CHIP, PROBES)][2],
        "platform": IDAT_SCANNERS[SCAN][0],
        "instrument_model": IDAT_SCANNERS[SCAN][1],
    }


# --- the classifier -----------------------------------------------------------


def _classify(header: IdatHeader) -> dict:
    return classify_from_idat_header(header, name=FileName.parse("201868530174_R03C01_Red.idat"))


def _entry(result: dict, field: str) -> tuple:
    entry = result[field]
    return entry["value"], entry["status"], [e.get("rule_id") for e in entry["evidence"]]


def test_a_recognised_chip_and_scanner_decide_four_dimensions():
    _, modality, assay = IDAT_CHIPS[(CHIP, PROBES)]
    platform, model = IDAT_SCANNERS[SCAN]
    result = _classify(IdatHeader(probe_count=PROBES, chip_type=CHIP, scan_software=[SCAN, SCAN]))
    assert _entry(result, "data_modality") == (modality, CLASSIFIED, ["idat_chip_type"])
    assert _entry(result, "assay_type") == (assay, CLASSIFIED, ["idat_chip_type"])
    assert _entry(result, "platform") == (platform, CLASSIFIED, ["idat_scanner"])
    assert _entry(result, "instrument_model") == (model, CLASSIFIED, ["idat_scanner"])
    assert _entry(result, "data_type") == ("array_signal", CLASSIFIED, ["idat_array_signal"])
    assert _entry(result, "reference_assembly") == (None, NOT_APPLICABLE, ["idat_array_signal"])


def test_a_header_only_call_still_takes_what_the_extension_says():
    result = classify_from_idat_header(IdatHeader(probe_count=PROBES, chip_type=CHIP, scan_software=[SCAN]))
    assert _entry(result, "data_type") == ("array_signal", CLASSIFIED, ["idat_array_signal"])
    assert _entry(result, "reference_assembly") == (None, NOT_APPLICABLE, ["idat_array_signal"])


@pytest.mark.parametrize(
    "header",
    [
        pytest.param(
            IdatHeader(probe_count=1_051_943, chip_type="BeadChip 8x5", scan_software=[SCAN]), id="another chip"
        ),
        pytest.param(
            IdatHeader(probe_count=PROBES + 1, chip_type=CHIP, scan_software=[SCAN]), id="another probe count"
        ),
        pytest.param(IdatHeader(probe_count=None, chip_type=None, scan_software=[SCAN]), id="neither field"),
    ],
)
def test_a_chip_not_recognised_is_left_not_classified_with_what_was_read(header):
    result = _classify(header)
    for field in ("data_modality", "assay_type"):
        value, status, rules = _entry(result, field)
        assert (value, status, rules) == (None, NOT_CLASSIFIED, ["idat_chip_type"])
        assert repr(header.chip_type) in result[field]["evidence"][0]["reason"]
    # The extension still says what the file is.
    assert _entry(result, "data_type")[0] == "array_signal"


def test_file_text_quoted_in_a_reason_is_cut_short():
    result = _classify(IdatHeader(probe_count=1, chip_type="x" * 10_000, scan_software=["y" * 10_000]))
    for field in ("data_modality", "platform"):
        reason = result[field]["evidence"][0]["reason"]
        assert len(reason) < 400 and "…" in reason


@pytest.mark.parametrize(
    ("software", "said"),
    [
        pytest.param(["NextSeq Control Software"], "NextSeq Control Software", id="another scanner"),
        pytest.param([SCAN, "HiScan Control Software"], "HiScan Control Software", id="two scanners"),
        pytest.param([], "no Scan row", id="no scan row"),
    ],
)
def test_a_scanner_not_recognised_is_left_not_classified_with_what_was_read(software, said):
    result = _classify(IdatHeader(probe_count=PROBES, chip_type=CHIP, scan_software=software))
    for field in ("platform", "instrument_model"):
        assert _entry(result, field) == (None, NOT_CLASSIFIED, ["idat_scanner"])
        assert said in result[field]["evidence"][0]["reason"]
