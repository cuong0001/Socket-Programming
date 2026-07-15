import socket
import struct


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """Nhận đúng n byte từ socket."""
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
    """Nhận một frame gồm 8 byte độ dài và phần nội dung."""
    (length,) = struct.unpack("!Q", recv_exact(sock, 8))

    if length > 1 << 20:
        raise ValueError(f"Frame khai báo {length} byte, từ chối")

    return recv_exact(sock, length)


def send_frame(sock: socket.socket, payload: bytes) -> None:
    """Gửi một frame gồm 8 byte độ dài và phần nội dung."""
    sock.sendall(struct.pack("!Q", len(payload)) + payload)