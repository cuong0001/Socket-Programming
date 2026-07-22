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
    pack_file_list_response,
    pack_filename,
    pack_packet,
    pack_upload,
    read_packet,
    unpack_ack,
    unpack_chunk,
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
        frame = pack_packet(
            FILE_UPLOAD,
            0x0007,
            pack_upload("data.bin", 10_000_000, 0),
        )

        self.assertEqual(len(frame), 34)
        self.assertEqual(
            frame.hex(" ").upper(),
            "00 00 00 1E 00 12 00 07 "
            "00 08 64 61 74 61 2E 62 69 6E "
            "00 00 00 00 00 98 96 80 "
            "00 00 00 00 00 00 00 00",
        )
        self.assertEqual(
            unpack_packet(frame),
            (int(FILE_UPLOAD), 7, pack_upload("data.bin", 10_000_000, 0)),
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
        payload = pack_upload("dữ liệu.bin", 12_345, 4096)
        self.assertEqual(unpack_upload(payload), ("dữ liệu.bin", 12_345, 4096))

    def test_chunk_preserves_binary_data(self) -> None:
        payload = pack_chunk(8192, bytes(range(256)) + b"\x00\n")
        self.assertEqual(
            unpack_chunk(payload), (8192, bytes(range(256)) + b"\x00\n")
        )

    def test_ack_round_trip(self) -> None:
        self.assertEqual(
            unpack_ack(pack_ack(FILE_UPLOAD, 10_000_000)),
            (int(FILE_UPLOAD), 10_000_000),
        )

    def test_download_and_delete_use_unambiguous_filename_payload(self) -> None:
        payload = pack_filename("report final.bin")
        self.assertEqual(unpack_filename(payload), "report final.bin")

    def test_file_list_response_round_trip(self) -> None:
        entries = [("empty.bin", 0), ("dữ liệu.bin", 4097)]
        self.assertEqual(
            unpack_file_list_response(pack_file_list_response(entries)), entries
        )

    def test_malformed_payloads_are_rejected(self) -> None:
        malformed = [
            lambda: unpack_upload(b"\x00\x08short"),
            lambda: unpack_ack(b"\x00" * 9),
            lambda: unpack_chunk(b"\x00" * 7),
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


if __name__ == "__main__":
    unittest.main()
