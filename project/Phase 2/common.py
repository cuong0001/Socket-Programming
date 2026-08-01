"""Shared framing helpers.

Phase 1 uses an 8-byte big-endian length prefix. Phase 2 reuses the same
framing logic with a 4-byte prefix.
"""

import socket
import struct


MAX_FRAME_SIZE = 1 << 20
_PREFIX_FORMATS = {4: "!I", 8: "!Q"}


def _prefix_format(prefix: int) -> str:
    try:
        return _PREFIX_FORMATS[prefix]
    except KeyError as exc:
        raise ValueError("prefix must be 4 or 8 bytes") from exc


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly ``n`` bytes or raise if the connection closes."""
    if n < 0:
        raise ValueError("n must not be negative")

    data = bytearray()
    while len(data) < n:
        part = sock.recv(n - len(data))
        if not part:
            raise ConnectionError(
                f"Connection closed after {len(data)}/{n} bytes"
            )
        data.extend(part)
    return bytes(data)


def read_frame(
    sock: socket.socket,
    prefix: int = 8,
    max_size: int = MAX_FRAME_SIZE,
) -> bytes:
    """Receive a frame with a 4-byte or 8-byte big-endian length prefix."""
    if max_size < 0:
        raise ValueError("max_size must not be negative")

    (length,) = struct.unpack(
        _prefix_format(prefix), recv_exact(sock, prefix)
    )
    if length > max_size:
        raise ValueError(f"Frame declares {length} bytes; limit is {max_size}")
    return recv_exact(sock, length)


def send_frame(
    sock: socket.socket,
    payload: bytes,
    prefix: int = 8,
    max_size: int = MAX_FRAME_SIZE,
) -> None:
    """Send a frame with a 4-byte or 8-byte big-endian length prefix."""
    payload = bytes(payload)
    if len(payload) > max_size:
        raise ValueError(
            f"Frame contains {len(payload)} bytes; limit is {max_size}"
        )
    sock.sendall(struct.pack(_prefix_format(prefix), len(payload)) + payload)
