"""Binary phase-2 packet and payload codecs.

Packet layout::

    [length:4][opcode:2][user_id:2][payload:length-4]

``length`` counts every byte after the length field. All integers use network
byte order. Client and server import this module to share one contract.
"""

import struct
from enum import IntEnum
from typing import Iterable

from common import MAX_FRAME_SIZE, read_frame


class Opcode(IntEnum):
    LOGIN = 0x01
    LOGOUT = 0x02
    FILE_LIST = 0x10
    FILE_LIST_RESP = 0x11
    FILE_UPLOAD = 0x12
    FILE_DOWNLOAD = 0x13
    FILE_CHUNK = 0x14
    FILE_DELETE = 0x15
    ACK = 0x20
    ERROR = 0xFF


LOGIN = Opcode.LOGIN
LOGOUT = Opcode.LOGOUT
FILE_LIST = Opcode.FILE_LIST
FILE_LIST_RESP = Opcode.FILE_LIST_RESP
FILE_UPLOAD = Opcode.FILE_UPLOAD
FILE_DOWNLOAD = Opcode.FILE_DOWNLOAD
FILE_CHUNK = Opcode.FILE_CHUNK
FILE_DELETE = Opcode.FILE_DELETE
ACK = Opcode.ACK
ERROR = Opcode.ERROR

HEADER_SIZE = 8
BODY_HEADER_SIZE = 4


def _unsigned(value: int, bits: int, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field} must be an integer")
    if not 0 <= value < (1 << bits):
        raise ValueError(f"{field} must fit in {bits} unsigned bits")
    return value


def _bytes(payload: bytes, field: str = "payload") -> bytes:
    try:
        return bytes(payload)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field} must be bytes-like") from exc


def pack_packet(opcode: int, user_id: int, payload: bytes = b"") -> bytes:
    """Pack one complete phase-2 packet, including its 4-byte length."""
    opcode = _unsigned(opcode, 16, "opcode")
    user_id = _unsigned(user_id, 16, "user_id")
    payload = _bytes(payload)
    body = struct.pack("!HH", opcode, user_id) + payload
    if len(body) > MAX_FRAME_SIZE:
        raise ValueError(f"Packet body exceeds {MAX_FRAME_SIZE} bytes")
    return struct.pack("!I", len(body)) + body


def unpack_body(body: bytes) -> tuple[int, int, bytes]:
    """Unpack the body returned by ``read_frame(sock, prefix=4)``."""
    body = _bytes(body, "body")
    if len(body) < BODY_HEADER_SIZE:
        raise ValueError("Packet body is shorter than opcode and user_id")
    opcode, user_id = struct.unpack("!HH", body[:BODY_HEADER_SIZE])
    return opcode, user_id, body[BODY_HEADER_SIZE:]


def unpack_packet(packet: bytes) -> tuple[int, int, bytes]:
    """Validate and unpack one complete packet held in memory."""
    packet = _bytes(packet, "packet")
    if len(packet) < HEADER_SIZE:
        raise ValueError("Packet is shorter than its header")
    (length,) = struct.unpack("!I", packet[:4])
    if length != len(packet) - 4:
        raise ValueError(
            f"Packet declares {length} body bytes, got {len(packet) - 4}"
        )
    return unpack_body(packet[4:])


def read_packet(sock) -> tuple[int, int, bytes]:
    """Read and unpack one packet from a connected socket."""
    return unpack_body(read_frame(sock, prefix=4))


def pack_text(value: str) -> bytes:
    """Encode a UTF-8 string with a 2-byte byte-length prefix."""
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    encoded = value.encode("utf-8")
    _unsigned(len(encoded), 16, "encoded string length")
    return struct.pack("!H", len(encoded)) + encoded


def unpack_text(payload: bytes, offset: int = 0) -> tuple[str, int]:
    """Decode one length-prefixed UTF-8 string and return its next offset."""
    payload = _bytes(payload)
    if offset < 0 or offset + 2 > len(payload):
        raise ValueError("Missing string length")
    (length,) = struct.unpack("!H", payload[offset : offset + 2])
    start = offset + 2
    end = start + length
    if end > len(payload):
        raise ValueError("Truncated string")
    try:
        return payload[start:end].decode("utf-8"), end
    except UnicodeDecodeError as exc:
        raise ValueError("String is not valid UTF-8") from exc


def _require_end(payload: bytes, offset: int) -> None:
    if offset != len(payload):
        raise ValueError(f"Unexpected {len(payload) - offset} trailing bytes")


def pack_filename(filename: str) -> bytes:
    if not filename:
        raise ValueError("filename must not be empty")
    return pack_text(filename)


def unpack_filename(payload: bytes) -> str:
    filename, offset = unpack_text(payload)
    _require_end(payload, offset)
    if not filename:
        raise ValueError("filename must not be empty")
    return filename


def _optional_sha256(sha256: bytes) -> bytes:
    """Validate an optional raw SHA-256 digest."""
    sha256 = _bytes(sha256, "sha256")
    if sha256 and len(sha256) != 32:
        raise ValueError("sha256 must be exactly 32 bytes")
    return sha256


def pack_upload(
    filename: str,
    total_size: int,
    offset: int = 0,
    sha256: bytes = b"",
) -> bytes:
    """Pack FILE_UPLOAD metadata, optionally including the full-file hash."""
    total_size = _unsigned(total_size, 64, "total_size")
    offset = _unsigned(offset, 64, "offset")
    if offset > total_size:
        raise ValueError("offset must not exceed total_size")
    return (
        pack_filename(filename)
        + struct.pack("!QQ", total_size, offset)
        + _optional_sha256(sha256)
    )


def unpack_upload(payload: bytes) -> tuple[str, int, int, bytes]:
    """Unpack FILE_UPLOAD metadata and return its optional raw digest."""
    payload = _bytes(payload)
    filename, offset = unpack_text(payload)
    if not filename:
        raise ValueError("filename must not be empty")
    remaining = len(payload) - offset
    if remaining not in (16, 48):
        raise ValueError(
            "Upload payload must contain total_size, offset, and optional SHA-256"
        )
    total_size, next_offset = struct.unpack("!QQ", payload[offset : offset + 16])
    if next_offset > total_size:
        raise ValueError("offset must not exceed total_size")
    sha256 = payload[offset + 16 :]
    return filename, total_size, next_offset, sha256


def pack_chunk(offset: int, data: bytes) -> bytes:
    offset = _unsigned(offset, 64, "offset")
    return struct.pack("!Q", offset) + _bytes(data, "data")


def unpack_chunk(payload: bytes) -> tuple[int, bytes]:
    payload = _bytes(payload)
    if len(payload) < 8:
        raise ValueError("Chunk payload is shorter than its offset")
    (offset,) = struct.unpack("!Q", payload[:8])
    return offset, payload[8:]


def pack_ack(
    acked_opcode: int,
    next_offset: int,
    sha256: bytes = b"",
) -> bytes:
    """Pack an ACK with an optional full-file SHA-256 digest."""
    acked_opcode = _unsigned(acked_opcode, 16, "acked_opcode")
    next_offset = _unsigned(next_offset, 64, "next_offset")
    return (
        struct.pack("!HQ", acked_opcode, next_offset)
        + _optional_sha256(sha256)
    )


def unpack_ack(payload: bytes) -> tuple[int, int, bytes]:
    """Unpack an ACK and return ``(opcode, next_offset, sha256)``."""
    payload = _bytes(payload)
    if len(payload) not in (10, 42):
        raise ValueError("ACK payload must be 10 bytes, plus optional SHA-256")
    acked_opcode, next_offset = struct.unpack("!HQ", payload[:10])
    return acked_opcode, next_offset, payload[10:]


def pack_error(code: int, message: str) -> bytes:
    """Pack an ERROR payload as code, UTF-8 byte length, and message."""
    code = _unsigned(code, 16, "error code")
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    encoded = message.encode("utf-8")
    _unsigned(len(encoded), 16, "error message length")
    return struct.pack("!HH", code, len(encoded)) + encoded


def pack_file_list_response(entries: Iterable[tuple[str, int]]) -> bytes:
    """Pack ``[(filename, size), ...]`` for FILE_LIST_RESP.

    Layout: ``count:4`` followed by ``name`` (pack_text format) and ``size:8``
    for each entry.
    """
    encoded_entries = []
    for filename, size in entries:
        encoded_entries.append(
            pack_filename(filename)
            + struct.pack("!Q", _unsigned(size, 64, "file size"))
        )
    _unsigned(len(encoded_entries), 32, "entry count")
    return struct.pack("!I", len(encoded_entries)) + b"".join(encoded_entries)


def unpack_file_list_response(payload: bytes) -> list[tuple[str, int]]:
    payload = _bytes(payload)
    if len(payload) < 4:
        raise ValueError("File-list response is missing its count")
    (count,) = struct.unpack("!I", payload[:4])
    offset = 4
    entries = []
    for _ in range(count):
        filename, offset = unpack_text(payload, offset)
        if not filename:
            raise ValueError("filename must not be empty")
        if offset + 8 > len(payload):
            raise ValueError("File-list entry is missing its size")
        (size,) = struct.unpack("!Q", payload[offset : offset + 8])
        offset += 8
        entries.append((filename, size))
    _require_end(payload, offset)
    return entries


__all__ = [
    "ACK",
    "ERROR",
    "FILE_CHUNK",
    "FILE_DELETE",
    "FILE_DOWNLOAD",
    "FILE_LIST",
    "FILE_LIST_RESP",
    "FILE_UPLOAD",
    "LOGIN",
    "LOGOUT",
    "Opcode",
    "pack_ack",
    "pack_chunk",
    "pack_error",
    "pack_file_list_response",
    "pack_filename",
    "pack_packet",
    "pack_text",
    "pack_upload",
    "read_packet",
    "unpack_ack",
    "unpack_body",
    "unpack_chunk",
    "unpack_file_list_response",
    "unpack_filename",
    "unpack_packet",
    "unpack_text",
    "unpack_upload",
]
