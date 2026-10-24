"""Read the sample and the device a nanopore FAST5 file names, from its first bytes (#605, #747).

A FAST5 is an HDF5 file MinKNOW writes, one sequencing run's reads to a file, each read's
``tracking_id`` group holding the run's ``sample_id`` and ``device_type``. In the one NIA_CARD
file read whole the reads share one such group, so each attribute is stored once, the
``sample_id`` about 5 KB in (#605); the ``device_type`` was within the first 64 KiB of each of
12 NIA_CARD heads probed (#747). Walking the file to it read about 7.5 MB per file (h5py and pyfive, measured on
#605; pyfive spends it loading the root group's index of the reads' UUID-named groups), so
this reader finds each attribute *named* ``sample_id`` or ``device_type`` in the first
:data:`HEAD_LENGTH` bytes and parses its message whole from the header before the name. It
does not prove the attribute sits in a ``tracking_id`` group.

The layout read is these files': a version 1 object header message of type 0x000C, holding a
version 1 attribute message (name padded to 8), a version 1 fixed-length string datatype, a
version 1 scalar dataspace and the string. The name with no such message header of its length
before it (one in a version 2 object header included) is skipped, as is a message running past
the bytes read; one laid out otherwise is refused. A ``device_type`` refused costs only the
device: :func:`read_header` keeps the samples, and records the device as unread (#747).
"""

import struct

from .evidence import Fast5Header
from .idat import Fetch

SIGNATURE = b"\x89HDF\r\n\x1a\n"
HEAD_LENGTH = 65536
SAMPLE_ID = "sample_id"
DEVICE_TYPE = "device_type"

# The version 1 object header message prefix: type, body length, flags, 3 reserved bytes.
_MESSAGE_PREFIX = struct.Struct("<HHB3x")
ATTRIBUTE_MESSAGE = 0x000C
# A version 1 attribute message's header: version, reserved, name, datatype and dataspace lengths.
_ATTRIBUTE_HEADER = struct.Struct("<BxHHH")
_DATATYPE = struct.Struct("<B3sI")  # class and version in one byte, three bytes of class bits, the size
STRING_CLASS = 3
NULL_TERM, NULL_PAD, SPACE_PAD = 0, 1, 2  # a string datatype's padding types
_DATASPACE = struct.Struct("<BBB5x")  # a version 1 dataspace's first 8 bytes: version, rank, flags


class Fast5Error(ValueError):
    """The bytes are no FAST5 this reader reads: no HDF5 signature, or a ``sample_id`` or ``device_type`` attribute message laid out otherwise than the one it parses."""


def read_header(fetch: Fetch) -> Fast5Header:
    """The ``sample_id`` and ``device_type`` values in the first :data:`HEAD_LENGTH` bytes ``fetch`` reads.

    ``device_types`` is None where a ``device_type`` attribute is laid out otherwise than the
    one this module parses, so a file whose device cannot be read keeps its samples.

    Raises:
        Fast5Error: as :func:`attribute_values` does for ``sample_id``.
    """
    head = fetch(0, HEAD_LENGTH - 1)
    samples = attribute_values(head, SAMPLE_ID)
    try:
        devices: list[str] | None = attribute_values(head, DEVICE_TYPE)
    except Fast5Error:
        devices = None
    return Fast5Header(sample_ids=samples, device_types=devices)


def attribute_values(head: bytes, name: str) -> list[str]:
    """Each distinct value of an attribute named ``name`` in ``head``, in the order found.

    Raises:
        Fast5Error: ``head`` does not start with the HDF5 signature (a gzipped file
            included), or an attribute message named ``name`` is laid out otherwise
            than the one the module docstring describes.
    """
    if not head.startswith(SIGNATURE):
        raise Fast5Error(f"starts {head[:8]!r}, not the HDF5 signature")
    encoded = name.encode() + b"\x00"
    found: dict[str, None] = {}
    at = head.find(encoded)
    while at >= 0:
        value = _attribute_value(head, at, name)
        if value is not None:
            found[value] = None
        at = head.find(encoded, at + 1)
    return list(found)


def _padded(length: int) -> int:
    return (length + 7) // 8 * 8


def _attribute_value(head: bytes, at: int, name: str) -> str | None:
    """The string value of the attribute ``name`` whose name starts at ``at``; None where no attribute message header precedes it, or the message it declares runs past ``head``."""
    start = at - _ATTRIBUTE_HEADER.size - _MESSAGE_PREFIX.size
    if start < 0:
        return None
    kind, body_length, _flags = _MESSAGE_PREFIX.unpack_from(head, start)
    version, name_length, datatype_length, dataspace_length = _ATTRIBUTE_HEADER.unpack_from(
        head, start + _MESSAGE_PREFIX.size
    )
    if kind != ATTRIBUTE_MESSAGE or name_length != len(name) + 1:
        return None
    message_end = start + _MESSAGE_PREFIX.size + body_length
    if message_end > len(head):
        return None
    if version != 1:
        raise Fast5Error(f"a {name} attribute message of version {version}; only version 1 is read")
    datatype = at + _padded(name_length)
    dataspace = datatype + _padded(datatype_length)
    data = dataspace + _padded(dataspace_length)
    if datatype_length < _DATATYPE.size or dataspace_length < _DATASPACE.size or data > message_end:
        raise Fast5Error(f"a {name} attribute message whose datatype or dataspace is cut short")
    class_version, bits, size = _DATATYPE.unpack_from(head, datatype)
    if class_version & 0x0F != STRING_CLASS or class_version >> 4 != 1:
        raise Fast5Error(
            f"a {name} attribute of datatype class {class_version & 0x0F} version {class_version >> 4}; only a version 1 string is read"
        )
    space_version, rank, _ = _DATASPACE.unpack_from(head, dataspace)
    if space_version != 1 or rank != 0:
        raise Fast5Error(
            f"a {name} attribute of dataspace version {space_version}, rank {rank}; only a version 1 scalar is read"
        )
    end = data + size
    if end > message_end:
        raise Fast5Error(f"a {name} attribute's {size}-byte value runs past its message")
    raw, padding = head[data:end], bits[0] & 0x0F
    if padding == NULL_TERM:
        raw = raw.split(b"\x00", 1)[0]
    elif padding == NULL_PAD:
        raw = raw.rstrip(b"\x00")
    elif padding == SPACE_PAD:
        raw = raw.rstrip(b" ")
    else:
        raise Fast5Error(f"a {name} string of padding type {padding}; only 0 to 2 are read")
    return raw.decode("utf-8", "replace")
