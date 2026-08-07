"""Concurrent end-to-end coverage for the Phase 2 server.

Ten clients log in at the same time, then each uploads, lists, downloads, and
verifies an isolated file.  The scenario is repeated three times with a fixed
seed so concurrency failures are reproducible instead of depending on random
test data.
"""

import hashlib
import random
import socket
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from helpers import RunningServer

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import protocol as P
from session import ErrorCode


CLIENT_COUNT = 10
ROUNDS = 3
SEED = 2026
PAYLOAD_SIZE = 64 * 1024 + 17
CHUNK_SIZE = 4096


def _read_ack(sock: socket.socket, expected_opcode: int) -> tuple[int, bytes]:
    opcode, _uid, payload = P.read_packet(sock)
    if opcode != P.ACK:
        if opcode == P.ERROR:
            code, message = P.unpack_error(payload)
            raise AssertionError(f"expected ACK, got ERROR {code}: {message}")
        raise AssertionError(f"expected ACK, got opcode {opcode:#06x}")

    acked_opcode, next_offset, digest = P.unpack_ack(payload)
    if acked_opcode != expected_opcode:
        raise AssertionError(
            f"expected ACK for {expected_opcode:#06x}, got {acked_opcode:#06x}"
        )
    return next_offset, digest


def _connect_and_login(port: int, username: str) -> tuple[socket.socket, int]:
    """Login, retrying only a transient SERVER_BUSY from server start-up."""
    deadline = time.monotonic() + 5
    while True:
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        sock.settimeout(10)
        sock.sendall(P.pack_packet(P.LOGIN, 0, P.pack_text(username)))
        opcode, uid, payload = P.read_packet(sock)
        if opcode == P.ACK:
            acked_opcode, acked_uid, _digest = P.unpack_ack(payload)
            if acked_opcode != P.LOGIN or acked_uid != uid:
                sock.close()
                raise AssertionError("LOGIN ACK contains inconsistent user information")
            return sock, uid

        if opcode == P.ERROR:
            code, message = P.unpack_error(payload)
            sock.close()
            if code == ErrorCode.SERVER_BUSY and time.monotonic() < deadline:
                time.sleep(0.02)
                continue
            raise AssertionError(f"LOGIN failed with {code}: {message}")

        sock.close()
        raise AssertionError(f"expected LOGIN ACK, got opcode {opcode:#06x}")


def _upload(sock: socket.socket, uid: int, filename: str, data: bytes) -> None:
    digest = hashlib.sha256(data).digest()
    request = P.pack_upload(filename, len(data), 0, digest)
    sock.sendall(P.pack_packet(P.FILE_UPLOAD, uid, request))
    offset, _digest = _read_ack(sock, P.FILE_UPLOAD)
    if offset != 0:
        raise AssertionError(f"new upload unexpectedly resumed at offset {offset}")

    for offset in range(0, len(data), CHUNK_SIZE):
        chunk = data[offset : offset + CHUNK_SIZE]
        sock.sendall(P.pack_packet(P.FILE_CHUNK, uid, P.pack_chunk(offset, chunk)))

    final_offset, server_digest = _read_ack(sock, P.FILE_UPLOAD)
    if final_offset != len(data) or server_digest != digest:
        raise AssertionError("upload completion ACK has the wrong size or checksum")


def _assert_private_listing(
    sock: socket.socket, uid: int, filename: str, expected_size: int
) -> None:
    sock.sendall(P.pack_packet(P.FILE_LIST, uid))
    opcode, _uid, payload = P.read_packet(sock)
    if opcode != P.FILE_LIST_RESP:
        raise AssertionError(f"expected FILE_LIST_RESP, got opcode {opcode:#06x}")
    entries = P.unpack_file_list_response(payload)
    if entries != [(filename, expected_size)]:
        raise AssertionError(f"user namespace leaked or lost files: {entries!r}")


def _download(sock: socket.socket, uid: int, filename: str) -> bytes:
    sock.sendall(P.pack_packet(P.FILE_DOWNLOAD, uid, P.pack_download(filename, 0)))
    total_size, expected_digest = _read_ack(sock, P.FILE_DOWNLOAD)

    received = bytearray()
    while len(received) < total_size:
        opcode, _uid, payload = P.read_packet(sock)
        if opcode != P.FILE_CHUNK:
            raise AssertionError(f"expected FILE_CHUNK, got opcode {opcode:#06x}")
        offset, chunk = P.unpack_chunk(payload)
        if offset != len(received):
            raise AssertionError(f"expected chunk offset {len(received)}, got {offset}")
        received.extend(chunk)

    if len(received) != total_size:
        raise AssertionError("download exceeded the size declared by the server")
    if hashlib.sha256(received).digest() != expected_digest:
        raise AssertionError("download checksum does not match the opening ACK")
    return bytes(received)


def _run_client(
    port: int,
    round_number: int,
    client_number: int,
    start_barrier: threading.Barrier,
) -> None:
    username = f"multi-r{round_number}-u{client_number}"
    filename = "shared-name.bin"
    data = random.Random(SEED + round_number * CLIENT_COUNT + client_number).randbytes(
        PAYLOAD_SIZE
    )

    sock, uid = _connect_and_login(port, username)
    try:
        # No transfer starts until all ten authenticated sessions occupy the
        # server concurrently.  Reusing the same filename also verifies that
        # per-user storage and file locks do not interfere with one another.
        start_barrier.wait(timeout=10)
        _upload(sock, uid, filename, data)
        _assert_private_listing(sock, uid, filename, len(data))
        downloaded = _download(sock, uid, filename)
        if downloaded != data:
            raise AssertionError("downloaded bytes differ from uploaded bytes")

        sock.sendall(P.pack_packet(P.LOGOUT, uid))
        _read_ack(sock, P.LOGOUT)
    finally:
        sock.close()


class ConcurrentClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = RunningServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_ten_clients_complete_upload_list_download_three_times(self) -> None:
        for round_number in range(ROUNDS):
            with self.subTest(round=round_number + 1):
                barrier = threading.Barrier(CLIENT_COUNT)
                with ThreadPoolExecutor(max_workers=CLIENT_COUNT) as executor:
                    futures = [
                        executor.submit(
                            _run_client,
                            self.server.port,
                            round_number,
                            client_number,
                            barrier,
                        )
                        for client_number in range(CLIENT_COUNT)
                    ]
                    for future in futures:
                        future.result(timeout=30)


if __name__ == "__main__":
    unittest.main()
