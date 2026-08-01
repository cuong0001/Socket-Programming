import socket
import struct
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from common import read_frame, recv_exact, send_frame


class FragmentedSocket:
    """Fake socket that returns at most one byte per recv call."""

    def __init__(self, data: bytes) -> None:
        self.data = bytearray(data)

    def recv(self, size: int) -> bytes:
        if not self.data:
            return b""
        amount = min(size, 1)
        result = bytes(self.data[:amount])
        del self.data[:amount]
        return result


class RecvExactTests(unittest.TestCase):
    def test_reassembles_one_byte_at_a_time(self) -> None:
        sock = FragmentedSocket(b"abcdef")
        self.assertEqual(recv_exact(sock, 6), b"abcdef")

    def test_raises_when_connection_closes_early(self) -> None:
        sock = FragmentedSocket(b"abc")
        with self.assertRaises(ConnectionError):
            recv_exact(sock, 6)


class FrameTests(unittest.TestCase):
    def test_three_consecutive_frames_are_preserved(self) -> None:
        sender, receiver = socket.socketpair()
        payloads = [b"hello", b"a\x00b\nc", b""]

        try:
            for payload in payloads:
                send_frame(sender, payload)

            actual = [read_frame(receiver) for _ in payloads]
            self.assertEqual(actual, payloads)
        finally:
            sender.close()
            receiver.close()

    def test_rejects_frame_larger_than_one_mebibyte(self) -> None:
        sender, receiver = socket.socketpair()

        try:
            sender.sendall(struct.pack("!Q", (1 << 20) + 1))
            with self.assertRaises(ValueError):
                read_frame(receiver)
        finally:
            sender.close()
            receiver.close()


if __name__ == "__main__":
    unittest.main()
