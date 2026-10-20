"""Read the sample a nanopore FAST5 file names, from its first bytes (#605).

A FAST5 is an HDF5 file MinKNOW writes, one sequencing run's reads to a file, each read's
``tracking_id`` group holding the run's ``sample_id``. In the one NIA_CARD file read whole the
reads share one such group, so the attribute is stored once, about 5 KB in (#605). Walking
the file to it read about 7.5 MB per file (h5py and pyfive, measured on #605; pyfive spends
it loading the root group's index of the reads' UUID-named groups), so this reader finds each
attribute *named* ``sample_id`` in the first :data:`HEAD_LENGTH` bytes and parses its message
whole from the header before the name. It does not prove the attribute sits in a
``tracking_id`` group.

The layout read is these files': a version 1 object header message of type 0x000C, holding a
version 1 attribute message (name padded to 8), a version 1 fixed-length string datatype, a
version 1 scalar dataspace and the string. The name with no such message header of its length
before it (one in a version 2 object header included) is skipped, as is a message running past
the bytes read; one laid out otherwise is refused.
"""

import struct

from .evidence import Fast5Header
from .idat import Fetch

SIGNATURE = b"\x89HDF\r\n\x1a\n"
HEAD_LENGTH = 65536
SAMPLE_ID = "sample_id"
_NAME = SAMPLE_ID.encode() + b"\x00"

# The version 1 object header message prefix: type, body length, flags, 3 reserved bytes.
_MESSAGE_PREFIX = struct.Struct("<HHB3x")
ATTRIBUTE_MESSAGE = 0x000C
# A version 1 attribute message's header: version, reserved, name, datatype and dataspace lengths.
_ATTRIBUTE_HEADER = struct.Struct("<BxHHH")
_DATATYPE = struct.Struct("<B3sI")  # class and version in one byte, three bytes of class bits, the size
STRING_CLASS = 3
SPACE_PAD = 2  # a string datatype padding type; the others end at a NUL
_DATASPACE = struct.Struct("<BBB5x")  # a version 1 dataspace's first 8 bytes: version, rank, flags


class Fast5Error(ValueError):
    """The bytes are no FAST5 this reader reads: no HDF5 signature, or a ``sample_id`` attribute message laid out otherwise than the one it parses."""


def read_header(fetch: Fetch) -> Fast5Header:
    """The ``sample_id`` values in the first :data:`HEAD_LENGTH` bytes ``fetch`` reads; raises as :func:`sample_ids`."""
    return Fast5Header(sample_ids=sample_ids(fetch(0, HEAD_LENGTH - 1)))


def sample_ids(head: bytes) -> list[str]:
    """Each distinct ``sample_id`` attribute value in ``head``, in the order found.

    Raises:
        Fast5Error: ``head`` does not start with the HDF5 signature (a gzipped file
            included), or an attribute message named ``sample_id`` is laid out otherwise
            than the one the module docstring describes.
    """
    if not head.startswith(SIGNATURE):
        raise Fast5Error(f"starts {head[:8]!r}, not the HDF5 signature")
    found: dict[str, None] = {}
    at = head.find(_NAME)
    while at >= 0:
        value = _attribute_value(head, at)
        if value is not None:
            found[value] = None
        at = head.find(_NAME, at + 1)
    return list(found)


def _padded(length: int) -> int:
    return (length + 7) // 8 * 8


def _attribute_value(head: bytes, at: int) -> str | None:
    """The string value of the attribute whose name starts at ``at``; None where no attribute message header precedes it, or it runs past ``head``."""
    start = at - _ATTRIBUTE_HEADER.size - _MESSAGE_PREFIX.size
    if start < 0:
        return None
    kind, body_length, _flags = _MESSAGE_PREFIX.unpack_from(head, start)
    version, name_length, datatype_length, dataspace_length = _ATTRIBUTE_HEADER.unpack_from(
        head, start + _MESSAGE_PREFIX.size
    )
    if kind != ATTRIBUTE_MESSAGE or name_length != len(_NAME):
        return None
    if version != 1:
        raise Fast5Error(f"a {SAMPLE_ID} attribute message of version {version}; only version 1 is read")
    datatype = at + _padded(name_length)
    dataspace = datatype + _padded(datatype_length)
    data = dataspace + _padded(dataspace_length)
    if datatype_length < _DATATYPE.size or dataspace_length < _DATASPACE.size:
        raise Fast5Error(f"a {SAMPLE_ID} attribute message whose datatype or dataspace is cut short")
    if data > len(head):
        return None
    class_version, bits, size = _DATATYPE.unpack_from(head, datatype)
    if class_version & 0x0F != STRING_CLASS or class_version >> 4 != 1:
        raise Fast5Error(
            f"a {SAMPLE_ID} attribute of datatype class {class_version & 0x0F} version {class_version >> 4}; only a version 1 string is read"
        )
    space_version, rank, _ = _DATASPACE.unpack_from(head, dataspace)
    if space_version != 1 or rank != 0:
        raise Fast5Error(
            f"a {SAMPLE_ID} attribute of dataspace version {space_version}, rank {rank}; only a version 1 scalar is read"
        )
    end = data + size
    if body_length < end - (start + _MESSAGE_PREFIX.size):
        raise Fast5Error(f"a {SAMPLE_ID} attribute's {size}-byte value runs past its message")
    if end > len(head):
        return None
    raw = head[data:end]
    raw = raw.rstrip(b" ") if bits[0] & 0x0F == SPACE_PAD else raw.split(b"\x00", 1)[0]
    return raw.decode("utf-8", "replace")
