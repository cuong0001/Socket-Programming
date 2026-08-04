import socket
import struct
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from protocol import (
    ACK,
    ERROR,
    FILE_CHUNK,
    FILE_DELETE,
    FILE_DOWNLOAD,
    FILE_LIST,
    FILE_LIST_RESP,
    FILE_UPLOAD,
    LOGIN,
    LOGOUT,
    pack_ack,
    pack_chunk,
    pack_download,
    pack_error,
    pack_file_list_response,
    pack_filename,
    pack_packet,
    pack_upload,
    read_packet,
    unpack_ack,
    unpack_chunk,
    unpack_download,
    unpack_error,
    unpack_file_list_response,
    unpack_filename,
    unpack_packet,
    unpack_upload,
)


class FragmentedSocket:
    def __init__(self, data: bytes) -> None:
        self.data = bytearray(data)

    def recv(self, size: int) -> bytes:
        if not self.data:
            return b""
        result = bytes(self.data[:1])
        del self.data[:1]
        return result


class OpcodeTests(unittest.TestCase):
    def test_opcode_table_matches_the_specification(self) -> None:
        self.assertEqual(
            [
                int(LOGIN),
                int(LOGOUT),
                int(FILE_LIST),
                int(FILE_LIST_RESP),
                int(FILE_UPLOAD),
                int(FILE_DOWNLOAD),
                int(FILE_CHUNK),
                int(FILE_DELETE),
                int(ACK),
                int(ERROR),
            ],
            [0x01, 0x02, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x20, 0xFF],
        )


class PacketTests(unittest.TestCase):
    def test_upload_hex_dump_matches_the_plan_byte_for_byte(self) -> None:
        digest = b"\x11" * 32
        frame = pack_packet(
            FILE_UPLOAD,
            0x0007,
            pack_upload("data.bin", 10_000_000, 0, digest),
        )

        self.assertEqual(len(frame), 66)
        self.assertEqual(
            frame.hex(" ").upper(),
            "00 00 00 3E 00 12 00 07 "
            "00 08 64 61 74 61 2E 62 69 6E "
            "00 00 00 00 00 98 96 80 "
            "00 00 00 00 00 00 00 00 "
            + " ".join(["11"] * 32),
        )
        self.assertEqual(
            unpack_packet(frame),
            (
                int(FILE_UPLOAD),
                7,
                pack_upload("data.bin", 10_000_000, 0, digest),
            ),
        )

    def test_read_packet_handles_a_fragmented_stream(self) -> None:
        packet = pack_packet(FILE_CHUNK, 9, pack_chunk(4096, b"a\x00b"))
        self.assertEqual(
            read_packet(FragmentedSocket(packet)),
            (int(FILE_CHUNK), 9, pack_chunk(4096, b"a\x00b")),
        )

    def test_three_packets_remain_separate_on_one_socket(self) -> None:
        sender, receiver = socket.socketpair()
        packets = [
            pack_packet(LOGIN, 0, pack_filename("alice")),
            pack_packet(FILE_LIST, 1),
            pack_packet(LOGOUT, 1),
        ]
        try:
            sender.sendall(b"".join(packets))
            actual = [read_packet(receiver) for _ in packets]
        finally:
            sender.close()
            receiver.close()

        self.assertEqual(
            actual,
            [
                (int(LOGIN), 0, pack_filename("alice")),
                (int(FILE_LIST), 1, b""),
                (int(LOGOUT), 1, b""),
            ],
        )

    def test_unpack_rejects_wrong_length(self) -> None:
        packet = pack_packet(FILE_LIST, 3)
        with self.assertRaises(ValueError):
            unpack_packet(struct.pack("!I", 99) + packet[4:])


class PayloadTests(unittest.TestCase):
    def test_upload_round_trip_supports_utf8_filename(self) -> None:
        digest = bytes(range(32))
        payload = pack_upload("unicode-\u2603.bin", 12_345, 4096, digest)
        self.assertEqual(
            unpack_upload(payload),
            ("unicode-\u2603.bin", 12_345, 4096, digest),
        )

        legacy_payload = pack_upload("empty.bin", 0)
        self.assertEqual(
            unpack_upload(legacy_payload),
            ("empty.bin", 0, 0, b""),
        )

    def test_chunk_preserves_binary_data(self) -> None:
        payload = pack_chunk(8192, bytes(range(256)) + b"\x00\n")
        self.assertEqual(
            unpack_chunk(payload), (8192, bytes(range(256)) + b"\x00\n")
        )

    def test_ack_round_trip(self) -> None:
        digest = b"\xA5" * 32
        self.assertEqual(
            unpack_ack(pack_ack(FILE_UPLOAD, 10_000_000, digest)),
            (int(FILE_UPLOAD), 10_000_000, digest),
        )
        self.assertEqual(
            unpack_ack(pack_ack(LOGIN, 1)),
            (int(LOGIN), 1, b""),
        )

    def test_error_payload_uses_utf8_byte_length(self) -> None:
        payload = pack_error(0x0101, "invalid Unicode message \u26a0")
        code, length = struct.unpack("!HH", payload[:4])
        self.assertEqual(code, 0x0101)
        self.assertEqual(
            length, len("invalid Unicode message \u26a0".encode("utf-8"))
        )
        self.assertEqual(
            payload[4:].decode("utf-8"), "invalid Unicode message \u26a0"
        )

    def test_error_round_trip(self) -> None:
        self.assertEqual(
            unpack_error(pack_error(0x0101, "invalid Unicode message \u26a0")),
            (0x0101, "invalid Unicode message \u26a0"),
        )

    def test_download_round_trip_supports_resume_and_utf8(self) -> None:
        payload = pack_download("unicode-\u2603.bin", 4096)
        self.assertEqual(
            payload,
            pack_filename("unicode-\u2603.bin") + struct.pack("!Q", 4096),
        )
        self.assertEqual(
            unpack_download(payload),
            ("unicode-\u2603.bin", 4096),
        )
        self.assertEqual(
            unpack_download(pack_download("fresh.bin")),
            ("fresh.bin", 0),
        )

    def test_download_and_delete_use_unambiguous_filename_payload(self) -> None:
        payload = pack_filename("report final.bin")
        self.assertEqual(unpack_filename(payload), "report final.bin")

    def test_file_list_response_round_trip(self) -> None:
        entries = [("empty.bin", 0), ("unicode-\u2603.bin", 4097)]
        self.assertEqual(
            unpack_file_list_response(pack_file_list_response(entries)), entries
        )

    def test_malformed_payloads_are_rejected(self) -> None:
        malformed = [
            lambda: unpack_upload(b"\x00\x08short"),
            lambda: unpack_ack(b"\x00" * 9),
            lambda: unpack_chunk(b"\x00" * 7),
            lambda: unpack_download(pack_filename("data.bin") + b"\x00" * 7),
            lambda: unpack_error(b"\x00\x01\x00\x02x"),
            lambda: unpack_error(b"\x00\x01\x00\x01xy"),
            lambda: unpack_filename(b"\x00\x05abc"),
            lambda: unpack_file_list_response(b"\x00\x00\x00\x01"),
        ]
        for operation in malformed:
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    operation()

    def test_upload_offset_cannot_exceed_total_size(self) -> None:
        with self.assertRaises(ValueError):
            pack_upload("data.bin", 10, 11)

    def test_sha256_fields_reject_wrong_lengths(self) -> None:
        for digest in (b"x", b"x" * 31, b"x" * 33):
            with self.subTest(length=len(digest)):
                with self.assertRaises(ValueError):
                    pack_upload("data.bin", 10, sha256=digest)
                with self.assertRaises(ValueError):
                    pack_ack(FILE_UPLOAD, 10, digest)


if __name__ == "__main__":
    unittest.main()
