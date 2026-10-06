"""Read an Illumina IDAT file's header by byte range (#603).

An IDAT (version 3) opens with the bytes ``IDAT``, a little-endian int64 version and an
int32 field count, then a table of ``(uint16 code, int64 offset)`` entries naming where
each field sits in the file. The per-probe intensities fill most of the file; the fields read
here are small, so a reader needs the table and a short read at each field's offset,
never the intensities. The layout is the one Bioconductor's ``illuminaio`` reads.

Three fields are read:

* 1000, the number of probes (``nSNPsRead`` in illuminaio: bead types, each read on
  several beads), the length of the per-probe arrays, an int32;
* 403, the chip type, the BeadChip's physical format (``1-95um_multi-swath_for_8x2-5M``);
* 300, the run log, one row per processing step, each five strings (time, block type,
  parameters, software, software version); a ``Scan`` row names the scanner's software.

A string is its byte length, 7 bits per byte low first (a set high bit means another
byte follows), then its bytes.
"""

import struct
from collections.abc import Callable

from .evidence import IdatHeader

MAGIC = b"IDAT"
_GZIP_MAGIC = b"\x1f\x8b"
VERSION = 3
FIELD_PROBE_COUNT = 1000
FIELD_RUN_INFO = 300
FIELD_CHIP_TYPE = 403
SCAN_BLOCK = "Scan"

# The bytes read from the start: the 16-byte preamble and a field table of up to 408
# entries. The 160 corpus files carry 19.
HEAD_LENGTH = 4096
# The bytes read at a field's offset. A field longer than this is refused, not cut short:
# the corpus's run logs are 16 rows, about 2KiB.
FIELD_WINDOW = 65536
_PREAMBLE = struct.Struct("<4sqi")
_TABLE_ENTRY = struct.Struct("<Hq")


class IdatError(ValueError):
    """The bytes are no IDAT this reader reads: gzipped, wrong magic, another version, an
    offset into the preamble or table, a negative run-log row count, or a field cut short."""


Fetch = Callable[[int, int], bytes]
"""Bytes ``start`` through ``end`` inclusive, fewer where the file ends first."""


def field_offsets(head: bytes) -> dict[int, int]:
    """Each field's offset, by its code, from a head holding the preamble and the whole table.

    Raises:
        IdatError: the bytes are gzipped, the magic is not ``IDAT``, the version is not
            3, the table runs past ``head``, or an offset points into the preamble or
            the table itself.
    """
    if len(head) < _PREAMBLE.size:
        raise IdatError(f"{len(head)} bytes, shorter than the IDAT preamble")
    if head.startswith(_GZIP_MAGIC):
        raise IdatError("gzipped: a compressed IDAT cannot be read by byte range")
    magic, version, n_fields = _PREAMBLE.unpack_from(head)
    if magic != MAGIC:
        raise IdatError(f"starts {magic!r}, not {MAGIC!r}")
    if version != VERSION:
        raise IdatError(f"IDAT version {version}; only version {VERSION} is read")
    end = _PREAMBLE.size + n_fields * _TABLE_ENTRY.size
    if n_fields < 0 or end > len(head):
        raise IdatError(f"a table of {n_fields} fields runs past the {len(head)} bytes read")
    offsets = dict(_TABLE_ENTRY.iter_unpack(head[_PREAMBLE.size : end]))
    if inside := {code: o for code, o in offsets.items() if o < end}:
        raise IdatError(f"field offsets {inside} point inside the {end}-byte preamble and table")
    return offsets


def read_header(fetch: Fetch) -> IdatHeader:
    """The probe count, chip type and scan software of the IDAT that ``fetch`` reads.

    A field the table does not list is ``None`` (the run log: no scan software). The probe
    count is read from the head where the head holds it; the text fields from one window
    spanning both where they lie within ``FIELD_WINDOW`` of each other.

    Raises:
        IdatError: as ``field_offsets``, a negative run-log row count, or a field runs
            past its window.
    """
    head = fetch(0, HEAD_LENGTH - 1)
    offsets = field_offsets(head)
    windows = _Windows(fetch, head)
    # The two text fields sit together near the file's end, in either order. One window
    # from the lower to ``FIELD_WINDOW`` past the higher serves both, where they are that
    # close; ``at`` reads its own window for a field it does not cover.
    text_offsets = [o for code in (FIELD_CHIP_TYPE, FIELD_RUN_INFO) if (o := offsets.get(code)) is not None]
    if text_offsets and (span := max(text_offsets) - min(text_offsets)) <= FIELD_WINDOW:
        windows.at(min(text_offsets), need=span + FIELD_WINDOW)

    probe_count = None
    if (offset := offsets.get(FIELD_PROBE_COUNT)) is not None:
        buf, pos = windows.at(offset, need=4)
        probe_count = _int32(buf, pos)

    chip_type = None
    if (offset := offsets.get(FIELD_CHIP_TYPE)) is not None:
        chip_type, _ = _string(*windows.at(offset))

    scan_software: list[str] = []
    if (offset := offsets.get(FIELD_RUN_INFO)) is not None:
        buf, pos = windows.at(offset)
        rows = _int32(buf, pos)
        if rows < 0:
            raise IdatError(f"a run log of {rows} rows")
        pos += 4
        for _ in range(rows):
            row = []
            for _ in range(5):
                text, pos = _string(buf, pos)
                row.append(text)
            if row[1] == SCAN_BLOCK:
                scan_software.append(row[3])
    return IdatHeader(probe_count=probe_count, chip_type=chip_type, scan_software=scan_software)


class _Windows:
    """The byte windows read so far, each starting at the offset it was read for."""

    def __init__(self, fetch: Fetch, head: bytes):
        self._fetch = fetch
        self._held = [(0, head, len(head) < HEAD_LENGTH)]

    def at(self, offset: int, need: int | None = None) -> tuple[bytes, int]:
        """A window holding ``offset`` and the ``need`` bytes from it (or to the file's end), and where ``offset`` sits in it.

        A field of unknown length asks for the whole ``FIELD_WINDOW`` (the default); an
        int32 asks for 4. Where no window held covers it, one is read, ``need`` bytes long.
        """
        need = FIELD_WINDOW if need is None else need
        for start, data, at_eof in self._held:
            end = start + len(data)
            if start <= offset and (offset + need <= end or (at_eof and offset < end)):
                return data, offset - start
        data = self._fetch(offset, offset + need - 1)
        self._held.append((offset, data, len(data) < need))
        return data, 0


def _int32(buf: bytes, pos: int) -> int:
    if pos + 4 > len(buf):
        raise IdatError("an int32 field runs past the bytes read")
    return struct.unpack_from("<i", buf, pos)[0]


def _string(buf: bytes, pos: int) -> tuple[str, int]:
    """The string at ``pos`` and the position after it."""
    length = shift = 0
    while True:
        if pos >= len(buf):
            raise IdatError("a string's length runs past the bytes read")
        byte = buf[pos]
        pos += 1
        length |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            break
    if pos + length > len(buf):
        raise IdatError(f"a {length}-byte string runs past the bytes read")
    raw = buf[pos : pos + length]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return text, pos + length
