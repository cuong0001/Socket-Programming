"""Phase 1 protocol contract.

Each frame = 8-byte big-endian payload length + payload.
UTF-8 commands: LIST | UPLOAD <size> <filename> | DOWNLOAD <filename>.
Responses: OK ... | ACK sha256 <digest> | ERR <message>.
File data is sent in frames using chunks of 4096 bytes.
"""

import socket
import struct


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly n bytes from the socket."""
    data = bytearray()

    while len(data) < n:
        part = sock.recv(n - len(data))

        if not part:
            raise ConnectionError(
                f"Mất kết nối sau khi nhận {len(data)}/{n} byte"
            )

        data.extend(part)

    return bytes(data)


def read_frame(sock: socket.socket) -> bytes:
    """Receive a frame containing an 8-byte length and its payload."""
    (length,) = struct.unpack("!Q", recv_exact(sock, 8))

    if length > 1 << 20:
        raise ValueError(f"Frame khai báo {length} byte, từ chối")

    return recv_exact(sock, length)


def send_frame(sock: socket.socket, payload: bytes) -> None:
    """Send a frame containing an 8-byte length and its payload."""
    sock.sendall(struct.pack("!Q", len(payload)) + payload)
